"""What a function turn produced (D157, function-nodes.md 5.6): the plain words of each function's turn, the reply printed and cut, and the
layer recording both on the atom for a turn that passed, one that failed and one that was abandoned.

The first half asks `output.py` directly, with turn buffers made by hand; the second drives the layer's hooks through the rig of
`test_engine_fn_layer.py` and reads the `atom` events it wrote, as the server does."""
import json

import pytest

from sutra_app.engine.fnodes import layer
from sutra_app.engine.fnodes.checks import TurnBuffer
from sutra_app.engine.fnodes.output import LINE, NOTHING, manual_output, reply_record, turn_output
from sutra_app.engine.hooks import CallInfo, TurnInfo
from sutra_app.library.atom import REPLY_TEXT_MAX, Atom
from sutra_app.library.gate import GATE
from sutra_app.library.types import FUNCTIONS
from test_engine_fn_layer import ASK_REPLY, SCHEDULE, Rig, ask_turn, rig  # noqa: F401  (rig is a fixture)


def buffer(function, kind, *replies, posted=(), saved=()):
    """A turn buffer as the hooks fill it: one call per reply (None: a call that gave no object), then the messages and the saved records."""
    turn = TurnInfo(run_id="r", dept_id="web", task_id="t", turn_no=1, function=function, kind=kind, step=1, step_label="s", cycle=1, task="t", context=[])
    buf = TurnBuffer(turn=turn)
    for number, reply in enumerate(replies, 1):
        buf.add_call(CallInfo(call_no=number, function=function, step=1, purpose="agent_turn", seconds=0.1, inputs=[], reply=reply))
    for message in posted:
        buf.add_message(message)
    for name in saved:
        buf.add_record(name, {})
    return buf


def odd_posted(buf, *junk):
    """Lines in `posted` that are no message: the hooks never add one, and the words must not depend on that."""
    buf.posted.extend(junk)
    return buf


def words(function, kind, *replies, posted=(), saved=()):
    items, _ = turn_output(buffer(function, kind, *replies, posted=posted, saved=saved))
    return [item.name for item in items]


PROPOSAL = {"act": "PROPOSE", "workflows": [{"id": "W-1", "name": "Build the page"}, {"name": "Write the copy"}], "left_out": [{"item": 3, "reason": "x"}]}
FINDINGS = {"findings": [{"id": f"F-{n}", "verdict": "PASS", "evidence": "seen"} for n in range(1, 5)] + [
    {"id": "F-5", "verdict": "NEEDS_REVISION", "evidence": "no viewport meta tag"}, {"id": "F-6", "verdict": "BLOCKED_BY_EVIDENCE"}]}


