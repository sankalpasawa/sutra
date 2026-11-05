"""The check runner (WP E6, function-nodes.md sections 4 and 5): `Evidence` built from hook data, reply-phase and turn-phase rounds,
`CheckResult` values and exit codes 0, 1 and 127, `RECOVERED:` / `WAIVED:`, closed versus verify_failed, at most 3 close runs.
The 14 checks themselves are tested in test_engine_fn_registry.py; here they are only run through the runner."""
import pytest

from sutra_app.engine.fnodes.checks import DEFERRED, RECOVERED, WAIVED, CheckRunner, Round, TurnBuffer
from sutra_app.engine.fnodes.declare import declare
from sutra_app.engine.fnodes.registry import REGISTRY, CheckArgsError, Outcome, UnknownCheck
from sutra_app.engine.hooks import CallInfo, TurnInfo, TurnOutcome
from sutra_app.library.atom import MAX_ATTEMPTS, Atom, CheckResult, close_atom, open_atom
from sutra_app.library.node import load_function_specs

SPECS = load_function_specs()
RUNNER = CheckRunner()
GOOD_CHARTER = {"statement": "A one-page site for Brew Lab", "done_when": ["Menu is shown", "Hours are shown", "A map is shown"]}
TWO_ITEMS = {"statement": "A site", "done_when": ["a", "b"]}
INTAKE_REPLY = {"say": "ok", "reason": "r", "next": "Adaptation", "enough": True, "to_requester": "Your site is on its way.", "to_agents": "@Adaptation go",
                "goal": {"kind": "site", "site_name": "Brew Lab", "statement": "A one-page site", "done_when": ["a", "b", "c"]}}
ASK_REPLY = {"say": "ok", "reason": "r", "next": "Requester", "enough": False, "questions": [{"question": "Which colour?"}], "to_requester": "Which colour?"}


def turn(function="identity", kind="intake", **fields) -> TurnInfo:
    base = dict(run_id="j2-run-1", dept_id="web", turn_no=1, function=function, kind=kind, step=1, step_label="J2.x", cycle=1, task="t", context=[])
    return TurnInfo(**{**base, **fields})


def call(function="identity", reply=None, **fields) -> CallInfo:
    base = dict(call_no=1, function=function, step=1, purpose="agent_turn", model="m-1", seconds=0.5, inputs=[], reply=reply)
    return CallInfo(**{**base, **fields})


def opened(function="identity", kind="intake", **kw) -> Atom:
    t = turn(function, kind)
    return open_atom(declare(t, SPECS.specs[function], **kw), id="a-abc-01", node_id=f"web.{function}", now=10).atom


def intake_buffer(goal=GOOD_CHARTER, **extra) -> TurnBuffer:
    buf = TurnBuffer(turn=turn())
    buf.add_call(call(reply=INTAKE_REPLY))
    buf.add_message({"id": 2, "who": "identity", "text": "@Adaptation go", "next": "adaptation"})
    buf.add_record("goal.json", goal)
    return buf


class Stub:
    """A registry stand-in: `outcomes` maps a check name to an Outcome or an exception to raise."""

    def __init__(self, outcomes, phases=("turn",)):
        self.outcomes, self.phases = outcomes, phases

    def __contains__(self, name):
        return name in self.outcomes

    def __getitem__(self, name):
        return type("S", (), {"phases": self.phases if isinstance(self.phases, tuple) else self.phases[name]})()

    def run(self, name, ev, args=()):
        out = self.outcomes[name]
        if isinstance(out, BaseException):
            raise out
        return out


def stub_atom(*check_names) -> Atom:
    """An open atom whose checks are the given registry names (they take no arguments), run against a Stub."""
    template = SPECS.specs["audit"].atom_templates[-1].model_dump() | {"name": "audit", "checks": [{"name": n, "args": []} for n in check_names]}
    spec = SPECS.specs["audit"].evolve(atom_templates=[template, SPECS.specs["audit"].atom_templates[-1]])
    return open_atom(declare(turn("audit", "audit"), spec, work="manual"), id="a-abc-02", node_id="web.audit", now=10).atom


# ---- the evidence -----------------------------------------------------------------------------------------------------

