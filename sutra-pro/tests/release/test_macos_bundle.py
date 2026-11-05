"""Sutra Pro.app and its DMG workflow (REL-2): no macOS tools needed.

Four layers: the bundle builder with a fake python archive and a fake wheel in tmp dirs; the Info.plist; the launcher (syntax,
quoting, and REAL runs against a fake `python -m sutra_app` server and a fake `open`); the release-macos.yml workflow structure
(shell steps that decide things are executed here on small inputs). Nothing is downloaded and nothing is signed.
"""
import hashlib
import importlib.util
import io
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import textwrap
import time
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_macos_app.py"
LAUNCHER = ROOT / "scripts" / "macos" / "launcher.sh"
TEMPLATE = ROOT / "scripts" / "macos" / "Info.plist.tmpl"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "sutra-pro-release-macos.yml"

_spec = importlib.util.spec_from_file_location("build_macos_app", SCRIPT)
bma = importlib.util.module_from_spec(_spec)
sys.modules["build_macos_app"] = bma
_spec.loader.exec_module(bma)

HOST = bma.host_arch()
OTHER = "x86_64" if HOST == "arm64" else "arm64"


# ================================================================ fakes: wheel and python archive

def make_wheel(directory, *, version="0.1.0", name="sutra-pro", filename=None, metadata=True):
    path = directory / (filename or f"sutra_pro-{version}-py3-none-any.whl")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sutra_app/__init__.py", "")
        if metadata:
            archive.writestr(
                "sutra_pro-0.0.0.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nSummary: x\n\nBody: Version: 9.9.9\n",
            )
    return path


FAKE_PYTHON = '''#!{python}
# fake python-build-standalone interpreter: logs its calls, "installs" the wheel by recording its version, and makes the
# console scripts a real pip would make (with an absolute shebang)
import json, os, sys, zipfile
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[1:]
with open(os.path.join(root, "calls.log"), "a") as log:
    log.write(json.dumps({{"args": args, "env": {{k: v for k, v in os.environ.items() if k.startswith(("PIP", "PYTHON", "UV"))}}}}) + "\\n")
PIP_EXIT = {pip_exit}
REPORT = {report!r}
if args[:2] == ["-m", "pip"]:
    if PIP_EXIT:
        print("ERROR: could not find a version that satisfies the requirement", file=sys.stderr)
        sys.exit(PIP_EXIT)
    wheel = args[-1]
    with zipfile.ZipFile(wheel) as z:
        meta = [n for n in z.namelist() if n.endswith("METADATA")][0]
        version = [l for l in z.read(meta).decode().splitlines() if l.startswith("Version:")][0].split(":")[1].strip()
    open(os.path.join(root, "installed-version"), "w").write(version)
    for script in ("sutra-pro", "uvicorn"):
        with open(os.path.join(root, "bin", script), "w") as handle:
            handle.write("#!" + os.path.join(root, "bin", "python3") + "\\n")
        os.chmod(os.path.join(root, "bin", script), 0o755)
elif "-c" in args:
    print("some warning line")
    print(REPORT or open(os.path.join(root, "installed-version")).read())
'''


def make_archive(directory, *, pip_exit=0, report=None, extra=(), name="cpython-3.11.14+20260901-fake.tar.gz", top="python"):
    """A tar.gz shaped like python-build-standalone's install_only: python/bin/python3 (+ a relative symlink as in the real one)."""
    path = directory / name
    body = FAKE_PYTHON.format(python=sys.executable, pip_exit=pip_exit, report=report).encode()
    with tarfile.open(path, "w:gz") as archive:
        for folder in (top, f"{top}/bin", f"{top}/lib"):
            info = tarfile.TarInfo(folder)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(info)
        info = tarfile.TarInfo(f"{top}/bin/python3.11")
        info.size, info.mode = len(body), 0o755
        archive.addfile(info, io.BytesIO(body))
        link = tarfile.TarInfo(f"{top}/bin/python3")
        link.type, link.linkname, link.mode = tarfile.SYMTYPE, "python3.11", 0o755
        archive.addfile(link)
        for member in extra:
            archive.addfile(*member)
    return path


@pytest.fixture
def work(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    return tmp_path


def build(work, *, arch=HOST, wheel=None, archive=None, **kwargs):
    return bma.build_app(
        wheel=wheel or make_wheel(work / "in"), arch=arch, out=work / "out",
        python_archive=archive or make_archive(work / "in"), allow_foreign_arch=True, **kwargs,
    )


def calls(app):
    log = app / "Contents" / "Resources" / "python" / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()]


# ================================================================ the bundle builder

def test_the_bundle_has_the_documented_layout(work):
    app = build(work)
    assert app == work / "out" / "Sutra Pro.app"
    contents = app / "Contents"
    assert (contents / "Info.plist").is_file()
    assert (contents / "PkgInfo").read_text() == "APPL????"
    launcher = contents / "MacOS" / "SutraPro"
    assert launcher.read_bytes() == LAUNCHER.read_bytes()
    assert os.access(launcher, os.X_OK)
    assert stat.S_IMODE(launcher.stat().st_mode) & 0o111 == 0o111
    assert (contents / "Resources" / "python" / "bin" / "python3").exists()


def test_the_info_plist_names_the_app_and_the_version_of_the_wheel(work):
    app = build(work, wheel=make_wheel(work / "in", version="3.4.5"))
    plist = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert plist["CFBundleName"] == "Sutra Pro"
    assert plist["CFBundleIdentifier"] == "os.sutra.pro" == bma.BUNDLE_ID
    assert plist["CFBundleShortVersionString"] == plist["CFBundleVersion"] == "3.4.5"
    assert plist["CFBundlePackageType"] == "APPL"
    assert (app / "Contents" / "MacOS" / plist["CFBundleExecutable"]).is_file()
    icon = app / "Contents" / "Resources" / (plist["CFBundleIconFile"] + ".icns")
    assert icon.read_bytes() == (ROOT / "assets" / "icon" / "sutra-pro.icns").read_bytes(), "the bundle carries the icon its Info.plist names"


