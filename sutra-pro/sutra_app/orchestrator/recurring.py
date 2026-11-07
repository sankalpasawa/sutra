"""Recurring work: a team's standing task on a schedule (gap package routines-limits; docs/notes/GAP2-routines-limits.md; the old app's routines).

    rec = Recurring(db, tasks, clock=clock, tz=None)         # tz None = the machine's local time (the words always say "(local)")
    rec.create(dept_id, text, Schedule(every="weekdays", hour=9))      # -> RecurringOut
    rec.update(id, text=, schedule=, enabled=) / rec.delete(id) / rec.listing() / rec.get(id) / rec.runs(id) / rec.run_now(id)
    rec.tick(now)                                             # what is due at `now`: one ordinary task per schedule, a skip row, or a pause
    await rec.start() / await rec.stop()                      # one tick at start (the catch-up), then one every TICK_S while the app runs

The server keeps running with the browser closed (the browser is the window, D12), so an in-process tick covers "the owner is away". The one
case it cannot cover is the app being quit or the machine asleep, and that is a catch-up: when the app next ticks, every due time since the
last one dealt with (`recurring.cursor_at`) is ONE run, and its row says how many due times were folded into it. Nothing is replayed once per
missed slot.

A due time is dealt with exactly once. Its row in `recurring_runs` is unique on (recurring_id, due_at) and is written in the same transaction
as the task and the new cursor, so a restart, a second tick or a slow clock cannot start the same slot twice. A cursor that is later than the
clock (the clock ran ahead, a catch-up moved the cursor, and the clock was corrected) is moved back to "now" by the next tick, so the schedule
does not go silent for the length of the error; a due time in the one tick between the correction and that tick is not owed. What a due time becomes:

    the team is free            a task made through `TaskService.create_scheduled` (an ordinary queued task, titled "... (scheduled)", with a
                                note in the team's chat), then `start_ready` as for any task: the caps, the one-live-task-per-team rule, the
                                spending limit and the plan-window guard all apply unchanged
    the team is busy            no task. A row that says why: still working, waiting for you, or already has work waiting to start
    three crashes in a row      the schedule pauses itself and says so (`paused_reason`); the owner switches it on again

A run's outcome is never stored: it is read from the task's own status by the join, so `done` and `done_with_open_items` are never both
called success. A schedule whose runs were all started by hand says `never_fired_on_schedule`: a green manual run does not prove the
schedule fires.
"""
import asyncio
import json
import logging
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Annotated, Literal

from pydantic import StringConstraints, ValidationError

from sutra_app.library.base import Value
from sutra_app.library.types import clip, violation
from sutra_app.orchestrator.db import Database, run_blocking
from sutra_app.orchestrator.errors import AppError, Busy, NotFound, validation_error
from sutra_app.orchestrator.ids import Clock, SystemClock, iso_z
from sutra_app.orchestrator.models import Count, Iso, Name, TaskOut
from sutra_app.orchestrator.schedule import Schedule, human, next_due, owed
from sutra_app.orchestrator.textutil import one_line_title

__all__ = ["Recurring", "RecurringOut", "RunOut", "TickReport", "TICK_S", "LATE_S", "MAX_RECURRING", "MAX_TEXT", "CRASH_LIMIT", "result_of"]

log = logging.getLogger(__name__)
TICK_S = 30.0                    # how often the running app looks for due schedules
LATE_S = 300                     # a due time started more than five minutes late is a catch-up (the app was away)
MAX_RECURRING = 50               # schedules in all
MAX_TEXT = 4000                  # the words of one standing task
CRASH_LIMIT = 3                  # crashes in a row that pause a schedule
_OPEN = ("starting", "running", "waiting_user", "queued", "blocked")
_PAUSED = f"Paused after {CRASH_LIMIT} runs in a row ended with a problem. Look at the team's last attempts, then switch it on again."
_UNREADABLE = "Paused: its schedule could not be read. Set it again."
_RESULT = {"queued": "working", "blocked": "working", "starting": "working", "running": "working", "waiting_user": "waiting",
           "done": "done", "done_with_open_items": "open_items", "crashed": "crashed", "stopped": "stopped", "cancelled": "stopped"}
