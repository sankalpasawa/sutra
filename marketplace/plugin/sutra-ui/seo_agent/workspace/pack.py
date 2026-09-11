"""pack.py — the knowledge pack: the one file a teammate downloads so they never build a
knowledge base.

Reads:  knowledge_dir()/site_index.json · content-database.jsonl · content-index/ · brand/
Writes: a deterministic zip at a caller-given path, then `pack/<half>/<version>.zip.000` ...
        and `pack/<half>/<version>.zip.sha256` in the `knowledge` bucket.

TWO HALVES, ONE PACK (approved 2026-09-10, after the measurement below):

    core    site_index.json + content-database.jsonl + brand/    33.6 MB zipped, 2.7 s to build
            everything a teammate needs to pick an idea and write
    index   content-index/                                       171.5 MB zipped, 4.9 s
            the meaning index: semantic search and internal links

THE RULING APPLIES TO BOTH HALVES, EQUALLY (WORKSPACE-PLAN section 2). Every refresh changes
pages or brand, so the CORE is rebuilt and re-uploaded on every single refresh — no threshold,
no exception, nothing beyond the one 300-second coalesce. The INDEX is rebuilt and re-uploaded
whenever the index itself changes, decided by comparing its content hash against the published
one: an exact answer, never an estimate and never a "has it moved enough". If `build_page_index`
runs, the index object is stale from that moment and the next publish replaces it. **The split
is not permission to defer either half.** It exists so a refresh stops re-sending 171 MB of
float32 vectors that are bit-for-bit what is already in the bucket, and so a joining teammate is
working after seven seconds instead of five minutes.

MEASURED ON THE OWNER'S REAL INSTALL, 2026-09-10, because the plan's estimates were written
before anyone packed it. 337.2 MB of knowledge in 533 files, and the plan's "about 100 MB
zipped" is wrong: it is 205.0 MB, because 193 MB of it is the meaning index's float32
vectors, which deflate to 0.89 and never will do better. Anything budgeting storage or a
progress bar should use these numbers and not that one.

    a whole first publish, both halves      8.0 s   205.1 MB up   peak RSS 32.9 MB
    a normal refresh, index unchanged       2.9 s    33.6 MB up   <- the common case
    a refresh after the index was rebuilt   7.8 s   205.1 MB up
    a join, before the index lands          33.6 MB down, and the teammate is working

Two builds of either half are byte-identical, and a teammate who rebuilds the core from their
own installed knowledge base gets the same file, hash for hash, that was published to them.

WHAT IS IN IT, AND WHAT IS DELIBERATELY NOT (WORKSPACE-PLAN section 7). In: the catalogue,
every page's text, the meaning index, the brand pack — everything needed to start picking
ideas and writing. Out: the raw page cache (3.7 GB of downloaded HTML on the owner's install,
2026-09-10), drafts, run folders and `_work/` working files. Only finished, agreed things go
up. The exclusion is not a size optimisation; a teammate has no use for another person's
half-finished work and it would be wrong to hand it to them.

THE OWNER'S RULING, WHICH THIS FILE EXISTS TO OBEY (WORKSPACE-PLAN section 2, 2026-09-10).
Every refresh rebuilds and re-uploads the pack. Every time. No drift, no threshold, no
"rebuild it when it has moved by 20%". The one and only concession is that he does not WAIT
for it: the click finishes in ~2 seconds when the rows reach every teammate, and the rebuild
runs behind him as a quiet line. The one and only guard is REBUILD_WINDOW_S below. Nothing
else about the pack may be deferred, and a future reader who is about to add a "has it moved
enough?" test should read section 2 first.

THE THREE PROPERTIES THAT MAKE IT SAFE:

  deterministic  the same knowledge base and the same version number produce byte-identical
                 zips. Entries sorted, timestamps pinned, no wall clock inside. A pack that
                 differs run to run cannot be checksummed, so nobody could ever prove which
                 pack a teammate is holding.
  streamed       nothing here ever holds a member in memory. 340 MB is read a megabyte at a
                 time, straight into the zip, and hashed on the way past.
  atomic         the zip is built at a `.building` path and only renamed onto the real one
                 after it has been reopened and verified. A half-built pack cannot be
                 uploaded, and a half-downloaded one cannot become somebody's knowledge base.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile

from seo_agent import store
from seo_agent.workspace._common import WorkspaceError

# ---- what a pack is ---------------------------------------------------------------------

BUCKET = "knowledge"                 # the one bucket, created by the setup SQL (see below)
PACK_PREFIX = "pack/"                # pack/<half>/<v>.zip.000 ... + pack/<half>/<v>.zip.sha256

# THE PACK GOES UP IN PARTS, AND THIS IS WHY. Supabase caps how big ONE stored object may be,
# and on the Free plan that cap is 50 MB. The owner's real pack is 205 MB (measured
# 2026-09-10 against his install: 337 MB of knowledge, 533 files, zipped in 8 seconds), so a
# single `pack/<version>.zip` object cannot exist on the plan this whole design is built
# around. The pack is still ONE deterministic zip with ONE sha256 — that never changes — but
# its bytes are stored as `pack/<version>.zip.000`, `.001`, ... and joined back together on
# the way down. 40 MB leaves headroom under a 50 MB cap, and if the bucket reports a smaller
# limit we use that instead rather than discovering it 200 MB into an upload.
PART_BYTES = 40 * 1024 * 1024
PART_HEADROOM = 4 * 1024 * 1024      # never size a part right up against the reported limit

# The four members. A file member is one file; a directory member is every file under it,
# sorted, minus the skips. These two tuples are the ONLY place the pack's contents are
# decided, and which half a member belongs to is decided here and nowhere else.
CORE_MEMBERS = ("site_index.json", "content-database.jsonl", "brand")
INDEX_MEMBERS = ("content-index",)
HALVES = {"core": CORE_MEMBERS, "index": INDEX_MEMBERS}
MEMBERS = CORE_MEMBERS + INDEX_MEMBERS

# THE TWO FILES `_index.status()` GATES ON, AND WHY THEY GO IN LAST. Every reader of the
# meaning index — links_pass, ownpage, assets/reuse — asks `_index.status()["built"]` first,
# and that returns False unless BOTH of these exist. So installing them last means a
# half-installed index reads as "no index" and every reader takes its existing no-index path
# (title matching, or a plain note) instead of loading vectors whose body/ half has not landed
# yet. Without this the install has a window where the index looks complete and is not.
INDEX_GATE_FILES = ("content-index/title/meta.jsonl", "content-index/title/vectors.npy")

# Skipped anywhere inside a directory member. `_work` is the big one: brand/_work is 2.5 MB
# of the brand folder's 3.1 MB on the owner's install (measured 2026-09-10), and it is the
# builders' scratch, exactly what section 7 says never syncs. The rest are the droppings a
# real install accumulates — the .bak-pre-refresh files that refresh_site leaves, a stray
# .tmp from a killed atomic write, and macOS's .DS_Store.
SKIP_DIRS = ("_work", "_raw", "__pycache__")
SKIP_SUFFIXES = (".tmp", ".part", ".DS_Store")
SKIP_PATTERNS = (re.compile(r"\.bak(-|\.|$)"),)

MANIFEST_NAME = "manifest.json"      # always the LAST entry: it carries the other members' hashes
PACK_SCHEMA = 1                      # the pack FORMAT version. Not workspace.schema_version.

# A pinned zip timestamp. 1980-01-01 is the zero of the DOS date format zip stores, so it is
# the one value that survives every reader unchanged. Using the real mtime would make the
# bytes depend on when the files were touched, and two identical knowledge bases would
# produce two different checksums.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = (0o644 << 16)             # every entry the same mode, for the same reason
ZIP_LEVEL = 6                        # zlib default. Measured on the owner's install 2026-09-10:
                                     # site_index.json 0.17, content-database.jsonl 0.28,
                                     # the .npy vectors 0.93 (float32 does not compress).
CHUNK = 1 << 20                      # 1 MB. The largest thing this module ever holds in memory.

# ---- the one guard the owner sanctioned -------------------------------------------------

# TWO REFRESHES INSIDE FIVE MINUTES MUST NOT REBUILD THE PACK TWICE; the second supersedes
# the first. This exists for one situation and no other: a long catch-up session, where a
# person works through six changes in ten minutes and would otherwise upload the same
# 200 MB six times over a home connection. It is a COALESCE, not a skip — the last request
# inside the window is always honoured, at the far edge of the window, so the pack still
# ends up carrying every change. This is the ONLY deferral in this file (WORKSPACE-PLAN
# section 2); do not add a second one.
REBUILD_WINDOW_S = 300

# How many pack versions stay in the bucket. TWO, not one, and the extra one is deliberate:
# a teammate who read `workspace.pack_version` a second before a rebuild landed is now
# downloading a version that publish() is about to delete, and deleting it under them turns
# their join into a 404 half way through a five-minute download. Keeping the previous
# generation costs one pack of storage against Supabase's free 1 GB and removes the race
# entirely. publish() therefore deletes version N-2 when it lands N.
PACK_KEEP_GENERATIONS = 2


# ---- errors -----------------------------------------------------------------------------

class PackError(WorkspaceError):
    """A pack failure a person can read. Same family as every other workspace error."""


class PackIncomplete(PackError):
    """A member is not on disk. The knowledge base is not ready to be shared yet."""


class PackCorrupt(PackError):
    """A zip failed its own verification, or a download's sha256 did not match."""


