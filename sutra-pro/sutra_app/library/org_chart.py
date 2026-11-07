"""The one global org chart and the record of how it changes (library design section 4; S2-models-01, S2-models-04).

There is ONE chart (owner rule). A chart is a document with a `revision`; a change is a record that produces the next
revision, and a task reuses, adds to or rearranges the chart on need. A department carries its five function nodes by
construction and is never moved or merged; only divisions move, merge and split. The library does the arithmetic and
the orchestrator keeps the tables, the approval policy and the extra rules around `apply_change`.

    OrgChart       the tree: nodes, parent-to-child edges, a revision; rules V1 to V6 are checked on every write
    ChartChangeRequest   what the chat agent asks the model for (reason, reuses, ops); the model never invents an id
    ChartChange    request + id, task id, base revision, ts; its kind (reuse, add, rearrange) is derived from the ops
    apply_change   pure: chart + change -> ChartChangeResult, or ChartChangeInvalid with ALL violations (C1 to C10)
    carry_links    the one rule for chat sessions on a merge (keep, move, archive); the store executes the plan

The docstrings and field descriptions of the model-facing classes (ChartChangeRequest, NewNode, the five ops,
ChildMove) are part of the transport schema the model reads, so they are short sentences on purpose.

Violation paths: `""` for the whole change (stale_base), `reuses.<i>`, `ops.<i>` followed by the field (`.node`,
`.to_parent`, `.into`, `.sources.<j>`, `.node.parent`, `.parts.<k>.name`, `.moves.<m>.child`), and `chart.<loc>` for
`invariant`, where `<loc>` is the place in the chart that would result. Codes: stale_base, unknown_node, bad_parent_kind,
duplicate_name, move_not_division, cycle, merge_not_division, bad_merge, split_not_division, bad_split_part, not_a_child,
bad_target, invariant, ids_lost, functions_changed (and, from carry_links and resolve_alias, bad_links and alias_cycle).
"""
import re
import unicodedata
from collections.abc import Callable, Collection, Mapping, Sequence
from itertools import count
from typing import Annotated, Any, Final, Literal, NoReturn, Self, Union

from pydantic import Field, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from .base import Record, Value
from .registry import REGISTRY, record
from .types import (
    FUNCTIONS, NODE_ID_RE, ChangeId, NodeId, Ref, Target, Ts, Violation, clip, function_node_id, violation,
    violations_from_validation_error,
)

__all__ = [
    "MAX_NODES", "MAX_EDGES", "MAX_DEPTH", "MAX_OPS", "MAX_REUSES", "MAX_SOURCES", "MAX_PARTS", "MAX_MOVES",
    "CHART_OPS_TRANSPORT", "SessionId", "FunctionIds", "OrgNode", "OrgEdge", "OrgChart", "seed_chart", "NewNode",
    "AddOp", "MoveOp", "RenameOp", "MergeOp", "ChildMove", "SplitOp", "ChartOp", "ChartChangeRequest", "ChartChange",
    "derive_kind", "ChartChangeResult", "LinkPlan", "ChartChangeInvalid", "NodeIdFactory", "slug_id", "apply_change",
    "carry_links", "resolve_alias",
]

MAX_NODES: Final = 500        # nodes in a chart (design parameters, not J2 or plugin facts)
MAX_EDGES: Final = 500
MAX_DEPTH: Final = 6          # edges between the root and the deepest node: department 1, divisions 2 to 6
MAX_OPS: Final = 8            # ops in one change
MAX_REUSES: Final = 10
MAX_SOURCES: Final = 4        # nodes merged away by one merge op
MAX_PARTS: Final = 3          # new divisions made by one split op
MAX_MOVES: Final = 20         # children re-parented by one split op
# How `ChartChangeRequest.ops` goes to the model: "union" (anyOf of the five ops). The live check
# `test_chart_change_request_native` decides; on failure this becomes "flat" and `ChartOpFlat` is added (S2-models-04).
CHART_OPS_TRANSPORT: Final = "union"

Name = Annotated[str, StringConstraints(min_length=1, max_length=80)]
Purpose = Annotated[str, StringConstraints(max_length=300)]
Reason = Annotated[str, StringConstraints(min_length=1, max_length=400)]
TaskId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
SessionId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
FunctionNodeId = Annotated[str, StringConstraints(min_length=1, max_length=60)]
Revision = Annotated[int, Field(ge=1)]
Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

_PARENT_KINDS = {"department": ("root",), "division": ("department", "division")}     # rule V4


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error for every problem, each at its own place (a model validator that raises a plain
    ValueError can report only one)."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)})
        for loc, text in problems])


# ---- the chart ----------------------------------------------------------------------------------------------------

class FunctionIds(Value):
    """The ids of a department's five function nodes, one field per function: `<department id>.<function>`."""

    identity: FunctionNodeId
    adaptation: FunctionNodeId
    priority: FunctionNodeId
    coordination: FunctionNodeId
    audit: FunctionNodeId

    @model_validator(mode="after")
    def _five_different(self) -> Self:
        if len(set(self.ids())) != len(FUNCTIONS):
            raise ValueError("the five function node ids must all be different")
        return self

    def ids(self) -> list[str]:
        """The five ids in the order of FUNCTIONS (identity, adaptation, priority, coordination, audit)."""
        return [getattr(self, function) for function in FUNCTIONS]

    @classmethod
    def for_department(cls, dept_id: str) -> Self:
        """The ids a department must carry; the scheme itself lives in `types.function_node_id`."""
        return cls(**{function: function_node_id(dept_id, function) for function in FUNCTIONS})


