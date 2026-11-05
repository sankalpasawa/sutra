"""Value and Record (library design 3.1) and the scalars, Violation and DomainEvent of types.py (3.2)."""
import datetime
import enum
import json
import uuid
from types import SimpleNamespace
from typing import Annotated, Literal, Optional, Union

import pytest
from pydantic import Field, StringConstraints, TypeAdapter, ValidationError

from sutra_app.library import base as base_module
from sutra_app.library.base import (
    Record, Value, aliased_fields, canonical_json, discriminator_of, is_abstract, nested_models, require_pydantic,
    unbounded_fields, union_members, unwrap_annotation,
)
from sutra_app.library.types import (
    EDGE_ID_RE, EVENT_DATA_KEYS, FUNCTIONS, MAX_VIOLATIONS, AtomId, ChangeId, DomainEvent, EdgeId, FindingId,
    FunctionName, JsonObject, NodeId, Ref, Target, Ts, Violation, WorkflowId, clip, violation,
    violations_from_validation_error,
)
from typing import get_args


def errors_of(exc_info):
    return [(e["type"], ".".join(str(p) for p in e["loc"])) for e in exc_info.value.errors()]


class Inner(Value):
    n: int
    s: Annotated[str, Field(min_length=1, max_length=5)] = "x"


class Outer(Value):
    inner: Inner
    items: list[Inner] = []
    flag: bool = False
    ratio: float = 0.0
    passed: bool = Field(default=False, alias="pass")
    maybe: Optional[str] = None


# ---- the config -----------------------------------------------------------------------------------------------------

def test_value_config_is_closed_strict_frozen():
    cfg = Value.model_config
    assert cfg["extra"] == "forbid"
    assert cfg["strict"] is True
    assert cfg["frozen"] is True
    assert cfg["str_strip_whitespace"] is True
    assert cfg["validate_by_name"] is True and cfg["validate_by_alias"] is True
    assert cfg["serialize_by_alias"] is True
    assert cfg["allow_inf_nan"] is False
    assert Value.TRANSPORT_OPTIONAL == frozenset()


def test_record_inherits_the_config_and_adds_kind_and_schema_version():
    assert Record.model_config == Value.model_config
    assert set(Record.model_fields) == {"kind", "schema_version"}
    assert Record.VERSION == 1 and Record.ABSTRACT is False and Record.model_fields["schema_version"].default == 1


def test_minimum_pydantic_is_checked():
    require_pydantic("2.11.0")
    require_pydantic("2.14.2")
    require_pydantic("3.0.1")
    for old in ("2.10.9", "2.8.0", "1.10.0", "garbage", ""):
        with pytest.raises(RuntimeError, match="pydantic"):
            require_pydantic(old)
    assert base_module.MIN_PYDANTIC == (2, 11)


# ---- rule 1: no coercion ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1", 1.0, True, None, [1]])
def test_an_int_field_refuses_every_other_type(value):
    with pytest.raises(ValidationError) as e:
        Inner.model_validate({"n": value})
    assert errors_of(e) == [("int_type", "n")]
    with pytest.raises(ValidationError):
        Inner.model_validate_json(json.dumps({"n": value}))


@pytest.mark.parametrize("value", ["true", "True", 1, 0, "yes", None])
def test_a_bool_field_refuses_every_other_type(value):
    with pytest.raises(ValidationError) as e:
        Outer.model_validate({"inner": {"n": 1}, "flag": value})
    assert errors_of(e) == [("bool_type", "flag")]


def test_a_str_field_refuses_numbers_and_a_float_field_refuses_text():
    with pytest.raises(ValidationError) as e:
        Inner.model_validate({"n": 1, "s": 5})
    assert errors_of(e) == [("string_type", "s")]
    with pytest.raises(ValidationError) as e:
        Outer.model_validate({"inner": {"n": 1}, "ratio": "0.5"})
    assert errors_of(e) == [("float_type", "ratio")]


def test_an_int_is_a_valid_float_but_nan_and_infinity_are_not():
    assert Outer.model_validate({"inner": {"n": 1}, "ratio": 3}).ratio == 3.0
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValidationError) as e:
            Outer.model_validate({"inner": {"n": 1}, "ratio": bad})
        assert errors_of(e) == [("finite_number", "ratio")]


def test_unknown_keys_are_refused_at_every_depth():
    with pytest.raises(ValidationError) as e:
        Outer.model_validate({"inner": {"n": 1, "colour": "red"}, "other": 1})
    assert sorted(errors_of(e)) == [("extra_forbidden", "inner.colour"), ("extra_forbidden", "other")]


def test_strings_are_stripped_before_their_bounds_are_checked():
    assert Inner(n=1, s="  ab  ").s == "ab"
    assert Inner(n=1, s="  abcde  ").s == "abcde"
    with pytest.raises(ValidationError) as e:
        Inner(n=1, s="   ")
    assert errors_of(e) == [("string_too_short", "s")]
    with pytest.raises(ValidationError):
        Inner(n=1, s="abcdef")


