"""The node family, graph edges, `check_graph`, HANDOFFS and the function-spec plug-in (library design section 8; WP L6):
ids and states per kind, the FunctionNode shape, edge rules, the five mirror checks G1 to G5, the spec models and their
loader, `new_function_node`, `refresh_function_nodes`, and the `REGISTRY.verify_refs()` wiring."""
import json
from typing import get_args

import pytest
from pydantic import ValidationError

from factories_node import (
    GENERIC_GOAL, TASK, chart_of_two, codes, function_dict, graph_of, said, step, stored_edge, structural, template, toy_spec,
    toy_specs, violations_of, with_edges,
)
from factories_org import make_chart, six_node_chart
from sutra_app.library import node as node_module
from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.gate import GATE
from sutra_app.library.node import (
    DEFAULT_SPECS_PATH, DERIVED_EDGE_KINDS, FUNCTION_NODE_CLASSES, FUNCTION_STATES, HANDOFFS, MAX_SPECS_BYTES, STORED_EDGE_KINDS,
    STRUCTURE_STATES, AdaptationNode, AtomTemplate, AuditNode, CheckRef, CoordinationNode, EdgeSource, FunctionNode, FunctionSpec,
    FunctionSpecs, FunctionSpecsError, GraphEdge, IdentityNode, Node, NodeState, PriorityNode, StructuralNode, TaskKind,
    check_graph, derive_edges, edge_id, hands_to, load_function_specs, make_edge, may_hand_off, new_function_node,
    refresh_function_nodes, step_node_id,
)
from sutra_app.library.org_chart import seed_chart
from sutra_app.library.registry import REGISTRY, RegistryError
from sutra_app.library.types import FUNCTIONS, IdError

NINE = list(get_args(NodeState))
FIVE = list(FUNCTION_STATES)


# ---- the node family ---------------------------------------------------------------------------------------------

def test_family_registers_nine_kinds_in_the_documented_order():
    kinds = REGISTRY.kinds("node")
    assert list(kinds) == ["root", "department", "division", "step", *FUNCTIONS]
    assert {k for k in list(kinds)[:4]} == {"root", "department", "division", "step"}
    assert all(kinds[k] is StructuralNode for k in ("root", "department", "division", "step"))
    assert [kinds[fn] for fn in FUNCTIONS] == [IdentityNode, AdaptationNode, PriorityNode, CoordinationNode, AuditNode]
    assert Node not in kinds.values() and FunctionNode not in kinds.values()      # abstract: never registered


def test_node_union_picks_the_class_by_kind_and_refuses_an_unknown_kind():
    adapter = REGISTRY.adapter("node")
    assert type(adapter.validate_python(function_dict("audit"))) is AuditNode
    assert type(adapter.validate_python({"kind": "division", "id": "leads", "label": "Leads"})) is StructuralNode
    found = violations_of(lambda: adapter.validate_python({"kind": "treasury", "id": "tr", "label": "T"}))
    assert [v.code for v in found] == ["union_tag_invalid"]


def test_the_documented_function_node_is_valid_and_its_defaults_are_idle_and_empty():
    node = PriorityNode(**function_dict("priority"))
    assert (node.id, node.state, node.detail, node.version, node.edge_ids) == ("sales.priority", "idle", "", 1, [])
    assert (node.context, node.open_atom, node.atom_count, node.wait_on, node.spec_version) == ([], None, 0, None, 1)
    assert node.stats.model_dump() == {"calls": 0, "seconds": 0.0, "tokens": {"input": 0, "output": 0}}
    assert (node.chat_session_id, node.ts_created, node.ts_updated, node.schema_version) == (None, 0, 0, 1)


def test_each_function_class_has_its_kind_and_function_name():
    assert list(FUNCTION_NODE_CLASSES) == list(FUNCTIONS)
    for fn, cls in FUNCTION_NODE_CLASSES.items():
        assert cls.FUNCTION == fn
        assert cls(**{k: v for k, v in function_dict(fn).items() if k != "kind"}).kind == fn
    with pytest.raises(ValidationError):
        IdentityNode(**function_dict("audit"))                    # kind audit on the identity class


def test_function_node_id_must_be_department_dot_function():
    found = violations_of(lambda: PriorityNode(**function_dict("priority", id="sales.audit")))
    assert said(found, "value_error", "'<department id>.<function>'", "sales.priority")


def test_function_node_needs_a_department():
    found = violations_of(lambda: PriorityNode(**{**function_dict("priority"), "department_id": None}))
    assert said(found, "value_error", "belongs to a department") and not any(v.path == "id" for v in found)


@pytest.mark.parametrize("state", [s for s in NINE if s not in FIVE])
def test_function_node_refuses_the_four_other_map_states(state):
    found = violations_of(lambda: PriorityNode(**function_dict("priority", state=state)))
    assert said(found, "value_error", "five", state) or said(found, "value_error", "idle, running", state)


@pytest.mark.parametrize("state", FIVE)
def test_function_node_accepts_its_five_states(state):
    extra = {"wait_on": "you"} if state == "waiting" else {}
    assert PriorityNode(**function_dict("priority", state=state, **extra)).state == state


def test_waiting_function_node_needs_wait_on_but_waiting_on_you_does_not():
    assert said(violations_of(lambda: PriorityNode(**function_dict("priority", state="waiting"))), "value_error", "wait_on")
    assert PriorityNode(**function_dict("priority", state="waiting", wait_on="adaptation")).wait_on == "adaptation"
    assert PriorityNode(**function_dict("priority", state="waiting_on_you")).wait_on is None


def test_function_node_reports_every_violation_at_once():
    found = violations_of(lambda: PriorityNode(**function_dict("priority", id="sales.audit", state="filed", edge_ids=["handoff:a>b"] * 2)))
    assert sorted(v.path for v in found) == ["edge_ids.1", "id", "state"]


