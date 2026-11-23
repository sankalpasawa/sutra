"""What one model call of a step may still spend, read NOW (D409, R-2): pure sqlite functions, so the server (the start gate, the tick) and the step's own process (before each builder call, read-only) use the
same arithmetic.

    cap = min(what is left of the owner's month, what is left of the project's own dollars / the steps of the project that RUN at this moment, this one included)

It is read on every call and never frozen at the step's start: a step that started alone is lowered when a sibling starts, a step held for an answer takes no share until it runs, and a share is given back when
a sibling ends. It is a bound on ONE call, not a promise: steps that run at the same time can still pass the limit by up to one call's worth each before the Conductor's tick sees the ledger, and Codex calls
carry no dollar figure, so nothing here can stop a project that runs on Codex.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from sutra_app.orchestrator.budgets import project_cost
from sutra_app.orchestrator.limits import month_start, spend_status

__all__ = ["frozen_limit", "month_left", "running_steps", "call_cap"]

RUNNING = ("leased", "running", "handing_off")


def frozen_limit(project: Any, monthly_limit: float | None, now: float) -> float | None:
    """The dollars a project was given at its start, while that still means something (D388): the owner's own number always; the month's leftover only while the owner still has a monthly limit and the
    month it was taken from is still the month. None when there is none. `project` has `budget_usd`, `caps_json` and `created_at`."""
    if project is None or project["budget_usd"] is None:
        return None
    if json.loads(project["caps_json"] or "{}").get("usd_from_month"):
        if not monthly_limit or month_start(float(project["created_at"])) != month_start(now):
            return None
    return float(project["budget_usd"])


def month_left(conn: sqlite3.Connection, monthly_limit: float | None, now: float) -> float | None:
    """The limit minus this month's known spending (every call of every task); None when the owner set no limit; never below 0."""
    if not monthly_limit:
        return None
    return max(0.0, round(float(monthly_limit) - float(spend_status(conn, monthly_limit, now)["spent"]), 6))


def running_steps(conn: sqlite3.Connection, project_id: str) -> int:
    """The steps of this project that run at this moment (a step held for an answer, or waiting for a slot, does not count); at least 1: the step that asks is one of them."""
    marks = ",".join("?" * len(RUNNING))
    return max(1, int(conn.execute(f"SELECT count(*) FROM agent_nodes WHERE project_id = ? AND role <> 'planner' AND state IN ({marks})", (project_id, *RUNNING)).fetchone()[0]))


def call_cap(conn: sqlite3.Connection, project_id: str, monthly_limit: float | None, now: float) -> float | None:
    """What the next model call of a step of this project may spend, or None when nothing limits it. Never below 0."""
    conn.row_factory = sqlite3.Row
    project = conn.execute("SELECT budget_usd, caps_json, created_at FROM projects WHERE id = ?", (project_id,)).fetchone()
    month = month_left(conn, monthly_limit, now)
    own = frozen_limit(project, monthly_limit, now)
    shares = None
    if own is not None:
        shares = max(0.0, own - project_cost(conn, project_id, int(project["created_at"]))[0]) / running_steps(conn, project_id)
    found = [v for v in (month, shares) if v is not None]
    return max(0.0, min(found)) if found else None
