"""The typed prompt compiler (PRD amendment A1.16; W1-CORE K1, steps C3, C4 and C5; the .md bundle retired by W3-PROOF X1).

C3  layers/prompts.py: compile_layout, words, prompt and faults. A part is served by the words and the layout of the version a
    department pins, else of the layer's default version; a part no version holds words for is an error that names it, never a
    blank; a marker with no value raises with the part named; a value is never scanned again.
C4  the words of every layer are the text of the .md files they came from, byte for byte (test_fixtures/retired-prompt-parts.json
    keeps that text since the files were retired), and a part a later step adds is served by its layer's words alone.
C5  the snapshot renders what runs: a stub overriding a prompt through the registry changes the rendered text, and the stubs
    still pass the contract, whose case 5 compiles each part with sample inputs.

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import copy
import os
from pathlib import Path
from unittest import mock

import pytest

import layers
import layers.contract as C
import layers.prompts as P
import layer_schema as S
import test_function_prompts as TFP  # the fixture department the M2.1a snapshot is rendered for, and the retired parts' text

HERE = Path(__file__).resolve().parent


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import engine_runtime as R
    return R


def holding(monkeypatch, layer, words, layout):
    """The layer's implementation, made to hold `words` and `layout` for the duration of the test."""
    module = layers.load(S.DEFAULT_PINS[layer])
    monkeypatch.setattr(module, "WORDS", words)
    monkeypatch.setattr(module, "LAYOUT", layout)
    return module


def md_part(layer, group, part, **inputs):
    """What the retired .md file said for a part, its inputs filled: the text the compiler must give back."""
    return P.SLOT.sub(lambda m: str(inputs[m.group(1)]), TFP.retired(layer, group, part))


def split_of(layer, *groups):
    """WORDS and LAYOUT for the groups of a layer: copies of its default version's own, to hand to a stub."""
    module = layers.load(S.DEFAULT_PINS[layer])
    names = groups or tuple(S.PROMPTS[layer])
    return ({g: copy.deepcopy(module.WORDS[g]) for g in names}, {g: copy.deepcopy(module.LAYOUT[g]) for g in names})


def all_parts():
    """The parts the retired .md bundle held, from the fixture that keeps their text (the reference), so a part a later step adds
    to the interface changes nothing here."""
    return [(layer, group, part) for layer in S.FUNCTION_LAYERS for group in S.PROMPTS[layer]
            for part in TFP.RETIRED["parts"][layer].get(group, {})]


def later_part(monkeypatch, runtime, layer, group, part, inputs=("brief",)):
    """A part a later step adds to the interface (A1.16, 'Parts added by later steps'), the way a package adds it: named in
    S.PROMPTS and in the runtime's list of the parts steps read, in no .md file and in no line of S.ADDED_PARTS. Returns its
    words and its layout, for a layer's implementation to hold."""
    spec = {"fields": {"task": "field.task", "guidance": "field.guidance"}, "inputs": tuple(inputs),
            "returns": 'Return ONLY a JSON object: {"ok": bool}.', "read_by": "%s.%s" % (layer, part)}
    monkeypatch.setitem(S.PROMPTS[layer][group], part, spec)
    monkeypatch.setitem(runtime.INSTRUCTIONS[layer][group], part, tuple(inputs))
    return {"task": "Read it.", "guidance": "Be brief."}, "{task}\nTHE BRIEF: {{brief}}\n\n{returns}\n{guidance}"


GATE = ("identity", "take", "gate")


# ---- C3 · the compiler ------------------------------------------------------------------------------------------------
def test_c3_compile_layout_fills_every_marker_in_one_pass():
    got = P.compile_layout("{task}\nFOR {{who}}:\n{items}\n{guidance} / {text}\n{returns}",
                           {"task": "Do it.", "items": ["a", "b"], "guidance": "Gently.", "text": "T"},
                           'Return ONLY a JSON object: {"ok": bool}.', {"who": "the owner"})
    assert got == 'Do it.\nFOR the owner:\n- a\n- b\nGently. / T\nReturn ONLY a JSON object: {"ok": bool}.'
    assert P.compile_layout("{{n}} and {{n}}", {}, None, {"n": 3}) == "3 and 3", "an input is str() of what code gave"
    assert P.compile_layout("{items}", {"items": "already text"}, None, {}) == "already text"


