"""Chart and department routes (ORCH-5): shapes validated against the response models, the token on POSTs, status codes, error bodies."""
import pytest
from factories_org import dept_op, make_change, merge_op, move_op, rename_op
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_chart_store import Env

from sutra_app.orchestrator.api import chart as chart_api
from sutra_app.orchestrator.api import departments as departments_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.models import ChangeResult, ChartChangeOut, ChartView, DepartmentOut, RunRef
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

HEADERS_KEY = "X-Sutra-Token"


@pytest.fixture
def built(db, settings, clock, events):
    return Env(db, settings, clock, events).build()


def make_client(env, settings, *, wired=True) -> TestClient:
    app = FastAPI()
    services = Services(settings=settings, version="test", db=env.db, redact=Redactor(None, environ={}))
    if wired:
        services.chart, services.departments = env.chart, env.chart.departments
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(chart_api.build_router())
    app.include_router(departments_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(built, settings):
    return make_client(built, settings)


@pytest.fixture
def auth(settings):
    return {HEADERS_KEY: settings.token}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


def payload(env, *ops, **kw) -> dict:
    return make_change(env.head(), *ops, id=env.chart.next_change_id(), **kw).model_dump(mode="json")


# ---- reads -----------------------------------------------------------------------------------------------------------------------

def test_get_chart_is_the_chart_view(client, built):
    response = client.get("/api/chart")
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/json")
    view = ChartView.model_validate(response.json())
    assert view.version == built.head().revision and {n.id for n in view.nodes} == {n.id for n in built.head().nodes}
    assert set(response.json()["nodes"][1]) == {"id", "kind", "name", "purpose", "parent_id", "position"}


def test_the_change_log_pages_by_seq_and_limit_and_needs_no_token(client):
    rows = [ChartChangeOut.model_validate(r) for r in client.get("/api/chart/changes").json()]
    assert [r.seq for r in rows] == [1, 2, 3]
    assert [r["seq"] for r in client.get("/api/chart/changes", params={"after": 1, "limit": 1}).json()] == [2]
    assert client.get("/api/chart/changes", params={"after": 3}).json() == []
    for bad in ({"limit": 0}, {"limit": 501}, {"after": -1}, {"limit": "x"}, {"newest": "maybe"}):
        error_of(client.get("/api/chart/changes", params=bad), 422, "validation")


def test_the_change_log_can_be_asked_for_its_newest_rows_still_oldest_first(client, built, auth):
    """QA org-chat-teams: the pages asked for `limit=50` and got changes 1 to 50 of a longer log, so the newest rows (and a pending approval) never showed."""
    for name in ("Support", "Billing", "Legal", "Logistics"):
        assert client.post("/api/chart/changes", json=payload(built, dept_op("$d", name)), headers=auth).status_code == 200
    assert [r["seq"] for r in client.get("/api/chart/changes", params={"limit": 3}).json()] == [1, 2, 3]
    assert [r["seq"] for r in client.get("/api/chart/changes", params={"limit": 3, "newest": "true"}).json()] == [5, 6, 7]
    assert [r["seq"] for r in client.get("/api/chart/changes", params={"limit": 3, "newest": 1, "after": 1}).json()] == [5, 6, 7]
    assert [r["seq"] for r in client.get("/api/chart/changes", params={"limit": 50, "newest": "true"}).json()] == [1, 2, 3, 4, 5, 6, 7]
    assert [r["seq"] for r in client.get("/api/chart/changes", params={"limit": 2, "newest": "false"}).json()] == [1, 2]


def test_unwired_stores_answer_500_internal_not_a_crash(built, settings):
    error_of(make_client(built, settings, wired=False).get("/api/chart"), 500, "internal")
    error_of(make_client(built, settings, wired=False).get("/api/departments"), 500, "internal")


# ---- POST /api/chart/changes ---------------------------------------------------------------------------------------------------

def test_posting_a_change_needs_the_token(client, built):
    body = payload(built, dept_op("$s", "Support"))
    error_of(client.post("/api/chart/changes", json=body), 401, "bad_token")
    error_of(client.post("/api/chart/changes", json=body, headers={HEADERS_KEY: "wrong"}), 401, "bad_token")
    error_of(client.post("/api/chart/changes", json=body, headers={HEADERS_KEY: "x", "Origin": "http://evil.example"}), 401, "bad_token")
    assert built.one("SELECT count(*) FROM chart_changes") == 3


def test_a_posted_change_is_applied_as_the_user_and_answers_the_change_result(client, built, auth):
    body = payload(built, dept_op("$s", "Support"), reason="we need a help desk")
    body["id"] = "chg-0500"
    response = client.post("/api/chart/changes", json=body, headers=auth)
    assert response.status_code == 200
    result = ChangeResult.model_validate(response.json())
    assert (result.id, result.status, result.added, result.revision, result.ids_by_ref) == ("chg-0004", "applied", ["support"], 4, {"$s": "support"})
    row = built.chart.history(after=3)[0]
    assert (row.actor, row.reason, row.task_title, row.task_id) == ("user", "we need a help desk", "we need a help desk", "req-1")
    assert built.sql("SELECT session_id, message_id FROM chart_changes WHERE seq = 4").fetchone()[:] == ("cs_org", None)


def test_a_dry_run_changes_nothing_and_says_what_would_happen(client, built, auth):
    before = built.chart.head().sha256
    response = client.post("/api/chart/changes", json={**payload(built, dept_op("$s", "Support")), "dry_run": True}, headers=auth)
    assert response.status_code == 200 and response.json()["status"] == "applied" and response.json()["added"] == ["support"]
    assert built.chart.head().sha256 == before and built.one("SELECT count(*) FROM chart_changes") == 3
    pending = client.post("/api/chart/changes", json={**payload(built, merge_op("quotes", "leads")), "dry_run": True}, headers=auth)
    assert pending.status_code == 202 and pending.json()["status"] == "pending_approval"
    assert built.one("SELECT count(*) FROM chart_changes") == 3


def test_a_merge_answers_202_and_waits_for_the_decision(client, built, auth):
    response = client.post("/api/chart/changes", json=payload(built, merge_op("quotes", "leads")), headers=auth)
    assert response.status_code == 202
    result = ChangeResult.model_validate(response.json())
    assert (result.status, result.id, result.revision) == ("pending_approval", "chg-0004", None)
    assert [c.id for c in built.chart.pending()] == ["chg-0004"]


def test_a_payload_the_gate_refuses_is_422_validation_with_violations(client, built, auth):
    body = payload(built, dept_op("$s", "Support"))
    body["kind"] = "banana"
    error = error_of(client.post("/api/chart/changes", json=body, headers=auth), 422, "validation")
    assert error["details"]["violations"][0]["path"]
    body = payload(built, dept_op("$s", "Support"))
    body["surprise"] = 1
    error_of(client.post("/api/chart/changes", json=body, headers=auth), 422, "validation")
    error_of(client.post("/api/chart/changes", json={**payload(built, dept_op("$s", "Support")), "dry_run": "yes"}, headers=auth), 422, "validation")
    error_of(client.post("/api/chart/changes", content=b"[1]", headers={**auth, "content-type": "application/json"}), 422, "validation")


def test_a_change_that_breaks_the_chart_rules_is_422_rules_with_all_violations(client, built, auth):
    body = payload(built, move_op("web", "sales"), rename_op("ghost", name="X"))
    error = error_of(client.post("/api/chart/changes", json=body, headers=auth), 422, "rules")
    assert [v["code"] for v in error["details"]["violations"]] == ["move_not_division", "unknown_node"]
    error = error_of(client.post("/api/chart/changes", json={**body, "dry_run": True}, headers=auth), 422, "rules")
    assert len(error["details"]["violations"]) == 2
    assert built.one("SELECT count(*) FROM chart_changes") == 3


def test_a_change_planned_on_an_old_revision_is_409_stale_chart_and_logged(client, built, auth):
    old = payload(built, dept_op("$s", "Support"))
    built.apply(rename_op("web", name="Web Studio"))
    error = error_of(client.post("/api/chart/changes", json=old, headers=auth), 409, "stale_chart")
    assert error["details"]["result"]["status"] == "stale"
    assert built.chart.history(after=4)[0].status == "stale"


# ---- POST /api/chart/changes/{id}/decision -----------------------------------------------------------------------------------

def test_the_decision_route_applies_a_yes_and_a_second_answer_is_409_with_the_first_result(client, built, auth):
    pending = client.post("/api/chart/changes", json=payload(built, merge_op("quotes", "leads")), headers=auth).json()["id"]
    url = f"/api/chart/changes/{pending}/decision"
    error_of(client.post(url, json={"approve": True}), 401, "bad_token")
    yes = client.post(url, json={"approve": True}, headers=auth)
    assert yes.status_code == 200 and ChangeResult.model_validate(yes.json()).status == "applied"
    again = error_of(client.post(url, json={"approve": False}, headers=auth), 409, "already_decided")
    assert again["details"]["result"]["status"] == "applied" and again["details"]["result"]["id"] == pending


def test_the_decision_route_rejects_on_no_and_checks_its_input(client, built, auth):
    pending = client.post("/api/chart/changes", json=payload(built, merge_op("quotes", "leads")), headers=auth).json()["id"]
    for bad in ({}, {"approve": "yes"}, {"approve": True, "extra": 1}):
        error_of(client.post(f"/api/chart/changes/{pending}/decision", json=bad, headers=auth), 422, "validation")
    no = client.post(f"/api/chart/changes/{pending}/decision", json={"approve": False}, headers=auth)
    assert no.status_code == 200 and no.json()["status"] == "rejected"
    error_of(client.post("/api/chart/changes/chg-0999/decision", json={"approve": True}, headers=auth), 404, "not_found")
    error_of(client.post("/api/chart/changes/not-an-id/decision", json={"approve": True}, headers=auth), 422, "validation")


# ---- departments ---------------------------------------------------------------------------------------------------------------

def test_the_department_list_and_one_department(client, built):
    rows = [DepartmentOut.model_validate(r) for r in client.get("/api/departments").json()]
    assert [r.id for r in rows] == ["sales", "web"] and len(rows[0].functions) == 5
    one = client.get("/api/departments/web")
    assert one.status_code == 200 and DepartmentOut.model_validate(one.json()).id == "web"
    assert set(one.json()) == {"id", "name", "purpose", "node_status", "live_task_id", "session_id", "functions"}
    error_of(client.get("/api/departments/ghost"), 404, "not_found")
    error_of(client.get("/api/departments/menu"), 404, "not_found")
    error_of(client.get("/api/departments/has space"), 422, "validation")


def test_the_runs_of_a_department_are_run_refs_newest_first(client, built):
    built.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at) VALUES ('tsk_000000000001','web','A','u','done','j2-20261104-100001-aaaa',1)")
    built.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at) VALUES ('tsk_000000000002','web','B','u','done','j2-20261104-100002-aaaa',2)")
    rows = [RunRef.model_validate(r) for r in client.get("/api/departments/web/runs").json()]
    assert [r.task_id for r in rows] == ["tsk_000000000002", "tsk_000000000001"]
    assert client.get("/api/departments/sales/runs").json() == []
    error_of(client.get("/api/departments/ghost/runs"), 404, "not_found")


def test_a_secret_in_a_chart_name_is_scrubbed_from_every_answer(built, settings, auth):
    app_client = make_client(built, settings)
    services = app_client.app.state.services
    services.redact = Redactor(None, environ={}, extra=["sekret-value-1234"])
    built.apply(rename_op("web", name="Web sekret-value-1234"))
    assert "sekret-value-1234" not in app_client.get("/api/chart").text
    assert "sekret-value-1234" not in app_client.get("/api/departments").text
    assert "sekret-value-1234" not in app_client.get("/api/chart/changes").text
