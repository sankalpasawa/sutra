"""The error table of connectors design 3.4, rows C1 to C25, one case each (work package CN-3).

`CLAUDE_ERROR_MAP` (claude.py) is the table as data: row id -> the error code. The fake `claude` has one preset per row
(`fake_cli.ROWS`), so every case runs the real connector, runner and process code. A meta-test keeps the map, the fake's
rows and the design document in step. Cases that need an exit the fake cannot make run the parser directly.
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
from sutra_app.connectors.claude import CLAUDE_ERROR_MAP, ClaudeConnector, ClaudeParser
from sutra_app.connectors.errors import ERROR_CLASSES, CallCancelledError, CallTimeoutError, CliMissingError
from sutra_app.connectors.models import ConnectorConfig, Message, RouteContext, SessionSpec
from sutra_app.connectors.process import ExitInfo
from sutra_app.engine.port import CliMissing, NotSignedIn, QuotaExhausted, StructuredOutputFailed

TESTS = Path(__file__).resolve().parent.parent
DESIGN = TESTS.parent / "docs" / "design" / "connectors.md"
_spec = importlib.util.spec_from_file_location("fake_cli_for_claude_errors", TESTS / "fakes" / "fake_cli.py")
fake_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake_cli)
SCENARIO = dict(fake_cli.ROWS["claude"])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("SUTRA_CLAUDE_MODEL", "CLAUDE_CLI_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def make(fake, tmp_path):
    def build(*scenarios, **settings):
        if scenarios:
            fake.sequence(*scenarios)
        fake.set(**settings)
        return ClaudeConnector(ConnectorConfig(**fake.config_kwargs(tmp_path)))
    return build


class Seen(Hooks):
    def __init__(self):
        self.records, self.quotas = [], []

    def after_call(self, record):
        self.records.append(record)

    def on_quota(self, provider, quota):
        self.quotas.append(quota)


def raised(conn, *, schema=None, **kw):
    """The ConnectorError of one call (or None)."""
    try:
        if schema is not None:
            conn.call_json("Say ok.", schema=schema, **kw)
        else:
            conn.call_text("Say ok.", **kw)
    except Exception as e:                                       # noqa: BLE001
        return e
    return None


# ---- the table is the single source -------------------------------------------------------------------------------------------

def test_every_row_of_the_design_has_a_case():
    doc = DESIGN.read_text(encoding="utf-8")
    start = doc.index("### 3.4 `ClaudeConnector`")
    rows = set(re.findall(r"^\| (C\d+) \|", doc[start:doc.index("### 3.5", start)], re.M))
    assert rows == {f"C{n}" for n in range(1, 26)}
    assert {re.match(r"C\d+", key).group(0) for key in CLAUDE_ERROR_MAP} == rows
    assert set(CLAUDE_ERROR_MAP) == set(SCENARIO) | {"C1"}                   # the fake has a preset for every row but C1
    assert {code for code in CLAUDE_ERROR_MAP.values() if code != "ok"} <= set(ERROR_CLASSES)


# ---- one case per row ---------------------------------------------------------------------------------------------------------------

def expect(row, err, conn, fake):
    """Row-specific facts beyond the code."""
    if row == "C2":
        assert err.detail["flag"] == "--no-such-flag" and "--no-such-flag" in err.user_message()
    elif row == "C3a":
        assert err.detail["flag"] == "--json-schema"
    elif row == "C3b":
        assert err.detail["flag"] == "--system-prompt-file"
    elif row in ("C4", "C5", "C19a", "C19b", "C19c"):
        assert isinstance(err, NotSignedIn) and "claude auth login" in err.user_message()
    elif row.startswith("C6"):
        assert err.detail["reason"] == {"C6a": "oauth_org_not_allowed", "C6b": "account_on_hold", "C6c": "verification_required"}[row]
    elif row == "C7":
        assert isinstance(err, QuotaExhausted) and err.resets_at == 1793748600       # from the rejected rate_limit_event
    elif row == "C9":
        assert err.resets_at is None and err.detail["reason"] == "billing_error"
    elif row == "C13":
        assert err.detail["model"] == "sonnet"
    elif row == "C14":
        assert "partial reply cut by the output limit" in err.detail["partial"]
    elif row == "C15":
        assert isinstance(err, StructuredOutputFailed)
    elif row == "C19d":
        assert err.detail["status"] == 429
    elif row == "C19e":
        assert err.detail["status"] == 503
    elif row == "C20":
        assert err.detail["exit"] == 137
    elif row == "C24":
        assert err.kind == "bad_output"


@pytest.mark.parametrize("row", sorted(CLAUDE_ERROR_MAP, key=lambda r: (int(re.match(r"C(\d+)", r).group(1)), r)))
def test_row(row, fake, make, tmp_path, monkeypatch):
    code = CLAUDE_ERROR_MAP[row]
    if row == "C1":                                              # PATH emptied: the bare name cannot be found
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        conn = ClaudeConnector(ConnectorConfig(**dict(fake.config_kwargs(tmp_path), claude_exe="claude")))
        err = raised(conn)
        assert isinstance(err, CliMissing) and "install it and run `claude`" in err.user_message()
    elif row == "C22":                                           # the total deadline
        err = raised(make(SCENARIO[row]), timeout=0.6)
        assert err.detail["which"] == "total" and err.detail["seconds"] == 0.6
    elif row == "C23":                                           # stop() while it runs
        err = _stop_during_slow(fake, make)
    elif row == "C16":                                           # a resumed chat turn
        conn = make(SCENARIO[row], FAKE_PATCH=None)
        state = conn.start(SessionSpec(session_id="cs_c16"))
        state.provider_session_id = "00000000-0000-4000-8000-0000000000ff"
        err = raised_send(conn, state)
    elif row == "C25":                                           # noise between events is skipped, the call succeeds
        turn = make(SCENARIO[row]).call_text("Say ok.")
        assert turn.text and code == "ok"
        return
    elif row == "C2":
        err = raised(make(SCENARIO[row], FAKE_BAD_FLAG="--no-such-flag"))
    else:
        err = raised(make(SCENARIO[row]))
    assert err is not None, f"{row} did not fail"
    assert err.code == code, f"{row}: {err.code} / {err}"
    assert err.provider == "claude" and err.detail.get("cli") in ("claude", None)
    assert err.as_dict()["code"] == code
    expect(row, err, None, fake)


def raised_send(conn, state):
    try:
        conn.send(state, Message(role="user", text="hi"))
    except Exception as e:                                       # noqa: BLE001
        return e
    return None


def _stop_during_slow(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.2")
    state = conn.start(SessionSpec(session_id="cs_c23"))
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


# ---- what the table does not spell out ------------------------------------------------------------------------------------------

def test_a_cancelled_call_is_the_cancelled_class(fake, make):
    err = _stop_during_slow(fake, make)
    assert isinstance(err, CallCancelledError) and not err.retryable and not err.fallback_ok


def test_the_idle_deadline_applies_only_to_streams_with_partials(fake, make):
    conn = make("hang")
    conn.idle_timeout_s = 0.6
    state = conn.start(SessionSpec(session_id="cs_idle"))
    began = time.time()
    with pytest.raises(CallTimeoutError) as caught:
        list(conn.stream(state, Message(role="user", text="go"), partials=True))
    assert caught.value.detail["which"] == "idle" and caught.value.detail["seconds"] == 0.6 and time.time() - began < 8
    assert "did not answer within 0.6 s" in caught.value.user_message()


def test_a_timeout_without_partials_waits_for_the_total_deadline_not_the_idle_one(fake, make):
    conn = make("slow", FAKE_LINE_DELAY="0.4")
    conn.idle_timeout_s = 0.1                                     # would fire after 0.1 s of silence if it applied
    turn = conn.call_text("x", timeout=30)
    assert turn.provider == "claude"


def test_a_good_result_with_a_bad_exit_is_a_crash(fake, make):
    err = raised(make("ok_plain", FAKE_EXIT_CODE="3"))
    assert err.code == "crashed" and err.detail["exit"] == 3 and err.retryable


def test_a_file_that_cannot_run_is_a_missing_cli(fake, make, tmp_path):
    script = tmp_path / "claude-noexec"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o644)
    conn = ClaudeConnector(ConnectorConfig(**dict(fake.config_kwargs(tmp_path), claude_exe=str(script))))
    err = raised(conn)
    assert isinstance(err, CliMissingError) and err.provider == "claude"


def test_the_quota_event_reaches_the_health_hook_even_when_the_call_fails(fake, make):
    seen = Seen()
    err = raised(make("quota"), hooks=seen)
    assert err.code == "quota"
    assert [(q.status, q.window, q.resets_at) for q in seen.quotas] == [("exhausted", "five_hour", 1793748600.0)]
    assert seen.records[0].code == "quota" and seen.records[0].ok is False


def test_an_error_never_carries_the_prompt_or_the_system_text(fake, make):
    secret_prompt, secret_system = "PROMPT-SECRET-123", "SYSTEM-SECRET-456"
    err = raised(make("not_logged_in"))
    conn = make("overloaded")
    try:
        conn.call_text(secret_prompt, system=secret_system)
    except Exception as e:                                       # noqa: BLE001
        err = e
    dumped = json.dumps(err.as_dict()) + str(err) + err.user_message() + json.dumps(err.detail)
    assert secret_prompt not in dumped and secret_system not in dumped


# ---- parser-level cases for exits and fields the fake cannot make ---------------------------------------------------------------

def plan(**kw):
    return TurnPlan(prompt="p", ctx=RouteContext(), model="sonnet", effort="low", **kw)


def finish(lines, *, code=0, stderr="", reason="exit", **plan_kw):
    parser = ClaudeParser(plan(**plan_kw), version="2.1.308")
    for line in lines:
        parser.feed(json.dumps(line) if isinstance(line, dict) else line)
    return parser.finish(ExitInfo(returncode=code, reason=reason, stderr_tail=stderr, seconds=0.1, pid=1))


def result(**fields):
    base = {"type": "result", "subtype": "success", "is_error": False, "result": "ok", "total_cost_usd": 0, "usage": {}, "num_turns": 1}
    base.update(fields)
    return base


def assistant_error(error, text="boom"):
    return {"type": "assistant", "error": error, "is_api_error_message": True, "message": {"content": [{"type": "text", "text": text}]}}


def code_of(*args, **kw):
    with pytest.raises(Exception) as caught:
        finish(*args, **kw)
    return caught.value


def test_a_signal_death_without_a_result_is_a_crash_naming_the_signal():
    err = code_of([{"type": "system", "subtype": "init"}], code=-9)
    assert err.code == "crashed" and err.detail["exit"] == "SIGKILL" and err.detail["version"] == "2.1.308"


def test_empty_output_with_exit_zero_is_a_protocol_error():
    assert code_of([], code=0).code == "protocol_error"


def test_nothing_on_stdout_and_a_bad_exit_with_other_words_is_a_crash():
    err = code_of([], code=2, stderr="something odd happened")
    assert err.code == "crashed" and err.detail["stderr"] == "something odd happened"


def test_unknown_option_is_read_from_stderr_without_a_quote_too():
    err = code_of([], code=1, stderr="error: unknown option '--turbo'\n")
    assert err.code == "cli_flag_unsupported" and err.detail["flag"] == "--turbo" and "--turbo" in err.user_message()


def test_a_stderr_session_message_without_a_result_is_a_lost_session():
    assert code_of([], code=1, stderr="No conversation found with session ID: x").code == "session_lost"


def test_rate_limit_text_without_the_event_still_means_quota_but_has_no_reset_time():
    err = code_of([assistant_error("rate_limit", "You've hit your limit"), result(is_error=True, result="You've hit your limit")])
    assert err.code == "quota" and err.resets_at is None


def test_an_unknown_assistant_error_falls_to_the_status_of_the_result():
    lines = [assistant_error("unknown", "weird"), result(is_error=True, api_error_status=529, result="weird")]
    assert code_of(lines).code == "overloaded"
    lines = [assistant_error("cloud_credential_error", "cred"), result(is_error=True, api_error_status=None, result="cred")]
    err = code_of(lines)
    assert err.code == "provider_error" and err.user_message() == "cred"


def test_a_failed_result_without_any_hint_is_a_provider_error_with_the_cli_text():
    err = code_of([result(is_error=True, result="x" * 1000)])
    assert err.code == "provider_error" and len(err.message) == 300


def test_other_result_subtypes_are_provider_errors():
    err = code_of([result(subtype="error_max_turns")])
    assert err.code == "provider_error" and err.detail["subtype"] == "error_max_turns"


def test_structured_retry_exhaustion_beats_a_generic_error():
    err = code_of([result(subtype="error_max_structured_output_retries", is_error=True)], schema={"type": "object"})
    assert err.code == "structured" and err.detail["subtype"] == "error_max_structured_output_retries"


def test_a_missing_structured_output_is_an_error_only_when_a_schema_was_sent():
    assert code_of([result()], schema={"type": "object"}).code == "structured"
    assert finish([result()]).text == "ok"


def test_a_blank_reply_with_a_structured_object_is_not_empty():
    turn = finish([result(result="", structured_output={"a": 1})])
    assert turn.structured == {"a": 1}
    assert code_of([result(result="  \n")]).code == "empty_reply"


def test_the_timeout_and_cancel_reasons_come_before_everything_else():
    ok = [result()]
    assert code_of(ok, reason="total_timeout", timeout_s=7.0).detail == {"cli": "claude", "version": "2.1.308", "which": "total", "seconds": 7.0}
    assert code_of(ok, reason="idle_timeout", idle_timeout_s=3.0, partials=True).detail["which"] == "idle"
    assert code_of(ok, reason="cancelled").code == "cancelled"


def test_a_lost_session_needs_zero_turns_and_the_words():
    lines = [result(subtype="error_during_execution", is_error=True, num_turns=0, errors=["No conversation found with session ID: z"])]
    assert code_of(lines).code == "session_lost"
    lines = [result(subtype="error_during_execution", is_error=True, num_turns=2, errors=["No conversation found with session ID: z"])]
    assert code_of(lines).code == "provider_error"
    lines = [result(subtype="error_during_execution", is_error=True, num_turns=0, errors=["disk full"])]
    assert code_of(lines).code == "provider_error"
