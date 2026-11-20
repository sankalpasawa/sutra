"""Projects: a request with two or more steps becomes a project, and its nodes are tasks (multi-agent nodes, D253, D255, D257, D259, D267, D302, D303, D305; MAN-5).

    projects = ProjectService(db, store=node_store, ids=ids, clock=clock, settings=settings, owner_access=..., output_of=..., node_control=...)
    reservation = projects.reserve(request_id, title, steps, budget=None)       # BEFORE the tasks exist: one transaction, the plan goes through the Gatekeeper's rules
    projects.link_task(tx, reservation, step_ref, task_id)                      # in the transaction that makes each task: the node and its task are one thing from then on
    tasks.task_gate = projects.gate                                              # the Conductor's gate: the kill switch and the grant first, then the project's own rules
    projects.sync_task(tx, task_row)                                             # after any change of a node's task: node state, lease, teardown, the project's state

A node is a task plus a row of `agent_nodes` (D253). The tasks are made by the chat agent's runner exactly as before (the same `TaskService.create`, the same `depends_on`), so FIFO, the caps
(`SUTRA_MAX_RUNS`, `SUTRA_MAX_LIVE`), one live task per team and `settle_blocked` apply to them with no second queue (D257). What the project adds: an identity and a frozen grant per node, a
parallel cap, a lease, and teardown. The Conductor's code is here because it is one thing with the project rows: `gate` is its task gate, `sync_task` its teardown and the state machine.

The gate holds a node in this order (D303): the kill switch and pause and a missing or unusable grant (`NodeControl.gate`, never replaced), then the project's state (stopped, ended, waiting for the
owner's answer, paused), then the node's own state, then the project's parallel cap. A held node stays `queued` with the sentence as its waiting detail and starts by itself when the reason ends.

The planner (the chat agent's staged call, inline in the server) has a node row too, and a stop token that is kept here while the call runs (D301): node stop, project stop and kill-all ask
`stop_planners`, which ends the running call; pause does not.

With SUTRA_NODES_V1 off none of this is built.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sutra_app.config import NODE_DEFAULT_CAPS, Settings
from sutra_app.connectors.cancel import CancelToken
from sutra_app.orchestrator.db import Database, Tx, run_blocking
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.gatekeeper import Evaluation, Plan, PlanStep, evaluate
from sutra_app.engine.host.handoff import ACCEPTED_FILE
from sutra_app.orchestrator.grants import Grant
from sutra_app.orchestrator.handoff_intake import HandoffRefused, read_handoff, write_accepted
from sutra_app.orchestrator.ids import Clock, IdFactory, SystemClock, iso_z
from sutra_app.orchestrator.models import NodeOut, ProjectOut
from sutra_app.orchestrator.nodes_store import GATE_REFUSED_ACTION, GATE_REFUSED_CLOSED, GATE_REFUSED_SLEEP, PROJECT_STOPPED_ACTION, NodeStore

__all__ = ["ProjectService", "ProjectStep", "Reservation", "default_output_of", "NODE_FINAL", "PROJECT_FINAL", "TASK_TO_NODE"]

log = logging.getLogger(__name__)
NODE_FINAL = ("done", "failed", "cancelled")
PROJECT_FINAL = ("done", "done_with_open_items", "stopped", "failed")
LIVE_NODE_STATES = ("leased", "running", "handing_off")
DEFAULT_SLICE = 100                       # the work credits a team's run starts with (J2_BUDGET): what a step with no estimate counts as (D300)
# a node's state from its task's status (the projector owns this from MAN-5: a node is `cancelled` only when its task ended stopped or was cancelled)
TASK_TO_NODE = {"blocked": "planned", "queued": "queued", "starting": "leased", "running": "running", "waiting_user": "running", "done": "done", "done_with_open_items": "done",
                "crashed": "failed", "stopped": "cancelled", "cancelled": "cancelled"}
HELD_STATES = ("awaiting_approval", "awaiting_system")
LOST_LEASE = "lost its lease: no sign of life"
APP_CLOSED = "the app was closed"


@dataclass(frozen=True)
class ProjectStep:
    """One step of a request as the project sees it: the plan's own id (`ref`, the chat agent's a1, a2 ...), the team, the steps it waits for, and the planner's estimate (0: none)."""

    ref: str
    dept_id: str
    depends_on: tuple[str, ...] = ()
    estimate_credits: int = 0


