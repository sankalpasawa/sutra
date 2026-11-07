"""Recurring work (gap package routines-limits): a standing task becomes one ordinary task per due time, one catch-up run after an absence, a skip
row with its reason when the team is busy, no slot twice across restarts, three crashes pause it. Built on the real task side (`TEnv`: fake
launcher, fake clock); the schedule math has its own file (test_schedule.py)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from orchestrator.test_scripted_conversation import FixedClock, Scenario, answered, make_scenario
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture used by name)

from sutra_app.orchestrator.errors import AppError, Busy, NotFound
from sutra_app.orchestrator.recurring import CRASH_LIMIT, MAX_RECURRING, Recurring
from sutra_app.orchestrator.schedule import COUNT_CAP, Schedule

UTC = timezone.utc
WEEKDAYS_9 = Schedule(every="weekdays", hour=9, minute=0)
DAILY_9 = Schedule(every="day", hour=9, minute=0)


def at(year, month, day, hour=0, minute=0, tz=UTC) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=tz).timestamp())


class Now:
    """A clock a test sets: the service reads it for `next_due_at` and for a tick without an explicit time."""

    def __init__(self, t: int) -> None:
        self.t = t

    def now(self) -> int:
        return self.t

    def time(self) -> float:
        return float(self.t)


@pytest.fixture
def rec(tenv):
    return Recurring(tenv.db, tenv.service, clock=Now(at(2026, 11, 4, 8)), tz=UTC)


def tasks_of(tenv, dept="web"):
    return [dict(r) for r in tenv.sql("SELECT id, title, user_text, status FROM tasks WHERE dept_id = ? ORDER BY created_at, rowid", dept)]


def rows_of(tenv, rec_id):
    return [dict(r) for r in tenv.sql(
        "SELECT trigger, outcome, folded, reason, task_id, due_at FROM recurring_runs WHERE recurring_id = ? ORDER BY id", rec_id)]


def end(tenv, task_id, status="crashed"):
    """Start the queued task and end it with `status` (the server's own terminal event)."""
    tenv.run(tenv.service.start_ready())
    assert tenv.projector.mark_ended(task_id, status, f"test: {status}")


# ---- one due slot, one task -----------------------------------------------------------------------------------------------------------

def test_one_due_slot_makes_exactly_one_task_with_the_stored_words(tenv, rec):
    made = rec.create("web", "Write the pipeline summary", WEEKDAYS_9, now=at(2026, 11, 4, 8))
    assert made.human == "Every weekday at 9:00 AM (local)" and made.enabled and made.next_due_at == "2026-11-04T09:00:00Z"
    assert made.never_fired_on_schedule is False
    assert rec.tick(at(2026, 11, 4, 8, 59)).started == []                                   # not due yet
    report = rec.tick(at(2026, 11, 4, 9, 0, ) + 10)
    assert [r for r, _ in report.started] == [made.id]
    (task,) = tasks_of(tenv)
    assert task["user_text"] == "Write the pipeline summary" and task["title"] == "Write the pipeline summary (scheduled)"
    assert task["status"] == "queued"
    (row,) = rows_of(tenv, made.id)
    assert (row["trigger"], row["outcome"], row["folded"], row["task_id"]) == ("schedule", "started", 0, task["id"])
    note = tenv.one("SELECT text FROM chat_messages WHERE task_id = ? AND kind = 'note'", task["id"])
    assert note.startswith("Scheduled (Every weekday at 9:00 AM (local)): Write the pipeline summary")
    assert rec.tick(at(2026, 11, 4, 9, 0) + 40).started == []                               # the same slot is never made twice
    assert len(tasks_of(tenv)) == 1


def test_the_task_starts_like_any_other_through_start_ready(tenv, rec):
    rec.create("web", "Write the pipeline summary", DAILY_9, now=at(2026, 11, 4, 8))
    report = tenv.run(rec.tick_async(at(2026, 11, 4, 9, 1)))
    assert len(report.started) == 1
    (task,) = tasks_of(tenv)
    assert task["status"] == "starting"                                                     # the fake launcher started it: caps and rules applied unchanged


def test_the_weekend_is_not_due_for_a_weekday_schedule(tenv, rec):
    rec.create("web", "Weekday work", WEEKDAYS_9, now=at(2026, 11, 6, 10))                    # Friday after 9
    assert rec.tick(at(2026, 11, 7, 12)).started == [] and rec.tick(at(2026, 11, 8, 12)).started == []     # Saturday, Sunday
    assert len(rec.tick(at(2026, 11, 9, 9, 5)).started) == 1                                 # Monday


# ---- an absence: one catch-up -----------------------------------------------------------------------------------------------------------

def test_three_days_down_then_start_makes_one_task_and_says_how_many_slots_it_folded_in(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 1, 10))
    report = rec.tick(at(2026, 11, 4, 10, 0))                                                # the app was off for 3 due times (the 2nd, 3rd, 4th)
    assert len(report.started) == 1 and len(tasks_of(tenv)) == 1
    (row,) = rows_of(tenv, made.id)
    assert (row["trigger"], row["folded"], row["due_at"]) == ("catch_up", 2, at(2026, 11, 4, 9))
    assert "2 earlier due times were missed" in row["reason"]
    assert rec.tick(at(2026, 11, 4, 10, 30)).started == []                                   # nothing more is owed


