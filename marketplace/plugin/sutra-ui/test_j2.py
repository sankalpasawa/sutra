"""Behavioral contract for J2: the five functions work toward the identity's goal (the department page, section J2).

Each test is one row of that section: a step of the happy path, or an edge. The departments here are born the way a
person makes them (founded, asked for, set up by Root), so what is tested is the lifecycle a real department lives,
on its real board, and not a record written by hand.
"""
import importlib
import json
import re
import threading

import pytest

import layers

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]


@pytest.fixture
def j2(tmp_path, monkeypatch):
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
    """Audit's reader (M8.3), a function: it says every done-when item in the prompt is met, with its evidence."""
    items = json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])
    return {"items": [{"id": i["id"], "verdict": "met", "claim": "it holds", "evidence": "the work shows it"} for i in items], "findings": []}


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    """A department as a person makes one: found the organisation, say the words, Root sets it up."""
    W, _, _, founding = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


def _work(W, ref):
    return [r["engine"] for r in W.runs(ref) if not r.get("system")]


def _stamp_all(W, ref, approve=True, kind=None):
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and (kind is None or a["kind"] == kind)]:
        W.decide_ask(ref, a["id"], approve)
    W.run_until_idle(ref, limit=300)


def _said(R, ref):
    return [str((p["payload"] or {}).get("done") or (p["payload"] or {}).get("objective") or "") for p in R.board(ref)
            if p["src"] == "Identity" and "Owner" in p["dst"]]


# ---- the boundary -------------------------------------------------------------------------------------------------
def test_start_needs_the_switch_the_handover_and_a_department(j2, monkeypatch):
    W, _, J, _ = j2
    d, _ = W.create("dref-plain", "Plain", "A goal", kind="website")
    with pytest.raises(J.J2Error, match="J2_NOT_READY"):
        J.start(d["ref"])
    with pytest.raises(J.J2Error, match="NO_DEPARTMENT"):
        J.start("dref-nobody")
    monkeypatch.setenv("J2_FLOW_V1", "0")
    with pytest.raises(J.J2Error, match="J2_FLOW_DISABLED"):
        J.start(d["ref"])
    assert J.status(d["ref"])["enabled"] is False


def test_the_switch_is_on_unless_turned_off(j2, monkeypatch):
    _, _, J, _ = j2
    monkeypatch.delenv("J2_FLOW_V1", raising=False)
    assert J.enabled() is True
    for off in ("0", "false", "off"):
        monkeypatch.setenv("J2_FLOW_V1", off)
        assert J.enabled() is False


# ---- the happy path, steps 1 to 8 ---------------------------------------------------------------------------------
def test_d1_the_cycle_starts_at_the_handover_and_nobody_presses_start(j2):
    """A department that waits for a Start button, or runs outside its cycle, must fail."""
    W, _, J, _ = j2
    ref = _born(j2, settle=False)
    st = J.status(ref)
    assert st["cycle_id"] and st["state"] != "not_started"
    assert J.start(ref)["cycle_id"] == st["cycle_id"]            # pressing Start changes nothing


def test_steps_1_to_5_a_library_kind_is_proposed_granted_checked_and_registered(j2):
    """Skipping the proposal, the grant or Root's registration must fail."""
    W, R, J, _ = j2
    ref = _born(j2)
    acts = _actions(J, ref)
    order = ["identity.assessed", "proposal.requested", "proposal.created", "proposal.granted", "workflow.validated", "workflow.registered"]
    assert acts[:6] == order
    assert [e["step"] for e in J.events(ref)[:6]] == [1, 2, 2, 3, 5, 5]
    created = next(e for e in J.events(ref) if e["action"] == "proposal.created")
    assert created["payload"] == {"source": "library", "workflow": LINE, "hop": 1}
    # the exchange is on the department's one board, on its own edges
    board = [(p["src"], p["dst"][0], p["msg_type"]) for p in R.board(ref) if (p["payload"] or {}).get("word") == "line"]
    assert board[:3] == [("Identity", "Adaptation", "request"), ("Adaptation", "Priority", "propose"), ("Priority", "Adaptation", "accept-proposal")]
    # registered on the department's record, as a version of its own
    [reg] = W.dept(ref)["workflows"]
    assert {k: reg[k] for k in ("version", "engines", "source", "by")} == {"version": 1, "engines": LINE, "source": "library", "by": "Root"}
    assert reg["registered"] and reg["deliverable"] == "Live site" and reg["left_out"] == [] and reg["checks"], "A1.14: the record keeps what it was held to"
    assert J.status(ref)["workflow"] == LINE
    assert any("The plan is set: Plan -> Write -> Check -> Publish" in s for s in _said(R, ref))
    # the tell says who said yes in the owner's words (PRD M1.7): Priority said yes to it, never that it granted it
    assert any("Priority said yes to it and it passed Root's check" in s for s in _said(R, ref))
    assert not [s for s in _said(R, ref) if "grant" in s.lower()]


def test_d2_no_workflow_runs_before_root_registers_it(j2):
    """Letting the line start on the Brief, as it did before J2, must fail."""
    W, _, J, _ = j2
    ref = _born(j2)
    events = J.events(ref)
    registered = next(e["seq"] for e in events if e["action"] == "workflow.registered")
    started = [e["seq"] for e in events if e["action"] == "run.started"]
    assert started and min(started) > registered
    assert _work(W, ref)[:3] == ["Plan", "Write", "Check"]


def test_step_2_with_no_template_adaptation_shapes_the_line_and_the_owner_stamps_nothing(j2):
    """Asking the owner to stamp the line, or stalling at step 2, must fail (S-18: no ask unless a rule says so)."""
    W, R, J, _ = j2
    ref = _born(j2, ORGANIC, "Lab Co")
    assert W.dept(ref)["kind"] == "organic"
    created = next(e for e in J.events(ref) if e["action"] == "proposal.created")
    assert created["payload"]["source"] == "shaped" and created["payload"]["workflow"] == ["Facts", "Site"]
    assert not [a for a in W.asks(ref) if a["kind"] == "line"]
    assert W.dept(ref)["engines"] == ["Facts", "Site"]
    assert J.status(ref)["step"] == 6
    assert _work(W, ref)[:1] == ["Facts"]


def test_steps_6_to_8_the_runs_the_audit_and_the_goal_are_on_the_ledger(j2, monkeypatch):
    """A ledger that stops at registration, or a goal reached twice, must fail. Audit's judge and its reader of the done-when
    items read with a model here: only a version the model read, item by item, can clear done-when (M0.3, M8.3)."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met})
    ref = _born(j2)
    _stamp_all(W, ref)                                           # the first publish: a born rule says ask
    acts = _actions(J, ref)
    for engine in LINE:
        ran = [e["action"] for e in J.events(ref) if e.get("workflow_ref") == engine]
        assert ran == ["slot.assigned", "run.started", "artifact.filed", "run.completed"], (engine, ran)
    assert acts[-2:] == ["audit.finding_filed", "goal.reached"]
    assert acts.count("goal.reached") == 1
    reached = J.events(ref)[-1]
    (reading,) = W.rows(ref, "readings.jsonl")
    assert reached["actor"] == "Identity" and reached["evidence_refs"] == [{"artifact": "Live site", "version": 1, "reading": reading["id"]}], \
        "Identity says it from the reading, and cites it (M8.4)"
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"]) == ("done", 8, True)
    assert len([s for s in _said(R, ref) if s.startswith("The goal is reached:")]) == 1
    # the loop is closed: more turns of the motor add nothing
    W.run_until_idle(ref, limit=100)
    assert _actions(J, ref).count("goal.reached") == 1


def test_step_7_a_finding_keeps_the_loop_open(j2, monkeypatch):
    """Declaring the goal reached over a finding Audit filed must fail."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": False, "findings": [{"page": "index", "claim": "The fees are invented", "severity": "high"}]}})
    ref = _born(j2)
    _stamp_all(W, ref, kind="publish")
    acts = _actions(J, ref)
    assert "audit.finding_filed" in acts and "goal.reached" not in acts
    # one event for the one reading, and it says what Audit found, never that it found nothing
    filed = [e for e in J.events(ref) if e["action"] == "audit.finding_filed"]
    assert [e["summary"] for e in filed] == ["The fees are invented"]
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"]) == ("pursuing", 8, False)
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["finding"]


def test_m0_3_an_offline_department_never_reaches_its_goal(j2):
    """An offline draft's empty list read as 'found nothing' must fail: no model read the version (M0.3)."""
    W, R, J, _ = j2
    ref = _born(j2)
    _stamp_all(W, ref)
    acts = _actions(J, ref)
    assert "goal.reached" not in acts and "audit.finding_filed" not in acts
    unread = next(e for e in J.events(ref) if e["action"] == "audit.not_read")
    assert (unread["step"], unread["actor"], unread["state"]) == (7, "Audit", "not_read")
    assert unread["evidence_refs"] == [{"artifact": "Live site", "version": 1}] and "no model" in unread["summary"]
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"]) == ("unread", 7, False)
    assert not [s for s in _said(R, ref) if s.startswith("The goal is reached")]
    filed = [r for r in R.step_rows(ref) if r["step"] == "audit.judge"]
    assert filed and filed[-1]["by"] == "offline draft"
    W.run_until_idle(ref, limit=100)
    assert "goal.reached" not in _actions(J, ref) and _actions(J, ref).count("audit.not_read") == 1


def test_m0_3_every_version_is_read_in_a_cycle_and_an_unsampled_v4_is_never_clean(j2, monkeypatch):
    """Audit's old sample skipped v4; a skipped judge's empty list read as 'found nothing' must fail."""
    W, R, J, _ = j2
    ref = _born(j2)
    _stamp_all(W, ref)
    assert R.audit_pick({"ref": ref, "inp": {"v": 4}}, None, None)["sample"] is True      # interim: every version, in a cycle
    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}})                  # a model there to read, unasked
    old = lambda ctx, step, item: {"sample": int(ctx["inp"]["v"]) <= 3 or int(ctx["inp"]["v"]) % 3 == 0, "v": int(ctx["inp"]["v"]), "pages": []}
    monkeypatch.setitem(layers.load("audit/v1").CODE, "audit_pick", old)         # Audit's code is looked up in its layer (A1.19)
    row = R.run_engine(ref, "Audit", {"v": 4}, "Audit@live-site.v4")
    assert row["status"] == "ok" and "not sampled" in row["what"]
    unread = [e for e in J.events(ref) if e["action"] == "audit.not_read"]
    assert [e["evidence_refs"][0]["version"] for e in unread] == [1, 4]
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["step"] == 7


