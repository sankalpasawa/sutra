"""GET and PUT /api/engine/settings[?dept=] (work package E4, engine design 7.1 rows 31-32, S1-contracts-03, D18): the owner
edits the two engine.json files; the change applies to the NEXT run only."""
import json
import os
import stat
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine.api import ctx as ctxmod, mount
from sutra_app.engine.api.settings import apply_change, settings_file, settings_view
from sutra_app.engine.spec import EDITABLE_FIELDS, LOCKED_FIELDS, SETTINGS_SCHEMA, EngineSettings, read_settings_file

TOKEN = {"X-Sutra-Token": "fake-token-fake-token-0123"}
URL = "/api/engine/settings"


@pytest.fixture
def api(fake_services):
    svc = fake_services
    svc.add_department("web")
    svc.add_department("sales")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    glob, web = svc.data_dir / "engine.json", svc.data_dir / "departments" / "web" / "engine.json"
    return SimpleNamespace(svc=svc, data=svc.data_dir, client=TestClient(app, raise_server_exceptions=False), glob=glob, web=web)


def put(api, body, dept=None, headers=TOKEN):
    return api.client.put(URL + (f"?dept={dept}" if dept else ""), json=body, headers=headers)


def codes(got):
    return {(v["path"], v["code"]) for v in got.json()["error"]["details"]["violations"]}


# ---- GET ------------------------------------------------------------------------------------------------------------
def test_get_without_dept_shows_the_global_scope(api):
    api.glob.write_text(json.dumps({"budget": 80}))
    body = api.client.get(URL).json()
    assert set(body) == {"schema", "defaults", "global", "effective", "editable", "locked"}
    assert body["schema"] == SETTINGS_SCHEMA == "engine-settings/1"
    assert body["defaults"] == EngineSettings().model_dump() and body["global"] == {"budget": 80}
    assert body["effective"] == {**EngineSettings().model_dump(), "budget": 80}
    assert body["editable"] == list(EDITABLE_FIELDS) and body["locked"] == list(LOCKED_FIELDS)
    assert "budget" in body["editable"] and "send_mode" in body["locked"] and not set(body["editable"]) & set(body["locked"])


def test_get_with_dept_adds_the_department_file_and_layers_it_over_the_global_one(api):
    api.glob.write_text(json.dumps({"budget": 80, "fixes": 1}))
    api.web.write_text(json.dumps({"budget": 20}))
    body = api.client.get(URL + "?dept=web").json()
    assert (body["global"], body["department"]) == ({"budget": 80, "fixes": 1}, {"budget": 20})
    assert (body["effective"]["budget"], body["effective"]["fixes"]) == (20, 1)
    assert api.client.get(URL + "?dept=sales").json()["department"] == {}          # no file yet
    assert api.client.get(URL + "?dept=sales").json()["effective"]["budget"] == 80


def test_with_a_team_the_body_says_what_the_next_run_would_use_and_without_one_it_does_not(api):
    body = api.client.get(URL + "?dept=web").json()
    assert body["next_run"] == {"output": "auto"} == {"output": EngineSettings().output}, "the default: the engine picks (D129)"
    assert "next_run" not in api.client.get(URL).json(), "the global scope is no run"
    assert set(body) == {"schema", "defaults", "global", "department", "next_run", "effective", "editable", "locked"}


def test_next_run_layers_the_files_and_the_start_pages_choice_and_effective_does_not(api):
    api.glob.write_text(json.dumps({"output": "prd"}))
    assert api.client.get(URL + "?dept=web").json()["next_run"] == {"output": "prd"}
    api.web.write_text(json.dumps({"output": "project"}))
    body = api.client.get(URL + "?dept=web").json()
    assert body["next_run"] == {"output": "project"} and api.client.get(URL + "?dept=sales").json()["next_run"] == {"output": "prd"}
    ctxmod.write_page(api.data, "web", next_settings={"J2_OUTPUT": "hld"})                 # what the start page chose for the first message
    body = api.client.get(URL + "?dept=web").json()
    assert body["next_run"] == {"output": "hld"} and body["effective"]["output"] == "project", "effective is the files only"
    assert api.client.get(URL + "?dept=sales").json()["next_run"] == {"output": "prd"}, "another team's page is not read"


def test_a_reload_of_the_start_page_shows_the_choice_it_made_through_post_output(api):
    assert api.client.post("/api/output?dept=web", json={"type": "website"}, headers=TOKEN).json() == {"ok": True, "output": "website"}
    assert api.client.get(URL + "?dept=web").json()["next_run"] == {"output": "website"}
    assert api.client.post("/api/output?dept=web", json={"type": "prd"}, headers=TOKEN).status_code == 200
    assert api.client.get(URL + "?dept=web").json()["next_run"] == {"output": "prd"}
    assert api.client.get(URL + "?dept=web").json()["global"] == {} and not api.web.exists(), "the team's file is not written by a start page choice"


