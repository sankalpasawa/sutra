"""Projects: a request with two or more steps becomes a project, and its nodes are tasks (multi-agent nodes, D253, D255, D257, D259, D267, D302, D303, D305; MAN-5).

    projects = ProjectService(db, store=node_store, ids=ids, clock=clock, settings=settings, owner_access=..., output_of=..., node_control=...)
    reservation = projects.reserve(request_id, title, steps, budget=None)       # BEFORE the tasks exist: one transaction, the plan goes through the Gatekeeper's rules
    projects.link_task(tx, reservation, step_ref, task_id)                      # in the transaction that makes each task: the node and its task are one thing from then on
    tasks.task_gate = projects.gate                                              # the Conductor's gate: the kill switch and the grant first, then the project's own rules
    projects.sync_task(tx, task_row)                                             # after any change of a node's task: node state, lease, teardown, the project's state

A node is a task plus a row of `agent_nodes` (D253). The tasks are made by the chat agent's runner exactly as before (the same `TaskService.create`, the same `depends_on`), so FIFO, the caps
(`SUTRA_MAX_RUNS`, `SUTRA_MAX_LIVE`), one live task per team and `settle_blocked` apply to them with no second queue (D257). What the project adds: an identity and a frozen grant per node, a
parallel cap, a lease, and teardown. The Conductor's code is in `conductor.py` (C0); the service here hands its calls to it under the same names (`gate` is its task gate, `sync_task` its teardown and the state machine).

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
from sutra_app.orchestrator.conductor import NODE_FINAL, PROJECT_FINAL, TASK_TO_NODE, Conductor
from sutra_app.orchestrator.db import Database, Tx, run_blocking
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.gatekeeper import Evaluation, Plan, PlanStep, evaluate
from sutra_app.orchestrator.ids import Clock, IdFactory, SystemClock, iso_z
from sutra_app.orchestrator.models import NodeOut, ProjectOut
from sutra_app.orchestrator.nodes_store import NodeStore

__all__ = ["ProjectService", "ProjectStep", "Reservation", "default_output_of", "NODE_FINAL", "PROJECT_FINAL", "TASK_TO_NODE"]

log = logging.getLogger(__name__)
DEFAULT_SLICE = 100                       # the work credits a team's run starts with (J2_BUDGET): what a step with no estimate counts as (D300)


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
    title: str = ""
    waits: tuple[int, int] | None = None                      # (the estimate, the limit it is over) while the project waits for the owner's OK on its estimate (D308); None otherwise


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
        self._planners: dict[str, tuple[str, CancelToken]] = {}          # request id -> (the planner's node id, its stop token)
        self._lock = threading.Lock()
        self.conductor = Conductor(self)

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
                return Reservation(found["id"], True, "", nodes, waits=self._waits_of(tx, found["id"]))        # a request planned again (stale chart) finds its project
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
        total = sum(max(0, int(step.estimate_credits or 0)) for step in plan.steps)
        for gate in evaluation.gates:                                                  # the questions are rows; the cards and the answers are MAN-8
            tier = gate.tier if gate.tier is not None else 5
            detail = {"credits": total, "limit": int(plan.confirm_credits or 0)} if gate.kind == "estimate" else {}
            asked = self.store.open_approval(tx, project_id=project_id, node_id=node_ids.get(gate.step_id or "", ""), tier=tier, expires_at=expires,
                                             request={"kind": gate.kind, "why": gate.why, **detail})
            self.store.audit(tx, actor="gatekeeper", action="gate.asked", project_id=project_id, node_id=node_ids.get(gate.step_id or "", None), tier=tier, decision="ask",
                             reason=gate.why, ref=asked.id)
        self.store.audit(tx, actor="gatekeeper", action="plan.accepted", project_id=project_id, decision="allow", reason=f"{len(steps)} steps, {len(evaluation.gates)} question(s)")
        tx.emit("project.created", {"project_id": project_id, "status": status})
        waits = (total, int(plan.confirm_credits or 0)) if any(gate.kind == "estimate" for gate in evaluation.gates) else None
        return Reservation(project_id, True, "", node_ids, planner_node_id, title=" ".join(title.split())[:200], waits=waits)

    @staticmethod
    def _waits_of(tx: Tx, project_id: str) -> tuple[int, int] | None:
        """(the estimate, the limit) of a project that still waits for its estimate question, from the stored question; None when no such question is open."""
        for row in tx.conn.execute("SELECT request_json FROM approvals WHERE project_id = ? AND status = 'open' ORDER BY created_at, id", (project_id,)):
            try:
                asked = json.loads(row["request_json"])
                if asked.get("kind") == "estimate":
                    return (int(asked["credits"]), int(asked["limit"]))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return None

    def link_task(self, tx: Tx, reservation: Reservation, step_ref: str, task_id: str) -> None:
        """In the transaction that makes the task: tie the node of `step_ref` to it. From then on the task is a node (the gate sees it)."""
        node_id = reservation.nodes.get(step_ref)
        if node_id is None:
            return
        tx.conn.execute("UPDATE agent_nodes SET task_id = ? WHERE id = ? AND task_id IS NULL", (task_id, node_id))
        self.sync_task(tx, task_id)

    # ---- the Conductor (conductor.py): same names, so nothing that calls the service changes (C0) -----------------------------------------

    @property
    def _ticker(self) -> Any:
        return self.conductor._ticker

    def gate(self, conn: sqlite3.Connection, now: int, row: Any) -> str:
        return self.conductor.gate(conn, now, row)

    def on_starting(self, tx: Tx, row: Any) -> None:
        self.conductor.on_starting(tx, row)

    def sync_task(self, tx: Tx, task_id: str) -> None:
        self.conductor.sync_task(tx, task_id)

    async def tick(self, now: int | None = None) -> dict[str, list[str]]:
        return await self.conductor.tick(now)

    async def refuse_open_gates(self, project_id: str, reason: str) -> int:
        return await self.conductor.refuse_open_gates(project_id, reason)

    async def reconcile_projects(self) -> dict[str, int]:
        return await self.conductor.reconcile_projects()

    def start_ticking(self, interval: float = 5.0) -> None:
        self.conductor.start_ticking(interval)

    async def stop_ticking(self) -> None:
        await self.conductor.stop_ticking()

    async def stop(self, project_id: str, *, by: str = "owner", reason: str = "stopped by you") -> int:
        return await self.conductor.stop(project_id, by=by, reason=reason)

    def begin_kill(self, reason: str) -> list[str]:
        return self.conductor.begin_kill(reason)

    async def finish_kill(self, project_ids: Sequence[str], reason: str) -> int:
        return await self.conductor.finish_kill(project_ids, reason)

    async def pause(self, project_id: str, *, resume: bool = False) -> ProjectOut:
        return await self.conductor.pause(project_id, resume=resume)

    # ---- stopping the planner -------------------------------------------------------------------------------------------------------

    async def stop_planner_node(self, node_id: str) -> bool:
        """Stop the planner call of the planner node `node_id` (the owner's node stop reaches the planner too, D301). False when no call runs for it."""
        with self._lock:
            request_id = next((rid for rid, (nid, _) in self._planners.items() if nid == node_id), None)
        if request_id is None:
            return False
        return bool(await run_blocking(self.stop_planners, request_id))

    def _project_row(self, project_id: str) -> sqlite3.Row | None:
        return self.db.conn().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

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
