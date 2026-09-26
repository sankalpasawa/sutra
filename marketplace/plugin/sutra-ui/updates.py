"""updates.py — check for, and install, the two things that can be out of date.

There are TWO components and they update by completely different mechanisms.
Conflating them is the mistake this module exists to prevent:

  DESKTOP APP   /Applications/Sutra.app. Released as a notarized DMG on GitHub.
                Updating means replacing the bundle, which a running app cannot
                do to itself. Squirrel is in the bundle only because Electron
                ships it; it is still not wired up. The auto-updater is the
                staging machinery below, driven by the Electron shell.

                On Windows the app is the per-user NSIS install (Sutra.exe),
                released as Sutra-Setup-x64.exe. Same staging machinery; the
                swap is that installer, run silently by a detached PowerShell
                helper once the app has exited. Before 2026-09-25 this module
                knew only the .app, so a Windows install reported itself
                unmanaged and the Settings row said "up to date" forever.

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

  On Windows gates 2 and 3 do not exist yet (the installer is not
  Authenticode-signed), so gate 1 is REQUIRED there rather than best-effort.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import platform
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
"""The update CHANNEL is an ownership decision, not a mirror detail (founder,
2026-08-24): sankalpasawa/sutra is the PRIMARY repo — releases are built,
signed and published there. tchandrakar/sutra published one final migration
bridge (the release that carried this default) and must never again publish a
higher desktop release, or users still on the old feed would be trapped on it
(codex consult 2026-08-24). Pinned by test_update_channel.py."""
DESKTOP_REPO = os.environ.get("SUTRA_UI_DESKTOP_REPO", "sankalpasawa/sutra")
PLUGIN_REPO = os.environ.get("SUTRA_UI_PLUGIN_REPO", "sankalpasawa/sutra")
NET_TIMEOUT = 15
# Where the release API and the deterministic per-tag download URLs live. The
# defaults are GitHub; a test harness points both at a local server so the
# whole lane -- check, stage, arm, helper swap -- runs against fixture releases
# without a network. Production never sets these.
RELEASE_API = os.environ.get("SUTRA_UI_RELEASE_API", "https://api.github.com").rstrip("/")
RELEASE_DOWNLOAD = os.environ.get("SUTRA_UI_RELEASE_DOWNLOAD", "https://github.com").rstrip("/")
# The delta lane (updates_delta.py) is on by default and can only ever fall
# back to the full image; SUTRA_UPDATE_DELTA=0 forces the full image.
DELTA_ENABLED = os.environ.get("SUTRA_UPDATE_DELTA", "1") != "0"

_IS_WIN = sys.platform == "win32"
_HERE = Path(os.path.abspath(__file__))
# electron-builder-win.yml nsis.artifactName. x64 only; the portable
# Sutra-x64.exe is never an update target (it cannot replace itself).
WIN_SETUP_ASSET = "Sutra-Setup-x64.exe"

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
    uname says arm64/x86_64 and that is what the filenames use. Read through
    platform.machine(): os.uname does not exist on Windows."""
    m = (platform.machine() or "").lower()
    return "arm64" if m in ("arm64", "aarch64") else "x86_64"


def _desktop_asset():
    return WIN_SETUP_ASSET if _IS_WIN else "Sutra-%s.dmg" % _arch()


# ------------------------------------------------------------- desktop ------

def app_bundle():
    """The .app this backend is running out of, or None in a dev checkout.

    Walks up from this file looking for Contents/Info.plist. The bundled layout
    is Sutra.app/Contents/Resources/payload/plugin/sutra-ui, so the answer is
    four levels up -- but the walk is written as a search rather than a fixed
    number of parents, because a fixed count silently returns the wrong
    directory the moment the payload layout changes.
    """
    # Test seam: the end-to-end harness runs this module from a checkout but
    # needs it to believe it lives inside a fixture bundle. Never set in
    # production; a bundled app ignores it because the walk below wins when
    # the override is absent.
    forced = os.environ.get("SUTRA_UI_APP_BUNDLE")
    if forced:
        p = Path(forced)
        return p if p.suffix == ".app" and (p / "Contents" / "Info.plist").is_file() else None
    here = Path(__file__).resolve()
    for p in here.parents:
        if p.suffix == ".app" and (p / "Contents" / "Info.plist").is_file():
            return p
    return None


def win_install():
    """Windows: the folder of the installed app this backend belongs to, or None.

    There is no Info.plist to walk up to, so the shell names its own exe
    (SUTRA_DESKTOP_EXE, main.js winPythonEnv) and the answer is that exe's
    folder -- but only if this file really lives under it. A source checkout
    that inherited the variable must not look installed.
    """
    exe = os.environ.get("SUTRA_DESKTOP_EXE") or ""
    if not exe or not os.path.isfile(exe):
        return None
    root = Path(exe).parent
    try:
        if root.resolve() in _HERE.resolve().parents:
            return root
    except OSError:
        pass
    return None


def _installed_app():
    return win_install() if _IS_WIN else app_bundle()


