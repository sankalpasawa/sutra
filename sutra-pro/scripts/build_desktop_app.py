#!/usr/bin/env python3
"""Build the desktop app: the Electron window (desktop/) + a bundled CPython + the sutra-pro wheel installed into it (D105, D108).

    scripts/py scripts/build_desktop_app.py --wheel dist/sutra_pro-0.2.0-py3-none-any.whl --target mac-arm64 --out build
    scripts/py scripts/build_desktop_app.py --wheel W --target win-x64 --out build
    scripts/py scripts/build_desktop_app.py --wheel W --target mac-x64 --out build --python-archive cpython-...tar.gz --skip-npm   # offline

Targets: mac-arm64 and mac-x64 (built on a Mac of that architecture) and win-x64 (built on Windows x64): the wheel is installed by RUNNING the
bundled interpreter, which a foreign system or architecture cannot do. The steps:

  1. `npm ci` in desktop/ (the exact versions of the lock file; `--skip-npm` when node_modules is already there)
  2. `node scripts/package.mjs`: the packager puts Electron and desktop/src into "Sutra Pro.app" (or the Windows folder)
  3. the interpreter archive of python-build-standalone is unpacked into the app's resources, verified against its sha256 like the other
     bundles (scripts/build_macos_app.py), the wheel and its dependencies are installed into it, and the install is proved by importing it
  4. the whole library (the standard library and site-packages) is compiled to bytecode that is never checked against its source: the interpreter
     ships with none, and the first Python process that imports without `-B` would write it INTO the signed app and break its seal (the release proof
     found 42 files written by an engine process); with it the server also starts in a third of the time
  5. build-info.json says what went in; every symbolic link is checked to stay inside the app

Layout of `<out>/Sutra Pro.app`:  Contents/Resources/python/ (the interpreter and the app), Contents/Resources/build-info.json
Layout of `<out>/Sutra Pro/`:     `Sutra Pro.exe`, resources/python/, resources/build-info.json (what the installer copies and the zip holds)

The interpreter is unpacked straight into the package because the packager rewrites a relative symbolic link as an absolute one when it
copies an extra resource (found by the old product's make-dmg.sh: all eleven links pointed at the build machine). This script never signs;
scripts/sign_desktop_app.sh signs the Mac app afterwards and the workflows notarize.

Exit status: 0 built; 1 the build was refused or failed (one `error:` line); 2 bad command line.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_macos_app as common                                     # noqa: E402  (the verified download, the wheel reader, the safe unpack)
import build_windows_app as windows                                  # noqa: E402  (the Windows interpreter unpack)
from build_macos_app import BuildError, Fetch, fetch_url, read_wheel, sha256_of   # noqa: E402

ROOT = HERE.parent
DESKTOP = ROOT / "desktop"
APP_NAME = "Sutra Pro"
BUNDLE_ID = "os.sutra.pro"


@dataclass(frozen=True)
class Target:
    name: str
    platform: str           # Electron's: darwin or win32
    arch: str               # Electron's: arm64 or x64
    archive: str            # the key of build_macos_app.TRIPLES the interpreter archive is looked up by

    @property
    def windows(self) -> bool:
        return self.platform == "win32"


TARGETS = {
    "mac-arm64": Target("mac-arm64", "darwin", "arm64", "arm64"),
    "mac-x64": Target("mac-x64", "darwin", "x64", "x86_64"),
    "win-x64": Target("win-x64", "win32", "x64", "win-x64"),
}

Packager = Callable[[Target, Path, str], Path]


def host_can_build(target: Target) -> bool:
    if target.windows:
        return windows.host_is_windows_x64()
    return sys.platform == "darwin" and common.host_arch() == ("arm64" if target.arch == "arm64" else "x86_64")


def tool(name: str) -> str:
    """The path of a program on PATH (`npm` is npm.cmd on Windows, which subprocess cannot find by its short name)."""
    found = shutil.which(name)
    if found is None:
        raise BuildError(f"{name} is not on PATH: the desktop app is built with Node 22 or newer (https://nodejs.org)")
    return found


def run_tool(args: list[str], what: str, cwd: Path) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BuildError(f"{what}: cannot run it ({error})") from error
    if done.returncode != 0:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-20:])
        raise BuildError(f"{what} failed (exit {done.returncode}):\n{tail}")
    return done


def package_window(target: Target, stage: Path, version: str, *, skip_npm: bool = False) -> Path:
    """Run `npm ci` and desktop/scripts/package.mjs; return the packaged app ("Sutra Pro.app" or the Windows folder), inside `stage`."""
    if not skip_npm:
        run_tool([tool("npm"), "ci", "--no-audit", "--no-fund"], "npm ci", DESKTOP)
    elif not (DESKTOP / "node_modules").is_dir():
        raise BuildError("--skip-npm was given but desktop/node_modules is not there: run `npm ci` in desktop/")
    done = run_tool([tool("node"), "scripts/package.mjs", "--platform", target.platform, "--arch", target.arch, "--out", str(stage), "--version", version],
                    "the Electron packager", DESKTOP)
    packaged = [line.split(" ", 1)[1].strip() for line in done.stdout.splitlines() if line.startswith("PACKAGED ")]
    if len(packaged) != 1 or not Path(packaged[0]).exists():
        raise BuildError(f"the packager did not say where the app is:\n{done.stdout.strip()[-400:]}")
    return Path(packaged[0])


def resources_of(app: Path, target: Target) -> Path:
    return app / "Contents" / "Resources" if not target.windows else app / "resources"


def install_wheel(interpreter: Path, wheel: common.WheelInfo, *, scripts_dir: str) -> None:
    """Install the wheel and its dependencies with the bundled interpreter and prove it imports there.

    pip writes console scripts with the absolute path of THIS build folder; once the app is copied they would point at nothing (and a space in
    the path breaks a shebang). The app starts `python -m sutra_app`, so every script pip added to `bin` (`Scripts` on Windows) is removed."""
    scripts = interpreter.parent if scripts_dir == "." else interpreter.parent / scripts_dir
    before = common.listing(scripts)
    common.run_bundled(interpreter, ["-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--no-warn-script-location", str(wheel.path)],
                       "pip install of the wheel")
    for name in sorted(common.listing(scripts) - before):
        path = scripts / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
    probe = common.run_bundled(interpreter, ["-I", "-c", "import importlib.metadata as m, sutra_app; print(m.version('sutra-pro'))"],
                               "importing sutra_app from the app")
    installed = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
    if installed != wheel.version:
        raise BuildError(f"the app reports sutra-pro {installed!r} but the wheel is {wheel.version!r}")


WINDOWS_READ_ME = """Sutra Pro {version}

