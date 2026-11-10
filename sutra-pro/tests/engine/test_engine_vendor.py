"""The vendored J2 tree (work package E1, engine design 3.1, 3.4 and decision D13): package-relative imports (P1), every
module imports, the data files are there, and VENDORED.md tells the truth about every file (commit, hashes, patch ids).
Nothing here reads the J2 prototype except the one test that needs `SUTRA_J2_CHECKOUT`, an extraction of this repository's
`prototypes/j2` (it skips without it)."""
import ast
import hashlib
import importlib.util
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
SEED_INDEX = ENGINE / "seed" / "library" / "index.json"
PIN = "00efb179e21cb79fae157a0679e819921ac37726"          # sync 4 (D136): the sutra commit that last touched prototypes/j2
PIN_TREE = "99b6f3a05de78a609b593d81d7fb06b55c32b961"     # `git rev-parse <PIN>:prototypes/j2`
CODE = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
        "j2_check", "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_template_lib")
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
    assert sum(1 for p in seed.rglob("*") if p.is_file()) == 157 and len(list(seed.rglob("meta.json"))) == 39


def test_the_reference_docs_are_copied():
    ref = REPO / "docs" / "reference" / "j2"
    for name in ("README.md", "SETUP.md", "docs/atom-schema.json", "docs/atom-schema.md", "docs/map-schema.md",
                 "docs/realization-schema.json", "docs/realization-axis.md", "docs/j2-handoff.md", "docs/j2-prompts.md",
                 "docs/j2-test-plan.md", "docs/agent-views-j2-proposal.md"):
        assert (ref / name).is_file(), name
    assert any((ref / "docs" / "superpowers").rglob("*.md"))


def test_the_manifest_carries_the_engine_data():
    text = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    for tree in ("agents", "conditions", "artifacts", "templates", "seed"):
        assert f"recursive-include sutra_app/engine/{tree} *" in text
    assert "include sutra_app/engine/VENDORED.md" in text


# ---- VENDORED.md ---------------------------------------------------------------------------------------------------------
def test_vendored_md_names_the_pinned_commit_the_tree_and_the_extraction_recipe():
    """D136: the one source is prototypes/j2 of this repository at a sutra commit and tree id, extracted with git archive."""
    head = MD.read_text(encoding="utf-8").split("## Patches")[0]
    assert f"at the sutra commit `{PIN}` (tree of `prototypes/j2`: `{PIN_TREE}`)" in head
    assert f"`git archive {PIN} prototypes/j2 | tar -x --strip-components=2 -C <empty folder>`" in head
    assert "the only source of every file below" in head
    assert f"--source <the extraction> --commit {PIN} --check" in head


def test_the_older_commit_ids_in_the_header_are_history_and_never_a_source():
    head = MD.read_text(encoding="utf-8").split("## Patches")[0]
    history = head.split("History, not a source:")[1].split("Patches are located")[0]
    assert "`9200cf6`" in history and "`33aeeda`" in history and "`ce2631f`" in history
    assert not any(old in head.split("History, not a source:")[0] for old in ("9200cf6", "33aeeda", "ce2631f"))


