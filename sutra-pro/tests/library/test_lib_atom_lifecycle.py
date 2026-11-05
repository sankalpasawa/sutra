"""The atom lifecycle (library design section 7; WP L4): open_atom, close_atom, abandon_atom, Seen, cards and events.

Pure functions: every test passes its own `now` and a fixed result list, so nothing reads a clock or runs a check."""
import pytest
from pydantic import ValidationError

from factories_atom import (
    ATOM_ID, SHA, abandon, check, close_with, closed, draft, fields, open_transition, opened, refused, results_for, tried,
    verify_failed_atom, work,
)
from sutra_app.library.atom import (
    MAX_ATTEMPTS, Atom, AtomError, Card, Check, CheckResult, Constraint, Refusal, Seen, Transition, abandon_atom, atom_display_state,
    build_card, card, close_atom, open_atom,
)
from sutra_app.library.gate import GATE


def rows(t):
    return {r.label: r.text for r in t.card.rows}


# ---- open ----------------------------------------------------------------------------------------------------------------

def test_open_gives_an_open_atom_with_default_relevance_and_no_tries():
    t = open_transition(check("file-exists"), check("grep-count", relevance="the heading is on the page"), now=100,
                        department_id="sales", workflow_id="W-3", task_id="tsk_9", session_id="3f9a1c2b7d")
    a = t.atom
    assert (t.outcome, t.refusal) == ("opened", None)
    assert (a.state, a.attempt, a.ts_open, a.ts_closed, a.id, a.node_id) == ("open", 0, 100, None, ATOM_ID, "sales.adaptation")
    assert (a.department_id, a.workflow_id, a.task_id, a.session_id) == ("sales", "W-3", "tsk_9", "3f9a1c2b7d")
    first, second = a.verify.checks
    assert (first.relevance, first.relevance_source) == ("declared: file-exists on site/index.html", "default")
    assert (second.relevance, second.relevance_source) == ("the heading is on the page", "declared")
    assert GATE.check("atom", a).model == a


def test_open_clears_any_results_a_draft_carried():
    carried = check("file-exists", results=[CheckResult(attempt=1, exit_code=1, ts=1)])
    assert opened(carried).verify.checks[0].results == []


def test_open_card_and_event():
    t = open_transition(constraints=[Constraint(text="Create only #contact"), Constraint(text="Keep the nav")], context=["charter item 1"],
                        model="sonnet", now=100)
    assert t.card.label == "WORK ATOM OPEN" and t.card.goal == "Visitors can open the contact form"
    assert rows(t) == {"Done when": "the file site/index.html exists and is not empty", "Done by": "an AI call [model: sonnet]",
                       "Limits": "Create only #contact; Keep the nav", "Using": "charter item 1", "Ref": ATOM_ID}
    [event] = t.events
    assert (event.type, event.subject_id, event.ts) == ("atom.transitioned", ATOM_ID, 100)
    assert event.data == {"atom_id": ATOM_ID, "node_id": "sales.adaptation", "outcome": "opened", "state": "open", "display": "open"}


@pytest.mark.parametrize("kind,done_by", [("llm", "an AI call"), ("bash", "code, no AI call"), ("manual", "you"), ("skill", "a Sutra skill")])
def test_done_by_says_who_does_the_work(kind, done_by):
    assert rows(open_transition(kind=kind))["Done by"] == done_by
    assert rows(open_transition(work=work("skill", ref="sutra:plan")))["Done by"] == "a Sutra skill (sutra:plan)"


REFUSALS = [
    ("atom_still_open", dict(other_open="a-3f9a1c2b7d-00")),
    ("goal_missing", dict(goal="")),
    ("goal_banal", dict(goal="done")),
    ("bad_args", dict(checks=[check("grep-count", ["x", "a.html"])])),
    ("vacuous_check", dict(checks=[check("grep-count", ["x", "a.html", "0"])])),
    ("relevance_empty", dict(checks=[check("file-exists", relevance="")])),
    ("pin_missing", dict(checks=[check("named-test").evolve(target_sha256=None)])),
    ("dotdot", dict(checks=[check("file-exists", ["../x.html"])])),
    ("outside_envelope", dict(checks=[check("file-exists", ["site"])], touches=["site/"])),
    ("bad_supersedes", dict(supersedes="a-3f9a1c2b7d-07")),
]


