"""updates.py — check for, and install, the two things that can be out of date.

There are TWO components and they update by completely different mechanisms.
Conflating them is the mistake this module exists to prevent:

  DESKTOP APP   /Applications/Sutra.app. Has NO auto-updater -- Squirrel is in
                the bundle only because Electron ships it, nothing wires it up.
                Released as a notarized DMG on GitHub. Updating means replacing
                the bundle, which a running app cannot do to itself.

  PLUGIN        core@sutra under ~/.claude/plugins. Already updates itself once
                a day via hooks/sessionstart-auto-update.sh, applying to the
                NEXT session. This module exposes the same operation on demand
                so it is visible and forceable, not only silent and daily.

CHECKING IS READ-ONLY AND NEVER AUTOMATIC HERE. Nothing in this module runs on
import or on boot; the panel asks. A desktop app that phones home on every
launch is a different product decision from one that has an update button, and
this is the second.

INSTALLING THE DESKTOP UPDATE, and why it looks the way it does:

  A bundle cannot overwrite itself while its own process is running. So the
  install is split -- this process downloads and VERIFIES, then hands a
  detached helper the job of waiting for the app to exit and swapping the
  bundle. Every gate that can be checked is checked BEFORE anything is
  replaced, because the helper runs unattended:

    1. sha256 of the download == the .sha256 published beside it
    2. spctl accepts the DMG          (notarized Developer ID, not just signed)
    3. codesign --verify the .app inside the mounted image
    4. only then: swap, and keep the old bundle until the new one is in place

  A failure at any gate leaves /Applications untouched and reports why.
"""
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# Where each component comes from. Overridable so a fork or a staging channel
# can be pointed somewhere else without editing code.
DESKTOP_REPO = os.environ.get("SUTRA_UI_DESKTOP_REPO", "tchandrakar/sutra")
PLUGIN_REPO = os.environ.get("SUTRA_UI_PLUGIN_REPO", "sankalpasawa/sutra")
NET_TIMEOUT = 15

# The desktop release tag is `v<version>-desktop`; the asset is per-arch.
_TAG_RE = re.compile(r"^v?(\d+(?:\.\d+)*)")


def _ver_tuple(s):
    """'2.67.1' -> (2, 67, 1). Unparseable -> (), which sorts below everything,
    so an unreadable version can never look NEWER than a real one."""
    m = _TAG_RE.match(str(s or "").strip())
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).split("."))


def _newer(latest, current):
    lt, ct = _ver_tuple(latest), _ver_tuple(current)
    return bool(lt) and bool(ct) and lt > ct


def _get_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "sutra-ui-updater",
    })
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _arch():
    """The DMG asset suffix for this machine. Matches make-dmg.sh's spelling:
    uname says arm64/x86_64 and that is what the filenames use."""
    m = (os.uname().machine or "").lower()
    return "arm64" if m in ("arm64", "aarch64") else "x86_64"


# ------------------------------------------------------------- desktop ------

def app_bundle():
    """The .app this backend is running out of, or None in a dev checkout.

    Walks up from this file looking for Contents/Info.plist. The bundled layout
    is Sutra.app/Contents/Resources/payload/plugin/sutra-ui, so the answer is
    four levels up -- but the walk is written as a search rather than a fixed
    number of parents, because a fixed count silently returns the wrong
    directory the moment the payload layout changes.
    """
    here = Path(__file__).resolve()
    for p in here.parents:
        if p.suffix == ".app" and (p / "Contents" / "Info.plist").is_file():
            return p
    return None


def _installed_desktop_version():
    app = app_bundle()
    if not app:
        return None
    try:
        with open(app / "Contents" / "Info.plist", "rb") as fh:
            return plistlib.load(fh).get("CFBundleShortVersionString")
    except (OSError, ValueError):
        return None


def _latest_desktop():
    """The newest desktop release, or an {'error': ...}. Never raises."""
    try:
        rel = _get_json("https://api.github.com/repos/%s/releases/latest" % DESKTOP_REPO)
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return {"error": "could not reach GitHub: %s" % exc}
    tag = rel.get("tag_name") or ""
    version = _TAG_RE.match(tag).group(1) if _TAG_RE.match(tag) else None
    want = "Sutra-%s.dmg" % _arch()
    assets = {a.get("name"): a for a in (rel.get("assets") or [])}
    dmg = assets.get(want)
    return {
        "version": version,
        "tag": tag,
        "url": rel.get("html_url"),
        "asset": want,
        "download_url": (dmg or {}).get("browser_download_url"),
        "size": (dmg or {}).get("size"),
        "sha256_url": (assets.get(want + ".sha256") or {}).get("browser_download_url"),
        # Stated rather than assumed: a release without an asset for THIS arch
        # is not an update this machine can take.
        "error": None if dmg else "release %s has no %s asset" % (tag or "?", want),
    }


