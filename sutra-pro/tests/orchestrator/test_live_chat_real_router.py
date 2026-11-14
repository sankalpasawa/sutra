"""The live direct chat end to end over the REAL router and connectors, with the fake `claude` replaying the captured stream (streaming design D201 to D222, work package STR-7).

Everything between the HTTP route and the process is real: `RouterChatPort`, `Router` (with its route events and back-off), `ClaudeConnector`, the process runner and its cancel ladder,
`BlockAccumulator`, `LiveTurn`. Only the model is a fake CLI that replays `tests/fixtures/connectors/claude/stream_partials_tool_ok.jsonl`. POSIX only (the fakes are shell wrappers)."""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from orchestrator.test_api_chat_v2 import H, error_code, rig, wait_for, world  # noqa: F401  (the fixtures of the chat v2 routes)

from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.orchestrator import direct_running
from sutra_app.orchestrator.chats import ChatTranscripts
from sutra_app.orchestrator.events import LIVE

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLIs are POSIX")

_spec = importlib.util.spec_from_file_location("connectors_conftest_for_live", Path(__file__).resolve().parent.parent / "connectors" / "conftest.py")
_conftest = importlib.util.module_from_spec(_spec)
sys.modules["connectors_conftest_for_live"] = _conftest
_spec.loader.exec_module(_conftest)

CID = "client-real-0001"


