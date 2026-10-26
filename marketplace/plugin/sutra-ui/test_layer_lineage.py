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


# ---- L2 . merge_recipe -------------------------------------------------------------------------------------------------
def merged(parent, patch, layer="identity"):
    """merge_recipe, and the proof that it changed neither argument."""
    before = copy.deepcopy(parent), copy.deepcopy(patch)
    got = L.merge_recipe(parent, patch, layer)
    assert (parent, patch) == before
    assert not containers(got) & (containers(parent) | containers(patch)), "the merge shares a dict or list with an argument"
    return got


def refused(parent, patch, *words):
    """The merge refuses the patch with a ModelFault whose text holds every word, and changes neither argument."""
    before = copy.deepcopy(parent), copy.deepcopy(patch)
    with pytest.raises(L.ModelFault) as caught:
        L.merge_recipe(parent, patch, "identity")
    text = str(caught.value)
    for w in words:
        assert w in text, "%r is not in the fault %r" % (w, text)
    assert (parent, patch) == before
    return text


def in_handler(msg_type, word, *steps):
    return {"on": [{"when": {"msg_type": msg_type, "word": word}, "steps": list(steps)}]}


def in_request(*steps):
    return in_handler("request", "request", *steps)


def a_step(without=(), **over):
    """A new step that meets the definitions' requirements (a step by code), with some fields left out or changed."""
    step = {"id": "identity.note", "name": "Note the request", "nature": "transform", "born": "C2", "code": "identity_read",
            "check": "facts_are_closed"}
    step.update(over)
    return {k: v for k, v in step.items() if k not in without}


def test_modelfault_is_not_a_valueerror():
    assert issubclass(L.ModelFault, Exception) and not issubclass(L.ModelFault, ValueError)


# The step fields A2 named. They are a floor, not the whole list: a package classifies a field it adds to a recipe step by adding
# it to STEP_FIXED or STEP_FREE (A3-CORE did so for may_end and side_by_side), and this test must not turn red on that one-line
# edit. A name leaves a list only by an edit of this test, which is the review that matters.
A2_STEP_FIXED = ("nature", "check", "answer", "out", "or", "only_if", "stringency", "each", "files", "by_hand")
A2_STEP_FREE = ("name", "born", "code", "prompt", "draft", "ceiling", "facts", "tools", "timeout_s", "below")


def test_the_names_the_inheritance_codes_against():
    assert L.PATCH_KEYS == ("parent", "set", "gates", "rules", "steps", "on")
    assert L.TOP_SET == ("description", "skills") and L.POSITION == ("after", "before")
    # may_end (fixed) and side_by_side (free) are fields the recipes use that A2 left out: A3-CORE classified them in DEFS['step']
    # (A2.12 rule 6) and in the two lists, and test_layer_templates holds the two classifications equal. They are not pinned here.
    assert set(A2_STEP_FIXED) <= set(L.STEP_FIXED), set(A2_STEP_FIXED) - set(L.STEP_FIXED)
    assert set(A2_STEP_FREE) <= set(L.STEP_FREE), set(A2_STEP_FREE) - set(L.STEP_FREE)
    assert L.STEP_FIELDS == ("id",) + L.STEP_FIXED + L.STEP_FREE
    assert L.GATE_ORDER == ("admit", "wait", "refuse")
    assert L.handler_key({"when": {"msg_type": "inform", "word": "born"}}) == ("inform", "born")
    assert L.handler_key({"when": {"msg_type": "accept-proposal"}}) == ("accept-proposal", S.ANY)
    assert L.only_if_target("adapt.source.source=library") == "adapt.source"
    assert L.only_if_target("identity.read.later") == "identity.read"


def classify_in_lineage(monkeypatch, fixed=(), free=(), drop=()):
    """The lists as a later package leaves them: names added to either, or (to prove the floor holds) one taken out."""
    new_fixed = tuple(f for f in L.STEP_FIXED if f not in drop) + tuple(fixed)
    new_free = tuple(f for f in L.STEP_FREE if f not in drop) + tuple(free)
    monkeypatch.setattr(L, "STEP_FIXED", new_fixed)
    monkeypatch.setattr(L, "STEP_FREE", new_free)
    monkeypatch.setattr(L, "STEP_FIELDS", ("id",) + new_fixed + new_free)


def test_the_names_test_takes_a_field_a_later_package_classifies(monkeypatch):
    """The next field to be classified (one fixed, one free, as A3-CORE's were) is one line in lineage.py; the pin above stays
    green."""
    classify_in_lineage(monkeypatch, fixed=("next_fixed",), free=("next_free",))
    test_the_names_the_inheritance_codes_against()
    assert "next_fixed" in L.STEP_FIXED and "next_free" in L.STEP_FREE and "next_fixed" in L.STEP_FIELDS


@pytest.mark.parametrize("name", A2_STEP_FIXED + A2_STEP_FREE)
def test_the_names_test_still_fails_when_an_a2_field_leaves_a_list(monkeypatch, name):
    classify_in_lineage(monkeypatch, drop=(name,))
    with pytest.raises(AssertionError):
        test_the_names_the_inheritance_codes_against()


def test_all_steps_run_gates_rules_steps_then_each_handlers_steps():
    r = recipe("coordination")
    want = ids(r["gates"]) + ids(r["rules"]) + ids(r["steps"]) + [s["id"] for h in r["on"] for s in h["steps"]]
    assert ids(L.all_steps(r)) == want == L.step_ids(r)
    assert L.all_steps(None) == [] and L.step_ids({}) == []


def test_l2a_the_identity_patch_gives_the_expected_recipe():
    parent, patch = recipe("identity"), fixture("identity.patch.json")
    got = merged(parent, patch)
    want = copy.deepcopy(parent)
    want["description"] = patch["set"]["description"]
    take = handler(want, "request", "request")["steps"]
    new = {k: v for k, v in patch["on"][0]["steps"][0].items() if k != "after"}
    take.insert(ids(take).index("identity.read") + 1, new)
    next(s for s in take if s["id"] == "identity.take")["name"] = patch["on"][0]["steps"][1]["name"]
    assert got == want
    # the same handlers, in the same order; the new step stands right after identity.read; the overlay is applied in place
    assert [L.handler_key(h) for h in got["on"]] == [L.handler_key(h) for h in parent["on"]]
    ids_now = ids(handler(got, "request", "request")["steps"])
    assert ids_now[:3] == ["identity.read", "identity.note", "identity.recognise"]
    assert len(ids_now) == len(ids(handler(parent, "request", "request")["steps"])) + 1
    assert next(s for s in handler(got, "request", "request")["steps"] if s["id"] == "identity.take")["name"] == \
        "Judge it against the goal and the rules"
    assert got["description"] != parent["description"] and got["skills"] == parent["skills"]
    assert got["gates"] == parent["gates"] and got["start"] == parent["start"]


def test_l2b_the_coordination_patch_gives_the_expected_recipe():
    parent, patch = recipe("coordination"), fixture("coordination.patch.json")
    got = merged(parent, patch, "coordination")
    want = copy.deepcopy(parent)
    born = handler(want, "inform", "born")["steps"]
    born.append({k: v for k, v in patch["on"][0]["steps"][0].items() if k != "after"})
    born[0]["name"] = patch["on"][0]["steps"][1]["name"]
    assert got == want
    assert ids(handler(got, "inform", "born")["steps"]) == ["coord.table", "coord.probe"]
    assert handler(got, "inform", "born")["steps"][0]["name"].endswith("version 2")
    for key in ("gates", "rules", "steps", "description", "skills", "start"):
        assert got[key] == parent[key]