def test_the_vendoring_script_pins_the_same_commit_and_tree_as_the_header():
    spec = importlib.util.spec_from_file_location("vendor_j2_under_test", REPO / "scripts" / "vendor_j2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.BASELINE, module.BASELINE_TREE) == (PIN, PIN_TREE)
    assert len(module.CODE) == 16 and tuple(Path(n).stem for n in module.CODE) == CODE


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


def test_the_patch_table_has_p1_to_p15_without_p6_and_p13():
    """P6 never existed; P13 (the run list and the change list) was retired into engine/runlist.py in sync 4 (D140)."""
    table = MD.read_text(encoding="utf-8").split("## Files")[0]
    ids = re.findall(r"^\| (P\d+) \|", table, re.M)
    assert ids == [f"P{n}" for n in range(1, 16) if n not in (6, 13)]
    used = {p for _, _, patches, _, _ in rows() for p in patches.split(",") if p != "-"}
    assert used == set(ids)


def test_a_patch_listed_for_a_file_leaves_its_mark_in_it():
    marks = {"P3": ("j2.py", "run_dir=None"), "P4": ("j2.py", "def apply_override"), "P9": ("j2.py", "system_addendum"),
             "P10": ("j2_template_lib.py", "class LibraryBusy"), "P11": ("j2.py", "def rehydrate"),
             "P14": ("j2.py", 'self.out.get("single")'),
             "P2": ("j2_realization.py", "J2_AGENTS_DIR")}
    by_file = {Path(v).name: patches.split(",") for v, _, patches, _, _ in rows() if v.endswith(".py")}
    for patch, (name, text) in marks.items():
        assert patch in by_file[name], (patch, name)
        assert text in (ENGINE / name).read_text(encoding="utf-8"), (patch, text)


def test_p13_left_nothing_behind_in_the_vendored_j2():
    """The run list and the change list are Sutra's own code now (engine/runlist.py); the vendored j2.py has neither."""
    j2_text = (ENGINE / "j2.py").read_text(encoding="utf-8")
    assert "def run_list" not in j2_text and "def run_changes" not in j2_text and "def run_row" not in j2_text
    assert "P13" not in j2_text and (ENGINE / "runlist.py").is_file()


def test_p1_j2_agent_views_has_no_sys_path_insert_and_imports_its_three_siblings_relative():
    tree = ast.parse((ENGINE / "j2_agent_views.py").read_text(encoding="utf-8"))
    relative = sorted(n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 1)
    assert relative == ["j2_agent_models", "j2_artifact_models", "j2_template_lib"]
    assert "sys.path" not in (ENGINE / "j2_agent_views.py").read_text(encoding="utf-8")


HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+")        # a pattern, never a path (R5)


def test_p15_no_file_of_the_seed_holds_an_absolute_home_folder_path():
    found = {p.relative_to(ENGINE).as_posix() for p in (ENGINE / "seed").rglob("*") if p.is_file()
             and HOME_PATH.search(p.read_text(encoding="utf-8", errors="replace"))}
    assert found == set()


def test_p15_the_six_home_paths_of_the_seed_index_read_not_recorded_and_the_two_tmp_values_stay():
    index = json.loads(SEED_INDEX.read_text(encoding="utf-8"))
    libraries = [r["library"] for r in index["runs"].values()]          # `runs` is keyed by run id
    assert len(libraries) == 8 and libraries.count("not recorded") == 6
    assert sorted(x for x in libraries if x != "not recorded") == ["/tmp/j2-live-library", "/tmp/j2-live-library-2"]


def test_p15_is_the_only_patch_of_a_seed_file_and_the_table_names_its_lines():
    seed = [(v, patches) for v, _, patches, _, _ in rows() if v.startswith("sutra_app/engine/seed/")]
    assert [v for v, patches in seed if patches != "-"] == ["sutra_app/engine/seed/library/index.json"]
    assert [patches for v, patches in seed if patches != "-"] == ["P15"]
    table = MD.read_text(encoding="utf-8").split("## Files")[0]
    row = next(line for line in table.splitlines() if line.startswith("| P15 |"))
    lines = re.findall(r"seed/library/index.json:(\d+)", row)
    assert len(lines) == 6
    text = SEED_INDEX.read_text(encoding="utf-8").splitlines()
    assert all('"library": "not recorded"' in text[int(n) - 1] for n in lines)


def test_the_seed_holds_what_sync_4_counts():
    """32 templates and 39 versions (26 of them mock) and 8 development runs: 6 templates and 13 versions are new in sync 4."""
    index = json.loads(SEED_INDEX.read_text(encoding="utf-8"))
    versions = sum(len(t["versions"]) for t in index["templates"])
    assert (len(index["templates"]), versions, len(index["runs"])) == (32, 39, 8)
    assert sorted(r["mock"] for r in index["runs"].values()) == [False, False] + [True] * 6
    assert sum(1 for t in index["templates"] for v in t["versions"] if v.get("mock") is True) == 26


def test_the_patch_line_ranges_point_at_real_lines():
    table = MD.read_text(encoding="utf-8").split("## Files")[0]
    for name, a, b in re.findall(r"(j2(?:_[a-z_]+)?\.py):(\d+)(?:-(\d+))?", table):
        lines = (ENGINE / name).read_text(encoding="utf-8").count("\n") + 1
        assert 1 <= int(a) <= (int(b) if b else int(a)) <= lines, (name, a, b)


@pytest.mark.skipif(not os.environ.get("SUTRA_J2_CHECKOUT"),
                    reason="SUTRA_J2_CHECKOUT is not set (an extraction of prototypes/j2 at the pinned commit)")
def test_the_tree_is_exactly_what_the_vendoring_script_derives_from_the_extraction():
    done = subprocess.run([sys.executable, str(REPO / "scripts" / "vendor_j2.py"), "--commit", PIN, "--check"], capture_output=True,
                          text=True, env={**os.environ, "PYTHONPATH": str(REPO)}, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "207 files, ok" in done.stdout