def test_the_version_comes_from_the_wheels_metadata_not_its_file_name(work):
    wheel = make_wheel(work / "in", version="0.3.0", filename="sutra_pro-9.9.9-py3-none-any.whl")
    assert bma.read_wheel(wheel).version == "0.3.0"            # and the body line "Version: 9.9.9" after the blank line is ignored
    plist = plistlib.loads((build(work, wheel=wheel) / "Contents" / "Info.plist").read_bytes())
    assert plist["CFBundleShortVersionString"] == "0.3.0"


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_build_info_records_what_went_in(work, arch):
    wheel, archive = make_wheel(work / "in"), make_archive(work / "in")
    app = build(work, arch=arch, wheel=wheel, archive=archive)
    info = json.loads((app / "Contents" / "Resources" / "build-info.json").read_text())
    assert info == {
        "app": "Sutra Pro", "bundle_id": "os.sutra.pro", "version": "0.1.0", "arch": arch,
        "python_archive": archive.name, "python_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "wheel": wheel.name, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    }


def test_the_wheel_is_installed_by_the_bundled_interpreter_in_a_clean_environment(work, monkeypatch):
    for key in ("PYTHONPATH", "PIP_INDEX_URL", "UV_PYTHON"):
        monkeypatch.setenv(key, "/should/not/leak")
    wheel = make_wheel(work / "in")
    app = build(work, wheel=wheel)
    install = calls(app)[0]
    assert install["args"][:2] == ["-m", "pip"] and install["args"][2] == "install"
    assert install["args"][-1] == str(wheel)
    assert {"--no-input", "--disable-pip-version-check"} <= set(install["args"])
    assert install["env"]["PIP_CONFIG_FILE"] == os.devnull
    assert install["env"]["PYTHONNOUSERSITE"] == "1"
    assert not {"PYTHONPATH", "PIP_INDEX_URL", "UV_PYTHON"} & set(install["env"])


def test_the_bundle_is_proved_to_import_sutra_app_at_the_wheels_version(work):
    app = build(work)
    probe = calls(app)[1]["args"]
    assert probe[0] == "-I" and probe[1] == "-c" and "import" in probe[2] and "sutra_app" in probe[2]


def test_console_scripts_with_an_absolute_shebang_are_removed_but_the_interpreter_stays(work):
    bin_dir = build(work) / "Contents" / "Resources" / "python" / "bin"
    assert sorted(p.name for p in bin_dir.iterdir()) == ["python3", "python3.11"]


def test_pip_failing_stops_the_build_and_leaves_nothing_behind(work):
    with pytest.raises(bma.BuildError, match="(?s)pip install of the wheel failed.*could not find a version"):
        build(work, archive=make_archive(work / "in", pip_exit=1))
    assert list((work / "out").iterdir()) == []                # no half bundle, no stage folder


def test_a_bundle_that_reports_another_version_is_refused(work):
    with pytest.raises(bma.BuildError, match=r"reports sutra-pro '9\.9\.9' but the wheel is '0\.1\.0'"):
        build(work, archive=make_archive(work / "in", report="9.9.9"))


def test_an_earlier_app_is_replaced_and_other_files_in_out_are_kept(work):
    old = work / "out" / "Sutra Pro.app"
    old.mkdir()
    (old / "stale.txt").write_text("x")
    (work / "out" / "keep.txt").write_text("y")
    app = build(work)
    assert not (app / "stale.txt").exists() and (work / "out" / "keep.txt").read_text() == "y"


def test_a_failed_rebuild_keeps_the_earlier_app(work):
    app = build(work)
    marker = app / "Contents" / "marker"
    marker.write_text("kept")
    with pytest.raises(bma.BuildError):
        build(work, archive=make_archive(work / "in", pip_exit=1))
    assert marker.read_text() == "kept"


def test_the_builder_never_signs(work, monkeypatch):
    fake = work / "bin"
    fake.mkdir()
    for tool in ("codesign", "security", "xcrun", "hdiutil"):
        (fake / tool).write_text(f"#!/bin/sh\necho {tool} >> '{work}/tools.log'\n")
        (fake / tool).chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    build(work)
    assert not (work / "tools.log").exists()


def test_a_foreign_architecture_is_refused_unless_allowed(work):
    with pytest.raises(bma.BuildError, match=f"this machine is {HOST} but the bundle is {OTHER}"):
        bma.build_app(wheel=make_wheel(work / "in"), arch=OTHER, out=work / "out", python_archive=make_archive(work / "in"))


def test_an_unknown_architecture_is_refused(work):
    with pytest.raises(bma.BuildError, match="unsupported arch 'ppc'"):
        build(work, arch="ppc")


def test_the_two_architectures_use_apples_target_triples():
    assert bma.ARCHES == {"arm64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}


# ---------------------------------------------------------------- the wheel

def test_a_missing_wheel_is_refused(work):
    with pytest.raises(bma.BuildError, match="wheel not found"):
        bma.read_wheel(work / "none.whl")


def test_a_file_that_is_not_a_zip_is_refused(work):
    path = work / "in" / "x.whl"
    path.write_text("not a zip")
    with pytest.raises(bma.BuildError, match="not a wheel"):
        bma.read_wheel(path)


def test_a_wheel_without_metadata_is_refused(work):
    with pytest.raises(bma.BuildError, match="0 .dist-info/METADATA"):
        bma.read_wheel(make_wheel(work / "in", metadata=False))


def test_another_projects_wheel_is_refused(work):
    with pytest.raises(bma.BuildError, match="not of 'sutra-pro'"):
        bma.read_wheel(make_wheel(work / "in", name="requests"))


def test_the_distribution_name_is_compared_after_pep_503_normalisation(work):
    assert bma.read_wheel(make_wheel(work / "in", name="Sutra_Pro")).version == "0.1.0"


@pytest.mark.parametrize("version", ["1.0", "0.2.0.dev1", "0.2.0b1", "01.2.3", "1.2.3+local"])
def test_a_version_that_is_not_three_integers_is_refused(work, version):
    with pytest.raises(bma.BuildError, match="not X.Y.Z"):
        bma.read_wheel(make_wheel(work / "in", version=version))


# ---------------------------------------------------------------- Info.plist rendering

def test_the_template_has_exactly_the_three_fields():
    assert sorted(set(re.findall(r"@[A-Z_]+@", TEMPLATE.read_text()))) == ["@BUNDLE_ID@", "@EXECUTABLE@", "@VERSION@"]


def test_the_rendered_template_parses_and_has_no_field_left():
    text = bma.render_info_plist(TEMPLATE.read_text(), version="1.2.3")
    assert "@" not in re.sub(r"<!--.*?-->", "", text, flags=re.S)
    assert plistlib.loads(text.encode())["CFBundleVersion"] == "1.2.3"


def test_values_are_xml_escaped():
    text = bma.render_info_plist("<string>@VERSION@ @BUNDLE_ID@ @EXECUTABLE@</string>", version="1.2.3", bundle_id="a.b-c")
    assert text == "<string>1.2.3 a.b-c SutraPro</string>"
    assert bma.xml_escape('a&b<c>"d') == "a&amp;b&lt;c&gt;&quot;d"


@pytest.mark.parametrize("kwargs, message", [
    ({"version": "1.2"}, "is not X.Y.Z"),
    ({"version": "1.2.3", "bundle_id": "nodots"}, "not reverse-DNS"),
    ({"version": "1.2.3", "bundle_id": "a.b<c"}, "not reverse-DNS"),
    ({"version": "1.2.3", "executable": "Sutra Pro"}, "executable name"),
])
def test_bad_values_are_refused(kwargs, message):
    with pytest.raises(bma.BuildError, match=message):
        bma.render_info_plist(TEMPLATE.read_text(), **kwargs)


def test_a_template_missing_a_field_or_holding_an_unknown_one_is_refused():
    with pytest.raises(bma.BuildError, match="no @BUNDLE_ID@ field"):
        bma.render_info_plist("@VERSION@ @EXECUTABLE@", version="1.2.3")
    with pytest.raises(bma.BuildError, match=r"unknown fields: \['@TYPO@'\]"):
        bma.render_info_plist("@VERSION@ @BUNDLE_ID@ @EXECUTABLE@ @TYPO@", version="1.2.3")


def test_the_bundle_identifier_and_name_are_the_documented_ones():
    plist = plistlib.loads(bma.render_info_plist(TEMPLATE.read_text(), version="0.1.0").encode())
    assert (plist["CFBundleName"], plist["CFBundleIdentifier"]) == ("Sutra Pro", "os.sutra.pro")
    assert not any(key.endswith("UsageDescription") for key in plist)        # the app asks for no permission


# ---------------------------------------------------------------- the interpreter archive: pick, verify, cache

def sums_text(entries):
    return "".join(f"{digest}  {name}\n" for name, digest in entries.items())


def release(work, *, patches=("3.11.9", "3.11.14", "3.11.2"), corrupt=False):
    """A fake python-build-standalone release: (fetch function, calls list, {name: bytes}). Both arches, several patch levels."""
    files, calls_made = {}, []
    for arch, triple in bma.ARCHES.items():
        for patch in patches:
            name = f"cpython-{patch}+{bma.PBS_TAG}-{triple}-install_only_stripped.tar.gz"
            files[name] = f"archive {arch} {patch}".encode()
    files["cpython-3.12.1+" + bma.PBS_TAG + f"-{bma.ARCHES['arm64']}-install_only_stripped.tar.gz"] = b"other series"
    files[f"cpython-3.11.14+{bma.PBS_TAG}-{bma.ARCHES['arm64']}-debug-full.tar.zst"] = b"other flavour"
    sums = sums_text({n: hashlib.sha256(b).hexdigest() for n, b in files.items()})

    def fetch(url, dest):
        calls_made.append(url)
        base = f"{bma.PBS_REPO}/{bma.PBS_TAG}/"
        assert url.startswith(base)
        leaf = url[len(base):]
        data = sums.encode() if leaf == "SHA256SUMS" else files[leaf]
        dest.write_bytes(data + (b"x" if corrupt and leaf != "SHA256SUMS" else b""))
    return fetch, calls_made, files


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_the_newest_patch_of_the_series_for_the_arch_is_chosen_and_verified(work, arch):
    fetch, _, files = release(work)
    path, digest = bma.resolve_archive(arch, work / "cache", fetch)
    assert path.name == f"cpython-3.11.14+{bma.PBS_TAG}-{bma.ARCHES[arch]}-install_only_stripped.tar.gz"
    assert path.read_bytes() == files[path.name] and digest == hashlib.sha256(files[path.name]).hexdigest()


def test_a_second_resolve_uses_the_cache_and_downloads_nothing(work):
    fetch, made, _ = release(work)
    bma.resolve_archive("arm64", work / "cache", fetch)
    assert len(made) == 2                                       # SHA256SUMS and the archive
    bma.resolve_archive("arm64", work / "cache", fetch)
    assert len(made) == 2


def test_a_damaged_cache_entry_is_fetched_again(work):
    fetch, made, files = release(work)
    path, _ = bma.resolve_archive("arm64", work / "cache", fetch)
    path.write_bytes(b"truncated")
    again, _ = bma.resolve_archive("arm64", work / "cache", fetch)
    assert again.read_bytes() == files[again.name] and len(made) == 3


def test_a_download_that_does_not_match_its_checksum_is_refused_and_deleted(work):
    fetch, _, _ = release(work, corrupt=True)
    with pytest.raises(bma.BuildError, match="does not match its sha256"):
        bma.resolve_archive("arm64", work / "cache", fetch)
    assert not list((work / "cache").glob("cpython-*"))


def test_a_pinned_checksum_that_the_release_contradicts_is_refused(work, monkeypatch):
    fetch, _, files = release(work)
    name = f"cpython-3.11.14+{bma.PBS_TAG}-{bma.ARCHES['arm64']}-install_only_stripped.tar.gz"
    monkeypatch.setitem(bma.PINNED_SHA256, name, "0" * 64)
    with pytest.raises(bma.BuildError, match="now publishes .* but this script pins"):
        bma.resolve_archive("arm64", work / "cache", fetch)


def test_a_pinned_checksum_that_matches_is_accepted_and_no_candidate_is_printed(work, monkeypatch, capsys):
    fetch, _, files = release(work)
    name = f"cpython-3.11.14+{bma.PBS_TAG}-{bma.ARCHES['arm64']}-install_only_stripped.tar.gz"
    monkeypatch.setitem(bma.PINNED_SHA256, name, hashlib.sha256(files[name]).hexdigest().upper())
    bma.resolve_archive("arm64", work / "cache", fetch)
    assert "pin candidate" not in capsys.readouterr().out


def test_an_unpinned_archive_prints_the_line_to_pin(work, capsys):
    fetch, _, files = release(work)
    path, digest = bma.resolve_archive("arm64", work / "cache", fetch)
    assert f"pin candidate: PINNED_SHA256[{path.name!r}] = {digest!r}" in capsys.readouterr().out


def test_a_release_without_the_series_for_the_arch_is_refused(work):
    fetch, _, _ = release(work, patches=())
    with pytest.raises(bma.BuildError, match="lists no CPython 3.11 install_only_stripped build"):
        bma.resolve_archive("x86_64", work / "cache", fetch)


def test_sums_parsing_accepts_both_layouts_and_ignores_junk():
    digest = "a" * 64
    parsed = bma.parse_sums(f"{digest}  one.tar.gz\n{digest.upper()} *two.tar.gz\nnot a hash  three\n\n{'b' * 63}  short\n")
    assert parsed == {"one.tar.gz": digest, "two.tar.gz": digest}


def test_only_https_is_downloaded(work):
    with pytest.raises(bma.BuildError, match="only https"):
        bma.fetch_url("http://example.com/x", work / "x")


def test_the_pins_name_a_real_looking_release_and_series():
    assert re.fullmatch(r"20\d{6}", bma.PBS_TAG) and bma.PY_SERIES == "3.11"
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in bma.PINNED_SHA256.values())


# ---------------------------------------------------------------- unpacking safely

def member(name, *, type=tarfile.REGTYPE, linkname="", data=b""):
    info = tarfile.TarInfo(name)
    info.type, info.linkname, info.size = type, linkname, len(data)
    return info, io.BytesIO(data)


@pytest.mark.parametrize("bad, message", [
    (member("../evil"), "unsafe path"),
    (member("python/../../evil"), "unsafe path"),
    (member("/abs/evil"), "unsafe path"),
    (member("python/link", type=tarfile.SYMTYPE, linkname="../../outside"), "points outside"),
    (member("python/link", type=tarfile.SYMTYPE, linkname="/etc/passwd"), "points outside"),
    (member("python/hard", type=tarfile.LNKTYPE, linkname="../outside"), "points outside"),
    (member("python/dev", type=tarfile.CHRTYPE), "device file"),
])
def test_an_unsafe_archive_is_refused_before_anything_is_written(work, bad, message):
    archive = make_archive(work / "in", extra=[bad])
    with pytest.raises(bma.BuildError, match=message):
        bma.extract_python(archive, work / "res")
    assert not (work / "res" / "python" / "bin").exists()


def test_a_relative_link_inside_the_tree_is_fine(work):
    interpreter = bma.extract_python(make_archive(work / "in"), work / "res")
    assert interpreter.is_symlink() and interpreter.resolve().name == "python3.11"


def test_an_archive_without_an_interpreter_is_refused(work):
    with pytest.raises(bma.BuildError, match="did not contain python/bin/python3"):
        bma.extract_python(make_archive(work / "in", top="elsewhere"), work / "res")


def test_a_file_that_is_not_an_archive_is_refused(work):
    path = work / "in" / "x.tar.gz"
    path.write_bytes(b"not gzip")
    with pytest.raises(bma.BuildError, match="cannot unpack"):
        bma.extract_python(path, work / "res")


def test_a_missing_python_archive_is_refused(work):
    with pytest.raises(bma.BuildError, match="python archive not found"):
        build(work, archive=work / "in" / "none.tar.gz")


def test_the_cache_default_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SUTRA_BUNDLE_CACHE", str(tmp_path))
    assert bma.default_cache_dir() == tmp_path
    monkeypatch.delenv("SUTRA_BUNDLE_CACHE")
    assert bma.default_cache_dir().parts[-2:] == (".cache", "sutra-pro-bundle")


def test_a_download_build_resolves_the_archive_through_the_fetch_function(work):
    fetch, made, files = release(work)
    # the fake release serves one-line fakes, not tarballs: the build must get as far as unpacking them
    with pytest.raises(bma.BuildError, match="cannot unpack"):
        bma.build_app(wheel=make_wheel(work / "in"), arch=HOST, out=work / "out", cache_dir=work / "cache", fetch=fetch)
    assert made[0].endswith("/SHA256SUMS") and made[1].endswith("install_only_stripped.tar.gz")


# ---------------------------------------------------------------- the command line

def test_main_builds_and_prints_the_path(work, capsys):
    code = bma.main([
        "--wheel", str(make_wheel(work / "in")), "--arch", HOST, "--out", str(work / "out"),
        "--python-archive", str(make_archive(work / "in")),
    ])
    assert code == 0 and f"built {work / 'out' / 'Sutra Pro.app'} ({HOST})" in capsys.readouterr().out


def test_main_reports_a_refusal_on_one_error_line_with_status_1(work, capsys):
    code = bma.main(["--wheel", str(work / "none.whl"), "--out", str(work / "out"), "--python-archive", str(work / "x")])
    assert code == 1 and capsys.readouterr().err.startswith("error: wheel not found")


@pytest.mark.parametrize("argv", [[], ["--wheel", "w"], ["--wheel", "w", "--out", "o", "--arch", "ppc"]])
def test_main_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as stop:
        bma.main(argv)
    assert stop.value.code == 2


def test_the_script_runs_as_a_program_and_uses_only_the_standard_library(work):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--wheel", str(make_wheel(work / "in")), "--arch", HOST, "--allow-foreign-arch",
         "--out", str(work / "out"), "--python-archive", str(make_archive(work / "in"))],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    imported = set(re.findall(r"^(?:import|from) ([a-z_]+)", SCRIPT.read_text(), re.M))
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


