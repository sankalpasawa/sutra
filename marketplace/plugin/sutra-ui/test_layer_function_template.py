"""The function template in the five layers (PRD amendment A3, A3-FUNCTIONS; A3.4), one section a step.

  F1  the parts and the words: each function's goal group holds done, role_is, role_may, role_procedure, role_patterns and
      the role block, as parts the interface lists (S.ADDED_PARTS), with their words and layout in the version
  F2  Adaptation's own goal is the site's, in the six places it lives
  F3  contract case 14 (FT-1 to FT-6, FT-9, FT-10) and the field rule of FT-9
  F4  the role block in the card of a function engine, and nowhere else
  F5  the picked template's whole floor reaches the card
  F6  the pane reads the typed goal, and done is a proposal until the owner marks it
  F7  every rule of the five official role files has a home, and the two records kept equal
  F8  the comparison script
  F9  the README lists what the card reads

The departments here are born the way the layer tests' are, on a records home of their own, offline: no test reaches a model,
the live records home or the network.
"""
import importlib
import re

import pytest

import layer_schema as S
import layers
import layers.contract as C

FUNCTIONS = S.FUNCTION_LAYERS
#: the parts this package adds to the goal group of each function, with what each holds
ROLE_PARTS = ("done", "role_is", "role_may", "role_procedure", "role_patterns", "role_block")
TEXT_PARTS = ("done", "role_is")
ITEM_PARTS = ("role_may", "role_procedure", "role_patterns")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return tmp_path


@pytest.fixture
def rt(home):
    """The runtime reloaded on a records home of its own, and a department made with W.create (no model, no run)."""
    import website_dept as W
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as FV
    for module in (W, R, J, FV):
        importlib.reload(module)
    ref = "dref-ftemplate01"
    W.create(ref, "Thread & Loom Website", None)
    return W, R, J, FV, ref


def module_of(fn):
    return layers.load(S.DEFAULT_PINS[fn])


# ---- F1: the parts and the words -------------------------------------------------------------------------------------
@pytest.mark.parametrize("fn", FUNCTIONS)
def test_ft2_every_word_part_is_present_and_within_its_limit(fn):
    """FT-2, FT-3, FT-5, FT-6: every version supplies the typed words of the template within their limits, and a layout of
    the role block that places all eight inputs."""
    m = module_of(fn)
    parts = S.PROMPTS[fn]["goal"]
    for part in ROLE_PARTS:
        assert part in parts and (fn, "goal", part) in S.ADDED_PARTS, "%s: goal.%s is an added part of the interface" % (fn, part)
        assert part in m.WORDS["goal"] and part in m.LAYOUT["goal"], "%s/v1 holds the words and the layout of goal.%s" % (fn, part)
    for part in TEXT_PARTS:
        text = m.WORDS["goal"][part]["text"]
        assert 0 < len(text) <= 400 and "\n" not in text, "%s: goal.%s is one clause of at most 400 characters" % (fn, part)
        assert m.LAYOUT["goal"][part] == "{text}"
        assert S.validate_field(fn, "goal", part, "text", text) == []
    for part in ITEM_PARTS:
        lines = m.WORDS["goal"][part]["items"]
        assert 1 <= len(lines) <= 12 and all(0 < len(x) <= 160 and "\n" not in x for x in lines), "%s: goal.%s" % (fn, part)
        assert m.LAYOUT["goal"][part] == "{items}"
        assert S.validate_field(fn, "goal", part, "items", lines) == []
    assert m.WORDS["goal"]["role_block"] == {} and m.LAYOUT["goal"]["role_block"] == S.ROLE_BLOCK_LAYOUT
    assert set(re.findall(r"\{\{([a-z_]+)\}\}", S.ROLE_BLOCK_LAYOUT)) == set(S.ROLE_INPUTS) == set(parts["role_block"]["inputs"])
    assert parts["role_block"]["fields"] == {} and parts["role_block"]["returns"] is None
    assert C.case_5(m, {}) == [], "the contract compiles every new part with sample inputs"
    assert [p for p in C.on_the_md_fallback(m) if p.split(".")[1] in ROLE_PARTS] == [], "an added part has no .md to fall back to"


def test_a_role_may_of_thirteen_lines_and_a_two_line_done_are_refused():
    """The failing examples of FT-2 and FT-6: the interface names the part and says what is wrong."""
    thirteen = ["rule on one thing number %d" % i for i in range(13)]
    got = S.validate_field("identity", "goal", "role_may", "items", thirteen)
    assert got and "more than 12 items" in got[0]
    two_lines = "every request has a verdict.\nEvery effect has a gate answer."
    got = S.validate_field("audit", "goal", "done", "text", two_lines)
    assert got and "line break" in got[0]
    assert S.validate_field("priority", "goal", "role_is", "text", "x" * 401)[0].startswith("$: longer than 400")
    assert S.validate_field("coordination", "goal", "role_block", "text", "x"), "the role block has no field the owner may change"
    # and the contract catches a version whose words break them, naming the part
    module = types_module("identity", WORDS={"goal": {"role_may": {"items": thirteen}}}, LAYOUT={"goal": {"role_may": "{items}"}})
    assert any("goal.role_may.items" in f and "more than 12 items" in f for f in C.case_5(module, {}))


