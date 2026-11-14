"""The live side of `ChatPort` and the router (streaming design D217, D218, D213; work package STR-5): route events only on the chat path that asked for them,
`started` forwarded, a restart that carries its reason, `usage` and `switched` only in `turn_done`, the parser kinds, tool descriptions and the idle-timeout words.
Everything older callers see is covered by the unchanged test_chat_port.py, test_chat_restart.py and test_router_chat.py."""
from __future__ import annotations

import json
import sys

import pytest

from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.chat_blocks import BlockAccumulator
from sutra_app.connectors.chat_models import EVENT_KINDS, ChatEvent, ChatTurnIn
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import JSON_BUFFER_MAX, ClaudeConnector, ClaudeParser
from sutra_app.connectors.codex import CodexParser
from sutra_app.connectors.errors import CallTimeoutError, CrashedError, ServerError
from sutra_app.connectors.models import AskRequest, ConnectorConfig, ConnectorEvent, Message, RouteContext
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.tool_kinds import describe

from test_router_chat import History, Named, policy

SID = "cs_live"


def kinds(events):
    return [e.kind for e in events]


def rig(tmp_path, *connectors, **defaults):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    made = {c.name: c for c in connectors} or {"claude": Named("claude", cfg), "codex": Named("codex", cfg)}
    router = Router(made, policy(**defaults), transcripts=History(), sleep=lambda s: None, rng=lambda: 0.0)
    return RouterChatPort(router), router


class Dies(StubConnector):
    """Streams some text, then dies, `dies` times; then answers."""

    def __init__(self, name, cfg, dies):
        super().__init__(cfg)
        self.name, self.dies = name, dies

    def resolve_model(self, requested):
        return requested or "scripted"

    def _spawn(self, plan, hooks, box):
        inner = super()._spawn(plan, hooks, box)
        if self.dies <= 0:
            yield from inner
            return
        self.dies -= 1
        for event in inner:
            yield event
            if event.kind == "text_delta":
                inner.close()
                raise CrashedError("died", provider=self.name, detail={"exit": 137})


# ---- the old callers see the old events --------------------------------------------------------------------------------------------

def test_without_an_accumulator_the_events_are_the_old_kinds_only(tmp_path):
    port, router = rig(tmp_path)
    got = kinds(port.stream(SID, ChatTurnIn(text="hello")))
    assert set(got) <= {"partial", "block", "restart", "usage", "switched", "turn_done"} and got[-1] == "turn_done"


def test_the_router_gives_route_events_only_to_a_caller_that_asked(tmp_path):
    port, router = rig(tmp_path)
    plain = list(router.chat_stream(SID, Message(role="user", text="hi"), RouteContext()))
    assert "route" not in kinds(plain) and kinds(plain)[0] == "started"
    asked = list(router.chat_stream("cs_live2", Message(role="user", text="hi"), RouteContext(), routes=True))
    assert kinds(asked)[:2] == ["route", "route"] and [e.data["event"] for e in asked if e.kind == "route"] == ["plan", "attempt"]


def test_an_engine_request_never_sees_a_route_event(tmp_path):
    port, router = rig(tmp_path)
    seen = []
    router.ask(AskRequest(user="hello"), on_progress=seen.append)
    assert not [p for p in seen if "event" in p]


# ---- the live kinds ----------------------------------------------------------------------------------------------------------------

def test_a_live_stream_yields_route_started_and_block_events_and_ends_with_a_turn_done_that_carries_the_ordered_blocks(tmp_path):
    port, router = rig(tmp_path)
    acc = BlockAccumulator()
    events = list(port.stream(SID, ChatTurnIn(text="hello"), acc=acc))
    got = kinds(events)
    assert got[0] == "route" and got[1] == "route" and got[2] == "started" and got[-1] == "turn_done"
    assert set(got) <= set(EVENT_KINDS) and "partial" not in got and "block" not in got
    plan, attempt = events[0].data, events[1].data
    assert plan["event"] == "plan" and plan["order"] == ["claude", "codex"]
    assert attempt["event"] == "attempt" and attempt["provider"] == "claude" and attempt["n"] == 1 and attempt["stream_mode"] == "tokens" and "idle_limit_s" in attempt
    assert events[2].data["provider"] == "claude"
    done = events[-1].data
    assert [b["type"] for b in done["blocks_ordered"]] == ["text"] and done["blocks_ordered"][0]["text"] == done["text"] and done["stored_order"] == ["b1"]
    assert done["earlier"] == [] and "usage" in done and done["blocks"] == acc.stored_blocks()
    assert "".join(e.data["delta"] for e in events if e.kind == "block_delta") == done["text"]
    assert [e.kind for e in events if e.kind.startswith("block_")][-1] == "block_end"                 # every block is ended before turn_done