@pytest.mark.parametrize("code,over", REFUSALS, ids=[c for c, _ in REFUSALS])
def test_a_broken_rule_is_a_stored_refused_atom_with_a_card_and_an_event(code, over):
    t = open_transition(*over.get("checks", []), now=77, **{k: v for k, v in over.items() if k != "checks"})
    a = t.atom
    assert t.outcome == "refused" and t.refusal.code == code == a.refusal.code
    assert (a.state, a.attempt, a.ts_open, a.ts_closed, a.closed_by) == ("refused", 0, 77, 77, None)
    assert t.card.label == "ATOM REFUSED" and rows(t) == {"Reason": t.refusal.message}
    assert [e.data["outcome"] for e in t.events] == ["refused"] and t.events[0].data["display"] == "refused"
    assert GATE.check("atom", a).model == a                       # a refused atom can be stored
    assert atom_display_state(a) == "refused"


def test_the_refusal_messages_name_the_problem():
    said = {c: open_transition(*o.get("checks", []), **{k: v for k, v in o.items() if k != "checks"}).refusal.message for c, o in REFUSALS}
    assert said["goal_banal"] == "goal is banal ('done'): state the observable outcome"
    assert "a-3f9a1c2b7d-00" in said["atom_still_open"] and "a-3f9a1c2b7d-07" in said["bad_supersedes"]
    assert "grep-count needs exactly 3 args" in said["bad_args"] and "min=0" in said["vacuous_check"]
    assert "'site'" in said["outside_envelope"] and "'../x.html'" in said["dotdot"] and "WHY" in said["relevance_empty"]


def test_first_rule_wins_when_several_are_broken():
    t = open_transition(check("grep-count", ["x", "a.html", "0"]), goal="done", other_open="a-3f9a1c2b7d-00")
    assert t.refusal.code == "atom_still_open"
    assert open_transition(check("grep-count", ["x", "a.html", "0"]), goal="done").refusal.code == "goal_banal"


def test_goal_is_banal_only_for_the_exact_banal_words_in_any_case():
    for goal in ("Done", "OK", "it runs", "No Errors", "passes"):
        assert open_transition(goal=goal).refusal.code == "goal_banal"
    assert open_transition(goal="done.").outcome == "opened"


def test_a_refused_atom_keeps_what_was_refused_but_supersedes_nothing():
    t = open_transition(check("file-exists", ["a.html"]), goal="done", supersedes="a-3f9a1c2b7d-07", constraints=[Constraint(text="c")])
    a = t.atom
    assert a.goal == "done" and a.verify.checks[0].args == ["a.html"] and a.constraints[0].text == "c" and a.supersedes is None


def test_a_supersedes_target_must_be_in_the_abandoned_ids_given():
    assert open_transition(supersedes="a-3f9a1c2b7d-07", abandoned_ids={"a-3f9a1c2b7d-07"}).outcome == "opened"
    assert open_transition(supersedes="a-3f9a1c2b7d-07", abandoned_ids=["a-3f9a1c2b7d-08"]).refusal.code == "bad_supersedes"
    assert open_transition(supersedes="a-3f9a1c2b7d-07").refusal.code == "bad_supersedes"


def test_another_open_atom_of_the_node_blocks_the_open():
    first = opened()
    t = open_transition(id="a-3f9a1c2b7d-02", other_open=first)
    assert t.refusal.code == "atom_still_open" and ATOM_ID in t.refusal.message


def test_a_bad_id_is_a_programming_error_not_a_refusal():
    with pytest.raises(ValidationError):
        open_transition(id="atom-1")


# ---- close ---------------------------------------------------------------------------------------------------------------

