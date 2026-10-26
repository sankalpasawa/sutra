"""The journey machinery (PRD amendment A3.6): the loader and the hash, the state of a row, the site reader, the twelve
cases, the walk, the status runner and the data-only API.

A journey is a JSON file under journeys/ that conforms to the interface's DEFS['journey']. The machinery here ships no
journey data (the content packages do), so every test works on the fixture journey of test_fixtures/journeys/ and on
temp folders it points journeys.FOLDER at. A test that meets a fault of the interface on purpose does so inside
S.expect_refused(); any other fault fails the test through the conftest fixture.
"""
import copy
import json
from pathlib import Path

import pytest

import journeys
import layer_schema as S
from journeys import status as ST

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "test_fixtures" / "journeys"
#: a test of the suite that really exists, for a row of the fixture journey to list
REAL_TEST = "test_j1.py::test_j1_4_no_fitting_template_uses_explicit_organic_route"


# ---- the fixture journey, and a folder to put journeys in -----------------------------------------------------------
def good(name="good", **change):
    """The fixture journey (two steps, one edge), a fresh copy, with the top-level fields in `change` set. An id other than
    J9 renames the edge too, so the copy is still a journey a loader takes."""
    doc = json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))
    new = change.get("id")
    if new and new != doc["id"]:
        for e in doc["edges"]:
            e["id"] = e["id"].replace(doc["id"], new, 1)
        doc["site_ids"] = [i.replace(doc["id"], new, 1) for i in doc["site_ids"]]
    doc.update(change)
    return doc


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """An empty journeys folder, which journeys.FOLDER now names."""
    d = tmp_path / "journeys"
    (d / "functions").mkdir(parents=True)
    monkeypatch.setattr(journeys, "FOLDER", d)
    return d


def put(folder, name, doc):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return path


def a_status(j, **change):
    """A status document of the journey that fits journey.status, stamped with the hash of the journey as it is."""
    keys = ["%s:%s" % (k, r) for k, r, _ in journeys.rows(j)]
    doc = {"schema_version": 1, "id": j["id"], "definitions_sha": journeys.sha_of(j), "state": "proven",
           "counts": {"proven": len(keys)}, "tests": {}, "rows": {k: {"state": "proven"} for k in keys}}
    doc.update(change)
    assert S.validate("journey.status", doc) == []
    return doc


# ---- Q1: the loader, the hash and the read model --------------------------------------------------------------------
def test_load_reads_files_and_functions_files(folder):
    assert journeys.load() == {}, "a folder with no journeys is no journeys"
    one = good()
    put(folder, "J9.json", one)
    two, three = good(id="FI1", kind="function", bound_to="identity"), good(id="FI2", kind="function", bound_to="identity")
    put(folder, "functions/identity.json", {"journeys": [two, three]})
    put(folder, "status/J9.json", a_status(one))          # a status document is not a journey and is not read as one
    got = journeys.load()
    assert sorted(got) == ["FI1", "FI2", "J9"]
    assert got["J9"] == one and got["FI1"] == two
    assert [r[:2] for r in journeys.rows(one)] == [("step", "1"), ("step", "2"), ("edge", "J9.1")], "the steps, then the edges"
    assert journeys.row_key("J1", "step", "3") == "J1:step:3" and journeys.row_key("J1", "edge", "J1.5") == "J1:edge:J1.5"
    was = good("good-with-was")
    assert [r[1] for r in journeys.rows(was)] == [s["n"] for s in was["steps"]] + [e["id"] for e in was["edges"]], \
        "the rows of `was` are history, not rows"


