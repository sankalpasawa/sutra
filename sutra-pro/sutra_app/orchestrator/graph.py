"""The workflow graph store (orchestrator 3.4, 4.1, 6.2; D44, D62, D77; S3-web-04, S4-fnodes-10, S4-fnodes-14).

    store = GraphStore(db)                       # specs: FunctionSpecs, or None to read the shipped file on first use
    store.view(level="full", dept="web")         # GraphView: nodes in depth-first pre-order, derived + stored edges
    store.node("web.identity")                   # NodeDetail: the full function meta, atoms, usage, task, archived chats
    store.put_node(tx, checked_node)             # False when nothing changed; else version + 1 and one graph.updated
    store.put_edge(tx, checked_edge)             # a stored edge (handoff, step, speaks_to, depends_on) and both ends' edge_ids
    store.aggregate(tx)                          # department, division and root state from tasks and function nodes

What the store owns: the `graph_nodes` and `graph_edges` rows. What it only reads: `org_nodes`/`org_edges` (the chart, written by
ChartStore: the tree is never stored here, D2/I7), `org_charts`, `tasks`, `atoms`, `usage_ledger` and `chat_sessions`.

The order of `GraphView.nodes` is a depth-first pre-order [S3-web-04]: a node, then its children. The children of a node come as
its chart children by `org_edges.position`, then its five function nodes (identity, adaptation, priority, coordination, audit),
then its step nodes by creation (`ts`, then id). The edges are derived on read (`contains`, `has_function`, `has_step`) and
read from the table (`handoff`, `step`, `speaks_to`, `depends_on`).

One `graph.updated` per transaction: the first change in a transaction bumps `meta.graph_version` and emits the event; later
changes in the same transaction add to that same event before it is delivered (after COMMIT).
"""
import json
import logging
import sqlite3
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sutra_app.library.gate import GATE, Checked
from sutra_app.library.node import (
    FunctionNode, FunctionSpecs, GraphEdge, Node, STORED_EDGE_KINDS, hands_to, load_function_specs, step_node_id,
)
from sutra_app.library.types import FUNCTIONS, clip
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import (
    LIVE_STATUSES, AtomOut, ChatSessionOut, FnDetailMeta, FnMeta, FnStats, GraphEdgeOut, GraphNodeOut, GraphView,
    NodeDetail, TaskOut, UsageTotals,
)

__all__ = ["GraphStore", "RECENT_TERMINAL_TASKS", "ATOMS_SHOWN", "Level"]

log = logging.getLogger(__name__)

Level = Literal["chart", "full"]
RECENT_TERMINAL_TASKS = 5           # `full` shows every step of the live tasks and of this many newest finished tasks per department
ATOMS_SHOWN = 20                    # NodeDetail.atoms: the open atom(s), then this many newest others
CHART_KINDS = ("root", "department", "division")
_NODE_COLUMNS = "id, kind, department_id, parent_id, state, label, detail, chat_session_id, task_id, step_ref, version, body, ts"
_OPEN_TASK_STATUSES = ("blocked", "queued", "starting", "running", "waiting_user")
_STATUS_WORDS = {
    "done": "done", "done_with_open_items": "done with open items", "stopped": "stopped", "crashed": "crashed",
    "cancelled": "cancelled", "blocked": "waiting", "queued": "queued", "starting": "starting", "running": "running",
    "waiting_user": "waiting for you",
}
_RANK_CHART, _RANK_FUNCTION, _RANK_STEP = 0, 1, 2
_LAST = 10 ** 9


def _marks(count: int) -> str:
    return ",".join("?" * count)


def _ids_json(ids: Sequence[str]) -> str:
    """A JSON array for `IN (SELECT value FROM json_each(?))`: one bound parameter however many ids there are."""
    return json.dumps(list(ids))


def _out_kind(kind: str) -> str:
    return "function" if kind in FUNCTIONS else kind


@dataclass
class _Batch:
    """What one transaction has changed in the graph so far; `event` is the graph.updated that will be delivered."""

    event: Any
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges_added: int = 0
    edges_removed: int = 0

    def sync(self) -> None:
        self.event.data["nodes"] = list(self.nodes.values())
        self.event.data["edges_added"] = self.edges_added
        self.event.data["edges_removed"] = self.edges_removed


