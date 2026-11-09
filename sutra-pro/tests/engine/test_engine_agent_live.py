"""The agent-live capability (D133, WP9): the engine publishes `<run>/agent_live.json` for the server's watcher.

What is proved: the file's shape (schema, agents, text tail of 4,000, last tool, tool count); an entry exists from an agent's first event of a call until
the call ends and is then removed; only an agent's own calls are shown, a note or a helper call is not; writes are throttled to the interval and coalesce;
an identical state writes nothing; the file is atomic and private; a router's progress events and finish hooks reach it end to end; mock mode installs
nothing."""
from __future__ import annotations

import json
import os
import stat
import sys
import time
from types import SimpleNamespace

import pytest

from sutra_app.connectors.engine_port import RouterPort
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.policy import load_default_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.engine import llm
from sutra_app.engine.capabilities.agents import LIVE_FILE, LIVE_SCHEMA, LIVE_TAIL, AgentLiveCapability
from sutra_app.engine.port import CallTag, CompletionRequest


def tag(function="W-3", purpose="agent_turn", call_no=7):
    return CallTag(function=function, purpose=purpose, call_no=call_no)


@pytest.fixture
def live(tmp_path):
    cap = AgentLiveCapability(threaded=False, clock=lambda: 1000.0)
    cap.attach(tmp_path / LIVE_FILE)
    return cap


def read(tmp_path):
    return json.loads((tmp_path / LIVE_FILE).read_text(encoding="utf-8"))


# ---- the entry and the file -----------------------------------------------------------------------------------------------------

def test_an_agent_is_listed_with_its_text_its_last_tool_and_the_tool_count(live, tmp_path):
    live.progress(tag(), {"tool": "Read src/app.py"})
    live.progress(tag(), {"chars": 5, "text": "Hello"})
    live.progress(tag(), {"tool": "Grep main"})
    assert live.write_now() is True
    doc = read(tmp_path)
    assert doc["schema"] == LIVE_SCHEMA == "agent-live/1" and doc["at"] == 1000.0
    assert doc["agents"] == {"W-3": {"call": 7, "since": 1000.0, "text": "Hello", "tool": "Grep main", "tools": 2}}


def test_the_text_keeps_its_tail_and_each_event_replaces_it(live, tmp_path):
    live.progress(tag(), {"chars": 6000, "text": "a" * 2000 + "b" * 4000})
    live.write_now()
    assert read(tmp_path)["agents"]["W-3"]["text"] == "b" * LIVE_TAIL
    live.progress(tag(), {"chars": 3, "text": "new"})                         # a retried call starts its text again
    live.write_now()
    assert read(tmp_path)["agents"]["W-3"]["text"] == "new"


def test_two_agents_at_once_and_an_entry_goes_when_its_call_ends(live, tmp_path):
    live.progress(tag("W-3"), {"chars": 1, "text": "x"})
    live.progress(tag("identity", "plan", 2), {"chars": 1, "text": "y"})
    live.write_now()
    assert sorted(read(tmp_path)["agents"]) == ["W-3", "identity"]
    live.finished(tag("W-3"))
    live.write_now()
    assert list(read(tmp_path)["agents"]) == ["identity"]
    live.finished(tag("identity", "plan"))
    live.write_now()
    assert read(tmp_path)["agents"] == {}
    live.finished(tag("identity"))                                           # a second finish, or one for an unknown agent, is nothing
    assert live.write_now() is False


def test_a_new_call_of_the_same_agent_is_a_new_entry(live, tmp_path):
    live.progress(tag(call_no=1), {"tool": "Read a"})
    live.finished(tag(call_no=1))
    live.progress(tag(call_no=2), {"chars": 1, "text": "x"})
    live.write_now()
    entry = read(tmp_path)["agents"]["W-3"]
    assert entry["call"] == 2 and entry["tools"] == 0 and entry["tool"] == ""


@pytest.mark.parametrize("event", [{"note": "claude out of quota, answered by codex"}, {}, {"chars": 1}, "text"])
def test_a_note_or_a_shapeless_event_is_not_live_work(live, event):
    live.progress(tag(), event)
    assert live.snapshot()["agents"] == {}


@pytest.mark.parametrize("purpose", ["summary", "template", "review", "change", "chat_plan"])
def test_a_helper_call_is_not_shown_as_the_agents(live, purpose):
    live.progress(tag("identity", purpose), {"chars": 1, "text": "x"})
    assert live.snapshot()["agents"] == {}


@pytest.mark.parametrize("purpose", ["agent_turn", "plan", "judge"])
def test_an_agents_own_calls_are_shown(live, purpose):
    live.progress(tag("audit", purpose), {"chars": 1, "text": "x"})
    assert list(live.snapshot()["agents"]) == ["audit"]


