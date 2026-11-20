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

    @staticmethod
    def _stamp(run_dir: Any) -> tuple[int, int, int] | None:
        from pathlib import Path
        try:
            info = (Path(run_dir) / HANDOFF_FILE).lstat()
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

    @staticmethod
    def _beat(tx: Tx, node: sqlite3.Row) -> None:
        now = tx.now()
        tx.conn.execute("UPDATE agent_nodes SET last_beat_at = ?, lease_expires_at = ? + COALESCE(lease_expires_at - last_beat_at, 90) WHERE id = ?", (now, now, node["id"]))

    def _teardown(self, tx: Tx, node: sqlite3.Row, state: str, why: str) -> None:
        """A node ended: its final state, its lease released, the time stamped, one audit row. The run folder stays where it is (D276: nothing the owner could want is deleted)."""
        now = tx.now()
        self._prepared.pop(node["task_id"] or "", None)
        tx.conn.execute("UPDATE agent_nodes SET state = ?, failure_reason = ?, lease_expires_at = NULL, ended_at = ?, torn_down_at = ? WHERE id = ?", (state, why[:200], now, now, node["id"]))
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
            for project in tx.conn.execute("SELECT id, status, caps_json, created_at, budget_usd FROM projects WHERE status IN ('planning','awaiting_approval','running') ORDER BY created_at").fetchall():
                lease_s = int(json.loads(project["caps_json"] or "{}").get("lease_s") or lease_default)
                slept = gap > lease_s // 2
                ran_out = self.store.expire_due(tx, project_id=project["id"], now=now)
                if any(a.request.get("late") for a in ran_out):                      # a late permission question that ran out only ends: the other steps keep their work (m3)
                    self.service.sync_cards(tx, project["id"])
                ran_out = [a for a in ran_out if not a.request.get("late")]
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

    def _refuse_in(self, tx: Tx, project_id: str, reason: str) -> int:
        """The database part of the D296 refusal, inside the caller's transaction: the open questions denied, the project stopped, the nodes that had not started cancelled, the receipt. The nodes
        that run are stopped by the caller after the commit (`_stop_nodes`). 0 when the project is over already."""
        status = tx.conn.execute("SELECT status FROM projects WHERE id = ?", (project_id,)).fetchone()
        if status is None or status["status"] in PROJECT_FINAL:
            return 0
        for approval in self.store.approvals(project_id, status="open"):
            self.store.decide(tx, approval.id, "deny", decided_by="system")
            self.store.audit(tx, actor="system", action=GATE_REFUSED_ACTION, project_id=project_id, node_id=approval.node_id or None, tier=approval.tier, decision="deny",
                             reason=reason, ref=approval.id)
        tx.conn.execute("UPDATE projects SET status = 'stopped', ended_at = ?, stop_reason = ? WHERE id = ?", (tx.now(), self.store.clean(reason), project_id))
        self.store.audit(tx, actor="system", action=PROJECT_STOPPED_ACTION, project_id=project_id, decision="n/a", reason=reason)
        cancelled = 0
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
                for project in tx.conn.execute("SELECT id FROM projects WHERE status IN ('planning','awaiting_approval','running') ORDER BY created_at").fetchall():
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
                tx.conn.execute("UPDATE projects SET paused = ? WHERE id = ?", (0 if resume else 1, project_id))
                self.store.audit(tx, actor="owner", action="project.resumed" if resume else "project.paused", project_id=project_id, decision="n/a")
                tx.emit("project.updated", {"project_id": project_id, "paused": not resume})
        await run_blocking(change)
        if resume and self.tasks is not None:
            await self.tasks.start_ready()
        return await run_blocking(self.get, project_id)