def _installed_desktop_version():
    if _IS_WIN:
        # The shell knows its own version for certain and names it; believed
        # only from inside an install.
        return (os.environ.get("SUTRA_DESKTOP_VERSION") or None) if win_install() else None
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
        rel = _get_json("%s/repos/%s/releases/latest" % (RELEASE_API, DESKTOP_REPO))
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return {"error": "could not reach GitHub: %s" % exc}
    tag = rel.get("tag_name") or ""
    version = _TAG_RE.match(tag).group(1) if _TAG_RE.match(tag) else None
    want = _desktop_asset()
    assets = {a.get("name"): a for a in (rel.get("assets") or [])}
    dmg = assets.get(want)
    # The delta lane's two assets. Both optional: a release without them is
    # simply a full-image release, which is what every release was before.
    # macOS bundles only: the x86_64 pack is a Mac's, never a Windows install's.
    man_name = "Sutra-%s.manifest.json" % _arch()
    pack_name = "Sutra-%s.delta.tar.xz" % _arch()
    man, pack = (None, None) if _IS_WIN else (assets.get(man_name), assets.get(pack_name))
    return {
        "version": version,
        "tag": tag,
        "url": rel.get("html_url"),
        "asset": want,
        "download_url": (dmg or {}).get("browser_download_url"),
        "size": (dmg or {}).get("size"),
        "sha256_url": (assets.get(want + ".sha256") or {}).get("browser_download_url"),
        "delta": bool(man and pack),
        "manifest_asset": man_name,
        "manifest_url": (man or {}).get("browser_download_url"),
        "manifest_sha256_url": (assets.get(man_name + ".sha256") or {}).get("browser_download_url"),
        "pack_url": (pack or {}).get("browser_download_url"),
        "pack_sha256_url": (assets.get(pack_name + ".sha256") or {}).get("browser_download_url"),
        "pack_size": (pack or {}).get("size"),
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
            "reason": "not running from inside an installed .app -- this server "
                      "was started outside Sutra.app (the CLI, or a source "
                      "checkout), so there is nothing for an updater to replace "
                      "here",
        }
    latest = _latest_desktop()
    return {
        "component": "desktop",
        "managed": True,
        "installed": installed,
        "app_path": str(_installed_app()),
        "arch": _arch(),
        "latest": latest.get("version"),
        "release_url": latest.get("url"),
        "asset": latest.get("asset"),
        "size": latest.get("size"),
        "update_available": _newer(latest.get("version"), installed),
        # Whether the release carries a delta pack for this arch, and how big it
        # is: the number the Updates screen should show instead of the DMG size.
        "delta": bool(latest.get("delta")) and DELTA_ENABLED,
        "pack_size": latest.get("pack_size"),
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
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("the `claude` CLI is not on PATH")
    before = _installed_plugin_version()
    out = []
    # By the path which() found, not the bare name: on Windows npm installs
    # `claude` as a .cmd shim, which which() finds through PATHEXT and
    # CreateProcess cannot find from the bare name -- both steps failed and
    # the result still read "Already current."
    for cmd in ([claude, "plugin", "marketplace", "update", "sutra"],
                [claude, "plugin", "update", "core@sutra"]):
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


# HOW MANY TIMES A CUT-SHORT DOWNLOAD IS PICKED UP AGAIN before the updater
# gives up. Four is not a magic number: it is "a flaky link gets a fair few
# goes", and every go resumes rather than restarts, so the cost of another
# attempt is the bytes still missing and not another 400MB.
DOWNLOAD_TRIES = 4


# DOWNLOAD PROGRESS (founder 2026-09-26: "some bar showing how much MB and
# time"). Only the download knows those numbers, and it runs in whichever
# process staged it -- the backend or the sidecar CLI -- so it writes them to a
# small file in the staging dir that the panel's local-only route reads.
PROGRESS_EVERY_S = 0.5          # file refresh while bytes arrive
PROGRESS_STALE_S = 60           # silent this long = a download that died
DOWNLOAD_CHUNK = 1 << 14
_progress_version = None        # set by stage_desktop for the run
_downloaded_bytes = 0           # bytes fetched this run (delta packs + image)


def _progress_path():
    return stage_dir() / "download-progress.json"


def _progress_write(**fields):
    """Best effort: a progress file that cannot be written must never fail
    the download it describes."""
    try:
        p = _progress_path()
        rec = dict(fields, version=_progress_version, ts=time.time())
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(rec))
        os.replace(tmp, p)
    except Exception:
        pass


def download_progress():
    """The live download, or None. A file that stopped refreshing is a download
    that died, and is not shown as one still running."""
    try:
        d = json.loads(_progress_path().read_text())
    except Exception:
        return None
    if not isinstance(d, dict) or time.time() - float(d.get("ts") or 0) > PROGRESS_STALE_S:
        return None
    return d


def progress_clear():
    try:
        _progress_path().unlink()
    except Exception:
        pass


