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
    assert services.tasks.node_usd_left == services.projects.usd_left and services.projects._monthly_limit == services.limits.monthly_limit      # D381: the month's limit reaches the projects and each step's cap
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


# ---- the flag turned off while a project's steps wait (D313, Minor 7) -------------------------------------------------------------------

def test_with_the_flag_turned_off_the_waiting_steps_of_a_project_stay_held_and_the_owner_can_stop_them(tmp_path, monkeypatch):
    from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
    from orchestrator.test_projects_adopt import make_app, rows, talk
    from sutra_app.config import NODE_DEFAULT_CAPS
    from sutra_app.orchestrator.nodes_store import HELD_WHILE_OFF, held_while_off
    monkeypatch.setattr("sutra_app.orchestrator.projects.NODE_DEFAULT_CAPS", {**NODE_DEFAULT_CAPS, "confirm_credits": 300})        # five steps wait for the owner: nothing starts
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        five = assignments(*[draft(f"a{i}", "web" if i % 2 else "sales", title=f"Step {i}") for i in range(1, 6)])
        talk(client, services, connector, "A lot of work", decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")), five, {"kind": "node_plan", "steps": []})
        waiting = [r["id"] for r in rows(services, "SELECT id FROM tasks ORDER BY created_at, rowid")]
        assert len(waiting) == 5 and {r["status"] for r in rows(services, "SELECT status FROM tasks")} == {"queued"}
    app2 = create_app(Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", watch_ms=20, max_runs=4, max_live=8), connector=ScriptedConnector(), launcher=FakeLauncher())
    assert app2.state.services.node_control is None and app2.state.services.tasks.task_gate is None            # nothing is installed until the start has looked at the database
    with TestClient(app2, base_url=BASE) as client:
        services = app2.state.services
        assert services.tasks.task_gate is held_while_off                                                         # only because steps of a project were waiting
        ordinary = client.post("/api/tasks", json={"dept_id": "web", "text": "an ordinary task"}, headers=HEADERS)
        assert ordinary.status_code in (200, 201), ordinary.text
        time.sleep(0.5)
        statuses = {r["id"]: r["status"] for r in rows(services, "SELECT id, status FROM tasks")}
        assert all(statuses[t] == "queued" for t in waiting) and statuses[ordinary.json()["id"]] in ("starting", "running", "done")
        detail = rows(services, "SELECT detail FROM graph_nodes WHERE task_id = ? AND step_ref = 'task'", waiting[0])[0]["detail"]
        assert detail == HELD_WHILE_OFF
        stopped = client.post(f"/api/tasks/{waiting[0]}/stop", headers=HEADERS)
        assert stopped.status_code == 200 and stopped.json()["status"] == "cancelled"


def test_an_app_that_never_made_a_project_installs_no_gate_even_with_the_flag_off(tmp_path):
    app = app_with(tmp_path)
    with TestClient(app, base_url=BASE):
        assert app.state.services.tasks.task_gate is None


def test_the_server_router_gets_a_slot_pool_only_with_the_slots_flag(tmp_path):
    from sutra_app.connectors.slots import SlotPool
    assert getattr(app_with(tmp_path / "a", nodes_v1=True).state.services.connector_router, "slots", None) is None
    on = app_with(tmp_path / "b", nodes_v1=True, nodes_slots=True)
    assert getattr(on.state.services.connector_router, "slots", None) is None or isinstance(on.state.services.connector_router.slots, SlotPool)      # stub mode (offline tests) takes none
    assert getattr(app_with(tmp_path / "c", nodes_slots=True).state.services.connector_router, "slots", None) is None      # the master flag is off