# ================================================================ the launcher: syntax and quoting

def test_the_launcher_is_valid_bash_and_executable():
    assert subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True).returncode == 0
    assert os.access(LAUNCHER, os.X_OK)
    assert LAUNCHER.read_text().startswith("#!/bin/bash\n")


PATH_VARIABLES = ("HERE", "RESOURCES", "PY", "DATA_DIR", "LOG_DIR", "LOG", "PIDFILE", "HOME", "RUNNER_TEMP", "SUTRA_DATA_DIR")


def unquoted_uses(script, names=PATH_VARIABLES):
    """Uses of the named variables outside double quotes, as a shell reads them: nesting of "$( ... )" is followed, and comments,
    single quotes and heredoc-free text are skipped. (path with a space: 'Sutra Pro.app' makes every unquoted use a bug)."""
    found, stack, i, line = [], ["top"], 0, 1
    depth = [0]
    pattern = re.compile(r"\$\{?(" + "|".join(names) + r")\b")
    while i < len(script):
        ch, ctx = script[i], stack[-1]
        if ch == "\n":
            line += 1
        if ctx == "sq":
            if ch == "'":
                stack.pop()
        elif ch == "\\":
            i += 1
        elif ch == "#" and ctx in ("top", "cmd") and (i == 0 or script[i - 1] in " \t\n;"):
            while i < len(script) and script[i] != "\n":
                i += 1
            continue
        elif ch == "'" and ctx != "dq":
            stack.append("sq")
        elif ch == '"':
            if ctx == "dq":
                stack.pop()
            else:
                stack.append("dq")
        elif script.startswith("$(", i):
            stack.append("cmd")
            depth.append(0)
            i += 1
        elif ch == "(" and ctx == "cmd":
            depth[-1] += 1
        elif ch == ")" and ctx == "cmd":
            if depth[-1] == 0:
                stack.pop()
                depth.pop()
            else:
                depth[-1] -= 1
        elif ch == "$" and ctx in ("top", "cmd"):
            match = pattern.match(script, i)
            if match:
                found.append((line, match.group(0)))
        i += 1
    return found


