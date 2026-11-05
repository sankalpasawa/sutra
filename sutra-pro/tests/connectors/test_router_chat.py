"""Router chat sessions: ids and usage across turns, the carry-over on a switch, a lost session, busy, pin, stop
(connectors design 3.6 "Chat sessions", 5.2, 5.3, S1-contracts-08, work package CN-7). Most tests use `Named` stub connectors
(no process); the last ones run the real connectors against the fake CLIs."""
from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import CallCancelledError, InvalidRequestError, NoProviderError, SessionLostError
from sutra_app.connectors.models import AuthStatus, ConnectorConfig, Message, RouteContext, SessionSpec
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import NEW_MESSAGE_LABEL, Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink, load_session_state

SID = "cs_chat1"


def policy(**defaults):
    base = {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
            "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
            "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": "read-only"}},
                         "defaults": base, "rules": [{"match": {"function": "chat_agent"}, "timeout_s": 120}], "rates": {}})


class Named(StubConnector):
    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name

    def resolve_model(self, requested):
        return requested or "scripted"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=True, billing="subscription", checked_at=self._clock())


class History:
    """The TranscriptSource: whatever the test says the stored conversation is."""

    def __init__(self):
        self.messages_list, self.asked = [], []

    def messages(self, session_id, limit=20):
        self.asked.append((session_id, limit))
        return list(self.messages_list)


class Rig:
    def __init__(self, tmp_path, **kw):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.cfg = cfg
        self.claude, self.codex = Named("claude", cfg), Named("codex", cfg)
        self.history, self.sink, self.events, self.hooks = History(), MemoryUsageSink(), [], []
        self.router = Router({"claude": self.claude, "codex": self.codex}, policy(), usage_sink=self.sink, transcripts=self.history,
                             events=lambda t, d: self.events.append((t, d)), session_hook=lambda *a: self.hooks.append(a),
                             sleep=lambda s: None, rng=lambda: 0.0, **kw)

    def send(self, text="hello", **kw):
        return self.router.chat_send(SID, Message(role="user", text=text), RouteContext(), **kw)

    def state(self):
        return load_session_state(self.cfg.resolved_work_root() / SID)

    def switches(self):
        return [d for t, d in self.events if t == "connector.switch"]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_chat_start_uses_the_first_provider_of_the_plan_and_writes_session_json(rig):
    state = rig.router.chat_start(SessionSpec(session_id=SID, system="You are the org chat."), RouteContext())
    assert (state.provider, state.model, state.effort, state.provider_session_id, state.turns) == ("claude", "sonnet", "high", None, 0)
    assert rig.state() == state and rig.claude.calls == []
    assert (rig.cfg.resolved_work_root() / SID / "system.txt").read_text() == "You are the org chat."


def test_chat_start_honours_a_requested_provider_and_refuses_an_unusable_one(rig):
    assert rig.router.chat_start(SessionSpec(session_id=SID, provider="codex"), RouteContext()).provider == "codex"
    rig.router.policy.providers["codex"].enabled = False
    with pytest.raises(NoProviderError):
        rig.router.chat_start(SessionSpec(session_id="cs_b", provider="codex"), RouteContext())


def test_three_turns_keep_the_provider_session_and_sum_the_usage(rig):
    rig.router.chat_start(SessionSpec(session_id=SID), RouteContext())
    for text in ("one", "two", "three"):
        rig.send(text)
    state = rig.state()
    assert state.turns == 3 and state.switches == 0 and state.provider == "claude" and state.provider_session_id
    assert len({c.session_id for c in rig.claude.calls}) == 1 and [c.prompt for c in rig.claude.calls] == ["one", "two", "three"]
    assert len(rig.sink.rows) == 3
    assert state.cum_usage.total == sum((r.tokens_in or 0) + (r.tokens_out or 0) for r in rig.sink.rows) > 0
    assert rig.hooks == [(SID, "claude", "sonnet", state.provider_session_id)]          # told once, when the id appeared
    assert rig.switches() == []