@pytest.mark.parametrize("field,value", [
    ("goal", ""), ("goal", "g" * 601), ("task", ""), ("task", "t" * 201), ("context", ["c"] * 41), ("context", [""]),
    ("context", ["c" * 201]), ("open_atom", "atom-1"), ("atom_count", -1), ("atom_count", "1"), ("wait_on", ""),
    ("wait_on", "w" * 41), ("spec_version", 0), ("stats", {"calls": -1}), ("stats", {"seconds": -0.5}),
    ("stats", {"tokens": {"input": -1}}), ("stats", {"calls": "1"}), ("stats", {"gpu": 1}), ("colour", "red"),
    ("label", ""), ("label", "l" * 81), ("detail", "d" * 301), ("chat_session_id", ""), ("version", 0), ("ts_created", -1),
    ("edge_ids", ["e"]), ("edge_ids", ["handoff:a>b"] * 201), ("department_id", "Sales"), ("state", "archived"),
])
def test_node_field_bounds(field, value):
    with pytest.raises(ValidationError):
        PriorityNode(**function_dict("priority", **{field: value}))


def test_function_node_accepts_the_edges_of_its_bounds():
    node = PriorityNode(**function_dict("priority", goal="g" * 600, task="t" * 200, context=["c" * 200] * 40, atom_count=10_000,
                                        open_atom="a-3f9a1c2b7d-01", wait_on="w" * 40, stats={"calls": 3, "seconds": 7, "tokens": {"input": 5}}))
    assert node.stats.seconds == 7.0 and node.stats.tokens.output == 0 and len(node.context) == 40


def test_ids_follow_the_pattern_with_an_optional_function_suffix():
    for good in ("sales", "ab", "a" * 40, "sales.identity", "lead-gen_2", "s-3f9a1c2b7d"):
        assert structural(good, "division").id == good
    for bad in ("Sales", "a", "1sales", "a" * 41, "sales.", "sales.Identity", ".identity", "a.b.c", "sales identity", "a" * 40 + "." + "b" * 17):
        with pytest.raises(ValidationError):
            structural(bad, "division")


def test_edge_ids_must_be_unique_in_a_node():
    found = violations_of(lambda: structural("leads", "division", edge_ids=["step:a>b", "step:a>b"]))
    assert said(found, "value_error", "listed twice") and found[0].path == "edge_ids.1"


def test_evolve_rechecks_the_function_rules():
    node = PriorityNode(**function_dict("priority"))
    assert node.evolve(state="running", detail="pricing").state == "running"
    with pytest.raises(ValidationError):
        node.evolve(state="filed")
    with pytest.raises(ValidationError):
        node.evolve(state="waiting")


def test_a_function_node_goes_through_the_gate_and_back_unchanged():
    checked = GATE.check("node", function_dict("coordination", state="waiting", wait_on="priority"))
    assert checked.kind == "coordination" and type(checked.model) is CoordinationNode
    again = GATE.check("node", json.loads(checked.json))
    assert again.sha256 == checked.sha256


def test_every_model_of_the_module_is_bounded_and_unaliased():
    classes = [StructuralNode, *FUNCTION_NODE_CLASSES.values(), GraphEdge, EdgeSource, FunctionSpecs, FunctionSpec, TaskKind,
               AtomTemplate, CheckRef]
    for cls in classes:
        assert unbounded_fields(cls) == [], cls
        assert aliased_fields(cls) == [], cls


# ---- structural nodes --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["root", "department", "division"])
def test_chart_nodes_use_only_four_states(kind):
    for state in NINE:
        if state in STRUCTURE_STATES:
            assert structural("sales", kind, state=state).state == state
        else:
            found = violations_of(lambda: structural("sales", kind, state=state))
            assert said(found, "value_error", kind, state)
    assert STRUCTURE_STATES == ("idle", "running", "waiting_on_you", "fault")


def test_a_step_node_uses_all_nine_states():
    for state in NINE:
        assert step(state=state).state == state


def test_step_node_needs_task_id_and_step_ref():
    sid = step_node_id(TASK, "task")
    found = violations_of(lambda: StructuralNode(id=sid, kind="step", label="S"))
    assert sorted(v.path for v in found) == ["step_ref", "task_id"]
    assert said(violations_of(lambda: StructuralNode(id=sid, kind="step", label="S", step_ref="task")), "value_error", "task_id")
    assert said(violations_of(lambda: StructuralNode(id=sid, kind="step", label="S", task_id=TASK)), "value_error", "step_ref")


@pytest.mark.parametrize("ref", ["task", "W-1", "W-123", "team:designer", "team:Web Designer", "team:a" + "b" * 33])
def test_step_ref_forms_accepted(ref):
    assert step(step_ref=ref).step_ref == ref


@pytest.mark.parametrize("ref", ["", "tasks", "W-", "W-x", "w-1", "team:", "team: x", "team:" + "x" * 35, "step", "W-1 Builder"])
def test_step_ref_forms_refused(ref):
    with pytest.raises(ValidationError):
        StructuralNode(id=step_node_id(TASK, "task"), kind="step", label="S", task_id=TASK, step_ref=ref)


def test_step_id_is_s_and_ten_hex_digits():
    for bad in ("s-3f9a1c2b7", "s-3f9a1c2b7dd", "s-3g9a1c2b7d", "step-3f9a1c2b7d", "sales"):
        found = violations_of(lambda: StructuralNode(id=bad, kind="step", label="S", task_id=TASK, step_ref="task"))
        assert said(found, "value_error", "step_node_id")


