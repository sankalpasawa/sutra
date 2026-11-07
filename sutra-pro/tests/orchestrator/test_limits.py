"""The monthly spending limit and the plan-window guard (gap package routines-limits): the levels and their edges, the words, the start gate on a
real task queue (a queued task waits with the reason and starts when the reason ends; a running task is never touched), and the file."""
import os
import stat
import time
from datetime import datetime, timezone

import pytest
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture used by name)

from sutra_app.connectors.models import Quota, QuotaWindow
from sutra_app.orchestrator.limits import (
    GUARD_HOLD, GUARD_WARN, WAIT_SPEND, Limits, LimitsFile, LimitsStore, guard_reading, money, month_end, month_start, reset_words,
    spend_status,
)

NOW = int(datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc).timestamp())          # the tests' FakeClock starts here (10:00 UTC)
DAY = 86400


@pytest.fixture
def utc_local(monkeypatch):
    """The machine's local zone is UTC for the test (the reset words are local); a no-op where the platform has no tzset."""
    if not hasattr(time, "tzset"):
        pytest.skip("no tzset on this platform")
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def window(key="seven_day", label="Weekly", used=0.83, resets_in=2 * DAY):
    return QuotaWindow(key=key, label=label, used=used, resets_at=NOW + resets_in if resets_in is not None else None)


def quota(*windows, seen_in=-60):
    return Quota(status="warning", windows=list(windows), seen_at=NOW + seen_in)


def quotas_of(**by_provider):
    return lambda: by_provider


@pytest.fixture
def limits(tenv, tmp_path):
    made = Limits(tmp_path / "limits.json", tenv.db, quotas=quotas_of(), clock=tenv.clock)
    tenv.service.start_gate = made.gate
    return made


def spend_row(tenv, usd, *, provider="claude", at=NOW - 3600, ref=None):
    tenv.sql("INSERT INTO usage_ledger(at, provider, purpose, usd, call_ref) VALUES (?,?,?,?,?)", at, provider, "test", usd, ref)


def waiting_detail(tenv, task_id):
    return tenv.one("SELECT detail FROM graph_nodes WHERE task_id = ? AND step_ref = 'task'", task_id)


# ---- spend: the levels --------------------------------------------------------------------------------------------------------------

def test_money_reads_as_dollars_with_cents_only_when_there_are_some():
    assert (money(10), money(8.2), money(1250), money(0.5), money(10.004)) == ("$10", "$8.20", "$1,250", "$0.50", "$10")


def test_the_levels_none_ok_warn_over_and_their_edges(tenv):
    for spent, level in ((0, "ok"), (7.99, "ok"), (8.0, "warn"), (9.99, "warn"), (10.0, "over"), (25, "over")):
        tenv.sql("DELETE FROM usage_ledger")
        if spent:
            spend_row(tenv, spent)
        assert spend_status(tenv.db.conn(), 10.0, NOW)["level"] == level, spent
    assert spend_status(tenv.db.conn(), None, NOW)["level"] == "none" and spend_status(tenv.db.conn(), 0, NOW)["limit"] is None


def test_the_warn_line_is_one_sentence_with_about_and_the_over_line_says_what_waits(tenv):
    spend_row(tenv, 8.2)
    warn = spend_status(tenv.db.conn(), 10.0, NOW)
    assert warn["line"] == "About $8.20 of your $10 monthly limit" and warn["pct"] == 0.82
    spend_row(tenv, 2.0)
    over = spend_status(tenv.db.conn(), 10.0, NOW)
    assert over["line"] == "This month's spending limit is used up: about $10.20 of your $10 monthly limit. New tasks wait until you raise it or the month ends"
    assert spend_status(tenv.db.conn(), 10.0, NOW)["month"] == "2026-11" and over["month_ends_at"] == "2026-12-01T00:00:00Z"