@dataclass(frozen=True)
class Reservation:
    """What `reserve` made. `nodes` maps a step's ref to its node id. `ok` is False when the Gatekeeper refused the plan (`why` says in words; no node was made and the caller makes no task)."""

    project_id: str
    ok: bool = True
    why: str = ""
    nodes: dict[str, str] = field(default_factory=dict)
    planner_node_id: str = ""


def default_output_of(data_dir: Any) -> Callable[[str], Any]:
    """The output spec of a team as far as it is known BEFORE a run: its engine setting `output` when that names a type (`engine.json` of the team, then the global one); `auto` is chosen
    by the engine per run, so it is not known here and counts as `read` (the conservative reading: nothing in the owner's folder beyond reading; D299 says the grant describes, it does not
    enforce). Anything that cannot be read is None (`read`)."""
    from pathlib import Path

    def output_of(dept_id: str) -> Any:
        try:
            from sutra_app.engine.spec import read_settings_file
            for path in (Path(data_dir) / "departments" / dept_id / "engine.json", Path(data_dir) / "engine.json"):
                found = read_settings_file(path) or {}
                name = found.get("output")
                if isinstance(name, str) and name != "auto":
                    from sutra_app.engine.capabilities.base import output_spec
                    return output_spec(name)
        except Exception:                                   # noqa: BLE001  (an unreadable setting is "not known": read)
            return None
        return None

    return output_of


