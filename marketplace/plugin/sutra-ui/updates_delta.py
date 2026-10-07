"""updates_delta.py -- incremental desktop updates: manifest, delta pack, reconstruction.

WHY THIS EXISTS. Every desktop release re-signs every Mach-O in the bundle, so
between two consecutive releases about 1,300 of 25,700 files differ even when a
dozen source files changed -- and the only artifact the updater knew how to
take was the whole notarized DMG (310 MB arm64, 393 MB x86_64). Measured on the
real 2.300.0 -> 2.302.0 pair: 24,428 files identical, 1,314 changed, 9 added,
and the changes are almost entirely signature blobs at the END of a Mach-O
slice, a code-directory header near the FRONT of one, a pyc header, or a few
hundred lines of a CodeResources plist. A per-file delta that copies the
unchanged bytes from the installed bundle and ships only the literal
differences packs those 1,323 files into 1.4 MB raw, 0.35 MB compressed.

WHAT IT DOES NOT DO. It never re-signs, never patches a bundle in place, and
never trusts itself: the reconstruction is byte-for-byte the signed bundle CI
released (manifest hashes of every file, symlink target, mode, empty dir), and
it is handed to the SAME gates the DMG path uses -- codesign --verify --deep
--strict, Gatekeeper, TeamIdentifier continuity, bundle id, version -- before
the existing helper swaps it in beside the old bundle. Any miss at any step is
a RuntimeError the caller turns into a full-DMG download. The delta lane can
only ever save bandwidth; it cannot install something the DMG lane would not.

THE THREE ARTIFACTS, per release and per arch, published beside the DMG:

  Sutra-<arch>.manifest.json     every path in the signed .app: sha256, mode,
                                 symlink target, empty dirs; plus version, arch,
                                 channel, bundle id, previous stable version.
  Sutra-<arch>.delta.tar.xz      one member per NEW file hash: either the whole
                                 file, or ops that rebuild it from the previous
                                 release's file with the same path.
  *.sha256                       transport checksums, same rule as the DMG.

A client N releases behind walks previous_version back through the manifests
and applies the packs in order (cap MAX_CHAIN, else full DMG). Nothing here
runs on import, and nothing here touches /Applications: the caller reconstructs
into the staging directory and the helper does the swap.

PACK SAFETY. Packs are never extracted with tarfile.extract/extractall. Member
names must be exactly `index.json` or `blobs/<64 hex>`, regular files under a
size bound; everything else is refused. Manifest paths are validated (relative,
no `..`, no empty component) before any of them is created on disk.

CLI (used by CI and the end-to-end tests):
  python3 -m updates_delta manifest <new.app> --version V --arch A --channel C
                                    --bundle-id B [--previous P] --out M.json
  python3 -m updates_delta pack <old.app> <new.app> --manifest M.json --out pack.tar.xz
  python3 -m updates_delta reconstruct <base.app> --manifest M.json --dest out.app
                                    [--pack P ...]      (newest pack first)
"""
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

SCHEMA = 1
BLOCK = 4096                       # aligned-diff granularity
MAX_CHAIN = 5                      # packs a client will chain before taking the DMG
MAX_INDEX_BYTES = 64 << 20         # a pack index larger than this is not a pack
MAX_MEMBER_BYTES = 1 << 30         # one literal member; the biggest file in the bundle
MAX_MANIFEST_BYTES = 64 << 20
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MEMBER = re.compile(r"^blobs/([0-9a-f]{64})$")


class DeltaMiss(RuntimeError):
    """The delta lane cannot produce this bundle from what it has. Not an
    error in the release: the caller takes the full image instead."""


# ------------------------------------------------------------ hashing -------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------- manifest -------

def _safe_rel(rel):
    """A manifest path is relative, non-empty, and never climbs."""
    if not rel or rel.startswith("/") or "\x00" in rel or "\\" in rel:
        return False
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            return False
    return True


