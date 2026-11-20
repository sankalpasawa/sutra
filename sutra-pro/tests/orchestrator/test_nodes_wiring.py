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
    assert services.node_control is not None and services.projects is not None and services.tasks.task_gate == services.projects.gate
    assert services.node_control.projects is services.projects and services.runner.projects is services.projects and services.tasks.node_sync == services.projects.sync_task == services.projector.node_sync
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


def test_the_project_tick_runs_with_the_app_and_a_gate_left_open_by_a_closed_app_is_refused_at_start(tmp_path):
    from sutra_app.orchestrator.db import Database
    app = app_with(tmp_path, nodes_v1=True)
    services = app.state.services
    with TestClient(app, base_url=BASE) as client:
        assert services.projects._ticker is not None and not services.projects._ticker.done()
        db = services.db
        db.conn().execute("INSERT INTO projects(id, request_id, title, status, created_at) VALUES ('prj_" + "1" * 12 + "', 'req-9', 'Left open', 'awaiting_approval', 1)")
        db.conn().execute("INSERT INTO approvals(id, project_id, tier, expires_at, created_at) VALUES ('ap_" + "1" * 12 + "', 'prj_" + "1" * 12 + "', 4, 9999999999, 1)")
    assert services.projects._ticker is None                                          # the tick ended with the app
    again = app_with(tmp_path, nodes_v1=True)                                         # the next start: reconcile_projects refuses the open gate
    with TestClient(again, base_url=BASE) as client:
        row = again.state.services.db.conn().execute("SELECT status, stop_reason FROM projects WHERE id = 'prj_" + "1" * 12 + "'").fetchone()
        assert row["status"] == "stopped" and row["stop_reason"] == "Sutra was closed before you answered"
        assert again.state.services.db.conn().execute("SELECT status FROM approvals").fetchone()["status"] == "denied"
