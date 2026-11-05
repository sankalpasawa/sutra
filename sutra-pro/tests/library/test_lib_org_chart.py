"""OrgChart and its parts (library design section 4; rules V1 to V6 and the invalid-input table of section 14):
FunctionIds, OrgNode, OrgEdge, the sorted edges, the tree helpers, seed_chart, the gate, and the design rules for bounded
fields. Changes to the chart are in test_lib_chart_change.py."""
import json
import random
import time

import pytest
from pydantic import ValidationError

from factories_org import SIX, big_tree, chain, make_chart, raw_chart, reject, six_node_chart
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.org_chart import (
    MAX_DEPTH, MAX_EDGES, MAX_NODES, ChartChange, ChartChangeRequest, ChartChangeResult, FunctionIds, LinkPlan, OrgChart,
    OrgEdge, OrgNode, seed_chart,
)
from sutra_app.library.registry import REGISTRY
from sutra_app.library.types import FUNCTIONS, IdError

DEEP = {"sales": {"leads": {"inbound": {}, "outbound": {}}, "quotes": {}}, "web": {"menu": {}}}


def paths(found, code=None):
    return [path for path, c, _ in found if code is None or c == code]


def messages(found):
    return [message for _, _, message in found]


# ---- FunctionIds ------------------------------------------------------------------------------------------------

def test_for_department_builds_the_five_ids_in_function_order():
    ids = FunctionIds.for_department("sales")
    assert ids.ids() == ["sales.identity", "sales.adaptation", "sales.priority", "sales.coordination", "sales.audit"]
    assert (ids.identity, ids.audit) == ("sales.identity", "sales.audit")
    assert tuple(FunctionIds.model_fields) == FUNCTIONS


def test_for_department_refuses_an_id_that_is_not_a_node_id():
    for bad in ("Sales", "sales.audit", "", "a"):
        with pytest.raises(IdError):
            FunctionIds.for_department(bad)


def test_the_five_function_ids_must_all_differ():
    found = reject(FunctionIds, {function: "sales.identity" for function in FUNCTIONS})
    assert found == [("", "value_error", "the five function node ids must all be different")]
    almost = FunctionIds.for_department("sales").model_dump()
    almost["audit"] = almost["priority"]
    assert paths(reject(FunctionIds, almost)) == [""]


def test_function_ids_are_closed_strict_and_complete():
    ok = FunctionIds.for_department("sales").model_dump()
    assert paths(reject(FunctionIds, {**ok, "extra": "x"}), "extra_forbidden") == ["extra"]
    assert reject(FunctionIds, {**ok, "audit": 5})[0][:2] == ("audit", "string_type")
    assert reject(FunctionIds, {**ok, "audit": ""})[0][:2] == ("audit", "string_too_short")
    assert reject(FunctionIds, {**ok, "audit": "x" * 61})[0][:2] == ("audit", "string_too_long")
    missing = dict(ok)
    del missing["audit"]
    assert reject(FunctionIds, missing)[0][:2] == ("audit", "missing")


# ---- OrgNode ----------------------------------------------------------------------------------------------------

def test_a_department_must_carry_its_five_function_nodes():
    data = raw_chart()
    data["nodes"][1]["functions"] = None
    assert reject(OrgChart, data) == [("nodes.1", "value_error", "a department must carry its five function nodes")]


def test_the_function_ids_must_be_the_departments_own():
    data = raw_chart()
    data["nodes"][1]["functions"]["audit"] = "web.audit"
    [(path, code, message)] = reject(OrgChart, data)
    assert (path, code) == ("nodes.1", "value_error")
    assert "sales" in message and "sales.identity" in message and "sales.audit" in message


def test_a_missing_function_is_a_missing_field_at_its_name():
    data = raw_chart()
    del data["nodes"][1]["functions"]["audit"]
    assert reject(OrgChart, data)[0][:2] == ("nodes.1.functions.audit", "missing")


def test_only_a_department_carries_function_nodes():
    for index, kind in ((0, "root"), (2, "division")):
        data = raw_chart()
        data["nodes"][index]["functions"] = data["nodes"][1]["functions"]
        assert reject(OrgChart, data) == [
            (f"nodes.{index}", "value_error", f"only a department carries function nodes, not a {kind}")]


