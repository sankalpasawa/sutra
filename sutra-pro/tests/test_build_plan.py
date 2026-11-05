"""The build plan keeps its promises: one owner per path, known dependencies, no cycles."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("plan_tools", ROOT / "scripts" / "plan_tools.py")
plan_tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_tools)


def _wp(i, owns=None, deps=(), **kw):
    base = {"id": i, "title": i, "section": "library", "owns": owns or [f"sutra_app/{i.lower()}.py", f"docs/notes/{i}.md"],
            "depends_on": list(deps), "acceptance": ["scripts/py -m pytest -q"]}
    base.update(kw)
    return base


def test_clean_plan_has_no_problems():
    plan = {"work_packages": [_wp("A"), _wp("B", deps=["A"])]}
    assert plan_tools.validate(plan) == []
    assert plan_tools.waves(plan) == [["A"], ["B"]]


def test_overlapping_ownership_is_refused():
    plan = {"work_packages": [_wp("A", owns=["sutra_app/x.py", "docs/notes/A.md"]), _wp("B", owns=["sutra_app/x.py", "docs/notes/B.md"])]}
    assert any("owned by both" in p for p in plan_tools.validate(plan))


def test_directory_owner_conflicts_with_a_file_beneath_it():
    plan = {"work_packages": [_wp("A", owns=["sutra_app/engine/", "docs/notes/A.md"]), _wp("B", owns=["sutra_app/engine/x.py", "docs/notes/B.md"])]}
    assert any("contains" in p for p in plan_tools.validate(plan))


def test_unknown_dependency_cycle_and_protected_file_are_refused():
    assert any("unknown" in p for p in plan_tools.validate({"work_packages": [_wp("A", deps=["Z"])]}))
    cyc = {"work_packages": [_wp("A", deps=["B"]), _wp("B", deps=["A"])]}
    assert any("cycle" in p for p in plan_tools.validate(cyc))
    prot = {"work_packages": [_wp("A", owns=["pyproject.toml", "docs/notes/A.md"])]}
    assert any("protected" in p for p in plan_tools.validate(prot))


def test_every_package_owns_its_notes_file():
    plan = {"work_packages": [_wp("A", owns=["sutra_app/a.py"])]}
    assert any("docs/notes/A.md" in p for p in plan_tools.validate(plan))


def test_committed_plan_is_valid():
    path = ROOT / "docs" / "build-plan.json"
    if not path.exists():
        pytest.skip("docs/build-plan.json is not written yet")
    plan = json.loads(path.read_text())
    assert plan_tools.validate(plan) == []
