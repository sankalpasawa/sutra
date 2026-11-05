"""The workflow graph's nodes and edges, the function-spec plug-in and the hand-off table (library design section 8).

    Node (family "node")   abstract base: id, label, department_id, state (J2's nine map/1 words), detail, version,
                           chat_session_id, edge_ids, timestamps
      StructuralNode       kinds root, department, division, step: the nodes that mirror the chart, and task steps
      FunctionNode         abstract: goal, task, context, open_atom, atom_count, wait_on, stats, spec_version
        IdentityNode AdaptationNode PriorityNode CoordinationNode AuditNode      (one kind each; ids `<dept>.<function>`)
    GraphEdge (family "edge")   seven kinds; handoff, step, speaks_to and depends_on are stored (each with a `source`),
                           contains, has_function and has_step are derived on read (`derive_edges`)
    HANDOFFS               who may hand the turn to whom (J2's ROUTES as changed by S3-web-04)
    check_graph            proves the graph mirrors the chart (rules G1 to G5)
    FunctionSpec(s)        the function-node design as DATA: standing sentences, task kinds, atom templates with named
                           checks; `load_function_specs` reads the file L10 ships, `new_function_node` makes a node from
                           a spec and `refresh_function_nodes` brings nodes up to a newer spec version

A graph node's goal, task, context and spec_version come from the spec when the node is made (and are refreshed at start
when the spec version rises); state, detail, wait_on and stats come from node events. This module is pure: it reads no
clock (callers pass `now`) and its one file read is the spec loader.

Importing this module binds `REGISTRY.bind_function_specs(load_function_specs)` and `REGISTRY.bind_check_arity`, so that
`REGISTRY.verify_refs()` judges every task kind's reply references and every template check name and argument count.

Violation codes of `check_graph`: G1 (a chart node and its graph node disagree, or a graph node is not in the chart),
G2 (a department's five function nodes), G3 (a node names a missing department), G4 (edge endpoints and the derived
`contains` / `has_function` / `has_step` edges), G5 (`edge_ids` against the stored edges). Paths: `nodes.<id>`,
`nodes.<id>.edge_ids`, `edges.<id>`.
"""
import hashlib
import json
import re
import string
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, ClassVar, Final, Literal, NoReturn, Self

from pydantic import Field, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from .atom import CheckTemplate, Work, check_arity
from .base import Record, Value
from .org_chart import OrgChart
from .registry import REGISTRY, record
from .types import (
    FUNCTIONS, AtomId, EdgeId, FunctionName, NodeId, Ts, Violation, clip, function_node_id, violation,
    violations_from_validation_error,
)

__all__ = [
    "GraphNodeId", "NodeState", "FUNCTION_STATES", "STRUCTURE_STATES", "EdgeKind", "EdgeStatus", "STORED_EDGE_KINDS",
    "DERIVED_EDGE_KINDS", "STEP_REFS", "Node", "StructuralNode", "NodeTokens", "NodeStats", "FunctionNode",
    "IdentityNode", "AdaptationNode", "PriorityNode", "CoordinationNode", "AuditNode", "FUNCTION_NODE_CLASSES",
    "step_node_id", "EdgeSource", "GraphEdge", "edge_id", "make_edge", "HANDOFFS", "WORKFLOW_AGENT_HANDOFFS", "hands_to",
    "may_hand_off", "derive_edges", "check_graph", "ALLOWED_GOAL_FIELDS", "TaskKind", "CheckRef", "AtomTemplate",
    "FunctionSpec", "FunctionSpecs", "FunctionSpecsError", "DEFAULT_SPECS_PATH", "MAX_SPECS_BYTES",
    "load_function_specs", "new_function_node", "refresh_function_nodes",
]

Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

# An id of the graph: a chart id (`sales`), a function node id (`sales.identity`) or a step id (`s-` + 10 hex digits).
# The suffix after the dot is bounded (the longest function name has 12 letters) so the pattern has a finite width.
GraphNodeId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{1,39}(\.[a-z]{1,16})?$", max_length=60)]
EdgeEnd = Annotated[str, StringConstraints(pattern=r"^[^>\s]{1,80}$")]
Label = Annotated[str, StringConstraints(min_length=1, max_length=80)]
Detail = Annotated[str, StringConstraints(max_length=300)]
Session = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Revision = Annotated[int, Field(ge=1)]
Count = Annotated[int, Field(ge=0)]

