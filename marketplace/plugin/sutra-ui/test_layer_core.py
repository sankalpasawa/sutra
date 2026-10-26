"""The typed owner values, the interface API, the page fields and views, and the typed options (PRD amendment A1.15 to
A1.17; W1-CORE K2, steps C6 to C10).

C6   {ref}/instructions.json: the owner's typed value for one prompt field, asked, stamped and read by the next run;
     words() lays the values over the implementation's defaults; a value equal to the default is removed; an earlier
     whole-file change is kept as the owner's note, with one tell
C7   the API: POST /{ref}/instructions takes {fn, group, part, field, value}, GET /{ref}/layers describes the
     interface, and a SchemaFault is 422 NOT_IN_SCHEMA
C8   function() reads the page fields from S.LAYERS and its hears and checks rows from S.HEARS and S.CHECKS
C9   _j2_part returns the pinned implementation's view() when it validates, else today's body with j2_faults
C10  W.option carries its kind (the id's prefix) and its params; the line request validates as act.line_request

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import copy
import json
import re
from pathlib import Path

import pytest

import layers
import layers.prompts as P
import layer_schema as S

HERE = Path(__file__).resolve().parent


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "0")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.setattr(layers, "_TOLD", set())
    return tmp_path / "departments"


def modules():
    import engine_runtime as R
    import website_dept as W
    return W, R


def born(home, ref="dref-core"):
    W, _ = modules()
    W.create(ref, "Core Website", None)
    return ref


def holding(monkeypatch, layer, words, layout):
    """The layer's implementation, made to hold `words` and `layout` for the duration of the test."""
    module = layers.load(S.DEFAULT_PINS[layer])
    monkeypatch.setattr(module, "WORDS", words)
    monkeypatch.setattr(module, "LAYOUT", layout)
    return module


def stored(ref):
    W, _ = modules()
    p = W.ddir(ref) / "instructions.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def told(ref, word="instructions"):
    _, R = modules()
    return [str(p["payload"]["done"]) for p in R.board(ref) if p["payload"].get("word") == word and p["payload"].get("done")]


TAKE = ("identity", "take", "take")
RECOGNISE = ("identity", "take", "recognise")


# ---- C6 · typed owner values ------------------------------------------------------------------------------------------
def test_c6_words_lay_the_owners_values_over_the_defaults_and_nothing_else(home):
    ref = born(home)
    shipped = P.defaults(ref, *TAKE)
    assert set(shipped) == {"task", "guidance"} and P.words(ref, *TAKE) == shipped
    assert P.store(ref, *TAKE, "task", "Judge one request, kindly.") == "set"
    got = P.words(ref, *TAKE)
    assert got == dict(shipped, task="Judge one request, kindly.") and P.defaults(ref, *TAKE) == shipped, "defaults stay the defaults"
    assert P.words(ref, *RECOGNISE) == P.defaults(ref, *RECOGNISE), "another part is untouched"
    assert P.words("dref-other", *TAKE) == shipped and P.words(None, *TAKE) == shipped, "so is another department, or none"
    assert P.owner_values(ref, *TAKE) == {"task": "Judge one request, kindly."}
    e = P.owner_entry(ref, *TAKE, "task")
    assert e["value"] == "Judge one request, kindly." and re.match(r"^\d{4}-\d\d-\d\d", e["at"]) and "ask" not in e
    assert P.owner_entry(ref, *TAKE, "guidance") is None
    got["task"] = "mutated"
    assert P.words(ref, *TAKE)["task"] == "Judge one request, kindly.", "a caller cannot change what the department reads"


def test_c6_a_list_field_is_laid_over_whole(home):
    ref = born(home)
    assert P.store(ref, "identity", "goal", "skills", "items", ["judge a request", "gate an effect"], ask="a-1") == "set"
    assert P.words(ref, "identity", "goal", "skills")["items"] == ["judge a request", "gate an effect"]
    assert P.owner_entry(ref, "identity", "goal", "skills", "items")["ask"] == "a-1"
    import engine_runtime as R
    assert R._goal_of(ref, "Identity")[1] == ["judge a request", "gate an effect"], "the skills an agent is told"
    assert R._goal_of("dref-other", "Identity")[1] == P.defaults(None, "identity", "goal", "skills")["items"]


