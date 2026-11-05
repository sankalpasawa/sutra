"""The desktop app and what ships with it (D105, D108): scripts/build_desktop_app.py, the entitlements, the signing script, the Windows installer script.

The builder installs the wheel by RUNNING the bundled interpreter, which only a machine of the target system can do, so these tests give it a
fake interpreter (a script named python3 or python.exe, runnable on any POSIX system with `allow_foreign_host=True`) and a fake packager, and
check what the builder does around them: the layout, the pip call, the clean-up, every refusal. That the real app runs is proved by
scripts/prove_desktop_app.py in the release workflows, on the runners, before anything is uploaded. Nothing is downloaded and nothing is signed.
"""
import importlib.util
import io
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest
from test_macos_bundle import make_archive as make_mac_archive
from test_macos_bundle import make_wheel

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_desktop_app.py"
SIGNER = ROOT / "scripts" / "sign_desktop_app.sh"
PROVER = ROOT / "scripts" / "prove_desktop_app.py"
INSTALLER = ROOT / "scripts" / "windows" / "sutra-pro-desktop.iss"
OLD_INSTALLER = ROOT / "scripts" / "windows" / "sutra-pro.iss"
DESKTOP = ROOT / "desktop"

sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("build_desktop_app", SCRIPT)
bda = importlib.util.module_from_spec(_spec)
sys.modules["build_desktop_app"] = bda
_spec.loader.exec_module(bda)
common = bda.common
BuildError = common.BuildError

_prover_spec = importlib.util.spec_from_file_location("prove_desktop_app", PROVER)
prover = importlib.util.module_from_spec(_prover_spec)
sys.modules["prove_desktop_app"] = prover
_prover_spec.loader.exec_module(prover)

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="the fake interpreter is a script with a shebang")


# ================================================================ fakes: the packager and a Windows interpreter

def fake_package(target, stage, version):
    """What `node scripts/package.mjs` leaves: the Electron app with no Python in it yet."""
    if target.windows:
        app = stage / "Sutra Pro-win32-x64"
        (app / "resources").mkdir(parents=True)
        (app / "Sutra Pro.exe").write_bytes(b"MZ")
    else:
        app = stage / f"Sutra Pro-darwin-{target.arch}" / "Sutra Pro.app"
        (app / "Contents" / "Resources").mkdir(parents=True)
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "MacOS" / "Sutra Pro").write_bytes(b"\xcf\xfa\xed\xfe")
    return app


FAKE_WINDOWS_PYTHON = '''#!{python}
# a fake python.exe: logs its calls and "installs" the wheel the way pip would, console scripts included
import json, os, sys, zipfile
root = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(root, "calls.log"), "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["-m", "pip"]:
    with zipfile.ZipFile(args[-1]) as z:
        meta = [n for n in z.namelist() if n.endswith("METADATA")][0]
        version = [l for l in z.read(meta).decode().splitlines() if l.startswith("Version:")][0].split(":")[1].strip()
    open(os.path.join(root, "installed-version"), "w").write(version)
    os.makedirs(os.path.join(root, "Scripts"), exist_ok=True)
    for script in ("sutra-pro.exe", "uvicorn.exe"):
        open(os.path.join(root, "Scripts", script), "w").write("MZ")
elif "-c" in args:
    print("a warning line")
    print(open(os.path.join(root, "installed-version")).read())
'''


def make_windows_archive(directory):
    path = directory / "cpython-3.11.14+20260901-windows-fake.tar.gz"
    body = FAKE_WINDOWS_PYTHON.format(python=sys.executable).encode()
    with tarfile.open(path, "w:gz") as archive:
        for folder in ("python", "python/Scripts"):
            info = tarfile.TarInfo(folder)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(info)
        info = tarfile.TarInfo("python/python.exe")
        info.size, info.mode = len(body), 0o755
        archive.addfile(info, io.BytesIO(body))
    return path