def test_node_fields_are_stripped_bounded_and_closed():
    node = OrgNode(id="sales", kind="department", name="  Sales  ", functions=FunctionIds.for_department("sales"))
    assert (node.name, node.purpose, node.added_in) == ("Sales", "", 1)
    base = {"id": "leads", "kind": "division", "name": "Leads"}
    assert reject(OrgNode, {**base, "name": ""})[0][:2] == ("name", "string_too_short")
    assert reject(OrgNode, {**base, "name": "   "})[0][:2] == ("name", "string_too_short")
    assert reject(OrgNode, {**base, "name": "x" * 81})[0][:2] == ("name", "string_too_long")
    assert OrgNode.model_validate({**base, "name": "x" * 80}).name == "x" * 80
    assert reject(OrgNode, {**base, "purpose": "p" * 301})[0][:2] == ("purpose", "string_too_long")
    assert OrgNode.model_validate({**base, "purpose": "p" * 300}).purpose == "p" * 300
    assert reject(OrgNode, {**base, "added_in": 0})[0][:2] == ("added_in", "greater_than_equal")
    assert reject(OrgNode, {**base, "kind": "team"})[0][:2] == ("kind", "literal_error")
    assert reject(OrgNode, {**base, "colour": "red"})[0][:2] == ("colour", "extra_forbidden")
    assert reject(OrgNode, {**base, "added_in": "1"})[0][:2] == ("added_in", "int_type")


def test_node_and_edge_ids_must_be_node_ids():
    for bad in ("Sales", "a", "x" * 41, "1sales", "sales.audit", "sa les", ""):
        assert reject(OrgNode, {"id": bad, "kind": "division", "name": "N"})[0][:2] == ("id", "string_pattern_mismatch"), bad
        assert reject(OrgEdge, {"parent": bad, "child": "leads"})[0][:2] == ("parent", "string_pattern_mismatch"), bad
        assert reject(OrgEdge, {"parent": "sales", "child": bad})[0][:2] == ("child", "string_pattern_mismatch"), bad


def test_an_edge_is_closed():
    assert reject(OrgEdge, {"parent": "a1", "child": "b1", "label": "x"})[0][:2] == ("label", "extra_forbidden")


# ---- OrgChart: shape --------------------------------------------------------------------------------------------

def test_seed_chart_is_revision_one_with_only_the_root():
    chart = seed_chart()
    assert (chart.revision, chart.updated_ts, chart.edges, chart.kind, chart.schema_version) == (1, 0, [], "org_chart", 1)
    assert [(n.id, n.kind, n.name, n.purpose, n.functions, n.added_in) for n in chart.nodes] == [
        ("root", "root", "Root", "", None, 1)]
    other = seed_chart("org", 77)
    assert other.nodes[0].id == "org" and other.updated_ts == 77


def test_seed_chart_refuses_a_root_id_that_is_not_a_node_id():
    with pytest.raises(ValidationError):
        seed_chart("Root")


def test_org_chart_is_one_registered_class_of_its_family():
    assert REGISTRY.kinds("org_chart") == {"org_chart": OrgChart}
    assert REGISTRY.versions("org_chart") == [1]
    assert (OrgChart.FAMILY, OrgChart.VERSION) == ("org_chart", 1)


@pytest.mark.parametrize("change, path, code", [
    ({"colour": "red"}, "colour", "extra_forbidden"),
    ({"revision": 0}, "revision", "greater_than_equal"),
    ({"revision": "1"}, "revision", "int_type"),
    ({"revision": 1.0}, "revision", "int_type"),
    ({"revision": True}, "revision", "int_type"),
    ({"kind": "org"}, "kind", "literal_error"),
    ({"schema_version": 2}, "", "value_error"),
    ({"updated_ts": -1}, "updated_ts", "greater_than_equal"),
    ({"nodes": []}, "nodes", "too_short"),
    ({"edges": "x"}, "edges", "list_type"),
])
def test_chart_fields_are_strict_closed_and_bounded(change, path, code):
    assert reject(OrgChart, {**raw_chart(), **change})[0][:2] == (path, code)


def test_a_node_id_with_capitals_is_refused_inside_a_chart():
    data = raw_chart()
    data["nodes"][1]["id"] = "Sales"
    assert reject(OrgChart, data)[0][:2] == ("nodes.1.id", "string_pattern_mismatch")


