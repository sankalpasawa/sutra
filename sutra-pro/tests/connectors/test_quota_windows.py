"""Every usage window of a plan, and the plan in words (GAP-providers; re-expresses the old app's test_usage_all.py TheShape and
TheUnhappyPaths, and test_account.py PlanLabel). The figures come from the captured CLI output in tests/fixtures/connectors."""
from __future__ import annotations

import json

import pytest

from sutra_app.connectors.claude import _quota_of
from sutra_app.connectors.codex import quota_from_rate_limits
from sutra_app.connectors.models import Quota, QuotaWindow
from sutra_app.connectors.quota_windows import plan_label, window_key, window_label, windows_from_claude, windows_from_codex


def claude_rate_limit_info(fixtures) -> dict:
    for raw in fixtures.text("claude/stream_structured_ok.jsonl").splitlines():
        obj = json.loads(raw) if raw.strip() else {}
        if obj.get("type") == "rate_limit_event":
            return obj["rate_limit_info"]
    raise AssertionError("the fixture has no rate_limit_event")


def codex_rate_limits(fixtures) -> dict:
    return json.loads(fixtures.text("codex/rollout_token_count.jsonl").splitlines()[-1])["payload"]["rate_limits"]


def test_both_claude_windows_of_the_captured_event_are_kept(fixtures):
    info = claude_rate_limit_info(fixtures)
    quota = _quota_of(info)
    assert [(w.key, w.label, w.used, w.resets_at) for w in quota.windows] == [
        ("five_hour", "5-hour", 0.09, 1793748600.0), ("seven_day", "Weekly", 0.1, 1794006000.0)]
    assert (quota.window, quota.used, quota.resets_at) == ("five_hour", 0.09, 1793748600.0)      # the metering window is unchanged


def test_without_unified_windows_the_named_window_is_the_one_row():
    windows = windows_from_claude({"status": "allowed_warning", "rateLimitType": "seven_day", "utilization": 0.83, "resetsAt": 1794006000})
    assert [(w.key, w.label, w.used) for w in windows] == [("seven_day", "Weekly", 0.83)]
    assert windows_from_claude({"status": "allowed"}) == []


def test_a_per_model_window_and_an_unknown_window_still_render_in_order():
    windows = windows_from_claude({"unifiedWindows": {"seven_day_opus": {"utilization": 0.5}, "seven_day": {"utilization": 0.4},
                                                       "five_hour": {"utilization": 0.2}, "burst_window": {"utilization": 0.1}}})
    assert [(w.key, w.label) for w in windows] == [("five_hour", "5-hour"), ("seven_day", "Weekly"), ("seven_day_opus", "Weekly (Opus)"),
                                                   ("burst_window", "Burst window")]


def test_an_absent_figure_stays_absent_and_a_hostile_key_is_dropped():
    windows = windows_from_claude({"unifiedWindows": {"five_hour": {"resetsAt": 5}, "<script>": {"utilization": 0.5},
                                                       "seven_day": {"utilization": True}, "x" * 41: {"utilization": 0.1},
                                                       "thirty_day": {"utilization": float("nan")}, "one_day": "not a mapping"}})
    assert [(w.key, w.used) for w in windows] == [("five_hour", None), ("seven_day", None), ("thirty_day", None)]


def test_codex_primary_and_secondary_are_both_kept_with_names_from_their_duration(fixtures):
    limits = codex_rate_limits(fixtures)
    assert [(w.key, w.label, w.used) for w in windows_from_codex(limits)] == [("thirty_day", "Monthly", 0.0)]
    derived = dict(limits, primary={"used_percent": 62.0, "window_minutes": 300, "resets_at": 1796300000},
                   secondary={"used_percent": 81.0, "window_minutes": 10080, "resets_at": 1796400000})
    quota = quota_from_rate_limits(derived)
    assert [(w.key, w.label, w.used, w.resets_at) for w in quota.windows] == [
        ("five_hour", "5-hour", 0.62, 1796300000.0), ("seven_day", "Weekly", 0.81, 1796400000.0)]
    assert (quota.window, quota.status, quota.plan) == ("seven_day", "warning", "go")          # the fuller one still meters the call


@pytest.mark.parametrize(("minutes", "key", "label"), [
    (300, "five_hour", "5-hour"), (10080, "seven_day", "Weekly"), (43200, "thirty_day", "Monthly"), (120, "120_min", "2-hour"),
    (2880, "2880_min", "2-day"), (45, "45_min", "45-minute")])
def test_a_codex_duration_nobody_listed_is_named_from_its_number(minutes, key, label):
    assert window_key(minutes) == key and window_label(key) == label


def test_a_codex_window_without_a_duration_is_named_by_its_slot():
    assert [(w.key, w.label) for w in windows_from_codex({"primary": {"used_percent": 5}})] == [("primary", "Primary")]
    assert window_key(0) is None and window_key(True) is None and window_key("300") is None


@pytest.mark.parametrize(("provider", "plan", "label"), [
    ("claude", "max", "Claude Max"), ("claude", "pro", "Claude Pro"), ("claude", "team", "Claude Team"),
    ("claude", "enterprise", "Claude Enterprise"), ("claude", "free", "Claude Free"), ("codex", "go", "ChatGPT Go"),
    ("codex", "plus", "ChatGPT Plus"), ("codex", "business", "ChatGPT Business"), ("codex", "edu", "ChatGPT Edu"),
    ("claude", "max_plus_ultra", "Claude Max Plus Ultra"), ("codex", "self-serve-business", "ChatGPT Self Serve Business"),
    ("claude", "claude_max", "Claude Max"), ("claude", None, None), ("codex", "  ", None), ("claude", "pro\u0000\n", "Claude Pro")])
def test_a_plan_is_named_and_an_unknown_one_is_title_cased_never_dropped(provider, plan, label):
    assert plan_label(provider, plan) == label


def test_old_stored_snapshots_still_validate_and_a_window_is_closed():
    old = {"status": "ok", "window": "five_hour", "used": 0.1, "resets_at": 5.0, "plan": None, "source": "rate_limit_event"}
    assert Quota.model_validate(old).windows == [] and Quota.model_validate(old).seen_at is None
    with pytest.raises(ValueError):
        QuotaWindow(key="five_hour", label="5-hour", used=0.1, extra=1)
    with pytest.raises(ValueError):
        QuotaWindow(key="Five Hour", label="5-hour")