Result = Literal["skipped", "working", "held", "waiting", "done", "open_items", "crashed", "stopped"]
HELD = "waiting:"                # how a queued task's detail begins when a limit holds its start (limits.WAIT_SPEND, limits.WAIT_GUARD)


class RunOut(Value):
    """One due time that was dealt with. `result` is read from the task's status (never stored): skipped, working, held (queued behind a limit:
    nothing has started), waiting (for the owner), done, open_items (done with open items), crashed or stopped."""

    id: Count
    due_at: Iso
    at: Iso
    trigger: Literal["schedule", "catch_up", "manual"]
    result: Result
    task_id: str | None = None
    folded: Count = 0                                                    # earlier due times this run stands for
    reason: Annotated[str, StringConstraints(max_length=300)] = ""


class RecurringOut(Value):
    id: Annotated[str, StringConstraints(pattern=r"^rec_[0-9a-f]{12}$")]
    dept_id: str
    dept_name: Name
    text: Annotated[str, StringConstraints(max_length=MAX_TEXT)]
    schedule: Schedule | None = None                                     # None only for a stored schedule this build cannot read (listed as paused)
    human: str
    enabled: bool
    paused_reason: Annotated[str, StringConstraints(max_length=300)] = ""      # empty on a schedule the owner paused; the app's words otherwise
    next_due_at: Iso | None = None                                       # None while paused
    created_at: Iso
    last_run: RunOut | None = None
    never_fired_on_schedule: bool = False


@dataclass
class TickReport:
    started: list[tuple[str, str]] = field(default_factory=list)         # (schedule id, task id)
    skipped: list[str] = field(default_factory=list)                     # schedule ids
    paused: list[str] = field(default_factory=list)                      # schedule ids

    def __bool__(self) -> bool:
        return bool(self.started or self.skipped or self.paused)


def result_of(outcome: str, task_status: str | None, detail: str = "") -> str:
    """The word for a run: a skip is `skipped`; a started run is whatever its task's status says (a missing task reads as `stopped`), except a
    task still `queued` with a limit's waiting words, which is `held`: the owner is told it has not started, not that it is working."""
    if outcome == "skipped":
        return "skipped"
    if task_status == "queued" and (detail or "").startswith(HELD):
        return "held"
    return _RESULT.get(task_status or "", "stopped")


def _new_id() -> str:
    return "rec_" + secrets.token_hex(6)


class _CouldNotStart(Exception):
    """The task for a due time could not be made (the team refused it). Carries what the row of the skip must say."""

    def __init__(self, due_at: int, trigger: str, folded: int, message: str) -> None:
        super().__init__(message)
        self.due_at, self.trigger, self.folded, self.message = due_at, trigger, folded, message


