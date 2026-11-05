"""Records, wire models, run events and the small foundation modules: errors, ids, redaction, the write guard, Services."""
import inspect
import json
import re

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from starlette.requests import Request

from sutra_app.config import Settings
from sutra_app.engine import events as engine_events
from sutra_app.engine.spec import TASK_SETTING_KEYS, TaskSpec
from sutra_app.library.base import Value, canonical_json
from sutra_app.library.chat import MessageMeta
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY, RegistryError, is_transport_safe
from sutra_app.library.types import Violation
from sutra_app.orchestrator import models
from sutra_app.orchestrator.api import deps
from sutra_app.orchestrator.api.deps import TOKEN_HEADER, Redactor, install_error_handlers, redacted_response_class, require_token
from sutra_app.orchestrator.errors import STATUS_BY_CODE, AlreadyDecided, AppError, Busy, NotFound, ReadOnly, error_body, from_gate_error, rules_error, validation_error
from sutra_app.orchestrator.ids import IdFactory, SystemClock, is_request_id, is_run_id, is_session_id, is_task_id, is_url_id, iso_z, parse_iso_z
from sutra_app.orchestrator.models import RUN_EVENT_TYPES, EventParseError, RunSpec, TaskSettings, parse_event
from sutra_app.orchestrator.records import ChatMessage, ChatSession, UsageRecord, WorkTask
from sutra_app.orchestrator.redact import REDACTED
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.testing import EventCollector, FakeClock, FakeIds

TASK = "tsk_a1b2c3d4e5f6"
RUN = "j2-20261104-100004-7f3a"
SESSION = "cs_5e0a77b19c3d"
TOKEN = "test-token-0123456789abcdef"


def check(family, **fields):
    return GATE.check(family, fields)


def session(**over):
    return {"kind": "department", "id": SESSION, "node_id": "web", "title": "Web", "writable": True, "created_at": 1, "updated_at": 2, **over}


def message(**over):
    return {"kind": "text", "session_id": "cs_org", "role": "agent", "who": "sutra", "text": "Hello", "at": 5, **over}


def usage(**over):
    return {"at": 5, "provider": "claude", "purpose": "chat_plan", **over}


def task(**over):
    return {"id": TASK, "dept_id": "web", "title": "Landing", "user_text": "A site", "status": "queued", "created_at": 1, **over}


# ---- the four records ---------------------------------------------------------------------------------------------

def test_every_record_passes_the_gate_and_round_trips():
    for family, fields in (("chat_session", session()), ("chat_message", message()), ("usage_record", usage()), ("work_task", task())):
        checked = check(family, **fields)
        assert checked.family == family and checked.model.schema_version == 1
        assert GATE.check(family, checked.json).sha256 == checked.sha256               # the stored text reads back to the same record
        assert json.loads(checked.json)["kind"]


def test_the_families_are_registered_with_their_kinds():
    assert sorted(REGISTRY.kinds("chat_session")) == ["department", "division", "function", "org", "step"]
    assert sorted(REGISTRY.kinds("chat_message")) == ["card", "error", "note", "question", "text"]
    assert list(REGISTRY.kinds("usage_record")) == ["usage_record"] and list(REGISTRY.kinds("work_task")) == ["work_task"]


def test_records_are_closed_and_frozen():
    for family, fields in (("chat_session", session()), ("chat_message", message()), ("usage_record", usage()), ("work_task", task())):
        with pytest.raises(GateError) as err:
            check(family, **fields, surprise=1)
        assert err.value.stage == "shape"
    rec = check("work_task", **task()).model
    with pytest.raises(ValidationError):
        rec.title = "x"
    assert rec.evolve(status="stopped", ended_at=3).status == "stopped"
    with pytest.raises(ValidationError):
        rec.evolve(status="running")                                                  # live without a run id


def test_strict_types_no_coercion():
    with pytest.raises(GateError):
        check("usage_record", **usage(tokens_in="12"))
    with pytest.raises(GateError):
        check("chat_session", **session(writable=1))


def bad(family, fragment, **fields):
    with pytest.raises(GateError) as err:
        GATE.check(family, fields)
    assert fragment in " ".join(v.message for v in err.value.violations), err.value.violations


def test_chat_session_rules():
    check("chat_session", **session(kind="org", id="cs_org", node_id="root"))
    check("chat_session", **session(kind="function", node_id="web.identity", writable=False))
    check("chat_session", **session(kind="division", node_id="menu", status="archived", writable=False, filed_under="recipes", connector="claude"))
    bad("chat_session", "only the org chat", **session(kind="org", node_id="root"))                            # org but not cs_org
    bad("chat_session", "only the org chat", **session(id="cs_org"))                                           # cs_org but not org
    bad("chat_session", "root node", **session(kind="org", id="cs_org", node_id="web"))
    bad("chat_session", "read-only", **session(kind="step", node_id="s-1111111111"))
    bad("chat_session", "not writable", **session(status="archived"))
    bad("chat_session", "only an archived", **session(filed_under="recipes"))
    bad("chat_session", "before created_at", **session(created_at=9, updated_at=8))
    check("chat_session", **session(created_at=9, updated_at=9))
    bad("chat_session", "", **session(id="cs_nothex"))
    bad("chat_session", "", **session(connector="gemini"))


