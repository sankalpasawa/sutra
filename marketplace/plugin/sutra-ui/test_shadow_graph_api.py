"""A5 P4.2: GET /api/shadow/graph and /api/shadow/graph/task/{mid}: 403 when the flag is off, a validated body, 404, no response_model,
no pydantic model on a streaming route, and one validator call over two polls."""
import ast
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import mission_engine as ME
import providers
import shadow_graph
import shadow_graph_api

HERE = Path(__file__).parent


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_SHADOW_HOME", str(tmp_path))
    monkeypatch.setattr(providers, "shadow_enabled", lambda settings=None: True)
    monkeypatch.setattr(shadow_graph, "dept_read", None)
    shadow_graph.clear()
    app = FastAPI()
    app.include_router(shadow_graph_api.router)
    yield TestClient(app)
    shadow_graph.clear()


def seed():
    s = ME.MissionStore()
    m = s.create("Fix the login bug", list(ME.templates())[0], target_session="sess-1")
    m["state"] = "running"
    s.save(m)
    return m["id"]


def test_403_when_the_flag_is_off(client, monkeypatch):
    monkeypatch.setattr(providers, "shadow_enabled", lambda settings=None: False)
    for url in ("/api/shadow/graph", "/api/shadow/graph/task/m-0123456789ab"):
        r = client.get(url)
        assert r.status_code == 403 and r.json()["detail"] == "the shadow flag is off"


def test_graph_body_is_the_validated_graph(client):
    mid = seed()
    r = client.get("/api/shadow/graph")
    assert r.status_code == 200
    import layer_schema
    assert layer_schema.validate("shadow.graph", r.json()) == []
    assert "task:" + mid in [n["id"] for n in r.json()["nodes"]]
    assert client.get("/api/shadow/graph?focus=" + mid).json()["focus"] == mid


def test_detail_and_404(client):
    mid = seed()
    d = client.get("/api/shadow/graph/task/" + mid)
    assert d.status_code == 200 and d.json()["task"]["id"] == mid
    import layer_schema
    assert layer_schema.validate("shadow.task_detail", d.json()) == []
    assert client.get("/api/shadow/graph/task/m-0123456789ab").status_code == 404
    assert client.get("/api/shadow/graph/task/junk").status_code == 404


def test_two_polls_in_one_tick_validate_once(client, monkeypatch):
    seed()
    client.get("/api/shadow/graph")                       # the first read may create the stores' directories
    calls = []
    real = shadow_graph._validate
    monkeypatch.setattr(shadow_graph, "_validate", lambda n, v: (calls.append(n), real(n, v))[1])
    shadow_graph.clear()
    a = client.get("/api/shadow/graph").json()
    b = client.get("/api/shadow/graph").json()
    assert a == b and calls == ["shadow.graph"], "the second poll is the memo, not a second check"


def test_no_response_model_and_no_model_on_a_stream():
    tree = ast.parse((HERE / "shadow_graph_api.py").read_text(encoding="utf-8"))
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]:
        for dec in fn.decorator_list:
            assert not [k for k in dec.keywords if k.arg == "response_model"], fn.name
    src = (HERE / "shadow_graph_api.py").read_text(encoding="utf-8")
    assert "StreamingResponse" not in src and "import app" not in src and "from app" not in src
    assert src.index("shadow_enabled") < src.index("shadow_graph.build"), "the flag is the first line of the route"
    for r in shadow_graph_api.router.routes:
        assert r.response_model is None


def test_the_app_serves_the_routes():
    import app
    paths = {getattr(r, "path", "") for r in app.app.routes}
    assert {"/api/shadow/graph", "/api/shadow/graph/task/{mid}"} <= paths