NodeState = Literal["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"]
FUNCTION_STATES: Final = ("idle", "running", "waiting", "waiting_on_you", "fault")      # the first five (S2-models-03)
STRUCTURE_STATES: Final = ("idle", "running", "waiting_on_you", "fault")                 # root, department, division
STEP_REF_RE: Final = re.compile(r"^(task|W-[0-9]+|team:[A-Za-z0-9][A-Za-z0-9 _.-]{0,33})$")
STEP_ID_RE: Final = re.compile(r"^s-[0-9a-f]{10}$")
STEP_REFS: Final = "'task', 'W-<n>' or 'team:<role>'"
_FUNCTION_ID_RE: Final = re.compile(r"^([a-z][a-z0-9_-]{1,39})\.(" + "|".join(FUNCTIONS) + r")$")


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error per problem, each at its own place (one ValueError could report only one)."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)}) for loc, text in problems])


# ---- nodes -------------------------------------------------------------------------------------------------------

@record
class Node(Record):
    """The abstract base of a graph node. `edge_ids` lists the STORED edges that touch the node; the tree edges are
    derived. `version` is the store's optimistic counter. A subclass adds its rules by extending `_problems`."""

    FAMILY = "node"
    ABSTRACT = True
    kind: str
    id: GraphNodeId
    label: Label
    department_id: NodeId | None = None
    state: NodeState = "idle"
    detail: Detail = ""
    version: Revision = 1
    chat_session_id: Session | None = None
    edge_ids: Annotated[list[EdgeId], Field(max_length=200)] = []
    ts_created: Ts = 0
    ts_updated: Ts = 0

    def _problems(self) -> list[Problem]:
        out: list[Problem] = []
        seen: set[str] = set()
        for index, edge_id_ in enumerate(self.edge_ids):
            if edge_id_ in seen:
                out.append((("edge_ids", index), f"edge id {edge_id_!r} is listed twice"))
            seen.add(edge_id_)
        return out

    @model_validator(mode="after")
    def _node_rules(self) -> Self:
        problems = self._problems()
        if problems:
            _raise(type(self).__name__, problems)
        return self


def step_node_id(task_id: str, step_ref: str) -> str:
    """The id of a step node: `s-` and the first 10 hex digits of sha1("<task_id>:<step_ref>") (design 8.1)."""
    if not isinstance(task_id, str) or not task_id or not isinstance(step_ref, str) or not step_ref:
        raise ValueError("a step id needs a task id and a step ref")
    return "s-" + hashlib.sha1(f"{task_id}:{step_ref}".encode("utf-8"), usedforsecurity=False).hexdigest()[:10]


@record
class StructuralNode(Node):
    """A node that mirrors the chart (root, department, division) or one step of a task (`task_id` + `step_ref`).
    A chart node uses four states; a step uses all nine."""

    kind: Literal["root", "department", "division", "step"]
    parent_id: NodeId | None = None
    task_id: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None = None
    step_ref: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None

    def _problems(self) -> list[Problem]:
        out = super()._problems()
        if self.kind == "step":
            if self.task_id is None:
                out.append((("task_id",), "a step node needs a task_id"))
            if self.step_ref is None:
                out.append((("step_ref",), "a step node needs a step_ref"))
            elif not STEP_REF_RE.fullmatch(self.step_ref):
                out.append((("step_ref",), f"a step_ref is {STEP_REFS}, not {clip(self.step_ref, 60)!r}"))
            if not STEP_ID_RE.fullmatch(self.id):
                out.append((("id",), f"a step node id is 's-' and 10 hex digits (step_node_id), not {self.id!r}"))
        else:
            if self.task_id is not None:
                out.append((("task_id",), f"a {self.kind} node has no task_id"))
            if self.step_ref is not None:
                out.append((("step_ref",), f"a {self.kind} node has no step_ref"))
            if self.state not in STRUCTURE_STATES:
                out.append((("state",), f"a {self.kind} node uses one of {', '.join(STRUCTURE_STATES)}, not {self.state!r}"))
        return out


