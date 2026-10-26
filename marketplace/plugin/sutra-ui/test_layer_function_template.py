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


# ---- F3: contract case 14, and the field rule of FT-9 -------------------------------------------------------------------
def stub_of(fn, change=None):
    """A stub version of a function: v1's words and layout copied, and `change(words, layout)` applied to the copies."""
    import copy
    m = module_of(fn)
    words, layout = copy.deepcopy(m.WORDS), copy.deepcopy(m.LAYOUT)
    if change:
        change(words, layout)
    return types_module(fn, WORDS=words, LAYOUT=layout)


def test_the_contract_lists_case_14_and_names_it():
    got = {n: what for n, what, _ in C.cases()}
    assert 14 in got and got[14].startswith("A function version keeps the function template")


def test_every_function_version_passes_case_14():
    """FT-1 to FT-6, FT-9, FT-10 for all five v1, as a module and as the implementation id W3-PINS reads a pin by; Root and a stub
    with no words of its own have nothing to compare."""
    assert [C.impl_id(m) for m in C.discover() if m.LAYER in FUNCTIONS] == [S.DEFAULT_PINS[fn] for fn in FUNCTIONS]
    for fn in FUNCTIONS:
        assert C.case_14_function_template(module_of(fn)) == [], fn
        assert C.case_14_function_template(S.DEFAULT_PINS[fn]) == [], fn
        assert C.case_14_function_template(module_of(fn), {}) == []
    assert C.case_14_function_template(module_of("root")) == [] and C.case_14_function_template("root/v1") == []
    assert C.case_14_function_template(types_module("identity")) == [], "a stub with no words of its own"
    assert C.case_14_function_template("identity/v9") == [] and C.case_14_function_template(None) == []


def test_case_14_never_raises_on_a_stub():
    for words in ({"goal": "nonsense"}, {"goal": {"role_may": 3, "done": None, "role_is": {"text": 4}}}, {"goal": {"role_block": []}},
                  {"goal": {"role_may": {"items": "raise a limit"}}}, {"tie": {}}):
        got = C.case_14_function_template(types_module("identity", WORDS=words, LAYOUT={"goal": {"role_block": 7}}))
        assert got and all(f.startswith("identity/v1: ") for f in got), words


def fault_of(got, *pieces):
    """The faults that hold every piece, so a test says which fault it found."""
    return [f for f in got if all(p in f for p in pieces)]


def test_a_failing_example_for_each_fault_of_case_14(monkeypatch):
    """One stub version for each fault of FT-1 to FT-6, FT-9 and FT-10; each is told in one sentence that names the version and
    the part, and the version that is not at fault says nothing."""
    def thirteen(w, l):
        w["goal"]["role_may"]["items"] = ["rule on thing number %d" % i for i in range(13)]

    def dropped(w, l):
        del w["goal"]["role_patterns"]

    def two_lines(w, l):
        w["goal"]["done"]["text"] = "every request has a verdict.\nEvery effect has a gate answer."

    def no_never(w, l):
        l["goal"]["role_block"] = l["goal"]["role_block"].replace("{{never}}", "")

    def no_agreement(w, l):
        l["goal"]["role_block"] = l["goal"]["role_block"].replace("All five functions keep: {{agreement}}", "")

    def too_long(w, l):
        w["goal"]["role_procedure"]["items"] = ["Step %d: %s" % (i, "x" * 140) for i in range(12)]
        w["goal"]["role_may"]["items"] = ["May %d: %s" % (i, "y" * 140) for i in range(12)]

    def charter(w, l):
        w["goal"]["role_is"]["text"] = "the keeper of the charter of the department"

    def too_long_text(w, l):
        w["goal"]["role_is"]["text"] = "z" * 401

    def too_long_line(w, l):
        w["goal"]["role_patterns"]["items"][0] = "w" * 161

    def screen_word(w, l):
        w["goal"]["done"]["text"] = "every plan was granted its limit"

    def orders(w, l):
        w["goal"]["role_procedure"]["items"][0] = "Order the accepted proposals by price."

    def said_yes(w, l):
        w["goal"]["role_procedure"]["items"][3] = "Give exactly one answer: said yes, asked for less or said no."

    def raise_a_limit(w, l):
        w["goal"]["role_may"]["items"][0] = "Raise a limit when the owner is in a hurry!"

    def no_layout(w, l):
        del l["goal"]["role_block"]

    for fn, change, pieces in (
            ("identity", dropped, ("goal.role_patterns has no words",)),
            ("identity", thirteen, ("goal.role_may has 13 lines", "at most 12")),
            ("audit", two_lines, ("goal.done is one clause", "line break")),
            ("coordination", no_never, ("goal.role_block leaves out {{never}}", "what it never does")),
            ("priority", no_agreement, ("goal.role_block leaves out {{agreement}}", "working agreement")),
            ("adaptation", too_long, ("goal.role_block compiles to", "at most 3600")),
            ("identity", charter, ("goal.role_is says", "charter")),
            ("identity", too_long_text, ("goal.role_is is 401 characters", "at most 400")),
            ("audit", too_long_line, ("goal.role_patterns line 1 is 161 characters", "at most 160")),
            ("audit", screen_word, ("goal.done says", "granted")),
            ("priority", orders, ("goal.role_procedure line 1 says", "Order", "never says which work runs next")),
            ("priority", said_yes, ("goal.role_procedure line 4 says", "said yes", "accept, counter or reject")),
            ("identity", raise_a_limit, ("goal.role_may line 1 says what Identity never does", "raise a limit")),
            ("identity", no_layout, ("goal.role_block has no layout",))):
        got = C.case_14_function_template(stub_of(fn, change))
        found = fault_of(got, *pieces)
        assert len(found) == 1 and found[0].startswith("%s/v1: " % fn), (fn, change.__name__, got)
        assert C.case_14_function_template(module_of(fn)) == [], "the version that is not at fault says nothing"
    # the interface's own entry: an entry with two never lines (FT-1), and a hands_on that names a receiver the layer has no row to
    # (FT-10), told in every version of that function
    monkeypatch.setitem(S.FUNCTION_TEMPLATE["identity"], "never", ("invent a new goal or a new rule", "raise a limit"))
    got = C.case_14_function_template(module_of("identity"))
    assert len(got) == 1 and got[0].startswith("identity/v1: the function template of Identity: never holds three to ten lines"), got
    monkeypatch.setitem(S.FUNCTION_TEMPLATE["audit"], "hands_on", "Identity only: readings and findings. Priority: a price.")
    got = C.case_14_function_template(module_of("audit"))
    assert len(got) == 1 and got[0].startswith("audit/v1: hands_on of Audit: Audit hands on to Priority, and the interface gives Audit no row"), got
    monkeypatch.setattr(S, "DEPARTMENT_AGREEMENT", S.DEPARTMENT_AGREEMENT[:3])
    assert C.case_14_function_template(module_of("coordination"))[0] == \
        "coordination/v1: the working agreement holds four to eight lines, and this holds 3"


