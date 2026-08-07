"""updates.py — check for, and install, the two things that can be out of date.

There are TWO components and they update by completely different mechanisms.
Conflating them is the mistake this module exists to prevent:

  DESKTOP APP   /Applications/Sutra.app. Released as a notarized DMG on GitHub.
                Updating means replacing the bundle, which a running app cannot
                do to itself. Squirrel is in the bundle only because Electron
                ships it; it is still not wired up. The auto-updater is the
                staging machinery below, driven by the Electron shell.

  PLUGIN        core@sutra under ~/.claude/plugins. Already updates itself once
                a day via hooks/sessionstart-auto-update.sh, applying to the
                NEXT session. This module exposes the same operation on demand
                so it is visible and forceable, not only silent and daily.

NOTHING IN THIS MODULE RUNS ON IMPORT OR ON BOOT. That has not changed, and it
is load-bearing for a reason that is easy to miss: this same FastAPI app is
what the CLI serves to a plain browser. A background poller started at import
would make every CLI user phone GitHub on launch, which is not what was asked
for and not a decision this module gets to make on their behalf.

  So the SCHEDULE lives in the Electron shell (main.js), which is the only
  caller that has an app to replace. Desktop auto-update was made MANDATORY by
  founder direction 2026-08-06; "mandatory" means the user cannot decline it,
  NOT that it happens to people who are not running the desktop app.

THE STATE MACHINE, because a deferred update outlives the process that staged
it and must survive a reboot:

  (none) --stage--> staged --arm--> installing --+--> (cleared, installed)
                      ^                          |
                      +-------- failed <---------+   (helper wrote why)

  `staged` means downloaded and verified, nothing armed. The user may defer
  from here as often as they like; cancelling is a DEFER, never a decline.
  `installing` is stamped BEFORE the helper is spawned and carries a lease, so
  a boot that finds a fresh `installing` record does not arm a second helper --
  which is how an update loop starts.

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
import time
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
        # What the updater actually does, in the place an operator reads to
        # find out. It used to say there was no background updater at all;
        # leaving that would have been the app lying about its own behaviour.
        "note": "The desktop app checks for updates in the background and "
                "installs them automatically. This button only makes it "
                "immediate.",
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
# Written by sutra-ui updates.py. Waits for the app to be GONE, then swaps the
# bundle. Everything checkable was checked before this ran; everything that can
# go stale between then and now is re-checked here, because from this point on
# there is no one to ask.
#
# Inputs arrive as environment variables, not positional arguments: this script
# runs unattended and an argument-order mistake is a silently wrong bundle.
set -uo pipefail
exec >>"$LOG" 2>&1
echo "[$(date)] installer start dmg=$DMG app=$APP wait_pid=$WAIT_PID relaunch=$RELAUNCH"

# Terminal status, written where the next launch can read it. The app must not
# have to INFER what happened here by comparing version numbers -- an install
# that succeeded while the panel read a stale version looks identical to one
# that failed, and guessing wrong throws away a good update.
result() {
  local ok="$1" stage="$2" err
  err="$(printf '%s' "${3:-}" | tr -d '\n\r"\\' | cut -c1-300)"
  printf '{"ok":%s,"stage":"%s","version":"%s","error":"%s","ts":%s}\n' \
    "$ok" "$stage" "$EXPECT_VERSION" "$err" "$(date +%s)" > "$RESULT.tmp" \
    && mv -f "$RESULT.tmp" "$RESULT"
}
die() { echo "FAIL($1): $2"; result false "$1" "$2"; exit 1; }

# The birth time of the pid we were told to wait on. A bare pid is not an
# identity: pids are recycled, and a recycled one that exits would tell us the
# app is gone while it is still running -- with the bundle open underneath us.
# `$1=$1` rebuilds the record with single spaces and no leading/trailing run,
# which is byte-for-byte what _proc_start() does in Python. These two strings
# are compared for equality across a language boundary; if they normalised
# differently, every update would abort as a phantom pid reuse.
starttime() { ps -o lstart= -p "$1" 2>/dev/null | awk '{$1=$1;print}'; }

# 1. wait for THAT process to end -- not merely for something with that pid to
#    end. A start-time change means the pid was reused; we then know nothing
#    about the app and must not touch it.
if [ -n "${WAIT_START:-}" ]; then
  now="$(starttime "$WAIT_PID")"
  if [ -n "$now" ] && [ "$now" != "$WAIT_START" ]; then
    die pid-reuse "pid $WAIT_PID is no longer the process that armed this update"
  fi
fi
for _ in $(seq 1 120); do
  kill -0 "$WAIT_PID" 2>/dev/null || break
  if [ -n "${WAIT_START:-}" ]; then
    now="$(starttime "$WAIT_PID")"
    [ -n "$now" ] && [ "$now" != "$WAIT_START" ] && die pid-reuse "pid recycled while waiting"
  fi
  sleep 1
done
kill -0 "$WAIT_PID" 2>/dev/null && die app-alive "app still running after 120s; $APP untouched"

# 2. the main process exiting is NOT the bundle being free. Electron leaves
#    helper, GPU and renderer processes executing out of the same .app, and
#    ditto-ing over a bundle whose binaries are still mapped is how you get a
#    half-replaced app that launches into nothing.
for _ in $(seq 1 60); do
  pgrep -f "$APP/Contents/MacOS/" >/dev/null 2>&1 || break
  sleep 1
done
pgrep -f "$APP/Contents/MacOS/" >/dev/null 2>&1 \
  && die procs-alive "processes are still running from $APP"

MNT="$(mktemp -d /tmp/sutra-mnt.XXXXXX)"
hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MNT" >/dev/null \
  || die mount "could not mount $DMG"
NEW="$MNT/Sutra.app"
cleanup() { hdiutil detach "$MNT" -quiet 2>/dev/null || true; rmdir "$MNT" 2>/dev/null || true; }
trap cleanup EXIT
[ -d "$NEW" ] || die contents "the disk image does not contain Sutra.app"

# 3. the bundle inside must verify too -- the DMG passing Gatekeeper is not
#    proof of what is inside it.
codesign --verify --deep --strict "$NEW" 2>/dev/null || die codesign "new bundle failed codesign"

# 4. "validly signed" is not "signed by us". Without this, a compromised
#    release or checksum could hand us a perfectly notarized app belonging to
#    somebody else and every earlier gate would pass it. The expectation is
#    CONTINUITY with the bundle being replaced, not a constant compiled in
#    here -- a constant would be wrong for ad-hoc dev builds and would rot the
#    day the signing identity legitimately changes.
NEW_TEAM="$(codesign -dv --verbose=4 "$NEW" 2>&1 | sed -n 's/^TeamIdentifier=//p' | head -1)"
[ "$NEW_TEAM" = "${EXPECT_TEAM:-}" ] \
  || die team "signed by team '${NEW_TEAM:-none}', expected '${EXPECT_TEAM:-none}'"
NEW_ID="$(plutil -extract CFBundleIdentifier raw -o - "$NEW/Contents/Info.plist" 2>/dev/null)"
[ "$NEW_ID" = "${EXPECT_BUNDLE_ID:-}" ] \
  || die bundle-id "bundle id '${NEW_ID:-none}', expected '${EXPECT_BUNDLE_ID:-none}'"
NEW_VER="$(plutil -extract CFBundleShortVersionString raw -o - "$NEW/Contents/Info.plist" 2>/dev/null)"
[ "$NEW_VER" = "$EXPECT_VERSION" ] \
  || die version "image contains $NEW_VER, but $EXPECT_VERSION was staged and verified"

# 5. swap. Copy BESIDE the old bundle and verify it there first, so the only
#    moment $APP does not exist is between two renames on the same volume.
#    RECOVER records that window: it is the breadcrumb for a crash landing
#    exactly inside it, which no amount of ordering can make impossible.
STAGE="${APP}.new-$$"
BAK="${APP}.old-$$"
rm -rf "$STAGE"
ditto "$NEW" "$STAGE" || { rm -rf "$STAGE"; die copy "could not copy the new bundle into place"; }
codesign --verify --deep --strict "$STAGE" 2>/dev/null \
  || { rm -rf "$STAGE"; die copy-verify "the copied bundle does not verify"; }

printf '{"app":"%s","backup":"%s","staged":"%s","ts":%s}\n' \
  "$APP" "$BAK" "$STAGE" "$(date +%s)" > "$RECOVER" 2>/dev/null
if ! mv "$APP" "$BAK"; then
  rm -f "$RECOVER"; rm -rf "$STAGE"; die swap "could not move the old bundle aside"
fi
if ! mv "$STAGE" "$APP"; then
  mv "$BAK" "$APP" 2>/dev/null
  rm -f "$RECOVER"; rm -rf "$STAGE"; die swap "could not move the new bundle into place"
fi
rm -f "$RECOVER"
rm -rf "$BAK"
result true installed ""
echo "[$(date)] installed $EXPECT_VERSION"

# 6. relaunch ONLY when the update drove the exit. If the user chose Quit and
#    we applied on the way out, reopening the app countermands them.
if [ "$RELAUNCH" = "1" ]; then
  echo "[$(date)] relaunching"
  open -a "$APP"
fi
"""