def test_an_absence_past_the_count_cap_is_told_as_many_and_a_shorter_one_as_a_figure(tenv, rec):
    """QA recurring-limits: 120 days of hourly times printed 'folded 1999' as if it were exact (the count stops at COUNT_CAP)."""
    hourly = Schedule(every="hour", minute=0)
    short = rec.create("web", "Hourly digest", hourly, now=at(2026, 11, 1, 0, 30))
    rec.tick(at(2026, 11, 4, 0, 30))                                                         # 72 whole hours away: an exact figure
    assert "71 earlier due times were missed" in rows_of(tenv, short.id)[0]["reason"] and rows_of(tenv, short.id)[0]["folded"] == 71
    rec.delete(short.id)
    tenv.sql("UPDATE tasks SET status = 'done', ended_at = created_at, outcome = 'x'")
    long = rec.create("web", "Hourly digest", hourly, now=at(2026, 1, 1, 0, 30))
    ((_, task),) = rec.tick(at(2026, 5, 1, 0, 30)).started                                   # about 120 days: more than the cap
    (row,) = rows_of(tenv, long.id)
    assert row["folded"] == COUNT_CAP - 1                                                    # the figure that is stored is the least it was
    assert row["reason"].startswith("many earlier due times were missed") and "1999" not in row["reason"] and "1,999" not in row["reason"]
    note = tenv.one("SELECT text FROM chat_messages WHERE task_id = ? AND kind = 'note'", task)
    assert "Many earlier due times were missed" in note and "1999" not in note


def test_the_page_names_the_same_cap_as_the_schedule_counts_to():
    """recurring_view.js tells a folded count at the cap as 'many'; its constant is COUNT_CAP - 1 (the count includes the run's own due time)."""
    import re
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "sutra_app" / "ui" / "static" / "js" / "recurring_view.js").read_text(encoding="utf-8")
    found = re.search(r"const MANY_FOLDED = (\d+);", source)
    assert found is not None and int(found.group(1)) == COUNT_CAP - 1


