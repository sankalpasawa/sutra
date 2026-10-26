"""The law of a child version, as pure functions (PRD amendment A2, A2-LAW): layers/lineage.py.

  L1  words merge per (group, part, field) and layout per (group, part), on copies; None and {} are accepted on both sides
  L2  merge_recipe: the parent's recipe plus a keyed patch, against the real identity and coordination recipes read from
      disk; one refusal for each malformed patch, in words that name the step; the arguments are never changed
  L3  recipe_faults: [] for every recipe against itself and for the merges of L2, one named fault for each way a child breaks
      the substitutability law, in the order the checks run
  L4  rank and tightens: admit below wait below refuse, for both result shapes of a gate body
  L5  the classification test (every step field of every recipe on disk is fixed or free) and the hygiene test (the module
      imports nothing from the runtime at import time)

The law is data in, data out: nothing here starts a department, reads a registry or reloads a module. The runtime's own rules
(engine_runtime.validate with a child in place) are layers.definition_faults, A2-INHERIT's, and are not called.
"""
import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from layers import R, S
from layers import lineage as L

HERE = Path(__file__).resolve().parent
LAYERS = HERE / "layers"
FIXTURES = HERE / "test_fixtures" / "lineage"
FUNCTION_LAYERS = ("identity", "priority", "coordination", "adaptation", "audit")


def recipe(layer):
    return json.loads((LAYERS / layer / "v1.json").read_text(encoding="utf-8"))


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def containers(x, into=None):
    """The identity of every dict and list inside x: two values that share one of them are not independent copies."""
    into = set() if into is None else into
    if isinstance(x, (dict, list)):
        into.add(id(x))
        for v in (x.values() if isinstance(x, dict) else x):
            containers(v, into)
    return into


def handler(r, msg_type, word=None):
    return next(h for h in r["on"] if (h["when"]["msg_type"], h["when"].get("word")) == (msg_type, word))


def ids(steps):
    return [s["id"] for s in steps]


# ---- L1 . words and layout ---------------------------------------------------------------------------------------------
from layers.coordination import v1 as COORD  # noqa: E402 -- the real WORDS and LAYOUT the done-check names


def test_l1_words_overlay_one_field_and_the_rest_of_the_part_is_kept():
    parent = {"goal": {"does": {"text": "old words", "note": "kept"}, "skills": {"items": ["a", "b"]}}}
    got = L.merge_words(parent, {"goal": {"does": {"text": "new words"}}})
    assert got == {"goal": {"does": {"text": "new words", "note": "kept"}, "skills": {"items": ["a", "b"]}}}


def test_l1_words_a_new_part_and_a_new_group_are_added():
    parent = {"goal": {"does": {"text": "old"}}}
    own = {"goal": {"extra": {"text": "more"}}, "fresh": {"part": {"x": 1}}}
    assert L.merge_words(parent, own) == {"goal": {"does": {"text": "old"}, "extra": {"text": "more"}},
                                          "fresh": {"part": {"x": 1}}}


def test_l1_words_a_part_named_with_no_field_adds_nothing():
    parent = {"goal": {"does": {"text": "old"}}}
    assert L.merge_words(parent, {"goal": {"empty": {}, "none": None}, "ghost": {"part": {}}}) == parent
    assert L.merge_words(parent, {"goal": None, "ghost": None}) == parent


def test_l1_layout_a_part_is_replaced_whole_and_the_others_stay():
    parent = {"goal": {"does": "{text}", "skills": "{items}"}, "tie": {"tie": "{task}\n{returns}"}}
    got = L.merge_layout(parent, {"goal": {"does": "DOES {text}"}, "extra": {"part": "{x}"}})
    assert got == {"goal": {"does": "DOES {text}", "skills": "{items}"}, "tie": {"tie": "{task}\n{returns}"},
                   "extra": {"part": "{x}"}}


def test_l1_real_coordination_words_and_layout():
    words = L.merge_words(COORD.WORDS, {"goal": {"does": {"text": "changed"}}, "tie": {"extra": {"task": "new part"}}})
    want = copy.deepcopy(COORD.WORDS)
    want["goal"]["does"]["text"] = "changed"
    want["tie"]["extra"] = {"task": "new part"}
    assert words == want
    assert words["goal"]["skills"] == COORD.WORDS["goal"]["skills"]
    layout = L.merge_layout(COORD.LAYOUT, {"tie": {"tie": "T {task}"}})
    want = copy.deepcopy(COORD.LAYOUT)
    want["tie"]["tie"] = "T {task}"
    assert layout == want
    assert layout["goal"] == COORD.LAYOUT["goal"]


def test_l1_the_arguments_are_unchanged_and_the_result_shares_nothing_with_them():
    own_words = {"goal": {"skills": {"items": ["one", "two"]}, "new": {"nested": {"deep": ["x"]}}}, "fresh": {"p": {"f": "v"}}}
    own_layout = {"goal": {"does": "DOES {text}"}, "fresh": {"p": "{f}"}}
    before = [copy.deepcopy(x) for x in (COORD.WORDS, own_words, COORD.LAYOUT, own_layout)]
    words = L.merge_words(COORD.WORDS, own_words)
    layout = L.merge_layout(COORD.LAYOUT, own_layout)
    assert [COORD.WORDS, own_words, COORD.LAYOUT, own_layout] == before
    assert not containers(words) & (containers(COORD.WORDS) | containers(own_words))
    assert not containers(layout) & (containers(COORD.LAYOUT) | containers(own_layout))
    # the copy is a copy: writing to the result writes to neither argument
    words["goal"]["skills"]["items"].append("three")
    words["goal"]["new"]["nested"]["deep"].append("y")
    layout["goal"]["skills"] = "changed"
    assert own_words["goal"]["skills"]["items"] == ["one", "two"]
    assert "three" not in COORD.WORDS["goal"]["skills"]["items"]
    assert own_words["goal"]["new"]["nested"]["deep"] == ["x"]
    assert COORD.LAYOUT["goal"]["skills"] == "{items}"


def test_l1_none_and_empty_are_accepted_on_both_sides():
    parent_w, parent_l = copy.deepcopy(COORD.WORDS), copy.deepcopy(COORD.LAYOUT)
    own_w, own_l = {"goal": {"does": {"text": "t"}}}, {"goal": {"does": "{text}"}}
    for empty in (None, {}):
        assert L.merge_words(empty, empty) == {} and L.merge_layout(empty, empty) == {}
        got = L.merge_words(parent_w, empty)
        assert got == parent_w and not containers(got) & containers(COORD.WORDS)
        got = L.merge_layout(parent_l, empty)
        assert got == parent_l and not containers(got) & containers(COORD.LAYOUT)
        got = L.merge_words(empty, own_w)
        assert got == own_w and not containers(got) & containers(own_w)
        got = L.merge_layout(empty, own_l)
        assert got == own_l and not containers(got) & containers(own_l)
    assert COORD.WORDS == parent_w and COORD.LAYOUT == parent_l
