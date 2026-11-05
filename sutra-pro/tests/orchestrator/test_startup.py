"""The app's life (ORCH-8, orchestrator 5.1): what the lifespan creates, that a second start changes nothing, the four reconcile cases
through a real restart, the shutdown ladder for waiting teams, the plug-ins and the command line. Offline: a stub connector, a fake
launcher, and for the CLI a real child process on the stub connector."""
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from orchestrator.test_scripted_conversation import (
    HEADERS, TOKEN, ATOM, FixedClock, Scenario, SurvivingLauncher, asked, make_scenario, new_team,
)

from sutra_app import main as main_module
from sutra_app.library import node as node_module
from sutra_app.config import Settings
from sutra_app.main import GRACEFUL_SHUTDOWN_S, bind_socket, build_parser, create_app, run
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher, ev
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

REPO = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8780"


def settings_in(tmp_path: Path, **changes) -> Settings:
    return Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", watch_ms=20, **changes)


def rows(path: Path, sql: str, *args) -> list[tuple]:
    conn = sqlite3.connect(path / "data" / "db.sqlite3")
    try:
        return [tuple(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


# ============================================ the lifespan ===================================================================

def test_the_lifespan_makes_the_folders_the_database_the_root_and_the_org_chat(tmp_path):
    data = tmp_path / "fresh" / "data"
    app = create_app(Settings.load({}, data_dir=data, token=TOKEN, env_file=tmp_path / "none.env", engine="fake"), connector=ScriptedConnector())
    with TestClient(app, base_url=BASE) as client:
        c = Scenario(client, app, ScriptedConnector())
        assert (data / "db.sqlite3").is_file() and (data / "departments").is_dir() and (data / "logs").is_dir()
        assert oct(data.stat().st_mode & 0o777) == "0o700" and oct((data / "departments").stat().st_mode & 0o777) == "0o700"
        assert c.one("SELECT kind FROM org_nodes") == "root" and c.one("PRAGMA user_version") == 1
        session = client.get("/api/chats/cs_org").json()
        assert session["node_id"] == "root" and session["writable"] is True and session["kind"] == "org"
        assert [m["who"] for m in client.get("/api/chats/cs_org/messages").json()["messages"]] == ["sutra"]
        assert c.services.started and app.state.plugins == {name: True for name in main_module.PLUGINS}


def test_a_second_start_on_the_same_data_changes_nothing(tmp_path):
    def counts(c: Scenario):
        return [c.one(f"SELECT count(*) FROM {table}") for table in ("org_charts", "chart_changes", "graph_nodes", "chat_sessions", "chat_messages")]
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        first = counts(Scenario(client, app, ScriptedConnector()))
    app2, _ = make_scenario(tmp_path)
    with TestClient(app2, base_url=BASE) as client2:
        c2 = Scenario(client2, app2, ScriptedConnector())
        assert counts(c2) == first == [1, 1, 1, 1, 1] and (c2.services.swept, c2.services.refreshed) == (0, 0)
        assert c2.services.reconciled.all() == []


def test_an_empty_department_folder_without_a_row_is_swept_at_start(tmp_path):
    stray = tmp_path / "data" / "departments" / "ghost" / "runs"
    stray.mkdir(parents=True)
    kept = tmp_path / "data" / "departments" / "quiet"
    kept.mkdir(parents=True)
    (kept / "engine.json").write_text("{}")
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE):
        assert app.state.services.swept == 1 and not stray.parent.exists() and kept.exists()


def test_a_function_node_under_an_older_spec_is_refreshed_at_start(tmp_path, monkeypatch):
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        new_team(Scenario(client, app, connector))
    shipped = json.loads((REPO / "sutra_app" / "library" / "specs" / "function_specs.json").read_text())
    for spec in shipped["specs"].values():
        spec["version"] = 2
        spec["goal"] = "the goal of version two"
    newer = tmp_path / "function_specs_v2.json"
    newer.write_text(json.dumps(shipped))
    monkeypatch.setattr(node_module, "DEFAULT_SPECS_PATH", newer)                       # the app now ships a newer spec
    app2, _ = make_scenario(tmp_path)
    with TestClient(app2, base_url=BASE) as client2:
        c2 = Scenario(client2, app2, ScriptedConnector())
        fresh = c2.services.graph.get("web.priority")
        assert c2.services.refreshed == 5 and (fresh.goal, fresh.spec_version) == ("the goal of version two", 2)
        assert fresh.state == "idle" and fresh.chat_session_id                              # nothing but goal, task, context and version changed
    app3, _ = make_scenario(tmp_path)
    with TestClient(app3, base_url=BASE):
        assert app3.state.services.refreshed == 0                                         # and a third start finds nothing stale


# ============================================ reconcile through a real restart ===============================================

def crashed_folder(tmp_path: Path) -> tuple[Path, str, int]:
    """The data folder of an app that died while a run was RUNNING: a copy taken while the first app was up, so nothing was settled."""
    first = tmp_path / "first"
    script = [{"emit": ev("run.started", schema="events/1", mock=True, seed="none")}, {"hold": True}]
    app, connector = make_scenario(first, launcher=FakeLauncher({"*": script}))
    with TestClient(app, base_url=BASE) as client:
        c = Scenario(client, app, connector)
        task = new_team(c)
        c.until("the run to start", lambda: c.task_status(task) == "running")
        c.db.checkpoint()
        shutil.copytree(first, tmp_path / "crashed")
    pid = rows(tmp_path / "crashed", "SELECT pid FROM tasks WHERE id = ?", task)[0][0]
    return tmp_path / "crashed", task, pid


def restart(folder: Path, launcher: SurvivingLauncher, clock) -> tuple:
    app, connector = make_scenario(folder, launcher=launcher, clock=clock)
    return app, connector


def test_reconcile_reattach(tmp_path):
    folder, task, pid = crashed_folder(tmp_path)
    launcher = SurvivingLauncher()
    launcher.adopt(pid, "x")
    app, connector = restart(folder, launcher, FixedClock(int(time.time()) + 5))
    with TestClient(app, base_url=BASE):
        services = app.state.services
        assert services.reconciled.reattached == [task] and services.watcher.watching() == [task]
        assert services.tasks.store.row(task).status == "running"


def test_reconcile_stale_alive_with_identity(tmp_path):
    folder, task, pid = crashed_folder(tmp_path)
    launcher = SurvivingLauncher()
    app, connector = restart(folder, launcher, FixedClock(int(time.time()) + 300))
    run_dir = folder / "data" / "departments" / "web" / "runs"
    launcher.adopt(pid, next(run_dir.iterdir()))                       # the process is ours: its command line names this very run folder
    with TestClient(app, base_url=BASE):
        services = app.state.services
        assert services.reconciled.signalled == [task] and launcher.stopped == [pid]
        row = services.tasks.store.row(task)
        assert (row.status, row.outcome) == ("crashed", "the app was closed while it ran and the team stopped answering")


def test_reconcile_pid_reuse_not_signalled(tmp_path):
    folder, task, pid = crashed_folder(tmp_path)
    launcher = SurvivingLauncher()
    launcher.adopt(pid, "x")
    launcher.commands[pid] = "/usr/bin/some-other-program --run-dir /elsewhere"            # the pid now belongs to a stranger
    app, connector = restart(folder, launcher, FixedClock(int(time.time()) + 300))
    with TestClient(app, base_url=BASE):
        services = app.state.services
        assert services.reconciled.untouched == [task] and launcher.stopped == [] and launcher.alive(pid)
        assert services.tasks.store.row(task).status == "crashed"


def test_reconcile_starting_without_events(tmp_path):
    first = tmp_path / "first"
    app, connector = make_scenario(first, launcher=FakeLauncher({"*": [{"hold": True}]}))        # starts, never writes run.started
    with TestClient(app, base_url=BASE) as client:
        c = Scenario(client, app, connector)
        task = new_team(c)
        assert c.task_status(task) == "starting"
        c.db.checkpoint()
        shutil.copytree(first, tmp_path / "crashed")
    launcher = SurvivingLauncher()                                                              # the process is gone
    app2, _ = restart(tmp_path / "crashed", launcher, FixedClock(int(time.time()) + 300))
    with TestClient(app2, base_url=BASE):
        services = app2.state.services
        assert services.reconciled.crashed == [task]
        assert services.tasks.store.row(task).outcome == "the app was closed while it ran"


# ============================================ shutdown =======================================================================

def test_shutdown_stops_waiting_runs(tmp_path):
    """A team waiting for the owner is stopped like a working one: the stop line ends it, the app's own words are not needed."""
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        c = Scenario(client, app, connector)
        task = asked(c)
        run_dir = c.run_dir(task)
        assert c.task_status(task) == "waiting_user"
    assert rows(tmp_path, "SELECT status FROM tasks WHERE id = ?", task) == [("stopped",)]
    ended = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines() if '"run.ended"' in line]
    assert [e["status"] for e in ended] == ["stopped"]
    assert rows(tmp_path, "SELECT display FROM atoms WHERE id = ?", ATOM) == [("abandoned",)]          # its open atom ends with the run
    wal = tmp_path / "data" / "db.sqlite3-wal"
    assert not wal.exists() or wal.stat().st_size == 0                                                    # the WAL was checkpointed