def test_a_single_late_slot_is_a_catch_up_too_but_folds_nothing(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    rec.tick(at(2026, 11, 4, 11, 0))                                                         # two hours late
    (row,) = rows_of(tenv, made.id)
    assert (row["trigger"], row["folded"]) == ("catch_up", 0) and "started late" in row["reason"]


def test_a_slot_on_time_is_a_schedule_run_not_a_catch_up(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    rec.tick(at(2026, 11, 4, 9, 0) + 20)
    assert rows_of(tenv, made.id)[0]["trigger"] == "schedule"


# ---- a busy team: a skip with its reason -------------------------------------------------------------------------------------------------

def test_a_team_waiting_for_the_owner_gets_a_skip_row_and_no_task(tenv, rec):
    live = tenv.started()
    tenv.sql("UPDATE tasks SET status = 'waiting_user' WHERE id = ?", live)
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    report = rec.tick(at(2026, 11, 4, 9, 1))
    assert report.skipped == [made.id] and report.started == []
    assert len(tasks_of(tenv)) == 1                                                          # still only the team's own task
    (row,) = rows_of(tenv, made.id)
    assert (row["outcome"], row["task_id"]) == ("skipped", None) and row["reason"] == "the team is waiting for your answer"
    assert rec.get(made.id).last_run.result == "skipped"


def test_a_working_team_and_a_team_with_work_waiting_say_which(tenv, rec):
    tenv.started()
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    rec.tick(at(2026, 11, 4, 9, 1))
    assert rows_of(tenv, made.id)[0]["reason"] == "the team is still working on its current task"
    tenv.sql("UPDATE tasks SET status = 'done', ended_at = created_at, outcome = 'x'")
    tenv.new("web", "Queued behind nothing")
    rec.tick(at(2026, 11, 5, 9, 1))
    assert rows_of(tenv, made.id)[1]["reason"] == "the team already has work waiting to start"


def test_a_skipped_slot_is_dealt_with_so_the_next_tick_does_not_skip_it_again(tenv, rec):
    tenv.started()
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    rec.tick(at(2026, 11, 4, 9, 1))
    rec.tick(at(2026, 11, 4, 9, 2))
    assert len(rows_of(tenv, made.id)) == 1


# ---- restarts ---------------------------------------------------------------------------------------------------------------------------

def test_two_restarts_add_no_second_row_for_the_same_due_time(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    rec.tick(at(2026, 11, 4, 9, 1))
    for _ in range(2):                                                                       # a restart is a new service over the same file
        again = Recurring(tenv.db, tenv.service, clock=Now(at(2026, 11, 4, 9, 2)), tz=UTC)
        assert again.tick(at(2026, 11, 4, 9, 2)).started == []
    # even a cursor that was left behind cannot make the slot twice: the unique row refuses it
    tenv.sql("UPDATE recurring SET cursor_at = ? WHERE id = ?", at(2026, 11, 4, 8), made.id)
    assert Recurring(tenv.db, tenv.service, clock=Now(at(2026, 11, 4, 9, 3)), tz=UTC).tick(at(2026, 11, 4, 9, 3)).started == []
    assert len(rows_of(tenv, made.id)) == 1 and len(tasks_of(tenv)) == 1
    assert tenv.one("SELECT cursor_at FROM recurring WHERE id = ?", made.id) == at(2026, 11, 4, 9)


# ---- a clock that ran ahead and was corrected -------------------------------------------------------------------------------------------

def test_a_clock_that_ran_ahead_and_was_corrected_does_not_silence_the_schedule(tenv, rec):
    """QA recurring-limits: a bad time sync a month ahead, one catch-up, then the clock is right again. The cursor must not stay in the future."""
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 9, 8))
    ((_, first),) = rec.tick(at(2026, 12, 9, 10)).started                                    # the clock is 30 days ahead: one catch-up
    end(tenv, first, "done")
    assert tenv.one("SELECT cursor_at FROM recurring WHERE id = ?", made.id) == at(2026, 12, 9, 9)
    assert rec.tick(at(2026, 11, 9, 8, 30)).started == []                                    # corrected: nothing is due yet, and nothing is stuck
    assert tenv.one("SELECT cursor_at FROM recurring WHERE id = ?", made.id) == at(2026, 11, 9, 8, 30)
    for day in range(9, 13):                                                                 # the schedule fires on its days again
        ((_, task),) = rec.tick(at(2026, 11, day, 9, 0, ) + 40).started
        end(tenv, task, "done")
    assert [r["due_at"] for r in rows_of(tenv, made.id)[1:]] == [at(2026, 11, day, 9) for day in range(9, 13)]
    rec.clock.t = at(2026, 11, 12, 10)
    assert rec.get(made.id).next_due_at == "2026-11-13T09:00:00Z"                            # the promise the list makes is the one the tick keeps


def test_a_schedule_made_while_the_clock_was_ahead_fires_once_the_clock_is_right(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 12, 9, 10))               # created on the wrong clock
    assert rec.tick(at(2026, 11, 10, 8)).started == []                                       # the first tick on the right clock moves the cursor back
    assert len(rec.tick(at(2026, 11, 10, 9, 0) + 30).started) == 1
    assert rows_of(tenv, made.id)[0]["due_at"] == at(2026, 11, 10, 9)