def test_only_known_dollars_of_this_utc_month_count(tenv):
    spend_row(tenv, 3.0)
    spend_row(tenv, None, provider="codex")                                          # a Codex call has no dollar figure: not counted, and said so
    spend_row(tenv, None, provider="codex", ref="r2")
    spend_row(tenv, 99.0, provider="stub")                                           # the offline stub is never money
    spend_row(tenv, 50.0, at=month_start(NOW) - 1)                                   # the last second of October
    state = spend_status(tenv.db.conn(), 10.0, NOW)
    assert state["spent"] == 3.0 and state["unpriced_calls"] == 2 and state["level"] == "ok"
    assert month_start(NOW) == int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()) and month_end(NOW) - month_start(NOW) == 30 * DAY
    december = int(datetime(2026, 12, 31, 23, tzinfo=timezone.utc).timestamp())
    assert month_end(december) == int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())


# ---- spend: the gate on a real queue ----------------------------------------------------------------------------------------------------

def test_no_limit_never_gates_however_much_was_spent(tenv, limits):
    spend_row(tenv, 5000.0)
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert tenv.status(task.id) == "starting"


def test_a_queued_task_waits_with_the_reason_when_the_limit_is_used_up_and_starts_when_it_is_raised(tenv, limits):
    limits.update(monthly_usd=10.0)
    spend_row(tenv, 10.2)
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == []
    assert tenv.status(task.id) == "queued"
    assert waiting_detail(tenv, task.id) == f"{WAIT_SPEND} (about $10.20 of $10)"
    assert waiting_detail(tenv, task.id).startswith("waiting: this month's spending limit is used up")
    limits.update(monthly_usd=20.0)                                                  # raising the limit is what the route follows with start_ready
    assert tenv.run(tenv.service.start_ready()) == [task.id]
    assert tenv.status(task.id) == "starting"


def test_clearing_the_limit_also_lets_the_task_start(tenv, limits):
    limits.update(monthly_usd=1.0)
    spend_row(tenv, 5.0)
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == []
    limits.update(monthly_usd=0)
    assert limits.state()["spend"]["level"] == "none"
    assert tenv.run(tenv.service.start_ready()) == [task.id]


def test_a_manual_start_is_held_too(tenv, limits):
    limits.update(monthly_usd=1.0)
    spend_row(tenv, 5.0)
    task = tenv.new()
    assert tenv.run(tenv.service.start(task.id)) is False and tenv.status(task.id) == "queued"


def test_a_running_task_is_never_touched_when_the_limit_is_crossed(tenv, limits):
    running = tenv.started()
    limits.update(monthly_usd=1.0)
    spend_row(tenv, 5.0)
    waiting = tenv.new("web", "A second task for the same team")
    tenv.run(tenv.service.start_ready())
    assert tenv.status(running) == "running" and tenv.status(waiting.id) == "queued"            # in flight: finished its own way; only starts wait


def test_the_new_month_releases_a_task_held_by_the_old_one(tenv, limits):
    limits.update(monthly_usd=10.0)
    spend_row(tenv, 12.0)
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == []
    tenv.clock.advance(31 * DAY)                                                      # December: last month's spending is last month's
    assert tenv.run(tenv.service.start_ready()) == [task.id]


def test_a_broken_gate_fails_open(tenv, limits, monkeypatch):
    limits.update(monthly_usd=1.0)
    spend_row(tenv, 5.0)
    monkeypatch.setattr("sutra_app.orchestrator.limits.spend_status", lambda *a, **k: 1 / 0)
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == [task.id]


# ---- the plan windows ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("used,level", [(0.0, "ok"), (0.69, "ok"), (0.699, "ok"), (0.70, "warn"), (0.79, "warn"), (0.80, "hold"), (0.83, "hold"), (1.0, "hold"), (1.4, "hold")])
def test_the_guard_levels_at_their_edges(used, level):
    assert (GUARD_WARN, GUARD_HOLD) == (0.70, 0.80)
    assert guard_reading({"claude": quota(window(used=used))}, NOW, enabled=True)["level"] == level


def test_a_hold_holds_only_when_the_owner_switched_the_guard_on(utc_local):
    quotas = {"claude": quota(window(used=0.83))}
    off = guard_reading(quotas, NOW, enabled=False)
    assert (off["level"], off["holding"]) == ("hold", False)                                        # the warning is shown, nothing waits
    on = guard_reading(quotas, NOW, enabled=True)
    assert on["holding"] is True and on["line"] == "Claude weekly window is at 83%, resets Fri 10:00"
    assert on["top"]["provider"] == "claude" and on["top"]["used"] == 0.83 and on["top"]["resets_at"] == "2026-11-06T10:00:00Z"


