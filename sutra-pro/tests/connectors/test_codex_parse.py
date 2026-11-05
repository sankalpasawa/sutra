"""CodexParser and the small parsers of codex.py against the captured and derived Codex streams (work package CN-4, design 3.5).

No process runs here: the parser is fed the fixture lines and an ExitInfo. Counters follow row 6 of the design
(`turn.completed.usage` is cumulative for the thread, a turn is the difference to the session's `cum_usage`).
"""
from __future__ import annotations

import json
import time

import pytest

from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.codex import (
    CodexParser, parse_device_auth, parse_reset_time, quota_from_rate_limits, strip_ansi,
)
from sutra_app.connectors.models import RouteContext, Usage
from sutra_app.connectors.policy import Rate
from sutra_app.connectors.process import ExitInfo

THREAD = "01a1a2b8-6719-7e71-83fa-bcf21c8c1649"


def plan(**kw):
    return TurnPlan(prompt="hello", ctx=RouteContext(), model="gpt-5.6-luna", effort="low", **kw)


def ended(code=0, reason="exit", stderr="", seconds=0.1):
    return ExitInfo(returncode=code, reason=reason, stderr_tail=stderr, seconds=seconds, pid=1)


def lines_of(fixtures, rel):
    return fixtures.text(rel).split("\n")[:-1]


def run(fixtures, rel, parser_plan=None, exit_info=None, **kw):
    parser = CodexParser(parser_plan or plan(), **kw)
    events = []
    for line in lines_of(fixtures, rel):
        events.extend(parser.feed(line))
    return parser, events, parser.finish(exit_info or ended())


# ---- the captured streams ---------------------------------------------------------------------------------------------------

def test_structured_fixture_event_order_and_reply(fixtures):
    _, events, turn = run(fixtures, "codex/exec_structured_ok.jsonl", plan(schema={"type": "object"}))
    assert [e.kind for e in events] == ["started", "text"]
    assert events[0].data == {"session_id": THREAD} and events[1].data == {"text": '{"answer":"ok"}'}
    assert turn.text == '{"answer":"ok"}' and turn.structured == {"answer": "ok"}
    assert turn.provider == "codex" and turn.model == "gpt-5.6-luna" and turn.provider_session_id == THREAD


def test_fresh_usage_is_the_whole_counter_with_cached_split_out(fixtures):
    parser, _, turn = run(fixtures, "codex/exec_structured_ok.jsonl")
    assert turn.usage == Usage(input_tokens=12168, output_tokens=15) and turn.usage.input_total == 12168
    assert parser.cum_usage == turn.usage and parser.cum_usd is None


def test_resume_fixture_charges_only_the_difference(fixtures):
    """24,342 cumulative input of which 10,368 cached, after a call of 12,168: this turn is 12,174 / 10,368 cached / 5."""
    before = Usage(input_tokens=12168, output_tokens=15)
    parser, _, turn = run(fixtures, "codex/exec_resume_plain_ok.jsonl", plan(cum_usage=before, resume=True))
    assert turn.usage == Usage(input_tokens=1806, cached_input_tokens=10368, output_tokens=5)
    assert turn.usage.input_total == 12174 and turn.usage.output_tokens == 5
    assert parser.cum_usage == Usage(input_tokens=13974, cached_input_tokens=10368, output_tokens=20)
    assert turn.text == "ok" and turn.structured is None            # no schema was sent


def test_a_counter_that_goes_backwards_is_taken_whole(fixtures):
    big = Usage(input_tokens=99999, cached_input_tokens=5, output_tokens=999)
    _, _, turn = run(fixtures, "codex/exec_structured_ok.jsonl", plan(cum_usage=big))
    assert turn.usage == Usage(input_tokens=12168, output_tokens=15)


def test_missing_usage_object_charges_nothing_and_keeps_the_baseline(fixtures):
    parser = CodexParser(plan(cum_usage=Usage(output_tokens=7)))
    for line in ('{"type":"item.completed","item":{"type":"agent_message","text":"hi"}}', '{"type":"turn.completed"}'):
        parser.feed(line)
    turn = parser.finish(ended())
    assert turn.usage == Usage() and parser.cum_usage is None


def test_reasoning_tokens_are_read_and_cache_writes_kept():
    parser = CodexParser(plan())
    parser.feed('{"type":"item.completed","item":{"type":"agent_message","text":"hi"}}')
    parser.feed(json.dumps({"type": "turn.completed", "usage": {
        "input_tokens": 100, "cached_input_tokens": 40, "cache_write_input_tokens": 7, "output_tokens": 30, "reasoning_output_tokens": 12}}))
    turn = parser.finish(ended())
    assert turn.usage == Usage(input_tokens=60, cached_input_tokens=40, cache_write_tokens=7, output_tokens=30, reasoning_tokens=12)


