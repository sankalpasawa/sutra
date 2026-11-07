"""Tasks: the `tasks` table, the task step nodes and the TaskService (orchestrator 3.4, 5.5, 5.6; D14, D20-D23; S1-contracts-11..19).

    store = TaskStore(db, data_dir)                      # rows: find_row, row, get, listing, update (gated), run_dir_of, resolve_run
    taskgraph = TaskGraph(store, graph)                  # the task's step node (step_ref 'task') and its builder step nodes
    service = TaskService(db, store=..., graph=..., chats=..., taskgraph=..., projector=..., launcher=..., settings=...)

    service.create(tx, dept_id=..., text=..., title=...)             # one task row (queued, or blocked on depends_on)
    await service.start_ready()                                      # FIFO, one live task per department, SUTRA_MAX_RUNS / SUTRA_MAX_LIVE
    service.deliver_to_department(dept, text)                        # answer a waiting team, 409 a working one, else a follow-up task
    service.stop_live(dept)                                          # the engine's reset: stop a waiting team, cancel queued work
    await service.stop(task_id) / await service.retry(task_id)       # the stop ladder; a fresh run (never seeded) told how earlier attempts ended
    service.resolve_run(run_id, dept_id)                             # RunRef: run_id wins, else the live task's run, else the latest

The server makes the run folder (mode 0700) before the engine process exists: `task.json` (RunSpec, 0600, written by temp file and
rename), empty `inbox.jsonl` and `events.jsonl` (0600, O_EXCL). The engine never creates it.

A follow-up remembers which run to continue from in `settings_json` under the reserved key `_seed_from` (the table has no column
for it): the seven J2_* keys stay as they were and every reader of the settings drops the underscore keys. A retry stores its attempt
number the same way, under `_attempt` (`attempts.py`).
"""
import asyncio
import hmac
import json
import logging
import os
from sutra_app import oslayer
import shutil
import sqlite3
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import anyio.from_thread
from pydantic import ValidationError

from sutra_app.config import Settings
from sutra_app.connectors.egress import scan
from sutra_app.library.gate import GATE, Checked, GateError
from sutra_app.library.node import StructuralNode, step_node_id
from sutra_app.library.types import clip, violation, violations_from_validation_error
from sutra_app.orchestrator import attempts
from sutra_app.orchestrator.attempts import ATTEMPT_KEY
from sutra_app.orchestrator.records import WorkTask
from sutra_app.orchestrator.db import Database, Tx, run_blocking
from sutra_app.orchestrator.errors import AppError, Busy, NotFound, ReadOnly, from_gate_error, validation_error
from sutra_app.orchestrator.graph import GraphStore, _task_out
from sutra_app.orchestrator.ids import Clock, IdFactory, SystemClock, iso_z
from sutra_app.orchestrator.models import (
    LIVE_STATUSES, TERMINAL_STATUSES, Delivery, RunRef, RunSpec, TaskOut, TaskSettings, UpstreamRef,
)
from sutra_app.orchestrator.nodes import ensure_node, node_init
from sutra_app.orchestrator.pathwords import machine_roots, shorten
from sutra_app.orchestrator.runs import stderr_tail
from sutra_app.orchestrator.textutil import one_line_title
from sutra_app.orchestrator.headsup import STOP_KEY
from sutra_app.orchestrator.standing_rules import framing_for
from sutra_app.orchestrator.waiting import why_waiting

__all__ = [
    "TaskRow", "TaskStore", "TaskGraph", "TaskService", "NODE_STATE_OF_TASK", "OVERRIDE_BUSY_NOTE", "RUN_FOLDER_INTERNALS",
    "SEED_KEY", "task_detail",
]

log = logging.getLogger(__name__)
SEED_KEY = "_seed_from"
OPEN_STATUSES = ("blocked", "queued", "starting", "running", "waiting_user")
GOOD_END = ("done", "done_with_open_items")
BAD_END = ("stopped", "crashed", "cancelled")
OVERRIDE_BUSY_NOTE = "Owner override needs a team that is waiting for you."
RUN_FOLDER_INTERNALS = frozenset({
    "task.json", "inbox.jsonl", "events.jsonl", "trace.jsonl", "snapshot.json", "live.json", "settings.json", "run.stdout.log",
    "run.stderr.log",
})
NODE_STATE_OF_TASK = {
    "blocked": "not_made", "queued": "not_made", "cancelled": "not_made", "starting": "running", "running": "running",
    "waiting_user": "waiting_on_you", "done": "filed", "done_with_open_items": "left_open", "stopped": "left_open", "crashed": "fault",
}
_COLUMNS = ("id, dept_id, scope_node_id, title, user_text, framing, status, run_id, parent_task_id, depends_on, request_id,"
            " origin_message_id, change_id, settings_json, pid, events_offset, inbox_seq, outcome, created_at, started_at, ended_at,"
            " last_event_at")
_UPDATABLE = frozenset({
    "title", "framing", "status", "run_id", "pid", "events_offset", "inbox_seq", "outcome", "started_at", "ended_at", "last_event_at",
    "settings_json",
})


def _marks(count: int) -> str:
    return ",".join("?" * count)


@dataclass(frozen=True)
class TaskRow:
    """One `tasks` row. `settings` holds the seven J2_* keys only; `seed_from` is the reserved key of a follow-up."""

    id: str
    dept_id: str
    scope_node_id: str | None
    title: str
    user_text: str
    framing: str
    status: str
    run_id: str | None
    parent_task_id: str | None
    depends_on: tuple[str, ...]
    request_id: str | None
    origin_message_id: int | None
    change_id: str | None
    settings: dict[str, str]
    seed_from: str | None
    pid: int | None
    events_offset: int
    inbox_seq: int
    outcome: str
    created_at: int
    started_at: int | None
    ended_at: int | None
    last_event_at: int | None

    @property
    def live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


