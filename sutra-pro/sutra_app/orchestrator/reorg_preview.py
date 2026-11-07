"""What a merge or a split will do, said before the owner answers (gap package chart-insight; docs/notes/GAP2-chart-insight.md).

    ReorgPreview(db).describe(change, before)    # ImpactOut {lines, notes}: a dry run of the change against `before`, as words

The approval card used to say only 'Merge Leads into Quotes? Their chats and history stay available.' The merge does more than that: the
merged-away division's chat stops accepting messages (ChatStore.apply_links archives it, read-only, filed under the survivor). This module
runs the library's own `apply_change` and `carry_links` on the pending change, reads the counts it needs, and writes the consequences as
plain sentences made by code (never by a model):

    lines   what the change does: which chat stays open and which becomes read-only history under the survivor (with message counts),
            how many step nodes and sub-divisions move, that a split keeps its chat and its new divisions start empty, that nothing is
            running in the divisions it touches
    notes   what to look at before saying yes: a division that is busy or a chart that moved on (a yes would be refused), a chart that
            becomes deeper than 4 levels, a pair that would look alike (name+purpose overlap of 40 percent or more)

Only what THIS change adds is listed (the old studio's rule: 'Only what the move ADDS'): a depth or a look-alike pair that is true on the
chart as it stands is never repeated, so an old untidiness does not bury the one line that matters. Nothing here writes: `describe` reads
through the connection of the calling thread, runs a pure function over copies, and the database is byte-identical before and after.
Cycle, duplicate-name and stale-base problems are the library's and `ChartStore`'s to report; here they become one sentence ('a yes would
be refused: ...') because the change can still be on the owner's screen when the chart has moved on.
"""
import sqlite3
from typing import Annotated

from pydantic import Field, StringConstraints

from sutra_app.library.base import Value
from sutra_app.library.org_chart import (
    MAX_DEPTH, AddOp, ChartChange, ChartChangeInvalid, ChartChangeResult, MergeOp, MoveOp, OrgChart, RenameOp, SplitOp, apply_change, carry_links,
    resolve_alias, slug_id,
)
from sutra_app.library.types import clip
from sutra_app.orchestrator.chart_health import OVERLAP_WARN, items_of, labels_of, overlap_pairs, percent
from sutra_app.orchestrator.chart_rules import ChartRules
from sutra_app.orchestrator.db import Database

__all__ = ["ReorgPreview", "ImpactOut", "ChangeImpactOut", "MAX_LINES", "LINE_CHARS", "DEPTH_WARN", "card_lines"]

MAX_LINES = 8                 # lines on an approval card
LINE_CHARS = 160
DEPTH_WARN = 5                # levels (edges below the root) at which a change that makes the chart this deep is worth a note; MAX_DEPTH is 6
_Line = Annotated[str, StringConstraints(min_length=1, max_length=LINE_CHARS)]


class ImpactOut(Value):
    lines: Annotated[list[_Line], Field(max_length=MAX_LINES)] = []
    notes: Annotated[list[_Line], Field(max_length=MAX_LINES)] = []


class ChangeImpactOut(ImpactOut):
    """The answer of GET /api/chart/changes/{id}/impact: the impact of that change and the status the change has now."""

    change_id: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    status: Annotated[str, StringConstraints(min_length=1, max_length=20)]


def card_lines(impact: ImpactOut) -> list[str]:
    """The lines an approval card carries: what to look at first (the notes), then what the change does, at most MAX_LINES."""
    return [*impact.notes, *impact.lines][:MAX_LINES]


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _names(names: list[str], *, limit: int = 3, rest: str = "divisions") -> str:
    if len(names) <= limit:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"{', '.join(names[:limit])} and {len(names) - limit} more {rest}"


