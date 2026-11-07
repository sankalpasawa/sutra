"""QA direct-chat bug 5: a retried attempt starts the reply again.

The router retries a chat turn that dies (and falls back to the other provider); every attempt streams its own `text_delta` pieces. `ChatPort.stream`
used to pass them all on as one reply, so the owner's streaming row and the kept partial reply were the same sentence repeated with no separator. The
first `started` of a turn begins it; a later `started` is a new attempt: the port says so with a `restart` event and forgets what the earlier attempt
streamed (its text, its blocks), and the caller (chat_v2._answer) starts the row and the kept text again."""
from __future__ import annotations

import json
import sys

import pytest

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.errors import CrashedError
from sutra_app.connectors.models import ConnectorConfig, ConnectorEvent, Message
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector

from test_router_chat import History, Named, policy

SID = "cs_restart"


def started():
    return ConnectorEvent(kind="started", data={"session_id": "p-1", "model": "m"})


def piece(text):
    return ConnectorEvent(kind="text_delta", data={"text": text, "kind": "text"})


def done(text):
    return ConnectorEvent(kind="turn_done", data={"result": {"text": text, "provider": "claude", "model": "m", "usd": None, "usage": None}})


def port_over(tmp_path, *events):
    """A port whose router plays these connector events for any turn (the retry loop is the router's: its own test is below)."""
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    router = Router({"claude": Named("claude", cfg)}, policy(), transcripts=History(), sleep=lambda s: None)
    router.chat_stream = lambda sid, message, ctx: iter(events)
    return RouterChatPort(router)


def kinds(events):
    return [e.kind for e in events]


def test_a_second_started_is_a_new_attempt_and_the_port_says_so(tmp_path):
    port = port_over(tmp_path, started(), piece("Here is "), piece("an ans"), started(), piece("Here is the answer."), done("Here is the answer."))
    events = list(port.stream(SID, ChatTurnIn(text="hi")))
    assert kinds(events) == ["partial", "partial", "restart", "partial", "usage", "turn_done"]
    after = events[kinds(events).index("restart") + 1:]
    assert "".join(e.data["delta"] for e in after if e.kind == "partial") == "Here is the answer."


def test_one_attempt_has_no_restart(tmp_path):
    events = list(port_over(tmp_path, started(), piece("a"), piece("b"), done("ab")).stream(SID, ChatTurnIn(text="hi")))
    assert "restart" not in kinds(events)


def test_what_an_earlier_attempt_streamed_does_not_hide_the_final_text_of_the_next(tmp_path):
    """The final `text` event is shown as a block only when nothing streamed; after a restart that is again the case."""
    events = list(port_over(tmp_path, started(), piece("half"), started(), ConnectorEvent(kind="text", data={"text": "whole"}),
                            done("whole")).stream(SID, ChatTurnIn(text="hi")))
    assert kinds(events) == ["partial", "restart", "block", "usage", "turn_done"]
    assert events[2].data["text"] == "whole"
    assert [b for b in events[-1].data["blocks"]] == [events[2].data]          # only the new attempt's block is kept


def test_blocks_of_an_earlier_attempt_are_dropped_with_it(tmp_path):
    call = ConnectorEvent(kind="tool_call", data={"id": "t1", "name": "Read", "input": {"file_path": "a.md"}})
    events = list(port_over(tmp_path, started(), call, started(), piece("ok"), done("ok")).stream(SID, ChatTurnIn(text="hi")))
    assert kinds(events) == ["block", "restart", "partial", "usage", "turn_done"]
    assert events[-1].data["blocks"] == []


class DiesAfterText(StubConnector):
    """A stub that streams its reply, then dies once per `dies`: what a Claude that crashes mid-answer does to the retry loop."""

    name = "claude"

    def __init__(self, cfg, dies):
        super().__init__(cfg)
        self.dies = dies

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
                raise CrashedError("died after some text", provider="claude", detail={"exit": 137})


def test_the_real_retry_loop_restarts_the_reply_and_only_the_last_attempt_is_whole(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    connector = DiesAfterText(cfg, dies=2)
    connector.delay = 0.0
    router = Router({"claude": connector}, policy(max_attempts=3), transcripts=History(), sleep=lambda s: None, rng=lambda: 0.0)
    events = list(RouterChatPort(router).stream(SID, ChatTurnIn(text="please answer")))
    assert kinds(events).count("restart") == 2 and kinds(events)[-1] == "turn_done"
    last = events[max(i for i, e in enumerate(events) if e.kind == "restart") + 1:]
    shown = "".join(e.data["delta"] for e in last if e.kind == "partial")
    assert shown == events[-1].data["text"] and shown.startswith("[stub]")
    router.close()


def test_a_fake_claude_that_dies_after_streaming_restarts_each_attempt(fake, fixtures, tmp_path):
    """The real Claude connector over the fake CLI: three attempts, each streams pieces and dies without a result line."""
    init = next(line for line in fixtures.lines("claude/stream_resume_plain_ok.jsonl") if isinstance(line, dict) and line.get("subtype") == "init")
    lines = [init] + [{"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
                                                          "delta": {"type": "text_delta", "text": text}}, "session_id": init["session_id"]}
                      for text in ("Here is a ", "streamed ", "answer.")]
    stream = tmp_path / "partial_fail.jsonl"
    stream.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    fake.sequence("file:" + str(stream), cli="claude")                    # the last scenario repeats: every attempt dies the same way
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = Router({"claude": ClaudeConnector(cfg)}, policy(max_attempts=3), transcripts=History(), sleep=lambda s: None, rng=lambda: 0.0)
    port = RouterChatPort(router)
    seen, error = [], None
    try:
        for event in port.stream(SID, ChatTurnIn(text="fail after partial text")):
            seen.append(event)
    except Exception as exc:                                               # the third attempt fails too: the turn ends in the error line
        error = exc
    assert isinstance(error, CrashedError) or error is not None
    assert kinds(seen).count("restart") == 2
    tail = seen[max(i for i, e in enumerate(seen) if e.kind == "restart") + 1:]
    assert "".join(e.data["delta"] for e in tail if e.kind == "partial") == "Here is a streamed answer."          # one attempt's text, not three glued
    router.close()
