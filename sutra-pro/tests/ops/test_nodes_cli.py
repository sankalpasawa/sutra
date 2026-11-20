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