# ---- rule 2: JSON-native types only (strict mode refuses the others from parsed JSON) --------------------------------

class Color(enum.Enum):
    RED = "red"


class Exotic(Value):
    pair: tuple[int, int] | None = None
    members: set[int] | None = None
    when: datetime.datetime | None = None
    ident: uuid.UUID | None = None
    color: Color | None = None


@pytest.mark.parametrize("field, parsed", [
    ("pair", [1, 2]), ("members", [1, 2]), ("when", "2026-11-04T10:00:00"),
    ("ident", "12345678-1234-5678-1234-567812345678"), ("color", "red"),
])
def test_values_that_json_cannot_say_are_refused_when_they_come_from_parsed_json(field, parsed):
    with pytest.raises(ValidationError):
        Exotic.model_validate({field: parsed})


# ---- rule 4: ABSTRACT is read from the class body ---------------------------------------------------------------------

def test_abstract_is_not_inherited():
    class Base(Record):
        ABSTRACT = True

    class Child(Base):
        kind: Literal["child"] = "child"

    class Grandchild(Child):
        pass

    assert is_abstract(Base) is True
    assert is_abstract(Child) is False and is_abstract(Grandchild) is False
    assert Child.ABSTRACT is True            # the attribute is inherited ...
    assert Record.ABSTRACT is False and is_abstract(Record) is False        # ... which is exactly why it is not trusted


# ---- rule 5: frozen, shallow ----------------------------------------------------------------------------------------

def test_a_value_cannot_be_assigned_to():
    item = Inner(n=1)
    with pytest.raises(ValidationError) as e:
        item.n = 2
    assert errors_of(e) == [("frozen_instance", "n")]
    assert item.n == 1
    with pytest.raises(ValidationError):
        del_attr = Outer(inner=item)
        del_attr.inner = Inner(n=3)


def test_frozen_is_shallow_so_the_gate_must_recheck():
    outer = Outer(inner=Inner(n=1), items=[Inner(n=2)])
    outer.items.append(Inner(n=3))                      # allowed: documented in design 3.1 rule 5
    assert len(outer.items) == 2


# ---- evolve: the only update path -----------------------------------------------------------------------------------

def test_evolve_returns_a_new_checked_instance_and_keeps_the_old_one():
    outer = Outer(inner=Inner(n=1), flag=False)
    newer = outer.evolve(flag=True, ratio=2.5)
    assert newer is not outer and type(newer) is Outer
    assert (newer.flag, newer.ratio, newer.inner) == (True, 2.5, Inner(n=1))
    assert (outer.flag, outer.ratio) == (False, 0.0)
    assert outer.evolve() == outer


def test_evolve_revalidates_every_change():
    outer = Outer(inner=Inner(n=1))
    with pytest.raises(ValidationError) as e:
        outer.evolve(flag="true")
    assert errors_of(e) == [("bool_type", "flag")]
    with pytest.raises(ValidationError) as e:
        outer.evolve(colour="red")
    assert errors_of(e) == [("extra_forbidden", "colour")]
    assert outer.flag is False


def test_evolve_accepts_a_field_name_or_its_alias():
    outer = Outer(inner=Inner(n=1))
    assert outer.evolve(passed=True).passed is True
    assert outer.evolve(**{"pass": True}).passed is True
    assert outer.evolve(passed=True).canonical_json() == outer.evolve(**{"pass": True}).canonical_json()


def test_evolve_with_a_nested_model_checks_it_again():
    outer = Outer(inner=Inner(n=1))
    assert outer.evolve(inner=Inner(n=9)).inner.n == 9
    assert outer.evolve(items=[Inner(n=1), Inner(n=2)]).items == [Inner(n=1), Inner(n=2)]
    broken = Inner.model_construct(n="not a number", s="x")
    with pytest.raises(ValidationError) as e:
        outer.evolve(inner=broken)
    assert errors_of(e) == [("int_type", "inner.n")]
    with pytest.raises(ValidationError):
        outer.evolve(items=[broken])


def test_evolve_rechecks_an_instance_built_with_model_construct():
    broken = Outer.model_construct(inner=Inner(n=1), flag="yes")
    with pytest.raises(ValidationError) as e:
        broken.evolve()
    assert errors_of(e) == [("bool_type", "flag")]


# ---- Record: kind and schema_version --------------------------------------------------------------------------------

class Toy(Record):
    FAMILY = "toy"
    kind: Literal["toy"] = "toy"
    n: int = 0


def test_record_kind_is_a_literal_with_a_default():
    assert Toy().kind == "toy"
    with pytest.raises(ValidationError) as e:
        Toy(kind="other")
    assert errors_of(e) == [("literal_error", "kind")]
    with pytest.raises(ValidationError) as e:
        Record()
    assert errors_of(e) == [("missing", "kind")]