def test_an_hour_the_clock_ran_ahead_does_not_run_a_slot_twice_when_it_is_corrected(tenv, rec):
    """The slot that fired on the early clock is still refused by its unique row, and a refused repeat is not reported as a skip."""
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 9, 8))
    ((_, first),) = rec.tick(at(2026, 11, 9, 10)).started                                    # the clock ran two hours ahead: 09:00 fires
    assert rec.tick(at(2026, 11, 9, 8, 30)).started == []                                    # corrected back before 09:00
    again = rec.tick(at(2026, 11, 9, 9, 0) + 30)                                             # the real 09:00: the team is still on its first task
    assert (again.started, again.skipped) == ([], [])
    end(tenv, first, "done")
    assert len(rows_of(tenv, made.id)) == 1 and len(tasks_of(tenv)) == 1


def test_the_catch_up_happens_when_the_app_starts_and_only_once(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 1, 10))

    rec.clock.t = at(2026, 11, 4, 10)                                                         # the app opens at 10:00 on the 4th

    async def go():
        first = await rec.start()
        await rec.stop()
        second = await Recurring(tenv.db, tenv.service, clock=Now(at(2026, 11, 4, 10, 1)), tz=UTC).start()
        return first, second
    first, second = asyncio.run(go())
    # three due times (the 2nd, 3rd and 4th at 09:00) folded into one
    assert len(first.started) == 1 and second.started == []
    assert rows_of(tenv, made.id)[0]["folded"] == 2


# ---- three crashes in a row -------------------------------------------------------------------------------------------------------------

def test_three_crashes_in_a_row_pause_the_schedule_and_say_so(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 3, 8))
    for day in range(CRASH_LIMIT):
        report = rec.tick(at(2026, 11, 4 + day, 9, 1))
        ((_, task_id),) = report.started
        end(tenv, task_id, "crashed")
    paused = rec.tick(at(2026, 11, 4 + CRASH_LIMIT, 9, 1))
    assert paused.paused == [made.id] and paused.started == []
    after = rec.get(made.id)
    assert after.enabled is False and after.next_due_at is None
    assert after.paused_reason.startswith("Paused after 3 runs in a row ended with a problem")
    assert len(tasks_of(tenv)) == CRASH_LIMIT
    note = tenv.one("SELECT text FROM chat_messages WHERE kind = 'note' AND text LIKE '%Paused after%'")
    assert note and note.startswith("Every day at 9:00 AM (local): Paused after")
    assert rec.tick(at(2026, 11, 12, 9, 1)).started == []                                    # paused means paused


def test_two_crashes_and_a_success_do_not_pause(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 3, 8))
    for day, status in enumerate(("crashed", "crashed", "done")):
        ((_, task_id),) = rec.tick(at(2026, 11, 4 + day, 9, 1)).started
        end(tenv, task_id, status)
    again = rec.tick(at(2026, 11, 7, 9, 1))                                                  # the success broke the streak
    assert again.paused == [] and len(again.started) == 1
    assert rec.get(made.id).enabled is True


