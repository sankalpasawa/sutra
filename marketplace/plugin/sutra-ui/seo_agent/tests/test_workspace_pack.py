"""tests/test_workspace_pack.py — the knowledge pack: the file a teammate downloads instead
of building a knowledge base.

Offline and stubbed. There is no Supabase here: `Fake` is a dict with an HTTP-shaped door on
it, and it deliberately comes in several shapes — with and without the streaming upload, the
object stat, the ranged download and the table delete — because `pack.py` has to degrade
honestly when `client.py` does not have one of them, and "honestly" is a thing you can only
prove by taking the method away.

What it proves, in the order the design cares about (design/WORKSPACE-PLAN.md):

  * WHAT IS IN EACH HALF — the four members split into core and index, and nothing else: not
    the 3.7 GB raw page cache, not `_work/`, not the .bak files a refresh leaves behind
    (section 7);
  * DETERMINISM — same knowledge base and same version in, byte-identical zip out, even when
    every file's mtime has moved. Without this nobody can say which pack a teammate holds;
  * STREAMING — a 20 MB member does not put 20 MB in memory, measured, not asserted by hope;
  * ATOMICITY — a build that dies leaves no pack, and a download that stops short never
    becomes somebody's knowledge base;
  * THE DELTA BOUNDARY, BOTH DIRECTIONS (section 3) — a change made after the pack is
    replayed by a joiner, and a change already inside the pack is not. This is the one bug
    that would be invisible until a new teammate is quietly missing forty pages;
  * THE RULING (section 2), ON BOTH HALVES — every refresh rebuilds and re-uploads the CORE,
    with no test of whether it was worth it; the INDEX goes up whenever its content hash
    differs from the published one, which is an exact comparison and not a threshold. The
    ONLY guard anywhere is that two refreshes inside five minutes coalesce into one, and the
    second supersedes the first;
  * A JOIN IS USABLE ON THE CORE ALONE — the teammate is working after 33.6 MB, and while the
    171 MB index lands behind them the real `tools/_index.status()` says "not built", which is
    the path links_pass and ownpage already take for a person with no Voyage key;
  * THE ORDER — the workspace only points at the new pack after the new pack is up, and the
    old one is only deleted after that, so a join that starts mid-rebuild gets a whole old
    pack rather than a truncated new one.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import tracemalloc
import zipfile

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store                              # noqa: E402
from seo_agent.workspace import pack                     # noqa: E402
from seo_agent.workspace._common import WorkspaceError   # noqa: E402

FAILS = []
CHECKS = [0]


def ok(label, cond, extra=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))


def _safe_call(fn):
    """Run fn and hand back whatever it raised, so a refusal can be checked inline."""
    try:
        return fn()
    except Exception as e:                                        # noqa: BLE001
        return e


TMP = []


def tmpdir(name):
    d = tempfile.mkdtemp(prefix="pack-%s-" % name)
    TMP.append(d)
    return d


# ---- a knowledge base on disk, small but the right SHAPE ----------------------------------

def make_knowledge(root, pages=6, big_mb=0, extras=True):
    """The four members plus the things that must NOT travel."""
    os.makedirs(root, exist_ok=True)
    store.write_json(os.path.join(root, "site_index.json"),
                     {"domain": "example.com", "page_count": pages,
                      "pages": [{"url": "https://example.com/p%d" % i, "title": "P%d" % i}
                                for i in range(pages)]})
    line = json.dumps({"url": "https://example.com/p", "text": "the quick brown fox " * 40})
    body = (line + "\n") * (1 if not big_mb else int(big_mb * 1e6 / (len(line) + 1)))
    with open(os.path.join(root, "content-database.jsonl"), "w") as f:
        f.write(body)

    ci = os.path.join(root, "content-index")
    os.makedirs(os.path.join(ci, "body", "parts"), exist_ok=True)
    store.write_json(os.path.join(ci, "index.json"),
                     {"pages": pages, "chunks": pages * 3, "model": "voyage-4-large"})
    for i in range(3):
        with open(os.path.join(ci, "body", "parts", "part_%05d.npy" % i), "wb") as f:
            f.write(os.urandom(4096))
    with open(os.path.join(ci, "body", "meta.jsonl"), "w") as f:
        f.write('{"url":"https://example.com/p0"}\n')
    # The two files `_index.status()` gates on. Without them a real index reader says "not
    # built", which is exactly what the core-alone tests below rely on.
    os.makedirs(os.path.join(ci, "title"), exist_ok=True)
    with open(os.path.join(ci, "title", "meta.jsonl"), "w") as f:
        for i in range(pages):
            f.write(json.dumps({"url": "https://example.com/p%d" % i}) + "\n")
    with open(os.path.join(ci, "title", "vectors.npy"), "wb") as f:
        f.write(b"\x93NUMPY\x01\x00" + os.urandom(2048))

    br = os.path.join(root, "brand")
    os.makedirs(os.path.join(br, "_work", "persona"), exist_ok=True)
    store.write_json(os.path.join(br, "company.json"), {"brand": "Example", "domain": "example.com"})
    for n in ("writer-brief.md", "style-guide.md"):
        open(os.path.join(br, n), "w").write("# %s\nreal brand file\n" % n)
    open(os.path.join(br, "_work", "persona", "step1.json"), "w").write('{"scratch": true}')

    if extras:
        # Everything section 7 says never syncs, planted where a real install puts it.
        os.makedirs(os.path.join(root, "_raw", "pages"), exist_ok=True)
        open(os.path.join(root, "_raw", "pages", "p0.html"), "w").write("<html>4 GB of this</html>")
        os.makedirs(os.path.join(root, "_work", "refresh"), exist_ok=True)
        open(os.path.join(root, "_work", "refresh", "stage.json"), "w").write("{}")
        open(os.path.join(root, "site_index.json.bak-pre-refresh"), "w").write("{}")
        open(os.path.join(root, "content-database.jsonl.bak-pre-refresh"), "w").write("")
        open(os.path.join(br, ".DS_Store"), "w").write("x")
    return root


# ---- the fake Supabase --------------------------------------------------------------------

class Fake:
    """Storage objects and tables in dicts. Every call is recorded, in order, because half of
    what this suite checks is the ORDER things happened in.

    The optional methods come off on purpose: `client.py` is owned elsewhere and may not have
    the object stat, the ranged read or the table delete on day one, and pack.py has to
    degrade HONESTLY rather than assume. You can only prove that by taking them away.
    """

    # schema.sql creates the workspace row at setup, so one always exists. `pack_columns`
    # off is the project whose table predates the six columns the pack wants — the case
    # HANDOFF-W3 asks the schema owner to add, and which pack.py must survive without.
    BASE_WS = {"id": "8f1c-workspace", "name": "Team workspace", "schema_version": 1,
               "pack_version": 0, "created_at": "2026-09-10T00:00:00Z"}
    PACK_COLS = {"pack_sha256": "", "pack_bytes": 0, "pack_parts": 0, "pack_part_bytes": 0,
                 "pack_change_id": 0, "pack_built_at": "", "index_version": 0}

    def __init__(self, buckets=("knowledge",), stat=True, deleting=True, ranged=True,
                 truncate_at=None, limit=None, sliced=False, pack_columns=True, no_ws=False):
        self.objects = {}
        ws = dict(self.BASE_WS, **(self.PACK_COLS if pack_columns else {}))
        self.tables = {"workspace": [] if no_ws else [ws], "pages": [], "changes": []}
        self.log = []
        self._buckets = list(buckets)
        self.limit = limit
        self.truncate_at = truncate_at          # simulate an object that stores fewer bytes
        if not stat:
            self.stat = None
        if not deleting:
            self.delete = None
        if not ranged:
            self.download_stream = None
        if not sliced:
            self.upload_file = None          # the day-one client.py; see HANDOFF-W3

    # -- storage -------------------------------------------------------------------------
    def buckets(self):
        return [{"name": b, "file_size_limit": self.limit} for b in self._buckets]

    def upload(self, bucket, path, data):
        self._bucket(bucket)
        data = bytes(data)
        if self.truncate_at is not None:
            data = data[:self.truncate_at]
        self.log.append(("upload", path, len(data)))
        self.objects[path] = data

    def upload_file(self, bucket, path, file_path, offset=0, length=None, progress=None):
        """The slice-off-disk upload pack.py prefers when client.py has it."""
        self._bucket(bucket)
        with open(file_path, "rb") as f:
            f.seek(offset)
            data = f.read(length)
        self.log.append(("upload_file", path, len(data)))
        self.objects[path] = data

    def download(self, bucket, path):
        self._bucket(bucket)
        self.log.append(("download", path, 0))
        if path not in self.objects:
            raise WorkspaceError("no such object %s" % path, 404)
        return self.objects[path]

    def download_stream(self, bucket, path, start=0):
        self._bucket(bucket)
        self.log.append(("download_stream", path, start))
        if path not in self.objects:
            raise WorkspaceError("no such object %s" % path, 404)
        data = self.objects[path][start:]
        # Small blocks on purpose: a real 205 MB pull gives a progress bar hundreds of
        # updates, and a fake that handed back one lump could not prove the bar moves.
        for i in range(0, len(data), 4096):
            yield data[i:i + 4096]

    def stat(self, bucket, path):
        self._bucket(bucket)
        if path not in self.objects:
            return None
        return {"name": path, "size": len(self.objects[path])}

    def remove(self, bucket, path):
        self._bucket(bucket)
        self.log.append(("remove", path, 0))
        self.objects.pop(path, None)

    def _bucket(self, bucket):
        if bucket not in self._buckets:
            raise WorkspaceError("new row violates row-level security policy", 403)

    # -- tables --------------------------------------------------------------------------
    def select(self, table, where=None, order=None, limit=None, columns="*", **kw):
        """Same shape as client.select: where / order="id.desc" / limit."""
        rows = [dict(r) for r in self.tables.setdefault(table, []) if self._match(r, where)]
        self.log.append(("select", table, len(rows)))
        if order:
            col, _, direction = order.partition(".")
            rows.sort(key=lambda r: r.get(col), reverse=(direction == "desc"))
        return rows[:int(limit)] if limit else rows

    def upsert(self, table, rows):
        self.log.append(("upsert", table, len(rows)))
        cur = self.tables.setdefault(table, [])
        for new in rows:
            for i, r in enumerate(cur):
                if r.get("id") == new.get("id"):
                    cur[i] = dict(r, **new)
                    break
            else:
                cur.append(dict(new))

    def delete(self, table, where=None):
        cur = self.tables.setdefault(table, [])
        keep = [r for r in cur if not self._match(r, where)]
        n = len(cur) - len(keep)
        self.tables[table] = keep
        self.log.append(("delete", table, n))
        return n

    def creds(self):
        return {"url": "https://example.supabase.co", "key": "sb_publishable_TEST"}

    @staticmethod
    def _match(row, where):
        """The same `where` shape client.select takes: {col: value} or {col: (op, value)}."""
        for col, want in (where or {}).items():
            got = row.get(col)
            if isinstance(want, tuple):
                op, val = want
                tests = {"lte": lambda: got <= val, "lt": lambda: got < val,
                         "gt": lambda: got > val, "gte": lambda: got >= val}
                if got is None or not tests[op]():
                    return False
            elif got != want:
                return False
        return True

    def joined(self, half, version):
        """Every part of a half, in order, glued back into the one file it came from."""
        n = json.loads(self.objects[pack.sidecar_name(half, version)])["parts"]
        return b"".join(self.objects[pack.part_name(half, version, i)] for i in range(n))

    def names(self, kind):
        return [p for k, p, _ in self.log if k == kind]

    def order(self, *kinds):
        return [(k, p) for k, p, _ in self.log if k in kinds]


# ==========================================================================================
print("\nwhat is in each half, and what is deliberately not")

K = make_knowledge(os.path.join(tmpdir("kb"), "knowledge"))
names = [r[0] for r in pack.members(K)]
core = [r[0] for r in pack.members(K, "core")]
idx = [r[0] for r in pack.members(K, "index")]

ok("the catalogue, every page's text and the brand pack are the CORE — everything needed to "
   "pick an idea and write", sorted({n.split("/")[0] for n in core}) ==
   ["brand", "content-database.jsonl", "site_index.json"], sorted(set(core)))
ok("the meaning index is the other half, on its own",
   {n.split("/")[0] for n in idx} == {"content-index"})
ok("between them the two halves are the whole pack, with nothing in both",
   sorted(core + idx) == sorted(names) and not (set(core) & set(idx)))
ok("the raw page cache never travels — it is 3.7 GB on his real install",
   not any(n.startswith("_raw") for n in names))
ok("run folders and working files never travel, brand/_work included",
   not any("_work/" in n or n.startswith("_work") for n in names),
   [n for n in names if "_work" in n])
ok("the .bak-pre-refresh files a refresh leaves behind never travel",
   not any(".bak" in n for n in names), [n for n in names if ".bak" in n])
ok("no .DS_Store", not any(".DS_Store" in n for n in names))
ok("each half is sorted, which is what makes two builds identical",
   core == sorted(core) and idx == sorted(idx))
ok("asking for a half that does not exist is refused rather than quietly packing nothing",
   isinstance(_safe_call(lambda: pack.members(K, "everything")), pack.PackError))

ok("survey names what is missing before anything reads 337 MB", pack.survey(K)["missing"] == [])
gone = os.path.join(K, "content-index")
shutil.move(gone, gone + "-hidden")
ok("a knowledge base with no meaning index has a complete CORE — the half that matters is "
   "not held hostage to the half that does not", pack.survey(K, "core")["missing"] == [])
ok("...and the index half is reported missing, by name",
   pack.survey(K, "index")["missing"] == ["content-index"])
shutil.move(gone + "-hidden", gone)

shutil.move(os.path.join(K, "brand"), os.path.join(K, "brand-hidden"))
try:
    pack.build(os.path.join(tmpdir("x"), "p.zip"), kroot=K)
    ok("a half-built knowledge base refuses to become a pack", False)
except pack.PackIncomplete as e:
    ok("a half-built knowledge base refuses to become a pack, and says which part is missing",
       "brand" in str(e), str(e))
shutil.move(os.path.join(K, "brand-hidden"), os.path.join(K, "brand"))


# ==========================================================================================
print("\ndeterminism: the same knowledge base gives the same bytes")

d = tmpdir("det")
a = pack.build(os.path.join(d, "a.zip"), kroot=K, version=3)
b = pack.build(os.path.join(d, "b.zip"), kroot=K, version=3)
ok("two builds of the same core are byte-identical", a["sha256"] == b["sha256"],
   (a["sha256"][:12], b["sha256"][:12]))
ai = pack.build(os.path.join(d, "ai.zip"), kroot=K, version=1, half="index")
bi = pack.build(os.path.join(d, "bi.zip"), kroot=K, version=1, half="index")
ok("and two builds of the same index are byte-identical too", ai["sha256"] == bi["sha256"])
ok("the two halves are different files", a["sha256"] != ai["sha256"])

old = time.time() - 86400 * 30
for arc, src, _ in pack.members(K):
    os.utime(src, (old, old))
c = pack.build(os.path.join(d, "c.zip"), kroot=K, version=3)
ok("touching every file changes nothing — the zip timestamps are pinned",
   c["sha256"] == a["sha256"])

e = pack.build(os.path.join(d, "e.zip"), kroot=K, version=4)
ok("a new version is a different object", e["sha256"] != a["sha256"])
ok("...but content_sha256 says the knowledge itself did not move",
   e["content_sha256"] == a["content_sha256"])

ok("content_sha() computes that same hash WITHOUT building the zip — which is how 'has the "
   "index changed?' is answered exactly, rather than estimated",
   pack.content_sha(K, "index") == ai["content_sha256"])
ok("...and it is the core's hash for the core", pack.content_sha(K, "core") == a["content_sha256"])

open(os.path.join(K, "brand", "style-guide.md"), "a").write("one more line\n")
f = pack.build(os.path.join(d, "f.zip"), kroot=K, version=3)
ok("a real change to the knowledge base does change content_sha256",
   f["content_sha256"] != a["content_sha256"])
ok("...and does NOT change the index's, because they are separate halves",
   pack.content_sha(K, "index") == ai["content_sha256"])


# ==========================================================================================
print("\nthe manifest, and the checksum a joiner trusts")

man = pack.read_manifest(f["path"])
ok("the manifest is inside the pack", man["pack_schema"] == pack.PACK_SCHEMA)
ok("it says which half it is", man["half"] == "core")
ok("it says which version it is", man["version"] == 3)
ok("the core says how many pages, read out of site_index.json's first 4 KB",
   man["pages"] == 6, man["pages"])
ok("the index half says how many chunks it holds",
   pack.read_manifest(ai["path"])["chunks"] == 18)
ok("neither half's manifest describes the other — the core carried the index's counts once, "
   "and that made the core's bytes move whenever the index did",
   "chunks" not in man and "pages" not in pack.read_manifest(ai["path"]))
ok("it carries a sha256 per file, so a single bad file can be named",
   all(len(x["sha256"]) == 64 for x in man["entries"]))
ok("it lists exactly what was packed", len(man["entries"]) == len(pack.members(K, "core")))
with zipfile.ZipFile(f["path"]) as zf:
    ok("manifest.json is the LAST entry, because it carries the others' hashes",
       zf.namelist()[-1] == pack.MANIFEST_NAME)
ok("the pack's own sha256 is the sha256 of the file on disk",
   hashlib.sha256(open(f["path"], "rb").read()).hexdigest() == f["sha256"])
ok("verify() names the checks it actually ran, and never claims one it skipped",
   pack.verify(f["path"], sha256=f["sha256"], deep=True)["checks"] == ["sha256", "manifest", "crc"])
ok("verify() with no sha256 does not pretend it checked one",
   "sha256" not in pack.verify(f["path"])["checks"])


# ==========================================================================================
print("\nstreaming: 337 MB must never sit in memory")

BIG = make_knowledge(os.path.join(tmpdir("big"), "knowledge"), pages=6, big_mb=20, extras=False)
raw = pack.survey(BIG, "core")["raw_bytes"]
tracemalloc.start()
pack.build(os.path.join(tmpdir("bigout"), "p.zip"), kroot=BIG, version=1, deep_verify=False)
peak = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
ok("the member really is 20 MB, so the measurement means something", raw > 20e6, raw)
ok("building it peaks under 8 MB, not 20 — it is read a chunk at a time",
   peak < 8e6, "%.1f MB peak against %.1f MB packed" % (peak / 1e6, raw / 1e6))
ok("one chunk is the largest thing this module holds", pack.CHUNK == 1 << 20)

tracemalloc.start()
pack.content_sha(BIG, "core")
peak2 = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()
ok("the staleness hash is streamed too — it never loads the index to find out whether the "
   "index moved", peak2 < 4e6, "%.1f MB" % (peak2 / 1e6))


# ==========================================================================================
print("\natomic: a half-built pack must never exist")

d2 = tmpdir("atomic")
target = os.path.join(d2, "p.zip")
broken = make_knowledge(os.path.join(tmpdir("broken"), "knowledge"))
real_sha = pack._sha_file
try:
    pack._sha_file = lambda p: (_ for _ in ()).throw(OSError("disk went away mid-build"))
    try:
        pack.build(target, kroot=broken, version=1)
        ok("a build that dies part way leaves no pack", False)
    except OSError:
        ok("a build that dies part way leaves no pack", not os.path.exists(target))
finally:
    pack._sha_file = real_sha
ok("...and leaves no .building file behind either",
   not [n for n in os.listdir(d2) if n.startswith(".building")], os.listdir(d2))
pack.build(target, kroot=broken, version=1)
ok("the same path builds fine on the next attempt", os.path.exists(target))


# ==========================================================================================
print("\npublishing: the core goes up EVERY time, the index whenever it changed")

ok("PART_BYTES is a named constant, and it is under Supabase's 50 MB free-plan object cap",
   pack.PART_BYTES == 40 * 1024 * 1024)
ok("a bucket that reports a SMALLER limit wins over our default, with headroom left",
   pack.part_size(Fake(limit=10 * 1024 * 1024)) == 6 * 1024 * 1024)
ok("a bucket that reports a bigger limit does not make us send one huge object",
   pack.part_size(Fake(limit=50 * 1024 * 1024 * 1024)) == pack.PART_BYTES)
ok("a client that cannot report a limit falls back to the constant, not to no limit",
   pack.part_size(Fake()) == pack.PART_BYTES)

REAL_PART = pack.PART_BYTES
pack.PART_BYTES = 512           # so a test-sized half really does go up in several parts

cli = Fake()
cli.tables["changes"] = [{"id": i} for i in range(1, 6)]          # the log is at 5
cli.tables["pages"] = [{"url": "/a", "pack_version": 0}, {"url": "/b", "pack_version": 0},
                       {"url": "/c", "pack_version": 1}]
res = pack.publish(cli, kroot=K, last_seen_id=5)                  # level with the log

ok("the first pack is core version 1", res["version"] == 1)
ok("the two halves live in their own folders, so the Supabase dashboard reads as two things",
   pack.part_name("core", 1, 0) == "pack/core/1.zip.000" and
   pack.part_name("index", 1, 0) == "pack/index/1.zip.000")
ok("the core went up as several parts, because one object may not exceed the plan's file cap",
   res["parts"] > 1 and pack.part_name("core", 1, 0) in cli.objects, res["parts"])
ok("the parts are zero-padded so a bucket listing sorts the way the file reads",
   pack.part_name("core", 1, 3) == "pack/core/1.zip.003")
ok("the core's parts glued back together are exactly the file that was built",
   hashlib.sha256(cli.joined("core", 1)).hexdigest() == res["sha256"])
ok("a .sha256 sidecar sits beside them, so the bucket is readable on its own",
   "pack/core/1.zip.sha256" in cli.objects)
side = json.loads(cli.objects["pack/core/1.zip.sha256"])
ok("the sidecar carries the half, the checksum, the size and the part count",
   side["half"] == "core" and side["sha256"] == res["sha256"] and side["parts"] == res["parts"])
ok("the index went up too, the first time — it had never been published",
   res["index_rebuilt"] is True and res["index_version"] == 1
   and pack.part_name("index", 1, 0) in cli.objects)
ok("the workspace row points at both halves",
   cli.tables["workspace"][0]["pack_version"] == 1
   and cli.tables["workspace"][0]["index_version"] == 1)
ok("the row it updated is the one schema.sql created, by its real id — nothing invents a "
   "second workspace", len(cli.tables["workspace"]) == 1
   and cli.tables["workspace"][0]["id"] == Fake.BASE_WS["id"])
ok("the upload was verified by comparing the stored size, and says so",
   res["upload_verified"] == "size", res["upload_verified"])

up = [p for k, p, _ in cli.log if k in ("upload", "upload_file")]
core_up = [p for p in up if p.startswith("pack/core/")]
ok("the core's SIDECAR is written last of the core's objects — until it exists there is no "
   "pack, only bytes, so a half-finished upload cannot be mistaken for one",
   core_up[-1] == "pack/core/1.zip.sha256", core_up[-3:])
seq = cli.order("upload", "upload_file", "upsert")
ok("the core is uploaded BEFORE the workspace points at it — a join mid-rebuild gets the "
   "whole old pack, never a truncated new one",
   seq.index(("upload", "pack/core/1.zip.sha256")) <
   [i for i, x in enumerate(seq) if x[0] == "upsert"][0])

# ---- THE RULING, on each half -----------------------------------------------------------
before = dict(cli.tables["workspace"][0])
r2 = pack.publish(cli, kroot=K, last_seen_id=5)
ok("A SECOND REFRESH WITH NOTHING CHANGED STILL REBUILDS AND RE-UPLOADS THE CORE. No "
   "threshold, no 'has it moved enough' — the owner's ruling, applied literally",
   r2["version"] == 2 and pack.part_name("core", 2, 0) in cli.objects)
ok("...and the workspace moved to it", cli.tables["workspace"][0]["pack_version"] == 2)
ok("the index did NOT go up again, because its bytes are bit-for-bit what is already in the "
   "bucket — an exact hash comparison, not an estimate",
   r2["index_rebuilt"] is False and r2["index"] == "unchanged" and r2["index_version"] == 1)
ok("...and nothing about the index moved on the row either",
   cli.tables["workspace"][0]["index_version"] == before["index_version"])
ok("no second index object was created", pack.part_name("index", 2, 0) not in cli.objects)

with open(os.path.join(K, "content-index", "body", "meta.jsonl"), "a") as fh:
    fh.write('{"url":"https://example.com/p9"}\n')
r3 = pack.publish(cli, kroot=K, last_seen_id=5)
ok("THE MOMENT THE INDEX CHANGES IT GOES UP, on the same call and on the same terms as the "
   "core — no waiting for a convenient time",
   r3["index_rebuilt"] is True and r3["index_version"] == 2
   and pack.part_name("index", 2, 0) in cli.objects)
ok("...and the core went up as well, as it does every single time", r3["version"] == 3)
ok("one changed line is enough — the comparison is the whole content, not a size or a date",
   json.loads(cli.objects["pack/index/2.zip.sha256"])["content_sha256"] !=
   json.loads(cli.objects["pack/index/1.zip.sha256"])["content_sha256"])

noindex = make_knowledge(os.path.join(tmpdir("noidx"), "knowledge"))
shutil.rmtree(os.path.join(noindex, "content-index"))
ni = Fake()
rni = pack.publish(ni, kroot=noindex, last_seen_id=0)
ok("a knowledge base with no meaning index still publishes its core — plenty of people have "
   "no Voyage key and they are not blocked from sharing",
   rni["version"] == 1 and pack.part_name("core", 1, 0) in ni.objects)
ok("...and says plainly that there was no index to send",
   rni["index_rebuilt"] is False and rni["index"] == "not built here")

sl = Fake(sliced=True)
rs = pack.publish(sl, kroot=K, last_seen_id=0)
ok("a client that can upload a SLICE of a file off disk is used in preference, so a 40 MB "
   "part never has to sit in memory", "upload_file" in [k for k, _, _ in sl.log])
ok("...and it produces exactly the same pack as the bytes path",
   hashlib.sha256(sl.joined("core", 1)).hexdigest() == rs["sha256"])

cli2 = Fake(stat=False)
r_ns = pack.publish(cli2, kroot=K, last_seen_id=0)
ok("a client that cannot stat an object does not claim the size was checked",
   r_ns["upload_verified"] in ("exists", "none"), r_ns["upload_verified"])

cli3 = Fake(truncate_at=100)
try:
    pack.publish(cli3, kroot=K, last_seen_id=0)
    ok("a part that stored fewer bytes than we sent is caught", False)
except pack.PackCorrupt as e:
    ok("a part that stored fewer bytes than we sent is caught, and says nobody is affected",
       "previous pack is untouched" in str(e), str(e))
ok("...and the truncated upload never became the workspace's pack — the row still says 0",
   cli3.tables["workspace"][0]["pack_version"] == 0)
ok("...and it never got a sidecar, so nothing downstream can follow it",
   "pack/core/1.zip.sha256" not in cli3.objects)


class Rls(Fake):
    """The bucket exists in the listing but no policy lets us write to it — the exact shape
    Supabase answers with when schema.sql's storage block hit insufficient_privilege. None of
    the storage policies have been proved live yet, so this is the likeliest first failure."""
    def upload(self, bucket, path, data):
        raise WorkspaceError("Supabase allowed the key but refused the row. new row violates "
                             "row-level security policy", 403, {"statusCode": "403"})

try:
    pack.publish(Rls(), kroot=K, last_seen_id=0)
    ok("a storage policy gap is reported as a SETUP problem, not a pack problem", False)
except pack.WorkspaceNotSetUp as e:
    ok("a storage policy gap is reported as a SETUP problem, not a pack problem", True)
    ok("...and the message names the setup script and says the existing pack is untouched, "
       "so nobody goes hunting for a bug in pack.py",
       "setup" in str(e).lower() and "untouched" in str(e), str(e))
ok("a missing bucket is the same family of error, so one handler catches both",
   issubclass(pack.BucketMissing, pack.WorkspaceNotSetUp))

cli4 = Fake(buckets=())
try:
    pack.publish(cli4, kroot=K, last_seen_id=0)
    ok("a missing bucket is caught before 337 MB is packed", False)
except pack.BucketMissing as e:
    ok("a missing bucket is caught before 337 MB is packed", not cli4.objects)
    ok("...and the message sends the reader to the setup script, not to pack.py — the "
       "publishable key is not allowed to create a bucket (measured 2026-09-10)",
       "setup" in str(e).lower() and "not allowed to create" in str(e), str(e))


# ==========================================================================================
print("\nthe delta boundary — the bug that would be invisible until a teammate is short 40 pages")

ok("the boundary is the client's OWN last_seen_id, not the log's high water mark: a change "
   "another teammate wrote but this client has not applied is NOT inside the pack",
   res["pack_change_id"] == 5, res["pack_change_id"])
ok("the same number is on the workspace row, so joiners and trimming cannot disagree",
   cli.tables["workspace"][0]["pack_change_id"] == 5)
ok("this client was level with the log, so the trim was safe to run", res["behind"] == 0)

trim = Fake()
trim.tables["changes"] = [{"id": 5}]
trim.tables["pages"] = [{"url": "/a", "pack_version": 0}, {"url": "/b", "pack_version": 0},
                        {"url": "/c", "pack_version": 1}]
pack.publish(trim, kroot=K, last_seen_id=5)
left = sorted(r["url"] for r in trim.tables["pages"])
ok("pages the pack absorbed are trimmed — that is what keeps the database under 5 MB",
   left == ["/c"], left)
ok("a row recorded AFTER the workspace moved on is not in the pack, and survives",
   trim.tables["pages"][0]["pack_version"] == 1)
ok("the column is pack_version, schema.sql's own word for it, not a second name for the "
   "same idea", all("pack_version" in r for r in trim.tables["pages"]))

# THE RULE ALL THREE OF US HOLD (2026-09-10). A trim is a plain DELETE; every teammate's
# sync ignores a `pages` delete precisely because it means "the delta was tidied". If this
# file ever marked, blanked or updated a pages row instead, that housekeeping would reach
# four other people as content and empty their catalogues. `mirror._trimmed()` is the other
# half of the rule, and it keys on the log row's op being `delete`.
touched = Fake()
survivor = {"url": "/new", "pack_version": 1, "op": "changed", "title": "A", "body": "b"}
touched.tables["pages"] = [{"url": "/a", "pack_version": 0, "op": "changed", "title": "A"},
                           dict(survivor)]
pack.publish(touched, kroot=K, last_seen_id=0)
ops = sorted({k for k, t, _ in touched.log if t == "pages"})
ok("trimming pages is a DELETE and only a delete — never an update, never a mark",
   ops == ["delete"], ops)
ok("the row that survived is untouched, field for field — a trim writes nothing at all",
   touched.tables["pages"] == [survivor], touched.tables["pages"])
ok("...and `op` is left entirely alone: 'this page went away' is op='gone' on an UPDATE, and "
   "it is the refresh path's job, never this file's",
   touched.tables["pages"][0]["op"] == "changed")

joiner = os.path.join(tmpdir("join"), "knowledge")
got = pack.join(cli, kroot=joiner, index="wait")
ok("a joiner is told to replay from exactly where the pack stops",
   got["replay_from"] == 5, got["replay_from"])
ok("...and it is a real boundary, not a fallback", got["full_replay"] is False)
cli.tables["changes"] += [{"id": 6}, {"id": 7}]
replayed = [c["id"] for c in cli.tables["changes"] if c["id"] > got["replay_from"]]
ok("DIRECTION 1 — a change made after the pack IS replayed, so nothing is missed",
   replayed == [6, 7], replayed)
ok("DIRECTION 2 — a change already inside the pack is NOT replayed, so nothing is applied twice",
   not any(i in replayed for i in (1, 2, 3, 4, 5)), replayed)

behind = Fake()
behind.tables["changes"] = [{"id": i} for i in range(1, 30)]      # the log is at 29
behind.tables["pages"] = [{"url": "/x", "pack_version": 0}]
rb_ = pack.publish(behind, kroot=K, last_seen_id=5)               # we have only applied 5
ok("a client that is BEHIND the log still rebuilds and uploads — the ruling says every "
   "refresh does, with no exceptions",
   rb_["version"] == 1 and pack.part_name("core", 1, 0) in behind.objects)
ok("...and it says how far behind it is", rb_["behind"] == 24, rb_["behind"])
ok("...but it trims NOTHING, because a page another teammate changed is not in the pack it "
   "just built, and deleting that row would lose the change for every future joiner",
   behind.tables["pages"] == [{"url": "/x", "pack_version": 0}], behind.tables["pages"])
ok("...and the boundary it publishes is still its own cursor, so the joiner replays the 24 "
   "it does not have", rb_["pack_change_id"] == 5)

blind = Fake()
blind.select = lambda t, **k: ([dict(blind.tables["workspace"][0])] if t == "workspace"
                               else (_ for _ in ()).throw(WorkspaceError("no changes", 404)))
rblind = pack.publish(blind, kroot=K, last_seen_id=0)
ok("a client that cannot even ask how far behind it is deletes nothing either — you do not "
   "delete what you cannot prove", rblind["behind"] is None and rblind["pages_trimmed"] == 0)

cli_nodel = Fake(deleting=False)
r5 = pack.publish(cli_nodel, kroot=K, last_seen_id=0)
ok("a client that cannot delete rows reports the trim as not done rather than assuming it",
   r5["pages_trimmed"] is None, r5["pages_trimmed"])

thin = Fake(pack_columns=False)
rt = pack.publish(thin, kroot=K, last_seen_id=4)
ok("a workspace table that predates the pack columns still gets a pack — the version is the "
   "one column that has always been there", thin.tables["workspace"][0]["pack_version"] == 1)
ok("...and the columns it could not store are NAMED, not silently dropped",
   rt["row_fields_missing"] == ["index_version", "pack_built_at", "pack_bytes",
                                "pack_change_id", "pack_part_bytes", "pack_parts",
                                "pack_sha256"], rt["row_fields_missing"])
ok("...and it says the index cannot be versioned, so nobody is surprised when there is only "
   "ever one generation of it", rt["index_versioning"] is False)
rt2 = pack.publish(thin, kroot=K, last_seen_id=4)
ok("...and even so the index is not re-sent when it has not changed: the published sidecar "
   "answers the question when the row cannot", rt2["index_rebuilt"] is False)
tj = pack.join(thin, kroot=os.path.join(tmpdir("thin"), "knowledge"), index="skip")
ok("a joiner against such a workspace falls back to the sidecar for the checksum and still "
   "verifies the file", tj["files"] == len(pack.members(K, "core")))
ok("...and it replays the WHOLE log rather than skipping rows, which is the safe direction, "
   "and says that is what it did", tj["replay_from"] == 0 and tj["full_replay"] is True)

try:
    pack.publish(Fake(no_ws=True), kroot=K, last_seen_id=0)
    ok("a project with no workspace row refuses rather than inventing one", False)
except pack.PackIncomplete as e:
    ok("a project with no workspace row refuses rather than inventing one, and says to run "
       "setup", "setup" in str(e).lower(), str(e))


# ==========================================================================================
print("\nkeeping the previous generation: a five-minute download must not be deleted underneath")

fresh_cli = Fake()
for i in range(3):
    with open(os.path.join(K, "content-index", "body", "meta.jsonl"), "a") as fh:
        fh.write('{"url":"https://example.com/g%d"}\n' % i)     # move BOTH halves each time
    pack.publish(fresh_cli, kroot=K, last_seen_id=0)
ok("the core is on version 3", fresh_cli.tables["workspace"][0]["pack_version"] == 3)
ok("...and so is the index, because it changed every time",
   fresh_cli.tables["workspace"][0]["index_version"] == 3)
for half in ("core", "index"):
    ok("%s 3 is live" % half, pack.part_name(half, 3, 0) in fresh_cli.objects)
    ok("%s 2, the previous one, is kept whole" % half,
       pack.part_name(half, 2, 0) in fresh_cli.objects)
    ok("%s 1 is gone: two generations per half, so a join that started before the rebuild "
       "still finds its object" % half,
       not [k for k in fresh_cli.objects if k.startswith("pack/%s/1." % half)],
       [k for k in fresh_cli.objects if k.startswith("pack/%s/1." % half)])
ok("the old sidecar is deleted FIRST, so the leftovers are unreachable rubbish rather than "
   "a pack somebody could half-follow",
   [p for p in fresh_cli.names("remove") if p.startswith("pack/core/1")][0]
   == "pack/core/1.zip.sha256")
ok("the deletes happen after the workspace moved, never before",
   fresh_cli.order("upsert", "remove")[0][0] == "upsert")
ok("PACK_KEEP_GENERATIONS is a named constant, not a 2 buried in a loop",
   pack.PACK_KEEP_GENERATIONS == 2)


# ==========================================================================================
print("\ndownloading: a truncated file must never become somebody's knowledge base")

dl = tmpdir("dl")
row = pack.workspace_row(fresh_cli)
V = row["pack_version"]
whole = fresh_cli.joined("core", V)
d1 = pack.download(fresh_cli, "core", V, os.path.join(dl, "p.zip"),
                   sha256=row["pack_sha256"], total_bytes=row["pack_bytes"],
                   parts=row["pack_parts"], part_bytes=row["pack_part_bytes"])
ok("a whole download verifies and lands", os.path.exists(d1["path"]))
ok("the parts arrived joined in the right order", open(d1["path"], "rb").read() == whole)
ok("it can resume inside a part, because the client can ask for a byte range",
   d1["resume"] == "range")

d1b = pack.download(fresh_cli, "core", V, os.path.join(dl, "p2.zip"))
ok("a joiner with nothing but the half and the version reads the sidecar and still gets it "
   "right", d1b["bytes"] == row["pack_bytes"] and d1b["parts"] == row["pack_parts"])
di = pack.download(fresh_cli, "index", row["index_version"], os.path.join(dl, "i.zip"))
ok("the index half downloads the same way, from its own sidecar",
   open(di["path"], "rb").read() == fresh_cli.joined("index", row["index_version"]))

seen = []
pack.download(fresh_cli, "core", V, os.path.join(dl, "q.zip"), sha256=row["pack_sha256"],
              total_bytes=row["pack_bytes"], parts=row["pack_parts"],
              part_bytes=row["pack_part_bytes"],
              progress=lambda st, done, tot, note: seen.append((st, done, tot)))
ok("it reports real bytes of a real total, which is what a progress bar needs",
   seen and seen[-1][1] == row["pack_bytes"] and seen[-1][2] == row["pack_bytes"], seen[-1:])
ok("progress climbs rather than jumping to the end", len(seen) > 1 and seen[0][1] < seen[-1][1])

half_p = os.path.join(dl, "r.zip")
with open(half_p + ".part", "wb") as fh:
    fh.write(whole[:len(whole) // 2])
r6 = pack.download(fresh_cli, "core", V, half_p, sha256=row["pack_sha256"],
                   total_bytes=row["pack_bytes"], parts=row["pack_parts"],
                   part_bytes=row["pack_part_bytes"])
ok("a half-finished download RESUMES from where it stopped instead of pulling it all again",
   r6["resumed_from"] == len(whole) // 2, r6["resumed_from"])
ok("...and the resumed file still verifies against the published checksum",
   pack.verify(half_p, sha256=row["pack_sha256"])["ok"])

cli_nr = Fake(ranged=False)
pack.publish(cli_nr, kroot=K, last_seen_id=0)
rn = pack.workspace_row(cli_nr)
nrw = cli_nr.joined("core", rn["pack_version"])
nr = os.path.join(tmpdir("nr"), "p.zip")
with open(nr + ".part", "wb") as fh:
    fh.write(nrw[:rn["pack_part_bytes"] + 10])          # two whole parts and a bit
d3 = pack.download(cli_nr, "core", rn["pack_version"], nr, sha256=rn["pack_sha256"],
                   total_bytes=rn["pack_bytes"], parts=rn["pack_parts"],
                   part_bytes=rn["pack_part_bytes"])
ok("a client with NO ranged read still resumes — at part granularity, so a dropped "
   "connection costs one part and not the whole pack",
   d3["resume"] == "part" and d3["resumed_from"] == rn["pack_part_bytes"], d3)
ok("...and what it produced is still the right file", open(nr, "rb").read() == nrw)

bad = os.path.join(dl, "bad.zip")
try:
    pack.download(fresh_cli, "core", V, bad, sha256="0" * 64, total_bytes=row["pack_bytes"],
                  parts=row["pack_parts"], part_bytes=row["pack_part_bytes"])
    ok("a pack whose checksum does not match is refused", False)
except pack.PackCorrupt as e:
    ok("a pack whose checksum does not match is refused, and says nothing was installed",
       "Nothing was installed" in str(e), str(e))
ok("...and it did not land at the real path", not os.path.exists(bad))
ok("...and the bad .part was thrown away rather than resumed for ever",
   not os.path.exists(bad + ".part"))

last = pack.part_name("core", V, row["pack_parts"] - 1)
keep_last = fresh_cli.objects[last]
fresh_cli.objects[last] = keep_last[:2]
short = os.path.join(dl, "short.zip")
try:
    pack.download(fresh_cli, "core", V, short, sha256=row["pack_sha256"],
                  total_bytes=row["pack_bytes"], parts=row["pack_parts"],
                  part_bytes=row["pack_part_bytes"])
    ok("a download that stops short is refused", False)
except pack.PackCorrupt as e:
    ok("a download that stops short is refused, and the part is kept so Join carries on",
       os.path.exists(short + ".part") and "carries on" in str(e), str(e))
ok("...and it did not land at the real path", not os.path.exists(short))
fresh_cli.objects[last] = keep_last

try:
    pack.pack_facts(Fake(), "core", 9)
    ok("a pack whose sidecar has not landed yet is 'still uploading', not an error", False)
except pack.PackIncomplete as e:
    ok("a pack whose sidecar has not landed yet is 'still uploading', not an error",
       "not finished uploading" in str(e), str(e))


# ==========================================================================================
print("\ninstalling: a downloaded zip is untrusted input")

fresh = os.path.join(tmpdir("fresh"), "knowledge")
put = pack.install(d1["path"], kroot=fresh)
ok("every file in the core landed", put["files"] == len(pack.members(K, "core")), put)
ok("the catalogue is there", os.path.exists(os.path.join(fresh, "site_index.json")))
ok("the brand pack is there", os.path.exists(os.path.join(fresh, "brand", "writer-brief.md")))
ok("the meaning index is NOT there — it is the other half", not pack.index_ready(fresh))
pack.install(di["path"], kroot=fresh)
ok("installing the index half puts it there",
   os.path.exists(os.path.join(fresh, "content-index", "body", "parts", "part_00000.npy")))
ok("...and index_ready() now says so", pack.index_ready(fresh))
ok("the staging folder is cleaned up", not os.path.exists(os.path.join(fresh, ".pack-incoming")))
ok("installing does not invent files the pack never had",
   not os.path.exists(os.path.join(fresh, "brand", "_work")))

keep = os.path.join(fresh, "brand", "_work", "mine")
os.makedirs(os.path.dirname(keep), exist_ok=True)
open(keep, "w").write("my own scratch")
pack.install(d1["path"], kroot=fresh)
ok("installing over an existing folder replaces what the pack carries and leaves the rest "
   "alone — brand/ also holds a person's own typing", open(keep).read() == "my own scratch")

order = pack._install_order(["content-index/title/vectors.npy", "content-index/body/x.npy",
                            "content-index/title/meta.jsonl", "content-index/index.json"])
ok("the two files _index.status() gates on are installed LAST, so a half-installed index "
   "reads as 'no index' instead of as a broken one",
   order[-2:] == ["content-index/title/meta.jsonl", "content-index/title/vectors.npy"], order)

torn_root = os.path.join(tmpdir("torn-install"), "knowledge")
real_replace = os.replace
STOP = [0]
def flaky(a, b):
    STOP[0] += 1
    if STOP[0] > 4 and "content-index" in str(b):
        raise OSError("the disk filled up half way through the index")
    return real_replace(a, b)
try:
    os.replace = flaky
    try:
        pack.install(di["path"], kroot=torn_root)
    except OSError:
        pass
finally:
    os.replace = real_replace
ok("an install that dies half way leaves an index that reads as NOT BUILT, so links_pass "
   "falls back to titles instead of loading vectors that are not there",
   not pack.index_ready(torn_root), os.listdir(torn_root))

for evil in ("../../etc/passwd", "/etc/passwd", "site_index.json/../../out", "elsewhere/x"):
    try:
        pack._safe_arc(evil)
        ok("a zip entry pointing outside the pack is refused: %s" % evil, False)
    except pack.PackCorrupt:
        ok("a zip entry pointing outside the pack is refused: %s" % evil, True)
ok("manifest.json is not extracted into the knowledge base",
   pack._safe_arc(pack.MANIFEST_NAME) is None)

torn = os.path.join(tmpdir("torn"), "torn.zip")
open(torn, "wb").write(open(d1["path"], "rb").read()[: len(whole) // 3])
try:
    pack.install(torn, kroot=os.path.join(tmpdir("t2"), "knowledge"))
    ok("a torn zip cannot be installed", False)
except pack.PackCorrupt:
    ok("a torn zip cannot be installed", True)


# ==========================================================================================
print("\nthe ruling: every refresh rebuilds, and the ONE guard is the five-minute coalesce")

class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


ok("the window is a named constant with the reason on it, and it is five minutes",
   pack.REBUILD_WINDOW_S == 300)
src = open(pack.__file__).read()
i = src.index("REBUILD_WINDOW_S = 300")
ok("...and the comment above it says why it exists",
   "catch-up" in src[i - 1200:i] and "coalesce" in src[i - 1200:i].lower())
ok("and the file says out loud that the split is not permission to defer either half",
   "not permission to defer" in src)

clock = Clock()
rb = pack.Rebuilder(Fake(), kroot=K, window=300, clock=clock, spawn=lambda fn: fn())
ok("the first refresh rebuilds straight away", rb.request("first") == "started")
ok("...and it really did upload a pack", rb.builds == 1 and rb.last_result["version"] == 1)

clock.t += 30
ok("a second refresh 30 seconds later does not rebuild a second time",
   rb.request("second") == "coalesced")
clock.t += 60
ok("nor a third", rb.request("third") == "coalesced")
clock.t += 60
ok("nor a fourth, fifth or sixth", [rb.request("n") for _ in range(3)] == ["coalesced"] * 3)
ok("six refreshes inside five minutes uploaded the pack ONCE, not six times", rb.builds == 1)
ok("...and a rebuild is still owed — the last change is not dropped, only deferred", rb.pending)

rb.cancel()
clock.t += 300
ok("once the window has passed a refresh rebuilds again, not never",
   rb.request("later") == "started")
ok("that is the second build of the session, and it carries everything since the first",
   rb.builds == 2 and rb.last_result["version"] == 2)

rb2 = pack.Rebuilder(Fake(), kroot=K, window=0.15, clock=time.time)
rb2.request("one")
rb2.request("two")
rb2.request("three")
ok("with a real timer and a real background thread the trailing rebuild does fire",
   rb2.wait(timeout=20) and rb2.builds == 2, rb2.builds)
ok("...and the second one superseded the others rather than queueing three",
   rb2.last_result["version"] == 2, rb2.last_result and rb2.last_result["version"])

t0 = time.time()
rb3 = pack.Rebuilder(Fake(), kroot=K, window=300)
ok("request() returns immediately — the owner was promised he never waits for the pack",
   rb3.request("go") == "started" and (time.time() - t0) < 0.25, "%.3fs" % (time.time() - t0))
rb3.wait(timeout=30)
rb3.cancel()

quiet = []
rb4 = pack.Rebuilder(Fake(), kroot=K, window=300, progress=lambda *a: quiet.append(a),
                     spawn=lambda fn: fn())
rb4.request("go")
ok("it reports as a quiet line, with a start and a finished size",
   quiet[0][0] == "start" and quiet[-1][0] == "done" and "MB" in quiet[-1][3], quiet[-1:])

broke = Fake(buckets=())
noise = []
rb5 = pack.Rebuilder(broke, kroot=K, window=300, progress=lambda *a: noise.append(a),
                     spawn=lambda fn: fn())
rb5.request("go")
ok("a background rebuild that fails does not raise into the click that started it",
   rb5.last_error and noise[-1][0] == "error")
ok("...and the reason survives, in words", "bucket" in rb5.last_error.lower() or
   "file store" in rb5.last_error.lower(), rb5.last_error)


# ==========================================================================================
print("\nend to end: a teammate is working after the CORE, and the index lands behind them")

live = Fake()
shared = pack.publish(live, kroot=K, last_seen_id=4)
mate = os.path.join(tmpdir("mate"), "knowledge")

joined = pack.join(live, kroot=mate, index="skip")
ok("join() comes back once the core is in — that is everything needed to pick an idea and "
   "write one", joined["ready"] is True and joined["version"] == shared["version"])
ok("the teammate's page count matches the manifest", joined["pages"] == 6, joined["pages"])
ok("the teammate replays from the boundary the creator wrote", joined["replay_from"] == 4)
ok("the meaning index is not there yet, and join() says so rather than implying it is",
   joined["index_ready"] is False and not pack.index_ready(mate))

# The real thing every index reader asks. Not a stand-in for it.
store.set_data_dir(os.path.dirname(mate))
try:
    from seo_agent.tools import _index
    st = _index.status()
    ok("tools/_index.status() — the exact test links_pass, ownpage and assets/reuse gate on — "
       "says the index is not built, so all three take their existing no-index path instead "
       "of loading vectors that are not there",
       st["built"] is False, st)
    ok("...and it did not raise on a knowledge base that has no content-index folder at all",
       isinstance(st, dict))

    core_only = pack.build(os.path.join(tmpdir("core-only"), "c.zip"), kroot=mate,
                           version=shared["version"])
    ok("the teammate rebuilding the CORE from their own knowledge base gets the identical "
       "file — which is the whole promise: they have what he has",
       core_only["sha256"] == shared["sha256"],
       (core_only["sha256"][:12], shared["sha256"][:12]))

    idx_got = pack.fetch_index(live, kroot=mate)
    ok("fetch_index() brings the other half down whenever they get round to it",
       idx_got["installed"] is True and idx_got["version"] == shared["index_version"])
    ok("...and now the index is ready", pack.index_ready(mate))
    ok("...and _index.status() agrees, without anything else being told", _index.status()["built"])
    mine_idx = pack.build(os.path.join(tmpdir("idx-only"), "i.zip"), kroot=mate,
                          version=shared["index_version"], half="index")
    ok("the index they hold is byte-identical to the one he published",
       mine_idx["sha256"] == json.loads(
           live.objects[pack.sidecar_name("index", shared["index_version"])])["sha256"])
finally:
    store.set_data_dir(None)

bg = os.path.join(tmpdir("bg"), "knowledge")
seen_bg = []
jb = pack.join(live, kroot=bg, progress=lambda *a: seen_bg.append(a[0]))
ok("by default the index is fetched on a background thread and join() does not wait for it",
   jb["index_pending"] is True and "index_thread" in jb)
jb["index_thread"].join(timeout=30)
ok("...and it does arrive", pack.index_ready(bg))

sad = Fake()
pack.publish(sad, kroot=K, last_seen_id=0)
for k in [k for k in sad.objects if k.startswith("pack/index/")]:
    del sad.objects[k]
sadroot = os.path.join(tmpdir("sad"), "knowledge")
notes = []
js = pack.join(sad, kroot=sadroot, progress=lambda *a: notes.append(a))
js["index_thread"].join(timeout=30)
ok("an index that fails to download does NOT break the join — the teammate is already "
   "working and the worst case is that links match on titles",
   js["ready"] is True and os.path.exists(os.path.join(sadroot, "site_index.json")))
ok("...and the reason is reported as a quiet line, not raised into the app",
   any(n[0] == "index-error" for n in notes), [n[0] for n in notes])

empty = Fake()
try:
    pack.join(empty, kroot=os.path.join(tmpdir("nope"), "knowledge"))
    ok("joining a workspace with no pack yet says so plainly", False)
except pack.PackIncomplete as e:
    ok("joining a workspace with no pack yet says so plainly, and what to do",
       "not shared its knowledge pack yet" in str(e), str(e))


# ---- clean up -----------------------------------------------------------------------------
pack.PART_BYTES = REAL_PART
for d in TMP:
    shutil.rmtree(d, ignore_errors=True)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