def test_schema_version_must_equal_the_class_version():
    assert Toy().schema_version == 1
    with pytest.raises(ValidationError) as e:
        Toy(schema_version=2)
    assert errors_of(e) == [("value_error", "")]
    assert "schema_version is 2, this class is version 1" in str(e.value)
    for bad in (0, "1", 1.0, True):
        with pytest.raises(ValidationError):
            Toy(schema_version=bad)


def test_a_second_version_class_declares_its_own_default():
    class ToyV2(Record):
        FAMILY = "toy"
        VERSION = 2
        kind: Literal["toy"] = "toy"
        schema_version: int = 2

    assert ToyV2().schema_version == 2
    with pytest.raises(ValidationError):
        ToyV2(schema_version=1)


def test_record_round_trips_through_its_canonical_json():
    toy = Toy(n=4)
    assert Toy.model_validate_json(toy.canonical_json()) == toy


# ---- canonical JSON -------------------------------------------------------------------------------------------------

def test_canonical_json_is_sorted_compact_and_keeps_unicode():
    class Doc(Value):
        zeta: str
        alpha: int
        nested: Inner

    doc = Doc(zeta="é ü", alpha=1, nested=Inner(n=2))
    text = doc.canonical_json()
    assert text == '{"alpha":1,"nested":{"n":2,"s":"x"},"zeta":"é ü"}'
    assert text == canonical_json(doc)
    assert json.loads(text)["zeta"] == "é ü"


def test_canonical_json_is_the_same_whatever_order_the_data_came_in():
    one = Outer.model_validate({"inner": {"n": 1, "s": "a"}, "flag": True})
    two = Outer.model_validate({"flag": True, "inner": {"s": "a", "n": 1}})
    assert one.canonical_json() == two.canonical_json()


def test_canonical_json_uses_the_wire_alias_and_keeps_defaults_and_nulls():
    data = json.loads(Outer(inner=Inner(n=1), passed=True).canonical_json())
    assert data["pass"] is True and "passed" not in data
    assert data["maybe"] is None and data["items"] == [] and data["ratio"] == 0.0


def test_canonical_json_refuses_a_non_finite_number_that_slipped_in():
    bad = Outer.model_construct(inner=Inner(n=1), ratio=float("nan"))
    with pytest.raises(ValueError):
        bad.canonical_json()


# ---- annotation helpers used by the registry and the reply parser ----------------------------------------------------

class A(Value):
    op: Literal["a"] = "a"


class B(Value):
    op: Literal["b"] = "b"


def test_unwrap_annotation_peels_every_annotated_layer():
    inner = Annotated[int, "first"]
    core, meta = unwrap_annotation(Annotated[inner, "second"])
    assert core is int and meta == ("first", "second")
    assert unwrap_annotation(str) == (str, ())


def test_union_members_sees_optional_union_and_pipe_forms_only():
    assert union_members(Optional[int]) == (int, type(None))
    assert union_members(Union[A, B]) == (A, B)
    assert union_members(A | B) == (A, B)
    assert union_members(Annotated[Union[A, B], Field(discriminator="op")]) == (A, B)
    assert union_members(list[A]) is None and union_members(int) is None


def test_discriminator_of_reads_field_metadata_and_plain_discriminators():
    from pydantic import Discriminator
    core, meta = unwrap_annotation(Annotated[Union[A, B], Field(discriminator="op")])
    assert discriminator_of(meta) == "op"
    assert discriminator_of((Discriminator("op"),)) == "op"
    assert discriminator_of(("note", 3)) is None and discriminator_of(()) is None


def test_nested_models_finds_every_model_class_inside_an_annotation():
    assert nested_models(int) == []
    assert nested_models(list[A]) == [A]
    assert nested_models(dict[str, Optional[Inner]]) == [Inner]
    assert nested_models(Annotated[list[Annotated[Union[A, B], Field(discriminator="op")]], "meta"]) == [A, B]
    assert nested_models(Literal["a", "b"]) == []
    assert nested_models(Union[A, list[A], dict[str, A]]) == [A]               # each class once
    assert nested_models(Optional[Union[A, B]]) == [A, B]


# ---- scalars of types.py ------------------------------------------------------------------------------------------

def check_pattern(annotation, good, bad):
    """The scalars are field types of strict Values, so they are tested as one (a bare TypeAdapter would coerce)."""
    class Holder(Value):
        field: annotation

    for value in good:
        assert Holder.model_validate({"field": value}).field == value, value
    for value in bad:
        with pytest.raises(ValidationError):
            Holder.model_validate({"field": value})


def test_node_id():
    check_pattern(NodeId, ["sales", "ab", "web_team-2", "a" * 40], ["Sales", "a", "", "1abc", "a.b", "a" * 41, "a b", 5])