# ---- OrgChart: the tree rules V1 to V6 --------------------------------------------------------------------------

def _two_loose_divisions(data):
    """Two divisions that only point at each other: a cycle that the root does not reach."""
    for name in ("aa", "bb"):
        data["nodes"].append({"id": name, "kind": "division", "name": name.upper(), "purpose": "", "functions": None, "added_in": 1})
    data["edges"] += [{"parent": "aa", "child": "bb"}, {"parent": "bb", "child": "aa"}]


def _move_edge(data, child, parent):
    for edge in data["edges"]:
        if edge["child"] == child:
            edge["parent"] = parent


TREE_CASES = [
    ("two roots", lambda d: d["nodes"][2].update(kind="root", functions=None), "nodes.2", "a chart has one root, 'root': 'leads' cannot be a second"),
    ("no root", lambda d: d["nodes"][0].update(kind="division"), "nodes", "the chart has no root node"),
    ("duplicate id", lambda d: d["nodes"][2].update(id="sales"), "nodes.2.id", "duplicate node id 'sales' (also nodes.1)"),
    ("node without a parent edge", lambda d: d["edges"].pop(0), "nodes.1", "node 'sales' has no parent edge"),
    ("node with two parents", lambda d: d["edges"].append({"parent": "web", "child": "leads"}), "edges.4",
     "node 'leads' has 2 parents: 'sales', 'web'"),
    ("cycle aa<->bb", _two_loose_divisions, "nodes.6", "cycle: aa -> bb -> aa"),
    ("edge to a missing node", lambda d: d["edges"].append({"parent": "sales", "child": "ghost"}), "edges.2.child",
     "edge child 'ghost' is not a node of the chart"),
    ("edge from a missing node", lambda d: d["edges"].append({"parent": "ghost", "child": "menu"}), "edges.0.parent",
     "edge parent 'ghost' is not a node of the chart"),
    ("division under the root", lambda d: _move_edge(d, "leads", "root"), "edges.0",
     "division 'leads' hangs under a department or a division, not under the root 'root'"),
    ("department under a division", lambda d: _move_edge(d, "web", "leads"), "edges.0",
     "department 'web' hangs under the root, not under the division 'leads'"),
    ("root with a parent", lambda d: d["edges"].append({"parent": "sales", "child": "root"}), "edges.4",
     "the root 'root' cannot have a parent"),
    ("a node under itself", lambda d: d["edges"].append({"parent": "leads", "child": "leads"}), "nodes.2", "cycle: leads -> leads"),
]


@pytest.mark.parametrize("mutate, path, message", [c[1:] for c in TREE_CASES], ids=[c[0] for c in TREE_CASES])
def test_the_tree_rules_reject_each_broken_chart(mutate, path, message):
    data = raw_chart()
    mutate(data)
    found = reject(OrgChart, data)
    assert (path, "value_error", message) in found
    assert all(code == "value_error" for _, code, _ in found)


def test_every_chart_violation_is_reported_together_not_the_first_only():
    data = raw_chart()
    data["edges"] = [e for e in data["edges"] if e["child"] != "web"]          # web has no parent edge
    data["edges"].append({"parent": "sales", "child": "ghost"})                 # an edge to nowhere
    _move_edge(data, "menu", "root")                                            # a division under the root
    assert reject(OrgChart, data) == [
        ("edges.2.child", "value_error", "edge child 'ghost' is not a node of the chart"),
        ("nodes.4", "value_error", "node 'web' has no parent edge"),
        ("edges.0", "value_error", "division 'menu' hangs under a department or a division, not under the root 'root'"),
    ]


def test_a_repeated_department_breaks_the_unique_function_ids_as_well_as_the_unique_ids():
    data = raw_chart()
    data["nodes"].append(dict(data["nodes"][1]))                                # 'sales' twice, functions and all
    found = reject(OrgChart, data)
    assert "duplicate node id 'sales' (also nodes.1)" in messages(found)
    assert "function node id 'sales.identity' is also used by nodes.1" in messages(found)
    assert paths(found, "value_error").count("nodes.6.functions") == 5


