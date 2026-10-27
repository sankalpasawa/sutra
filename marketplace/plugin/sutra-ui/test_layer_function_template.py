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
import owner_words

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


# ---- F4: the role block in the card -------------------------------------------------------------------------------------
BLOCK = re.compile(r"\nIt is: .*?\nAll five functions keep: [^\n]*(?=\n)", re.S)
#: the strings the scripted test models of test_engine_runtime, test_j2, test_j2_identity and test_layer_root read their
#: prompts by (the first occurrence of each), and the words they key on: no word of the role block may hold one
SCRIPTED = ("THE WORDS: ", "THE DIRECTIVE: ", "THE FEEDBACK: ", "THE IDEA: ", "THE REQUEST: ", "THE ENGINE: ", "THE OWNER'S WORDS: ",
            "DEPARTMENTS THIS ROOT ALREADY HAS: ", "THIS PAGE: ", "index.html", "- Summary:", "- Publish:", "THE OWNER: none")
SCRIPTED_WORDS = ("new website", "algebra", "bakery")


def test_the_card_carries_the_role_block_for_a_function_and_not_for_a_work_engine(rt, monkeypatch):
    W, R, J, FV, ref = rt
    for fn in FUNCTIONS:
        title = S.TITLE[fn]
        card = card_of(rt, title)
        lines = card.split("\n")
        assert lines[0].startswith("You are the agent of %s, one engine of the department" % title)
        assert lines[1].startswith("What %s does: it " % title) and lines[2].startswith("Its skills: ")
        assert lines[3].startswith("It is: ") and lines[10].startswith("All five functions keep: ")
        assert [ln.split(":")[0] for ln in lines[3:11]] == ["It is", "It is not", "It may", "It never", "How it decides", "It avoids",
                                                              "It hands on to", "All five functions keep"]
        assert lines[11].startswith("It always: ") and lines[12].startswith("It decides: "), "the template lines follow the block"
        assert "It is not: " + S.FUNCTION_TEMPLATE[fn]["is_not"] in card and "It hands on to: " + S.FUNCTION_TEMPLATE[fn]["hands_on"] in card
        assert "It never: " + "; ".join(x.rstrip(".") for x in S.FUNCTION_TEMPLATE[fn]["never"]) + "." in card
        assert S.DEPARTMENT_AGREEMENT[0] in card and S.DEPARTMENT_AGREEMENT[-1] in card
        assert card.endswith("you state nothing you were not given.\n\n"), "a blank line before the step's prompt"
        assert len(BLOCK.search(card).group(0)) - 1 <= S.ROLE_BLOCK_MAX
    assert "It is: " in card_of(rt, "Identity") and "It never:" in card_of(rt, "Identity") and "All five functions keep:" in card_of(rt, "Identity")
    for engine in ("Plan", "Write", "Check", "Publish", "Do"):
        card = card_of(rt, engine)
        assert not any(m in card for m in ("It is:", "It is not:", "It never:", "All five functions keep:")), engine
        assert card.startswith("You are the agent of %s" % engine)
    # Root's Setup prompts use no card and no block: its template is interface-only
    assert S.FUNCTION_TEMPLATE["root"]["in_card"] is False
    assert R._role_block(ref, "Setup", R.engine_def("Setup")) == "" and R._role_block(ref, "Write", R.engine_def("Write")) == ""
    root_snap = (HERE / "test_fixtures/root-prompts.snapshot.json").read_text(encoding="utf-8")
    assert "All five functions keep" not in root_snap and "It never:" not in root_snap
    # a department with no template pick still has the block, and so has one whose registry cannot be read
    import function_templates
    with monkeypatch.context() as m:
        m.setattr(function_templates, "picked", lambda r: {})
        card = card_of(rt, "Priority")
        assert "It never: " in card and "It always:" not in card and "It decides:" not in card
    with monkeypatch.context() as m:
        m.setattr(function_templates, "picked", lambda r: 1 / 0)
        d = W.dept(ref)
        d["templates"] = {}
        card = R.card({"ref": ref, "dept": d, "engine": "Audit", "def": R.engine_def("Audit")})
        assert "It never: " in card and "It always:" not in card, "the block does not wait on a template"
    # with the constant off the card is as it was, and a function whose template says in_card false is sent no block
    with_block = card_of(rt, "Coordination")
    with monkeypatch.context() as m:
        m.setattr(S, "ROLE_IN_CARD", False)
        without = card_of(rt, "Coordination")
    assert BLOCK.sub("", with_block) == without and "It never:" not in without
    with monkeypatch.context() as m:
        m.setitem(S.FUNCTION_TEMPLATE["coordination"], "in_card", False)
        assert card_of(rt, "Coordination") == without
    # a block that cannot be built never stops a step: the card is what it was
    with monkeypatch.context() as m:
        m.setattr(S, "role_inputs", lambda *a: 1 / 0)
        assert card_of(rt, "Coordination") == without
    assert card_of(rt, "Coordination") == with_block


