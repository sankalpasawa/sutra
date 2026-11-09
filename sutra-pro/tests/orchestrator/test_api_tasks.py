"""Task and run routes (ORCH-6): shapes validated against the response models, the token on POSTs, status codes and error bodies."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.api import tasks as tasks_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.models import RunRef, TaskOut
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services

TOKEN = "X-Sutra-Token"


def make_client(t: TEnv, *, wired: bool = True) -> TestClient:
    app = FastAPI()
    services = Services(settings=t.settings, version="test", db=t.db, redact=Redactor(None, environ={}))
    if wired:
        services.tasks = t.service
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(tasks_api.build_router())
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


def test_post_task_needs_the_token(client):
    error_of(client.post("/api/tasks", json={"dept_id": "web", "text": "hi"}), 401, "bad_token")
    error_of(client.post("/api/tasks", json={"dept_id": "web", "text": "hi"}, headers={TOKEN: "wrong-token-wrong-token"}), 401, "bad_token")
    error_of(client.post("/api/tasks/tsk_000000000001/stop"), 401, "bad_token")
    error_of(client.post("/api/tasks/tsk_000000000001/retry"), 401, "bad_token")


def test_post_task_creates_and_starts_it(client, auth, tenv):
    response = client.post("/api/tasks", json={"dept_id": "web", "text": "  Build the menu page  ", "settings": {"J2_OUTPUT": "prd"}}, headers=auth)
    assert response.status_code == 201, response.text
    task = TaskOut.model_validate(response.json())
    assert (task.dept_id, task.dept_name, task.title, task.status) == ("web", "Web", "Build the menu page", "starting")
    assert task.run_id and (tenv.run_dir(task.id) / "task.json").exists()
    assert tenv.row(task.id).settings == {"J2_OUTPUT": "prd"}


def test_post_task_stores_a_credential_in_its_words_and_title_replaced(client, auth, tenv):
    leak = "sk-proj-REPRO1234567890abcdefghij"
    tenv.service.redact = Redactor(None, environ={"MY_API_TOKEN": "hunter2hunter2"}, extra=[tenv.settings.token])
    body = {"dept_id": "web", "text": f"deploy with {leak} and {tenv.settings.token}", "title": f"title {leak}"}
    response = client.post("/api/tasks", json=body, headers=auth)
    assert response.status_code == 201, response.text
    row = tenv.row(response.json()["id"])
    assert row.user_text == "deploy with [redacted:openai-key] and [redacted]" and row.title == "title [redacted:openai-key]"
    stored = "\n".join(tenv.db.conn().iterdump()) + (tenv.run_dir(row.id) / "task.json").read_text()
    assert leak not in stored and tenv.settings.token not in stored


def test_post_task_title_scope_and_follows(client, auth, tenv):
    first = client.post("/api/tasks", json={"dept_id": "web", "text": "one", "title": "My title", "scope_id": "menu"}, headers=auth).json()
    assert (first["title"], first["scope_node_id"]) == ("My title", "menu")
    tenv.projector.mark_ended(first["id"], "done", "ok")
    second = client.post("/api/tasks", json={"dept_id": "web", "text": "two", "follows": first["id"]}, headers=auth).json()
    assert tenv.row(second["id"]).seed_from == first["run_id"] and second["parent_task_id"] == first["id"]


@pytest.mark.parametrize("body,status,code", [
    ({"dept_id": "web", "text": "x", "settings": {"J2_SEND_MODE": "live"}}, 422, "validation"),
    ({"dept_id": "web", "text": "x", "settings": {"J2_BUDGET": "0"}}, 422, "validation"),
    ({"dept_id": "web", "text": "x", "scope_id": "leads"}, 422, "validation"),
    ({"dept_id": "web", "text": "x", "follows": "tsk_000000000999"}, 422, "validation"),
    ({"dept_id": "web", "text": "x", "extra": 1}, 422, "validation"),
    ({"dept_id": "web", "text": ""}, 422, "validation"),
    ({"dept_id": "web"}, 422, "validation"),
    ({"dept_id": "nowhere", "text": "x"}, 404, "not_found"),
])
def test_post_task_refusals(client, auth, body, status, code):
    error_of(client.post("/api/tasks", json=body, headers=auth), status, code)


def test_list_and_get(client, auth, tenv):
    a = client.post("/api/tasks", json={"dept_id": "web", "text": "one"}, headers=auth).json()
    b = client.post("/api/tasks", json={"dept_id": "sales", "text": "two"}, headers=auth).json()
    rows = [TaskOut.model_validate(r) for r in client.get("/api/tasks").json()]
    assert [r.id for r in rows] == [b["id"], a["id"]]                                          # newest first
    assert [r["id"] for r in client.get("/api/tasks", params={"dept_id": "web"}).json()] == [a["id"]]
    assert [r["id"] for r in client.get("/api/tasks", params={"status": "starting", "limit": 1}).json()] == [b["id"]]
    assert client.get("/api/tasks", params={"status": "nonsense"}).status_code == 422
    assert client.get("/api/tasks", params={"limit": 0}).status_code == 422
    assert client.get(f"/api/tasks/{a['id']}").json()["id"] == a["id"]
    error_of(client.get("/api/tasks/tsk_000000000999"), 404, "not_found")


def test_get_run_is_a_run_ref(client, auth, tenv):
    task = client.post("/api/tasks", json={"dept_id": "web", "text": "one"}, headers=auth).json()
    ref = RunRef.model_validate(client.get(f"/api/runs/{task['run_id']}").json())
    assert (ref.task_id, ref.dept_id, ref.status, ref.dir) == (task["id"], "web", "starting", f"departments/web/runs/{task['run_id']}")
    error_of(client.get("/api/runs/j2-20990101-000000-0000"), 404, "not_found")


def test_stop_and_retry(client, auth, tenv):
    task = client.post("/api/tasks", json={"dept_id": "web", "text": "one"}, headers=auth).json()
    stopped = client.post(f"/api/tasks/{task['id']}/stop", headers=auth)
    assert stopped.status_code == 200 and (stopped.json()["status"], stopped.json()["outcome"]) == ("stopped", "stopped by you")
    error_of(client.post(f"/api/tasks/{task['id']}/stop", headers=auth), 409, "busy")
    error_of(client.post("/api/tasks/tsk_000000000999/stop", headers=auth), 404, "not_found")
    retried = client.post(f"/api/tasks/{task['id']}/retry", headers=auth)
    assert retried.status_code == 201
    new = TaskOut.model_validate(retried.json())
    assert (new.parent_task_id, new.status) == (task["id"], "starting") and new.id != task["id"]
    error_of(client.post(f"/api/tasks/{new.id}/retry", headers=auth), 409, "busy")           # it is running: nothing to retry
    error_of(client.post("/api/tasks/tsk_000000000999/retry", headers=auth), 404, "not_found")


def test_an_unwired_service_is_500_internal(tenv):
    unwired = make_client(tenv, wired=False)
    error_of(unwired.get("/api/tasks"), 500, "internal")
    error_of(unwired.post("/api/tasks", json={"dept_id": "web", "text": "x"}, headers={TOKEN: tenv.settings.token}), 500, "internal")


def test_post_routes_are_guarded_by_require_token():
    guarded = {(sorted(r.methods)[0], r.path) for r in tasks_api.router.routes
               if any(d.call.__name__ == "require_token" for d in r.dependant.dependencies) or "GET" not in r.methods}
    assert guarded == {("POST", "/api/tasks"), ("POST", "/api/tasks/{task_id}/stop"), ("POST", "/api/tasks/{task_id}/retry"),
                       ("PUT", "/api/tasks/{task_id}/choice")}
    assert all(any(d.call.__name__ == "require_token" for d in r.dependant.dependencies) for r in tasks_api.router.routes if "GET" not in r.methods)