def _proc_start(pid):
    """The birth time of `pid`, as the string the installer will compare against.
    Empty when the process does not exist. Pairing this with the pid is what
    makes 'wait for it to exit' mean a specific process rather than a number."""
    try:
        p = _run(["ps", "-o", "lstart=", "-p", str(int(pid))], timeout=10)
    except (ValueError, OSError, subprocess.SubprocessError):
        return ""
    return " ".join((p.stdout or "").split())


def _bundle_identity(app):
    """(team, bundle_id) of an installed bundle, for continuity checking."""
    team = ""
    try:
        p = _run(["codesign", "-dv", "--verbose=4", str(app)], timeout=30)
        for line in ((p.stderr or "") + (p.stdout or "")).splitlines():
            if line.startswith("TeamIdentifier="):
                team = line.split("=", 1)[1].strip()
                break
    except (OSError, subprocess.SubprocessError):
        pass
    if team == "not set":
        team = "not set"
    bid = ""
    try:
        with open(Path(app) / "Contents" / "Info.plist", "rb") as fh:
            bid = plistlib.load(fh).get("CFBundleIdentifier") or ""
    except (OSError, ValueError):
        pass
    return team, bid


def install_desktop(dmg, app_path=None, wait_pid=None, wait_start=None,
                    relaunch=False, version=None, result_path=None,
                    recover_path=None):
    """Spawn the detached installer. Returns immediately; the swap happens once
    the app named by `wait_pid` is gone.

    The caller is expected to quit the app. This does NOT kill it: a backend
    that force-quits the UI it is serving would look like a crash, and the
    helper already refuses to touch anything while the app is alive.

    `wait_pid` defaults to getppid() only to keep the old manual call working.
    That default is WRONG for the desktop shell and the shell must not rely on
    it: main.js has a path where it attaches to a backend it did not spawn, and
    getppid() is then a shell -- whose exit would release the helper while Sutra
    is still running. The shell passes its own pid, with its start time.
    """
    # The emptiness check is separate and comes FIRST because Path("") is
    # PosixPath("."), which is a real directory and passes every test below it.
    # In a source checkout app_bundle() is None, so the old `Path(x or "")`
    # resolved the target to the CURRENT WORKING DIRECTORY -- and the helper
    # would have moved it aside and copied a .app over it.
    target = app_path or app_bundle()
    if not target or not str(target).strip():
        raise RuntimeError("no installed .app to replace")
    app = Path(target)
    if not app.is_dir() or app.suffix != ".app":
        raise RuntimeError("%s is not an installed .app bundle" % app)
    if not os.access(app.parent, os.W_OK):
        raise RuntimeError("%s is not writable by this user -- install the DMG "
                           "manually" % app.parent)
    if not Path(dmg).is_file():
        raise RuntimeError("no such disk image: %s" % dmg)

    pid = int(wait_pid) if wait_pid else os.getppid()
    start = wait_start if wait_start is not None else _proc_start(pid)
    team, bundle_id = _bundle_identity(app)

    d = Path(tempfile.mkdtemp(prefix="sutra-installer-"))
    script = d / "install.sh"
    log = d / "install.log"
    script.write_text(_INSTALLER, encoding="utf-8")
    script.chmod(0o755)

    env = dict(os.environ)
    env.update({
        "DMG": str(dmg), "APP": str(app), "LOG": str(log),
        "WAIT_PID": str(pid), "WAIT_START": start or "",
        "RELAUNCH": "1" if relaunch else "0",
        "EXPECT_VERSION": str(version or ""),
        "EXPECT_TEAM": team, "EXPECT_BUNDLE_ID": bundle_id,
        "RESULT": str(result_path or (d / "install-result.json")),
        "RECOVER": str(recover_path or (d / "recover.json")),
    })
    subprocess.Popen(
        ["/bin/bash", str(script)], env=env,
        start_new_session=True,          # survives this process being torn down
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"scheduled": True, "log": str(log), "app": str(app),
            "wait_pid": pid, "relaunch": bool(relaunch),
            "note": "Quit Sutra to let the update apply."
                    + (" It reopens itself." if relaunch else "")}


