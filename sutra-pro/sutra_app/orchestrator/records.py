"""The orchestrator's stored records, registered in the library's `REGISTRY` (orchestrator 3.2, S2-models-15).

    chat_session   one chat per graph node (the columns of `chat_sessions`); its `kind` is the session kind
    chat_message   the stored server message (the columns of `chat_messages`); its `kind` is the message kind and its `meta` is
                   the library's `MessageMeta`. J2's own `chat.jsonl` line is the library's payload `run_message`.
    usage_record   one model request (the columns of `usage_ledger`)
    work_task      one run of one department (the columns of `tasks`)

A record is built, passed through `GATE.check(family, record, ctx=tx.ctx)` and stored from the returned `Checked`: the SQL
`CHECK`s are the second line. Importing this module registers the four families; import it before the registry is frozen.
`chat_message.id` and `chat_session` timestamps are the store's, so a message is checked before it has an id.
The chat agent's reply classes (`ChatDecision`, `AssignmentPlan`, `AssignmentDraft`) belong to the agent package (ORCH-7).
"""
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, TypeAdapter, ValidationError, model_validator

from sutra_app.engine.spec import DEPT_ID_RE
from sutra_app.library.base import Record
from sutra_app.library.chat import ChatBlock, MessageMeta
from sutra_app.library.node import GraphNodeId
from sutra_app.library.registry import record
from sutra_app.library.types import JsonObject, NodeId, Ts
from sutra_app.orchestrator.models import (
    LIVE_STATUSES, TERMINAL_STATUSES, ChatCard, RunId, SessionId, TaskId, TaskSettings, TaskStatus,
)

__all__ = ["ChatSession", "ChatMessage", "UsageRecord", "WorkTask", "RequestId"]

RequestId = Annotated[str, StringConstraints(pattern=r"^req-[0-9]{1,12}$")]
_CARD = TypeAdapter(ChatCard)


@record
class ChatSession(Record):
    """`kind` doubles as the record's discriminator: org, department, division, function or step. The org chat is the fixed
    session `cs_org` of node `root`. Function and step sessions are read-only logs; an archived session (a merged-away
    division's) is not writable and is filed under its survivor."""

    FAMILY = "chat_session"
    kind: Literal["org", "department", "division", "function", "step", "legacy"]
    id: SessionId
    node_id: GraphNodeId
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    writable: bool
    status: Literal["active", "archived"] = "active"
    filed_under: GraphNodeId | None = None
    connector: Literal["claude", "codex", "stub", ""] = ""
    model: Annotated[str, StringConstraints(max_length=100)] = ""
    pinned: Literal["claude", "codex", ""] = ""            # the owner's per-chat provider choice (ABS-6); "" = the policy decides
    pinned_model: Annotated[str, StringConstraints(max_length=100)] = ""           # the model and effort of that choice (D131); empty when `pinned` is
    pinned_effort: Literal["", "low", "medium", "high", "xhigh", "max"] = ""
    run_id: RunId | None = None                            # the run an agent's function or step session belongs to (D130); None for every other chat
    provider_session_id: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    last_message_id: Annotated[int, Field(ge=0)] = 0
    note: Annotated[str, StringConstraints(max_length=500)] = ""
    created_at: Ts
    updated_at: Ts

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.kind == "org") != (self.id == "cs_org"):
            raise ValueError("the org chat, and only the org chat, is the session cs_org")
        if self.kind == "org" and self.node_id != "root":
            raise ValueError("the org chat belongs to the root node")
        if self.kind == "legacy" and (self.status != "archived" or self.writable):
            raise ValueError("an imported old chat is archived and read only")
        if self.kind in ("function", "step") and self.writable:
            raise ValueError("a function or step session is a read-only log")
        if self.status == "archived" and self.writable:
            raise ValueError("an archived session is not writable")
        if not self.pinned and (self.pinned_model or self.pinned_effort):
            raise ValueError("a model or an effort is chosen together with its provider")
        if self.run_id is not None and self.kind not in ("function", "step"):
            raise ValueError("only a function or step session belongs to a run")
        if self.filed_under is not None and self.status != "archived":
            raise ValueError("only an archived session is filed under another node")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at is before created_at")
        return self


