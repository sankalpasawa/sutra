"""Chat sessions and messages (orchestrator 3.4, 4.1, 6.2; S1-contracts-08, S2-models-11, S4-fnodes-06).

    chats = ChatStore(db)
    chats.post(tx, "cs_org", checked_message)       # ChatMessageOut, or None when its `src_ref` is stored already
    chats.messages("cs_a1", after=0, limit=200)     # oldest first; a division session shows its own notes plus the department lines of its tasks
    chats.mark_answered(tx, question_id, by_id)     # a question is answered once; a second call changes nothing
    chats.needs_you()                               # open department questions and pending approval cards
    chats.set_provider(sid, "claude", "sonnet", "provider-session")    # the connector router's `session_hook`; opens its own transaction
    chats.note_provider(tx, sid, "claude", "sonnet")                   # connector and model only (UsageStore.record calls it)
    chats.apply_links(tx, plan, names)              # executes the library's `carry_links` plan after a merge
    ChatTranscripts(chats).messages(sid, 20)        # the router's `TranscriptSource`

One session per node; `chat_sessions` rows are made by `ensure_node` (ORCH-5), never here. Messages are written only through
`post`, from a message the gate has checked (`Checked[ChatMessage]`). This store emits `chat.message` for every stored message
and `needs_you.changed` whenever the number of open questions and pending approvals can have changed; the Projector and the
chart store need not emit it.
"""
import json
import logging
import re
import sqlite3
from collections.abc import Mapping, Sequence

from sutra_app.connectors.models import Message
from sutra_app.library.gate import GATE, Checked
from sutra_app.library.org_chart import LinkPlan
from sutra_app.orchestrator.chat_v2 import ChatSegments
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.ids import iso_z
from sutra_app.orchestrator.models import ChatMessageOut, ChatSessionOut, NeedsYouOut, ResumeInfo
from sutra_app.orchestrator.records import ChatMessage, ChatSession
from sutra_app.orchestrator.waiting import ask_state

__all__ = ["ChatStore", "ChatTranscripts", "RESUME_MESSAGES", "TURN_PHASES", "PROVIDERS", "parse_options"]

log = logging.getLogger(__name__)
RESUME_MESSAGES = 20
MAX_LIMIT = 500
TURN_PHASES = ("reading", "planning", "building")
PROVIDERS = ("claude", "codex", "stub", "")
_MESSAGE_COLUMNS = "id, session_id, role, who, kind, text, card_json, meta_json, pause, answered_by, task_id, src_ref, state, at"
_SESSION_COLUMNS = ("id, node_id, kind, title, writable, status, filed_under, connector, model, provider_session_id, "
                    "last_message_id, note, created_at, updated_at, pinned")