def _fetch_dmg(url, dmg, want_bytes=0):
    """Download the release image to `dmg`, whole, or raise saying what happened.

    WHY THIS IS NOT ONE urlopen INTO copyfileobj (owner, 2026-09-21). It was,
    and a truncated download was then indistinguishable from a corrupt one. A
    connection that dies at 263MB of 421MB leaves a perfectly readable short
    file; copyfileobj is happy, because a socket that closes IS end-of-file as
    far as it can tell. The checksum then fails, and the only thing the app
    could say was "checksum mismatch: published 1e553c0e, downloaded 9dbb56a0"
    -- which reads as "GitHub is serving a bad file, there is nothing you can
    do", when the truth was "your link dropped, try again". The owner hit this
    on a 421MB DMG, and so did two of my own downloads of the same file from
    this network, one through `gh` and one through curl.

    So: the expected length is known before a byte is read (the release says
    so, and the response says so again), a short file is NAMED as short, and a
    dropped connection is resumed with a Range request instead of starting the
    whole thing over. The checksum stays exactly where it was, and now it only
    ever fires for what it is actually for -- a file that arrived complete and
    wrong.
    """
    global _downloaded_bytes
    last = ""
    for attempt in range(1, DOWNLOAD_TRIES + 1):
        have = dmg.stat().st_size if dmg.exists() else 0
        if want_bytes and have > want_bytes:       # a stale part-file from an older,
            have = 0                               # bigger release: start it again
        headers = {"User-Agent": "sutra-ui-updater"}
        if have:
            headers["Range"] = "bytes=%d-" % have
        req = urllib.request.Request(url, headers=headers)
        expect = want_bytes
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                # A server that ignored the Range gives 200 and the whole file, so
                # the part-file must be thrown away rather than appended to.
                resumed = r.status == 206 if hasattr(r, "status") else r.getcode() == 206
                mode = "ab" if (have and resumed) else "wb"
                length = r.headers.get("Content-Length")
                expect = (int(length) + (have if resumed else 0)) if length else want_bytes
                # Chunked rather than copyfileobj so the panel can show MB, speed
                # and time left. start_done is what a resumed attempt already had,
                # so the speed is this attempt's, not inflated by the part-file.
                base = have if (have and resumed) else 0
                done, started, last_w = base, time.time(), 0.0
                _progress_write(phase="downloading", done=done, total=expect or 0,
                                start_done=base, started=started)
                with open(dmg, mode) as fh:
                    while True:
                        chunk = r.read(DOWNLOAD_CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        _downloaded_bytes += len(chunk)
                        now = time.time()
                        if now - last_w >= PROGRESS_EVERY_S:
                            last_w = now
                            _progress_write(phase="downloading", done=done, total=expect or 0,
                                            start_done=base, started=started)
        except urllib.error.HTTPError as exc:
            # 416 is the server saying "you already have at least all of it", which
            # means the part-file on disk is stale, not resumable. Bin it and start
            # the next attempt from zero rather than asking the same bad question.
            if exc.code == 416 and have:
                try:
                    dmg.unlink()
                except OSError:
                    pass
                last = "the part-file on disk did not match the release; starting again"
            else:
                last = "the server refused the download: %s" % exc
        except (urllib.error.URLError, OSError) as exc:
            last = "the connection dropped: %s" % exc
        else:
            got = dmg.stat().st_size
            if not expect or got >= expect:
                _progress_write(phase="verifying", done=got, total=expect or got,
                                start_done=base, started=started)
                return
            last = ("the download was cut short at %s of %s bytes"
                    % ("{:,}".format(got), "{:,}".format(expect)))
        if attempt < DOWNLOAD_TRIES:
            time.sleep(2 * attempt)
    try:
        dmg.unlink()                               # never leave a short file to be found later
    except OSError:
        pass
    raise RuntimeError(
        "download failed after %d tries -- %s. This is a network problem, not a "
        "bad release: the file on GitHub is fine. Try again on a steadier "
        "connection, or download the DMG from the release page and install it "
        "by hand." % (DOWNLOAD_TRIES, last))


def _published_sha256(url):
    """First token of a published .sha256 file, or None when it cannot be read.
    The caller decides what None means; here it never means 'fine'."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sutra-ui-updater"})
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
            return r.read(4096).decode("utf-8").split()[0].strip()
    except (urllib.error.URLError, OSError, IndexError, UnicodeDecodeError):
        return None


def _fetch_bytes(url, limit):
    """A small asset (manifest, checksum) read whole, refused past `limit`."""
    req = urllib.request.Request(url, headers={"User-Agent": "sutra-ui-updater"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT * 4) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("asset at %s is larger than %d bytes" % (url, limit))
    return data


def _staged_app_name(version):
    safe = re.sub(r"[^0-9.]", "", str(version or "")).strip(".") or "unknown"
    return "Sutra-%s-%s.app" % (_arch(), safe)


def _delta_reconstruct(latest, installed_version, work, app):
    """THE DELTA LANE. Rebuild the released bundle beside the staging dir from
    the installed one plus the release's delta pack(s), then run the same
    bundle-level gates the DMG lane runs. Raises (DeltaMiss or RuntimeError)
    for anything short of a byte-exact, Gatekeeper-accepted bundle; the caller
    then downloads the full image. See updates_delta.py for the format.

    Returns {"app": path, "manifest_path": path, "sha256": <manifest sha256>,
             "sha256_url": ..., "tree_sha256": ..., "asset": ..., "delta": stats}.
    """
    import updates_delta as ud
    arch = _arch()
    team, bundle_id = _bundle_identity(app)
    chain = []          # newest first: {version, manifest, manifest_sha256, pack_url, pack_sha256_url, pack_size}
    url = latest.get("manifest_url")
    sha_url = latest.get("manifest_sha256_url")
    pack_url, pack_sha_url, pack_size = latest.get("pack_url"), latest.get("pack_sha256_url"), latest.get("pack_size")
    version = latest.get("version")
    for _depth in range(ud.MAX_CHAIN):
        if not url or not pack_url:
            raise ud.DeltaMiss("release %s has no delta assets for %s" % (version, arch))
        raw = _fetch_bytes(url, ud.MAX_MANIFEST_BYTES)
        published = _published_sha256(sha_url)
        if not published:
            raise RuntimeError("the manifest for %s has no published checksum" % version)
        if _sha256_bytes(raw) != published:
            raise RuntimeError("the manifest for %s does not match its published checksum" % version)
        man = ud.validate_manifest(json.loads(raw.decode("utf-8")))
        if man.get("version") != version or man.get("arch") != arch:
            raise RuntimeError("the manifest for %s describes %s/%s" % (version, man.get("version"), man.get("arch")))
        if man.get("bundle_id") != bundle_id:
            raise ud.DeltaMiss("the release is for bundle %s, this app is %s" % (man.get("bundle_id"), bundle_id))
        chain.append({"version": version, "manifest": man, "manifest_raw": raw,
                      "manifest_sha256": published, "manifest_sha256_url": sha_url,
                      "pack_url": pack_url, "pack_sha256_url": pack_sha_url,
                      "pack_size": int(pack_size or 0)})
        prev = man.get("previous_version")
        if prev == installed_version:
            break
        if not prev or not _newer(prev, installed_version):
            raise ud.DeltaMiss("no delta chain from %s reaches the installed %s"
                               % (latest.get("version"), installed_version))
        # The previous release's assets have deterministic names under its tag.
        version = prev
        base = "%s/%s/releases/download/v%s-desktop/Sutra-%s" % (RELEASE_DOWNLOAD, DESKTOP_REPO, prev, arch)
        url, sha_url = base + ".manifest.json", base + ".manifest.json.sha256"
        pack_url, pack_sha_url, pack_size = base + ".delta.tar.xz", base + ".delta.tar.xz.sha256", 0
    else:
        raise ud.DeltaMiss("the installed %s is more than %d releases behind"
                           % (installed_version, ud.MAX_CHAIN))

    pack_dirs = []
    for hop in chain:
        p = work / ("pack-%s.tar.xz" % re.sub(r"[^0-9.]", "", hop["version"]))
        _fetch_dmg(hop["pack_url"], p, hop["pack_size"])
        published = _published_sha256(hop["pack_sha256_url"])
        if not published or _sha256(p) != published:
            raise RuntimeError("the delta pack for %s does not match its published checksum" % hop["version"])
        d = work / ("pack-%s" % re.sub(r"[^0-9.]", "", hop["version"]))
        ud.unpack_to_dir(p, d)
        p.unlink()
        pack_dirs.append(d)

    dest = work / _staged_app_name(latest.get("version"))
    stats = ud.reconstruct(app, chain[0]["manifest"], pack_dirs, dest)
    for d in pack_dirs:
        shutil.rmtree(d, ignore_errors=True)

    # The bundle-level gates, BEFORE staging: a rebuilt tree that codesign or
    # Gatekeeper will not accept is a miss, not something to hand the helper.
    p = _run(["codesign", "--verify", "--deep", "--strict", str(dest)], timeout=300)
    if p.returncode != 0:
        raise RuntimeError("the rebuilt bundle failed codesign: %s"
                           % (p.stderr or p.stdout or "").strip()[:300])
    p = _run(["spctl", "-a", "-t", "execute", "-v", str(dest)])
    if p.returncode != 0:
        raise RuntimeError("the rebuilt bundle is not accepted by Gatekeeper: %s"
                           % (p.stderr or p.stdout or "").strip()[:300])
    man_path = work / (latest.get("manifest_asset") or "Sutra-%s.manifest.json" % arch)
    man_path.write_bytes(chain[0]["manifest_raw"])
    return {"app": str(dest), "manifest_path": str(man_path),
            "sha256": chain[0]["manifest_sha256"], "sha256_url": chain[0]["manifest_sha256_url"],
            "tree_sha256": chain[0]["manifest"].get("tree_sha256"),
            "asset": latest.get("manifest_asset"), "delta": dict(stats, hops=len(chain))}


def download_and_verify(dest_dir=None):
    """Fetch the release for this arch and prove it before anything is replaced.

    Returns {"kind": "dmg", "dmg": path, "version": ...} for a full image or
    {"kind": "app", "app": path, ...} for a bundle rebuilt by the delta lane.
    Raises RuntimeError naming the gate that failed -- an update that cannot
    be verified is not installed, and the reason is not swallowed.
    """
    latest = _latest_desktop()
    if latest.get("error"):
        raise RuntimeError(latest["error"])
    url = latest.get("download_url")
    if not url:
        raise RuntimeError("the latest release has no downloadable asset for this machine")

    d = Path(dest_dir or tempfile.mkdtemp(prefix="sutra-update-"))
    d.mkdir(parents=True, exist_ok=True)

    # THE DELTA LANE FIRST. It can only fail towards the full image, and it
    # says why, so a support log shows "delta update not possible (...)"
    # rather than a silent 300 MB download.
    delta_note = None
    app = app_bundle()
    if DELTA_ENABLED and latest.get("delta") and app:
        try:
            got = _delta_reconstruct(latest, _installed_desktop_version(), d, app)
            got.update({"kind": "app", "dmg": None, "version": latest.get("version"), "dir": str(d)})
            return got
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            delta_note = "delta update not possible (%s); downloading the full image" % exc
            for p in list(d.iterdir()):
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() and not p.is_symlink() else p.unlink(missing_ok=True)

    dmg = d / latest["asset"]
    _fetch_dmg(url, dmg, int(latest.get("size") or 0))

    # GATE 1 -- checksum, against the file published beside the DMG.
    want = None
    if latest.get("sha256_url"):
        want = _published_sha256(latest["sha256_url"])
    if want:
        got = _sha256(dmg)
        if got != want:
            # THE BAD FILE GOES, and that is not tidying. Staging keeps the
            # image on disk between attempts so a download can be resumed, and
            # a complete-but-wrong file left lying there is the one thing that
            # rule cannot cope with: every later attempt would see the full
            # byte count, ask for nothing, and fail the same way forever.
            try:
                Path(dmg).unlink()
            except OSError:
                pass
            raise RuntimeError(
                "the downloaded image does not match the one published "
                "(published %s, downloaded %s). The copy here has been "
                "deleted; try the update again." % (want[:16], got[:16]))
    elif _IS_WIN:
        # On a Mac this is one gate of three. The Windows installer is unsigned,
        # so here it is the only one, and an unchecked installer is not run.
        raise RuntimeError(
            "could not read the published checksum for %s. On Windows it is the "
            "only check the installer gets, so it was not installed; try the "
            "update again later." % latest["asset"])

    if _IS_WIN:
        return {"dmg": str(dmg), "version": latest.get("version"), "dir": str(d)}

    # GATE 2 -- Gatekeeper. Signed is not enough; this must be NOTARIZED, which
    # is what `spctl` reports and what a stranger's Mac will demand.
    p = _run(["spctl", "-a", "-t", "open", "--context",
              "context:primary-signature", "-v", str(dmg)])
    if p.returncode != 0:
        raise RuntimeError("the downloaded image is not accepted by Gatekeeper: %s"
                           % (p.stderr or p.stdout or "").strip()[:300])

    return {"kind": "dmg", "dmg": str(dmg), "version": latest.get("version"),
            "dir": str(d), "sha256_url": latest.get("sha256_url"),
            "asset": latest.get("asset"), "note": delta_note}


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


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

if [ "${ARTIFACT_KIND:-dmg}" = "app" ]; then
  # A bundle the delta lane rebuilt in the staging directory. It was already
  # verified file-by-file against the release manifest and passed codesign
  # and Gatekeeper there; every gate below runs on it again regardless,
  # because from here on there is no one to ask.
  NEW="$DMG"
  cleanup() { :; }
  [ -d "$NEW" ] && [ ! -L "$NEW" ] || die contents "the staged bundle is gone"
else
  MNT="$(mktemp -d /tmp/sutra-mnt.XXXXXX)"
  hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MNT" >/dev/null \
    || die mount "could not mount $DMG"
  NEW="$MNT/Sutra.app"
  cleanup() { hdiutil detach "$MNT" -quiet 2>/dev/null || true; rmdir "$MNT" 2>/dev/null || true; }
  [ -d "$NEW" ] || die contents "the disk image does not contain Sutra.app"
fi
trap cleanup EXIT

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
if [ "${ARTIFACT_KIND:-dmg}" = "app" ]; then
  # Same volume, so this is an APFS clone: instant and costs no space. ditto
  # remains the fallback for a staging dir on some other filesystem.
  cp -c -R -p "$NEW" "$STAGE" 2>/dev/null \
    || { rm -rf "$STAGE"; ditto "$NEW" "$STAGE" || { rm -rf "$STAGE"; die copy "could not copy the new bundle into place"; }; }
else
  ditto "$NEW" "$STAGE" || { rm -rf "$STAGE"; die copy "could not copy the new bundle into place"; }
fi
codesign --verify --deep --strict "$STAGE" 2>/dev/null \
  || { rm -rf "$STAGE"; die copy-verify "the copied bundle does not verify"; }

printf '{"app":"%s","backup":"%s","staged":"%s","ts":%s}\n' \
  "$APP" "$BAK" "$STAGE" "$(date +%s)" > "$RECOVER" 2>/dev/null
if ! mv "$APP" "$BAK"; then
  rm -f "$RECOVER"; rm -rf "$STAGE"; die swap "could not move the old bundle aside"
fi
# `mv src dst` NESTS INSTEAD OF REPLACING WHEN dst IS AN EXISTING DIRECTORY, and
# it exits 0 doing it. That broke a real install on 2026-09-24: the user was left
# with Sutra.app/Sutra.app.new-<pid> sitting inside a Sutra.app whose
# Contents/MacOS was gone, while every gate above had passed and the swap below
# reported success. The mv is only a rename while $APP does not exist, so that is
# checked rather than assumed -- the line above can report success and still
# leave $APP standing, and from here exit 0 means the opposite of what it reads as.
if [ -e "$APP" ]; then
  mv "$BAK" "$APP" 2>/dev/null
  rm -f "$RECOVER"; rm -rf "$STAGE"
  die swap "$APP still exists after being moved aside; refusing to move the new bundle into it"
fi
if ! mv "$STAGE" "$APP"; then
  mv "$BAK" "$APP" 2>/dev/null
  rm -f "$RECOVER"; rm -rf "$STAGE"; die swap "could not move the new bundle into place"
fi
# A SWAP THAT EXITED 0 IS NOT A SWAP THAT LANDED. The executable is what macOS
# needs to launch at all, so its absence is the whole difference between an
# installed app and one that opens into nothing, which is the state the nesting
# bug shipped. Checked while $BAK is still here, so there is something to go back
# to; after the rm below there would not be.
APP_EXE="$(plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist" 2>/dev/null)"
if [ -z "$APP_EXE" ] || [ ! -x "$APP/Contents/MacOS/$APP_EXE" ]; then
  rm -rf "$APP"
  mv "$BAK" "$APP" 2>/dev/null
  rm -f "$RECOVER"
  die swap "the installed bundle has no runnable executable; the old one was put back"
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


ON_IMAGE = (
    "Sutra is running from the installer disk image, which is read-only, so it "
    "cannot replace itself and no update can ever land.\n\n"
    "Quit Sutra, drag it to your Applications folder, eject the disk image, and "
    "open it from Applications. Updates work by themselves from then on."
)

PORTABLE = (
    "This is the portable Sutra-x64.exe. It runs from a temporary copy, so it "
    "cannot replace itself and no update can ever land.\n\n"
    "Download Sutra-Setup-x64.exe from the release page and run it once. Sutra "
    "then installs for your user account, and updates work by themselves from "
    "then on."
)


def _win_exe_name():
    return Path(os.environ.get("SUTRA_DESKTOP_EXE") or "Sutra.exe").name


def _win_blocker(root):
    """install_blocker() for Windows. The portable exe sets
    PORTABLE_EXECUTABLE_FILE for its children; an NSIS install also leaves its
    uninstaller beside the exe, which an unpacked portable copy never has."""
    if os.environ.get("PORTABLE_EXECUTABLE_FILE") or not any(root.glob("Uninstall*.exe")):
        return PORTABLE
    # The feed (releases/latest) carries the stable installer only. macOS
    # refuses a different app by bundle id; unsigned, the exe name is all
    # Windows has, and running stable's installer into a beta's folder would
    # replace one app with another.
    if _win_exe_name().lower() != "sutra.exe":
        return ("This is %s. Updates carry the stable Sutra installer only, which "
                "would replace this app with a different one. Install the stable "
                "release separately instead." % Path(_win_exe_name()).stem)
    # A real write, not os.access: on Windows that checks only the read-only
    # attribute and says yes to Program Files. The installer offers an
    # all-users install there, and a silent update of it needs an admin.
    try:
        fd, probe = tempfile.mkstemp(prefix=".sutra-write-probe-", dir=str(root))
        os.close(fd)
        os.unlink(probe)
    except OSError:
        return ("Sutra is installed in %s for everyone on this PC, which this user "
                "account cannot change without an administrator, so it cannot "
                "update itself. Run Sutra-Setup-x64.exe by hand, or reinstall it "
                "choosing \"Only for me\"." % root)
    return None


def install_blocker(app_path=None):
    """A plain-English reason this machine cannot install an update, or None.

    Checked BEFORE the download, because the alternative is what actually
    happened to a user: wait for 240MB, then get told a folder is "not
    writable". The overwhelming cause is an app still running from the DMG --
    people double-click it in the installer window and it works, so nothing
    ever tells them they never installed it. Name that, rather than naming a
    path and a permission bit.
    """
    target = app_path or _installed_app()
    if not target:
        return None                      # a source checkout updates by git
    app = Path(target)
    if _IS_WIN:
        return _win_blocker(app)
    if str(app).startswith("/Volumes/"):
        return ON_IMAGE
    if not os.access(app.parent, os.W_OK):
        return ("Sutra is installed in %s, which this user account cannot write "
                "to, so the update cannot be put there. Move Sutra to your "
                "Applications folder, or install the DMG by hand." % app.parent)
    return None


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
    if _IS_WIN:
        return _install_desktop_windows(dmg, app_path=app_path, wait_pid=wait_pid,
                                        relaunch=relaunch, version=version,
                                        result_path=result_path)
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
    blocked = install_blocker(app)
    if blocked:
        raise RuntimeError(blocked)
    artifact = Path(dmg)
    if artifact.is_symlink():
        raise RuntimeError("the staged artifact is a symlink: %s" % dmg)
    if artifact.is_dir() and artifact.suffix == ".app":
        kind = "app"
    elif artifact.is_file():
        kind = "dmg"
    else:
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
        "DMG": str(dmg), "ARTIFACT_KIND": kind, "APP": str(app), "LOG": str(log),
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


_WIN_INSTALLER = r"""# Written by sutra-ui updates.py. The Windows leg of the desktop updater: waits
# for the app to be GONE, then runs the verified NSIS installer silently over
# the existing install. The checksum was checked before this ran; from here on
# there is no one to ask. Inputs arrive as environment variables, as on macOS:
# SETUP APP_DIR APP_EXE LOG WAIT_PID RELAUNCH EXPECT_VERSION RESULT.
$ErrorActionPreference = 'Stop'

function Log([string]$m) {
  try { Add-Content -LiteralPath $env:LOG -Value ('[' + (Get-Date -Format s) + '] ' + $m) } catch {}
}

# Terminal status, in the shape the macOS helper writes and resolve_pending()
# reads. UTF-8 without a BOM: Windows PowerShell's own UTF8 writes one, and
# json.load refuses it.
function Result([bool]$ok, [string]$stage, [string]$err) {
  if ($err.Length -gt 300) { $err = $err.Substring(0, 300) }
  $o = [ordered]@{
    ok = $ok
    stage = $stage
    version = [string]$env:EXPECT_VERSION
    error = $err
    ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  }
  $tmp = $env:RESULT + '.tmp'
  [System.IO.File]::WriteAllText($tmp, ($o | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -LiteralPath $tmp -Destination $env:RESULT -Force
}

function Die([string]$stage, [string]$msg) {
  Log ('FAIL(' + $stage + '): ' + $msg)
  Result $false $stage $msg
  exit 1
}

Log ('installer start setup=' + $env:SETUP + ' app=' + $env:APP_DIR + ' wait_pid=' + $env:WAIT_PID + ' relaunch=' + $env:RELAUNCH)

# 1. wait for THAT process to end. Its start time is taken now, while it is
#    still the shell that armed us: a pid reused later has a different start
#    time, which means ours is already gone.
$waitPid = [int]$env:WAIT_PID
$t0 = $null
try { $t0 = (Get-Process -Id $waitPid -ErrorAction Stop).StartTime } catch {}
function Shell-Alive {
  try {
    $p = Get-Process -Id $waitPid -ErrorAction Stop
    if ($t0 -and $p.StartTime -ne $t0) { return $false }
    return $true
  } catch { return $false }
}
for ($i = 0; $i -lt 120; $i++) {
  if (-not (Shell-Alive)) { break }
  Start-Sleep -Seconds 1
}
if (Shell-Alive) { Die 'app-alive' ('app still running after 120s; ' + $env:APP_DIR + ' untouched') }

# 2. the shell exiting is not the folder being free. Electron helpers, the
#    bundled python backend and anything it started run out of the same folder,
#    and the installer cannot replace a file in use. What the app that quit
#    left behind is orphaned: stop it after a grace period. A Sutra.exe started
#    AFTER this helper is the user opening Sutra again: touch nothing, and the
#    next quit applies the update.
$helperStart = (Get-Process -Id $PID).StartTime
$prefix = $env:APP_DIR.TrimEnd('\') + '\'
function From-App {
  @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and $_.Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) } catch { $false }
  })
}
function Reopened {
  @(From-App | Where-Object {
    try { ($_.Path -ieq $env:APP_EXE) -and ($_.StartTime -gt $helperStart) } catch { $false }
  })
}
for ($i = 0; $i -lt 30; $i++) {
  if ((Reopened).Count -gt 0) { break }
  if ((From-App).Count -eq 0) { break }
  Start-Sleep -Seconds 1
}
if ((Reopened).Count -gt 0) {
  Die 'app-reopened' ('Sutra was opened again before the update could apply; ' + $env:APP_DIR + ' untouched')
}
$left = From-App
if ($left.Count -gt 0) {
  Log ('stopping leftovers: ' + (($left | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ', '))
  $left | ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {} }
  Start-Sleep -Seconds 2
}
$left = From-App
if ($left.Count -gt 0) {
  Die 'procs-alive' ('processes are still running from ' + $env:APP_DIR + ': ' + (($left | ForEach-Object { $_.ProcessName }) -join ', '))
}

