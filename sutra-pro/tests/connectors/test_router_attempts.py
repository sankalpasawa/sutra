"""Router attempts: retry delays, fallback, the one usage row per request, the concurrency cap, health events
(connectors design 3.6 "Attempts", 3.8, work package CN-7). Providers are `Named` stub connectors (no process)."""
from __future__ import annotations

import sys
import threading
import time

import pytest

from sutra_app.connectors.errors import (
    CallCancelledError, ConnectorError, InvalidRequestError, NoProviderError, OverloadedError, ProviderError,
)
from sutra_app.connectors.models import AskRequest, AuthStatus, ConnectorConfig, RouteContext
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import CallTag, ModelError


def policy(claude=None, codex=None, **defaults):
    base = {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
            "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
            "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4, **(claude or {})},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, **(codex or {})}},
                         "defaults": base, "rules": [], "rates": {}})


class Named(StubConnector):
    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name

    def resolve_model(self, requested):
        return requested or "scripted"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=True, billing="subscription", checked_at=self._clock())


class Rig:
    def __init__(self, tmp_path, pol=None, rng=lambda: 0.0, **kw):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Named("claude", cfg), Named("codex", cfg)
        self.sleeps, self.sink, self.events = [], MemoryUsageSink(), []
        self.router = Router({"claude": self.claude, "codex": self.codex}, pol or policy(), usage_sink=self.sink,
                             sleep=self.sleeps.append, rng=rng, events=lambda t, d: self.events.append((t, d)), **kw)

    def ask(self, text="hello", **kw):
        return self.router.ask(AskRequest(user=text, **kw))


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_a_retryable_error_is_retried_after_each_delay(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=3))
    rig.claude.fail_next("overloaded", 2)
    turn = rig.ask()
    assert rig.sleeps == [2.0, 5.0]
    assert turn.text.startswith("[stub] hello")
    row, = rig.sink.rows
    assert [a["code"] for a in row.detail["attempts"]] == ["overloaded", "overloaded", "ok"]
    assert row.provider == "claude" and row.ok and row.detail["note"] is None


def test_the_last_delay_repeats_and_jitter_is_added(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=4), rng=lambda: 0.5)
    rig.claude.fail_next("server_error", 3)
    rig.ask()
    assert rig.sleeps == [2.5, 5.5, 5.5]


def test_no_delays_means_no_sleep(tmp_path):
    rig = Rig(tmp_path, policy(retry_delays_s=[]))
    rig.claude.fail_next("overloaded")
    rig.ask()
    assert rig.sleeps == []


def test_the_default_is_one_retry_then_the_next_provider_with_a_note(rig):
    rig.claude.fail_next("overloaded", 2)
    progress = []
    rig.router.ask(AskRequest(user="hello"), progress.append)
    assert rig.sleeps == [2.0]
    row, = rig.sink.rows
    assert row.provider == "codex" and row.detail["note"] == "claude overloaded, answered by codex"
    assert {"note": "claude overloaded, answered by codex"} in progress
    assert [a["provider"] for a in row.detail["attempts"]] == ["claude", "claude", "codex"]


def test_quota_falls_back_at_once_and_the_provider_is_skipped_next_time(rig):
    rig.claude.fail_next("quota", resets_at=time.time() + 3600)
    rig.ask()
    assert rig.sleeps == []
    assert rig.sink.rows[0].detail["note"] == "claude out of quota, answered by codex"
    assert rig.router.health.state("claude").state == "quota"
    assert ("connector.health", {"provider": "claude", "state": "quota", "until": rig.router.health.state("claude").until,
                                 "reason": "usage limit reached"}) in rig.events
    rig.ask()
    assert [c.rule for c in rig.claude.calls] == ["failed"]            # the second request never touched claude
    assert rig.sink.rows[1].provider == "codex" and rig.sink.rows[1].detail["note"] is None


def test_a_non_retryable_fallback_error_skips_the_retry(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=3))
    rig.claude.fail_next("not_signed_in")
    rig.ask()
    assert rig.sleeps == [] and rig.sink.rows[0].provider == "codex" and len(rig.claude.calls) == 1


