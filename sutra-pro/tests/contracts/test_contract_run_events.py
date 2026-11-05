"""The run events: the engine's builders, the orchestrator's `RunEvent` union and the Projector agree with Appendix A of S1-contracts-09
(eight types, a closed union on `t`, `at` on every line). Imports both sides unconditionally: a missing module is a failure.

The engine's own E7 test checks every builder and a live run; this module is the other side of the line: the appendix as data, against
both packages, and what the server does with a line it does not know."""
import json
import re

import pytest
from pydantic import TypeAdapter

from sutra_app.engine.events import (
    ATOM_KEYS, EVENT_TYPES, END_STATUSES, atom_event, heartbeat_event, node_event, run_ended_event, run_started_event, say_event, step_event,
    usage_event,
)
from sutra_app.orchestrator.models import RUN_EVENT_TYPES, RUN_EVENT_VARIANTS, EventParseError, RunEvent, parse_event

from .test_contract_world import REPO, clock, db, events, ids, jsonl, settings, tenv  # noqa: F401  (fixtures used by name)
from orchestrator.test_tasks import ev  # noqa: E402  (after the world: its conftest puts tests/library on sys.path)

GOLDEN = REPO / "tests" / "engine" / "golden" / "run_events.jsonl"
AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

# Appendix A, "Fields" column, as data. `node` has `fn` or `step`; the wire name of RunStarted's schema field is `schema`.
APPENDIX_A = {
    "run.started": {"pid", "schema", "mock", "seed"},
    "say": {"id", "who", "text", "to_user", "act", "pause", "questions", "next"},
    "node": {"fn", "step", "status", "detail", "calls", "seconds", "task", "context", "wait_on", "tokens"},
    "step": {"step", "name", "parent", "status", "handoff", "reads", "rework"},
    "atom": {"node", "atom", "outcome", "card", "ledger"},
    "usage": {"fn", "step", "atom", "provider", "model", "purpose", "usd", "tokens_in", "tokens_out", "seconds", "ok", "how", "call_ref", "detail"},
    "heartbeat": set(),
    "run.ended": {"status", "outcome", "code"},
}
ATOM_OBJECT = {"id", "schema", "goal", "work_kind", "verify_template", "status", "attempt", "closed_by", "reason", "body", "ts_open", "ts_closed"}
ATOM = {"id": "a-3f9a1c2b7d-01", "schema": "work-atom/0.3", "goal": "The charter is stamped", "work_kind": "llm", "verify_template": "charter-stamp",
        "status": "open", "attempt": 0, "closed_by": None, "reason": None, "body": {"state": "open"}, "ts_open": 1793748000, "ts_closed": None}
SAMPLES = {
    "run.started": run_started_event(pid=4242, mock=True, seed="none"),
    "say": say_event(id=1, who="identity", text="What is the business called?", to_user=True, act="ASK_REQUESTER", pause="info", next="user"),
    "node": node_event(fn="identity", status="waiting_on_you", detail="waiting", calls=1, seconds=2.5, wait_on="you", tokens={"input": 10, "output": 5}),
    "step": step_event(step="W-1", name="Landing page", status="running", handoff=["W-2"], reads=[]),
    "atom": atom_event(node="web.identity", atom=ATOM, outcome="opened", card={"label": "WORK ATOM OPEN", "goal": "g", "rows": []}),
    "usage": usage_event(fn="identity", step="J2.a", atom=ATOM["id"], provider="claude", model="sonnet", purpose="agent_turn", usd=0.01,
                         tokens_in=10, tokens_out=5, seconds=1.0, ok=True, how="native", call_ref="j2-20261104-100004-7f3a:1", detail=None),
    "heartbeat": heartbeat_event(),
    "run.ended": run_ended_event(status="crashed", outcome="could not start", code="start_failed"),
}


def fields_of(variant) -> set[str]:
    return {info.alias or name for name, info in variant.model_fields.items()} - {"t", "at"}


# ---- the list --------------------------------------------------------------------------------------------------------------------

def test_the_engine_and_the_orchestrator_name_the_same_eight_types_in_the_same_order():
    assert EVENT_TYPES == RUN_EVENT_TYPES == tuple(APPENDIX_A) == tuple(RUN_EVENT_VARIANTS)
    assert len(RUN_EVENT_TYPES) == 8
    assert "session" not in RUN_EVENT_TYPES                                             # removed by S1-contracts-09


