"""The in-flight turn checkpoint (streaming design D211, migration v5): what a restart after a crash turns into a partial reply.

    save(db, generation_id=..., session_id=..., message_id=..., attempt=..., attempt_no=..., state=..., seq=..., blocks=[...])   # one INSERT OR REPLACE
    load(db, session_id)           # the newest checkpoint of a chat, or None
    all_rows(db)                   # every checkpoint (the start-up recovery reads these)
    drop(tx, generation_id)        # inside the transaction that stores the final reply
    drop_session(db, session_id)

`blocks` is the snapshot rows of the current attempt as the live view had them (`BlockAccumulator.snapshot()`), already redacted. The JSON is capped at
`MAX_JSON` bytes: when it would be longer, the OLDEST text is cut first and the block says `truncated`. Never an UPDATE of `chat_messages` (its FTS trigger would
re-index the text on every save). The caller serialises outside any lock; this module only writes.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

from sutra_app.orchestrator.db import Database, Tx

__all__ = ["MAX_JSON", "save", "load", "all_rows", "drop", "drop_session", "cap_blocks", "stored_blocks", "shown_text"]

MAX_JSON = 256 * 1024


def _dump(blocks: list[dict]) -> str:
    return json.dumps(blocks, separators=(",", ":"), ensure_ascii=False)


def _size(blocks: list[dict]) -> int:
    return len(_dump(blocks).encode("utf-8"))


def cap_blocks(blocks: list[dict], limit: int = MAX_JSON) -> list[dict]:
    """`blocks` whose JSON is at most `limit` characters: text is trimmed from the head of the OLDEST text block first (the newest words are the ones a person wants
    back), a trimmed block says `truncated`. Never raises; blocks without text are never touched (a very long list of tool lines is cut from the front last)."""
    rows = [dict(b) for b in blocks]
    size = _size(rows)
    for row in rows:
        if size <= limit:
            return rows
        text = row.get("text")
        if row.get("type") == "text" and isinstance(text, str) and text:
            drop = min(len(text), size - limit + 64)          # the margin covers the `truncated` key this row gains
            row["text"] = text[drop:]
            row["truncated"] = True
            size = _size(rows)
    while rows and _size(rows) > limit:            # only non-text rows are left and they are still too long: keep the newest
        rows.pop(0)
    return rows


def save(db: Database, *, generation_id: str, session_id: str, message_id: int, attempt: int, attempt_no: int, state: str, seq: int, blocks: list[dict],
         now: Optional[float] = None) -> None:
    payload = _dump(cap_blocks(blocks))
    with db.tx() as tx:
        tx.conn.execute(
            "INSERT OR REPLACE INTO chat_turn_checkpoint(generation_id, session_id, message_id, attempt, attempt_no, state, seq, blocks_json, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (generation_id, session_id, int(message_id), int(attempt), int(attempt_no), state, int(seq), payload, time.time() if now is None else now))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        blocks = json.loads(row["blocks_json"])
    except ValueError:
        blocks = []
    return {"generation_id": row["generation_id"], "session_id": row["session_id"], "message_id": row["message_id"], "attempt": row["attempt"],
            "attempt_no": row["attempt_no"], "state": row["state"], "seq": row["seq"], "blocks": blocks if isinstance(blocks, list) else [], "updated_at": row["updated_at"]}


_COLUMNS = "generation_id, session_id, message_id, attempt, attempt_no, state, seq, blocks_json, updated_at"


def load(db: Database, session_id: str) -> Optional[dict[str, Any]]:
    row = db.conn().execute(f"SELECT {_COLUMNS} FROM chat_turn_checkpoint WHERE session_id = ? ORDER BY updated_at DESC, rowid DESC LIMIT 1", (session_id,)).fetchone()
    return None if row is None else _row(row)


def all_rows(db: Database) -> list[dict[str, Any]]:
    return [_row(r) for r in db.conn().execute(f"SELECT {_COLUMNS} FROM chat_turn_checkpoint ORDER BY updated_at, rowid")]


def drop(tx: Tx, generation_id: str) -> None:
    tx.conn.execute("DELETE FROM chat_turn_checkpoint WHERE generation_id = ?", (generation_id,))


def drop_session(db: Database, session_id: str) -> None:
    with db.tx() as tx:
        tx.conn.execute("DELETE FROM chat_turn_checkpoint WHERE session_id = ?", (session_id,))


def stored_blocks(rows: list[dict]) -> list[dict]:
    """A checkpoint's snapshot rows as the `ChatBlock` dicts a stored message carries (text, thinking, tool use; no tool result: the output of a tool is never part of a
    snapshot). What a restart after a crash stores for a turn that was in flight."""
    out: list[dict] = []
    for row in rows:
        kind = row.get("type")
        if kind == "text" and row.get("text"):
            block = {"type": "text", "kind": "other", "text": str(row["text"])}
            if row.get("truncated"):
                block["truncated"] = True
            out.append(block)
        elif kind == "thinking":
            out.append({"type": "thinking", "kind": "other", "text": ""})
        elif kind == "tool_use":
            name = str(row.get("name") or "")[:200]
            out.append({"type": "tool_use", "kind": row.get("kind") if row.get("kind") in ("read", "edit", "run", "search", "web", "other") else "other", "name": name,
                        "text": str(row.get("title") or name)[:1000]})
    return out


def shown_text(rows: list[dict]) -> str:
    """The text a checkpoint's text blocks hold, in order (the partial reply of a turn that was in flight)."""
    return "".join(str(r.get("text") or "") for r in rows if r.get("type") == "text")
