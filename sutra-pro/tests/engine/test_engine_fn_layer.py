"""The function-node layer (WP E6, function-nodes.md sections 5 and 9, engine design 4.3a): hook sequences against fake J2 events.
Open, fail, close; refused; waived; recovered; abandon at run end; the manual atom; overhead binding; errors swallowed;
`touches_miss` only logs; the factory. Every `atom` line the layer writes is parsed by ORCH's strict `RunAtom` model."""
import itertools
import json
from pathlib import Path

import pytest

from sutra_app.engine import llm
from sutra_app.engine.events import EventWriter
from sutra_app.engine.fnodes.layer import NODE_MODES, WRITE_TERMS, FunctionNodeHooks, factory, writable_records
from sutra_app.engine.hooks import CallInfo, EventHooks, TurnInfo, TurnOutcome
from sutra_app.library.atom import MAX_ATTEMPTS
from sutra_app.library.node import FunctionSpecsError, load_function_specs
from sutra_app.library.types import FUNCTIONS, atom_sid, overhead_atom_id
from sutra_app.orchestrator.models import parse_event

SPECS = load_function_specs()
RUN_ID = "j2-20261104-100004-7f3a"
APPROVAL = {"clause": "c", "decision": "ASK", "say": "ask"}                      # a valid Identity approval reply
ASK_REPLY = {"say": "ok", "reason": "r", "next": "Requester", "enough": False, "questions": [{"question": "Which colour?"}],
             "to_requester": "Which colour?"}
GOOD_GOAL = {"statement": "A one-page site", "done_when": ["a", "b", "c"]}
TWO_ITEMS = {"statement": "A site", "done_when": ["a", "b"]}
SCHEDULE = {"say": "@Priority Schedule W-1.", "rule": "dependencies first", "order": ["W-1"], "holds": [], "next": "Priority"}


class Rig:
    """Hooks over a real EventWriter in a temp run folder, with a counting clock and a counting notify."""

    def __init__(self, run_dir: Path, **kw):
        self.run_dir = run_dir
        self.writer = EventWriter(run_dir)
        self.notified = 0
        self.ticks = itertools.count(100)
        self.hooks = FunctionNodeHooks(self.writer, self._notify, clock=lambda: next(self.ticks), **kw)
        self.turn_no = 0

    def _notify(self):
        self.notified += 1

    def start(self):
        self.hooks.run_started({"run_id": RUN_ID, "dept_id": "web"})

    def turn(self, function="identity", kind="approval", **fields) -> TurnInfo:
        self.turn_no += 1
        base = dict(run_id=RUN_ID, dept_id="web", task_id="tsk_1", turn_no=self.turn_no, function=function, kind=kind, step=1,
                    step_label="J2.x test", cycle=1, task="why", context=[("charter", "c")])
        t = TurnInfo(**{**base, **fields})
        self.hooks.turn_started(t)
        return t

    def call(self, function="identity", reply=APPROVAL, **fields):
        base = dict(call_no=1, function=function, step=1, purpose="agent_turn", model="model-1", seconds=0.1, inputs=[], reply=reply)
        self.hooks.call_finished(CallInfo(**{**base, **fields}))

    def say(self, who="identity", text="hello", id=1, **meta):
        self.hooks.message_posted({"id": id, "who": who, "text": text, **meta})

    def finish(self, t, result="ok", **fields):
        self.hooks.turn_finished(t, TurnOutcome(result=result, **fields))

    def good_turn(self, function="identity", kind="approval", reply=APPROVAL, **fields):
        """A turn that passes every check: one valid reply, one routed message."""
        t = self.turn(function, kind, **fields)
        self.call(function, reply)
        self.say(function, "done", id=self.turn_no * 10, next="adaptation")
        self.finish(t, messages=[self.turn_no * 10])
        return t

    def lines(self, name="events.jsonl") -> list[dict]:
        path = self.run_dir / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def atoms(self) -> list[dict]:
        out = []
        for line in self.lines():
            parse_event(line, strict=True)           # ORCH's closed model: the engine and the server agree on every line
            if line["t"] == "atom":
                out.append(line)
        return out

    def outcomes(self) -> list[str]:
        return [e["outcome"] for e in self.atoms()]

    def trace(self, type_: str) -> list[dict]:
        return [t["data"] for t in self.lines("trace.jsonl") if t["type"] == type_]


