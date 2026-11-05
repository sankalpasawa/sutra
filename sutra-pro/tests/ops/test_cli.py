"""The operator commands and the server's start-up path (GAP-OPS-1): doctor, status, stop, config, open, the dispatcher, the lock in `run`."""
import http.server
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from sutra_app import main as main_module
from sutra_app.main import bind_socket, run
from sutra_app.ops import browser, cli, doctor
from sutra_app.ops.lock import InstanceLock, is_locked, read_holder

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_env_and_logging(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith(("SUTRA_", "J2_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("SUTRA_ENV_FILE", str(tmp_path / "x.env"))
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for handler in [h for h in root.handlers if h not in before]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)


def call(capsys, *argv):
    """Run one command in-process -> (exit code, stdout, stderr)."""
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def data_args(tmp_path):
    return ["--data-dir", str(tmp_path / "d")]


def free_port():
    probe = bind_socket("127.0.0.1", 0, scan=False)
    port = probe.getsockname()[1]
    probe.close()
    return port


class HealthServer:
    """A tiny stand-in for /api/health on a free port."""

    def __init__(self, body):
        body_bytes = json.dumps(body).encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/health":
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body_bytes)))
                    self.end_headers()
                    self.wfile.write(body_bytes)
                else:
                    self.send_error(404)

            def log_message(self, *a):
                pass
        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def spawn_holder(data_dir, on_term):
    """A child process that holds the instance lock; `on_term` is 'exit' (release and leave) or 'ignore'."""
    handler = "lambda *a: (l.release(), sys.exit(0))" if on_term == "exit" else "signal.SIG_IGN"
    code = ("import signal, sys, time; from sutra_app.ops.lock import InstanceLock; l = InstanceLock(sys.argv[1], version='7.7'); "
            f"assert l.acquire(); l.update(8798); signal.signal(signal.SIGTERM, {handler}); print('held', flush=True); time.sleep(40)")
    child = subprocess.Popen([str(REPO / "scripts" / "py"), "-c", code, str(data_dir)], stdout=subprocess.PIPE, text=True)
    assert child.stdout.readline().strip() == "held"
    return child


def reap(child):
    if child.poll() is None:
        child.kill()
    child.wait(timeout=10)
    child.stdout.close()


# ---- doctor ---------------------------------------------------------------------------------------------------------------------

def test_doctor_prints_json_with_fourteen_checks_and_exits_zero(tmp_path, capsys):
    code, out, _ = call(capsys, "doctor", "--offline", "--json", *data_args(tmp_path))
    doc = json.loads(out)
    assert code == 0 and doc["ok"] is True and [c["id"] for c in doc["checks"]] == list(doctor.CHECK_IDS)


def test_doctor_exits_one_when_a_check_fails_and_prints_the_hint(tmp_path, capsys):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "engine.json").write_text('{"budget": 0}')
    code, out, _ = call(capsys, "doctor", "--offline", *data_args(tmp_path))
    assert code == 1 and "[FAIL] Locked settings" in out and "-> fix:" in out


