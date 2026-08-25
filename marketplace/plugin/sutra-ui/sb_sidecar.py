"""SilverBullet sidecar — the Files screen's engine (S1, research doc §12).

Runs the MIT-licensed SilverBullet server binary as a supervised loopback
process and points it at the panel's workdir. The panel embeds the SB client
in an iframe; this module owns lifecycle, hardening, and the startup probe.

Design decisions (dual consult 2026-08-21, PoC atom a-78660f98-06):
- FastAPI owns the sidecar (policy lives next to the file APIs); Electron
  kills the whole runtime tree on exit, so orphans die with the app.
- Read-only follows the SAME out-of-band gate as /api/fs/write: without
  SUTRA_UI_READ_ONLY=1 the sidecar runs SB_READ_ONLY=1 (PoC: PUT -> 403); editing defaults ON
  and NO files are injected into the user's space.
- Theme injection is marker-fenced and only-if-absent: a user's own
  THEME.md is never touched.
- Version pinned + sha256 fail-closed. The 2.10.0 release build does NOT
  implement If-Match/412 (PoC-verified; the docs are ahead of the binary),
  so the probe asserts only ping + config coherence; conflict handling is
  last-writer-wins until upstream ships ETags — the same posture as the
  old textarea editor without base_bytes.
"""

import hashlib
import json
import os
import re
import platform
import signal
import socket
import stat
import subprocess
import time
import urllib.request
import zipfile

import providers

SB_VERSION = "2.10.0"
# Release assets: the *server* binary (the small "sb-*" zips are the CLI client).
SB_ASSETS = {
    "arm64": {
        "url": "https://github.com/silverbulletmd/silverbullet/releases/download/"
               "2.10.0/silverbullet-server-darwin-aarch64.zip",
        "sha256": "3625a3c3b6fcdc1ca1bdbe57559c41c97b3bc642613d8d8d32d40013df648bc1",
    },
    "x86_64": {
        "url": "https://github.com/silverbulletmd/silverbullet/releases/download/"
               "2.10.0/silverbullet-server-darwin-x86_64.zip",
        "sha256": "fd5aac2b006b8b58e38be5ee447441bec8a95f325c436814eb2d6eba8f468b41",
    },
}

# Vendored plugs copied into the space's _plug/ folder (the only place SB 2.x
# loads plugs from) so the offline DMG rule holds — no Plugs: Update fetch.
# Each entry is hash-pinned; a managed copy whose hash matches is left alone,
# a foreign file with the same name is never overwritten.
VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
PLUGS = {
    "treeview.plug.js": {
        "src": os.path.join(VENDOR_DIR, "silverbullet-treeview", "treeview.plug.js"),
        "sha256": "2eb6726e031b788affd0e86f4ca200e7a914b17f1546445eb4ab298c47a5125f",
    },
}

THEME_VERSION = 2
THEME_MARKER_RE = re.compile(r"<!-- sutra-managed: theme v(\d+) -->")
THEME_MARKER = "<!-- sutra-managed: theme v%d -->" % THEME_VERSION
THEME_MD = THEME_MARKER + """
```space-style
/* Sutra theme v2 — generated from panel.css tokens (2.222.x). Keyed on SB's own
   html[data-theme], which SilverBullet derives from prefers-color-scheme; the
   desktop shell drives that scheme via nativeTheme (sutra:theme IPC), so the
   iframe follows the panel toggle. Values are MIRRORED panel tokens — the
   iframe is cross-origin and cannot read the panel's variables. */
html[data-theme="light"] {
  --root-background-color: #ffffff;   /* panel --surface (doc column) */
  --root-color: #1c1917;              /* panel --ink */
  --ui-accent-color: #8A5D2E;         /* panel --acc */
  --top-background-color: #ffffff;
  --ui-font: -apple-system, "Segoe UI", Roboto, sans-serif;
  --editor-font: -apple-system, "Segoe UI", Roboto, sans-serif;
}
html[data-theme="dark"] {
  --root-background-color: #161412;   /* panel --surface */
  --root-color: #F5F0E8;              /* panel --ink */
  --ui-accent-color: #C4956A;         /* panel --acc */
  --top-background-color: #161412;
  --ui-font: -apple-system, "Segoe UI", Roboto, sans-serif;
  --editor-font: -apple-system, "Segoe UI", Roboto, sans-serif;
}
/* The panel renders its own breadcrumb, title context and save state (mock 07),
   so SB's top bar duplicates chrome the design does not have. NARROW selector,
   pinned to SB 2.10.0 (#sb-top verified in its DOM); a broader selector could
   swallow a future read-only or error affordance. Editing and autosave do not
   depend on the bar (verified: PUT persists with it hidden). */
#sb-top { display: none; }
/* Serif headings per the locked mock (panel --serif stack). Pinned-version
   compatibility selectors: SB 2.10.0 renders headings as .sb-line-h1/h2/h3. */
#sb-editor .sb-line-h1, #sb-editor .sb-line-h2, #sb-editor .sb-line-h3 {
  font-family: ui-serif, "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
}
```
"""

