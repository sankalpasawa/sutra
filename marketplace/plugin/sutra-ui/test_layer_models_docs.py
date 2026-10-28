"""test_layer_models_docs.py -- the documents beside the pydantic interface, and the staged copy (PRD amendment A4, A4-DOCS).

The README of layer_models names every module and the twelve rules; the README of schemas/layers names every file there; the A4 rows of
the decision log are all there; and the install stage carries the package, so the staged copy imports it."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
README = (HERE / "layer_models" / "README.md").read_text(encoding="utf-8")
SCHEMAS_README = (HERE / "schemas" / "layers" / "README.md").read_text(encoding="utf-8")
DECISIONS = (HERE / "design" / "PRD-FIVE-FUNCTIONS-DECISIONS.md").read_text(encoding="utf-8")


def test_the_readme_names_every_module():
    missing = [p.name for p in sorted((HERE / "layer_models").glob("*.py")) if p.name != "__init__.py" and "`%s`" % p.name not in README]
    assert missing == []


def test_the_readme_names_the_twelve_rules():
    for n in range(1, 13):
        assert "| **R%d** |" % n in README, "rule R%d" % n
    for row in re.findall(r"^\| \*\*R\d+\*\* \|.*$", README, re.M):
        tests = re.findall(r"`(test_[a-z0-9_]+)`", row)
        assert tests, "every rule names its test: " + row[:40]
        for name in tests:
            assert any(("def %s(" % name) in f.read_text(encoding="utf-8") for f in HERE.glob("test_layer_models_*.py")), name


def test_the_schemas_readme_names_every_file():
    files = [p for p in (HERE / "schemas" / "layers").iterdir() if p.is_file() and p.name != "README.md"]
    assert files
    assert [p.name for p in files if p.name not in SCHEMAS_README] == []
    assert "fixtures/" in SCHEMAS_README
    for p in (HERE / "schemas" / "models").iterdir():
        assert "schemas/models/%s" % p.name in SCHEMAS_README, p.name


def test_the_main_readme_has_its_section():
    assert "## The interface is pydantic" in (HERE / "README.md").read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("rsync"), reason="the install stage uses rsync")
def test_the_staged_copy_imports_the_package(tmp_path):
    """install.sh's stage_runtime rsync (the same excludes), then layer_models imported from the copy and validated against."""
    src = tmp_path / "stage"
    subprocess.run(["rsync", "-a", "--delete", "--delete-excluded", "--exclude", ".venv/", "--exclude", ".git/", "--exclude", "__pycache__/",
                    "--exclude", "*.pyc", "--exclude", "test_*", "--exclude", ".DS_Store", "--exclude", "electron/node_modules/",
                    "--exclude", "electron/dist/", "--exclude", "electron/payload/", "--exclude", "mock/", str(HERE) + "/", str(src) + "/"], check=True)
    assert (src / "layer_models" / "__init__.py").is_file() and (src / "models_api.py").is_file()
    code = ("import layer_models, layer_schema as S, pathlib;"
            "assert pathlib.Path(layer_models.__file__).resolve().parent.parent == pathlib.Path('.').resolve();"
            "assert len(layer_models.classes()) > 50 and len(S.DEFS) == 130;"
            "assert S.validate('identity.ask', {}) != [];"
            "print('ok')")
    got = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, '.');" + code], cwd=str(src), capture_output=True, text=True, timeout=120)
    assert got.returncode == 0 and got.stdout.strip() == "ok", got.stderr[-800:]