# 3. run the installer silently, as an update, into the SAME folder. These are
#    the arguments electron-updater gives an electron-builder NSIS installer:
#    --updated keeps user data, /S is silent, --force-run reopens the app, and
#    /D= must come LAST, unquoted (NSIS reads the rest of the line as the path).
$argList = @('--updated', '/S')
if ($env:RELAUNCH -eq '1') { $argList += '--force-run' }
$argList += ('/D=' + $env:APP_DIR)
Log ('running ' + $env:SETUP + ' ' + ($argList -join ' '))
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $env:SETUP
$psi.Arguments = ($argList -join ' ')
$psi.UseShellExecute = $false
$psi.WorkingDirectory = Split-Path -Parent $env:SETUP
try {
  $proc = [System.Diagnostics.Process]::Start($psi)
} catch {
  Die 'spawn' ('could not start the installer: ' + $_.Exception.Message)
}
# The installer alone, not its tree: --force-run starts the app as its child,
# and waiting on that would wait for the user to quit Sutra again.
if (-not $proc.WaitForExit(600000)) { Die 'install-timeout' 'the installer did not finish within 10 minutes' }
if ($proc.ExitCode -ne 0) { Die 'install' ('the installer exited with code ' + $proc.ExitCode) }

# 4. exit code 0 is not proof the new version landed. electron-builder stamps
#    the exe's FileVersion with the app version; read it back.
if (-not (Test-Path -LiteralPath $env:APP_EXE)) { Die 'verify' ('no ' + $env:APP_EXE + ' after the installer finished') }
$fv = [string](Get-Item -LiteralPath $env:APP_EXE).VersionInfo.FileVersion
$want = [string]$env:EXPECT_VERSION
if ($want -and $fv -and $fv -ne $want -and -not $fv.StartsWith($want + '.')) {
  Die 'version' ('installed ' + $fv + ', but ' + $want + ' was staged and verified')
}
Result $true 'installed' ''
Log ('installed ' + $want + ' (file version ' + $fv + ')')
"""

# Win32 process-creation flags (winbase.h), spelled out so this module imports
# the same on every OS.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def _install_desktop_windows(setup, app_path=None, wait_pid=None, relaunch=False,
                             version=None, result_path=None):
    """Spawn the detached helper that runs the verified installer once the app
    has exited. Returns immediately, like the macOS leg. The installer does the
    swap itself, so there is no two-rename window and no recover record."""
    target = app_path or win_install()
    if not target or not str(target).strip():
        raise RuntimeError("no installed Sutra to replace")
    root = Path(target)
    if not root.is_dir():
        raise RuntimeError("%s is not an installed Sutra folder" % root)
    blocked = install_blocker(root)
    if blocked:
        raise RuntimeError(blocked)
    setup = Path(setup)
    if not setup.is_file() or setup.suffix.lower() != ".exe":
        raise RuntimeError("no such installer: %s" % setup)

    pid = int(wait_pid) if wait_pid else os.getppid()
    d = Path(tempfile.mkdtemp(prefix="sutra-installer-"))
    script = d / "install.ps1"
    log = d / "install.log"
    script.write_text(_WIN_INSTALLER, encoding="utf-8")

    env = dict(os.environ)
    env.update({
        "SETUP": str(setup), "APP_DIR": str(root),
        "APP_EXE": str(root / _win_exe_name()), "LOG": str(log),
        "WAIT_PID": str(pid), "RELAUNCH": "1" if relaunch else "0",
        "EXPECT_VERSION": str(version or ""),
        "RESULT": str(result_path or (d / "install-result.json")),
    })
    # By absolute path: a powershell.exe earlier on PATH is not ours to run.
    ps = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows",
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    argv = [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", str(script)]
    # Detached and out of the shell's job: Electron runs the backend in a
    # kill-on-close job, and the helper has to outlive the app it waits for.
    # A job that forbids breakaway refuses that flag; start without it then.
    base = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
    for flags in (base | _CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            # cwd out of the install folder: the backend runs inside it, and a
            # process's cwd pins that directory while the old version is removed.
            subprocess.Popen(argv, env=env, cwd=str(d), creationflags=flags,
                             close_fds=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
        except OSError:
            if flags == base:
                raise
    return {"scheduled": True, "log": str(log), "app": str(root),
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
# The Windows helper can wait 120 s for the shell, 32 s for leftovers and 600 s
# for the installer; a shorter lease lets a launch arm a second helper.
WIN_ARM_LEASE_SECONDS = 900


def stage_dir():
    """The durable staging directory, created 0700 and proven not to be a
    symlink.

    NOT tempfile.mkdtemp: /tmp is periodically purged, and an update the user
    deferred on Friday has to still be there on Monday. Durability is the point,
    but it is also the cost -- a file that sits in a writable place for days is
    a file someone can swap, so the directory is locked down and every read out
    of it is re-verified rather than trusted.
    """
    if _IS_WIN:
        # Per app (Sutra / Sutra Beta): a shared manifest would let a beta
        # launch arm stable's staged installer.
        default = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                               Path(_win_exe_name()).stem, "updates")
    else:
        default = "~/Library/Application Support/Sutra/updates"
    d = Path(os.path.expanduser(os.environ.get("SUTRA_UPDATE_DIR", default)))
    if d.is_symlink():
        raise RuntimeError("%s is a symlink; refusing to stage there" % d)
    d.mkdir(parents=True, exist_ok=True)
    if _IS_WIN:
        # No POSIX owner or mode bits here (st_uid is always 0; os.getuid does
        # not exist). %LOCALAPPDATA% is private to the user by its default ACL,
        # which is the property the checks below prove on a Mac.
        return d
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


STATE_BUSY_MESSAGE = ("the update state is in use by another process "
                      "(a stage or install is in progress)")
STALE_DOWNLOAD_SECONDS = 3600   # a .download-* dir untouched this long is abandoned


class StateBusy(RuntimeError):
    """The manifest lock was not free in time. NOT a failed update: nothing was
    checked and nothing was refused, so callers retry instead of reporting it.
    Still a RuntimeError, so every existing `except RuntimeError` keeps working.
    The shell matches on STATE_BUSY_MESSAGE (HTTP detail) or `busy` (CLI)."""


@contextlib.contextmanager
def _state_lock(timeout=5.0):
    """Serialise manifest read-modify-write across PROCESSES.

    The lease makes arming idempotent-ish and the Electron single-instance
    lock caps shells at one, but neither protects pending-update.json from a
    second WRITER CLASS -- and since 2026-08-25 there is one: the shell spawns
    this module as a CLI (updates_cli) in attach mode, alongside whatever
    backend also holds these functions. flock, held narrowly and NEVER
    indefinitely: the quit path runs under a hard wall-clock bound, and a lock
    that outwaits it would freeze the app on exit. Timeout raises StateBusy.

    HELD ONLY AROUND LOCAL FILE WORK. Never around a download, a Gatekeeper
    check, or a network re-check: a stage used to hold this for the whole
    ~400MB download, so an arm or resolve arriving meanwhile timed out and the
    banner reported a perfectly good update as "could not be applied".
    Manifest writes are atomic renames, so reading WITHOUT the lock is safe.
    """
    path = stage_dir() / ".lock"
    fh = open(path, "a")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise StateBusy(STATE_BUSY_MESSAGE)
                time.sleep(0.1)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


def read_pending():
    return _read_json(_pending_path())


def clear_pending(also_remove_dmg=True):
    man = read_pending()
    if also_remove_dmg and man and man.get("dmg"):
        try:
            p = Path(man["dmg"])
            if p.is_symlink():
                pass
            elif p.is_file():
                p.unlink()
            elif p.is_dir() and p.suffix == ".app" and stage_dir().resolve() in p.resolve().parents:
                shutil.rmtree(p, ignore_errors=True)
        except (OSError, RuntimeError):
            pass
    if also_remove_dmg and man and man.get("manifest_path"):
        try:
            Path(man["manifest_path"]).unlink()
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
    root = stage_dir().resolve()
    if man.get("artifact_kind") == "app":
        # A rebuilt bundle: its identity is the release manifest. Every file is
        # re-hashed against it (a few seconds), and the manifest's own digest
        # is what the online re-check compares with the published one.
        import updates_delta as ud
        if not dmg.is_dir() or dmg.is_symlink():
            raise RuntimeError("the staged bundle is gone")
        if root not in dmg.resolve().parents:
            raise RuntimeError("the staged bundle is not inside the staging directory")
        mp = Path(man.get("manifest_path") or "")
        if not mp.is_file() or mp.is_symlink() or root not in mp.resolve().parents:
            raise RuntimeError("the staged bundle's manifest is gone")
        got = _sha256(mp)
        if man.get("sha256") and got != man["sha256"]:
            raise RuntimeError("the staged manifest changed on disk since it was verified")
        manifest = ud.load_manifest(mp)
        problems = ud.verify_tree(dmg, manifest)
        if problems:
            raise RuntimeError("the staged bundle changed on disk since it was verified: %s"
                               % "; ".join(problems[:3]))
    else:
        if not dmg.is_file() or dmg.is_symlink():
            raise RuntimeError("the staged disk image is gone")
        if root not in dmg.resolve().parents:
            raise RuntimeError("the staged image is not inside the staging directory")
        got = _sha256(dmg)
        if man.get("sha256") and got != man["sha256"]:
            raise RuntimeError("the staged image changed on disk since it was verified")

    published = None
    if recheck_online and man.get("sha256_url"):
        published = _published_sha256(man["sha256_url"])
    if published and published != got:
        raise RuntimeError("the staged image no longer matches the published "
                           "checksum for this release")
    return {"sha256": got, "reverified_online": bool(published)}


def _install_live(man, now=None):
    """True while a spawned helper may still be using the manifest's DMG."""
    now = int(time.time()) if now is None else now
    return bool(man) and man.get("state") == "installing" \
        and (man.get("lease_until") or 0) > now


