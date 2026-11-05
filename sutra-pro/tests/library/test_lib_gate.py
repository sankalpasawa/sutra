"""The one write gate (library design 3.4): Checked, the seven steps of Gate.check, and the shipped cross rules."""
import collections
import copy
import enum
import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType, SimpleNamespace
from typing import Annotated, Literal, Optional

import pytest
from pydantic import BaseModel, Field, ValidationError, field_validator

from sutra_app.library import gate as gate_module
from sutra_app.library.base import Record, Value
from sutra_app.library.gate import (
    GATE, MAX_PAYLOAD_BYTES, SHIPPED_CROSS_RULES, Checked, FunctionRule, Gate, GateError, cross_rule,
)
from sutra_app.library.registry import REGISTRY, ModelRegistry, RegistryError
from sutra_app.library.types import Violation, violation


class PlainModel(BaseModel):
    """A pydantic model that is not a library Value: the gate does not take it."""
    x: int = 0


def refused(toys_or_gate, *args, **kwargs) -> GateError:
    gate = getattr(toys_or_gate, "gate", toys_or_gate)
    with pytest.raises(GateError) as e:
        gate.check(*args, **kwargs)
    return e.value


def facts(error: GateError):
    return [(v.path, v.code) for v in error.violations]


GOOD = {"kind": "thing", "name": "n", "count": 2, "tags": ["a"]}


# ---- Checked ------------------------------------------------------------------------------------------------------------

def test_checked_cannot_be_built_by_hand(toys):
    model = toys.Thing(name="n")
    fields = dict(model=model, family="thing", version=1, kind="thing", json="{}", sha256="0" * 64)
    for call in (lambda: Checked(), lambda: Checked(**fields), lambda: Checked(model, "thing", 1, "thing", "{}", "0" * 64),
                 lambda: Checked(object(), model, "thing", 1, "thing", "{}", "0" * 64),
                 lambda: Checked(None, model, "thing", 1, "thing", "{}", "0" * 64),
                 lambda: Checked(*fields.values(), forged=True), lambda: Checked[type(model)](**fields)):
        with pytest.raises(TypeError, match="Gate.check"):
            call()


def test_even_the_private_token_opens_the_door_only_for_exactly_seven_positional_arguments(toys):
    token, model = gate_module._TOKEN, toys.Thing(name="n")
    good = (token, model, "thing", 1, "thing", "{}", "0" * 64)
    assert Checked(*good).family == "thing"
    for bad in (good[:-1], good + ("extra",), (token,)):
        with pytest.raises(TypeError):
            Checked(*bad)
    with pytest.raises(TypeError):
        Checked(*good, bogus=1)
    with pytest.raises(TypeError):
        Checked(*good[:6], sha256="0" * 64)


def test_checked_is_immutable_and_has_no_dict(toys):
    checked = toys.gate.check("thing", GOOD)
    for name in ("model", "family", "version", "kind", "json", "sha256"):
        with pytest.raises(AttributeError):
            setattr(checked, name, "x")
        with pytest.raises(AttributeError):
            delattr(checked, name)
    with pytest.raises(AttributeError):
        checked.extra = 1
    assert not hasattr(checked, "__dict__")


def test_checked_cannot_be_subclassed():
    with pytest.raises(TypeError):
        class Forged(Checked):
            pass


def test_two_checked_are_equal_only_when_family_version_kind_and_hash_all_agree(toys):
    model = toys.Thing(name="n")
    make = lambda family="f", version=1, kind="k", sha="a" * 64: gate_module._make_checked(model, family, version, kind, "{}", sha)
    assert make() == make() and hash(make()) == hash(make())
    for different in (make(family="g"), make(version=2), make(kind="j"), make(sha="b" * 64)):
        assert make() != different
    assert make().json == "{}" and make().model is model


def test_checked_carries_the_model_and_what_a_store_writes(toys):
    checked = toys.gate.check("thing", GOOD)
    assert isinstance(checked, Checked) and type(checked.model) is toys.Thing
    assert (checked.family, checked.version, checked.kind) == ("thing", 1, "thing")
    assert checked.json == checked.model.canonical_json()
    assert checked.sha256 == hashlib.sha256(checked.json.encode("utf-8")).hexdigest()
    assert json.loads(checked.json) == {"kind": "thing", "schema_version": 1, "name": "n", "count": 2, "tags": ["a"],
                                        "pass": False, "note": None}


def test_checked_repr_does_not_print_the_body(toys):
    text = repr(toys.gate.check("thing", {**GOOD, "name": "secret-name"}))
    assert "secret-name" not in text and "thing" in text and "v1" in text and "sha256=" in text


def test_checked_equality_hash_and_copies(toys):
    one, same, other = (toys.gate.check("thing", GOOD), toys.gate.check("thing", dict(GOOD)),
                        toys.gate.check("thing", {**GOOD, "count": 3}))
    assert one == same and hash(one) == hash(same) and one != other and one != "x"
    assert hash(one) != hash(other) and len({one, same, other}) == 2
    assert copy.copy(one) is one and copy.deepcopy(one) is one
    assert {one: 1}[same] == 1


# ---- the happy path ---------------------------------------------------------------------------------------------------

def test_every_payload_form_gives_the_same_checked(toys):
    model = toys.Thing(name="n", count=2, tags=["a"])
    forms = [GOOD, json.dumps(GOOD), json.dumps(GOOD).encode(), bytearray(json.dumps(GOOD).encode()),
             memoryview(json.dumps(GOOD).encode()), model]
    results = [toys.gate.check("thing", form) for form in forms]
    assert len({r.sha256 for r in results}) == 1 and len({r.json for r in results}) == 1
    assert all(r == results[0] and r.model == model for r in results)


