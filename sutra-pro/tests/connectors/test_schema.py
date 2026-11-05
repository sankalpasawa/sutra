"""CN-1: JSON-schema helpers (connectors design 3.6, D33): to_json_schema, strict_schema, minimal_validate, example_from_schema."""
import copy
import json
from typing import Literal, Optional, Union

import pytest
from pydantic import BaseModel, Field

from sutra_app.connectors import schema as S
from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.library.registry import transport_schema


class Inner(BaseModel):
    name: str
    count: int = 3


class Outer(BaseModel):
    title: str
    kind: Literal["a", "b"]
    inner: Inner
    items: list[Inner] = []
    note: Optional[str] = None
    score: float = Field(0.5, ge=0)
    flag: bool = False


# ===================================================================================================================
# to_json_schema, schema_text, schema_sha, fits_native
# ===================================================================================================================

def test_a_class_goes_through_the_librarys_transport_schema():
    assert S.to_json_schema(Outer) == transport_schema(Outer)


def test_a_dict_is_copied_and_checked():
    src = {"type": "object", "properties": {"a": {"type": "string"}}}
    got = S.to_json_schema(src)
    assert got == src and got is not src and got["properties"] is not src["properties"]


@pytest.mark.parametrize("bad", [{"type": "string"}, {"type": "array", "items": {}}, {}])
def test_a_dict_schema_must_describe_an_object(bad):
    with pytest.raises(InvalidRequestError, match="JSON object at its root"):
        S.to_json_schema(bad)


def test_a_union_or_ref_root_is_accepted():
    assert S.to_json_schema({"anyOf": [{"type": "object"}]}) and S.to_json_schema({"$ref": "#/definitions/X", "definitions": {}})


@pytest.mark.parametrize("bad", [{"type": "object", "x": float("nan")}, {"type": "object", "x": object()}])
def test_a_schema_that_is_not_json_is_refused(bad):
    with pytest.raises(InvalidRequestError, match="not JSON"):
        S.to_json_schema(bad)


def test_something_that_is_not_a_schema_is_refused():
    with pytest.raises(InvalidRequestError, match="pydantic class or a dict"):
        S.to_json_schema("nope")


def test_a_class_the_library_cannot_make_safe_is_an_invalid_request():
    class Free(BaseModel):
        anything: dict[str, int]

    with pytest.raises(InvalidRequestError, match="Free"):
        S.to_json_schema(Free)


def test_schema_sha_ignores_key_order_and_sees_changes():
    a = {"type": "object", "properties": {"x": {"type": "string"}, "y": {"type": "integer"}}}
    b = {"properties": {"y": {"type": "integer"}, "x": {"type": "string"}}, "type": "object"}
    assert S.schema_sha(a) == S.schema_sha(b) and len(S.schema_sha(a)) == 64
    assert S.schema_sha(a) != S.schema_sha({**a, "required": ["x"]})


def test_schema_text_is_compact_json():
    assert S.schema_text({"a": [1, 2], "b": "é"}) == '{"a":[1,2],"b":"é"}'


def test_the_native_gate_is_100000_characters():
    base = len(S.schema_text({"type": "object", "description": ""}))

    def sized(n):
        return {"type": "object", "description": "x" * (n - base)}

    assert S.NATIVE_SCHEMA_MAX_CHARS == 100_000
    assert len(S.schema_text(sized(99_999))) == 99_999 and S.fits_native(sized(99_999))
    assert not S.fits_native(sized(100_000))


# ===================================================================================================================
# strict_schema
# ===================================================================================================================

def walk_objects(node, path="$"):
    """Every schema node that declares properties (or type object), with its path."""
    if isinstance(node, dict):
        if "properties" in node or node.get("type") == "object":
            yield path, node
        for k, v in node.items():
            if k in ("properties", "definitions", "$defs"):
                for name, sub in v.items():
                    yield from walk_objects(sub, f"{path}.{k}.{name}")
            elif k in ("items", "additionalProperties"):
                yield from walk_objects(v, f"{path}.{k}")
            elif k in ("anyOf", "allOf"):
                for i, sub in enumerate(v):
                    yield from walk_objects(sub, f"{path}.{k}.{i}")


def test_every_object_is_closed_and_has_every_property_required():
    strict = S.strict_schema(Outer.model_json_schema())
    nodes = list(walk_objects(strict))
    assert len(nodes) >= 2                       # Outer and Inner (a $def)
    for path, node in nodes:
        assert node["additionalProperties"] is False, path
        assert node["required"] == list(node["properties"]), path


