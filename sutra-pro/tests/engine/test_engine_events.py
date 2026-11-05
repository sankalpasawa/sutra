"""events.py and hooks.py: the run-event protocol and the hooks that write it (engine.md 4.3, 4.5; S1-contracts-05, -09;
S2-models-07; S3-web-04).

Builders return plain dicts; EventWriter appends them as whole lines; EventUsageSink turns a usage row into a `usage` event;
EventHooks writes the `say` events and the trace lines. The unconditional check against the orchestrator's `RunEvent` union
is `test_engine_events_contract.py` (WP E7); the conditional one at the end of this file runs once ORCH-1 has merged.
"""
import json
import os
import re
import stat
import sys
import threading
from pathlib import Path

import pytest

from sutra_app.engine import events, hooks, llm
from sutra_app.engine.events import (
    ATOM_KEYS, EVENT_TYPES, EventError, EventUsageSink, EventWriter, atom_event, context_strings, encode_line, heartbeat_event,
    node_event, run_ended_event, run_started_event, say_event, step_event, usage_event, utc_iso,
)
from sutra_app.engine.hooks import (
    CallInfo, EngineHooks, EventHooks, NullHooks, TurnInfo, TurnOutcome, is_fatal, load_validator,
)
from sutra_app.library.types import overhead_atom_id

AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
RUN = "j2-20261104-100004-7f3a"


def lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="ascii").splitlines()]


ATOM_V1 = {"id": "W-1.a2", "schema": "atom/1", "goal": "Write the menu section", "work_kind": "llm", "verify_template": "contains",
           "status": "closed", "attempt": 1, "closed_by": "verify", "reason": None, "body": {"id": "W-1.a2"}, "ts_open": 1793748000,
           "ts_closed": 1793748060}
ATOM_V03 = {"id": "a-3f9a1c2b7d-01", "schema": "work-atom/0.3", "goal": "The charter is stamped", "work_kind": "llm",
            "verify_template": None, "status": "open", "attempt": 0, "closed_by": None, "reason": None, "body": {"state": "open"},
            "ts_open": 1793748000, "ts_closed": None}
TASK = {"id": "t-1", "kind": "intake", "summary": "J2.a Enough information to work?: intake", "state": "running", "set_by": "system"}
USAGE = dict(fn="identity", step="J2.a", atom="a-3f9a1c2b7d-01", provider="claude", model="sonnet", purpose="agent_turn", usd=0.012,
             tokens_in=3100, tokens_out=240, seconds=6.2, ok=True, how="native", call_ref=RUN + ":1", detail=None)


# ---- the closed list --------------------------------------------------------------------------------------------------

def test_the_event_types_are_the_eight_of_the_design_in_orchs_order():
    assert EVENT_TYPES == ("run.started", "say", "node", "step", "atom", "usage", "heartbeat", "run.ended")
    assert events.EVENTS_SCHEMA == "events/1"


def test_utc_iso_is_seconds_in_utc_with_a_z():
    assert utc_iso(0) == "1970-01-01T00:00:00Z"
    assert utc_iso(1793750406.9) == "2026-11-04T00:00:06Z"
    assert AT.match(utc_iso())


# ---- each builder yields exactly the fields of 4.5 and an `at` ------------------------------------------------------------

BUILT = {
    "run.started": (lambda: run_started_event(pid=48211, mock=False, seed="none"), ["t", "at", "pid", "schema", "mock", "seed"]),
    "say": (lambda: say_event(id=3, who="identity", text="hello"), ["t", "at", "id", "who", "text", "to_user", "act", "pause", "questions", "next"]),
    "node": (lambda: node_event(fn="identity", status="running"), ["t", "at", "fn", "status", "detail", "calls", "seconds"]),
    "step": (lambda: step_event(step="W-1", name="Menu", status="running"), ["t", "at", "step", "name", "parent", "status", "handoff", "reads", "rework"]),
    "atom": (lambda: atom_event(node="web.identity", atom=ATOM_V1), ["t", "at", "node", "atom"]),
    "usage": (lambda: usage_event(**USAGE), ["t", "at", "fn", "step", "atom", "provider", "model", "purpose", "usd", "tokens_in", "tokens_out",
                                             "seconds", "ok", "how", "call_ref", "detail"]),
    "heartbeat": (lambda: heartbeat_event(), ["t", "at"]),
    "run.ended": (lambda: run_ended_event(status="done", outcome="Done: the site is workable."), ["t", "at", "status", "outcome", "code"]),
}


def test_there_is_a_builder_for_every_event_type():
    assert set(BUILT) == set(EVENT_TYPES)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_each_builder_yields_exactly_the_fields_of_the_design_and_an_at(event_type):
    build, keys = BUILT[event_type]
    event = build()
    assert list(event) == keys
    assert event["t"] == event_type
    assert AT.match(event["at"])
    json.dumps(event, allow_nan=False)                       # JSON all the way down


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_a_given_at_is_kept_and_a_bad_one_is_refused(event_type):
    makers = {
        "run.started": lambda at: run_started_event(pid=1, mock=True, seed="fresh", at=at),
        "say": lambda at: say_event(id=1, who="system", text="t", at=at),
        "node": lambda at: node_event(fn="audit", status="idle", at=at),
        "step": lambda at: step_event(step="team:Designer", name="n", status="filed", at=at),
        "atom": lambda at: atom_event(node="n", atom=ATOM_V1, at=at),
        "usage": lambda at: usage_event(**USAGE, at=at),
        "heartbeat": lambda at: heartbeat_event(at=at),
        "run.ended": lambda at: run_ended_event(status="stopped", outcome="Stopped: stopped on request", at=at),
    }
    assert makers[event_type]("2026-11-04T10:00:06Z")["at"] == "2026-11-04T10:00:06Z"
    for bad in ("2026-11-04 10:00:06", "2026-11-04T10:00:06+00:00", "2026-11-04T10:00:06.123Z", "yesterday", 5, ""):
        with pytest.raises(EventError):
            makers[event_type](bad)


# ---- run.started, run.ended, heartbeat ------------------------------------------------------------------------------

def test_run_started_matches_the_example():
    event = run_started_event(pid=48211, mock=False, seed="none", at="2026-11-04T10:00:06Z")
    assert event == {"t": "run.started", "at": "2026-11-04T10:00:06Z", "pid": 48211, "schema": "events/1", "mock": False, "seed": "none"}


@pytest.mark.parametrize("seed", ["none", "rehydrated", "fresh"])
def test_run_started_seed_words(seed):
    assert run_started_event(pid=1, mock=True, seed=seed)["seed"] == seed


@pytest.mark.parametrize("kwargs", [dict(pid=0, mock=True, seed="none"), dict(pid=-4, mock=True, seed="none"),
                                    dict(pid=True, mock=True, seed="none"), dict(pid="12", mock=True, seed="none"),
                                    dict(pid=1.0, mock=True, seed="none"), dict(pid=1, mock=1, seed="none"),
                                    dict(pid=1, mock="yes", seed="none"), dict(pid=1, mock=True, seed="old"),
                                    dict(pid=1, mock=True, seed=None), dict(pid=1, mock=True, seed="NONE")])
def test_run_started_refuses_bad_arguments(kwargs):
    with pytest.raises(EventError):
        run_started_event(**kwargs)


def test_run_started_needs_all_of_pid_mock_seed():
    with pytest.raises(TypeError):
        run_started_event(pid=1, mock=True)


def test_heartbeat_has_no_fields_but_t_and_at():
    assert heartbeat_event(at="2026-11-04T10:00:11Z") == {"t": "heartbeat", "at": "2026-11-04T10:00:11Z"}


@pytest.mark.parametrize("status", ["done", "done_with_open_items", "stopped", "crashed"])
def test_run_ended_status_words(status):
    code = "internal" if status == "crashed" else None
    assert run_ended_event(status=status, outcome="o", code=code)["status"] == status


@pytest.mark.parametrize("status", ["Done", "running", "failed", "", None, "cancelled"])
def test_run_ended_refuses_other_words(status):
    with pytest.raises(EventError):
        run_ended_event(status=status, outcome="o")