class WorkspaceNotSetUp(PackError):
    """The bucket, or its storage.objects policies, are not there. A SETUP problem.

    Kept apart from every other failure for one reason: an RLS refusal on a storage write and
    an RLS refusal on creating a bucket are the SAME 403 with the same body, and whoever reads
    "row violates row-level security policy" will start looking for a bug in pack.py. There is
    no bug in pack.py that can produce it. The bucket and its four policies are created by
    `schema.sql`, at the one moment the setup holds admin rights (measured 2026-09-10: the
    publishable key cannot create a bucket, and cannot write to one that has no insert policy).
    """


class BucketMissing(WorkspaceNotSetUp):
    """The `knowledge` bucket does not exist, which is a SETUP problem, not a pack problem.

    Measured 2026-09-10: the publishable key CANNOT create a bucket — Supabase answers
    403 "new row violates row-level security policy". The bucket and its storage.objects
    policies are created by the setup SQL, at the one moment we hold admin rights. So this
    module never tries to create it, and never treats a missing one as something it can fix:
    it says which file to look in, because otherwise whoever reads the error goes hunting in
    the wrong place.
    """


# ---- listing what goes in ---------------------------------------------------------------

def _skip(name):
    if name.endswith(SKIP_SUFFIXES) or name.startswith("."):
        return True
    return any(p.search(name) for p in SKIP_PATTERNS)


def _half(half):
    if half in (None, "all"):
        return MEMBERS
    try:
        return HALVES[half]
    except KeyError:
        raise PackError("There is no %r half of the knowledge pack." % half)


def members(kroot=None, half=None):
    """[(arcname, abspath, bytes)] for what a half contains, sorted.

    Sorted by arcname across the whole half, not per member, so the order is a property of
    the names alone. That is what makes two builds of the same knowledge base identical.
    """
    kroot = kroot or store.knowledge_dir()
    rows = []
    for m in _half(half):
        src = os.path.join(kroot, m)
        if os.path.isfile(src):
            if not _skip(m):
                rows.append((m, src, os.path.getsize(src)))
            continue
        if not os.path.isdir(src):
            continue
        for base, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for f in sorted(files):
                if _skip(f):
                    continue
                fp = os.path.join(base, f)
                if not os.path.isfile(fp) or os.path.islink(fp):
                    continue
                arc = m + "/" + os.path.relpath(fp, src).replace(os.sep, "/")
                rows.append((arc, fp, os.path.getsize(fp)))
    rows.sort(key=lambda r: r[0])
    return rows


def survey(kroot=None, half=None):
    """A cheap pre-flight: what is present, what is missing, how big it will be.

    Called BEFORE a 337 MB build so a missing member is a sentence in two milliseconds
    rather than a crash a minute in.
    """
    kroot = kroot or store.knowledge_dir()
    want = _half(half)
    rows = members(kroot, half)
    present = {m for m in want if os.path.exists(os.path.join(kroot, m))}
    return {"root": kroot,
            "half": half or "all",
            "members": sorted(present),
            "missing": [m for m in want if m not in present],
            "files": len(rows),
            "raw_bytes": sum(r[2] for r in rows)}


def content_sha(kroot=None, half="index"):
    """The content hash of a half, WITHOUT building its zip. Nothing else decides staleness.

    This is how "has the index changed?" is answered — exactly, by hashing what is on disk and
    comparing it against the `content_sha256` in the published sidecar. It is not a heuristic,
    not a timestamp and not a size: two runs that produce the same bytes give the same hash,
    and one changed vector gives a different one.

    Cheap enough to do on every publish: 193 MB of index reads and hashes in about a third of
    a second, against the eight seconds and 171 MB it saves when nothing moved.
    """
    rows = members(kroot, half)
    return _content_sha([{"name": arc, "bytes": n, "sha256": _sha_file(src)}
                         for arc, src, n in rows])