class _Closed(BaseException):
    """The app closes mid-step: nothing in the runtime catches it, so the run is left running, as a closed app leaves it."""


def test_m0_3_a_judge_the_model_read_before_the_app_closed_still_counts_as_read(j2, monkeypatch):
    """A kept judge step read as 'how it was read is not on the record' (the department then waits at step 7 on a version
    the model did read) must fail: the kept step's how is the one its finished row says."""
    W, R, J, _ = j2
    asked = []
    _model(monkeypatch, R, {"audit.judge": lambda prompt: asked.append(1) or {"ok": True, "findings": []}, "audit.items": _items_met})
    ref = _born(j2)
    filing = layers.load("audit/v1").CODE["audit_file"]
    closes = [True]

    def audit_file(ctx, step, item):
        if closes.pop() if closes else False:
            raise _Closed()                              # after the judge's row, before Audit files what it read
        return filing(ctx, step, item)
    monkeypatch.setitem(layers.load("audit/v1").CODE, "audit_file", audit_file)
    with pytest.raises(_Closed):
        _stamp_all(W, ref)
    assert "goal.reached" not in _actions(J, ref) and len(asked) == 1
    W.recover()
    W.run_until_idle(ref, limit=300)
    acts = _actions(J, ref)
    assert "audit.not_read" not in acts and acts.count("goal.reached") == 1
    assert len(asked) == 1                               # the reading was kept, not asked for again
    judged = [r for r in R.step_rows(ref) if r["step"] == "audit.judge"]
    assert [r["by"] for r in judged] == ["model"]
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"]) == ("done", 8, True)


def test_m0_4_an_envelope_hold_is_one_event_and_one_ask_however_often_it_is_asked(j2, monkeypatch):
    """A hold the ledger never sees, or one written on every tick or on a panel read, must fail."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    W.set_envelope(ref, "Plan", calls=0)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["step"] == 6 and _work(W, ref) == []
    asked = {"n": 0}
    real = J.on_held

    def counted(*a, **k):
        asked["n"] += 1
        return real(*a, **k)
    monkeypatch.setattr(J, "on_held", counted)
    for _ in range(20):
        W.status(ref)                                                # a panel read: a peek
    assert asked["n"] == 0
    for _ in range(20):
        W.run_until_idle(ref, limit=1)                               # a motor tick
    assert asked["n"] >= 20 and _work(W, ref) == []
    held = [e for e in J.events(ref) if e["action"] == "envelope.held"]
    assert len(held) == 1
    assert (held[0]["actor"], held[0]["recipient"], held[0]["step"]) == ("Priority", "Plan", 6)
    assert held[0]["payload"]["slot"].startswith("Plan@") and held[0]["summary"] == "Plan is out of today's envelope"
    envelope = [a for a in W.asks(ref) if a["kind"] == "envelope"]
    assert len(envelope) == 1 and envelope[0]["escalated"] is True and envelope[0]["status"] == "pending"
    shown = [r for r in J.activity(ref) if r["action"] == "envelope.held"]
    assert len(shown) == 1                                           # once in Agent activity


# ---- the edges ------------------------------------------------------------------------------------------------------
def test_j2_1_identitys_question_takes_words_once_and_the_standard_is_read_again(j2):
    """A question that only takes a stamp, or an answer taken twice, must fail."""
    W, _, J, _ = j2
    d, _ = W.create("dref-gap", "Finance highlights", "Publish verified finance news", kind="website")
    d.update({"goal": "", "done": "", "events": [{"kind": "j2_ready", "route": "template"}],
              "rules": [{"id": "r1", "tag": "go", "line": "Work inside the record"}]})
    W.save_dept(d["ref"], d)
    ref = d["ref"]

    first = J.start(ref)
    assert first["state"] == "waiting" and J.start(ref) == first
    asks = [a for a in W.asks(ref) if a["kind"] == "j2_identity"]
    assert [a["text"] for a in asks] == ["What goal must this department achieve?"]
    assert J.holding(ref)                                          # nothing may run while Identity asks

    second = J.answer(ref, "Publish five verified finance highlights each morning")
    assert W.dept(ref)["goal"] == "Publish five verified finance highlights each morning"
    assert second["state"] == "waiting"                            # the next thing missing is asked, one at a time
    assert [a["text"] for a in W.asks(ref) if a["status"] == "pending"] == ["What evidence will prove this department is done?"]

    third = J.answer(ref, "Five highlights are filed with dated sources")
    assert third["state"] == "assessing" and third["open_ask"] is None
    assert W.dept(ref)["done"] == "Five highlights are filed with dated sources"
    assert W.dept(ref)["identity_revision"] == 3
    with pytest.raises(J.J2Error, match="NO_OPEN_QUESTION"):
        J.answer(ref, "again")
    assert _actions(J, ref) == ["identity.questioned", "ask.answered", "identity.questioned", "ask.answered"]


def test_j2_1_the_status_and_the_map_read_while_identitys_question_is_open(j2):
    """Identity's question names no engine (it is Identity's, and takes words, never a stamp). status() and map_view() read the
    engine of every pending ask, so the moment a department waited on the owner they raised KeyError: no engine card, no
    plan, and the J2 view's Map lost every workflow. A question that names no engine is Identity's wait and waits no engine."""
    W, _, J, _ = j2
    d, _ = W.create("dref-gap2", "Finance highlights", "", kind="website")
    ref = d["ref"]
    d.update({"goal": "", "done": "", "events": [{"kind": "j2_ready", "route": "template"}]})
    W.save_dept(ref, d)
    J.start(ref)
    q = next(a for a in W.asks(ref) if a["kind"] == "j2_identity" and a["status"] == "pending")
    assert "engine" not in q
    st = W.status(ref)
    assert [w["what"] for w in st["waits"]] == ["Identity"] and st["waits"][0]["why"] == q["text"]
    mv = W.map_view(ref)
    assert [e["name"] for e in mv["engines"]] == W.dept(ref)["engines"] and "planned" in mv
    assert all(e["state"] != "Waits" for e in mv["engines"]), "Identity's question is no engine's wait"
    W._put_ask(ref, {"id": "a-stamp", "kind": "publish", "engine": "Publish", "text": "Publish: go live", "status": "pending",
                     "created": W.now()})
    again = W.map_view(ref)
    assert {e["name"]: e["state"] for e in again["engines"]}["Publish"] == "Waits"
    assert sorted(w["what"] for w in W.status(ref)["waits"]) == ["Identity", "Publish"]


def test_j2_1_thin_first_words_are_asked_about_and_nothing_starts(j2, monkeypatch):
    W, R, J, _ = j2
    _model(monkeypatch, R, {"identity.take": lambda prompt: {"verdict": "go", "why": "", "thin": "New website" in prompt and "algebra" not in prompt,
                                                             "needs": [], "unsure": []}})
    d, _ = W.create("dref-thin", "Thin Website", None, kind="website")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    ref = d["ref"]
    J.start(ref)
    W.give_goal(ref, "New website")
    W.run_until_idle(ref, limit=200)
    assert _actions(J, ref) == ["identity.questioned"]
    assert J.status(ref)["state"] == "waiting" and _work(W, ref) == []

    W.owner_ask(ref, "It teaches algebra to Class 8 students")
    W.run_until_idle(ref, limit=300)
    assert "identity.assessed" in _actions(J, ref) and "workflow.registered" in _actions(J, ref)


def test_step_4_a_refusal_goes_to_identity_and_what_it_cannot_settle_is_one_ask(j2, monkeypatch):
    """A refusal that ends in silence, or two asks for one conflict, must fail (J2.2, J2.3)."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}})
    ref = _born(j2)
    acts = _actions(J, ref)
    assert acts[2:] == ["proposal.created", "proposal.refused", "conflict.raised", "identity.ruled", "ask.created"]
    assert _work(W, ref) == []                                     # the disputed work does not run
    asks = [a for a in W.asks(ref) if a["status"] == "pending"]
    assert [a["kind"] for a in asks] == ["conflict"]
    assert "Priority said no to the plan: no room in the envelope today" in asks[0]["text"]
    assert asks[0]["text"].endswith("Stamp to run it as proposed, or say no to drop it."), "the text says the buttons' words"
    assert J.status(ref)["state"] == "waiting"
    W.run_until_idle(ref, limit=100)
    assert len([a for a in W.asks(ref) if a["kind"] == "conflict"]) == 1

    _stamp_all(W, ref, kind="conflict")                            # one answer resumes the same cycle
    assert "workflow.registered" in _actions(J, ref)
    assert _work(W, ref)[:3] == ["Plan", "Write", "Check"]
    assert len({e["cycle_id"] for e in J.events(ref)}) == 1


def test_j2_3_the_owner_refuses_the_plan_and_nothing_runs(j2, monkeypatch):
    W, R, J, _ = j2
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}})
    ref = _born(j2)
    _stamp_all(W, ref, approve=False, kind="conflict")
    assert J.status(ref)["state"] == "blocked"
    assert _work(W, ref) == [] and "workflow.registered" not in _actions(J, ref)
    assert any("The plan is dropped because you said no" in s for s in _said(R, ref))


def test_step_4_identity_rules_from_the_goal_and_the_rules_without_asking(j2, monkeypatch):
    W, R, J, _ = j2
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room"},
                            "identity.close": {"ruling": "run", "why": "the goal cannot be met without a site"}})
    ref = _born(j2)
    ruled = next(e for e in J.events(ref) if e["action"] == "identity.ruled")
    assert ruled["state"] == "run" and "goal" in ruled["summary"]
    assert not [a for a in W.asks(ref) if a["kind"] == "conflict"]
    assert "workflow.registered" in _actions(J, ref) and _work(W, ref)[:1] == ["Plan"]


def test_step_4_identity_lets_a_refusal_stand(j2, monkeypatch):
    W, R, J, _ = j2
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "no room"},
                            "identity.close": {"ruling": "drop", "why": "the rules say work inside the budget"}})
    ref = _born(j2)
    assert J.status(ref)["state"] == "blocked" and _work(W, ref) == []
    assert any("is dropped: the rules say work inside the budget" in s for s in _said(R, ref))


