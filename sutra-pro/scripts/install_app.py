#!/usr/bin/env python3
"""Install Sutra Pro on this Mac: a BETA built from this working tree, or a published RELEASE (D242). On a Windows x64 PC: the BETA only (D432).

    scripts/py scripts/install_app.py beta              build "Sutra Pro Beta" from this tree, prove it, install it beside the stable app, open it
    scripts/py scripts/install_app.py release [TAG]     download a published release, check its checksum, replace "Sutra Pro", reinstall the command
    scripts/py scripts/install_app.py status            what is installed, what is running, where each keeps its data

Two apps, one Mac. They differ in every name a second copy could collide on (desktop/src/channels.json):

    |                     | stable                         | beta                                   |
    | app                 | /Applications/Sutra Pro.app    | /Applications/Sutra Pro Beta.app       |
    | bundle id           | os.sutra.pro                   | os.sutra.pro.beta                      |
    | data folder         | ~/.sutra-pro                   | ~/.sutra-pro-beta  (its own, empty at first) |
    | where it comes from | a GitHub release               | the working tree of this checkout, local only |
    | updates itself      | yes (signed releases)          | never                                  |

So a beta can be installed and opened without touching the stable app, its data or its server, and both can run at once. `beta` replaces only the
beta; `release` replaces only the stable app and the `sutra-pro` command. Neither touches ~/.sutra-pro unless the stable app is the one that runs.

beta     uv build (the wheel of this tree) -> the Electron app with the Python inside (scripts/build_desktop_app.py --channel beta) -> ad hoc signature
         (scripts/sign_desktop_app.sh) -> the window proof (scripts/prove_desktop_app.py, throw-away data, no network) -> quit a running beta that is not
         working -> ditto into the install folder -> open it and wait for /api/health with this tree's version. The wheel and the app are built
         into build/beta/ (ignored by git). --no-proof skips the proof, --no-launch the opening, --skip-npm reuses desktop/node_modules.
release  the DMG of this Mac's architecture and its .sha256 are downloaded from the GitHub release (public, no login), the checksum is checked, the stable app
         is quit when it is running and idle, replaced from the DMG's copy (never half: the new copy is made beside the old and swapped in), its seal and
         bundle id are checked, the wheel is checked and installed with `uv tool install --reinstall`, then the app is opened and must answer /api/health with the
         release's version. TAG defaults to the newest stable `sutra-pro-vX.Y.Z` tag of origin.

A running app is never quit while it is working: an app whose server has a child process (an engine run, a model call of a chat turn) is busy, the install
stops with exit status 3 and says what is running; --force quits it anyway. Nothing is ever killed with SIGKILL: an app that does not quit within a
minute stops the install (exit 1) and the owner quits it.

Windows (D432): `beta` builds the folder "Sutra Pro Beta" (Sutra Pro Beta.exe, resources/python, resources/build-info.json, where its facts come from),
does not sign it, reads the processes from PowerShell's process list, closes a running idle beta through its window (`taskkill /PID`, never `/F`), copies the
folder in whole (beside, then swapped in), starts its exe, and writes a Start-menu entry. The default install folder is %LOCALAPPDATA%\\Programs.
`beta --pull` first fetches and fast-forwards this checkout to its upstream (the beta's own checkout follows origin/main); it refuses a tree with changes.

Exit status: 0 done; 1 a step failed (one `error:` line); 2 bad command line; 3 the app is busy. Python 3.11 (scripts/py) and the standard library; `beta` also uses
scripts/build_desktop_app.py, and needs node (22 or newer) and uv.
"""
from __future__ import annotations

import argparse
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
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import build_desktop_app as builder                                          # noqa: E402  (the channels, and the builder of the app)

CHANNELS = builder.CHANNELS
REPO = "sankalpasawa/sutra"
TAG = re.compile(r"^sutra-pro-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")    # a stable release tag (no leading zeros, as the release guard has it): a beta tag has a suffix and is never installed as the app
DEFAULT_INSTALL_DIR = Path("/Applications")                                  # a Mac's; on Windows, default_install_dir() (D432)
QUIT_TIMEOUT_S = 60
START_TIMEOUT_S = 120
BUSY = 3


class InstallError(Exception):
    """A step failed; `str(error)` is the one line the owner reads."""


class Busy(InstallError):
    """The app is working: quitting it would end a run or a reply."""


def say(text: str) -> None:
    print(text, flush=True)


