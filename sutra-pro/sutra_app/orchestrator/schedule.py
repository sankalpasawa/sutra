"""When a recurring task is due: the pure half of the scheduler (gap package routines-limits; docs/notes/GAP2-routines-limits.md).

    s = Schedule(every="weekdays", hour=9, minute=0)      # hour, day, weekdays or week; closed, so a free cron line cannot get in
    next_due(s, after, tz)                                # the first due time strictly after `after` (epoch seconds)
    latest_due(s, upto, tz)                               # the last due time at or before `upto`, None when there is none within 8 days
    owed(s, after, upto, tz)                              # (latest due time in (after, upto], how many due times that range holds)
    human(s)                                              # "Every weekday at 9:00 AM (local)"

Pure: no clock, no database, no file. `tz` is a `tzinfo` (a test passes a fixed one); None means the machine's own local time, which is
what the owner reads ("9:00 AM" is the owner's 9 in the morning, and the words always say "(local)").

The cadence is a preset, never a free cron line: the old app's `parse_cron` and its single-minute rule existed to keep a schedule from firing
more than once an hour ("a cost incident, not a feature"), and a closed list of four presets makes that rule structural. A sub-hourly
word is refused with the sentence that says why. Daily, weekday and weekly times are wall-clock times: on the day a clock skips an hour a
09:30 that does not exist runs at the first moment after the gap, and on the day it repeats an hour a time that happens twice runs on
its first pass, so a slot fires exactly once per local day. The hourly preset keeps the minute past each hour on the real clock.
"""
from datetime import date, datetime, time as dtime, timedelta, tzinfo
from typing import Literal

from pydantic import Field, field_validator, model_validator

from sutra_app.library.base import Value

__all__ = ["Schedule", "EVERY", "WEEKDAY_NAMES", "HOURLY_FLOOR", "COUNT_CAP", "next_due", "latest_due", "owed", "human", "clock12"]

EVERY = ("hour", "day", "weekdays", "week")
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
HOURLY_FLOOR = "A schedule runs at most once an hour: choose hour, day, weekdays or week."
LOOK_BACK_S = 8 * 86400                 # the longest gap between two due times is a week
COUNT_CAP = 2000                        # how many missed due times are counted before "many" (hourly for eleven weeks)


class Schedule(Value):
    """One cadence. `hour` is used by day, weekdays and week; `minute` by all four (the minute past the hour for `hour`); `weekday` by week
    only (Monday is 0). A field a cadence does not use is stored as 0, so two schedules that mean the same thing are equal."""

    every: Literal["hour", "day", "weekdays", "week"]
    hour: int = Field(0, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    weekday: int = Field(0, ge=0, le=6)

    @field_validator("every", mode="before")
    @classmethod
    def _at_most_hourly(cls, value: object) -> object:
        if value not in EVERY:
            raise ValueError(HOURLY_FLOOR)
        return value

    @model_validator(mode="before")
    @classmethod
    def _unused_fields_are_zero(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if data.get("every") == "hour":
            data["hour"] = 0
        if data.get("every") != "week":
            data["weekday"] = 0
        return data


# ---- the clock ------------------------------------------------------------------------------------------------------------------

def _offset(ts: int, tz: tzinfo | None) -> int:
    """The zone's offset from UTC, in seconds, at the moment `ts`."""
    moment = datetime.fromtimestamp(ts, tz) if tz is not None else datetime.fromtimestamp(ts).astimezone()
    found = moment.utcoffset()
    return int(found.total_seconds()) if found is not None else 0


def _epoch(day: date, hour: int, minute: int, tz: tzinfo | None) -> int:
    """Epoch seconds of a wall-clock time on a local date (a skipped time runs just after the gap, a repeated one on its first pass)."""
    return int(datetime.combine(day, dtime(hour, minute), tzinfo=tz).timestamp())


def _day_of(ts: int, tz: tzinfo | None) -> date:
    return (datetime.fromtimestamp(ts, tz) if tz is not None else datetime.fromtimestamp(ts)).date()


def _wanted(s: Schedule, day: date) -> bool:
    if s.every == "day":
        return True
    if s.every == "weekdays":
        return day.weekday() < 5
    return day.weekday() == s.weekday


def next_due(s: Schedule, after: int | float, tz: tzinfo | None = None) -> int:
    """The first due time strictly after `after` (epoch seconds, whole)."""
    after = int(after)
    if s.every == "hour":
        # the grid of "minute M of every local hour" is the same for every whole-hour offset, so a daylight-saving change does not move it
        wanted = s.minute * 60
        step = (wanted - (after + _offset(after, tz)) % 3600) % 3600
        return after + (step or 3600)
    first = _day_of(after, tz) - timedelta(days=1)             # a zone's day can start a day earlier than the date of `after` in UTC terms
    found: int | None = None
    for n in range(10):
        day = first + timedelta(days=n)
        if not _wanted(s, day):
            continue
        slot = _epoch(day, s.hour, s.minute, tz)
        if slot > after and (found is None or slot < found):
            found = slot
    if found is None:                                          # unreachable for a valid schedule: a week holds a due day
        raise ValueError("no due time in the next ten days")
    return found


def latest_due(s: Schedule, upto: int | float, tz: tzinfo | None = None) -> int | None:
    """The last due time at or before `upto`, looking back 8 days (None when there is none)."""
    upto = int(upto)
    slot = next_due(s, upto - LOOK_BACK_S, tz)
    last: int | None = None
    while slot <= upto:
        last = slot
        slot = next_due(s, slot, tz)
    return last


def owed(s: Schedule, after: int | float, upto: int | float, tz: tzinfo | None = None) -> tuple[int | None, int]:
    """(the latest due time in (after, upto], the number of due times in that range). (None, 0) when there is none. The count stops at
    COUNT_CAP: a machine that slept for weeks is told "many", not an exact figure."""
    after, upto = int(after), int(upto)
    if upto <= after:
        return None, 0
    latest = latest_due(s, upto, tz)
    if latest is None or latest <= after:
        return None, 0
    count, slot = 0, next_due(s, after, tz)
    while slot <= upto and count < COUNT_CAP:
        count += 1
        slot = next_due(s, slot, tz)
    return latest, count


# ---- words ----------------------------------------------------------------------------------------------------------------------

def clock12(hour: int, minute: int) -> str:
    """9:05 PM, from a 24-hour hour and a minute."""
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def human(s: Schedule) -> str:
    """The schedule in the owner's words. Always says local: a time without a zone has two honest readings."""
    if s.every == "hour":
        return "Every hour, on the hour (local)" if s.minute == 0 else f"Every hour at :{s.minute:02d} (local)"
    at = clock12(s.hour, s.minute)
    if s.every == "day":
        return f"Every day at {at} (local)"
    if s.every == "weekdays":
        return f"Every weekday at {at} (local)"
    return f"Every {WEEKDAY_NAMES[s.weekday]} at {at} (local)"