def test_usage_and_switched_ride_the_turn_done_and_are_not_live_blocks(tmp_path):
    port, router = rig(tmp_path)
    list(port.stream(SID, ChatTurnIn(text="one")))
    router.transcripts.messages_list = []
    port.choose(SID, "codex")
    events = list(port.stream(SID, ChatTurnIn(text="two"), acc=BlockAccumulator()))
    assert events[-1].data["switched"]["to"] == "codex" and "usage" in events[-1].data


def test_the_stop_token_reaches_the_router_through_a_live_stream(tmp_path):
    from sutra_app.connectors.cancel import CancelToken
    from sutra_app.connectors.errors import CallCancelledError
    port, router = rig(tmp_path)
    token = CancelToken()
    token.request()
    with pytest.raises(CallCancelledError):
        list(port.stream(SID, ChatTurnIn(text="hello"), cancel=token, acc=BlockAccumulator()))


def test_a_retry_emits_route_failed_before_the_wait_and_a_restart_that_carries_the_reason_and_the_new_provider(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    claude, codex = Dies("claude", cfg, dies=3), Named("codex", cfg)
    router = Router({"claude": claude, "codex": codex}, policy(max_attempts=2), transcripts=History(), sleep=lambda s: None, rng=lambda: 0.0)
    acc = BlockAccumulator()
    events = list(RouterChatPort(router).stream(SID, ChatTurnIn(text="please answer"), acc=acc))
    routes = [e.data for e in events if e.kind == "route"]
    assert [r["event"] for r in routes] == ["plan", "attempt", "failed", "attempt", "failed", "attempt"]
    first_fail, second_fail = routes[2], routes[4]
    assert first_fail["provider"] == "claude" and first_fail["action"] == "retry" and first_fail["delay_s"] == 2.0 and first_fail["retryable"] is True
    assert "stopped unexpectedly" in first_fail["reason"] and first_fail["next_provider"] == "claude" and "Traceback" not in json.dumps(first_fail)
    assert second_fail["action"] == "fallback" and second_fail["delay_s"] == 0.0 and second_fail["next_provider"] == "codex"
    restarts = [e for e in events if e.kind == "restart"]
    assert len(restarts) == 2 and restarts[0].data["reason"] == first_fail["reason"] and restarts[0].data["provider"] == "claude"
    assert restarts[1].data["provider"] == "codex" and restarts[1].data["after_side_effects"] is False
    order = kinds(events)
    assert order.index("route") < order.index("started")
    assert order.index("restart") > [i for i, e in enumerate(events) if e.kind == "route" and e.data["event"] == "failed"][0]
    done = events[-1].data
    assert len(done["earlier"]) == 2 and done["earlier"][0]["provider"] == "claude" and done["earlier"][1]["provider"] == "claude"
    assert "".join(e.data["delta"] for e in events[order.index("restart", order.index("restart") + 1):] if e.kind == "block_delta") == done["text"]
    assert acc.provider == "codex"
    router.close()


def test_route_failed_names_the_attempts_and_a_non_retryable_failure_says_fail(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)

    class Refuses(Named):
        def stream(self, *a, **kw):
            from sutra_app.connectors.errors import InvalidRequestError
            raise InvalidRequestError("nope", provider=self.name)
    router = Router({"claude": Refuses("claude", cfg)}, policy(order=["claude"]), transcripts=History(), sleep=lambda s: None)
    port = RouterChatPort(router)
    seen = []
    with pytest.raises(Exception):
        for e in port.stream(SID, ChatTurnIn(text="x"), acc=BlockAccumulator()):
            seen.append(e)
    failed = [e.data for e in seen if e.kind == "route" and e.data["event"] == "failed"]
    assert len(failed) == 1 and failed[0]["action"] == "fail" and failed[0]["retryable"] is False and failed[0]["next_provider"] is None


def test_stream_mode_by_provider(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    from sutra_app.connectors.codex import CodexConnector
    router = Router({"codex": CodexConnector(cfg), "claude": ClaudeConnector(cfg), "stub": StubConnector(cfg)}, policy(order=["codex"]), transcripts=History(), sleep=lambda s: None)
    from sutra_app.connectors.router import _stream_mode
    assert (_stream_mode("codex", router._connectors["codex"]), _stream_mode("claude", router._connectors["claude"]), _stream_mode("stub", router._connectors["stub"])) == ("activity", "tokens", "simulated")


# ---- the parser kinds ---------------------------------------------------------------------------------------------------------------

def claude_plan(partials=True):
    return TurnPlan(prompt="x", ctx=RouteContext(), model="m", effort="low", partials=partials, kind="chat")


def sev(**event):
    return json.dumps({"type": "stream_event", "event": event})


def test_claude_parser_emits_block_kinds_only_for_a_partials_turn():
    lines = [sev(type="message_start"), sev(type="content_block_start", index=0, content_block={"type": "tool_use", "id": "t1", "name": "Read", "input": {}}),
             sev(type="content_block_stop", index=0)]
    quiet, loud = ClaudeParser(claude_plan(False)), ClaudeParser(claude_plan(True))
    assert [quiet.feed(l) for l in lines] == [[], [], []]
    got = [e for l in lines for e in loud.feed(l)]
    assert [(e.kind, e.data) for e in got] == [("message_boundary", {}), ("block_start", {"index": 0, "type": "tool_use", "tool_id": "t1", "name": "Read"}), ("block_stop", {"index": 0})]


def test_claude_parser_buffers_tool_input_privately_and_parses_it_at_the_stop():
    p = ClaudeParser(claude_plan())
    p.feed(sev(type="message_start"))
    p.feed(sev(type="content_block_start", index=2, content_block={"type": "tool_use", "id": "t", "name": "Read", "input": {}}))
    for piece in ('', '{"file_path": "/w', '/a.py"}'):
        p.feed(sev(type="content_block_delta", index=2, delta={"type": "input_json_delta", "partial_json": piece}))
    stop = p.feed(sev(type="content_block_stop", index=2))[0]
    assert stop.data == {"index": 2, "input": {"file_path": "/w/a.py"}}


def test_claude_parser_buffer_is_bounded_and_a_bad_buffer_is_dropped_without_failing():
    p = ClaudeParser(claude_plan())
    p.feed(sev(type="content_block_start", index=0, content_block={"type": "tool_use", "id": "t", "name": "Write", "input": {}}))
    for _ in range(JSON_BUFFER_MAX // 100 + 5):
        p.feed(sev(type="content_block_delta", index=0, delta={"type": "input_json_delta", "partial_json": "x" * 100}))
    assert p.feed(sev(type="content_block_stop", index=0))[0].data == {"index": 0}                       # too big: dropped, never sent
    q = ClaudeParser(claude_plan())
    q.feed(sev(type="content_block_start", index=0, content_block={"type": "tool_use", "id": "t", "name": "Read", "input": {}}))
    q.feed(sev(type="content_block_delta", index=0, delta={"type": "input_json_delta", "partial_json": '{"a":'}))
    assert q.feed(sev(type="content_block_stop", index=0))[0].data == {"index": 0}                       # cut short: no input, no error


def test_claude_parser_thinking_and_text_blocks_and_unknown_blocks():
    p = ClaudeParser(claude_plan())
    got = [e for l in (sev(type="content_block_start", index=0, content_block={"type": "thinking", "thinking": ""}),
                       sev(type="content_block_delta", index=0, delta={"type": "thinking_delta", "thinking": "private"}),
                       sev(type="content_block_start", index=1, content_block={"type": "text", "text": ""}),
                       sev(type="content_block_start", index=2, content_block={"type": "image"}),
                       sev(type="content_block_start", index="x", content_block={"type": "text"})) for e in p.feed(l)]
    assert [(e.kind, e.data["type"]) for e in got] == [("block_start", "thinking"), ("block_start", "text")] and "private" not in json.dumps([e.data for e in got])


def test_message_start_resets_the_input_buffers_of_the_previous_message():
    p = ClaudeParser(claude_plan())
    p.feed(sev(type="content_block_start", index=0, content_block={"type": "tool_use", "id": "t", "name": "Read", "input": {}}))
    p.feed(sev(type="message_start"))
    assert p.feed(sev(type="content_block_stop", index=0))[0].data == {"index": 0}


def codex_plan(kind="chat"):
    return TurnPlan(prompt="x", ctx=RouteContext(), model="m", effort="low", kind=kind)


def test_codex_parser_item_started_and_completed_for_a_chat_turn_only():
    start = json.dumps({"type": "item.started", "item": {"id": "i0", "type": "command_execution", "command": "ls", "aggregated_output": "", "exit_code": None, "status": "in_progress"}})
    done = json.dumps({"type": "item.completed", "item": {"id": "i0", "type": "command_execution", "command": "ls", "aggregated_output": "a" * 3000, "exit_code": 1, "status": "failed"}})
    chat, engine = CodexParser(codex_plan()), CodexParser(codex_plan("text"))
    assert engine.feed(start) == [] and [e.kind for e in engine.feed(done)] == ["tool_call"]              # an engine call sees what it always saw
    started = chat.feed(start)
    assert [(e.kind, e.data["name"], e.data["input"]) for e in started] == [("block_start", "command_execution", {"command": "ls"})]
    finished = chat.feed(done)
    assert [e.kind for e in finished] == ["tool_call", "block_stop"]
    stop = finished[1].data
    assert stop["completed"] is True and stop["exit_code"] == 1 and len(stop["output"]) == 2000 and stop["truncated"] is True and stop["tool_id"] == "i0"


def test_codex_parser_does_not_open_a_block_for_a_message_or_an_error_item():
    p = CodexParser(codex_plan())
    for kind in ("agent_message", "error", "reasoning"):
        assert p.feed(json.dumps({"type": "item.started", "item": {"id": "x", "type": kind}})) == []


# ---- tool descriptions, error words --------------------------------------------------------------------------------------------------

def test_describe_paths_relative_to_the_turn_folder_or_a_basename_and_never_the_root(tmp_path):
    folder = str(tmp_path / "proj")
    (tmp_path / "proj" / "src").mkdir(parents=True)
    assert describe("Read", {"file_path": f"{folder}/src/a.py"}, folder) == ("read", "Reading src/a.py", "src/a.py")
    assert describe("Edit", {"file_path": "/etc/hosts"}, folder)[2] == "hosts"                            # outside the folder: the basename only
    assert describe("Read", {"file_path": "src/b.py"}, folder)[2] == "src/b.py" and describe("Read", {"file_path": "../../x/y.txt"}, folder)[2] == "y.txt"
    assert describe("Read", {"file_path": folder}, folder)[2] == "proj"
    for kind, title, target in (describe("Read", {"file_path": f"{folder}/src/a.py"}, folder), describe("Glob", {"pattern": "**/*.py", "path": folder}, folder)):
        assert str(tmp_path) not in title + target


def test_describe_commands_queries_urls_unknown_tools_and_nonsense():
    assert describe("Bash", {"command": "ls   -la\n/tmp"}) == ("run", "Running ls -la /tmp", "ls -la /tmp")
    assert describe("command_execution", {"command": "/bin/zsh -lc \"cat 'a b.txt'\""}, "", "codex")[2] == "cat 'a b.txt'"
    assert describe("Grep", {"pattern": "TODO"})[:2] == ("search", "Searching TODO") and describe("WebFetch", {"url": "https://x.example"})[1] == "Fetching https://x.example"
    assert describe("Mystery", {"x": 1}) == ("other", "Using Mystery", "") and describe(None, None) == ("other", "Using a tool", "")
    assert describe("Bash", {"command": "x" * 900})[2] == "x" * 200 and len(describe("Bash", {"command": "x" * 900})[1]) <= 200
    assert describe("Read", ["not a dict"]) == ("read", "Using Read", "") and describe("Read", {"file_path": 7}) == ("read", "Using Read", "")


def test_an_idle_timeout_names_the_limit_and_a_total_timeout_keeps_its_words():
    idle = CallTimeoutError("", provider="claude", detail={"which": "idle", "seconds": 120})
    total = CallTimeoutError("", provider="claude", detail={"which": "total", "seconds": 900})
    assert idle.user_message() == "Claude did not answer within 120 s: it sent no output for that long, so it was stopped"
    assert total.user_message() == "Claude did not answer within 900 s"


def test_started_event_data_of_the_real_connector_has_what_the_live_turn_needs(tmp_path):
    port, router = rig(tmp_path)
    events = list(port.stream(SID, ChatTurnIn(text="hello"), acc=BlockAccumulator()))
    started = next(e for e in events if e.kind == "started")
    assert started.data["provider"] == "claude" and "session_id" in started.data