def test_run_ended_code_belongs_to_a_crashed_run_only():
    assert run_ended_event(status="crashed", outcome="could not start: x", code="start_failed")["code"] == "start_failed"
    assert run_ended_event(status="crashed", outcome="Crashed: boom")["code"] is None
    assert run_ended_event(status="done", outcome="Done")["code"] is None
    for status in ("done", "done_with_open_items", "stopped"):
        with pytest.raises(EventError):
            run_ended_event(status=status, outcome="o", code="timeout")
    with pytest.raises(EventError):
        run_ended_event(status="crashed", outcome="o", code="")
    with pytest.raises(EventError):
        run_ended_event(status="done", outcome=None)


# ---- say --------------------------------------------------------------------------------------------------------------

def test_say_matches_the_example_of_a_question():
    question = [{"question": "What are your opening hours?", "options": []}]
    event = say_event(id=3, who="identity", text="@Requester What are your opening hours?", to_user=True, act="ASK_REQUESTER",
                      pause="info", questions=question, next="user", at="2026-11-04T10:00:41Z")
    assert event == {"t": "say", "at": "2026-11-04T10:00:41Z", "id": 3, "who": "identity", "text": "@Requester What are your opening hours?",
                     "to_user": True, "act": "ASK_REQUESTER", "pause": "info", "questions": question, "next": "user"}


def test_say_nulls_what_is_absent():
    event = say_event(id=1, who="adaptation", text="t")
    assert (event["to_user"], event["act"], event["pause"], event["questions"], event["next"]) == (False, None, None, None, None)


@pytest.mark.parametrize("who", ["identity", "adaptation", "priority", "coordination", "audit", "validator", "system", "W-1",
                                 "W-12", "team:Web designer"])
def test_say_who_words(who):
    assert say_event(id=1, who=who, text="t")["who"] == who


@pytest.mark.parametrize("who", ["user", "Identity", "W-", "W-x", "team:", "team:\n", "", None, 5, "reviewer", "w-1"])
def test_say_refuses_the_owner_and_unknown_authors(who):
    with pytest.raises(EventError):
        say_event(id=1, who=who, text="t")


@pytest.mark.parametrize("bad", [dict(id=0), dict(id=-1), dict(id="1"), dict(id=True), dict(text=None), dict(text=5),
                                 dict(to_user=1), dict(to_user=None), dict(act=5), dict(pause=1), dict(next=7)])
def test_say_refuses_bad_arguments(bad):
    kwargs = dict(id=1, who="audit", text="t") | bad
    with pytest.raises(EventError):
        say_event(**kwargs)


def test_only_a_question_carries_questions():
    q = [{"question": "q?", "options": ["a"]}]
    assert say_event(id=1, who="identity", text="t", act="ASK_REQUESTER", questions=q)["questions"] == q
    for act in (None, "GRANT", "ask_requester"):
        with pytest.raises(EventError):
            say_event(id=1, who="identity", text="t", act=act, questions=q)
    for bad in ("q?", [["q"]], [1], {"question": "q"}):
        with pytest.raises(EventError):
            say_event(id=1, who="identity", text="t", act="ASK_REQUESTER", questions=bad)
    assert say_event(id=1, who="identity", text="t", act="ASK_REQUESTER", questions=[])["questions"] == []


def test_say_copies_its_questions():
    q = [{"question": "q?"}]
    event = say_event(id=1, who="identity", text="t", act="ASK_REQUESTER", questions=q)
    q[0]["question"] = "changed"
    assert event["questions"] == [{"question": "q?"}]


# ---- node -------------------------------------------------------------------------------------------------------------

def test_node_matches_the_example_and_has_no_goal():
    event = node_event(fn="identity", status="waiting_on_you", detail="Waiting for your answer", calls=1, seconds=6.2, task=TASK,
                       context=[("charter", "none yet")], wait_on="you", tokens={"input": 3100, "output": 240},
                       at="2026-11-04T10:00:41Z")
    assert event == {"t": "node", "at": "2026-11-04T10:00:41Z", "fn": "identity", "status": "waiting_on_you",
                     "detail": "Waiting for your answer", "calls": 1, "seconds": 6.2, "task": TASK, "context": ["charter: none yet"],
                     "wait_on": "you", "tokens": {"input": 3100, "output": 240}}
    assert list(event)[-4:] == ["task", "context", "wait_on", "tokens"]
    assert "goal" not in event


def test_node_has_no_goal_parameter():
    with pytest.raises(TypeError):
        node_event(fn="identity", status="idle", goal="x")


def test_node_leaves_out_the_optional_parts_it_was_not_given():
    event = node_event(fn="audit", status="idle")
    assert list(event) == ["t", "at", "fn", "status", "detail", "calls", "seconds"]
    assert (event["detail"], event["calls"], event["seconds"]) == ("", 0, 0.0)


def test_node_fills_wait_on_and_tokens_from_the_map_node():
    event = node_event(fn="coordination", status="waiting", wait_on="priority", tokens={"input": 10, "output": 2})
    assert event["wait_on"] == "priority" and event["tokens"] == {"input": 10, "output": 2}
    assert node_event(step="W-3", status="waiting", wait_on="W-2")["wait_on"] == "W-2"
    assert node_event(step="team:Copywriter", status="waiting", wait_on="you")["wait_on"] == "you"


@pytest.mark.parametrize("wait_on", ["you", "identity", "adaptation", "priority", "coordination", "audit", "W-7", "team:x"])
def test_node_wait_on_words(wait_on):
    assert node_event(fn="audit", status="waiting", wait_on=wait_on)["wait_on"] == wait_on


@pytest.mark.parametrize("wait_on", ["Requester", "validator", "user", "", "W-", "Identity", 5, ["you"]])
def test_node_refuses_other_wait_on_words(wait_on):
    with pytest.raises(EventError):
        node_event(fn="audit", status="waiting", wait_on=wait_on)


@pytest.mark.parametrize("tokens", [{"input": 1}, {"output": 1}, {"input": 1, "output": 2, "total": 3}, {"input": -1, "output": 2},
                                    {"input": 1.5, "output": 2}, {"input": True, "output": 2}, [1, 2], "12"])
def test_node_tokens_are_exactly_input_and_output(tokens):
    with pytest.raises(EventError):
        node_event(fn="audit", status="running", tokens=tokens)


def test_exactly_one_of_fn_and_step():
    for kwargs in ({}, {"fn": "audit", "step": "W-1"}):
        with pytest.raises(EventError):
            node_event(status="idle", **kwargs)
    assert node_event(fn="audit", status="idle")["fn"] == "audit"
    event = node_event(step="W-1", status="idle")
    assert event["step"] == "W-1" and "fn" not in event


@pytest.mark.parametrize("fn", ["Identity", "validator", "W-1", "", "root"])
def test_node_fn_must_be_one_of_the_five(fn):
    with pytest.raises(EventError):
        node_event(fn=fn, status="idle")


@pytest.mark.parametrize("step", ["W-", "w-1", "team:", "identity", "", "W-1 ", "task"])
def test_node_step_must_be_a_builder_or_a_team(step):
    with pytest.raises(EventError):
        node_event(step=step, status="idle")


NINE = ["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"]


def test_a_function_node_uses_the_first_five_words_a_step_all_nine():
    assert list(events.NODE_STATUSES) == NINE and events.FUNCTION_STATUSES == tuple(NINE[:5])
    for word in NINE[:5]:
        assert node_event(fn="priority", status=word)["status"] == word
    for word in NINE[5:]:
        with pytest.raises(EventError):
            node_event(fn="priority", status=word)
    for word in NINE:
        assert node_event(step="W-2", status=word)["status"] == word
    for bad in ("working", "blocked", "done", "", None, "Running"):
        with pytest.raises(EventError):
            node_event(step="W-2", status=bad)
        with pytest.raises(EventError):
            node_event(fn="audit", status=bad)


@pytest.mark.parametrize("bad", [dict(detail=None), dict(detail=3), dict(calls=-1), dict(calls=1.5), dict(calls=True),
                                 dict(seconds=-0.1), dict(seconds=float("nan")), dict(seconds=float("inf")), dict(seconds="2"),
                                 dict(seconds=True)])