def test_an_empty_patch_is_the_parent_copied():
    parent = recipe("coordination")
    got = merged(parent, {})
    assert got == parent and got is not parent
    assert merged(parent, {"parent": "coordination/v1", "set": None, "gates": [], "rules": None, "steps": None, "on": []}) == parent


def test_set_changes_the_description_and_the_skills_and_a_null_deletes():
    parent = recipe("identity")
    got = merged(parent, {"set": {"description": "d", "skills": ["a", "b"]}})
    assert (got["description"], got["skills"]) == ("d", ["a", "b"])
    got = merged(parent, {"set": {"description": None, "skills": None}})
    assert "description" not in got and "skills" not in got
    assert {k: v for k, v in got.items()} == {k: v for k, v in parent.items() if k not in ("description", "skills")}


def test_a_new_step_goes_after_before_or_last_and_may_anchor_on_a_step_the_patch_just_added():
    parent = recipe("identity")
    base = ids(handler(parent, "request", "request")["steps"])
    got = merged(parent, in_request(a_step(id="identity.a", after="identity.recognise"), a_step(id="identity.b", before="identity.take"),
                                    a_step(id="identity.c")))
    now = ids(handler(got, "request", "request")["steps"])
    assert now == base[:2] + ["identity.a", "identity.b"] + base[2:] + ["identity.c"]
    got = merged(parent, in_request(a_step(id="identity.a", after="identity.read"),
                                    a_step(id="identity.b", after="identity.a"),
                                    a_step(id="identity.c", before="identity.a")))
    assert ids(handler(got, "request", "request")["steps"])[:4] == ["identity.read", "identity.c", "identity.a", "identity.b"]


def test_a_new_soft_step_names_its_prompt_its_draft_and_the_shape_of_its_answer():
    parent = recipe("identity")
    soft = {"id": "identity.think", "name": "Think", "nature": "decide", "born": "C0", "prompt": "identity_take",
            "draft": "identity_take_draft", "out": {"verdict": ["go", "ask"]}, "check": "verdict_is_known", "ceiling": "C2",
            "after": "identity.recognise"}
    got = merged(parent, in_request(soft))
    step = next(s for s in handler(got, "request", "request")["steps"] if s["id"] == "identity.think")
    assert step == {k: v for k, v in soft.items() if k != "after"}


def test_a_new_gate_a_new_rule_and_a_new_top_level_step_are_added_to_their_own_lists():
    parent = recipe("identity")
    assert "steps" not in parent and "rules" not in parent
    got = merged(parent, {"gates": [a_step(id="identity.g", after="identity.gate", nature="decide")],
                          "rules": [a_step(id="identity.r")], "steps": [a_step(id="identity.s")]})
    assert ids(got["gates"]) == ["identity.gate", "identity.g", "identity.wait_engine"]
    assert ids(got["rules"]) == ["identity.r"] and ids(got["steps"]) == ["identity.s"]


def test_a_free_field_of_a_gate_or_a_rule_is_overlaid_in_place():
    parent = recipe("identity")
    got = merged(parent, {"gates": [{"id": "identity.gate", "name": "Gate it, version 2", "code": "identity_wait_engine"}]})
    gate = got["gates"][0]
    assert (gate["name"], gate["code"]) == ("Gate it, version 2", "identity_wait_engine")
    assert {k: v for k, v in gate.items() if k not in ("name", "code")} == \
        {k: v for k, v in parent["gates"][0].items() if k not in ("name", "code")}
    assert ids(got["gates"]) == ids(parent["gates"])
    coord = recipe("coordination")
    got = merged(coord, {"rules": [{"id": "coord.busy", "name": "Keep one run going", "code": "coord_pick"}]}, "coordination")
    assert (got["rules"][0]["name"], got["rules"][0]["code"]) == ("Keep one run going", "coord_pick")


def test_every_free_field_may_be_replaced_and_a_null_deletes_it():
    parent = recipe("identity")
    take = next(s for s in handler(parent, "request", "request")["steps"] if s["id"] == "identity.take")
    over = {"name": "N", "born": "C1", "code": "identity_read", "prompt": "identity_enough", "draft": "identity_enough_draft",
            "ceiling": "C1", "facts": ["kind"], "tools": [], "timeout_s": 30, "below": "C0"}
    got = merged(parent, in_request(dict(over, id="identity.take")))
    step = next(s for s in handler(got, "request", "request")["steps"] if s["id"] == "identity.take")
    assert {k: step[k] for k in over} == over
    assert {k: v for k, v in step.items() if k not in over} == {k: v for k, v in take.items() if k not in over}
    got = merged(parent, in_request({"id": "identity.take", "ceiling": None, "facts": None, "prompt": None}))
    step = next(s for s in handler(got, "request", "request")["steps"] if s["id"] == "identity.take")
    assert "ceiling" not in step and "facts" not in step and "prompt" not in step and step["draft"] == take["draft"]


def test_a_fixed_field_given_as_the_parent_has_it_is_accepted():
    parent = recipe("identity")
    take = next(s for s in handler(parent, "request", "request")["steps"] if s["id"] == "identity.take")
    fixed = {k: take[k] for k in ("nature", "check", "answer", "out", "only_if", "stringency")}
    assert merged(parent, in_request(dict(fixed, id="identity.take", name="Same, renamed"))) is not None
    got = merged(parent, in_request(dict(fixed, id="identity.take")))
    assert got == parent


def test_an_out_that_adds_a_key_or_reorders_an_enum_is_accepted():
    parent = recipe("coordination")
    patch = {"steps": [{"id": "coord.tie", "out": {"answer": "str", "why": "str", "note": "str"}}]}
    got = merged(parent, patch, "coordination")
    assert next(s for s in got["steps"] if s["id"] == "coord.tie")["out"] == {"answer": "str", "why": "str", "note": "str"}
    parent = recipe("identity")
    got = merged(parent, in_request({"id": "identity.take", "out": {"verdict": ["refuse", "go", "ask"], "why": "str"}}))
    step = next(s for s in handler(got, "request", "request")["steps"] if s["id"] == "identity.take")
    assert step["out"] == {"verdict": ["refuse", "go", "ask"], "why": "str"}


def test_an_out_given_to_a_step_that_had_none_is_accepted_and_an_empty_one_changes_nothing():
    parent = recipe("identity")
    got = merged(parent, in_request({"id": "identity.read", "out": {"cue": "str"}}))
    assert handler(got, "request", "request")["steps"][0]["out"] == {"cue": "str"}
    assert merged(parent, in_request({"id": "identity.read", "out": None})) == parent
    assert merged(parent, in_request({"id": "identity.read", "out": {}})) == parent


def test_the_patch_is_not_changed_by_a_merge_that_overlays_and_inserts():
    parent, patch = recipe("identity"), fixture("identity.patch.json")
    once = merged(parent, patch)
    twice = merged(parent, patch)
    assert once == twice


