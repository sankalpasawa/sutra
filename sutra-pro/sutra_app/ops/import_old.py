"""`sutra-pro import-old-chats [--source ~/.sutra-ui/chats] [--apply]`: bring the old Sutra app's chats in, read only (absorb design section 4, D113).

One-way and explicit; nothing is migrated silently and NOTHING in the old folder is written, moved or deleted (D98). Dry run by default: it prints
the number of chats and messages and what would be flattened. `--apply` takes the usual backup first (when a database exists), refuses while
another Sutra Pro holds the data folder (D94), then writes one transaction per chat.

Mapping: one old chat is one `chat_sessions` row `cs_old_<first 12 of its id>`, kind `legacy`, node `legacy`, archived, read only; the title is kept;
the note says where it came from; the connector is the last segment's provider when it is claude or codex (a DeepSeek chat is history only).
Messages: user -> user, assistant -> agent (`old Sutra`); the text blocks are the message; tool calls and results collapse into ONE note per
assistant turn (tool names and counts, never inputs or outputs); thinking is dropped; an old `{role, text, ts}` message is a text message. `src_ref`
is `old:<id>:<index>`, so a second run adds nothing. Every text goes through the `Redactor` and the credential shapes of `connectors.egress` first.
Not imported, and the command says so: archive marks, the providers' own transcripts, the registry of departments, settings, agents, drafts.

A chat the store cannot hold never stops the import. A file whose `sutra_id` is not a hex string is unreadable (listed, like malformed JSON). A lone
surrogate half in a string (JavaScript leaves one when it cuts a string inside an emoji) is stored as U+FFFD and counted. A time before 1970
reads as unknown, like one that does not parse. Anything else the gate refuses skips that chat alone (one transaction each, so nothing of it is
stored), and the command names it; the dry run rehearses the same code on a throwaway database, so it names them too. A store that fails
(disk, lock, a damaged database) ends the command with one sentence and exit 1, never a traceback; a rerun adds nothing twice.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sutra_app.config import default_env_file
from sutra_app.connectors.egress import scan
from sutra_app.library.gate import GATE, GateError
from sutra_app.ops import cli, lock
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import Database, SchemaError
from sutra_app.orchestrator.errors import StoreBusy
from sutra_app.orchestrator.records import ChatMessage, ChatSession
from sutra_app.orchestrator.redact import Redactor

__all__ = ["OldChat", "Plan", "read_chats", "plan", "import_chats", "rehearse", "register", "cmd_import", "default_source", "NOT_IMPORTED"]

SOURCE_HINT = "~/.sutra-ui/chats"
NOT_IMPORTED = ("archive marks (every imported chat is archived)", "the providers' own transcripts under ~/.claude and ~/.gemini",
                "the registry of departments (tell the chat agent which teams you want; it builds the chart)", "settings, agents, drafts, connectors")
WHO = "old Sutra"
_ID = re.compile(r"[0-9a-f]{12,64}")                  # used with fullmatch: `$` would let a trailing newline through
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")      # half an emoji: not UTF-8, so neither the gate nor SQLite can take it


def default_source() -> Path:
    return Path.home() / ".sutra-ui" / "chats"


@dataclass
class OldChat:
    sutra_id: str
    title: str
    cwd: str
    created: str
    updated: str
    providers: list[str]
    messages: list[dict]
    file: str = ""
    repaired: int = 0            # lone surrogate halves replaced by U+FFFD


@dataclass
class Plan:
    chats: int = 0
    non_empty: int = 0
    messages: int = 0
    notes: int = 0               # tool collapses
    thinking_dropped: int = 0
    unreadable: list[str] = field(default_factory=list)
    repaired: int = 0            # chats with at least one lone surrogate half
    providers: Counter = field(default_factory=Counter)


def _repair(value: Any, found: list[int]) -> Any:
    """`value` (parsed JSON) with every lone surrogate half in its strings and keys replaced by U+FFFD; `found[0]` counts them."""
    if isinstance(value, str):
        value, n = _LONE_SURROGATE.subn("\ufffd", value)
        found[0] += n
        return value
    if isinstance(value, list):
        return [_repair(item, found) for item in value]
    if isinstance(value, dict):
        return {_repair(key, found): _repair(item, found) for key, item in value.items()}
    return value


def read_chats(source: Path) -> tuple[list[OldChat], list[str]]:
    """The chat files of `source` (the `_index.json` is not a chat), in a stable order; an unreadable file is named, not fatal."""
    chats: list[OldChat] = []
    bad: list[str] = []
    for path in sorted(Path(source).glob("*.json")):
        if path.name.startswith("_"):
            continue
        found = [0]
        try:
            doc = _repair(json.loads(path.read_text(encoding="utf-8")), found)
        except (OSError, ValueError, RecursionError):                    # a document nested past the parser's limit is not a chat either
            bad.append(path.name)
            continue
        sutra_id = doc.get("sutra_id") if isinstance(doc, dict) else None
        if not isinstance(sutra_id, str) or not _ID.fullmatch(sutra_id) or not isinstance(doc.get("messages", []), list):
            bad.append(path.name)
            continue
        history = [h for h in doc.get("provider_history", []) if isinstance(h, dict)] if isinstance(doc.get("provider_history", []), list) else []
        chats.append(OldChat(sutra_id=sutra_id, title=str(doc.get("title") or ""), cwd=str(doc.get("cwd") or ""), created=str(doc.get("created") or ""),
                             updated=str(doc.get("updated") or ""), providers=[str(h.get("provider", "")) for h in history],
                             messages=[m for m in doc["messages"] if isinstance(m, dict)], file=path.name, repaired=found[0]))
    return chats, bad


def turns(chat: OldChat) -> list[dict]:
    """The chat as flat turns: `{index, role, ts, text, tools: Counter, thinking}`. A turn with neither text nor tools is left out."""
    out = []
    for index, m in enumerate(chat.messages):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        texts, tools, thinking = [], Counter(), 0
        blocks = m.get("blocks")
        if isinstance(blocks, list):
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                kind = b.get("type")
                if kind == "text" and isinstance(b.get("text"), str):
                    texts.append(b["text"])
                elif kind == "tool_use":
                    tools[str(b.get("name") or "tool")[:60]] += 1
                elif kind == "tool_result":
                    pass                                         # a result is part of its call's note; its content is never kept
                elif kind == "thinking":
                    thinking += 1
        elif isinstance(m.get("text"), str):
            texts.append(m["text"])
        text = "\n\n".join(t for t in texts if t.strip()).strip()
        if text or tools:
            out.append({"index": index, "role": role, "ts": str(m.get("ts") or ""), "text": text, "tools": tools, "thinking": thinking})
    return out


def plan(chats: list[OldChat], bad: list[str] | None = None) -> Plan:
    p = Plan(chats=len(chats), unreadable=list(bad or []))
    for chat in chats:
        p.repaired += 1 if chat.repaired else 0
        flat = turns(chat)
        p.non_empty += 1 if flat else 0
        for t in flat:
            p.messages += 1 if t["text"] else 0
            p.notes += 1 if t["tools"] else 0
            p.thinking_dropped += t["thinking"]
        if chat.providers:
            p.providers[chat.providers[-1]] += 1
    return p


def _epoch(value: str, fallback: int = 0) -> int:
    """Seconds since 1970 of an ISO time. `fallback` when it does not parse or is before 1970: the store holds no negative time."""
    try:
        seconds = int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError, OverflowError, OSError):         # a time with no zone, long ago, can overflow or be refused by the system
        return fallback
    return seconds if seconds >= 0 else fallback


def _note_text(tools: Counter) -> str:
    return "Tools used: " + ", ".join(f"{name} x{n}" if n > 1 else name for name, n in sorted(tools.items())) if tools else ""


def _write_chat(db: Database, store: ChatStore, chat: OldChat, redactor: Redactor) -> dict[str, Any]:
    """One chat in one transaction. -> {added, present, messages, scrubbed}. Raises what the gate or the models refuse; nothing of the chat is stored then."""
    scrubbed: Counter = Counter()

    def clean(text: str) -> str:
        found, counts = scan(redactor(text), replace=True)
        scrubbed.update(counts)
        return found

    out = {"added": 0, "present": 0, "messages": 0, "scrubbed": scrubbed}
    sid = "cs_old_" + chat.sutra_id[:12]
    created = _epoch(chat.created)
    updated = max(_epoch(chat.updated, created), created)
    connector = chat.providers[-1] if chat.providers and chat.providers[-1] in ("claude", "codex") else ""
    folder = Path(chat.cwd.replace("\\", "/")).name if chat.cwd else ""
    title = " ".join(clean(chat.title).split())[:200] or "Old chat"
    note = f"Imported from old Sutra{', folder ' + folder if folder else ''}"[:500]
    with db.tx() as tx:
        if tx.conn.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (sid,)).fetchone() is None:
            s = GATE.check("chat_session", ChatSession(kind="legacy", id=sid, node_id="legacy", title=title, writable=False, status="archived",
                                                       connector=connector, note=note, created_at=created, updated_at=updated), ctx=tx.ctx).model
            tx.conn.execute(
                "INSERT INTO chat_sessions(id, node_id, kind, title, writable, status, connector, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (s.id, s.node_id, s.kind, s.title, 0, "archived", s.connector, s.note, s.created_at, s.updated_at))
            out["added"] += 1
        else:
            out["present"] += 1
        for t in turns(chat):
            at = _epoch(t["ts"], created)
            if t["text"]:
                posted = store.post(tx, sid, GATE.check("chat_message", ChatMessage(
                    kind="text", session_id=sid, role=t["role"] if t["role"] == "user" else "agent", who="user" if t["role"] == "user" else WHO,
                    text=clean(t["text"])[:200_000], src_ref=f"old:{chat.sutra_id}:{t['index']}", at=at), ctx=tx.ctx))
                out["messages"] += 1 if posted is not None else 0
            if t["tools"] and t["role"] == "assistant":
                posted = store.post(tx, sid, GATE.check("chat_message", ChatMessage(
                    kind="note", session_id=sid, role="agent", who=WHO, text=_note_text(t["tools"]), src_ref=f"old:{chat.sutra_id}:{t['index']}:tools", at=at),
                    ctx=tx.ctx))
                out["messages"] += 1 if posted is not None else 0
    return out


def import_chats(db: Database, chats: list[OldChat], redactor: Redactor) -> dict[str, Any]:
    """Write the chats, one transaction each. -> {chats_added, chats_present, messages_added, scrubbed: {shape: n}, unstorable: [file]}.
    A chat the gate or the models refuse (a ValueError, a GateError) is skipped and named in `unstorable`; the others are written."""
    store = ChatStore(db)
    result: dict[str, Any] = {"chats_added": 0, "chats_present": 0, "messages_added": 0, "scrubbed": Counter(), "unstorable": []}
    for chat in chats:
        try:
            done = _write_chat(db, store, chat, redactor)
        except (GateError, ValueError):
            result["unstorable"].append(chat.file or chat.sutra_id)
            continue
        result["chats_added"] += done["added"]
        result["chats_present"] += done["present"]
        result["messages_added"] += done["messages"]
        result["scrubbed"].update(done["scrubbed"])
    result["scrubbed"] = dict(result["scrubbed"])
    return result


def rehearse(chats: list[OldChat], redactor: Redactor) -> list[str]:
    """The files of the chats the store would refuse: the real import code run into a throwaway database, so nothing of the owner's is touched."""
    with tempfile.TemporaryDirectory(prefix="sutra-import-rehearsal-", ignore_cleanup_errors=True) as scratch:
        db = Database(Path(scratch) / "rehearsal.sqlite3", lambda events: None)
        try:
            db.migrate()
            return import_chats(db, chats, redactor)["unstorable"]
        finally:
            db.close()


