"""Wire and run models of the orchestrator (orchestrator 3.3, S1-contracts-09, S3-web-04, S4-fnodes-10).

Every class here derives from the library's `Value` (closed, strict, frozen). Times on the wire are ISO-8601 with a Z
(`Iso`); the database holds epoch seconds. A few field names collide with pydantic (`schema`): they are declared as
`schema_` with the alias `schema`, and `Value` serialises by alias, so the wire key is `schema`.

    * the shapes the UI reads: ChartView, ChartChangeOut, GraphView, GraphNodeOut, NodeDetail, ChatSessionOut,
      ChatMessageOut, ChatCard, TaskOut, DepartmentOut, AtomOut, AtomLogRow, UsageOut, NeedsYouOut ...
    * the request/answer shapes: ChatPost, Accepted, Delivery, ChangeResult
    * the run documents: RunSpec (`task.json`) and the closed `RunEvent` union (one line of `events.jsonl`)
"""
import json
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import Field, StringConstraints, TypeAdapter, ValidationError, field_validator, model_serializer, model_validator

from sutra_app.engine.spec import DEPT_ID_RE, RUN_ID_RE, TASK_SCHEMA, TASK_SETTING_KEYS
from sutra_app.library.chat import ChatBlock
from sutra_app.library.base import Value, nested_models, unwrap_annotation
from sutra_app.library.node import GraphNodeId, NodeState
from sutra_app.library.types import (
    FUNCTIONS, AtomId, ChangeId, FunctionName, JsonObject, NodeId, Ts, Violation, violations_from_validation_error,
)

__all__ = [
    "Iso", "Event", "Violation", "ChartNodeOut", "ChartView", "ChartChangeOut", "ChangeResult", "GraphEdgeOut", "GraphNodeOut",
    "GraphView", "FnStats", "FnMeta", "FnDetailMeta", "UsageTotals", "ChatSessionOut", "ChatMessageOut", "ChatOption",
    "ChatCard", "ChartChangeCard", "TaskCard", "ApprovalCard", "ChoiceCard", "NeedsYouCard", "DoneCard", "DoneReceipt", "AtomCard", "CardRow",
    "ChatChoice", "ChatPost", "Accepted", "Delivery", "TaskOut", "RunRef", "FunctionChip", "DepartmentOut", "DeptRow", "AtomOut",
    "AtomLogRow", "UsageOut", "NeedsYouOut", "NodeDetail", "TaskSettings", "UpstreamRef", "RunSpec", "RunEvent", "RUN_EVENT_TYPES",
    "RUN_EVENT_VARIANTS", "EventParseError", "parse_event", "RunStarted", "RunSay", "RunNode", "RunStep", "RunAtom", "RunUsage",
    "RunHeartbeat", "RunEnded", "ChangeContext", "NodeInit", "ResumeInfo", "TASK_STATUSES", "LIVE_STATUSES", "TERMINAL_STATUSES",
    "STEP_ID_RE",
]

Iso = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")]
Name = Annotated[str, StringConstraints(max_length=200)]
Line = Annotated[str, StringConstraints(max_length=1000)]
Body = Annotated[str, StringConstraints(max_length=500_000)]
Ident = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Ids = Annotated[list[Ident], Field(max_length=500)]
Count = Annotated[int, Field(ge=0)]
Seconds = Annotated[float, Field(ge=0)]
TaskId = Annotated[str, StringConstraints(pattern=r"^tsk_[0-9a-f]{12}$")]
SessionId = Annotated[str, StringConstraints(pattern=r"^(cs_[0-9a-f]{12}|cs_org|cs_old_[a-z0-9]{12})$")]      # cs_old_*: an imported old chat (D113)
RunId = Annotated[str, StringConstraints(pattern=r"^" + RUN_ID_RE + r"$")]
DeptId = Annotated[str, StringConstraints(pattern=DEPT_ID_RE)]
StepId = Annotated[str, StringConstraints(pattern=r"^(W-[0-9]+|team:[^\x00-\x1f\x7f]{1,80})$")]
STEP_ID_RE = re.compile(r"W-[0-9]+|team:[^\x00-\x1f\x7f]{1,80}")

