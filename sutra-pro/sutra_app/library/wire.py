"""J2's wire documents as closed payload models (library design 2 and 10, work package L9, S2-models-14).

J2 writes some of these into a run folder (`map.json`, `artifacts.json`, `realization.json`, `summary.json`, `board.json`)
and serves the rest from `/api/*` (story, agent, artifacts tree). The J2 page reads every one of them, so the models
describe J2's keys exactly (D6) and the library checks them on `save()` through `gate_record` (`records.py`, L8):

    payload         J2 schema         where it comes from
    map             map/1             map.json, GET /api/map
    board           board/1           board.json, GET /api/board
    story           story/1           GET /api/story
    agent           agent/1           GET /api/agent
    artifacts       artifacts/1       artifacts.json
    artifacts_tree  artifacts-tree/1  GET /api/artifacts/tree
    realization     (no schema key)   realization.json: the whole planning record
    realization_plan realization/1    its `plan` object: the schema in docs/reference/j2/docs/realization-schema.json
    run_summary     (no schema key)   summary.json, with its budget `{start, granted, used, raises}` (S2-models-14)

Rules of this module:

* Every model is closed, strict and frozen (`Value`); a key J2 does not write is refused, so a renamed key is found by a
  test, not by a blank panel. Free-form model output (a reply, a plan's scores, a rubric) is a bounded JSON value.
* The J2 key `schema` is read as `schema_` with the alias `schema`, as `AtomView` does; `from` and `pass` are Python
  keywords, so `from_` and `pass_` carry those aliases (design rule 7). Nothing else is aliased.
* A document keeps the keys J2 wrote: `wire()` returns exactly the keys that were set when it was read, so the page gets
  J2's JSON back. A key J2 only writes in some situations (a node's `tab`, an entry's `impact`) is optional here.
* Where J2 derives one field from another by code, a validator re-derives it (counts, totals, `has_board`), so a
  document edited by hand or built by a bug fails at the gate.
* Real J2 output is the reference: `test_lib_wire.py` runs the vendored engine in mock mode and validates what it wrote.
"""
from typing import Annotated, Any, ClassVar, Final, Literal, Optional, Self, TypeVar, Union

from pydantic import Field, StringConstraints, model_validator

from .base import Value
from .chat import MetaValue
from .node import NodeState
from .registry import REGISTRY

__all__ = [
    "WIRE_PAYLOADS", "WIRE_FILES", "WIRE_SCHEMAS", "Wire", "Checks", "Source", "MapNode", "MapEdge", "MapDoc", "BoardEntry",
    "BoardDoc", "StoryDoc", "AgentDoc", "ArtifactRow", "ArtifactsDoc", "TreeItem", "ArtifactsTreeDoc", "RealizationPlan",
    "RealizationDoc", "SummaryBudget", "RunSummary",
]

T = TypeVar("T")

# ---- sizes: one place, rule 3 of the design (every str and list is bounded) ----------------------------------------------
Id = Annotated[str, StringConstraints(min_length=1, max_length=200)]                 # an id, a file name, a short key
Line = Annotated[str, StringConstraints(max_length=2_000)]                           # a label, a one-line detail
Text = Annotated[str, StringConstraints(max_length=100_000)]                         # a message, a brief, a section of prose
Big = Annotated[str, StringConstraints(max_length=300_000)]                          # a prompt or raw reply kept for "technical details"
Free = MetaValue                                                                     # free-form output of a model: any JSON value, 32 levels
Scalar = Union[Annotated[str, StringConstraints(max_length=100_000)], int, float, bool, None]
Count = Annotated[int, Field(ge=0)]
Seconds = Annotated[float, Field(ge=0)]
Score = Annotated[float, Field(ge=0, le=1)]


def seq(item: Any, limit: int = 1_000) -> Any:
    """`list[item]` of at most `limit` entries."""
    return Annotated[list[item], Field(max_length=limit)]


def table(item: Any, limit: int = 1_000) -> Any:
    """`dict[str, item]` of at most `limit` entries, with bounded keys."""
    return Annotated[dict[Id, item], Field(max_length=limit)]


FUNCS: Final = ("identity", "adaptation", "priority", "coordination", "audit")
FnName = Literal["identity", "adaptation", "priority", "coordination", "audit"]
RunStatus = Literal["done", "done_with_open_items", "stopped", "crashed"]


class Wire(Value):
    """Base of the wire documents. `SCHEMA` is J2's schema string, or None for a record J2 writes without one."""

    SCHEMA: ClassVar[Optional[str]] = None

    def wire(self) -> dict[str, Any]:
        """J2's JSON for this document: the keys that were set (so a document read from J2 comes back as J2 wrote it),
        with `schema` first when the document has one."""
        data = self.model_dump(mode="json", by_alias=True, exclude_unset=True, warnings=False)
        if self.SCHEMA is None:
            return data
        data.pop("schema", None)
        return {"schema": self.SCHEMA, **data}


class Checks(Value):
    """`{passed, run}`: how many of the checks that ran passed."""

    passed: Count
    run: Count

    @model_validator(mode="after")
    def _passed_is_within_run(self) -> Self:
        if self.passed > self.run:
            raise ValueError(f"{self.passed} checks passed but only {self.run} ran")
        return self


class Tokens(Value):
    """Tokens summed over a function's calls (a map box)."""

    input: Count
    output: Count