# ----------------------------------------------------- staging / pending ----
# Everything below exists so that an update can be downloaded NOW and applied
# LATER -- possibly days later, across a reboot, by a process that has not been
# started yet. That is the whole difference between an update button and an
# auto-updater, and it is all state management.

MAX_APPLY_ATTEMPTS = 2      # after this many tries at one version, stop trying
ARM_LEASE_SECONDS = 300     # how long a spawned helper is presumed to be alive


def stage_dir():
    """The durable staging directory, created 0700 and proven not to be a
    symlink.

    NOT tempfile.mkdtemp: /tmp is periodically purged, and an update the user
    deferred on Friday has to still be there on Monday. Durability is the point,
    but it is also the cost -- a file that sits in a writable place for days is
    a file someone can swap, so the directory is locked down and every read out
    of it is re-verified rather than trusted.
    """
    d = Path(os.path.expanduser(os.environ.get(
        "SUTRA_UPDATE_DIR", "~/Library/Application Support/Sutra/updates")))
    if d.is_symlink():
        raise RuntimeError("%s is a symlink; refusing to stage there" % d)
    d.mkdir(parents=True, exist_ok=True)
    # Ownership before permissions: chmod on a directory belonging to somebody
    # else either fails or, worse, succeeds and tells us nothing.
    if d.stat().st_uid != os.getuid():
        raise RuntimeError("%s is not owned by this user" % d)
    try:
        os.chmod(d, 0o700)      # repair rather than refuse -- it is ours to fix
    except OSError:
        pass
    if d.stat().st_mode & 0o077:
        raise RuntimeError("%s is accessible to other users and could not be "
                           "locked down" % d)
    return d