def home_relative(path: Path) -> str:
    """A path as `~/...` when it is under the home folder (what the scripts print, so a log never carries a person's name)."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- commands and processes (the seams the tests replace)

def run(args: Sequence[str], *, timeout: Optional[float] = None, cwd: Optional[Path] = None, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    """Run a program with an argument list (no shell); the result is returned whatever its exit status, a program that cannot start has status 127."""
    try:
        return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None, env=env)
    except FileNotFoundError as error:
        return subprocess.CompletedProcess(list(args), 127, "", str(error))
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(list(args), 124, "", f"timed out after {error.timeout} s")


def windows() -> bool:
    return sys.platform == "win32"


def default_install_dir() -> Path:
    """Where the apps go: /Applications on a Mac; on Windows the user's own programs folder, %LOCALAPPDATA%\\Programs (no administrator needed)."""
    if not windows():
        return DEFAULT_INSTALL_DIR
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / "AppData" / "Local") / "Programs"


def contains(command: str, text: str) -> bool:
    """`text` in `command`, ignoring case on Windows (its paths are not case-sensitive, and a command line may spell one either way)."""
    return text.lower() in command.lower() if windows() else text in command


PROCESS_LIST = "Get-CimInstance Win32_Process | ForEach-Object { '{0} {1} {2}' -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }"


def process_table() -> list[tuple[int, int, str]]:
    """(pid, parent pid, command line) of every process (`ps` on a Mac, PowerShell's process list on Windows)."""
    rows = []
    listing = (run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROCESS_LIST], timeout=120) if windows()
               else run(["ps", "-axo", "pid=,ppid=,command="]))
    for line in listing.stdout.splitlines():
        found = re.match(r"\s*(\d+)\s+(\d+)\s+(.*)$", line)
        if found:
            rows.append((int(found.group(1)), int(found.group(2)), found.group(3)))
    return rows


def sleep(seconds: float) -> None:
    time.sleep(seconds)


# ---------------------------------------------------------------- what is where

def bundle(channel: str, install_dir: Path) -> Path:
    """The app of `channel` in `install_dir`: `<name>.app` on a Mac, the folder `<name>` (holding `<name>.exe`) on Windows."""
    name = CHANNELS[channel]["appName"]
    return Path(install_dir) / (name if windows() else f"{name}.app")


def data_dir(channel: str) -> Path:
    return Path.home() / CHANNELS[channel]["dataDirName"]


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def host_target() -> tuple[str, str]:
    """(the builder's target, the architecture in the DMG's name) of this Mac, or ("win-x64", "x64") on a Windows PC (a beta only: D432)."""
    if windows():
        if platform.machine().upper() not in ("AMD64", "X86_64"):
            raise InstallError(f"unsupported architecture {platform.machine()!r}: the Windows app is x64 only")
        return "win-x64", "x64"
    if sys.platform != "darwin":
        raise InstallError("this installs a Mac app: run it on the Mac")
    machine = platform.machine()
    if machine == "arm64":
        return "mac-arm64", "arm64"
    if machine == "x86_64":
        return "mac-x64", "x86_64"
    raise InstallError(f"no Mac app is built for the architecture {machine!r}")