_state = {"proc": None, "port": None, "root": None, "error": None, "readonly": None}


def _bin_dir():
    return os.path.expanduser("~/.sutra-ui/bin")


def _bundled_binary():
    """Binary shipped inside the .app by bundle-runtime.sh, if present."""
    res = os.environ.get("SUTRA_UI_RESOURCES")
    if res:
        cand = os.path.join(res, "sb", "silverbullet-server")
        if os.path.isfile(cand):
            return cand
    return None


def binary_path():
    return _bundled_binary() or os.path.join(_bin_dir(), "silverbullet-server-" + SB_VERSION)


def ensure_binary():
    """Return path to a verified binary, downloading the pinned release if absent.

    Fail-closed: a checksum mismatch deletes the download and raises."""
    path = binary_path()
    if os.path.isfile(path):
        return path
    arch = platform.machine()
    asset = SB_ASSETS.get("arm64" if arch == "arm64" else "x86_64")
    if not asset or not asset["sha256"]:
        raise RuntimeError("no pinned SilverBullet asset for arch %s" % arch)
    os.makedirs(_bin_dir(), exist_ok=True)
    zpath = path + ".zip"
    urllib.request.urlretrieve(asset["url"], zpath)
    digest = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
    if digest != asset["sha256"]:
        os.remove(zpath)
        raise RuntimeError("SilverBullet download sha256 mismatch (%s)" % digest)
    with zipfile.ZipFile(zpath) as zf:
        if "silverbullet" not in zf.namelist():
            raise RuntimeError("unexpected zip layout: %s" % zf.namelist()[:5])
        zf.extract("silverbullet", _bin_dir())
    os.replace(os.path.join(_bin_dir(), "silverbullet"), path)
    os.chmod(path, 0o755)
    os.remove(zpath)
    return path


def _stable_port(root):
    """Deterministic per-workdir port. The SB CLIENT keys its space index by
    ORIGIN — a random port per boot meant a fresh origin and a from-scratch
    reindex (minutes on a real corpus) on EVERY app restart; styles and
    markdown rendering read as broken until it finished (reviewer 2026-08-25,
    blocker 3 root cause). Falls forward to the next free port on collision."""
    base = 8340 + (int(hashlib.sha256(root.encode()).hexdigest(), 16) % 200)
    for port in range(base, base + 20):
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", port))
            probe.close()
            return port
        except OSError:
            probe.close()
    return _free_port()


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def inject_theme(root):
    """Marker-versioned, and only when editing is allowed.

    States (strict, no fuzzy merging):
      absent            -> write the current version
      ours, older       -> replace with the current version
      ours, same/newer  -> leave as is (newer = a later plugin wrote it)
      no marker (user)  -> never touch a file we don't own outright
    Returns True when the file on disk is sutra-managed after the call."""
    if not providers.editing_allowed():
        return False
    path = os.path.join(root, "THEME.md")
    if os.path.exists(path):
        head = open(path, "r", encoding="utf-8", errors="replace").read(120)
        m = THEME_MARKER_RE.match(head)
        if not m:
            return False                      # user-authored: hands off
        if int(m.group(1)) >= THEME_VERSION:
            return True                       # same or newer: no-op
        # ours and older: replace wholesale (managed block IS the whole file)
    tmp = path + ".sutra-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(THEME_MD)
    os.replace(tmp, path)
    return True


