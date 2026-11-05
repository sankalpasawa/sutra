"""Chart rules that need the database or the owner's words (orchestrator 5.4; D68; S2-models-01, S4-fnodes-12).

The library's `apply_change` does the chart arithmetic and reports ALL its violations (C1 to C12). This module adds what the
library cannot know, as the same `Violation` objects:

    reuse_candidate   an added department or division that looks like a live node of the same kind (name+purpose Jaccard >= 0.5,
                      or the same normalised name): the model must reuse it instead (reuse first, ORCH-D3)
    busy              a move, merge or split of a division whose subtree has an unfinished task scoped to it
    bad_assignment    stage C: a department that is not live (or added by the change), a scope that is not a division under it,
                      a `follows` that is not a task of that department
    classify          'approve' iff a rearrange holds a MergeOp or a SplitOp (the one step that is hard to take back), else 'auto'
    digest            the chart as the model reads it: one line per department, one per division, bounded in size

`ChartRules` holds only the database handle; every rule reads through the connection it is given, so the same code runs on a
plain read (`ChartStore.check`) and inside the apply transaction. Nothing here writes.
"""
import sqlite3
from collections.abc import Collection, Iterable, Sequence
from typing import Any, Literal

from sutra_app.library.org_chart import AddOp, ChartChange, MergeOp, MoveOp, OrgChart, OrgNode, SplitOp
from sutra_app.library.types import Violation, violation
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.models import LIVE_STATUSES
from sutra_app.orchestrator.textutil import jaccard, name_key, tokens

__all__ = [
    "ChartRules", "JACCARD_REUSE", "OPEN_STATUSES", "DIGEST_DEPARTMENT_LIMIT", "DIGEST_KEEP", "classify", "reuse_violations",
    "TERMINAL_NOTE",
]

JACCARD_REUSE = 0.5                          # name+purpose token overlap at which a new node is "the same as" a live one
OPEN_STATUSES = ("blocked", "queued", "starting", "running", "waiting_user")     # an unfinished task still needs its division
DIGEST_DEPARTMENT_LIMIT = 40                 # over this many departments the digest keeps only the best matches and the busy ones
DIGEST_KEEP = 25
DIGEST_PURPOSE_DEPARTMENT = 120
DIGEST_PURPOSE_DIVISION = 80
TERMINAL_NOTE = "(+{n} more not shown)"


def classify(change: ChartChange) -> Literal["auto", "approve"]:
    """'approve' iff the change is a rearrange that holds a MergeOp or a SplitOp; reuse, add, move and rename are automatic."""
    ops = change.ops
    return "approve" if change.kind == "rearrange" and any(isinstance(op, (MergeOp, SplitOp)) for op in ops) else "auto"


def _node_tokens(node: OrgNode) -> frozenset[str]:
    return tokens(f"{node.name} {node.purpose}")


def reuse_violations(chart: OrgChart, ops: Sequence[Any]) -> list[Violation]:
    """`reuse_candidate` for every AddOp whose new node resembles a live node of the same kind (path `ops.<i>.node.name`)."""
    out: list[Violation] = []
    for i, op in enumerate(ops):
        if not isinstance(op, AddOp):
            continue
        new = op.node
        new_tokens = tokens(f"{new.name} {new.purpose}")
        new_key = name_key(new.name)
        for live in chart.nodes:
            if live.kind != new.kind:
                continue
            same_name = bool(new_key) and new_key == name_key(live.name)
            if same_name or jaccard(new_tokens, _node_tokens(live)) >= JACCARD_REUSE:
                out.append(violation(
                    f"ops.{i}.node.name", "reuse_candidate",
                    f"{new.name!r} looks like the existing {live.kind} {live.name!r} ({live.id}): reuse it instead of adding another"))
                break
    return out