def test_a_run_that_ignores_the_stop_line_is_killed_and_the_task_says_the_app_was_closed(tmp_path):
    stubborn = [{"emit": ev("run.started", schema="events/1", mock=True, seed="none")}, {"ignore_stop": True}, {"hold": True}]
    app, connector = make_scenario(tmp_path, launcher=FakeLauncher({"*": stubborn}, stop_grace=0.1))
    with TestClient(app, base_url=BASE) as client:
        c = Scenario(client, app, connector)
        task = new_team(c)
        c.until("the run to start", lambda: c.task_status(task) == "running")
    assert rows(tmp_path, "SELECT status, outcome FROM tasks WHERE id = ?", task) == [("stopped", "the app was closed")]      # not 'crashed'


def test_the_watchers_end_before_the_stop_ladders(tmp_path):
    """Left running they could see a process the ladder just killed and call the task crashed before it is settled as stopped."""
    app, _ = make_scenario(tmp_path)
    order = []
    with TestClient(app, base_url=BASE):
        services = app.state.services
        real_close, real_shutdown = services.watcher.close, services.tasks.shutdown

        async def close(*a, **k):
            order.append("watchers")
            return await real_close(*a, **k)

        async def shutdown(*a, **k):
            order.append("ladders")
            return await real_shutdown(*a, **k)
        services.watcher.close, services.tasks.shutdown = close, shutdown
    assert order[:2] == ["watchers", "ladders"]                    # (the task service closes them once more, harmlessly, after the ladders)