def test_chat_message_rules():
    card = {"type": "task", "task_id": TASK, "dept_id": "web", "dept_name": "Web", "title": "T", "status": "running"}
    ok = check("chat_message", **message(kind="card", text="", card=card, task_id=TASK)).model
    assert ok.card == card and ok.meta == MessageMeta()
    bad("chat_message", "carries a card", **message(kind="card", text=""))
    bad("chat_message", "no text", **message(kind="card", card=card))
    bad("chat_message", "not a known card", **message(kind="card", text="", card={"type": "sticker"}))
    bad("chat_message", "not a known card", **message(kind="card", text="", card={**card, "extra": 1}))
    bad("chat_message", "only a card message", **message(card=card))
    bad("chat_message", "carries text", **message(text=""))
    bad("chat_message", "exactly when its role is user", **message(role="user"))
    bad("chat_message", "exactly when its role is user", **message(who="user"))
    check("chat_message", **message(role="user", who="user", state="pending"))
    check("chat_message", **message(kind="question", who="identity", pause="ASK", answered_by=7))
    bad("chat_message", "only a question is answered", **message(answered_by=7))
    bad("chat_message", "asked by an agent", **message(kind="question", role="system", who="sutra"))


def test_chat_message_meta_is_the_library_meta():
    stored = check("chat_message", **message(meta={"act": "ASK_REQUESTER", "options_only": True, "gaps": [1, {"a": 2}]})).model
    assert isinstance(stored.meta, MessageMeta) and stored.meta.act == "ASK_REQUESTER"
    assert json.loads(canonical_json(stored))["meta"] == {"act": "ASK_REQUESTER", "gaps": [1, {"a": 2}], "options_only": True}   # unset keys left out
    bad("chat_message", "", **message(meta={"not_a_j2_key": 1}))


def test_usage_record_bounds():
    full = check("usage_record", **usage(session_id="cs_org", node_id="web.identity", task_id=TASK, dept_id="web", fn="identity", step="W-1",
                                           atom_id=f"{RUN}:W-1.a1", usd=0.0, tokens_in=0, tokens_out=3, seconds=1.5, how="native",
                                           call_ref=f"{RUN}:4", detail={"cache": {"read": 1}})).model
    assert full.atom_id.endswith("W-1.a1")
    for field, value in (("usd", -0.1), ("tokens_in", -1), ("seconds", -1.0), ("provider", "gpt"), ("purpose", ""), ("call_ref", "")):
        with pytest.raises(GateError):
            check("usage_record", **usage(**{field: value}))


def test_work_task_rules():
    run = check("work_task", **task(status="running", run_id=RUN, pid=77, events_offset=120, started_at=2, settings={"J2_OUTPUT": "prd", "J2_BUDGET": "50"},
                                    request_id="req-3", change_id="chg-0002", depends_on=["tsk_ffffffffffff"])).model
    assert run.settings.J2_OUTPUT == "prd"
    check("work_task", **task(status="cancelled", ended_at=4, outcome="waiting task X did not finish"))
    bad("work_task", "has a run id", **task(status="starting"))
    bad("work_task", "has an end time", **task(status="done"))
    bad("work_task", "has not ended", **task(ended_at=3))
    bad("work_task", "own parent", **task(parent_task_id=TASK))
    bad("work_task", "own parent", **task(depends_on=[TASK]))
    bad("work_task", "twice", **task(depends_on=["tsk_ffffffffffff", "tsk_ffffffffffff"]))
    bad("work_task", "before created_at", **task(started_at=0))
    bad("work_task", "before the task started", **task(status="stopped", started_at=5, ended_at=3))
    bad("work_task", "", **task(dept_id="Web"))
    bad("work_task", "", **task(status="archived"))


def test_task_settings_are_the_engines_seven_keys_and_nothing_else():
    assert tuple(TaskSettings.model_fields) == TASK_SETTING_KEYS
    ok = TaskSettings.model_validate({"J2_BUDGET": "100000", "J2_FIXES": "1", "J2_OUTPUT": "lld"})
    assert ok.model_dump() == {"J2_OUTPUT": "lld", "J2_BUDGET": "100000", "J2_FIXES": "1"}            # unset keys are left out
    for bad_value in ({"J2_SEND_MODE": "live"}, {"J2_OUTPUT": "pdf"}, {"J2_BUDGET": "0"}, {"J2_BUDGET": "100001"}, {"J2_BUDGET": "abc"},
                      {"J2_BUDGET": "007"}, {"J2_BUDGET_CAP": "1.5"}, {"J2_FIXES": "2"}, {"J2_MEMORY": True}, {"J2_BUDGET": 5}):
        with pytest.raises(ValidationError):
            TaskSettings.model_validate(bad_value)


# ---- wire models ----------------------------------------------------------------------------------------------------

def test_every_class_in_models_derives_from_value():
    classes = [c for _, c in inspect.getmembers(models, inspect.isclass) if issubclass(c, BaseModel) and c.__module__ == models.__name__]
    assert len(classes) > 40
    assert [c.__name__ for c in classes if not issubclass(c, Value)] == []


