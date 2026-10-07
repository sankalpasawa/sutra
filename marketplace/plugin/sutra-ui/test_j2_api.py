"""HTTP boundary tests for the department-scoped J2 contract."""
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")

    import website_dept as W
    import engine_runtime as R
    import j2_runtime as J
    import j2_api

    for module in (W, R, J, j2_api):
        importlib.reload(module)
    d, _ = W.create("dref-api", "Finance highlights", "Publish verified finance news", kind="website")
    d["goal"] = "Publish five verified finance-news highlights each morning"
    d["done"] = ""                                         # Identity's standard is not met: it asks
    d["events"] = [{"kind": "j2_ready", "route": "website"}]
    d["template_ref"] = {"id": "department/website", "version": 1}
    W.save_dept(d["ref"], d)
    app = FastAPI()
    app.include_router(j2_api.router)
    return TestClient(app)


@pytest.mark.parametrize("base", ["/api/dept", "/api/departments"])
def test_j2_api_starts_takes_the_answer_once_lists_activity_stops_and_resumes(client, base):
    """The screen's paths and the PRD's paths are the same routes."""
    url = base + "/dref-api"
    before = client.get(url + "/j2")
    assert before.status_code == 200
    assert (before.json()["state"], before.json()["enabled"]) == ("not_started", True)

    started = client.post(url + "/j2/start")
    assert started.status_code == 200
    assert started.json()["state"] == "waiting" and started.json()["open_ask"]
    assert client.post(url + "/j2/start").json() == started.json()
    ask = started.json()["open_ask"]

    assert client.post(url + "/j2/answer", json={"text": "  "}).status_code == 400
    wrong = client.post(url + "/asks/a-other/answer", json={"text": "Five highlights filed"})
    assert (wrong.status_code, wrong.json()["detail"]) == (409, {"code": "NO_OPEN_QUESTION"})
    answered = client.post(url + "/asks/" + ask + "/answer", json={"text": "Five highlights are filed with dated sources"})
    assert answered.status_code == 200 and answered.json()["state"] == "assessing"
    again = client.post(url + "/j2/answer", json={"text": "once more"})
    assert (again.status_code, again.json()["detail"]) == (409, {"code": "NO_OPEN_QUESTION"})
    assert client.get(url + "/j2").json()["done_when"] == "Five highlights are filed with dated sources"

    activity = client.get(url + "/j2/events")
    assert activity.status_code == 200
    actions = [row["action"] for row in activity.json()["events"] if row["step"]]
    assert actions == ["identity.questioned", "ask.answered"]
    cursor = activity.json()["cursor"]
    assert client.get(url + "/j2/events", params={"after": cursor}).json()["events"] == []

    stopped = client.post(url + "/j2/stop")
    assert stopped.status_code == 200 and stopped.json()["state"] == "stopped"
    resumed = client.post(url + "/j2/resume")
    assert resumed.status_code == 200 and resumed.json()["state"] == "assessing"


def test_j2_api_returns_stable_errors(client):
    for method, path in (("get", "/j2"), ("get", "/j2/events"), ("post", "/j2/start"), ("post", "/j2/stop"),
                         ("post", "/j2/resume"), ("post", "/j2/answer")):
        response = getattr(client, method)("/api/dept/no-such" + path, **({"json": {"text": "x"}} if path.endswith("answer") else {}))
        assert response.status_code == 404, path
        assert response.json()["detail"] == {"code": "NO_DEPARTMENT"}, path


def test_j2_api_refuses_start_when_the_switch_is_off_but_still_stops(client, monkeypatch):
    monkeypatch.setenv("J2_FLOW_V1", "0")
    refused = client.post("/api/dept/dref-api/j2/start")
    assert (refused.status_code, refused.json()["detail"]) == (409, {"code": "J2_FLOW_DISABLED"})
    assert client.get("/api/dept/dref-api/j2").json()["enabled"] is False
    assert client.post("/api/dept/dref-api/j2/stop").status_code == 200       # Stop never depends on the switch
