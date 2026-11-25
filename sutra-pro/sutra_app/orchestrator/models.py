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

from pydantic import ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError, field_validator, model_serializer, model_validator

from sutra_app.engine.spec import (
    DEPT_ID_RE, OUTPUT_NAME_RE, RUN_ID_RE, RUN_TEMPLATE_ID_RE, RUN_TEMPLATE_WORKFLOWS_MAX, TASK_SCHEMA, TASK_SETTING_KEYS, run_template_keys,
)
from sutra_app.library.chat import ChatBlock
from sutra_app.library.base import Value, nested_models, unwrap_annotation
from sutra_app.library.node import GraphNodeId, NodeState
from sutra_app.library.types import (
    FUNCTIONS, AtomId, ChangeId, FunctionName, JsonObject, NodeId, Ref, Ts, Violation, violations_from_validation_error,
)

__all__ = [
    "Iso", "Event", "Violation", "ChartNodeOut", "ChartView", "ChartChangeOut", "ChangeResult", "GraphEdgeOut", "GraphNodeOut",
    "GraphView", "FnStats", "FnMeta", "FnDetailMeta", "UsageTotals", "ChatSessionOut", "ChatMessageOut", "ChatOption",
    "ChatCard", "ChartChangeCard", "TaskCard", "ApprovalCard", "ChoiceCard", "NeedsYouCard", "DoneCard", "DoneReceipt", "DoneReport", "AtomCard", "CardRow",
    "DeliverableCard", "DeliverableChanges", "ChangedFile", "DELIVERABLE_TEXT_MAX", "DELIVERABLE_FILES_MAX", "AnswerCard", "AnswerSource",
    "ChatChoice", "ChatPost", "Accepted", "Delivery", "TaskOut", "RunRef", "FunctionChip", "DepartmentOut", "DeptRow", "AtomOut",
    "AtomLogRow", "UsageOut", "NeedsYouOut", "NodeDetail", "TaskSettings", "UpstreamRef", "RunSpec", "RunEvent", "RUN_EVENT_TYPES",
    "RUN_EVENT_VARIANTS", "EventParseError", "parse_event", "RunStarted", "RunSay", "RunNode", "RunStep", "RunAtom", "RunUsage",
    "RunHeartbeat", "RunEnded", "ChangeContext", "NodeInit", "ResumeInfo", "TASK_STATUSES", "LIVE_STATUSES", "TERMINAL_STATUSES",
    "STEP_ID_RE", "ProjectId", "AgentNodeId", "GrantId", "ApprovalId", "AgentNodeState", "NodeCaps", "NodeBlock", "ProjectOut", "NodeOut", "NodeApprovalCard", "SystemPermissionCard", "PROJECT_STATUSES", "NODE_STATES", "NODE_ROLES",
    "NODE_RUNTIMES",
]

ProjectId = Annotated[str, StringConstraints(pattern=r"^prj_[0-9a-f]{12}$")]
ApprovalId = Annotated[str, StringConstraints(pattern=r"^ap_[0-9a-f]{12}$")]
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
    """One server event. `seq` is process-local from 1 each launch; the database hands out `seq` 0 and the bus assigns it.

    The data keeps its strings exactly as they were: `Value` strips the white space around every string it validates, and a streamed piece of text ("the ", " price") is
    nothing but white space at its edges (streaming design D232: found by the browser test, the page saw "aprice in" and its offset check made it read the snapshot again)."""

    model_config = ConfigDict(str_strip_whitespace=False)

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
    pinned: Literal["claude", "codex", ""] = ""         # the owner's own choice for this chat: provider, model, effort ("" = none, D131)
    pinned_model: Annotated[str, StringConstraints(max_length=100)] = ""
    pinned_effort: Literal["", "low", "medium", "high", "xhigh", "max"] = ""
    run_id: RunId | None = None             # the run a function or step session belongs to (D130)
    direct_turn: Count | None = None        # the owner's line that a direct turn is answering right now (direct_running.py), else None: any page can offer Stop
    live: dict[str, Any] | None = None      # the live turn that is streaming in this chat ({generation_id, seq, state, attempt_no}, streaming design D203), else None (the key is left out)

    @model_serializer(mode="wrap")
    def _live_only_when_there_is_one(self, handler: Any) -> dict[str, Any]:
        """The wire shape of a chat session is what it always was unless a live turn is streaming in it."""
        data = handler(self)
        if data.get("live") is None:
            data.pop("live", None)
        return data


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
    project_id: ProjectId | None = None     # the project this task is a step of (nodes on): the card links to its page (D382); left out of the wire shape when there is none

    @model_serializer(mode="wrap")
    def _project_only_when_there_is_one(self, handler: Any) -> dict[str, Any]:
        """A card of an ordinary task keeps the wire shape it always had: no `project_id` key."""
        data = handler(self)
        if data.get("project_id") is None:
            data.pop("project_id", None)
        return data