class OrgNode(Value):
    """One node of the chart. Only a department carries `functions`; `added_in` is the revision that made the node."""

    id: NodeId
    kind: Literal["root", "department", "division"]
    name: Name
    purpose: Purpose = ""
    functions: FunctionIds | None = None
    added_in: Revision = 1

    @model_validator(mode="after")
    def _functions_belong_to_departments(self) -> Self:
        if self.kind != "department":
            if self.functions is not None:
                raise ValueError(f"only a department carries function nodes, not a {self.kind}")
        elif self.functions is None:
            raise ValueError("a department must carry its five function nodes")
        else:
            wanted = FunctionIds.for_department(self.id)
            if self.functions != wanted:
                raise ValueError(f"the function nodes of department {self.id!r} must be {', '.join(wanted.ids())}")
        return self


class OrgEdge(Value):
    """A `contains` edge: `parent` holds `child`. The chart is one tree."""

    parent: NodeId
    child: NodeId


def _edge_key(edge: Any) -> tuple[str, str] | None:
    """(parent, child) of an edge given as an OrgEdge or as a dict, else None (the field check will say what is wrong)."""
    if isinstance(edge, OrgEdge):
        return edge.parent, edge.child
    if isinstance(edge, dict) and isinstance(edge.get("parent"), str) and isinstance(edge.get("child"), str):
        return edge["parent"], edge["child"]
    return None


def _chart_problems(nodes: Sequence[OrgNode], edges: Sequence[OrgEdge]) -> list[Problem]:
    """Rules V1 to V6 of the design, every violation found, none hidden behind an earlier one."""
    out: list[Problem] = []
    first_at: dict[str, int] = {}                                     # V1 ids unique
    for index, node in enumerate(nodes):
        if node.id in first_at:
            out.append((("nodes", index, "id"), f"duplicate node id {node.id!r} (also nodes.{first_at[node.id]})"))
        else:
            first_at[node.id] = index
    kind = {node.id: node.kind for node in reversed(nodes)}           # the first node of an id wins
    roots = [index for index, node in enumerate(nodes) if node.kind == "root"]        # V2 exactly one root
    if not roots:
        out.append((("nodes",), "the chart has no root node"))
    for index in roots[1:]:
        out.append((("nodes", index), f"a chart has one root, {nodes[roots[0]].id!r}: {nodes[index].id!r} cannot be a second"))
    parent_edges: dict[str, list[int]] = {}                           # V3 endpoints exist, one parent edge each
    for index, edge in enumerate(edges):
        for end, node_id in (("parent", edge.parent), ("child", edge.child)):
            if node_id not in first_at:
                out.append((("edges", index, end), f"edge {end} {node_id!r} is not a node of the chart"))
        if edge.child in first_at:
            parent_edges.setdefault(edge.child, []).append(index)
    for index, node in enumerate(nodes):
        held = parent_edges.get(node.id, [])
        if node.kind == "root":
            if held:
                out.append((("edges", held[0]), f"the root {node.id!r} cannot have a parent"))
        elif not held:
            out.append((("nodes", index), f"node {node.id!r} has no parent edge"))
        elif len(held) > 1:
            parents = ", ".join(repr(edges[k].parent) for k in held)
            out.append((("edges", held[1]), f"node {node.id!r} has {len(held)} parents: {parents}"))
    for index, edge in enumerate(edges):                              # V4 parent kinds
        if edge.parent in kind and edge.child in kind and kind[edge.child] in _PARENT_KINDS:
            if kind[edge.parent] not in _PARENT_KINDS[kind[edge.child]]:
                wanted = "the root" if kind[edge.child] == "department" else "a department or a division"
                out.append((("edges", index),
                            f"{kind[edge.child]} {edge.child!r} hangs under {wanted}, not under the {kind[edge.parent]} {edge.parent!r}"))
    out.extend(_cycle_and_depth_problems(nodes, edges, first_at, kind))          # V5
    seen_functions: dict[str, int] = {}                               # V6 function node ids unique
    for index, node in enumerate(nodes):
        for function_id in (node.functions.ids() if node.functions is not None else ()):
            if function_id in seen_functions:
                out.append((("nodes", index, "functions"), f"function node id {function_id!r} is also used by nodes.{seen_functions[function_id]}"))
            else:
                seen_functions[function_id] = index
    return out


def _cycle_and_depth_problems(nodes: Sequence[OrgNode], edges: Sequence[OrgEdge], first_at: Mapping[str, int],
                              kind: Mapping[str, str]) -> list[Problem]:
    """V5: every node must reach the root by following parent edges (a loop is a cycle) and lie at most MAX_DEPTH
    edges below it. A node cut off from the root by a missing parent edge is V3's business and is not reported again.
    One violation per cycle, and one per chain at the first node that is too deep."""
    parent: dict[str, str] = {}
    for edge in edges:
        if edge.child in first_at and edge.parent in first_at:
            parent.setdefault(edge.child, edge.parent)
    depth: dict[str, int] = {}                  # nodes whose distance from the root is known
    dead: set[str] = set()                      # nodes that do not reach the root (a cycle, or a missing parent edge)
    out: list[Problem] = []
    for start in first_at:
        if start in depth or start in dead:
            continue
        trail: list[str] = []
        current: str | None = start
        base: int | None = None
        while True:
            if current is None or current in dead:
                break
            if current in depth:
                base = depth[current]
                break
            if kind[current] == "root":
                depth[current] = base = 0
                break
            if current in trail:
                loop = trail[trail.index(current):]
                out.append((("nodes", first_at[loop[0]]), "cycle: " + " -> ".join([*loop, current])))
                break
            trail.append(current)
            current = parent.get(current)
        if base is None:
            dead.update(trail)
            continue
        for step, node_id in enumerate(reversed(trail), start=1):
            depth[node_id] = base + step
            if base + step == MAX_DEPTH + 1:
                out.append((("nodes", first_at[node_id]),
                            f"node {node_id!r} lies more than {MAX_DEPTH} levels below the root"))
    return out