GRAPH = {"version": 42, "chart_version": 2, "nodes": [
    {"id": "root", "kind": "root", "label": "Root", "status": "running", "detail": "", "chat_session_id": "cs_org", "org_node_id": "root", "dept_id": None,
     "task_id": None, "fn": None, "step_ref": None, "version": 3, "meta": {}},
    {"id": "web.identity", "kind": "function", "label": "Identity", "status": "waiting_on_you", "detail": "asked about the menu",
     "chat_session_id": "cs_77aa10c2e9b4", "org_node_id": None, "dept_id": "web", "task_id": None, "fn": "identity", "step_ref": None, "version": 4,
     "meta": {"stats": {"calls": 12, "seconds": 41.0, "tokens_in": 7000, "tokens_out": 2120, "atoms_open": 1, "atoms_closed": 5, "atoms_failed": 1,
                        "atoms_total": 8}, "wait_on": "you"}},
    {"id": "s-3f9a1c2b7d", "kind": "step", "label": "Coffee shop landing page", "status": "running", "detail": "", "chat_session_id": "cs_0c91d4aa3e77",
     "org_node_id": None, "dept_id": "web", "task_id": TASK, "fn": None, "step_ref": "task", "version": 2, "meta": {"run_id": RUN}}],
    "edges": [{"src": "root", "dst": "web", "kind": "contains", "label": ""}, {"src": "web", "dst": "web.identity", "kind": "has_function", "label": ""}]}
MESSAGES = [
    {"id": 1, "session_id": "cs_org", "role": "agent", "who": "sutra", "kind": "text", "text": "Hello.", "card": None, "pause": None, "answered_by": None,
     "task_id": None, "state": "ok", "at": "2026-11-04T10:00:00Z"},
    {"id": 4, "session_id": "cs_org", "role": "agent", "who": "sutra", "kind": "card", "text": "", "card": {"type": "task", "task_id": TASK, "dept_id": "web",
     "dept_name": "Web", "title": "Coffee shop landing page", "status": "running"}, "pause": None, "answered_by": None, "task_id": TASK, "state": "ok",
     "at": "2026-11-04T10:00:03Z"},
    {"id": 13, "session_id": "cs_77aa10c2e9b4", "role": "agent", "who": "sutra", "kind": "card", "text": "", "card": {"type": "atom", "atom_id": "a-77aa10c2e9-03",
     "outcome": "verify_failed", "label": "VERIFY FAILED", "goal": "the brief becomes a charter", "rows": [{"label": "Result", "text": "attempt 2 of 3"}]},
     "pause": None, "answered_by": None, "task_id": TASK, "state": "ok", "at": "2026-11-04T10:01:12Z"}]
CHANGE = {"seq": 2, "id": "chg-0002", "at": "2026-11-04T10:00:03Z", "actor": "chat_agent", "decision": "add", "status": "applied", "summary": "Added the Web team",
          "reason": "No team makes websites", "task_id": "req-17", "task_title": "Coffee shop landing page", "revision": 2, "added": ["web"], "moved": [],
          "archived": [], "reused": []}


def test_the_ui_contract_examples_validate_and_round_trip():
    view = models.GraphView.model_validate(GRAPH)
    assert view.model_dump(mode="json") == GRAPH
    assert models.FnMeta.model_validate(GRAPH["nodes"][1]["meta"]).model_dump(mode="json") == GRAPH["nodes"][1]["meta"]
    assert models.ChartChangeOut.model_validate(CHANGE).model_dump(mode="json") == CHANGE
    chart = {"version": 2, "nodes": [{"id": "root", "kind": "root", "name": "Root", "purpose": "", "parent_id": None, "position": 0},
                                     {"id": "web", "kind": "department", "name": "Web", "purpose": "Websites", "parent_id": "root", "position": 0}]}
    assert models.ChartView.model_validate(chart).model_dump(mode="json") == chart
    for item in MESSAGES:
        assert models.ChatMessageOut.model_validate(item).model_dump(mode="json") == item
    assert isinstance(models.ChatMessageOut.model_validate(MESSAGES[2]).card, models.AtomCard)


def test_function_node_meta_has_exactly_the_documented_keys():
    detail = {"goal": "g", "task": "J2.a charter", "context": ["the charter"], "constraints": ["invent a goal"], "wait_on": "you",
              "hands_to": ["adaptation", "audit"], "stats": GRAPH["nodes"][1]["meta"]["stats"]}
    assert list(models.FnDetailMeta.model_validate(detail).model_dump(mode="json")) == ["goal", "task", "context", "constraints", "wait_on", "hands_to", "stats"]
    assert list(models.FnMeta.model_fields) == ["stats", "wait_on"] and "last_seen" not in models.FnStats.model_fields
    with pytest.raises(ValidationError):
        models.FnMeta.model_validate({"stats": {}, "wait_on": None, "goal": "x"})


