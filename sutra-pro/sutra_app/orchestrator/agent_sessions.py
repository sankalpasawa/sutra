"""The chat session of every agent (agent-sessions design 3.1, 3.3, D130, D131).

    agent_of(conn, sid) -> AgentRef | None         what an agent session is: its agent name, team, task, run (None for every other chat)
    effective(conn, sid, default) -> dict          the pick the session runs on and where it comes from: own > run > team > policy default
    sessions = AgentSessions(db, graph)
    sessions.open(tx, task_row, node_id) -> sid    the session an agent's line goes to in this run (rolls a function agent's used session, D130)

A function agent's session (the five functions) and a builder's step session (`W-n`) are read-only logs of one agent. Which model and effort that agent
runs on is a cascade, a whole pick at a time (`chat_v2.cascade`): its own session's pick, the run's (`tasks.pick_json`), the team's (the team chat's pill),
then the policy default.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sutra_app.connectors.models import Pick
from sutra_app.library.gate import GATE
from sutra_app.library.types import FUNCTIONS, clip
from sutra_app.orchestrator.chat_v2 import ChatArchive, ChatChoices, cascade
from sutra_app.orchestrator.chats import _SESSION_COLUMNS, _session_record
from sutra_app.orchestrator.db import Database, Tx

__all__ = ["AgentRef", "AgentSessions", "agent_of", "effective", "pick_dict", "session_title", "team_agents"]

TITLE_TASK_CHARS = 40


@dataclass(frozen=True)
class AgentRef:
    """An agent session's identity: `agent` is the name the engine tags its calls with (identity, ..., W-3); `kind` is function or step."""

    session_id: str
    kind: str
    agent: str
    node_id: str
    dept_id: str | None
    task_id: str | None
    run_id: str | None
    status: str


