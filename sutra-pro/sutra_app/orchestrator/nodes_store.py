"""The rows of the multi-agent nodes work that this package owns: the audit and the approvals (guardrails 5 and 8; D270, D280).

    store = NodeStore(db, ids=ids, redact=redactor)
    with db.tx() as tx:
        store.audit(tx, actor="gatekeeper", action="grant.issued", project_id=..., node_id=..., role="worker", tier=2, decision="allow", reason="role table")
        approval = store.open_approval(tx, project_id=..., node_id=..., tier=4, request={"why": "read GitHub"}, expires_at=tx.now() + 86400, client_id="c1")
        store.decide(tx, approval.id, "allow_project", decided_by="owner")

The audit is `node_audit`, append only (the table's triggers refuse an UPDATE and a DELETE). A row is names, shapes, counts and hashes, never a payload: `audit` has a fixed list of
keyword arguments and no place for a body, a prompt or file contents, so a caller cannot pass one by accident. Text parts (`target`, `reason`, `ref`) are put through the app's
secret redactor and the credential shape scan FIRST and clipped to 200 characters AFTER (so a secret is never cut in half and left), and lose their line breaks. `action` is a
dotted name like `grant.issued` or `kill`; `hash` is a sha256 or empty; the tier is 0 to 6 or none (a refusal of tier 6 is recorded, never a grant of it).

Approvals are rows of `approvals`: who is asked what, the answer, who answered, when it expires. Tier 6 is never asked, so `open_approval` refuses it; "allow for this project" is only
for tiers up to 4 (tier 5 is a question per raise, D270); an answer given twice is stored once (`client_id`, and a repeat of the same decision is a no-op); a different answer to a
question that was answered is `AlreadyDecided`. An open approval ends after `expires_at` as `expired`, which means denied. Nothing here is wired to a route or a card yet.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sutra_app.connectors.egress import scrubbed
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.grants import Grant, GrantError
from sutra_app.orchestrator.ids import IdFactory, iso_z
from sutra_app.orchestrator.models import NodeBlock

__all__ = [
    "NodeStore", "ApprovalRow", "PostedMessage", "MESSAGE_KINDS", "MESSAGE_BODY_MAX", "ApprovalExpired", "NodeBlockError", "node_block_of", "is_node_task", "HELD_WHILE_OFF", "held_while_off", "has_waiting_node_tasks", "GATE_REFUSED_SLEEP", "GATE_REFUSED_CLOSED", "GATE_REFUSED_ACTION", "PROJECT_STOPPED_ACTION", "AUDIT_ACTORS", "AUDIT_DECISIONS", "APPROVAL_DECISIONS", "REASON_MAX", "REQUEST_KEYS_MAX", "DECIDERS", "PROJECT_ALLOWED_TIERS",
]

# D296 (a closed laptop is a refusal), designed now and built in MAN-7 and MAN-8: the words a node is cancelled with, and the audit actions, so that every package uses the same ones.
GATE_REFUSED_SLEEP = "the computer went to sleep before you answered"
GATE_REFUSED_CLOSED = "Sutra was closed before you answered"
GATE_REFUSED_ACTION = "gate.refused"          # one row per open gate of the project, reason = one of the two sentences above, decision = deny, actor = system
PROJECT_STOPPED_ACTION = "project.stopped"    # one row when the project is stopped because of it
AUDIT_ACTORS = ("conductor", "gatekeeper", "node", "owner", "system")
AUDIT_DECISIONS = ("allow", "deny", "ask", "asked_allow", "asked_deny", "n/a")
APPROVAL_DECISIONS = {"allow_once": "allowed_once", "allow_project": "allowed_project", "deny": "denied"}      # the owner's words and the status each one stores
PROJECT_ALLOWED_TIERS = (0, 1, 2, 3, 4)            # "allow for this project" stops at tier 4 (tier 5 is asked per raise, tier 6 is not offered)
REASON_MAX = 200
REQUEST_KEYS_MAX = 20
_TEXT_MAX = 200
_ACTION = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
_HASH = re.compile(r"^([0-9a-f]{64})?$")
_ROLE = re.compile(r"^(planner|worker|reviewer|conductor|gatekeeper|)$")
_PROJECT_ID = re.compile(r"^prj_[0-9a-f]{12}$")
_NODE_ID = re.compile(r"^nd_[0-9a-f]{12}$")
DECIDERS = re.compile(r"^(owner|system|rule:[a-z][a-z0-9_]{0,40})$")      # who answered: the owner, the clock (expiry), or a named rule of the Gatekeeper's table (D294)


class ApprovalExpired(AppError):
    """A question that ran out was answered: it stays expired (which counts as denied). The words say so, so it is not read as "somebody else answered first"."""

    def __init__(self) -> None:
        super().__init__("already_decided", "That question ran out of time, so it counts as refused. Ask again to start over")


class NodeBlockError(ValueError):
    """A task has a node row that cannot be turned into the `node` block of its `task.json` (no usable grant, a role that has no process). Ids only, never text a node wrote."""


def node_block_of(conn: sqlite3.Connection, task_id: str) -> NodeBlock | None:
    """The `node` block of `task.json` for the task `task_id`, from its `agent_nodes` row and the grant frozen on it (D283); None when the task is not a node. Raises NodeBlockError
    when it is a node that has no usable grant: a node never runs without one (the task gate of MAN-5 refuses to start it)."""
    row = conn.execute("SELECT id, project_id, role, runtime, attempt, grants_json FROM agent_nodes WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    try:
        grant = Grant.from_json(json.loads(row["grants_json"] or "{}"))
        if grant.role != row["role"] or not grant.id or grant.node_id != row["id"]:
            raise NodeBlockError("the grant does not belong to this node (its role or its id), or has no id")
        return NodeBlock(id=row["id"], project_id=row["project_id"], role=row["role"], runtime=row["runtime"], attempt=int(row["attempt"]), grants_id=grant.id,
                         caps=grant.caps, scope=list(grant.scope), tool_profile=grant.tool_profile, tiers=list(grant.tiers), commands=grant.commands)
    except (GrantError, ValueError, TypeError) as exc:
        if isinstance(exc, NodeBlockError):
            raise
        raise NodeBlockError("the node has no usable grant") from None


def is_node_task(conn: sqlite3.Connection, task_id: str) -> bool:
    """True when the task is, or ever was, the task of a node of a project: the node's current task, or an earlier attempt of it (its `parent_task_id` chain). A step is tried again by its project (the
    Conductor's one retry, the fresh attempt after a close), never by hand: a task made by hand has no node, so no grant, no narrowing, no scope and no dollar limit (D398)."""
    return conn.execute("WITH RECURSIVE chain(id) AS (SELECT task_id FROM agent_nodes WHERE task_id IS NOT NULL UNION SELECT t.parent_task_id FROM tasks t JOIN chain c ON t.id = c.id "
                        "WHERE t.parent_task_id IS NOT NULL) SELECT 1 FROM chain WHERE id = ? LIMIT 1", (task_id,)).fetchone() is not None


