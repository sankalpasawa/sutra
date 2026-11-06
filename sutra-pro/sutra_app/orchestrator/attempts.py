"""The attempts of one request (GAP-model-quality): a retry is told how the earlier attempts ended, so a goal outlives its attempts.

    attempt_of(row)                         # 1 for a first try; n for the n-th try (the reserved settings key `_attempt`)
    attempt_in(conn, task_id)               # the same, read by id
    chain(conn, task_id)                    # [first attempt, ..., this task]: parents with the same words, each a retry of the one before
    brief(conn, earlier, number, run_dir=..., scrub=...)    # the fixed-template paragraph attempt `number` gets in its framing

`TaskService.retry` appends the brief to the FIRST attempt's own framing (so briefs never pile up) and stores the new number under
`_attempt` in `settings_json`, beside `_seed_from`; every reader of the settings drops underscore keys. The engine host posts the framing
as "Context from the team lead: ..." before the owner's words (engine/host/loop.py), so no J2 file changes.

Facts only, each read from a record that code wrote: the task row (status and outcome), the run folder's `summary.json` (`done_when[].pass`,
`limits_hit`, `to_be_confirmed`; J2's `_write_summary`, code only), the task's atoms (closed or not) and, for a crash, the tail of
`run.stderr.log`. No chat line is read and nothing is guessed. A retry starts fresh (no seed, no files of the old run), so the brief says what
the earlier attempts showed and that none of it counts as done in the new run; it never marks a check met. A missing or unreadable file is
skipped; every text goes through `scrub` (the app's redactor and the egress credential shapes).
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path

from sutra_app.library.types import clip
from sutra_app.orchestrator.runs import stderr_tail

__all__ = ["ATTEMPT_KEY", "BRIEF_CHARS", "attempt_of", "attempt_in", "chain", "brief"]

ATTEMPT_KEY = "_attempt"
BRIEF_CHARS = 4000
MAX_CHAIN = 20
ITEMS_SHOWN = 10
ITEM_CHARS = 160
OUTCOME_CHARS = 300
STDERR_CHARS = 400
SUMMARY_MAX_BYTES = 2_000_000
_COLUMNS = "id, dept_id, user_text, framing, status, outcome, run_id, parent_task_id, settings_json"
ENDED = {"crashed": "crashed", "stopped": "was stopped", "cancelled": "was cancelled", "done_with_open_items": "finished with open items",
         "done": "finished"}


def attempt_of(row: sqlite3.Row | dict) -> int:
    """The attempt number a task row carries: `_attempt` in its settings (2, 3, ...), else 1."""
    try:
        found = json.loads(row["settings_json"] or "{}").get(ATTEMPT_KEY)
    except (ValueError, AttributeError):
        return 1
    return found if isinstance(found, int) and not isinstance(found, bool) and found >= 1 else 1


def attempt_in(conn: sqlite3.Connection, task_id: str) -> int:
    found = conn.execute("SELECT settings_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return attempt_of(found) if found is not None else 1


def chain(conn: sqlite3.Connection, task_id: str) -> list[sqlite3.Row]:
    """The attempts up to and including `task_id`, oldest first. A row's parent belongs to the chain while the row is a retry (`_attempt`
    at least 2) of the same department and the same words; a follow-up (other words, no `_attempt`) ends it. At most MAX_CHAIN rows."""
    rows: list[sqlite3.Row] = []
    current = conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE id = ?", (task_id,)).fetchone()
    while current is not None and len(rows) < MAX_CHAIN:
        rows.insert(0, current)
        if attempt_of(current) < 2 or current["parent_task_id"] is None:
            break
        parent = conn.execute(f"SELECT {_COLUMNS} FROM tasks WHERE id = ?", (current["parent_task_id"],)).fetchone()
        if parent is None or parent["dept_id"] != current["dept_id"] or parent["user_text"] != current["user_text"]:
            break
        current = parent
    return rows


def _summary(run_dir: Path | None) -> dict:
    """summary.json of a run folder, or {} when there is none (a crash may leave none), it is too large or it is not a JSON object."""
    if run_dir is None:
        return {}
    path = run_dir / "summary.json"
    try:
        if path.stat().st_size > SUMMARY_MAX_BYTES:
            return {}
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _texts(items: object) -> list[str]:
    """The text of each item of a summary list: a string, or the `text` of an object; anything else is skipped."""
    out = []
    for item in items if isinstance(items, list) else []:
        value = item if isinstance(item, str) else (item.get("text") if isinstance(item, dict) else None)
        if isinstance(value, str) and value.strip():
            out.append(value)
    return out


def _listed(label: str, items: Sequence[str], scrub: Callable[[str], str]) -> list[str]:
    if not items:
        return []
    shown = [clip(" ".join(scrub(i).split()), ITEM_CHARS) for i in items[:ITEMS_SHOWN]]
    more = f" (and {len(items) - ITEMS_SHOWN} more)" if len(items) > ITEMS_SHOWN else ""
    return [f"  {label}: " + "; ".join(shown) + more + "."]


def _block(conn: sqlite3.Connection, row: sqlite3.Row, run_dir: Callable[[str, str], Path | None], scrub: Callable[[str], str]) -> tuple[str, list[str]]:
    """(the attempt's one line, its detail lines)."""
    outcome = clip(" ".join(scrub(row["outcome"] or "").split()), OUTCOME_CHARS)
    head = f"Attempt {attempt_of(row)} {ENDED.get(row['status'], row['status'].replace('_', ' '))}" + (f": {outcome}" if outcome else ".")
    folder = run_dir(row["dept_id"], row["run_id"]) if row["run_id"] else None
    summary = _summary(folder)
    checks = [d for d in summary.get("done_when", []) if isinstance(d, dict) and isinstance(d.get("criterion"), str)]
    details = _listed("Done-when items its audit found met", [d["criterion"] for d in checks if d.get("pass") is True], scrub)
    details += _listed("Done-when items not met or not checked", [d["criterion"] for d in checks if d.get("pass") is not True], scrub)
    details += _listed("Limits it hit", _texts(summary.get("limits_hit")), scrub)
    details += _listed("Left to confirm with the owner", _texts(summary.get("to_be_confirmed")), scrub)
    atoms = conn.execute("SELECT goal, display FROM atoms WHERE task_id = ? ORDER BY ts_open, id", (row["id"],)).fetchall()
    details += _listed("Work it closed and checked", [a["goal"] for a in atoms if a["display"] == "closed"], scrub)
    details += _listed("Work it did not finish", [f"{a['goal']} ({a['display'].replace('_', ' ')})" for a in atoms if a["display"] != "closed"], scrub)
    if row["status"] == "crashed" and folder is not None:
        tail = " ".join(scrub(stderr_tail(folder)).split())
        if tail:
            details.append(f"  The end of its error log: {'…' + tail[-STDERR_CHARS:] if len(tail) > STDERR_CHARS else tail}")
    return head, details


def brief(conn: sqlite3.Connection, earlier: Sequence[sqlite3.Row], number: int, *, run_dir: Callable[[str, str], Path | None],
          scrub: Callable[[str], str] = lambda text: text) -> str:
    """The paragraph attempt `number` is given about `earlier` (oldest first); "" when there is none. At most BRIEF_CHARS: the newest
    attempt is filled first, line by whole line, then the one before it; what does not fit is left out, and dropped attempts are named."""
    if not earlier:
        return ""
    head = (f"This is attempt {number} of this request. It starts fresh: nothing an earlier attempt made is in this run, so make and check "
            "everything again here.")
    foot = "Use this to avoid what stopped the earlier attempts. None of it counts as done or checked in this run."
    reserve = 60                                                      # room for the note that names the attempts left out
    budget = BRIEF_CHARS - len(head) - len(foot) - 2 - reserve
    kept: list[str] = []
    for line, details in reversed([_block(conn, row, run_dir, scrub) for row in earlier]):
        if budget < 80:
            break
        chosen = [clip(line, budget - 1)]
        budget -= len(chosen[0]) + 1
        for detail in details:
            if len(detail) + 1 > budget:
                break
            chosen.append(detail)
            budget -= len(detail) + 1
        kept.insert(0, "\n".join(chosen))
    if len(kept) < len(earlier):
        kept.insert(0, f"(the {len(earlier) - len(kept)} oldest attempts are left out)")
    return "\n".join([head, *kept, foot])[:BRIEF_CHARS]