def test_doctor_is_offline_when_the_settings_say_so(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("SUTRA_OFFLINE", "1")
    code, out, _ = call(capsys, "doctor", "--json", *data_args(tmp_path))
    assert code == 0 and sum(c["status"] == "skip" for c in json.loads(out)["checks"]) == 5


def test_a_bad_setting_is_exit_two_and_a_bad_command_or_flag_is_a_usage_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("SUTRA_MAX_RUNS", "many")
    code, _, err = call(capsys, "doctor", "--offline", *data_args(tmp_path))
    assert code == 2 and "SUTRA_MAX_RUNS" in err
    for argv in (["frobnicate"], ["doctor", "--nope"], ["config"], ["config", "set", "budget"]):
        with pytest.raises(SystemExit) as stop:
            cli.main(argv)
        assert stop.value.code == 2
    with pytest.raises(SystemExit) as stop:
        cli.main(["doctor", "--help"])
    assert stop.value.code == 0


# ---- status -----------------------------------------------------------------------------------------------------------------------

def test_status_of_a_folder_nobody_serves_is_exit_one(tmp_path, capsys):
    code, out, _ = call(capsys, "status", *data_args(tmp_path))
    assert code == 1 and "not running" in out
    code, out, _ = call(capsys, "status", "--json", *data_args(tmp_path))
    assert code == 1 and json.loads(out)["running"] is False


def test_status_of_a_running_server_reports_where_who_and_its_health(tmp_path, capsys):
    health = HealthServer({"ok": True, "schema": 1, "connectors": {"claude": {"installed": True, "signed_in": True},
                                                                       "codex": {"installed": False, "signed_in": None}}})
    held = InstanceLock(tmp_path / "d", version="3.2.1")
    held.acquire()
    held.update(health.port)
    try:
        code, out, _ = call(capsys, "status", *data_args(tmp_path))
        assert code == 0 and f"running on http://127.0.0.1:{health.port}/" in out and f"pid {os.getpid()}" in out and "version 3.2.1" in out
        assert "health: ok, schema 1" in out and "claude: installed, signed in" in out and "codex: missing" in out
        code, out, _ = call(capsys, "status", "--json", *data_args(tmp_path))
        doc = json.loads(out)
        assert code == 0 and doc["running"] and doc["pid"] == os.getpid() and doc["health"]["schema"] == 1 and doc["uptime_s"] >= 0
    finally:
        held.release()
        health.close()


def test_status_says_so_when_the_server_does_not_answer_or_has_no_port_yet(tmp_path, capsys):
    held = InstanceLock(tmp_path / "d")
    held.acquire()
    try:
        code, out, _ = call(capsys, "status", *data_args(tmp_path))
        assert code == 0 and "starting" in out                                # lock held, port not recorded yet
        held.update(free_port())                                              # nothing listens there
        code, out, _ = call(capsys, "status", *data_args(tmp_path))
        assert code == 1 and "did not answer" in out
    finally:
        held.release()


def test_status_is_a_problem_when_health_says_not_ok(tmp_path, capsys):
    health = HealthServer({"ok": False, "schema": None, "connectors": {}})
    held = InstanceLock(tmp_path / "d")
    held.acquire()
    held.update(health.port)
    try:
        code, out, _ = call(capsys, "status", *data_args(tmp_path))
        assert code == 1 and "NOT ok" in out
    finally:
        held.release()
        health.close()


# ---- stop -------------------------------------------------------------------------------------------------------------------------

def test_stop_when_nothing_runs_is_fine(tmp_path, capsys):
    code, out, _ = call(capsys, "stop", *data_args(tmp_path))
    assert code == 0 and "not running" in out
    code, out, _ = call(capsys, "stop", "--json", *data_args(tmp_path))
    assert json.loads(out) == {"was_running": False, "stopped": True, "pid": None}


def test_stop_sends_sigterm_and_waits_for_the_lock_to_free(tmp_path, capsys):
    child = spawn_holder(tmp_path / "d", "exit")
    try:
        code, out, _ = call(capsys, "stop", *data_args(tmp_path))
        assert code == 0 and f"pid {child.pid}" in out and "Stopped." in out
        assert child.wait(timeout=10) == 0 and not is_locked(tmp_path / "d")
    finally:
        reap(child)


def test_stop_never_kills_a_server_that_is_slow_to_end(tmp_path, capsys):
    child = spawn_holder(tmp_path / "d", "ignore")
    try:
        started = time.monotonic()
        code, out, _ = call(capsys, "stop", "--wait", "0.6", *data_args(tmp_path))
        assert code == 1 and "NOT being killed" in out and f"pid {child.pid}" in out
        assert 0.5 < time.monotonic() - started < 5
        assert child.poll() is None and is_locked(tmp_path / "d")             # still alive, still locked
        code, out, _ = call(capsys, "stop", "--wait", "0.3", "--json", *data_args(tmp_path))
        assert json.loads(out)["stopped"] is False
    finally:
        reap(child)


def test_stop_does_not_signal_a_pid_that_is_gone_or_when_the_file_is_unreadable(tmp_path, capsys):
    held = InstanceLock(tmp_path / "d")
    held.acquire()
    try:
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        (tmp_path / "d" / "app.pid").write_text(f"{gone.pid} 8780\n")
        code, out, _ = call(capsys, "stop", *data_args(tmp_path))
        assert code == 1 and "is gone" in out
        (tmp_path / "d" / "app.pid").unlink()
        code, out, _ = call(capsys, "stop", *data_args(tmp_path))
        assert code == 1 and "does not say what" in out
    finally:
        held.release()


# ---- open -------------------------------------------------------------------------------------------------------------------------

def test_open_needs_a_running_server_and_opens_its_url(tmp_path, capsys, monkeypatch):
    code, out, _ = call(capsys, "open", *data_args(tmp_path))
    assert code == 1 and "not running" in out
    seen = []
    monkeypatch.setattr(browser, "open_url", lambda url, prefer="auto": seen.append((url, prefer)) or browser.OpenResult(True, "chrome", "Google Chrome"))
    held = InstanceLock(tmp_path / "d")
    held.acquire()
    held.update(8790)
    try:
        code, out, _ = call(capsys, "open", "--browser", "default", *data_args(tmp_path))
        assert code == 0 and seen == [("http://127.0.0.1:8790/", "default")] and "Opened http://127.0.0.1:8790/" in out
        monkeypatch.setattr(browser, "open_url", lambda url, prefer="auto": browser.OpenResult(False, "none", "no display"))
        code, out, _ = call(capsys, "open", *data_args(tmp_path))
        assert code == 1 and "open http://127.0.0.1:8790/ yourself" in out
    finally:
        held.release()


# ---- config -----------------------------------------------------------------------------------------------------------------------

def test_config_show_gives_every_value_with_its_source_and_no_secret(tmp_path, capsys, monkeypatch):
    data = tmp_path / "d"
    (data / "departments" / "web").mkdir(parents=True)
    (data / "engine.json").write_text('{"budget": 40, "rates": false}')
    (data / "departments" / "web" / "engine.json").write_text('{"budget": 7}')
    (tmp_path / "x.env").write_text("J2_OVERRIDE_KEY=owner-secret-key-123\n")
    monkeypatch.setenv("J2_BOARD", "1")
    monkeypatch.setenv("SUTRA_PORT", "8790")
    monkeypatch.setenv("SUTRA_TOKEN", "launch-token-0123456789")
    code, out, _ = call(capsys, "config", "show", "--json", *data_args(tmp_path))
    doc = json.loads(out)
    fields = doc["engine"]["fields"]
    assert code == 0 and doc["engine"]["scope"] == "global"
    assert fields["budget"] == {"value": 40, "source": "engine.json", "locked": False}
    assert fields["board"]["source"] == "environment (J2_BOARD)" and fields["board"]["value"] is True
    assert fields["max_cycles"]["source"] == "default" and fields["send_mode"]["locked"] is True
    assert doc["app"]["port"] == {"value": 8790, "source": "environment (SUTRA_PORT)"}
    assert doc["override_key_set"] is True and doc["department_overrides"] == {"web": {"budget": 7}}
    assert "owner-secret-key-123" not in out and "launch-token-0123456789" not in out
    code, out, _ = call(capsys, "config", "show", "--dept", "web", "--json", *data_args(tmp_path))
    assert json.loads(out)["engine"]["fields"]["budget"] == {"value": 7, "source": "department web engine.json", "locked": False}


def test_config_show_text_marks_locked_fields_and_never_prints_the_key(tmp_path, capsys):
    (tmp_path / "x.env").write_text("J2_OVERRIDE_KEY=owner-secret-key-123\n")
    code, out, _ = call(capsys, "config", "show", *data_args(tmp_path))
    assert code == 0 and "send_mode = \"dry-run\"  [default]  (locked: only `config set` changes it)" in out
    assert "override key set" in out and "owner-secret-key-123" not in out


def test_config_show_reports_an_invalid_layer_as_a_problem(tmp_path, capsys):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "engine.json").write_text('{"nonsense": 1}')
    code, _, err = call(capsys, "config", "show", *data_args(tmp_path))
    assert code == 1 and "engine.json" in err


