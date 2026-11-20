"""B1: nothing a node's run folder holds, and nothing the node state machine trips over, can undo a task's own change or stop the app. A poisoned hand-off is a refusal, an unexpected error
ends the node `failed` (never retried) and the task still ends, a retry for an archived team ends the node cleanly, and stop and reconcile still work afterwards."""
import json
import os

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def two(rig, retries=0):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', ?) WHERE id = ?", retries, reservation.project_id)
    rig.start()
    rig.go(tasks["a1"])
    return reservation, tasks


def node(rig, ref):
    return rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()


def still_works(rig, reservation):
    """Stop and reconcile run without an error afterwards, as they do at the next start of the app."""
    assert isinstance(rig.t.run(rig.projects.reconcile_projects()), dict)
    rig.t.run(rig.projects.stop(reservation.project_id))
    assert rig.project(reservation.project_id)["status"] in ("stopped", "failed", "done_with_open_items")


POISON = {
    "deep": lambda rig, tasks: {"handoff.json": "[" * 30_000},
    "bytes": lambda rig, tasks: {"handoff.json": b"\xff\xfe\x00{"},
    "lone_surrogate": lambda rig, tasks: {"handoff.json": json.dumps({"v": 1, "node_id": node(rig, "a1")["id"], "status": "done", "summary": "x\ud800y", "files": [], "claims": [], "needs": []})},
    "lone_surrogate_in_a_claim": lambda rig, tasks: {"handoff.json": json.dumps({"v": 1, "node_id": node(rig, "a1")["id"], "status": "done", "summary": "ok", "files": [], "claims": ["\udfff"],
                                                                              "needs": []})},
}


@pytest.mark.parametrize("name", sorted(POISON))
def test_a_poisoned_hand_off_is_a_refusal_the_task_still_ends_and_the_dependant_is_cancelled(rig, name):
    reservation, tasks = two(rig)
    rig.finish(tasks["a1"], handoff=False, files=POISON[name](rig, tasks))
    assert rig.t.status(tasks["a1"]) == "done"                                                         # the task's own end was recorded
    assert node(rig, "a1")["state"] == "failed" and rig.t.status(tasks["a2"]) == "cancelled"
    assert [r["action"] for r in rig.audit("handoff.refused")] == ["handoff.refused"] and rig.audit("node.error") == []
    still_works(rig, reservation)


def test_a_path_that_cannot_be_compared_is_a_refusal_not_an_exception(rig, monkeypatch):
    reservation, tasks = two(rig)
    (rig.t.run_dir(tasks["a1"]) / "out.md").write_text("x")
    monkeypatch.setattr(os.path, "commonpath", lambda paths: (_ for _ in ()).throw(ValueError("Paths don't have the same drive")))
    rig.finish(tasks["a1"])                                                                           # a good hand-off listing out.md
    assert node(rig, "a1")["state"] == "failed" and rig.audit("handoff.refused")[0]["reason"] == "a listed file leaves the run folder"


def test_an_unexpected_error_in_the_state_machine_ends_the_node_failed_without_a_retry_and_the_task_still_ends(rig, monkeypatch):
    reservation, tasks = two(rig, retries=1)

    def boom(*args, **kwargs):
        raise RuntimeError("a bug that must not take the task with it")
    monkeypatch.setattr(rig.projects.conductor, "_hand_off", boom)
    rig.finish(tasks["a1"])
    assert rig.t.status(tasks["a1"]) == "done" and node(rig, "a1")["state"] == "failed" and node(rig, "a1")["attempt"] == 1
    assert rig.sql("SELECT count(*) FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0] == 1 and rig.t.status(tasks["a2"]) == "cancelled"
    error = rig.audit("node.error")
    assert len(error) == 1 and error[0]["decision"] == "deny" and "RuntimeError" not in error[0]["reason"] and "bug" not in error[0]["reason"]
    still_works(rig, reservation)


def test_a_retry_for_an_archived_team_ends_the_node_cleanly(rig):
    reservation, tasks = two(rig, retries=1)
    rig.sql("UPDATE org_nodes SET state = 'archived' WHERE id = 'web'")
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)
    assert rig.t.status(tasks["a1"]) == "crashed" and node(rig, "a1")["state"] == "failed" and node(rig, "a1")["attempt"] == 1
    assert "could not be tried again" in node(rig, "a1")["failure_reason"] and rig.audit("node.error") == [] and rig.t.status(tasks["a2"]) == "cancelled"
    assert rig.project(reservation.project_id)["status"] == "failed"
    still_works(rig, reservation)


