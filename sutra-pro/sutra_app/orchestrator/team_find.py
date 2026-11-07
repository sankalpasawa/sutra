"""Find a team or its work across the org: purposes, divisions, task titles and outcomes, with the reason each one matched (gap package
chart-insight; docs/notes/GAP2-chart-insight.md).

    TeamFind(db).search(q, limit=20)      # TeamFindOut: the teams and divisions that match, best first

The chat search (`chat_v2.ChatSearch`) finds MESSAGES and session titles. This finds TEAMS: one row per team or division with its address
('Bakery site > Menu'), which fields matched and a snippet. Four fields are looked at, in this rank order, and a row is ranked by the best
one it matched:

    name      the team's or division's name           purpose   the purpose the chart holds for it
    task      the title of one of its tasks           outcome   the words a task ended with

A task that was scoped to a division belongs to that division; a task of a team belongs to the team, and so does a task whose division was
merged away. The scope is in the SQL: only `org_nodes` rows that are `active` are read, so a node that was merged away is never returned.
A query is matched word by word, ignoring case: a field matches when it holds every word of it. A query under two characters finds nothing
('one character is not a search'). The newest `TASK_SCAN` tasks are read, so the cost stays bounded however long the app has run.

Reads only; the clock is not needed. The messages group of the answer is the chat search's, joined in by the route.
"""
import sqlite3
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from sutra_app.library.base import Value
from sutra_app.library.types import clip
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.models import Name, NodeId

__all__ = ["TeamFind", "TeamFindOut", "FoundOut", "MIN_CHARS", "MAX_WORDS", "LIMIT", "TASK_SCAN", "FIELDS", "words_of"]

MIN_CHARS = 2                # a query of fewer characters finds nothing
MAX_WORDS = 5                # words of a query that count (the rest is ignored)
LIMIT = 20                   # rows returned at most
TASK_SCAN = 2000             # the newest tasks looked through
FIELDS = ("name", "purpose", "task", "outcome")        # best first
SNIPPET = 110
_Field = Literal["name", "purpose", "task", "outcome"]


class FoundOut(Value):
    team_id: NodeId                                          # the team the row belongs to (its page is /d/<team_id>/)
    team_name: Name
    node_id: NodeId                                          # the node that matched: the team itself or one of its divisions
    kind: Literal["department", "division"]
    address: Annotated[str, StringConstraints(max_length=600)]
    matched_on: Annotated[list[_Field], Field(min_length=1, max_length=4)]
    snippet: Annotated[str, StringConstraints(max_length=SNIPPET + 4)] = ""


class TeamFindOut(Value):
    teams: Annotated[list[FoundOut], Field(max_length=LIMIT)]
    counts: dict[Literal["department", "division"], Annotated[int, Field(ge=0)]]
    truncated: bool = False                                  # more rows matched than `teams` holds


def words_of(q: object) -> list[str]:
    """The words of a query (lowercase, distinct, at most MAX_WORDS), or [] when none of them has MIN_CHARS characters ('a b' is not a search)."""
    if not isinstance(q, str):
        return []
    found = list(dict.fromkeys(q.lower().split()))[:MAX_WORDS]
    return found if any(len(word) >= MIN_CHARS for word in found) else []


def _holds(text: str, words: list[str]) -> bool:
    low = text.lower()
    return all(w in low for w in words)


def _excerpt(text: str, words: list[str]) -> str:
    """One line of `text` around the first place a word of the query appears."""
    flat = " ".join(text.split())
    if len(flat) <= SNIPPET:
        return flat
    low = flat.lower()
    at = min((p for p in (low.find(w) for w in words) if p >= 0), default=0)
    start = max(0, at - 30)
    piece = flat[start:start + SNIPPET]
    return ("…" if start else "") + piece + ("…" if start + SNIPPET < len(flat) else "")


class TeamFind:
    """Reads only. One instance per database; the connection is the calling thread's."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def search(self, q: str, limit: int = LIMIT) -> TeamFindOut:
        words = words_of(q)
        if not words:
            return TeamFindOut(teams=[], counts={"department": 0, "division": 0})
        conn = self.db.conn()
        nodes = conn.execute("SELECT id, kind, name, purpose FROM org_nodes WHERE state = 'active' AND kind IN ('department','division') ORDER BY rowid").fetchall()
        parent = {r["child_id"]: r["parent_id"] for r in conn.execute("SELECT parent_id, child_id FROM org_edges")}
        by_id = {r["id"]: r for r in nodes}
        order = {r["id"]: n for n, r in enumerate(nodes)}
        hits: dict[str, dict[str, str]] = {}                    # node id -> {field: the text that matched}
        for r in nodes:
            if _holds(r["name"], words):
                hits.setdefault(r["id"], {})["name"] = r["purpose"]                  # the snippet of a name hit is what the node is for
            if r["purpose"] and _holds(r["purpose"], words):
                hits.setdefault(r["id"], {})["purpose"] = _excerpt(r["purpose"], words)
        for t in self._tasks(conn):
            fields = hits.setdefault(t["node_id"], {}) if _holds(t["title"], words) or _holds(t["outcome"], words) else None
            if fields is None:
                continue
            if _holds(t["title"], words):
                fields.setdefault("task", t["title"])
            if _holds(t["outcome"], words):
                fields.setdefault("outcome", _excerpt(t["outcome"], words))
        first = words[0]
        ranked = sorted(hits, key=lambda i: (min(FIELDS.index(f) for f in hits[i]), 0 if by_id[i]["name"].lower().startswith(first) else 1, order[i]))
        rows = [self._row(by_id, parent, i, hits[i]) for i in ranked if i in by_id]
        counts = {"department": 0, "division": 0}
        for row in rows:
            counts[row.kind] += 1
        return TeamFindOut(teams=rows[:max(1, min(int(limit), LIMIT))], counts=counts, truncated=len(rows) > max(1, min(int(limit), LIMIT)))

    @staticmethod
    def _tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
        """The newest tasks with the node each one belongs to: its division when that division is live, else its team."""
        return conn.execute(
            "SELECT COALESCE(sn.id, d.id) AS node_id, t.title AS title, t.outcome AS outcome FROM tasks t"
            " JOIN org_nodes d ON d.id = t.dept_id AND d.state = 'active'"
            " LEFT JOIN org_nodes sn ON sn.id = t.scope_node_id AND sn.state = 'active'"
            " ORDER BY t.created_at DESC, t.rowid DESC LIMIT ?", (TASK_SCAN,)).fetchall()

    @staticmethod
    def _row(by_id: dict, parent: dict, node_id: str, found: dict[str, str]) -> FoundOut:
        chain, current, seen = [], node_id, set()
        while current in by_id and current not in seen:
            chain.append(current)
            seen.add(current)
            current = parent.get(current)
        chain.reverse()                                         # department first, the node last
        team = by_id[chain[0]] if chain else by_id[node_id]
        node = by_id[node_id]
        matched = [f for f in FIELDS if f in found]
        best = matched[0]
        return FoundOut(
            team_id=team["id"], team_name=clip(team["name"], 200), node_id=node_id, kind=node["kind"],
            address=clip(" > ".join(by_id[c]["name"] for c in chain), 600), matched_on=matched, snippet=clip(" ".join(found[best].split()), SNIPPET + 4))
