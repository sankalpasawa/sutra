"""scripts/build_windows_app.py and what ships with it (D101, D102): the app folder, its launchers, the installer script, the icons.

The builder installs the wheel by RUNNING the bundled python.exe, which only a Windows machine can do, so these tests give it a fake
interpreter (a script named python.exe, runnable on any system with `allow_foreign_host=True`) and check what the builder does around
it: the layout, the pip call, the clean-up, every refusal. That the real folder runs is proved by scripts/prove_windows_app.py in the
release workflow, on a Windows runner, before anything is uploaded.
"""
import importlib.util
import io
import json
import os
import re
import struct
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_windows_app.py"
INSTALLER = ROOT / "scripts" / "windows" / "sutra-pro.iss"
ICONS = ROOT / "assets" / "icon"

sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("build_windows_app", SCRIPT)
bwa = importlib.util.module_from_spec(_spec)
sys.modules["build_windows_app"] = bwa
_spec.loader.exec_module(bwa)
common = bwa.common


def make_wheel(directory, *, version="0.1.0"):
    path = directory / f"sutra_pro-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sutra_app/__init__.py", "")
        archive.writestr("sutra_pro-0.0.0.dist-info/METADATA", f"Metadata-Version: 2.1\nName: sutra-pro\nVersion: {version}\nSummary: x\n")
    return path


FAKE_PYTHON = '''#!{python}
# a fake python.exe: logs its calls and "installs" the wheel the way pip would, console scripts included
import json, os, sys, zipfile
root = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(root, "calls.log"), "a") as log:
    log.write(json.dumps(args) + "\\n")
REPORT = {report!r}
if args[:2] == ["-m", "pip"]:
    requirement = args[-1]
    wheel_uri = requirement.split(" @ ", 1)[1]
    with zipfile.ZipFile(wheel_uri.replace("file://", "", 1)) as z:
        meta = [n for n in z.namelist() if n.endswith("METADATA")][0]
        version = [l for l in z.read(meta).decode().splitlines() if l.startswith("Version:")][0].split(":")[1].strip()
    open(os.path.join(root, "installed-version"), "w").write(version)
    for script in ("sutra-pro.exe", "uvicorn.exe"):
        open(os.path.join(root, "Scripts", script), "w").write("MZ")
elif "-c" in args:
    print("a warning line")
    print(REPORT or open(os.path.join(root, "installed-version")).read())
'''


def make_archive(directory, *, report=None, with_python=True, with_pythonw=True, extra=()):
    path = directory / "cpython-3.11.16+20260901-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for folder in ("python", "python/Scripts", "python/Lib"):
            info = tarfile.TarInfo(folder)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(info)
        if with_python:
            body = FAKE_PYTHON.format(python=sys.executable, report=report).encode()
            info = tarfile.TarInfo("python/python.exe")
            info.size, info.mode = len(body), 0o755
            archive.addfile(info, io.BytesIO(body))
        if with_pythonw:
            body = b"pythonw bytes"
            info = tarfile.TarInfo("python/pythonw.exe")
            info.size, info.mode = len(body), 0o755
            archive.addfile(info, io.BytesIO(body))
        for member in extra:
            archive.addfile(*member)
    return path