def test_c6_a_value_the_interface_no_longer_takes_is_not_used(home):
    ref = born(home)
    P.store(ref, *TAKE, "task", "Judge one request, kindly.")
    doc = stored(ref)
    doc["values"]["identity"]["take"]["take"]["task"]["value"] = "Judge {{words}}"      # a hand-edited file
    (P.values_path(ref)).write_text(json.dumps(doc), encoding="utf-8")
    assert P.owner_values(ref, *TAKE) == {} and P.words(ref, *TAKE) == P.defaults(ref, *TAKE)
    (P.values_path(ref)).write_text("{not json", encoding="utf-8")
    assert P.owner_doc(ref) == {"schema_version": 1, "values": {}} and P.words(ref, *TAKE) == P.defaults(ref, *TAKE)


def test_c6_store_writes_whole_and_atomically_through_the_sink(home):
    ref = born(home)
    P.store(ref, *TAKE, "task", "Judge one request, kindly.", ask="a-1")
    P.store(ref, *RECOGNISE, "task", "Recognise the kind of words.")
    doc = stored(ref)
    assert S.validate_instructions(doc) == [] and S.validate("instructions", doc) == []
    assert doc["schema_version"] == 1 and set(doc["values"]) == {"identity"}
    assert set(doc["values"]["identity"]["take"]) == {"take", "recognise"}
    assert not list(P.values_path(ref).parent.glob("*.tmp")), "written beside itself and moved into place"
    # the sink reads the values, not the shape alone: a value past its field's type is a fault in itself
    W, _ = modules()
    bad = copy.deepcopy(doc)
    bad["values"]["identity"]["take"]["take"]["task"]["value"] = "x" * 1201
    with S.expect_refused("instructions") as met:
        W._write(P.values_path(ref), bad)
    assert met and "longer than 1200" in met[0]
    P.store(ref, *TAKE, "task", "Judge one request, kindly.")        # leave the file as the owner stamped it


def test_c6_a_value_equal_to_the_default_is_removed_and_a_later_default_reaches_the_department(home, monkeypatch):
    ref = born(home)
    shipped = P.defaults(ref, *TAKE)
    assert P.store(ref, *TAKE, "task", shipped["task"]) == "same" and stored(ref) is None, "nothing to keep"
    assert P.store(ref, *TAKE, "task", "Judge it kindly.") == "set"
    assert P.store(ref, *TAKE, "task", "Judge it kindly.") == "same"
    assert P.store(ref, *TAKE, "guidance", "go or ask.") == "set"
    assert P.store(ref, *TAKE, "task", shipped["task"]) == "removed"
    assert set(stored(ref)["values"]["identity"]["take"]["take"]) == {"guidance"}, "only the changed field stays"
    assert P.store(ref, *TAKE, "guidance", shipped["guidance"]) == "removed"
    assert stored(ref) is None, "a document with nothing in it goes"
    # an update ships other words: a department with no value reads them, one with a value keeps its own
    words, layout = {}, {}
    for g, p in (("take", "take"),):
        words.setdefault(g, {})[p], layout.setdefault(g, {})[p] = P.split(g, p, P.md_part("identity", g, p))
    monkeypatch.setattr(layers.load("identity/v1"), "WORDS", words)
    monkeypatch.setattr(layers.load("identity/v1"), "LAYOUT", layout)
    P.store(ref, *TAKE, "task", "Judge it kindly.")
    new = copy.deepcopy(words)
    new["take"]["take"]["task"] = "Judge one request from the owner, with care."
    monkeypatch.setattr(layers.load("identity/v1"), "WORDS", new)
    assert P.words(ref, *TAKE)["task"] == "Judge it kindly."
    assert P.words("dref-other", *TAKE)["task"] == "Judge one request from the owner, with care."
    assert P.store(ref, *TAKE, "task", "Judge one request from the owner, with care.") == "removed" and stored(ref) is None