def test_the_quoting_scanner_catches_unquoted_uses_and_passes_quoted_ones():
    assert unquoted_uses('cd $HERE\n') == [(1, "$HERE")]
    assert unquoted_uses('x=$PY; y=${LOG}/a\n') == [(1, "$PY"), (1, "${LOG")]
    assert unquoted_uses('echo "a $(cd "$HERE" && pwd) b"\n') == []
    assert unquoted_uses('x="$(dirname "$0")/$PY"\n') == []
    assert unquoted_uses("echo '$HERE' # $PY\n") == []
    assert unquoted_uses('if (( 1 )); then echo $(echo $LOG); fi\n') == [(1, "$LOG")]


def test_every_path_variable_in_the_launcher_is_quoted():
    assert unquoted_uses(LAUNCHER.read_text()) == []


def test_the_launcher_uses_no_bash_4_features():
    text = re.sub(r"#.*", "", LAUNCHER.read_text())
    assert not re.search(r"declare -A|\bwait -n\b|\$\{[A-Za-z_]+(,,|\^\^)\}|\bmapfile\b|\breadarray\b|&>>|\|&", text)


# ================================================================ the launcher: real runs

FAKE_SERVER = '''#!{python}
# fake `python -m sutra_app`: records its arguments and environment, serves /api/health, stops on SIGTERM
import http.server, json, os, signal, sys, threading, time
args = sys.argv[1:]
record = os.environ["FAKE_RECORD"]
with open(record, "a") as f:
    f.write(json.dumps({{"args": args, "pid": os.getpid(), "cwd": os.getcwd(),
                         "env": {{k: os.environ.get(k) for k in ("PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
                                                               "SUTRA_DATA_DIR", "PATH", "VIRTUAL_ENV")}}}}) + "\\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "die":
    print("boom: cannot start", file=sys.stderr)
    sys.exit(3)
port = int(args[args.index("--port") + 1])
if mode == "never-listen":
    time.sleep(60)
    sys.exit(0)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{{"ok": true}}'
        self.send_response(200 if self.path == "/api/health" else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
def on_term(*a):
    open(record + ".term", "w").write("got SIGTERM")
    threading.Thread(target=server.shutdown).start()
signal.signal(signal.SIGTERM, on_term)
if mode == "crash-after":
    threading.Timer(1.0, lambda: os._exit(7)).start()
print("fake server listening", port, flush=True)
server.serve_forever()
'''