def test_step_3_priority_counters_and_adaptation_takes_the_counter(j2, monkeypatch):
    """A counter treated as a refusal, or a bargain that never closes, must fail."""
    W, R, J, _ = j2
    three = {"engines": [{"name": "Facts", "does": "finds the facts", "reads": "Brief", "writes": "Facts", "internet": True},
                         {"name": "Notes", "does": "sorts the facts", "reads": "Facts", "writes": "Notes", "internet": False},
                         {"name": "Summary", "does": "writes the summary", "reads": "Notes", "writes": "Summary", "internet": False}]}

    def bargain(prompt):
        if "- Summary:" in prompt:
            return {"answer": "counter", "why": "room for two today", "keep": ["Facts", "Notes"]}
        return {"answer": "accept", "why": "the envelope has room"}

    _model(monkeypatch, R, {"adapt.line": three, "priority.bargain": bargain})
    ref = _born(j2, ORGANIC, "Lab Co")
    acts = _actions(J, ref)
    assert acts[2:8] == ["proposal.created", "proposal.countered", "proposal.created", "proposal.granted", "workflow.validated", "workflow.registered"]
    hops = [e["payload"]["hop"] for e in J.events(ref) if e["step"] in (2, 3) and "hop" in e["payload"]]
    assert hops == [1, 2, 3, 4]                                    # one thread, inside its four hops
    assert W.dept(ref)["engines"] == ["Facts", "Notes"]
    assert "conflict.raised" not in acts


def test_j2_2_a_bargain_at_its_bound_goes_to_identity(j2, monkeypatch):
    """A bargain that hits its bound and ends in a silent refusal must fail."""
    W, R, J, founding = j2
    monkeypatch.setattr(R, "BOUNDS", {"hops": 1, "seconds": 900, "usd": 0.5})       # room for the proposal, none for an answer
    ref = _born(j2)
    raised = next(e for e in J.events(ref) if e["action"] == "conflict.raised")
    assert raised["actor"] == "Coordination" and raised["payload"]["bound"] == "hops"
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["conflict"]
    assert _work(W, ref) == []


def test_j2_4_roots_refusal_goes_back_to_adaptation_and_registers_nothing(j2, monkeypatch):
    """Registering a workflow Root's check refused must fail; so must reshaping without end."""
    W, R, J, _ = j2
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["Facts reads Notes, which nothing before it writes"] if calls["n"] == 1 else real(ref, d, engines, source)

    monkeypatch.setattr(R, "_root_check", check)
    ref = _born(j2, ORGANIC, "Lab Co")
    acts = _actions(J, ref)
    blocked = acts.index("workflow.blocked")
    assert acts[blocked + 1] == "proposal.requested" and acts.index("workflow.registered") > blocked
    assert next(e for e in J.events(ref) if e["action"] == "workflow.blocked")["payload"]["faults"] == ["Facts reads Notes, which nothing before it writes"]
    assert any("Root's check sent the plan back" in s and "reshaping" in s for s in _said(R, ref))
    assert len(W.dept(ref)["workflows"]) == 1


def test_j2_4_after_two_repairs_the_owner_is_told_and_nothing_runs(j2, monkeypatch):
    W, R, J, _ = j2
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: ["the line reaches outside without a rule"])
    ref = _born(j2, ORGANIC, "Lab Co")
    acts = _actions(J, ref)
    assert acts.count("workflow.blocked") == J.REPAIRS + 1 and "workflow.registered" not in acts
    assert J.status(ref)["state"] == "blocked" and _work(W, ref) == []
    assert any("sent the plan back 3 times" in s for s in _said(R, ref))


def _six_items(W, ref):
    """The department's done-when grows to D1 to D6, each with how it is checked: what the plan below is held to cover."""
    d = W.dept(ref)
    d["done_items"] = [{"id": "D%d" % n, "text": "Item %d is done" % n, "how": "model", "level": "outcome"} for n in range(1, 7)]
    W.save_dept(ref, d)
    return W.dept(ref)


def _line_covering(*covers):
    """The website's Library line, each engine naming the done-when items it covers."""
    return [{"name": n, "covers": list(c)} for n, c in zip(LINE, covers)]


def test_j2_4_a_plan_without_an_engine_covering_d6_is_refused_naming_items_covered(j2):
    """A plan that leaves a done-when item with no engine registered, or refused without the standard that broke, must fail."""
    import layer_schema as S
    W, R, J, _ = j2
    ref = _born(j2)
    d = _six_items(W, ref)
    before = len(d["workflows"])
    plan = _line_covering(["D1", "D2"], ["D3"], ["D4"], ["D5"])
    out = R._j2_settle(ref, d, plan, "library", d.get("goal"), "a test")
    assert "sent the workflow back" in out["said"] and "D6 is covered by no engine of the plan" in out["said"]
    assert len(W.dept(ref)["workflows"]) == before, "nothing registered"
    blocked = [e for e in J.events(ref) if e["action"] == "workflow.blocked"][-1]
    assert blocked["payload"]["faults"] == ["D6 is covered by no engine of the plan"]
    rows = blocked["payload"]["checks"]
    assert [c["check"] for c in rows if not c["passed"]] == ["items_covered"] and all(S.validate("workflow.check", c) == [] for c in rows)
    assert R._root_check(ref, d, plan, "library") == ["D6 is covered by no engine of the plan"]
    # the last engine takes D6 too, and the plan registers, with the cover it named
    plan[3]["covers"] = ["D5", "D6"]
    assert R._root_check(ref, d, plan, "library") == []
    R._j2_settle(ref, d, plan, "library", d.get("goal"), "a test")
    reg = W.dept(ref)["workflows"][-1]
    assert len(W.dept(ref)["workflows"]) == before + 1 and reg["covers"]["D6"] == ["Publish"] and reg["covers"]["D1"] == ["Plan"]


def test_j2_4_the_third_refusal_leaves_one_options_ask_naming_the_standard_and_its_options_apply(j2):
    """A third refusal that is said in a line with nothing to press, or one that does not name the broken standard in its
    words, or an option that applies nothing, must fail."""
    import layer_schema as S
    W, R, J, _ = j2
    ref = _born(j2)
    d = _six_items(W, ref)
    plan = _line_covering(["D1", "D2"], ["D3"], ["D4"], ["D5"])
    for n in range(J.REPAIRS):
        R._j2_settle(ref, d, plan, "library", d.get("goal"), "a test")
        assert J.status(ref)["state"] != "blocked", "refused %d: sent back to Adaptation, not yet to the owner" % (n + 1)
    R._j2_settle(ref, d, plan, "library", d.get("goal"), "a test")
    assert J.status(ref)["state"] == "blocked"
    cards = [a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending"]
    assert len(cards) == 1
    says = next(text for sid, text, _, _ in S.WORKFLOW_STANDARDS if sid == "items_covered")
    assert says in cards[0]["text"] and "D6 is covered by no engine of the plan" in cards[0]["text"]
    assert says in cards[0]["why"] and cards[0]["who"] == "Root, at its review"
    assert [o["id"] for o in cards[0]["options"]] == ["words", "leave:D6", "stop"]
    assert not [w for w in ("items_covered", "reads_known", "workflow_meets_standards") if w in cards[0]["text"]], "the owner is told in words, not ids"
    # leaving D6 out applies: done-when is D1 to D5, and the plan is shaped afresh
    W.choose_option(ref, cards[0]["id"], "leave:D6")
    W.run_until_idle(ref, limit=300)
    assert [i["id"] for i in W.dept(ref)["done_items"]] == ["D1", "D2", "D3", "D4", "D5"]


def test_j2_b_a_second_shaped_department_takes_names_the_library_does_not_have(j2):
    """Shaping Facts and Site twice must fail: the second line's check refused it and the cycle sat at step 2, unsaid."""
    W, _, J, _ = j2
    first = _born(j2, ORGANIC, "Lab Co")
    second = _born(j2, ORGANIC, "Field Co")
    assert W.dept(first)["engines"] == ["Facts", "Site"]
    assert W.dept(second)["engines"] == ["Facts 2", "Site 2"]
    assert J.status(second)["step"] == 6


def test_j2_b_a_line_that_cannot_be_shaped_is_tried_again_then_said(j2, monkeypatch):
    """An Adaptation run that fails and leaves the cycle standing at step 2 with nothing said must fail."""
    W, R, J, _ = j2
    bad = {"engines": [{"name": "Plan", "does": "plans", "reads": "Brief", "writes": "Notes", "internet": False}]}   # a name the Library has
    _model(monkeypatch, R, {"adapt.line": bad})
    ref = _born(j2, ORGANIC, "Lab Co")
    acts = _actions(J, ref)
    assert acts.count("workflow.blocked") == J.REPAIRS + 1 and acts.count("proposal.requested") == J.REPAIRS + 1
    assert J.status(ref)["state"] == "blocked" and _work(W, ref) == []
    assert any("could not shape a plan that passes its check" in s for s in _said(R, ref))


def _thin(monkeypatch, R):
    """Root takes 'a website' as clear (J1 asked nothing), and Identity reads it as naming nothing to build from."""
    _model(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""},
                            "identity.take": lambda prompt: {"verdict": "go", "why": "", "needs": [], "unsure": [],
                                                             "thin": "bakery" not in prompt.split("THE REQUEST: ", 1)[1].split("\n", 1)[0]}})


def _client(J):
    import j2_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    importlib.reload(j2_api)
    app = FastAPI()
    app.include_router(j2_api.router)
    return TestClient(app)


BAKERY = "a site for my bakery in Pune"