def _row_of(r: sqlite3.Row) -> TaskRow:
    stored = json.loads(r["settings_json"] or "{}")
    return TaskRow(
        id=r["id"], dept_id=r["dept_id"], scope_node_id=r["scope_node_id"], title=r["title"], user_text=r["user_text"], framing=r["framing"],
        status=r["status"], run_id=r["run_id"], parent_task_id=r["parent_task_id"], depends_on=tuple(json.loads(r["depends_on"] or "[]")),
        request_id=r["request_id"], origin_message_id=r["origin_message_id"], change_id=r["change_id"],
        settings={k: v for k, v in stored.items() if not k.startswith("_")}, seed_from=stored.get(SEED_KEY), pid=r["pid"],
        events_offset=r["events_offset"], inbox_seq=r["inbox_seq"], outcome=r["outcome"], created_at=r["created_at"], started_at=r["started_at"],
        ended_at=r["ended_at"], last_event_at=r["last_event_at"])


def _payload(row: TaskRow) -> dict[str, Any]:
    """The `work_task` record of a row, for the gate."""
    return dict(
        kind="work_task", id=row.id, dept_id=row.dept_id, scope_node_id=row.scope_node_id, title=row.title, user_text=row.user_text,
        framing=row.framing, status=row.status, run_id=row.run_id, parent_task_id=row.parent_task_id, depends_on=list(row.depends_on),
        request_id=row.request_id, origin_message_id=row.origin_message_id, change_id=row.change_id, settings=row.settings, pid=row.pid,
        events_offset=row.events_offset, inbox_seq=row.inbox_seq, outcome=row.outcome, created_at=row.created_at, started_at=row.started_at,
        ended_at=row.ended_at, last_event_at=row.last_event_at)


def _settings_json(settings: dict[str, str], seed_from: str | None, attempt: int | None = None) -> str:
    stored: dict[str, Any] = dict(settings)
    if seed_from:
        stored[SEED_KEY] = seed_from
    if attempt is not None and attempt >= 2:
        stored[ATTEMPT_KEY] = attempt
    return json.dumps(stored, sort_keys=True, separators=(",", ":"))


def task_detail(row: TaskRow, *, waiting: str = "") -> str:
    """The one-line detail of a task's step node."""
    if row.status in ("blocked", "queued"):
        return waiting or ("waiting for another task" if row.status == "blocked" else "waiting to start")
    if row.terminal:
        return clip(row.outcome, 300)
    return ""


# ---- the store ----------------------------------------------------------------------------------------------------------

