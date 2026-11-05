"""ChartChangeRequest, ChartChange and apply_change (library design section 4: rules C1 to C12 and the invalid-input
tables of section 14), slug_id, resolve_alias, carry_links and a 300-step random walk. The chart itself is tested in
test_lib_org_chart.py and the schema the model sees in test_lib_chart_transport.py."""
import json
import random

import pytest

from factories_org import (
    add_op, apply, big_tree, dept_op, div_op, found, make_change, make_chart, merge_op, move_op, new_node, raw_change,
    refused, reject, rename_op, six_node_chart, split_op,
)
from sutra_app.library import org_chart
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.org_chart import (
    MAX_DEPTH, MAX_MOVES, MAX_OPS, ChartChange, ChartChangeInvalid, ChartChangeRequest, ChartChangeResult, FunctionIds,
    LinkPlan, MergeOp, SplitOp, _preserved_problems, apply_change, carry_links, derive_kind, resolve_alias, seed_chart,
    slug_id,
)
from sutra_app.library.registry import REGISTRY
from sutra_app.library.types import FUNCTIONS, NODE_ID_RE, violation

DEEP = {"sales": {"leads": {"inbound": {}, "outbound": {}}, "quotes": {}}, "web": {"menu": {}}}

EXAMPLE = ('{"kind":"add","schema_version":1,"id":"chg-0001","task_id":"req-17","base_revision":1,'
           '"reason":"the brief needs sales and support","reuses":[],"ts":1,"ops":['
           '{"op":"add","node":{"ref":"$sales","kind":"department","name":"Sales","purpose":"","parent":"root"}},'
           '{"op":"add","node":{"ref":"$leads","kind":"division","name":"Leads","purpose":"","parent":"$sales"}}]}')


def ids(chart):
    return [node.id for node in chart.nodes]


def edges(chart):
    return [(edge.parent, edge.child) for edge in chart.edges]


def functions_of(department):
    return [f"{department}.{function}" for function in FUNCTIONS]


# ---- derive_kind and the change model ---------------------------------------------------------------------------

def test_derive_kind_is_reuse_without_ops_add_for_adds_only_and_rearrange_otherwise():
    assert derive_kind([]) == "reuse"
    assert derive_kind([dept_op("$a", "Aa")]) == "add"
    assert derive_kind([dept_op("$a", "Aa"), div_op("$b", "Bb", "$a")]) == "add"
    assert derive_kind([rename_op("sales", name="Revenue")]) == "rearrange"
    assert derive_kind([dept_op("$a", "Aa"), move_op("leads", "web")]) == "rearrange"
    assert derive_kind([merge_op("quotes", "leads")]) == "rearrange"


def test_the_kind_must_be_the_one_the_ops_give():
    assert reject(ChartChange, raw_change(move_op("leads", "web"), kind="add")) == [
        ("", "value_error", "kind is rearrange for these ops, not add")]
    assert reject(ChartChange, raw_change(dept_op("$a", "Aa"), kind="rearrange")) == [
        ("", "value_error", "kind is add for these ops, not rearrange")]
    assert reject(ChartChange, raw_change(dept_op("$a", "Aa"), kind="reuse", reuses=["sales"])) == [
        ("", "value_error", "kind is add for these ops, not reuse")]
    assert reject(ChartChange, raw_change(kind="add")) == [("", "value_error", "kind is reuse for these ops, not add")]


def test_a_reuse_change_must_name_what_it_reuses():
    assert reject(ChartChange, raw_change(kind="reuse")) == [
        ("reuses", "value_error", "a reuse change must name the nodes it reuses")]
    assert ChartChange.model_validate(raw_change(kind="reuse", reuses=["sales"])).kind == "reuse"
    assert ChartChange.model_validate(raw_change(dept_op("$a", "Aa"), reuses=[])).kind == "add"            # only reuse needs them


REF_USES = [
    ("move node", move_op("$x", "web"), "ops.0.node"),
    ("move to_parent", move_op("leads", "$x"), "ops.0.to_parent"),
    ("rename node", rename_op("$x", name="Nn"), "ops.0.node"),
    ("merge into", merge_op("$x", "leads"), "ops.0.into"),
    ("merge source", merge_op("quotes", "leads", "$x"), "ops.0.sources.1"),
    ("add parent", div_op("$a", "Aa", "$x"), "ops.0.node.parent"),
    ("split node", split_op("$x", [new_node("$p", "division", "Pp", "sales")]), "ops.0.node"),
    ("split part parent", split_op("leads", [new_node("$p", "division", "Pp", "$x")]), "ops.0.parts.0.parent"),
    ("split moved child", split_op("leads", [new_node("$p", "division", "Pp", "sales")], [("$x", "$p")]), "ops.0.moves.0.child"),
    ("split target", split_op("leads", [new_node("$p", "division", "Pp", "sales")], [("inbound", "$x")]), "ops.0.moves.0.to"),
]


@pytest.mark.parametrize("op, path", [c[1:] for c in REF_USES], ids=[c[0] for c in REF_USES])
def test_a_ref_must_be_added_before_an_op_uses_it(op, path):
    assert reject(ChartChange, raw_change(op)) == [(path, "value_error", "ref $x is used before it is added")]


def test_a_ref_cannot_be_its_own_parent_and_is_added_once():
    assert reject(ChartChange, raw_change(div_op("$a", "Aa", "$a"))) == [
        ("ops.0.node.parent", "value_error", "ref $a is used before it is added")]
    assert reject(ChartChange, raw_change(dept_op("$a", "Aa"), dept_op("$a", "Bb"))) == [
        ("ops.1.node.ref", "value_error", "ref $a is added twice (first at ops.0.node.ref)")]
    twice = split_op("leads", [new_node("$p", "division", "Pp", "sales"), new_node("$p", "division", "Qq", "sales")])
    assert reject(ChartChange, raw_change(twice))[0][0] == "ops.0.parts.1.ref"


def test_a_ref_may_be_used_by_later_ops_and_by_the_moves_of_the_split_that_adds_it():
    ops = [dept_op("$d", "Delta"), div_op("$v", "Vee", "$d"), move_op("leads", "$v"), rename_op("$d", name="Delta Two"),
           merge_op("$v", "quotes"),
           split_op("leads", [new_node("$p", "division", "Pee", "sales")], [("inbound", "$p"), ("outbound", "leads")])]
    assert ChartChange.model_validate(raw_change(*ops)).kind == "rearrange"


def test_a_rename_needs_a_name_or_a_purpose_and_an_empty_purpose_counts():
    data = raw_change(rename_op("sales", name="Revenue"))
    data["ops"][0]["name"] = None
    assert reject(ChartChange, data) == [("ops.0.rename", "value_error", "a rename needs a new name, a new purpose or both")]
    assert ChartChange.model_validate(raw_change(rename_op("sales", purpose=""))).ops[0].purpose == ""


def test_a_change_holds_at_most_eight_ops():
    assert MAX_OPS == 8
    ops = [dept_op(f"$d{i}", f"Dept {i}") for i in range(9)]
    assert reject(ChartChange, raw_change(*ops))[0][:2] == ("ops", "too_long")
    assert len(ChartChange.model_validate(raw_change(*ops[:8])).ops) == 8