def test_evidence_is_built_from_the_buffer_and_copies_what_j2_keeps_changing():
    buf = TurnBuffer(turn=turn(), before={"workflows.json": [{"id": "W-1"}]}, owners={"a-x-01": "web.audit"})
    reply = {"enough": True}
    buf.add_call(call(reply=reply))
    message = {"id": 3, "who": "identity", "text": "hi", "schedule": ["W-1"]}
    buf.add_message(message)
    data = {"statement": "s", "done_when": ["a"]}
    buf.add_record("goal.json", data)
    buf.add_record("summary.json", {"x": 1})
    reply["enough"], message["text"], data["statement"] = False, "changed", "changed"      # J2 keeps mutating its objects
    message["schedule"].append("W-2")
    ev = RUNNER.evidence(buf)
    assert ev.reply == {"enough": True} and ev.replies == [{"enough": True}] and ev.call.call_no == 1
    assert ev.posted == [{"id": 3, "who": "identity", "text": "hi", "schedule": ["W-1"], "after_reply": 1}]
    assert ev.records["goal.json"]["statement"] == "s" and ev.records["workflows.json"] == [{"id": "W-1"}]        # saved, else as read
    assert "summary.json" not in ev.records and ev.saved_names == {"goal.json", "summary.json"}
    assert ev.before == {"workflows.json": [{"id": "W-1"}]} and ev.owners == {"a-x-01": "web.audit"} and ev.outcome is None
    assert buf.model == "m-1"


def test_posted_messages_know_how_many_replies_had_arrived():
    buf = TurnBuffer(turn=turn("adaptation", "propose"))
    buf.add_message({"id": 1, "who": "system", "text": "Validator rejected"})
    buf.add_call(call("adaptation", {"workflows": []}))
    buf.add_message({"id": 2, "who": "system", "text": "later"})
    assert [m["after_reply"] for m in buf.posted] == [0, 1]


def test_a_latest_call_with_no_usable_reply_leaves_the_evidence_without_replies():
    buf = TurnBuffer(turn=turn())
    buf.add_call(call(reply={"enough": True}))
    buf.add_call(call(call_no=2, reply=None))
    ev = RUNNER.evidence(buf)
    assert ev.reply is None and ev.replies == [] and ev.call.call_no == 2
    rnd = RUNNER.round(opened(), buf, "reply", 11)
    assert rnd.runs[0].name == "reply-valid" and rnd.runs[0].result.exit_code == 1 and "no reply" in rnd.runs[0].result.evidence


def test_the_outcome_is_part_of_the_evidence_from_the_turn_phase_on():
    buf = intake_buffer()
    out = TurnOutcome(result="ok", messages=[2])
    assert RUNNER.evidence(buf, outcome=out).outcome == out and RUNNER.evidence(buf).outcome is None


# ---- phases and results -----------------------------------------------------------------------------------------------

def test_reply_phase_judges_reply_checks_and_defers_the_rest():
    rnd = RUNNER.round(opened(), intake_buffer(), "reply", 11)
    assert [r.name for r in rnd.runs] == ["reply-valid", "turn-posted", "charter-stamp", "audience-split"]
    assert [r.deferred for r in rnd.runs] == [False, True, True, False]
    deferred = rnd.runs[1].result
    assert (deferred.exit_code, deferred.evidence) == (0, DEFERRED)
    assert rnd.runs[2].result.evidence == DEFERRED
    assert rnd.runs[0].passed and rnd.runs[0].outcome.evidence == "ok"        # reply-valid answered for real, not deferred


def test_reply_phase_failure_is_exit_1_with_the_checks_words():
    buf = TurnBuffer(turn=turn())
    buf.add_call(call(reply={"enough": True}))                                # no `next`, `reason`: not a valid intake reply
    rnd = RUNNER.round(opened(), buf, "reply", 11)
    assert not rnd.passed and [r.name for r in rnd.failing] == ["reply-valid"]
    assert rnd.failing[0].result.exit_code == 1 and rnd.failing[0].outcome.ok is False
    assert rnd.reason.startswith("verify failed: reply-valid: ") and "Field required" in rnd.reason


def test_turn_phase_judges_every_check_on_the_whole_turn():
    buf = intake_buffer()
    rnd = RUNNER.round(opened(), buf, "turn", 12, outcome=TurnOutcome(result="ok", messages=[2]))
    assert [r.result.exit_code for r in rnd.runs] == [0, 0, 0, 0] and rnd.passed and not any(r.deferred for r in rnd.runs)
    assert all(r.result.attempt == 1 and r.result.ts == 12 for r in rnd.runs) and rnd.concerns == []