class GraphStore:
    """Reads the graph as the wire shows it and writes graph nodes and edges. Synchronous (async code uses `run_blocking`)."""

    def __init__(self, db: Database, *, specs: FunctionSpecs | Callable[[], FunctionSpecs] | None = None) -> None:
        self._db = db
        self._specs_source = specs
        self._specs: FunctionSpecs | None = specs if isinstance(specs, FunctionSpecs) else None
        self._batches: "weakref.WeakKeyDictionary[Tx, _Batch]" = weakref.WeakKeyDictionary()

    # ---- specs (constraints of a function node come from here, never from the stored body) --------------------------

    def specs(self) -> FunctionSpecs:
        if self._specs is None:
            source = self._specs_source
            self._specs = source() if callable(source) else load_function_specs()
        return self._specs

    # =================================================================================================================
    # reads
    # =================================================================================================================

    def view(self, *, level: Level = "chart", dept: str | None = None, task: str | None = None) -> GraphView:
        """`chart`: the root, every department and division, and each department's latest task step. `full`: adds the function
        nodes and every step of the live tasks and of the newest finished ones. `dept` keeps that department's subtree and the
        way up to the root; `task` keeps only that task's steps. One read transaction."""
        if level not in ("chart", "full"):
            raise ValueError(f"level is 'chart' or 'full', not {level!r}")
        with self._db.read() as conn:
            if dept is not None:
                found = conn.execute("SELECT kind FROM graph_nodes WHERE id = ?", (dept,)).fetchone()
                if found is None or found["kind"] != "department":
                    raise NotFound("that team")
            if task is not None and conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task,)).fetchone() is None:
                raise NotFound("that task")
            return self._view(conn, level, dept, task)

    def node(self, node_id: str) -> NodeDetail:
        """The drawer's data: the node with its full meta, its active chat session, the open atom(s) first and then the newest
        20, usage totals (stub rows excluded), its task and the chats filed under it or archived by the owner."""
        with self._db.read() as conn:
            row = conn.execute(f"SELECT {_NODE_COLUMNS} FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
            if row is None:
                raise NotFound("that node")
            out = self._outs(conn, [row], detail=True)[0]
            session = conn.execute("SELECT * FROM chat_sessions WHERE node_id = ? AND status = 'active'", (node_id,)).fetchone()
            archived = conn.execute(
                "SELECT * FROM chat_sessions WHERE filed_under = ? OR (node_id = ? AND status = 'archived' "
                "AND EXISTS (SELECT 1 FROM chat_messages m WHERE m.session_id = chat_sessions.id)) ORDER BY created_at, id",
                (node_id, node_id)).fetchall()      # merged-away chats filed under it, and the owner's own archived ones (an empty one, such as the replacement
                                                    # that archiving started and bringing the old chat back set aside, has nothing to show: not listed)
            return NodeDetail(
                node=out, session=_session_out(session) if session is not None else None,
                atoms=self._atoms(conn, node_id),
                usage_total=_usage_totals(conn, "dept_id" if row["kind"] == "department" else "node_id", node_id),
                task=self._task_for(conn, row), archived_chats=[_session_out(s) for s in archived])

    def get(self, node_id: str) -> Node | None:
        """The stored node (the library model) or None."""
        return _stored_node(self._db.conn(), node_id)

    # ---- the view ---------------------------------------------------------------------------------------------------

    def _view(self, conn: sqlite3.Connection, level: Level, dept: str | None, task: str | None) -> GraphView:
        version = _meta_int(conn, "graph_version")
        chart_version = int(conn.execute("SELECT COALESCE(MAX(revision), 0) FROM org_charts").fetchone()[0])
        step_tasks = self._step_tasks(conn, level, dept, task)
        step_filter = "kind = 'step' AND task_id IN (SELECT value FROM json_each(?))" + (" AND step_ref = 'task'" if level == "chart" else "")
        where = f"kind IN ('root','department','division') OR ({step_filter})" if level == "chart" else f"kind != 'step' OR ({step_filter})"
        rows = {r["id"]: r for r in conn.execute(f"SELECT {_NODE_COLUMNS} FROM graph_nodes WHERE {where}", (_ids_json(step_tasks),))}

        order: dict[str, int] = {}
        chart_parent: dict[str, str] = {}
        for edge in conn.execute("SELECT parent_id, child_id, position FROM org_edges"):
            chart_parent[edge["child_id"]] = edge["parent_id"]
            order[edge["child_id"]] = edge["position"]
        parent_of: dict[str, str | None] = {}
        sort_key: dict[str, tuple] = {}
        for node_id, row in rows.items():
            kind = row["kind"]
            if kind in CHART_KINDS:
                parent_of[node_id] = chart_parent.get(node_id) or row["parent_id"]
                sort_key[node_id] = (_RANK_CHART, order.get(node_id, _LAST), 0, node_id)
            elif kind in FUNCTIONS:
                parent_of[node_id] = row["department_id"]
                sort_key[node_id] = (_RANK_FUNCTION, FUNCTIONS.index(kind), 0, node_id)
            else:
                parent_of[node_id] = row["parent_id"]
                sort_key[node_id] = (_RANK_STEP, row["ts"], 0, node_id)
        children: dict[str, list[str]] = {}
        roots: list[str] = []
        for node_id in rows:
            parent = parent_of[node_id]
            if parent is not None and parent in rows and parent != node_id:
                children.setdefault(parent, []).append(node_id)
            else:
                roots.append(node_id)
        for kids in children.values():
            kids.sort(key=sort_key.__getitem__)
        roots.sort(key=lambda n: (0 if rows[n]["kind"] == "root" else 1, sort_key[n]))

        keep: set[str] | None = None
        if dept is not None:
            keep = _subtree(dept, children)
            up = parent_of.get(dept)
            while up is not None and up in rows and up not in keep:
                keep.add(up)
                up = parent_of.get(up)

        ordered: list[str] = []
        edges: list[GraphEdgeOut] = []
        seen: set[str] = set()
        stack = [n for n in reversed(roots) if keep is None or n in keep]
        while stack:
            node_id = stack.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            ordered.append(node_id)
            kids = [k for k in children.get(node_id, ()) if keep is None or k in keep]
            for kid in kids:
                rank = sort_key[kid][0]
                edges.append(GraphEdgeOut(src=node_id, dst=kid, kind=("contains", "has_function", "has_step")[rank]))
            stack.extend(reversed(kids))

        shown = set(ordered)
        for edge in conn.execute("SELECT kind, from_id, to_id, label, body FROM graph_edges ORDER BY id"):
            if edge["from_id"] in shown and edge["to_id"] in shown:
                label = edge["label"]
                if not label:
                    count = json.loads(edge["body"]).get("n")
                    label = str(count) if count is not None else ""
                edges.append(GraphEdgeOut(src=edge["from_id"], dst=edge["to_id"], kind=edge["kind"], label=label))
        nodes = self._outs(conn, [rows[n] for n in ordered], detail=False)
        return GraphView(version=version, chart_version=chart_version, nodes=nodes, edges=edges)

    def _step_tasks(self, conn: sqlite3.Connection, level: Level, dept: str | None, task: str | None) -> list[str]:
        """The tasks whose step nodes the view shows."""
        if task is not None:
            return [task]
        sql = "SELECT id, dept_id, status FROM tasks" + (" WHERE dept_id = ?" if dept is not None else "") + " ORDER BY created_at DESC, rowid DESC"
        chosen: list[str] = []
        finished: dict[str, int] = {}
        seen_dept: set[str] = set()
        for t in conn.execute(sql, (dept,) if dept is not None else ()):
            if level == "chart":
                if t["dept_id"] not in seen_dept:
                    seen_dept.add(t["dept_id"])
                    chosen.append(t["id"])
            elif t["status"] in _OPEN_TASK_STATUSES:
                chosen.append(t["id"])
            elif finished.get(t["dept_id"], 0) < RECENT_TERMINAL_TASKS:
                finished[t["dept_id"]] = finished.get(t["dept_id"], 0) + 1
                chosen.append(t["id"])
        return chosen

    # ---- rows to the wire --------------------------------------------------------------------------------------------

    def _outs(self, conn: sqlite3.Connection, rows: Sequence[sqlite3.Row], *, detail: bool) -> list[GraphNodeOut]:
        function_ids = [r["id"] for r in rows if r["kind"] in FUNCTIONS]
        counts = _atom_counts(conn, function_ids)
        dept_ids = [r["id"] for r in rows if r["kind"] == "department"]
        dept_runs = _department_runs(conn, dept_ids)
        task_runs = _task_runs(conn, [r["task_id"] for r in rows if r["kind"] == "step"])
        out: list[GraphNodeOut] = []
        for row in rows:
            kind = row["kind"]
            meta: dict[str, Any] = {}
            if kind == "department":
                if row["id"] in dept_runs:
                    meta["run_id"] = dept_runs[row["id"]]
            elif kind == "step":
                if task_runs.get(row["task_id"]):
                    meta["run_id"] = task_runs[row["task_id"]]
            elif kind in FUNCTIONS:
                meta = self._function_meta(row, counts.get(row["id"], {}), detail)
            out.append(GraphNodeOut(
                id=row["id"], kind=_out_kind(kind), label=row["label"], status=row["state"], detail=row["detail"],
                chat_session_id=row["chat_session_id"], org_node_id=row["id"] if kind in CHART_KINDS else None,
                dept_id=row["department_id"], task_id=row["task_id"], fn=kind if kind in FUNCTIONS else None,
                step_ref=row["step_ref"], version=row["version"], meta=meta))
        return out

    def _function_meta(self, row: sqlite3.Row, counts: dict[str, int], detail: bool) -> dict[str, Any]:
        """`{stats, wait_on}` for the view and for `graph.updated`; the seven keys of the drawer for NodeDetail."""
        body = json.loads(row["body"])
        stored = body.get("stats") or {}
        tokens = stored.get("tokens") or {}
        stats = FnStats(
            calls=stored.get("calls", 0), seconds=float(stored.get("seconds", 0.0)), tokens_in=tokens.get("input", 0),
            tokens_out=tokens.get("output", 0), atoms_open=counts.get("open", 0), atoms_closed=counts.get("closed", 0),
            atoms_failed=counts.get("verify_failed", 0), atoms_total=sum(counts.values()))
        wait_on = body.get("wait_on")
        if not detail:
            return FnMeta(stats=stats, wait_on=wait_on).model_dump(mode="json")
        spec = self.specs().specs[row["kind"]]
        return FnDetailMeta(
            goal=body["goal"], task=body["task"], context=list(body.get("context", [])), constraints=list(spec.may_not),
            wait_on=wait_on, hands_to=hands_to(row["kind"]), stats=stats).model_dump(mode="json")

    def _atoms(self, conn: sqlite3.Connection, node_id: str) -> list[AtomOut]:
        columns = "id, schema, node_id, task_id, display, attempt, goal, body, ts_open, ts_closed"
        opened = conn.execute(
            f"SELECT {columns} FROM atoms WHERE node_id = ? AND display = 'open' ORDER BY ts_open DESC, rowid DESC", (node_id,)).fetchall()
        newest = conn.execute(
            f"SELECT {columns} FROM atoms WHERE node_id = ? AND display != 'open' ORDER BY ts_open DESC, rowid DESC LIMIT ?",
            (node_id, ATOMS_SHOWN)).fetchall()
        rows = [*opened, *newest]
        usage = _atom_usage(conn, [r["id"] for r in rows])
        return [AtomOut(
            id=r["id"], schema=r["schema"], node_id=r["node_id"], task_id=r["task_id"], state=r["display"], goal=r["goal"],
            attempt=r["attempt"], ts_open=iso_z(r["ts_open"]), ts_closed=iso_z(r["ts_closed"]) if r["ts_closed"] is not None else None,
            body=json.loads(r["body"]), usage=usage.get(r["id"], UsageTotals())) for r in rows]

    def _task_for(self, conn: sqlite3.Connection, row: sqlite3.Row) -> TaskOut | None:
        """A step node's own task; for a department or one of its function nodes the department's live task; else None."""
        if row["kind"] == "step":
            found = conn.execute("SELECT * FROM tasks WHERE id = ?", (row["task_id"],)).fetchone()
        elif row["kind"] == "department" or row["kind"] in FUNCTIONS:
            dept = row["id"] if row["kind"] == "department" else row["department_id"]
            found = conn.execute(
                f"SELECT * FROM tasks WHERE dept_id = ? AND status IN ({_marks(len(LIVE_STATUSES))}) ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (dept, *LIVE_STATUSES)).fetchone()
        else:
            found = None
        return _task_out(conn, found) if found is not None else None

    # =================================================================================================================
    # writes (the server is the only writer; every change is inside the caller's Database.tx())
    # =================================================================================================================

    def touch(self, tx: Tx) -> int:
        """Count this transaction as a graph change (once) and return the new `graph_version`. `ChartStore.apply` calls it so a
        change that only reuses nodes still moves the version."""
        return self._batch(tx).event.data["version"]

    def put_node(self, tx: Tx, node: Checked[Node]) -> bool:
        """Store a checked node. False (nothing written, no event) when it equals the stored one apart from `version` and
        `ts_updated`; else the row's `version` becomes 1 (new) or the old one + 1, and the node joins this transaction's
        graph.updated. The store owns `edge_ids` (always the ids of the stored edges that touch the node) and keeps a node's
        session: a node that arrives without `chat_session_id` keeps the stored one."""
        _require(node, "node", "put_node")
        model = node.model
        if model.kind == "step" and model.id != step_node_id(model.task_id, model.step_ref):
            raise ValueError(f"the id of a step node is step_node_id(task_id, step_ref), not {model.id!r}")
        row = tx.conn.execute(f"SELECT {_NODE_COLUMNS} FROM graph_nodes WHERE id = ?", (model.id,)).fetchone()
        changes: dict[str, Any] = {}
        wanted_edges = _edge_ids_of(tx.conn, model.id)
        if list(model.edge_ids) != wanted_edges:
            changes["edge_ids"] = wanted_edges
        if row is not None and model.chat_session_id is None and row["chat_session_id"]:
            changes["chat_session_id"] = row["chat_session_id"]
        if changes:
            node = GATE.check("node", model.evolve(**changes), ctx=tx.ctx)
            model = node.model
        if row is not None and _same_node(json.loads(row["body"]), json.loads(node.json)):
            return False
        values = (
            model.kind, model.department_id, getattr(model, "parent_id", None), model.state, model.label, model.detail,
            model.chat_session_id, getattr(model, "task_id", None), getattr(model, "step_ref", None), node.json, node.sha256)
        if row is None:
            tx.conn.execute(
                f"INSERT INTO graph_nodes (kind, department_id, parent_id, state, label, detail, chat_session_id, task_id, step_ref, body, sha256, id, version, ts)"
                f" VALUES ({_marks(11)}, ?, 1, ?)", (*values, model.id, model.ts_created or tx.now()))
        else:
            tx.conn.execute(
                "UPDATE graph_nodes SET kind=?, department_id=?, parent_id=?, state=?, label=?, detail=?, chat_session_id=?, task_id=?,"
                " step_ref=?, body=?, sha256=?, version=version+1 WHERE id=?", (*values, model.id))
        self._note_node(tx, model.id)
        return True

    def put_edge(self, tx: Tx, edge: Checked[GraphEdge]) -> bool:
        """Store a checked edge of a stored kind (handoff, step, speaks_to, depends_on). A derived kind (contains, has_function,
        has_step) is refused: the graph can never become a second chart (I7). False when unchanged. Both ends list the edge in
        their `edge_ids` afterwards."""
        _require(edge, "edge", "put_edge")
        model = edge.model
        if model.kind not in STORED_EDGE_KINDS:
            raise ValueError(f"a {model.kind} edge is derived on read and never stored (stored kinds: {', '.join(STORED_EDGE_KINDS)})")
        row = tx.conn.execute("SELECT body FROM graph_edges WHERE id = ?", (model.id,)).fetchone()
        if row is not None and _same_edge(json.loads(row["body"]), json.loads(edge.json)):
            return False
        task_row = tx.conn.execute(
            "SELECT task_id FROM graph_nodes WHERE id IN (?, ?) AND task_id IS NOT NULL ORDER BY id LIMIT 1", (model.from_id, model.to_id)).fetchone()
        task_id = task_row["task_id"] if task_row is not None else None
        if row is None:
            tx.conn.execute(
                "INSERT INTO graph_edges (id, kind, from_id, to_id, status, label, task_id, version, body) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (model.id, model.kind, model.from_id, model.to_id, model.status, model.label, task_id, edge.json))
        else:
            tx.conn.execute(
                "UPDATE graph_edges SET status=?, label=?, task_id=?, body=?, version=version+1 WHERE id=?",
                (model.status, model.label, task_id, edge.json, model.id))
        batch = self._batch(tx)
        if row is None:
            batch.edges_added += 1
        batch.sync()
        for end in dict.fromkeys((model.from_id, model.to_id)):
            self._resync_edge_ids(tx, end)
        return True

    def delete_edge(self, tx: Tx, edge_id: str) -> bool:
        """Remove a stored edge and take it out of both ends' `edge_ids`. False when there is no such edge."""
        row = tx.conn.execute("SELECT from_id, to_id FROM graph_edges WHERE id = ?", (edge_id,)).fetchone()
        if row is None:
            return False
        tx.conn.execute("DELETE FROM graph_edges WHERE id = ?", (edge_id,))
        batch = self._batch(tx)
        batch.edges_removed += 1
        batch.sync()
        for end in dict.fromkeys((row["from_id"], row["to_id"])):
            self._resync_edge_ids(tx, end)
        return True

    def delete_node(self, tx: Tx, node_id: str) -> bool:
        """Remove a graph node and the stored edges that touch it (a merged-away division's node is deleted, not archived).
        False when there is no such node. Rows that still point at it (atoms, usage) make SQLite refuse, which is a bug upstream."""
        if tx.conn.execute("SELECT 1 FROM graph_nodes WHERE id = ?", (node_id,)).fetchone() is None:
            return False
        touching = tx.conn.execute("SELECT id, from_id, to_id FROM graph_edges WHERE from_id = ? OR to_id = ?", (node_id, node_id)).fetchall()
        tx.conn.execute("DELETE FROM graph_edges WHERE from_id = ? OR to_id = ?", (node_id, node_id))
        tx.conn.execute("DELETE FROM graph_nodes WHERE id = ?", (node_id,))
        batch = self._batch(tx)
        batch.edges_removed += len(touching)
        batch.nodes.pop(node_id, None)
        batch.sync()
        others = {end for e in touching for end in (e["from_id"], e["to_id"])} - {node_id}
        for end in sorted(others):
            self._resync_edge_ids(tx, end)
        return True

    def aggregate(self, tx: Tx) -> None:
        """Set the state of every department, division and the root from the tasks and the function nodes [5.6]:

        department  a live task: `waiting_on_you` when the task waits for the owner or a function node does, else `running`
                    (its detail stays as the projector wrote it); no live task: `fault` when its newest task crashed, else `idle`,
                    with the detail 'last: <title>, <how it ended>' ('' when it never had a task)
        division    the department's state while a task scoped to the division is live, else `idle`
        root        `waiting_on_you` over `running` over `idle` among the departments
        """
        conn = tx.conn
        live = {t["dept_id"]: t for t in conn.execute(
            f"SELECT dept_id, scope_node_id, status FROM tasks WHERE status IN ({_marks(len(LIVE_STATUSES))})", LIVE_STATUSES)}
        last = {t["dept_id"]: t for t in conn.execute(
            "SELECT t.dept_id, t.title, t.status FROM tasks t WHERE t.rowid = (SELECT u.rowid FROM tasks u WHERE u.dept_id = t.dept_id"
            " ORDER BY u.created_at DESC, u.rowid DESC LIMIT 1)")}
        asking = {r[0] for r in conn.execute(
            f"SELECT DISTINCT department_id FROM graph_nodes WHERE state = 'waiting_on_you' AND kind IN ({_marks(len(FUNCTIONS))})", FUNCTIONS)}
        dept_state: dict[str, str] = {}
        for dept in conn.execute("SELECT id FROM graph_nodes WHERE kind = 'department' ORDER BY id").fetchall():
            dept_id = dept["id"]
            task = live.get(dept_id)
            if task is not None:
                state = "waiting_on_you" if task["status"] == "waiting_user" or dept_id in asking else "running"
                self._set_state(tx, dept_id, state, None)
            else:
                ended = last.get(dept_id)
                state = "fault" if ended is not None and ended["status"] == "crashed" else "idle"
                text = f"last: {ended['title']}, {_STATUS_WORDS.get(ended['status'], ended['status'])}" if ended is not None else ""
                self._set_state(tx, dept_id, state, clip(text, 300))
            dept_state[dept_id] = state
        for div in conn.execute("SELECT id, department_id FROM graph_nodes WHERE kind = 'division' ORDER BY id").fetchall():
            task = live.get(div["department_id"])
            mirrored = task is not None and task["scope_node_id"] == div["id"]
            self._set_state(tx, div["id"], dept_state.get(div["department_id"], "idle") if mirrored else "idle", None)
        states = set(dept_state.values())
        root = "waiting_on_you" if "waiting_on_you" in states else "running" if "running" in states else "idle"
        for row in conn.execute("SELECT id FROM graph_nodes WHERE kind = 'root'").fetchall():
            self._set_state(tx, row["id"], root, None)

    # ---- write helpers -------------------------------------------------------------------------------------------------

    def _set_state(self, tx: Tx, node_id: str, state: str, detail: str | None) -> None:
        model = tx.ctx.get("node", node_id)
        if model is None or (model.state == state and (detail is None or model.detail == detail)):
            return
        changes: dict[str, Any] = {"state": state, "ts_updated": tx.now()}
        if detail is not None:
            changes["detail"] = detail
        self.put_node(tx, GATE.check("node", model.evolve(**changes), ctx=tx.ctx))

    def _resync_edge_ids(self, tx: Tx, node_id: str) -> None:
        """Re-store a node unchanged so that `put_node` brings its `edge_ids` up to the stored edges."""
        model = tx.ctx.get("node", node_id)
        if model is not None:
            self.put_node(tx, GATE.check("node", model, ctx=tx.ctx))

    def _batch(self, tx: Tx) -> _Batch:
        batch = self._batches.get(tx)
        if batch is None:
            row = tx.conn.execute("SELECT value FROM meta WHERE key = 'graph_version'").fetchone()
            version = (int(row[0]) if row is not None else 0) + 1
            tx.conn.execute(
                "INSERT INTO meta (key, value) VALUES ('graph_version', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(version),))
            tx.emit("graph.updated", {"version": version, "nodes": [], "edges_added": 0, "edges_removed": 0})
            batch = _Batch(event=tx.pending[-1])
            self._batches[tx] = batch
        return batch

    def _note_node(self, tx: Tx, node_id: str) -> None:
        batch = self._batch(tx)
        row = tx.conn.execute(f"SELECT {_NODE_COLUMNS} FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
        batch.nodes[node_id] = self._outs(tx.conn, [row], detail=False)[0].model_dump(mode="json")
        batch.sync()


# ---- module helpers ------------------------------------------------------------------------------------------------------

def _require(checked: Any, family: str, where: str) -> None:
    if not isinstance(checked, Checked):
        raise TypeError(f"{where} takes a Checked {family} from Gate.check, not {type(checked).__name__}")
    if checked.family != family:
        raise TypeError(f"{where} takes a Checked {family}, not a Checked {checked.family}")


def _stored_node(conn: sqlite3.Connection, node_id: str) -> Node | None:
    from sutra_app.orchestrator.db import StoreContext
    return StoreContext(conn).get("node", node_id)


def _same_node(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Equal apart from `version` and `ts_updated`: a caller that restamps a node must not make it look changed."""
    return {k: v for k, v in old.items() if k not in ("version", "ts_updated")} == {k: v for k, v in new.items() if k not in ("version", "ts_updated")}


def _same_edge(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return {k: v for k, v in old.items() if k != "version"} == {k: v for k, v in new.items() if k != "version"}


def _edge_ids_of(conn: sqlite3.Connection, node_id: str) -> list[str]:
    return [r[0] for r in conn.execute("SELECT id FROM graph_edges WHERE from_id = ? OR to_id = ? ORDER BY id", (node_id, node_id))]


def _meta_int(conn: sqlite3.Connection, key: str) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return int(row[0]) if row is not None else 0


def _subtree(root: str, children: dict[str, list[str]]) -> set[str]:
    found, stack = set(), [root]
    while stack:
        node_id = stack.pop()
        if node_id not in found:
            found.add(node_id)
            stack.extend(children.get(node_id, ()))
    return found


def _atom_counts(conn: sqlite3.Connection, node_ids: Sequence[str]) -> dict[str, dict[str, int]]:
    """node id -> {display word: count} for the given nodes: one GROUP BY over atoms.display."""
    out: dict[str, dict[str, int]] = {}
    if node_ids:
        for r in conn.execute(
                "SELECT node_id, display, count(*) AS n FROM atoms WHERE node_id IN (SELECT value FROM json_each(?)) GROUP BY node_id, display",
                (_ids_json(node_ids),)):
            out.setdefault(r["node_id"], {})[r["display"]] = r["n"]
    return out


def _department_runs(conn: sqlite3.Connection, dept_ids: Sequence[str]) -> dict[str, str]:
    """The run a department node points at: its live task's run, else its newest task that has a run."""
    out: dict[str, str] = {}
    if not dept_ids:
        return out
    ids = _ids_json(dept_ids)
    for r in conn.execute(
            "SELECT t.dept_id, t.run_id FROM tasks t WHERE t.run_id IS NOT NULL AND t.dept_id IN (SELECT value FROM json_each(?))"
            " AND t.rowid = (SELECT u.rowid FROM tasks u WHERE u.dept_id = t.dept_id AND u.run_id IS NOT NULL ORDER BY u.created_at DESC, u.rowid DESC LIMIT 1)",
            (ids,)):
        out[r["dept_id"]] = r["run_id"]
    for r in conn.execute(
            f"SELECT dept_id, run_id FROM tasks WHERE run_id IS NOT NULL AND status IN ({_marks(len(LIVE_STATUSES))})"
            " AND dept_id IN (SELECT value FROM json_each(?)) ORDER BY created_at, rowid", (*LIVE_STATUSES, ids)):
        out[r["dept_id"]] = r["run_id"]
    return out


def _task_runs(conn: sqlite3.Connection, task_ids: Sequence[str | None]) -> dict[str, str | None]:
    found = [t for t in dict.fromkeys(task_ids) if t]
    if not found:
        return {}
    return {r["id"]: r["run_id"] for r in conn.execute("SELECT id, run_id FROM tasks WHERE id IN (SELECT value FROM json_each(?))", (_ids_json(found),))}


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _usage_totals(conn: sqlite3.Connection, column: Literal["node_id", "dept_id", "task_id"], value: str) -> UsageTotals:
    """Calls and sums over the ledger rows of one owner, stub rows left out; a sum is null when every row's part is null."""
    row = conn.execute(
        f"SELECT count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger"
        f" WHERE {column} = ? AND provider != 'stub'", (value,)).fetchone()
    return UsageTotals(calls=row["calls"], usd=_round(row["usd"]), tokens_in=row["tin"], tokens_out=row["tout"])


def _atom_usage(conn: sqlite3.Connection, atom_ids: Sequence[str]) -> dict[str, UsageTotals]:
    out: dict[str, UsageTotals] = {}
    if atom_ids:
        for r in conn.execute(
                "SELECT atom_id, count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger"
                " WHERE provider != 'stub' AND atom_id IN (SELECT value FROM json_each(?)) GROUP BY atom_id", (_ids_json(atom_ids),)):
            out[r["atom_id"]] = UsageTotals(calls=r["calls"], usd=_round(r["usd"]), tokens_in=r["tin"], tokens_out=r["tout"])
    return out


def _session_out(row: sqlite3.Row) -> ChatSessionOut:
    return ChatSessionOut(
        id=row["id"], node_id=row["node_id"], kind=row["kind"], title=row["title"], writable=bool(row["writable"]), status=row["status"],
        filed_under=row["filed_under"], connector=row["connector"], model=row["model"], provider_session_id=row["provider_session_id"],
        last_message_id=row["last_message_id"], note=row["note"])


def _task_out(conn: sqlite3.Connection, row: sqlite3.Row) -> TaskOut:
    name = conn.execute("SELECT name FROM org_nodes WHERE id = ?", (row["dept_id"],)).fetchone()
    return TaskOut(
        id=row["id"], dept_id=row["dept_id"], dept_name=name["name"] if name is not None else row["dept_id"],
        scope_node_id=row["scope_node_id"], title=row["title"], status=row["status"], run_id=row["run_id"],
        parent_task_id=row["parent_task_id"], depends_on=json.loads(row["depends_on"]), outcome=row["outcome"],
        created_at=iso_z(row["created_at"]), started_at=iso_z(row["started_at"]) if row["started_at"] is not None else None,
        ended_at=iso_z(row["ended_at"]) if row["ended_at"] is not None else None, usage=_usage_totals(conn, "task_id", row["id"]))