def test_no_word_of_the_role_block_holds_a_label_the_scripted_models_read():
    for fn in FUNCTIONS:
        words = module_of(fn).WORDS["goal"]
        text = " ".join([words["done"]["text"], words["role_is"]["text"], *words["role_may"]["items"], *words["role_procedure"]["items"],
                         *words["role_patterns"]["items"], *[S.FUNCTION_TEMPLATE[fn][k] for k in ("role", "is_not", "hands_on")],
                         *S.FUNCTION_TEMPLATE[fn]["never"], *S.DEPARTMENT_AGREEMENT, S.ROLE_BLOCK_LAYOUT])
        assert not [m for m in SCRIPTED if m in text], fn
        assert not [m for m in SCRIPTED_WORDS if m in text.lower()], fn


def test_a_stamped_role_field_reaches_the_next_card(rt):
    """The owner's path is the one every field has: an ask, a stamp, and the next card holds the words; the boundaries stay."""
    W, R, J, FV, ref = rt
    before = card_of(rt, "Coordination")
    mine = list(module_of("coordination").WORDS["goal"]["role_may"]["items"]) + ["name the order of two ready engines of equal weight"]
    ask = R.instructions_ask(ref, "coordination", "goal", "role_may", "items", mine)
    assert card_of(rt, "Coordination") == before, "nothing changes until the stamp"
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=200)
    after = card_of(rt, "Coordination")
    assert after != before and "; name the order of two ready engines of equal weight." in after
    assert BLOCK.sub("", after) == BLOCK.sub("", before), "only the block changed"
    never = "It never: " + "; ".join(x.rstrip(".") for x in S.FUNCTION_TEMPLATE["coordination"]["never"]) + "."
    assert never in after and S.DEPARTMENT_AGREEMENT[0] in after and S.FUNCTION_TEMPLATE["coordination"]["is_not"] in after
    # the sentence it is in: what the owner stamped for what it is
    ask = R.instructions_ask(ref, "coordination", "goal", "role_is", "text", "the timetable of this department, kept by code first")
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=200)
    assert "\nIt is: the timetable of this department, kept by code first.\n" in card_of(rt, "Coordination")


def test_a_child_version_overlay_changes_one_field_and_keeps_the_boundaries(rt, monkeypatch):
    """A child version (A2) writes only what differs: one line of how Identity decides. The card of a department that runs it
    holds the child's line and the interface's boundaries as they are, and the child passes case 14."""
    import copy
    import types
    W, R, J, FV, ref = rt
    parent = module_of("identity")
    words = copy.deepcopy(parent.WORDS)
    words["goal"]["role_procedure"]["items"][0] = "Name the goal item or the rule that applies, and say which."
    layout = copy.deepcopy(parent.LAYOUT)
    if hasattr(layers, "inherit"):                                             # A2-INHERIT's registry helper, when it is on main
        child = types.SimpleNamespace(**dict(layers.inherit("identity/v1", words={"goal": {"role_procedure": {"items": words["goal"]["role_procedure"]["items"]}}}),
                                             LAYER="identity", VERSION=2, IMPLEMENTS=1, PARENT="identity/v1", RECIPE="v1.json",
                                             __file__=parent.__file__.replace("v1.py", "v2.py")))
    else:
        child = types.SimpleNamespace(**{**vars(parent), "WORDS": words, "LAYOUT": layout, "VERSION": 2, "PARENT": "identity/v1"})
    child.__file__ = parent.__file__.replace("v1.py", "v2.py")
    assert C.case_14_function_template(child) == []
    base = card_of(rt, "Identity")
    monkeypatch.setitem(layers._LOADED, "identity/v2", child)
    monkeypatch.setitem(S.DEFAULT_PINS, "identity", "identity/v2")
    got = card_of(rt, "Identity")
    assert got != base and "1) Name the goal item or the rule that applies, and say which. 2) Separate what is known" in got
    changed = [(a, b) for a, b in zip(base.split("\n"), got.split("\n")) if a != b]
    assert len(changed) == 1 and changed[0][0].startswith("How it decides: "), "one field of one line"
    for kept in ("It is not: ", "It never: ", "It hands on to: ", "All five functions keep: "):
        assert next(x for x in got.split("\n") if x.startswith(kept)) == next(x for x in base.split("\n") if x.startswith(kept))
    # a child that drops the boundaries from its layout is told by case 14, and its words are not what the card is made of
    bad = copy.deepcopy(layout)
    bad["goal"]["role_block"] = bad["goal"]["role_block"].replace("It never: {{never}}\n", "")
    nobody = types.SimpleNamespace(**{**vars(child), "LAYOUT": bad})
    assert C.case_14_function_template(nobody) == ["identity/v2: goal.role_block leaves out {{never}}, so the agent would not be told what it never does"]