class ProposedAdd(Value):
    """A project the org chat would start (D427): the change's ref and the name it suggests; the owner names it before it is made."""
    ref: Ref
    name: Name


class ApprovalCard(Value):
    type: Literal["approval"]
    change_id: ChangeId
    question: Annotated[str, StringConstraints(max_length=500)]
    options: Annotated[list[ChatOption], Field(max_length=10)]
    impact: Annotated[list[Annotated[str, StringConstraints(max_length=160)]], Field(max_length=8)] = []      # what a yes would do (reorg_preview.py)
    adds: Annotated[list[ProposedAdd], Field(max_length=8)] = []        # the projects a yes would start (D427); left out of the wire shape when none

    @model_serializer(mode="wrap")
    def _adds_only_when_there_are_some(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if not data.get("adds"):
            data.pop("adds", None)
        return data


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


class TeamChatCard(Value):
    """The org chat's pointer to a team's own chat (GAP3 dept-chats): "Started <name>: open its chat" when the turn made the team,
    "<name> has a question for you" when its Identity asked the owner. It carries no words of the team: the conversation stays in
    the team's chat (`session_id`). `node_id` is a department or a division."""
    type: Literal["team_chat"]
    node_id: NodeId
    name: Name
    kind: Literal["department", "division"] = "department"
    session_id: SessionId
    about: Literal["started", "question"] = "started"
    question_message_id: Annotated[int, Field(ge=1)] | None = None       # about `question`: the message in the team's chat that asks


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


class DoneReport(Value):
    """Where the finished report of a run opens (D135): the team's page at its Preview tab for this run. `label` is the deliverable's name ("Project work report")."""
    dept_id: NodeId
    run_id: RunId
    label: Name


class DoneCard(Value):
    type: Literal["done"]
    task_id: TaskId
    dept_name: Name
    title: Name
    status: TaskStatus
    outcome: Annotated[str, StringConstraints(max_length=2000)] = ""
    receipt: DoneReceipt | None = None
    report: DoneReport | None = None
    project_id: ProjectId | None = None     # the project this task is a step of (nodes on): the card links to its page (D394); left out of the wire shape when there is none

    @model_serializer(mode="wrap")
    def _receipt_and_report_only_when_there_are_some(self, handler: Any) -> dict[str, Any]:
        """A card without a receipt, a report or a project (every card stored before they existed) keeps the wire shape it always had: the keys are left out."""
        data = handler(self)
        for key in ("receipt", "report", "project_id"):
            if data.get(key) is None:
                data.pop(key, None)
        return data


DELIVERABLE_TEXT_MAX = 30_000          # characters of the report a team chat card holds (a longer report is cut and says so; the page opens the whole)
DELIVERABLE_FILES_MAX = 100            # changed files a card names (the host's record names as many; the rest are counted)


class ChangedFile(Value):
    """One path git saw change in the owner's folder during the run, relative to that folder."""
    path: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    status: Literal["new", "modified", "deleted", "reverted"]


class DeliverableChanges(Value):
    """What the engine host saw change in the owner's working folder during the run (git, before and after; never an agent): the first files and how
    many more there were. An empty list is an answer: git looked and nothing changed."""
    files: Annotated[list[ChangedFile], Field(max_length=DELIVERABLE_FILES_MAX)] = []
    more: Count = 0


class DeliverableCard(Value):
    """The finished deliverable of a run in the TEAM's chat (D135): the report as the team wrote it (markdown, `text`, cut at DELIVERABLE_TEXT_MAX with
    `cut` set), the files the host saw change in the owner's folder (`changes`, absent when the folder is no git work tree, access was read or git could not
    say), and where the whole report opens on the team page (`run_id`, `dept_id`). Posted once, by the Projector, when the run ends."""
    type: Literal["deliverable"]
    task_id: TaskId
    run_id: RunId
    dept_id: NodeId
    label: Name
    file: Annotated[str, StringConstraints(max_length=80)] = ""
    text: Annotated[str, StringConstraints(max_length=DELIVERABLE_TEXT_MAX)] = ""
    cut: bool = False
    changes: DeliverableChanges | None = None

    @model_serializer(mode="wrap")
    def _changes_only_when_known(self, handler: Any) -> dict[str, Any]:
        """No `changes` key when git could not say (not a work tree, read only, too slow): the card then says nothing of changes."""
        data = handler(self)
        if data.get("changes") is None:
            data.pop("changes", None)
        return data


class AnswerSource(Value):
    """One source a cited answer named, as code found it (DV-1, `orchestrator/citations.py`). `label` is `checked` or `could not find`; it is written by code and never by a model.
    `how` says what `checked` covers (`lines`: the file and those lines are there; `quote`: and the quoted words are on them) and is absent for `could not find`, which has a `reason`."""
    path: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    start: Annotated[int, Field(ge=0, le=999_999_999)]
    end: Annotated[int, Field(ge=0, le=999_999_999)]
    quote: Annotated[str, StringConstraints(max_length=1000)] | None = None
    label: Literal["checked", "could not find"]
    how: Literal["lines", "quote"] | None = None
    reason: Annotated[str, StringConstraints(max_length=200)] = ""

    @model_serializer(mode="wrap")
    def _only_what_there_is(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        for key in ("quote", "how"):
            if data.get(key) is None:
                data.pop(key, None)
        if not data.get("reason"):
            data.pop("reason", None)
        return data


class AnswerCard(Value):
    """The sources of a cited answer (DV-1), a card of its own in the chat right after the answer: every mark of the answer with its label, the counts, and the owner's question
    (the page drafts "Turn this into work" from it). `sources` empty is an answer too: the answer named no file. `more` counts marks past the limit that were not checked."""
    type: Literal["answer_sources"]
    question: Annotated[str, StringConstraints(max_length=500)] = ""
    sources: Annotated[list[AnswerSource], Field(max_length=50)] = []
    checked: Count = 0
    missing: Count = 0
    more: Count = 0
    tried: Count = 0                                                   # edit or web tool calls the turn made although Ask does not allow them (counted from the turn's own blocks, `tool_kinds`); left out when 0

    @model_serializer(mode="wrap")
    def _tried_only_when_there_were_some(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if not data.get("tried"):
            data.pop("tried", None)
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


class NodeApprovalCard(Value):
    """One open question of a project as a card (MAN-8): what is asked in plain words, which tier, which node it is about (empty: the whole project), the answers it takes and when it
    ends. `kind` is `tier` (the app tools or GitHub), `scope` (a wide write scope), `plan_estimate` (the plan's cost) or `system` (a permission of the computer, MAN-15). A plan estimate
    can be allowed once or refused; nothing is ever "allowed for the project" above tier 4."""

    type: Literal["node_approval"] = "node_approval"
    project_id: ProjectId
    approval_id: ApprovalId
    kind: Annotated[str, StringConstraints(max_length=40)]
    tier: Annotated[int, Field(ge=0, le=6)]
    node_id: Annotated[str, StringConstraints(max_length=40)] = ""
    question: Annotated[str, StringConstraints(max_length=500)]
    options: Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=4)]
    expires_at: Iso
    item: Annotated[str, StringConstraints(max_length=40)] = ""      # a system question: which permission (the buttons call its check and skip routes)


ChatCard = Annotated[
    Union[ChartChangeCard, TaskCard, ApprovalCard, ChoiceCard, NeedsYouCard, TeamChatCard, DoneCard, DeliverableCard, AtomCard, NodeApprovalCard, AnswerCard],
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
    passed_on: Annotated[int, Field(ge=1)] | None = None                  # the owner's line the org chat passed on to this team: the id of the original in cs_org
    steer: bool = False                                                    # the owner's note to an agent (POST /api/chats/{sid}/steer, D132): its src_ref is `steer:<id>`
    ask: Literal["q", "records", "model"] | None = None                    # the owner's question to a function (q) and its answer, made from its records or by a model
                                                                           # (POST /api/ask, D148): the src_ref is `ask:<id>`, `ask:<id>:records` or `ask:<id>:model`
    client_id: Annotated[str, StringConstraints(max_length=64)] | None = None   # the owner's line of a direct turn: the id the page sent with it (`direct-ask:<id>`, D220)
    attempt: Annotated[int, Field(ge=1)] | None = None                     # a direct-chat reply, note or error: which try of the owner's line it ends (1, or N for a retry, D216)
    superseded: bool = False                                               # a reply of a try that a later try of the same owner line replaced (kept, not shown as the answer)
    ordered: bool = False                                                  # `blocks` holds the whole turn in order, text included (D212)
    via: JsonObject | None = None                                          # a direct reply: {provider, model} that wrote it, so the header says the same live and after a reload
    mode: Literal["ask"] | None = None                                     # the owner's line of an Ask turn (DV-1, D350): left out of every other message, so a page that does not know Ask sees what it always saw
    attachments: Annotated[list[JsonObject], Field(max_length=10)] = []    # the owner's line that carried files (D440): what the model received of each (name, kind, sent, chars, cut, total); left out when empty

    @model_serializer(mode="wrap")
    def _blocks_only_when_there_are_some(self, handler: Any) -> dict[str, Any]:
        """The wire shape of a message without blocks (or a turn, a pass-on, a note or a question) is what it always was: the keys are left out when empty."""
        data = handler(self)
        if not data.get("blocks"):
            data.pop("blocks", None)
        if data.get("turn") is None:
            data.pop("turn", None)
        if data.get("passed_on") is None:
            data.pop("passed_on", None)
        if not data.get("steer"):
            data.pop("steer", None)
        if data.get("ask") is None:
            data.pop("ask", None)
        if data.get("mode") is None:
            data.pop("mode", None)
        if not data.get("attachments"):
            data.pop("attachments", None)
        if data.get("client_id") is None:
            data.pop("client_id", None)
        if data.get("attempt") is None:
            data.pop("attempt", None)
        if not data.get("superseded"):
            data.pop("superseded", None)
        if not data.get("ordered"):
            data.pop("ordered", None)
        if not data.get("via"):
            data.pop("via", None)
        return data


class ChatChoice(Value):
    message_id: Annotated[int, Field(ge=1)]
    option: Annotated[str, StringConstraints(min_length=1, max_length=200)]       # the option's id or its label text


class ChatPost(Value):
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000)]
    choice: ChatChoice | None = None
    # D252: the home screen's "Budget (work credits)" for a new request in the org chat; None: the team's own budget. The limits are
    # J2_BUDGET's (TaskSettings, EngineSettings.budget).
    budget: Annotated[int, Field(ge=1, le=100_000)] | None = None
    # MAN-8, D294: "Decide for me" for the project this request may become: the Gatekeeper's rule table answers its questions (never credits over the ceiling, never a permission of the computer).
    # Only read while SUTRA_NODES_V1 is on; None or false: the owner answers.
    decide_for_me: bool | None = None
    # D423: the home screen's dollar budget (API price) for a new request; None: the team's own. The limits are EngineSettings.usd_budget's.
    usd_budget: Annotated[float, Field(ge=1, le=10_000, allow_inf_nan=False)] | None = None

    @field_validator("usd_budget")
    @classmethod
    def _to_the_cent(cls, value: float | None) -> float | None:
        if value is not None and round(value, 2) != value:
            raise ValueError("dollars, at most two decimals")
        return value


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
    last_status: TaskStatus | None = None          # the newest task's status: a team whose last run is done shows Done once it is idle again
    session_id: SessionId | None = None
    functions: Annotated[list[FunctionChip], Field(max_length=5)] = []


