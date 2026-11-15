"""The wheel carries every data file the app reads (S3-web-08, D86, D88; work package ORCH-8).

From a checkout every file is simply there, so no test run in the checkout can see a missing data file; the first user of the wheel would.
These tests keep two promises as files are added: (1) every non-Python file under `sutra_app/` is matched by a `[tool.setuptools.package-data]`
glob of `pyproject.toml` (and no glob is dead); (2) a built wheel holds them (slow, `SUTRA_SLOW=1`). A third promise is checked by running
the app: nothing the running app opens lives under `docs/` (a wheel has no `docs/`; `docs/schemas/` is generated documentation)."""
import ast
import builtins
import glob
import io
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "sutra_app"
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
GLOBS: list[str] = PYPROJECT["tool"]["setuptools"]["package-data"]["sutra_app"]
NOT_DATA = {"engine/VENDORED.md"}                  # the vendoring log is documentation: intentionally not shipped (S3-web-08)
JUNK = {".DS_Store"}
# files the app cannot run without (design: ui 4, engine 3.1, orchestrator 2 and 5.2, library 10, connectors 5.2)
MUST_SHIP = [
    "ui/pages/home.html", "ui/pages/j2_ui.html", "ui/pages/j2_ui_render.js", "ui/pages/j2_graph_layout.js",
    "orchestrator/agent/templates/decide.md", "orchestrator/agent/templates/change.md", "orchestrator/agent/templates/assign.md",
    "orchestrator/agent/templates/retry.md", "library/specs/function_specs.json", "connectors/policy.default.json",
]


def data_files() -> list[str]:
    """Every file under `sutra_app/` that is not Python, not a bytecode folder and not junk, as a path relative to the package."""
    found = []
    for path in PACKAGE.rglob("*"):
        rel = path.relative_to(PACKAGE).as_posix()
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in (".py", ".pyc", ".pyo") or path.name in JUNK:
            continue
        found.append(rel)
    return sorted(found)


def matched_by(pattern: str) -> set[str]:
    """What setuptools gives a package-data pattern: `glob.glob(recursive=True)` from the package folder, files only."""
    return {Path(f).as_posix() for f in glob.glob(pattern, root_dir=PACKAGE, recursive=True) if (PACKAGE / f).is_file()}


# ============================================ the globs and the tree =========================================================

def test_every_data_file_is_matched_by_a_package_data_glob():
    covered = set().union(*(matched_by(p) for p in GLOBS))
    missing = [f for f in data_files() if f not in covered and f not in NOT_DATA]
    assert not missing, f"these files would not be in the wheel (add a glob to [tool.setuptools.package-data]): {missing[:10]}"


def test_no_glob_is_dead():
    dead = [p for p in GLOBS if not matched_by(p)]
    assert not dead, f"these package-data globs match no file (a glob that ships nothing is a mistake or a leftover): {dead}"


def test_the_vendoring_log_is_documentation_and_no_glob_names_it():
    """(MANIFEST.in lists it for the sdist, and `include-package-data` then lets it into the wheel too: harmless, but it is no app data.)"""
    covered = set().union(*(matched_by(p) for p in GLOBS))
    assert "engine/VENDORED.md" not in covered and (PACKAGE / "engine" / "VENDORED.md").is_file()


def test_the_files_the_app_cannot_run_without_exist_and_are_covered():
    covered = set().union(*(matched_by(p) for p in GLOBS))
    assert [f for f in MUST_SHIP if not (PACKAGE / f).is_file()] == []
    assert [f for f in MUST_SHIP if f not in covered] == []


def test_a_file_nobody_listed_would_be_found(tmp_path, monkeypatch):
    """The check is not a rubber stamp: a new data folder that no glob names is reported."""
    stray = PACKAGE / "orchestrator" / "_packaging_probe" / "notes.txt"
    stray.parent.mkdir()
    try:
        stray.write_text("x")
        covered = set().union(*(matched_by(p) for p in GLOBS))
        assert "orchestrator/_packaging_probe/notes.txt" in data_files() and "orchestrator/_packaging_probe/notes.txt" not in covered
    finally:
        shutil.rmtree(stray.parent)