def test_optional_properties_become_nullable_and_required_ones_stay_as_they_were():
    src = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer"}, "c": {"type": ["string", "null"]},
                                              "d": {"enum": ["x", "y"]}, "e": {"type": "string", "enum": ["p", "q"]},
                                              "f": {"$ref": "#/definitions/T"}, "g": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
           "required": ["a"], "definitions": {"T": {"type": "boolean"}}}
    got = S.strict_schema(src)["properties"]
    assert got["a"] == {"type": "string"}
    assert got["b"] == {"type": ["integer", "null"]}
    assert got["c"] == {"type": ["string", "null"]}
    assert got["d"] == {"anyOf": [{"enum": ["x", "y"]}, {"type": "null"}]}
    assert got["e"] == {"type": ["string", "null"], "enum": ["p", "q", None]}
    assert got["f"] == {"anyOf": [{"$ref": "#/definitions/T"}, {"type": "null"}]}
    assert got["g"] == {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}


def test_a_nullable_anyof_is_not_given_a_second_null():
    src = {"type": "object", "properties": {"a": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "n": {"type": "null"}}}
    got = S.strict_schema(src)["properties"]
    assert got["a"]["anyOf"] == [{"type": "string"}, {"type": "null"}] and got["n"] == {"type": "null"}


def test_default_title_and_examples_are_removed_but_properties_of_those_names_stay():
    src = {"type": "object", "title": "T", "default": {}, "examples": [{}], "properties": {
        "title": {"type": "string", "title": "Title", "default": "x", "examples": ["y"]}, "default": {"type": "integer", "default": 1},
        "examples": {"type": "array", "items": {"type": "string", "title": "Row"}}}, "required": ["title", "default", "examples"]}
    got = S.strict_schema(src)
    assert set(got) == {"type", "properties", "required", "additionalProperties"}
    assert got["properties"] == {"title": {"type": "string"}, "default": {"type": "integer"}, "examples": {"type": "array", "items": {"type": "string"}}}


def test_definitions_and_defs_are_kept_and_made_strict():
    src = {"type": "object", "properties": {"x": {"$ref": "#/$defs/D"}}, "required": ["x"],
           "$defs": {"D": {"type": "object", "properties": {"v": {"type": "integer"}}}}}
    got = S.strict_schema(src)
    assert got["$defs"]["D"] == {"type": "object", "properties": {"v": {"type": ["integer", "null"]}}, "required": ["v"], "additionalProperties": False}
    old = S.strict_schema({"type": "object", "properties": {}, "definitions": {"D": {"type": "object", "properties": {"v": {"type": "string"}}, "required": ["v"]}}})
    assert old["definitions"]["D"]["additionalProperties"] is False


def test_oneof_becomes_anyof_and_const_becomes_a_one_value_enum():
    src = {"type": "object", "properties": {"u": {"oneOf": [{"type": "object", "properties": {"op": {"const": "add"}}, "required": ["op"]},
                                                              {"type": "string"}], "discriminator": {"propertyName": "op"}}},
           "required": ["u"]}
    u = S.strict_schema(src)["properties"]["u"]
    assert "oneOf" not in u and "discriminator" not in u
    assert u["anyOf"][0]["properties"]["op"] == {"enum": ["add"]} and u["anyOf"][0]["additionalProperties"] is False
    assert u["anyOf"][1] == {"type": "string"}


def test_array_items_and_union_branches_are_made_strict():
    src = {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "items": {"type": "object", "properties": {"k": {"type": "string"}}}}}}
    assert S.strict_schema(src)["properties"]["rows"]["items"]["additionalProperties"] is False