def test_c3_a_value_is_never_scanned_again():
    values = {"task": "keep {{who}} and {guidance} and {returns} as written", "guidance": "{task}"}
    got = P.compile_layout("{task}|{guidance}|{{who}}", values, "R", {"who": "{{who}} {task}"})
    assert got == "keep {{who}} and {guidance} and {returns} as written|{task}|{{who}} {task}"


def test_c3_a_marker_with_no_value_is_an_error_never_a_blank():
    with pytest.raises(ValueError, match=r"^Identity's take instructions, gate: the app fills no \{\{engine\}\}$"):
        P.compile_layout("{{rules}} {{engine}}", {}, None, {"rules": "r"}, P.who(*GATE))
    with pytest.raises(ValueError, match=r"a prompt: the app fills no \{\{x\}\}"):
        P.compile_layout("{{x}}", {}, None, {})
    with pytest.raises(ValueError, match=r"no guidance to put at \{guidance\}"):
        P.compile_layout("{guidance}", {"task": "t"}, None, {}, P.who(*GATE))
    with pytest.raises(ValueError, match=r"no answer contract to put at \{returns\}"):
        P.compile_layout("{returns}", {}, None, {}, P.who(*GATE))


def test_c3_the_part_is_named_in_the_error_when_the_words_serve_it_too(runtime):
    with pytest.raises(ValueError, match=r"^Identity's take instructions, gate: the app fills no \{\{engine\}\}$"):
        P.prompt(None, *GATE, rules="r")
    with pytest.raises(ValueError, match=r"^Identity's take instructions have no part nothing$"):
        P.prompt(None, "identity", "take", "nothing")
    with pytest.raises(ValueError, match=r"^Audit's judge instructions have no part gate$"):
        P.words(None, "audit", "judge", "gate")


def test_c3_a_stub_holding_words_and_layout_for_identity_take_gate_renders_exactly_the_retired_files_text(runtime, monkeypatch):
    want = md_part(*GATE, rules="the rules", engine="the engine")
    assert want.startswith("An engine asks whether it may start.\nTHE RULES: the rules\nTHE ENGINE: the engine\n\nReturn ONLY")
    assert P.prompt(None, *GATE, rules="the rules", engine="the engine") == want, "from the version's own words"
    words, layout = split_of("identity", "take")
    everything = split_of("identity")
    holding(monkeypatch, "identity", everything[0], everything[1])
    assert P._module(None, "identity", "take", "gate") is not None, "the pinned module holds the part"
    assert P.prompt(None, *GATE, rules="the rules", engine="the engine") == want, "from a stub that holds the same"
    assert layers.prompt(None, *GATE, rules="the rules", engine="the engine") == want
    # the stub's words are what is sent: change one and the text changes
    words["take"]["gate"]["task"] = "A step asks whether it may run."
    everything[0]["take"]["gate"] = words["take"]["gate"]
    assert P.prompt(None, *GATE, rules="the rules", engine="the engine") == want.replace("An engine asks whether it may start.", "A step asks whether it may run.")
    # a part the stub does not hold is not read from anywhere else: it is an error that names it, never a blank
    del everything[0]["take"]["rule"], everything[1]["take"]["rule"]
    with pytest.raises(ValueError, match=r"^Identity's take instructions, rule: no version holds words for this part$"):
        P.prompt(None, "identity", "take", "rule", goal="g", rules="r", words="w")
    # the compiler is reached by the runtime's own name for it
    assert runtime._prompt(*GATE, ref=None, rules="the rules", engine="the engine").startswith("A step asks whether it may run.")


