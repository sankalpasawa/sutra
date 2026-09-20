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
    desk, _ = E.mint_domain(root, "Desktop", ["desk"], "T-local", origin="project-import")
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
        assert out["index_lines"] == len(E._read_jsonl(E.DOMAIN_INDEX)) and out["index_lines"] >= 4, "S52: history length rides the read"


def test_node_kinds_root_machine_organisation_department():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        assert M.department(root)["kind"] == "root"
        assert M.department(desk)["kind"] == "machine"
        assert M.department(a)["kind"] == "organisation"
        assert M.department(a1)["kind"] == "department"


def test_node_kind_is_stored_at_mint_backfilled_once_and_preferred():
    """BUILD-PLAN S94: the engine stores node_kind; the read prefers it; a move
    to or from under the root re-kinds; the backfill fills only what is missing."""
    import json
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        rows = E.load_domains()
        assert [rows[r]["node_kind"] for r in (root, desk, a, a1)] == ["root", "machine", "organisation", "department"]
        # a caller may name the kind; an unknown value falls back to the rule
        x, _ = E.mint_domain(a, "Named", ["x"], "T-local", origin="test", node_kind="machine")
        y, _ = E.mint_domain(a, "Odd", ["y"], "T-local", origin="test", node_kind="planet")
        assert E.load_domains()[x]["node_kind"] == "machine" and E.load_domains()[y]["node_kind"] == "department"
        # the read prefers the stored field even where the interim rule disagrees
        E.set_domain_fields(desk, node_kind="organisation")
        assert M.department(desk)["kind"] == "organisation"
        E.set_domain_fields(desk, node_kind="machine")
        # a move under the root makes a department an organisation, and back
        E.restructure("move", a1, target=root)
        assert E.load_domains()[a1]["node_kind"] == "organisation"
        E.restructure("move", a1, target=a)
        assert E.load_domains()[a1]["node_kind"] == "department"
        # rows minted before the field existed: strip it, backfill, once
        p = Path(tmp) / "domains" / (a + ".json")
        if not p.exists():
            p = next(Path(tmp).rglob(a + ".json"))
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc.pop("node_kind", None)
        p.write_text(json.dumps(doc, sort_keys=True, indent=2), encoding="utf-8")
        assert "node_kind" not in E.load_domains()[a]
        assert M.department(a)["kind"] == "organisation", "the interim rule still answers meanwhile"
        assert E.backfill_node_kind(dry_run=True) == {"missing": 1, "written": 0}
        assert E.backfill_node_kind() == {"missing": 1, "written": 1}
        assert E.load_domains()[a]["node_kind"] == "organisation"
        assert E.backfill_node_kind() == {"missing": 0, "written": 0}
        events = [r for r in E._read_jsonl(E.DOMAIN_INDEX) if r.get("event") == "node_kind_backfilled"]
        assert len(events) == 1 and events[0]["count"] == 1, "one summary event, not one per row"
        assert M.filter_departments(kind="organisation")["refs"] == [a]


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


def test_filter_by_kind_state_and_subtree():
    from fastapi import HTTPException
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        assert M.filter_departments(kind="organisation")["refs"] == [a]
        assert set(M.filter_departments(kind="machine,department")["refs"]) == {desk, a1}
        assert set(M.filter_departments(state="no-charter")["refs"]) == {root, desk, a, a1}, "no charters minted yet"
        assert set(M.filter_departments(where=a)["refs"]) == {a, a1}
        assert set(M.filter_departments(kind="department", where=a)["refs"]) == {a1}
        assert set(M.filter_departments()["refs"]) == {root, desk, a, a1}, "empty query matches everything"
        with pytest.raises(HTTPException) as ei:
            M.filter_departments(kind="planet")
        assert ei.value.status_code == 400