def _pending_path():
    return stage_dir() / "pending-update.json"


def _result_path():
    return stage_dir() / "install-result.json"


def _recover_path():
    return stage_dir() / "recover.json"


def _read_json(path):
    try:
        if Path(path).is_symlink():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path, obj):
    """Atomic, so a crash mid-write cannot leave a half-parsed manifest that
    makes the next launch throw away a perfectly good staged update."""
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def read_pending():
    return _read_json(_pending_path())


def clear_pending(also_remove_dmg=True):
    man = read_pending()
    if also_remove_dmg and man and man.get("dmg"):
        try:
            p = Path(man["dmg"])
            if p.is_file() and not p.is_symlink():
                p.unlink()
        except OSError:
            pass
    for p in (_pending_path(), _result_path()):
        try:
            Path(p).unlink()
        except OSError:
            pass
    return man


def _verify_staged(man, recheck_online=True):
    """Prove the staged image is still the one that was verified at download.

    The local digest comparison is a CORRUPTION check and nothing more: the
    manifest and the image sit in the same directory, so anyone able to swap one
    can rewrite the other. The security check is the re-fetch of the digest
    PUBLISHED beside the release, which is why its absence is reported rather
    than silently downgraded.
    """
    dmg = Path(man.get("dmg") or "")
    if not dmg.is_file() or dmg.is_symlink():
        raise RuntimeError("the staged disk image is gone")
    root = stage_dir().resolve()
    if root not in dmg.resolve().parents:
        raise RuntimeError("the staged image is not inside the staging directory")
    got = _sha256(dmg)
    if man.get("sha256") and got != man["sha256"]:
        raise RuntimeError("the staged image changed on disk since it was verified")

    published = None
    if recheck_online and man.get("sha256_url"):
        try:
            req = urllib.request.Request(man["sha256_url"],
                                         headers={"User-Agent": "sutra-ui-updater"})
            with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
                published = r.read().decode("utf-8").split()[0].strip()
        except (urllib.error.URLError, OSError, IndexError, ValueError):
            published = None
    if published and published != got:
        raise RuntimeError("the staged image no longer matches the published "
                           "checksum for this release")
    return {"sha256": got, "reverified_online": bool(published)}