def test_the_canonical_json_and_sha_do_not_depend_on_key_order(toys):
    one = toys.gate.check("thing", {"kind": "thing", "name": "n", "count": 2, "tags": ["a", "b"]})
    two = toys.gate.check("thing", {"tags": ["a", "b"], "count": 2, "name": "n", "kind": "thing"})
    three = toys.gate.check("thing", '{"name":"n","tags":["a","b"],"kind":"thing","count":2}')
    assert one.json == two.json == three.json and one.sha256 == two.sha256 == three.sha256
    assert one.json == '{"count":2,"kind":"thing","name":"n","note":null,"pass":false,"schema_version":1,"tags":["a","b"]}'
    assert toys.gate.check("thing", {**GOOD, "tags": ["b", "a"]}).sha256 != toys.gate.check("thing", {**GOOD, "tags": ["a", "b"]}).sha256


def test_the_wire_alias_and_the_field_name_both_read_but_the_alias_is_written(toys):
    by_alias = toys.gate.check("thing", {"kind": "thing", "name": "n", "pass": True})
    by_name = toys.gate.check("thing", {"kind": "thing", "name": "n", "passed": True})
    assert by_alias.sha256 == by_name.sha256 and '"pass":true' in by_alias.json and "passed" not in by_alias.json


def test_defaults_are_filled_in_and_strings_are_stripped(toys):
    checked = toys.gate.check("thing", {"name": "  padded  "})
    assert checked.model.name == "padded" and checked.model.kind == "thing" and checked.model.schema_version == 1


def test_the_kind_of_a_checked_is_the_kind_of_its_model(toys):
    assert toys.gate.check("pair", {"kind": "alpha"}).kind == "alpha"
    assert toys.gate.check("pair", {"kind": "gamma"}).kind == "gamma"
    assert type(toys.gate.check("pair", {"kind": "gamma"}).model) is toys.Beta
    assert toys.gate.check("doc", {"title": "t"}).kind == "doc"                # a payload: its own name


def test_payload_families_are_never_upgraded_by_the_gate_even_with_a_field_called_schema_version():
    reg = ModelRegistry()

    class One(Value):
        schema_version: int = 1

    class Two(Value):
        schema_version: int = 2
        extra: str = ""

    reg.register_payload("section", 1, One)
    reg.register_payload("section", 2, Two)
    seen = []
    reg.upgrade("section", 1)(lambda payload: seen.append(payload) or {"schema_version": 2})
    gate = Gate(reg)
    assert gate.check("section", {"schema_version": 1}).version == 2 and seen == []         # read as the latest class
    assert gate.check("section", {"schema_version": 1}, version=1).version == 1


def test_a_payload_with_a_field_called_kind_still_has_its_family_as_its_kind():
    reg = ModelRegistry()

    class Labelled(Value):
        kind: str = "free text"

    reg.register_payload("labelled", 1, Labelled)
    checked = Gate(reg).check("labelled", {"kind": "anything goes"})
    assert checked.kind == "labelled" and checked.model.kind == "anything goes"


def test_a_payload_family_checks_like_any_other(toys):
    checked = toys.gate.check("doc", {"title": "t", "items": [{"n": 1}, {"n": 2, "label": "b"}]})
    assert type(checked.model) is toys.Doc and checked.version == 1 and checked.model.items[1].label == "b"
    assert refused(toys, "doc", {"title": "t", "items": [{"n": "1"}]}).violations[0].path == "items.0.n"


def test_a_nested_model_instance_inside_a_dict_is_checked_again(toys):
    assert toys.gate.check("doc", {"title": "t", "items": [toys.Item(n=1)]}).model.items[0].n == 1
    error = refused(toys, "doc", {"title": "t", "items": [toys.Item.model_construct(n="bad")]})
    assert error.stage == "shape" and facts(error) == [("items.0.n", "int_type")]


def test_the_version_can_be_named(toys):
    assert toys.gate.check("thing", GOOD, version=1).version == 1


# ---- stage: unknown --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("family", ["ghost", "", "Thing", None, 5, ["thing"]])
def test_an_unknown_family_is_refused(toys, family):
    error = refused(toys, family, GOOD)
    assert error.stage == "unknown" and facts(error) == [("", "unknown_family")]


@pytest.mark.parametrize("version", [0, 2, -1, True, "1", 1.0])
def test_an_unknown_version_is_refused(toys, version):
    error = refused(toys, "thing", GOOD, version=version)
    assert error.stage == "unknown" and facts(error) == [("", "unknown_version")]


def test_unknown_comes_before_size_and_shape(toys):
    assert refused(toys, "ghost", "x" * (MAX_PAYLOAD_BYTES + 1)).stage == "unknown"
    assert refused(toys, "ghost", object()).stage == "unknown"
    assert refused(toys, "thing", object(), version=9).stage == "unknown"


def test_a_long_family_name_is_not_echoed_in_full(toys):
    error = refused(toys, "f" * 500, GOOD)
    assert error.family == "f" * 79 + "…" and len(error.violations[0].message) <= 300


# ---- stage: size -----------------------------------------------------------------------------------------------------

def blob_gate():
    reg = ModelRegistry()

    class Blob(Record):
        FAMILY = "blob"
        kind: Literal["blob"] = "blob"
        text: str

    reg.register(Blob)
    return Gate(reg)


def blob_payload(total_bytes: int) -> str:
    head, tail = '{"kind":"blob","text":"', '"}'
    return head + "a" * (total_bytes - len(head) - len(tail)) + tail


def test_the_size_limit_is_one_mebibyte_exactly():
    assert MAX_PAYLOAD_BYTES == 1_048_576 == 1024 * 1024
    gate = blob_gate()
    at_limit = blob_payload(MAX_PAYLOAD_BYTES)
    assert len(at_limit.encode()) == MAX_PAYLOAD_BYTES
    assert len(gate.check("blob", at_limit).model.text) == MAX_PAYLOAD_BYTES - 23 - 2
    over = refused(gate, "blob", blob_payload(MAX_PAYLOAD_BYTES + 1))
    assert over.stage == "size" and facts(over) == [("", "payload_too_large")]


def test_a_payload_of_exactly_the_limit_passes_in_every_form():
    gate = blob_gate()
    exact = blob_payload(MAX_PAYLOAD_BYTES)
    for form in (exact, exact.encode(), bytearray(exact.encode()), memoryview(exact.encode())):
        assert gate.check("blob", form).model.text.startswith("aaa")
    assert refused(gate, "blob", exact.encode() + b" ").stage == "size"
    assert refused(gate, "blob", exact + " ").stage == "size"


