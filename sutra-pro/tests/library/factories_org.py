"""Builders for the org chart tests (WP L2): a chart from a nested dict, the five ops, a change and `apply` in one call.

Any library test that needs a chart can import this module (`from factories_org import make_chart`): tests/library has
no __init__.py, so pytest puts the folder on sys.path. Nothing here is a fixture and nothing registers a class.

    chart = make_chart({"sales": {"leads": {}, "quotes": {}}, "web": {}})     # top level: departments; below: divisions
    result = apply(chart, merge_op("quotes", "leads"))                         # a change based on the chart's revision
"""
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import ValidationError

from sutra_app.library.org_chart import (
    AddOp, ChartChange, ChartChangeInvalid, ChartChangeResult, ChildMove, FunctionIds, MergeOp, MoveOp, NewNode, OrgChart,
    OrgEdge, OrgNode, RenameOp, SplitOp, apply_change, derive_kind,
)
from sutra_app.library.types import violations_from_validation_error


def titled(node_id: str) -> str:
    """The name a factory gives a node: its id as words ("lead-gen" -> "Lead Gen")."""
    return node_id.replace("-", " ").replace("_", " ").title()


def make_chart(tree: Mapping[str, Any] | None = None, *, names: Mapping[str, str] | None = None,
               purposes: Mapping[str, str] | None = None, revision: int = 1, ts: int = 0, root_id: str = "root") -> OrgChart:
    """A valid chart from a nested dict of ids: the keys of the top level are departments under the root, everything
    below is a division. `names` and `purposes` override the defaults (the id as words, no purpose). Nodes come in
    depth-first order, as the dict lists them."""
    names, purposes = names or {}, purposes or {}
    nodes = [OrgNode(id=root_id, kind="root", name=names.get(root_id, "Root"), purpose=purposes.get(root_id, ""))]
    edges: list[OrgEdge] = []

    def walk(level: Mapping[str, Any], parent: str, kind: str) -> None:
        for node_id, below in level.items():
            nodes.append(OrgNode(
                id=node_id, kind=kind, name=names.get(node_id, titled(node_id)), purpose=purposes.get(node_id, ""),
                functions=FunctionIds.for_department(node_id) if kind == "department" else None))
            edges.append(OrgEdge(parent=parent, child=node_id))
            walk(below, node_id, "division")

    walk(tree or {}, root_id, "department")
    return OrgChart(revision=revision, nodes=nodes, edges=edges, updated_ts=ts)


SIX = {"sales": {"leads": {}, "quotes": {}}, "web": {"menu": {}}}      # root, sales, leads, quotes, web, menu


def six_node_chart() -> OrgChart:
    """The chart of the live transport check ("merge Leads into Quotes and add a Support team"): six nodes."""
    return make_chart(SIX)


def chain(levels: int) -> dict[str, Any]:
    """One department `dept` with a straight line of `levels` divisions below it: the deepest sits `levels + 1` edges
    below the root."""
    tree: dict[str, Any] = {"dept": {}}
    level = tree["dept"]
    for i in range(levels):
        level[f"div{i}"] = {}
        level = level[f"div{i}"]
    return tree


def big_tree(departments: int = 20, divisions: int = 479) -> dict[str, Any]:
    """root + `departments` + `divisions` nodes (500 by default), the divisions spread over the departments."""
    tree: dict[str, Any] = {f"d{i:02d}": {} for i in range(departments)}
    for j in range(divisions):
        tree[f"d{j % departments:02d}"][f"v{j:03d}"] = {}
    return tree


def raw_chart(chart: OrgChart | None = None) -> dict[str, Any]:
    """A chart as plain JSON data, for a test that breaks one thing in it."""
    return (chart or six_node_chart()).model_dump(mode="json")


# ---- ops --------------------------------------------------------------------------------------------------------

def new_node(ref: str, kind: str, name: str, parent: str, purpose: str = "") -> NewNode:
    return NewNode(ref=ref, kind=kind, name=name, purpose=purpose, parent=parent)


def add_op(ref: str, kind: str, name: str, parent: str, purpose: str = "") -> AddOp:
    return AddOp(node=new_node(ref, kind, name, parent, purpose))


def dept_op(ref: str, name: str, parent: str = "root") -> AddOp:
    return add_op(ref, "department", name, parent)


def div_op(ref: str, name: str, parent: str) -> AddOp:
    return add_op(ref, "division", name, parent)


def move_op(node: str, to_parent: str) -> MoveOp:
    return MoveOp(node=node, to_parent=to_parent)


def rename_op(node: str, name: str | None = None, purpose: str | None = None) -> RenameOp:
    return RenameOp(node=node, name=name, purpose=purpose)


def merge_op(into: str, *sources: str) -> MergeOp:
    return MergeOp(into=into, sources=list(sources))


def split_op(node: str, parts: Sequence[NewNode], moves: Sequence[tuple[str, str]] = ()) -> SplitOp:
    return SplitOp(node=node, parts=list(parts), moves=[ChildMove(child=c, to=t) for c, t in moves])


# ---- changes ----------------------------------------------------------------------------------------------------

def make_change(chart: OrgChart, *ops: Any, reuses: Sequence[str] = (), kind: str | None = None,
                reason: str = "test change", id: str = "chg-0001", task_id: str = "req-1", ts: int = 1,
                base_revision: int | None = None) -> ChartChange:
    """A ChartChange based on `chart`'s revision, its kind derived from the ops unless `kind` says otherwise."""
    return ChartChange(
        kind=kind or derive_kind(ops), reason=reason, reuses=list(reuses), ops=list(ops), id=id, task_id=task_id,
        base_revision=chart.revision if base_revision is None else base_revision, ts=ts)


def apply(chart: OrgChart, *ops: Any, new_id: Any = None, **change: Any) -> ChartChangeResult:
    """Build a change from `ops` (see make_change) and apply it."""
    made = make_change(chart, *ops, **change)
    return apply_change(chart, made) if new_id is None else apply_change(chart, made, new_id=new_id)


def refused(chart: OrgChart, *ops: Any, **change: Any) -> ChartChangeInvalid:
    """The ChartChangeInvalid that applying these ops raises (the test fails when nothing is raised)."""
    with pytest.raises(ChartChangeInvalid) as info:
        apply(chart, *ops, **change)
    return info.value


def found(exc: ChartChangeInvalid) -> list[tuple[str, str]]:
    """(path, code) of every violation, in order."""
    return [(v.path, v.code) for v in exc.violations]


def raw_change(*ops: Any, kind: str | None = None, **fields: Any) -> dict[str, Any]:
    """A change as plain JSON data, built without checking it: for a test that needs an invalid one."""
    data: dict[str, Any] = {
        "kind": kind or derive_kind(ops), "reason": "test change", "reuses": [], "ops": [op.model_dump(mode="json") for op in ops],
        "id": "chg-0001", "task_id": "req-1", "base_revision": 1, "ts": 1}
    data.update(fields)
    return data


def reject(model: Any, data: Any) -> list[tuple[str, str, str]]:
    """(path, code, message) of every violation `model` finds in `data`; the test fails when it accepts the data."""
    with pytest.raises(ValidationError) as info:
        model.model_validate(data)
    return [(v.path, v.code, v.message) for v in violations_from_validation_error(info.value)]