class Rig:
    """A throw-away 'Sutra Pro.app' (with a space in its path) holding the REAL launcher and a fake bundled python, a fake `open`,
    and an isolated HOME and data folder."""

    def __init__(self, root):
        self.root = root
        self.app = root / "Sutra Pro.app"
        self.exe = self.app / "Contents" / "MacOS" / "SutraPro"
        self.exe.parent.mkdir(parents=True)
        shutil.copyfile(LAUNCHER, self.exe)
        self.exe.chmod(0o755)
        self.python = self.app / "Contents" / "Resources" / "python" / "bin" / "python3"
        self.python.parent.mkdir(parents=True)
        self.python.write_text(FAKE_SERVER.format(python=sys.executable))
        self.python.chmod(0o755)
        self.bin = root / "bin"
        self.bin.mkdir()
        self.opened = root / "opened.txt"
        (self.bin / "open").write_text(f"#!/bin/sh\necho \"$1\" >> '{self.opened}'\n")
        (self.bin / "open").chmod(0o755)
        self.home = root / "home"
        self.home.mkdir()
        self.data = root / "data"
        self.record = root / "record.jsonl"
        self.procs = []

    def env(self, **extra):
        env = {
            "HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "SUTRA_DATA_DIR": str(self.data),
            "SUTRA_NO_DIALOG": "1", "FAKE_RECORD": str(self.record), "SUTRA_START_TIMEOUT": "20",
            "TMPDIR": "/tmp", "LANG": "C",
        }
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def start(self, **extra):
        proc = subprocess.Popen([str(self.exe)], env=self.env(**extra), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.procs.append(proc)
        return proc

    def run(self, timeout=20, **extra):
        proc = self.start(**extra)
        proc.wait(timeout=timeout)
        return proc.returncode

    def wait_for(self, condition, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if condition():
                return True
            time.sleep(0.05)
        return False

    def opened_urls(self):
        return self.opened.read_text().split() if self.opened.exists() else []

    def started(self):
        return [json.loads(l) for l in self.record.read_text().splitlines()] if self.record.exists() else []

    def log(self):
        path = self.data / "logs" / "app.log"
        return path.read_text() if path.exists() else ""

    def close(self):
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        for entry in self.started():
            try:
                os.kill(entry["pid"], signal.SIGKILL)
            except OSError:
                pass


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.close()


def free_ports(count):
    """`count` consecutive loopback ports that are free right now."""
    base = 40000 + (os.getpid() * 37) % 20000
    for start in range(base, base + 2000):
        socks = []
        try:
            for port in range(start, start + count):
                s = socket.socket()
                s.bind(("127.0.0.1", port))
                socks.append(s)
            return start
        except OSError:
            continue
        finally:
            for s in socks:
                s.close()
    raise RuntimeError("no free ports")


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def health(port):
    done = subprocess.run(["curl", "-fsS", "--noproxy", "*", "--max-time", "2", f"http://127.0.0.1:{port}/api/health"],
                          capture_output=True, text=True)
    return done.returncode, done.stdout


needs_curl = pytest.mark.skipif(shutil.which("curl") is None, reason="the launcher waits on /api/health with curl")


@needs_curl
def test_the_launcher_starts_the_server_opens_the_browser_and_stops_the_server_on_quit(rig):
    port = free_ports(1)
    proc = rig.start(SUTRA_PORT_MIN=str(port), SUTRA_PORT_MAX=str(port), PYTHONPATH="/should/not/leak", VIRTUAL_ENV="/x/venv",
                     http_proxy="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9", all_proxy="http://127.0.0.1:9")   # loopback must bypass a proxy
    assert rig.wait_for(lambda: rig.opened_urls()), rig.log()
    assert rig.opened_urls() == [f"http://127.0.0.1:{port}/"]
    assert health(port) == (0, '{"ok": true}')
    (server,) = rig.started()
    assert server["args"] == ["-m", "sutra_app", "--no-browser", "--port", str(port), "--data-dir", str(rig.data)]
    assert server["cwd"] == str(rig.data.resolve()) or server["cwd"].endswith("data")
    env = server["env"]
    assert env["PYTHONPATH"] is None and env["VIRTUAL_ENV"] is None
    assert env["PYTHONNOUSERSITE"] == "1" and env["PYTHONDONTWRITEBYTECODE"] == "1" and env["SUTRA_DATA_DIR"] == str(rig.data)
    assert env["PATH"].startswith(f"{rig.bin}:/usr/bin:/bin:") and "/opt/homebrew/bin" in env["PATH"] and ".claude/local" in env["PATH"]
    assert (rig.data / "app.pid").read_text().split() == [str(proc.pid), str(port)]
    assert "ready: http://127.0.0.1:%d/" % port in rig.log()
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(timeout=15) == 143
    assert not alive(server["pid"])
    assert not (rig.data / "app.pid").exists()
    assert "stopping the server" in rig.log()


@needs_curl
def test_the_data_folder_defaults_to_dot_sutra_pro_in_the_home_folder(rig):
    port = free_ports(1)
    proc = rig.start(SUTRA_DATA_DIR=None, SUTRA_PORT=str(port))
    assert rig.wait_for(lambda: rig.opened_urls())
    home_data = rig.home / ".sutra-pro"
    assert (home_data / "logs" / "app.log").is_file()
    (server,) = rig.started()
    assert server["args"][-2:] == ["--data-dir", str(home_data)] and server["env"]["SUTRA_DATA_DIR"] == str(home_data)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=15)


@needs_curl
def test_the_first_free_port_of_the_range_is_taken(rig):
    start = free_ports(3)
    busy = socket.socket()
    busy.bind(("127.0.0.1", start))
    busy.listen()
    try:
        proc = rig.start(SUTRA_PORT_MIN=str(start), SUTRA_PORT_MAX=str(start + 2))
        assert rig.wait_for(lambda: rig.opened_urls())
        assert rig.opened_urls() == [f"http://127.0.0.1:{start + 1}/"]
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=15)
    finally:
        busy.close()


