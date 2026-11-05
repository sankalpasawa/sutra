"""The allowance gate and the router's ceiling (connectors design 3.6 "Attempts", S1-contracts-06, work package CN-7).

Before every spawn the router checks the caller's `Allowance` (deadline, max_calls, max_usd) and its own ceiling
`max_calls_per_request`; an over-allowance request raises EnvelopeExceededError with NO process started."""
from __future__ import annotations

import sys
import threading

import pytest
from pydantic import BaseModel

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.errors import EnvelopeExceededError, InvalidJsonError
from sutra_app.connectors.models import AskRequest, AuthStatus, ConnectorConfig, JsonRequest, RouteContext
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import Allowance


def policy(**defaults):
    base = {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
            "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
            "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 1},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2}},
                         "defaults": base, "rules": [], "rates": {}})


class Named(StubConnector):
    def __init__(self, name, cfg, **kw):
        super().__init__(cfg, **kw)
        self.name = name
        self.timeouts = []

    def resolve_model(self, requested):
        return requested or "scripted"

    def probe_auth(self):
        return AuthStatus(provider=self.name, installed=True, signed_in=True, billing="subscription", checked_at=self._clock())

    def call_text(self, prompt, **kw):
        self.timeouts.append(kw.get("timeout"))
        return super().call_text(prompt, **kw)


class Out(BaseModel):
    answer: str


class Rig:
    def __init__(self, tmp_path, pol=None, **kw):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.claude, self.codex = Named("claude", cfg), Named("codex", cfg)
        self.sleeps, self.sink = [], MemoryUsageSink()
        self.router = Router({"claude": self.claude, "codex": self.codex}, pol or policy(), usage_sink=self.sink,
                             sleep=self.sleeps.append, rng=lambda: 0.0, **kw)

    def ask(self, allowance, **kw):
        return self.router.ask(AskRequest(user="hello", ctx=RouteContext(allowance=allowance), **kw))

    def json(self, allowance=None, schema=Out):
        ctx = RouteContext(allowance=allowance or Allowance())
        return self.router.call_json(JsonRequest(user="hello", ctx=ctx, schema=schema))