def test_step_node_id_is_the_sha1_prefix_and_depends_on_both_parts():
    import hashlib
    expected = "s-" + hashlib.sha1(f"{TASK}:task".encode()).hexdigest()[:10]
    assert step_node_id(TASK, "task") == expected
    assert step_node_id(TASK, "W-1") != expected and step_node_id("tsk_aaaaaaaaaaaa", "task") != expected
    for args in (("", "task"), (TASK, ""), (None, "task"), (TASK, 3)):
        with pytest.raises(ValueError):
            step_node_id(*args)


@pytest.mark.parametrize("kind,over", [("department", {"step_ref": "task"}), ("division", {"task_id": TASK}), ("root", {"task_id": TASK, "step_ref": "task"})])
def test_only_a_step_has_task_id_and_step_ref(kind, over):
    found = violations_of(lambda: structural("sales", kind, **over))
    assert all(v.code == "value_error" for v in found) and sorted(v.path for v in found) == sorted(over)


def test_structural_node_kind_is_one_of_four():
    for kind in ("function", "identity", "team"):
        with pytest.raises(ValidationError):
            structural("sales", kind)


# ---- edges -------------------------------------------------------------------------------------------------------

def test_edge_kinds_are_seven_and_split_into_stored_and_derived():
    assert set(STORED_EDGE_KINDS) | set(DERIVED_EDGE_KINDS) == set(REGISTRY.kinds("edge"))
    assert set(STORED_EDGE_KINDS).isdisjoint(DERIVED_EDGE_KINDS) and len(REGISTRY.kinds("edge")) == 7


@pytest.mark.parametrize("kind", STORED_EDGE_KINDS)
def test_a_stored_edge_needs_its_source(kind):
    found = violations_of(lambda: make_edge(kind, "sales.priority", "sales.coordination"))
    assert said(found, "value_error", kind, "source")
    assert stored_edge(kind, "web", "sales").source.file == "workflows.json"


@pytest.mark.parametrize("kind", DERIVED_EDGE_KINDS)
def test_a_derived_edge_needs_no_source(kind):
    edge = make_edge(kind, "sales", "leads")
    assert edge.source is None and edge.id == f"{kind}:sales>leads"


def test_an_edge_joins_two_different_nodes():
    found = violations_of(lambda: make_edge("contains", "sales", "sales"))
    assert said(found, "value_error", "different nodes")


def test_edge_id_must_be_kind_colon_from_greater_than_to():
    assert edge_id("step", "a1", "b2") == "step:a1>b2"
    found = violations_of(lambda: GraphEdge(kind="contains", id="contains:sales>web", from_id="sales", to_id="leads"))
    assert said(found, "value_error", "contains:sales>leads")


def test_handoff_inside_one_department_must_be_in_the_table():
    found = violations_of(lambda: stored_edge("handoff", "sales.audit", "sales.priority"))
    assert said(found, "value_error", "audit does not hand off to priority", "identity")
    assert said(violations_of(lambda: stored_edge("handoff", "sales.priority", "sales.audit")), "value_error", "priority does not hand off to audit")


def test_every_listed_handoff_is_accepted_and_every_other_pair_refused():
    for source in FUNCTIONS:
        for target in FUNCTIONS:
            if source == target:
                continue
            build = lambda: stored_edge("handoff", f"sales.{source}", f"sales.{target}")           # noqa: E731
            if target in HANDOFFS[source]:
                assert build().to_id == f"sales.{target}"
            else:
                with pytest.raises(ValidationError):
                    build()


def test_handoff_rule_leaves_other_pairs_and_other_kinds_alone():
    assert stored_edge("handoff", "sales.audit", "web.priority").kind == "handoff"            # two departments
    assert stored_edge("handoff", "sales.audit", "sales").kind == "handoff"                    # not a function node
    assert stored_edge("speaks_to", "sales.audit", "sales.priority").kind == "speaks_to"       # not a handoff
    assert stored_edge("depends_on", "sales.audit", "sales.priority").kind == "depends_on"


@pytest.mark.parametrize("status", ["filed", "running", "waiting", "waiting_on_you", "fault", "not_made", "idle"])
def test_edge_statuses_accepted(status):
    assert make_edge("contains", "sales", "leads", status=status).status == status


@pytest.mark.parametrize("field,value", [
    ("status", "done_unchecked"), ("status", "left_open"), ("from_id", "a>b"), ("from_id", "a b"), ("to_id", ""), ("to_id", "x" * 81),
    ("label", "l" * 201), ("n", -1), ("n", "2"), ("version", 0), ("kind", "reads"), ("kind", "rework"), ("source", {"file": "f"}),
])
def test_edge_field_refusals(field, value):
    base = dict(kind="contains", id="contains:sales>leads", from_id="sales", to_id="leads")
    with pytest.raises(ValidationError):
        GraphEdge(**{**base, field: value})


def test_edge_defaults_and_source_shape():
    edge = make_edge("contains", "sales", "leads")
    assert (edge.label, edge.n, edge.version, edge.status, edge.schema_version) == ("", None, 1, "idle", 1)
    source = EdgeSource(file="goal.json", field="charter", value="")
    assert source.workflow is None
    for bad in ({"file": "", "field": "f", "value": "v"}, {"file": "f", "field": "", "value": "v"}, {"file": "f", "field": "f"},
                {"file": "f", "field": "f", "value": "v", "line": 3}):
        with pytest.raises(ValidationError):
            EdgeSource(**bad)


def test_a_read_and_a_rework_are_labelled_depends_on_edges():
    reads = stored_edge("depends_on", "s-aaaaaaaaaa", "s-bbbbbbbbbb", label="reads")
    revises = stored_edge("depends_on", "s-bbbbbbbbbb", "s-aaaaaaaaaa", label="revises")
    assert (reads.kind, reads.label, revises.label) == ("depends_on", "reads", "revises")