def test_switching_on_again_starts_a_new_streak_so_the_old_crashes_do_not_pause_it_at_once(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 3, 8))
    for day in range(CRASH_LIMIT):
        ((_, task_id),) = rec.tick(at(2026, 11, 4 + day, 9, 1)).started
        end(tenv, task_id, "crashed")
    assert rec.tick(at(2026, 11, 7, 9, 1)).paused == [made.id]
    back = rec.update(made.id, enabled=True, now=at(2026, 11, 7, 11))
    rec.clock.t = at(2026, 11, 7, 11)
    assert rec.get(made.id).enabled and rec.get(made.id).paused_reason == "" and rec.get(made.id).next_due_at == "2026-11-08T09:00:00Z"
    assert back.enabled and back.paused_reason == ""
    assert rec.tick(at(2026, 11, 7, 11, 30)).paused == []                                     # the three old crashes are behind the floor
    assert len(rec.tick(at(2026, 11, 8, 9, 1)).started) == 1


def test_a_team_that_left_the_chart_pauses_its_schedule_with_a_reason(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    tenv.sql("UPDATE org_nodes SET state = 'archived' WHERE id = 'web'")
    assert rec.tick(at(2026, 11, 4, 9, 1)).paused == [made.id]
    assert rec.get(made.id).paused_reason == "Paused: the team is no longer in the org chart."


# ---- run now, edits ---------------------------------------------------------------------------------------------------------------------

def test_run_now_starts_a_manual_task_and_does_not_move_the_schedule(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    run = rec.run_now(made.id)
    assert run.trigger == "manual" and run.result == "working" and run.task_id
    assert tenv.one("SELECT cursor_at FROM recurring WHERE id = ?", made.id) == at(2026, 11, 4, 8)
    got = rec.get(made.id)
    assert got.never_fired_on_schedule is True                                                # a green manual run does not prove the schedule fires
    with pytest.raises(Busy) as busy:
        rec.run_now(made.id)                                                                  # the task just made is waiting to start
    assert "work waiting to start" in busy.value.message
    end(tenv, run.task_id, "done")
    rec.tick(at(2026, 11, 4, 9, 1))
    assert rec.get(made.id).never_fired_on_schedule is False                                  # it fired on its own once


def test_a_manual_run_on_a_working_team_is_refused_not_skipped(tenv, rec):
    tenv.started()
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    with pytest.raises(Busy):
        rec.run_now(made.id)
    assert rows_of(tenv, made.id) == []


def test_a_run_is_called_done_or_open_items_from_its_task_never_both_success(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 3, 8))
    results = []
    for day, status in enumerate(("done", "done_with_open_items", "stopped")):
        ((_, task_id),) = rec.tick(at(2026, 11, 4 + day, 9, 1)).started
        end(tenv, task_id, status)
        results.append(rec.runs(made.id, 1)[0].result)
    assert results == ["done", "open_items", "stopped"]


def test_changing_the_cadence_or_switching_on_does_not_owe_the_time_it_was_away(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 1, 8))
    rec.update(made.id, schedule=Schedule(every="day", hour=10), now=at(2026, 11, 4, 8))
    assert rec.tick(at(2026, 11, 4, 9, 0)).started == []                                      # no catch-up for the days before the change
    rec.update(made.id, enabled=False, now=at(2026, 11, 4, 9))
    assert rec.tick(at(2026, 11, 8, 12)).started == []
    rec.update(made.id, enabled=True, now=at(2026, 11, 8, 12))
    assert rec.tick(at(2026, 11, 8, 12, 5)).started == []                                     # switched on at noon: nothing is owed for the week off
    assert len(rec.tick(at(2026, 11, 9, 10, 1)).started) == 1


def test_the_words_can_change_and_delete_keeps_the_tasks_but_not_the_rows(tenv, rec):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    rec.tick(at(2026, 11, 4, 9, 1))
    assert rec.update(made.id, text="  New words  ").text == "New words"
    rec.delete(made.id)
    assert tenv.one("SELECT count(*) FROM recurring_runs") == 0 and len(tasks_of(tenv)) == 1
    with pytest.raises(NotFound):
        rec.get(made.id)
    with pytest.raises(NotFound):
        rec.delete(made.id)