TASK_STATUSES = ("blocked", "queued", "starting", "running", "waiting_user", "done", "done_with_open_items", "stopped", "crashed", "cancelled")
LIVE_STATUSES = ("starting", "running", "waiting_user")
TERMINAL_STATUSES = ("done", "done_with_open_items", "stopped", "crashed", "cancelled")
TaskStatus = Literal["blocked", "queued", "starting", "running", "waiting_user", "done", "done_with_open_items", "stopped", "crashed", "cancelled"]
AtomDisplay = Literal["open", "verify_failed", "closed", "refused", "abandoned"]


# ---- events (SSE) -------------------------------------------------------------------------------------------------

class Event(Value):
    """One server event. `seq` is process-local from 1 each launch; the database hands out `seq` 0 and the bus assigns it."""

    seq: Count
    at: Iso
    type: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    data: JsonObject


# ---- chart --------------------------------------------------------------------------------------------------------

class ChartNodeOut(Value):
    id: NodeId
    kind: Literal["root", "department", "division"]
    name: Name
    purpose: Annotated[str, StringConstraints(max_length=1000)] = ""
    parent_id: NodeId | None
    position: Count


class ChartView(Value):
    version: Annotated[int, Field(ge=1)]       # = OrgChart.revision
    nodes: Annotated[list[ChartNodeOut], Field(max_length=600)]


class ChartChangeOut(Value):
    seq: Annotated[int, Field(ge=1)]
    id: ChangeId
    at: Iso
    actor: Literal["chat_agent", "user", "system"]
    decision: Literal["reuse", "add", "rearrange"]
    status: Literal["applied", "pending_approval", "rejected", "stale", "failed"]
    summary: Annotated[str, StringConstraints(max_length=500)]
    reason: Annotated[str, StringConstraints(max_length=2000)] = ""
    task_id: Annotated[str, StringConstraints(max_length=40)]
    task_title: Name = ""
    revision: Annotated[int, Field(ge=1)] | None = None
    added: Ids = []
    moved: Ids = []
    archived: Ids = []
    reused: Ids = []


class ChangeResult(Value):
    id: ChangeId
    status: Literal["applied", "pending_approval", "rejected", "stale"]
    decision: Literal["reuse", "add", "rearrange"]
    summary: Annotated[str, StringConstraints(max_length=500)]
    revision: Annotated[int, Field(ge=1)] | None = None
    added: Ids = []
    moved: Ids = []
    archived: Ids = []
    ids_by_ref: Annotated[dict[Annotated[str, StringConstraints(max_length=20)], NodeId], Field(max_length=100)] = {}


# ---- graph --------------------------------------------------------------------------------------------------------

class GraphEdgeOut(Value):
    src: Ident
    dst: Ident
    kind: Literal["contains", "has_function", "has_step", "handoff", "step", "speaks_to", "depends_on"]
    label: Annotated[str, StringConstraints(max_length=120)] = ""


class GraphNodeOut(Value):
    """`kind` is 'function' for the five function nodes (`fn` names which). `meta`: `run_id` on department and step nodes; on a
    function node exactly `{stats, wait_on}` in a GraphView (`FnMeta`) and the seven keys of `FnDetailMeta` in a NodeDetail."""

    id: GraphNodeId
    kind: Literal["root", "department", "division", "function", "step"]
    label: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    status: NodeState
    detail: Annotated[str, StringConstraints(max_length=300)] = ""
    chat_session_id: SessionId | None = None
    org_node_id: NodeId | None = None
    dept_id: NodeId | None = None
    task_id: TaskId | None = None
    fn: FunctionName | None = None
    step_ref: Annotated[str, StringConstraints(max_length=60)] | None = None
    version: Annotated[int, Field(ge=1)] = 1
    meta: JsonObject = {}


class GraphView(Value):
    version: Count
    chart_version: Count
    nodes: Annotated[list[GraphNodeOut], Field(max_length=5000)]
    edges: Annotated[list[GraphEdgeOut], Field(max_length=20000)]


class FnStats(Value):
    """The chip numbers of a function node: the first four from the `node` event, the atom counts from `atoms.display`
    (failed = verify_failed; total counts every atom of the node)."""

    calls: Count = 0
    seconds: Seconds = 0.0
    tokens_in: Count = 0
    tokens_out: Count = 0
    atoms_open: Count = 0
    atoms_closed: Count = 0
    atoms_failed: Count = 0
    atoms_total: Count = 0