@record
class OrgChart(Record):
    """The org chart: one tree of nodes with a revision. Edges are kept sorted, nodes in change order."""

    FAMILY = "org_chart"
    kind: Literal["org_chart"] = "org_chart"
    revision: Revision = 1
    nodes: Annotated[list[OrgNode], Field(min_length=1, max_length=MAX_NODES)]
    edges: Annotated[list[OrgEdge], Field(max_length=MAX_EDGES)] = []
    updated_ts: Ts = 0

    @model_validator(mode="before")
    @classmethod
    def _sort_edges(cls, data: Any) -> Any:
        """Edges are sorted by (parent, child) so that canonical JSON and its sha do not depend on the order they
        arrived in. Left alone when an edge is malformed: the field check reports that."""
        if isinstance(data, dict) and isinstance(data.get("edges"), list):
            keys = [_edge_key(edge) for edge in data["edges"]]
            if all(key is not None for key in keys):
                order = sorted(range(len(keys)), key=keys.__getitem__)
                return {**data, "edges": [data["edges"][index] for index in order]}
        return data

    @model_validator(mode="after")
    def _is_one_tree(self) -> Self:
        problems = _chart_problems(self.nodes, self.edges)
        if problems:
            _raise("OrgChart", problems)
        return self

    # ---- reading the tree. Unknown ids give None or [], never an error: ids often come from a model's reply.

    def node(self, node_id: str) -> OrgNode | None:
        for candidate in self.nodes:
            if candidate.id == node_id:
                return candidate
        return None

    def parent_of(self, node_id: str) -> str | None:
        """The id of the node's parent; None for the root and for an unknown id."""
        for edge in self.edges:
            if edge.child == node_id:
                return edge.parent
        return None

    def children_of(self, node_id: str) -> list[str]:
        """The ids of the node's children, in the order of `nodes`."""
        parent = {edge.child: edge.parent for edge in self.edges}
        return [candidate.id for candidate in self.nodes if parent.get(candidate.id) == node_id]

    def subtree(self, node_id: str) -> list[str]:
        """The node and everything below it, depth first, children in the order of `nodes`; [] for an unknown id."""
        if self.node(node_id) is None:
            return []
        parent = {edge.child: edge.parent for edge in self.edges}
        below: dict[str, list[str]] = {}
        for candidate in self.nodes:
            if candidate.id in parent:
                below.setdefault(parent[candidate.id], []).append(candidate.id)
        out: list[str] = []
        stack = [node_id]
        while stack:
            current = stack.pop()
            out.append(current)
            stack.extend(reversed(below.get(current, [])))
        return out

    def department_of(self, node_id: str) -> str | None:
        """The department the node is or lies in; None for the root and for an unknown id."""
        parent = {edge.child: edge.parent for edge in self.edges}
        kind = {candidate.id: candidate.kind for candidate in self.nodes}
        current, seen = node_id, set()
        while current in kind and current not in seen:          # `seen` only guards a chart built without validation
            if kind[current] == "department":
                return current
            seen.add(current)
            current = parent.get(current)
        return None


def seed_chart(root_id: str = "root", ts: int = 0) -> OrgChart:
    """Revision 1: the root and nothing else."""
    return OrgChart(revision=1, nodes=[OrgNode(id=root_id, kind="root", name="Root")], edges=[], updated_ts=ts)


# ---- the ops a model may propose ----------------------------------------------------------------------------------

class NewNode(Value):
    """A team or sub-team to create. It gets a placeholder ref, never an id: code assigns the id."""

    ref: Ref = Field(description="a placeholder such as $web; later ops may use it; it is never an id")
    kind: Literal["department", "division"]
    name: Name
    purpose: Purpose = ""
    parent: Target = Field(description="the id of an existing node, or a $ref added by an earlier op")


class AddOp(Value):
    """Add a department (under the root) or a division (under a department or a division)."""

    op: Literal["add"] = "add"
    node: NewNode


class MoveOp(Value):
    """Move a division under another department or division. A department cannot be moved."""

    op: Literal["move"] = "move"
    node: Target
    to_parent: Target


class RenameOp(Value):
    """Change the name or the purpose of a node; send null for the one you keep."""

    op: Literal["rename"] = "rename"
    node: Target
    name: Name | None = None
    purpose: Purpose | None = None

    @model_validator(mode="after")
    def _says_something(self) -> Self:
        if self.name is None and self.purpose is None:
            raise ValueError("a rename needs a new name, a new purpose or both")
        return self


class MergeOp(Value):
    """Merge divisions into another division; their children move to it and they disappear."""

    op: Literal["merge"] = "merge"
    into: Target
    sources: Annotated[list[Target], Field(min_length=1, max_length=MAX_SOURCES)]


class ChildMove(Value):
    """One child of the split division and the part (or the division itself) it goes to."""

    child: Target
    to: Target


class SplitOp(Value):
    """Split a division: new parts appear beside it under its parent; listed children move into a part."""

    op: Literal["split"] = "split"
    node: Target
    parts: Annotated[list[NewNode], Field(min_length=1, max_length=MAX_PARTS)]
    moves: Annotated[list[ChildMove], Field(max_length=MAX_MOVES)] = []