def test_an_edge_goes_through_the_gate():
    checked = GATE.check("edge", stored_edge("step", "sales", "web", n=2).model_dump(mode="json"))
    assert checked.kind == "step" and checked.model.n == 2


# ---- HANDOFFS ----------------------------------------------------------------------------------------------------

def test_handoffs_is_the_documented_table():
    assert HANDOFFS == {
        "identity": ("requester", "adaptation", "priority", "coordination", "audit"),
        "adaptation": ("priority", "identity", "audit", "coordination"),
        "priority": ("adaptation", "identity", "coordination"),
        "coordination": ("priority", "adaptation", "identity", "audit"),
        "audit": ("identity",),
    }
    with pytest.raises(TypeError):
        HANDOFFS["audit"] = ("priority",)            # type: ignore[index]


def test_handoffs_equal_j2_routes_except_coordination_and_audit():
    j2_routes = {                                   # j2.py:103-107 (J2 says "user" where the app says "requester")
        "identity": ("user", "adaptation", "priority", "coordination", "audit"),
        "adaptation": ("priority", "identity", "audit", "coordination"),
        "priority": ("adaptation", "identity", "coordination"),
        "coordination": ("priority", "adaptation", "identity"),
        "audit": ("adaptation", "identity"),
    }
    renamed = {fn: tuple("requester" if t == "user" else t for t in row) for fn, row in j2_routes.items()}
    different = {fn for fn in FUNCTIONS if set(HANDOFFS[fn]) != set(renamed[fn])}
    assert different == {"coordination", "audit"}
    assert set(HANDOFFS["coordination"]) - set(renamed["coordination"]) == {"audit"}      # the code hand-off at queue empty
    assert HANDOFFS["audit"] == ("identity",)                                              # audit hands to Identity only
    assert set(HANDOFFS) == set(FUNCTIONS) and all(fn not in HANDOFFS[fn] for fn in FUNCTIONS)


def test_only_identity_reaches_the_requester():
    assert [fn for fn in FUNCTIONS if "requester" in HANDOFFS[fn]] == ["identity"]


def test_hands_to_is_the_table_without_the_requester():
    assert hands_to("identity") == ["adaptation", "priority", "coordination", "audit"]
    assert hands_to("audit") == ["identity"]
    with pytest.raises(KeyError):
        hands_to("treasury")


def test_may_hand_off_covers_functions_and_workflow_agents():
    assert may_hand_off("priority", "coordination") and not may_hand_off("priority", "audit")
    assert may_hand_off("identity", "requester") and not may_hand_off("audit", "requester")
    assert may_hand_off("W-3", "coordination") and not may_hand_off("W-3", "identity")
    assert not may_hand_off("W-x", "coordination") and not may_hand_off("treasury", "identity")


# ---- derived edges and check_graph -------------------------------------------------------------------------------

def test_derive_edges_gives_contains_has_function_and_has_step():
    chart = chart_of_two()
    nodes, _ = graph_of(chart)
    nodes.append(step(parent_id="sales"))
    derived = derive_edges(chart, nodes)
    by_kind = {k: [e.id for e in derived if e.kind == k] for k in DERIVED_EDGE_KINDS}
    assert by_kind["contains"] == ["contains:root>sales", "contains:root>web", "contains:sales>leads"]
    assert by_kind["has_function"][:5] == [f"has_function:sales>sales.{fn}" for fn in FUNCTIONS]
    assert len(by_kind["has_function"]) == 10 and by_kind["has_step"] == [f"has_step:sales>{step_node_id(TASK, 'task')}"]
    assert derived[:3] == [make_edge("contains", "root", "sales"), make_edge("contains", "root", "web"), make_edge("contains", "sales", "leads")]
    assert derive_edges(chart, [step(parent_id=None)]) == derived[:3]            # a step with no parent has no has_step edge


def test_a_graph_that_mirrors_the_chart_has_no_violation():
    chart = six_node_chart()
    nodes, edges = graph_of(chart)
    assert len(nodes) == 6 + 10 and check_graph(chart, nodes, edges) == []


def test_stored_edges_listed_both_ways_pass():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    handoff = stored_edge("handoff", "sales.priority", "sales.coordination")
    speaks = stored_edge("speaks_to", "sales.identity", "web.identity", n=3)
    edges = [*edges, handoff, speaks]
    assert check_graph(chart, with_edges(nodes, edges), edges) == []


def test_a_chart_with_only_a_root_needs_only_the_root_node():
    chart = seed_chart()
    assert check_graph(chart, [structural("root", "root")], []) == []
    found = check_graph(chart, [], [])
    assert codes(found) == ["G1"] and found[0].path == "nodes.root"


def test_g1_a_chart_node_without_its_graph_node():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    found = check_graph(chart, [n for n in nodes if n.id != "leads"], edges)
    assert any(v.code == "G1" and v.path == "nodes.leads" and "no graph node" in v.message for v in found)


def test_g1_a_node_of_the_wrong_kind_or_class():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    wrong_kind = [n.evolve(kind="division") if n.id == "web" else n for n in nodes]
    assert said(check_graph(chart, wrong_kind, edges), "G1", "web", "division", "department")


def test_g2_a_structural_node_standing_where_a_function_node_belongs():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    clash = [structural("sales.audit", "division") if n.id == "sales.audit" else n for n in nodes]
    found = check_graph(chart, clash, edges)
    assert codes(found) == ["G1", "G2", "G4"]                    # not in the chart; not the function node; its has_function edge now dangles
    assert any(v.code == "G2" and "is not the audit function node" in v.message for v in found)