class NodeTokens(Value):
    """Tokens a node's calls used."""

    input: Count = 0
    output: Count = 0


class NodeStats(Value):
    """What a function node has used so far (from its node events)."""

    calls: Count = 0
    seconds: Annotated[float, Field(ge=0)] = 0.0
    tokens: NodeTokens = Field(default_factory=NodeTokens)


@record
class FunctionNode(Node):
    """The agentic node of one function. `goal` is the standing sentence of the spec, `task` its standing TASK line,
    `context` the names of the slice it reads; the live unit of work is the department's task and the open atom. The
    atoms table is the list of work atoms: a node holds only its `open_atom` and an `atom_count`."""

    ABSTRACT = True
    FUNCTION: ClassVar[str]
    goal: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    task: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    context: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=200)]], Field(max_length=40)] = []
    open_atom: AtomId | None = None
    atom_count: Count = 0
    wait_on: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    stats: NodeStats = Field(default_factory=NodeStats)
    spec_version: Revision = 1

    def _problems(self) -> list[Problem]:
        out = super()._problems()
        if self.department_id is None:
            out.append((("department_id",), "a function node belongs to a department"))
        else:
            wanted = function_node_id(self.department_id, self.kind)
            if self.id != wanted:
                out.append((("id",), f"a function node id is '<department id>.<function>': {wanted!r}, not {self.id!r}"))
        if self.state not in FUNCTION_STATES:
            out.append((("state",), f"a function node uses one of {', '.join(FUNCTION_STATES)}, not {self.state!r}"))
        if self.state == "waiting" and not self.wait_on:
            out.append((("wait_on",), "a waiting function node says whom it waits for (wait_on)"))
        return out


@record
class IdentityNode(FunctionNode):
    FUNCTION = "identity"
    kind: Literal["identity"] = "identity"


@record
class AdaptationNode(FunctionNode):
    FUNCTION = "adaptation"
    kind: Literal["adaptation"] = "adaptation"


@record
class PriorityNode(FunctionNode):
    FUNCTION = "priority"
    kind: Literal["priority"] = "priority"


@record
class CoordinationNode(FunctionNode):
    FUNCTION = "coordination"
    kind: Literal["coordination"] = "coordination"


@record
class AuditNode(FunctionNode):
    FUNCTION = "audit"
    kind: Literal["audit"] = "audit"


FUNCTION_NODE_CLASSES: Final = MappingProxyType({
    "identity": IdentityNode, "adaptation": AdaptationNode, "priority": PriorityNode,
    "coordination": CoordinationNode, "audit": AuditNode,
})


# ---- hand-offs ---------------------------------------------------------------------------------------------------

# Who may hand the turn to whom (J2:103-107, changed by S3-web-04): coordination -> audit is the code hand-off at queue
# empty (j2.py:6834, 6891); audit -> identity only (j2.py:8969, _pick allowed=(identity,)). Only Identity reaches the
# Requester. The wire's `hands_to` is this table without "requester".
HANDOFFS: Final = MappingProxyType({
    "identity": ("requester", "adaptation", "priority", "coordination", "audit"),
    "adaptation": ("priority", "identity", "audit", "coordination"),
    "priority": ("adaptation", "identity", "coordination"),
    "coordination": ("priority", "adaptation", "identity", "audit"),
    "audit": ("identity",),
})
WORKFLOW_AGENT_HANDOFFS: Final = ("coordination",)       # a workflow agent W-n hands back to Coordination only


def hands_to(function: str) -> list[str]:
    """The wire's `hands_to` of a function: its HANDOFFS row without "requester". Raises KeyError for another name."""
    return [name for name in HANDOFFS[function] if name != "requester"]


def may_hand_off(source: str, target: str) -> bool:
    """True when `source` (a function name, or a workflow agent such as "W-3") may hand the turn to `target`."""
    if source in HANDOFFS:
        return target in HANDOFFS[source]
    return bool(re.fullmatch(r"W-[0-9]+", source)) and target in WORKFLOW_AGENT_HANDOFFS


# ---- edges -------------------------------------------------------------------------------------------------------

