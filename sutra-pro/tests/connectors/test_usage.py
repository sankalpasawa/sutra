"""Usage normalisation, delta rules, the UsageIn row and its sinks (CN-6, connectors 3.8, S1-contracts-05, S4-fnodes-07)."""
from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.connectors.models import Allowance, RouteContext, SessionState, Usage
from sutra_app.connectors.policy import Rate
from sutra_app.connectors.usage import (
    HOW_VALUES, Attempt, MemoryUsageSink, UsageIn, UsageSink, build_usage_row, call_ref, cost_delta, cumulative_delta,
    load_session_state, new_request_id, rate_card_usd, save_session_state, session_path, step_label, usage_from_claude,
    usage_from_codex,
)
from sutra_app.engine.events import EventUsageSink, EventWriter
from sutra_app.engine.port import CallTag

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "connectors"


def result_line(rel):
    for line in (FIX / rel).read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("type") in ("result", "turn.completed"):
            return obj
    raise AssertionError(rel)


def ctx(**tag):
    session_id = tag.pop("session_id", None)
    node_id = tag.pop("node_id", None)
    allowance = tag.pop("allowance", Allowance())
    return RouteContext(tag=CallTag(**tag), session_id=session_id, node_id=node_id, allowance=allowance)


def ok_attempt(provider="claude", **kw):
    kw.setdefault("usage", Usage(input_tokens=10, output_tokens=5))
    kw.setdefault("usd", 0.01)
    return Attempt(provider=provider, model="m", **kw)


# ---- normalising what the CLIs print --------------------------------------------------------------------------------------
def test_usage_from_claude_maps_cache_read_to_cached_and_creation_to_writes():
    usage = usage_from_claude({"input_tokens": 2, "cache_creation_input_tokens": 2276, "cache_read_input_tokens": 1079,
                               "output_tokens": 53, "junk": "x"})
    assert usage == Usage(input_tokens=2, cached_input_tokens=1079, cache_write_tokens=2276, output_tokens=53)
    assert usage.input_total == 3357


def test_usage_from_codex_input_includes_cached_so_fresh_is_the_difference():
    usage = usage_from_codex({"input_tokens": 24342, "cached_input_tokens": 10368, "cache_write_input_tokens": 3,
                              "output_tokens": 20, "reasoning_output_tokens": 7})
    assert usage == Usage(input_tokens=13974, cached_input_tokens=10368, cache_write_tokens=3, output_tokens=20, reasoning_tokens=7)


def test_normalising_tolerates_missing_none_negative_and_non_numbers():
    assert usage_from_claude(None) == Usage() and usage_from_codex({}) == Usage()
    assert usage_from_claude({"input_tokens": -5, "output_tokens": "3", "cache_read_input_tokens": True}) == Usage()
    assert usage_from_codex({"input_tokens": 5, "cached_input_tokens": 9}).input_tokens == 0        # never below zero
    assert usage_from_claude({"output_tokens": 4.9}).output_tokens == 4


# ---- delta rules (CD5) ------------------------------------------------------------------------------------------------------
def test_claude_cost_is_the_delta_of_the_cumulative_total_from_the_fixtures():
    first = result_line("claude/stream_structured_ok.jsonl")["total_cost_usd"]
    second = result_line("claude/stream_resume_plain_ok.jsonl")["total_cost_usd"]
    assert cost_delta(first, 0.0) == pytest.approx(0.0097459, abs=1e-12)
    assert cost_delta(second, first) == pytest.approx(0.0092889, abs=1e-12)        # not 0.0190348


def test_claude_cost_counter_going_backwards_is_taken_whole_and_never_negative():
    assert cost_delta(0.004, 0.019) == 0.004
    assert cost_delta(0.019, 0.019) == 0.0
    assert cost_delta(0.0, 0.0) == 0.0


def test_codex_tokens_are_the_delta_of_the_cumulative_counter_from_the_fixtures():
    first = usage_from_codex(result_line("codex/exec_structured_ok.jsonl")["usage"])
    second = usage_from_codex(result_line("codex/exec_resume_plain_ok.jsonl")["usage"])
    assert cumulative_delta(first, Usage()).input_total == 12168 and first.output_tokens == 15
    delta = cumulative_delta(second, first)
    assert (delta.input_total, delta.cached_input_tokens, delta.output_tokens) == (12174, 10368, 5)