def test_g1_a_structural_node_the_chart_does_not_have():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    found = check_graph(chart, [*nodes, structural("old-team", "division")], edges)
    assert said(found, "G1", "old-team", "not in the chart")
    assert check_graph(chart, [*nodes, step(parent_id="sales")], [*edges, make_edge("has_step", "sales", step_node_id(TASK, "task"))]) == []


def test_g1_a_node_id_that_appears_twice():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    found = check_graph(chart, [*nodes, nodes[1]], edges)
    assert said(found, "G1", "more than once") and found[0].path == f"nodes.{nodes[1].id}"


def test_g2_a_missing_function_node():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    found = check_graph(chart, [n for n in nodes if n.id != "sales.audit"], [e for e in edges if e.to_id != "sales.audit"])
    assert [(v.code, v.path) for v in found] == [("G2", "nodes.sales.audit")]
    assert "no audit function node" in found[0].message


def test_g2_a_function_node_of_another_department_or_function():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    # defensive branches: nodes built without validation
    wrong_dept = [AuditNode.model_construct(**{**n.model_dump(), "department_id": "web"}) if n.id == "sales.audit" else n for n in nodes]
    assert said(check_graph(chart, wrong_dept, edges), "G2", "belongs to 'web'", "not to 'sales'")
    wrong_kind = [IdentityNode.model_construct(**{**n.model_dump(), "kind": "identity"}) if n.id == "sales.audit" else n for n in nodes]
    assert said(check_graph(chart, wrong_kind, edges), "G2", "is not the audit function node")


def test_g3_a_function_node_of_a_department_the_chart_lacks():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    ghost = new_function_node("ghost", "identity", toy_specs(), 1)
    found = check_graph(chart, [*nodes, ghost], edges)
    assert any(v.code == "G3" and v.path == "nodes.ghost.identity" and "'ghost'" in v.message for v in found)


def test_g3_a_division_or_root_is_not_a_department():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    as_dept = [n.evolve(department_id="leads") if n.id == "web" else n for n in nodes]
    assert said(check_graph(chart, as_dept, edges), "G3", "web", "leads")
    assert said(check_graph(chart, [*nodes, step(parent_id="sales", department_id="root")], edges), "G3", "'root'")
    assert check_graph(chart, [*nodes, step(parent_id="sales", department_id="web")], [*edges, make_edge("has_step", "sales", step_node_id(TASK, "task"))]) == []


def test_g4_an_edge_whose_end_is_not_a_node():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    found = check_graph(chart, nodes, [*edges, stored_edge("step", "sales", "nowhere")])
    assert any(v.code == "G4" and v.path == "edges.step:sales>nowhere" and "'nowhere'" in v.message and "to end" in v.message for v in found)
    assert any(v.code == "G4" and "from end 'ghost'" in v.message for v in check_graph(chart, nodes, [*edges, stored_edge("step", "ghost", "sales")]))


def test_g4_the_contains_edges_must_equal_the_chart():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    missing = check_graph(chart, nodes, [e for e in edges if e.id != "contains:sales>leads"])
    assert [(v.code, v.path) for v in missing] == [("G4", "edges.contains:sales>leads")] and "has no contains edge" in missing[0].message
    extra = check_graph(chart, nodes, [*edges, make_edge("contains", "web", "leads")])
    assert [(v.code, v.path) for v in extra] == [("G4", "edges.contains:web>leads")] and "not in the chart" in extra[0].message
    assert check_graph(chart, nodes, []) != [] and set(codes(check_graph(chart, nodes, []))) == {"G4"}


def test_g4_a_has_function_or_has_step_edge_must_be_what_the_nodes_say():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    wrong_function = [*edges, make_edge("has_function", "web", "sales.audit")]
    assert said(check_graph(chart, nodes, wrong_function), "G4", "has_function:web>sales.audit", "node fields")
    stepper = step(parent_id="sales")
    wrong_step = [*edges, make_edge("has_step", "web", stepper.id)]
    assert said(check_graph(chart, [*nodes, stepper], wrong_step), "G4", "has_step:web>")
    # a derived edge that is simply absent is not data: nothing is reported for it
    assert check_graph(chart, [*nodes, stepper], edges) == []


def test_g4_the_same_edge_id_twice():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    assert said(check_graph(chart, nodes, [*edges, edges[0]]), "G4", "more than once")


def test_g5_node_lists_an_edge_that_is_not_stored():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    lists_unknown = [n.evolve(edge_ids=["step:sales>web"]) if n.id == "sales" else n for n in nodes]
    found = check_graph(chart, lists_unknown, edges)
    assert [(v.code, v.path) for v in found] == [("G5", "nodes.sales.edge_ids")] and "not a stored edge" in found[0].message
    lists_derived = [n.evolve(edge_ids=["contains:root>sales"]) if n.id == "sales" else n for n in nodes]
    assert codes(check_graph(chart, lists_derived, edges)) == ["G5"]                  # contains is derived, never stored


def test_g5_node_lists_a_stored_edge_that_does_not_touch_it():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    edge = stored_edge("step", "sales", "web")
    listed = with_edges(nodes, [*edges, edge])
    mixed = [n.evolve(edge_ids=[edge.id]) if n.id == "leads" else n for n in listed]
    assert said(check_graph(chart, mixed, [*edges, edge]), "G5", "'leads'", "does not touch it")


def test_g5_a_stored_edge_missing_from_an_end_s_edge_ids():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    edge = stored_edge("step", "sales", "web")
    only_from = [n.evolve(edge_ids=[edge.id]) if n.id == "sales" else n for n in nodes]
    found = check_graph(chart, only_from, [*edges, edge])
    assert [(v.code, v.path) for v in found] == [("G5", f"edges.{edge.id}")] and "'web'" in found[0].message
    only_to = [n.evolve(edge_ids=[edge.id]) if n.id == "web" else n for n in nodes]
    assert "'sales'" in check_graph(chart, only_to, [*edges, edge])[0].message