HELD_WHILE_OFF = "On hold: this step is part of a project, and projects are switched off. Switch them on again, or stop this step"


def held_while_off(conn: sqlite3.Connection, now: int, row: Any) -> str:
    """`TaskService.task_gate` for an app that starts with SUTRA_NODES_V1 off while the database still holds the node tasks of an earlier run with it on (D313): a task that is a node never starts
    as an ordinary task (it would have the reach of a whole team run, wider than its grant); it waits with a plain note, and the owner can stop it. Any other task: "" (never held)."""
    return HELD_WHILE_OFF if conn.execute("SELECT 1 FROM agent_nodes WHERE task_id = ?", (row.id,)).fetchone() is not None else ""


def has_waiting_node_tasks(conn: sqlite3.Connection) -> bool:
    """True when some node's task has not started yet (blocked or queued): the one case where the flag-off app needs the gate above. False for an app that never used projects."""
    return conn.execute("SELECT 1 FROM agent_nodes n JOIN tasks t ON t.id = n.task_id WHERE t.status IN ('blocked','queued') LIMIT 1").fetchone() is not None


MESSAGE_KINDS = ("handoff", "verdict", "gate_request", "gate_decision", "control", "status")
MESSAGE_BODY_MAX = 16 * 1024                       # a body over this is stored as a reference to a file with its sha256 (architecture 4.1)