def test_the_default_port_range_is_8780_to_8799():
    text = LAUNCHER.read_text()
    assert 'PORT_MIN="${SUTRA_PORT_MIN:-8780}"' in text and 'PORT_MAX="${SUTRA_PORT_MAX:-8799}"' in text


@needs_curl
def test_no_free_port_in_the_range_is_a_clear_failure_and_no_server_starts(rig):
    start = free_ports(2)
    held = []
    for port in (start, start + 1):
        s = socket.socket()
        s.bind(("127.0.0.1", port))
        s.listen()
        held.append(s)
    try:
        assert rig.run(SUTRA_PORT_MIN=str(start), SUTRA_PORT_MAX=str(start + 1)) == 1
    finally:
        for s in held:
            s.close()
    assert f"No free port between {start} and {start + 1}" in rig.log()
    assert rig.started() == [] and rig.opened_urls() == []


@needs_curl
def test_a_pinned_port_that_is_busy_or_not_a_number_is_refused(rig):
    start = free_ports(1)
    held = socket.socket()
    held.bind(("127.0.0.1", start))
    held.listen()
    try:
        assert rig.run(SUTRA_PORT=str(start)) == 1
        assert f"Port {start} (SUTRA_PORT) is already in use" in rig.log()
    finally:
        held.close()
    assert rig.run(SUTRA_PORT="80a") == 1
    assert "SUTRA_PORT must be a number" in rig.log()
    assert rig.started() == []


@needs_curl
def test_a_second_launch_opens_the_browser_on_the_first_and_starts_no_second_server(rig):
    port = free_ports(1)
    first = rig.start(SUTRA_PORT=str(port))
    assert rig.wait_for(lambda: rig.opened_urls())
    assert rig.run() == 0
    assert rig.opened_urls() == [f"http://127.0.0.1:{port}/"] * 2
    assert len(rig.started()) == 1 and "already running" in rig.log()
    first.send_signal(signal.SIGTERM)
    first.wait(timeout=15)


@needs_curl
def test_a_stale_pid_file_is_ignored(rig):
    port = free_ports(1)
    rig.data.mkdir()
    (rig.data / "app.pid").write_text(f"999999 {port}\n")
    proc = rig.start(SUTRA_PORT=str(port))
    assert rig.wait_for(lambda: rig.opened_urls())
    assert "stale" in rig.log() and len(rig.started()) == 1
    assert (rig.data / "app.pid").read_text().split()[0] == str(proc.pid)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=15)


@needs_curl
def test_a_server_that_dies_while_starting_is_reported_and_leaves_no_pid_file(rig):
    assert rig.run(FAKE_MODE="die", SUTRA_PORT=str(free_ports(1))) == 1
    log = rig.log()
    assert "The server stopped while starting (exit status 3)" in log and "boom: cannot start" in log
    assert not (rig.data / "app.pid").exists() and rig.opened_urls() == []


@needs_curl
def test_a_server_that_never_answers_is_stopped_after_the_timeout(rig):
    assert rig.run(FAKE_MODE="never-listen", SUTRA_START_TIMEOUT="1", SUTRA_PORT=str(free_ports(1))) == 1
    assert "did not answer /api/health within 1 seconds" in rig.log()
    (server,) = rig.started()
    assert rig.wait_for(lambda: not alive(server["pid"]))


@needs_curl
def test_a_server_that_crashes_later_ends_the_app_with_status_1(rig):
    assert rig.run(FAKE_MODE="crash-after", SUTRA_PORT=str(free_ports(1))) == 1
    assert "the server exited with status 7" in rig.log() and "stopped unexpectedly (exit status 7)" in rig.log()
    assert not (rig.data / "app.pid").exists()


def test_a_missing_bundled_python_is_reported_not_run(rig):
    rig.python.unlink()
    assert rig.run() == 1
    assert "The bundled Python is missing or not executable" in rig.log()
    assert rig.opened_urls() == []


def test_an_unusable_data_folder_fails_with_status_1(rig, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert rig.run(SUTRA_DATA_DIR=str(blocker / "sub")) == 1


@needs_curl
def test_killing_the_launcher_hard_still_stops_the_server_within_seconds(rig):
    port = free_ports(1)
    proc = rig.start(SUTRA_PORT=str(port))
    assert rig.wait_for(lambda: rig.opened_urls())
    (server,) = rig.started()
    proc.kill()                                    # SIGKILL: no trap can run
    proc.wait()
    assert rig.wait_for(lambda: not alive(server["pid"]), timeout=12), "the watchdog left the server running"
    assert (rig.record.parent / "record.jsonl.term").exists(), "the watchdog must ask with SIGTERM before it uses SIGKILL"


@needs_curl
def test_a_log_over_five_megabytes_is_rotated(rig):
    port = free_ports(1)
    (rig.data / "logs").mkdir(parents=True)
    (rig.data / "logs" / "app.log").write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    proc = rig.start(SUTRA_PORT=str(port))
    assert rig.wait_for(lambda: rig.opened_urls())
    assert (rig.data / "logs" / "app.log.1").stat().st_size == 5 * 1024 * 1024 + 1
    assert (rig.data / "logs" / "app.log").stat().st_size < 10_000
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=15)


# ================================================================ release-macos.yml

def wf():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps(job):
    return wf()["jobs"][job]["steps"]


def step_named(job, fragment):
    found = [s for s in steps(job) if fragment.lower() in s.get("name", "").lower()]
    assert len(found) == 1, f"{fragment!r}: {[s.get('name') for s in found]}"
    return found[0]


def step_index(job, fragment):
    return steps(job).index(step_named(job, fragment))


SECRETS = ["APPLE_CERT_P12", "APPLE_CERT_PASSWORD", "APPLE_NOTARY_KEY", "APPLE_NOTARY_KEY_ID", "APPLE_NOTARY_ISSUER"]
REQUIRED = [name for name in SECRETS if name != "APPLE_CERT_PASSWORD"]      # a .p12 may be exported without a password
SIGNING_STEPS = {"Check the signing secrets", "Import the signing certificate", "Notarize and staple the app", "Notarize and staple the DMG"}


def test_the_workflow_has_the_three_jobs_with_guard_first():
    data = wf()
    assert list(data["jobs"]) == ["guard", "dmg", "verify"]
    assert data["name"] == "sutra-pro-release-macos"
    assert "needs" not in data["jobs"]["guard"] and data["jobs"]["guard"]["runs-on"] == "ubuntu-latest"
    assert data["jobs"]["dmg"]["needs"] == "guard"
    assert set(data["jobs"]["verify"]["needs"]) == {"guard", "dmg"}


