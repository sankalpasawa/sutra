"""Limits on unattended work: a monthly spending limit and a plan-window guard (gap package routines-limits; docs/notes/GAP2-routines-limits.md).

    limits = Limits(path, db, quotas=lambda: {"claude": Quota | None, "codex": ...}, clock=clock, offline=False)
    limits.state(now)                          # {"spend": {...}, "guard": {...}}: what the Home line and the Settings group show
    limits.update(monthly_usd=10.0, guard_enabled=True)       # 0 or None clears the limit
    limits.continue_now(now)                   # one Continue: work proceeds until the windows that hold it reset
    limits.gate(conn, now, dept_id) -> str     # TaskService's start gate: "" lets a task start, else the words it waits with

Two guards, one gate. Both only decide whether a QUEUED task may START: a run already in flight is the engine process's and is never touched
(the old app paused a task before its next step; this is weaker on purpose). A held task stays `queued` with the reason as its waiting
detail, and starts by itself when the reason ends (the limit is raised, Continue is pressed, the month turns, the window resets): the
scheduler's tick and every route that changes a limit call `start_ready`.

  spend   the owner's monthly limit in dollars. Level none (no limit), ok, warn from 80 %, over from 100 %. Spent = the month's known dollars
          in the usage ledger (UTC month, like the console; stub rows left out). Dollars are Claude's list-price estimate (D37) and Codex rows
          carry none, so the number is "about" and a subscription's real limit is its quota. A limit of 0 or none is no limit.
  guard   plan windows (the 5-hour and weekly windows the CLIs report, GAP-providers). Warn from 70 % always; hold from 80 % only when the owner
          switched the guard on (default off). One Continue lets work proceed until the holding window resets (stored with its reset time, so a
          restart does not undo it). It fails open: no snapshot, a window that has reset, or a snapshot too old to trust holds nothing, and so does
          any error in here.

The file `<data>/limits.json` (mode 0600, written atomically) holds the owner's two choices and the Continue marks; it never holds a figure the
CLIs reported. A file that does not read is ignored (defaults), never an error.
"""
import json
import logging
import math
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from sutra_app import oslayer
from sutra_app.connectors.base import write_private_file
from sutra_app.library.base import Value
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.ids import iso_z

__all__ = [
    "Limits", "LimitsFile", "GuardSetting", "LimitsStore", "LIMITS_FILE", "WARN_AT", "GUARD_WARN", "GUARD_HOLD", "MAX_LIMIT_USD", "STALE_S",
    "month_start", "month_end", "spend_status", "guard_reading", "money", "reset_words", "WAIT_SPEND", "WAIT_GUARD",
]

log = logging.getLogger(__name__)
LIMITS_FILE = "limits.json"
WARN_AT = 0.8                    # the old app's WARN_AT: one line at 80 % of the monthly limit
GUARD_WARN = 0.70                # the old plugin guard: warn at 70, hold at 80
GUARD_HOLD = 0.80
MAX_LIMIT_USD = 100_000          # the old app's ceiling for a limit
STALE_S = 6 * 3600               # a window with no reset time is trusted this long after it was seen
_MAX_BYTES = 64 * 1024
_NAMES = {"claude": "Claude", "codex": "Codex"}
WAIT_SPEND = "waiting: this month's spending limit is used up; raise it to continue"
WAIT_GUARD = "waiting: {line} (press Continue to run anyway)"


# ---- the file -------------------------------------------------------------------------------------------------------------------

class GuardSetting(Value):
    enabled: bool = False
    continued: dict[str, int] = Field(default_factory=dict)             # "claude:seven_day" -> epoch seconds the Continue lasts until


class LimitsFile(Value):
    version: Literal[1] = 1
    monthly_usd: float | None = Field(None, gt=0, le=MAX_LIMIT_USD)
    guard: GuardSetting = Field(default_factory=GuardSetting)