FIELD_CASES = [
    (lambda d: d.update(reason=""), "reason", "string_too_short"),
    (lambda d: d.update(reason="r" * 401), "reason", "string_too_long"),
    (lambda d: d.update(reuses=["sales"] * 11), "reuses", "too_long"),
    (lambda d: d.update(reuses=["Sales"]), "reuses.0", "string_pattern_mismatch"),
    (lambda d: d.update(id="chg-1"), "id", "string_pattern_mismatch"),
    (lambda d: d.update(task_id=""), "task_id", "string_too_short"),
    (lambda d: d.update(task_id="t" * 65), "task_id", "string_too_long"),
    (lambda d: d.update(base_revision=0), "base_revision", "greater_than_equal"),
    (lambda d: d.update(base_revision="1"), "base_revision", "int_type"),
    (lambda d: d.update(ts=-1), "ts", "greater_than_equal"),
    (lambda d: d.update(kind="delete"), "kind", "literal_error"),
    (lambda d: d.update(schema_version=2), "", "value_error"),
    (lambda d: d.update(colour="red"), "colour", "extra_forbidden"),
    (lambda d: d["ops"][0].update(op="teleport"), "ops.0", "union_tag_invalid"),
    (lambda d: d["ops"][0].update(colour="red"), "ops.0.add.colour", "extra_forbidden"),
    (lambda d: d["ops"][0]["node"].update(kind="root"), "ops.0.add.node.kind", "literal_error"),
    (lambda d: d["ops"][0]["node"].update(name=""), "ops.0.add.node.name", "string_too_short"),
    (lambda d: d["ops"][0]["node"].update(name="n" * 81), "ops.0.add.node.name", "string_too_long"),
    (lambda d: d["ops"][0]["node"].update(purpose="p" * 301), "ops.0.add.node.purpose", "string_too_long"),
    (lambda d: d["ops"][0]["node"].update(parent="Sales"), "ops.0.add.node.parent", "string_pattern_mismatch"),
    (lambda d: d["ops"][0]["node"].update(ref="sales"), "ops.0.add.node.ref", "string_pattern_mismatch"),
]


@pytest.mark.parametrize("mutate, path, code", FIELD_CASES, ids=[f"{c[1] or 'schema_version'}-{c[2]}" for c in FIELD_CASES])
def test_the_fields_of_a_change_are_strict_closed_and_bounded(mutate, path, code):
    data = raw_change(dept_op("$sales", "Sales"))
    mutate(data)
    assert reject(ChartChange, data)[0][:2] == (path, code)


def test_the_lists_of_the_ops_are_bounded():
    merge = {"op": "merge", "into": "quotes", "sources": []}
    assert reject(MergeOp, merge)[0][:2] == ("sources", "too_short")
    assert reject(MergeOp, {**merge, "sources": ["aa", "bb", "cc", "dd", "ee"]})[0][:2] == ("sources", "too_long")
    part = new_node("$p", "division", "Pp", "sales").model_dump()
    split = {"op": "split", "node": "leads", "parts": [], "moves": []}
    assert reject(SplitOp, split)[0][:2] == ("parts", "too_short")
    assert reject(SplitOp, {**split, "parts": [part] * 4})[0][:2] == ("parts", "too_long")
    move = {"child": "inbound", "to": "leads"}
    assert reject(SplitOp, {**split, "parts": [part], "moves": [move] * (MAX_MOVES + 1)})[0][:2] == ("moves", "too_long")
    assert len(SplitOp.model_validate({**split, "parts": [part], "moves": [move] * MAX_MOVES}).moves) == MAX_MOVES


def test_the_request_checks_its_refs_too_so_a_bad_reply_is_refused_before_code_builds_a_change():
    data = {"reason": "r", "reuses": [], "ops": [move_op("leads", "$x").model_dump(mode="json")]}
    assert reject(ChartChangeRequest, data) == [("ops.0.to_parent", "value_error", "ref $x is used before it is added")]
    assert reject(ChartChangeRequest, {"reason": "r", "kind": "add"}) == [("kind", "extra_forbidden", "Extra inputs are not permitted")]


def test_every_violation_of_a_change_is_reported_together():
    found_ = reject(ChartChange, raw_change(move_op("leads", "$x"), dept_op("$a", "Aa"), dept_op("$a", "Bb"), kind="add"))
    assert [(path, message) for path, _, message in found_] == [
        ("", "kind is rearrange for these ops, not add"),
        ("ops.0.to_parent", "ref $x is used before it is added"),
        ("ops.2.node.ref", "ref $a is added twice (first at ops.1.node.ref)")]


def test_from_request_adds_the_kind_the_ids_and_the_time_that_code_owns():
    request = ChartChangeRequest(reason="because", ops=[dept_op("$a", "Aa")])
    change = ChartChange.from_request(request, id="chg-0007", task_id="req-9", base_revision=3, ts=5)
    assert (change.kind, change.id, change.task_id, change.base_revision, change.ts) == ("add", "chg-0007", "req-9", 3, 5)
    assert (change.reason, change.reuses, change.ops) == ("because", [], request.ops)
    reuse = ChartChange.from_request(ChartChangeRequest(reason="r", reuses=["sales"]), id="chg-0008", task_id="req-9", base_revision=1)
    assert (reuse.kind, reuse.ts) == ("reuse", 0)
    move = ChartChange.from_request(ChartChangeRequest(reason="r", ops=[move_op("leads", "web")]), id="chg-0009", task_id="r", base_revision=1)
    assert move.kind == "rearrange"
    with pytest.raises(Exception, match="a reuse change must name the nodes it reuses"):
        ChartChange.from_request(ChartChangeRequest(reason="r"), id="chg-0010", task_id="req-9", base_revision=1)


def test_chart_change_is_one_class_with_three_kinds_and_the_request_is_a_payload():
    assert REGISTRY.kinds("chart_change") == {"reuse": ChartChange, "add": ChartChange, "rearrange": ChartChange}
    assert REGISTRY.kinds("chart_change_request") == {"chart_change_request": ChartChangeRequest}
    assert (ChartChange.FAMILY, ChartChange.VERSION) == ("chart_change", 1)


def test_the_gate_checks_a_change_and_its_json_reads_back_equal():
    chart = make_chart(DEEP)
    change = make_change(chart, dept_op("$d", "Delta"), div_op("$v", "Vee", "$d"), move_op("leads", "web"),
                         rename_op("sales", purpose="Money"), merge_op("quotes", "leads"),
                         split_op("quotes", [new_node("$p", "division", "Pee", "sales")], [("inbound", "$p")]))
    checked = GATE.check("chart_change", change)
    assert ChartChange.model_validate_json(checked.json) == change
    assert GATE.check("chart_change", json.loads(checked.json)).sha256 == checked.sha256
    assert (checked.family, checked.kind) == ("chart_change", "rearrange")


def test_the_gate_refuses_a_change_whose_kind_the_ops_contradict():
    bad = ChartChange.model_construct(**{**raw_change(move_op("leads", "web"), kind="add"), "ops": [move_op("leads", "web")]})
    with pytest.raises(GateError) as info:
        GATE.check("chart_change", bad)
    assert info.value.stage == "shape" and "kind is rearrange for these ops, not add" in str(info.value.violations)


# ---- apply_change: the first request, staleness and reuse (C1, C2) ------------------------------------------------

def test_the_first_request_on_an_empty_chart_gives_two_nodes_and_five_function_nodes():
    change = ChartChange.model_validate_json(EXAMPLE)
    result = apply_change(seed_chart(), change)
    assert result.ids == {"$sales": "sales", "$leads": "leads"}
    assert (result.chart.revision, result.chart.updated_ts) == (2, 1)
    assert result.new_function_nodes == functions_of("sales")
    assert ids(result.chart) == ["root", "sales", "leads"] and edges(result.chart) == [("root", "sales"), ("sales", "leads")]
    assert (result.added, result.moved, result.merged, result.aliases) == (["sales", "leads"], [], [], {})
    assert result.chart.node("sales").functions == FunctionIds.for_department("sales")


def test_the_same_change_one_revision_later_is_stale_with_the_documented_text():
    first = apply_change(seed_chart(), ChartChange.model_validate_json(EXAMPLE))
    with pytest.raises(ChartChangeInvalid) as info:
        apply_change(first.chart, ChartChange.model_validate_json(EXAMPLE))
    assert [v.model_dump() for v in info.value.violations] == [{
        "path": "", "code": "stale_base",
        "message": "change is based on revision 1, chart is at 2: read the chart again"}]


