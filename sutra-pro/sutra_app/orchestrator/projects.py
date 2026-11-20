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

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sutra_app.config import NODE_DEFAULT_CAPS, Settings
from sutra_app.connectors.cancel import CancelToken
from sutra_app.orchestrator.budgets import DEFAULT_SLICE, make_slices
from sutra_app.orchestrator.conductor import NODE_FINAL, PROJECT_FINAL, TASK_TO_NODE, Conductor
from sutra_app.orchestrator.db import Database, Tx, run_blocking
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app import oslayer, syspermissions
from sutra_app.orchestrator.gatekeeper import DECIDE_FOR_ME, Evaluation, Plan, PlanStep, Refusal, decide_for_me_answer, evaluate
from sutra_app.orchestrator.grants import Grant
from sutra_app.orchestrator.ids import Clock, IdFactory, SystemClock, iso_z
from sutra_app.orchestrator.models import NodeApprovalCard, NodeOut, ProjectOut, SystemPermissionCard
from sutra_app.orchestrator.nodes_store import NodeStore

__all__ = ["ProjectService", "ProjectStep", "Reservation", "default_output_of", "default_output_name", "NODE_FINAL", "PROJECT_FINAL", "TASK_TO_NODE"]

log = logging.getLogger(__name__)
PROBE_SECONDS = 45.0                       # the longest the probe of the computer's permissions may take (D322 e)


@dataclass(frozen=True)
class ProjectStep:
    """One step of a request as the project sees it: the plan's own id (`ref`, the chat agent's a1, a2 ...), the team, the steps it waits for, and the planner's estimate (0: none)."""

    ref: str
    dept_id: str
    depends_on: tuple[str, ...] = ()
    estimate_credits: int = 0
    scope: tuple[str, ...] = ()                       # the paths of the owner's folder the step asks to change (the node plan, D306)
    needs: tuple[str, ...] = ()                       # the app tools it asks for: `sutra`, `github`


def _tool_profile(needs: Sequence[str]) -> str:
    asked = set(needs)
    return "sutra+github" if {"sutra", "github"} <= asked else "github" if "github" in asked else "sutra" if "sutra" in asked else "none"


@dataclass(frozen=True)
class Reservation:
    """What `reserve` made. `nodes` maps a step's ref to its node id. `ok` is False when the Gatekeeper refused the plan (`why` says in words; no node was made and the caller makes no task)."""

    project_id: str
    ok: bool = True
    why: str = ""
    nodes: dict[str, str] = field(default_factory=dict)
    planner_node_id: str = ""
    title: str = ""
    asks: tuple[str, ...] = ()                                  # the kinds of the other open questions (`tier`, `scope`) the reply must tell the owner about (D317)
    waits: tuple[int, int] | None = None                      # (the estimate, the limit it is over) while the project waits for the owner's OK on its estimate (D308); None otherwise


def _configured_output(data_dir: Any, dept_id: str) -> str:
    """The `output` setting of a team as the engine would read it BEFORE a run (`engine.json` of the team, then the global one): a type name, or `auto`, or "" when nothing can be read."""
    from pathlib import Path
    try:
        from sutra_app.engine.spec import read_settings_file
        for path in (Path(data_dir) / "departments" / dept_id / "engine.json", Path(data_dir) / "engine.json"):
            name = (read_settings_file(path) or {}).get("output")
            if isinstance(name, str) and name:
                return name
    except Exception:                                       # noqa: BLE001  (an unreadable setting is "not known")
        return ""
    return ""


def default_output_of(data_dir: Any) -> Callable[[str], Any]:
    """The output spec of a team as far as it is known BEFORE a run: its engine setting `output` when that names a type; `auto` is chosen by the engine per run, so it is not known here and counts as
    `read` (the conservative reading: nothing in the owner's folder beyond reading; D299 says the grant describes, it does not enforce). Anything that cannot be read is None (`read`)."""
    def output_of(dept_id: str) -> Any:
        name = _configured_output(data_dir, dept_id)
        if not name or name == "auto":
            return None
        try:
            from sutra_app.engine.capabilities.base import output_spec
            return output_spec(name)
        except Exception:                                   # noqa: BLE001
            return None

    return output_of


def default_output_name(data_dir: Any) -> Callable[[str], str]:
    """The team's `output` setting as a word (`auto`, a type name, or ""), so the record of a grant can say "output auto" instead of pretending it knows (G10, D307)."""
    return lambda dept_id: _configured_output(data_dir, dept_id)


