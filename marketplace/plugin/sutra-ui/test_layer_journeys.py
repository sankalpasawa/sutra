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


# ---- Q3: the twelve cases ---------------------------------------------------------------------------------------------
from journeys import contract as C                                             # noqa: E402

STATIC_CASES = ("JC-1", "JC-2", "JC-3", "JC-4", "JC-5", "JC-6", "JC-7", "JC-9", "JC-10", "JC-11", "JC-12")
#: what the fixture journey's edge says to the owner (outcome.golden): the code says it, and the test the edge lists asserts it
#: here, in this file: "the department already has this rule"
GOLDEN = "the department already has this rule"


def proven(**change):
    """The fixture journey with the one thing it lacks to pass every case: a test for its edge (the test that asserts the
    edge, which is the one below)."""
    j = good(**change)
    j["edges"][0]["tests"] = ["test_layer_journeys.py::test_the_good_journey_passes_every_case"]
    return j


def broken(cid, journey_list, *words, also=()):
    """The case `cid` finds a fault in these journeys, one sentence names every word given, and no other case finds any
    (but those in `also`): a failing example is a single mutation, and a single mutation breaks one rule."""
    got = C.cases(journey_list if isinstance(journey_list, list) else [journey_list])
    assert set(got) == set(STATIC_CASES), "the cases: JC-1 to JC-7 and JC-9 to JC-12 (JC-8 needs a run)"
    assert any(all(w in f for w in words) for f in got[cid]), (cid, words, got[cid])
    others = {k: v for k, v in got.items() if k != cid and k not in also and v}
    assert not others, others
    return got[cid]


def test_the_good_journey_passes_every_case():
    assert GOLDEN in HERE.joinpath("test_layer_journeys.py").read_text(encoding="utf-8").lower()
    got = C.cases([proven()])
    assert set(got) == set(STATIC_CASES)
    assert got == {k: [] for k in STATIC_CASES}, got
    # the journey as the fixture is has one fault, and it is the one the fixture says it proves nothing about
    assert C.cases([good()])["JC-7"] == ["J9 edge J9.1 has code and lists no test: it is unproven"]
    # and the earlier rows a journey keeps are not rows: the same ids in `was` are not a clash
    old = proven(**{"was": good("good-with-was")["was"]})
    assert C.cases([old]) == {k: [] for k in STATIC_CASES}
    # a list, a dict of them, and one journey are the same journeys
    assert C.cases({"J9": proven()}) == C.cases(proven()) == C.cases([proven()])


def test_a_case_never_raises_on_what_it_is_given(folder):
    whole = proven()
    rubbish = [{}, {"id": "J9"}, {"id": "J8", "steps": [None, 3, {}, {"n": 4}], "edges": [{"id": "J8.1"}, "x"], "was": "x", "sub": [1],
                                  "serves": [5], "children": [7], "lanes": None, "build_rows": ["x"], "scenarios": [None]},
               {"id": "J7", "steps": [{"n": "1", "binds": [{"kind": "act"}, {"kind": "step"}, {"kind": "mystery"}, {}], "code": [3], "tests": "x"}],
                "edges": [{"id": "J7.1", "at": None, "outcome": "ask", "tests": [None], "site": 4}], "was": {"steps": [{}], "edges": [{}]}},
               whole]
    got = C.cases(rubbish)
    assert set(got) == set(STATIC_CASES) and all(isinstance(v, list) and all(isinstance(f, str) for f in v) for v in got.values())
    assert not any("could not be checked" in f for v in got.values() for f in v), "a journey that is not whole is a fault, not a crash"
    assert got["JC-1"], "and the shape is where it is told"
    # nothing at all, and the folder: an empty folder passes, a folder with a bad file says so in JC-1
    assert C.cases([]) == {k: [] for k in STATIC_CASES} == C.cases()
    (folder / "J8.json").write_text("{ not json", encoding="utf-8")
    assert C.cases()["JC-1"] == ["the journey file J8.json is refused: it is not JSON (Expecting property name enclosed in double quotes: "
                                 "line 1 column 3 (char 2))"]
    assert all(v == [] for k, v in C.cases().items() if k != "JC-1")


def test_jc1_a_step_with_no_lane_and_an_unknown_field_fail_the_shape():
    j = proven()
    del j["steps"][0]["lane"]
    broken("JC-1", j, "J9 step 1", "does not fit the journey definition", "lane: is missing")
    j = proven()
    j["edges"][0]["colour"] = "red"
    broken("JC-1", j, "J9 edge J9.1", "colour: is not a field here")
    j = proven()
    j["state"] = "proven"
    broken("JC-1", j, "J9 does not fit the journey definition", "state: is not a field here")
    j = proven()
    j["steps"][1]["lane"] = "audit"
    broken("JC-1", j, "J9 step 2", "lane audit", "lists no such lane")


def test_jc2_ids_are_unique_and_begin_with_their_journeys():
    j = proven()
    j["edges"].append(copy.deepcopy(j["edges"][0]))
    broken("JC-2", j, "J9 has the edge id J9.1 twice")
    j = proven()
    j["steps"].append(copy.deepcopy(j["steps"][0]))
    broken("JC-2", j, "J9 has the step number 1 twice")
    j = proven()
    j["edges"].append(dict(copy.deepcopy(j["edges"][0]), id="J2.9"))
    broken("JC-2", j, "J9 edge J2.9 does not begin with J9.")
    j = proven()
    j["sub"] = [{"id": "J2.a", "title": "A", "step": "1"}, {"id": "J9.b", "title": "B", "step": "1"}, {"id": "J9.b", "title": "C", "step": "2"}]
    got = broken("JC-2", j, "J9 sub-journey J2.a does not begin with J9.")
    assert any("J9 has the sub-journey J9.b twice" in f for f in got)
    # two journeys with one id; and a backlog entry defined twice
    broken("JC-2", [proven(), proven()], "J9 is the id of more than one journey")
    a, b = proven(), proven(id="J8")
    a["backlog"] = b["backlog"] = [{"id": "BL-1", "row": "edge:J9.1", "smallest": "Say it.", "package": "later"}]
    broken("JC-2", [a, b], "the backlog entry BL-1 is defined more than once (J9, J8)")
    # build rows and directions carry ids too
    j = proven()
    j["build_rows"] = [{"id": "B1", "change": "x"}, {"id": "B1", "change": "y"}]
    broken("JC-2", j, "J9 has the build row B1 twice")
    # `was` is a namespace of its own: it may reuse the ids of the rows above, and repeats nothing of its own
    old = proven(**{"was": good("good-with-was")["was"]})
    assert C.case_jc2([old]) == []
    old["was"]["edges"].append(copy.deepcopy(old["was"]["edges"][0]))
    assert C.case_jc2([old]) == ["J9 has the earlier edge id J9.1 twice"]
    old["was"]["edges"][1]["id"] = "J2.1"
    assert C.case_jc2([old]) == ["J9 earlier edge J2.1 does not begin with J9."]


def test_jc3_places_resolve():
    broken("JC-3", proven(serves=["J99:1"]), "J9 serves step 1 of J99", "there is no journey J99")
    parent = proven(id="J8")
    broken("JC-3", [parent, proven(serves=["J8:9"])], "J9 serves step 9 of J8", "J8 has no step 9")
    assert C.case_jc3([parent, proven(serves=["J8:1"])]) == []
    broken("JC-3", proven(inside="J13"), "J9 is inside J13", "there is no journey J13")
    broken("JC-3", proven(inside="J9"), "J9 is inside itself")
    a, b = proven(id="J10", inside="J11"), proven(id="J11", inside="J10")
    got = C.case_jc3([a, b])
    assert any("J10 is inside itself" in f for f in got) and any("J11 is inside itself" in f for f in got) and len(got) == 2
    c = proven(id="J12", inside="J10")                     # inside a loop, but not part of it: no sentence of its own
    assert len(C.case_jc3([a, b, c])) == 2
    broken("JC-3", proven(children=["J8"]), "J9 lists J8 as a child", "there is no journey J8")
    kid = proven(id="J8")
    broken("JC-3", [proven(children=["J8"]), kid], "J9 lists J8 as a child", "J8 is not inside J9")
    assert C.case_jc3([proven(children=["J8"]), dict(kid, inside="J9")]) == []
    j = proven()
    j["steps"][1]["child"] = "J5"
    broken("JC-3", j, "J9 step 2 opens the journey J5")
    j = proven()
    j["sub"] = [{"id": "J9.a", "title": "A", "step": "7"}]
    broken("JC-3", j, "J9 sub-journey J9.a hangs under step 7")
    j = proven()
    j["edges"][0]["at"] = "9"
    broken("JC-3", j, "J9 edge J9.1 hangs under step 9", "J9 has no such step", also=("JC-9",) if False else ())
    j["edges"][0]["at"] = "any"
    assert C.case_jc3([j]) == [], "an edge of a function journey may hang under any step"
    old = proven(**{"was": good("good-with-was")["was"]})
    old["was"]["edges"][0]["at"] = "7"
    assert C.case_jc3([old]) == ["J9 earlier edge J9.1 hangs under step 7, and the earlier version has no such step"]
    # a function journey is bound to a function, a user journey to none
    broken("JC-3", proven(kind="function"), "J9 is a function journey and is bound to no function", also=("JC-12",))
    broken("JC-3", proven(bound_to="identity"), "J9 is a user journey and is bound to identity")