# ---- the words of each function ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("function,kind,reply,posted,saved,expected", [
    # Identity: the charter, a question, a rule, and what it decided on the way
    ("identity", "intake", {"enough": True, "goal": {"site_name": "Brew Lab", "done_when": ["a", "b", "c"]}}, [], ["goal.json"],
     ["the charter: Brew Lab, 3 done-when items"]),
    ("identity", "intake", {"enough": True, "goal": {"product_name": "Orders", "statement": "x", "done_when": ["a"]}}, [], [],
     ["the charter: Orders, 1 done-when item"]),
    ("identity", "intake", {"enough": False, "questions": [{"question": "What are your opening hours?"}, {"question": "Where?"}]},
     [{"who": "identity", "next": "user"}], [], ["asked you 2 questions: What are your opening hours?", "posted 1 message to you"]),
    ("identity", "resolve", {"resolved": True, "ruling": "adaptation", "clause": "the stories cover that item"}, [], ["conflicts.json"],
     ["ruled for Adaptation: the stories cover that item"]),
    ("identity", "resolve", {"resolved": True, "ruling": "split", "workflows": ["Build", "Write"]}, [], ["conflicts.json", "workflows.json"],
     ["ruled to split the proposal: Build, Write", "saved the workflows"]),
    ("identity", "resolve", {"resolved": False, "user_question": {"question": "Which one first?", "options": ["a", "b"]}}, [], [],
     ["asked you: Which one first?"]),
    ("identity", "approval", {"approved": True, "budget_increase": 20}, [], [], ["approved more budget (+20)"]),
    ("identity", "approval", {"approved": False}, [], [], ["did not approve more budget"]),
    ("identity", "approval", {"decision": "DENY"}, [], [], ["denied the request for more budget"]),
    ("identity", "approval", {"decision": "ASK", "user_question": {"question": "Add 20 credits?"}}, [], [], ["asked you to approve: Add 20 credits?"]),
    ("identity", "audit", {"done": True}, [], [], ["decided the goal is reached"]),
    ("identity", "audit", {"done": False, "requester_questions": ["Which colour?"]}, [], [], ["decided the goal is not reached yet; needs you: Which colour?"]),
    ("identity", "requester_answered", {"decision": "continue"}, [], [], ["read your answer: carry on"]),
    ("identity", "requester_answered", {"decision": "drop", "drop_items": [2, 3]}, [], [], ["read your answer: leave out 2 items"]),
    ("identity", "requester_answered", {"decision": "ship"}, [], [], ["read your answer: finish as it is"]),
    ("identity", "question", {"say": "The hours are in the charter."}, [], [], ["said: The hours are in the charter."]),
    # Adaptation: a proposal, and the answers around it
    ("adaptation", "propose", PROPOSAL, [{"who": "adaptation", "next": "priority"}], ["workflows.json", "realization.json"],
     ["a proposal of 2 workflows: W-1 Build the page, Write the copy; left out 1 item", "posted 1 message to Priority", "saved the plan"]),
    ("adaptation", "propose", {"act": "POLICY_QUESTION", "question": "May the page use stock photos?"}, [], [], ["asked Identity: May the page use stock photos?"]),
    ("adaptation", "propose", {"act": "DISPUTE", "dispute": {"with": "Audit", "about": "F-7", "reason": "fluid widths"}}, [], [],
     ["disputed F-7 with Audit: fluid widths"]),
    ("adaptation", "respond", {"act": "ACCEPT"}, [], [], ["accepted Priority's decision"]),
    ("adaptation", "respond", {"act": "PARK"}, [], [], ["parked the proposal"]),
    ("adaptation", "respond", {"act": "REVISE", "workflows": [{"name": "Smaller page"}]}, [], [], ["a revised proposal of 1 workflow: Smaller page"]),
    ("adaptation", "atom_failed", {"verdict": "CHECK_WRONG", "atom": "W-2.a1", "verification": [{"text": "a"}, {"text": "b"}, {"text": "c"}]}, [], [],
     ["judged the check wrong for W-2.a1: sent 3 corrected checks"]),
    ("adaptation", "atom_failed", {"verdict": "BUILD_WRONG", "atom": "W-2.a1", "build_wrong_reason": "the section misses the form"}, [], [],
     ["judged the build wrong for W-2.a1: the section misses the form"]),
    # Priority: GRANT, COUNTER, REFUSE and the envelope
    ("priority", "price", {"decision": "GRANT", "workflows": [{"id": "W-1", "name": "Scaffold", "envelope": {"money_limit": 15}}, {"name": "Core"}]},
     [{"who": "priority", "next": "adaptation"}], ["workflows.json"],
     ["GRANT: funded 2 workflows: W-1 Scaffold (money 15), Core", "posted 1 message to Adaptation"]),
    ("priority", "price", {"decision": "COUNTER", "workflows": [{"name": "Core", "envelope": {"money_limit": 30}}]}, [], [],
     ["COUNTER: 1 workflow at another price: Core (money 30)"]),
    ("priority", "price", {"decision": "REFUSE"}, [], [], ["REFUSE: funded nothing"]),
    ("priority", "envelope", {"decision": "HOLD"}, [], [], ["HOLD: the workflow waits, it is over its envelope"]),
    ("priority", "envelope", {"decision": "REQUEST_APPROVAL"}, [], [], ["REQUEST_APPROVAL: asked Identity to approve more"]),
    ("priority", "envelope", None, [{"who": "priority", "next": "W-1"}, {"who": "system", "text": "Code ran 2 checks"}], [],
     ["posted 1 message to W-1", "code posted 1 message: Code ran 2 checks"]),
    # Coordination: the order, its rule and the holds
    ("coordination", "schedule", {"rule": "dependencies first", "order": ["W-1", "W-2"], "holds": [{"id": "W-3", "missing": "the copy"}]},
     [{"who": "coordination", "next": "priority"}], ["workflows.json"],
     ["scheduled 2 workflows in this order: W-1, W-2. Rule: dependencies first", "held 1 workflow: W-3 (missing the copy)", "posted 1 message to Priority"]),
    ("coordination", "schedule", {"order": []}, [], [], ["scheduled nothing to run"]),
    # Audit: the count by verdict, then each finding that does not pass
    ("audit", "report", FINDINGS, [{"who": "audit", "next": "identity"}], ["audits.json"],
     ["6 findings: 4 pass, 1 needs revision, 1 is blocked by missing evidence", "finding F-5: needs revision, no viewport meta tag",
      "finding F-6: is blocked by missing evidence", "posted 1 message to Identity"]),
    ("audit", "report", {"findings": [{"id": "F-1", "verdict": "PASS", "evidence": "ok"}], "rubric": [{"id": "R-1", "verdict": "PASS_WITH_WARNING", "evidence": "e"}]},
     [], [], ["2 findings and rubric rows: 1 passes, 1 passes with a warning"]),
    ("audit", "report", {"rubric": [{"id": "R-2", "verdict": "NEEDS_REVISION", "evidence": "x"}]}, [], [],
     ["1 rubric row: 1 needs revision", "rubric row R-2: needs revision, x"]),
])
def test_the_words_of_each_functions_turn(function, kind, reply, posted, saved, expected):
    assert words(function, kind, *([] if reply is None else [reply]), posted=posted, saved=saved) == expected