class FnMeta(Value):
    """A function node's `meta` in GraphView and `graph.updated`: exactly these two keys."""

    stats: FnStats
    wait_on: Annotated[str, StringConstraints(max_length=80)] | None = None


class FnDetailMeta(Value):
    """A function node's `meta` in NodeDetail: exactly these seven keys."""

    goal: Annotated[str, StringConstraints(max_length=1000)]
    task: Annotated[str, StringConstraints(max_length=1000)]
    context: Annotated[list[Annotated[str, StringConstraints(max_length=300)]], Field(max_length=40)]
    constraints: Annotated[list[Annotated[str, StringConstraints(max_length=300)]], Field(max_length=40)]
    wait_on: Annotated[str, StringConstraints(max_length=80)] | None = None
    hands_to: Annotated[list[FunctionName], Field(max_length=5)]
    stats: FnStats


class UsageTotals(Value):
    calls: Count = 0
    usd: Annotated[float, Field(ge=0)] | None = None
    tokens_in: Count | None = None
    tokens_out: Count | None = None


# ---- chats --------------------------------------------------------------------------------------------------------

class ChatSessionOut(Value):
    id: SessionId
    node_id: GraphNodeId
    kind: Literal["org", "department", "division", "function", "step", "legacy"]
    title: Name
    writable: bool
    status: Literal["active", "archived"]
    filed_under: GraphNodeId | None = None
    connector: Annotated[str, StringConstraints(max_length=20)] = ""
    model: Annotated[str, StringConstraints(max_length=100)] = ""
    provider_session_id: Annotated[str, StringConstraints(max_length=200)] | None = None
    last_message_id: Count = 0
    note: Annotated[str, StringConstraints(max_length=500)] = ""
    phase: Literal["reading", "planning", "building", "working", "ready"] | None = None     # the org chat only


class ChatOption(Value):
    id: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    label: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class _NodeRef(Value):
    id: NodeId
    name: Name


class _AddedNode(_NodeRef):
    kind: Literal["department", "division"]


class _MovedNode(_NodeRef):
    from_name: Name
    to_name: Name


class _ArchivedNode(_NodeRef):
    into_name: Name


class ChartChangeCard(Value):
    type: Literal["chart_change"]
    change_id: ChangeId
    decision: Literal["reuse", "add", "rearrange"]
    summary: Annotated[str, StringConstraints(max_length=500)]
    added: Annotated[list[_AddedNode], Field(max_length=50)] = []
    moved: Annotated[list[_MovedNode], Field(max_length=50)] = []
    archived: Annotated[list[_ArchivedNode], Field(max_length=50)] = []
    pending: bool = False


class TaskCard(Value):
    type: Literal["task"]
    task_id: TaskId
    dept_id: NodeId
    dept_name: Name
    title: Name
    status: TaskStatus


class ApprovalCard(Value):
    type: Literal["approval"]
    change_id: ChangeId
    question: Annotated[str, StringConstraints(max_length=500)]
    options: Annotated[list[ChatOption], Field(max_length=10)]
    impact: Annotated[list[Annotated[str, StringConstraints(max_length=160)]], Field(max_length=8)] = []      # what a yes would do (reorg_preview.py)


class ChoiceCard(Value):
    type: Literal["choice"]
    question: Annotated[str, StringConstraints(max_length=500)]
    options: Annotated[list[ChatOption], Field(max_length=10)]


class NeedsYouCard(Value):
    type: Literal["needs_you"]
    dept_id: NodeId
    dept_name: Name
    question_message_id: Annotated[int, Field(ge=1)]
    text: Body
    options: Annotated[list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=20)] = []


class DoneReceipt(Value):
    """What a finished task cost and took, evidence only (GAP-model-quality): `usd` sums the ledger's Claude figures (a floor: a failed call
    has none, so the page says "about"), `tokens` the token counts (what a Codex-only task shows), `seconds` from start to end, the atoms of
    the task by final state (`checks_total` 0: the team recorded none, so no check is claimed) and the attempt number of a retry."""
    usd: Annotated[float, Field(ge=0)] | None = None
    tokens: Count | None = None
    seconds: Count | None = None
    checks_passed: Count = 0
    checks_total: Count = 0
    attempt: Annotated[int, Field(ge=2)] | None = None


