"""Chart notes: what has drifted in the org chart, said in names and never in codes (gap package chart-insight; docs/notes/GAP2-chart-insight.md).

    ChartHealth(db).notes(now)      # ChartNotesOut: up to 20 ChartNote, worst first, and how many there were in all
    overlap_pairs(items, parent)    # (a, b, score) for every live pair of one kind that shares at least OVERLAP_WARN of its words

Three kinds of note, all read at request time from the live chart (`org_nodes`, `org_edges`) and the tasks and chats; nothing is stored, and
nothing is scheduled:

    overlap     two teams, or two divisions, whose name and purpose share 40 percent of their words (Jaccard over `textutil.tokens`).
                A node and its ancestor or descendant are exempt: a division looks like the team it belongs to by construction. The
                threshold is its own name, not `JACCARD_REUSE` (0.5, which refuses a NEW node): this one only tells.
    no_purpose  a team or division whose purpose is empty, or says nothing its name does not (every word of it is in the name)
    quiet       a team with no task and no chat message for 60 days and nothing unfinished; its age counts from the newest of those, or
                from when the team was made. Only teams are listed: a division has no tasks of its own to measure.

Every age is measured from the ONE `now` the caller passes (the old app's lesson: two halves of one screen disagreed until the HTTP layer
handed both a single clock). A note is information only. Only divisions can be merged (D68) and a team is never archived, moved or merged
(DL5), so a note about two teams has no sentence to say; a note about two divisions offers 'merge X into Y' as words the owner can say to
the chat agent, and a team with no purpose offers 'change the purpose of X to ...'. Nothing here changes the chart.
"""
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from sutra_app.library.base import Value
from sutra_app.library.types import clip
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.models import NodeId
from sutra_app.orchestrator.textutil import jaccard, tokens
from sutra_app.orchestrator.waiting import age_words

__all__ = [
    "ChartHealth", "ChartNote", "ChartNotesOut", "NoteNode", "Item", "OVERLAP_WARN", "QUIET_DAYS", "MAX_NOTES", "overlap_pairs",
    "items_of", "related", "labels_of", "percent", "thin_purpose",
]

OVERLAP_WARN = 0.40            # name+purpose overlap at which two live nodes of one kind "look alike" (the old tuned value)
QUIET_DAYS = 60                # a team with nothing for this long is "quiet"
MAX_NOTES = 20                 # notes sent at most (the pane shows them all; the rest is counted)
_OPEN = ("blocked", "queued", "starting", "running", "waiting_user")
_LABEL = 160


@dataclass(frozen=True)
class Item:
    """What the notes need to know of one node: the chart's own nodes and the projection's rows both become these."""

    id: str
    kind: str
    name: str
    purpose: str


class NoteNode(Value):
    """A node a note names: `label` is the text of its name inside `words` (an address when two nodes share a name), so a page can turn
    that very text into a button that opens the node's card."""

    id: NodeId
    label: Annotated[str, StringConstraints(min_length=1, max_length=_LABEL)]


class ChartNote(Value):
    kind: Literal["overlap", "no_purpose", "quiet"]
    nodes: Annotated[list[NoteNode], Field(min_length=1, max_length=2)]
    words: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    say: Annotated[str, StringConstraints(max_length=300)] = ""        # a sentence the owner can say to the chat agent, or "" (information only)


class ChartNotesOut(Value):
    notes: Annotated[list[ChartNote], Field(max_length=MAX_NOTES)]
    total: Annotated[int, Field(ge=0)]                                  # notes found; `notes` holds the first MAX_NOTES of them


# ---- the pure part ------------------------------------------------------------------------------------------------------------

def items_of(chart) -> tuple[list[Item], dict[str, str | None]]:
    """(the department and division nodes of an OrgChart in chart order, id -> parent id for every node)."""
    parent = {edge.child: edge.parent for edge in chart.edges}
    items = [Item(n.id, n.kind, n.name, n.purpose) for n in chart.nodes if n.kind in ("department", "division")]
    return items, {n.id: parent.get(n.id) for n in chart.nodes}