def build_manifest(app_dir, version, arch, channel, bundle_id, tag=None,
                   previous_version=None):
    """Walk a signed .app and record everything needed to rebuild it exactly."""
    app_dir = Path(app_dir)
    if not app_dir.is_dir() or app_dir.is_symlink():
        raise RuntimeError("not a bundle directory: %s" % app_dir)
    entries = []
    total = 0
    for dp, dns, fns in os.walk(app_dir, followlinks=False):
        dns.sort()
        fns.sort()
        d = Path(dp)
        # directories: only EMPTY ones are recorded; every other directory is
        # implied by the files below it. Symlinked dirs are symlinks.
        for name in list(dns):
            p = d / name
            if p.is_symlink():
                dns.remove(name)
                entries.append({"p": str(p.relative_to(app_dir)), "t": "l",
                                "l": os.readlink(p)})
                continue
            if not any(True for _ in p.iterdir()):
                entries.append({"p": str(p.relative_to(app_dir)), "t": "d",
                                "m": p.lstat().st_mode & 0o7777})
        for name in fns:
            p = d / name
            st = p.lstat()
            rel = str(p.relative_to(app_dir))
            if stat.S_ISLNK(st.st_mode):
                entries.append({"p": rel, "t": "l", "l": os.readlink(p)})
            elif stat.S_ISREG(st.st_mode):
                entries.append({"p": rel, "t": "f", "h": sha256_file(p),
                                "s": st.st_size, "m": st.st_mode & 0o7777})
                total += st.st_size
            else:
                raise RuntimeError("unsupported file type in bundle: %s" % rel)
    for e in entries:
        if not _safe_rel(e["p"]):
            raise RuntimeError("refusing unsafe path in bundle: %r" % e["p"])
    entries.sort(key=lambda e: e["p"])
    man = {
        "schema": SCHEMA,
        "version": str(version),
        "arch": str(arch),
        "channel": str(channel),
        "bundle_id": str(bundle_id),
        "tag": tag,
        "previous_version": previous_version,
        "app_name": app_dir.name,
        "files": sum(1 for e in entries if e["t"] == "f"),
        "bytes": total,
        "entries": entries,
    }
    man["tree_sha256"] = tree_digest(man)
    return man


def tree_digest(man):
    """Content identity of a bundle: hash of the canonical entry list."""
    canon = json.dumps(man["entries"], sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canon.encode("utf-8"))


def validate_manifest(man):
    if not isinstance(man, dict) or man.get("schema") != SCHEMA:
        raise RuntimeError("manifest schema is not %s" % SCHEMA)
    for key in ("version", "arch", "channel", "bundle_id", "entries"):
        if key not in man:
            raise RuntimeError("manifest is missing %r" % key)
    seen = set()
    for e in man["entries"]:
        p = e.get("p")
        if not isinstance(p, str) or not _safe_rel(p):
            raise RuntimeError("manifest carries an unsafe path: %r" % (p,))
        if p in seen:
            raise RuntimeError("manifest lists %s twice" % p)
        seen.add(p)
        t = e.get("t")
        if t == "f":
            if not isinstance(e.get("h"), str) or not _HEX64.match(e["h"]):
                raise RuntimeError("bad hash for %s" % p)
            if not isinstance(e.get("m"), int):
                raise RuntimeError("bad mode for %s" % p)
        elif t == "l":
            if not isinstance(e.get("l"), str) or not e["l"] or "\x00" in e["l"]:
                raise RuntimeError("bad symlink target for %s" % p)
        elif t == "d":
            if not isinstance(e.get("m"), int):
                raise RuntimeError("bad mode for dir %s" % p)
        else:
            raise RuntimeError("unknown entry type %r for %s" % (t, p))
    # Nothing may live BELOW a symlink entry: a manifest that named
    # `Contents/x -> /etc` and then `Contents/x/passwd` would otherwise make
    # the reconstruction write through the link, outside its own directory.
    links = [e["p"] + "/" for e in man["entries"] if e.get("t") == "l"]
    for e in man["entries"]:
        for prefix in links:
            if e["p"].startswith(prefix):
                raise RuntimeError("manifest places %s under the symlink %s"
                                   % (e["p"], prefix[:-1]))
    if man.get("tree_sha256") and man["tree_sha256"] != tree_digest(man):
        raise RuntimeError("manifest tree digest does not match its entries")
    return man


