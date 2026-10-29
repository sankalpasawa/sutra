"""A5 P1.2: the page words (A5.1.3, A5.1.4): PageWords, the kind table validated at import, the fallback kept apart."""
import re

import pytest
from pydantic import TypeAdapter

import layer_models.a5_types as A
import layer_models.a5_words as W
from layer_models.faults import sentences

S4_KEYS = {"team", "noun", "describe", "describe_long", "start", "ready", "built", "rubric", "style_empty", "memory_off", "go_preview",
           "new_task", "retry", "frame_title", "steps", "examples", "follow_ups", "pick", "can_open", "can_download", "hide_tabs"}
AD = TypeAdapter(W.PageWords)


def test_the_fields_are_exactly_the_keys_the_page_reads_and_all_are_optional():
    assert set(W.PageWords.model_fields) == S4_KEYS
    assert all(not f.is_required() for f in W.PageWords.model_fields.values())
    assert W.PageWords().model_dump(exclude_none=True) == {}


def test_a_hostile_or_unknown_word_is_refused():
    assert sentences(AD, {"colour": "red"}) == ["$.colour: is not a field here"]
    assert sentences(AD, {"team": ""}) and sentences(AD, {"team": "x" * 81}) and sentences(AD, {"noun": "Site"}) and sentences(AD, {"noun": "a1"})
    assert sentences(AD, {"steps": ["x"] * 8}) and sentences(AD, {"steps": ["x"] * 10}) and sentences(AD, {"steps": ["x"] * 9}) == []
    assert sentences(AD, {"examples": ["x"] * 6}) and sentences(AD, {"follow_ups": ["x"] * 5})
    assert sentences(AD, {"hide_tabs": ["docs", "docs"]}) and sentences(AD, {"hide_tabs": ["board"]}) and sentences(AD, {"hide_tabs": ["docs", "preview"]}) == []
    assert sentences(AD, {"pick": "no"}) and sentences(AD, {"can_open": False}) == []


def test_the_table_is_validated_and_the_website_entry_is_the_empty_object():
    assert set(W.KIND_WORDS) == {"website", "default", "organic", "root"}
    assert W.KIND_WORDS["website"].model_dump(exclude_none=True) == {}, "a website department sees the prototype's text"
    assert [W.KIND_WORDS[k].noun for k in ("default", "organic", "root")] == ["result", "work", "department"]
    assert W.FALLBACK_WORDS.noun == "work"
    for kind in ("default", "organic", "root"):
        w = W.KIND_WORDS[kind]
        assert (w.pick, w.can_download, w.can_open) == (False, False, True)
        assert w.hide_tabs == ["docs", "style", "lessons", "playbooks"] and len(w.steps) == 9
        assert w.go_preview == "Open the preview" and w.new_task == "Give it another task" and w.retry == "Try again"


def test_a_wrong_entry_stops_the_import_not_a_poll():
    bad = dict(W._KIND_TABLE, default={"noun": "Result"})
    with pytest.raises(Exception):
        W._KIND_ADAPTER.validate_python(bad)
    with pytest.raises(Exception):
        W._KIND_ADAPTER.validate_python({"Not A Kind": {}})


def test_kind_words_returns_the_entry_or_the_fallback_and_a_kind_named_fallback_cannot_collide():
    assert W.kind_words("default") is W.KIND_WORDS["default"] and W.kind_words("website") is W.KIND_WORDS["website"]
    assert W.kind_words("fallback") is W.FALLBACK_WORDS and W.kind_words("anything-else") is W.FALLBACK_WORDS
    assert W.kind_words(None) is W.FALLBACK_WORDS and W.kind_words(["x"]) is W.FALLBACK_WORDS
    assert "fallback" not in W.KIND_WORDS


def test_the_neutral_entries_say_none_of_the_website_words():
    for kind in ("default", "organic", "root"):
        text = " ".join(str(v) for v in W.KIND_WORDS[kind].model_dump(exclude_none=True).values()).lower()
        assert not re.search(r"website|\bsite\b|\bprd\b|document|page|blog|charter", text), (kind, text)


def test_the_shared_scalars():
    assert re.fullmatch(A.MID_RE, "m-00000000a001") and not re.fullmatch(A.MID_RE, "m-xyz")
    assert re.fullmatch(A.NODE_ID_RE, "task:m-00000000a001") and re.fullmatch(A.NODE_ID_RE, "dept:dref-acme0001") and re.fullmatch(A.NODE_ID_RE, "shadow:now")
    assert re.fullmatch(A.NODE_ID_RE, "conv:shc-a1b2c3") and re.fullmatch(A.NODE_ID_RE, "goal:g-000000000001")
    assert not re.fullmatch(A.NODE_ID_RE, "task:g-000000000001") and not re.fullmatch(A.NODE_ID_RE, "dept:../x") and not re.fullmatch(A.NODE_ID_RE, "shadow:later")
    assert re.fullmatch(A.REF_RE, "dref-acme0001") and not re.fullmatch(A.REF_RE, "a/b")