def test_search_names_and_short_queries():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        assert M.search("a1")["refs"] == [a1]
        assert M.search("desk")["refs"] == [desk]
        assert M.search("x")["refs"] == [], "one character is not a search"
        assert M.search("nothing-here")["refs"] == []


def test_health_lists_unowned_names():
    from fastapi import HTTPException
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        out = M.health(a)
        assert out["name"] == "A" and out["checked"] == 2
        assert [u["name"] for u in out["unowned"]] == ["A", "A1"]
        assert out["one_line"] == [] and isinstance(out["overlaps"], list)
        with pytest.raises(HTTPException) as ei:
            M.health("dref-none")
        assert ei.value.status_code == 404


def test_request_files_a_proposal_and_refuses_bad_shapes():
    from fastapi import HTTPException
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SUTRA_UI_PROPOSALS"] = os.path.join(tmp, "props")
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        import proposals
        out = M.request(M.RequestBody(kind="org.rename", args={"ref": a, "name": " B  C "}))
        assert out["summary"] == "Rename A to B C"
        rec = out["proposal"]
        assert rec["status"] == "pending" and rec["kind"] == "org.rename" and rec["args"] == {"ref": a, "name": " B  C "}
        assert proposals.get(rec["id"])["summary"] == "Rename A to B C"
        out = M.request(M.RequestBody(kind="org.create", args={"parent": a, "name": "New"}))
        assert out["summary"] == "New department New under A"
        out = M.request(M.RequestBody(kind="org.move", args={"ref": a1, "target": root}))
        assert out["summary"] == "Move A1 under Co"
        out = M.request(M.RequestBody(kind="org.charter", args={"ref": a, "purpose": "Everything under A."}))
        assert out["summary"] == "Write the goal and rules of A"
        other = E.mint_charter_stub(a1, "A1 Charter", "A1 work.", [], [], "T-local")
        for body, code in ((M.RequestBody(kind="org.charter", args={"ref": a}), 400),
                           (M.RequestBody(kind="org.charter", args={"ref": a, "purpose": "x", "charter_id": other}), 400),
                           (M.RequestBody(kind="org.charter", args={"ref": a, "purpose": "x", "charter_id": "C-0000000000000000"}), 404)):
            with pytest.raises(HTTPException) as ei:
                M.request(body)
            assert ei.value.status_code == code
        for body, code in ((M.RequestBody(kind="org.delete", args={"ref": a}), 400),
                           (M.RequestBody(kind="org.rename", args={"ref": a}), 400),
                           (M.RequestBody(kind="org.rename", args={"ref": a, "name": " desktop "}), 400),   # a sibling's name
                           (M.RequestBody(kind="org.create", args={"parent": root, "name": "A"}), 400),      # a child's name
                           (M.RequestBody(kind="org.rename", args={"ref": "dref-none", "name": "X"}), 404),
                           (M.RequestBody(kind="org.move", args={"ref": a, "target": a1}), 400),
                           (M.RequestBody(kind="org.move", args={"ref": a1, "target": a}), 400)):
            with pytest.raises(HTTPException) as ei:
                M.request(body)
            assert ei.value.status_code == code, body.kind
        assert len(proposals.pending()) == 4, "refusals file nothing"


