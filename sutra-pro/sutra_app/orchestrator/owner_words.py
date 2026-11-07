"""What the owner types into a standing rule or an owner note, checked the same way for both (GAP2 rules-notes).

    refusal(text, redact=None, limit=300)   None when the text may be stored, else one plain sentence saying why not: empty, too long, or
                                            it holds a credential (a key, a token, a password; the shapes of `connectors.egress` and the
                                            app's own secret values through `redact`)
    local_today(clock)                      today's date in the owner's own time zone, as an ISO `YYYY-MM-DD` (for a note's expiry)
    json_meta(conn, key) / save_meta(conn, key, doc)   one JSON document in the `meta` table (no migration, so it is in every backup)

Nothing here guesses: a refused line is never stored, trimmed or half-kept.
"""
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sutra_app.connectors.egress import scan
from sutra_app.library.practice import clean_text

__all__ = ["refusal", "local_today", "json_meta", "save_meta", "is_date"]


def refusal(text: str, redact: Callable[[str], str] | None = None, limit: int = 300) -> str | None:
    """None when `text` may be stored, else the sentence that tells the owner why not (shown as typed, never echoing the secret)."""
    line = clean_text(text)
    if not line:
        return "That line is empty."
    if len(line) > limit:
        return f"That line is {len(line)} characters long; the most is {limit}. Make it shorter."
    _unchanged, shapes = scan(line)
    if shapes or (redact is not None and redact(line) != line):
        return "That line looks like it holds a key, a token or a password, and those are never kept. Take it out and try again."
    return None


def is_date(value: str) -> bool:
    """True for a real calendar date written `YYYY-MM-DD`."""
    if len(value) != 10:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def local_today(clock: Any) -> str:
    """The owner's date now (the machine's time zone), from the app clock's epoch seconds."""
    return datetime.fromtimestamp(clock.now()).astimezone().strftime("%Y-%m-%d")


def json_meta(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    """The JSON document stored under `key` in `meta`; {} when there is none or it cannot be read (a damaged value is never trusted)."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return {}
    try:
        found = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def save_meta(conn: sqlite3.Connection, key: str, doc: dict[str, Any]) -> None:
    """Store `doc` under `key` (the upsert of the chart store's own meta rows). Call inside `db.tx()`."""
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, json.dumps(doc, ensure_ascii=False, separators=(",", ":"))))