@pytest.fixture
def j2(home):
    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as FV
    for module in (E, W, org2_apply, founding, R, J, FV):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, FV


def _run_offline(j2, monkeypatch, words, org):
    """A department born the way a person makes it and run offline to the end of what it can do alone; every soft call's prompt
    recorded with the step that made it. Returns [(engine, step id, prompt)]."""
    W, R, J, founding, FV = j2
    seen = []

    def model(prompt, step):
        seen.append((step["id"], prompt))
        return None, 0.0, "offline"
    monkeypatch.setattr(R, "MODEL", model)
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(child, limit=300)
    for _ in range(4):                                                         # the owner stamps what waits, so the reading is made
        asks = [a for a in W.asks(child) if a["status"] == "pending"]
        if not asks:
            break
        for a in asks:
            W.decide_ask(child, a["id"], True)
        W.run_until_idle(child, limit=300)
    return [(R.step_def(sid)[0], sid, prompt) for sid, prompt in seen]


def test_the_block_is_sent_to_every_soft_step_of_a_function(j2, monkeypatch):
    """Over offline runs of a website and of an organic department, each soft call of Identity, Adaptation, Priority,
    Coordination and Audit is sent a prompt that starts 'You are the agent of' and holds the block once; a work engine's does
    not, and Root's Setup prompts have none."""
    calls = _run_offline(j2, monkeypatch, "Build a website that teaches algebra to Class 8 students", "Acme Learning")
    calls += _run_offline(j2, monkeypatch, "Set up a laboratory system to track chemical inventory for our school science team", "Lab Org")
    seen = {}
    for engine, sid, prompt in calls:
        assert prompt.startswith("You are the agent of %s, one engine of the department" % engine), (sid, prompt[:60])
        if engine in [S.TITLE[fn] for fn in FUNCTIONS]:
            seen.setdefault(engine, set()).add(sid)
            assert "\nIt is: " in prompt and prompt.count("All five functions keep: ") == 1, sid
            assert prompt.index("Its skills: ") < prompt.index("It is: ") < prompt.index("It never: ") < prompt.index("All five functions keep: "), sid
        else:
            assert "It is:" not in prompt and "All five functions keep" not in prompt, (engine, sid)
    assert set(seen) == {S.TITLE[fn] for fn in FUNCTIONS}, "all five functions made a soft call: %s" % {k: sorted(v) for k, v in seen.items()}
    assert {"identity.take", "priority.bargain", "audit.judge", "coord.tie"} <= set().union(*seen.values())


class TestTheBlockIsTheOnlyDifference(__import__("test_function_prompts").Fixture):
    """The prompt snapshot (test_fixtures/function-prompts.snapshot.json, 'snapshot: A3 role block') differs from the cards as
    they were only by the block (A3.4.8): every prompt of a function carries it once, and without it each is what the same
    fixture renders with S.ROLE_IN_CARD false, which is the snapshot of the commit before."""

    def test_snapshot_differs_from_the_commit_before_only_by_the_block(self):
        import json
        from unittest import mock
        snap = json.loads((HERE / "test_fixtures/function-prompts.snapshot.json").read_text(encoding="utf-8"))
        got = self.prompts()
        with mock.patch.object(S, "ROLE_IN_CARD", False):
            before = self.prompts()
        self.assertEqual(sorted(snap), sorted(before))
        self.assertGreaterEqual(len(snap), 29)
        for k in sorted(snap):
            self.assertEqual(len(BLOCK.findall(snap[k])), 1, "%s carries the block once" % k)
            self.assertEqual(BLOCK.sub("", snap[k]), before[k], "%s without the block is what it was" % k)
            self.assertEqual(snap[k], got[k], "%s renders as the snapshot holds it" % k)