@pytest.fixture
def rig(run_dir, llm_reset):
    r = Rig(run_dir)
    r.start()
    yield r
    r.writer.close()


# ---- open, close ------------------------------------------------------------------------------------------------------

def test_a_good_turn_opens_and_closes_one_atom_with_card_and_ledger(rig):
    rig.good_turn()
    opened, closed = rig.atoms()
    sid = atom_sid(RUN_ID, "web.identity")
    assert (opened["node"], opened["outcome"], opened["atom"]["id"]) == ("web.identity", "opened", f"a-{sid}-01")
    assert opened["card"]["label"] == "WORK ATOM OPEN" and opened["ledger"] is None and opened["atom"]["schema"] == "work-atom/0.3"
    assert opened["atom"]["status"] == "open" and opened["atom"]["work_kind"] == "llm" and opened["atom"]["verify_template"] == "reply-valid"
    assert opened["atom"]["body"]["task_id"] == "tsk_1" and opened["atom"]["body"]["session_id"] == sid and opened["atom"]["body"]["department_id"] == "web"
    assert (closed["outcome"], closed["atom"]["status"], closed["atom"]["closed_by"], closed["atom"]["attempt"]) == ("closed", "closed", "verify", 1)
    assert closed["card"]["label"] == "WORK ATOM CLOSED" and closed["ledger"]["status"] == "closed" and closed["ledger"]["atom_id"] == opened["atom"]["id"]
    assert closed["atom"]["body"]["model"] == "model-1" and closed["atom"]["ts_open"] < closed["atom"]["ts_closed"]
    assert rig.hooks.open_atoms == {} and rig.notified > 0 and rig.hooks.errors == []


def test_declared_goal_checks_and_context_are_in_the_stored_atom(rig):
    t = rig.turn()
    body = rig.atoms()[0]["atom"]["body"]
    assert body["goal"] == "The owner's answer is read and passed on" and body["outputs"] == ["charter, rule, question"]
    assert [c["template"] for c in body["verify"]["checks"]] == ["reply-valid", "turn-posted", "audience-split"]
    assert body["context"] == ["charter: c"] and body["work"]["steps"] == "J2.x test" and len(body["constraints"]) == 9
    rig.finish(t)


def test_ids_count_per_node_and_every_open_consumes_a_number(rig):
    rig.good_turn()
    rig.good_turn()
    rig.good_turn("audit", "dispute", reply={"say": "ok"})
    ids = [e["atom"]["id"] for e in rig.atoms() if e["outcome"] == "opened"]
    assert [i.rpartition("-")[2] for i in ids] == ["01", "02", "01"]
    assert ids[0].split("-")[1] != ids[2].split("-")[1]                      # the sid names the node


def test_the_atom_is_bound_for_cost_during_the_turn_and_the_overhead_key_after(rig):
    overhead = overhead_atom_id(RUN_ID)
    assert llm.bound_atom() == overhead                                      # run_started
    t = rig.turn()
    bound = llm.bound_atom()
    assert bound == rig.atoms()[0]["atom"]["id"] and bound != overhead
    rig.call()
    assert llm.bound_atom() == bound                                          # a try does not unbind
    rig.say(next="adaptation")
    rig.finish(t)
    assert llm.bound_atom() == overhead


