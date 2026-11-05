"""Scenario 5 (GAP-E2E, G05): several teams at once under `max_runs=2`.

Three departments, each with a Brew Lab task (a full brief: no question, so the runs only work). Two engine processes run at the
same time, the third task queues and starts the moment a slot frees, a second task for a busy team waits behind its first (one
live task per department), and when everything is Done the atom, usage and ledger tables agree with each run's own event file.
Runs are slowed (`STUDIO_MOCK_DELAY`) so that they really overlap.
"""
import time

import pytest
from harness import BREW_LAB, TERMINAL, LiveApp
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

LIVE = ("starting", "running", "waiting_user")
WORKING = ("starting", "running")


@pytest.fixture(scope="module")
def parallel(tmp_path_factory):
    live = LiveApp(tmp_path_factory.mktemp("parallel"), connector=ScriptedConnector(), max_runs=2, mock_delay=0.08).start()
    try:
        for dept in ("alpha", "beta", "gamma"):
            live.add_department(dept, dept.title(), f"{dept} pages")
        tasks = {dept: live.give_task(dept, BREW_LAB, f"{dept} page") for dept in ("alpha", "beta", "gamma")}
        again = live.give_task("alpha", BREW_LAB + " Add a loyalty section.", "alpha second")
        peak, snapshots = 0, []
        while True:
            status = {r["id"]: r["status"] for r in live.rows("SELECT id, status FROM tasks")}
            peak = max(peak, sum(1 for s in status.values() if s in WORKING))
            snapshots.append(dict(status))
            if all(s in TERMINAL for s in status.values()):
                break
            assert len(snapshots) < 4000, status
            time.sleep(0.02)
        yield {"live": live, "tasks": tasks, "again": again, "peak": peak, "snapshots": snapshots}
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


def test_two_engines_run_at_once_and_never_more_than_max_runs(parallel):
    live = parallel["live"]
    assert live.get("/api/config")["max_runs"] == 2
    assert parallel["peak"] == 2                                                         # they did overlap, and never three
    for snapshot in parallel["snapshots"]:
        assert sum(1 for s in snapshot.values() if s in WORKING) <= 2


def test_the_third_team_queues_and_starts_when_a_slot_frees(parallel):
    t = parallel["tasks"]
    queued_while = [s for s in parallel["snapshots"] if s[t["gamma"]] == "queued" and sum(1 for v in s.values() if v in WORKING) == 2]
    assert queued_while                                                                   # it waited because both slots were taken
    live = parallel["live"]
    started = {task: live.task_row(task)["started_at"] for task in t.values()}
    ended = {task: live.task_row(task)["ended_at"] for task in t.values()}
    assert started[t["gamma"]] >= min(ended[t["alpha"]], ended[t["beta"]])               # started after one of the first two ended
    assert [live.task_status(task) for task in t.values()] == ["done"] * 3


def test_one_live_task_per_department_the_second_alpha_task_waits_for_the_first(parallel):
    live, t = parallel["live"], parallel["tasks"]
    for snapshot in parallel["snapshots"]:
        assert not (snapshot[t["alpha"]] in LIVE and snapshot[parallel["again"]] in LIVE)
    live_per_dept = live.rows("SELECT dept_id, count(*) n FROM tasks WHERE status IN ('starting','running','waiting_user') GROUP BY dept_id")
    assert all(r["n"] == 1 for r in live_per_dept)
    first, second = live.task_row(t["alpha"]), live.task_row(parallel["again"])
    assert live.task_status(parallel["again"]) == "done" and second["started_at"] >= first["ended_at"]
    assert first["run_id"] != second["run_id"] and first["pid"] != second["pid"]


def test_atom_usage_and_ledger_tables_agree_with_every_runs_own_events(parallel):
    live = parallel["live"]
    tasks = [*parallel["tasks"].values(), parallel["again"]]
    for task in tasks:
        row = live.task_row(task)
        events = live.events_of(task)
        assert row["events_offset"] == (live.run_dir(task) / "events.jsonl").stat().st_size
        usage = [e for e in events if e["t"] == "usage"]
        rows = live.rows("SELECT call_ref, dept_id, atom_id FROM usage_ledger WHERE task_id = ?", task)
        assert len(rows) == len(usage) > 10 and {r["dept_id"] for r in rows} == {row["dept_id"]}      # no row on the wrong team
        assert all(r["atom_id"] for r in rows)
        atoms = live.rows("SELECT department_id, node_id, display FROM atoms WHERE task_id = ?", task)
        assert atoms and {a["department_id"] for a in atoms} == {row["dept_id"]}
        assert all(a["node_id"].startswith(row["dept_id"] + ".") or a["node_id"].startswith("s-") for a in atoms)
        assert all(a["display"] != "open" for a in atoms)
    assert live.one("SELECT count(*) FROM atom_ledger") == live.one("SELECT count(*) FROM atoms")
    assert live.one("SELECT count(*) FROM usage_ledger WHERE task_id IS NULL") == 0
    assert live.one("SELECT count(*) FROM usage_ledger") == sum(
        sum(1 for e in live.events_of(task) if e["t"] == "usage") for task in tasks)
    assert len(live.cards("done")) == 4 and {c["status"] for c in live.cards("done")} == {"done"}
    for dept in ("alpha", "beta", "gamma"):
        assert live.one("SELECT state FROM graph_nodes WHERE id = ?", dept) == "idle"
