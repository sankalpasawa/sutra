"""test_org2_api.py -- the department read behind the new Org screen
(BUILD-PLAN.md step 36) on an isolated registry, and the guards around it.

Run: .venv/bin/python test_org2_api.py   (or pytest -q test_org2_api.py)
"""
import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def _fresh(tmp):
    """org2_api + engine bound to an isolated registry (the test_org_apply idiom)."""
    os.environ["SUTRA_NATIVE_HOME"] = str(tmp)
    for m in ("placement_engine", "org2_api"):
        sys.modules.pop(m, None)
    import org2_api
    import placement_engine as E
    importlib.reload(E)
    importlib.reload(org2_api)
    return org2_api, E


def _tree(E):
    """Root Co with the machine node Desktop, an organisation A and A's child A1."""
    root, _ = E.mint_domain(None, "Co", ["root"], "T-local", origin="test")
    desk, _ = E.mint_domain(root, "Desktop", ["desk"], "T-local", origin="test")
    a, _ = E.mint_domain(root, "A", ["a"], "T-local", origin="test")
    a1, _ = E.mint_domain(a, "A1", ["a1"], "T-local", origin="test")
    return root, desk, a, a1


def test_department_read_shape_and_names():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        out = M.department(a)
        assert out["ref"] == a and out["name"] == "A"
        assert out["kind"] == "organisation"
        assert out["address"] == ["Co", "A"], "the address is a chain of names"
        assert [c["name"] for c in out["children"]] == ["A1"]
        assert out["parent"] == {"ref": root, "name": "Co"}
        assert out["charter"] is None and out["charters"] == []
        assert out["filed"] == [] and out["filed_n"] == 0 and out["docs"] == []
        assert out["status"] == "active" and out["successors"] == []
        assert "/" not in "".join(out["address"]), "names, never paths"


def test_node_kinds_root_machine_organisation_department():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        assert M.department(root)["kind"] == "root"
        assert M.department(desk)["kind"] == "machine"
        assert M.department(a)["kind"] == "organisation"
        assert M.department(a1)["kind"] == "department"


def test_unknown_department_is_404():
    from fastapi import HTTPException
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        _tree(E)
        with pytest.raises(HTTPException) as ei:
            M.department("dref-does-not-exist")
        assert ei.value.status_code == 404


def test_unknown_charter_is_404():
    from fastapi import HTTPException
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        _tree(E)
        with pytest.raises(HTTPException) as ei:
            M.charter("C-0000000000000000")
        assert ei.value.status_code == 404


def test_labels_are_names_not_paths():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        assert M._label("holding/departments/experience/org/BUILD-PLAN.md") == "BUILD PLAN"
        assert M._label("sutra-ui/static/js/03-org.js") == "03 org"
        assert M._label("  a   chat   title  ") == "a chat title"
        long = "x" * 100
        out = M._label(long)
        assert len(out) <= M.LABEL_MAX and out.endswith("…")
        assert M._label("") == "" and M._label(None) == ""


def test_root_pick_prefers_the_largest_live_subtree():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        live = E.live_refs(E.load_domains())
        assert M._root_ref(live) == root


def test_forbidden_scan_covers_this_module():
    """The provable negative must include org2_api.py, or the guard scans nothing new."""
    import test_forbidden_calls as T
    names = [p.name for p in T.FILES_UNDER_TEST]
    assert "org2_api.py" in names
    text = (HERE / "org2_api.py").read_text(encoding="utf-8")
    aliases = T._engine_aliases(text)
    assert aliases, "org2_api.py must import placement_engine as an alias the scan can see"
    for name in T.FORBIDDEN_CALLS:
        assert not T._find_forbidden_calls(text, aliases, name), name


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
