"""AsyncConnector: the orchestrator's ConnectorPort over the Router (connectors design 3.10, ORCH 3.5, S1-contracts-07,
S4-fnodes-07, work package CN-7). Providers are stub connectors; a `Spy` records what the router handed the connector."""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import threading
from pathlib import Path

import pytest

from sutra_app.connectors.errors import ConnectorError, InvalidJsonError, InvalidRequestError, NoProviderError, QuotaError
from sutra_app.connectors.models import AuthStatus, ConnectorConfig, JsonResult, TurnResult, Usage
from sutra_app.connectors.orchestrator_port import AsyncConnector, build_tag
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import CallTag

ORG = {"purpose": "chat_plan", "session_id": "cs_org", "node_id": "root"}


def policy():
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2}},
                         "defaults": {"order": ["claude", "codex"], "max_attempts": 2, "retry_delays_s": [2, 5]},
                         "rules": [{"match": {"function": "chat_agent"}, "timeout_s": 120}], "rates": {}})


class Spy(StubConnector):
    """A stub named claude/codex that remembers how the router called it."""

    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name
        self.seen = []

    def resolve_model(self, requested):
        return requested or "scripted"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, version="9.9", signed_in=True, method="claude.ai", billing="subscription",
                          plan="max", account="me@example.com", detail="ok", checked_at=self._clock())

    def call_json_result(self, prompt, tools=(), schema=None, timeout=900, **kw):
        self.seen.append({"prompt": prompt, "tools": tools, "schema": schema, "timeout": timeout, "ctx": kw.get("ctx"),
                          "thread": threading.current_thread().name})
        return super().call_json_result(prompt, tools, schema, timeout, **kw)


class Rig:
    def __init__(self, tmp_path, sink=True):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Spy("claude", cfg), Spy("codex", cfg)
        self.sink = MemoryUsageSink() if sink else None
        self.router = Router({"claude": self.claude, "codex": self.codex}, policy(), usage_sink=self.sink, sleep=lambda s: None)
        self.port = AsyncConnector(self.router)

    def call(self, prompt="plan it", **kw):
        return asyncio.run(self.port.call_json(prompt, **kw))


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_call_json_signature_matches_the_orchestrators_port():
    sig = inspect.signature(AsyncConnector.call_json)
    assert inspect.iscoroutinefunction(AsyncConnector.call_json)
    params = sig.parameters
    assert list(params) == ["self", "prompt", "schema", "tools", "timeout", "function", "step", "context"]
    assert all(params[n].kind is inspect.Parameter.KEYWORD_ONLY for n in list(params)[2:])
    assert [params[n].default for n in list(params)[2:]] == [None, (), 120.0, "chat_agent", "plan", None]


def test_call_json_returns_the_object_the_usd_and_how(rig):
    value, usd, how = rig.call(schema={"type": "object", "properties": {"intent": {"type": "string"}}, "required": ["intent"]})
    assert value == {"intent": "stub"} and usd == 0.0 and how == "stub"


def test_the_tag_is_built_from_the_arguments_never_from_the_string_step(rig):
    rig.call(function="chat_agent", step="decide", context=ORG)
    ctx = rig.claude.seen[0]["ctx"]
    assert ctx.tag == CallTag(function="chat_agent", stage="decide", purpose="chat_plan")
    assert (ctx.session_id, ctx.node_id) == ("cs_org", "root") and ctx.tag.step == 0 and ctx.tag.atom is None


def test_atom_id_in_the_context_becomes_tag_atom_and_the_row_atom_id(rig):
    key = "overhead-req-17"
    rig.call(function="chat_agent", step="decide", context={**ORG, "atom_id": key})
    ctx = rig.claude.seen[0]["ctx"]
    assert ctx.tag.atom == key and ctx.tag.step == 0 and ctx.tag.stage == "decide"
    row, = rig.sink.rows
    assert row.atom_id == key and row.purpose == "chat_plan" and row.session_id == "cs_org" and row.node_id == "root"
    assert row.fn == "chat_agent" and row.step is None


def test_task_id_becomes_the_tag_task_id(rig):
    rig.call(context={"task_id": "tsk_abc", "purpose": "plan"})
    assert rig.claude.seen[0]["ctx"].tag.task_id == "tsk_abc" and rig.sink.rows[0].task_id == "tsk_abc"


def test_no_context_means_the_defaults_and_unknown_keys_are_ignored(rig):
    rig.call(context={"colour": "red"})
    tag = rig.claude.seen[0]["ctx"].tag
    assert tag == CallTag(function="chat_agent", stage="plan") and rig.claude.seen[0]["ctx"].session_id is None
    assert rig.sink.rows[0].atom_id is None


def test_a_bad_purpose_is_an_invalid_request(rig):
    with pytest.raises(InvalidRequestError, match="purpose") as e:
        rig.call(context={"purpose": "Not A Purpose!"})
    assert e.value.kind == "bad_output" and rig.claude.seen == []