def test_an_object_without_properties_is_closed_and_a_map_with_free_keys_is_left_alone():
    assert S.strict_schema({"type": "object"}) == {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    free = {"type": "object", "additionalProperties": {"type": "integer", "title": "N"}}
    assert S.strict_schema(free) == {"type": "object", "additionalProperties": {"type": "integer"}}


def test_strict_schema_is_idempotent_and_does_not_touch_its_input():
    src = Outer.model_json_schema()
    before = copy.deepcopy(src)
    once = S.strict_schema(src)
    assert src == before
    assert S.strict_schema(once) == once


def test_strict_schema_of_a_transport_schema_is_still_strict():
    strict = S.strict_schema(transport_schema(Outer))
    assert strict["additionalProperties"] is False and strict["required"] == list(strict["properties"])
    json.dumps(strict)


# ===================================================================================================================
# minimal_validate
# ===================================================================================================================

SCHEMA = {"type": "object", "required": ["name", "tags"], "properties": {
    "name": {"type": "string"}, "age": {"type": "integer"}, "score": {"type": "number"}, "ok": {"type": "boolean"},
    "tags": {"type": "array", "items": {"type": "string"}}, "mode": {"enum": ["a", "b"]},
    "child": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}},
    "maybe": {"type": ["string", "null"]}}}


def test_a_value_that_fits_has_no_errors():
    assert S.minimal_validate({"name": "n", "tags": ["x"], "age": 3, "score": 1.5, "ok": True, "mode": "a", "child": {"id": 1}, "maybe": None}, SCHEMA) == []


def test_extra_keys_and_unchecked_keywords_are_ignored():
    assert S.minimal_validate({"name": "n", "tags": [], "extra": 1}, {**SCHEMA, "additionalProperties": False}) == []
    assert S.minimal_validate({"s": "x"}, {"type": "object", "properties": {"s": {"type": "string", "minLength": 9, "pattern": "^z"}}}) == []


def test_a_wrong_root_type_is_reported_once():
    assert S.minimal_validate([1], SCHEMA) == ["reply: must be object, got a list"]
    assert S.minimal_validate("x", SCHEMA) == ["reply: must be object, got a string"]


def test_missing_required_keys_are_named():
    assert S.minimal_validate({}, SCHEMA) == ["name: is required", "tags: is required"]
    assert S.minimal_validate({"name": "n", "tags": [], "child": {}}, SCHEMA) == ["child.id: is required"]


def test_primitive_property_types_are_checked_with_a_path():
    got = S.minimal_validate({"name": 5, "tags": ["ok", 2], "age": "7", "ok": "yes", "child": {"id": "1"}}, SCHEMA)
    assert sorted(got) == sorted([
        "name: must be string, got a number", "tags.1: must be string, got a number", "age: must be integer, got a string",
        "ok: must be boolean, got a string", "child.id: must be integer, got a string"])


def test_a_boolean_is_not_a_number_and_an_integral_float_is_an_integer():
    assert S.minimal_validate({"name": "n", "tags": [], "age": True}, SCHEMA) == ["age: must be integer, got a boolean"]
    assert S.minimal_validate({"name": "n", "tags": [], "score": False}, SCHEMA) == ["score: must be number, got a boolean"]
    assert S.minimal_validate({"name": "n", "tags": [], "age": 3.0, "score": 2}, SCHEMA) == []
    assert S.minimal_validate({"name": "n", "tags": [], "age": 3.5}, SCHEMA) == ["age: must be integer, got a number"]


def test_a_type_list_accepts_null_only_when_it_names_null():
    assert S.minimal_validate({"name": "n", "tags": [], "maybe": None}, SCHEMA) == []
    assert S.minimal_validate({"name": None, "tags": []}, SCHEMA) == ["name: must be string, got null"]


def test_enum_const_anyof_and_refs():
    assert S.minimal_validate({"name": "n", "tags": [], "mode": "z"}, SCHEMA) == ["mode: must be one of ['a', 'b']"]
    assert S.minimal_validate({"k": "x"}, {"type": "object", "properties": {"k": {"const": "y"}}}) == ["k: must be 'y'"]
    anyof = {"type": "object", "properties": {"u": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}}
    assert S.minimal_validate({"u": 3}, anyof) == [] and S.minimal_validate({"u": "s"}, anyof) == []
    assert S.minimal_validate({"u": [1]}, anyof) == ["u: does not match any of the allowed shapes"]
    ref = {"type": "object", "properties": {"d": {"$ref": "#/definitions/D"}}, "definitions": {"D": {"type": "object", "required": ["z"]}}}
    assert S.minimal_validate({"d": {}}, ref) == ["d.z: is required"]
    assert S.minimal_validate({"d": {"z": 1}}, ref) == []
    assert S.minimal_validate({"d": 1}, {"$ref": "#/nowhere"}) == []          # an unresolvable ref is not an error


def test_allof_members_all_apply():
    schema = {"allOf": [{"type": "object", "required": ["a"]}, {"type": "object", "required": ["b"]}]}
    assert S.minimal_validate({"a": 1}, schema) == ["b: is required"]