def test_turn_phase_failure_names_the_failing_check_in_the_reason():
    rnd = RUNNER.round(opened(), intake_buffer(TWO_ITEMS), "turn", 12, outcome=TurnOutcome(result="ok", messages=[2]))
    failing = {r.name: r.result for r in rnd.failing}
    assert "charter-stamp" in failing and failing["charter-stamp"].evidence == "fewer than 3 'done when' criteria"
    assert "charter-stamp: fewer than 3 'done when' criteria" in rnd.reason


def test_results_are_numbered_by_the_next_close_run_and_a_fourth_run_is_refused():
    t = turn()
    atom = open_atom(declare(t, SPECS.specs["identity"]), id="a-abc-01", node_id="web.identity", now=10).atom
    buf = intake_buffer(TWO_ITEMS)
    out = TurnOutcome(result="ok", messages=[2])
    for expected in (1, 2, 3):
        rnd = RUNNER.round(atom, buf, "turn", 20 + expected, outcome=out)
        assert {r.result.attempt for r in rnd.runs} == {expected}
        tr = close_atom(atom, rnd.results, 20 + expected)
        assert tr.outcome == "verify_failed"
        atom = tr.atom
    assert atom.attempt == MAX_ATTEMPTS
    with pytest.raises(ValueError, match="close runs"):
        RUNNER.round(atom, buf, "turn", 30, outcome=out)


def test_a_round_decides_closed_or_verify_failed_through_the_library():
    atom = stub_atom("pass-needs-proof")
    ok = CheckRunner(Stub({"pass-needs-proof": Outcome(ok=True, evidence="fine")})).round(atom, TurnBuffer(turn=turn("audit", "audit")), "turn", 20)
    assert close_atom(atom, ok.results, 20).outcome == "closed"
    bad = CheckRunner(Stub({"pass-needs-proof": Outcome(ok=False, evidence="no")})).round(atom, TurnBuffer(turn=turn("audit", "audit")), "turn", 20)
    tr = close_atom(atom, bad.results, 20)
    assert tr.outcome == "verify_failed" and tr.atom.state == "open" and tr.atom.attempt == 1


# ---- RECOVERED, WAIVED, na and exit 127 ---------------------------------------------------------------------------------

def test_words_put_recovered_or_waived_in_front():
    assert CheckRunner.words(Outcome(ok=True, evidence="dropped W-9", changed=("dropped W-9",))) == RECOVERED + "dropped W-9"
    assert CheckRunner.words(Outcome(ok=True, evidence="below the gate", waived=True)) == WAIVED + "below the gate"
    assert CheckRunner.words(Outcome(ok=True, evidence="plain")) == "plain"
    assert CheckRunner.words(Outcome(ok=False, evidence="broken")) == "broken"
    assert CheckRunner.words(Outcome(ok=True, evidence="n/a", na=True)) == "n/a"
    assert len(CheckRunner.words(Outcome(ok=True, evidence="x" * 2000, waived=True))) == 2000


def test_a_round_marks_recovered_and_waived_results_and_still_passes():
    atom = stub_atom("order-registered", "judge-gate", "workable")
    stub = Stub({"order-registered": Outcome(ok=True, evidence="dropped W-9", changed=("dropped W-9",)),
                 "judge-gate": Outcome(ok=True, evidence="plan 0.7 < 0.80", waived=True), "workable": Outcome(ok=True, evidence="not applicable", na=True)})
    rnd = CheckRunner(stub).round(atom, TurnBuffer(turn=turn("audit", "audit")), "turn", 20)
    assert rnd.passed and [r.result.evidence for r in rnd.runs][-3:] == [RECOVERED + "dropped W-9", WAIVED + "plan 0.7 < 0.80", "not applicable"]
    assert [r.result.exit_code for r in rnd.runs][-3:] == [0, 0, 0] and rnd.concerns == ["order-registered", "judge-gate"]
    assert close_atom(atom, rnd.results, 20).outcome == "closed"