# ---- F6: the pane reads the typed goal, and done is a proposal --------------------------------------------------------------
def born(j2, words="Build a website that teaches algebra to Class 8 students"):
    """A department made the way a person makes one (founded, asked for, set up by Root), on the engine runtime."""
    W, R, J, founding, FV = j2
    root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(child, limit=300)
    return child


def field_of(page, key):
    return next(f for f in page["fields"] if f["key"] == key)


def stamp(j2, ref, fn, part, field, value):
    W, R, J, founding, FV = j2
    ask = R.instructions_ask(ref, fn, "goal", part, field, value)
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)


def test_the_pane_goal_reads_the_typed_goal_and_done_is_a_proposal(j2):
    """A3.4.6: the goal field is the typed goal.does (the version's, the owner's over it), capitalised; the done field has no
    value and is a placeholder until the owner marks it, and carries the version's default as its proposal."""
    W, R, J, founding, FV = j2
    ref = born(j2)
    for fn in FUNCTIONS:
        page = FV.function(ref, fn)
        assert [f["key"] for f in page["fields"]][:2] == ["goal", "done"]
        typed = owner_words.plain(module_of(fn).WORDS["goal"]["does"]["text"])              # the screen's words (Priority gives, never grants)
        goal, done = field_of(page, "goal"), field_of(page, "done")
        assert goal["value"] == typed[:1].upper() + typed[1:] and goal["placeholder"] is False, fn
        proposal = module_of(fn).WORDS["goal"]["done"]["text"]
        assert done["value"] is None and done["placeholder"] is True, "'not set yet' until the owner marks it"
        assert done["proposal"] == proposal[:1].upper() + proposal[1:]
    assert field_of(FV.function(ref, "adaptation"), "goal")["value"].startswith("Decides how the department reaches its goal")
    assert field_of(FV.function(ref, "priority"), "goal")["value"] == "Gives each engine its limit and answers proposals that cost something"
    # the owner's stamped goal is the pane's goal, in their words
    stamp(j2, ref, "adaptation", "does", "text", "decides what the department learns next")
    assert field_of(FV.function(ref, "adaptation"), "goal")["value"] == "Decides what the department learns next"


def test_a_stamped_done_replaces_the_proposal(j2):
    W, R, J, founding, FV = j2
    ref = born(j2)
    before = field_of(FV.function(ref, "audit"), "done")
    mine = "every page of the live site was read against the brief, and nothing is left to confirm"
    stamp(j2, ref, "audit", "done", "text", mine)
    after = field_of(FV.function(ref, "audit"), "done")
    assert after["value"] == mine and after["placeholder"] is False, "the owner's words, as they gave them"
    assert after["proposal"] == before["proposal"], "the proposal is the version's, and stays what it was"
    assert field_of(FV.function(ref, "priority"), "done")["value"] is None, "only that function's"
    # the owner gives the shipped words back: the stamp goes, and the field is a placeholder again
    stamp(j2, ref, "audit", "done", "text", module_of("audit").WORDS["goal"]["done"]["text"])
    again = field_of(FV.function(ref, "audit"), "done")
    assert again["value"] is None and again["placeholder"] is True


def _instructions_told(R, ref):
    """What Identity has told the owner of a change to instructions, in order."""
    return [str(p["payload"]["done"]) for p in R.board(ref) if p["payload"].get("word") == "instructions" and p["payload"].get("done")]