def test_codex_counter_going_backwards_is_taken_whole():
    previous = Usage(input_tokens=500, cached_input_tokens=100, output_tokens=40)
    now = Usage(input_tokens=700, cached_input_tokens=0, output_tokens=10)               # one part dropped: a new session
    assert cumulative_delta(now, previous) == now
    assert cumulative_delta(Usage(), previous) == Usage()                                # all zero is whole too, not negative
    assert cumulative_delta(previous, previous) == Usage()


def test_every_usage_part_is_checked_for_a_restart():
    previous = Usage(input_tokens=1, cached_input_tokens=1, cache_write_tokens=1, output_tokens=1, reasoning_tokens=1)
    for part in Usage.model_fields:
        now = Usage(**{name: 0 if name == part else 50 for name in Usage.model_fields})
        assert cumulative_delta(now, previous) == now, part


# ---- the rate card -------------------------------------------------------------------------------------------------------
def test_rate_card_prices_each_part_per_million():
    rate = Rate(in_per_mtok=2.0, cached_in_per_mtok=0.5, out_per_mtok=10.0, cache_write_per_mtok=4.0)
    usage = Usage(input_tokens=1_000_000, cached_input_tokens=2_000_000, cache_write_tokens=500_000, output_tokens=100_000,
                  reasoning_tokens=60_000)                                                # reasoning is inside output: not added
    assert rate_card_usd(rate, usage) == pytest.approx(2.0 + 1.0 + 2.0 + 1.0)


def test_null_rate_card_means_usd_none_not_zero():
    usage = Usage(input_tokens=100, output_tokens=10)
    assert rate_card_usd(None, usage) is None
    assert rate_card_usd(Rate(), usage) is None
    assert rate_card_usd(Rate(in_per_mtok=1.0), usage) is None                           # output price missing
    assert rate_card_usd(Rate(out_per_mtok=1.0), usage) is None                          # input price missing


def test_rate_card_cached_price_is_needed_only_when_cached_tokens_were_used():
    rate = Rate(in_per_mtok=1.0, out_per_mtok=2.0)
    assert rate_card_usd(rate, Usage(input_tokens=1_000_000)) == pytest.approx(1.0)
    assert rate_card_usd(rate, Usage(cached_input_tokens=1)) is None


def test_rate_card_cache_write_defaults_to_the_input_price():
    rate = Rate(in_per_mtok=3.0, out_per_mtok=1.0)
    assert rate_card_usd(rate, Usage(cache_write_tokens=1_000_000)) == pytest.approx(3.0)


# ---- UsageIn ---------------------------------------------------------------------------------------------------------------
def test_usage_in_fields_and_defaults():
    assert list(UsageIn.model_fields) == [
        "provider", "model", "purpose", "session_id", "node_id", "task_id", "dept_id", "fn", "step", "atom_id", "usd",
        "tokens_in", "tokens_out", "seconds", "ok", "how", "call_ref", "detail"]
    row = UsageIn(provider="claude", purpose="chat", how="chat")
    assert (row.model, row.step, row.atom_id, row.usd, row.ok, row.seconds, row.detail) == ("", None, None, None, True, 0.0, None)


def test_usage_in_is_closed_and_validates():
    good = dict(provider="claude", purpose="summary", how="native")
    UsageIn(**good)
    for bad in ({"extra": 1}, {"provider": "gemini"}, {"purpose": "Bad Purpose"}, {"purpose": ""}, {"how": "magic"}, {"usd": -0.1},
                {"tokens_in": -1}, {"seconds": -1}, {"call_ref": ""}, {"detail": {"x": object()}}, {"detail": {"x": float("nan")}}):
        with pytest.raises(ValidationError):
            UsageIn(**{**good, **bad})
    assert set(HOW_VALUES) == {"native", "prompted", "repaired", "stub", "chat", "text"}


# ---- step_label and call_ref -----------------------------------------------------------------------------------------------
def test_step_label_is_the_builder_id_or_the_j2_letter():
    assert step_label(CallTag(function="W-3", step=4)) == "W-3"                 # a builder: its id wins over the number
    assert [step_label(CallTag(function="identity", step=n)) for n in (1, 3, 8)] == ["J2.a", "J2.c", "J2.h"]
    assert step_label(CallTag(function="identity")) is None
    assert step_label(CallTag(function="Wx-3", step=0)) is None


