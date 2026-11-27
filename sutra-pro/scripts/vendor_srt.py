#!/usr/bin/env python3
"""Vendor srt (`@anthropic-ai/sandbox-runtime`) and its runtime dependencies into `sutra_app/vendor/srt/` (D462).

    scripts/py scripts/vendor_srt.py            # download the pinned tarballs (registry.npmjs.org), verify, patch, write
    scripts/py scripts/vendor_srt.py --check    # offline: the tree is exactly upstream plus S1 and S2 (exit 1 otherwise)

Write mode downloads the five pinned tarballs, refuses one whose sha512 differs from its pin, extracts regular files only
(no links, no absolute or `..` paths; paths with a `.`-component are dropped and listed), applies the numbered patches S1 and
S2 as anchored exact-text edits (vendor_j2's `Edit` and `apply_edits`: an anchor that is not there the required number of
times stops the run), and writes the tree, `srt.mjs`, `NOTICE` and `VENDORED.md` (pins, patches, the sha256 of every file
upstream and vendored). `--check` re-hashes every file, undoes S1 and S2 on the patched files and compares with the recorded
upstream sha256, and reports missing and extra files. Standard library only.
"""
import argparse
import base64
import hashlib
import io
import re
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vendor_j2 import Edit, VendorError, apply_edits      # noqa: E402  (the J2 patch mechanics, reused)

REPO = Path(__file__).resolve().parent.parent
DEST = "sutra_app/vendor/srt"
SRT = "@anthropic-ai/sandbox-runtime"
REGISTRY = "https://registry.npmjs.org/"

# (npm name, exact version, tarball URL, npm sha512 integrity). Each dependency is the newest version inside srt 0.0.83's range.
PINS = (
    (SRT, "0.0.83", REGISTRY + "@anthropic-ai/sandbox-runtime/-/sandbox-runtime-0.0.83.tgz",
     "sha512-yEusORnVJrNseF/9fvjVYyk6tr79/aFbIB3T/X8p2puLZdaaiGNeYN50v0CE+1DT70v7XuzKOAnTivh1f5cksA=="),
    ("zod", "3.25.76", REGISTRY + "zod/-/zod-3.25.76.tgz",                                  # ^3.25.0
     "sha512-gzUt/qt81nXsFGKIFcC3YnfEAx5NkunCfnDlvuBSSFS02bcXu4Lmea0AFIUwbLWxWPx3d9p8S5QoaujKcNQxcQ=="),
    ("commander", "12.1.0", REGISTRY + "commander/-/commander-12.1.0.tgz",                  # ^12.1.0
     "sha512-Vw8qHK3bZM9y/P10u3Vib8o/DdkvA2OtPtZvD871QKjy74Wj1WSKFILMPRPSdUSx5RFK1arlJzEtA4PkFgnbuA=="),
    ("node-forge", "1.4.4", REGISTRY + "node-forge/-/node-forge-1.4.4.tgz",                 # ^1.4.0
     "sha512-T6VRRpF3+czIGcXW/LOeoD7Ej28d8CF1UMEAbJyJRUtYMvyXAgxUPW2kbUibumvV9LiUQAznJOFyeYclzSJMMg=="),
    ("@pondwader/socks5-server", "1.0.10", REGISTRY + "@pondwader/socks5-server/-/socks5-server-1.0.10.tgz",   # ^1.0.10
     "sha512-bQY06wzzR8D2+vVCUoBsr5QS2U6UgPUQRmErNwtsuI6vLcyRKkafjkr3KxbtGFf9aBBIV2mcvlsKD1UYaIV+sg=="),
)

HTTP_PROXY = f"node_modules/{SRT}/dist/sandbox/http-proxy.js"
SOCKS_PROXY = f"node_modules/{SRT}/dist/sandbox/socks-proxy.js"
CLI = f"node_modules/{SRT}/dist/cli.js"
_NOTE = ("            // Modified by Sutra (patch {id}, D462): destroy only when the upstream did not end cleanly; after a clean end pipe() has already\n"
         "            // called socket.end(), which flushes the queued bytes (anthropics/sandbox-runtime#606).\n")
EDITS = (
    Edit("S1", HTTP_PROXY, "            upstream.on('close', () => socket.destroy());\n",
         _NOTE.format(id="S1") + "            upstream.on('close', () => { if (!upstream.readableEnded) socket.destroy(); });\n"),
    Edit("S2", SOCKS_PROXY, "            upstream.on('close', () => conn.socket.destroy());\n",
         _NOTE.format(id="S2") + "            upstream.on('close', () => { if (!upstream.readableEnded) conn.socket.destroy(); });\n"),
)
PATCH_NOTES = {
    "S1": "the CONNECT tunnel's upstream `close` handler destroys the client socket only when the upstream did not end cleanly, so the bytes still queued after a clean end are flushed",
    "S2": "the same for the SOCKS relay's `conn.socket`",
}

