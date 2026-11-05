"""The schema the model sees when it proposes a chart change (library design 3.5 and section 14; S2-models-04):
`transport_schema(ChartChangeRequest)` is draft-07, sends the ops union as anyOf of five closed objects, holds no
free-key dict, and what it accepts reads back through ReplyParser. The live check that decides union against flat is
tests/library/test_lib_live_transport.py (L8); until it runs, CHART_OPS_TRANSPORT stays "union"."""
import json
from typing import Literal

import pytest
from pydantic import ValidationError

from sutra_app.library.base import Value
from sutra_app.library.org_chart import (
    CHART_OPS_TRANSPORT, AddOp, ChartChangeRequest, ChildMove, MergeOp, MoveOp, NewNode, RenameOp, SplitOp,
)
from sutra_app.library.registry import REGISTRY, RegistryError, is_transport_safe, transport_schema
from sutra_app.library.replies import ReplyInvalid, ReplyParser

SCHEMA = transport_schema(ChartChangeRequest)
DEFINITIONS = SCHEMA["definitions"]
OPS = ["add", "move", "rename", "merge", "split"]
PARSER = ReplyParser()


def definition(ref):
    assert ref.startswith("#/definitions/")
    return DEFINITIONS[ref[len("#/definitions/"):]]


def walk(node, path="#"):
    """Every dict of a schema with its json pointer."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}/{index}")


def keys_of(schema):
    return {key for _, node in walk(schema) for key in node}


def is_type(value, name):
    return {"string": isinstance(value, str), "object": isinstance(value, dict), "array": isinstance(value, list),
            "null": value is None, "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool)}[name]


def conforms(schema, value, root=None):
    """A checker for the small part of JSON Schema this transport uses: $ref, anyOf, enum, type (also a list), object
    properties with required and additionalProperties false, and items. Enough to say what a CLI would accept."""
    root = root or schema
    if "$ref" in schema:
        return conforms(definition(schema["$ref"]), value, root)
    if "anyOf" in schema:
        return any(conforms(member, value, root) for member in schema["anyOf"])
    if "enum" in schema and value not in schema["enum"]:
        return False
    kinds = schema.get("type", [])
    kinds = kinds if isinstance(kinds, list) else [kinds]
    if kinds and not any(is_type(value, kind) for kind in kinds):
        return False
    if isinstance(value, dict) and "properties" in schema:
        properties = schema["properties"]
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        if set(schema.get("required", [])) - set(value):
            return False
        return all(conforms(properties[key], item, root) for key, item in value.items() if key in properties)
    if isinstance(value, list) and "items" in schema:
        return all(conforms(schema["items"], item, root) for item in value)
    return True


PART = {"ref": "$a", "kind": "division", "name": "Alpha", "purpose": "", "parent": "sales"}
SAMPLES = {
    "add": {"op": "add", "node": {"ref": "$support", "kind": "department", "name": "Support", "purpose": "", "parent": "root"}},
    "move": {"op": "move", "node": "leads", "to_parent": "web"},
    "rename": {"op": "rename", "node": "sales", "name": "Revenue", "purpose": None},
    "merge": {"op": "merge", "into": "quotes", "sources": ["leads"]},
    "split": {"op": "split", "node": "leads", "parts": [PART], "moves": [{"child": "inbound", "to": "$a"}]},
}


def reply(*ops, reason="merge leads into quotes", reuses=("sales",)):
    return {"reason": reason, "reuses": list(reuses), "ops": list(ops)}


# ---- the shape of the schema --------------------------------------------------------------------------------------

def test_the_schema_is_draft_07_with_no_oneof_discriminator_defs_or_const():
    assert SCHEMA["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert keys_of(SCHEMA).isdisjoint({"oneOf", "discriminator", "$defs", "const", "allOf", "default", "title", "pattern",
                                       "minLength", "maxLength", "minItems", "maxItems", "format"})
    assert is_transport_safe(SCHEMA) == []


def test_the_ops_are_anyof_of_five_closed_objects_each_with_a_one_value_op_enum():
    items = SCHEMA["properties"]["ops"]["items"]
    assert set(items) == {"anyOf"} and len(items["anyOf"]) == 5
    members = [definition(member["$ref"]) for member in items["anyOf"]]
    assert [member["properties"]["op"]["enum"] for member in members] == [[name] for name in OPS]
    for member in members:
        assert member["type"] == "object" and member["additionalProperties"] is False
        assert member["required"] == list(member["properties"])


def test_every_object_is_closed_and_has_every_property_required():
    objects = [(path, node) for path, node in walk(SCHEMA) if node.get("type") == "object"]
    assert len(objects) == 1 + len(DEFINITIONS) == 8                       # the request, five ops, NewNode, ChildMove
    for path, node in objects:
        assert node["additionalProperties"] is False, path
        assert node["required"] == list(node["properties"]), path


def test_there_is_no_free_key_dict_anywhere():
    for path, node in walk(SCHEMA):
        assert node.get("additionalProperties", False) is False, path
        if node.get("type") == "object":
            assert "properties" in node, path
    split = DEFINITIONS["SplitOp"]["properties"]
    assert split["moves"]["type"] == "array" and definition(split["moves"]["items"]["$ref"]) is DEFINITIONS["ChildMove"]
    assert list(DEFINITIONS["ChildMove"]["properties"]) == ["child", "to"]


def test_the_schema_is_under_four_kilobytes():
    assert len(json.dumps(SCHEMA)) < 4096
    assert len(json.dumps(SCHEMA, sort_keys=True, separators=(",", ":"))) < 4096


def test_what_the_model_may_leave_unchanged_is_nullable_not_optional():
    rename = DEFINITIONS["RenameOp"]["properties"]
    assert rename["name"]["type"] == ["string", "null"] and rename["purpose"]["type"] == ["string", "null"]
    assert "name" in DEFINITIONS["RenameOp"]["required"] and "purpose" in DEFINITIONS["RenameOp"]["required"]
    assert set(SCHEMA["required"]) == {"reason", "reuses", "ops"}


def test_the_class_sentences_and_field_hints_are_what_the_model_reads():
    assert SCHEMA["description"].startswith("A change to the org chart")
    for name, text in (("AddOp", "Add a department"), ("MoveOp", "Move a division"), ("RenameOp", "Change the name"),
                       ("MergeOp", "Merge divisions"), ("SplitOp", "Split a division")):
        assert DEFINITIONS[name]["description"].startswith(text)
    assert "never an id" in DEFINITIONS["NewNode"]["properties"]["ref"]["description"]
    assert "$ref" in DEFINITIONS["NewNode"]["properties"]["parent"]["description"]


def test_each_model_facing_class_has_a_safe_transport_schema_on_its_own():
    for cls in (NewNode, AddOp, MoveOp, RenameOp, MergeOp, ChildMove, SplitOp, ChartChangeRequest):
        assert is_transport_safe(transport_schema(cls)) == [], cls


def test_the_registry_serves_the_same_schema_for_the_request():
    assert REGISTRY.transport_schema("chart_change_request") == SCHEMA
    assert transport_schema(ChartChangeRequest) == SCHEMA                      # and it does not change from call to call
    assert CHART_OPS_TRANSPORT == "union"                                      # until the live check says "flat"


def test_a_free_key_dict_is_refused_which_is_why_split_moves_are_a_list_of_pairs():
    class OldSplit(Value):                                                     # the shape S2-models-04 replaced
        op: Literal["split"] = "split"
        node: str
        move_children: dict[str, str]

    with pytest.raises(RegistryError) as info:
        transport_schema(OldSplit)
    assert info.value.code == "transport_dict" and "list of pairs" in info.value.detail

    class Holder(Value):
        inner: OldSplit

    with pytest.raises(RegistryError) as nested:
        transport_schema(Holder)
    assert nested.value.code == "transport_dict"


# ---- the schema against the class ---------------------------------------------------------------------------------

@pytest.mark.parametrize("name", OPS)
def test_a_reply_the_schema_accepts_is_a_valid_request_for_every_op(name):
    data = reply(SAMPLES[name])
    assert conforms(SCHEMA, data)
    parsed = PARSER.parse("chart_change_request", json.dumps(data))
    assert isinstance(parsed.model, ChartChangeRequest) and parsed.dropped_keys == [] and parsed.normalised == []
    assert parsed.model.ops[0].op == name


def test_a_reply_with_all_five_ops_and_no_reuse_validates():
    data = reply(*SAMPLES.values(), reuses=())
    assert conforms(SCHEMA, data) and len(PARSER.parse("chart_change_request", json.dumps(data)).model.ops) == 5


def test_what_the_schema_refuses_the_class_refuses_too():
    bad_ops = [
        {"op": "delete", "node": "leads"},                                       # no such op
        {"op": "move", "node": "leads"},                                         # a missing key
        {**SAMPLES["move"], "colour": "red"},                                    # an extra key
        {"op": "merge", "into": "quotes", "sources": "leads"},                   # the wrong type
        {**SAMPLES["add"], "node": {**SAMPLES["add"]["node"], "kind": "root"}},  # a value outside the enum
    ]
    for op in bad_ops:
        data = reply(op)
        assert not conforms(SCHEMA, data), op
        with pytest.raises(ValidationError):
            ChartChangeRequest.model_validate(data)
    assert not conforms(SCHEMA, {"reason": "r", "ops": []})                      # reuses is required in the transport
    assert not conforms(SCHEMA, {**reply(), "extra": 1})


def test_the_schema_is_looser_than_the_class_and_the_parser_has_the_last_word():
    nothing_to_rename = reply({"op": "rename", "node": "sales", "name": None, "purpose": None})
    assert conforms(SCHEMA, nothing_to_rename)                                   # JSON Schema cannot say "at least one"
    with pytest.raises(ReplyInvalid) as info:
        PARSER.parse("chart_change_request", json.dumps(nothing_to_rename))
    assert info.value.code == "shape"
    assert info.value.retry_text == "THE VALIDATOR REJECTED: ops.0.rename: a rename needs a new name, a new purpose or both"


def test_a_models_reply_is_read_tolerantly_and_then_checked_strictly():
    text = ('Here is the change:\n```json\n'
            '{"reason": "merge leads into quotes and add support", "reuses": ["sales"], "note": "x", "ops": ['
            '{"op": "MERGE", "into": "quotes", "sources": ["leads"], "why": "same team"},'
            '{"op": "add", "node": {"ref": "$support", "kind": "Department", "name": "Support", "purpose": "",'
            ' "parent": "root", "colour": "red"}}]}\n```')
    parsed = PARSER.parse("chart_change_request", text)
    assert [type(op).__name__ for op in parsed.model.ops] == ["MergeOp", "AddOp"]
    assert parsed.model.ops[1].node.kind == "department"
    assert parsed.dropped_keys == ["note", "ops.0.why", "ops.1.node.colour"]
    assert parsed.normalised == ["ops.0.op", "ops.1.node.kind"]


def test_a_bad_reply_gets_retry_text_that_names_the_place():
    def retry(data):
        with pytest.raises(ReplyInvalid) as info:
            PARSER.parse("chart_change_request", json.dumps(data))
        assert info.value.code == "shape"
        return info.value.retry_text

    assert retry(reply({"op": "teleport", "node": "leads"})).startswith(
        "THE VALIDATOR REJECTED: ops.0: Input tag 'teleport' found using 'op' does not match any of the expected tags: 'add'")
    assert retry(reply({"op": "move", "node": "leads", "to_parent": "$x"})) == (
        "THE VALIDATOR REJECTED: ops.0.to_parent: ref $x is used before it is added")
    assert retry(reply({"op": "move", "node": "leads"})) == "THE VALIDATOR REJECTED: ops.0.move.to_parent: Field required"
    assert retry({"reason": "r", "reuses": "sales", "ops": []}) == "THE VALIDATOR REJECTED: reuses: Input should be a valid list"