def test_c3_a_pinned_version_with_no_words_of_its_own_is_served_the_default_versions(runtime, monkeypatch):
    """The pinned version serves a part when it holds words and a layout for it; else the layer's default version does."""
    inputs = {"rules": "the rules", "engine": "the engine"}
    stub = type("Stub", (), {"WORDS": {}, "LAYOUT": {}})
    monkeypatch.setattr(layers, "impl", lambda ref, layer, d=None: stub)
    assert P._module("dref-x", "identity", "take", "gate") is layers.load("identity/v1")
    assert P.prompt("dref-x", *GATE, **inputs) == md_part(*GATE, **inputs)
    stub.WORDS = {"take": {"gate": {"task": "A pinned version asks."}}}
    stub.LAYOUT = {"take": {"gate": "{task}\nTHE RULES: {{rules}}\nTHE ENGINE: {{engine}}\n\n{returns}"}}
    assert P._module("dref-x", *GATE[:2], "gate") is stub
    assert P.prompt("dref-x", *GATE, **inputs).startswith("A pinned version asks.\nTHE RULES: the rules\n"), "its own words win"
    assert P.prompt("dref-x", "identity", "take", "rule", goal="g", rules="r", words="w") == md_part("identity", "take", "rule", goal="g", rules="r", words="w")


def test_c3_a_stub_missing_an_input_raises_with_the_part_named(runtime, monkeypatch):
    words, layout = split_of("identity", "take")
    holding(monkeypatch, "identity", {"take": {"gate": words["take"]["gate"]}}, {"take": {"gate": layout["take"]["gate"]}})
    with pytest.raises(ValueError, match=r"^Identity's take instructions, gate: the app fills no \{\{engine\}\}$"):
        P.prompt(None, *GATE, rules="the rules")


def test_c3_words_are_the_versions_defaults(runtime, monkeypatch):
    got = P.words(None, "identity", "take", "take")
    assert sorted(got) == ["guidance", "task"] and got["task"] == "Judge one request from the owner."
    assert P.words(None, "identity", "goal", "skills")["items"][0] == "recognise a task, a query, a directive, feedback or a new idea"
    assert P.words(None, "identity", "goal", "close") == {} and layers.words(None, "identity", "goal", "close") == {}
    note = P.words(None, "adaptation", "decide", "note")["text"]
    assert note.startswith("In this version the choice is made by code") and note.endswith("never applies one itself.")
    # a copy: the version's own words are never handed out to be changed
    words, layout = split_of("identity")
    words["take"]["gate"] = {"task": "Mine."}
    layout["take"]["gate"] = "{task}\n\n{returns}"
    holding(monkeypatch, "identity", words, layout)
    P.words(None, *GATE)["task"] = "changed"
    assert words["take"]["gate"]["task"] == "Mine."
    # what an agent is told it is comes from the words its layer's version holds
    words["goal"]["does"], words["goal"]["skills"] = {"text": "does it differently"}, {"items": ["x", "y"]}
    assert runtime._goal_of(None, "Identity") == ("does it differently", ["x", "y"])
    assert runtime._goal_of(None, "Audit")[0] == "drops in on what went live and checks claims against the record"


def test_c3_the_goal_of_a_function_is_what_its_definition_says_and_a_work_engine_keeps_its_own(runtime):
    for fn in ("Identity", "Adaptation", "Priority", "Coordination", "Audit"):
        e = runtime.engine_def(fn)
        assert runtime._goal_of(None, fn) == (e["description"], e["skills"]), fn
    plan = runtime.engine_def("Plan")
    assert runtime._goal_of(None, "Plan") == (plan["description"], list(plan["skills"]))
    assert runtime._goal_of(None, "Nobody") == ("", [])


def test_c3_instructions_are_the_interfaces_parts_with_the_inputs_code_fills(runtime):
    R = runtime
    # the parts the retired files shipped with, as the floor: a part a later step adds to the interface stands beside them
    shipped = {"identity": {"goal": ["does", "skills", "close"], "completeness": ["thin", "enough"],
                                       "take": ["recognise", "take", "answer", "rule", "weigh", "gate"]},
                          "adaptation": {"goal": ["does", "skills"], "sense": ["shape"], "decide": [], "make": ["line", "refused"]},
                          "priority": {"goal": ["does", "skills"], "bargain": ["line", "engine", "cost"]},
                          "coordination": {"goal": ["does", "skills"], "tie": ["tie"]},
                          "audit": {"goal": ["does", "skills"], "judge": ["judge", "items"]}}
    assert list(R.INSTRUCTIONS) == list(shipped) and all([g for g in R.INSTRUCTIONS[fn] if g in files] == list(files) for fn, files in shipped.items())
    for fn, files in shipped.items():
        for group, parts in files.items():
            # the retired files' parts, in their order: a part a later step adds stands beside them and changes none of this
            assert [p for p in R.INSTRUCTIONS[fn][group] if p in parts] == parts, (fn, group)
            assert [p for p in parts if p in TFP.RETIRED["parts"][fn][group]] == parts, "the fixture still holds them"
    assert R.INSTRUCTIONS["identity"]["completeness"]["enough"] == ("words", "asked", "goal", "items", "rules", "owner", "budget", "confirm")
    for layer, group, part in all_parts():
        if layer == "adaptation" and group == "decide":
            continue
        assert R.INSTRUCTIONS[layer][group][part] == tuple(S.PROMPTS[layer][group][part]["inputs"])