def test_node_detail_and_atom_out_use_the_wire_key_schema():
    atom = {"id": f"{RUN}:W-3.a1", "schema": "atom/1", "node_id": "s-3f9a1c2b7d", "task_id": TASK, "state": "verify_failed", "goal": "g", "attempt": 3,
            "ts_open": "2026-11-04T10:00:40Z", "ts_closed": None, "body": {"k": 1}, "usage": {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}}
    out = models.AtomOut.model_validate(atom)
    assert out.model_dump(mode="json") == atom and out.schema_ == "atom/1"
    detail = models.NodeDetail.model_validate({"node": GRAPH["nodes"][2], "session": None, "atoms": [atom], "task": None})
    assert detail.archived_chats == [] and detail.usage_total.calls == 0
    with pytest.raises(ValidationError):
        models.AtomOut.model_validate({**atom, "state": "failed"})                    # only the five display words
    row = models.AtomLogRow(seq=1, atom_id="a-77aa10c2e9-03", node_id="web.identity", status="verify_failed", body={}, ts="2026-11-04T10:00:00Z")
    assert row.status == "verify_failed"
    with pytest.raises(ValidationError):
        models.AtomLogRow(seq=1, atom_id="a", node_id="web.identity", status="open", body={}, ts="2026-11-04T10:00:00Z")


def test_chat_post_and_answers():
    assert models.ChatPost(text="  hi  ", choice=None).text == "hi"
    for text in ("", "   ", "x" * 8001):
        with pytest.raises(ValidationError):
            models.ChatPost(text=text)
    assert models.ChatPost(text="x" * 8000).text and models.ChatPost.model_validate({"text": "Yes", "choice": {"message_id": 3, "option": "approve"}})
    assert models.Accepted(message_id=1, turn="queued").turn == "queued"
    with pytest.raises(ValidationError):
        models.Delivery(message_id=1, delivered="queued", task_id=TASK)


def test_dept_row_and_helpers():
    row = models.DeptRow(id="web", name="Web")
    assert (row.archived, row.merged_into_name) == (False, "")
    assert models.ChangeContext(session_id="cs_org", request_id="req-3").request_title == ""
    assert models.NodeInit(node={"id": "web"}, session_title="Web").session_id is None
    assert models.ResumeInfo().messages == []
    assert models.Event(seq=0, at="2026-11-04T10:00:00Z", type="graph.updated", data={"version": 1}).seq == 0


# ---- the run events -----------------------------------------------------------------------------------------------

AT = "2026-11-04T10:00:06Z"
ATOM_BODY = {"id": "a-77aa10c2e9-01", "schema": "work-atom/0.3", "goal": "the brief becomes a charter", "work_kind": "llm", "verify_template": "charter-stamp",
             "status": "open", "attempt": 1, "closed_by": None, "reason": None, "body": {"work": {}}, "ts_open": 100, "ts_closed": None}
ENGINE_EVENTS = [
    engine_events.run_started_event(pid=4242, mock=False, seed="fresh", at=AT),
    engine_events.say_event(id=3, who="identity", text="What is the menu?", to_user=True, act="ASK_REQUESTER", pause="ASK", questions=[{"q": "x"}], next="adaptation", at=AT),
    engine_events.say_event(id=4, who="team:Product Analyst", text="hi", at=AT),
    engine_events.node_event(fn="identity", status="waiting_on_you", detail="asked", calls=3, seconds=1.5, wait_on="you", tokens={"input": 10, "output": 5},
                             task={"id": "t-1", "kind": "intake", "summary": "s", "state": "running", "set_by": "x"}, context=[("brief", "A site")], at=AT),
    engine_events.node_event(step="W-3", status="done_unchecked", at=AT),
    engine_events.step_event(step="W-3", name="Write copy", status="running", parent="task", handoff=["W-4"], reads=["W-2"], rework="W-1", at=AT),
    engine_events.atom_event(node="web.identity", atom=ATOM_BODY, outcome="opened", card={"title": "x"}, ledger=None, at=AT),
    engine_events.atom_event(node="s-1", atom={**ATOM_BODY, "id": "W-1.a1", "schema": "atom/1", "status": "verify_failed", "attempt": 2}, at=AT),
    engine_events.usage_event(fn="identity", step=None, atom="a-77aa10c2e9-01", provider="claude", model="sonnet", purpose="turn", usd=0.01, tokens_in=10,
                              tokens_out=2, seconds=1.0, ok=True, how="native", call_ref=f"{RUN}:1", detail={"cache": 1}, at=AT),
    engine_events.heartbeat_event(at=AT),
    engine_events.run_ended_event(status="crashed", outcome="boom", code="internal", at=AT),
    engine_events.run_ended_event(status="done", outcome="shipped", at=AT),
]


def test_run_event_types_are_the_engines_eight():
    assert RUN_EVENT_TYPES == engine_events.EVENT_TYPES and set(models.RUN_EVENT_VARIANTS) == set(RUN_EVENT_TYPES)
    assert {e["t"] for e in ENGINE_EVENTS} == set(RUN_EVENT_TYPES)


@pytest.mark.parametrize("event", ENGINE_EVENTS, ids=lambda e: e["t"] + ":" + str(e.get("who") or e.get("fn") or e.get("step") or e.get("status") or ""))
def test_every_event_the_engine_builds_parses_strictly(event):
    line = engine_events.encode_line(event)
    parsed = parse_event(line, strict=True)
    assert parsed.t == event["t"] and parsed.at == AT
    assert parse_event(line.decode(), strict=True) == parse_event(event, strict=True) == parsed          # bytes, text and a dict agree
    assert json.loads(parsed.model_dump_json(by_alias=True, exclude_none=True))["t"] == event["t"]