def test_build_tag_directly():
    assert build_tag("audit", None, None) == CallTag(function="audit")
    assert build_tag("audit", "", {"atom_id": ""}) == CallTag(function="audit")


def test_timeout_and_tools_and_schema_reach_the_connector(rig):
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    rig.call(function="identity", timeout=30, schema=schema)
    seen = rig.claude.seen[0]
    assert seen["timeout"] == 30.0 and seen["schema"] == schema and seen["tools"] == ()


def test_the_policy_rule_for_the_chat_agent_wins_over_the_callers_timeout(rig):
    rig.call(function="chat_agent", timeout=600)
    assert rig.claude.seen[0]["timeout"] == 120.0


def test_tools_ask_for_a_provider_that_has_them(rig):
    with pytest.raises(NoProviderError) as e:
        rig.call(tools=("sutra",))
    assert e.value.kind == "unavailable"


def test_the_call_runs_off_the_event_loop_thread(rig):
    rig.call()
    assert rig.claude.seen[0]["thread"] != threading.main_thread().name


def test_a_non_object_value_is_an_invalid_json_error(rig, monkeypatch):
    turn = TurnResult(text="[1]", provider="claude", model="m", provider_session_id=None, usage=Usage(), usd=None, usd_basis="none",
                      duration_ms=1)
    monkeypatch.setattr(rig.router, "call_json", lambda req: JsonResult(value=[1], usd=None, how="native", turn=turn, calls_made=1, usd_spent=0))
    with pytest.raises(InvalidJsonError, match="not an object"):
        rig.call()


@pytest.mark.parametrize("code, kind", [("quota", "quota"), ("not_signed_in", "auth"), ("timeout", "timeout"),
                                        ("overloaded", "unavailable"), ("empty_reply", "bad_output"), ("account_blocked", "auth")])
def test_errors_carry_the_kind_the_orchestrator_reads(rig, code, kind):
    rig.claude.fail_next(code, 4)
    rig.codex.fail_next(code, 4)
    with pytest.raises(ConnectorError) as e:
        rig.call()
    assert e.value.code == code and e.value.kind == kind


def test_a_fallback_still_answers_the_chat_agent(rig):
    rig.claude.fail_next("quota")
    value, usd, how = rig.call()
    assert value == {} and rig.codex.seen and rig.sink.rows[0].provider == "codex"


def test_records_usage_follows_the_sink(tmp_path):
    assert Rig(tmp_path / "a", sink=True).port.records_usage is True
    assert Rig(tmp_path / "b", sink=False).port.records_usage is False


def test_each_call_writes_exactly_one_row(rig):
    rig.call(context=ORG)
    rig.claude.fail_next("overloaded", 2)
    rig.call(context=ORG)
    assert len(rig.sink.rows) == 2 and rig.sink.rows[1].provider == "codex" and rig.sink.rows[1].ok


def test_status_is_a_per_provider_view(rig):
    status = rig.port.status()
    assert list(status) == ["claude", "codex"]
    claude = status["claude"]
    assert (claude["installed"], claude["signed_in"], claude["detail"]) == (True, True, "ok")
    assert (claude["method"], claude["billing"], claude["plan"], claude["version"]) == ("claude.ai", "subscription", "max", "9.9")
    assert claude["health"] == {"state": "ok", "until": None, "reason": None} and claude["quota"] is None
    assert claude["plan_label"] == "Claude Max"
    assert "account" not in claude


def test_status_has_the_shape_the_settings_page_reads(rig):
    """GET /api/health carries this view; settings_view.js and tests/ui/fixtures/health.json read `health` as {state, until, reason}.
    A bare string made the chip fall back to Ready for a provider out of quota (GAP-providers)."""
    fixture = json.loads((Path(__file__).resolve().parents[1] / "ui" / "fixtures" / "health.json").read_text(encoding="utf-8"))
    status = rig.port.status()
    for name, page_row in fixture["connectors"].items():
        assert set(page_row) <= set(status[name]), name
        assert isinstance(status[name]["health"], dict) and set(status[name]["health"]) == set(page_row["health"]), name


def test_status_reports_a_provider_in_cooldown_and_a_missing_cli(tmp_path):
    rig = Rig(tmp_path)
    rig.router.health.failed("claude", QuotaError("limit", provider="claude", resets_at=4_000_000_000.0))
    rig.router._connectors["codex"].cfg = rig.router._connectors["codex"].cfg.model_copy(update={"codex_exe": "/nonexistent/codex"})
    status = rig.port.status()
    assert status["claude"]["health"] == {"state": "quota", "until": 4_000_000_000.0, "reason": "usage limit reached"}
    assert status["codex"]["installed"] is False and status["codex"]["signed_in"] is None