class LimitsStore:
    """`<data>/limits.json`: read on demand (cached while the file is unchanged), replaced atomically, never raises on a bad file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._seen: tuple[int, int] | None = None
        self._held = LimitsFile()

    def load(self) -> LimitsFile:
        with self._lock:
            try:
                stat = self.path.stat()
            except FileNotFoundError:
                self._seen, self._held = None, LimitsFile()
                return self._held
            except OSError:
                return self._held
            mark = (stat.st_mtime_ns, stat.st_size)
            if mark == self._seen:
                return self._held
            try:
                if stat.st_size > _MAX_BYTES:
                    raise ValueError("too large")
                self._held = LimitsFile.model_validate_json(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ValidationError) as exc:
                log.warning("the limits file %s is not used (%s); defaults apply until it is saved again", self.path, type(exc).__name__)
                self._held = LimitsFile()
            self._seen = mark
            return self._held

    def save(self, found: LimitsFile) -> LimitsFile:
        """Write the whole file, atomically and private. Raises OSError."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self.path.parent / f".{self.path.name}.{uuid.uuid4().hex[:8]}.tmp"
            try:
                write_private_file(tmp, found.model_dump_json(indent=2))
                oslayer.replace(tmp, self.path)
            finally:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
            self._held = found
            try:
                stat = self.path.stat()
                self._seen = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                self._seen = None
            return found


# ---- words ----------------------------------------------------------------------------------------------------------------------

def money(value: float) -> str:
    """$8.20, $10, $1,250 (a whole number of dollars has no cents; under $100 the cents are shown)."""
    whole = abs(value - round(value)) < 0.005
    return f"${value:,.0f}" if whole else f"${value:,.2f}"


def reset_words(resets_at: float | None, now: float) -> str:
    """"resets 14:05" for a reset later today, "resets Fri 09:00" for a later day, "" when there is none. Local time of this machine."""
    if resets_at is None or resets_at <= now:
        return ""
    moment = datetime.fromtimestamp(resets_at)
    same_day = moment.date() == datetime.fromtimestamp(now).date()
    return "resets " + (moment.strftime("%H:%M") if same_day else moment.strftime("%a %H:%M"))


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


# ---- spend ----------------------------------------------------------------------------------------------------------------------

def month_start(now: float) -> int:
    """Epoch seconds of the first moment of the UTC month that holds `now`."""
    moment = datetime.fromtimestamp(now, timezone.utc)
    return int(datetime(moment.year, moment.month, 1, tzinfo=timezone.utc).timestamp())


def month_end(now: float) -> int:
    """Epoch seconds of the first moment of the next UTC month."""
    moment = datetime.fromtimestamp(now, timezone.utc)
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())