def test_node_refuses_bad_numbers_and_text(bad):
    with pytest.raises(EventError):
        node_event(fn="audit", status="running", **bad)


def test_node_task_has_exactly_five_keys_and_a_state():
    assert node_event(fn="audit", status="running", task=TASK)["task"] == TASK
    assert node_event(fn="audit", status="running", task={**TASK, "kind": None, "state": "done"})["task"]["kind"] is None
    for bad in ({**TASK, "extra": 1}, {k: v for k, v in TASK.items() if k != "set_by"}, {**TASK, "state": "paused"},
                {**TASK, "id": ""}, {**TASK, "summary": 5}, [TASK], "t-1"):
        with pytest.raises(EventError):
            node_event(fn="audit", status="running", task=bad)


def test_node_task_summary_is_cut_to_300_characters():
    short = node_event(fn="audit", status="running", task={**TASK, "summary": "s" * 300})["task"]["summary"]
    assert short == "s" * 300
    long = node_event(fn="audit", status="running", task={**TASK, "summary": "s" * 301})["task"]["summary"]
    assert len(long) == 300 and long.endswith("…")


def test_context_pairs_become_kind_colon_summary_strings():
    assert context_strings([("charter", "none yet"), "ledger: 3 rows", ["chat", "12 messages"]]) == [
        "charter: none yet", "ledger: 3 rows", "chat: 12 messages"]
    assert context_strings([]) == []
    assert node_event(fn="audit", status="running", context=[])["context"] == []


def test_context_items_are_cut_to_200_characters_and_the_list_to_40():
    out = context_strings([("k", "v" * 500)] * 3)
    assert all(len(item) == 200 and item.endswith("…") for item in out)
    assert context_strings([("k", "v" * 193)]) == ["k: " + "v" * 193]                  # exactly 196 characters: kept whole
    assert context_strings(["x" * 200]) == ["x" * 200]
    assert len(context_strings([f"item {i}" for i in range(100)])) == 40
    assert context_strings([f"item {i}" for i in range(100)])[39] == "item 39"


@pytest.mark.parametrize("bad", ["a string", None, 5, [5], [("a",)], [("a", "b", "c")], [("a", 5)], [b"x"]])
def test_context_refuses_what_is_not_a_list_of_strings_or_pairs(bad):
    with pytest.raises(EventError):
        context_strings(bad)


# ---- step -------------------------------------------------------------------------------------------------------------

def test_step_matches_the_design():
    event = step_event(step="W-2", name="Menu section", status="running", parent="box-1", handoff=["W-3"], reads=["W-1"],
                       rework="W-1", at="2026-11-04T10:01:00Z")
    assert event == {"t": "step", "at": "2026-11-04T10:01:00Z", "step": "W-2", "name": "Menu section", "parent": "box-1",
                     "status": "running", "handoff": ["W-3"], "reads": ["W-1"], "rework": "W-1"}
    plain = step_event(step="team:Copywriter", name="Copy", status="filed")
    assert (plain["parent"], plain["handoff"], plain["reads"], plain["rework"]) == (None, [], [], None)


@pytest.mark.parametrize("bad", [dict(step="identity"), dict(step="W-"), dict(name=None), dict(status="working"),
                                 dict(parent=5), dict(handoff="W-1"), dict(handoff=[1]), dict(reads=None), dict(reads=[None]),
                                 dict(rework=5)])
def test_step_refuses_bad_arguments(bad):
    kwargs = dict(step="W-1", name="n", status="idle", handoff=[], reads=[]) | bad
    with pytest.raises(EventError):
        step_event(**kwargs)


# ---- atom -------------------------------------------------------------------------------------------------------------

def test_atom_has_the_twelve_fields_in_order():
    assert ATOM_KEYS == ("id", "schema", "goal", "work_kind", "verify_template", "status", "attempt", "closed_by", "reason", "body",
                         "ts_open", "ts_closed")
    event = atom_event(node="web.identity", atom=ATOM_V1)
    assert list(event["atom"]) == list(ATOM_KEYS)
    assert event["atom"] == ATOM_V1 and event["node"] == "web.identity"


def test_a_builders_atom_view_has_no_outcome_card_or_ledger():
    assert list(atom_event(node="W-1", atom=ATOM_V1)) == ["t", "at", "node", "atom"]
    for extra in ({"outcome": "closed"}, {"card": {"label": "x"}}, {"ledger": {"atom_id": "x"}}):
        with pytest.raises(EventError):
            atom_event(node="W-1", atom=ATOM_V1, **extra)


def test_a_function_atom_carries_outcome_card_and_ledger_next_to_the_atom():
    card = {"label": "ATOM OPENED", "goal": "g", "rows": [{"label": "a", "text": "b"}]}
    event = atom_event(node="web.identity", atom=ATOM_V03, outcome="opened", card=card)
    assert list(event) == ["t", "at", "node", "atom", "outcome", "card", "ledger"]
    assert (event["outcome"], event["card"], event["ledger"]) == ("opened", card, None)          # ledger: null while the atom is open
    closed = {**ATOM_V03, "status": "closed", "attempt": 1, "closed_by": "verify", "ts_closed": 1793748100}
    ledger = {"atom_id": ATOM_V03["id"], "status": "closed"}
    event = atom_event(node="web.identity", atom=closed, outcome="closed", card=card, ledger=ledger)
    assert event["ledger"] == ledger and event["atom"]["status"] == "closed"


def test_a_function_atom_event_without_outcome_or_card_has_nulls():
    event = atom_event(node="web.identity", atom=ATOM_V03)
    assert (event["outcome"], event["card"], event["ledger"]) == (None, None, None)


@pytest.mark.parametrize("outcome", ["opened", "verify_failed", "closed", "refused", "abandoned"])
def test_atom_outcome_words(outcome):
    assert atom_event(node="n", atom=ATOM_V03, outcome=outcome)["outcome"] == outcome


@pytest.mark.parametrize("outcome", ["open", "failed", "Closed", ""])
def test_atom_refuses_other_outcome_words(outcome):
    with pytest.raises(EventError):
        atom_event(node="n", atom=ATOM_V03, outcome=outcome)


def test_atom_status_words_depend_on_the_schema():
    for word in ("open", "closed", "verify_failed", "abandoned"):
        assert atom_event(node="n", atom={**ATOM_V1, "status": word})["atom"]["status"] == word
    for word in ("open", "closed", "refused", "abandoned"):
        assert atom_event(node="n", atom={**ATOM_V03, "status": word})["atom"]["status"] == word
    with pytest.raises(EventError):
        atom_event(node="n", atom={**ATOM_V1, "status": "refused"})
    with pytest.raises(EventError):
        atom_event(node="n", atom={**ATOM_V03, "status": "verify_failed"})


def test_atom_fills_missing_optional_fields_with_null():
    sparse = {k: v for k, v in ATOM_V03.items() if k not in ("verify_template", "closed_by", "reason", "ts_closed")}
    atom = atom_event(node="n", atom=sparse)["atom"]
    assert (atom["verify_template"], atom["closed_by"], atom["reason"], atom["ts_closed"]) == (None, None, None, None)


@pytest.mark.parametrize("change", [
    {"id": "A-1"}, {"id": ""}, {"id": "a-3f9a1c2b7d-1"}, {"schema": "atom/2"}, {"work_kind": "ai"}, {"attempt": 4}, {"attempt": -1},
    {"attempt": True}, {"attempt": "1"}, {"body": "x"}, {"body": None}, {"ts_open": -1}, {"ts_open": 1.5}, {"ts_closed": "soon"},
    {"goal": None}, {"reason": 5}, {"closed_by": 5}, {"verify_template": 5}, {"unknown": 1}])
def test_atom_refuses_bad_fields(change):
    with pytest.raises(EventError):
        atom_event(node="n", atom={**ATOM_V03, **change})


@pytest.mark.parametrize("missing", ["id", "schema", "goal", "work_kind", "status", "attempt", "body", "ts_open"])
def test_atom_needs_its_required_fields(missing):
    with pytest.raises(EventError):
        atom_event(node="n", atom={k: v for k, v in ATOM_V03.items() if k != missing})