@dataclass(frozen=True)
class PostedMessage:
    """One row of `node_messages`. `duplicate` is True when this call found the message that was there already."""

    project_id: str
    seq: int
    from_node: str
    to_node: str
    kind: str
    src_ref: str
    body: str
    body_sha256: str
    at: int
    duplicate: bool = False

    def as_dict(self) -> dict[str, Any]:
        """The wire shape (`node-message/1`): the body as JSON when it is JSON, else as text."""
        try:
            body: Any = json.loads(self.body)
        except ValueError:
            body = self.body
        return {"v": 1, "project_id": self.project_id, "seq": self.seq, "at": iso_z(self.at), "from": {"node_id": self.from_node}, "to": {"node_id": self.to_node}, "kind": self.kind,
                "src_ref": self.src_ref, "body": body, "body_sha256": self.body_sha256}


@dataclass(frozen=True)
class ApprovalRow:
    """One question to the owner at a gate, as stored."""

    id: str
    project_id: str
    node_id: str
    tier: int
    request: Mapping[str, Any]
    status: str                  # open, allowed_once, allowed_project, denied, expired
    decided_by: str
    decided_at: int | None
    expires_at: int
    client_id: str | None
    created_at: int
    duplicate: bool = False      # True when this call found the row that was there already (the same client_id, or the same answer again)

    @property
    def open(self) -> bool:
        return self.status == "open"

    @property
    def allowed(self) -> bool:
        return self.status in ("allowed_once", "allowed_project")


