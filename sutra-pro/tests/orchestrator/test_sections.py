"""Sidebar sections: the store (round trip, refusals, the atomic write, a damaged file) and the two routes (GET default, PUT, refusals, the write guard).

The routes run over a `Services` with no wiring at all: the store is built from `services.settings.data_dir` on each call."""
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import tenv  # noqa: F401  (tenv is a fixture)

from sutra_app import oslayer
from sutra_app.orchestrator import sections as sections_mod
from sutra_app.orchestrator.api import sections as sections_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.sections import MAX_SECTIONS, SectionsStore, clean_doc, empty_doc
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"
DOC = {"version": 1, "sections": [
    {"id": "sec_ab12cd", "name": "Clients", "teams": ["web-development", "prd"], "collapsed": False},
    {"id": "sec_ef34gh", "name": "Internal", "teams": [], "collapsed": True},
]}


def section(i: int, **kw) -> dict:
    return {"id": f"sec_{i:06d}", "name": f"S{i}", "teams": [], "collapsed": False, **kw}


def codes(exc: AppError) -> list[tuple[str, str]]:
    return [(v["path"], v["code"]) for v in exc.details["violations"]]


# ---- the store -------------------------------------------------------------------------------------------------------------------

def test_nothing_saved_reads_as_the_empty_default_and_a_save_comes_back_as_it_was(tmp_path):
    store = SectionsStore(tmp_path)
    assert store.load() == empty_doc() == {"version": 1, "sections": []}
    assert store.save(DOC) == DOC
    assert store.path == tmp_path / "ui" / "sections.json" and json.loads(store.path.read_text(encoding="utf-8")) == DOC
    assert SectionsStore(tmp_path).load() == DOC                                    # a new store (a restart, another port) over the same folder


def test_a_name_is_trimmed_and_loses_its_control_characters_and_collapsed_defaults_to_false():
    kept = clean_doc({"version": 1, "sections": [{"id": "sec_ab12cd", "name": "  Cli\x07ents\n ", "teams": ["web"]}]})
    assert kept["sections"] == [{"id": "sec_ab12cd", "name": "Clients", "teams": ["web"], "collapsed": False}]
    assert clean_doc({"version": 1, "sections": [section(1, name="x" * 40)]})["sections"][0]["name"] == "x" * 40


@pytest.mark.parametrize("doc, expected", [
    ([], [("", "not_object")]),
    ({"version": 2, "sections": []}, [("version", "bad_version")]),
    ({"version": True, "sections": []}, [("version", "bad_version")]),
    ({"version": 1, "sections": {}}, [("sections", "not_list")]),
    ({"version": 1, "sections": [], "more": 1}, [("more", "extra")]),
    ({"version": 1, "sections": [section(1, name="   ")]}, [("sections.0.name", "empty_name")]),
    ({"version": 1, "sections": [section(1, name="\x01\x02")]}, [("sections.0.name", "empty_name")]),
    ({"version": 1, "sections": [section(1, name="x" * 41)]}, [("sections.0.name", "long_name")]),
    ({"version": 1, "sections": [section(1, id="folder1")]}, [("sections.0.id", "bad_id")]),
    ({"version": 1, "sections": [section(1), section(1)]}, [("sections.1.id", "repeat_id")]),
    ({"version": 1, "sections": [section(1, teams=["Web_Dev", "a", "ok-team"])]}, [("sections.0.teams.0", "bad_team"), ("sections.0.teams.1", "bad_team")]),
    ({"version": 1, "sections": [section(1, teams=["web"]), section(2, teams=["web"])]}, [("sections.1.teams.0", "repeat_team")]),
    ({"version": 1, "sections": [section(1, teams=["web", "web"])]}, [("sections.0.teams.1", "repeat_team")]),
    ({"version": 1, "sections": [section(1, collapsed="yes")]}, [("sections.0.collapsed", "not_bool")]),
    ({"version": 1, "sections": [section(1, colour="red")]}, [("sections.0.colour", "extra")]),
    ({"version": 1, "sections": [section(i) for i in range(MAX_SECTIONS + 1)]}, [("sections", "too_many")]),
])
def test_a_bad_document_is_refused_with_each_violation_named(tmp_path, doc, expected):
    store = SectionsStore(tmp_path)
    with pytest.raises(AppError) as caught:
        store.save(doc)
    assert caught.value.status == 422 and caught.value.code == "validation" and codes(caught.value) == expected
    assert not store.path.exists()                                                  # nothing was written