def test_a_failed_reply_is_a_try_of_the_same_atom(rig):
    t = rig.turn()
    rig.call(reply={"say": "ask"})                                            # not a valid approval: no clause or decision
    failed = rig.atoms()[-1]
    assert (failed["outcome"], failed["atom"]["status"], failed["atom"]["attempt"], failed["card"]["label"]) == ("verify_failed", "open", 1, "VERIFY FAILED")
    assert failed["ledger"] is None and "reply-valid" in failed["card"]["rows"][1]["text"]
    assert llm.bound_atom() == failed["atom"]["id"]
    rig.call(reply=APPROVAL)                                                  # J2 asked again; the second reply is valid
    assert rig.outcomes() == ["opened", "verify_failed"]                      # a passing reply makes no transition
    rig.say(next="adaptation")
    rig.finish(t)
    closed = rig.atoms()[-1]
    assert (closed["outcome"], closed["atom"]["attempt"]) == ("closed", 2) and closed["ledger"]["attempt"] == 2
    results = closed["atom"]["body"]["verify"]["checks"][0]["results"]
    assert [r["exit_code"] for r in results] == [1, 0]
    assert closed["atom"]["body"]["verify"]["checks"][1]["results"][0]["evidence"] == "deferred: judged when the turn ends"


def test_the_third_failing_reply_abandons_the_atom_at_once(rig):
    t = rig.turn()
    for _ in range(3):
        rig.call(reply={"say": "bad"})
    assert rig.outcomes() == ["opened", "verify_failed", "verify_failed", "verify_failed", "abandoned"]
    last = rig.atoms()[-1]
    assert last["atom"]["body"]["abandon_code"] == "verify_failed" and last["atom"]["attempt"] == MAX_ATTEMPTS
    assert last["atom"]["reason"].startswith("verify failed: reply-valid:") and last["ledger"]["status"] == "verify_failed"
    rig.say(next="adaptation")
    rig.finish(t)
    assert rig.outcomes()[-1] == "abandoned" and len(rig.atoms()) == 5          # the turn end adds nothing: no atom is open
    assert rig.hooks.open_atoms == {} and llm.bound_atom() == overhead_atom_id(RUN_ID)


def test_a_turn_phase_failure_fails_the_close_then_abandons(rig):
    t = rig.turn("identity", "intake")
    rig.call(reply={"say": "ok", "reason": "r", "next": "Adaptation", "enough": True, "to_requester": "Your site is on its way.",
                    "to_agents": "@Adaptation go", "goal": {"kind": "site", "site_name": "Brew Lab", **TWO_ITEMS}})
    rig.hooks.record_saved("goal.json", TWO_ITEMS)
    rig.say(next="adaptation")
    assert rig.outcomes() == ["opened"]                                        # charter-stamp is a turn-phase check: deferred
    rig.finish(t)
    assert rig.outcomes() == ["opened", "verify_failed", "abandoned"]
    failed, abandoned = rig.atoms()[1:]
    assert failed["atom"]["attempt"] == 1 and "fewer than 3" in failed["card"]["rows"][1]["text"]
    assert abandoned["atom"]["reason"] == "verify failed: charter-stamp: fewer than 3 'done when' criteria"
    assert abandoned["card"]["label"] == "WORK ATOM ABANDONED" and abandoned["ledger"]["status"] == "verify_failed"
    assert abandoned["ledger"]["verify"] == {"template": "charter-stamp", "exit_code": 1}
    next_turn = rig.good_turn("identity", "approval")                           # the node is free again, the next id follows
    assert rig.atoms()[-1]["atom"]["id"].endswith("-02") and next_turn.turn_no == 2