def test_workflow_id():
    check_pattern(WorkflowId, ["W-1", "W-123456"], ["W-", "w-1", "W-1a", "W-٣", "W-" + "1" * 11, 1])
    check_pattern(WorkflowId, ["W-" + "1" * 10], ["W-" + "1" * 11])


def test_change_id_and_ref_and_target():
    check_pattern(ChangeId, ["chg-0001", "chg-123456789"], ["chg-001", "chg-1234567890", "chg-00a1", "CHG-0001"])
    check_pattern(Ref, ["$a", "$sales_2", "$" + "a" * 16], ["$", "sales", "$Sales", "$1a", "$" + "a" * 17, "$a-b"])
    check_pattern(Target, ["sales", "$leads", "ab"], ["$", "Sales", "$$a", "a.b", "", "$A"])


def test_finding_id_and_edge_id():
    check_pattern(FindingId, ["F-1", "F-A-12", "F-" + "x" * 20], ["F-", "f-1", "F-" + "x" * 21, "F-a b", "F_1"])
    check_pattern(EdgeId, ["handoff:sales.identity>sales.audit", "depends_on:s-0123456789>s-abcdef0123"],
                  ["handoff", "Handoff:a>b", "handoff:>b", "handoff:a>", "handoff:a>b>c", "x" * 30 + ":a>b"])
    assert EDGE_ID_RE.fullmatch("step:a>b") and not EDGE_ID_RE.fullmatch("step:a>b\n")


def test_compiled_patterns_refuse_a_trailing_newline_that_a_dollar_would_let_through():
    from sutra_app.library.types import (
        ATOM_ID_RE, CHANGE_ID_RE, FINDING_ID_RE, NODE_ID_RE, REF_RE, TARGET_RE, WORKFLOW_ID_RE,
    )
    for regex, good in ((NODE_ID_RE, "sales"), (WORKFLOW_ID_RE, "W-1"), (ATOM_ID_RE, "a-x-01"), (CHANGE_ID_RE, "chg-0001"),
                        (REF_RE, "$a"), (TARGET_RE, "sales"), (FINDING_ID_RE, "F-1")):
        assert regex.fullmatch(good) and not regex.fullmatch(good + "\n"), regex.pattern
    # a strict Value strips whitespace first, so "sales\n" is the valid NodeId "sales" once it is stored
    class Holder(Value):
        field: NodeId

    assert Holder(field="sales\n").field == "sales"


def test_ts_is_a_non_negative_int():
    check_pattern(Ts, [0, 1, 1_700_000_000], [-1, 1.5, "5", True, None])


def test_function_name_and_functions_agree():
    assert FUNCTIONS == ("identity", "adaptation", "priority", "coordination", "audit")
    assert get_args(FunctionName) == FUNCTIONS
    check_pattern(FunctionName, list(FUNCTIONS), ["root", "Identity", ""])


def test_json_object_is_json_native_and_bounded():
    adapter = TypeAdapter(JsonObject)
    assert adapter.validate_python({"a": [1, 2.5, "x", None, True, {"b": []}]}) == {"a": [1, 2.5, "x", None, True, {"b": []}]}
    for bad in ({"a": (1, 2)}, {"a": {1, 2}}, {"a": object()}, {1: "a"}, {"a": float("nan")}, {"a": [float("inf")]}, [1]):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
    assert adapter.validate_python({f"k{i}": i for i in range(500)})
    with pytest.raises(ValidationError):
        adapter.validate_python({f"k{i}": i for i in range(501)})
    deep: dict = {}
    node = deep
    for _ in range(31):
        node["x"] = {}
        node = node["x"]
    assert adapter.validate_python(deep)
    node["x"] = {}
    with pytest.raises(ValidationError):
        adapter.validate_python(deep)
    with pytest.raises(ValidationError, match="finite"):
        adapter.validate_json('{"a": NaN}')


# ---- Violation and DomainEvent ---------------------------------------------------------------------------------------

def test_violation_has_a_path_a_code_and_a_bounded_message():
    v = Violation(path="nodes.1", code="value_error", message="a department must carry its five function nodes")
    assert (v.path, v.code) == ("nodes.1", "value_error")
    assert Violation(path="", code="x", message="m").path == ""
    for kwargs in ({"path": "", "code": "", "message": "m"}, {"path": "", "code": "x", "message": ""},
                   {"path": "", "code": "x", "message": "   "}, {"path": "", "code": "x", "message": "m" * 301},
                   {"path": "p" * 501, "code": "x", "message": "m"}, {"path": "", "code": "c" * 81, "message": "m"}):
        with pytest.raises(ValidationError):
            Violation(**kwargs)
    assert Violation(path="", code="x", message="m" * 300)


def test_violation_helper_clips_instead_of_failing():
    v = violation("p" * 600, "c" * 100, "m" * 500)
    assert len(v.path) == 500 and len(v.code) == 80 and len(v.message) == 300
    assert v.message.endswith("…") and v.path.endswith("…")
    assert violation("", "stale_base", "   ").message == "stale_base"
    assert violation("a", "b", "  text  ").message == "text"
    assert clip("abc", 3) == "abc" and clip("abcd", 3) == "ab…" and clip("", 3) == ""


