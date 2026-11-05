"""The release tag guard (scripts/check_release_tag.py): which tags may be released, and the command the workflow runs."""
import fnmatch
import importlib.util
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_release_tag.py"
_spec = importlib.util.spec_from_file_location("check_release_tag", SCRIPT)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def run_cli(*args, cwd=None):
    """The guard as the workflow runs it: a fresh interpreter, the script path, its arguments."""
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd, timeout=60)


def write_pyproject(tmp_path, body):
    path = tmp_path / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------- the pure function

@pytest.mark.parametrize("tag,version", [
    ("sutra-pro-v0.1.0", "0.1.0"), ("sutra-pro-v1.2.3", "1.2.3"), ("sutra-pro-v10.20.30", "10.20.30"), ("sutra-pro-v0.0.0", "0.0.0"), ("sutra-pro-v1.0.0", "1.0.0"),
])
def test_a_stable_tag_that_matches_is_accepted(tag, version):
    ok, message = guard.check(tag, version)
    assert ok, message
    assert tag in message and version in message
    assert "stable" in message and "beta" not in message


@pytest.mark.parametrize("tag,version", [
    ("sutra-pro-v0.2.0-beta.1", "0.2.0"), ("sutra-pro-v0.2.0-beta.12", "0.2.0"), ("sutra-pro-v1.0.0-beta.0", "1.0.0"), ("sutra-pro-v1.2.3-beta.100", "1.2.3"),
])
def test_a_beta_tag_is_accepted_and_only_its_x_y_z_is_compared(tag, version):
    ok, message = guard.check(tag, version)
    assert ok, message
    assert tag in message and "beta" in message and "pre-release" in message


def test_a_beta_tag_for_another_version_is_a_mismatch():
    ok, message = guard.check("sutra-pro-v0.2.0-beta.1", "0.1.0")
    assert not ok
    assert "claims 0.2.0" in message and "says 0.1.0" in message


@pytest.mark.parametrize("tag,version", [
    ("sutra-pro-v0.2.0", "0.1.0"), ("sutra-pro-v0.1.1", "0.1.0"), ("sutra-pro-v1.1.0", "1.0.0"), ("sutra-pro-v2.0.0", "1.0.0"), ("sutra-pro-v1.0.0", "2.0.0"),
    ("sutra-pro-v1.2.3", "1.2.30"), ("sutra-pro-v1.2.30", "1.2.3"), ("sutra-pro-v11.2.3", "1.2.3"), ("sutra-pro-v1.2.3", "01.2.3"),
    ("sutra-pro-v1.2.3", ""), ("sutra-pro-v1.2.3", "1.2.3 "), ("sutra-pro-v1.2.3", " 1.2.3"), ("sutra-pro-v1.2.3", "sutra-pro-v1.2.3"), ("sutra-pro-v1.2.3", "1.2.3-beta.1"),
    ("sutra-pro-v1.2.3-beta.1", "1.2.3-beta.1"),
])
def test_a_tag_for_another_version_is_a_mismatch_that_names_both(tag, version):
    ok, message = guard.check(tag, version)
    assert not ok
    claimed = re.search(r"v([0-9.]+)", tag).group(1)
    assert f"tag {tag} claims {claimed} but pyproject.toml says {version}" in message
    assert "Bump [project].version" in message
    assert f"gh workflow run sutra-pro-release-wheel -f tag={tag} --ref {tag}" in message, "the repair hint names the tag"


@pytest.mark.parametrize("tag", [
    "V1.2.3", "vv1.2.3", "x1.2.3", "release-1.2.3", "version1.2.3", "refs/tags/v1.2.3", "v-1.2.3", "v+1.2.3", "v_1.2.3",
])
def test_a_wrong_prefix_is_refused_even_when_the_numbers_match(tag):
    ok, message = guard.check(tag, "1.2.3")
    assert not ok
    assert "sutra-pro-vX.Y.Z" in message and repr(tag) in message


@pytest.mark.parametrize("tag", ["1.2.3", "1.2.3-beta.1", "01.2.3", "0.0.0"])
def test_a_tag_without_the_v_is_refused_even_when_the_numbers_match(tag):
    version = tag.split("-")[0]
    ok, message = guard.check(tag, version)
    assert not ok
    assert "sutra-pro-vX.Y.Z" in message and repr(tag) in message


@pytest.mark.parametrize("tag", ["", " ", "\n", "v"])
def test_an_empty_or_blank_tag_is_refused(tag):
    ok, message = guard.check(tag, "1.2.3")
    assert not ok
    assert "sutra-pro-vX.Y.Z" in message and repr(tag) in message


