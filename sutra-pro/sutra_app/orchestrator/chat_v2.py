"""Chat storage v2 (absorb design 2.3, D108): provider segments, full-text search, owner archive, the persisted per-chat choice.

    ChatSegments(db).record(tx, sid, "codex", provider_session_id, from_message_id)   # a segment per provider the chat has run on
    ChatSearch(db).search("deploy", scope="dept:web", include_archived=False)          # at most 50 rows, scope applied in SQL
    ChatArchive(db).archive(tx, sid) / .unarchive(tx, sid)                             # a mark, never a delete
    ChatChoices(db).set(tx, sid, "codex") / .get(sid)                                  # the owner's choice, survives a restart

There is no delete anywhere in this module. The tables and triggers are created by `schema._v2`.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.ids import iso_z

__all__ = ["ChatSegments", "ChatSearch", "ChatArchive", "ChatChoices", "MAX_RESULTS", "SCOPE_RE"]

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
    """Archive is a mark. An archived chat keeps every message; archiving a node's active chat frees the node's slot (a fresh chat may start)."""

    def __init__(self, db: Database) -> None:
        self.db = db

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
        tx.emit("chat.archived", {"session_id": session_id, "archived": True})
        return True

    def unarchive(self, tx: Tx, session_id: str) -> bool:
        row = self._row(tx.conn, session_id)
        if row["status"] == "active":
            return False
        if row["kind"] == "legacy" or row["filed_under"] is not None:
            raise AppError("rules", "That chat stays in the archive (it was imported or its team was merged away)")
        taken = tx.conn.execute("SELECT 1 FROM chat_sessions WHERE node_id = ? AND status = 'active'", (row["node_id"],)).fetchone()
        if taken is not None:
            raise AppError("busy", "This team already has an open chat; archive that one first")
        writable = 1 if row["kind"] in _WRITABLE_KINDS else 0
        tx.conn.execute("UPDATE chat_sessions SET status = 'active', writable = ?, updated_at = max(updated_at, ?) WHERE id = ?", (writable, tx.now(), session_id))
        tx.emit("chat.archived", {"session_id": session_id, "archived": False})
        return True


class ChatChoices:
    """The owner's per-chat provider (`chat_sessions.pinned`). '' means the policy decides."""

    VALID = ("claude", "codex", "")

    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, session_id: str) -> str:
        row = self.db.conn().execute("SELECT pinned FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        return row["pinned"] if row is not None else ""

    def set(self, tx: Tx, session_id: str, provider: str | None) -> None:
        value = provider or ""
        if value not in self.VALID:
            raise AppError("validation", "the provider is claude or codex")
        cur = tx.conn.execute("UPDATE chat_sessions SET pinned = ? WHERE id = ?", (value, session_id))
        if cur.rowcount == 0:
            raise NotFound("that chat")