def test_jc4_binds_are_held_to_what_exists(monkeypatch):
    bind = lambda **b: b                                                                       # noqa: E731
    cases = [
        (bind(kind="act", src="Audit", act="request", word="x", dst="Owner"), "binds the act (Audit, request, x, Owner)", "no sender sends it"),
        (bind(kind="act", src="Owner", act="request", word="front", dst="Audit"), "binds the act (Owner, request, front, Audit)", "no sender sends it"),
        (bind(kind="act", src="Identity", act="inform", word="request"), "binds act and leaves out its dst", ""),
        (bind(kind="step", id="no.such_step"), "binds the step no.such_step", "no engine has a step of that id"),
        (bind(kind="event", action="x.y"), "binds the event x.y", "the ledger has no such action"),
        (bind(kind="ui", symbol="wbNoSuchThing"), "binds the screen symbol wbNoSuchThing", "no script defines it"),
        (bind(kind="ui", symbol="setup_say"), "binds the screen symbol setup_say", "no script defines it"),       # a Python name is no script's
        (bind(kind="api", method="POST", path="/api/native/nope"), "binds the route POST /api/native/nope", "the app has no such route"),
        (bind(kind="api", method="GET", path="/api/native/found"), "binds the route GET /api/native/found", "the app has no such route"),
        (bind(kind="api", path="/api/native/found"), "binds api and leaves out its method", ""),
    ]
    monkeypatch.setitem(C._ROUTES, "routes", {("POST", "/api/native/found"), ("GET", "/api/native/{ref}/chat")})
    for b, *words in cases:
        j = proven()
        j["steps"][0]["binds"].append(b)
        broken("JC-4", j, "J9 step 1", *[w for w in words if w])
        j = proven()
        j["edges"][0]["binds"].append(b)
        broken("JC-4", j, "J9 edge J9.1", *[w for w in words if w])
    good_binds = [bind(kind="act", src="Owner", act="request", word="front", dst="Identity"), bind(kind="act", src="Identity", act="inform", word="question", dst="Owner"),
                  bind(kind="act", src="Priority", act="accept-proposal", word="anything at all", dst="Adaptation"),     # a row that takes any word
                  bind(kind="step", id="setup.converse"), bind(kind="step", id="identity.rule"), bind(kind="event", action="ask.created"),
                  bind(kind="ui", symbol="wbFoundGo"), bind(kind="api", method="POST", path="/api/native/found"),
                  bind(kind="api", method="GET", path="/api/native/{ref}/chat"), bind(kind="person", what="You type the name")]
    j = proven()
    j["steps"][0]["binds"] = good_binds
    assert C.case_jc4([j]) == []
    # a step of a journey that is not declared binds something; an edge need not, a declared journey need not, and a step that
    # is the same as another's or that the owner dropped need not
    j = proven()
    j["steps"][1]["binds"] = []
    broken("JC-4", j, "J9 step 2 binds nothing")
    j["edges"][0]["binds"] = []
    assert len(C.case_jc4([j])) == 1
    k = copy.deepcopy(j)
    k["steps"][1].update(same_as="J8/step/1")
    assert C.case_jc4([k]) == []
    k["steps"][1].pop("same_as")
    k["steps"][1]["disposition"] = "drop"
    assert C.case_jc4([k]) == []
    j["declared"] = True
    assert C.case_jc4([j]) == []
    # the earlier rows of a journey bind nothing, and a bind on one is still held to what exists
    old = proven(**{"was": good("good-with-was")["was"]})
    assert C.case_jc4([old]) == []
    old["was"]["steps"][0]["binds"] = [bind(kind="event", action="x.y")]
    assert C.case_jc4([old]) == ["J9 earlier step 0a binds the event x.y, and the ledger has no such action"]
    # an app that does not import skips the routes with a printed line, and nothing else
    monkeypatch.setitem(C._ROUTES, "routes", None)
    j = proven()
    j["steps"][0]["binds"].append(bind(kind="api", method="POST", path="/api/native/nope"))
    assert C.case_jc4([j]) == []


def test_jc4_api_binds_are_held_to_the_route_table_of_the_real_app(monkeypatch):
    monkeypatch.delitem(C._ROUTES, "routes", raising=False)
    j = proven()
    j["steps"][0]["binds"].append({"kind": "api", "method": "POST", "path": "/api/native/found"})
    j["steps"][0]["binds"].append({"kind": "api", "method": "GET", "path": "/api/native/{ref}/chat"})
    assert C.case_jc4([j]) == [], "the routes the J1 and J3 journeys bind are the app's"
    assert ("POST", "/api/native/found") in C._ROUTES["routes"] and len(C._ROUTES["routes"]) > 200
    j["steps"][1]["binds"].append({"kind": "api", "method": "POST", "path": "/api/native/found/again"})
    assert C.case_jc4([j]) == ["J9 step 2 binds the route POST /api/native/found/again, and the app has no such route"]


def test_jc5_a_name_no_code_defines_fails_its_row():
    j = proven()
    j["steps"][0]["code"] = ["identity_file", "setup_sayy"]
    broken("JC-5", j, "J9 step 1", "names setup_sayy in its code", "no code defines it")
    j = proven()
    j["edges"][0]["code"] = ["website_dept.nope"]
    broken("JC-5", j, "J9 edge J9.1", "website_dept.nope")
    j = proven()
    j["steps"][0]["code"] = ["setup_say", "website_dept.create", "wbFoundGo", "engine_runtime.setup_say"]
    assert C.case_jc5([j]) == []


def test_jc6_a_test_no_suite_has_fails_its_row():
    j = proven()
    j["steps"][0]["tests"].append("test_j1.py::test_no_such")
    broken("JC-6", j, "J9 step 1", "lists the test test_j1.py::test_no_such", "there is no such test")
    j = proven()
    j["edges"][0]["tests"] = ["js:test_website.js#W999"]
    broken("JC-6", j, "J9 edge J9.1", "js:test_website.js#W999", also=("JC-10",))
    j = proven()
    j["build_rows"] = [{"id": "B1", "change": "x", "tests": [REAL_TEST, "test_nothing.py::test_x"]}]
    broken("JC-6", j, "J9 build row B1", "test_nothing.py::test_x")
    j = proven()
    j["scenarios"] = [{"id": "J9.walk", "lane": "the life", "test": "test_layer_journey_j9.py::test_walk"}]
    broken("JC-6", j, "J9 scenario J9.walk", "test_layer_journey_j9.py::test_walk")
    j = proven()
    j["steps"][0]["tests"] = ["test_engine_runtime.py::TestTheFiveJourneys::test_37_a_directive_is_restated_put_back_and_kept_only_on_a_stamp",
                              "js:test_website.js#W45", REAL_TEST]
    assert C.case_jc6([j]) == []


def test_jc7_a_row_is_proven_or_wanted():
    # code and no tests: unproven
    j = proven()
    j["edges"][0]["tests"] = []
    broken("JC-7", j, "J9 edge J9.1", "has code and lists no test", "unproven", also=("JC-10",))   # and nothing asserts what it says
    # an edge that lists tests says what the code does, in at least 20 characters
    for says in ("", "Says it.", "  "):
        j = proven()
        j["edges"][0]["code_does"] = says
        broken("JC-7", j, "J9 edge J9.1", "does not say what the code does")
    # a step needs no sentence
    j = proven()
    assert not j["steps"][0].get("code_does")
    assert C.case_jc7([j]) == []
    # wanted: no code, a backlog entry some journey defines, no test
    def wanted(**row):
        w = proven()
        w["edges"][0].update(code=[], binds=[], tests=[], backlog="BL-1", outcome={"kind": "none", "voice": "none", "golden": None}, **row)
        w["backlog"] = [{"id": "BL-1", "row": "edge:J9.1", "smallest": "Say it back.", "package": "later"}]
        return w
    assert C.case_jc7([wanted()]) == []
    w = wanted()
    w["edges"][0]["tests"] = [REAL_TEST]
    broken("JC-7", w, "J9 edge J9.1", "has no code and lists a test", "a wanted row lists none")
    w = wanted()
    w["edges"][0]["backlog"] = None
    broken("JC-7", w, "J9 edge J9.1", "has no code and no backlog entry")
    w = wanted()
    w["backlog"] = []
    broken("JC-7", w, "J9 edge J9.1", "names the backlog entry BL-1", "no journey defines it")
    assert C.case_jc7([w, dict(proven(id="J8"), backlog=wanted()["backlog"])]) == [], "some other journey may define it"
    # built, with a part named as not built: partly, and still code and tests
    p = proven()
    p["edges"][0]["backlog"] = "BL-1"
    p["backlog"] = wanted()["backlog"]
    assert C.case_jc7([p]) == []
    # a row that is the same as another, or that the owner dropped, is not held to this; nor is a declared journey
    s = proven()
    s["edges"][0].update(tests=[], same_as="J1/edge/J1.5")
    assert C.case_jc7([s]) == []
    d = proven()
    d["edges"][0].update(tests=[], disposition="drop")
    assert C.case_jc7([d]) == []
    d = proven(declared=True)
    d["edges"][0]["tests"] = []
    assert C.case_jc7([d]) == []


