"""The proof run (PRD M10.4 and M10.5; amendment A1, package W2-PROOF): qa/j2_metrics.py reads only the record and reports
SM-1 to SM-14.

Two halves. The first builds records by hand, one fault at a time, and asks each metric to find it and to pass the
record beside it: a metric that cannot fail would report 0 for ever. The second is the scenario the proof runs over:
TestProofScenarios brings one department of each kind to a real done the way a person does (founded, asked for, set up
by Root, the first publish stamped), with the model a function of the step id, and the script then reads what they left
in a records home it kept. test_j2.py, test_j2_api.py and test_j1.py are the rest of the scenario suite; they have their
own lanes, and the script runs them again for the proof.
"""
import importlib
import importlib.util
import json
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LAB_LINE = [{"name": "Gather", "does": "collects the lab inventory facts", "reads": "Brief", "writes": "Notes", "internet": False},
            {"name": "Report", "does": "writes the inventory report", "reads": "Notes", "writes": "Report", "internet": False}]


def _load():
    spec = importlib.util.spec_from_file_location("j2_metrics_under_test", HERE / "qa" / "j2_metrics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# ---- the scenario: a department of each kind, to a real done --------------------------------------------------------
@pytest.fixture
def j2(tmp_path, monkeypatch):
    """test_j2's fixture: a department is born the way a person makes one, on a records home of its own."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J

    for module in (E, W, org2_apply, founding, R, J):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding


def _model(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what the model says (a dict, or a callable taking the prompt).
    Every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _items_met(prompt):
    """Audit's reader, a function: it says every done-when item in the prompt is met, with its evidence."""
    items = json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])
    return {"items": [{"id": i["id"], "verdict": "met", "claim": "it holds", "evidence": "the work shows it"} for i in items], "findings": []}


READER = {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met}


def _born(j2, words=WEBSITE, org="Acme Learning"):
    W, _, _, founding = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _default(j2, ref="dref-answers"):
    """A department of the default kind, as test_j2 makes one: one Do engine, its Result the deliverable."""
    W, _, J, _ = j2
    d, _ = W.create(ref, "Answers", None, kind="default")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
    W.run_until_idle(d["ref"], limit=300)
    return d["ref"]


def _stamp_all(W, ref):
    for a in [a for a in W.asks(ref) if a["status"] == "pending"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)


class TestProofScenarios:
    """One department of each kind, brought to a real done with the model stubbed (decision C2). The proof reads what
    they leave: these are the departments SM-7 counts and the ones SM-1, SM-3 and SM-4 are held against on every kind."""

    @pytest.mark.parametrize("kind", ["website", "default", "organic"])
    def test_a_department_of_each_kind_reaches_a_done_a_reading_stands_behind(self, j2, monkeypatch, kind):
        W, R, J, _ = j2
        answers = dict(READER, **({"adapt.line": {"engines": LAB_LINE}} if kind == "organic" else {}))
        _model(monkeypatch, R, answers)
        words, org = {"website": (WEBSITE, "Acme Learning"), "organic": (ORGANIC, "Lab Co")}.get(kind, (None, None))
        ref = _default(j2) if kind == "default" else _born(j2, words, org)
        _stamp_all(W, ref)
        assert W.dept(ref)["kind"] == kind
        st = J.status(ref)
        assert (st["state"], st["goal_reached"]) == ("done", True), "%s did not reach done: %s" % (kind, st["state"])
        assert [e["action"] for e in J.events(ref)].count("goal.reached") == 1
        # and the proof reads it the same way, from the files
        d = M.Dept(W.ddir(ref))
        assert M.real_done(d) and M.sm1([d])["value"] == 0 and M.sm1([d])["claims"] == 1
        assert M.sm3([d])["value"] == 0 and M.sm4([d])["value"] == 0


# ---- records by hand: one fault at a time ---------------------------------------------------------------------------
def _w(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc) if not isinstance(doc, str) else doc, encoding="utf-8")


def _jsonl(path, rows):
    _w(path, "".join(json.dumps(r) + "\n" for r in rows))


ITEMS = [{"id": "D1", "text": "Every page is checked", "how": "code", "level": "outcome"},
         {"id": "D2", "text": "A learner can find the lessons", "how": "model", "level": "outcome"}]


def _row(item, verdict, method="model", sev="low"):
    return {"id": item, "subject": "s", "claim": "c", "evidence": "e", "method": method, "verdict": verdict, "severity": sev}


def _reading(rid="r-00000001", v=1, art="Live site", rows=None, read=True, findings=(), at="2026-10-27T10:00:00+05:30"):
    return {"schema_version": 1, "id": rid, "v": v, "artifact": art, "cycle_id": "c1", "round": None, "read": read,
            "why_not_read": None if read else "no model was there to read it", "findings": list(findings), "at": at,
            "items": rows if rows is not None else [_row("D1", "met", "code"), _row("D2", "met")]}


def _goal(art="Live site", v=1, refs=None, at="2026-10-27T10:00:05+05:30"):
    return {"action": "goal.reached", "event_id": "evt-1", "seq": 9, "occurred_at": at,
            "evidence_refs": refs if refs is not None else [{"artifact": art, "version": v}], "payload": {}}


def make(root, ref="dref-a", kind="website", group="t0", dept=None, runs=None, asks=None, board=None, readings=None,
         events=None, state=None, table=None):
    """A department folder as the app leaves it, <root>/<group>/departments/<ref>/, with only the files given."""
    d = Path(root) / group / "departments" / ref
    _w(d / "dept.json", dict({"kind": kind, "ref": ref, "name": "Acme", "done_items": ITEMS, "workflows": [],
                              "envelopes": {}}, **(dept or {})))
    if runs is not None:
        _w(d / "runs.json", runs)
    if asks is not None:
        _w(d / "asks.json", asks)
    if board is not None:
        _jsonl(d / "board.jsonl", board)
    if readings is not None:
        _jsonl(d / "readings.jsonl", readings)
    if events is not None:
        _jsonl(d / "j2-events.jsonl", events)
    if state is not None:
        _w(d / "j2-state.json", dict({"cycle_id": "c1"}, **state))
    if table is not None:
        _w(d / "coordination.json", table)
    return d


def _depts(root):
    return M.find_departments(root)


def test_the_record_is_found_in_a_kept_tree_and_in_a_flat_home_and_a_link_is_not_followed(tmp_path):
    make(tmp_path, "dref-a", group="lane/bt/test_one0")
    make(tmp_path, "dref-b", group="lane/bt/test_two0")
    try:                                                            # pytest leaves a `current` link beside each numbered folder
        (tmp_path / "lane" / "bt" / "test_onecurrent").symlink_to(tmp_path / "lane" / "bt" / "test_one0")
    except (OSError, NotImplementedError):
        pass                                                        # a platform with no links has no link to skip
    found = _depts(tmp_path)
    assert [(d.ref, d.group) for d in found] == [("dref-a", "lane/test_one0"), ("dref-b", "lane/test_two0")]
    flat = tmp_path / "home"
    _w(flat / "dref-c" / "dept.json", {"kind": "website", "ref": "dref-c", "name": "Flat"})
    (d,) = _depts(flat)
    assert (d.ref, d.group, d.label) == ("dref-c", "", "Flat (website)")