def test_config_set_validates_and_writes_engine_json_atomically(tmp_path, capsys):
    path = tmp_path / "d" / "engine.json"
    code, out, _ = call(capsys, "config", "set", "budget", "55", *data_args(tmp_path))
    assert code == 0 and json.loads(path.read_text()) == {"budget": 55} and "applies to the next run" in out
    assert path.stat().st_mode & 0o777 == 0o600 and not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]
    call(capsys, "config", "set", "rates", "off", *data_args(tmp_path))
    call(capsys, "config", "set", "bargain_minutes", "2.5", *data_args(tmp_path))
    call(capsys, "config", "set", "output", "prd", *data_args(tmp_path))
    assert json.loads(path.read_text()) == {"budget": 55, "rates": False, "bargain_minutes": 2.5, "output": "prd"}


def test_config_set_is_the_way_to_set_a_locked_field_and_says_what_live_needs(tmp_path, capsys):
    code, out, _ = call(capsys, "config", "set", "send_mode", "live", *data_args(tmp_path))
    assert code == 0 and "J2_SMTP_*" in out
    call(capsys, "config", "set", "test_email", "me@example.com", *data_args(tmp_path))
    assert json.loads((tmp_path / "d" / "engine.json").read_text()) == {"send_mode": "live", "test_email": "me@example.com"}