def test_c3_the_old_names_are_thin_aliases_of_the_compiler(runtime):
    R = runtime
    assert R._prompt("coordination", "tie", "tie", None, ready="a", what="b", order="c", waiting="d") == \
        P.prompt(None, "coordination", "tie", "tie", ready="a", what="b", order="c", waiting="d")
    assert R.prompt_faults() == P.faults() == []
    for gone in ("_parts", "_instruction", "instruction_faults", "bundle_faults", "PROMPTS_DIR"):
        assert not hasattr(R, gone), "%s went with the .md bundle" % gone
    for gone in ("parts_of", "instruction", "file_parts", "md_part", "instruction_faults", "bundle_faults", "extract", "split", "main"):
        assert not hasattr(P, gone), "layers.prompts.%s went with the .md bundle" % gone


def test_c3_faults_name_what_keeps_a_typed_part_from_serving(runtime, monkeypatch):
    R = runtime
    words, layout = split_of("identity")
    assert P.faults() == []
    for edit, fault in (
            (lambda w, l: l["take"].update(gate=l["take"]["gate"].replace("{{engine}}", "{{engine}} {{budget}}")),
             "the layout holds {{budget}} and the app fills no such input"),
            (lambda w, l: l["take"].update(gate=l["take"]["gate"].replace("{task}", "{guidance}")),
             "the layout holds {guidance} and the part has no field guidance"),
            (lambda w, l: l["take"].update(gate=l["take"]["gate"].replace("{returns}", "")),
             "the layout leaves out the answer contract"),
            (lambda w, l: l["take"].update(gate=l["take"]["gate"].replace("{task}\n", "")),
             "the layout never reads the field task"),
            (lambda w, l: w["take"]["gate"].update(task="Say {{engine}} first."),
             "task: holds '{{' or '}}', which only the app may write"),
            (lambda w, l: w["take"]["gate"].update(task="x" * 1201), "task: longer than 1200")):
        w, l = copy.deepcopy(words), copy.deepcopy(layout)
        edit(w, l)
        holding(monkeypatch, "identity", w, l)
        assert [f for f in P.faults() if fault in f] == ["Identity's take instructions, gate: " + fault], fault
    w, l = copy.deepcopy(words), copy.deepcopy(layout)
    w["take"]["nothing"], l["take"]["nothing"] = {"task": "x"}, "{task}"
    holding(monkeypatch, "identity", w, l)
    assert "Identity's take instructions, nothing: Identity has no part take.nothing" in P.faults()


def test_c3_a_part_the_version_holds_no_words_for_is_a_fault_that_names_it_and_nothing_else_serves_it(runtime, monkeypatch):
    """The covering check of the words: with the bundle gone a part without words is not read from anywhere, so the check
    names it (the definitions load refuses, test_function_prompts), where the bundle once covered it."""
    words, layout = split_of("audit", "judge")
    holding(monkeypatch, "audit", words, layout)                 # a layer whose goal group has no words at all
    goal_parts = list(S.PROMPTS["audit"]["goal"])
    assert goal_parts[:2] == ["does", "skills"] and len(goal_parts) == 8, goal_parts
    assert P.faults() == ["Audit's goal instructions, %s: the version holds no words for it" % part for part in goal_parts]
    assert P.unserved("audit", layers.load("audit/v1")) == ["goal.%s" % part for part in goal_parts]
    with pytest.raises(ValueError, match=r"^Audit's goal instructions, does: no version holds words for this part$"):
        P.words(None, "audit", "goal", "does")
    # an added part (S.ADDED_PARTS) has no other source either: it is asked for like the rest
    assert all(("audit", "goal", part) in S.ADDED_PARTS for part in goal_parts[2:])


