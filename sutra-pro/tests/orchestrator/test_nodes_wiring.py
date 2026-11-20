"""The node controls in the whole app (MAN-4): built, gated and watched only while SUTRA_NODES_V1 is on; with it off nothing of them exists and the routes are 404."""
import time

import pytest
from fastapi.testclient import TestClient
from orchestrator.test_scripted_conversation import HEADERS, TOKEN

from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

BASE = "http://127.0.0.1:8780"


def app_with(tmp_path, **flags):
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", watch_ms=20, **flags)
    return create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher())


def test_with_the_flag_off_nothing_is_built_and_the_routes_are_404(tmp_path):
    app = app_with(tmp_path)
    services = app.state.services
    assert services.node_control is None and services.tasks.task_gate is None
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/nodes/status").status_code == 404
        assert client.post("/api/nodes/kill-all", json={}, headers=HEADERS).status_code == 404
    assert not (tmp_path / "data" / "nodes").exists()


def test_with_the_flag_on_the_controls_are_built_the_gate_is_installed_and_the_routes_answer(tmp_path):
    app = app_with(tmp_path, nodes_v1=True)
    services = app.state.services
    assert services.node_control is not None and services.tasks.task_gate == services.node_control.gate
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/nodes/status").json() == {"level": "none", "kill": None, "pause": None}
        assert client.post("/api/nodes/pause-all", json={"reason": "x"}, headers=HEADERS).json() == {"affected": 0}
        assert client.get("/api/nodes/status").json()["level"] == "pause"
        assert services.node_control._watcher is not None and not services.node_control._watcher.done()
    assert services.node_control._watcher is None                                   # the watcher ended with the app


def test_a_kill_file_that_is_there_when_the_app_starts_is_acted_on_and_audited_once(tmp_path):
    (tmp_path / "data" / "nodes").mkdir(parents=True)
    (tmp_path / "data" / "nodes" / "KILL").touch()
    app = app_with(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        time.sleep(0.2)
        rows = client.get("/api/nodes/status").json()
        assert rows["level"] == "kill"
        audit = app.state.services.db.conn().execute("SELECT action, actor FROM node_audit").fetchall()
    assert [(r["action"], r["actor"]) for r in audit] == [("kill", "system")]


def test_a_kill_file_made_by_hand_while_the_app_runs_is_noticed(tmp_path):
    app = app_with(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        (tmp_path / "data" / "nodes").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "nodes" / "KILL").touch()
        deadline = time.time() + 8
        seen = []
        while time.time() < deadline and not seen:
            seen = app.state.services.db.conn().execute("SELECT action FROM node_audit").fetchall()
            time.sleep(0.1)
    assert [r["action"] for r in seen] == ["kill"]
