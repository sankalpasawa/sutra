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
C11  K2 end to end: a department made and run the way a person makes one reads, on every pane, as the interface types it
     (the checks of C1 to C5 are test_layer_registry.py's and test_layer_prompts.py's)

A test that meets a fault of the interface fails (conftest.py); a deliberate one is wrapped in S.expect_refused().
"""
import copy
import importlib
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
        with pytest.raises(S.SchemaFault):                           # refuse mode: the write is refused after its row
            W._write(P.values_path(ref), bad)
    assert met and "longer than 1200" in met[0]
    assert stored(ref) == doc, "nothing was written"


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
    words = copy.deepcopy(layers.load("identity/v1").WORDS)
    layout = copy.deepcopy(layers.load("identity/v1").LAYOUT)
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
    # the whole sentence, so a clause the interface's own message leaves behind (said twice) fails here
    for field, value, why in (("task", "Judge {{words}}", "task cannot hold '{{' or '}}', which only the app writes"),
                              ("task", "Judge }} it", "task cannot hold '{{' or '}}', which only the app writes"),
                              ("task", "Return ONLY yes", "task cannot hold 'Return ONLY': the shape of the answer belongs to the app"),
                              ("task", "", "task is empty"), ("task", "x" * 1201, "task is longer than 1200 characters"),
                              ("task", 7, "task has to be words"), ("task", None, "task has to be words")):
        with pytest.raises(ValueError) as cm:
            P.store(ref, *TAKE, field, value)
        assert str(cm.value) == why
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


def test_c6_a_rewritten_fault_replaces_the_interfaces_whole_message_and_leaves_no_tail_of_it():
    """The interface's message for a marker or a shape word carries a clause of its own after the part the owner's
    words match; the owner's sentence replaces all of it, so no clause is said twice."""
    from layer_schema import validate_field
    for value, said in (("Judge {{words}}", "task cannot hold '{{' or '}}', which only the app writes"),
                        ("Judge it }}", "task cannot hold '{{' or '}}', which only the app writes"),
                        ("Judge it. Return ONLY yes", "task cannot hold 'Return ONLY': the shape of the answer belongs to the app")):
        faults = validate_field(*TAKE[:2], TAKE[2], "task", value)
        assert faults, value
        assert P.plain_faults("task", faults) == [said], (value, faults)
    # a fault the interface says in more words than the table knows is rewritten whole, never half
    tails = P.plain_faults("task", ["$: holds '{{' or '}}', which only the app may write, said some other way",
                                    "$: holds 'Return ONLY': said some other way"])
    assert tails == ["task cannot hold '{{' or '}}', which only the app writes",
                     "task cannot hold 'Return ONLY': the shape of the answer belongs to the app"]


def test_c6_prompt_lays_the_owners_value_over_the_shipped_words_and_over_a_module_that_holds_words(home, monkeypatch):
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
                # every part is read but Adaptation's decide note and a function's own done, which only its page reads (A3.4.6)
                assert p["read"] is ((layer, g["group"], p["part"]) != ("adaptation", "decide", "note") and (g["group"], p["part"]) != ("goal", "done"))
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


# ---- C7 · the API ---------------------------------------------------------------------------------------------------
@pytest.fixture
def api(home):
    import website_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    return TestClient(app)


def post_field(api, ref, **body):
    return api.post("/api/native/%s/instructions" % ref, json=dict({"fn": "identity", "group": "take", "part": "take", "field": "task",
                                                                     "value": "Judge one request, kindly."}, **body))


def test_c7_post_instructions_takes_a_field_and_files_the_ask(api, home):
    ref = born(home)
    r = post_field(api, ref)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    a = r.json()["ask"]
    assert S.validate("identity.ask", a) == [] and (a["kind"], a["fn"], a["group"], a["part"], a["field"]) == ("instructions", "identity", "take", "take", "task")
    assert a["value"] == "Judge one request, kindly." and stored(ref) is None, "nothing changes until the stamp"
    lst = post_field(api, ref, fn="identity", group="goal", part="skills", field="items", value=["judge a request", "gate an effect"])
    assert lst.status_code == 200 and lst.json()["ask"]["value"] == ["judge a request", "gate an effect"]


