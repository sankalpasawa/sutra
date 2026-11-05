"""The error table of connectors design 3.5, rows X1 to X18, one case each (work package CN-4).

`CODEX_ERROR_MAP` (codex.py) is the table as data: row id -> the error code. The fake `codex` has one preset per row
(`fake_cli.ROWS`), so every case runs the real connector, runner and process code. A meta-test keeps the map, the fake's rows and
the design document in step. Cases that need an exit or a message the fake cannot make run the parser directly.
"""
from __future__ import annotations

import importlib.util
import json
import re
import threading
import time
from pathlib import Path

import pytest

from sutra_app.connectors.base import Hooks, TurnPlan
from sutra_app.connectors.codex import CODEX_ERROR_MAP, CodexConnector, CodexParser
from sutra_app.connectors.errors import (
    ERROR_CLASSES, CallCancelledError, CallTimeoutError, CrashedError, FlagUnsupportedError, InvalidRequestError, ModelNotFoundError,
    NotSignedInError, ProviderError, QuotaError, RateLimitedError, ServerError, SessionLostError, StructuredError,
)
from sutra_app.connectors.models import ConnectorConfig, Message, Quota, RouteContext, SessionSpec
from sutra_app.connectors.process import ExitInfo
from sutra_app.engine.port import CliMissing, NotSignedIn, QuotaExhausted, StructuredOutputFailed

TESTS = Path(__file__).resolve().parent.parent
DESIGN = TESTS.parent / "docs" / "design" / "connectors.md"
_spec = importlib.util.spec_from_file_location("fake_cli_for_codex_errors", TESTS / "fakes" / "fake_cli.py")
fake_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_cli)
SCENARIO = dict(fake_cli.ROWS["codex"])
THREAD = "00000000-0000-4000-8000-0000000000ff"


@pytest.fixture
def make(fake, tmp_path):
    def build(*scenarios, **settings):
        if scenarios:
            fake.sequence(*scenarios)
        fake.set(**settings)
        kwargs = fake.config_kwargs(tmp_path)
        kwargs["extra_env"] = {**kwargs["extra_env"], "CODEX_HOME": str(tmp_path / "codex-home")}
        return CodexConnector(ConnectorConfig(**kwargs))
    return build


class Seen(Hooks):
    def __init__(self):
        self.records = []

    def after_call(self, record):
        self.records.append(record)


def raised(conn, **kw):
    """The ConnectorError of one call (or None)."""
    try:
        conn.call_text("Say ok.", **kw)
    except Exception as e:                                       # noqa: BLE001
        return e
    return None


def raised_send(conn, state):
    try:
        conn.send(state, Message(role="user", text="hi"))
    except Exception as e:                                       # noqa: BLE001
        return e
    return None