def spend_status(conn: sqlite3.Connection, limit: float | None, now: float) -> dict[str, Any]:
    """The month's known dollars against the limit. `partial` counts the calls of this month that carry no dollar figure (Codex rows): they
    are not in `spent`, and the answer says so rather than pretending."""
    start = month_start(now)
    row = conn.execute("SELECT sum(usd) AS usd, sum(usd IS NULL) AS unpriced FROM usage_ledger WHERE at >= ? AND provider != 'stub'", (start,)).fetchone()
    spent = round(float(row["usd"] or 0.0), 6)
    unpriced = int(row["unpriced"] or 0)
    out: dict[str, Any] = {"limit": limit, "spent": spent, "pct": None, "level": "none", "unpriced_calls": unpriced,
                           "month": datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m"), "month_ends_at": iso_z(month_end(now)), "line": ""}
    if not limit:
        out["limit"] = None
        return out
    pct = spent / limit
    out["pct"] = round(pct, 4)
    out["level"] = "over" if pct >= 1 else ("warn" if pct >= WARN_AT else "ok")
    about = f"about {money(spent)} of your {money(limit)} monthly limit"
    out["line"] = (f"This month's spending limit is used up: {about}. New tasks wait until you raise it or the month ends" if out["level"] == "over"
                   else about[:1].upper() + about[1:])
    return out


# ---- the plan windows -----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Window:
    provider: str
    key: str
    label: str
    used: float
    resets_at: float | None


def _windows_of(quotas: Mapping[str, Any], now: float, providers: tuple[str, ...] | None) -> list[_Window]:
    """The live windows of the considered providers: a window with no figure is left out, a window whose reset has passed is over (the snapshot
    is stale), a window with no reset time is trusted for STALE_S after the snapshot was seen."""
    found: list[_Window] = []
    for provider, quota in quotas.items():
        if quota is None or (providers is not None and provider not in providers):
            continue
        listed = [(w.key, w.label, w.used, w.resets_at) for w in (getattr(quota, "windows", None) or [])]
        if not listed and getattr(quota, "used", None) is not None:                      # an older snapshot: only the metering window
            name = str(quota.window or "plan window")
            listed = [(re.sub(r"[^a-z0-9_]+", "_", name.lower())[:40] or "window", name[:60], quota.used, quota.resets_at)]
        seen_at = getattr(quota, "seen_at", None)
        for key, label, used, resets_at in listed:
            if used is None or not math.isfinite(used):
                continue
            if resets_at is not None and resets_at <= now:
                continue
            if resets_at is None and (seen_at is None or now - seen_at > STALE_S):
                continue
            found.append(_Window(provider, key, label, float(used), resets_at))
    return found


def guard_reading(quotas: Mapping[str, Any], now: float, *, enabled: bool, continued: Mapping[str, int] | None = None,
                  providers: tuple[str, ...] | None = None, warn: float = GUARD_WARN, hold: float = GUARD_HOLD) -> dict[str, Any]:
    """What the plan windows say. `level`: none (no live window), ok, warn (a window at `warn` or more) or hold (a window at `hold` or more).
    `holding` is true only when the guard is on, a window is at `hold` or more and that window has no Continue that is still running. `top` is
    the fullest window that matters (the holding one, else the fullest)."""
    marks = {k: int(v) for k, v in (continued or {}).items()}
    windows = _windows_of(quotas, now, providers)
    rows = []
    for w in windows:
        key = f"{w.provider}:{w.key}"
        level = "hold" if w.used >= hold else ("warn" if w.used >= warn else "ok")
        rows.append({"provider": w.provider, "key": w.key, "label": w.label, "used": round(w.used, 4), "resets_at": iso_z(w.resets_at) if w.resets_at else None,
                     "level": level, "continued": level == "hold" and marks.get(key, 0) > now, "_w": w})
    out: dict[str, Any] = {"enabled": enabled, "level": "none", "holding": False, "top": None, "line": "", "windows": []}
    if not rows:
        return out
    rank = {"ok": 0, "warn": 1, "hold": 2}
    out["level"] = max((r["level"] for r in rows), key=rank.__getitem__)
    holders = [r for r in rows if r["level"] == "hold" and not r["continued"]]
    pool = holders or [r for r in rows if r["level"] != "ok"] or rows
    top = max(pool, key=lambda r: r["used"])
    w: _Window = top["_w"]
    pct = int(math.floor(w.used * 100 + 1e-9))
    words = f"{_NAMES.get(w.provider, w.provider.title())} {_lower_first(w.label)} window is at {pct}%"
    when = reset_words(w.resets_at, now)
    out.update(holding=enabled and bool(holders), line=words + (", " + when if when else ""))
    out["top"] = {k: v for k, v in top.items() if k != "_w"}
    out["windows"] = [{k: v for k, v in r.items() if k != "_w"} for r in rows if r["level"] != "ok"]
    return out


# ---- the facade -----------------------------------------------------------------------------------------------------------------

class Limits:
    """The owner's choices, the two readings and the start gate. Synchronous; the readings are cheap (one indexed SUM, in-memory snapshots)."""

    def __init__(self, path: Path, db: Database, *, quotas: Callable[[], Mapping[str, Any]], clock: Any = None, offline: bool = False) -> None:
        self.store = LimitsStore(path)
        self.db = db
        self.quotas = quotas
        self.clock = clock
        self.offline = offline

    def _now(self, now: float | None) -> float:
        return float(now if now is not None else (self.clock.now() if self.clock is not None else datetime.now().timestamp()))

    def _quotas(self) -> Mapping[str, Any]:
        try:
            return self.quotas() or {}
        except Exception:                                                  # noqa: BLE001  (the guard fails open)
            log.exception("the plan windows could not be read")
            return {}

    def state(self, now: float | None = None) -> dict[str, Any]:
        moment = self._now(now)
        found = self.store.load()
        spend = spend_status(self.db.conn(), found.monthly_usd, moment)
        guard = guard_reading(self._quotas(), moment, enabled=found.guard.enabled, continued=found.guard.continued)
        return {"spend": spend, "guard": guard}

    def update(self, *, monthly_usd: float | None | Literal["keep"] = "keep", guard_enabled: bool | None = None, now: float | None = None) -> dict[str, Any]:
        """Set the monthly limit (None or 0 clears it) and/or the guard switch. Switching the guard off forgets its Continue marks."""
        found = self.store.load()
        limit = found.monthly_usd if monthly_usd == "keep" else (float(monthly_usd) if monthly_usd else None)
        guard = found.guard if guard_enabled is None else GuardSetting(enabled=guard_enabled, continued=found.guard.continued if guard_enabled else {})
        self.store.save(LimitsFile(monthly_usd=limit, guard=guard))
        return self.state(now)

    def continue_now(self, now: float | None = None) -> dict[str, Any]:
        """One Continue: every window that holds work right now lets it proceed until that window resets (an hour when it names no reset time)."""
        moment = self._now(now)
        found = self.store.load()
        reading = guard_reading(self._quotas(), moment, enabled=True, continued=found.guard.continued)
        marks = {k: v for k, v in found.guard.continued.items() if v > moment}
        for row in reading["windows"]:
            if row["level"] == "hold":
                until = int(datetime.fromisoformat(row["resets_at"].replace("Z", "+00:00")).timestamp()) if row["resets_at"] else int(moment) + 3600
                marks[f"{row['provider']}:{row['key']}"] = until
        self.store.save(LimitsFile(monthly_usd=found.monthly_usd, guard=GuardSetting(enabled=found.guard.enabled, continued=marks)))
        return self.state(moment)

    def pinned_of(self, conn: sqlite3.Connection, dept_id: str) -> tuple[str, ...] | None:
        """The provider a team's chat is pinned to (the pill, ABS-8), as a one-item tuple; None when it follows the policy."""
        found = conn.execute("SELECT s.pinned FROM graph_nodes g JOIN chat_sessions s ON s.id = g.chat_session_id WHERE g.id = ?", (dept_id,)).fetchone()
        return (found["pinned"],) if found is not None and found["pinned"] in ("claude", "codex") else None

    def gate(self, conn: sqlite3.Connection, now: float, dept_id: str) -> str:
        """TaskService's start gate: "" when a task of `dept_id` may start, else the words it waits with. Never raises."""
        try:
            found = self.store.load()
            if found.monthly_usd:
                spend = spend_status(conn, found.monthly_usd, now)
                if spend["level"] == "over":
                    return f"{WAIT_SPEND} (about {money(spend['spent'])} of {money(found.monthly_usd)})"
            if found.guard.enabled and not self.offline:
                reading = guard_reading(self._quotas(), now, enabled=True, continued=found.guard.continued, providers=self.pinned_of(conn, dept_id))
                if reading["holding"]:
                    return WAIT_GUARD.format(line=reading["line"])
        except Exception:                                                  # noqa: BLE001  (fail open: a broken guard must not stop the work)
            log.exception("the limits gate failed; the task may start")
        return ""