def bundle_facts(app: Path) -> dict:
    """The identifier, the version and the build label of an installed app, from its Info.plist and build-info.json; {} when it is not an app.
    A Windows folder has no Info.plist: everything comes from resources/build-info.json."""
    if windows():
        try:
            record = json.loads((app / "resources" / "build-info.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(record, dict) or not record.get("bundle_id"):
            return {}
        return {"id": record.get("bundle_id"), "version": record.get("version"), "name": record.get("app"), "build": record.get("build", "") or ""}
    try:
        plist = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}
    facts = {"id": plist.get("CFBundleIdentifier"), "version": plist.get("CFBundleShortVersionString"), "name": plist.get("CFBundleName"), "build": ""}
    try:
        facts["build"] = json.loads((app / "Contents" / "Resources" / "build-info.json").read_text(encoding="utf-8")).get("build", "") or ""
    except (OSError, ValueError):
        pass
    return facts


def check_bundle(app: Path, channel: str, version: Optional[str] = None) -> dict:
    """The app at `app` must be the one of `channel` (a beta never goes into the stable app's place, nor the other way round), of `version` when
    given, and its seal must hold."""
    facts = bundle_facts(app)
    want = CHANNELS[channel]["appId"]
    if facts.get("id") != want:
        raise InstallError(f"{app} has the bundle id {facts.get('id')!r}, not {want!r}: it is not the {channel} app")
    if version is not None and facts.get("version") != version:
        raise InstallError(f"{app} is version {facts.get('version')!r}, not {version!r}")
    if windows():                                                             # the Windows beta is not signed: there is no seal to check
        return facts
    sealed = run(["codesign", "--verify", "--deep", "--strict", str(app)])
    if sealed.returncode != 0:
        raise InstallError(f"the signature of {app} does not hold: {(sealed.stderr or sealed.stdout).strip()[:200]}")
    return facts


def running(app: Path) -> list[int]:
    """The processes of `app`: the window, its helpers and the Python server inside it (every command line holds the app's own path)."""
    if windows():                                                             # "<dir>\\Sutra Pro\\" is not "<dir>\\Sutra Pro Beta\\"
        marker = str(app).replace("/", "\\") + "\\"
        return sorted(pid for pid, _parent, command in process_table() if contains(command.replace("/", "\\"), marker) and pid != os.getpid())
    marker = f"{app}/Contents/"
    return sorted(pid for pid, _parent, command in process_table() if marker in command and pid != os.getpid())


def server_of(data: Path) -> Optional[tuple[int, int]]:
    """(pid, port) a server wrote to <data>/app.pid ("<pid> <port>" on the first line), or None."""
    try:
        first = (data / "app.pid").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    found = re.match(r"\s*(\d+)\s+(\d+)", first)
    return (int(found.group(1)), int(found.group(2))) if found else None


def health(port: int) -> Optional[dict]:
    """GET /api/health on loopback: the parsed answer when the server says ok, else None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as answer:
            body = json.loads(answer.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) and body.get("ok") is True else None


def busy_work(data: Path) -> list[str]:
    """What the server of this data folder is doing right now, as command lines: its children (an engine run, the `claude` or `codex` process of a chat turn) and
    any engine process of a run folder below `data`, whoever started it. An idle server has none."""
    table = process_table()
    server = server_of(data)
    found = []
    for pid, parent, command in table:
        if (server and parent == server[0]) or any(contains(command, f"sutra_app.engine --run-dir {data}{sep}") for sep in ("/", "\\")):
            found.append(f"{pid} {command[:110]}")
    return found


def quit_app(app: Path, channel: str, *, force: bool = False) -> bool:
    """Quit `app` the way a person does (Quit in its menu, through its bundle id), after checking that it is not working. True when it was running."""
    if not running(app):
        return False
    working = busy_work(data_dir(channel))
    if working and not force:
        raise Busy(f"{app.name} is working (an engine run or a reply is in progress), so it was not quit:\n    " + "\n    ".join(working[:5])
                   + "\n  wait for it to finish, or run again with --force")
    if windows():
        # the window's own close (WM_CLOSE, what its X does): it stops its server and quits. Never /F: nothing is killed
        pids = set(running(app))
        table = {pid: parent for pid, parent, _command in process_table()}
        for window in sorted(pid for pid in pids if table.get(pid) not in pids):
            run(["taskkill", "/PID", str(window)], timeout=30)
    else:
        run(["osascript", "-e", f'tell application id "{CHANNELS[channel]["appId"]}" to quit'], timeout=30)
    for _ in range(QUIT_TIMEOUT_S):
        if not running(app):
            return True
        sleep(1)
    raise InstallError(f"{app.name} did not quit within {QUIT_TIMEOUT_S} s: quit it yourself, then run this again")


def replace_bundle(source: Path, destination: Path) -> None:
    """Put a copy of the app `source` at `destination`, replacing the one there: the copy is made beside it first and swapped in, so a failed copy leaves the
    old app as it was."""
    fresh = destination.with_name(destination.name + ".new")
    old = destination.with_name(destination.name + ".old")
    for leftover in (fresh, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    if windows():
        try:
            shutil.copytree(source, fresh)
        except OSError as error:
            shutil.rmtree(fresh, ignore_errors=True)
            raise InstallError(f"copying the app into {destination.parent} failed: {error}") from error
    else:
        copied = run(["ditto", str(source), str(fresh)])
        if copied.returncode != 0:
            shutil.rmtree(fresh, ignore_errors=True)
            raise InstallError(f"copying the app into {destination.parent} failed: {(copied.stderr or copied.stdout).strip()[:200]}")
        run(["xattr", "-dr", "com.apple.quarantine", str(fresh)])              # a copy made here carries none; a copy of a download may
    if destination.exists():
        destination.rename(old)
    fresh.rename(destination)
    shutil.rmtree(old, ignore_errors=True)


def start(program: Path) -> None:
    """Start a Windows program on its own, not as a child of this script (it outlives it, and has no console)."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(program)], cwd=str(program.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, creationflags=flags)


def open_and_check(app: Path, channel: str, version: str, *, timeout: float = START_TIMEOUT_S) -> dict:
    """Open the app (Launch Services on a Mac, its exe on Windows) and wait until the server of its data folder answers /api/health with `version`:
    {pid, port, health}."""
    if windows():
        try:
            start(app / f"{CHANNELS[channel]['appName']}.exe")
        except OSError as error:
            raise InstallError(f"could not open {app}: {error}") from error
    else:
        opened = run(["open", "-a", str(app)])
        if opened.returncode != 0:
            raise InstallError(f"could not open {app}: {(opened.stderr or opened.stdout).strip()[:200]}")
    data = data_dir(channel)
    deadline = time.monotonic() + timeout
    last = "the server did not write its pid file"
    while time.monotonic() < deadline:
        server = server_of(data)
        if server:
            answer = health(server[1])
            if answer and answer.get("version") == version:
                return {"pid": server[0], "port": server[1], "health": answer}
            last = f"port {server[1]} answered {answer.get('version') if answer else 'nothing'}"
        sleep(1)
    raise InstallError(f"{app.name} was opened but its server did not answer /api/health with version {version} within {int(timeout)} s ({last}); the log is "
                       f"{home_relative(data / 'logs' / 'desktop.log')}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(file: Path, checksum: Path) -> None:
    """`checksum` holds `<hex>  <name>` (shasum's format) for `file`."""
    words = checksum.read_text(encoding="utf-8").split()
    if not words or not re.fullmatch(r"[0-9a-f]{64}", words[0]):
        raise InstallError(f"{checksum.name} does not hold a SHA-256")
    if len(words) > 1 and words[1].lstrip("*") != file.name:
        raise InstallError(f"{checksum.name} is for {words[1]}, not {file.name}")
    if sha256_of(file) != words[0]:
        raise InstallError(f"{file.name} does not match its published checksum: it was not installed")


def download(url: str, destination: Path) -> None:
    """curl (the system's own trust store, redirects, retries): the release assets of a public repository need no login."""
    done = run(["curl", "-fL", "--silent", "--show-error", "--retry", "3", "-o", str(destination), url], timeout=1800)
    if done.returncode != 0:
        raise InstallError(f"could not download {url}: {(done.stderr or done.stdout).strip()[:200] or 'status ' + str(done.returncode)}")


def newest_release_tag() -> str:
    """The newest stable `sutra-pro-vX.Y.Z` tag of origin."""
    listed = run(["git", "-C", str(ROOT), "ls-remote", "--tags", "--refs", "origin", "refs/tags/sutra-pro-v*"], timeout=120)
    if listed.returncode != 0:
        raise InstallError(f"could not list the tags of origin ({listed.stderr.strip()[:160]}): name the tag, for example sutra-pro-v1.2.3")
    versions = []
    for line in listed.stdout.splitlines():
        tag = line.split("refs/tags/")[-1].strip()
        found = TAG.match(tag)
        if found:
            versions.append((tuple(int(part) for part in found.groups()), tag))
    if not versions:
        raise InstallError("origin has no stable sutra-pro-vX.Y.Z tag")
    return max(versions)[1]


# ---------------------------------------------------------------- beta

def build_label() -> str:
    """What the beta says about the tree it was built from: the short commit id, `+changes` when the working tree differs from it."""
    head = run(["git", "-C", str(ROOT), "rev-parse", "--short=7", "HEAD"])
    if head.returncode != 0 or not head.stdout.strip():
        return "no-git"
    changed = run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no", "--", "."]).stdout.strip()
    return head.stdout.strip() + ("+changes" if changed else "")


def pull_main() -> None:
    """Bring this checkout to its upstream (the beta's checkout follows origin/main): refused when the tree has changes or no upstream, then a fetch and a
    fast-forward. Nothing is built when this fails."""
    changed = run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if changed:
        raise InstallError(f"--pull: this checkout has changes, so it was not pulled (commit or drop them first):\n    {changed.splitlines()[0]}")
    upstream = run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream.returncode != 0 or not upstream.stdout.strip():
        raise InstallError("--pull: this branch has no upstream to pull from (git branch --set-upstream-to origin/main)")
    fetched = run(["git", "-C", str(ROOT), "fetch", "origin"], timeout=300)
    if fetched.returncode != 0:
        raise InstallError(f"--pull: git fetch failed: {(fetched.stderr or fetched.stdout).strip()[-300:]}")
    merged = run(["git", "-C", str(ROOT), "merge", "--ff-only", "@{u}"], timeout=300)
    if merged.returncode != 0:
        raise InstallError(f"--pull: {upstream.stdout.strip()} cannot be fast-forwarded into this branch: "
                           f"{(merged.stderr or merged.stdout).strip()[-300:]}")
    say(f"pulled {upstream.stdout.strip()}")


def write_shortcut(app: Path, channel: str) -> Path:
    """A Start-menu entry for a Windows app (its name, its exe, its folder), written with PowerShell's WScript.Shell; replaced when it exists."""
    name = CHANNELS[channel]["appName"]
    programs = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    link = programs / f"{name}.lnk"
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"           # noqa: E731  (a PowerShell single-quoted string)
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({quote(link)}); $s.TargetPath = {quote(app / (name + '.exe'))}; "
              f"$s.WorkingDirectory = {quote(app)}; $s.Description = {quote(name)}; $s.Save()")
    written = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], timeout=60)
    if written.returncode != 0:
        raise InstallError(f"the Start-menu shortcut was not written: {(written.stderr or written.stdout).strip()[:200]}")
    return link