def test_the_triggers_are_a_version_tag_push_or_a_dispatch_with_a_tag():
    on = wf()[True]
    assert on["push"] == {"tags": ["sutra-pro-v*"]}
    assert on["workflow_dispatch"]["inputs"]["tag"]["required"] is True


def test_the_guard_checks_the_tag_against_pyproject_before_anything_else_of_substance():
    guard = steps("guard")
    check = step_named("guard", "Tag must match pyproject")
    assert check["run"] == 'scripts/py scripts/check_release_tag.py "$TAG" --github-output "$GITHUB_OUTPUT"'
    assert check["env"]["TAG"] == "${{ inputs.tag || github.ref_name }}"
    assert [s.get("uses") for s in guard[:2]] == ["actions/checkout@v4", "astral-sh/setup-uv@v5"]
    assert guard.index(check) < guard.index(step_named("guard", "must already exist"))


def test_a_dispatched_tag_must_already_exist():
    exists = step_named("guard", "must already exist")
    assert exists["if"] == "github.event_name == 'workflow_dispatch'" and "git ls-remote --exit-code --tags" in exists["run"]


def test_the_matrix_builds_each_architecture_natively_on_its_own_runner():
    dmg = wf()["jobs"]["dmg"]
    assert dmg["runs-on"] == "${{ matrix.runner }}"
    assert dmg["strategy"]["fail-fast"] is False
    assert dmg["strategy"]["matrix"]["include"] == [
        {"arch": "arm64", "runner": "macos-15"}, {"arch": "x86_64", "runner": "macos-15-intel"},
    ]
    assert {e["arch"] for e in dmg["strategy"]["matrix"]["include"]} == set(bma.ARCHES)


def test_only_the_dmg_job_can_write_the_release():
    data = wf()
    assert data["permissions"] == {"contents": "read"}
    assert data["jobs"]["dmg"]["permissions"] == {"contents": "write"}
    assert "permissions" not in data["jobs"]["guard"] and "permissions" not in data["jobs"]["verify"]


def test_secrets_appear_only_in_the_env_of_the_signing_steps():
    data = wf()
    seen = {}
    for job_id, job in data["jobs"].items():
        assert "secrets." not in json.dumps({k: v for k, v in job.items() if k != "steps"}), f"{job_id}: a secret outside a step"
        for step in job["steps"]:
            in_env = json.dumps(step.get("env") or {})
            outside = json.dumps({k: v for k, v in step.items() if k != "env"})
            assert "secrets." not in outside, f"{step.get('name')}: a secret in run, with or if"
            if "secrets." in in_env:
                assert step["name"] in SIGNING_STEPS, step["name"]
                seen[step["name"]] = set(re.findall(r"secrets\.(\w+)", in_env))
    assert set(seen) == SIGNING_STEPS
    assert set().union(*seen.values()) == set(SECRETS)
    assert "secrets." not in json.dumps(data.get("env") or {})


def test_the_signing_decision_is_one_step_output_that_later_steps_test():
    assert step_named("dmg", "Check the signing secrets")["id"] == "signing"
    for name in ("Import the signing certificate", "Notarize and staple the app", "Notarize and staple the DMG",
                 "A signed build must actually be notarized"):
        assert step_named("dmg", name)["if"] == "steps.signing.outputs.enabled == 'true'"
    assert step_named("dmg", "Refuse to downgrade")["if"] == "steps.signing.outputs.enabled != 'true'"