def stop_during_slow(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.2")
    state = conn.start(SessionSpec(session_id="cs_x16"))
    box = {}
    worker = threading.Thread(target=lambda: box.update(error=raised_send(conn, state)))
    worker.start()
    fake.wait_for(1)
    for _ in range(100):
        if conn.stop(state):
            break
        time.sleep(0.05)
    worker.join(12)
    assert not worker.is_alive()
    return box["error"]


# ---- the table is the single source -------------------------------------------------------------------------------------------

def test_every_row_of_the_design_has_a_case():
    doc = DESIGN.read_text(encoding="utf-8")
    start = doc.index("### 3.5 `CodexConnector`")
    rows = set(re.findall(r"^\| (X\d+) \|", doc[start:doc.index("### 3.6", start)], re.M))
    assert rows == {f"X{n}" for n in range(1, 19)}
    assert {re.match(r"X\d+", key).group(0) for key in CODEX_ERROR_MAP} == rows
    assert set(CODEX_ERROR_MAP) == set(SCENARIO) | {"X1", "X4"}              # the fake has a preset for every row but X1 and X4
    assert {code for code in CODEX_ERROR_MAP.values() if code != "ok"} <= set(ERROR_CLASSES)


# ---- one case per row ---------------------------------------------------------------------------------------------------------------

def expect(row, err):
    """Row-specific facts beyond the code."""
    if row == "X2":
        assert isinstance(err, FlagUnsupportedError) and err.detail["flag"] == "--no-such-flag" and "--no-such-flag" in err.user_message()
    elif row == "X3a":
        assert "not valid JSON" in str(err)
    elif row == "X3b":
        assert "Failed to read output schema" in str(err)
    elif row == "X3c":
        assert "No such file or directory" in str(err)
    elif row in ("X5", "X5b"):
        assert isinstance(err, NotSignedIn) and err.detail["reason"] == "401_in_a_row" and "Codex is not signed in" in err.user_message()
    elif row == "X5c":
        assert isinstance(err, NotSignedInError) and err.detail["reason"] == "turn_failed"
    elif row == "X6":
        assert isinstance(err, QuotaExhausted) and err.resets_at is None and "usage limit" in str(err)
    elif row == "X7":
        assert isinstance(err, RateLimitedError) and err.retryable and err.detail["status"] == 429
    elif row == "X8":
        assert isinstance(err, ServerError) and err.retryable and err.detail["status"] == 500
    elif row == "X9":
        assert isinstance(err, StructuredOutputFailed) and err.detail["status"] == 400
    elif row == "X10":
        assert isinstance(err, ModelNotFoundError) and err.detail["model"] == "gpt-5.6-luna" and not err.retryable
    elif row == "X11":
        assert isinstance(err, ProviderError) and "418" in str(err)
    elif row == "X12":
        assert isinstance(err, SessionLostError)
    elif row == "X13":
        assert isinstance(err, CrashedError) and err.detail["exit"] == 137 and err.retryable
    elif row == "X14":
        assert err.code == "protocol_error" and "without a turn end" in str(err)
    elif row == "X17":
        assert err.kind == "bad_output" and err.retryable


@pytest.mark.parametrize("row", sorted(CODEX_ERROR_MAP, key=lambda r: (int(re.match(r"X(\d+)", r).group(1)), r)))
def test_row(row, fake, make, tmp_path, monkeypatch):
    code = CODEX_ERROR_MAP[row]
    if row == "X1":                                              # PATH emptied: the bare name cannot be found
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        conn = CodexConnector(ConnectorConfig(**dict(fake.config_kwargs(tmp_path), codex_exe="codex")))
        err = raised(conn)
        assert isinstance(err, CliMissing) and "install it and run `codex login`" in err.user_message()
    elif row == "X4":                                            # signed out: found by `login status`, no process for the call
        fake.auth(codex="signed_out")
        seen = Seen()
        err = raised(make("ok_plain"), hooks=seen)
        assert fake.model_calls("codex") == [] and seen.records[0].code == "not_signed_in" and seen.records[0].exit_code is None
        assert isinstance(err, NotSignedIn)
    elif row == "X5b":                                           # a slow stream of 401s is stopped after two, not after 18 s
        conn = make(SCENARIO[row])
        began = time.time()
        err = raised(conn)
        assert time.time() - began < 5
        call = fake.model_calls("codex")[0]
        assert call["exit"] is not None and call["exit"] != 0 and conn.runner.live() == []
    elif row == "X12":                                           # a resumed chat turn
        conn = make(SCENARIO[row])
        state = conn.start(SessionSpec(session_id="cs_x12"))
        state.provider_session_id = THREAD
        err = raised_send(conn, state)
        assert fake.model_calls("codex")[0]["argv"][:2] == ["exec", "resume"] and THREAD in fake.model_calls("codex")[0]["argv"]
    elif row == "X15":                                           # the total deadline
        err = raised(make(SCENARIO[row]), timeout=0.6)
        assert err.detail["which"] == "total" and err.detail["seconds"] == 0.6 and "did not answer within 0.6 s" in err.user_message()
    elif row == "X16":                                           # stop() while it runs
        err = stop_during_slow(fake, make)
    elif row == "X18":                                           # an item type nobody knows is tolerated
        events = []
        turn = make(SCENARIO[row]).call_text("Say ok.", on_event=events.append)
        assert turn.text and [e.data["type"] for e in events if e.kind == "tool_call"] == ["command_execution"] and code == "ok"
        return
    elif row == "X2":
        err = raised(make(SCENARIO[row], FAKE_BAD_FLAG="--no-such-flag"))
    else:
        err = raised(make(SCENARIO[row]))
    assert err is not None, f"{row} did not fail"
    assert err.code == code, f"{row}: {err.code} / {err}"
    assert err.provider == "codex" and err.detail.get("cli") in ("codex", None)
    assert err.as_dict()["code"] == code
    expect(row, err)


# ---- what the table does not spell out ------------------------------------------------------------------------------------------------

def test_a_cancelled_call_is_the_cancelled_class(fake, make):
    err = stop_during_slow(fake, make)
    assert isinstance(err, CallCancelledError) and not err.retryable and not err.fallback_ok


def test_a_usage_limit_with_a_time_in_it_gives_the_reset_time(fake, make):
    err = raised(make("usage_limit_try_again"))
    assert err.code == "quota" and err.resets_at is not None
    assert time.strftime("%Y-%m-%d %H:%M", time.localtime(err.resets_at)) == "2026-11-05 16:30"


def test_every_failure_reaches_the_hooks_with_its_code(fake, make):
    seen = Seen()
    err = raised(make("rate_limited_429"), hooks=seen)
    assert err.code == "rate_limited" and [(r.ok, r.code, r.exit_code) for r in seen.records] == [(False, "rate_limited", 1)]


def test_an_error_never_carries_the_prompt_or_the_system_text(fake, make):
    secret_prompt, secret_system = "PROMPT-SECRET-123", "SYSTEM-SECRET-456"
    for scenario in ("server_error_500", "not_signed_in", "provider_error", "crash"):
        try:
            make(scenario).call_text(secret_prompt, system=secret_system)
        except Exception as e:                                   # noqa: BLE001
            dumped = json.dumps(e.as_dict()) + str(e) + e.user_message() + json.dumps(e.detail)
            assert secret_prompt not in dumped and secret_system not in dumped


def test_a_file_that_cannot_run_is_a_missing_cli(fake, make, tmp_path):
    script = tmp_path / "codex-noexec"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o644)
    conn = CodexConnector(ConnectorConfig(**dict(fake.config_kwargs(tmp_path), codex_exe=str(script))))
    err = raised(conn)
    assert err.code == "cli_missing" and err.provider == "codex"
    assert conn.auth_status().installed is False