def test_refusals_an_unknown_team_empty_words_and_too_many(tenv, rec):
    with pytest.raises(NotFound):
        rec.create("nowhere", "x", DAILY_9)
    for bad in ("", "   ", "x" * 4001):
        with pytest.raises(AppError) as caught:
            rec.create("web", bad, DAILY_9)
        assert caught.value.code == "validation"
    for n in range(MAX_RECURRING):
        rec.create("web", f"w{n}", DAILY_9)
    with pytest.raises(AppError) as many:
        rec.create("web", "one more", DAILY_9)
    assert many.value.code == "validation" and "50 schedules" in many.value.message


def test_a_schedule_the_team_cannot_take_is_skipped_once_with_the_reason_not_retried_every_tick(tenv, rec, monkeypatch):
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))

    def refuse(*a, **k):
        raise AppError("validation", "the words were refused")
    monkeypatch.setattr(tenv.service, "create_scheduled", refuse)
    assert rec.tick(at(2026, 11, 4, 9, 1)).skipped == [made.id]
    assert rec.tick(at(2026, 11, 4, 9, 2)).skipped == []
    (row,) = rows_of(tenv, made.id)
    assert row["outcome"] == "skipped" and row["reason"] == "could not start: the words were refused"


def test_a_failing_schedule_does_not_keep_the_others_from_running(tenv, rec, monkeypatch):
    first = rec.create("web", "First", DAILY_9, now=at(2026, 11, 4, 8))
    second = rec.create("web", "Second", Schedule(every="day", hour=9, minute=30), now=at(2026, 11, 4, 8))
    tenv.sql("UPDATE recurring SET schedule_json = '{broken' WHERE id = ?", first.id)
    report = rec.tick(at(2026, 11, 4, 9, 45))
    assert report.paused == [first.id] and [r for r, _ in report.started] == [second.id]


MONTHLY = '{"every":"month","hour":9,"minute":0,"weekday":0}'            # a cadence this build does not have (a downgrade, a hand-edited file)


def test_one_unreadable_schedule_does_not_hide_the_others_and_is_listed_as_paused_with_its_reason(tenv, rec):
    """QA recurring-limits: one bad schedule_json made the whole list a 500, so the owner could neither see 'Set it again' nor remove the row."""
    good = rec.create("web", "Good one", DAILY_9, now=at(2026, 11, 4, 8))
    bad = rec.create("web", "Bad one", DAILY_9, now=at(2026, 11, 4, 8))
    tenv.sql("UPDATE recurring SET schedule_json = ? WHERE id = ?", MONTHLY, bad.id)
    listed = {r.id: r for r in rec.listing()}                                                # before the tick has paused it
    assert set(listed) == {good.id, bad.id} and listed[good.id].enabled is True and listed[good.id].next_due_at == "2026-11-04T09:00:00Z"
    one = listed[bad.id]
    assert (one.enabled, one.schedule, one.next_due_at, one.never_fired_on_schedule) == (False, None, None, False)
    assert one.paused_reason == "Paused: its schedule could not be read. Set it again." and one.text == "Bad one" and one.human
    assert rec.get(bad.id).paused_reason == one.paused_reason
    assert rec.tick(at(2026, 11, 4, 9, 1)).paused == [bad.id]                                # the tick pauses it and says so, as before
    again = {r.id: r for r in rec.listing()}
    assert again[bad.id].enabled is False and again[bad.id].paused_reason == one.paused_reason
    assert again[good.id].last_run is not None and again[good.id].schedule == DAILY_9
    rec.delete(bad.id)                                                                       # the owner can remove it
    assert [r.id for r in rec.listing()] == [good.id]