#: a part of a layer that holds its words (Identity's, Coordination's and Priority's), and the file the owner changes whole
HELD = [("identity", "take", "take"), ("coordination", "tie", "tie"), ("priority", "bargain", "line")]


@pytest.mark.parametrize("layer,group,part", HELD)
def test_c3_a_file_the_owner_changed_whole_is_no_run_s_words_the_typed_values_took_it_over(runtime, layer, group, part):
    """M2.2 read a department's own copy of a file in the words' place; W1-CORE K2's typed values took that over (A1-7): a
    whole-file copy is kept as the owner's note and no run reads it, so the layer's words (and any typed value laid over
    them) are what a prompt is made of, in that department and in every other."""
    import website_dept as W
    ref, other = "dref-ownscopy0001", "dref-ownscopy0002"
    for r in (ref, other):
        W.create(r, "Own Copy " + r[-1] + " Website", None)
    module = layers.load(S.DEFAULT_PINS[layer])
    inputs = {n: "<%s>" % n for n in S.PROMPTS[layer][group][part]["inputs"]}
    shipped = P.prompt(ref, layer, group, part, **inputs)
    assert P._module(ref, layer, group, part) is module and P.words(ref, layer, group, part) == module.WORDS[group][part]
    mine = "What the owner's file is for.\n\n## %s\n\nThe owner's own words.\n%s\n" % (part, TFP.retired(layer, group, part))
    path = P.own(ref, layer, group)
    path.parent.mkdir(parents=True)
    path.write_text(mine, encoding="utf-8")
    assert P._module(ref, layer, group, part) is module, "the copy is not read in the words' place"
    assert P.prompt(ref, layer, group, part, **inputs) == shipped and layers.prompt(ref, layer, group, part, **inputs) == shipped
    assert P.words(ref, layer, group, part) == module.WORDS[group][part]
    assert "The owner's own words." not in " ".join(str(v) for v in P.words(ref, layer, group, part).values())
    assert P.prompt(other, layer, group, part, **inputs) == shipped
    assert P.own_files(ref, layer) == [group] and P.own_files(other, layer) == [], "it is the department's own note, and only theirs"


def test_c3_a_ref_that_is_no_department_is_served_the_words_all_the_same(runtime):
    inputs = {n: "<%s>" % n for n in S.PROMPTS["identity"]["take"]["gate"]["inputs"]}
    assert P.prompt("../not-a-ref", "identity", "take", "gate", **inputs) == P.prompt(None, "identity", "take", "gate", **inputs)
    assert P.own_files("../not-a-ref", "identity") == [] and P.owner_values("../not-a-ref", "identity", "take", "gate") == {}


# ---- C4 · the words are the retired files' text -----------------------------------------------------------------------------
def inputs_of(text):
    """The names a part's text asks code to fill, in the order they first appear."""
    return list(dict.fromkeys(P.SLOT.findall(text)))


def test_c4_the_interfaces_parts_are_the_retired_files_parts_and_the_added_ones_and_no_other():
    """S.ADDED_PARTS is exactly the parts that have no retired text: a part is in one list or the other, never both, never
    neither. (So a part added after the files, and only such a part, is exempt from being the files' text.)"""
    retired = set(all_parts())
    interface = {(layer, group, part) for layer in S.FUNCTION_LAYERS for group, parts in S.PROMPTS[layer].items() for part in parts}
    added = set(S.ADDED_PARTS)
    assert retired & added == set(), "a part the files held is not an added part"
    assert interface - retired - added == set(), "every part of the interface is one or the other"
    assert added <= interface and len(retired) == 29, "and every added part is the interface's"


