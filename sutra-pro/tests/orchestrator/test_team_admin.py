"""Named projects, task 3: the owner makes, renames and hides projects (teams) through `/api/teams`, with no model call (D426).

    POST   /api/teams            {name, folder?, access?}  -> 201 {team, folder, access}
    PATCH  /api/teams/{dept_id}  {name}                    -> 200 DepartmentOut
    DELETE /api/teams/{dept_id}                            -> 200 {"hidden": true}
"""
import os
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chart_store import Env
from orchestrator.test_departments import add_task

from sutra_app.connectors.workdir import WorkFolder
from sutra_app.orchestrator.api import departments as departments_api
from sutra_app.orchestrator.api import teams as teams_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.schema import SCHEMA_VERSION
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.team_admin import TeamAdmin, deleted_name, folder_name
from sutra_app.orchestrator.testing import FakeClock

HEADERS_KEY = "X-Sutra-Token"
NOV_23 = int(datetime(2026, 11, 23, 12, 0, 0).timestamp())          # local noon: the date the owner sees


@pytest.fixture
def clock():
    return FakeClock(start=NOV_23)


@pytest.fixture
def built(db, settings, clock, events):
    return Env(db, settings, clock, events).build()


@pytest.fixture
def documents(tmp_path):
    found = tmp_path / "Documents"
    found.mkdir()
    return found


@pytest.fixture
def admin(built, settings, clock, documents):
    return TeamAdmin(built.db, built.chart, built.chart.departments, settings.data_dir, clock, folders=WorkFolder(settings.data_dir), documents=documents)