def test_check_graph_reports_every_violation_together_and_changes_nothing():
    chart = chart_of_two()
    nodes, edges = graph_of(chart)
    broken_nodes = [n for n in nodes if n.id not in ("leads", "sales.audit")]
    broken_edges = [*[e for e in edges if e.id != "contains:root>web"], stored_edge("step", "sales", "nowhere")]
    before = ([n.model_dump() for n in broken_nodes], [e.model_dump() for e in broken_edges], chart.model_dump())
    found = check_graph(chart, [*broken_nodes, new_function_node("ghost", "audit", toy_specs(), 1)], broken_edges)
    assert {"G1", "G2", "G3", "G4"} <= set(codes(found))
    assert before == ([n.model_dump() for n in broken_nodes], [e.model_dump() for e in broken_edges], chart.model_dump())


# ---- function specs ----------------------------------------------------------------------------------------------

def test_function_specs_registers_and_validates_a_toy_set():
    assert list(REGISTRY.kinds("function_specs")) == ["function_specs"]
    specs = toy_specs()
    assert list(specs.specs) == list(FUNCTIONS) and specs.kind == "function_specs"
    again = GATE.check("function_specs", specs.model_dump(mode="json"))
    assert again.model == specs and GATE.check("function_specs", specs).sha256 == again.sha256


def test_function_specs_needs_all_five_and_the_right_key():
    five = toy_specs().specs
    short = {k: v for k, v in five.items() if k != "audit"}
    assert said(violations_of(lambda: FunctionSpecs(specs=short)), "value_error", "audit spec is missing")
    swapped = {**five, "audit": five["priority"]}
    found = violations_of(lambda: FunctionSpecs(specs=swapped))
    assert said(found, "value_error", "under 'audit'", "'priority'") and found[0].path == "specs.audit.function"
    with pytest.raises(ValidationError):
        FunctionSpecs(specs={**five, "treasury": five["audit"]})
    with pytest.raises(ValidationError):
        FunctionSpecs(specs={})


def test_function_spec_needs_a_generic_template_and_unique_names():
    assert said(violations_of(lambda: toy_spec(atom_templates=[template("price")])), "value_error", "'generic'")
    found = violations_of(lambda: toy_spec(atom_templates=[template("generic"), template("generic")]))
    assert said(found, "value_error", "two atom templates") and found[0].path == "atom_templates.1.name"
    found = violations_of(lambda: toy_spec(task_kinds=[TaskKind(kind="k", summary="s"), TaskKind(kind="k", summary="t")]))
    assert said(found, "value_error", "two task kinds") and found[0].path == "task_kinds.1.kind"
    assert toy_spec(task_kinds=[]).task_kinds == []


@pytest.mark.parametrize("field,value", [
    ("version", 0), ("role", ""), ("goal", "g" * 601), ("yields", ""), ("yields", "y" * 61), ("stages", ["s"] * 9),
    ("reads", ["r"] * 21), ("reads", ["r" * 81]), ("writes", ["w"] * 21), ("may_not", ["m"] * 21), ("may_not", ["m" * 201]),
    ("function", "treasury"), ("rubric", ["x"]),
])
def test_function_spec_bounds(field, value):
    with pytest.raises(ValidationError):
        toy_spec(**{field: value})


def test_function_spec_list_limits_accept_their_maximum():
    spec = toy_spec(stages=["s"] * 8, reads=["r"] * 20, may_not=["m"] * 20, task_kinds=[TaskKind(kind=f"k{i}", summary="s") for i in range(20)],
                    atom_templates=[template("generic"), *[template(f"t{i}") for i in range(9)]])
    assert len(spec.task_kinds) == 20 and len(spec.atom_templates) == 10
    with pytest.raises(ValidationError):
        toy_spec(task_kinds=[TaskKind(kind=f"k{i}", summary="s") for i in range(21)])
    with pytest.raises(ValidationError):
        toy_spec(atom_templates=[template("generic"), *[template(f"t{i}") for i in range(10)]])


def test_task_kind_defaults_to_no_reply_and_keeps_alternatives():
    assert TaskKind(kind="question", summary="s").reply_family == "" and TaskKind(kind="question", summary="s").reply_kind == ""
    assert TaskKind(kind="x", summary="s", reply_family="priority", reply_kind="a|b").reply_kind == "a|b"
    for bad in ({"kind": "", "summary": "s"}, {"kind": "k", "summary": ""}, {"kind": "k" * 41, "summary": "s"},
                {"kind": "k", "summary": "s" * 201}, {"kind": "k", "summary": "s", "reply_family": "f" * 61}):
        with pytest.raises(ValidationError):
            TaskKind(**bad)


def test_atom_template_goal_may_name_four_fields_only():
    ok = template("t", goal="{function} {kind} {step_label} {task}")
    assert ok.goal == "{function} {kind} {step_label} {task}"
    assert said(violations_of(lambda: template("t", goal="the {colour} goal")), "value_error", "{colour}", "{function}")
    assert said(violations_of(lambda: template("t", goal="a stray { brace")), "value_error", "brace")
    assert said(violations_of(lambda: template("t", goal="a stray } brace")), "value_error", "brace")
    assert template("t", goal="no fields at all").checks == []


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("name", "n" * 61), ("goal", ""), ("goal", "g" * 601), ("work_hint", "skill"), ("work_hint", "ai"),
    ("checks", [{"name": "lint"}]), ("touches", ["t"] * 41), ("touches", [""]), ("work", {}), ("extra", 1),
])
def test_atom_template_bounds(field, value):
    with pytest.raises(ValidationError):
        AtomTemplate(**{"name": "n", "goal": GENERIC_GOAL, "work": {"dispatch_kind": "llm"}, **{field: value}})