def test_the_project_declares_the_command_and_both_package_data_and_the_manifest_agree():
    assert PYPROJECT["project"]["scripts"] == {"sutra-pro": "sutra_app.__main__:main"} and PYPROJECT["tool"]["setuptools"]["include-package-data"]
    manifest = (REPO / "MANIFEST.in").read_text()
    for folder in ("ui/pages", "ui/static", "engine/agents", "engine/conditions", "engine/artifacts", "engine/templates", "engine/seed",
                   "orchestrator/agent/templates"):
        assert f"sutra_app/{folder}" in manifest, f"MANIFEST.in does not carry {folder} (the sdist would drop it)"
    assert "sutra_app/connectors/policy.default.json" in manifest


def test_the_entry_point_is_a_callable_that_takes_no_argument_and_answers_help():
    from sutra_app.__main__ import main
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    assert callable(main)


# ============================================ nothing reads docs/ at runtime =================================================

DOCS_SCHEMAS = REPO / "docs" / "schemas"
# generators and checkers that write or diff docs/schemas on request (never on the way to serving a page); the reason is the entry
GENERATORS = {
    "library/export.py": "the `export` command writes (or with --check diffs) docs/schemas",
}


def mentions_docs_schemas(source: str) -> bool:
    """A path built as ... / "docs" / "schemas" (or the text docs/schemas inside a string that is used, not only documented)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = []
            cur = node
            while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
                if isinstance(cur.right, ast.Constant):
                    parts.append(cur.right.value)
                cur = cur.left
            if "docs" in parts and "schemas" in parts:
                return True
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("joinpath", "join"):
            values = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if "docs" in values and "schemas" in values:
                return True
    return False


def test_only_the_generators_name_the_docs_schemas_folder():
    found = {}
    for path in PACKAGE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if mentions_docs_schemas(path.read_text(encoding="utf-8")):
            found[path.relative_to(PACKAGE).as_posix()] = True
    assert set(found) == set(GENERATORS), f"a module builds a path to docs/schemas: {sorted(set(found) - set(GENERATORS))}; or a generator stopped doing so"


def test_a_running_app_opens_nothing_under_docs(tmp_path, monkeypatch):
    """Boot the whole app, make a team and read its pages and routes while recording every file opened: none is under docs/."""
    import orchestrator.conftest  # noqa: F401  (puts tests/library on sys.path, which the scripted conversation's factories need)
    from fastapi.testclient import TestClient
    from orchestrator.test_scripted_conversation import Scenario, make_scenario, new_team
    opened: list[str] = []
    real_open, real_io_open = builtins.open, io.open

    def record(path):
        try:
            if isinstance(path, (str, bytes, os.PathLike)):
                text = os.fsdecode(path)
                if os.path.abspath(text).startswith(str(REPO / "docs")):
                    opened.append(text)
        except (TypeError, ValueError):
            pass

    def spy(path, *args, **kwargs):
        record(path)
        return real_open(path, *args, **kwargs)

    def spy_io(path, *args, **kwargs):
        record(path)
        return real_io_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy_io)
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8780") as client:
        c = Scenario(client, app, connector)
        new_team(c)
        for path in ("/", "/api/health", "/api/graph?level=full", "/api/chart", "/api/schemas", "/openapi.json", "/api/connectors/status"):
            assert client.get(path).status_code == 200, path
    assert opened == []


# ============================================ the real wheel (slow) ==========================================================

@pytest.mark.slow
def test_a_built_wheel_holds_every_data_file_and_the_command(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed: no wheel can be built here")
    tree = tmp_path / "tree"
    shutil.copytree(REPO, tree, ignore=shutil.ignore_patterns(".git", ".venv", "data", "docs", "tests", "dist", "build", "*.egg-info", "__pycache__",
                                                            "node_modules", ".pytest_cache", "scripts"))
    out = tmp_path / "dist"
    proc = subprocess.run([uv, "build", "--wheel", "--offline", "--out-dir", str(out), str(tree)], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        if "offline" in proc.stderr.lower() or "network" in proc.stderr.lower() or "resolve" in proc.stderr.lower():
            pytest.skip("uv cannot build offline here (the build requirements are not in its cache): " + proc.stderr.strip()[-300:])
        pytest.fail(f"uv build failed:\n{proc.stderr}")
    [wheel] = list(out.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    expected = {f"sutra_app/{f}" for f in data_files() if f not in NOT_DATA}
    assert sorted(expected - names)[:10] == []
    assert "sutra_app/main.py" in names and "sutra_app/__main__.py" in names and "sutra_app/orchestrator/wiring.py" in names
    assert not [n for n in names if n.startswith(("docs/", "tests/", "scripts/")) or "/tests/" in n]
    check = subprocess.run([sys.executable, str(REPO / "scripts" / "check_wheel.py"), str(wheel), "--root", str(tree)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