def policy(**defaults):
    base = {"order": ["claude"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2, "retry_delays_s": [30, 30], "repair_rounds": 2,
            "max_calls_per_request": 6, "fallback_on_invalid_json": False, "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4}}, "defaults": base, "rules": [], "rates": {}})


class Real:
    """The live chat wired to a real router over the fake claude. `play(...)` sets the fake's scenarios and THEN builds the connector (its environment is read when it is built)."""

    def __init__(self, rig, tmp_path):
        self.client, self.world, self.chats, self.bus, self.services = rig
        self.fake = _conftest.FakeCli(tmp_path / "fake")
        self.fake.root.mkdir(parents=True, exist_ok=True)
        self.tmp, self.connector, self.router, self.seen = tmp_path, None, None, []
        self.services.settings = self.services.settings.model_copy(update={"live_v1": True, "live_coalesce_ms": 5, "live_checkpoint_s": 0.05})
        original = self.bus.publish_one

        def record(type, data=None):
            if type == LIVE:
                self.seen.append(json.loads(json.dumps(data)))
            return original(type, data)
        self.bus.publish_one = record

    def play(self, *scenarios, delay="0.02", retry_delays=(30, 30), sleep=None):
        self.fake.sequence(*scenarios, cli="claude").set(FAKE_LINE_DELAY=delay)
        cfg = ConnectorConfig(**self.fake.config_kwargs(self.tmp / f"real{len(self.fake.vars)}{time.time_ns()}"))
        self.connector = ClaudeConnector(cfg)
        kw = {} if sleep is None else {"sleep": sleep}
        self.router = Router({"claude": self.connector}, policy(retry_delays_s=list(retry_delays)), transcripts=ChatTranscripts(self.chats), **kw)
        self.services.chat_port = RouterChatPort(self.router)
        return self

    def close(self):
        for sid in list(direct_running.RUNNING):
            token = direct_running.token_of(sid)
            if token is not None:
                token.request()
        wait_for(lambda: not direct_running.RUNNING, 15)
        if self.router is not None:
            self.router.close()
        self.fake.close()


@pytest.fixture
def real(rig, tmp_path):
    r = Real(rig, tmp_path)
    yield r
    r.close()


def post(client, sid, text="please read the notes", **extra):
    return client.post(f"/api/chats/{sid}/direct", json={"text": text, "client_id": CID, **extra}, headers=H)


def done(chats, sid, count, seconds=30):
    return wait_for(lambda: len(chats.messages(sid)) >= count and not direct_running.answering(sid), seconds)


def test_a_real_tool_turn_streams_a_tool_line_then_text_and_is_stored_in_order(real):
    sid = real.world.session_of["web"]
    real.play("tool_partials")
    r = post(real.client, sid)
    assert r.status_code == 202
    assert done(real.chats, sid, 2)
    e = real.seen
    assert [x["seq"] for x in e] == list(range(1, len(e) + 1))
    kinds = [x["type"] for x in e]
    assert kinds[:3] == ["turn.accepted", "turn.connecting", "turn.started"] and kinds[-1] == "turn.done"
    connecting = e[1]["payload"]
    assert connecting["provider"] == "claude" and connecting["stream_mode"] == "tokens"
    start = next(x for x in e if x["type"] == "block.start" and x["payload"]["type"] == "tool_use")
    assert start["payload"] == {"type": "tool_use", "kind": "read", "name": "Read"}                       # the tool line begins with the name only
    update = next(x for x in e if x["type"] == "block.update")
    assert update["block_id"] == start["block_id"] and update["payload"]["title"] == "Reading notes.txt" and update["payload"]["target"] == "notes.txt"
    assert kinds.index("block.start") < kinds.index("block.update") < [i for i, k in enumerate(kinds) if k == "block.end"][0]
    text = "".join(x["payload"]["delta"] for x in e if x["type"] == "block.delta")
    reply = real.chats.messages(sid)[1]
    assert text and reply.ordered and [b.type for b in reply.blocks] == ["tool_use", "tool_result", "text"] and reply.blocks[2].text == text
    assert "launch checklist" in reply.text and reply.attempt == 1
    text_block = next(x["block_id"] for x in e if x["type"] == "block.start" and x["payload"]["type"] == "text")
    assert e[-1]["payload"]["stored_order"] == [start["block_id"], start["block_id"], text_block]
    assert real.connector.runner.live() == [] and not direct_running.answering(sid)


def test_a_real_stop_cancels_the_process_group_and_the_turn_ends_stopped_with_the_text_that_was_shown(real):
    sid = real.world.session_of["web"]
    real.play("tool_partials", delay="0.4")
    post(real.client, sid)
    assert wait_for(lambda: any(x["type"] == "block.start" for x in real.seen), 20)
    assert wait_for(lambda: real.connector.runner.live() != [], 5)
    began = time.time()
    r = real.client.post(f"/api/chats/{sid}/direct/stop", headers=H)
    assert time.time() - began < 1.0 and r.json()["stopped"] is True
    assert done(real.chats, sid, 2, 30)
    assert time.time() - began < 15
    assert real.connector.runner.live() == []                                                     # no process left running
    last = real.seen[-1]
    assert last["type"] == "turn.stopped" and last["payload"]["exit"] == "cancelled"
    kinds = [x["type"] for x in real.seen]
    assert kinds.index("turn.stopping") < kinds.index("turn.stopped")
    rows = real.chats.messages(sid)[1:]
    assert rows[-1].kind == "note" and rows[-1].text.startswith("Stopped")
    ends = [x for x in real.seen if x["type"] == "block.end"]
    assert all(x["payload"]["status"] in ("ok", "interrupted") for x in ends)
    assert not direct_running.answering(sid) and real.router.chat_stop(sid) is False


def test_a_stop_in_the_back_off_wait_of_a_real_router_ends_the_wait_at_once(real):
    """The fake claude crashes without a result; the router would wait 30 s before the second attempt. Stop ends the wait, the process of the second attempt never starts."""
    sid = real.world.session_of["web"]
    real.play("crash")
    post(real.client, sid)
    assert wait_for(lambda: any(x["type"] == "attempt.failed" for x in real.seen), 20)
    failed = next(x for x in real.seen if x["type"] == "attempt.failed")["payload"]
    assert failed["action"] == "retry" and 30 <= failed["delay_s"] <= 31 and failed["provider"] == "claude" and "stopped unexpectedly" in failed["reason"]
    began = time.time()
    assert real.client.post(f"/api/chats/{sid}/direct/stop", headers=H).json()["stopped"] is True
    assert done(real.chats, sid, 2, 10)
    assert time.time() - began < 8                                                                # not 30 s
    assert real.seen[-1]["type"] == "turn.stopped"
    assert len(real.fake.model_calls("claude")) == 1                                              # the second attempt never started a process
    assert real.connector.runner.live() == []


def test_a_real_retry_after_a_crash_reports_the_failure_then_the_restart_and_lands_one_reply(real):
    sid = real.world.session_of["web"]
    real.play("crash", "tool_partials", delay="0.01", retry_delays=(0.05, 0.05))
    post(real.client, sid)
    assert done(real.chats, sid, 2, 40)
    kinds = [x["type"] for x in real.seen]
    assert "attempt.failed" in kinds and "attempt.restart" in kinds and kinds[-1] == "turn.done"
    assert kinds.index("attempt.failed") < kinds.index("attempt.restart")
    assert [x["attempt"] for x in real.seen if x["type"] == "turn.connecting"] == [1, 2]
    reply = real.chats.messages(sid)[1]
    assert reply.kind == "text" and "launch checklist" in reply.text and reply.attempt == 1


def test_the_route_events_never_reach_a_non_live_turn(real):
    sid = real.world.session_of["web"]
    real.play("tool_partials")
    real.services.settings = real.services.settings.model_copy(update={"live_v1": False})
    r = real.client.post(f"/api/chats/{sid}/direct", json={"text": "hello"}, headers=H)
    assert r.status_code == 202 and set(r.json()) == {"message_id", "turn"}
    assert done(real.chats, sid, 2)
    assert real.seen == []                                                                         # the legacy path publishes chat.partial, never chat.live
