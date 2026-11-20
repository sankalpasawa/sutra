"""The Conductor of multi-agent nodes (D257, D275, D277, D278, D296, D302, D303, D311, D312). Split out of `projects.py` by C0: a move, no change of behaviour.

    conductor = Conductor(service)          # `service` is the `ProjectService`: its db, store, tasks, node control, chats and ids are the Conductor's too

What it owns: the task gate (`gate`, `on_starting`), the node state machine and teardown (`sync_task`, `_hand_off`, `_teardown`, `_sync_project`), failure and retry (`_fail`, `_retry`), the tick
(leases, a sleeping computer, gates that ran out), the D296 refusal (`refuse_open_gates`), `reconcile_projects`, and stopping (`stop`, `begin_kill`, `finish_kill`, `pause`). `ProjectService`
keeps `reserve`, `link_task`, the reads and the planner's tokens, and hands the rest to its Conductor, so every caller (the runner, the routes, the wiring, `NodeControl`) is unchanged.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sutra_app.config import NODE_DEFAULT_CAPS
from sutra_app.orchestrator.budgets import SCRUB_LIMIT, chain_spend, egress_scrubs, project_spend, slice_left
from sutra_app.orchestrator.db import Tx, run_blocking
from sutra_app.orchestrator.grants import scopes_overlap
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.engine.host.handoff import ACCEPTED_FILE, HANDOFF_FILE
from sutra_app.engine.host.toollog import log_path, read_log, summarize
from sutra_app.orchestrator.handoff_intake import Accepted, HandoffRefused, read_handoff, write_accepted
from sutra_app.orchestrator.models import ProjectOut
from sutra_app.syspermissions import is_permission_failure
from sutra_app.orchestrator.nodes_store import GATE_REFUSED_ACTION, GATE_REFUSED_CLOSED, GATE_REFUSED_SLEEP, PROJECT_STOPPED_ACTION, NodeBlockError, node_block_of

log = logging.getLogger(__name__)
NODE_FINAL = ("done", "failed", "cancelled")
PROJECT_FINAL = ("done", "done_with_open_items", "stopped", "failed")
LIVE_NODE_STATES = ("leased", "running", "handing_off")
# a node's state from its task's status (the projector owns this from MAN-5: a node is `cancelled` only when its task ended stopped or was cancelled)
TASK_TO_NODE = {"blocked": "planned", "queued": "queued", "starting": "leased", "running": "running", "waiting_user": "running", "done": "done", "done_with_open_items": "done",
                "crashed": "failed", "stopped": "cancelled", "cancelled": "cancelled"}
HELD_STATES = ("awaiting_approval", "awaiting_system")
LOST_LEASE = "lost its lease: no sign of life"
APP_CLOSED = "the app was closed"
APP_CLOSED_WHY = "the app was closed while it ran"
MAX_RESTARTS = 2                                   # a node that the closing of the app ended gets a fresh attempt that does not use up its one retry, at most this many times (D314)
NODE_ERROR_WHY = "following this step failed, so it was ended"
PERMISSION_RESTART = "the computer allowed it, so the step starts again"
NEEDS_SYSTEM_PERMISSION = "your computer did not allow it"       # why a node ended when the computer refused a file (MAN-15)
CAP_PHRASES = ("used up its model calls", "used up its dollars", "ran out of time")      # what the engine host writes (`llm.CAP_WORDS`)
CAP_REACHED = "stopped: this step "                       # + "used up its model calls" / "used up its dollars" / "ran out of time"          # the outcome the engine host writes when a node used up its calls, dollars or time (MAN-9)


def _covers_path(scope: tuple[str, ...], path: str) -> bool:
    """`path` (of the owner's folder, written with `/`) is inside one of the `scope` entries, compared without case (Windows and the default macOS file system do not tell them apart)."""
    low = path.replace("\\", "/").lstrip("/").casefold()
    return any(low == entry.rstrip("/").casefold() or low.startswith(entry.rstrip("/").casefold() + "/") for entry in scope)


def caps_of(project: Any) -> dict[str, Any]:
    return json.loads(project["caps_json"] or "{}")


class Conductor:
    def __init__(self, service: Any) -> None:
        self.service = service
        self._pending: list[tuple[str, str]] = []                                # (project id, reason): stops that were decided inside a transaction and are run by the next tick
        self._last_tick: int | None = None
        self._extended: dict[str, int] = {}                                       # node id -> the moment its lease was extended (once) for a sleeping computer
        self._ticker: Any = None
        self._stop_tasks: list[str] = []                                           # tasks of nodes that were failed closed and are still alive: the next tick stops them (M3)
        self._prepared: dict[str, tuple[tuple[int, int, int], Accepted | None, str]] = {}      # task id -> (the hand-off file's stamp, what was accepted or why not): made outside any transaction (MJ5)
        self._tools: dict[str, tuple[tuple[int, int, int], list[dict[str, Any]]]] = {}         # task id -> (the tool log's stamp, its lines): read before the transaction, written as audit rows at the node's end (MAN-14)

    # what the Conductor shares with the service (read live: the wiring sets some of them after the service is built)
    @property
    def db(self) -> Any:
        return self.service.db

    @property
    def store(self) -> Any:
        return self.service.store

    @property
    def tasks(self) -> Any:
        return self.service.tasks

    @property
    def control(self) -> Any:
        return self.service.control

    @property
    def chats(self) -> Any:
        return self.service.chats

    @property
    def ids(self) -> Any:
        return self.service.ids

    @property
    def settings(self) -> Any:
        return self.service.settings

    @property
    def _clock(self) -> Any:
        return self.service._clock

    def get(self, project_id: str) -> ProjectOut:
        return self.service.get(project_id)

    def stop_planners(self, request_id: str | None = None) -> int:
        return self.service.stop_planners(request_id)

    def _project_row(self, project_id: str) -> sqlite3.Row | None:
        return self.service._project_row(project_id)

    # ---- the task gate -------------------------------------------------------------------------------------------------------------

    def gate(self, conn: sqlite3.Connection, now: int, row: Any) -> str:
        """`TaskService.task_gate` (D257, D302, D303): a waiting sentence or "". The kill switch, pause and the grant check come first (`NodeControl.gate`); then the project's state and the node's."""
        if self.control is not None:
            held = self.control.gate(conn, now, row)
            if held:
                return held
        node = conn.execute(
            "SELECT n.id AS id, n.state AS state, n.project_id AS project_id, p.status AS pstatus, p.paused AS paused, p.caps_json AS caps FROM agent_nodes n "
            "JOIN projects p ON p.id = n.project_id WHERE n.task_id = ?", (row.id,)).fetchone()
        if node is None:
            return ""
        if node["pstatus"] in PROJECT_FINAL:
            return "Held: this project has ended"
        if node["pstatus"] == "awaiting_approval" or node["state"] in HELD_STATES:
            return "Waiting for your answer before this project starts"
        if node["paused"]:
            return "Paused: this project is paused until you resume it"
        if self._upstream_held(conn, node["id"]):
            return "Waiting: a step it needs is held for your answer"             # PB-1: never handed the work of a step that has not been kept or set aside, whoever pressed Continue
        caps = json.loads(node["caps"] or "{}")
        limit = int(caps.get("max_parallel") or NODE_DEFAULT_CAPS["max_parallel"] or 3)
        running = conn.execute("SELECT count(*) FROM agent_nodes WHERE project_id = ? AND state IN ('leased','running','handing_off','expired')", (node["project_id"],)).fetchone()[0]      # an expired node whose process is still there holds its slot (Minor 6)
        if running >= limit:
            return f"Waiting for a free slot in this project ({limit} at a time)"
        apart = self._lease_conflict(conn, node["id"])                       # two writers whose scopes overlap never run together (D260, D323)
        if apart:
            return apart
        ceiling = conn.execute("SELECT budget_credits FROM projects WHERE id = ?", (node["project_id"],)).fetchone()["budget_credits"]
        if ceiling is not None:                                              # the slices of the nodes that still count must fit the project's ceiling (MAN-9)
            slices = conn.execute("SELECT COALESCE(SUM(slice_credits), 0) FROM agent_nodes WHERE project_id = ? AND role = 'worker' AND state NOT IN ('failed','cancelled')",
                                  (node["project_id"],)).fetchone()[0]
            if slices > ceiling:
                return "Waiting: the credits set aside for this project's steps are more than the project may spend"
        return ""

    @staticmethod
    def _upstream_held(conn: sqlite3.Connection, node_id: str) -> bool:
        """True when a step this node follows is `awaiting_approval`: its work is finished but the owner has not yet said keep or set aside (MAN-10, PB-1)."""
        return conn.execute("SELECT 1 FROM agent_nodes d WHERE d.state = 'awaiting_approval' AND d.id IN (SELECT j.value FROM agent_nodes n, json_each(n.depends_on) j WHERE n.id = ?)", (node_id,)).fetchone() is not None

    def _lease_of(self, conn: sqlite3.Connection, row: Any) -> tuple[str, ...] | None:
        """The part of the owner's folder a node may change, as a lease: None for a node that cannot write, `()` for the whole folder (a writer with no scope, or a team whose output is `auto`: a
        possible writer, D307 d), else its normalised paths."""
        try:
            grant = json.loads(row["grants_json"] or "{}")
        except ValueError:
            return None
        if 2 in (grant.get("tiers") or []):
            return tuple(json.loads(row["writes_json"] or "[]"))
        plan = json.loads(conn.execute("SELECT caps_json FROM projects WHERE id = ?", (row["project_id"],)).fetchone()["caps_json"] or "{}").get("plan") or []
        dept = next((s.get("dept") for s in plan if s.get("ref") == row["plan_ref"]), "")
        return () if dept and self.service._output_name(dept) == "auto" else None

    def _lease_conflict(self, conn: sqlite3.Connection, node_id: str) -> str:
        """A waiting sentence when another writer that is alive holds a part of the folder that overlaps this node's, else "". The leases are the rows of `agent_nodes` (their `writes_json`), so they
        survive a restart and are read in the transaction that starts the node. A folder that is not a git repository cannot say who changed what: writers run one at a time (D260)."""
        mine_row = conn.execute("SELECT id, project_id, plan_ref, grants_json, writes_json FROM agent_nodes WHERE id = ?", (node_id,)).fetchone()
        mine = self._lease_of(conn, mine_row) if mine_row is not None else None
        if mine is None:
            return ""
        folder = self.service._folder_of()
        serial = bool(folder) and not (Path(folder) / ".git").exists()
        for other in conn.execute("SELECT id, project_id, plan_ref, grants_json, writes_json FROM agent_nodes WHERE id <> ? AND state IN ('leased','running','handing_off','expired')", (node_id,)).fetchall():
            theirs = self._lease_of(conn, other)
            if theirs is not None and (serial or scopes_overlap(mine, theirs)):
                return "Waiting: another step is changing the same part of your folder" if not serial else "Waiting: another step is changing your folder (it is not a git folder, so steps change it one at a time)"
        return ""

    def on_starting(self, tx: Tx, row: Any) -> None:
        """`TaskService.on_task_starting`, in the transaction that marks the task `starting`: the lease is taken (this node holds its slot until `last_beat_at + lease_s`), so two starts cannot
        both take the last slot."""
        self.sync_task(tx, row.id)

    # ---- the state machine and teardown ---------------------------------------------------------------------------------------------

    def sync_task(self, tx: Tx, task_id: str) -> None:
        """After any change of a node's task: the node's state from the task's status, its lease and teardown, then the project's state. Never moves a node back out of a final state.
        Contained (B1): this runs inside the transaction that records the task's change, so an exception here would undo the task's end and, at startup, stop the app. A failure is undone alone
        (a savepoint), the node is ended `failed` with an audit row `node.error`, never retried, and the task's own change goes on."""
        try:
            with tx.savepoint():
                self._sync_task(tx, task_id)
        except Exception:                                                    # noqa: BLE001  (the state machine must never take the task's own transaction with it)
            log.exception("the state of the node of task %s could not be followed", task_id)
            self._fail_closed(tx, task_id)

    def _fail_closed(self, tx: Tx, task_id: str) -> None:
        """The node of `task_id` ended `failed` because following its task raised: the smallest writes that make it final, then the project's state. Fixed words, nothing from the node."""
        try:
            with tx.savepoint():
                node = tx.conn.execute("SELECT * FROM agent_nodes WHERE task_id = ?", (task_id,)).fetchone()
                if node is None or node["state"] in NODE_FINAL:
                    return
                now = tx.now()
                tx.conn.execute("UPDATE agent_nodes SET state = 'failed', failure_reason = ?, lease_expires_at = NULL, ended_at = ?, torn_down_at = ? WHERE id = ?",
                                (NODE_ERROR_WHY, now, now, node["id"]))
                self.store.audit(tx, actor="conductor", action="node.error", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny", reason=NODE_ERROR_WHY,
                                 ref=task_id)
                tx.emit("node.updated", {"project_id": node["project_id"], "node_id": node["id"], "state": "failed"})
                self._stop_its_task(tx, task_id)
        except Exception:                                                    # noqa: BLE001
            log.exception("could not end the node of task %s", task_id)
            return
        for step in (self._cancel_dependants_of, self._sync_project_of):
            try:
                with tx.savepoint():
                    step(tx, task_id)
            except Exception:                                                # noqa: BLE001  (the next tick looks at the project again)
                log.exception("could not settle the project after the node of task %s", task_id)

    def _stop_its_task(self, tx: Tx, task_id: str) -> None:
        """A node ended by the contained-error path must not leave its task alive (M3): a queued or blocked task is cancelled here; a live one (`starting`, `running`, `waiting_user`) is queued for the
        stop ladder, which the next tick runs (a process that has not begun is refused by `spawn_guard`)."""
        status = tx.conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if status is None or self.tasks is None:
            return
        if status["status"] in ("queued", "blocked"):
            self.tasks.cancel_in(tx, task_id, "stopped: following this step failed")
        elif status["status"] in ("starting", "running", "waiting_user"):
            self._stop_tasks.append(task_id)

    def _cancel_dependants_of(self, tx: Tx, task_id: str) -> None:
        node = tx.conn.execute("SELECT * FROM agent_nodes WHERE task_id = ?", (task_id,)).fetchone()
        if node is not None and self.tasks is not None:
            self._cancel_dependants(tx, node)

    def _sync_project_of(self, tx: Tx, task_id: str) -> None:
        node = tx.conn.execute("SELECT project_id FROM agent_nodes WHERE task_id = ?", (task_id,)).fetchone()
        if node is not None:
            self._sync_project(tx, node["project_id"])

    def _sync_task(self, tx: Tx, task_id: str) -> None:
        node = tx.conn.execute("SELECT n.*, t.status AS tstatus, t.outcome AS toutcome FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.task_id = ?", (task_id,)).fetchone()
        if node is None:
            return
        want = TASK_TO_NODE.get(node["tstatus"], node["state"])
        state = node["state"]
        if state in NODE_FINAL:
            return
        outcome = node["toutcome"] or ""
        if state == "expired" and want in ("cancelled", "failed"):
            want = "failed"                                                  # the ladder ended a node that had gone silent: that is a failure to retry, not the owner's stop
            outcome = LOST_LEASE
        elif want in ("cancelled", "failed") and outcome.startswith(APP_CLOSED):
            want = "failed"                                                  # the app was closed under the node: nothing the owner asked for, so it is tried again, not cancelled
            outcome = APP_CLOSED_WHY
        if want == "failed" and state not in NODE_FINAL and is_permission_failure(outcome):
            self._late_permission(tx, node, outcome)
            return
        if want in ("cancelled", "failed") and outcome.startswith(CAP_REACHED) and any(phrase in outcome for phrase in CAP_PHRASES):
            self.store.audit(tx, actor="conductor", action="trigger.cap_reached", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny", reason=outcome[:200],
                             ref=task_id)
            self._note(tx, node["project_id"], f"A step stopped: {outcome[len('stopped: '):]}. It was not tried again.", f"project:{node['project_id']}#cap:{node['id']}")
            self._fail(tx, node, outcome[:200], retry=False)               # a second attempt would meet the same cap
            tx.emit("node.updated", {"project_id": node["project_id"], "node_id": node["id"], "state": "failed"})
            self._sync_project(tx, node["project_id"])
            return
        if state in HELD_STATES and want in ("queued", "planned"):
            want = state                                                    # a node that waits for an answer stays there until it is answered
        if want == state:
            if want in LIVE_NODE_STATES:
                self._beat(tx, node)
            return
        now = tx.now()
        lease_s = int((json.loads(tx.conn.execute("SELECT caps_json FROM projects WHERE id = ?", (node["project_id"],)).fetchone()["caps_json"] or "{}")).get("lease_s") or 90)
        if want == "leased":
            tx.conn.execute("UPDATE agent_nodes SET state = 'leased', lease_expires_at = ?, last_beat_at = ? WHERE id = ?", (now + lease_s, now, node["id"]))
            self.store.audit(tx, actor="conductor", action="node.leased", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", reason=f"lease {lease_s} s")
        elif want == "running":
            tx.conn.execute("UPDATE agent_nodes SET state = 'running', lease_expires_at = ?, last_beat_at = ? WHERE id = ?", (now + lease_s, now, node["id"]))
            self.store.audit(tx, actor="conductor", action="node.spawned", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", ref=task_id)
        elif want == "done" and node["role"] == "worker" and self.tasks is not None:
            self._hand_off(tx, node, task_id)                              # the hand-off is read, checked, scrubbed and stored; only then is the node done (MAN-6)
        elif want == "done" and node["role"] == "reviewer" and self.tasks is not None:
            self._review_done(tx, node, task_id)                           # the verdict is read, checked and stored; it informs, the owner decides (MAN-11)
        elif want == "failed":
            self._fail(tx, node, outcome[:200])
        elif want in NODE_FINAL:
            self._teardown(tx, node, want, outcome[:200] if want != "done" else "")
        else:
            tx.conn.execute("UPDATE agent_nodes SET state = ? WHERE id = ?", (want, node["id"]))
        tx.emit("node.updated", {"project_id": node["project_id"], "node_id": node["id"], "state": want})
        self._sync_project(tx, node["project_id"])

    def prepare_handoff(self, task_id: str) -> None:
        """Before the projector opens its transaction for a task's events (MJ5): when the task is the run of a worker node and its `handoff.json` is there, the file is read, checked, hashed and
        `handoff.accepted.json` is written NOW, outside any transaction, so no hash, fsync or rename happens while the writer transaction is open. The outcome (an `Accepted` or the refusal)
        waits in `_prepared` for `_hand_off`; a changed file is read again there. Never raises: a failure here only means `_hand_off` does the work itself."""
        try:
            node = self.db.conn().execute("SELECT id, runtime FROM agent_nodes WHERE task_id = ? AND role = 'worker' AND state IN ('leased','running')", (task_id,)).fetchone()
            if node is None or self.tasks is None:
                return
            row = self.tasks.store.find_row(task_id)
            if row is None or row.run_id is None:
                return
            run_dir = self.tasks.store.run_dir_of(row)
            stamp = self._stamp(run_dir)
            if stamp is None or (task_id in self._prepared and self._prepared[task_id][0] == stamp):
                return
            try:
                accepted = read_handoff(run_dir, node["id"], node["runtime"], self.store.redact)
                write_accepted(run_dir, accepted)
                self._prepared[task_id] = (stamp, accepted, "")
            except HandoffRefused as refused:
                self._prepared[task_id] = (stamp, None, str(refused))
            except OSError:
                self._prepared[task_id] = (stamp, None, "the hand-off could not be stored")
        except Exception:                                                    # noqa: BLE001  (a look ahead that fails is no reason to fail anything)
            log.exception("could not look at the hand-off of task %s ahead of time", task_id)

    def prepare_tools(self, task_id: str) -> None:
        """MAN-14: before the projector's transaction, read the run's `tools.jsonl` of a node that is working (only when the file changed since the last look), so no file is read while the writer
        transaction is open. Never raises."""
        try:
            node = self.db.conn().execute("SELECT id FROM agent_nodes WHERE task_id = ? AND role IN ('worker','reviewer') AND state IN ('leased','running','handing_off')", (task_id,)).fetchone()
            if node is None or self.tasks is None:
                return
            row = self.tasks.store.find_row(task_id)
            if row is None or row.run_id is None:
                return
            path = log_path(self.settings.data_dir, row.run_id)
            stamp = self._stamp(path.parent, path.name)
            if stamp is None or (task_id in self._tools and self._tools[task_id][0] == stamp):
                return
            self._tools[task_id] = (stamp, read_log(path))
        except Exception:                                                    # noqa: BLE001
            log.exception("could not read the tool log of task %s ahead of time", task_id)

    def _audit_tools(self, tx: Tx, node: sqlite3.Row) -> None:
        """MAN-14, D327: at a node's end its tool calls become audit rows: one for each different tool, with its kind, the base name of a file and how many times. Names and kinds only, never an
        input (the log holds none). The lines read ahead (`prepare_tools`) are used; when none were (the node ended before it could be read, or the server restarted) the file is read here: it is
        small and has a hard limit. At most MAX_KINDS rows; the calls of the kinds that did not fit are counted in one last row. Nothing at all for a node that made no tool call."""
        task_id = node["task_id"] or ""
        ahead = self._tools.pop(task_id, None)
        rows = ahead[1] if ahead is not None else None
        if rows is None and task_id and self.tasks is not None:
            try:
                row = self.tasks.store.row_in(tx.conn, task_id)
                rows = read_log(log_path(self.settings.data_dir, row.run_id)) if row is not None and row.run_id is not None else []
            except Exception:                                                # noqa: BLE001  (a tool log that cannot be read is no rows, never a node that cannot end)
                rows = []
        groups, left_out = summarize(rows or [])
        for name, kind, target, times in groups:
            self.store.audit(tx, actor="node", action="tool.used", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", target=name,
                             reason=f"{kind}{' ' + target if target else ''}, {times} time{'s' if times != 1 else ''}", ref=task_id)
        if left_out:
            self.store.audit(tx, actor="node", action="tool.used", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", target="more",
                             reason=f"{left_out} more calls of other tools", ref=task_id)

    @staticmethod
    def _stamp(run_dir: Any, name: str = HANDOFF_FILE) -> tuple[int, int, int] | None:
        from pathlib import Path
        try:
            info = (Path(run_dir) / name).lstat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size, info.st_ino)

    def _hand_off(self, tx: Tx, node: sqlite3.Row, task_id: str) -> None:
        """The Conductor's intake (D263, D281; MAN-6): the node's task ended well, so its `handoff.json` is read and checked (`handoff_intake`), scrubbed, stored as a message of the project
        (`handoff:<node>:<attempt>`, once) and written as `handoff.accepted.json`, the one file dependants are given. A missing, malformed, too big or untrue hand-off ends the node `failed` with
        the rule that broke, and an audit row `handoff.refused`; the node's own files stay for the owner. The reading, hashing and writing of files is done before the transaction opened
        (`prepare_handoff`, MJ5); only when that did not happen (the file changed, or the task ended some other way) is it done here."""
        tx.conn.execute("UPDATE agent_nodes SET state = 'handing_off' WHERE id = ?", (node["id"],))
        row = self.tasks.store.row_in(tx.conn, task_id)
        try:
            run_dir = self.tasks.store.run_dir_of(row)
            prepared = self._prepared.pop(task_id, None)
            if prepared is not None and prepared[0] == self._stamp(run_dir):
                if prepared[1] is None:
                    raise HandoffRefused(prepared[2])
                accepted = prepared[1]
            else:
                accepted = read_handoff(run_dir, node["id"], node["runtime"], self.store.redact)
                write_accepted(run_dir, accepted)
            if self._scope_violation(tx, node, accepted, task_id):                # a path nobody owns was changed: held for the owner's answer, or set aside (MAN-10)
                return
            posted = self.store.post(tx, project_id=node["project_id"], kind="handoff", src_ref=f"handoff:{node['id']}:{node['attempt']}", body=accepted.document,
                                     from_node=node["id"], to_node="project", file=ACCEPTED_FILE)
        except HandoffRefused as refused:
            self.store.audit(tx, actor="conductor", action="handoff.refused", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny", reason=str(refused),
                             ref=task_id)
            self._fail(tx, node, f"its results were not accepted: {refused}")
            return
        except OSError:
            self.store.audit(tx, actor="conductor", action="handoff.refused", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny",
                             reason="the hand-off could not be stored", ref=task_id)
            self._fail(tx, node, "its results were not accepted: they could not be stored")
            return
        self.store.audit(tx, actor="conductor", action="handoff.accepted", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="allow",
                         reason=f"{len(accepted.document['files'])} file(s), message {posted.seq}", ref=str(posted.seq))
        self._teardown(tx, node, "done", "")

    def _unchecked(self, tx: Tx, node: sqlite3.Row, task_id: str, why: str) -> None:
        """G26 (D336 b): a writer's check that could not be made says so, once for each run of the step: an audit row `scope.unchecked` with the reason in plain words and no path. It never holds anything."""
        if tx.conn.execute("SELECT 1 FROM node_audit WHERE node_id = ? AND action = 'scope.unchecked' AND ref = ?", (node["id"], task_id)).fetchone() is None:
            self.store.audit(tx, actor="conductor", action="scope.unchecked", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", reason=why, ref=task_id)

    def _ran_alone(self, tx: Tx, node: sqlite3.Row, task_id: str) -> bool:
        """True when no other step that may write was alive while this one ran (R2, D336 e): another writer counts when its task is still going, or its window overlaps this one's. Windows are the
        tasks' own `started_at` and `ended_at` (whole seconds): a step that began in the very second another ended did not overlap it. Writers of other projects count too (leases are global)."""
        mine = tx.conn.execute("SELECT started_at, ended_at, created_at FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if mine is None:
            return False
        begin = mine["started_at"] if mine["started_at"] is not None else mine["created_at"]
        end = mine["ended_at"] if mine["ended_at"] is not None else tx.now()
        for other in tx.conn.execute(
                "SELECT n.id, n.project_id, n.plan_ref, n.grants_json, n.writes_json, t.started_at AS s, t.ended_at AS e FROM agent_nodes n JOIN tasks t ON t.id = n.task_id "
                "WHERE n.id <> ? AND n.role = 'worker' AND t.started_at IS NOT NULL", (node["id"],)).fetchall():
            if self._lease_of(tx.conn, other) is None:
                continue
            if other["e"] is None or (other["e"] > begin and other["s"] < end):
                return False
        return True

    def _outside_paths(self, tx: Tx, node: sqlite3.Row, accepted: Accepted, task_id: str) -> list[str]:
        """The paths this step changed that it had no part in (MAN-10, D336): from the host's whole list (`changes.json`, up to 5000), else the first 100 the hand-off names. A step that ran alone is
        checked against ITS OWN scope; steps that overlapped in time are checked against the union of the project's writers' scopes (the watch cannot say which of two parallel writers wrote a path).
        When the check cannot be made (no list at all, a partial list, a step or a neighbour with no scope) an audit row says so and nothing is held."""
        mine = self._lease_of(tx.conn, node)
        document = accepted.document
        paths = accepted.changes_all if accepted.changes_all is not None else document.get("changes")
        if paths is None:
            if mine is not None:
                self._unchecked(tx, node, task_id, "git could not say which files this step changed (this is not a git folder, there were too many changes, or git did not answer), so they were not checked")
            return []
        if accepted.changes_all is None and int(document.get("changes_more") or 0) > 0 and mine is not None:
            self._unchecked(tx, node, task_id, f"only the first {len(paths)} changed files were named, so the other {int(document['changes_more'])} were not checked")
        if not paths:
            return []
        if mine is not None and not mine:
            self._unchecked(tx, node, task_id, "this step was not given its own part of your folder, so nothing could be outside it")
            return []
        if mine is not None and self._ran_alone(tx, node, task_id):
            return [path for path in paths if not _covers_path(mine, path)]
        owned: list[tuple[str, ...]] = []
        for row in tx.conn.execute("SELECT plan_ref, grants_json, writes_json, project_id FROM agent_nodes WHERE project_id = ? AND role = 'worker'", (node["project_id"],)).fetchall():
            lease = self._lease_of(tx.conn, row)
            if lease is not None:
                owned.append(lease)
        if any(not scope for scope in owned):                                   # a writer that owns the whole folder: nothing can be said to be outside
            if mine is not None:
                self._unchecked(tx, node, task_id, "another step may change the whole folder, so one step's files cannot be told from another's")
            return []
        return [path for path in paths if not any(_covers_path(scope, path) for scope in owned)]

    def _scope_violation(self, tx: Tx, node: sqlite3.Row, accepted: Accepted, task_id: str) -> bool:
        """MAN-10 (D303, D336): a path the node's run changed in the owner's folder that it had no part in (its own scope when it ran alone, else the union of the scopes of the project's writers) is a
        scope violation. The owner is asked (a card): keep the work or set it aside; Decide for me sets it aside (`gatekeeper.on_scope_violation`: the node is
        quarantined, its files kept, nothing is given on). While the question is open the node waits (`awaiting_approval`) and the project starts nothing new. Returns True when the hand-off must not
        go on now (held or set aside), False when there is nothing outside or the owner allowed it."""
        outside = self._outside_paths(tx, node, accepted, task_id)
        if not outside:
            return False
        key = f"violation:{node['id']}:{node['attempt']}"
        found = tx.conn.execute("SELECT id, status FROM approvals WHERE project_id = ? AND client_id = ?", (node["project_id"], key)).fetchone()
        if found is None:
            names = [path[:200] for path in outside[:5]]
            asked = self.store.open_approval(tx, project_id=node["project_id"], node_id=node["id"], tier=2, client_id=key,
                                             expires_at=tx.now() + int(NODE_DEFAULT_CAPS["approval_expiry_s"] or 86400), request={"kind": "scope_violation", "paths": names, "count": len(outside)})
            self.store.audit(tx, actor="conductor", action="scope.violation", project_id=node["project_id"], node_id=node["id"], role=node["role"], tier=2, decision="ask",
                             reason=f"{len(outside)} file(s) outside every step's part of your folder", ref=asked.id)
            tx.conn.execute("UPDATE agent_nodes SET state = 'awaiting_approval' WHERE id = ?", (node["id"],))
            tx.conn.execute("UPDATE projects SET paused = 1 WHERE id = ?", (node["project_id"],))
            self.store.audit(tx, actor="system", action="project.paused", project_id=node["project_id"], decision="n/a", reason="a step changed files nobody owns")
            decide = tx.conn.execute("SELECT decide_for_me FROM projects WHERE id = ?", (node["project_id"],)).fetchone()["decide_for_me"]
            if decide:
                tx.conn.execute("UPDATE projects SET paused = 0 WHERE id = ?", (node["project_id"],))
                self.service.violation_by_rule(tx, asked)                       # the rule table sets it aside, audited as `rule:decide_for_me`
                return self._scope_violation(tx, tx.conn.execute("SELECT * FROM agent_nodes WHERE id = ?", (node["id"],)).fetchone(), accepted, task_id)
            self.service.sync_cards(tx, node["project_id"])
            return True
        if found["status"] == "open":
            tx.conn.execute("UPDATE agent_nodes SET state = 'awaiting_approval' WHERE id = ?", (node["id"],))
            return True
        if found["status"] in ("allowed_once", "allowed_project"):
            return False
        self.store.audit(tx, actor="conductor", action="scope.quarantined", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny",
                         reason="its changes outside every step's part of your folder were set aside; its files are kept", ref=found["id"])
        self._fail(tx, node, "it changed files nobody gave it: its work was set aside and its files are kept", retry=False)
        return True

    @staticmethod
    def _beat(tx: Tx, node: sqlite3.Row) -> None:
        now = tx.now()
        tx.conn.execute("UPDATE agent_nodes SET last_beat_at = ?, lease_expires_at = ? + COALESCE(lease_expires_at - last_beat_at, 90) WHERE id = ?", (now, now, node["id"]))

    def _teardown(self, tx: Tx, node: sqlite3.Row, state: str, why: str) -> None:
        """A node ended: its final state, its lease released, the time stamped, one audit row. The run folder stays where it is (D276: nothing the owner could want is deleted)."""
        now = tx.now()
        self._prepared.pop(node["task_id"] or "", None)
        tx.conn.execute("UPDATE agent_nodes SET state = ?, failure_reason = ?, lease_expires_at = NULL, ended_at = ?, torn_down_at = ? WHERE id = ?", (state, why[:200], now, now, node["id"]))
        self._audit_tools(tx, node)                                                 # the tool calls of this attempt, as names and kinds (MAN-14); before the end row, so the story reads in order
        self.store.audit(tx, actor="conductor", action=f"node.{state}", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", reason=why, ref=node["task_id"] or "")
        if state == "failed" and self.tasks is not None:
            self._cancel_dependants(tx, node)

    def _cancel_dependants(self, tx: Tx, node: sqlite3.Row) -> None:
        """A node that failed after its task ended well (a refused hand-off) must not let its dependants start: they are cancelled, as the dependants of a task that ended badly are (failure policy
        `stop_branch`, D278). A task that ended badly does this through `settle_blocked` already; this is the same rule for the failure the task layer cannot see."""
        found = tx.conn.execute("SELECT n.task_id AS task_id FROM agent_nodes n, json_each(n.depends_on) j WHERE j.value = ? AND n.task_id IS NOT NULL AND n.state NOT IN ('done','failed','cancelled')",
                                (node["id"],)).fetchall()
        for row in found:
            task = self.tasks.store.row_in(tx.conn, row["task_id"])
            if task is not None and task.status in ("blocked", "queued"):
                self.tasks.cancel_in(tx, task.id, "cancelled: a step it needed did not finish")
    def _sync_project(self, tx: Tx, project_id: str) -> None:
        """The project's state from its nodes (D278: a project with a failed or cancelled node never ends `done`). `running` while any node is live or waiting to start."""
        project = tx.conn.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None or project["status"] in PROJECT_FINAL:
            return
        if self._review(tx, project_id):                                    # a reviewer is made, or the owner's answer to a verdict is awaited (MAN-11): the project does not end yet
            return
        states = [r["state"] for r in tx.conn.execute("SELECT state FROM agent_nodes WHERE project_id = ? AND role <> 'planner'", (project_id,))]
        if not states or any(state not in NODE_FINAL for state in states):
            return
        open_items = tx.conn.execute("SELECT count(*) FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND t.status = 'done_with_open_items'", (project_id,)).fetchone()[0]
        if all(state == "done" for state in states) and open_items:
            end, why = "done_with_open_items", "some steps ended with open items"
        elif all(state == "done" for state in states):
            end, why = "done", ""
        elif any(state == "done" for state in states):
            end, why = "done_with_open_items", "some steps did not finish"
        else:
            end, why = "failed", "no step finished"
        tx.conn.execute("UPDATE projects SET status = ?, ended_at = ?, stop_reason = ? WHERE id = ?", (end, tx.now(), why, project_id))
        self.store.audit(tx, actor="conductor", action="project.ended", project_id=project_id, decision="n/a", reason=end)
        tx.emit("project.updated", {"project_id": project_id, "status": end})

    # ---- failure: retry once, then the policy (D278, D305c, MAN-7) ------------------------------------------------------------------

    def _fail(self, tx: Tx, node: sqlite3.Row, why: str, *, retry: bool = True) -> None:
        """A node failed (its task crashed, it lost its lease, its hand-off was refused). It is retried once, as a new attempt of the same node, if the project still runs; else it is `failed`
        and the project's failure policy applies. A node the owner or the kill switch stopped never comes here (it is `cancelled`). `retry=False`: a failure a second attempt would repeat
        (a grant that is not valid, a node the state machine itself could not handle) ends the node at once."""
        project = tx.conn.execute("SELECT status, failure_policy, caps_json FROM projects WHERE id = ?", (node["project_id"],)).fetchone()
        caps = json.loads(project["caps_json"] or "{}")
        retries = int(caps.get("retries") if caps.get("retries") is not None else NODE_DEFAULT_CAPS["retries"] or 1)
        restarts = self._restarts(tx, node["id"])
        closed = why.startswith(APP_CLOSED_WHY)
        if closed and restarts < MAX_RESTARTS:
            action = "node.restarted"                                        # the app closing is not the node's failure: a fresh attempt that spends no retry (D314)
        elif node["attempt"] - restarts <= retries:
            action = "node.retry"
        else:
            action = ""
        if action and retry and project["status"] in ("running",) and self.tasks is not None and node["task_id"]:
            try:
                with tx.savepoint():
                    self._retry(tx, node, why, action=action)
                return
            except AppError as refused:                                      # the team is gone (archived), the task cannot be repeated or its credits are used up: the node ends here, cleanly (B1)
                why = f"{why[:100]} ({refused.message if refused.code == 'busy' else 'it could not be tried again'})"
        self._teardown(tx, node, "failed", why)
        if why.startswith(LOST_LEASE) and node["attempt"] >= 2:                 # D303 e: a node that loses its lease twice stops the project and says so
            self.store.audit(tx, actor="conductor", action="trigger.lease_lost", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny",
                             reason="lost its lease twice", ref=node["task_id"] or "")
            self._pending.append((node["project_id"], "a step lost contact with Sutra twice"))
        elif project["failure_policy"] == "stop_all":
            self._pending.append((node["project_id"], "a step failed and this project stops at the first failure"))

    @staticmethod
    def _restarts(tx: Tx, node_id: str) -> int:
        """How many times the closing of the app already gave this node a fresh attempt (counted from the audit trail: no column for it)."""
        return int(tx.conn.execute("SELECT count(*) FROM node_audit WHERE node_id = ? AND action = 'node.restarted'", (node_id,)).fetchone()[0])

    def _retry(self, tx: Tx, node: sqlite3.Row, why: str, *, action: str = "node.retry") -> None:
        """A new attempt of the node in the transaction that ends the old one (D305c): the node's `task_id` points at the new task, the attempt number goes up, its dependants wait for the new task,
        and the grant is the one it had (frozen). The old task stays in `tasks` as the new one's parent."""
        old_task = node["task_id"]
        if node["slice_credits"] is not None and slice_left(node["slice_credits"], chain_spend(tx.conn, old_task)[0]) <= 0:
            raise AppError("busy", "That step used up all its credits, so it is not tried again")         # never a full fresh slice (D324)
        new = self.tasks.retry_in(tx, old_task, force=True)
        tx.conn.execute("UPDATE tasks SET lane = (SELECT lane FROM tasks WHERE id = ?) WHERE id = ?", (old_task, new.id))      # a step keeps its lane for every attempt: a retry, a restart, a send-back (PB-5)
        self._audit_tools(tx, node)                                                 # what the attempt that ended did, before the node points at the new task (MAN-14)
        now = tx.now()
        tx.conn.execute("UPDATE agent_nodes SET task_id = ?, attempt = attempt + 1, state = 'queued', failure_reason = '', lease_expires_at = NULL, last_beat_at = NULL, ended_at = NULL, "
                        "torn_down_at = NULL WHERE id = ?", (new.id, node["id"]))
        for row in tx.conn.execute("SELECT t.id AS id, t.depends_on AS deps FROM tasks t WHERE t.status IN ('blocked','queued') AND t.id <> ? AND EXISTS "
                                   "(SELECT 1 FROM json_each(t.depends_on) j WHERE j.value = ?)", (new.id, old_task)).fetchall():
            tx.conn.execute("UPDATE tasks SET depends_on = ? WHERE id = ?", (json.dumps([new.id if dep == old_task else dep for dep in json.loads(row["deps"])]), row["id"]))
        self._extended.pop(node["id"], None)
        self.store.audit(tx, actor="conductor", action=action, project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", reason=why[:200],
                         ref=new.id)
        tx.emit("node.updated", {"project_id": node["project_id"], "node_id": node["id"], "state": "queued"})

    # ---- the tick: leases, a sleeping computer, gates that ran out (MAN-7) ------------------------------------------------------------

    async def tick(self, now: int | None = None) -> dict[str, list[str]]:
        """One look at every project that runs. A live node that has been silent for its lease (default 90 s: no event, heartbeat included) goes `expired`, its process through the stop ladder,
        and is retried once (D275). If the tick itself came late by more than half a lease the computer slept: the leases are extended once instead, and a project with an open gate is
        refused (D296). A gate that ran out (24 h) is refused too. Stops decided inside a transaction (`stop_all`, a node that lost its lease twice) are run here. Returns what it did."""
        began = int(self._clock.now())
        moment = int(now) if now is not None else began
        gap = 0 if self._last_tick is None else moment - self._last_tick
        try:
            return await self._tick(moment, gap)
        finally:
            # the gap is measured from the END of a tick to the start of the next (D311): the stop ladders a tick ran are its own work, not a sleep. An explicit `now` (tests) moves on by what the tick took.
            self._last_tick = moment + max(0, int(self._clock.now()) - began)

    async def _tick(self, moment: int, gap: int) -> dict[str, list[str]]:
        import asyncio
        scrubs = await run_blocking(egress_scrubs, self.settings.data_dir / "connectors" / "egress.jsonl")       # read BEFORE the write transaction opens: up to 2 MB is parsed (m8)
        did = await run_blocking(self._tick_sync, moment, gap, scrubs)
        if did["expire"]:
            await asyncio.gather(*(self.tasks.stop_node(task_id, f"no sign of life for {did['lease']} s", by="system") for task_id in did["expire"]), return_exceptions=True)
        stuck, self._stop_tasks = self._stop_tasks, []
        if stuck:
            await asyncio.gather(*(self.tasks.stop_node(task_id, "stopped: following this step failed", by="system") for task_id in stuck), return_exceptions=True)
        if did["scrub"]:
            await asyncio.gather(*(self.tasks.stop_node(task_id, "stopped: its prompts held secrets again and again", by="system") for task_id in did["scrub"]), return_exceptions=True)
        for project_id, reason in did["refuse"]:
            await self._stop_nodes(project_id, reason, "system")                     # the database part of the refusal was done in the tick's own transaction
        pending, self._pending = self._pending, []
        for project_id, reason in pending:
            await self.stop(project_id, by="system", reason=reason)
        return {"expired": did["expire"], "refused": [p for p, _ in did["refuse"]], "stopped": [p for p, _ in pending], "extended": did["extended"]}

    def _tick_sync(self, now: int, gap: int, scrubs: dict[str, int] | None = None) -> dict[str, Any]:
        expire: list[str] = []
        scrub: list[str] = []
        extended: list[str] = []
        refuse: list[tuple[str, str]] = []
        lease_default = int(NODE_DEFAULT_CAPS["lease_s"] or 90)
        with self.db.tx() as tx:
            for project in tx.conn.execute("SELECT id, status, caps_json, created_at, budget_usd FROM projects WHERE status IN ('planning','awaiting_approval','running','reviewing') ORDER BY created_at").fetchall():
                lease_s = int(json.loads(project["caps_json"] or "{}").get("lease_s") or lease_default)
                slept = gap > lease_s // 2
                ran_out = self.store.expire_due(tx, project_id=project["id"], now=now)
                if any(a.request.get("late") for a in ran_out):                      # a late permission question that ran out only ends: the other steps keep their work (m3)
                    self.service.sync_cards(tx, project["id"])
                reviews_out = [a for a in ran_out if a.request.get("kind") == "review"]
                for approval in reviews_out:                                         # the reviewer's advice ran out: a no, the project ends as it is (PB-3)
                    self.store.audit(tx, actor="system", action=GATE_REFUSED_ACTION, project_id=project["id"], node_id=approval.node_id or None, tier=approval.tier, decision="deny",
                                     reason="the question ran out of time, so it counts as a no", ref=approval.id)
                if reviews_out:
                    self._sync_project(tx, project["id"])
                    self.service.sync_cards(tx, project["id"])
                ran_out = [a for a in ran_out if not a.request.get("late") and a.request.get("kind") != "review"]
                if slept:
                    self._review_as_no(tx, project["id"], "the computer was closed or asleep before you answered, so it counts as a no")
                reason = ""
                if ran_out:
                    for approval in ran_out:
                        self.store.audit(tx, actor="system", action=GATE_REFUSED_ACTION, project_id=project["id"], node_id=approval.node_id or None, tier=approval.tier, decision="deny",
                                         reason="the question ran out of time", ref=approval.id)
                    reason = "not approved: the question ran out of time"
                elif slept and tx.conn.execute("SELECT 1 FROM approvals WHERE project_id = ? AND status = 'open' AND request_json NOT LIKE '%\"late\":1%'", (project["id"],)).fetchone() is not None:
                    reason = GATE_REFUSED_SLEEP
                elif project["status"] == "awaiting_approval" and tx.conn.execute("SELECT 1 FROM approvals WHERE project_id = ? AND status = 'open'", (project["id"],)).fetchone() is None:
                    reason = "not approved: no question was left to answer"          # a project that waits for nothing would wait for ever (MJ7)
                if reason:
                    self._refuse_in(tx, project["id"], reason)                       # the decision and the stop are one transaction: no crash can leave one without the other (MJ7)
                    refuse.append((project["id"], reason))
                    continue
                if self._project_limit(tx, project["id"], now, project["created_at"], caps_of(project)):
                    continue
                self._scrubbed_nodes(tx, project["id"], scrub, scrubs or {})
                self._fail_without_grant(tx, project["id"])
                for stuck in tx.conn.execute("SELECT n.task_id AS task_id FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND n.state = 'expired' "
                                             "AND t.status IN ('starting','running','waiting_user')", (project["id"],)).fetchall():
                    expire.append(stuck["task_id"])                                   # its stop did not work: ask again every tick until the process is gone (Minor 6)
                for node in tx.conn.execute(
                        "SELECT n.id AS id, n.role AS role, n.task_id AS task_id, n.state AS state, COALESCE(t.last_event_at, t.started_at, ?) AS beat FROM agent_nodes n "
                        "JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND n.state IN ('leased','running')", (now, project["id"])).fetchall():
                    beat = max(int(node["beat"]), self._extended.get(node["id"], 0))        # the extension counts as a sign of life
                    silent = now - beat
                    if silent <= lease_s:
                        tx.conn.execute("UPDATE agent_nodes SET last_beat_at = ?, lease_expires_at = ? WHERE id = ?", (beat, beat + lease_s, node["id"]))
                    elif slept and node["id"] not in self._extended:         # the computer slept: the lease is extended once, not the process killed
                        self._extended[node["id"]] = now
                        tx.conn.execute("UPDATE agent_nodes SET last_beat_at = ?, lease_expires_at = ? WHERE id = ?", (now, now + lease_s, node["id"]))
                        self.store.audit(tx, actor="conductor", action="node.lease_extended", project_id=project["id"], node_id=node["id"], role=node["role"], decision="n/a",
                                         reason="the computer slept")
                        extended.append(node["id"])
                    else:
                        tx.conn.execute("UPDATE agent_nodes SET state = 'expired' WHERE id = ?", (node["id"],))
                        self.store.audit(tx, actor="conductor", action="node.heartbeat_lost", project_id=project["id"], node_id=node["id"], role=node["role"], decision="n/a",
                                         reason=f"silent for {silent} s (lease {lease_s} s)")
                        self.store.audit(tx, actor="conductor", action="node.expired", project_id=project["id"], node_id=node["id"], role=node["role"], decision="n/a", reason="lease lost")
                        expire.append(node["task_id"])
        return {"expire": expire, "scrub": scrub, "refuse": refuse, "extended": extended, "lease": lease_default}

    def _project_limit(self, tx: Tx, project_id: str, now: int, created_at: int, caps: dict[str, Any]) -> bool:
        """The project's own limits (MAN-9): wall time (`project_wall_s`, 2 hours) and dollars (`budget_usd`, when the owner set one). Past either the project is stopped by the system (the ladders
        run at the end of the tick), with an audit row `trigger.project_wall` or `trigger.project_usd` and a plain note. True when it was stopped."""
        wall = int(caps.get("project_wall_s") or NODE_DEFAULT_CAPS["project_wall_s"] or 7200)
        reason = action = ""
        began = tx.conn.execute("SELECT MIN(t.started_at) FROM tasks t JOIN agent_nodes n ON n.task_id = t.id WHERE n.project_id = ? AND t.started_at IS NOT NULL", (project_id,)).fetchone()[0]
        # the wall time counts from the first node's start (a project that waits for an answer is not running, D321 b) and leaves out the time it was paused
        if began is not None and now - int(began) - self._paused_seconds(tx, project_id, now, int(began)) > wall:
            reason, action = f"the project ran longer than {wall // 60} minutes", "trigger.project_wall"
        else:
            limit = tx.conn.execute("SELECT budget_usd FROM projects WHERE id = ?", (project_id,)).fetchone()["budget_usd"]
            if limit is not None:
                spent = project_spend(tx.conn, project_id)[1]                      # every attempt of every node counts (D324)
                if spent > float(limit):
                    reason, action = "the project spent more than the dollars you set", "trigger.project_usd"
        if not reason:
            return False
        self.store.audit(tx, actor="conductor", action=action, project_id=project_id, decision="deny", reason=reason)
        self._note(tx, project_id, f"I stopped it: {reason}.", f"project:{project_id}#limit")
        self._pending.append((project_id, f"stopped: {reason}"))
        return True

    @staticmethod
    def _paused_seconds(tx: Tx, project_id: str, now: int, since: int) -> int:
        """How long the project was paused after `since`, from its audit rows (`project.paused`, `project.resumed`); a pause that is still on counts until `now`."""
        total, began = 0, None
        for row in tx.conn.execute("SELECT at, action FROM node_audit WHERE project_id = ? AND action IN ('project.paused','project.resumed') ORDER BY seq", (project_id,)):
            if row["action"] == "project.paused" and began is None:
                began = max(int(row["at"]), since)
            elif row["action"] == "project.resumed" and began is not None:
                total += max(0, int(row["at"]) - began)
                began = None
        return total + (max(0, now - began) if began is not None else 0)

    def _scrubbed_nodes(self, tx: Tx, project_id: str, scrub: list[str], counts: dict[str, int]) -> None:
        """D303: a node whose prompts were scrubbed `SCRUB_LIMIT` times (rows of `egress.jsonl` that name it and found something) is ended: audit `trigger.egress_scrub`, a plain note, its task
        through the stop ladder at the end of the tick. Counted from the node's own rows, so a repeat is the same node and never another."""
        live = tx.conn.execute("SELECT n.id AS id, n.role AS role, n.task_id AS task_id FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? "
                               "AND n.state IN ('leased','running') AND t.status IN ('starting','running','waiting_user')", (project_id,)).fetchall()
        if not live:
            return
        for row in live:
            if counts.get(row["id"], 0) >= SCRUB_LIMIT:
                scrub.append(row["task_id"])                                         # asked again every tick until the process is gone
                if tx.conn.execute("SELECT 1 FROM node_audit WHERE node_id = ? AND action = 'trigger.egress_scrub'", (row["id"],)).fetchone() is not None:
                    continue                                                         # the row and the note are written once
                self.store.audit(tx, actor="conductor", action="trigger.egress_scrub", project_id=project_id, node_id=row["id"], role=row["role"], decision="deny",
                                 reason=f"its prompts were scrubbed {counts[row['id']]} times", ref=row["task_id"])
                self._note(tx, project_id, "A step was stopped because its prompts held secrets again and again.", f"project:{project_id}#scrub:{row['id']}")

    # ---- the reviewer (MAN-11) ------------------------------------------------------------------------------------------------------

    def _review(self, tx: Tx, project_id: str) -> bool:
        """With SUTRA_NODES_REVIEWER on: once every worker of the project is over and at least one finished, a read-only reviewer node (runtime `light`) is made, with the earlier steps' tasks as its
        upstream; at most one more for each time the owner sent work back. While a reviewer runs, or a question about its verdict is open, the project is `reviewing` and does not end. Returns True
        when the project must not end now."""
        if not self.settings.reviewer_on or self.tasks is None:
            return False
        open_review = any(a.request.get("kind") == "review" for a in self.store.approvals(project_id, status="open"))
        rows = tx.conn.execute("SELECT * FROM agent_nodes WHERE project_id = ? AND role <> 'planner' ORDER BY created_at, rowid", (project_id,)).fetchall()
        workers = [r for r in rows if r["role"] == "worker"]
        reviewers = [r for r in rows if r["role"] == "reviewer"]
        if open_review or any(r["state"] not in NODE_FINAL for r in reviewers):
            return True
        project = tx.conn.execute("SELECT request_id, review_loops FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not workers or any(r["state"] not in NODE_FINAL for r in workers) or not any(r["state"] == "done" for r in workers) or len(reviewers) >= 1 + int(project["review_loops"]):
            return False
        done = [r for r in workers if r["state"] == "done" and r["task_id"]]
        level = "edit" if any(json.loads(r["grants_json"] or "{}").get("folder") == "edit" for r in done) else "read"        # the strongest level among the steps it reviews (D305 a)
        from sutra_app.orchestrator.grants import StepRequest, resolve
        node_id = self.ids.node_id()
        grant = resolve("reviewer", StepRequest(id="review"), level, self.service._owner_access()).grant.for_node(self.ids.grant_id(), node_id)
        first = tx.conn.execute("SELECT dept_id, title FROM tasks WHERE id = ?", (done[0]["task_id"],)).fetchone()
        title = tx.conn.execute("SELECT title FROM projects WHERE id = ?", (project_id,)).fetchone()["title"] or "the project"
        try:
            task = self.tasks.create(tx, dept_id=first["dept_id"], text=f"Check the work of: {title}", title="Review", depends_on=[r["task_id"] for r in done], request=project["request_id"])
        except AppError:                                                     # the team is gone: no review, the project ends as it would have
            return False
        tx.conn.execute("UPDATE tasks SET lane = (SELECT lane FROM tasks WHERE id = ?) WHERE id = ?", (done[0]["task_id"], task.id))     # the reviewer is in the lane of the first step it checks (PB-5)
        tx.conn.execute("INSERT INTO agent_nodes(id, project_id, task_id, role, runtime, plan_ref, depends_on, state, grants_json, writes_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (node_id, project_id, task.id, "reviewer", "light", "review", json.dumps([r["id"] for r in done]), "planned", json.dumps(grant.to_json(), sort_keys=True), "[]", tx.now()))
        pick, independent = self._reviewer_connector(tx, [r["task_id"] for r in done])
        tx.conn.execute("UPDATE projects SET status = 'reviewing', caps_json = json_set(caps_json, '$.reviewer_connector', ?, '$.reviewer_independent', ?) WHERE id = ?", (pick, 1 if independent else 0, project_id))
        self.store.audit(tx, actor="gatekeeper", action="grant.issued", project_id=project_id, node_id=node_id, role="reviewer", tier=max(grant.tiers), decision="allow", reason=grant.describe(), target=first["dept_id"], ref=grant.id)
        self.store.audit(tx, actor="conductor", action="review.started", project_id=project_id, node_id=node_id, role="reviewer", decision="n/a",
                         reason="independent of the builders" if independent else "not independent of the builders", ref=task.id)
        self.sync_task(tx, task.id)
        tx.emit("project.updated", {"project_id": project_id, "status": "reviewing"})
        return True

    def _reviewer_connector(self, tx: Tx, task_ids: list[str]) -> tuple[str, bool]:
        """The connector the reviewer should use: one that did NOT build the work (the usage ledger says which providers did), when another is installed and signed in; else `` (the router picks) and
        the review says it is not independent. A model that checks its own work is not a second opinion, so the page and the card say so."""
        marks = ",".join("?" * len(task_ids))
        built = {r[0] for r in tx.conn.execute(f"SELECT DISTINCT provider FROM usage_ledger WHERE task_id IN ({marks}) AND provider != 'stub'", task_ids)} if task_ids else set()
        for name in self.service._providers():
            if name not in built:
                return name, True
        return "", False

    def _review_done(self, tx: Tx, node: sqlite3.Row, task_id: str) -> None:
        """The reviewer's run ended well: its `verdict.json` is read (at most 8 KB), checked as a closed typed object, scrubbed and stored as a message of the project; a verdict that is not the typed
        object fails the node. `approve` changes nothing. `changes` and `reject` open ONE question for the owner (kind `review`): nothing is redone unless the owner says so (a model never approves
        a model, and it never orders work either). Decide for me does not answer it."""
        from sutra_app.nodes.reviewer import VERDICT_FILE, VerdictInvalid, check_verdict
        row = self.tasks.store.row_in(tx.conn, task_id)
        try:
            path = self.tasks.store.run_dir_of(row) / VERDICT_FILE
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
                raise VerdictInvalid("there is no verdict file")
            verdict = check_verdict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, VerdictInvalid):
            self.store.audit(tx, actor="conductor", action="verdict.refused", project_id=node["project_id"], node_id=node["id"], role="reviewer", decision="deny", reason="the verdict could not be used", ref=task_id)
            self._fail(tx, node, "its verdict could not be used", retry=False)
            return
        posted = self.store.post(tx, project_id=node["project_id"], kind="verdict", src_ref=f"verdict:{node['id']}:{node['attempt']}", body=verdict, from_node=node["id"], to_node="project")
        self.store.audit(tx, actor="conductor", action="verdict.received", project_id=node["project_id"], node_id=node["id"], role="reviewer", decision="allow" if verdict["verdict"] == "approve" else "ask",
                         reason=verdict["verdict"], ref=str(posted.seq))
        self._teardown(tx, node, "done", "")
        if verdict["verdict"] != "approve":
            loops = tx.conn.execute("SELECT review_loops FROM projects WHERE id = ?", (node["project_id"],)).fetchone()[0]
            cap = int(json.loads(tx.conn.execute("SELECT caps_json FROM projects WHERE id = ?", (node["project_id"],)).fetchone()[0] or "{}").get("review_loops") or NODE_DEFAULT_CAPS["review_loops"] or 2)
            if int(loops) >= cap:                                            # the loop cap: no more going back; the owner is told, and the project ends as it is
                self.store.audit(tx, actor="conductor", action="review.loop_cap", project_id=node["project_id"], node_id=node["id"], role="reviewer", decision="deny", reason="the work went back twice already")
                self._note(tx, node["project_id"], "The reviewer still asks for changes after two tries, so I stopped there. Open the project to read what it said.", f"project:{node['project_id']}#review-cap")
            else:
                independent = bool(json.loads(tx.conn.execute("SELECT caps_json FROM projects WHERE id = ?", (node["project_id"],)).fetchone()[0] or "{}").get("reviewer_independent"))      # the Conductor's own fact from the usage ledger (G25, D338 a)
                asked = self.store.open_approval(tx, project_id=node["project_id"], node_id="", tier=1, client_id=f"review:{node['id']}:{node['attempt']}",
                                                 expires_at=tx.now() + int(NODE_DEFAULT_CAPS["approval_expiry_s"] or 86400),
                                                 request={"kind": "review", "verdict": verdict["verdict"], "summary": verdict["summary"][:200], "refs": verdict["needs_work"], "independent": independent})
                self.store.audit(tx, actor="gatekeeper", action="gate.asked", project_id=node["project_id"], node_id=node["id"], tier=1, decision="ask", reason=f"the reviewer says {verdict['verdict']}", ref=asked.id)
                self.service.sync_cards(tx, node["project_id"])

    def send_back(self, tx: Tx, project_id: str, refs: list[str]) -> int:
        """The owner said yes to the reviewer's `changes`: each step the verdict names gets a fresh attempt (one for each loop, at most the project's cap), and the project runs again; the reviewer
        looks once more when they are done. Returns how many steps went back."""
        tx.conn.execute("UPDATE projects SET review_loops = review_loops + 1, status = 'running' WHERE id = ?", (project_id,))
        went = 0
        for ref in refs:
            node = tx.conn.execute("SELECT * FROM agent_nodes WHERE project_id = ? AND plan_ref = ? AND role = 'worker' AND state = 'done'", (project_id, ref)).fetchone()
            if node is None:
                continue
            try:
                with tx.savepoint():
                    self._retry(tx, node, "the reviewer asked for changes", action="node.rework")
                went += 1
            except AppError:
                continue
        if not went:                                                         # nothing could go back: the project ends as it is
            self._sync_project(tx, project_id)
        return went

    def _fail_without_grant(self, tx: Tx, project_id: str) -> None:
        """G3 (D310, D302): a node whose task waits and whose grant is missing, unreadable, too wide for its role or not its own is held by the gate for ever, and the project would hang. The tick fails it:
        an audit row `grant.denied` (fixed words, nothing from the grant), the node `failed` with no retry (a second attempt has the same grant), its task cancelled, the failure policy applies."""
        if self.tasks is None:
            return
        for node in tx.conn.execute(
                "SELECT n.* FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND n.state IN ('planned','queued','awaiting_approval','awaiting_system') "
                "AND t.status IN ('blocked','queued') ORDER BY n.created_at, n.rowid", (project_id,)).fetchall():
            try:
                node_block_of(tx.conn, node["task_id"])
                continue
            except NodeBlockError:
                pass
            self.store.audit(tx, actor="conductor", action="grant.denied", project_id=project_id, node_id=node["id"], role=node["role"], decision="deny",
                             reason="this step has no permissions set", ref=node["task_id"])
            self._fail(tx, node, "it had no permissions set", retry=False)
            self.tasks.cancel_in(tx, node["task_id"], "cancelled: this step has no permissions set")       # the node is final already: the task's end changes nothing more
            tx.emit("node.updated", {"project_id": project_id, "node_id": node["id"], "state": "failed"})
            self._sync_project(tx, project_id)

    async def refuse_open_gates(self, project_id: str, reason: str) -> int:
        """D296: every open gate of the project counts as refused. The questions are answered `denied` (by the system), the nodes that waited for them are `cancelled` with the reason, the project
        is `stopped`, one receipt line says why, and the nodes that run are stopped through the ladder together. Returns how many nodes it ended. The decision and the stop are ONE transaction
        (`_refuse_in`), so a crash cannot leave a project that was refused but not stopped (MJ7)."""
        def settle() -> int:
            with self.db.tx() as tx:
                return self._refuse_in(tx, project_id, reason)
        ended = await run_blocking(settle)
        ended += await self._stop_nodes(project_id, reason, "system")
        return ended

    def _review_as_no(self, tx: Tx, project_id: str, why: str) -> int:
        """PB-3 (D330, D345): a question about the reviewer's verdict is advice, not a gate: when it is refused, ran out, or met a sleep or a restart, it counts as the owner's no, which is "the project
        ends as it is" (the work is finished). The question is answered `denied` by the system, one audit row says why, and the project ends by its steps. Returns how many questions it closed."""
        closed = 0
        for approval in self.store.approvals(project_id, status="open"):
            if approval.request.get("kind") == "review":
                self.store.decide(tx, approval.id, "deny", decided_by="system")
                self.store.audit(tx, actor="system", action=GATE_REFUSED_ACTION, project_id=project_id, node_id=approval.node_id or None, tier=approval.tier, decision="deny", reason=why, ref=approval.id)
                closed += 1
        if closed:
            self._sync_project(tx, project_id)
            self.service.sync_cards(tx, project_id)
        return closed

    def _refuse_in(self, tx: Tx, project_id: str, reason: str) -> int:
        """The database part of the D296 refusal, inside the caller's transaction: the open questions denied, the project stopped, the nodes that had not started cancelled, the receipt. The nodes
        that run are stopped by the caller after the commit (`_stop_nodes`). 0 when the project is over already."""
        status = tx.conn.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        if status is None or status["status"] in PROJECT_FINAL:
            return 0
        open_now = self.store.approvals(project_id, status="open")
        if open_now and all(a.request.get("kind") == "review" for a in open_now) and status["status"] == "reviewing":
            self._review_as_no(tx, project_id, reason)                          # only the reviewer's advice was open: the project ends as it is, it is not stopped (PB-3)
            return 0
        for approval in open_now:
            self.store.decide(tx, approval.id, "deny", decided_by="system")
            self.store.audit(tx, actor="system", action=GATE_REFUSED_ACTION, project_id=project_id, node_id=approval.node_id or None, tier=approval.tier, decision="deny",
                             reason=reason, ref=approval.id)
        tx.conn.execute("UPDATE projects SET status = 'stopped', ended_at = ?, stop_reason = ? WHERE id = ?", (tx.now(), self.store.clean(reason), project_id))
        self.store.audit(tx, actor="system", action=PROJECT_STOPPED_ACTION, project_id=project_id, decision="n/a", reason=reason)
        cancelled = 0
        self._end_held(tx, project_id, reason)
        for node in tx.conn.execute("SELECT n.id AS id, n.task_id AS task_id, n.state AS state, t.status AS tstatus FROM agent_nodes n LEFT JOIN tasks t ON t.id = n.task_id "
                                    "WHERE n.project_id = ? AND n.role <> 'planner' AND n.state NOT IN ('done','failed','cancelled')", (project_id,)).fetchall():
            if node["task_id"] and node["tstatus"] in ("blocked", "queued"):
                self.tasks.cancel_in(tx, node["task_id"], reason)
                cancelled += 1
            elif not node["task_id"]:
                tx.conn.execute("UPDATE agent_nodes SET state = 'cancelled', failure_reason = ?, ended_at = ?, torn_down_at = ? WHERE id = ?", (self.store.clean(reason), tx.now(), tx.now(), node["id"]))
                cancelled += 1
        self._receipt(tx, project_id, reason)
        self.service.sync_cards(tx, project_id)
        tx.emit("project.updated", {"project_id": project_id, "status": "stopped"})
        return cancelled

    def _late_permission(self, tx: Tx, node: sqlite3.Row, outcome: str) -> None:
        """A node that ended on a refusal of the computer (EPERM, WinError 5: a permission the probe could not see) did not fail: it needs a permission. It ends `failed` with that reason, is not
        retried (it would be refused again), and ONE card asks the owner (a system question of the project, once, by its client id); the audit says `system.late_denied`."""
        self.store.audit(tx, actor="conductor", action="system.late_denied", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny", reason="your computer did not allow it",
                         ref=node["task_id"] or "")
        asked = self.store.open_approval(tx, project_id=node["project_id"], node_id=node["id"], tier=2,
                                         request={"kind": "system", "item": "unknown", "level": "write", "late": 1, "nodes": [node["id"]]},
                                         expires_at=tx.now() + int(NODE_DEFAULT_CAPS["approval_expiry_s"] or 86400), client_id=f"system:late:{node['project_id']}")
        if not asked.duplicate:
            self.store.audit(tx, actor="gatekeeper", action="system.asked", project_id=node["project_id"], node_id=node["id"], tier=2, decision="ask", reason="late: the computer refused a file", ref=asked.id)
            self._note(tx, node["project_id"], "A step could not use your files because your computer did not allow it. Open the project to see what to allow.", f"project:{node['project_id']}#late")
            self.service.sync_cards(tx, node["project_id"])
        self._fail(tx, node, NEEDS_SYSTEM_PERMISSION, retry=False)
        tx.emit("node.updated", {"project_id": node["project_id"], "node_id": node["id"], "state": "failed"})
        self._sync_project(tx, node["project_id"])

    def restart_after_permission(self, tx: Tx, node_id: str) -> bool:
        """P3 (D322 g): after the late permission card was cleared, the node that ended with the computer refusing a file gets ONE fresh attempt, as a new task of the same node, that does not spend its
        retry (the D314 mechanism: audit `node.restarted`). Once for each node; never for a node whose project has ended. Returns True when it started one."""
        node = tx.conn.execute("SELECT * FROM agent_nodes WHERE id = ?", (node_id,)).fetchone()
        if node is None or node["state"] != "failed" or node["failure_reason"] != NEEDS_SYSTEM_PERMISSION or not node["task_id"] or self.tasks is None:
            return False
        project = tx.conn.execute("SELECT status FROM projects WHERE id = ?", (node["project_id"],)).fetchone()
        if project is None or project["status"] in PROJECT_FINAL:
            return False
        if tx.conn.execute("SELECT 1 FROM node_audit WHERE node_id = ? AND action = 'node.restarted' AND reason = ?", (node_id, PERMISSION_RESTART)).fetchone() is not None:
            return False
        try:
            with tx.savepoint():
                self._retry(tx, node, PERMISSION_RESTART, action="node.restarted")
        except AppError:                                                     # the team is gone: the node stays failed
            return False
        return True

    def _note(self, tx: Tx, project_id: str, text: str, src_ref: str) -> None:
        """A plain note in the org chat about a project (once, by its `src_ref`): a trigger that ended a step or the project says so (D311: a note, not a card)."""
        if self.chats is None:
            return
        from sutra_app.library.gate import GATE
        from sutra_app.orchestrator.ids import ORG_SESSION_ID
        title = tx.conn.execute("SELECT title FROM projects WHERE id = ?", (project_id,)).fetchone()["title"]
        full = f"Project \u201c{title}\u201d: {text}" if title else text
        payload = dict(kind="note", session_id=ORG_SESSION_ID, role="agent", who="sutra", text=full[:2000], src_ref=src_ref, at=tx.now())
        self.chats.post(tx, ORG_SESSION_ID, GATE.check("chat_message", payload, ctx=tx.ctx))

    def _receipt(self, tx: Tx, project_id: str, reason: str) -> None:
        """The one line in the org chat that says why a project stopped by itself (D296). A plain note, once (by its `src_ref`)."""
        if self.chats is None:
            return
        from sutra_app.library.gate import GATE
        from sutra_app.orchestrator.ids import ORG_SESSION_ID
        title = tx.conn.execute("SELECT title FROM projects WHERE id = ?", (project_id,)).fetchone()["title"]
        text = f"I stopped the project \u201c{title}\u201d: {reason}. Start it again when you are back." if title else f"I stopped a project: {reason}."
        payload = dict(kind="note", session_id=ORG_SESSION_ID, role="agent", who="sutra", text=text[:2000], src_ref=f"project:{project_id}#stopped", at=tx.now())
        self.chats.post(tx, ORG_SESSION_ID, GATE.check("chat_message", payload, ctx=tx.ctx))

    async def reconcile_projects(self) -> dict[str, int]:
        """Run once at start, after `reconcile` has settled the tasks and before anything starts (D277, D296). A project with an open gate was left open by a closed app: every gate is refused
        ("Sutra was closed before you answered"). The nodes follow their tasks (a task `reconcile` crashed gives a node that is retried); a node that was reserved but never got its task
        (the request was cut off) is cancelled; the lease of every live node starts again from now. It never starts a task."""
        def settle() -> tuple[list[str], int]:
            refused: list[str] = []
            fixed = 0
            with self.db.tx() as tx:
                for project in tx.conn.execute("SELECT id FROM projects WHERE status IN ('planning','awaiting_approval','running','reviewing') ORDER BY created_at").fetchall():
                    gate_open = tx.conn.execute("SELECT 1 FROM approvals WHERE project_id = ? AND status = 'open' AND request_json NOT LIKE '%\"late\":1%'", (project["id"],)).fetchone() is not None
                    if gate_open:
                        refused.append(project["id"])
                        continue
                    for node in tx.conn.execute("SELECT id, task_id, state, role FROM agent_nodes WHERE project_id = ? AND role <> 'planner' AND state NOT IN ('done','failed','cancelled')",
                                                (project["id"],)).fetchall():
                        if node["task_id"] is None:
                            tx.conn.execute("UPDATE agent_nodes SET state = 'cancelled', failure_reason = 'the request was cut off before its task was made', ended_at = ?, torn_down_at = ? WHERE id = ?",
                                            (tx.now(), tx.now(), node["id"]))
                            fixed += 1
                        else:
                            self.sync_task(tx, node["task_id"])
                    lease = int(json.loads(tx.conn.execute("SELECT caps_json FROM projects WHERE id = ?", (project["id"],)).fetchone()["caps_json"] or "{}").get("lease_s") or 90)
                    tx.conn.execute("UPDATE agent_nodes SET last_beat_at = ?, lease_expires_at = ? WHERE project_id = ? AND state IN ('leased','running')", (tx.now(), tx.now() + lease, project["id"]))
                    self._sync_project(tx, project["id"])
            return refused, fixed
        refused, fixed = await run_blocking(settle)
        for project_id in refused:
            await self.refuse_open_gates(project_id, GATE_REFUSED_CLOSED)
        return {"refused": len(refused), "cancelled": fixed}

    def start_ticking(self, interval: float = 5.0) -> None:
        """Run `tick` every `interval` seconds on the running loop. Idempotent."""
        import asyncio
        if self._ticker is not None and not self._ticker.done():
            return

        async def loop() -> None:
            while True:
                try:
                    await self.tick()
                except asyncio.CancelledError:
                    raise
                except Exception:                         # noqa: BLE001  (a bad look must not end the tick)
                    log.exception("the project tick failed")
                await asyncio.sleep(interval)
        self._ticker = asyncio.get_running_loop().create_task(loop())

    async def stop_ticking(self) -> None:
        import asyncio
        ticker, self._ticker = self._ticker, None
        if ticker is not None:
            ticker.cancel()
            try:
                await ticker
            except (asyncio.CancelledError, Exception):         # noqa: BLE001
                pass

    # ---- stopping (D303) ------------------------------------------------------------------------------------------------------------

    async def stop(self, project_id: str, *, by: str = "owner", reason: str = "stopped by you") -> int:
        """Stop a project: it becomes `stopped` first (so the gate holds everything), its planner call ends, every live node goes through the stop ladder together, its queued and blocked
        nodes are cancelled, and nothing starts by itself afterwards. Returns how many nodes it stopped or cancelled. 404 for a project that does not exist."""
        found = await run_blocking(self._project_row, project_id)
        if found is None:
            raise NotFound("that project")
        if found["status"] in PROJECT_FINAL:
            return 0
        await run_blocking(self._mark_stopped, project_id, reason, by)
        if found["request_id"]:
            await run_blocking(self.stop_planners, found["request_id"])
        return await self._stop_nodes(project_id, reason, by)

    def begin_kill(self, reason: str) -> list[str]:
        """The kill switch ends every project that has a live or waiting node (D303 d). First step: they become `stopped` (so the gate holds everything and a node that ends is not counted as a
        failed project); returns their ids. The nodes are stopped next (`NodeControl`), then `finish_kill` cancels what had not started."""
        ids = self._projects_with_open_nodes()
        for project_id in ids:
            self._mark_stopped(project_id, reason, "system")
        return ids

    async def finish_kill(self, project_ids: Sequence[str], reason: str) -> int:
        """Last step of a kill: the queued and blocked nodes of those projects are cancelled, so nothing starts by itself after resume (D303 d). Returns how many it cancelled."""
        return sum([await self._stop_nodes(project_id, reason, "system") for project_id in project_ids])

    def _projects_with_open_nodes(self) -> list[str]:
        rows = self.db.conn().execute(
            "SELECT DISTINCT p.id FROM projects p JOIN agent_nodes n ON n.project_id = p.id JOIN tasks t ON t.id = n.task_id "
            "WHERE p.status NOT IN ('done','done_with_open_items','stopped','failed') AND t.status IN ('blocked','queued','starting','running','waiting_user') ORDER BY p.created_at").fetchall()
        return [r["id"] for r in rows]

    def _end_held(self, tx: Tx, project_id: str, reason: str) -> None:
        """PB-10: a step held for a scope question has no live task (its run is over), so no stop path reaches it; when the project ends it ends too: `cancelled`, with the reason, nothing handed on."""
        now = tx.now()
        tx.conn.execute("UPDATE agent_nodes SET state = 'cancelled', failure_reason = ?, ended_at = ?, torn_down_at = ? WHERE project_id = ? AND state = 'awaiting_approval' "
                        "AND task_id IN (SELECT id FROM tasks WHERE status NOT IN ('blocked','queued','starting','running','waiting_user'))", (self.store.clean(reason), now, now, project_id))

    def _mark_stopped(self, project_id: str, reason: str, by: str) -> None:
        with self.db.tx() as tx:
            changed = tx.conn.execute("UPDATE projects SET status = 'stopped', ended_at = ?, stop_reason = ? WHERE id = ? AND status NOT IN ('done','done_with_open_items','stopped','failed')",
                                      (tx.now(), self.store.clean(reason), project_id)).rowcount
            if changed:
                actor = "owner" if by == "owner" else "system"
                for approval in self.store.approvals(project_id, status="open"):          # a stopped project asks nothing: its open questions are answered no (MJ7)
                    self.store.decide(tx, approval.id, "deny", decided_by=actor)
                    self.store.audit(tx, actor=actor, action="approval.denied" if actor == "owner" else GATE_REFUSED_ACTION, project_id=project_id, node_id=approval.node_id or None,
                                     tier=approval.tier, decision="deny", reason="the project was stopped", ref=approval.id)
                self._end_held(tx, project_id, reason)
                self.store.audit(tx, actor=actor, action="project.stopped", project_id=project_id, decision="n/a", reason=reason)
                self.service.sync_cards(tx, project_id)
                tx.emit("project.updated", {"project_id": project_id, "status": "stopped"})

    async def _stop_nodes(self, project_id: str, outcome: str, by: str = "owner") -> int:
        """The live nodes of the project through the ladder, all together; the ones that have not started are cancelled. `by`: who asked (Minor 2): only the owner's own stop is recorded as theirs."""
        import asyncio
        rows = await run_blocking(lambda: self.db.conn().execute(
            "SELECT n.id AS id, n.task_id AS task_id, t.status AS status FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? "
            "AND t.status IN ('blocked','queued','starting','running','waiting_user')", (project_id,)).fetchall())

        async def one(row: sqlite3.Row) -> int:
            try:
                return 1 if await self.tasks.stop_node(row["task_id"], outcome, by="owner" if by == "owner" else "system") else 0
            except Exception:                         # noqa: BLE001  (one that will not stop must not keep the others)
                log.exception("could not stop node %s", row["id"])
                return 0

        return sum(await asyncio.gather(*(one(row) for row in rows)))

    async def pause(self, project_id: str, *, resume: bool = False) -> ProjectOut:
        """Pause or resume one project: no node of it starts while it is paused; what runs finishes. Resuming lets what waited start."""
        def change() -> None:
            with self.db.tx() as tx:
                found = tx.conn.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
                if found is None:
                    raise NotFound("that project")
                if found["status"] in PROJECT_FINAL:
                    raise AppError("busy", "That project has ended")
                if resume and tx.conn.execute("SELECT 1 FROM approvals WHERE project_id = ? AND status = 'open' AND json_extract(request_json, '$.kind') = 'scope_violation'", (project_id,)).fetchone():
                    raise AppError("busy", "A step changed files nobody gave it. Answer that question first; the project goes on when you do")       # the hold is not the owner's pause (PB-1)
                tx.conn.execute("UPDATE projects SET paused = ? WHERE id = ?", (0 if resume else 1, project_id))
                self.store.audit(tx, actor="owner", action="project.resumed" if resume else "project.paused", project_id=project_id, decision="n/a")
                tx.emit("project.updated", {"project_id": project_id, "paused": not resume})
        await run_blocking(change)
        if resume and self.tasks is not None:
            await self.tasks.start_ready()
        return await run_blocking(self.get, project_id)