def test_c4_the_words_of_every_layer_are_the_retired_files_text_byte_for_byte():
    seen = 0
    for layer in S.FUNCTION_LAYERS:
        module = layers.load(S.DEFAULT_PINS[layer])
        assert list(TFP.RETIRED["leads"][layer]) == list(S.PROMPTS[layer]) == list(S.GROUPS[layer]), "the interface's groups, in its order"
        for group, lead in TFP.RETIRED["leads"][layer].items():
            assert S.GROUPS[layer][group] == lead, "%s/%s: the lead of a group is the interface's" % (layer, group)
        for group, parts in S.PROMPTS[layer].items():
            for part, spec in parts.items():
                if (layer, group, part) in S.ADDED_PARTS:
                    continue                                   # a part a later step added has no retired text to be the same as
                md = TFP.retired(layer, group, part)
                sample = {n: "<<%s>>" % n for n in spec["inputs"]}
                got = P.compile_layout(module.LAYOUT[group][part], module.WORDS[group][part], spec["returns"], sample, P.who(layer, group, part))
                assert got == P.SLOT.sub(lambda m: sample[m.group(1)], md), "%s.%s.%s" % (layer, group, part)
                assert spec["returns"] is None or spec["returns"] in md, "returns is the part's own, byte for byte"
                assert spec["returns"] is not None or "Return ONLY" not in md
                assert inputs_of(md) == list(spec["inputs"]), "the part asks for the inputs the interface names"
                assert set(module.WORDS[group][part]) == set(spec["fields"]), (layer, group, part)
                seen += 1
    assert seen == len(all_parts()) == 29, "every part the files held"


def test_c4_the_layers_words_pass_the_interface_and_the_layouts_serve(runtime):
    for layer in S.FUNCTION_LAYERS:
        module = layers.load(S.DEFAULT_PINS[layer])
        for group, parts in module.WORDS.items():
            for part, values in parts.items():
                assert P.part_faults(layer, group, part, values, module.LAYOUT[group][part]) == [], (layer, group, part)
                for field, value in values.items():
                    assert S.validate_field(layer, group, part, field, value) == [], (layer, group, part, field)
        assert P.unserved(layer, module) == [], "and every part of the interface has its words"


# ---- C4 · a part a later step adds has its words in its layer and nowhere else (A1.16, 'Parts added by later steps') -----------
# A package that adds a part to the interface adds its words to its layer's version, and needs no line in this file or in
# S.ADDED_PARTS: nothing else can serve it (the .md files are retired).
def typing(monkeypatch, layer, group, part, words, layout):
    """The layer's default implementation made to type the part, beside everything it holds."""
    module = layers.load(S.DEFAULT_PINS[layer])
    w, l = copy.deepcopy(module.WORDS), copy.deepcopy(module.LAYOUT)
    w.setdefault(group, {})[part], l.setdefault(group, {})[part] = words, layout
    return holding(monkeypatch, layer, w, l)


@pytest.fixture
def fresh_defs(runtime):
    """The definitions load afresh for the test, and again after it: what a test patched is never what a later test loads."""
    runtime._DEFS.clear()
    yield runtime
    runtime._DEFS.clear()


def test_c4_a_part_a_later_step_adds_is_served_by_the_layers_words(fresh_defs, monkeypatch):
    R = fresh_defs
    words, layout = later_part(monkeypatch, R, "audit", "judge", "extra")
    typing(monkeypatch, "audit", "judge", "extra", words, layout)
    assert P.faults() == R.prompt_faults() == [] and R.validate(R.defs()) == [], "and the definitions load"
    assert P.prompt(None, "audit", "judge", "extra", brief="B") == "Read it.\nTHE BRIEF: B\n\n" + \
        S.PROMPTS["audit"]["judge"]["extra"]["returns"] + "\nBe brief."
    assert ("audit", "judge", "extra") not in all_parts() and ("audit", "judge", "items") in all_parts()


def test_c4_a_part_no_version_holds_words_for_is_still_a_fault_listed_as_added_or_not(fresh_defs, monkeypatch):
    R = fresh_defs
    later_part(monkeypatch, R, "audit", "judge", "extra")
    assert R.prompt_faults() == ["Audit's judge instructions, extra: the version holds no words for it"], "a step reads it and nothing serves it"
    with pytest.raises(ValueError, match=r"Audit's judge instructions, extra: the version holds no words for it"):
        R.defs()
    # S.ADDED_PARTS exempts nothing from having words: an added part has no other source either
    monkeypatch.setattr(S, "ADDED_PARTS", S.ADDED_PARTS + (("audit", "judge", "extra"),))
    assert R.prompt_faults() == ["Audit's judge instructions, extra: the version holds no words for it"]
    with pytest.raises(ValueError, match=r"Audit's judge instructions, extra: no version holds words for this part"):
        P.prompt(None, "audit", "judge", "extra", brief="B")