def _staged_dmg_path(asset, version):
    """Version-specific name, e.g. Sutra-arm64-2.271.5.dmg. A download of the
    NEXT release can then never land on the file an armed install is using --
    they used to share one name, so a stage truncated the staged image."""
    stem, ext = os.path.splitext(os.path.basename(str(asset or "Sutra.dmg")))
    safe = re.sub(r"[^0-9.]", "", str(version or "")).strip(".") or "unknown"
    return stage_dir() / ("%s-%s%s" % (stem or "Sutra", safe, ext or ".dmg"))


def _sweep_stale_downloads(root):
    """Remove .download-* dirs left by a crashed stage. Judged by the newest
    mtime inside, so a download still being written is never touched."""
    now = time.time()
    for p in root.glob(".download-*"):
        try:
            if p.is_symlink() or not p.is_dir():
                continue
            newest = p.lstat().st_mtime
            for c in p.iterdir():
                newest = max(newest, c.lstat().st_mtime)
            if now - newest > STALE_DOWNLOAD_SECONDS:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def stage_desktop():
    """Download and verify the newest desktop release, arming nothing.

    Split from arming deliberately. While these were one call there was no
    moment at which an update was ready but not yet scheduled -- which is the
    only moment a prompt can happen in.

    The download and the Gatekeeper check run with NO lock held, into a
    private .download-* dir inside the staging directory (same volume, so the
    final move is a rename). Only _commit_stage takes the lock.
    """
    state = desktop_state()
    if not state.get("managed"):
        return {"staged": False, "reason": state.get("reason", "not an installed app")}
    if state.get("error"):
        raise RuntimeError(state["error"])
    if not state.get("update_available"):
        return {"staged": False, "reason": "already up to date",
                "installed": state.get("installed")}
    # Asked here and not only by the HTTP route: the sidecar (updates_cli stage)
    # calls straight in, and a portable Windows copy downloaded the installer
    # on every release only to be refused at every arm.
    blocked = install_blocker()
    if blocked:
        raise RuntimeError(blocked)

    version = state.get("latest")
    existing = read_pending()
    if _install_live(existing):
        return {"staged": False, "version": existing.get("version"),
                "reason": "an installer for %s is already waiting"
                          % existing.get("version")}
    if existing and existing.get("version") == version and existing.get("dmg"):
        try:
            _verify_staged(existing, recheck_online=False)
            return {"staged": True, "already": True, "version": version,
                    "state": existing.get("state")}
        except RuntimeError:
            pass     # unusable; fetch it again -- the commit replaces this record

    root = stage_dir()
    _sweep_stale_downloads(root)
    latest = _latest_desktop()
    work = Path(tempfile.mkdtemp(prefix=".download-", dir=str(root)))
    global _progress_version, _downloaded_bytes
    _progress_version, _downloaded_bytes = version, 0
    try:
        got = download_and_verify(dest_dir=str(work))
        got["downloaded_bytes"] = _downloaded_bytes
        # A rebuilt bundle's identity is its manifest's digest; an image's is
        # its own. Either way it is what arm re-checks against the release.
        digest = got["sha256"] if got.get("kind") == "app" else _sha256(got["dmg"])
        with _state_lock():
            return _commit_stage(got, got.get("version") or version, digest,
                                 latest, replaceable=existing)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        progress_clear()


