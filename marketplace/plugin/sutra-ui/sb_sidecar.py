"""SilverBullet sidecar — the Files screen's engine (S1, research doc §12).

Runs the MIT-licensed SilverBullet server binary as a supervised loopback
process and points it at the panel's workdir. The panel embeds the SB client
in an iframe; this module owns lifecycle, hardening, and the startup probe.

Design decisions (dual consult 2026-08-21, PoC atom a-78660f98-06):
- FastAPI owns the sidecar (policy lives next to the file APIs); Electron
  kills the whole runtime tree on exit, so orphans die with the app.
- Read-only follows the SAME out-of-band gate as /api/fs/write: without
  SUTRA_UI_ALLOW_EDIT=1 the sidecar runs SB_READ_ONLY=1 (PoC: PUT -> 403)
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
import platform
import signal
import socket
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
        # Pinned at packaging time by bundle-runtime.sh; dev download on this
        # arch fails closed until the hash is recorded there.
        "sha256": os.environ.get("SUTRA_SB_SHA256_X86_64", ""),
    },
}

THEME_MARKER = "<!-- sutra-managed: theme v1 -->"
THEME_MD = THEME_MARKER + """
```space-style
html {
  --root-background-color: #FAFAF7;
  --root-color: #1A1714;
  --ui-accent-color: #B8945F;
  --ui-font: 'Inter', -apple-system, sans-serif;
  --editor-font: 'Inter', -apple-system, sans-serif;
  --top-background-color: #FFFFFF;
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


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def inject_theme(root):
    """Marker-fenced, only-if-absent, and only when editing is allowed."""
    if not providers.editing_allowed():
        return False
    path = os.path.join(root, "THEME.md")
    if os.path.exists(path):
        # Never overwrite a file we don't own outright.
        head = open(path, "r", encoding="utf-8", errors="replace").read(len(THEME_MARKER))
        return head == THEME_MARKER
    tmp = path + ".sutra-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(THEME_MD)
    os.replace(tmp, path)
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
        if not readonly:
            inject_theme(root)
        port = _free_port()
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