def _from_site(jid="J1"):
    """A journey that carries everything the saved site file lists for `jid`, in the site's words: faithful by construction."""
    from journeys import site
    data = site.load()
    live = {x["id"].upper(): x for x in data["journeys"]}[jid]
    listed, blocks = site.rows(data)[jid], site.blocks(data).get(jid, {})
    j = {"schema_version": 1, "id": jid, "title": "From the site", "kind": "person", "inside": None, "bound_to": None, "serves": [],
         "declared": True, "goal": "x", "lanes": [], "steps": [site.step_row(s) for s in live["steps"]],
         "edges": [site.edge_row(e) for e in live["edges"]], "site_ids": list(listed["ids"]),
         "build_rows": [{"id": "B%d" % (i + 1), "change": "x"} for i, _ in enumerate(live.get("build") or [])],
         "directions": [{"id": x["id"], "direction": "x"} for x in data["directed"]] if jid == "J1" else [],
         "sub": [{"id": s[0], "title": "x", "step": "1"} for s in live.get("sub") or []],
         "quotes": [{"text": "x"} for _ in live.get("said") or []]}
    for key in ("tag", "today", "was"):
        if key in blocks:
            j[key] = copy.deepcopy(blocks[key])
    return j


def test_jc9_a_journey_made_of_the_sites_rows_is_faithful():
    for jid in ("J1", "J2", "J3", "J4", "J5", "J6", "J7"):
        assert C.case_jc9([_from_site(jid)]) == [], jid
    assert C.case_jc9([proven()]) == [], "a journey the site does not list is not held to it"
    assert C.case_jc9([]) == []
    j = _from_site("J1")
    assert len(j["steps"]) == 7 and len(j["edges"]) == 9 and len(j["site_ids"]) == 30
    # the token {helper} counts as the site's word Sutra
    for row in j["steps"] + j["edges"]:
        for key in ("text", "trigger"):
            if key in row:
                row[key] = row[key].replace("Sutra", "{helper}")
    j["steps"][4]["text"] = j["steps"][4]["text"].replace("Sutra", "{helper}")
    assert any("{helper}" in r.get("text", "") + r.get("trigger", "") for r in j["steps"] + j["edges"])
    assert C.case_jc9([j]) == []


def test_jc9_a_row_deleted_from_both_the_steps_and_the_site_ids_is_still_caught():
    j = _from_site("J1")
    j["edges"] = [e for e in j["edges"] if e["id"] != "J1.3"]
    j["site_ids"].remove("edge:J1.3")
    assert [f for f in C.case_jc9([j])] == ["J1 lacks the row edge:J1.3 that the site lists: a row leaves only by the owner's mark drop"], \
        "the journey data alone could not catch this: it holds neither the row nor the id; the saved copy of the site does"
    j = _from_site("J1")
    j["steps"] = [s for s in j["steps"] if s["n"] != "4"]
    got = C.case_jc9([j])
    assert any("J1 lacks the row step:4" in f for f in got) and not any("step:5" in f for f in got)
    for rid in ("build:B2", "direction:D-c", "today"):
        j = _from_site("J1")
        if rid == "build:B2":
            j["build_rows"] = [b for b in j["build_rows"] if b["id"] != "B2"]
        elif rid == "direction:D-c":
            j["directions"] = [d for d in j["directions"] if d["id"] != "D-c"]
        else:
            del j["today"]
        j["site_ids"].remove(rid)
        assert any(("J1 lacks the row " + rid) in f for f in C.case_jc9([j])), rid
    j = _from_site("J2")
    j["sub"] = j["sub"][:-1]
    j["quotes"] = j["quotes"][:-1]
    j["was"]["steps"] = j["was"]["steps"][1:]
    j["was"]["edges"] = j["was"]["edges"][:-1]
    got = C.case_jc9([j])
    for rid in ("sub:J2.h", "quote:8", "was:step:0a", "was:edge:J2.20"):
        assert any(("J2 lacks the row " + rid) in f for f in got), rid
    # a row that is there but is not in the journey's own list of the rows the site lists
    j = _from_site("J1")
    j["site_ids"].remove("edge:J1.3")
    assert C.case_jc9([j]) == ["J1 does not list the row edge:J1.3 among the rows the site lists (site_ids)"]
    # a row the owner dropped stays: the mark keeps the row and removes its weight
    j = _from_site("J1")
    j["edges"][2]["disposition"] = "drop"
    assert C.case_jc9([j]) == []


def test_jc9_an_edge_moved_under_another_step_or_a_changed_word_fails_its_row():
    j = _from_site("J1")
    edge = next(e for e in j["edges"] if e["id"] == "J1.7")
    assert edge["at"] == "2"
    edge["at"] = "3"
    assert C.case_jc9([j]) == ["J1 edge J1.7 hangs under step 3, and the site hangs it under step 2"]
    for where, key, what in (("steps", "text", "text"), ("steps", "site_code", "Code column"), ("steps", "site_says", "status words"),
                             ("steps", "site_function", "function"), ("edges", "trigger", "trigger")):
        j = _from_site("J1")
        j[where][2][key] = j[where][2][key] + " (and more)"
        got = C.case_jc9([j])
        assert len(got) == 1 and (("step 3" if where == "steps" else "edge J1.3") in got[0]) and ("says its %s differently from the site" % what) in got[0], got
    j = _from_site("J1")
    j["edges"][4]["site"]["text"] = "Built: it is done."
    assert C.case_jc9([j]) == ["J1 edge J1.5 says its status words differently from the site (the site: " + _from_site("J1")["edges"][4]["site"]["text"][:60] + "...)"]
    # the words of the page and of the earlier version are the site's too
    j = _from_site("J1")
    j["tag"] = "THE FLOW I WANT"
    j["today"]["text"] += " Not so."
    j["today"]["sources"] = "somewhere else"
    got = C.case_jc9([j])
    assert [f.split(" says ")[1].split(" differently")[0] for f in got] == ["its tag", 'its "how it runs today" block', 'its sources of the "how it runs today" block']
    j = _from_site("J2")
    j["was"]["title"] = "Another title"
    j["was"]["steps"][4]["text"] += "!"
    j["was"]["edges"][6]["at"] = "1"
    got = C.case_jc9([j])
    assert len(got) == 3 and any("J2 earlier step 3 says its text" in f for f in got) and any("J2 earlier edge J2.7 hangs under step 1" in f for f in got)
    # a short label and the normalised status word are the author's, not the site's
    j = _from_site("J1")
    j["steps"][0]["short"] = "Type the name"
    j["steps"][0]["site_status"] = "to_build"
    j["edges"][0]["short"] = "Vague"
    j["edges"][0]["site"]["status"] = "built"
    assert C.case_jc9([j]) == []
    # a missing saved file is a fault, not a crash
    assert "cannot be read" in C.case_jc9([j], path=HERE / "test_fixtures" / "journeys" / "nope.json")[0]


def test_jc10_the_words_an_edge_says_are_in_the_code_and_in_a_test_it_lists():
    j = proven()
    j["edges"][0]["outcome"]["golden"] = "this sentence is in no code at all"
    broken("JC-10", j, "J9 edge J9.1", 'says "this sentence is in no code at all" to the owner', "no code says it")
    # the code says it, but no test file the journey lists does
    j = proven()
    j["edges"][0]["tests"] = [REAL_TEST]
    j["steps"][0]["tests"] = [REAL_TEST]
    j["steps"][1]["tests"] = [REAL_TEST]
    got = broken("JC-10", j, "J9 edge J9.1", 'says "%s" to the owner' % GOLDEN, "no test file the journey lists asserts it")
    assert len(got) == 1
    # case, a backslash in the source and the spaces between words do not matter
    j = proven()
    j["edges"][0]["outcome"]["golden"] = "The department  ALREADY has this rule"
    assert C.case_jc10([j]) == []
    # only an ask or a tell has a golden lead the owner reads; nothing to search for otherwise
    for kind in ("file", "hold", "refuse", "block", "retry", "none"):
        j = proven()
        j["edges"][0]["outcome"] = {"kind": kind, "voice": "none", "golden": "this sentence is in no code at all"}
        assert C.case_jc10([j]) == [], kind
    j = proven()
    j["edges"][0]["outcome"] = {"kind": "ask", "voice": "Identity", "golden": None}
    assert C.case_jc10([j]) == []
    # a declared journey is a design: what it will say is not in the code yet
    j = proven(declared=True)
    j["edges"][0]["outcome"]["golden"] = "this sentence is in no code at all"
    assert C.case_jc10([j]) == []
    # a step has no outcome; a test file the journey lists that is not there is JC-6's to say
    j = proven()
    for row in j["steps"] + j["edges"]:
        row["tests"] = ["test_layer_journey_j9.py::test_walk"]
    assert C.case_jc10([j]) == [], "the walk file is not written yet: only JC-6 says so"
    assert C.case_jc6([j]) != []