def test_violations_from_a_validation_error_use_the_loc_as_the_path():
    class Parent(Value):
        child: Inner
        names: list[Annotated[str, Field(max_length=2)]]

    with pytest.raises(ValidationError) as e:
        Parent.model_validate({"child": {"n": "x", "extra": 1}, "names": ["ok", "toolong", 5]})
    got = {(v.path, v.code) for v in violations_from_validation_error(e.value)}
    assert got == {("child.n", "int_type"), ("child.extra", "extra_forbidden"),
                   ("names.1", "string_too_long"), ("names.2", "string_type")}


def test_value_error_messages_lose_pydantics_prefix():
    class Picky(Value):
        n: int

        @classmethod
        def check(cls, data):
            return cls.model_validate(data)

    from pydantic import model_validator

    class Rule(Value):
        a: int

        @model_validator(mode="after")
        def _rule(self):
            if self.a == 0:
                raise ValueError("a must not be zero")
            return self

    with pytest.raises(ValidationError) as e:
        Rule(a=0)
    [v] = violations_from_validation_error(e.value)
    assert (v.path, v.code, v.message) == ("", "value_error", "a must not be zero")

    class Asserting(Value):
        a: int

        @model_validator(mode="after")
        def _assert(self):
            if self.a == 0:
                raise AssertionError("a is zero")
            return self

    with pytest.raises(ValidationError) as e:
        Asserting(a=0)
    [v] = violations_from_validation_error(e.value)
    assert (v.code, v.message) == ("assertion_error", "a is zero")


def test_a_long_union_tag_is_not_echoed_in_full():
    adapter = TypeAdapter(Annotated[Union[A, B], Field(discriminator="op")])
    with pytest.raises(ValidationError) as e:
        adapter.validate_python({"op": "z" * 400})
    [v] = violations_from_validation_error(e.value)
    assert v.code == "union_tag_invalid" and len(v.message) <= 300
    assert "z" * 100 in v.message and "z" * 101 not in v.message


def test_a_flood_of_errors_is_cut_to_fifty_and_counted():
    class Many(Value):
        values: list[int]

    with pytest.raises(ValidationError) as e:
        Many.model_validate({"values": ["x"] * 120})
    found = violations_from_validation_error(e.value)
    assert len(found) == MAX_VIOLATIONS + 1 == 51
    assert found[-1].code == "more_errors" and "70 more" in found[-1].message
    assert found[0].path == "values.0"


def test_a_very_deep_path_is_clipped_to_its_bound():
    class Tree(Value):
        children: list["Tree"] = []

    Tree.model_rebuild()
    node: dict = {"children": [], "bad": 1}
    for _ in range(300):
        node = {"children": [node]}
    with pytest.raises(ValidationError) as e:
        Tree.model_validate(node)
    found = violations_from_validation_error(e.value)
    assert found and all(len(v.path) <= 500 for v in found)


EVENT_DATA = {                                     # a valid `data` for each type (design section 13)
    "chart.changed": {"revision": 3, "change_id": "chg-0003", "kind": "add", "added": ["sales"], "moved": [], "merged": []},
    "atom.transitioned": {"atom_id": "a-3f9a1c2b7d-01", "node_id": "sales.audit", "outcome": "done", "state": "done"},
    "node.state": {"node_id": "sales.audit", "state": "idle"},
}


def test_domain_event():
    event = DomainEvent(type="node.state", subject_id="sales.audit", data={"node_id": "sales.audit", "state": "idle"}, ts=5)
    assert event.canonical_json() == '{"data":{"node_id":"sales.audit","state":"idle"},"subject_id":"sales.audit","ts":5,"type":"node.state"}'
    for kind, data in EVENT_DATA.items():
        assert DomainEvent(type=kind, subject_id="x", data=data, ts=0).type == kind
    assert get_args(DomainEvent.model_fields["type"].annotation) == ("chart.changed", "atom.transitioned", "node.state")
    base = {"type": "node.state", "subject_id": "x", "data": EVENT_DATA["node.state"], "ts": 0}
    assert DomainEvent(**base).data == EVENT_DATA["node.state"]
    for kwargs in ({"type": "chart.deleted"}, {"subject_id": ""}, {"subject_id": "x" * 201}, {"ts": -1}, {"data": []},
                   {"data": {**EVENT_DATA["node.state"], "k": (1, 2)}}, {"colour": "red"}):
        with pytest.raises(ValidationError):
            DomainEvent(**{**base, **kwargs})