class TaskStore:
    """The `tasks` table: reads, and one gated writer (`update`). Synchronous; async code uses `run_blocking`."""

    def __init__(self, db: Database, data_dir: str | os.PathLike[str]) -> None:
        self.db = db
        self.data_dir = Path(data_dir)

    # ---- reads -----------------------------------------------------------------------------------------------------------

    def row_in(self, conn: sqlite3.Connection, task_id: str) -> TaskRow | None:
        found = conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_of(found) if found is not None else None

    def find_row(self, task_id: str) -> TaskRow | None:
        return self.row_in(self.db.conn(), task_id)

    def row(self, task_id: str) -> TaskRow:
        found = self.find_row(task_id)
        if found is None:
            raise NotFound("that task")
        return found

    def out_in(self, conn: sqlite3.Connection, task_id: str) -> TaskOut:
        found = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if found is None:
            raise NotFound("that task")
        return _task_out(conn, found)

    def get(self, task_id: str) -> TaskOut:
        return self.out_in(self.db.conn(), task_id)

    def listing(self, *, dept_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0) -> list[TaskOut]:
        """Newest first."""
        where, args = [], []
        for column, value in (("dept_id", dept_id), ("status", status)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        sql = ("SELECT * FROM tasks" + (f" WHERE {' AND '.join(where)}" if where else "")
               + " ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?")
        with self.db.read() as conn:
            return [_task_out(conn, r) for r in conn.execute(sql, (*args, max(1, min(int(limit), 500)), max(0, int(offset)))).fetchall()]

    def unfinished_ids(self) -> list[str]:
        """Tasks that have (or may have) a process: starting, running, waiting_user."""
        return [r[0] for r in self.db.conn().execute(
            f"SELECT id FROM tasks WHERE status IN ({_marks(len(LIVE_STATUSES))}) ORDER BY created_at, rowid", LIVE_STATUSES)]

    def live_in(self, conn: sqlite3.Connection, dept_id: str) -> TaskRow | None:
        found = conn.execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE dept_id = ? AND status IN ({_marks(len(LIVE_STATUSES))}) LIMIT 1", (dept_id, *LIVE_STATUSES)).fetchone()
        return _row_of(found) if found is not None else None

    def latest_in(self, conn: sqlite3.Connection, dept_id: str) -> TaskRow | None:
        found = conn.execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE dept_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1", (dept_id,)).fetchone()
        return _row_of(found) if found is not None else None

    def counts_in(self, conn: sqlite3.Connection) -> tuple[int, int]:
        """(tasks starting or running, tasks starting, running or waiting for the owner)."""
        working = conn.execute("SELECT count(*) FROM tasks WHERE status IN ('starting','running')").fetchone()[0]
        live = conn.execute("SELECT count(*) FROM tasks WHERE status IN ('starting','running','waiting_user')").fetchone()[0]
        return int(working), int(live)

    def home_dir_in(self, conn: sqlite3.Connection, dept_id: str) -> str:
        found = conn.execute("SELECT home_dir FROM departments WHERE id = ?", (dept_id,)).fetchone()
        if found is None:
            raise NotFound("that team")
        return found["home_dir"]

    def run_dir_of(self, row: TaskRow) -> Path:
        """`<data dir>/departments/<dept>/runs/<run id>` (the task must have a run)."""
        if row.run_id is None:
            raise ValueError(f"task {row.id} has no run folder yet")
        return self.data_dir / self.home_dir_in(self.db.conn(), row.dept_id) / "runs" / row.run_id

    def runs_dir_in(self, conn: sqlite3.Connection, dept_id: str) -> Path:
        return self.data_dir / self.home_dir_in(conn, dept_id) / "runs"

    def stderr_tail(self, row: TaskRow) -> str:
        return stderr_tail(self.run_dir_of(row))

    def run_ref(self, run_id: str) -> RunRef | None:
        conn = self.db.conn()
        found = conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE run_id = ?", (run_id,)).fetchone()
        return self._ref(conn, _row_of(found)) if found is not None else None

    def _ref(self, conn: sqlite3.Connection, row: TaskRow) -> RunRef:
        home = self.home_dir_in(conn, row.dept_id)
        return RunRef(
            run_id=row.run_id, task_id=row.id, dept_id=row.dept_id, dir=f"{home}/runs/{row.run_id}", status=row.status, pid=row.pid or None,
            started_at=iso_z(row.started_at) if row.started_at is not None else None,
            ended_at=iso_z(row.ended_at) if row.ended_at is not None else None)

    def resolve_run(self, run_id: str | None, dept_id: str) -> RunRef | None:
        """`run_id` wins (it must be a run of `dept_id`); else the department's live task's run; else its latest run."""
        conn = self.db.conn()
        if run_id:
            found = conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE run_id = ? AND dept_id = ?", (run_id, dept_id)).fetchone()
        else:
            found = conn.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE dept_id = ? AND run_id IS NOT NULL ORDER BY"
                f" (status IN ({_marks(len(LIVE_STATUSES))})) DESC, created_at DESC, rowid DESC LIMIT 1", (dept_id, *LIVE_STATUSES)).fetchone()
        return self._ref(conn, _row_of(found)) if found is not None else None

    # ---- writes ----------------------------------------------------------------------------------------------------------

    def insert(self, tx: Tx, checked: Checked[WorkTask], *, seed_from: str | None = None, attempt: int | None = None) -> TaskRow:
        """Insert a new row from a Checked `work_task` (the only way in). `seed_from` is the run a follow-up continues from; `attempt`
        the number of a retry (2, 3, ...; `attempts.ATTEMPT_KEY`)."""
        if not isinstance(checked, Checked) or checked.family != "work_task":
            raise TypeError("TaskStore.insert takes a Checked work_task from GATE.check")
        t: WorkTask = checked.model
        settings = t.settings.model_dump()
        tx.conn.execute(
            f"INSERT INTO tasks({_COLUMNS}) VALUES ({_marks(22)})",
            (t.id, t.dept_id, t.scope_node_id, t.title, t.user_text, t.framing, t.status, t.run_id, t.parent_task_id, json.dumps(list(t.depends_on)),
             t.request_id, t.origin_message_id, t.change_id, _settings_json(settings, seed_from, attempt), t.pid, t.events_offset, t.inbox_seq, t.outcome,
             t.created_at, t.started_at, t.ended_at, t.last_event_at))
        return self.row_in(tx.conn, t.id)

    def update(self, tx: Tx, task_id: str, **changes: Any) -> TaskRow:
        """Change columns of one row; the result must still be a valid `work_task` (a GateError is a bug of the caller)."""
        bad = set(changes) - _UPDATABLE
        if bad:
            raise ValueError(f"tasks columns that may change: {', '.join(sorted(_UPDATABLE))}; not {', '.join(sorted(bad))}")
        old = self.row_in(tx.conn, task_id)
        if old is None:
            raise NotFound("that task")
        new = replace(old, **{k: v for k, v in changes.items() if k != "settings_json"})
        GATE.check("work_task", _payload(new), ctx=tx.ctx)
        sets = ", ".join(f"{column} = ?" for column in changes)
        tx.conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", (*changes.values(), task_id))
        return new

    def touch(self, tx: Tx, task_id: str, *, events_offset: int, last_event_at: int | None = None) -> None:
        """The watcher's per-batch write: the new offset and the time of the newest line (no gate: two integers)."""
        if last_event_at is None:
            tx.conn.execute("UPDATE tasks SET events_offset = ? WHERE id = ?", (events_offset, task_id))
        else:
            tx.conn.execute("UPDATE tasks SET events_offset = ?, last_event_at = ? WHERE id = ?", (events_offset, last_event_at, task_id))

    def settle_blocked(self, tx: Tx, changed: Callable[[TaskRow], None]) -> list[str]:
        """A blocked task becomes queued when all its dependencies are done (or done with open items), and cancelled when one of
        them ended otherwise or is gone. Repeats until nothing changes (a cancelled task cancels its dependants). `changed` is
        called with each new row."""
        moved: list[str] = []
        while True:
            progress = False
            for r in tx.conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE status = 'blocked' ORDER BY created_at, rowid").fetchall():
                row = _row_of(r)
                deps = [self.row_in(tx.conn, d) for d in row.depends_on]
                bad = next((d for d in deps if d is None or d.status in BAD_END), None)
                if bad is not None:
                    why = f"waiting task {bad.title if bad is not None else 'that was removed'} did not finish"
                    new = self.update(tx, row.id, status="cancelled", ended_at=tx.now(), outcome=clip(why, 2000))
                elif all(d is not None and d.status in GOOD_END for d in deps):
                    new = self.update(tx, row.id, status="queued")
                else:
                    continue
                changed(new)
                moved.append(row.id)
                progress = True
            if not progress:
                return moved


# ---- the task's nodes in the graph -------------------------------------------------------------------------------------------