# ---- cost ---------------------------------------------------------------------------------------------------------------------

def test_without_rates_the_cost_is_unknown(fixtures):
    _, _, turn = run(fixtures, "codex/exec_structured_ok.jsonl")
    assert turn.usd is None and turn.usd_basis == "unknown"


def test_with_rates_the_cost_is_rate_card_times_the_delta(fixtures):
    rate = Rate(in_per_mtok=2.0, cached_in_per_mtok=0.5, out_per_mtok=10.0)
    before = Usage(input_tokens=12168, output_tokens=15)
    _, _, turn = run(fixtures, "codex/exec_resume_plain_ok.jsonl", plan(cum_usage=before), rate=rate)
    assert turn.usd == pytest.approx((1806 * 2.0 + 10368 * 0.5 + 5 * 10.0) / 1e6) and turn.usd_basis == "rate_card"


def test_a_rate_with_a_null_price_leaves_the_cost_unknown(fixtures):
    _, _, turn = run(fixtures, "codex/exec_structured_ok.jsonl", rate=Rate(in_per_mtok=2.0, out_per_mtok=None))
    assert turn.usd is None and turn.usd_basis == "unknown"


# ---- the reply ------------------------------------------------------------------------------------------------------------------

def test_the_reply_is_the_last_non_blank_agent_message():
    parser = CodexParser(plan())
    for text in ("first", "second", "  "):
        parser.feed(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}))
    parser.feed('{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}')
    assert parser.finish(ended()).text == "second"


def test_a_schema_reply_that_is_not_json_has_no_structured_value_and_is_left_to_the_base(fixtures):
    _, _, turn = run(fixtures, "derived/codex_reply_not_json.jsonl", plan(schema={"type": "object"}))
    assert turn.structured is None and turn.text


def test_unknown_item_types_are_tool_calls_and_do_not_disturb_the_reply(fixtures):
    parser, events, turn = run(fixtures, "derived/codex_unknown_item_type.jsonl")
    assert [e.kind for e in events] == ["started", "tool_call", "text"]
    assert events[1].data == {"type": "command_execution", "id": "item_0"} and parser.tool_types == ["command_execution"]
    assert turn.text == '{"answer":"ok"}'


def test_item_errors_and_top_level_errors_are_notices():
    parser = CodexParser(plan())
    events = parser.feed('{"type":"error","message":"Reconnecting... 1/5"}')
    events += parser.feed('{"type":"item.completed","item":{"type":"error","message":"Falling back to HTTPS"}}')
    assert [(e.kind, e.data["text"]) for e in events] == [("notice", "Reconnecting... 1/5"), ("notice", "Falling back to HTTPS")]


def test_noise_and_unknown_event_types_are_ignored_and_counted():
    parser = CodexParser(plan())
    assert parser.feed("Reading additional input from stdin...") == [] and parser.feed("[1, 2]") == []
    assert parser.feed('{"type":"turn.started"}') == [] and parser.feed('{"type":"brand.new"}') == [] and parser.feed('{"type":7}') == []
    assert (parser.skipped, parser.objects) == (2, 3)


def test_duration_comes_from_the_exit_info(fixtures):
    _, _, turn = run(fixtures, "codex/exec_structured_ok.jsonl", exit_info=ended(seconds=2.5))
    assert turn.duration_ms == 2500


def test_a_turn_that_completed_counts_even_when_the_exit_code_is_bad(fixtures):
    _, _, turn = run(fixtures, "codex/exec_structured_ok.jsonl", exit_info=ended(code=1))
    assert turn.text == '{"answer":"ok"}'


# ---- the 401 streak ---------------------------------------------------------------------------------------------------------------

class FakeProc:
    def __init__(self):
        self.cancelled = 0

    def cancel(self):
        self.cancelled += 1
        return True


def test_two_401_errors_in_a_row_stop_the_process_once(fixtures):
    parser = CodexParser(plan())
    parser.proc = FakeProc()
    for line in lines_of(fixtures, "codex/exec_not_signed_in.jsonl")[:4]:      # started, turn.started, two 401 errors
        parser.feed(line)
    assert parser.auth_aborted and parser.proc.cancelled == 1
    for line in lines_of(fixtures, "codex/exec_not_signed_in.jsonl")[4:7]:
        parser.feed(line)
    assert parser.proc.cancelled == 1                                          # stopped once, not once per later line


