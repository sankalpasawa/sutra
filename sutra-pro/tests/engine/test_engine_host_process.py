"""The real process: `python -m sutra_app.engine --run-dir <dir> --mock` (work package E3, engine design 4.7, flows F1, F5, F6, F8).

The engine process gets J2's Chrome checks faked the way a deployment never would: `SUTRA_HOOKS` names `factory` below, which
patches `j2_check` and returns the ordinary hooks (the hook factory runs before J2 is imported, in the engine process itself).
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_engine_host import (  # noqa: F401  (these fixtures are used by name)
    BREW_LAB, QUIET, VAGUE, append_inbox, events, fake_chrome, jsonl, of, trace, wait_until,
)

from sutra_app.engine.hooks import EventHooks
from sutra_app.orchestrator.models import parse_event

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def factory(**kw):
    """`SUTRA_HOOKS=test_engine_host_process:factory`, run inside the engine process before J2 is imported."""
    from sutra_app.engine import j2_check
    fake_chrome(j2_check)
    return EventHooks(kw["writer"], kw["notify"], kw["validator"], kw["node_context_file"])


def spawn(run_dir: Path, *extra: str, **env) -> subprocess.Popen:
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_"))}
    clean.update({"PYTHONPATH": os.pathsep.join([str(ROOT), str(HERE)]), "SUTRA_HOOKS": "test_engine_host_process:factory",
                  "SUTRA_NODES": "on", "SUTRA_HEARTBEAT_S": "0.2", "SUTRA_ENV_FILE": str(run_dir.parent / "none.env"), **env})
    out, err = open(run_dir / "run.stdout.log", "ab"), open(run_dir / "run.stderr.log", "ab")      # what the launcher does
    return subprocess.Popen([sys.executable, "-m", "sutra_app.engine", "--run-dir", str(run_dir), "--mock", *extra], env=clean,
                            cwd=str(run_dir.parent), stdout=out, stderr=err, start_new_session=True)


def finish(proc: subprocess.Popen, timeout: float = 60.0) -> int:
    try:
        return proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise


def stderr_of(run_dir: Path) -> str:
    return (run_dir / "run.stderr.log").read_text(errors="replace")


def asked(run_dir):
    return [e for e in of(events(run_dir), "say") if e.get("act") == "ASK_REQUESTER"]


@pytest.fixture
def procs():
    started = []
    yield started
    for proc in started:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_a_brew_lab_run_in_a_real_process_ends_done_with_heartbeats_and_a_clean_log(make_run_dir, procs):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    proc = spawn(run_dir)
    procs.append(proc)
    assert finish(proc) == 0, stderr_of(run_dir)
    rows = events(run_dir)
    assert rows[0]["t"] == "run.started" and rows[0]["pid"] == proc.pid and rows[0]["mock"] is True and rows[0]["seed"] == "none"
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items")
    assert len(of(rows, "heartbeat")) >= 2 and rows[1]["t"] in ("heartbeat", "say", "node"), "the first beat follows run.started"
    for row in rows:
        parse_event(row, strict=True)
    assert {"node", "step", "atom", "usage", "say"} <= {e["t"] for e in rows}
    assert (run_dir / "run.stdout.log").read_text() == "", "the host never prints protocol data"
    assert "Traceback" not in stderr_of(run_dir)
    live = json.loads((run_dir / "live.json").read_text())
    assert live["pid"] == proc.pid and json.loads((run_dir / "snapshot.json").read_text())["done"] is True
    assert json.loads((run_dir / "settings.json").read_text())["budget"] == 100
    assert (run_dir.parents[3] / "library" / "index.json").is_file(), "the template library was seeded"


def test_kill_minus_9_leaves_no_run_ended_and_the_heartbeat_stops_with_the_process(make_run_dir, procs):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    proc = spawn(run_dir)
    procs.append(proc)
    wait_until(lambda: asked(run_dir), what="the question")
    wait_until(lambda: len(of(events(run_dir), "heartbeat")) >= 3, what="beats while the run waits for the owner")
    proc.send_signal(signal.SIGKILL)
    assert finish(proc) == -signal.SIGKILL
    count = len(events(run_dir))
    time.sleep(0.6)
    rows = events(run_dir)
    assert len(rows) == count and "run.ended" not in [e["t"] for e in rows], "a process that was killed says nothing more"


def test_sigterm_writes_stopped_and_exits_143(make_run_dir, procs):
    run_dir = make_run_dir(user_text=VAGUE[0], settings=QUIET)
    proc = spawn(run_dir)
    procs.append(proc)
    wait_until(lambda: asked(run_dir), what="the question")
    proc.send_signal(signal.SIGTERM)
    assert finish(proc) == 143
    ended = events(run_dir)[-1]
    assert ended["t"] == "run.ended" and ended["status"] == "stopped" and "SIGTERM" in ended["outcome"]
    assert json.loads((run_dir / "summary.json").read_text())["status"] == "stopped"


def test_a_stop_line_ends_the_process_inside_six_seconds_while_a_slow_call_is_running(make_run_dir, procs):
    run_dir = make_run_dir(user_text=BREW_LAB, settings=QUIET)
    proc = spawn(run_dir, STUDIO_MOCK_DELAY="60")             # every scripted reply takes a minute
    procs.append(proc)
    wait_until(lambda: trace(run_dir, "turn.started"), what="a turn with a call in flight")
    time.sleep(0.3)
    started = time.time()
    append_inbox(run_dir, 1, "stop")
    assert finish(proc, 10) == 0, stderr_of(run_dir)
    assert time.time() - started < 6
    ended = events(run_dir)[-1]
    assert ended["status"] == "stopped" and ended["outcome"] == "Stopped: stopped on request" and ended["code"] is None
    assert json.loads((run_dir / "summary.json").read_text())["status"] == "stopped"


def test_two_departments_run_side_by_side_and_share_nothing_but_the_library(make_run_dir, data_dir, procs):
    a = make_run_dir(dept_id="web", run_id="j2-20261104-100004-aaaa", user_text=BREW_LAB, settings={"J2_BUDGET": "95"})
    b = make_run_dir(dept_id="docs", run_id="j2-20261104-100004-bbbb", user_text=BREW_LAB, settings={"J2_BUDGET": "120", "J2_REALIZATION": "0"})
    first, second = spawn(a), spawn(b)
    procs.extend([first, second])
    assert finish(first) == 0 and finish(second) == 0, stderr_of(a) + stderr_of(b)
    assert first.pid != second.pid
    for run_dir, mine in ((a, "j2-20261104-100004-aaaa"), (b, "j2-20261104-100004-bbbb")):
        rows = events(run_dir)
        assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items")
        assert {u["call_ref"].split(":")[0] for u in of(rows, "usage") if not u["call_ref"].startswith("r:")} == {mine}
    assert (json.loads((a / "settings.json").read_text())["budget"], json.loads((b / "settings.json").read_text())["budget"]) == (95, 120)
    assert json.loads((a / "summary.json").read_text())["budget"]["start"] == 95, "each process has its own J2 constants"
    assert json.loads((b / "summary.json").read_text())["budget"]["start"] == 120
    assert json.loads((a / "summary.json").read_text())["realization"]["applied"] is True
    assert "realization" not in json.loads((b / "summary.json").read_text())
    memory = {d: sorted(p.name for p in (data_dir / "departments" / d / "memory").glob("*")) for d in ("web", "docs")}
    assert memory["web"] and memory["docs"], "each department keeps its own memory folder"
    for dept, other_run in (("web", "bbbb"), ("docs", "aaaa")):
        for path in (data_dir / "departments" / dept / "memory").glob("*"):
            assert other_run not in path.read_text(), "no lesson of the other department"
    assert sorted(p.name for p in data_dir.iterdir() if p.name != "departments") == ["library"]


def test_the_command_line_is_checked_before_anything_runs(tmp_path):
    base = {**{k: v for k, v in os.environ.items() if not k.startswith(("J2_", "SUTRA_"))}, "PYTHONPATH": str(ROOT)}
    missing = subprocess.run([sys.executable, "-m", "sutra_app.engine"], env=base, capture_output=True, text=True, cwd=tmp_path)
    assert missing.returncode == 2 and "--run-dir" in missing.stderr
    nowhere = tmp_path / "departments" / "web" / "runs" / "j2-20261104-100004-7f3a"
    gone = subprocess.run([sys.executable, "-m", "sutra_app.engine", "--run-dir", str(nowhere), "--mock"], env=base,
                          capture_output=True, text=True, cwd=tmp_path)
    assert gone.returncode == 2 and "could not start: the run directory does not exist" in gone.stderr and gone.stdout == ""
    assert not nowhere.exists(), "the engine never creates its run directory"
    assert jsonl(tmp_path / "none") == []
