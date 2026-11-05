"""Live runs through the real connector layer (work package E3, engine design 9). They carry the `live` marker and run only with
SUTRA_LIVE=1 (the merge gate skips them); they need the connector layer's `engine_port` and a signed-in `claude` or `codex`.

    SUTRA_LIVE=1 scripts/py -m pytest tests/engine/test_engine_live.py -q -m live
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BRIEF = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru, open 8am to 8pm every day at "
         "12 Church Street. Show a short menu (espresso 120, latte 160, filter coffee 90 rupees) and where to find us. Warm and "
         "simple, and it must work on a phone.")


def rows_of(run_dir: Path) -> list:
    path = run_dir / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def live_run(run_dir: Path, answers=("Option 1: keep going.",), timeout: float = 900.0) -> subprocess.Popen:
    """Start the real engine (no --mock), answer its questions from `answers`, stop it if it is still waiting at the end."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("STUDIO_", "SUTRA_MOCK", "SUTRA_OFFLINE"))}
    env.update({"PYTHONPATH": str(ROOT), "J2_MAX_CYCLES": "1"})
    proc = subprocess.Popen([sys.executable, "-m", "sutra_app.engine", "--run-dir", str(run_dir)], env=env, cwd=str(run_dir.parent),
                            stdout=open(run_dir / "run.stdout.log", "ab"), stderr=open(run_dir / "run.stderr.log", "ab"),
                            start_new_session=True)
    sent, deadline = 0, time.time() + timeout
    while proc.poll() is None and time.time() < deadline:
        asks = [e for e in rows_of(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"]
        if len(asks) > sent:
            sent += 1
            kind, fields = ("user", {"text": answers[min(sent - 1, len(answers) - 1)]}) if sent <= len(answers) else ("stop", {})
            with open(run_dir / "inbox.jsonl", "a") as f:
                f.write(json.dumps({"n": sent, "kind": kind, **fields}) + "\n")
        time.sleep(0.5)
    if proc.poll() is None:
        proc.kill()
        pytest.fail("the live run did not finish in time")
    return proc


@pytest.fixture(scope="module")
def first_run(tmp_path_factory):
    if not (shutil.which("claude") or shutil.which("codex")):
        pytest.skip("neither the claude nor the codex CLI is installed")
    pytest.importorskip("sutra_app.connectors.engine_port")
    data = tmp_path_factory.mktemp("live-data")
    run_dir = data / "departments" / "web" / "runs" / "j2-20261104-100004-live"
    run_dir.mkdir(parents=True)
    (run_dir / "task.json").write_text(json.dumps({
        "schema": "run-spec/1", "run_id": run_dir.name, "task_id": "tsk_live00000001", "dept_id": "web", "user_text": BRIEF,
        "settings": {"J2_BUDGET": "100"}, "connector": "auto"}))
    for name in ("inbox.jsonl", "events.jsonl"):
        (run_dir / name).touch()
    proc = live_run(run_dir)
    return run_dir, proc


def test_a_short_real_run_goes_through_the_connector_layer(first_run):
    run_dir, proc = first_run
    rows = rows_of(run_dir)
    assert proc.returncode == 0 and rows[0]["t"] == "run.started" and rows[0]["mock"] is False
    assert rows[-1]["t"] == "run.ended"
    usage = [e for e in rows if e["t"] == "usage"]
    assert usage and all(u["provider"] in ("claude", "codex") and u["atom"] for u in usage), "real providers, every call charged to an atom"
    assert any(e["t"] == "say" for e in rows) and (run_dir / "snapshot.json").exists()


def test_a_follow_up_is_rehydrated_and_runs_with_a_real_model(first_run):
    old, _ = first_run
    if rows_of(old)[-1].get("status") not in ("done", "done_with_open_items"):
        pytest.skip("the first live run did not finish, so there is nothing to continue")
    new = old.parent / "j2-20261104-110000-live"
    new.mkdir()
    (new / "task.json").write_text(json.dumps({
        "schema": "run-spec/1", "run_id": new.name, "task_id": "tsk_live00000002", "dept_id": "web", "seed_from": old.name,
        "user_text": "Add the loyalty card: buy 9 coffees, get the 10th free.", "settings": {}, "connector": "auto"}))
    for name in ("inbox.jsonl", "events.jsonl"):
        (new / name).touch()
    proc = live_run(new)
    rows = rows_of(new)
    assert proc.returncode == 0 and rows[0]["seed"] == "rehydrated"
    assert rows[-1]["status"] in ("done", "done_with_open_items"), \
        "if it pauses, add the condition realization == 0 back in rehydrate.py (engine design 9)"