def test_atom_attempt_runs_from_zero_to_three():
    for attempt in range(4):
        assert atom_event(node="n", atom={**ATOM_V03, "attempt": attempt})["atom"]["attempt"] == attempt


def test_atom_work_kinds():
    for kind in ("llm", "skill", "bash", "manual"):
        assert atom_event(node="n", atom={**ATOM_V03, "work_kind": kind})["atom"]["work_kind"] == kind


def test_atom_node_atom_and_the_parts_must_be_objects():
    for bad in ("", None, 5):
        with pytest.raises(EventError):
            atom_event(node=bad, atom=ATOM_V03)
    with pytest.raises(EventError):
        atom_event(node="n", atom="a-3f9a1c2b7d-01")
    for part in ({"card": "x"}, {"ledger": "x"}):
        with pytest.raises(EventError):
            atom_event(node="n", atom=ATOM_V03, **part)


def test_atom_body_is_copied():
    body = {"state": "open"}
    event = atom_event(node="n", atom={**ATOM_V03, "body": body})
    body["state"] = "changed"
    assert event["atom"]["body"] == {"state": "open"}


# ---- usage ------------------------------------------------------------------------------------------------------------

def test_usage_matches_the_example():
    event = usage_event(**USAGE, at="2026-11-04T10:00:41Z")
    assert event == {"t": "usage", "at": "2026-11-04T10:00:41Z", "fn": "identity", "step": "J2.a", "atom": "a-3f9a1c2b7d-01",
                     "provider": "claude", "model": "sonnet", "purpose": "agent_turn", "usd": 0.012, "tokens_in": 3100,
                     "tokens_out": 240, "seconds": 6.2, "ok": True, "how": "native", "call_ref": RUN + ":1", "detail": None}


def test_usage_allows_the_nulls_of_the_design():
    event = usage_event(**{**USAGE, "step": None, "atom": None, "model": None, "usd": None, "tokens_in": None, "tokens_out": None,
                           "detail": {"request_id": "x", "attempts": []}})
    assert (event["step"], event["atom"], event["model"], event["usd"], event["tokens_in"], event["tokens_out"]) == (None,) * 6
    assert event["detail"] == {"request_id": "x", "attempts": []}


@pytest.mark.parametrize("bad", [dict(fn=None), dict(provider=""), dict(provider=None), dict(purpose=""), dict(how=""), dict(call_ref=""),
                                 dict(call_ref=None), dict(usd=-0.001), dict(usd=float("nan")), dict(usd="0.1"), dict(tokens_in=-1),
                                 dict(tokens_in=1.5), dict(tokens_out=True), dict(seconds=-1), dict(seconds=None), dict(ok=1),
                                 dict(ok=None), dict(detail="x"), dict(detail=[1]), dict(atom=5), dict(step=3), dict(model=7)])
def test_usage_refuses_bad_arguments(bad):
    with pytest.raises(EventError):
        usage_event(**{**USAGE, **bad})


def test_usage_needs_every_field():
    for name in ("fn", "step", "atom", "provider", "model", "purpose", "usd", "tokens_in", "tokens_out", "seconds", "ok", "how", "call_ref"):
        with pytest.raises(TypeError):
            usage_event(**{k: v for k, v in USAGE.items() if k != name})


def test_usage_zero_is_a_value_not_an_absence():
    event = usage_event(**{**USAGE, "usd": 0, "tokens_in": 0, "tokens_out": 0, "seconds": 0})
    assert (event["usd"], event["tokens_in"], event["tokens_out"], event["seconds"]) == (0.0, 0, 0, 0.0)


# ---- the line format ---------------------------------------------------------------------------------------------------

def test_a_line_is_compact_ascii_json_and_one_newline():
    line = encode_line({"t": "say", "text": "café   and \u0085 and \ud800 and \"q\"\nnext", "n": 1.5, "ok": True, "x": None})
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert line.isascii()
    parsed = json.loads(line)
    assert parsed["text"] == "café   and \u0085 and \ud800 and \"q\"\nnext"
    assert line.startswith(b'{"t":"say","text":"caf\\u00e9 \\u2028')
    assert len(line.decode("ascii").splitlines()) == 1


def test_a_line_refuses_nan_and_non_json_values():
    with pytest.raises(ValueError):
        encode_line({"seconds": float("nan")})
    with pytest.raises(ValueError):
        encode_line({"seconds": float("inf")})
    with pytest.raises(TypeError):
        encode_line({"when": object()})


# ---- EventWriter ------------------------------------------------------------------------------------------------------

@pytest.fixture
def writer(tmp_path):
    w = EventWriter(tmp_path, clock=lambda: 1793750406.4)
    yield w
    w.close()


def test_emit_appends_a_whole_line_and_stamps_at(writer, tmp_path):
    written = writer.emit({"t": "heartbeat"})
    assert written == {"t": "heartbeat", "at": "2026-11-04T00:00:06Z"}
    assert (tmp_path / "events.jsonl").read_bytes() == b'{"t":"heartbeat","at":"2026-11-04T00:00:06Z"}\n'
    writer.emit(say_event(id=1, who="system", text="hi", at="2026-11-04T10:00:00Z"))
    assert [e["t"] for e in lines(tmp_path / "events.jsonl")] == ["heartbeat", "say"]
    assert lines(tmp_path / "events.jsonl")[1]["at"] == "2026-11-04T10:00:00Z"


def test_emit_puts_t_and_at_first_whatever_the_order_given(writer, tmp_path):
    writer.emit({"pid": 1, "at": "2026-11-04T10:00:00Z", "schema": "events/1", "t": "run.started", "mock": True, "seed": "none"})
    assert list(lines(tmp_path / "events.jsonl")[0])[:2] == ["t", "at"]


def test_emit_refuses_a_type_outside_the_closed_list(writer, tmp_path):
    for bad in ({"t": "session"}, {"t": "Say"}, {"at": "2026-11-04T10:00:00Z"}, {}, "heartbeat", None, {"t": None}):
        with pytest.raises(EventError):
            writer.emit(bad)
    assert (tmp_path / "events.jsonl").read_bytes() == b""


def test_emit_refuses_a_bad_at(writer, tmp_path):
    with pytest.raises(EventError):
        writer.emit({"t": "heartbeat", "at": "now"})
    assert (tmp_path / "events.jsonl").read_bytes() == b""


def test_a_non_json_event_writes_nothing(writer, tmp_path):
    with pytest.raises(TypeError):
        writer.emit({"t": "say", "text": object()})
    with pytest.raises(ValueError):
        writer.emit({"t": "node", "seconds": float("nan")})
    assert (tmp_path / "events.jsonl").read_bytes() == b""


def test_the_writer_appends_to_the_file_the_orchestrator_made(tmp_path):
    path = tmp_path / "events.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, b'{"t":"run.started"}\n')
    os.close(fd)
    with EventWriter(tmp_path) as w:
        w.emit({"t": "heartbeat"})
    assert path.read_text().splitlines()[0] == '{"t":"run.started"}'
    assert len(path.read_text().splitlines()) == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_new_files_are_private(tmp_path):
    with EventWriter(tmp_path) as w:
        w.emit({"t": "heartbeat"})
        w.trace("turn.started")
    for name in ("events.jsonl", "trace.jsonl"):
        assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600


def test_the_writer_never_makes_the_run_directory(tmp_path):
    missing = tmp_path / "no-such-run"
    with pytest.raises(FileNotFoundError):
        EventWriter(missing)
    assert not missing.exists()
    (tmp_path / "plain").write_text("x")
    with pytest.raises(NotADirectoryError):
        EventWriter(tmp_path / "plain")


def test_trace_lines_have_seq_at_type_and_data(writer, tmp_path):
    assert not (tmp_path / "trace.jsonl").exists()                     # opened on the first trace line
    first = writer.trace("turn.started", {"turn_no": 3})
    second = writer.trace("record.saved")
    assert first == {"seq": 1, "at": "2026-11-04T00:00:06Z", "type": "turn.started", "data": {"turn_no": 3}}
    assert second["seq"] == 2 and second["data"] == {}
    assert lines(tmp_path / "trace.jsonl") == [first, second]
    assert list(first) == ["seq", "at", "type", "data"]