def test_the_data_of_each_event_type_holds_the_keys_design_13_fixes():
    # Review round 1: `data` was a free object, so an event with misspelt keys (or none) reached the SSE mapping unnoticed.
    assert {kind: tuple(keys) for kind, keys in EVENT_DATA_KEYS.items()} == {
        "chart.changed": ("revision", "change_id", "kind", "added", "moved", "merged"),
        "atom.transitioned": ("atom_id", "node_id", "outcome", "state"),
        "node.state": ("node_id", "state"),
    }
    assert set(EVENT_DATA_KEYS) == set(get_args(DomainEvent.model_fields["type"].annotation))
    with pytest.raises(TypeError):                                      # a module constant: nobody can loosen the shapes at run time
        EVENT_DATA_KEYS["node.state"] = ()
    for kind, data in EVENT_DATA.items():
        assert tuple(data) == EVENT_DATA_KEYS[kind]
        with pytest.raises(ValidationError) as e:
            DomainEvent(type=kind, subject_id="x", data={}, ts=0)
        [(code, path)] = errors_of(e)
        assert (code, path) == ("value_error", "")
        for key in EVENT_DATA_KEYS[kind]:                               # each key is needed on its own
            without = {k: v for k, v in data.items() if k != key}
            with pytest.raises(ValidationError) as e:
                DomainEvent(type=kind, subject_id="x", data=without, ts=0)
            assert key in str(e.value)


def test_a_misspelt_key_is_refused_and_the_message_shows_the_keys_it_has():
    with pytest.raises(ValidationError) as e:
        DomainEvent(type="node.state", subject_id="sales.audit", data={"nodeid": "sales.audit", "stat": "idle"}, ts=0)
    [v] = violations_from_validation_error(e.value)
    assert v.code == "value_error" and "lacks node_id, state" in v.message and "nodeid, stat" in v.message
    with pytest.raises(ValidationError) as e:
        DomainEvent(type="chart.changed", subject_id="x", data={}, ts=0)
    assert "it has no keys" in violations_from_validation_error(e.value)[0].message
    with pytest.raises(ValidationError) as e:
        DomainEvent(type="node.state", subject_id="x", data={f"k{i}": i for i in range(20)}, ts=0)
    assert "k0, k1, k10, k11, k12, k13, k14, k15, ..." in violations_from_validation_error(e.value)[0].message
    for count, tail in ((8, "(it has k0, k1, k2, k3, k4, k5, k6, k7)"), (9, "(it has k0, k1, k2, k3, k4, k5, k6, k7, ...)")):
        with pytest.raises(ValidationError) as e:                       # eight keys are all shown; a ninth is only counted
            DomainEvent(type="node.state", subject_id="x", data={f"k{i}": i for i in range(count)}, ts=0)
        assert violations_from_validation_error(e.value)[0].message.endswith(tail)
    with pytest.raises(ValidationError) as e:                           # a long key is cut to 40 characters
        DomainEvent(type="node.state", subject_id="x", data={"k" * 60: 1}, ts=0)
    assert violations_from_validation_error(e.value)[0].message.endswith("(it has " + "k" * 39 + "…)")


def test_the_type_decides_which_keys_are_needed():
    with pytest.raises(ValidationError):                                # node.state keys on an atom.transitioned event
        DomainEvent(type="atom.transitioned", subject_id="x", data=EVENT_DATA["node.state"], ts=0)
    with pytest.raises(ValidationError):
        DomainEvent(type="node.state", subject_id="x", data=EVENT_DATA["chart.changed"], ts=0)


def test_more_keys_than_the_shape_fixes_are_allowed_since_the_orchestrator_adds_some():
    data = {**EVENT_DATA["chart.changed"], "version": 3, "summary": "added sales", "archived": False}
    assert DomainEvent(type="chart.changed", subject_id="x", data=data, ts=0).data["summary"] == "added sales"
    assert DomainEvent(type="node.state", subject_id="x", data={**EVENT_DATA["node.state"], "extra": [1, {"a": None}]}, ts=0)


def test_the_keys_of_an_event_are_checked_when_it_is_read_back_from_json_too():
    event = DomainEvent(type="node.state", subject_id="x", data=EVENT_DATA["node.state"], ts=1)
    assert DomainEvent.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError):
        DomainEvent.model_validate_json('{"type":"node.state","subject_id":"x","data":{},"ts":1}')
    assert event.evolve(ts=2).ts == 2
    with pytest.raises(ValidationError):
        event.evolve(data={})                                           # evolve re-checks the shape


# ---- rule 3: every str and list is bounded (unbounded_fields) --------------------------------------------------------------

def test_the_classes_of_types_py_have_no_unbounded_field():
    assert unbounded_fields(Violation) == []
    assert unbounded_fields(DomainEvent) == []                          # `data` is a JsonObject: bounded by its own validator


@pytest.mark.parametrize("annotation", [NodeId, WorkflowId, AtomId, ChangeId, Ref, Target, FindingId, EdgeId])
def test_every_id_type_is_bounded_by_its_pattern_or_its_max_length(annotation):
    class Holder(Value):
        ident: annotation
        idents: Annotated[list[annotation], Field(max_length=3)] = []

    assert unbounded_fields(Holder) == []