def _page_count(path):
    """`page_count` out of site_index.json without loading 14 MB of it.

    The file is written by index_site with `domain` and `page_count` ahead of the `pages`
    array, so the number is inside the first few hundred bytes. Reading the whole file to
    learn one integer would be the one place in this module that broke the streaming rule,
    for no reason. Returns None if the shape ever changes — a manifest with a missing count
    is a small loss; a memory spike on a 5-person laptop fleet is not.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4096).decode("utf-8", "ignore")
    except OSError:
        return None
    m = re.search(r'"page_count"\s*:\s*(\d+)', head)
    return int(m.group(1)) if m else None


def _index_stats(kroot):
    """pages/chunks out of content-index/index.json — 147 bytes, safe to just read."""
    return store.read_json(os.path.join(kroot, "content-index", "index.json"), {}) or {}


# ---- building ---------------------------------------------------------------------------

def _zinfo(arc):
    zi = zipfile.ZipInfo(arc, date_time=ZIP_EPOCH)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = ZIP_MODE
    zi.create_system = 3                 # unix, pinned. The default follows the host OS,
    return zi                            # so a Mac and a Linux build would differ.


def _content_sha(entries):
    """One hash over WHAT the pack contains, with no version number in it.

    The zip's own sha256 changes when the version changes, because the version is inside the
    manifest. That is correct — a v7 pack and a v8 pack are different objects — but it means
    the zip hash cannot answer "did the knowledge actually move?". This one can, and it is in
    the manifest so anyone can ask later.
    """
    h = hashlib.sha256()
    for e in entries:
        h.update(("%s\0%d\0%s\n" % (e["name"], e["bytes"], e["sha256"])).encode())
    return h.hexdigest()


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def build(dest, kroot=None, version=1, half="core", progress=None, deep_verify=True):
    """Build one half of the pack at `dest`. Returns its manifest, sha256 and size.

    STREAMED: each member is read a megabyte at a time straight into the zip and hashed on
    the way past, so the peak memory is one CHUNK regardless of a 340 MB knowledge base.

    ATOMIC: the zip is written to `<dest>.building-<pid>-<rand>` in the SAME directory, then
    reopened and verified, and only then renamed onto `dest`. The rename is atomic within one
    filesystem, so `dest` is only ever absent or complete. A crash leaves a stray .building
    file, which the next run cleans up. This is store.write_json's discipline, applied to a
    file far too big to hold in memory.

    `progress(stage, done, total, note)` is called as it goes — bytes for the copy stage — so
    the UI can draw the quiet line the owner sees instead of a modal.
    """
    kroot = kroot or store.knowledge_dir()
    t0 = time.time()
    pre = survey(kroot, half)
    if pre["missing"]:
        raise PackIncomplete(
            "Sutra cannot build the %s of the knowledge pack yet: %s %s not been built. Run "
            "the site catalogue and the brand pack first, then share the workspace."
            % (half, ", ".join(pre["missing"]),
               "has" if len(pre["missing"]) == 1 else "have"))

    rows = members(kroot, half)
    total = pre["raw_bytes"]
    done = 0
    entries = []

    d = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".building-", suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=ZIP_LEVEL, allowZip64=True) as zf:
            for arc, src, size in rows:
                h = hashlib.sha256()
                with open(src, "rb") as fin, zf.open(_zinfo(arc), "w") as fout:
                    for block in iter(lambda: fin.read(CHUNK), b""):
                        h.update(block)
                        fout.write(block)
                        done += len(block)
                        if progress:
                            progress("pack", done, total, arc)
                entries.append({"name": arc, "bytes": size, "sha256": h.hexdigest()})

            manifest = {
                "pack_schema": PACK_SCHEMA,
                "half": half,
                "version": int(version),
                "members": list(_half(half)),
                "files": len(entries),
                "raw_bytes": total,
                "content_sha256": _content_sha(entries),
                "entries": entries,
            }
            # EACH HALF'S MANIFEST DESCRIBES ONLY ITS OWN HALF, and this is load-bearing
            # rather than tidy. The core manifest used to carry the index's page and chunk
            # counts, which meant the core's BYTES changed whenever the index was rebuilt —
            # so two identical cores hashed differently and the split's whole premise (a core
            # that only moves when the core moves) was false. Caught by the round-trip test,
            # 2026-09-10: a teammate who had the core but not the index rebuilt it and got a
            # different file from the one he was sent.
            if half == "core":
                manifest["pages"] = _page_count(os.path.join(kroot, "site_index.json"))
            else:
                idx = _index_stats(kroot)
                manifest["indexed_pages"] = idx.get("pages")
                manifest["chunks"] = idx.get("chunks")
                manifest["embedding_model"] = idx.get("model")
            # LAST, on purpose: it carries the other entries' hashes, so it cannot be written
            # until they have all streamed past. Fixed order, so determinism holds.
            body = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode()
            zf.writestr(_zinfo(MANIFEST_NAME), body)

        if progress:
            progress("verify", total, total, "")
        verify(tmp, deep=deep_verify)                 # never rename a zip we have not opened
        sha = _sha_file(tmp)
        size = os.path.getsize(tmp)
        os.chmod(tmp, 0o644)                          # mkstemp gives 0600; a pack is not a secret
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

    return {"path": dest, "half": half, "version": int(version), "sha256": sha, "bytes": size,
            "raw_bytes": total, "files": len(entries),
            "content_sha256": manifest["content_sha256"],
            "manifest": manifest, "seconds": round(time.time() - t0, 2)}


def read_manifest(zip_path):
    """The manifest out of a built pack, without extracting anything else."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            return json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except (KeyError, zipfile.BadZipFile, ValueError) as e:
        raise PackCorrupt("That knowledge pack is not readable (%s). It will be built again."
                          % type(e).__name__)