def test_a_bad_file_refuses_the_load_and_names_it(folder):
    put(folder, "J9.json", good())
    (folder / "J8.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match=r"the journey file J8\.json is refused: it is not JSON"):
        journeys.load()
    (folder / "J8.json").unlink()
    put(folder, "J8.json", dict(good(id="J8"), colour="red"))
    with pytest.raises(ValueError, match=r"the journey file J8\.json is refused: \$\.colour: is not a field here"):
        journeys.load()
    put(folder, "J8.json", dict(good(id="J8"), steps=[dict(good()["steps"][0], lane=None)]))
    with pytest.raises(ValueError, match=r"the journey file J8\.json is refused: .*lane"):
        journeys.load()
    put(folder, "J8.json", good(id="J9"))
    with pytest.raises(ValueError, match=r"the journey file J9\.json is refused: J9 is already a journey \(in J8\.json\)"):
        journeys.load()
    (folder / "J8.json").unlink()
    put(folder, "functions/identity.json", {"journeys": [dict(good(id="FI1"), colour="red")]})
    with pytest.raises(ValueError, match=r"the journey file functions/identity\.json is refused: .*journeys\[0\]\.colour"):
        journeys.load()
    put(folder, "functions/identity.json", ["not", "a", "journey"])
    with pytest.raises(ValueError, match=r"the journey file functions/identity\.json is refused: it holds one journey"):
        journeys.load()


def test_definitions_sha_changes_with_any_row_of_that_journey_only(folder):
    a, b = good(), good(id="J8")
    put(folder, "J9.json", a)
    put(folder, "J8.json", b)
    sha_a, sha_b, sha_all = journeys.definitions_sha("J9"), journeys.definitions_sha("J8"), journeys.definitions_sha()
    assert len({sha_a, sha_b, sha_all}) == 3 and all(len(s) == 64 for s in (sha_a, sha_b, sha_all))
    assert journeys.definitions_sha("J9") == sha_a, "the same file, the same hash"
    # the hash is of the canonical JSON: the order of the keys in the file does not matter, the words do
    put(folder, "J9.json", dict(reversed(list(a.items()))))
    assert journeys.definitions_sha("J9") == sha_a
    for change in (lambda j: j["steps"][1].update(short="Identity says it back"),
                   lambda j: j["edges"][0].update(trigger="The rule is on the record already."),
                   lambda j: j["edges"][0]["tests"].append(REAL_TEST),
                   lambda j: j["steps"][0]["binds"][0].update(word="front")):
        changed = copy.deepcopy(a)
        change(changed)
        put(folder, "J9.json", changed)
        assert journeys.definitions_sha("J9") != sha_a, change
        assert journeys.definitions_sha("J8") == sha_b, "another journey's hash does not move"
        assert journeys.definitions_sha() != sha_all
    with pytest.raises(journeys.UnknownJourney):
        journeys.definitions_sha("J7")


def test_view_marks_a_journey_stale_when_its_hash_differs_or_its_file_is_missing(folder):
    j = good()
    put(folder, "J9.json", j)
    # no status file: stale, and every row that lists tests reads unknown; a row that lists none reads its definition
    listed = journeys.view()
    assert listed["schema_version"] == 1 and [x["id"] for x in listed["journeys"]] == ["J9"]
    row = listed["journeys"][0]
    assert (row["stale"], row["declared"], row["kind"], row["inside"], row["bound_to"]) == (True, False, "system", None, None)
    one = journeys.view("J9")
    assert one["status"]["stale"] is True
    assert {k: r["state"] for k, r in one["status"]["rows"].items()} == {"step:1": "unknown", "step:2": "unknown", "edge:J9.1": "unproven"}, \
        "rows that list tests are unknown until a run is recorded; a row with code and no tests is unproven whatever ran"
    assert one["status"]["state"] == "fault" and row["state"] == "fault", "an unproven row is a fault, and the definition says so"
    # a status file with the journey's hash: fresh, and the file's states are the states
    put(folder, "status/J9.json", a_status(j, state="proven", rows={"step:1": {"state": "proven", "proven_by": [REAL_TEST]},
                                                                    "step:2": {"state": "partly"}, "edge:J9.1": {"state": "proven"}}))
    fresh = journeys.view("J9")["status"]
    assert fresh["stale"] is False and fresh["state"] == "proven"
    assert {k: r["state"] for k, r in fresh["rows"].items()} == {"step:1": "proven", "step:2": "partly", "edge:J9.1": "proven"}
    assert fresh["rows"]["step:1"]["proven_by"] == ["test_j1_4_no_fitting_template_uses_explicit_organic_route"], "the test by name, never by file"
    assert journeys.view()["journeys"][0]["stale"] is False
    # the journey's file changes by one word: the hash is no longer the file's, and the same status is stale
    changed = copy.deepcopy(j)
    changed["steps"][0]["short"] = "You say it"
    put(folder, "J9.json", changed)
    assert journeys.view("J9")["status"]["stale"] is True
    assert journeys.view("J9")["status"]["rows"]["step:1"]["state"] == "unknown"
    # a status file that is not whole is no status file
    (folder / "status" / "J9.json").write_text("{", encoding="utf-8")
    assert journeys.view()["journeys"][0]["stale"] is True
    put(folder, "status/J9.json", dict(a_status(changed), id="J8"))
    assert journeys.view()["journeys"][0]["stale"] is True, "a document for another journey is not this journey's"
    # a declared journey has no state to compute and is never stale
    put(folder, "functions/identity.json", {"journeys": [good(id="FI1", kind="function", bound_to="identity", declared=True)]})
    declared = {x["id"]: x for x in journeys.view()["journeys"]}["FI1"]
    assert (declared["state"], declared["stale"], declared["declared"]) == ("declared", False, True)
    assert {r["state"] for r in journeys.view("FI1")["status"]["rows"].values()} == {"declared"}
    # a read writes nothing
    before = sorted(p.name for p in folder.rglob("*"))
    journeys.view()
    journeys.view("J9")
    assert sorted(p.name for p in folder.rglob("*")) == before
    with pytest.raises(journeys.UnknownJourney):
        journeys.view("J7")


def test_view_replaces_the_helper_token(folder):
    j = good(title="Found the organisation; {helper} asks first")
    j["steps"][0]["text"] = "{helper} appears in the chat, and {helper} says hello."
    j["steps"][1]["short"] = "{helper} restates it"
    j["edges"][0]["site"]["text"] = "Said back by {helper}."
    put(folder, "J9.json", j)
    one = journeys.view("J9")
    text = json.dumps([journeys.view(), one])
    assert "{helper}" not in text and "Root appears in the chat, and Root says hello." in text
    assert journeys.view()["journeys"][0]["title"] == "Found the organisation; Root asks first"
    assert one["steps"][1]["short"] == "Root restates it" and one["edges"][0]["site"]["text"] == "Said back by Root."
    assert j["steps"][0]["text"].startswith("{helper}"), "the file is the author's; the read model is a copy"
    # the journey names the word its screen says
    put(folder, "J9.json", dict(j, helper={"site": "Sutra", "screen": "Sutra", "code": "Root"}))
    assert "Sutra appears in the chat" in json.dumps(journeys.view("J9"))


# ---- Q2: the names a row lists, the state of a row, and the site reader ----------------------------------------------
def test_resolve_code_finds_python_and_js_names_and_refuses_a_missing_one():
    for name in ("setup_say", "wbFoundGo", "website_dept.create", "engine_runtime.setup_say", "SECOND", "fixture_department"):
        assert ST.resolve_code(name) is True, name
    # a name that is not there, a module that does not define it, a test file's name, a name of the wrong language
    for name in ("setup_sayy", "website_dept.setup_say", "no_such_module.create", "engine_runtime.wbFoundGo",
                 "_born", "test_j1_4_no_fitting_template_uses_explicit_organic_route", "wbFoundGoo"):
        assert ST.resolve_code(name) is False, name


def test_the_code_roots_are_the_plugin_python_without_tests_layers_and_the_scripts(tmp_path, monkeypatch):
    root = tmp_path / "plugin"
    for name, text in {"alpha.py": "X = 1\nA, B = 1, 2\ndef f():\n    inner = 1\n\nclass C:\n    LATER = 1\n    def m(self):\n        pass\n",
                       "test_alpha.py": "def only_in_a_test():\n    pass\n",
                       "layers/sub/beta.py": "def g():\n    pass\n",
                       "static/js/10-x.js": "function jsf(){}\nconst jsc = 1;\nlet jsl;\nvar jsv;\nasync function jsa(){}\n",
                       "static/js/not.txt": "function nope(){}\n", "notes/gamma.py": "def elsewhere():\n    pass\n",
                       "broken.py": "def (:\n"}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(ST, "ROOT", root)
    found = {n for n in ("f", "C", "m", "X", "A", "B", "g", "jsf", "jsc", "jsl", "jsv", "jsa") if ST.resolve_code(n)}
    assert found == {"f", "C", "m", "X", "A", "B", "g", "jsf", "jsc", "jsl", "jsv", "jsa"}, found
    assert not any(ST.resolve_code(n) for n in ("inner", "LATER", "only_in_a_test", "nope", "elsewhere")), \
        "a local of a function, a class attribute, a test, a file that is no script, a folder that is no root"
    assert ST.resolve_code("alpha.f") and ST.resolve_code("beta.g") and not ST.resolve_code("alpha.g") and not ST.resolve_code("beta.f")
    assert not ST.resolve_code("10-x.jsf") and not ST.resolve_code("x.jsf"), "module.name is for the Python files"
    # a file that changes is read again
    (root / "alpha.py").write_text("def fresh():\n    pass\n", encoding="utf-8")
    import os
    os.utime(root / "alpha.py", ns=(1, (root / "alpha.py").stat().st_mtime_ns + 5_000_000))
    assert ST.resolve_code("fresh") and not ST.resolve_code("f")


def test_resolve_test_for_pytest_classes_functions_and_js():
    for ref in ("test_engine_runtime.py::TestTheFiveJourneys::test_37_a_directive_is_restated_put_back_and_kept_only_on_a_stamp",
                REAL_TEST, "js:test_website.js#W45", "js:test_website.js#W10b", "test_layer_journeys.py::test_row_state_table"):
        assert ST.resolve_test(ref) is True, ref
    for ref in ("test_engine_runtime.py::TestTheFiveJourneys::test_no_such_test",          # the name is wrong
                "test_engine_runtime.py::TestNoSuchClass::test_37_a_directive_is_restated_put_back_and_kept_only_on_a_stamp",
                "test_engine_runtime.py::test_37_a_directive_is_restated_put_back_and_kept_only_on_a_stamp",   # it is a method, not a function
                "test_j1.py::TestTheFiveJourneys::" + REAL_TEST.split("::")[1],                  # a function, not a method
                "test_j1.py::test_j1_no_such_test", "test_no_such_file.py::test_x",
                "js:test_website.js#W999", "js:test_website.js#W4x", "js:test_no_such_file.js#W45",
                "js:test_website.js#", "test_j1.py", "test_j1.py::a::b::c", "nothing"):
        assert ST.resolve_test(ref) is False, ref
    # `W4` is a test of its own: it does not answer for W45, and W45 does not answer for W4
    assert ST.resolve_test("js:test_website.js#W4") is True and ST.resolve_test("js:test_website.js#W5") is True


def _row(**change):
    """A row of a journey that has code, one test and nothing else: the shape of a proven one."""
    row = {"code": ["identity_file"], "tests": ["t.py::a"]}
    row.update(change)
    return row


def test_row_state_table():
    ok, bad = {"t.py::a": "passed"}, {"t.py::a": "failed"}
    two = {"tests": ["t.py::a", "t.py::b"]}
    cases = [
        # (row, results, expected state)
        (_row(), ok, "proven"),
        (_row(backlog="BL-1"), ok, "partly"),                                    # built, with a part named as not built
        (_row(**two), {"t.py::a": "passed", "t.py::b": "passed"}, "proven"),
        (_row(**two), {"t.py::a": "passed", "t.py::b": "failed"}, "failing"),   # one of them is enough
        (_row(), bad, "failing"),
        (_row(), {"t.py::a": "missing"}, "failing"),                             # the run asked for it and did not find it
        (_row(backlog="BL-1"), bad, "failing"),
        (_row(**two), {"t.py::a": "passed"}, "unknown"),                         # no result for one: the read model's word
        (_row(), {}, "unknown"),
        (_row(tests=[]), ok, "unproven"),                                        # code and no tests
        (_row(tests=[], backlog="BL-1"), ok, "unproven"),
        ({"backlog": "BL-1"}, ok, "wanted"),                                     # no code, a backlog entry, no tests
        ({"backlog": "BL-1", "binds": [{"kind": "person"}]}, ok, "wanted"),      # the owner's own act is no code
        ({}, ok, "fault"),                                                       # no code and no backlog entry
        ({"tests": ["t.py::a"], "backlog": "BL-1"}, ok, "fault"),                # a wanted row that lists a test
        ({"tests": ["t.py::a"]}, ok, "fault"),
        ({"binds": [{"kind": "act", "src": "Owner", "act": "request", "word": "front", "dst": "Identity"}], "tests": ["t.py::a"]},
         ok, "proven"),                                                          # a bind that can be traced is code enough
        ({"binds": [{"kind": "ui", "symbol": "wbFoundGo"}], "tests": ["t.py::a"]}, ok, "proven"),
        (_row(disposition="drop"), bad, "dropped"),                              # the owner's mark: it counts for nothing, whatever ran
        ({"disposition": "drop"}, {}, "dropped"),
        (_row(disposition="keep"), ok, "proven"), (_row(disposition="change"), ok, "proven"), (_row(disposition=None), ok, "proven"),
    ]
    for row, results, want in cases:
        assert ST.row_state(row, results) == want, (row, results, want)
    assert ST.row_state(_row(), None) == "unknown", "no results at all"
    # same_as takes the state of the row it names, and the drop of the row itself wins
    states = {"J1:step:3": "proven", "J1:edge:J1.5": "failing", "J2:step:1": "wanted"}
    assert ST.row_state({"same_as": "J1/step/3"}, {}, states) == "proven"
    assert ST.row_state({"same_as": "J1/edge/J1.5"}, {}, states) == "failing"
    assert ST.row_state({"same_as": "J2/step/1", "tests": ["t.py::a"]}, {"t.py::a": "failed"}, states) == "wanted", "its own tests are not asked"
    assert ST.row_state({"same_as": "J1/step/9"}, {}, states) == "fault", "a row that points at nothing is a fault"
    assert ST.row_state({"same_as": "J1/step/3", "disposition": "drop"}, {}, states) == "dropped"
    assert ST.row_state({"same_as": "J1/step/3"}, {}) == "fault"


def test_journey_state_rules():
    j, declared = {"id": "J9"}, {"id": "FI1", "declared": True}
    one = lambda *states: ST.journey_state(j, list(states))        # noqa: E731
    assert ST.journey_state(declared, ["failing", "fault"]) == "declared", "a declared journey has no state to compute"
    assert one("proven", "proven") == "proven"
    assert one("proven", "partly") == "partly" and one("proven", "wanted") == "partly" and one("wanted", "partly") == "partly"
    assert one("proven", "unproven") == "fault" and one("proven", "fault") == "fault" and one("partly", "fault") == "fault"
    assert one("proven", "failing") == "failing" and one("fault", "unproven", "failing", "partly") == "failing", "failing outranks the rest"
    assert one("proven", "unknown") == "unknown" and one("partly", "unknown") == "unknown"
    assert one("unknown", "fault") == "fault", "what the definition says is true whatever ran"
    assert one("proven", "dropped") == "proven" and one("dropped", "dropped") == "proven", "a dropped row counts for nothing"
    assert one("dropped", "wanted") == "partly"
    assert ST.journey_state(j, {"step:1": "proven", "edge:J9.1": "fault"}) == "fault", "a dict of row states is read by its values"


def test_row_states_read_a_same_as_row_after_the_others():
    j = good()
    j["steps"][1]["same_as"] = "J9/step/1"
    j["steps"][1]["tests"] = []
    j["edges"][0]["same_as"] = "J1/edge/J1.5"
    results = {t: "passed" for t in ST.tests_listed(j)}
    got = ST.row_states(j, results, {"J1:edge:J1.5": "partly"})
    assert got == {"step:1": "proven", "step:2": "proven", "edge:J9.1": "partly"}, "a row of this journey, and a row of another"
    assert list(got) == ["step:1", "step:2", "edge:J9.1"], "in the journey's order"
    assert ST.row_states(j, {t: "failed" for t in results}, {"J1:edge:J1.5": "partly"}) == \
        {"step:1": "failing", "step:2": "failing", "edge:J9.1": "partly"}


def test_drift_lists_the_rows_where_the_site_and_the_state_differ():
    # the site's word, the state: built but wanted, built but not proven, wanted but proven or partly
    assert ST.drifts("built", "wanted") and ST.drifts("built", "partly") and ST.drifts("built", "failing") and ST.drifts("built", "fault")
    assert ST.drifts("wanted", "proven") and ST.drifts("to_build", "proven") and ST.drifts("not_built", "partly")
    assert ST.drifts("partly", "proven") and ST.drifts("partly", "wanted")
    # agreement is no drift, and the site's words that claim nothing never drift
    assert not (ST.drifts("built", "proven") or ST.drifts("wanted", "wanted") or ST.drifts("partly", "partly"))
    assert not any(ST.drifts(w, s) for w in ("today", "open", "directed", "none", None) for s in ("proven", "wanted", "failing"))
    # a row that is dropped, not run yet or declared says nothing against the site
    assert not any(ST.drifts(w, s) for w in ("built", "wanted") for s in ("dropped", "unknown", "declared"))
    j = good()
    j["steps"][0].update(site_status="to_build", tests=[REAL_TEST])
    j["steps"][1].update(site_status="built", tests=[REAL_TEST])
    j["edges"][0].update(code=[], binds=[], tests=[], backlog="BL-1")
    j["edges"][0]["site"]["status"] = "built"
    j["backlog"] = [{"id": "BL-1", "row": "edge:J9.1", "smallest": "Say it back.", "package": "later"}]
    doc = ST.compute(j, {REAL_TEST: "passed"})
    assert doc["drift"] == [{"row": "step:1", "site": "to_build", "state": "proven"},
                            {"row": "edge:J9.1", "site": "built", "state": "wanted"}], "the site says wanted and the row is proven; the site says built and it is wanted"
    assert [k for k, r in doc["rows"].items() if r["drift"]] == ["step:1", "edge:J9.1"]
    assert doc["rows"]["step:2"]["drift"] is False and doc["rows"]["step:2"]["site"] == "built"


def test_compute_fits_the_status_definition():
    j = good()
    j["steps"][0]["tests"] = [REAL_TEST]
    j["steps"][1]["tests"] = [REAL_TEST, "test_j1.py::test_j1_6_a_refused_preview_closes_the_request"]
    j["edges"][0]["tests"] = ["test_j1.py::test_j1_7_unanswered_question_stays_waiting_without_a_child"]
    results = {REAL_TEST: "passed", "test_j1.py::test_j1_6_a_refused_preview_closes_the_request": "failed"}
    doc = ST.compute(j, results)
    assert S.validate("journey.status", doc) == []
    assert (doc["id"], doc["definitions_sha"]) == ("J9", journeys.sha_of(j)), "stamped with the hash of the journey as it is"
    assert doc["tests"] == {REAL_TEST: "passed", "test_j1.py::test_j1_6_a_refused_preview_closes_the_request": "failed",
                            "test_j1.py::test_j1_7_unanswered_question_stays_waiting_without_a_child": "missing"}, \
        "every listed test has a result, and one nobody reported is missing"
    assert {k: r["state"] for k, r in doc["rows"].items()} == {"step:1": "proven", "step:2": "failing", "edge:J9.1": "failing"}
    assert doc["state"] == "failing" and doc["counts"] == {"proven": 1, "partly": 0, "failing": 2, "unproven": 0, "wanted": 0, "dropped": 0, "fault": 0}
    assert doc["rows"]["step:2"]["proven_by"] == [REAL_TEST] and doc["rows"]["step:2"]["failing"] == ["test_j1.py::test_j1_6_a_refused_preview_closes_the_request"]
    assert doc["rows"]["edge:J9.1"]["failing"] == ["test_j1.py::test_j1_7_unanswered_question_stays_waiting_without_a_child"]
    assert doc["drift"] == [{"row": "edge:J9.1", "site": "built", "state": "failing"}], "the site says built and the test that proves it failed"
    # nothing in it but the journey and the results: the same input is the same document, byte for byte
    assert json.dumps(doc, sort_keys=True) == json.dumps(ST.compute(copy.deepcopy(j), dict(results)), sort_keys=True)
    green = ST.compute(j, {t: "passed" for t in doc["tests"]})
    assert green["state"] == "proven" and green["counts"]["proven"] == 3 and S.validate("journey.status", green) == []
    # the rows of `was` have no state
    old = good("good-with-was")
    assert set(ST.compute(old, {})["rows"]) == {"%s:%s" % (k, r) for k, r, _ in journeys.rows(old)} and "was:step:0a" not in ST.compute(old, {})["rows"]
    # a declared journey is not computed: every row reads declared and nothing is run
    decl = good(id="FI1", kind="function", bound_to="identity", declared=True)
    doc = ST.compute(decl, {})
    assert S.validate("journey.status", doc) == [] and doc["state"] == "declared" and doc["tests"] == {}
    assert {r["state"] for r in doc["rows"].values()} == {"declared"} and ST.tests_listed(decl) == []
    assert ST.tests_listed([j, decl]) == sorted(doc_tests := set(ST.tests_listed(j))) and len(doc_tests) == 3
    assert ST.tests_listed({"J9": j, "FI1": decl}) == ST.tests_listed(j) == sorted(ST.tests_listed(j))


def test_compute_all_finds_a_row_of_another_journey_whichever_is_read_first():
    a, b = good(id="J2"), good(id="J3")
    for j in (a, b):
        j["steps"][0]["tests"], j["steps"][1]["tests"], j["edges"][0]["tests"] = [REAL_TEST], [REAL_TEST], [REAL_TEST]
    b["steps"][0].update(same_as="J2/step/2", tests=[], code=[], binds=[])
    got = ST.compute_all({"J3": b, "J2": a, "FI1": good(id="FI1", kind="function", bound_to="identity", declared=True)}, {REAL_TEST: "failed"})
    assert sorted(got) == ["J2", "J3"], "a declared journey has no document"
    assert got["J3"]["rows"]["step:1"]["state"] == "failing", "it is the other journey's row, which failed"
    got = ST.compute_all({"J3": b, "J2": a}, {REAL_TEST: "passed"})
    assert got["J3"]["rows"]["step:1"]["state"] == "proven"


def test_site_rows_of_the_saved_file():
    from journeys import site
    data = site.load()
    assert [j["id"].upper() for j in data["journeys"]] == ["J1", "J2", "J3", "J4", "J5", "J6", "J7"] and data["version"].startswith("2.4,")
    got = site.rows(data)
    # every row the site lists, per journey (steps, edges, build rows, directions, sub-journeys, quotes, the rows of `was`, `today`)
    assert {k: len(v["ids"]) for k, v in got.items()} == {"J1": 30, "J2": 66, "J3": 18, "J4": 12, "J5": 20, "J6": 11, "J7": 11}
    j1, j2 = got["J1"], got["J2"]
    assert len([i for i in j1["ids"] if i != "today"]) == 29 and "today" in j1["ids"]
    assert [i for i in j1["ids"] if i.startswith(("step:", "edge:"))] == ["step:%d" % n for n in range(1, 8)] + ["edge:J1.%d" % n for n in range(1, 10)]
    assert [i for i in j1["ids"] if i.startswith("direction:")] == ["direction:D-%s" % c for c in "abcdef"] and \
        [i for i in j1["ids"] if i.startswith("build:")] == ["build:B%d" % n for n in range(1, 8)]
    assert len([i for i in j2["ids"] if not i.startswith("was:") and i != "today"]) == 32 and "today" in j2["ids"]
    assert len([i for i in j2["ids"] if i.startswith("was:")]) == 33 and len(j2["was_edge_at"]) == 20
    assert [i for i in j2["ids"] if i.startswith("sub:")] == ["sub:J2.%s" % c for c in "abcdefgh"]
    assert j1["edge_at"] == {"J1.1": "4", "J1.2": "4", "J1.3": "5", "J1.4": "5", "J1.5": "5", "J1.6": "5", "J1.7": "2", "J1.8": "5", "J1.9": "3"}
    assert j1["step_says"]["5"] == "built, stamp to remove" and j1["step_says"]["3"] == "to build"
    assert j1["step_code"]["1"] == "wbFoundGo, POST /api/native/found"
    blocks = site.blocks(data)
    assert blocks["J1"]["tag"].startswith("THE FLOW YOU WANT") and blocks["J1"]["today"]["sources"] == "birth.md, sutra 50599599 and ef0e8c39."
    assert [len(blocks["J2"]["was"][k]) for k in ("steps", "edges")] == [13, 20] and blocks["J2"]["was"]["steps"][0]["n"] == "0a"
    assert blocks["J2"]["was"]["lanes"][0] and "was" not in blocks["J1"]
    # the words are the site's with the tags out, and {helper} counts as the site's word Sutra
    assert site.clean("<b>A</b>  rule &amp;\n more ") == "A rule & more"
    assert site.same("{helper} asks", "Sutra asks") and not site.same("Root asks", "Sutra asks") and site.same("", "") and site.same(None, "")
    assert site.status_of("Wanted: x") == "wanted" and site.status_of("built, name to change") == "built" and \
        site.status_of("Partly built: x") == "partly" and site.status_of("To build.") == "to_build" and site.status_of("hm") == "none"
    # a file that is not the saved one is read from its path
    assert site.load(site.SAVED)["journeys"][0]["id"] == "j1"