@record
class ChatMessage(Record):
    """`kind` doubles as the discriminator: text, question, card, note or error. `who` is user, sutra, identity, W-3 and so on.
    A card message carries a `ChatCard` in `card` and no text; every other kind carries text and no card."""

    FAMILY = "chat_message"
    kind: Literal["text", "question", "card", "note", "error"]
    session_id: SessionId
    role: Literal["user", "agent", "system"]
    who: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    text: Annotated[str, StringConstraints(max_length=200_000)] = ""
    card: JsonObject | None = None
    meta: MessageMeta = MessageMeta()
    blocks: list[ChatBlock] = []                            # typed provider blocks of a settled chat turn (ABS-6), stored in meta_json
    pause: Annotated[str, StringConstraints(min_length=1, max_length=60)] | None = None
    answered_by: Annotated[int, Field(ge=1)] | None = None
    task_id: TaskId | None = None
    src_ref: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    state: Literal["ok", "pending", "error"] = "ok"
    at: Ts

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.role == "user") != (self.who == "user"):
            raise ValueError("a message is from the user exactly when its role is user")
        if self.kind == "card":
            if self.card is None:
                raise ValueError("a card message carries a card")
            if self.text:
                raise ValueError("a card message carries no text")
            try:
                _CARD.validate_python(self.card)
            except ValidationError as exc:
                first = exc.errors(include_url=False, include_input=False)[0]
                raise ValueError(f"card is not a known card: {'.'.join(str(p) for p in first['loc'])}: {first['msg']}") from None
        else:
            if self.card is not None:
                raise ValueError("only a card message carries a card")
            if not self.text:
                raise ValueError(f"a {self.kind} message carries text")
        if self.answered_by is not None and self.kind != "question":
            raise ValueError("only a question is answered")
        if self.kind == "question" and self.role != "agent":
            raise ValueError("a question is asked by an agent")
        return self


@record
class UsageRecord(Record):
    """One model request, built once by the connector Router (D37). `atom_id` is the atom the call is charged to: a function
    atom id, the overhead key of a run or request, or `<run id>:W-n.aK` for a J2 workflow atom (so a bounded string, not an
    AtomId). Stub rows are stored and left out of totals."""

    FAMILY = "usage_record"
    kind: Literal["usage_record"] = "usage_record"
    at: Ts
    provider: Literal["claude", "codex", "stub"]
    model: Annotated[str, StringConstraints(max_length=100)] = ""
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    session_id: SessionId | None = None
    node_id: GraphNodeId | None = None
    task_id: TaskId | None = None
    dept_id: NodeId | None = None
    fn: Annotated[str, StringConstraints(min_length=1, max_length=20)] | None = None
    step: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    atom_id: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    usd: Annotated[float, Field(ge=0)] | None = None
    tokens_in: Annotated[int, Field(ge=0)] | None = None
    tokens_out: Annotated[int, Field(ge=0)] | None = None
    seconds: Annotated[float, Field(ge=0)] = 0.0
    ok: bool = True
    how: Annotated[str, StringConstraints(max_length=40)] = ""
    call_ref: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    detail: JsonObject | None = None


@record
class WorkTask(Record):
    """One run of one department (the `tasks` row). A run id exists from the moment the task starts; a task that is starting,
    running or waiting for the owner always has one. Times are epoch seconds and run in order."""

    FAMILY = "work_task"
    kind: Literal["work_task"] = "work_task"
    id: TaskId
    dept_id: Annotated[str, StringConstraints(pattern=DEPT_ID_RE)]
    scope_node_id: NodeId | None = None
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    user_text: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    framing: Annotated[str, StringConstraints(max_length=20_000)] = ""
    status: TaskStatus
    run_id: RunId | None = None
    parent_task_id: TaskId | None = None
    depends_on: Annotated[list[TaskId], Field(max_length=20)] = []
    request_id: RequestId | None = None
    origin_message_id: Annotated[int, Field(ge=1)] | None = None
    change_id: Annotated[str, StringConstraints(pattern=r"^chg-[0-9]{4,9}$")] | None = None
    settings: TaskSettings = TaskSettings()
    pid: Annotated[int, Field(ge=1)] | None = None
    events_offset: Annotated[int, Field(ge=0)] = 0
    inbox_seq: Annotated[int, Field(ge=0)] = 0
    outcome: Annotated[str, StringConstraints(max_length=2000)] = ""
    created_at: Ts
    started_at: Ts | None = None
    ended_at: Ts | None = None
    last_event_at: Ts | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.status in LIVE_STATUSES and self.run_id is None:
            raise ValueError(f"a {self.status} task has a run id")
        if self.status in TERMINAL_STATUSES and self.ended_at is None:
            raise ValueError(f"a {self.status} task has an end time")
        if self.status not in TERMINAL_STATUSES and self.ended_at is not None:
            raise ValueError(f"a {self.status} task has not ended")
        if self.parent_task_id == self.id or self.id in self.depends_on:
            raise ValueError("a task cannot be its own parent or dependency")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on lists a task twice")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at is before created_at")
        if self.ended_at is not None and self.ended_at < (self.started_at if self.started_at is not None else self.created_at):
            raise ValueError("ended_at is before the task started")
        return self