class DoneCard(Value):
    type: Literal["done"]
    task_id: TaskId
    dept_name: Name
    title: Name
    status: TaskStatus
    outcome: Annotated[str, StringConstraints(max_length=2000)] = ""
    receipt: DoneReceipt | None = None

    @model_serializer(mode="wrap")
    def _receipt_only_when_there_is_one(self, handler: Any) -> dict[str, Any]:
        """A card without a receipt (every card stored before it existed) keeps the wire shape it always had: the key is left out."""
        data = handler(self)
        if data.get("receipt") is None:
            data.pop("receipt", None)
        return data


class CardRow(Value):
    label: Annotated[str, StringConstraints(max_length=80)]
    text: Annotated[str, StringConstraints(max_length=2000)]


class AtomCard(Value):
    type: Literal["atom"]
    atom_id: Ident
    outcome: Literal["opened", "verify_failed", "closed", "refused", "abandoned"]
    label: Annotated[str, StringConstraints(max_length=80)]
    goal: Annotated[str, StringConstraints(max_length=1000)]
    rows: Annotated[list[CardRow], Field(max_length=30)] = []


ChatCard = Annotated[
    Union[ChartChangeCard, TaskCard, ApprovalCard, ChoiceCard, NeedsYouCard, DoneCard, AtomCard],
    Field(discriminator="type"),
]


class ChatMessageOut(Value):
    id: Annotated[int, Field(ge=1)]
    session_id: SessionId
    role: Literal["user", "agent", "system"]
    who: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    kind: Literal["text", "question", "card", "note", "error"]
    text: Body
    card: ChatCard | None = None
    pause: Annotated[str, StringConstraints(max_length=60)] | None = None
    answered_by: Annotated[int, Field(ge=1)] | None = None
    task_id: TaskId | None = None
    state: Literal["ok", "pending", "error"] = "ok"
    at: Iso
    blocks: Annotated[list[ChatBlock], Field(max_length=500)] = []        # the typed provider blocks of a settled chat turn (ABS-6)
    turn: Annotated[int, Field(ge=1)] | None = None                       # a direct-chat reply: the id of the owner's line it answers

    @model_serializer(mode="wrap")
    def _blocks_only_when_there_are_some(self, handler: Any) -> dict[str, Any]:
        """The wire shape of a message without blocks (or a turn) is what it always was: the keys are left out when empty."""
        data = handler(self)
        if not data.get("blocks"):
            data.pop("blocks", None)
        if data.get("turn") is None:
            data.pop("turn", None)
        return data


class ChatChoice(Value):
    message_id: Annotated[int, Field(ge=1)]
    option: Annotated[str, StringConstraints(min_length=1, max_length=200)]       # the option's id or its label text


class ChatPost(Value):
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000)]
    choice: ChatChoice | None = None


class Accepted(Value):
    message_id: Annotated[int, Field(ge=1)]
    turn: Literal["started", "queued"]


class Delivery(Value):
    message_id: Annotated[int, Field(ge=1)]
    delivered: Literal["answer", "follow_up"]
    task_id: TaskId


# ---- tasks, departments, atoms, usage -------------------------------------------------------------------------

class TaskOut(Value):
    id: TaskId
    dept_id: NodeId
    dept_name: Name
    scope_node_id: NodeId | None = None
    title: Name
    status: TaskStatus
    run_id: RunId | None = None
    parent_task_id: TaskId | None = None
    depends_on: Annotated[list[TaskId], Field(max_length=20)] = []
    outcome: Annotated[str, StringConstraints(max_length=2000)] = ""
    created_at: Iso
    started_at: Iso | None = None
    ended_at: Iso | None = None
    usage: UsageTotals = UsageTotals()


class RunRef(Value):
    run_id: RunId
    task_id: TaskId
    dept_id: NodeId
    dir: Annotated[str, StringConstraints(min_length=1, max_length=400)]          # relative to the data dir
    status: TaskStatus
    pid: Annotated[int, Field(ge=1)] | None = None
    started_at: Iso | None = None
    ended_at: Iso | None = None


class FunctionChip(Value):
    id: GraphNodeId
    fn: FunctionName
    status: NodeState
    chat_session_id: SessionId | None = None