@pytest.mark.parametrize("kind", sorted(APPENDIX_A))
def test_each_variant_declares_the_fields_of_the_appendix_and_no_others(kind):
    assert fields_of(RUN_EVENT_VARIANTS[kind]) == APPENDIX_A[kind]


def test_the_atom_object_has_the_appendix_fields_on_both_sides():
    assert set(ATOM_KEYS) == ATOM_OBJECT
    assert fields_of(RUN_EVENT_VARIANTS["atom"].model_fields["atom"].annotation) == ATOM_OBJECT


def test_the_union_is_closed_on_the_type_word():
    adapter = TypeAdapter(RunEvent)
    assert {adapter.validate_python(SAMPLES[kind]).t for kind in SAMPLES} == set(RUN_EVENT_TYPES)
    with pytest.raises(Exception):
        adapter.validate_python({"t": "session", "at": "2026-11-04T10:00:00Z"})


# ---- the builders ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(APPENDIX_A))
def test_a_builder_line_is_read_strictly_by_the_orchestrator_and_every_line_carries_its_time(kind):
    line = SAMPLES[kind]
    assert line["t"] == kind and AT.fullmatch(line["at"])
    assert set(line) - {"t", "at"} <= APPENDIX_A[kind], set(line) - APPENDIX_A[kind]
    parsed = parse_event(json.dumps(line), strict=True)
    assert parsed.t == kind


def test_the_end_statuses_are_the_same_four_words():
    assert END_STATUSES == ("done", "done_with_open_items", "stopped", "crashed")
    for status in END_STATUSES:
        parse_event(run_ended_event(status=status, outcome="x", code="c" if status == "crashed" else None), strict=True)
    with pytest.raises(EventParseError):
        parse_event({"t": "run.ended", "at": "2026-11-04T10:00:00Z", "status": "failed", "outcome": ""}, strict=True)
    with pytest.raises(EventParseError) as refused:
        parse_event({"t": "run.ended", "at": "2026-11-04T10:00:00Z", "status": "done", "outcome": "", "code": "x"}, strict=True)
    assert refused.value.code == "invalid"                                              # only a crash has a code


def test_the_recorded_run_reads_strictly_and_every_line_has_its_time_and_the_last_is_run_ended():
    lines = jsonl(GOLDEN)
    assert len(lines) == 151 and lines[0]["t"] == "run.started" and lines[-1]["t"] == "run.ended"
    assert all(AT.fullmatch(line["at"]) for line in lines)
    assert {line["t"] for line in lines} <= set(RUN_EVENT_TYPES)
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        parse_event(line, strict=True)


# ---- what the server does with a line it does not know -----------------------------------------------------------------------------------

def test_strict_parsing_refuses_an_unknown_field_and_the_server_drops_it_and_says_which():
    line = {**SAMPLES["heartbeat"], "extra": 1}
    with pytest.raises(EventParseError):
        parse_event(line, strict=True)
    dropped: list[str] = []
    assert parse_event(line, strict=False, dropped=dropped).t == "heartbeat" and dropped == ["extra"]


def test_an_unknown_type_is_an_error_to_the_parser_and_a_skipped_line_to_the_projector(tenv):
    with pytest.raises(EventParseError) as refused:
        parse_event({"t": "session", "at": "2026-11-04T10:00:00Z"}, strict=False)
    assert refused.value.code == "unknown_type"
    task = tenv.started()
    tenv.write_events(task, {"t": "session", "id": "x"}, ev("heartbeat", extra=1), ev("run.ended", status="done", outcome="Done."))
    tenv.drain(task)
    assert tenv.status(task) == "done"                                                  # the two odd lines did not stop the run


@pytest.mark.parametrize("status", END_STATUSES)
def test_every_end_status_is_the_status_the_task_ends_with(tenv, status):
    task = tenv.started()
    tenv.write_events(task, ev("run.ended", status=status, outcome="because", **({"code": "start_failed"} if status == "crashed" else {})))
    tenv.drain(task)
    assert tenv.status(task) == status
    assert tenv.row(task).outcome == "because"


def test_run_started_stores_the_pid_and_a_question_makes_the_task_wait_for_the_owner(tenv):
    task = tenv.new().id
    tenv.run(tenv.service.start_ready())
    tenv.write_events(task, ev("run.started", pid=777, schema="events/1", mock=False, seed="none"))
    tenv.drain(task)
    assert tenv.status(task) == "running" and tenv.row(task).pid == 777
    tenv.write_events(task, SAMPLES["say"])
    tenv.drain(task)
    assert tenv.status(task) == "waiting_user"