def test_a_stale_change_is_refused_with_only_stale_base_even_when_its_ops_are_wrong_too():
    chart = six_node_chart()
    assert found(refused(chart, div_op("$x", "Xx", "ghost-1"), base_revision=3)) == [("", "stale_base")]
    assert found(refused(chart, reuses=["ghost-1"], base_revision=2)) == [("", "stale_base")]
    newer = apply(chart, dept_op("$s", "Support")).chart
    assert found(refused(newer, dept_op("$t", "Tools"), base_revision=1)) == [("", "stale_base")]


def test_a_reuse_change_returns_the_chart_as_it_is():
    chart = six_node_chart()
    result = apply(chart, reuses=["sales", "leads"])
    assert result.chart is chart and result.chart.revision == 1
    assert (result.ids, result.aliases, result.added, result.moved, result.merged, result.new_function_nodes) == ({}, {}, [], [], [], [])


def test_reusing_a_node_that_is_not_there_is_refused():
    exc = refused(six_node_chart(), reuses=["sales", "ghost-1"])
    assert found(exc) == [("reuses.1", "unknown_node")]
    assert exc.violations[0].message == "cannot reuse 'ghost-1': it is not in the chart"


def test_the_reuses_of_an_add_or_rearrange_change_are_checked_against_the_chart_before_the_change():
    chart = six_node_chart()
    assert found(refused(chart, dept_op("$s", "Support"), reuses=["ghost-1"])) == [("reuses.0", "unknown_node")]
    assert apply(chart, merge_op("quotes", "leads"), reuses=["leads"]).merged == ["leads"]          # leads existed before it merged


# ---- C3 add, C10 function nodes -----------------------------------------------------------------------------------

def test_add_a_department_under_the_root_with_its_five_function_nodes():
    chart = six_node_chart()
    result = apply(chart, add_op("$s", "department", "Support", "root", purpose="Answers customers"))
    new = result.chart
    assert new.revision == 2 and ids(new) == ids(chart) + ["support"] and new.parent_of("support") == "root"
    node = new.node("support")
    assert (node.kind, node.name, node.purpose, node.added_in) == ("department", "Support", "Answers customers", 2)
    assert node.functions == FunctionIds.for_department("support")
    assert result.ids == {"$s": "support"} and result.added == ["support"]
    assert result.new_function_nodes == functions_of("support")
    assert (result.moved, result.merged, result.aliases) == ([], [], {})
    assert [n for n in new.nodes if n.id != "support"] == chart.nodes                   # the others are untouched


def test_add_divisions_under_a_department_and_under_a_division():
    chart = six_node_chart()
    result = apply(chart, div_op("$a", "Alpha", "sales"), div_op("$b", "Beta", "$a"), div_op("$c", "Gamma", "leads"))
    new = result.chart
    assert (new.parent_of("alpha"), new.parent_of("beta"), new.parent_of("gamma")) == ("sales", "alpha", "leads")
    assert ids(new) == ids(chart) + ["alpha", "beta", "gamma"]                         # appended in change order
    assert new.node("beta").functions is None and result.new_function_nodes == []
    assert [new.node(i).added_in for i in ("alpha", "beta", "gamma")] == [2, 2, 2]


def test_a_department_hangs_only_under_the_root_and_a_division_only_under_a_department_or_division():
    chart = six_node_chart()
    exc = refused(chart, dept_op("$s", "Support", "sales"))
    assert found(exc) == [("ops.0.node.parent", "bad_parent_kind")]
    assert exc.violations[0].message == "a department hangs under the root, not under the department 'sales'"
    assert found(refused(chart, dept_op("$s", "Support", "leads"))) == [("ops.0.node.parent", "bad_parent_kind")]
    exc = refused(chart, div_op("$s", "Support", "root"))
    assert found(exc) == [("ops.0.node.parent", "bad_parent_kind")]
    assert exc.violations[0].message == "a division hangs under a department or a division, not under the root 'root'"


def test_a_parent_that_is_not_in_the_chart_is_unknown():
    exc = refused(six_node_chart(), div_op("$s", "Support", "ghost-1"))
    assert found(exc) == [("ops.0.node.parent", "unknown_node")]
    assert exc.violations[0].message == "'ghost-1' is not in the chart"


def test_a_name_that_matches_a_sibling_ignoring_case_and_spaces_is_a_duplicate():
    for name in ("LEADS", "leads", "Le ads", "L E A D S", "LEADS\u00a0", "\uff2c\uff25\uff21\uff24\uff33"):
        exc = refused(six_node_chart(), div_op("$x", name, "sales"))
        assert found(exc) == [("ops.0.node.name", "duplicate_name")], name
        assert exc.violations[0].message == "'Sales' (sales) already has 'Leads' (leads): reuse it or pick another name"


def test_the_blank_padded_name_of_the_design_table_is_a_duplicate():
    data = raw_change(div_op("$x", "Xx", "sales"))
    data["ops"][0]["node"]["name"] = " LEADS "
    change = ChartChange.model_validate(data)
    assert change.ops[0].node.name == "LEADS"
    with pytest.raises(ChartChangeInvalid) as info:
        apply_change(six_node_chart(), change)
    assert found(info.value) == [("ops.0.node.name", "duplicate_name")]


def test_a_department_name_must_be_unique_among_the_departments_and_the_same_name_elsewhere_is_fine():
    chart = six_node_chart()
    assert found(refused(chart, dept_op("$x", "SALES"))) == [("ops.0.node.name", "duplicate_name")]
    assert apply(chart, div_op("$x", "Leads", "web")).chart.node("leads-2").name == "Leads"


def test_two_adds_with_one_name_under_one_parent_clash_inside_the_change():
    exc = refused(six_node_chart(), div_op("$a", "Alpha", "sales"), div_op("$b", "alpha", "sales"))
    assert found(exc) == [("ops.1.node.name", "duplicate_name")]


def test_ids_come_from_the_name_and_a_taken_slug_gets_a_number():
    result = apply(six_node_chart(), dept_op("$a", "Support Team"), div_op("$b", "Support Team", "web"),
                   div_op("$c", "Support  team ", "sales"))
    assert result.ids == {"$a": "support-team", "$b": "support-team-2", "$c": "support-team-3"}


def test_the_injected_generator_gives_the_ids_and_sees_every_taken_id():
    seen = []

    def make(kind, name, taken):
        seen.append((kind, name, taken))
        return f"{kind[:3]}-{len(seen)}"

    chart = six_node_chart()
    result = apply(chart, dept_op("$a", "Support"), div_op("$b", "Tier One", "$a"), dept_op("$c", "Tools"), new_id=make)
    assert result.ids == {"$a": "dep-1", "$b": "div-2", "$c": "dep-3"}
    assert [(kind, name) for kind, name, _ in seen] == [("department", "Support"), ("division", "Tier One"), ("department", "Tools")]
    assert seen[0][2] == set(ids(chart)) and seen[1][2] == set(ids(chart)) | {"dep-1"} and seen[2][2] == set(ids(chart)) | {"dep-1", "div-2"}
    assert all(isinstance(taken, frozenset) for _, _, taken in seen)                    # the generator cannot edit the set


def test_a_generator_that_returns_a_taken_or_malformed_id_is_an_invariant_violation():
    for made, text in (("sales", "'sales', which is already used"), ("Not An Id", "'Not An Id', which is not a node id"),
                       (5, "5, which is not a node id"), ("a.b", "which is not a node id")):
        exc = refused(six_node_chart(), dept_op("$a", "Support"), new_id=lambda kind, name, taken: made)
        assert found(exc) == [("ops.0.node", "invariant")], made
        assert text in exc.violations[0].message