def test_size_is_judged_before_the_text_is_read_at_all():
    gate = blob_gate()
    not_utf8 = b"\xff" * (MAX_PAYLOAD_BYTES + 1)                     # would be bad_unicode if anyone tried to decode it
    assert facts(refused(gate, "blob", not_utf8)) == [("", "payload_too_large")]
    assert facts(refused(gate, "blob", bytearray(not_utf8))) == [("", "payload_too_large")]
    lone_surrogate = "\ud800" * (MAX_PAYLOAD_BYTES + 1)               # would be bad_unicode if anyone tried to encode it
    assert facts(refused(gate, "blob", lone_surrogate)) == [("", "payload_too_large")]
    assert facts(refused(gate, "blob", b"\xff")) == [("", "bad_unicode")]
    assert facts(refused(gate, "blob", "\ud800")) == [("", "bad_unicode")]


def test_every_payload_form_is_measured_in_bytes(toys):
    big = blob_payload(MAX_PAYLOAD_BYTES + 10)
    gate = blob_gate()
    assert refused(gate, "blob", big.encode()).stage == "size"
    assert refused(gate, "blob", bytearray(big.encode())).stage == "size"
    assert refused(gate, "blob", memoryview(big.encode())).stage == "size"
    assert refused(gate, "blob", {"kind": "blob", "text": "a" * MAX_PAYLOAD_BYTES}).stage == "size"
    assert refused(gate, "blob", gate.registry.adapter("blob").validate_python({"text": "a" * MAX_PAYLOAD_BYTES})).stage == "size"
    two_bytes = '{"kind":"blob","text":"' + "é" * (MAX_PAYLOAD_BYTES // 2) + '"}'
    assert len(two_bytes) < MAX_PAYLOAD_BYTES < len(two_bytes.encode())
    assert refused(gate, "blob", two_bytes).stage == "size"


# ---- stage: shape ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("payload, path, code", [
    ({"kind": "thing", "name": "n", "count": "1"}, "count", "int_type"),
    ({"kind": "thing", "name": "n", "count": 1.0}, "count", "int_type"),
    ({"kind": "thing", "name": "n", "count": True}, "count", "int_type"),
    ({"kind": "thing", "name": "n", "pass": "true"}, "pass", "bool_type"),
    ({"kind": "thing", "name": "n", "colour": "red"}, "colour", "extra_forbidden"),
    ({"kind": "thing"}, "name", "missing"),
    ({"kind": "thing", "name": ""}, "name", "string_too_short"),
    ({"kind": "thing", "name": "n" * 21}, "name", "string_too_long"),
    ({"kind": "thing", "name": "n", "count": -1}, "count", "greater_than_equal"),
    ({"kind": "thing", "name": "n", "tags": ["a"] * 4}, "tags", "too_long"),
    ({"kind": "other", "name": "n"}, "kind", "literal_error"),
    ({"kind": "thing", "name": "n", "schema_version": 1.0}, "schema_version", "int_type"),
    ({"kind": "thing", "name": "n", "schema_version": 2}, "", "value_error"),
])
def test_a_shape_error_is_a_violation_with_path_and_code(toys, payload, path, code):
    error = refused(toys, "thing", payload)
    assert error.stage == "shape" and error.family == "thing"
    assert (path, code) in facts(error)


def test_every_violation_is_reported_not_only_the_first(toys):
    error = refused(toys, "thing", {"kind": "thing", "name": "", "count": "x", "colour": 1})
    assert sorted(facts(error)) == [("colour", "extra_forbidden"), ("count", "int_type"), ("name", "string_too_short")]
    assert all(isinstance(v, Violation) for v in error.violations)


def test_a_union_tag_comes_first_in_the_path(toys):
    assert facts(refused(toys, "pair", {"kind": "alpha", "size": "3"})) == [("alpha.size", "int_type")]
    assert facts(refused(toys, "pair", {"kind": "delta"})) == [("", "union_tag_invalid")]
    assert facts(refused(toys, "pair", {})) == [("", "union_tag_not_found")]


def test_gate_error_names_the_stage_the_family_and_the_first_violation(toys):
    error = refused(toys, "thing", {"kind": "thing", "name": "", "count": "x"})
    text = str(error)
    assert text.startswith("shape refused a 'thing' payload: ") and "(+1 more)" in text
    assert f"{error.violations[0].path}: {error.violations[0].message}" in text
    single = GateError("f", "size", [violation("", "x", "too big")])
    assert str(single) == "size refused a 'f' payload: <root>: too big"
    assert str(GateError("f", "cross", [])) == "cross refused a 'f' payload: no detail"


def test_gate_error_keeps_its_own_list_of_violations():
    given = (violation("a", "x", "m"), violation("b", "y", "n"))
    error = GateError("f", "shape", given)
    assert error.violations == list(given) and isinstance(error.violations, list)
    as_list = [violation("a", "x", "m")]
    error = GateError("f", "shape", as_list)
    as_list.append(violation("b", "y", "n"))
    assert len(error.violations) == 1
    assert (error.family, error.stage) == ("f", "shape")


def test_the_message_of_a_validator_error_has_no_pydantic_prefix():
    class Rule(Record):
        FAMILY = "rule"
        kind: Literal["rule"] = "rule"
        a: int = 1

        @field_validator("a")
        @classmethod
        def _positive(cls, v):
            if v < 1:
                raise ValueError("a must be positive")
            return v

    reg = ModelRegistry()
    reg.register(Rule)
    error = refused(Gate(reg), "rule", {"a": 0})
    assert [(v.path, v.code, v.message) for v in error.violations] == [("a", "value_error", "a must be positive")]


@pytest.mark.parametrize("payload, code", [
    ([1, 2], "payload_type"), (None, "payload_type"), (5, "payload_type"), (1.5, "payload_type"),
    ({"a"}, "payload_type"), (("a",), "payload_type"), (object(), "payload_type"),
    (PlainModel(), "payload_type"),
])
def test_a_payload_that_is_not_a_model_dict_text_or_bytes_is_refused(toys, payload, code):
    error = refused(toys, "thing", payload)
    assert error.stage == "shape" and facts(error) == [("", code)]