def _names(files: list[str]) -> str:
    return f"{', '.join(files[:5])}{' ...' if len(files) > 5 else ''}"


def cmd_import(args: argparse.Namespace) -> int:
    source = (args.source or default_source()).expanduser()
    if not source.is_dir():
        print(f"sutra-pro: there is no folder {source} (pass --source)", file=sys.stderr)
        return 1
    chats, bad = read_chats(source)
    p = plan(chats, bad)
    redactor = Redactor(default_env_file())
    refused: list[str] = []
    no_rehearsal = ""
    if not args.apply:                                                   # the dry run finds what --apply would skip; --apply finds it as it writes
        try:
            refused = rehearse(chats, redactor)
        except (OSError, sqlite3.Error) as exc:                          # no room in the temporary folder: the rest of the dry run still stands
            no_rehearsal = f"The check of what the store would refuse could not run ({str(exc).rstrip('.')}); --apply still skips such a chat and names it."
    lines = [f"Old chats in {source}: {p.chats} ({p.non_empty} with messages), {p.messages} messages.",
             f"Would be flattened: {p.notes} turn(s) of tool calls become one note each (names and counts only); {p.thinking_dropped} thinking block(s) are dropped."]
    if p.providers:
        lines.append("Last provider of each chat: " + ", ".join(f"{name} {n}" for name, n in sorted(p.providers.items())) + ". Only claude and codex are kept; others are history only.")
    if bad:
        lines.append(f"Could not read {len(bad)} file(s): {_names(bad)}.")
    if p.repaired:
        lines.append(f"{p.repaired} chat(s) hold a lone surrogate half (a string cut inside an emoji); it is stored as U+FFFD.")
    if refused:
        lines.append(f"Could not store {len(refused)} chat(s): {_names(refused)}. They would be skipped; every other chat imports.")
    if no_rehearsal:
        lines.append(no_rehearsal)
    lines.append("Not imported: " + "; ".join(NOT_IMPORTED) + ".")
    payload: dict[str, Any] = {"source": str(source), "chats": p.chats, "non_empty": p.non_empty, "messages": p.messages, "notes": p.notes,
                               "thinking_dropped": p.thinking_dropped, "unreadable": bad, "repaired": p.repaired, "unstorable": refused, "applied": False}
    if not args.apply:
        lines.append("Dry run: nothing was written. Add --apply to import (a backup is taken first).")
        cli.emit(args, payload, lines)
        return 0
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    from sutra_app.ops import backup
    held = lock.InstanceLock(settings.data_dir)          # also for a folder that does not exist yet: taking the lock makes it, private (0700)
    try:
        try:
            if not held.acquire():
                print(f"sutra-pro: Sutra Pro is running on {settings.data_dir}; stop it first (`sutra-pro stop`). Nothing was changed", file=sys.stderr)
                return 1
            if settings.db_path.exists():
                made = backup.create_backup(settings)
                lines.append(f"Backup written first: {made.path}")
                payload["backup"] = str(made.path)
            db = Database(settings.db_path, lambda events: None)
            try:
                db.migrate()
                done = import_chats(db, chats, redactor)
            finally:
                db.close()
        finally:
            held.release()
    except (backup.BackupError, SchemaError, StoreBusy, sqlite3.Error, OSError) as exc:
        print(f"sutra-pro: the import stopped: {str(exc).rstrip('.')}. Each chat is one transaction, so none is half imported; run it again once that is fixed.",
              file=sys.stderr)
        return 1
    payload.update(applied=True, **done)
    lines.append(f"Imported {done['chats_added']} chat(s) ({done['chats_present']} already there), {done['messages_added']} message(s) added.")
    if done["unstorable"]:
        lines.append(f"Could not store {len(done['unstorable'])} chat(s): {_names(done['unstorable'])}. They were skipped; every other chat was imported.")
    if done["scrubbed"]:
        lines.append("Credential shapes scrubbed: " + ", ".join(f"{k} {v}" for k, v in sorted(done["scrubbed"].items())) + ".")
    lines.append("They are archived and read only: find them under Older chats and in search.")
    cli.emit(args, payload, lines)
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("import-old-chats", parents=[cli.common_parser()],
                       help=f"bring the old Sutra app's chats in, read only (dry run unless --apply; default source {SOURCE_HINT})")
    p.add_argument("--source", type=Path, metavar="DIR", help=f"the old app's chats folder (default {SOURCE_HINT})")
    p.add_argument("--apply", action="store_true", help="write the chats (a backup is taken first); without it nothing is written")
    p.set_defaults(func=cmd_import)