def test_a_torn_line_and_a_torn_document_read_as_absent(tmp_path):
    d = make(tmp_path, runs="{not json", board=[{"n": 1}])
    with open(d / "board.jsonl", "a") as f:
        f.write('{"n": 2, "src"')
    (dept,) = _depts(tmp_path)
    assert dept.runs == [] and [p["n"] for p in dept.board] == [1] and dept.events == [] and dept.state == {}


# ---- SM-1 ------------------------------------------------------------------------------------------------------------
def _sm1(tmp_path, **kw):
    make(tmp_path, **kw)
    return M.sm1(_depts(tmp_path))


def test_sm1_a_claim_with_the_reading_of_its_version_every_item_met_is_clean(tmp_path):
    m = _sm1(tmp_path, readings=[_reading()], events=[_goal()])
    assert (m["value"], m["claims"], m["status"], m["gaps"]) == (0, 1, "met", [])


def test_sm1_no_claim_is_no_gap_and_a_state_written_by_hand_is_not_a_claim(tmp_path):
    m = _sm1(tmp_path, events=[], state={"state": "done"})
    assert (m["value"], m["claims"]) == (0, 0)


@pytest.mark.parametrize("why, readings, refs, fragment", [
    ("no reading at all", [], None, "no reading of Live site v1 is on the record"),
    ("a reading of another version", [_reading(v=2)], None, "no reading of Live site v1"),
    ("a reading of another artifact", [_reading(art="Result")], None, "no reading of Live site v1"),
    ("a version that was not read", [_reading(read=False, rows=[])], None, "was not read (no model was there to read it)"),
    ("an item not met", [_reading(rows=[_row("D1", "met", "code"), _row("D2", "not_met")])], None, "D2 not met"),
    ("an item to confirm", [_reading(rows=[_row("D1", "met", "code"), _row("D2", "to_confirm")])], None, "D2 to confirm"),
    ("an item with no row", [_reading(rows=[_row("D1", "met", "code")])], None, "D2 has no row"),
    ("the worse of two rows standing", [_reading(rows=[_row("D1", "met", "code"), _row("D2", "met"), _row("D2", "not_met", "code")])],
     None, "D2 not met"),
    ("a high finding open", [_reading(findings=[{"id": "F1", "severity": "high", "claim": "c", "where": "w"}])], None,
     "high finding (F1)"),
    ("a claim that cites nothing", [_reading()], [], "cites no reading and no version"),
    ("a reading id that is not there", [_reading()], ["r-ffffffff"], "no reading of r-ffffffff"),
])
def test_sm1_a_claim_without_the_reading_it_needs_is_a_gap_that_names_why(tmp_path, why, readings, refs, fragment):
    m = _sm1(tmp_path, readings=readings, events=[_goal(refs=refs)])
    assert (m["value"], m["status"]) == (1, "gap"), why
    assert fragment in m["gaps"][0] and "Acme (website)" in m["gaps"][0] and "evt-1" in m["gaps"][0]


def test_sm1_a_reading_is_found_by_its_id_in_either_shape_the_claim_may_cite_it(tmp_path):
    for i, refs in enumerate((["r-00000001"], [{"reading": "r-00000001"}], [{"id": "r-00000001", "kind": "reading"}])):
        m = _sm1(tmp_path / ("x%d" % i), readings=[_reading()], events=[_goal(refs=refs)])
        assert (m["value"], m["claims"]) == (0, 1), refs


def test_sm1_the_reading_that_stands_is_the_last_one_of_that_version_before_the_claim(tmp_path):
    late_no = _reading(rid="r-00000002", rows=[_row("D1", "met", "code"), _row("D2", "not_met")], at="2026-10-27T11:00:00+05:30")
    assert _sm1(tmp_path / "a", readings=[_reading(), late_no], events=[_goal()])["value"] == 0       # read after the claim: not behind it
    early_no = _reading(rid="r-00000003", rows=[_row("D1", "met", "code"), _row("D2", "not_met")], at="2026-10-27T09:00:00+05:30")
    assert _sm1(tmp_path / "b", readings=[early_no, _reading()], events=[_goal()])["value"] == 0      # a later yes stands
    just_after = dict(early_no, at="2026-10-27T10:00:04+05:30")
    assert _sm1(tmp_path / "c", readings=[_reading(), just_after], events=[_goal()])["value"] == 1       # the last one before the claim says no


def test_sm1_a_claim_made_before_any_reading_of_its_version_is_not_backed_by_a_reading_made_after_it(tmp_path):
    """A reading written after the claim cannot have been what the claim stood on, even when it says every item is met."""
    late = _reading(at="2026-10-27T11:00:00+05:30")                                  # the claim is at 10:00:05
    m = _sm1(tmp_path / "one", readings=[late], events=[_goal()])
    assert (m["value"], m["status"]) == (1, "gap") and "its only reading came after the claim" in m["gaps"][0]
    later = [late, _reading(rid="r-00000002", at="2026-10-27T12:00:00+05:30")]
    m = _sm1(tmp_path / "two", readings=later, events=[_goal(refs=["r-00000001", "r-00000002"])])
    assert m["value"] == 1 and "every reading it cites came after the claim" in m["gaps"][0]
    same_second = _reading(at="2026-10-27T10:00:05+05:30")                           # the app writes the claim and its reading together
    assert _sm1(tmp_path / "three", readings=[same_second], events=[_goal()])["value"] == 0
    assert _sm1(tmp_path / "four", readings=[late, _reading(rid="r-00000003")], events=[_goal(refs=["r-00000001", "r-00000003"])])["value"] == 0, \
        "one reading before the claim stands behind it, whatever came after"


def test_sm7_a_done_whose_only_reading_came_after_its_claim_is_not_a_real_done(tmp_path):
    make(tmp_path, kind="website", state={"state": "done"}, readings=[_reading(at="2026-10-27T11:00:00+05:30")], events=[_goal()])
    assert M.sm7(_depts(tmp_path))["value"] == 0


def test_sm1_a_department_with_no_done_item_has_nothing_to_have_read(tmp_path):
    m = _sm1(tmp_path, dept={"done_items": []}, readings=[_reading(rows=[])], events=[_goal()])
    assert m["value"] == 1 and "no done-when item" in m["gaps"][0]


# ---- SM-3 ------------------------------------------------------------------------------------------------------------
def _run(engine, rid="r-1", system=False, slot=None, **kw):
    return dict({"id": rid, "engine": engine, "system": system, "slot": slot, "status": "ok", "started": "2026-10-27T10:00:00+05:30",
                 "ended": "2026-10-27T10:00:00+05:30", "spend": {"calls": 0, "usd": 0.0}}, **kw)


LINE = [{"version": 1, "engines": ["Plan", "Write", "Check", "Publish"], "source": "library"}]


