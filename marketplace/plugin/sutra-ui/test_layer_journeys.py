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