class CallTokens(Value):
    """Tokens of one AI call: J2 records None for the one the connector did not report."""

    input: Optional[Count] = None
    output: Optional[Count] = None


class Source(Value):
    """The record an edge or a placement was drawn from (map-schema.md, Edges): `{file, workflow, field, value}`."""

    file: Id
    workflow: Optional[Id] = None
    field: Optional[Id] = None
    value: Scalar = None


# ============================================ map/1 ===========================================================================

MapKind = Literal["person", "work", "engine", "function", "know"]
MapRow = Literal["people", "functions", "work", "knows"]
MapEdgeKind = Literal["handoff", "step", "speaks_to", "asks", "uses", "draws_on"]


class CallRange(Value):
    """The ids of the first and last AI call that made a document (documents.json)."""

    from_: Annotated[int, Field(ge=0)] = Field(alias="from")
    to: Annotated[int, Field(ge=0)]


class MadeBy(Value):
    """Which functions made a step: only where documents.json recorded the call range."""

    calls: CallRange
    functions: table(Count, 5)
    basis: Literal["recorded"]


class TeamReads(Value):
    """An artifact one of a team's workflows made and others of the same team read."""

    made_by: seq(Id, 200)
    read_by: seq(Id, 200)
    sources: seq(Source, 1_000)


class MapNode(Value):
    """One box of the Map. The keys depend on the kind (map-schema.md, Nodes): a function box has `tab`, `calls`, `seconds`
    and `tokens`; a work box has `note`, `output`, `send`, `lane` and `team_reads`; an engine box (a step) has `team`,
    `unchecked`, `made_by` and `persona`."""

    id: Id
    kind: MapKind
    row: MapRow
    label: Line
    status: NodeState
    version: Optional[int] = None
    detail: Optional[Text] = None
    file: Optional[Id] = None
    workflows: seq(Id, 500) = []
    tag: Optional[Id] = None
    color: Optional[Id] = None
    lane: Optional[Literal["trunk", "branch"]] = None
    # function boxes
    tab: Optional[Id] = None
    wait_on: Optional[Id] = None
    calls: Optional[Count] = None
    seconds: Optional[Seconds] = None
    tokens: Optional[Tokens] = None
    # work boxes
    note: Optional[Line] = None
    output: Optional[Line] = None
    send: Optional[Line] = None
    team_reads: Optional[TeamReads] = None
    # engine boxes
    team: Optional[Line] = None
    unchecked: Optional[seq(Id, 500)] = None
    made_by: Optional[MadeBy] = None
    persona: Optional[Line] = None

    @model_validator(mode="after")
    def _function_boxes_name_a_function(self) -> Self:
        if self.kind == "function" and self.id.removeprefix("fn:") not in FUNCS:
            raise ValueError(f"a function box is fn:<function>, not {self.id!r}")
        return self


class MapEdge(Value):
    """A line of the Map. No line without a record: `source` says where it was drawn from (map-schema.md, Edges)."""

    from_: Id = Field(alias="from")
    to: Id
    kind: MapEdgeKind
    label: Optional[Line] = None
    n: Optional[Count] = None
    basis: Literal["recorded"]
    source: Source
    sources: Optional[seq(Source, 1_000)] = None
    readers: Optional[seq(Id, 500)] = None


class MapWorkflow(Value):
    """One workflow of the Tree view's circle (presentation only)."""

    id: Id
    name: Line
    status: Optional[Id] = None
    box: Optional[Id] = None
    atoms: Optional[Literal["verify_failed", "open", "abandoned", "closed"]] = None
    checks: Checks
    reads: seq(Id, 500)
    out: seq(Id, 50)


class TeamNode(Value):
    """A workflow (`wf`) or an artifact or section (`artifact`) in a team's bipartite graph."""

    id: Id
    kind: Literal["wf", "artifact"]
    label: Line
    col: Count
    row: Count
    section: Optional[bool] = None
    file: Optional[Line] = None
    input: Optional[bool] = None
    from_team: Optional[seq(Line, 50)] = None


class TeamEdge(Value):
    from_: Id = Field(alias="from")
    to: Id
    kind: Literal["makes", "reads"]
    loop: bool
    via: Optional[seq(Id, 500)] = None


class Unresolved(Value):
    workflow: Id
    read: Scalar = None
    why: Line
    source: Source


class Team(Value):
    """The open-team view: one bipartite graph per team (j2_map.team_graphs)."""

    id: Id
    label: Line
    workflows: seq(Id, 500)
    columns: Count
    nodes: seq(TeamNode, 2_000)
    edges: seq(TeamEdge, 10_000)
    unresolved: seq(Unresolved, 2_000)
    cycles: seq(seq(Id, 500), 100)
    loops: seq(Id, 500)


class Slot(Value):
    section: Optional[Id] = None
    label: Optional[Line] = None
    builder: Id
    fixes: seq(Id, 500)
    empty: bool


class ConstellationFlow(Value):
    name: Line
    role: Literal["builder", "fix"]
    section: Optional[Id] = None
    rank: Count
    t: Optional[Id] = None
    ran: bool
    status: Optional[Id] = None
    output: bool
    reads: seq(Id, 500)


class ConstellationInput(Value):
    id: Id
    label: Line
    file: Optional[Line] = None
    section: bool
    team: Line