class Recurring:
    """Store, service and ticker of the schedules. The methods are synchronous (each opens its own transaction) except `start`, `stop` and
    `tick_async`, which talk to the task service and the loop."""

    def __init__(self, db: Database, tasks: object, *, clock: Clock | None = None, tz: tzinfo | None = None,
                 new_id: Callable[[], str] = _new_id, tick_s: float = TICK_S) -> None:
        self.db = db
        self.tasks = tasks
        self.clock = clock or SystemClock()
        self.tz = tz
        self._new_id = new_id
        self.tick_s = tick_s
        self._loop_task: asyncio.Task[None] | None = None

    # ---- reads ----------------------------------------------------------------------------------------------------------------

    def _run_out(self, r: sqlite3.Row) -> RunOut:
        return RunOut(
            id=r["id"], due_at=iso_z(r["due_at"]), at=iso_z(r["at"]), trigger=r["trigger"], result=result_of(r["outcome"], r["status"], r["detail"]),
            task_id=r["task_id"], folded=r["folded"], reason=clip(r["reason"], 300))

    _RUN_SQL = ("SELECT r.id, r.due_at, r.at, r.trigger, r.outcome, r.task_id, r.folded, r.reason, t.status, g.detail FROM recurring_runs r"
                " LEFT JOIN tasks t ON t.id = r.task_id"
                " LEFT JOIN graph_nodes g ON g.task_id = r.task_id AND g.step_ref = 'task' AND g.kind = 'step'")

    @staticmethod
    def _read(raw: str) -> Schedule | None:
        """The stored schedule, or None when it does not read (a build with another cadence wrote it, or the file was edited by hand)."""
        try:
            return Schedule.model_validate_json(raw)
        except ValidationError:
            return None

    def _out(self, conn: sqlite3.Connection, r: sqlite3.Row, now: int) -> RecurringOut:
        schedule = self._read(r["schedule_json"])
        last = conn.execute(f"{self._RUN_SQL} WHERE r.recurring_id = ? ORDER BY r.id DESC LIMIT 1", (r["id"],)).fetchone()
        kinds = {x[0] for x in conn.execute("SELECT DISTINCT trigger FROM recurring_runs WHERE recurring_id = ?", (r["id"],))}
        enabled = bool(r["enabled"]) and schedule is not None         # a schedule that does not read will not fire: the tick pauses it, the list says so now
        return RecurringOut(
            id=r["id"], dept_id=r["dept_id"], dept_name=clip(r["dept_name"] or r["dept_id"], 80), text=r["text"], schedule=schedule,
            human=human(schedule) if schedule is not None else "Its schedule could not be read", enabled=enabled,
            paused_reason=r["paused_reason"] if schedule is not None else _UNREADABLE,
            next_due_at=iso_z(next_due(schedule, now, self.tz)) if enabled and schedule is not None else None, created_at=iso_z(r["created_at"]),
            last_run=self._run_out(last) if last is not None else None,
            never_fired_on_schedule=enabled and "manual" in kinds and not (kinds & {"schedule", "catch_up"}))

    _SELECT = ("SELECT c.*, o.name AS dept_name FROM recurring c LEFT JOIN org_nodes o ON o.id = c.dept_id")

    def listing(self) -> list[RecurringOut]:
        now = self.clock.now()
        with self.db.read() as conn:
            return [self._out(conn, r, now) for r in conn.execute(f"{self._SELECT} ORDER BY c.created_at, c.rowid")]

    def get(self, rec_id: str) -> RecurringOut:
        now = self.clock.now()
        with self.db.read() as conn:
            found = conn.execute(f"{self._SELECT} WHERE c.id = ?", (rec_id,)).fetchone()
            if found is None:
                raise NotFound("that schedule")
            return self._out(conn, found, now)

    def run_out(self, run_id: int) -> RunOut | None:
        """One run row as it reads now (None when it is gone): the route reads it again after `start_ready` has decided whether a limit holds it."""
        with self.db.read() as conn:
            found = conn.execute(f"{self._RUN_SQL} WHERE r.id = ?", (run_id,)).fetchone()
            return self._run_out(found) if found is not None else None

    def runs(self, rec_id: str, limit: int = 20) -> list[RunOut]:
        """The newest rows first, at most `limit` (1 to 200)."""
        with self.db.read() as conn:
            if conn.execute("SELECT 1 FROM recurring WHERE id = ?", (rec_id,)).fetchone() is None:
                raise NotFound("that schedule")
            return [self._run_out(r) for r in conn.execute(
                f"{self._RUN_SQL} WHERE r.recurring_id = ? ORDER BY r.id DESC LIMIT ?", (rec_id, max(1, min(int(limit), 200))))]

    # ---- the owner's changes --------------------------------------------------------------------------------------------------

    @staticmethod
    def _text(text: str) -> str:
        body = (text or "").strip()
        if not body:
            raise validation_error([violation("text", "empty", "write what the team should do each time")], "Write what the team should do each time")
        if len(body) > MAX_TEXT:
            raise validation_error([violation("text", "too_long", f"keep it under {MAX_TEXT} characters")], f"Keep it under {MAX_TEXT} characters")
        return body

    def create(self, dept_id: str, text: str, schedule: Schedule, *, now: int | None = None) -> RecurringOut:
        body = self._text(text)
        moment = int(now if now is not None else self.clock.now())
        with self.db.tx() as tx:
            if tx.conn.execute("SELECT 1 FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone() is None:
                raise NotFound("that team")
            if tx.conn.execute("SELECT count(*) FROM recurring").fetchone()[0] >= MAX_RECURRING:
                raise validation_error([violation("schedule", "too_many", f"{MAX_RECURRING} schedules is the most; remove one first")],
                                       f"{MAX_RECURRING} schedules is the most; remove one first")
            rec_id = self._new_id()
            tx.conn.execute(
                "INSERT INTO recurring(id, dept_id, text, schedule_json, enabled, paused_reason, cursor_at, streak_after, created_at, updated_at)"
                " VALUES (?,?,?,?,1,'',?,0,?,?)", (rec_id, dept_id, body, schedule.model_dump_json(), moment, moment, moment))
        return self.get(rec_id)

    def update(self, rec_id: str, *, text: str | None = None, schedule: Schedule | None = None, enabled: bool | None = None,
               now: int | None = None) -> RecurringOut:
        """Change the words, the cadence or the switch. A new cadence, or switching on again, starts from now: the time the schedule was
        away is not owed a run, and a fresh three-crash streak begins."""
        moment = int(now if now is not None else self.clock.now())
        with self.db.tx() as tx:
            found = tx.conn.execute("SELECT * FROM recurring WHERE id = ?", (rec_id,)).fetchone()
            if found is None:
                raise NotFound("that schedule")
            sets: dict[str, object] = {}
            if text is not None:
                sets["text"] = self._text(text)
            if schedule is not None and schedule.model_dump_json() != found["schedule_json"]:
                sets.update(schedule_json=schedule.model_dump_json(), cursor_at=moment)
            if enabled is not None and bool(found["enabled"]) != enabled:
                if enabled and schedule is None and self._read(found["schedule_json"]) is None:      # switching on would only be paused again, with another note
                    raise validation_error([violation("schedule", "unreadable", "set the schedule again")], "Its schedule could not be read. Set it again")
                sets.update(enabled=int(enabled), paused_reason="")
                if enabled:
                    top = tx.conn.execute("SELECT coalesce(max(id), 0) FROM recurring_runs WHERE recurring_id = ?", (rec_id,)).fetchone()[0]
                    sets.update(cursor_at=moment, streak_after=top)
            if sets:
                sets["updated_at"] = moment
                tx.conn.execute(f"UPDATE recurring SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), rec_id))
        return self.get(rec_id)

    def delete(self, rec_id: str) -> None:
        with self.db.tx() as tx:
            if tx.conn.execute("DELETE FROM recurring WHERE id = ?", (rec_id,)).rowcount == 0:
                raise NotFound("that schedule")

    # ---- starting a task ------------------------------------------------------------------------------------------------------

    @staticmethod
    def _busy(conn: sqlite3.Connection, dept_id: str) -> str:
        """Why the team cannot take a scheduled task now, in words; empty when it can."""
        marks = ",".join("?" * len(_OPEN))
        found = conn.execute(f"SELECT status FROM tasks WHERE dept_id = ? AND status IN ({marks})", (dept_id, *_OPEN)).fetchall()
        statuses = {r[0] for r in found}
        if "waiting_user" in statuses:
            return "the team is waiting for your answer"
        if statuses & {"starting", "running"}:
            return "the team is still working on its current task"
        if statuses:
            return "the team already has work waiting to start"
        return ""

    def _start(self, tx: object, rec: sqlite3.Row, schedule: Schedule, reason: str) -> str:
        """Make the task, in the transaction `tx`. The caller wrote the run row; this returns the new task's id."""
        words = f"Scheduled ({human(schedule)}): {clip(' '.join(rec['text'].split()), 200)}"
        if reason:
            words += f". {reason[:1].upper()}{reason[1:]}"
        title = clip(one_line_title(rec["text"], 60), 180) + " (scheduled)"
        made: TaskOut = self.tasks.create_scheduled(tx, dept_id=rec["dept_id"], text=rec["text"], title=title, note=clip(words, 900))
        return made.id

    def _team_active(self, conn: sqlite3.Connection, dept_id: str) -> bool:
        return conn.execute("SELECT 1 FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone() is not None

    def run_now(self, rec_id: str) -> RunOut:
        """Start the standing task by hand, now. A team that is busy refuses (409): a manual run is the owner's own click, so it is told,
        not skipped quietly. The row says `manual`; it never moves the schedule's cursor."""
        moment = self.clock.now()
        with self.db.tx() as tx:
            rec = tx.conn.execute("SELECT * FROM recurring WHERE id = ?", (rec_id,)).fetchone()
            if rec is None:
                raise NotFound("that schedule")
            if not self._team_active(tx.conn, rec["dept_id"]):
                raise NotFound("that team")
            schedule = self._read(rec["schedule_json"])
            if schedule is None:
                raise validation_error([violation("schedule", "unreadable", "set the schedule again")], "Its schedule could not be read. Set it again")
            busy = self._busy(tx.conn, rec["dept_id"])
            if busy:
                raise Busy(busy[0].upper() + busy[1:] + ". Try again when it is free")
            made = tx.conn.execute(
                "INSERT INTO recurring_runs(recurring_id, due_at, at, trigger, outcome, folded, reason) VALUES (?,?,?,'manual','started',0,'')"
                " ON CONFLICT(recurring_id, due_at) DO NOTHING", (rec_id, moment, moment))
            if made.rowcount == 0:
                raise Busy("It was started a moment ago")
            row_id = made.lastrowid
            task_id = self._start(tx, rec, schedule, "started by you, now")
            tx.conn.execute("UPDATE recurring_runs SET task_id = ? WHERE id = ?", (task_id, row_id))
            out = self._run_out(tx.conn.execute(f"{self._RUN_SQL} WHERE r.id = ?", (row_id,)).fetchone())
        return out

    # ---- the tick -------------------------------------------------------------------------------------------------------------

    def tick(self, now: int | None = None) -> TickReport:
        """Deal with every enabled schedule that has a due time since its cursor. One failing schedule is logged and left for the next tick;
        it never keeps the others from running. Synchronous: call it on a worker thread."""
        moment = int(now if now is not None else self.clock.now())
        report = TickReport()
        with self.db.read() as conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM recurring WHERE enabled = 1 ORDER BY created_at, rowid")]
        for rec_id in ids:
            try:
                self._tick_one(rec_id, moment, report)
            except Exception:                                       # noqa: BLE001
                log.exception("the schedule %s could not be checked", rec_id)
        return report

    def _streak(self, conn: sqlite3.Connection, rec: sqlite3.Row) -> int:
        """How many of the schedule's newest started runs (above its streak floor) ended `crashed`, up to CRASH_LIMIT."""
        count = 0
        for r in conn.execute(
                "SELECT t.status FROM recurring_runs r JOIN tasks t ON t.id = r.task_id WHERE r.recurring_id = ? AND r.outcome = 'started'"
                " AND r.id > ? ORDER BY r.id DESC LIMIT ?", (rec["id"], rec["streak_after"], CRASH_LIMIT)):
            if r[0] != "crashed":
                break
            count += 1
        return count

    def _tick_one(self, rec_id: str, now: int, report: TickReport) -> None:
        try:
            self._tick_in_tx(rec_id, now, report)
        except _CouldNotStart as failed:             # the whole transaction rolled back: say so in a row of its own, once, not at every tick
            with self.db.tx() as tx:
                if tx.conn.execute("SELECT 1 FROM recurring WHERE id = ?", (rec_id,)).fetchone() is not None:
                    self._row(tx.conn, rec_id, failed.due_at, now, failed.trigger, "skipped", failed.folded, f"could not start: {failed.message}")
                    tx.conn.execute("UPDATE recurring SET cursor_at = ?, updated_at = ? WHERE id = ?", (failed.due_at, now, rec_id))
            report.skipped.append(rec_id)

    def _tick_in_tx(self, rec_id: str, now: int, report: TickReport) -> None:
        with self.db.tx() as tx:
            conn = tx.conn
            rec = conn.execute("SELECT * FROM recurring WHERE id = ? AND enabled = 1", (rec_id,)).fetchone()
            if rec is None:
                return
            if self._streak(conn, rec) >= CRASH_LIMIT:
                self._pause(tx, rec, _PAUSED, now)
                report.paused.append(rec_id)
                return
            schedule = self._read(rec["schedule_json"])
            if schedule is None:
                self._pause(tx, rec, _UNREADABLE, now)
                report.paused.append(rec_id)
                return
            cursor = rec["cursor_at"]
            if cursor > now:                      # the clock ran ahead (a bad time sync) and was corrected: a cursor cannot be later than "now"
                cursor = now
                conn.execute("UPDATE recurring SET cursor_at = ?, updated_at = ? WHERE id = ?", (cursor, now, rec_id))
            latest, count = owed(schedule, cursor, now, self.tz)
            if latest is None:
                return
            if not self._team_active(conn, rec["dept_id"]):
                self._pause(tx, rec, "Paused: the team is no longer in the org chart.", now)
                report.paused.append(rec_id)
                return
            folded = max(0, count - 1)
            trigger = "catch_up" if folded or now - latest > LATE_S else "schedule"
            busy = self._busy(conn, rec["dept_id"])
            if busy:
                written = self._row(conn, rec_id, latest, now, trigger, "skipped", folded, busy)
                conn.execute("UPDATE recurring SET cursor_at = ?, updated_at = ? WHERE id = ?", (latest, now, rec_id))
                if written is not None:             # a due time dealt with already (after a corrected clock) is not a new skip
                    report.skipped.append(rec_id)
                return
            reason = ""
            if folded:
                reason = f"{folded} earlier due time{'' if folded == 1 else 's'} {'was' if folded == 1 else 'were'} missed while the app was away and folded into this one run"
            elif trigger == "catch_up":
                reason = "started late: the app was not running at the due time"
            made = self._row(conn, rec_id, latest, now, trigger, "started", folded, reason)
            if made is None:                                          # this due time was dealt with already: only the cursor was behind
                conn.execute("UPDATE recurring SET cursor_at = ?, updated_at = ? WHERE id = ?", (latest, now, rec_id))
                return
            try:
                task_id = self._start(tx, rec, schedule, reason)
            except AppError as exc:                                   # the team cannot take it
                raise _CouldNotStart(latest, trigger, folded, exc.message) from None
            conn.execute("UPDATE recurring_runs SET task_id = ? WHERE id = ?", (task_id, made))
            conn.execute("UPDATE recurring SET cursor_at = ?, updated_at = ? WHERE id = ?", (latest, now, rec_id))
            report.started.append((rec_id, task_id))

    def _row(self, conn: sqlite3.Connection, rec_id: str, due_at: int, now: int, trigger: str, outcome: str, folded: int, reason: str) -> int | None:
        """Write the run row; None when a row for this due time exists already (the unique key)."""
        made = conn.execute(
            "INSERT INTO recurring_runs(recurring_id, due_at, at, trigger, outcome, folded, reason) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(recurring_id, due_at) DO NOTHING", (rec_id, due_at, now, trigger, outcome, folded, clip(reason, 300)))
        return made.lastrowid if made.rowcount else None

    def _pause(self, tx: object, rec: sqlite3.Row, reason: str, now: int) -> None:
        tx.conn.execute("UPDATE recurring SET enabled = 0, paused_reason = ?, updated_at = ? WHERE id = ?", (reason, now, rec["id"]))
        schedule = self._read(rec["schedule_json"])
        what = human(schedule) if schedule is not None else "A scheduled task"
        try:
            self.tasks.post_note(tx, rec["dept_id"], f"{what}: {reason}")
        except AppError:
            pass                                                     # the team is gone or its chat is read-only: the list still says it

    # ---- the loop -------------------------------------------------------------------------------------------------------------

    async def tick_async(self, now: int | None = None) -> TickReport:
        """One tick, then the start of whatever it made. Also starts work that waits only because a limit has just lifted (a new month, a
        window that reset, a limit raised): a queued task is cheap to look for, and `start_ready` is the one place that decides."""
        report = await run_blocking(self.tick, now)
        if report.started or await run_blocking(self._anything_queued):
            await self.tasks.start_ready()
        return report

    def _anything_queued(self) -> bool:
        return self.db.conn().execute("SELECT 1 FROM tasks WHERE status = 'queued' LIMIT 1").fetchone() is not None

    async def start(self) -> TickReport:
        """The catch-up tick (the caller's `start_ready` starts what it made), then the loop."""
        report = await run_blocking(self.tick)
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.get_running_loop().create_task(self._loop(), name="sutra-recurring")
        return report

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_s)
            try:
                await self.tick_async()
            except asyncio.CancelledError:
                raise
            except Exception:                                       # noqa: BLE001  (a failing tick must not end the loop)
                log.exception("a scheduler tick failed")

    async def stop(self) -> None:
        task, self._loop_task = self._loop_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):             # noqa: BLE001
                pass