def install_beta(install_dir: Path, *, launch: bool = True, proof: bool = True, skip_npm: Optional[bool] = None, force: bool = False,
                 dry_run: bool = False, pull: bool = False) -> int:
    target, _arch = host_target()
    if pull and not dry_run:
        pull_main()
    version = project_version()
    label = build_label()
    work = ROOT / "build" / "beta"
    app = bundle("beta", install_dir)
    if skip_npm is None:
        skip_npm = (ROOT / "desktop" / "node_modules").is_dir()
    if dry_run:
        say(f"dry run: nothing is built or installed. The beta of this tree ({version}, {label}) would be:")
        if pull:
            say("  0. git fetch origin, then a fast-forward to this branch's upstream (refused when the tree has changes)")
        say(f"  1. uv build --out-dir {home_relative(work / 'dist')}   (the wheel of this tree, made from its sdist like a release's)")
        say(f"  2. scripts/build_desktop_app.py --channel beta --target {target}   ->  {home_relative(work / 'app' / app.name)}"
            + ("   (npm ci skipped)" if skip_npm else "   (npm ci first)"))
        say("  3. (not signed: Windows)" if windows() else "  3. scripts/sign_desktop_app.sh   (ad hoc)")
        say("  4. scripts/prove_desktop_app.py --no-team   (a throw-away data folder, no network)" if proof else "  4. (no proof: --no-proof)")
        say(f"  5. quit a Sutra Pro Beta that is running and idle, install into {app}")
        say(f"  6. open it and wait for /api/health, version {version}" if launch else "  6. (not opened: --no-launch)")
        say(f"The stable app ({bundle('stable', install_dir)}) and {home_relative(data_dir('stable'))} are not touched. The beta keeps its data in "
            f"{home_relative(data_dir('beta'))}.")
        return 0
    if shutil.which("uv") is None:
        raise InstallError("uv is not installed (https://docs.astral.sh/uv/): it builds the wheel")
    dist = work / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    dist.mkdir(parents=True, exist_ok=True)
    say(f"building the wheel of this tree ({version}, {label}) ...")
    built = run(["uv", "build", "--out-dir", str(dist), str(ROOT)], timeout=1200)
    wheels = sorted(dist.glob("sutra_pro-*.whl"))
    if built.returncode != 0 or len(wheels) != 1:
        raise InstallError(f"uv build failed: {(built.stderr or built.stdout).strip()[-300:]}")
    say("building the app (Electron, the Python inside it, the wheel) ...")
    try:
        made = builder.build_app(wheel=wheels[0], target=target, out=work / "app", skip_npm=skip_npm, channel="beta", build_label=label)
    except builder.BuildError as error:
        raise InstallError(str(error)) from error
    if not windows():                                                         # the Windows beta is not signed (D432)
        say("signing it (ad hoc) ...")
        signed = run(["bash", str(HERE / "sign_desktop_app.sh"), str(made)], timeout=900, env={**os.environ, "SIGN_TIMESTAMP": "none"})
        if signed.returncode != 0:
            raise InstallError(f"signing failed: {(signed.stderr or signed.stdout).strip()[-400:]}")
    if proof:
        say("proving that it starts (a throw-away data folder, no network) ...")
        proved = run([sys.executable, str(HERE / "prove_desktop_app.py"), "--app", str(made), "--version", version, "--no-team"], timeout=900)
        if proved.returncode != 0:
            raise InstallError(f"the beta does not start; nothing was installed:\n{(proved.stderr or proved.stdout).strip()[-600:]}")
    check_bundle(made, "beta", version)
    if quit_app(app, "beta", force=force):
        say("quit the running Sutra Pro Beta")
    replace_bundle(made, app)
    check_bundle(app, "beta", version)
    say(f"installed {app} ({version}, beta {label})")
    if windows():
        say(f"Start menu: {write_shortcut(app, 'beta').name}")
    if launch:
        started = open_and_check(app, "beta", version)
        say(f"Sutra Pro Beta is open: http://127.0.0.1:{started['port']}/ (its own server, process {started['pid']})")
    stable = bundle_facts(bundle("stable", install_dir))
    say(f"data: {home_relative(data_dir('beta'))} (the beta's own; the stable app's {home_relative(data_dir('stable'))} is untouched)")
    say("the stable Sutra Pro " + (f"{stable['version']} is left as it was" if stable else "is not installed here"))
    return 0