MALFORMED = [
    # (label, patch builder, words the fault holds)
    ("an unknown patch key", lambda: {"drop": ["identity.take"]}, ["drop"]),
    ("a parent that is not a string", lambda: {"parent": 3}, ["parent"]),
    ("set of start", lambda: {"set": {"start": {"on": [{"kind": "post"}], "unless": []}}}, ["start"]),
    ("set of steps", lambda: {"set": {"steps": []}}, ["steps"]),
    ("set that is not an object", lambda: {"set": ["description"]}, ["set"]),
    ("a description that is not words", lambda: {"set": {"description": 5}}, ["description"]),
    ("skills that are not a list of words", lambda: {"set": {"skills": [1, 2]}}, ["skills"]),
    ("a list of the patch that is not a list of objects", lambda: {"steps": ["identity.take"]}, ["steps"]),
    ("a missing anchor, after", lambda: in_request(a_step(after="identity.nowhere")), ["identity.note", "identity.nowhere"]),
    ("a missing anchor, before", lambda: in_request(a_step(before="identity.nowhere")), ["identity.note", "identity.nowhere"]),
    ("an anchor that is a step of another list", lambda: in_request(a_step(after="identity.gate")),
     ["identity.note", "identity.gate"]),
    ("after and before together", lambda: in_request(a_step(after="identity.read", before="identity.take")),
     ["identity.note", "after and before"]),
    ("an anchor that is not an id", lambda: in_request(a_step(after=7)), ["identity.note", "after"]),
    ("an inherited step given an after", lambda: in_request({"id": "identity.take", "after": "identity.read"}),
     ["identity.take", "after"]),
    ("an inherited step given a before", lambda: in_request({"id": "identity.take", "before": "identity.read"}),
     ["identity.take", "before"]),
    ("a gate given an after", lambda: {"gates": [{"id": "identity.gate", "after": "identity.wait_engine"}]},
     ["identity.gate", "after"]),
    ("nature changed", lambda: in_request({"id": "identity.take", "nature": "make"}), ["identity.take", "nature"]),
    ("check changed", lambda: in_request({"id": "identity.take", "check": "facts_are_closed"}), ["identity.take", "check"]),
    ("only_if changed", lambda: in_request({"id": "identity.take", "only_if": "identity.read.later"}),
     ["identity.take", "only_if"]),
    ("only_if deleted", lambda: in_request({"id": "identity.take", "only_if": None}), ["identity.take", "only_if"]),
    ("only_if added to a step with none", lambda: in_request({"id": "identity.read", "only_if": "identity.read.later"}),
     ["identity.read", "only_if"]),
    ("answer changed", lambda: in_request({"id": "identity.take", "answer": "journey"}), ["identity.take", "answer"]),
    ("stringency changed", lambda: in_request({"id": "identity.take", "stringency": "low"}), ["identity.take", "stringency"]),
    ("the check of a gate changed", lambda: {"gates": [{"id": "identity.gate", "check": "facts_are_closed"}]},
     ["identity.gate", "check"]),
    ("an out whose enum list changes", lambda: in_request({"id": "identity.take", "out": {"verdict": ["go", "ask"]}}),
     ["identity.take", "verdict"]),
    ("an out whose enum list gains a member", lambda: in_request({"id": "identity.take", "out": {"verdict": ["go", "ask", "refuse", "stop"]}}),
     ["identity.take", "verdict"]),
    ("an out that drops a key", lambda: in_request({"id": "identity.enough", "out": {"enough": "bool"}}),
     ["identity.enough", "missing"]),
    ("an out that is null where the parent has keys", lambda: in_request({"id": "identity.enough", "out": None}),
     ["identity.enough"]),
    ("an out whose kind changes", lambda: in_request({"id": "identity.enough", "out": {"enough": "str", "missing": "list"}}),
     ["identity.enough", "enough"]),
    ("an out that is not an object", lambda: in_request({"id": "identity.enough", "out": ["enough"]}), ["identity.enough"]),
    ("an unknown field on an inherited step", lambda: in_request({"id": "identity.take", "colour": "red"}),
     ["identity.take", "colour"]),
    ("an unknown field on a new step", lambda: in_request(a_step(colour="red")), ["identity.note", "colour"]),
    ("a free field of the wrong kind", lambda: in_request({"id": "identity.take", "facts": "kind"}), ["identity.take", "facts"]),
    ("a new step missing its name", lambda: in_request(a_step(without=("name",))), ["identity.note", "name"]),
    ("a new step missing born", lambda: in_request(a_step(without=("born",))), ["identity.note", "born"]),
    ("a new step missing check", lambda: in_request(a_step(without=("check",))), ["identity.note", "check"]),
    ("a new step missing nature", lambda: in_request(a_step(without=("nature",))), ["identity.note", "nature"]),
    ("a new step with a nature outside NATURES", lambda: in_request(a_step(nature="ponder")), ["identity.note", "nature"]),
    ("a new step with a born outside RUNGS", lambda: in_request(a_step(born="C9")), ["identity.note", "born"]),
    ("a new step with a prompt and no draft",
     lambda: in_request(a_step(code=None, prompt="identity_take", out={"verdict": ["go"]})), ["identity.note", "draft"]),
    ("a new step with a prompt and no out",
     lambda: in_request(a_step(code=None, prompt="identity_take", draft="identity_take_draft")), ["identity.note", "out"]),
    ("a new step with neither code nor prompt", lambda: in_request(a_step(without=("code",))), ["identity.note", "code"]),
    ("a new step whose out is not an object", lambda: in_request(a_step(out=["verdict"])), ["identity.note", "out"]),
    ("a new step that takes an id another list uses", lambda: in_request(a_step(id="identity.gate")), ["identity.gate"]),
    ("a step of the gates named in the steps list", lambda: {"steps": [{"id": "identity.gate", "name": "Gate"}]}, ["identity.gate"]),
    ("a step named twice in one list", lambda: in_request(a_step(), a_step()), ["identity.note", "twice"]),
    ("a handler the parent lacks", lambda: in_handler("inform", "nothing", a_step()), ["inform/nothing"]),
    ("a handler with no when", lambda: {"on": [{"steps": [a_step()]}]}, ["when"]),
    ("a handler whose when is a text", lambda: {"on": [{"when": "request", "steps": []}]}, ["when"]),
    ("a handler whose msg_type is a list", lambda: {"on": [{"when": {"msg_type": ["request"], "word": "request"}, "steps": []}]},
     ["when", "msg_type", "each a word"]),
    ("a handler whose msg_type is a number", lambda: {"on": [{"when": {"msg_type": 7, "word": "request"}, "steps": []}]}, ["when"]),
    ("a handler whose word is an object", lambda: {"on": [{"when": {"msg_type": "request", "word": {"b": 1}}, "steps": []}]},
     ["when", "word", "each a word"]),
    ("a handler whose when has no msg_type", lambda: {"on": [{"when": {"word": "request"}, "steps": []}]}, ["when"]),
    ("a handler entry that carries more than when and steps",
     lambda: {"on": [{"when": {"msg_type": "request", "word": "request"}, "name": "Take it", "steps": []}]},
     ["request/request", "name"]),
    ("a handler entry that carries a start", lambda: {"on": [{"when": {"msg_type": "request", "word": "request"}, "start": {}}]},
     ["request/request", "start"]),
    ("a handler named twice", lambda: {"on": [{"when": {"msg_type": "request", "word": "request"}, "steps": []},
                                              {"when": {"msg_type": "request", "word": "request"}, "steps": []}]},
     ["request/request", "twice"]),
    ("an item with no id in a list", lambda: {"steps": [{"name": "Nameless"}]}, ["no id"]),
    ("an item with an empty id in a handler", lambda: in_request({"id": "", "name": "Nameless"}), ["no id"]),
    ("a handler item with no id", lambda: in_request({"name": "Nameless", "nature": "transform"}), ["no id"]),
]