def test_waived_closes_with_the_concern_on_record(rig):
    t = rig.turn("identity", "intake")
    rig.call(reply={"say": "ok", "reason": "r", "next": "Adaptation", "enough": True, "to_requester": "Your site is on its way.",
                    "to_agents": "@Adaptation go", "goal": {"kind": "site", "site_name": "Brew Lab", **GOOD_GOAL}})
    rig.hooks.record_saved("goal.json", TWO_ITEMS)
    rig.say("system", "Charter accepted after two attempts; the validator's concern is on record.", id=7)
    rig.say(next="adaptation", id=8)
    rig.finish(t)
    closed = rig.atoms()[-1]
    stamp = next(c for c in closed["atom"]["body"]["verify"]["checks"] if c["template"] == "charter-stamp")
    assert closed["outcome"] == "closed" and stamp["results"][-1]["evidence"] == "WAIVED: fewer than 3 'done when' criteria"


def test_recovered_closes_with_what_j2s_code_changed(rig, run_dir):
    (run_dir / "workflows.json").write_text(json.dumps([{"id": "W-1", "status": "registered"}, {"id": "W-3", "status": "held"}]))
    t = rig.turn("coordination", "schedule")
    assert rig.atoms()[0]["atom"]["work_kind"] == "llm"                         # read from the file at turn start: something is registered
    rig.call("coordination", {**SCHEDULE, "order": ["W-1", "W-9"], "holds": [{"id": "W-3", "missing": "waits"}]})
    rig.say("coordination", "@Priority Schedule", id=5, next="priority", schedule=["W-1"])
    rig.finish(t)
    closed = rig.atoms()[-1]
    ordered = next(c for c in closed["atom"]["body"]["verify"]["checks"] if c["template"] == "order-registered")
    assert closed["outcome"] == "closed" and ordered["results"][-1]["evidence"].startswith("RECOVERED: schedule W-1; W-3 held; dropped W-9")


def test_a_wrong_work_guess_is_corrected_by_what_the_turn_did(rig):
    t = rig.turn("coordination", "schedule")                                    # no workflows.json: predicted bash
    assert rig.atoms()[0]["atom"]["work_kind"] == "bash"
    rig.call("coordination", {**SCHEDULE, "order": []})                         # but a model call happened
    rig.say("coordination", "nothing to do", id=3)
    rig.finish(t)
    closed = rig.atoms()[-1]
    assert closed["atom"]["work_kind"] == "llm" and closed["atom"]["body"]["notes"] == "declared bash, did llm"


def test_a_bash_turn_without_a_call_closes_on_turn_posted(rig):
    t = rig.turn("priority", "envelope")
    assert rig.atoms()[0]["atom"]["work_kind"] == "bash"
    rig.say("priority", "Envelope check for W-1: within limits. Budget 40/100 used. Runs now.", id=4, next="coordination", envelope="allowed", auto=True)
    rig.finish(t)
    closed = rig.atoms()[-1]
    assert closed["outcome"] == "closed" and closed["atom"]["body"]["model"] is None and closed["atom"]["work_kind"] == "bash"


# ---- refused, stale, run end ------------------------------------------------------------------------------------------

def refusing_specs():
    """The shipped specs, but Audit's `audit` template tests a file outside the paths it touches: open_atom refuses."""
    audit = SPECS.specs["audit"]
    template = audit.atom_templates[-1].model_dump() | {"name": "audit", "touches": ["site/"], "checks": [{"name": "file-exists", "args": ["elsewhere/x.html"]}]}
    return SPECS.model_copy(update={"specs": {**SPECS.specs, "audit": audit.evolve(atom_templates=[template, audit.atom_templates[-1]])}})