def desktop_state():
    installed = _installed_desktop_version()
    if installed is None:
        return {
            "component": "desktop",
            "managed": False,
            "installed": None,
            "reason": "not running from an installed .app -- this is a source "
                      "checkout, so there is nothing for an updater to replace",
        }
    latest = _latest_desktop()
    return {
        "component": "desktop",
        "managed": True,
        "installed": installed,
        "app_path": str(app_bundle()),
        "arch": _arch(),
        "latest": latest.get("version"),
        "release_url": latest.get("url"),
        "asset": latest.get("asset"),
        "size": latest.get("size"),
        "update_available": _newer(latest.get("version"), installed),
        "error": latest.get("error"),
        # No auto-update exists. Say so where the operator can read it, rather
        # than letting them assume a desktop app keeps itself current.
        "note": "The desktop app has no background updater. It is checked and "
                "installed only when you ask.",
    }


# -------------------------------------------------------------- plugin ------

def _plugin_cache_root():
    return Path(os.path.expanduser(os.environ.get(
        "SUTRA_CACHE_ROOT", "~/.claude/plugins/cache/sutra/core")))


def _installed_plugin_version():
    """Highest version directory present. Comparing DIRECTORIES rather than a
    manifest is deliberate and matches sessionstart-auto-update.sh: an update
    lands as a new cache dir, so the manifest under the old root still reads the
    old number."""
    root = _plugin_cache_root()
    if not root.is_dir():
        return None
    vers = []
    try:
        for d in os.listdir(root):
            if _ver_tuple(d):
                vers.append(d)
    except OSError:
        return None
    return max(vers, key=_ver_tuple) if vers else None


def _latest_plugin():
    """The version on the marketplace's default branch."""
    url = ("https://raw.githubusercontent.com/%s/main/marketplace/plugin/"
           ".claude-plugin/plugin.json" % PLUGIN_REPO)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sutra-ui-updater"})
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8")).get("version"), None
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return None, "could not reach GitHub: %s" % exc


def plugin_state():
    installed = _installed_plugin_version()
    latest, err = _latest_plugin()
    return {
        "component": "plugin",
        "managed": shutil.which("claude") is not None,
        "installed": installed,
        "latest": latest,
        "update_available": _newer(latest, installed),
        "error": err if err else (
            None if shutil.which("claude") else
            "the `claude` CLI is not on PATH, so the plugin cannot be updated "
            "from here"),
        "cache_root": str(_plugin_cache_root()),
        # This one DOES update on its own; the button only makes it immediate.
        "note": "The plugin already updates itself once a day at session start, "
                "applying to the next session. Installing here just does it now.",
    }