@pytest.mark.parametrize("code", ["invalid_request", "reply_truncated", "cancelled"])
def test_these_errors_never_fall_back(rig, code):
    rig.claude.fail_next(code)
    with pytest.raises(ConnectorError) as e:
        rig.ask()
    assert e.value.code == code and rig.codex.calls == [] and rig.sleeps == []
    assert rig.sink.rows[0].ok is False


def test_all_providers_failing_raises_the_last_error_and_records_one_failed_row(rig):
    rig.claude.fail_next("quota")
    rig.codex.fail_next("overloaded", 2)
    with pytest.raises(OverloadedError) as e:
        rig.ask()
    assert e.value.provider == "codex"
    row, = rig.sink.rows
    assert row.ok is False and row.provider == "codex"
    assert [a["code"] for a in row.detail["attempts"]] == ["quota", "overloaded", "overloaded"]
    assert e.value.detail["request_id"] == row.detail["request_id"] and e.value.detail["attempts"] == row.detail["attempts"]
    assert "prompt" not in e.value.as_dict()["detail"]


def test_a_retryable_error_on_the_only_provider_stops_after_max_attempts(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=3))
    rig.router._connectors.pop("codex")
    rig.claude.fail_next("provider_error", 5)
    with pytest.raises(ProviderError):
        rig.ask()
    assert len(rig.claude.calls) == 3 and rig.sleeps == [2.0, 5.0]


def test_the_error_that_stops_a_request_is_the_engines_model_error(rig):
    rig.claude.fail_next("invalid_request")
    with pytest.raises(ModelError):
        rig.ask()
    assert issubclass(InvalidRequestError, RuntimeError)


def test_one_row_per_request_whatever_the_attempts(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=3))
    rig.claude.fail_next("overloaded", 3)
    rig.ask()
    assert len(rig.sink.rows) == 1 and len(rig.sink.rows[0].detail["attempts"]) == 4


def test_the_row_carries_the_tag_and_context(rig):
    tag = CallTag(run_id="j2-20261104-000000-ab12", dept_id="web", task_id="tsk_1", function="audit", role="judge", stage="website",
                  step=3, call_no=7, atom="a-1234567890-01", purpose="review")
    rig.ask(ctx=RouteContext(tag=tag, session_id="cs_org", node_id="root"))
    row, = rig.sink.rows
    assert (row.purpose, row.fn, row.dept_id, row.task_id, row.step, row.atom_id) == ("review", "audit", "web", "tsk_1", "J2.c", "a-1234567890-01")
    assert (row.session_id, row.node_id, row.call_ref) == ("cs_org", "root", "j2-20261104-000000-ab12:7")
    assert row.how == "text" and row.model == "scripted" and row.tokens_in is not None and row.usd == 0.0


def test_a_call_without_a_tag_has_a_null_atom_and_a_request_call_ref(rig):
    rig.ask()
    row, = rig.sink.rows
    assert row.atom_id is None and row.call_ref == "r:" + row.detail["request_id"] and row.step is None


def test_a_failure_before_any_spawn_still_records_a_row(rig):
    for c in (rig.claude, rig.codex):
        c.probe_auth = lambda c=c: AuthStatus(provider=c.name, installed=True, signed_in=False, checked_at=0.0)
    with pytest.raises(NoProviderError) as e:
        rig.ask()
    row, = rig.sink.rows
    assert row.ok is False and row.provider == "claude" and row.tokens_in is None and row.detail["attempts"] == []
    assert e.value.detail["request_id"] == row.detail["request_id"] and len(e.value.detail["skipped"]) == 2


def test_a_missing_image_is_refused_before_any_spawn(rig, tmp_path):
    with pytest.raises(InvalidRequestError, match="image not found"):
        rig.ask(images=[str(tmp_path / "nope.png")])
    assert rig.claude.calls == [] and rig.sink.rows[0].ok is False