def test_a_later_op_can_use_the_ref_of_an_earlier_add_and_a_new_node_counts_as_added_not_moved():
    chart = six_node_chart()
    result = apply(chart, dept_op("$d", "Delta"), div_op("$v", "Vee", "$d"), rename_op("$v", name="Vee Two"),
                   move_op("$v", "sales"))
    assert result.chart.node("vee").name == "Vee Two" and result.chart.parent_of("vee") == "sales"
    assert (result.added, result.moved) == (["delta", "vee"], [])
    assert result.ids == {"$d": "delta", "$v": "vee"} and result.new_function_nodes == functions_of("delta")


def test_an_op_that_needs_the_ref_of_a_failed_add_is_skipped_without_a_second_complaint():
    exc = refused(six_node_chart(), div_op("$a", "Leads", "sales"), div_op("$b", "Inner", "$a"),
                  move_op("menu", "$a"), rename_op("$a", name="Xx"), merge_op("quotes", "$a"),
                  split_op("$a", [new_node("$p", "division", "Pp", "sales")]), move_op("menu", "$p"))
    assert found(exc) == [("ops.0.node.name", "duplicate_name")]


def test_every_bad_op_is_reported_in_op_order_not_only_the_first():
    exc = refused(six_node_chart(), merge_op("ghost-9", "leads"), merge_op("leads", "web"))
    assert found(exc) == [("ops.0.into", "unknown_node"), ("ops.1.sources.0", "merge_not_division")]


def test_two_departments_in_one_change_give_ten_function_node_ids_in_order():
    result = apply(six_node_chart(), dept_op("$a", "Alpha"), div_op("$v", "Vee", "$a"), dept_op("$b", "Beta"))
    assert result.new_function_nodes == functions_of("alpha") + functions_of("beta")


# ---- C4 move ------------------------------------------------------------------------------------------------------

def test_move_a_division_with_its_children_to_another_department():
    chart = make_chart(DEEP)
    result = apply(chart, move_op("leads", "web"))
    new = result.chart
    assert new.parent_of("leads") == "web" and new.children_of("leads") == ["inbound", "outbound"]
    assert ids(new) == ids(chart) and new.node("leads") == chart.node("leads")          # same id, same node, same place in the list
    assert (result.moved, result.added, result.merged, result.aliases) == (["leads"], [], [], {})
    assert new.revision == 2


def test_move_a_division_under_a_division():
    result = apply(make_chart(DEEP), move_op("quotes", "menu"))
    assert result.chart.parent_of("quotes") == "menu" and result.moved == ["quotes"]


def test_a_move_to_the_same_parent_or_back_again_moves_nothing():
    chart = make_chart(DEEP)
    assert apply(chart, move_op("leads", "sales")).moved == []
    there_and_back = apply(chart, move_op("leads", "web"), move_op("leads", "sales"))
    assert there_and_back.moved == [] and there_and_back.chart.revision == 2 and edges(there_and_back.chart) == edges(chart)


def test_a_division_cannot_move_into_itself_or_its_own_subtree():
    chart = make_chart(DEEP)
    exc = refused(chart, move_op("leads", "leads"))
    assert found(exc) == [("ops.0.to_parent", "cycle")] and exc.violations[0].message == "'leads' cannot move into itself"
    exc = refused(chart, move_op("leads", "inbound"))
    assert found(exc) == [("ops.0.to_parent", "cycle")]
    assert exc.violations[0].message == "'inbound' lies inside 'leads': a division cannot move into its own subtree"


def test_only_divisions_move():
    chart = make_chart(DEEP)
    exc = refused(chart, move_op("web", "sales"))
    assert found(exc) == [("ops.0.node", "move_not_division")]
    assert exc.violations[0].message == "'web' is a department: only divisions can be moved"
    assert refused(chart, move_op("root", "sales")).violations[0].message == "'root' is a root: only divisions can be moved"


def test_a_division_cannot_be_moved_under_the_root_or_next_to_a_clashing_name():
    chart = make_chart(DEEP)
    assert found(refused(chart, move_op("menu", "root"))) == [("ops.0.to_parent", "bad_parent_kind")]
    clash = make_chart({"sales": {"menu-copy": {}}, "web": {"menu": {}}}, names={"menu-copy": "Menu"})
    exc = refused(clash, move_op("menu", "sales"))
    assert found(exc) == [("ops.0.to_parent", "duplicate_name")] and "'Menu' (menu-copy)" in exc.violations[0].message


def test_a_move_of_unknown_nodes_reports_both_ends():
    exc = refused(make_chart(DEEP), move_op("ghost-1", "ghost-2"))
    assert found(exc) == [("ops.0.node", "unknown_node"), ("ops.0.to_parent", "unknown_node")]


# ---- C5 rename ----------------------------------------------------------------------------------------------------

def test_rename_changes_the_name_or_the_purpose_and_nothing_else():
    chart = make_chart(DEEP, purposes={"leads": "old"})
    result = apply(chart, rename_op("leads", name="Lead Gen"), rename_op("quotes", purpose="Prices"),
                   rename_op("sales", name="Revenue", purpose="Money"))
    new = result.chart
    assert (new.node("leads").name, new.node("leads").purpose) == ("Lead Gen", "old")
    assert (new.node("quotes").name, new.node("quotes").purpose) == ("Quotes", "Prices")
    sales = new.node("sales")
    assert (sales.id, sales.name, sales.purpose, sales.functions) == ("sales", "Revenue", "Money", chart.node("sales").functions)
    assert ids(new) == ids(chart) and edges(new) == edges(chart) and new.revision == 2
    assert (result.added, result.moved, result.merged, result.aliases, result.new_function_nodes) == ([], [], [], {}, [])


def test_a_purpose_can_be_cleared_and_a_node_can_take_its_own_name_in_another_case():
    chart = make_chart(DEEP, purposes={"leads": "old"})
    result = apply(chart, rename_op("leads", purpose=""), rename_op("quotes", name="QUOTES"))
    assert result.chart.node("leads").purpose == "" and result.chart.node("quotes").name == "QUOTES"


def test_a_rename_may_not_take_a_siblings_name():
    exc = refused(make_chart(DEEP), rename_op("leads", name="quotes"))
    assert found(exc) == [("ops.0.name", "duplicate_name")]
    assert "'Quotes' (quotes) already has that name beside 'leads'" in exc.violations[0].message


def test_the_root_cannot_be_renamed_and_an_unknown_node_is_unknown():
    exc = refused(make_chart(DEEP), rename_op("root", name="Org"))
    assert found(exc) == [("ops.0.node", "unknown_node")]
    assert exc.violations[0].message == "'root' is the root of the chart and cannot be renamed"
    assert found(refused(make_chart(DEEP), rename_op("ghost-1", name="Org"))) == [("ops.0.node", "unknown_node")]


# ---- C6 merge -----------------------------------------------------------------------------------------------------

def test_merge_moves_the_children_removes_the_source_and_records_the_alias():
    chart = make_chart(DEEP)
    result = apply(chart, merge_op("quotes", "leads"))
    new = result.chart
    assert new.node("leads") is None
    assert new.children_of("quotes") == ["inbound", "outbound"] and new.children_of("sales") == ["quotes"]
    assert ids(new) == ["root", "sales", "inbound", "outbound", "quotes", "web", "menu"]
    assert result.aliases == {"leads": "quotes"} and result.merged == ["leads"] and result.moved == ["inbound", "outbound"]
    assert (result.added, result.new_function_nodes) == ([], []) and new.revision == 2
    assert new.node("quotes") == chart.node("quotes")


