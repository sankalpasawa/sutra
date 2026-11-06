"""The Heads up lane beside Needs you: what happened to the teams lately (gap package attention; docs/notes/GAP-attention.md).

    HeadsUp(db).items(now)      # HeadsUpOut[]: problems (newest first), then quiet teams, then finished work (newest first)

Three kinds of row, all derived at read time from the `tasks` table (nothing is stored, nothing is scheduled):

    problem    a task that crashed, or stopped without the owner asking, in the last 24 h, and that nothing newer has replaced: no
               retry of it (`parent_task_id`) and no later task of that team (a follow-up the owner wrote supersedes it). It offers
               Try again (the existing POST /api/tasks/{id}/retry) and it counts on the badge.
    quiet      a task starting or running whose last sign of life (`last_event_at`) is 10 minutes old or more. Computed, so it clears
               itself the moment the team writes again. Never counted.
    finished   a task done, or done with open items, in the last 24 h: a quiet FYI row. Done with open items offers Try again while
               nothing newer replaced it. Never counted.

The owner's own stop is never listed. The engine ends a stopped run with the same words whoever asked ('Stopped: stopped on request'),
so `TaskService` writes who asked into the reserved settings key `_stopped_by` ("owner" or "app", beside `_seed_from`) before it
starts the stop ladder; the owner's words of the server's own ending ('stopped by you', 'reset by you') are recognised too.
"""
import json
import sqlite3
from typing import Annotated, Literal

from pydantic import StringConstraints

from sutra_app.library.base import Value
from sutra_app.library.types import clip
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import Count, Iso, Name, NodeId, TaskId, TaskStatus
from sutra_app.orchestrator.waiting import age_words

__all__ = ["HeadsUp", "HeadsUpOut", "WINDOW_S", "QUIET_AFTER_S", "STOP_KEY", "OWNER_STOP_WORDS", "MAX_FINISHED"]

WINDOW_S = 24 * 3600               # a crash or a finish is news for this long after it ended
QUIET_AFTER_S = 600                # a working team with no event for this long "went quiet"
MAX_FINISHED = 50                  # FYI rows sent at most (the page shows three and "+N more")
STOP_KEY = "_stopped_by"           # who asked a live task to stop: "owner" or "app"
OWNER_STOP_WORDS = frozenset({"stopped by you", "reset by you"})
_ENDED = ("crashed", "stopped", "done", "done_with_open_items")
_WORKING = ("starting", "running")


class HeadsUpOut(Value):
    kind: Literal["problem", "quiet", "finished"]
    tone: Literal["err", "stop", "warn", "ok"]
    task_id: TaskId
    dept_id: NodeId
    dept_name: Name
    title: Name
    status: TaskStatus
    text: Annotated[str, StringConstraints(max_length=600)]            # the row's sentence, from a fixed template
    outcome: Annotated[str, StringConstraints(max_length=300)] = ""     # the task's own ending words, clipped
    at: Iso                                                             # when it ended (quiet: its last sign of life)
    since_s: Count
    retry: bool = False                                                 # Try again is offered


def _one_line(value: str | None, limit: int) -> str:
    return clip(" ".join((value or "").split()), limit)


def _stopped_by(settings_json: str | None) -> str:
    try:
        found = json.loads(settings_json or "{}").get(STOP_KEY, "")
    except (ValueError, AttributeError):
        return ""
    return found if isinstance(found, str) else ""


class HeadsUp:
    """Reads only; one call is one consistent read of `tasks` (a `db.read()` block)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def items(self, now: int) -> list[HeadsUpOut]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT t.rowid AS seq, t.id, t.dept_id, t.title, t.status, t.outcome, t.created_at, t.started_at, t.ended_at,"
                " t.last_event_at, t.settings_json, o.name FROM tasks t LEFT JOIN org_nodes o ON o.id = t.dept_id"
                f" WHERE (t.status IN ({','.join('?' * len(_ENDED))}) AND t.ended_at >= ?) OR t.status IN ({','.join('?' * len(_WORKING))})"
                " ORDER BY coalesce(t.ended_at, t.last_event_at, t.started_at, t.created_at) DESC, t.rowid DESC",
                (*_ENDED, int(now) - WINDOW_S, *_WORKING)).fetchall()
            problems, quiet, finished = [], [], []
            for r in rows:
                item = self._item(conn, r, int(now))
                if item is None:
                    continue
                {"problem": problems, "quiet": quiet, "finished": finished}[item.kind].append(item)
        return problems + quiet + finished[:MAX_FINISHED]

    @staticmethod
    def _replaced(conn: sqlite3.Connection, r: sqlite3.Row) -> bool:
        """A retry of the task, or any task of the same team made after it ended, replaces it."""
        return conn.execute(
            "SELECT 1 FROM tasks WHERE dept_id = ? AND id != ? AND (parent_task_id = ? OR (created_at >= ? AND rowid > ?)) LIMIT 1",
            (r["dept_id"], r["id"], r["id"], r["ended_at"], r["seq"])).fetchone() is not None

    def _item(self, conn: sqlite3.Connection, r: sqlite3.Row, now: int) -> HeadsUpOut | None:
        status = r["status"]
        team = _one_line(r["name"] or r["dept_id"], 200)
        title = _one_line(r["title"], 200)
        outcome = _one_line(r["outcome"], 300)
        base = dict(task_id=r["id"], dept_id=r["dept_id"], dept_name=team, title=title, status=status, outcome=outcome)
        if status in _WORKING:
            seen = r["last_event_at"] or r["started_at"] or r["created_at"]
            since = max(0, now - int(seen))
            if since < QUIET_AFTER_S:
                return None
            return HeadsUpOut(kind="quiet", tone="warn", text=f'{team} has gone quiet on "{title}": no sign of work for {age_words(since)}',
                              at=iso_z(seen), since_s=since, **base)
        since = max(0, now - int(r["ended_at"]))
        ended = dict(at=iso_z(r["ended_at"]), since_s=since)
        app_closed = outcome.lower().startswith("the app was closed")
        if status == "done":
            return HeadsUpOut(kind="finished", tone="ok", text=f'{team} finished "{title}"', **ended, **base)
        if status == "done_with_open_items":
            return HeadsUpOut(kind="finished", tone="warn", text=f'{team} finished "{title}" with some things left open',
                              retry=not self._replaced(conn, r), **ended, **base)
        if status == "stopped":
            by = _stopped_by(r["settings_json"])
            if by == "owner" or (by != "app" and outcome.lower().rstrip(".") in OWNER_STOP_WORDS):
                return None                                                   # the owner knows: they pressed Stop
            if self._replaced(conn, r):
                return None
            text = (f'{team} was working on "{title}" when the app closed' if by == "app" or app_closed
                    else f'{team} stopped before it finished "{title}"')
            return HeadsUpOut(kind="problem", tone="stop", text=text, retry=True, **ended, **base)
        if self._replaced(conn, r):                                            # crashed
            return None
        text = f'{team} was working on "{title}" when the app closed' if app_closed else f'{team} ran into a problem on "{title}"'
        return HeadsUpOut(kind="problem", tone="err", text=text, retry=True, **ended, **base)
