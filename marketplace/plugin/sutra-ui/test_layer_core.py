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
                      ({"value": "Judge {{words}}"}, "task cannot hold '{{' or '}}'"),
                      ({"value": "Judge it. Return ONLY yes"}, "task cannot hold 'Return ONLY'"),
                      ({"value": "x" * 1201}, "task is longer than 1200 characters"), ({"value": 5}, "task has to be words"),
                      ({"value": "   "}, "task is empty"), ({"value": P.defaults(ref, *TAKE)["task"]}, "these are the words Identity's take task holds now")):
        r = post_field(api, ref, **body)
        assert r.status_code == 400 and why in r.json()["detail"], (body, r.text)
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
    assert got["schema_version"] == S.SCHEMA_VERSION == 1
    assert got["pins"] == S.DEFAULT_PINS and got["available"] == layers.available()
    assert got["standards"] == [{"id": i, "says": s} for i, s, _, _ in S.WORKFLOW_STANDARDS]
    assert [x["id"] for x in got["standards"]][0] == "names_an_engine" and all(set(x) == {"id", "says"} for x in got["standards"])
    assert got["describe"] == S.describe() and got["describe"]["layers"]["identity"]["v1"] == S.LAYERS["identity"]["v1"]
    assert got["describe"]["default_pins"] == S.DEFAULT_PINS and got["describe"]["workflow_standards"][0]["id"] == "names_an_engine"


def test_c7_get_layers_names_a_pin_it_cannot_honour_once(api, home):
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
    import functions_view as F
    ref = born(home)
    d = modules()[0].dept(ref)
    for layer in S.FUNCTION_LAYERS:
        title = S.TITLE[layer]
        stub = layers.load(S.DEFAULT_PINS[layer]).view
        assert stub(ref, d, [], []) == F._j2_body(ref, d, title, [], []) == F._j2_part(ref, d, title, [], []), layer
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