def test_check_ref_takes_a_registry_name_and_at_most_eight_args():
    assert CheckRef(name="reply-valid", args=["priority", "price"]).args == ["priority", "price"]
    assert CheckRef(name="turn-posted").args == []
    for bad in ({"name": "lint"}, {"name": "turn-posted", "args": ["a"] * 9}, {"name": "turn-posted", "args": [""]},
                {"name": "turn-posted", "args": ["a" * 501]}, {"name": "turn-posted", "args": [1]}):
        with pytest.raises(ValidationError):
            CheckRef(**bad)
    assert len(template("t", checks=[CheckRef(name="turn-posted")] * 6).checks) == 6
    with pytest.raises(ValidationError):
        template("t", checks=[CheckRef(name="turn-posted")] * 7)


# ---- load_function_specs -----------------------------------------------------------------------------------------

def write_specs(path, specs=None):
    path.write_text(json.dumps((specs or toy_specs()).model_dump(mode="json")), encoding="utf-8")
    return path


def test_load_function_specs_reads_a_file_into_the_same_specs(tmp_path):
    specs = toy_specs(version=3)
    assert load_function_specs(write_specs(tmp_path / "s.json", specs)) == specs
    assert load_function_specs(str(write_specs(tmp_path / "t.json", specs))) == specs


def test_load_function_specs_default_path_is_the_shipped_data_file(tmp_path, monkeypatch):
    assert DEFAULT_SPECS_PATH.parts[-3:] == ("library", "specs", "function_specs.json")
    monkeypatch.setattr(node_module, "DEFAULT_SPECS_PATH", write_specs(tmp_path / "d.json", toy_specs(version=4)))
    assert load_function_specs().specs["audit"].version == 4


def test_load_function_specs_errors_carry_a_code(tmp_path):
    with pytest.raises(FunctionSpecsError) as missing:
        load_function_specs(tmp_path / "nope.json")
    assert missing.value.code == "missing" and "nope.json" in missing.value.detail
    with pytest.raises(FunctionSpecsError) as unreadable:
        load_function_specs(tmp_path)                                      # a directory
    assert unreadable.value.code == "unreadable"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(FunctionSpecsError) as not_json:
        load_function_specs(bad)
    assert not_json.value.code == "not_json"
    bad.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(FunctionSpecsError) as binary:
        load_function_specs(bad)
    assert binary.value.code == "not_json"
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(FunctionSpecsError) as listed:
        load_function_specs(bad)
    assert listed.value.code == "not_json" and "list" in listed.value.detail


def test_load_function_specs_invalid_content_lists_violations(tmp_path):
    data = toy_specs().model_dump(mode="json")
    data["specs"]["identity"]["version"] = 0
    data["specs"]["priority"]["version"] = 0
    path = tmp_path / "inv.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(FunctionSpecsError) as caught:
        load_function_specs(path)
    assert caught.value.code == "invalid" and len(caught.value.violations) >= 2
    assert caught.value.violations[0].path in caught.value.detail


def test_load_function_specs_refuses_a_file_over_one_mebibyte(tmp_path):
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (MAX_SPECS_BYTES + 1))
    with pytest.raises(FunctionSpecsError) as caught:
        load_function_specs(big)
    assert caught.value.code == "too_large"
    ok = write_specs(tmp_path / "ok.json")
    ok.write_bytes(ok.read_bytes().ljust(MAX_SPECS_BYTES))                # exactly the limit, padded with blanks: still read
    assert ok.stat().st_size == MAX_SPECS_BYTES
    assert load_function_specs(ok).kind == "function_specs"


# ---- new_function_node and refresh_function_nodes ---------------------------------------------------------------

@pytest.mark.parametrize("fn", FUNCTIONS)
def test_new_function_node_copies_the_spec_and_starts_idle(fn):
    specs = toy_specs(version=2)
    spec = specs.specs[fn]
    node = new_function_node("sales", fn, specs, 1700)
    assert type(node) is FUNCTION_NODE_CLASSES[fn] and node.kind == fn and node.id == f"sales.{fn}"
    assert (node.goal, node.task, node.context, node.spec_version) == (spec.goal, spec.role, spec.reads, 2)
    assert (node.label, node.department_id, node.state, node.detail) == (fn.capitalize(), "sales", "idle", "")
    assert (node.ts_created, node.ts_updated, node.open_atom, node.atom_count, node.wait_on, node.version) == (1700, 1700, None, 0, None, 1)
    assert node.stats.calls == 0 and node.edge_ids == [] and node.chat_session_id is None


def test_new_function_node_refuses_a_bad_department_or_function():
    specs = toy_specs()
    for dept, fn in (("Sales", "audit"), ("", "audit"), ("sales", "treasury"), ("sales", "")):
        with pytest.raises(IdError):
            new_function_node(dept, fn, specs, 1)
    with pytest.raises(ValidationError):
        new_function_node("sales", "audit", toy_specs(audit={"goal": "g" * 600}), -1)             # a negative clock


def test_new_function_node_does_not_share_the_spec_list():
    specs = toy_specs()
    node = new_function_node("sales", "audit", specs, 1)
    assert node.context == specs.specs["audit"].reads and node.context is not specs.specs["audit"].reads
    assert check_graph(six_node_chart(), graph_of(six_node_chart())[0], graph_of(six_node_chart())[1]) == []


def running(node, **over):
    return node.evolve(state="running", detail="pricing", stats={"calls": 4, "seconds": 2.5, "tokens": {"input": 9, "output": 3}},
                       open_atom="a-3f9a1c2b7d-01", atom_count=7, version=5, chat_session_id="cs-1", ts_updated=99, **over)


