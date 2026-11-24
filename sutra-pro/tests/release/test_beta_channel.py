"""The beta channel of the desktop app (D242), as far as the Python side is concerned: the builder makes "Sutra Pro Beta.app" with its own identity, a release is
built exactly as it always was, the beta icon is a sound icon that is not the stable one, and the proof finds the beta's program. The JavaScript side (the window, the
packager's options) is tested in desktop/test/channel.test.js.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_desktop_bundle import DESKTOP, POSIX_ONLY, BuildError, bda, build, prover, work                     # noqa: F401  (`work` is a fixture)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import make_beta_icon                                                           # noqa: E402

CHANNELS = json.loads((DESKTOP / "src" / "channels.json").read_text(encoding="utf-8"))


def test_the_builder_and_the_window_read_one_file_for_the_names_of_the_app():
    assert bda.CHANNELS == CHANNELS
    assert (bda.APP_NAME, bda.BUNDLE_ID) == ("Sutra Pro", "os.sutra.pro"), "what every release has been called since 0.1.0"
    assert CHANNELS["beta"]["appName"] == "Sutra Pro Beta" and CHANNELS["beta"]["appId"] == "os.sutra.pro.beta"
    for field in ("appName", "appId", "dataDirName", "packageName", "iconName", "icns"):
        assert CHANNELS["beta"][field] != CHANNELS["stable"][field], field


@POSIX_ONLY
def test_the_beta_is_built_as_its_own_app_and_says_which_tree_it_came_from(work):
    app = build(work, "mac-arm64", channel="beta", build_label="1a2b3c4+changes")
    assert app == work / "out" / "Sutra Pro Beta.app"
    info = json.loads((app / "Contents" / "Resources" / "build-info.json").read_text())
    assert info["app"] == "Sutra Pro Beta" and info["bundle_id"] == "os.sutra.pro.beta" and info["channel"] == "beta" and info["build"] == "1a2b3c4+changes"
    assert info["version"] == "0.2.0" and info["target"] == "mac-arm64"
    assert [p.name for p in (work / "out").iterdir()] == ["Sutra Pro Beta.app"], "no build folder is left beside the app"


@POSIX_ONLY
def test_a_release_build_is_what_it_always_was_and_a_beta_replaces_only_a_beta(work):
    stable = build(work, "mac-arm64")
    info = json.loads((stable / "Contents" / "Resources" / "build-info.json").read_text())
    assert stable.name == "Sutra Pro.app" and info["app"] == "Sutra Pro" and info["bundle_id"] == "os.sutra.pro"
    assert "channel" not in info and "build" not in info, "a release's build-info.json has no channel: only a beta says what tree it came from"
    beta = build(work, "mac-arm64", channel="beta")
    assert {p.name for p in (work / "out").iterdir()} == {"Sutra Pro.app", "Sutra Pro Beta.app"}, "the two builds sit side by side in one folder"
    assert beta != stable


def test_a_channel_must_exist(work):
    with pytest.raises(BuildError, match="unsupported channel"):
        build(work, "mac-arm64", channel="nightly")


@POSIX_ONLY
def test_a_beta_builds_for_windows_too_as_a_folder_of_its_own_name(work):
    def package(target, stage, version):
        app = stage / "Sutra Pro Beta-win32-x64"
        (app / "resources").mkdir(parents=True)
        (app / "Sutra Pro Beta.exe").write_bytes(b"MZ")
        return app

    app = build(work, "win-x64", channel="beta", build_label="1a2b3c4", package=package)
    assert app == work / "out" / "Sutra Pro Beta"
    assert (app / "Sutra Pro Beta.exe").is_file()
    info = json.loads((app / "resources" / "build-info.json").read_text())
    assert info["app"] == "Sutra Pro Beta" and info["bundle_id"] == "os.sutra.pro.beta" and info["channel"] == "beta" and info["build"] == "1a2b3c4"
    assert info["target"] == "win-x64"


def test_the_packager_is_told_the_channel_only_for_a_beta(tmp_path, monkeypatch):
    ran = []

    def run_tool(args, what, cwd):
        ran.append(args)
        packaged = tmp_path / "pkg" / "Sutra Pro.app"
        packaged.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(args, 0, stdout=f"PACKAGED {packaged}\n", stderr="")

    monkeypatch.setattr(bda, "run_tool", run_tool)
    monkeypatch.setattr(bda, "tool", lambda name: f"/usr/bin/{name}")
    bda.package_window(bda.TARGETS["mac-arm64"], tmp_path / "stage", "0.2.0", skip_npm=False)
    bda.package_window(bda.TARGETS["mac-arm64"], tmp_path / "stage", "0.2.0", skip_npm=False, channel="beta")
    stable_command, beta_command = [call for call in ran if call[0].endswith("node")]
    assert "--channel" not in stable_command, "the command line of a release is the one it has always had"
    assert beta_command[-2:] == ["--channel", "beta"] and beta_command[-4:-2] == ["--version", "0.2.0"]


@pytest.mark.skipif(sys.platform == "win32", reason="the proof of a Mac app: the layout of a Windows folder is another test")
def test_the_proof_starts_the_program_the_packager_named_after_the_app(monkeypatch):
    monkeypatch.setattr(prover, "WINDOWS", False)
    exe, python = prover.layout(Path("/x/Sutra Pro Beta.app"))
    assert exe == Path("/x/Sutra Pro Beta.app/Contents/MacOS/Sutra Pro Beta")
    assert python == Path("/x/Sutra Pro Beta.app/Contents/Resources/python/bin/python3")
    assert prover.layout(Path("/x/Sutra Pro.app"))[0] == Path("/x/Sutra Pro.app/Contents/MacOS/Sutra Pro")


def test_the_windows_proof_starts_the_exe_its_build_info_names(tmp_path, monkeypatch):
    monkeypatch.setattr(prover, "WINDOWS", True)
    installed = tmp_path / "installed"                                           # an installed folder need not carry the app's name
    (installed / "resources").mkdir(parents=True)
    assert prover.layout(installed) == (installed / "Sutra Pro.exe", installed / "resources" / "python" / "python.exe"), "no build-info: the stable app"
    (installed / "resources" / "build-info.json").write_text(json.dumps({"app": "Sutra Pro Beta"}), encoding="utf-8")
    assert prover.layout(installed)[0] == installed / "Sutra Pro Beta.exe"


# ================================================================ the icon

def test_the_committed_beta_icon_is_sound_and_is_not_the_stable_icon():
    assert make_beta_icon.problems() == []
    icons = ROOT / "assets" / "icon"
    assert (icons / "sutra-pro-beta-1024.png").read_bytes() != (icons / "sutra-pro-1024.png").read_bytes()
    for name in (CHANNELS["beta"]["iconName"], CHANNELS["beta"]["icns"], CHANNELS["beta"]["ico"], CHANNELS["beta"]["windowsIconName"]):
        assert (icons / name).is_file(), name
    for field in ("ico", "windowsIconName"):                                     # the Windows beta has its own icon too (the orange band)
        assert CHANNELS["beta"][field] != CHANNELS["stable"][field], field
        assert (icons / CHANNELS["beta"][field]).read_bytes() != (icons / CHANNELS["stable"][field]).read_bytes(), field


def test_a_broken_beta_icon_is_found(tmp_path):
    icons = ROOT / "assets" / "icon"
    png, icns = tmp_path / "beta.png", tmp_path / "beta.icns"
    assert "is missing" in make_beta_icon.problems(png, icns)[0]
    png.write_bytes((icons / "sutra-pro-beta-1024.png").read_bytes())
    icns.write_bytes((icons / "sutra-pro-beta.icns").read_bytes())
    assert make_beta_icon.problems(png, icns) == []
    icns.write_bytes((icons / "sutra-pro-beta.icns").read_bytes()[:-1])                       # the declared length no longer matches
    assert make_beta_icon.problems(png, icns)
    icns.write_bytes((icons / "sutra-pro-beta.icns").read_bytes())
    png.write_bytes((icons / "sutra-pro-1024.png").read_bytes())                              # the stable picture: the 1024 chunk is not this file
    assert any("1024 px chunk" in line for line in make_beta_icon.problems(png, icns))
    png.write_bytes(b"not a png")
    assert any("not a 1024 x 1024 PNG" in line for line in make_beta_icon.problems(png, icns))


def test_the_beta_icon_script_checks_without_pillow(capsys):
    assert make_beta_icon.main(["--check"]) == 0
    assert "beta icon: ok" in capsys.readouterr().out