def test_sm3_an_engine_on_the_registered_line_a_function_s_system_row_and_a_grown_engine_are_all_clean(tmp_path):
    make(tmp_path, dept={"workflows": LINE}, state={"state": "running"}, table={"grown": ["Do"]},
         runs=[_run("Plan"), _run("Publish", "r-2"), _run("Do", "r-3"), _run("Identity", "r-4", system=True), _run("Audit", "r-5", True),
               _run("Root", "r-6", True, what="refused a write that does not fit the interface: asks: $.kind: is wrong")])
    m = M.sm3(_depts(tmp_path))
    assert (m["value"], m["runs"], m["departments"]) == (0, 6, 1)
    assert M.FUNCTIONS == ("Identity", "Adaptation", "Priority", "Coordination", "Audit"), "the five functions, and no more"


@pytest.mark.parametrize("name", ["Identity", "Adaptation", "Priority", "Coordination", "Audit", "Root", "Setup"])
def test_sm3_a_work_run_named_like_a_function_or_root_is_on_no_line_only_a_system_row_may_carry_the_name(tmp_path, name):
    """Rule 3 and S-10: Root never starts an engine. A run that is not a system row and is called Root (or Setup, or a
    function) is an engine on no line, and the allowance for the functions' own rows must not hide it."""
    make(tmp_path, dept={"workflows": LINE}, state={"state": "running"},
         runs=[_run("Plan"), _run(name, "r-9", system=False, slot="%s@brief.v1" % name)])
    m = M.sm3(_depts(tmp_path))
    assert (m["value"], m["status"]) == (1, "gap") and ("ran %s (run r-9, %s@brief.v1)" % (name, name)) in m["gaps"][0]


def test_sm3_setup_is_no_function_of_a_department_that_lives_a_cycle_even_as_a_system_row(tmp_path):
    """'Setup' runs on a root department, which SM-3 does not read; in a J2 department it is no title a system row carries."""
    make(tmp_path, kind="root", runs=[_run("Setup", "r-1")])
    assert M.sm3(_depts(tmp_path))["value"] == 0
    make(tmp_path / "j2", state={"state": "running"}, runs=[_run("Setup", "r-1", system=True)])
    assert M.sm3(_depts(tmp_path / "j2"))["value"] == 1


def test_sm3_an_engine_the_counter_cut_that_still_ran_is_a_gap_that_names_the_run(tmp_path):
    cut = [{"version": 1, "engines": ["Plan", "Write", "Publish"], "source": "library"}]
    make(tmp_path, dept={"workflows": cut, "engines": ["Plan", "Write", "Check", "Publish"]}, state={"state": "running"},
         runs=[_run("Plan"), _run("Check", "r-9", slot="Check@pages.v1")])
    m = M.sm3(_depts(tmp_path))
    assert (m["value"], m["status"]) == (1, "gap")
    assert "ran Check (run r-9, Check@pages.v1)" in m["gaps"][0]


def test_sm3_a_run_before_any_registration_is_a_gap_and_the_union_is_over_every_version(tmp_path):
    make(tmp_path, "dref-a", state={"state": "adapting"}, runs=[_run("Plan")])
    v2 = LINE + [{"version": 2, "engines": ["Facts"], "source": "shaped"}]
    make(tmp_path, "dref-b", dept={"workflows": v2}, state={"state": "running"}, runs=[_run("Plan"), _run("Facts", "r-2")])
    m = M.sm3(_depts(tmp_path))
    assert m["value"] == 1 and "dref-a" not in m["gaps"][0] and "ran Plan" in m["gaps"][0]


def test_sm3_a_department_that_lives_no_cycle_is_not_held_to_a_line(tmp_path):
    make(tmp_path, kind="root", runs=[_run("Whatever")])
    make(tmp_path, "dref-b", runs=[_run("Whatever")])
    m = M.sm3(_depts(tmp_path))
    assert (m["value"], m["departments"], m["runs"]) == (0, 0, 0)


# ---- SM-4 ------------------------------------------------------------------------------------------------------------
def _post(n, src, dst, act="inform"):
    return {"n": n, "src": src, "dst": dst, "msg_type": act, "payload": {}}


def test_sm4_only_identity_posts_to_the_owner(tmp_path):
    make(tmp_path, board=[_post(1, "Owner", ["Identity"], "request"), _post(2, "Identity", ["Owner"]),
                          _post(3, "Identity", ["Adaptation", "Owner"], "request"), _post(4, "Audit", ["Identity"])])
    m = M.sm4(_depts(tmp_path))
    assert (m["value"], m["posts"], m["status"]) == (0, 2, "met")


@pytest.mark.parametrize("src", ["Priority", "Audit", "Adaptation", "Coordination", "Root"])
def test_sm4_a_post_to_the_owner_from_anyone_else_is_a_gap(tmp_path, src):
    make(tmp_path, board=[_post(7, "Identity", ["Owner"]), _post(8, src, ["Owner"], "refuse")])
    m = M.sm4(_depts(tmp_path))
    assert (m["value"], m["status"]) == (1, "gap") and ("%s posted to the owner (board 8, refuse)" % src) in m["gaps"][0]


# ---- SM-6 and SM-7 ---------------------------------------------------------------------------------------------------
def _ask(status="pending", options=None, **kw):
    return dict({"id": "a-1", "kind": "j2_identity", "status": status, "options": options if options is not None else []}, **kw)


@pytest.mark.parametrize("state, asks, dead", [
    ("waiting", [_ask()], False),                                    # a question answered in words is a next move
    ("waiting", [], True),
    ("waiting", [_ask("chosen")], True),                             # an ask already answered is none
    ("blocked", [_ask(options=[{"id": "o1"}])], False),
    ("blocked", [_ask()], True),                                     # blocked is left by an option
    ("unread", [], True),
    ("unread", [_ask(options=[{"id": "o1"}])], False),
    ("stopped", [], False),                                          # Start is the owner's move
    ("done", [], False),
    ("running", [], False),                                          # the motor moves it
    ("pursuing", [], False),
])
def test_sm6_an_end_state_that_is_not_done_needs_a_pending_ask(tmp_path, state, asks, dead):
    make(tmp_path, state={"state": state}, asks=asks)
    m = M.sm6(_depts(tmp_path))
    assert (m["value"] == 1) is dead
    assert not dead or "the owner has no next move" in m["gaps"][0]


def _done_dept(tmp_path, ref, kind, **kw):
    return make(tmp_path, ref, kind=kind, state={"state": "done"}, readings=[_reading()], events=[_goal()], **kw)


def test_sm7_counts_the_kinds_that_reached_a_done_a_reading_stands_behind(tmp_path):
    _done_dept(tmp_path, "dref-a", "website")
    _done_dept(tmp_path, "dref-b", "default")
    make(tmp_path, "dref-c", kind="organic", state={"state": "done"})                       # done by hand: no claim, no reading
    m = M.sm7(_depts(tmp_path))
    assert (m["value"], m["of"], m["reached"], m["status"]) == (2, 3, ["website", "default"], "gap")
    assert m["gaps"] == ["no organic department reached a done a reading stands behind"]
    _done_dept(tmp_path, "dref-d", "organic")
    assert (M.sm7(_depts(tmp_path))["value"], M.sm7(_depts(tmp_path))["status"]) == (3, "met")


def test_sm7_a_done_whose_claim_has_no_reading_is_not_a_real_done(tmp_path):
    make(tmp_path, kind="website", state={"state": "done"}, events=[_goal()])
    assert M.sm7(_depts(tmp_path))["value"] == 0