def test_put_with_a_team_answers_with_next_run_like_get(api):
    got = put(api, {"set": {"output": "lld"}}, "web")
    assert got.status_code == 200 and got.json()["next_run"] == {"output": "lld"} and got.json() == api.client.get(URL + "?dept=web").json()
    assert "next_run" not in put(api, {"set": {"budget": 70}}).json()


def test_get_is_read_without_a_token_and_the_server_environment_is_not_a_layer(api, monkeypatch):
    monkeypatch.setenv("J2_BUDGET", "5")
    assert api.client.get(URL).json()["effective"]["budget"] == 100


def test_unknown_department_is_404_and_a_malformed_one_is_422_in_the_envelope(api):
    for call in (lambda: api.client.get(URL + "?dept=nope"), lambda: put(api, {"set": {"budget": 5}}, "nope")):
        got = call()
        assert got.status_code == 404 and got.json()["error"]["code"] == "not_found"
    for dept in ("Web", "a", "web/..", "x y"):
        got = api.client.get(URL + "?dept=" + dept)
        assert got.status_code == 422 and got.json()["error"]["code"] == "validation", dept
    assert api.client.get(URL + "?dept=web&dept=sales").status_code == 422


def test_an_unreadable_settings_file_is_a_422_naming_it_and_put_does_not_overwrite_it(api):
    api.glob.write_text("{half")
    got = api.client.get(URL)
    assert got.status_code == 422 and "engine.json" in got.json()["error"]["details"]["violations"][0]["message"]
    assert put(api, {"set": {"budget": 5}}).status_code == 422 and api.glob.read_text() == "{half"
    api.glob.write_text(json.dumps({"budget": 0}))                  # valid JSON, invalid setting
    assert api.client.get(URL).status_code == 422
    assert put(api, {"set": {"fixes": 1}}).status_code == 422 and json.loads(api.glob.read_text()) == {"budget": 0}


# ---- PUT ------------------------------------------------------------------------------------------------------------
def test_put_writes_the_global_file_and_answers_like_get(api):
    got = put(api, {"set": {"budget": 60, "board": True, "output": "prd", "bargain_minutes": 20}})
    assert got.status_code == 200 and got.json()["global"] == {"board": True, "bargain_minutes": 20, "budget": 60, "output": "prd"}
    assert got.json()["effective"]["budget"] == 60 and got.json() == api.client.get(URL).json()
    assert read_settings_file(api.glob) == {"board": True, "bargain_minutes": 20, "budget": 60, "output": "prd"}
    assert not api.web.exists()


def test_put_with_dept_writes_that_departments_file_only(api):
    got = put(api, {"set": {"slim": False}}, "web")
    assert got.status_code == 200 and got.json()["department"] == {"slim": False} and got.json()["effective"]["slim"] is False
    assert json.loads(api.web.read_text()) == {"slim": False} and not api.glob.exists()
    assert not (api.data / "departments" / "sales" / "engine.json").exists()


def test_put_merges_into_the_file_and_unset_removes_a_field(api):
    api.glob.write_text(json.dumps({"budget": 80, "send_mode": "mock"}))          # a hand-edited locked field must survive
    put(api, {"set": {"fixes": 1}})
    got = put(api, {"set": {"budget": 70}, "unset": ["fixes", "board"]})
    assert got.json()["global"] == {"budget": 70, "send_mode": "mock"}
    assert json.loads(api.glob.read_text()) == {"budget": 70, "send_mode": "mock"}
    assert put(api, {"unset": ["budget"]}).json()["effective"]["budget"] == 100


def test_put_refuses_unknown_and_locked_fields_with_422_validation(api):
    got = put(api, {"set": {"send_mode": "live", "nonsense": 1, "chrome": "/bin/x"}, "unset": ["force_audit_fail", "nope"]})
    assert got.status_code == 422 and set(got.json()["error"]) == {"code", "message", "details"} and got.json()["error"]["code"] == "validation"
    assert codes(got) == {("set.send_mode", "locked_field"), ("set.chrome", "locked_field"), ("set.nonsense", "unknown_field"),
                          ("unset.force_audit_fail", "locked_field"), ("unset.nope", "unknown_field")}
    assert not api.glob.exists()
    for name in LOCKED_FIELDS:                                   # every locked field, one by one
        assert put(api, {"set": {name: EngineSettings().model_dump()[name]}}).status_code == 422, name
    assert not api.glob.exists()