def test_merge_several_sources_into_one_division():
    chart = make_chart({"sales": {"a1": {"x1": {}}, "b1": {}, "c1": {"y1": {}}, "t1": {}}})
    result = apply(chart, merge_op("t1", "a1", "c1"))
    assert result.aliases == {"a1": "t1", "c1": "t1"} and result.merged == ["a1", "c1"]
    assert result.chart.children_of("t1") == ["x1", "y1"] and result.chart.children_of("sales") == ["b1", "t1"]
    assert result.moved == ["x1", "y1"]


def test_merge_sources_that_lie_inside_each_other_merge_in_order():
    chart = make_chart({"sales": {"a1": {"b1": {"c1": {}}}, "t1": {}}})
    result = apply(chart, merge_op("t1", "a1", "b1"))
    assert result.aliases == {"a1": "t1", "b1": "t1"} and result.chart.children_of("t1") == ["c1"]
    assert result.moved == ["c1"]                                                      # b1 moved, then it was merged away itself


def test_a_node_made_and_merged_away_by_one_change_is_an_alias_but_not_added():
    result = apply(make_chart(DEEP), div_op("$v", "Vee", "sales"), div_op("$w", "Wee", "sales"), merge_op("$w", "$v"))
    assert result.ids == {"$v": "vee", "$w": "wee"} and result.aliases == {"vee": "wee"} and result.merged == ["vee"]
    assert result.added == ["wee"] and result.chart.node("vee") is None and result.moved == []


def test_merges_can_chain_inside_one_change_and_resolve_alias_follows_them():
    chart = make_chart({"sales": {"a1": {}, "b1": {}, "c1": {}}})
    result = apply(chart, merge_op("b1", "a1"), merge_op("c1", "b1"))
    assert result.aliases == {"a1": "b1", "b1": "c1"} and result.merged == ["a1", "b1"]
    assert resolve_alias(result.aliases, "a1") == "c1" and result.chart.children_of("sales") == ["c1"]


def test_only_divisions_merge():
    chart = make_chart(DEEP)
    exc = refused(chart, merge_op("sales", "web"))
    assert found(exc) == [("ops.0.into", "merge_not_division"), ("ops.0.sources.0", "merge_not_division")]
    assert exc.violations[1].message == "'web' is a department: only divisions can be merged"
    assert found(refused(chart, merge_op("quotes", "sales"))) == [("ops.0.sources.0", "merge_not_division")]
    assert found(refused(chart, merge_op("root", "leads"))) == [("ops.0.into", "merge_not_division")]


def test_a_node_cannot_be_merged_into_itself_or_listed_twice():
    chart = make_chart(DEEP)
    exc = refused(chart, merge_op("leads", "leads"))
    assert found(exc) == [("ops.0.sources.0", "bad_merge")] and exc.violations[0].message == "'leads' cannot be merged into itself"
    exc = refused(chart, merge_op("leads", "quotes", "quotes"))
    assert found(exc) == [("ops.0.sources.1", "bad_merge")] and exc.violations[0].message == "'quotes' is listed twice in sources"


def test_a_division_cannot_be_merged_into_its_own_descendant():
    chart = make_chart({"sales": {"a1": {"b1": {}}}})
    exc = refused(chart, merge_op("b1", "a1"))
    assert found(exc) == [("ops.0.into", "cycle")]
    assert exc.violations[0].message == "'b1' lies inside 'a1', which is merged away: merge into a node outside it"
    deep = make_chart({"sales": {"a1": {"b1": {"c1": {}}}, "z1": {}}})
    assert found(refused(deep, merge_op("c1", "z1", "a1"))) == [("ops.0.into", "cycle")]


def test_an_unknown_source_is_unknown_and_a_merged_away_id_says_where_it_went():
    chart = make_chart(DEEP)
    assert found(refused(chart, merge_op("quotes", "ghost-1"))) == [("ops.0.sources.0", "unknown_node")]
    exc = refused(chart, merge_op("quotes", "leads"), rename_op("leads", name="Xx"))
    assert found(exc) == [("ops.1.node", "unknown_node")]
    assert exc.violations[0].message == "'leads' was merged into 'quotes' earlier in this change"


def test_moved_children_may_not_clash_with_the_targets_children_and_a_rename_first_fixes_it():
    chart = make_chart({"sales": {"a1": {"inb": {}}, "t1": {"inb2": {}}}}, names={"inb2": "Inb"})
    exc = refused(chart, merge_op("t1", "a1"))
    assert found(exc) == [("ops.0.sources.0", "duplicate_name")]
    assert "'Inb' (inb) would sit beside 'Inb' (inb2) in 't1': rename one first" in exc.violations[0].message
    result = apply(chart, rename_op("inb2", name="Inb Two"), merge_op("t1", "a1"))
    assert result.chart.children_of("t1") == ["inb", "inb2"]


# ---- C7 split -----------------------------------------------------------------------------------------------------

def test_split_makes_parts_beside_the_division_and_moves_the_listed_children():
    chart = make_chart(DEEP)
    parts = [new_node("$a", "division", "Inbound Team", "sales"), new_node("$b", "division", "Outbound Team", "sales")]
    result = apply(chart, split_op("leads", parts, [("inbound", "$a"), ("outbound", "$b")]))
    new = result.chart
    assert result.ids == {"$a": "inbound-team", "$b": "outbound-team"} and result.added == ["inbound-team", "outbound-team"]
    assert result.moved == ["inbound", "outbound"] and (result.merged, result.aliases, result.new_function_nodes) == ([], {}, [])
    assert new.parent_of("inbound-team") == "sales" and new.children_of("inbound-team") == ["inbound"]
    assert new.parent_of("outbound-team") == "sales" and new.children_of("outbound-team") == ["outbound"]
    assert new.node("leads") == chart.node("leads") and new.children_of("leads") == []          # the node itself stays
    assert ids(new) == ids(chart) + ["inbound-team", "outbound-team"] and new.revision == 2
    assert new.node("inbound-team").added_in == 2 and new.node("inbound-team").functions is None


def test_a_split_can_leave_children_where_they_are_and_a_later_op_can_use_a_part_ref():
    chart = make_chart(DEEP)
    result = apply(chart, split_op("leads", [new_node("$a", "division", "Alpha", "sales")], [("inbound", "leads")]),
                   move_op("quotes", "$a"))
    assert result.chart.children_of("leads") == ["inbound", "outbound"] and result.chart.parent_of("quotes") == "alpha"
    assert result.moved == ["quotes"]


def test_a_split_with_no_moves_only_adds_the_parts():
    result = apply(make_chart(DEEP), split_op("leads", [new_node("$a", "division", "Alpha", "sales")]))
    assert result.added == ["alpha"] and result.moved == [] and result.chart.children_of("alpha") == []


def test_a_part_must_be_a_division_under_the_nodes_own_parent():
    chart = make_chart(DEEP)
    exc = refused(chart, split_op("leads", [new_node("$a", "division", "Alpha", "web")]))
    assert found(exc) == [("ops.0.parts.0.parent", "bad_split_part")]
    assert exc.violations[0].message == "a split part hangs under 'sales', the parent of 'leads', not under 'web'"
    assert found(refused(chart, split_op("leads", [new_node("$a", "department", "Alpha", "sales")]))) == [("ops.0.parts.0.kind", "bad_split_part")]
    exc = refused(chart, split_op("leads", [new_node("$a", "division", "Alpha", "ghost-1")]))
    assert found(exc) == [("ops.0.parts.0.parent", "bad_split_part")] and "not under 'ghost-1'" in exc.violations[0].message
    two = [new_node("$a", "division", "Alpha", "sales"), new_node("$b", "division", "Beta", "$a")]
    assert found(refused(chart, split_op("leads", two))) == [("ops.0.parts.1.parent", "bad_split_part")]