def test_jc11_the_words_an_owner_reads_hold_no_banned_word():
    for word in ("charter", "Charters", "grant", "Granted", "counter", "refuse", "refused", "requester", "CEO", "internal system"):
        j = proven()
        j["edges"][0]["outcome"]["golden"] = "the department already has this rule (%s)" % word
        got = C.case_jc11([j])
        assert len(got) == 1 and "J9 edge J9.1 has the word" in got[0] and "in its golden lead" in got[0], (word, got)
        j = proven()
        j["edges"][0]["reword"] = "Say it back with the word %s in it." % word
        got = C.case_jc11([j])
        assert len(got) == 1 and "in its reword" in got[0], (word, got)
    # the site's own labels are data and may say it; so may the trigger and the code's description
    j = proven()
    j["edges"][0].update(short="Priority refuses", trigger="Priority refuses the offer.", code_does="The offer is refused and the owner is told so.")
    j["edges"][0]["site"]["text"] = "Refused: the owner is told why."
    j["steps"][0]["text"] = "A grant, a counter or a refusal."
    assert C.case_jc11([j]) == []
    assert C.case_jc11([proven()]) == []


def test_jc12_function_journeys_are_bound_and_point_at_rows_that_exist():
    def fn(jid="FI1", **change):
        return proven(**dict({"id": jid, "kind": "function", "bound_to": "identity"}, **change))
    user = proven(id="J8")
    assert C.case_jc12([user, fn(serves=["J8:1"])]) == []
    broken("JC-12", fn(bound_to="marketing"), "FI1 is bound to marketing", "not one of the five functions", also=("JC-1", "JC-3"))
    broken("JC-12", fn(bound_to=None), "FI1 is bound to None", also=("JC-3",))
    target = proven(id="J8", kind="function", bound_to="audit")
    broken("JC-12", fn(serves=["J8:1"]), "FI1 serves a step of J8", "which is a function journey", also=("JC-3",)) if False else None
    got = C.case_jc12([target, fn(serves=["J8:1"])])
    assert got == ["FI1 serves a step of J8, which is a function journey: it serves a step of a user journey"], got
    # same_as: the row exists, and is not itself a same_as
    j = proven()
    j["steps"][1].update(same_as="J10/step/3", tests=[], code=[], binds=[], backlog="BL-1")
    j["backlog"] = [{"id": "BL-1", "row": "step:2", "smallest": "x", "package": "x"}]
    got = broken("JC-12", j, "J9 step 2 is the same row as J10/step/3", "there is no such row")
    other = proven(id="J10")
    other["steps"].append(dict(other["steps"][0], n="3"))
    assert C.case_jc12([j, other]) == []
    other["steps"][2].update(same_as="J10/step/1")
    broken("JC-12", [j, other], "J9 step 2 is the same row as J10/step/3", "itself the same as another")
    j["steps"][1]["same_as"] = "J10/edge/J10.9"
    assert "J9 step 2 is the same row as J10/edge/J10.9" in C.case_jc12([j, other])[0]
    # a function journey that is not declared has every row proven
    f = fn()
    assert C.case_jc12([f]) == []
    f["edges"][0]["tests"] = []
    got = C.case_jc12([f])
    assert got == ["FI1 is not declared, and its edge FI1.1 would read unproven even if every test passed: every row is proven, or the journey is declared"] or \
        got == ["FI1 is not declared, and its edge J9.1 would read unproven even if every test passed: every row is proven, or the journey is declared"], got
    f["declared"] = True
    assert C.case_jc12([f]) == []
    w = fn()
    w["edges"][0]["backlog"] = "BL-1"
    assert "would read partly" in C.case_jc12([w])[0], "built with a part not built is not proven: it is declared, or it is proven"


def test_every_shipped_journey_passes_every_static_case():
    """The journeys of journeys/ (the content packages add them) pass the static cases; an empty folder passes too."""
    got = C.cases()
    assert set(got) == set(STATIC_CASES)
    assert got == {k: [] for k in STATIC_CASES}, {k: v[:5] for k, v in got.items() if v}


# ---- Q4: the walk helper -----------------------------------------------------------------------------------------------
from journeys import walk as WK                                                # noqa: E402

TRACE_SAMPLE = FIXTURES / "trace-sample.json"
SAY = "It teaches algebra to Class 8 students so that they practise every week"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """A department founded and asked the way test_j1.py's fixture does, with the offline model, run to idle: Root said one
    question, the owner answered, and Root made the department. (W, R, J, the root's ref, the child's ref.)"""
    import importlib
    with pytest.MonkeyPatch.context() as mp:
        home = tmp_path_factory.mktemp("walk")
        mp.setenv("SUTRA_NATIVE_DEPT_HOME", str(home / "departments"))
        mp.setenv("SUTRA_NATIVE_HOME", str(home / "registry"))
        mp.setenv("SUTRA_UI_PROPOSALS", str(home / "proposals"))
        mp.setenv("SUTRA_WEBSITE_OFFLINE", "1")
        mp.setenv("J1_FLOW_V1", "1")
        mp.setenv("J2_FLOW_V1", "1")
        mp.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
        import website_dept as W
        import founding
        import placement_engine as E
        import org2_apply
        import engine_runtime as R
        import j2_runtime as J
        for module in (E, W, org2_apply, founding, R, J):
            importlib.reload(module)
        if not E.active_roots(E.load_domains()):
            E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
        root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
        W.owner_ask(root, "Build me a website")
        W.run_until_idle(root, limit=200)
        W.owner_ask(root, SAY)
        W.run_until_idle(root, limit=200)
        child = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
        yield W, R, J, root, child, home