EdgeKind = Literal["contains", "has_function", "has_step", "handoff", "step", "speaks_to", "depends_on"]
EdgeStatus = Literal["filed", "running", "waiting", "waiting_on_you", "fault", "not_made", "idle"]
STORED_EDGE_KINDS: Final = ("handoff", "step", "speaks_to", "depends_on")
DERIVED_EDGE_KINDS: Final = ("contains", "has_function", "has_step")


class EdgeSource(Value):
    """The record an edge was drawn from: "no line without a record" (map-schema). `value` is the text of the field."""

    file: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    workflow: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    field: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    value: Annotated[str, StringConstraints(max_length=300)]


def edge_id(kind: str, from_id: str, to_id: str) -> str:
    """"<kind>:<from_id>><to_id>", the id every GraphEdge must carry."""
    return f"{kind}:{from_id}>{to_id}"


@record
class GraphEdge(Record):
    """A line between two nodes. `status` is the map/1 word the line is drawn in; `n` counts what the line stands for."""

    FAMILY = "edge"
    kind: EdgeKind
    id: EdgeId
    from_id: EdgeEnd
    to_id: EdgeEnd
    label: Annotated[str, StringConstraints(max_length=200)] = ""
    n: Count | None = None
    version: Revision = 1
    status: EdgeStatus = "idle"
    source: EdgeSource | None = None

    @model_validator(mode="after")
    def _edge_rules(self) -> Self:
        problems: list[Problem] = []
        if self.from_id == self.to_id:
            problems.append((("to_id",), f"an edge joins two different nodes, not {self.from_id!r} to itself"))
        wanted = edge_id(self.kind, self.from_id, self.to_id)
        if self.id != wanted:
            problems.append((("id",), f"the id of this edge is {wanted!r}, not {self.id!r}"))
        if self.kind in STORED_EDGE_KINDS and self.source is None:
            problems.append((("source",), f"a {self.kind} edge needs its source record (no line without a record)"))
        origin, target = _FUNCTION_ID_RE.fullmatch(self.from_id), _FUNCTION_ID_RE.fullmatch(self.to_id)
        if self.kind == "handoff" and origin and target and origin.group(1) == target.group(1):
            if target.group(2) not in HANDOFFS[origin.group(2)]:
                allowed = ", ".join(HANDOFFS[origin.group(2)])
                problems.append((("to_id",), f"{origin.group(2)} does not hand off to {target.group(2)} (it hands to: {allowed})"))
        if problems:
            _raise("GraphEdge", problems)
        return self


def make_edge(kind: str, from_id: str, to_id: str, *, label: str = "", n: int | None = None, status: str = "idle",
              source: EdgeSource | Mapping[str, Any] | None = None, version: int = 1) -> GraphEdge:
    """A GraphEdge with the id its kind and ends give it."""
    return GraphEdge(kind=kind, id=edge_id(kind, from_id, to_id), from_id=from_id, to_id=to_id, label=label, n=n,
                     status=status, source=source, version=version)


def derive_edges(chart: OrgChart, nodes: Iterable[Node]) -> list[GraphEdge]:
    """The edges the store derives on read, never stores: `contains` from the chart's edges, `has_function` from each
    function node's department, `has_step` from each step node's parent. In that order, each in the order of its source."""
    out = [make_edge("contains", edge.parent, edge.child) for edge in chart.edges]
    for node in nodes:
        if isinstance(node, FunctionNode) and node.department_id is not None:
            out.append(make_edge("has_function", node.department_id, node.id))
        elif isinstance(node, StructuralNode) and node.kind == "step" and node.parent_id is not None:
            out.append(make_edge("has_step", node.parent_id, node.id))
    return out


