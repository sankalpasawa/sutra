"""Model replies (library design 3.5): `extract_json` and `close_json` (J2's own code, the one copy), and the
ReplyParser that reads a reply tolerantly and validates it strictly."""
import itertools
import json
import logging
import random
import re
import time
from typing import Annotated, Literal, Optional, Union

import pytest
from pydantic import Field, model_validator

from sutra_app.library import replies
from sutra_app.library.base import Record, Value
from sutra_app.library.gate import MAX_PAYLOAD_BYTES
from sutra_app.library.registry import ModelRegistry, RegistryError
from sutra_app.library.replies import (
    RETRY_PREFIX, ParsedReply, ReplyInvalid, ReplyParser, close_json, drop_unknown, extract_json, normalise_enums,
    retry_text_for, tolerate,
)
from sutra_app.library.types import violation


# ---- extract_json and close_json: the verbatim J2 cases (llm.py:268-295) -------------------------------------------------

def test_a_fenced_json_block_is_extracted():
    assert extract_json('Here you go:\n```json\n{"a": 1, "b": {"c": [1, 2]}}\n```\nbye') == {"a": 1, "b": {"c": [1, 2]}}
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```json {"a": 1} ```') == {"a": 1}


def test_a_fence_wins_over_braces_elsewhere_in_the_text():
    assert extract_json('prose {"not": "this"} then ```json\n{"yes": 1}\n``` end') == {"yes": 1}


def test_the_first_of_two_fenced_blocks_is_the_one_read():
    text = 'one ```json\n{"a": 1}\n``` and another ```json\n{"b": 2}\n``` done'
    assert extract_json(text) == {"a": 1}


def test_a_multi_line_fenced_block_wins_over_a_brace_earlier_in_the_prose():
    text = 'I think {"not": "this"} but here is the answer:\n```json\n{\n  "yes": 1,\n  "deep": {\n    "x": [1, 2]\n  }\n}\n```\nend'
    assert extract_json(text) == {"yes": 1, "deep": {"x": [1, 2]}}


def test_without_a_fence_the_text_from_the_first_brace_to_the_last_is_used():
    assert extract_json('Sure! {"a": 1, "b": "x"} hope that helps') == {"a": 1, "b": "x"}
    assert extract_json('{"a": {"b": {"c": 1}}}') == {"a": {"b": {"c": 1}}}
    assert extract_json('```JSON\n{"a": 1}\n```') == {"a": 1}                 # an unrecognised fence tag: the brace slice works


def test_a_reply_cut_short_is_closed_and_read():
    assert extract_json('{"say": "@Priority hi", "workflows": [{"name": "A", "outputs": ["x"') == {
        "say": "@Priority hi", "workflows": [{"name": "A", "outputs": ["x"]}]}
    assert extract_json('{"say": "cut short in a str') == {"say": "cut short in a str"}
    assert extract_json('{"a": [1, 2,') == {"a": [1, 2]}
    assert extract_json('{"a": "q\\"uote') == {"a": 'q"uote'}
    assert extract_json('{"a": 1} ```') == {"a": 1}


def test_no_object_in_the_reply_raises_value_error():
    for text in ("no object here", "[1, 2]", "", "   "):
        with pytest.raises(ValueError, match="no JSON object in reply"):
            extract_json(text)


def test_what_cannot_be_closed_raises_a_json_error_which_is_a_value_error():
    for text in ('text {"a": {"b": 1}} more {not json}', '```json\n{"a": 1,}\n```', '{"a": }', "{'a': 1}"):
        with pytest.raises(ValueError) as e:
            extract_json(text)
        assert isinstance(e.value, json.JSONDecodeError)


def test_close_json_closes_the_open_string_and_brackets_in_order():
    assert close_json('{"a": [1, {"b": "x') == '{"a": [1, {"b": "x"}]}'
    assert close_json('{"a": "q\\"') == '{"a": "q\\""}'
    assert close_json('{"a": "esc\\\\') == '{"a": "esc\\\\"}'
    assert close_json('[1, [2') == '[1, [2]]'
    assert close_json('{"a": 1,') == '{"a": 1}'
    assert close_json('  {"a": [1,  ') == '  {"a": [1]}'
    assert close_json('"plain') == '"plain"'
    assert close_json('{"a": 1}') == '{"a": 1}'
    assert close_json('{"a": "}"') == '{"a": "}"}'                       # a brace inside a string is not a bracket
    assert close_json('') == ''
    assert close_json('{"a": "x\\\\", "b": [1') == '{"a": "x\\\\", "b": [1]}'     # an escaped backslash does not escape the quote
    assert close_json('{"a": "x\\", "b": [1') == '{"a": "x\\", "b": [1"}'         # an escaped quote does not end the string
    assert close_json(']}') == ']}' and close_json('1]') == '1]'        # a closer with nothing open is left alone


def test_there_is_one_copy_of_the_json_helpers():
    assert replies.extract_json is extract_json and replies.close_json is close_json
    assert extract_json.__module__ == close_json.__module__ == "sutra_app.library.replies"