ChartOp = Annotated[Union[AddOp, MoveOp, RenameOp, MergeOp, SplitOp], Field(discriminator="op")]


def derive_kind(ops: Sequence[Any]) -> Literal["reuse", "add", "rearrange"]:
    """The kind of a change: reuse with no ops, add when every op adds, rearrange otherwise. Code sets it, never the model."""
    if not ops:
        return "reuse"
    return "add" if all(isinstance(op, AddOp) for op in ops) else "rearrange"


def _is_ref(target: str) -> bool:
    return target.startswith("$")


def _ref_problems(ops: Sequence[Any]) -> list[Problem]:
    """C12: a ref is added once and used only by a later op (or later in the op that adds it)."""
    added: dict[str, str] = {}
    out: list[Problem] = []

    def use(target: str, loc: tuple[str | int, ...]) -> None:
        if _is_ref(target) and target not in added:
            out.append((loc, f"ref {target} is used before it is added"))

    def add(ref: str, loc: tuple[str | int, ...]) -> None:
        if ref in added:
            out.append((loc, f"ref {ref} is added twice (first at {added[ref]})"))
        else:
            added[ref] = ".".join(str(part) for part in loc)

    for i, op in enumerate(ops):
        if isinstance(op, AddOp):
            use(op.node.parent, ("ops", i, "node", "parent"))
            add(op.node.ref, ("ops", i, "node", "ref"))
        elif isinstance(op, MoveOp):
            use(op.node, ("ops", i, "node"))
            use(op.to_parent, ("ops", i, "to_parent"))
        elif isinstance(op, RenameOp):
            use(op.node, ("ops", i, "node"))
        elif isinstance(op, MergeOp):
            use(op.into, ("ops", i, "into"))
            for j, source in enumerate(op.sources):
                use(source, ("ops", i, "sources", j))
        elif isinstance(op, SplitOp):
            use(op.node, ("ops", i, "node"))
            for k, part in enumerate(op.parts):
                use(part.parent, ("ops", i, "parts", k, "parent"))
                add(part.ref, ("ops", i, "parts", k, "ref"))
            for m, move in enumerate(op.moves):
                use(move.child, ("ops", i, "moves", m, "child"))
                use(move.to, ("ops", i, "moves", m, "to"))
    return out


class ChartChangeRequest(Value):
    """A change to the org chart: the reason, the existing nodes it reuses, and the ops to run in order."""

    reason: Reason = Field(description="one short sentence: why")
    reuses: Annotated[list[NodeId], Field(max_length=MAX_REUSES)] = Field(
        default=[], description="ids of existing nodes this change reuses")
    ops: Annotated[list[ChartOp], Field(max_length=MAX_OPS)] = Field(
        default=[], description="run in order; empty when the change only reuses")

    def _problems(self) -> list[Problem]:
        return _ref_problems(self.ops)

    @model_validator(mode="after")
    def _is_well_formed(self) -> Self:
        problems = self._problems()
        if problems:
            _raise(type(self).__name__, problems)
        return self


REGISTRY.register_payload("chart_change_request", 1, ChartChangeRequest)     # so ReplyParser and REGISTRY.transport_schema serve stage B


@record
class ChartChange(Record, ChartChangeRequest):
    """A request made into a record by code: kind (derived from the ops), id, the request id, the revision it was based on."""

    FAMILY = "chart_change"
    kind: Literal["reuse", "add", "rearrange"]
    id: ChangeId
    task_id: TaskId
    base_revision: Revision
    ts: Ts = 0

    def _problems(self) -> list[Problem]:
        out: list[Problem] = []
        wanted = derive_kind(self.ops)
        if self.kind != wanted:
            out.append(((), f"kind is {wanted} for these ops, not {self.kind}"))
        if self.kind == "reuse" and not self.reuses:
            out.append((("reuses",), "a reuse change must name the nodes it reuses"))
        return out + super()._problems()

    @classmethod
    def from_request(cls, request: ChartChangeRequest, *, id: str, task_id: str, base_revision: int, ts: int = 0) -> Self:
        """What the chat agent does with a model's reply: code adds the kind, id, request id, base revision and time."""
        return cls(kind=derive_kind(request.ops), reason=request.reason, reuses=request.reuses, ops=request.ops,
                   id=id, task_id=task_id, base_revision=base_revision, ts=ts)


# ---- results and errors -------------------------------------------------------------------------------------------

class ChartChangeResult(Value):
    """What a change did. `ids` maps each ref to the id code gave it; `aliases` maps a merged-away id to the node it
    went into (a chain when that node was merged too); `added`, `moved` and `merged` list node ids in change order
    (`moved`: nodes whose parent changed, by a move, a merge or a split; `merged`: the merged-away nodes);
    `new_function_nodes` are the function node ids of the departments added, for the graph store. A node that the
    change makes and merges away again is in `ids`, `aliases` and `merged` but not in `added` or in the chart."""

    chart: OrgChart
    ids: dict[Ref, NodeId] = {}
    aliases: dict[NodeId, NodeId] = {}
    added: Annotated[list[NodeId], Field(max_length=MAX_NODES)] = []
    moved: Annotated[list[NodeId], Field(max_length=MAX_NODES)] = []
    merged: Annotated[list[NodeId], Field(max_length=MAX_NODES)] = []
    new_function_nodes: Annotated[list[FunctionNodeId], Field(max_length=len(FUNCTIONS) * MAX_OPS * MAX_PARTS)] = []