@pytest.mark.parametrize("payload, code", [
    (b"\xff\xfe\x00", "bad_unicode"),
    ({"kind": "thing", "name": "\ud800"}, "bad_unicode"),
    ({"kind": "thing", "name": "n", "tags": {"a", "b"}}, "not_json"),
    ({"kind": "thing", "name": "n", "note": float("nan")}, "not_json"),
    ({"kind": "thing", "name": "n", "note": object()}, "not_json"),
])
def test_a_payload_that_is_not_json_is_a_shape_error(toys, payload, code):
    error = refused(toys, "thing", payload)
    assert error.stage == "shape" and facts(error) == [("", code)]


@pytest.mark.parametrize("text", ["", "not json", "{", '{"kind": "thing", "name": }', "{'kind': 'thing'}"])
def test_text_that_is_not_json_is_a_json_invalid_violation(toys, text):
    error = refused(toys, "thing", text)
    assert error.stage == "shape" and facts(error) == [("", "json_invalid")]


def test_json_that_is_not_an_object_is_refused(toys):
    for text in ("[]", "[1]", '"thing"', "5", "null", "true", "NaN"):
        error = refused(toys, "thing", text)
        assert error.stage == "shape" and facts(error)[0][1] in ("model_type", "dict_type"), (text, facts(error))


def test_a_deeply_nested_dict_is_refused_not_crashed(toys):
    deep: dict = {}
    node = deep
    for _ in range(5000):
        node["x"] = {}
        node = node["x"]
    error = refused(toys, "thing", {"kind": "thing", "name": "n", "note": deep})
    assert error.stage == "shape" and facts(error) == [("", "too_deep")]
    text_error = refused(toys, "thing", '{"kind":"thing","name":"n","note":' + "[" * 100_000 + "]" * 100_000 + "}")
    assert text_error.stage == "shape"


def test_a_recursion_error_inside_validation_is_a_shape_error_too(toys, monkeypatch):
    def boom(text):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(toys.registry.adapter("thing"), "validate_json", boom)
    error = refused(toys, "thing", GOOD)
    assert error.stage == "shape" and facts(error) == [("", "too_deep")]


def test_a_flood_of_violations_is_cut_to_fifty_and_counted(toys):
    error = refused(toys, "thing", {"kind": "thing", "name": "n", **{f"extra{i}": i for i in range(200)}})
    assert len(error.violations) == 51 and error.violations[-1].code == "more_errors"
    assert "150 more" in error.violations[-1].message


# ---- a dict payload: any Mapping is one, and nothing is quietly changed on the way to JSON -------------------------------

class Bag(Value):
    data: dict[str, int] = {}
    tags: list[str] = []
    inner: Optional[dict[str, list[str]]] = None


@pytest.fixture
def bag_gate():
    reg = ModelRegistry()
    reg.register_payload("bag", 1, Bag)
    return Gate(reg)


class ReadOnlyMapping(Mapping):
    """A Mapping that is not a dict and not a dict subclass."""

    def __init__(self, items):
        self._items = dict(items)

    def __getitem__(self, key):
        return self._items[key]

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


PLAIN_BAG = {"data": {"a": 1, "b": 2}, "tags": ["x", "y"], "inner": {"k": ["v"]}}
MAPPING_MAKERS = {
    "MappingProxyType": MappingProxyType,
    "UserDict": collections.UserDict,
    "ChainMap": lambda m: collections.ChainMap(dict(m)),
    "OrderedDict": collections.OrderedDict,
    "defaultdict": lambda m: collections.defaultdict(list, m),
    "a Mapping of its own": ReadOnlyMapping,
}


@pytest.mark.parametrize("make", list(MAPPING_MAKERS.values()), ids=list(MAPPING_MAKERS))
def test_any_kind_of_mapping_is_a_dict_payload_and_gives_the_checked_a_dict_gives(bag_gate, make):
    # Review round 1: only dict and dict subclasses were accepted (the JSON default knew nothing else); the design takes a Mapping.
    expected = bag_gate.check("bag", PLAIN_BAG)
    checked = bag_gate.check("bag", make(PLAIN_BAG))
    assert (checked.json, checked.sha256, checked.model) == (expected.json, expected.sha256, expected.model)


@pytest.mark.parametrize("make", list(MAPPING_MAKERS.values()), ids=list(MAPPING_MAKERS))
def test_mappings_nested_in_a_payload_are_accepted_too(bag_gate, make):
    nested = {"data": make({"a": 1}), "tags": ["x"], "inner": make({"k": ["v"]})}
    assert bag_gate.check("bag", nested).json == bag_gate.check("bag", {"data": {"a": 1}, "tags": ["x"], "inner": {"k": ["v"]}}).json


def test_a_model_inside_a_dict_payload_is_dumped_like_the_model_itself(toys):
    inside = toys.gate.check("doc", {"title": "t", "items": [toys.Item(n=1), {"n": 2}]})
    assert [item.n for item in inside.model.items] == [1, 2] and inside.model.items[0].label == "x"


def test_a_str_subclass_key_is_a_string_key(bag_gate):
    class Key(str):
        pass

    class Name(str, enum.Enum):
        A = "a"

    assert bag_gate.check("bag", {"data": {Key("k"): 1, Name.A: 2}}).model.data == {"k": 1, "a": 2}