def install_plugin():
    """Run the same two commands the daily hook runs, and report the move."""
    if not shutil.which("claude"):
        raise RuntimeError("the `claude` CLI is not on PATH")
    before = _installed_plugin_version()
    out = []
    for cmd in (["claude", "plugin", "marketplace", "update", "sutra"],
                ["claude", "plugin", "update", "core@sutra"]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            out.append({"cmd": " ".join(cmd), "code": p.returncode,
                        "out": (p.stdout or "")[-2000:],
                        "err": (p.stderr or "")[-2000:]})
        except (OSError, subprocess.SubprocessError) as exc:
            out.append({"cmd": " ".join(cmd), "code": -1, "out": "", "err": str(exc)})
    after = _installed_plugin_version()
    return {
        "before": before,
        "after": after,
        "changed": bool(after and after != before),
        "steps": out,
        # The running session already loaded the old version -- the same caveat
        # the daily hook prints. Claiming otherwise would be a lie the operator
        # discovers later.
        "note": ("Updated to %s. It applies to the NEXT Claude Code session, "
                 "not the one already running." % after) if after and after != before
                else "Already current.",
    }


# ------------------------------------------------------ desktop install -----

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def download_and_verify(dest_dir=None):
    """Fetch the DMG for this arch and prove it before anything is replaced.

    Returns {"dmg": path, "version": ...}. Raises RuntimeError naming the gate
    that failed -- an update that cannot be verified is not installed, and the
    reason is not swallowed.
    """
    latest = _latest_desktop()
    if latest.get("error"):
        raise RuntimeError(latest["error"])
    url = latest.get("download_url")
    if not url:
        raise RuntimeError("the latest release has no downloadable asset for this Mac")

    d = Path(dest_dir or tempfile.mkdtemp(prefix="sutra-update-"))
    d.mkdir(parents=True, exist_ok=True)
    dmg = d / latest["asset"]

    req = urllib.request.Request(url, headers={"User-Agent": "sutra-ui-updater"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r, open(dmg, "wb") as fh:
            shutil.copyfileobj(r, fh)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError("download failed: %s" % exc)

    # GATE 1 -- checksum, against the file published beside the DMG.
    if latest.get("sha256_url"):
        try:
            req = urllib.request.Request(latest["sha256_url"],
                                         headers={"User-Agent": "sutra-ui-updater"})
            with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
                want = r.read().decode("utf-8").split()[0].strip()
        except (urllib.error.URLError, OSError, IndexError):
            want = None
        if want:
            got = _sha256(dmg)
            if got != want:
                raise RuntimeError("checksum mismatch: published %s, downloaded %s"
                                   % (want[:16], got[:16]))

    # GATE 2 -- Gatekeeper. Signed is not enough; this must be NOTARIZED, which
    # is what `spctl` reports and what a stranger's Mac will demand.
    p = _run(["spctl", "-a", "-t", "open", "--context",
              "context:primary-signature", "-v", str(dmg)])
    if p.returncode != 0:
        raise RuntimeError("the downloaded image is not accepted by Gatekeeper: %s"
                           % (p.stderr or p.stdout or "").strip()[:300])

    return {"dmg": str(dmg), "version": latest.get("version"), "dir": str(d)}


_INSTALLER = r"""#!/bin/bash
# Written by sutra-ui updates.py. Waits for the running app to exit, then swaps
# the bundle. Everything verifiable was verified BEFORE this ran.
set -uo pipefail
DMG="$1"; APP="$2"; PPID_WAIT="$3"; LOG="$4"
exec >>"$LOG" 2>&1
echo "[$(date)] installer start dmg=$DMG app=$APP wait_pid=$PPID_WAIT"

# 1. wait for the app to quit (bounded -- never hang forever holding a mount)
for _ in $(seq 1 120); do
  kill -0 "$PPID_WAIT" 2>/dev/null || break
  sleep 1
done
if kill -0 "$PPID_WAIT" 2>/dev/null; then
  echo "app still running after 120s; aborting without touching $APP"; exit 1
fi

MNT="$(mktemp -d /tmp/sutra-mnt.XXXXXX)"
hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MNT" || { echo "mount failed"; exit 1; }
NEW="$MNT/Sutra.app"
cleanup() { hdiutil detach "$MNT" -quiet 2>/dev/null || true; rmdir "$MNT" 2>/dev/null || true; }
trap cleanup EXIT

# 2. the bundle inside must verify too -- the DMG passing is not proof of it
codesign --verify --deep --strict "$NEW" || { echo "new bundle failed codesign"; exit 1; }

# 3. swap, keeping the old one until the new is in place
BAK="${APP}.old-$$"
mv "$APP" "$BAK" || { echo "could not move old bundle"; exit 1; }
if ! ditto "$NEW" "$APP"; then
  echo "copy failed; restoring previous bundle"
  rm -rf "$APP"; mv "$BAK" "$APP"; exit 1
fi
rm -rf "$BAK"
echo "[$(date)] installed; relaunching"
open -a "$APP"
"""


def install_desktop(dmg, app_path=None):
    """Spawn the detached installer. Returns immediately; the swap happens after
    this process's app quits.

    The caller is expected to quit the app. This does NOT kill it: a backend
    that force-quits the UI it is serving would look like a crash, and the
    helper already refuses to touch anything while the app is alive.
    """
    app = Path(app_path or (app_bundle() or ""))
    if not app or not app.is_dir():
        raise RuntimeError("no installed .app to replace")
    if not os.access(app.parent, os.W_OK):
        raise RuntimeError("%s is not writable by this user -- install the DMG "
                           "manually" % app.parent)
    if not Path(dmg).is_file():
        raise RuntimeError("no such disk image: %s" % dmg)

    d = Path(tempfile.mkdtemp(prefix="sutra-installer-"))
    script = d / "install.sh"
    log = d / "install.log"
    script.write_text(_INSTALLER, encoding="utf-8")
    script.chmod(0o755)

    subprocess.Popen(
        ["/bin/bash", str(script), str(dmg), str(app), str(os.getppid()), str(log)],
        start_new_session=True,          # survives this process being torn down
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"scheduled": True, "log": str(log), "app": str(app),
            "note": "Quit Sutra to let the update apply; it reopens itself."}


def all_state():
    return {"desktop": desktop_state(), "plugin": plugin_state()}