class Constellation(Value):
    id: Id
    label: Line
    slots: seq(Slot, 500)
    workflows: table(ConstellationFlow, 500)
    inputs: seq(ConstellationInput, 500)


class MapStatus(Value):
    state: Line
    state_status: NodeState
    checks: Checks


class LegendItem(Value):
    key: Id
    label: Line
    drawn: bool


class MapDoc(Wire):
    """map/1: the Map of a run (docs/map-schema.md). An empty map (a run that is not there) has no teams, constellations
    or workflows."""

    SCHEMA: ClassVar[Optional[str]] = "map/1"
    schema_: Literal["map/1"] = Field("map/1", alias="schema")
    run: Optional[Id] = None
    live: bool
    status: MapStatus
    nodes: seq(MapNode, 2_000)
    edges: seq(MapEdge, 20_000)
    legend: seq(LegendItem, 100)
    built_from: seq(Line, 20)
    not_recorded: seq(Line, 500)
    teams: seq(Team, 100) = []
    constellations: table(Constellation, 100) = {}
    workflows: seq(MapWorkflow, 500) = []

    @model_validator(mode="after")
    def _node_ids_are_unique(self) -> Self:
        seen, twice = set(), []
        for node in self.nodes:
            if node.id in seen:
                twice.append(node.id)
            seen.add(node.id)
        if twice:
            raise ValueError(f"node ids must be unique, these come twice: {', '.join(sorted(set(twice)))}")
        return self


# ============================================ board/1 and story/1 =============================================================

BoardStatus = Literal["open", "answered", "unanswered", "refused", "routed to Identity"]


class ArtifactUpdate(Value):
    """What an answer changed. A workflow's own section carries `body`; a document carries `doc`, `section` and the versions;
    a model's raw proposal may carry `text` and `why` (J2 `_board_doc_update`)."""

    doc: Optional[Id] = None
    section: Optional[Id] = None
    from_version: Optional[int] = None
    to_version: Optional[int] = None
    body: Optional[Text] = None
    text: Optional[Text] = None
    why: Optional[Text] = None
    reason: Optional[Text] = None


class AnsweredFrom(Value):
    """Where an answer came from: a function, or a workflow with the version of its output."""

    function: Optional[Id] = None
    workflow: Optional[Id] = None
    version: Optional[int] = None


class Impact(Value):
    atom: Id
    result: Literal["passed", "failed"]


class SentToIdentity(Value):
    doc: Id
    section: Id
    reason: Line