def types_module(layer, **more):
    """A stub version, as the contract's tests make them: a namespace with the attributes a version has."""
    import types
    base = {"__file__": "/nowhere/layers/%s/v1.py" % layer, "LAYER": layer, "VERSION": 1, "IMPLEMENTS": 1, "RECIPE": "v1.json",
            "CODE": {}, "PROMPT": {}, "DRAFT": {}, "CHECK": {}, "WORDS": {}, "LAYOUT": {}}
    base.update(more)
    return types.SimpleNamespace(**base)


def test_the_instructions_view_lists_the_six_new_parts_in_the_goal_group(rt):
    """S16 is derived from S.PROMPTS: the owner finds the new parts in the group goal of each function."""
    W, R, J, FV, ref = rt
    for fn in FUNCTIONS:
        group = next(g for g in R.instructions_view(ref, fn) if g["group"] == "goal")
        names = [p["part"] for p in group["parts"]]
        assert names[:2] == ["does", "skills"] and all(part in names for part in ROLE_PARTS), fn
        done = next(p for p in group["parts"] if p["part"] == "done")
        assert [f["field"] for f in done["fields"]] == ["text"] and done["fields"][0]["value"] == module_of(fn).WORDS["goal"]["done"]["text"]
        block = next(p for p in group["parts"] if p["part"] == "role_block")
        assert block["fields"] == [] and len(block["inputs"]) == 8


# ---- F2: Adaptation's goal ---------------------------------------------------------------------------------------------
HERE = __import__("pathlib").Path(__file__).parent
SITE_GOAL = ("decides how the department reaches its goal and keeps changing how as it learns: it proposes the workflows the goal "
             "needs, from the Library or shaped fresh, and a step's move up or down the ladder")


def test_adaptations_goal_is_the_sites_and_the_six_places_agree(rt):
    """The goal is the site's ('decide how the department reaches its goal, and keep changing how as it learns'), at most 400
    characters, promising nothing unbuilt; the recipe's description, the typed words, the .md file, the fixture of the
    definitions, the test that held the old text and the prompt snapshot hold the same text (A1 requires the first two equal)."""
    import json
    W, R, J, FV, ref = rt
    typed = module_of("adaptation").WORDS["goal"]["does"]["text"]
    assert typed.startswith("decides how the department reaches its goal") and len(typed) <= 400 and "\n" not in typed
    assert typed == SITE_GOAL
    assert not re.search(S.TEMPLATE_BANNED, typed, re.I), "the goal is read on the pane: the screen's words"
    places = {
        "the recipe's description": json.loads((HERE / "layers/adaptation/v1.json").read_text(encoding="utf-8"))["description"],
        "the typed words": typed,
        "the .md file": layers.prompts.parts_of((HERE / "function-prompts/adaptation/goal.md").read_text(encoding="utf-8"))[1]["does"],
        "the fixture of the definitions": _base_description("Adaptation"),
        "the engine the runtime reads": R.engine_def("Adaptation")["description"],
        "what the card tells the agent": R._goal_of(ref, "Adaptation")[0],
    }
    assert {name: text for name, text in places.items() if text != typed} == {}, "six places, one text"
    assert SITE_GOAL in (HERE / "test_layer_adaptation.py").read_text(encoding="utf-8"), "the assertion that held the old text holds the new"
    snap = json.loads((HERE / "test_fixtures/function-prompts.snapshot.json").read_text(encoding="utf-8"))
    keys = [k for k in snap if k.startswith("adapt.")]
    assert keys and all("What Adaptation does: it %s." % typed in snap[k] for k in keys), "the snapshot's Adaptation prompts"
    assert not any("steps one down" in v for v in snap.values()), "no prompt keeps the old text"


def _base_description(name):
    """The description of one engine in the fixture of the definitions as they were before the move into the layers."""
    import json
    doc = json.loads((HERE / "test_fixtures/function-engines.base.json").read_text(encoding="utf-8"))
    engines = doc.get("engines", doc)
    e = engines[name] if isinstance(engines, dict) else next(x for x in engines if x.get("name") == name)
    return e["description"]


def test_an_owner_who_stamped_the_goal_keeps_the_stamp(rt):
    """A department whose owner stamped goal.does keeps their words: the corrected default reaches only a field the owner
    never changed (the stored value is the owner's, and a later default does not replace it)."""
    W, R, J, FV, ref = rt
    mine = "reads the rows and proposes one rung up, or steps one down, and nothing else"
    ask = R.instructions_ask(ref, "adaptation", "goal", "does", "text", mine)
    assert layers.words(ref, "adaptation", "goal", "does")["text"] == SITE_GOAL, "nothing changes until the stamp"
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=200)
    assert layers.words(ref, "adaptation", "goal", "does")["text"] == mine
    assert R._goal_of(ref, "Adaptation")[0] == mine, "the card carries the owner's words"
    assert layers.prompts.owner_entry(ref, "adaptation", "goal", "does", "text")["value"] == mine
    # and a default that changed under the stamp does not touch it: the shipped words are what the field falls back to
    assert layers.prompts.defaults(ref, "adaptation", "goal", "does")["text"] == SITE_GOAL