def test_goal_done_is_shown_on_the_page_and_no_run_reads_it_and_the_owner_is_told_so(j2):
    """A3.4.6, a verifier's finding (F1/F6): only the function's page reads goal.done; no card does. So the view says no run
    reads it, the ask and Identity's tell say it is shown on the page and never that the next run uses it, while the four role
    words, which the role block carries into every card, stay read and keep the words they had."""
    W, R, J, founding, FV = j2
    ref = born(j2)
    for fn in FUNCTIONS:
        group = next(g for g in R.instructions_view(ref, fn) if g["group"] == "goal")
        by = {p["part"]: p for p in group["parts"]}
        assert by["done"]["read"] is False and by["done"]["read_by"] == [], "%s: no run reads when it is done" % fn
        assert all(by[part]["read"] is True for part in ("does", "skills", "role_is", "role_may", "role_procedure", "role_patterns", "role_block")), fn
    # the stamped words reach no card: this is what the view says
    audit = "every page of the live site was read against the brief, and nothing is left to confirm"
    ask = R.instructions_ask(ref, "audit", "goal", "done", "text", audit)
    said = next(p for p in R.board(ref) if p["thread"] == ask["thread"])["payload"]["objective"]
    assert said == ("Change when Audit is done to your words? No run reads these words, and Audit's page shows them: "
                    "stamp to show your words there, or say no to keep them as they are.")
    assert "next run" not in said
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    assert _instructions_told(R, ref) == ["when Audit is done now reads as you changed it; no run reads it, and Audit's page shows it."]
    assert field_of(FV.function(ref, "audit"), "done")["value"] == audit, "the page shows what the owner stamped"
    for fn in FUNCTIONS:
        card = R.card({"ref": ref, "dept": W.dept(ref), "engine": S.TITLE[fn], "def": R.engine_def(S.TITLE[fn])})
        assert audit not in card, "%s: no card holds the stamped done" % fn
    # the owner gives the shipped words back: still not a word about the next run
    ask = R.instructions_ask(ref, "audit", "goal", "done", "text", module_of("audit").WORDS["goal"]["done"]["text"])
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    assert _instructions_told(R, ref)[-1] == "when Audit is done now reads as shipped; no run reads it, and Audit's page shows it."
    assert not [t for t in _instructions_told(R, ref) if "next run" in t]
    # a role word is read: its ask and its tell keep the words every read part has
    ask = R.instructions_ask(ref, "audit", "goal", "role_is", "text", "the check of this department, kept apart from its writers")
    said = next(p for p in R.board(ref) if p["thread"] == ask["thread"])["payload"]["objective"]
    assert said == "Change what Audit is to your words? Stamp to use them from the next run, or say no to keep them as they are."
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    assert _instructions_told(R, ref)[-1] == "what Audit is now reads as you changed it; the next run uses it."


PURSUE_WORDS = (("role_is", None, ", and again after each reading until the done-when holds"),
                ("role_may", 5, "propose the next round when Audit's reading is not done and the correction advances the goal"),
                ("role_procedure", 7, "When Audit's reading is not done, propose a correction only if it moves the goal."))


def test_adaptations_role_words_promise_pursue_only_when_it_is_built():
    """Three clauses of Adaptation's role words promise Pursue (W2-ADAPT F3, F5: the handler 'Propose the next round'): a
    sentence of role_is, the fifth line of role_may and the seventh of role_procedure. They are in the words when the handler is in
    the recipe and out of them when it is not, so the words never promise what is unbuilt and never leave out what is built.
    The day W2-ADAPT merges this fails until the clauses are put back (the words of A3.4.5), the snapshot is regenerated with
    FUNCTION_PROMPTS_SNAPSHOT=write, and AD-P7 of role-rules.json is a word at role_procedure 7 again (and AD-P8 at 8)."""
    import json
    recipe = json.loads((HERE / "layers/adaptation/v1.json").read_text(encoding="utf-8"))
    built = any(h.get("name") == "Propose the next round" for h in recipe.get("on") or [])
    goal = module_of("adaptation").WORDS["goal"]
    held = []
    for part, n, clause in PURSUE_WORDS:
        text = goal[part]["text"] if n is None else (goal[part]["items"][n - 1] if len(goal[part]["items"]) >= n else "")
        held.append(clause in text)
    assert held == [built] * 3, "Pursue is %s, and the clauses that promise it are %s" % (
        "built" if built else "not built", ["in" if h else "out" for h in held])
    rules = {r["id"]: r for r in load_rules()}
    assert (rules["AD-P7"]["home"] == "word") == built and rules["AD-P8"]["line"] == "goal.role_procedure %d" % (8 if built else 7)


# ---- F7: every rule of the five official role files has a home --------------------------------------------------------------
RULES_FILE = HERE / "test_fixtures" / "templates" / "role-rules.json"
HOMES = ("word", "constant", "derived", "left")


def _all_test_names():
    names = set()
    for path in HERE.glob("test_*.py"):
        names |= set(re.findall(r"^\s*def (test_\w+)", path.read_text(encoding="utf-8"), re.M))
    return names


def _holds(token):
    """Whether one name in a rule's held_by is there: an S. name, a test, a step id of the definitions, a DEFS name, a check, or a
    function of the runtime, the records or a layer's version."""
    import engine_runtime as R
    import j2_runtime as J
    import website_dept as W
    if token.startswith("S."):
        return hasattr(S, token[2:])
    if token.startswith("test_"):
        return token in _all_test_names()
    if token in {s["id"] for name in R.defs()["engines"] for s in R.all_steps(name)} or token in S.DEFS:
        return True
    if token in S.SHARED_CHECKS or any(token in checks for checks in S.CHECKS.values()):
        return True
    return any(hasattr(m, token) for m in (R, W, J, *[module_of(fn) for fn in FUNCTIONS]))