def test_a_chat_row_is_how_chat_purpose_chat_with_the_session(rig):
    rig.send()
    row, = rig.sink.rows
    assert (row.how, row.purpose, row.session_id, row.provider, row.ok) == ("chat", "chat", SID, "claude", True)
    assert row.call_ref.startswith("r:")


def test_without_a_session_file_the_first_send_creates_one(rig):
    rig.send()
    assert rig.state().provider == "claude" and rig.state().turns == 1


def test_a_brand_new_conversation_sends_the_bare_message(rig):
    rig.send("hello")
    assert rig.claude.calls[0].prompt == "hello" and rig.history.asked == [(SID, 20)]


def test_history_that_already_exists_is_carried_into_the_first_prompt(rig):
    rig.history.messages_list = [Message(role="user", text="earlier question"), Message(role="assistant", text="earlier answer"),
                                 Message(role="user", text="hello")]               # the owner's message is stored before the call
    rig.send("hello")
    prompt = rig.claude.calls[0].prompt
    assert prompt.startswith("Earlier messages of this conversation, carried over because the provider changed:")
    assert "User: earlier question\nAssistant: earlier answer" in prompt and "User: hello" not in prompt
    assert prompt.endswith(f"\n\n{NEW_MESSAGE_LABEL}\nhello")


def test_a_quota_switch_carries_the_transcript_to_the_other_provider(rig):
    rig.send("one")
    rig.send("two")
    rig.history.messages_list = [Message(role="user", text="one"), Message(role="assistant", text="[stub] one"),
                                 Message(role="user", text="two"), Message(role="assistant", text="[stub] two"), Message(role="user", text="three")]
    forgotten = []
    rig.claude.forget = lambda s: forgotten.append(s.provider)
    old_id = rig.state().provider_session_id
    rig.claude.fail_next("quota")
    rig.send("three")
    rig.router.drain()
    prompt = rig.codex.calls[0].prompt
    assert prompt.startswith("Earlier messages of this conversation, carried over because the provider changed (claude → codex):")
    assert "User: one\nAssistant: [stub] one\nUser: two\nAssistant: [stub] two" in prompt and prompt.endswith(f"{NEW_MESSAGE_LABEL}\nthree")
    state = rig.state()
    assert (state.provider, state.model, state.switches, state.turns) == ("codex", "gpt-5.6-luna", 1, 3)
    assert rig.hooks[-1] == (SID, "codex", "gpt-5.6-luna", state.provider_session_id)
    assert rig.switches() == [{"session_id": SID, "from": "claude", "to": "codex", "reason": "out of quota"}]
    assert forgotten == ["claude"] and old_id
    row = rig.sink.rows[-1]
    assert row.provider == "codex" and row.how == "chat" and row.detail["note"] == "claude out of quota, answered by codex"
    assert len(rig.sink.rows) == 3


def test_the_next_turn_stays_on_the_new_provider_while_the_old_one_is_in_cooldown(rig):
    rig.send("one")
    rig.claude.fail_next("quota")
    rig.send("two")
    rig.send("three")
    assert [c.prompt for c in rig.codex.calls][-1] == "three"                 # resumed: no carry-over, no second switch
    assert rig.state().switches == 1 and len(rig.switches()) == 1


def test_when_the_policy_provider_is_back_the_session_switches_back_with_a_carry_over(rig):
    rig.send("one")
    rig.claude.fail_next("quota")
    rig.send("two")
    rig.router.health.ok("claude")
    rig.history.messages_list = [Message(role="user", text="one"), Message(role="assistant", text="a")]
    rig.send("three")
    assert rig.state().provider == "claude" and rig.state().switches == 2
    assert rig.switches()[-1] == {"session_id": SID, "from": "codex", "to": "claude", "reason": "policy"}
    assert "claude" in rig.claude.calls[-1].prompt.split("\n")[0] and "codex → claude" in rig.claude.calls[-1].prompt


def test_the_system_text_survives_a_switch(rig):
    rig.router.chat_start(SessionSpec(session_id=SID, system="You are the org chat."), RouteContext())
    rig.send("one")
    rig.claude.fail_next("quota")
    rig.send("two")
    assert rig.codex.calls[0].system == "You are the org chat."