Start it:      the Start menu entry "Sutra Pro", or double-click "Sutra Pro.exe". A window opens on the app, which runs a local server on 127.0.0.1
               (the first free port from 8780 to 8799). Closing the window stops the server.
Your data:     %USERPROFILE%\\.sutra-pro   (the database, the departments, the runs, the logs, the backups)
The logs:      %USERPROFILE%\\.sutra-pro\\logs\\desktop.log (the window and what the server printed to it) and app.log (the server's own)
Command line:  sutra-pro.cmd doctor | status | stop | config | open     (doctor checks the machine, Claude, Codex, Chrome)

Sutra Pro runs the `claude` and `codex` command line tools you already signed in to. It never asks for an API key.

This build is not signed. Windows SmartScreen may say "Windows protected your PC" the first time:
choose "More info", then "Run anyway". The file's SHA-256 is published next to it on the release page.
"""


def write_windows_extras(app: Path, version: str) -> None:
    """The files beside `Sutra Pro.exe` that are not Electron's: `sutra-pro.cmd` (the command line of the Python inside the app; `-I` keeps a user's own
    Python setup out of it, `-B` writes no bytecode into the installed folder, `-X utf8` makes a file opened without an encoding UTF-8) and README.txt. Both with the CRLF line endings of Windows."""
    (app / "sutra-pro.cmd").write_bytes(b'@echo off\r\n"%~dp0resources\\python\\python.exe" -I -B -X utf8 -m sutra_app %*\r\n')
    (app / "README.txt").write_bytes(WINDOWS_READ_ME.format(version=version).replace("\n", "\r\n").encode("utf-8"))


def precompile(interpreter: Path, *, windows: bool) -> None:
    """Compile the interpreter's whole library to bytecode that is never checked against its source (`unchecked-hash`), so that nothing has to be written
    into the app when it runs. python-build-standalone ships no bytecode, and pip, run here with PYTHONDONTWRITEBYTECODE, writes none. Without this every
    start of the server compiles about a second of imports, and any Python process that is not told `-B` (an engine process, `sutra-pro doctor`) writes the
    files into the app, which breaks the seal of a signed app. Nobody edits a source inside an app, so a hash that is not checked cannot go stale.
    A file that does not compile is a warning, not a failure (a test fixture with deliberately bad syntax): what matters is that the library is there."""
    series = common.PY_SERIES
    root = interpreter.parent / "Lib" if windows else interpreter.parent.parent / "lib" / f"python{series}"
    marker = root / "__pycache__" / f"os.cpython-{series.replace('.', '')}.pyc"
    try:
        common.run_bundled(interpreter, ["-I", "-m", "compileall", "-q", "-f", "--invalidation-mode", "unchecked-hash", "-j", "0", str(root)],
                           "compiling the library")
    except BuildError as error:
        if not marker.is_file():
            raise
        print(f"warning: {error}", file=sys.stderr)
    if not marker.is_file():
        raise BuildError(f"compiling the library left no bytecode ({marker} is missing)")


def check_links(root: Path) -> None:
    """Every symbolic link in the app resolves to something inside it: an absolute link or one that climbs out would point at the build machine
    (codesign rejects it as 'invalid destination for symbolic link in bundle', and on a user's machine it is simply dangling)."""
    base = root.resolve()
    bad = []
    for path in root.rglob("*"):
        if path.is_symlink():
            target = os.readlink(path)
            resolved = (path.parent / target).resolve() if not os.path.isabs(target) else Path(target)
            if os.path.isabs(target) or (base != resolved and base not in resolved.parents):
                bad.append(f"{path.relative_to(root)} -> {target}")
    if bad:
        raise BuildError("symbolic links that do not stay inside the app:\n  " + "\n  ".join(bad[:10]))


def build_app(*, wheel: Path, target: str, out: Path, python_archive: Optional[Path] = None, cache_dir: Optional[Path] = None,
              fetch: Fetch = fetch_url, skip_npm: bool = False, package: Optional[Packager] = None, allow_foreign_host: bool = False) -> Path:
    """Build `<out>/Sutra Pro.app` (or `<out>/Sutra Pro`) and return its path. Replaces one of that name already in `out`; touches nothing else.
    `package` replaces the Electron packager (tests)."""
    if target not in TARGETS:
        raise BuildError(f"unsupported target {target!r} ({', '.join(TARGETS)})")
    spec = TARGETS[target]
    if not allow_foreign_host and not host_can_build(spec):
        raise BuildError(f"this machine cannot build {target}: the wheel is installed by running the bundled interpreter, so build on a "
                         f"machine of the target system and architecture (the workflow does)")
    info = read_wheel(wheel)
    if python_archive is not None:
        if not python_archive.is_file():
            raise BuildError(f"python archive not found: {python_archive}")
        archive, archive_sha = python_archive, sha256_of(python_archive)
    else:
        archive, archive_sha = common.resolve_archive(spec.archive, cache_dir or common.default_cache_dir(), fetch)

    out.mkdir(parents=True, exist_ok=True)
    final = out / (f"{APP_NAME}.app" if not spec.windows else APP_NAME)
    stage = Path(tempfile.mkdtemp(prefix=".sutra-pro-build-", dir=out))      # a failed build never leaves a half app under the final name
    try:
        app = (package or (lambda t, s, v: package_window(t, s, v, skip_npm=skip_npm)))(spec, stage, info.version)
        resources = resources_of(app, spec)
        if not resources.is_dir():
            raise BuildError(f"the packaged app has no resources folder: {resources}")
        if spec.windows:
            interpreter = windows.extract_windows_python(archive, resources)
            install_wheel(interpreter, info, scripts_dir="Scripts")
        else:
            interpreter = common.extract_python(archive, resources)
            install_wheel(interpreter, info, scripts_dir=".")
        precompile(interpreter, windows=spec.windows)
        if spec.windows:
            write_windows_extras(app, info.version)
        (resources / "build-info.json").write_text(json.dumps({
            "app": APP_NAME, "bundle_id": BUNDLE_ID, "version": info.version, "target": target, "shell": "electron",
            "electron": json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))["devDependencies"]["electron"],
            "python_archive": archive.name, "python_archive_sha256": archive_sha, "wheel": wheel.name, "wheel_sha256": info.sha256,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        check_links(app)
        if final.exists():
            shutil.rmtree(final)
        app.rename(final)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return final


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the desktop app (Electron window + bundled CPython + the wheel). Never signs.")
    parser.add_argument("--wheel", required=True, type=Path, help="the sutra_pro-X.Y.Z-py3-none-any.whl to install into the app")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS), help="what to build (on a machine of that system and architecture)")
    parser.add_argument("--out", required=True, type=Path, help="folder that receives 'Sutra Pro.app' or 'Sutra Pro'")
    parser.add_argument("--python-archive", type=Path, default=None,
                        help="a local python-build-standalone archive to use instead of downloading one (trusted as given)")
    parser.add_argument("--cache-dir", type=Path, default=None, help="download cache (default: $SUTRA_BUNDLE_CACHE or ~/.cache/sutra-pro-bundle)")
    parser.add_argument("--skip-npm", action="store_true", help="do not run `npm ci`: desktop/node_modules is already installed")
    args = parser.parse_args(argv)
    try:
        app = build_app(wheel=args.wheel, target=args.target, out=args.out, python_archive=args.python_archive, cache_dir=args.cache_dir,
                        skip_npm=args.skip_npm)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"built {app} ({args.target})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