def test_a_passing_close_closes_the_atom_through_the_checks():
    t = close_with(opened(check("file-exists"), check("grep-count")), 0, now=120)
    a = t.atom
    assert (t.outcome, a.state, a.attempt, a.closed_by, a.ts_closed, a.reason) == ("closed", "closed", 1, "verify", 120, None)
    assert all(c.results[-1].exit_code == 0 and len(c.results) == 1 for c in a.verify.checks)
    assert t.refusal is None and atom_display_state(a) == "closed" and GATE.check("atom", a).model == a


def test_closed_card_and_event():
    t = close_with(opened(check("file-exists", ["site/index.html"]), outputs=["site/index.html"]), 0)
    assert t.card.label == "WORK ATOM CLOSED"
    assert rows(t) == {"Result": "goal reached", "Proof": "checked the file site/index.html exists and is not empty -- passed",
                       "Output": "site/index.html", "Recorded": "added to the Atom log", "Ref": ATOM_ID}
    assert t.events[0].data == {"atom_id": ATOM_ID, "node_id": "sales.adaptation", "outcome": "closed", "state": "closed", "display": "closed"}
    assert "on attempt 2" in rows(close_with(tried(opened(), 1), 0))["Proof"]
    assert "Output" not in rows(close_with(opened(check("turn-posted")), 0))


def test_a_failed_try_keeps_the_atom_open_with_one_more_attempt():
    t = close_with(opened(check("file-exists"), check("grep-count")), 1, 0, evidence="missing", now=110)
    a = t.atom
    assert (t.outcome, a.state, a.attempt, a.closed_by, a.ts_closed) == ("verify_failed", "open", 1, None, None)
    assert [c.results[-1].exit_code for c in a.verify.checks] == [1, 0]          # every result is kept, passing ones too
    assert atom_display_state(a) == "open" and GATE.check("atom", a).model == a


def test_verify_failed_card_says_why_and_what_next():
    t = close_with(opened(check("file-exists"), check("grep-count")), 1, 0, evidence="missing")
    assert t.card.label == "VERIFY FAILED"
    assert rows(t) == {"Result": "not done -- attempt 1 of 3 did not pass, so this stays open", "Why": "file-exists: missing",
                       "Next": "fix the work, then close again (attempt 2 of 3)", "Ref": ATOM_ID}
    assert t.events[0].data["outcome"] == "verify_failed" and t.events[0].data["state"] == "open"
    last = close_with(tried(opened(), 2), 1)
    assert rows(last)["Next"] == "no tries are left: the atom will be abandoned" and last.atom.attempt == 3
    blank = close_atom(opened(), [CheckResult(attempt=1, exit_code=2, ts=1)], 5)
    assert rows(blank)["Why"] == "file-exists: exit 2"


def test_exit_codes_one_127_and_97_are_all_failed_tries():
    for code in (1, 127, 97, 2):
        t = close_with(opened(), code)
        assert t.outcome == "verify_failed" and t.atom.verify.checks[0].results[0].exit_code == code


def test_open_fail_close_sequence():
    a = opened()
    t1 = close_with(a, 1, now=110)
    t2 = close_with(t1.atom, 0, now=120)
    assert [t1.outcome, t2.outcome] == ["verify_failed", "closed"]
    assert t2.atom.attempt == 2 and [r.exit_code for r in t2.atom.verify.checks[0].results] == [1, 0]
    assert [r.attempt for r in t2.atom.verify.checks[0].results] == [1, 2]


def test_open_fail_fail_fail_abandon_sequence_ends_as_verify_failed():
    a = tried(opened(), 3)
    assert (a.state, a.attempt) == ("open", 3) and atom_display_state(a) == "open"       # an open atom at attempt 3 is open
    refused_close = close_with(a, 0)
    assert refused_close.outcome == "refused" and refused_close.refusal.code == "attempts_exhausted" and refused_close.atom == a
    t = abandon(a, "verify failed: file-exists: missing", code="verify_failed", now=140)
    assert (t.outcome, t.atom.state, t.atom.abandon_code, t.atom.ts_closed) == ("abandoned", "abandoned", "verify_failed", 140)
    assert atom_display_state(t.atom) == "verify_failed"