def _line_of(rule, template, words, line=None):
    """The line of words a rule names, '(part) (index)': goal.role_may 3, never 2, is_not, agreement 1, goal.role_is."""
    layer, line = rule["layer"], line or rule["line"]
    part, _, n = line.partition(" ")
    n = int(n) if n else None
    if part.startswith("goal."):
        got = words[layer].get(part[5:]) or {}
        items = got.get("items")
        return got.get("text") if items is None else (items[n - 1] if n and 0 < n <= len(items) else None)
    if part == "agreement":
        return S.DEPARTMENT_AGREEMENT[n - 1] if n and 0 < n <= len(S.DEPARTMENT_AGREEMENT) else None
    value = (template.get(layer) or {}).get(part)
    if isinstance(value, (list, tuple)):
        return value[n - 1] if n and 0 < n <= len(value) else None
    return value


def role_rule_faults(rules, template=None, words=None):
    """What is wrong with the record of the official rules against the interface and the versions: a rule whose line is gone, or
    whose line no longer holds its key phrase (weakened), a rule with no home or no reason, a name it says holds it that is not
    there, a keeps phrase the page does not say. One sentence for each, naming the rule."""
    template = template if template is not None else S.FUNCTION_TEMPLATE
    words = words if words is not None else {fn: module_of(fn).WORDS["goal"] for fn in FUNCTIONS}
    out, seen = [], set()
    for r in rules:
        rid = r.get("id", "?")
        if rid in seen:
            out.append("%s: the id is used twice" % rid)
        seen.add(rid)
        if r.get("home") not in HOMES or r.get("layer") not in FUNCTIONS:
            out.append("%s: it has no home (%s) in a function (%s)" % (rid, r.get("home"), r.get("layer")))
            continue
        if r["home"] == "left" and not str(r.get("reason") or "").strip():
            out.append("%s: it is left, and says no reason" % rid)
        if r["home"] == "derived" and r.get("line") not in S.DEFS:
            out.append("%s: it is derived, and %s is no definition of the interface" % (rid, r.get("line")))
        if r["home"] in ("word", "constant"):
            for where in [{"line": r["line"], "phrase": r["phrase"]}] + list(r.get("also") or []):
                text = _line_of(r, template, words, where["line"])
                if not isinstance(text, str):
                    out.append("%s: %s of %s has no such line" % (rid, where["line"], r["layer"]))
                elif where["phrase"] not in text:
                    out.append("%s: %s of %s no longer holds \"%s\"" % (rid, where["line"], r["layer"], where["phrase"]))
        out += ["%s: %s is named as holding it and is not there" % (rid, t) for t in r.get("held_by") or [] if not _holds(t)]
        if r.get("keeps_phrase") and r["keeps_phrase"] not in S.LAYERS[r["layer"]]["keeps"]:
            out.append("%s: the page of %s no longer says \"%s\"" % (rid, r["layer"], r["keeps_phrase"]))
    return out


def load_rules():
    import json
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))["rules"]