class ChartRules:
    """The rules that read the database. One instance per database; all methods are reads."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- what the tasks say -----------------------------------------------------------------------------------------

    @staticmethod
    def unfinished_scopes(conn: sqlite3.Connection) -> dict[str, str]:
        """Division id -> the title of the oldest unfinished task scoped to it (blocked, queued, starting, running, waiting)."""
        marks = ",".join("?" * len(OPEN_STATUSES))
        rows = conn.execute(
            f"SELECT scope_node_id, title FROM tasks WHERE scope_node_id IS NOT NULL AND status IN ({marks}) ORDER BY created_at, rowid",
            OPEN_STATUSES).fetchall()
        found: dict[str, str] = {}
        for row in rows:
            found.setdefault(row["scope_node_id"], row["title"])
        return found

    # ---- change rules ---------------------------------------------------------------------------------------------------

    def extras(self, conn: sqlite3.Connection, chart: OrgChart, change: ChartChange) -> list[Violation]:
        """The violations this module adds to the library's: `reuse_candidate`, then `busy`, each in op order."""
        return reuse_violations(chart, change.ops) + self.busy(conn, chart, change)

    def busy(self, conn: sqlite3.Connection, chart: OrgChart, change: ChartChange) -> list[Violation]:
        """A move, merge (each source) or split of a division whose subtree holds an unfinished task scope. Refs and ids that are
        not in the chart are skipped (the library reports them)."""
        scopes = self.unfinished_scopes(conn)
        if not scopes:
            return []
        out: list[Violation] = []

        def check(node_id: str, path: str) -> None:
            node = chart.node(node_id)
            if node is None or node.kind != "division":
                return
            for inside in chart.subtree(node_id):
                if inside in scopes:
                    where = node.name if inside == node_id else f"{node.name} ({chart.node(inside).name})"
                    out.append(violation(path, "busy", f"{where} is busy with {scopes[inside]}"))
                    return

        for i, op in enumerate(change.ops):
            if isinstance(op, MoveOp):
                check(op.node, f"ops.{i}.node")
            elif isinstance(op, SplitOp):
                check(op.node, f"ops.{i}.node")
            elif isinstance(op, MergeOp):
                for j, source in enumerate(op.sources):
                    check(source, f"ops.{i}.sources.{j}")
        return out

    # ---- stage C --------------------------------------------------------------------------------------------------------

    def assignments(self, conn: sqlite3.Connection, drafts: Iterable[Any], chart: OrgChart, *,
                    added: Collection[str] = ()) -> list[Violation]:
        """`bad_assignment` for each draft (anything with `dept`, `scope` and `follows`): the department must be a department of
        `chart` (the chart as it will be after stage B) or one of the ids in `added`; a scope must be a division under that
        department; `follows` must be a task of that department. Paths `assignments.<i>.dept`, `.scope`, `.follows`."""
        out: list[Violation] = []
        for i, draft in enumerate(drafts):
            dept, scope, follows = _attr(draft, "dept"), _attr(draft, "scope"), _attr(draft, "follows")
            node = chart.node(dept) if isinstance(dept, str) else None
            live = node is not None and node.kind == "department"
            if not live and dept not in added:
                out.append(violation(f"assignments.{i}.dept", "bad_assignment", f"{dept!r} is not a live team and this change does not add it"))
                continue
            if scope is not None:
                inner = chart.node(scope)
                if inner is None or inner.kind != "division" or chart.department_of(scope) != dept:
                    out.append(violation(f"assignments.{i}.scope", "bad_assignment", f"{scope!r} is not a division under {dept!r}"))
            if follows is not None:
                row = conn.execute("SELECT dept_id FROM tasks WHERE id = ?", (follows,)).fetchone()
                if row is None or row["dept_id"] != dept:
                    out.append(violation(f"assignments.{i}.follows", "bad_assignment", f"{follows!r} is not a task of {dept!r}"))
        return out

    # ---- the digest ----------------------------------------------------------------------------------------------------

    def digest(self, conn: sqlite3.Connection, chart: OrgChart, text: str, *, max_chars: int = 6000) -> str:
        """The chart as the model reads it. A header, then per department `id | name | purpose | live: <title or -> | last: <title
        (status) task id or ->` and, indented, one `id | name | purpose` line per division below it. Over 40 departments only the
        25 whose words overlap `text` most are kept, plus every busy one. The result is at most `max_chars` characters and says
        how much it left out."""
        if max_chars < 80:
            raise ValueError("a digest needs at least 80 characters")
        live = _latest_by_dept(conn, LIVE_STATUSES)
        last = _latest_by_dept(conn, None)
        departments = [n for n in chart.nodes if n.kind == "department"]
        blocks: dict[str, list[str]] = {}
        for dept in departments:
            below = [d for d in chart.subtree(dept.id) if d != dept.id]
            title_live = live.get(dept.id)
            title_last = last.get(dept.id)
            head = " | ".join([
                dept.id, dept.name, dept.purpose[:DIGEST_PURPOSE_DEPARTMENT],
                f"live: {title_live['title'] if title_live else '-'}",
                f"last: {_last_text(title_last)}"])
            lines = [head]
            for node_id in below:
                node = chart.node(node_id)
                depth = _depth(chart, node_id, dept.id)
                lines.append(f"{'  ' * depth}{node.id} | {node.name} | {node.purpose[:DIGEST_PURPOSE_DIVISION]}")
            blocks[dept.id] = lines
        chosen = [d.id for d in departments]
        omitted_teams = 0
        if len(departments) > DIGEST_DEPARTMENT_LIMIT:
            wanted = tokens(text)

            def overlap(dept: OrgNode) -> int:
                words = set(tokens(f"{dept.name} {dept.purpose}"))
                for node_id in chart.subtree(dept.id):
                    inner = chart.node(node_id)
                    words |= tokens(f"{inner.name} {inner.purpose}")
                return len(wanted & words)

            ranked = sorted(departments, key=lambda d: (-overlap(d), chart.nodes.index(d)))
            keep = {d.id for d in ranked[:DIGEST_KEEP]} | {d.id for d in departments if d.id in live}
            chosen = [d.id for d in departments if d.id in keep]
            omitted_teams = len(departments) - len(chosen)
        header = f"Org chart revision {chart.revision}. Root id: {_root_id(chart)}."
        lines = [header]
        for dept_id in chosen:
            lines.extend(blocks[dept_id])
        tail_teams = f"(+{omitted_teams} more teams not shown)" if omitted_teams else ""
        return _fit(lines, tail_teams, max_chars)