@pytest.mark.parametrize("payload, path, word", [
    ({"tags": ("a", "b")}, "tags", "tuple"),
    ({"tags": ["a", ("b",)]}, "tags.1", "tuple"),
    ({"inner": {"k": ("v",)}}, "inner.k", "tuple"),
    ({"inner": {"k": [("v",)]}}, "inner.k.0", "tuple"),
    ({"tags": collections.namedtuple("Pair", "a b")("a", "b")}, "tags", "tuple"),
    ({"data": MappingProxyType({"a": (1,)})}, "data.a", "tuple"),
    ({"data": {1: 10, "1": 20}}, "data", "int"),                       # the two keys would have collapsed into one
    ({"data": {1: 10}}, "data", "int"),
    ({"data": {True: 1}}, "data", "bool"),
    ({"data": {None: 1}}, "data", "NoneType"),
    ({"data": {1.5: 1}}, "data", "float"),
    ({"data": {("a", "b"): 1}}, "data", "tuple"),
    ({"inner": {"k": ["v"], 2: ["w"]}}, "inner", "int"),
    ({1: "x"}, "", "int"),
])
def test_what_json_does_not_have_is_refused_not_quietly_converted(bag_gate, payload, path, word):
    # Review round 1: json.dumps wrote a tuple as a list and every key as a string, so the gate accepted what strict
    # validation of the same dict refuses (rule 1, no coercion), and {1: 10, "1": 20} lost its first value.
    error = refused(bag_gate, "bag", payload)
    assert error.stage == "shape" and facts(error) == [(path, "not_json")]
    assert word in error.violations[0].message
    with pytest.raises(ValidationError):                                # the class itself refuses it, too
        Bag.model_validate(payload)


def test_the_refusal_says_what_to_send_instead(bag_gate):
    # The text goes to whoever built the payload (a store, or a model's reply): it names the fix, not only the fault.
    assert refused(bag_gate, "bag", {"tags": ("a",)}).violations[0].message == "a tuple is not a list: send a list"
    assert refused(bag_gate, "bag", {"data": {1: 1}}).violations[0].message == "object keys must be strings, found int 1"
    long_key = (1, "x" * 100)
    message = refused(bag_gate, "bag", {"data": {long_key: 1}}).violations[0].message
    assert message.startswith("object keys must be strings, found tuple (1, 'xxx") and message.endswith("…")


def test_the_gate_is_never_laxer_than_the_class_on_a_dict(bag_gate):
    for payload in ({"tags": ("a",)}, {"data": {1: 1}}, {"data": {"a": "1"}}, {"tags": [1]}, {"data": {"a": 1.5}}, {"extra": 1}):
        with pytest.raises(ValidationError):
            Bag.model_validate(payload)
        with pytest.raises(GateError):
            bag_gate.check("bag", payload)


def test_the_repro_of_the_review_round(bag_gate):
    assert bag_gate.check("bag", MappingProxyType({"tags": ["a"]})).model.tags == ["a"]
    with pytest.raises(GateError) as e:
        bag_gate.check("bag", {"data": {1: 10, "1": 20}, "tags": ("a", "b")})
    assert e.value.stage == "shape" and e.value.violations[0].code == "not_json"


def test_a_dict_that_contains_itself_is_refused_as_json_cannot_hold_it(bag_gate):
    loop: dict = {}
    loop["data"] = loop
    error = refused(bag_gate, "bag", loop)
    assert error.stage == "shape" and facts(error) == [("data", "not_json")]
    assert "contains itself" in error.violations[0].message
    through_a_list: dict = {"tags": []}
    through_a_list["tags"].append(through_a_list)
    assert facts(refused(bag_gate, "bag", through_a_list)) == [("tags.0", "not_json")]
    through_a_mapping: dict = {}
    through_a_mapping["data"] = MappingProxyType(through_a_mapping)
    assert facts(refused(bag_gate, "bag", through_a_mapping)) == [("data.data", "not_json")]


def test_the_same_container_twice_in_a_payload_is_not_a_cycle(bag_gate):
    shared = ["x"]
    checked = bag_gate.check("bag", {"tags": shared, "inner": {"a": shared, "b": shared}})
    assert checked.model.tags == ["x"] and checked.model.inner == {"a": ["x"], "b": ["x"]}


def test_a_path_in_the_message_is_cut_to_the_bound_of_a_violation(bag_gate):
    key = "k" * 300
    error = refused(bag_gate, "bag", {"inner": {key: {key: {1: 2}}}})
    [v] = error.violations
    assert len(v.path) == 500 and v.path.endswith("…") and v.code == "not_json"        # 607 characters, cut to the bound


def test_the_old_refusals_of_values_json_cannot_hold_keep_their_codes(bag_gate):
    assert facts(refused(bag_gate, "bag", {"tags": {"a"}})) == [("", "not_json")]
    assert facts(refused(bag_gate, "bag", {"data": {"a": float("nan")}})) == [("", "not_json")]
    assert facts(refused(bag_gate, "bag", {"tags": [object()]})) == [("", "not_json")]
    assert facts(refused(bag_gate, "bag", {"tags": [b"x"]})) == [("", "not_json")]


# ---- a model_construct instance cannot bypass the gate ------------------------------------------------------------------

def test_model_construct_cannot_bypass_validation(toys):
    for built in (toys.Thing.model_construct(name=123, count="x"),
                  toys.Thing.model_construct(name="n", tags="not a list"),
                  toys.Thing.model_construct(kind="wrong", name="n"),
                  toys.Thing.model_construct()):
        error = refused(toys, "thing", built)
        assert error.stage == "shape"
    assert sorted(facts(refused(toys, "thing", toys.Thing.model_construct(name=123, count="x")))) == [
        ("count", "int_type"), ("name", "string_type")]


def test_model_construct_inside_a_nested_model_is_found_too(toys):
    built = toys.Doc.model_construct(title="ok", items=[toys.Item(n=1), toys.Item.model_construct(n="bad")])
    assert facts(refused(toys, "doc", built)) == [("items.1.n", "int_type")]


def test_an_instance_built_with_model_construct_that_is_in_fact_valid_passes(toys):
    built = toys.Thing.model_construct(kind="thing", schema_version=1, name="n", count=0, tags=[], passed=False, note=None)
    assert toys.gate.check("thing", built).model == toys.Thing(name="n")


def test_a_model_of_another_class_is_refused(toys):
    assert refused(toys, "thing", toys.Alpha()).stage == "shape"
    assert refused(toys, "pair", toys.Thing(name="n")).stage == "shape"


def test_a_mutated_list_is_caught_because_frozen_is_shallow(toys):
    thing = toys.Thing(name="n", tags=["a"])
    thing.tags.extend(["b", "c", "d"])                                   # frozen blocks assignment, not this
    assert facts(refused(toys, "thing", thing)) == [("tags", "too_long")]