def test_findings_that_pass_are_counted_and_only_the_rest_are_told_one_by_one():
    many = {"findings": [{"id": f"F-{n}", "verdict": "NEEDS_REVISION", "evidence": f"e{n}"} for n in range(1, 9)] + [{"id": "F-9", "verdict": "PASS", "evidence": "ok"}]}
    told = words("audit", "report", many)
    assert told[0] == "9 findings: 1 passes, 8 need revision"
    assert told[1:6] == [f"finding F-{n}: needs revision, e{n}" for n in range(1, 6)] and told[6] == "and 3 more that do not pass" and len(told) == 7


def test_what_a_turn_made_names_the_record_it_saved_and_a_record_no_sentence_covers_is_told_once():
    told = words("adaptation", "propose", PROPOSAL, saved=["workflows.json", "realization.json", "conflicts.json", "chat.jsonl", "realization.json"])
    assert told[1:] == ["saved the plan and the conflict log"]                       # workflows.json is in the proposal's own sentence; chat.jsonl is no record
    items, _ = turn_output(buffer("adaptation", "propose", PROPOSAL, saved=["workflows.json"]))
    assert [(i.verb, i.form, i.ref) for i in items] == [("make", "proposal", "workflows.json")]
    unsaved, _ = turn_output(buffer("adaptation", "propose", PROPOSAL))
    assert unsaved[0].ref == "the reply"                                              # nothing was saved: the words say where the proposal is, only in the reply


def test_a_messages_targets_are_the_owner_a_function_or_a_builder():
    said = lambda *targets: words("identity", "question", {"say": "x"}, posted=[{"who": "identity", "next": t} for t in targets])[-1]
    assert said("user") == "posted 1 message to you" and said("requester", "adaptation") == "posted 2 messages to you and Adaptation"
    assert said("W-3") == "posted 1 message to W-3" and said(None) == "posted 1 message" and said("audit", "audit", "audit") == "posted 3 messages to Audit"


def test_what_the_code_said_during_the_turn_is_told_by_its_first_line_and_is_not_the_functions_own_message():
    queue = "Queue empty: no registered work left in cycle 1. Hand-off by code: Audit checks site v4."
    assert words("coordination", "schedule", None, posted=[{"who": "system", "text": queue}]) == [f"code posted 1 message: {queue}"]
    both = words("identity", "intake", {"say": "x"}, posted=[{"who": "identity", "next": "adaptation"}, {"who": "validator", "text": "Charter valid."},
                                                            {"who": "system", "text": "Paused."}])
    assert both == ["said: x", "posted 1 message to Adaptation", "code posted 2 messages: Charter valid."]
    assert words("priority", "envelope", None, posted=[{"who": "system", "next": "x"}, {"who": "validator"}, {"who": "user", "text": "hi"}]) == [NOTHING]
    long = words("audit", "report", None, posted=[{"who": "system", "text": "y" * 500}])[0]
    assert len(long) < 170 and long.endswith("…")


def test_a_turn_that_made_nothing_says_so_and_so_does_a_reply_nothing_can_be_read_from():
    assert words("audit", "report") == [NOTHING] and words("coordination", "schedule", None) == [NOTHING]
    assert words("audit", "report", {}) == [NOTHING] and words("identity", "intake", {"enough": "maybe"}) == [NOTHING]
    items, reply = turn_output(buffer("audit", "report"))
    assert (items[0].verb, items[0].form) == ("do", "nothing") and reply is None