def _attr(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _root_id(chart: OrgChart) -> str:
    return next((n.id for n in chart.nodes if n.kind == "root"), "root")


def _depth(chart: OrgChart, node_id: str, dept_id: str) -> int:
    depth, current = 0, node_id
    while current != dept_id and current is not None:
        current = chart.parent_of(current)
        depth += 1
    return depth


def _latest_by_dept(conn: sqlite3.Connection, statuses: Sequence[str] | None) -> dict[str, sqlite3.Row]:
    """The newest task of each department (restricted to `statuses` when given)."""
    where, args = "", ()
    if statuses is not None:
        where = f"WHERE status IN ({','.join('?' * len(statuses))})"
        args = tuple(statuses)
    rows = conn.execute(f"SELECT id, dept_id, title, status FROM tasks {where} ORDER BY created_at, rowid", args).fetchall()
    return {row["dept_id"]: row for row in rows}           # later rows replace earlier ones: the newest wins


def _last_text(row: sqlite3.Row | None) -> str:
    return "-" if row is None else f"{row['title']} ({row['status']}) {row['id']}"


def _fit(lines: list[str], tail_teams: str, max_chars: int) -> str:
    """Join `lines` (then `tail_teams`) within `max_chars`. When they do not fit, the lines that do not are replaced by one
    `(+N more not shown)` line, so the reader knows the list is cut."""
    tail = [tail_teams] if tail_teams else []
    whole = "\n".join(lines + tail)
    if len(whole) <= max_chars:
        return whole
    reserve = len(TERMINAL_NOTE.format(n=len(lines))) + 1 + (len(tail_teams) + 1 if tail_teams else 0)
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 + reserve > max_chars:
            break
        kept.append(line)
        used += len(line) + 1
    kept.append(TERMINAL_NOTE.format(n=len(lines) - len(kept)))
    result = "\n".join(kept + tail)
    return result[:max_chars]