def test_call_ref_uses_run_and_call_number_else_the_request_id():
    assert call_ref(CallTag(run_id="run_1", call_no=7), "abc") == "run_1:7"
    assert call_ref(CallTag(run_id="run_1", call_no=0), "abc") == "r:abc"
    assert call_ref(CallTag(run_id="", call_no=7), "abc") == "r:abc"             # no run id: it would collide across runs
    assert len({new_request_id() for _ in range(50)}) == 50


# ---- build_usage_row -------------------------------------------------------------------------------------------------------
def test_claude_fresh_row_from_the_fixture_numbers():
    result = result_line("claude/stream_structured_ok.jsonl")
    usage = usage_from_claude(result["usage"])
    attempt = Attempt(provider="claude", model="claude-sonnet-5-5", effort="low", usage=usage,
                      usd=cost_delta(result["total_cost_usd"], 0.0), usd_basis="reported", seconds=4.8, cli_version="2.1.308",
                      billing="subscription")
    row = build_usage_row(ctx=ctx(run_id="run_1", dept_id="d1", task_id="t1", function="identity", step=3, call_no=4, atom="at-1",
                                  purpose="agent_turn"),
                          attempts=[attempt], request_id="rq1", ok=True, how="native")
    assert (row.provider, row.model, row.tokens_in, row.tokens_out, row.usd) == ("claude", "claude-sonnet-5-5", 3357, 53, 0.0097459)
    assert (row.fn, row.step, row.atom_id, row.task_id, row.dept_id, row.purpose) == ("identity", "J2.c", "at-1", "t1", "d1", "agent_turn")
    assert (row.call_ref, row.ok, row.how, row.seconds) == ("run_1:4", True, "native", 4.8)


def test_claude_resumed_row_is_the_delta_not_the_cumulative_total():
    first = result_line("claude/stream_structured_ok.jsonl")
    second = result_line("claude/stream_resume_plain_ok.jsonl")
    attempt = Attempt(provider="claude", model="m", usage=usage_from_claude(second["usage"]),
                      usd=cost_delta(second["total_cost_usd"], first["total_cost_usd"]), usd_basis="reported")
    row = build_usage_row(ctx=ctx(session_id="cs_1", node_id="root"), attempts=[attempt], request_id="r2", ok=True, how="chat",
                          purpose="chat")
    assert (row.tokens_in, row.tokens_out, row.usd) == (2947, 4, 0.0092889)
    assert (row.session_id, row.node_id, row.purpose, row.how) == ("cs_1", "root", "chat", "chat")


def test_codex_fresh_and_resumed_rows_have_usd_null_without_rates():
    first = usage_from_codex(result_line("codex/exec_structured_ok.jsonl")["usage"])
    second = usage_from_codex(result_line("codex/exec_resume_plain_ok.jsonl")["usage"])
    fresh = build_usage_row(ctx=ctx(), request_id="a", ok=True, how="native", attempts=[
        Attempt(provider="codex", model="gpt-5.6-luna", usage=cumulative_delta(first, Usage()),
                usd=rate_card_usd(None, first), usd_basis="unknown")])
    resumed = build_usage_row(ctx=ctx(), request_id="b", ok=True, how="chat", attempts=[
        Attempt(provider="codex", model="gpt-5.6-luna", usage=cumulative_delta(second, first), usd=None, usd_basis="unknown")])
    assert (fresh.tokens_in, fresh.tokens_out, fresh.usd) == (12168, 15, None)
    assert (resumed.tokens_in, resumed.tokens_out, resumed.usd) == (12174, 5, None)


def test_codex_with_a_filled_rate_card_has_a_rate_card_usd():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    usd = rate_card_usd(Rate(in_per_mtok=1.0, out_per_mtok=2.0), usage)
    row = build_usage_row(ctx=ctx(), request_id="a", ok=True, how="native",
                          attempts=[Attempt(provider="codex", usage=usage, usd=usd, usd_basis="rate_card")])
    assert row.usd == 3.0 and row.detail["usd_basis"] == "rate_card"


def test_stub_row_is_zero_dollars_and_keeps_the_atom_id():
    row = build_usage_row(ctx=ctx(function="W-2", atom="W-2.a1"), request_id="s", ok=True, how="stub", attempts=[
        Attempt(provider="stub", model="scripted", usage=Usage(input_tokens=25, output_tokens=3), usd=0.0, usd_basis="none")])
    assert (row.provider, row.model, row.usd, row.tokens_in, row.tokens_out, row.atom_id, row.step) == (
        "stub", "scripted", 0.0, 25, 3, "W-2.a1", "W-2")