def test_a_refused_open_is_stored_ledgered_carded_and_the_turn_goes_on(run_dir, llm_reset):
    rig = Rig(run_dir, specs=refusing_specs())
    rig.start()
    t = rig.turn("audit", "audit")
    [event] = rig.atoms()
    assert (event["outcome"], event["atom"]["status"], event["atom"]["attempt"]) == ("refused", "refused", 0)
    assert event["card"]["label"] == "ATOM REFUSED" and event["ledger"]["status"] == "refused" and "outside" in event["atom"]["reason"]
    [line] = rig.trace("atom.refused")
    assert line["code"] == "outside_envelope" and line["atom"] == event["atom"]["id"] and line["fn"] == "audit"
    assert rig.hooks.open_atoms == {} and llm.bound_atom() == overhead_atom_id(RUN_ID)           # no atom to charge: the overhead key stays
    rig.call("audit", {"anything": 1})                                                           # the turn goes on: no transitions
    rig.say("audit", "findings", id=2, next="identity")
    rig.finish(t)
    assert rig.outcomes() == ["refused"] and rig.hooks.errors == []
    assert rig.trace("layer.touches_miss")[0]["reason"].startswith("audit posted a message while its node has no open atom")
    rig.good_turn("audit", "dispute", reply={"say": "ok"})
    assert rig.atoms()[-1]["atom"]["id"].endswith("-01") is False and rig.atoms()[-1]["atom"]["id"].endswith("-02")          # the refusal used 01


def test_a_stale_open_atom_is_replaced_when_the_next_turn_starts(rig):
    rig.turn()
    first = rig.atoms()[0]["atom"]["id"]
    rig.turn()                                                                    # the first turn never finished
    abandoned = rig.atoms()[1]
    assert abandoned["outcome"] == "abandoned" and abandoned["atom"]["id"] == first and abandoned["atom"]["body"]["abandon_code"] == "replaced"
    assert "replaced" in abandoned["atom"]["reason"] and abandoned["ledger"]["status"] == "abandoned"
    assert rig.outcomes() == ["opened", "abandoned", "opened"] and len(rig.hooks.open_atoms) == 1


def test_run_status_waiting_and_not_paused_abandons_what_is_open(rig):
    t = rig.turn()
    rig.hooks.run_status({"status": "running", "paused": None})
    rig.hooks.run_status({"status": "waiting", "paused": {"kind": "question", "msg": 3}})
    assert rig.outcomes() == ["opened"]                                           # running, and waiting while paused, end nothing
    rig.hooks.run_status({"status": "waiting", "paused": None})
    last = rig.atoms()[-1]
    assert last["outcome"] == "abandoned" and last["atom"]["reason"] == "run ended: waiting" and last["atom"]["body"]["abandon_code"] == "run_ended"
    assert last["ledger"]["status"] == "abandoned" and rig.hooks.open_atoms == {} and llm.bound_atom() == overhead_atom_id(RUN_ID)
    rig.hooks.run_status({"status": "waiting", "paused": None})
    assert len(rig.atoms()) == 2                                                  # nothing left to abandon: nothing more written
    rig.finish(t)                                                                 # J2 reports the turn's end after the run ended: nothing to close
    assert len(rig.atoms()) == 2 and rig.hooks.errors == []


def test_run_error_and_the_hosts_stop_abandon_open_atoms(rig):
    rig.turn()
    rig.hooks.run_error("internal", "boom")
    last = rig.atoms()[-1]
    assert last["atom"]["reason"] == "run ended: crashed" and last["atom"]["body"]["abandon_code"] == "run_ended"
    assert rig.hooks.last_error == ("internal", "boom") and rig.trace("run.error")
    rig.turn("audit", "dispute")
    rig.hooks.abandon_open("stopped")
    assert rig.atoms()[-1]["atom"]["reason"] == "run ended: stopped" and rig.hooks.open_atoms == {}


# ---- the manual atom --------------------------------------------------------------------------------------------------

def ask_turn(rig):
    t = rig.turn("identity", "intake")
    rig.call(reply=ASK_REPLY)
    rig.hooks.message_posted({"id": 4, "who": "identity", "text": "Which colour?", "to_user": True, "act": "ASK_REQUESTER", "pause": "questions",
                              "next": "user"}, questions=[{"question": "Which colour?"}])
    rig.finish(t, "paused", messages=[4])
    return t