def test_m0_5_thin_words_are_an_open_question_and_the_answer_box_starts_step_2(j2, monkeypatch):
    """Thin words that file no ask (so /j2/answer said 409), or an answer that starts nothing, must fail."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    ref = _born(j2, "a website", "Bakery Co")
    client = _client(J)
    st = client.get("/api/dept/%s/j2" % ref).json()
    q = st["open_question"]
    assert (st["state"], st["step"]) == ("waiting", 1)
    assert q["missing"] == "words" and q["text"] == "What is the site for, and about whom or what?"
    assert q["why"] == "Your words name nothing to build from yet." and q["id"] == st["open_ask"]
    assert [a["id"] for a in W.asks(ref) if a["kind"] == "j2_identity" and a["status"] == "pending"] == [q["id"]]
    assert _work(W, ref) == [] and "proposal.requested" not in _actions(J, ref)

    got = client.post("/api/dept/%s/j2/answer" % ref, json={"text": BAKERY})
    assert got.status_code == 200 and got.json()["open_question"] is None
    W.run_until_idle(ref, limit=300)
    requested = next(e for e in J.events(ref) if e["action"] == "proposal.requested")
    assert requested["step"] == 2
    assert _actions(J, ref)[:4] == ["identity.questioned", "ask.answered", "identity.assessed", "proposal.requested"]
    assert BAKERY in W.read_files(ref, "Brief", 1)["brief.md"]
    after = client.get("/api/dept/%s/j2" % ref).json()
    assert after["open_question"] is None and after["answered_question"]["answer"] == BAKERY
    again = client.post("/api/dept/%s/j2/answer" % ref, json={"text": BAKERY})
    assert (again.status_code, again.json()["detail"]) == (409, {"code": "NO_OPEN_QUESTION"})


def test_m0_5_the_same_question_is_answered_in_chat_once(j2, monkeypatch):
    """Words said in the chat that leave the question open, or that are taken twice, must fail."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    ref = _born(j2, "a website", "Bakery Co")
    aid = J.status(ref)["open_question"]["id"]
    W.owner_ask(ref, BAKERY)
    W.run_until_idle(ref, limit=300)
    ask = next(a for a in W.asks(ref) if a["id"] == aid)
    assert (ask["status"], ask["answered"]) == ("stamped", BAKERY)
    assert _actions(J, ref).count("ask.answered") == 1
    assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2
    assert J.status(ref)["open_question"] is None and "workflow.registered" in _actions(J, ref)


def test_m0_5_still_too_little_is_asked_again_and_a_stopped_department_uses_the_answer_on_start(j2, monkeypatch):
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    ref = _born(j2, "a website", "Bakery Co")
    first = J.status(ref)["open_question"]["id"]
    J.answer(ref, "a nice one")                                        # still names nothing: FI1.1, asked again
    W.run_until_idle(ref, limit=300)
    second = J.status(ref)["open_question"]
    assert second and second["id"] != first and second["missing"] == "words"
    assert _actions(J, ref).count("identity.questioned") == 2 and "proposal.requested" not in _actions(J, ref)

    J.stop(ref)
    assert J.status(ref)["open_question"]["id"] == second["id"]          # a stopped department can still be answered
    J.answer(ref, BAKERY)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["state"] == "stopped" and "proposal.requested" not in _actions(J, ref)
    J.start(ref)
    W.run_until_idle(ref, limit=300)
    assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2


def test_m0_5_a_department_that_is_not_a_website_is_never_called_a_site(j2, monkeypatch):
    """The card asking what the department is for while the line beside it asks what the site is for (one screen, two
    names for one thing) must fail: a department is a site only when it is a website, on its birth words and on the
    second department Root sets up."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""},
                            "identity.take": lambda prompt: {"verdict": "go", "why": "", "needs": [], "unsure": [], "thin": not any(
                                w in prompt.split("THE REQUEST: ", 1)[1].split("\n", 1)[0] for w in ("algebra", "bakery"))}})
    lab = _born(j2, ORGANIC, "Lab Co")
    site = _born(j2, WEBSITE, "Acme Learning")
    root = W.dept(site)["root"]
    W.owner_ask(root, "Set up another department: a sales CRM for the team")      # a second name: another kind
    W.run_until_idle(root, limit=300)
    crm = next(d["ref"] for d in W.list_depts() if d.get("parent") == root and d["ref"] != site)
    W.run_until_idle(crm, limit=300)
    for ref in (lab, crm):
        assert W.dept(ref)["kind"] != "website"
        assert J.status(ref)["open_question"]["text"] == "What is the department for, and about whom or what?"
        mine = _said(R, ref) + _said(R, W.dept(ref)["root"])
        asked = [s for s in mine if "nothing to build from" in s]
        assert asked and all(s.startswith("Say what the department is for and about whom or what") for s in asked), asked
        told = [t["line"] for t in R.chat_view(ref)["turns"] if t["src"] != "Owner"] + mine
        assert not [s for s in told if re.search(r"\bsites?\b", s, re.I)], told

    bakery = _born(j2, "a website", "Bakery Co")                       # a website is still a site, on its card and its line
    assert J.status(bakery)["open_question"]["text"] == "What is the site for, and about whom or what?"
    assert [s for s in _said(R, bakery) if "nothing to build from" in s][0].startswith("Say what the site is for")


def test_m0_6_identitys_question_is_never_closed_by_a_stamp(j2, monkeypatch):
    """A stamp that closes a question with nothing said (the cycle then waits on an answer no one can give) must fail."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    ref = _born(j2, "a website", "Bakery Co")
    aid = J.status(ref)["open_question"]["id"]
    for approve in (True, False):
        with pytest.raises(ValueError, match="takes words"):
            W.decide_ask(ref, aid, approve)
    assert J.status(ref)["open_question"]["id"] == aid


def test_m0_6_the_chat_carries_identitys_question_and_keeps_its_answer(j2, monkeypatch):
    """The card in Chat reads the chat: an open question there, and once answered, its answer kept, on the department's
    chat and on Root's."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    ref = _born(j2, "a website", "Bakery Co")
    chat = R.chat_view(ref)
    q = [a for a in chat["asks"] if a["kind"] == "j2_identity"]
    assert len(q) == 1 and (q[0]["ref"], q[0]["missing"]) == (ref, "words") and q[0]["why"] == J.THIN
    assert chat["answered"] == []
    J.answer(ref, BAKERY)
    W.run_until_idle(ref, limit=300)
    chat = R.chat_view(ref)
    assert not [a for a in chat["asks"] if a["kind"] == "j2_identity"]
    assert [(a["id"], a["answered"], a["ref"]) for a in chat["answered"]] == [(q[0]["id"], BAKERY, ref)]
    assert [a["id"] for a in R.chat_view(W.dept(ref)["root"])["answered"]] == [q[0]["id"]]


def _copies(view, q, words):
    """What a chat says of Identity's question beside its card: lines that say the question again, and the owner's
    turns that say the answer again."""
    turns = view["turns"]
    return ([t["line"] for t in turns if t["src"] != "Owner" and ("nothing to build from" in t["line"] or q["text"] in t["line"])],
            [t["line"] for t in turns if t["src"] == "Owner" and t["line"] == words])


def test_m0_6_the_chat_says_identitys_question_once_on_its_card_and_the_answer_once_under_it(j2, monkeypatch):
    """Identity's line about the question standing above its card, or the answer kept under the card and said again as
    a turn of its own (the chat said each twice), must fail: on the department's chat and on Root's, whether the answer
    came from the card's box, from the department's Chat box (through Root), or in a department with no Root. The board
    keeps both posts; only the chat leaves them to the card."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    d, _ = W.create("dref-alone", "Alone Website", None, kind="website")       # a department with no Root
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "a website")
    W.run_until_idle(d["ref"], limit=300)
    for how, ref in (("card", _born(j2, "a website", "Bakery Co")), ("chat", _born(j2, "a website", "Bakery Two")), ("alone", d["ref"])):
        root = W.dept(ref).get("root")
        views = lambda: [R.chat_view(ref)] + ([R.chat_view(root)] if root else [])
        q = J.status(ref)["open_question"]
        for view in views():
            assert [a["id"] for a in view["asks"] if a["kind"] == "j2_identity"] == [q["id"]], how
            assert _copies(view, q, BAKERY) == ([], []), how
        if how == "card":
            J.answer(ref, BAKERY)                                      # the card's Send: /j2/answer
        elif how == "chat":
            W.owner_ask(root, BAKERY, about=ref)                       # the department's Chat box: to Root, carrying it
            W.run_until_idle(root, limit=300)
        else:
            W.owner_ask(ref, BAKERY)
        W.run_until_idle(ref, limit=300)
        assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2, how
        for view in views():
            assert [(a["id"], a["answered"]) for a in view["answered"]] == [(q["id"], BAKERY)], how
            assert _copies(view, q, BAKERY) == ([], []), how
        assert [s for s in _said(R, ref) if "nothing to build from" in s], how          # the board keeps what was said
        boards = [ref] + ([root] if root else [])
        assert [p for b in boards for p in R.board(b) if p["src"] == "Owner" and (p["payload"] or {}).get("words") == BAKERY], how


def test_m0_6_a_question_on_a_gap_in_the_identity_is_said_once_on_its_card(j2):
    """A gap in the identity asked as a card and again as Identity's line beside it must fail; the card keeps the
    answer, and the next question is its own card."""
    W, R, J, _ = j2
    d, _ = W.create("dref-gap2", "Finance highlights", "Publish verified finance news", kind="website")
    d.update({"goal": "", "done": "", "events": [{"kind": "j2_ready", "route": "template"}],
              "rules": [{"id": "r1", "tag": "go", "line": "Work inside the record"}]})
    W.save_dept(d["ref"], d)
    ref = d["ref"]
    J.start(ref)
    goal = "Publish five verified finance highlights each morning"
    asked = J.status(ref)["open_question"]
    assert asked["text"] in _said(R, ref)                                # on the record
    lines = lambda: [t["line"] for t in R.chat_view(ref)["turns"]]
    assert asked["text"] not in lines()
    J.answer(ref, goal)
    after = R.chat_view(ref)
    assert [a["answered"] for a in after["answered"]] == [goal]
    assert [a["text"] for a in after["asks"] if a["kind"] == "j2_identity"] == ["What evidence will prove this department is done?"]
    assert not [x for x in lines() if x in (asked["text"], goal, "What evidence will prove this department is done?")]


def _failed(W, ref):
    return [r for r in W.runs(ref) if r.get("status") == "failed"]


