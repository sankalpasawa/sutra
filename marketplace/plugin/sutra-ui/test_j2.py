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


def test_steps_6_to_8_the_runs_the_audit_and_the_goal_are_on_the_ledger(j2):
    """A ledger that stops at registration, or a goal reached twice, must fail."""
    W, R, J, _ = j2
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
    _, _, J, _ = j2
    ref = _born(j2)
    J.note(ref, 6, "Plan", "Coordination", "run.step_recorded", "recorded", "A step.", "private-1",
           {"reasoning": "hidden", "token": "abc", "kept": {"password": "x", "shown": 1}})
    blob = str(J.events(ref)[-1]) + str(J.activity(ref))
    assert "hidden" not in blob and "abc" not in blob and "'shown': 1" in blob