def _commit_stage(got, version, digest, latest, replaceable):
    """Move a verified download into place and write the manifest. LOCK HELD.

    Re-reads the manifest, because the world moved during the download:
      - a live install  -> discard; its DMG is never deleted or overwritten
      - same or newer already staged by someone else -> discard
      - the broken same-version record we set out to replace -> replace it
    """
    cur = read_pending()
    if _install_live(cur):
        return {"staged": False, "discarded": version,
                "version": cur.get("version"),
                "reason": "an installer for %s is already waiting"
                          % cur.get("version")}
    if cur and cur.get("dmg") and _ver_tuple(cur.get("version")) >= _ver_tuple(version):
        broken_same = cur == replaceable and cur.get("version") == version
        if not broken_same:
            return {"staged": True, "already": True, "discarded": version,
                    "version": cur.get("version"), "state": cur.get("state")}

    kind = got.get("kind") or "dmg"
    src = Path(got["app"] if kind == "app" else got["dmg"])
    if src.is_symlink() or not (src.is_dir() if kind == "app" else src.is_file()):
        raise RuntimeError("the verified download disappeared before it was staged")
    manifest_final = None
    if kind == "app":
        final = stage_dir() / _staged_app_name(version)
        if final.exists() and not final.is_symlink():
            shutil.rmtree(final, ignore_errors=True)
        manifest_final = stage_dir() / (final.name[:-4] + ".manifest.json")
        os.replace(got["manifest_path"], manifest_final)
    else:
        final = _staged_dmg_path(latest.get("asset") or src.name, version)
    os.replace(src, final)
    _write_json(_pending_path(), {
        "state": "staged",
        "version": version,
        "dmg": str(final),
        "artifact_kind": kind,
        "manifest_path": str(manifest_final) if manifest_final else None,
        "tree_sha256": got.get("tree_sha256"),
        "delta": got.get("delta"),
        "note": got.get("note"),
        "downloaded_bytes": got.get("downloaded_bytes"),
        "sha256": digest,
        "sha256_url": got.get("sha256_url") if kind == "app" else latest.get("sha256_url"),
        "asset": got.get("asset") if kind == "app" else latest.get("asset"),
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
    # Every other image here is now unreferenced: the only other holder of a
    # DMG path is a live install, refused above. This also retires the old
    # unversioned Sutra-<arch>.dmg name. (.exe on Windows.)
    for p in list(stage_dir().glob("*" + final.suffix)) + list(stage_dir().glob("*.app")) \
            + list(stage_dir().glob("*.manifest.json")):
        try:
            if p in (final, manifest_final) or p.is_symlink():
                continue
            if p.is_file():
                p.unlink()
            elif p.is_dir() and p.suffix == ".app":
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass
    try:
        _result_path().unlink()
    except OSError:
        pass
    return {"staged": True, "version": version, "dmg": str(final), "artifact_kind": kind,
            "delta": got.get("delta"), "note": got.get("note")}


ARM_RECORD_RETRIES = 3      # manifest changed between verify and commit


def arm_desktop(wait_pid, wait_start=None, relaunch=False):
    """Schedule the swap for after the app named by `wait_pid` exits.

    Idempotent and single-flight. Two callers can plausibly reach this at once
    -- the countdown firing while the user is already quitting -- and two
    helpers racing to replace the same bundle is exactly the situation the rest
    of this file is written to avoid.

    The image is re-verified (hashing plus a network re-check) OUTSIDE the
    lock; under the lock the manifest is re-read and must still be exactly the
    record that was verified, or the whole decision is taken again.
    """
    for _ in range(ARM_RECORD_RETRIES):
        man = read_pending()
        early = _arm_precheck(man)
        if early is not None:
            return early
        proof = _verify_staged(man)
        with _state_lock():
            cur = read_pending()
            if cur == man:
                return _arm_locked(cur, proof, wait_pid, wait_start, relaunch)
    raise StateBusy(STATE_BUSY_MESSAGE)


def _arm_precheck(man):
    """None when `man` may be armed; an answer or a refusal otherwise."""
    if not man:
        raise RuntimeError("there is no staged update to install")
    if _install_live(man):
        return {"scheduled": True, "already": True, "version": man.get("version"),
                "note": "an installer for this version is already waiting"}
    if man.get("state") == "failed" and man.get("install_failures", 0) >= MAX_APPLY_ATTEMPTS:
        raise RuntimeError("this update failed to install %d times and will not "
                           "be retried automatically: %s"
                           % (man["install_failures"], man.get("last_error") or "unknown"))
    return None


def _arm_locked(man, proof, wait_pid, wait_start, relaunch):
    """Stamp `installing` and spawn the helper. LOCK HELD; `man` is verified."""
    now = int(time.time())

    # Stamped BEFORE the spawn, so a crash between here and the helper starting
    # is still visible as an attempt at the next launch.
    man.update({"state": "installing", "armed_at": now,
                "lease_until": now + (WIN_ARM_LEASE_SECONDS if _IS_WIN else ARM_LEASE_SECONDS),
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
    """Public, serialised entry -- see _state_lock for why."""
    with _state_lock():
        return _resolve_pending_unlocked(installed_version=installed_version)


def _resolve_pending_unlocked(installed_version=None):
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
           "downloaded_bytes": man.get("downloaded_bytes"),
           "delta": bool(man.get("artifact_kind") == "app"),
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