def load_manifest(path):
    p = Path(path)
    if p.stat().st_size > MAX_MANIFEST_BYTES:
        raise RuntimeError("manifest is implausibly large")
    with open(p, "rb") as fh:
        man = json.loads(fh.read().decode("utf-8"))
    return validate_manifest(man)


# -------------------------------------------------------------- codec -------
# A delta is a list of ops over the OLD bytes: ["c", old_off, length] copies a
# run, ["l", length] takes the next `length` literal bytes. Every encoder is
# self-verified by applying it; the smallest literal wins; full is the floor.

def apply_ops(old, ops, lit):
    out = bytearray()
    p = 0
    for op in ops:
        if op[0] == "c":
            off, n = int(op[1]), int(op[2])
            if off < 0 or n < 0 or off + n > len(old):
                raise RuntimeError("delta copy outside the base file")
            out += old[off:off + n]
        elif op[0] == "l":
            n = int(op[1])
            if n < 0 or p + n > len(lit):
                raise RuntimeError("delta literal outside the pack member")
            out += lit[p:p + n]
            p += n
        else:
            raise RuntimeError("unknown delta op %r" % (op[0],))
    if p != len(lit):
        raise RuntimeError("delta did not consume its literals")
    return bytes(out)


def _common_prefix(a, b):
    n = min(len(a), len(b))
    i = 0
    step = 1 << 16
    while i + step <= n and a[i:i + step] == b[i:i + step]:
        i += step
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _common_suffix(a, b, maxlen):
    n = min(len(a), len(b), maxlen)
    i = 0
    step = 1 << 16
    while i + step <= n and a[len(a) - i - step:len(a) - i] == b[len(b) - i - step:len(b) - i]:
        i += step
    while i < n and a[len(a) - 1 - i] == b[len(b) - 1 - i]:
        i += 1
    return i


def enc_trim(old, new, base=0):
    """Common prefix + common suffix; the middle is literal. Catches a signature
    blob rewritten at the tail of a thin Mach-O and a pyc header at the head."""
    pl = _common_prefix(old, new)
    sl = _common_suffix(old, new, min(len(old), len(new)) - pl)
    ops, lit = [], bytearray()
    if pl:
        ops.append(["c", base, pl])
    mid = new[pl:len(new) - sl]
    if mid:
        ops.append(["l", len(mid)])
        lit += mid
    if sl:
        ops.append(["c", base + len(old) - sl, sl])
    return ops, bytes(lit)


def enc_aligned(old, new, base=0):
    """Same length: 4 KiB blocks that differ become literals. Catches a code
    directory whose special-slot hash changed while its 30k page hashes did not."""
    if len(old) != len(new):
        return None
    ops, lit = [], bytearray()
    i, n = 0, len(new)
    while i < n:
        j = min(i + BLOCK, n)
        if old[i:j] == new[i:j]:
            k = j
            while k < n and old[k:k + BLOCK] == new[k:k + BLOCK]:
                k += BLOCK
            k = min(k, n)
            ops.append(["c", base + i, k - i])
        else:
            k = j
            while k < n and old[k:k + BLOCK] != new[k:k + BLOCK]:
                k += BLOCK
            k = min(k, n)
            ops.append(["l", k - i])
            lit += new[i:k]
        i = k
    return ops, bytes(lit)


def _fat_slices(b):
    if len(b) < 8:
        return None
    magic, n = struct.unpack(">II", b[:8])
    if magic != 0xCAFEBABE or n == 0 or n > 20 or len(b) < 8 + 20 * n:
        return None
    out = []
    for k in range(n):
        off = 8 + k * 20
        _cpu, _sub, foff, fsize, _align = struct.unpack(">IIIII", b[off:off + 20])
        if foff + fsize > len(b):
            return None
        out.append((foff, fsize))
    return out