def test_pinned_named_test_that_changed_gets_exit_97_whatever_the_runner_said():
    a = opened(check("named-test", ["tests/form.sh"]), check("file-exists"))
    t = close_atom(a, results_for(a, 0), 120, pins_now={0: "cd" * 32})
    assert t.outcome == "verify_failed"
    pinned, other = t.atom.verify.checks
    assert (pinned.results[0].exit_code, pinned.results[0].evidence) == (97, "hash-pin mismatch: the pinned test changed since the atom opened")
    assert other.results[0].exit_code == 0
    assert "named-test: hash-pin mismatch" in rows(t)["Why"]


def test_a_pin_that_matches_or_is_unknown_or_belongs_to_another_check_changes_nothing():
    a = opened(check("named-test", ["tests/form.sh"]), check("file-exists"))
    for pins in ({0: SHA}, {}, None, {1: "cd" * 32}, {7: "cd" * 32}):
        t = close_atom(a, results_for(a, 0), 120, pins_now=pins)
        assert t.outcome == "closed", pins


@pytest.mark.parametrize("make,code", [
    (lambda a: [], "bad_results"),
    (lambda a: results_for(a, 0) * 2, "bad_results"),
    (lambda a: [CheckResult(attempt=2, exit_code=0, ts=1)], "bad_results"),
])
def test_results_must_be_one_per_check_for_the_next_attempt(make, code):
    a = opened()
    t = close_atom(a, make(a), 120)
    assert t.outcome == "refused" and t.refusal.code == code and t.atom == a and t.events == []


@pytest.mark.parametrize("state_of,code", [(lambda: closed(), "not_open"), (lambda: verify_failed_atom(), "not_open"), (lambda: refused(), "not_open")])
def test_closing_an_atom_that_is_not_open_is_refused(state_of, code):
    a = state_of()
    t = close_atom(a, [CheckResult(attempt=min(a.attempt + 1, 3), exit_code=0, ts=1)], 200)
    assert t.refusal.code == code and t.atom == a and t.outcome == "refused"


def test_a_refused_close_changes_nothing_and_publishes_nothing_but_still_has_its_card():
    a = tried(opened(), 3)
    t = close_with(a, 0)
    assert t.atom is a and t.events == [] and t.card.label == "ATOM REFUSED"
    assert rows(t) == {"Reason": f"atom {ATOM_ID} used all 3 attempts: abandon it with a reason"}
    assert MAX_ATTEMPTS == 3


def test_a_check_that_left_the_envelope_refuses_the_close():
    a = opened(touches=["site/"])
    outside = a.model_copy(update={"touches": ["docs/"]})                 # model_copy skips validation: an atom that drifted
    t = close_with(outside, 0)
    assert t.outcome == "refused" and t.refusal.code == "outside_envelope" and t.atom is outside
    dotdot = a.model_copy(update={"verify": a.verify.model_copy(update={"checks": [check("file-exists", ["../x.html"])]})})
    assert close_with(dotdot, 0).refusal.code == "dotdot"
    assert close_with(a, 0).outcome == "closed"


def test_close_checks_the_tries_in_the_plugin_order():
    done = closed()
    t = close_atom(done, [], 130)                        # not open wins over bad_results
    assert t.refusal.code == "not_open"
    exhausted = tried(opened(), 3)
    assert close_atom(exhausted, [], 130).refusal.code == "attempts_exhausted"       # attempts_exhausted wins over bad_results