def test_an_unreadable_schedule_can_be_set_again_and_a_manual_run_of_it_says_so_instead_of_failing(tenv, rec):
    made = rec.create("web", "Bad one", DAILY_9, now=at(2026, 11, 4, 8))
    tenv.sql("UPDATE recurring SET schedule_json = ? WHERE id = ?", MONTHLY, made.id)
    with pytest.raises(AppError) as refused:
        rec.run_now(made.id)
    assert refused.value.code == "validation" and "schedule could not be read" in refused.value.message and tasks_of(tenv) == []
    assert rec.tick(at(2026, 11, 4, 9, 1)).paused == [made.id]
    with pytest.raises(AppError) as still:                                                   # switching it on alone would only be paused again, with another note
        rec.update(made.id, enabled=True)
    assert still.value.code == "validation" and tenv.one("SELECT enabled FROM recurring WHERE id = ?", made.id) == 0
    fixed = rec.update(made.id, schedule=WEEKDAYS_9, enabled=True, now=at(2026, 11, 4, 8, 5))
    assert fixed.schedule == WEEKDAYS_9 and fixed.enabled and fixed.paused_reason == "" and fixed.next_due_at == "2026-11-04T09:00:00Z"


def test_a_daily_time_in_a_zone_that_springs_forward_fires_once_that_day(tenv):
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        ny = zoneinfo.ZoneInfo("America/New_York")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no tz database on this machine")
    rec = Recurring(tenv.db, tenv.service, clock=Now(at(2027, 3, 13, 12, tz=ny)), tz=ny)
    made = rec.create("web", "Nightly", Schedule(every="day", hour=2, minute=30), now=at(2027, 3, 13, 12, tz=ny))
    ((_, first),) = rec.tick(at(2027, 3, 14, 3, 30, tz=ny) + 20).started                      # the 02:30 that did not exist ran right after the gap
    assert rec.tick(at(2027, 3, 14, 12, tz=ny)).started == []                                # once that day
    end(tenv, first, "done")
    assert len(rec.tick(at(2027, 3, 15, 2, 30, tz=ny) + 20).started) == 1
    assert [r["trigger"] for r in rows_of(tenv, made.id)] == ["schedule", "schedule"]


def test_the_tick_starts_work_a_limit_was_holding_once_the_limit_lifts(tenv, tmp_path):
    """The spending limit and the plan window only gate STARTS, and nothing but time or the owner lifts them: the tick is what notices that a month
    turned, a window reset or the limit file was raised, so a held task is not stranded."""
    from sutra_app.orchestrator.limits import Limits
    path = tmp_path / "limits.json"
    limits = Limits(path, tenv.db, quotas=lambda: {}, clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    limits.update(monthly_usd=1.0)
    tenv.sql("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (?,?,?,?)", at(2026, 11, 4, 9), "claude", "test", 5.0)
    task = tenv.new()
    rec = Recurring(tenv.db, tenv.service, clock=Now(at(2026, 11, 4, 10)), tz=UTC)
    tenv.run(rec.tick_async())                                                              # nothing is due; the task is held by the limit
    assert tenv.status(task.id) == "queued"
    Limits(path, tenv.db, quotas=lambda: {}, clock=tenv.clock).update(monthly_usd=50.0)     # raised from outside this service
    tenv.run(rec.tick_async())
    assert tenv.status(task.id) == "starting"


def over_the_limit(tenv, tmp_path):
    """The monthly limit is used up: every start is held, the way the app wires it."""
    from sutra_app.orchestrator.limits import Limits
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=lambda: {}, clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    limits.update(monthly_usd=1.0)
    tenv.sql("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (?,?,?,?)", at(2026, 11, 4, 9), "claude", "test", 5.0)
    return limits


def test_a_run_whose_task_the_spending_limit_holds_is_not_called_working(tenv, tmp_path, rec):
    """QA recurring-limits: Run now, and a scheduled run, said 'working' for a task that was queued behind the limit and had not started."""
    limits = over_the_limit(tenv, tmp_path)
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    manual = rec.run_now(made.id)
    tenv.run(tenv.service.start_ready())
    assert tenv.status(manual.task_id) == "queued"                                           # held: nothing is running
    assert (rec.runs(made.id)[0].result, rec.get(made.id).last_run.result) == ("held", "held")
    assert rec.run_out(manual.id).result == "held"                                          # what the route answers once start_ready has decided
    limits.update(monthly_usd=50.0)
    tenv.run(tenv.service.start_ready())
    assert tenv.status(manual.task_id) == "starting" and rec.runs(made.id)[0].result == "working"     # raised: it started, and now it is working
    end(tenv, manual.task_id, "done")
    assert rec.runs(made.id)[0].result == "done"
    ((_, scheduled),) = rec.tick(at(2026, 11, 4, 9, 1)).started                              # the same holds for a due time
    limits.update(monthly_usd=1.0)
    tenv.run(tenv.service.start_ready())
    assert tenv.status(scheduled) == "queued" and rec.runs(made.id)[0].result == "held"


def test_both_limit_holds_begin_with_the_words_a_held_run_is_told_by():
    from sutra_app.orchestrator.limits import WAIT_GUARD, WAIT_SPEND
    from sutra_app.orchestrator.recurring import HELD, result_of
    assert WAIT_SPEND.startswith(HELD) and WAIT_GUARD.startswith(HELD)
    assert result_of("started", "queued", WAIT_SPEND) == "held" and result_of("started", "queued", "waiting to start") == "working"
    assert result_of("started", "starting", WAIT_SPEND) == "working" and result_of("skipped", "queued", WAIT_SPEND) == "skipped"


def test_a_queued_task_that_waits_for_a_slot_or_the_team_is_still_working(tenv, rec):
    """Only a limit makes a run 'held': a task that has just been made and is about to start is not."""
    made = rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))
    run = rec.run_now(made.id)
    assert tenv.status(run.task_id) == "queued" and rec.runs(made.id)[0].result == "working"