def enc_fat(old, new, base=0):
    """Universal (fat) Mach-O: each slice carries its own signature at ITS end,
    so trim is applied per slice; headers and padding between slices are
    copied when unchanged."""
    so, sn = _fat_slices(old), _fat_slices(new)
    if not so or not sn or len(so) != len(sn):
        return None
    ops, lit = [], bytearray()
    pos = 0
    for (oo, osz), (no, nsz) in zip(so, sn):
        if no < pos:
            return None
        gap = new[pos:no]
        if gap:
            og = old[pos:oo] if oo >= pos else b""
            if og == gap:
                ops.append(["c", base + pos, len(gap)])
            else:
                ops.append(["l", len(gap)])
                lit += gap
        o_sl, n_sl = old[oo:oo + osz], new[no:no + nsz]
        r = enc_aligned(o_sl, n_sl, base + oo) or enc_trim(o_sl, n_sl, base + oo)
        ops += r[0]
        lit += r[1]
        pos = no + nsz
    tail = new[pos:]
    if tail:
        ops.append(["l", len(tail)])
        lit += tail
    return ops, bytes(lit)


def enc_lines(old, new, base=0):
    """Text: old lines indexed by content, new walked, matching runs copied.
    Catches the CodeResources plist where 1,300 of 100k lines change."""
    if b"\x00" in new[:4096] or b"\x00" in old[:4096]:
        return None
    ol = old.split(b"\n")
    idx = {}
    off = 0
    for i, line in enumerate(ol):
        idx.setdefault(line, []).append((i, off))
        off += len(line) + 1
    nl = new.split(b"\n")
    ops, lit = [], bytearray()
    run = bytearray()
    i = 0

    def flush():
        nonlocal run
        if run:
            ops.append(["l", len(run)])
            lit.extend(run)
            run = bytearray()

    while i < len(nl):
        cand = idx.get(nl[i])
        if cand and len(nl[i]) > 8:
            best = None
            for (oi, ooff) in cand[:8]:
                k = 0
                while i + k < len(nl) and oi + k < len(ol) and nl[i + k] == ol[oi + k]:
                    k += 1
                if best is None or k > best[0]:
                    best = (k, oi, ooff)
            k, oi, ooff = best
            if k >= 2 or len(nl[i]) > 40:
                flush()
                last = i + k < len(nl)          # the joining newline exists only if more follows
                seg_len = sum(len(x) + 1 for x in ol[oi:oi + k]) - (0 if last else 1)
                if oi + k >= len(ol) and last:  # old ran out: its last line has no newline
                    seg_len -= 1
                    run += b"\n"
                ops.append(["c", base + ooff, seg_len])
                i += k
                continue
        run += nl[i] + (b"\n" if i + 1 < len(nl) else b"")
        i += 1
    flush()
    return ops, bytes(lit)


def encode(old, new):
    """(kind, ops, literals) that rebuilds `new` from `old`; verified here."""
    best = ("full", [["l", len(new)]], new)
    for kind, fn in (("aligned", enc_aligned), ("fat", enc_fat),
                     ("trim", enc_trim), ("lines", enc_lines)):
        try:
            r = fn(old, new)
        except Exception:
            r = None
        if not r:
            continue
        ops, lit = r
        if len(lit) < len(best[2]):
            try:
                ok = apply_ops(old, ops, lit) == new
            except RuntimeError:
                ok = False
            if ok:
                best = (kind, ops, lit)
    return best


# --------------------------------------------------------------- pack -------

def index_bundle(app_dir):
    """{relative path: sha256} for every regular file; symlinks and dirs skipped."""
    app_dir = Path(app_dir)
    out = {}
    for dp, dns, fns in os.walk(app_dir, followlinks=False):
        d = Path(dp)
        dns[:] = [n for n in dns if not (d / n).is_symlink()]
        for n in fns:
            p = d / n
            if p.is_symlink():
                continue
            if stat.S_ISREG(p.lstat().st_mode):
                out[str(p.relative_to(app_dir))] = sha256_file(p)
    return out