def test_trace_needs_a_type_and_makes_no_event(writer, tmp_path):
    for bad in ("", None, 5):
        with pytest.raises(EventError):
            writer.trace(bad)
    assert (tmp_path / "events.jsonl").read_bytes() == b""
    assert writer.trace("x")["seq"] == 1                                # the refusals used no number


def test_nothing_follows_run_ended_in_events_but_the_trace_stays_open(writer, tmp_path):
    writer.emit({"t": "heartbeat"})
    assert writer.ended is False
    writer.emit(run_ended_event(status="done", outcome="Done"))
    assert writer.ended is True
    for event in ({"t": "heartbeat"}, run_ended_event(status="stopped", outcome="again"), say_event(id=9, who="system", text="late")):
        with pytest.raises(EventError, match="run.ended"):
            writer.emit(event)
    assert [e["t"] for e in lines(tmp_path / "events.jsonl")] == ["heartbeat", "run.ended"]
    assert writer.trace("layer.error", {"late": True})["seq"] == 1


def test_a_closed_writer_refuses_everything_and_close_is_safe_twice(tmp_path):
    w = EventWriter(tmp_path)
    w.trace("a")
    assert w.closed is False
    w.close()
    w.close()
    assert w.closed is True
    with pytest.raises(EventError, match="closed"):
        w.emit({"t": "heartbeat"})
    with pytest.raises(EventError, match="closed"):
        w.trace("b")


def test_the_context_manager_closes_the_writer(tmp_path):
    with EventWriter(tmp_path) as w:
        assert w.closed is False
    assert w.closed is True


def test_one_line_is_one_write_call(monkeypatch, tmp_path):
    calls = []
    real = EventWriter._write_all
    monkeypatch.setattr(EventWriter, "_write_all", staticmethod(lambda fd, data, write=os.write: (calls.append(data), real(fd, data))[1]))
    with EventWriter(tmp_path) as w:
        w.emit({"t": "heartbeat"})
        w.trace("x")
    assert len(calls) == 2 and all(c.endswith(b"\n") and c.count(b"\n") == 1 for c in calls)


def test_a_short_write_is_completed_before_the_next_line():
    chunks = []

    def short(fd, view):
        piece = bytes(view[:5])
        chunks.append(piece)
        return len(piece)

    EventWriter._write_all(1, b"0123456789abcdef", short)
    assert b"".join(chunks) == b"0123456789abcdef" and len(chunks) == 4


def test_a_write_that_makes_no_progress_is_an_error_not_a_loop():
    with pytest.raises(OSError, match="no progress"):
        EventWriter._write_all(1, b"abc", lambda fd, view: 0)


def test_a_write_from_inside_a_write_does_not_deadlock(tmp_path):
    """A SIGTERM handler runs in the thread that is writing; it must still be able to write run.ended."""
    w = EventWriter(tmp_path)
    real = EventWriter._write_all
    nested = []

    def write_all(fd, data, write=os.write):
        if not nested:
            nested.append(True)                       # the handler is the first to arrive inside a write, once
            w.emit(run_ended_event(status="stopped", outcome="Stopped: stopped on request"))
        real(fd, data, write)

    EventWriter._write_all = staticmethod(write_all)
    try:
        done = threading.Event()
        threading.Thread(target=lambda: (w.trace("x"), done.set()), daemon=True).start()
        assert done.wait(5), "the nested write waited for the lock held by its own thread"
    finally:
        EventWriter._write_all = staticmethod(real)
    assert [e["t"] for e in lines(tmp_path / "events.jsonl")] == ["run.ended"] and w.ended
    w.close()


