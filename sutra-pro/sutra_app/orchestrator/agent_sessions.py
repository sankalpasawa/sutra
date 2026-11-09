"""The chat session of every agent (agent-sessions design 3.1, 3.3, D130, D131).

    agent_of(conn, sid) -> AgentRef | None         what an agent session is: its agent name, team, task, run (None for every other chat)
    effective(conn, sid, default) -> dict          the pick the session runs on and where it comes from: own > run > team > policy default

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
from sutra_app.orchestrator.chat_v2 import ChatChoices, cascade

__all__ = ["AgentRef", "agent_of", "effective", "pick_dict"]


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