# ---- abandon -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", ["manual", "run_ended", "replaced", "verify_failed"])
def test_abandon_stores_the_reason_and_the_code(code):
    t = abandon(tried(opened(), 1), "run ended: stopped", code=code, now=135)
    a = t.atom
    assert (t.outcome, a.state, a.reason, a.closed_by, a.abandon_code, a.ts_closed, a.attempt) == \
        ("abandoned", "abandoned", "run ended: stopped", "manual-override", code, 135, 1)
    assert t.card.label == "WORK ATOM ABANDONED" and t.events[0].data["outcome"] == "abandoned"
    assert t.events[0].data["display"] == ("verify_failed" if code == "verify_failed" else "abandoned")
    assert GATE.check("atom", a).model == a


def test_abandon_code_defaults_to_manual():
    assert abandon_atom(opened(), "changed my mind", 130).atom.abandon_code == "manual"


def test_abandon_card_has_reason_and_for_verify_failed_the_failing_evidence():
    plain = abandon(opened(), "run ended: stopped")
    assert rows(plain) == {"Result": "stopped without finishing", "Reason": "run ended: stopped", "Recorded": "added to the Atom log", "Ref": ATOM_ID}
    t = abandon(tried(opened(check("file-exists"), check("turn-posted")), 1), "verify failed: file-exists: missing", code="verify_failed")
    assert rows(t)["Reason"] == "verify failed: file-exists: missing"
    assert rows(t)["Why"] == "file-exists: missing; turn-posted: missing"
    assert rows(abandon(opened(), "r", code="verify_failed"))["Why"] == "no failed check result was recorded"


def test_abandon_needs_a_reason_and_an_open_atom():
    a = opened()
    for blank in ("", "   ", None):
        t = abandon_atom(a, blank, 130)
        assert t.outcome == "refused" and t.refusal.code == "reason_missing" and t.atom is a and t.events == []
    done = closed()
    assert abandon_atom(done, "why", 130).refusal.code == "not_open"
    assert abandon_atom(verify_failed_atom(), "again", 130).refusal.code == "not_open"
    assert abandon_atom(done, "", 130).refusal.code == "reason_missing"        # the plugin asks for the reason first (SA:373-391)
    assert rows(abandon_atom(a, "", 130)) == {"Reason": "abandon needs a reason: it is recorded, never silent"}


def test_an_unknown_abandon_code_is_a_programming_error():
    with pytest.raises(AtomError) as caught:
        abandon_atom(opened(), "why", 130, code="crash")
    assert caught.value.code == "bad_code"


def test_a_long_abandon_reason_is_cut_to_the_bound():
    t = abandon(opened(), "verify failed: " + "x" * 2000)
    assert len(t.atom.reason) == 600 and t.atom.reason.endswith("…")


def test_an_abandoned_atom_frees_the_node_for_the_next_one_and_can_be_superseded():
    gone = abandon(opened(), "stopped").atom
    nxt = open_atom(draft(supersedes=gone.id), id="a-3f9a1c2b7d-02", node_id="sales.adaptation", now=200, abandoned_ids={gone.id})
    assert nxt.outcome == "opened" and nxt.atom.supersedes == gone.id


# ---- Seen ----------------------------------------------------------------------------------------------------------------

def test_seen_work_that_differs_replaces_the_declared_kind_and_notes_it():
    a = opened(kind="bash")
    t = close_atom(a, results_for(a, 0), 120, seen=Seen(work="llm", model="sonnet"))
    assert (t.atom.work.dispatch_kind, t.atom.notes, t.atom.model) == ("llm", "declared bash, did llm", "sonnet")
    assert t.atom.work.agent == a.work.agent and t.atom.work.how_kind == a.work.how_kind          # nothing else changes
    assert t.atom.goal == a.goal and t.atom.verify.checks[0].relevance == a.verify.checks[0].relevance


def test_seen_adds_to_existing_notes_and_applies_to_a_failed_try_and_an_abandon():
    a = opened(kind="llm").evolve(notes="from J2")
    failed = close_atom(a, results_for(a, 1), 120, seen=Seen(work="manual"))
    assert failed.outcome == "verify_failed" and failed.atom.notes == "from J2 declared llm, did manual"
    gone = abandon_atom(opened(kind="bash"), "run ended", 130, code="run_ended", seen=Seen(work="llm"))
    assert gone.atom.work.dispatch_kind == "llm" and gone.atom.notes == "declared bash, did llm"