def check_graph(chart: OrgChart, nodes: Sequence[Node], edges: Sequence[GraphEdge]) -> list[Violation]:
    """Does the graph mirror the chart? `edges` are the stored edges plus the ones the store derives (`derive_edges`).
    Every violation found is returned, none hidden behind an earlier one; `[]` means the graph is sound.

    G1 every chart node has a StructuralNode with the same id and kind, and no root, department or division node is
       left that the chart does not have (a merged-away division's node is gone)
    G2 every department's five function nodes exist with the chart's ids, their function as kind and this department
    G3 no node names a department the chart does not have
    G4 every edge endpoint is a node; the `contains` edges are exactly the chart's; a given `has_function` or `has_step`
       edge is the one its node fields derive (a missing one is not reported: it is not data)
    G5 node.edge_ids and the stored edges agree both ways
    "one open atom per node" is the store's unique index, not a rule here."""
    found: list[Violation] = []

    def add(path: str, code: str, message: str) -> None:
        found.append(violation(path, code, message))

    by_id: dict[str, Node] = {}
    for node in nodes:
        if node.id in by_id:
            add(f"nodes.{node.id}", "G1", f"node id {node.id!r} appears more than once")
        else:
            by_id[node.id] = node
    chart_nodes = {chart_node.id: chart_node for chart_node in chart.nodes}
    departments = {chart_node.id for chart_node in chart.nodes if chart_node.kind == "department"}

    for chart_node in chart.nodes:                                                                      # G1
        node = by_id.get(chart_node.id)
        if node is None:
            add(f"nodes.{chart_node.id}", "G1", f"the chart's {chart_node.kind} {chart_node.id!r} has no graph node")
        elif not isinstance(node, StructuralNode) or node.kind != chart_node.kind:
            add(f"nodes.{chart_node.id}", "G1", f"{chart_node.id!r} is a {node.kind} node, the chart says {chart_node.kind}")
    for node in by_id.values():
        if isinstance(node, StructuralNode) and node.kind != "step" and node.id not in chart_nodes:
            add(f"nodes.{node.id}", "G1", f"the {node.kind} node {node.id!r} is not in the chart")

    for chart_node in chart.nodes:                                                                      # G2
        if chart_node.kind != "department" or chart_node.functions is None:
            continue
        for function in FUNCTIONS:
            wanted = getattr(chart_node.functions, function)
            node = by_id.get(wanted)
            if node is None:
                add(f"nodes.{wanted}", "G2", f"department {chart_node.id!r} has no {function} function node {wanted!r}")
            elif not isinstance(node, FunctionNode) or node.kind != function:
                add(f"nodes.{wanted}", "G2", f"{wanted!r} is not the {function} function node of {chart_node.id!r}")
            elif node.department_id != chart_node.id:
                add(f"nodes.{wanted}", "G2", f"{wanted!r} belongs to {node.department_id!r}, not to {chart_node.id!r}")

    for node in by_id.values():                                                                         # G3
        if node.department_id is not None and node.department_id not in departments:
            add(f"nodes.{node.id}", "G3", f"node {node.id!r} names the department {node.department_id!r}, which the chart does not have")

    seen_edges: set[str] = set()                                                                        # G4
    for edge in edges:
        if edge.id in seen_edges:
            add(f"edges.{edge.id}", "G4", f"edge id {edge.id!r} appears more than once")
        seen_edges.add(edge.id)
        for end, node_id in (("from", edge.from_id), ("to", edge.to_id)):
            if node_id not in by_id:
                add(f"edges.{edge.id}", "G4", f"the {end} end {node_id!r} of edge {edge.id!r} is not a node")
    given = {(edge.from_id, edge.to_id) for edge in edges if edge.kind == "contains"}
    wanted_pairs = {(edge.parent, edge.child) for edge in chart.edges}
    for from_id, to_id in sorted(wanted_pairs - given):
        add(f"edges.{edge_id('contains', from_id, to_id)}", "G4", f"the chart's edge {from_id!r} contains {to_id!r} has no contains edge")
    for from_id, to_id in sorted(given - wanted_pairs):
        add(f"edges.{edge_id('contains', from_id, to_id)}", "G4", f"the contains edge {from_id!r} to {to_id!r} is not in the chart")
    derived = {kind: {(edge.from_id, edge.to_id) for edge in derive_edges(chart, by_id.values()) if edge.kind == kind}
               for kind in ("has_function", "has_step")}
    for edge in edges:
        if edge.kind in derived and (edge.from_id, edge.to_id) not in derived[edge.kind]:
            add(f"edges.{edge.id}", "G4", f"the {edge.kind} edge {edge.id!r} is not what the node fields say")

    stored = {edge.id: edge for edge in edges if edge.kind in STORED_EDGE_KINDS}                        # G5
    for node in by_id.values():
        for listed in node.edge_ids:
            edge = stored.get(listed)
            if edge is None:
                add(f"nodes.{node.id}.edge_ids", "G5", f"node {node.id!r} lists the edge {listed!r}, which is not a stored edge")
            elif node.id not in (edge.from_id, edge.to_id):
                add(f"nodes.{node.id}.edge_ids", "G5", f"node {node.id!r} lists the edge {listed!r}, which does not touch it")
    for edge in stored.values():
        for end in dict.fromkeys((edge.from_id, edge.to_id)):
            node = by_id.get(end)
            if node is not None and edge.id not in node.edge_ids:
                add(f"edges.{edge.id}", "G5", f"node {end!r} does not list its stored edge {edge.id!r} in edge_ids")
    return found