def test_lines_stay_whole_under_eight_concurrent_writers(tmp_path):
    per_thread, payload = 150, "x" * 3000
    w = EventWriter(tmp_path)
    barrier = threading.Barrier(9)

    def work(n):
        barrier.wait()
        for i in range(per_thread):
            w.emit({"t": "say", "id": n * 1000 + i + 1, "who": "system", "text": payload, "to_user": False})
            w.trace("t", {"thread": n, "i": i})

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    barrier.wait()
    for t in threads:
        t.join()
    w.close()
    got = lines(tmp_path / "events.jsonl")
    assert len(got) == 8 * per_thread and all(e["text"] == payload for e in got)
    for n in range(8):
        ids = [e["id"] for e in got if e["id"] // 1000 == n]
        assert ids == [n * 1000 + i + 1 for i in range(per_thread)]                    # each thread's lines in its own order
    trace = lines(tmp_path / "trace.jsonl")
    assert [t["seq"] for t in trace] == list(range(1, 8 * per_thread + 1))             # numbered in file order, none twice


# ---- EventUsageSink ----------------------------------------------------------------------------------------------------

ROW = {"provider": "stub", "model": "scripted", "purpose": "agent_turn", "session_id": None, "node_id": None, "task_id": "tsk_1",
       "dept_id": "web", "fn": "audit", "step": "J2.g", "atom_id": "W-1.a2", "tokens_in": 10, "tokens_out": 3, "usd": 0.0, "seconds": 0.01,
       "ok": True, "how": "stub", "call_ref": RUN + ":12", "detail": None}


def test_the_sink_appends_one_usage_line_and_counts(writer, tmp_path):
    sink = EventUsageSink(writer)
    assert sink.record(ROW) == 1
    assert sink.record({**ROW, "call_ref": RUN + ":13"}) == 2
    got = lines(tmp_path / "events.jsonl")
    assert [e["t"] for e in got] == ["usage", "usage"]
    first = got[0]
    assert list(first) == ["t", "at", "fn", "step", "atom", "provider", "model", "purpose", "usd", "tokens_in", "tokens_out",
                           "seconds", "ok", "how", "call_ref", "detail"]
    assert (first["fn"], first["step"], first["atom"], first["call_ref"]) == ("audit", "J2.g", "W-1.a2", RUN + ":12")
    assert sink.count == 2


def test_the_sink_ignores_the_ids_that_belong_to_the_server(writer, tmp_path):
    EventUsageSink(writer).record({**ROW, "session_id": "cs_1", "node_id": "web.audit", "task_id": "tsk_9", "dept_id": "web", "extra": 1})
    event = lines(tmp_path / "events.jsonl")[0]
    assert not {"session_id", "node_id", "task_id", "dept_id", "extra", "atom_id"} & set(event)


def test_the_sink_takes_an_object_with_model_dump(writer, tmp_path):
    class Row:
        def model_dump(self):
            return dict(ROW)
    assert EventUsageSink(writer).record(Row()) == 1
    assert lines(tmp_path / "events.jsonl")[0]["atom"] == "W-1.a2"


def test_the_sink_refuses_what_is_neither_a_mapping_nor_a_model(writer, tmp_path):
    for bad in ("row", 5, None, [ROW]):
        with pytest.raises(TypeError):
            EventUsageSink(writer).record(bad)
    assert (tmp_path / "events.jsonl").read_bytes() == b""


def test_atom_id_becomes_atom_and_atom_wins_when_both_are_given(writer, tmp_path):
    sink = EventUsageSink(writer)
    sink.record({k: v for k, v in ROW.items() if k != "atom_id"} | {"atom": "a-3f9a1c2b7d-01"})
    sink.record({**ROW, "atom": "a-3f9a1c2b7d-02"})
    sink.record({**ROW, "atom": None})
    assert [e["atom"] for e in lines(tmp_path / "events.jsonl")] == ["a-3f9a1c2b7d-01", "a-3f9a1c2b7d-02", "W-1.a2"]


def test_a_row_without_an_atom_is_charged_to_the_default_atom(writer, tmp_path):
    overhead = overhead_atom_id(RUN)
    sink = EventUsageSink(writer, default_atom=overhead)
    sink.record({**ROW, "atom_id": None})
    sink.record({**ROW, "atom_id": "W-1.a2"})                           # its own atom wins
    assert [e["atom"] for e in lines(tmp_path / "events.jsonl")] == [overhead, "W-1.a2"]
    EventUsageSink(writer).record({**ROW, "atom_id": None})
    assert lines(tmp_path / "events.jsonl")[-1]["atom"] is None          # nothing to fill it with: it stays null


def test_a_row_with_a_missing_or_bad_part_writes_nothing_and_counts_nothing(writer, tmp_path):
    sink = EventUsageSink(writer)
    for bad in ({k: v for k, v in ROW.items() if k != "provider"}, {**ROW, "ok": None}, {**ROW, "call_ref": None},
                {k: v for k, v in ROW.items() if k != "ok"}, {**ROW, "usd": -1.0}, {**ROW, "tokens_in": "10"}):
        with pytest.raises(EventError):
            sink.record(bad)
    assert sink.count == 0 and (tmp_path / "events.jsonl").read_bytes() == b""
    assert sink.record(ROW) == 1


def test_a_row_without_fn_is_charged_to_the_empty_function(writer, tmp_path):
    EventUsageSink(writer).record({**ROW, "fn": None})
    assert lines(tmp_path / "events.jsonl")[0]["fn"] == ""


def test_the_sink_counter_is_safe_across_threads(tmp_path):
    w = EventWriter(tmp_path)
    sink = EventUsageSink(w)
    seen, lock = [], threading.Lock()

    def work():
        for i in range(60):
            n = sink.record({**ROW, "call_ref": f"r:{threading.get_ident()}-{i}"})
            with lock:
                seen.append(n)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    w.close()
    assert sorted(seen) == list(range(1, 481)) and len(lines(tmp_path / "events.jsonl")) == 480


def test_a_mock_call_through_scripted_port_and_the_sink_makes_a_valid_usage_line(tmp_path, llm_reset, clean_env):
    with EventWriter(tmp_path) as w:
        overhead = overhead_atom_id(RUN)
        llm.configure(llm.ScriptedPort(EventUsageSink(w, default_atom=overhead), delay=0),
                      base_tag={"run_id": RUN, "dept_id": "web", "task_id": "tsk_1"})
        llm.bind_atom(overhead)
        assert llm.ask("s", "u", lambda: "ok") == "ok"                                    # outside any turn: the run's overhead key
        with llm.tagged(function="identity", step=1, call_no=1, atom="a-3f9a1c2b7d-01"):
            llm.ask("s", "u", lambda: "ok")
    first, second = lines(tmp_path / "events.jsonl")
    assert (first["atom"], first["call_ref"], first["fn"], first["step"]) == (overhead, "r:1", "", None)
    assert (second["atom"], second["call_ref"], second["fn"], second["step"]) == ("a-3f9a1c2b7d-01", RUN + ":1", "identity", "J2.a")
    assert all(e["provider"] == "stub" and e["model"] == "scripted" and e["how"] == "stub" and e["ok"] is True for e in (first, second))


# ---- the hook records -------------------------------------------------------------------------------------------------

def turn(**kw):
    base = dict(run_id=RUN, dept_id="web", task_id="tsk_1", turn_no=3, function="adaptation", kind="propose", step=2,
                step_label="J2.b Adaptation proposes workflows", cycle=1, stage="website", task="why",
                context=[("charter", "none yet")])
    return TurnInfo(**(base | kw))


def call(**kw):
    base = dict(call_no=7, function="adaptation", step=2, stage="website", purpose="agent_turn", model="sonnet", provider="claude",
                tokens={"input": 10, "output": 2}, usd=0.01, seconds=1.5, session_id=None, inputs=[["task", "t"]], reply={"say": "x"},
                reason="because", atom="a-3f9a1c2b7d-02")
    return CallInfo(**(base | kw))


def test_turn_info_fields_and_context_pairs():
    assert list(TurnInfo.model_fields) == ["run_id", "dept_id", "task_id", "turn_no", "function", "kind", "step", "step_label", "cycle",
                                           "stage", "task", "context"]
    t = turn(context=[["charter", "none"], ("ledger", "3 rows")])
    assert t.context == [("charter", "none"), ("ledger", "3 rows")]
    assert "goal" not in TurnInfo.model_fields                                        # it duplicated step_label
    with pytest.raises(Exception):
        turn(goal="x")
    with pytest.raises(Exception):
        turn(context=[("only one",)])


def test_turn_info_may_leave_task_kind_and_stage_null():
    t = TurnInfo(run_id=RUN, dept_id="web", turn_no=1, function="identity", step=1, step_label="J2.a", cycle=0, task="t", context=[])
    assert (t.task_id, t.kind, t.stage) == (None, None, None)
    for missing in ("run_id", "dept_id", "turn_no", "function", "step", "step_label", "cycle", "task", "context"):
        kwargs = dict(run_id=RUN, dept_id="web", turn_no=1, function="identity", step=1, step_label="J2.a", cycle=0, task="t", context=[])
        del kwargs[missing]
        with pytest.raises(Exception):
            TurnInfo(**kwargs)


def test_call_info_fields_and_closed():
    assert list(CallInfo.model_fields) == ["call_no", "function", "step", "stage", "purpose", "model", "provider", "tokens", "usd", "seconds",
                                           "session_id", "inputs", "reply", "reason", "atom"]
    assert call().atom == "a-3f9a1c2b7d-02"
    with pytest.raises(Exception):
        call(cost=1)


def test_turn_outcome_results_and_defaults():
    assert TurnOutcome(result="ok").model_dump() == {"result": "ok", "next": None, "messages": [], "calls": [], "notes": []}
    for result in ("ok", "redirected", "paused", "error"):
        assert TurnOutcome(result=result, next="priority", messages=[1, 2], calls=[3], notes=["n"]).result == result
    for bad in ("done", "", "OK", None):
        with pytest.raises(Exception):
            TurnOutcome(result=bad)


# ---- NullHooks and the protocol -----------------------------------------------------------------------------------------

def test_null_hooks_do_nothing():
    h = NullHooks()
    assert h.run_started({}) is None and h.run_status({}) is None
    assert h.turn_started(turn()) is None and h.turn_finished(turn(), TurnOutcome(result="ok")) is None
    assert h.call_finished(call()) is None and h.message_posted({"id": 1}) is None and h.message_posted({"id": 1}, questions=[]) is None
    assert h.record_saved("goal.json", {}) == [] and h.run_error("internal", "boom") is None
    assert h.system_addendum("identity") == ""


def test_the_hook_classes_satisfy_the_protocol():
    assert isinstance(NullHooks(), EngineHooks)
    assert not isinstance(object(), EngineHooks)
    assert [n for n in vars(EngineHooks) if not n.startswith("_") and callable(getattr(EngineHooks, n))] == [
        "run_started", "run_status", "turn_started", "turn_finished", "call_finished", "message_posted", "record_saved",
        "run_error", "system_addendum"]


# ---- EventHooks -------------------------------------------------------------------------------------------------------

class Notes:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1


@pytest.fixture
def hk(tmp_path):
    w = EventWriter(tmp_path)
    notes = Notes()
    h = EventHooks(w, notes)
    h.notes, h.dir = notes, tmp_path
    yield h
    w.close()


def trace_of(h):
    path = h.dir / "trace.jsonl"
    return lines(path) if path.exists() else []


def test_event_hooks_are_hooks_and_a_null_hooks_subclass(hk):
    assert isinstance(hk, EngineHooks) and isinstance(hk, NullHooks)


def test_turn_started_traces_the_example_line_and_wakes_the_publisher(hk):
    hk.turn_started(turn())
    (line,) = trace_of(hk)
    assert line["type"] == "turn.started" and line["seq"] == 1
    assert line["data"] == {"turn_no": 3, "function": "adaptation", "kind": "propose", "step": 2,
                            "step_label": "J2.b Adaptation proposes workflows", "cycle": 1}
    assert hk.notes.n == 1


def test_turn_finished_traces_the_outcome(hk):
    hk.turn_finished(turn(), TurnOutcome(result="redirected", next="identity", messages=[4, 5], calls=[7], notes=["n" * 900]))
    (line,) = trace_of(hk)
    assert line["type"] == "turn.finished"
    assert line["data"]["turn_no"] == 3 and line["data"]["function"] == "adaptation"
    assert (line["data"]["result"], line["data"]["next"], line["data"]["messages"], line["data"]["calls"]) == ("redirected", "identity", [4, 5], [7])
    assert len(line["data"]["notes"][0]) == 500
    assert hk.notes.n == 1


def test_call_finished_traces_the_call_without_its_bulk(hk):
    hk.call_finished(call())
    (line,) = trace_of(hk)
    assert line["type"] == "call.finished"
    assert line["data"] == {"call_no": 7, "function": "adaptation", "step": 2, "stage": "website", "purpose": "agent_turn", "model": "sonnet",
                            "provider": "claude", "tokens": {"input": 10, "output": 2}, "usd": 0.01, "seconds": 1.5, "session_id": None,
                            "atom": "a-3f9a1c2b7d-02"}
    assert hk.notes.n == 1


def test_run_status_only_wakes_the_publisher(hk):
    hk.run_status({"status": "waiting", "chat": ["a huge snapshot"]})
    assert hk.notes.n == 1 and trace_of(hk) == []


def test_run_started_does_nothing(hk):
    hk.run_started({"run_id": RUN})
    assert hk.notes.n == 0 and trace_of(hk) == [] and not (hk.dir / "events.jsonl").read_bytes()


def test_run_error_is_remembered_traced_and_wakes_the_publisher(hk):
    assert hk.last_error is None
    hk.run_error("timeout", "Stopped: ModelTimeout: " + "x" * 700)
    assert hk.last_error == ("timeout", "Stopped: ModelTimeout: " + "x" * 700)
    (line,) = trace_of(hk)
    assert line["type"] == "run.error" and line["data"]["code"] == "timeout" and len(line["data"]["message"]) == 500
    assert hk.notes.n == 1


def test_a_message_becomes_a_say_event(hk):
    hk.message_posted({"id": 3, "t": "10:00:41", "who": "adaptation", "text": "I propose three workflows.", "step": 2, "next": "priority"})
    (event,) = lines(hk.dir / "events.jsonl")
    assert event["t"] == "say" and AT.match(event["at"])
    assert {k: event[k] for k in ("id", "who", "text", "to_user", "act", "pause", "questions", "next")} == {
        "id": 3, "who": "adaptation", "text": "I propose three workflows.", "to_user": False, "act": None, "pause": None,
        "questions": None, "next": "priority"}
    assert hk.notes.n == 1


def test_a_question_to_the_owner_carries_its_questions(hk):
    questions = [{"question": "What are your opening hours?", "options": []}]
    hk.message_posted({"id": 3, "t": "10:00:41", "who": "identity", "text": "@Requester What are your opening hours?", "step": 1,
                       "act": "ASK_REQUESTER", "to_user": True, "next": "user", "pause": "info"}, questions=questions)
    (event,) = lines(hk.dir / "events.jsonl")
    assert (event["to_user"], event["act"], event["pause"], event["next"], event["questions"]) == (True, "ASK_REQUESTER", "info", "user", questions)


def test_questions_are_dropped_for_a_message_that_is_not_a_question(hk):
    hk.message_posted({"id": 4, "who": "identity", "text": "ok", "to_user": True}, questions=[{"question": "q"}])
    assert lines(hk.dir / "events.jsonl")[0]["questions"] is None


def test_the_owners_own_lines_are_not_events(hk):
    hk.message_posted({"id": 1, "t": "10:00:00", "who": "user", "text": "A website for my cafe", "step": 0})
    assert (hk.dir / "events.jsonl").read_bytes() == b"" and hk.notes.n == 1


def test_a_malformed_message_raises_for_j2_to_catch(hk):
    with pytest.raises(EventError):
        hk.message_posted({"who": "identity", "text": "no id"})
    with pytest.raises(EventError):
        hk.message_posted({"id": 2, "who": "stranger", "text": "who?"})


def test_every_message_line_is_checked_as_chat_jsonl(tmp_path):
    seen = []
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), validator=lambda name, data: seen.append((name, data)))
    h.message_posted({"id": 1, "who": "user", "text": "hi"})
    h.message_posted({"id": 2, "who": "identity", "text": "hello"})
    w.close()
    assert [name for name, _ in seen] == ["chat.jsonl", "chat.jsonl"] and seen[1][1]["id"] == 2