def run_signing_check(tmp_path, present):
    out = tmp_path / "gh-output"
    out.write_text("")
    env = {"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(out), **{n: "v" for n in present}}
    done = subprocess.run(["bash", "-c", step_named("dmg", "Check the signing secrets")["run"]], env=env, capture_output=True, text=True)
    return done, out.read_text()


def test_the_signing_check_is_ad_hoc_without_secrets_and_signed_with_the_four_that_decide(tmp_path):
    done, output = run_signing_check(tmp_path, [])
    assert done.returncode == 0 and output == "enabled=false\n"
    done, output = run_signing_check(tmp_path, REQUIRED)
    assert done.returncode == 0 and output == "enabled=true\n", "the certificate's password is optional: this repository's .p12 has none"
    done, output = run_signing_check(tmp_path, SECRETS)
    assert done.returncode == 0 and output == "enabled=true\n"


def test_a_password_alone_does_not_turn_signing_on(tmp_path):
    done, output = run_signing_check(tmp_path, ["APPLE_CERT_PASSWORD"])
    assert done.returncode == 0 and output == "enabled=false\n"


@pytest.mark.parametrize("missing", REQUIRED)
def test_some_but_not_all_secrets_fail_the_build_naming_the_missing_one(tmp_path, missing):
    done, output = run_signing_check(tmp_path, [s for s in SECRETS if s != missing])
    assert done.returncode == 1 and output == ""
    assert f"missing: {missing}. Set all four (APPLE_CERT_PASSWORD is optional) or none." in done.stdout


def test_an_empty_secret_counts_as_absent(tmp_path):
    out = tmp_path / "o"
    out.touch()
    env = {"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(out), **{n: "" for n in SECRETS}}
    done = subprocess.run(["bash", "-c", step_named("dmg", "Check the signing secrets")["run"]], env=env, capture_output=True, text=True)
    assert done.returncode == 0 and out.read_text() == "enabled=false\n"


def test_the_steps_run_in_the_order_that_makes_the_release_trustworthy():
    order = [step_index("dmg", n) for n in (
        "Build the wheel", "Check the signing secrets", "Build Sutra Pro.app", "Sign the app", "Prove the bundle",
        "Notarize and staple the app", "Make the DMG", "Notarize and staple the DMG", "A signed build must",
        "Write the checksum", "Refuse to downgrade", "Attach the DMG",
    )]
    assert order == sorted(order) and len(set(order)) == len(order)
    assert step_index("dmg", "Import the signing certificate") < step_index("dmg", "Sign the app")


def test_the_build_uses_the_builder_natively_per_arch_and_checks_the_wheel_name_against_the_tag():
    build_step = step_named("dmg", "Build Sutra Pro.app")["run"]
    assert 'scripts/py scripts/build_macos_app.py --wheel "${wheels[0]}" --arch "$ARCH" --out build' in build_step
    assert 'sutra_pro-$want-py3-none-any.whl' in build_step and "${TAG#sutra-pro-v}" in build_step and "%-beta.*" in build_step
    assert "--allow-foreign-arch" not in build_step and "--python-archive" not in build_step
    assert wf()["jobs"]["dmg"]["env"] == {"ARCH": "${{ matrix.arch }}", "TAG": "${{ inputs.tag || github.ref_name }}"}


def test_the_cpython_download_is_cached_per_architecture():
    cache = step_named("dmg", "Cache the CPython")
    assert cache["uses"] == "actions/cache@v4" and cache["with"]["path"] == "~/.cache/sutra-pro-bundle"
    assert "${{ matrix.arch }}" in cache["with"]["key"]
    assert str(bma.default_cache_dir()).endswith(".cache/sutra-pro-bundle")


def test_ad_hoc_signing_is_the_default_and_developer_id_adds_the_hardened_runtime():
    sign = step_named("dmg", "Sign the app")["run"]
    assert 'identity="${SIGN_IDENTITY:--}"' in sign
    assert '--force --sign "$identity"' in sign
    assert 'if [ "$identity" != "-" ]' in sign and "--timestamp --options runtime --entitlements" in sign
    assert sign.index("Mach-O") < sign.index('codesign "${args[@]}" "$app"')          # inside out: files first, the bundle last
    assert 'codesign --verify --deep --strict' in sign
    plist = re.search(r"<<'PLIST'\n(.*?)\nPLIST\n", sign, re.S).group(1)
    assert set(re.findall(r"<key>(.*?)</key>", plist)) == {
        "com.apple.security.cs.disable-library-validation", "com.apple.security.cs.allow-unsigned-executable-memory"}
    assert plistlib.loads(re.sub(r"<!--.*?-->", "", plist, flags=re.S).encode())


def test_developer_id_signing_notarizes_staples_and_validates_both_the_app_and_the_dmg():
    app = step_named("dmg", "Notarize and staple the app")["run"]
    dmg = step_named("dmg", "Notarize and staple the DMG")["run"]
    for script in (app, dmg):
        assert "xcrun notarytool submit" in script and "--wait" in script and "xcrun stapler staple" in script
        assert 'base64 --decode > "$key"' in script and "trap 'rm -f \"$key\"' EXIT" in script
    assert 'codesign --force --timestamp --sign "$SIGN_IDENTITY"' in dmg
    validate = step_named("dmg", "A signed build must")["run"]
    assert validate.count("xcrun stapler validate") == 2 and "spctl --assess" in validate


def test_the_signed_bundle_is_proved_through_the_real_launcher_with_the_network_cut():
    prove = step_named("dmg", "Prove the bundle")["run"]
    for needle in ("Contents/MacOS/SutraPro", "api/health", "HTTP_PROXY=http://127.0.0.1:9", "PIP_NO_INDEX=1", "SUTRA_NO_DIALOG=1",
                   'kill -TERM "$launcher"', "build-info.json", 'codesign --verify --deep --strict "$app"'):
        assert needle in prove, needle
    assert prove.index("api/health") < prove.index('kill -TERM "$launcher"') < prove.rindex("codesign --verify")
    # the bundled Python that checks the version is not the launcher's: without -B it writes .pyc files of the standard library into
    # the signed bundle and the seal breaks (found by running the step on a real build, D98)
    assert 'python/bin/python3" -B -I -c' in prove


def test_the_dmg_is_made_with_hdiutil_from_the_app_and_an_applications_link():
    make = step_named("dmg", "Make the DMG")["run"]
    assert 'hdiutil create -volname "Sutra Pro $version" -srcfolder "$stage" -ov -format UDZO "$dmg"' in make
    assert 'dmg="release/Sutra-Pro-$ARCH.dmg"' in make and 'ln -s /Applications "$stage/Applications"' in make
    assert "hdiutil verify" in make and "PlistBuddy" in make


def test_the_checksum_is_written_by_the_leg_that_built_the_dmg_after_signing():
    check = step_named("dmg", "Write the checksum")
    assert check["working-directory"] == "sutra-pro/release"          # a step's own directory is relative to the workspace, not to the default
    assert 'shasum -a 256 "Sutra-Pro-$ARCH.dmg" > "Sutra-Pro-$ARCH.dmg.sha256"' in check["run"]
    assert 'shasum -a 256 -c "Sutra-Pro-$ARCH.dmg.sha256"' in check["run"]


def test_the_upload_names_the_stable_assets_sets_no_body_and_fails_on_a_missing_file():
    upload = step_named("dmg", "Attach the DMG")
    assert upload["uses"] == "softprops/action-gh-release@v2"
    assert upload["with"]["files"].strip().splitlines() == ["sutra-pro/release/Sutra-Pro-${{ matrix.arch }}.dmg", "sutra-pro/release/Sutra-Pro-${{ matrix.arch }}.dmg.sha256"]
    assert upload["with"]["fail_on_unmatched_files"] is True
    assert "body" not in upload["with"]                       # sutra-pro-release-wheel.yml owns the release text
    assert upload["with"]["make_latest"] == "false"           # D100: the old product's site and updater read /releases/latest
    assert upload["with"]["name"] == "${{ needs.guard.outputs.release_name }}"
    assert "'-beta.'" in upload["with"]["prerelease"]


def test_an_ad_hoc_build_never_replaces_a_notarized_dmg():
    script = step_named("dmg", "Refuse to downgrade")["run"]
    assert 'gh release download "$TAG"' in script and "xcrun stapler validate" in script
    assert 'case " $existing " in' in script and '*" Sutra-Pro-$ARCH.dmg "*)' in script        # only this leg's own asset counts
    assert "exit 1" in script and "allowed" in script


def test_verify_needs_both_legs_green_both_architectures_on_the_release_and_matching_checksums():
    verify = wf()["jobs"]["verify"]
    assert verify["if"] == "always() && needs.guard.result == 'success'"
    assert verify["env"]["DMG_RESULT"] == "${{ needs.dmg.result }}"
    scripts = "\n".join(s["run"] for s in verify["steps"])
    assert '[ "$DMG_RESULT" != "success" ]' in scripts
    for name in ("Sutra-Pro-arm64.dmg", "Sutra-Pro-arm64.dmg.sha256", "Sutra-Pro-x86_64.dmg", "Sutra-Pro-x86_64.dmg.sha256"):
        assert name in scripts
    assert "shasum -a 256 -c Sutra-Pro-arm64.dmg.sha256 Sutra-Pro-x86_64.dmg.sha256" in scripts
    assert verify["runs-on"] == "ubuntu-latest"


def test_every_python_call_goes_through_scripts_py_and_nothing_else_is_installed():
    scripts = "\n".join(s["run"] for job in wf()["jobs"].values() for s in job["steps"] if "run" in s)
    assert not re.search(r"(?<![/\w-])python3?\s+(?!-I)", re.sub(r"<<'SH'.*?\nSH\n", "", scripts, flags=re.S).replace("bin/python3\" -I", ""))
    assert "pip install" not in scripts
    assert scripts.count("uv venv .venv --python 3.11") == 2


def test_the_release_workflow_names_match_the_documented_asset_names():
    doc = (ROOT / "docs" / "RELEASE-macos.md").read_text()
    for name in ("Sutra-Pro-arm64.dmg", "Sutra-Pro-x86_64.dmg", "Sutra-Pro-arm64.dmg.sha256", "os.sutra.pro", "~/.sutra-pro/logs/app.log",
                 *SECRETS):
        assert name in doc, name