def test_c7_the_old_body_says_which_part_and_which_field(api, home):
    ref = born(home)
    r = api.post("/api/native/%s/instructions" % ref, json={"fn": "identity", "file": "take", "text": "Judge it."})
    assert (r.status_code, r.json()["detail"]) == (400, "say which part and which field")
    for body in ({"fn": "identity", "group": "take", "part": "take"}, {"fn": "identity", "group": "take", "field": "task"},
                 {"fn": "identity", "part": "take", "field": "task"}, {}, {"group": "", "part": " ", "field": ""}):
        r = api.post("/api/native/%s/instructions" % ref, json=body)
        assert (r.status_code, r.json()["detail"]) == (400, "say which part and which field"), body
    r = api.post("/api/native/%s/instructions" % ref, content="not json", headers={"content-type": "application/json"})
    assert (r.status_code, r.json()["detail"]) == (400, "say which part and which field")
    r = api.post("/api/native/%s/instructions" % ref, json=["a list"])
    assert r.status_code == 400
    r = api.post("/api/native/%s/instructions" % ref, json={"fn": "identity", "group": "take", "part": "take", "field": "task"})
    assert (r.status_code, r.json()["detail"]) == (400, "say what the words should be")
    assert stored(ref) is None and not [a for a in modules()[0].asks(ref) if a["kind"] == "instructions"]


def test_c7_the_errors_are_400_in_plain_words(api, home):
    ref = born(home)
    for body, why in (({"fn": "marketing"}, "no function named marketing"), ({"fn": ""}, "no function named nothing"),
                      ({"group": "voice"}, "Identity has no instructions named voice"),
                      ({"part": "nowhere"}, "Identity's take instructions have no part nowhere"),
                      ({"field": "colour"}, "has no colour you may change"),
                      ({"value": "x" * 1201}, "task is longer than 1200 characters"), ({"value": 5}, "task has to be words"),
                      ({"value": "   "}, "task is empty"), ({"value": P.defaults(ref, *TAKE)["task"]}, "these are the words Identity's take task holds now")):
        r = post_field(api, ref, **body)
        assert r.status_code == 400 and why in r.json()["detail"], (body, r.text)
    # the two words the app keeps are said once, whole: the sentence is the owner's, with none of the interface's tail after it
    for value, said in (("Judge {{words}}", "task cannot hold '{{' or '}}', which only the app writes"),
                        ("Judge it. Return ONLY yes", "task cannot hold 'Return ONLY': the shape of the answer belongs to the app")):
        r = post_field(api, ref, value=value)
        assert r.status_code == 400 and r.json()["detail"] == "these words cannot serve Identity: " + said, (value, r.text)
    assert post_field(api, ref).status_code == 200
    r = post_field(api, ref, value="Judge it, twice.")
    assert r.status_code == 400 and "already waits for your stamp" in r.json()["detail"]


def test_c7_a_ref_that_is_not_a_runtime_department_is_404(api, home, monkeypatch):
    W, _ = modules()
    assert post_field(api, "dref-nobody").status_code == 404 and api.get("/api/native/dref-nobody/layers").status_code == 404
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    W.create("dref-old", "Old Website", None)
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME")
    assert W.dept("dref-old").get("runtime") != 2
    assert post_field(api, "dref-old").status_code == 404
    r = api.get("/api/native/dref-old/layers")
    assert r.status_code == 404 and r.json()["detail"] == "this department does not run on the engine runtime"


def test_c7_get_layers_describes_the_interface_the_department_runs_under(api, home):
    ref = born(home)
    r = api.get("/api/native/%s/layers" % ref)
    assert r.status_code == 200
    got = r.json()
    assert set(got) == {"schema_version", "pins", "available", "standards", "describe"}
    assert got["schema_version"] == S.SCHEMA_VERSION == 2
    assert got["pins"] == S.DEFAULT_PINS and got["available"] == layers.available()
    assert got["standards"] == [{"id": i, "says": s} for i, s, _, _ in S.WORKFLOW_STANDARDS]
    assert [x["id"] for x in got["standards"]][0] == "names_an_engine" and all(set(x) == {"id", "says"} for x in got["standards"])
    assert got["describe"] == S.describe() and got["describe"]["layers"]["identity"]["v1"] == S.LAYERS["identity"]["v1"]
    assert got["describe"]["default_pins"] == S.DEFAULT_PINS and got["describe"]["workflow_standards"][0]["id"] == "names_an_engine"