def test_a_part_may_name_its_parent_by_a_ref_that_resolves_to_the_nodes_parent():
    chart = make_chart(DEEP)
    result = apply(chart, dept_op("$d", "Delta"), div_op("$v", "Vee", "$d"),
                   split_op("$v", [new_node("$p", "division", "Pee", "$d")]))
    assert result.chart.parent_of("pee") == "delta" and result.added == ["delta", "vee", "pee"]


def test_a_moved_child_must_be_a_current_child_of_the_node():
    chart = make_chart(DEEP)
    part = [new_node("$a", "division", "Alpha", "sales")]
    exc = refused(chart, split_op("leads", part, [("menu", "$a")]))
    assert found(exc) == [("ops.0.moves.0.child", "not_a_child")] and exc.violations[0].message == "'menu' is not a child of 'leads'"
    exc = refused(chart, split_op("leads", part, [("ghost-1", "$a")]))
    assert found(exc) == [("ops.0.moves.0.child", "not_a_child")] and exc.violations[0].message == "'ghost-1' is not in the chart"
    exc = refused(chart, split_op("leads", part, [("inbound", "$a"), ("inbound", "$a")]))
    assert found(exc) == [("ops.0.moves.1.child", "not_a_child")]
    assert exc.violations[0].message == "'inbound' was already moved by an earlier entry of moves"


def test_a_child_goes_to_a_part_or_stays_and_any_other_target_is_bad():
    chart = make_chart(DEEP)
    part = [new_node("$a", "division", "Alpha", "sales")]
    exc = refused(chart, split_op("leads", part, [("inbound", "quotes")]))
    assert found(exc) == [("ops.0.moves.0.to", "bad_target")]
    assert exc.violations[0].message == "'quotes' is neither a new part nor 'leads': children move to a part or stay"
    assert found(refused(chart, split_op("leads", part, [("inbound", "ghost-1")]))) == [("ops.0.moves.0.to", "bad_target")]


def test_only_a_division_splits():
    chart = make_chart(DEEP)
    exc = refused(chart, split_op("sales", [new_node("$a", "division", "Alpha", "root")]))
    assert found(exc) == [("ops.0.node", "split_not_division")] and exc.violations[0].message == "'sales' is a department: only divisions can be split"
    assert found(refused(chart, split_op("ghost-1", [new_node("$a", "division", "Alpha", "sales")]))) == [("ops.0.node", "unknown_node")]


def test_part_names_follow_the_sibling_name_rule_and_so_do_the_moved_children():
    chart = make_chart(DEEP)
    exc = refused(chart, split_op("leads", [new_node("$a", "division", "Quotes", "sales")]))
    assert found(exc) == [("ops.0.parts.0.name", "duplicate_name")]
    assert found(refused(chart, split_op("leads", [new_node("$a", "division", "LEADS", "sales")]))) == [("ops.0.parts.0.name", "duplicate_name")]
    twice = [new_node("$a", "division", "Alpha", "sales"), new_node("$b", "division", "ALPHA", "sales")]
    assert found(refused(chart, split_op("leads", twice))) == [("ops.0.parts.1.name", "duplicate_name")]
    clash = make_chart({"sales": {"leads": {"i1": {}, "i2": {}}}}, names={"i2": "I1"})
    exc = refused(clash, split_op("leads", [new_node("$a", "division", "Alpha", "sales")], [("i1", "$a"), ("i2", "$a")]))
    assert found(exc) == [("ops.0.moves.1.to", "duplicate_name")]


def test_a_failed_split_changes_nothing_and_its_part_refs_are_not_blamed_again():
    chart = make_chart(DEEP)
    exc = refused(chart, split_op("sales", [new_node("$a", "division", "Alpha", "root")]), move_op("menu", "$a"))
    assert found(exc) == [("ops.0.node", "split_not_division")]
    exc = refused(chart, split_op("leads", [new_node("$a", "division", "Alpha", "sales")], [("menu", "$a")]), move_op("quotes", "$a"))
    assert found(exc) == [("ops.0.moves.0.child", "not_a_child")]


# ---- C8 the result must be a valid chart, C9 nothing is lost ------------------------------------------------------

def test_a_move_that_makes_the_chart_too_deep_is_an_invariant_violation_at_its_place_in_the_new_chart():
    chart = make_chart({"dept": {"d1": {"d2": {"d3": {"d4": {"d5": {}}}}}}, "other": {"x1": {}}})
    assert MAX_DEPTH == 6
    exc = refused(chart, move_op("x1", "d5"))
    assert found(exc) == [("chart.nodes.8", "invariant")]
    assert exc.violations[0].message == "node 'x1' lies more than 6 levels below the root"
    assert apply(chart, move_op("x1", "d4")).chart.parent_of("x1") == "d4"                  # one level less is fine


def test_the_501st_node_is_an_invariant_violation():
    chart = make_chart(big_tree())
    assert len(chart.nodes) == 500
    exc = refused(chart, div_op("$x", "Extra", "d00"))
    assert found(exc) == [("chart.nodes", "invariant")] and "500" in exc.violations[0].message
    assert len(apply(make_chart(big_tree(divisions=478)), div_op("$x", "Extra", "d00")).chart.nodes) == 500


def test_a_lost_id_that_no_alias_excuses_is_reported():
    old = make_chart(DEEP)
    new = make_chart({"sales": {"quotes": {}}, "web": {"menu": {}}})              # leads, inbound and outbound are gone
    problems = _preserved_problems(old, new, {"leads": "quotes"})
    assert [(v.code, v.path) for v in problems] == [("ids_lost", ""), ("ids_lost", "")]
    assert "'inbound'" in problems[0].message and "'outbound'" in problems[1].message
    assert _preserved_problems(old, old, {}) == []


def test_a_changed_function_set_of_a_department_is_reported():
    old = six_node_chart()
    doctored = old.node("sales").model_copy(update={"functions": FunctionIds.for_department("web")})        # skips validation
    new = old.model_copy(update={"nodes": [doctored if n.id == "sales" else n for n in old.nodes]})
    problems = _preserved_problems(old, new, {})
    assert [(v.code, v.message) for v in problems] == [("functions_changed", "the function nodes of department 'sales' changed")]


def test_the_nothing_lost_check_runs_after_the_ops_and_its_findings_are_raised(monkeypatch):
    calls = []

    def fake(old, new, aliases):
        calls.append((old.revision, new.revision, dict(aliases)))
        return [violation("", "ids_lost", "node 'x' disappeared without being merged")]

    monkeypatch.setattr(org_chart, "_preserved_problems", fake)
    exc = refused(make_chart(DEEP), merge_op("quotes", "leads"))
    assert found(exc) == [("", "ids_lost")] and calls == [(1, 2, {"leads": "quotes"})]


def test_apply_change_does_not_rely_on_the_model_check_alone():
    unchecked = ChartChange.model_construct(kind="rearrange", reason="r", reuses=[], ops=[move_op("leads", "$x")],
                                            id="chg-0001", task_id="req-1", base_revision=1, ts=0, schema_version=1)
    with pytest.raises(ChartChangeInvalid) as info:
        apply_change(make_chart(DEEP), unchecked)
    assert found(info.value) == [("ops.0.to_parent", "unknown_node")]
    assert info.value.violations[0].message == "ref $x was not added by an earlier op"


def test_a_split_that_names_the_ref_of_a_failed_add_is_not_blamed_again():
    chart = make_chart(DEEP)
    failed = div_op("$a", "Quotes", "sales")                                       # a sibling of that name exists
    under_it = split_op("leads", [new_node("$p", "division", "Pee", "$a")])
    to_it = split_op("leads", [new_node("$q", "division", "Queue", "sales")], [("inbound", "$a")])
    from_it = split_op("leads", [new_node("$q", "division", "Queue", "sales")], [("$a", "$q")])
    for split in (under_it, to_it, from_it):
        assert found(refused(chart, failed, split)) == [("ops.0.node.name", "duplicate_name")]