def agent_of(conn: sqlite3.Connection, session_id: str) -> AgentRef | None:
    """The agent a function or step session belongs to, or None for any other session (or an unknown one)."""
    row = conn.execute("SELECT id, kind, node_id, status, run_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None or row["kind"] not in ("function", "step"):
        return None
    node = conn.execute("SELECT kind, department_id, task_id, step_ref FROM graph_nodes WHERE id = ?", (row["node_id"],)).fetchone()
    if node is None:
        return None
    agent = node["step_ref"] if row["kind"] == "step" else node["kind"]
    task_id = node["task_id"] if row["kind"] == "step" else None
    if task_id is None and row["run_id"]:
        found = conn.execute("SELECT id FROM tasks WHERE run_id = ?", (row["run_id"],)).fetchone()
        task_id = found["id"] if found is not None else None
    return AgentRef(session_id=row["id"], kind=row["kind"], agent=agent or "", node_id=row["node_id"], dept_id=node["department_id"],
                    task_id=task_id, run_id=row["run_id"], status=row["status"])


def pick_dict(pick: Pick | None) -> dict[str, Any] | None:
    """`{provider, model, effort}` of a pick that names a provider, else None."""
    if pick is None or not pick.provider:
        return None
    return {"provider": pick.provider, "model": pick.model, "effort": pick.effort}


def team_pick(conn: sqlite3.Connection, dept_id: str | None) -> Pick:
    """The team's pick: its chat's pill."""
    found = conn.execute("SELECT chat_session_id FROM graph_nodes WHERE id = ?", (dept_id,)).fetchone() if dept_id else None
    return ChatChoices.pick_in(conn, found["chat_session_id"] if found is not None else None)


def effective(conn: sqlite3.Connection, session_id: str, default: Callable[[str], Pick] | Pick | None = None) -> dict[str, Any]:
    """`{provider, model, effort, source}` for any chat. A function or step session resolves own > run > team > default; any other chat is its own pick, else
    the default. `default` is the policy's answer for an agent (`ChatPort.default_pick`), called with the agent's name, or a ready `Pick`; None says
    nothing is known (all fields null, source default). Never raises for a missing piece."""
    own = ChatChoices.pick_in(conn, session_id)
    ref = agent_of(conn, session_id)
    run = Pick()
    team = Pick()
    if ref is not None:
        if ref.task_id is not None:
            from sutra_app.orchestrator.tasks import TaskStore
            run = TaskStore.pick_in(conn, ref.task_id)
        team = team_pick(conn, ref.dept_id)
    fallback = default(ref.agent if ref is not None else "") if callable(default) else default
    chosen, source = cascade(own, run, team, fallback)
    return {"provider": chosen.provider or None, "model": chosen.model, "effort": chosen.effort, "source": source}


def session_title(kind: str, agent: str, label: str, task_title: str) -> str:
    """The title of an agent's session: a function agent's is `Identity · <task title, 40 characters>`; a builder's is `W-3 · <workflow name>`
    (a step whose label is its own ref has just the ref, and the task's own log keeps the task's title)."""
    if kind == "function":
        return clip(f"{agent.capitalize()} · {clip(task_title, TITLE_TASK_CHARS)}", 200)
    if agent == "task" or not label or label == agent:
        return clip(label or agent, 200)
    return clip(f"{agent} · {label}", 200)


class AgentSessions:
    """Opens the chat session an agent works in for one run (D130). Used by the Projector for every line an agent says, every `node` event and every
    usage row, and by `TaskGraph.ensure_step` when a builder's step node is made, so that one place knows which session is current.

    A builder's step session is made with its node (`ensure_node`, one transaction) and is stamped with the run and titled here. A function agent's
    session is the node's active session (invariant I1) and is rolled at the agent's first event of each run: when the active session holds lines of an
    earlier run, it is archived and its replacement is started in the same transaction (`ChatArchive`, which carries the owner's pick over), then the
    replacement is stamped and titled. A session with no lines is only stamped, so nothing churns."""

    def __init__(self, db: Database, graph: Any) -> None:
        self.db = db
        self.graph = graph

    def open(self, tx: Tx, row: Any, node_id: str | None) -> str | None:
        """The session id the lines of `node_id` belong to in the run of `row` (a TaskRow), or None for a node with no session. Idempotent."""
        if not node_id:
            return None
        conn = tx.conn
        node = conn.execute("SELECT kind, chat_session_id, step_ref, label FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
        if node is None or not node["chat_session_id"]:
            return None
        sid: str = node["chat_session_id"]
        run = getattr(row, "run_id", None)
        session = conn.execute(f"SELECT {_SESSION_COLUMNS} FROM chat_sessions WHERE id = ?", (sid,)).fetchone()
        if session is None or session["kind"] not in ("function", "step"):
            return sid
        is_step = session["kind"] == "step"
        agent = node["step_ref"] if is_step else node["kind"]
        title = session_title(session["kind"], agent or "", node["label"], getattr(row, "title", ""))
        if run is None:                                     # not started: a step is titled, nothing else can be said
            if is_step and session["title"] != title:
                self._stamp(tx, session, run_id=None, title=title)
            return sid
        if session["run_id"] == run:
            if is_step and session["title"] != title:       # a workflow's name arrives with its `step` event, after the node was made
                self._stamp(tx, session, run_id=run, title=title)
            return sid
        rolled_from = None
        if not is_step and conn.execute("SELECT 1 FROM chat_messages WHERE session_id = ? LIMIT 1", (sid,)).fetchone() is not None:
            ChatArchive(self.db, self.graph).archive(tx, sid)          # the used session is archived and its replacement started, in this transaction
            rolled_from = sid
            sid = conn.execute("SELECT chat_session_id FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()["chat_session_id"]
            session = conn.execute(f"SELECT {_SESSION_COLUMNS} FROM chat_sessions WHERE id = ?", (sid,)).fetchone()
        self._stamp(tx, session, run_id=run, title=title)
        if agent != "task":
            payload: dict[str, Any] = {"session_id": sid, "node_id": node_id, "agent": agent, "run_id": run}
            if rolled_from is not None:
                payload["rolled_from"] = rolled_from
            tx.emit("agent.session", payload)
        return sid

    @staticmethod
    def _stamp(tx: Tx, session: sqlite3.Row, *, run_id: str | None, title: str) -> None:
        checked = GATE.check("chat_session", _session_record(session).evolve(
            run_id=run_id, title=title, updated_at=max(session["updated_at"], tx.now())), ctx=tx.ctx)
        s = checked.model
        tx.conn.execute("UPDATE chat_sessions SET run_id = ?, title = ?, updated_at = ? WHERE id = ?", (s.run_id, s.title, s.updated_at, s.id))


def session_of(conn: sqlite3.Connection, row: Any, agent: str) -> str | None:
    """The session an agent of the run of `row` already has (its function node's, or its builder's step node's), else None. Reads only: the live view
    (`RunWatcher`) asks this at every tick, and opening or rolling a session is the projector's job at the agent's first event."""
    run = getattr(row, "run_id", None)
    if not run or not agent:
        return None
    found = conn.execute(
        "SELECT g.chat_session_id AS sid FROM graph_nodes g JOIN chat_sessions s ON s.id = g.chat_session_id "
        "WHERE s.run_id = ? AND s.status = 'active' AND g.department_id = ? AND (g.id = ? OR g.step_ref = ?) ORDER BY s.created_at DESC LIMIT 1",
        (run, row.dept_id, f"{row.dept_id}.{agent}", agent)).fetchone()
    return found["sid"] if found is not None else None


# ---- the agents of a team, for the page (GET /api/teams/{dept}/agents) --------------------------------------------------------------------------

def _plus(a: int | float | None, b: int | float | None) -> int | float | None:
    """A sum in which a part nobody reported counts for nothing, and which is null when every part is (as the SQL `sum` is)."""
    return b if a is None else (a if b is None else a + b)


def _spent(conn: sqlite3.Connection, session_ids: list[str]) -> dict[str, dict[str, Any]]:
    """What each of the sessions was charged, stub rows left out: `{session_id: {calls, usd, tokens_in, tokens_out, by_purpose: {purpose: {calls, usd}}}}`. One
    pass over the ledger by session and purpose, so the purposes of a row always add up to its totals (a session with no call has no entry here)."""
    spent: dict[str, dict[str, Any]] = {}
    if not session_ids:
        return spent
    for u in conn.execute(
            "SELECT session_id, purpose, count(*) AS calls, sum(usd) AS usd, sum(tokens_in) AS tin, sum(tokens_out) AS tout FROM usage_ledger "
            f"WHERE provider != 'stub' AND session_id IN ({','.join('?' * len(session_ids))}) GROUP BY session_id, purpose ORDER BY session_id, purpose", session_ids):
        mine = spent.setdefault(u["session_id"], {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None, "by_purpose": {}})
        mine["calls"] += u["calls"]
        mine["usd"], mine["tokens_in"], mine["tokens_out"] = _plus(mine["usd"], u["usd"]), _plus(mine["tokens_in"], u["tin"]), _plus(mine["tokens_out"], u["tout"])
        mine["by_purpose"][u["purpose"]] = {"calls": u["calls"], "usd": round(float(u["usd"]), 6) if u["usd"] is not None else None}
    for mine in spent.values():
        if mine["usd"] is not None:
            mine["usd"] = round(float(mine["usd"]), 6)
    return spent


def team_agents(conn: sqlite3.Connection, store: Any, dept_id: str, run_id: str | None = None,
                default: Callable[[str], Pick] | Pick | None = None) -> list[dict[str, Any]]:
    """The agent chats of a team for one run: the five active function sessions (when the run is the live or latest one) and every session stamped with the
    run (its builders, and the function sessions a later run rolled). `run_id` None means the live run, else the latest. A run that is not the team's is
    NotFound. Each row: `{agent, label, kind, title, session_id, node_id, run_id, task_id, state, live, status, own, run_pick, effective, usage, last_at}`.
    Usage is the session's own (stub rows left out, as in every total): `{calls, usd, tokens_in, tokens_out, by_purpose}`, where `by_purpose` is
    `{purpose: {calls, usd}}` for each purpose the session was charged for (`agent_turn`, `plan`, `judge`, `agent_chat`, ...; none for an agent that has not
    called, D159), `usd` null when none of that purpose's calls has a price. Its calls add up to `calls`, and its dollars to `usd`."""
    from sutra_app.orchestrator.errors import NotFound
    from sutra_app.orchestrator.ids import iso_z
    from sutra_app.orchestrator.tasks import TaskStore
    if conn.execute("SELECT 1 FROM departments WHERE id = ?", (dept_id,)).fetchone() is None:
        raise NotFound("that team")
    ref = store.resolve_run(run_id, dept_id)
    if run_id and ref is None:
        raise NotFound("that run")
    default_ref = store.resolve_run(None, dept_id)
    run = ref.run_id if ref is not None else None
    include_active = run is None or (default_ref is not None and default_ref.run_id == run)
    task = conn.execute("SELECT id, status FROM tasks WHERE run_id = ?", (run,)).fetchone() if run else None
    live = task is not None and task["status"] in ("starting", "running", "waiting_user")
    where = ["s.kind IN ('function', 'step')", "g.department_id = ?", "COALESCE(g.step_ref, '') != 'task'"]
    args: list[Any] = [dept_id]
    sessions = ["s.run_id = ?"] if run else []
    if run:
        args.append(run)
    if include_active:
        sessions.append("(s.kind = 'function' AND s.status = 'active')")
    if not sessions:
        return []
    found = conn.execute(
        "SELECT s.id, s.node_id, s.kind, s.title, s.status, s.run_id, s.created_at, s.updated_at, g.kind AS gkind, g.step_ref, g.label, g.state "
        "FROM chat_sessions s JOIN graph_nodes g ON g.id = s.node_id "
        f"WHERE {' AND '.join(where)} AND ({' OR '.join(sessions)}) ORDER BY s.created_at, s.rowid", args).fetchall()
    ids = [r["id"] for r in found]
    spent = _spent(conn, ids)
    run_pick = pick_dict(TaskStore.pick_in(conn, task["id"])) if task is not None else None
    rows = []
    for r in found:
        function = r["kind"] == "function"
        agent = r["gkind"] if function else r["step_ref"]
        rows.append({
            "agent": agent, "label": agent.capitalize() if function else r["label"], "kind": r["kind"], "title": r["title"], "session_id": r["id"],
            "node_id": r["node_id"], "run_id": r["run_id"], "task_id": task["id"] if task is not None else None, "state": r["state"],
            "live": bool(live and r["status"] == "active" and r["state"] == "running"), "status": r["status"],
            "own": pick_dict(ChatChoices.pick_in(conn, r["id"])), "run_pick": run_pick, "effective": effective(conn, r["id"], default),
            "usage": spent.get(r["id"], {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None, "by_purpose": {}}), "last_at": iso_z(r["updated_at"]),
            "_order": (0 if function else 1, FUNCTIONS.index(agent) if function and agent in FUNCTIONS else 0, r["created_at"])})
    rows.sort(key=lambda x: x["_order"])
    for row in rows:
        del row["_order"]
    return rows


# ---- the owner's note to an agent (POST /api/chats/{sid}/steer, D132) ---------------------------------------------------------------------------

NOTE_CHARS = 2000                   # the most the owner can write in one note, and the most of an agent's notes the engine is given
NOTE_PREFIX = "Owner's note: "
CONTEXT_FILE = "node_context.json"


def compose_notes(old: str, note: str) -> str:
    """The text of `node_context.json[agent]` after one more note: the notes so far, one per line, newest last, each starting `Owner's note:`; the whole at most
    2,000 characters (the oldest notes go first; one note longer than that keeps its end). A note's own line breaks become spaces, so a line is a note."""
    line = NOTE_PREFIX + " ".join(note.split())
    lines = [kept for kept in (old or "").split("\n") if kept.startswith(NOTE_PREFIX)] + [line]
    while len(lines) > 1 and len("\n".join(lines)) > NOTE_CHARS:
        lines.pop(0)
    return "\n".join(lines)[-NOTE_CHARS:]