class DeptRow(Value):
    """What `Services.department` returns. The engine and the UI read `id, name, archived, merged_into_name` through their own
    Protocols. A department is never moved or merged (DL5), so `merged_into_name` is empty; `archived` is True only for a project the owner
    deleted (hidden, D426): its page and runs stay readable, every write is refused."""

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
    kind: Literal["question", "approval", "node_approval"]
    dept_id: NodeId | None = None
    dept_name: Name = ""
    text: Body
    options: Annotated[list[Annotated[str, StringConstraints(max_length=500)]], Field(max_length=20)] = []
    asked_at: Iso
    waiting_s: Count | None = None          # how long it has waited, by the server's clock at the read (gap attention)
    stale: bool = False                     # waited past waiting.ASK_STALE_S (24 h)
    change_id: ChangeId | None = None       # an approval's change, and the projects it would start (D427): both left out when there are none
    adds: Annotated[list[ProposedAdd], Field(max_length=8)] = []

    @model_serializer(mode="wrap")
    def _change_only_for_approvals(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if data.get("change_id") is None:
            data.pop("change_id", None)
        if not data.get("adds"):
            data.pop("adds", None)
        return data


class NodeDetail(Value):
    node: GraphNodeOut
    session: ChatSessionOut | None = None
    atoms: Annotated[list[AtomOut], Field(max_length=200)] = []
    usage_total: UsageTotals = UsageTotals()
    task: TaskOut | None = None
    archived_chats: Annotated[list[ChatSessionOut], Field(max_length=200)] = []


# ---- multi-agent nodes: projects and nodes (design docs/design/multi-agent-nodes, D253, D283, D290) --------------------------------------
# A "node" here is a runtime node: a running agent, one `tasks` row plus one `agent_nodes` row (not a graph node, which is a box in the graph). These shapes are inert until
# SUTRA_NODES_V1 is on: nothing builds one while the flag is off, and `RunSpec.node` (MAN-3) is left out of `task.json` unless it is set.

AgentNodeId = Annotated[str, StringConstraints(pattern=r"^nd_[0-9a-f]{12}$")]
GrantId = Annotated[str, StringConstraints(pattern=r"^gr_[0-9a-f]{12}$")]
ScopePath = Annotated[str, StringConstraints(min_length=1, max_length=400)]
ScopeList = Annotated[list[ScopePath], Field(max_length=50)]

PROJECT_STATUSES = ("planning", "awaiting_approval", "running", "reviewing", "done", "done_with_open_items", "stopped", "failed")
NODE_STATES = ("planned", "awaiting_approval", "awaiting_system", "ready", "queued", "leased", "running", "handing_off", "done", "failed", "cancelled", "expired")
NODE_ROLES = ("planner", "worker", "reviewer")
NODE_RUNTIMES = ("inline", "engine", "light")
ProjectStatus = Literal["planning", "awaiting_approval", "running", "reviewing", "done", "done_with_open_items", "stopped", "failed"]
AgentNodeState = Literal["planned", "awaiting_approval", "awaiting_system", "ready", "queued", "leased", "running", "handing_off", "done", "failed", "cancelled", "expired"]
NodeRole = Literal["planner", "worker", "reviewer"]
NodeRuntime = Literal["inline", "engine", "light"]


class NodeCaps(Value):
    """What one node may spend before its host stops it (D272, D273): model calls, dollars where the provider reports them (none unless the owner sets it), wall time."""

    calls: Annotated[int, Field(ge=1, le=10_000)] = 60
    usd: Annotated[float, Field(gt=0, le=100_000)] | None = None
    wall_s: Annotated[int, Field(ge=1, le=86_400)] = 1800


class NodeBlock(Value):
    """The optional `node` block of `task.json` (D283): who this run is inside a project. Older readers ignore it (`TaskSpec` drops unknown keys); the writer leaves it out
    of the file while SUTRA_NODES_V1 is off, so the file is byte-identical to today's. Only workers and reviewers run as processes: the planner is inline."""

    id: AgentNodeId
    project_id: ProjectId
    role: Literal["worker", "reviewer"]
    runtime: Literal["engine", "light"]
    attempt: Annotated[int, Field(ge=1, le=10)] = 1
    grants_id: GrantId
    caps: NodeCaps = NodeCaps()
    scope: ScopeList = []
    # MAN-8 (D298): the app tools this node's grant gives it (`none`, `sutra`, `github` or `sutra+github`), so the host can put them on the node's own agent-turn calls (never on a builder-tools
    # call). `none` for a node whose grant holds none.
    tool_profile: Literal["none", "sutra", "github", "sutra+github"] = "none"
    slots: bool = False                       # SUTRA_NODES_SLOTS is on: the run takes a machine-wide slot for each model program it starts (MAN-12)
    tiers: list[int] = []                     # D380: the tiers of the frozen grant and its commands level: the host takes the builder tools of this node's calls down to them
    commands: str = "none"


class ProjectOut(Value):
    """A project as the page reads it (`GET /api/projects`): the row, with times as ISO text. `caps` is the cap table the project froze at plan time."""

    id: ProjectId
    request_id: Ident | None = None
    title: Name = ""
    status: ProjectStatus
    failure_policy: Literal["stop_branch", "stop_all"] = "stop_branch"
    decide_for_me: bool = False
    paused: bool = False
    review_loops: Count = 0
    caps: JsonObject = {}
    budget_credits: Count | None = None
    budget_usd: Seconds | None = None
    created_at: Iso
    ended_at: Iso | None = None
    stop_reason: Annotated[str, StringConstraints(max_length=200)] = ""


class SystemPermissionCard(Value):
    """A permission of the computer a step needs before it starts (MAN-15, D295): which one, what it is for, the plain steps for THIS system, and the two answers: check again (after the owner allowed
    it in the settings) or skip (the steps that need it are cancelled). Sutra changes no setting and Decide for me cannot answer it."""

    type: Literal["system_permission"] = "system_permission"
    project_id: ProjectId
    approval_id: ApprovalId
    item: Annotated[str, StringConstraints(max_length=40)]
    label: Annotated[str, StringConstraints(max_length=200)] = ""
    level: Literal["read", "write"] = "read"
    steps: Annotated[list[Annotated[str, StringConstraints(max_length=300)]], Field(max_length=8)]
    platform: Annotated[str, StringConstraints(max_length=20)] = ""
    options: Annotated[list[Annotated[str, StringConstraints(max_length=40)]], Field(max_length=4)] = ["check_again", "skip"]
    affects: Annotated[list[str], Field(max_length=20)] = []


class NodeOut(Value):
    """A runtime node as the page reads it. `grants` is the frozen grant (`grants.Grant.to_json()`), empty until the Gatekeeper has issued one."""

    id: AgentNodeId
    project_id: ProjectId
    task_id: TaskId | None = None
    role: NodeRole
    runtime: NodeRuntime
    plan_ref: Annotated[str, StringConstraints(max_length=200)] = ""
    title: Annotated[str, StringConstraints(max_length=200)] = ""          # the step's own title (its task's), so the page names a step by what it does (D383)
    calls: Count | None = None                                             # what the step used, every attempt counted (D395): model calls, dollars (None: no call priced) and minutes from its first start
    usd: Annotated[float, Field(ge=0)] | None = None
    minutes: Annotated[float, Field(ge=0)] | None = None
    depends_on: Annotated[list[AgentNodeId], Field(max_length=50)] = []
    state: AgentNodeState
    attempt: Annotated[int, Field(ge=1, le=10)] = 1
    grants: JsonObject = {}
    scope: ScopeList = []
    slice_credits: Count | None = None
    last_beat_at: Iso | None = None
    lease_expires_at: Iso | None = None
    failure_reason: Annotated[str, StringConstraints(max_length=200)] = ""
    created_at: Iso
    ended_at: Iso | None = None


# ---- the run document: task.json -----------------------------------------------------------------------------------

_INT_SETTING = re.compile(r"[1-9][0-9]{0,5}")


class TaskSettings(Value):
    """The eleven task keys a request may carry (D18, S1-contracts-03; J2 sync 4 added the Decide for me switch, J2 sync 6 the two run template keys, D182,
    D422 the dollar budget J2_USD_BUDGET), all text as J2
    reads its environment. `J2_RUN_TEMPLATE` and `J2_RUN_TEMPLATE_WORKFLOWS` are not engine settings: they name the run template this one request starts from and
    the workflows of it, and only the engine host reads them. A key left unset is left out of the dump. Anything else is refused (closed class), so a model reply or web request cannot reach live email,
    a Chrome path or a forced audit failure."""

    J2_OUTPUT: Annotated[str, StringConstraints(pattern=rf"^(auto|{OUTPUT_NAME_RE})$")] | None = None      # `auto` or a type name by shape (D166)
    J2_BUDGET: Annotated[str, StringConstraints(max_length=6)] | None = None
    J2_BUDGET_CAP: Annotated[str, StringConstraints(max_length=6)] | None = None
    J2_FIXES: Literal["0", "1"] | None = None
    J2_MEMORY: Literal["0", "1"] | None = None
    J2_SLIM: Literal["0", "1"] | None = None
    J2_RATES: Literal["0", "1"] | None = None
    J2_DECIDE_FOR_ME: Literal["0", "1"] | None = None
    J2_RUN_TEMPLATE: Annotated[str, StringConstraints(pattern=rf"^{RUN_TEMPLATE_ID_RE}$")] | None = None      # a run template's id (D182)
    J2_RUN_TEMPLATE_WORKFLOWS: Annotated[str, StringConstraints(max_length=RUN_TEMPLATE_WORKFLOWS_MAX)] | None = None      # `all` or a comma list of workflow keys
    J2_USD_BUDGET: Annotated[str, StringConstraints(max_length=10)] | None = None      # D422: dollars (API price), up to two decimals

    @field_validator("J2_RUN_TEMPLATE_WORKFLOWS")
    @classmethod
    def _workflow_keys(cls, value: str | None) -> str | None:
        if value is not None and run_template_keys(value) is None:
            raise ValueError("must be all, or a comma list of at most 40 workflow keys of at most 20 letters, digits, - _ or .")
        return value

    @field_validator("J2_BUDGET", "J2_BUDGET_CAP")
    @classmethod
    def _whole_number_in_range(cls, value: str | None) -> str | None:
        if value is not None and (not _INT_SETTING.fullmatch(value) or int(value) > 100_000):
            raise ValueError("must be a whole number from 1 to 100000")
        return value

    @field_validator("J2_USD_BUDGET")
    @classmethod
    def _dollars_in_range(cls, value: str | None) -> str | None:
        if value is not None and (not re.fullmatch(r"[0-9]{1,5}(\.[0-9]{1,2})?", value) or not 1 <= float(value) <= 10_000):
            raise ValueError("must be dollars from 1 to 10000, at most two decimals")
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
    words verbatim (Identity starts from them); `framing` is the chat agent's paragraph, context only. `node` is the optional identity block of a project's node (D283)."""

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
    node: NodeBlock | None = None            # who this run is inside a multi-agent project (D283): only for a node, and only while SUTRA_NODES_V1 is on

    @model_serializer(mode="wrap")
    def _no_node_unless_there_is_one(self, handler: Any) -> dict[str, Any]:
        """`task.json` is byte-identical to what it was before nodes existed whenever the run is not a node: the key is left out, not written as null."""
        data = handler(self)
        if data.get("node") is None:
            data.pop("node", None)
        return data


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

