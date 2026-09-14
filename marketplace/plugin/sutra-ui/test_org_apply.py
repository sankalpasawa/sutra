"""test_org_apply.py -- drag-and-drop apply edits linkages and NOTHING else.

The founder's constraint (2026-09-13): "drag and drop should only edit the
linkages inside Sutra; nothing outside Sutra will change." These tests pin the
three ways that could be violated -- a non-move op slipping through, a move
writing outside the registry, or an invalid/stale plan being committed -- plus
that a real move actually re-parents.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest


def _fresh(tmp):
    """org_apply + engine bound to an isolated registry."""
    import importlib
    import sys
    os.environ["SUTRA_NATIVE_HOME"] = str(tmp)
    for m in ("placement_engine", "reorg_sim", "org_apply"):
        if m in sys.modules:
            del sys.modules[m]
    # org_apply inserts ../lib on sys.path at import, so it must come first --
    # importing placement_engine before that path insert is the ModuleNotFound.
    import org_apply
    import placement_engine as E
    importlib.reload(E)
    importlib.reload(org_apply)
    return org_apply, E


def _tree(E):
    """Root with two branches: A (child A1) and B. Returns the refs."""
    root, _ = E.mint_domain(None, "Co", ["root"], "T-local", origin="test")
    a, _ = E.mint_domain(root, "A", ["a"], "T-local", origin="test")
    b, _ = E.mint_domain(root, "B", ["b"], "T-local", origin="test")
    a1, _ = E.mint_domain(a, "A1", ["a1"], "T-local", origin="test")
    return root, a, b, a1


def test_a_move_reparents_the_department():
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh(Path(tmp))
        root, a, b, a1 = _tree(E)
        assert E.load_domains()[a1]["parent_ref"] == a
        out = P.apply_moves([{"op": "move", "ref": a1, "target": b}])
        assert out["applied"] and out["count"] == 1
        assert E.load_domains()[a1]["parent_ref"] == b, "A1 now hangs off B"
        assert out["moves"][0] == {"ref": a1, "target": b,
                                   "parent_before": a, "parent_after": b}


def test_a_non_move_op_is_refused_before_the_registry_is_touched():
    """The structural guarantee. rename/delete/retire never reach the engine."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh(Path(tmp))
        root, a, b, a1 = _tree(E)
        # Each carries a VALID ref+target so only the op-TYPE guard can reject
        # it -- otherwise the missing-target check would mask a removed op guard
        # (a mutation test caught exactly that).
        for bad in ({"op": "rename", "ref": a, "target": b},
                    {"op": "delete", "ref": a, "target": b},
                    {"op": "retire", "ref": a, "target": b},
                    {"op": "merge", "ref": a, "target": b},
                    {"op": "move"}):                       # and the missing-field case
            with pytest.raises(ValueError):
                P.apply_moves([bad])
            assert E.load_domains()[a]["parent_ref"] == root, "%r changed the tree" % bad
        # a good move in the SAME batch as a bad op applies nothing
        with pytest.raises(ValueError):
            P.apply_moves([{"op": "move", "ref": a1, "target": b},
                           {"op": "rename", "ref": a, "name": "X"}])
        assert E.load_domains()[a1]["parent_ref"] == a, "the good move did not sneak through"


def test_apply_writes_ONLY_under_the_registry_root(tmp_path):
    """The literal 'nothing outside Sutra' check: snapshot the filesystem
    outside SUTRA_NATIVE_HOME before and after a move; it must be byte-identical.
    A sentinel 'project directory' and 'transcript' stand in for the real
    ~/.claude and repos the founder does not want touched."""
    reg = tmp_path / "registry"
    outside = tmp_path / "outside"
    (outside / "project").mkdir(parents=True)
    (outside / "project" / "file.py").write_text("print('hi')\n")
    (outside / "transcript.jsonl").write_text('{"cwd":"/x"}\n')

    def snapshot():
        return {p.relative_to(outside).as_posix(): p.read_bytes()
                for p in outside.rglob("*") if p.is_file()}

    P, E = _fresh(reg)
    root, a, b, a1 = _tree(E)
    before = snapshot()
    P.apply_moves([{"op": "move", "ref": a1, "target": b}])
    assert snapshot() == before, "a move changed something outside the registry"


def test_a_cycle_is_refused_and_nothing_is_written():
    """Moving A under its own descendant A1 would orphan the subtree. simulate
    blocks it (ORG-006), and restructure would too; either way, no write."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh(Path(tmp))
        root, a, b, a1 = _tree(E)
        with pytest.raises(P.ApplyRefused) as ei:
            P.apply_moves([{"op": "move", "ref": a, "target": a1}])
        assert any("ORG-006" in b for b in ei.value.blocks and
                   [f.get("code", "") for f in ei.value.blocks]) or ei.value.blocks
        assert E.load_domains()[a]["parent_ref"] == root, "A stayed where it was"


def test_a_drifted_plan_is_refused():
    """base captures the tree the operator dragged on; if it moved since, ORG-010
    blocks apply rather than writing onto a tree they were not looking at."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh(Path(tmp))
        root, a, b, a1 = _tree(E)
        stale_base = {"domain_index_lines": 0}   # tree has more rows than this
        with pytest.raises(P.ApplyRefused):
            P.apply_moves([{"op": "move", "ref": a1, "target": b}], base=stale_base)
        assert E.load_domains()[a1]["parent_ref"] == a


def test_validate_does_not_write():
    """validate() is the dry run the endpoint could call alone; it must never
    mutate."""
    with tempfile.TemporaryDirectory() as tmp:
        P, E = _fresh(Path(tmp))
        root, a, b, a1 = _tree(E)
        P.validate([{"op": "move", "ref": a1, "target": b}])
        assert E.load_domains()[a1]["parent_ref"] == a, "validate wrote a change"


def test_apply_is_registry_only_by_construction():
    """Source guard: org_apply must call NO mutator other than restructure, and
    restructure only for 'move'. A future edit that reaches rename/delete/retire
    would silently widen the blast radius past the founder's constraint."""
    import ast
    import inspect
    import org_apply
    tree = ast.parse(inspect.getsource(org_apply))
    engine_calls = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "E":
            engine_calls.add(n.func.attr)
    mutators = {"mint_domain", "restructure", "retire", "unretire", "resolve",
                "consolidate", "reconcile", "repair", "set_domain_fields"}
    used = engine_calls & mutators
    assert used == {"restructure"}, \
        "org_apply may mutate the registry ONLY via restructure(move); found %s" % used
    # and every restructure call passes the literal "move"
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "restructure":
            first = n.args[0] if n.args else None
            assert isinstance(first, ast.Constant) and first.value == "move", \
                "restructure is called with something other than the literal 'move'"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