def test_an_exception_that_is_not_a_connector_error_propagates_and_is_recorded(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    sink = MemoryUsageSink()
    router = Router({"stub": StubConnector(cfg)}, policy(), usage_sink=sink, connector="stub")
    with pytest.raises(TypeError, match="scripted reply is text"):
        router.ask(AskRequest(user="x", scripted=lambda: 5))
    row, = sink.rows
    assert row.ok is False and row.provider == "stub" and row.how == "stub"


def test_a_stub_answer_is_how_stub(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    sink = MemoryUsageSink()
    router = Router({"stub": StubConnector(cfg)}, policy(), usage_sink=sink, connector="stub")
    assert router.ask(AskRequest(user="x", scripted=lambda: "canned")).text == "canned"
    assert sink.rows[0].how == "stub" and sink.rows[0].model == "scripted"


def test_a_sink_that_fails_does_not_fail_the_request(rig):
    class Broken:
        def record(self, row):
            raise RuntimeError("database is locked")
    rig.router.usage_sink = Broken()
    assert rig.ask().text.startswith("[stub]")


def test_a_failing_events_callback_does_not_fail_the_request(tmp_path):
    rig = Rig(tmp_path)

    def boom(t, d):
        raise RuntimeError("bus closed")
    rig.router._events = boom
    rig.claude.fail_next("quota")
    assert rig.ask().text


def test_health_events_fire_on_a_change_only(rig):
    rig.ask()
    rig.ask()
    assert rig.events == []
    rig.claude.fail_next("rate_limited", 2)
    rig.ask()
    assert [d["state"] for t, d in rig.events if t == "connector.health"][0] == "cooldown"


def test_a_success_lifts_the_cooldown_and_says_so(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=2))
    rig.claude.fail_next("rate_limited")
    rig.ask()
    states = [d["state"] for t, d in rig.events]
    assert states == ["cooldown", "ok"] and rig.router.health.state("claude").state == "ok"


def test_the_semaphore_caps_concurrent_spawns_per_provider(tmp_path):
    for limit in (1, 2):
        rig = Rig(tmp_path / str(limit), policy(claude={"max_concurrency": limit}))
        live, peak, lock = [0], [0], threading.Lock()

        def reply():
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            return "ok"
        rig.claude.book.set("*", "*", reply)
        threads = [threading.Thread(target=rig.ask) for _ in range(5)]
        [t.start() for t in threads]
        [t.join(10) for t in threads]
        assert peak[0] == limit and len(rig.sink.rows) == 5


def test_status_counts_todays_calls_and_tokens(rig):
    rig.ask("x" * 400)
    rig.ask("y" * 400)
    today = rig.router.status().providers[0].today
    assert today.calls == 2 and today.tokens >= 200 and today.usd == 0.0


def test_close_refuses_new_work_stops_children_and_is_idempotent(rig):
    stopped = []
    rig.claude.runner.stop_all = lambda: stopped.append("claude") or 0
    rig.codex.runner.stop_all = lambda: stopped.append("codex") or 0
    rig.router.close()
    rig.router.close()
    assert stopped == ["claude", "codex"] * 2
    with pytest.raises(CallCancelledError):
        rig.ask()
    assert rig.sink.rows[0].ok is False


def test_an_error_after_close_is_not_retried(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.book.set("*", "*", lambda: rig.router.close() or "late")
    rig.claude.fail_next("overloaded")
    rig.router.close()
    with pytest.raises(CallCancelledError):
        rig.ask()
    assert rig.sleeps == []


def test_progress_events_are_cumulative_text(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg, delay=0.03)}, policy(), connector="stub")
    seen = []
    router.ask(AskRequest(user="x", scripted=lambda: "abcdefghij" * 6), seen.append)
    assert seen[-1] == {"chars": 60, "text": "abcdefghij" * 6}
    assert [e["chars"] for e in seen] == sorted(e["chars"] for e in seen) and len(seen) > 5
    assert len({e["chars"] for e in seen}) == len(seen)                 # the closing `text` event is not a second copy