class TaskGraph:
    """The graph side of a task: its step node (`step_ref` 'task', parent: the department or the scoped division) and the builder
    step nodes (`W-<n>`, `team:<role>`) that engine events create. Also the one place that announces `task.updated`."""

    def __init__(self, store: TaskStore, graph: GraphStore, *, ids: IdFactory | None = None) -> None:
        self.store = store
        self.graph = graph
        self._ids = ids or IdFactory()

    def _session_id(self) -> str:
        return self._ids.session_id()

    def sync(self, tx: Tx, row: TaskRow, *, waiting: str = "", announce: bool = True) -> None:
        """Make the task's step node agree with the row (state from the status, detail) and announce `task.updated`."""
        self.ensure_step(tx, row, "task", label=row.title, state=NODE_STATE_OF_TASK[row.status], detail=task_detail(row, waiting=waiting),
                    parent_id=row.scope_node_id or row.dept_id)
        if announce:
            tx.emit("task.updated", {"task": self.store.out_in(tx.conn, row.id).model_dump(mode="json")})

    def node_id(self, row: TaskRow, ref: str) -> str:
        return step_node_id(row.id, ref)

    def ensure_step(self, tx: Tx, row: TaskRow, ref: str, *, label: str | None = None, state: str | None = None, detail: str | None = None,
               parent_id: str | None = None) -> str:
        """Create or update the step node `ref` of a task and return its id. A new node needs a label (default: the ref)."""
        node_id = step_node_id(row.id, ref)
        existing = tx.ctx.get("node", node_id)
        now = tx.now()
        if existing is None:
            parent = parent_id or step_node_id(row.id, "task")
            if ref != "task" and tx.ctx.get("node", parent) is None:
                parent = step_node_id(row.id, "task")
            node = StructuralNode(
                kind="step", id=node_id, label=clip(label or ref, 80), department_id=row.dept_id, state=state or "idle",
                detail=clip(detail or "", 300), parent_id=parent, task_id=row.id, step_ref=ref, ts_created=now, ts_updated=now)
            ensure_node(tx, node_init(node, title=clip(label or ref, 80)), graph=self.graph, new_session_id=self._session_id)
            return node_id
        changes: dict[str, Any] = {}
        if label is not None and clip(label, 80) != existing.label:
            changes["label"] = clip(label, 80)
        if state is not None and state != existing.state:
            changes["state"] = state
        if detail is not None and clip(detail, 300) != existing.detail:
            changes["detail"] = clip(detail, 300)
        if parent_id is not None and parent_id != existing.parent_id and tx.ctx.get("node", parent_id) is not None:
            changes["parent_id"] = parent_id
        if changes:
            changes["ts_updated"] = max(existing.ts_updated, now)
            self.graph.put_node(tx, GATE.check("node", existing.evolve(**changes), ctx=tx.ctx))
        return node_id


# ---- the service ---------------------------------------------------------------------------------------------------------------

