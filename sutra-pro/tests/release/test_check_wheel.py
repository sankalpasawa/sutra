"""The wheel checker (scripts/check_wheel.py): package data, the console script and the distribution name.

Most cases edit a wheel assembled by hand from a tiny fixture tree, so every failure is produced on purpose and the clean wheel
passes. Two groups use the real build tool (uv, offline) and are skipped with a printed reason where it cannot build: a wheel
built by setuptools from the fixture tree, and one built from this repository's own tree.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_wheel.py"
_spec = importlib.util.spec_from_file_location("check_wheel", SCRIPT)
cw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cw)

PYPROJECT = """\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "sutra-pro"
version = "0.0.1"
requires-python = ">=3.11"

[project.scripts]
sutra-pro = "sutra_app.__main__:main"

[tool.setuptools]
include-package-data = true

[tool.setuptools.packages.find]
include = ["sutra_app*"]

[tool.setuptools.package-data]
sutra_app = ["pages/*", "static/**/*", "policy.default.json"]
"""
FILES = {
    "sutra_app/__init__.py": "",
    "sutra_app/__main__.py": "def main():\n    return 0\n",
    "sutra_app/pages/home.html": "<html></html>\n",
    "sutra_app/static/app.css": "body {}\n",
    "sutra_app/static/js/app.js": "// js\n",
    "sutra_app/policy.default.json": "{}\n",
}
DIST_INFO = "sutra_pro-0.0.1.dist-info"
METADATA = "Metadata-Version: 2.1\nName: sutra-pro\nVersion: 0.0.1\nRequires-Python: >=3.11\n"
ENTRY_POINTS = "[console_scripts]\nsutra-pro = sutra_app.__main__:main\n"
WHEEL_FILE = "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
META = f"{DIST_INFO}/METADATA"
ENTRY = f"{DIST_INFO}/entry_points.txt"


def write_tree(dest, pyproject=PYPROJECT, files=None):
    """A project tree: pyproject.toml plus the fixture files (or `files`)."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    for name, text in (FILES if files is None else files).items():
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return dest