LAUNCHER = ("// Sutra's launcher for the bundled srt (D462). The desktop app runs it on Electron's own node with ELECTRON_RUN_AS_NODE=1;\n"
            "// that variable is removed here so it never reaches the sandboxed command. cli.js runs srt's main() on import.\n"
            "delete process.env.ELECTRON_RUN_AS_NODE;\n"
            f"await import('./{CLI}');\n")
NOTICE = (f"This folder is {SRT} {PINS[0][1]} (Apache-2.0, node_modules/{SRT}/LICENSE) as modified by Sutra:\n"
          f"{HTTP_PROXY} (S1), {SOCKS_PROXY} (S2); see VENDORED.md.\n"
          "The dependencies in node_modules/ ship unchanged, each with its own license.\n")
SUTRA_FILES = {"srt.mjs": LAUNCHER, "NOTICE": NOTICE}       # written by this script, checked byte for byte
VENDORED_MD = "VENDORED.md"
ROW = re.compile(r"^\| `([^`]+)` \| ([0-9a-f]{64}) \| ([0-9a-f]{64}) \| ([^|]*) \|$", re.M)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def extract(tgz: bytes, name: str):
    """The tarball's regular files as {path below `package/`: (bytes, mode)}, and the dropped dot-paths. A link, a device, an
    absolute path or a `..` component raises VendorError."""
    files, dropped = {}, []
    with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as t:
        for m in t.getmembers():
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise VendorError(f"{name}: refused path {m.name!r} (absolute or `..`)")
            if m.isdir():
                continue
            if not m.isfile():
                raise VendorError(f"{name}: refused {m.name!r} (not a regular file: a link or a device)")
            if len(p.parts) < 2 or p.parts[0] != "package":
                raise VendorError(f"{name}: refused {m.name!r} (outside the tarball's package/ folder)")
            rel = PurePosixPath(*p.parts[1:]).as_posix()
            if any(c.startswith(".") for c in p.parts[1:]):
                dropped.append(rel)
                continue
            files[rel] = (t.extractfile(m).read(), 0o755 if m.mode & 0o111 else 0o644)
    return files, sorted(dropped)


def build(pins=None):
    """Download, verify, extract, patch: ({path: (bytes, mode)}, [(path, upstream sha256, vendored sha256, patches)], dropped)."""
    files, upstream, dropped = {}, {}, []
    for name, version, url, want in pins or PINS:
        data = fetch(url)
        if integrity(data) != want:
            raise VendorError(f"{name}@{version}: the tarball's sha512 is not the pinned one ({url})")
        got, gone = extract(data, f"{name}@{version}")
        for rel, v in got.items():
            files[f"node_modules/{name}/{rel}"] = v
        dropped += [f"node_modules/{name}/{rel}" for rel in gone]
    patches = {}
    for path in sorted({e.file for e in EDITS}):
        if path not in files:
            raise VendorError(f"{path}: missing, so {', '.join(e.patch for e in EDITS if e.file == path)} cannot apply")
        mine = [e for e in EDITS if e.file == path]
        data, mode = files[path]
        text, _ = apply_edits(data.decode("utf-8"), mine, name=path)
        upstream[path] = sha256(data)
        files[path] = (text.encode("utf-8"), mode)
        patches[path] = ", ".join(e.patch for e in mine)
    rows = [(p, upstream.get(p, sha256(d)), sha256(d), patches.get(p, "")) for p, (d, _) in sorted(files.items())]
    return files, rows, dropped


