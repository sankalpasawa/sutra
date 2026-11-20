"""The node routes (MAN-4, D279): 404 for everybody while SUTRA_NODES_V1 is off, the launch token on every write when it is on, closed bodies, and what each route does with the switch."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_killswitch import KILL_FILE, PAUSE_FILE, KillSwitch, NodeControl, NodeStore, seed_node  # noqa: F401
from orchestrator.test_tasks import TEnv, tenv, tenv_with  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.api import projects as nodes_api
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class, require_token
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.testing.fake_engine import ev

HEADER = "X-Sutra-Token"
BASE = "http://127.0.0.1:8780"
WRITES = [("/api/nodes/pause-all", {"reason": "lunch"}), ("/api/nodes/kill-all", {"reason": "stop"}), ("/api/nodes/resume", {}), ("/api/nodes/nd_" + "a" * 12 + "/stop", {})]


def make_client(t: TEnv, *, wired: bool = True):
    app = FastAPI()
    services = Services(settings=t.settings, version="test", db=t.db, redact=Redactor(None, environ={}))
    services.tasks = t.service
    switch = KillSwitch(t.settings.data_dir / "nodes", clock=t.clock)
    if wired:
        services.node_control = NodeControl(switch, tasks=t.service, db=t.db, store=NodeStore(t.db, ids=t.ids), clock=t.clock)
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(nodes_api.build_router())
    return TestClient(app, base_url=BASE, raise_server_exceptions=False), switch, services


def code_of(response):
    try:
        return response.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return None


@pytest.fixture
def off(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events)
    client, switch, _ = make_client(t)
    return t, client, switch


@pytest.fixture
def on(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, nodes_v1=True)
    client, switch, services = make_client(t)
    return t, client, switch, {HEADER: t.settings.token}


# ---- flag off ---------------------------------------------------------------------------------------------------------------------

def test_with_the_flag_off_every_node_route_is_404_not_found_with_or_without_a_token_and_does_nothing(off):
    t, client, switch = off
    token = {HEADER: t.settings.token}
    assert client.get("/api/nodes/status").status_code == 404 and code_of(client.get("/api/nodes/status")) == "not_found"
    for path, body in WRITES:
        for headers in ({}, token, {HEADER: "wrong"}):
            response = client.post(path, json=body, headers=headers)
            assert response.status_code == 404 and code_of(response) == "not_found", (path, headers)
    assert switch.level() == "none" and not switch.directory.exists()              # nothing was written


# ---- the token --------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,body", WRITES)
def test_a_write_without_the_token_is_401_bad_token_and_changes_nothing(on, path, body):
    t, client, switch, headers = on
    response = client.post(path, json=body)
    assert response.status_code == 401 and code_of(response) == "bad_token"
    assert client.post(path, json=body, headers={HEADER: headers[HEADER] + "x"}).status_code == 401
    assert switch.level() == "none"


def test_the_token_in_the_url_or_a_foreign_origin_does_not_count(on):
    t, client, switch, headers = on
    assert client.post("/api/nodes/kill-all", json={}, params={"token": t.settings.token, HEADER: t.settings.token}).status_code == 401
    refused = client.post("/api/nodes/kill-all", json={}, headers={**headers, "Origin": "http://evil.example"})
    assert refused.status_code == 403 and code_of(refused) == "bad_origin" and switch.level() == "none"
    assert client.post("/api/nodes/kill-all", json={}, headers={**headers, "Origin": BASE}).status_code == 200


def test_every_write_route_of_the_nodes_router_depends_on_the_token_and_reads_do_not():
    router = nodes_api.build_router()
    assert router.routes
    for route in router.routes:
        names = {d.call for d in route.dependant.dependencies}
        assert nodes_api.nodes_enabled in names
        assert (require_token in names) == (route.methods != {"GET"}), route.path


def test_the_status_needs_no_token(on):
    t, client, switch, headers = on
    assert {k: v for k, v in client.get("/api/nodes/status").json().items() if k != "settings"} == {"level": "none", "kill": None, "pause": None}


# ---- the routes -------------------------------------------------------------------------------------------------------------------

def test_pause_kill_and_resume_move_the_switch_and_report_what_they_did(on):
    t, client, switch, headers = on
    assert client.post("/api/nodes/pause-all", json={"reason": "lunch"}, headers=headers).json() == {"affected": 0}
    status = client.get("/api/nodes/status").json()
    assert status["level"] == "pause" and status["pause"]["reason"] == "lunch" and status["pause"]["by"] == "owner" and status["kill"] is None
    assert client.post("/api/nodes/kill-all", json={}, headers=headers).json() == {"affected": 0, "file_written": True}
    assert client.get("/api/nodes/status").json()["level"] == "kill" and (switch.directory / KILL_FILE).exists()
    assert client.post("/api/nodes/resume", json={}, headers=headers).json() == {"resumed": True}
    assert {k: v for k, v in client.get("/api/nodes/status").json().items() if k != "settings"} == {"level": "none", "kill": None, "pause": None}
    assert client.post("/api/nodes/resume", json={}, headers=headers).json() == {"resumed": False}
    assert [row["action"] for row in NodeStore(t.db).audit_rows()] == ["pause", "kill", "resume"]


def test_kill_all_stops_the_live_nodes_and_says_how_many(on):
    t, client, switch, headers = on
    a, b = t.new("web", "one"), t.new("sales", "two")
    t.run(t.service.start_ready())
    for task in (a, b):
        t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
        t.drain(task.id)
    node = seed_node(t, a.id, 1)
    assert client.post("/api/nodes/kill-all", json={"reason": "stop it"}, headers=headers).json() == {"affected": 1, "file_written": True}
    assert (t.status(a.id), t.status(b.id)) == ("stopped", "running")                  # b is an ordinary task
    assert client.post(f"/api/nodes/{node}/stop", json={}, headers=headers).json() == {"stopped": False}      # already over: not an error


def test_stop_one_node_and_a_404_for_a_node_that_does_not_exist(on):
    t, client, switch, headers = on
    task = t.new("web", "one")
    t.run(t.service.start_ready())
    t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
    t.drain(task.id)
    node = seed_node(t, task.id, 1)
    assert client.post(f"/api/nodes/{node}/stop", json={}, headers=headers).json() == {"stopped": True} and t.status(task.id) == "stopped"
    missing = client.post("/api/nodes/nd_" + "f" * 12 + "/stop", json={}, headers=headers)
    assert missing.status_code == 404 and code_of(missing) == "not_found"


def test_the_bodies_are_closed_and_the_reason_is_short(on):
    t, client, switch, headers = on
    for path, body in (("/api/nodes/pause-all", {"reason": "x", "extra": 1}), ("/api/nodes/kill-all", {"reason": "x" * 201}), ("/api/nodes/kill-all", {"reason": 5}),
                       ("/api/nodes/resume", {"x": 1})):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 422 and code_of(response) == "validation", (path, body)
    assert switch.level() == "none"
    assert client.post("/api/nodes/pause-all", json={}, headers=headers).status_code == 200


def test_the_routes_say_so_when_the_controls_are_not_wired(db, settings, clock, events):
    t = tenv_with(db, settings, clock, events, nodes_v1=True)
    client, _, _ = make_client(t, wired=False)
    response = client.get("/api/nodes/status")
    assert response.status_code == 500 and code_of(response) == "internal"


def test_a_secret_in_a_reason_never_reaches_a_response_or_the_audit(on):
    t, client, switch, headers = on
    secret = "sk-ABCDEFGHIJKLMNOP1234"
    client.post("/api/nodes/pause-all", json={"reason": f"my key {secret}"}, headers=headers)
    assert secret not in client.get("/api/nodes/status").text and secret not in json.dumps(NodeStore(t.db).audit_rows())


def test_kill_all_says_when_the_file_could_not_be_written_and_stops_the_nodes_anyway(on, monkeypatch):
    t, client, switch, headers = on
    task = t.new("web", "one")
    t.run(t.service.start_ready())
    t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
    t.drain(task.id)
    seed_node(t, task.id, 1)
    monkeypatch.setattr(KillSwitch, "set", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError("read-only disk")))
    assert client.post("/api/nodes/kill-all", json={}, headers=headers).json() == {"affected": 1, "file_written": False}
    assert t.status(task.id) == "stopped" and switch.level() == "kill"          # no file, but the switch is held in memory so the gate still holds (Minor 3)
