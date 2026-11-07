"""The pure schedule math of recurring tasks (gap package routines-limits): presets, the next due time, what a long absence owes, the words,
and the hourly floor. Fixed-offset zones need no tz database; the daylight-saving cases skip where it is absent (Windows CI)."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sutra_app.orchestrator.schedule import HOURLY_FLOOR, Schedule, human, latest_due, next_due, owed

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))


def at(year, month, day, hour=0, minute=0, tz=UTC) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=tz).timestamp())


def test_a_daily_schedule_is_due_at_its_hour_and_next_due_is_strictly_after():
    s = Schedule(every="day", hour=9, minute=0)
    assert next_due(s, at(2026, 11, 4, 10), UTC) == at(2026, 11, 5, 9)
    assert next_due(s, at(2026, 11, 4, 8, 59), UTC) == at(2026, 11, 4, 9)
    assert next_due(s, at(2026, 11, 4, 9), UTC) == at(2026, 11, 5, 9)          # at the due time itself the next one is a day away


def test_a_schedule_reads_in_the_zone_it_is_given():
    s = Schedule(every="day", hour=9, minute=0)
    assert next_due(s, at(2026, 11, 4, 0, tz=IST), IST) == at(2026, 11, 4, 9, tz=IST)          # 03:30 UTC, not 09:00 UTC


def test_weekdays_skip_the_weekend_and_weekly_names_its_day():
    friday = at(2026, 11, 6, 10)                                                 # 2026-11-06 is a Friday
    assert datetime.fromtimestamp(friday, UTC).weekday() == 4
    weekdays = Schedule(every="weekdays", hour=9, minute=0)
    assert next_due(weekdays, friday, UTC) == at(2026, 11, 9, 9)                  # Monday
    weekly = Schedule(every="week", hour=9, minute=30, weekday=2)                 # Wednesday
    assert next_due(weekly, friday, UTC) == at(2026, 11, 11, 9, 30)


def test_hourly_keeps_its_minute_on_the_clock_of_the_zone():
    s = Schedule(every="hour", minute=15)
    assert next_due(s, at(2026, 11, 4, 10, 0), UTC) == at(2026, 11, 4, 10, 15)
    assert next_due(s, at(2026, 11, 4, 10, 15), UTC) == at(2026, 11, 4, 11, 15)
    # local minute 15 in a zone at +5:30 is minute 45 of the UTC hour
    assert next_due(s, at(2026, 11, 4, 10, 0), IST) == at(2026, 11, 4, 10, 45)
    on_the_hour = Schedule(every="hour")
    assert next_due(on_the_hour, at(2026, 11, 4, 10, 0), UTC) == at(2026, 11, 4, 11, 0)


def test_consecutive_due_times_are_never_less_than_an_hour_apart():
    for s in (Schedule(every="hour", minute=7), Schedule(every="day", hour=3), Schedule(every="weekdays", hour=23, minute=59), Schedule(every="week")):
        t, last = at(2026, 11, 1), None
        for _ in range(60):
            t = next_due(s, t, UTC)
            assert last is None or t - last >= 3600
            last = t


@pytest.mark.parametrize("word", ["minute", "30 minutes", "every minute", "second", "", None, 5, "*/5 * * * *"])
def test_a_cadence_below_an_hour_is_refused_with_the_sentence_that_says_why(word):
    with pytest.raises(ValidationError) as caught:
        Schedule(every=word)
    assert HOURLY_FLOOR in str(caught.value)


def test_the_schedule_is_closed_and_strict_and_unused_fields_are_zero():
    with pytest.raises(ValidationError):
        Schedule(every="day", hour=24)
    with pytest.raises(ValidationError):
        Schedule(every="day", minute=60)
    with pytest.raises(ValidationError):
        Schedule(every="day", hour=True)                                          # a boolean is not an hour
    with pytest.raises(ValidationError):
        Schedule(every="day", cron="* * * * *")                                   # no free cron line gets in
    assert Schedule(every="hour", hour=9, minute=5, weekday=3) == Schedule(every="hour", minute=5)
    assert Schedule(every="day", hour=9, weekday=3) == Schedule(every="day", hour=9)
    assert Schedule(every="week", hour=9, weekday=3).weekday == 3


def test_a_long_absence_owes_one_run_and_counts_what_it_folded_in():
    s = Schedule(every="day", hour=9, minute=0)
    cursor = at(2026, 11, 1, 9)                       # the last due time dealt with
    latest, count = owed(s, cursor, at(2026, 11, 4, 10), UTC)                      # the app was away for three days
    assert (latest, count) == (at(2026, 11, 4, 9), 3)
    assert owed(s, at(2026, 11, 4, 9), at(2026, 11, 4, 10), UTC) == (None, 0)       # nothing new since the last one
    assert owed(s, at(2026, 11, 4, 10), at(2026, 11, 4, 8), UTC) == (None, 0)       # a clock that went back owes nothing
    assert owed(s, at(2026, 11, 3, 9), at(2026, 11, 4, 9), UTC) == (at(2026, 11, 4, 9), 1)        # inclusive at the end, exclusive at the start


def test_the_latest_due_time_is_found_even_when_the_count_is_capped():
    s = Schedule(every="hour", minute=0)
    latest, count = owed(s, at(2026, 1, 1), at(2026, 11, 4, 10, 30), UTC)           # ten months of hours
    assert latest == at(2026, 11, 4, 10)
    assert count == 2000                                                           # capped: "many"
    assert latest_due(Schedule(every="week", weekday=0, hour=9), at(2026, 11, 4, 10), UTC) == at(2026, 11, 2, 9)


def test_the_words_always_say_local():
    assert human(Schedule(every="weekdays", hour=9)) == "Every weekday at 9:00 AM (local)"
    assert human(Schedule(every="day", hour=0, minute=5)) == "Every day at 12:05 AM (local)"
    assert human(Schedule(every="day", hour=12)) == "Every day at 12:00 PM (local)"
    assert human(Schedule(every="day", hour=21, minute=30)) == "Every day at 9:30 PM (local)"
    assert human(Schedule(every="week", hour=9, weekday=4)) == "Every Friday at 9:00 AM (local)"
    assert human(Schedule(every="hour")) == "Every hour, on the hour (local)"
    assert human(Schedule(every="hour", minute=15)) == "Every hour at :15 (local)"
    for s in (Schedule(every="hour"), Schedule(every="day"), Schedule(every="weekdays"), Schedule(every="week")):
        assert human(s).endswith("(local)")


# ---- daylight saving ------------------------------------------------------------------------------------------------------------

def new_york():
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        return zoneinfo.ZoneInfo("America/New_York")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no tz database on this machine")


def test_a_daily_time_that_does_not_exist_fires_once_on_the_day_the_clock_springs_forward():
    ny = new_york()
    s = Schedule(every="day", hour=2, minute=30)                                  # 2027-03-14: 02:00 jumps to 03:00 in New York
    t, fired = at(2027, 3, 12, 12, tz=ny), []
    for _ in range(4):
        t = next_due(s, t, ny)
        fired.append(datetime.fromtimestamp(t, ny))
    assert [d.date().isoformat() for d in fired] == ["2027-03-13", "2027-03-14", "2027-03-15", "2027-03-16"]      # one per local day
    assert fired[1].hour == 3 and fired[1].minute == 30                           # the missing 02:30 runs right after the gap
    assert fired[0].hour == 2 and fired[2].hour == 2


def test_a_daily_time_that_happens_twice_fires_once_on_the_day_the_clock_falls_back():
    ny = new_york()
    s = Schedule(every="day", hour=1, minute=30)                                  # 2026-11-01: 01:30 happens twice in New York
    t, fired = at(2026, 10, 30, 12, tz=ny), []
    for _ in range(4):
        t = next_due(s, t, ny)
        fired.append(t)
    days = [datetime.fromtimestamp(x, ny).date().isoformat() for x in fired]
    assert days == ["2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03"]
    assert len(set(fired)) == 4


def test_hourly_stays_one_hour_apart_across_both_clock_changes():
    ny = new_york()
    s = Schedule(every="hour", minute=30)
    for start in (at(2027, 3, 14, 0, tz=ny), at(2026, 11, 1, 0, tz=ny)):
        t, last = start, None
        for _ in range(8):
            t = next_due(s, t, ny)
            assert last is None or t - last == 3600
            last = t