def test_a_lost_session_restarts_on_the_same_provider_with_the_carry_over(rig):
    rig.send("one")
    rig.history.messages_list = [Message(role="user", text="one"), Message(role="assistant", text="[stub] one")]
    rig.claude.fail_next("session_lost")
    rig.send("two")
    assert rig.state().provider == "claude" and rig.state().switches == 1 and rig.state().turns == 2
    prompt = rig.claude.calls[-1].prompt
    assert "because the provider session was lost (claude)" in prompt and "User: one" in prompt and prompt.endswith("two")
    assert rig.switches() == [{"session_id": SID, "from": "claude", "to": "claude", "reason": "session lost"}]
    row = rig.sink.rows[-1]
    assert [a["code"] for a in row.detail["attempts"]] == ["session_lost", "ok"] and len(rig.sink.rows) == 2
    assert rig.hooks[-1][0] == SID and len(rig.hooks) == 2


def test_a_session_lost_twice_is_an_error(rig):
    rig.send("one")
    rig.claude.fail_next("session_lost", 2)
    with pytest.raises(SessionLostError):
        rig.send("two")
    assert rig.sink.rows[-1].ok is False and rig.codex.calls == []


def test_a_deleted_session_file_means_a_new_provider_session_with_the_carry_over(rig):
    rig.send("one")
    (rig.cfg.resolved_work_root() / SID / "session.json").unlink()
    rig.history.messages_list = [Message(role="user", text="one"), Message(role="assistant", text="[stub] one")]
    rig.send("two")
    assert "User: one" in rig.claude.calls[-1].prompt and rig.state().turns == 1
    assert rig.hooks[-1][0] == SID


def test_a_second_send_while_a_turn_runs_is_refused_and_writes_no_row(rig):
    started, release = threading.Event(), threading.Event()
    rig.claude.book.set("*", "*", lambda: (started.set(), release.wait(10), "slow reply")[2])
    worker = threading.Thread(target=rig.send, args=("first",), daemon=True)
    worker.start()
    assert started.wait(5)
    with pytest.raises(InvalidRequestError, match="already running a turn") as e:
        rig.send("second")
    assert e.value.detail == {"busy": True}
    release.set()
    worker.join(5)
    assert len(rig.sink.rows) == 1
    assert rig.send("third").text                                                  # the session is free again


def test_a_failed_turn_frees_the_session_too(rig):
    rig.claude.fail_next("invalid_request")
    with pytest.raises(InvalidRequestError):
        rig.send("x")
    assert rig.send("y").text and rig.sink.rows[0].ok is False


def test_pin_sends_the_next_turn_to_that_provider_and_unpin_releases_it(rig):
    rig.send("one")
    rig.router.chat_pin(SID, "codex")
    assert rig.state().pinned == "codex"
    rig.send("two")
    assert rig.state().provider == "codex" and rig.switches()[-1]["reason"] == "pinned"
    rig.router.chat_pin(SID, None)
    assert rig.state().pinned is None
    rig.send("three")
    assert rig.state().provider == "claude" and rig.switches()[-1]["reason"] == "policy"


def test_a_pin_set_before_the_session_exists_applies_to_its_first_turn(rig):
    rig.router.chat_pin(SID, "codex")
    rig.send("one")
    assert rig.state().provider == "codex" and rig.state().pinned == "codex" and rig.claude.calls == []


def test_pin_refuses_a_provider_that_is_not_configured(rig):
    with pytest.raises(InvalidRequestError, match="not a configured provider"):
        rig.router.chat_pin(SID, "gemini")


def test_a_session_id_that_names_a_path_is_refused(rig):
    for bad in ("../etc", "a/b", "", "x" * 65):
        with pytest.raises(InvalidRequestError, match="names a directory"):
            rig.router.chat_send(bad, Message(role="user", text="x"))
    assert rig.sink.rows == []


def test_only_a_user_message_is_sent(rig):
    with pytest.raises(InvalidRequestError, match="user message"):
        rig.router.chat_send(SID, Message(role="assistant", text="x"))