def test_c7_get_layers_names_a_pin_it_cannot_honour_once(api, home, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # a record that holds a pin the registry cannot find is kept (warn mode), as an older record may be
    ref = born(home)
    W, _ = modules()
    d = W.dept(ref)
    d["layers"] = dict(S.DEFAULT_PINS, audit="audit/v2")
    with S.expect_refused("department") as met:                  # the interface says so when a record is saved with it
        W.save_dept(ref, d)
    assert met and "audit/v2 is no implementation the registry can find" in met[0]
    for _ in range(2):
        assert api.get("/api/native/%s/layers" % ref).json()["pins"] == S.DEFAULT_PINS, "it runs the default"
    assert [r["engine"] for r in W.runs(ref) if "per-department" in str(r.get("what"))] == ["Audit"]


def test_c7_a_schema_fault_is_422_not_in_schema_with_its_first_three_faults(api, home, monkeypatch):
    ref = born(home)
    W, _ = modules()
    boom = S.SchemaFault("department", ["$.a: is wrong", "$.b: is wrong", "$.c: is wrong", "$.d: is wrong"])
    monkeypatch.setattr(W, "set_stopped", lambda *a, **k: (_ for _ in ()).throw(boom))
    r = api.post("/api/native/%s/stop" % ref)
    assert r.status_code == 422
    assert r.json() == {"detail": {"code": "NOT_IN_SCHEMA", "faults": ["$.a: is wrong", "$.b: is wrong", "$.c: is wrong"]}}
    # a read route (sync) and a write route (async) alike
    monkeypatch.setattr(W, "map_view", lambda *a, **k: (_ for _ in ()).throw(boom))
    assert api.get("/api/native/%s/map" % ref).status_code == 422
    monkeypatch.setattr(W, "give_goal", lambda *a, **k: (_ for _ in ()).throw(boom))
    r = api.post("/api/native/%s/goal" % ref, json={"text": "Add a page"})
    assert (r.status_code, r.json()["detail"]["code"]) == (422, "NOT_IN_SCHEMA")
    # a fault that is not the interface's stays what it was
    monkeypatch.setattr(W, "set_stopped", lambda *a, **k: (_ for _ in ()).throw(ValueError("not ours")))
    with pytest.raises(ValueError):
        api.post("/api/native/%s/stop" % ref)


def test_c7_in_refuse_mode_a_write_the_interface_refuses_comes_back_422(api, home, monkeypatch):
    ref = born(home)
    monkeypatch.setattr(S, "MODE", "refuse")
    monkeypatch.setitem(S.DEFS, "identity.ask", S.obj({"id": S.text(3)}, required=("id",), open=False))
    with S.expect_refused("identity.ask") as met:
        r = post_field(api, ref)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "NOT_IN_SCHEMA"
    assert 1 <= len(r.json()["detail"]["faults"]) <= 3 and r.json()["detail"]["faults"] == met[:3]


def boom(*a, **k):
    """A write the interface refuses, met inside a route: four faults, of which the answer says three."""
    raise S.SchemaFault("department", ["$.a: is wrong", "$.b: is wrong", "$.c: is wrong", "$.d: is wrong"])


NOT_IN_SCHEMA = {"detail": {"code": "NOT_IN_SCHEMA", "faults": ["$.a: is wrong", "$.b: is wrong", "$.c: is wrong"]}}


def test_c7_every_router_that_writes_through_the_sink_answers_a_schema_fault_as_422(home, monkeypatch):
    """A SchemaFault is 422 NOT_IN_SCHEMA from j2_api, j2ui_api, dept_api and org2_api as from website_api, in an app of a test's
    own making (no handler registered): one 500 here would go live the day the interface refuses (found by a verifier, 2026-10-26)."""
    import dept_api
    import j2_api
    import j2ui_api
    import org2_api
    import website_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    ref = born(home)
    W, _ = modules()
    monkeypatch.setattr(j2_api.J, "status", boom)                              # a read, then three writes, of the J2 lifecycle
    monkeypatch.setattr(j2_api.J, "start", boom)
    monkeypatch.setattr(j2_api.J, "answer", boom)
    monkeypatch.setattr(j2ui_api, "_known", lambda r: True)                    # the screen's writes: the owner's words, a reset
    monkeypatch.setattr(j2ui_api.SAY, "say_http", boom)
    monkeypatch.setattr(j2ui_api.SAY, "reset", boom)
    monkeypatch.setattr(dept_api, "_engine", boom)                             # the department screen: a read and the pause ask
    monkeypatch.setattr(org2_api.E, "load_domains", boom)                      # the Org screen: a read
    app = FastAPI()
    for router in (j2_api.router, j2ui_api.router, dept_api.router, org2_api.router, website_api.router):
        app.include_router(router)
    c = TestClient(app)
    calls = [("get", "/api/dept/%s/j2" % ref), ("post", "/api/dept/%s/j2/start" % ref), ("post", "/api/departments/%s/j2/answer" % ref),
             ("post", "/j2ui/%s/api/say" % ref), ("post", "/j2ui/%s/api/reset" % ref),
             ("get", "/api/dept/%s/engines/e1/data" % ref), ("post", "/api/dept/%s/engines/e1/pause" % ref),
             ("get", "/api/org2/department/%s" % ref)]
    for method, path in calls:
        r = getattr(c, method)(path)
        assert (r.status_code, r.json()) == (422, NOT_IN_SCHEMA), (path, r.status_code, r.text[:120])
    # a fault that is not the interface's stays what it was
    monkeypatch.setattr(j2_api.J, "status", lambda *a, **k: (_ for _ in ()).throw(ValueError("not ours")))
    with pytest.raises(ValueError):
        c.get("/api/dept/%s/j2" % ref)


def test_c7_the_app_answers_a_schema_fault_from_a_route_of_any_router(home):
    """One handler for the app (A1.4): a plain router, with no route class of its own, is covered by interface_http.install, in an
    app of a test's own making and in the real app, whose handlers hold it."""
    import interface_http
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    def meets():
        boom()

    async def late():
        boom()
    plain = APIRouter()
    plain.get("/plain")(meets)
    plain.post("/plain")(late)
    bare, app = FastAPI(), FastAPI()
    bare.include_router(plain)
    app.include_router(plain)
    assert TestClient(bare, raise_server_exceptions=False).get("/plain").status_code == 500, "without the handler it is the 500 it was"
    interface_http.install(app)
    c = TestClient(app)
    for method in ("get", "post"):
        r = getattr(c, method)("/plain")
        assert (r.status_code, r.json()) == (422, NOT_IN_SCHEMA), method
    import app as A
    assert A.app.exception_handlers[S.SchemaFault] is interface_http.handle
    A.app.add_api_route("/__c7_plain", meets)                                 # a route of the real app with no route class
    try:
        r = TestClient(A.app, base_url="http://127.0.0.1:8330").get("/__c7_plain")
    finally:
        A.app.router.routes.pop()
    assert (r.status_code, r.json()) == (422, NOT_IN_SCHEMA)


# ---- C8 · the page fields from the interface --------------------------------------------------------------------------
PAGE_KEYS = ("vsm", "line", "holds", "hands_to", "keeps", "v1")
BANNED = re.compile(r"\b(?:grant|counter|refus|orders\b|charter|internal system)", re.I)


def test_c8_function_reads_vsm_line_holds_hands_to_keeps_and_v1_from_the_interface(home):
    import functions_view as F
    ref = born(home)
    assert not hasattr(F, "PAGES"), "the pages moved into layer_schema.LAYERS"
    for layer in S.FUNCTION_LAYERS:
        got = F.function(ref, layer)
        for k in PAGE_KEYS:
            assert got[k] == S.LAYERS[layer][k], (layer, k)
        assert got["name"] == S.TITLE[layer] and [j["id"] for j in got["journeys"]] == [j[0] for j in F.JOURNEYS[S.TITLE[layer]]]


def test_c8_a_pane_changes_with_the_interface_it_reads(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    monkeypatch.setitem(S.LAYERS, "priority", dict(S.LAYERS["priority"], line="Prices every proposal. Nothing else.", v1="Version one."))
    got = F.function(ref, "priority")
    assert (got["line"], got["v1"]) == ("Prices every proposal. Nothing else.", "Version one.")
    assert F.function(ref, "audit")["line"] == S.LAYERS["audit"]["line"]


def test_c8_each_panes_hears_row_is_what_the_interface_says_the_layer_hears_in_words(home):
    import functions_view as F
    import owner_words
    ref = born(home)
    for layer in S.FUNCTION_LAYERS:
        row = next(f for f in F.function(ref, layer)["fields"] if f["key"] == "hears")
        want = [owner_words.plain(h["handler"]) for h in S.hears(layer)]
        assert row["value"] == (want or None) and row["label"] == "Hears" and row["placeholder"] is (not want), layer
        assert not [t for t in want if BANNED.search(t)], layer
    assert next(f for f in F.function(ref, "audit")["fields"] if f["key"] == "hears")["value"] is None, "Audit hears nothing"
    assert "Take a no" in next(f for f in F.function(ref, "identity")["fields"] if f["key"] == "hears")["value"]


def test_c8_each_panes_checks_row_lists_the_interfaces_checks_in_plain_words(home):
    import functions_view as F
    import owner_words
    ref = born(home)
    for layer in S.FUNCTION_LAYERS:
        row = next(f for f in F.function(ref, layer)["fields"] if f["key"] == "checks")
        want = [owner_words.plain(says) for says in S.CHECKS[layer].values()]
        assert row["value"] == want and row["label"] == "Checks" and row["placeholder"] is False, layer
        assert not [t for t in row["value"] if BANNED.search(t)], (layer, "the screen never says refuse")
    ident = next(f for f in F.function(ref, "identity")["fields"] if f["key"] == "checks")["value"]
    assert "a gate's verdict is let through, wait or stop" in ident and "a verdict is go, ask or stop, and an ask or a no says why" in ident
    assert [f["key"] for f in F.function(ref, "audit")["fields"]] == ["goal", "done", "hears", "writes", "checks", "envelope", "settings"]


def test_c8_the_rows_follow_the_interface_when_a_handler_or_a_check_is_added(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    monkeypatch.setitem(S.HEARS, "audit", [dict(act="request", word="spot", via="board", payload="act.ask", handler="Drop in unannounced")])
    monkeypatch.setitem(S.CHECKS, "audit", dict(S.CHECKS["audit"], looked_twice="it looked at each page twice"))
    got = {f["key"]: f["value"] for f in F.function(ref, "audit")["fields"]}
    assert got["hears"] == ["Drop in unannounced"] and got["checks"][-1] == "it looked at each page twice"


def test_c8_a_settings_row_is_printed_in_the_owners_words_and_the_value_is_kept_as_it_is(home):
    """A typed value is on a function's Settings at rest (K2), so the row says it the way the screen word rules ask: Identity's
    verdict words and Adaptation's sent-back line (`shown`, `label`), while the field's `value`, which the owner changes, is
    left as the words the department reads."""
    import owner_words
    ref = born(home)
    _, R = modules()
    rows = {}
    for fn in ("identity", "adaptation", "priority"):
        for g in owner_words.steps({"instructions": R.instructions_view(ref, fn)})["instructions"]:
            for p in g["parts"]:
                rows[(fn, g["group"], p["part"])] = p
    guidance = rows[("identity", "take", "take")]["fields"][1]
    assert guidance["field"] == "guidance" and "refuse: it breaks a rule" in guidance["value"], "the value is the words the agent is sent"
    assert "stop: it breaks a rule" in guidance["shown"] and "refus" not in guidance["shown"].lower() and "\n" not in guidance["shown"]
    does = rows[("priority", "goal", "does")]["fields"][0]
    assert "gives each engine its limit" in does["shown"] and "grants each engine" in does["value"]
    skills = rows[("identity", "goal", "skills")]["fields"][0]
    assert skills["shown"] == "; ".join(skills["value"]), "a list reads as its items"
    sent_back = rows[("adaptation", "make", "refused")]
    assert (sent_back["part"], sent_back["label"]) == ("refused", "sent back"), "the part keeps its name; the row prints the label"
    assert "label" not in rows[("identity", "take", "take")]
    # a first-design file row, and a view with no rows, pass as they did
    assert owner_words.steps({"instructions": [{"file": "take", "lead": "How to judge a request: go, ask or refuse."}]})["instructions"] == \
        [{"file": "take", "lead": "How to judge a request: go, ask or stop."}]


def test_c8_no_settings_row_of_any_function_prints_a_banned_word(api, home):
    """Every word a Settings row prints at rest (`shown`, a group's `lead`, a part's `label`, the `inputs` and `answers` it names)
    on every function's steps read, which is what the screen draws, in the owner's words: never grant, counter, refuse, orders,
    charter or internal system (found by a verifier, 2026-10-26: Identity's completeness row said 'every rule is tagged go,
    ask, refuse or always'). The raw `value` the owner edits stays the words the agent is sent, and a part's id is a name."""
    ref = born(home)
    _, R = modules()

    def printed(x):
        if isinstance(x, str):
            yield x
        elif isinstance(x, list):
            for y in x:
                yield from printed(y)

    rows = 0
    for layer in S.FUNCTION_LAYERS:
        got = api.get("/api/native/%s/steps/%s" % (ref, S.TITLE[layer]))
        assert got.status_code == 200, layer
        for g in got.json()["instructions"]:
            assert not BANNED.search(g["lead"]), (layer, g["group"], g["lead"])
            for p in g["parts"]:
                for k in ("label", "inputs", "answers"):
                    assert not [t for t in printed(p.get(k)) if BANNED.search(t)], (layer, g["group"], p["part"], k)
                for f in p["fields"]:
                    rows += 1
                    assert isinstance(f["shown"], str) and not BANNED.search(f["shown"]), (layer, g["group"], p["part"], f["field"], f["shown"])
    assert rows >= 20, "the scan reached the fields of all five functions"
    # the sentence that lists the rule tags says the tag the badge says; the raw value is the words the agent reads
    enough = next(f for g in R.instructions_view(ref, "identity") if g["group"] == "completeness"
                  for p in g["parts"] if p["part"] == "enough" for f in p["fields"] if f["field"] == "task")
    assert "tagged go, ask, refuse or always" in enough["value"]
    import owner_words
    shown = owner_words.steps({"instructions": R.instructions_view(ref, "identity")})["instructions"]
    said = next(f for g in shown if g["group"] == "completeness" for p in g["parts"] if p["part"] == "enough" for f in p["fields"])["shown"]
    assert "tagged go, ask, never or always" in said and "refus" not in said.lower()


# ---- C9 · views through the layers ------------------------------------------------------------------------------------
AUDIT_VIEW = {"readings": [{"summary": "Audit read Live site v1.", "at": None}], "findings": [], "spot_checks": []}


def with_view(monkeypatch, layer, fn):
    """The layer's implementation, made to hold a view() for the duration of the test."""
    module = layers.load(S.DEFAULT_PINS[layer])
    monkeypatch.setattr(module, "view", fn, raising=False)
    return module


def without_view(monkeypatch, layer):
    monkeypatch.delattr(layers.load(S.DEFAULT_PINS[layer]), "view", raising=False)


def test_c9_with_no_view_the_part_is_todays_body(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    d = modules()[0].dept(ref)
    for layer in S.FUNCTION_LAYERS:
        title = S.TITLE[layer]
        today = F._j2_body(ref, d, title, [], [])
        without_view(monkeypatch, layer)
        assert not hasattr(layers.load(S.DEFAULT_PINS[layer]), "view")
        assert F._j2_part(ref, d, title, [], []) == today and "j2_faults" not in today and S.validate_view(layer, today) == [], layer
    assert set(F.function(ref, "audit")["j2"]) == {"readings", "findings", "spot_checks"}
    assert set(F.function(ref, "coordination")["j2"]) == set(S.COORDINATION_FIELDS)


def test_c9_the_stub_views_of_wave_0_read_todays_body_by_reference_and_the_dispatch_does_not_loop(home):
    """A layer's view is what the pane returns. Wave 0's stub is today's body by reference; the view a layer's package writes
    holds every field of today's body as it was and may add its own (Adaptation's coverage, Priority's prices, Audit's latest)."""
    import functions_view as F
    ref = born(home)
    d = modules()[0].dept(ref)
    for layer in S.FUNCTION_LAYERS:
        title = S.TITLE[layer]
        stub = layers.load(S.DEFAULT_PINS[layer]).view
        view, today = stub(ref, d, [], []), F._j2_body(ref, d, title, [], [])
        assert view == F._j2_part(ref, d, title, [], []), layer
        assert {k: view.get(k, "<missing>") for k in today} == today, layer
        j2 = F.function(ref, layer)["j2"]
        assert "j2_faults" not in j2 and S.validate_view(layer, j2) == [], layer


def test_c9_a_stub_view_is_what_the_pane_returns_and_it_is_handed_the_record(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    seen = []
    with_view(monkeypatch, "audit", lambda ref_, d, events, asks: seen.append((ref_, d, events, asks)) or AUDIT_VIEW)
    got = F.function(ref, "audit")
    assert got["j2"] == AUDIT_VIEW
    assert len(seen) == 1 and seen[0][0] == ref and seen[0][1]["ref"] == ref and isinstance(seen[0][2], list) and isinstance(seen[0][3], list)
    assert F.function(ref, "priority")["j2"] != AUDIT_VIEW, "another layer's pane is its own"


def test_c9_every_layers_own_view_can_be_todays_body_and_it_validates(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    d = modules()[0].dept(ref)
    for layer in S.FUNCTION_LAYERS:
        title = S.TITLE[layer]
        today = F._j2_body(ref, d, title, [], [])
        with_view(monkeypatch, layer, lambda ref_, d_, events, asks, title=title: F._j2_body(ref_, d_, title, events, asks))
        assert F._j2_part(ref, d, title, [], []) == today and S.validate_view(layer, today) == [], layer
        without_view(monkeypatch, layer)


def test_c9_an_invalid_view_is_todays_part_with_the_first_three_faults(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    d = modules()[0].dept(ref)
    today = F._j2_body(ref, d, "Audit", [], [])
    with_view(monkeypatch, "audit", lambda *a: {"readings": "none"})
    got = F.function(ref, "audit")["j2"]
    want = S.validate_view("audit", {"readings": "none"})
    assert want == ["$.findings: is missing", "$.spot_checks: is missing", "$.readings: is not a list"] or len(want) == 3
    assert got == dict(today, j2_faults=want[:3]), "today's part, and why the view was not used"
    without_view(monkeypatch, "audit")
    with_view(monkeypatch, "coordination", lambda *a: {"a": 1, "b": 2, "c": 3, "d": 4})
    got = F.function(ref, "coordination")["j2"]
    assert len(got["j2_faults"]) == 3 and set(got) - {"j2_faults"} == set(S.COORDINATION_FIELDS), "today's part, and three faults at most"
    without_view(monkeypatch, "coordination")
    for bad in ([], "a view", 7):
        with_view(monkeypatch, "priority", lambda *a, bad=bad: bad)
        got = F.function(ref, "priority")["j2"]
        assert got["j2_faults"] and set(got) - {"j2_faults"} == {"bargains", "envelopes"}, bad
        without_view(monkeypatch, "priority")


def test_c9_a_view_that_raises_is_todays_part_and_the_read_never_raises(home, monkeypatch):
    import functions_view as F
    ref = born(home)

    def boom(*a):
        raise RuntimeError("the view broke")
    with_view(monkeypatch, "audit", boom)
    got = F.function(ref, "audit")
    assert got["j2"]["j2_faults"] == ["the view could not be read: the view broke"]
    assert set(got["j2"]) == {"readings", "findings", "spot_checks", "j2_faults"} and got["name"] == "Audit"
    assert F.functions(ref)["functions"], "the other reads go on"


def test_c9_a_fault_is_kept_to_the_part_and_is_a_few_plain_lines(home, monkeypatch):
    import functions_view as F
    ref = born(home)
    with_view(monkeypatch, "audit", lambda *a: {"readings": 3})
    f = F.function(ref, "audit")
    assert "j2_faults" in f["j2"] and not [k for k in f if "fault" in k], "only the part carries it"
    assert 1 <= len(f["j2"]["j2_faults"]) <= 3 and all(isinstance(x, str) and "Traceback" not in x for x in f["j2"]["j2_faults"])
    assert not F.PATHLIKE.search(json.dumps(f["j2"]["j2_faults"])), "names, never paths"


# ---- C10 · typed options and the line request -------------------------------------------------------------------------
def blocked_card(ref):
    """The card a blocked plan puts to the owner (M3.5), made by the runtime on a department with three done-when items."""
    W, R = modules()
    d = dict(W.dept(ref), done_items=[{"id": "D%d" % i, "text": "item %d" % i, "how": "code", "level": "outcome"} for i in (1, 2, 3)])
    return R._blocked(ref, d, {"src": "Root"}, "The plan could not be approved.", "The plan could not be approved.",
                      "Root, at its review", "D3 reaches outside without a rule")


def test_c10_an_option_has_its_kind_from_its_id_and_its_params_pass_untouched(home):
    W, _ = modules()
    assert W.option("words", "Change it", "Adaptation shapes it afresh") == {
        "id": "words", "label": "Change it", "cost": "Adaptation shapes it afresh", "kind": "words"}
    assert W.option("leave:D2", "Leave D2 out", "dropped")["kind"] == "leave"
    assert W.option("stop", "Stop", "stops")["kind"] == "stop"
    params = {"what": "envelope", "engine": "Design", "calls": 4, "usd": 0.5}
    got = W.option("raise", "Add room", "up to twice", params)
    assert got["kind"] == "raise" and got["params"] == params and got["params"] is params, "params pass through untouched"
    assert "params" not in W.option("stop", "Stop", "stops"), "no params, none stored"
    for o in (W.option("words", "w", "c"), W.option("leave:D2", "l", "c"), got, W.option("root_setup", "r", "c", {"words": "again"})):
        assert S.validate("option", o) == [], o


def test_c10_options_ask_is_otherwise_unchanged_and_keeps_kind_and_params(home):
    W, _ = modules()
    params = {"what": "ceiling", "engine": "Design", "calls": 2, "usd": 0.1}
    opts = [W.option("words", "A", "costs a"), W.option("raise", "B", "costs b", params), W.option("stop", "C", "c"), W.option("leave:D1", "D", "d")]
    a = W.options_ask("blocked", "Stuck", opts, why="because")
    assert [o["id"] for o in a["options"]] == ["words", "raise", "stop"], "at most three"
    assert [o["kind"] for o in a["options"]] == ["words", "raise", "stop"] and a["options"][1]["params"] == params
    assert "params" not in a["options"][0]
    assert (a["kind"], a["engine"], a["status"], a["chosen"], a["why"]) == ("blocked", "Identity", "pending", None, "because")
    # an option made by hand, as a caller of this ask may pass it, takes the same road
    again = W.options_ask("blocked", "Stuck", [{"id": "stop", "label": "S", "cost": "c"}])
    assert again["options"] == [W.option("stop", "S", "c")]


def test_c10_the_ask_rows_pass_the_sink_and_a_way_out_the_interface_lacks_does_not(home):
    ref = born(home)
    W, _ = modules()
    a = W.options_ask("blocked", "Stuck", [W.option("words", "A", "a"), W.option("leave:D1", "B", "b"), W.option("stop", "C", "c")], who="Root")
    with S.expect_refused() as met:
        W._put_ask(ref, a)                                 # the sink checks the row: identity.ask, options and all
    assert list(met) == [], "a row of typed options meets no fault"
    got = next(x for x in W.asks(ref) if x["id"] == a["id"])
    assert S.validate("identity.ask", got) == [] and [x["kind"] for x in got["options"]] == ["words", "leave", "stop"]
    odd = W.options_ask("blocked", "Stuck", [W.option("sideways:1", "A", "a")])
    assert any("kind" in f for f in S.validate("identity.ask", odd)), "a kind that is not a way out of the interface is a fault"
    with S.expect_refused() as met:
        with pytest.raises(S.SchemaFault):
            W._put_ask(ref, odd)
    assert any("kind" in str(r) for r in met.rows), "the sink met it"


def test_c10_every_blocked_ask_carries_the_kinds_words_leave_and_stop_and_validates(home):
    ref = born(home)
    W, _ = modules()
    card = blocked_card(ref)
    assert [o["id"] for o in card["options"]] == ["words", "leave:D3", "stop"]
    assert [o["kind"] for o in card["options"]] == ["words", "leave", "stop"]
    assert all(o["kind"] in S.OPTION_KINDS for o in card["options"]) and S.validate("identity.ask", card) == []
    stored_card = next(x for x in W.asks(ref) if x["id"] == card["id"])
    assert stored_card["options"] == card["options"], "what the sink wrote is what the card offers"


def test_c10_choose_option_behaves_as_built_and_an_unknown_option_is_409_with_its_code(api, home):
    ref = born(home)
    W, _ = modules()
    card = blocked_card(ref)
    bad = api.post("/api/native/%s/asks/%s" % (ref, card["id"]), json={"option": "sideways"})
    assert bad.status_code == 409 and bad.json()["detail"] == {"code": "UNKNOWN_OPTION"}
    empty = api.post("/api/native/%s/asks/%s" % (ref, card["id"]), json={"option": "words", "text": "  "})
    assert empty.status_code == 400 and empty.json()["detail"] == {"code": "EMPTY_ANSWER"}
    with pytest.raises(W.AskError) as exc:
        W.choose_option(ref, card["id"], "kind")
    assert exc.value.code == "UNKNOWN_OPTION", "the kind of an option is not an option's id"


def test_c10_the_line_request_is_an_act_line_request_and_post_checks_it(home):
    ref = born(home)
    W, R = modules()
    d = W.dept(ref)
    R._line_request(ref, d, "A phone-first site for a bakery", thread=None)
    R._line_request(ref, d, "A phone-first site for a bakery", thread="t-1", faults=["the line reaches outside without a rule"])
    R._line_request(ref, d, "A site", faults=["x" * 900, "second"])
    rows = [p for p in R.board(ref) if p["src"] == "Identity" and p["msg_type"] == "request" and p["payload"].get("word") == "line"]
    assert len(rows) == 3
    for p in rows:
        assert S.validate("act.line_request", p["payload"]) == [], p["payload"]
        assert S.validate_act("Identity", p["dst"], "request", p["payload"]) == [], "the act as the interface sends it"
    assert rows[0]["payload"]["faults"] == [] and rows[1]["payload"]["faults"] == ["the line reaches outside without a rule"]
    assert rows[2]["payload"]["faults"] == ["x" * 600, "second"], "a fault is a line, kept to the interface's length"
    assert rows[1]["payload"]["for"] == "t-1" and rows[1]["payload"]["objective"] == "propose the workflows the goal needs"


def test_c10_a_line_request_that_does_not_fit_is_a_fault_of_the_interface(home):
    ref = born(home)
    _, R = modules()
    with S.expect_refused():
        with pytest.raises(S.SchemaFault):
            R.post(ref, "Identity", "Adaptation", "request", {"word": "line", "words": 7, "objective": "x", "faults": "none"})


# ---- C11 · K2 end to end ----------------------------------------------------------------------------------------------
def test_c11_a_department_made_and_run_the_way_a_person_makes_one_reads_as_the_interface_types_it(home, monkeypatch):
    """Root and the department it made, run to idle offline (test_j2's way): every pane of each reads as VIEWS[layer], with
    no fault kept to show, every work engine's card as VIEWS['engine_card'], and every ask on the record passes the
    interface, its options typed (C10). The instructions of every function read through the same record (C6, C7)."""
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as F
    for module in (E, W, org2_apply, founding, R, J, F):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    root = founding.found_structure("Sutra Org", owner="Sankalp")["root"]
    W.owner_ask(root, "A phone-first website for Bakery Co, a bakery in Pune, where customers see every cake")
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    assert len(R.board(ref)) > 4, "the department ran, and left its record"
    for r in (root, ref):
        for layer in S.FUNCTION_LAYERS:
            j2 = F.function(r, layer)["j2"]
            assert "j2_faults" not in j2 and S.validate_view(layer, j2) == [], (r, layer)
            assert set(F.function(r, layer)) >= {"vsm", "line", "holds", "hands_to", "keeps", "fields"}, "the page fields (C8)"
    work = [n for n, e in R.defs()["engines"].items() if e.get("kind") == "work"]
    assert work and all(S.validate_view("engine_card", F.engine_card(ref, n)) == [] for n in work)
    for a in W.asks(ref):
        assert S.validate("identity.ask", a) == [] and all(o.get("kind") in S.OPTION_KINDS for o in a.get("options") or []), a["id"]
    for layer in S.FUNCTION_LAYERS:
        view = R.instructions_view(ref, layer)
        assert [g["group"] for g in view] == list(S.PROMPTS[layer]), layer
        assert any(f["value"] for g in view for p in g["parts"] for f in p["fields"]), "a field the owner may change reads its words"