def test_the_node_event_takes_wait_on_and_tokens_and_has_no_goal():
    node = parse_event(ENGINE_EVENTS[3], strict=True)
    assert node.wait_on == "you" and (node.tokens.input, node.tokens.output) == (10, 5) and not hasattr(node, "goal")
    with pytest.raises(EventParseError) as err:
        parse_event({**ENGINE_EVENTS[3], "goal": "Keep the department aligned"}, strict=True)
    assert err.value.code == "invalid" and err.value.violations[0].path == "goal"
    noted = []
    assert parse_event({**ENGINE_EVENTS[3], "goal": "x"}, dropped=noted).fn == "identity" and noted == ["goal"]


def test_undeclared_keys_are_dropped_and_noted_when_not_strict():
    noted = []
    event = parse_event({**ENGINE_EVENTS[6], "future": 1, "atom": {**ENGINE_EVENTS[6]["atom"], "extra": 2}}, dropped=noted)
    assert event.atom.id == "a-77aa10c2e9-01" and sorted(noted) == ["atom.extra", "future"]
    event = parse_event({**ENGINE_EVENTS[3], "tokens": {"input": 1, "output": 2, "cached": 3}, "task": None})
    assert event.tokens.output == 2
    with pytest.raises(EventParseError):
        parse_event({**ENGINE_EVENTS[6], "future": 1}, strict=True)
    with pytest.raises(EventParseError):
        parse_event({**ENGINE_EVENTS[6], "atom": {**ENGINE_EVENTS[6]["atom"], "extra": 2}}, strict=True)


@pytest.mark.parametrize("line,code", [("{not json", "not_json"), (b"\xff\xfe", "not_json"), ("[1]", "not_object"), ("3", "not_object"),
                                       ('{"t":"session","at":"%s"}' % AT, "unknown_type"), ('{"at":"%s"}' % AT, "unknown_type"),
                                       ('{"t":["say"]}', "unknown_type"), ('{"t":"heartbeat"}', "invalid"), ('{"t":"heartbeat","at":"yesterday"}', "invalid")])
def test_bad_lines(line, code):
    with pytest.raises(EventParseError) as err:
        parse_event(line)
    assert err.value.code == code
    assert err.value.t in (None, "session", "heartbeat")


def test_event_shape_rules():
    node = ENGINE_EVENTS[3]
    for broken in ({**node, "step": "W-1"}, {k: v for k, v in node.items() if k != "fn"}, {**node, "status": "filed"}, {**node, "fn": "sales"}):
        with pytest.raises(EventParseError):
            parse_event(broken)
    with pytest.raises(EventParseError):
        parse_event({**ENGINE_EVENTS[0], "pid": 0})
    with pytest.raises(EventParseError):
        parse_event({**ENGINE_EVENTS[1], "who": "user"})                                      # the owner's lines are never events
    atom = ENGINE_EVENTS[6]
    for broken in ({**atom, "atom": {**atom["atom"], "status": "verify_failed"}},                 # not a work-atom word
                   {**atom, "atom": {**atom["atom"], "attempt": 4}}, {**atom, "atom": {**atom["atom"], "schema": "atom/2"}}):
        with pytest.raises(EventParseError):
            parse_event(broken)
    view = ENGINE_EVENTS[7]
    with pytest.raises(EventParseError) as err:
        parse_event({**view, "outcome": "closed"})
    assert "work-atom/0.3 only" in err.value.violations[0].message
    with pytest.raises(EventParseError):
        parse_event({**view, "atom": {**view["atom"], "status": "refused"}})
    with pytest.raises(EventParseError):
        parse_event({**ENGINE_EVENTS[-1], "code": "internal"})                                 # only a crash has a code


def test_run_spec_is_what_the_engine_reads():
    spec = RunSpec(run_id=RUN, task_id=TASK, dept_id="web", dept_label="Web", user_text="A site for my cafe", settings=TaskSettings(J2_OUTPUT="prd", J2_RATES="0"),
                   upstream=[{"dept_id": "content", "run_id": "j2-20261103-090000-aaaa", "title": "Copy", "files": ["site/index.html"]}], scope_id="menu",
                   scope_label="Menu", connector="stub", seed_from="j2-20261103-090000-bbbb")
    document = json.loads(spec.canonical_json())
    assert document["schema"] == "run-spec/1" and document["settings"] == {"J2_OUTPUT": "prd", "J2_RATES": "0"}
    read = TaskSpec.model_validate(document)
    assert (read.run_id, read.task_id, read.user_text, read.settings, read.connector) == (RUN, TASK, "A site for my cafe", {"J2_OUTPUT": "prd", "J2_RATES": "0"}, "stub")
    assert set(RunSpec.model_fields) - {"schema_"} <= set(TaskSpec.model_fields)                # every field exists in the reader
    assert TaskSpec.model_validate(json.loads(RunSpec(run_id=RUN, task_id=TASK, dept_id="web", dept_label="Web", user_text="x").canonical_json())).settings == {}
    with pytest.raises(ValidationError):
        RunSpec(run_id="not-a-run", task_id=TASK, dept_id="web", dept_label="Web", user_text="x")
    with pytest.raises(ValidationError):
        RunSpec(run_id=RUN, task_id=TASK, dept_id="web", dept_label="Web", user_text="x", settings={"J2_SEND_MODE": "live"})


