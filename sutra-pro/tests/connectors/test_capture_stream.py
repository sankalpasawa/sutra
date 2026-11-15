"""`scripts/capture_connector_fixtures.py --stream` (streaming design D205, work package STR-1), driven against the fake CLIs: it goes through the product's
connectors, writes scrubbed files, and refuses to write a file the audit objects to. No test reaches a real model."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location("capture_stream_script", ROOT / "scripts" / "capture_connector_fixtures.py")
capture = importlib.util.module_from_spec(spec)
sys.modules["capture_stream_script"] = capture
spec.loader.exec_module(capture)

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="the fake CLIs are POSIX")


def test_plan_lists_the_stream_steps_and_runs_nothing():
    text = capture.plan_text()
    assert "With --stream only" in text and "claude_stream_tool" in text and "codex_stream_stop" in text
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "capture_connector_fixtures.py"), "--plan"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "claude_stream_tool" in out.stdout


def test_the_stream_mode_needs_the_live_switch(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "capture_connector_fixtures.py"), "--stream", "--out", str(tmp_path)], capture_output=True, text=True,
                         timeout=60, env={"PATH": "/usr/bin:/bin"})
    assert out.returncode == 2 and not list(tmp_path.iterdir())


@pytest.mark.parametrize("text,hit", [
    ("a path /Users/me/work/x and C:\\Users\\me\\x", False),
    ("a path /Users/someone/work", True), ("/home/someone/x", True), ("C:\\Users\\someone\\x", True),
    ("/var/folders/ab/sutra-capture-xyz/scratch", True),
])
def test_the_audit_refuses_user_paths_and_the_scratch_directory(text, hit):
    assert bool(capture.audit_text(text)) is hit


def test_the_audit_reads_the_ownership_pattern_from_the_audit_script_not_from_itself():
    pattern = capture.ownership_pattern()
    assert pattern is not None
    assert capture.audit_text("written by " + pattern.pattern.split("|")[0]) != []
    assert pattern.pattern.split("|")[0] not in (ROOT / "scripts" / "capture_connector_fixtures.py").read_text(encoding="utf-8").lower()


def test_audit_catches_a_learned_identity_string():
    assert capture.audit_text("hello someone@corp.example", extra=["someone@corp.example"]) != []
    assert capture.audit_text("hello", extra=["someone@corp.example"]) == []


@POSIX
def test_a_stream_capture_through_the_connectors_writes_scrubbed_files(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="the notes say three items")
    out = tmp_path / "out"
    out.mkdir()
    env = fake.env()
    cap = capture.StreamCapture(out, fake.claude, fake.codex, only="claude", skip=["stream_stop"], pass_env=sorted(env), environ={**env, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    code = cap.run_streams()
    assert code == 0, cap.failed
    written = sorted(cap.written)
    assert "claude/stream_partials_tool_ok.jsonl" in written and "timing/stream_timing.json" in written
    lines = [json.loads(l) for l in (out / "claude" / "stream_partials_tool_ok.jsonl").read_text().splitlines()]
    assert lines[0]["type"] == "system" and lines[0]["cwd"] == "/work" and lines[-1]["type"] == "result"
    timing = json.loads((out / "timing/stream_timing.json").read_text())
    assert timing["measured"]["claude_tool"]["first_output_s"] is not None and "timeline" in timing["measured"]["claude_tool"]
    assert any("--include-partial-messages" == f for f in timing["measured"]["claude_tool"]["argv_flags"])      # it ran the product's own command
    assert cap.model_calls["claude"] == 1


@POSIX
def test_a_hit_in_the_audit_refuses_the_write_and_fails_the_step(fake, tmp_path):
    fake.sequence("ok_plain")
    out = tmp_path / "out"
    out.mkdir()
    env = fake.env()
    cap = capture.StreamCapture(out, fake.claude, fake.codex, only="claude", skip=["stream_stop"], pass_env=sorted(env), environ={**env, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    original = cap.scrubbed_lines
    cap.scrubbed_lines = lambda result: original(result) + '{"type":"note","text":"/Users/someoneelse/project"}\n'      # a path the scrubber did not know
    code = cap.run_streams()
    assert code == 1 and not (out / "claude" / "stream_partials_tool_ok.jsonl").exists()
    assert any("not written" in why and "user path" in why for _, why in cap.failed)


@POSIX
def test_the_stream_call_limit_is_two_per_cli(fake, tmp_path):
    fake.sequence("ok_plain")
    env = fake.env()
    cap = capture.StreamCapture(tmp_path / "o", fake.claude, fake.codex, only="claude", pass_env=sorted(env), environ={**env, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    cap.stream("claude", "hello")
    cap.stream("claude", "hello")
    with pytest.raises(capture.CaptureError):
        cap.stream("claude", "hello")


def _delta_lines(pieces, kind="input_json_delta", field="partial_json"):
    return "\n".join(json.dumps({"type": "stream_event", "api_message_id": "m1", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": kind, field: p}}})
                     for p in pieces)


def test_a_path_split_across_deltas_is_scrubbed_whole_and_the_piece_count_is_kept():
    scrubber = capture.Scrubber("/Users/someone")
    scrubber.add("/private/tmp/sutra-capture-abc123", "/scratch/probe")
    pieces = ["", '{"file_path": "/private/t', "mp/sutra-cap", "ture-abc123/folder/notes.", "txt", '"}']
    raw = _delta_lines(pieces)
    assert capture.audit_text(raw) != []                                      # no single line holds the whole path, the joined deltas do
    out = capture.scrub_stream(raw, scrubber)
    got = [json.loads(l)["event"]["delta"]["partial_json"] for l in out.splitlines()]
    assert len(got) == len(pieces) and got[0] == "" and "".join(got) == '{"file_path": "/scratch/probe/folder/notes.txt"}'
    assert capture.audit_text(out) == []


def test_text_deltas_split_across_pieces_are_scrubbed_too_and_other_blocks_are_left_alone():
    scrubber = capture.Scrubber("/Users/someone")
    scrubber.add("someone@corp.example", "user@example.com")
    raw = _delta_lines(["write to someone@co", "rp.example now"], "text_delta", "text") + "\n" + _delta_lines(["untouched"], "text_delta", "text").replace('"m1"', '"m2"')
    got = [json.loads(l)["event"]["delta"]["text"] for l in capture.scrub_stream(raw, scrubber).splitlines()]
    assert "".join(got[:2]) == "write to user@example.com now" and got[2] == "untouched"


def test_the_audit_sees_a_secret_that_only_exists_across_deltas():
    raw = _delta_lines(["a path /Users/some", "oneelse/project"], "text_delta", "text")
    assert capture.audit_text(raw) != []