def test_a_turn_that_ends_paused_adds_one_manual_atom_for_the_question(rig):
    ask_turn(rig)
    assert rig.outcomes() == ["opened", "closed", "opened"]
    manual = rig.atoms()[-1]
    assert manual["node"] == "web.identity" and manual["atom"]["work_kind"] == "manual" and manual["atom"]["id"].endswith("-02")
    body = manual["atom"]["body"]
    assert body["goal"] == "The owner's answer to the first question is recorded"
    assert [(c["template"], c["args"]) for c in body["verify"]["checks"]] == [("answer-recorded", ["4"])]
    assert body["context"] == ["question: Which colour?", "pause: questions"] and body["work"]["agent"] == "owner"
    assert llm.bound_atom() == overhead_atom_id(RUN_ID) and list(rig.hooks.open_atoms) == ["web.identity"]
    rig.hooks.run_status({"status": "waiting", "paused": {"kind": "questions", "msg": 4}})
    assert len(rig.atoms()) == 3                                                  # still waiting for the owner


def test_the_owners_answer_closes_the_manual_atom(rig):
    ask_turn(rig)
    rig.hooks.message_posted({"id": 5, "who": "user", "text": "Blue, please"})
    closed = rig.atoms()[-1]
    check = closed["atom"]["body"]["verify"]["checks"][0]
    assert closed["outcome"] == "closed" and closed["atom"]["work_kind"] == "manual" and closed["ledger"]["status"] == "closed"
    assert check["results"][0]["evidence"] == 'answer recorded as message 5: "Blue, please"' and rig.hooks.open_atoms == {}
    rig.hooks.message_posted({"id": 6, "who": "user", "text": "one more thing"})
    assert len(rig.atoms()) == 4                                                  # nothing is open: nothing happens
    rig.good_turn("identity", "requester_answered", reply={"say": "ok"})
    assert rig.atoms()[-2]["atom"]["id"].endswith("-03")


def test_an_unanswered_manual_atom_is_abandoned_at_run_end(rig):
    ask_turn(rig)
    rig.hooks.run_status({"status": "waiting", "paused": None})
    last = rig.atoms()[-1]
    assert last["outcome"] == "abandoned" and last["atom"]["reason"] == "run ended: waiting" and last["atom"]["work_kind"] == "manual"
    rig.hooks.message_posted({"id": 9, "who": "user", "text": "late"})
    assert len(rig.atoms()) == 4


def test_a_stale_manual_atom_is_replaced_by_the_nodes_next_turn(rig):
    ask_turn(rig)
    rig.turn("identity", "requester_answered")                                     # the answer came another way (an override), not as a message
    assert [e["outcome"] for e in rig.atoms()][-2:] == ["abandoned", "opened"]
    assert rig.atoms()[-2]["atom"]["body"]["abandon_code"] == "replaced" and rig.atoms()[-2]["atom"]["work_kind"] == "manual"


def test_a_pause_with_no_question_message_falls_back_to_the_last_message(rig):
    t = rig.turn("identity", "intake")
    rig.call(reply=ASK_REPLY)
    rig.finish(t, "paused", messages=[11, 12])
    assert rig.atoms()[-1]["atom"]["body"]["verify"]["checks"][0]["args"] == ["12"]


# ---- what is not a function turn --------------------------------------------------------------------------------------

def test_builders_and_helper_calls_open_no_atom(rig):
    t = rig.turn("W-1", "build")
    rig.call("W-1", {"x": 1})
    rig.say("W-1", "built", id=2)
    rig.finish(t)
    assert rig.atoms() == [] and llm.bound_atom() == overhead_atom_id(RUN_ID)
    t = rig.turn()
    rig.call(purpose="planner", reply={"junk": True})                              # a helper call is no reply and no try
    rig.call("audit", {"junk": True})                                              # another function's call is not this turn's
    rig.call(reply=APPROVAL)
    rig.say(next="adaptation")
    rig.finish(t)
    assert rig.outcomes() == ["opened", "closed"]


