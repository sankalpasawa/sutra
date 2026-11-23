"""`sutra-pro nodes status | pause | kill | resume` (MAN-4, D279): the two files by hand, the words it prints, and that it needs neither the server nor a token."""
import json
import os
import stat

import pytest

from sutra_app.ops import cli
from sutra_app.orchestrator.killswitch import KILL_FILE, PAUSE_FILE


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith(("SUTRA_", "J2_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("SUTRA_ENV_FILE", str(tmp_path / "x.env"))


def call(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def nodes(tmp_path):
    return tmp_path / "d" / "nodes"


def args(tmp_path, *more):
    return ["nodes", *more, "--data-dir", str(tmp_path / "d")]


def test_the_command_is_registered_with_its_four_actions():
    parser = cli.build_parser()
    assert "nodes" in cli.COMMANDS and "nodes" in cli.command_names()
    for action in ("status", "pause", "kill", "resume"):
        assert parser.parse_args(["nodes", action]).nodes_cmd == action
    with pytest.raises(SystemExit):
        parser.parse_args(["nodes"])
    with pytest.raises(SystemExit):
        parser.parse_args(["nodes", "explode"])


def test_status_with_nothing_there_says_agents_may_start_and_shows_the_four_settings(capsys, tmp_path):
    code, out, err = call(capsys, *args(tmp_path, "status"))
    assert code == 0 and err == "" and "Agents may start." in out and "KILL absent, PAUSE absent" in out
    assert "SUTRA_NODES_V1=0, SUTRA_NODES_LANES=0, SUTRA_NODES_REVIEWER=0, SUTRA_NODES_SLOTS=0" in out and "SUTRA_NODES_V1 is 0" in out
    assert not nodes(tmp_path).exists()                                              # looking creates nothing


def test_status_as_json_has_the_level_the_files_and_the_settings(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NODES_V1", "1")
    monkeypatch.setenv("SUTRA_NODES_LANES", "1")
    code, out, _ = call(capsys, *args(tmp_path, "status", "--json"))
    doc = json.loads(out)
    assert code == 0 and doc["level"] == "none" and doc["kill"] is None and doc["pause"] is None and doc["folder"] == str(nodes(tmp_path))
    assert doc["settings"] == {"SUTRA_NODES_V1": True, "SUTRA_NODES_LANES": True, "SUTRA_NODES_REVIEWER": False, "SUTRA_NODES_SLOTS": False}
    assert "SUTRA_NODES_V1 is 0" not in out


def test_pause_then_kill_then_resume_move_the_files_and_the_words(capsys, tmp_path):
    code, out, _ = call(capsys, *args(tmp_path, "pause", "--reason", "lunch break"))
    assert code == 0 and "Paused" in out and (nodes(tmp_path) / PAUSE_FILE).is_file() and not (nodes(tmp_path) / KILL_FILE).exists()
    code, out, _ = call(capsys, *args(tmp_path, "kill", "--reason", "stop everything"))
    assert code == 0 and "Kill switch on" in out and "nodes resume" in out and (nodes(tmp_path) / KILL_FILE).is_file()
    _, out, _ = call(capsys, *args(tmp_path, "status"))
    assert "The KILL file is there" in out and "every agent was stopped" not in out and "KILL present, PAUSE present" in out and "reason stop everything" in out and "by owner" in out
    code, out, _ = call(capsys, *args(tmp_path, "resume"))
    assert code == 0 and "KILL" in out and "PAUSE" in out and not list(nodes(tmp_path).iterdir())
    code, out, _ = call(capsys, *args(tmp_path, "resume"))
    assert code == 0 and "Nothing to resume" in out
    _, out, _ = call(capsys, *args(tmp_path, "status", "--json"))
    assert json.loads(out)["level"] == "none"


def test_the_files_are_private_and_hold_who_why_and_when(capsys, tmp_path):
    call(capsys, *args(tmp_path, "kill", "--reason", "x"))
    path = nodes(tmp_path) / KILL_FILE
    note = json.loads(path.read_text(encoding="utf-8"))
    assert note["by"] == "owner" and note["reason"] == "x" and note["at"].endswith("Z")
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_key_typed_into_the_reason_is_not_written_to_the_file(capsys, tmp_path):
    call(capsys, *args(tmp_path, "pause", "--reason", "token sk-ABCDEFGHIJKLMNOP1234 leaked"))
    text = (nodes(tmp_path) / PAUSE_FILE).read_text(encoding="utf-8")
    assert "sk-ABCDEFGHIJ" not in text and "[redacted" in text


def test_a_long_reason_is_clipped_and_a_json_result_is_valid(capsys, tmp_path):
    code, out, _ = call(capsys, *args(tmp_path, "kill", "--reason", "y" * 500, "--json"))
    assert code == 0 and json.loads(out)["level"] == "kill"
    assert len(json.loads((nodes(tmp_path) / KILL_FILE).read_text(encoding="utf-8"))["reason"]) == 200


def test_with_the_flag_on_the_command_does_not_print_the_off_note(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NODES_V1", "1")
    _, out, _ = call(capsys, *args(tmp_path, "kill"))
    assert "SUTRA_NODES_V1 is 0" not in out and "Kill switch on" in out


def test_a_bad_setting_is_exit_2(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NODES_V1", "maybe")
    code, out, err = call(capsys, *args(tmp_path, "status"))
    assert code == 2 and "SUTRA_NODES_V1" in err


def test_the_command_module_does_not_import_the_orchestrator_until_a_command_runs():
    import subprocess
    import sys as _sys
    code = "import sys, sutra_app.ops.nodes as n; assert 'sutra_app.orchestrator.killswitch' not in sys.modules, 'imported early'; print('light')"
    done = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0 and "light" in done.stdout, done.stderr


def test_a_switch_file_that_cannot_be_written_is_exit_1_and_says_nothing_is_held_back(capsys, tmp_path, monkeypatch):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "nodes").write_text("a file where the folder should be")
    code, out, err = call(capsys, *args(tmp_path, "kill"))
    assert code == 1 and "could not write the KILL file" in err and "nothing is held back" in err and "Kill switch on" not in out


def test_resume_tells_a_running_app_to_let_go_of_a_switch_it_holds_in_memory_and_a_nodes_path_that_is_a_file_is_a_plain_error(capsys, tmp_path, monkeypatch):
    from sutra_app.orchestrator.killswitch import KillSwitch, RESUME_FILE
    monkeypatch.setenv("SUTRA_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    app_side = KillSwitch(tmp_path / "data" / "nodes")
    monkeypatch.setattr(app_side, "_write", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only disk")))
    with pytest.raises(OSError):
        app_side.set("kill")
    assert app_side.killed is True                                                              # held in memory
    assert cli.main(["nodes", "resume"]) == 0
    marker = app_side.resume_marker()
    assert marker.exists() and app_side.killed is False and marker.name == RESUME_FILE
    assert marker.exists(), "the marker stays until the app has written its row (D406)"
    app_side.pending_resumes()
    app_side.finish_resumes()
    assert not marker.exists()
    broken = tmp_path / "other"
    monkeypatch.setenv("SUTRA_DATA_DIR", str(broken))
    broken.mkdir()
    (broken / "nodes").write_text("x")
    capsys.readouterr()
    assert cli.main(["nodes", "resume"]) == 1
    assert "is a file, not a folder" in capsys.readouterr().out and (broken / "nodes").read_text() == "x"                  # nothing of the owner's is deleted
    assert "file, not a folder" in KillSwitch(broken / "nodes").held() and KillSwitch(broken / "nodes").broken()


# ---- the shell's settings are not the running app's (D384) -------------------------------------------------------------------------------

import http.server
import threading

from sutra_app.ops.lock import InstanceLock


class _Status(http.server.BaseHTTPRequestHandler):
    code = 200
    body = {"level": "none", "kill": None, "pause": None, "settings": {"SUTRA_NODES_V1": True, "SUTRA_NODES_LANES": False, "SUTRA_NODES_REVIEWER": False, "SUTRA_NODES_SLOTS": False}}

    def do_GET(self):                                   # noqa: N802
        payload = json.dumps(self.body).encode() if self.code == 200 else b'{"error":{"code":"not_found"}}'
        self.send_response(self.code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):                       # noqa: D401
        pass


@pytest.fixture
def running_app(tmp_path):
    """A stand-in for a running Sutra on tmp/d: it holds the folder's lock and answers /api/nodes/status."""
    data = tmp_path / "d"
    data.mkdir()
    lock = InstanceLock(data, version="0.0.0")
    assert lock.acquire()

    def start(code=200):
        handler = type("H", (_Status,), {"code": code})
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        lock.update(port=server.server_address[1])
        return server
    servers = []
    yield lambda code=200: servers.append(start(code))
    for server in servers:
        server.shutdown()
        server.server_close()
    lock.release()


def test_status_labels_the_shells_settings_and_says_nothing_runs_when_no_app_holds_the_folder(capsys, tmp_path):
    code, out, _ = call(capsys, *args(tmp_path, "status"))
    assert "settings in this shell: SUTRA_NODES_V1=0" in out and "running Sutra: none holds this folder now" in out
    assert "so a running Sutra does not look" not in out and "no agent runs" not in out, "it must not say a running app has nothing on because this shell does not"


def test_status_shows_a_running_app_with_projects_on_whatever_the_shell_says(capsys, tmp_path, running_app):
    running_app(200)
    code, out, _ = call(capsys, *args(tmp_path, "status"))                              # this shell has SUTRA_NODES_V1 unset
    assert code == 0 and "SUTRA_NODES_V1=0, SUTRA_NODES_LANES=0" in out.split("running Sutra")[0] and "projects are ON" in out
    assert "no agent runs" not in out and "SUTRA_NODES_V1 is 0" not in out
    _, as_json, _ = call(capsys, *args(tmp_path, "status", "--json"))
    doc = json.loads(as_json)
    assert doc["settings"]["SUTRA_NODES_V1"] is False and doc["running"]["state"] == "running" and doc["running"]["projects"] is True
    assert doc["running"]["settings"]["SUTRA_NODES_V1"] is True and doc["running"]["level"] == "none"


def test_status_says_a_running_app_with_projects_off_does_not_look_at_the_files(capsys, tmp_path, running_app, monkeypatch):
    running_app(404)
    monkeypatch.setenv("SUTRA_NODES_V1", "1")                                           # this shell says ON, the app is OFF
    code, out, _ = call(capsys, *args(tmp_path, "status"))
    assert "projects are OFF (it was started without SUTRA_NODES_V1=1)" in out and "no agent runs" in out
    assert json.loads(call(capsys, *args(tmp_path, "status", "--json"))[1])["running"]["projects"] is False


def test_status_says_when_a_running_app_does_not_answer(capsys, tmp_path, running_app):
    data = tmp_path / "d"
    running_app(200)
    from sutra_app.ops import lock as lock_module
    (data / lock_module.PID_NAME).write_text(f"{os.getpid()} 1\n", encoding="utf-8")        # a port nobody listens on
    code, out, _ = call(capsys, *args(tmp_path, "status"))
    assert code == 0 and "it did not answer, so its settings are not known" in out


def test_pause_and_kill_say_what_runs_too(capsys, tmp_path, running_app):
    running_app(200)
    for action in ("pause", "kill"):
        code, out, _ = call(capsys, *args(tmp_path, action))
        assert code == 0 and "projects are ON" in out