def test_the_words_name_the_provider_the_window_and_the_percent_rounded_down(utc_local):
    five = guard_reading({"codex": quota(window(key="300_min", label="5-hour", used=0.7999, resets_in=3600))}, NOW, enabled=True)
    assert five["line"] == "Codex 5-hour window is at 79%, resets 11:00" and five["level"] == "warn" and five["holding"] is False
    assert reset_words(None, NOW) == "" and reset_words(NOW - 1, NOW) == "" and reset_words(NOW + DAY, NOW) == "resets Thu 10:00"


def test_the_fullest_window_of_every_provider_is_the_one_named():
    both = guard_reading({"claude": quota(window(key="five_hour", label="5-hour", used=0.2), window(used=0.5)),
                          "codex": quota(window(key="300_min", label="5-hour", used=0.9))}, NOW, enabled=True)
    assert both["top"]["provider"] == "codex" and both["holding"] is True
    assert [r["provider"] for r in both["windows"]] == ["codex"]                                    # only windows at warn or more are listed


def test_a_missing_or_stale_snapshot_holds_nothing():
    assert guard_reading({}, NOW, enabled=True)["level"] == "none"
    assert guard_reading({"claude": None}, NOW, enabled=True)["holding"] is False
    reset = quota(window(used=0.95, resets_in=-10))                                                 # the window reset since the snapshot: nothing is known
    assert guard_reading({"claude": reset}, NOW, enabled=True) ["level"] == "none"
    old = quota(window(used=0.95, resets_in=None), seen_in=-7 * 3600)                               # no reset time and seen seven hours ago
    assert guard_reading({"claude": old}, NOW, enabled=True)["holding"] is False
    fresh = quota(window(used=0.95, resets_in=None), seen_in=-600)
    assert guard_reading({"claude": fresh}, NOW, enabled=True)["holding"] is True
    nofigure = Quota(status="unknown", windows=[QuotaWindow(key="seven_day", label="Weekly", used=None, resets_at=NOW + DAY)], seen_at=NOW)
    assert guard_reading({"claude": nofigure}, NOW, enabled=True)["level"] == "none"


def test_an_older_snapshot_with_only_the_metering_window_is_read_too():
    old = Quota(status="warning", window="five_hour", used=0.9, resets_at=NOW + 600, seen_at=NOW - 30)
    out = guard_reading({"claude": old}, NOW, enabled=True)
    assert out["holding"] is True and out["top"]["key"] == "five_hour"


def test_a_continue_lasts_until_that_window_resets_and_not_longer():
    quotas = {"claude": quota(window(used=0.83, resets_in=3600))}
    marks = {"claude:seven_day": NOW + 3600}
    kept = guard_reading(quotas, NOW, enabled=True, continued=marks)
    assert kept["holding"] is False and kept["level"] == "hold" and kept["top"]["continued"] is True
    later = NOW + 3601                                                                              # the window reset: a new one begins and may fill again
    next_week = QuotaWindow(key="seven_day", label="Weekly", used=0.83, resets_at=later + 7 * DAY)
    refilled = guard_reading({"claude": Quota(status="warning", windows=[next_week], seen_at=later - 5)}, later, enabled=True, continued=marks)
    assert refilled["holding"] is True and refilled["top"]["continued"] is False                 # the old Continue ended with the old window


def test_only_the_pinned_provider_counts_for_a_team_pinned_to_it():
    quotas = {"claude": quota(window(used=0.9)), "codex": quota(window(key="300_min", label="5-hour", used=0.1))}
    assert guard_reading(quotas, NOW, enabled=True, providers=("codex",))["holding"] is False
    assert guard_reading(quotas, NOW, enabled=True, providers=("claude",))["holding"] is True


# ---- the guard on a real queue -------------------------------------------------------------------------------------------------------------

def test_a_queued_task_waits_at_the_hold_line_and_one_continue_lets_it_go(tenv, tmp_path):
    reading = quotas_of(claude=quota(window(used=0.83)))
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=reading, clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    limits.update(guard_enabled=True)
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == []
    assert tenv.status(task.id) == "queued"
    detail = waiting_detail(tenv, task.id)
    assert detail.startswith("waiting: Claude weekly window is at 83%, resets ") and detail.endswith("(press Continue to run anyway)")
    state = limits.continue_now()
    assert state["guard"]["holding"] is False and state["guard"]["top"]["continued"] is True
    assert tenv.run(tenv.service.start_ready()) == [task.id]


