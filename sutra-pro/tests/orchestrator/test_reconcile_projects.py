"""`reconcile_projects` (MAN-7; D277, D296): after `reconcile` has settled the tasks, the nodes follow them, leases start again, a node is never started twice, and a project whose gate was left open by a
closed app is refused. The existing `reconcile` is not changed."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.nodes_store import GATE_REFUSED_CLOSED

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def running(rig, steps):
    reservation, tasks = rig.request(steps)
    rig.start()
    for task_id in tasks.values():
        if rig.t.status(task_id) == "starting":
            rig.go(task_id)
    return reservation, tasks


def reconcile(rig):
    return rig.t.run(rig.projects.reconcile_projects())


def test_a_restart_with_a_live_node_readopts_it_and_the_lease_starts_again_from_now(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("UPDATE agent_nodes SET lease_expires_at = 5, last_beat_at = 1")                           # the old lease means nothing after a restart
    now = rig.t.clock.peek
    assert reconcile(rig) == {"refused": 0, "cancelled": 0}
    node = rig.node_of(tasks["a1"])
    assert node["state"] == "running" and node["lease_expires_at"] > now and node["last_beat_at"] >= now
    assert rig.t.status(tasks["a1"]) == "running" and rig.t.launcher.started and len(rig.t.launcher.started) == 1             # nothing was started again


def test_a_task_that_reconcile_crashed_gives_a_node_that_is_retried_and_a_node_never_starts_twice(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET status = 'crashed', outcome = 'the app was closed while it ran' WHERE id = ?", tasks["a1"])         # what `reconcile` does to a task with no process
    reconcile(rig)
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["attempt"] == 2 and node["state"] == "queued" and rig.t.row(node["task_id"]).parent_task_id == tasks["a1"]
    assert reconcile(rig) == {"refused": 0, "cancelled": 0} and rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == 3         # a second pass changes nothing
    started = rig.start()
    assert started == [node["task_id"]] and rig.start() == []                                         # the retry starts once, and only once


def test_a_task_that_ended_while_the_app_was_down_settles_its_node_and_the_project(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    from sutra_app.engine.host import handoff
    for ref in ("a1", "a2"):
        run_dir = rig.t.run_dir(tasks[ref])
        handoff.write(run_dir, handoff.build(run_dir, rig.node_of(tasks[ref])["id"], "done", "ok"))
        rig.sql("UPDATE tasks SET status = 'done', outcome = 'ok' WHERE id = ?", tasks[ref])
    reconcile(rig)
    assert rig.node_states(tasks) == {"a1": "done", "a2": "done"} and rig.project(reservation.project_id)["status"] == "done"
    assert len(rig.store.messages(reservation.project_id)) == 2                                         # the hand-offs that were waiting were taken in


def test_a_node_that_was_reserved_but_never_got_its_task_is_cancelled(rig):
    from sutra_app.orchestrator.projects import ProjectStep
    reservation = rig.projects.reserve("req-cut", "cut off", [ProjectStep("a1", "web"), ProjectStep("a2", "sales")])
    assert reservation.ok and rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == 0                   # the app died between the reservation and the tasks
    assert reconcile(rig) == {"refused": 0, "cancelled": 2}
    assert {n["state"] for n in rig.sql("SELECT state FROM agent_nodes")} == {"cancelled"} and rig.project(reservation.project_id)["status"] == "failed"
    assert "cut off" in rig.sql("SELECT failure_reason FROM agent_nodes").fetchone()[0]


def test_a_project_that_has_ended_or_a_node_that_has_is_left_alone(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    for ref in ("a1", "a2"):
        rig.finish(tasks[ref])
    before = [tuple(r) for r in rig.sql("SELECT * FROM agent_nodes ORDER BY id")]
    assert reconcile(rig) == {"refused": 0, "cancelled": 0} and [tuple(r) for r in rig.sql("SELECT * FROM agent_nodes ORDER BY id")] == before


def test_a_project_with_an_open_gate_is_refused_on_restart_with_the_closed_words(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    with rig.t.db.tx() as tx:
        rig.store.open_approval(tx, project_id=reservation.project_id, node_id=rig.node_of(tasks["a2"])["id"], tier=4, request={"why": "read GitHub"}, expires_at=BASE + 86_400)
    assert reconcile(rig) == {"refused": 1, "cancelled": 0}
    assert rig.project(reservation.project_id)["status"] == "stopped" and rig.project(reservation.project_id)["stop_reason"] == GATE_REFUSED_CLOSED
    assert {a.status for a in rig.store.approvals(reservation.project_id)} == {"denied"}
    assert rig.node_states(tasks) == {"a1": "cancelled", "a2": "cancelled"}                              # the running node was stopped through the ladder, the waiting one cancelled
    assert [r["action"] for r in rig.audit("gate.refused")] == ["gate.refused"] and rig.audit("gate.refused")[0]["reason"] == GATE_REFUSED_CLOSED
    assert rig.sql("SELECT text FROM chat_messages WHERE src_ref = ?", f"project:{reservation.project_id}#stopped").fetchone()["text"].startswith("I stopped the project")


# ---- an app that was closed is not a node that failed (D314) ----------------------------------------------------------------------------

def app_closed_under(rig, ref):
    """What `reconcile` leaves of a node's task when the app was closed under it, then the node follows its task."""
    node = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()
    rig.sql("UPDATE tasks SET status = 'crashed', outcome = 'the app was closed while it ran' WHERE id = ?", node["task_id"])
    reconcile(rig)
    return rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()


def test_a_node_found_dead_because_the_app_closed_gets_a_fresh_attempt_that_does_not_spend_its_one_retry(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    node = app_closed_under(rig, "a1")
    assert node["attempt"] == 2 and node["state"] == "queued" and [r["action"] for r in rig.audit("node.restarted")] == ["node.restarted"] and rig.audit("node.retry") == []
    rig.start()
    rig.go(node["task_id"])
    rig.finish(node["task_id"], status="crashed", outcome="it really crashed", handoff=False)         # now a real failure: the one retry is still there
    again = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert again["attempt"] == 3 and again["state"] in ("queued", "leased") and [r["action"] for r in rig.audit("node.retry")] == ["node.retry"]
    rig.start()
    rig.go(again["task_id"])
    rig.finish(again["task_id"], status="crashed", outcome="and again", handoff=False)               # the retry is used: the node fails and the project goes on without it
    assert rig.sql("SELECT state FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0] == "failed"


def test_the_restart_attempts_of_a_node_are_capped_at_two(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)         # no ordinary retry: only restart attempts remain
    for expected in (2, 3):
        node = app_closed_under(rig, "a1")
        assert node["attempt"] == expected and node["state"] == "queued"
        rig.start()
        rig.go(node["task_id"])
    node = app_closed_under(rig, "a1")                                                                  # the third close: the cap is reached
    assert node["state"] == "failed" and node["attempt"] == 3 and len(rig.audit("node.restarted")) == 2
    assert "app was closed" in node["failure_reason"]


def test_a_node_that_was_stopped_by_the_closing_of_the_app_is_a_restart_too_and_a_stop_by_the_owner_is_not(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET status = 'stopped', outcome = 'the app was closed' WHERE id = ?", tasks["a1"])         # app shutdown ends a live task as stopped
    rig.sql("UPDATE tasks SET status = 'stopped', outcome = 'stopped by you' WHERE id = ?", tasks["a2"])
    reconcile(rig)
    assert rig.sql("SELECT attempt, state FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[:] == (2, "queued")
    assert rig.sql("SELECT attempt, state FROM agent_nodes WHERE plan_ref = 'a2'").fetchone()[:] == (1, "cancelled")