def test_config_set_refuses_a_bad_field_or_value_and_writes_nothing(tmp_path, capsys):
    for field, value in (("nonsense", "1"), ("budget", "0"), ("budget", "lots"), ("send_mode", "sometimes"), ("rates", "maybe")):
        code, _, err = call(capsys, "config", "set", field, value, *data_args(tmp_path))
        assert code == 2 and err.startswith("sutra-pro:"), (field, value)
    assert not (tmp_path / "d" / "engine.json").exists()


def test_config_set_will_not_build_on_a_broken_file(tmp_path, capsys):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "engine.json").write_text("{broken")
    code, _, err = call(capsys, "config", "set", "budget", "5", *data_args(tmp_path))
    assert code == 1 and "not valid JSON" in err and (tmp_path / "d" / "engine.json").read_text() == "{broken"


def test_config_set_for_a_department_writes_its_own_file_and_needs_the_department(tmp_path, capsys):
    code, _, err = call(capsys, "config", "set", "budget", "9", "--dept", "web", *data_args(tmp_path))
    assert code == 1 and "no department folder" in err
    (tmp_path / "d" / "departments" / "web").mkdir(parents=True)
    code, out, _ = call(capsys, "config", "set", "budget", "9", "--dept", "web", *data_args(tmp_path))
    assert code == 0 and json.loads((tmp_path / "d" / "departments" / "web" / "engine.json").read_text()) == {"budget": 9}
    assert not (tmp_path / "d" / "engine.json").exists()
    code, _, err = call(capsys, "config", "set", "budget", "9", "--dept", "../x", *data_args(tmp_path))
    assert code == 1


def test_config_init_writes_a_private_template_and_never_overwrites(tmp_path, capsys):
    env_file = tmp_path / "x.env"
    code, out, _ = call(capsys, "config", "init", "--generate-override-key", *data_args(tmp_path))
    key = [l for l in env_file.read_text().splitlines() if l.startswith("J2_OVERRIDE_KEY=")][0].split("=", 1)[1]
    assert code == 0 and env_file.stat().st_mode & 0o777 == 0o600 and str(env_file) in out
    assert key and key not in out                                              # the key is in the file, never on screen
    before = env_file.read_text()
    code, _, err = call(capsys, "config", "init", *data_args(tmp_path))
    assert code == 1 and "already exists" in err and env_file.read_text() == before


def test_config_init_without_the_flag_and_with_json(tmp_path, capsys):
    code, out, _ = call(capsys, "config", "init", "--json", *data_args(tmp_path))
    assert code == 0 and json.loads(out) == {"file": str(tmp_path / "x.env"), "override_key_generated": False}
    assert "J2_OVERRIDE_KEY=" not in [l.split("#")[0].strip() for l in (tmp_path / "x.env").read_text().splitlines() if l.startswith("J2")]


def test_config_sync_library_adds_what_is_missing_and_is_idempotent(tmp_path, capsys):
    data = tmp_path / "d"
    doctor.sync_seed_library(data)
    import shutil
    shutil.rmtree(data / "library" / "prd" / "goals")
    code, out, _ = call(capsys, "config", "sync-library", *data_args(tmp_path))
    assert code == 0 and "Added 1 template(s): prd/goals/still-point-yoga-goals" in out
    code, out, _ = call(capsys, "config", "sync-library", "--json", *data_args(tmp_path))
    assert json.loads(out) == {"added": []}


# ---- the dispatcher and the optional commands ---------------------------------------------------------------------------------------