def build_pack(old_app, new_app, manifest, out_path, from_version=None):
    """Write a pack that turns the OLD bundle's files into every file of the NEW
    manifest that the old bundle does not already contain (by hash)."""
    validate_manifest(manifest)
    old_app, new_app = Path(old_app), Path(new_app)
    old_by_path = index_bundle(old_app)
    old_hashes = set(old_by_path.values())
    index = {"schema": SCHEMA, "from_version": from_version, "to_version": manifest["version"],
             "arch": manifest["arch"], "channel": manifest["channel"], "entries": {}}
    members = {}
    stats = {"unchanged": 0, "full": 0, "delta": 0, "literal_bytes": 0, "new_bytes": 0}
    for e in manifest["entries"]:
        if e["t"] != "f":
            continue
        h = e["h"]
        if h in old_hashes:
            stats["unchanged"] += 1
            continue
        if h in index["entries"]:
            continue                                   # same content at another path
        new_bytes = (new_app / e["p"]).read_bytes()
        if sha256_bytes(new_bytes) != h:
            raise RuntimeError("manifest hash does not match %s" % e["p"])
        base_h = old_by_path.get(e["p"])
        kind, ops, lit = "full", [["l", len(new_bytes)]], new_bytes
        if base_h:
            old_bytes = (old_app / e["p"]).read_bytes()
            kind, ops, lit = encode(old_bytes, new_bytes)
            if kind != "full" and len(lit) >= 0.9 * len(new_bytes):
                kind, ops, lit = "full", [["l", len(new_bytes)]], new_bytes
        entry = {"kind": kind, "size": len(new_bytes)}
        if kind != "full":
            entry["base"] = base_h
            entry["ops"] = ops
            stats["delta"] += 1
        else:
            stats["full"] += 1
        index["entries"][h] = entry
        members[h] = lit
        stats["literal_bytes"] += len(lit)
        stats["new_bytes"] += len(new_bytes)
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.name + ".tmp")
    with tarfile.open(tmp, "w:xz", preset=6) as tar:
        raw = json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ti = tarfile.TarInfo("index.json")
        ti.size = len(raw)
        ti.mtime = 0
        tar.addfile(ti, io.BytesIO(raw))
        for h in sorted(members):
            ti = tarfile.TarInfo("blobs/%s" % h)
            ti.size = len(members[h])
            ti.mtime = 0
            tar.addfile(ti, io.BytesIO(members[h]))
    os.replace(tmp, out_path)
    stats["pack_bytes"] = out_path.stat().st_size
    stats["members"] = len(members)
    return stats