# ---- stage: round_trip ------------------------------------------------------------------------------------------------

def test_a_model_whose_dump_is_not_valid_input_fails_the_round_trip():
    class Shy(Record):
        FAMILY = "shy"
        kind: Literal["shy"] = "shy"
        text: str = ""

        @field_validator("text")
        @classmethod
        def _bang(cls, v):
            if v.endswith("!"):
                raise ValueError("no bangs on the way in")
            return v + "!"                                # the stored form can never be read back

    reg = ModelRegistry()
    reg.register(Shy)
    error = refused(Gate(reg), "shy", {"text": "hi"})
    assert error.stage == "round_trip" and facts(error) == [("text", "value_error")]


def test_a_model_that_reads_back_as_another_model_fails_the_round_trip():
    class Drift(Record):
        FAMILY = "drift"
        kind: Literal["drift"] = "drift"
        text: str = ""

        @field_validator("text")
        @classmethod
        def _grow(cls, v):
            return v + "+"                                # accepts its own output, but changes it every time

    reg = ModelRegistry()
    reg.register(Drift)
    error = refused(Gate(reg), "drift", {"text": "hi"})
    assert error.stage == "round_trip" and facts(error) == [("", "round_trip_mismatch")]


def test_a_stable_validator_round_trips():
    class Calm(Record):
        FAMILY = "calm"
        kind: Literal["calm"] = "calm"
        text: str = ""

        @field_validator("text")
        @classmethod
        def _lower(cls, v):
            return v.lower()

    reg = ModelRegistry()
    reg.register(Calm)
    assert Gate(reg).check("calm", {"text": "HI"}).model.text == "hi"


# ---- the upgrade chain: an older schema_version -----------------------------------------------------------------------

def evolving(steps: int = 2):
    reg = ModelRegistry()
    seen = []

    class V1(Record):
        FAMILY = "evolving"
        kind: Literal["e"] = "e"
        old: str = ""

    reg.register(V1)
    if steps >= 2:
        class V2(Record):
            FAMILY = "evolving"
            VERSION = 2
            kind: Literal["e"] = "e"
            schema_version: int = 2
            mid: str = ""

        reg.register(V2)

        @reg.upgrade("evolving", 1)
        def one_to_two(payload):
            seen.append(("1>2", dict(payload)))
            return {"kind": payload["kind"], "mid": payload["old"].upper()}
    if steps >= 3:
        class V3(Record):
            FAMILY = "evolving"
            VERSION = 3
            kind: Literal["e"] = "e"
            schema_version: int = 3
            new: str = ""

        reg.register(V3)

        @reg.upgrade("evolving", 2)
        def two_to_three(payload):
            seen.append(("2>3", dict(payload)))
            return {"kind": payload["kind"], "new": payload["mid"] + "!"}
    return SimpleNamespace(registry=reg, gate=Gate(reg), seen=seen)


def test_an_older_payload_is_upgraded_to_the_latest_version():
    world = evolving(2)
    checked = world.gate.check("evolving", {"kind": "e", "schema_version": 1, "old": "x"})
    assert checked.version == 2 and checked.model.mid == "X" and '"schema_version":2' in checked.json
    assert world.seen == [("1>2", {"kind": "e", "schema_version": 1, "old": "x"})]


def test_the_chain_runs_every_step_and_works_from_any_older_version():
    world = evolving(3)
    from_one = world.gate.check("evolving", '{"kind":"e","schema_version":1,"old":"x"}')
    assert from_one.version == 3 and from_one.model.new == "X!" and [s for s, _ in world.seen] == ["1>2", "2>3"]
    world.seen.clear()
    from_two = world.gate.check("evolving", {"kind": "e", "schema_version": 2, "mid": "M"})
    assert from_two.model.new == "M!" and [s for s, _ in world.seen] == ["2>3"]
    world.seen.clear()
    current = world.gate.check("evolving", {"kind": "e", "schema_version": 3, "new": "n"})
    assert current.model.new == "n" and world.seen == []


def test_a_payload_without_a_schema_version_is_read_as_the_latest():
    world = evolving(2)
    assert world.gate.check("evolving", {"kind": "e", "mid": "m"}).version == 2 and world.seen == []


def test_the_callers_dict_is_not_changed_by_an_upgrade():
    world = evolving(2)
    payload = {"kind": "e", "schema_version": 1, "old": "x"}
    world.gate.check("evolving", payload)
    assert payload == {"kind": "e", "schema_version": 1, "old": "x"}


def test_an_old_class_can_still_be_asked_for_by_version():
    world = evolving(2)
    checked = world.gate.check("evolving", {"kind": "e", "schema_version": 1, "old": "x"}, version=1)
    assert checked.version == 1 and checked.model.old == "x" and world.seen == []
    assert world.gate.check("evolving", {"kind": "e", "schema_version": 2, "mid": "m"}, version=2).version == 2


def test_a_payload_older_than_any_upgrade_is_refused_with_schema_version():
    world = evolving(2)
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": 0, "old": "x"})
    assert error.stage == "shape" and facts(error) == [("schema_version", "schema_version")]
    assert "version 0" in error.violations[0].message and "latest is 2" in error.violations[0].message


def test_version_zero_with_no_upgrade_at_all_is_refused():
    world = evolving(1)
    for payload in ({"kind": "e", "schema_version": 0}, {"kind": "e", "schema_version": -3}):
        error = refused(world.gate, "evolving", payload)
        assert error.stage == "shape" and facts(error) == [("schema_version", "schema_version")]


def test_a_gap_in_the_chain_is_refused():
    world = evolving(3)
    del world.registry._families["evolving"].upgrades[1]
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": 1, "old": "x"})
    assert facts(error) == [("schema_version", "schema_version")]
    assert world.gate.check("evolving", {"kind": "e", "schema_version": 2, "mid": "m"}).version == 3


def test_a_payload_newer_than_the_class_is_a_value_error_not_an_upgrade():
    world = evolving(1)
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": 2})
    assert error.stage == "shape" and facts(error) == [("", "value_error")]
    assert "schema_version is 2, this class is version 1" in error.violations[0].message