def test_request_summaries_are_screen_words_and_never_say_charter():
    """B1: the request writer is the one place a summary's words are chosen, and
    the department screen paints that summary verbatim (PRD A29). Every summary
    the composer can produce is checked here -- the five shapes and the two edit
    variants -- so a template that ever carries the word again fails at the
    writer rather than on a card."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SUTRA_UI_PROPOSALS"] = os.path.join(tmp, "props")
        M, E = _fresh(Path(tmp))
        root, desk, a, a1 = _tree(E)
        import proposals
        cid = E.mint_charter_stub(a, "A Charter", "A work.", [], [], "T-local")
        said = [
            M.request(M.RequestBody(kind="org.rename", args={"ref": a1, "name": "B"}))["summary"],
            M.request(M.RequestBody(kind="org.move", args={"ref": a1, "target": root}))["summary"],
            M.request(M.RequestBody(kind="org.create", args={"parent": a, "name": "New"}))["summary"],
            M.request(M.RequestBody(kind="org.charter", args={"ref": a, "purpose": "All of A."}))["summary"],
            M.request(M.RequestBody(kind="org.charter",
                                    args={"ref": a, "purpose": "All of A.", "charter_id": cid}))["summary"],
            M.request(M.RequestBody(kind="org.charter",
                                    args={"ref": a, "purpose": "Run A.", "kind": "role",
                                          "person": " Sankalp  Asawa "}))["summary"],
            M.request(M.RequestBody(kind="org.charter",
                                    args={"ref": a, "purpose": "Run A.", "kind": "role"}))["summary"],
            M.request(M.RequestBody(kind="org.charter",
                                    args={"ref": a, "purpose": "Run A.", "kind": "role",
                                          "person": "Sankalp Asawa", "charter_id": cid}))["summary"],
        ]
        assert said == [
            "Rename A1 to B",
            "Move A1 under Co",
            "New department New under A",
            "Write the goal and rules of A",
            "Edit the goal and rules of A",
            "New role under A for Sankalp Asawa",
            "New role under A for nobody yet",
            "Edit the role under A for Sankalp Asawa",
        ]
        assert set(M.REQUEST_SUMMARIES) == {"rename", "move", "create", "role", "role.edit",
                                            "goal", "goal.edit"}, "every template above is walked"
        for s in said + list(M.REQUEST_SUMMARIES.values()):
            assert "charter" not in s.lower(), s
        # the record carries the very words the approver was shown
        assert sorted(r["summary"] for r in proposals.pending()) == sorted(said)


def test_apply_charter_writes_then_amends_by_succession():
    """D-O3: an edit mints a successor body; the old one stays, superseded;
    filed work follows the amended charter; the department read shows the new one."""
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        sys.modules.pop("org2_apply", None)
        sys.modules.pop("org_apply", None)
        import org2_apply
        root, desk, a, a1 = _tree(E)
        assert M.department(a)["charter"] is None
        with pytest.raises(ValueError):
            org2_apply.apply_request("org.charter", {"ref": a, "purpose": "  "})
        out = org2_apply.apply_request("org.charter", {"ref": a, "purpose": "Everything under A."})
        first = out["charter_id"]
        assert out["supersedes"] is None and first.startswith("C-")
        dep = M.department(a)
        assert dep["charter"]["id"] == first and dep["charter"]["title"] == "A Charter" and dep["charter"]["purpose"] == "Everything under A."
        # work filed under the first charter
        E.write_placement({"kind": "task", "id": "task-1"}, a, first, "matched", 0.9, {"domains": [], "charters": []}, "T-local")
        assert [p["charter_id"] for p in M._filed(a)] == [first]
        with pytest.raises(ValueError, match="nothing changed"):
            org2_apply.apply_request("org.charter", {"ref": a, "charter_id": first, "title": "A Charter", "purpose": "Everything under A."})
        out = org2_apply.apply_request("org.charter", {"ref": a, "charter_id": first, "title": "A, the organisation",
                                                       "purpose": "Everything under A, and its books."})
        second = out["charter_id"]
        assert second != first and out["supersedes"] == first and out["repointed"] == 1
        assert E.superseded_ids().get(first) == second, "supersession is derived from the new body"
        assert E.load_charter(first)["purpose"] == "Everything under A.", "the old body is untouched"
        assert E.load_sidecar(first).get("lifecycle") == "superseded"
        dep = M.department(a)
        assert dep["charter"]["id"] == second and dep["charter"]["title"] == "A, the organisation"
        assert [c["id"] for c in dep["charters"]] == [first], "the old charter lists under Other charters"
        assert [p["charter_id"] for p in M._filed(a)] == [second], "filed work follows the amendment"
        with pytest.raises(ValueError, match="already amended"):
            org2_apply.apply_request("org.charter", {"ref": a, "charter_id": first, "purpose": "again"})
        with pytest.raises(ValueError, match="another department"):
            org2_apply.apply_request("org.charter", {"ref": a1, "charter_id": second, "purpose": "steal"})
        events = [r.get("event") for r in E._read_jsonl(E.CHARTER_INDEX)]
        assert events.count("charter_written") == 1 and events.count("charter_amended") == 1


def test_apply_request_rename_create_move_registry_only():
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        sys.modules.pop("org2_apply", None)
        sys.modules.pop("org_apply", None)
        import org2_apply
        root, desk, a, a1 = _tree(E)
        out = org2_apply.apply_request("org.rename", {"ref": a, "name": "  Alpha "})
        assert out["name_before"] == "A" and out["name_after"] == "Alpha"
        assert E.load_domains()[a]["name"] == "Alpha"
        with pytest.raises(ValueError):
            org2_apply.apply_request("org.rename", {"ref": a, "name": "Alpha"})
        with pytest.raises(ValueError):
            org2_apply.apply_request("org.rename", {"ref": a, "name": ""})
        with pytest.raises(ValueError, match="already has a department named"):
            org2_apply.apply_request("org.rename", {"ref": a, "name": "DESKTOP"})   # a live sibling's name
        out = org2_apply.apply_request("org.create", {"parent": a, "name": "A2"})
        assert out["created"] is True and E.load_domains()[out["ref"]]["parent_ref"] == a
        with pytest.raises(ValueError):
            org2_apply.apply_request("org.create", {"parent": a, "name": "a2"})
        out = org2_apply.apply_request("org.move", {"ref": a1, "target": root})
        assert out["applied"] is True and E.load_domains()[a1]["parent_ref"] == root
        with pytest.raises(ValueError):
            org2_apply.apply_request("org.delete", {"ref": a})
        assert set(proposal_kinds()) >= {"org.rename", "org.move", "org.create"}


def proposal_kinds():
    import proposals
    return proposals.KINDS


def test_page_wraps_a_workdir_html_under_the_tokens():
    import types
    from fastapi import HTTPException
    with tempfile.TemporaryDirectory() as tmp:
        M, E = _fresh(Path(tmp))
        wd = Path(tmp) / "wd"
        wd.mkdir()
        (wd / "org.html").write_text("<h1>Org</h1>", encoding="utf-8")

        def _resolve(rel):
            target = os.path.realpath(os.path.join(str(wd), rel))
            if not target.startswith(str(wd.resolve()) + os.sep):
                raise HTTPException(status_code=400, detail="escapes")
            return str(wd.resolve()), target
        saved = {k: sys.modules.get(k) for k in ("org_api", "modules_api")}
        sys.modules["org_api"] = types.SimpleNamespace(_fs_resolve=_resolve, FS_MAX_READ=1_000_000)
        sys.modules["modules_api"] = types.SimpleNamespace(TOKEN_CSS=":root{--ink:#000}", PAGE_CSP="default-src 'none'")
        try:
            html = M._page_html("org.html", "dark")
            assert html.startswith('<meta charset="utf-8">') and 'id="sutra-tokens"' in html
            assert 'setAttribute("data-theme","dark")' in html and html.endswith("<h1>Org</h1>")
            assert "data-theme" not in M._page_html("org.html", "pink"), "an unknown theme stamps nothing"
            for rel, code in (("notes.md", 400), ("missing.html", 404), ("../x.html", 400)):
                with pytest.raises(HTTPException) as ei:
                    M._page_html(rel, "")
                assert ei.value.status_code == code, rel
            resp = M.page("org.html", "light")
            assert resp.headers["content-security-policy"] == "default-src 'none'"
            assert resp.headers["cache-control"].startswith("no-store")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v


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
