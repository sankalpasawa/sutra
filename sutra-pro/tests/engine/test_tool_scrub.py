"""R11 (D345): when a node's run ends the inputs of its tool calls are emptied in `calls.jsonl` and `snapshot.json`; names, numbers and results stay; every other line is byte for byte as it was; an
ordinary run (no node) is never touched."""
import json
from types import SimpleNamespace

from sutra_app.engine.host.loop import Host
from sutra_app.engine.host.toolscrub import blank_tool_inputs

SECRET = "curl -H 'token: ghp_" + "a" * 36 + "' https://x.example/private"


def record(n, with_tools=True):
    rec = {"id": n, "fn": "builder", "prompt": "write the page", "raw": "done"}
    if with_tools:
        rec["tools"] = {"allowed": ["Bash"], "cwd": "/run", "calls": [{"n": 1, "name": "Bash", "input": SECRET, "ok": True}, {"n": 2, "name": "Read", "input": "/run/a.txt", "ok": None}], "denied": 0}
    return rec


def make_run(tmp_path):
    lines = [json.dumps(record(1, False)) + "\n", json.dumps(record(2)) + "\n", "not json but has \"tools\" and \"input\"\n"]
    (tmp_path / "calls.jsonl").write_text("".join(lines))
    (tmp_path / "snapshot.json").write_text(json.dumps({"call_log": [record(2)], "other": "x"}))
    return lines


def test_inputs_are_emptied_and_everything_else_is_kept(tmp_path):
    lines = make_run(tmp_path)
    assert blank_tool_inputs(tmp_path) == 4                                                        # two calls in each file
    new = (tmp_path / "calls.jsonl").read_text().splitlines(True)
    assert new[0] == lines[0] and new[2] == lines[2]                                               # a line with no tool input, and a damaged one, are as they were
    row = json.loads(new[1])
    assert [(c["n"], c["name"], c["input"], c["ok"]) for c in row["tools"]["calls"]] == [(1, "Bash", "", True), (2, "Read", "", None)] and row["prompt"] == "write the page"
    snap = json.loads((tmp_path / "snapshot.json").read_text())
    assert snap["other"] == "x" and all(c["input"] == "" for c in snap["call_log"][0]["tools"]["calls"])
    assert "ghp_" not in (tmp_path / "calls.jsonl").read_text() + (tmp_path / "snapshot.json").read_text()
    assert blank_tool_inputs(tmp_path) == 0                                                        # nothing left to blank: the files are not rewritten


def test_missing_files_links_and_damaged_snapshots_change_nothing(tmp_path):
    assert blank_tool_inputs(tmp_path) == 0
    (tmp_path / "real.jsonl").write_text(json.dumps(record(1)) + "\n")
    (tmp_path / "calls.jsonl").symlink_to(tmp_path / "real.jsonl")
    (tmp_path / "snapshot.json").write_text("{not json")
    assert blank_tool_inputs(tmp_path) == 0 and "ghp_" in (tmp_path / "real.jsonl").read_text()    # a link is never followed or rewritten


def test_only_the_run_of_a_project_step_is_cleaned(tmp_path):
    make_run(tmp_path)
    before = (tmp_path / "calls.jsonl").read_bytes()
    for node, expect in ((None, before), (object(), None)):
        host = SimpleNamespace(task=SimpleNamespace(node=node), paths=SimpleNamespace(run_dir=tmp_path), trace=lambda *a, **k: None)
        Host._blank_tool_inputs(host)
        if expect is not None:
            assert (tmp_path / "calls.jsonl").read_bytes() == expect                               # an ordinary run: byte for byte as J2 wrote it
    assert b"ghp_" not in (tmp_path / "calls.jsonl").read_bytes()