def test_a_non_401_error_or_a_reply_resets_the_streak():
    parser = CodexParser(plan())
    parser.proc = FakeProc()
    for line in ('{"type":"error","message":"unexpected status 401 Unauthorized"}', '{"type":"error","message":"stream disconnected"}',
                 '{"type":"error","message":"unexpected status 401 Unauthorized"}',
                 '{"type":"item.completed","item":{"type":"agent_message","text":"x"}}',
                 '{"type":"error","message":"unexpected status 401 Unauthorized"}'):
        parser.feed(line)
    assert not parser.auth_aborted and parser.proc.cancelled == 0


def test_a_request_id_that_contains_401_is_not_a_401():
    parser = CodexParser(plan())
    parser.proc = FakeProc()
    for _ in range(3):
        parser.feed('{"type":"error","message":"stream error, request id: req_4401abc, cf-ray: a54d401e-BOM"}')
    assert not parser.auth_aborted


# ---- helpers ------------------------------------------------------------------------------------------------------------------------

def test_parse_device_auth_strips_ansi_and_reads_link_and_code(fixtures):
    text = fixtures.text("codex/login_device_auth.txt")
    assert "\x1b[" in text                                                     # the capture really has colours
    url, code = parse_device_auth(text.split("\n"))
    assert url == "https://auth.openai.com/codex/device" and code == "ABCD-EFGHJ"
    assert strip_ansi("\x1b[94mhttps://x\x1b[0m") == "https://x"


def test_parse_device_auth_needs_both_and_ignores_a_code_before_the_link():
    assert parse_device_auth(["Welcome", "ABCD-EFGH before any link"]) == (None, None)
    assert parse_device_auth(["go to https://auth.example/device."]) == ("https://auth.example/device", None)


def test_parse_reset_time_reads_the_dated_form_in_local_time():
    now = time.mktime((2026, 11, 4, 12, 0, 0, 0, 0, -1))
    said = "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage or try again at Nov 5th, 2026 4:30 PM."
    assert parse_reset_time(said, now) == time.mktime((2026, 11, 5, 16, 30, 0, 0, 0, -1))
    assert parse_reset_time("try again at December 1, 2026 9:05 AM", now) == time.mktime((2026, 12, 1, 9, 5, 0, 0, 0, -1))


def test_parse_reset_time_with_only_a_clock_time_is_the_next_such_time():
    now = time.mktime((2026, 11, 4, 12, 0, 0, 0, 0, -1))
    assert parse_reset_time("try again at 4:30 PM.", now) == time.mktime((2026, 11, 4, 16, 30, 0, 0, 0, -1))
    assert parse_reset_time("try again at 9:00 AM", now) == time.mktime((2026, 11, 4, 9, 0, 0, 0, 0, -1)) + 86400.0


def test_parse_reset_time_gives_up_quietly():
    now = 1.0e9
    assert parse_reset_time("You've hit your usage limit.", now) is None
    assert parse_reset_time("try again at some point", now) is None


def test_quota_from_the_captured_rollout_line(fixtures):
    line = json.loads(fixtures.text("codex/rollout_token_count.jsonl").split("\n")[0])
    quota = quota_from_rate_limits(line["payload"]["rate_limits"])
    assert (quota.status, quota.window, quota.used, quota.plan, quota.source) == ("ok", "thirty_day", 0.0, "go", "rollout")
    assert quota.resets_at == 1796323361.0


@pytest.mark.parametrize(("limits", "status"), [
    ({"primary": {"used_percent": 79.9}}, "ok"), ({"primary": {"used_percent": 80}}, "warning"),
    ({"primary": {"used_percent": 100}}, "exhausted"), ({"primary": {"used_percent": 3}, "rate_limit_reached_type": "primary"}, "exhausted"),
    ({"primary": {"window_minutes": 300}}, "unknown")])
def test_quota_status_thresholds(limits, status):
    assert quota_from_rate_limits(limits).status == status


def test_quota_shows_the_fuller_window_and_none_without_windows():
    quota = quota_from_rate_limits({"primary": {"used_percent": 10, "window_minutes": 300, "resets_at": 5},
                                    "secondary": {"used_percent": 90, "window_minutes": 10080, "resets_at": 9}})
    assert (quota.window, quota.used, quota.resets_at, quota.status) == ("seven_day", 0.9, 9.0, "warning")
    assert quota_from_rate_limits({"primary": None, "secondary": None}) is None and quota_from_rate_limits({}) is None