# ---------------------------------------------------------------- release

def install_release(tag: Optional[str], install_dir: Path, *, launch: bool = True, cli: bool = True, force: bool = False, dry_run: bool = False) -> int:
    if windows():
        raise InstallError("a release is installed by this script on a Mac only: on Windows, run the Setup .exe of the release (its GitHub page)")
    _target, arch = host_target()
    tag = tag or newest_release_tag()
    found = TAG.match(tag)
    if not found:
        raise InstallError(f"{tag!r} is not a stable release tag (sutra-pro-vX.Y.Z): a beta tag is never installed as the app")
    version = ".".join(found.groups())
    app = bundle("stable", install_dir)
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    dmg, wheel = f"Sutra-Pro-{arch}.dmg", f"sutra_pro-{version}-py3-none-any.whl"
    if dry_run:
        say(f"dry run: nothing is downloaded or installed. Release {tag} would be installed like this:")
        say(f"  1. download {base}/{dmg} and {dmg}.sha256 (and {wheel} with its .sha256), check the checksums")
        say(f"  2. quit {app.name} when it is running and idle (busy: stop, exit status 3)")
        say(f"  3. replace {app} from the DMG, check its bundle id, version {version} and signature")
        say("  4. uv tool install --reinstall <the wheel>" if cli else "  4. (the command is not reinstalled: --no-cli)")
        say(f"  5. open it and wait for /api/health, version {version}" if launch else "  5. (not opened: --no-launch)")
        say(f"{home_relative(data_dir('stable'))} is not touched by the install.")
        return 0
    work = Path(tempfile.mkdtemp(prefix="sutra-release-"))
    mount = work / "mount"
    mounted = False
    try:
        say(f"downloading {tag} ({dmg}) ...")
        for name in (dmg, dmg + ".sha256"):
            download(f"{base}/{name}", work / name)
        verify_checksum(work / dmg, work / (dmg + ".sha256"))
        say("the checksum matches")
        if cli:
            for name in (wheel, wheel + ".sha256"):
                download(f"{base}/{name}", work / name)
            verify_checksum(work / wheel, work / (wheel + ".sha256"))
        mount.mkdir()
        attached = run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(work / dmg)], timeout=300)
        if attached.returncode != 0:
            raise InstallError(f"could not open the disk image: {(attached.stderr or attached.stdout).strip()[:200]}")
        mounted = True
        inside = mount / app.name
        if not inside.is_dir():
            raise InstallError(f"the disk image holds no {app.name}")
        check_bundle(inside, "stable", version)
        if quit_app(app, "stable", force=force):
            say(f"quit the running {app.name}")
        replace_bundle(inside, app)
        check_bundle(app, "stable", version)
        say(f"installed {app} ({version})")
        if cli:
            if shutil.which("uv") is None:
                say("the sutra-pro command was not reinstalled: uv is not installed (https://docs.astral.sh/uv/)")
            else:
                installed = run(["uv", "tool", "install", "--reinstall", str(work / wheel)], timeout=600)
                if installed.returncode != 0:
                    raise InstallError(f"uv tool install failed: {(installed.stderr or installed.stdout).strip()[-300:]}")
                listed = run(["uv", "tool", "list"]).stdout
                if f"sutra-pro v{version}" not in listed:
                    raise InstallError(f"uv tool list does not show sutra-pro v{version} after the install")
                say(f"the sutra-pro command is {version}")
    finally:
        if mounted:
            if run(["hdiutil", "detach", str(mount)]).returncode != 0:
                run(["hdiutil", "detach", "-force", str(mount)])
        shutil.rmtree(work, ignore_errors=True)
    if launch:
        started = open_and_check(app, "stable", version)
        say(f"Sutra Pro {version} is open: http://127.0.0.1:{started['port']}/ (process {started['pid']})")
    say(f"data: {home_relative(data_dir('stable'))} (not touched by the install)")
    return 0