def test_max_calls_one_with_a_transient_failure_stops_before_a_second_spawn(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.fail_next("overloaded")
    with pytest.raises(EnvelopeExceededError) as e:
        rig.ask(Allowance(max_calls=1, envelope_id="atom-9"))
    assert len(rig.claude.calls) == 1 and rig.codex.calls == [] and rig.sleeps == []       # it does not even wait for the refused retry
    assert e.value.detail["limit"] == "max_calls" and e.value.detail["calls_made"] == 1 and e.value.detail["envelope_id"] == "atom-9"
    row, = rig.sink.rows
    assert row.ok is False and row.detail["envelope_id"] == "atom-9" and len(row.detail["attempts"]) == 1


def test_max_calls_zero_allows_no_spawn_at_all(tmp_path):
    rig = Rig(tmp_path)
    with pytest.raises(EnvelopeExceededError):
        rig.ask(Allowance(max_calls=0))
    assert rig.claude.calls == [] and rig.codex.calls == []
    assert rig.sink.rows[0].ok is False and rig.sink.rows[0].detail["attempts"] == []


def test_a_fallback_spawn_counts_against_max_calls(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.fail_next("quota")
    assert rig.ask(Allowance(max_calls=2)).text
    rig2 = Rig(tmp_path / "b")
    rig2.claude.fail_next("quota")
    with pytest.raises(EnvelopeExceededError):
        rig2.ask(Allowance(max_calls=1))
    assert rig2.codex.calls == []


def test_the_envelope_error_never_falls_back_and_is_not_retried(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.fail_next("envelope_exceeded")
    with pytest.raises(EnvelopeExceededError):
        rig.ask(Allowance())
    assert rig.codex.calls == [] and rig.sleeps == []


def test_a_deadline_in_the_past_stops_the_request_at_once(tmp_path):
    rig = Rig(tmp_path, clock=lambda: 1000.0)
    with pytest.raises(EnvelopeExceededError) as e:
        rig.ask(Allowance(deadline=1000.0))
    assert e.value.detail["limit"] == "deadline" and rig.claude.calls == []


def test_a_deadline_that_passes_during_a_retry_wait_stops_the_retry(tmp_path):
    now = [1000.0]
    rig = Rig(tmp_path, clock=lambda: now[0])
    rig.router._sleep = lambda s: now.__setitem__(0, now[0] + s)
    rig.claude.fail_next("overloaded")
    with pytest.raises(EnvelopeExceededError) as e:
        rig.ask(Allowance(deadline=1001.5))
    assert e.value.detail["limit"] == "deadline" and len(rig.claude.calls) == 1


def test_the_call_timeout_is_cut_to_the_time_left(tmp_path):
    rig = Rig(tmp_path, clock=lambda: 1000.0)
    rig.ask(Allowance(deadline=1030.0))
    rig.ask(Allowance(deadline=1000.2))
    rig.ask(Allowance())
    assert rig.claude.timeouts == [30.0, 1.0, 900.0]


def test_max_usd_zero_allows_no_spawn(tmp_path):
    rig = Rig(tmp_path)
    with pytest.raises(EnvelopeExceededError) as e:
        rig.ask(Allowance(max_usd=0))
    assert rig.claude.calls == [] and e.value.detail["limit"] == "max_usd"


def test_max_usd_stops_a_repair_round_once_the_money_is_spent(fake, tmp_path):
    fake.sequence("ok_plain").cost(0.5).reply(text="not json at all")     # the native try fails (no structured output), the prompted one costs 0.5
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    sink = MemoryUsageSink()
    router = Router({"claude": ClaudeConnector(cfg)}, policy(), usage_sink=sink, sleep=lambda s: None)
    with pytest.raises(EnvelopeExceededError) as e:
        router.call_json(JsonRequest(user="hello", schema=Out, ctx=RouteContext(allowance=Allowance(max_usd=0.4))))
    assert len(fake.model_calls("claude")) == 2                                       # no repair spawn was started
    assert len(e.value.detail["attempts"]) == 2
    row, = sink.rows
    assert row.ok is False and row.usd == pytest.approx(0.5) and [a["code"] for a in row.detail["attempts"]] == ["structured", "ok"]


def test_a_cheap_enough_request_is_not_stopped_by_max_usd(fake, tmp_path):
    fake.cost(0.5)
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = Router({"claude": ClaudeConnector(cfg)}, policy(), sleep=lambda s: None)
    assert router.ask(AskRequest(user="hello", ctx=RouteContext(allowance=Allowance(max_usd=1.0)))).usd == pytest.approx(0.5)
    argv = fake.model_calls("claude")[0]["argv"]
    assert float(argv[argv.index("--max-budget-usd") + 1]) == 1.0


def test_repair_rounds_count_as_calls(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.book.set("*", "*", "this is not json")
    with pytest.raises(EnvelopeExceededError) as e:
        rig.json(Allowance(max_calls=2))
    assert e.value.detail["calls_made"] == 2 and len(rig.claude.calls) == 2
    assert rig.sink.rows[0].ok is False


def test_without_an_allowance_the_repairs_run_to_the_end(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.book.set("*", "*", "this is not json")
    with pytest.raises(InvalidJsonError) as e:
        rig.json()
    assert len(rig.claude.calls) == 3 and e.value.detail["calls"] == 3


def test_calls_made_and_usd_spent_are_the_whole_requests(tmp_path):
    rig = Rig(tmp_path)
    replies = iter(["not json", '{"answer": "yes"}'])
    rig.claude.book.set("*", "*", lambda: next(replies))
    result = rig.json(Allowance(max_calls=5))
    assert result.value == Out(answer="yes") and result.calls_made == 2 and result.usd_spent == 0.0 and result.usd == 0.0


def test_calls_made_counts_a_fallback_provider_too(tmp_path):
    rig = Rig(tmp_path)
    rig.claude.fail_next("quota")
    result = rig.json()
    assert result.calls_made == 2 and result.value == Out(answer="stub")


def test_the_router_ceiling_of_six_is_the_default(tmp_path):
    rig = Rig(tmp_path, policy(max_attempts=10, retry_delays_s=[1]))
    rig.claude.fail_next("overloaded", 20)
    with pytest.raises(EnvelopeExceededError) as e:
        rig.ask(Allowance())
    assert e.value.detail["limit"] == "max_calls_per_request" and e.value.detail["calls_made"] == 6
    assert len(rig.claude.calls) == 6 and rig.codex.calls == []


def test_a_lower_ceiling_from_the_policy_stops_the_repairs(tmp_path):
    rig = Rig(tmp_path, policy(max_calls_per_request=2))
    rig.claude.book.set("*", "*", "this is not json")
    with pytest.raises(EnvelopeExceededError) as e:
        rig.json()
    assert e.value.detail["limit"] == "max_calls_per_request" and len(rig.claude.calls) == 2


def test_a_stopped_request_gives_its_concurrency_slot_back(tmp_path):
    rig = Rig(tmp_path)                                             # claude may run one spawn at a time
    for _ in range(3):
        with pytest.raises(EnvelopeExceededError):
            rig.ask(Allowance(max_calls=0))
    done = threading.Event()
    threading.Thread(target=lambda: (rig.ask(Allowance()), done.set()), daemon=True).start()
    assert done.wait(5)


def test_the_slot_is_released_when_the_gate_trips_after_the_wait(tmp_path):
    now = [1000.0]
    rig = Rig(tmp_path, clock=lambda: now[0])
    sem = rig.router._semaphore("claude")
    sem.acquire()                                                   # another request holds claude's only slot
    result = {}

    def late():
        try:
            rig.ask(Allowance(deadline=1005.0))
        except EnvelopeExceededError as e:
            result["error"] = e
    t = threading.Thread(target=late, daemon=True)
    t.start()
    t.join(0.3)
    now[0] = 2000.0                                                 # the deadline passes while it waits
    sem.release()
    t.join(5)
    assert result["error"].detail["limit"] == "deadline" and rig.claude.calls == []
    assert sem.acquire(timeout=1)                                   # the slot is free again


def test_a_refused_spawn_does_not_even_queue_for_a_concurrency_slot(tmp_path):
    class Counting:
        def __init__(self):
            self.acquired = 0

        def acquire(self, *a, **kw):
            self.acquired += 1
            return True

        def release(self):
            pass
    rig = Rig(tmp_path)
    counting = rig.router._sems["claude"] = Counting()
    rig.claude.book.set("*", "*", "this is not json")
    with pytest.raises(EnvelopeExceededError):
        rig.json(Allowance(max_calls=1))
    assert counting.acquired == 1                  # the original spawn only; the refused repair never asked for a slot