# ---- SM-8 and SM-9 ---------------------------------------------------------------------------------------------------
def test_sm8_the_effort_is_the_asks_and_the_questions_before_it_and_the_median_is_judged(tmp_path):
    root = make(tmp_path, "dref-root", kind="root", board=[
        {"n": 1, "src": "Identity", "dst": ["Owner"], "msg_type": "inform", "payload": {"word": "question"}},
        {"n": 2, "src": "Identity", "dst": ["Owner"], "msg_type": "inform", "payload": {"word": "request"}}])
    for i, asks in enumerate(([_ask("stamped")], [_ask("stamped"), _ask("chosen", id="a-2")], [])):
        _done_dept(tmp_path, "dref-%d" % i, "website", dept={"parent": "dref-root"}, asks=asks)
    m = M.sm8(_depts(tmp_path))
    assert (m["value"], m["departments"], m["status"]) == (2, 3, "met")                 # 1+1, 2+1, 0+1 -> 2, 3, 1
    for i in range(3):
        _done_dept(tmp_path, "dref-x%d" % i, "website", dept={"parent": "dref-root"}, asks=[_ask("stamped")] * 4)
    m = M.sm8(_depts(tmp_path))
    assert (m["value"], m["status"]) == (4, "gap") and "median 4.0 is over 3" in m["gaps"][0]       # 1, 2, 3, 5, 5, 5
    assert root.exists()


def test_sm8_and_sm9_have_nothing_to_judge_before_a_department_is_done(tmp_path):
    make(tmp_path, state={"state": "running"})
    assert (M.sm8(_depts(tmp_path))["status"], M.sm9(_depts(tmp_path))["status"]) == ("not run", "not run")


def test_sm9_is_the_median_calls_and_usd_of_a_website_department_that_reached_done(tmp_path):
    for i, (calls, usd) in enumerate(((10, 0.5), (20, 1.0), (30, 1.5))):
        _done_dept(tmp_path, "dref-%d" % i, "website", runs=[_run("Plan", spend={"calls": calls - 1, "usd": usd - 0.1}),
                                                              _run("Audit", "r-2", True, spend={"calls": 1, "usd": 0.1})])
    _done_dept(tmp_path, "dref-d", "default", runs=[_run("Do", spend={"calls": 900, "usd": 90.0})])        # only websites are SM-9's
    m = M.sm9(_depts(tmp_path))
    assert (m["value"], m["departments"], m["status"]) == ({"calls": 20, "usd": 1.0}, 3, "met")
    _done_dept(tmp_path, "dref-e", "website", runs=[_run("Plan", spend={"calls": 100, "usd": 9.0})])
    _done_dept(tmp_path, "dref-f", "website", runs=[_run("Plan", spend={"calls": 100, "usd": 9.0})])
    _done_dept(tmp_path, "dref-g", "website", runs=[_run("Plan", spend={"calls": 100, "usd": 9.0})])
    m = M.sm9(_depts(tmp_path))
    assert m["status"] == "gap" and "against 40 and 3" in m["gaps"][0]


# ---- SM-11 -----------------------------------------------------------------------------------------------------------
def test_sm11_a_run_over_its_envelope_a_shared_slot_or_a_start_while_another_run_is_open_is_flagged(tmp_path):
    t = "2026-10-27T10:00:%02d+05:30"
    runs = [_run("Plan", "r-1", slot="Plan@brief.v1", started=t % 0, ended=t % 5),
            _run("Write", "r-2", slot="Write@plan.v1", started=t % 3, ended=t % 9),                 # starts while Plan is open
            _run("Check", "r-3", slot="Check@pages.v1", started=t % 20, ended=t % 21, spend={"calls": 31, "usd": 0.1}),
            _run("Publish", "r-4", slot="Publish@build.v1", started=t % 30, ended=t % 31),
            _run("Publish", "r-5", slot="Publish@build.v1", started=t % 40, ended=t % 41)]           # the slot of r-4 again
    make(tmp_path, dept={"envelopes": {"Check": {"calls": 30, "usd": 6.0}}}, runs=runs)
    m = M.sm11(_depts(tmp_path))
    assert (m["runs"], m["flagged"], m["value"], m["status"]) == (5, 4, 0.8, "gap")
    said = " | ".join(m["gaps"])
    assert "Write (run r-2) started while Plan was open" in said and "Check (run r-3) overspent its envelope" in said
    assert "Publish (run r-5) shares slot Publish@build.v1" in said


def test_sm11_runs_one_after_another_inside_their_envelopes_are_clean(tmp_path):
    t = "2026-10-27T10:00:%02d+05:30"
    make(tmp_path, dept={"envelopes": {"Plan": {"calls": 30, "usd": 6.0}}},
         runs=[_run("Plan", "r-1", slot="a", started=t % 0, ended=t % 0, spend={"calls": 3, "usd": 0.1}),
               _run("Plan", "r-2", slot="b", started=t % 1, ended=t % 2, spend={"calls": 3, "usd": 0.1}),
               _run("Identity", "r-3", True, slot="Identity@board.n1")])
    m = M.sm11(_depts(tmp_path))
    assert (m["runs"], m["flagged"], m["value"], m["status"]) == (2, 0, 0.0, "met")


def test_sm11_a_run_that_answers_a_question_inside_the_run_that_asked_it_is_no_clash(tmp_path):
    t = "2026-10-27T10:00:%02d+05:30"
    make(tmp_path, dept={"envelopes": {"Plan": {"calls": 30, "usd": 6.0}}},
         runs=[_run("Write", "r-1", slot="Write@plan.v1", started=t % 0, ended=t % 9),
               _run("Plan", "r-2", slot="Plan@board.n3", started=t % 3, ended=t % 4, for_run="r-1", spend={"calls": 1, "usd": 0.01}),
               _run("Check", "r-3", slot="Check@pages.v1", started=t % 5, ended=t % 6)])        # a run that is no answer, started inside r-1
    m = M.sm11(_depts(tmp_path))
    assert (m["runs"], m["flagged"]) == (3, 1) and "Check (run r-3) started while Write was open" in " | ".join(m["gaps"])
    assert "r-2" not in " | ".join(m["gaps"])


def test_sm11_an_answering_run_is_no_clash_only_inside_the_run_that_asked_it(tmp_path):
    """Decision W3B-1: a run that names the run it answers for and ends after it, or is still open when it is over, is a clash."""
    t = "2026-10-27T10:00:%02d+05:30"
    make(tmp_path, dept={"envelopes": {"Plan": {"calls": 30, "usd": 6.0}}},
         runs=[_run("Write", "r-1", slot="Write@plan.v1", started=t % 0, ended=t % 5),
               _run("Plan", "r-2", slot="Plan@board.n3", started=t % 3, ended=t % 4, for_run="r-1", spend={"calls": 1, "usd": 0.01}),
               _run("Plan", "r-3", slot="Plan@board.n4", started=t % 4, ended=t % 9, for_run="r-1", spend={"calls": 1, "usd": 0.01})])
    m = M.sm11(_depts(tmp_path))
    said = " | ".join(m["gaps"])
    assert (m["runs"], m["flagged"]) == (3, 1) and "Plan (run r-3) started while Write was open" in said and "r-2" not in said


