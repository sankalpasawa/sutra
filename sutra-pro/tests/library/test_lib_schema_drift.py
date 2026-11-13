"""`docs/schemas/` equals a fresh export (library design 3.3, flow F5; work package L8).

The export runs in a CHILD process: the registry of this process may hold the orchestrator's families too (its test files import
`orchestrator/records.py`), which a real export never sees. A change to a class that is not followed by `python -m
sutra_app.library.export` fails here, so a breaking change cannot merge without its schema diff being reviewed."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "docs" / "schemas"


def export(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SUTRA_", "J2_"))}
    env["PYTHONPATH"] = f"{REPO}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(REPO)
    return subprocess.run([sys.executable, "-m", "sutra_app.library.export", *args], env=env, cwd=cwd or REPO,
                          capture_output=True, text=True, timeout=120)


def test_docs_schemas_equals_a_fresh_export():
    done = export("--check")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "up to date" in done.stdout


def test_the_index_lists_every_schema_file_and_every_file_is_a_json_schema():
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    files = sorted(p.name for p in SCHEMAS.glob("*.v*.json"))
    assert files == sorted(f"{family}.v{version}.json" for family, versions in index.items() for version in versions)
    assert len(index) > 35 and {"atom", "node", "org_chart", "goal", "run_message", "receipt", "template.file"} <= set(index)
    schema = json.loads((SCHEMAS / "atom.v1.json").read_text(encoding="utf-8"))
    assert schema["type"] == "object" and "id" in schema["properties"]


def test_a_changed_a_deleted_and_a_left_over_schema_file_are_each_found(tmp_path):
    copy = tmp_path / "schemas"
    shutil.copytree(SCHEMAS, copy)
    schema = json.loads((copy / "department.v1.json").read_text(encoding="utf-8"))
    schema["properties"].pop("home_dir")                                    # a field removed without a version bump
    (copy / "department.v1.json").write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (copy / "atom.v1.json").unlink()
    (copy / "ghost.v1.json").write_text("{}\n", encoding="utf-8")
    done = export("--check", "--dir", str(copy))
    assert done.returncode == 1
    assert "differs: department.v1.json" in done.stdout and "missing: atom.v1.json" in done.stdout and "stale: ghost.v1.json" in done.stdout


def test_the_export_writes_the_same_files_into_an_empty_folder(tmp_path):
    done = export("--dir", str(tmp_path / "fresh"))
    assert done.returncode == 0, done.stderr
    fresh = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "fresh").iterdir()}
    assert fresh == {p.name: p.read_text(encoding="utf-8") for p in SCHEMAS.iterdir() if p.is_file()}


def test_docs_schemas_holds_no_copy_of_the_generic_templates_or_the_section_models():
    """D171: J2's `templates/<type>/generic.json` is the single source; the library exports nothing of it."""
    assert not (SCHEMAS / "templates").exists()
    assert not list(SCHEMAS.glob("artifact.*.json"))
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    assert not [name for name in index if name.startswith("artifact.")] and "artifact_data" in index
