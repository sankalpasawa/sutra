"""The engine host's hand-off (MAN-6, D263): `handoff.json` for a node's run, built from the run folder; skipped for every other run; the finish steps that exist are unchanged."""
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from sutra_app.engine.host import finish, handoff
from sutra_app.orchestrator import tasks as orchestrator_tasks

NODE = "nd_" + "a" * 12


def run_folder(tmp_path, **files):
    folder = tmp_path / "run"
    folder.mkdir()
    for name, body in files.items():
        (folder / name.replace("__", ".")).write_bytes(body if isinstance(body, bytes) else body.encode())
    return folder


def host_for(folder, node=True, status="done", outcome="Landing page ready"):
    task = SimpleNamespace(node=SimpleNamespace(id=NODE, role="worker") if node else None)
    lines = []
    return SimpleNamespace(task=task, paths=SimpleNamespace(run_dir=folder), ended_status=status, ended_outcome=outcome, lines=lines, stopping=SimpleNamespace(is_set=lambda: False),
                           trace=lambda type, data=None: lines.append((type, data)))


def test_the_document_lists_the_top_level_files_with_checksums_and_leaves_out_the_plumbing(tmp_path):
    folder = run_folder(tmp_path, index__html="<h1>hi</h1>", notes__md="n", task__json="{}", events__jsonl="", trace__jsonl="x", deliverable__json="{}", handoff__json="old")
    (folder / "site").mkdir()
    (folder / "site" / "deep.txt").write_text("not top level")
    (folder / ".hidden").write_text("h")
    os.symlink(folder / "index.html", folder / "link.html") if os.name == "posix" else None
    document = handoff.build(folder, NODE, "done", "  Done:\nthe page  ")
    assert document["v"] == 1 and document["node_id"] == NODE and document["status"] == "done" and document["summary"] == "Done: the page" and document["claims"] == [] and document["needs"] == []
    assert [f["path"] for f in document["files"]] == ["index.html", "notes.md"]
    index = next(f for f in document["files"] if f["path"] == "index.html")
    assert index == {"path": "index.html", "sha256": hashlib.sha256(b"<h1>hi</h1>").hexdigest(), "bytes": 11}


def test_limits_the_summary_clipped_the_files_at_200_and_the_status_is_one_of_the_three(tmp_path):
    folder = run_folder(tmp_path)
    for n in range(230):
        (folder / f"f{n:03}.txt").write_text(str(n))
    document = handoff.build(folder, NODE, "done_with_open_items", "x" * 5000)
    assert len(document["files"]) == 200 and len(document["summary"]) == 2000 and document["status"] == "done_with_open_items"
    assert handoff.build(folder, NODE, "stopped", "")["status"] == "blocked" and handoff.build(folder, NODE, "done", "")["summary"] == "The run ended."


def test_write_is_private_atomic_and_leaves_no_temp_file(tmp_path):
    folder = run_folder(tmp_path)
    path = handoff.write(folder, handoff.build(folder, NODE, "done", "ok"))
    assert path == folder / "handoff.json" and json.loads(path.read_text())["node_id"] == NODE and [p.name for p in folder.iterdir()] == ["handoff.json"]
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_finish_step_writes_it_only_for_a_node_and_a_run_that_is_not_one_writes_nothing_and_traces_nothing(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "out.txt").write_text("x")
    host = host_for(plain, node=False)
    assert finish.run_steps(host, "done", ()) == [] and not (plain / "handoff.json").exists()
    assert [name for name, _ in finish.STEPS + (finish.NODE_STEPS if host.task.node is not None else ())] == ["agent_views", "export", "catalog"]
    rows = finish.run_steps(host, "done", (("handoff", finish.handoff),))
    assert rows[0]["result"] == "skipped" and "not a node" in rows[0]["why"] and not (plain / "handoff.json").exists()
    node_dir = tmp_path / "node"
    node_dir.mkdir()
    (node_dir / "out.txt").write_text("x")
    host = host_for(node_dir)
    rows = finish.run_steps(host, "done", (("handoff", finish.handoff),))
    assert rows[0]["result"] == "ok" and rows[0]["files"] == 1 and json.loads((node_dir / "handoff.json").read_text())["files"][0]["path"] == "out.txt"