def test_every_rule_of_the_five_official_role_files_has_a_home():
    """The guard for 'preserve every rule of the five official role files' (A3.4.8): the data holds every rule of A3.4.5 with its
    home, the line it names and a key phrase that must be in that line; the interface and the versions are checked against it. A
    weakened word, a dropped never line or a rule with no home is named by its id."""
    import copy
    rules = load_rules()
    assert role_rule_faults(rules) == []
    ids = [r["id"] for r in rules]
    # the ids of A3.4.5, in the order of the tables, from ID-S1 to AU-F5
    assert ids[0] == "ID-S1" and ids[-1] == "AU-F5" and len(ids) == len(set(ids)) == 115
    expect = {"identity": ("ID", ["S1", "S2", "S3", *["M%d" % i for i in range(1, 8)], *["N%d" % i for i in range(1, 9)],
                                  *["P%d" % i for i in range(1, 6)], *["F%d" % i for i in range(1, 6)], "O1", "X1"]),
              "adaptation": ("AD", ["S1", "S2", "O1", *["P%d" % i for i in range(1, 9)], *["N%d" % i for i in range(1, 9)], *["F%d" % i for i in range(1, 6)]]),
              "priority": ("PR", ["S1", "S2", "E1", *["P%d" % i for i in range(1, 7)], *["N%d" % i for i in range(1, 8)], *["F%d" % i for i in range(1, 6)]]),
              "coordination": ("CO", ["S1", "S2", *["P%d" % i for i in range(1, 8)], "X1", *["N%d" % i for i in range(1, 8)], *["F%d" % i for i in range(1, 6)]]),
              "audit": ("AU", ["S1", "S2", "O1", *["P%d" % i for i in range(1, 8)], "X1", "N6", "N8", *["F%d" % i for i in range(1, 6)]])}
    for layer, (prefix, tail) in expect.items():
        assert [r["id"] for r in rules if r["layer"] == layer] == ["%s-%s" % (prefix, t) for t in tail], layer
    homes = {h: sum(1 for r in rules if r["home"] == h) for h in HOMES}
    assert homes["left"] == 1 and homes["derived"] == 4 and homes["word"] + homes["constant"] == 110, homes
    assert {r["id"] for r in rules if r["home"] == "left"} == {"CO-X1"}, "one rule is left, with its reason (AD-P7 is a word since Pursue)"
    # the failing examples: delete a never line from a copy of the interface, and the rules that rest on it are named
    template = copy.deepcopy(S.FUNCTION_TEMPLATE)
    template["identity"]["never"] = tuple(x for i, x in enumerate(template["identity"]["never"], 1) if i != 3)
    got = role_rule_faults(rules, template=template)
    assert got[0] == "ID-N3: never 3 of identity no longer holds \"raise a limit\"", got
    assert {f.split(":")[0] for f in got} >= {"ID-N3", "ID-N4", "ID-N8"} and not [f for f in got if not f.startswith("ID-N")]
    # weaken a word so its phrase is gone, and the rule is named
    words = {fn: copy.deepcopy(module_of(fn).WORDS["goal"]) for fn in FUNCTIONS}
    words["priority"]["role_procedure"]["items"][4] = "Bargain with Adaptation for as long as it takes."
    words["audit"]["role_is"]["text"] = "the department's second pair of eyes"
    got = role_rule_faults(rules, words=words)
    assert got == ["PR-P5: goal.role_procedure 5 of priority no longer holds \"at most four exchanges\"",
                   "AU-S1: goal.role_is of audit no longer holds \"what was actually made\""], got
    # a rule with no home, a rule left with no reason, a name that is not there, a keeps phrase the page no longer says
    broken = [dict(rules[0], home="nowhere"), dict(rules[1], id="X-1", held_by=["S.NO_SUCH_THING", "no_such_step.here"]),
              dict(rules[2], id="X-2", keeps_phrase="never says this"), dict(rules[3], id="X-3", home="left", line=None, phrase=None, reason="")]
    got = role_rule_faults(broken)
    assert [f.split(":")[0] for f in got] == ["ID-S1", "X-1", "X-1", "X-2", "X-3"], got


def test_the_keeps_and_the_journey_ids_of_the_pages_equal_the_interface(capsys):
    """Two records the interface and the pages keep apart are held equal (A3.4.6): every 'never' line the data marks as one of
    Sutra's keeps names the words of the page it comes from; and the journeys a function's page lists are those of its journey
    file (skipped while journeys/functions/<fn>.json does not exist: A3-J34 creates it)."""
    import functions_view as FV
    marked = [r for r in load_rules() if r.get("keeps_phrase")]
    assert {r["id"] for r in marked} == {"ID-N7", "ID-N8", "AD-N8", "PR-N7", "CO-N7", "AU-N6", "AU-N8"}
    for r in marked:
        assert r["home"] == "constant" and r["line"].startswith("never "), r["id"]
        assert r["keeps_phrase"] in S.LAYERS[r["layer"]]["keeps"], "%s: the page of %s does not say \"%s\"" % (r["id"], r["layer"], r["keeps_phrase"])
        assert r["keeps_phrase"] in FV.S.LAYERS[r["layer"]]["keeps"], "the function pages read the same words"
    folder = HERE / "journeys" / "functions"
    missing = [fn for fn in FUNCTIONS if not (folder / (fn + ".json")).is_file()]
    if missing:
        print("skipped: the function journeys of %s are not there yet (journeys/functions/<fn>.json, A3-J34)" % ", ".join(missing))
        return
    import json
    for fn in FUNCTIONS:
        filed = json.loads((folder / (fn + ".json")).read_text(encoding="utf-8"))
        ids = [j["id"] for j in (filed.get("journeys") if isinstance(filed, dict) and "journeys" in filed else [filed])]
        assert [j[0] for j in FV.PAGES[fn]["journeys"]] == ids, fn