def test_a_failed_part_of_the_transaction_leaves_no_half_written_rows_and_no_events(db, clock):
    from sutra_app.orchestrator.db import Database  # noqa: F401
    with db.tx() as tx:
        tx.conn.execute("CREATE TABLE IF NOT EXISTS scratch(x INTEGER)")
        tx.conn.execute("INSERT INTO scratch VALUES (1)")
        with pytest.raises(ValueError):
            with tx.savepoint():
                tx.conn.execute("INSERT INTO scratch VALUES (2)")
                tx.emit("scratch.touched", {})
                raise ValueError("part failed")
        tx.conn.execute("INSERT INTO scratch VALUES (3)")
        assert [e.type for e in tx.pending] == []
    assert [r[0] for r in db.conn().execute("SELECT x FROM scratch ORDER BY x")] == [1, 3]


# ---- the hand-off's files are read and written before the transaction opens (MJ5) -----------------------------------------------------

def test_the_hand_off_is_read_hashed_and_written_before_the_projectors_transaction_opens(rig, monkeypatch):
    from sutra_app.orchestrator import conductor
    seen = {"read": [], "write": []}
    real_read, real_write = conductor.read_handoff, conductor.write_accepted

    def read(*args, **kwargs):
        seen["read"].append(rig.t.db._local.depth)                                                   # 0: no transaction is open on this thread
        return real_read(*args, **kwargs)

    def write(*args, **kwargs):
        seen["write"].append(rig.t.db._local.depth)
        return real_write(*args, **kwargs)
    monkeypatch.setattr(conductor, "read_handoff", read)
    monkeypatch.setattr(conductor, "write_accepted", write)
    reservation, tasks = two(rig)
    rig.finish(tasks["a1"], files={"out.md": "result"})
    assert seen == {"read": [0], "write": [0]}                                                       # once each, never inside the transaction, and not again inside it
    assert node(rig, "a1")["state"] == "done" and (rig.t.run_dir(tasks["a1"]) / "handoff.accepted.json").is_file()
    assert [r["action"] for r in rig.audit("handoff.accepted")] == ["handoff.accepted"]


def test_a_refusal_found_before_the_transaction_is_the_refusal_the_transaction_records(rig):
    reservation, tasks = two(rig)
    rig.finish(tasks["a1"], files={"out.md": "result"}, override={"files": [{"path": "out.md", "sha256": "0" * 64, "bytes": 6}]})
    assert node(rig, "a1")["state"] == "failed" and rig.audit("handoff.refused")[0]["reason"] == "a listed file does not match its checksum"


def test_a_hand_off_that_changed_after_it_was_prepared_is_read_again_inside(rig):
    reservation, tasks = two(rig)
    run_dir = rig.t.run_dir(tasks["a1"])
    (run_dir / "out.md").write_text("result")
    from sutra_app.engine.host import handoff as handoff_file
    handoff_file.write(run_dir, handoff_file.build(run_dir, node(rig, "a1")["id"], "done", "first"))
    rig.projects.prepare_handoff(tasks["a1"])                                                         # prepared for the first file
    handoff_file.write(run_dir, handoff_file.build(run_dir, node(rig, "a1")["id"], "done", "second and longer"))
    rig.finish(tasks["a1"], handoff=False)
    assert json.loads((run_dir / "handoff.accepted.json").read_text())["handoff"]["summary"] == "second and longer"


# ---- the contained error also stops the task (M3) ------------------------------------------------------------------------------------------

def test_a_node_failed_closed_while_its_task_is_starting_leaves_no_process_behind(rig, monkeypatch):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    real = rig.projects.conductor._sync_task

    def break_on_start(tx, task_id):
        if task_id == tasks["a1"] and rig.t.row(task_id).status == "starting":
            raise RuntimeError("the state machine broke while the task was starting")
        return real(tx, task_id)
    monkeypatch.setattr(rig.projects.conductor, "_sync_task", break_on_start)
    rig.start()
    assert node(rig, "a1")["state"] == "failed"
    assert tasks["a1"] not in {s.task_id for s, *_ in rig.t.launcher.started}                      # the guard refused the start: no process began
    assert rig.t.status(tasks["a1"]) == "stopped"
    assert tasks["a2"] in {s.task_id for s, *_ in rig.t.launcher.started}                          # the other step was not touched


def test_a_node_failed_closed_while_its_task_runs_has_that_task_stopped_by_the_next_tick(rig):
    reservation, tasks = two(rig)                                                                   # a1 runs
    with rig.t.db.tx() as tx:
        rig.projects.conductor._fail_closed(tx, tasks["a1"])
    assert node(rig, "a1")["state"] == "failed" and rig.projects.conductor._stop_tasks == [tasks["a1"]] and rig.t.status(tasks["a1"]) == "running"
    rig.t.run(rig.projects.tick(now=1793786400 + 5))
    assert rig.t.status(tasks["a1"]) == "stopped" and rig.projects.conductor._stop_tasks == [] and rig.t.launcher.stopped