def stage_desktop():
    """Download and verify the newest desktop release, arming nothing.

    Split from arming deliberately. While these were one call there was no
    moment at which an update was ready but not yet scheduled -- which is the
    only moment a prompt can happen in.
    """
    state = desktop_state()
    if not state.get("managed"):
        return {"staged": False, "reason": state.get("reason", "not an installed app")}
    if state.get("error"):
        raise RuntimeError(state["error"])
    if not state.get("update_available"):
        return {"staged": False, "reason": "already up to date",
                "installed": state.get("installed")}

    version = state.get("latest")
    existing = read_pending()
    if existing and existing.get("version") == version and existing.get("dmg"):
        try:
            _verify_staged(existing, recheck_online=False)
            return {"staged": True, "already": True, "version": version,
                    "state": existing.get("state")}
        except RuntimeError:
            clear_pending()          # unusable; fall through and fetch it again

    latest = _latest_desktop()
    got = download_and_verify(dest_dir=str(stage_dir()))
    _write_json(_pending_path(), {
        "state": "staged",
        "version": got.get("version") or version,
        "dmg": got["dmg"],
        "sha256": _sha256(got["dmg"]),
        "sha256_url": latest.get("sha256_url"),
        "asset": latest.get("asset"),
        "staged_at": int(time.time()),
        "armed_at": None,
        "lease_until": None,
        # Three counters, not one. A helper that never spawned and a helper that
        # ran and broke the install are different failures, and collapsing them
        # lets two bookkeeping hiccups permanently suppress a good release.
        "arm_attempts": 0,
        "spawn_failures": 0,
        "install_failures": 0,
        "last_error": None,
    })
    try:
        _result_path().unlink()
    except OSError:
        pass
    return {"staged": True, "version": got.get("version"), "dmg": got["dmg"]}


def arm_desktop(wait_pid, wait_start=None, relaunch=False):
    """Schedule the swap for after the app named by `wait_pid` exits.

    Idempotent and single-flight. Two callers can plausibly reach this at once
    -- the countdown firing while the user is already quitting -- and two
    helpers racing to replace the same bundle is exactly the situation the rest
    of this file is written to avoid.
    """
    man = read_pending()
    if not man:
        raise RuntimeError("there is no staged update to install")
    now = int(time.time())
    if man.get("state") == "installing" and (man.get("lease_until") or 0) > now:
        return {"scheduled": True, "already": True, "version": man.get("version"),
                "note": "an installer for this version is already waiting"}
    if man.get("state") == "failed" and man.get("install_failures", 0) >= MAX_APPLY_ATTEMPTS:
        raise RuntimeError("this update failed to install %d times and will not "
                           "be retried automatically: %s"
                           % (man["install_failures"], man.get("last_error") or "unknown"))

    proof = _verify_staged(man)

    # Stamped BEFORE the spawn, so a crash between here and the helper starting
    # is still visible as an attempt at the next launch.
    man.update({"state": "installing", "armed_at": now,
                "lease_until": now + ARM_LEASE_SECONDS,
                "arm_attempts": int(man.get("arm_attempts", 0)) + 1,
                "relaunch": bool(relaunch)})
    _write_json(_pending_path(), man)

    try:
        sched = install_desktop(
            man["dmg"], wait_pid=wait_pid, wait_start=wait_start,
            relaunch=relaunch, version=man.get("version"),
            result_path=str(_result_path()), recover_path=str(_recover_path()))
    except (RuntimeError, OSError) as exc:
        man.update({"state": "staged", "lease_until": None,
                    "spawn_failures": int(man.get("spawn_failures", 0)) + 1,
                    "last_error": "could not start the installer: %s" % exc})
        _write_json(_pending_path(), man)
        raise RuntimeError("could not start the installer: %s" % exc)

    sched.update({"version": man.get("version"),
                  "reverified_online": proof["reverified_online"]})
    return sched