# ---- errors ---------------------------------------------------------------------------------------------------------

def test_error_codes_and_statuses_are_the_designs():
    assert STATUS_BY_CODE == {"bad_token": 401, "bad_host": 400, "bad_origin": 403, "validation": 422, "rules": 422, "not_found": 404, "busy": 409,
                              "stale_chart": 409, "already_decided": 409, "read_only": 403, "too_many_pending": 429, "provider_unavailable": 503,
                              "cli_missing": 503, "store_busy": 503, "internal": 500}
    err = AppError("busy", "later", {"task": 1})
    assert (err.status, err.code, err.body()) == (409, "busy", {"error": {"code": "busy", "message": "later", "details": {"task": 1}}})
    with pytest.raises(ValueError, match="unknown error code"):
        AppError("oops", "x")
    assert (NotFound("the chat").status, ReadOnly().code, Busy().status) == (404, "read_only", 409) and "the chat" in NotFound("the chat").message
    assert AlreadyDecided({"id": "chg-0001"}).result == {"id": "chg-0001"}
    assert error_body("internal", "m") == {"error": {"code": "internal", "message": "m", "details": {}}}


def test_gate_and_rule_violations_become_422():
    with pytest.raises(GateError) as gate:
        check("usage_record", provider="gpt", at=1, purpose="p")
    err = from_gate_error(gate.value)
    assert (err.status, err.code) == (422, "validation") and err.details["violations"][0]["path"] == "provider"
    found = rules_error([Violation(path="ops.0", code="busy", message="Web is busy")])
    assert (found.status, found.code, found.details["violations"][0]["code"]) == (422, "rules", "busy")
    assert validation_error([]).details == {"violations": []}


# ---- ids and time -----------------------------------------------------------------------------------------------------

def test_id_formats():
    ids = IdFactory(FakeClock())
    assert is_task_id(ids.task_id()) and is_session_id(ids.session_id()) and is_run_id(ids.run_id())
    assert re.fullmatch(r"j2-20261104-1000\d\d-[0-9a-f]{4}", ids.run_id())                       # the fake clock starts at 10:00:00 UTC
    assert ids.request_id(17) == "req-17" and is_request_id("req-17") and ids.change_id(2) == "chg-0002" and ids.change_id(12345) == "chg-12345"
    for bad_value in (0, -1, True, "3"):
        with pytest.raises(ValueError):
            IdFactory.request_id(bad_value)
        with pytest.raises(ValueError):
            IdFactory.change_id(bad_value)
    assert is_session_id("cs_org") and not is_session_id("cs_ORG") and not is_task_id("tsk_123") and not is_run_id("run-1") and not is_task_id("tsk_a1b2c3d4e5f6\n")
    assert is_url_id("web.identity") and is_url_id("j2-1:W-3.a1") and not is_url_id("a/b") and not is_url_id("") and not is_url_id("x" * 121)
    assert len(IdFactory(SystemClock()).task_id()) == 16 and IdFactory().task_id() != IdFactory().task_id()


def test_fake_ids_and_clock_are_deterministic():
    one, two = FakeIds(FakeClock()), FakeIds(FakeClock())
    assert [one.task_id(), one.session_id(), one.run_id()] == [two.task_id(), two.session_id(), two.run_id()]
    assert one.task_id() == "tsk_000000000004" and one.session_id() == "cs_000000000005"
    clock = FakeClock(start=100, step=5)
    assert (clock.now(), clock.now(), clock.time(), clock.peek) == (100, 105, 110.0, 115)
    clock.advance(10)
    assert clock.now() == 125


def test_iso_z_round_trips():
    assert iso_z(1793786406) == "2026-11-04T10:00:06Z" and parse_iso_z("2026-11-04T10:00:06Z") == 1793786406 and iso_z(0.9) == "1970-01-01T00:00:00Z"
    for text in ("2026-11-04", "2026-11-04T10:00:06+00:00", None):
        with pytest.raises(ValueError):
            parse_iso_z(text)


# ---- redaction ----------------------------------------------------------------------------------------------------------