@pytest.mark.parametrize("label,build,words", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_l2_a_malformed_patch_is_refused_in_words_that_name_the_step(label, build, words):
    text = refused(recipe("identity"), build(), *words)
    assert text and not any(c in text for c in "{}[]"), text      # plain words, never a dict or a list printed at the reader


@pytest.mark.parametrize("patch", [[], "a patch", 3, None, ("set",)], ids=["list", "string", "number", "none", "tuple"])
def test_l2_a_patch_that_is_not_an_object_is_refused(patch):
    text = refused(recipe("identity"), patch, "object")
    assert "identity" in text


def test_l2_a_parent_that_is_not_an_object_is_refused():
    with pytest.raises(L.ModelFault):
        L.merge_recipe(None, {}, "identity")
    with pytest.raises(L.ModelFault):
        L.merge_recipe([], {}, "identity")


def test_l2_the_same_refusals_hold_against_the_other_real_recipes():
    for layer in FUNCTION_LAYERS:
        r = recipe(layer)
        key = next(k for k in ("gates", "rules", "steps") if r.get(k))     # a list of this recipe that holds a step
        some = r[key][0]["id"]
        for patch in ({"set": {"start": {}}}, {"surprise": 1}, {key: [{"id": some, "nature": "no-such-nature"}]},
                      {"on": [{"when": {"msg_type": "inform", "word": "never-heard"}, "steps": []}]}):
            with pytest.raises(L.ModelFault):
                L.merge_recipe(r, patch, layer)
        # and a step of the first list can be renamed in place, whatever the layer
        got = merged(r, {key: [{"id": some, "name": "Renamed"}]}, layer)
        assert got[key][0]["name"] == "Renamed" and ids(L.all_steps(got)) == ids(L.all_steps(r))


# ---- L3 . recipe_faults ------------------------------------------------------------------------------------------------
def step_of(r, sid):
    return next(s for s in L.all_steps(r) if s["id"] == sid)


def the_one_fault(parent, child, *words):
    """Exactly one fault, a plain sentence that holds every word."""
    got = L.recipe_faults(parent, child, "coordination")
    assert len(got) == 1, got
    for w in words:
        assert w in got[0], "%r is not in %r" % (w, got[0])
    assert not any(c in got[0] for c in "{}[]"), got[0]
    return got[0]


@pytest.mark.parametrize("layer", FUNCTION_LAYERS)
def test_l3_a_recipe_is_a_child_of_itself_and_is_sound_alone(layer):
    r = recipe(layer)
    assert L.recipe_faults(r, r, layer) == []
    assert L.recipe_faults(r, copy.deepcopy(r), layer) == []
    assert L.recipe_faults(None, r, layer) == []


def test_l3_the_merges_of_l2_hold_the_law():
    ident, coord = recipe("identity"), recipe("coordination")
    assert L.recipe_faults(ident, merged(ident, fixture("identity.patch.json")), "identity") == []
    assert L.recipe_faults(coord, merged(coord, fixture("coordination.patch.json"), "coordination"), "coordination") == []
    assert L.recipe_faults(None, merged(ident, fixture("identity.patch.json")), "identity") == []


def test_l3_a_handler_removed_is_a_fault_and_a_handler_added_is_one():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["on"] = [h for h in child["on"] if L.handler_key(h) != ("inform", "born")]
    got = L.recipe_faults(parent, child, "coordination")
    assert got[0] == "the handler for inform/born is gone: a version hears what its parent hears"
    assert any("coord.table" in f for f in got[1:])               # its step is gone with it, said at the step
    child = copy.deepcopy(parent)
    child["on"].append({"name": "Hear a thing", "when": {"msg_type": "inform", "word": "thing"},
                        "steps": [{"id": "coord.thing", "name": "T", "nature": "transform", "born": "C2", "code": "coord_ready",
                                   "check": "said_what_it_did"}]})
    the_one_fault(parent, child, "inform/thing", "new")


def test_l3_a_step_removed_is_a_fault_that_names_it():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["steps"] = [s for s in child["steps"] if s["id"] != "coord.ready"]
    the_one_fault(parent, child, "coord.ready", "gone")
    child = copy.deepcopy(parent)
    child["on"][-1]["steps"] = []                                    # coord.table, the only step of its handler
    the_one_fault(parent, child, "coord.table", "gone")


@pytest.mark.parametrize("sid,field,value", [
    ("coord.ready", "nature", "decide"),
    ("coord.ready", "check", "said_what_it_did"),
    ("coord.tie", "answer", "why"),
    ("coord.tie", "stringency", "high"),
    ("coord.busy", "only_if", "coord.ready.later"),
    ("coord.tie", "each", "run"),
    ("coord.tie", "files", ["a.md"]),
    ("coord.tie", "by_hand", True),
    ("coord.tie", "or", {"cannot": "dict"}),
])
def test_l3_a_fixed_field_changed_is_a_fault_that_names_the_step_and_the_field(sid, field, value):
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    step_of(child, sid)[field] = value               # (an only_if here points at a step that exists: one fault, not two)
    the_one_fault(parent, child, sid, field)


def test_l3_a_fixed_field_deleted_is_a_fault_too():
    parent = recipe("identity")
    child = copy.deepcopy(parent)
    del step_of(child, "identity.take")["only_if"]
    the_one_fault(parent, child, "identity.take", "only_if")
    child = copy.deepcopy(parent)
    del step_of(child, "identity.take")["answer"]
    the_one_fault(parent, child, "identity.take", "answer")


def test_l3_an_out_key_removed_or_an_enum_changed_is_a_fault_and_a_key_added_is_not():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    del step_of(child, "coord.tie")["out"]["why"]
    the_one_fault(parent, child, "coord.tie", "why", "gone")
    child = copy.deepcopy(parent)
    step_of(child, "coord.tie")["out"]["note"] = "str"
    assert L.recipe_faults(parent, child, "coordination") == []
    parent = recipe("identity")
    child = copy.deepcopy(parent)
    step_of(child, "identity.take")["out"]["verdict"] = ["go", "ask"]
    the_one_fault(parent, child, "identity.take", "verdict")
    child = copy.deepcopy(parent)
    step_of(child, "identity.take")["out"]["verdict"] = ["refuse", "ask", "go"]      # the same members, another order
    assert L.recipe_faults(parent, child, "identity") == []
    child = copy.deepcopy(parent)
    step_of(child, "identity.enough")["out"]["enough"] = "str"
    the_one_fault(parent, child, "identity.enough", "enough")


def test_l3_a_gate_removed_or_a_rule_removed_is_a_fault_said_once():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["gates"] = []
    the_one_fault(parent, child, "coord.chain", "gate and rule")
    child = copy.deepcopy(parent)
    child["rules"] = [r for r in child["rules"] if r["id"] != "coord.busy"]
    the_one_fault(parent, child, "coord.busy", "gate and rule")


def test_l3_a_gate_that_is_moved_into_the_steps_is_no_longer_a_gate():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["steps"].insert(0, child["gates"].pop())
    the_one_fault(parent, child, "coord.chain", "gate or a rule")
    child = copy.deepcopy(parent)
    child["gates"].append(child["rules"].pop(0))                      # a rule that becomes a gate is still one of the two
    assert L.recipe_faults(parent, child, "coordination") == []


def test_l3_a_duplicate_id_is_a_fault_said_once_whatever_the_lists():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["steps"].append(copy.deepcopy(step_of(child, "coord.ready")))
    the_one_fault(parent, child, "coord.ready", "more than one")
    child = copy.deepcopy(parent)
    child["on"][0]["steps"].append(copy.deepcopy(child["gates"][0]))   # a handler step that reuses a gate's id
    child["on"][1]["steps"].append(copy.deepcopy(child["gates"][0]))   # and again
    the_one_fault(parent, child, "coord.chain", "more than one")


def test_l3_a_dangling_only_if_is_a_fault_that_names_the_step_and_its_target():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["steps"].append({"id": "coord.extra", "name": "E", "nature": "transform", "born": "C2", "code": "coord_ready",
                           "check": "said_what_it_did", "only_if": "coord.nowhere.answer=yes"})
    the_one_fault(parent, child, "coord.extra", "coord.nowhere", "no step")
    child = copy.deepcopy(parent)
    child["steps"][-1]["only_if"] = "coord.ready.later"              # a target that is a step: sound
    child["steps"][-1]["id"] = "coord.record"
    assert [f for f in L.recipe_faults(parent, child, "coordination") if "no step" in f] == []


def test_l3_a_removed_step_that_another_step_reads_is_two_faults_in_the_order_of_the_checks():
    parent = recipe("identity")
    child = copy.deepcopy(parent)
    handler(child, "request", "request")["steps"] = [s for s in handler(child, "request", "request")["steps"]
                                                       if s["id"] != "identity.recognise"]
    got = L.recipe_faults(parent, child, "identity")
    assert "identity.recognise" in got[0] and "gone" in got[0]
    assert any("identity.take" in f and "identity.recognise" in f and "no step" in f for f in got[1:])


def test_l3_the_faults_come_in_the_order_the_checks_run():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["on"] = [h for h in child["on"] if L.handler_key(h) != ("inform", "born")]             # 1, and 2 for coord.table
    child["steps"] = [s for s in child["steps"] if s["id"] != "coord.record"]                    # 2
    step_of(child, "coord.tie")["check"] = "said_what_it_did"                                    # 3
    del step_of(child, "coord.tie")["out"]["why"]                                                # 3
    child["steps"].insert(0, child["gates"].pop())                                               # 4
    child["steps"].append(copy.deepcopy(step_of(child, "coord.ready")))                          # 5
    child["steps"].append({"id": "coord.extra", "name": "E", "nature": "transform", "born": "C2", "code": "coord_ready",
                           "check": "said_what_it_did", "only_if": "coord.nowhere.answer=yes"})  # 6
    got = L.recipe_faults(parent, child, "coordination")
    # a missing step is said in the parent's order: its steps, then each handler's
    marks = ["is gone: a version hears", "coord.record: a version keeps every step", "coord.table: a version keeps every step",
             "coord.tie: check", "coord.tie: the out key why", "coord.chain: a gate or a rule", "coord.ready: this id is used",
             "coord.extra: only_if"]
    at = [next(i for i, f in enumerate(got) if m in f) for m in marks]
    assert at == sorted(at) and len(set(at)) == len(marks), (at, got)
    assert len(got) == len(marks), got


def test_l3_with_no_parent_only_the_childs_own_soundness_is_judged():
    r = recipe("coordination")
    assert L.recipe_faults(None, r, "coordination") == []
    dup = copy.deepcopy(r)
    dup["steps"].append(copy.deepcopy(dup["rules"][0]))
    the_one_fault(None, dup, "coord.busy", "more than one")
    dangling = copy.deepcopy(r)
    step_of(dangling, "coord.tie")["only_if"] = "coord.gone.answer=1"
    the_one_fault(None, dangling, "coord.tie", "coord.gone")
    # no handler, step or gate is missed when there is nothing to miss them against
    gutted = {"kind": "function", "steps": []}
    assert L.recipe_faults(None, gutted, "coordination") == []


def test_l3_a_recipe_that_is_not_in_shape_is_a_fault_not_an_exception():
    parent = recipe("coordination")
    assert L.recipe_faults(parent, None, "coordination") == ["the recipe is not an object"]
    assert L.recipe_faults(parent, [], "coordination") == ["the recipe is not an object"]
    assert L.recipe_faults([], parent, "coordination") == ["the parent's recipe is not an object"]
    child = copy.deepcopy(parent)
    child["steps"] = "none"
    child["gates"].append("not a step")
    child["rules"].append({"name": "A rule with no id"})
    got = L.recipe_faults(parent, child, "coordination")
    assert any("no id" in f and "A rule with no id" in f for f in got)
    assert any("coord.ready" in f and "gone" in f for f in got)
    assert any("the steps are not a list" in f and "a text" in f for f in got)
    assert any("the gates hold an item that is not a step" in f and "a text" in f for f in got)
    # an item that is not an object is a fault whatever the parent, and so is a handler that says nothing of what it hears
    got = L.recipe_faults(None, {"on": [None, {"steps": [None]}]}, "coordination")
    assert got == ["the handlers hold an item that is not a handler (it is nothing)",
                   "the handler number 2 does not say what it hears: its when is nothing, not an object with a msg_type and "
                   "a word",
                   "the steps of the handler number 2 hold an item that is not a step (it is nothing)"]


NOT_OBJECTS = [("a text", "not a step"), ("nothing", None), ("a number", 7), ("a number", 1.5), ("a yes or no", True),
               ("a list", ["a"]), ("a list", [])]
SECTIONS = [("the gates hold", lambda r: r["gates"]), ("the rules hold", lambda r: r["rules"]),
            ("the steps hold", lambda r: r["steps"]),
            ("the steps of the handler for inform/born hold", lambda r: handler(r, "inform", "born")["steps"])]


@pytest.mark.parametrize("has_parent", [True, False], ids=["with a parent", "alone"])
@pytest.mark.parametrize("kind,item", NOT_OBJECTS, ids=["%s %r" % (k, i) for k, i in NOT_OBJECTS])
@pytest.mark.parametrize("who,where", SECTIONS, ids=[w[0] for w in SECTIONS])
def test_l3_an_item_that_is_not_an_object_is_a_fault_in_every_list_a_recipe_has(who, where, kind, item, has_parent):
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    where(child).append(copy.deepcopy(item))
    where(child).insert(0, copy.deepcopy(item))
    got = L.recipe_faults(parent if has_parent else None, child, "coordination")
    want = "%s an item that is not a step (it is %s)" % (who, kind)
    assert got == [want, want], got                       # said for each item, and nothing else is wrong with the recipe
    assert not any(c in got[0] for c in "{}[]"), got[0]


def test_l3_an_object_for_a_step_with_no_id_is_still_the_no_id_fault_and_not_the_not_a_step_one():
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child["gates"].append({})
    child["steps"].append({"name": "Nameless"})
    got = L.recipe_faults(parent, child, "coordination")
    assert got == ["a step has no id: it has no name either", "a step has no id: Nameless"], got


@pytest.mark.parametrize("bad", [["a"], {"a": 1}, [], {}, 7, 1.5, True], ids=repr)
def test_l3_an_id_that_is_not_a_word_is_a_fault_not_an_exception(bad):
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    step_of(child, "coord.ready")["id"] = bad
    got = L.recipe_faults(parent, child, "coordination")
    assert any("coord.ready" in f and "gone" in f for f in got), got
    if bad in ([], {}):                                    # empty is no id at all, any other kind is an id that is no word
        assert any(f.startswith("a step has no id: ") for f in got), got
    else:
        assert any(f.startswith("a step has no id that is a word: ") for f in got), got
    assert not any(c in f for f in got for c in "{}[]"), got
    got = L.recipe_faults(None, child, "coordination")
    assert len(got) == 1 and got[0].startswith("a step has no id") and "coord.ready" not in got[0], got
    assert L.step_ids(child) == [i for i in L.step_ids(parent) if i != "coord.ready"]
    two = copy.deepcopy(parent)
    step_of(two, "coord.ready")["id"] = bad
    step_of(two, "coord.record")["id"] = bad               # two steps with the same unhashable id: no id, twice, not a clash
    assert len([f for f in L.recipe_faults(None, two, "coordination") if f.startswith("a step has no id")]) == 2


def test_l3_the_duplicate_check_and_the_by_id_map_see_words_only():
    r = {"gates": [{"id": ["a"], "name": "G"}], "steps": [{"id": "x", "name": "S"}, {"id": "x", "name": "T"}, {"id": 5}]}
    assert L.step_ids(r) == ["x", "x"]
    got = L.recipe_faults(None, r, "coordination")
    assert got == ["a step has no id that is a word: G", "x: this id is used by more than one step",
                   "a step has no id that is a word: it has no name either"], got


@pytest.mark.parametrize("when,kind", [("inform", "a text"), (["inform", "born"], "a list"), (7, "a number"), (None, "nothing"),
                                       (True, "a yes or no"), ([], "a list"), ("", "a text")], ids=repr)
def test_l3_a_handler_whose_when_is_not_an_object_is_a_fault_and_not_a_key(when, kind):
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    h = handler(child, "inform", "born")
    h["when"] = when
    got = L.recipe_faults(parent, child, "coordination")
    assert got[0] == ("the handler %s does not say what it hears: its when is %s, not an object with a msg_type and a word"
                      % (h["name"], kind)), got
    assert "the handler for inform/born is gone: a version hears what its parent hears" in got
    assert not any("is new" in f for f in got), got        # the handler that says nothing is not also a new one
    assert L.recipe_faults(None, child, "coordination") == [got[0]]       # alone: the one fault, and no exception


def test_l3_a_handler_that_says_nothing_of_its_message_or_its_word_is_a_fault_not_an_exception():
    parent = recipe("coordination")
    for when, mark in [({"word": "born"}, "msg_type"), ({"msg_type": "", "word": "born"}, "msg_type"),
                       ({"msg_type": ["inform"], "word": "born"}, "msg_type"), ({"msg_type": {"x": 1}}, "msg_type"),
                       ({"msg_type": 7, "word": "born"}, "msg_type"), ({"msg_type": "inform", "word": ["born"]}, "word"),
                       ({"msg_type": "inform", "word": 7}, "word"), ({"msg_type": "inform", "word": {"b": 1}}, "word")]:
        child = copy.deepcopy(parent)
        handler(child, "inform", "born")["when"] = when
        got = L.recipe_faults(parent, child, "coordination")
        assert got[0].startswith("the handler ") and "does not say what it hears" in got[0] and mark in got[0], (when, got)
        assert "the handler for inform/born is gone: a version hears what its parent hears" in got, (when, got)
        assert not any(c in f for f in got for c in "{}[]"), (when, got)
        assert L.recipe_faults(None, child, "coordination") == [got[0]]


def test_l3_a_handler_with_no_when_at_all_is_named_by_its_name_or_its_number():
    child = copy.deepcopy(recipe("coordination"))
    h = handler(child, "inform", "born")
    del h["when"]
    say = "the handler %s does not say what it hears: its when is nothing, not an object with a msg_type and a word"
    assert L.recipe_faults(None, child, "coordination") == [say % h["name"]]
    del h["name"]
    n = next(i for i, x in enumerate(child["on"], 1) if x is h)
    assert L.recipe_faults(None, child, "coordination") == [say % ("number %d" % n)]


@pytest.mark.parametrize("key,words", [("gates", "the gates"), ("rules", "the rules"), ("steps", "the steps"),
                                       ("on", "the handlers")])
@pytest.mark.parametrize("bad,kind", [("none", "a text"), (7, "a number"), (True, "a yes or no"), ({"id": "x"}, "an object")])
def test_l3_a_part_that_is_not_a_list_is_a_fault_and_nothing_at_all_is_not(key, words, bad, kind):
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    child[key] = bad
    got = L.recipe_faults(parent, child, "coordination")
    assert got[0] == "%s are not a list (they are %s)" % (words, kind), got
    alone = L.recipe_faults(None, child, "coordination")
    assert alone[0] == got[0] and len(alone) == 1, alone
    child[key] = None                                       # a key set to null is the same as a key left out: no shape fault
    assert not [f for f in L.recipe_faults(None, child, "coordination") if "not a list" in f]
    del child[key]
    assert not [f for f in L.recipe_faults(None, child, "coordination") if "not a list" in f]


@pytest.mark.parametrize("bad,kind", [("none", "a text"), (7, "a number"), ({"id": "x"}, "an object")])
def test_l3_the_steps_of_a_handler_that_are_not_a_list_are_a_fault(bad, kind):
    parent = recipe("coordination")
    child = copy.deepcopy(parent)
    handler(child, "inform", "born")["steps"] = bad
    got = L.recipe_faults(parent, child, "coordination")
    assert got[0] == "the steps of the handler for inform/born are not a list (they are %s)" % kind, got
    assert any("coord.table" in f and "gone" in f for f in got[1:]), got      # its step is gone with them, said at the step


def test_l3_an_only_if_of_another_kind_is_read_as_its_text_and_points_nowhere():
    parent = recipe("coordination")
    for bad in (["coord.ready.later"], 7, {"a": 1}, True):
        child = copy.deepcopy(parent)
        step_of(child, "coord.busy")["only_if"] = bad
        got = L.recipe_faults(parent, child, "coordination")
        assert any(f.startswith("coord.busy: only_if points at") for f in got), (bad, got)


def test_l3_handler_key_is_total_and_always_a_key():
    for h in (None, "x", 7, [], ["when"], {}, {"when": None}, {"when": "inform"}, {"when": []}, {"when": 7}):
        assert L.handler_key(h) == (None, S.ANY), h
    assert L.handler_key({"when": {"msg_type": ["inform"], "word": {"b": 1}}}) == ("['inform']", "{'b': 1}")
    assert L.handler_key({"when": {"msg_type": "inform", "word": ""}}) == ("inform", S.ANY)
    for h in ({"when": {"msg_type": ["a"], "word": ["b"]}}, {"when": {"msg_type": {"a": 1}}}, {"when": "x"}, "x"):
        hash(L.handler_key(h))                              # usable in a set, whatever the recipe holds


JUNK = [None, "text", "", 7, 0, 1.5, True, False, [], ["a"], [None], {}, {"x": 1}, [[]], ["born"]]


def junk_paths(x, p=()):
    yield p
    for k, v in (x.items() if isinstance(x, dict) else enumerate(x) if isinstance(x, list) else ()):
        yield from junk_paths(v, p + (k,))


def junked(r, rng):
    """r with one to three of its parts replaced by, or joined by, a value of another kind: the recipes a careless author writes."""
    r = copy.deepcopy(r)
    for _ in range(rng.choice([1, 1, 2, 3])):
        p = rng.choice([q for q in junk_paths(r) if q])
        holder = r
        for k in p[:-1]:
            holder = holder[k]
        op = rng.random()
        if op < 0.7:
            holder[p[-1]] = copy.deepcopy(rng.choice(JUNK))
        elif isinstance(holder, list):
            holder.insert(rng.randrange(len(holder) + 1), copy.deepcopy(rng.choice(JUNK)))
        else:
            holder.pop(p[-1], None)
    return r


def test_l3_recipe_faults_never_raises_whatever_a_recipe_holds():
    """A2.7: the contract cases that call recipe_faults never raise on a stub. 1500 recipes made from the five real ones, a part
    or three of each replaced by, or joined by, a value of another kind, judged against the real parent, against a damaged
    parent and alone: a list of sentences each time. The seed is fixed, so a failure is the same failure on every run."""
    import random
    rng = random.Random(20260427)
    recipes = {layer: recipe(layer) for layer in FUNCTION_LAYERS}
    for n in range(1500):
        layer = rng.choice(FUNCTION_LAYERS)
        parent = recipes[layer]
        child = junked(parent, rng)
        for against in (parent, junked(parent, rng), None):
            got = L.recipe_faults(against, child, layer)
            assert isinstance(got, list) and all(isinstance(f, str) and f for f in got), (n, layer)


def test_l3_a_handler_whose_when_has_no_word_hears_any():
    parent = recipe("identity")
    child = copy.deepcopy(parent)
    assert any(h["when"].get("word") is None for h in child["on"])      # accept-proposal and reject-proposal hear any word
    assert L.recipe_faults(parent, child, "identity") == []
    child["on"] = [h for h in child["on"] if L.handler_key(h) != ("accept-proposal", S.ANY)]
    assert L.recipe_faults(parent, child, "identity")[0].startswith("the handler for accept-proposal/%s is gone" % S.ANY)


# ---- L4 . gate ranking -------------------------------------------------------------------------------------------------
def says(answer):
    """A gate body that always answers `answer` as (answer, why), the shape engine_runtime's gate bodies return."""
    return lambda ctx, step, item: (answer, None if answer == "admit" else "because")


def says_as_dict(answer):
    return lambda ctx, step, item: {"answer": answer, "why": "because"}


CONTEXT = ({"ref": "r"}, {"id": "s"}, None)


def test_l4_rank_is_admit_then_wait_then_refuse():
    assert [L.rank(a) for a in ("admit", "wait", "refuse")] == [0, 1, 2]
    assert L.rank("admit") < L.rank("wait") < L.rank("refuse")
    assert [L.GATE_ORDER[L.rank(a)] for a in L.GATE_ORDER] == list(L.GATE_ORDER)


@pytest.mark.parametrize("answer", ["allow", "", "ADMIT", None, 0, 1, True, ["admit"], {"answer": "admit"}, ("admit",), b"admit"])
def test_l4_rank_raises_value_error_for_anything_else(answer):
    with pytest.raises(ValueError):
        L.rank(answer)


@pytest.mark.parametrize("make", [says, says_as_dict], ids=["tuple", "dict"])
def test_l4_tightens_is_empty_for_a_child_that_answers_the_same_or_stricter(make):
    contexts = [CONTEXT, CONTEXT, CONTEXT]
    for parent in ("admit", "wait", "refuse"):
        for child in L.GATE_ORDER[L.rank(parent):]:
            assert L.tightens(make(parent), make(child), contexts) == [], (parent, child)
    assert L.tightens(says("admit"), says("admit"), []) == []


@pytest.mark.parametrize("parent_make", [says, says_as_dict], ids=["parent tuple", "parent dict"])
@pytest.mark.parametrize("child_make", [says, says_as_dict], ids=["child tuple", "child dict"])
def test_l4_tightens_names_the_context_where_the_child_lets_through_what_the_parent_held_back(parent_make, child_make):
    got = L.tightens(parent_make("wait"), child_make("admit"), [CONTEXT])
    assert len(got) == 1 and "context 0" in got[0] and "admit" in got[0] and "wait" in got[0]
    got = L.tightens(parent_make("refuse"), child_make("wait"), [CONTEXT])
    assert len(got) == 1 and "context 0" in got[0] and "wait" in got[0] and "refuse" in got[0]
    got = L.tightens(parent_make("refuse"), child_make("admit"), [CONTEXT])
    assert len(got) == 1 and "context 0" in got[0]


def test_l4_tightens_calls_both_bodies_with_each_context_and_names_only_the_contexts_that_fail():
    seen = []

    def parent(ctx, step, item):
        seen.append(("parent", ctx, step, item))
        return ("wait", "x") if ctx["n"] % 2 else ("admit", None)

    def child(ctx, step, item):
        seen.append(("child", ctx, step, item))
        return ("admit", None)

    contexts = [({"n": n}, "step", "item%d" % n) for n in range(4)]
    got = L.tightens(parent, child, contexts)
    assert len(got) == 2 and "context 1" in got[0] and "context 3" in got[1]
    assert [s[0] for s in seen] == ["parent", "child"] * 4
    assert [s[1:] for s in seen if s[0] == "child"] == [c for c in contexts]


def test_l4_tightens_lets_a_bad_answer_or_shape_raise_for_the_author_to_see():
    with pytest.raises(ValueError):
        L.tightens(says("admit"), lambda *a: ("maybe", "x"), [CONTEXT])
    with pytest.raises(ValueError):
        L.tightens(lambda *a: None, says("admit"), [CONTEXT])
    with pytest.raises(ValueError):
        L.tightens(says("admit"), lambda *a: "admit", [CONTEXT])
    with pytest.raises(KeyError):
        L.tightens(says("admit"), lambda *a: {}["nothing"], [CONTEXT])


def test_l4_the_real_identity_gate_answers_in_the_shape_tightens_reads():
    """engine_runtime.identity_gate on a context that is cheap to build (an engine whose artifact stays in the record): it admits,
    as (answer, why)."""
    ctx = {"ref": "r", "engine": "Plan", "slot": "s", "inp": {"v": 1}, "def": {}, "dept": {}}
    assert R.identity_gate(ctx, {"id": "identity.gate"}, None) == ("admit", None)
    contexts = [(ctx, {"id": "identity.gate"}, None)]
    assert L.tightens(R.identity_gate, says("wait"), contexts) == []                     # a stricter replacement
    assert L.tightens(R.identity_gate, R.identity_gate, contexts) == []
    got = L.tightens(says("wait"), R.identity_gate, contexts)                              # a laxer one
    assert len(got) == 1 and "context 0" in got[0]


# ---- L5 . the classification test and the hygiene test -----------------------------------------------------------------
RECIPE_FILE = re.compile(r"^v[1-9][0-9]*\.json$")
PATCH_FILE = re.compile(r"^v[1-9][0-9]*\.patch\.json$")
RECIPE_KEYS = ("kind", "description", "skills", "start", "gates", "rules", "on", "steps", "reads", "template")
HANDLER_FIELDS = ("name", "when", "steps")
CLASSIFY = ("classify it in layers/lineage.py: fixed (the parent's value holds) or free (a child may change it)")


def recipe_files(layers_dir=LAYERS):
    return sorted(p for p in layers_dir.glob("*/v*.json") if RECIPE_FILE.match(p.name))


def patch_files(layers_dir=LAYERS):
    return sorted(p for p in layers_dir.glob("*/v*.json") if PATCH_FILE.match(p.name))


def classification_problems(layers_dir):
    """Every key of every recipe under layers_dir that the law has not classified, one sentence each."""
    problems = []
    for path in recipe_files(layers_dir):
        where = "%s/%s" % (path.parent.name, path.name)
        r = json.loads(path.read_text(encoding="utf-8"))
        for key in r:
            if key not in RECIPE_KEYS:
                problems.append("%s: the recipe key %s is none of %s" % (where, key, ", ".join(RECIPE_KEYS)))
        for h in r.get("on") or []:
            for key in h:
                if key not in HANDLER_FIELDS:
                    problems.append("%s: the handler %s holds %s, and a handler holds %s only"
                                    % (where, h.get("name") or h.get("when"), key, ", ".join(HANDLER_FIELDS)))
        for s in L.all_steps(r):
            for key in s:
                if key not in L.STEP_FIELDS:
                    problems.append("%s: the step %s holds %s, which is in neither list: %s" % (where, s.get("id"), key, CLASSIFY))
    return problems


def test_l5_the_two_lists_of_step_fields_do_not_overlap_and_cover_every_field():
    assert not set(L.STEP_FIXED) & set(L.STEP_FREE)
    assert "id" not in L.STEP_FIXED and "id" not in L.STEP_FREE
    assert len(set(L.STEP_FIELDS)) == len(L.STEP_FIELDS) == 1 + len(L.STEP_FIXED) + len(L.STEP_FREE)
    assert not set(L.POSITION) & set(L.STEP_FIELDS)


def test_every_step_field_of_every_recipe_is_classified():
    files = recipe_files()
    assert len(files) >= len(FUNCTION_LAYERS), "the five function recipes are on disk; the scan found %s" % [p.name for p in files]
    problems = classification_problems(LAYERS)
    assert not problems, "\n".join(problems)


def test_l5_every_patch_on_disk_holds_the_patch_grammar():
    """A patch beside a version (layers/<layer>/v<N>.patch.json, A2-INHERIT's) is held to the same two lists, and to the keys a
    patch may hold. None is on disk until a child version is written; the scan is then the whole check."""
    problems = []
    for path in patch_files():
        where = "%s/%s" % (path.parent.name, path.name)
        p = json.loads(path.read_text(encoding="utf-8"))
        problems += ["%s: the patch key %s is none of %s" % (where, k, ", ".join(L.PATCH_KEYS)) for k in p if k not in L.PATCH_KEYS]
        lists = [p.get(k) or [] for k in ("gates", "rules", "steps")] + [h.get("steps") or [] for h in p.get("on") or []]
        for h in p.get("on") or []:
            problems += ["%s: the handler entry %s holds %s, and a patch holds when and steps only" % (where, h.get("when"), k)
                         for k in h if k not in ("when", "steps")]
        for items in lists:
            for s in items:
                problems += ["%s: the step %s holds %s, which is in neither list: %s" % (where, s.get("id"), k, CLASSIFY)
                             for k in s if k not in L.STEP_FIELDS and k not in L.POSITION]
    assert not problems, "\n".join(problems)


def test_the_classification_scan_finds_a_field_in_neither_list(tmp_path):
    """The scan is not vacuous: a step with a new field, a handler with a new key and a recipe with a new key are each found,
    and the message says how to classify the field."""
    fake = tmp_path / "coordination"
    fake.mkdir()
    r = recipe("coordination")
    r["steps"][0]["glow"] = True
    r["on"][0]["colour"] = "red"
    r["surprise"] = 1
    (fake / "v1.json").write_text(json.dumps(r), encoding="utf-8")
    got = classification_problems(tmp_path)
    assert len(got) == 3, got
    assert any("glow" in p and CLASSIFY in p for p in got)
    assert any("colour" in p for p in got) and any("surprise" in p for p in got)
    assert classification_problems(LAYERS) == []


FORBIDDEN_AT_IMPORT = ("engine_runtime", "website_dept", "j2_runtime", "functions_view", "layer_schema")


def imports_at_import_time(tree):
    """The import statements that run when the module is imported: the module's own, and those under an if, a try, a with or a
    class body; not those inside a function, which run only when it is called."""
    found = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                found.append(child)
            else:
                walk(child)

    walk(tree)
    return found


def forbidden_names(node):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_AT_IMPORT]
    named = [node.module] if node.module and node.module.split(".")[0] in FORBIDDEN_AT_IMPORT else []
    return named + [a.name for a in node.names if a.name in FORBIDDEN_AT_IMPORT]