def test_a_bad_id_for_a_split_part_is_an_invariant_violation():
    exc = refused(make_chart(DEEP), split_op("leads", [new_node("$p", "division", "Pee", "sales")]),
                  new_id=lambda kind, name, taken: "sales")
    assert found(exc) == [("ops.0.parts.0", "invariant")]


# ---- the whole result: purity, determinism, the gate --------------------------------------------------------------

def test_apply_change_is_pure_and_deterministic():
    chart = make_chart(DEEP)
    change = make_change(chart, merge_op("quotes", "leads"), dept_op("$s", "Support"), div_op("$t", "Tier", "$s"))
    before = (chart.canonical_json(), change.canonical_json())
    first, second = apply_change(chart, change), apply_change(chart, change)
    assert first == second and first.chart is not chart and first.chart.canonical_json() == second.chart.canonical_json()
    assert (chart.canonical_json(), change.canonical_json()) == before


def test_a_refused_change_touches_nothing_and_can_be_tried_again():
    chart = make_chart(DEEP)
    change = make_change(chart, rename_op("sales", name="Revenue"), merge_op("ghost-1", "leads"))
    before = chart.canonical_json()
    for _ in range(2):
        with pytest.raises(ChartChangeInvalid) as info:
            apply_change(chart, change)
        assert found(info.value) == [("ops.1.into", "unknown_node")]
        assert chart.canonical_json() == before and chart.node("sales").name == "Sales"


def test_the_new_chart_passes_the_gate_and_its_revision_follows_the_kind():
    chart = make_chart(DEEP)
    for ops, revision in (((dept_op("$a", "Aa"),), 2), ((rename_op("leads", name="Lead Gen"),), 2), ((), 1)):
        result = apply(chart, *ops, reuses=["sales"] if not ops else ())
        assert result.chart.revision == revision and GATE.check("org_chart", result.chart).model == result.chart


def test_apply_change_takes_a_chart_and_a_change_and_nothing_else():
    chart = six_node_chart()
    with pytest.raises(TypeError):
        apply_change("chart", make_change(chart, reuses=["sales"]))
    with pytest.raises(TypeError):
        apply_change(chart, ChartChangeRequest(reason="r", reuses=["sales"]))
    with pytest.raises(TypeError):
        apply_change(chart, {"kind": "reuse"})


def test_chart_change_invalid_carries_every_violation_and_a_readable_message():
    exc = ChartChangeInvalid([violation("ops.0", "unknown_node", "x is gone"), violation("", "stale_base", "old")])
    assert [v.code for v in exc.violations] == ["unknown_node", "stale_base"]
    assert str(exc) == "chart change refused: unknown_node at ops.0: x is gone (+1 more)"
    assert str(ChartChangeInvalid([violation("", "stale_base", "old")])) == "chart change refused: stale_base at <change>: old"
    assert str(ChartChangeInvalid([])) == "chart change refused: no detail"


# ---- slug_id ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, name, taken, expected", [
    ("division", "Quotes", set(), "quotes"),
    ("division", "Quotes Team", set(), "quotes-team"),
    ("division", "  R&D / Labs!  ", set(), "r-d-labs"),
    ("division", "snake_case name", set(), "snake-case-name"),
    ("division", "Quotes", {"quotes"}, "quotes-2"),
    ("division", "Quotes", {"quotes", "quotes-2", "quotes-3"}, "quotes-4"),
    ("division", "Quotes", {"quotes-2"}, "quotes"),
    ("department", "Café Équipe", set(), "cafe-equipe"),
    ("department", "销售", set(), "department"),
    ("department", "销售", {"department"}, "department-2"),
    ("division", "3D Printing", set(), "division-3d-printing"),
    ("division", "A", set(), "division-a"),
    ("division", "!!!", set(), "division"),
    ("", "!!!", set(), "node"),
    ("division", "x" * 60, set(), "x" * 40),
    ("division", "x" * 60, {"x" * 40}, "x" * 38 + "-2"),
    ("division", "word " * 12, set(), "-".join(["word"] * 8)),
    ("division", "word " * 12, {"-".join(["word"] * 8)}, "-".join(["word"] * 7) + "-wor-2"),            # cut to fit "-2"
])
def test_slug_id_examples(kind, name, taken, expected):
    made = slug_id(kind, name, taken)
    assert made == expected
    assert NODE_ID_RE.fullmatch(made) and made not in taken


def test_slug_ids_are_always_node_ids_that_also_fit_a_department_url():
    rng = random.Random(3)
    alphabet = "abcXYZ019 -_&!é销/. "
    for _ in range(300):
        name = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 70)))
        taken = {slug_id("division", name, set())} if rng.random() < 0.5 else set()
        made = slug_id(rng.choice(["division", "department"]), name, taken)
        assert NODE_ID_RE.fullmatch(made) and made not in taken
        assert all(c.isascii() and (c.isalnum() or c == "-") for c in made) and "--" not in made and not made.endswith("-")


# ---- resolve_alias and carry_links --------------------------------------------------------------------------------

def test_resolve_alias_follows_chains_and_leaves_other_ids_alone():
    aliases = {"a1": "b1", "b1": "c1"}
    assert [resolve_alias(aliases, node) for node in ("a1", "b1", "c1", "zz")] == ["c1", "c1", "c1", "zz"]
    assert resolve_alias({}, "a1") == "a1"


def test_resolve_alias_refuses_a_cycle():
    with pytest.raises(ChartChangeInvalid) as info:
        resolve_alias({"a1": "b1", "b1": "a1"}, "a1")
    assert found(info.value) == [("aliases", "alias_cycle")]
    with pytest.raises(ChartChangeInvalid):
        resolve_alias({"a1": "a1"}, "a1")


def sessions_for(chart, skip=()):
    """One session per node, in the order of the chart: the way ChatStore lists them."""
    return {node.id: f"cs_{node.id}" for node in chart.nodes if node.id not in skip}


def placed(plan):
    """Every session a plan puts somewhere, in no particular order."""
    return sorted([*plan.keep.values(), *plan.move, *plan.archive])


def test_a_merge_keeps_the_survivors_sessions_and_archives_the_merged_ones_under_the_target():
    chart = make_chart(DEEP)
    links = sessions_for(chart)
    plan = carry_links(links, apply(chart, merge_op("quotes", "leads")))
    assert plan.archive == {"cs_leads": "quotes"} and plan.move == {}
    assert plan.keep == {k: v for k, v in links.items() if k != "leads"}
    assert placed(plan) == sorted(links.values())                                   # no session is dropped


def test_a_merged_sessions_moves_to_a_target_that_has_none_and_the_next_ones_are_archived():
    chart = make_chart({"sales": {"a1": {}, "b1": {}, "t1": {}}})
    result = apply(chart, merge_op("t1", "a1", "b1"))
    plan = carry_links(sessions_for(chart, skip=("t1",)), result)
    assert plan.move == {"cs_a1": "t1"} and plan.archive == {"cs_b1": "t1"}
    assert plan.keep == {"root": "cs_root", "sales": "cs_sales"}
    reversed_links = dict(reversed(list(sessions_for(chart, skip=("t1",)).items())))                   # the order of links decides
    again = carry_links(reversed_links, result)
    assert again.move == {"cs_b1": "t1"} and again.archive == {"cs_a1": "t1"}


def test_sessions_follow_alias_chains_to_the_final_target():
    chart = make_chart({"sales": {"a1": {}, "b1": {}, "c1": {}}})
    result = apply(chart, merge_op("b1", "a1"), merge_op("c1", "b1"))
    plan = carry_links(sessions_for(chart), result)
    assert plan.archive == {"cs_a1": "c1", "cs_b1": "c1"} and plan.move == {}
    bare = carry_links(sessions_for(chart, skip=("c1",)), result)
    assert bare.move == {"cs_a1": "c1"} and bare.archive == {"cs_b1": "c1"}