# ---- SM-12 -----------------------------------------------------------------------------------------------------------
def test_sm12_reads_the_marks_of_the_decision_log_once_each(tmp_path):
    log = tmp_path / "design"
    _w(log / "PRD-FIVE-FUNCTIONS-DECISIONS.md", "\n".join([
        "| Id | The question | Taken | Steps it opens |", "|---|---|---|---|",
        "| MK-1 | q | five points | M3.3 |", "| MK-2 | q | each item has a level | M3.2 |", "| Q1 | q | Identity only | M3.6 |",
        "| Id | Settled by the UI port | Where |", "| MK-1 | Superseded. | J2UI |"]))
    m = M.sm12(tmp_path)
    assert (m["marked"], m["of"], m["value"], m["status"]) == (2, 2, 100.0, "met")
    _w(log / "PRD-FIVE-FUNCTIONS-DECISIONS.md", "| MK-1 | q |  | M3.3 |\n| MK-2 | q | taken | M3.2 |\n")
    m = M.sm12(tmp_path)
    assert (m["value"], m["status"], m["gaps"]) == (50.0, "gap", ["MK-1 has no decision"])
    assert M.sm12(tmp_path / "nowhere")["status"] == "not run"


def test_sm12_on_the_real_decision_log_every_mark_row_carries_what_was_taken():
    m = M.sm12(HERE)
    assert (m["of"], m["marked"], m["status"]) == (10, 10, "met")


# ---- SM-2 and the junit file -----------------------------------------------------------------------------------------
def test_sm2_a_lane_that_ran_no_test_is_a_gap_and_the_gate_must_name_the_department_lanes():
    m = M.sm2([{"lane": "test_j2.py", "tests": 64}, {"lane": "test_x.py", "tests": 0}], "pytest test_j2.py test_j2_api.py test_j1.py")
    assert (m["value"], m["gaps"], m["status"]) == (1, ["test_x.py ran 0 tests"], "gap")
    m = M.sm2([{"lane": "test_j2.py", "tests": 64}], "pytest test_j2.py test_j1.py")
    assert m["gaps"] == ["qa/walks/suites.sh does not run test_j2_api.py"]


def test_sm2_with_no_lane_run_it_is_not_run_and_the_real_gate_names_the_three_department_lanes_and_this_one():
    assert M.sm2([], None)["status"] == "not run"
    gate = (HERE / "qa" / "walks" / "suites.sh").read_text()
    assert M.sm2([{"lane": "x", "tests": 1}], gate)["value"] == 0
    assert "test_j2_metrics.py" in gate and "qa/j2_metrics.py --check" in gate, "the proof runs in the gate"


def test_the_junit_file_gives_the_tests_run_the_failures_the_skips_and_what_a_test_recorded(tmp_path):
    xml = tmp_path / "junit.xml"
    xml.write_text("""<?xml version="1.0"?><testsuites><testsuite name="pytest" tests="4">
      <testcase classname="a" name="ok"><properties><property name="sm10_append_p95_ms" value="1.234"/></properties></testcase>
      <testcase classname="a" name="bad"><failure message="x">trace</failure></testcase>
      <testcase classname="a" name="err"><error message="x">trace</error></testcase>
      <testcase classname="a" name="skip"><skipped message="s"/></testcase></testsuite></testsuites>""")
    assert M.parse_junit(xml) == {"tests": 3, "failed": 2, "skipped": 1, "props": {"sm10_append_p95_ms": "1.234"}}
    assert M.parse_junit(tmp_path / "none.xml")["tests"] == 0
    assert M.sm10(1.234)["status"] == "recorded" and M.sm10(None)["status"] == "pending"


# ---- SM-13: the rows (the entries, refuse mode and the ownership rows are Z2's, below) ------------------------------
def test_sm13_the_rows_the_interface_wrote_for_a_refused_write_and_a_kept_record_are_counted(tmp_path):
    ok = _run("Identity", "r-1", True, what="set its rules within the parent's")
    no = _run("Identity", "r-2", True, what="refused a write that does not fit the interface: asks: $.kind: is not one of publish, setup")
    kept = _run("Priority", "r-3", True, what="kept a record that does not fit the interface: department: $.control: is not one of granted")
    make(tmp_path, runs=[ok, no, kept])
    m = M.sm13(_depts(tmp_path))
    assert (m["value"], m["refused_rows"], m["kept_rows"], m["status"]) == (2, 1, 1, "gap")
    assert "asks: $.kind: is not one of publish, setup" in m["gaps"][0]
    make(tmp_path / "clean", runs=[ok])
    assert M.sm13(_depts(tmp_path / "clean"))["value"] == 0