def test_with_the_guard_off_a_task_starts_even_at_ninety_percent(tenv, tmp_path):
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=quotas_of(claude=quota(window(used=0.9))), clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    task = tenv.new()
    assert limits.state()["guard"]["level"] == "hold" and limits.state()["guard"]["holding"] is False
    assert tenv.run(tenv.service.start_ready()) == [task.id]


def test_a_team_pinned_to_codex_is_not_held_by_a_full_claude_window(tenv, tmp_path):
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=quotas_of(claude=quota(window(used=0.9)), codex=quota(window(key="300_min", label="5-hour", used=0.1))),
                    clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    limits.update(guard_enabled=True)
    tenv.sql("UPDATE chat_sessions SET pinned = 'codex' WHERE id = (SELECT chat_session_id FROM graph_nodes WHERE id = 'web')")
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == [task.id]


def test_the_guard_does_not_apply_offline(tenv, tmp_path):
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=quotas_of(claude=quota(window(used=0.99))), clock=tenv.clock, offline=True)
    tenv.service.start_gate = limits.gate
    limits.update(guard_enabled=True)
    task = tenv.new()
    assert tenv.run(tenv.service.start_ready()) == [task.id]


def test_the_wait_is_visible_but_the_spend_reason_comes_first_when_both_hold(tenv, tmp_path):
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=quotas_of(claude=quota(window(used=0.9))), clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    limits.update(monthly_usd=1.0, guard_enabled=True)
    spend_row(tenv, 5.0)
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert waiting_detail(tenv, task.id).startswith(WAIT_SPEND)


# ---- the file ---------------------------------------------------------------------------------------------------------------------------

def test_the_file_is_private_atomic_and_holds_only_the_owners_choices(tenv, limits):
    limits.update(monthly_usd=12.5, guard_enabled=True)
    path = limits.store.path
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 if os.name == "posix" else path.is_file()
    body = path.read_text()
    assert '"monthly_usd": 12.5' in body and '"enabled": true' in body and not list(path.parent.glob(".limits.json.*"))
    assert LimitsStore(path).load() == LimitsFile(monthly_usd=12.5, guard={"enabled": True})


def test_a_file_that_does_not_read_is_ignored_and_the_next_save_replaces_it(tenv, limits):
    limits.store.path.write_text("{not json")
    assert limits.state()["spend"]["limit"] is None and limits.state()["guard"]["enabled"] is False
    limits.store.path.write_text('{"version": 1, "monthly_usd": -5}')
    assert limits.state()["spend"]["limit"] is None
    limits.store.path.write_text('{"version": 1, "monthly_usd": 1e9}')
    assert limits.state()["spend"]["limit"] is None
    limits.update(monthly_usd=3.0)
    assert limits.state()["spend"]["limit"] == 3.0


def test_switching_the_guard_off_forgets_its_continue_marks_and_a_change_is_seen_without_a_restart(tenv, tmp_path):
    reading = quotas_of(claude=quota(window(used=0.9)))
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=reading, clock=tenv.clock)
    limits.update(guard_enabled=True)
    assert limits.continue_now(NOW)["guard"]["top"]["continued"] is True
    limits.update(guard_enabled=False)
    assert limits.store.load().guard.continued == {}
    other = Limits(limits.store.path, tenv.db, quotas=reading, clock=tenv.clock)               # another process, same file
    assert other.state(NOW)["guard"]["enabled"] is False
    limits.update(guard_enabled=True)
    assert other.state(NOW)["guard"]["enabled"] is True


def test_update_keeps_what_it_is_not_given(tenv, limits):
    limits.update(monthly_usd=7.0)
    limits.update(guard_enabled=True)
    state = limits.state()
    assert state["spend"]["limit"] == 7.0 and state["guard"]["enabled"] is True
    limits.update(monthly_usd=None)
    assert limits.state()["spend"]["limit"] is None and limits.state()["guard"]["enabled"] is True