def test_m0_5_an_answer_said_to_root_from_the_departments_chat_takes_the_question(j2, monkeypatch):
    """The Chat box sends the words to Root with the department's chip. An answer that starts with yes, ok or no read as
    a stamp on Identity's question (Root's run failed, the question stayed open, and the owner read a raw error) must fail."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    for lead, org in (("yes, ", "Bakery Co"), ("OK, ", "Bakery Two"), ("no, it is ", "Bakery Three")):   # a department each
        ref = _born(j2, "a website", org)
        root = W.dept(ref)["root"]
        aid = J.status(ref)["open_question"]["id"]
        W.owner_ask(root, lead + BAKERY, about=ref)
        W.run_until_idle(root, limit=300)
        W.run_until_idle(ref, limit=300)
        ask = next(a for a in W.asks(ref) if a["id"] == aid)
        assert (ask["status"], ask["answered"]) == ("stamped", lead + BAKERY), lead
        assert _actions(J, ref)[:4] == ["identity.questioned", "ask.answered", "identity.assessed", "proposal.requested"], lead
        assert next(e for e in J.events(ref) if e["action"] == "proposal.requested")["step"] == 2
        assert _failed(W, root) == [] and not [s for s in _said(R, root) if "could not act" in s], lead


def test_m0_6_a_bare_yes_to_root_leaves_identitys_question_open_and_says_so(j2, monkeypatch):
    """A 'yes' with nothing to stamp, while Identity's question is open, that fails Root's run (or closes the question
    with nothing said) must fail; Root says, in plain words, that the question still wants words."""
    W, R, J, _ = j2
    _thin(monkeypatch, R)
    ref = _born(j2, "a website", "Bakery Co")
    root, name = W.dept(ref)["root"], W.dept(ref)["name"]
    q = J.status(ref)["open_question"]
    for about in (None, ref):                            # said in Root's chat, then in the department's
        W.owner_ask(root, "yes", about=about)
        W.run_until_idle(root, limit=300)
    assert J.status(ref)["open_question"]["id"] == q["id"] and _failed(W, root) == []
    assert _said(R, root)[-2:] == ["Nothing is waiting for a stamp. %s asks you: %s Answer it in your own words." % (name, q["text"])] * 2
    assert "ask.answered" not in _actions(J, ref)


def test_m0_6_a_yes_to_root_stamps_another_departments_ask_while_identitys_question_is_open(j2, monkeypatch):
    """Identity's open question taken as the latest ask to stamp (the stamp fails, and the other department's publish ask
    stays pending whenever the department with the question is listed first) must fail."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""},
                            "identity.take": lambda prompt: {"verdict": "go", "why": "", "needs": [], "unsure": [], "thin": not any(
                                w in prompt.split("THE REQUEST: ", 1)[1].split("\n", 1)[0] for w in ("algebra", "bakery"))}})
    site = _born(j2)
    root = W.dept(site)["root"]
    publish = [a for a in W.asks(site) if a["status"] == "pending"]
    assert [a["kind"] for a in publish] == ["publish"]
    W.owner_ask(root, "Set up another department: a sales CRM for the team")      # a second name: another kind
    W.run_until_idle(root, limit=300)
    thin = next(d["ref"] for d in W.list_depts() if d.get("parent") == root and d["ref"] != site)
    W.run_until_idle(thin, limit=300)
    aid = J.status(thin)["open_question"]["id"]
    children = R._children
    monkeypatch.setattr(R, "_children", lambda r: sorted(children(r), key=lambda c: c["ref"] != thin))
    assert [c["ref"] for c in R._children(root)] == [thin, site]

    W.owner_ask(root, "yes")
    W.run_until_idle(root, limit=300)
    assert next(a for a in W.asks(site) if a["id"] == publish[0]["id"])["status"] == "stamped"
    assert J.status(thin)["open_question"]["id"] == aid and _failed(W, root) == []

    W.owner_ask(root, "OK, " + BAKERY, about=thin)       # the department's Chat box: the answer, not a stamp
    W.run_until_idle(root, limit=300)
    W.run_until_idle(thin, limit=300)
    assert next(a for a in W.asks(thin) if a["id"] == aid)["answered"] == "OK, " + BAKERY
    assert next(e for e in J.events(thin) if e["action"] == "proposal.requested")["step"] == 2
    assert _failed(W, root) == []


# Root's standards by id (A1.14): the schema's own shape row first, then each standard that applied at registration
LIBRARY_CHECKS = ["workflow_meets_standards", "names_an_engine", "engines_known", "names_unique", "first_reads_input", "reads_known",
                  "one_output", "items_covered", "required_kept", "size_in_range", "check_exists", "fits_room"]
SHAPED_CHECKS = ["workflow_meets_standards", "names_an_engine", "each_engine_named", "names_unique", "names_new", "first_reads_input",
                 "reads_known", "one_output", "items_covered", "required_kept", "size_in_range", "check_exists", "fits_room"]


def test_m0_7_the_validated_event_lists_the_checks_that_ran_for_a_library_and_a_shaped_line(j2, monkeypatch):
    """A fixed list of check names, written whatever ran (a Library line was said to pass checks only a shaped line
    runs), must fail: each row is a standard's id, only the standards that apply to the source are listed, and every
    row is a workflow.check."""
    import layer_schema as S
    W, R, J, _ = j2
    ran, real = [], R._root_checks

    def spy(*a):
        out = real(*a)
        ran.append(out)
        return out
    monkeypatch.setattr(R, "_root_checks", spy)
    says = {sid: text for sid, text, _, _ in S.WORKFLOW_STANDARDS}
    lib = _born(j2)
    checks = next(e for e in J.events(lib) if e["action"] == "workflow.validated")["payload"]["checks"]
    assert checks == ran[-1] and [c["check"] for c in checks] == LIBRARY_CHECKS and all(c["passed"] for c in checks)
    # the website kind requires Check (PRD M4.4), so the standard that none is left out ran, and held
    assert next(c for c in checks if c["check"] == "required_kept")["why"] == says["required_kept"]
    # Priority prices the line while the department is born (M5.3) and keeps the price, so Root's check reads a real one
    priced = [r for r in W.rows(lib, "prices.jsonl") if r["proposal"] == "line"]
    assert priced and priced[-1]["answer"] == "accept", "Priority said yes to the line, and kept its price"
    assert next(c for c in checks if c["check"] == "fits_room")["why"] == says["fits_room"]
    assert W.dept(lib)["workflows"][-1]["checks"] == checks, "the registration keeps the rows the event listed"
    shaped = _born(j2, ORGANIC, "Lab Co")
    checks = next(e for e in J.events(shaped) if e["action"] == "workflow.validated")["payload"]["checks"]
    assert checks == ran[-1] and [c["check"] for c in checks] == SHAPED_CHECKS and all(c["passed"] and c["why"] for c in checks)
    assert all(S.validate("workflow.check", c) == [] for c in checks)
    # a standard that does not apply to the source is not listed
    assert "engines_known" not in [c["check"] for c in checks] and "names_new" not in LIBRARY_CHECKS


def test_m0_7_a_refusal_lists_the_checks_that_ran_and_the_one_that_failed(j2, monkeypatch):
    import layer_schema as S
    W, R, J, _ = j2
    ref = _born(j2)
    d = W.dept(ref)
    R._j2_settle(ref, d, [{"name": "Plan"}, {"name": "Nobody Knows"}], "library", d.get("goal"), "a test")
    blocked = [e for e in J.events(ref) if e["action"] == "workflow.blocked"][-1]
    # the plan also leaves out Check, which the website kind requires (PRD M4.4): every standard runs, and each fault is listed
    assert blocked["payload"]["faults"] == ["the Library has no engine named Nobody Knows",
                                            "the plan leaves out Check, which this kind of department requires"]
    rows = blocked["payload"]["checks"]
    assert all(S.validate("workflow.check", c) == [] for c in rows)
    assert [(c["check"], c["why"]) for c in rows if not c["passed"]] == [
        ("engines_known", "the Library has no engine named Nobody Knows"),
        ("required_kept", "the plan leaves out Check, which this kind of department requires")]
    assert [c["check"] for c in rows if c["passed"]] == ["workflow_meets_standards", "names_an_engine", "names_unique", "first_reads_input",
                                                         "reads_known", "one_output", "items_covered", "size_in_range", "check_exists", "fits_room"]
    # a check put in Root's place is listed as it ran, beside the standards
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: ["the line reaches outside without a rule"])
    lab = _born(j2, ORGANIC, "Lab Co")
    first = next(e for e in J.events(lab) if e["action"] == "workflow.blocked")
    assert [c["check"] for c in first["payload"]["checks"]] == SHAPED_CHECKS + ["workflow_meets_standards"]
    assert first["payload"]["checks"][-1] == {"check": "workflow_meets_standards", "passed": False, "why": "the line reaches outside without a rule"}
    assert all(S.validate("workflow.check", c) == [] for c in first["payload"]["checks"])


def test_m0_7_a_line_that_failed_adaptations_own_check_ran_none_of_roots(j2, monkeypatch):
    W, R, J, _ = j2
    bad = {"engines": [{"name": "Plan", "does": "plans", "reads": "Brief", "writes": "Notes", "internet": False}]}
    _model(monkeypatch, R, {"adapt.line": bad})
    ref = _born(j2, ORGANIC, "Lab Co")
    blocked = [e for e in J.events(ref) if e["action"] == "workflow.blocked"]
    assert blocked and all(e["actor"] == "Adaptation" and e["payload"]["checks"] == [] for e in blocked)


# ---- the owner's switch --------------------------------------------------------------------------------------------
def test_stop_then_start_goes_on_from_the_same_step_and_the_two_switches_agree(j2):
    """A Stop that starts a cycle first, or a department that is On while its cycle says stopped, must fail."""
    W, _, J, _ = j2
    ref = _born(j2)
    before = J.status(ref)
    stopped = J.stop(ref)
    assert stopped["state"] == "stopped" and W.dept(ref)["stopped"] is True
    assert J.stop(ref) == stopped and _actions(J, ref).count("cycle.stopped") == 1
    assert J.holding(ref)

    W.set_stopped(ref, False)                                      # the department's own Start
    after = J.status(ref)
    assert (after["state"], after["step"], after["cycle_id"]) == (before["state"], before["step"], before["cycle_id"])
    assert W.dept(ref)["stopped"] is False

    J.stop(ref)
    again = J.start(ref)                                           # the J2 Start does the same
    assert again["state"] == before["state"] and W.dept(ref)["stopped"] is False


def test_stop_on_a_department_that_never_started_runs_nothing_first(j2):
    W, _, J, _ = j2
    d, _ = W.create("dref-cold", "Cold", "A goal", kind="website")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.stop(d["ref"])
    assert _actions(J, d["ref"]) == ["cycle.stopped"]


def test_eight_starts_at_once_are_one_cycle(j2):
    """Reading the state and writing it outside one lock must fail (8 clicks made 8 cycles and 40 events)."""
    W, _, J, _ = j2
    d, _ = W.create("dref-race", "Race", "A goal", kind="website")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    gate, out = threading.Barrier(8), []

    def go():
        gate.wait()
        out.append(J.start(d["ref"])["cycle_id"])

    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(out)) == 1 and len(out) == 8