def test_c4_a_part_added_beside_adaptations_decide_note_leaves_the_note_as_it_is(fresh_defs, monkeypatch):
    """Adaptation's decide group has no headed part (its words are the part `note`). A later step adds decide.next; the group is
    the same group, and the note is still its note."""
    R = fresh_defs
    note = P.words(None, "adaptation", "decide", "note")["text"]
    words, layout = later_part(monkeypatch, R, "adaptation", "decide", "next")
    typing(monkeypatch, "adaptation", "decide", "next", words, layout)
    assert P.words(None, "adaptation", "decide", "note") == {"text": note}
    assert R.prompt_faults() == [] and R.validate(R.defs()) == []
    assert R.INSTRUCTIONS["adaptation"]["decide"] == {"next": ("brief",)}, "the note is no part a step reads; the new one is"


# ---- C5 · the snapshot renders what runs; the compiling contract case ---------------------------------------------------


class TestTheSnapshotRendersWhatRuns(TFP.Fixture):
    TAKES = {"identity.take:" + n for n in ("directive", "task", "query", "feedback", "thin")}

    def test_c5_the_snapshot_looks_every_name_up_through_the_registry(self):
        R = self.R
        seen, real = [], R._resolve

        def spy(ctx, kind, name, engine=None):
            seen.append((kind, name, engine))
            return real(ctx, kind, name, engine)
        R._resolve = spy
        self.addCleanup(setattr, R, "_resolve", real)
        got = self.prompts()
        assert len(got) >= 25
        kinds = {k for k, _, _ in seen}
        assert kinds == {"code", "prompt"}, "a code step to fill the bag, a prompt to send"
        assert {n for k, n, _ in seen if k == "prompt"} >= {"identity_take", "adapt_line", "priority_bargain", "coord_tie", "audit_judge"}
        assert all(engine in ("Identity", "Adaptation", "Priority", "Coordination", "Audit") for _, _, engine in seen), \
            "each name is looked up for the function whose step it is"
        want = TFP.json.loads(TFP.SNAP.read_text(encoding="utf-8"))
        assert got == want, "and what the registry gives is still the snapshot"

    def test_c5_a_stub_overriding_identity_takes_prompt_changes_the_rendered_text(self):
        before = self.prompts()
        module = layers.load("identity/v1")
        stub = lambda ctx, step, item: "THE STUB'S TAKE"
        module.PROMPT["identity_take"] = stub
        self.addCleanup(module.PROMPT.pop, "identity_take", None)
        after = self.prompts()
        changed = {k for k in before if before[k] != after[k]}
        assert changed == self.TAKES, "the registry is used: the five renders of identity.take, and nothing else"
        for k in changed:
            assert after[k].endswith("\n\nTHE STUB'S TAKE") and "THE GOAL:" not in after[k], k
            assert after[k].startswith(before[k].split("Judge one request")[0]), "the card is still the engine's"

    def test_c5_a_stub_overriding_a_code_step_changes_what_the_prompt_reads(self):
        before = self.prompts()
        real = layers.resolve(None, "Priority", "code", "priority_read", self.R.CODE)     # the body that runs, wherever it lives

        def room_flipped(ctx, step, item):
            got = real(ctx, step, item)
            return dict(got, facts=dict(got["facts"], room=not got["facts"]["room"]))
        patch = mock.patch.dict(layers.load("priority/v1").CODE, {"priority_read": room_flipped})
        patch.start()
        self.addCleanup(patch.stop)
        after = self.prompts()
        assert {k for k in before if before[k] != after[k]} == {k for k in before if k.startswith("priority.bargain:")}

    def test_c5_the_stubs_that_hold_the_words_still_pass_the_contract(self):
        module = layers.load("identity/v1")
        words, layout = split_of("identity")                                       # a stub that holds the same words, every part
        stub_take = lambda ctx, step, item: "THE STUB'S TAKE"
        for patch in (mock.patch.object(module, "WORDS", words), mock.patch.object(module, "LAYOUT", layout),
                      mock.patch.dict(module.PROMPT, {"identity_take": stub_take})):
            patch.start()
            self.addCleanup(patch.stop)
        ref = C.fixture_department(os.environ["SUTRA_NATIVE_DEPT_HOME"], TFP.REF)
        got = {n: fn(module, {"ref": ref}) for n, _, fn in C.cases()}
        assert got == {n: [] for n, _, _ in C.cases()} and set(got) >= set(range(1, 14)), got      # every case the contract has: 13 from A2, 14 from A3
        assert C.parts_without_words(module) == [], "every part of Identity is typed in the stub"
        # and the snapshot, rendered through the registry from the typed words, is the snapshot still
        del module.PROMPT["identity_take"]
        assert self.prompts() == TFP.json.loads(TFP.SNAP.read_text(encoding="utf-8")), "a words-migration commit passes the snapshot unchanged"