def test_the_loop_runs_ticks_and_stops_cleanly(tenv):
    rec = Recurring(tenv.db, tenv.service, clock=Now(at(2026, 11, 4, 10)), tz=UTC, tick_s=0.01)
    rec.create("web", "Daily digest", DAILY_9, now=at(2026, 11, 4, 8))

    async def go():
        report = await rec.start()                                                           # the clock reads 10:00: the 09:00 slot is owed
        assert len(report.started) == 1
        assert rec._loop_task is not None and not rec._loop_task.done()
        await asyncio.sleep(0.05)
        await rec.stop()
        assert rec._loop_task is None
        await rec.stop()                                                                     # safe twice
    tenv.run(go())
    assert len(tasks_of(tenv)) == 1


def test_the_app_makes_the_catch_up_at_start_and_ends_the_loop_at_stop(tmp_path):
    """Through the real lifespan: a schedule left behind while the app was closed is ONE run when the app opens, the loop runs while it is
    open and is gone after the stop."""
    base = "http://127.0.0.1:8780"
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url=base) as client:
        c = Scenario(client, app, connector)
        answered(c)                                                                          # the Web team exists and its first task is done
        made = c.services.recurring.create("web", "Daily digest", DAILY_9)
        away = c.services.clock.now() + 3 * 86400 + 3600
    assert c.services.recurring._loop_task is None                                           # stop_services ended the loop
    app2, connector2 = make_scenario(tmp_path, clock=FixedClock(away))
    with TestClient(app2, base_url=base) as client2:
        c2 = Scenario(client2, app2, connector2)
        rows = c2.db.conn().execute("SELECT trigger, outcome, folded, task_id FROM recurring_runs WHERE recurring_id = ?", (made.id,)).fetchall()
        assert len(rows) == 1 and rows[0]["trigger"] == "catch_up" and rows[0]["outcome"] == "started" and rows[0]["folded"] >= 1
        assert c2.one("SELECT count(*) FROM tasks WHERE title LIKE '%(scheduled)'") == 1
        loop = c2.services.recurring._loop_task
        assert loop is not None and not loop.done()
    assert c2.services.recurring._loop_task is None