def resolve_pending(installed_version=None):
    """Called at launch, before the window opens. Decides what the last attempt
    did and what this launch owes the user.

    The helper's own status file is believed over any comparison of version
    numbers. The shell can attach to a backend it did not start, so a version
    read back through the API can belong to the PREVIOUS install -- and
    concluding "still old, therefore it failed" would throw away an update that
    actually landed.
    """
    man = read_pending()
    if not man:
        return {"pending": False}
    version = man.get("version")
    now = int(time.time())
    res = _read_json(_result_path())

    if res and res.get("version") == version:
        if res.get("ok"):
            clear_pending()
            return {"pending": False, "applied": version}
        man["install_failures"] = int(man.get("install_failures", 0)) + 1
        man["last_error"] = res.get("error") or ("failed at %s" % res.get("stage"))
        man["state"] = "failed"
        if man["install_failures"] >= MAX_APPLY_ATTEMPTS:
            clear_pending()
            return {"pending": False, "gave_up": True, "version": version,
                    "error": man["last_error"]}
        man["state"] = "staged"
        man["lease_until"] = None
        _write_json(_pending_path(), man)
        return {"pending": True, "action": "arm", "version": version,
                "retry_after_failure": man["last_error"], "dmg": man.get("dmg")}

    if installed_version and _ver_tuple(installed_version) >= _ver_tuple(version):
        clear_pending()
        return {"pending": False, "applied": version}

    if man.get("state") == "installing":
        if (man.get("lease_until") or 0) > now:
            # A helper is plausibly still waiting. Arming a second one here is
            # how a boot loop starts.
            return {"pending": True, "action": "wait", "version": version}
        man["install_failures"] = int(man.get("install_failures", 0)) + 1
        man["last_error"] = "the installer never reported back"
        if man["install_failures"] >= MAX_APPLY_ATTEMPTS:
            man["state"] = "failed"
            _write_json(_pending_path(), man)
            return {"pending": True, "action": "manual", "version": version,
                    "error": man["last_error"]}
        man["state"] = "staged"
        man["lease_until"] = None
        _write_json(_pending_path(), man)

    if man.get("state") == "failed":
        return {"pending": True, "action": "manual", "version": version,
                "error": man.get("last_error")}
    return {"pending": True, "action": "arm", "version": version,
            "dmg": man.get("dmg")}


def pending_state():
    """What the panel needs to draw the banner. No network, so it is safe to
    poll -- which is the only reason the panel is allowed to poll it."""
    try:
        man = read_pending()
    except RuntimeError as exc:
        return {"pending": False, "error": str(exc)}
    if not man:
        return {"pending": False}
    out = {"pending": True, "version": man.get("version"),
           "state": man.get("state"), "staged_at": man.get("staged_at"),
           "install_failures": man.get("install_failures", 0),
           "error": man.get("last_error")}
    rec = _read_json(_recover_path())
    if rec:
        # Only ever present if a swap died between two renames. Surfaced rather
        # than cleaned up: it names the backup a human would restore from.
        out["interrupted_swap"] = rec
    return out


def all_state():
    return {"desktop": desktop_state(), "plugin": plugin_state(),
            "staged": pending_state()}