class DepartmentOut(Value):
    id: NodeId
    name: Name
    purpose: Annotated[str, StringConstraints(max_length=1000)] = ""
    node_status: NodeState
    live_task_id: TaskId | None = None
    session_id: SessionId | None = None
    functions: Annotated[list[FunctionChip], Field(max_length=5)] = []


class DeptRow(Value):
    """What `Services.department` returns. The engine and the UI read `id, name, archived, merged_into_name` through their own
    Protocols. A department is never archived, moved or merged (DL5), so `archived` is False and `merged_into_name` is empty."""

    id: NodeId
    name: Name
    archived: bool = False
    merged_into_name: Name = ""


class AtomOut(Value):
    """`id` is the stored key (`'<run id>:W-3.a1'` for an atom/1 row); `state` is the display word."""

    id: Ident
    schema_: Literal["work-atom/0.3", "atom/1"] = Field(alias="schema")
    node_id: GraphNodeId
    task_id: TaskId | None = None
    state: AtomDisplay
    goal: Annotated[str, StringConstraints(max_length=2000)]
    attempt: Annotated[int, Field(ge=0, le=3)]
    ts_open: Iso
    ts_closed: Iso | None = None
    body: JsonObject
    usage: UsageTotals = UsageTotals()


class AtomLogRow(Value):
    """One row of the Atom log (`atom_ledger`); `status` is the display word at the end; `body` is the library LedgerRow."""

    seq: Annotated[int, Field(ge=1)]
    atom_id: Ident
    node_id: GraphNodeId
    status: Literal["closed", "verify_failed", "abandoned", "refused"]
    body: JsonObject
    ts: Iso


class UsageOut(Value):
    id: Annotated[int, Field(ge=1)]
    at: Iso
    provider: Literal["claude", "codex", "stub"]
    model: Annotated[str, StringConstraints(max_length=100)] = ""
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    session_id: SessionId | None = None
    node_id: GraphNodeId | None = None
    task_id: TaskId | None = None
    dept_id: NodeId | None = None
    fn: Annotated[str, StringConstraints(max_length=20)] | None = None
    step: Annotated[str, StringConstraints(max_length=100)] | None = None
    atom_id: Ident | None = None
    usd: Annotated[float, Field(ge=0)] | None = None
    tokens_in: Count | None = None
    tokens_out: Count | None = None
    seconds: Seconds = 0.0
    ok: bool = True
    how: Annotated[str, StringConstraints(max_length=40)] = ""
    call_ref: Ident | None = None
    detail: JsonObject | None = None


class NeedsYouOut(Value):
    message_id: Annotated[int, Field(ge=1)]
    session_id: SessionId
    kind: Literal["question", "approval"]
    dept_id: NodeId | None = None
    dept_name: Name = ""
    text: Body
    options: Annotated[list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=20)] = []
    asked_at: Iso
    waiting_s: Count | None = None          # how long it has waited, by the server's clock at the read (gap attention)
    stale: bool = False                     # waited past waiting.ASK_STALE_S (24 h)


class NodeDetail(Value):
    node: GraphNodeOut
    session: ChatSessionOut | None = None
    atoms: Annotated[list[AtomOut], Field(max_length=200)] = []
    usage_total: UsageTotals = UsageTotals()
    task: TaskOut | None = None
    archived_chats: Annotated[list[ChatSessionOut], Field(max_length=200)] = []


# ---- the run document: task.json -----------------------------------------------------------------------------------

_INT_SETTING = re.compile(r"[1-9][0-9]{0,5}")


class TaskSettings(Value):
    """The seven task keys a request may carry (D18, S1-contracts-03), all text as J2 reads its environment. A key left unset is
    left out of the dump. Anything else is refused (closed class), so a model reply or web request cannot reach live email,
    a Chrome path or a forced audit failure."""

    J2_OUTPUT: Literal["website", "prd", "hld", "lld"] | None = None
    J2_BUDGET: Annotated[str, StringConstraints(max_length=6)] | None = None
    J2_BUDGET_CAP: Annotated[str, StringConstraints(max_length=6)] | None = None
    J2_FIXES: Literal["0", "1"] | None = None
    J2_MEMORY: Literal["0", "1"] | None = None
    J2_SLIM: Literal["0", "1"] | None = None
    J2_RATES: Literal["0", "1"] | None = None

    @field_validator("J2_BUDGET", "J2_BUDGET_CAP")
    @classmethod
    def _whole_number_in_range(cls, value: str | None) -> str | None:
        if value is not None and (not _INT_SETTING.fullmatch(value) or int(value) > 100_000):
            raise ValueError("must be a whole number from 1 to 100000")
        return value

    @model_serializer(mode="wrap")
    def _only_what_is_set(self, handler: Any) -> dict[str, Any]:
        return {key: value for key, value in handler(self).items() if value is not None}