@pytest.mark.parametrize("function", FUNCTIONS)
def test_no_reply_of_any_shape_stops_the_words(function):
    odd = [{}, {"workflows": 5}, {"workflows": [None, 3, "x", {"name": 5}, {"id": 7, "envelope": "no"}]}, {"findings": "no"}, {"findings": [None, {"verdict": 3}, {"id": []}]},
           {"order": "W-1"}, {"order": [None, 5]}, {"holds": [1, {"id": None}]}, {"decision": 7}, {"decision": "GRANT", "workflows": {}}, {"act": None}, {"act": "PROPOSE"},
           {"questions": [5, None, {}]}, {"goal": []}, {"goal": {"done_when": "x"}, "enough": True}, {"resolved": True, "ruling": 5}, {"done": "yes"}, {"say": 5},
           {"verdict": "CHECK_WRONG", "verification": "no"}, {"rubric": [{"verdict": None}]}, {"user_question": 5, "resolved": False}, {"approved": True, "budget_increase": True}]
    for reply in odd:
        items, _ = turn_output(odd_posted(buffer(function, "x", reply, posted=[{"who": function}]), None, 4, "text"))
        assert items and all(1 <= len(i.name) <= LINE and i.ref and i.form for i in items) and len(items) <= 40, reply


def test_what_a_reply_says_is_cut_to_the_length_of_a_name_and_the_list_to_forty():
    items, _ = turn_output(buffer("adaptation", "propose", {"act": "PROPOSE", "workflows": [{"name": "x" * 500}] * 3, "left_out": []}))
    assert len(items[0].name) <= LINE and items[0].name.startswith("a proposal of 3 workflows: ")
    shown, _ = turn_output(buffer("audit", "report", {"findings": [{"id": f"F-{n}", "verdict": "NEEDS_REVISION", "evidence": "y" * 400} for n in range(50)]}))
    assert len(shown) <= 40 and all(len(i.name) <= LINE for i in shown)


# ---- the reply -------------------------------------------------------------------------------------------------------------

def test_the_reply_is_printed_with_two_space_indents_and_keeps_the_models_order_and_words():
    reply = {"say": "Zażółć gęślą jaźń", "act": "PROPOSE", "workflows": [{"name": "a"}]}
    record = reply_record(buffer("adaptation", "propose", reply))
    assert record.text == json.dumps(reply, ensure_ascii=False, indent=2) and record.clipped is False
    assert record.text.splitlines()[1] == '  "say": "Zażółć gęślą jaźń",' and json.loads(record.text) == reply


def test_a_long_reply_is_cut_at_4000_characters_and_says_so():
    record = reply_record(buffer("adaptation", "propose", {"say": "w" * 6000}))
    assert record.clipped is True and len(record.text) == REPLY_TEXT_MAX == 4000 and record.text.endswith("…")
    exact = {"say": "w" * (REPLY_TEXT_MAX - len(json.dumps({"say": ""}, indent=2)))}
    assert len(json.dumps(exact, indent=2)) == REPLY_TEXT_MAX and reply_record(buffer("audit", "report", exact)).clipped is False


def test_only_the_latest_call_is_shown_and_a_latest_call_with_no_object_shows_nothing():
    two = buffer("audit", "report", {"say": "first"}, {"say": "second"})
    assert json.loads(reply_record(two).text) == {"say": "second"}
    assert reply_record(buffer("audit", "report", {"say": "first"}, None)) is None            # an older reply is not offered for a newer call that gave none
    assert reply_record(buffer("audit", "report")) is None and turn_output(two)[1] == reply_record(two)


def test_the_manual_atom_of_a_question_is_done_by_the_answer():
    buf = buffer("identity", "intake")
    assert manual_output(buf) == []
    buf.add_message({"id": 5, "who": "user", "text": "Blue,   please\n"})
    [item] = manual_output(buf)
    assert (item.verb, item.name, item.form, item.ref) == ("do", "you answered: Blue, please", "answer", "chat message 5")
    buf.add_message({"id": 6, "who": "identity", "text": "thanks"})
    assert manual_output(buf)[0].name == "you answered: Blue, please"                              # only the owner's lines count


# ---- the layer records them on every transition of the atom ----------------------------------------------------------------------

def body(event):
    return event["atom"]["body"]


def names(event):
    return [item["name"] for item in body(event)["produced"]]


