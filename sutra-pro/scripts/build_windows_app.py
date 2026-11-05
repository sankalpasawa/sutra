#!/usr/bin/env python3
"""Build the Windows app folder: a bundled CPython + the sutra-pro wheel installed into it + launchers (D101, D102).

    python scripts/build_windows_app.py --wheel dist/sutra_pro-0.1.0-py3-none-any.whl --out build
    python scripts/build_windows_app.py --wheel W --out build --python-archive cpython-...-windows-msvc-install_only_stripped.tar.gz

The Windows twin of scripts/build_macos_app.py, with the same rules: the interpreter comes from python-build-standalone (the release
pinned there, the sha256 checked, the download cached), the wheel is installed by running that interpreter, nothing is signed here.
Layout of `<out>/Sutra Pro/` (the folder the installer copies and the portable zip holds):

    python/                       CPython 3.11 with sutra-pro and its dependencies (and the tray extra: pystray, Pillow) installed
    python/SutraPro.exe           a copy of pythonw.exe: the app's process, so Task Manager says SutraPro and no console opens
    Sutra Pro.cmd                 start the app (portable use; the installer makes Start menu shortcuts that do the same)
    Quit Sutra Pro.cmd            ask the running app to stop (`sutra-pro stop`: it writes app.stop, which the server polls)
    sutra-pro.cmd                 the command line (`sutra-pro.cmd doctor | status | stop | config ...`)
    icon/sutra-pro.ico            the icon of the shortcuts
    build-info.json               what went in (version, archive name and sha256, wheel name and sha256)
    README.txt                    how to start it, where the data and the log are, what SmartScreen will say

Every launcher runs the interpreter with `-I` (no PYTHON* variables, no user site: a user's own Python setup cannot break the app)
and `-X utf8` (every file opened without an encoding is UTF-8, not the console's code page).

Exit status: 0 built; 1 the build was refused or failed (one `error:` line); 2 bad command line.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_macos_app as common                                     # noqa: E402  (the verified download, the wheel reader, the safe unpack)
from build_macos_app import BuildError, Fetch, WheelInfo, fetch_url, read_wheel, sha256_of   # noqa: E402

ROOT = HERE.parent
APP_NAME = "Sutra Pro"
TARGET = "win-x64"
ICON = ROOT / "assets" / "icon" / "sutra-pro.ico"
EXE_NAME = "SutraPro.exe"
INTERPRETER_FLAGS = "-I -X utf8"

READ_ME = """Sutra Pro {version}

Start it:      double-click "Sutra Pro.cmd" (or the Start menu entry, when you used the installer).
               It starts a local server on 127.0.0.1 (the first free port from 8780 to 8799) and opens your browser on it.
               An icon appears in the notification area: Open Sutra Pro, Quit Sutra Pro.
Stop it:       the icon's Quit, or "Quit Sutra Pro.cmd".
Your data:     %USERPROFILE%\\.sutra-pro   (the database, the departments, the runs, the logs, the backups)
The log:       %USERPROFILE%\\.sutra-pro\\logs\\app.log   and, for a start that failed before logging began, desktop.log
Command line:  sutra-pro.cmd doctor | status | stop | config | open     (doctor checks the machine, Claude, Codex, Chrome)

Sutra Pro runs the `claude` and `codex` command line tools you already signed in to. It never asks for an API key.