def _stub(layer, words, layout, tmp_path):
    fake = tmp_path / layer
    fake.mkdir(exist_ok=True)
    real = layers.load(S.DEFAULT_PINS[layer])
    (fake / "v1.json").write_text(Path(real.__file__).with_name("v1.json").read_text(encoding="utf-8"), encoding="utf-8")
    return type("Stub", (), {"__file__": str(fake / "v1.py"), "LAYER": layer, "VERSION": 1, "IMPLEMENTS": 1, "RECIPE": "v1.json",
                            "CODE": {}, "PROMPT": {}, "DRAFT": {}, "CHECK": {}, "WORDS": words, "LAYOUT": layout})


def test_c5_case_5_compiles_each_part_with_sample_inputs(tmp_path):
    words, layout = split_of("priority")                  # the version's own words, which no part of Priority may be without
    assert C.case_5(_stub("priority", words, layout, tmp_path)) == [], "the words serve"

    def broken(edit):
        w, l = {g: {p: dict(v) for p, v in parts.items()} for g, parts in words.items()}, {g: dict(parts) for g, parts in layout.items()}
        edit(w, l)
        return C.case_5(_stub("priority", w, l, tmp_path))
    assert broken(lambda w, l: l["bargain"].update(line=l["bargain"]["line"].replace("{returns}", ""))) == \
        ["priority/v1: bargain.line: the layout leaves out the answer contract"]
    assert broken(lambda w, l: l["bargain"].update(cost=l["bargain"]["cost"].replace("{{room}}", "{{room}} {{budget}}"))) == \
        ["priority/v1: bargain.cost: the layout holds {{budget}} and the app fills no such input"]
    assert broken(lambda w, l: l["bargain"].update(engine=l["bargain"]["engine"].replace("{task}\n", ""))) == \
        ["priority/v1: bargain.engine: the layout never reads the field task"]
    assert broken(lambda w, l: w["bargain"]["engine"].pop("task")) == \
        ["priority/v1: bargain.engine: the layout holds {task} and WORDS holds no task"]
    assert broken(lambda w, l: l["bargain"].update(extra="{task}")) == ["priority/v1: bargain.extra has a LAYOUT and no WORDS"]
    assert broken(lambda w, l: (w["bargain"].update(extra={"task": "x"}), l["bargain"].update(extra="{task}"))) == \
        ["priority/v1: bargain.extra.task: Priority has no part bargain.extra", "priority/v1: bargain.extra: Priority has no part bargain.extra"]
    assert broken(lambda w, l: l["goal"].update(skills="{items}\n{{a}}")) == \
        ["priority/v1: goal.skills: the layout holds {{a}} and the app fills no such input"]


def test_c5_case_5_finds_the_returns_in_the_compiled_part_and_no_marker_left(tmp_path, monkeypatch):
    words, layout = split_of("audit")
    fake = _stub("audit", words, layout, tmp_path)
    assert C.case_5(fake) == []
    # a layout that holds {returns} but whose part's contract was changed under it: the compile no longer holds it verbatim
    monkeypatch.setitem(S.PROMPTS["audit"]["judge"]["judge"], "returns", "Return ONLY a JSON object: {\"x\": 1}.")
    assert C.case_5(fake) == [], "{returns} is filled with the interface's own, so the contract is in the compiled part by construction"
    monkeypatch.undo()
    # a value that carries a marker of its own into the compiled part is found
    words["goal"]["does"]["text"] = "reads {text} as it stands"
    assert C.case_5(fake) == ["audit/v1: goal.does: the compiled part still holds {text}"]
