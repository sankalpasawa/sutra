"""Chat storage v2 (absorb design 2.3, D108): provider segments, full-text search, owner archive, the persisted per-chat choice.

    ChatSegments(db).record(tx, sid, "codex", provider_session_id, from_message_id)   # a segment per provider the chat has run on
    ChatSearch(db).search("deploy", scope="dept:web", include_archived=False)          # at most 50 rows, scope applied in SQL
    ChatArchive(db).archive(tx, sid) / .unarchive(tx, sid)                             # a mark, never a delete
    ChatChoices(db).set(tx, sid, "codex") / .get(sid)                                  # the owner's provider choice, survives a restart
    ChatChoices(db).set_pick(tx, sid, "claude", "sonnet", "high") / .pick(sid)         # the whole triple (D131); null provider clears all three
    cascade(own, run, team, default) -> (Pick, source)                                 # own session > run > team > policy default, a whole pick at a time
    recover_interrupted(db, chats)                                                    # at start: the direct turns the last process did not finish

There is no delete anywhere in this module. The tables and triggers are created by `schema._v2`.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from sutra_app.connectors.models import Pick
from sutra_app.library.gate import GATE
from sutra_app.orchestrator import direct_turns
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.records import ChatMessage

__all__ = ["ChatSegments", "ChatSearch", "ChatArchive", "ChatChoices", "MAX_RESULTS", "SCOPE_RE", "DIRECT_ASK", "INTERRUPTED", "recover_interrupted",
           "cascade", "SOURCES", "EFFORTS"]

MAX_RESULTS = 50
SCOPE_RE = re.compile(r"^(all|node:[a-z][a-z0-9_.-]{1,60}|dept:[a-z][a-z0-9_-]{1,40})$")
_WRITABLE_KINDS = ("org", "department", "division")


class ChatSegments:
    """One row per provider session a chat has run on, so its history outlives any provider (the old `provider_history`)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def record(tx: Tx, session_id: str, connector: str, provider_session_id: str | None, from_message_id: int) -> bool:
        """Appends a segment when `connector` differs from the last one (or there is none). True when one was added.
        `from_message_id` is the first message the new provider serves."""
        conn = tx.conn
        last = conn.execute("SELECT seq, connector FROM chat_segments WHERE session_id = ? ORDER BY seq DESC LIMIT 1", (session_id,)).fetchone()
        if not connector or (last is not None and last["connector"] == connector):
            return False
        conn.execute("INSERT INTO chat_segments(session_id, seq, connector, provider_session_id, from_message_id, at) VALUES (?,?,?,?,?,?)",
                     (session_id, 1 if last is None else last["seq"] + 1, connector, provider_session_id, int(from_message_id), tx.now()))
        return True

    def segments(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.db.conn().execute(
            "SELECT seq, connector, provider_session_id, from_message_id, at FROM chat_segments WHERE session_id = ? ORDER BY seq", (session_id,))
        return [{"seq": r["seq"], "connector": r["connector"], "provider_session_id": r["provider_session_id"],
                 "from_message_id": r["from_message_id"], "at": iso_z(r["at"])} for r in rows]


def _fts_query(q: str) -> str | None:
    """Words of the owner's text as quoted FTS5 terms (no operator can come from the owner); the last one matches as a prefix."""
    words = re.findall(r"[^\W_]+", q or "", flags=re.UNICODE)[:12]
    if not words:
        return None
    return " ".join([f'"{w}"' for w in words[:-1]] + [f'"{words[-1]}"*'])


class ChatSearch:
    def __init__(self, db: Database) -> None:
        self.db = db

    def search(self, q: str, *, scope: str = "all", include_archived: bool = False, limit: int = MAX_RESULTS) -> list[dict[str, Any]]:
        """`[{session_id, message_id, title, snippet, at, archived}]`, best match first, at most 50. `message_id` is 0 for a title match.
        The scope is part of the SQL: a row outside it is never read."""
        if SCOPE_RE.match(scope or "") is None:
            raise AppError("validation", "scope is all, node:<id> or dept:<id>")
        match = _fts_query(q)
        if match is None:
            return []
        where, args = ["chat_search MATCH ?"], [match]
        if not include_archived:
            where.append("s.status = 'active'")
        if scope.startswith("node:"):
            node = scope[5:]
            where.append("(s.node_id = ? OR s.filed_under = ?)")
            args += [node, node]
        elif scope.startswith("dept:"):
            dept = scope[5:]
            where.append("(s.node_id = ? OR s.filed_under = ? OR s.node_id IN (SELECT id FROM graph_nodes WHERE department_id = ?))")
            args += [dept, dept, dept]
        sql = ("SELECT f.session_id AS session_id, f.message_id AS message_id, s.title AS title, "
               "snippet(chat_search, 0, '', '', '…', 12) AS snippet, COALESCE(m.at, s.updated_at) AS at, s.status AS status "
               "FROM chat_search f JOIN chat_sessions s ON s.id = f.session_id "
               "LEFT JOIN chat_messages m ON f.message_id <> 0 AND m.id = f.message_id "
               f"WHERE {' AND '.join(where)} ORDER BY rank LIMIT ?")
        rows = self.db.conn().execute(sql, (*args, max(1, min(int(limit), MAX_RESULTS)))).fetchall()
        return [{"session_id": r["session_id"], "message_id": int(r["message_id"]), "title": r["title"], "snippet": r["snippet"], "at": iso_z(r["at"]),
                 "archived": r["status"] == "archived"}
                for r in rows]


class ChatArchive:
    """Archive is a mark. An archived chat keeps every message; archiving a node's active chat frees the node's slot and, in the same
    transaction, starts the node's replacement chat (invariant I1: every graph node has one ACTIVE session), carrying the choice over."""

    def __init__(self, db: Database, graph: Any = None) -> None:
        self.db = db
        self.graph = graph

    @staticmethod
    def _row(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT id, kind, node_id, status, filed_under, note FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFound("that chat")
        return row

    def archive(self, tx: Tx, session_id: str) -> bool:
        """True when the chat changed. The org chat cannot be archived (it is the one chat of the app)."""
        row = self._row(tx.conn, session_id)
        if row["kind"] == "org":
            raise AppError("rules", "The org chat cannot be archived")
        if row["status"] == "archived":
            return False
        tx.conn.execute("UPDATE chat_sessions SET status = 'archived', writable = 0, updated_at = max(updated_at, ?) WHERE id = ?", (tx.now(), session_id))
        self._replace(tx, row)
        tx.emit("chat.archived", {"session_id": session_id, "archived": True})
        return True

    def _replace(self, tx: Tx, row: sqlite3.Row) -> None:
        """When the archived chat is its node's current session, a fresh active session takes its place (`ensure_node`) and keeps `pinned`."""
        node = tx.conn.execute("SELECT body, chat_session_id FROM graph_nodes WHERE id = ?", (row["node_id"],)).fetchone()
        if node is None or node["chat_session_id"] != row["id"]:
            return
        from sutra_app.orchestrator.graph import GraphStore
        from sutra_app.orchestrator.models import NodeInit
        from sutra_app.orchestrator.nodes import WRITABLE_KINDS, ensure_node
        payload = json.loads(node["body"])
        title = tx.conn.execute("SELECT title, pinned, pinned_model, pinned_effort FROM chat_sessions WHERE id = ?", (row["id"],)).fetchone()
        out = ensure_node(tx, NodeInit(node=payload, session_title=title["title"], writable=payload["kind"] in WRITABLE_KINDS),
                          graph=self.graph or GraphStore(self.db))
        if out.chat_session_id and out.chat_session_id != row["id"] and title["pinned"]:         # the whole pick goes with the chat (D131)
            tx.conn.execute("UPDATE chat_sessions SET pinned = ?, pinned_model = ?, pinned_effort = ? WHERE id = ?",
                            (title["pinned"], title["pinned_model"], title["pinned_effort"], out.chat_session_id))

    def _relink(self, tx: Tx, node_id: str, session_id: str) -> None:
        """The graph node names `session_id` again (its payload and its column)."""
        from sutra_app.orchestrator.graph import GraphStore
        from sutra_app.orchestrator.models import NodeInit
        from sutra_app.orchestrator.nodes import WRITABLE_KINDS, ensure_node
        node = tx.conn.execute("SELECT body FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
        if node is None:
            return
        payload = json.loads(node["body"])
        title = tx.conn.execute("SELECT title FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()["title"]
        ensure_node(tx, NodeInit(node=payload, session_title=title, writable=payload["kind"] in WRITABLE_KINDS),
                    graph=self.graph or GraphStore(self.db))

    def unarchive(self, tx: Tx, session_id: str) -> bool:
        row = self._row(tx.conn, session_id)
        if row["status"] == "active":
            return False
        if row["kind"] == "legacy" or row["filed_under"] is not None:
            raise AppError("rules", "That chat stays in the archive (it was imported or its team was merged away)")
        taken = tx.conn.execute("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", (row["node_id"],)).fetchone()
        if taken is not None:
            used = tx.conn.execute("SELECT 1 FROM chat_messages WHERE session_id = ? LIMIT 1", (taken["id"],)).fetchone()
            if used is not None:
                raise AppError("busy", "This team already has an open chat; archive that one first")
            # the empty chat that archiving started steps aside (archived, kept) so this one is the node's session again
            tx.conn.execute("UPDATE chat_sessions SET status = 'archived', writable = 0, updated_at = max(updated_at, ?) WHERE id = ?", (tx.now(), taken["id"]))
        writable = 1 if row["kind"] in _WRITABLE_KINDS else 0
        tx.conn.execute("UPDATE chat_sessions SET status = 'active', writable = ?, updated_at = max(updated_at, ?) WHERE id = ?", (writable, tx.now(), session_id))
        if taken is not None:
            self._relink(tx, row["node_id"], session_id)
        tx.emit("chat.archived", {"session_id": session_id, "archived": False})
        return True


SOURCES = ("own", "run", "team", "default")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def cascade(own: Pick | None, run: Pick | None, team: Pick | None, default: Pick | None) -> tuple[Pick, str]:
    """The pick an agent runs on and where it comes from: its own session's, else the run's, else the team's, else the policy default. A whole pick
    replaces, never field by field (a model of one provider is meaningless on another). A pick with no provider is "Default": nobody chose. The
    result is `(Pick(), "default")` when even the default is unknown."""
    for source, found in (("own", own), ("run", run), ("team", team)):
        if found is not None and found.provider:
            return found, source
    return (default if default is not None else Pick()), "default"


class ChatChoices:
    """The owner's per-chat provider, model and effort (`chat_sessions.pinned`, `pinned_model`, `pinned_effort`). '' means the policy decides."""

    VALID = ("claude", "codex", "")

    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, session_id: str) -> str:
        row = self.db.conn().execute("SELECT pinned FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        return row["pinned"] if row is not None else ""

    def set(self, tx: Tx, session_id: str, provider: str | None) -> None:
        """The provider only; a model and effort that went with an earlier provider are cleared (a whole pick replaces)."""
        self.set_pick(tx, session_id, provider, None, None)

    def pick(self, session_id: str) -> Pick:
        return self.pick_in(self.db.conn(), session_id)

    @staticmethod
    def pick_in(conn: sqlite3.Connection, session_id: str | None) -> Pick:
        """The session's own pick; `Pick()` ("Default") when it has none or does not exist."""
        row = conn.execute("SELECT pinned, pinned_model, pinned_effort FROM chat_sessions WHERE id = ?", (session_id,)).fetchone() if session_id else None
        if row is None or not row["pinned"]:
            return Pick()
        return Pick(provider=row["pinned"], model=row["pinned_model"] or None, effort=row["pinned_effort"] or None)

    def set_pick(self, tx: Tx, session_id: str, provider: str | None, model: str | None = None, effort: str | None = None) -> Pick:
        """Store the owner's whole choice for one chat. A null provider clears all three; a model or effort without a provider is refused."""
        value = provider or ""
        if value not in self.VALID:
            raise AppError("validation", "the provider is claude or codex")
        if not value and (model or effort):
            raise AppError("validation", "a model or an effort is chosen together with its provider")
        if effort and effort not in EFFORTS:
            raise AppError("validation", f"the effort is one of {', '.join(EFFORTS)}")
        cur = tx.conn.execute("UPDATE chat_sessions SET pinned = ?, pinned_model = ?, pinned_effort = ? WHERE id = ?",
                              (value, (model or "") if value else "", (effort or "") if value else "", session_id))
        if cur.rowcount == 0:
            raise NotFound("that chat")
        return self.pick_in(tx.conn, session_id)


# ---- direct turns the last process did not finish ---------------------------------------------------------------------------------------------------

DIRECT_ASK = "direct-ask:"           # the src_ref prefix of the owner's line that starts a direct turn (api/chat_v2._store_user_line adds a random tail)
INTERRUPTED = "Interrupted: the app closed before the model answered."


def recover_interrupted(db: Database, chats: Any) -> int:
    """Marks every owner's direct line that has no ending: the error line `INTERRUPTED`, stored like any failed turn's (`direct_turns.failed`: src_ref
    `direct:<id>`, so the page offers Retry and the line is answered for good). A process that dies mid-turn (SIGKILL, a crash, a power cut) cannot say so itself;
    a graceful stop already stores its own note. Called once at start, before any turn of this process exists. The team route's lines carry no mark and are
    never touched. -> how many lines were marked."""
    rows = db.conn().execute(
        "SELECT m.session_id AS sid, m.id AS id FROM chat_messages m WHERE m.src_ref LIKE ? AND NOT EXISTS ("
        " SELECT 1 FROM chat_messages r WHERE r.session_id = m.session_id AND r.src_ref = 'direct:' || m.id) ORDER BY m.id", (DIRECT_ASK + "%",)).fetchall()
    marked = 0
    for row in rows:
        with db.tx() as tx:
            for ending in direct_turns.failed(int(row["id"]), "", INTERRUPTED):
                posted = chats.post(tx, row["sid"], GATE.check("chat_message", ChatMessage(
                    kind=ending.kind, session_id=row["sid"], role="agent", who="sutra", text=ending.text, blocks=ending.blocks, src_ref=ending.src_ref,
                    at=tx.now()), ctx=tx.ctx))
                marked += 1 if posted is not None else 0
    return marked