def test_dispatch_routes_serve_flags_and_words(monkeypatch, capsys, tmp_path):
    seen = []
    monkeypatch.setattr(main_module, "run", lambda argv: seen.append(list(argv)) or 0)
    assert cli.dispatch([]) == 0 and cli.dispatch(["serve"]) == 0 and cli.dispatch(["--port", "9"]) == 0 and cli.dispatch(["serve", "--no-browser"]) == 0
    assert seen == [[], [], ["--port", "9"], ["--no-browser"]]
    assert cli.dispatch(["status", *data_args(tmp_path)]) == 1 and seen[-1] == ["--no-browser"]     # a word is a command, not the server


def test_the_server_help_names_the_commands_and_the_new_flags(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.dispatch(["serve", "--help"])
    out = capsys.readouterr().out
    assert stop.value.code == 0 and "doctor, status, stop, config and open" in out and "--browser" in out and "--verbose" in out


def test_command_names_lists_serve_and_the_builtins():
    assert cli.command_names()[:1] == ["serve"] and set(cli.BUILTIN) <= set(cli.COMMANDS)


def test_modules_of_other_packages_register_commands_and_a_missing_one_is_skipped(monkeypatch, capsys, tmp_path):
    import importlib.machinery
    import types
    module = types.ModuleType("sutra_app.ops.backup")
    module.__spec__ = importlib.machinery.ModuleSpec("sutra_app.ops.backup", None)
    calls = []

    def register(sub):
        parser = sub.add_parser("backup", parents=[cli.common_parser()], help="back up")
        parser.set_defaults(func=lambda args: calls.append(args.data_dir) or 0)
    module.register = register
    module.before_upgrade = lambda settings: calls.append(("upgrade", settings.data_dir))
    monkeypatch.setitem(sys.modules, "sutra_app.ops.backup", module)
    assert cli.main(["backup", *data_args(tmp_path)]) == 0 and calls == [tmp_path / "d"]
    assert "backup" in cli.COMMANDS
    from sutra_app.config import Settings
    settings = Settings.load({}, data_dir=tmp_path / "d", env_file=tmp_path / "x.env")
    cli.before_start(settings)
    assert calls[-1] == ("upgrade", tmp_path / "d")
    monkeypatch.delitem(sys.modules, "sutra_app.ops.backup")
    real_import = cli.importlib.import_module

    def without_backup(name, *args):                                          # GAP-DATA merged: the real module exists, so its absence is simulated
        if name == "sutra_app.ops.backup":
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args)
    monkeypatch.setattr(cli.importlib, "import_module", without_backup)
    cli.build_parser()
    assert "backup" not in cli.COMMANDS                                       # no module, no command, no error
    cli.before_start(settings)