def related(parent: Mapping[str, str | None], a: str, b: str) -> bool:
    """True when `a` lies above `b` or `b` above `a` in the tree (an ancestor and its descendant)."""
    def above(low: str, high: str) -> bool:
        seen: set[str] = set()
        node = parent.get(low)
        while node is not None and node not in seen:
            if node == high:
                return True
            seen.add(node)
            node = parent.get(node)
        return False

    return above(a, b) or above(b, a)


def overlap_pairs(items: Sequence[Item], parent: Mapping[str, str | None], *, threshold: float = OVERLAP_WARN) -> list[tuple[Item, Item, float]]:
    """Every pair of live nodes of one kind (department with department, division with division) whose name+purpose share at least
    `threshold` of their words, ancestors and descendants exempt. Worst first; ties keep the chart order. Only nodes that share a word
    are compared at all, so a chart of 500 nodes costs what its common words cost."""
    live = [i for i in items if i.kind in ("department", "division")]
    words = {i.id: tokens(f"{i.name} {i.purpose}") for i in live}
    order = {i.id: n for n, i in enumerate(live)}
    by_word: dict[str, list[Item]] = {}
    for item in live:
        for word in words[item.id]:
            by_word.setdefault(word, []).append(item)
    seen: set[tuple[str, str]] = set()
    found: list[tuple[Item, Item, float]] = []
    for members in by_word.values():
        for a, b in combinations(members, 2):               # `members` keep the chart order, so a pair is always (earlier, later)
            if a.kind != b.kind or (a.id, b.id) in seen:
                continue
            seen.add((a.id, b.id))
            if related(parent, a.id, b.id):
                continue
            score = jaccard(words[a.id], words[b.id])
            if score >= threshold:
                found.append((a, b, score))
    found.sort(key=lambda p: (-p[2], order[p[0].id], order[p[1].id]))
    return found


def thin_purpose(item: Item) -> str:
    """'' when the purpose says something, 'empty' when it is blank, 'repeats' when every word of it is already in the name."""
    if not item.purpose.strip():
        return "empty"
    said = tokens(item.purpose)
    return "repeats" if not said or said <= tokens(item.name) else ""


def percent(score: float) -> int:
    return int(round(score * 100))


# ---- the store -----------------------------------------------------------------------------------------------------------------