class BoardEntry(Value):
    """One question of the message board (j2_board.new_entry, then the fields the answer path adds)."""

    id: Id
    asked_by: Id
    atom: Optional[Id] = None
    to: Id
    about: Optional[Text] = None
    question: Text
    answer: Optional[Text] = None
    answered_by: Optional[Id] = None
    status: BoardStatus
    artifact_update: Optional[ArtifactUpdate] = None
    used_by: seq(Id, 500)
    cycle: Optional[int] = None
    attempt: Optional[int] = None
    asked_by_role: Literal["function", "builder"]
    answered_from: Optional[AnsweredFrom] = None
    impact: seq(Impact, 500)
    sent_to_identity: Optional[SentToIdentity] = None

    @model_validator(mode="after")
    def _status_matches_the_answer(self) -> Self:
        problems = []
        if self.status == "answered" and not (self.answer and self.answered_by):
            problems.append("an answered question carries the answer and who gave it")
        if self.status == "open" and (self.answer or self.answered_by):
            problems.append("an open question has no answer yet")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class BoardDoc(Wire):
    """board/1: a shared message board; `entries` in the order the questions were asked."""

    SCHEMA: ClassVar[Optional[str]] = "board/1"
    schema_: Literal["board/1"] = Field("board/1", alias="schema")
    entries: seq(BoardEntry, 1_000)

    @model_validator(mode="after")
    def _entry_ids_are_unique(self) -> Self:
        ids = [e.id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("board entry ids must be unique")
        return self


STORY_STEPS: Final = ("doubt", "ask", "answer", "change", "recheck")


class StoryAtom(Value):
    """An atom as the story shows it: its id, its name, where it sits. Everything the run did not record is None."""

    atom: Optional[Id] = None
    name: Optional[Line] = None
    workflow: Optional[Id] = None
    deliverable: Optional[Id] = None
    tag: Optional[Id] = None


class StoryDoubt(StoryAtom):
    role: Optional[Literal["function", "builder"]] = None
    asked_by: Optional[Id] = None


class StoryAsk(StoryAtom):
    about: Optional[Text] = None
    question: Optional[Text] = None


class StoryAnswer(Value):
    text: Optional[Text] = None
    by: Optional[Id] = None
    from_: Optional[AnsweredFrom] = Field(None, alias="from")
    updated_own_section: bool
    sent_to_identity: Optional[SentToIdentity] = None


class StoryChange(Value):
    doc: Id
    tag: Optional[Id] = None
    section: Optional[Id] = None
    from_version: Optional[int] = None
    to_version: Optional[int] = None


class StoryRecheck(Value):
    atoms: Count
    passed: Count
    failed: Count
    receipts: Count


class StoryImpact(StoryAtom):
    result: Optional[Id] = None


class StoryReuse(StoryAtom):
    id: Id


class StoryEntry(Value):
    id: Id
    status: Optional[BoardStatus] = None
    cycle: Optional[int] = None
    doubt: StoryDoubt
    ask: StoryAsk
    answer: StoryAnswer
    change: Optional[StoryChange] = None
    recheck: StoryRecheck
    impact: seq(StoryImpact, 500)
    reused_by: seq(StoryReuse, 500)

    @model_validator(mode="after")
    def _recheck_counts_the_impact(self) -> Self:
        r = self.recheck
        if r.atoms != len(self.impact) or r.passed + r.failed != r.atoms:
            raise ValueError("recheck counts must match impact: atoms = len(impact) = passed + failed")
        return self


class StoryNumbers(Value):
    questions: Count = 0
    rechecked: Count = 0
    receipts: Count = 0
    duplicate_edges: Count = 0


class StoryFacts(Value):
    run: Optional[Id] = None
    status: Optional[Text] = None
    cycles: Optional[int] = None
    versions: table(Optional[int], 50) = {}
    has_board: bool = False
    questions: Count = 0


class StoryFlags(Value):
    mock: Optional[bool] = None
    provider: Optional[Id] = None
    model: Optional[Id] = None
    force_question: Optional[Id] = None


class StoryDoc(Wire):
    """story/1: what each message-board question did, step by step, read from what the run recorded. A run with no board
    has `has_board: false` and no entries; a run that is not there has `run: null` and `facts` and `flags` empty."""

    SCHEMA: ClassVar[Optional[str]] = "story/1"
    schema_: Literal["story/1"] = Field("story/1", alias="schema")
    run: Optional[Id] = None
    has_board: bool
    entries: seq(StoryEntry, 1_000)
    numbers: StoryNumbers
    facts: StoryFacts
    flags: StoryFlags
    steps: seq(Id, 10)
    not_recorded: seq(Line, 100)

    @model_validator(mode="after")
    def _derived_fields_agree(self) -> Self:
        problems = []
        if self.has_board != bool(self.entries):
            problems.append("has_board is true exactly when there are entries")
        if self.numbers.questions != len(self.entries):
            problems.append("numbers.questions is the number of entries")
        if self.numbers.rechecked != sum(e.recheck.atoms for e in self.entries):
            problems.append("numbers.rechecked adds up the entries' rechecked atoms")
        if self.steps != list(STORY_STEPS):
            problems.append(f"steps are {', '.join(STORY_STEPS)}, in that order")
        if problems:
            raise ValueError("; ".join(problems))
        return self


# ============================================ agent/1 =========================================================================

Pair = Annotated[list[Text], Field(min_length=2, max_length=2)]         # [name, text]


class AgentMessage(Value):
    """One chat line a function sent or received (`sent` tells which)."""

    id: Annotated[int, Field(ge=1)]
    t: Optional[Id] = None
    step: Union[int, Id, None] = None
    from_: Id = Field(alias="from")
    to: seq(Id, 20)
    text: Text
    sent: bool


class AgentTalk(Value):
    """The conversation with one counterpart (`with` is None for lines posted with no one named)."""

    with_: Optional[Id] = Field(alias="with")
    count: Count
    messages: seq(AgentMessage, 5_000)

    @model_validator(mode="after")
    def _count_is_the_messages(self) -> Self:
        if self.count != len(self.messages):
            raise ValueError(f"count is {self.count} but the conversation holds {len(self.messages)} messages")
        return self


class AgentReply(Value):
    """A reply as sentences and labelled lines (j2_agent._reply)."""

    text: seq(Text, 20)
    fields: seq(Pair, 200)
    reason: Optional[Text] = None
    note: Optional[Line] = None


class Technical(Value):
    """Prompt, system text and raw output, each cut to 40,000 characters (j2_agent.TECH_MAX)."""

    system: Annotated[str, StringConstraints(max_length=40_000)]
    prompt: Annotated[str, StringConstraints(max_length=40_000)]
    raw: Annotated[str, StringConstraints(max_length=40_000)]


class AgentCall(Value):
    """One AI call as a card: what the agent was given, its stated reason, its reply."""

    id: Optional[int] = None
    step: Union[int, Id, None] = None
    cycle: Optional[int] = None
    t: Optional[Id] = None
    seconds: Optional[Seconds] = None
    model: Optional[Id] = None
    tokens: Optional[CallTokens] = None
    atom: Optional[Id] = None
    given: seq(Pair, 200)
    reason: Optional[Text] = None
    reply: AgentReply
    technical: Technical


class AgentMost(Value):
    with_: Optional[Id] = Field(alias="with")
    count: Count


class AgentSummary(Value):
    calls: Count
    seconds: Seconds
    models: seq(Id, 50)
    tokens: Tokens
    messages: Count
    most: Optional[AgentMost] = None


class AgentDoc(Wire):
    """agent/1: who one agent (a function id or a workflow id) talked to and how it decided. For a run that is not there, or
    an empty `who`, J2 answers `{schema, who, found: false}` and nothing else; for an agent the run never heard of the
    parts are there and empty."""

    SCHEMA: ClassVar[Optional[str]] = "agent/1"
    schema_: Literal["agent/1"] = Field("agent/1", alias="schema")
    who: Annotated[str, StringConstraints(max_length=200)]
    found: bool
    names: Optional[table(Optional[Line], 1_000)] = None
    summary: Optional[AgentSummary] = None
    conversations: Optional[seq(AgentTalk, 200)] = None
    thinking: Optional[seq(AgentCall, 2_000)] = None

    @model_validator(mode="after")
    def _the_parts_come_together(self) -> Self:
        parts = (self.names, self.summary, self.conversations, self.thinking)
        if all(p is None for p in parts):
            if self.found:
                raise ValueError("a found agent carries names, summary, conversations and thinking")
            return self
        if any(p is None for p in parts):
            raise ValueError("names, summary, conversations and thinking come together or not at all")
        if self.summary.calls != len(self.thinking):
            raise ValueError(f"summary.calls is {self.summary.calls} but there are {len(self.thinking)} call cards")
        if self.found != bool(self.thinking or self.conversations):
            raise ValueError("found is true exactly when the agent made a call or took part in a conversation")
        return self


# ============================================ artifacts/1 and artifacts-tree/1 ================================================

class ReusedFrom(Value):
    """A section this run served from an earlier run (the content door, J2_ARTIFACT_LIBRARY=1; j2_artifacts.rows, from reuse.json):
    the workflow that owns it here, its section, the source run and the source's workflow and run template key."""

    workflow: Id
    section: Optional[Id] = None
    run: Optional[Id] = None
    source_workflow: Optional[Id] = None
    key: Optional[Id] = None


class ArtifactRow(Value):
    """One thing the run made, a deliverable (`kind` type) or a record (j2_artifacts.rows)."""

    name: Line
    type: Id
    kind: Literal["type", "record"]
    form: Id
    file: Id
    deliverable: bool
    workflows: seq(Id, 500)
    depends_on: seq(Id, 50)
    version: Optional[int] = None
    changed_by: Optional[seq(Id, 500)] = None
    rechecked_after: Optional[seq(Id, 500)] = None
    sha256: Optional[Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]] = None
    time: Optional[Id] = None
    reused_from: Optional[seq(ReusedFrom, 500)] = None          # the content door only: absent on every other run


