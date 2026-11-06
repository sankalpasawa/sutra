"""ChatPort over the Router (work package ABS-1; absorb design 2.2). Stub connectors under real names: no process starts."""
from __future__ import annotations

import sys

import pytest

from sutra_app.connectors.chat_models import ChatEvent, ChatTurnIn
from sutra_app.connectors.chat_port import ChatPort, RouterChatPort
from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.connectors.models import AuthStatus, ConnectorConfig, Message
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink, load_session_state

from test_router_chat import History, Named, policy

A, B = "cs_port_a", "cs_port_b"


class KeyBilled(Named):
    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=True, billing="api_key", checked_at=self._clock())


class SignedOut(Named):
    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=False, billing="subscription", checked_at=self._clock())


def make(tmp_path, codex=Named):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
    history = History()
    claude, other = Named("claude", cfg), codex("codex", cfg)
    router = Router({"claude": claude, "codex": other}, policy(), usage_sink=MemoryUsageSink(), transcripts=history,
                    sleep=lambda s: None, rng=lambda: 0.0)
    return RouterChatPort(router), router, history, cfg, claude, other


def test_it_is_a_chat_port(tmp_path):
    assert isinstance(make(tmp_path)[0], ChatPort)


def test_both_providers_are_offered_ready_when_they_can_run(tmp_path):
    port = make(tmp_path)[0]
    pills = port.providers(A)
    assert [(p.name, p.ready, p.why_not) for p in pills] == [("claude", True, ""), ("codex", True, "")]
    assert pills[0].model == "sonnet" and not any(p.chosen for p in pills)


def test_a_provider_that_cannot_run_is_offered_with_its_reason(tmp_path):
    pills = {p.name: p for p in make(tmp_path, SignedOut)[0].providers()}
    assert pills["claude"].ready and not pills["codex"].ready and pills["codex"].why_not == "not signed in"


def test_an_api_key_provider_is_refused_and_cannot_be_chosen(tmp_path):
    port = make(tmp_path, KeyBilled)[0]
    pill = next(p for p in port.providers() if p.name == "codex")
    assert not pill.ready and "API" in pill.why_not.upper()
    with pytest.raises(InvalidRequestError):
        port.choose(A, "codex")


def test_the_pill_carries_the_last_quota_snapshot_with_every_window(tmp_path):
    """GAP-providers: the pill shows the fullest window of a ready provider, so the snapshot rides along."""
    from sutra_app.connectors.models import Quota, QuotaWindow
    port, router = make(tmp_path)[:2]
    router.health.set_quota("claude", Quota(status="ok", source="rate_limit_event", windows=[QuotaWindow(key="five_hour", label="5-hour", used=0.62)]))
    pills = {p.name: p for p in port.providers()}
    assert [(w.label, w.used) for w in pills["claude"].quota.windows] == [("5-hour", 0.62)] and pills["codex"].quota is None
    assert pills["claude"].model_dump(mode="json")["quota"]["windows"][0]["key"] == "five_hour"


def test_a_disabled_provider_says_why(tmp_path):
    port, router = make(tmp_path)[:2]
    router.policy.providers["codex"].enabled = False
    assert next(p for p in port.providers() if p.name == "codex").why_not == "disabled in the routing policy"