def _is_regular(path):
    """True only for a real regular file — not a symlink, FIFO, device or dir.
    lstat, not stat: a symlink to a regular file must still be refused."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    import stat as _stat
    return _stat.S_ISREG(st.st_mode)


def _sha256(path):
    if not _is_regular(path):
        raise RuntimeError("refusing to hash a non-regular file: %s" % path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inject_plug(root, name="treeview.plug.js"):
    """Copy a vendored, hash-pinned plug into <root>/_plug/ — the directory
    tree for the Files screen. Same gate as the theme: only when editing is
    allowed (a read-only space is never mutated; those users get the page
    picker). Hardening (codex review 2026-08-21):
    - _plug must be a real directory INSIDE the realpath'd root (no symlink
      escape); the destination must be absent or a regular file.
    - No TOCTOU: the managed copy is linked into place with os.link, which
      fails atomically if anything appeared at dst in the meantime — a
      foreign file is never overwritten.
    Returns True when the managed plug is in place, False when skipped."""
    if not providers.editing_allowed():
        return False
    spec = PLUGS[name]
    if not _is_regular(spec["src"]) or _sha256(spec["src"]) != spec["sha256"]:
        raise RuntimeError("vendored plug %s missing or tampered" % name)
    real_root = os.path.realpath(root)
    pdir = os.path.join(real_root, "_plug")
    if os.path.lexists(pdir) and (os.path.islink(pdir) or not os.path.isdir(pdir)):
        raise RuntimeError("_plug exists but is not a plain directory; leaving it alone")
    os.makedirs(pdir, exist_ok=True)
    if os.path.realpath(pdir) != pdir:
        raise RuntimeError("_plug resolves outside the space root; leaving it alone")
    dst = os.path.join(pdir, name)
    if os.path.lexists(dst):
        if not _is_regular(dst):
            raise RuntimeError("%s is not a regular file; leaving it alone" % name)
        return _sha256(dst) == spec["sha256"]
    tmp = os.path.join(pdir, ".%s.sutra-tmp-%d" % (name, os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as out, open(spec["src"], "rb") as src:
            out.write(src.read())
        try:
            os.link(tmp, dst)          # atomic no-clobber: EEXIST if dst appeared
        except FileExistsError:
            return _is_regular(dst) and _sha256(dst) == spec["sha256"]
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return True


def _sb_env(readonly, port):
    env = dict(os.environ)
    env.update({
        "SB_HOSTNAME": "127.0.0.1",
        "SB_PORT": str(port),
        "SB_DISABLE_SERVICE_WORKER": "1",
        "SB_RUNTIME_API": "0",
        "SB_FS_WATCH": "off",
    })
    if readonly:
        env["SB_READ_ONLY"] = "1"
    else:
        env.pop("SB_READ_ONLY", None)
    return env


def _probe(port, want_readonly):
    """Startup probe (consult req 3, amended by PoC): ping + config coherence.

    Does NOT assert If-Match/412 — the 2.10.0 release build has no ETag
    support; asserting it would fail every launch."""
    base = "http://127.0.0.1:%d" % port
    body = urllib.request.urlopen(base + "/.ping", timeout=5).read()
    if body.strip() != b"OK":
        raise RuntimeError("ping failed: %r" % body[:40])
    cfg = json.load(urllib.request.urlopen(base + "/.config", timeout=5))
    if bool(cfg.get("readOnly")) != want_readonly:
        raise RuntimeError("readOnly mismatch: wanted %s got %s"
                           % (want_readonly, cfg.get("readOnly")))
    if cfg.get("disableServiceWorker") is not True:
        raise RuntimeError("service worker not disabled")
    return cfg


def status():
    proc = _state["proc"]
    running = proc is not None and proc.poll() is None
    return {
        "running": running,
        "port": _state["port"] if running else None,
        "root": _state["root"],
        "readonly": _state["readonly"],
        "version": SB_VERSION,
        "error": _state["error"],
        "inject_error": _state.get("inject_error"),
    }


def start(root):
    """Start (or return) the sidecar for `root`. The caller resolves which
    root to serve; the $HOME guard is re-checked here so this module stays
    safe even if a new call site forgets it."""
    if not providers.workdir_allowed(root):
        raise RuntimeError("root outside allowed tree")
    st = status()
    if st["running"] and _state["root"] == root:
        return st
    stop()
    readonly = not providers.editing_allowed()
    try:
        binary = ensure_binary()
        # Injection is best-effort: a bad _plug path or a tampered vendor file
        # must degrade to "no tree / default theme", never to a Files screen
        # that cannot start (codex review: do not wedge startup).
        _state["inject_error"] = None
        if not readonly:
            # Labels are literals, not step.__name__: reading an attribute off
            # the callable inside the handler is one more thing that can raise
            # while we are already handling a failure -- and that exception
            # escapes to the outer try, which is precisely the startup wedge
            # this loop exists to prevent.
            for label, step in (("theme", inject_theme), ("tree", inject_plug)):
                try:
                    step(root)
                except Exception as exc:  # noqa: BLE001
                    _state["inject_error"] = "%s: %s" % (label, exc)
        port = _stable_port(root)
        proc = subprocess.Popen(
            [binary, "--single", root],
            env=_sb_env(readonly, port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # killpg-able; no orphan on uvicorn reload
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the panel verbatim
        _state.update(proc=None, port=None, root=root, error=str(exc), readonly=readonly)
        return status()
    deadline = time.time() + 15
    last_err = None
    while time.time() < deadline:
        try:
            _probe(port, readonly)
            _state.update(proc=proc, port=port, root=root, error=None, readonly=readonly)
            return status()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if proc.poll() is not None:
                break
            time.sleep(0.4)
    proc.kill()
    _state.update(proc=None, port=None, root=root,
                  error="probe failed: %s" % last_err, readonly=readonly)
    return status()


def stop():
    proc = _state["proc"]
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    _state.update(proc=None, port=None)