class ArtifactsDoc(Wire):
    """artifacts/1: what a run made (artifacts.json). A deliverable depends only on deliverable types that were built."""

    SCHEMA: ClassVar[Optional[str]] = "artifacts/1"
    schema_: Literal["artifacts/1"] = Field("artifacts/1", alias="schema")
    rows: seq(ArtifactRow, 2_000)

    @model_validator(mode="after")
    def _depends_on_what_was_built(self) -> Self:
        built = {r.type for r in self.rows}
        for r in self.rows:
            missing = [d for d in r.depends_on if d not in built]
            if missing:
                raise ValueError(f"{r.name} depends on {', '.join(missing)}, which this run did not build")
        return self


class TreeMaker(Value):
    """Who made an artifact: a function (`function`), or a team of workflows (`persona`, `workflows`)."""

    function: Optional[Line] = None
    persona: Optional[Line] = None
    workflows: Optional[seq(Id, 500)] = None


class TreeCode(Value):
    deck: Id
    section: Optional[Id] = None


class TreeRewrite(Value):
    by: Id
    name: Line


class TreeItem(Value):
    """A row of the Artifacts tree: a file, or a folder of rows (`children`, with a `count`). Group rows such as
    "Sections" carry only a name, a count and their children."""

    name: Line
    file: Optional[Id] = None
    made_by: Optional[TreeMaker] = None
    status: Optional[Line] = None
    size: Optional[Count] = None
    open: Optional[Id] = None
    note: Optional[Line] = None
    version: Optional[int] = None
    node: Optional[Id] = None
    workflows: Optional[Count] = None
    read_by: Optional[Count] = None
    output: Optional[Line] = None
    code: Optional[TreeCode] = None
    section: Optional[Id] = None
    rewritten: Optional[TreeRewrite] = None
    count: Optional[Count] = None
    collapsed: Optional[bool] = None
    shots: Optional[bool] = None
    children: Optional[seq("TreeItem", 2_000)] = None


TreeItem.model_rebuild()


class TreeGroup(Value):
    id: Literal["plan", "specs", "deliverables", "proof"]
    label: Line
    count: Count
    collapsed: bool
    items: seq(TreeItem, 2_000)

    @model_validator(mode="after")
    def _count_is_the_items(self) -> Self:
        if self.count != len(self.items):
            raise ValueError(f"count is {self.count} but the group holds {len(self.items)} items")
        return self


class ArtifactsTreeDoc(Wire):
    """artifacts-tree/1: the Artifacts tab as a tree in four groups (plan, specs, deliverables, proof), or no group for a
    run that is not there."""

    SCHEMA: ClassVar[Optional[str]] = "artifacts-tree/1"
    schema_: Literal["artifacts-tree/1"] = Field("artifacts-tree/1", alias="schema")
    groups: seq(TreeGroup, 4)

    @model_validator(mode="after")
    def _groups_are_distinct(self) -> Self:
        ids = [g.id for g in self.groups]
        if len(ids) != len(set(ids)):
            raise ValueError("a group may come only once")
        return self


# ============================================ realization.json and realization/1 ==============================================

Zone = Literal["operate", "analyze", "experiment", "stabilize"]
Stage = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]
Tier = Literal["strategy", "capability", "architecture", "feature", "contract", "implementation"]
Research = Annotated[str, StringConstraints(pattern=r"^research\.md#R-[0-9]{1,6}$")]
Item = Annotated[int, Field(ge=1)]


