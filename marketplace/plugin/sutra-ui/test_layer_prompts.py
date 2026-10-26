"""The typed prompt compiler (PRD amendment A1.16; W1-CORE K1, steps C3, C4 and C5).

C3  layers/prompts.py: compile_layout, words, prompt and faults, with the .md reader as the fallback. A stub module holding
    WORDS and LAYOUT for a part compiles to exactly the .md text; a marker with no value raises with the part named; a value
    is never scanned again; the M2.1 and M2.2 tests (test_function_prompts.py) pass unchanged on the fallback.
C4  `python -m layers.prompts --extract <layer>` prints WORDS and LAYOUT by the split rule, checks each part's returns,
    inputs and fields against the interface, and the words compiled back are the .md part byte for byte, for every part of
    the five function layers. No part needed a hand fix.
C5  the snapshot renders what runs: a stub overriding a prompt through the registry changes the rendered text, and the stubs
    still pass the contract, whose case 5 compiles each part with sample inputs.

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import ast
import importlib
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import layers
import layers.contract as C
import layers.prompts as P
import layer_schema as S

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
    """What the .md bundle says for a part, its inputs filled: the text the compiler must give back."""
    return P.SLOT.sub(lambda m: str(inputs[m.group(1)]), P.md_part(layer, group, part))


def split_of(layer, *groups):
    """WORDS and LAYOUT for the groups of a layer, by the split rule over its .md files (the C4 extractor prints the same)."""
    words, layout = {}, {}
    for group in groups or S.PROMPTS[layer]:
        for part in S.PROMPTS[layer][group]:
            words.setdefault(group, {})[part], layout.setdefault(group, {})[part] = P.split(group, part, P.md_part(layer, group, part))
    return words, layout


def all_parts():
    return [(layer, group, part) for layer in S.FUNCTION_LAYERS for group, parts in S.PROMPTS[layer].items() for part in parts]


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


def test_c3_the_part_is_named_in_the_error_on_the_fallback_too(runtime):
    with pytest.raises(ValueError, match=r"^Identity's take instructions, gate: the app fills no \{\{engine\}\}$"):
        P.prompt(None, *GATE, rules="r")
    with pytest.raises(ValueError, match=r"^Identity's take instructions have no part nothing$"):
        P.prompt(None, "identity", "take", "nothing")
    with pytest.raises(ValueError, match=r"^Audit's judge instructions have no part gate$"):
        P.words(None, "audit", "judge", "gate")


def test_c3_a_stub_holding_words_and_layout_for_identity_take_gate_renders_exactly_the_md_text(runtime, monkeypatch):
    want = md_part(*GATE, rules="the rules", engine="the engine")
    assert want.startswith("An engine asks whether it may start.\nTHE RULES: the rules\nTHE ENGINE: the engine\n\nReturn ONLY")
    assert P.prompt(None, *GATE, rules="the rules", engine="the engine") == want, "on the fallback"
    words, layout = split_of("identity", "take")
    holding(monkeypatch, "identity", {"take": {"gate": words["take"]["gate"]}}, {"take": {"gate": layout["take"]["gate"]}})
    assert P._module(None, "identity", "take", "gate") is not None, "the pinned module holds the part now"
    assert P.prompt(None, *GATE, rules="the rules", engine="the engine") == want, "from the stub"
    assert layers.prompt(None, *GATE, rules="the rules", engine="the engine") == want
    # the stub's words are what is sent: change one and the text changes
    words["take"]["gate"]["task"] = "A step asks whether it may run."
    holding(monkeypatch, "identity", {"take": {"gate": words["take"]["gate"]}}, {"take": {"gate": layout["take"]["gate"]}})
    assert P.prompt(None, *GATE, rules="the rules", engine="the engine") == want.replace("An engine asks whether it may start.", "A step asks whether it may run.")
    # a part the stub does not hold is still read from the bundle
    assert P.prompt(None, "identity", "take", "rule", goal="g", rules="r", words="w") == md_part("identity", "take", "rule", goal="g", rules="r", words="w")
    # the compiler is reached by the runtime's own name for it
    assert runtime._prompt(*GATE, ref=None, rules="the rules", engine="the engine").startswith("A step asks whether it may run.")


def test_c3_a_stub_missing_an_input_raises_with_the_part_named(runtime, monkeypatch):
    words, layout = split_of("identity", "take")
    holding(monkeypatch, "identity", {"take": {"gate": words["take"]["gate"]}}, {"take": {"gate": layout["take"]["gate"]}})
    with pytest.raises(ValueError, match=r"^Identity's take instructions, gate: the app fills no \{\{engine\}\}$"):
        P.prompt(None, *GATE, rules="the rules")


def test_c3_words_are_the_stubs_defaults_or_the_md_parts_fields(runtime, monkeypatch):
    got = P.words(None, "identity", "take", "take")
    assert sorted(got) == ["guidance", "task"] and got["task"] == "Judge one request from the owner."
    assert P.words(None, "identity", "goal", "skills")["items"][0] == "recognise a task, a query, a directive, feedback or a new idea"
    assert P.words(None, "identity", "goal", "close") == {} and layers.words(None, "identity", "goal", "close") == {}
    note = P.words(None, "adaptation", "decide", "note")["text"]
    assert note.startswith("In this version the choice is made by code") and note.endswith("never applies one itself.")
    # a copy: the stub's own words are never handed out to be changed
    mine = {"take": {"gate": {"task": "Mine."}}}
    holding(monkeypatch, "identity", mine, {"take": {"gate": "{task}"}})
    P.words(None, *GATE)["task"] = "changed"
    assert mine["take"]["gate"]["task"] == "Mine."
    # a layer's module that holds the words is read before the bundle, for what an agent is told it is
    holding(monkeypatch, "identity", {"goal": {"does": {"text": "does it differently"}, "skills": {"items": ["x", "y"]}}},
            {"goal": {"does": "{text}", "skills": "{items}"}})
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
    assert {fn: {g: list(parts) for g, parts in files.items()} for fn, files in R.INSTRUCTIONS.items()} == {
        "identity": {"goal": ["does", "skills", "close"], "completeness": ["thin", "enough"],
                     "take": ["recognise", "take", "answer", "rule", "weigh", "gate"]},
        "adaptation": {"goal": ["does", "skills"], "sense": ["shape"], "decide": [], "make": ["line", "refused"]},
        "priority": {"goal": ["does", "skills"], "bargain": ["line", "engine", "cost"]},
        "coordination": {"goal": ["does", "skills"], "tie": ["tie"]},
        "audit": {"goal": ["does", "skills"], "judge": ["judge"]}}
    assert R.INSTRUCTIONS["identity"]["completeness"]["enough"] == ("words", "asked", "goal", "items", "rules", "owner", "budget", "confirm")
    for layer, group, part in all_parts():
        if layer == "adaptation" and group == "decide":
            continue
        assert R.INSTRUCTIONS[layer][group][part] == tuple(S.PROMPTS[layer][group][part]["inputs"])


def test_c3_the_old_names_are_thin_aliases_of_the_compiler(runtime):
    R = runtime
    assert R._parts("Lead.\n\n## a\n\nx") == P.parts_of("Lead.\n\n## a\n\nx") == ("Lead.", {"a": "x"})
    assert R._instruction("audit", "judge") == P.instruction("audit", "judge")
    assert R._prompt("coordination", "tie", "tie", None, ready="a", what="b", order="c", waiting="d") == \
        P.prompt(None, "coordination", "tie", "tie", ready="a", what="b", order="c", waiting="d")
    assert R.bundle_faults() == P.faults() == []
    assert R.instruction_faults("audit", "judge", "") == P.instruction_faults("audit", "judge", "") != []


def test_c3_faults_name_what_keeps_a_typed_part_from_serving(runtime, monkeypatch):
    R = runtime
    words, layout = split_of("identity", "take")
    good = ({"take": {"gate": words["take"]["gate"]}}, {"take": {"gate": layout["take"]["gate"]}})
    holding(monkeypatch, "identity", *good)
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
        w, l = {"take": {"gate": dict(words["take"]["gate"])}}, {"take": {"gate": layout["take"]["gate"]}}
        edit(w, l)
        holding(monkeypatch, "identity", w, l)
        assert [f for f in P.faults() if fault in f] == ["Identity's take instructions, gate: " + fault], fault
    holding(monkeypatch, "identity", {"take": {"nothing": {"task": "x"}}}, {"take": {"nothing": "{task}"}})
    assert "Identity's take instructions, nothing: Identity has no part take.nothing" in P.faults()


def test_c3_a_file_every_part_of_which_is_typed_needs_no_bundle_file(runtime, monkeypatch, tmp_path):
    words, layout = split_of("audit", "judge")
    bundle = tmp_path / "bundle"
    shutil.copytree(runtime.PROMPTS_DIR, bundle)
    (bundle / "audit" / "judge.md").unlink()
    monkeypatch.setattr(runtime, "PROMPTS_DIR", bundle)
    assert P.faults() == ["Audit's judge instructions are missing from the bundle"]
    holding(monkeypatch, "audit", {"judge": words["judge"]}, {"judge": layout["judge"]})
    assert P.faults() == [], "the words are the module's now"
    (bundle / "audit" / "goal.md").unlink()
    assert P.faults() == ["Audit's goal instructions are missing from the bundle"], "a file with a part still on the fallback is needed"


# ---- C4 · the extractor and the split proof -----------------------------------------------------------------------------
RETURNS = 'Return ONLY a JSON object: {"ok": bool, "rows": [{"a": str}]}.'


def test_c4_returns_is_the_json_sentence_wherever_it_stands():
    text = "before. " + RETURNS + " after."
    assert text[slice(*P.returns_span(text))] == RETURNS
    assert P.returns_span("Return ONLY a JSON object: {\"a\": 1}{{refused}}") == (0, len('Return ONLY a JSON object: {"a": 1}')), "no full stop to take"
    assert P.returns_span("no contract here") is None and P.returns_span("Return ONLY a JSON object: {\"a\": ") is None
    assert P.returns_span("Return ONLY a list") is None, "only the JSON object sentence is a contract"


def test_c4_the_split_rule_on_small_parts():
    # rule 3 and 5: the task is the text before the first line holding an input; labels and inputs stay in the layout
    f, l = P.split("g", "p", "Say it.\nTHE GOAL: {{goal}}\nTHE WORDS:\n{{words}}\n\n" + RETURNS)
    assert f == {"task": "Say it."} and l == "{task}\nTHE GOAL: {{goal}}\nTHE WORDS:\n{{words}}\n\n{returns}"
    # rule 4: the guidance is the run of lines after returns that hold no input, up to a blank line; the rest stays
    f, l = P.split("g", "p", "Say it.\nIN: {{x}}\n\n" + RETURNS + "\nfirst.\nsecond.\n\nTHE END:\n{{y}}")
    assert f == {"task": "Say it.", "guidance": "first.\nsecond."} and l == "{task}\nIN: {{x}}\n\n{returns}\n{guidance}\n\nTHE END:\n{{y}}"
    f, l = P.split("g", "p", "Say it.\nIN: {{x}}\n\n" + RETURNS + "\nfirst.\n{{completeness}}")
    assert f == {"task": "Say it.", "guidance": "first."} and l == "{task}\nIN: {{x}}\n\n{returns}\n{guidance}\n{{completeness}}"
    # the guidance may stand on the line of the returns, and the contract may stand in the middle of a paragraph
    f, l = P.split("g", "p", "Say it.\nIN: {{x}}\n\n" + RETURNS + " But gently.")
    assert f == {"task": "Say it.", "guidance": "But gently."} and l == "{task}\nIN: {{x}}\n\n{returns} {guidance}"
    f, l = P.split("g", "p", "Read it. " + RETURNS + " Be brief.\n\nTHE PAGES:\n{{pages}}")
    assert f == {"task": "Read it.", "guidance": "Be brief."} and l == "{task} {returns} {guidance}\n\nTHE PAGES:\n{{pages}}"
    # an input on the first line leaves no task, and an input glued to the returns is not its guidance
    f, l = P.split("g", "p", "You are {{who}}.\nIN: {{x}}\n" + RETURNS + "{{refused}}")
    assert f == {} and l == "You are {{who}}.\nIN: {{x}}\n{returns}{{refused}}"
    # rule 6: a part with no returns is its task, and its input lines
    assert P.split("g", "thin", "thin: true when nothing is named.") == ({"task": "thin: true when nothing is named."}, "{task}")
    assert P.split("g", "refused", "REFUSED: {{faults}}. Again.") == ({}, "REFUSED: {{faults}}. Again.")
    assert P.split("g", "p", "Say it.\nIN: {{x}}") == ({"task": "Say it."}, "{task}\nIN: {{x}}")
    # rule 6 and 7: does, skills and the note
    assert P.split("goal", "does", "holds it all") == ({"text": "holds it all"}, "{text}")
    assert P.split("goal", "skills", "- one\n- two words\n  - three") == ({"items": ["one", "two words", "three"]}, "{items}")
    assert P.split("decide", "note", "Code makes this choice.") == ({"text": "Code makes this choice."}, "{text}")


def test_c4_the_extractor_exits_0_for_all_five_and_prints_literals_that_are_the_split(runtime):
    for layer in S.FUNCTION_LAYERS:
        out, err = io.StringIO(), io.StringIO()
        assert P.main(["--extract", layer], out, err) == 0 and err.getvalue() == "", layer
        tree = ast.parse(out.getvalue())
        got = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)}
        words, layout, bad = P.extract(layer)
        assert bad == [] and got == {"WORDS": words, "LAYOUT": layout}, layer
        assert list(got["WORDS"]) == list(S.PROMPTS[layer]), "the interface's groups, in its order"
        assert out.getvalue().startswith("# %s: WORDS and LAYOUT by the split rule" % S.TITLE[layer])


def test_c4_the_command_line_is_python_m_layers_prompts(runtime, tmp_path):
    env = {"PATH": "/usr/bin:/bin", "SUTRA_NATIVE_HOME": str(tmp_path)}
    ok = subprocess.run([sys.executable, "-m", "layers.prompts", "--extract", "audit"], cwd=str(HERE), capture_output=True, text=True, env=env)
    assert ok.returncode == 0 and "LAYOUT = {" in ok.stdout and ok.stderr == "", ok.stderr
    for argv in (["--extract"], ["--extract", "root"], ["--extract", "marketing"], ["audit"]):
        bad = subprocess.run([sys.executable, "-m", "layers.prompts"] + argv, cwd=str(HERE), capture_output=True, text=True, env=env)
        assert bad.returncode == 2 and bad.stdout == "" and "usage: python -m layers.prompts --extract" in bad.stderr, argv


def test_c4_the_extractor_exits_1_and_names_the_part_when_the_split_does_not_match_the_interface(runtime, monkeypatch, tmp_path):
    def run(layer):
        out, err = io.StringIO(), io.StringIO()
        return P.main(["--extract", layer], out, err), err.getvalue().strip().split("\n")
    # returns, inputs and fields are the interface's
    monkeypatch.setitem(S.PROMPTS["identity"]["take"]["gate"], "returns", 'Return ONLY a JSON object: {"verdict": "yes"}.')
    code, said = run("identity")
    assert code == 1 and said == ["Identity's take instructions, gate: the split finds returns "
                                  "'Return ONLY a JSON object: {\"verdict\": \"admit\" | \"wait\" | \"refuse\", \"why\": \"one line\"}.', and the interface "
                                  "'Return ONLY a JSON object: {\"verdict\": \"yes\"}.'"]
    monkeypatch.undo()
    monkeypatch.setitem(S.PROMPTS["audit"]["judge"]["judge"], "inputs", ("brief", "pages"))
    code, said = run("audit")
    assert code == 1 and said == ["Audit's judge instructions, judge: the part asks for the inputs ['brief', 'filed', 'pages'], and the interface ['brief', 'pages']"]
    monkeypatch.undo()
    monkeypatch.setitem(S.PROMPTS["priority"]["bargain"]["cost"], "fields", {"task": "field.task", "guidance": "field.guidance"})
    code, said = run("priority")
    assert code == 1 and said == ["Priority's bargain instructions, cost: the split finds the fields ['task'], and the interface ['guidance', 'task']"]
    monkeypatch.undo()
    # the group's lead and the parts of the file are the interface's
    bundle = tmp_path / "bundle"
    shutil.copytree(runtime.PROMPTS_DIR, bundle)
    monkeypatch.setattr(runtime, "PROMPTS_DIR", bundle)
    text = (bundle / "coordination" / "tie.md").read_text(encoding="utf-8")
    (bundle / "coordination" / "tie.md").write_text(text.replace("How Coordination says", "How Coordination might say"), encoding="utf-8")
    code, said = run("coordination")
    assert code == 1 and said == ["Coordination: the lead of tie is not the interface's"]
    (bundle / "coordination" / "tie.md").write_text(text.replace("## tie", "## ties"), encoding="utf-8")
    code, said = run("coordination")
    assert code == 1 and "Coordination: tie holds the parts ['ties'], and the interface ['tie']" in said
    (bundle / "coordination" / "tie.md").unlink()
    code, said = run("coordination")
    assert code == 1 and said == ["Coordination: the bundle has no file tie"]


def test_c4_compiled_from_its_extracted_words_every_part_is_the_md_part_byte_for_byte(runtime):
    seen = 0
    for layer in S.FUNCTION_LAYERS:
        words, layout, bad = P.extract(layer)
        assert bad == [], bad
        for group, parts in S.PROMPTS[layer].items():
            for part, spec in parts.items():
                md = P.md_part(layer, group, part)
                sample = {n: "<<%s>>" % n for n in spec["inputs"]}
                got = P.compile_layout(layout[group][part], words[group][part], spec["returns"], sample, P.who(layer, group, part))
                assert got == P.SLOT.sub(lambda m: sample[m.group(1)], md), "%s.%s.%s" % (layer, group, part)
                assert spec["returns"] is None or spec["returns"] in md, "returns is the part's own, byte for byte"
                assert set(words[group][part]) == set(spec["fields"]), (layer, group, part)
                seen += 1
    assert seen == len(all_parts()) == 28


def test_c4_the_extracted_words_pass_the_interface_and_the_layouts_serve(runtime):
    for layer in S.FUNCTION_LAYERS:
        words, layout, _ = P.extract(layer)
        for group, parts in words.items():
            for part, values in parts.items():
                assert P.part_faults(layer, group, part, values, layout[group][part]) == [], (layer, group, part)
                for field, value in values.items():
                    assert S.validate_field(layer, group, part, field, value) == [], (layer, group, part, field)


def test_c4_the_split_keeps_the_words_the_md_files_had_for_the_fallback_to_read(runtime):
    """Whatever the owner's whole-file M2.2 copy says, the fallback gives the fields the same split gives."""
    mine = "How to judge.\n\n## gate\n\nA step asks.\nTHE RULES: {{rules}}\nTHE ENGINE: {{engine}}\n\n" + RETURNS + " Go on."
    assert P.parts_of(mine)[1]["gate"].startswith("A step asks.")
    assert P.split("take", "gate", P.parts_of(mine)[1]["gate"])[0] == {"task": "A step asks.", "guidance": "Go on."}