@pytest.mark.parametrize("tag", [
    "sutra-pro-v1", "sutra-pro-v1.2", "sutra-pro-v1.2.3.4", "sutra-pro-v1.2.x", "sutra-pro-v1.2.3-", "sutra-pro-v1.2.3-beta", "sutra-pro-v1.2.3-beta.", "sutra-pro-v1.2.3-beta.x", "sutra-pro-v1.2.3-beta.1.2",
    "sutra-pro-v1.2.3-rc.1", "sutra-pro-v1.2.3-alpha.1", "sutra-pro-v1.2.3-BETA.1", "sutra-pro-v1.2.3-Beta.1", "sutra-pro-v1.2.3-desktop", "sutra-pro-v1.2.3-beta.1-desktop",
    "sutra-pro-v1.2.3+build.5", "sutra-pro-v1.2.3.beta.1", "sutra-pro-v1.2.3beta.1", "sutra-pro-v1.2.3--beta.1", "sutra-pro-v1_2_3", "sutra-pro-v1.2.3-beta.-1",
])
def test_a_tag_that_is_not_the_two_accepted_shapes_is_refused(tag):
    ok, message = guard.check(tag, "1.2.3")
    assert not ok
    assert "sutra-pro-vX.Y.Z" in message and repr(tag) in message


@pytest.mark.parametrize("tag", ["sutra-pro-v01.2.3", "sutra-pro-v1.02.3", "sutra-pro-v1.2.03", "sutra-pro-v00.0.0", "sutra-pro-v1.2.3-beta.01", "sutra-pro-v1.2.3-beta.00"])
def test_leading_zeros_are_refused(tag):
    ok, _ = guard.check(tag, tag.split("-")[0][1:])
    assert not ok


@pytest.mark.parametrize("tag", [
    " v1.2.3", "sutra-pro-v1.2.3 ", "sutra-pro-v1.2.3\n", "\nv1.2.3", "sutra-pro-v1.2.3\r", "sutra-pro-v1.2.3-beta.1\n", "sutra-pro-v1.2.3\t", "v 1.2.3", "sutra-pro-v1.2.3-beta.1 ",
])
def test_whitespace_and_newlines_are_refused(tag):
    """A regex `$` would let a trailing newline through; the guard must not."""
    ok, _ = guard.check(tag, "1.2.3")
    assert not ok


@pytest.mark.parametrize("tag", ["sutra-pro-v١.٢.٣", "sutra-pro-v1.2.3-beta.١", "sutra-pro-v１.２.３", "sutra-pro-v1.2.3-beta.٣", "sutra-pro-v1٢.3.4", "sutra-pro-v1.2٣.4", "sutra-pro-v1.2.3٤", "sutra-pro-v1.2.3-beta.1٢"])
def test_digits_of_other_scripts_are_refused(tag):
    ok, _ = guard.check(tag, "1.2.3")
    assert not ok


@pytest.mark.parametrize("tag", ["sutra-pro-v1.2.3;rm -rf /", "sutra-pro-v1.2.3$(id)", "sutra-pro-v1.2.3`id`", "sutra-pro-v1.2.3|cat", "sutra-pro-v1.2.3&x", "sutra-pro-v1.2.3'", 'v1.2.3"'])
def test_shell_metacharacters_are_refused(tag):
    ok, _ = guard.check(tag, "1.2.3")
    assert not ok


def test_the_accepted_shapes_are_exactly_two():
    """A small exhaustive sweep: of these candidates only the two documented shapes pass."""
    accepted = []
    for prefix in ("", "v", "V", "sutra-pro-", "sutra-pro-V", "Sutra-Pro-v", "sutra-pro-vv", "sutra-pro-v"):
        for core in ("1.2.3", "1.2", "1.2.3.4"):
            for suffix in ("", "-beta.1", "-beta", "-rc.1", "-beta.0", "-beta.10", "-desktop"):
                tag = prefix + core + suffix
                if guard.check(tag, "1.2.3")[0]:
                    accepted.append(tag)
    assert sorted(accepted) == ["sutra-pro-v1.2.3", "sutra-pro-v1.2.3-beta.0", "sutra-pro-v1.2.3-beta.1", "sutra-pro-v1.2.3-beta.10"]


# ---------------------------------------------------------------- reading the version

def test_read_version_reads_the_static_project_version(tmp_path):
    path = write_pyproject(tmp_path, '[build-system]\nrequires = []\n\n[project]\nname = "x"\n# a comment\nversion = "3.4.5"\n')
    assert guard.read_version(path) == "3.4.5"


def test_read_version_of_this_repository_is_a_plain_x_y_z():
    """The real version must be something the guard can ever accept, or no release tag could pass."""
    version = guard.read_version()
    assert version == tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert guard.check(f"sutra-pro-v{version}", version)[0], f"pyproject.toml version {version!r} is not X.Y.Z"
    assert guard.check(f"sutra-pro-v{version}-beta.1", version)[0]