@pytest.fixture
def client(built, settings, admin):
    app = FastAPI()
    services = Services(settings=settings, version="test", db=built.db, redact=Redactor(None, environ={}))
    services.chart, services.departments, services.team_admin = built.chart, built.chart.departments, admin
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(teams_api.build_router())
    app.include_router(departments_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def auth(settings):
    return {HEADERS_KEY: settings.token}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code, body
    return body["error"]


def real(path):
    return os.path.realpath(str(path))


def made(client, auth, name="Pulse", **more):
    response = client.post("/api/teams", json={"name": name, **more}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


# ---- create -------------------------------------------------------------------------------------------------------------------

def test_create_makes_a_team_with_five_agents_and_a_folder(client, auth, built, settings, documents):
    changes = built.one("SELECT count(*) FROM chart_changes")
    body = made(client, auth)
    team = body["team"]
    assert team["name"] == "Pulse" and len(team["functions"]) == 5
    assert (settings.data_dir / "departments" / team["id"]).is_dir()
    assert body["folder"] == real(documents / "Sutra Pro" / "Pulse") and (documents / "Sutra Pro" / "Pulse").is_dir()
    assert body["access"] == "edit"
    assert WorkFolder(settings.data_dir, dept_id=team["id"]).get() == body["folder"]
    assert built.one("SELECT count(*) FROM chart_changes") == changes + 1
    assert built.one("SELECT actor FROM chart_changes ORDER BY seq DESC LIMIT 1") == "user"
    assert team["id"] in [d["id"] for d in client.get("/api/departments").json()]


def test_create_needs_the_token(client, built):
    error_of(client.post("/api/teams", json={"name": "Pulse"}), 401, "bad_token")
    error_of(client.post("/api/teams", json={"name": "Pulse"}, headers={HEADERS_KEY: "wrong"}), 401, "bad_token")


@pytest.mark.parametrize("name, message", [("   ", "Give the project a name"), ("x" * 81, "Keep the project name to 80 characters")])
def test_a_blank_or_long_name_is_refused(client, auth, built, name, message):
    before = built.one("SELECT count(*) FROM departments")
    error = error_of(client.post("/api/teams", json={"name": name}, headers=auth), 422, "validation")
    assert error["message"] == message and error["details"]["field"] == "name"
    assert built.one("SELECT count(*) FROM departments") == before


def test_a_name_in_use_is_refused_ignoring_case_and_spaces(client, auth):
    made(client, auth)
    error = error_of(client.post("/api/teams", json={"name": " pulse "}, headers=auth), 409, "name_taken")
    assert error["message"] == "A project called Pulse already exists" and error["details"]["field"] == "name"
    error_of(client.post("/api/teams", json={"name": "web"}, headers=auth), 409, "name_taken")


def test_owner_names_skip_the_similar_name_check(client, auth):
    made(client, auth)
    assert made(client, auth, "Pulse app")["team"]["name"] == "Pulse app"


def test_a_chosen_folder_is_checked_and_stored(client, auth, built, settings, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    body = made(client, auth, folder=str(src), access="read")
    assert body["folder"] == real(src) and body["access"] == "read"
    assert WorkFolder(settings.data_dir, dept_id=body["team"]["id"]).stored_access() == "read"
    before = built.one("SELECT count(*) FROM departments")
    error = error_of(client.post("/api/teams", json={"name": "Other", "folder": str(tmp_path / "nope")}, headers=auth), 422, "validation")
    assert error["message"].startswith("There is no folder at") and error["details"]["field"] == "folder"
    assert built.one("SELECT count(*) FROM departments") == before


def test_default_folder_name_is_safe_on_every_os(client, auth, documents):
    for name, folder in (("Pulse: v2", "Pulse- v2"), ("CON", "Project"), ("Notes.", "Notes")):
        body = made(client, auth, name)
        assert body["team"]["name"] == name
        assert body["folder"] == real(documents / "Sutra Pro" / folder)


def test_folder_name_rules():
    free = lambda name: False                       # noqa: E731
    assert folder_name("a/b\\c", free) == "a-b-c"
    assert folder_name("  ", free) == "Project"
    assert folder_name("lpt1", free) == "Project"
    assert folder_name("Pulse", lambda name: name in ("Pulse", "Pulse 2")) == "Pulse 3"


def test_default_folder_never_reuses_an_old_one(client, auth, documents):
    old = documents / "Sutra Pro" / "Pulse"
    old.mkdir(parents=True)
    (old / "prd.md").write_text("an old project's work", encoding="utf-8")
    body = made(client, auth)
    assert body["folder"] == real(documents / "Sutra Pro" / "Pulse 2")
    assert (old / "prd.md").read_text(encoding="utf-8") == "an old project's work"


# ---- rename -------------------------------------------------------------------------------------------------------------------

def test_rename_keeps_the_id(client, auth):
    team = made(client, auth)["team"]
    response = client.patch(f"/api/teams/{team['id']}", json={"name": "Pulse pilot"}, headers=auth)
    assert response.status_code == 200, response.text
    assert (response.json()["id"], response.json()["name"]) == (team["id"], "Pulse pilot")
    error_of(client.patch(f"/api/teams/{team['id']}", json={"name": "Web"}, headers=auth), 409, "name_taken")
    error_of(client.patch(f"/api/teams/{team['id']}", json={"name": "Web"}), 401, "bad_token")


# ---- delete (hide) ------------------------------------------------------------------------------------------------------------

def test_delete_hides_and_frees_the_name(client, auth, built, settings):
    body = made(client, auth)
    team_id = body["team"]["id"]
    response = client.delete(f"/api/teams/{team_id}", headers=auth)
    assert response.status_code == 200 and response.json() == {"hidden": True}
    assert team_id not in [d["id"] for d in client.get("/api/departments").json()]
    assert built.one("SELECT name FROM org_nodes WHERE id = ?", team_id) == "Pulse (deleted 23 Nov)"
    assert (settings.data_dir / "departments" / team_id).is_dir() and os.path.isdir(body["folder"])
    again = made(client, auth)
    assert again["team"]["id"] != team_id


def test_delete_is_refused_while_the_team_works(client, auth, built):
    team_id = made(client, auth)["team"]["id"]
    add_task(built, 1, team_id, "running")
    error = error_of(client.delete(f"/api/teams/{team_id}", headers=auth), 409, "busy")
    assert error["message"] == "Pulse is working. Stop it first."
    assert team_id in [d["id"] for d in client.get("/api/departments").json()]


def test_delete_needs_the_token(client, auth):
    team_id = made(client, auth)["team"]["id"]
    error_of(client.delete(f"/api/teams/{team_id}"), 401, "bad_token")


def test_a_hidden_team_is_read_only(client, auth, built):
    team_id = made(client, auth)["team"]["id"]
    client.delete(f"/api/teams/{team_id}", headers=auth)
    row = built.chart.departments.row(team_id)
    assert row is not None and row.archived is True
    assert built.chart.departments.hidden_ids() == {team_id}
    assert client.get(f"/api/departments/{team_id}").status_code == 404


def test_deleting_twice_in_a_day_keeps_names_apart(client, auth, built):
    first = made(client, auth)["team"]["id"]
    client.delete(f"/api/teams/{first}", headers=auth)
    second = made(client, auth)["team"]["id"]
    assert client.delete(f"/api/teams/{second}", headers=auth).status_code == 200
    assert built.one("SELECT name FROM org_nodes WHERE id = ?", second) == "Pulse (deleted 23 Nov) 2"


def test_deleted_name_fits_80():
    day = datetime(2026, 11, 23).date()
    name = deleted_name("x" * 80, day)
    assert len(name) <= 80 and name.endswith("(deleted 23 Nov)")
    assert deleted_name("Pulse", day) == "Pulse (deleted 23 Nov)"


def test_migration_adds_hidden_at(built):
    assert "hidden_at" in [r[1] for r in built.sql("PRAGMA table_info(departments)")]
    assert SCHEMA_VERSION >= 9                                        # v9 added hidden_at; later migrations only add (v10: project files, D451)


def test_a_deleted_projects_page_says_so(client, auth, built):
    from sutra_app.ui.boot import dept_boot
    team_id = made(client, auth)["team"]["id"]
    client.delete(f"/api/teams/{team_id}", headers=auth)
    boot = dept_boot(built.chart.departments.row(team_id), token="t" * 24, version="test")
    assert boot.archived is True and boot.note == "This project was deleted. Its runs and files stay on disk."


# ---- the last project picked on Attention (task 8, R1.9): kept on the server, a browser's storage is per port --------------------

def test_last_pick_round_trips(client, auth, settings):
    assert client.get("/api/teams/last").json() == {"dept": ""}
    team_id = made(client, auth)["team"]["id"]
    response = client.put("/api/teams/last", json={"dept": team_id}, headers=auth)
    assert response.status_code == 200 and response.json() == {"dept": team_id}
    assert client.get("/api/teams/last").json() == {"dept": team_id}
    assert (settings.data_dir / "ui" / "last_project.json").is_file()
    assert client.put("/api/teams/last", json={"dept": ""}, headers=auth).json() == {"dept": ""}


def test_a_hidden_or_unknown_last_pick_reads_as_none(client, auth):
    team_id = made(client, auth)["team"]["id"]
    client.put("/api/teams/last", json={"dept": team_id}, headers=auth)
    client.delete(f"/api/teams/{team_id}", headers=auth)
    assert client.get("/api/teams/last").json() == {"dept": ""}
    error_of(client.put("/api/teams/last", json={"dept": "nobody"}, headers=auth), 404, "not_found")


def test_last_pick_needs_the_token(client):
    error_of(client.put("/api/teams/last", json={"dept": ""}), 401, "bad_token")


def test_a_new_project_never_shares_a_deleted_ones_empty_folder(client, auth, documents):
    first = made(client, auth, "Throwaway")
    client.delete(f"/api/teams/{first['team']['id']}", headers=auth)
    assert not any(os.scandir(first["folder"]))                         # still empty: the old project never ran
    again = made(client, auth, "Throwaway")
    assert again["folder"] == real(documents / "Sutra Pro" / "Throwaway 2")


# ---- hide is all or nothing (review: Important 5) ---------------------------------------------------------------------------------

def test_hide_marks_the_team_hidden_before_the_rename(client, auth, built, admin, monkeypatch):
    team_id = made(client, auth)["team"]["id"]
    seen = {}
    original = admin._rename

    def rename(dept_id, name):
        seen["hidden_at"] = built.one("SELECT hidden_at FROM departments WHERE id = ?", dept_id)
        return original(dept_id, name)

    monkeypatch.setattr(admin, "_rename", rename)
    admin.hide(team_id)
    assert seen["hidden_at"] is not None                  # no moment where new work could reach a team being deleted


def test_a_failed_rename_leaves_the_project_as_it_was(client, auth, built, admin, monkeypatch):
    team_id = made(client, auth)["team"]["id"]

    def broken(dept_id, name):
        raise RuntimeError("the chart could not be saved")

    monkeypatch.setattr(admin, "_rename", broken)
    with pytest.raises(RuntimeError):
        admin.hide(team_id)
    assert built.one("SELECT hidden_at FROM departments WHERE id = ?", team_id) is None
    assert built.one("SELECT name FROM org_nodes WHERE id = ?", team_id) == "Pulse"