def unpack_to_dir(pack_path, dest):
    """Stream a pack into dest/index.json and dest/blobs/<hash>, refusing every
    member that is not exactly that shape. Never tarfile.extract()."""
    dest = Path(dest)
    (dest / "blobs").mkdir(parents=True, exist_ok=True)
    index = None
    with tarfile.open(pack_path, "r:xz") as tar:
        for ti in tar:
            if not ti.isreg():
                raise RuntimeError("pack member %r is not a regular file" % ti.name)
            if ti.name == "index.json":
                if ti.size > MAX_INDEX_BYTES:
                    raise RuntimeError("pack index is implausibly large")
                index = json.loads(tar.extractfile(ti).read().decode("utf-8"))
                continue
            m = _MEMBER.match(ti.name)
            if not m:
                raise RuntimeError("pack member %r is not allowed" % ti.name)
            if ti.size > MAX_MEMBER_BYTES:
                raise RuntimeError("pack member %s is implausibly large" % ti.name)
            src = tar.extractfile(ti)
            target = dest / "blobs" / m.group(1)
            with open(target, "wb") as fh:
                shutil.copyfileobj(src, fh)
    if not isinstance(index, dict) or index.get("schema") != SCHEMA:
        raise RuntimeError("pack has no usable index")
    if not isinstance(index.get("entries"), dict):
        raise RuntimeError("pack index has no entries")
    for h, ent in index["entries"].items():
        if not _HEX64.match(h) or not isinstance(ent, dict):
            raise RuntimeError("pack index entry %r is malformed" % (h,))
        if ent.get("kind") != "full":
            if not isinstance(ent.get("base"), str) or not _HEX64.match(ent["base"]):
                raise RuntimeError("pack delta %s has no base hash" % h)
            if not isinstance(ent.get("ops"), list):
                raise RuntimeError("pack delta %s has no ops" % h)
    with open(dest / "index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh)
    return index


# ------------------------------------------------------ reconstruction ------

class _Packs:
    """Unpacked packs, newest first, with blob resolution and a memo."""

    def __init__(self, pack_dirs):
        self.dirs = [Path(d) for d in pack_dirs]
        self.indexes = []
        for d in self.dirs:
            with open(d / "index.json", "r", encoding="utf-8") as fh:
                self.indexes.append(json.load(fh))
        self.memo = {}

    def lookup(self, h):
        for d, idx in zip(self.dirs, self.indexes):
            ent = idx["entries"].get(h)
            if ent is not None:
                return d, ent
        return None, None

    def resolve(self, h, base_bytes_for, depth=0):
        """Bytes for hash h: from the base bundle, or from a pack (recursively
        rebuilding the delta's own base). Raises DeltaMiss when impossible."""
        if h in self.memo:
            return self.memo[h]
        if depth > MAX_CHAIN + 2:
            raise DeltaMiss("delta chain for %s is too deep" % h[:12])
        data = base_bytes_for(h)
        if data is None:
            d, ent = self.lookup(h)
            if ent is None:
                raise DeltaMiss("no pack carries file %s" % h[:12])
            lit = (d / "blobs" / h).read_bytes()
            if ent["kind"] == "full":
                data = lit
            else:
                base = self.resolve(ent["base"], base_bytes_for, depth + 1)
                data = apply_ops(base, ent["ops"], lit)
        if sha256_bytes(data) != h:
            raise RuntimeError("rebuilt file does not hash to %s" % h[:12])
        if len(data) <= (32 << 20):
            self.memo[h] = data
        return data


def _clone_tree(src, dst):
    """APFS clone (instant, copy-on-write); plain copy elsewhere."""
    p = subprocess.run(["cp", "-c", "-R", "-p", str(src), str(dst)],
                       capture_output=True, text=True)
    if p.returncode == 0:
        return "clone"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, symlinks=True)
    return "copy"