# ---- the function-spec plug-in -----------------------------------------------------------------------------------

ALLOWED_GOAL_FIELDS: Final = ("function", "kind", "step_label", "task")      # what an AtomTemplate goal may name in braces
MAX_SPECS_BYTES: Final = 1024 * 1024
DEFAULT_SPECS_PATH: Final = Path(__file__).resolve().parent / "specs" / "function_specs.json"     # shipped by WP L10


class TaskKind(Value):
    """One kind of turn a function takes (a J2 dispatcher case) and the reply it answers with. `reply_kind` may list
    alternatives as "a|b"; a turn with no reply names neither family nor kind."""

    kind: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    summary: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    reply_family: Annotated[str, StringConstraints(max_length=60)] = ""
    reply_kind: Annotated[str, StringConstraints(max_length=100)] = ""


class CheckRef(Value):
    """A named check of the verify registry and its arguments. The name and argument count are judged by verify_refs."""

    name: CheckTemplate
    args: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=500)]], Field(max_length=8)] = []


class AtomTemplate(Value):
    """What a turn declares before its work: the goal sentence (it may name {function} {kind} {step_label} {task}), how
    the work is predicted to be done, the named checks (declare adds the floor checks) and the paths it touches."""

    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    goal: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    work: Work
    work_hint: Literal["llm", "bash", "manual"] = "llm"
    checks: Annotated[list[CheckRef], Field(max_length=6)] = []
    touches: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=300)]], Field(max_length=40)] = []

    @model_validator(mode="after")
    def _goal_names_only_known_fields(self) -> Self:
        try:
            names = [field for _, field, _, _ in string.Formatter().parse(self.goal) if field is not None]
        except ValueError as exc:
            raise ValueError(f"the goal has a brace that is not a field: {exc}") from None
        bad = [name for name in names if name not in ALLOWED_GOAL_FIELDS]
        if bad:
            raise ValueError(f"the goal names {{{bad[0]}}}; it may name only {', '.join('{' + f + '}' for f in ALLOWED_GOAL_FIELDS)}")
        return self


class FunctionSpec(Value):
    """The standing design of one function: its TASK line (`role`), its goal sentence, what it yields, reads, writes and
    may not do, the task kinds it takes and an atom template per kind. One template is named `generic`: it serves any
    task kind without its own template."""

    function: FunctionName
    role: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    goal: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    yields: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    stages: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=40)]], Field(max_length=8)] = []
    reads: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=80)]], Field(max_length=20)] = []
    writes: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=80)]], Field(max_length=20)] = []
    may_not: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=200)]], Field(max_length=20)] = []
    task_kinds: Annotated[list[TaskKind], Field(max_length=20)] = []
    atom_templates: Annotated[list[AtomTemplate], Field(max_length=10)]
    version: Revision

    @model_validator(mode="after")
    def _templates_and_kinds(self) -> Self:
        problems: list[Problem] = []
        names: set[str] = set()
        for index, template in enumerate(self.atom_templates):
            if template.name in names:
                problems.append((("atom_templates", index, "name"), f"two atom templates are named {template.name!r}"))
            names.add(template.name)
        if "generic" not in names:
            problems.append((("atom_templates",), "a function spec holds an atom template named 'generic'"))
        kinds: set[str] = set()
        for index, task_kind in enumerate(self.task_kinds):
            if task_kind.kind in kinds:
                problems.append((("task_kinds", index, "kind"), f"two task kinds are named {task_kind.kind!r}"))
            kinds.add(task_kind.kind)
        if problems:
            _raise("FunctionSpec", problems)
        return self