def test_a_run_that_did_not_end_well_leaves_no_hand_off_and_a_failure_is_traced_never_raised(tmp_path, monkeypatch):
    folder = run_folder(tmp_path, a__txt="a")
    for status in ("stopped", "crashed"):
        assert finish.run_steps(host_for(folder, status=status), status) == [] and not (folder / "handoff.json").exists()
    monkeypatch.setattr(handoff, "write", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    rows = finish.run_steps(host_for(folder), "done", (("handoff", finish.handoff),))
    assert rows[0]["result"] == "failed" and "disk full" in rows[0]["error"]


def test_the_plumbing_names_cover_what_the_servers_upstream_listing_leaves_out():
    assert set(orchestrator_tasks.RUN_FOLDER_INTERNALS) <= set(handoff.NOT_HANDED_ON)


def test_the_default_steps_of_a_node_carry_the_hand_off_and_those_of_any_other_run_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(finish, "STEPS", ())                                   # the J2 steps are tested elsewhere: only the node step differs
    node_dir, plain_dir = tmp_path / "n", tmp_path / "p"
    for folder in (node_dir, plain_dir):
        folder.mkdir()
        (folder / "a.txt").write_text("a")
    node_host, plain_host = host_for(node_dir), host_for(plain_dir, node=False)
    assert [row["step"] for row in finish.run_steps(node_host, "done")] == ["handoff"] and (node_dir / "handoff.json").is_file()
    assert finish.run_steps(plain_host, "done") == [] and not (plain_dir / "handoff.json").exists() and plain_host.lines == []


def test_the_hand_off_runs_first_so_a_slow_step_never_costs_a_node_its_hand_off(tmp_path, monkeypatch):
    """G1 (D311): `agent_views` took more than the step limit and ends the rest; the hand-off had already been written, and the slow step's own line says it was slow."""
    folder = tmp_path / "n"
    folder.mkdir()
    (folder / "a.txt").write_text("a")
    ticks = iter(range(0, 1000, 1))

    def slow_views(host):                                                      # takes "30 seconds" on the fake clock: over STEP_SECONDS
        for _ in range(29):
            next(ticks)
        return {"files": 0}
    monkeypatch.setattr(finish, "STEPS", (("agent_views", slow_views), ("catalog", lambda host: {})))
    rows = finish.run_steps(host_for(folder), "done", clock=lambda: float(next(ticks)))
    assert [row["step"] for row in rows] == ["handoff", "agent_views", "catalog"]
    assert rows[0]["result"] == "ok" and (folder / "handoff.json").is_file()
    assert rows[1].get("slow") is True and rows[2]["result"] == "skipped"


def test_a_link_planted_under_the_old_temp_name_is_never_followed_and_the_temp_is_unique_and_exclusive(tmp_path, monkeypatch):
    """Minor 4: the temp file has a name nobody else has and is made with O_EXCL, so a symlink planted at the old fixed name does not redirect the write."""
    folder = run_folder(tmp_path, out__txt="x")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    (folder / ".handoff.json.tmp").symlink_to(victim)
    seen = []
    real_open = os.open

    def spy(path, flags, *a, **k):
        seen.append((str(path), flags))
        return real_open(path, flags, *a, **k)
    monkeypatch.setattr(os, "open", spy)
    handoff.write(folder, handoff.build(folder, NODE, "done", "ok"))
    handoff.write(folder, handoff.build(folder, NODE, "done", "again"))
    temps = [(p, f) for p, f in seen if p.endswith(".tmp")]
    assert victim.read_text() == "keep me" and len(temps) == 2 and temps[0][0] != temps[1][0] and all(f & os.O_EXCL for _, f in temps)
    assert json.loads((folder / "handoff.json").read_text())["summary"] == "again" and sorted(p.name for p in folder.iterdir() if p.name.endswith(".tmp")) == [".handoff.json.tmp"]