@pytest.mark.parametrize("value", ["1", 1.0, True, None, [1]])
def test_a_malformed_schema_version_is_left_to_the_strict_check(value):
    world = evolving(2)
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": value})
    assert error.stage == "shape" and facts(error)[0][0] == "schema_version" and facts(error)[0][1] != "schema_version"
    assert world.seen == []


def test_an_upgrade_that_cannot_read_the_old_data_is_a_shape_error():
    world = evolving(2)
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": 1})          # no "old": the upgrade raises KeyError
    assert error.stage == "shape" and facts(error) == [("schema_version", "upgrade_failed")]
    assert "KeyError" in error.violations[0].message


def test_a_bug_inside_an_upgrade_is_not_swallowed():
    world = evolving(2)

    @world.registry.upgrade("evolving", 0)
    def broken(payload):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError, match="bug"):
        world.gate.check("evolving", {"kind": "e", "schema_version": 0})


def test_an_upgraded_payload_is_validated_like_any_other():
    world = evolving(2)
    world.registry._families["evolving"].upgrades[1] = lambda payload: {"kind": "e", "mid": 5}
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": 1})
    assert error.stage == "shape" and facts(error) == [("mid", "string_type")]


def test_an_upgrade_that_makes_the_payload_too_big_is_refused_as_size():
    world = evolving(2)
    world.registry._families["evolving"].upgrades[1] = lambda payload: {"kind": "e", "mid": "x" * MAX_PAYLOAD_BYTES}
    error = refused(world.gate, "evolving", {"kind": "e", "schema_version": 1})
    assert error.stage == "size" and facts(error) == [("", "payload_too_large")]


def test_a_bad_return_from_an_upgrade_is_a_programming_error():
    world = evolving(2)
    world.registry._families["evolving"].upgrades[1] = lambda payload: "oops"
    with pytest.raises(RegistryError) as e:
        world.gate.check("evolving", {"kind": "e", "schema_version": 1})
    assert e.value.code == "bad_upgrade"


# ---- stage: cross ---------------------------------------------------------------------------------------------------------

class Store:
    """A GateContext over a dict: (family, id) -> model."""

    def __init__(self, **items):
        self.items = {tuple(k.split("/")): v for k, v in items.items()}
        self.asked = []

    def get(self, family, id):
        self.asked.append((family, id))
        return self.items.get((family, id))


def no_dupe_rule(name="thing.unique_name", family="thing", kind=None, taken="taken"):
    @cross_rule(name, family, kind)
    def rule(model, ctx):
        return [violation("name", "name_taken", f"{model.name} is taken")] if ctx.get("thing", model.name) else []
    return rule


def test_a_cross_rule_that_fails_refuses_at_stage_cross(toys):
    gate = Gate(toys.registry, [no_dupe_rule()])
    store = Store(**{"thing/n": toys.Thing(name="n")})
    error = refused(gate, "thing", GOOD, ctx=store)
    assert error.stage == "cross" and facts(error) == [("name", "name_taken")]
    assert gate.check("thing", {**GOOD, "name": "fresh"}, ctx=store).model.name == "fresh"


def test_cross_rules_run_only_when_a_context_is_given(toys):
    called = []

    @cross_rule("thing.spy", "thing")
    def spy(model, ctx):
        called.append(model)
        return [violation("", "always", "always fails")]

    gate = Gate(toys.registry, [spy])
    assert gate.check("thing", GOOD).model.name == "n" and called == []
    assert refused(gate, "thing", GOOD, ctx=Store()).stage == "cross" and len(called) == 1


def test_the_rule_gets_the_validated_model_and_the_context(toys):
    got = []

    @cross_rule("thing.spy", "thing")
    def spy(model, ctx):
        got.append((model, ctx))
        return []

    store = Store()
    checked = Gate(toys.registry, [spy]).check("thing", {"name": " padded "}, ctx=store)
    assert got == [(checked.model, store)] and got[0][0].name == "padded"


def test_rules_apply_by_family_and_by_kind(toys):
    ran = []

    def make(name, family, kind):
        @cross_rule(name, family, kind)
        def rule(model, ctx):
            ran.append(name)
            return []
        return rule

    gate = Gate(toys.registry, [make("thing.all", "thing", None), make("pair.alpha", "pair", "alpha"),
                                make("pair.beta", "pair", "beta"), make("pair.gamma", "pair", "gamma"),
                                make("pair.all", "pair", None), make("doc.all", "doc", None), make("ghost.all", "ghost", None)])
    store = Store()
    gate.check("thing", GOOD, ctx=store)
    assert ran == ["thing.all"]
    ran.clear()
    gate.check("pair", {"kind": "gamma"}, ctx=store)
    assert ran == ["pair.gamma", "pair.all"]
    ran.clear()
    gate.check("doc", {"title": "t"}, ctx=store)
    assert ran == ["doc.all"]


def test_every_failing_rule_is_reported_together(toys):
    first = no_dupe_rule("thing.one")

    @cross_rule("thing.two", "thing")
    def second(model, ctx):
        return [violation("count", "too_many", "too many"), violation("tags", "too_few", "too few")]

    error = refused(Gate(toys.registry, [first, second]), "thing", GOOD, ctx=Store(**{"thing/n": object()}))
    assert error.stage == "cross" and facts(error) == [("name", "name_taken"), ("count", "too_many"), ("tags", "too_few")]


def test_shape_errors_come_before_cross_rules(toys):
    store = Store()
    gate = Gate(toys.registry, [no_dupe_rule()])
    assert refused(gate, "thing", {"kind": "thing"}, ctx=store).stage == "shape" and store.asked == []


def test_rules_are_not_given_to_the_gate_by_accident(toys):
    assert Gate(toys.registry).cross_rules == () and Gate(toys.registry).registry is toys.registry
    with pytest.raises(RegistryError) as e:
        Gate(toys.registry, [no_dupe_rule("same"), no_dupe_rule("same")])
    assert e.value.code == "duplicate"