# ---- extract_json is J2's, in linear time (review round 1: a reply is untrusted) -------------------------------------

def j2_extract_json(text):
    """J2's extract_json (llm.py:268-295) exactly as J2 wrote it, with its quadratic fence search: the oracle."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        raise ValueError("no JSON object in reply")
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return json.loads(close_json(text[start:]))


def outcome(fn, text):
    try:
        return "value", fn(text)
    except Exception as exc:              # the type and the message are part of the contract (callers catch ValueError)
        return "raised", type(exc).__name__, str(exc)


def seconds(fn, *args):
    start = time.perf_counter()
    try:
        fn(*args)
    except (ValueError, ReplyInvalid):
        pass
    return time.perf_counter() - start


@pytest.mark.parametrize("text", [
    '} ```',                                                            # a closer and no opener
    '```json\n{"a": 1}',                                                # an opener and no closer
    '```json\n{"a": {"b": 1}}\n```',                                   # a brace inside the object
    'x } ``` y ```json {"a": 1} ``` z',                                 # a closer in the prose before the fence
    '```{"a": 1}``` ```{"b": 2}```',                                    # two blocks: the first one
    '```json\n{"a": 1}\n```\n```json\n{"b": 2}\n```',
    '````{"a": 1}````',                                                 # four backticks
    '```json{"a": 1}   \n\t ```',
    '```jsonx {"a": 1} ```',                                            # not the json tag: no fence match, the brace slice
    '```JSON\n{"a": 1}\n```',
    '```{"a": "} ``` in a string"} and then {"b": 1} ```',               # a closer inside a string: J2's match, kept
    '{"a": 1} ``` {"b": 2} ```',
    '```{ ```{ ```{ } ```',
    '```{',
    '```{}```',
    '```{}```{}```',
    '\u00a0```json\u2028{"a": 1}\u2028```',                            # unicode whitespace is whitespace to \\s
])
def test_the_linear_fence_search_gives_j2s_result_on_the_awkward_cases(text):
    assert outcome(extract_json, text) == outcome(j2_extract_json, text)


def test_the_linear_fence_search_gives_j2s_result_on_every_short_text_of_a_small_alphabet():
    alphabet = ["```", "{", "}", " ", "json", "x"]
    for length in range(6):
        for combo in itertools.product(alphabet, repeat=length):
            text = "".join(combo)
            assert outcome(extract_json, text) == outcome(j2_extract_json, text), text


def test_the_linear_fence_search_gives_j2s_result_on_random_texts():
    pieces = ["`", "```", "``", "{", "}", "{}", '{"a": 1}', '"', " ", "\n", "json", "JSON", "a", ",", "[", "]", "\\", "\t"]
    rnd = random.Random(20261104)
    for _ in range(20_000):
        text = "".join(rnd.choice(pieces) for _ in range(rnd.randint(0, 12)))
        assert outcome(extract_json, text) == outcome(j2_extract_json, text), text


@pytest.mark.parametrize("text", [
    "```{" * 20_000,                                  # J2's search took 3.4 s on 16000 of these
    "```json {" * 20_000,
    "}```" + "```{" * 20_000,                         # a closer, but before every opening fence
    ("```" + " " * 40) * 5_000 + "{",
    "```{}" * 20_000 + "```{",                       # many complete blocks: the first matches at once
    "{" * 50_000,
    "} " * 50_000,
])
def test_extract_json_stays_fast_on_texts_built_to_make_the_fence_search_quadratic(text):
    assert seconds(extract_json, text) < 1.0


# ---- toy classes ------------------------------------------------------------------------------------------------------

class Step(Value):
    id: str
    priority: Literal["must", "should", "could"] = "must"


class SiteGoal(Value):
    kind: Literal["site"] = "site"
    site_name: str = ""


class DocGoal(Value):
    kind: Literal["doc"] = "doc"
    product_name: str = ""


class Price(Record):
    FAMILY = "priority"
    kind: Literal["price"] = "price"
    decision: Literal["GRANT", "COUNTER", "REFUSE"]
    steps: list[Step] = []
    by_name: dict[str, Step] = {}
    mode: Optional[Literal["fast", "slow"]] = None
    modes: list[Literal["fast", "slow"]] = []
    goal: Union[SiteGoal, DocGoal, None] = None
    pass_: bool = Field(default=False, alias="pass")
    reason: str = ""

    @model_validator(mode="after")
    def _refuse_funds_nothing(self):
        if self.decision == "REFUSE" and self.steps:
            raise ValueError("REFUSE funds nothing: steps must be empty")
        return self


class Envelope(Record):
    FAMILY = "priority"
    kind: Literal["envelope_check"] = "envelope_check"
    decision: Literal["HOLD", "REQUEST_APPROVAL"]


class Add(Value):
    op: Literal["add"] = "add"
    name: str
    parent: Literal["root", "sales"] = "root"


class Move(Value):
    op: Literal["move"] = "move"
    to: str


class Request(Value):
    reason: str
    ops: list[Annotated[Union[Add, Move], Field(discriminator="op")]] = []
    one: Union[Add, Move, None] = Field(default=None, discriminator="op")


class PA(Value):
    kind: Literal["same"] = "same"
    op: Literal["a"] = "a"
    only_a: str = ""


class QB(Value):
    kind: Literal["same"] = "same"
    op: Literal["b"] = "b"
    only_b: str = ""


class ByField(Value):
    one: Union[PA, QB] = Field(discriminator="op")


class ByMeta(Value):
    many: list[Annotated[Union[PA, QB], Field(discriminator="op")]] = []


class P1(Value):
    mode: Literal["m"] = "m"
    kind: Literal["p"] = "p"
    only_p: str = ""


class Q1(Value):
    mode: Literal["m"] = "m"
    kind: Literal["q"] = "q"
    only_q: str = ""


class P2(Value):
    op: Literal["a"] = "a"
    only_a: str = ""


class Q2(Value):
    op: Literal["b"] = "b"
    only_b: str = ""


class LowTag(Value):
    op: Literal["ab"] = "ab"
    low: str = ""


class UpTag(Value):
    op: Literal["AB"] = "AB"
    up: str = ""


class Grant(Value):
    op: Literal["GRANT"] = "GRANT"
    a: str = ""


class Refuse(Value):
    op: Literal["REFUSE"] = "REFUSE"
    b: str = ""


class Leaf(Value):
    n: int = 0


class Holder(Value):
    maybe_leaf: Optional[Leaf] = None
    auto_kind: Union[P1, Q1] | None = None
    auto_op: Union[P2, Q2] | None = None
    case: Union[LowTag, UpTag] | None = None
    words: Union[Grant, Refuse] | None = None
    maybe_step: Optional[Step] = None


@pytest.fixture
def parser():
    reg = ModelRegistry()
    reg.register(Price)
    reg.register(Envelope)
    reg.register_payload("request", 1, Request)
    return ReplyParser(reg)


# ---- parse: reading the text --------------------------------------------------------------------------------------------

PRICE = {"kind": "price", "decision": "GRANT"}


def test_a_bare_json_reply(parser):
    parsed = parser.parse("priority", json.dumps(PRICE))
    assert isinstance(parsed, ParsedReply) and type(parsed.model) is Price
    assert (parsed.dropped_keys, parsed.normalised) == ([], []) and parsed.model.decision == "GRANT"


def test_a_fenced_reply_with_prose_around_it(parser):
    text = 'Here is my answer.\n```json\n' + json.dumps(PRICE) + '\n```\nLet me know!'
    assert parser.parse("priority", text).model.decision == "GRANT"


def test_the_brace_slice_and_a_cut_short_reply_are_read(parser):
    assert parser.parse("priority", 'Sure: {"kind": "price", "decision": "REFUSE"} done').model.decision == "REFUSE"
    assert parser.parse("priority", '{"kind": "price", "decision": "COUNTER", "reason": "cut sho').model.reason == "cut sho"


def test_bytes_and_an_already_parsed_object_are_accepted_too(parser):
    assert parser.parse("priority", json.dumps(PRICE).encode()).model.decision == "GRANT"
    assert parser.parse("priority", PRICE).model.decision == "GRANT"
    original = dict(PRICE)
    assert parser.parse("priority", original).model == parser.parse("priority", json.dumps(PRICE)).model
    assert original == PRICE                                              # the caller's dict is not touched


def test_text_with_no_json_is_not_json(parser):
    for text in ("I cannot do that", "", "   ", "no braces, sorry", "{broken: json}", 'prefix {"a": } suffix', "x {y}"):
        with pytest.raises(ReplyInvalid) as e:
            parser.parse("priority", text)
        assert e.value.code == "not_json", text
        assert e.value.violations[0].code == "not_json" and e.value.retry_text.startswith(RETRY_PREFIX)


@pytest.mark.parametrize("text, what", [
    ("[1,2]", "a list"), ('[{"decision": "GRANT"}]', "a list"), ('"GRANT"', "a string"), ("42", "a number"),
    ("null", "null"), ("true", "a boolean"), ("```json\n[1, 2]\n```", "a list"), ("  [1]  ", "a list"),
])
def test_json_that_is_not_an_object_is_not_object(parser, text, what):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", text)
    assert e.value.code == "not_object" and what in e.value.violations[0].message


def test_something_that_is_not_text_is_not_json(parser):
    for bad in (None, 5, ["a"], object()):
        with pytest.raises(ReplyInvalid) as e:
            parser.parse("priority", bad)
        assert e.value.code == "not_json"


@pytest.mark.parametrize("text", [
    "```json\n" + "\n" * 20_000 + "Sorry",                    # 0.5 s for 1000 lines, minutes for this one, before the fix
    "```json\n" + " \n" * 20_000 + "Sorry",
    "```" + " " * 100_000 + "x",
    "```json" + "\n" * 100_000,
    "```" + "\n" * 100_000 + "```" + "\n" * 100_000 + "Sorry",
    "```{" * 20_000,                                         # J2's own fence pattern was quadratic on these
    "```json\n{" * 20_000,
    "}```" + "```{" * 20_000,
])
def test_a_degenerate_reply_is_refused_quickly_not_after_minutes(parser, text):
    start = time.perf_counter()
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", text)
    assert time.perf_counter() - start < 1.0
    assert e.value.code == "not_json"


def test_a_fenced_non_object_with_a_lot_of_blank_lines_is_still_not_object_and_fast(parser):
    text = "```json\n" + "\n" * 20_000 + "[1, 2]" + "\n" * 20_000 + "```"
    start = time.perf_counter()
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", text)
    assert time.perf_counter() - start < 1.0
    assert e.value.code == "not_object" and "a list" in e.value.violations[0].message


@pytest.mark.parametrize("text, what", [
    ("```\n[1]\n```", "a list"), ("```json[1]```", "a list"), ("```json\n\n  5  \n\n```", "a number"),
    ("  ```json\n\"GRANT\"\n```  \n", "a string"), ("```null```", "null"), ("```json true ```", "a boolean"),
    ("```jsonnull```", "null"),                                  # a tag is dropped once; what follows is the content
])
def test_a_fenced_non_object_is_not_object(parser, text, what):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", text)
    assert e.value.code == "not_object" and what in e.value.violations[0].message


@pytest.mark.parametrize("text", [
    "```", "``````", "```json```", "```json", "```json\n", "```\nnot json\n```", "```JSON\n[1]\n```", "```json\njson [1]\n```",
    "``` [1]", "[1] ```", "```[1]``", "``json\n[1]\n``",
    "```json\n[1] xyz", "xyz [1]\n```",          # one fence end only: dropping three characters would leave a valid list
])
def test_text_that_is_not_one_fenced_json_value_is_not_json(parser, text):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", text)
    assert e.value.code == "not_json"


def test_a_reply_is_one_fence_only_when_it_has_an_opening_and_a_closing_one():
    # What the fence helper hands back, case by case: the content, or None when the text is not one fence end to end.
    for text in ("", "`", "``", "```", "````", "`````", "```json", "``` x", "x ```", "``json\n1\n``", "```json\n[1] xyz", "xyz [1]\n```"):
        assert replies._fenced_inner(text) is None, text
    assert replies._fenced_inner("``````") == "" and replies._fenced_inner("```json```") == ""
    assert replies._fenced_inner(" \n```json\n[1]\n```\n ") == "[1]"              # the text and the content are both stripped
    assert replies._fenced_inner("```\njson [1]\n```") == "json [1]"               # a tag counts only right after the fence
    assert replies._fenced_inner("```json [1]```") == "[1]" and replies._fenced_inner("```jsonx```") == "x"
    assert replies._fenced_inner("```JSON\n[1]\n```") == "JSON\n[1]"               # the tag is lower case, as in J2's pattern


# ---- a reply is limited in size, before any pattern runs ---------------------------------------------------------------

class Wide(Value):
    note: str = ""


def wide_parser():
    reg = ModelRegistry()
    reg.register_payload("wide", 1, Wide)
    return ReplyParser(reg)


def object_text_of(length):
    head, tail = '{"note": "', '"}'
    return head + "x" * (length - len(head) - len(tail)) + tail


def test_a_reply_over_the_payload_limit_is_refused_before_anything_reads_it(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the reply was read although it is over the limit")

    monkeypatch.setattr(replies, "extract_json", boom)
    monkeypatch.setattr(replies, "_loads", boom)
    parser = wide_parser()
    for reply, unit in ((" " * (MAX_PAYLOAD_BYTES + 1), "characters"), (b" " * (MAX_PAYLOAD_BYTES + 1), "bytes"),
                        (bytearray(b"{" * (MAX_PAYLOAD_BYTES + 1)), "bytes"), (object_text_of(MAX_PAYLOAD_BYTES + 1), "characters")):
        with pytest.raises(ReplyInvalid) as e:
            parser.parse("wide", reply)
        [v] = e.value.violations
        assert e.value.code == "not_json" and v.code == "reply_too_large"
        assert v.message == f"the reply is {len(reply)} {unit} long, the limit is {MAX_PAYLOAD_BYTES}: send one JSON object, shorter"
        assert e.value.retry_text == RETRY_PREFIX + v.message                    # the retry prompt says what to do about it


def test_a_reply_of_exactly_the_payload_limit_is_still_read():
    parser = wide_parser()
    text = object_text_of(MAX_PAYLOAD_BYTES)
    assert len(text) == MAX_PAYLOAD_BYTES
    assert len(parser.parse("wide", text).model.note) == MAX_PAYLOAD_BYTES - len('{"note": ""}')
    assert len(parser.parse("wide", text.encode()).model.note) == MAX_PAYLOAD_BYTES - len('{"note": ""}')


def test_a_text_reply_is_measured_in_characters_and_a_bytes_reply_in_bytes():
    parser = wide_parser()
    accented = object_text_of(MAX_PAYLOAD_BYTES).replace("x", "é")       # as long in characters, nearly twice as long in bytes
    assert len(accented) == MAX_PAYLOAD_BYTES and len(accented.encode("utf-8")) > MAX_PAYLOAD_BYTES
    assert parser.parse("wide", accented).model.note.startswith("éé")
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("wide", accented.encode("utf-8"))
    assert e.value.violations[0].code == "reply_too_large" and "bytes" in e.value.violations[0].message


def test_an_already_parsed_object_is_not_measured_by_the_reply_limit():
    assert wide_parser().parse("wide", {"note": "x" * (MAX_PAYLOAD_BYTES + 1)}).model.note.startswith("xxx")


def test_a_json_object_wins_over_a_fence_inside_one_of_its_strings(parser):
    tricky = json.dumps({"kind": "price", "decision": "GRANT", "reason": 'see ```json\n{"x": 1}\n``` above'})
    parsed = parser.parse("priority", tricky)
    assert parsed.model.decision == "GRANT" and "```" in parsed.model.reason


# ---- parse: enum words in any case ---------------------------------------------------------------------------------------

def test_enum_words_are_read_in_any_case_and_written_in_the_models_casing(parser):
    parsed = parser.parse("priority", '{"kind": "PRICE", "decision": "grant", "mode": " Fast "}', kind="price")
    assert parsed.model.decision == "GRANT" and parsed.model.mode == "fast" and parsed.model.kind == "price"
    assert parsed.normalised == ["kind", "decision", "mode"]


def test_enum_words_are_fixed_inside_lists_dicts_and_nested_models(parser):
    parsed = parser.parse("priority", json.dumps({
        "kind": "price", "decision": "Counter", "steps": [{"id": "a", "priority": "MUST"}, {"id": "b", "priority": "could"}],
        "by_name": {"x": {"id": "x", "priority": "Should"}}, "modes": ["FAST", "slow", "Slow"],
        "goal": {"kind": "SITE", "site_name": "s"}}))
    assert [s.priority for s in parsed.model.steps] == ["must", "could"]
    assert parsed.model.by_name["x"].priority == "should" and parsed.model.modes == ["fast", "slow", "slow"]
    assert type(parsed.model.goal) is SiteGoal
    assert parsed.normalised == ["decision", "steps.0.priority", "by_name.x.priority", "modes.0", "modes.2", "goal.kind"]


def test_a_word_that_is_right_already_is_not_reported(parser):
    assert parser.parse("priority", '{"kind": "price", "decision": "GRANT", "mode": "fast"}').normalised == []


def test_an_unknown_word_is_left_for_the_strict_check_to_refuse(parser):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"kind": "price", "decision": "MAYBE"}')
    assert e.value.code == "shape"
    assert [(v.path, v.code) for v in e.value.violations] == [("decision", "literal_error")]
    assert e.value.retry_text == "THE VALIDATOR REJECTED: decision: Input should be 'GRANT', 'COUNTER' or 'REFUSE'"


def test_an_ambiguous_word_is_left_alone():
    class Twin(Value):
        word: Literal["Ab", "aB"]

    fixed, changed = normalise_enums(Twin, {"word": "AB"})
    assert fixed == {"word": "AB"} and changed == []
    assert normalise_enums(Twin, {"word": "ab"})[1] == []                       # ambiguous too: both differ only in case
    assert normalise_enums(Twin, {"word": "Ab"}) == ({"word": "Ab"}, [])        # exact


def test_only_strings_are_fixed():
    class Num(Value):
        n: Literal[1, 2]
        s: Literal["a"]

    assert normalise_enums(Num, {"n": "1", "s": 5}) == ({"n": "1", "s": 5}, [])


# ---- parse: keys the class does not declare -------------------------------------------------------------------------------

def test_undeclared_keys_are_dropped_and_recorded_at_any_depth(parser):
    parsed = parser.parse("priority", json.dumps({
        "kind": "price", "decision": "GRANT", "colour": "red",
        "steps": [{"id": "a", "extra": 1}, {"id": "b"}], "by_name": {"x": {"id": "x", "more": 2}},
        "goal": {"kind": "doc", "product_name": "p", "junk": True}}))
    assert parsed.model.steps[0].id == "a" and type(parsed.model.goal) is DocGoal
    assert parsed.dropped_keys == ["colour", "steps.0.extra", "by_name.x.more", "goal.junk"]


def test_an_alias_is_a_declared_key(parser):
    assert parser.parse("priority", '{"kind": "price", "decision": "GRANT", "pass": true}').model.pass_ is True
    assert parser.parse("priority", '{"kind": "price", "decision": "GRANT", "pass_": true}').model.pass_ is True
    assert parser.parse("priority", '{"kind": "price", "decision": "GRANT", "pass": true}').dropped_keys == []


def test_nothing_is_logged_when_nothing_was_dropped(parser, caplog):
    with caplog.at_level(logging.DEBUG, logger="sutra.library"):
        parser.parse("priority", json.dumps(PRICE))
    assert caplog.records == []


def test_dropped_keys_are_logged_at_debug_only(parser, caplog):
    with caplog.at_level(logging.DEBUG, logger="sutra.library"):
        parser.parse("priority", '{"kind": "price", "decision": "GRANT", "colour": "red"}')
    records = [r for r in caplog.records if r.name == "sutra.library"]
    assert len(records) == 1 and records[0].levelno == logging.DEBUG and "colour" in records[0].getMessage()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="sutra.library"):
        parser.parse("priority", '{"kind": "price", "decision": "GRANT", "colour": "red"}')
    assert caplog.records == []


# ---- parse: discriminated unions ------------------------------------------------------------------------------------------

def test_a_union_member_is_picked_by_its_tag_in_any_case_and_then_cleaned(parser):
    parsed = parser.parse("request", json.dumps({
        "reason": "r", "ops": [{"op": "ADD", "name": "n", "parent": "Sales", "junk": 1}, {"op": "Move", "to": "t", "other": 2}],
        "one": {"op": "MOVE", "to": "x"}}))
    assert [type(o) for o in parsed.model.ops] == [Add, Move] and parsed.model.ops[0].parent == "sales"
    assert type(parsed.model.one) is Move
    assert parsed.dropped_keys == ["ops.0.junk", "ops.1.other"]
    assert parsed.normalised == ["ops.0.op", "ops.0.parent", "ops.1.op", "one.op"]


def test_an_unknown_tag_is_refused_by_the_strict_check(parser):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("request", '{"reason": "r", "ops": [{"op": "teleport"}]}')
    assert e.value.code == "shape" and [(v.path, v.code) for v in e.value.violations] == [("ops.0", "union_tag_invalid")]


def test_a_union_with_a_common_literal_field_needs_no_declared_discriminator():
    class Holder(Value):
        goal: Union[SiteGoal, DocGoal, None] = None

    fixed, dropped, changed = tolerate(Holder, {"goal": {"kind": "DOC", "product_name": "p", "x": 1}})
    assert fixed == {"goal": {"kind": "doc", "product_name": "p"}} and dropped == ["goal.x"] and changed == ["goal.kind"]
    assert tolerate(Holder, {"goal": None})[0] == {"goal": None}
    assert tolerate(Holder, {"goal": {"product_name": "no tag"}})[0] == {"goal": {"product_name": "no tag"}}      # cannot tell: left


def test_a_declared_discriminator_beats_the_field_the_parser_would_guess():
    # PA and QB share `kind` ("same"), so only the declared `op` can tell them apart
    on_field = tolerate(ByField, {"one": {"op": "B", "only_b": "x", "only_a": "y"}})
    assert on_field == ({"one": {"op": "b", "only_b": "x"}}, ["one.only_a"], ["one.op"])
    on_meta = tolerate(ByMeta, {"many": [{"op": "A", "only_a": "1", "only_b": "2"}, {"op": "b", "only_b": "3", "only_a": "4"}]})
    assert on_meta == ({"many": [{"op": "a", "only_a": "1"}, {"op": "b", "only_b": "3"}]},
                       ["many.0.only_b", "many.1.only_a"], ["many.0.op"])


def test_without_a_declared_discriminator_kind_is_preferred_and_else_the_first_common_literal():
    assert tolerate(Holder, {"auto_kind": {"kind": "Q", "mode": "m", "only_q": "x", "only_p": "y"}}) == (
        {"auto_kind": {"kind": "q", "mode": "m", "only_q": "x"}}, ["auto_kind.only_p"], ["auto_kind.kind"])
    assert tolerate(Holder, {"auto_op": {"op": "B", "only_b": "x", "only_a": "y"}}) == (
        {"auto_op": {"op": "b", "only_b": "x"}}, ["auto_op.only_a"], ["auto_op.op"])


def test_a_tag_that_matches_exactly_beats_one_that_matches_only_in_other_case():
    assert tolerate(Holder, {"case": {"op": "AB", "up": "1", "low": "2"}})[1] == ["case.low"]
    assert tolerate(Holder, {"case": {"op": "ab", "up": "1", "low": "2"}})[1] == ["case.up"]
    assert tolerate(Holder, {"case": {"op": "Ab", "up": "1", "low": "2"}})[1] == ["case.up"]          # no exact match: first


def test_a_tag_is_stripped_and_folded_against_the_models_own_casing():
    fixed, dropped, changed = tolerate(Holder, {"words": {"op": " refuse ", "b": "1", "a": "2"}})
    assert fixed == {"words": {"op": "REFUSE", "b": "1"}} and dropped == ["words.a"] and changed == ["words.op"]


def test_an_optional_single_model_is_cleaned_like_any_nested_model():
    fixed, dropped, changed = tolerate(Holder, {"maybe_step": {"id": "a", "priority": "MUST", "x": 1}})
    assert fixed == {"maybe_step": {"id": "a", "priority": "must"}} and dropped == ["maybe_step.x"] and changed == ["maybe_step.priority"]
    assert tolerate(Holder, {"maybe_step": None}) == ({"maybe_step": None}, [], [])
    # a model with no Literal field at all: nothing but the single-model rule can pick it
    assert tolerate(Holder, {"maybe_leaf": {"n": 1, "x": 2}}) == ({"maybe_leaf": {"n": 1}}, ["maybe_leaf.x"], [])


def test_a_union_of_a_literal_and_a_number_fixes_the_word_only():
    class Mixed(Value):
        either: Union[Literal["auto", "manual"], int]

    assert normalise_enums(Mixed, {"either": "AUTO"}) == ({"either": "auto"}, ["either"])
    assert normalise_enums(Mixed, {"either": 5}) == ({"either": 5}, [])
    assert normalise_enums(Mixed, {"either": "other"}) == ({"either": "other"}, [])


# ---- parse: strict after tolerant ---------------------------------------------------------------------------------------

def test_strictness_is_not_loosened_for_types(parser):
    for reply in ('{"kind": "price", "decision": "GRANT", "pass": "true"}', '{"kind": "price", "decision": "GRANT", "steps": [{"id": 5}]}',
                  '{"kind": "price", "decision": "GRANT", "steps": "none"}'):
        with pytest.raises(ReplyInvalid) as e:
            parser.parse("priority", reply)
        assert e.value.code == "shape"


def test_the_retry_text_names_every_violation_in_j2s_wording(parser):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"kind": "price", "decision": "nope", "steps": [{"id": 1}], "pass": 3}')
    assert e.value.retry_text.startswith("THE VALIDATOR REJECTED: ")
    parts = e.value.retry_text[len(RETRY_PREFIX):].split("; ")
    assert sorted(p.split(":")[0] for p in parts) == ["decision", "pass", "steps.0.id"]
    assert parts == [f"{v.path}: {v.message}" for v in e.value.violations]


def test_a_rule_of_the_class_shows_up_without_a_leading_colon(parser):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"kind": "price", "decision": "REFUSE", "steps": [{"id": "a"}]}')
    assert e.value.retry_text == "THE VALIDATOR REJECTED: REFUSE funds nothing: steps must be empty"
    assert [(v.path, v.code) for v in e.value.violations] == [("", "value_error")]


def test_retry_text_for_joins_with_semicolons_and_is_capped():
    vs = [violation("a.b", "x", "first"), violation("", "y", "second"), violation("c", "z", "third")]
    assert retry_text_for(vs) == "THE VALIDATOR REJECTED: a.b: first; second; c: third"
    long = retry_text_for([violation(f"field{i}", "x", "m" * 200) for i in range(50)])
    assert len(long) == 4000 and long.endswith("…") and long.startswith(RETRY_PREFIX)
    assert retry_text_for([]) == RETRY_PREFIX


def test_reply_invalid_keeps_its_own_list_of_violations():
    given = (violation("a", "x", "m"), violation("b", "y", "n"))
    error = ReplyInvalid("shape", given)
    assert error.violations == list(given) and isinstance(error.violations, list)
    as_list = [violation("a", "x", "m")]
    error = ReplyInvalid("shape", as_list)
    as_list.append(violation("b", "y", "n"))
    assert len(error.violations) == 1


def test_reply_invalid_carries_code_violations_and_retry_text():
    error = ReplyInvalid("shape", [violation("a", "c", "m")])
    assert (error.code, error.retry_text) == ("shape", "THE VALIDATOR REJECTED: a: m") and "m" in str(error)
    custom = ReplyInvalid("not_json", [], retry_text="say it again")
    assert custom.retry_text == "say it again" and "not_json" in str(custom)


# ---- parse: choosing the class --------------------------------------------------------------------------------------------

def test_a_family_with_several_classes_is_told_apart_by_the_replys_own_kind(parser):
    assert type(parser.parse("priority", '{"kind": "envelope_check", "decision": "HOLD"}').model) is Envelope
    assert type(parser.parse("priority", '{"kind": "Envelope_Check", "decision": "HOLD"}').model) is Envelope
    assert type(parser.parse("priority", PRICE).model) is Price


def test_the_kind_can_be_named_by_the_caller_so_the_reply_need_not_say_it(parser):
    assert type(parser.parse("priority", '{"decision": "HOLD"}', kind="envelope_check").model) is Envelope
    with pytest.raises(ReplyInvalid) as e:                                       # but it cannot say something else
        parser.parse("priority", '{"kind": "price", "decision": "GRANT"}', kind="envelope_check")
    assert e.value.code == "shape"


def test_a_missing_or_unknown_kind_in_a_multi_class_family_is_a_shape_error(parser):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"decision": "GRANT"}')
    assert [(v.path, v.code) for v in e.value.violations] == [("kind", "union_tag_not_found")] and "envelope_check" in e.value.violations[0].message
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"kind": "refund", "decision": "GRANT"}')
    assert [(v.path, v.code) for v in e.value.violations] == [("kind", "union_tag_invalid")]
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"kind": 5, "decision": "GRANT"}')
    assert e.value.violations[0].code == "union_tag_invalid"


def test_the_kind_in_a_reply_may_be_padded_or_in_any_case(parser):
    parsed = parser.parse("priority", '{"kind": "  PRICE ", "decision": "GRANT"}')
    assert type(parsed.model) is Price and parsed.normalised == ["kind"]


def test_one_class_with_several_kinds_needs_no_kind_in_the_reply():
    class Change(Record):
        FAMILY = "chart_change"
        kind: Literal["reuse", "add", "rearrange"] = "reuse"
        reason: str = ""

    reg = ModelRegistry()
    reg.register(Change)
    parser = ReplyParser(reg)
    assert parser.parse("chart_change", '{"reason": "r"}').model.kind == "reuse"
    assert parser.parse("chart_change", '{"kind": "ADD"}').model.kind == "add"
    assert parser.parse("chart_change", '{"reason": "r"}', kind="rearrange").model.kind == "reuse"


def test_the_error_for_a_missing_kind_lists_the_kinds_in_order(parser):
    with pytest.raises(ReplyInvalid) as e:
        parser.parse("priority", '{"decision": "GRANT"}')
    assert e.value.violations[0].message == "the reply must say which kind it is: one of envelope_check, price"


def test_a_payload_family_needs_no_kind(parser):
    assert type(parser.parse("request", '{"reason": "r"}').model) is Request


def test_asking_for_a_family_or_kind_that_does_not_exist_is_a_registry_error(parser):
    with pytest.raises(RegistryError) as e:
        parser.parse("ghost", "{}")
    assert e.value.code == "unknown_family"
    with pytest.raises(RegistryError) as e:
        parser.parse("priority", "{}", kind="ghost")
    assert e.value.code == "unknown_kind"
    with pytest.raises(RegistryError) as e:
        parser.parse("priority", "{}", kind="price", version=9)
    assert e.value.code == "unknown_version"


def test_the_version_can_be_chosen():
    reg = ModelRegistry()

    class V1(Record):
        FAMILY = "evolving"
        kind: Literal["e"] = "e"
        old: str = ""

    class V2(Record):
        FAMILY = "evolving"
        VERSION = 2
        kind: Literal["e"] = "e"
        schema_version: int = 2
        new: str = ""

    reg.register(V1)
    reg.register(V2)
    parser = ReplyParser(reg)
    assert type(parser.parse("evolving", '{"new": "x"}').model) is V2
    assert type(parser.parse("evolving", '{"old": "x"}', version=1).model) is V1
    latest = parser.parse("evolving", '{"old": "x"}')                    # read as the latest: the old key is not declared
    assert type(latest.model) is V2 and latest.dropped_keys == ["old"]


def test_the_default_parser_uses_the_apps_registry():
    from sutra_app.library.registry import REGISTRY
    assert ReplyParser()._registry is REGISTRY


# ---- the tolerant helpers on their own ------------------------------------------------------------------------------------

def test_tolerate_does_not_change_its_input():
    data = {"kind": "PRICE", "decision": "grant", "colour": 1, "steps": [{"id": "a", "priority": "MUST", "x": 1}]}
    before = json.loads(json.dumps(data))
    fixed, dropped, changed = tolerate(Price, data)
    assert data == before and fixed is not data
    assert fixed == {"kind": "price", "decision": "GRANT", "steps": [{"id": "a", "priority": "must"}]}
    assert dropped == ["colour", "steps.0.x"] and changed == ["kind", "decision", "steps.0.priority"]


def test_normalise_enums_leaves_unknown_keys_and_drop_unknown_leaves_words():
    data = {"kind": "price", "decision": "grant", "colour": 1}
    assert normalise_enums(Price, data) == ({"kind": "price", "decision": "GRANT", "colour": 1}, ["decision"])
    assert drop_unknown(Price, data) == ({"kind": "price", "decision": "grant"}, ["colour"])


def test_anything_that_is_not_a_dict_is_returned_as_it_is():
    assert tolerate(Price, [1, 2]) == ([1, 2], [], [])
    assert tolerate(Price, "text") == ("text", [], [])
    assert normalise_enums(Price, {"decision": None, "steps": "no", "by_name": [1]}) == (
        {"decision": None, "steps": "no", "by_name": [1]}, [])


def test_a_parsed_reply_is_immutable_and_holds_lists():
    parsed = ParsedReply(model=Step(id="a"), dropped_keys=["x"], normalised=["y"])
    with pytest.raises(Exception):
        parsed.model = Step(id="b")
    assert ParsedReply(model=Step(id="a")).dropped_keys == []