def test_choosing_for_one_session_leaves_the_policy_and_the_other_session_alone(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    before = list(router.policy.resolve(__import__("sutra_app.connectors.models", fromlist=["AskRequest"]).AskRequest(user="x")).order)
    choice = port.choose(A, "codex")
    assert choice.provider == "codex"
    port.send(A, ChatTurnIn(text="hello"))
    port.send(B, ChatTurnIn(text="hello"))
    assert len(codex.calls) == 1 and len(claude.calls) == 1
    assert load_session_state(cfg.resolved_work_root() / A).provider == "codex"
    assert load_session_state(cfg.resolved_work_root() / B).provider == "claude"
    assert list(router.policy.resolve(__import__("sutra_app.connectors.models", fromlist=["AskRequest"]).AskRequest(user="x")).order) == before
    assert next(p for p in port.providers(A) if p.name == "codex").chosen
    assert not any(p.chosen for p in port.providers(B))


def test_clearing_the_choice_restores_the_policy(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.choose(A, "codex")
    port.choose(A, None)
    port.send(A, ChatTurnIn(text="hello"))
    assert len(claude.calls) == 1 and not codex.calls


def test_choosing_an_unknown_provider_is_refused(tmp_path):
    with pytest.raises(InvalidRequestError):
        make(tmp_path)[0].choose(A, "gemini")


def test_plan_switch_starts_no_process_and_writes_nothing(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    history.messages_list = [Message(role="user", text="one"), Message(role="assistant", text="two")]
    plan = port.plan_switch(A, "codex")
    assert (plan.tier, plan.kept_messages, plan.omitted, plan.target) == ("full", 2, 0, "codex") and plan.chars > 0
    assert not claude.calls and not codex.calls
    assert load_session_state(cfg.resolved_work_root() / A) is None


def test_plan_switch_of_an_empty_chat_carries_nothing(tmp_path):
    assert make(tmp_path)[0].plan_switch(A, "codex").tier == "none"


def test_plan_switch_digest_tier_when_the_chat_is_long(tmp_path):
    port, router, history, *_ = make(tmp_path)
    history.messages_list = [Message(role="user" if i % 2 == 0 else "assistant", text="x" * 2000) for i in range(60)]
    plan = port.plan_switch(A, "codex")
    assert plan.tier == "digest" and plan.kept_messages == 40 and plan.omitted == 20


def test_a_stream_yields_partials_and_ends_with_turn_done(tmp_path):
    port = make(tmp_path)[0]
    events = list(port.stream(A, ChatTurnIn(text="hello")))
    kinds = [e.kind for e in events]
    assert kinds[-1] == "turn_done" and kinds.count("turn_done") == 1 and "usage" in kinds
    assert "".join(e.data["delta"] for e in events if e.kind == "partial") == events[-1].data["text"]


def test_send_returns_the_turn_and_reports_a_switch(tmp_path):
    port, router, history, *_ = make(tmp_path)
    port.send(A, ChatTurnIn(text="one"))
    history.messages_list = [Message(role="user", text="one"), Message(role="assistant", text="[stub] one")]
    port.choose(A, "codex")
    seen: list[ChatEvent] = []
    out = port.send(A, ChatTurnIn(text="two"), on_event=seen.append)
    assert out.switched["from"] == "claude" and out.switched["to"] == "codex"
    assert [e.kind for e in seen if e.kind == "switched"] == ["switched"]


def test_two_sessions_never_share_history_or_workdir(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.send(A, ChatTurnIn(text="secret-alpha"))
    port.send(B, ChatTurnIn(text="hello"))
    assert all("secret-alpha" not in c.prompt for c in claude.calls if c.session_id != claude.calls[0].session_id)
    assert (cfg.resolved_work_root() / A) != (cfg.resolved_work_root() / B)
    assert load_session_state(cfg.resolved_work_root() / A).provider_session_id != load_session_state(cfg.resolved_work_root() / B).provider_session_id
    assert [asked for asked, _ in history.asked] == [A, B]       # each send read only its own session's transcript


def test_attachments_are_refused_until_a_delivery_exists(tmp_path):
    from sutra_app.connectors.chat_models import AttachmentRef
    ref = AttachmentRef(id="0" * 64, name="a.png", kind="image", size=1)
    with pytest.raises(InvalidRequestError):
        make(tmp_path)[0].send(A, ChatTurnIn(text="x", attachments=[ref]))


def test_a_bad_session_id_is_refused(tmp_path):
    with pytest.raises(InvalidRequestError):
        make(tmp_path)[0].plan_switch("../x", "codex")


def test_a_model_choice_is_applied_to_a_chat_that_already_has_a_session_or_refused_never_dropped(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.send(A, ChatTurnIn(text="hello"))                                      # claude now has a session.json
    assert port.choose(A, "claude", "opus").model == "opus"
    assert load_session_state(cfg.resolved_work_root() / A).model == "opus"
    with pytest.raises(InvalidRequestError):
        port.choose(A, "codex", "gpt-x")                                        # a switch would not use it
    with pytest.raises(InvalidRequestError):
        port.choose(B, None, "opus")                                            # a model needs its provider
    assert load_session_state(cfg.resolved_work_root() / A).provider == "claude"