def test_redaction_rules(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PLAIN_NAME=envfile-value-123\nSHORT=tiny\n", encoding="utf-8")
    environ = {"MY_API_KEY": "key-abcdefgh", "GITHUB_TOKEN": "tok-12345678", "DB_PASSWORD": "pass-1234567", "CLIENT_SECRET": "sec-12345678",
               "SSH_AUTH_SOCK": "/tmp/agent.sock", "TOO_SHORT_KEY": "short", "HOME": "/Users/someone/home", "KEYBOARD_X": "kb-12345678"}
    redactor = Redactor(env_file, environ=environ)
    text = "k=key-abcdefgh t=tok-12345678 p=pass-1234567 s=sec-12345678 a=/tmp/agent.sock f=envfile-value-123 short=short tiny=tiny home=/Users/someone/home"
    out = redactor(text)
    assert out == "k=[redacted] t=[redacted] p=[redacted] s=[redacted] a=[redacted] f=[redacted] short=short tiny=tiny home=/Users/someone/home"
    assert REDACTED == "[redacted]" and redactor("kb-12345678") == "[redacted]"                        # KEY inside a name counts, as in J2
    assert redactor(5) == 5


def test_longest_secret_goes_first_and_extras_ignore_the_minimum_length():
    redactor = Redactor(None, environ={"A_KEY": "abcdefgh", "B_KEY": "abcdefghijkl"}, extra=["tk", lambda: "dyn", lambda: None, ""])
    assert redactor("abcdefghijkl and abcdefgh and tk and dyn") == "[redacted] and [redacted] and [redacted] and [redacted]"
    assert redactor.secrets()[0] == "abcdefghijkl"


def test_the_env_file_is_reread_when_it_changes(tmp_path):
    env_file = tmp_path / ".env"
    redactor = Redactor(env_file, environ={})
    assert redactor("value-one-1234") == "value-one-1234"                                                  # no file yet
    env_file.write_text("A=value-one-1234\n")
    assert redactor("value-one-1234") == "[redacted]"
    env_file.write_text("A=value-two-12345\n")
    assert redactor("value-one-1234 value-two-12345") == "value-one-1234 [redacted]"
    env_file.unlink()
    assert redactor("value-two-12345") == "value-two-12345"


def test_scrub_finds_secrets_json_would_escape():
    redactor = Redactor(None, environ={"X_TOKEN": 'qu"ote\\slash-é-1234'})
    body = {"msg": 'has qu"ote\\slash-é-1234 inside', "list": ["qu\"ote\\slash-é-1234", 3, None], 'qu"ote\\slash-é-1234': "k", "nested": {"a": ("t", True)}}
    scrubbed = redactor.scrub(body)
    assert "slash" not in json.dumps(scrubbed) and scrubbed["msg"] == "has [redacted] inside" and scrubbed["list"] == ["[redacted]", 3, None]
    assert scrubbed["nested"] == {"a": ["t", True]} and "[redacted]" in scrubbed
    clean = {"a": 1}
    assert Redactor(None, environ={}).scrub(clean) is clean


# ---- the write guard and the error envelope ---------------------------------------------------------------------------

@pytest.fixture
def app(settings):
    app = FastAPI(default_response_class=redacted_response_class(Redactor(None, environ={"X_API_KEY": "leaky-secret-0001"}, extra=[settings.token])))
    app.state.services = Services(settings=settings, version="t", db=None, redact=lambda t: t)
    install_error_handlers(app, app.router.default_response_class)

    @app.get("/read")
    def read():
        return {"ok": True, "echo": "leaky-secret-0001"}

    @app.post("/write", dependencies=[Depends(require_token)])
    def write():
        return {"ok": True}

    @app.put("/put", dependencies=[Depends(app.state.services.require_token)])
    def put(body: models.ChatPost):
        return {"text": body.text}

    @app.post("/boom", dependencies=[Depends(require_token)])
    def boom():
        raise RuntimeError("secret detail leaky-secret-0001")

    @app.get("/typed")
    def typed():
        raise Busy()

    return app


@pytest.fixture
def client(app):
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


def code_of(response):
    return response.json()["error"]["code"]


def test_reads_need_no_token_and_responses_are_redacted(client):
    r = client.get("/read")
    assert r.status_code == 200 and r.json() == {"ok": True, "echo": "[redacted]"}


def test_a_write_needs_the_token_in_the_header(client):
    assert (lambda r: (r.status_code, code_of(r)))(client.post("/write")) == (401, "bad_token")
    assert client.post("/write", headers={TOKEN_HEADER: "wrong-token-0123456789"}).status_code == 401
    assert client.post("/write", headers={TOKEN_HEADER: TOKEN[:-1]}).status_code == 401
    assert client.post("/write", headers={TOKEN_HEADER: TOKEN}).json() == {"ok": True}
    assert client.post("/write", headers={TOKEN_HEADER.lower(): TOKEN}).status_code == 200            # header names are case-insensitive
    assert client.post("/write", headers={TOKEN_HEADER: ("é" * 20).encode("utf-8")}).status_code == 401                 # non-ASCII is a plain mismatch, not a crash


def test_the_token_in_a_cookie_query_or_body_is_not_accepted(client):
    client.cookies.set("X-Sutra-Token", TOKEN)
    assert client.post("/write").status_code == 401
    assert client.post(f"/write?token={TOKEN}").status_code == 401
    assert client.post("/write", json={"token": TOKEN}).status_code == 401


def test_two_token_headers_are_refused(client):
    assert client.post("/write", headers=[(TOKEN_HEADER, TOKEN), (TOKEN_HEADER, TOKEN)]).status_code == 401


def test_origin_must_be_this_app_when_present(client):
    ok = {TOKEN_HEADER: TOKEN}
    assert client.post("/write", headers={**ok, "Origin": "http://127.0.0.1:8780"}).status_code == 200
    assert client.post("/write", headers=ok).status_code == 200                                      # absent is allowed
    for origin in ("http://evil.example", "null", "https://127.0.0.1:8780", "http://127.0.0.1:8781", "http://localhost:8780", ""):
        r = client.post("/write", headers={**ok, "Origin": origin})
        assert (r.status_code, code_of(r)) == (403, "bad_origin"), origin
    assert client.post("/write", headers=[(TOKEN_HEADER, TOKEN), ("Origin", "http://127.0.0.1:8780"), ("Origin", "http://127.0.0.1:8780")]).status_code == 403
    assert client.post("/write", headers={"Origin": "http://evil.example"}).status_code == 401       # the token is checked first


def test_the_guard_reads_the_token_of_the_apps_services_and_fails_closed(client, app):
    app.state.services = None
    r = client.post("/write", headers={TOKEN_HEADER: TOKEN})
    assert (r.status_code, code_of(r)) == (500, "internal")
    assert client.get("/read").status_code == 200                                                    # a read needs no services


def test_safe_methods_pass_the_dependency_alone():
    from starlette.requests import Request as R
    import anyio
    for method in ("GET", "HEAD", "OPTIONS"):
        scope = {"type": "http", "method": method, "headers": [], "app": FastAPI()}
        assert anyio.run(require_token, R(scope)) is None


def test_error_envelope_for_app_validation_and_unexpected_errors(client):
    r = client.get("/typed")
    assert (r.status_code, r.json()["error"]["code"], r.json()["error"]["details"]) == (409, "busy", {})
    bad = client.put("/put", json={"text": ""}, headers={TOKEN_HEADER: TOKEN})
    assert bad.status_code == 422 and code_of(bad) == "validation"
    violations = bad.json()["error"]["details"]["violations"]
    assert violations[0]["path"] == "body.text" and set(violations[0]) == {"path", "code", "message"}
    assert client.put("/put", json={"text": "hi"}, headers={TOKEN_HEADER: TOKEN}).json() == {"text": "hi"}
    boom = client.post("/boom", headers={TOKEN_HEADER: TOKEN})
    assert (boom.status_code, code_of(boom)) == (500, "internal") and "leaky" not in boom.text and "RuntimeError" not in boom.text


def test_a_locked_database_escaping_a_route_is_store_busy():
    import sqlite3
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/locked")
    def locked():
        raise sqlite3.OperationalError("database is locked")

    @app.get("/broken")
    def broken():
        raise sqlite3.OperationalError("no such table: x")

    c = TestClient(app, raise_server_exceptions=False)
    assert (c.get("/locked").status_code, code_of(c.get("/locked"))) == (503, "store_busy")
    assert (c.get("/broken").status_code, code_of(c.get("/broken"))) == (500, "internal")


def test_the_default_response_class_redacts_the_environment(monkeypatch):
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "env-token-value-99")
    response = deps.RedactedJSONResponse({"x": "env-token-value-99"})
    assert json.loads(response.body) == {"x": "[redacted]"}