@pytest.mark.parametrize("body", [
    '[project]\nname = "x"\ndynamic = ["version"]\n',          # a dynamic version
    '[project]\nname = "x"\n',                                 # no version at all
    '[tool.x]\nversion = "1.2.3"\n',                           # a version in the wrong table
    '[project]\nname = "x"\nversion = 123\n',                  # not a string
    '[project]\nname = "x"\nversion = ""\n',                   # empty
    'project = "x"\n',                                         # [project] is not a table
    "[project\n",                                              # not TOML
    "",                                                        # empty file
])
def test_read_version_refuses_what_it_cannot_guard(tmp_path, body):
    with pytest.raises(ValueError):
        guard.read_version(write_pyproject(tmp_path, body))


def test_read_version_of_a_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        guard.read_version(tmp_path / "nowhere.toml")


# ---------------------------------------------------------------- the command line (in process)

def test_main_prints_the_message_and_returns_0_for_a_matching_tag(capsys):
    assert guard.main(["sutra-pro-v0.2.0", "--version", "0.2.0"]) == 0
    out = capsys.readouterr().out
    assert out.strip() == "tag sutra-pro-v0.2.0 matches pyproject.toml version 0.2.0 (stable)"


def test_main_prints_an_error_annotation_and_returns_1_for_a_mismatch(capsys):
    assert guard.main(["sutra-pro-v0.2.0", "--version", "0.1.0"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("::error::tag sutra-pro-v0.2.0 claims 0.2.0 but pyproject.toml says 0.1.0")
    assert len(out.splitlines()) == 1


def test_main_returns_1_for_a_tag_that_is_not_a_release_tag(capsys):
    assert guard.main(["1.2.3", "--version", "1.2.3"]) == 1
    assert capsys.readouterr().out.startswith("::error::tag '1.2.3' is not sutra-pro-vX.Y.Z")


def test_main_returns_1_for_an_empty_tag(capsys):
    assert guard.main(["", "--version", "1.2.3"]) == 1
    assert capsys.readouterr().out.startswith("::error::")


def test_main_reads_the_version_from_the_given_pyproject(tmp_path, capsys):
    path = write_pyproject(tmp_path, '[project]\nname = "x"\nversion = "3.4.5"\n')
    assert guard.main(["sutra-pro-v3.4.5", "--pyproject", str(path)]) == 0
    assert guard.main(["sutra-pro-v3.4.5-beta.2", "--pyproject", str(path)]) == 0
    assert guard.main(["sutra-pro-v3.4.6", "--pyproject", str(path)]) == 1
    assert capsys.readouterr().out.count("::error::") == 1


@pytest.mark.parametrize("body", ['[project]\nname = "x"\ndynamic = ["version"]\n', "[project\n", ""])
def test_main_fails_closed_when_the_version_cannot_be_read(tmp_path, capsys, body):
    path = write_pyproject(tmp_path, body)
    assert guard.main(["sutra-pro-v1.2.3", "--pyproject", str(path)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("::error::cannot read the version from ") and str(path) in out


def test_main_fails_closed_when_pyproject_is_missing(tmp_path, capsys):
    assert guard.main(["sutra-pro-v1.2.3", "--pyproject", str(tmp_path / "nowhere.toml")]) == 1
    assert capsys.readouterr().out.startswith("::error::cannot read the version from ")


def test_main_defaults_to_this_repositorys_pyproject(capsys):
    version = guard.read_version()
    major, minor, patch = version.split(".")
    assert guard.main([f"sutra-pro-v{version}"]) == 0
    assert guard.main([f"sutra-pro-v{major}.{minor}.{int(patch) + 1}"]) == 1
    assert guard.main([f"sutra-pro-v{int(major) + 1}.{minor}.{patch}-beta.1"]) == 1


def test_main_takes_an_empty_version_literally_and_does_not_fall_back_to_pyproject(capsys):
    real = guard.read_version()
    assert guard.main([f"sutra-pro-v{real}", "--version", ""]) == 1
    assert "says ." in capsys.readouterr().out


def test_main_refuses_both_a_pyproject_and_a_version():
    with pytest.raises(SystemExit) as stop:
        guard.main(["sutra-pro-v1.2.3", "--pyproject", "x.toml", "--version", "1.2.3"])
    assert stop.value.code == 2


def test_main_needs_a_tag():
    with pytest.raises(SystemExit) as stop:
        guard.main([])
    assert stop.value.code == 2


@pytest.mark.parametrize("tag", ["sutra-pro-v1.2.3\n::error::forged", "sutra-pro-v1.2.3\r\n::set-output name=x::y", "100%\n::add-mask::z"])
def test_a_hostile_tag_cannot_start_a_second_workflow_command(tag, capsys):
    """The tag may come from a dispatch input: whatever it holds, the output is ONE annotation line."""
    assert guard.main([tag, "--version", "1.2.3"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1 and lines[0].startswith("::error::")
    assert "\r" not in lines[0]


def test_annotation_escapes_the_three_characters_github_decodes():
    assert guard.annotation("a%b\nc\rd") == "::error::a%25b%0Ac%0Dd"


# ---------------------------------------------------------------- the command line (as the workflow runs it)

def test_the_script_runs_as_a_program_and_accepts(tmp_path):
    proc = run_cli("sutra-pro-v1.2.3", "--version", "1.2.3")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "tag sutra-pro-v1.2.3 matches pyproject.toml version 1.2.3 (stable)"
    assert proc.stderr == ""


def test_the_script_runs_as_a_program_and_refuses_with_exit_1(tmp_path):
    proc = run_cli("sutra-pro-v1.2.4", "--version", "1.2.3")
    assert proc.returncode == 1
    assert proc.stdout.startswith("::error::tag sutra-pro-v1.2.4 claims 1.2.4 but pyproject.toml says 1.2.3")
    assert proc.stderr == ""


def test_the_script_reads_this_checkouts_pyproject_whatever_the_working_directory(tmp_path):
    version = guard.read_version()
    assert run_cli(f"sutra-pro-v{version}", cwd=tmp_path).returncode == 0
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "9.9.9"\n')
    assert run_cli("sutra-pro-v9.9.9", cwd=tmp_path).returncode == 1, "a pyproject.toml in the working directory must not be used"


def test_the_script_with_no_tag_is_a_usage_error():
    proc = run_cli()
    assert proc.returncode == 2
    assert "usage:" in proc.stderr


# ---------------------------------------------------------------- the old product's tags are never ours (D100)

@pytest.mark.parametrize("tag", ["v1.2.3", "v1.2.3-beta.1", "v2.307.1-desktop", "v2.307.1-beta.1-desktop", "sutra-v1.2.3", "pro-v1.2.3"])
def test_a_tag_of_the_old_product_or_a_bare_v_tag_is_refused(tag):
    """The old pipeline owns `v*`; a release of this product must never be mistaken for one of its releases."""
    ok, message = guard.check(tag, "1.2.3")
    assert not ok
    assert "sutra-pro-vX.Y.Z" in message and repr(tag) in message


def test_no_release_tag_of_this_product_can_start_with_a_v():
    assert guard.TAG_PREFIX == "sutra-pro-" and not guard.TAG_PREFIX.startswith("v")
    assert not guard.TAG_PREFIX.startswith("v") and fnmatch.fnmatchcase("sutra-pro-v1.2.3", "sutra-pro-v*")
    assert not fnmatch.fnmatchcase("sutra-pro-v1.2.3", "v*"), "the old workflows' tag filter must not match ours"


# ---------------------------------------------------------------- the facts a release is published with

@pytest.mark.parametrize("tag,expected", [
    ("sutra-pro-v0.1.0", {"version": "0.1.0", "prerelease": "false", "release_name": "Sutra Pro 0.1.0"}),
    ("sutra-pro-v10.20.30", {"version": "10.20.30", "prerelease": "false", "release_name": "Sutra Pro 10.20.30"}),
    ("sutra-pro-v0.2.0-beta.3", {"version": "0.2.0", "prerelease": "true", "release_name": "Sutra Pro 0.2.0 beta 3"}),
])
def test_release_facts_name_the_release_and_flag_a_beta_as_a_prerelease(tag, expected):
    assert guard.release_facts(tag) == {"tag": tag, **expected}


def test_release_facts_refuse_a_tag_that_is_not_a_release_tag():
    with pytest.raises(ValueError):
        guard.release_facts("v0.1.0")


def test_the_cli_writes_the_facts_to_the_github_output_file_only_for_a_valid_tag(tmp_path):
    out = tmp_path / "output.txt"
    ok = run_cli("sutra-pro-v0.1.0-beta.2", "--version", "0.1.0", "--github-output", str(out))
    assert ok.returncode == 0, ok.stdout
    assert out.read_text(encoding="utf-8").splitlines() == [
        "tag=sutra-pro-v0.1.0-beta.2", "version=0.1.0", "prerelease=true", "release_name=Sutra Pro 0.1.0 beta 2"]
    out2 = tmp_path / "output2.txt"
    bad = run_cli("sutra-pro-v0.2.0", "--version", "0.1.0", "--github-output", str(out2))
    assert bad.returncode == 1 and bad.stdout.startswith("::error::")
    assert not out2.exists(), "a refused tag leaves the output file alone"