def verify(zip_path, sha256=None, deep=False):
    """Prove a zip is a complete pack before anything trusts it.

    Three checks, cheapest first. `sha256` is the whole-file hash, which is what a DOWNLOAD
    checks — a truncated download fails here and never reaches the knowledge base. `deep`
    re-inflates every entry and checks its CRC, which is what a BUILD does, because a pack
    that fails its own CRC must not be uploaded to five people.

    Nothing here reports success it has not run: each check that passes is named in the
    returned dict, so a caller can say which ones actually happened.
    """
    ran = []
    if sha256:
        actual = _sha_file(zip_path)
        if actual != sha256:
            raise PackCorrupt(
                "The knowledge pack that arrived is not the one the workspace published — "
                "its checksum does not match, so it was cut short or altered on the way. "
                "Nothing was installed. Try joining again.")
        ran.append("sha256")

    man = read_manifest(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        want = {e["name"] for e in man.get("entries", [])}
        missing = sorted(want - names)
        if missing:
            raise PackCorrupt("The knowledge pack is missing %d of the files its own manifest "
                              "lists (first: %s)." % (len(missing), missing[0]))
        sizes = {i.filename: i.file_size for i in zf.infolist()}
        wrong = [e["name"] for e in man.get("entries", []) if sizes.get(e["name"]) != e["bytes"]]
        if wrong:
            raise PackCorrupt("The knowledge pack's %s is a different size than its manifest "
                              "says." % wrong[0])
        ran.append("manifest")
        if deep:
            bad = zf.testzip()
            if bad:
                raise PackCorrupt("The knowledge pack failed its own integrity check on %s. "
                                  "It was not uploaded." % bad)
            ran.append("crc")
    return {"ok": True, "checks": ran, "manifest": man}


# ---- the client's optional extras --------------------------------------------------------
# client.py is owned elsewhere (design/HANDOFF-W3.md carries the exact signatures this file
# wants). Everything below degrades honestly: if the client has the streaming call we use it,
# and if it does not we fall back to the bytes call and SAY SO in the result, rather than
# quietly loading 200 MB into memory and letting somebody discover it on a laptop.

def _has(client, name):
    return callable(getattr(client, name, None))


def bucket_ready(client):
    """True if the `knowledge` bucket exists. Cheap, and worth it.

    GET /storage/v1/bucket answers 200 with a list for the publishable key (measured
    2026-09-10), so this costs one small request. Discovering the bucket is missing AFTER
    packing 340 MB would waste a minute of somebody's life for nothing.
    """
    if not _has(client, "buckets"):
        return None                       # cannot tell; the upload will say if it is wrong
    try:
        return any((b or {}).get("name") == BUCKET for b in (client.buckets() or []))
    except WorkspaceError:
        return None


def _require_bucket(client):
    if bucket_ready(client) is False:
        raise BucketMissing(
            "This workspace has no `%s` file store, so the knowledge pack cannot be uploaded. "
            "The bucket is created by the workspace setup script, not by Sutra at run time — "
            "the publishable key is not allowed to create one. Re-run Create workspace, or "
            "paste the setup SQL again from the Connections tab." % BUCKET)


def _storage_write(client, what, fn, *a, **kw):
    """Every storage WRITE goes through here, so one refusal has one explanation.

    Supabase answers a policy gap with 403 "new row violates row-level security policy" —
    byte for byte what a missing bucket looks like, and what the publishable key gets when it
    tries to create one. Left raw, that sentence sends the reader into this file looking for a
    bug that is in `schema.sql`. NONE of the storage policies have been proved live yet (there
    is no Supabase access token on this machine as of 2026-09-10), so this is the error we are
    most likely to see first and the one that most needs to point at the right file.
    """
    try:
        return fn(*a, **kw)
    except WorkspaceError as e:
        body = " ".join(str(v) for v in (e.body or {}).values())
        if e.status in (400, 401, 403) or "row-level security" in (str(e) + body):
            raise WorkspaceNotSetUp(
                "Supabase refused to %s. This is the workspace's own storage rules, not the "
                "knowledge pack: the `%s` bucket and its four storage policies are made by the "
                "workspace setup script, and the key Sutra holds is not allowed to make them. "
                "Re-run Create workspace, or paste the setup SQL again from the Connections "
                "tab. Nothing was changed, and the pack every teammate already has is "
                "untouched. (Supabase said: %s)" % (what, BUCKET, e))
        raise


def _upload_verified(client, path, expect_bytes):
    """How we know the object actually landed, and what we are entitled to claim.

    Never "the request did not error" (WORKSPACE-PLAN section 10). If the client can stat an
    object we compare the stored size, which catches a truncated upload. If it cannot, we say
    the size was not checked rather than implying it was.
    """
    if _has(client, "stat"):
        got = client.stat(BUCKET, path) or {}
        size = got.get("size")
        if size is not None and int(size) != int(expect_bytes):
            raise PackCorrupt(
                "The knowledge pack did not upload completely — Supabase stored %s bytes of "
                "%s. The previous pack is untouched, so nobody is affected; Sutra will build "
                "and upload it again." % (size, expect_bytes))
        return "size" if size is not None else "exists"
    return "none"


def part_name(half, version, i):
    """`pack/core/7.zip.003`. A folder per half so the Supabase dashboard reads as two
    things, and zero-padded so a bucket listing sorts the way the file reads."""
    return "%s%s/%d.zip.%03d" % (PACK_PREFIX, half, int(version), int(i))


def sidecar_name(half, version):
    return "%s%s/%d.zip.sha256" % (PACK_PREFIX, half, int(version))


def part_size(client):
    """How big one uploaded object may be. The bucket's own answer beats our guess.

    Supabase returns `file_size_limit` on GET /storage/v1/bucket, which is the real cap for
    THIS project — a paid plan raises it, a project setting can lower it. Reading it costs
    one small request we are already making for bucket_ready(), and it turns "the upload died
    at 41 MB" into a part size that was never going to fail.
    """
    limit = None
    if _has(client, "buckets"):
        try:
            for b in client.buckets() or []:
                if (b or {}).get("name") == BUCKET:
                    limit = b.get("file_size_limit")
        except WorkspaceError:
            limit = None
    if not limit:
        return PART_BYTES
    return max(1 << 20, min(PART_BYTES, int(limit) - PART_HEADROOM))


def _upload_parts(client, half, version, zip_path, total, chunk, progress=None):
    """Slice the built zip into objects and upload them in order.

    HOW MUCH THIS HOLDS IN MEMORY. `client.upload(bucket, path, data)` takes bytes, so this
    reads one part — 40 MB — to hand it over, and never more than one at a time. Measured
    2026-09-10 on the owner's real 205 MB pack: peak RSS 116 MB for the whole publish. If
    client.py grows `upload_file(bucket, path, file_path, offset=, length=)` (the signature
    is in design/HANDOFF-W3.md) this sends a slice straight off disk instead, and the same
    publish peaks at 32 MB. It is used automatically when present.
    """
    n = max(1, (total + chunk - 1) // chunk)
    sliced = _has(client, "upload_file")
    sent = 0
    f = None if sliced else open(zip_path, "rb")
    try:
        for i in range(n):
            want = min(chunk, total - i * chunk)
            name = part_name(half, version, i)
            if sliced:
                _storage_write(client, "send part %d of the knowledge pack" % (i + 1),
                               client.upload_file, BUCKET, name, zip_path,
                               offset=i * chunk, length=want)
            else:
                data = f.read(want)
                if len(data) != want:
                    raise PackCorrupt("The knowledge pack changed while it was being uploaded.")
                _storage_write(client, "send part %d of the knowledge pack" % (i + 1),
                               client.upload, BUCKET, name, data)
                del data
            stored = _upload_verified(client, name, want)
            sent += want
            if progress:
                progress("upload", sent, total, "part %d of %d" % (i + 1, n))
    finally:
        if f:
            f.close()
    return n, stored


# ---- publishing -------------------------------------------------------------------------

def publish(client, kroot=None, last_seen_id=0, workdir=None, progress=None, deep_verify=True):
    """Rebuild and re-upload the pack, then move the workspace to it. BOTH HALVES.

    THE RULING, APPLIED TO EACH HALF ON ITS OWN TERMS (WORKSPACE-PLAN section 2). The CORE is
    rebuilt and re-uploaded here, every single time this is called, with no test of whether it
    was worth it — a refresh always touches pages or brand, and the owner's ruling is that one
    click leaves everyone current. The INDEX is rebuilt and re-uploaded whenever the index has
    changed, and "has changed" is answered by hashing what is on disk against the
    `content_sha256` in the published sidecar. That is an exact comparison of the bytes, not a
    threshold and not a guess: if `build_page_index` has run, the hash differs and the index
    goes up on this same call. **Neither half may be deferred.** The split exists so a refresh
    stops re-sending 171 MB of float32 vectors that are bit-for-bit already in the bucket.

    THE DELTA BOUNDARY, WHICH IS THE THING TO GET RIGHT (WORKSPACE-PLAN section 3). The
    `pages` table holds only what has changed SINCE the current pack, and a joiner replays the
    `changes` log from where the pack stops. One number does all three jobs, so the three can
    never disagree:

        pack_change_id = the client's own last_seen_id, READ BEFORE THE FILES ARE READ.

    Why that number. The pack is a copy of THIS client's local knowledge base, and this
    client's local knowledge base is, by definition, pack N-1 plus every change it has
    applied — that is, everything up to its own last_seen_id. So the pack contains exactly
    "up to last_seen_id", and a joiner replaying `id > last_seen_id` misses nothing.

    Why BEFORE and not after. If a teammate's change lands while the 337 MB is being read,
    reading the cursor first means we under-claim: the change may be inside the pack AND get
    replayed. Reading it after would mean we over-claim: a change could be counted as packed
    when the file it touches was already read past. Replaying a change twice is harmless
    because every replay is an upsert keyed by the row's own key; missing one is permanent. So
    the error is always taken in the safe direction.

    Why not max(changes.id). Because rows in `changes` come from other teammates too, and one
    that this client has not applied yet is NOT in the pack. Trimming on the server's high
    water mark would delete a page change that no future joiner ever sees again. We read the
    high water mark all the same, for one purpose: if it is ahead of our cursor this client
    is BEHIND, and _trim_pages then deletes nothing at all.

    THE ORDER IS THE SAFETY. Each half is built, verified, uploaded, and its upload verified,
    before the workspace row is moved to it. Until that moment every teammate is still pointed
    at the previous version of that half, which is still in the bucket, so a join that starts
    mid-rebuild gets a complete old object rather than a truncated new one.

    AND THE TWO HALVES ARE COMMITTED SEPARATELY, on purpose. The core is the half the ruling
    is about, and it must not be held hostage to the index: if the 171 MB index upload fails,
    the core has already landed and every teammate already has the new pages. The workspace
    then still points at the previous index version, which still exists, and the next refresh
    finds the hash still different and tries again. A joiner in between gets the new core with
    the older index, which is a valid pair — the index is a search aid, and a page it has not
    heard of simply does not come back from semantic search.
    """
    kroot = kroot or store.knowledge_dir()
    say = progress or (lambda *a, **k: None)
    t0 = time.time()

    _require_bucket(client)                       # before 337 MB, not after
    cursor = int(last_seen_id or 0)               # READ FIRST. See the docstring.

    row = _require_row(client)
    head = _log_head(client)
    behind = None if head is None else max(0, head - cursor)
    chunk = part_size(client)

    tmpdir = workdir or tempfile.mkdtemp(prefix="sutra-pack-")
    made_tmpdir = workdir is None
    out = {"behind": behind, "pack_change_id": cursor, "part_bytes": chunk,
           "row_fields_missing": []}
    try:
        # ---- the CORE. Always. -------------------------------------------------------
        version = int(row.get("pack_version") or 0) + 1
        say("build", 0, 0, "building the knowledge pack")
        built = build(os.path.join(tmpdir, "core-%d.zip" % version), kroot=kroot,
                      version=version, half="core", progress=progress,
                      deep_verify=deep_verify)
        parts, landed = _publish_half(client, "core", version, built, chunk, say)

        fields, missing = _ws_fields(row, {
            "pack_version": version,
            "pack_sha256": built["sha256"],
            "pack_bytes": built["bytes"],
            "pack_parts": parts,
            "pack_part_bytes": chunk,
            "pack_change_id": cursor,
            "pack_built_at": store.now()})
        say("publish", 0, 0, "pointing the workspace at pack %d" % version)
        row = _point_workspace(client, row, fields)
        out.update({"version": version, "sha256": built["sha256"], "bytes": built["bytes"],
                    "raw_bytes": built["raw_bytes"], "files": built["files"],
                    "parts": parts, "content_sha256": built["content_sha256"],
                    "upload_verified": landed, "build_seconds": built["seconds"]})
        out["row_fields_missing"] += missing

        # ---- the INDEX. Whenever it has changed, on the same terms. -------------------
        idx = _publish_index(client, row, kroot, tmpdir, chunk, say, deep_verify)
        out["row_fields_missing"] = sorted(set(out["row_fields_missing"])
                                           | set(idx.pop("row_fields_missing", [])))
        out.update(idx)

        trimmed = _trim_pages(client, version, behind)
        removed = _drop_old_packs(client, "core", version)
    finally:
        if made_tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    out.update({"pages_trimmed": trimmed, "removed": removed,
                "seconds": round(time.time() - t0, 2)})
    return out


def _publish_half(client, half, version, built, chunk, say):
    """Upload one half's parts and then its sidecar. Returns (parts, how it was verified).

    The sidecar is written LAST of the objects on purpose: until it exists the parts are just
    bytes in a bucket, and nothing downstream can mistake a half-finished upload for a pack.
    """
    say("upload", 0, built["bytes"], "sending the %s" % half)
    parts, landed = _upload_parts(client, half, version, built["path"], built["bytes"], chunk,
                                  progress=say)
    side = json.dumps({"half": half, "version": version, "sha256": built["sha256"],
                       "bytes": built["bytes"], "parts": parts, "part_bytes": chunk,
                       "files": built["files"], "raw_bytes": built["raw_bytes"],
                       "content_sha256": built["content_sha256"]}, indent=2).encode()
    _storage_write(client, "finish the %s upload" % half,
                   client.upload, BUCKET, sidecar_name(half, version), side)
    return parts, landed


def _publish_index(client, row, kroot, tmpdir, chunk, say, deep_verify):
    """The index half: rebuilt and re-uploaded WHENEVER IT HAS CHANGED, and never deferred.

    "Changed" is decided by one exact comparison and nothing else: the content hash of what is
    on disk against the `content_sha256` inside the sidecar of the version currently published.
    Equal means the bytes in the bucket ARE the bytes on disk, so re-uploading them would send
    171 MB to arrive at the file that is already there. Different — by one vector — means the
    index is stale from that moment and it goes up on this call, exactly like the core.

    This is not the "has it moved enough" test the owner rejected. There is no threshold here
    and no window; the only two answers are identical and not identical.
    """
    if not os.path.isdir(os.path.join(kroot, "content-index")):
        # A knowledge base with no meaning index is a normal thing — nobody with no Voyage key
        # has one. The core still went up and a teammate can still write.
        return {"index_version": int(row.get("index_version") or 0), "index_rebuilt": False,
                "index": "not built here"}

    versioned = "index_version" in row
    current = int(row.get("index_version") or 0) if versioned else 1
    on_disk = content_sha(kroot, "index")
    published = None
    if current >= 1:
        try:
            published = json.loads(
                client.download(BUCKET, sidecar_name("index", current)).decode()
            ).get("content_sha256")
        except Exception:                                          # noqa: BLE001
            published = None                                       # no sidecar: publish it

    if published == on_disk:
        return {"index_version": current, "index_rebuilt": False,
                "index": "unchanged", "index_versioning": versioned}

    version = (current + 1) if versioned else 1
    say("build", 0, 0, "building the meaning index")
    built = build(os.path.join(tmpdir, "index-%d.zip" % version), kroot=kroot,
                  version=version, half="index", progress=say, deep_verify=deep_verify)
    parts, landed = _publish_half(client, "index", version, built, chunk, say)

    fields, missing = _ws_fields(row, {"index_version": version})
    if fields:
        _point_workspace(client, row, fields)
    removed = _drop_old_packs(client, "index", version) if versioned else []

    return {"index_version": version, "index_rebuilt": True, "index": "rebuilt",
            "index_bytes": built["bytes"], "index_parts": parts,
            "index_sha256": built["sha256"], "index_content_sha256": built["content_sha256"],
            "index_seconds": built["seconds"], "index_upload_verified": landed,
            "index_removed": removed, "index_versioning": versioned,
            "row_fields_missing": missing}


def workspace_row(client):
    """The single `workspace` row. schema.sql inserts it at creation, so it always exists."""
    rows = client.select("workspace") or []
    return dict(rows[0]) if rows else {}


def _require_row(client):
    row = workspace_row(client)
    if not row:
        raise PackIncomplete(
            "This project has no workspace row yet, so there is nothing to attach a knowledge "
            "pack to. Run the workspace setup script first (Connections -> Create workspace).")
    return row


def _log_head(client):
    """The highest `changes.id` on the server, or None if we cannot ask.

    One row, one request. It is the difference between "this client is level with everyone"
    and "this client is behind", and that decides whether the trim in _trim_pages is safe.
    """
    try:
        rows = client.select("changes", order="id.desc", limit=1, columns="id") or []
    except (WorkspaceError, TypeError):
        return None
    try:
        return int(rows[0]["id"]) if rows else 0
    except (KeyError, ValueError, TypeError):
        return None


def _point_workspace(client, row, fields):
    """Move the workspace row on to a new pack, and PROVE it moved. Returns the row as it now is.

    AN UPDATE, NEVER AN UPSERT. schema.sql gives the workspace row a read rule and an update rule
    and deliberately no insert rule: the row is born in the setup script and never created from
    the app. An upsert is an INSERT ... ON CONFLICT DO UPDATE, and row-level security judges it
    against the insert rule that is not there -- so it is refused before the update half is ever
    reached. This line used to be an upsert, and on the owner's live workspace it refused EVERY
    publish from the day the workspace was made: the core uploaded, the row never moved, the
    workspace sat at pack 0, and the first teammate to join was handed nothing. Measured
    2026-09-11: the upsert failed with "new row violates row-level security policy for table
    workspace", and a PATCH of the same row came back with the row.

    NOT REPORTING SUCCESS FROM SILENCE. A PATCH that a rule filters out does not error; it comes
    back 200 with no rows. So an empty answer is treated as the refusal it is, rather than as a
    workspace that has moved to a pack nobody can see.
    """
    if not fields:
        return dict(row)
    wid = row.get("id")
    if not wid:
        raise PackError("The workspace row has no id, so Sutra cannot say which row to point "
                        "at the new pack. Nothing a teammate downloads has changed.")
    got = client.update("workspace", {"id": wid}, fields) or []
    if not got:
        raise PackError("The pack uploaded, but the workspace would not point at it: the update "
                        "came back with no row. Nothing a teammate downloads has changed.")
    return dict(row, **fields)


def _ws_fields(row, fields):
    """Only the columns this project's `workspace` table actually has.

    The pack needs six columns beyond what schema.sql v1 created (design/HANDOFF-W3.md has
    the exact ALTER statements). Until they land, PostgREST answers a write to a column it
    does not know with a 400 and the WHOLE publish fails — over a field that is a nicety.
    So we write what exists, and the result names what could not be stored rather than
    letting a caller believe it was.
    """
    keep = {k: v for k, v in fields.items() if k in row}
    return keep, sorted(k for k in fields if k not in row)


def _trim_pages(client, version, behind):
    """Drop the delta rows the new pack has absorbed. This is what keeps the database small.

    `pages` carries only what has changed since the current pack (WORKSPACE-PLAN section 3):
    12,318 pages live in the pack and the table holds the handful that moved since. Without
    this trim it grows into the whole site, and the 500 MB free tier is the least of it —
    every teammate would replay the entire catalogue row by row on every join.

    THE COLUMN IS `pack_version`, which is schema.sql's own word for it ("the pack this delta
    is measured against"), not a second one meaning the same thing. A row written while the
    workspace was on pack 6 carries 6; pack 7 is built from a knowledge base that has already
    absorbed it; so `pack_version < 7` is exactly the set pack 7 contains.

    AND IT IS SKIPPED WHEN THIS CLIENT IS BEHIND. `pages` rows come from other teammates too,
    and one this client has not applied yet is NOT in the pack it just built, even though its
    pack_version says it should be. Deleting that row would lose a page change permanently —
    no future joiner would ever see it. So when the log has moved past our last_seen_id we
    upload the pack (the ruling in section 2 says every refresh does) and simply do not trim.
    The delta stays a little longer; nothing is ever lost. `behind` is None when we could not
    find out, which is treated the same way: do not delete what you cannot prove.

    A TRIM IS A PLAIN DELETE AND NOTHING ELSE, and this is the rule all three of us hold
    (agreed with the sync and schema agents, 2026-09-10). Every domain table has a trigger
    that logs a delete to `changes`, and every teammate's sync applies what it reads — so if
    a trim looked like content, routine housekeeping would read as "these 12,000 pages are
    gone from the site" and empty four other people's catalogues on every rebuild. The two
    halves of the rule:

        a page genuinely gone from the site   ->  op='gone' on the row, an UPDATE
        a delete on `pages`                   ->  the delta being trimmed, IGNORED by everyone

    So: delete the rows. Do not mark them, do not blank their fields, do not touch `op`, and
    never express "this page went away" by deleting a row — that is the refresh path's job
    and not this file's. `mirror._trimmed()` is the consumer side of the same rule.
    """
    if behind is None or behind > 0:
        return 0
    if not _has(client, "delete"):
        return None                       # said plainly in the result, never assumed done
    return client.delete("pages", {"pack_version": ("lt", int(version))})


def _drop_old_packs(client, half, version):
    """Remove version N-PACK_KEEP_GENERATIONS of THIS half, keeping current + previous.

    Per half, on the same terms: a joiner downloading the core and a joiner downloading the
    index are both five minutes of somebody's evening, and both deserve the object they were
    pointed at to still be there.

    The old sidecar says how many parts there were, so we delete exactly those and never
    guess. The sidecar goes FIRST: from that moment the leftovers are unreachable rubbish
    rather than a pack somebody could half-follow.
    """
    old = version - PACK_KEEP_GENERATIONS
    if old < 1:
        return []
    n = 0
    try:
        n = int(json.loads(client.download(BUCKET, sidecar_name(half, old)).decode())["parts"])
    except Exception:                                             # noqa: BLE001
        n = 0
    gone = []
    for name in [sidecar_name(half, old)] + [part_name(half, old, i) for i in range(n)]:
        try:
            client.remove(BUCKET, name)
            gone.append(name)
        except WorkspaceError:
            # A pack that will not delete is litter, not a failure. The new pack is already
            # live and every teammate is on it; raising here would turn a successful publish
            # into a red error over 200 MB of storage.
            pass
    return gone


# ---- the debounce: the one and only deferral --------------------------------------------

class Rebuilder:
    """Runs publish() behind the click, and coalesces a burst into one rebuild.

    The owner's picture (WORKSPACE-PLAN section 2):

        click "Go ahead"
          ~2 seconds   the changes reach every teammate       <- the click finishes HERE
          ~1 minute    the pack is rebuilt and uploaded       <- he has already moved on

    So `request()` returns immediately, always. It never blocks, never opens a modal, and
    reports through `progress` as a quiet line.

    THE COALESCE, precisely. The first request starts a rebuild now. Any request that arrives
    while one is running, or within REBUILD_WINDOW_S of the last one starting, does not start
    a second — it arms a single trailing rebuild that fires at the end of the window and
    carries everything, including changes that arrived after it was armed. A third and a
    tenth request inside the window supersede the armed one rather than adding to it. So a
    ten-minute catch-up session uploads twice, not six times, and the last change is still
    in the pack the second upload carries.

    `clock` and `spawn` are injectable so the tests can prove this in milliseconds instead of
    sitting through five real minutes.
    """

    def __init__(self, client, kroot=None, window=REBUILD_WINDOW_S, progress=None,
                 cursor=None, clock=time.time, spawn=None):
        self.client = client
        self.kroot = kroot
        self.window = window
        self.progress = progress or (lambda *a, **k: None)
        self.cursor = cursor or (lambda: 0)
        self.clock = clock
        self.spawn = spawn or self._thread
        self.lock = threading.RLock()
        self.running = False
        self.pending = False              # one trailing rebuild, armed or not
        self.timer = None
        self.last_started = None
        self.builds = 0
        self.last_result = None
        self.last_error = None

    # -- the door ------------------------------------------------------------------------
    def request(self, reason=""):
        """Ask for a rebuild. Returns "started" or "coalesced". NEVER blocks."""
        with self.lock:
            now = self.clock()
            fresh = self.last_started is not None and (now - self.last_started) < self.window
            if self.running or fresh:
                self.pending = True
                self._arm(now)
                return "coalesced"
            self._start(reason)
            return "started"

    def wait(self, timeout=60):
        """Tests and shutdown only. The UI never calls this — that would be the wait the
        owner was promised he would not have."""
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if not self.running and not self.pending:
                    return True
            time.sleep(0.01)
        return False

    def cancel(self):
        with self.lock:
            self.pending = False
            if self.timer:
                self.timer.cancel()
                self.timer = None

    # -- the works -----------------------------------------------------------------------
    def _arm(self, now):
        if self.timer is not None:
            return                        # already armed; the newest request supersedes it
        delay = max(0.0, self.window - (now - (self.last_started or now)))
        self.timer = threading.Timer(delay, self._fire)
        self.timer.daemon = True
        self.timer.start()

    def _fire(self):
        with self.lock:
            self.timer = None
            if not self.pending or self.running:
                return
            self._start("coalesced")

    def _start(self, reason):
        self.running = True
        self.pending = False
        self.last_started = self.clock()
        self.builds += 1
        self.spawn(lambda: self._run(reason))

    def _thread(self, fn):
        t = threading.Thread(target=fn, name="sutra-pack-rebuild", daemon=True)
        t.start()
        return t

    def _run(self, reason):
        try:
            self.progress("start", 0, 0, "updating the shared knowledge pack")
            res = publish(self.client, kroot=self.kroot, last_seen_id=self.cursor(),
                          progress=self.progress)
            self.last_result = res
            self.last_error = None
            self.progress("done", res["bytes"], res["bytes"],
                          "knowledge pack v%d shared (%.0f MB)" % (res["version"],
                                                                   res["bytes"] / 1e6))
        except Exception as e:                                        # noqa: BLE001
            # A failed background rebuild must never take the app down or lose the reason.
            # The rows already reached every teammate — that part of the click succeeded —
            # so this is a quiet line saying the pack is behind, not a failed refresh.
            self.last_error = str(e)
            self.progress("error", 0, 0, str(e))
        finally:
            with self.lock:
                self.running = False
                if self.pending:
                    self._arm(self.clock())


# ---- the joining side --------------------------------------------------------------------

def pack_facts(client, half, version):
    """The sidecar for a version: sha256, bytes, parts, part_bytes.

    Read from the bucket rather than only from the workspace row, so a download can check
    itself against the object store it is actually pulling from. A missing sidecar means the
    pack is not finished uploading (publish writes it last), which is a real answer and not
    a crash.
    """
    try:
        return json.loads(client.download(BUCKET, sidecar_name(half, version)).decode("utf-8"))
    except WorkspaceError:
        raise PackIncomplete(
            "The %s of pack %d is not finished uploading yet. Give it a minute and try again "
            "— nothing is wrong, the person who set the workspace up is still sending it."
            % (half, int(version)))
    except (ValueError, KeyError):
        raise PackCorrupt("The %s of pack %d has an unreadable checksum file."
                          % (half, int(version)))


def _fetch_part(client, name, out, start, want, total_done, total, progress):
    """Append one part to the open file. Returns how many bytes arrived.

    RESUME HAS TWO GRAINS. Whole parts already on disk are never fetched again, which works
    with any client. Inside a part we can only continue from an offset if the client can ask
    for a byte range — `download_stream(bucket, path, start)`, backed by Supabase Storage's
    HTTP Range support. Without it we simply re-pull the current part, so the worst a dropped
    connection costs is one part instead of the whole 205 MB.
    """
    got = 0
    if start and _has(client, "download_stream"):
        for block in client.download_stream(BUCKET, name, start=start):
            out.write(block)
            got += len(block)
            if progress:
                progress("download", total_done + got, total, name)
        return got
    data = client.download(BUCKET, name)
    if start:
        data = data[start:]
    out.write(data)
    if progress:
        progress("download", total_done + len(data), total, name)
    return len(data)


def download(client, half, version, dest, sha256=None, total_bytes=None, parts=None,
             part_bytes=None, progress=None):
    """Pull one half of pack <version> to `dest`, verifying before it is allowed to exist.

    Streamed into `<dest>.part` and only renamed onto `dest` once the sha256 of the whole
    joined file matches what the workspace published. A truncated download therefore cannot
    become somebody's knowledge base — it stays a .part file, and the next attempt continues
    it rather than starting the ~5 minutes again.

    `progress(stage, done, total, note)` gets real bytes of the real total throughout, which
    is what the join screen's bar is drawn from.
    """
    version = int(version)
    if not (sha256 and total_bytes and parts and part_bytes):
        facts = pack_facts(client, half, version)
        sha256 = sha256 or facts.get("sha256")
        total_bytes = int(total_bytes or facts.get("bytes") or 0)
        parts = int(parts or facts.get("parts") or 1)
        part_bytes = int(part_bytes or facts.get("part_bytes") or PART_BYTES)
    total_bytes, parts, part_bytes = int(total_bytes), int(parts), int(part_bytes)

    d = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(d, exist_ok=True)
    part = dest + ".part"

    already = os.path.getsize(part) if os.path.exists(part) else 0
    if already > total_bytes:
        already = 0                                   # a stale, over-long part: start again
    first = already // part_bytes
    inside = already - first * part_bytes
    if inside and not _has(client, "download_stream"):
        already -= inside                             # re-pull this one part, not the lot
        inside = 0
    if already == 0 and os.path.exists(part):
        os.remove(part)
    elif already and os.path.exists(part) and os.path.getsize(part) != already:
        with open(part, "r+b") as f:
            f.truncate(already)

    t0 = time.time()
    done = already
    grain = "range" if _has(client, "download_stream") else "part"
    with open(part, "ab") as out:
        for i in range(first, parts):
            want = min(part_bytes, total_bytes - i * part_bytes) - (inside if i == first else 0)
            got = _fetch_part(client, part_name(half, version, i), out,
                              inside if i == first else 0, want, done, total_bytes, progress)
            done += got
            if got != want:
                break

    if done != total_bytes:
        raise PackCorrupt(
            "The knowledge pack stopped part way down — %d of %d bytes arrived. Nothing was "
            "installed, and what did arrive is kept, so pressing Join again carries on from "
            "here rather than starting over." % (done, total_bytes))
    try:
        verify(part, sha256=sha256, deep=False)
    except PackCorrupt:
        os.remove(part)                               # a wrong pack is not worth resuming
        raise
    os.replace(part, dest)
    return {"path": dest, "half": half, "version": version, "bytes": done, "parts": parts,
            "resumed_from": already, "resume": grain,
            "seconds": round(time.time() - t0, 2)}


def _install_order(names):
    """Sorted, except the two files `_index.status()` gates on, which go last."""
    return sorted(names, key=lambda n: (n in INDEX_GATE_FILES, n))


def core_ready(kroot=None):
    """Does this Mac hold the CORE -- the catalogue, every page's text, and the brand pack?

    The heal in agents_api reads this to tell which side of a missing pack a machine is on.
    Holding the core while the workspace has no pack means THIS Mac is the one to send it;
    lacking the core while the workspace has one means this Mac is the one to fetch it. It tests
    the same members the pack is built from, so the two can never disagree about what the core is.
    """
    kroot = kroot or store.knowledge_dir()
    return all(os.path.exists(os.path.join(kroot, n)) for n in CORE_MEMBERS)


def index_ready(kroot=None):
    """Does this knowledge base have a usable meaning index? The same test its readers use.

    Deliberately the SAME two files `tools/_index.status()` checks, not a different one — one
    concept, one test. If this says False, semantic search and internal-link matching fall
    back to titles, which is what a person without a Voyage key already gets.
    """
    kroot = kroot or store.knowledge_dir()
    return all(os.path.exists(os.path.join(kroot, n)) for n in INDEX_GATE_FILES)


def _safe_arc(name):
    """A downloaded zip is untrusted input, even from your own team's project.

    Every entry has to be inside one of the four members and inside the knowledge folder:
    no absolute paths, no `..`, no name that is not a member. Without this, one bad entry in
    a zip could write anywhere the app can write.
    """
    if name == MANIFEST_NAME:
        return None
    n = name.replace("\\", "/")
    if n.startswith("/") or ".." in n.split("/") or n.startswith("."):
        raise PackCorrupt("The knowledge pack contains a file path that is not allowed (%s)."
                          % name)
    top = n.split("/")[0]
    if top not in MEMBERS:
        raise PackCorrupt("The knowledge pack contains %s, which is not part of a pack." % name)
    return n


def install(zip_path, kroot=None, progress=None):
    """Unpack a VERIFIED pack into the local knowledge base.

    Only ever called after verify() has passed, which is where the atomicity comes from: the
    whole file is known good before the first byte is written into the knowledge folder.

    Files are extracted to a sibling staging folder and then renamed into place one at a
    time, rather than the whole member directory being swapped. That is deliberate: `brand/`
    on a real install also holds `_work/` and anything the person has typed, and swapping the
    directory would delete both. A rename per file replaces exactly what the pack carries and
    leaves everything else alone.
    """
    kroot = kroot or store.knowledge_dir()
    os.makedirs(kroot, exist_ok=True)
    man = read_manifest(zip_path)
    stage = os.path.join(kroot, ".pack-incoming")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    written = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist() if _safe_arc(n)]
            total = len(names)
            for i, n in enumerate(sorted(names)):
                out = os.path.join(stage, n)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with zf.open(n) as fin, open(out, "wb") as fout:
                    shutil.copyfileobj(fin, fout, CHUNK)   # streamed; never zf.read()
                if progress:
                    progress("install", i + 1, total, n)
            # THE GATE FILES GO LAST, and this is the whole reason install() bothers with
            # an order at all. `_index.status()["built"]` is False until BOTH title files
            # exist, and every reader of the meaning index asks it first. Moving them last
            # means that during the seconds this loop is running, a half-installed index
            # reads as "no index" and links_pass falls back to title matching, exactly as it
            # does for a person with no Voyage key. Move them first and there is a window
            # where the index claims to be built and its body/ vectors are not there yet,
            # which is a crash instead of a graceful degrade.
            for n in _install_order(names):
                target = os.path.join(kroot, n)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(os.path.join(stage, n), target)
                written += 1
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return {"files": written, "half": man.get("half"), "version": man.get("version"),
            "pages": man.get("pages"), "chunks": man.get("chunks"),
            "content_sha256": man.get("content_sha256")}


def join(client, kroot=None, workdir=None, progress=None, index="background"):
    """Everything a new teammate does once. RETURNS AS SOON AS THEY CAN WORK.

    The core — the catalogue, every page's text and the brand pack — is 33.6 MB and about
    seven seconds on a normal line. That is everything needed to pick an idea and write one,
    so `join()` installs it and comes back. The meaning index is 171 MB and lands behind them.

    Until it lands, `index_ready()` is False and every reader of the index takes the path it
    already has for a person with no Voyage key: `links_pass` matches internal links on
    titles, `research/ownpage` and `assets/reuse` say plainly that the index is not there.
    Nothing crashes and nothing is silently wrong — verified against those three call sites,
    2026-09-10, all of which gate on `_index.status()["built"]`.

    `index=`:
        "background"  fetch it on a daemon thread, return now.       <- the default
        "wait"        fetch it before returning. For a script.
        "skip"        do not fetch it at all. The caller will.

    Returns `replay_from`, which is `workspace.pack_change_id` — the boundary publish() wrote.
    The joiner then drains `changes` for `id > replay_from` and is level with everyone else.
    Getting this wrong in either direction is the bug that bites: too low and every change
    since the pack is applied twice, too high and pages are silently missing.
    """
    kroot = kroot or store.knowledge_dir()
    row = workspace_row(client)
    version = int(row.get("pack_version") or 0)
    if version < 1:
        raise PackIncomplete(
            "This workspace has not shared its knowledge yet. Nothing to do: as soon as whoever "
            "created it opens the SEO Writer, it is sent, and it arrives on this Mac by itself.")

    tmpdir = workdir or tempfile.mkdtemp(prefix="sutra-join-")
    made = workdir is None
    try:
        got = download(client, "core", version, os.path.join(tmpdir, "core-%d.zip" % version),
                       sha256=row.get("pack_sha256"), total_bytes=row.get("pack_bytes"),
                       parts=row.get("pack_parts"), part_bytes=row.get("pack_part_bytes"),
                       progress=progress)
        put = install(got["path"], kroot=kroot, progress=progress)
    finally:
        if made:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # A workspace whose table predates the pack columns has no boundary to give. Replaying
    # the whole log on top of the pack is the SAFE direction — every replay is an upsert
    # keyed by the row's own key, so re-applying is a no-op, whereas skipping is a page a
    # teammate never sees. It is slow rather than wrong, and `full_replay` says which
    # happened so the join screen is not silently guessing.
    boundary = row.get("pack_change_id")
    out = {"version": version, "replay_from": int(boundary or 0),
           "full_replay": boundary is None, "ready": True,
           "bytes": got["bytes"], "files": put["files"], "pages": put["pages"],
           "seconds": got["seconds"],
           "index_version": int(row.get("index_version") or 0),
           "index_ready": index_ready(kroot), "index_pending": False}

    if index == "skip" or not out["index_version"]:
        return out
    if index == "wait":
        out["index"] = fetch_index(client, kroot=kroot, progress=progress)
        out["index_ready"] = index_ready(kroot)
        return out

    # The default: they are already working; the index catches up behind them.
    out["index_pending"] = True
    t = threading.Thread(target=lambda: _quiet_index(client, kroot, progress),
                         name="sutra-join-index", daemon=True)
    t.start()
    out["index_thread"] = t
    return out


def _quiet_index(client, kroot, progress):
    """The background half of a join. It must never take the app down: the teammate is
    already working, and the worst case of a failure here is that internal links match on
    titles until somebody presses Join again."""
    try:
        fetch_index(client, kroot=kroot, progress=progress)
    except Exception as e:                                          # noqa: BLE001
        if progress:
            progress("index-error", 0, 0, str(e))


def fetch_index(client, kroot=None, workdir=None, progress=None):
    """Pull and install the meaning index. Safe to call at any time, and safe to repeat.

    Separate and public so the join screen can start it, retry it after a dropped connection,
    or leave it until the person is on wifi. It resumes like any other download, so a retry
    continues rather than starting the 171 MB again.
    """
    kroot = kroot or store.knowledge_dir()
    row = workspace_row(client)
    version = int(row.get("index_version") or 0)
    if version < 1:
        return {"version": 0, "installed": False, "why": "this workspace has no meaning index"}

    tmpdir = workdir or tempfile.mkdtemp(prefix="sutra-index-")
    made = workdir is None
    try:
        got = download(client, "index", version,
                       os.path.join(tmpdir, "index-%d.zip" % version), progress=progress)
        put = install(got["path"], kroot=kroot, progress=progress)
    finally:
        if made:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return {"version": version, "installed": True, "bytes": got["bytes"],
            "files": put["files"], "chunks": put.get("chunks"),
            "ready": index_ready(kroot), "seconds": got["seconds"]}