def _files(home):
    """Every file of the record and what is in it: a read must leave all of this as it was."""
    import hashlib
    return {str(p.relative_to(home)): (p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(home.rglob("*")) if p.is_file()}


def test_trace_reads_only_the_record(run):
    W, R, J, root, child, home = run
    before = _files(home)
    assert before, "there is a record to read"
    got = WK.trace(W, R, J, root, child)
    assert _files(home) == before, "a trace writes nothing: not a row, not a file, not a time"
    assert set(got) == {"board", "steps", "events", "asks"}
    first = got["board"][0]
    assert first == {"ref": root, "n": 1, "src": "Owner", "dst": ["Identity"], "act": "request", "word": "front"}
    assert [(p["src"], p["act"], p["word"]) for p in got["board"] if p["ref"] == root][:3] == \
        [("Owner", "request", "front"), ("Identity", "inform", "question"), ("Owner", "request", "front")], "the order it was written"
    assert got["board"][-1]["ref"] == child, "the departments in the order they were given"
    assert all(set(p) == {"ref", "n", "src", "dst", "act", "word"} and isinstance(p["dst"], list) for p in got["board"])
    steps = [s["step"] for s in got["steps"]]
    assert {"setup.converse", "setup.say", "setup.shape", "setup.make", "setup.file"} <= set(steps)
    assert steps.index("setup.converse") < steps.index("setup.say") < steps.index("setup.shape") < steps.index("setup.make") < steps.index("setup.file")
    assert all(set(s) == {"engine", "step", "status"} for s in got["steps"])
    assert got["events"] == [] and got["asks"] == [], "Root has no cycle and asked nothing: it said, and made the department"
    # the same record, the same trace; one department alone is the part of it
    assert WK.trace(W, R, J, root, child) == got
    assert WK.trace(W, R, J, root)["board"] == [p for p in got["board"] if p["ref"] == root]
    assert WK.trace(W, R, J) == {"board": [], "steps": [], "events": [], "asks": []}
    assert _files(home) == before


def _walked(**change):
    """A hand-made journey of two steps that the J1 run really produced: the owner's words and Root's one question; Root's
    answer to the second words, and the department it made."""
    j = proven(id="J9")
    j["steps"] = [dict(j["steps"][0], n="1", binds=[
        {"kind": "act", "src": "Owner", "act": "request", "word": "front", "dst": "Identity"},
        {"kind": "step", "id": "setup.converse"}, {"kind": "step", "id": "setup.say"},
        {"kind": "act", "src": "Identity", "act": "inform", "word": "question", "dst": "Owner"}]),
        dict(j["steps"][1], n="2", binds=[
            {"kind": "step", "id": "setup.shape"}, {"kind": "step", "id": "setup.make"}, {"kind": "step", "id": "setup.file"},
            {"kind": "act", "src": "Identity", "act": "inform", "word": "department", "dst": "Owner"}])]
    j["scenarios"] = [{"id": "J9.walk", "lane": "the life", "test": "test_layer_journeys.py::test_follows_a_real_run", "walks": ["1", "2"]}]
    j.update(change)
    return j


def test_follows_a_real_run(run):
    W, R, J, root, child, home = run
    got = WK.trace(W, R, J, root)
    assert WK.follows(_walked(), got) == [], "the walk the scenario names is followed, in the order the steps give"
    assert WK.follows(_walked(), got, walks=["1"]) == [] == WK.follows(_walked(), got, ["1", "2"])
    # the trace of the child as well: its Owner request was posted by Root, and the steps of both are in one list
    both = WK.trace(W, R, J, root, child)
    assert WK.follows(_walked(), both) == []


def test_follows_names_a_missing_bind():
    sample = json.loads(TRACE_SAMPLE.read_text(encoding="utf-8"))
    assert WK.follows(_walked(), sample) == []
    # a bind that did not happen: the fault names the step and the bind
    j = _walked()
    j["steps"][1]["binds"].append({"kind": "act", "src": "Audit", "act": "inform", "word": "finding", "dst": "Identity"})
    assert WK.follows(j, sample) == ["J9 step 2: the act (Audit, inform, finding, Identity) did not happen"]
    j = _walked()
    j["steps"][0]["binds"].append({"kind": "step", "id": "setup.no_such_step"})
    assert WK.follows(j, sample) == ["J9 step 1: the step setup.no_such_step did not happen"]
    j = _walked()
    j["steps"][1]["binds"].append({"kind": "event", "action": "ask.created"})
    assert WK.follows(j, sample) == ["J9 step 2: the event ask.created did not happen"]
    with_event = dict(sample, events=[{"action": "ask.created", "step": 4}])
    assert WK.follows(j, with_event) == [], "and when it did, it did"
    # an act is matched on all four: the sender, the act, the word and the receiver
    for change in ({"src": "Root"}, {"act": "request"}, {"word": "front"}, {"dst": "Adaptation"}):
        j = _walked()
        j["steps"][0]["binds"][3] = dict(j["steps"][0]["binds"][3], **change)
        assert len(WK.follows(j, sample)) == 1, change
    # the receiver is one of the list the post named
    row = dict(sample["board"][1], dst=["Owner", "Audit"])
    assert WK.follows(_walked(), dict(sample, board=[sample["board"][0], row] + sample["board"][2:])) == []
    # a step whose row failed did not run; one that is waiting or asked did
    for status, ok in (("failed", False), ("ok", True), ("waiting", True), ("asked", True)):
        steps = [dict(s, status=status) if s["step"] == "setup.shape" else s for s in sample["steps"]]
        assert (WK.follows(_walked(), dict(sample, steps=steps)) == []) is ok, status
    # a step the journey names that the journey does not have
    assert WK.follows(_walked(), sample, walks=["1", "7"]) == ["J9: the walk names step 7, and the journey has no such step"]
    # an empty trace follows nothing
    empty = {"board": [], "steps": [], "events": [], "asks": []}
    got = WK.follows(_walked(), empty)
    assert len(got) == 8 and all(f.startswith("J9 step ") and "did not happen" in f for f in got)


def test_follows_checks_order_within_a_source():
    sample = json.loads(TRACE_SAMPLE.read_text(encoding="utf-8"))
    # step 2 names what happened after step 1: the walk says step 2 first, and the board and the step rows say otherwise.
    # Each bind of step 1 happened, but only before step 2's place
    got = WK.follows(_walked(), sample, walks=["2", "1"])
    assert "J9 step 1: the act (Owner, request, front, Identity) happened only before step 2 on the board, and the journey puts step 2 first" in got
    assert "J9 step 1: the act (Identity, inform, question, Owner) happened only before step 2 on the board, and the journey puts step 2 first" in got
    assert "J9 step 1: the step setup.converse happened only before step 2 on the step rows, and the journey puts step 2 first" in got
    assert "J9 step 1: the step setup.say happened only before step 2 on the step rows, and the journey puts step 2 first" in got
    assert len(got) == 4, got
    # in one source only: the department Root told of (step 2) trades places with the owner's words (step 1) on the board
    board = list(sample["board"])
    board[0], board[4] = board[4], board[0]
    got = WK.follows(_walked(), dict(sample, board=board))
    assert all("on the board" in f for f in got) and got, got
    assert not WK.follows(_walked(), dict(sample, board=board), walks=["1"]), "step 1 alone is still followed"
    # a word the owner says twice is two places: step 4 of J1 binds the second front, and step 3's question lies between them
    j = _walked()
    j["steps"][0]["binds"] = [{"kind": "act", "src": "Owner", "act": "request", "word": "front", "dst": "Identity"}]
    j["steps"][1]["binds"] = [{"kind": "act", "src": "Identity", "act": "inform", "word": "question", "dst": "Owner"}]
    j["steps"].append(dict(j["steps"][0], n="3"))                  # the owner answers: the same words again
    assert WK.follows(j, sample, walks=["1", "2", "3"]) == []
    only_one = dict(sample, board=[sample["board"][0]] + sample["board"][1:2] + sample["board"][3:])    # the second front is gone
    assert WK.follows(j, only_one, walks=["1", "2", "3"]) == ["J9 step 3: the act (Owner, request, front, Identity) happened only before step 2 on the board, and the journey puts step 2 first"]
    # the first of a step's binds is its place: a later repeat of an earlier step's bind does not matter
    again = dict(sample, board=sample["board"] + [sample["board"][0]], steps=sample["steps"] + [s for s in sample["steps"] if s["step"] == "setup.converse"])
    assert WK.follows(_walked(), again) == []
    # a step that shares its place with another is in order; and the ledger is a source of its own
    j = _walked()
    j["steps"][0]["binds"] = [{"kind": "event", "action": "ask.created"}]
    j["steps"][1]["binds"] = [{"kind": "event", "action": "run.started"}, {"kind": "event", "action": "ask.created"}]
    ledger = dict(sample, events=[{"action": "ask.created", "step": 3}, {"action": "run.started", "step": 6}])
    assert WK.follows(j, ledger) == []
    swapped = dict(sample, events=list(reversed(ledger["events"])))
    fault = ["J9 step 2: the event run.started happened only before step 1 on the ledger, and the journey puts step 1 first"]
    assert WK.follows(j, swapped) == fault, "ask.created is found, run.started lies before it"
    j["steps"][1]["binds"] = [{"kind": "event", "action": "run.started"}]
    assert WK.follows(j, swapped) == fault and WK.follows(j, ledger) == []


def test_follows_ignores_ui_api_and_person_binds_and_optional_ones():
    sample = json.loads(TRACE_SAMPLE.read_text(encoding="utf-8"))
    j = _walked()
    j["steps"][0]["binds"] += [{"kind": "ui", "symbol": "wbFoundGo"}, {"kind": "api", "method": "POST", "path": "/api/native/found"},
                               {"kind": "person", "what": "You type the name"}]
    assert WK.follows(j, sample) == [], "the node and API tests prove those; the trace cannot"
    # an optional bind may be absent
    j = _walked()
    j["steps"][1]["binds"].append({"kind": "act", "src": "Audit", "act": "inform", "word": "finding", "dst": "Identity", "optional": True})
    assert WK.follows(j, sample) == []
    # but at least one bind of a step must appear: a step that has only optional binds, none of which happened, did not happen
    j = _walked()
    j["steps"][1]["binds"] = [{"kind": "event", "action": "ask.created", "optional": True}, {"kind": "step", "id": "setup.no_such_step", "optional": True}]
    assert WK.follows(j, sample) == ["J9 step 2: none of its binds happened"]
    # a step with no bind the trace can see (a screen's, a person's) asks nothing of it
    j = _walked()
    j["steps"][1]["binds"] = [{"kind": "ui", "symbol": "wbOrgHtml"}, {"kind": "person", "what": "You read it"}]
    assert WK.follows(j, sample) == []
    j["steps"][1].pop("binds")
    assert WK.follows(j, sample) == []
    # the default is the first scenario's steps; with no scenario, every step
    j = _walked()
    j["scenarios"][0]["walks"] = ["1"]
    j["steps"][1]["binds"] = [{"kind": "step", "id": "setup.no_such_step"}]
    assert WK.follows(j, sample) == [] and len(WK.follows(j, sample, walks=["1", "2"])) == 1
    j["scenarios"] = []
    assert WK.follows(j, sample) == ["J9 step 2: the step setup.no_such_step did not happen"]


# ---- Q5: the status runner and the gate line ------------------------------------------------------------------------------
import importlib.util                                                          # noqa: E402
import subprocess                                                              # noqa: E402
import sys                                                                     # noqa: E402

_spec = importlib.util.spec_from_file_location("journey_status", HERE / "qa" / "journey_status.py")
JS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(JS)


def test_parse_junit_folds_parametrised_cases_and_marks_missing():
    sample = FIXTURES / "junit-sample.xml"
    refs = ["test_j1.py::test_j1_a_passes", "test_j1.py::test_j1_b_is_parametrised_and_passes",
            "test_j1.py::test_j1_c_runs_for_each",              # two cases, both passed: passed
            "test_j1.py::test_j1_d_has_one_bad_case",           # three cases, one failed: failed
            "test_j1.py::test_j1_e_fails", "test_j1.py::test_j1_f_is_skipped",           # skipped: it did not run
            "test_j1.py::test_j1_g_errors_in_its_fixture",      # an error is a failure
            "test_j1.py::test_j1_not_in_the_file",              # no case: missing
            "test_engine_runtime.py::TestTheFiveJourneys::test_37_a_directive_is_restated",   # classname test_engine_runtime.TestTheFiveJourneys
            "test_engine_runtime.py::TestTheFiveJourneys::test_38_another", "test_j1.py::TestPlain::test_p_one"]
    got = JS.parse_junit(sample, refs)
    assert got == {"test_j1.py::test_j1_a_passes": "passed", "test_j1.py::test_j1_b_is_parametrised_and_passes": "passed",
                   "test_j1.py::test_j1_c_runs_for_each": "passed", "test_j1.py::test_j1_d_has_one_bad_case": "failed",
                   "test_j1.py::test_j1_e_fails": "failed", "test_j1.py::test_j1_f_is_skipped": "missing",
                   "test_j1.py::test_j1_g_errors_in_its_fixture": "failed", "test_j1.py::test_j1_not_in_the_file": "missing",
                   "test_engine_runtime.py::TestTheFiveJourneys::test_37_a_directive_is_restated": "passed",
                   "test_engine_runtime.py::TestTheFiveJourneys::test_38_another": "failed",
                   "test_j1.py::TestPlain::test_p_one": "passed"}, got        # classname test_j1.TestPlain is a class of test_j1
    # the text of the file reads the same as the file; a ref is answered once however many cases it had
    assert JS.parse_junit(sample.read_text(encoding="utf-8"), refs) == got
    assert JS.parse_junit(sample, []) == {}
    assert JS.parse_junit("<testsuites><testsuite></testsuite></testsuites>", ["test_j1.py::a"]) == {"test_j1.py::a": "missing"}


def test_parse_node_lines():
    text = (FIXTURES / "node-sample.txt").read_text(encoding="utf-8")
    ref = lambda i: "js:test_website.js#" + i                                                     # noqa: E731
    got = JS.parse_node(text, [ref(i) for i in ("W1", "W10", "W10b", "W41", "W45", "W46", "W47", "W48", "W4", "W49", "W490", "W99", "M1")])
    assert {k.partition("#")[2]: v for k, v in got.items()} == {
        "W1": "passed", "W10": "passed", "W10b": "passed", "W41": "passed", "W45": "passed",
        "W46": "failed",                                    # a FAIL line
        "W47": "failed",                                    # four tests begin W47: three passed and one did not
        "W48": "passed",
        "W4": "passed",                                     # `W4 ` begins a name; W41 and W45 do not answer for it
        "W49": "missing",                                   # W490 is another id: it begins W49 but is not followed by : or a space
        "W490": "passed", "W99": "missing", "M1": "passed"}
    assert JS.parse_node("", [ref("W1")]) == {ref("W1"): "missing"}, "a file that printed nothing proves nothing"
    assert JS.parse_node("ok   W1\nFAIL W1\n", [ref("W1")]) == {ref("W1"): "failed"}, "a name that is the id alone counts"
    assert JS.split_refs([ref("W1"), "test_j1.py::a", "test_j1.py::TestK::b", ref("W2"), "test_x.py::c", ref("W1")]) == (
        {"test_j1.py": ["test_j1.py::TestK::b", "test_j1.py::a"], "test_x.py": ["test_x.py::c"]},
        {"test_website.js": [ref("W1"), ref("W2")]}), "one list per file, each ref once"


def _folder_with(folder, *journeys_):
    for j in journeys_:
        put(folder, ("functions/" if j["kind"] == "function" else "") + j["id"] + ".json", j)
    return journeys.load()


def test_check_fails_on_a_failing_row_an_unproven_row_and_a_stale_file(folder):
    from journeys import status
    j = proven()
    j["steps"][0]["tests"] = [REAL_TEST]
    j["steps"][1]["tests"] = ["test_layer_journeys.py::test_row_state_table"]
    js = _folder_with(folder, j)
    results = {t: "passed" for t in status.tests_listed(js)}
    docs = JS.documents(js, results)
    assert sorted(docs) == ["J9"] and docs["J9"]["state"] == "proven"
    # no status file yet: that is a problem, and it names the command
    assert JS.problems(js, docs, JS.disk_docs()) == ["J9 has no status file: run qa/journey_status.py --write J9"]
    JS.write(docs["J9"], journeys)
    text = (folder / "status" / "J9.json").read_text(encoding="utf-8")
    assert text.endswith("}\n") and text == json.dumps(docs["J9"], sort_keys=True, indent=1, ensure_ascii=False) + "\n" and "\n \"definitions_sha\"" in text
    assert JS.problems(js, docs, JS.disk_docs()) == [] and JS.summary(js, docs, 0) == "journeys: 3 rows, 3 proven, 0 wanted, 0 faults"
    # a listed test turned red: the row is failing, and the file no longer says what the tests give
    red = JS.documents(js, dict(results, **{REAL_TEST: "failed"}))
    got = JS.problems(js, red, JS.disk_docs())
    assert got == ["J9 step 1 is failing: " + REAL_TEST,
                   "the status file of J9 differs from what the tests give now: run qa/journey_status.py --write J9"]
    assert JS.summary(js, red, len(got)) == "journeys: 3 rows, 2 proven, 0 wanted, 2 faults"
    assert JS.problems(js, red, JS.disk_docs(), ran=False) == ["J9 step 1 is failing: " + REAL_TEST], "with no run, a file is compared by its hash only"
    # a test the run did not find is failing too
    gone = JS.documents(js, {t: "passed" for t in results if t != REAL_TEST})
    assert gone["J9"]["tests"][REAL_TEST] == "missing" and gone["J9"]["rows"]["step:1"]["state"] == "failing"
    # an unproven row (code and no test) and a fault row (no code, no backlog) in a journey that is not declared
    bare = copy.deepcopy(j)
    bare["steps"][1]["tests"] = []
    bare["edges"][0].update(code=[], binds=[], tests=[])
    bare["edges"][0].pop("backlog", None)
    js2 = _folder_with(folder, bare)
    got = JS.problems(js2, JS.documents(js2, results), JS.disk_docs())
    assert got[:2] == ["J9 step 2 is unproven: it has code and lists no test",
                       "J9 edge J9.1 is a fault: it has no code and no backlog entry, or a wanted row lists a test"]
    assert got[2] == "the status file of J9 is stale (the journey changed after it was written): run qa/journey_status.py --write J9"
    # a stale file: the journey changed by a word, the file is the old one
    changed = copy.deepcopy(j)
    changed["steps"][0]["short"] = "You say it"
    js3 = _folder_with(folder, changed)
    assert JS.problems(js3, JS.documents(js3, results), JS.disk_docs()) == \
        ["the status file of J9 is stale (the journey changed after it was written): run qa/journey_status.py --write J9"]
    assert JS.problems(js3, JS.documents(js3, results), JS.disk_docs(), ran=False)[0].startswith("the status file of J9 is stale")
    # a status file that belongs to no journey; a file that is not JSON is a document of nothing
    put(folder, "status/J7.json", docs["J9"])
    (folder / "status" / "J6.json").write_text("{", encoding="utf-8")
    got = JS.problems(js, docs, JS.disk_docs())
    assert got == ["the status file J6.json belongs to no journey: run qa/journey_status.py --write",
                   "the status file J7.json belongs to no journey: run qa/journey_status.py --write"]
    # a declared journey is not held to any of it
    put(folder, "functions/FI1.json", {"journeys": [good(id="FI1", kind="function", bound_to="identity", declared=True)]})
    js4 = journeys.load()
    live = {i: x for i, x in js4.items() if not x.get("declared")}
    assert sorted(live) == ["J9"] and JS.problems(live, docs, {"J9": docs["J9"]}) == []


def test_without_a_run_the_files_are_read_by_hash_and_the_rest_by_definition(folder):
    j = proven()
    js = _folder_with(folder, j)
    from journeys import status
    docs = JS.documents(js, {t: "passed" for t in status.tests_listed(js)})
    # no file: every row is read from the definition; rows that list tests are unknown
    got = JS.without_run(js, {})
    assert {k: r["state"] for k, r in got["J9"]["rows"].items()} == {"step:1": "unknown", "step:2": "unknown", "edge:J9.1": "unknown"}
    assert got["J9"]["definitions_sha"] == journeys.sha_of(j)
    bare = proven()
    bare["edges"][0]["tests"] = []
    assert JS.without_run({"J9": bare}, {})["J9"]["rows"]["edge:J9.1"]["state"] == "unproven", "a row that lists none is read as the definition says"
    # a file with the journey's hash is the document
    assert JS.without_run(js, {"J9": docs["J9"]}) == {"J9": docs["J9"]}
    # a file with another hash is not
    assert JS.without_run(js, {"J9": dict(docs["J9"], definitions_sha="0" * 64)})["J9"]["rows"]["step:1"]["state"] == "unknown"
    assert JS.states_of(docs) == {"J9:step:1": "proven", "J9:step:2": "proven", "J9:edge:J9.1": "proven"}


def test_static_mode_runs_without_a_test_run(folder, monkeypatch, capsys):
    def never(refs):
        raise AssertionError("a test was run: %r" % (refs,))
    monkeypatch.setattr(JS, "run_tests", never)
    assert JS.main(["--static"]) == 0
    assert capsys.readouterr().out == "journeys: 0 journeys, 0 static faults\n"
    _folder_with(folder, proven())
    assert JS.main(["--static"]) == 0
    assert capsys.readouterr().out == "journeys: 1 journeys, 0 static faults\n"
    bad = proven()
    bad["steps"][0]["code"] = ["setup_sayy"]
    _folder_with(folder, bad)
    assert JS.main(["--static"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out == ["JC-5: J9 step 1 names setup_sayy in its code, and no code defines it", "journeys: 1 journeys, 1 static faults"]
    (folder / "J9.json").write_text("{", encoding="utf-8")                 # a file that cannot be loaded is told, not raised
    assert JS.main(["--static"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("the journey file J9.json is refused: it is not JSON") and out[-1] == "journeys: 0 rows, 0 proven, 0 wanted, 1 faults"
    with pytest.raises(SystemExit):
        JS.main([])


def test_check_and_write_the_whole_lane_with_injected_results(folder, monkeypatch, capsys):
    j = proven()
    j["steps"][0]["tests"] = [REAL_TEST]
    j["steps"][1]["tests"] = ["test_layer_journeys.py::test_row_state_table"]
    decl = good(id="FI1", kind="function", bound_to="identity", declared=True)
    _folder_with(folder, j, decl)
    asked = []
    result = {"all": "passed"}
    monkeypatch.setattr(JS, "run_tests", lambda refs: asked.append(sorted(refs)) or {t: result["all"] for t in refs})
    # no file yet: the check fails, and says what to run
    assert JS.main(["--check"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out == ["J9 has no status file: run qa/journey_status.py --write J9", "journeys: 3 rows, 3 proven, 0 wanted, 1 faults"]
    assert asked == [sorted(["test_layer_journeys.py::test_the_good_journey_passes_every_case", REAL_TEST, "test_layer_journeys.py::test_row_state_table"])], \
        "the tests of the journeys that are not declared, each once"
    # --write writes the file, and what it writes is what the check then finds
    assert JS.main(["--write"]) == 0
    assert capsys.readouterr().out == "journeys: 3 rows, 3 proven, 0 wanted, 0 faults\n"
    first = (folder / "status" / "J9.json").read_bytes()
    assert not (folder / "status" / "FI1.json").exists(), "a declared journey has no status file"
    assert JS.main(["--check"]) == 0
    assert capsys.readouterr().out == "journeys: 3 rows, 3 proven, 0 wanted, 0 faults\n"
    assert JS.main(["--write", "J9"]) == 0 and (folder / "status" / "J9.json").read_bytes() == first, "the same results are the same bytes"
    capsys.readouterr()
    # --no-run: nothing is run; a fresh file passes, and a journey changed after its file was written does not
    asked.clear()
    assert JS.main(["--check", "--no-run"]) == 0 and asked == []
    assert capsys.readouterr().out == "journeys: 3 rows, 3 proven, 0 wanted, 0 faults\n"
    changed = copy.deepcopy(j)
    changed["steps"][0]["short"] = "You say it"
    put(folder, "J9.json", changed)
    assert JS.main(["--check", "--no-run"]) == 1 and asked == []
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("the status file of J9 is stale") and out[-1] == "journeys: 3 rows, 0 proven, 0 wanted, 1 faults", out
    assert JS.main(["--check"]) == 1
    assert capsys.readouterr().out.splitlines()[0].startswith("the status file of J9 is stale")
    # a test turns red: the row is failing, the lane fails, and --write records it
    put(folder, "J9.json", j)
    assert JS.main(["--check"]) == 0
    capsys.readouterr()
    result["all"] = "failed"
    assert JS.main(["--check"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "J9 step 1 is failing: " + REAL_TEST and out[-1] == "journeys: 3 rows, 0 proven, 0 wanted, 4 faults", out
    assert JS.main(["--write", "J9"]) == 1, "it records what is, and says what is wrong"
    assert json.loads((folder / "status" / "J9.json").read_text(encoding="utf-8"))["state"] == "failing"
    capsys.readouterr()
    result["all"] = "passed"
    # --write of one journey runs only its tests; of a declared journey, none; of one that is not there, an error
    asked.clear()
    assert JS.main(["--write", "J9"]) == 0 and len(asked) == 1
    assert JS.main(["--write", "FI1"]) == 0 and "FI1 is declared: it has no status to write" in capsys.readouterr().out
    assert JS.main(["--write", "J7"]) == 2 and capsys.readouterr().out == "no journey J7\n"
    # --write of all removes the file of a journey that is no more
    put(folder, "status/J7.json", json.loads((folder / "status" / "J9.json").read_text(encoding="utf-8")))
    assert JS.main(["--write"]) == 0
    assert "removed the status file of J7: it is no journey" in capsys.readouterr().out and not (folder / "status" / "J7.json").exists()


def test_run_tests_runs_each_file_once_and_reads_what_it_printed(folder, monkeypatch):
    """The real run: one process for the Python file, one for the node file, and the results as the files gave them."""
    real, calls = subprocess.run, []
    monkeypatch.setattr(JS.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or real(cmd, **kw))
    refs = ["test_layer_journeys.py::test_row_state_table", "test_layer_journeys.py::test_journey_state_rules",
            "test_layer_journeys.py::test_no_such_test", "js:test_j2view.js#J1", "js:test_j2view.js#J999"]
    got = JS.run_tests(refs)
    assert got == {"test_layer_journeys.py::test_row_state_table": "passed", "test_layer_journeys.py::test_journey_state_rules": "passed",
                   "test_layer_journeys.py::test_no_such_test": "missing", "js:test_j2view.js#J1": "passed", "js:test_j2view.js#J999": "missing"}
    assert len(calls) == 2, "one process for the Python file and one for the node file"
    py = next(c for c in calls if "pytest" in c)
    assert py[1:4] == ["-m", "pytest", "-q"] and "--junitxml" in py and "no:cacheprovider" in py
    assert py[-2:] == ["test_layer_journeys.py::test_journey_state_rules", "test_layer_journeys.py::test_row_state_table"], \
        "the ids as they are, and the one pytest cannot find is not asked for (it would stop the run)"
    assert next(c for c in calls if "pytest" not in c)[1:] == ["test_j2view.js"]
    assert JS.run_tests([]) == {}


def test_the_command_line_on_the_journeys_of_the_repository():
    """python qa/journey_status.py exits 0 on the folder the repository holds: with no journey it is the empty folder, and with
    journeys their status files are fresh (--no-run) and their static cases pass (--static)."""
    def cli(*args):
        done = subprocess.run([sys.executable, str(HERE / "qa" / "journey_status.py")] + list(args), cwd=str(HERE), capture_output=True, text=True, timeout=600)
        return done.returncode, done.stdout.strip().splitlines()
    code, out = cli("--static")
    assert (code, out[-1].startswith("journeys: ")) == (0, True), out
    code, out = cli("--check", "--no-run")
    assert code == 0 and out[-1].endswith(" 0 faults"), out
    if not journeys.load():
        code, out = cli("--check")
        assert (code, out) == (0, ["journeys: 0 rows, 0 proven, 0 wanted, 0 faults"])
    code, out = cli("--no-such-mode")
    assert code == 2


# ---- Q6: the data-only API ---------------------------------------------------------------------------------------------
import re                                                                      # noqa: E402


@pytest.fixture
def api(run, folder):
    """The website router over a bare app, on the records home of the run, and the journeys folder of the test."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import website_api
    app = FastAPI()
    app.include_router(website_api.router)
    return TestClient(app)


def test_the_list_route_and_the_one_route_answer(api, folder):
    assert api.get("/api/native/journeys").json() == {"schema_version": 1, "journeys": []}, "no journeys is an empty list, not an error"
    j = proven()
    j["steps"][0]["tests"] = [REAL_TEST]
    put(folder, "J9.json", j)
    put(folder, "functions/fi.json", {"journeys": [good(id="FI1", kind="function", bound_to="identity", declared=True)]})
    put(folder, "status/J9.json", a_status(j, state="partly", counts={"proven": 2, "partly": 1}, rows={
        "step:1": {"state": "proven", "proven_by": [REAL_TEST], "site": "none", "drift": False}, "step:2": {"state": "proven"},
        "edge:J9.1": {"state": "partly", "site": "built", "drift": True}}, drift=[{"row": "edge:J9.1", "site": "built", "state": "partly"}]))
    before = sorted(p.name for p in folder.rglob("*"))
    got = api.get("/api/native/journeys")
    assert got.status_code == 200
    assert got.json() == {"schema_version": 1, "journeys": [
        {"id": "FI1", "title": "A fixture journey", "kind": "function", "inside": None, "bound_to": "identity", "declared": True, "state": "declared",
         "stale": False, "counts": {}},
        {"id": "J9", "title": "A fixture journey", "kind": "system", "inside": None, "bound_to": None, "declared": False, "state": "partly",
         "stale": False, "counts": {"proven": 2, "partly": 1}}]}, "in id order: FI1 before J9"
    one = api.get("/api/native/journeys/J9")
    assert one.status_code == 200
    body = one.json()
    assert body["id"] == "J9" and [s["n"] for s in body["steps"]] == ["1", "2"] and body["edges"][0]["id"] == "J9.1"
    assert body["status"]["state"] == "partly" and body["status"]["stale"] is False
    assert body["status"]["rows"]["step:1"] == {"state": "proven", "proven_by": ["test_j1_4_no_fitting_template_uses_explicit_organic_route"],
                                                "failing": [], "site": "none", "drift": False}
    assert body["status"]["rows"]["edge:J9.1"] == {"state": "partly", "proven_by": [], "failing": [], "site": "built", "drift": True}
    assert set(body["status"]["rows"]) == {"step:1", "step:2", "edge:J9.1"}
    assert body["status"]["drift"] == [{"row": "edge:J9.1", "site": "built", "state": "partly"}], "the site says built, and a part is not"
    assert body["status"]["counts"] == {"proven": 2, "partly": 1}
    # a declared journey is answered too, with every row declared
    fi = api.get("/api/native/journeys/FI1").json()
    assert fi["status"]["state"] == "declared" and {r["state"] for r in fi["status"]["rows"].values()} == {"declared"}
    # a read writes nothing, and the journeys are the same for the next reader
    assert sorted(p.name for p in folder.rglob("*")) == before
    assert api.get("/api/native/journeys/J9").json() == body


def test_an_unknown_journey_is_404_with_its_code(api, folder):
    put(folder, "J9.json", proven())
    for jid in ("J99", "J8", "FI1", "S1", "U2", "FAU3"):
        got = api.get("/api/native/journeys/" + jid)
        assert (got.status_code, got.json()) == (404, {"detail": {"code": "UNKNOWN_JOURNEY"}}), jid
    assert api.get("/api/native/journeys/J9").status_code == 200


def test_a_department_ref_named_journeys_is_not_shadowed(api, folder, run):
    W, R, J, root, child, home = run
    # the router answers for the departments it always answered for
    assert api.get("/api/native/depts").status_code == 200
    assert api.get("/api/native/%s/map" % child).status_code == 200
    # and for a department whose ref is `journeys`: its own routes keep answering beneath that name
    W.create("journeys", "Journeys", "A goal", kind="website")
    for tail in ("map", "status", "health"):
        got = api.get("/api/native/journeys/" + tail)
        assert got.status_code == 200, (tail, got.status_code, got.text[:200])
    assert set(api.get("/api/native/journeys/map").json()) == set(api.get("/api/native/%s/map" % child).json()) != set(), \
        "it is a department's map, not an answer about journeys"
    assert api.get("/api/native/journeys/functions").status_code in (200, 404), "a route that exists beneath the ref answers, whatever it says"
    # the list is still the journeys, and a journey's id is still a journey's
    put(folder, "J9.json", proven())
    assert [x["id"] for x in api.get("/api/native/journeys").json()["journeys"]] == ["J9"]
    assert api.get("/api/native/journeys/J9").json()["id"] == "J9"
    # the routes are declared before every route that begins with /{ref}
    import website_api
    paths = [r.path for r in website_api.router.routes]
    first_ref = next(i for i, p in enumerate(paths) if p.startswith("/api/native/{ref}"))
    assert paths.index("/api/native/journeys") < first_ref and paths.index("/api/native/journeys/{jid:journey_id}") < first_ref


def _strings(value, path=()):
    """Every string of a document with where it is: keys and values."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield path + (k,), k
            yield from _strings(v, path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, path + (i,))
    elif isinstance(value, str):
        yield path, value


def test_no_screen_word_in_the_read_model(api, folder):
    """The read model is for a screen: no act id, no name of a file, none of the places the code and the tests live, and none of
    the words the screen does not say in what the model itself adds (the states, the site's claim, the drift) or in what an
    owner may read (a golden lead, a reword). The site's and the author's prose is theirs, passed on as it is: JC-11 holds the
    owner's words, and the journey data may say "refused" where the site does."""
    j = proven()
    j["steps"][0].update(tests=[REAL_TEST, "js:test_website.js#W45"], code=["setup_say", "website_dept.create"])
    j["steps"][0]["text"] = "{helper} asks the owner what the department is for."
    j["edges"][0]["reword"] = "Say it back, once."
    j["scenarios"] = [{"id": "J9.walk", "lane": "the life", "test": "test_layer_journey_j9.py::test_walk", "walks": ["1"], "says": "Found it and watch."}]
    j["build_rows"] = [{"id": "B1", "change": "Say it back.", "where": "engine_runtime.py, identity_file", "tests": [REAL_TEST]}]
    j["today"] = {"text": "How it runs now.", "sources": "birth.md and sutra 50599599."}
    put(folder, "J9.json", j)
    put(folder, "status/J9.json", a_status(j, state="partly", counts={"proven": 2, "partly": 1}, drift=[{"row": "edge:J9.1", "site": "built", "state": "partly"}],
                                           rows={"step:1": {"state": "proven", "proven_by": [REAL_TEST, "js:test_website.js#W45"], "site": "none"},
                                                 "step:2": {"state": "proven"}, "edge:J9.1": {"state": "partly", "site": "built", "drift": True}}))
    banned, path = re.compile(S.TEMPLATE_BANNED, re.I), re.compile(r"(\.(py|js|json|md|html)\b|::|\bjs:|/)")
    keys_gone = {"binds", "code", "tests", "site_code", "site_ids", "helper", "flag", "invariants", "where", "sources"}
    one = api.get("/api/native/journeys/J9").json()
    for url, body in (("/api/native/journeys", api.get("/api/native/journeys").json()), ("/api/native/journeys/J9", one)):
        for where, text in _strings(body):
            assert text not in S.ACTS and text not in keys_gone, (url, where, text)
            assert " " in text or not path.search(text), ("a name, not a path", url, where, text)
            assert "{helper}" not in text, (url, where, text)
    own = [t for w, t in _strings(one["status"]) if "proven_by" not in w and "failing" not in w]
    own += [t for w, t in _strings(one) if w[-1] in ("golden", "reword")]
    own += [t for w, t in _strings(api.get("/api/native/journeys").json())]
    assert own and not [t for t in own if banned.search(t)], [t for t in own if banned.search(t)]
    assert one["steps"][0]["text"] == "Root asks the owner what the department is for."
    assert one["today"] == {"text": "How it runs now."} and one["scenarios"] == [{"id": "J9.walk", "lane": "the life", "walks": ["1"], "says": "Found it and watch."}]
    assert one["build_rows"] == [{"id": "B1", "change": "Say it back."}]
    assert one["edges"][0]["reword"] == "Say it back, once." and one["edges"][0]["outcome"]["golden"] == GOLDEN
    assert one["status"]["rows"]["step:1"]["proven_by"] == ["test_j1_4_no_fitting_template_uses_explicit_organic_route", "W45"], "the test by name"
    assert not (keys_gone & {k for _, k in _strings(one)}), "none of the places the code and the tests live"
    # the states a screen reads are the words of the interface
    assert {r["state"] for r in one["status"]["rows"].values()} <= set(S.READ_STATES)