@record
class FunctionSpecs(Record):
    """The five FunctionSpecs, keyed by function (the key is the spec's own `function`)."""

    FAMILY = "function_specs"
    kind: Literal["function_specs"] = "function_specs"
    specs: dict[FunctionName, FunctionSpec]

    @model_validator(mode="after")
    def _all_five(self) -> Self:
        problems: list[Problem] = []
        for function in FUNCTIONS:
            if function not in self.specs:
                problems.append((("specs", function), f"the {function} spec is missing"))
        for key, spec in self.specs.items():
            if spec.function != key:
                problems.append((("specs", key, "function"), f"the spec under {key!r} says it is for {spec.function!r}"))
        if problems:
            _raise("FunctionSpecs", problems)
        return self


class FunctionSpecsError(Exception):
    """The spec file could not be turned into FunctionSpecs. `code`: missing, unreadable, too_large, not_json, invalid
    (then `violations` lists what is wrong)."""

    def __init__(self, code: str, detail: str = "", violations: Sequence[Violation] = ()) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.violations = list(violations)


def load_function_specs(path: str | Path | None = None) -> FunctionSpecs:
    """Read and validate the spec file (default: `specs/function_specs.json`, WP L10). Raises FunctionSpecsError."""
    target = Path(path) if path is not None else DEFAULT_SPECS_PATH
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        raise FunctionSpecsError("missing", f"there is no function spec file at {target}") from None
    except OSError as exc:
        raise FunctionSpecsError("unreadable", f"{target}: {exc.strerror or exc}") from None
    if len(raw) > MAX_SPECS_BYTES:
        raise FunctionSpecsError("too_large", f"{target} is {len(raw)} bytes, the limit is {MAX_SPECS_BYTES}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FunctionSpecsError("not_json", f"{target}: {clip(str(exc), 200)}") from None
    if not isinstance(data, dict):
        raise FunctionSpecsError("not_json", f"{target} holds {type(data).__name__}, not a JSON object")
    try:
        return FunctionSpecs.model_validate(data)
    except ValidationError as exc:
        found = violations_from_validation_error(exc)
        raise FunctionSpecsError("invalid", f"{target}: {len(found)} violation(s), the first: {found[0].path}: {found[0].message}", found) from None


def new_function_node(dept_id: str, function: str, specs: FunctionSpecs, now: int) -> FunctionNode:
    """The idle function node of `function` in department `dept_id`: goal = spec.goal, task = spec.role, context =
    spec.reads, spec_version = spec.version. Raises IdError for a bad department id or function name."""
    node_id = function_node_id(dept_id, function)
    spec = specs.specs[function]
    return FUNCTION_NODE_CLASSES[function](
        id=node_id, label=function.capitalize(), department_id=dept_id, goal=spec.goal, task=spec.role,
        context=list(spec.reads), spec_version=spec.version, ts_created=now, ts_updated=now)


def refresh_function_nodes(specs: FunctionSpecs, nodes: Iterable[Node]) -> list[FunctionNode]:
    """Pure: the function nodes whose spec_version is lower than their spec's, with goal, task, context and
    spec_version replaced (nothing else changes: state, stats, atoms and the store's version stay). The orchestrator calls
    it at startup and stores the result through the gate. Other nodes, and nodes already at the spec's version or above,
    are left out."""
    out: list[FunctionNode] = []
    for node in nodes:
        if not isinstance(node, FunctionNode):
            continue
        spec = specs.specs[node.kind]
        if node.spec_version < spec.version:
            out.append(node.evolve(goal=spec.goal, task=spec.role, context=list(spec.reads), spec_version=spec.version))
    return out


REGISTRY.bind_function_specs(load_function_specs)       # REGISTRY.verify_refs() with no argument loads the shipped specs
REGISTRY.bind_check_arity(check_arity)                   # ... and judges every check name and argument count
