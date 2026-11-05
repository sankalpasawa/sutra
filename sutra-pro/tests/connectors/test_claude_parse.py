"""ClaudeParser against the captured and derived Claude streams, line by line (work package CN-3, connectors design 3.4).

No process runs here: the parser is fed the fixture lines and an ExitInfo. Counters follow row 6 of the design (usage is per
turn, cost and modelUsage are cumulative for a session).
"""
from __future__ import annotations

import json

import pytest

from sutra_app.connectors.claude import ClaudeParser
from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.models import RouteContext, Usage
from sutra_app.connectors.process import ExitInfo


def plan(**kw):
    return TurnPlan(prompt="hello", ctx=RouteContext(), model="sonnet", effort="low", **kw)


def ended(code=0, reason="exit", stderr=""):
    return ExitInfo(returncode=code, reason=reason, stderr_tail=stderr, seconds=0.1, pid=1)


def lines_of(fixtures, rel):
    return fixtures.text(rel).split("\n")[:-1]


def run(fixtures, rel, parser_plan=None, exit_info=None):
    parser = ClaudeParser(parser_plan or plan())
    events = []
    for line in lines_of(fixtures, rel):
        events.extend(parser.feed(line))
    return parser, events, parser.finish(exit_info or ended())


def test_structured_fixture_event_order(fixtures):
    _, events, _ = run(fixtures, "claude/stream_structured_ok.jsonl")
    assert [e.kind for e in events] == ["started", "tool_call", "tool_result", "quota"]
    started = events[0].data
    assert started["session_id"] == "092c7b68-7118-42da-ba0a-57fa2e5ef699" and started["model"] == "claude-sonnet-5-5"
    assert started["tools"] == ["StructuredOutput"] and started["mcp_servers"] == []
    assert events[1].data["name"] == "StructuredOutput" and events[1].data["input"] == {"answer": "ok"}
    assert events[2].data["tool_use_id"] == events[1].data["id"] and "successfully" in events[2].data["content"]


def test_structured_fixture_result(fixtures):
    _, _, turn = run(fixtures, "claude/stream_structured_ok.jsonl", plan(schema={"type": "object"}))
    assert turn.structured == {"answer": "ok"} and turn.text == '{"answer":"ok"}'
    assert turn.usage == Usage(input_tokens=2, cached_input_tokens=1079, cache_write_tokens=2276, output_tokens=53)
    assert turn.usage.input_total == 3357 and turn.usage.output_tokens == 53
    assert turn.usd == 0.0097459 and turn.usd_basis == "reported"
    assert turn.model == "claude-sonnet-5-5" and turn.provider == "claude" and turn.subtype == "success"
    assert turn.provider_session_id == "092c7b68-7118-42da-ba0a-57fa2e5ef699" and turn.duration_ms == 2357
    assert turn.quota.status == "ok" and turn.quota.window == "five_hour" and turn.quota.used == 0.09
    assert turn.quota.resets_at == 1793748600 and turn.quota.source == "rate_limit_event"


def test_resume_fixture_charges_only_the_difference(fixtures):
    parser, _, turn = run(fixtures, "claude/stream_resume_plain_ok.jsonl", plan(cum_usd=0.0097459))
    assert turn.usd == pytest.approx(0.0092889, abs=1e-9)             # not 0.0190348
    assert turn.usage.input_total == 2947 and turn.usage.output_tokens == 4
    assert parser.cum_usd == pytest.approx(0.0190348, abs=1e-7)
    assert turn.text == "ok" and turn.structured is None


def test_session_counters_add_the_turns(fixtures):
    first, _, _ = run(fixtures, "claude/stream_structured_ok.jsonl")
    second, _, _ = run(fixtures, "claude/stream_resume_plain_ok.jsonl", plan(cum_usd=first.cum_usd, cum_usage=first.cum_usage))
    assert second.cum_usage == Usage(input_tokens=6, cached_input_tokens=1728, cache_write_tokens=4570, output_tokens=57)


def test_a_counter_that_goes_backwards_is_taken_whole(fixtures):
    _, _, turn = run(fixtures, "claude/stream_structured_ok.jsonl", plan(cum_usd=5.0))
    assert turn.usd == 0.0097459


def test_partials_become_text_deltas_only_when_asked(fixtures):
    stream = [json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
                                                            "delta": {"type": kind, key: value}}})
              for kind, key, value in (("text_delta", "text", "Hel"), ("input_json_delta", "partial_json", '{"a"'),
                                       ("thinking_delta", "thinking", "hmm"))]
    quiet, loud = ClaudeParser(plan()), ClaudeParser(plan(partials=True))
    assert [quiet.feed(line) for line in stream] == [[], [], []]
    got = [e for line in stream for e in loud.feed(line)]
    assert [(e.kind, e.data) for e in got] == [("text_delta", {"text": "Hel", "kind": "text"}),
                                               ("text_delta", {"text": '{"a"', "kind": "json"})]