# ---- parser-level cases for messages and exits the fake cannot make ---------------------------------------------------------------------

def plan():
    return TurnPlan(prompt="hello", ctx=RouteContext(), model="gpt-5.6-luna", effort="low")


def ended(code=0, reason="exit", stderr=""):
    return ExitInfo(returncode=code, reason=reason, stderr_tail=stderr, seconds=0.1, pid=1)


def failure(message, **kw):
    parser = CodexParser(plan(), **kw)
    parser.feed(json.dumps({"type": "turn.failed", "error": {"message": message}}))
    with pytest.raises(Exception) as caught:
        parser.finish(ended(1))
    return caught.value


@pytest.mark.parametrize(("message", "cls", "status"), [
    ("unexpected status 503 Service Unavailable, url: https://x", ServerError, 503),
    ("exceeded retry limit, last status: 502 Bad Gateway", ServerError, 502),
    ("exceeded retry limit, last status: 429 Too Many Requests", RateLimitedError, 429),
    ("Too Many Requests", RateLimitedError, None),
    ("unexpected status 401 Unauthorized: Missing bearer", NotSignedInError, 401),
    ("Missing bearer or basic authentication in header", NotSignedInError, None),
    ("unexpected status 400 Bad Request: bad response_format", StructuredError, 400),
    ("unexpected status 400 Bad Request: the model gpt-x is not supported", ModelNotFoundError, 400),
    ("unexpected status 400 Bad Request: something else", ProviderError, None),
    ("model overloaded, try later", ProviderError, None),
    ("", ProviderError, None)])
def test_turn_failed_messages_are_classified_in_the_order_of_the_table(message, cls, status):
    err = failure(message)
    assert type(err) is cls
    if status is not None:
        assert err.detail["status"] == status


def test_a_status_number_inside_an_id_is_not_a_status():
    err = failure("stream failed, request id: req_4294ab, cf-ray: 4001-BOM, retry 5003")
    assert type(err) is ProviderError