def test_a_closed_atom_carries_what_the_turn_made_and_the_reply_the_model_gave(rig, run_dir):
    (run_dir / "workflows.json").write_text(json.dumps([{"id": "W-1", "status": "registered"}, {"id": "W-2", "status": "registered"}]))
    t = rig.turn("coordination", "schedule")
    reply = {**SCHEDULE, "order": ["W-1", "W-2"]}
    rig.call("coordination", reply)
    rig.hooks.record_saved("workflows.json", [{"id": "W-1", "status": "registered"}, {"id": "W-2", "status": "registered"}])
    rig.say("coordination", "@Priority Schedule", id=5, next="priority", schedule=["W-1", "W-2"])
    opened = rig.atoms()[0]
    assert body(opened)["produced"] == [] and body(opened)["reply"] is None                          # nothing has happened yet
    rig.finish(t)
    closed = rig.atoms()[-1]
    assert closed["outcome"] == "closed"
    assert names(closed) == ["scheduled 2 workflows in this order: W-1, W-2. Rule: dependencies first", "posted 1 message to Priority"]
    assert [(i["verb"], i["form"], i["ref"]) for i in body(closed)["produced"]] == [("make", "order", "workflows.json"), ("do", "message", "chat")]
    assert json.loads(body(closed)["reply"]["text"]) == reply and body(closed)["reply"]["clipped"] is False
    assert Atom.model_validate(body(closed)).reply.text == body(closed)["reply"]["text"] and GATE.check("atom", body(closed)).model.produced
    assert body(closed)["notes"] == "" and rig.hooks.errors == []


# the owner's case: Adaptation's verdict on a failed atom, whose corrected checks have no `template`
BAD_VERDICT = {"say": "@Coordination the check was wrong", "verdict": "CHECK_WRONG", "atom": "W-2.a1", "verification": [{"text": "the page has a menu"}]}


def test_a_failed_try_keeps_the_reply_that_failed_and_what_it_said(rig):
    rig.turn("adaptation", "atom_failed")
    rig.call("adaptation", BAD_VERDICT)
    failed = rig.atoms()[-1]
    assert (failed["outcome"], failed["atom"]["status"], failed["atom"]["attempt"]) == ("verify_failed", "open", 1)
    assert "verification.0.template" in failed["card"]["rows"][1]["text"]                           # why: the check says it too
    assert json.loads(body(failed)["reply"]["text"]) == BAD_VERDICT                                  # what the model sent
    assert names(failed) == ["judged the check wrong for W-2.a1: sent 1 corrected check"]
    second = {**BAD_VERDICT, "say": "again"}
    rig.call("adaptation", second)
    assert json.loads(body(rig.atoms()[-1])["reply"]["text"]) == second                              # the newest reply replaces it


def test_an_abandoned_atom_keeps_the_last_reply_it_received(rig):
    t = rig.turn("adaptation", "atom_failed")
    for n in range(1, 4):
        rig.call("adaptation", {**BAD_VERDICT, "say": f"try {n}"})
    last = rig.atoms()[-1]
    assert last["outcome"] == "abandoned" and body(last)["abandon_code"] == "verify_failed" and last["ledger"]["status"] == "verify_failed"
    assert json.loads(body(last)["reply"]["text"])["say"] == "try 3" and names(last) == ["judged the check wrong for W-2.a1: sent 1 corrected check"]
    rig.finish(t)
    assert len(rig.atoms()) == 5 and json.loads(body(rig.atoms()[-1])["reply"]["text"])["say"] == "try 3"          # the turn end adds nothing


def test_a_turn_phase_failure_records_the_reply_and_the_charter_it_made(rig):
    t = rig.turn("identity", "intake")
    reply = {"say": "ok", "reason": "r", "next": "Adaptation", "enough": True, "to_requester": "Your site is on its way.", "to_agents": "@Adaptation go",
             "goal": {"kind": "site", "site_name": "Brew Lab", "statement": "A site", "done_when": ["a", "b"]}}
    rig.call("identity", reply)
    rig.hooks.record_saved("goal.json", {"statement": "A site", "done_when": ["a", "b"]})
    rig.say("identity", "@Adaptation go", id=6, next="adaptation")
    rig.finish(t)
    assert rig.outcomes() == ["opened", "verify_failed", "abandoned"]
    failed, abandoned = rig.atoms()[1:]
    for event in (failed, abandoned):                                                              # the failed close and the abandon that follows say the same
        assert names(event) == ["the charter: Brew Lab, 2 done-when items", "posted 1 message to Adaptation"]
        assert json.loads(body(event)["reply"]["text"]) == reply
    assert abandoned["atom"]["reason"].startswith("verify failed: charter-stamp")