def test_other_changes_keep_every_session():
    chart = make_chart(DEEP)
    links = sessions_for(chart)
    for ops in ((dept_op("$a", "Aa"),), (move_op("leads", "web"),), (rename_op("sales", name="Revenue"),),
                (split_op("leads", [new_node("$p", "division", "Pee", "sales")], [("inbound", "$p")]),)):
        plan = carry_links(links, apply(chart, *ops))
        assert plan.keep == links and plan.move == {} and plan.archive == {}
    assert carry_links({}, apply(chart, merge_op("quotes", "leads"))) == LinkPlan()


def test_a_link_for_a_node_that_is_neither_in_the_chart_nor_merged_away_is_refused():
    chart = make_chart(DEEP)
    result = apply(chart, merge_op("quotes", "leads"))
    with pytest.raises(ChartChangeInvalid) as info:
        carry_links({"ghost-1": "cs_ghost", "sales": "cs_sales"}, result)
    assert found(info.value) == [("links.ghost-1", "unknown_node")]
    assert info.value.violations[0].message == "'ghost-1' is neither in the chart nor merged away by this change"


def test_a_session_linked_to_two_nodes_is_refused_and_so_is_an_alias_that_leads_nowhere():
    chart = make_chart(DEEP)
    result = apply(chart, merge_op("quotes", "leads"))
    with pytest.raises(ChartChangeInvalid) as info:
        carry_links({"sales": "cs_x", "web": "cs_x"}, result)
    assert found(info.value) == [("links.web", "bad_links")]
    assert info.value.violations[0].message == "session 'cs_x' is already linked to 'sales'"
    broken = ChartChangeResult(chart=result.chart, aliases={"leads": "ghost-9"})
    with pytest.raises(ChartChangeInvalid) as info:
        carry_links({"leads": "cs_leads"}, broken)
    assert found(info.value) == [("links.leads", "unknown_node")]
    assert info.value.violations[0].message == "'leads' went into 'ghost-9', which is not in the chart"


def test_a_link_plan_is_closed_and_frozen():
    plan = LinkPlan(keep={"sales": "cs_sales"}, move={"cs_a": "web"}, archive={"cs_b": "web"})
    with pytest.raises(Exception):
        plan.keep = {}
    assert reject(LinkPlan, {"keep": {"Sales": "cs_x"}})[0][0].startswith("keep")
    assert reject(LinkPlan, {"colour": "red"})[0][:2] == ("colour", "extra_forbidden")


# ---- a 300-step random walk ---------------------------------------------------------------------------------------

def random_change(rng, chart, step):
    """One to three random ops on the chart: most are legal, a few are not (a department moved, a division into its
    own subtree, a node merged away earlier in the same change, a chart that gets too deep)."""
    nodes = {n.id: n for n in chart.nodes}
    departments = [i for i, n in nodes.items() if n.kind == "department"]
    divisions = [i for i, n in nodes.items() if n.kind == "division"]
    holders = departments + divisions
    ops, refs = [], 0
    for _ in range(rng.randint(1, 3)):
        roll = rng.random()
        if roll < 0.12 or not holders:
            ops.append(dept_op(f"$n{refs}", f"Dept {step}-{refs}"))
            refs += 1
        elif roll < 0.42:
            ops.append(div_op(f"$n{refs}", f"Div {step}-{refs}", rng.choice(holders)))
            refs += 1
        elif roll < 0.55 and divisions:
            ops.append(move_op(rng.choice(divisions), rng.choice(holders)))
        elif roll < 0.70 and len(nodes) > 1:
            ops.append(rename_op(rng.choice([i for i in nodes if i != "root"]), name=f"Renamed {step}-{refs}"))
        elif roll < 0.82 and len(divisions) >= 2:
            into, source = rng.sample(divisions, 2)
            ops.append(merge_op(into, source))
        elif roll < 0.94 and divisions:
            node = rng.choice(divisions)
            kids = chart.children_of(node)
            moves = [(kid, "$n%d" % refs) for kid in kids[: rng.randint(0, len(kids))]]
            ops.append(split_op(node, [new_node(f"$n{refs}", "division", f"Part {step}-{refs}", chart.parent_of(node))], moves))
            refs += 1
        else:
            ops.append(move_op(rng.choice(departments or ["root"]), rng.choice(holders or ["root"])))
    return ops


def test_a_300_step_random_walk_keeps_ids_aliases_and_function_ids():
    rng = random.Random(20261104)
    chart = seed_chart()
    ever = {"root"}                                    # every id that was ever in the chart: ids are never reused
    aliases = {}                                       # merged-away id -> the node it went into, over all steps
    sessions = {"root": "cs_root"}                     # node -> session of the live nodes
    all_sessions, archived = {"cs_root"}, set()
    applied = rejected = 0
    kinds_applied, refusal_codes = set(), set()
    for step in range(300):
        before = chart.canonical_json()
        ops = random_change(rng, chart, step)
        change = make_change(chart, *ops, ts=step + 1, id=f"chg-{step + 1:04d}")
        try:
            result = apply_change(chart, change, new_id=lambda kind, name, taken: slug_id(kind, name, set(taken) | ever))
        except ChartChangeInvalid as exc:
            rejected += 1
            refusal_codes.update(v.code for v in exc.violations)
            assert exc.violations and all(v.code and v.message for v in exc.violations)
            assert chart.canonical_json() == before                                       # a refused change touches nothing
            continue
        applied += 1
        kinds_applied.update(type(op).__name__ for op in ops)
        new = result.chart
        assert new.revision == chart.revision + 1 and new.updated_ts == step + 1
        assert GATE.check("org_chart", new).model == new                                   # the gate agrees
        old_ids, new_ids = set(ids(chart)), set(ids(new))
        assert old_ids - new_ids <= set(result.aliases)                                    # only merged-away ids vanish
        assert not set(result.added) & ever                                                # an id is never reused
        assert set(result.added) <= new_ids and set(result.added) == new_ids - old_ids
        assert set(result.moved) <= old_ids & new_ids and not set(result.moved) & set(result.added)
        for node in chart.nodes:                                                           # departments never change or move
            if node.kind == "department":
                assert new.node(node.id).functions == node.functions and new.parent_of(node.id) == "root"
        aliases.update(result.aliases)
        assert all(resolve_alias(aliases, gone) in new_ids for gone in aliases)            # every alias ends on a live node
        assert result.new_function_nodes == [f for i in result.added if new.node(i).functions for f in new.node(i).functions.ids()]
        ever |= new_ids | set(result.aliases)
        links = {n.id: sessions[n.id] for n in chart.nodes if n.id in sessions}            # the old chart's node order
        plan = carry_links(links, result)
        assert placed(plan) == sorted(links.values())                                      # carry_links loses no session
        archived |= set(plan.archive)
        for gone in result.aliases:
            sessions.pop(gone, None)
        for session, target in plan.move.items():
            sessions[target] = session
        for added in result.added:
            sessions[added] = f"cs_{added}"
            all_sessions.add(sessions[added])
        assert set(sessions.values()) | archived == all_sessions and not set(sessions.values()) & archived
        assert set(sessions) == new_ids
        chart = new
    assert applied >= 200 and rejected >= 20 and applied + rejected == 300         # the prototype applied 285 of 300
    assert len(refusal_codes) >= 3 and "move_not_division" in refusal_codes
    assert kinds_applied >= {"AddOp", "MoveOp", "RenameOp", "MergeOp", "SplitOp"}
    assert aliases and archived and len(chart.nodes) > 30
    assert chart.revision == applied + 1
