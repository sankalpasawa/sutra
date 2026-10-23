"""Behavioral contract for J2: the five functions work toward the identity's goal (the department page, section J2).

Each test is one row of that section: a step of the happy path, or an edge. The departments here are born the way a
person makes them (founded, asked for, set up by Root), so what is tested is the lifecycle a real department lives,
on its real board, and not a record written by hand.
"""
import importlib
import threading

import pytest

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
    assert W.dept(ref)["workflows"] == [{"version": 1, "engines": LINE, "source": "library", "registered": W.dept(ref)["workflows"][0]["registered"], "by": "Root"}]
    assert J.status(ref)["workflow"] == LINE
    assert any("The plan is set: Plan -> Write -> Check -> Publish" in s for s in _said(R, ref))


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
    """A ledger that stops at registration, or a goal reached twice, must fail. Audit's judge reads with a model here:
    only a version the model read can clear done-when (M0.3)."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}})
    ref = _born(j2)
    _stamp_all(W, ref)                                           # the first publish: a born rule says ask
    acts = _actions(J, ref)
    for engine in LINE:
        ran = [e["action"] for e in J.events(ref) if e.get("workflow_ref") == engine]
        assert ran == ["slot.assigned", "run.started", "artifact.filed", "run.completed"], (engine, ran)
    assert acts[-2:] == ["audit.finding_filed", "goal.reached"]
    assert acts.count("goal.reached") == 1
    reached = J.events(ref)[-1]
    assert reached["actor"] == "Identity" and reached["evidence_refs"] == [{"artifact": "Live site", "version": 1}]
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
    monkeypatch.setitem(R.CODE, "audit_pick", old)
    row = R.run_engine(ref, "Audit", {"v": 4}, "Audit@live-site.v4")
    assert row["status"] == "ok" and "not sampled" in row["what"]
    unread = [e for e in J.events(ref) if e["action"] == "audit.not_read"]
    assert [e["evidence_refs"][0]["version"] for e in unread] == [1, 4]
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["step"] == 7


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
    assert "Priority refused the plan: no room in the envelope today" in asks[0]["text"]
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
    assert any("The plan is dropped on your refusal" in s for s in _said(R, ref))


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
    assert any("Root's check refused the plan" in s and "reshaping" in s for s in _said(R, ref))
    assert len(W.dept(ref)["workflows"]) == 1


def test_j2_4_after_two_repairs_the_owner_is_told_and_nothing_runs(j2, monkeypatch):
    W, R, J, _ = j2
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: ["the line reaches outside without a rule"])
    ref = _born(j2, ORGANIC, "Lab Co")
    acts = _actions(J, ref)
    assert acts.count("workflow.blocked") == J.REPAIRS + 1 and "workflow.registered" not in acts
    assert J.status(ref)["state"] == "blocked" and _work(W, ref) == []
    assert any("refused the plan 3 times" in s for s in _said(R, ref))


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


SHAPED_CHECKS = ["names an engine", "one to six engines", "each engine named", "names unique", "names new to the Library",
                 "first reads the Brief", "each reads what one before it wrote", "each writes something new"]


def test_m0_7_the_validated_event_lists_the_checks_that_ran_for_a_library_and_a_shaped_line(j2, monkeypatch):
    """A fixed list of check names, written whatever ran (a Library line was said to pass checks only a shaped line
    runs), must fail."""
    W, R, J, _ = j2
    ran, real = [], R._root_checks

    def spy(*a):
        out = real(*a)
        ran.append(out)
        return out
    monkeypatch.setattr(R, "_root_checks", spy)
    lib = _born(j2)
    checks = next(e for e in J.events(lib) if e["action"] == "workflow.validated")["payload"]["checks"]
    assert checks == ran[-1]
    assert [(c["check"], c["passed"]) for c in checks] == [("names an engine", True), ("engines known", True)]
    shaped = _born(j2, ORGANIC, "Lab Co")
    checks = next(e for e in J.events(shaped) if e["action"] == "workflow.validated")["payload"]["checks"]
    assert checks == ran[-1]
    assert [c["check"] for c in checks] == SHAPED_CHECKS and all(c["passed"] and c["why"] for c in checks)


def test_m0_7_a_refusal_lists_the_checks_that_ran_and_the_one_that_failed(j2, monkeypatch):
    W, R, J, _ = j2
    ref = _born(j2)
    d = W.dept(ref)
    R._j2_settle(ref, d, [{"name": "Plan"}, {"name": "Nobody Knows"}], "library", d.get("goal"), "a test")
    blocked = [e for e in J.events(ref) if e["action"] == "workflow.blocked"][-1]
    assert blocked["payload"]["faults"] == ["the Library has no engine named Nobody Knows"]
    assert blocked["payload"]["checks"] == [{"check": "names an engine", "passed": True, "why": "the workflow names its engines"},
                                            {"check": "engines known", "passed": False, "why": "the Library has no engine named Nobody Knows"}]
    # a check put in Root's place is listed as it ran, beside the standards
    monkeypatch.setattr(R, "_root_check", lambda ref, d, engines, source: ["the line reaches outside without a rule"])
    lab = _born(j2, ORGANIC, "Lab Co")
    first = next(e for e in J.events(lab) if e["action"] == "workflow.blocked")
    assert [c["check"] for c in first["payload"]["checks"]] == SHAPED_CHECKS + ["Root's check"]
    assert first["payload"]["checks"][-1] == {"check": "Root's check", "passed": False, "why": "the line reaches outside without a rule"}


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
