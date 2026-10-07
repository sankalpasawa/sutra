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
    d["done"] = "Five current highlights are filed with dated source evidence"
    d["events"] = [{"kind": "j2_ready", "route": "website"}]
    d["template_ref"] = {"id": "department/website", "version": 1}
    W.save_dept(d["ref"], d)
    app = FastAPI()
    app.include_router(j2_api.router)
    return TestClient(app)


def test_j2_api_starts_lists_activity_and_stops(client):
    before = client.get("/api/dept/dref-api/j2")
    assert before.status_code == 200
    assert before.json()["state"] == "not_started"

    started = client.post("/api/dept/dref-api/j2/start")
    assert started.status_code == 200
    assert started.json()["state"] == "ready"

    activity = client.get("/api/dept/dref-api/j2/events")
    assert activity.status_code == 200
    assert activity.json()["events"][0]["actor"] == "Owner"
    assert any(row["actor"] == "Adaptation" for row in activity.json()["events"])

    stopped = client.post("/api/dept/dref-api/j2/stop")
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"


def test_j2_api_returns_stable_not_found_error(client):
    response = client.get("/api/dept/no-such/j2")
    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "NO_DEPARTMENT"}