def test_a_broken_optional_module_is_an_error_not_a_silent_skip(monkeypatch, tmp_path):
    import importlib.machinery
    import types
    module = types.ModuleType("sutra_app.ops.retention")
    module.__spec__ = importlib.machinery.ModuleSpec("sutra_app.ops.retention", None)
    monkeypatch.setitem(sys.modules, "sutra_app.ops.retention", module)
    monkeypatch.setattr(cli.importlib, "import_module",
                        lambda name: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'zzz'", name="zzz")) if name.endswith("backup") else module)
    with pytest.raises(ModuleNotFoundError):
        cli.build_parser()


def test_first_run_problems_lists_failures_only_and_never_raises(tmp_path, monkeypatch):
    from sutra_app.config import Settings
    settings = Settings.load({}, data_dir=tmp_path / "d", env_file=tmp_path / "x.env", offline=True)
    assert cli.first_run_problems(settings) == []
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "engine.json").write_text('{"budget": 0}')
    lines = cli.first_run_problems(settings)
    assert len(lines) == 1 and lines[0].startswith("[FAIL] Locked settings")
    monkeypatch.setattr(doctor, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bang")))
    assert "the doctor could not run (RuntimeError" in cli.first_run_problems(settings)[0]


# ---- `run`: the lock, the logging, the first run ------------------------------------------------------------------------------------

class FakeServer:
    """Stands in for AppServer: records what run() built and what the pid file said while 'serving'."""
    last = None

    def __init__(self, config, *, services, url, open_browser):
        self.url, self.open_browser, self.services = url, open_browser, services
        self.opener = None
        FakeServer.last = self

    def run(self, sockets):
        self.pid_while_serving = read_holder(self.services.settings.data_dir)
        self.locked_while_serving = is_locked(self.services.settings.data_dir)
        self.port = sockets[0].getsockname()[1]
        sockets[0].close()


def serve_args(tmp_path, *extra):
    return ["--offline", "--no-browser", "--port", "0", *data_args(tmp_path), *extra]


def test_run_holds_the_lock_while_serving_records_the_port_and_releases_it_after(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "AppServer", FakeServer)
    assert run(serve_args(tmp_path)) == 0
    server = FakeServer.last
    assert server.locked_while_serving and server.pid_while_serving.pid == os.getpid()
    assert server.pid_while_serving.port == server.port and server.pid_while_serving.version
    assert not is_locked(tmp_path / "d") and not (tmp_path / "d" / "app.pid").exists()


def test_a_second_run_prints_where_the_first_is_opens_it_and_exits_zero(tmp_path, monkeypatch, capsys):
    held = InstanceLock(tmp_path / "d")
    held.acquire()
    held.update(8793)
    opened = []
    monkeypatch.setattr(main_module.ops_browser, "open_url", lambda url, prefer="auto": opened.append((url, prefer)) or browser.OpenResult(True, "chrome", ""))
    monkeypatch.setattr(main_module, "AppServer", lambda *a, **k: pytest.fail("a second server must not be built"))
    try:
        assert run(["--offline", "--browser", "default", *data_args(tmp_path)]) == 0
        assert capsys.readouterr().out.strip() == f"Sutra Pro is already running on http://127.0.0.1:8793/ (pid {os.getpid()})"
        assert opened == [("http://127.0.0.1:8793/", "default")]
        assert run(["--offline", "--no-browser", *data_args(tmp_path)]) == 0 and len(opened) == 1       # --no-browser opens nothing
        assert is_locked(tmp_path / "d")                                                              # and the first lock is untouched
    finally:
        held.release()


def test_a_second_run_says_so_when_no_browser_can_be_opened(tmp_path, monkeypatch, capsys):
    held = InstanceLock(tmp_path / "d")
    held.acquire()
    held.update(8793)
    monkeypatch.setattr(main_module.ops_browser, "open_url", lambda url, prefer="auto": browser.OpenResult(False, "none", "no display"))
    try:
        assert run(["--offline", *data_args(tmp_path)]) == 0
        assert "open http://127.0.0.1:8793/ yourself" in capsys.readouterr().out
    finally:
        held.release()


def test_a_stale_pid_file_does_not_stop_a_start(tmp_path, monkeypatch):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "app.pid").write_text("999999 8780\n")
    monkeypatch.setattr(main_module, "AppServer", FakeServer)
    assert run(serve_args(tmp_path)) == 0 and FakeServer.last.pid_while_serving.pid == os.getpid()


def test_the_lock_is_released_when_the_start_is_refused(tmp_path, monkeypatch, capsys):
    blocker = bind_socket("127.0.0.1", 0, scan=False)
    blocker.listen(1)          # a socket that is only bound does not block its port on Linux when the next one sets SO_REUSEADDR: run() then
    port = blocker.getsockname()[1]       # served for ever and the CI's ubuntu leg hung here (found with a stack dump, D104)
    try:
        assert run(["--offline", "--no-browser", "--port", str(port), *data_args(tmp_path)]) == 2
    finally:
        blocker.close()
    assert not is_locked(tmp_path / "d") and not (tmp_path / "d" / "app.pid").exists()
    assert "Use --port" in capsys.readouterr().err


def test_a_data_folder_that_cannot_be_used_is_exit_two(tmp_path, capsys):
    (tmp_path / "file").write_text("x")
    assert run(["--offline", "--no-browser", "--data-dir", str(tmp_path / "file" / "inside")]) == 2
    assert "cannot use the data folder" in capsys.readouterr().err