def test_with_the_switch_off_a_department_runs_as_it_did_before(j2, monkeypatch):
    W, _, J, _ = j2
    monkeypatch.setenv("J2_FLOW_V1", "0")
    ref = _born(j2)
    assert J.status(ref)["state"] == "not_started" and J.events(ref) == []
    assert _work(W, ref)[:3] == ["Plan", "Write", "Check"]        # never held
    lab = _born(j2, ORGANIC, "Lab Co")
    assert [a["kind"] for a in W.asks(lab) if a["status"] == "pending"] == ["line"]


# ---- the ledger ------------------------------------------------------------------------------------------------------
def test_the_ledger_takes_an_event_once_and_only_for_its_own_department(j2):
    _, _, J, _ = j2
    ref = _born(j2)
    event = dict(J.events(ref)[0])
    n = len(J.events(ref))
    assert J.append_event(ref, {k: event[k] for k in ("idempotency_key", "department_ref", "cycle_id", "step", "journey", "actor",
                                                       "recipient", "action", "state", "summary")})["event_id"] == event["event_id"]
    assert len(J.events(ref)) == n
    with pytest.raises(J.J2Error, match="DEPARTMENT_MISMATCH"):
        J.append_event("dref-other", event)
    with pytest.raises(J.J2Error, match="INVALID_EVENT"):
        J.append_event(ref, {"department_ref": ref, "idempotency_key": "x"})


def test_events_carry_the_contract_and_the_activity_keeps_their_order(j2):
    """Sorting two events of one second by a random id must fail (the screen showed steps 5, 5, 1, 3, 2)."""
    _, _, J, _ = j2
    ref = _born(j2)
    events = J.events(ref)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    for e in events:
        for key in ("schema_version", "event_id", "identity_revision", "correlation_id", "evidence_refs", "occurred_at"):
            assert key in e, key
        assert e["correlation_id"] == e["cycle_id"]
    assert events[0]["causation_id"] is None and events[1]["causation_id"] == events[0]["event_id"]
    shown = [r["id"] for r in J.activity(ref) if not r["id"].startswith("board-")]
    assert shown == [e["event_id"] for e in events]


def test_nothing_private_reaches_the_ledger_or_the_activity(j2):
    # the token's value holds letters no hex id has: "abc" was found inside a random event id (evt-2abcf99a3c61)
    _, _, J, _ = j2
    ref = _born(j2)
    J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "A step.", "private-1",
           {"reasoning": "hidden", "token": "tok-qzx", "kept": {"password": "x", "shown": 1}})
    blob = str(J.events(ref)[-1]) + str(J.activity(ref))
    assert "hidden" not in blob and "tok-qzx" not in blob and "'shown': 1" in blob


# ---- PRD M4: Coordination's timetable, and the line is what was granted -------------------------------------------------
def _table_writes(W, monkeypatch):
    """Every write of coordination.json from here on, as (who it says wrote it, the line it wrote)."""
    seen, real = [], W._write

    def spy(p, obj):
        if str(p).endswith("coordination.json"):
            seen.append((obj.get("by"), list(obj.get("line") or [])))
        return real(p, obj)
    monkeypatch.setattr(W, "_write", spy)
    return seen


def test_m4_1_root_records_the_plan_coordination_writes_its_table_and_priority_gives_each_new_engine_its_limit(j2, monkeypatch):
    """Root writing Coordination's table, a limit nobody gave on the ledger, or an engine Root made must fail."""
    W, R, J, _ = j2
    writes = _table_writes(W, monkeypatch)
    for words, org in ((WEBSITE, "Acme Learning"), (ORGANIC, "Lab Co")):
        del writes[:]
        ref = _born(j2, words, org)
        names = W.dept(ref)["workflows"][-1]["engines"]
        t = W._read(W.ddir(ref) / "coordination.json", None)
        assert (t["by"], t["registered"], t["line"]) == ("Coordination", 1, names), org
        assert [w for w in writes if w[0] != "born"] and all(by in ("born", "Coordination") for by, _ in writes), writes
        events = J.events(ref)
        reg = next(e for e in events if e["action"] == "workflow.registered")
        assert (reg["actor"], reg["recipient"]) == ("Root", "Coordination")
        table = [e for e in events if e["action"] == "timetable.written"]
        assert [(e["actor"], e["payload"]["line"]) for e in table] == [("Coordination", names)]
        granted = [e for e in events if e["action"] == "envelope.granted"]
        assert [e["recipient"] for e in granted] == names and {e["actor"] for e in granted} == {"Priority"}, granted
        assert all(e["seq"] > reg["seq"] and e["step"] == 5 and e["workflow_ref"] == "workflow/1" for e in granted)
        assert all(W.dept(ref)["envelopes"].get(n) for n in names)
        # each decision is a row of the function whose handler it is, never Root's
        rows = [(r["engine"], r["step"]) for r in R.step_rows(ref) if r["step"] in ("coord.table", "priority.grant")]
        assert rows == [("Coordination", "coord.table"), ("Priority", "priority.grant")], rows
        assert {e["action"] for e in events if e["actor"] == "Root"} == {"workflow.validated", "workflow.registered"}
    # a shaped engine is Adaptation's: born into the Library with made_by Adaptation, its limit Priority's
    lab = W.dept(ref)
    for n in lab["engines"]:
        assert R.engine_def(n)["made_by"]["by"] == "Adaptation"
    assert [e["payload"]["kept"] for e in J.events(ref) if e["action"] == "envelope.granted"] == [False] * len(lab["engines"])
    assert lab["envelopes"][lab["engines"][0]]["calls"] == 8 * 30, "a work engine's limit, from Priority's template"


def test_m4_1_on_every_kind_each_engines_first_limit_is_priority_s_grant_at_registration(j2, monkeypatch):
    """A website or default department born with its engines' limits already written (so Priority's handler only finds
    limits that exist, and every envelope.granted says the engine keeps the limit it holds) must fail: a department
    that lives J2 is born with its functions' limits only, and Priority gives each engine its own when the plan that
    names it is registered."""
    W, R, J, _ = j2
    web = _born(j2, settle=False)
    assert set(W.dept(web)["envelopes"]) == set(R.FUNCTIONS), "born with the functions' limits only"
    assert W.limit_of(W.dept(web), "Write") == R.engine_limit("Write") == {"calls": 240, "usd": 6.0}, "read as Priority gives it"
    W.run_until_idle(web, limit=300)
    d, _ = W.create("dref-answers", "Answers", None, kind="default")   # the default kind: one Do engine
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
    W.run_until_idle(d["ref"], limit=300)
    for ref, names in ((web, LINE), (d["ref"], ["Do"])):
        granted = [e for e in J.events(ref) if e["action"] == "envelope.granted"]
        assert [(e["recipient"], e["actor"], e["payload"]["kept"]) for e in granted] == [(n, "Priority", False) for n in names], granted
        assert all(e["summary"] == "Priority gave %s its limit." % e["recipient"] for e in granted)
        assert all(W.dept(ref)["envelopes"][n] == R.engine_limit(n) for n in names)
    # a department off J2 runs the way it did before it: its engines are born with their limits
    monkeypatch.setenv("J2_FLOW_V1", "0")
    off = W.create("dref-off", "Off", None, kind="website")[0]
    assert all(W.dept(off["ref"])["envelopes"][n] == R.engine_limit(n) for n in LINE)


def test_m4_1_an_engine_that_holds_a_limit_keeps_it_and_the_ledger_says_so(j2):
    """Priority's handler overwriting the owner's own limit must fail."""
    W, R, J, _ = j2
    ref = _born(j2, settle=False)
    W.set_envelope(ref, "Write", calls=12)
    W.run_until_idle(ref, limit=300)
    assert W.dept(ref)["envelopes"]["Write"]["calls"] == 12
    granted = {e["recipient"]: e for e in J.events(ref) if e["action"] == "envelope.granted"}
    assert sorted(granted) == sorted(LINE) and granted["Write"]["payload"]["kept"] is True and granted["Write"]["payload"]["calls"] == 12
    assert granted["Write"]["summary"] == "Write keeps the limit it holds."


def test_m4_1_an_engine_the_owner_stamped_joins_the_line_by_coordination_and_its_limit_by_priority(j2):
    """J5: the owner's stamp on an engine an idea asked for: Coordination grows its line, Priority gives the limit."""
    W, R, J, _ = j2
    ref = _born(j2)
    W.add_engine(ref, "Do")
    t = W._read(W.ddir(ref) / "coordination.json", None)
    assert (t["by"], t["why"], t["line"][0]) == ("Coordination", "the owner's stamp", "Do")
    granted = [e for e in J.events(ref) if e["action"] == "envelope.granted" and e["recipient"] == "Do"]
    assert len(granted) == 1 and granted[0]["actor"] == "Priority" and granted[0]["payload"]["kept"] is False
    assert W.dept(ref)["envelopes"]["Do"] == {"calls": 240, "usd": 6.0}
    grown = [e for e in J.events(ref) if e["action"] == "timetable.written" and e["payload"].get("grown") == "Do"]
    assert len(grown) == 1 and grown[0]["actor"] == "Coordination"


def test_m4_1_a_born_word_on_the_board_that_names_no_engine_changes_nothing(j2):
    """The fixed trigger 'an engine is born', posted on the board with nothing in it (Identity may inform Coordination
    and Priority), emptying the line, leaving every engine out or touching a limit must fail."""
    W, R, J, _ = j2
    ref = _born(j2)
    path = W.ddir(ref) / "coordination.json"
    before, envs = W._read(path, None), dict(W.dept(ref)["envelopes"])
    assert before["line"] == LINE
    R.post(ref, "Identity", ["Coordination"], "inform", {"word": "born"})
    R.post(ref, "Identity", ["Priority"], "inform", {"word": "born"})
    W.run_until_idle(ref, limit=50)
    heard = [r for r in R.step_rows(ref) if r["step"] in ("coord.table", "priority.grant") and r.get("mode") != "gate"]
    assert sorted(r["engine"] for r in heard) == ["Coordination", "Priority"], "both handlers ran from the board"
    assert W._read(path, None) == before, "the table is not written"
    assert W.dept(ref)["envelopes"] == envs and R.coordination(ref)["line"] == LINE