class TaskService:
    """Creating, starting, delivering to, stopping and retrying tasks. Synchronous methods take or open a transaction;
    `start_ready`, `start`, `stop`, `retry` and `shutdown` are coroutines (they talk to the launcher)."""

    def __init__(self, db: Database, *, store: TaskStore, graph: GraphStore, chats: Any, taskgraph: TaskGraph, projector: Any,
                 launcher: Any, settings: Settings, watcher: Any = None, clock: Clock | None = None, ids: IdFactory | None = None,
                 redact: Callable[[str], str] | None = None) -> None:
        self.db = db
        self.store = store
        self.graph = graph
        self.chats = chats
        self.taskgraph = taskgraph
        self.projector = projector
        self.launcher = launcher
        self.settings = settings
        self.watcher = watcher
        self.clock = clock or SystemClock()
        self.ids = ids or IdFactory(self.clock)
        self.redact = redact or (lambda text: text)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None
        # limits.py (gap routines-limits): called as gate(conn, now, dept_id) for a queued task that may otherwise start; a non-empty answer
        # is the words it keeps waiting with. Only starts are gated: a run in flight is never touched.
        self.start_gate: Callable[[sqlite3.Connection, int, str], str] | None = None

    # ---- loop plumbing -----------------------------------------------------------------------------------------------------

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """The server loop: synchronous callers (the engine's routes run in worker threads) schedule `start_ready` on it."""
        self._loop = loop

    def kick(self) -> None:
        """Schedule `start_ready()` on the server loop without waiting (a no-op when no loop is bound or it is not running)."""
        loop = self._loop
        if loop is None or loop.is_closed() or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.start_ready(), loop)

    def _run_async(self, factory: Callable[[], Awaitable[Any]]) -> Any:
        """Drive a coroutine from synchronous code: from an AnyIO worker thread (the engine's routes), from another thread with
        the bound loop, or (tests, no loop) on a loop of its own."""
        try:
            return anyio.from_thread.run(factory)
        except RuntimeError:
            pass
        loop = self._loop
        if loop is not None and loop.is_running():
            return asyncio.run_coroutine_threadsafe(factory(), loop).result()
        return asyncio.run(factory())

    # ---- create ------------------------------------------------------------------------------------------------------------

    def create(self, tx: Tx, *, dept_id: str, text: str, title: str | None = None, scope_id: str | None = None, framing: str = "",
               depends_on: Sequence[str] = (), follows: str | None = None, request: str | None = None, change_id: str | None = None,
               settings: dict[str, Any] | None = None) -> TaskOut:
        """One task row. Status: `queued`, or `blocked` while a dependency has not finished, or `cancelled` when one ended badly.
        `settings`: the seven allowed keys with valid values, else 422 `validation`. `follows`: a task of the same department
        that has a run; sets the parent and the run to continue from. `request`: the owner's request id (`req-<n>`)."""
        row = self._insert(tx, dept_id=dept_id, text=text, title=title, scope_id=scope_id, framing=framing, depends_on=depends_on,
                           follows=follows, request=request, change_id=change_id, settings=settings, seed_run=None, parent_task_id=None)
        return self.store.out_in(tx.conn, row.id)

    def create_scheduled(self, tx: Tx, *, dept_id: str, text: str, title: str, note: str) -> TaskOut:
        """The task a recurring schedule makes (recurring.py): an ordinary queued task, plus one system note in the team's chat that says it
        was scheduled, so the owner who opens the team sees why it started. Raises like `create`."""
        created = self.create(tx, dept_id=dept_id, text=text, title=title)
        self.post_note(tx, dept_id, note, task_id=created.id)
        return created

    def post_note(self, tx: Tx, dept_id: str, text: str, *, task_id: str | None = None) -> None:
        """One system note in a team's chat (the owner did not write it; Sutra did)."""
        self._post(tx, self._dept_session(tx.conn, dept_id), role="system", who="sutra", kind="note", text=text, task_id=task_id)

    def _insert(self, tx: Tx, *, dept_id: str, text: str, title: str | None, scope_id: str | None, framing: str, depends_on: Sequence[str],
                follows: str | None, request: str | None, change_id: str | None, settings: dict[str, Any] | None, seed_run: str | None,
                parent_task_id: str | None, status_override: str | None = None, attempt: int | None = None) -> TaskRow:
        conn = tx.conn
        problems = []
        body = (text or "").strip()
        if not body:
            problems.append(violation("text", "empty", "a task needs the owner's words"))
        if conn.execute("SELECT 1 FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone() is None:
            raise NotFound("that team")
        clean = self._clean_settings(settings)
        if scope_id is not None and not self._under(conn, scope_id, dept_id):
            problems.append(violation("scope_id", "bad_scope", f"{scope_id} is not a division of the team {dept_id}"))
        deps: list[TaskRow] = []
        for dep_id in dict.fromkeys(depends_on):
            dep = self.store.row_in(conn, dep_id)
            if dep is None:
                problems.append(violation("depends_on", "unknown_task", f"{dep_id} is not a task"))
            else:
                deps.append(dep)
        if follows is not None:
            followed = self.store.row_in(conn, follows)
            if followed is None or followed.dept_id != dept_id:
                problems.append(violation("follows", "bad_follows", f"{follows} is not a task of the team {dept_id}"))
            elif followed.run_id is None:
                problems.append(violation("follows", "no_run", f"{follows} has no run to continue from"))
            else:
                parent_task_id, seed_run = followed.id, followed.run_id
        if problems:
            raise validation_error(problems)
        now = tx.now()
        if status_override:
            status = status_override
        elif any(d.status in BAD_END for d in deps):
            status = "cancelled"
        elif all(d.status in GOOD_END for d in deps):
            status = "queued"
        else:
            status = "blocked"
        outcome = ""
        if status == "cancelled":
            bad = next(d for d in deps if d.status in BAD_END)
            outcome = clip(f"waiting task {bad.title} did not finish", 2000)
        origin = None
        if request is not None:
            if not request.startswith("req-") or not request[4:].isdigit():
                raise validation_error([violation("request", "bad_request", "a request id is req-<number>")])
            origin = int(request[4:])
        task_title = clip((title or one_line_title(body)).strip() or one_line_title(body), 200)
        row = TaskRow(
            id=self.ids.task_id(), dept_id=dept_id, scope_node_id=scope_id, title=task_title, user_text=body, framing=framing or "",
            status=status, run_id=None, parent_task_id=parent_task_id, depends_on=tuple(d.id for d in deps), request_id=request,
            origin_message_id=origin, change_id=change_id, settings=clean, seed_from=seed_run, pid=None, events_offset=0, inbox_seq=0,
            outcome=outcome, created_at=now, started_at=None, ended_at=now if status == "cancelled" else None, last_event_at=None)
        try:
            row = self.store.insert(tx, GATE.check("work_task", _payload(row), ctx=tx.ctx), seed_from=seed_run, attempt=attempt)
        except GateError as exc:
            raise from_gate_error(exc) from None
        self.taskgraph.sync(tx, row)
        return row

    @staticmethod
    def _clean_settings(settings: dict[str, Any] | None) -> dict[str, str]:
        try:
            return TaskSettings.model_validate(settings or {}).model_dump()
        except ValidationError as exc:
            raise validation_error(violations_from_validation_error(exc), "Those task settings are not allowed") from None

    @staticmethod
    def _under(conn: sqlite3.Connection, node_id: str, dept_id: str) -> bool:
        """Is `node_id` a division somewhere under the department `dept_id` in the live chart?"""
        found = conn.execute("SELECT kind, state FROM org_nodes WHERE id = ?", (node_id,)).fetchone()
        if found is None or found["kind"] != "division" or found["state"] != "active":
            return False
        current, seen = node_id, set()
        while current not in seen:
            seen.add(current)
            parent = conn.execute("SELECT parent_id FROM org_edges WHERE child_id = ?", (current,)).fetchone()
            if parent is None:
                return False
            if parent["parent_id"] == dept_id:
                return True
            current = parent["parent_id"]
        return False

    # ---- starting ----------------------------------------------------------------------------------------------------------

    def _gate(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def start_ready(self) -> list[str]:
        """FIFO: blocked tasks move to queued (or cancelled) when their dependencies have finished; queued tasks start while
        count(starting, running) < SUTRA_MAX_RUNS and count(starting, running, waiting_user) < SUTRA_MAX_LIVE, one live task per
        department. Returns the ids started."""
        started: list[str] = []
        async with self._gate():
            while True:
                prepared = await run_blocking(self._prepare_next)
                if prepared is None:
                    return started
                task_id, spec, run_dir = prepared
                await self._launch(task_id, spec, run_dir)
                started.append(task_id)

    async def start(self, task_id: str) -> bool:
        """Start one queued task now (the caps still apply: False when it has to wait)."""
        async with self._gate():
            prepared = await run_blocking(self._prepare_next, task_id)
            if prepared is None:
                return False
            await self._launch(*prepared)
            return True

    def _prepare_next(self, only: str | None = None) -> tuple[str, RunSpec, Path] | None:
        """In one transaction: settle blocked tasks, pick the first queued task that may start, make its run folder and mark it
        `starting`. None when nothing may start (the others get their waiting detail)."""
        with self.db.tx() as tx:
            self.store.settle_blocked(tx, lambda row: self.taskgraph.sync(tx, row))
            working, live = self.store.counts_in(tx.conn)
            busy = {r[0]: r[1] for r in tx.conn.execute(f"SELECT dept_id, status FROM tasks WHERE status IN ({_marks(len(LIVE_STATUSES))})", LIVE_STATUSES)}
            queued = [_row_of(r) for r in tx.conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE status = 'queued' ORDER BY created_at, rowid")]
            for row in queued:
                if only is not None and row.id != only:
                    continue
                waiting = why_waiting(busy_status=busy.get(row.dept_id), working=working, live=live,              # names the owner when it is the owner
                                      max_runs=self.settings.max_runs, max_live=self.settings.max_live)
                if not waiting and self.start_gate is not None:                                                  # the spending limit, the plan window
                    waiting = self.start_gate(tx.conn, tx.now(), row.dept_id)
                if waiting:
                    self.taskgraph.sync(tx, row, waiting=waiting, announce=False)
                    continue
                spec, run_dir = self._begin(tx, row)
                return row.id, spec, run_dir
            return None

    def _begin(self, tx: Tx, row: TaskRow) -> tuple[RunSpec, Path]:
        """Allocate the run id, make the folder and its three files, and mark the task `starting`."""
        conn = tx.conn
        runs_dir = self.store.runs_dir_in(conn, row.dept_id)
        os.makedirs(runs_dir, mode=0o700, exist_ok=True)
        run_dir: Path | None = None
        run_id = ""
        for _ in range(20):
            run_id = self.ids.run_id()
            if conn.execute("SELECT 1 FROM tasks WHERE run_id = ?", (run_id,)).fetchone() is not None:
                continue
            try:
                os.mkdir(runs_dir / run_id, 0o700)
            except FileExistsError:
                continue
            run_dir = runs_dir / run_id
            break
        if run_dir is None:
            raise AppError("internal", "could not allocate a run id")
        try:
            spec = self._run_spec(conn, row, run_id)
            _write_atomic(run_dir / "task.json", spec.model_dump_json(indent=2) + "\n")
            for name in ("inbox.jsonl", "events.jsonl"):
                os.close(os.open(run_dir / name, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600))
            now = tx.now()
            started = self.store.update(tx, row.id, status="starting", run_id=run_id, started_at=now, last_event_at=now)
            self.taskgraph.sync(tx, started)
            self.graph.aggregate(tx)
        except BaseException:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
        return spec, run_dir

    def _run_spec(self, conn: sqlite3.Connection, row: TaskRow, run_id: str) -> RunSpec:
        dept = conn.execute("SELECT name FROM org_nodes WHERE id = ?", (row.dept_id,)).fetchone()
        scope = conn.execute("SELECT name FROM org_nodes WHERE id = ?", (row.scope_node_id,)).fetchone() if row.scope_node_id else None
        parent = self.store.row_in(conn, row.parent_task_id) if row.parent_task_id else None
        upstream: list[UpstreamRef] = []
        for dep_id in row.depends_on[:10]:
            dep = self.store.row_in(conn, dep_id)
            if dep is not None and dep.status in GOOD_END and dep.run_id:
                upstream.append(UpstreamRef(dept_id=dep.dept_id, run_id=dep.run_id, title=clip(dep.title, 200),
                                            files=self._files_of(conn, dep)))
        connector = "stub" if self.settings.offline else self.settings.connector
        if connector != "stub":                                      # a team's run follows its team chat's provider choice (ABS-8)
            chosen = conn.execute("SELECT s.pinned FROM graph_nodes g JOIN chat_sessions s ON s.id = g.chat_session_id WHERE g.id = ?",
                                  (row.dept_id,)).fetchone()
            if chosen is not None and chosen["pinned"] in ("claude", "codex"):
                connector = chosen["pinned"]
        return RunSpec(
            run_id=run_id, task_id=row.id, dept_id=row.dept_id, dept_label=clip(dept["name"] if dept else row.dept_id, 200),
            scope_id=row.scope_node_id, scope_label=clip(scope["name"], 200) if scope is not None else None, user_text=row.user_text,
            framing=framing_for(conn, row.dept_id, row.framing),                  # the team's standing rules in front, read now (GAP2 rules-notes)
            parent_run_id=parent.run_id if parent is not None else None, seed_from=row.seed_from, upstream=upstream,
            settings=TaskSettings.model_validate(row.settings), connector=connector)

    def _files_of(self, conn: sqlite3.Connection, dep: TaskRow) -> list[str]:
        """The files an upstream run left at the top of its folder (the engine's own plumbing is left out), up to 200."""
        folder = self.store.runs_dir_in(conn, dep.dept_id) / dep.run_id
        try:
            names = sorted(p.name for p in folder.iterdir() if p.is_file() and not p.is_symlink() and p.name not in RUN_FOLDER_INTERNALS)
        except OSError:
            return []
        return names[:200]

    async def _launch(self, task_id: str, spec: RunSpec, run_dir: Path) -> None:
        try:
            pid = await self.launcher.start(spec, run_dir)
        except Exception as exc:                          # noqa: BLE001  (a spawn failure ends this task only)
            log.warning("could not start task %s: %s", task_id, exc)
            said = shorten(self.redact(str(exc)), machine_roots([self.settings.data_dir]))         # the owner reads file names, the log above keeps the paths
            await run_blocking(self.projector.mark_ended, task_id, "crashed", f"could not start: {said}", "start_failed")
            return
        alive = await run_blocking(self._store_pid, task_id, pid)
        if alive and self.watcher is not None:
            self.watcher.watch(task_id)

    def _store_pid(self, task_id: str, pid: int) -> bool:
        with self.db.tx() as tx:
            row = self.store.row_in(tx.conn, task_id)
            if row is None or row.status != "starting":
                return row is not None and row.live
            self.store.update(tx, task_id, pid=pid if pid and pid > 0 else None)
            return True

    # ---- the owner writes to a department -------------------------------------------------------------------------------------

    def deliver(self, session_id: str, text: str) -> Delivery:
        """The owner's line in a department or division chat. Function, step, org and archived chats are read-only (403)."""
        found = self.db.conn().execute("SELECT kind, node_id, status FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if found is None:
            raise NotFound("that chat")
        if found["status"] != "active" or found["kind"] not in ("department", "division"):
            raise ReadOnly()
        if found["kind"] == "department":
            return self.deliver_to_department(found["node_id"], text)
        dept = self.db.conn().execute("SELECT department_id FROM graph_nodes WHERE id = ?", (found["node_id"],)).fetchone()
        if dept is None or dept["department_id"] is None:
            raise NotFound("that team")
        return self.deliver_to_department(dept["department_id"], text, scope_id=found["node_id"])

    def deliver_to_department(self, dept_id: str, text: str, *, scope_id: str | None = None, settings: dict | None = None) -> Delivery:
        """What the engine's `POST /api/say` calls. Strips the text. A team waiting for the owner gets it as an answer (or as an
        override when it starts with the override key); a working team is 409 `busy`; with no live task a follow-up is created
        and scheduled. Raises `Busy`."""
        body = (text or "").strip()
        if not body:
            raise validation_error([violation("text", "empty", "write something first")])
        refusal: AppError | None = None
        with self.db.tx() as tx:
            if tx.conn.execute("SELECT 1 FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone() is None:
                raise NotFound("that team")
            sid = self._dept_session(tx.conn, dept_id)
            live = self.store.live_in(tx.conn, dept_id)
            override = self._override_command(body)
            if override is not None:
                if live is None or live.status != "waiting_user":
                    self._post(tx, sid, role="system", who="sutra", kind="note", text=OVERRIDE_BUSY_NOTE, task_id=live.id if live else None)
                    refusal = Busy(OVERRIDE_BUSY_NOTE)
                elif not override:
                    raise validation_error([violation("text", "empty_override", "an override needs a command after the key")])
                else:
                    result = self._answer(tx, live, sid, "Owner override sent", {"kind": "override", "cmd": override}, answered=False)
            elif live is not None and live.status == "waiting_user":
                result = self._answer(tx, live, sid, body, {"kind": "user", "text": body}, answered=True)
            elif live is not None:
                raise Busy()
            elif tx.conn.execute("SELECT 1 FROM tasks WHERE dept_id = ? AND status IN ('blocked','queued') LIMIT 1", (dept_id,)).fetchone():
                raise Busy("The team has work waiting to start. You can write again when it is done")
            else:
                result = self._follow_up(tx, dept_id, sid, body, scope_id, settings)
        if refusal is not None:
            raise refusal
        if result.delivered == "follow_up":
            self.kick()
        return result

    def _override_command(self, text: str) -> str | None:
        """The command after the override key, '' when only the key was sent, None when the text does not start with the key."""
        secret = self.settings.override_key
        key = secret.get_secret_value() if secret is not None else ""
        if not key or len(text) < len(key):
            return None
        if not hmac.compare_digest(text[: len(key)].encode("utf-8"), key.encode("utf-8")):
            return None
        return text[len(key):].strip()

    @staticmethod
    def _dept_session(conn: sqlite3.Connection, dept_id: str) -> str:
        found = conn.execute("SELECT chat_session_id FROM graph_nodes WHERE id = ?", (dept_id,)).fetchone()
        if found is None or not found["chat_session_id"]:
            raise NotFound("that team's chat")
        return found["chat_session_id"]

    def _post(self, tx: Tx, session_id: str, *, role: str, who: str, kind: str, text: str, task_id: str | None, src_ref: str | None = None,
              **extra: Any) -> Any:
        payload = dict(kind=kind, session_id=session_id, role=role, who=who, text=text, task_id=task_id, src_ref=src_ref, at=tx.now(), **extra)
        try:
            return self.chats.post(tx, session_id, GATE.check("chat_message", payload, ctx=tx.ctx))
        except GateError as exc:
            raise from_gate_error(exc) from None

    def _answer(self, tx: Tx, live: TaskRow, sid: str, shown: str, line: dict, *, answered: bool) -> Delivery:
        """Send an answer (or an override) to the waiting task: the inbox line, the stored owner line, the open questions answered,
        the task and Identity back to `running`."""
        posted = self._post(tx, sid, role="user", who="user", kind="text", text=shown, task_id=live.id)
        run_dir = self.store.run_dir_of(live)
        n = self.launcher.send(run_dir, {**line, "at": iso_z(tx.now())})
        if answered:
            for q in tx.conn.execute(
                    "SELECT id FROM chat_messages WHERE session_id = ? AND kind = 'question' AND answered_by IS NULL AND task_id = ? ORDER BY id",
                    (sid, live.id)).fetchall():
                self.chats.mark_answered(tx, q["id"], posted.id)
        row = self.store.update(tx, live.id, status="running", inbox_seq=n) if live.status == "waiting_user" else live
        identity = tx.ctx.get("node", f"{live.dept_id}.identity")
        if identity is not None and identity.state in ("waiting_on_you", "waiting"):
            self.graph.put_node(tx, GATE.check("node", identity.evolve(state="running", wait_on=None, ts_updated=max(identity.ts_updated, tx.now())), ctx=tx.ctx))
        self.taskgraph.sync(tx, row)
        self.graph.aggregate(tx)
        return Delivery(message_id=posted.id, delivered="answer", task_id=live.id)

    def _follow_up(self, tx: Tx, dept_id: str, sid: str, body: str, scope_id: str | None, settings: dict | None) -> Delivery:
        """No live task: a NEW task (new run id, folder and process; the old folder is never written again). It continues from the
        department's latest run that has a folder; a question left open by an ended task becomes its framing."""
        conn = tx.conn
        latest = self.store.latest_in(conn, dept_id)
        seed = None
        for r in conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE dept_id = ? AND run_id IS NOT NULL ORDER BY created_at DESC, rowid DESC", (dept_id,)):
            prior = _row_of(r)
            if (self.store.runs_dir_in(conn, dept_id) / prior.run_id).is_dir():
                seed = prior
                break
        framing, orphan = "", None
        q = conn.execute(
            "SELECT m.id, m.text, m.task_id FROM chat_messages m JOIN tasks t ON t.id = m.task_id WHERE m.session_id = ? AND m.kind = 'question'"
            " AND m.answered_by IS NULL AND t.status IN ('stopped','crashed','done','done_with_open_items','cancelled') ORDER BY m.id DESC LIMIT 1",
            (sid,)).fetchone()
        if q is not None:
            orphan = q["id"]
            framing = clip(f"Earlier the team asked the owner: {q['text']}", 20_000)
        row = self._insert(
            tx, dept_id=dept_id, text=body, title=None, scope_id=scope_id, framing=framing, depends_on=(), follows=None, request=None,
            change_id=None, settings=settings, seed_run=seed.run_id if seed is not None else None,
            parent_task_id=latest.id if latest is not None else None)
        posted = self._post(tx, sid, role="user", who="user", kind="text", text=body, task_id=row.id)
        if orphan is not None:
            self.chats.mark_answered(tx, orphan, posted.id)
        return Delivery(message_id=posted.id, delivered="follow_up", task_id=row.id)

    # ---- stopping ------------------------------------------------------------------------------------------------------------

    def stop_live(self, dept_id: str) -> bool:
        """The engine's reset. True when no task of the department is starting or running afterwards: a team waiting for the
        owner is stopped through the ladder ('reset by you') and its queued and blocked tasks are cancelled. False, touching
        nothing, when a task is starting or running. May block for the stop ladder (12 s)."""
        conn = self.db.conn()
        rows = [_row_of(r) for r in conn.execute(
            f"SELECT {_COLUMNS} FROM tasks WHERE dept_id = ? AND status IN ('blocked','queued','starting','running','waiting_user')", (dept_id,))]
        if any(r.status in ("starting", "running") for r in rows):
            return False
        for row in rows:
            if row.status == "waiting_user":
                self._run_async(lambda row=row: self._stop(row.id, "reset by you"))
        with self.db.tx() as tx:
            for row in rows:
                if row.status in ("blocked", "queued"):
                    self._cancel(tx, row.id, "reset by you")
            self.graph.aggregate(tx)
        return not any(r.live and r.status != "waiting_user" for r in rows)

    def _cancel(self, tx: Tx, task_id: str, outcome: str) -> TaskRow:
        row = self.store.update(tx, task_id, status="cancelled", ended_at=tx.now(), outcome=outcome)
        self.taskgraph.sync(tx, row)
        self.store.settle_blocked(tx, lambda moved: self.taskgraph.sync(tx, moved))
        return row

    def _mark_stop(self, task_id: str, by: str) -> None:
        """Remember who asked a live task to stop, "owner" or "app", in the reserved settings key `_stopped_by` (the first one to ask
        wins). The engine ends a stopped run with the same words for both, and the Heads up lane must never list the owner's own stop
        (headsup.py)."""
        with self.db.tx() as tx:
            found = tx.conn.execute("SELECT settings_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if found is None:
                return
            stored = json.loads(found["settings_json"] or "{}")
            if stored.get(STOP_KEY):
                return
            stored[STOP_KEY] = by
            self.store.update(tx, task_id, settings_json=json.dumps(stored, sort_keys=True, separators=(",", ":")))

    async def stop(self, task_id: str) -> TaskOut:
        """Stop a task ('stopped by you'): a live task through the ladder, a queued or blocked one is cancelled; a finished one is 409."""
        return await self._stop(task_id, "stopped by you")

    async def _stop(self, task_id: str, outcome: str) -> TaskOut:
        row = await run_blocking(self.store.row, task_id)
        if row.terminal:
            raise Busy("That task has already ended")
        if row.status in ("blocked", "queued"):
            def cancel() -> TaskOut:
                with self.db.tx() as tx:
                    self._cancel(tx, task_id, "stopped by you" if outcome == "stopped by you" else outcome)
                    self.graph.aggregate(tx)
                return self.store.get(task_id)
            return await run_blocking(cancel)
        await run_blocking(self._mark_stop, task_id, "owner")
        run_dir = await run_blocking(self.store.run_dir_of, row)
        await self.launcher.stop(run_dir, row.pid)
        if self.watcher is not None:
            await self.watcher.drain(task_id)
        else:
            await run_blocking(self.projector.drain, task_id)
        await run_blocking(self.projector.mark_ended, task_id, "stopped", outcome)
        if self.watcher is not None:
            self.watcher.unwatch(task_id)
        await self.start_ready()
        return await run_blocking(self.store.get, task_id)

    async def retry(self, task_id: str) -> TaskOut:
        """A new task with the same words, department, scope and settings; `parent_task_id` = the old task. It starts fresh
        (`parent_run_id` only, never `seed_from`). Only a task that ended badly can be retried. Its framing is the first attempt's own
        framing plus the brief of every earlier attempt (`attempts.brief`: how each ended, what its audit had met, what it left), and it
        carries its attempt number."""
        def make() -> str:
            with self.db.tx() as tx:
                old = self.store.row_in(tx.conn, task_id)
                if old is None:
                    raise NotFound("that task")
                if old.status not in ("stopped", "crashed", "cancelled", "done_with_open_items"):
                    raise Busy("Only a task that stopped, crashed or was cancelled can be tried again")
                earlier = attempts.chain(tx.conn, old.id)
                number = attempts.attempt_of(earlier[-1]) + 1
                note = attempts.brief(tx.conn, earlier, number, run_dir=lambda dept, run: self.store.runs_dir_in(tx.conn, dept) / run,
                                      scrub=lambda text: scan(self.redact(text), replace=True)[0])
                base = earlier[0]["framing"].strip()
                framing = f"{clip(base, 20_000 - len(note) - 2)}\n\n{note}" if base else note          # the brief is never the part cut
                row = self._insert(
                    tx, dept_id=old.dept_id, text=old.user_text, title=old.title, scope_id=old.scope_node_id, framing=framing, depends_on=(),
                    follows=None, request=old.request_id, change_id=old.change_id, settings=old.settings, seed_run=None, parent_task_id=old.id,
                    attempt=number)
                return row.id
        new_id = await run_blocking(make)
        await self.start_ready()
        return await run_blocking(self.store.get, new_id)

    # ---- reads the engine plug-in needs ---------------------------------------------------------------------------------------

    def resolve_run(self, run_id: str | None, dept_id: str) -> RunRef | None:
        return self.store.resolve_run(run_id, dept_id)

    # ---- shutdown ------------------------------------------------------------------------------------------------------------

    async def shutdown(self) -> None:
        """App shutdown (5.1): the stop ladder of every live task in parallel (waiting teams included), one last drain of each
        `events.jsonl`, 'the app was closed' (stopped, not crashed) for a task that never wrote run.ended, then the watchers are
        cancelled and the WAL is checkpointed."""
        ids = await run_blocking(self.store.unfinished_ids)

        async def one(task_id: str) -> None:
            row = await run_blocking(self.store.find_row, task_id)
            if row is None or not row.live:
                return
            try:
                await run_blocking(self._mark_stop, task_id, "app")
                run_dir = await run_blocking(self.store.run_dir_of, row)
                await self.launcher.stop(run_dir, row.pid)
                await run_blocking(self.projector.drain, task_id)
                await run_blocking(self.projector.mark_ended, task_id, "stopped", "the app was closed")
            except Exception:                              # noqa: BLE001  (one team must not keep the others from stopping)
                log.exception("could not stop task %s at shutdown", task_id)

        await asyncio.gather(*(one(t) for t in ids))
        if self.watcher is not None:
            await self.watcher.close()
        await run_blocking(self.db.checkpoint)


def _write_atomic(path: Path, text: str) -> None:
    """Write a file with mode 0600 by temp file and rename (the engine reads `task.json` the moment it starts)."""
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        oslayer.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