def test_the_first_run_prints_the_doctors_failures_and_a_later_run_does_not(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main_module, "AppServer", FakeServer)
    monkeypatch.setattr(cli, "first_run_problems", lambda settings: ["[FAIL] Python: too old  -> fix: upgrade"])
    assert run(serve_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "found problems with this machine" in out and "[FAIL] Python: too old" in out
    (tmp_path / "d" / "db.sqlite3").write_bytes(b"")                          # the data folder is not empty any more
    assert run(serve_args(tmp_path)) == 0 and "found problems" not in capsys.readouterr().out
    monkeypatch.setattr(cli, "first_run_problems", lambda settings: [])
    (tmp_path / "d" / "db.sqlite3").unlink()
    assert run(serve_args(tmp_path)) == 0 and capsys.readouterr().out == ""


def test_a_failing_pre_upgrade_hook_stops_the_start_with_exit_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main_module, "AppServer", lambda *a, **k: pytest.fail("must not start"))
    monkeypatch.setattr(cli, "before_start", lambda settings: (_ for _ in ()).throw(RuntimeError("backup failed: disk full")))
    assert run(serve_args(tmp_path)) == 1
    assert "cannot start: backup failed: disk full" in capsys.readouterr().err and not is_locked(tmp_path / "d")


def test_verbose_and_the_browser_choice_reach_the_server(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "AppServer", FakeServer)
    opened = []
    monkeypatch.setattr(main_module.ops_browser, "open_url", lambda url, prefer="auto": opened.append(prefer))
    assert run(serve_args(tmp_path, "--verbose", "--browser", "chrome")) == 0
    assert logging.getLogger().level == logging.DEBUG and (tmp_path / "d" / "logs" / "server.log").is_file()
    FakeServer.last.opener("http://x/")
    assert opened == ["chrome"]
    assert run(serve_args(tmp_path)) == 0 and logging.getLogger().level == logging.INFO


def test_the_app_server_opens_the_browser_through_the_browser_choice_unless_told_otherwise():
    import uvicorn
    config = uvicorn.Config(lambda: None, log_config=None)
    assert main_module.AppServer(config, services=None, url="http://x/", open_browser=True).opener is browser.open_url
    mine = lambda url: None                                                                  # noqa: E731
    assert main_module.AppServer(config, services=None, url="http://x/", open_browser=True, opener=mine).opener is mine


# ---- the real thing: a child process --------------------------------------------------------------------------------------------------

def test_a_real_server_locks_its_folder_answers_status_refuses_a_twin_logs_without_queries_and_stops_on_stop(tmp_path):
    data = tmp_path / "real"
    port = free_port()
    py = str(REPO / "scripts" / "py")
    env = {**os.environ, "SUTRA_ENV_FILE": str(tmp_path / "x.env"), "SUTRA_TOKEN": "t0ken-0123456789abc", "SUTRA_BROWSER_APP": "true"}
    argv = ["--offline", "--no-browser", "--port", str(port), "--data-dir", str(data)]
    child = subprocess.Popen([py, "-m", "sutra_app", "serve", *argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        for _ in range(300):
            if child.poll() is not None:
                pytest.fail("the server exited early:\n" + child.stdout.read())
            try:
                response = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health?secret=abc", timeout=2)
                break
            except OSError:
                time.sleep(0.1)
        assert response.headers["X-Request-Id"] and len(response.headers["X-Request-Id"]) == 12
        holder = read_holder(data)
        assert (holder.pid, holder.port) == (child.pid, port) and is_locked(data)
        status = subprocess.run([py, "-m", "sutra_app", "status", "--json", "--data-dir", str(data)], capture_output=True, text=True, env=env, timeout=60)
        doc = json.loads(status.stdout)
        assert status.returncode == 0 and doc["pid"] == child.pid and doc["health"]["ok"] is True
        twin = subprocess.run([py, "-m", "sutra_app", *argv], capture_output=True, text=True, env=env, timeout=60)
        assert twin.returncode == 0 and f"already running on http://127.0.0.1:{port}/ (pid {child.pid})" in twin.stdout
        stop = subprocess.run([py, "-m", "sutra_app", "stop", "--data-dir", str(data)], capture_output=True, text=True, env=env, timeout=60)
        assert stop.returncode == 0 and "Stopped." in stop.stdout
        child.wait(timeout=20)
        assert not is_locked(data) and not (data / "app.pid").exists()
        log = (data / "logs" / "server.log").read_text()
        assert "GET /api/health" in log and "secret=abc" not in log and "t0ken-0123456789abc" not in log
    finally:
        if child.poll() is None:
            child.kill()
        child.stdout.close()
