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


def test_the_names_the_inheritance_codes_against():
    assert L.PATCH_KEYS == ("parent", "set", "gates", "rules", "steps", "on")
    assert L.TOP_SET == ("description", "skills") and L.POSITION == ("after", "before")
    assert L.STEP_FIXED == ("nature", "check", "answer", "out", "or", "only_if", "stringency", "each", "files", "by_hand")
    assert L.STEP_FREE == ("name", "born", "code", "prompt", "draft", "ceiling", "facts", "tools", "timeout_s", "below")
    assert L.STEP_FIELDS == ("id",) + L.STEP_FIXED + L.STEP_FREE
    assert L.GATE_ORDER == ("admit", "wait", "refuse")
    assert L.handler_key({"when": {"msg_type": "inform", "word": "born"}}) == ("inform", "born")
    assert L.handler_key({"when": {"msg_type": "accept-proposal"}}) == ("accept-proposal", S.ANY)
    assert L.only_if_target("adapt.source.source=library") == "adapt.source"
    assert L.only_if_target("identity.read.later") == "identity.read"


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
