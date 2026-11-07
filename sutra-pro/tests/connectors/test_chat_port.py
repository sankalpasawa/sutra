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


# ---- the system text of a session (GAP-model-quality: the grounding of a direct chat) -------------------------------------------------

def test_set_system_writes_a_private_file_that_the_next_turn_reads_and_replaces_or_removes_it(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.set_system(A, "You answer in the chat of the team Web.")
    path = cfg.resolved_work_root() / A / "system.txt"
    assert path.read_text() == "You answer in the chat of the team Web."
    assert sys.platform == "win32" or (path.stat().st_mode & 0o777) == 0o600          # Windows has no POSIX modes
    port.send(A, ChatTurnIn(text="one"))
    assert claude.calls[-1].system == "You answer in the chat of the team Web."
    port.set_system(A, "The record changed.")
    port.send(A, ChatTurnIn(text="two"))                                        # the same provider session reads the new text
    assert claude.calls[-1].system == "The record changed." and len({c.session_id for c in claude.calls}) == 1
    assert [p.name for p in path.parent.iterdir() if p.name.startswith(".system")] == []          # no temp file is left
    port.set_system(A, "")
    assert not path.exists()
    port.send(A, ChatTurnIn(text="three"))
    assert claude.calls[-1].system == ""
    with pytest.raises(InvalidRequestError):
        port.set_system("../x", "nope")


def test_the_system_text_of_one_session_is_never_another_sessions(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.set_system(A, "team A record")
    port.set_system(B, "team B record")
    port.send(A, ChatTurnIn(text="x"))
    port.send(B, ChatTurnIn(text="y"))
    assert sorted(c.system for c in claude.calls) == ["team A record", "team B record"]
    assert (cfg.resolved_work_root() / A / "system.txt").read_text() == "team A record"


def test_the_system_text_survives_a_switch_to_codex(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.set_system(A, "grounded")
    port.send(A, ChatTurnIn(text="one"))
    claude.fail_next("quota")
    port.send(A, ChatTurnIn(text="two"))
    assert load_session_state(cfg.resolved_work_root() / A).provider == "codex" and codex.calls[-1].system == "grounded"


def test_the_real_claude_gets_the_system_text_on_argv_and_codex_in_front_of_its_first_prompt(fake, tmp_path):
    from sutra_app.connectors.claude import ClaudeConnector
    from sutra_app.connectors.codex import CodexConnector

    grounding = 'You are answering in the chat of the team "Web". What the team is for: Websites.'
    fake.sequence("ok_plain", "quota", cli="claude").reply(text="the reply")
    fake.sequence("ok_plain", cli="codex").reply(text="codex reply")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = Router({"claude": ClaudeConnector(cfg), "codex": CodexConnector(cfg)}, policy(), transcripts=History(), sleep=lambda s: None)
    port = RouterChatPort(router)
    port.set_system("cs_real", grounding)
    port.send("cs_real", ChatTurnIn(text="first"))
    argv = fake.model_calls("claude")[0]["argv"]
    assert argv[argv.index("--system-prompt") + 1] == grounding
    port.send("cs_real", ChatTurnIn(text="second"))                           # claude is out of quota: a new codex thread
    router.drain()
    assert fake.model_calls("codex")[0]["stdin"].startswith("<system>\n" + grounding + "\n</system>")


# ---- the model picker: names and notes, a model the provider does not offer refused when chosen, an effort per chat (welcome-settings, item 4) ------------

class CodexListing(Named):
    """A Codex that lists two models, one of which takes only two efforts (what `codex debug models` would say)."""

    def models(self):
        from sutra_app.connectors.models import ModelInfo
        return [ModelInfo(slug="gpt-wide", label="GPT Wide", efforts=["low", "medium", "high"], context_window=258_400, images=False, listed=True),
                ModelInfo(slug="gpt-slim", label="GPT Slim", efforts=["low", "medium"], context_window=258_400, images=False, listed=True)]


def test_the_pill_carries_the_model_list_with_notes_and_a_more_fold(tmp_path):
    pills = {p.name: p for p in make(tmp_path, CodexListing)[0].providers(A)}
    claude = pills["claude"].model_options
    assert [o.slug for o in claude[:4]] == ["best", "opus", "sonnet", "haiku"] and claude[0].group == "main" and claude[-1].group == "more"
    assert all(o.note for o in claude) and any(o.slug == "opus[1m]" and o.group == "more" for o in claude)
    assert [(o.slug, o.label, o.efforts) for o in pills["codex"].model_options] == [
        ("gpt-wide", "GPT Wide", ["low", "medium", "high"]), ("gpt-slim", "GPT Slim", ["low", "medium"])]
    assert pills["claude"].model_dump(mode="json")["model_options"][0] == {
        "slug": "best", "label": "Best available", "note": "the newest model this account can run", "group": "main",
        "efforts": ["low", "medium", "high", "xhigh", "max"], "context_window": 1_000_000}


def test_a_model_the_provider_does_not_offer_is_refused_with_the_list_and_nothing_is_stored(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    with pytest.raises(InvalidRequestError) as caught:
        port.choose(A, "claude", "opuss")                                          # a typo
    assert "opuss is not a model claude offers" in str(caught.value) and "best, opus, sonnet, haiku" in str(caught.value)
    assert load_session_state(cfg.resolved_work_root() / A) is None                # no session was started, nothing pinned
    assert router._pins.get(A) is None
    port.send(A, ChatTurnIn(text="hello"))
    with pytest.raises(InvalidRequestError):
        port.choose(A, "claude", "gpt-5")                                          # another provider's name
    assert load_session_state(cfg.resolved_work_root() / A).model != "gpt-5"


def test_a_codex_model_is_checked_against_what_codex_lists(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path, CodexListing)
    assert port.choose(B, "codex", "gpt-slim").model == "gpt-slim"
    with pytest.raises(InvalidRequestError) as caught:
        port.choose(B, "codex", "gpt-slimm")
    assert "gpt-wide, gpt-slim" in str(caught.value)
    assert load_session_state(cfg.resolved_work_root() / B).model == "gpt-slim"


def test_a_choice_picks_the_model_and_the_effort_of_a_new_chat_and_leaves_the_policy_alone(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    choice = port.choose(A, "claude", "haiku", "max")
    assert (choice.provider, choice.model, choice.effort) == ("claude", "haiku", "max")
    stored = load_session_state(cfg.resolved_work_root() / A)
    assert (stored.model, stored.effort) == ("haiku", "max")
    assert router.policy.model_for("claude") == "sonnet" and router.policy.model_for("codex") == policy().model_for("codex")      # the default is untouched
    pill = next(p for p in port.providers(A) if p.name == "claude")
    assert (pill.chat_model, pill.chat_effort, pill.can_pick) == ("haiku", "max", True)
    other = next(p for p in port.providers(A) if p.name == "codex")
    assert (other.chat_model, other.chat_effort, other.can_pick) == (None, None, False)      # the session runs on claude: a codex model waits for the switch


def test_an_effort_is_written_to_the_stored_session_and_the_next_turn_runs_on_it(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.send(A, ChatTurnIn(text="one"))
    assert load_session_state(cfg.resolved_work_root() / A).effort == "high"                     # the policy's text effort until the owner picks one
    choice = port.choose(A, "claude", None, "xhigh")                               # an effort alone keeps the model
    assert (choice.model, choice.effort) == (load_session_state(cfg.resolved_work_root() / A).model, "xhigh")
    port.send(A, ChatTurnIn(text="two"))
    assert load_session_state(cfg.resolved_work_root() / A).effort == "xhigh"
    assert load_session_state(cfg.resolved_work_root() / A).turns == 2          # base.chat_turn reads the effort of the stored state on every turn (base.py `effort=s.effort`)


def test_an_effort_the_model_does_not_accept_is_refused_with_the_valid_ones(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path, CodexListing)
    with pytest.raises(InvalidRequestError) as caught:
        port.choose(A, "codex", "gpt-slim", "max")
    assert "does not accept the effort max" in str(caught.value) and "low, medium" in str(caught.value)
    assert load_session_state(cfg.resolved_work_root() / A) is None
    assert port.choose(A, "codex", "gpt-wide", "high").effort == "high"
    with pytest.raises(InvalidRequestError):
        port.choose(A, "codex", None, "max")                                       # the chat's model, gpt-wide, takes only three
    with pytest.raises(InvalidRequestError):
        port.choose(B, None, None, "low")                                          # an effort needs its provider too
    with pytest.raises(InvalidRequestError):
        port.choose(A, "claude", None, "low")                                      # the session runs on codex: choose the provider first