class ProjectService:
    def __init__(self, db: Database, *, store: NodeStore, ids: IdFactory | None = None, clock: Clock | None = None, settings: Settings,
                 owner_access: Callable[[], str] | None = None, output_of: Callable[[str], Any] | None = None, node_control: Any = None, tasks: Any = None, chats: Any = None) -> None:
        self.db = db
        self.store = store
        self.ids = ids or IdFactory()
        self._clock = clock or SystemClock()
        self.settings = settings
        self._owner_access = owner_access or (lambda: "none")
        self._output_of = output_of or (lambda dept: None)
        self.control = node_control
        self.tasks = tasks
        self.chats = chats                                                        # the org chat's store: where the receipt of a stopped project is written (MAN-7)
        self._pending: list[tuple[str, str]] = []                                # (project id, reason): stops that were decided inside a transaction and are run by the next tick
        self._last_tick: int | None = None
        self._extended: dict[str, int] = {}                                       # node id -> the moment its lease was extended (once) for a sleeping computer
        self._ticker: Any = None
        self._planners: dict[str, tuple[str, CancelToken]] = {}          # request id -> (the planner's node id, its stop token)
        self._lock = threading.Lock()

    # ---- the planner (D291, D301) ---------------------------------------------------------------------------------------------------

    def planner_for(self, request_id: str) -> tuple[str, CancelToken]:
        """The planner's node id and stop token for one request, made when planning starts and kept until `release_planner`. The same pair on a second call (a stale plan is planned again)."""
        with self._lock:
            found = self._planners.get(request_id)
            if found is None:
                found = self._planners[request_id] = (self.ids.node_id(), CancelToken())
            return found

    def release_planner(self, request_id: str) -> None:
        with self._lock:
            self._planners.pop(request_id, None)

    def planner_id_of(self, request_id: str) -> str:
        with self._lock:
            found = self._planners.get(request_id)
        return found[0] if found is not None else ""

    def stop_planners(self, request_id: str | None = None) -> int:
        """Stop the planner calls that are running (all, or the one of `request_id`): the token is requested and the cancel ladder runs on the bound process (up to 12 s, so this blocks:
        call it on a worker thread). Returns how many tokens were requested."""
        with self._lock:
            tokens = [token for rid, (_, token) in self._planners.items() if request_id is None or rid == request_id]
        for token in tokens:
            token.request()
        for token in tokens:
            token.cancel_bound()
        return len(tokens)

    # ---- planning: the Gatekeeper's rules, then the rows ---------------------------------------------------------------------------

    def reserve(self, request_id: str, title: str, steps: Sequence[ProjectStep], *, budget: int | None = None, decide_for_me: bool = False,
                planner_node_id: str = "") -> Reservation | None:
        """Make the project and its nodes for a request, before its tasks exist (the tasks are linked as they are made: `link_task`). None when this is not a project: fewer than two steps (D255:
        a one-step request keeps today's path). The plan goes through `gatekeeper.evaluate`; a refused plan makes a project that is `failed` and no node. A plan that needs the owner (a question
        about a tier above the defaults, a wide scope, or an estimate over the confirm threshold) makes the project `awaiting_approval` with its questions stored as approvals; nothing starts until
        they are answered (MAN-8) or run out (MAN-7). One transaction."""
        if len(steps) < 2:
            return None
        slice_credits = budget if budget is not None else DEFAULT_SLICE
        plan = Plan(
            steps=tuple(PlanStep(id=step.ref, role="worker", depends_on=tuple(step.depends_on), output=self._output_of(step.dept_id),
                                 estimate_credits=step.estimate_credits or slice_credits) for step in steps),
            owner_access=self._owner_access(), confirm_credits=None if budget is not None else int(NODE_DEFAULT_CAPS["confirm_credits"] or 500))
        evaluation = evaluate(plan)
        with self.db.tx() as tx:
            if tx.conn.execute("SELECT id FROM projects WHERE request_id = ?", (request_id,)).fetchone() is not None:
                found = tx.conn.execute("SELECT id FROM projects WHERE request_id = ?", (request_id,)).fetchone()
                nodes = {r["plan_ref"]: r["id"] for r in tx.conn.execute("SELECT id, plan_ref FROM agent_nodes WHERE project_id = ? AND role = 'worker'", (found["id"],))}
                return Reservation(found["id"], True, "", nodes)                       # a request planned again (stale chart) finds its project
            return self._reserve(tx, request_id, title, steps, plan, evaluation, budget, decide_for_me, planner_node_id)

    def _reserve(self, tx: Tx, request_id: str, title: str, steps: Sequence[ProjectStep], plan: Plan, evaluation: Evaluation, budget: int | None, decide_for_me: bool,
                 planner_node_id: str) -> Reservation:
        now = tx.now()
        project_id = self.ids.project_id()
        caps = {key: value for key, value in NODE_DEFAULT_CAPS.items()}
        if budget is not None:
            caps["confirm_credits"] = None                                           # the owner's own number is the answer (D300)
        caps["conflict_edges"] = [list(edge) for edge in evaluation.conflicts]     # kept for the lanes package (MAN-10): a delay, never a cancel (D259)
        status = "failed" if not evaluation.ok else "awaiting_approval" if evaluation.gates else "running"
        why = "; ".join(refusal.why for refusal in evaluation.refusals)[:200]
        tx.conn.execute(
            "INSERT INTO projects(id, request_id, title, status, decide_for_me, caps_json, budget_credits, created_at, ended_at, stop_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, request_id, " ".join(title.split())[:200], status, 1 if decide_for_me else 0, json.dumps(caps, sort_keys=True), budget, now,
             now if status == "failed" else None, why if status == "failed" else ""))
        self.store.audit(tx, actor="system", action="project.created", project_id=project_id, decision="n/a", reason=f"{len(steps)} steps", ref=request_id)
        if planner_node_id:
            tx.conn.execute("INSERT INTO agent_nodes(id, project_id, role, runtime, state, created_at, ended_at) VALUES (?,?,?,?,?,?,?)",
                            (planner_node_id, project_id, "planner", "inline", "done", now, now))
        if not evaluation.ok:
            self.store.audit(tx, actor="gatekeeper", action="plan.refused", project_id=project_id, decision="deny", reason=why)
            tx.emit("project.created", {"project_id": project_id, "status": "failed"})
            return Reservation(project_id, False, why or "the plan was refused")
        node_ids = {step.ref: self.ids.node_id() for step in steps}
        for step in steps:
            node_id = node_ids[step.ref]
            grant = evaluation.grants[step.ref].for_node(self.ids.grant_id(), node_id)
            writes = list(grant.scope)
            state = "awaiting_approval" if evaluation.gates else "planned"
            tx.conn.execute(
                "INSERT INTO agent_nodes(id, project_id, role, runtime, plan_ref, depends_on, state, grants_json, writes_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (node_id, project_id, "worker", "engine", step.ref, json.dumps([node_ids[d] for d in step.depends_on if d in node_ids]), state,
                 json.dumps(grant.to_json(), sort_keys=True), json.dumps(writes), now))
            self.store.audit(tx, actor="gatekeeper", action="grant.issued", project_id=project_id, node_id=node_id, role="worker", tier=max(grant.tiers), decision="allow",
                             reason=grant.describe(), target=step.dept_id, ref=grant.id)
            for denial_step, denial in evaluation.denied:
                if denial_step == step.ref:
                    self.store.audit(tx, actor="gatekeeper", action="grant.denied", project_id=project_id, node_id=node_id, role="worker", tier=denial.tier, decision="deny",
                                     reason=denial.why, target=step.dept_id)
        expires = now + int(NODE_DEFAULT_CAPS["approval_expiry_s"] or 86400)
        for gate in evaluation.gates:                                                  # the questions are rows; the cards and the answers are MAN-8
            tier = gate.tier if gate.tier is not None else 5
            asked = self.store.open_approval(tx, project_id=project_id, node_id=node_ids.get(gate.step_id or "", ""), tier=tier, expires_at=expires,
                                             request={"kind": gate.kind, "why": gate.why})
            self.store.audit(tx, actor="gatekeeper", action="gate.asked", project_id=project_id, node_id=node_ids.get(gate.step_id or "", None), tier=tier, decision="ask",
                             reason=gate.why, ref=asked.id)
        self.store.audit(tx, actor="gatekeeper", action="plan.accepted", project_id=project_id, decision="allow", reason=f"{len(steps)} steps, {len(evaluation.gates)} question(s)")
        tx.emit("project.created", {"project_id": project_id, "status": status})
        return Reservation(project_id, True, "", node_ids, planner_node_id)

    def link_task(self, tx: Tx, reservation: Reservation, step_ref: str, task_id: str) -> None:
        """In the transaction that makes the task: tie the node of `step_ref` to it. From then on the task is a node (the gate sees it)."""
        node_id = reservation.nodes.get(step_ref)
        if node_id is None:
            return
        tx.conn.execute("UPDATE agent_nodes SET task_id = ? WHERE id = ? AND task_id IS NULL", (task_id, node_id))
        self.sync_task(tx, task_id)

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
        running = conn.execute("SELECT count(*) FROM agent_nodes WHERE project_id = ? AND state IN ('leased','running','handing_off')", (node["project_id"],)).fetchone()[0]
        if running >= limit:
            return f"Waiting for a free slot in this project ({limit} at a time)"
        return ""

    def on_starting(self, tx: Tx, row: Any) -> None:
        """`TaskService.on_task_starting`, in the transaction that marks the task `starting`: the lease is taken (this node holds its slot until `last_beat_at + lease_s`), so two starts cannot
        both take the last slot."""
        self.sync_task(tx, row.id)

    # ---- the state machine and teardown ---------------------------------------------------------------------------------------------

    def sync_task(self, tx: Tx, task_id: str) -> None:
        """After any change of a node's task: the node's state from the task's status, its lease and teardown, then the project's state. Never moves a node back out of a final state."""
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
        elif want == "cancelled" and outcome.startswith(APP_CLOSED):
            want = "failed"                                                  # the app was closed under the node: nothing the owner asked for, so it is retried, not cancelled
            outcome = "the app was closed while it ran"
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

    def _hand_off(self, tx: Tx, node: sqlite3.Row, task_id: str) -> None:
        """The Conductor's intake (D263, D281; MAN-6): the node's task ended well, so its `handoff.json` is read and checked (`handoff_intake`), scrubbed, stored as a message of the project
        (`handoff:<node>:<attempt>`, once) and written as `handoff.accepted.json`, the one file dependants are given. A missing, malformed, too big or untrue hand-off ends the node `failed` with
        the rule that broke, and an audit row `handoff.refused`; the node's own files stay for the owner (retry is MAN-7)."""
        tx.conn.execute("UPDATE agent_nodes SET state = 'handing_off' WHERE id = ?", (node["id"],))
        row = self.tasks.store.row_in(tx.conn, task_id)
        try:
            run_dir = self.tasks.store.run_dir_of(row)
            accepted = read_handoff(run_dir, node["id"], node["runtime"], self.store.redact)
            write_accepted(run_dir, accepted)
            posted = self.store.post(tx, project_id=node["project_id"], kind="handoff", src_ref=f"handoff:{node['id']}:{node['attempt']}", body=accepted.document,
                                     from_node=node["id"], to_node="project", file=ACCEPTED_FILE)
        except HandoffRefused as refused:
            self.store.audit(tx, actor="conductor", action="handoff.refused", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny", reason=str(refused),
                             ref=task_id)
            self._fail(tx, node, f"hand-off refused: {refused}")
            return
        except OSError:
            self.store.audit(tx, actor="conductor", action="handoff.refused", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny",
                             reason="the hand-off could not be stored", ref=task_id)
            self._fail(tx, node, "hand-off refused: it could not be stored")
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

    def _fail(self, tx: Tx, node: sqlite3.Row, why: str) -> None:
        """A node failed (its task crashed, it lost its lease, its hand-off was refused). It is retried once, as a new attempt of the same node, if the project still runs; else it is `failed`
        and the project's failure policy applies. A node the owner or the kill switch stopped never comes here (it is `cancelled`)."""
        project = tx.conn.execute("SELECT status, failure_policy, caps_json FROM projects WHERE id = ?", (node["project_id"],)).fetchone()
        caps = json.loads(project["caps_json"] or "{}")
        retries = int(caps.get("retries") if caps.get("retries") is not None else NODE_DEFAULT_CAPS["retries"] or 1)
        if project["status"] in ("running",) and node["attempt"] <= retries and self.tasks is not None and node["task_id"]:
            self._retry(tx, node, why)
            return
        self._teardown(tx, node, "failed", why)
        if why.startswith(LOST_LEASE) and node["attempt"] >= 2:                 # D303 e: a node that loses its lease twice stops the project and says so
            self.store.audit(tx, actor="conductor", action="trigger.lease_lost", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="deny",
                             reason="lost its lease twice", ref=node["task_id"] or "")
            self._pending.append((node["project_id"], "a step lost contact with Sutra twice"))
        elif project["failure_policy"] == "stop_all":
            self._pending.append((node["project_id"], "a step failed and this project stops at the first failure"))

    def _retry(self, tx: Tx, node: sqlite3.Row, why: str) -> None:
        """A new attempt of the node in the transaction that ends the old one (D305c): the node's `task_id` points at the new task, the attempt number goes up, its dependants wait for the new task,
        and the grant is the one it had (frozen). The old task stays in `tasks` as the new one's parent."""
        old_task = node["task_id"]
        new = self.tasks.retry_in(tx, old_task, force=True)
        now = tx.now()
        tx.conn.execute("UPDATE agent_nodes SET task_id = ?, attempt = attempt + 1, state = 'queued', failure_reason = '', lease_expires_at = NULL, last_beat_at = NULL, ended_at = NULL, "
                        "torn_down_at = NULL WHERE id = ?", (new.id, node["id"]))
        for row in tx.conn.execute("SELECT t.id AS id, t.depends_on AS deps FROM tasks t WHERE t.status IN ('blocked','queued') AND t.id <> ? AND EXISTS "
                                   "(SELECT 1 FROM json_each(t.depends_on) j WHERE j.value = ?)", (new.id, old_task)).fetchall():
            tx.conn.execute("UPDATE tasks SET depends_on = ? WHERE id = ?", (json.dumps([new.id if dep == old_task else dep for dep in json.loads(row["deps"])]), row["id"]))
        self._extended.pop(node["id"], None)
        self.store.audit(tx, actor="conductor", action="node.retry", project_id=node["project_id"], node_id=node["id"], role=node["role"], decision="n/a", reason=why[:200],
                         ref=new.id)
        tx.emit("node.updated", {"project_id": node["project_id"], "node_id": node["id"], "state": "queued"})

    # ---- the tick: leases, a sleeping computer, gates that ran out (MAN-7) ------------------------------------------------------------

    async def tick(self, now: int | None = None) -> dict[str, list[str]]:
        """One look at every project that runs. A live node that has been silent for its lease (default 90 s: no event, heartbeat included) goes `expired`, its process through the stop ladder,
        and is retried once (D275). If the tick itself came late by more than half a lease the computer slept: the leases are extended once instead, and a project with an open gate is
        refused (D296). A gate that ran out (24 h) is refused too. Stops decided inside a transaction (`stop_all`, a node that lost its lease twice) are run here. Returns what it did."""
        import asyncio
        moment = int(now) if now is not None else int(self._clock.now())
        gap = 0 if self._last_tick is None else moment - self._last_tick
        self._last_tick = moment
        did = await run_blocking(self._tick_sync, moment, gap)
        if did["expire"]:
            await asyncio.gather(*(self.tasks.stop_node(task_id, f"no sign of life for {did['lease']} s") for task_id in did["expire"]), return_exceptions=True)
        for project_id, reason in did["refuse"]:
            await self.refuse_open_gates(project_id, reason)
        pending, self._pending = self._pending, []
        for project_id, reason in pending:
            await self.stop(project_id, by="system", reason=reason)
        return {"expired": did["expire"], "refused": [p for p, _ in did["refuse"]], "stopped": [p for p, _ in pending], "extended": did["extended"]}

    def _tick_sync(self, now: int, gap: int) -> dict[str, Any]:
        expire: list[str] = []
        extended: list[str] = []
        refuse: list[tuple[str, str]] = []
        lease_default = int(NODE_DEFAULT_CAPS["lease_s"] or 90)
        with self.db.tx() as tx:
            for project in tx.conn.execute("SELECT id, caps_json FROM projects WHERE status IN ('planning','awaiting_approval','running') ORDER BY created_at").fetchall():
                lease_s = int(json.loads(project["caps_json"] or "{}").get("lease_s") or lease_default)
                slept = gap > lease_s // 2
                ran_out = self.store.expire_due(tx, project_id=project["id"], now=now)
                if ran_out:
                    for approval in ran_out:
                        self.store.audit(tx, actor="system", action=GATE_REFUSED_ACTION, project_id=project["id"], node_id=approval.node_id or None, tier=approval.tier, decision="deny",
                                         reason="the question ran out of time", ref=approval.id)
                    refuse.append((project["id"], "not approved: the question ran out of time"))
                    continue
                if slept and tx.conn.execute("SELECT 1 FROM approvals WHERE project_id = ? AND status = 'open'", (project["id"],)).fetchone() is not None:
                    refuse.append((project["id"], GATE_REFUSED_SLEEP))
                    continue
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
        return {"expire": expire, "refuse": refuse, "extended": extended, "lease": lease_default}

    async def refuse_open_gates(self, project_id: str, reason: str) -> int:
        """D296: every open gate of the project counts as refused. The questions are answered `denied` (by the system), the nodes that waited for them are `cancelled` with the reason, the project
        is `stopped`, one receipt line says why, and the nodes that run are stopped through the ladder together. Returns how many nodes it ended."""
        def settle() -> int:
            with self.db.tx() as tx:
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
                tx.emit("project.updated", {"project_id": project_id, "status": "stopped"})
                return cancelled
        ended = await run_blocking(settle)
        ended += await self._stop_nodes(project_id, reason)
        return ended

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
                    gate_open = tx.conn.execute("SELECT 1 FROM approvals WHERE project_id = ? AND status = 'open'", (project["id"],)).fetchone() is not None
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
        return await self._stop_nodes(project_id, reason)

    def begin_kill(self, reason: str) -> list[str]:
        """The kill switch ends every project that has a live or waiting node (D303 d). First step: they become `stopped` (so the gate holds everything and a node that ends is not counted as a
        failed project); returns their ids. The nodes are stopped next (`NodeControl`), then `finish_kill` cancels what had not started."""
        ids = self._projects_with_open_nodes()
        for project_id in ids:
            self._mark_stopped(project_id, reason, "system")
        return ids

    async def finish_kill(self, project_ids: Sequence[str], reason: str) -> int:
        """Last step of a kill: the queued and blocked nodes of those projects are cancelled, so nothing starts by itself after resume (D303 d). Returns how many it cancelled."""
        return sum([await self._stop_nodes(project_id, reason) for project_id in project_ids])

    async def stop_planner_node(self, node_id: str) -> bool:
        """Stop the planner call of the planner node `node_id` (the owner's node stop reaches the planner too, D301). False when no call runs for it."""
        with self._lock:
            request_id = next((rid for rid, (nid, _) in self._planners.items() if nid == node_id), None)
        if request_id is None:
            return False
        return bool(await run_blocking(self.stop_planners, request_id))

    def _projects_with_open_nodes(self) -> list[str]:
        rows = self.db.conn().execute(
            "SELECT DISTINCT p.id FROM projects p JOIN agent_nodes n ON n.project_id = p.id JOIN tasks t ON t.id = n.task_id "
            "WHERE p.status NOT IN ('done','done_with_open_items','stopped','failed') AND t.status IN ('blocked','queued','starting','running','waiting_user') ORDER BY p.created_at").fetchall()
        return [r["id"] for r in rows]

    def _project_row(self, project_id: str) -> sqlite3.Row | None:
        return self.db.conn().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    def _mark_stopped(self, project_id: str, reason: str, by: str) -> None:
        with self.db.tx() as tx:
            changed = tx.conn.execute("UPDATE projects SET status = 'stopped', ended_at = ?, stop_reason = ? WHERE id = ? AND status NOT IN ('done','done_with_open_items','stopped','failed')",
                                      (tx.now(), self.store.clean(reason), project_id)).rowcount
            if changed:
                self.store.audit(tx, actor="owner" if by == "owner" else "system", action="project.stopped", project_id=project_id, decision="n/a", reason=reason)
                tx.emit("project.updated", {"project_id": project_id, "status": "stopped"})

    async def _stop_nodes(self, project_id: str, outcome: str) -> int:
        """The live nodes of the project through the ladder, all together; the ones that have not started are cancelled."""
        import asyncio
        rows = await run_blocking(lambda: self.db.conn().execute(
            "SELECT n.id AS id, n.task_id AS task_id, t.status AS status FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? "
            "AND t.status IN ('blocked','queued','starting','running','waiting_user')", (project_id,)).fetchall())

        async def one(row: sqlite3.Row) -> int:
            try:
                return 1 if await self.tasks.stop_node(row["task_id"], outcome) else 0
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

    # ---- reading --------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _project_out(row: sqlite3.Row) -> ProjectOut:
        return ProjectOut(id=row["id"], request_id=row["request_id"], title=row["title"], status=row["status"], failure_policy=row["failure_policy"],
                          decide_for_me=bool(row["decide_for_me"]), paused=bool(row["paused"]), review_loops=row["review_loops"], caps=json.loads(row["caps_json"] or "{}"),
                          budget_credits=row["budget_credits"], budget_usd=row["budget_usd"], created_at=iso_z(row["created_at"]),
                          ended_at=iso_z(row["ended_at"]) if row["ended_at"] is not None else None, stop_reason=row["stop_reason"])

    @staticmethod
    def _node_out(row: sqlite3.Row) -> NodeOut:
        grants = json.loads(row["grants_json"] or "{}")
        return NodeOut(id=row["id"], project_id=row["project_id"], task_id=row["task_id"], role=row["role"], runtime=row["runtime"], plan_ref=row["plan_ref"],
                       depends_on=json.loads(row["depends_on"] or "[]"), state=row["state"], attempt=row["attempt"], grants=grants, scope=json.loads(row["writes_json"] or "[]"),
                       slice_credits=row["slice_credits"], last_beat_at=iso_z(row["last_beat_at"]) if row["last_beat_at"] is not None else None,
                       lease_expires_at=iso_z(row["lease_expires_at"]) if row["lease_expires_at"] is not None else None, failure_reason=row["failure_reason"],
                       created_at=iso_z(row["created_at"]), ended_at=iso_z(row["ended_at"]) if row["ended_at"] is not None else None)

    def get(self, project_id: str) -> ProjectOut:
        row = self._project_row(project_id)
        if row is None:
            raise NotFound("that project")
        return self._project_out(row)

    def list_projects(self, *, status: str | None = None, limit: int = 50, offset: int = 0) -> list[ProjectOut]:
        sql, args = "SELECT * FROM projects", []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        rows = self.db.conn().execute(sql + " ORDER BY created_at DESC, id LIMIT ? OFFSET ?", (*args, max(1, min(int(limit), 200)), max(0, int(offset)))).fetchall()
        return [self._project_out(row) for row in rows]

    def snapshot(self, project_id: str) -> dict[str, Any]:
        """The page's snapshot (architecture 6): the project, its nodes, the plan's edges, what it spent, the open questions and the last message number (0 until hand-offs exist)."""
        conn = self.db.conn()
        project = self.get(project_id)
        nodes = [self._node_out(r) for r in conn.execute("SELECT * FROM agent_nodes WHERE project_id = ? ORDER BY created_at, rowid", (project_id,))]
        edges = [{"from": dep, "to": node.id, "kind": "depends_on"} for node in nodes for dep in node.depends_on]
        edges += [{"from": earlier, "to": later, "kind": "conflict"} for earlier, later in self._conflict_edges(project, nodes)]
        marks = ",".join("?" * max(1, len([n for n in nodes if n.task_id])))
        task_ids = [n.task_id for n in nodes if n.task_id] or [""]
        spend = conn.execute(f"SELECT count(*) AS calls, sum(usd) AS usd FROM usage_ledger WHERE task_id IN ({marks}) AND provider != 'stub'", task_ids).fetchone()
        approvals = [{"id": a.id, "tier": a.tier, "node_id": a.node_id, "status": a.status, "request": dict(a.request), "expires_at": iso_z(a.expires_at)}
                     for a in self.store.approvals(project_id, status="open")]
        last = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM node_messages WHERE project_id = ?", (project_id,)).fetchone()[0]
        return {"project": project.model_dump(mode="json"), "nodes": [n.model_dump(mode="json") for n in nodes], "edges": edges, "caps": project.caps,
                "spend": {"calls": spend["calls"], "usd": round(spend["usd"], 6) if spend["usd"] is not None else None}, "approvals": approvals, "last_message_seq": last}

    @staticmethod
    def _conflict_edges(project: ProjectOut, nodes: Sequence[NodeOut]) -> list[tuple[str, str]]:
        by_ref = {n.plan_ref: n.id for n in nodes if n.plan_ref}
        return [(by_ref[a], by_ref[b]) for a, b in project.caps.get("conflict_edges", []) if a in by_ref and b in by_ref]    # type: ignore[union-attr]
