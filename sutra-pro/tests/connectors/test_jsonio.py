"""CN-1: reading a model's JSON reply (connectors design 3.6). The verbatim J2 cases of extract_json / close_json are tested
once, in tests/library/test_lib_replies.py; here are the object identities and the connector's own parse, validate,
repair prompt and prune_nulls."""
import copy
from typing import Optional

import pytest
from pydantic import BaseModel, create_model

from sutra_app.connectors import jsonio, schema
from sutra_app.connectors.errors import InvalidJsonError
from sutra_app.engine import llm
from sutra_app.library import replies


class Item(BaseModel):
    name: str
    qty: int = 1


class Order(BaseModel):
    id: str
    note: str = "none"
    maybe: Optional[str] = None
    must_say: Optional[str]                  # required, but null is allowed
    first: Item
    items: list[Item] = []
    extra: Optional[Item] = None


# ---- the library's helpers, not copies -------------------------------------------------------------------------------

def test_extract_json_and_close_json_are_the_librarys_objects():
    assert jsonio.extract_json is replies.extract_json
    assert jsonio.close_json is replies.close_json
    assert jsonio.extract_json is llm.extract_json         # the engine re-exports the same one (S1-contracts-18)


# ---- parse -----------------------------------------------------------------------------------------------------------

def test_parse_reply_reads_a_fence_a_slice_and_a_cut_off_reply():
    assert jsonio.parse_reply('Here:\n```json\n{"a": 1}\n```\nbye') == {"a": 1}
    assert jsonio.parse_reply('sure! {"a": {"b": 2}} done') == {"a": {"b": 2}}
    assert jsonio.parse_reply('{"a": "cut off') == {"a": "cut off"}
    assert jsonio.parse_reply('{"items": [1, 2') == {"items": [1, 2]}


@pytest.mark.parametrize("text", ["no object here", "", "[1, 2]", "{broken", None])
def test_parse_reply_without_an_object_is_invalid_json(text):
    with pytest.raises(InvalidJsonError, match="reply: "):
        jsonio.parse_reply(text)


def test_parse_reply_refuses_a_non_object(monkeypatch):
    monkeypatch.setattr(jsonio, "extract_json", lambda text: [1])
    with pytest.raises(InvalidJsonError, match="not an object"):
        jsonio.parse_reply("x")


# ---- validate --------------------------------------------------------------------------------------------------------

def test_validate_with_a_class_returns_the_instance():
    got = jsonio.validate_reply({"id": "o1", "must_say": None, "first": {"name": "n"}}, Order)
    assert isinstance(got, Order) and got.first.qty == 1


def test_validate_errors_are_pydantics_words_as_loc_and_message():
    with pytest.raises(InvalidJsonError) as e:
        jsonio.validate_reply({"id": 5, "first": {"qty": "x"}}, Order)
    text = str(e.value)
    assert "id: Input should be a valid string" in text and "must_say: Field required" in text
    assert "first.name: Field required" in text and "first.qty: Input should be a valid integer" in text
    assert "; " in text and e.value.code == "invalid_json"


def test_validate_errors_are_cut_at_500_characters():
    Wide = create_model("Wide", **{f"f{i}": (int, ...) for i in range(100)})
    with pytest.raises(InvalidJsonError) as e:
        jsonio.validate_reply({}, Wide)
    assert len(e.value.message) == jsonio.MAX_ERROR_DETAIL
    with pytest.raises(InvalidJsonError) as e2:
        jsonio.validate_reply({"a": 1}, {"type": "object", "required": [f"k{i}" for i in range(100)]})
    assert len(e2.value.message) == jsonio.MAX_ERROR_DETAIL


def test_validate_with_a_dict_schema_uses_minimal_validate_and_returns_the_value():
    sch = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    value = {"a": 1, "b": 2}
    assert jsonio.validate_reply(value, sch) is value
    with pytest.raises(InvalidJsonError, match="a: must be integer, got a string"):
        jsonio.validate_reply({"a": "x"}, sch)
    with pytest.raises(InvalidJsonError, match="a: is required"):
        jsonio.validate_reply({}, sch)


def test_validate_without_a_schema_is_a_passthrough_and_a_bad_schema_is_a_type_error():
    value = {"x": 1}
    assert jsonio.validate_reply(value, None) is value
    with pytest.raises(TypeError, match="schema must be"):
        jsonio.validate_reply(value, "nope")


def test_parse_and_validate_closes_a_cut_off_reply_before_validating():
    text = 'Sure: ```json\n{"id": "o1", "must_say": null, "first": {"name": "n"}, "items": [{"name": "a"}, {"name": "b"'
    got = jsonio.parse_and_validate(text, Order)
    assert [i.name for i in got.items] == ["a", "b"]
    assert jsonio.parse_and_validate('{"a": 1}') == {"a": 1}
    with pytest.raises(InvalidJsonError):
        jsonio.parse_and_validate("prose only", Order)


def test_format_errors_handles_nested_locations_and_other_exceptions():
    try:
        Order.model_validate({"id": "x", "must_say": None, "first": {"name": "n"}, "items": [{"qty": 1}]})
    except Exception as exc:
        assert jsonio.format_errors(exc) == "items.0.name: Field required"
    assert jsonio.format_errors(ValueError("first line\nsecond")) == "first line"
    assert jsonio.format_errors(ValueError("")) == "reply: not valid"

    class Root(BaseModel):
        pass

    try:
        Root.model_validate("not a dict")
    except Exception as exc:
        assert jsonio.format_errors(exc).startswith("reply: ")