def test_m4_1_a_born_word_on_the_board_never_rewrites_the_plan_root_registered(j2):
    """A born post on the board that sets Coordination's line to what it names (a line without the required Check, one
    that is not the plan on dept.workflows, one with no version or an older one, an engine nobody stamped), takes the
    table's 'registered' from it, or gives a limit, must fail: from the board the handlers act only on what the record
    already holds, so Root's check and Priority's price stay in front of the line (PRD M4.1, M4.4; A1 hears the word
    by call)."""
    W, R, J, _ = j2
    ref = _born(j2)
    path = W.ddir(ref) / "coordination.json"
    before, envs = W._read(path, None), dict(W.dept(ref)["envelopes"])
    assert (before["line"], before["registered"], W.dept(ref)["workflows"][-1]["engines"]) == (LINE, 1, LINE)
    tables = len([e for e in J.events(ref) if e["action"] == "timetable.written"])
    stray = ({"engines": ["Plan", "Write", "Publish"]},                         # no version, and no Check
             {"engines": ["Plan", "Write", "Publish"], "version": 1},           # not the plan, and no Check
             {"engines": ["Plan", "Write", "Check", "Nobody"], "version": 1},   # not the plan
             {"engines": ["Plan"], "full": False},                              # no version: 'registered' is kept
             {"engines": "Plan", "version": 1},
             {"version": 2}, {"version": 0}, {"version": True}, {"version": "1"},
             {"grow": "Publish"},                                               # on the record, but nobody stamped it
             {"grow": "Do"})                                                    # not on the record
    for pl in stray:
        for to in ("Coordination", "Priority"):
            R.post(ref, "Identity", [to], "inform", dict(pl, word="born"))
        W.run_until_idle(ref, limit=50)
        t = W._read(path, None)
        assert (t["line"], t["registered"], [r["engine"] for r in t["left_out"]]) == (LINE, 1, []), pl
        assert t == before and W.dept(ref)["envelopes"] == envs, pl
    assert len([e for e in J.events(ref) if e["action"] == "timetable.written"]) == tables, "nothing on the ledger"
    heard = [r for r in R.step_rows(ref) if r["step"] in ("coord.table", "priority.grant") and r.get("mode") == "slot"]
    assert len(heard) == 2 * len(stray) and all(r["status"] == "ok" for r in heard), "each handler heard each post"
    # and each says why it did nothing
    def said(code, pl):
        return code({"ref": ref, "dept": W.dept(ref), "post": {"payload": dict(pl, word="born")}}, None, None)["said"]
    assert said(R.coord_table, stray[0]) == "nothing to do: the word born names no plan Root registered"
    assert said(R.coord_table, stray[1]) == "nothing to do: the line it names is not the plan Root registered (v1)"
    assert said(R.coord_table, {"version": 2}) == "nothing to do: the word born names v2, and the plan Root registered last is v1"
    assert said(R.coord_table, {"grow": "Publish"}) == "nothing to do: nobody stamped Publish onto the department's record"
    assert said(R.priority_grant, stray[1]) == "nothing to do: the line it names is not the plan Root registered (v1)"
    assert said(R.priority_grant, {"version": 1}) == "nothing to do: each engine it names holds its limit"
    # the plan Root registered, named by its version, is what the record already holds: the table follows it, and is
    # left as it is
    R.post(ref, "Identity", ["Coordination"], "inform", {"word": "born", "version": 1, "engines": LINE})
    W.run_until_idle(ref, limit=50)
    assert W._read(path, None) == before
    # a table that lost its registration is set again from the record, never from the post: the registered plan whole
    W._write(path, dict(before, line=["Plan", "Write", "Publish"], registered=None, left_out=[R.left_out_row("Check")]))
    R.post(ref, "Identity", ["Coordination"], "inform", {"word": "born", "version": 1})
    W.run_until_idle(ref, limit=50)
    t = W._read(path, None)
    assert (t["by"], t["line"], t["registered"], t["left_out"]) == ("Coordination", LINE, 1, [])
    # a plan on the record that leaves out what the kind requires (one registered before Root checked for it) is not
    # set from the board either
    d = W.dept(ref)
    d["workflows"].append(dict(d["workflows"][-1], version=2, engines=["Plan", "Write", "Publish"]))
    W.save_dept(ref, d)
    assert said(R.coord_table, {"version": 2}) == "nothing to do: the plan leaves out Check, which this kind requires"
    assert W._read(path, None) == t


def test_m4_1_a_line_set_with_no_version_keeps_the_registration_it_follows(j2):
    """set_line writing registered None (a registration that names no version) must fail: the table keeps the plan it
    follows."""
    W, R, J, _ = j2
    ref = _born(j2)
    t = R.set_line(ref, LINE, None, full=False)
    assert (t["line"], t["registered"]) == (LINE, 1)


def _sm3(W, R, ref, j5=()):
    """SM-3: runs of an engine that is on no registered line and was not stamped through J5, the five functions aside."""
    d = W.dept(ref)
    allowed = {n for w in d.get("workflows") or [] for n in w.get("engines") or []} | set(R.FUNCTIONS) | set(j5)
    allowed |= {a.get("engine") for a in W.asks(ref) if a.get("kind") == "engine" and a["status"] == "stamped"}
    return [r["engine"] for r in W.runs(ref) if r["engine"] not in allowed]


KEEP = ["Plan", "Write", "Check"]


def _counter_keeps(monkeypatch, R, keep=KEEP):
    """Priority asks for less on the first plan (the one that names Publish), and says yes to the plan that keeps `keep`."""
    def bargain(prompt):
        if "- Publish:" in prompt:
            return {"answer": "counter", "why": "room for three today", "keep": list(keep)}
        return {"answer": "accept", "why": "the envelope has room"}
    _model(monkeypatch, R, {"priority.bargain": bargain})


def test_m4_2_a_website_counter_keeps_a_subset_and_the_engine_it_cut_never_runs(j2, monkeypatch):
    """The born line running past what Priority granted (Publish ran though the plan left it out) must fail (SM-3)."""
    W, R, J, _ = j2
    _counter_keeps(monkeypatch, R)
    ref = _born(j2)
    assert "proposal.countered" in _actions(J, ref)
    assert W.dept(ref)["workflows"][-1]["engines"] == KEEP
    t = W._read(W.ddir(ref) / "coordination.json", None)
    assert t["line"] == KEEP and [(r["engine"], r["in_line"]) for r in t["left_out"]] == [("Publish", False)]
    assert R.coordination(ref)["line"] == KEEP
    assert W.dept(ref)["engines"] == LINE, "the engine left out stays on the record"
    _stamp_all(W, ref)
    W.run_until_idle(ref, limit=100)
    assert _work(W, ref) == KEEP and "Publish" not in [r["engine"] for r in W.runs(ref)]
    assert _sm3(W, R, ref) == []
    assert any("Left out of the plan: Publish." in s for s in _said(R, ref)), "the plan message names what was left out (Q13)"
    eng = {e["name"]: e for e in W.map_view(ref)["engines"]}
    assert (eng["Publish"]["in_line"], eng["Publish"]["state"]) == (False, "Left out") and eng["Check"]["in_line"] is True


def test_m4_2_a_later_full_registration_sets_the_line_again_and_merges_what_the_owner_added(j2):
    """A J5 engine lost on the next registration, or a dropped engine kept in the line, must fail."""
    W, R, J, _ = j2
    ref = _born(j2)
    W.add_engine(ref, "Do")                                        # J5: the owner stamped it; it reads the Brief, so it goes first
    assert R.coordination(ref)["line"] == ["Do"] + LINE
    d = W.dept(ref)
    R._j2_settle(ref, d, [{"name": n} for n in KEEP], "library", d.get("goal"), "a test")   # a later plan, the whole line
    t = W._read(W.ddir(ref) / "coordination.json", None)
    assert (t["registered"], t["line"]) == (2, ["Do"] + KEEP), t
    assert [r["engine"] for r in t["left_out"]] == ["Publish"]
    assert not [e for e in J.events(ref) if e["action"] == "envelope.granted" and e.get("workflow_ref") == "workflow/2"], \
        "no engine is new to the plans: Priority gives no new limit"
    R._j2_settle(ref, d, [{"name": n} for n in LINE], "library", d.get("goal"), "a test")    # Publish is back in the plan
    t = W._read(W.ddir(ref) / "coordination.json", None)
    assert (t["registered"], t["line"], t["left_out"]) == (3, ["Do"] + LINE, [])
    W.run_until_idle(ref, limit=200)
    assert _sm3(W, R, ref, j5=["Do"]) == []


def _register(W, ref, version, engines):
    """A registration on the department's record, made by hand: the plan the line is checked against when it is written."""
    d = W.dept(ref)
    d["workflows"].append(dict(d["workflows"][-1], version=version, engines=list(engines)))
    W.save_dept(ref, d)


def test_m4_2_a_set_line_that_is_not_full_adds_to_the_line_and_a_faulty_table_keeps_what_was_left_out(j2, monkeypatch):
    W, R, J, _ = j2
    _counter_keeps(monkeypatch, R)
    ref = _born(j2)
    _register(W, ref, 9, ["Plan", "Publish"])     # a registration that adds Publish: the record holding the engine is not one
    t = R.set_line(ref, ["Plan", "Publish"], 9, full=False)
    assert t["line"] == KEEP + ["Publish"] and t["left_out"] == []
    _register(W, ref, 10, KEEP)
    R.set_line(ref, KEEP, 10)
    t = W._read(W.ddir(ref) / "coordination.json", None)
    t["line"] = KEEP + ["Nobody"]                                   # a name the Library does not define: the table is not read
    W._write(W.ddir(ref) / "coordination.json", t)
    assert R.coordination(ref)["line"] == KEEP, "the born line, without the engine the plan left out"


def _table(W, ref):
    return W._read(W.ddir(ref) / "coordination.json", None)


