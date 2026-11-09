"""The agent-picks capability (D131, WP6): the engine process reads `<run>/choices.json` and its router honours each agent's own model and effort.

The file is written by the server (`connectors/agent_picks.py`), read here per call. What is proved: `install` gives the process's router the reader
(from the context's port, or from the port `llm` was configured with); a change of the file between two calls shows in the second call and not in the
first; an agent's own pick beats the run's default; "Default" (no pick) and a bad file leave the policy; mock mode has no router and nothing breaks;
the capability adds nothing to a call's tag or text."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from sutra_app.connectors.agent_picks import build_choices, write_choices
from sutra_app.connectors.engine_port import RouterPort
from sutra_app.connectors.models import AuthStatus, ConnectorConfig, Pick
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine import llm
from sutra_app.engine.capabilities.agents import AgentPicksCapability
from sutra_app.engine.port import CallTag, CompletionRequest


def policy():
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4}, "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2}},
                         "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
                                      "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
                                      "tool_profile": "none", "idle_timeout_s": 120}, "rules": [], "rates": {}})


class Named(StubConnector):
    def __init__(self, name, cfg):
        super().__init__(cfg)
        self.name = name
        self.got = []

    def resolve_model(self, requested):
        return requested or f"{self.name}-default"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=True, billing="subscription", checked_at=self._clock())

    def call_text(self, prompt, **kw):
        self.got.append({"model": kw.get("model"), "effort": kw.get("effort")})
        return super().call_text(prompt, **kw)


class Rig:
    def __init__(self, tmp_path):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Named("claude", cfg), Named("codex", cfg)
        self.sink = MemoryUsageSink()
        self.router = Router({"claude": self.claude, "codex": self.codex}, policy(), usage_sink=self.sink, sleep=lambda s: None)
        self.port = RouterPort(self.router)
        self.run_dir = tmp_path / "run"
        self.run_dir.mkdir()
        self.file = self.run_dir / "choices.json"
        self.ctx = SimpleNamespace(port=self.port, paths=SimpleNamespace(run_dir=self.run_dir), data_dir=tmp_path / "data")
        self.rev = 0

    def choose(self, default=None, **agents):
        self.rev += 1
        write_choices(self.file, build_choices(self.rev, default, agents, default_from="run" if default else ""))

    def call(self, function="identity", purpose="agent_turn"):
        self.port.complete(CompletionRequest(system="s", user="u", tag=CallTag(function=function, purpose=purpose)))
        return self.sink.rows[-1].provider


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_install_gives_the_router_the_reader_of_the_runs_choices_file(rig):
    assert rig.router.agent_pick is None
    AgentPicksCapability().install(rig.ctx)
    assert rig.router.agent_pick is not None
    assert rig.call() == "claude" and rig.claude.got == [{"model": "sonnet", "effort": "high"}]      # no file yet: the policy answers


def test_a_change_of_the_file_between_two_calls_shows_in_the_second_only(rig):
    AgentPicksCapability().install(rig.ctx)
    rig.choose(**{"W-3": Pick(provider="claude", model="haiku", effort="low")})
    assert rig.call("W-3") == "claude"
    rig.choose(**{"W-3": Pick(provider="codex", model="gpt-5.6-terra", effort="xhigh")})
    assert rig.call("W-3") == "codex"
    rig.choose()                                                                  # the owner cleared it: back to the policy
    assert rig.call("W-3") == "claude"
    assert rig.claude.got == [{"model": "haiku", "effort": "low"}, {"model": "sonnet", "effort": "high"}]
    assert rig.codex.got == [{"model": "gpt-5.6-terra", "effort": "xhigh"}]


def test_an_agents_own_pick_beats_the_runs_default_and_the_others_follow_the_default(rig):
    AgentPicksCapability().install(rig.ctx)
    rig.choose(default=Pick(provider="codex", model="gpt-5.6-luna", effort="medium"), identity=Pick(provider="claude", model="haiku", effort="low"))
    assert rig.call("identity") == "claude" and rig.call("W-1") == "codex" and rig.call("audit") == "codex"
    assert rig.claude.got == [{"model": "haiku", "effort": "low"}] and rig.codex.got[0] == {"model": "gpt-5.6-luna", "effort": "medium"}


def test_only_an_agents_own_calls_use_the_pick(rig):
    AgentPicksCapability().install(rig.ctx)
    rig.choose(default=Pick(provider="codex", effort="low"))
    assert rig.call("identity", "agent_turn") == "codex" and rig.call("W-2", "plan") == "codex" and rig.call("audit", "judge") == "codex"
    assert rig.call("summariser", "summary") == "claude" and rig.call("identity", "review") == "claude"      # helpers keep the policy


def test_a_file_that_is_not_ours_is_ignored_and_the_run_goes_on(rig):
    AgentPicksCapability().install(rig.ctx)
    rig.file.write_text("{not json", encoding="utf-8")
    assert rig.call() == "claude"
    rig.file.write_text(json.dumps({"schema": "agent-choices/9", "agents": {}}), encoding="utf-8")
    assert rig.call() == "claude"
    rig.choose(identity=Pick(provider="codex"))                                    # a good file later is used again
    assert rig.call() == "codex"


def test_a_pick_for_a_provider_that_cannot_run_answers_by_policy_with_the_note(rig):
    rig.codex.probe_auth = lambda: AuthStatus(provider="codex", installed=True, signed_in=False, billing="subscription", checked_at=0.0)
    AgentPicksCapability().install(rig.ctx)
    rig.choose(identity=Pick(provider="codex", model="gpt-5.6-luna", effort="low"))
    result = rig.port.complete(CompletionRequest(system="s", user="u", tag=CallTag(function="identity")))
    assert result.note == "your choice for identity (codex) could not run: not signed in; claude answered"
    assert rig.claude.got == [{"model": "sonnet", "effort": "high"}]


def test_the_router_is_found_through_the_port_llm_was_configured_with(rig):
    context = SimpleNamespace(paths=SimpleNamespace(run_dir=rig.run_dir), data_dir=rig.run_dir)         # no port of its own, as the host's context has none
    llm.configure(rig.port, mock=False)
    try:
        AgentPicksCapability().install(context)
    finally:
        llm.configure()
    assert rig.router.agent_pick is not None


def test_in_mock_mode_there_is_no_router_and_install_does_nothing(tmp_path):
    context = SimpleNamespace(port=llm.ScriptedPort(), paths=SimpleNamespace(run_dir=tmp_path), data_dir=tmp_path)
    AgentPicksCapability().install(context)                                       # must not raise
    context = SimpleNamespace(paths=None, data_dir=tmp_path)
    AgentPicksCapability().install(context)


def test_the_capability_adds_nothing_to_a_calls_tag_or_text(rig):
    cap = AgentPicksCapability()
    assert cap.name == "agent-picks" and cap.outputs() == {} and cap.tag(CallTag(function="identity"), rig.ctx) == {}
    assert cap.addendum("identity", rig.ctx) == "" and cap.select("a brief", rig.ctx) is None