def test_record_saved_checks_the_record_and_traces_the_save(tmp_path):
    seen = []
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), validator=lambda name, data: seen.append((name, data)))
    assert h.record_saved("goal.json", {"statement": "x"}) == []
    assert seen == [("goal.json", {"statement": "x"})]
    assert lines(tmp_path / "trace.jsonl") == [{**lines(tmp_path / "trace.jsonl")[0], "type": "record.saved", "data": {"name": "goal.json", "warnings": 0}}]
    w.close()


def test_without_a_validator_nothing_is_checked(hk):
    assert hk.record_saved("goal.json", {}) == []
    assert [t["type"] for t in trace_of(hk)] == ["record.saved"]
    hk.message_posted({"id": 1, "who": "system", "text": "t"})
    assert [t["type"] for t in trace_of(hk)] == ["record.saved"]


def test_warnings_from_the_validator_become_trace_lines_and_are_returned(tmp_path):
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), validator=lambda name, data: ["goal: statement is empty", "goal: no done_when"])
    assert h.record_saved("goal.json", {}) == ["goal: statement is empty", "goal: no done_when"]
    got = lines(tmp_path / "trace.jsonl")
    assert [(t["type"], t["data"]) for t in got] == [
        ("record.warning", {"name": "goal.json", "warning": "goal: statement is empty", "fatal": False}),
        ("record.warning", {"name": "goal.json", "warning": "goal: no done_when", "fatal": False}),
        ("record.saved", {"name": "goal.json", "warnings": 2})]
    w.close()


def test_a_validator_result_that_is_not_a_list_means_no_warnings(tmp_path):
    w = EventWriter(tmp_path)
    for result in (None, {"ok": True}, "fine", 0):
        assert EventHooks(w, Notes(), validator=lambda name, data, r=result: r).record_saved("x.json", {}) == []
    w.close()


def test_a_validator_that_raises_is_a_warning_not_a_failure(tmp_path):
    def broken(name, data):
        raise ValueError("a" * 800)
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), validator=broken)
    (warning,) = h.record_saved("goal.json", {})
    assert warning.startswith("ValueError: aaa") and len(warning) == 500
    h.message_posted({"id": 1, "who": "system", "text": "still delivered"})
    assert lines(tmp_path / "events.jsonl")[0]["text"] == "still delivered"
    w.close()


class RecordRejected(Exception):
    """The library's strict-mode error is recognised by its name."""


class Fatal(Exception):
    fatal = True


class NotFatal(Exception):
    fatal = False


@pytest.mark.parametrize("exc, fatal", [(RecordRejected("x"), True), (Fatal("x"), True), (NotFatal("x"), False), (ValueError("x"), False),
                                        (KeyError("x"), False)])
def test_is_fatal_follows_p8(exc, fatal):
    assert is_fatal(exc) is fatal


@pytest.mark.parametrize("exc", [RecordRejected("goal.json: rejected"), Fatal("stop the run")])
def test_a_fatal_validator_error_is_traced_and_raised_again(tmp_path, exc):
    def strict(name, data):
        raise exc
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), validator=strict)
    with pytest.raises(type(exc)):
        h.record_saved("goal.json", {})
    (line,) = lines(tmp_path / "trace.jsonl")
    assert line["type"] == "record.warning" and line["data"]["fatal"] is True and line["data"]["name"] == "goal.json"
    w.close()


def test_a_fatal_error_on_a_chat_line_comes_after_the_say_event(tmp_path):
    def strict(name, data):
        raise RecordRejected("chat.jsonl: bad line")
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), validator=strict)
    with pytest.raises(RecordRejected):
        h.message_posted({"id": 5, "who": "audit", "text": "findings"})
    assert [e["t"] for e in lines(tmp_path / "events.jsonl")] == ["say"]                # J2 wrote the line, so the owner sees it
    w.close()


