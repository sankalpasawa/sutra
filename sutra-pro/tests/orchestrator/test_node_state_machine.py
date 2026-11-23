"""Cases of the node state machine that had no test of their own (MJ6): the dependants of a refused hand-off, the one-time lease extension, the gate holding an ended project, a node in a final
state never moving, a kill that has nothing running, and what a message's text body is scrubbed of."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def node(rig, ref):
    return rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = ?", ref).fetchone()


def tick(rig, seconds):
    return rig.t.run(rig.projects.tick(now=BASE + seconds))


def test_the_dependants_of_a_node_whose_hand_off_is_refused_are_cancelled_not_started(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"]), ("a3", "ops", ["a2"]), ("a4", "hr", [])])
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], handoff=False)                                                  # the task ended well, the node left no hand-off
    assert node(rig, "a1")["state"] == "failed" and rig.audit("handoff.refused")
    assert rig.t.status(tasks["a2"]) == "cancelled" and rig.t.status(tasks["a3"]) == "cancelled" and rig.start() == []
    assert node(rig, "a2")["state"] == "cancelled" and node(rig, "a3")["state"] == "cancelled" and node(rig, "a4")["state"] in ("leased", "running", "queued")


def test_a_second_sleep_does_not_extend_the_lease_again_the_node_is_then_a_dead_one(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    for task_id in tasks.values():
        rig.go(task_id)
    tick(rig, 10)
    assert len(tick(rig, 2000)["extended"]) == 2                                              # the first sleep: extended once
    again = tick(rig, 5000)                                                                    # a second sleep right after: the one extension is used
    assert again["extended"] == [] and sorted(again["expired"]) == sorted(tasks.values())


def test_the_gate_holds_a_node_of_an_ended_project_and_says_so(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET status = 'failed' WHERE id = ?", reservation.project_id)
    assert "this project has ended" in rig.projects.gate(rig.t.db.conn(), BASE, rig.t.row(tasks["a1"]))
    assert rig.start() == [] and "has ended" in rig.detail(tasks["a1"])


@pytest.mark.parametrize("final", ["done", "failed", "cancelled"])
def test_a_node_in_a_final_state_never_moves_again(rig, final):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE agent_nodes SET state = ?, ended_at = 5 WHERE plan_ref = 'a1'", final)
    for status in ("running", "queued", "crashed", "done"):
        rig.sql("UPDATE tasks SET status = ? WHERE id = ?", status, tasks["a1"])
        with rig.t.db.tx() as tx:
            rig.projects.sync_task(tx, tasks["a1"])
        assert node(rig, "a1")["state"] == final


def test_a_kill_with_nothing_running_cancels_the_queued_and_blocked_nodes_on_its_own(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"]), ("a3", "ops", [])])
    assert rig.t.status(tasks["a1"]) == "queued" and rig.t.status(tasks["a2"]) == "blocked"            # nothing was started
    ids = rig.projects.begin_kill("stopped by the kill switch")
    assert ids == [reservation.project_id] and rig.project(reservation.project_id)["status"] == "stopped"
    cancelled = rig.t.run(rig.projects.finish_kill(ids, "stopped by the kill switch"))
    assert cancelled == 3 and {rig.t.status(t) for t in tasks.values()} == {"cancelled"}
    assert set(rig.node_states(tasks).values()) == {"cancelled"} and rig.t.run(rig.projects.finish_kill(ids, "again")) == 0


def test_a_text_body_of_a_message_is_scrubbed_like_a_json_one(db, ids):
    from sutra_app.orchestrator.nodes_store import NodeStore
    from sutra_app.orchestrator.redact import Redactor
    secret = "the-launch-token-0123456789"
    project = "prj_" + "a" * 12
    db.conn().execute("INSERT INTO projects(id, created_at) VALUES (?, 1)", (project,))
    store = NodeStore(db, ids=ids, redact=Redactor(extra=[secret], environ={}))
    with db.tx() as tx:
        posted = store.post(tx, project_id=project, kind="status", src_ref="s:1", body=f"the token is {secret} and a key sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789")
    assert secret not in posted.body and "sk-ant-api03" not in posted.body and "[redacted" in posted.body
    assert secret not in store.messages(project)[0].body


# ---- the API cannot try a step again by hand (D398, M-A) ------------------------------------------------------------------------------------------

def test_a_step_is_refused_a_retry_by_hand_with_a_plain_409_and_makes_no_task(db, settings, clock, events):
    from orchestrator.projects_rig import PRig
    from sutra_app.orchestrator.errors import Busy
    rig = PRig(db, settings, clock, events, max_runs=5, max_live=10)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)          # the project's own retry makes attempt 2
    current = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]
    rig.sql("UPDATE tasks SET status = 'crashed', ended_at = ? WHERE id = ?", 1793786500, current)
    before = rig.sql("SELECT count(*) FROM tasks").fetchone()[0]
    for task_id in {tasks["a1"], current}:                                                  # the first attempt and the current one
        with pytest.raises(Busy) as refused:
            rig.t.run(rig.t.service.retry(task_id))
        assert refused.value.status == 409 and "tried again by its project" in refused.value.message
    assert rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == before


def test_an_ordinary_task_is_still_retried_by_hand(db, settings, clock, events):
    from orchestrator.projects_rig import PRig
    rig = PRig(db, settings, clock, events, max_runs=5, max_live=10)
    plain = rig.t.new("ops", "an ordinary task")
    rig.sql("UPDATE tasks SET status = 'crashed', ended_at = ? WHERE id = ?", 1793786500, plain.id)
    assert rig.t.run(rig.t.service.retry(plain.id)).parent_task_id == plain.id
