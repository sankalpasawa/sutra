"""The recurring work routes (gap package routines-limits): shapes, the token on every write, the 422 for a cadence below an hour, run now, history."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.api import recurring as recurring_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.recurring import Recurring, RecurringOut, RunOut
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.schedule import HOURLY_FLOOR
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"
WEEKDAYS = {"every": "weekdays", "hour": 9, "minute": 0}


def make_client(t: TEnv, *, wired: bool = True) -> TestClient:
    app = FastAPI()
    services = Services(settings=t.settings, version="test", db=t.db, redact=Redactor(None, environ={}))
    services.tasks = t.service
    if wired:
        services.recurring = Recurring(t.db, t.service, clock=t.clock)
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(recurring_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(tenv):
    return make_client(tenv)


@pytest.fixture
def auth(tenv):
    return {TOKEN: tenv.settings.token}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


def add(client, auth, **over):
    body = {"dept_id": "web", "text": "Write the pipeline summary", "schedule": WEEKDAYS, **over}
    response = client.post("/api/recurring", json=body, headers=auth)
    assert response.status_code == 201, response.text
    return RecurringOut.model_validate(response.json())


def test_every_write_needs_the_token_and_every_read_does_not(client, auth):
    rec = add(client, auth)
    for method, path, body in (("post", "/api/recurring", {"dept_id": "web", "text": "x", "schedule": WEEKDAYS}),
                               ("put", f"/api/recurring/{rec.id}", {"enabled": False}), ("delete", f"/api/recurring/{rec.id}", None),
                               ("post", f"/api/recurring/{rec.id}/run", None)):
        kwargs = {"json": body} if body is not None else {}
        error_of(getattr(client, method)(path, **kwargs), 401, "bad_token")
        error_of(getattr(client, method)(path, headers={TOKEN: "wrong-token-wrong-token"}, **kwargs), 401, "bad_token")
    assert client.get("/api/recurring").status_code == 200 and client.get(f"/api/recurring/{rec.id}/runs").status_code == 200


def test_create_and_list_answer_in_the_owners_words(client, auth):
    rec = add(client, auth)
    assert (rec.dept_name, rec.human, rec.enabled, rec.paused_reason, rec.last_run) == ("Web", "Every weekday at 9:00 AM (local)", True, "", None)
    listed = client.get("/api/recurring").json()
    assert [RecurringOut.model_validate(x).id for x in listed] == [rec.id]
    assert listed[0]["schedule"] == {"every": "weekdays", "hour": 9, "minute": 0, "weekday": 0} and listed[0]["next_due_at"].endswith("Z")


def test_a_credential_in_the_words_is_stored_and_answered_replaced(client, auth, tenv):
    leak = "ghp_QAFAKE0ghp1234567890abcdefghijklmn"
    made = client.post("/api/recurring", json={"dept_id": "web", "text": f"weekly: use {leak}", "schedule": WEEKDAYS}, headers=auth)
    assert made.status_code == 201 and made.json()["text"] == "weekly: use [redacted:github-token]"
    put = client.put(f"/api/recurring/{made.json()['id']}", json={"text": f"now {leak}"}, headers=auth)
    assert put.status_code == 200 and put.json()["text"] == "now [redacted:github-token]"
    assert leak not in "\n".join(tenv.db.conn().iterdump())


@pytest.mark.parametrize("every", ["minute", "30 minutes", "*/5 * * * *", "", 5])
def test_a_cadence_below_an_hour_is_a_422_that_says_why(client, auth, every):
    refused = error_of(client.post("/api/recurring", json={"dept_id": "web", "text": "x", "schedule": {"every": every}}, headers=auth), 422, "validation")
    assert refused["message"] == HOURLY_FLOOR
    assert refused["details"]["violations"][0]["path"].startswith("schedule")
    assert client.get("/api/recurring").json() == []


def test_a_free_cron_field_an_unknown_team_and_empty_words_are_refused(client, auth):
    error_of(client.post("/api/recurring", json={"dept_id": "web", "text": "x", "schedule": {"every": "day", "cron": "* * * * *"}}, headers=auth), 422, "validation")
    error_of(client.post("/api/recurring", json={"dept_id": "web", "text": "x", "schedule": {"every": "day", "hour": 25}}, headers=auth), 422, "validation")
    error_of(client.post("/api/recurring", json={"dept_id": "nowhere", "text": "x", "schedule": WEEKDAYS}, headers=auth), 404, "not_found")
    error_of(client.post("/api/recurring", json={"dept_id": "web", "text": "   ", "schedule": WEEKDAYS}, headers=auth), 422, "validation")
    error_of(client.post("/api/recurring", json={"dept_id": "web", "text": "x", "schedule": WEEKDAYS, "extra": 1}, headers=auth), 422, "validation")
    error_of(client.post("/api/recurring", json={"dept_id": "web", "text": "x"}, headers=auth), 422, "validation")


def test_put_changes_the_words_the_cadence_and_the_switch(client, auth):
    rec = add(client, auth)
    changed = client.put(f"/api/recurring/{rec.id}", json={"text": "New words", "schedule": {"every": "week", "hour": 8, "weekday": 4}}, headers=auth)
    assert changed.status_code == 200 and changed.json()["text"] == "New words" and changed.json()["human"] == "Every Friday at 8:00 AM (local)"
    paused = client.put(f"/api/recurring/{rec.id}", json={"enabled": False}, headers=auth).json()
    assert paused["enabled"] is False and paused["next_due_at"] is None and paused["paused_reason"] == ""
    error_of(client.put(f"/api/recurring/{rec.id}", json={}, headers=auth), 422, "validation")
    error_of(client.put(f"/api/recurring/{rec.id}", json={"schedule": {"every": "minute"}}, headers=auth), 422, "validation")
    error_of(client.put("/api/recurring/rec_000000000000", json={"enabled": False}, headers=auth), 404, "not_found")
    error_of(client.put("/api/recurring/not-an-id", json={"enabled": False}, headers=auth), 422, "validation")


def test_run_now_starts_a_task_and_the_history_says_manual(client, auth, tenv):
    rec = add(client, auth)
    run = client.post(f"/api/recurring/{rec.id}/run", headers=auth)
    assert run.status_code == 201, run.text
    out = RunOut.model_validate(run.json())
    assert out.trigger == "manual" and out.task_id and tenv.status(out.task_id) == "starting"        # start_ready ran as for any task
    runs = [RunOut.model_validate(x) for x in client.get(f"/api/recurring/{rec.id}/runs").json()]
    assert [r.trigger for r in runs] == ["manual"] and runs[0].result == "working"
    error_of(client.post(f"/api/recurring/{rec.id}/run", headers=auth), 409, "busy")                  # the team is working now
    assert client.get("/api/recurring").json()[0]["never_fired_on_schedule"] is True


def test_one_unreadable_schedule_leaves_the_list_a_200_and_can_still_be_removed(client, auth, tenv):
    good, bad = add(client, auth), add(client, auth, text="Another")
    tenv.sql("UPDATE recurring SET schedule_json = ? WHERE id = ?", '{"every":"month","hour":9,"minute":0,"weekday":0}', bad.id)
    listed = client.get("/api/recurring")
    assert listed.status_code == 200, listed.text
    rows = {x["id"]: RecurringOut.model_validate(x) for x in listed.json()}
    assert set(rows) == {good.id, bad.id} and rows[good.id].enabled is True
    assert rows[bad.id].enabled is False and rows[bad.id].schedule is None and rows[bad.id].paused_reason == "Paused: its schedule could not be read. Set it again."
    assert client.get(f"/api/recurring/{good.id}/runs").status_code == 200
    error_of(client.post(f"/api/recurring/{bad.id}/run", headers=auth), 422, "validation")
    assert client.delete(f"/api/recurring/{bad.id}", headers=auth).status_code == 200
    assert [x["id"] for x in client.get("/api/recurring").json()] == [good.id]


def test_run_now_under_a_used_up_limit_answers_held_not_working(client, auth, tenv, tmp_path):
    from sutra_app.orchestrator.limits import Limits
    limits = Limits(tmp_path / "limits.json", tenv.db, quotas=lambda: {}, clock=tenv.clock)
    tenv.service.start_gate = limits.gate
    limits.update(monthly_usd=1.0)
    tenv.sql("INSERT INTO usage_ledger(at, provider, purpose, usd) VALUES (?,?,?,?)", int(tenv.clock.now()) - 60, "claude", "test", 5.0)
    rec = add(client, auth)
    run = client.post(f"/api/recurring/{rec.id}/run", headers=auth)
    assert run.status_code == 201, run.text
    assert tenv.status(run.json()["task_id"]) == "queued" and run.json()["result"] == "held"
    assert client.get(f"/api/recurring/{rec.id}/runs").json()[0]["result"] == "held"
    assert client.get("/api/recurring").json()[0]["last_run"]["result"] == "held"


def test_delete_removes_it_and_a_second_delete_is_404(client, auth):
    rec = add(client, auth)
    assert client.delete(f"/api/recurring/{rec.id}", headers=auth).json() == {"deleted": rec.id}
    error_of(client.delete(f"/api/recurring/{rec.id}", headers=auth), 404, "not_found")
    assert client.get("/api/recurring").json() == []
    error_of(client.get(f"/api/recurring/{rec.id}/runs"), 404, "not_found")


def test_the_runs_route_limits_and_orders_newest_first(client, auth, tenv):
    rec = add(client, auth)
    for due in (100, 200, 300):
        tenv.sql("INSERT INTO recurring_runs(recurring_id, due_at, at, trigger, outcome, reason) VALUES (?,?,?,'schedule','skipped','the team is still working on its current task')",
                 rec.id, due, due)
    runs = client.get(f"/api/recurring/{rec.id}/runs", params={"limit": 2}).json()
    assert [r["due_at"] for r in runs] == ["1970-01-01T00:05:00Z", "1970-01-01T00:03:20Z"] and runs[0]["result"] == "skipped"
    error_of(client.get(f"/api/recurring/{rec.id}/runs", params={"limit": 0}), 422, "validation")


def test_an_unwired_scheduler_is_a_500_not_a_crash(tenv, auth):
    error_of(make_client(tenv, wired=False).get("/api/recurring"), 500, "internal")