def test_c6_store_refuses_in_plain_words_and_writes_nothing(home):
    ref = born(home)
    for field, value, why in (("task", "Judge {{words}}", "task cannot hold '{{' or '}}', which only the app writes"),
                              ("task", "Judge }} it", "task cannot hold '{{' or '}}'"),
                              ("task", "Return ONLY yes", "task cannot hold 'Return ONLY': the shape of the answer belongs to the app"),
                              ("task", "", "task is empty"), ("task", "x" * 1201, "task is longer than 1200 characters"),
                              ("task", 7, "task has to be words"), ("task", None, "task has to be words")):
        with pytest.raises(ValueError) as cm:
            P.store(ref, *TAKE, field, value)
        assert why in str(cm.value)
    with pytest.raises(ValueError, match="colour"):
        P.store(ref, *TAKE, "colour", "red")
    with pytest.raises(ValueError, match="has no part"):
        P.store(ref, "identity", "take", "nowhere", "task", "x")
    with pytest.raises(ValueError, match="longer than 400"):
        P.store(ref, "identity", "goal", "does", "text", "x" * 401)
    with pytest.raises(ValueError, match="item 2"):
        P.store(ref, "identity", "goal", "skills", "items", ["fine", "x" * 161])
    assert stored(ref) is None, "nothing was written"


def test_c6_plain_faults_say_what_the_interface_says_in_the_owners_words():
    got = P.plain_faults("task", ["$: shorter than 1", "$: longer than 20", "$[2]: longer than 160", "$: holds a line break",
                                  "$: holds a control character", "$: fewer than 1 items", "$: more than 12 items", "$: is not a list",
                                  "$: something else the interface will one day say"])
    assert got == ["task is empty", "task is longer than 20 characters", "task (item 3) is longer than 160 characters",
                   "task must be one line", "task holds a character that cannot be shown", "task needs at least 1 of them",
                   "task can hold at most 12 of them", "task has to be a list", "task something else the interface will one day say"]


def test_c6_prompt_lays_the_owners_value_over_the_fallback_and_over_a_module_that_holds_words(home, monkeypatch):
    ref = born(home)
    inputs = {n: "<%s>" % n for n in S.PROMPTS["identity"]["take"]["recognise"]["inputs"]}
    shipped = P.prompt(ref, *RECOGNISE, **inputs)
    P.store(ref, *RECOGNISE, "task", "Recognise, in few words, the kind.")
    mine = P.prompt(ref, *RECOGNISE, **inputs)
    assert mine.startswith("Recognise, in few words, the kind.\nTHE GOAL: <goal>") and mine != shipped
    assert mine.endswith(S.PROMPTS["identity"]["take"]["recognise"]["returns"]), "the answer's shape is the app's"
    assert P.prompt("dref-other", *RECOGNISE, **inputs) == shipped, "another department is sent the shipped words"
    # the same through a module that holds its own words and layout
    words, layout = {"take": {"recognise": {"task": "Shipped task."}}}, {"take": {"recognise": "{task}\nTHE GOAL: {{goal}}\n{returns}"}}
    holding(monkeypatch, "identity", words, layout)
    assert P.prompt("dref-other", *RECOGNISE, goal="G").startswith("Shipped task.\nTHE GOAL: G\n")
    assert P.prompt(ref, *RECOGNISE, goal="G").startswith("Recognise, in few words, the kind.\nTHE GOAL: G\n"), "the owner's value, not the module's"
    P.store(ref, *RECOGNISE, "task", "Shipped task.")
    assert stored(ref) is None, "equal to the module's default: removed"


def test_c6_a_missing_input_still_raises_with_the_part_named_after_an_owner_value(home):
    ref = born(home)
    P.store(ref, *RECOGNISE, "task", "Recognise the kind.")
    with pytest.raises(ValueError, match=r"Identity's take instructions, recognise: the app fills no \{\{goal\}\}"):
        P.prompt(ref, *RECOGNISE, words="W", facts="F")


def test_c6_a_value_is_never_scanned_for_markers_when_it_is_laid_over_the_layout(home):
    ref = born(home)
    P.store(ref, "identity", "goal", "skills", "items", ["use {task} and {returns} as they are"])
    assert P.words(ref, "identity", "goal", "skills")["items"] == ["use {task} and {returns} as they are"]
    P.store(ref, *TAKE, "task", "Judge {guidance} or {returns} as written.")
    inputs = {n: "<%s>" % n for n in S.PROMPTS["identity"]["take"]["take"]["inputs"]}
    assert P.prompt(ref, *TAKE, **inputs).startswith("Judge {guidance} or {returns} as written.\n"), "a brace in a value is only a brace"