if tuple(TaskSettings.model_fields) != TASK_SETTING_KEYS:            # the engine's TaskSpec reads these keys: they must agree
    raise ImportError("TaskSettings and the engine's TASK_SETTING_KEYS differ")


class UpstreamRef(Value):
    dept_id: DeptId
    run_id: RunId
    title: Name
    files: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=400)]], Field(max_length=200)] = []


class RunSpec(Value):
    """`task.json` ("run-spec/1"): the strict writer of a document the engine's `TaskSpec` reads. `user_text` is the owner's
    words verbatim (Identity starts from them); `framing` is the chat agent's paragraph, context only."""

    schema_: Literal["run-spec/1"] = Field(TASK_SCHEMA, alias="schema")
    run_id: RunId
    task_id: TaskId
    dept_id: DeptId
    dept_label: Name
    scope_id: NodeId | None = None
    scope_label: Name | None = None
    user_text: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    framing: Annotated[str, StringConstraints(max_length=20_000)] = ""
    parent_run_id: RunId | None = None
    seed_from: RunId | None = None
    upstream: Annotated[list[UpstreamRef], Field(max_length=10)] = []
    settings: TaskSettings = TaskSettings()
    connector: Literal["auto", "claude", "codex", "stub"] = "auto"


# ---- the run events (events.jsonl) -----------------------------------------------------------------------------

_Function = Literal["identity", "adaptation", "priority", "coordination", "audit"]
_NODE_STATUS = Literal["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"]
_FUNCTION_STATUS = ("idle", "running", "waiting", "waiting_on_you", "fault")


class _Event(Value):
    at: Iso


class RunStarted(_Event):
    t: Literal["run.started"]
    pid: Annotated[int, Field(ge=1)]
    schema_: Literal["events/1"] = Field(alias="schema")
    mock: bool
    seed: Literal["none", "rehydrated", "fresh"]


class RunSay(_Event):
    t: Literal["say"]
    id: Annotated[int, Field(ge=1)]
    who: Annotated[str, StringConstraints(pattern=r"^(" + "|".join(FUNCTIONS) + r"|validator|system|W-[0-9]+|team:[^\x00-\x1f\x7f]{1,80})$")]
    text: Body
    to_user: bool = False
    act: Annotated[str, StringConstraints(max_length=80)] | None = None
    pause: Annotated[str, StringConstraints(max_length=80)] | None = None
    questions: Annotated[list[JsonObject], Field(max_length=50)] | None = None
    next: Annotated[str, StringConstraints(max_length=80)] | None = None


class _TaskInfo(Value):
    id: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    kind: Annotated[str, StringConstraints(max_length=80)] | None
    summary: Annotated[str, StringConstraints(max_length=300)]
    state: Literal["running", "done"]
    set_by: Annotated[str, StringConstraints(max_length=80)]


class _Tokens(Value):
    input: Count
    output: Count


class RunNode(_Event):
    """The state of ONE node: a function (`fn`) or a builder step (`step`). It has no `goal` (a function node's standing goal,
    task and context come from its FunctionSpec); `task` and `context` are trace-only and the Projector ignores them;
    `wait_on` and `tokens` feed the node's `wait_on` and `stats`."""

    t: Literal["node"]
    fn: _Function | None = None
    step: StepId | None = None
    status: _NODE_STATUS
    detail: Annotated[str, StringConstraints(max_length=1000)] = ""
    calls: Count = 0
    seconds: Seconds = 0.0
    task: _TaskInfo | None = None
    context: Annotated[list[Annotated[str, StringConstraints(max_length=300)]], Field(max_length=40)] | None = None
    wait_on: Annotated[str, StringConstraints(max_length=80)] | None = None
    tokens: _Tokens | None = None

    @model_validator(mode="after")
    def _one_target_and_status(self) -> "RunNode":
        if (self.fn is None) == (self.step is None):
            raise ValueError("exactly one of fn or step")
        if self.fn is not None and self.status not in _FUNCTION_STATUS:
            raise ValueError(f"a function node uses one of {', '.join(_FUNCTION_STATUS)}, not {self.status}")
        return self