def test_a_usage_limit_without_a_time_asks_the_rollout_and_only_believes_an_exhausted_window():
    message = "You've hit your usage limit."
    assert failure(message).resets_at is None
    exhausted = Quota(status="exhausted", resets_at=1796323361.0, source="rollout")
    ok = Quota(status="ok", resets_at=1796323361.0, source="rollout")
    parser = CodexParser(plan(), quota_reader=lambda thread: exhausted)
    parser.feed('{"type":"thread.started","thread_id":"t1"}')
    parser.feed(json.dumps({"type": "turn.failed", "error": {"message": message}}))
    with pytest.raises(QuotaError) as caught:
        parser.finish(ended(1))
    assert caught.value.resets_at == 1796323361.0
    assert failure(message, quota_reader=lambda thread: ok).resets_at is None
    boom = CodexParser(plan(), quota_reader=lambda thread: 1 / 0)
    boom.feed('{"type":"thread.started","thread_id":"t1"}')
    boom.feed(json.dumps({"type": "turn.failed", "error": {"message": message}}))
    with pytest.raises(QuotaError):
        boom.finish(ended(1))                                    # a reader that blows up is ignored


def test_a_text_time_beats_the_rollout():
    clock = lambda: time.mktime((2026, 11, 4, 12, 0, 0, 0, 0, -1))      # noqa: E731
    err = failure("hit your usage limit, try again at Nov 5th, 2026 4:30 PM.", clock=clock,
                  quota_reader=lambda t: Quota(status="exhausted", resets_at=5.0))
    assert err.resets_at == time.mktime((2026, 11, 5, 16, 30, 0, 0, 0, -1))


def test_turn_failed_wins_over_a_later_missing_turn_end_and_a_bad_exit():
    err = failure("unexpected status 500 Internal Server Error")
    assert err.code == "server_error"


def test_the_timeout_and_cancel_reasons_come_before_everything_else():
    parser = CodexParser(plan())
    parser.feed(json.dumps({"type": "turn.failed", "error": {"message": "unexpected status 500"}}))
    with pytest.raises(CallTimeoutError):
        parser.finish(ended(-15, "total_timeout"))
    with pytest.raises(CallTimeoutError) as idle:
        parser.finish(ended(-15, "idle_timeout"))
    assert idle.value.detail["which"] == "idle"
    with pytest.raises(CallCancelledError):
        parser.finish(ended(-15, "cancelled"))


def test_the_auth_abort_comes_before_the_cancel_it_caused():
    parser = CodexParser(plan())
    parser.auth_aborted = True
    with pytest.raises(NotSignedInError):
        parser.finish(ended(-2, "cancelled"))


def test_a_signal_death_without_a_turn_end_is_a_crash_naming_the_signal():
    parser = CodexParser(plan())
    parser.feed('{"type":"thread.started","thread_id":"t"}')
    with pytest.raises(CrashedError) as caught:
        parser.finish(ended(-9, stderr="Killed"))
    assert caught.value.detail["exit"] == "SIGKILL"


def test_empty_output_with_exit_zero_is_a_protocol_error_and_a_bad_exit_a_crash():
    with pytest.raises(Exception) as zero:
        CodexParser(plan()).finish(ended(0))
    assert zero.value.code == "protocol_error"
    with pytest.raises(CrashedError):
        CodexParser(plan()).finish(ended(3, stderr="something else went wrong"))


def test_the_command_line_rows_need_no_event_but_a_lost_thread_needs_none_either():
    parser = CodexParser(plan())
    parser.feed('{"type":"thread.started","thread_id":"t"}')
    with pytest.raises(FlagUnsupportedError):
        CodexParser(plan()).finish(ended(2, stderr="error: unexpected argument '--x' found"))
    with pytest.raises(CrashedError):                            # events were seen: this is not an argument error
        parser.finish(ended(2, stderr="error: unexpected argument '--x' found"))
    with pytest.raises(SessionLostError):
        parser.finish(ended(1, stderr="Error: thread/resume failed: no rollout found for thread id t (code -32600)"))
    with pytest.raises(InvalidRequestError):
        CodexParser(plan()).finish(ended(1, stderr="Reading additional input from stdin...\nOutput schema file /x is not valid JSON: boom\n"))


def test_a_blank_reply_is_empty():
    parser = CodexParser(plan())
    parser.feed('{"type":"item.completed","item":{"type":"agent_message","text":"  "}}')
    parser.feed('{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}')
    with pytest.raises(Exception) as caught:
        parser.finish(ended(0))
    assert caught.value.code == "empty_reply"
