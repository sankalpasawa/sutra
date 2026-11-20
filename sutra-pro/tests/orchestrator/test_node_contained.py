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