def test_a_keyboard_interrupt_is_not_swallowed(tmp_path):
    def interrupted(name, data):
        raise KeyboardInterrupt
    w = EventWriter(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        EventHooks(w, Notes(), validator=interrupted).record_saved("goal.json", {})
    w.close()


# ---- system_addendum ---------------------------------------------------------------------------------------------------

def test_no_node_context_file_means_no_addendum(hk):
    assert hk.system_addendum("identity") == ""


def test_the_addendum_is_the_functions_text_under_a_heading_and_is_reread_every_call(tmp_path):
    ctx = tmp_path / "node-context.json"
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), node_context_file=ctx)
    assert h.system_addendum("identity") == ""                                           # not written yet: normal
    ctx.write_text(json.dumps({"identity": "Prefer short answers.", "audit": "Check the footer."}))
    assert h.system_addendum("identity") == "\n\n## Node context\nPrefer short answers."
    assert h.system_addendum("audit") == "\n\n## Node context\nCheck the footer."
    assert h.system_addendum("priority") == ""
    ctx.write_text(json.dumps({"identity": "Changed."}))
    assert h.system_addendum("identity") == "\n\n## Node context\nChanged."
    assert h.system_addendum("audit") == ""
    ctx.unlink()
    assert h.system_addendum("identity") == ""
    assert not (tmp_path / "trace.jsonl").exists()
    assert hooks.ADDENDUM_HEADING == "\n\n## Node context\n"
    w.close()


def test_an_empty_or_odd_text_is_no_addendum(tmp_path):
    ctx = tmp_path / "c.json"
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), node_context_file=str(ctx))
    ctx.write_text(json.dumps({"identity": "", "audit": "  \n", "priority": 5, "coordination": None, "adaptation": ["x"]}))
    assert [h.system_addendum(f) for f in ("identity", "audit", "priority", "coordination", "adaptation")] == [""] * 5
    w.close()


def test_a_bad_context_file_never_breaks_a_prompt_and_is_noted_once(tmp_path):
    ctx = tmp_path / "c.json"
    w = EventWriter(tmp_path)
    h = EventHooks(w, Notes(), node_context_file=ctx)
    ctx.write_text("{not json")
    assert h.system_addendum("identity") == "" and h.system_addendum("audit") == ""
    ctx.write_text(json.dumps(["a", "list"]))
    assert h.system_addendum("identity") == ""
    ctx.write_bytes(b"\xff\xfe\x00bad")
    assert h.system_addendum("identity") == ""
    got = [t for t in lines(tmp_path / "trace.jsonl") if t["type"] == "addendum.error"]
    assert len(got) == 3 and all(t["data"]["file"] == str(ctx) for t in got)
    w.close()


# ---- load_validator ----------------------------------------------------------------------------------------------------

@pytest.fixture
def hook_module(tmp_path, monkeypatch):
    (tmp_path / "rec_hook_mod.py").write_text(
        "CALLS = []\n"
        "def check(name, data, mode):\n    CALLS.append((name, data, mode))\n    return ['warned']\n"
        "def rec_boom_import():\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("rec_hook_mod", None)
    yield "rec_hook_mod"
    sys.modules.pop("rec_hook_mod", None)


def test_the_validator_calls_the_named_function_with_the_mode(hook_module):
    validate = load_validator({"SUTRA_RECORDS_HOOK": f"{hook_module}:check"})
    assert validate("goal.json", {"a": 1}) == ["warned"]
    assert sys.modules[hook_module].CALLS == [("goal.json", {"a": 1}, "log")]
    strict = load_validator({"SUTRA_RECORDS_HOOK": f" {hook_module}:check ", "SUTRA_RECORDS": " Strict "})
    strict("x.json", {})
    assert sys.modules[hook_module].CALLS[-1][2] == "strict"


def test_the_default_hook_is_the_librarys_gate_record_when_that_module_exists():
    import importlib.util
    assert hooks.DEFAULT_RECORDS_HOOK == "sutra_app.library.records:gate_record"
    validate = load_validator({})
    assert (validate is None) == (importlib.util.find_spec("sutra_app.library.records") is None)


def test_a_missing_default_hook_module_is_no_validator_not_an_error(monkeypatch):
    monkeypatch.setattr(hooks, "DEFAULT_RECORDS_HOOK", "no_such_pkg_e0.records:gate_record")
    assert load_validator({}) is None
    monkeypatch.setattr(hooks, "DEFAULT_RECORDS_HOOK", "sutra_app.no_such_e0.records:gate_record")
    assert load_validator({}) is None


def test_a_default_hook_module_that_fails_to_import_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "broken_e0_records.py").write_text("import a_module_that_is_not_there_e0\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(hooks, "DEFAULT_RECORDS_HOOK", "broken_e0_records:gate_record")
    with pytest.raises(ImportError, match="broken_e0_records"):
        load_validator({})


def test_a_named_hook_that_cannot_be_imported_is_an_error(hook_module):
    for target in ("no_such_hook_mod_e0:check", f"{hook_module}:missing"):
        with pytest.raises(ImportError, match="SUTRA_RECORDS_HOOK|:"):
            load_validator({"SUTRA_RECORDS_HOOK": target})


@pytest.mark.parametrize("target", ["nocolon", "a.b", ":check", "mod:", "mod:two:colons", "mod: fn", "1mod:fn", "mod:1fn", "a-b:fn"])
def test_a_malformed_hook_name_is_an_error(target):
    with pytest.raises(ValueError, match="package.module:function"):
        load_validator({"SUTRA_RECORDS_HOOK": target})


def test_an_unknown_records_mode_is_an_error(hook_module):
    for mode in ("off", "STRCT", "1"):
        with pytest.raises(ValueError, match="SUTRA_RECORDS"):
            load_validator({"SUTRA_RECORDS_HOOK": f"{hook_module}:check", "SUTRA_RECORDS": mode})
    assert load_validator({"SUTRA_RECORDS_HOOK": f"{hook_module}:check", "SUTRA_RECORDS": ""}) is not None


def test_load_validator_reads_the_process_environment_by_default(hook_module, clean_env):
    clean_env.setenv("SUTRA_RECORDS_HOOK", f"{hook_module}:check")
    clean_env.setenv("SUTRA_RECORDS", "strict")
    load_validator()("a.json", {})
    assert sys.modules[hook_module].CALLS[-1] == ("a.json", {}, "strict")


# ---- the module boundaries ---------------------------------------------------------------------------------------------

def test_events_and_hooks_import_nothing_from_connectors_orchestrator_or_ui():
    import ast
    for module in (events, hooks):
        tree = ast.parse(Path(module.__file__).read_text())
        names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + \
                [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [n for n in names if re.match(r"(sutra_app\.)?(connectors|orchestrator|ui)\b", n)], module.__name__


# ---- against the orchestrator's RunEvent (once ORCH-1 has merged) -----------------------------------------------------

def test_event_types_equal_orchs_and_every_sample_validates_against_run_event():
    models = pytest.importorskip("sutra_app.orchestrator.models", reason="ORCH-1 has not merged yet: test_engine_events_contract.py (E7) then checks this unconditionally")
    from pydantic import TypeAdapter
    assert tuple(models.RUN_EVENT_TYPES) == EVENT_TYPES
    samples = [
        run_started_event(pid=48211, mock=False, seed="none"),
        say_event(id=3, who="identity", text="@Requester What are your opening hours?", to_user=True, act="ASK_REQUESTER", pause="info",
                  questions=[{"question": "What are your opening hours?", "options": []}], next="user"),
        node_event(fn="identity", status="waiting_on_you", detail="Waiting for your answer", calls=1, seconds=6.2, task=TASK,
                   context=[("charter", "none yet")], wait_on="you", tokens={"input": 3100, "output": 240}),
        node_event(step="W-1", status="running"),
        step_event(step="W-2", name="Menu", status="running", parent="box-1", handoff=["W-3"], reads=["W-1"], rework=None),
        atom_event(node="web.identity", atom=ATOM_V1),
        atom_event(node="web.identity", atom=ATOM_V03, outcome="opened"),
        usage_event(**USAGE),
        heartbeat_event(),
        run_ended_event(status="done", outcome="Done: the site is workable."),
        run_ended_event(status="crashed", outcome="could not start: x", code="start_failed"),
    ]
    adapter = TypeAdapter(models.RunEvent)
    for sample in samples:
        adapter.validate_python(sample)