def make_wheel(tree, out, *, put=None, drop=()):
    """A wheel assembled from `tree`: every file below sutra_app/ plus a clean dist-info; `put` adds or replaces members
    (str or bytes), `drop` removes members (a name that is not there is an error, so a typo cannot pass silently)."""
    members = {}
    for path in sorted((tree / "sutra_app").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            members[path.relative_to(tree).as_posix()] = path.read_bytes()
    members.update({META: METADATA, ENTRY: ENTRY_POINTS, f"{DIST_INFO}/WHEEL": WHEEL_FILE, f"{DIST_INFO}/RECORD": ""})
    members.update(put or {})
    for name in drop:
        del members[name]
    out.mkdir(parents=True, exist_ok=True)
    wheel = out / "sutra_pro-0.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return wheel


@pytest.fixture
def tree(tmp_path):
    return write_tree(tmp_path / "tree")


def problems_of(tree, tmp_path, **edits):
    return cw.check_wheel(make_wheel(tree, tmp_path / "dist", **edits), tree)


# ---------------------------------------------------------------- package data

def test_a_clean_wheel_has_no_problems(tree, tmp_path):
    assert problems_of(tree, tmp_path) == []


def test_a_glob_that_matches_no_wheel_member_is_reported(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=["sutra_app/pages/home.html"])
    assert len(problems) == 1
    assert "'pages/*'" in problems[0] and "of sutra_app" in problems[0]
    assert "1 file(s) in the tree (for example pages/home.html) but not one of them is in the wheel" in problems[0]


def test_a_double_star_glob_needs_one_member_not_all_of_them(tree, tmp_path):
    assert problems_of(tree, tmp_path, drop=["sutra_app/static/js/app.js"]) == []   # the top-level file is enough
    assert problems_of(tree, tmp_path, drop=["sutra_app/static/app.css"]) == []     # so is the nested one


def test_a_double_star_glob_with_no_member_at_all_is_reported(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=["sutra_app/static/app.css", "sutra_app/static/js/app.js"])
    assert len(problems) == 1
    assert "'static/**/*'" in problems[0] and "2 file(s) in the tree (for example static/app.css)" in problems[0]


def test_the_example_file_in_a_problem_does_not_depend_on_the_order_the_file_system_lists(tree, tmp_path, monkeypatch):
    real_glob = cw.glob.glob
    monkeypatch.setattr(cw.glob, "glob", lambda *a, **k: sorted(real_glob(*a, **k), reverse=True))
    problems = problems_of(tree, tmp_path, drop=["sutra_app/static/app.css", "sutra_app/static/js/app.js"])
    assert "(for example static/app.css)" in problems[0]


def test_a_literal_file_in_package_data_is_checked_like_any_glob(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=["sutra_app/policy.default.json"])
    assert len(problems) == 1 and "'policy.default.json'" in problems[0]


def test_a_member_in_another_package_directory_does_not_count(tree, tmp_path):
    """pages/* of sutra_app means sutra_app/pages/*, not a pages/ directory elsewhere in the wheel."""
    problems = problems_of(tree, tmp_path, drop=["sutra_app/pages/home.html"], put={"other/pages/home.html": "x"})
    assert len(problems) == 1 and "'pages/*'" in problems[0]


def test_a_wheel_member_whose_source_file_is_gone_does_not_count(tmp_path):
    files = {k: v for k, v in FILES.items() if k != "sutra_app/pages/home.html"}
    tree = write_tree(tmp_path / "tree", files=files)
    problems = problems_of(tree, tmp_path, put={"sutra_app/pages/ghost.html": "x"})
    assert len(problems) == 1
    assert "'pages/*'" in problems[0] and "matches no file in the tree (under sutra_app/)" in problems[0]


def test_a_stale_member_does_not_hide_a_file_missing_from_the_wheel(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=["sutra_app/pages/home.html"], put={"sutra_app/pages/ghost.html": "x"})
    assert len(problems) == 1 and "not one of them is in the wheel" in problems[0]


def test_a_glob_without_any_file_in_the_tree_is_reported(tmp_path):
    pyproject = PYPROJECT.replace('"policy.default.json"]', '"policy.default.json", "missing/*"]')
    tree = write_tree(tmp_path / "tree", pyproject=pyproject)
    problems = problems_of(tree, tmp_path)
    assert len(problems) == 1
    assert "'missing/*'" in problems[0] and "matches no file in the tree (under sutra_app/)" in problems[0]


def test_a_directory_is_not_a_file_for_a_glob(tmp_path):
    pyproject = PYPROJECT.replace('"policy.default.json"]', '"policy.default.json", "emptydir"]')
    tree = write_tree(tmp_path / "tree", pyproject=pyproject)
    (tree / "sutra_app" / "emptydir").mkdir()
    problems = problems_of(tree, tmp_path)
    assert len(problems) == 1 and "'emptydir'" in problems[0] and "matches no file in the tree" in problems[0]


def test_a_hidden_file_alone_does_not_satisfy_a_glob(tmp_path):
    """setuptools does not ship dot-files for a `*` glob, so a glob that only finds one is empty."""
    pyproject = PYPROJECT.replace('"policy.default.json"]', '"policy.default.json", "dot/*"]')
    tree = write_tree(tmp_path / "tree", pyproject=pyproject, files={**FILES, "sutra_app/dot/.keep": ""})
    problems = problems_of(tree, tmp_path)
    assert len(problems) == 1 and "'dot/*'" in problems[0] and "matches no file in the tree" in problems[0]


def test_every_failing_glob_is_reported_not_only_the_first(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=["sutra_app/pages/home.html", "sutra_app/policy.default.json"])
    assert len(problems) == 2
    assert "'pages/*'" in problems[0] and "'policy.default.json'" in problems[1]


def test_a_dotted_package_key_maps_to_its_directory(tmp_path):
    pyproject = PYPROJECT.replace('sutra_app = ["pages/*", "static/**/*", "policy.default.json"]',
                                  '"sutra_app.ui" = ["assets/*"]')
    tree = write_tree(tmp_path / "tree", pyproject=pyproject, files={**FILES, "sutra_app/ui/assets/logo.svg": "<svg/>"})
    assert problems_of(tree, tmp_path) == []
    problems = problems_of(tree, tmp_path, drop=["sutra_app/ui/assets/logo.svg"])
    assert len(problems) == 1 and "'assets/*'" in problems[0] and "of sutra_app.ui" in problems[0]


def test_package_dir_maps_the_tree_to_the_wheel_for_a_src_layout(tmp_path):
    pyproject = PYPROJECT + '\n[tool.setuptools.package-dir]\n"" = "src"\n'
    tree = write_tree(tmp_path / "tree", pyproject=pyproject, files={f"src/{k}": v for k, v in FILES.items()})
    wheel = make_wheel(tree / "src", tmp_path / "dist")
    assert cw.check_wheel(wheel, tree) == []
    wheel = make_wheel(tree / "src", tmp_path / "dist", drop=["sutra_app/pages/home.html"])
    problems = cw.check_wheel(wheel, tree)
    assert len(problems) == 1 and "'pages/*'" in problems[0]


def test_without_package_dir_a_src_tree_has_no_files_for_the_globs(tmp_path):
    tree = write_tree(tmp_path / "tree", files={f"src/{k}": v for k, v in FILES.items()})
    wheel = make_wheel(tree / "src", tmp_path / "dist")
    problems = cw.check_wheel(wheel, tree)
    assert len(problems) == 3 and all("matches no file in the tree" in p for p in problems)


def test_package_dir_can_name_one_package(tmp_path):
    pyproject = PYPROJECT + '\n[tool.setuptools.package-dir]\nsutra_app = "lib/sutra_app"\n'
    tree = write_tree(tmp_path / "tree", pyproject=pyproject, files={f"lib/{k}": v for k, v in FILES.items()})
    assert cw.check_wheel(make_wheel(tree / "lib", tmp_path / "dist"), tree) == []


def test_source_dir_unit(tmp_path):
    assert str(cw.source_dir({}, "a")) == "a"
    assert str(cw.source_dir({}, "a.b.c")) == "a/b/c"
    assert str(cw.source_dir({"tool": {"setuptools": {"package-dir": {"": "src"}}}}, "a.b")) == "src/a/b"
    assert str(cw.source_dir({"tool": {"setuptools": {"package-dir": {"a": "lib/a"}}}}, "a")) == "lib/a"
    assert str(cw.source_dir({"tool": {"setuptools": {"package-dir": {"a": "lib/a", "": "src"}}}}, "b")) == "src/b"
    assert str(cw.source_dir({"tool": {"setuptools": {"package-dir": "oops"}}}, "a")) == "a"


@pytest.mark.parametrize("table,expected", [
    ("", "has no [tool.setuptools.package-data]"),
    ("\n[tool.setuptools.package-data]\n", "has no [tool.setuptools.package-data]"),
    ('\n[tool.setuptools.package-data]\n"*" = ["x"]\n', "package-data key '*' is not supported"),
    ('\n[tool.setuptools.package-data]\nsutra_app = "pages/*"\n', "package-data of sutra_app is not a list of globs"),
    ("\n[tool.setuptools.package-data]\nsutra_app = [1]\n", "package-data of sutra_app is not a list of globs"),
])
def test_a_package_data_table_that_cannot_be_checked_is_a_problem(tmp_path, table, expected):
    pyproject = PYPROJECT.split("[tool.setuptools.package-data]")[0] + table
    tree = write_tree(tmp_path / "tree", pyproject=pyproject)
    problems = problems_of(tree, tmp_path)
    assert len(problems) == 1 and expected in problems[0]


def test_a_missing_pyproject_is_one_problem_and_the_other_checks_still_run(tree, tmp_path):
    wheel = make_wheel(tree, tmp_path / "dist", put={META: "Metadata-Version: 2.1\nName: wrong\n"})
    (tree / "pyproject.toml").unlink()
    problems = cw.check_wheel(wheel, tree)
    assert len(problems) == 2
    assert problems[0].startswith("cannot read pyproject.toml under ") and "METADATA Name is 'wrong'" in problems[1]


def test_an_unparsable_pyproject_is_a_problem(tree, tmp_path):
    wheel = make_wheel(tree, tmp_path / "dist")
    (tree / "pyproject.toml").write_text("[project\n")
    problems = cw.check_wheel(wheel, tree)
    assert len(problems) == 1 and problems[0].startswith("cannot read pyproject.toml under ")


# ---------------------------------------------------------------- the console script

@pytest.mark.parametrize("text", [
    "[console_scripts]\nsutra-pro=sutra_app.__main__:main\n",                                         # no spaces
    "[console_scripts]\nsutra-pro   =   sutra_app.__main__:main   \n",                                # padded
    "# generated\n[console_scripts]\nsutra-pro = sutra_app.__main__:main\n",                           # a comment first
    "[console_scripts]\nother = pkg.mod:func\nsutra-pro = sutra_app.__main__:main\n[gui_scripts]\ng = a:b\n",
    "[console_scripts]\nsutra-pro = sutra_app.__main__:main\nodd = a:b%s%(x)s\n",                      # % is not interpolated
    "[console_scripts]\r\nsutra-pro = sutra_app.__main__:main\r\n",                                    # CRLF
    "[console_scripts]\nsutra-pro = sutra_app.__main__:main\n[console_scripts]\nsutra-pro = sutra_app.__main__:main\n",
])
def test_entry_points_that_declare_the_script_pass(tree, tmp_path, text):
    assert problems_of(tree, tmp_path, put={ENTRY: text}) == []


@pytest.mark.parametrize("text,expected", [
    ("", "declares no console script 'sutra-pro' (it declares: none)"),
    ("[console_scripts]\nother = x:y\n", "declares no console script 'sutra-pro' (it declares: ['other'])"),
    ("[console_scripts]\nsutra-app = sutra_app.__main__:main\n", "declares no console script 'sutra-pro'"),
    ("[console_scripts]\nsutra_pro = sutra_app.__main__:main\n", "declares no console script 'sutra-pro'"),
    ("[console_scripts]\nSutra-Pro = sutra_app.__main__:main\n", "declares no console script 'sutra-pro'"),
    ("[gui_scripts]\nsutra-pro = sutra_app.__main__:main\n", "declares no console script 'sutra-pro'"),
    ("[console_scripts]\nsutra-pro = sutra_app.__main__:run\n", "points at 'sutra_app.__main__:run'"),
    ("[console_scripts]\nsutra-pro = sutra_app.cli:main\n", "points at 'sutra_app.cli:main'"),
    ("[console_scripts]\nsutra-pro = sutra_app.__main__\n", "points at 'sutra_app.__main__'"),
    ("[console_scripts]\nsutra-pro = sutra_app.__main__:main [extra]\n", "points at 'sutra_app.__main__:main [extra]'"),
    ("[console_scripts]\nsutra-pro = other.__main__:main\n", "points at 'other.__main__:main'"),
    ("sutra-pro = sutra_app.__main__:main\n", "entry_points.txt cannot be parsed"),                     # no section header
    ("[console_scripts]\nsutra-pro: sutra_app.__main__:main\n", "entry_points.txt cannot be parsed"),   # only `=` separates
    ("[console_scripts\nsutra-pro = sutra_app.__main__:main\n", "entry_points.txt cannot be parsed"),
])
def test_entry_points_that_do_not_declare_the_script_are_reported(tree, tmp_path, text, expected):
    problems = problems_of(tree, tmp_path, put={ENTRY: text})
    assert len(problems) == 1 and expected in problems[0]


def test_a_wheel_without_entry_points_is_reported(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=[ENTRY])
    assert problems == ["the wheel has no entry_points.txt, so it declares no console script"]


# ---------------------------------------------------------------- the distribution name

@pytest.mark.parametrize("text", [
    "Metadata-Version: 2.1\nName: sutra-pro\nVersion: 0.0.1\n",
    "Version: 0.0.1\nName: sutra-pro\n",
    "Metadata-Version: 2.1\nName: sutra-pro\n\nName: sutra-app\n\nA description that mentions Name: other\n",
    "Metadata-Version: 2.4\r\nName: sutra-pro\r\nVersion: 0.0.1\r\n",
])
def test_metadata_with_the_right_name_passes(tree, tmp_path, text):
    assert problems_of(tree, tmp_path, put={META: text}) == []


@pytest.mark.parametrize("text,shown", [
    ("Metadata-Version: 2.1\nName: sutra-app\n", "'sutra-app'"),
    ("Metadata-Version: 2.1\nName: sutra_pro\n", "'sutra_pro'"),
    ("Metadata-Version: 2.1\nName: Sutra-Pro\n", "'Sutra-Pro'"),
    ("Metadata-Version: 2.1\nName: sutra-pro-extra\n", "'sutra-pro-extra'"),
    ("Metadata-Version: 2.1\nName: sutra\n", "'sutra'"),
    ("Metadata-Version: 2.1\nVersion: 0.0.1\n", "None"),                       # no Name header
    ("", "None"),
    ("Metadata-Version: 2.1\nVersion: 0.0.1\n\nName: sutra-pro\n", "None"),    # Name only in the description
])
def test_metadata_with_another_name_is_reported(tree, tmp_path, text, shown):
    problems = problems_of(tree, tmp_path, put={META: text})
    assert problems == [f"METADATA Name is {shown}, expected 'sutra-pro'"]


def test_a_wheel_without_metadata_is_reported(tree, tmp_path):
    assert problems_of(tree, tmp_path, drop=[META]) == ["the wheel has no METADATA"]


# ---------------------------------------------------------------- the wheel as a file

def test_a_wheel_without_a_dist_info_directory_is_reported(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=[META, ENTRY, f"{DIST_INFO}/WHEEL", f"{DIST_INFO}/RECORD"])
    assert "expected exactly one *.dist-info directory in the wheel, found 0" in problems
    assert len(problems) == 3     # and the two files that should be in it are missing as well


def test_a_wheel_with_two_dist_info_directories_is_reported(tree, tmp_path):
    problems = problems_of(tree, tmp_path, put={"other-1.0.dist-info/METADATA": METADATA})
    assert problems == [
        f"expected exactly one *.dist-info directory in the wheel, found 2: other-1.0.dist-info, {DIST_INFO}",
        "the wheel has no entry_points.txt, so it declares no console script",   # which of the two to read is not guessed
        "the wheel has no METADATA",
    ]


def test_a_file_that_is_not_a_zip_is_one_problem(tmp_path):
    bad = tmp_path / "x.whl"
    bad.write_text("this is not a zip file")
    problems = cw.check_wheel(bad, ROOT)
    assert len(problems) == 1 and problems[0].startswith("cannot read the wheel: ")


def test_a_missing_wheel_is_one_problem(tmp_path):
    problems = cw.check_wheel(tmp_path / "nowhere.whl", ROOT)
    assert len(problems) == 1 and problems[0].startswith("cannot read the wheel: ")


def test_a_metadata_that_is_not_utf8_is_one_problem(tree, tmp_path):
    problems = problems_of(tree, tmp_path, put={META: b"Name: \xff\xfe\n"})
    assert len(problems) == 1 and problems[0].startswith("cannot read the wheel: ")


def test_an_empty_zip_fails_every_check(tree, tmp_path):
    empty = tmp_path / "empty.whl"
    zipfile.ZipFile(empty, "w").close()
    problems = cw.check_wheel(empty, tree)
    assert len(problems) == 3 + 1 + 2     # three globs, no dist-info, no entry_points.txt, no METADATA
    assert problems[-1] == "the wheel has no METADATA"


def test_all_three_kinds_of_problem_are_reported_together(tree, tmp_path):
    problems = problems_of(tree, tmp_path, drop=["sutra_app/pages/home.html"], put={
        ENTRY: "[console_scripts]\nsutra-pro = sutra_app.cli:main\n",
        META: "Metadata-Version: 2.1\nName: sutra-app\n",
    })
    assert len(problems) == 3
    assert "'pages/*'" in problems[0] and "points at 'sutra_app.cli:main'" in problems[1] and "'sutra-app'" in problems[2]


# ---------------------------------------------------------------- the command line

def test_main_prints_ok_for_a_clean_wheel(tree, tmp_path, capsys):
    wheel = make_wheel(tree, tmp_path / "dist")
    assert cw.main([str(wheel), "--root", str(tree)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ok: sutra_pro-0.0.1-py3-none-any.whl: ") and "::error::" not in out
    assert "sutra-pro -> sutra_app.__main__:main" in out and len(out.splitlines()) == 1


def test_main_prints_one_annotation_per_problem_and_returns_1(tree, tmp_path, capsys):
    wheel = make_wheel(tree, tmp_path / "dist", drop=["sutra_app/pages/home.html"],
                       put={META: "Metadata-Version: 2.1\nName: sutra-app\n"})
    assert cw.main([str(wheel), "--root", str(tree)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and all(line.startswith("::error::sutra_pro-0.0.1-py3-none-any.whl: ") for line in lines)
    assert "'pages/*'" in lines[0] and "METADATA Name is 'sutra-app'" in lines[1]


def test_main_checks_every_wheel_and_fails_when_any_fails(tree, tmp_path, capsys):
    good = make_wheel(tree, tmp_path / "good")
    bad = make_wheel(tree, tmp_path / "bad", put={ENTRY: ""})
    assert cw.main([str(good), str(bad), "--root", str(tree)]) == 1
    out = capsys.readouterr().out
    assert out.count("ok: ") == 1 and out.count("::error::") == 1
    assert cw.main([str(bad), str(good), "--root", str(tree)]) == 1     # the order does not matter
    assert cw.main([str(good), str(good), "--root", str(tree)]) == 0


def test_main_fails_on_a_wheel_that_is_not_there(tmp_path, capsys):
    assert cw.main([str(tmp_path / "dist" / "*.whl")]) == 1       # an unmatched shell glob arrives as the literal pattern
    assert "::error::*.whl: cannot read the wheel" in capsys.readouterr().out


def test_main_needs_a_wheel():
    with pytest.raises(SystemExit) as stop:
        cw.main([])
    assert stop.value.code == 2


def test_main_checks_against_this_checkouts_tree_by_default(tree, tmp_path, capsys):
    """Without --root the tree is this repository: a fixture wheel cannot hold its package data."""
    wheel = make_wheel(tree, tmp_path / "dist")
    assert cw.main([str(wheel)]) == 1
    assert "'ui/pages/*'" in capsys.readouterr().out


def test_the_script_runs_as_a_program(tree, tmp_path):
    wheel = make_wheel(tree, tmp_path / "dist")
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], capture_output=True, text=True, timeout=60)
    ok = run(str(wheel), "--root", str(tree))
    assert ok.returncode == 0 and ok.stdout.startswith("ok: ") and ok.stderr == ""
    bad = run(str(make_wheel(tree, tmp_path / "bad", drop=[ENTRY])), "--root", str(tree))
    assert bad.returncode == 1 and bad.stdout.startswith("::error::") and bad.stderr == ""
    assert run().returncode == 2


def test_annotation_escapes_the_three_characters_github_decodes():
    assert cw.annotation("a%b\nc\rd") == "::error::a%25b%0Ac%0Dd"


# ---------------------------------------------------------------- wheels built by the real tool

def build_with_uv(project, out, *, wheel_only):
    """`uv build` offline. Skips, with the reason printed, where uv is missing or cannot build without the network."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed: no wheel can be built here")
    command = [uv, "build", "--out-dir", str(out), str(project)] + (["--wheel"] if wheel_only else [])
    proc = subprocess.run(command, capture_output=True, text=True, timeout=300, env={**os.environ, "UV_OFFLINE": "1"})
    if proc.returncode != 0:
        lowered = proc.stderr.lower()
        if "network" in lowered and "disabled" in lowered:
            pytest.skip("uv cannot build offline here (the build requirements are not in its cache): " + proc.stderr.strip()[-300:])
        pytest.fail(f"uv build failed:\n{proc.stderr}")
    wheels = sorted(out.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


@pytest.fixture(scope="module")
def built_fixture(tmp_path_factory):
    """(tree, wheel): the fixture project and the wheel setuptools builds from it. Built once for the tests that read it."""
    tree = write_tree(tmp_path_factory.mktemp("fixture-tree"))
    return tree, build_with_uv(tree, tmp_path_factory.mktemp("fixture-dist"), wheel_only=True)


def test_a_wheel_built_by_setuptools_from_the_fixture_passes(built_fixture):
    tree, wheel = built_fixture
    assert wheel.name == "sutra_pro-0.0.1-py3-none-any.whl"
    assert cw.check_wheel(wheel, tree) == []
    names = set(zipfile.ZipFile(wheel).namelist())
    assert {"sutra_app/pages/home.html", "sutra_app/static/app.css", "sutra_app/static/js/app.js",
            "sutra_app/policy.default.json"} <= names


def test_the_wheel_uv_builds_from_the_sdist_passes_too(tmp_path):
    """`uv build` without flags is what the workflows run: the sdist first, then the wheel from that sdist."""
    tree = write_tree(tmp_path / "tree")
    wheel = build_with_uv(tree, tmp_path / "dist", wheel_only=False)
    assert len(list((tmp_path / "dist").glob("*.tar.gz"))) == 1, "uv build made the sdist as well"
    assert cw.check_wheel(wheel, tree) == []


def test_a_wheel_built_by_setuptools_fails_when_the_pyproject_asks_for_more_than_the_tree_holds(built_fixture, tmp_path):
    tree, wheel = built_fixture
    other = shutil.copytree(tree, tmp_path / "tree", ignore=shutil.ignore_patterns("build", "*.egg-info"))
    (other / "pyproject.toml").write_text(PYPROJECT.replace('"policy.default.json"]', '"policy.default.json", "nothing/**/*"]'))
    problems = cw.check_wheel(wheel, other)
    assert len(problems) == 1 and "'nothing/**/*'" in problems[0]


@pytest.fixture(scope="module")
def real_wheel(tmp_path_factory):
    """This repository's own wheel, built from a copy of pyproject.toml and sutra_app/ (the tree itself is never written to)."""
    work = tmp_path_factory.mktemp("real-tree")
    shutil.copy2(ROOT / "pyproject.toml", work / "pyproject.toml")
    shutil.copytree(ROOT / "sutra_app", work / "sutra_app",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info", ".DS_Store"))
    return build_with_uv(work, tmp_path_factory.mktemp("real-dist"), wheel_only=True)


def tree_files(package, pattern):
    """Files of `package` that a package-data glob finds, by pathlib (an independent expansion; dot-files are hidden)."""
    base = ROOT / Path(*package.split("."))
    return {rel.as_posix() for rel in (p.relative_to(base) for p in base.glob(pattern) if p.is_file())
            if not any(part.startswith(".") for part in rel.parts)}


def test_the_real_wheel_is_checked_against_the_real_tree(real_wheel):
    """The entry point and the name must be right today. Package data may only be missing for a glob whose files do not
    exist in the tree yet (other work packages add them); once they all exist the same assertion demands a clean wheel."""
    table = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
    globs = [(package, pattern) for package, patterns in table.items() for pattern in patterns]
    names = set(zipfile.ZipFile(real_wheel).namelist())
    problems = cw.check_wheel(real_wheel, ROOT)
    empty = {pattern for package, pattern in globs if not tree_files(package, pattern)}
    flagged = re.findall(r"package-data glob '([^']*)'", "\n".join(problems))
    assert sorted(flagged) == sorted(empty), problems
    assert len(problems) == len(empty), f"something other than empty globs was reported: {problems}"
    for package, pattern in globs:           # setuptools and the checker agree on what a glob means
        for found in tree_files(package, pattern):
            assert f"{package}/{found}" in names, f"{package}/{found} matches {pattern!r} but is not in the real wheel"


def test_the_real_wheel_declares_the_command_and_the_name(real_wheel):
    with zipfile.ZipFile(real_wheel) as archive:
        entry = next(n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt"))
        meta = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        assert "sutra-pro = sutra_app.__main__:main" in archive.read(entry).decode()
        assert "\nName: sutra-pro\n" in archive.read(meta).decode()
    assert real_wheel.name == f"sutra_pro-{tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']}-py3-none-any.whl"