def test_a_message_by_a_function_without_an_open_atom_only_logs(rig):
    rig.say("priority", "stray", id=3)                                             # between turns
    [line] = rig.trace("layer.touches_miss")
    assert line == {"fn": "priority", "atom": None, "target": "message", "reason": "priority posted a message while its node has no open atom"}
    rig.say("system", "not a function", id=4)
    rig.say("W-2", "a builder", id=5)
    assert len(rig.trace("layer.touches_miss")) == 1 and rig.atoms() == []


def test_a_record_outside_writes_logs_one_line_and_changes_no_outcome(rig):
    t = rig.turn("audit", "dispute")
    rig.hooks.record_saved("audits.json", [{"id": "A"}])                           # Audit writes findings: fine
    assert rig.trace("layer.touches_miss") == []
    rig.hooks.record_saved("goal.json", TWO_ITEMS)                                 # a charter is not Audit's to write
    rig.hooks.record_saved("summary.json", {"x": 1})                               # not one of the five records the checks read
    rig.call("audit", {"say": "ok"})
    rig.say("audit", "x", id=2, next="identity")
    rig.finish(t)
    [line] = rig.trace("layer.touches_miss")
    assert (line["fn"], line["target"], line["atom"]) == ("audit", "goal.json", rig.atoms()[0]["atom"]["id"]) and "does not list" in line["reason"]
    assert rig.outcomes() == ["opened", "closed"]


def test_write_terms_cover_every_term_of_the_shipped_specs():
    for function in FUNCTIONS:
        assert set(SPECS.specs[function].writes) <= set(WRITE_TERMS), function
    assert writable_records(SPECS.specs["audit"].writes) == {"audits.json", "conflicts.json"}
    assert writable_records(["unknown phrase"]) == frozenset()


def test_record_saved_returns_the_gate_warnings_and_the_system_addendum_stays_empty(run_dir, llm_reset):
    rig = Rig(run_dir)
    rig.hooks.validator = lambda name, data: ["a warning"]
    assert rig.hooks.record_saved("goal.json", {}) == ["a warning"] and rig.hooks.system_addendum("identity") == ""
    assert rig.trace("record.warning")[0]["warning"] == "a warning"


def test_model_and_work_come_from_the_turn_not_from_a_later_call(rig):
    t = rig.turn()
    rig.call(model="first-model")
    rig.call(model="second-model", call_no=2)
    rig.say(next="adaptation")
    rig.finish(t)
    assert rig.atoms()[-1]["atom"]["body"]["model"] == "first-model"


# ---- errors never reach J2 ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("hook, body, args", [
    ("run_started", "_on_run_started", ({"run_id": RUN_ID},)),
    ("turn_started", "_on_turn_started", ("turn",)),
    ("call_finished", "_on_call_finished", ("call",)),
    ("message_posted", "_on_message", ({"id": 1, "who": "identity", "text": "x"},)),
    ("record_saved", "_on_record", ("goal.json", {})),
    ("turn_finished", "_on_turn_finished", ("turn", TurnOutcome(result="ok"))),
    ("run_status", "_on_run_status", ({"status": "waiting", "paused": None},)),
])
def test_an_exception_inside_every_hook_body_is_traced_and_never_raised(rig, monkeypatch, hook, body, args):
    def boom(*a, **k):
        raise RuntimeError(f"{body} broke")
    monkeypatch.setattr(rig.hooks, body, boom)
    t = TurnInfo(run_id=RUN_ID, dept_id="web", turn_no=1, function="identity", kind="approval", step=1, step_label="x", cycle=1, task="t", context=[])
    c = CallInfo(call_no=1, function="identity", step=1, purpose="agent_turn", seconds=0.1, inputs=[], reply=APPROVAL)
    args = tuple(t if a == "turn" else c if a == "call" else a for a in args)
    getattr(rig.hooks, hook)(*args)
    [line] = rig.trace("layer.error")
    assert line["hook"] == hook and line["error"] == f"RuntimeError: {body} broke" and rig.atoms() == []
    assert rig.hooks.errors == [f"{hook}: RuntimeError: {body} broke"]