class Loose(Value):
    text: str
    maybe: Optional[str] = None
    items: list[str] = []
    ok: Annotated[str, Field(max_length=5)] = ""
    ok_items: Annotated[list[Annotated[str, Field(max_length=3)]], Field(max_length=4)] = []
    bare_items: Annotated[list[Annotated[str, Field(max_length=3)]], Field(min_length=0)] = []
    by_name: dict[str, str] = {}
    by_name_ok: dict[str, Annotated[str, Field(max_length=3)]] = {}
    words: list[Annotated[str, Field(max_length=3)]] = []
    mode: Literal["a", "b"] = "a"
    one: Literal["a"] = "a"
    number: int = 0


def test_a_str_and_a_list_without_a_bound_are_found_wherever_they_sit():
    assert unbounded_fields(Loose) == [
        "Loose.text", "Loose.maybe", "Loose.items", "Loose.items[]", "Loose.bare_items", "Loose.by_name{}", "Loose.words",
    ]


def test_the_report_names_the_class_a_field_belongs_to_and_looks_into_nested_classes():
    class Row(Value):
        label: str
        ok: Annotated[str, Field(max_length=5)] = ""

    class Table(Value):
        title: Annotated[str, Field(max_length=5)]
        rows: Annotated[list[Row], Field(max_length=10)] = []
        first: Optional[Row] = None
        pair: tuple[Annotated[str, Field(max_length=2)], str] = ("a", "b")

    assert unbounded_fields(Table) == ["Table.pair[1]", "Row.label"]
    assert unbounded_fields(Row) == ["Row.label"]
    class Unbounded(Value):
        rows: list[Row] = []

    assert unbounded_fields(Unbounded) == ["Unbounded.rows", "Row.label"]


def test_a_union_is_looked_into_member_by_member():
    class Either(Value):
        value: Union[str, Annotated[str, Field(max_length=3)], list[str], int, None] = None

    assert unbounded_fields(Either) == ["Either.value", "Either.value[]"]


def test_a_pattern_bounds_a_string_only_when_it_is_anchored_and_cannot_run_on():
    class Patterned(Value):
        anchored_short: Annotated[str, StringConstraints(pattern=r"^[a-z]{1,5}$")] = "a"
        anchored_alternatives: Annotated[str, StringConstraints(pattern=r"^(a|bb|ccc)$")] = "a"
        open_ended: Annotated[str, StringConstraints(pattern=r"^[a-z]+$")] = "a"
        star: Annotated[str, StringConstraints(pattern=r"^.*$")] = "a"
        unanchored: Annotated[str, StringConstraints(pattern=r"[a-z]{1,5}")] = "a"
        half_anchored: Annotated[str, StringConstraints(pattern=r"^[a-z]{1,5}")] = "a"
        end_anchored_only: Annotated[str, StringConstraints(pattern=r"[a-z]{1,5}$")] = "a"
        alternatives_not_anchored_together: Annotated[str, StringConstraints(pattern=r"^a|b$")] = "a"
        long_but_bounded_by_max_length: Annotated[str, StringConstraints(pattern=r"^[a-z]+$", max_length=9)] = "a"

    assert unbounded_fields(Patterned) == [
        "Patterned.open_ended", "Patterned.star", "Patterned.unanchored", "Patterned.half_anchored",
        "Patterned.end_anchored_only", "Patterned.alternatives_not_anchored_together",
    ]


def test_a_pattern_the_checker_cannot_read_counts_as_unbounded(monkeypatch):
    class Patterned(Value):
        short: Annotated[str, StringConstraints(pattern=r"^[a-z]{1,5}$")] = "a"

    assert unbounded_fields(Patterned) == []
    monkeypatch.setattr(base_module, "re", SimpleNamespace())          # a Python whose regex parser is not where we look
    assert unbounded_fields(Patterned) == ["Patterned.short"]
    assert base_module._pattern_bounds_length("(") is False             # and a pattern that is not a pattern


def test_a_pattern_whose_width_reached_the_parsers_own_cap_is_unbounded_whatever_that_cap_is(monkeypatch):
    # Python 3.11 caps the width of an unbounded repeat at 2**64, older ones at MAXREPEAT: "no limit" must never read as
    # bounded. The parser is made to report a width, so both caps are tried on whatever Python runs the suite.
    import re as regex
    real_parse = regex._parser.parse
    cap = regex._constants.MAXREPEAT

    def parser_reporting(width):
        def parse(pattern, *args, **kwargs):
            parsed = real_parse(pattern, *args, **kwargs)
            parsed.width = (1, width)                                   # getwidth() hands back what is stored here
            return parsed
        return parse

    monkeypatch.setattr(regex._parser, "parse", parser_reporting(cap))
    assert base_module._pattern_bounds_length("^x$") is False
    monkeypatch.setattr(regex._parser, "parse", parser_reporting(cap - 1))
    assert base_module._pattern_bounds_length("^x$") is True


