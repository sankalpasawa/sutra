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
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sutra_app.config import default_env_file
from sutra_app.connectors.egress import scan
from sutra_app.library.gate import GATE
from sutra_app.ops import cli, lock
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.records import ChatMessage, ChatSession
from sutra_app.orchestrator.redact import Redactor

__all__ = ["OldChat", "Plan", "read_chats", "plan", "import_chats", "register", "cmd_import", "default_source", "NOT_IMPORTED"]

SOURCE_HINT = "~/.sutra-ui/chats"
NOT_IMPORTED = ("archive marks (every imported chat is archived)", "the providers' own transcripts under ~/.claude and ~/.gemini",
                "the registry of departments (tell the chat agent which teams you want; it builds the chart)", "settings, agents, drafts, connectors")
WHO = "old Sutra"
_ID = re.compile(r"^[0-9a-f]{12,64}$")


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


@dataclass
class Plan:
    chats: int = 0
    non_empty: int = 0
    messages: int = 0
    notes: int = 0               # tool collapses
    thinking_dropped: int = 0
    unreadable: list[str] = field(default_factory=list)
    providers: Counter = field(default_factory=Counter)


def read_chats(source: Path) -> tuple[list[OldChat], list[str]]:
    """The chat files of `source` (the `_index.json` is not a chat), in a stable order; an unreadable file is named, not fatal."""
    chats: list[OldChat] = []
    bad: list[str] = []
    for path in sorted(Path(source).glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(path.name)
            continue
        if not isinstance(doc, dict) or not _ID.match(str(doc.get("sutra_id", ""))) or not isinstance(doc.get("messages", []), list):
            bad.append(path.name)
            continue
        history = [h for h in doc.get("provider_history", []) if isinstance(h, dict)] if isinstance(doc.get("provider_history", []), list) else []
        chats.append(OldChat(sutra_id=doc["sutra_id"], title=str(doc.get("title") or ""), cwd=str(doc.get("cwd") or ""), created=str(doc.get("created") or ""),
                             updated=str(doc.get("updated") or ""), providers=[str(h.get("provider", "")) for h in history],
                             messages=[m for m in doc["messages"] if isinstance(m, dict)], file=path.name))
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
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return fallback


def _note_text(tools: Counter) -> str:
    return "Tools used: " + ", ".join(f"{name} x{n}" if n > 1 else name for name, n in sorted(tools.items())) if tools else ""


def import_chats(db: Database, chats: list[OldChat], redactor: Redactor) -> dict[str, Any]:
    """Write the chats, one transaction each. -> {chats_added, chats_present, messages_added, scrubbed: {shape: n}}."""
    store = ChatStore(db)
    result: dict[str, Any] = {"chats_added": 0, "chats_present": 0, "messages_added": 0, "scrubbed": Counter()}

    def clean(text: str) -> str:
        found, counts = scan(redactor(text), replace=True)
        result["scrubbed"].update(counts)
        return found

    for chat in chats:
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
                result["chats_added"] += 1
            else:
                result["chats_present"] += 1
            for t in turns(chat):
                at = _epoch(t["ts"], created)
                if t["text"]:
                    posted = store.post(tx, sid, GATE.check("chat_message", ChatMessage(
                        kind="text", session_id=sid, role=t["role"] if t["role"] == "user" else "agent", who="user" if t["role"] == "user" else WHO,
                        text=clean(t["text"])[:200_000], src_ref=f"old:{chat.sutra_id}:{t['index']}", at=at), ctx=tx.ctx))
                    result["messages_added"] += 1 if posted is not None else 0
                if t["tools"] and t["role"] == "assistant":
                    posted = store.post(tx, sid, GATE.check("chat_message", ChatMessage(
                        kind="note", session_id=sid, role="agent", who=WHO, text=_note_text(t["tools"]), src_ref=f"old:{chat.sutra_id}:{t['index']}:tools", at=at),
                        ctx=tx.ctx))
                    result["messages_added"] += 1 if posted is not None else 0
    result["scrubbed"] = dict(result["scrubbed"])
    return result


def cmd_import(args: argparse.Namespace) -> int:
    source = (args.source or default_source()).expanduser()
    if not source.is_dir():
        print(f"sutra-pro: there is no folder {source} (pass --source)", file=sys.stderr)
        return 1
    chats, bad = read_chats(source)
    p = plan(chats, bad)
    lines = [f"Old chats in {source}: {p.chats} ({p.non_empty} with messages), {p.messages} messages.",
             f"Would be flattened: {p.notes} turn(s) of tool calls become one note each (names and counts only); {p.thinking_dropped} thinking block(s) are dropped."]
    if p.providers:
        lines.append("Last provider of each chat: " + ", ".join(f"{name} {n}" for name, n in sorted(p.providers.items())) + ". Only claude and codex are kept; others are history only.")
    if bad:
        lines.append(f"Could not read {len(bad)} file(s): {', '.join(bad[:5])}{' ...' if len(bad) > 5 else ''}.")
    lines.append("Not imported: " + "; ".join(NOT_IMPORTED) + ".")
    payload: dict[str, Any] = {"source": str(source), "chats": p.chats, "non_empty": p.non_empty, "messages": p.messages, "notes": p.notes,
                               "thinking_dropped": p.thinking_dropped, "unreadable": bad, "applied": False}
    if not args.apply:
        lines.append("Dry run: nothing was written. Add --apply to import (a backup is taken first).")
        cli.emit(args, payload, lines)
        return 0
    settings = cli.load_settings(args)
    if settings is None:
        return 2
    held = None
    if settings.data_dir.exists():
        held = lock.InstanceLock(settings.data_dir)
        if not held.acquire():
            print(f"sutra-pro: Sutra Pro is running on {settings.data_dir}; stop it first (`sutra-pro stop`). Nothing was changed", file=sys.stderr)
            return 1
    try:
        from sutra_app.ops import backup
        if settings.db_path.exists():
            made = backup.create_backup(settings)
            lines.append(f"Backup written first: {made.path}")
            payload["backup"] = str(made.path)
        db = Database(settings.db_path, lambda events: None)
        try:
            db.migrate()
            done = import_chats(db, chats, Redactor(default_env_file()))
        finally:
            db.close()
    finally:
        if held is not None:
            held.release()
    payload.update(applied=True, **done)
    lines.append(f"Imported {done['chats_added']} chat(s) ({done['chats_present']} already there), {done['messages_added']} message(s) added.")
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