class RunStep(_Event):
    t: Literal["step"]
    step: StepId
    name: Annotated[str, StringConstraints(max_length=300)]
    parent: Annotated[str, StringConstraints(max_length=100)] | None = None
    status: _NODE_STATUS
    handoff: Annotated[list[Annotated[str, StringConstraints(max_length=100)]], Field(max_length=100)] = []
    reads: Annotated[list[Annotated[str, StringConstraints(max_length=100)]], Field(max_length=100)] = []
    rework: Annotated[str, StringConstraints(max_length=100)] | None = None


_ATOM_STATUSES = {"atom/1": ("open", "closed", "verify_failed", "abandoned"), "work-atom/0.3": ("open", "closed", "refused", "abandoned")}


class _EventAtom(Value):
    id: AtomId
    schema_: Literal["atom/1", "work-atom/0.3"] = Field(alias="schema")
    goal: Annotated[str, StringConstraints(max_length=2000)]
    work_kind: Literal["llm", "skill", "bash", "manual"]
    verify_template: Annotated[str, StringConstraints(max_length=80)] | None = None
    status: Literal["open", "closed", "refused", "verify_failed", "abandoned"]
    attempt: Annotated[int, Field(ge=0, le=3)]
    closed_by: Annotated[str, StringConstraints(max_length=80)] | None = None
    reason: Annotated[str, StringConstraints(max_length=2000)] | None = None
    body: JsonObject
    ts_open: Ts
    ts_closed: Ts | None = None

    @model_validator(mode="after")
    def _status_belongs_to_schema(self) -> "_EventAtom":
        if self.status not in _ATOM_STATUSES[self.schema_]:
            raise ValueError(f"status {self.status} does not exist for {self.schema_} (it has {', '.join(_ATOM_STATUSES[self.schema_])})")
        return self


class RunAtom(_Event):
    """A function-node atom transition (`work-atom/0.3`: with `outcome`, `card` and, at the end, `ledger`) or a builder's J2
    `atom/1` view (those three stay null)."""

    t: Literal["atom"]
    node: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    atom: _EventAtom
    outcome: Literal["opened", "verify_failed", "closed", "refused", "abandoned"] | None = None
    card: JsonObject | None = None
    ledger: JsonObject | None = None

    @model_validator(mode="after")
    def _function_fields_only_for_function_atoms(self) -> "RunAtom":
        if self.atom.schema_ == "atom/1" and (self.outcome is not None or self.card is not None or self.ledger is not None):
            raise ValueError("outcome, card and ledger belong to work-atom/0.3 only")
        return self


class RunUsage(_Event):
    t: Literal["usage"]
    fn: Annotated[str, StringConstraints(max_length=40)]
    step: Annotated[str, StringConstraints(max_length=100)] | None = None
    atom: Annotated[str, StringConstraints(max_length=200)] | None = None
    provider: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    model: Annotated[str, StringConstraints(max_length=100)] | None = None
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    usd: Annotated[float, Field(ge=0)] | None = None
    tokens_in: Count | None = None
    tokens_out: Count | None = None
    seconds: Seconds
    ok: bool
    how: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    call_ref: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    detail: JsonObject | None = None


class RunHeartbeat(_Event):
    t: Literal["heartbeat"]


class RunEnded(_Event):
    t: Literal["run.ended"]
    status: Literal["done", "done_with_open_items", "stopped", "crashed"]
    outcome: Annotated[str, StringConstraints(max_length=2000)] = ""
    code: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None

    @model_validator(mode="after")
    def _only_a_crash_has_a_code(self) -> "RunEnded":
        if self.code is not None and self.status != "crashed":
            raise ValueError("only a crashed run has a code")
        return self


RUN_EVENT_TYPES = ("run.started", "say", "node", "step", "atom", "usage", "heartbeat", "run.ended")
RUN_EVENT_VARIANTS: dict[str, type[_Event]] = {
    "run.started": RunStarted, "say": RunSay, "node": RunNode, "step": RunStep, "atom": RunAtom, "usage": RunUsage,
    "heartbeat": RunHeartbeat, "run.ended": RunEnded,
}
RunEvent = Annotated[
    Union[RunStarted, RunSay, RunNode, RunStep, RunAtom, RunUsage, RunHeartbeat, RunEnded], Field(discriminator="t"),
]
_RUN_EVENT_ADAPTER: TypeAdapter = TypeAdapter(RunEvent)