def test_c6_answer_keys_are_the_contracts_own_keys_and_cover_what_each_step_returns(home):
    _, R = modules()
    assert P.answer_keys(S.PROMPTS["identity"]["take"]["take"]["returns"]) == ["verdict", "why", "unsure", "rule", "thin"]
    assert P.answer_keys(S.PROMPTS["priority"]["bargain"]["line"]["returns"]) == ["answer", "why", "keep"]
    assert P.answer_keys(None) == [] and P.answer_keys("no object here") == []
    for layer in S.FUNCTION_LAYERS:
        for group, parts in S.PROMPTS[layer].items():
            for part, spec in parts.items():
                keys = P.answer_keys(spec["returns"])
                assert bool(keys) == bool(spec["returns"]), (layer, group, part)
                for sid in ([spec["read_by"]] if isinstance(spec["read_by"], str) else list(spec["read_by"] or [])):
                    assert set(R.step_def(sid)[1].get("out") or {}) <= set(keys), (sid, keys)


def test_c6_instructions_view_is_the_groups_parts_and_fields_of_the_interface(home):
    ref = born(home)
    _, R = modules()
    for layer in S.FUNCTION_LAYERS:
        v = R.instructions_view(ref, layer)
        assert [g["group"] for g in v] == list(S.PROMPTS[layer]), layer
        for g in v:
            assert g["lead"] == S.GROUPS[layer][g["group"]] and g["kept"] is None
            assert [p["part"] for p in g["parts"]] == list(S.PROMPTS[layer][g["group"]])
            for p in g["parts"]:
                spec = S.PROMPTS[layer][g["group"]][p["part"]]
                assert [f["field"] for f in p["fields"]] == list(spec["fields"])
                assert p["answers"] == P.answer_keys(spec["returns"]) and len(p["inputs"]) == len(spec["inputs"])
                assert p["read"] is ((layer, g["group"], p["part"]) != ("adaptation", "decide", "note"))
                for f in p["fields"]:
                    shape = S.DEFS[spec["fields"][f["field"]]]
                    listed = f["type"] == "list"
                    assert listed == (shape["type"] == "array") and f["type"] in ("text", "list")
                    one = shape["items"] if listed else shape
                    assert (f["max"], f["min"]) == (one["maxLength"], one["minLength"])
                    assert f["max_items"] == (shape["maxItems"] if listed else None)
                    assert f["multiline"] is bool(one["x-field"]["multiline"])
                    assert f["value"] == P.defaults(ref, layer, g["group"], p["part"])[f["field"]] and f["as_shipped"] is True and f["waits"] is None
    import functions_view as FV
    for layer in S.FUNCTION_LAYERS:
        text = json.dumps(R.instructions_view(ref, layer))
        assert str(home) not in text and ".md" not in text and not FV.PATHLIKE.search(text), "names, never paths"


def test_c6_the_view_names_what_the_app_fills_and_what_the_step_answers_with(home):
    ref = born(home)
    _, R = modules()
    take = next(p for g in R.instructions_view(ref, "identity") if g["group"] == "take" for p in g["parts"] if p["part"] == "take")
    assert take["inputs"] == ["the goal", "the rules", "the request", "what code read", "how complete the request is"]
    assert take["answers"] == ["verdict", "why", "unsure", "rule", "thin"] and take["read_by"] == ["identity.take"] and take["read"] is True
    gate = next(p for g in R.instructions_view(ref, "identity") if g["group"] == "take" for p in g["parts"] if p["part"] == "gate")
    assert gate["read_by"] == ["identity.gate", "identity.wait_engine", "identity.judge"]
    note = next(p for g in R.instructions_view(ref, "adaptation") if g["group"] == "decide" for p in g["parts"])
    assert (note["part"], note["read"], note["read_by"], note["inputs"], note["answers"]) == ("note", False, [], [], [])
    does = next(p for p in R.instructions_view(ref, "audit")[0]["parts"] if p["part"] == "does")
    assert does["read"] is True and does["read_by"] == [] and does["fields"][0]["max"] == 400, "the card reads it; no step does"
    assert all(n in R.INPUT_SAYS for layer in S.FUNCTION_LAYERS for gs in S.PROMPTS[layer].values() for sp in gs.values() for n in sp["inputs"])


