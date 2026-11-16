"""One stop owner for a chat turn (streaming design D215, work package STR-2): the `CancelToken`, and a Stop at every moment of a turn.

The windows a Stop used to fall through: during session setup, between the turn being registered and its process being tracked, while the
process is being started, and in the wait between two attempts. In each of them the token ends the turn, no process is left, and
`Router.chat_stop` says True for as long as the turn runs and False only after it ended."""
from __future__ import annotations

import sys
import threading
import time

import pytest

from sutra_app.connectors.cancel import CancelToken
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.errors import CallCancelledError, ServerError
from sutra_app.connectors.models import AuthStatus, ConnectorConfig, Message, RouteContext
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink

from test_router_chat import Named, History, policy, SID

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLIs and the cancel ladder are POSIX")


class FakeProc:
    def __init__(self, running=True):
        self.running, self.cancelled = running, 0

    def cancel(self):
        self.cancelled += 1
        return self.running


# ---- the token itself ------------------------------------------------------------------------------------------------------------

def test_request_is_true_once_and_wait_returns_at_once_after_it():
    token = CancelToken()
    assert token.requested is False and token.wait(0.01) is False
    assert token.request() is True and token.request() is False and token.requested
    started = time.monotonic()
    assert token.wait(5) is True and time.monotonic() - started < 0.5


def test_wait_wakes_up_when_another_thread_requests():
    token = CancelToken()
    threading.Timer(0.05, token.request).start()
    started = time.monotonic()
    assert token.wait(5) is True and time.monotonic() - started < 2


def test_a_process_bound_after_the_request_is_cancelled_at_once():
    token, proc = CancelToken(), FakeProc()
    token.request()
    assert token.bind(proc) is True and proc.cancelled == 1


def test_a_process_bound_before_the_request_is_cancelled_by_cancel_bound_only():
    token, proc = CancelToken(), FakeProc()
    assert token.bind(proc) is False
    token.request()
    assert proc.cancelled == 0                           # request never blocks on the ladder
    assert token.cancel_bound() is True and proc.cancelled == 1
    token.unbind(proc)
    assert token.cancel_bound() is False