def test_put_checks_each_value_strictly_and_writes_nothing_on_any_problem(api):
    cases = {"budget": ["50", 0, 1.5, True, None, 100001], "fixes": [2, "1", True], "board": ["yes", 1, None], "output": ["blog", 1],
             "bargain_minutes": ["x", -1, "nan"], "delay": [-0.5], "budget_cap": [0, "5"], "max_cycles": [0]}
    for field, values in cases.items():
        for value in values:
            got = put(api, {"set": {field: value}})
            assert got.status_code == 422, (field, value, got.text[:200])
            assert {path for path, _ in codes(got)} == {f"set.{field}"}, (field, value)
    assert not api.glob.exists()
    assert put(api, {"set": {"budget": 5, "fixes": 3}}).status_code == 422 and not api.glob.exists()          # one bad value blocks all


def test_put_accepts_what_the_models_own_types_allow(api):
    ok = {"budget": 42, "budget_cap": 90, "fixes": 1, "bargain_minutes": 7, "delay": 0.5, "memory": False, "output": "lld", "tap_min": 40}
    got = put(api, {"set": ok})
    assert got.status_code == 200 and got.json()["global"] == ok
    EngineSettings.layered({}, read_settings_file(api.glob), None, {})            # what the host reads validates


def test_put_body_must_be_an_object_with_only_set_and_unset(api):
    for body in ([1], "x", {"set": []}, {"set": {"budget": 5}, "extra": 1}, {"unset": "budget"}, {"unset": [5]},
                 {"set": {"budget": 5}, "unset": ["budget"]}):
        got = put(api, body)
        assert got.status_code == 422 and got.json()["error"]["code"] == "validation", body
    assert api.client.put(URL, content=b"{torn", headers={**TOKEN, "Content-Type": "application/json"}).status_code == 422
    assert not api.glob.exists()


def test_an_empty_change_writes_no_file(api):
    assert put(api, {}).status_code == 200 and put(api, {"unset": ["budget"]}).status_code == 200
    assert not api.glob.exists()
    put(api, {"set": {"budget": 9}})
    before = api.glob.stat().st_mtime_ns
    put(api, {"set": {"budget": 9}})
    assert api.glob.stat().st_mtime_ns == before


def test_put_needs_the_token_and_checks_it_before_the_department(api):
    assert api.client.put(URL, json={"set": {"budget": 5}}).status_code == 401
    assert api.client.put(URL + "?dept=nope", json={"set": {"budget": 5}}).status_code == 401
    assert put(api, {"set": {"budget": 5}}, headers={"X-Sutra-Token": "wrong"}).status_code == 401
    assert not api.glob.exists()


def test_the_file_is_written_atomically_with_mode_0600_and_leaves_no_temp_file(api):
    put(api, {"set": {"budget": 5}}, "web")
    put(api, {"set": {"budget": 6}}, "web")
    assert stat.S_IMODE(api.web.stat().st_mode) == 0o600
    assert sorted(p.name for p in api.web.parent.iterdir() if p.name.startswith(".")) == []
    api.glob.write_text("{}")
    os.chmod(api.glob, 0o644)
    put(api, {"set": {"budget": 7}})
    assert stat.S_IMODE(api.glob.stat().st_mode) == 0o600


def test_a_failed_write_keeps_the_old_file_whole(api, monkeypatch):
    put(api, {"set": {"budget": 5}})
    monkeypatch.setattr("sutra_app.engine.api.settings.os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    assert put(api, {"set": {"budget": 6}}).status_code == 500
    assert json.loads(api.glob.read_text()) == {"budget": 5}
    assert [p.name for p in api.data.iterdir() if p.name.startswith(".")] == []


def test_a_put_during_a_live_run_leaves_that_runs_settings_alone_and_changes_the_next(api):
    ref = api.svc.add_run("web", status="running")
    run_settings = api.data / ref.dir / "settings.json"
    run_settings.write_text(json.dumps(EngineSettings().model_dump()))           # what the host wrote at the run's start
    before = run_settings.read_bytes()
    put(api, {"set": {"budget": 33}}, "web")
    assert run_settings.read_bytes() == before
    layers = (read_settings_file(api.glob), read_settings_file(api.web))
    assert EngineSettings.layered({}, *layers, {}).budget == 33                   # the next run's host resolves it so


def test_an_archived_departments_settings_are_read_only(api):
    api.svc.add_department("old", archived=True)
    assert api.client.get(URL + "?dept=old").status_code == 200
    got = put(api, {"set": {"budget": 5}}, "old")
    assert got.status_code == 403 and got.json()["error"]["code"] == "read_only"


def test_helpers_pick_the_file_and_apply_changes_without_http(api):
    assert settings_file(api.data, None) == api.glob and settings_file(api.data, "web") == api.web
    apply_change(api.data, "web", {"set": {"budget": 12}})
    assert settings_view(api.data, "web")["effective"]["budget"] == 12