def test_atom_id_is_tag_atom_and_none_for_an_untagged_call():
    tagged = build_usage_row(ctx=ctx(atom="at-9"), attempts=[ok_attempt()], request_id="x", ok=True, how="native")
    untagged = build_usage_row(ctx=RouteContext(), attempts=[ok_attempt()], request_id="x", ok=True, how="native")
    assert tagged.atom_id == "at-9"
    assert (untagged.atom_id, untagged.step, untagged.fn, untagged.dept_id, untagged.task_id) == (None, None, None, None, None)


def test_call_ref_in_the_row_follows_call_no():
    numbered = build_usage_row(ctx=ctx(run_id="run_7", call_no=12), attempts=[ok_attempt()], request_id="x", ok=True, how="native")
    plain = build_usage_row(ctx=ctx(run_id="run_7"), attempts=[ok_attempt()], request_id="req9", ok=True, how="native")
    assert (numbered.call_ref, plain.call_ref) == ("run_7:12", "r:req9")


def test_detail_keys_and_attempts():
    attempts = [
        Attempt(provider="claude", model="sonnet", effort="low", code="quota", usage=None, seconds=1.25),
        Attempt(provider="codex", model="gpt-5.6-luna", effort="low", usage=Usage(input_tokens=5, cached_input_tokens=7,
                cache_write_tokens=2, output_tokens=4, reasoning_tokens=3), usd=None, usd_basis="unknown", seconds=2.0,
                cli_version="0.146.0", billing="subscription"),
    ]
    row = build_usage_row(ctx=ctx(allowance=Allowance(envelope_id="env-1")), attempts=attempts, request_id="rq", ok=True,
                          how="prompted", note="claude out of quota, answered by codex", seconds=3.5)
    d = row.detail
    assert set(d) == {"request_id", "attempts", "cached_in", "cache_write", "reasoning", "usd_basis", "billing", "cli_version",
                      "envelope_id", "note"}
    assert (d["request_id"], d["cached_in"], d["cache_write"], d["reasoning"]) == ("rq", 7, 2, 3)
    assert (d["usd_basis"], d["billing"], d["cli_version"], d["envelope_id"]) == ("unknown", "subscription", "0.146.0", "env-1")
    assert d["note"] == "claude out of quota, answered by codex"
    assert d["attempts"] == [
        {"provider": "claude", "model": "sonnet", "effort": "low", "code": "quota", "usd": None, "tokens_in": None,
         "tokens_out": None, "seconds": 1.25},
        {"provider": "codex", "model": "gpt-5.6-luna", "effort": "low", "code": "ok", "usd": None, "tokens_in": 14,
         "tokens_out": 4, "seconds": 2.0}]
    assert (row.provider, row.seconds) == ("codex", 3.5)                           # the provider that answered; wall time as given
    json.dumps(row.model_dump(mode="json"))                                         # the whole row is JSON


def test_sums_over_attempts_and_known_usd_only():
    attempts = [ok_attempt("claude", usage=Usage(input_tokens=10, output_tokens=5), usd=0.5),
                ok_attempt("claude", usage=Usage(input_tokens=1, cached_input_tokens=2, output_tokens=3), usd=0.25),
                ok_attempt("codex", usage=Usage(input_tokens=100, output_tokens=7), usd=None)]
    row = build_usage_row(ctx=ctx(), attempts=attempts, request_id="x", ok=True, how="repaired")
    assert (row.tokens_in, row.tokens_out, row.usd) == (10 + 3 + 100, 5 + 3 + 7, 0.75)
    assert row.seconds == 0.0 and len(row.detail["attempts"]) == 3


def test_seconds_default_to_the_sum_of_the_attempts():
    row = build_usage_row(ctx=ctx(), attempts=[ok_attempt(seconds=1.5), ok_attempt(seconds=2.0)], request_id="x", ok=True, how="native")
    assert row.seconds == 3.5