class EventParseError(ValueError):
    """A line of events.jsonl that cannot become a RunEvent. `code`: not_json, not_object, unknown_type or invalid (then
    `violations` says why). The watcher skips the line with a note (failure F9)."""

    def __init__(self, code: str, message: str, *, t: str | None = None, violations: list[Violation] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.t = t
        self.violations = violations or []


def _known_keys(cls: type[Value]) -> set[str]:
    keys: set[str] = set()
    for name, info in cls.model_fields.items():
        keys.add(name)
        if isinstance(info.alias, str):
            keys.add(info.alias)
    return keys


def _prune(cls: type[Value], data: dict[str, Any], prefix: str, dropped: list[str]) -> dict[str, Any]:
    """`data` without the keys `cls` does not declare, here and in the closed objects nested one level at a time."""
    known = _known_keys(cls)
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            dropped.append(f"{prefix}{key}")
            continue
        info = cls.model_fields.get(key) or next((i for n, i in cls.model_fields.items() if i.alias == key), None)
        if info is not None and isinstance(value, dict):
            inner = [m for m in nested_models(unwrap_annotation(info.annotation)[0]) if issubclass(m, Value)]
            if len(inner) == 1:
                value = _prune(inner[0], value, f"{prefix}{key}.", dropped)
        out[key] = value
    return out


def parse_event(line: str | bytes | Mapping[str, Any], strict: bool = False, *, dropped: list[str] | None = None) -> Any:
    """One line of `events.jsonl` (text, bytes or an already parsed object) as the RunEvent variant its `t` names.

    `strict=False` (the server): keys a variant does not declare are dropped before validating, at the top and in the objects
    nested in it (`atom.extra`), and listed in `dropped` when a list is given, so a newer engine cannot lose events.
    `strict=True` (tests): they are an error. Unknown `t`, bad JSON, a non-object or a wrong shape raise `EventParseError`."""
    if isinstance(line, Mapping):
        data: Any = dict(line)
    else:
        try:
            text = bytes(line).decode("utf-8") if isinstance(line, (bytes, bytearray)) else line
            data = json.loads(text)
        except (ValueError, RecursionError):
            raise EventParseError("not_json", "the line is not valid JSON") from None
    if not isinstance(data, dict):
        raise EventParseError("not_object", "an event is a JSON object")
    kind = data.get("t")
    cls = RUN_EVENT_VARIANTS.get(kind) if isinstance(kind, str) else None
    if cls is None:
        raise EventParseError("unknown_type", f"unknown event type {str(kind)[:40]!r}", t=kind if isinstance(kind, str) else None)
    if not strict:
        data = _prune(cls, data, "", dropped if dropped is not None else [])
    try:
        return cls.model_validate(data)
    except ValidationError as exc:
        raise EventParseError("invalid", f"a {kind} event is not valid", t=kind, violations=violations_from_validation_error(exc)) from None


# ---- names the stores share ----------------------------------------------------------------------------------------

class ChangeContext(Value):
    """Who and what a chart change belongs to. `request_title` is set by the TurnRunner (T7): the first assignment's title,
    else the owner's request cut to 60 characters at a word boundary on one line."""

    session_id: SessionId
    message_id: Annotated[int, Field(ge=1)] | None = None
    request_id: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    request_title: Name = ""


class NodeInit(Value):
    """What `ensure_node` needs to make a graph node and its chat session in one transaction: the Node payload (checked by the
    gate, `chat_session_id` filled in by `ensure_node`) and the session's own facts."""

    node: JsonObject
    session_title: Name
    writable: bool = False
    session_id: SessionId | None = None            # None: ensure_node makes one; the root's is the fixed `cs_org`


class ResumeInfo(Value):
    """Diagnostics only: the router's transcript hook is `ChatTranscripts`."""

    connector: Annotated[str, StringConstraints(max_length=20)] = ""
    provider_session_id: Annotated[str, StringConstraints(max_length=200)] | None = None
    messages: Annotated[list[ChatMessageOut], Field(max_length=20)] = []