def test_shutdown_closes_the_event_streams_and_is_safe_twice(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE):
        services = app.state.services
    assert services.stopped and services.bus.closed
    import asyncio
    from sutra_app.orchestrator.wiring import stop_services
    asyncio.run(stop_services(services))                                                       # a second call does nothing and raises nothing
    assert services.problems == []


def test_one_failing_shutdown_step_does_not_stop_the_others(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE):
        services = app.state.services

        async def boom():
            raise RuntimeError("the runner would not close")
        services.runner.close = boom
    assert services.problems == ["turn runner"] and services.bus.closed


# ============================================ plug-ins, docs and the connector routes ========================================

def test_docs_are_off_and_the_openapi_description_stays(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/docs").status_code == 404 and client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 200


def test_the_connector_routes_answer_and_a_switch_reaches_the_event_stream(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        status = client.get("/api/connectors/status")
        assert status.status_code == 200 and [p["name"] for p in status.json()["providers"]] == ["stub"]
        app.state.services.connector_router._emit("connector.switch", {"session_id": "cs_x", "from": "claude", "to": "codex", "reason": "policy"})
        text = client.get("/api/events", params={"topics": "connector", "after": 0, "once": 1}).text
        assert "event: connector.mode" in text and "event: connector.switch" in text and '"to":"codex"' in text


def test_a_plugin_that_cannot_be_imported_is_skipped_and_logged(tmp_path, monkeypatch, caplog):
    real = main_module.importlib.import_module

    def fake(name, *a, **k):
        if name == "sutra_app.library.api":
            raise ImportError("gone")
        return real(name, *a, **k)
    monkeypatch.setattr(main_module.importlib, "import_module", fake)
    app, _ = make_scenario(tmp_path)
    assert app.state.plugins["sutra_app.library.api"] is False and app.state.plugins["sutra_app.ui"] is True
    assert any("sutra_app.library.api" in r.getMessage() for r in caplog.records)


def test_the_agents_decision_route_is_the_one_that_answers(tmp_path):
    """Two routers define the decision route; the agent's must come first, because only it finishes the request that waits for the yes."""
    from orchestrator.test_api_security import walk
    app, _ = make_scenario(tmp_path)
    routes = [r for r in walk(app.routes) if getattr(r, "path", "") == "/api/chart/changes/{change_id}/decision"]
    assert len(routes) == 2 and routes[0].endpoint.__module__ == "sutra_app.orchestrator.api.agent"


def test_the_library_schema_routes_are_guarded_like_every_write(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/schemas").status_code == 200
        assert client.post("/api/schemas/validate", json={"family": "x", "payload": {}}).status_code == 401


def test_the_engine_routes_and_the_pages_are_served_from_the_one_app(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/runs", params={"dept": "web"}).status_code == 404         # the engine's dept rule: no such team yet
        home = client.get("/")
        assert home.status_code == 200 and "text/html" in home.headers["content-type"]


# ============================================ health and config ==============================================================

def test_health_reports_the_version_the_schema_and_the_connectors(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        body = client.get("/api/health").json()
        assert body["ok"] is True and body["version"] == "0.1.0" and body["schema"] == 1 and set(body["connectors"]) == {"stub"}
        assert body["connectors"]["stub"]["installed"] is True


def test_health_does_not_wait_for_a_slow_connector_status(tmp_path, monkeypatch):
    from sutra_app.orchestrator.api import system
    monkeypatch.setattr(system, "STATUS_WAIT_S", 0.05)
    app, connector = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        app.state.services.connector.status = lambda: time.sleep(0.5) or {"slow": {}}
        started = time.time()
        body = client.get("/api/health").json()
        assert body["ok"] is True and body["connectors"] == {} and time.time() - started < 0.4


def test_health_says_not_ok_when_the_database_cannot_answer(tmp_path):
    app, _ = make_scenario(tmp_path)
    with TestClient(app, base_url=BASE) as client:
        def broken():
            raise sqlite3.OperationalError("disk I/O error")
        app.state.services.db.version = broken
        response = client.get("/api/health")
        assert response.status_code == 503 and response.json()["ok"] is False


def test_config_shows_the_settings_and_never_a_secret(tmp_path):
    env = tmp_path / "secrets.env"
    env.write_text("SOME_SERVICE_PASSWORD=hunter2-hunter2\n")
    settings = Settings.load({"J2_OVERRIDE_KEY": "override-key-0123456789"}, data_dir=tmp_path / "data", token=TOKEN, env_file=env,
                             engine="fake", max_runs=2, max_live=5)
    app = create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher())
    with TestClient(app, base_url=BASE) as client:
        body = client.get("/api/config").json()
        assert (body["max_runs"], body["max_live"], body["engine"]) == (2, 5, "fake")
        text = json.dumps(body)
        assert TOKEN not in text and "override-key" not in text and "hunter2" not in text and "token" not in body and "override_key" not in body


# ============================================ the command line ===============================================================

def test_help_exits_zero_and_lists_the_flags(capsys):
    with pytest.raises(SystemExit) as info:
        build_parser().parse_args(["--help"])
    assert info.value.code == 0
    text = capsys.readouterr().out
    assert all(flag in text for flag in ("--port", "--data-dir", "--offline", "--no-browser"))


def test_the_module_answers_help_offline_with_exit_zero():
    done = subprocess.run([str(REPO / "scripts" / "py"), "-m", "sutra_app", "--help"], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "--no-browser" in done.stdout


def test_a_bad_setting_is_a_message_and_exit_two(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SUTRA_MAX_RUNS", "many")
    assert run(["--data-dir", str(tmp_path / "d")]) == 2
    assert "SUTRA_MAX_RUNS" in capsys.readouterr().err


def test_an_explicit_port_that_is_taken_is_refused_and_a_scan_skips_it():
    holder = bind_socket("127.0.0.1", 0, scan=False)
    holder.listen(1)
    taken = holder.getsockname()[1]
    try:
        with pytest.raises(OSError):
            bind_socket("127.0.0.1", taken, scan=False)
        found = bind_socket("127.0.0.1", taken, scan=True, last=taken + 20)
        assert found.getsockname()[1] > taken
        found.close()
        with pytest.raises(OSError, match="no free port"):
            bind_socket("127.0.0.1", taken, scan=True, last=taken)
    finally:
        holder.close()


@pytest.mark.parametrize("argv, env, scan, port", [([], None, True, 8780), (["--port", "9123"], None, False, 9123), ([], "9124", False, 9124)])
def test_the_port_rule_default_scans_from_8780_and_an_explicit_port_is_exact(tmp_path, monkeypatch, argv, env, scan, port):
    seen = []

    def fake_bind(host, number, *, scan):
        seen.append((host, number, scan))
        raise OSError("stop here")
    monkeypatch.setattr(main_module, "bind_socket", fake_bind)
    monkeypatch.delenv("SUTRA_PORT", raising=False)
    if env:
        monkeypatch.setenv("SUTRA_PORT", env)
    assert run([*argv, "--data-dir", str(tmp_path / "d")]) == 2
    assert seen == [("127.0.0.1", port, scan)]


def test_run_binds_the_port_before_building_the_app(tmp_path, monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, config, *, services, url, open_browser):
            seen.update(url=url, opened=open_browser, port=services.settings.port)

        def run(self, sockets):
            seen["bound"] = sockets[0].getsockname()[1]
            sockets[0].close()
    monkeypatch.setattr(main_module, "AppServer", Fake)
    monkeypatch.delenv("SUTRA_PORT", raising=False)
    assert run(["--no-browser", "--offline", "--port", "0", "--data-dir", str(tmp_path / "d")]) == 0
    assert seen["opened"] is False and seen["port"] == seen["bound"] and seen["url"] == f"http://127.0.0.1:{seen['bound']}/"
    assert (tmp_path / "d" / "logs" / "server.log").is_file()


def test_a_real_server_starts_answers_health_and_stops_on_sigterm_with_a_stream_open(tmp_path):
    """The packaged app's contract (REL-2): `--no-browser --port N --data-dir D --offline`, /api/health, a clean stop on SIGTERM."""
    probe = bind_socket("127.0.0.1", 0, scan=False)
    port = probe.getsockname()[1]
    probe.close()
    env = {**os.environ, "SUTRA_TOKEN": TOKEN}
    child = subprocess.Popen([str(REPO / "scripts" / "py"), "-m", "sutra_app", "--no-browser", "--offline", "--port", str(port),
                              "--data-dir", str(tmp_path / "d")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        health = None
        for _ in range(300):
            if child.poll() is not None:
                pytest.fail("the server exited early:\n" + child.stdout.read())
            try:
                health = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2))
                break
            except OSError:
                time.sleep(0.1)
        assert health and health["ok"] is True
        stream = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=5)         # an open event stream must not hold the stop
        assert stream.readline().startswith(b"event: server.hello")
        child.send_signal(signal.SIGTERM)
        started = time.time()
        child.wait(timeout=GRACEFUL_SHUTDOWN_S + 10)
        assert time.time() - started < GRACEFUL_SHUTDOWN_S - 2           # the open stream was ended by the bus, not cancelled by the timeout
        assert TOKEN not in (tmp_path / "d" / "logs" / "server.log").read_text()
    finally:
        if child.poll() is None:
            child.kill()
        child.stdout.close()