def reconstruct(base_app, manifest, pack_dirs, dest, progress=None):
    """Rebuild the bundle described by `manifest` at `dest` from the installed
    `base_app` plus the given unpacked packs (newest first). Verifies every
    entry before returning. Raises DeltaMiss when a full image is needed and
    RuntimeError when something is actually wrong."""
    validate_manifest(manifest)
    base_app, dest = Path(base_app), Path(dest)
    if dest.exists():
        raise RuntimeError("reconstruction target already exists: %s" % dest)
    if not base_app.is_dir():
        raise DeltaMiss("no installed bundle to build from")
    t0 = time.time()
    base_by_path = index_bundle(base_app)
    base_by_hash = {}
    for p, h in base_by_path.items():
        base_by_hash.setdefault(h, p)
    packs = _Packs(pack_dirs)

    def base_bytes_for(h):
        p = base_by_hash.get(h)
        return (base_app / p).read_bytes() if p else None

    wanted = {e["p"]: e for e in manifest["entries"]}
    # Everything that needs bytes is resolved BEFORE the tree is touched, so a
    # miss costs nothing but hashing time and leaves no half-built directory.
    plan = {}
    for e in manifest["entries"]:
        if e["t"] != "f":
            continue
        if base_by_path.get(e["p"]) == e["h"]:
            continue                                     # cloned as-is
        if e["h"] in base_by_hash:
            plan[e["p"]] = ("copy", base_by_hash[e["h"]])
        else:
            packs.resolve(e["h"], base_bytes_for)        # raises DeltaMiss
            plan[e["p"]] = ("blob", e["h"])
    # Free-space preflight. The clone is copy-on-write on APFS, but every file
    # the plan rewrites is written in full, and a non-APFS fallback copies the
    # whole bundle. ENOSPC halfway through would otherwise read as corruption.
    need = sum(e.get("s", 0) for e in manifest["entries"] if e["t"] == "f" and e["p"] in plan)
    need += 64 << 20
    try:
        free = shutil.disk_usage(dest.parent).free
    except OSError:
        free = None
    if free is not None and free < need:
        raise DeltaMiss("not enough free space to rebuild the bundle (%d MB needed, %d MB free)"
                        % (need >> 20, free >> 20))
    how = _clone_tree(base_app, dest)
    if how == "copy" and free is not None and free < need + manifest.get("bytes", 0):
        shutil.rmtree(dest, ignore_errors=True)
        raise DeltaMiss("not enough free space for a full copy of the bundle")
    stats = {"clone": how, "kept": 0, "copied": 0, "rebuilt": 0, "removed": 0,
             "bytes_written": 0, "seconds": 0.0}
    try:
        # 1. remove everything the manifest does not list (files, links, dirs)
        keep_dirs = set()
        for p in wanted:
            parts = p.split("/")
            for i in range(1, len(parts)):
                keep_dirs.add("/".join(parts[:i]))
        for dp, dns, fns in os.walk(dest, topdown=False, followlinks=False):
            d = Path(dp)
            for n in fns:
                rel = str((d / n).relative_to(dest))
                if rel not in wanted:
                    (d / n).unlink()
                    stats["removed"] += 1
            for n in dns:
                p = d / n
                rel = str(p.relative_to(dest))
                if p.is_symlink():
                    if rel not in wanted:
                        p.unlink()
                        stats["removed"] += 1
                elif rel not in wanted and rel not in keep_dirs:
                    shutil.rmtree(p)
                    stats["removed"] += 1
        # 2. materialise every entry
        for e in manifest["entries"]:
            p = dest / e["p"]
            if e["t"] == "d":
                if p.is_symlink() or (p.exists() and not p.is_dir()):
                    p.unlink()
                p.mkdir(parents=True, exist_ok=True)
                continue
            if e["t"] == "l":
                if p.is_symlink():
                    if os.readlink(p) == e["l"]:
                        continue
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    p.unlink()
                p.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(e["l"], p)
                continue
            # regular file
            step = plan.get(e["p"])
            if step is None:
                stats["kept"] += 1
            else:
                if p.is_symlink() or p.is_dir():
                    if p.is_dir() and not p.is_symlink():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                p.parent.mkdir(parents=True, exist_ok=True)
                if step[0] == "copy":
                    # from the BASE, not dest: the old path may already have
                    # been swept away as an extra a few lines above.
                    src = base_app / step[1]
                    tmp = p.with_name(p.name + ".delta-tmp")
                    shutil.copyfile(src, tmp)
                    os.replace(tmp, p)
                    stats["copied"] += 1
                else:
                    data = packs.resolve(step[1], base_bytes_for)
                    tmp = p.with_name(p.name + ".delta-tmp")
                    with open(tmp, "wb") as fh:
                        fh.write(data)
                    os.replace(tmp, p)
                    stats["rebuilt"] += 1
                    stats["bytes_written"] += len(data)
            if (p.lstat().st_mode & 0o7777) != e["m"]:
                os.chmod(p, e["m"])
        for e in manifest["entries"]:
            if e["t"] == "d":
                p = dest / e["p"]
                if (p.lstat().st_mode & 0o7777) != e["m"]:
                    os.chmod(p, e["m"])
        # 3. verify the whole tree against the manifest, independently
        problems = verify_tree(dest, manifest)
        if problems:
            raise RuntimeError("reconstructed bundle does not match its manifest: %s"
                               % "; ".join(problems[:5]))
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    stats["seconds"] = round(time.time() - t0, 2)
    return stats