def test_failed_request_still_builds_a_row_with_ok_false():
    attempts = [Attempt(provider="claude", model="sonnet", code="overloaded", seconds=0.5),
                Attempt(provider="codex", model="gpt-5.6-luna", code="timeout", seconds=900)]
    row = build_usage_row(ctx=ctx(function="audit", atom="ov-1"), attempts=attempts, request_id="f", ok=False, how="native")
    assert (row.ok, row.provider, row.model, row.tokens_in, row.tokens_out, row.usd) == (False, "codex", "gpt-5.6-luna", None, None, None)
    assert [a["code"] for a in row.detail["attempts"]] == ["overloaded", "timeout"]
    assert row.atom_id == "ov-1"


def test_request_that_failed_before_any_spawn_names_the_planned_provider():
    row = build_usage_row(ctx=ctx(), attempts=[], provider="claude", request_id="e", ok=False, how="native")
    assert (row.provider, row.model, row.detail["attempts"], row.tokens_in, row.usd) == ("claude", "", [], None, None)
    assert row.detail["usd_basis"] == "none" and row.detail["billing"] == "unknown" and row.detail["cli_version"] is None
    with pytest.raises(ValueError, match="provider"):
        build_usage_row(ctx=ctx(), attempts=[], request_id="e", ok=False, how="native")


def test_purpose_defaults_to_the_tag_and_is_overridden_for_sessions():
    base = dict(attempts=[ok_attempt()], request_id="x", ok=True, how="native")
    assert build_usage_row(ctx=ctx(purpose="review"), **base).purpose == "review"
    assert build_usage_row(ctx=ctx(purpose="review"), purpose="chat", **base).purpose == "chat"


# ---- sinks ---------------------------------------------------------------------------------------------------------------
def test_memory_sink_keeps_every_row_and_counts():
    sink = MemoryUsageSink()
    assert isinstance(sink, UsageSink)
    row = build_usage_row(ctx=ctx(), attempts=[ok_attempt()], request_id="x", ok=True, how="native")
    assert (sink.record(row), sink.record(row)) == (1, 2)                           # no de-duplication: a double write shows
    assert sink.rows == [row, row] and len(sink) == 2
    sink.clear()
    assert sink.rows == []


def test_memory_sink_is_thread_safe():
    sink = MemoryUsageSink()
    row = build_usage_row(ctx=ctx(), attempts=[ok_attempt()], request_id="x", ok=True, how="native")
    threads = [threading.Thread(target=lambda: [sink.record(row) for _ in range(100)]) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(sink) == 800


def test_a_plain_object_without_record_is_not_a_sink():
    assert not isinstance(object(), UsageSink)


def test_the_engine_event_sink_takes_the_row_and_turns_atom_id_into_atom(tmp_path):
    """The two sinks agree on the row: EventUsageSink reads UsageIn's fields (E0 contract)."""
    with EventWriter(tmp_path) as writer:
        sink = EventUsageSink(writer)
        row = build_usage_row(ctx=ctx(run_id="run_1", call_no=2, function="W-3", atom="W-3.a1"), attempts=[ok_attempt()],
                              request_id="x", ok=True, how="native")
        assert sink.record(row) == 1
    line = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert (line["t"], line["atom"], line["step"], line["fn"], line["call_ref"]) == ("usage", "W-3.a1", "W-3", "W-3", "run_1:2")


# ---- session state file --------------------------------------------------------------------------------------------------
def state(tmp_path, **kw):
    workdir = tmp_path / "cs_1"
    base = dict(session_id="cs_1", provider="claude", provider_session_id="abc", model="sonnet", effort="low", workdir=str(workdir),
                turns=2, cum_usd=0.0190348, cum_usage=Usage(input_tokens=6, output_tokens=57), created_at=1793748000.0)
    return SessionState(**{**base, **kw})


def test_session_state_round_trip_is_atomic_and_private(tmp_path):
    s = state(tmp_path)
    path = save_session_state(s)
    assert path == session_path(s.workdir) == tmp_path / "cs_1" / "session.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == ["session.json"]
    assert load_session_state(s.workdir) == s
    save_session_state(s.model_copy(update={"turns": 3}))
    assert load_session_state(s.workdir).turns == 3


def test_missing_or_corrupt_session_file_loads_as_none(tmp_path):
    s = state(tmp_path)
    assert load_session_state(s.workdir) is None
    path = save_session_state(s)
    path.write_text("{not json", encoding="utf-8")
    assert load_session_state(s.workdir) is None
    path.write_text(json.dumps({"session_id": "cs_1"}), encoding="utf-8")        # valid JSON, wrong shape
    assert load_session_state(s.workdir) is None