class ChartHealth:
    """Reads only. One instance per database; `notes(now)` is the whole API."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def notes(self, now: int) -> ChartNotesOut:
        conn = self.db.conn()
        items, parent = self._live(conn)
        labels = labels_of(items, parent)
        out: list[ChartNote] = []
        for a, b, score in overlap_pairs(items, parent):
            out.append(self._overlap(a, b, score, labels))
        for item in items:
            why = thin_purpose(item)
            if why:
                out.append(self._no_purpose(item, why, labels))
        out.extend(self._quiet(conn, items, now, labels))
        return ChartNotesOut(notes=out[:MAX_NOTES], total=len(out))

    # ---- one kind at a time ------------------------------------------------------------------------------------------------

    @staticmethod
    def _live(conn: sqlite3.Connection) -> tuple[list[Item], dict[str, str | None]]:
        rows = conn.execute("SELECT id, kind, name, purpose FROM org_nodes WHERE state = 'active' ORDER BY rowid").fetchall()
        parent: dict[str, str | None] = {r["id"]: None for r in rows}
        for edge in conn.execute("SELECT parent_id, child_id FROM org_edges"):
            if edge["child_id"] in parent:
                parent[edge["child_id"]] = edge["parent_id"]
        return [Item(r["id"], r["kind"], r["name"], r["purpose"]) for r in rows if r["kind"] in ("department", "division")], parent

    @staticmethod
    def _overlap(a: Item, b: Item, score: float, labels: Mapping[str, str]) -> ChartNote:
        words = f"{labels[a.id]} and {labels[b.id]} look alike ({percent(score)}% of their words)"
        say = f"merge {labels[b.id]} into {labels[a.id]}" if a.kind == "division" and b.kind == "division" else ""
        return ChartNote(kind="overlap", nodes=[NoteNode(id=a.id, label=labels[a.id]), NoteNode(id=b.id, label=labels[b.id])],
                         words=clip(words, 500), say=clip(say, 300))

    @staticmethod
    def _no_purpose(item: Item, why: str, labels: Mapping[str, str]) -> ChartNote:
        label = labels[item.id]
        words = f"{label} has no purpose written" if why == "empty" else f"The purpose of {label} only repeats its name"
        return ChartNote(kind="no_purpose", nodes=[NoteNode(id=item.id, label=label)], words=clip(words, 500),
                         say=clip(f"change the purpose of {label} to ...", 300))

    @staticmethod
    def _quiet(conn: sqlite3.Connection, items: Sequence[Item], now: int, labels: Mapping[str, str]) -> list[ChartNote]:
        """Teams with nothing unfinished whose newest task, chat message or birth is `QUIET_DAYS` or more before `now`, oldest first."""
        teams = [i for i in items if i.kind == "department"]
        if not teams:
            return []
        born = {r["id"]: r["ts"] for r in conn.execute("SELECT id, ts FROM org_nodes WHERE kind = 'department'")}
        busy = {r["dept_id"]: r["n"] for r in conn.execute(
            f"SELECT dept_id, count(*) AS n FROM tasks WHERE status IN ({','.join('?' * len(_OPEN))}) GROUP BY dept_id", _OPEN)}
        last: dict[str, int] = {}
        for r in conn.execute("SELECT dept_id, max(created_at) AS a, max(COALESCE(ended_at, 0)) AS b, max(COALESCE(last_event_at, 0)) AS c"
                              " FROM tasks GROUP BY dept_id"):
            last[r["dept_id"]] = max(r["a"] or 0, r["b"], r["c"])
        for r in conn.execute("SELECT g.department_id AS dept_id, max(m.at) AS at FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id"
                              " JOIN graph_nodes g ON g.id = s.node_id WHERE g.department_id IS NOT NULL GROUP BY g.department_id"):
            last[r["dept_id"]] = max(last.get(r["dept_id"], 0), r["at"] or 0)
        found: list[tuple[int, ChartNote]] = []
        for team in teams:
            if busy.get(team.id):
                continue
            newest = max(last.get(team.id, 0), born.get(team.id) or 0)
            idle = int(now) - newest
            if idle < QUIET_DAYS * 86400:
                continue
            label = labels[team.id]
            found.append((idle, ChartNote(kind="quiet", nodes=[NoteNode(id=team.id, label=label)],
                                          words=clip(f"{label} has had nothing for {age_words(idle)}", 500))))
        return [note for _, note in sorted(found, key=lambda pair: -pair[0])]


def labels_of(items: Sequence[Item], parent: Mapping[str, str | None]) -> dict[str, str]:
    """The text each node goes by in a sentence: its name, or its address ('Bakery site > Menu') when another live node has the same name."""
    names: dict[str, list[str]] = {}
    for item in items:
        names.setdefault(item.name.strip().lower(), []).append(item.id)
    by_id = {i.id: i for i in items}
    out: dict[str, str] = {}
    for item in items:
        if len(names[item.name.strip().lower()]) == 1:
            out[item.id] = clip(item.name.strip() or item.id, _LABEL)
            continue
        chain, node, seen = [], item.id, set()
        while node is not None and node not in seen and node in by_id:
            chain.append(by_id[node].name.strip() or node)
            seen.add(node)
            node = parent.get(node)
        out[item.id] = clip(" > ".join(reversed(chain)), _LABEL)
    return out