class PlanFactor(Value):
    """A factor of the plan: where it comes from decides what it must carry (realization-schema.json, allOf)."""

    name: Id
    source: Literal["brief", "general", "research", "budget"]
    quote: Optional[Text] = None
    citation: Optional[Research] = None
    why: Text
    stages: seq(Stage, 35) = []

    @model_validator(mode="after")
    def _source_rules(self) -> Self:
        problems = []
        if self.source == "brief" and not (self.quote or "").strip():
            problems.append("a factor from the brief quotes the brief: quote must not be empty")
        if self.source == "research" and not self.citation:
            problems.append("a research factor cites a research entry such as research.md#R-1")
        if self.source == "budget" and self.stages:
            problems.append("a budget factor belongs to no stage: stages must be empty")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class PlanUnplaced(Value):
    name: Id
    why: Text


class PlanStageRow(Value):
    id: Stage
    thinking: Text
    tiers: Annotated[list[Tier], Field(min_length=1, max_length=6)]
    goal: Text
    done_test: Text
    method: Optional[Text] = None
    owns_factors: seq(Id, 100) = []
    inputs_from: seq(Stage, 35) = []


class PlanExperiment(Value):
    hypothesis: Text
    signal: Text
    fails_if: Text
    limit: Text


class PlanResearch(Value):
    question: Text
    feeds: Text
    min_sources: Annotated[int, Field(ge=3)]
    output: Research


class PlanWorkflow(Value):
    name: Id
    stage: Stage
    certainty: Zone
    certainty_signals: seq(Text, 20) = []
    approach: Text = ""
    goal: Text
    done_test: Text
    delivers: seq(Item, 100)
    informs: seq(Item, 100)
    inputs_from: seq(Id, 100)
    hold: Optional[Literal["waiting_on_identity", "waiting_on_dependency"]] = None
    experiment: Optional[PlanExperiment] = None
    research: Optional[PlanResearch] = None

    @model_validator(mode="after")
    def _research_workflows_deliver_nothing(self) -> Self:
        if self.research is not None:
            if self.delivers:
                raise ValueError("a research workflow finds sources and delivers no done-when item")
            if self.stage == "build":
                raise ValueError("a research workflow is not in the build stage")
        return self


class PlanOpenFact(Value):
    fact: Text
    workflow: Id
    blocking: bool
    handling: Text = ""


class PlanNotReady(Value):
    workflow: Id
    score: Score
    weakest: Literal["inputs", "method", "done_test", "factors", "zone_fit", "size"]
    stop_reason: Text
    route: Literal["identity", "priority", "left_out"]


class PlanAnalysis(Value):
    options: seq(Free, 20) = []
    chosen: Text = ""
    why: Text = ""
    assumptions: seq(Text, 50) = []


class PlanSignal(Value):
    answer: Literal["yes", "no", "unknown"]
    evidence: Text = ""


class PlanSignals(Value):
    broken: PlanSignal
    reaction: PlanSignal
    facts_given: PlanSignal
    known_pattern: PlanSignal
    open_choices: PlanSignal


class PlanCertainty(Value):
    zone: Zone
    signals: PlanSignals
    rationale: Text = ""


class PlanChange(Value):
    workflow: Id
    weakest: Optional[Id] = None
    remedy: Optional[Text] = None
    axis: Optional[Id] = None


class PlanDeferred(Value):
    item: Text
    until: Text


class RealizationPlan(Wire):
    """realization/1: the plan Adaptation makes by stage and certainty (docs/reference/j2/docs/realization-schema.json),
    the `plan` of a realization.json. J2 sends a plan with faults back once, so an empty list is not refused here:
    `plan_faults` of the record says what is wrong."""

    factors: seq(PlanFactor, 100)
    unplaced: seq(PlanUnplaced, 100)
    stages: seq(PlanStageRow, 35)
    workflows: seq(PlanWorkflow, 200)
    open_facts: seq(PlanOpenFact, 100)
    not_ready: seq(PlanNotReady, 100) = []
    analysis: Optional[PlanAnalysis] = None
    certainty_assessment: Optional[PlanCertainty] = None
    changes: seq(PlanChange, 100) = []
    deferred: seq(PlanDeferred, 100) = []

    @model_validator(mode="after")
    def _names_are_unique_and_inputs_exist(self) -> Self:
        names = [w.name for w in self.workflows]
        problems = []
        if len(names) != len(set(names)):
            problems.append("workflow names must be unique")
        known = set(names)
        for w in self.workflows:
            gone = [n for n in w.inputs_from if n not in known]
            if gone:
                problems.append(f"workflow {w.name} reads {', '.join(gone)}, which the plan does not have")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class PlanScore(Value):
    """The confidence judge's mark for one workflow."""

    score: Score
    weakest: Optional[Id] = None
    capped: bool
    checks: table(Id, 20)
    missing: seq(Text, 50)
    failed: seq(Text, 50)
    compare: Optional[Id] = None


class PlanRound(Value):
    round: Count
    plan: RealizationPlan
    plan_faults: seq(Text, 200)
    changes: seq(PlanChange, 100)
    scores: Optional[table(PlanScore, 200)] = None
    judge_faults: Optional[seq(Free, 100)] = None


class StageConfidence(Value):
    confidence: Score
    zone: Zone


class WaitingOnIdentity(Value):
    workflow: Id
    score: Optional[Score] = None
    ask: seq(Optional[Text], 50)