_OPEN_TASKS = ("blocked", "queued", "starting", "running", "waiting_user")
_OPTION_LINE = re.compile(r"^[ \t]*Option[ \t]+[0-9]+:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_TRANSCRIPT_ROLES = {"user": "user", "agent": "assistant", "system": "system"}


def parse_options(text: str) -> list[str]:
    """The answer options in a question's text: the `Option N: ...` lines J2 writes (`j2.numbered`), in order, at most 20,
    each cut to 500 characters."""
    return [found[:500] for found in _OPTION_LINE.findall(text)][:20]


def _session_out(row: sqlite3.Row, phase: str | None = None) -> ChatSessionOut:
    return ChatSessionOut(
        id=row["id"], node_id=row["node_id"], kind=row["kind"], title=row["title"], writable=bool(row["writable"]), status=row["status"],
        filed_under=row["filed_under"], connector=row["connector"], model=row["model"], provider_session_id=row["provider_session_id"],
        last_message_id=row["last_message_id"], note=row["note"], phase=phase)


def _session_record(row: sqlite3.Row) -> ChatSession:
    return ChatSession(
        kind=row["kind"], id=row["id"], node_id=row["node_id"], title=row["title"], writable=bool(row["writable"]), status=row["status"],
        filed_under=row["filed_under"], connector=row["connector"], model=row["model"], provider_session_id=row["provider_session_id"],
        last_message_id=row["last_message_id"], note=row["note"], created_at=row["created_at"], updated_at=row["updated_at"],
        pinned=row["pinned"])


def _message_out(row: sqlite3.Row) -> ChatMessageOut:
    return ChatMessageOut(
        id=row["id"], session_id=row["session_id"], role=row["role"], who=row["who"], kind=row["kind"], text=row["text"],
        card=json.loads(row["card_json"]) if row["card_json"] else None, pause=row["pause"], answered_by=row["answered_by"],
        task_id=row["task_id"], state=row["state"], at=iso_z(row["at"]), blocks=_blocks_of(row["meta_json"]),
        turn=_turn_of(row["src_ref"]))


def _turn_of(src_ref: str | None) -> int | None:
    """The owner's line a direct-chat reply answers (`src_ref` is `direct:<message id>`, or `direct-note:`, `direct-error:`, `direct-switch:`
    for the other messages that end the same turn: orchestrator/direct_turns.py), else None."""
    found = re.fullmatch(r"direct(?:-(?:note|error|switch))?:([1-9][0-9]{0,15})", src_ref or "")
    return int(found.group(1)) if found else None


def _blocks_of(meta_json: str | None) -> list[dict]:
    try:
        found = json.loads(meta_json or "{}").get("blocks", [])
    except ValueError:
        return []
    return found if isinstance(found, list) else []


def _clamp(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


class ChatStore:
    """Sessions and messages. Reads use this thread's connection; writes take the `Tx` of the caller (except `set_provider`,
    which is the router's hook and opens its own)."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._turn_phase: str | None = None

    # ---- sessions --------------------------------------------------------------------------------------------------

    def sessions(self, *, node_id: str | None = None, include_archived: bool = False, limit: int = MAX_LIMIT) -> list[ChatSessionOut]:
        """The sessions in creation order. Only the active ones unless `include_archived`; `node_id` limits to one node (for
        a merged-away division its archived session is listed under the node it was filed under as well as under its own)."""
        where, args = [], []
        if node_id is not None:
            where.append("(node_id = ? OR filed_under = ?)")
            args += [node_id, node_id]
        if not include_archived:
            where.append("status = 'active'")
        sql = f"SELECT {_SESSION_COLUMNS} FROM chat_sessions" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY created_at, rowid LIMIT ?"
        rows = self.db.conn().execute(sql, (*args, _clamp(limit))).fetchall()
        return [_session_out(r, self.phase(r["id"])) for r in rows]

    def session(self, session_id: str) -> ChatSessionOut:
        row = self.db.conn().execute(f"SELECT {_SESSION_COLUMNS} FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFound("that chat")
        return _session_out(row, self.phase(session_id))

    def phase(self, session_id: str) -> str | None:
        """The org chat's progress word: `reading`, `planning` or `building` while a turn is in that part (set by the turn
        runner), else `working` while any task is not finished, else `ready`. Every other session has none."""
        if session_id != "cs_org":
            return None
        if self._turn_phase is not None:
            return self._turn_phase
        marks = ",".join("?" * len(_OPEN_TASKS))
        busy = self.db.conn().execute(f"SELECT 1 FROM tasks WHERE status IN ({marks}) LIMIT 1", _OPEN_TASKS).fetchone()
        return "working" if busy is not None else "ready"

    def set_turn_phase(self, phase: str | None) -> None:
        """The turn runner says which part of a request it is in (None when no turn runs). Kept in memory only."""
        if phase is not None and phase not in TURN_PHASES:
            raise ValueError(f"a turn phase is one of {', '.join(TURN_PHASES)}, not {phase!r}")
        self._turn_phase = phase

    # ---- messages --------------------------------------------------------------------------------------------------

    def messages(self, session_id: str, *, after: int = 0, limit: int = 200) -> list[ChatMessageOut]:
        """Messages with an id above `after`, oldest first. A division session is a lens: its own notes plus the lines the
        department session holds for the tasks scoped to that division (by `tasks.scope_node_id`, so a division that moved
        or was merged away keeps showing them). The lines keep the department session's id in `session_id`."""
        conn = self.db.conn()
        session = conn.execute("SELECT id, kind, node_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if session is None:
            raise NotFound("that chat")
        if session["kind"] == "division":
            rows = conn.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM chat_messages WHERE id > ? AND (session_id = ? OR (task_id IN"
                " (SELECT id FROM tasks WHERE scope_node_id = ?) AND session_id IN (SELECT id FROM chat_sessions WHERE kind = 'department')))"
                " ORDER BY id LIMIT ?", (int(after), session_id, session["node_id"], _clamp(limit))).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_MESSAGE_COLUMNS} FROM chat_messages WHERE session_id = ? AND id > ? ORDER BY id LIMIT ?",
                (session_id, int(after), _clamp(limit))).fetchall()
        return [_message_out(r) for r in rows]

    def message(self, message_id: int) -> ChatMessageOut | None:
        row = self.db.conn().execute(f"SELECT {_MESSAGE_COLUMNS} FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return _message_out(row) if row is not None else None

    def blocks(self, message_id: int) -> list[dict]:
        """The typed blocks stored with a message, in order (empty for a message without any)."""
        row = self.db.conn().execute("SELECT meta_json FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        return list(json.loads(row["meta_json"]).get("blocks", [])) if row is not None else []

    def last_messages(self, session_id: str, limit: int = RESUME_MESSAGES, *, kinds: Sequence[str] | None = None,
                      ok_only: bool = False) -> list[ChatMessageOut]:
        """The newest `limit` messages of one session (its own rows only), oldest first; `kinds` and `ok_only` filter first."""
        where, args = ["session_id = ?"], [session_id]
        if kinds is not None:
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            args += list(kinds)
        if ok_only:
            where.append("state = 'ok'")
        rows = self.db.conn().execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM chat_messages WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
            (*args, max(0, int(limit)))).fetchall()
        return [_message_out(r) for r in reversed(rows)]

    def post(self, tx: Tx, session_id: str, rec: Checked[ChatMessage]) -> ChatMessageOut | None:
        """Store a checked message in `session_id` and emit `chat.message`. Returns None, storing nothing, when a message with
        the same `src_ref` is already in the session (a replayed line). A question or an approval card also emits
        `needs_you.changed`."""
        if not isinstance(rec, Checked) or rec.family != "chat_message":
            raise TypeError("ChatStore.post takes a Checked chat_message from GATE.check")
        msg: ChatMessage = rec.model
        if msg.session_id != session_id:
            raise ValueError(f"the message belongs to session {msg.session_id}, not {session_id}")
        conn = tx.conn
        if conn.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)).fetchone() is None:
            raise NotFound("that chat")
        if msg.src_ref is not None and conn.execute(
                "SELECT 1 FROM chat_messages WHERE session_id = ? AND src_ref = ?", (session_id, msg.src_ref)).fetchone() is not None:
            return None
        card_json = json.dumps(msg.card, separators=(",", ":"), ensure_ascii=False, sort_keys=True) if msg.card is not None else None
        meta_json = msg.meta.model_dump_json()
        if msg.blocks:                              # typed provider blocks ride in meta_json (absorb D108); MessageMeta itself is J2's and unchanged
            meta_json = json.dumps({**json.loads(meta_json), "blocks": [b.model_dump(mode="json", exclude_defaults=True) for b in msg.blocks]},
                                   separators=(",", ":"), ensure_ascii=False)
        cursor = conn.execute(
            "INSERT INTO chat_messages(session_id, role, who, kind, text, card_json, meta_json, pause, answered_by, task_id, src_ref, state, at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, msg.role, msg.who, msg.kind, msg.text, card_json, meta_json, msg.pause, msg.answered_by, msg.task_id,
             msg.src_ref, msg.state, msg.at))
        message_id = int(cursor.lastrowid)
        conn.execute("UPDATE chat_sessions SET last_message_id = ?, updated_at = max(updated_at, ?) WHERE id = ?", (message_id, msg.at, session_id))
        out = self.message_in(conn, message_id)
        tx.emit("chat.message", {"session_id": session_id, "message": out.model_dump(mode="json")})
        if msg.kind == "question" or (msg.kind == "card" and (msg.card or {}).get("type") == "approval"):
            self.emit_needs_you(tx)
        return out

    @staticmethod
    def message_in(conn: sqlite3.Connection, message_id: int) -> ChatMessageOut:
        return _message_out(conn.execute(f"SELECT {_MESSAGE_COLUMNS} FROM chat_messages WHERE id = ?", (message_id,)).fetchone())

    def mark_answered(self, tx: Tx, question_id: int, by_message_id: int) -> None:
        """Say that message `by_message_id` answered the question `question_id`. A question is answered once: a second call
        (the same answer replayed, or another one) changes nothing. Emits `needs_you.changed` when it did change."""
        conn = tx.conn
        row = conn.execute("SELECT kind, answered_by FROM chat_messages WHERE id = ?", (question_id,)).fetchone()
        if row is None or row["kind"] != "question":
            raise ValueError(f"message {question_id} is not a question")
        if conn.execute("SELECT 1 FROM chat_messages WHERE id = ?", (by_message_id,)).fetchone() is None:
            raise ValueError(f"message {by_message_id} does not exist")
        if row["answered_by"] is not None:
            return
        conn.execute("UPDATE chat_messages SET answered_by = ? WHERE id = ?", (by_message_id, question_id))
        self.emit_needs_you(tx)

    # ---- needs you -------------------------------------------------------------------------------------------------

    def needs_you(self, *, now: int | None = None) -> list[NeedsYouOut]:
        """What waits for the owner, oldest first: every unanswered question in a department session (Identity's text,
        verbatim, with its `Option N:` lines as options) and every approval card whose chart change is still pending. With `now`
        (epoch seconds, the server's clock) each item also says how long it has waited and whether that is past 24 h (`stale`)."""
        conn = self.db.conn()
        out: list[NeedsYouOut] = []

        def age(at: int) -> dict:
            if now is None:
                return {}
            waited, stale = ask_state(at, now)
            return {"waiting_s": waited, "stale": stale}

        for r in conn.execute(
                "SELECT m.id, m.session_id, m.text, m.at, s.node_id, o.name FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id"
                " LEFT JOIN org_nodes o ON o.id = s.node_id WHERE m.kind = 'question' AND m.answered_by IS NULL AND s.kind = 'department'"
                " ORDER BY m.id"):
            out.append(NeedsYouOut(
                message_id=r["id"], session_id=r["session_id"], kind="question", dept_id=r["node_id"], dept_name=r["name"] or r["node_id"],
                text=r["text"], options=parse_options(r["text"]), asked_at=iso_z(r["at"]), **age(r["at"])))
        for r in conn.execute(
                "SELECT m.id, m.session_id, m.card_json, m.at FROM chat_messages m WHERE m.kind = 'card'"
                " AND json_extract(m.card_json, '$.type') = 'approval' AND json_extract(m.card_json, '$.change_id') IN"
                " (SELECT id FROM chart_changes WHERE status = 'pending_approval') ORDER BY m.id"):
            card = json.loads(r["card_json"])
            out.append(NeedsYouOut(
                message_id=r["id"], session_id=r["session_id"], kind="approval", text=card["question"],
                options=[o["label"] for o in card["options"]], asked_at=iso_z(r["at"]), **age(r["at"])))
        return sorted(out, key=lambda item: item.message_id)

    def needs_you_count(self) -> int:
        return self._count_in(self.db.conn())

    def emit_needs_you(self, tx: Tx) -> None:
        """Emit `needs_you.changed {count}` from inside a transaction (the count is read through that transaction)."""
        tx.emit("needs_you.changed", {"count": self._count_in(tx.conn)})

    @staticmethod
    def _count_in(conn: sqlite3.Connection) -> int:
        questions = conn.execute(
            "SELECT count(*) FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id"
            " WHERE m.kind = 'question' AND m.answered_by IS NULL AND s.kind = 'department'").fetchone()[0]
        approvals = conn.execute(
            "SELECT count(*) FROM chat_messages m WHERE m.kind = 'card' AND json_extract(m.card_json, '$.type') = 'approval'"
            " AND json_extract(m.card_json, '$.change_id') IN (SELECT id FROM chart_changes WHERE status = 'pending_approval')").fetchone()[0]
        return int(questions + approvals)

    # ---- the provider chip -----------------------------------------------------------------------------------------

    def set_provider(self, session_id: str, connector: str, model: str, provider_session_id: str | None) -> None:
        """The connector router's `session_hook`, called positionally as (session_id, provider, model, provider_session_id).
        Opens its own transaction. A session this store does not know is ignored (the router also runs for sessions of its
        own); a provider name outside claude, codex, stub is a ValueError."""
        if connector not in PROVIDERS:
            raise ValueError(f"a connector is one of claude, codex, stub or empty, not {connector!r}")
        with self.db.tx() as tx:
            row = tx.conn.execute(f"SELECT {_SESSION_COLUMNS} FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                log.debug("set_provider: no chat session %s", session_id)
                return
            self._update_provider(tx, row, connector=connector, model=model, provider_session_id=provider_session_id or None)
            ChatSegments.record(tx, session_id, connector, provider_session_id or None, row["last_message_id"])

    def note_provider(self, tx: Tx, session_id: str, connector: str, model: str) -> None:
        """Keep the session's chip current from a usage row: connector and model only, `provider_session_id` is never touched.
        An empty model leaves the stored model as it is. An unknown session is ignored."""
        if connector not in PROVIDERS:
            raise ValueError(f"a connector is one of claude, codex, stub or empty, not {connector!r}")
        row = tx.conn.execute(f"SELECT {_SESSION_COLUMNS} FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return
        self._update_provider(tx, row, connector=connector, model=model or row["model"], provider_session_id=row["provider_session_id"])

    def _update_provider(self, tx: Tx, row: sqlite3.Row, *, connector: str, model: str, provider_session_id: str | None) -> None:
        if (row["connector"], row["model"], row["provider_session_id"]) == (connector, model, provider_session_id):
            return
        checked = GATE.check("chat_session", _session_record(row).evolve(
            connector=connector, model=model, provider_session_id=provider_session_id, updated_at=max(row["updated_at"], tx.now())), ctx=tx.ctx)
        s: ChatSession = checked.model
        tx.conn.execute("UPDATE chat_sessions SET connector = ?, model = ?, provider_session_id = ?, updated_at = ? WHERE id = ?",
                        (s.connector, s.model, s.provider_session_id, s.updated_at, s.id))

    def resume_info(self, session_id: str) -> ResumeInfo:
        """Diagnostics: the session's provider, its provider session id and its last 20 messages."""
        out = self.session(session_id)
        return ResumeInfo(connector=out.connector, provider_session_id=out.provider_session_id,
                          messages=self.last_messages(session_id, RESUME_MESSAGES))

    # ---- merges ----------------------------------------------------------------------------------------------------

    def apply_links(self, tx: Tx, plan: LinkPlan, names: Mapping[str, str]) -> None:
        """Execute the library's `carry_links` plan for a merge. `keep`: nothing. `archive` (session -> survivor): the session
        becomes archived and read-only, its note says "Merged into <name>", `filed_under` is the survivor and `node_id` stays
        (a division's filtered view keeps working); sessions archived earlier under the node that was just merged away are
        re-filed under the survivor. `move` (session -> node): `node_id` is re-pointed. `names` maps node ids to names."""
        conn = tx.conn
        for session_id, target in plan.archive.items():
            row = self._need(conn, session_id)
            note = f"Merged into {names.get(target, target)}"[:500]
            checked = GATE.check("chat_session", _session_record(row).evolve(
                status="archived", writable=False, filed_under=target, note=note, updated_at=max(row["updated_at"], tx.now())), ctx=tx.ctx)
            s: ChatSession = checked.model
            conn.execute("UPDATE chat_sessions SET status = 'archived', writable = 0, note = ?, filed_under = ?, updated_at = ? WHERE id = ?",
                         (s.note, s.filed_under, s.updated_at, session_id))
            conn.execute("UPDATE chat_sessions SET filed_under = ? WHERE status = 'archived' AND filed_under = ? AND id != ?",
                         (target, row["node_id"], session_id))
        for session_id, target in plan.move.items():
            row = self._need(conn, session_id)
            checked = GATE.check("chat_session", _session_record(row).evolve(node_id=target, updated_at=max(row["updated_at"], tx.now())), ctx=tx.ctx)
            conn.execute("UPDATE chat_sessions SET node_id = ?, updated_at = ? WHERE id = ?", (target, checked.model.updated_at, session_id))

    @staticmethod
    def _need(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = conn.execute(f"SELECT {_SESSION_COLUMNS} FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise ValueError(f"the link plan names the chat session {session_id}, which does not exist")
        return row


class ChatTranscripts:
    """The connector router's `TranscriptSource`: the recent conversation of a session, so a new provider session can be
    primed. Only messages of kind text and question with state ok; role `agent` becomes `assistant`."""

    def __init__(self, chats: ChatStore) -> None:
        self._chats = chats

    def messages(self, session_id: str, limit: int = 20) -> list[Message]:
        found = self._chats.last_messages(session_id, limit, kinds=("text", "question"), ok_only=True)
        return [Message(role=_TRANSCRIPT_ROLES[m.role], text=m.text) for m in found]
