"""Department (library design section 5, S2-models-14, D48): three fields, id, home_dir and ts_created, and nothing else."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from sutra_app.library.base import aliased_fields, unbounded_fields
from sutra_app.library.department import Department
from sutra_app.library.gate import GATE, GateError
from sutra_app.library.registry import REGISTRY

GOOD = {"kind": "department", "id": "sales", "home_dir": "departments/sales", "ts_created": 1_762_000_000}


def problems(data) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        Department.model_validate(data)
    return [(".".join(str(p) for p in e["loc"]), e["type"]) for e in error.value.errors()]


def test_a_department_is_its_id_its_home_dir_and_its_creation_time():
    dept = Department.model_validate(GOOD)
    assert (dept.id, dept.home_dir, dept.ts_created, dept.kind, dept.schema_version) == ("sales", "departments/sales", 1_762_000_000, "department", 1)
    assert set(Department.model_fields) == {"kind", "schema_version", "id", "home_dir", "ts_created"}


def test_the_family_holds_one_class_and_the_gate_takes_it():
    assert REGISTRY.kinds("department") == {"department": Department}
    checked = GATE.check("department", GOOD)
    assert (checked.family, checked.kind, checked.model) == ("department", "department", Department.model_validate(GOOD))
    assert checked.json == '{"home_dir":"departments/sales","id":"sales","kind":"department","schema_version":1,"ts_created":1762000000}'


@pytest.mark.parametrize("key", ["name", "goal", "budget", "run_ids", "purpose", "status", "created_rev", "ts_updated"])
def test_the_fields_that_have_another_owner_are_refused(key):
    """The name and purpose belong to the chart, the goal to goal.json, the runs to the tasks table, the budget to the run summary."""
    assert problems({**GOOD, key: "x"}) == [(key, "extra_forbidden")]


def test_the_id_is_a_node_id():
    for bad in ("Sales", "s", "1sales", "has space", "a" * 41, ""):
        assert problems({**GOOD, "id": bad}) == [("id", "string_pattern_mismatch")]
    assert Department.model_validate({**GOOD, "id": "web-team_2"}).id == "web-team_2"


def test_every_field_is_needed_and_typed():
    for key in ("id", "home_dir", "ts_created"):
        assert problems({k: v for k, v in GOOD.items() if k != key}) == [(key, "missing")]
    assert problems({**GOOD, "ts_created": "5"}) == [("ts_created", "int_type")]
    assert problems({**GOOD, "ts_created": -1}) == [("ts_created", "greater_than_equal")]
    assert problems({**GOOD, "ts_created": 1.5}) == [("ts_created", "int_type")]


def test_the_kind_and_the_version_are_fixed():
    assert problems({**GOOD, "kind": "dept"}) == [("kind", "literal_error")]
    assert problems({**GOOD, "schema_version": 2}) == [("", "value_error")]
    assert Department(id="sales", home_dir="departments/sales", ts_created=0).kind == "department"          # the kind has a default


def test_home_dir_is_not_empty_and_at_most_200_characters():
    assert problems({**GOOD, "home_dir": ""}) == [("home_dir", "string_too_short")]
    assert problems({**GOOD, "home_dir": "d" * 201}) == [("home_dir", "string_too_long")]
    assert Department.model_validate({**GOOD, "home_dir": "d" * 200}).home_dir == "d" * 200


@pytest.mark.parametrize("path", ["/etc/passwd", "../sales", "departments/../../x", "departments//sales", "departments/./sales",
                                  "departments/sales/", "departments\\sales", "departments/sa\x00les", "departments/sa\nles", ".."])
def test_home_dir_stays_inside_the_data_dir(path):
    assert problems({**GOOD, "home_dir": path}) == [("home_dir", "value_error")]


def test_a_department_is_changed_only_by_evolve():
    dept = Department.model_validate(GOOD)
    assert dept.evolve(ts_created=5).ts_created == 5 and dept.ts_created == 1_762_000_000
    with pytest.raises(ValidationError):
        dept.evolve(home_dir="../x")
    with pytest.raises(ValidationError):
        dept.ts_created = 9                                               # frozen


def test_the_cross_rule_wants_the_department_in_the_chart():
    """`department.in_chart` (gate.py) reads the id of this class: the Department record exists only for a chart node of that id."""
    chart = SimpleNamespace(nodes=[SimpleNamespace(kind="root", id="root"), SimpleNamespace(kind="department", id="sales")])
    with_chart = SimpleNamespace(get=lambda family, id: chart if (family, id) == ("org_chart", "chart") else None)
    assert GATE.check("department", GOOD, ctx=with_chart).model.id == "sales"
    with pytest.raises(GateError) as error:
        GATE.check("department", {**GOOD, "id": "support", "home_dir": "departments/support"}, ctx=with_chart)
    assert (error.value.stage, [v.code for v in error.value.violations]) == ("cross", ["department_not_in_chart"])


def test_the_class_is_bounded_and_aliases_nothing():
    assert unbounded_fields(Department) == [] and aliased_fields(Department) == []