def test_an_identical_state_writes_nothing_again(live, tmp_path):
    live.progress(tag(), {"chars": 1, "text": "x"})
    assert live.write_now() is True
    mtime = (tmp_path / LIVE_FILE).stat().st_mtime_ns
    assert live.write_now() is False and (tmp_path / LIVE_FILE).stat().st_mtime_ns == mtime and live.writes == 1


def test_the_file_is_private_and_no_temp_file_is_left(live, tmp_path):
    live.progress(tag(), {"chars": 1, "text": "x"})
    live.write_now()
    assert stat.S_IMODE(os.stat(tmp_path / LIVE_FILE).st_mode) == 0o600 or sys.platform == "win32"
    assert [p.name for p in tmp_path.iterdir()] == [LIVE_FILE]


def test_a_folder_that_is_gone_loses_the_view_not_the_run(tmp_path):
    cap = AgentLiveCapability(threaded=False)
    cap.attach(tmp_path / "gone" / LIVE_FILE)
    cap.progress(tag(), {"chars": 1, "text": "x"})
    assert cap.write_now() is False


# ---- the thread: throttled and coalescing ---------------------------------------------------------------------------------------------

def wait_for(check, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return False


def test_writes_are_throttled_to_the_interval_and_the_last_state_arrives(tmp_path):
    cap = AgentLiveCapability(interval=0.1)
    cap.attach(tmp_path / LIVE_FILE)
    try:
        started = time.monotonic()
        for n in range(1, 301):
            cap.progress(tag(), {"chars": n, "text": "x" * n})
            time.sleep(0.001)
        elapsed = time.monotonic() - started
        assert wait_for(lambda: (tmp_path / LIVE_FILE).exists() and read(tmp_path)["agents"].get("W-3", {}).get("text") == "x" * 300)
        assert 1 <= cap.writes <= elapsed / 0.1 + 3, (cap.writes, elapsed)           # 300 events, a handful of writes
    finally:
        cap.close()


def test_the_removal_reaches_the_file_and_close_leaves_it_empty(tmp_path):
    cap = AgentLiveCapability(interval=0.02)
    cap.attach(tmp_path / LIVE_FILE)
    cap.progress(tag(), {"chars": 1, "text": "x"})
    assert wait_for(lambda: (tmp_path / LIVE_FILE).exists() and "W-3" in read(tmp_path)["agents"])
    cap.finished(tag())
    assert wait_for(lambda: read(tmp_path)["agents"] == {})
    cap.close()
    assert read(tmp_path)["agents"] == {} and cap._thread is None


# ---- through a router -----------------------------------------------------------------------------------------------------------------

def make_port(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    return RouterPort(Router({"stub": StubConnector(cfg)}, load_default_policy(), connector="stub"), mock=True)


def test_install_wires_the_progress_hook_and_the_finish_hook_through_a_router(tmp_path):
    port = make_port(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cap = AgentLiveCapability(threaded=False)
    cap.install(SimpleNamespace(port=port, paths=SimpleNamespace(run_dir=run_dir), data_dir=tmp_path))
    assert cap.finished in port.router.finish_hooks
    cap.install(SimpleNamespace(port=port, paths=SimpleNamespace(run_dir=run_dir), data_dir=tmp_path))      # a second install adds no second hook
    assert port.router.finish_hooks.count(cap.finished) == 1
    seen = {}

    def on_progress(event):
        cap.progress(tag("W-3"), event)                                      # what llm._hooked_progress does with every event
        seen["while"] = cap.snapshot()["agents"].get("W-3", {}).get("text")

    port.complete(CompletionRequest(system="s", user="u", scripted=lambda: "the reply", tag=tag("W-3")), on_progress)
    assert seen["while"] == "the reply"                                      # listed while the call was going
    assert cap.snapshot()["agents"] == {}                                    # and gone when it ended


def test_in_mock_mode_install_changes_nothing(tmp_path):
    cap = AgentLiveCapability(threaded=False)
    cap.install(SimpleNamespace(port=llm.ScriptedPort(), paths=SimpleNamespace(run_dir=tmp_path), data_dir=tmp_path))
    cap.progress(tag(), {"chars": 1, "text": "x"})
    assert cap.write_now() is False and not (tmp_path / LIVE_FILE).exists() and cap._thread is None


def test_the_capability_adds_nothing_to_a_calls_tag_or_text(tmp_path):
    cap = AgentLiveCapability(threaded=False)
    ctx = SimpleNamespace(paths=SimpleNamespace(run_dir=tmp_path))
    assert cap.name == "agent-live" and cap.outputs() == {} and cap.tag(tag(), ctx) == {} and cap.addendum("W-3", ctx) == ""