def test_real_checks_close_recovered_and_waived_through_the_runner():
    waived = TurnBuffer(turn=turn())
    waived.add_message({"id": 8, "who": "system", "text": "Charter accepted after two attempts; the validator's concern is on record."})
    waived.add_record("goal.json", TWO_ITEMS)
    waived.add_message({"id": 9, "who": "identity", "text": "x", "next": "adaptation"})
    rnd = RUNNER.round(opened(), waived, "turn", 12, outcome=TurnOutcome(result="ok"))
    stamp = next(r for r in rnd.runs if r.name == "charter-stamp")
    assert stamp.passed and stamp.result.evidence == WAIVED + "fewer than 3 'done when' criteria" and stamp.outcome.waived

    schedule = opened("coordination", "schedule", workflows=[{"id": "W-1", "status": "registered"}])
    buf = TurnBuffer(turn=turn("coordination", "schedule"), before={"workflows.json": [{"id": "W-1", "status": "registered"}]})
    buf.add_call(call("coordination", {"say": "@Priority s", "rule": "r", "order": ["W-1", "W-9"], "holds": [], "next": "Priority"}))
    buf.add_message({"id": 4, "who": "coordination", "text": "@Priority Schedule", "next": "priority", "schedule": ["W-1"]})
    rnd = RUNNER.round(schedule, buf, "turn", 12, outcome=TurnOutcome(result="ok"))
    ordered = next(r for r in rnd.runs if r.name == "order-registered")
    assert rnd.passed and ordered.result.evidence.startswith(RECOVERED) and "dropped W-9" in ordered.result.evidence


def test_na_is_exit_0_with_the_checks_own_words():
    buf = TurnBuffer(turn=turn())
    buf.add_call(call(reply=ASK_REPLY))
    buf.add_message({"id": 2, "who": "identity", "text": "asking", "next": "user"})
    rnd = RUNNER.round(opened(), buf, "turn", 12, outcome=TurnOutcome(result="paused"))
    stamp = next(r for r in rnd.runs if r.name == "charter-stamp")
    assert stamp.result.exit_code == 0 and stamp.result.evidence == "the owner is asked" and stamp.outcome.na


@pytest.mark.parametrize("raised, text", [
    (UnknownCheck("nope"), "UnknownCheck"), (CheckArgsError("wrong arity"), "wrong arity"), (RuntimeError("boom"), "RuntimeError: boom"),
])
def test_a_check_that_cannot_run_is_exit_127(raised, text):
    atom = stub_atom("finding-per-item")
    rnd = CheckRunner(Stub({"finding-per-item": raised})).round(atom, TurnBuffer(turn=turn("audit", "audit")), "turn", 20)
    result = rnd.runs[-1].result
    assert result.exit_code == 127 and text in result.evidence and "finding-per-item" in result.evidence
    assert not rnd.passed and close_atom(atom, rnd.results, 20).outcome == "verify_failed"


def test_a_name_the_registry_does_not_have_is_exit_127_in_every_phase():
    template = SPECS.specs["audit"].atom_templates[-1].model_dump() | {"name": "audit", "checks": [{"name": "file-exists", "args": ["site/index.html"]}]}
    spec = SPECS.specs["audit"].evolve(atom_templates=[template, SPECS.specs["audit"].atom_templates[-1]])
    atom = open_atom(declare(turn("audit", "audit"), spec), id="a-abc-03", node_id="web.audit", now=10).atom
    for phase in ("reply", "turn"):
        rnd = RUNNER.round(atom, TurnBuffer(turn=turn("audit", "audit")), phase, 20)
        last = rnd.runs[-1]
        assert last.name == "file-exists" and last.result.exit_code == 127 and "no runner" in last.result.evidence


def test_evidence_that_cannot_be_built_fails_every_check_with_exit_127():
    buf = TurnBuffer(turn=turn())
    buf.owners = {"a-x-01": 5}                                      # an owner must be a node id string
    rnd = RUNNER.round(opened(), buf, "turn", 20)
    assert [r.result.exit_code for r in rnd.runs] == [127] * 4 and "could not be built" in rnd.runs[0].result.evidence


def test_the_abandon_reason_is_bounded_and_lists_each_failing_check():
    atom = stub_atom("pass-needs-proof", "finding-per-item")
    stub = Stub({"pass-needs-proof": Outcome(ok=False, evidence="a" * 2000), "finding-per-item": Outcome(ok=False, evidence="b")})
    rnd = CheckRunner(stub).round(atom, TurnBuffer(turn=turn("audit", "audit")), "turn", 20)
    assert len(rnd.reason) == 600 and rnd.reason.startswith("verify failed: pass-needs-proof: aaa")
    short = CheckRunner(Stub({"pass-needs-proof": Outcome(ok=False, evidence=""), "finding-per-item": Outcome(ok=False, evidence="b")})).round(
        atom, TurnBuffer(turn=turn("audit", "audit")), "turn", 20)
    assert short.reason == "verify failed: pass-needs-proof: exit 1; finding-per-item: b"
    assert isinstance(short, Round) and CheckResult(attempt=1, exit_code=1, ts=1).evidence == ""


def test_the_runner_uses_the_frozen_registry_by_default():
    assert CheckRunner().registry is REGISTRY