def test_request_and_bind_race_in_both_orders_never_lose_the_stop():
    for order in ("request_first", "bind_first"):
        for _ in range(50):
            token, proc = CancelToken(), FakeProc()
            first, second = (token.request, lambda: token.bind(proc)) if order == "request_first" else (lambda: token.bind(proc), token.request)
            threads = [threading.Thread(target=first), threading.Thread(target=second)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            token.cancel_bound() if proc.cancelled == 0 else None      # a bind that preceded the request is reached by the stop route's cancel_bound
            assert proc.cancelled >= 1


def test_cancelling_a_process_that_raises_is_swallowed():
    class Bad:
        def cancel(self):
            raise RuntimeError("gone")
    token = CancelToken()
    token.request()
    assert token.bind(Bad()) is False


# ---- the router, with stub connectors (no process) ---------------------------------------------------------------------------------

class Rig:
    def __init__(self, tmp_path, connector_cls=Named, **kw):
        cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work", claude_exe=sys.executable, codex_exe=sys.executable)
        self.cfg = cfg
        self.claude, self.codex = connector_cls("claude", cfg), Named("codex", cfg)
        self.history, self.sink = History(), MemoryUsageSink()
        self.router = Router({"claude": self.claude, "codex": self.codex}, policy(**kw.pop("defaults", {})), usage_sink=self.sink,
                             transcripts=self.history, **kw)

    def stream(self, token, text="hello"):
        return list(self.router.chat_stream(SID, Message(role="user", text=text), RouteContext(), cancel=token))


def test_a_token_requested_before_the_turn_stops_it_before_anything_happens(tmp_path):
    rig = Rig(tmp_path, sleep=lambda s: None)
    token = CancelToken()
    token.request()
    with pytest.raises(CallCancelledError):
        rig.stream(token)
    assert rig.claude.calls == [] and rig.router.chat_stop(SID) is False


def test_the_entry_of_a_turn_cannot_erase_a_requested_token(tmp_path):
    """The old early flag was cleared by `_chat` on entry; a token lives in the caller, so a Stop sent just before the turn is still a Stop."""
    rig = Rig(tmp_path, sleep=lambda s: None)
    token = CancelToken()
    assert rig.router.chat_stop(SID) is False            # nothing is running: it does not pretend
    token.request()
    with pytest.raises(CallCancelledError):
        rig.stream(token)
    assert rig.claude.calls == []
    assert len(rig.stream(CancelToken())) > 0            # and the next turn is not poisoned


def test_stop_during_session_setup_with_a_token_ends_the_turn_before_a_process(tmp_path):
    rig = Rig(tmp_path, sleep=lambda s: None)
    token, answers = CancelToken(), []

    class StopsDuringSetUp(History):
        def messages(self, session_id, limit=20):
            answers.append(rig.router.chat_stop(session_id))          # a Stop in the window after the turn began and before any process
            return super().messages(session_id, limit)
    rig.router.transcripts = StopsDuringSetUp()
    with pytest.raises(CallCancelledError):
        rig.stream(token)
    assert answers == [True] and token.requested and rig.claude.calls == [] and rig.router.chat_stop(SID) is False


class Fails(Named):
    """A provider that fails retryably every time: the router waits between attempts."""
    attempts = 0

    def stream(self, *a, **kw):
        type(self).attempts += 1
        raise ServerError("boom", provider=self.name)


def test_stop_ends_the_back_off_wait_at_once(tmp_path):
    Fails.attempts = 0
    rig = Rig(tmp_path, connector_cls=Fails, defaults={"retry_delays_s": [30, 30], "max_attempts": 3, "order": ["claude"]})
    rig.router._sleep = time.sleep                         # the real wait: the token's wait replaces it
    token, errors = CancelToken(), []

    def run():
        try:
            rig.stream(token)
        except Exception as e:                             # noqa: BLE001
            errors.append(e)
    worker = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    worker.start()
    deadline = time.time() + 5
    while Fails.attempts < 1 and time.time() < deadline:
        time.sleep(0.01)
    time.sleep(0.1)                                        # inside the 30 s wait
    assert rig.router.chat_stop(SID) is True
    worker.join(5)
    assert not worker.is_alive() and time.monotonic() - started < 5
    assert len(errors) == 1 and isinstance(errors[0], CallCancelledError) and Fails.attempts == 1
    assert rig.router.chat_stop(SID) is False


def test_without_a_token_the_injected_sleep_is_still_what_waits(tmp_path):
    Fails.attempts = 0
    slept = []
    rig = Rig(tmp_path, connector_cls=Fails, sleep=slept.append, rng=lambda: 0.0, defaults={"retry_delays_s": [7], "max_attempts": 2, "order": ["claude"]})
    with pytest.raises(ServerError):
        list(rig.router.chat_stream(SID, Message(role="user", text="x"), RouteContext()))
    assert slept == [7] and Fails.attempts == 2


# ---- the real connector against the fake CLI: the process windows ----------------------------------------------------------------

class SlowStart:
    """A runner whose `start` takes a while (the window while the process is being started) and then runs the real one."""

    def __init__(self, inner, gate):
        self.inner, self.gate = inner, gate

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def start(self, *a, **kw):
        self.gate.wait(10)
        return self.inner.start(*a, **kw)


def _real(fake, tmp_path, scenario="slow"):
    fake.sequence(scenario).set(FAKE_LINE_DELAY="0.2")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    connector = ClaudeConnector(cfg)
    router = Router({"claude": connector}, policy(order=["claude"]), sleep=lambda s: None, transcripts=History())
    return connector, router


@POSIX
def test_stop_while_the_process_is_starting_cancels_it_the_moment_it_is_tracked(fake, tmp_path):
    connector, router = _real(fake, tmp_path)
    gate = threading.Event()
    connector.runner = SlowStart(connector.runner, gate)
    token, outcome = CancelToken(), []

    def run():
        try:
            list(router.chat_stream(SID, Message(role="user", text="hi"), RouteContext(), cancel=token))
        except Exception as e:                                       # noqa: BLE001
            outcome.append(e)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.time() + 5
    while not router._chat_tokens and time.time() < deadline:
        time.sleep(0.01)
    assert router.chat_stop(SID) is True                             # the process does not exist yet, and the answer is still True
    assert token.requested
    gate.set()                                                       # now it starts: `bind` finds the request and cancels at once
    worker.join(15)
    assert not worker.is_alive() and len(outcome) == 1 and isinstance(outcome[0], CallCancelledError)
    assert connector.runner.live() == [] and router.chat_stop(SID) is False


@POSIX
def test_stop_during_a_running_process_cancels_it_and_chat_stop_is_true_until_the_end(fake, tmp_path):
    connector, router = _real(fake, tmp_path)
    token, outcome, seen = CancelToken(), [], []

    def run():
        try:
            for event in router.chat_stream(SID, Message(role="user", text="hi"), RouteContext(), cancel=token):
                seen.append(event.kind)
        except Exception as e:                                       # noqa: BLE001
            outcome.append(e)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    deadline = time.time() + 10
    while "started" not in seen and time.time() < deadline:
        time.sleep(0.02)
    assert router.chat_stop(SID) is True
    worker.join(15)
    assert not worker.is_alive() and isinstance(outcome[0], CallCancelledError)
    assert connector.runner.live() == [] and router.chat_stop(SID) is False


@POSIX
def test_a_token_that_is_never_requested_changes_nothing_for_a_real_turn(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="fine")
    cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
    router = Router({"claude": ClaudeConnector(cfg)}, policy(order=["claude"]), sleep=lambda s: None, transcripts=History())
    events = list(router.chat_stream(SID, Message(role="user", text="hi"), RouteContext(), cancel=CancelToken()))
    assert events[-1].kind == "turn_done" and events[-1].data["result"]["text"] == "fine"
