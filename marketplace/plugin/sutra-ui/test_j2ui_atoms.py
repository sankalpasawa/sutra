"""test_j2ui_atoms.py -- a work atom for each slot step, and atoms_v1 (j2ui_atoms.py; UI port, package j2ui-work).

Named claims:
  W3b an atom's words are the same words as the call log's: a decision's bare answer is the act in the owner's words
  W3  one atom for each slot step of an engine (a gate or a rule is a decision, not an atom), in order, W-1.a1 on, with every
      key the page's atom card reads; its check is a sentence in the owner's words, the check's id only in `target`; a result's
      attempt is the run of the engine its row is of, so a step that works on each page in turn has one attempt and several
      results; the atom's `attempts`, which the page prints as 'attempt N of 3', is the tries in the latest run (the most rows
      the step has for one item) and no more than the engine's retry bound, so a first-try pass reads 'attempt 1 of 3' in every
      request, however many requests the department has had; a step that has not run has no status, no notes and no output;
      atoms_v1 is the prototype's own run_views of these atoms (the equality proof, against the pinned prototype's j2_schema.py),
      and without the vendored file there is none

The helpers (the stand-in Ctx, the record's writers) are test_j2ui_work.py's.
"""
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

import j2ui_atoms as A
import j2ui_work as K
from test_j2ui_work import (BANNED, CHECK_ID, LINE, PINNED, REF, ago, born, mods, page_state, post, proto_file, render, run, shown,  # noqa: F401
                            standin, step_row, walk)

UI = Path(__file__).resolve().parent
ATOM_KEYS = ("id", "goal", "constraints", "context", "how", "expected_output", "verification", "results", "attempts", "status",
             "human_output", "agent_output")                  # what atomBlocks reads
VIEW_KEYS = ["schema", "id", "workflow", "name", "owner", "status", "attempt", "goal", "how", "constraints", "context",
             "defined_output", "verification", "output", "depends_on", "used_by", "notes", "details"]


def proto_text():
    return proto_file("j2_schema.py")


def proto_schema():
    """The pinned prototype's j2_schema as a module. test_fixtures/j2ui/proto.py (package j2ui-core) loads it, once that is merged
    and it can read the prototype (J2_PROTOTYPE); otherwise it is built from the git object proto_text() reads."""
    helper = UI / "test_fixtures" / "j2ui" / "proto.py"
    if helper.exists():
        spec = importlib.util.spec_from_file_location("j2ui_proto", str(helper))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if mod.skip_reason() is None:
            return mod.load("j2_schema")
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("j2_schema_pinned", loader=None))
    exec(compile(proto_text(), "j2_schema.py@" + PINNED[:7], "exec"), mod.__dict__)
    return mod


def atoms_of(mods, name, **kw):
    ctx = standin(mods, **kw)
    got = K.build(ctx)
    return next(w for w in got["workflows"] if w["name"] == name)["atoms"], ctx


# ---- W3: the atoms --------------------------------------------------------------------------------------------------
def test_w3_one_atom_for_each_slot_step_in_order_and_ids_w_k_a_j(mods):
    counts = {}
    for name in LINE:
        atoms, ctx = atoms_of(mods, name)
        counts[name] = [a["id"] for a in atoms]
    assert counts["Plan"] == ["W-1.a1", "W-1.a2", "W-1.a3", "W-1.a4"]
    assert counts["Write"] == ["W-2.a1", "W-2.a2", "W-2.a3"]
    assert counts["Check"] == ["W-3.a1", "W-3.a2", "W-3.a3"]
    assert counts["Publish"] == ["W-4.a1"]


def test_w3_a_gate_and_a_rule_are_decisions_not_atoms(mods):
    atoms, ctx = atoms_of(mods, "Plan")
    e = next(x for x in ctx.engines if x["name"] == "Plan")
    e["steps_view"]["steps"].insert(1, {"id": "plan.gate", "name": "Is there room", "mode": "gate", "soft": False, "check": "has_room"})
    e["steps_view"]["steps"].insert(0, {"id": "plan.rule", "name": "Hold the chain", "mode": "rule", "soft": False, "check": "chain_free"})
    ids = [a["goal"] for a in A.legacy_atoms(ctx, e)]
    assert ids == ["Read the brief", "Propose the pages", "Fit the page list", "File the plan"]