class ReorgPreview:
    """Reads only. One instance per database; the connection is the calling thread's (as `ChartStore`'s reads are)."""

    def __init__(self, db: Database, rules: ChartRules | None = None) -> None:
        self.db = db
        self.rules = rules or ChartRules(db)

    def describe(self, change: ChartChange, before: OrgChart) -> ImpactOut:
        conn = self.db.conn()
        notes: list[str] = []
        busy = self.rules.busy(conn, before, change)
        notes.extend(f"{v.message}: a yes would be refused until it finishes" for v in busy)
        try:
            result = apply_change(before, change, new_id=_ids(conn))
        except ChartChangeInvalid as exc:
            stale = any(v.code == "stale_base" for v in exc.violations)
            first = exc.violations[0].message if exc.violations else "it no longer fits"
            notes.append("The chart changed since you were asked: a yes would be refused" if stale else f"A yes would be refused now: {first}")
            return _out([], notes)
        lines = _Lines(conn, before, result, change)
        out = lines.collect()
        involved = lines.involved_divisions()
        if involved and not busy:
            out.append(f"Nothing is running in {_names(involved)}.")
        notes.extend(_depth_note(before, result.chart))
        notes.extend(_alike_notes(before, result.chart))
        return _out(out, notes)


def _out(lines: list[str], notes: list[str]) -> ImpactOut:
    return ImpactOut(lines=[clip(x, LINE_CHARS) for x in lines[:MAX_LINES]], notes=[clip(x, LINE_CHARS) for x in notes[:MAX_LINES]])


def _ids(conn: sqlite3.Connection):
    """The id factory of the dry run: `slug_id` with every id ever stored taken, as `ChartStore` does, so the ids it gives are the real ones."""
    used = {r["id"] for r in conn.execute("SELECT id FROM org_nodes")} | {"root"}

    def make(kind: str, name: str, taken):
        return slug_id(kind, name, set(taken) | used)

    return make


# ---- what the chart looks like afterwards ---------------------------------------------------------------------------------------

def _depth(chart: OrgChart) -> int:
    parent = {e.child: e.parent for e in chart.edges}
    deepest = 0
    for node in chart.nodes:
        depth, current, seen = 0, node.id, set()
        while current in parent and current not in seen:
            seen.add(current)
            current = parent[current]
            depth += 1
        deepest = max(deepest, depth)
    return deepest


def _depth_note(before: OrgChart, after: OrgChart) -> list[str]:
    was, now = _depth(before), _depth(after)
    if now >= DEPTH_WARN and now > was:
        return [f"The chart would be {now} levels deep ({MAX_DEPTH} is the most)."]
    return []


def _alike_notes(before: OrgChart, after: OrgChart) -> list[str]:
    """Pairs that look alike on the chart after the change and did not on the chart before: only what this change adds."""
    items_before, parent_before = items_of(before)
    items_after, parent_after = items_of(after)
    known = {tuple(sorted((a.id, b.id))) for a, b, _ in overlap_pairs(items_before, parent_before, threshold=OVERLAP_WARN)}
    labels = labels_of(items_after, parent_after)
    out = []
    for a, b, score in overlap_pairs(items_after, parent_after, threshold=OVERLAP_WARN):
        if tuple(sorted((a.id, b.id))) in known:
            continue
        out.append(f"{labels[a.id]} and {labels[b.id]} would look alike ({percent(score)}% of their words).")
    return out


# ---- the consequences, op by op -------------------------------------------------------------------------------------------------