def test_a_turn_the_run_ended_in_keeps_what_it_had_made_so_far(rig):
    rig.turn("coordination", "schedule")
    rig.call("coordination", SCHEDULE)
    rig.say("coordination", "@Priority Schedule", id=5, next="priority")
    rig.hooks.run_status({"status": "waiting", "paused": None})
    ended = rig.atoms()[-1]
    assert ended["outcome"] == "abandoned" and ended["atom"]["reason"] == "run ended: waiting"
    assert names(ended) == ["scheduled 1 workflow in this order: W-1. Rule: dependencies first", "posted 1 message to Priority"]
    assert json.loads(body(ended)["reply"]["text"]) == SCHEDULE


def test_a_turn_stopped_before_it_made_anything_says_nothing_was_made(rig):
    rig.turn("audit", "audit")
    rig.hooks.abandon_open("stopped")
    assert names(rig.atoms()[-1]) == [NOTHING] and body(rig.atoms()[-1])["reply"] is None


def test_a_stale_atom_keeps_what_its_last_transition_recorded(rig):
    rig.turn("adaptation", "atom_failed")
    rig.call("adaptation", BAD_VERDICT)
    rig.turn("adaptation", "atom_failed")                                                           # the first turn never finished: replaced
    replaced = [e for e in rig.atoms() if e["outcome"] == "abandoned"][0]
    assert body(replaced)["abandon_code"] == "replaced" and json.loads(body(replaced)["reply"]["text"]) == BAD_VERDICT


def test_the_owners_answer_is_what_the_manual_atom_produced(rig):
    ask_turn(rig)
    opened = rig.atoms()[-1]
    assert opened["atom"]["work_kind"] == "manual" and body(opened)["produced"] == []
    rig.hooks.message_posted({"id": 5, "who": "user", "text": "Blue, please"})
    closed = rig.atoms()[-1]
    assert closed["outcome"] == "closed" and names(closed) == ["you answered: Blue, please"] and body(closed)["reply"] is None
    first = rig.atoms()[1]                                                                          # the turn that asked
    assert names(first) == ["asked you 1 question: Which colour?", "posted 1 message to you"] and json.loads(body(first)["reply"]["text"]) == ASK_REPLY


def test_an_unanswered_manual_atom_ends_with_nothing_recorded(rig):
    ask_turn(rig)
    rig.hooks.run_status({"status": "waiting", "paused": None})
    last = rig.atoms()[-1]
    assert last["outcome"] == "abandoned" and last["atom"]["work_kind"] == "manual" and body(last)["produced"] == [] and body(last)["reply"] is None


def test_a_refused_atom_has_no_turn_and_records_nothing(run_dir, llm_reset):
    from test_engine_fn_layer import refusing_specs
    refused_rig = Rig(run_dir, specs=refusing_specs())
    refused_rig.start()
    t = refused_rig.turn("audit", "audit")
    refused_rig.call("audit", {"findings": []})
    refused_rig.finish(t)
    [event] = refused_rig.atoms()
    assert event["outcome"] == "refused" and body(event)["produced"] == [] and body(event)["reply"] is None


def test_the_output_never_stops_an_atom_from_closing(rig, run_dir, monkeypatch):
    (run_dir / "workflows.json").write_text(json.dumps([{"id": "W-1", "status": "registered"}]))
    def broken(buf):
        raise ValueError("boom")
    monkeypatch.setattr(layer, "turn_output", broken)
    t = rig.turn("coordination", "schedule")
    rig.call("coordination", SCHEDULE)
    rig.say("coordination", "@Priority Schedule", id=5, next="priority")
    rig.finish(t)
    assert rig.outcomes()[-1] == "closed" and rig.atoms()[-1]["ledger"]["status"] == "closed"
    assert body(rig.atoms()[-1])["produced"] == [] and body(rig.atoms()[-1])["reply"] is None
    assert rig.hooks.errors and rig.hooks.errors[0] == "output: ValueError: boom" and rig.trace("layer.error")[0]["hook"] == "output"


def test_every_atom_line_the_layer_writes_is_read_by_the_servers_strict_model(rig):
    """The rig parses each line with ORCH's closed `RunAtom` model: the two new body keys ride in the open `body` object."""
    rig.good_turn("identity", "approval")
    ask_turn(rig)
    rig.hooks.message_posted({"id": 9, "who": "user", "text": "Blue"})
    assert len(rig.atoms()) >= 5 and all({"produced", "reply", "notes"} <= set(body(e)) for e in rig.atoms())