def test_the_walk_follows_every_way_a_schema_can_combine_types():
    # pydantic writes `anyOf` for a union and, depending on its version, `allOf` or `oneOf` for other combinations; the
    # walk must not depend on which one it gets, so the schema is written by hand here.
    class Handmade(Value):
        @classmethod
        def model_json_schema(cls, *args, **kwargs):
            return {
                "type": "object",
                "properties": {
                    "one": {"oneOf": [{"type": "string", "maxLength": 3}, {"type": "array", "items": {"type": "string"}, "maxItems": 2}]},
                    "all": {"allOf": [{"type": "string"}]},
                    "any": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "ref": {"$ref": "#/$defs/Part"},
                },
                "$defs": {"Part": {"type": "object", "properties": {"inner": {"oneOf": [{"type": "string"}]}}}},
            }

    assert unbounded_fields(Handmade) == ["Handmade.one[]", "Handmade.all", "Handmade.any", "Part.inner"]


def test_a_field_is_named_by_its_python_name_not_by_its_alias():
    class Wire(Value):
        passed: str = Field(default="", alias="pass")

    assert unbounded_fields(Wire) == ["Wire.passed"]


def test_unbounded_fields_survives_a_class_that_refers_to_itself():
    class Tree(Value):
        label: str
        children: list["Tree"] = []

    Tree.model_rebuild()
    assert unbounded_fields(Tree) == ["Tree.label", "Tree.children"]


def test_unbounded_fields_finds_what_the_gate_lets_through():
    # The repro of the review round: nothing reported a class that accepts half a megabyte of text.
    from sutra_app.library.gate import Gate
    from sutra_app.library.registry import ModelRegistry

    class Wide(Record):
        FAMILY = "wide"
        kind: Literal["wide"] = "wide"
        text: str
        items: list[str] = []

    reg = ModelRegistry()
    reg.register(Wide)
    assert len(Gate(reg).check("wide", {"kind": "wide", "text": "x" * 500_000, "items": ["a"] * 50_000}).json) > 500_000
    assert unbounded_fields(Wide) == ["Wide.text", "Wide.items", "Wide.items[]"]


# ---- rule 7: an alias only where J2's wire key is a Python keyword (aliased_fields) --------------------------------------

def test_a_keyword_alias_is_what_rule_7_allows_and_nothing_else_is_reported():
    class Wire(Value):
        passed: bool = Field(default=False, alias="pass")
        origin: str = Field(default="", alias="from", max_length=5)
        plain: int = 0

    assert aliased_fields(Wire) == []


def test_an_alias_that_is_not_a_keyword_is_reported_with_its_class():
    class Row(Value):
        label: str = Field(default="", alias="name", max_length=5)

    class AtomView(Value):                    # the one alias the design allows on purpose: J2's wire key `schema` (L4's AtomView)
        schema_: str = Field(default="atom/1", alias="schema", max_length=10)
        passed: bool = Field(default=False, alias="pass")
        rows: list[Row] = Field(default=[], max_length=3)

    assert aliased_fields(AtomView) == [("AtomView", "schema"), ("Row", "name")]
    assert aliased_fields(Row) == [("Row", "name")]
    allowed = {("AtomView", "schema")}                                  # what L8 holds as its allow-list over the full REGISTRY
    assert set(aliased_fields(AtomView)) - allowed == {("Row", "name")}
    assert set(aliased_fields(AtomView)) - allowed - {("Row", "name")} == set()


def test_each_kind_of_alias_is_reported_once():
    from pydantic import AliasChoices

    class Many(Value):
        a: str = Field(default="", validation_alias="va", serialization_alias="sa", max_length=5)
        b: str = Field(default="", alias="same", max_length=5)
        c: str = Field(default="", validation_alias=AliasChoices("x", "y"), max_length=5)

    assert aliased_fields(Many) == [("Many", "va"), ("Many", "sa"), ("Many", "same"), ("Many", "AliasChoices(choices=['x', 'y'])")]


def test_an_alias_that_only_the_alias_attribute_of_the_field_holds_is_found_too():
    class Row(Value):
        label: str = Field(default="", alias="name", max_length=5)

    info = Row.model_fields["label"]
    info.validation_alias = info.serialization_alias = None              # as a pydantic that sets `alias` alone would leave it
    assert aliased_fields(Row) == [("Row", "name")]


def test_aliased_fields_survives_a_class_that_refers_to_itself():
    class Tree(Value):
        label: str = Field(default="", alias="name", max_length=5)
        children: list["Tree"] = Field(default=[], max_length=5)

    Tree.model_rebuild()
    assert aliased_fields(Tree) == [("Tree", "name")]


def test_the_toy_aliases_of_this_suite_are_all_keywords():
    assert aliased_fields(Outer) == []                                  # `pass` only