@pytest.fixture
def work(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    return tmp_path


def build(work, *, wheel=None, archive=None, **kwargs):
    if sys.platform == "win32":
        pytest.skip("the fake interpreter is a shebang script; the real build runs in the release workflow")
    return bwa.build_app(wheel=wheel or make_wheel(work / "in"), out=work / "out", python_archive=archive or make_archive(work / "in"),
                         allow_foreign_host=True, **kwargs)


# ================================================================ the folder

def test_the_app_folder_has_the_documented_layout(work):
    app = build(work)
    assert app == work / "out" / "Sutra Pro"
    for name in ("python/python.exe", "python/pythonw.exe", "python/SutraPro.exe", "icon/sutra-pro.ico", "Sutra Pro.cmd",
                 "Quit Sutra Pro.cmd", "sutra-pro.cmd", "README.txt", "build-info.json"):
        assert (app / name).is_file(), name
    assert (app / "python" / "SutraPro.exe").read_bytes() == (app / "python" / "pythonw.exe").read_bytes(), "SutraPro.exe is a copy of pythonw.exe"
    assert (app / "icon" / "sutra-pro.ico").read_bytes() == (ICONS / "sutra-pro.ico").read_bytes()


def test_the_wheel_is_installed_with_the_tray_extra_by_the_bundled_interpreter(work):
    app = build(work)
    calls = [json.loads(line) for line in (app / "python" / "calls.log").read_text().splitlines()]
    pip = next(c for c in calls if c[:2] == ["-m", "pip"])
    assert pip[2] == "install" and "--no-warn-script-location" in pip
    requirement = pip[-1]
    assert requirement.startswith("sutra-pro[desktop] @ file://") and requirement.endswith(".whl")
    probe = next(c for c in calls if "-c" in c)
    assert probe[0] == "-I" and "pystray" in probe[-1] and "sutra_app" in probe[-1], "the probe proves the tray can be imported too"


def test_the_console_scripts_pip_wrote_are_removed(work):
    app = build(work)
    assert list((app / "python" / "Scripts").iterdir()) == [], "a console script names the build folder, and would point at nothing once the app is copied"


def test_build_info_says_what_went_in(work):
    wheel = make_wheel(work / "in", version="2.3.4")
    archive = make_archive(work / "in")
    info = json.loads((build(work, wheel=wheel, archive=archive) / "build-info.json").read_text())
    assert info["version"] == "2.3.4" and info["target"] == "win-x64" and info["wheel"] == wheel.name
    assert info["python_archive"] == archive.name and re.fullmatch(r"[0-9a-f]{64}", info["python_archive_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", info["wheel_sha256"])


def test_the_readme_names_the_version_the_data_and_what_smartscreen_says(work):
    text = (build(work, wheel=make_wheel(work / "in", version="9.8.7")) / "README.txt").read_bytes().decode("utf-8")
    assert "Sutra Pro 9.8.7" in text and ".sutra-pro" in text and "SmartScreen" in text and "Run anyway" in text
    assert "\r\n" in text and "\n" not in text.replace("\r\n", ""), "Windows line endings"


# ================================================================ the launchers

def test_the_launchers_run_the_bundled_interpreter_isolated_and_in_utf8_mode(work):
    app = build(work)
    start = (app / "Sutra Pro.cmd").read_bytes().decode("ascii")
    assert start == '@echo off\r\nstart "" "%~dp0python\\SutraPro.exe" -I -X utf8 -m sutra_app.desktop %*\r\n'
    quit_ = (app / "Quit Sutra Pro.cmd").read_bytes().decode("ascii")
    assert '"%~dp0python\\python.exe" -I -X utf8 -m sutra_app stop %*' in quit_
    cli = (app / "sutra-pro.cmd").read_bytes().decode("ascii")
    assert cli == '@echo off\r\n"%~dp0python\\python.exe" -I -X utf8 -m sutra_app %*\r\n'
    for text in (start, quit_, cli):
        assert "\r\n" in text and "\n" not in text.replace("\r\n", "")


def test_the_installer_script_uses_the_same_commands_as_the_launchers():
    iss = INSTALLER.read_text(encoding="utf-8")
    assert bwa.INTERPRETER_FLAGS == "-I -X utf8"
    assert 'Parameters: "-I -X utf8 -m sutra_app.desktop"' in iss, "the Start menu entry runs the desktop module"
    assert 'Parameters: "-I -X utf8 -m sutra_app stop"' in iss, "the Quit entry stops the app the same way"
    assert 'Filename: "{app}\\python\\SutraPro.exe"' in iss and 'Filename: "{app}\\python\\python.exe"' in iss
    assert bwa.EXE_NAME == "SutraPro.exe"


def test_the_installer_script_is_per_user_named_and_never_touches_the_data_folder():
    iss = INSTALLER.read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss and "{localappdata}\\Programs\\{#AppName}" in iss
    assert "OutputBaseFilename=Sutra-Pro-Setup-x64" in iss and "ArchitecturesAllowed=x64compatible" in iss
    assert re.search(r"^AppId=\{\{[0-9A-F-]{36}\}$", iss, re.M), "a fixed AppId, how a newer installer finds the older install"
    assert ".sutra-pro" in iss and "never touched" in iss, "the script says the data folder is left alone"
    assert not re.search(r"\[(UninstallDelete|InstallDelete)\]", iss), "nothing is deleted but what the installer put there"
    assert "stop --wait" in iss, "a running app is asked to stop before files go over it and before they are removed"
    for define in ("AppVersion", "SourceDir", "IconFile"):
        assert f"#ifndef {define}" in iss and f"/D{define}" in iss


# ================================================================ refusals

def test_it_refuses_to_build_off_windows_without_the_flag(work):
    if bwa.host_is_windows_x64():
        pytest.skip("this is a Windows x64 machine")
    with pytest.raises(common.BuildError, match="Windows x64"):
        bwa.build_app(wheel=make_wheel(work / "in"), out=work / "out", python_archive=make_archive(work / "in"))


def test_an_archive_without_python_exe_is_refused(work):
    with pytest.raises(common.BuildError, match="python/python.exe"):
        build(work, archive=make_archive(work / "in", with_python=False))
    assert list((work / "out").iterdir()) == [], "a refused build leaves nothing behind"


def test_an_archive_without_pythonw_exe_is_refused(work):
    with pytest.raises(common.BuildError, match="pythonw.exe"):
        build(work, archive=make_archive(work / "in", with_pythonw=False))
    assert list((work / "out").iterdir()) == []


def test_a_version_the_bundle_does_not_report_is_refused(work):
    with pytest.raises(common.BuildError, match="reports sutra-pro '9.9.9'"):
        build(work, archive=make_archive(work / "in", report="9.9.9"))
    assert list((work / "out").iterdir()) == []


def test_an_unsafe_archive_path_is_refused(work):
    evil = tarfile.TarInfo("../outside.txt")
    evil.size = 1
    with pytest.raises(common.BuildError, match="unsafe path"):
        build(work, archive=make_archive(work / "in", extra=[(evil, io.BytesIO(b"x"))]))


def test_a_missing_wheel_or_archive_is_refused(work):
    with pytest.raises(common.BuildError, match="wheel not found"):
        bwa.build_app(wheel=work / "in" / "nope.whl", out=work / "out", python_archive=make_archive(work / "in"), allow_foreign_host=True)
    with pytest.raises(common.BuildError, match="python archive not found"):
        bwa.build_app(wheel=make_wheel(work / "in"), out=work / "out", python_archive=work / "in" / "nope.tar.gz", allow_foreign_host=True)


def test_a_rebuild_replaces_the_folder_and_touches_nothing_else(work):
    (work / "out" / "keep.txt").write_text("mine")
    first = build(work)
    (first / "stale.txt").write_text("old")
    second = build(work)
    assert second == first and not (second / "stale.txt").exists() and (work / "out" / "keep.txt").read_text() == "mine"
    assert sorted(p.name for p in (work / "out").iterdir()) == ["Sutra Pro", "keep.txt"]


# ================================================================ the interpreter lookup knows Windows

WINDOWS_SUMS = (
    "{a}  cpython-3.11.16+20260901-x86_64-pc-windows-msvc-install_only_stripped.tar.gz\n"
    "{b}  cpython-3.11.16+20260901-aarch64-pc-windows-msvc-install_only_stripped.tar.gz\n"
    "{c}  cpython-3.11.16+20260901-x86_64-pc-windows-msvc-install_only.tar.gz\n"
    "{d}  cpython-3.12.9+20260901-x86_64-pc-windows-msvc-install_only_stripped.tar.gz\n"
    "{e}  cpython-3.11.16+20260901-aarch64-apple-darwin-install_only_stripped.tar.gz\n"
)


def test_the_windows_target_picks_the_x64_stripped_cpython_311_and_no_mac_or_arm_archive():
    hashes = {key: f"{i:064x}" for i, key in enumerate("abcde", 1)}
    sums = common.parse_sums(WINDOWS_SUMS.format(**hashes))
    name, digest = common.pick_archive(sums, "win-x64")
    assert name == "cpython-3.11.16+20260901-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" and digest == hashes["a"]
    mac, _ = common.pick_archive(sums, "arm64")
    assert "apple-darwin" in mac, "the Mac targets still find their own archives"


# ================================================================ the icons

def test_the_icons_are_real_files_in_the_formats_the_systems_read():
    png = (ICONS / "sutra-pro-1024.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (1024, 1024)
    ico = (ICONS / "sutra-pro.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind) == (0, 1) and count >= 6, "an .ico with the small sizes the Start menu and the tray ask for"
    icns = (ICONS / "sutra-pro.icns").read_bytes()
    assert icns[:4] == b"icns" and struct.unpack(">I", icns[4:8])[0] == len(icns)
    tray = (ROOT / "sutra_app" / "assets" / "icon.png").read_bytes()
    assert tray[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", tray[16:24]) == (256, 256)