def test_seen_changes_nothing_when_it_agrees_or_says_nothing():
    a = opened(kind="llm", model="opus")
    same = close_atom(a, results_for(a, 0), 120, seen=Seen(work="llm", model="sonnet", note="saw the call"))
    assert same.atom.notes == "" and same.atom.work == a.work and same.atom.model == "opus"          # a model already set stays
    assert close_atom(a, results_for(a, 0), 120, seen=Seen()).atom.notes == ""
    assert close_atom(a, results_for(a, 0), 120).atom.notes == ""


def test_seen_is_not_applied_to_a_refusal():
    a = closed()
    t = abandon_atom(a, "why", 130, seen=Seen(work="bash"))
    assert t.refusal.code == "not_open" and t.atom is a and t.atom.notes == ""


def test_seen_is_a_closed_value():
    assert Seen().work is None and Seen().note == ""
    for bad in ({"work": "skill"}, {"model": ""}, {"note": "x" * 201}, {"colour": 1}):
        with pytest.raises(ValidationError):
            Seen(**bad)


# ---- Transition and cards ------------------------------------------------------------------------------------------------

def test_every_transition_carries_the_card_of_its_outcome_and_card_rebuilds_it():
    a = opened()
    transitions = [open_transition(), close_with(a, 1), close_with(a, 0), abandon(a), open_transition(goal="done"), close_with(closed(), 0)]
    labels = {"opened": "WORK ATOM OPEN", "verify_failed": "VERIFY FAILED", "closed": "WORK ATOM CLOSED", "abandoned": "WORK ATOM ABANDONED",
              "refused": "ATOM REFUSED"}
    assert [t.outcome for t in transitions] == ["opened", "verify_failed", "closed", "abandoned", "refused", "refused"]
    for t in transitions:
        assert t.card.label == labels[t.outcome] and card(t) == t.card and isinstance(t.card, Card)


def test_a_transition_must_fit_its_atom_card_and_refusal():
    a = opened()
    ok = open_transition()
    with pytest.raises(ValidationError, match="does not fit"):
        Transition(outcome="closed", atom=a, card=build_card("closed", a))
    with pytest.raises(ValidationError, match="the card of outcome opened"):
        Transition(outcome="opened", atom=a, card=build_card("abandoned", a))
    with pytest.raises(ValidationError, match="exactly when"):
        Transition(outcome="opened", atom=a, card=ok.card, refusal=Refusal(code="x", message="y"))
    with pytest.raises(ValidationError, match="exactly when"):
        Transition(outcome="refused", atom=a, card=build_card("refused", a))
    with pytest.raises(ValidationError):
        Transition(outcome="opened", atom=a, card=ok.card, events=[ok.events[0]] * 5)
    assert Transition.model_validate(ok.model_dump()) == ok


def test_the_card_lists_use_only_the_plugin_row_names_and_are_bounded():
    t = open_transition(constraints=[Constraint(text="x" * 300)] * 20)
    assert [r.label for r in t.card.rows] == ["Done when", "Done by", "Limits", "Ref"]
    assert len(rows(t)["Limits"]) == 2000 and rows(t)["Limits"].endswith("…")
    with pytest.raises(ValidationError):
        Card(label="WORK ATOM OPEN", rows=[{"label": "Colour", "text": "x"}])
    with pytest.raises(ValidationError):
        Card(label="DONE")


def test_open_and_close_agree_on_the_ids_they_use():
    t = open_transition(id="a-aaaaaaaaaa-07", node_id="web.priority")
    again = close_with(t.atom, 0)
    assert again.atom.id == "a-aaaaaaaaaa-07" and again.events[0].data["node_id"] == "web.priority"
    assert isinstance(again.atom, Atom) and fields(again.atom)["kind"] == "atom" and isinstance(Check(template="file-exists", args=["a"]), Check)