def test_function_templates_read_the_interface_banned_words():
    """The single copy (A3.4.6): test_function_templates holds no list of its own; the screen's words and Priority's pattern are
    the interface's."""
    import test_function_templates as TFT
    assert TFT.SCREEN_WORDS.pattern == S.TEMPLATE_BANNED and not hasattr(TFT, "FORBIDDEN_WORD")
    source = (HERE / "test_function_templates.py").read_text(encoding="utf-8")
    assert "S.TEMPLATE_NEVER_SAY[\"priority\"]" in source and "S.TEMPLATE_BANNED" in source
    assert '"what runs next"' not in source and "charters?" not in source, "no copy of either list in that file"
    assert TFT.FORBIDDEN_ID.search("DS-3") and TFT.FORBIDDEN_ID.search("dref-abc"), "the founder-only-id pattern is not a word list, and stays"


# ---- F8: the comparison script ------------------------------------------------------------------------------------------------
def test_the_comparison_script_runs_and_the_block_is_the_only_difference(home, capsys):
    """qa/role_block_ab.py runs the same scenarios with S.ROLE_IN_CARD on and off in one process, on the offline model; the two
    arms then differ in prompt size only (the steps, the checks and the answers are the same), the arm with the block sends more
    characters in the calls of the functions and no more calls, and a report ends well (exit 0) whatever it finds."""
    import io
    import json
    import os
    import subprocess
    import sys
    sys.path.insert(0, str(HERE / "qa"))
    try:
        import role_block_ab as B
    finally:
        sys.path.remove(str(HERE / "qa"))
    env_before = {k: os.environ.get(k) for k in B.ENV}
    results = B.run_arms()
    assert list(results) == ["happy", "counter", "refused"]
    for name, arms in results.items():
        on, off = arms["on"], arms["off"]
        assert (on["arm"], off["arm"]) == ("on", "off") and on["scenario"] == off["scenario"] == name
        assert on["prompt_chars"] > off["prompt_chars"], "the arm with the block sends more characters"
        extra = on["prompt_chars"] - off["prompt_chars"]
        assert on["function_calls"] > 0 and on["function_calls"] * 2000 < extra < on["function_calls"] * (S.ROLE_BLOCK_MAX + 1), (name, extra)
        assert on["function_prompt_chars"] - off["function_prompt_chars"] == extra, "and only in the calls of the functions"
        for key in ("steps", "checks", "passed", "pass_rate", "soft_calls", "function_calls", "calls", "usd"):
            assert on[key] == off[key], "%s %s: offline, the arms differ in prompt size only" % (name, key)
        assert on["outside_the_contract"] == off["outside_the_contract"] == []
        assert on["steps"] > 0 and on["checks"] > 0 and on["pass_rate"] == 1.0
    assert results["counter"]["on"]["steps"] != results["refused"]["on"]["steps"], "the scenarios are not the same run"
    assert S.ROLE_IN_CARD is True, "the constant is put back"
    assert {k: os.environ.get(k) for k in B.ENV} == env_before, "and so is the environment"
    out = io.StringIO()
    assert B.main(["refused"], out) == 0
    text = out.getvalue()
    assert "role block in the card" in text and "the block adds" in text and "the arms differ in prompt size only" in text
    assert "The live numbers are pending" in text and "refused" in text and "happy" not in text.split("\n", 2)[2]
    out = io.StringIO()
    assert B.main(["--json", "refused"], out) == 0 and json.loads(out.getvalue())["refused"]["on"]["prompt_chars"] > 0
    out = io.StringIO()
    assert B.main(["nonsense"], out) == 0 and "no scenario named nonsense" in out.getvalue()
    # run as a script it ends with exit 0, and no environment variable decides the constant
    done = subprocess.run([sys.executable, str(HERE / "qa" / "role_block_ab.py"), "refused"], capture_output=True, text=True, timeout=300,
                          env=dict(os.environ, SUTRA_NATIVE_DEPT_HOME=str(home / "elsewhere")))
    assert done.returncode == 0 and "the block adds" in done.stdout, done.stderr
    assert not [k for k in B.ENV if "ROLE" in k], "the environment the script sets holds nothing about the block"
    assert re.findall(r"environ[^\n]*ROLE|ROLE[^\n]*environ", (HERE / "qa" / "role_block_ab.py").read_text(encoding="utf-8").replace("never an environment", "")) == []