def test_run_error_swallows_a_broken_abandon_and_turn_finished_still_rebinds(rig, monkeypatch):
    t = rig.turn()
    monkeypatch.setattr(rig.hooks.runner, "round", lambda *a, **k: (_ for _ in ()).throw(ValueError("no round")))
    rig.finish(t)                                                                   # the final close cannot run
    assert rig.trace("layer.error")[0]["error"] == "ValueError: no round" and llm.bound_atom() == overhead_atom_id(RUN_ID)
    assert len(rig.hooks.open_atoms) == 1                                           # still open; the next turn replaces it
    rig.turn()
    assert rig.outcomes() == ["opened", "abandoned", "opened"]


def test_a_broken_trace_writer_does_not_turn_a_swallowed_error_into_a_raised_one(rig, monkeypatch):
    monkeypatch.setattr(rig.hooks, "_on_message", lambda m: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(rig.hooks, "trace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    rig.say("identity", "hello")                                                    # neither the body nor the trace error reaches the caller
    assert rig.hooks.errors == ["message_posted: RuntimeError: x"]


class RecordRejected(Exception):
    """Named like the library's strict-mode error: a run must stop on it."""


def test_the_strict_mode_of_the_record_gate_still_stops_the_run(run_dir, llm_reset):
    def strict(name, data):
        raise RecordRejected("goal.json: no")
    rig = Rig(run_dir)
    rig.hooks.validator = strict
    with pytest.raises(RecordRejected):
        rig.hooks.record_saved("goal.json", {})
    with pytest.raises(RecordRejected):
        rig.hooks.message_posted({"id": 1, "who": "identity", "text": "x"})
    assert rig.trace("layer.error") == []                                           # a fatal error is not a layer error


# ---- the factory ------------------------------------------------------------------------------------------------------

def test_factory_by_mode(run_dir):
    writer = EventWriter(run_dir)
    layer = factory(writer, lambda: None, None, None, {"run_id": RUN_ID, "dept_id": "web"}, environ={})
    assert isinstance(layer, FunctionNodeHooks) and layer.run_id == RUN_ID and layer.dept_id == "web"
    assert isinstance(factory(writer, lambda: None, environ={"SUTRA_NODES": " ON "}), FunctionNodeHooks)
    off = factory(writer, lambda: None, environ={"SUTRA_NODES": "off"})
    assert type(off) is EventHooks and not isinstance(off, FunctionNodeHooks)
    assert NODE_MODES == ("on", "off", "enforce")
    with pytest.raises(ValueError, match="reserved"):
        factory(writer, lambda: None, environ={"SUTRA_NODES": "enforce"})
    with pytest.raises(ValueError, match="one of on, off, enforce"):
        factory(writer, lambda: None, environ={"SUTRA_NODES": "maybe"})
    writer.close()


def test_factory_reads_the_environment_and_reports_unloadable_specs(run_dir, clean_env, monkeypatch):
    writer = EventWriter(run_dir)
    clean_env.setenv("SUTRA_NODES", "off")
    assert type(factory(writer, lambda: None)) is EventHooks
    clean_env.delenv("SUTRA_NODES")
    assert isinstance(factory(writer, lambda: None), FunctionNodeHooks)            # on by default

    def broken(*a, **k):
        raise FunctionSpecsError("missing", "no file")
    monkeypatch.setattr("sutra_app.engine.fnodes.layer.load_function_specs", broken)
    with pytest.raises(ValueError, match="function specs: missing: no file"):
        factory(writer, lambda: None)
    writer.close()


def test_the_layer_hooks_are_the_engine_hooks_protocol(run_dir):
    from sutra_app.engine.hooks import EngineHooks
    writer = EventWriter(run_dir)
    assert isinstance(FunctionNodeHooks(writer, lambda: None), EngineHooks)
    writer.close()