@pytest.fixture
def work(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    return tmp_path


def build(work, target="mac-arm64", **kwargs):
    archive = kwargs.pop("archive", None) or (make_windows_archive(work / "in") if target == "win-x64" else make_mac_archive(work / "in"))
    return bda.build_app(wheel=kwargs.pop("wheel", None) or make_wheel(work / "in", version="0.2.0"), target=target, out=work / "out",
                         python_archive=archive, package=kwargs.pop("package", fake_package), allow_foreign_host=True, **kwargs)


# ================================================================ the Mac app

@POSIX_ONLY
def test_the_mac_app_is_the_electron_app_with_the_python_inside_its_resources(work):
    app = build(work, "mac-arm64")
    assert app == work / "out" / "Sutra Pro.app"
    resources = app / "Contents" / "Resources"
    assert (app / "Contents" / "MacOS" / "Sutra Pro").is_file(), "the packager's executable is what a person starts"
    assert (resources / "python" / "bin" / "python3").exists()
    info = json.loads((resources / "build-info.json").read_text())
    desktop = json.loads((DESKTOP / "package.json").read_text())
    assert info["app"] == "Sutra Pro" and info["bundle_id"] == "os.sutra.pro" and info["shell"] == "electron"
    assert info["version"] == "0.2.0" and info["target"] == "mac-arm64" and info["electron"] == desktop["devDependencies"]["electron"]
    assert info["wheel"] == "sutra_pro-0.2.0-py3-none-any.whl" and len(info["wheel_sha256"]) == 64 and len(info["python_archive_sha256"]) == 64
    assert [p.name for p in (work / "out").iterdir()] == ["Sutra Pro.app"], "no build folder is left beside the app"


@POSIX_ONLY
def test_pip_installs_the_wheel_with_a_clean_environment_and_its_console_scripts_are_removed(work):
    app = build(work, "mac-arm64")
    python = app / "Contents" / "Resources" / "python"
    calls = [json.loads(line) for line in (python / "calls.log").read_text().splitlines()]
    pip = next(call for call in calls if call["args"][:2] == ["-m", "pip"])
    assert pip["args"][-1].endswith("sutra_pro-0.2.0-py3-none-any.whl") and "--no-warn-script-location" in pip["args"]
    assert pip["env"]["PYTHONNOUSERSITE"] == "1" and pip["env"]["PYTHONDONTWRITEBYTECODE"] == "1", "pip runs clean, and writes no bytecode into the app"
    assert (python / "installed-version").read_text() == "0.2.0"
    assert sorted(p.name for p in (python / "bin").iterdir() if p.is_file() or p.is_symlink()) == ["python3", "python3.11"], \
        "pip's console scripts name this build folder: they are removed, the app starts `python -m sutra_app`"


@POSIX_ONLY
def test_a_second_build_replaces_the_first_and_a_failed_one_leaves_nothing(work):
    build(work, "mac-arm64")
    build(work, "mac-arm64")
    assert [p.name for p in (work / "out").iterdir()] == ["Sutra Pro.app"]
    shutil.rmtree(work / "out")
    (work / "out").mkdir()
    with pytest.raises(BuildError, match="pip install"):
        build(work, "mac-arm64", archive=make_mac_archive(work / "in", pip_exit=1, name="failing.tar.gz"))
    assert list((work / "out").iterdir()) == [], "a failed build never leaves a half app under the final name"


@POSIX_ONLY
def test_an_app_that_reports_another_version_than_its_wheel_is_refused(work):
    with pytest.raises(BuildError, match="reports sutra-pro '9.9.9' but the wheel is '0.2.0'"):
        build(work, "mac-arm64", archive=make_mac_archive(work / "in", report="9.9.9", name="liar.tar.gz"))


@POSIX_ONLY
def test_a_link_that_leaves_the_app_is_refused(work):
    link = tarfile.TarInfo("python/lib/escape")
    link.type, link.linkname, link.mode = tarfile.SYMTYPE, "../../../../../../etc", 0o755
    archive = make_mac_archive(work / "in", extra=[(link,)], name="escape.tar.gz")
    # the archive reader itself refuses a link that leaves the tree it unpacks into ...
    with pytest.raises(BuildError, match="points outside"):
        build(work, "mac-arm64", archive=archive)
    # ... and the app-wide check is the second line: an absolute link written after unpacking (a build script that made one) is found too
    app = fake_package(bda.TARGETS["mac-arm64"], work / "stage", "0.2.0")
    os.symlink("/usr/bin/python3", app / "Contents" / "Resources" / "python-link")
    with pytest.raises(BuildError, match="do not stay inside the app"):
        bda.check_links(app)
    (app / "Contents" / "Resources" / "python-link").unlink()
    os.symlink("python3.11", app / "Contents" / "Resources" / "fine")
    bda.check_links(app)


def test_the_packaged_app_must_have_a_resources_folder(work):
    def empty(target, stage, version):
        (stage / "x" / "Sutra Pro.app" / "Contents").mkdir(parents=True)
        return stage / "x" / "Sutra Pro.app"
    with pytest.raises(BuildError, match="no resources folder"):
        build(work, "mac-arm64", package=empty)


# ================================================================ the Windows app

@POSIX_ONLY
def test_the_windows_app_has_the_python_in_resources_and_the_command_wrapper_beside_the_exe(work):
    app = build(work, "win-x64")
    assert app == work / "out" / "Sutra Pro"
    assert (app / "Sutra Pro.exe").is_file()
    assert (app / "resources" / "python" / "python.exe").is_file()
    assert (app / "resources" / "build-info.json").is_file()
    assert sorted(p.name for p in (app / "resources" / "python" / "Scripts").iterdir()) == [], "pip's .exe launchers name the build folder: removed"
    command = (app / "sutra-pro.cmd").read_bytes()
    assert command == b'@echo off\r\n"%~dp0resources\\python\\python.exe" -I -X utf8 -m sutra_app %*\r\n'
    readme = (app / "README.txt").read_bytes()
    assert b"Sutra Pro 0.2.0\r\n" in readme and b"\r\n" in readme and b"\n" not in readme.replace(b"\r\n", b""), "CRLF line endings"
    assert b"SmartScreen" in readme and b".sutra-pro" in readme
    assert not (app / "python").exists(), "the 0.1.x layout kept the interpreter in python\\; this one does not"


def test_the_windows_wheel_is_installed_without_the_tray_extra(work):
    if sys.platform == "win32":
        pytest.skip("the fake interpreter is a script with a shebang")
    app = build(work, "win-x64")
    calls = [json.loads(line) for line in (app / "resources" / "python" / "calls.log").read_text().splitlines()]
    pip = next(call for call in calls if call[:2] == ["-m", "pip"])
    assert "[desktop]" not in pip[-1], "the window has no notification-area icon: pystray and Pillow stay out of the app"


# ================================================================ the targets and the refusals

def test_each_target_names_an_electron_platform_and_a_python_archive_that_exists():
    assert {name: (t.platform, t.arch, t.archive) for name, t in bda.TARGETS.items()} == {
        "mac-arm64": ("darwin", "arm64", "arm64"), "mac-x64": ("darwin", "x64", "x86_64"), "win-x64": ("win32", "x64", "win-x64")}
    for target in bda.TARGETS.values():
        assert target.archive in common.TRIPLES
        assert any(name.endswith("install_only_stripped.tar.gz") and common.TRIPLES[target.archive] in name for name in common.PINNED_SHA256), target.name


def test_a_target_the_machine_cannot_build_is_refused_before_anything_happens(work):
    wheel = make_wheel(work / "in", version="0.2.0")
    with pytest.raises(BuildError, match="unsupported target"):
        bda.build_app(wheel=wheel, target="linux-x64", out=work / "out")
    if sys.platform != "win32":
        with pytest.raises(BuildError, match="cannot build win-x64"):
            bda.build_app(wheel=wheel, target="win-x64", out=work / "out")
    other = "mac-x64" if common.host_arch() == "arm64" else "mac-arm64"            # the Mac architecture this machine is not
    assert not bda.host_can_build(bda.TARGETS[other])
    with pytest.raises(BuildError, match="cannot build"):
        bda.build_app(wheel=wheel, target=other, out=work / "out")
    assert list((work / "out").iterdir()) == [], "nothing was created"


def test_a_wheel_that_is_not_ours_or_has_no_version_is_refused(work):
    with pytest.raises(BuildError, match="not of 'sutra-pro'"):
        build(work, "mac-arm64", wheel=make_wheel(work / "in", name="other", version="0.2.0", filename="other-0.2.0-py3-none-any.whl"))
    with pytest.raises(BuildError, match="X.Y.Z"):
        build(work, "mac-arm64", wheel=make_wheel(work / "in", version="0.2.0b1", filename="sutra_pro-0.2.0b1-py3-none-any.whl"))


# ================================================================ the packager step

def test_the_packager_is_run_after_npm_ci_with_the_platform_the_architecture_and_the_version(tmp_path, monkeypatch):
    ran = []

    def run_tool(args, what, cwd):
        ran.append((Path(args[0]).name, args[1:], what, cwd))
        packaged = tmp_path / "pkg" / "Sutra Pro.app"
        packaged.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(args, 0, stdout=f"noise\nPACKAGED {packaged}\n", stderr="")

    monkeypatch.setattr(bda, "run_tool", run_tool)
    monkeypatch.setattr(bda, "tool", lambda name: f"/usr/bin/{name}")
    app = bda.package_window(bda.TARGETS["mac-x64"], tmp_path / "stage", "0.2.0")
    assert app == tmp_path / "pkg" / "Sutra Pro.app"
    assert [item[0] for item in ran] == ["npm", "node"]
    assert ran[0][1] == ["ci", "--no-audit", "--no-fund"] and ran[0][3] == DESKTOP
    assert ran[1][1][:5] == ["scripts/package.mjs", "--platform", "darwin", "--arch", "x64"] and ran[1][1][-2:] == ["--version", "0.2.0"]


def test_skipping_npm_needs_node_modules_and_a_packager_that_does_not_say_where_the_app_is_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(bda, "tool", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(bda, "DESKTOP", tmp_path / "desktop")
    (tmp_path / "desktop").mkdir()
    with pytest.raises(BuildError, match="node_modules is not there"):
        bda.package_window(bda.TARGETS["mac-arm64"], tmp_path, "0.2.0", skip_npm=True)
    (tmp_path / "desktop" / "node_modules").mkdir()
    monkeypatch.setattr(bda, "run_tool", lambda args, what, cwd: subprocess.CompletedProcess(args, 0, stdout="nothing useful\n", stderr=""))
    with pytest.raises(BuildError, match="did not say where the app is"):
        bda.package_window(bda.TARGETS["mac-arm64"], tmp_path, "0.2.0", skip_npm=True)


def test_a_missing_node_or_npm_says_which_and_what_is_needed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(BuildError, match="node is not on PATH.*Node 22"):
        bda.tool("node")


# ================================================================ versions, entitlements, scripts

def test_the_version_is_one_number_in_the_wheel_the_package_and_the_app():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    package = json.loads((DESKTOP / "package.json").read_text())["version"]
    lock = json.loads((DESKTOP / "package-lock.json").read_text())
    source = (ROOT / "sutra_app" / "__init__.py").read_text()
    assert re.search(r'^__version__ = "([^"]+)"', source, re.M).group(1) == pyproject == package == lock["version"] == lock["packages"][""]["version"]


def test_the_entitlements_are_the_short_lists_their_comments_defend():
    electron = plistlib.loads((DESKTOP / "entitlements.electron.plist").read_bytes())
    python = plistlib.loads((DESKTOP / "entitlements.python.plist").read_bytes())
    assert set(electron) == {"com.apple.security.cs.allow-jit", "com.apple.security.cs.allow-unsigned-executable-memory"}
    assert set(python) == {"com.apple.security.cs.disable-library-validation", "com.apple.security.cs.allow-unsigned-executable-memory"}
    assert all(value is True for value in {**electron, **python}.values())
    assert "com.apple.security.cs.disable-library-validation" not in electron, "Electron's own processes keep library validation on"
    assert not any("dyld" in key or "sandbox" in key for key in {**electron, **python})


@pytest.mark.skipif(sys.platform == "win32", reason="bash")
def test_the_signing_script_is_valid_bash_and_refuses_what_is_not_an_app(tmp_path):
    assert subprocess.run(["bash", "-n", str(SIGNER)], capture_output=True).returncode == 0
    none = subprocess.run(["bash", str(SIGNER)], capture_output=True, text=True)
    assert none.returncode == 2 and "usage" in none.stderr
    folder = subprocess.run(["bash", str(SIGNER), str(tmp_path)], capture_output=True, text=True)
    assert folder.returncode == 2 and "usage" in folder.stderr
    (tmp_path / "Contents" / "MacOS").mkdir(parents=True)
    no_python = subprocess.run(["bash", str(SIGNER), str(tmp_path)], capture_output=True, text=True)
    assert no_python.returncode == 2 and "Contents/Resources/python" in no_python.stderr


@pytest.mark.skipif(sys.platform != "darwin", reason="needs codesign")
def test_the_signing_script_signs_inside_out_and_the_audit_finds_a_file_no_pass_looked_at(tmp_path):
    app = tmp_path / "Sutra Pro.app"
    for folder in ("Contents/MacOS", "Contents/Resources/python/bin", "Contents/Resources/python/lib", "Contents/Frameworks"):
        (app / folder).mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Sutra Pro", "CFBundleIdentifier": "os.sutra.test",
                                                                  "CFBundlePackageType": "APPL"}))
    for target in ("Contents/MacOS/Sutra Pro", "Contents/Resources/python/bin/python3.11"):
        shutil.copy("/bin/ls", app / target)
    env = {**os.environ, "SIGN_RUNTIME": "1"}                    # ad hoc, but with the hardened runtime: the audit has something to check
    done = subprocess.run(["bash", str(SIGNER), str(app)], capture_output=True, text=True, env=env, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "python: signed 1 Mach-O files" in done.stdout and "audit: all 2 Mach-O files carry the hardened runtime" in done.stdout
    # a Mach-O with no executable bit and an odd name is found by what it is, and an unsigned one fails the audit
    stray = app / "Contents" / "Resources" / "python" / "lib" / "stray-data.bin"
    shutil.copy("/bin/ls", stray)
    stray.chmod(0o644)
    subprocess.run(["codesign", "--remove-signature", str(stray)], capture_output=True)
    bad = subprocess.run(["bash", str(SIGNER), str(app)], capture_output=True, text=True, env=env, timeout=120)
    assert bad.returncode == 1, "the signing passes look at libraries and executables; only the audit looks at what a file IS\n" + bad.stdout + bad.stderr
    assert "stray-data.bin" in bad.stderr and "would be rejected by notarization" in bad.stderr


def test_the_proof_finds_the_program_and_the_interpreter_of_each_layout_and_refuses_a_folder_that_is_not_an_app(tmp_path, monkeypatch):
    monkeypatch.setattr(prover, "WINDOWS", False)
    exe, python = prover.layout(Path("/x/Sutra Pro.app"))
    assert exe == Path("/x/Sutra Pro.app/Contents/MacOS/Sutra Pro") and python == Path("/x/Sutra Pro.app/Contents/Resources/python/bin/python3")
    monkeypatch.setattr(prover, "WINDOWS", True)
    exe, python = prover.layout(Path("/x/Sutra Pro"))
    assert exe == Path("/x/Sutra Pro/Sutra Pro.exe") and python == Path("/x/Sutra Pro/resources/python/python.exe")
    with pytest.raises(prover.Failure, match="is not a desktop app"):
        prover.prove(tmp_path, "0.2.0")


def test_the_windows_installer_is_the_electron_layout_and_replaces_a_0_1_x_install_in_place():
    text = INSTALLER.read_text()
    old = OLD_INSTALLER.read_text()
    guid = re.search(r"^AppId=(\{\{[0-9A-F-]+\})", text, re.M).group(1)
    assert guid == re.search(r"^AppId=(\{\{[0-9A-F-]+\})", old, re.M).group(1), "the same AppId: an upgrade, not a second app"
    assert '#define AppExe "Sutra Pro.exe"' in text and "OutputBaseFilename=Sutra-Pro-Setup-x64" in text
    assert "PrivilegesRequired=lowest" in text and "DefaultDirName={localappdata}\\Programs\\{#AppName}" in text
    delete = re.split(r"^\[InstallDelete\]$", text, flags=re.M)[1].split("\n[Files]")[0]       # the section, not the word in the header comment
    for leftover in ('Name: "{app}\\python"', 'Name: "{app}\\icon"', 'Name: "{app}\\Sutra Pro.cmd"', 'Name: "{app}\\Quit Sutra Pro.cmd"'):
        assert leftover in delete, leftover
    assert "SutraPro.exe" not in text and "sutra_app.desktop" not in text, "nothing of the 0.1.x launcher"
    assert "resources\\python\\python.exe" in text, "the uninstaller and the upgrade stop the server of the new layout"
    assert "{app}\\python\\python.exe" in text, "and the upgrade stops a server of the old layout first"
    assert ".sutra-pro" in text and "never touched" in text, "the data folder is left alone, and the file says so"