def test_c6_the_ask_files_a_typed_change_through_identity_and_the_stamp_writes_it(home):
    ref = born(home)
    W, R = modules()
    a = R.instructions_ask(ref, "Identity", " Take ", "RECOGNISE", "task", "  Recognise, in few words, the kind.\r\n")
    S.validate("identity.ask", a) == [] or pytest.fail("the ask does not fit the interface")
    assert (a["kind"], a["fn"], a["group"], a["part"], a["field"], a["status"]) == ("instructions", "identity", "take", "recognise", "task", "pending")
    assert a["value"] == "Recognise, in few words, the kind." and a["text"] == "Change Identity's recognise task to your words"
    board = [p for p in R.board(ref) if p["thread"] == a["thread"]]
    assert [(p["src"], p["dst"], p["msg_type"]) for p in board] == [("Identity", ["Owner"], "request")]
    assert board[0]["payload"]["objective"].endswith("Stamp to use them from the next run, or say no to keep them as they are.")
    assert stored(ref) is None, "nothing changes until the stamp"
    with pytest.raises(ValueError, match="already waits for your stamp"):
        R.instructions_ask(ref, "identity", "take", "recognise", "task", "Another.")
    g = next(g for g in R.instructions_view(ref, "identity") if g["group"] == "take")
    assert next(f for f in g["parts"][0]["fields"])["waits"] == {"ask": a["id"], "at": a["created"]}
    W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=200)
    assert P.words(ref, *RECOGNISE)["task"] == "Recognise, in few words, the kind."
    assert stored(ref)["values"]["identity"]["take"]["recognise"]["task"]["ask"] == a["id"]
    assert told(ref) == ["Identity's recognise task now reads as you changed it; the next run uses it."]
    again = R.instructions_ask(ref, "identity", "take", "recognise", "task", "Recognise it, plainly.")      # nothing waits any more
    W.decide_ask(ref, again["id"], False)
    assert P.words(ref, *RECOGNISE)["task"] == "Recognise, in few words, the kind.", "a no changes nothing"


def test_c6_an_earlier_whole_file_change_is_kept_as_a_note_with_one_tell_and_no_run_reads_it(home):
    ref = born(home)
    W, R = modules()
    old = W.ddir(ref) / "prompts" / "audit" / "judge.md"
    old.parent.mkdir(parents=True)
    old.write_text("Check it.\n\n## judge\n\nLook only at the front page.\n", encoding="utf-8")
    sent = P.prompt(ref, "audit", "judge", "judge", brief="B", filed="F", pages="P")
    assert "front page" not in sent, "no run reads it"
    assert told(ref) == [] and stored(ref) is None, "the record is made by the first read of Settings, not before"
    v = R.instructions_view(ref, "audit")
    note = "Your earlier change to Audit's judge is kept as a note; change the field again in Settings to use it."
    assert told(ref) == [note] and [g["group"] for g in v if g["kept"]] == ["judge"]
    for _ in range(3):
        R.instructions_view(ref, "audit")
    assert told(ref) == [note], "once"
    assert S.validate_instructions(stored(ref)) == [] and list(stored(ref)["kept"]) == ["audit/judge"] and stored(ref)["values"] == {}
    assert P.prompt(ref, "audit", "judge", "judge", brief="B", filed="F", pages="P") == sent
    assert old.read_text(encoding="utf-8").endswith("front page.\n"), "the owner's file is as they left it"
    # a department of the layer's other file is told about that file when it is first read, and not before
    other = W.ddir(ref) / "prompts" / "identity" / "take.md"
    other.parent.mkdir(parents=True)
    other.write_text("Take it.\n", encoding="utf-8")
    R.instructions_view(ref, "audit")
    assert told(ref) == [note]
    R.instructions_view(ref, "identity")
    assert told(ref) == [note, "Your earlier change to Identity's take is kept as a note; change the field again in Settings to use it."]
    # the owner's value is stored beside the note, and a value taken away leaves the note
    P.store(ref, "audit", "judge", "judge", "guidance", "At most two findings.")
    assert set(stored(ref)) >= {"kept", "values"}
    P.store(ref, "audit", "judge", "judge", "guidance", P.defaults(ref, "audit", "judge", "judge")["guidance"])
    assert stored(ref)["values"] == {} and "audit/judge" in stored(ref)["kept"]