class LinkPlan(Value):
    """What to do with chat sessions after a merge: `keep` (node -> session stays), `move` (session -> the node it is
    re-pointed to), `archive` (session -> the node it is filed under, read-only)."""

    keep: dict[NodeId, SessionId] = {}
    move: dict[SessionId, NodeId] = {}
    archive: dict[SessionId, NodeId] = {}


class ChartChangeInvalid(Exception):
    """A change that cannot be applied. `violations` holds ALL of them, in op order. HTTP: 422."""

    def __init__(self, violations: Sequence[Violation]) -> None:
        self.violations = list(violations)
        first = self.violations[0] if self.violations else None
        more = f" (+{len(self.violations) - 1} more)" if len(self.violations) > 1 else ""
        summary = f"{first.code} at {first.path or '<change>'}: {first.message}" if first else "no detail"
        super().__init__(f"chart change refused: {summary}{more}")


# ---- ids ----------------------------------------------------------------------------------------------------------

_WINDOWS_DEVICES = frozenset({"con", "prn", "aux", "nul", *(f"{device}{n}" for device in ("com", "lpt") for n in range(1, 10))})


def slug_id(kind: str, name: str, taken: Collection[str]) -> str:
    """A node id from a name: lowercase letters, digits and hyphens, then "-2", "-3" ... until it is free.
    A name with no usable letters (or none first) starts from the kind ("division-3d-printing", "department"), and an
    id is 2 to 40 characters, so it always fits NodeId and the department URL and folder rules. A name that slugs to a
    Windows device name (con, prn, aux, nul, com1-9, lpt1-9) also starts from the kind ("department-con"): a team's
    folder carries its id, and Windows cannot make a folder with such a name."""
    def slug(text: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
        return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")

    prefix = slug(kind) or "node"
    base = slug(name)
    if not base or not base[0].isalpha():
        base = f"{prefix}-{base}".strip("-")
    elif len(base) < 2:
        base = f"{prefix}-{base}"
    if base in _WINDOWS_DEVICES:
        base = f"{prefix}-{base}"
    for n in count(1):                                  # ends within len(taken) + 1 steps: the candidates differ
        suffix = "" if n == 1 else f"-{n}"
        candidate = base[: 40 - len(suffix)].rstrip("-") + suffix
        if candidate not in taken:
            return candidate


NodeIdFactory = Callable[[str, str, Collection[str]], str]       # (kind, name, taken) -> a fresh NodeId


def _name_key(name: str) -> str:
    """What two sibling names are compared by: case and spaces do not count ("a clash means reuse it")."""
    return "".join(unicodedata.normalize("NFKC", name).split()).casefold()


# ---- applying a change --------------------------------------------------------------------------------------------

_SKIP: Final = object()      # a target that is a ref whose node could not be made: the op is skipped, not blamed twice


class _Work:
    """The tree as two dicts while ops run. `clone()` is a scratch copy for an op that must change nothing if it fails."""

    def __init__(self, nodes: dict[str, OrgNode], parent: dict[str, str]) -> None:
        self.nodes = nodes
        self.parent = parent

    @classmethod
    def of(cls, chart: OrgChart) -> "_Work":
        return cls({n.id: n for n in chart.nodes}, {e.child: e.parent for e in chart.edges})

    def clone(self) -> "_Work":
        return _Work(dict(self.nodes), dict(self.parent))

    def children(self, node_id: str) -> list[str]:
        return [i for i in self.nodes if self.parent.get(i) == node_id]

    def contains(self, outer: str, inner: str) -> bool:
        """True when `inner` is `outer` itself or lies below it."""
        current, seen = inner, set()
        while current is not None and current not in seen:
            if current == outer:
                return True
            seen.add(current)
            current = self.parent.get(current)
        return False

    def clash(self, parent_id: str, name: str, ignore: Collection[str] = ()) -> OrgNode | None:
        """The child of `parent_id` (other than `ignore`) whose name is the same as `name`, or None."""
        key = _name_key(name)
        for child in self.children(parent_id):
            if child not in ignore and _name_key(self.nodes[child].name) == key:
                return self.nodes[child]
        return None


def _place_problem(work: _Work, kind: str, name: str, parent_id: str, parent_path: str, name_path: str,
                   ignore: Collection[str] = ()) -> tuple[str, str, str] | None:
    """(path, code, message) when a node of `kind` named `name` cannot hang under `parent_id`: rule V4, then C3's
    "the name is unique among siblings" (a clash means: reuse it)."""
    parent = work.nodes[parent_id]
    if parent.kind not in _PARENT_KINDS[kind]:
        wanted = "the root" if kind == "department" else "a department or a division"
        return parent_path, "bad_parent_kind", f"a {kind} hangs under {wanted}, not under the {parent.kind} {parent_id!r}"
    clash = work.clash(parent_id, name, ignore)
    if clash is not None:
        return (name_path, "duplicate_name",
                f"{parent.name!r} ({parent_id}) already has {clash.name!r} ({clash.id}): reuse it or pick another name")
    return None


class _Applier:
    """One run of `apply_change`: ops in order on a working copy, every violation collected, nothing mutated."""

    def __init__(self, chart: OrgChart, change: ChartChange, new_id: NodeIdFactory) -> None:
        self.chart, self.change, self.new_id = chart, change, new_id
        self.revision = chart.revision + 1
        self.w = _Work.of(chart)
        self.violations: list[Violation] = []
        self.ids: dict[str, str] = {}              # ref -> id
        self.failed: set[str] = set()              # refs whose node could not be made
        self.taken: set[str] = {n.id for n in chart.nodes}
        self.aliases: dict[str, str] = {}          # merged-away id -> the node it went into
        self.added: list[str] = []
        self.moved: list[str] = []                 # candidates, in order; the final parents decide
        self.merged: list[str] = []

    def violate(self, path: str, code: str, message: str) -> None:
        self.violations.append(violation(path, code, message))

    def run(self) -> ChartChangeResult:
        change, chart = self.change, self.chart
        if change.base_revision != chart.revision:                                           # C1
            raise ChartChangeInvalid([violation(
                "", "stale_base",
                f"change is based on revision {change.base_revision}, chart is at {chart.revision}: read the chart again")])
        for i, node_id in enumerate(change.reuses):                                          # C2
            if node_id not in self.w.nodes:
                self.violate(f"reuses.{i}", "unknown_node", f"cannot reuse {node_id!r}: it is not in the chart")
        if not change.ops:
            if self.violations:
                raise ChartChangeInvalid(self.violations)
            return ChartChangeResult(chart=chart)
        for i, op in enumerate(change.ops):
            if isinstance(op, AddOp):
                self.op_add(i, op)
            elif isinstance(op, MoveOp):
                self.op_move(i, op)
            elif isinstance(op, RenameOp):
                self.op_rename(i, op)
            elif isinstance(op, MergeOp):
                self.op_merge(i, op)
            else:
                self.op_split(i, op)
        if self.violations:
            raise ChartChangeInvalid(self.violations)
        return self.finish()

    # ---- finding targets and making nodes

    def lookup(self, target: str, refs: Mapping[str, str]) -> Any:
        """The id a target names: an id as it is, a ref as the id it was given. None for a ref nothing added, _SKIP for
        a ref whose node could not be made (the op that made it already has a violation)."""
        if not _is_ref(target):
            return target
        if target in refs:
            return refs[target]
        return _SKIP if target in self.failed else None

    def resolve(self, target: str, path: str) -> Any:
        """`lookup`, and the node must be in the working chart: otherwise unknown_node is recorded and None returned."""
        found = self.lookup(target, self.ids)
        if found is _SKIP:
            return _SKIP
        if found is None:
            self.violate(path, "unknown_node", f"ref {target} was not added by an earlier op")
            return None
        if found not in self.w.nodes:
            into = self.aliases.get(found)
            self.violate(path, "unknown_node", f"{found!r} was merged into {into!r} earlier in this change" if into
                         else f"{found!r} is not in the chart")
            return None
        return found

    def fresh_id(self, kind: str, name: str, path: str) -> str | None:
        taken = frozenset(self.taken)
        made = self.new_id(kind, name, taken)
        if not isinstance(made, str) or not NODE_ID_RE.fullmatch(made):
            self.violate(path, "invariant", f"new_id returned {clip(repr(made), 60)}, which is not a node id")
            return None
        if made in taken:
            self.violate(path, "invariant", f"new_id returned {made!r}, which is already used")
            return None
        self.taken.add(made)
        return made

    def make_node(self, work: _Work, spec: NewNode, parent_id: str, path: str) -> str | None:
        node_id = self.fresh_id(spec.kind, spec.name, path)
        if node_id is None:
            return None
        functions = FunctionIds.for_department(node_id) if spec.kind == "department" else None
        work.nodes[node_id] = OrgNode(id=node_id, kind=spec.kind, name=spec.name, purpose=spec.purpose,
                                      functions=functions, added_in=self.revision)
        work.parent[node_id] = parent_id
        return node_id

    # ---- the five ops. Each checks first and changes the working copy last (merge and split on a scratch copy).

    def op_add(self, i: int, op: AddOp) -> None:                                             # C3, C10
        spec, path = op.node, f"ops.{i}.node"
        parent = self.resolve(spec.parent, f"{path}.parent")
        if not isinstance(parent, str):
            self.failed.add(spec.ref)
            return
        problem = _place_problem(self.w, spec.kind, spec.name, parent, f"{path}.parent", f"{path}.name")
        if problem is not None:
            self.violate(*problem)
            self.failed.add(spec.ref)
            return
        node_id = self.make_node(self.w, spec, parent, path)
        if node_id is None:
            self.failed.add(spec.ref)
            return
        self.ids[spec.ref] = node_id
        self.added.append(node_id)

    def op_move(self, i: int, op: MoveOp) -> None:                                           # C4
        path = f"ops.{i}"
        node_id = self.resolve(op.node, f"{path}.node")
        parent = self.resolve(op.to_parent, f"{path}.to_parent")
        if not isinstance(node_id, str) or not isinstance(parent, str):
            return
        node = self.w.nodes[node_id]
        if node.kind != "division":
            self.violate(f"{path}.node", "move_not_division", f"{node_id!r} is a {node.kind}: only divisions can be moved")
        elif self.w.contains(node_id, parent):
            self.violate(f"{path}.to_parent", "cycle",
                         f"{node_id!r} cannot move into itself" if parent == node_id
                         else f"{parent!r} lies inside {node_id!r}: a division cannot move into its own subtree")
        else:
            problem = _place_problem(self.w, "division", node.name, parent, f"{path}.to_parent", f"{path}.to_parent", {node_id})
            if problem is not None:
                self.violate(*problem)
            else:
                self.w.parent[node_id] = parent
                self.moved.append(node_id)

    def op_rename(self, i: int, op: RenameOp) -> None:                                       # C5
        path = f"ops.{i}"
        node_id = self.resolve(op.node, f"{path}.node")
        if not isinstance(node_id, str):
            return
        node = self.w.nodes[node_id]
        if node.kind == "root":
            self.violate(f"{path}.node", "unknown_node", f"{node_id!r} is the root of the chart and cannot be renamed")
            return
        if op.name is not None:
            clash = self.w.clash(self.w.parent[node_id], op.name, {node_id})
            if clash is not None:
                self.violate(f"{path}.name", "duplicate_name",
                             f"{clash.name!r} ({clash.id}) already has that name beside {node_id!r}: reuse it or pick another name")
                return
        changes: dict[str, str] = {}
        if op.name is not None:
            changes["name"] = op.name
        if op.purpose is not None:
            changes["purpose"] = op.purpose
        self.w.nodes[node_id] = node.evolve(**changes)

    def op_merge(self, i: int, op: MergeOp) -> None:                                         # C6
        path = f"ops.{i}"
        into = self.resolve(op.into, f"{path}.into")
        sources = [self.resolve(s, f"{path}.sources.{j}") for j, s in enumerate(op.sources)]
        if not isinstance(into, str) or not all(isinstance(s, str) for s in sources):
            return
        before = len(self.violations)
        for where, node_id in [(f"{path}.into", into), *((f"{path}.sources.{j}", s) for j, s in enumerate(sources))]:
            kind = self.w.nodes[node_id].kind
            if kind != "division":
                self.violate(where, "merge_not_division", f"{node_id!r} is a {kind}: only divisions can be merged")
        seen: set[str] = set()
        for j, source in enumerate(sources):
            if source == into:
                self.violate(f"{path}.sources.{j}", "bad_merge", f"{source!r} cannot be merged into itself")
            elif source in seen:
                self.violate(f"{path}.sources.{j}", "bad_merge", f"{source!r} is listed twice in sources")
            seen.add(source)
        if len(self.violations) > before:
            return
        for source in sources:
            if self.w.contains(source, into):
                self.violate(f"{path}.into", "cycle",
                             f"{into!r} lies inside {source!r}, which is merged away: merge into a node outside it")
        if len(self.violations) > before:
            return
        trial, taken_in = self.w.clone(), []
        for j, source in enumerate(sources):
            for child in trial.children(source):
                clash = trial.clash(into, trial.nodes[child].name)
                if clash is not None:
                    self.violate(f"{path}.sources.{j}", "duplicate_name",
                                 f"{trial.nodes[child].name!r} ({child}) would sit beside {clash.name!r} ({clash.id}) in {into!r}: rename one first")
                else:
                    trial.parent[child] = into
                    taken_in.append(child)
            del trial.nodes[source]
            trial.parent.pop(source, None)
        if len(self.violations) > before:
            return
        self.w = trial
        for source in sources:
            self.aliases[source] = into
            self.merged.append(source)
        self.moved.extend(taken_in)

    def op_split(self, i: int, op: SplitOp) -> None:                                         # C7
        path = f"ops.{i}"
        node_id = self.resolve(op.node, f"{path}.node")
        if not isinstance(node_id, str):
            self.failed.update(part.ref for part in op.parts)
            return
        node = self.w.nodes[node_id]
        if node.kind != "division":
            self.violate(f"{path}.node", "split_not_division", f"{node_id!r} is a {node.kind}: only divisions can be split")
            self.failed.update(part.ref for part in op.parts)
            return
        parent_id = self.w.parent[node_id]
        trial, ok = self.w.clone(), True
        parts: dict[str, str] = {}                 # ref -> the id of the new part
        for k, part in enumerate(op.parts):
            where = f"{path}.parts.{k}"
            if part.kind != "division":
                self.violate(f"{where}.kind", "bad_split_part", "a split part is a division, not a department")
                ok = False
                continue
            under = self.lookup(part.parent, {**self.ids, **parts})
            if under is _SKIP:
                ok = False
                continue
            if under != parent_id:
                self.violate(f"{where}.parent", "bad_split_part",
                             f"a split part hangs under {parent_id!r}, the parent of {node_id!r}, not under {clip(str(under or part.parent), 60)!r}")
                ok = False
                continue
            problem = _place_problem(trial, "division", part.name, parent_id, f"{where}.parent", f"{where}.name")
            if problem is not None:
                self.violate(*problem)
                ok = False
                continue
            part_id = self.make_node(trial, part, parent_id, where)
            if part_id is None:
                ok = False
                continue
            parts[part.ref] = part_id
        refs = {**self.ids, **parts}
        taken_over: list[str] = []
        for m, move in enumerate(op.moves):
            where = f"{path}.moves.{m}"
            child, to = self.lookup(move.child, refs), self.lookup(move.to, refs)
            if child is _SKIP or to is _SKIP:
                ok = False
                continue
            if not isinstance(child, str) or trial.parent.get(child) != node_id:
                if child in taken_over:
                    why = "was already moved by an earlier entry of moves"
                elif child not in trial.nodes:
                    why = "is not in the chart"
                else:
                    why = f"is not a child of {node_id!r}"
                self.violate(f"{where}.child", "not_a_child", f"{(child if isinstance(child, str) else move.child)!r} {why}")
                ok = False
            elif to not in {*parts.values(), node_id}:
                self.violate(f"{where}.to", "bad_target",
                             f"{clip(str(to or move.to), 60)!r} is neither a new part nor {node_id!r}: children move to a part or stay")
                ok = False
            elif to != node_id:
                clash = trial.clash(to, trial.nodes[child].name, {child})
                if clash is not None:
                    self.violate(f"{where}.to", "duplicate_name",
                                 f"{trial.nodes[child].name!r} ({child}) would sit beside {clash.name!r} ({clash.id}) in {to!r}: rename one first")
                    ok = False
                else:
                    trial.parent[child] = to
                    taken_over.append(child)
        if not ok:
            self.failed.update(part.ref for part in op.parts)
            return
        self.w = trial
        self.ids.update(parts)
        self.added.extend(parts.values())
        self.moved.extend(taken_over)

    # ---- the result

    def finish(self) -> ChartChangeResult:
        nodes = list(self.w.nodes.values())
        edges = [OrgEdge(parent=parent, child=child) for child, parent in self.w.parent.items()]
        try:
            chart = OrgChart(revision=self.revision, nodes=nodes, edges=edges, updated_ts=self.change.ts)      # C8
        except ValidationError as exc:
            raise ChartChangeInvalid([
                violation(f"chart.{v.path}" if v.path else "chart", "invariant", v.message)
                for v in violations_from_validation_error(exc)]) from None
        problems = _preserved_problems(self.chart, chart, self.aliases)                                      # C9
        if problems:
            raise ChartChangeInvalid(problems)
        now = {n.id: n for n in chart.nodes}
        added = [node_id for node_id in self.added if node_id in now]
        old_parent = {e.child: e.parent for e in self.chart.edges}
        new_parent = {e.child: e.parent for e in chart.edges}
        moved = [node_id for node_id in dict.fromkeys(self.moved)
                 if node_id in old_parent and node_id in new_parent and node_id not in added
                 and old_parent[node_id] != new_parent[node_id]]
        functions = [fid for node_id in added if (fns := now[node_id].functions) is not None for fid in fns.ids()]      # C10
        return ChartChangeResult(chart=chart, ids=dict(self.ids), aliases=dict(self.aliases), added=added, moved=moved,
                                 merged=list(self.merged), new_function_nodes=functions)


def _preserved_problems(old: OrgChart, new: OrgChart, aliases: Mapping[str, str]) -> list[Violation]:
    """C9: the new chart loses no id except merged-away ones, and no department's function ids change."""
    now = {n.id: n for n in new.nodes}
    out: list[Violation] = []
    for node in old.nodes:
        if node.id not in now:
            if node.id not in aliases:
                out.append(violation("", "ids_lost", f"node {node.id!r} disappeared without being merged"))
        elif node.kind == "department" and now[node.id].functions != node.functions:
            out.append(violation("", "functions_changed", f"the function nodes of department {node.id!r} changed"))
    return out


def apply_change(chart: OrgChart, change: ChartChange, *, new_id: NodeIdFactory = slug_id) -> ChartChangeResult:
    """Apply `change` to `chart`. Pure: neither argument is touched and the same input gives the same result.

    Ops run in order on a working copy, so a later op may use a ref an earlier op added. Every violation of every op is
    collected and raised together as ChartChangeInvalid (an op that failed changes nothing, and an op that depends on a
    ref that failed is skipped without a second complaint). `new_id(kind, name, taken)` gives each added node its id:
    `taken` holds every id of the chart and of the change so far; the orchestrator widens it with all ids ever used so
    that an id is never reused. A reuse change returns the chart as it is; add and rearrange raise the revision by 1."""
    if not isinstance(chart, OrgChart) or not isinstance(change, ChartChange):
        raise TypeError("apply_change takes an OrgChart and a ChartChange")
    return _Applier(chart, change, new_id).run()


# ---- chat links ---------------------------------------------------------------------------------------------------

def resolve_alias(aliases: Mapping[str, str], node_id: str) -> str:
    """The node `node_id` finally went into: a merged-away id follows its alias, and so on while the target was merged
    too. An id that is not an alias is returned as it is."""
    seen = {node_id}
    while node_id in aliases:
        node_id = aliases[node_id]
        if node_id in seen:
            raise ChartChangeInvalid([violation("aliases", "alias_cycle", f"the aliases lead from {node_id!r} back to itself")])
        seen.add(node_id)
    return node_id


def carry_links(links: Mapping[str, str], result: ChartChangeResult) -> LinkPlan:
    """The one rule for chat sessions when a change merges nodes (C11). `links` maps each node id to its session id,
    in the order of the old chart. A node that is still in the chart keeps its session (`keep`). A merged-away node's
    session moves to the node it finally went into when that node has none (`move`), else it is filed under it
    (`archive`); the first merged-away node in `links` order gets the `move`. No session is dropped: a node that is
    neither in the chart nor merged away, or a session linked twice, raises ChartChangeInvalid instead."""
    alive = {node.id for node in result.chart.nodes}
    problems: list[Violation] = []
    owner: dict[str, str] = {}
    for node_id, session_id in links.items():
        if session_id in owner:
            problems.append(violation(f"links.{node_id}", "bad_links", f"session {session_id!r} is already linked to {owner[session_id]!r}"))
        owner[session_id] = node_id
    keep = {node_id: session_id for node_id, session_id in links.items() if node_id in alive}
    holders = set(keep)
    move: dict[str, str] = {}
    archive: dict[str, str] = {}
    for node_id, session_id in links.items():
        if node_id in alive:
            continue
        if node_id not in result.aliases:
            problems.append(violation(f"links.{node_id}", "unknown_node", f"{node_id!r} is neither in the chart nor merged away by this change"))
            continue
        target = resolve_alias(result.aliases, node_id)
        if target not in alive:
            problems.append(violation(f"links.{node_id}", "unknown_node", f"{node_id!r} went into {target!r}, which is not in the chart"))
        elif target in holders:
            archive[session_id] = target
        else:
            move[session_id] = target
            holders.add(target)
    if problems:
        raise ChartChangeInvalid(problems)
    return LinkPlan(keep=keep, move=move, archive=archive)