# ---- repair prompt ---------------------------------------------------------------------------------------------------

def test_repair_prompt_has_the_prompt_the_errors_the_last_reply_and_the_instruction():
    p = jsonio.repair_prompt("ORIGINAL PROMPT", "id: Field required", '{"bad": 1}')
    assert p == ("ORIGINAL PROMPT\nYOUR LAST REPLY WAS REJECTED: id: Field required\n"
                 'YOUR LAST REPLY WAS:\n{"bad": 1}\nReply again with one JSON object only.')


def test_repair_prompt_caps_errors_at_1500_and_the_reply_at_3000():
    p = jsonio.repair_prompt("P", "e" * 5000, "r" * 9000)
    assert (jsonio.MAX_ERRORS_CHARS, jsonio.MAX_LAST_REPLY_CHARS) == (1500, 3000)
    assert "e" * 1500 in p and "e" * 1501 not in p
    assert "r" * 3000 in p and "r" * 3001 not in p
    assert p.startswith("P\n") and p.endswith("Reply again with one JSON object only.")


def test_repair_prompt_tolerates_none():
    assert "REJECTED: \n" in jsonio.repair_prompt("P", None, None)


# ---- prune_nulls -----------------------------------------------------------------------------------------------------

def test_without_a_schema_every_null_dict_value_goes_but_list_items_stay():
    value = {"a": None, "b": {"c": None, "d": 1}, "e": [None, {"f": None, "g": 2}], "h": 0, "i": False, "j": ""}
    assert jsonio.prune_nulls(value) == {"b": {"d": 1}, "e": [None, {"g": 2}], "h": 0, "i": False, "j": ""}


def test_with_a_class_only_nulls_of_optional_fields_go_so_defaults_apply():
    reply = {"id": "o1", "note": None, "maybe": None, "must_say": None, "first": {"name": "n", "qty": None},
             "items": [{"name": "a", "qty": None}], "extra": None}
    got = jsonio.prune_nulls(reply, Order)
    assert got == {"id": "o1", "must_say": None, "first": {"name": "n"}, "items": [{"name": "a"}]}
    order = Order.model_validate(got)
    assert (order.note, order.first.qty, order.items[0].qty) == ("none", 1, 1)       # the defaults were not defeated


def test_a_null_at_a_required_property_is_kept_so_validation_still_sees_it():
    got = jsonio.prune_nulls({"id": None, "must_say": None, "first": None}, Order)
    assert got == {"id": None, "must_say": None, "first": None}


def test_with_a_dict_schema_not_required_means_prunable():
    sch = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}, "b": {"type": "string"},
                                                                   "c": {"$ref": "#/definitions/C"},
                                                                   "list": {"type": "array", "items": {"$ref": "#/definitions/C"}}},
           "definitions": {"C": {"type": "object", "required": ["k"], "properties": {"k": {"type": "string"}, "m": {"type": "string"}}}}}
    reply = {"a": None, "b": None, "c": {"k": None, "m": None}, "list": [{"k": "x", "m": None}], "unknown": None}
    assert jsonio.prune_nulls(reply, sch) == {"a": None, "c": {"k": None}, "list": [{"k": "x"}], "unknown": None}


def test_a_union_is_followed_to_the_branch_that_has_the_keys():
    sch = {"type": "object", "properties": {"u": {"anyOf": [
        {"type": "object", "required": ["op"], "properties": {"op": {"enum": ["add"]}, "x": {"type": "string"}}},
        {"type": "object", "required": ["op"], "properties": {"op": {"enum": ["del"]}, "y": {"type": "string"}}}]}}}
    assert jsonio.prune_nulls({"u": {"op": "del", "y": None}}, sch) == {"u": {"op": "del"}}
    assert jsonio.prune_nulls({"u": {"op": "add", "x": None}}, sch) == {"u": {"op": "add"}}


def test_where_the_schema_cannot_be_followed_the_level_is_left_alone():
    sch = {"type": "object", "properties": {"gone": {"$ref": "#/definitions/Missing"}, "u": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                              "w": {"anyOf": [{"type": "object", "properties": {"only": {"type": "string"}}}]}}}
    reply = {"gone": {"a": None}, "u": None, "w": {"other": None}}
    got = jsonio.prune_nulls(reply, sch)
    assert got["gone"] == {"a": None} and got["w"] == {"other": None}


def test_prune_nulls_does_not_modify_its_input():
    reply = {"id": "o", "note": None, "must_say": None, "first": {"name": "n", "qty": None}}
    before = copy.deepcopy(reply)
    jsonio.prune_nulls(reply, Order)
    jsonio.prune_nulls(reply)
    assert reply == before


def test_prune_nulls_passes_scalars_and_lists_through():
    assert jsonio.prune_nulls(5) == 5 and jsonio.prune_nulls([None, 1], Order) == [None, 1]
    assert jsonio.prune_nulls("s", {"type": "string"}) == "s"


def test_the_codex_round_trip_strict_schema_nulls_then_prune_then_defaults():
    strict = schema.strict_schema(Order.model_json_schema())
    assert set(strict["required"]) == set(Order.model_fields)                 # the model had to answer every field
    codex_reply = {"id": "o1", "note": None, "maybe": None, "must_say": "hi", "first": {"name": "n", "qty": None}, "items": None, "extra": None}
    order = Order.model_validate(jsonio.prune_nulls(codex_reply, Order))
    assert (order.note, order.first.qty, order.items, order.extra, order.must_say) == ("none", 1, [], None, "hi")