def test_refresh_returns_only_nodes_below_the_spec_version_with_four_fields_replaced():
    old = running(new_function_node("sales", "priority", toy_specs(version=1), 10))
    fresh = toy_specs(version=2, priority={"goal": "a new goal", "role": "J2.c new role", "reads": ["new input"]})
    [updated] = refresh_function_nodes(fresh, [old])
    assert (updated.goal, updated.task, updated.context, updated.spec_version) == ("a new goal", "J2.c new role", ["new input"], 2)
    for kept in ("id", "label", "state", "detail", "stats", "open_atom", "atom_count", "version", "chat_session_id", "ts_created",
                 "ts_updated", "department_id", "edge_ids", "wait_on"):
        assert getattr(updated, kept) == getattr(old, kept), kept
    assert type(updated) is PriorityNode and old.spec_version == 1                                  # the input is unchanged


def test_refresh_leaves_current_and_newer_nodes_and_structural_nodes_alone():
    specs = toy_specs(version=3)
    nodes = [new_function_node("sales", "audit", toy_specs(version=3), 1), new_function_node("sales", "identity", toy_specs(version=9), 1),
             structural("sales", "department"), step(), new_function_node("sales", "priority", toy_specs(version=2), 1)]
    out = refresh_function_nodes(specs, nodes)
    assert [n.id for n in out] == ["sales.priority"] and out[0].spec_version == 3


def test_refresh_keeps_the_input_order_and_handles_an_empty_list():
    old = toy_specs(version=1)
    nodes = [new_function_node(d, fn, old, 1) for d in ("web", "sales") for fn in ("audit", "identity")]
    out = refresh_function_nodes(toy_specs(version=2), nodes)
    assert [n.id for n in out] == ["web.audit", "web.identity", "sales.audit", "sales.identity"]
    assert refresh_function_nodes(toy_specs(version=2), []) == []
    assert refresh_function_nodes(toy_specs(version=2), iter(nodes[:1]))[0].id == "web.audit"
    assert refresh_function_nodes(toy_specs(version=2), refresh_function_nodes(toy_specs(version=2), nodes)) == []


def test_refreshed_nodes_pass_the_gate():
    old = new_function_node("sales", "coordination", toy_specs(version=1), 1)
    [updated] = refresh_function_nodes(toy_specs(version=2), [old])
    assert GATE.check("node", updated).model == updated


# ---- REGISTRY.verify_refs wiring ---------------------------------------------------------------------------------

def test_node_module_binds_the_loader_so_verify_refs_checks_the_shipped_specs(tmp_path, monkeypatch):
    good = toy_specs()
    monkeypatch.setattr(node_module, "DEFAULT_SPECS_PATH", write_specs(tmp_path / "good.json", good))
    assert REGISTRY.verify_refs() == []                                                   # five specs were looked at, all resolved
    bad = toy_specs(priority={"task_kinds": [
        TaskKind(kind="price", summary="s", reply_family="chart_change", reply_kind="add|merge"),
        TaskKind(kind="ruling", summary="s", reply_family="no_such_family", reply_kind="x"),
        TaskKind(kind="half", summary="s", reply_family="chart_change")],
        "atom_templates": [template("generic"), template("t", checks=[CheckRef(name="reply-valid", args=["only-one"]),
                                                                       CheckRef(name="turn-posted", args=["extra"])])]})
    monkeypatch.setattr(node_module, "DEFAULT_SPECS_PATH", write_specs(tmp_path / "bad.json", bad))
    found = REGISTRY.verify_refs()
    assert sorted(v.code for v in found) == ["bad_check_args", "bad_check_args", "incomplete_reply_ref", "unknown_reply_family", "unknown_reply_kind"]
    paths = {v.code: v.path for v in found if v.code != "bad_check_args"}
    assert paths["unknown_reply_kind"] == "priority.task_kinds.price.reply_kind" and "'merge'" in next(v.message for v in found if v.code == "unknown_reply_kind")
    assert {v.path for v in found if v.code == "bad_check_args"} == {"priority.atom_templates.t.checks.0.args", "priority.atom_templates.t.checks.1.args"}


def test_verify_refs_looks_at_every_function_not_only_the_first(tmp_path, monkeypatch):
    broken = {fn: {"task_kinds": [TaskKind(kind="k", summary="s", reply_family="chart_change", reply_kind="gone")]} for fn in FUNCTIONS}
    monkeypatch.setattr(node_module, "DEFAULT_SPECS_PATH", write_specs(tmp_path / "all.json", toy_specs(**broken)))
    assert sorted(v.path.split(".")[0] for v in REGISTRY.verify_refs()) == sorted(FUNCTIONS)


def test_verify_refs_fails_loudly_when_the_spec_file_is_not_there(tmp_path, monkeypatch):
    monkeypatch.setattr(node_module, "DEFAULT_SPECS_PATH", tmp_path / "absent.json")
    with pytest.raises(FunctionSpecsError) as caught:
        REGISTRY.verify_refs()
    assert caught.value.code == "missing"                                                 # never a quiet pass over nothing


def test_verify_refs_with_given_specs_uses_the_bound_arity_function():
    found = REGISTRY.verify_refs(toy_specs(audit={"atom_templates": [template("generic"), template("t", checks=[CheckRef(name="answer-recorded")])]}))
    assert [(v.code, v.path) for v in found] == [("bad_check_args", "audit.atom_templates.t.checks.0.args")]
    assert "takes 1 arguments, got 0" in found[0].message
    with pytest.raises(RegistryError) as caught:
        REGISTRY.verify_refs({})
    assert caught.value.code == "specs_empty"