def verify_tree(app_dir, manifest):
    """Every manifest entry present and exact, nothing extra. Returns a list of
    problems (empty means the tree IS the manifest)."""
    app_dir = Path(app_dir)
    problems = []
    wanted = {e["p"]: e for e in manifest["entries"]}
    keep_dirs = set()
    for p in wanted:
        parts = p.split("/")
        for i in range(1, len(parts)):
            keep_dirs.add("/".join(parts[:i]))
    seen = set()
    for dp, dns, fns in os.walk(app_dir, followlinks=False):
        d = Path(dp)
        for n in list(dns):
            p = d / n
            rel = str(p.relative_to(app_dir))
            if p.is_symlink():
                dns.remove(n)
                seen.add(rel)
                if rel not in wanted:
                    problems.append("extra symlink %s" % rel)
            elif rel not in keep_dirs:
                if rel in wanted and wanted[rel]["t"] == "d":
                    seen.add(rel)
                    if (p.lstat().st_mode & 0o7777) != wanted[rel]["m"]:
                        problems.append("mode of dir %s" % rel)
                else:
                    problems.append("extra directory %s" % rel)
        for n in fns:
            p = d / n
            rel = str(p.relative_to(app_dir))
            seen.add(rel)
            e = wanted.get(rel)
            if e is None:
                problems.append("extra file %s" % rel)
                continue
            st = p.lstat()
            if e["t"] == "l":
                if not stat.S_ISLNK(st.st_mode) or os.readlink(p) != e["l"]:
                    problems.append("symlink %s" % rel)
            elif e["t"] == "f":
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                    problems.append("not a regular file %s" % rel)
                elif (st.st_mode & 0o7777) != e["m"]:
                    problems.append("mode of %s" % rel)
                elif sha256_file(p) != e["h"]:
                    problems.append("content of %s" % rel)
            else:
                problems.append("directory expected at %s" % rel)
    for rel, e in wanted.items():
        if rel not in seen:
            if e["t"] == "l" and (app_dir / rel).is_symlink():
                if os.readlink(app_dir / rel) != e["l"]:
                    problems.append("symlink %s" % rel)
                continue
            problems.append("missing %s" % rel)
    return problems


# ---------------------------------------------------------------- CLI -------

def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="updates_delta")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("app")
    m.add_argument("--version", required=True)
    m.add_argument("--arch", required=True)
    m.add_argument("--channel", default="stable")
    m.add_argument("--bundle-id", required=True)
    m.add_argument("--tag")
    m.add_argument("--previous")
    m.add_argument("--out", required=True)
    p = sub.add_parser("pack")
    p.add_argument("old_app")
    p.add_argument("new_app")
    p.add_argument("--manifest", required=True)
    p.add_argument("--from-version")
    p.add_argument("--out", required=True)
    r = sub.add_parser("reconstruct")
    r.add_argument("base_app")
    r.add_argument("--manifest", required=True)
    r.add_argument("--pack", action="append", default=[])
    r.add_argument("--dest", required=True)
    v = sub.add_parser("verify")
    v.add_argument("app")
    v.add_argument("--manifest", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "manifest":
        man = build_manifest(a.app, a.version, a.arch, a.channel, a.bundle_id,
                             tag=a.tag, previous_version=a.previous)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(man, fh, sort_keys=True, separators=(",", ":"))
        return {"ok": True, "files": man["files"], "bytes": man["bytes"],
                "tree_sha256": man["tree_sha256"], "out": a.out}
    if a.cmd == "pack":
        man = load_manifest(a.manifest)
        st = build_pack(a.old_app, a.new_app, man, a.out, from_version=a.from_version)
        st["ok"] = True
        st["out"] = a.out
        return st
    if a.cmd == "reconstruct":
        man = load_manifest(a.manifest)
        work = tempfile.mkdtemp(prefix="sutra-delta-")
        dirs = []
        try:
            for i, pk in enumerate(a.pack):
                d = Path(work) / ("pack%d" % i)
                unpack_to_dir(pk, d)
                dirs.append(d)
            st = reconstruct(a.base_app, man, dirs, a.dest)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        st["ok"] = True
        st["dest"] = a.dest
        return st
    if a.cmd == "verify":
        man = load_manifest(a.manifest)
        problems = verify_tree(a.app, man)
        return {"ok": not problems, "problems": problems[:20]}
    raise SystemExit(2)


def main(argv=None):
    try:
        out = _cli(sys.argv[1:] if argv is None else argv)
    except DeltaMiss as exc:
        print(json.dumps({"ok": False, "miss": str(exc)}))
        return 3
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