def render_vendored_md(rows, dropped, size) -> str:
    pins = "\n".join(f"| `{n}` | {v} | {u} | `{i}` |" for n, v, u, i in PINS)
    patches = "\n".join(f"| {e.patch} | `{e.file}` | {PATCH_NOTES[e.patch]} | D462 |" for e in EDITS)
    table = "\n".join(f"| `{p}` | {u} | {v} | {pt} |" for p, u, v, pt in rows)
    sutra = "\n".join(f"| `{n}` | {sha256(t.encode())} |" for n, t in SUTRA_FILES.items())
    gone = "\n".join(f"- `{p}`" for p in dropped) or "- none"
    return f"""# Vendored srt (D462)

Written by `scripts/vendor_srt.py`; never edit a file here by hand. `scripts/py scripts/vendor_srt.py --check` proves offline that every file below
is the upstream bytes plus the patches S1 and S2.

Size: {size} bytes in {len(rows) + len(SUTRA_FILES) + 1} files.

## Pins

| package | version | tarball | integrity |
|---|---|---|---|
{pins}

## Patches

| id | file | what changes | decision |
|---|---|---|---|
{patches}

## Sutra's own files

| file | sha256 |
|---|---|
{sutra}

## Dropped (a path component starts with `.`: not a runtime file, and setuptools globs skip it)

{gone}

## Home paths in upstream bytes

Upstream comments in this folder hold upstream authors' example home paths (for example `dist/sandbox/sandbox-utils.js`). They stay byte for byte,
because `--check` requires the upstream bytes, so `sutra_app/vendor/srt/` is exempt from AGENTS.md's home-path rule. No scanner needs an exclusion
today (tests/test_ownership.py and scripts/ownership-audit.sh match names only); a tree-wide home-path scanner added later must skip this folder.

## Re-pin (by hand)

1. Edit `PINS` in `scripts/vendor_srt.py`: the new srt version and, for each dependency, the newest version inside srt's range, each with its
   `dist.integrity` (`npm view <name>@<version> dist.integrity`).
2. `scripts/py scripts/vendor_srt.py`. It stops if S1's or S2's anchor moved or changed; when upstream ships the fix (#606), drop S1 and S2.
3. Review the diff, then `scripts/py scripts/vendor_srt.py --check` and the real-srt tests (`tests/engine/test_sandbox_runtime.py`).

## Files

| file | upstream sha256 | vendored sha256 | patches |
|---|---|---|---|
{table}
"""


def write(dest: Path) -> None:
    files, rows, dropped = build()
    if dest.exists():
        shutil.rmtree(dest)
    for rel, (data, mode) in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        p.chmod(mode)
    for name, text in SUTRA_FILES.items():
        (dest / name).write_text(text, encoding="utf-8")
    size = sum(len(d) for d, _ in files.values()) + sum(len(t.encode()) for t in SUTRA_FILES.values())
    (dest / VENDORED_MD).write_text(render_vendored_md(rows, dropped, size), encoding="utf-8")


def check(dest: Path) -> list:
    """[] when `dest` is exactly upstream plus EDITS; else one line per problem, naming the file (and the patch)."""
    md = dest / VENDORED_MD
    if not md.is_file():
        return [f"{md}: missing"]
    rows = {m[1]: (m[2], m[3], m[4].strip()) for m in ROW.finditer(md.read_text(encoding="utf-8"))}
    if not rows:
        return [f"{md}: no file table"]
    out = []
    for e in EDITS:
        if e.patch not in rows.get(e.file, ("", "", ""))[2]:
            out.append(f"{e.file}: VENDORED.md does not record {e.patch}")
    for path, (up, vend, patches) in sorted(rows.items()):
        f = dest / path
        if not f.is_file():
            out.append(f"{path}: missing")
            continue
        data = f.read_bytes()
        if sha256(data) != vend:
            out.append(f"{path}: sha256 differs from VENDORED.md")
        mine = [e for e in EDITS if e.file == path]
        if not mine:
            if up != vend:
                out.append(f"{path}: not patched, but its upstream and vendored sha256 differ")
            continue
        try:
            text, _ = apply_edits(data.decode("utf-8"), [Edit(e.patch, e.file, e.new, e.old, e.count) for e in reversed(mine)], name=path)
        except (VendorError, UnicodeDecodeError) as err:
            out.append(f"{path}: {', '.join(e.patch for e in mine)} cannot be undone: {err}")
            continue
        if sha256(text.encode("utf-8")) != up:
            out.append(f"{path}: with {', '.join(e.patch for e in mine)} undone it is not the upstream file")
    for name, text in SUTRA_FILES.items():
        f = dest / name
        if not f.is_file() or f.read_bytes() != text.encode("utf-8"):
            out.append(f"{name}: missing or not the text vendor_srt.py writes")
    known = set(rows) | set(SUTRA_FILES) | {VENDORED_MD}
    for f in sorted(dest.rglob("*")):
        rel = f.relative_to(dest).as_posix()
        if (f.is_file() or f.is_symlink()) and rel not in known:
            out.append(f"{rel}: extra file")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="offline: compare the tree with VENDORED.md, change nothing")
    ap.add_argument("--dest", default=str(REPO), help="the sutra-pro folder (default: this checkout)")
    a = ap.parse_args(argv)
    dest = Path(a.dest) / DEST
    try:
        if a.check:
            problems = check(dest)
            for p in problems:
                print(f"vendor_srt: {p}", file=sys.stderr)
            print(f"vendor_srt: {'FAILED, ' + str(len(problems)) + ' problem(s)' if problems else 'ok'}")
            return 1 if problems else 0
        write(dest)
    except VendorError as e:
        print(f"vendor_srt: {e}", file=sys.stderr)
        return 2
    print(f"vendor_srt: wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