def test_m4_3_coordinations_timetable_is_one_slot_for_each_engine_and_a_grown_engine_adds_one(j2):
    """A timetable that is not on the record, an engine with two slots or none, or a grown engine with no slot must fail."""
    W, R, J, _ = j2
    ref = _born(j2)
    t = _table(W, ref)
    assert [r["engine"] for r in t["timetable"]] == LINE == t["line"]
    rows = {r["engine"]: r for r in t["timetable"]}
    assert [rows[n]["on"] for n in LINE] == ["after Brief v1", "after Site plan v1", "after Pages v1", "after Build v1"]
    assert [rows[n]["of"] for n in LINE] == ["Brief", "Site plan", "Pages", "Build"]
    assert rows["Publish"]["checked"] is True and rows["Plan"]["checked"] is False
    assert [rows[n]["window_min"] for n in LINE] == [15, 30, 5, 10], "each engine's window, from the record"
    assert all(rows[n]["since"] for n in LINE)
    # the record's shape is named once: the table's fields and a slot's fields, in order
    assert set(t) <= set(R.TABLE_FIELDS) and all(list(r) == [k for k in R.SLOT_FIELDS if k in r] for r in t["timetable"])
    written = [e for e in J.events(ref) if e["action"] == "timetable.written"]
    assert [s["on"] for s in written[-1]["payload"]["timetable"]] == [rows[n]["on"] for n in LINE], "the ledger names the slots"
    W.add_engine(ref, "Do")
    t2 = _table(W, ref)
    assert [r["engine"] for r in t2["timetable"]] == ["Do"] + LINE, "the grown engine adds one slot"
    grown = {r["engine"]: r for r in t2["timetable"]}
    assert grown["Do"]["on"] == "after Brief v1" and grown["Do"]["window_min"] == 15, "it has not run on the Brief yet"
    assert all(grown[n]["since"] == rows[n]["since"] for n in LINE), "a slot keeps the time it has been held since"
    lab = _born(j2, ORGANIC, "Lab Co")
    t3 = _table(W, lab)
    assert [(r["engine"], r["on"]) for r in t3["timetable"]] == [("Facts", "after Brief v1"), ("Site", "after Facts v1")]
    assert R.slot_of(ref, "Plan")["on"] == "after Brief v2", "the slot moves on once Plan ran on Brief v1"


def test_m4_3_no_scenario_clashes_in_a_slot_on_any_kind(j2, monkeypatch):
    """SM-11's clash in a slot (two runs on one slot id, or a start while another run is open), in any scenario on any
    kind, must fail; so must an engine run that no registered line or J5 stamp allowed (SM-3)."""
    import functions_view as F
    W, R, J, _ = j2
    refs = [_born(j2)]
    _stamp_all(W, refs[0])                                            # a website, published
    refs.append(_born(j2, ORGANIC, "Lab Co"))                          # an organic line, shaped for the goal
    d, _ = W.create("dref-answers", "Answers", None, kind="default")   # the default kind: one Do engine
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
    W.run_until_idle(d["ref"], limit=300)
    refs.append(d["ref"])
    _counter_keeps(monkeypatch, R)
    refs.append(_born(j2, WEBSITE, "Counter Co"))                      # a website whose plan Priority cut
    W.add_engine(refs[-1], "Do")                                       # and an engine the owner added through J5
    W.owner_ask(refs[-1], "Add a page for the timetable of the algebra classes")
    W.run_until_idle(refs[-1], limit=300)
    for ref in refs:
        W.run_until_idle(ref, limit=100)
        assert "workflow.registered" in _actions(J, ref), ref
        assert [r for r in W.runs(ref) if not r.get("system")], "work ran: %s" % ref
        assert F.slot_clashes(W.runs(ref)) == [], ref
        assert _sm3(W, R, ref, j5=["Do"]) == [], ref
        t = _table(W, ref)
        assert sorted(r["engine"] for r in t["timetable"]) == sorted(t["line"]) and len(t["timetable"]) == len(set(t["line"]))
    assert "Publish" not in [r["engine"] for r in W.runs(refs[-1])]
    # the reader finds a clash when there is one
    run = next(r for r in W.runs(refs[0]) if r.get("slot") and not r.get("system"))
    twice = [run, dict(run, id="r-again")]
    assert [c["why"] for c in F.slot_clashes(twice)] == ["the slot ran twice"]
    open_ = [dict(run, started="2026-10-23T10:00:00+05:30", ended="2026-10-23T10:05:00+05:30"),
             dict(run, id="r-two", slot="Write@site-plan.v9", engine="Write", started="2026-10-23T10:02:00+05:30", ended="2026-10-23T10:03:00+05:30")]
    assert [c["slot"] for c in F.slot_clashes(open_)] == ["Write@site-plan.v9"]


def test_m4_3_the_map_reads_each_engines_slot_off_coordinations_timetable(j2):
    W, R, J, _ = j2
    ref = _born(j2)
    eng = {e["name"]: e for e in W.map_view(ref)["engines"]}
    assert [eng[n]["timetable"]["on"] for n in LINE] == [r["on"] for r in _table(W, ref)["timetable"]]


# ---- PRD M4.4: required engines (Q12: only Check, on the website kind) -----------------------------------------------
def test_m4_4_a_plan_without_check_is_refused_by_roots_check(j2):
    """A website plan that leaves out Check registered, or refused without the check that broke, must fail; a kind that
    marks nothing required runs no such check."""
    W, R, J, _ = j2
    assert R.required_engines({"kind": "website"}) == ["Check"]
    assert R.required_engines({"kind": "organic"}) == [] and R.required_engines({"kind": "default"}) == []
    ref = _born(j2)
    d = W.dept(ref)
    before = len(d["workflows"])
    out = R._j2_settle(ref, d, [{"name": n} for n in ("Plan", "Write", "Publish")], "library", d.get("goal"), "a test")
    assert "sent the workflow back" in out["said"]
    assert len(W.dept(ref)["workflows"]) == before, "nothing registered"
    blocked = [e for e in J.events(ref) if e["action"] == "workflow.blocked"][-1]
    # Publish reads the Build that Check files, so the plan also breaks reads_known (every standard reads a Library line too)
    assert blocked["payload"]["faults"] == ["Publish reads Build, which nothing before it writes",
                                            "the plan leaves out Check, which this kind of department requires"]
    assert [c["check"] for c in blocked["payload"]["checks"] if not c["passed"]] == ["reads_known", "required_kept"]
    assert {"check": "required_kept", "passed": False, "why": "the plan leaves out Check, which this kind of department requires"} in blocked["payload"]["checks"]
    assert R._root_check(ref, d, [{"name": n} for n in LINE], "library") == []
    assert R.coordination(ref)["line"] == LINE, "the line stays what was registered"
    # the kind's mark is data, checked when the definitions load: a required engine is one of the kind's own line
    bad = dict(R.defs())
    bad["kinds"] = dict(bad["kinds"], website=dict(bad["kinds"]["website"], required=["Nobody"]))
    assert "kinds, website: required names engines of its own line" in R.validate(bad)


def test_m4_4_a_refused_website_plan_registers_on_the_next_proposal_with_check_in_it(j2, monkeypatch):
    """Reshaping a website's refused plan (a shaped line is made of names new to the Library, so it can never carry
    Check, and is refused for the same fault until the cycle blocks) must fail: Adaptation takes the Library's line
    again, with Check, and it registers."""
    W, R, J, _ = j2
    ref = _born(j2)
    d = W.dept(ref)
    seen = len(J.events(ref))
    R._j2_settle(ref, d, [{"name": n} for n in ("Plan", "Write", "Publish")], "library", d.get("goal"), "a test")
    W.run_until_idle(ref, limit=300)
    after = J.events(ref)[seen:]
    assert [e["action"] for e in after].count("workflow.blocked") == 1, "refused once, and once only"
    assert [e["payload"]["source"] for e in after if e["action"] == "proposal.created"] == ["library"]
    assert W.dept(ref)["workflows"][-1]["engines"] == LINE and J.status(ref)["state"] == "running"
    assert R.coordination(ref)["line"] == LINE
    # Root's check refuses a website's first plan for another reason: the next proposal is the Library's again, and it
    # registers with Check in it (it was blocked after three shaped tries before)
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["the line reaches outside without a rule"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    other = _born(j2, org="Refused Co")
    acts = _actions(J, other)
    assert acts.count("workflow.blocked") == 1 and "workflow.registered" in acts and J.status(other)["state"] != "blocked"
    assert [e["payload"]["source"] for e in J.events(other) if e["action"] == "proposal.created"] == ["library", "library"]
    assert W.dept(other)["workflows"][-1]["engines"] == LINE
    # the repair route itself: the Library's line, without a name the Library has no engine for, the required one put
    # back at its place on the kind's line; none for a kind that requires nothing
    assert R._library_repair({"kind": "website"}, ["Plan", "Nobody Knows", "Write", "Publish"]) == LINE
    assert R._library_repair({"kind": "organic"}, ["Facts"]) is None
    # a record without the required engine: the Library's line brings it back, and Adaptation brings it onto the record
    third = _born(j2, org="Thin Co", settle=False)
    rec = W.dept(third)
    rec["engines"] = ["Plan", "Write", "Publish"]
    W.save_dept(third, rec)
    W.run_until_idle(third, limit=300)
    assert W.dept(third)["workflows"][-1]["engines"] == LINE and W.dept(third)["engines"] == LINE
    assert any(r["engine"] == "Adaptation" and "Check" in str(r.get("what")) for r in W.runs(third) if r.get("system"))


def test_m4_4_a_counter_that_drops_check_goes_to_identity_as_a_conflict(j2, monkeypatch):
    """Adaptation taking a counter that leaves out Check, or the conflict going anywhere but Identity, must fail; the ask
    says it in the owner's words on the record itself."""
    W, R, J, _ = j2
    _counter_keeps(monkeypatch, R, keep=["Plan", "Write", "Publish"])
    ref = _born(j2)
    acts = _actions(J, ref)
    assert "proposal.countered" in acts and "workflow.registered" not in acts
    raised = next(e for e in J.events(ref) if e["action"] == "conflict.raised")
    conflict = next(p for p in R.board(ref) if (p.get("payload") or {}).get("word") == "conflict")
    assert conflict["src"] == "Adaptation" and conflict["dst"] == ["Identity"]
    assert "leave out Check, which this kind of department requires" in conflict["payload"]["why"]
    assert [e["name"] for e in conflict["payload"]["engines"]] == LINE, "the plan put to Identity is the whole one"
    assert raised["seq"] > next(e for e in J.events(ref) if e["action"] == "proposal.countered")["seq"]
    # Identity could not settle it from the goal and the rules (offline): one ask, in the owner's words, and nothing ran
    ask = [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "conflict"]
    assert len(ask) == 1 and _work(W, ref) == []
    import owner_words
    said = owner_words.plain(ask[0]["text"])
    assert "Priority asked for less" in ask[0]["text"] and "countered" not in said.lower(), said
    # the owner stamps it: the plan as proposed, Check in it, is registered and runs
    _stamp_all(W, ref, kind="conflict")
    assert W.dept(ref)["workflows"][-1]["engines"] == LINE
    assert "Check" in R.coordination(ref)["line"]