def test_assistant_text_and_tool_calls_become_events():
    parser = ClaudeParser(plan())
    events = parser.feed(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Let me look."}, {"type": "tool_use", "id": "t1", "name": "mcp__sutra__sutra_chart_read", "input": {"depth": 1}},
        "junk", {"type": "image"}]}}))
    assert [(e.kind, e.data) for e in events] == [
        ("text", {"text": "Let me look."}),
        ("tool_call", {"id": "t1", "name": "mcp__sutra__sutra_chart_read", "input": {"depth": 1}})]


def test_an_error_text_is_not_an_answer_event(fixtures):
    parser = ClaudeParser(plan())
    events = [e for line in lines_of(fixtures, "claude/stream_not_logged_in.jsonl") for e in parser.feed(line)]
    assert [e.kind for e in events] == ["started"]               # "Not logged in" is kept for the error, not shown as text
    assert parser.assistant_error == "authentication_failed"


def test_tool_result_content_is_cut_and_flagged():
    parser = ClaudeParser(plan())
    events = parser.feed(json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t9", "is_error": True, "content": [{"type": "text", "text": "x" * 5000}]}]}}))
    assert events[0].kind == "tool_result" and events[0].data["is_error"] is True and len(events[0].data["content"]) == 2000


def test_connected_mcp_server_has_no_notice(fixtures):
    parser = ClaudeParser(plan())
    events = [e for line in lines_of(fixtures, "claude/stream_tool_profile_init.jsonl") for e in parser.feed(line)]
    assert [e.kind for e in events] == ["started"]
    assert events[0].data["mcp_servers"][0]["name"] == "sutra" and events[0].data["tools"] == ["mcp__sutra__ping"]


def test_a_server_that_is_not_connected_adds_a_notice():
    parser = ClaudeParser(plan())
    init = {"type": "system", "subtype": "init", "session_id": "s", "model": "m", "tools": [],
            "mcp_servers": [{"name": "sutra", "status": "connected"}, {"name": "gh", "status": "failed"}]}
    events = parser.feed(json.dumps(init))
    assert [e.kind for e in events] == ["started", "notice"]
    assert events[1].data["server"] == "gh" and "failed" in events[1].data["text"]


def test_noise_lines_are_skipped_and_counted(fixtures):
    parser, events, turn = run(fixtures, "derived/claude_noise_lines.jsonl")
    assert parser.skipped >= 1 and turn.text
    clean, clean_events, _ = run(fixtures, "claude/stream_resume_plain_ok.jsonl")
    assert clean.skipped == 0


def test_other_json_and_unknown_types_are_ignored():
    parser = ClaudeParser(plan())
    assert parser.feed("[1, 2]") == [] and parser.feed("42") == [] and parser.feed("") == [] and parser.feed("Warning: hi") == []
    assert parser.feed(json.dumps({"type": "something_new", "x": 1})) == []
    assert parser.feed(json.dumps({"type": "system", "subtype": "status", "status": "requesting"})) == []
    assert parser.feed(json.dumps({"no_type": True})) == []
    assert parser.skipped == 4 and parser.objects == 3


@pytest.mark.parametrize("status,expected", [("allowed", "ok"), ("allowed_warning", "warning"), ("rejected", "exhausted"),
                                             ("something", "unknown")])
def test_quota_status_mapping(status, expected):
    parser = ClaudeParser(plan())
    events = parser.feed(json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": status, "resetsAt": 1793748600, "rateLimitType": "seven_day", "utilization": 0.5}}))
    assert events[0].kind == "quota" and events[0].data["status"] == expected
    assert events[0].data["window"] == "seven_day" and events[0].data["used"] == 0.5     # top-level utilization is the fallback
    assert parser.feed(json.dumps({"type": "rate_limit_event", "rate_limit_info": "bad"})) == []


def test_reasoning_tokens_are_a_subset_of_output():
    parser = ClaudeParser(plan())
    parser.feed(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok", "total_cost_usd": 0.5,
                            "usage": {"input_tokens": 1, "output_tokens": 10, "output_tokens_details": {"thinking_tokens": 99}},
                            "modelUsage": {}}))
    turn = parser.finish(ended())
    assert turn.usage.reasoning_tokens == 10 and turn.model is None and turn.duration_ms is None and turn.usd == 0.5


def test_garbage_counters_count_as_zero():
    parser = ClaudeParser(plan())
    parser.feed(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok", "total_cost_usd": "free",
                            "usage": {"input_tokens": True, "output_tokens": -4, "cache_read_input_tokens": 2.5}}))
    turn = parser.finish(ended())
    assert turn.usage == Usage() and turn.usd == 0.0