# ---- SM-14: the journey rows, read from the status files ------------------------------------------------------------
def _journey(ui, jid, states, backlog=(), stale=False):
    """journeys/<id>.json and journeys/status/<id>.json, the status file carrying the hash of the journey."""
    import hashlib
    journey = {"id": jid, "title": jid, "backlog": [{"id": b, "row": r} for r, b in backlog]}
    _w(Path(ui) / "journeys" / (jid + ".json"), journey)
    sha = hashlib.sha256(json.dumps(journey, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _w(Path(ui) / "journeys" / "status" / (jid + ".json"), {
        "schema_version": 1, "id": jid, "definitions_sha": "0" * 64 if stale else sha, "state": "partly", "counts": {}, "tests": {},
        "rows": {k: {"state": v} for k, v in states.items()}})


def test_sm14_with_no_status_file_it_is_not_run_and_does_not_fail(tmp_path):
    m = M.sm14(tmp_path)
    assert (m["status"], m["value"]) == ("not run", None) and "J1 (no status file)" in m["note"]


def test_sm14_counts_the_unproven_failing_and_fault_rows_and_lists_the_partly_and_wanted_with_their_backlog_id(tmp_path):
    _journey(tmp_path, "J1", {"step:1": "proven", "step:2": "unproven", "edge:J1.1": "failing", "edge:J1.2": "partly",
                              "step:3": "wanted", "edge:J1.3": "declared"}, backlog=[("edge:J1.2", "BL-3"), ("step:3", "BL-9")])
    _journey(tmp_path, "J2", {"step:1": "fault", "step:2": "proven"})
    m = M.sm14(tmp_path)
    assert (m["value"], m["status"], m["rows"]) == (3, "gap", 8)
    assert sorted(m["gaps"]) == ["J1 edge:J1.1 is failing", "J1 step:2 is unproven", "J2 step:1 is fault"]
    assert sorted(m["waiting"]) == ["J1 edge:J1.2 is partly (BL-3)", "J1 step:3 is wanted (BL-9)"]
    assert "J3 (no status file)" in m["note"] and "J4 (no status file)" in m["note"]


def test_sm14_a_waiting_row_names_its_backlog_id_from_the_backlog_list_or_from_the_row_whatever_key_the_status_uses(tmp_path):
    journey = {"id": "J2", "title": "J2", "backlog": [{"id": "BL-1", "row": "edge:J2.8"}],
               "steps": [{"n": "8", "backlog": "BL-5"}], "edges": [{"id": "J2.8"}, {"id": "J2.9"}]}
    _w(tmp_path / "journeys" / "J2.json", journey)
    import hashlib
    sha = hashlib.sha256(json.dumps(journey, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _w(tmp_path / "journeys" / "status" / "J2.json", {"id": "J2", "definitions_sha": sha, "rows": {
        "J2:edge:J2.8": {"state": "wanted"}, "step:8": {"state": "partly"}, "edge:J2.9": {"state": "wanted"}}})
    assert sorted(M.sm14(tmp_path)["waiting"]) == ["J2 J2:edge:J2.8 is wanted (BL-1)", "J2 edge:J2.9 is wanted (no backlog id named)",
                                                   "J2 step:8 is partly (BL-5)"]


def test_sm14_a_status_file_whose_hash_is_stale_is_not_run_not_counted(tmp_path):
    _journey(tmp_path, "J1", {"step:1": "unproven"}, stale=True)
    _journey(tmp_path, "J2", {"step:1": "proven"})
    m = M.sm14(tmp_path)
    assert (m["value"], m["status"], m["not_run"][0]) == (0, "met", "J1 (stale)")


def test_sm14_all_proven_is_met(tmp_path):
    for jid in M.JOURNEYS:
        _journey(tmp_path, jid, {"step:1": "proven", "edge:%s.1" % jid: "proven"})
    m = M.sm14(tmp_path)
    assert (m["value"], m["status"], m["rows"], m["not_run"]) == (0, "met", 8, [])


# ---- the report and the gate's line ----------------------------------------------------------------------------------
def test_the_report_has_every_metric_in_order_says_what_stays_pending_and_ends_on_the_line_the_gate_shows(tmp_path):
    make(tmp_path, state={"state": "running"}, runs=[_run("Plan")])
    rep = M.build(_depts(tmp_path), [], ui=HERE)
    assert [m["id"] for m in rep["metrics"]] == ["SM-%d" % n for n in range(1, 15)]
    assert rep["schema"] == "j2.metrics.v1" and rep["departments"] == 1
    assert {"nine live Beta runs", "the Human Simulation walk"} <= {p["what"] for p in rep["pending"]}
    assert next(p for p in rep["pending"] if p["what"] == "the Human Simulation walk")["why"].count("narrowest-viewer") == 1
    by = {m["id"]: m["status"] for m in rep["metrics"]}
    assert by["SM-5"] == "pending" and by["SM-10"] == "pending" and by["SM-14"] in ("not run", "met", "gap")
    text = M.render(rep)
    assert text.splitlines()[-1].startswith("proof run: SM-1 0, SM-3 1, SM-4 0, SM-6 0, SM-13 0;") and "Pending under C2" in text


REFUSED_ROW = "refused a write that does not fit the interface: asks: $.kind: is not one of publish, setup"
KEPT_ROW = "kept a record that does not fit the interface: " + "department: $.control: is not one of granted"


@pytest.mark.parametrize("make_it, check, strict", [
    (lambda root: make(root, readings=[], events=[_goal()]), 1, 1),                                  # a claim with no reading
    (lambda root: make(root, state={"state": "waiting"}, asks=[]), 0, 1),                            # a dead end: named, not the gate's
    (lambda root: make(root, board=[_post(1, "Audit", ["Owner"])]), 1, 1),                           # a post to the owner from Audit
    (lambda root: make(root, runs=[_run("Gone")], state={"state": "running"}), 1, 1),                # an engine on no line
    (lambda root: make(root, runs=[_run("Identity", "r-1", True, what=REFUSED_ROW)]), 1, 1),         # SM-13: a write the interface refused
    (lambda root: make(root, runs=[_run("Priority", "r-1", True, what=KEPT_ROW)]), 1, 1),            # SM-13: a record it kept with a fault
    (lambda root: make(root, runs=[_run("Identity", "r-1", True, what="set its rules within the parent's")]), 0, 1),   # a clean row: only SM-7 gaps
])
def test_check_fails_on_a_gap_in_sm_1_3_4_13_and_strict_on_any_gap(tmp_path, capsys, make_it, check, strict):
    make_it(tmp_path)
    assert M.main(["--records", str(tmp_path), "--check"]) == check
    assert M.main(["--records", str(tmp_path), "--strict"]) == strict
    assert M.main(["--records", str(tmp_path)]) == 0, "without --check the report only reports"
    assert "proof run: SM-1" in capsys.readouterr().out


def test_the_gates_line_is_sm_1_2_3_4_and_13_and_a_record_with_nothing_in_it_has_no_hard_gap():
    assert set(M.HARD) == {"SM-1", "SM-2", "SM-3", "SM-4", "SM-13"}
    rep = M.build(M.find_departments(Path("/nonexistent-records-home")), [], ui=HERE)
    assert rep["hard_gaps"] == [] and rep["ok"]


def test_sm13_alone_makes_the_report_not_ok_and_names_it_on_the_last_line(tmp_path):
    make(tmp_path, runs=[_run("Identity", "r-1", True, what=REFUSED_ROW)])
    rep = M.build(_depts(tmp_path), [], ui=HERE)
    assert rep["hard_gaps"] == ["SM-13"] and "SM-13" in rep["gaps"] and rep["ok"] is False
    assert M.render(rep).splitlines()[-1].endswith("NOT OK: SM-13")


def _lane(name="test_j2.py", rc=0, tests=10, failed=0):
    return {"lane": name, "rc": rc, "tests": tests, "failed": failed, "skipped": 0, "seconds": 1.0,
            "summary": "%d failed, %d passed" % (failed, tests - failed) if failed else "%d passed" % tests,
            "props": {}, "refused_entries": 0, "refused_rows": [], "mode": "refuse"}


def test_a_lane_that_failed_makes_the_report_not_ok_though_it_ran_tests_and_no_metric_gaps(tmp_path):
    """The one thing that can fail the gate with every metric at its target: a scenario lane that ran its tests and had some fail
    (rc 1, tests above 0, so SM-2 has no gap). Without lane_faults in `ok` this passed."""
    make(tmp_path, runs=[_run("Plan")], state={"state": "running"}, dept={"workflows": LINE})
    ok = M.build(_depts(tmp_path), [_lane("test_j2.py"), _lane("test_j2_api.py")], ui=HERE)
    assert ok["ok"] is True and ok["lane_faults"] == [] and ok["hard_gaps"] == []
    rep = M.build(_depts(tmp_path), [_lane("test_j2.py", rc=1, tests=10, failed=2), _lane("test_j2_api.py")], ui=HERE)
    by = {m["id"]: m["status"] for m in rep["metrics"]}
    assert by["SM-2"] == "met" and all(by[i] != "gap" for i in M.HARD), "no metric is in gap: only the lane failed"
    assert rep["hard_gaps"] == [] and rep["ok"] is False
    assert rep["lane_faults"] == ["lane test_j2.py: 2 failed, 8 passed"]
    last = M.render(rep).splitlines()[-1]
    assert last.endswith("NOT OK: lane test_j2.py: 2 failed, 8 passed") and "FAILED lane test_j2.py: 2 failed, 8 passed" in M.render(rep)


def test_a_lane_that_timed_out_is_a_failed_lane_too(tmp_path):
    rep = M.build([], [dict(_lane("test_j2.py", rc=-1, tests=4), summary="timed out after 1500 s")], ui=HERE)
    assert rep["ok"] is False and rep["lane_faults"] == ["lane test_j2.py: timed out after 1500 s"]


def test_a_clean_record_of_the_three_kinds_passes_strict_and_the_json_and_out_file_agree(tmp_path, capsys):
    for i, kind in enumerate(M.KINDS_TO_PROVE):
        _done_dept(tmp_path, "dref-%d" % i, kind, runs=[_run("Plan", "r-%d" % i)], dept={"workflows": LINE})
    out = tmp_path / "report.json"
    assert M.main(["--records", str(tmp_path), "--strict", "--json", "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(out.read_text()) and printed["ok"] and printed["gaps"] == []
    assert {m["id"]: m["status"] for m in printed["metrics"]}["SM-7"] == "met"


def test_a_lane_that_cannot_run_is_a_failed_lane_with_no_tests_and_the_report_is_not_ok(tmp_path):
    lanes = M.run_suite(["test_no_such_file_anywhere.py"], tmp_path, workers=1)
    assert lanes[0]["rc"] != 0 and lanes[0]["tests"] == 0
    rep = M.build([], lanes, ui=HERE)
    assert rep["ok"] is False and rep["lane_faults"] and "test_no_such_file_anywhere.py ran 0 tests" in rep["metrics"][1]["gaps"]


def test_the_ledger_figure_a_lane_recorded_is_read_into_sm10_and_gates_nothing(tmp_path):
    lane = {"lane": "test_j2_ledger.py::t", "rc": 0, "tests": 1, "failed": 0, "skipped": 0, "seconds": 9.0, "summary": "1 passed",
            "props": {"sm10_append_p95_ms": "7.5"}, "refused_entries": 0, "refused_rows": [], "mode": "refuse"}
    rep = M.build([], [lane], ui=HERE)
    m = next(m for m in rep["metrics"] if m["id"] == "SM-10")
    assert (m["value"], m["status"]) == (7.5, "recorded") and "over the target" in m["note"]
    assert rep["ok"] and "SM-10" not in rep["gaps"]


def test_the_text_report_says_how_each_metric_was_read_and_lists_the_waiting_journey_rows(tmp_path):
    _journey(tmp_path, "J1", {"step:1": "partly"}, backlog=[("step:1", "BL-2b")])
    rep = M.build([], [], ui=tmp_path)
    text = M.render(rep)
    assert "how: matches each goal.reached to the reading of the version it cites" in text
    assert "waits: J1 step:1 is partly (BL-2b)" in text
    assert "SM-5  pending" in text and "SM-14 met" in text


def test_the_text_report_names_every_dead_end_not_a_count_of_them_and_says_what_is_carried_to_w3_proof(tmp_path, capsys):
    """Nine departments stand unread with no ask (the proof run's own finding). 'And 1 more' hid one of them, and the gate
    shows only the last line, so the text report lists every gap of a metric that counts departments; the runs of SM-3 can
    run to hundreds and keep their cap, and --out names them all."""
    for i in range(9):
        make(tmp_path, "dref-%d" % i, group="t%d" % i, state={"state": "unread"}, asks=[])
    make(tmp_path, "dref-live", group="live", state={"state": "running"}, runs=[_run("Gone", "r-%d" % i) for i in range(12)])
    out = tmp_path / "report.json"
    assert M.main(["--records", str(tmp_path), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    sm6 = [ln for ln in text.splitlines() if ln.startswith("        gap: ") and "stands unread" in ln]
    assert len(sm6) == 9 and len({ln.split(" / ")[0] for ln in sm6}) == 9, "each of the nine is a line of its own"
    assert "more" not in text.split("SM-7")[0].split("SM-6")[1], "no 'and N more' under SM-6"
    assert text.count("ran Gone (run") == 8 and "and 4 more (the report file, --out, names every one)" in text, "a long list keeps its cap"
    assert "carried to W3-PROOF: 9 of these stand unread" in text and "no ask is filed" in text
    assert text.splitlines()[-1].startswith("proof run: SM-1 0, SM-3 12, SM-4 0, SM-6 9, SM-13 0;")
    rep = json.loads(out.read_text())
    by = {m["id"]: m for m in rep["metrics"]}
    assert len(by["SM-6"]["gaps"]) == 9 and by["SM-6"]["unread"] == 9 and len(by["SM-3"]["gaps"]) == 12, "the file names them all"
    make(tmp_path / "other", "dref-w", state={"state": "waiting"}, asks=[])
    assert M.sm6(_depts(tmp_path / "other"))["carried"] == [], "a dead end that is not an unread cycle carries nothing"


def test_the_gate_writes_the_whole_report_to_a_file_and_points_at_it_when_a_gap_is_named():
    gate = (HERE / "qa" / "walks" / "suites.sh").read_text()
    line = next(ln for ln in gate.splitlines() if "qa/j2_metrics.py --check" in ln)
    assert "--out /tmp/sutra-suite-metrics.json" in line and "/tmp/sutra-suite-metrics.txt" in line
    assert 'grep -q "gaps named"' in gate and "whole report is /tmp/sutra-suite-metrics.json" in gate


def test_the_suite_runs_on_a_kept_home_or_a_temporary_one_that_is_removed_after(tmp_path, monkeypatch, capsys):
    made, real = [], M.tempfile.mkdtemp
    monkeypatch.setattr(M.tempfile, "mkdtemp", lambda **kw: made.append(real(dir=str(tmp_path), **kw)) or made[-1])
    assert M.main(["--files", "test_j2_api.py", "--workers", "1", "--check", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["lanes"][0]["lane"] == "test_j2_api.py" and rep["lanes"][0]["tests"] > 0 and "kept" not in rep
    assert rep["departments"] > 0 and made and not Path(made[0]).exists(), "a temporary home is removed"
    keep = tmp_path / "kept"
    assert M.main(["--files", "test_j2_api.py", "--keep", str(keep), "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["kept"] == str(keep) and len(M.find_departments(keep)) == rep["departments"] > 0, "a kept home stays to be read again"
    again = M.build(M.find_departments(keep), [], ui=HERE)
    assert [(m["id"], m["value"]) for m in again["metrics"] if m["id"] in ("SM-1", "SM-3", "SM-4")] == [("SM-1", 0), ("SM-3", 0), ("SM-4", 0)]


# ---- Z2 (M10.5): schema conformance in refuse mode -------------------------------------------------------------------
OWN = "department: $.goal: is Identity's, and Priority wrote it"


def test_z2_a_save_with_by_for_a_key_another_layer_owns_is_listed_as_an_ownership_row(tmp_path):
    make(tmp_path, runs=[
        _run("Priority", "r-1", True, what="kept a record that does not fit the interface: " + OWN),
        _run("Adaptation", "r-2", True, what="refused a write that does not fit the interface: department: $.workflows: is Root's, and Adaptation wrote it"),
        _run("Priority", "r-3", True, what="refused a write that does not fit the interface: priority.price: $.answer: is not one of accept"),
        _run("Plan", "r-4", what="its text names $.goal: is Identity's, and Priority wrote it")])             # not a row of the interface's
    own = M.ownership_rows(_depts(tmp_path))
    assert [(o["key"], o["owner"], o["writer"], o["kept"]) for o in own] == [("goal", "Identity", "Priority", True),
                                                                           ("workflows", "Root", "Adaptation", False)]
    m = M.sm13(_depts(tmp_path), [], "refuse")
    assert m["status"] == "gap" and len(m["ownership"]) == 2
    assert any(g.startswith("ownership: Priority wrote goal, which is Identity's") for g in m["gaps"])


def test_z2_an_ownership_fault_the_processes_dumped_is_listed_once_even_when_a_row_shows_it_too(tmp_path):
    make(tmp_path, runs=[_run("Priority", "r-1", True, what="kept a record that does not fit the interface: " + OWN)])
    dumped = {"test": "test_x.py::t", "ref": "dref-a", "kept": True, "faults": ["$.goal: is Identity's, and Priority wrote it"]}
    other = {"test": "test_y.py::t", "ref": None, "kept": False, "faults": ["$.rules: is Identity's, and Audit wrote it", "$.x: is not a field"]}
    own = M.ownership_rows(_depts(tmp_path), [{"lane": "test_x.py", "refused_rows": [dumped, other]}])
    assert [(o["key"], o["writer"]) for o in own] == [("goal", "Priority"), ("rules", "Audit")]
    assert own[1]["dept"] == "test_y.py::t (no department)"


def test_z2_sm13_is_the_larger_of_the_rows_and_the_entries_so_a_fault_is_counted_once(tmp_path):
    row = _run("Priority", "r-1", True, what="refused a write that does not fit the interface: asks: $.kind: is wrong")
    make(tmp_path, runs=[row])
    one = [{"lane": "test_j2.py", "refused_entries": 1}]
    assert M.sm13(_depts(tmp_path), one, "refuse")["value"] == 1, "a fault with a department leaves a row and an entry"
    assert M.sm13(_depts(tmp_path), [{"lane": "x", "refused_entries": 3}], "refuse")["value"] == 3, "one with none leaves an entry only"
    gone = M.sm13([], [{"lane": "test_j2.py", "refused_entries": 2}], "refuse")
    assert gone["value"] == 2 and "test_j2.py: 2 entries in S.REFUSED" in gone["gaps"]
    assert M.sm13([], [{"lane": "test_j2.py", "refused_entries": 0}], "refuse")["status"] == "met"


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """The module as the suite's processes load it (-p j2_metrics), with an interface of its own to count on."""
    fake = types.SimpleNamespace(MODE="warn", REFUSED={"count": 0, "rows": []})
    monkeypatch.setattr(M, "_schema", lambda: fake)
    monkeypatch.setattr(M, "_STATE", {"entries": 0, "rows": []})
    monkeypatch.setenv("J2_METRICS_DUMP", str(tmp_path / "dump.json"))
    monkeypatch.setenv("J2_METRICS_LANE", "test_x.py")
    monkeypatch.setenv("J2_METRICS_MODE", "refuse")
    return fake, types.SimpleNamespace(nodeid="test_x.py::test_one")


def _teardown(item):
    gen = M.pytest_runtest_teardown(item, None)
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)


def test_z2_the_plugin_puts_the_interface_in_refuse_mode_for_the_test_and_counts_what_the_test_left_on_refused(plugin, tmp_path):
    fake, item = plugin
    M.pytest_runtest_setup(item)
    M.pytest_runtest_call(item)
    assert fake.MODE == "refuse"
    fake.REFUSED["count"] += 2
    fake.REFUSED["rows"] += [{"name": "asks", "faults": ["$.kind: is wrong"]}, {"name": "department", "faults": ["x"]}]
    _teardown(item)
    M.pytest_runtest_setup(item)                                                    # a second test that leaves nothing
    _teardown(item)
    M.pytest_sessionfinish(None, 0)
    dump = json.loads((tmp_path / "dump.json").read_text())
    assert (dump["lane"], dump["mode"], dump["entries"]) == ("test_x.py", "refuse", 2)
    assert [r["name"] for r in dump["rows"]] == ["asks", "department"] and dump["rows"][0]["test"] == "test_x.py::test_one"


def test_z2_a_fault_taken_off_by_expect_refused_is_not_counted_and_app_mode_leaves_the_constant_alone(plugin, monkeypatch):
    fake, item = plugin
    M.pytest_runtest_setup(item)
    fake.REFUSED["count"] += 1                       # what expect_refused() adds and takes off again before the test ends
    fake.REFUSED["count"] -= 1
    _teardown(item)
    assert M._STATE["entries"] == 0
    monkeypatch.setenv("J2_METRICS_MODE", "app")
    M.pytest_runtest_call(item)
    assert fake.MODE == "warn"


def test_z2_without_the_dump_variable_the_plugin_does_nothing(plugin, monkeypatch, tmp_path):
    fake, item = plugin
    monkeypatch.delenv("J2_METRICS_DUMP")
    M.pytest_runtest_call(item)
    fake.REFUSED["count"] += 1
    _teardown(item)
    M.pytest_sessionfinish(None, 0)
    assert fake.MODE == "warn" and M._STATE["entries"] == 0 and not (tmp_path / "dump.json").exists()


def test_z2_the_app_constant_is_read_from_the_source_and_the_report_says_both_modes(tmp_path):
    _w(tmp_path / "layer_schema.py", "X = 1\nMODE = 'refuse'          # a code constant\nOWNERSHIP_MODE = 'warn'\n")
    assert M.app_mode(tmp_path) == "refuse" and M.app_mode(tmp_path / "nowhere") == "unknown"
    assert M.app_mode(HERE) in ("warn", "refuse")
    rep = M.build([], [], "refuse", ui=HERE)
    assert rep["mode"] == {"run": "refuse", "app": M.app_mode(HERE)}


def test_z2_the_scenario_suite_in_refuse_mode_leaves_no_refused_write_and_no_ownership_row(tmp_path):
    """The done check of M10.5: SM-13 is 0, counted over the records the suite kept and the entries its processes dumped.
    The lanes here are the proof scenarios and the API lane; the gate's own line runs the whole suite."""
    lanes = M.run_suite(["test_j2_api.py", "test_j2_metrics.py::TestProofScenarios"], tmp_path, "refuse", workers=2)
    assert [(ln["rc"], ln["failed"]) for ln in lanes] == [(0, 0), (0, 0)] and all(ln["tests"] > 0 for ln in lanes), lanes
    assert [ln["mode"] for ln in lanes] == ["refuse", "refuse"], "the processes ran with the plugin, in refuse mode"
    rep = M.build(M.find_departments(tmp_path), lanes, "refuse", ui=HERE)
    by = {m["id"]: m for m in rep["metrics"]}
    assert by["SM-13"]["value"] == 0 and by["SM-13"]["ownership"] == [] and by["SM-13"]["status"] == "met"
    assert (by["SM-1"]["value"], by["SM-3"]["value"], by["SM-4"]["value"]) == (0, 0, 0)
    assert by["SM-1"]["claims"] == 3 and by["SM-7"]["value"] == 3 and by["SM-7"]["status"] == "met", "all three kinds reach a real done"
    assert rep["ok"] and rep["lane_faults"] == []