# ---------------------------------------------------------------- status

def status(install_dir: Path) -> int:
    for channel in ("stable", "beta"):
        app = bundle(channel, install_dir)
        facts = bundle_facts(app)
        data = data_dir(channel)
        server = server_of(data)
        answer = health(server[1]) if server else None
        label = CHANNELS[channel]["appName"]
        if not facts:
            say(f"{label}: not installed ({app})")
        else:
            build = f", built from {facts['build']}" if facts.get("build") else ""
            say(f"{label}: {facts['version']}{build}, {app}; " + ("running" if running(app) else "not running")
                + (f", server on port {server[1]} ({answer.get('version')})" if answer else ""))
        say(f"  data: {home_relative(data)} ({'exists' if data.is_dir() else 'not created yet'})")
    listed = run(["uv", "tool", "list"]).stdout if shutil.which("uv") else ""
    command = re.search(r"^sutra-pro v\S+", listed, re.M)
    say(f"the sutra-pro command: {command.group(0)[len('sutra-pro '):] if command else 'not installed with uv'}")
    return 0


# ---------------------------------------------------------------- command line

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Install Sutra Pro: a beta built from this working tree (a Mac or a Windows PC), or a published "
                                                 "release (a Mac).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--install-dir", type=Path, default=default_install_dir(),
                        help="where the apps are (default /Applications; on Windows %%LOCALAPPDATA%%\\Programs)")
    commands = parser.add_subparsers(dest="command", required=True)
    beta = commands.add_parser("beta", parents=[common], help="build Sutra Pro Beta from this working tree and install it beside the stable app")
    beta.add_argument("--no-proof", action="store_true", help="skip the proof that the built app starts")
    beta.add_argument("--no-launch", action="store_true", help="do not open it afterwards")
    beta.add_argument("--skip-npm", action="store_true", default=None, help="reuse desktop/node_modules (the default when it exists)")
    beta.add_argument("--force", action="store_true", help="quit a running beta even when it is working")
    beta.add_argument("--dry-run", action="store_true", help="say what would happen and do nothing")
    beta.add_argument("--pull", action="store_true", help="first bring this checkout to its upstream (origin/main for the beta's checkout)")
    release = commands.add_parser("release", parents=[common], help="install a published release as the stable app")
    release.add_argument("tag", nargs="?", default=None, help="sutra-pro-vX.Y.Z (default: the newest stable tag of origin)")
    release.add_argument("--no-cli", action="store_true", help="do not reinstall the sutra-pro command")
    release.add_argument("--no-launch", action="store_true", help="do not open it afterwards")
    release.add_argument("--force", action="store_true", help="quit the running app even when it is working")
    release.add_argument("--dry-run", action="store_true", help="say what would happen and do nothing")
    commands.add_parser("status", parents=[common], help="what is installed and running")
    args = parser.parse_args(argv)
    try:
        if args.command == "beta":
            return install_beta(args.install_dir, launch=not args.no_launch, proof=not args.no_proof, skip_npm=args.skip_npm, force=args.force,
                                dry_run=args.dry_run, pull=args.pull)
        if args.command == "release":
            return install_release(args.tag, args.install_dir, launch=not args.no_launch, cli=not args.no_cli, force=args.force, dry_run=args.dry_run)
        return status(args.install_dir)
    except Busy as error:
        print(f"error: {error}", file=sys.stderr)
        return BUSY
    except InstallError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