def test_thirty_sections_and_an_unknown_but_valid_team_are_kept(tmp_path):
    doc = {"version": 1, "sections": [section(i) for i in range(MAX_SECTIONS - 1)] + [section(99, teams=["not-made-yet"])]}
    assert SectionsStore(tmp_path).save(doc)["sections"][-1]["teams"] == ["not-made-yet"]


def test_the_write_goes_through_a_temp_file_in_the_same_folder_and_a_failed_swap_keeps_the_old_file(tmp_path, monkeypatch):
    store = SectionsStore(tmp_path)
    store.save(DOC)
    swaps = []
    real = oslayer.replace

    def spy(src, dst):
        swaps.append((str(src), str(dst)))
        real(src, dst)
    monkeypatch.setattr(sections_mod.oslayer, "replace", spy)
    store.save({"version": 1, "sections": []})
    (src, dst), = swaps
    assert dst == str(store.path) and src != dst and src.endswith(".tmp") and str(store.path.parent) in src

    def broken(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(sections_mod.oslayer, "replace", broken)
    with pytest.raises(OSError):
        store.save(DOC)
    assert store.load() == empty_doc()                                              # the last complete file, not half of the new one
    assert [p.name for p in store.path.parent.iterdir()] == ["sections.json"]       # no temp file is left behind


@pytest.mark.parametrize("text", ["{not json", "[]", '{"version": 1, "sections": [{"id": "x"}]}', ""])
def test_a_damaged_file_reads_as_the_empty_default_with_a_warning_and_never_crashes(tmp_path, caplog, text):
    store = SectionsStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=sections_mod.__name__):
        assert store.load() == empty_doc()
    assert "damaged" in caplog.text
    assert store.save(DOC) == DOC and store.load() == DOC                           # the next save heals it


# ---- the routes ------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tenv):  # noqa: F811
    app = FastAPI()
    app.state.services = Services(settings=tenv.settings, version="test", db=tenv.db, redact=Redactor(None, environ={}), clock=tenv.clock)
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(sections_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def auth(tenv):  # noqa: F811
    return {TOKEN: tenv.settings.token}


def test_get_answers_the_empty_default_before_anything_is_saved(client):
    got = client.get("/api/sections")
    assert (got.status_code, got.json()) == (200, {"version": 1, "sections": []})


def test_a_valid_put_is_kept_and_read_back(client, auth, tenv):  # noqa: F811
    done = client.put("/api/sections", json=DOC, headers=auth)
    assert (done.status_code, done.json()) == (200, DOC)
    assert client.get("/api/sections").json() == DOC
    assert json.loads((tenv.settings.data_dir / "ui" / "sections.json").read_text(encoding="utf-8")) == DOC


def test_a_bad_put_is_a_422_in_the_error_envelope_and_changes_nothing(client, auth):
    client.put("/api/sections", json=DOC, headers=auth)
    bad = {"version": 1, "sections": [section(1, teams=["web"]), section(2, teams=["web"])]}
    refused = client.put("/api/sections", json=bad, headers=auth)
    error = refused.json()["error"]
    assert refused.status_code == 422 and error["code"] == "validation" and error["message"] == "The sections were refused"
    assert error["details"]["violations"][0]["path"] == "sections.1.teams.0" and "one section only" in error["details"]["violations"][0]["message"]
    for body in ("not json", None):
        assert client.put("/api/sections", content=body or b"", headers={**auth, "Content-Type": "application/json"}).status_code == 422
    assert client.get("/api/sections").json() == DOC


def test_a_put_without_the_token_or_from_another_origin_is_refused_and_changes_nothing(client, auth):
    assert client.put("/api/sections", json=DOC).status_code == 401
    assert client.put("/api/sections", json=DOC, headers={TOKEN: "wrong-token-wrong-token"}).status_code == 401
    assert client.put("/api/sections", json=DOC, headers={**auth, "Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/sections").json() == empty_doc()