def test_the_session_hook_failing_does_not_fail_the_turn(rig):
    rig.router._session_hook = lambda *a: 1 / 0
    assert rig.send().text


def test_chat_stream_ends_with_turn_done_and_chat_send_hides_it(rig):
    events = list(rig.router.chat_stream(SID, Message(role="user", text="hello"), RouteContext()))
    assert [e.kind for e in events][0] == "started" and events[-1].kind == "turn_done"
    assert json.loads(json.dumps(events[-1].data))["result"]["text"].startswith("[stub] hello")
    seen = []
    result = rig.send("again", on_event=seen.append)
    assert result.text.startswith("[stub] again") and "turn_done" not in {e.kind for e in seen} and {"started", "text"} <= {e.kind for e in seen}


def test_chat_stop_ends_a_running_turn_and_is_false_when_idle(tmp_path):
    rig = Rig(tmp_path)
    assert rig.router.chat_stop(SID) is False
    rig.claude.delay = 5.0
    errors = []

    def run():
        try:
            rig.send("long")
        except CallCancelledError as e:
            errors.append(e)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.time() + 5
    while not rig.router.chat_stop(SID) and time.time() < deadline:
        time.sleep(0.02)
    worker.join(5)
    assert len(errors) == 1 and not worker.is_alive()
    assert rig.sink.rows[0].ok is False and rig.router.chat_stop(SID) is False


def test_close_stops_a_running_turn(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.delay = 5.0
    errors = []
    worker = threading.Thread(target=lambda: errors.append(_catch(rig.send, "long")), daemon=True)
    worker.start()
    time.sleep(0.3)
    rig.router.close()
    worker.join(5)
    assert isinstance(errors[0], CallCancelledError)


def _catch(fn, *args):
    try:
        fn(*args)
    except Exception as e:
        return e


# ---- the real connectors against the fake CLIs ------------------------------------------------------------------------------

def test_a_quota_switch_with_the_real_connectors_starts_a_codex_exec_with_the_carry_over(fake, tmp_path):
    fake.sequence("ok_plain", "quota", cli="claude").reply(text="the reply")
    fake.sequence("ok_plain", cli="codex").reply(text="codex reply")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    history, hooks = History(), []
    router = Router({"claude": ClaudeConnector(cfg), "codex": CodexConnector(cfg)}, policy(), transcripts=history,
                    session_hook=lambda *a: hooks.append(a), sleep=lambda s: None)
    router.chat_send("cs_real", Message(role="user", text="first"))
    history.messages_list = [Message(role="user", text="first"), Message(role="assistant", text="the reply"), Message(role="user", text="second")]
    result = router.chat_send("cs_real", Message(role="user", text="second"))
    router.drain()
    assert result.text == "codex reply" and result.provider == "codex"
    claude_calls, codex_calls = fake.model_calls("claude"), fake.model_calls("codex")
    assert [c["argv"][0] for c in codex_calls] == ["exec"] and "resume" not in codex_calls[0]["argv"]
    assert "carried over because the provider changed (claude → codex)" in codex_calls[0]["stdin"]
    assert "User: first\nAssistant: the reply" in codex_calls[0]["stdin"] and codex_calls[0]["stdin"].endswith("second")
    assert "--session-id" in claude_calls[0]["argv"]
    state = load_session_state(cfg.resolved_work_root() / "cs_real")
    assert state.provider == "codex" and state.switches == 1 and state.provider_session_id
    assert [h[1] for h in hooks] == ["claude", "codex"]


def test_the_real_claude_connector_resumes_the_session_on_turn_two(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="r")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = Router({"claude": ClaudeConnector(cfg)}, policy(), sleep=lambda s: None)
    for text in ("one", "two"):
        router.chat_send("cs_res", Message(role="user", text=text))
    first, second = fake.model_calls("claude")
    assert "--session-id" in first["argv"] and "--resume" in second["argv"]
    assert first["argv"][first["argv"].index("--session-id") + 1] == second["argv"][second["argv"].index("--resume") + 1]
