"""A project's instructions and its earlier-context memory (D451).

    pm = ProjectMemory(db, redact=..., clock=...)
    pm.instructions("web") / pm.put_instructions("web", text, rev)     # one free-text field, 4,000 characters, a secret-shaped line refused, a stale save refused (409)
    pm.memory("web") / pm.add_entry / pm.put_memory(whole list, rev) / pm.delete_entry / pm.set_enabled
    pm.deliverable("web", limit)                                        # the enabled entries' text, newest first, up to `limit` characters: what a chat or a run is told
    record_run_end(conn, row, now) / record_chat_archive(conn, session_id, now)    # what the app writes, in the caller's transaction (no model is called)

Storage: two JSON documents per project in the `meta` table (`pinstr:<dept>`, `pmem:<dept>`), the way rules and notes are kept: no table, in every backup. An entry is the owner's request and the
outcome sentence of a run that finished, or the first owner line and the last reply of a chat that was archived, both already stored, passed through the egress scrub: no file content, no
reasoning, no secret (FR-19). At most 30 entries of 300 characters; the 31st automatic entry drops the oldest automatic one and never an owner's. With memory switched off nothing is sent and nothing
is appended. An existing project is seeded ONCE, on its first read or write, from its stored history (its last 10 finished runs and last 5 archived chats), marked `history`: the migration itself
stays DDL only.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from sutra_app.connectors.egress import scan
from sutra_app.library.types import violation
from sutra_app.orchestrator import project_context as ctx
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.errors import AppError, NotFound, ReadOnly, validation_error
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.owner_words import json_meta, save_meta

__all__ = ["ProjectMemory", "InstructionsOut", "MemoryOut", "EntryOut", "Stale", "record_run_end", "record_chat_archive", "MAX_ENTRIES", "ENTRY_CHARS", "INSTRUCTIONS_KEY", "MEMORY_KEY"]

log = logging.getLogger(__name__)
INSTRUCTIONS_KEY = "pinstr:{}"
MEMORY_KEY = "pmem:{}"
MAX_ENTRIES = ctx.MEMORY_ENTRIES
ENTRY_CHARS = ctx.ENTRY_CHARS
REQUEST_CHARS = 120
OUTCOME_CHARS = 160
SEED_RUNS = 10
SEED_CHATS = 5
_ENDS_REMEMBERED = ("done", "done_with_open_items", "stopped")
STALE_SENTENCE = "Changed since you opened it. Reload to see the new text."


class Stale(AppError):
    """A save made from an old read (another window saved first): refused, nothing overwritten. HTTP 409 (the code `busy`, so the closed list of error codes is unchanged); `details.stale` says why."""

    def __init__(self, current: dict | None = None) -> None:
        super().__init__("busy", STALE_SENTENCE, {"stale": True, **({"current": current} if current is not None else {})})


class InstructionsOut(BaseModel):
    text: str
    rev: str
    updated_at: str | None = None
    max_chars: int = ctx.INSTRUCTIONS_MAX


class EntryOut(BaseModel):
    n: int
    text: str
    source: str                   # run | chat | owner | history
    at: str
    ref: str
    on: bool


class MemoryOut(BaseModel):
    enabled: bool
    entries: list[EntryOut]       # newest first
    rev: str
    max_entries: int = MAX_ENTRIES
    entry_chars: int = ENTRY_CHARS


# ---- small helpers --------------------------------------------------------------------------------------------------------------------------------------------

def _oneline(text: Any, limit: int) -> str:
    """One line of stored text, scrubbed of credential shapes (replaced, as every prompt text is), white space runs one space, cut at `limit` characters."""
    line = " ".join(str(text or "").split())
    line = scan(line, replace=True)[0]
    return line if len(line) <= limit else line[: max(0, limit - 1)].rstrip() + "…"


def _date(now: float) -> str:
    return datetime.fromtimestamp(now).astimezone().strftime("%Y-%m-%d")


def _mem_rev(doc: dict) -> str:
    body = repr([doc.get("enabled", True), [[e["n"], e["text"], e["on"]] for e in doc.get("entries", [])]])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _text_rev(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _team(conn: sqlite3.Connection, dept_id: str) -> sqlite3.Row:
    found = conn.execute("SELECT d.hidden_at FROM departments d JOIN org_nodes o ON o.id = d.id WHERE d.id = ? AND o.state = 'active'", (dept_id,)).fetchone()
    if found is None:
        raise NotFound("that project")
    return found


def _entry_out(e: dict) -> EntryOut:
    return EntryOut(n=e["n"], text=e["text"], source=e["source"], at=iso_z(e["at"]), ref=e.get("ref", ""), on=bool(e["on"]))


def _newest_first(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: (e["at"], e["n"]), reverse=True)


# ---- what the app writes (in the caller's transaction) ---------------------------------------------------------------------------------------------------------

def _doc(conn: sqlite3.Connection, dept_id: str) -> dict:
    found = json_meta(conn, MEMORY_KEY.format(dept_id))
    entries = [e for e in found.get("entries", []) if isinstance(e, dict) and {"n", "text", "source", "at", "on"} <= set(e)] if isinstance(found.get("entries"), list) else []
    return {"enabled": found.get("enabled", True) is not False, "seeded": bool(found.get("seeded")), "next": int(found.get("next") or (max((e["n"] for e in entries), default=0) + 1)),
            "entries": entries}


def _save(conn: sqlite3.Connection, dept_id: str, doc: dict) -> None:
    save_meta(conn, MEMORY_KEY.format(dept_id), {"v": 1, "enabled": doc["enabled"], "seeded": doc["seeded"], "next": doc["next"], "entries": doc["entries"]})


def _run_text(request: Any, outcome: Any, at: float) -> str:
    text = f"{_date(at)}: asked '{_oneline(request, REQUEST_CHARS)}'. Result: {_oneline(outcome, OUTCOME_CHARS)}"
    return text if len(text) <= ENTRY_CHARS else text[: ENTRY_CHARS - 1].rstrip() + "…"


def _chat_text(first: Any, last: Any, at: float) -> str:
    text = f"{_date(at)}: chat '{_oneline(first, REQUEST_CHARS)}'. Last: {_oneline(last, OUTCOME_CHARS) or '(no reply)'}"
    return text if len(text) <= ENTRY_CHARS else text[: ENTRY_CHARS - 1].rstrip() + "…"


def _first_owner_line(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute("SELECT text FROM chat_messages WHERE session_id = ? AND role = 'user' AND kind = 'text' ORDER BY id LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return None
    lines = [l for l in str(row["text"]).split("\n") if not l.startswith("(attached")]
    return "\n".join(lines).strip() or None


def _last_reply(conn: sqlite3.Connection, session_id: str) -> str:
    row = conn.execute("SELECT text FROM chat_messages WHERE session_id = ? AND role <> 'user' AND kind = 'text' ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
    return str(row["text"]) if row is not None else ""


def _seed(conn: sqlite3.Connection, dept_id: str, doc: dict, exclude: set[str]) -> None:
    """The project's stored history as entries, once: its last SEED_RUNS finished runs and last SEED_CHATS archived chats, oldest first so `n` follows time."""
    have = {e.get("ref") for e in doc["entries"]} | exclude
    found: list[tuple[float, str, str, str]] = []
    for r in conn.execute("SELECT id, user_text, outcome, status, COALESCE(ended_at, created_at) AS at FROM tasks WHERE dept_id = ? AND status IN ('done','done_with_open_items','stopped')"
                          " ORDER BY COALESCE(ended_at, created_at) DESC, rowid DESC LIMIT ?", (dept_id, SEED_RUNS + len(have))):
        if r["id"] not in have and len([f for f in found if f[2] == "run"]) < SEED_RUNS:
            found.append((r["at"], _run_text(r["user_text"], r["outcome"], r["at"]), "run", r["id"]))
    for s in conn.execute("SELECT id, updated_at FROM chat_sessions WHERE node_id = ? AND kind = 'department' AND status = 'archived' ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                          (dept_id, SEED_CHATS + len(have))):
        if s["id"] in have or len([f for f in found if f[2] == "chat"]) >= SEED_CHATS:
            continue
        first = _first_owner_line(conn, s["id"])
        if first is not None:
            found.append((s["updated_at"], _chat_text(first, _last_reply(conn, s["id"]), s["updated_at"]), "chat", s["id"]))
    for at, text, _kind, ref in sorted(found):
        doc["entries"].append({"n": doc["next"], "text": text, "source": "history", "at": at, "ref": ref, "on": True})
        doc["next"] += 1
    doc["seeded"] = True


def _append(doc: dict, text: str, source: str, at: float, ref: str) -> bool:
    """One automatic entry; the cap drops the oldest AUTOMATIC one, never an owner's. False when every entry is the owner's and the list is full."""
    if len(doc["entries"]) >= MAX_ENTRIES:
        autos = sorted((e for e in doc["entries"] if e["source"] != "owner"), key=lambda e: (e["at"], e["n"]))
        if not autos:
            return False
        doc["entries"].remove(autos[0])
    doc["entries"].append({"n": doc["next"], "text": text, "source": source, "at": at, "ref": ref, "on": True})
    doc["next"] += 1
    return True


def _write_entry(conn: sqlite3.Connection, dept_id: str, ref: str, make: Any, source: str, at: float) -> None:
    if ctx.switched_off() or conn.execute("SELECT 1 FROM departments WHERE id = ?", (dept_id,)).fetchone() is None:
        return
    doc = _doc(conn, dept_id)
    if not doc["enabled"]:
        return
    if not doc["seeded"]:
        _seed(conn, dept_id, doc, {ref})
    if any(e.get("ref") == ref for e in doc["entries"]):
        return
    _append(doc, make(), source, at, ref)
    _save(conn, dept_id, doc)


def record_run_end(conn: sqlite3.Connection, row: Any, now: float) -> None:
    """A run ended: one entry with the owner's request and the outcome sentence, when it finished (done, done with open items) or was stopped. Inside the caller's transaction; never raises."""
    try:
        if row.status not in _ENDS_REMEMBERED:
            return
        _write_entry(conn, row.dept_id, row.id, lambda: _run_text(row.user_text, row.outcome, now), "run", now)
    except Exception:                                          # noqa: BLE001  (a memory that cannot be written must never keep a run from ending)
        log.exception("the project memory could not take the end of run %s", getattr(row, "id", "?"))


def record_chat_archive(conn: sqlite3.Connection, session_id: str, now: float) -> None:
    """A team's chat was archived: one entry with its first owner line and its last reply; nothing for a chat with no owner line. Inside the caller's transaction; never raises."""
    try:
        session = conn.execute("SELECT node_id, kind FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None or session["kind"] != "department":
            return
        first = _first_owner_line(conn, session_id)
        if first is None:
            return
        _write_entry(conn, session["node_id"], session_id, lambda: _chat_text(first, _last_reply(conn, session_id), now), "chat", now)
    except Exception:                                          # noqa: BLE001
        log.exception("the project memory could not take the chat %s", session_id)


# ---- the store ---------------------------------------------------------------------------------------------------------------------------------------------------

class ProjectMemory:
    def __init__(self, db: Database, redact: Any = None, *, clock: Any = None) -> None:
        self.db = db
        self._redact = redact
        self.clock = clock

    def _now(self) -> float:
        return float(self.clock.now()) if self.clock is not None else datetime.now().timestamp()

    def _check_text(self, text: str, limit: int, what: str) -> str:
        said = None
        if len(text) > limit:
            said = f"That is {len(text)} characters long; the most is {limit}. Make it shorter."
        else:
            _same, shapes = scan(text)
            if shapes or (self._redact is not None and self._redact(text) != text):
                said = f"That {what} looks like it holds a key, a token or a password, and those are never kept. Take it out and try again."
        if said:
            raise validation_error([violation("text", "refused", said)], said)
        return text

    def _writable(self, conn: sqlite3.Connection, dept_id: str) -> None:
        if _team(conn, dept_id)["hidden_at"] is not None:
            raise ReadOnly("This project was deleted.")

    # ---- instructions ----------------------------------------------------------------------------------------------------------------

    def instructions(self, dept_id: str) -> InstructionsOut:
        conn = self.db.conn()
        _team(conn, dept_id)
        return self._instr_out(json_meta(conn, INSTRUCTIONS_KEY.format(dept_id)))

    @staticmethod
    def _instr_out(doc: dict) -> InstructionsOut:
        text = str(doc.get("text") or "")
        return InstructionsOut(text=text, rev=_text_rev(text), updated_at=iso_z(doc["updated_at"]) if isinstance(doc.get("updated_at"), (int, float)) else None)

    def put_instructions(self, dept_id: str, text: str, rev: str | None = None) -> InstructionsOut:
        body = str(text or "").replace("\r\n", "\n").strip()
        self._check_text(body, ctx.INSTRUCTIONS_MAX, "text")
        with self.db.tx() as tx:
            self._writable(tx.conn, dept_id)
            current = self._instr_out(json_meta(tx.conn, INSTRUCTIONS_KEY.format(dept_id)))
            if rev is not None and rev != current.rev:
                raise Stale(current.model_dump(mode="json"))
            doc = {"v": 1, "text": body, "updated_at": tx.now()}
            save_meta(tx.conn, INSTRUCTIONS_KEY.format(dept_id), doc)
            return self._instr_out(doc)

    # ---- memory ----------------------------------------------------------------------------------------------------------------------

    def _read_doc(self, dept_id: str) -> dict:
        """The memory document, seeded from the project's history on its first read (when memory is on). Opens its own transaction only for that one write."""
        conn = self.db.conn()
        _team(conn, dept_id)
        doc = _doc(conn, dept_id)
        if doc["seeded"] or not doc["enabled"] or ctx.switched_off():
            return doc
        with self.db.tx() as tx:
            doc = _doc(tx.conn, dept_id)
            if not doc["seeded"]:
                _seed(tx.conn, dept_id, doc, set())
                _save(tx.conn, dept_id, doc)
            return doc

    def read_in(self, conn: sqlite3.Connection, dept_id: str) -> dict:
        """The same, inside the caller's open write transaction (a run's start): seeds with that connection."""
        doc = _doc(conn, dept_id)
        if not doc["seeded"] and doc["enabled"] and not ctx.switched_off():
            _seed(conn, dept_id, doc, set())
            _save(conn, dept_id, doc)
        return doc

    def _out(self, doc: dict) -> MemoryOut:
        return MemoryOut(enabled=doc["enabled"], entries=[_entry_out(e) for e in _newest_first(doc["entries"])], rev=_mem_rev(doc))

    def memory(self, dept_id: str) -> MemoryOut:
        return self._out(self._read_doc(dept_id))

    @staticmethod
    def texts_of(doc: dict, limit: int) -> list[str]:
        """The enabled entries' text, newest first, whole entries up to `limit` characters in all; nothing when memory is off."""
        if not doc["enabled"] or ctx.switched_off():
            return []
        out: list[str] = []
        used = 0
        for e in _newest_first(doc["entries"]):
            if e["on"]:
                if used + len(e["text"]) > limit:
                    break
                out.append(e["text"])
                used += len(e["text"])
        return out

    def deliverable(self, dept_id: str, limit: int) -> list[str]:
        try:
            return self.texts_of(self._read_doc(dept_id), limit)
        except NotFound:
            return []

    def _edit(self, dept_id: str, change: Any, rev: str | None = None) -> MemoryOut:
        with self.db.tx() as tx:
            self._writable(tx.conn, dept_id)
            doc = _doc(tx.conn, dept_id)
            if not doc["seeded"] and doc["enabled"] and not ctx.switched_off():
                _seed(tx.conn, dept_id, doc, set())
            if rev is not None and rev != _mem_rev(doc):
                raise Stale(self._out(doc).model_dump(mode="json"))
            result = change(doc, tx.now())
            _save(tx.conn, dept_id, doc)
            return self._out(doc) if result is None else result

    def add_entry(self, dept_id: str, text: str) -> EntryOut:
        line = _oneline_owner(text)
        self._check_text(line, ENTRY_CHARS, "line")
        if not line:
            raise validation_error([violation("text", "empty", "That line is empty.")], "That line is empty.")

        def change(doc: dict, now: float) -> EntryOut:
            if not _append(doc, line, "owner", now, ""):
                said = f"The list holds {MAX_ENTRIES} of your own lines. Take one out before adding another."
                raise validation_error([violation("text", "full", said)], said)
            return _entry_out(doc["entries"][-1])
        return self._edit(dept_id, change)       # type: ignore[return-value]

    def put_memory(self, dept_id: str, entries: list[dict], rev: str | None = None) -> MemoryOut:
        """The owner's whole list: each item {n, text, on}; an item whose `n` is kept keeps its source, date and ref; one with no known `n` is the owner's own new line; what is left out is deleted."""
        if len(entries) > MAX_ENTRIES:
            said = f"A project keeps {MAX_ENTRIES} entries. Take one out before adding another."
            raise validation_error([violation("entries", "too_many", said)], said)
        checked = []
        for item in entries:
            line = _oneline_owner(str(item.get("text", "")))
            if not line:
                raise validation_error([violation("entries", "empty", "An entry cannot be empty.")], "An entry cannot be empty.")
            self._check_text(line, ENTRY_CHARS, "line")
            checked.append((item.get("n"), line, bool(item.get("on", True))))

        def change(doc: dict, now: float) -> None:
            by_n = {e["n"]: e for e in doc["entries"]}
            out = []
            for n, line, on in checked:
                old = by_n.get(n)
                if old is not None:
                    out.append({**old, "text": line, "on": on})
                else:
                    out.append({"n": doc["next"], "text": line, "source": "owner", "at": now, "ref": "", "on": on})
                    doc["next"] += 1
            doc["entries"] = out
        return self._edit(dept_id, change, rev)

    def delete_entry(self, dept_id: str, n: int) -> MemoryOut:
        def change(doc: dict, now: float) -> None:
            if not any(e["n"] == n for e in doc["entries"]):
                raise NotFound("that entry")
            doc["entries"] = [e for e in doc["entries"] if e["n"] != n]
        return self._edit(dept_id, change)

    def set_enabled(self, dept_id: str, on: bool) -> MemoryOut:
        def change(doc: dict, now: float) -> None:
            doc["enabled"] = bool(on)
        return self._edit(dept_id, change)


def _oneline_owner(text: str) -> str:
    return " ".join(str(text or "").split())
