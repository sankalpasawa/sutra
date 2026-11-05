"""Builders for the node, edge and function-spec tests (WP L6): a toy spec set, a consistent graph for a chart, steps and
stored edges, and a violation reader.

Any library test that needs graph nodes can import this module (`from factories_node import graph_of`): tests/library has
no __init__.py, so pytest puts the folder on sys.path. Nothing here is a fixture and nothing registers a class.

    chart = make_chart({"sales": {"leads": {}}, "web": {}})
    nodes, edges = graph_of(chart)                    # structural nodes, five function nodes per department, derived edges
    assert check_graph(chart, nodes, edges) == []
    specs = toy_specs(version=2)                      # five valid FunctionSpecs, every one with its 'generic' template
"""
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import ValidationError

from factories_org import make_chart
from sutra_app.library.atom import Work
from sutra_app.library.node import (
    AtomTemplate, CheckRef, EdgeSource, FunctionNode, FunctionSpec, FunctionSpecs, GraphEdge, Node, StructuralNode,
    TaskKind, derive_edges, make_edge, new_function_node, step_node_id,
)
from sutra_app.library.org_chart import OrgChart
from sutra_app.library.types import FUNCTIONS, Violation, violations_from_validation_error

TASK = "tsk_0123456789ab"
GENERIC_GOAL = "The {function} answers the hand-off {kind} with a reply that follows its rules"


def violations_of(build) -> list[Violation]:
    """Run `build()` (it must raise a ValidationError) and return its violations."""
    with pytest.raises(ValidationError) as caught:
        build()
    return violations_from_validation_error(caught.value)


def said(found: Sequence[Violation], code: str, *words: str) -> bool:
    """Is there a violation with this code whose message holds every word?"""
    return any(v.code == code and all(w in v.message for w in words) for v in found)


def codes(found: Sequence[Violation]) -> list[str]:
    return [v.code for v in found]


def template(name: str = "generic", **over: Any) -> AtomTemplate:
    fields: dict[str, Any] = dict(name=name, goal=GENERIC_GOAL, work=Work(dispatch_kind="llm"), work_hint="llm", checks=[], touches=[])
    return AtomTemplate(**{**fields, **over})


def toy_spec(function: str = "priority", *, version: int = 1, **over: Any) -> FunctionSpec:
    """A valid spec of `function`: one task kind with a reply, a 'generic' template and one named check."""
    fields: dict[str, Any] = dict(
        function=function, role=f"J2.x {function} does its part", goal=f"{function} keeps its part of the run sound",
        yields="a reply", stages=["J2.x"], reads=["charter", "proposals"], writes=["decisions"], may_not=["write the site"],
        task_kinds=[TaskKind(kind="price", summary="price a proposal", reply_family="chart_change", reply_kind="add|reuse")],
        atom_templates=[template("generic"), template("price", goal="the proposal is priced", checks=[CheckRef(name="turn-posted")])],
        version=version)
    return FunctionSpec(**{**fields, **over})


def toy_specs(version: int = 1, **per_function: Any) -> FunctionSpecs:
    """Five valid specs at `version`; `per_function` maps a function name to a dict of FunctionSpec overrides."""
    return FunctionSpecs(specs={fn: toy_spec(fn, version=version, **per_function.get(fn, {})) for fn in FUNCTIONS})


def structural(node_id: str, kind: str, **over: Any) -> StructuralNode:
    return StructuralNode(id=node_id, kind=kind, label=over.pop("label", node_id.title()), **over)


def step(task_id: str = TASK, step_ref: str = "task", parent_id: str | None = "sales", **over: Any) -> StructuralNode:
    """A step node whose id is the library's (`step_node_id`)."""
    return StructuralNode(id=step_node_id(task_id, step_ref), kind="step", label=over.pop("label", f"Step {step_ref}"),
                          task_id=task_id, step_ref=step_ref, parent_id=parent_id, **over)


def stored_edge(kind: str = "depends_on", from_id: str = "sales.priority", to_id: str = "sales.coordination", **over: Any) -> GraphEdge:
    """A stored edge with a source record."""
    source = over.pop("source", EdgeSource(file="workflows.json", workflow="W-4", field="dependencies", value="copy-guide"))
    return make_edge(kind, from_id, to_id, source=source, **over)


def graph_of(chart: OrgChart, *, now: int = 5) -> tuple[list[Node], list[GraphEdge]]:
    """A graph that mirrors `chart`: a structural node for every chart node, five function nodes for every department,
    and the derived edges. Nodes come in the chart's order, the five functions after their department."""
    specs = toy_specs()
    parents = {edge.child: edge.parent for edge in chart.edges}
    nodes: list[Node] = []
    for chart_node in chart.nodes:
        department = chart.department_of(chart_node.id)
        nodes.append(StructuralNode(id=chart_node.id, kind=chart_node.kind, label=chart_node.name, parent_id=parents.get(chart_node.id),
                                    department_id=department, ts_created=now, ts_updated=now))
        if chart_node.kind == "department":
            nodes.extend(new_function_node(chart_node.id, fn, specs, now) for fn in FUNCTIONS)
    return nodes, derive_edges(chart, nodes)


def with_edges(nodes: Sequence[Node], edges: Sequence[GraphEdge]) -> list[Node]:
    """`nodes` with every stored edge listed in the `edge_ids` of both of its ends (the agreement G5 wants)."""
    listed: dict[str, list[str]] = {}
    for edge in edges:
        if edge.kind in ("handoff", "step", "speaks_to", "depends_on"):
            for end in dict.fromkeys((edge.from_id, edge.to_id)):
                listed.setdefault(end, []).append(edge.id)
    return [node.evolve(edge_ids=listed[node.id]) if node.id in listed else node for node in nodes]


def chart_of_two():
    """root, sales (leads), web."""
    return make_chart({"sales": {"leads": {}}, "web": {}})


def function_dict(function: str = "priority", dept: str = "sales", **over: Any) -> dict[str, Any]:
    """A FunctionNode as plain JSON data."""
    data: dict[str, Any] = dict(kind=function, id=f"{dept}.{function}", label=function.capitalize(), department_id=dept,
                                goal="Price every proposal against the room that is left", task="J2.c prices, checks run limits", state="idle")
    return {**data, **over}


def is_function_node(node: Node) -> bool:
    return isinstance(node, FunctionNode)