def test_the_depth_limit_is_six_edges_below_the_root():
    assert MAX_DEPTH == 6
    assert len(make_chart(chain(MAX_DEPTH - 1)).nodes) == 1 + 1 + (MAX_DEPTH - 1)          # depth 6: still a valid chart
    with pytest.raises(ValidationError) as info:
        make_chart(chain(MAX_DEPTH))
    text = str(info.value)
    assert "node 'div5' lies more than 6 levels below the root" in text


def test_a_too_deep_chain_is_reported_once_at_its_first_node_too_deep():
    data = raw_chart(make_chart(chain(MAX_DEPTH - 1)))
    for i in range(MAX_DEPTH - 1, MAX_DEPTH + 4):                                # four nodes too deep
        data["nodes"].append({"id": f"div{i}", "kind": "division", "name": f"Div{i}", "purpose": "", "functions": None, "added_in": 1})
        data["edges"].append({"parent": "dept" if i == 0 else f"div{i - 1}", "child": f"div{i}"})
    found = reject(OrgChart, data)
    assert messages(found) == ["node 'div5' lies more than 6 levels below the root"]
    assert paths(found) == [f"nodes.{1 + 1 + 5}"]


def test_two_chains_that_are_too_deep_are_each_reported():
    tree = {"aa": {}, "bb": {}}
    for name in ("aa", "bb"):
        level = tree[name]
        for i in range(MAX_DEPTH):
            level[f"{name}{i}"] = {}
            level = level[f"{name}{i}"]
    with pytest.raises(ValidationError) as info:
        make_chart(tree)
    assert "node 'aa5' lies more than 6 levels" in str(info.value) and "node 'bb5' lies more than 6 levels" in str(info.value)


def test_a_chart_of_500_nodes_is_valid_and_fast_and_501_is_not():
    start = time.monotonic()
    chart = make_chart(big_tree())
    assert len(chart.nodes) == MAX_NODES == 500 and len(chart.edges) == 499 <= MAX_EDGES
    assert time.monotonic() - start < 5.0                                       # O(n * depth): milliseconds in practice
    assert len(OrgChart.model_validate(chart.model_dump(mode="json")).nodes) == 500
    data = raw_chart(chart)
    data["nodes"].append({"id": "extra", "kind": "division", "name": "Extra", "purpose": "", "functions": None, "added_in": 1})
    data["edges"].append({"parent": "d00", "child": "extra"})
    assert reject(OrgChart, data)[0][:2] == ("nodes", "too_long")


def test_more_than_500_edges_are_refused():
    data = raw_chart()
    data["edges"] = data["edges"] + [{"parent": "sales", "child": f"x{i:03d}"} for i in range(MAX_EDGES)]
    assert ("edges", "too_long") in [p[:2] for p in reject(OrgChart, data)]


# ---- OrgChart: edges and nodes keep a stable order ---------------------------------------------------------------

def test_edges_are_sorted_by_parent_then_child_so_the_json_is_stable():
    chart = make_chart({"web": {"menu": {}}, "sales": {"quotes": {}, "leads": {}}})
    pairs = [(e.parent, e.child) for e in chart.edges]
    assert pairs == [("root", "sales"), ("root", "web"), ("sales", "leads"), ("sales", "quotes"), ("web", "menu")]
    shuffled = raw_chart(chart)
    random.Random(7).shuffle(shuffled["edges"])
    again = OrgChart.model_validate(shuffled)
    assert again == chart and again.canonical_json() == chart.canonical_json()


def test_edges_given_as_models_are_sorted_too_and_nodes_keep_their_order():
    chart = make_chart({"web": {}, "sales": {"leads": {}}})
    again = OrgChart(nodes=chart.nodes, edges=list(reversed(chart.edges)))
    assert again == chart
    assert [n.id for n in again.nodes] == ["root", "web", "sales", "leads"]             # not alphabetical


def test_malformed_edges_get_the_field_error_and_do_not_crash_the_sort():
    base = raw_chart()
    assert reject(OrgChart, {**base, "edges": [1, 2]})[0][:2] == ("edges.0", "model_type")
    assert reject(OrgChart, {**base, "edges": [{"parent": 1, "child": "x"}]})[0][:2] == ("edges.0.parent", "string_type")
    assert reject(OrgChart, {**base, "edges": [{"parent": "sales"}]})[0][:2] == ("edges.0.child", "missing")


