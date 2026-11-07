"""Quiet hours and an hourly cap for what the app pushes at the owner (gap package routines-limits; docs/notes/GAP2-routines-limits.md).

    prefs = AttentionPrefs(<data>/attention.json)
    prefs.read()                                  # {"quiet_hours": {"start": "21:00", "end": "08:00"} | None, "nudges_per_hour": 3}; never raises
    prefs.write(quiet_hours=..., nudges_per_hour=...)      # read-modify-write; a key left out is kept; quiet_hours=None deletes the window
    clean_quiet_hours(value) / clamp_nudges(n)    # the checks: junk is a ValueError, never stored
    window_active(window, "02:00")                # quiet right now? inclusive at the start, exclusive at the end, wraps midnight

The pure rules are the old app's (`shadow_presence.py`), kept to the letter because their edge cases are the point: a window is `{start, end}` in
zero-padded 24-hour HH:MM (what `<input type=time>` sends); start == end is refused because it has two honest readings (all day, or no time at
all); the start minute is quiet and the end minute is not; a window that ends before it starts wraps midnight. The rate is a whole number
from 0 to 10 (default 3): numbers are clamped, junk raises, and booleans are junk (a switch's value must not become "one a day"). 0 means the
app never speaks unasked.

What the two settings govern is a page matter (the browser raises the desktop notices, chat_attention.js): during quiet hours no desktop
notice is pushed, but the count in the title, the strip and the pill stays, so nothing is hidden; a notice that a team FINISHED obeys the
hourly cap as well as quiet hours, while a question, an approval or a crash obeys quiet hours only. The page cannot ask the server on every
ping, so it holds a twin of `window_active` and both run one case table (tests/fixtures/quiet_hours_cases.json).

The file `<data>/attention.json` (mode 0600, atomic replace, absent = defaults) is only these two choices and any key a newer app added. It
never raises on read: an unreadable file or a junk value degrades toward speaking (no window, the default rate) rather than toward silence.
"""
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any

from sutra_app import oslayer
from sutra_app.connectors.base import write_private_file

__all__ = [
    "AttentionPrefs", "ATTENTION_FILE", "DEFAULT_NUDGES_PER_HOUR", "MIN_NUDGES_PER_HOUR", "MAX_NUDGES_PER_HOUR", "clean_quiet_hours", "clamp_nudges",
    "window_active", "minutes_of", "UNSET",
]

log = logging.getLogger(__name__)
ATTENTION_FILE = "attention.json"
DEFAULT_NUDGES_PER_HOUR = 3
MIN_NUDGES_PER_HOUR = 0
MAX_NUDGES_PER_HOUR = 10
_QUIET_KEY = "quiet_hours"
_NUDGES_KEY = "nudges_per_hour"
_HM = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
_MAX_BYTES = 64 * 1024
UNSET: Any = object()                    # "leave it as it is" (None means clear)


def minutes_of(hm: str) -> int:
    """Minutes after midnight of a zero-padded HH:MM."""
    found = _HM.fullmatch(hm) if isinstance(hm, str) else None
    if found is None:
        raise ValueError("a time of day is HH:MM, 24-hour, with the zero")
    return int(found.group(1)) * 60 + int(found.group(2))


def clean_quiet_hours(value: Any) -> dict[str, str]:
    """A window as stored: `{"start": "21:00", "end": "08:00"}`, or ValueError. Both ends, zero-padded, and not the same time."""
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise ValueError("quiet hours need a start and an end")
    start, end = value["start"], value["end"]
    for part in (start, end):
        if not isinstance(part, str) or _HM.fullmatch(part) is None:
            raise ValueError("a time of day is HH:MM, 24-hour, with the zero (like 21:00)")
    if start == end:
        raise ValueError("quiet hours that start and end at the same time could mean all day or no time at all: choose different times")
    return {"start": start, "end": end}


def clamp_nudges(value: Any) -> int:
    """A legal rate: numbers are clamped into 0..10, anything that is not a whole number (a boolean included) is a ValueError."""
    if isinstance(value, bool):
        raise ValueError("nudges_per_hour must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("nudges_per_hour must be a whole number") from None
    if isinstance(value, float) and value != number:
        raise ValueError("nudges_per_hour must be a whole number")
    return max(MIN_NUDGES_PER_HOUR, min(MAX_NUDGES_PER_HOUR, number))


def window_active(window: dict[str, str] | None, at: str | int | datetime | dtime) -> bool:
    """Is `at` (HH:MM, minutes after midnight, or a time) inside the window? Inclusive at the start, exclusive at the end, wrapping midnight.
    No window is never quiet."""
    if not window:
        return False
    if isinstance(at, (datetime, dtime)):
        minute = at.hour * 60 + at.minute
    elif isinstance(at, str):
        minute = minutes_of(at)
    else:
        minute = int(at)
    start, end = minutes_of(window["start"]), minutes_of(window["end"])
    return start <= minute < end if start < end else (minute >= start or minute < end)


class AttentionPrefs:
    """`<data>/attention.json`. Thread-safe; read never raises, write refuses junk before touching the file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _raw(self) -> dict[str, Any]:
        try:
            if self.path.stat().st_size > _MAX_BYTES:
                return {}
            found = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.warning("the attention file %s is not read (it will be replaced by the next save)", self.path)
            return {}
        return found if isinstance(found, dict) else {}

    def read(self) -> dict[str, Any]:
        raw = self._raw()
        try:
            window: dict[str, str] | None = clean_quiet_hours(raw.get(_QUIET_KEY)) if _QUIET_KEY in raw else None
        except ValueError:
            window = None                                         # a hand-edited junk window: speak rather than go silent
        try:
            rate = clamp_nudges(raw[_NUDGES_KEY]) if _NUDGES_KEY in raw else DEFAULT_NUDGES_PER_HOUR
        except ValueError:
            rate = DEFAULT_NUDGES_PER_HOUR
        return {_QUIET_KEY: window, _NUDGES_KEY: rate}

    def write(self, *, quiet_hours: Any = UNSET, nudges_per_hour: Any = UNSET) -> dict[str, Any]:
        """Change what is given, keep the rest (and any key this app does not know). `quiet_hours=None` clears the window by deleting the key.
        A junk value is a ValueError and nothing is written."""
        window = rate = None
        if quiet_hours is not UNSET and quiet_hours is not None:
            window = clean_quiet_hours(quiet_hours)
        if nudges_per_hour is not UNSET:
            rate = clamp_nudges(nudges_per_hour)
        with self._lock:
            kept = self._raw()
            if quiet_hours is not UNSET:
                if quiet_hours is None:
                    kept.pop(_QUIET_KEY, None)
                else:
                    kept[_QUIET_KEY] = window
            if nudges_per_hour is not UNSET:
                kept[_NUDGES_KEY] = rate
            kept.setdefault("version", 1)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self.path.parent / f".{self.path.name}.{uuid.uuid4().hex[:8]}.tmp"
            try:
                write_private_file(tmp, json.dumps(kept, indent=2, sort_keys=True) + "\n")
                oslayer.replace(tmp, self.path)
            finally:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
        return self.read()
