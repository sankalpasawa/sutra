"""Slices and ceilings of a project (multi-agent nodes, MAN-9; D271, D272, D294, D300): pure functions, no database.

    slices = make_slices([120, 80, 0], ceiling=300)        # a share of the project's credits for each step; the sum is never over the ceiling
    left   = slice_left(120, *chain_spend(conn, task_id))   # what a retry or a restart starts with

A slice is the work credits one node's run starts with (`J2_BUDGET`) and may not go past (`J2_BUDGET_CAP`): the node cannot raise it itself (P25, D251: a raise is the Requester's own). The project's
ceiling is the sum of the slices (`projects.budget_credits`). A slice is final (D320): nothing moves credits between nodes and nothing, Decide for me included, raises the ceiling (D294); a retry or a
restart starts with its slice minus what the earlier attempts of the node spent (D324). `egress_scrubs` counts, per node, the audit rows of `egress.jsonl` in which something was scrubbed (D303: the same node three times ends it).
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

__all__ = ["DEFAULT_SLICE", "SCRUB_LIMIT", "make_slices", "slice_left", "chain_spend", "project_spend", "project_cost", "egress_scrubs"]

DEFAULT_SLICE = 100                      # the work credits a step's run starts with when nobody said otherwise (J2_BUDGET's default; D300)
SCRUB_LIMIT = 3                          # the same node's prompts scrubbed this many times end the node (D303)
_TAIL_BYTES = 2 * 1024 * 1024            # how much of the end of egress.jsonl is read


def make_slices(wants: Sequence[int], ceiling: int | None = None) -> list[int]:
    """One slice per step: what the step wants (at least 1; anything that is not a whole number counts as the default), and, when `ceiling` is given and the wants add up to more, every slice cut
    in proportion (never below 1 while the ceiling allows one for each) so that the sum is never over the ceiling."""
    asked = [max(1, w) if isinstance(w, int) and not isinstance(w, bool) else DEFAULT_SLICE for w in wants]
    if ceiling is None or sum(asked) <= ceiling:
        return asked
    ceiling = max(0, int(ceiling))
    if ceiling < len(asked):                                   # not even one credit each: the first steps get one, the rest none
        return [1 if index < ceiling else 0 for index in range(len(asked))]
    total = sum(asked)
    cut = [max(1, w * ceiling // total) for w in asked]
    while sum(cut) > ceiling:                                  # the minimum of one can overshoot: take from the largest
        cut[cut.index(max(cut))] -= 1
    return cut


_CHAIN = ("WITH RECURSIVE chain(id) AS (SELECT ? UNION SELECT t.parent_task_id FROM tasks t JOIN chain c ON t.id = c.id WHERE t.parent_task_id IS NOT NULL) ")


def chain_spend(conn: sqlite3.Connection, task_id: str | None) -> tuple[int, float]:
    """(model calls, dollars) the task and every earlier attempt of the same node (its `parent_task_id` chain) spent, from the usage ledger (stub calls cost nothing and are not counted). One credit is
    counted for each call until J2 reports its own credits to the server (D324): a retry or a restart starts with its slice minus this, never with a full fresh slice."""
    if not task_id:
        return 0, 0.0
    row = conn.execute(_CHAIN + "SELECT count(*), COALESCE(SUM(usd), 0) FROM usage_ledger WHERE task_id IN (SELECT id FROM chain) AND provider != 'stub'", (task_id,)).fetchone()
    return int(row[0]), float(row[1])


def project_spend(conn: sqlite3.Connection, project_id: str) -> tuple[int, float]:
    """(model calls, dollars) the whole project spent: every node's task AND the earlier attempts of each node (a retried node's first attempt cost money too, D324)."""
    row = conn.execute("WITH RECURSIVE chain(id) AS (SELECT task_id FROM agent_nodes WHERE project_id = ? AND task_id IS NOT NULL UNION SELECT t.parent_task_id FROM tasks t JOIN chain c ON t.id = c.id "
                       "WHERE t.parent_task_id IS NOT NULL) SELECT count(*), COALESCE(SUM(usd), 0) FROM usage_ledger WHERE task_id IN (SELECT id FROM chain) AND provider != 'stub'", (project_id,)).fetchone()
    return int(row[0]), float(row[1])


def project_cost(conn: sqlite3.Connection, project_id: str, after: int | None = None) -> tuple[float, int]:
    """(dollars, calls with no dollar figure) of the whole project as the usage ledger holds them (D383): every step's task and its earlier attempts, the reviewer, AND the calls the project's planner made
    (a row of the org chat whose detail names one of the project's nodes). A call with no dollar figure (Codex, a call that failed before it reported one) is counted apart, so the page can say "about". Stub calls
    cost nothing and are not counted. `after`: only the rows from that moment on (the project's creation), which is what the project's dollar limit is compared with: the planner's calls were made before the project
    existed, so they are already out of the month's allowance the limit was taken from (D388); the page shows them all."""
    row = conn.execute(
        "WITH RECURSIVE chain(id) AS (SELECT task_id FROM agent_nodes WHERE project_id = ?1 AND task_id IS NOT NULL UNION SELECT t.parent_task_id FROM tasks t JOIN chain c ON t.id = c.id WHERE t.parent_task_id IS NOT NULL) "
        "SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(usd IS NULL), 0) FROM usage_ledger WHERE provider != 'stub' AND (task_id IN (SELECT id FROM chain) OR "
        "(task_id IS NULL AND CASE WHEN json_valid(detail_json) THEN json_extract(detail_json, '$.agent_node') END IN (SELECT id FROM agent_nodes WHERE project_id = ?1))) AND (?2 IS NULL OR at >= ?2)", (project_id, after)).fetchone()
    return float(row[0]), int(row[1])


def slice_left(slice_credits: int, spent_calls: int) -> int:
    """What a new attempt of a node starts with: its slice minus what the earlier attempts spent (one credit for each call, D324); 0 when nothing is left (the node is then not tried again)."""
    return max(0, int(slice_credits) - max(0, int(spent_calls)))


def egress_scrubs(path: str | Path, node_ids: Sequence[str] | None = None) -> dict[str, int]:
    """Per node id, how many rows of the egress audit file say something was scrubbed (`shapes` is not empty). Only the end of the file is read; a line that is not a row is skipped; a node that has
    none is absent. `node_ids` limits the answer to those nodes."""
    wanted = set(node_ids) if node_ids is not None else None
    counts: dict[str, int] = {}
    try:
        size = Path(path).stat().st_size
        with open(path, "rb") as handle:
            handle.seek(max(0, size - _TAIL_BYTES))
            tail = handle.read().decode("utf-8", "replace")
    except OSError:
        return counts
    for line in tail.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        node = row.get("node") if isinstance(row, dict) else None
        if isinstance(node, str) and row.get("shapes") and (wanted is None or node in wanted):
            counts[node] = counts.get(node, 0) + 1
    return counts