def test_resolve_ref():
    root = {"definitions": {"A": {"type": "string"}}, "$defs": {"B/C": {"type": "integer"}}}
    assert S.resolve_ref("#/definitions/A", root) == {"type": "string"}
    assert S.resolve_ref("#/$defs/B~1C", root) == {"type": "integer"}
    assert S.resolve_ref("#/definitions/Z", root) is None
    assert S.resolve_ref("http://elsewhere#/x", root) is None and S.resolve_ref(5, root) is None
    assert S.resolve_ref("#/definitions/A/type", root) is None              # a string is not a schema node


# ===================================================================================================================
# example_from_schema
# ===================================================================================================================

def test_example_uses_the_documented_placeholders():
    schema = {"type": "object", "required": ["s", "i", "n", "b", "l", "e", "o"], "properties": {
        "s": {"type": "string"}, "i": {"type": "integer"}, "n": {"type": "number"}, "b": {"type": "boolean"}, "l": {"type": "array", "items": {"type": "string"}},
        "e": {"enum": ["first", "second"]}, "o": {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}, "skipped": {"type": "string"}}},
        "optional": {"type": "string"}}}
    assert S.example_from_schema(schema) == {"s": "stub", "i": 0, "n": 0, "b": False, "l": [], "e": "first", "o": {"x": "stub"}}


def test_example_respects_bounds_and_const():
    assert S.example_from_schema({"type": "string", "minLength": 6}) == "stubxx"
    assert S.example_from_schema({"type": "string", "maxLength": 2}) == "st"
    assert S.example_from_schema({"type": "integer", "minimum": 5}) == 5
    assert S.example_from_schema({"type": "integer", "exclusiveMinimum": 0}) == 1
    assert S.example_from_schema({"type": "integer", "maximum": -3}) == -3
    assert S.example_from_schema({"type": "number", "exclusiveMaximum": 0}) == -1
    assert S.example_from_schema({"type": "array", "minItems": 2, "items": {"type": "boolean"}}) == [False, False]
    assert S.example_from_schema({"const": {"k": 1}}) == {"k": 1}


def test_example_picks_the_first_non_null_branch_and_follows_refs():
    assert S.example_from_schema({"anyOf": [{"type": "null"}, {"type": "integer"}]}) == 0
    assert S.example_from_schema({"anyOf": [{"type": "null"}]}) is None
    assert S.example_from_schema({"type": ["null", "string"]}) == "stub"
    assert S.example_from_schema({"$ref": "#/definitions/A", "definitions": {"A": {"type": "boolean"}}}) is False
    assert S.example_from_schema({"allOf": [{"type": "string"}]}) == "stub"
    assert S.example_from_schema({}) is None
    assert S.example_from_schema({"properties": {"a": {"type": "string"}}, "required": ["a"]}) == {"a": "stub"}


def test_example_of_a_self_referencing_schema_terminates():
    node = {"type": "object", "required": ["next"], "properties": {"next": {"$ref": "#"}}}
    S.example_from_schema(node)                    # must return, not recurse for ever


def test_example_returns_a_copy_of_enum_and_const_values():
    schema = {"enum": [[1]]}
    got = S.example_from_schema(schema)
    got.append(2)
    assert schema == {"enum": [[1]]}


def test_example_of_a_class_validates_against_it():
    got = S.example_from_schema(Outer)
    assert got == {"title": "stub", "kind": "a", "inner": {"name": "stub"}}
    assert Outer.model_validate(got)


def test_example_of_a_class_with_bounds_unions_and_nested_lists_validates():
    class Row(BaseModel):
        id: int = Field(ge=1)
        label: str = Field(min_length=3)
        tags: list[str] = Field(min_length=1)

    class Doc(BaseModel):
        rows: list[Row] = Field(min_length=2)
        pick: Union[int, str]
        maybe: Optional[int]
        mode: Literal["x"]

    got = S.example_from_schema(Doc)
    assert Doc.model_validate(got)
    assert len(got["rows"]) == 2 and got["rows"][0]["id"] == 1


def test_example_of_a_transport_schema_class_validates():
    assert Outer.model_validate(S.example_from_schema(S.to_json_schema(Outer)))


def test_example_refuses_something_that_is_not_a_schema():
    with pytest.raises(InvalidRequestError):
        S.example_from_schema(5)