class ProjectService:
    def __init__(self, db: Database, *, store: NodeStore, ids: IdFactory | None = None, clock: Clock | None = None, settings: Settings,
                 owner_access: Callable[[], str] | None = None, output_of: Callable[[str], Any] | None = None, node_control: Any = None, tasks: Any = None, chats: Any = None,
                 output_name: Callable[[str], str] | None = None, folder_of: Callable[[], str | None] | None = None, adapter: Any = None,
                 elevated: Callable[[], bool] | None = None, owner_decides: Callable[[Sequence[str]], bool] | None = None) -> None:
        self.db = db
        self.store = store
        self.ids = ids or IdFactory()
        self._clock = clock or SystemClock()
        self.settings = settings
        self._owner_access = owner_access or (lambda: "none")
        self._output_of = output_of or (lambda dept: None)
        self._output_name = output_name or (lambda dept: "")
        self._folder_of = folder_of or (lambda: None)                              # the owner's working folder, for the system probe (MAN-15)
        self._adapter = adapter                                                     # a fake in tests; None: the adapter of this system
        self._elevated = elevated or oslayer.is_elevated
        self._owner_decides = owner_decides or (lambda depts: False)                # the owner's own Decide for me setting of these teams (D319, G13)
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
                planner_node_id: str = "", plan_defaults: bool = False) -> Reservation | None:
        """Make the project and its nodes for a request, before its tasks exist (the tasks are linked as they are made: `link_task`). None when this is not a project: fewer than two steps (D255:
        a one-step request keeps today's path). The plan goes through `gatekeeper.evaluate`; a refused plan makes a project that is `failed` and no node. A plan that needs the owner (a question
        about a tier above the defaults, a wide scope, or an estimate over the confirm threshold) makes the project `awaiting_approval` with its questions stored as approvals; nothing starts until
        they are answered (MAN-8) or run out (MAN-7). One transaction."""
        if len(steps) < 2:
            return None
        decide_for_me = bool(decide_for_me) or bool(self._owner_decides([step.dept_id for step in steps]))      # one switch, one meaning: the request's OR the owner's own (D319)
        slice_credits = budget if budget is not None else DEFAULT_SLICE
        plan = Plan(
            steps=tuple(PlanStep(id=step.ref, role="worker", depends_on=tuple(step.depends_on), output=self._output_of(step.dept_id),
                                 estimate_credits=step.estimate_credits or slice_credits, wants=frozenset({4}) if "github" in step.needs else frozenset(), scope=tuple(step.scope),
                                 tool_profile=_tool_profile(step.needs)) for step in steps),
            owner_access=self._owner_access(), confirm_credits=None if budget is not None else int(NODE_DEFAULT_CAPS["confirm_credits"] or 500))
        evaluation = evaluate(plan)
        if self._elevated():                                                        # a process run as administrator makes no node: what it writes would belong to the administrator (MAN-15)
            evaluation = Evaluation(False, {}, refusals=(Refusal(None, "system.elevated", "Sutra is running as administrator. Close it and open it again the usual way, then ask again"),))
        with self.db.tx() as tx:
            if tx.conn.execute("SELECT id FROM projects WHERE request_id = ?", (request_id,)).fetchone() is not None:
                found = tx.conn.execute("SELECT id, status FROM projects WHERE request_id = ?", (request_id,)).fetchone()
                nodes = {r["plan_ref"]: r["id"] for r in tx.conn.execute("SELECT id, plan_ref FROM agent_nodes WHERE project_id = ? AND role = 'worker'", (found["id"],))}
                if found["status"] in PROJECT_FINAL:                                  # fail closed (G8, B2): a request whose project ended makes no task, so no ordinary task escapes the gate
                    return Reservation(found["id"], False, "that project has already ended, so it was not started again")
                return Reservation(found["id"], True, "", nodes, waits=self._waits_of(tx, found["id"]))        # a request planned again (stale chart) finds its project
            return self._reserve(tx, request_id, title, steps, plan, evaluation, budget, decide_for_me, planner_node_id, plan_defaults)

    def _reserve(self, tx: Tx, request_id: str, title: str, steps: Sequence[ProjectStep], plan: Plan, evaluation: Evaluation, budget: int | None, decide_for_me: bool,
                 planner_node_id: str, plan_defaults: bool = False) -> Reservation:
        now = tx.now()
        project_id = self.ids.project_id()
        caps = {key: value for key, value in NODE_DEFAULT_CAPS.items()}
        if budget is not None:
            caps["confirm_credits"] = None                                           # the owner's own number is the answer (D300)
        caps["conflict_edges"] = [list(edge) for edge in evaluation.conflicts]     # kept for the lanes package (MAN-10): a delay, never a cancel (D259)
        caps["plan"] = [{"ref": step.ref, "dept": step.dept_id, "scope": list(step.scope), "needs": list(step.needs), "estimate": int(step.estimate_credits or 0),
                              "depends_on": list(step.depends_on)} for step in steps]       # what the answer path re-evaluates (MAN-8); not shown
        wants = [budget if budget is not None else (step.estimate_credits or DEFAULT_SLICE) for step in steps]            # the owner's number wins over the planner's guess (D252)
        slices = make_slices(wants)                                              # each step's share (MAN-9); the project's ceiling is their sum, written as `budget_credits`
        caps["owner_budget"] = budget                                            # the owner's own number for each run (D252), None when they gave none
        status = "failed" if not evaluation.ok else "awaiting_approval" if evaluation.gates else "running"
        why = "; ".join(refusal.why for refusal in evaluation.refusals)[:200]
        tx.conn.execute(
            "INSERT INTO projects(id, request_id, title, status, decide_for_me, caps_json, budget_credits, created_at, ended_at, stop_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, request_id, " ".join(title.split())[:200], status, 1 if decide_for_me else 0, json.dumps(caps, sort_keys=True), sum(slices), now,
             now if status == "failed" else None, why if status == "failed" else ""))
        self.store.audit(tx, actor="system", action="project.created", project_id=project_id, decision="n/a", reason=f"{len(steps)} steps", ref=request_id)
        if plan_defaults:
            self.store.audit(tx, actor="system", action="plan.defaults", project_id=project_id, decision="n/a", reason="the step requests could not be read, so no step asks for more than its defaults")
        if planner_node_id:
            tx.conn.execute("INSERT INTO agent_nodes(id, project_id, role, runtime, state, created_at, ended_at) VALUES (?,?,?,?,?,?,?)",
                            (planner_node_id, project_id, "planner", "inline", "done", now, now))
        if not evaluation.ok:
            self.store.audit(tx, actor="gatekeeper", action="plan.refused", project_id=project_id, decision="deny", reason=why)
            if any(refusal.code == "system.elevated" for refusal in evaluation.refusals):
                self.store.audit(tx, actor="gatekeeper", action="system.elevated", project_id=project_id, decision="deny", reason="a process run as administrator makes no node")
            tx.emit("project.created", {"project_id": project_id, "status": "failed"})
            return Reservation(project_id, False, why or "the plan was refused")
        node_ids = {step.ref: self.ids.node_id() for step in steps}
        for step in steps:
            node_id = node_ids[step.ref]
            grant = evaluation.grants[step.ref].for_node(self.ids.grant_id(), node_id)
            writes = list(grant.scope)
            state = "awaiting_approval" if evaluation.gates else "planned"
            tx.conn.execute(
                "INSERT INTO agent_nodes(id, project_id, role, runtime, plan_ref, depends_on, state, grants_json, writes_json, slice_credits, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (node_id, project_id, "worker", "engine", step.ref, json.dumps([node_ids[d] for d in step.depends_on if d in node_ids]), state,
                 json.dumps(grant.to_json(), sort_keys=True), json.dumps(writes), slices[steps.index(step)], now))
            self.store.audit(tx, actor="gatekeeper", action="grant.issued", project_id=project_id, node_id=node_id, role="worker", tier=max(grant.tiers), decision="allow",
                             reason=grant.describe(output=self._output_name(step.dept_id)), target=step.dept_id, ref=grant.id)
            for denial_step, denial in evaluation.denied:
                if denial_step == step.ref:
                    self.store.audit(tx, actor="gatekeeper", action="grant.denied", project_id=project_id, node_id=node_id, role="worker", tier=denial.tier, decision="deny",
                                     reason=denial.why, target=step.dept_id)
        expires = now + int(NODE_DEFAULT_CAPS["approval_expiry_s"] or 86400)
        total = sum(max(0, int(step.estimate_credits or 0)) for step in plan.steps)
        for gate in evaluation.gates:                                                  # the questions are rows; the cards and the answers are MAN-8
            tier = gate.tier if gate.tier is not None else 5
            detail = {"credits": total, "limit": int(plan.confirm_credits or 0)} if gate.kind == "estimate" else {}
            kind = "plan_estimate" if gate.kind == "estimate" else gate.kind                  # the estimate question is its own kind: tier 5, allow once or deny only (D308)
            asked = self.store.open_approval(tx, project_id=project_id, node_id=node_ids.get(gate.step_id or "", ""), tier=tier, expires_at=expires,
                                             request={"kind": kind, "why": gate.why, **detail})
            self.store.audit(tx, actor="gatekeeper", action="gate.asked", project_id=project_id, node_id=node_ids.get(gate.step_id or "", None), tier=tier, decision="ask",
                             reason=gate.why, ref=asked.id)
        self.store.audit(tx, actor="gatekeeper", action="plan.accepted", project_id=project_id, decision="allow", reason=f"{len(steps)} steps, {len(evaluation.gates)} question(s)")
        tx.emit("project.created", {"project_id": project_id, "status": status})
        if decide_for_me:
            self._decide_by_rule(tx, project_id)                                      # Decide for me (D294): the rule table answers in this transaction; nothing it cannot answer is hidden
        self.sync_cards(tx, project_id)                                                 # one card in the org chat for each open question (D317)
        waits = (total, int(plan.confirm_credits or 0)) if self._waits_of(tx, project_id) is not None else None
        asks = tuple(dict.fromkeys(str(a.request.get("kind", "")) for a in self.store.approvals(project_id, status="open") if a.request.get("kind") in ("tier", "scope")))
        return Reservation(project_id, True, "", node_ids, planner_node_id, title=" ".join(title.split())[:200], waits=waits, asks=asks)

    @staticmethod
    def _waits_of(tx: Tx, project_id: str) -> tuple[int, int] | None:
        """(the estimate, the limit) of a project that still waits for its estimate question, from the stored question; None when no such question is open."""
        for row in tx.conn.execute("SELECT request_json FROM approvals WHERE project_id = ? AND status = 'open' ORDER BY created_at, id", (project_id,)):
            try:
                asked = json.loads(row["request_json"])
                if asked.get("kind") == "plan_estimate":
                    return (int(asked["credits"]), int(asked["limit"]))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        return None

    def link_task(self, tx: Tx, reservation: Reservation, step_ref: str, task_id: str) -> None:
        """In the transaction that makes the task: tie the node of `step_ref` to it. From then on the task is a node (the gate sees it). A step that has no node in an ok reservation, or whose node has a task
        already, raises: the transaction ends and no task is made, so a request that is planned or retried again can never leave an ordinary, ungated task behind (G8, B2)."""
        ended = tx.conn.execute("SELECT status FROM projects WHERE id = ?", (reservation.project_id,)).fetchone()
        if ended is not None and ended["status"] in PROJECT_FINAL:                  # a stop or a kill between `reserve` and the tasks makes no task (D322 f)
            raise AppError("busy", "That project has ended, so no step of it was started")
        node_id = reservation.nodes.get(step_ref)
        if node_id is None:
            raise AppError("busy", "That step has no place in its project, so its task was not made")                 # fail closed (G8, B2): the task is never made without its node
        linked = tx.conn.execute("UPDATE agent_nodes SET task_id = ? WHERE id = ? AND task_id IS NULL", (task_id, node_id)).rowcount
        if not linked:
            raise AppError("busy", "That step of the project already has its task, so no second one was made")
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

    def prepare_handoff(self, task_id: str) -> None:
        self.conductor.prepare_handoff(task_id)

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

    # ---- Decide for me, and the answer path (MAN-8, D294, D306, D308) --------------------------------------------------------------

    def owner_turned_on(self, dept_id: str) -> int:
        """The owner turned Decide for me on for a team (the Simple view's switch, D319, P2): every project of that team that still has open questions is switched to Decide for me and the
        rule table answers what it may at once (the same table, audited the same way). Turning it OFF changes nothing here: it applies to the next project (a question already answered stays
        answered). Returns how many projects it switched."""
        switched = 0
        with self.db.tx() as tx:
            for row in tx.conn.execute("SELECT id, caps_json FROM projects WHERE status IN ('planning','awaiting_approval','running') AND decide_for_me = 0").fetchall():
                if not any(step.get("dept") == dept_id for step in (json.loads(row["caps_json"] or "{}").get("plan") or [])):
                    continue
                if not self.store.approvals(row["id"], status="open"):
                    continue
                tx.conn.execute("UPDATE projects SET decide_for_me = 1 WHERE id = ?", (row["id"],))
                self.store.audit(tx, actor="owner", action="project.decide_for_me", project_id=row["id"], decision="n/a", reason="Decide for me was turned on")
                self._decide_by_rule(tx, row["id"])
                switched += 1
        return switched

    def _ceiling(self, project: sqlite3.Row) -> int | None:
        """The most credits a plan may be estimated at for Decide for me to say yes once: the cap `project_credits`, never more (D294). The project's own ceiling, `budget_credits`, is the sum of its slices."""
        found = json.loads(project["caps_json"] or "{}").get("project_credits")
        return int(found) if found else None

    def _decide_by_rule(self, tx: Tx, project_id: str) -> None:
        """Decide for me (D294): the rule table of the Gatekeeper answers every open question it may, in the caller's transaction, each answer audited as `decided_by rule:decide_for_me`. The
        questions it may not answer (credits over the ceiling, tier 6, a permission of the computer) stay open for the owner."""
        project = tx.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        for approval in self.store.approvals(project_id, status="open"):
            answer = decide_for_me_answer(str(approval.request.get("kind", "")), approval.tier, estimate=int(approval.request.get("credits") or 0), ceiling=self._ceiling(project))
            if answer is None:
                continue
            self.store.decide(tx, approval.id, answer.decision, decided_by=DECIDE_FOR_ME)
            self.store.audit(tx, actor="gatekeeper", action="gate.decided", project_id=project_id, node_id=approval.node_id or None, tier=approval.tier, decision="allow",
                             reason=f"decided_by {DECIDE_FOR_ME}: {answer.rule}: {answer.why}", ref=approval.id)
        self._settle_answers(tx, project_id)

    def _settle_answers(self, tx: Tx, project_id: str, why: str = "not approved: a question was answered no") -> str:
        outcome = self._settle_inner(tx, project_id, why)
        self.sync_cards(tx, project_id)
        return outcome

    @staticmethod
    def _is_step_question(a: Any) -> bool:
        """A question about ONE step: a system permission (D295's skip) or a tier-4 or wide-scope question that names its node (D315 b)."""
        kind = a.request.get("kind")
        return kind == "system" or (kind in ("tier", "scope") and bool(a.node_id))

    def _cancel_step(self, tx: Tx, project_id: str, node_id: str) -> bool:
        """Cancel one step that was not approved ("not approved: you said no") and, following the plan's edges, the steps that wait for it ("a step it needed was not approved"). Returns True
        when a step was cancelled now. A system question is not handled here (its skip cancels its own nodes)."""
        why = "not approved: you said no"
        did = False
        todo, seen = [(node_id, why)], set()
        while todo:
            nid, reason = todo.pop(0)
            if not nid or nid in seen:
                continue
            seen.add(nid)
            row = tx.conn.execute("SELECT n.state AS state, n.task_id AS task_id, t.status AS tstatus FROM agent_nodes n LEFT JOIN tasks t ON t.id = n.task_id WHERE n.id = ? AND n.project_id = ?",
                                  (nid, project_id)).fetchone()
            if row is None or row["state"] in NODE_FINAL:
                continue
            if row["task_id"] and row["tstatus"] in ("blocked", "queued") and self.tasks is not None:
                self.tasks.cancel_in(tx, row["task_id"], reason)
            else:
                tx.conn.execute("UPDATE agent_nodes SET state = 'cancelled', failure_reason = ?, ended_at = ?, torn_down_at = ? WHERE id = ? AND state NOT IN ('done','failed','cancelled')",
                                (reason, tx.now(), tx.now(), nid))
                tx.emit("node.updated", {"project_id": project_id, "node_id": nid, "state": "cancelled"})
            self.store.audit(tx, actor="gatekeeper", action="node.cancelled", project_id=project_id, node_id=nid, decision="deny", reason=reason)
            did = True
            todo += [(r["id"], "a step it needed was not approved") for r in tx.conn.execute("SELECT n.id AS id FROM agent_nodes n, json_each(n.depends_on) j WHERE n.project_id = ? AND j.value = ?", (project_id, nid))]
        if did:
            self.conductor._sync_project(tx, project_id)
        return did

    def _settle_inner(self, tx: Tx, project_id: str, why: str) -> str:
        """After any answer (the owner's, a rule's): a project with a question answered no (or run out) is refused at once (D296's own path); else the plan is evaluated again with what was
        allowed, the grant of every node that has NOT spawned is rewritten (a new `grant.issued` row; a node that runs is never touched), and when no question is open the project and its waiting
        nodes move on. Returns `refused`, `running`, `waiting` or `ended`."""
        project = tx.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None or project["status"] in PROJECT_FINAL:
            return "ended"
        approvals = self.store.approvals(project_id)
        if any((a.status == "expired" and not a.request.get("late")) or (a.status == "denied" and not self._is_step_question(a)) for a in approvals):      # a no to the estimate, or a question that ran out, stops the project
            self.conductor._refuse_in(tx, project_id, why)
            return "refused"
        for a in approvals:                                                          # a no to ONE step's question cancels only that step (D315 b)
            if a.status == "denied" and a.request.get("kind") != "system" and self._is_step_question(a):
                if self._cancel_step(tx, project_id, a.node_id) and project["failure_policy"] == "stop_all":
                    self.conductor._refuse_in(tx, project_id, "not approved: you said no and this project stops at the first failure")
                    return "refused"
        caps = json.loads(project["caps_json"] or "{}")
        nodes = {r["plan_ref"]: r for r in tx.conn.execute("SELECT * FROM agent_nodes WHERE project_id = ? AND role = 'worker'", (project_id,))}
        by_id = {row["id"]: ref for ref, row in nodes.items()}
        approved: dict[str, set[int]] = {}
        wide: set[str] = set()
        estimate_ok = False
        for approval in approvals:
            if approval.status not in ("allowed_once", "allowed_project"):
                continue
            kind, ref = str(approval.request.get("kind", "")), by_id.get(approval.node_id)
            if kind == "tier" and ref:
                approved.setdefault(ref, set()).add(approval.tier)
            elif kind == "scope" and ref:
                wide.add(ref)
            elif kind == "plan_estimate":
                estimate_ok = True
        rows = caps.get("plan") or []
        if rows:
            owner_budget = caps.get("owner_budget")
            slice_credits = owner_budget if owner_budget is not None else DEFAULT_SLICE
            plan = Plan(
                steps=tuple(PlanStep(id=r["ref"], role="worker", depends_on=tuple(r.get("depends_on") or ()), output=self._output_of(r["dept"]), estimate_credits=r.get("estimate") or slice_credits,
                                     wants=frozenset({4}) if "github" in r.get("needs", ()) else frozenset(), scope=tuple(r.get("scope") or ()), tool_profile=_tool_profile(r.get("needs", ())))
                            for r in rows),
                owner_access=self._owner_access(), approved={k: frozenset(v) for k, v in approved.items()}, approved_wide=frozenset(wide),
                confirm_credits=None if estimate_ok or caps.get("owner_budget") is not None else int(caps.get("confirm_credits") or NODE_DEFAULT_CAPS["confirm_credits"] or 500))
            evaluation = evaluate(plan)
            if evaluation.ok:
                for ref, node in nodes.items():
                    if node["state"] not in ("awaiting_approval", "planned", "queued") or ref not in evaluation.grants:
                        continue                                                    # a node that has spawned is never rewritten
                    old = Grant.from_json(json.loads(node["grants_json"]))
                    new = evaluation.grants[ref].for_node(old.id, node["id"])
                    if new.to_json() != old.to_json():
                        issued = evaluation.grants[ref].for_node(self.ids.grant_id(), node["id"])
                        tx.conn.execute("UPDATE agent_nodes SET grants_json = ?, writes_json = ? WHERE id = ?",
                                        (json.dumps(issued.to_json(), sort_keys=True), json.dumps(list(issued.scope)), node["id"]))
                        dept = next((r["dept"] for r in rows if r["ref"] == ref), "")
                        self.store.audit(tx, actor="gatekeeper", action="grant.issued", project_id=project_id, node_id=node["id"], role="worker", tier=max(issued.tiers), decision="allow",
                                         reason=issued.describe(output=self._output_name(dept)), target=dept, ref=issued.id)
        if any(a.status == "open" for a in approvals):
            return "waiting"
        tx.conn.execute("UPDATE projects SET status = 'running' WHERE id = ? AND status = 'awaiting_approval'", (project_id,))
        for node in tx.conn.execute("SELECT n.id AS id, t.status AS tstatus FROM agent_nodes n LEFT JOIN tasks t ON t.id = n.task_id WHERE n.project_id = ? AND n.state = 'awaiting_approval'",
                                    (project_id,)).fetchall():
            tx.conn.execute("UPDATE agent_nodes SET state = ? WHERE id = ?", ("queued" if node["tstatus"] == "queued" else "planned", node["id"]))
            tx.emit("node.updated", {"project_id": project_id, "node_id": node["id"], "state": "queued" if node["tstatus"] == "queued" else "planned"})
        tx.emit("project.updated", {"project_id": project_id, "status": "running"})
        return "running"

    async def answer(self, project_id: str, approval_id: str, decision: str, *, by: str = "owner") -> dict[str, Any]:
        """The owner's answer to one open question (`allow_once`, `allow_project` or `deny`; `allow_project` is refused for the plan's estimate and above tier 4, 422). The first answer wins (a
        repeat is a no-op, a different one is 409, an answer to a question that ran out says so). The plan is evaluated again, the grants of the nodes that have not started are rewritten and,
        when nothing is left to ask, the project starts; a no stops it with "not approved". Returns the project's snapshot."""
        def work() -> str:
            with self.db.tx() as tx:
                found = tx.conn.execute("SELECT request_json FROM approvals WHERE id = ? AND project_id = ?", (approval_id, project_id)).fetchone()
                if found is None:
                    raise NotFound("that question")
                if '"kind":"system"' in found["request_json"].replace(" ", ""):            # a question about the computer has its own two answers (m2)
                    raise AppError("validation", "That question is about your computer. Use Check again or Skip")
                row = self.store.decide(tx, approval_id, decision, decided_by="owner" if by == "owner" else "system")
                if row.duplicate:
                    return "again"
                refused = decision == "deny" or row.status in ("denied", "expired")                  # an answer that came after the question ran out is a refusal, not an allow (m1)
                self.store.audit(tx, actor="owner" if by == "owner" else "system", action="gate.refused" if row.status == "expired" else "gate.decided", project_id=project_id,
                                 node_id=row.node_id or None, tier=row.tier, decision="deny" if refused else "allow",
                                 reason=("the question had run out of time" if row.status == "expired" else f"decided_by {row.decided_by}: {decision}"), ref=approval_id)
                return self._settle_answers(tx, project_id, why="not approved: you said no" if decision == "deny" else "not approved: a question was answered no")
        outcome = await run_blocking(work)
        if outcome == "running" and self.tasks is not None:
            await self.tasks.start_ready()
        return await run_blocking(self.snapshot, project_id)

    # the words of a card (plain, simple). A no to a question about one step cancels that step (D315 b); a no to the estimate stops the project; nothing here says a writer "runs alone" before MAN-10 (D323).
    _WORDS = {
        "tier": "A step wants to read GitHub, through your own GitHub login (read only). Allow it? If you say no, only that step is cancelled and the steps that need it. The rest go on.",
        "scope": "A step changes files in several places of your folder. Allow it? If you say no, only that step is cancelled and the steps that need it. The rest go on.",
        "plan_estimate": "This plan is estimated at about {credits} credits, which is over {limit}. Allow it once? If you say no, the whole project stops.",
        "system": "Your computer must allow something first. Open the settings, allow it, then press Check again. If you skip it, the steps that need it are cancelled.",
    }

    def _card_of(self, project_id: str, a: Any) -> NodeApprovalCard:
        kind = str(a.request.get("kind", ""))
        options = (["check_again", "skip"] if kind == "system" else ["allow_once", "deny"] if kind in ("plan_estimate", "scope") or a.tier == 5 else ["allow_once", "allow_project", "deny"])
        question = self._WORDS.get(kind, "A step needs your answer.").format(credits=a.request.get("credits", "?"), limit=a.request.get("limit", "?"))
        return NodeApprovalCard(project_id=project_id, approval_id=a.id, kind=kind[:40], tier=a.tier, node_id=a.node_id, question=question, options=options, expires_at=iso_z(a.expires_at),
                                item=str(a.request.get("item", ""))[:40] if kind == "system" else "")

    def approval_cards(self, project_id: str) -> list[NodeApprovalCard]:
        """The open questions of a project as cards, in plain words (no word of any node)."""
        return [self._card_of(project_id, a) for a in self.store.approvals(project_id, status="open")]

    def sync_cards(self, tx: Tx, project_id: str) -> None:
        """Keep the org chat in step with the project's questions (D317): ONE card message for each open question (by its `src_ref` `approval:<id>`), written in the transaction that opens it, and
        a card whose question was answered or ended is marked answered (it points at itself, as a card decided without a line does). `needs_you.changed` follows. A no-op without a chat."""
        if self.chats is None:
            return
        from sutra_app.library.gate import GATE
        from sutra_app.orchestrator.ids import ORG_SESSION_ID
        changed = False
        for a in self.store.approvals(project_id):
            src = f"approval:{a.id}"
            row = tx.conn.execute("SELECT id, answered_by FROM chat_messages WHERE session_id = ? AND src_ref = ?", (ORG_SESSION_ID, src)).fetchone()
            if row is None and a.status == "open":
                card = json.loads(self._card_of(project_id, a).model_dump_json())
                payload = dict(kind="card", session_id=ORG_SESSION_ID, role="agent", who="sutra", text="", card=card, src_ref=src, at=tx.now())
                self.chats.post(tx, ORG_SESSION_ID, GATE.check("chat_message", payload, ctx=tx.ctx))
                changed = True
            elif row is not None and a.status != "open" and row["answered_by"] is None:
                tx.conn.execute("UPDATE chat_messages SET answered_by = ? WHERE id = ?", (row["id"], row["id"]))
                changed = True
        if changed:
            self.chats.emit_needs_you(tx)

    # ---- system permissions (MAN-15, D295) ------------------------------------------------------------------------------------------

    def _system_adapter(self) -> Any:
        return self._adapter if self._adapter is not None else syspermissions.adapter_for()

    async def probe_system(self, project_id: str) -> int:
        """Before any node of the project starts: what the computer has allowed (the probe only looks). A step that writes needs the write probe, the others the read probe. Every need is ONE
        question of the project (kind `system`, tier 2 for a write, 1 for a read; the same question for several steps), the steps it affects wait in `awaiting_system` (the gate holds them),
        the others run. It touches the disk and may show a system dialog, so it is not run inside the gate: the runner calls it after `reserve` and before the tasks are made. Returns how many
        questions it opened. Decide for me does not answer them."""
        folder = self._folder_of()
        if not folder:
            return 0
        adapter = self._system_adapter()
        nodes = await run_blocking(lambda: [dict(r) for r in self.db.conn().execute(
            "SELECT id, grants_json, state FROM agent_nodes WHERE project_id = ? AND role = 'worker' AND state IN ('planned','awaiting_approval','queued')", (project_id,))])
        writers = [n for n in nodes if json.loads(n["grants_json"] or "{}").get("folder") == "edit"]
        readers = [n for n in nodes if n not in writers]
        found: dict[tuple[str, str, str], list[str]] = {}
        for group, write in ((writers, True), (readers, False)):
            if not group:
                continue
            try:                                                                    # a system dialog can stay unanswered: past the limit the folder counts as a need and its card opens (D322 e)
                needs = await asyncio.wait_for(run_blocking(lambda write=write: adapter.probe(Path(folder), write=write)), PROBE_SECONDS)
            except asyncio.TimeoutError:
                needs = [syspermissions.Need("unknown", "write" if write else "read", "your folder")]
            for need in needs:
                found.setdefault((need.item, need.level, need.label), []).extend(n["id"] for n in group)
        if not found:
            return 0

        def open_questions() -> int:
            opened = 0
            with self.db.tx() as tx:
                expires = tx.now() + int(NODE_DEFAULT_CAPS["approval_expiry_s"] or 86400)
                for (item, level, label), ids in found.items():
                    asked = self.store.open_approval(tx, project_id=project_id, node_id="", tier=2 if level == "write" else 1, expires_at=expires, client_id=f"system:{item}:{level}",
                                                     request={"kind": "system", "item": item, "level": level, "label": label, "nodes": list(dict.fromkeys(ids))[:12]})
                    if asked.duplicate:
                        continue
                    opened += 1
                    self.store.audit(tx, actor="gatekeeper", action="system.asked", project_id=project_id, tier=asked.tier, decision="ask", reason=f"{item}: {label}"[:200], ref=asked.id)
                    for node_id in dict.fromkeys(ids):
                        tx.conn.execute("UPDATE agent_nodes SET state = 'awaiting_system' WHERE id = ? AND state IN ('planned','queued')", (node_id,))
                        tx.emit("node.updated", {"project_id": project_id, "node_id": node_id, "state": "awaiting_system"})
                self.sync_cards(tx, project_id)
            return opened
        return await run_blocking(open_questions)

    def _release_system_nodes(self, tx: Tx, project_id: str, node_ids: Sequence[str]) -> None:
        """The steps that waited for one permission go on when nothing else holds them: `awaiting_system` becomes `planned` (no task yet or blocked) or `queued`, unless another open system
        question still names them."""
        still = {n for a in self.store.approvals(project_id, status="open") if a.request.get("kind") == "system" for n in (a.request.get("nodes") or [])}
        for node_id in node_ids:
            if node_id in still:
                continue
            row = tx.conn.execute("SELECT t.status AS tstatus FROM agent_nodes n LEFT JOIN tasks t ON t.id = n.task_id WHERE n.id = ? AND n.state = 'awaiting_system'", (node_id,)).fetchone()
            if row is None:
                continue
            state = "queued" if row["tstatus"] == "queued" else "planned"
            tx.conn.execute("UPDATE agent_nodes SET state = ? WHERE id = ?", (state, node_id))
            tx.emit("node.updated", {"project_id": project_id, "node_id": node_id, "state": state})

    async def system_check(self, project_id: str, item: str) -> dict[str, Any]:
        """"Check again": the probe runs again. If the permission is there now the question is answered (allow once, by the owner), the steps that waited go on and the project starts what can
        start; if not, the audit says `system.still_needed` and the card stays with its steps."""
        found = await run_blocking(self._find_system, project_id, item)
        level, label = str(found.request.get("level", "read")), str(found.request.get("label", ""))
        folder = self._folder_of()
        adapter = self._system_adapter()
        needs = await run_blocking(lambda: adapter.probe(Path(folder), write=level == "write")) if folder else []
        still = bool(needs) if item == "unknown" else any(need.item == item for need in needs)       # the late card has no item of its own: any need the probe finds keeps it open (G17)

        def work() -> str:
            with self.db.tx() as tx:
                if still:
                    self.store.audit(tx, actor="owner", action="system.still_needed", project_id=project_id, tier=found.tier, decision="n/a", reason=f"{item}: {label}"[:200], ref=found.id)
                    return "still"
                self.store.decide(tx, found.id, "allow_once", decided_by="owner")
                self.store.audit(tx, actor="owner", action="system.cleared", project_id=project_id, tier=found.tier, decision="allow", reason=f"{item}: {label}"[:200], ref=found.id)
                self._release_system_nodes(tx, project_id, list(found.request.get("nodes") or []))
                if found.request.get("late"):                                          # P3 (D322 g): the step that the computer refused gets ONE fresh attempt that spends no retry
                    for node_id in found.request.get("nodes") or []:
                        self.conductor.restart_after_permission(tx, str(node_id))
                return self._settle_answers(tx, project_id)
        outcome = await run_blocking(work)
        if outcome in ("running", "waiting", "ended") and not still and self.tasks is not None:
            await self.tasks.start_ready()
        return await run_blocking(self.snapshot, project_id)

    def _find_system(self, project_id: str, item: str) -> Any:
        for approval in self.store.approvals(project_id, status="open"):
            if approval.request.get("kind") == "system" and approval.request.get("item") == item:
                return approval
        raise NotFound("that question")

    async def system_skip(self, project_id: str, item: str) -> dict[str, Any]:
        """"Skip": the owner does not want to allow it. The question is answered no, and ONLY the steps that need it are cancelled ("skipped: the computer did not allow it"); the others run."""
        found = await run_blocking(self._find_system, project_id, item)

        def work() -> None:
            with self.db.tx() as tx:
                self.store.decide(tx, found.id, "deny", decided_by="owner")
                self.store.audit(tx, actor="owner", action="system.skipped", project_id=project_id, tier=found.tier, decision="deny", reason=f"{item}: {found.request.get('label', '')}"[:200], ref=found.id)
                for node_id in found.request.get("nodes") or []:
                    row = tx.conn.execute("SELECT n.state AS state, n.task_id AS task_id, t.status AS tstatus FROM agent_nodes n LEFT JOIN tasks t ON t.id = n.task_id WHERE n.id = ?", (node_id,)).fetchone()
                    if row is None or row["state"] != "awaiting_system":
                        continue
                    if row["task_id"] and row["tstatus"] in ("blocked", "queued"):
                        self.tasks.cancel_in(tx, row["task_id"], "skipped: the computer did not allow it")
                    else:
                        tx.conn.execute("UPDATE agent_nodes SET state = 'cancelled', failure_reason = ?, ended_at = ?, torn_down_at = ? WHERE id = ?",
                                        ("skipped: the computer did not allow it", tx.now(), tx.now(), node_id))
                        tx.emit("node.updated", {"project_id": project_id, "node_id": node_id, "state": "cancelled"})
                self.conductor._sync_project(tx, project_id)
                self._settle_answers(tx, project_id)
        await run_blocking(work)
        if self.tasks is not None:
            await self.tasks.start_ready()
        return await run_blocking(self.snapshot, project_id)

    def system_cards(self, project_id: str) -> list[SystemPermissionCard]:
        """The open permission questions of a project as cards, with the steps of THIS system in plain words."""
        adapter = self._system_adapter()
        cards = []
        for a in self.store.approvals(project_id, status="open"):
            if a.request.get("kind") != "system":
                continue
            need = syspermissions.Need(str(a.request.get("item", "unknown")), "write" if a.request.get("level") == "write" else "read", str(a.request.get("label", "")))
            cards.append(SystemPermissionCard(project_id=project_id, approval_id=a.id, item=need.item[:40], label=need.label[:200], level=need.level, steps=[s[:300] for s in adapter.explain(need)][:8],
                                              platform=str(getattr(adapter, "name", ""))[:20], affects=[str(n) for n in (a.request.get("nodes") or [])][:20]))
        return cards

    # ---- reading --------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _project_out(row: sqlite3.Row) -> ProjectOut:
        return ProjectOut(id=row["id"], request_id=row["request_id"], title=row["title"], status=row["status"], failure_policy=row["failure_policy"],
                          decide_for_me=bool(row["decide_for_me"]), paused=bool(row["paused"]), review_loops=row["review_loops"],
                          caps={key: value for key, value in json.loads(row["caps_json"] or "{}").items() if key != "plan"},
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
                "spend": {"calls": spend["calls"], "usd": round(spend["usd"], 6) if spend["usd"] is not None else None}, "approvals": approvals, "cards": [card.model_dump(mode="json") for card in self.approval_cards(project_id) if card.kind != "system"],
                "system_cards": [card.model_dump(mode="json") for card in self.system_cards(project_id)], "last_message_seq": last}

    @staticmethod
    def _conflict_edges(project: ProjectOut, nodes: Sequence[NodeOut]) -> list[tuple[str, str]]:
        by_ref = {n.plan_ref: n.id for n in nodes if n.plan_ref}
        return [(by_ref[a], by_ref[b]) for a, b in project.caps.get("conflict_edges", []) if a in by_ref and b in by_ref]    # type: ignore[union-attr]
