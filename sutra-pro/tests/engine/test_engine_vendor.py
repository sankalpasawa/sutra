"""The vendored J2 tree (work package E1, engine design 3.1, 3.4 and decision D13): package-relative imports (P1), every
module imports, the data files are there, and VENDORED.md tells the truth about every file (commit, hashes, patch ids).
Nothing here reads the J2 prototype except the one test that needs `SUTRA_J2_CHECKOUT` (it skips without it)."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ENGINE = REPO / "sutra_app" / "engine"
MD = ENGINE / "VENDORED.md"
CODE = ("j2", "j2_agent", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change", "j2_check", "j2_map",
        "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_template_lib")
SIBLINGS = set(CODE) | {"llm", "rehydrate"}
ROLE_FILES = {"team.md", "identity.md", "adaptation.md", "priority.md", "coordination.md", "audit.md", "builder.md",
              "confidence-judge.md", "rates.json", "stages.json"}
ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \| ([^|]+?) \| `([0-9a-f]{64})` \| `([0-9a-f]{64})` \|$")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows() -> list:
    found = [m.groups() for line in MD.read_text(encoding="utf-8").splitlines() if (m := ROW.match(line))]
    assert found, "VENDORED.md has no file table"
    return found


# ---- P1: package-relative imports ------------------------------------------------------------------------------------
def test_no_module_of_the_engine_imports_j2_or_llm_by_its_flat_name():
    flat = re.compile(r"^\s*(import|from) (j2|llm)\b", re.M)
    bad = [str(p.relative_to(REPO)) for p in (ENGINE).rglob("*.py") if flat.search(p.read_text(encoding="utf-8"))]
    assert bad == []


@pytest.mark.parametrize("name", CODE + ("rehydrate",))
def test_p1_no_sibling_is_imported_by_its_flat_name(name):
    """Walks the whole syntax tree, so the three lazy imports inside functions of j2_artifacts count too."""
    tree = ast.parse((ENGINE / f"{name}.py").read_text(encoding="utf-8"))
    flat = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            flat += [a.name for a in node.names if a.name.split(".")[0] in SIBLINGS]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] in SIBLINGS:
            flat.append(node.module)
    assert flat == []


def test_p1_j2_artifacts_keeps_its_three_lazy_imports_relative():
    tree = ast.parse((ENGINE / "j2_artifacts.py").read_text(encoding="utf-8"))
    lazy = [n for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) for n in ast.walk(f)
            if isinstance(n, (ast.Import, ast.ImportFrom))]
    relative = [n for n in lazy if isinstance(n, ast.ImportFrom) and n.level == 1]
    assert len(relative) >= 3


# ---- every module imports ----------------------------------------------------------------------------------------------
def test_every_vendored_module_imports_in_a_clean_process(tmp_path):
    code = ("import importlib, sys\n"
            "for n in sys.argv[1:]:\n    importlib.import_module('sutra_app.engine.' + n)\n"
            "print('imported', len(sys.argv) - 1)\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_"))}
    env.update(J2_RUNS_DIR=str(tmp_path / "runs"), J2_LIBRARY_DIR=str(tmp_path / "lib"), STUDIO_MOCK="1",
               PYTHONPATH=os.pathsep.join([str(REPO), *sys.path]))
    done = subprocess.run([sys.executable, "-c", code, *CODE, "rehydrate"], capture_output=True, text=True, env=env,
                          cwd=tmp_path, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"imported {len(CODE) + 1}"
    assert not (tmp_path / "runs").exists() and not (tmp_path / "lib").exists(), "an import writes nothing"


# ---- the data files -----------------------------------------------------------------------------------------------------
def test_the_data_files_are_all_there():
    assert {p.name for p in (ENGINE / "agents" / "j2").iterdir()} == ROLE_FILES
    assert {p.name for p in (ENGINE / "conditions").iterdir()} == {"hld.json", "lld.json", "prd.json", "website.json"}
    for generic in (ENGINE / "templates").glob("*/generic.json"):
        json.loads(generic.read_text(encoding="utf-8"))
    assert sorted(p.parent.name for p in (ENGINE / "templates").glob("*/generic.json")) == \
        ["design", "hld", "lld", "prd", "website"]
    types = json.loads((ENGINE / "artifacts" / "types.json").read_text(encoding="utf-8"))
    assert types, "artifacts/types.json is empty"
    seed = ENGINE / "seed" / "library"
    assert sum(1 for p in seed.rglob("*") if p.is_file()) == 105 and len(list(seed.rglob("meta.json"))) == 26


def test_the_reference_docs_are_copied():
    ref = REPO / "docs" / "reference" / "j2"
    for name in ("README.md", "SETUP.md", "docs/atom-schema.json", "docs/atom-schema.md", "docs/map-schema.md",
                 "docs/realization-schema.json", "docs/realization-axis.md", "docs/j2-handoff.md", "docs/j2-prompts.md",
                 "docs/j2-test-plan.md"):
        assert (ref / name).is_file(), name
    assert any((ref / "docs" / "superpowers").rglob("*.md"))


def test_the_manifest_carries_the_engine_data():
    text = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    for tree in ("agents", "conditions", "artifacts", "templates", "seed"):
        assert f"recursive-include sutra_app/engine/{tree} *" in text
    assert "include sutra_app/engine/VENDORED.md" in text


# ---- VENDORED.md ---------------------------------------------------------------------------------------------------------
def test_vendored_md_names_the_baseline_commit():
    head = MD.read_text(encoding="utf-8")
    assert "9200cf626e5c05032caefda4f96b694284efdc5e" in head and "33aeeda" in head and "ce2631f" in head


def test_every_recorded_vendored_hash_matches_the_file():
    for vendored, _, _, _, vendored_sha in rows():
        assert sha(REPO / vendored) == vendored_sha, vendored


def test_a_file_without_patches_is_a_byte_copy_and_a_patched_file_differs():
    for vendored, _, patches, j2_sha, vendored_sha in rows():
        assert (j2_sha == vendored_sha) == (patches == "-"), vendored


def test_every_vendored_file_is_listed_and_every_listed_file_exists():
    listed = {v for v, *_ in rows()}
    on_disk = {p.relative_to(REPO).as_posix() for tree in ("sutra_app/engine/agents", "sutra_app/engine/conditions",
                                                          "sutra_app/engine/artifacts", "sutra_app/engine/templates",
                                                          "sutra_app/engine/seed", "docs/reference/j2")
               for p in (REPO / tree).rglob("*") if p.is_file()}
    on_disk |= {f"sutra_app/engine/{n}.py" for n in CODE}
    assert on_disk == listed


def test_the_patch_table_has_p1_to_p13_without_p6():
    table = MD.read_text(encoding="utf-8").split("## Files")[0]
    ids = re.findall(r"^\| (P\d+) \|", table, re.M)
    assert ids == [f"P{n}" for n in range(1, 14) if n != 6]
    used = {p for _, _, patches, _, _ in rows() for p in patches.split(",") if p != "-"}
    assert used == set(ids)


def test_a_patch_listed_for_a_file_leaves_its_mark_in_it():
    marks = {"P3": ("j2.py", "run_dir=None"), "P4": ("j2.py", "def apply_override"), "P9": ("j2.py", "system_addendum"),
             "P10": ("j2_template_lib.py", "class LibraryBusy"), "P11": ("j2.py", "def rehydrate"),
             "P13": ("j2.py", "def run_list"),
             "P2": ("j2_realization.py", "J2_AGENTS_DIR")}
    by_file = {Path(v).name: patches.split(",") for v, _, patches, _, _ in rows() if v.endswith(".py")}
    for patch, (name, text) in marks.items():
        assert patch in by_file[name], (patch, name)
        assert text in (ENGINE / name).read_text(encoding="utf-8"), (patch, text)


def test_the_patch_line_ranges_point_at_real_lines():
    table = MD.read_text(encoding="utf-8").split("## Files")[0]
    for name, a, b in re.findall(r"(j2(?:_[a-z_]+)?\.py):(\d+)(?:-(\d+))?", table):
        lines = (ENGINE / name).read_text(encoding="utf-8").count("\n") + 1
        assert 1 <= int(a) <= (int(b) if b else int(a)) <= lines, (name, a, b)


@pytest.mark.skipif(not os.environ.get("SUTRA_J2_CHECKOUT"), reason="SUTRA_J2_CHECKOUT is not set (the J2 prototype is read-only)")
def test_the_tree_is_exactly_what_the_vendoring_script_derives_from_j2():
    done = subprocess.run([sys.executable, str(REPO / "scripts" / "vendor_j2.py"), "--check"], capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(REPO)}, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