def test_the_gate_accepts_a_chart_and_its_sha_does_not_depend_on_key_order():
    chart = six_node_chart()
    checked = GATE.check("org_chart", chart)
    assert checked.model == chart and (checked.family, checked.kind) == ("org_chart", "org_chart")
    assert checked.json == chart.canonical_json()
    raw = raw_chart()
    reordered = {key: raw[key] for key in reversed(list(raw))}
    reordered["nodes"] = [{key: node[key] for key in reversed(list(node))} for node in raw["nodes"]]
    reordered["edges"] = list(reversed(raw["edges"]))
    assert GATE.check("org_chart", json.dumps(reordered)).sha256 == checked.sha256


def test_a_chart_built_with_model_construct_cannot_get_past_the_gate():
    broken = OrgChart.model_construct(revision=1, nodes=six_node_chart().nodes, edges=[], updated_ts=0,
                                      kind="org_chart", schema_version=1)
    with pytest.raises(GateError) as info:
        GATE.check("org_chart", broken)
    assert info.value.stage == "shape" and "has no parent edge" in str(info.value.violations)


def test_a_chart_is_frozen_and_evolve_checks_again():
    chart = six_node_chart()
    with pytest.raises(ValidationError):
        chart.revision = 2
    assert chart.evolve(revision=2).revision == 2 and chart.revision == 1
    with pytest.raises(ValidationError):
        chart.evolve(revision=0)
    with pytest.raises(ValidationError):
        chart.evolve(edges=[])                                                  # nodes without parent edges


# ---- reading the tree --------------------------------------------------------------------------------------------

def test_node_returns_the_node_or_none():
    chart = make_chart(DEEP)
    assert chart.node("leads").name == "Leads" and chart.node("sales").kind == "department"
    assert chart.node("ghost") is None and chart.node("sales.audit") is None


def test_parent_of_gives_the_parents_id():
    chart = make_chart(DEEP)
    assert chart.parent_of("inbound") == "leads" and chart.parent_of("sales") == "root"
    assert chart.parent_of("root") is None and chart.parent_of("ghost") is None


def test_children_of_follow_the_order_of_nodes_not_the_alphabet():
    chart = make_chart({"sales": {"zeta": {}, "alpha": {}}, "web": {}})
    assert chart.children_of("sales") == ["zeta", "alpha"]
    assert chart.children_of("root") == ["sales", "web"]
    assert chart.children_of("alpha") == [] and chart.children_of("ghost") == []


def test_subtree_is_the_node_then_everything_below_depth_first():
    chart = make_chart(DEEP)
    assert chart.subtree("sales") == ["sales", "leads", "inbound", "outbound", "quotes"]
    assert chart.subtree("inbound") == ["inbound"]
    assert chart.subtree("root") == [n.id for n in chart.nodes]
    assert chart.subtree("ghost") == []


def test_department_of_is_the_node_or_the_department_above_it():
    chart = make_chart(DEEP)
    assert chart.department_of("inbound") == "sales" and chart.department_of("menu") == "web"
    assert chart.department_of("sales") == "sales"
    assert chart.department_of("root") is None and chart.department_of("ghost") is None


def test_a_function_node_id_names_its_department_by_the_prefix():
    chart = six_node_chart()
    sales = chart.node("sales")
    assert sales.functions == FunctionIds.for_department("sales")
    assert {fid.split(".")[0] for node in chart.nodes if node.functions for fid in node.functions.ids()} == {"sales", "web"}


# ---- the design rules for the library's classes -------------------------------------------------------------------

def test_every_string_and_list_is_bounded_and_no_field_has_an_alias():
    for cls in (OrgChart, OrgNode, OrgEdge, FunctionIds, ChartChangeRequest, ChartChange, ChartChangeResult, LinkPlan):
        assert unbounded_fields(cls) == [], cls
        assert aliased_fields(cls) == [], cls


def test_the_documented_sizes_are_the_constants():
    assert (MAX_NODES, MAX_EDGES, MAX_DEPTH) == (500, 500, 6)
    assert SIX == {"sales": {"leads": {}, "quotes": {}}, "web": {"menu": {}}}