def test_cross_rule_decorator_makes_a_rule_object():
    rule = no_dupe_rule("a.b", "a", "k")
    assert isinstance(rule, FunctionRule) and (rule.name, rule.family, rule.kind) == ("a.b", "a", "k")
    assert rule(SimpleNamespace(name="x"), Store(**{"thing/x": 1})) == [violation("name", "name_taken", "x is taken")]
    assert no_dupe_rule().kind is None


# ---- the shipped cross rules --------------------------------------------------------------------------------------------

def shipped_world():
    reg = ModelRegistry()

    class Atom(Record):
        FAMILY = "atom"
        kind: Literal["atom"] = "atom"
        state: Literal["open", "closed", "abandoned"] = "open"
        supersedes: Optional[str] = None

    class Edge(Record):
        FAMILY = "edge"
        kind: Literal["handoff", "contains"] = "handoff"
        from_id: str
        to_id: str

    class Node(Record):
        FAMILY = "node"
        kind: Literal["department", "division", "identity"] = "division"
        id: str
        department_id: Optional[str] = None

    class Department(Record):
        FAMILY = "department"
        kind: Literal["department"] = "department"
        id: str

    class ChartNode(Value):
        id: str
        kind: Literal["root", "department", "division"]

    class Chart(Record):
        FAMILY = "org_chart"
        kind: Literal["org_chart"] = "org_chart"
        nodes: Annotated[list[ChartNode], Field(max_length=10)] = []

    for cls in (Atom, Edge, Node, Department, Chart):
        reg.register(cls)
    return SimpleNamespace(gate=Gate(reg, SHIPPED_CROSS_RULES), Atom=Atom, Edge=Edge, Node=Node, Department=Department,
                           Chart=Chart, ChartNode=ChartNode)


def test_the_four_shipped_rules_and_the_global_gate():
    assert [r.name for r in SHIPPED_CROSS_RULES] == ["atom.supersedes_abandoned", "edge.endpoints_exist",
                                                     "node.department_exists", "department.in_chart"]
    assert [(r.family, r.kind) for r in SHIPPED_CROSS_RULES] == [("atom", None), ("edge", None), ("node", None), ("department", None)]
    assert GATE.registry is REGISTRY and GATE.cross_rules == SHIPPED_CROSS_RULES


def test_atom_supersedes_abandoned():
    w = shipped_world()
    store = Store(**{"atom/a-x-01": w.Atom(state="abandoned"), "atom/a-x-02": w.Atom(state="open"),
                     "atom/a-x-03": w.Atom(state="closed")})
    assert w.gate.check("atom", {"supersedes": "a-x-01"}, ctx=store).model.supersedes == "a-x-01"
    assert w.gate.check("atom", {}, ctx=store).model.supersedes is None
    for target in ("a-x-02", "a-x-03"):
        error = refused(w.gate, "atom", {"supersedes": target}, ctx=store)
        assert error.stage == "cross" and facts(error) == [("supersedes", "supersedes_not_abandoned")]
        assert target in error.violations[0].message
    assert facts(refused(w.gate, "atom", {"supersedes": "a-x-99"}, ctx=store)) == [("supersedes", "unknown_atom")]
    assert store.asked and all(f == "atom" for f, _ in store.asked)


def test_edge_endpoints_exist():
    w = shipped_world()
    store = Store(**{"node/a": w.Node(id="a"), "node/b": w.Node(id="b")})
    assert w.gate.check("edge", {"from_id": "a", "to_id": "b"}, ctx=store).kind == "handoff"
    assert w.gate.check("edge", {"kind": "contains", "from_id": "b", "to_id": "a"}, ctx=store)
    assert facts(refused(w.gate, "edge", {"from_id": "a", "to_id": "ghost"}, ctx=store)) == [("to_id", "unknown_node")]
    assert facts(refused(w.gate, "edge", {"from_id": "ghost", "to_id": "b"}, ctx=store)) == [("from_id", "unknown_node")]
    both = refused(w.gate, "edge", {"from_id": "x", "to_id": "y"}, ctx=store)
    assert both.stage == "cross" and facts(both) == [("from_id", "unknown_node"), ("to_id", "unknown_node")]


def test_node_department_exists():
    w = shipped_world()
    store = Store(**{"node/sales": w.Node(kind="department", id="sales"), "node/leads": w.Node(kind="division", id="leads")})
    assert w.gate.check("node", {"id": "x"}, ctx=store).model.department_id is None                       # names none
    assert w.gate.check("node", {"id": "x", "department_id": "sales"}, ctx=store)
    assert w.gate.check("node", {"kind": "department", "id": "newdept", "department_id": "newdept"}, ctx=store)   # itself: fine
    assert facts(refused(w.gate, "node", {"id": "x", "department_id": "ghost"}, ctx=store)) == [("department_id", "unknown_department")]
    error = refused(w.gate, "node", {"id": "x", "department_id": "leads"}, ctx=store)
    assert error.stage == "cross" and facts(error) == [("department_id", "not_a_department")] and "division" in error.violations[0].message


def test_department_in_chart():
    w = shipped_world()
    chart = w.Chart(nodes=[w.ChartNode(id="root", kind="root"), w.ChartNode(id="sales", kind="department"),
                           w.ChartNode(id="leads", kind="division")])
    store = Store(**{"org_chart/chart": chart})
    assert w.gate.check("department", {"id": "sales"}, ctx=store).model.id == "sales"
    assert facts(refused(w.gate, "department", {"id": "ghost"}, ctx=store)) == [("id", "department_not_in_chart")]
    assert facts(refused(w.gate, "department", {"id": "leads"}, ctx=store)) == [("id", "department_not_in_chart")]    # a division is no department
    empty = refused(w.gate, "department", {"id": "sales"}, ctx=Store())
    assert empty.stage == "cross" and facts(empty) == [("id", "no_chart")]
    assert store.asked == [("org_chart", "chart")] * 3


def test_shipped_rules_do_nothing_without_a_context():
    w = shipped_world()
    assert w.gate.check("department", {"id": "anything"}).model.id == "anything"
    assert w.gate.check("edge", {"from_id": "a", "to_id": "b"}).model.from_id == "a"