def test_w3_every_atom_carries_the_keys_the_card_reads(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", notes=["the brief has words"], read=[{"art": "Brief", "v": 1}])
    for name in LINE:
        atoms, ctx = atoms_of(mods, name)
        for a in atoms:
            assert set(ATOM_KEYS) - {"status", "human_output", "agent_output"} <= set(a), (a["id"], set(a))
            assert isinstance(a["constraints"], list) and isinstance(a["context"], list)
            assert isinstance(a["how"], dict) and {"kind", "agent", "steps"} == set(a["how"])
            assert a["expected_output"][0].keys() == {"text", "kind", "met"} and a["expected_output"][0]["kind"] == "check"
            assert a["verification"][0].keys() == {"text", "type", "target", "expect"} and a["verification"][0]["expect"] is True


def test_w3_a_step_that_has_not_run_has_no_status_no_notes_and_no_output(mods):
    atoms, ctx = atoms_of(mods, "Plan")
    a = atoms[0]
    assert "status" not in a and "human_output" not in a and "agent_output" not in a
    assert a["results"] == [] and a["attempts"] == 0 and a["context"] == []
    assert a["expected_output"] == [{"text": "Read the brief", "kind": "check", "met": None}]
    assert a["verification"] == [{"text": "Read the brief", "type": "step-check", "target": "plan.read", "expect": True}]
    assert a["goal"] == "Read the brief" and a["constraints"] == []


def test_w3_who_builds_it_is_the_ai_inside_a_soft_step_and_code_otherwise(mods):
    atoms, ctx = atoms_of(mods, "Plan")
    assert [a["how"]["kind"] for a in atoms] == ["code", "AI", "code", "code"]
    assert all(a["how"]["agent"] == "Plan" for a in atoms)
    assert [a["how"]["steps"] for a in atoms] == ["Read the brief", "Propose the pages", "Fit the page list", "File the plan"]


def test_w3_a_step_that_ran_and_passed_is_passed_with_its_notes_and_what_it_read(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", notes=["the brief has words"], run_id="r-1", read=[{"art": "Brief", "v": 1}, {"post": 3}])
    atoms, ctx = atoms_of(mods, "Plan")
    a = atoms[0]
    assert a["status"] == "passed" and a["attempts"] == 1
    assert a["context"] == ["Brief v1"], "a post it read is no artifact version"
    assert a["expected_output"] == [{"text": "Read the brief: the brief has words", "kind": "check", "met": True}]
    assert a["verification"] == [{"text": "Read the brief: the brief has words", "type": "step-check", "target": "plan.read", "expect": True}]
    r = a["results"][0]
    assert (r["atom"], r["type"], r["target"], r["expect"], r["actual"], r["pass"]) == ("W-1.a1", "step-check", "plan.read", True, True, True)
    assert (r["check"], r["evidence"], r["attempt"], r["of"], r["by"]) == ("Read the brief: the brief has words", "the brief has words", 1, 1, "code")
    assert r["t"] == "2026-10-26T10:00:01+05:30"
    assert a["human_output"] == {"atom": "W-1.a1", "attempt": 1, "text": "the brief has words"}
    assert a["agent_output"] == {"atom": "W-1.a1", "attempt": 1, "files": [], "section": ""}


def test_w3_a_failed_check_is_failed_unless_the_engine_is_still_running(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.pages", ok=False, notes=["no pages proposed"], run_id="r-1")
    atoms, ctx = atoms_of(mods, "Plan")
    a = atoms[1]
    assert a["status"] == "failed" and a["results"][0]["pass"] is False and a["results"][0]["evidence"] == "no pages proposed"
    assert a["expected_output"][0]["met"] is False
    run(W, "Plan", status="running")
    atoms, ctx = atoms_of(mods, "Plan")
    assert atoms[1].get("status") is None and "status" not in atoms[1], "it may still pass on its retry"
    assert atoms[1]["results"][0]["pass"] is False, "what the check found is still said"


def test_w3_a_check_with_no_notes_says_what_it_found_in_words(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", ok=True, notes=[], run_id="r-1")
    step_row(R, "Plan", "plan.pages", ok=False, notes=[], run_id="r-1")
    step_row(R, "Plan", "plan.fit", ok=None, notes=[], run_id="r-1", check={})
    atoms, ctx = atoms_of(mods, "Plan")
    assert atoms[0]["results"][0]["evidence"] == "passed its check" and atoms[0]["human_output"]["text"] == "Read the brief"
    assert atoms[1]["results"][0]["evidence"] == "failed its check"
    r = atoms[2]["results"][0]
    assert r["pass"] is None and r["evidence"] == "its check could not run", "the card says 'Could not run' for null"
    assert "status" not in atoms[2]


def test_w3_a_results_attempt_is_a_run_of_the_engine_not_a_row(mods):
    W, R, J, F = mods
    for item in ("index", "about", "doctors"):                                    # one run of Write, a page at a time
        step_row(R, "Write", "write.page", notes=["has a title and a body"], run_id="r-w1", item=item)
    atoms, ctx = atoms_of(mods, "Write")
    a = atoms[1]
    assert a["attempts"] == 1 and len(a["results"]) == 3
    assert [r["attempt"] for r in a["results"]] == [1, 1, 1] and {r["of"] for r in a["results"]} == {1}
    assert [r["evidence"] for r in a["results"]] == ["%s: has a title and a body" % i for i in ("index", "about", "doctors")]
    step_row(R, "Write", "write.page", ok=False, notes=["no body"], run_id="r-w2", item="index")   # the next run
    atoms, ctx = atoms_of(mods, "Write")
    a = atoms[1]
    assert [r["attempt"] for r in a["results"]] == [2, 1, 1, 1] and {r["of"] for r in a["results"]} == {2}, "the results say which run each is of"
    assert a["attempts"] == 1, "and the step has been tried once in the latest run"
    assert [r["evidence"] for r in a["results"]][1:] == ["%s: has a title and a body" % i for i in ("index", "about", "doctors")], "the latest run first, each run's rows in order"
    assert a["status"] == "failed", "the latest run decides: it failed"
    assert a["human_output"]["attempt"] == 1 and a["agent_output"]["attempt"] == 1, "the notes say the try the card heads with"


def test_w3_the_latest_run_passing_makes_it_passed_though_an_earlier_one_failed(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", ok=False, notes=["the brief is empty"], run_id="r-1")
    step_row(R, "Plan", "plan.read", ok=True, notes=["the brief has words"], run_id="r-2")
    atoms, ctx = atoms_of(mods, "Plan")
    assert atoms[0]["status"] == "passed" and atoms[0]["attempts"] == 1, "passed at the first try of the latest run"
    assert [r["attempt"] for r in atoms[0]["results"]] == [2, 1] and {r["of"] for r in atoms[0]["results"]} == {2}


def test_w3_the_notes_are_the_answer_line_when_the_row_has_one_cut_to_a_line(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", notes=["the brief has words"], run_id="r-1", answer="Priority granted the line " + "x" * 400)
    atoms, ctx = atoms_of(mods, "Plan")
    text = atoms[0]["human_output"]["text"]
    assert text.startswith("Priority said yes to the line") and len(text) <= 305 and not BANNED.search(text)


def test_w3_a_decisions_bare_answer_is_never_the_words_of_an_atom(mods):
    """The same words as the call log: a step's answer of accept, counter, reject, admit, wait or refuse is the act in the owner's
    words, and a code that is no act gives way to the check's note, so the card never prints a bare word."""
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", notes=["the brief has words"], run_id="r-1", answer="counter")
    step_row(R, "Plan", "plan.pages", notes=["6 pages proposed"], run_id="r-1", answer="refuse")
    step_row(R, "Plan", "plan.fit", notes=["every page is on the list"], run_id="r-1", answer="accept-proposal")
    step_row(R, "Plan", "plan.file", notes=[], run_id="r-1", answer="go")
    atoms, ctx = atoms_of(mods, "Plan")
    assert [a["human_output"]["text"] for a in atoms] == ["asked for less", "stopped", "every page is on the list", "File the plan"]
    assert not re.search(r"\b(accept|counter|reject|admit|wait|refuse)\b|accept-proposal", json.dumps(K.build(ctx)), re.I)


def test_w3_identitys_bare_answers_are_the_act_in_the_owners_words_on_the_atom_too(mods):
    """The same table as the call log (j2ui_atoms.acts): Identity's run, drop and ask are 'it runs', 'dropped' and 'asked you'."""
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", notes=["the brief has words"], run_id="r-1", answer="run")
    step_row(R, "Plan", "plan.pages", notes=["6 pages proposed"], run_id="r-1", answer="drop")
    step_row(R, "Plan", "plan.fit", notes=["every page is on the list"], run_id="r-1", answer="ask")
    atoms, ctx = atoms_of(mods, "Plan")
    assert [a["human_output"]["text"] for a in atoms[:3]] == ["it runs", "dropped", "asked you"]


def test_w3_agent_output_names_the_files_of_the_version_the_engine_made(mods):
    W, R, J, F = mods
    r1 = run(W, "Plan", status="ok", id="r-plan-a")
    W.add_version(REF, "Site plan", {"site-plan.json": "{}", "notes/plan.md": "x"}, [{"art": "Brief", "v": 1}], r1["id"], {"ok": True, "notes": []})
    W.add_version(REF, "Site plan", {"other.json": "{}"}, [{"art": "Brief", "v": 1}], "r-someone-else", {"ok": True, "notes": []})
    step_row(R, "Plan", "plan.file", notes=["files and their verdict are both there"], run_id=r1["id"])
    atoms, ctx = atoms_of(mods, "Plan")
    assert atoms[3]["agent_output"]["files"] == ["notes/plan.md", "site-plan.json"], "the version the engine's own run made, by name"
    assert atoms[0]["agent_output"]["files"] == [] if "agent_output" in atoms[0] else True, "a step that only reads made no file"


def test_w3_only_the_step_that_files_names_the_files_as_its_output(mods):
    W, R, J, F = mods
    r1 = run(W, "Plan", status="ok", id="r-plan-a")
    W.add_version(REF, "Site plan", {"site-plan.json": "{}"}, [{"art": "Brief", "v": 1}], r1["id"], {"ok": True, "notes": []})
    for sid in ("plan.read", "plan.pages", "plan.fit", "plan.file"):
        step_row(R, "Plan", sid, notes=["fine"], run_id=r1["id"])
    atoms, ctx = atoms_of(mods, "Plan")
    assert [a["agent_output"]["files"] for a in atoms] == [[], [], [], ["site-plan.json"]]
    assert all(a["agent_output"]["attempt"] == 1 for a in atoms)
    e = next(x for x in ctx.engines if x["name"] == "Plan")
    import engine_runtime
    orig = engine_runtime.all_steps
    engine_runtime.all_steps = lambda name: (_ for _ in ()).throw(RuntimeError("no template"))
    try:
        again = [a["agent_output"]["files"] for a in A.legacy_atoms(ctx, e)]
    finally:
        engine_runtime.all_steps = orig
    assert again == [[], [], [], ["site-plan.json"]], "with no template to read, the last step is the one that files"


def test_w3_agent_output_has_no_files_when_the_engine_made_no_version(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.file", notes=["files and their verdict are both there"], run_id="r-1")
    atoms, ctx = atoms_of(mods, "Plan")
    assert atoms[3]["agent_output"]["files"] == []


def test_w3_no_string_of_any_atom_is_a_check_id_or_says_an_inside_word(mods):
    W, R, J, F = mods
    for sid in ("plan.read", "plan.pages", "plan.fit", "plan.file"):
        step_row(R, "Plan", sid, notes=["brief_is_text", "6 pages proposed"], run_id="r-1")
    step_row(R, "Plan", "plan.read", notes=["Priority granted the line; Take the refusal to Identity"], run_id="r-2")
    atoms, ctx = atoms_of(mods, "Plan")
    text = list(walk(atoms))
    assert not [s for s in text if CHECK_ID.match(s)], [s for s in text if CHECK_ID.match(s)]
    assert not BANNED.search(json.dumps(atoms)) and "granted" not in json.dumps(atoms)
    ids = {a["verification"][0]["target"] for a in atoms}
    assert ids == {"plan.read", "plan.pages", "plan.fit", "plan.file"}, "the check's own id is only the target"
    assert json.loads(json.dumps(atoms)) == atoms


def test_w3_an_engine_with_no_place_in_the_line_or_no_template_has_no_atoms(mods):
    ctx = standin(mods)
    assert A.legacy_atoms(ctx, "Nothing") == []
    e = dict(next(x for x in ctx.engines if x["name"] == "Plan"), wid=None)
    assert A.legacy_atoms(ctx, e) == []
    e = dict(next(x for x in ctx.engines if x["name"] == "Plan"), steps_view=None)
    assert A.legacy_atoms(ctx, e) == []
    assert [a["id"] for a in A.legacy_atoms(ctx, "Plan")][0] == "W-1.a1", "an engine can be named"


# ---- atoms_v1: the prototype's own views, through the vendored schema ----------------------------------------------------
def seeded(mods):
    W, R, J, F = mods
    r1 = run(W, "Plan", status="ok", id="r-plan-a")
    W.add_version(REF, "Site plan", {"site-plan.json": "{}"}, [{"art": "Brief", "v": 1}], r1["id"], {"ok": True, "notes": []})
    for sid, note in (("plan.read", "the brief has words"), ("plan.pages", "6 pages proposed"), ("plan.fit", "the home page is first"),
                      ("plan.file", "files and their verdict are both there")):
        step_row(R, "Plan", sid, notes=[note], run_id=r1["id"], read=[{"art": "Brief", "v": 1}])
    r2 = run(W, "Write", status="ok", id="r-write-a")
    W.add_version(REF, "Pages", {"index.html": "<p>x</p>", "about.html": "<p>y</p>"}, [{"art": "Site plan", "v": 1}], r2["id"], {"ok": True, "notes": []})
    for item in ("index", "about"):
        step_row(R, "Write", "write.page", notes=["has a title and a body"], run_id=r2["id"], item=item, read=[{"art": "Site plan", "v": 1}])
    step_row(R, "Write", "write.file", notes=["2 pages"], run_id=r2["id"], read=[{"art": "Site plan", "v": 1}])
    step_row(R, "Check", "check.build", ok=False, notes=["a link does not resolve"], run_id="r-check-a")
    return standin(mods)


def test_w3_atoms_v1_is_the_prototypes_run_views_of_the_workflows(mods, monkeypatch):
    schema = proto_schema()
    monkeypatch.setattr(A, "_schema", schema)
    ctx = seeded(mods)
    got = K.build(ctx)
    workflows = got["workflows"]
    views, warnings = schema.run_views(workflows)
    assert got["atoms_v1"] == {v["id"]: v for v in views} and len(views) == 11
    assert not [w for w in warnings if "which is not an atom of this run" in w], warnings
    assert not [w for w in warnings if w.startswith("cycle")], warnings
    for v in got["atoms_v1"].values():
        assert list(v) == VIEW_KEYS, "the 18 keys in the prototype's order"
    assert schema.validate_views(list(got["atoms_v1"].values())) == warnings, "the same reading by the prototype's own validator"
    text = [s for s in walk(got["atoms_v1"]) if isinstance(s, str)]
    texts = [x for v in got["atoms_v1"].values() for x in (v["goal"], v["notes"]) + tuple(e.get("evidence") or "" for e in v["verification"])]
    assert not [t for t in texts if CHECK_ID.match(str(t))], "no goal, note or evidence is a check's id"
    assert text and json.loads(json.dumps(got["atoms_v1"])) == got["atoms_v1"]


def test_w3_atoms_v1_reads_the_atoms_as_the_prototype_does(mods, monkeypatch):
    schema = proto_schema()
    monkeypatch.setattr(A, "_schema", schema)
    got = K.build(seeded(mods))["atoms_v1"]
    read = got["W-1.a1"]
    assert (read["schema"], read["workflow"], read["name"], read["owner"], read["status"]) == ("atom/1", "W-1", "Plan", "Plan", "closed")
    assert read["verification"][0]["met"] is True and read["verification"][0]["check"] == "valid"
    assert got["W-1.a4"]["output"] == [{"verb": "make", "name": "site-plan.json", "form": "file", "ref": "site-plan.json"}]
    pages = got["W-2.a3"]["output"]
    assert got["W-2.a2"]["output"] == [], "the step that writes each page filed no file of its own"
    assert sorted(o["name"] for o in pages) == ["about.html", "index.html"] and {o["form"] for o in pages} == {"page"}
    assert [e["atom"] for e in got["W-2.a1"]["depends_on"]][:1] == ["W-1.a1"], "from the workflow's dependency on Plan"
    assert got["W-3.a3"]["status"] == "verify_failed", "a failed check of an engine that is not running"
    assert got["W-4.a1"]["status"] == "open" and got["W-4.a1"]["output"] == []


def test_w3_without_the_vendored_file_there_are_no_views(mods, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "_schema", None)
    monkeypatch.setattr(A, "ASSET", tmp_path / "j2ui_assets" / "j2_schema.py")
    A._LOADED.clear()
    ctx = seeded(mods)
    got = K.build(ctx)
    assert got["atoms_v1"] == {}, "the page draws its plain cards"
    assert len(got["workflows"][0]["atoms"]) == 4 and got["agents"]["W-1"] == "W-1 Plan"
    assert ctx.reasons == []


def test_w3_the_vendored_file_is_loaded_by_path_and_read_again_when_it_changes(mods, monkeypatch, tmp_path):
    text = proto_text()
    asset = tmp_path / "j2ui_assets" / "j2_schema.py"
    asset.parent.mkdir()
    asset.write_text(text)
    monkeypatch.setattr(A, "_schema", None)
    monkeypatch.setattr(A, "ASSET", asset)
    A._LOADED.clear()
    first = K.build(seeded(mods))["atoms_v1"]
    assert len(first) == 11 and first["W-1.a1"]["schema"] == "atom/1"
    held = A.schema()
    assert A.schema() is held, "loaded once"
    asset.write_text(text + "\nSCHEMA_NOTE = 'changed'\n")
    os.utime(asset, (asset.stat().st_atime, asset.stat().st_mtime + 5))
    assert A.schema() is not held and A.schema().SCHEMA_NOTE == "changed", "a changed file is read again"


def test_w3_a_vendored_file_that_cannot_run_is_no_views_and_no_error(mods, monkeypatch, tmp_path):
    asset = tmp_path / "j2_schema.py"
    asset.write_text("raise RuntimeError('broken')\n")
    monkeypatch.setattr(A, "_schema", None)
    monkeypatch.setattr(A, "ASSET", asset)
    A._LOADED.clear()
    assert A.schema() is None and A.views([{"id": "W-1"}]) == {}
    asset.write_text("def run_views(workflows, given=None, ended=False):\n    raise ValueError('no')\n")
    os.utime(asset, (asset.stat().st_atime, asset.stat().st_mtime + 5))
    assert A.views([{"id": "W-1"}]) == {}, "a schema that raises gives none"


def test_w3_sections_are_none_and_agents_name_who_builds_each_workflow(mods):
    got = K.build(standin(mods))
    assert got["sections"] == []
    assert got["agents"] == {"W-1": "W-1 Plan", "W-2": "W-2 Write", "W-3": "W-3 Check", "W-4": "W-4 Publish"}


def test_w3_a_failure_in_the_atoms_leaves_the_workflows_as_they_were(mods, monkeypatch):
    ctx = standin(mods)
    monkeypatch.setattr(A, "legacy_atoms", lambda c, e: 1 / 0)
    got = K.build(ctx)
    assert [w["id"] for w in got["workflows"]] == ["W-1", "W-2", "W-3", "W-4"] and all(w["atoms"] == [] for w in got["workflows"])
    assert got["atoms_v1"] == {} and got["agents"] == {}
    assert any(r.startswith("atoms: ZeroDivisionError") for r in ctx.reasons), ctx.reasons


def test_w3_a_real_departments_atoms_make_valid_views(mods, born, monkeypatch):
    schema = proto_schema()
    monkeypatch.setattr(A, "_schema", schema)
    W, R, J, F = mods
    ref = born()
    ctx = standin(mods, ref=ref)
    got = K.build(ctx)
    views, warnings = schema.run_views(got["workflows"])
    assert got["atoms_v1"] == {v["id"]: v for v in views} and len(views) == 11
    assert not [w for w in warnings if "which is not an atom of this run" in w or w.startswith("cycle")], warnings
    plan = got["workflows"][0]["atoms"]
    assert [a["status"] for a in plan] == ["passed"] * 4 and all(a["attempts"] == 1 for a in plan)
    assert plan[0]["context"] == ["Brief v1"] and plan[3]["agent_output"]["files"], "the plan's file, by name"
    write = got["workflows"][1]["atoms"]
    assert len(write[1]["results"]) == 6 and write[1]["attempts"] == 1, "six pages, one attempt"
    assert not BANNED.search(json.dumps(got)) and not [s for s in walk(got) if CHECK_ID.match(s)]


def test_w3_the_prototypes_page_draws_every_card_from_these_atoms(mods, monkeypatch):
    monkeypatch.setattr(A, "_schema", proto_schema())
    got = K.build(seeded(mods))
    state = page_state(got)
    html = render(state, "({cards: Object.fromEntries(s.workflows.map(w => [w.id, atomCards(s, w)])), table: renderWorkflows(s)})")
    plan = shown(html["cards"]["W-1"])
    assert "Work atom 1 W-1.a1 · Read the brief" in plan and "Work atom 4 W-1.a4 · File the plan" in plan
    assert "1 check(s), checks passed, attempt 1 of 3" in plan
    assert "AI builds it: Plan." in plan and "Code builds it: Plan." in plan
    assert "Read the brief: the brief has words" in plan and "Brief v1" in plan
    assert re.search(r"Passed\s*: the brief has words\. Attempt 1 of 1", plan), plan[:900]
    check = shown(html["cards"]["W-3"])
    assert "checks failing" in check and re.search(r"Failed\s*: a link does not resolve", check)
    never = shown(html["cards"]["W-4"])
    assert "not run yet" in never and "Not run yet." in never and "Nothing made yet." in never
    table = shown(html["table"])
    for w in got["workflows"]:
        assert w["id"] in table and w["name"] in table
    for text in (plan, check, never, table):
        assert not re.search(r"undefined|NaN|\bnull\b|\[object", text), re.findall(r".{30}(?:undefined|NaN|null|\[object).{30}", text)
    assert "calls 0/" in table and "retries 0/%d" % len(mods[1].WAITS) in table and "%d min" % mods[0].dept(REF)["windows"]["Plan"] in table


def test_w3_the_first_result_the_page_shows_is_the_latest_runs(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", ok=False, notes=["the brief is empty"], run_id="r-1")
    step_row(R, "Plan", "plan.read", ok=True, notes=["the brief has words"], run_id="r-2")
    atoms, ctx = atoms_of(mods, "Plan")
    assert [(r["attempt"], r["pass"]) for r in atoms[0]["results"]] == [(2, True), (1, False)]
    got = K.build(ctx)
    state = page_state(got)
    text = shown(render(state, "atomCards(s, s.workflows[0])"))
    assert re.search(r"Passed\s*: the brief has words\. Attempt 2 of 2", text), text[:1200]


def test_w3_an_atom_carries_the_latest_rows_of_a_step_not_every_row_it_ever_had(mods):
    W, R, J, F = mods
    for n in range(100):
        step_row(R, "Plan", "plan.read", ok=n % 10 != 0, notes=["note %d" % n], run_id="r-%03d" % n)
    atoms, ctx = atoms_of(mods, "Plan")
    a = atoms[0]
    assert len(a["results"]) == A.RESULTS_MAX == 30
    assert [r["attempt"] for r in a["results"]] == list(range(100, 70, -1)) and {r["of"] for r in a["results"]} == {100}, "the run each is of"
    assert a["attempts"] == 1, "a hundred requests are not a hundred tries: the latest run tried it once"
    assert a["status"] == "passed" and a["human_output"]["text"] == "note 99" and a["human_output"]["attempt"] == 1


def test_w3_a_first_try_pass_reads_attempt_1_of_3_in_every_request(mods):
    """The page prints 'attempt N of 3' from `attempts`. Each request runs the engine again, so counting the engine's runs made every
    first-try atom read 'attempt 2 of 3' after one follow-up and 'attempt 4 of 3' after a fourth. It is the tries in the latest run."""
    W, R, J, F = mods
    for request in range(1, 5):
        for sid in ("plan.read", "plan.pages", "plan.fit", "plan.file"):
            step_row(R, "Plan", sid, notes=["fine"], run_id="r-request-%d" % request)
        got = K.build(standin(mods))
        plan = got["workflows"][0]["atoms"]
        assert [a["attempts"] for a in plan] == [1, 1, 1, 1], request
        assert [(a["human_output"]["attempt"], a["agent_output"]["attempt"]) for a in plan] == [(1, 1)] * 4, request
        assert {r["of"] for a in plan for r in a["results"]} == {request}, "a result still says which run it is of"
        text = shown(render(page_state(got), "atomCards(s, s.workflows[0])"))
        assert text.count("checks passed, attempt 1 of 3") == 4, (request, text[:600])
        assert text.count("Check attempt 1 of 3") == 4 and text.count("Attempt 1.") == 4, request
        assert set(re.findall(r"(?:checks passed|checks failing), attempt (\d+) of 3|Check attempt (\d+) of 3", text)) == {("1", ""), ("", "1")}, request


def test_w3_the_tries_are_the_most_rows_one_item_has_in_the_latest_run_and_never_over_the_retry_bound(mods):
    W, R, J, F = mods
    bound = len(R.WAITS)
    assert bound == 3, "the 3 the page prints"
    for item in ("index", "about"):                                               # a page each: one try
        step_row(R, "Write", "write.page", notes=["fine"], run_id="r-w1", item=item)
    assert atoms_of(mods, "Write")[0][1]["attempts"] == 1
    step_row(R, "Write", "write.page", ok=False, notes=["no body"], run_id="r-w1", item="index")     # one page tried again in the same run
    assert atoms_of(mods, "Write")[0][1]["attempts"] == 2
    for n in range(6):                                                            # and again and again: the bound
        step_row(R, "Write", "write.page", ok=False, notes=["no body"], run_id="r-w1", item="index")
    a = atoms_of(mods, "Write")[0][1]
    assert a["attempts"] == bound == a["human_output"]["attempt"] and len(a["results"]) == 9
    step_row(R, "Write", "write.page", notes=["fine"], run_id="r-w2", item="index")             # the next run: its own tries
    assert atoms_of(mods, "Write")[0][1]["attempts"] == 1


def test_w3_runs_are_grouped_in_one_pass(mods):
    rows = [{"id": "s-%d" % i, "run": "r-%d" % (i // 2)} for i in range(6)] + [{"id": "s-x", "run": None}, {"id": "s-y"}]
    got = A._by_run(rows)
    assert list(got) == ["r-0", "r-1", "r-2", "s-x", "s-y"] and [len(v) for v in got.values()] == [2, 2, 2, 1, 1]