class _Lines:
    """The sentences of one dry run, read from the result and from the tables (chats, steps, earlier chats)."""

    def __init__(self, conn: sqlite3.Connection, before: OrgChart, result: ChartChangeResult, change: ChartChange) -> None:
        self.conn, self.before, self.result, self.change = conn, before, result, change
        self.names = {n.id: n.name for n in result.chart.nodes} | {n.id: n.name for n in before.nodes}      # the name the owner knows wins
        self.plan = self._plan()

    def name(self, node_id: str) -> str:
        return self.names.get(node_id, node_id)

    def real(self, target: str) -> str:
        return self.result.ids.get(target, target)

    def _plan(self):
        """The library's own rule for the chats (`carry_links`), over the sessions the nodes have now; a node the change adds will get a fresh one."""
        links: dict[str, str] = {}
        for node in self.before.nodes:
            row = self.conn.execute("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", (node.id,)).fetchone()
            if row is not None:
                links[node.id] = row["id"]
        for node_id in self.result.added:
            links[node_id] = f"new:{node_id}"
        try:
            return carry_links(links, self.result), links
        except ChartChangeInvalid:
            return None, links

    def messages(self, session_id: str) -> int:
        row = self.conn.execute("SELECT count(*) AS n FROM chat_messages WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["n"])

    def involved_divisions(self) -> list[str]:
        """The names of the divisions whose subtree the ops touch (a merge's sources, a split's node, a moved node): where 'nothing is running' is said."""
        found: list[str] = []
        for op in self.change.ops:
            if isinstance(op, MergeOp):
                targets = [self.real(s) for s in op.sources]
            elif isinstance(op, (SplitOp, MoveOp)):
                targets = [self.real(op.node)]
            else:
                continue
            for target in targets:
                node = self.before.node(target)
                if node is not None and node.kind == "division" and node.name not in found:
                    found.append(node.name)
        return found

    def collect(self) -> list[str]:
        out: list[str] = []
        for op in self.change.ops:
            if isinstance(op, MergeOp):
                out.extend(self.merge(op))
            elif isinstance(op, SplitOp):
                out.extend(self.split(op))
            elif isinstance(op, MoveOp):
                out.extend(self.move(op))
            elif isinstance(op, AddOp):
                out.append(f"Adds the {self.name(self.real(op.node.ref))} {op.node.kind}.")
            elif isinstance(op, RenameOp) and op.name is not None:
                out.append(f"Renames {self.name(self.real(op.node))} to {op.name}.")
        return out

    def merge(self, op: MergeOp) -> list[str]:
        plan, links = self.plan
        out: list[str] = []
        into = self.real(op.into)
        sources = [self.real(s) for s in op.sources]
        for source in sources:
            survivor = self.name(resolve_alias(self.result.aliases, source)) if source in self.result.aliases else self.name(into)
            session = links.get(source)
            if plan is not None and session is not None and not session.startswith("new:"):
                n = self.messages(session)
                if session in plan.archive:
                    out.append(f"The chat of {self.name(source)} ({_count(n, 'message')}) becomes read-only history under {survivor}.")
                elif session in plan.move:
                    out.append(f"The chat of {self.name(source)} ({_count(n, 'message')}) moves to {survivor} and stays open.")
            older = int(self.conn.execute("SELECT count(*) AS n FROM chat_sessions WHERE status = 'archived' AND filed_under = ?", (source,)).fetchone()["n"])
            if older:
                out.append(f"{_count(older, 'older chat')} of {self.name(source)} {'is' if older == 1 else 'are'} filed under {survivor} too.")
        final = resolve_alias(self.result.aliases, into) if into in self.result.aliases else into
        kept = links.get(final)
        if plan is not None and kept is not None and not kept.startswith("new:") and final in plan.keep:
            out.append(f"The chat of {self.name(final)} ({_count(self.messages(kept), 'message')}) stays open.")
        steps = self._steps(sources)
        if steps:
            out.append(f"{_count(steps, 'step node')} of {_names([self.name(s) for s in sources])} would move to {self.name(final)}.")
        children = [c for c in self.result.moved if self.before.parent_of(c) in sources]
        if children:
            out.append(f"{_names([self.name(c) for c in children], rest='divisions')} would move under {self.name(final)}.")
        return out

    def split(self, op: SplitOp) -> list[str]:
        plan, links = self.plan
        node = self.real(op.node)
        out: list[str] = []
        session = links.get(node)
        if plan is not None and session is not None and node in plan.keep:
            out.append(f"The chat of {self.name(node)} ({_count(self.messages(session), 'message')}) stays open.")
        parts = [self.real(p.ref) for p in op.parts]
        out.append(f"{_names([self.name(p) for p in parts], rest='divisions')} {'starts' if len(parts) == 1 else 'start'} with an empty chat.")
        for part in op.parts:
            moved = [self.real(m.child) for m in op.moves if self.real(m.to) == self.real(part.ref)]
            if moved:
                out.append(f"{_names([self.name(c) for c in moved], rest='divisions')} would move into {self.name(self.real(part.ref))}.")
        return out

    def move(self, op: MoveOp) -> list[str]:
        node, new = self.real(op.node), self.real(op.to_parent)
        old = self.before.parent_of(node)
        return [f"{self.name(node)} moves from {self.name(old) if old else 'the top'} to {self.name(new)}."]

    def _steps(self, sources: list[str]) -> int:
        marks = ",".join("?" * len(sources))
        row = self.conn.execute(f"SELECT count(*) AS n FROM graph_nodes WHERE kind = 'step' AND parent_id IN ({marks})", sources).fetchone()
        return int(row["n"])