def test_lineage_imports_nothing_from_the_runtime_at_import_time():
    tree = ast.parse((LAYERS / "lineage.py").read_text(encoding="utf-8"))
    top = imports_at_import_time(tree)
    assert top, "the scan found no import in layers/lineage.py"
    assert not [n for n in top if forbidden_names(n)], "layers/lineage.py imports the runtime when it is imported"
    # what it does import is the standard library and the lazy proxies of the layers package
    assert {a.name for n in top if isinstance(n, ast.ImportFrom) and n.module == "layers" for a in n.names} >= {"R", "S"}
    assert {a.name for n in top if isinstance(n, ast.Import) for a in n.names} <= {"copy"}


def test_the_import_scan_sees_what_it_is_meant_to_see():
    tree = ast.parse("import json\nimport engine_runtime\nfrom website_dept import x\nfrom layers import j2_runtime\n"
                     "try:\n    import functions_view\nexcept ImportError:\n    pass\nif True:\n    from layer_schema import SCHEMA\n"
                     "def f():\n    import engine_runtime as inner\nclass C:\n    import j2_runtime\n"
                     "    def g(self):\n        import website_dept\n")
    named = [forbidden_names(n) for n in imports_at_import_time(tree)]
    assert [x for x in named if x] == [["engine_runtime"], ["website_dept"], ["j2_runtime"], ["functions_view"], ["layer_schema"],
                                      ["j2_runtime"]]
    assert len(named) == 7                                                # json too; the two inside functions are not counted


def test_lineage_imports_without_the_runtime_present():
    """The same law, run: import the module in a fresh interpreter in which every runtime module refuses to import, and use the
    functions that need none. (A new step checked reaches engine_runtime, and handler_key reaches layer_schema: both when called.)"""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "for m in %r: sys.modules[m] = None\n"
        "from layers import lineage as L\n"
        "assert L.rank('wait') == 1\n"
        "assert L.merge_words({'a': {'b': {'c': 1}}}, {'a': {'b': {'d': 2}}}) == {'a': {'b': {'c': 1, 'd': 2}}}\n"
        "assert L.merge_layout(None, {'a': {'b': 'x'}}) == {'a': {'b': 'x'}}\n"
        "assert L.recipe_faults(None, {'steps': []}, 'identity') == []\n"
        "assert L.merge_recipe({'description': 'd'}, {'set': {'description': 'e'}}, 'identity') == {'description': 'e'}\n"
        "print('ok')\n" % (str(HERE), list(FORBIDDEN_AT_IMPORT)))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(HERE), timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr[-2000:]