def test_an_owner_line_that_says_what_a_never_line_forbids_is_refused(rt):
    """FT-9 at the ask: a role_may or role_procedure line that says what a 'never' line of the layer forbids is refused in plain
    words, compared by normalised words (case and punctuation do not hide it); a line that does not is filed as an ask. The
    interface is the one rule, so the stamp refuses it again."""
    W, R, J, FV, ref = rt
    fine = list(module_of("identity").WORDS["goal"]["role_may"]["items"])
    with pytest.raises(ValueError) as e:
        R.instructions_ask(ref, "identity", "goal", "role_may", "items", fine + ["Raise a limit, when the owner asks!"])
    assert "these words cannot serve Identity: items (item 8) Identity never does this: raise a limit" == str(e.value)
    with pytest.raises(ValueError) as e:
        R.instructions_ask(ref, "priority", "goal", "role_procedure", "items", ["Check the cost.", "Then START A RUN."])
    assert "items (item 2) Priority never does this: start a run" in str(e.value)
    ask = R.instructions_ask(ref, "identity", "goal", "role_may", "items", fine + ["warn the owner when a limit is near"])
    assert ask["kind"] == "instructions" and ask["status"] == "pending" and ask["text"] == "Change what Identity may do to your words"
    # the same words are no fault in a layer whose never lines do not say them: the rule is per layer
    assert S.validate_field("priority", "goal", "role_may", "items", ["raise a limit"]) == []
    assert S.validate_field("identity", "goal", "role_may", "items", ["raise a limit"]) == ["$[0]: Identity never does this: raise a limit"]
    # and a default that says one is a fault of the version, in contract case 5 and in case 14
    bad = stub_of("coordination", lambda w, l: w["goal"]["role_procedure"]["items"].append("start a run: the engine starts itself in its slot"))
    assert any("goal.role_procedure.items" in f and "Coordination never does this" in f for f in C.case_5(bad, {}))
    assert fault_of(C.case_14_function_template(bad), "goal.role_procedure line 8 says what Coordination never does")


# ---- F5: the floor ------------------------------------------------------------------------------------------------------
def card_of(rt, engine):
    """The card of one engine of the fixture department, as a step is sent it."""
    W, R, J, FV, ref = rt
    return R.card({"ref": ref, "dept": W.dept(ref), "engine": engine, "def": R.engine_def(engine)})


@pytest.fixture
def registry(rt, monkeypatch):
    """The registry the function templates' picks live in, on a home of its own (as test_85 does): the placement engine is
    reloaded on it, and again on the real environment when the test is over."""
    import placement_engine as E
    importlib.reload(E)
    yield E
    monkeypatch.undo()
    importlib.reload(E)


def test_the_picked_templates_whole_floor_reaches_the_card(rt, registry):
    """FT-8: a department on the Default reads the Default's whole floor, its last line included; a use case's own lines come
    after the Default's, and the card holds both (at most eight lines); the choices stay the first three."""
    import json
    import function_templates as FT
    default = FT.get("priority/default")
    assert len(default["floor"]) == 4 and default["floor"][3].startswith("Never reads a check to set pay, budget or rank")
    card = card_of(rt, "Priority")
    always = next(ln for ln in card.split("\n") if ln.startswith("It always: "))
    assert always == "It always: " + " ".join(default["floor"]), "the Default's four lines, the last one too"
    FT.write_pick(rt[4], "priority", "priority/money-movement")
    card = card_of(rt, "Priority")
    always = next(ln for ln in card.split("\n") if ln.startswith("It always: "))
    money = FT.get("priority/money-movement")
    assert always == "It always: " + " ".join(money["floor"])
    assert "Keeps room in today's budget for anything due to a customer or a bank" in always, "what the use case adds"
    assert all(line in always for line in default["floor"]), "and the Default's lines"
    assert always.index(default["floor"][3]) < always.index("Keeps room in today's budget"), "the Default's first"
    decides = next(ln for ln in card.split("\n") if ln.startswith("It decides: "))
    assert decides == "It decides: " + " ".join(money["choices"][:3])
    # at most eight lines, and the helper takes strings
    R = rt[1]
    assert R._floor_lines({"floor": ["line %d" % i for i in range(12)]}) == ["line %d" % i for i in range(8)]
    assert R._floor_lines({"floor": ["a", 2]}) == ["a", "2"]
    # no template of the library has more than eight lines, so none loses one
    assert max(len(t["floor"]) for fn in FT.FUNCTIONS for t in FT.templates(fn)) <= 8