class LateEntry(Value):
    """One judgement of a workflow proposed after the first plan (J2 `_late_judge`: a fix, a replacement, a change's relay round),
    kept in realization.json under `late`. J2 writes all fourteen keys every time: the workflow, what it revises, the time, the
    cycle, the calls and seconds the judging took, and the judge's own mark (score, weakest check, up to three missing items, the
    score of each round, ready, zone, stage); a judge that could not be reached leaves `score` empty and says why in `note`."""

    workflow: Id
    revises: Optional[Id] = None
    t: Text
    cycle: Count
    calls: Count
    seconds: Seconds
    score: Optional[Score] = None
    weakest: Optional[Text] = None
    missing: seq(Text, 3) = []
    rounds: seq(Score, 5) = []
    ready: Optional[bool] = None
    zone: Optional[Text] = None
    stage: Optional[Text] = None
    note: Optional[Text] = None


class RealizationDoc(Wire):
    """realization.json: the whole planning record of a run (j2_realization.plan_goal)."""

    goal: Optional[Text] = None
    web: bool
    provider: Optional[Id] = None
    model: Optional[Id] = None
    mock: bool
    checklist: seq(Free, 200)
    plan: RealizationPlan
    scores: table(PlanScore, 200)
    history: table(seq(Score, 20), 200)
    rounds: Annotated[list[PlanRound], Field(min_length=1, max_length=20)]
    not_ready: seq(PlanNotReady, 200)
    held: table(Literal["waiting_on_identity", "not_ready", "waiting_on_dependency"], 200)
    waiting_on_identity: seq(WaitingOnIdentity, 200)
    stages: table(StageConfidence, 35)
    plan_confidence: Score
    plan_faults: seq(Text, 200)
    calls: Count
    seconds: Seconds
    late: seq(LateEntry, 200) = []      # J2 sync 4 (D145): the late judge's entries; a run that never judged one late leaves the key out

    @model_validator(mode="after")
    def _the_record_agrees_with_its_last_round(self) -> Self:
        problems = []
        if [r.round for r in self.rounds] != list(range(len(self.rounds))):
            problems.append("rounds are numbered 0, 1, 2, ... in order")
        elif self.rounds[-1].plan_faults != self.plan_faults:
            problems.append("plan_faults is the last round's plan_faults")
        names = {w.name for w in self.plan.workflows}
        gone = sorted(n for n in self.scores if n not in names)
        if gone:
            problems.append(f"scores for workflows the plan does not have: {', '.join(gone)}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


# ============================================ summary.json ====================================================================

class SummaryRaise(Value):
    """A budget raise the Requester granted (J2 `raises`)."""

    cycle: Optional[int] = None
    asked: int
    from_: int = Field(alias="from")
    to: int
    why: Optional[Text] = None


class SummaryBudget(Value):
    """The budget of a run, read from summary.json (S2-models-14): what it started with, what is granted now, what is used,
    and each raise. This is the department's budget: Department itself holds none."""

    start: Count
    granted: Count
    used: Count
    raises: seq(SummaryRaise, 100)

    @model_validator(mode="after")
    def _granted_follows_the_raises(self) -> Self:
        problems = []
        if self.granted < self.start:
            problems.append(f"granted {self.granted} is below the start {self.start}")
        if any(r.to <= r.from_ for r in self.raises):
            problems.append("a raise goes up: to is above from")
        if self.raises and self.raises[-1].to != self.granted:
            problems.append(f"the last raise ends at {self.raises[-1].to} but {self.granted} is granted")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class SummarySection(Value):
    heading: Line
    words: Count


class ConditionTally(Value):
    """`conditions` and `necessary_conditions`: how many are met, the warnings, and the list."""

    met: Count
    total: Count
    warnings: Count
    list: seq(Free, 200)

    @model_validator(mode="after")
    def _tally_matches_the_list(self) -> Self:
        rows = [r for r in self.list if isinstance(r, dict)]
        if self.total != len(self.list) or self.met != sum(r.get("met") is True for r in rows):
            raise ValueError("total is the length of the list and met is the number of entries that are met")
        return self


class SummaryExport(Value):
    file: Id
    written: bool
    note: Optional[Text] = None


class SummaryConflict(Value):
    id: Id
    pair: seq(Id, 4)
    topic: Id
    subject: Line
    attempts: Count
    escalated: bool
    resolved_by: Optional[Id] = None
    repriced: bool
    user_question: Optional[Text] = None
    user_answer: Optional[Free] = None
    outcome: Optional[Text] = None


class SummaryRejection(Value):
    cycle: Optional[int] = None
    workflow: Line
    reason: Text


class SummaryHold(Value):
    cycle: Optional[int] = None
    by: Id
    detail: Text


class SummaryVerdict(Value):
    id: Optional[Id] = None
    item: Scalar = None             # a done-when number, or the id of a rubric or extra-issue row
    verdict: Optional[Id] = None


class SummaryAudit(Value):
    cycle: Optional[int] = None
    version: Optional[int] = None
    all_pass: bool
    verdicts: seq(SummaryVerdict, 500)


class SummaryAgent(Value):
    id: Id
    agent: Optional[Line] = None
    section: Optional[Id] = None
    revises: Optional[Id] = None
    status: Id
    calls: Count
    retries: Count


class SummaryVerification(Value):
    passed: Count
    failed: Count
    escalated: Count
    could_not_run: Count
    checks_run: Count


class SummaryRulings(Value):
    grant: Count
    counter: Count
    refuse: Count


class SummaryMemory(Value):
    memory: Optional[bool] = None
    saved: seq(Id, 200) = []
    used: Free = []


class SummaryPlaybooks(Value):
    saved: Free = None
    used: Free = []


class SummaryRubric(Value):
    id: Id
    pass_: Optional[bool] = Field(alias="pass")
    verdict: Id


class SummaryDoneWhen(Value):
    item: Optional[Scalar] = None
    criterion: Text
    pass_: Optional[bool] = Field(alias="pass")


class SummaryRouteViolation(Value):
    agent: Id
    detail: Text
    msg: Optional[int] = None
    cycle: Optional[int] = None


class SummaryRealization(Value):
    """`realization`: whether the plan was applied, then what the planning kept (j2.real_summary)."""

    applied: bool
    plan_confidence: Optional[Score] = None
    stages: seq(Id, 35) = []
    workflows: Optional[Count] = None
    rounds: Optional[Count] = None
    plan_faults: seq(Text, 200) = []
    waiting_on_identity: seq(Free, 200) = []
    not_ready: seq(Free, 200) = []
    calls: Optional[Count] = None
    seconds: Optional[Seconds] = None
    proposal_brief: seq(Free, 200) = []
    left_out: seq(Free, 200) = []
    proposed: Optional[Free] = None


class SummaryDocuments(Value):
    requested: seq(Id, 10)
    stages: seq(Id, 10)
    files: table(Line, 10)
    chain: Free = None
    lld_revisions: Free = None
    lld_compare: Free = None


class RunSummary(Wire):
    """summary.json: how a run ended, written by code when it ends (j2._write_summary). It has no `schema` key."""

    run: Id
    output_type: Id
    j2_fixes: Count
    realization: Optional[SummaryRealization] = None
    design_documents: Optional[SummaryDocuments] = None
    provider: Optional[Id] = None
    sections: seq(Union[SummarySection, Id], 500)
    conditions: Optional[ConditionTally] = None
    necessary_conditions: Optional[ConditionTally] = None
    export: Optional[SummaryExport] = None
    force_audit_fail: Free = None
    test_lessons: Free = False
    force_question: Optional[Id] = None
    has_board: bool
    model: Optional[Id] = None
    mock: bool
    brief: Text
    change_requests: seq(Text, 200)
    status: RunStatus
    outcome: Text
    budget: SummaryBudget
    ai_calls: Count
    cycles: Count
    links: table(Count, 500)
    verification: SummaryVerification
    identity_to_requester_decisions: Count
    identity_to_requester_facts: Count
    priority_rulings: SummaryRulings
    questions_to_user: seq(Free, 200)
    conflicts: seq(SummaryConflict, 500)
    validator_rejections: seq(SummaryRejection, 1_000)
    holds: seq(SummaryHold, 500)
    audits: seq(SummaryAudit, 200)
    site_versions: Count
    workable: Optional[seq(Text, 200)] = None
    to_be_confirmed: seq(Free, 200)
    dropped_by_requester: seq(Free, 200)
    workflow_agents: seq(SummaryAgent, 500)
    limits_hit: seq(Text, 200)
    milestone_emails: Optional[seq(Free, 100)] = None
    lessons: SummaryMemory
    playbooks: SummaryPlaybooks
    business_type: Optional[Id] = None
    style_guide: bool
    rubric: seq(SummaryRubric, 200)
    done_when: seq(SummaryDoneWhen, 200)
    route_check_violations: seq(SummaryRouteViolation, 500)

    @model_validator(mode="after")
    def _status_and_outcome_agree(self) -> Self:
        words = {"done": "Done", "done_with_open_items": "Done with open items", "crashed": "Crashed"}
        word = words.get(self.status)
        if word is None:
            if self.outcome.startswith(("Done", "Crashed")):
                raise ValueError(f"status {self.status} but the outcome says {self.outcome[:20]!r}")
        elif not self.outcome.startswith(word):
            raise ValueError(f"status {self.status} but the outcome does not start with {word!r}")
        return self


# ============================================ registration ====================================================================

WIRE_PAYLOADS: Final[dict[str, type]] = {
    "map": MapDoc, "board": BoardDoc, "story": StoryDoc, "agent": AgentDoc, "artifacts": ArtifactsDoc,
    "artifacts_tree": ArtifactsTreeDoc, "realization": RealizationDoc, "realization_plan": RealizationPlan,
    "run_summary": RunSummary,
}
WIRE_FILES: Final[dict[str, str]] = {      # the run-folder files of this module, for the record catalogue (records.py)
    "map.json": "map", "board.json": "board", "artifacts.json": "artifacts", "realization.json": "realization",
    "summary.json": "run_summary",
}
WIRE_SCHEMAS: Final[dict[str, str]] = {    # J2's `schema` string => the payload name
    "map/1": "map", "board/1": "board", "story/1": "story", "agent/1": "agent", "artifacts/1": "artifacts",
    "artifacts-tree/1": "artifacts_tree", "realization/1": "realization_plan",
}

for _name, _cls in WIRE_PAYLOADS.items():
    REGISTRY.register_payload(_name, 1, _cls)