class NodeStore:
    """Audit and approvals. Synchronous, like every store: async code calls it through `run_blocking`. Every write takes the caller's open transaction (`db.tx()`), so it commits
    or rolls back with the rest of the caller's work."""

    def __init__(self, db: Database, *, ids: IdFactory | None = None, redact: Callable[[str], str] | None = None) -> None:
        self.db = db
        self.ids = ids or IdFactory()
        self.redact = redact

    # ---- the audit -------------------------------------------------------------------------------------------------------------

    def audit(self, tx: Tx, *, actor: str, action: str, project_id: str | None = None, node_id: str | None = None, role: str = "", tier: int | None = None,
              target: str = "", decision: str = "n/a", reason: str = "", ref: str = "", hash: str = "") -> int:  # noqa: A002  (the column is called hash)
        """Append one row and return its `seq`. Raises ValueError for a name outside the closed lists; clips and scrubs the text parts (see the module text)."""
        if actor not in AUDIT_ACTORS:
            raise ValueError(f"an audit actor is one of {', '.join(AUDIT_ACTORS)}")
        if decision not in AUDIT_DECISIONS:
            raise ValueError(f"an audit decision is one of {', '.join(AUDIT_DECISIONS)}")
        if not isinstance(action, str) or len(action) > 80 or not _ACTION.fullmatch(action):
            raise ValueError("an audit action is a dotted name like grant.issued")
        if tier is not None and (isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 6):
            raise ValueError("an audit tier is 0 to 6, or none")
        if not isinstance(hash, str) or not _HASH.fullmatch(hash):
            raise ValueError("an audit hash is a sha256 in hex, or empty")
        if not isinstance(role, str) or not _ROLE.fullmatch(role):
            raise ValueError("an audit role is planner, worker, reviewer, conductor, gatekeeper or empty")
        if project_id is not None and not (isinstance(project_id, str) and _PROJECT_ID.fullmatch(project_id)):
            raise ValueError("an audit project is a prj_ id, or none")
        if node_id is not None and not (isinstance(node_id, str) and _NODE_ID.fullmatch(node_id)):
            raise ValueError("an audit node is an nd_ id, or none")
        cursor = tx.conn.execute(
            "INSERT INTO node_audit(at, project_id, node_id, role, actor, action, tier, target, decision, reason, ref, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",         # never INSERT OR REPLACE on an append-only table: a replace deletes the old row without a trigger (m1)
            (tx.now(), project_id, node_id, role, actor, action, tier, self._text(target), decision, self._text(reason), self._text(ref), hash))
        return int(cursor.lastrowid)

    # ---- messages (D264, D297) --------------------------------------------------------------------------------------------------

    def post(self, tx: Tx, *, project_id: str, kind: str, src_ref: str, body: Any, from_node: str = "", to_node: str = "", file: str | None = None) -> PostedMessage:
        """Store one message of a project and return it with its `seq` (D297). ALL of this happens in the caller's one write transaction: look for `(project_id, src_ref)` first and, if the
        message is there, return that row and take no number (a repeat is stored once, `duplicate=True`); else take `MAX(seq) + 1` for the project and insert. So at every committed state the
        `seq` values of one project are exactly 1 to n: the key forbids a repeat, the server is the only writer and a write is `BEGIN IMMEDIATE`, the number is taken and used in the same
        transaction (a rollback gives it back), a repeated source takes none, the triggers forbid update and delete, and the event is published after COMMIT. The body (JSON text, or
        anything JSON-able) has every string scrubbed of the app's secrets and the credential shapes first; a body over 16 KB is stored as a reference `{file, sha256, bytes}` to `file` (the
        caller's file of the full text). `kind` is one of the table's; the insert is `ON CONFLICT DO NOTHING`, never a replace."""
        if kind not in MESSAGE_KINDS:
            raise ValueError("a message kind is " + ", ".join(MESSAGE_KINDS))
        if not isinstance(src_ref, str) or not 1 <= len(src_ref) <= 200:
            raise ValueError("a message has a source reference of 1 to 200 characters")
        found = tx.conn.execute("SELECT * FROM node_messages WHERE project_id = ? AND src_ref = ?", (project_id, src_ref)).fetchone()
        if found is not None:
            return self._message(found, duplicate=True)
        text = body if isinstance(body, str) else json.dumps(self._scrub_json(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        text = scrubbed(text, self.redact)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        raw = text.encode("utf-8")
        if len(raw) > MESSAGE_BODY_MAX:
            text = json.dumps({"file": file or "", "sha256": digest, "bytes": len(raw)}, separators=(",", ":"))
        seq = int(tx.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM node_messages WHERE project_id = ?", (project_id,)).fetchone()[0])
        cursor = tx.conn.execute(
            "INSERT INTO node_messages(project_id, seq, from_node, to_node, kind, src_ref, body, body_sha256, at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (project_id, seq, from_node, to_node, kind, src_ref, text, digest, tx.now()))
        if cursor.rowcount == 0:                                   # cannot happen inside one write transaction; if it ever does, it is the same message: return it
            return self._message(tx.conn.execute("SELECT * FROM node_messages WHERE project_id = ? AND src_ref = ?", (project_id, src_ref)).fetchone(), duplicate=True)
        tx.emit("project.message", {"project_id": project_id, "seq": seq, "kind": kind})
        return self._message(tx.conn.execute("SELECT * FROM node_messages WHERE project_id = ? AND seq = ?", (project_id, seq)).fetchone())

    def messages(self, project_id: str, *, after: int = 0, limit: int = 100) -> list[PostedMessage]:
        """The messages of a project after `after`, in `seq` order (1 to 500 of them): what the page's catch-up reads. The first one is `after + 1` unless a message was lost."""
        found = self.db.conn().execute("SELECT * FROM node_messages WHERE project_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                                       (project_id, max(0, int(after)), max(1, min(int(limit), 500)))).fetchall()
        return [self._message(row) for row in found]

    def last_seq(self, project_id: str) -> int:
        return int(self.db.conn().execute("SELECT COALESCE(MAX(seq), 0) FROM node_messages WHERE project_id = ?", (project_id,)).fetchone()[0])

    def _scrub_json(self, value: Any) -> Any:
        """The value with every string (and key) scrubbed, on the data before it is written as JSON, so a secret that JSON would escape is still found."""
        if isinstance(value, str):
            return scrubbed(value, self.redact)
        if isinstance(value, Mapping):
            return {(scrubbed(k, self.redact) if isinstance(k, str) else k): self._scrub_json(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._scrub_json(v) for v in value]
        return value

    @staticmethod
    def _message(row: sqlite3.Row, *, duplicate: bool = False) -> "PostedMessage":
        return PostedMessage(project_id=row["project_id"], seq=int(row["seq"]), from_node=row["from_node"], to_node=row["to_node"], kind=row["kind"], src_ref=row["src_ref"],
                             body=row["body"], body_sha256=row["body_sha256"], at=int(row["at"]), duplicate=duplicate)

    def clean(self, text: str) -> str:
        """One line of at most 200 characters with the app's secrets and the credential shapes replaced: what an audit text becomes (a few words for a file or a card use it too)."""
        return self._text(text)

    def mark_ended(self, tx: Tx, node_id: str, state: str, why: str) -> bool:
        """Put a node that has not ended into a final state (`cancelled`, `failed` or `done`) with a reason of at most 200 characters, and stamp when. False, changing nothing, when the node
        does not exist or is final already. (The projector's full state machine arrives with the projects, MAN-5; this is the one move the owner's stop needs.)"""
        if state not in ("done", "failed", "cancelled"):
            raise ValueError("a node ends as done, failed or cancelled")
        cursor = tx.conn.execute("UPDATE agent_nodes SET state = ?, failure_reason = ?, ended_at = ? WHERE id = ? AND state NOT IN ('done','failed','cancelled')",
                                 (state, self._text(why), tx.now(), node_id))
        return cursor.rowcount > 0

    def audit_rows(self, *, project_id: str | None = None, node_id: str | None = None, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        """The rows in `seq` order, those above `after`, at most `limit` (1 to 500). Times are ISO text."""
        where, args = ["seq > ?"], [max(0, int(after))]
        for column, value in (("project_id", project_id), ("node_id", node_id)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        found = self.db.conn().execute(
            "SELECT seq, at, project_id, node_id, role, actor, action, tier, target, decision, reason, ref, hash FROM node_audit WHERE " + " AND ".join(where)
            + " ORDER BY seq LIMIT ?", (*args, max(1, min(int(limit), 500)))).fetchall()
        return [{**{key: row[key] for key in row.keys() if key != "at"}, "at": iso_z(row["at"])} for row in found]

    def _text(self, text: str) -> str:
        """One line of at most 200 characters: the app's secrets and the credential shapes replaced first, then the white space collapsed, then clipped."""
        if not isinstance(text, str):
            raise ValueError("an audit text is text")
        cleaned = " ".join(scrubbed(text, self.redact).split())
        return cleaned[:_TEXT_MAX]

    # ---- approvals -------------------------------------------------------------------------------------------------------------

    def open_approval(self, tx: Tx, *, project_id: str, node_id: str, tier: int, request: Mapping[str, Any], expires_at: int, client_id: str | None = None) -> ApprovalRow:
        """Ask the owner one question. Tier 6 is never asked (ValueError). A repeated `client_id` in a project returns the row that is there (`duplicate=True`). The request is a small
        object of names and short text (at most 20 keys); its text is scrubbed and clipped like an audit reason."""
        if isinstance(tier, bool) or not isinstance(tier, int) or not 1 <= tier <= 5:
            raise ValueError("a gate asks about tiers 1 to 5: tier 6 is never offered")
        if client_id is not None:
            seen = tx.conn.execute("SELECT * FROM approvals WHERE project_id = ? AND client_id = ?", (project_id, client_id)).fetchone()
            if seen is not None:
                return self._row(seen, duplicate=True)
        approval_id = self.ids.approval_id()
        tx.conn.execute(
            "INSERT INTO approvals(id, project_id, node_id, tier, request_json, status, expires_at, client_id, created_at) VALUES (?,?,?,?,?,'open',?,?,?)",
            (approval_id, project_id, node_id, tier, self._request_json(request), int(expires_at), client_id, tx.now()))
        return self._row(tx.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())

    def decide(self, tx: Tx, approval_id: str, decision: str, *, decided_by: str) -> ApprovalRow:
        """Record the answer: `allow_once`, `allow_project` or `deny`, by `owner`, a named rule (`rule:decide_for_me`) or `system`. The first answer wins: the same answer again returns
        the row with `duplicate=True`; a different one raises `AlreadyDecided`. `allow_project` is refused above tier 4, and an allow of tier 5 or 6 is only ever `allow_once` for 5
        (6 can not be allowed at all). An approval that ran out (`expires_at` passed) is stored `expired`, which means denied, whatever the decision says."""
        if decision not in APPROVAL_DECISIONS:
            raise AppError("validation", "The answer is allow_once, allow_project or deny")
        if not isinstance(decided_by, str) or not DECIDERS.fullmatch(decided_by):
            raise ValueError("an approval is answered by owner, system or a named rule")
        row = tx.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise NotFound("that approval")
        status = APPROVAL_DECISIONS[decision]
        if row["status"] == "expired":                          # expired stays expired (it counts as denied): any answer to it is refused, in words that say so, never as a repeat (m5)
            raise ApprovalExpired()
        if row["status"] != "open":
            if row["status"] == status:
                return self._row(row, duplicate=True)
            raise AlreadyDecided(self._row(row, duplicate=True))
        if decided_by.startswith("rule:"):                      # a rule of the Gatekeeper's table answers only for a project that asked for it (D294): the check is here, in the one place every answer goes through (m4)
            on = tx.conn.execute("SELECT decide_for_me FROM projects WHERE id = ?", (row["project_id"],)).fetchone()
            if on is None or int(on["decide_for_me"]) != 1:
                raise AppError("validation", "A rule can answer only when Decide for me is on for the project")
        tier = int(row["tier"])
        if status != "denied" and tier == 6:
            raise AppError("validation", "Tier 6 can not be allowed")
        if status == "allowed_project" and tier not in PROJECT_ALLOWED_TIERS:
            raise AppError("validation", "That can only be allowed once, for this question")
        if status != "denied" and tx.now() >= int(row["expires_at"]):
            status, decided_by = "expired", "system"            # too late: an answer that arrives after the expiry does not count (expired means denied)
        tx.conn.execute("UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE id = ? AND status = 'open'", (status, decided_by, tx.now(), approval_id))
        return self._row(tx.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())

    def expire_due(self, tx: Tx, *, project_id: str | None = None, now: int | None = None) -> list[ApprovalRow]:
        """Every open approval whose time has run out becomes `expired` (denied, decided by `system`). Returns the rows it changed. `now` is the caller's moment (the tick's); default the clock's."""
        now = tx.now() if now is None else int(now)
        found = tx.conn.execute("SELECT id FROM approvals WHERE status = 'open' AND expires_at <= ?" + (" AND project_id = ?" if project_id else "") + " ORDER BY created_at, id",
                                (now, project_id) if project_id else (now,)).fetchall()
        changed = []
        for row in found:
            tx.conn.execute("UPDATE approvals SET status = 'expired', decided_by = 'system', decided_at = ? WHERE id = ? AND status = 'open'", (now, row["id"]))
            changed.append(self._row(tx.conn.execute("SELECT * FROM approvals WHERE id = ?", (row["id"],)).fetchone()))
        return changed

    def get_approval(self, approval_id: str) -> ApprovalRow | None:
        row = self.db.conn().execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return None if row is None else self._row(row)

    def approvals(self, project_id: str, *, status: str | None = None) -> list[ApprovalRow]:
        """The approvals of a project, oldest first; `status` limits them (for example `open`)."""
        args: list[Any] = [project_id]
        sql = "SELECT * FROM approvals WHERE project_id = ?"
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        return [self._row(row) for row in self.db.conn().execute(sql + " ORDER BY created_at, id", args).fetchall()]

    # ---- helpers ---------------------------------------------------------------------------------------------------------------

    def _request_json(self, request: Mapping[str, Any]) -> str:
        """The request as compact JSON: at most 20 keys, each value a short text, a whole number, a bool or a short list of texts. Anything else is a ValueError."""
        if not isinstance(request, Mapping) or len(request) > REQUEST_KEYS_MAX:
            raise ValueError(f"an approval request is an object of at most {REQUEST_KEYS_MAX} keys")
        clean: dict[str, Any] = {}
        for key, value in request.items():
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key):
                raise ValueError("an approval request key is a short lower-case name")
            if isinstance(value, bool) or isinstance(value, int):
                clean[key] = value
            elif isinstance(value, str):
                clean[key] = self._text(value)
            elif isinstance(value, (list, tuple)) and len(value) <= 20 and all(isinstance(item, str) for item in value):
                clean[key] = [self._text(item) for item in value]
            else:
                raise ValueError("an approval request holds text, whole numbers, true or false, or a short list of text")
        return json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _row(row: sqlite3.Row, *, duplicate: bool = False) -> ApprovalRow:
        return ApprovalRow(id=row["id"], project_id=row["project_id"], node_id=row["node_id"], tier=int(row["tier"]), request=json.loads(row["request_json"] or "{}"),
                           status=row["status"], decided_by=row["decided_by"], decided_at=row["decided_at"], expires_at=int(row["expires_at"]), client_id=row["client_id"],
                           created_at=int(row["created_at"]), duplicate=duplicate)
