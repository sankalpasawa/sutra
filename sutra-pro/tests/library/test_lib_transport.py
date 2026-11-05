"""The transport schema (library design 3.5): what a model is asked to answer in. Toy classes only; the real classes
are checked in L2, L5 and L7. A port of J2's `transport_schema` with four declared changes: `const` stays as a
one-value `enum`, a union is `anyOf`, a recursive class is refused, and a dict with free keys is refused."""
import copy
import hashlib
import json
from typing import Annotated, Literal, Optional, Union

import pytest
from pydantic import Field, ValidationError

from sutra_app.library import registry as registry_module
from sutra_app.library.base import Record, Value
from sutra_app.library.registry import (
    TRANSPORT_DRAFT, ModelRegistry, RegistryError, is_transport_safe, reply_schema, schema_sha, transport_schema,
)


def walk(node):
    """Every dict in a schema, schema nodes and property maps alike."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def schema_nodes(schema):
    """Only the nodes that are schemas (not the maps of property names or definition names)."""
    if isinstance(schema, dict):
        yield schema
        for key, value in schema.items():
            if key in ("properties", "definitions") and isinstance(value, dict):
                for sub in value.values():
                    yield from schema_nodes(sub)
            elif key in ("items", "additionalProperties"):
                yield from schema_nodes(value)
            elif key == "anyOf":
                for sub in value:
                    yield from schema_nodes(sub)


class Leaf(Value):
    word: Annotated[str, Field(min_length=1, max_length=20, pattern="^[a-z]+$", description="a lowercase word")]
    count: Annotated[int, Field(ge=0, le=10, multiple_of=1)] = 0
    ratio: Annotated[float, Field(gt=0, lt=1)] = 0.5
    day: Annotated[str, Field(json_schema_extra={"format": "date"})] = "2026-01-01"


class Plain(Value):
    reason: str
    leaf: Leaf
    leaves: Annotated[list[Leaf], Field(min_length=1, max_length=4)] = []
    mode: Literal["fast", "slow"] = "fast"
    fixed: Literal["only"] = "only"
    note: Optional[str] = None
    amount: Optional[int] = None
    tags: Optional[list[str]] = None


class Add(Value):
    op: Literal["add"] = "add"
    name: str


class Move(Value):
    op: Literal["move"] = "move"
    to: str


Op = Annotated[Union[Add, Move], Field(discriminator="op")]


class Request(Value):
    reason: str
    ops: Annotated[list[Op], Field(max_length=8)] = []
    first: Optional[Op] = None


# ---- the draft-07 shape ----------------------------------------------------------------------------------------------

def test_the_schema_is_draft_07_with_definitions():
    schema = transport_schema(Plain)
    assert schema["$schema"] == TRANSPORT_DRAFT == "http://json-schema.org/draft-07/schema#"
    assert "$defs" not in schema and set(schema["definitions"]) == {"Leaf"}
    assert schema["properties"]["leaf"] == {"$ref": "#/definitions/Leaf"}
    assert schema["properties"]["leaves"]["items"] == {"$ref": "#/definitions/Leaf"}
    assert "$defs" not in json.dumps(schema)
    assert list(schema)[0] == "$schema"


def test_every_object_is_closed_and_every_property_is_required():
    schema = transport_schema(Plain)
    objects = [n for n in schema_nodes(schema) if n.get("type") == "object"]
    assert len(objects) == 2
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])


def test_length_pattern_format_default_title_and_range_keywords_are_removed_everywhere():
    schema = transport_schema(Plain)
    banned = {"minLength", "maxLength", "minItems", "maxItems", "pattern", "format", "exclusiveMinimum", "exclusiveMaximum",
              "minimum", "maximum", "multipleOf", "default", "title", "examples", "const", "oneOf", "discriminator"}
    for node in schema_nodes(schema):
        assert not banned & set(node), node
    leaf = schema["definitions"]["Leaf"]["properties"]
    assert leaf["word"] == {"description": "a lowercase word", "type": "string"}        # the description is kept
    assert leaf["count"] == {"type": "integer"} and leaf["ratio"] == {"type": "number"} and leaf["day"] == {"type": "string"}
    assert schema["properties"]["leaves"] == {"items": {"$ref": "#/definitions/Leaf"}, "type": "array"}


def test_a_wire_alias_is_the_property_name_the_model_must_use():
    class Wire(Value):
        passed: bool = Field(default=False, alias="pass")
        origin: str = Field(default="", alias="from")

    schema = transport_schema(Wire)
    assert list(schema["properties"]) == ["pass", "from"] and schema["required"] == ["pass", "from"]


def test_a_plain_pydantic_model_is_closed_too():
    from pydantic import BaseModel

    class Open(BaseModel):
        a: int = 0

    class Outer(BaseModel):
        open: Open
        many: list[Open] = []

    schema = transport_schema(Outer)
    assert schema["additionalProperties"] is False and schema["definitions"]["Open"]["additionalProperties"] is False
    assert is_transport_safe(schema) == []


def test_the_generated_schema_passes_its_own_checker():
    for model in (Plain, Request, Leaf, Add):
        assert is_transport_safe(transport_schema(model)) == []


def test_property_names_that_look_like_keywords_survive():
    class Awkward(Value):
        title: str
        default: int
        format: str
        const: bool
        pattern: str
        discriminator: str
        description: str

    schema = transport_schema(Awkward)
    assert list(schema["properties"]) == ["title", "default", "format", "const", "pattern", "discriminator", "description"]
    assert schema["required"] == list(schema["properties"])
    assert is_transport_safe(schema) == []


def test_asking_for_a_non_model_is_a_registry_error():
    for bad in (int, "Plain", Plain(reason="x", leaf=Leaf(word="a")), None):
        with pytest.raises(RegistryError) as e:
            transport_schema(bad)
        assert e.value.code == "not_model"


# ---- const stays as a one-value enum ---------------------------------------------------------------------------------

def test_a_single_value_literal_becomes_a_one_value_enum():
    props = transport_schema(Plain)["properties"]
    assert props["fixed"] == {"enum": ["only"], "type": "string"}
    assert "const" not in json.dumps(transport_schema(Plain))
    assert props["mode"] == {"enum": ["fast", "slow"], "type": "string"}


def test_a_const_of_any_json_type_becomes_an_enum():
    class Numbers(Value):
        one: Literal[1] = 1
        yes: Literal[True] = True

    props = transport_schema(Numbers)["properties"]
    assert props["one"]["enum"] == [1] and props["yes"]["enum"] == [True]
    assert "const" not in json.dumps(transport_schema(Numbers))


def test_a_record_kind_is_a_one_value_enum_so_a_reply_says_what_it_is():
    class Price(Record):
        FAMILY = "toy"
        kind: Literal["price"] = "price"
        decision: Literal["GRANT", "COUNTER"]

    props = transport_schema(Price)["properties"]
    assert props["kind"]["enum"] == ["price"]
    assert props["schema_version"] == {"type": "integer"}


# ---- unions become anyOf ---------------------------------------------------------------------------------------------

def test_a_discriminated_union_is_anyof_without_oneof_or_discriminator():
    schema = transport_schema(Request)
    items = schema["properties"]["ops"]["items"]
    assert items == {"anyOf": [{"$ref": "#/definitions/Add"}, {"$ref": "#/definitions/Move"}]}
    text = json.dumps(schema)
    assert "oneOf" not in text and "discriminator" not in text
    assert schema["definitions"]["Add"]["properties"]["op"] == {"enum": ["add"], "type": "string"}
    assert schema["definitions"]["Move"]["properties"]["op"] == {"enum": ["move"], "type": "string"}
    for name in ("Add", "Move"):
        assert schema["definitions"][name]["additionalProperties"] is False


def test_an_optional_union_keeps_its_members_and_loses_only_the_null_as_j2_did():
    # J2 parity: anyOf [A, B, null] -> anyOf [A, B]; the property is then optional only through TRANSPORT_OPTIONAL.
    first = transport_schema(Request)["properties"]["first"]
    assert first == {"anyOf": [{"$ref": "#/definitions/Add"}, {"$ref": "#/definitions/Move"}]}


def test_a_union_of_scalars_and_a_model_is_kept_as_anyof():
    class Mixed(Value):
        either: Union[int, Leaf]

    schema = transport_schema(Mixed)
    assert schema["properties"]["either"]["anyOf"] == [{"type": "integer"}, {"$ref": "#/definitions/Leaf"}]


# ---- Optional[X] is folded into a type list --------------------------------------------------------------------------

def test_optional_scalars_become_a_type_list():
    props = transport_schema(Plain)["properties"]
    assert props["note"] == {"type": ["string", "null"]}
    assert props["amount"] == {"type": ["integer", "null"]}
    assert props["tags"] == {"items": {"type": "string"}, "type": ["array", "null"]}


def test_an_optional_enum_allows_null_in_the_enum_too():
    class Choosy(Value):
        pick: Optional[Literal["a", "b"]] = None
        solo: Optional[Literal["a"]] = None

    props = transport_schema(Choosy)["properties"]
    assert props["pick"] == {"enum": ["a", "b", None], "type": ["string", "null"]}
    assert props["solo"] == {"enum": ["a", None], "type": ["string", "null"]}


# ---- optional fields -------------------------------------------------------------------------------------------------

def test_transport_optional_names_are_left_out_of_required():
    class Sparse(Value):
        TRANSPORT_OPTIONAL = frozenset({"hint", "extra"})
        reason: str
        hint: str = ""
        extra: Optional[int] = None

    schema = transport_schema(Sparse)
    assert schema["required"] == ["reason"]
    assert list(schema["properties"]) == ["reason", "hint", "extra"]          # still described, just not required


def test_the_optional_set_of_a_class_applies_to_its_own_properties_only():
    class Inner(Value):
        TRANSPORT_OPTIONAL = frozenset({"detail"})
        name: str
        detail: str = ""

    class Outer(Value):
        TRANSPORT_OPTIONAL = frozenset({"inner_list"})
        inner: Inner
        inner_list: list[Inner] = []
        detail: str = ""                      # the same name in the outer class: Outer's own set does not list it

    schema = transport_schema(Outer)
    assert schema["definitions"]["Inner"]["required"] == ["name"]
    assert schema["required"] == ["inner", "detail"]


def test_a_reply_class_that_marks_reason_and_say_optional_does_not_loosen_the_classes_nested_in_it():
    # Review round 1: the set used to be the union over the whole tree, applied by name at every depth. A model could then
    # leave out the `reason` of a nested row, the schema accepted that, and the strict class refused the reply.
    class LeftOut(Value):
        item: int
        reason: str

    class Dispute(Value):
        party: str
        about: str
        reason: str

    class Reply(Value):
        TRANSPORT_OPTIONAL = frozenset({"reason", "say"})
        say: str = ""
        reason: str = ""
        left_out: list[LeftOut] = []
        dispute: Optional[Dispute] = None

    schema = transport_schema(Reply)
    assert schema["required"] == ["left_out", "dispute"]
    assert schema["definitions"]["LeftOut"]["required"] == ["item", "reason"]
    assert schema["definitions"]["Dispute"]["required"] == ["party", "about", "reason"]
    with pytest.raises(ValidationError):                         # the strict class agrees with the transport schema now
        Reply.model_validate({"left_out": [{"item": 1}]})
    assert Reply.model_validate({"left_out": [{"item": 1, "reason": "r"}]}).left_out[0].reason == "r"


def test_the_optional_set_of_a_nested_class_reaches_neither_the_class_around_it_nor_its_neighbours():
    class Loose(Value):
        TRANSPORT_OPTIONAL = frozenset({"x"})
        x: str = ""
        y: str

    class Tight(Value):
        x: str
        y: str

    class Root(Value):
        loose: Loose
        tight: Tight
        x: str

    schema = transport_schema(Root)
    assert schema["required"] == ["loose", "tight", "x"]
    assert schema["definitions"]["Loose"]["required"] == ["y"]
    assert schema["definitions"]["Tight"]["required"] == ["x", "y"]


def test_every_member_of_a_union_and_every_level_of_nesting_uses_its_own_classes_set():
    class Add(Value):
        TRANSPORT_OPTIONAL = frozenset({"note"})
        op: Literal["add"] = "add"
        name: str
        note: str = ""

    class Move(Value):
        op: Literal["move"] = "move"
        to: str
        note: str = ""

    class Group(Value):
        TRANSPORT_OPTIONAL = frozenset({"ops"})
        ops: list[Annotated[Union[Add, Move], Field(discriminator="op")]] = []
        note: str = ""

    class Top(Value):
        group: Group
        note: str = ""

    schema = transport_schema(Top)
    assert schema["required"] == ["group", "note"]
    assert schema["definitions"]["Group"]["required"] == ["note"]
    assert schema["definitions"]["Add"]["required"] == ["op", "name"]
    assert schema["definitions"]["Move"]["required"] == ["op", "to", "note"]


def test_a_subclass_inherits_the_optional_set_of_its_base_class_so_one_set_can_serve_a_whole_family_of_classes():
    # How the J2 artifact models keep J2's global OPTIONAL_FIELDS: the set sits once on their base class.
    class Base(Value):
        TRANSPORT_OPTIONAL = frozenset({"reason", "hint"})

    class Row(Base):
        item: int
        reason: str = ""

    class Section(Base):
        reason: str = ""
        hint: str = ""
        rows: list[Row] = []

    class Strict(Row):
        TRANSPORT_OPTIONAL = frozenset()                         # a subclass may replace the set

    class Wider(Row):
        TRANSPORT_OPTIONAL = Row.TRANSPORT_OPTIONAL | {"item"}   # or extend it

    schema = transport_schema(Section)
    assert schema["required"] == ["rows"]
    assert schema["definitions"]["Row"]["required"] == ["item"]
    assert transport_schema(Strict)["required"] == ["item", "reason"]
    assert transport_schema(Wider)["required"] == ["item", "reason"]        # all optional: all required, as in J2


def test_two_nested_classes_with_the_same_name_and_the_same_fields_keep_their_own_sets():
    def row(optional):
        class Row(Value):
            TRANSPORT_OPTIONAL = frozenset(optional)
            a: str = ""
            b: str = ""
        return Row

    first_row, second_row = row({"a"}), row({"b"})

    class Pair(Value):
        first: first_row
        second: second_row

    schema = transport_schema(Pair)
    ref_of = lambda name: schema["properties"][name]["$ref"].rsplit("/", 1)[1]
    assert ref_of("first") != ref_of("second")
    assert schema["definitions"][ref_of("first")]["required"] == ["b"]
    assert schema["definitions"][ref_of("second")]["required"] == ["a"]


def test_the_optional_names_are_the_json_property_names_and_names_that_are_not_properties_are_ignored():
    class Wire(Value):
        TRANSPORT_OPTIONAL = frozenset({"pass", "nothing_of_this_name"})
        passed: bool = Field(default=False, alias="pass")
        kept: bool = False

    assert transport_schema(Wire)["required"] == ["kept"]

    class ByFieldName(Value):
        TRANSPORT_OPTIONAL = frozenset({"passed"})                # the field name, not the wire key: no effect
        passed: bool = Field(default=False, alias="pass")

    assert transport_schema(ByFieldName)["required"] == ["pass"]


def test_the_marker_the_generator_adds_never_leaves_the_transport_schema_nor_reaches_the_exported_one():
    class Row(Value):
        TRANSPORT_OPTIONAL = frozenset({"reason"})
        reason: str = ""
        item: int = 0

    class Reply(Value):
        TRANSPORT_OPTIONAL = frozenset({"reason"})
        reason: str = ""
        rows: list[Row] = []

    marker = registry_module._OPTIONAL_KEY
    assert marker in json.dumps(Reply.model_json_schema(by_alias=True, schema_generator=registry_module._TransportSchemaGenerator))
    assert marker not in json.dumps(Reply.model_json_schema(by_alias=True))
    assert marker not in json.dumps(transport_schema(Reply))
    assert marker not in json.dumps(reply_schema(Reply, {}))
    registry = ModelRegistry()
    registry.register_payload("reply", 1, Reply)
    assert marker not in json.dumps(registry.json_schema("reply"))
    assert marker not in json.dumps(registry.transport_schema("reply"))
    assert is_transport_safe(transport_schema(Reply)) == []


def test_when_every_property_is_optional_all_of_them_are_required_as_in_j2():
    class AllOptional(Value):
        TRANSPORT_OPTIONAL = frozenset({"a", "b"})
        a: str = ""
        b: str = ""

    assert transport_schema(AllOptional)["required"] == ["a", "b"]


def test_a_class_without_fields_is_an_empty_closed_object():
    class Nothing(Value):
        pass

    schema = transport_schema(Nothing)
    assert schema["properties"] == {} and schema["required"] == [] and schema["additionalProperties"] is False
    assert is_transport_safe(schema) == []


# ---- refusals --------------------------------------------------------------------------------------------------------

def test_a_recursive_class_is_refused():
    class Tree(Value):
        label: str
        children: list["Tree"] = []

    Tree.model_rebuild()
    with pytest.raises(RegistryError) as e:
        transport_schema(Tree)
    assert e.value.code == "transport_recursion" and "Tree -> Tree" in str(e.value)


def test_mutual_recursion_is_refused_too():
    class Ping(Value):
        pong: Optional["Pong"] = None

    class Pong(Value):
        ping: Optional[Ping] = None

    Ping.model_rebuild()
    Pong.model_rebuild()
    with pytest.raises(RegistryError) as e:
        transport_schema(Ping)
    assert e.value.code == "transport_recursion"


def test_a_shared_nested_class_is_not_recursion():
    class Shared(Value):
        name: str

    class Both(Value):
        left: Shared
        right: Shared
        many: list[Shared] = []

    assert is_transport_safe(transport_schema(Both)) == []


@pytest.mark.parametrize("make", [
    lambda: dict[str, str],
    lambda: dict,
    lambda: Optional[dict[str, int]],
    lambda: list[dict[str, str]],
    lambda: dict[str, list[int]],
])
def test_a_dict_with_free_keys_raises_transport_dict(make):
    annotation = make()

    class Loose(Value):
        pairs: annotation

    with pytest.raises(RegistryError) as e:
        transport_schema(Loose)
    assert e.value.code == "transport_dict"
    assert "list of pairs" in str(e.value)


def test_a_free_dict_inside_a_nested_class_is_refused_too():
    class Bag(Value):
        stuff: dict[str, str]

    class Holder(Value):
        bag: Bag

    with pytest.raises(RegistryError) as e:
        transport_schema(Holder)
    assert e.value.code == "transport_dict"


def test_a_list_of_pairs_is_the_way_to_send_a_mapping():
    class Pair(Value):
        key: str
        value: str

    class Mapped(Value):
        pairs: list[Pair]

    assert is_transport_safe(transport_schema(Mapped)) == []


# ---- the checker -----------------------------------------------------------------------------------------------------

def good_schema():
    return copy.deepcopy(transport_schema(Plain))


def test_the_checker_accepts_nothing_but_a_schema_object():
    assert is_transport_safe("not a schema") and is_transport_safe(None) and is_transport_safe([])


@pytest.mark.parametrize("mutate, code", [
    (lambda s: s.update({"$schema": "https://json-schema.org/draft/2020-12/schema"}), "draft"),
    (lambda s: s.pop("$schema"), "draft"),
    (lambda s: s.update({"$defs": {}}), "keyword_not_allowed"),
    (lambda s: s["properties"]["reason"].update({"minLength": 1}), "keyword_not_allowed"),
    (lambda s: s["properties"]["reason"].update({"pattern": "^a$"}), "keyword_not_allowed"),
    (lambda s: s["properties"]["reason"].update({"default": ""}), "keyword_not_allowed"),
    (lambda s: s["properties"]["reason"].update({"title": "Reason"}), "keyword_not_allowed"),
    (lambda s: s["properties"]["fixed"].update({"const": "only"}), "keyword_not_allowed"),
    (lambda s: s["properties"]["leaves"].update({"maxItems": 4}), "keyword_not_allowed"),
    (lambda s: s["properties"]["mode"].update({"oneOf": [{"type": "string"}]}), "keyword_not_allowed"),
    (lambda s: s["properties"]["mode"].update({"discriminator": {"propertyName": "x"}}), "keyword_not_allowed"),
    (lambda s: s["properties"]["mode"].update({"allOf": []}), "keyword_not_allowed"),
    (lambda s: s["definitions"]["Leaf"].update({"additionalProperties": True}), "not_closed"),
    (lambda s: s["definitions"]["Leaf"].pop("additionalProperties"), "not_closed"),
    (lambda s: s.update({"additionalProperties": {"type": "string"}}), "not_closed"),
    (lambda s: s["definitions"]["Leaf"].pop("properties"), "transport_dict"),
    (lambda s: s["properties"].update({"free": {"type": "object", "additionalProperties": False}}), "transport_dict"),
    (lambda s: s["definitions"]["Leaf"]["required"].append("ghost"), "bad_required"),
    (lambda s: s["properties"].update({"x": {"$ref": "#/definitions/Missing"}}), "bad_ref"),
    (lambda s: s["properties"].update({"x": {"$ref": "#/$defs/Leaf"}}), "bad_ref"),
    (lambda s: s["definitions"]["Leaf"]["properties"].update({"back": {"$ref": "#/definitions/Leaf"}}), "transport_recursion"),
    (lambda s: s["properties"]["note"].update({"enum": ["a"]}), "enum_null"),
])
def test_the_checker_reports_what_the_transport_refuses(mutate, code):
    schema = good_schema()
    mutate(schema)
    problems = is_transport_safe(schema)
    assert problems and any(f": {code}: " in p for p in problems), problems


def test_the_checker_looks_inside_items_and_union_members():
    schema = good_schema()
    schema["properties"]["tags"] = {"type": "array", "items": {"type": "object", "properties": {}}}
    schema["properties"]["either"] = {"anyOf": [{"type": "object", "properties": {"x": {"type": "string", "minLength": 1}}, "additionalProperties": False}, {"type": "null"}]}
    problems = is_transport_safe(schema)
    assert any(p.startswith("#/properties/tags/items: not_closed") for p in problems), problems
    assert any(p.startswith("#/properties/either/anyOf/0/properties/x: keyword_not_allowed") for p in problems), problems
    assert len(problems) == 2


def test_the_checker_names_the_place_of_each_problem():
    schema = good_schema()
    schema["definitions"]["Leaf"]["properties"]["word"]["minLength"] = 1
    [problem] = is_transport_safe(schema)
    assert problem.startswith("#/definitions/Leaf/properties/word: keyword_not_allowed: 'minLength'")


def test_the_checker_does_not_mistake_a_property_called_default_for_a_keyword():
    schema = good_schema()
    schema["properties"]["default"] = {"type": "string"}
    schema["properties"]["title"] = {"type": "string"}
    assert is_transport_safe(schema) == []


def test_a_ladder_of_shared_definitions_is_not_walked_over_and_over():
    from sutra_app.library import registry as registry_module
    depth = 18
    definitions = {f"D{i}": {"type": "object", "additionalProperties": False, "required": ["a", "b"],
                             "properties": {"a": {"$ref": f"#/definitions/D{i + 1}"}, "b": {"$ref": f"#/definitions/D{i + 1}"}}}
                   for i in range(depth)}
    definitions[f"D{depth}"] = {"type": "object", "additionalProperties": False, "required": [], "properties": {}}
    schema = {"$schema": TRANSPORT_DRAFT, "type": "object", "additionalProperties": False, "required": ["a"],
              "properties": {"a": {"$ref": "#/definitions/D0"}}, "definitions": definitions}
    reads = []
    real = registry_module._refs_in
    registry_module._refs_in = lambda node: (reads.append(1) if any(node is d for d in definitions.values()) else None) or real(node)
    try:
        assert registry_module._find_cycle(schema) is None
    finally:
        registry_module._refs_in = real
    assert len(reads) == depth + 1                                          # each definition is read once, not 2**18 times


def test_mutual_recursion_through_definitions_is_reported():
    schema = {"$schema": TRANSPORT_DRAFT, "type": "object", "additionalProperties": False, "required": ["a"],
              "properties": {"a": {"$ref": "#/definitions/A"}},
              "definitions": {
                  "A": {"type": "object", "additionalProperties": False, "required": ["b"], "properties": {"b": {"$ref": "#/definitions/B"}}},
                  "B": {"type": "object", "additionalProperties": False, "required": ["a"], "properties": {"a": {"$ref": "#/definitions/A"}}}}}
    problems = is_transport_safe(schema)
    assert any("transport_recursion" in p and "A -> B -> A" in p for p in problems), problems


# ---- reply_schema (ported as is) --------------------------------------------------------------------------------------

def test_reply_schema_wraps_a_section_with_reason_first():
    schema = reply_schema(Plain, None)
    assert list(schema["properties"]) == ["reason", "say", "human_output", "atom_human_output", "next", "section"]
    assert schema["required"] == ["reason", "say", "human_output", "atom_human_output", "next", "section"]
    assert schema["additionalProperties"] is False and schema["type"] == "object"
    assert schema["$schema"] == TRANSPORT_DRAFT
    section = schema["properties"]["section"]
    assert "$schema" not in section and "definitions" not in section
    assert set(schema["definitions"]) == {"Leaf"}
    assert section["properties"]["leaf"] == {"$ref": "#/definitions/Leaf"}


def test_reply_schema_extra_fields_are_properties_but_not_required():
    schema = reply_schema(Add, {"board": {"type": "string"}, "spec": {"type": "object"}})
    assert list(schema["properties"])[-2:] == ["board", "spec"]
    assert "board" not in schema["required"] and "spec" not in schema["required"]
    assert "definitions" not in schema                      # Add has no nested classes


def test_reply_schema_is_checkable_like_any_other():
    assert is_transport_safe(reply_schema(Plain, {})) == []


def test_reply_schema_uses_the_library_transport_schema_for_the_section():
    schema = reply_schema(Request, {})
    assert schema["properties"]["section"]["properties"]["ops"]["items"] == {
        "anyOf": [{"$ref": "#/definitions/Add"}, {"$ref": "#/definitions/Move"}]}


# ---- schema_sha --------------------------------------------------------------------------------------------------------

def test_schema_sha_is_the_sha256_of_the_sorted_json():
    schema = transport_schema(Plain)
    assert schema_sha(schema) == hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert schema_sha({"b": 1, "a": 2}) == schema_sha({"a": 2, "b": 1})
    other = copy.deepcopy(schema)
    other["required"] = other["required"][:-1]
    assert schema_sha(other) != schema_sha(schema)


def test_schema_sha_keeps_non_ascii_text_as_it_is():
    schema = {"description": "café — naïve", "type": "string"}
    expected = hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert schema_sha(schema) == expected
    assert expected != hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def test_the_schema_is_the_same_every_time_it_is_asked_for():
    assert schema_sha(transport_schema(Plain)) == schema_sha(transport_schema(Plain))
    first = transport_schema(Plain)
    first["required"].append("tampered")
    assert "tampered" not in transport_schema(Plain)["required"]