def test_route_guard_is_the_service_dependency(settings):
    services = Services(settings=settings, version="t", db=None, redact=str)
    assert services.require_token is require_token and inspect.iscoroutinefunction(require_token)
    assert inspect.signature(require_token).parameters["request"].annotation is Request


# ---- Services ----------------------------------------------------------------------------------------------------------

def test_services_slots(settings):
    services = Services(settings=settings, version="1", db=None, redact=lambda t: t, clock=FakeClock())
    assert services.data_dir == settings.data_dir and isinstance(services.ids, IdFactory)
    assert services.missing() == ["bus", "chats", "atoms", "usage", "graph", "chart", "departments", "tasks", "projector", "watcher", "runner",
                                  "connector", "launcher", "resolve_run", "department", "deliver_to_department", "stop_live"]
    with pytest.raises(RuntimeError, match="Services.chart is not wired"):
        services.need("chart")
    services.chart = object()
    services.department = lambda dept_id: models.DeptRow(id=dept_id, name=dept_id.title())
    assert "chart" not in services.missing() and "department" not in services.missing()
    assert services.need("chart") is services.chart and services.department("web").name == "Web"
    with pytest.raises(KeyError):
        services.need("settings_typo")


def test_event_collector_groups_commits():
    seen = EventCollector()
    seen([models.Event(seq=0, at="2026-11-04T10:00:00Z", type="a.b", data={})])
    seen([models.Event(seq=0, at="2026-11-04T10:00:00Z", type="c.d", data={}), models.Event(seq=0, at="2026-11-04T10:00:00Z", type="e.f", data={})])
    assert seen.types() == ["a.b", "c.d", "e.f"] and [len(b) for b in seen.batches] == [1, 2]


# ---- transport safety -----------------------------------------------------------------------------------------------

def test_stored_records_with_no_free_dict_have_transport_safe_schemas():
    assert is_transport_safe(REGISTRY.transport_schema("work_task")) == []
    assert is_transport_safe(REGISTRY.transport_schema("chat_session", kind="org")) == []
    for family, field in (("chat_message", "card"), ("usage_record", "detail")):          # a free JSON object is the one reason the registry refuses
        with pytest.raises(RegistryError, match=f"transport_dict.*/{field}/"):
            REGISTRY.transport_schema(family, kind=next(iter(REGISTRY.kinds(family))))