This build is not signed. Windows SmartScreen may say "Windows protected your PC" the first time:
choose "More info", then "Run anyway". The file's SHA-256 is published next to it on the release page.
"""


def host_is_windows_x64() -> bool:
    return sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64")


def extract_windows_python(archive_path: Path, dest: Path) -> Path:
    """Unpack a python-build-standalone `install_only` archive for Windows (one top folder, `python/`) into `dest`."""
    import tarfile
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path, "r:*") as archive:
            members = list(common.safe_members(archive, dest))
            if hasattr(tarfile, "data_filter"):
                archive.extractall(dest, members=members, filter="data")
            else:
                archive.extractall(dest, members=members)
    except (tarfile.TarError, EOFError) as error:
        raise BuildError(f"cannot unpack {archive_path.name}: {error}") from error
    interpreter = dest / "python" / "python.exe"
    if not interpreter.exists():
        raise BuildError(f"{archive_path.name} did not contain python/python.exe")
    return interpreter


def install_wheel(interpreter: Path, wheel: WheelInfo) -> None:
    """Install the wheel with its `desktop` extra (the tray icon) and its dependencies, with the bundled interpreter, then prove that it imports.

    pip writes console scripts into python/Scripts with the absolute path of THIS build folder; once the folder is copied somewhere
    else they would point at nothing. The app starts `python -m sutra_app`, so every script pip added is removed."""
    scripts = interpreter.parent / "Scripts"
    before = common.listing(scripts)
    requirement = f"sutra-pro[desktop] @ {wheel.path.resolve().as_uri()}"
    common.run_bundled(interpreter, ["-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--no-warn-script-location",
                                     requirement], "pip install of the wheel")
    for name in sorted(common.listing(scripts) - before):
        path = scripts / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
    probe = common.run_bundled(
        interpreter, ["-I", "-c", "import importlib.metadata as m, sutra_app, pystray, PIL; print(m.version('sutra-pro'))"],
        "importing sutra_app and the tray from the bundle")
    installed = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
    if installed != wheel.version:
        raise BuildError(f"the bundle reports sutra-pro {installed!r} but the wheel is {wheel.version!r}")


def launcher_files() -> dict[str, str]:
    """The .cmd files, by name. CRLF line endings are written by `write_launchers`."""
    exe = rf'"%~dp0python\{EXE_NAME}"'
    py = r'"%~dp0python\python.exe"'
    return {
        "Sutra Pro.cmd": f'@echo off\r\nstart "" {exe} {INTERPRETER_FLAGS} -m sutra_app.desktop %*\r\n',
        "Quit Sutra Pro.cmd": f"@echo off\r\n{py} {INTERPRETER_FLAGS} -m sutra_app stop %*\r\npause\r\n",
        "sutra-pro.cmd": f"@echo off\r\n{py} {INTERPRETER_FLAGS} -m sutra_app %*\r\n",
    }


def write_launchers(app: Path) -> None:
    for name, text in launcher_files().items():
        (app / name).write_bytes(text.encode("ascii"))


def build_app(*, wheel: Path, out: Path, python_archive: Optional[Path] = None, cache_dir: Optional[Path] = None,
              fetch: Fetch = fetch_url, allow_foreign_host: bool = False) -> Path:
    """Build `<out>/Sutra Pro/` and return its path. Replaces a folder of that name already in `out`; touches nothing else."""
    if not host_is_windows_x64() and not allow_foreign_host:
        raise BuildError("the bundle is built on Windows x64: the wheel is installed by running the bundled python.exe (the workflow does)")
    info = read_wheel(wheel)
    if python_archive is not None:
        if not python_archive.is_file():
            raise BuildError(f"python archive not found: {python_archive}")
        archive, archive_sha = python_archive, sha256_of(python_archive)
    else:
        archive, archive_sha = common.resolve_archive(TARGET, cache_dir or common.default_cache_dir(), fetch)
    if not ICON.is_file():
        raise BuildError(f"the icon is missing: {ICON}")

    out.mkdir(parents=True, exist_ok=True)
    final = out / APP_NAME
    stage = Path(tempfile.mkdtemp(prefix=".sutra-pro-build-", dir=out))      # a failed build never leaves a half folder under the final name
    try:
        app = stage / APP_NAME
        app.mkdir()
        interpreter = extract_windows_python(archive, app)
        install_wheel(interpreter, info)
        pythonw = interpreter.parent / "pythonw.exe"
        if not pythonw.exists():
            raise BuildError("the interpreter archive has no pythonw.exe")
        shutil.copyfile(pythonw, interpreter.parent / EXE_NAME)
        (app / "icon").mkdir()
        shutil.copyfile(ICON, app / "icon" / ICON.name)
        write_launchers(app)
        (app / "README.txt").write_bytes(READ_ME.format(version=info.version).replace("\n", "\r\n").encode("utf-8"))
        (app / "build-info.json").write_text(json.dumps({
            "app": APP_NAME, "version": info.version, "target": TARGET, "python_archive": archive.name, "python_archive_sha256": archive_sha,
            "wheel": wheel.name, "wheel_sha256": info.sha256}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if final.exists():
            shutil.rmtree(final)
        app.rename(final)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return final


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Windows app folder (bundled CPython + the wheel + launchers). Never signs.")
    parser.add_argument("--wheel", required=True, type=Path, help="the sutra_pro-X.Y.Z-py3-none-any.whl to install into the bundle")
    parser.add_argument("--out", required=True, type=Path, help="folder that receives 'Sutra Pro'")
    parser.add_argument("--python-archive", type=Path, default=None,
                        help="a local python-build-standalone archive to use instead of downloading one (trusted as given)")
    parser.add_argument("--cache-dir", type=Path, default=None, help="download cache (default: $SUTRA_BUNDLE_CACHE or ~/.cache/sutra-pro-bundle)")
    parser.add_argument("--allow-foreign-host", action="store_true", help="skip the Windows x64 check (tests with a fake interpreter)")
    args = parser.parse_args(argv)
    try:
        app = build_app(wheel=args.wheel, out=args.out, python_archive=args.python_archive, cache_dir=args.cache_dir,
                        allow_foreign_host=args.allow_foreign_host)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"built {app} ({TARGET})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
