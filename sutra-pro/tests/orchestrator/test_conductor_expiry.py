"""Leases, retries and the failure policy (MAN-7; D275, D277, D278, D303 e, D305 c): a silent node is stopped through the ladder and retried once, a computer that slept is not a dead node,
a crash is retried once, the owner's stop is never retried, and `stop_branch` / `stop_all` decide what a failure costs the project. Real scheduler, `FakeLauncher`, an injected `now`."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

BASE = 1793786400                         # the second the fake events are stamped with (2026-11-04 10:00:00 UTC)


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def running(rig, steps):
    reservation, tasks = rig.request(steps)
    rig.start()
    for ref, task_id in tasks.items():
        if rig.t.status(task_id) == "starting":
            rig.go(task_id)
    return reservation, tasks


def tick(rig, seconds):
    return rig.t.run(rig.projects.tick(now=BASE + seconds))


# ---- a silent node ------------------------------------------------------------------------------------------------------------------

def test_a_node_silent_past_its_lease_gets_the_ladder_and_one_retry_and_its_dependant_waits_for_the_new_attempt(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    assert tick(rig, 90) == {"expired": [], "refused": [], "stopped": [], "extended": []}                  # exactly the lease: still alive
    done = tick(rig, 100)
    assert done["expired"] == [tasks["a1"]] and rig.t.launcher.stopped == [rig.t.row(tasks["a1"]).pid]
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["attempt"] == 2 and node["state"] in ("queued", "leased") and node["task_id"] != tasks["a1"]          # the retry may already have started: the ladder's own start_ready
    new = node["task_id"]
    assert rig.t.row(new).parent_task_id == tasks["a1"] and rig.t.status(tasks["a1"]) == "stopped"
    assert json.loads(rig.sql("SELECT depends_on FROM tasks WHERE id = ?", tasks["a2"]).fetchone()[0]) == [new]          # the dependant waits for the new attempt
    assert rig.t.status(tasks["a2"]) == "blocked"
    actions = [r["action"] for r in rig.audit()]
    assert {"node.heartbeat_lost", "node.expired", "node.retry"} <= set(actions)


def test_the_retry_runs_and_the_project_goes_on_as_if_nothing_happened(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    tick(rig, 100)
    first = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]
    assert first != tasks["a1"] and rig.t.status(first) in ("starting", "running")                        # the ladder freed the team and the retry started by itself
    rig.go(first)
    rig.finish(first)
    assert rig.node_states({"a1": first})["a1"] == "done" and rig.t.status(tasks["a2"]) == "queued"
    rig.start()
    rig.go(tasks["a2"])
    rig.finish(tasks["a2"])
    assert rig.project(reservation.project_id)["status"] == "done"


def test_an_event_extends_the_lease_so_a_chatty_node_is_never_expired(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.t.sql("UPDATE tasks SET last_event_at = ? WHERE id = ?", BASE + 80, tasks["a1"])
    assert tick(rig, 150)["expired"] == [tasks["a2"]]                                                   # a1 spoke at +80: 70 s ago is fine; a2 has been silent 150 s
    assert rig.node_of(tasks["a1"])["lease_expires_at"] == BASE + 80 + 90 and rig.node_of(tasks["a1"])["last_beat_at"] == BASE + 80


def test_a_computer_that_slept_extends_the_lease_once_and_is_not_a_dead_node(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    tick(rig, 10)
    woke = tick(rig, 2000)                                                                              # the tick itself came 1990 s late: the machine slept
    assert sorted(woke["extended"]) == sorted(r["id"] for r in rig.sql("SELECT id FROM agent_nodes").fetchall()) and woke["expired"] == [] and rig.t.launcher.stopped == []
    assert rig.node_of(tasks["a1"])["lease_expires_at"] == BASE + 2000 + 90 and [r["action"] for r in rig.audit("node.lease_extended")] == ["node.lease_extended"] * 2
    assert tick(rig, 2030)["expired"] == [] and tick(rig, 2070)["expired"] == []                         # the extended lease (until +2090) is still good
    assert sorted(tick(rig, 2095)["expired"]) == sorted(tasks.values())                                  # silent past it, and the one extension is used: now they are dead nodes


def test_a_node_that_loses_its_lease_twice_stops_the_project_and_says_why(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    tick(rig, 100)                                                                                      # the first loss of a1 and a2: both retried and started
    for row in rig.sql("SELECT task_id FROM agent_nodes").fetchall():
        rig.go(row["task_id"])
        rig.t.sql("UPDATE tasks SET last_event_at = ? WHERE id = ?", BASE + 100, row["task_id"])
    for at in (135, 170):                                                                               # ticks close together: no sleep is suspected, and 70 s of silence is inside the lease
        assert tick(rig, at)["expired"] == []
    chatty = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a2'").fetchone()[0]
    rig.t.sql("UPDATE tasks SET last_event_at = ? WHERE id = ?", BASE + 185, chatty)                    # a2 is still talking; only a1 goes silent a second time
    done = tick(rig, 191)                                                                               # 91 s of silence: the second loss of a1
    assert len(done["expired"]) == 1, done
    assert "a step lost contact with Sutra twice" in rig.project(reservation.project_id)["stop_reason"] and rig.project(reservation.project_id)["status"] == "stopped"
    assert [r["action"] for r in rig.audit("trigger.lease_lost")] == ["trigger.lease_lost"] * len(done["expired"])
    assert {n["plan_ref"]: n["state"] for n in rig.sql("SELECT plan_ref, state FROM agent_nodes")} == {"a1": "failed", "a2": "cancelled"}


# ---- crashes, hand-offs and the owner's stop ----------------------------------------------------------------------------------------

def test_a_crash_is_retried_once_then_the_node_fails_and_only_its_dependants_are_cancelled(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", []), ("a3", "ops", ["a1"]), ("a4", "hr", ["a2"])])
    rig.finish(tasks["a1"], "crashed", "it broke")
    retry = rig.node_of(rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0])
    assert retry["attempt"] == 2 and retry["state"] == "queued" and rig.t.status(tasks["a3"]) == "blocked"          # not cancelled: the retry may still make what a3 needs
    rig.start()
    second = retry["task_id"]
    rig.go(second)
    rig.finish(second, "crashed", "it broke again")
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["state"] == "failed" and node["attempt"] == 2 and node["failure_reason"] == "it broke again"
    assert rig.t.status(tasks["a3"]) == "cancelled" and rig.t.status(tasks["a2"]) == "running" and rig.t.status(tasks["a4"]) == "blocked"       # stop_branch: the sibling goes on
    rig.finish(tasks["a2"])
    rig.start()
    rig.go(tasks["a4"])
    rig.finish(tasks["a4"])
    assert rig.project(reservation.project_id)["status"] == "done_with_open_items"                       # never `done` with a failed node


def test_a_refused_hand_off_is_retried_once_too(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.finish(tasks["a1"], handoff=False)
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["attempt"] == 2 and node["state"] == "queued" and rig.t.status(tasks["a2"]) == "blocked" and [r["action"] for r in rig.audit("handoff.refused")] == ["handoff.refused"]
    rig.start()
    rig.go(node["task_id"])
    rig.finish(node["task_id"])
    assert rig.node_of(node["task_id"])["state"] == "done" and rig.t.status(tasks["a2"]) == "queued"
    assert [m.src_ref.endswith(":2") for m in rig.store.messages(reservation.project_id)] == [True]          # the message of attempt 2: `handoff:<node>:2`


def test_the_retry_is_told_how_the_first_attempt_ended_and_keeps_the_grant(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    before = rig.node_of(tasks["a1"])["grants_json"]
    rig.finish(tasks["a1"], "crashed", "it broke")
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["grants_json"] == before and "it broke" in rig.t.row(node["task_id"]).framing


def test_the_owners_stop_and_the_kill_switch_are_never_retried(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])])
    node_a1 = rig.node_of(tasks["a1"])["id"]
    assert rig.t.run(rig.control.stop_node(node_a1)) is True
    assert rig.node_of(tasks["a1"])["state"] == "cancelled" and rig.node_of(tasks["a1"])["attempt"] == 1 and rig.sql("SELECT count(*) FROM agent_nodes").fetchone()[0] == 3
    rig.t.run(rig.control.kill_all())
    assert rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == 3 and {r["state"] for r in rig.sql("SELECT state FROM agent_nodes")} == {"cancelled"}
    assert rig.start() == []


def test_the_app_closed_under_a_node_gets_a_retry_not_a_cancel(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.t.run(rig.t.service.shutdown())                                                                 # the app is closing: every live task is stopped "the app was closed"
    states = {r["plan_ref"]: (r["state"], r["attempt"]) for r in rig.sql("SELECT plan_ref, state, attempt FROM agent_nodes")}
    assert states == {"a1": ("queued", 2), "a2": ("queued", 2)}


def test_the_project_never_retries_more_than_the_cap(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)
    rig.finish(tasks["a1"], "crashed", "boom")
    assert rig.node_of(tasks["a1"])["state"] == "failed" and rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == 2
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 3) WHERE id = ?", reservation.project_id)
    rig.finish(tasks["a2"], "crashed", "boom")
    assert rig.sql("SELECT attempt FROM agent_nodes WHERE plan_ref = 'a2'").fetchone()[0] == 2


# ---- the failure policy -------------------------------------------------------------------------------------------------------------

def test_stop_all_stops_the_project_at_the_first_failure_that_cannot_be_retried(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", []), ("a3", "ops", ["a2"])])
    rig.sql("UPDATE projects SET failure_policy = 'stop_all', caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)
    rig.finish(tasks["a1"], "crashed", "boom")
    assert rig.project(reservation.project_id)["status"] == "running"                                    # decided inside the transaction, run by the next tick
    done = tick(rig, 1)
    assert done["stopped"] == [reservation.project_id] and rig.project(reservation.project_id)["status"] == "stopped"
    assert "stops at the first failure" in rig.project(reservation.project_id)["stop_reason"]
    assert rig.node_states(tasks) == {"a1": "failed", "a2": "cancelled", "a3": "cancelled"}


def test_stop_branch_is_the_default_and_the_project_ends_failed_when_nothing_finished(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    assert rig.project(reservation.project_id)["failure_policy"] == "stop_branch"
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 0) WHERE id = ?", reservation.project_id)
    rig.finish(tasks["a1"], "crashed", "x")
    rig.finish(tasks["a2"], "crashed", "y")
    assert rig.project(reservation.project_id)["status"] == "failed"


def test_a_paused_project_does_not_retry_into_a_running_state_but_keeps_the_retry_queued(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.t.run(rig.projects.pause(reservation.project_id))
    rig.finish(tasks["a1"], "crashed", "x")
    assert rig.node_of(rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0])["state"] == "queued" and rig.start() == []


# ---- a node with no valid grant (G3, D310) -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("broken", ["{}", "not json", '{"role": "reviewer"}'])
def test_a_node_with_no_valid_grant_is_failed_by_the_tick_and_the_project_does_not_hang(rig, broken):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"]), ("a3", "ops", [])])
    rig.sql("UPDATE agent_nodes SET grants_json = ? WHERE task_id = ?", broken, tasks["a1"])
    assert rig.start() == [tasks["a3"]]                                                             # the gate holds the broken one, the rest starts
    done = tick(rig, 10)
    assert done["expired"] == [] and rig.node_states(tasks) == {"a1": "failed", "a2": "cancelled", "a3": "leased"}
    assert rig.t.status(tasks["a1"]) == "cancelled" and rig.t.status(tasks["a2"]) == "cancelled"        # nothing of it starts, its dependant is cancelled
    denied = rig.audit("grant.denied")
    assert [(r["actor"], r["decision"], r["reason"]) for r in denied if r["node_id"] == rig.node_of(tasks["a1"])["id"]] == [("conductor", "deny", "this step has no valid grant")]
    assert rig.sql("SELECT count(*) FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0] == 1 and rig.node_of(tasks["a1"])["attempt"] == 1       # no retry: the grant would be the same
    rig.go(tasks["a3"])
    rig.finish(tasks["a3"])
    assert rig.project(reservation.project_id)["status"] == "done_with_open_items"                  # the other node finished


def test_a_project_whose_only_node_has_no_valid_grant_ends_failed(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE agent_nodes SET grants_json = '{}'")
    tick(rig, 10)
    assert rig.project(reservation.project_id)["status"] == "failed" and rig.start() == []


def test_a_broken_grant_under_stop_all_stops_the_project(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET failure_policy = 'stop_all'")
    rig.sql("UPDATE agent_nodes SET grants_json = '{}' WHERE task_id = ?", tasks["a1"])
    rig.start()
    rig.go(tasks["a2"])
    done = tick(rig, 10)
    assert done["stopped"] == [reservation.project_id] and rig.project(reservation.project_id)["status"] == "stopped"


# ---- a retry keeps what the node waited for (G4, D310) ------------------------------------------------------------------------------

def test_the_retry_of_a_node_keeps_its_upstream_and_a_node_that_waits_for_it_waits_for_the_new_attempt(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"]), ("a3", "ops", ["a2"])])
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], files={"out.md": "result"})
    rig.start()
    rig.go(tasks["a2"])
    rig.finish(tasks["a2"], status="crashed", outcome="it crashed", handoff=False)               # the node's single retry is made in the same transaction
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a2'").fetchone()
    new = node["task_id"]
    assert node["attempt"] == 2 and new != tasks["a2"] and json.loads(rig.sql("SELECT depends_on FROM tasks WHERE id = ?", new).fetchone()[0]) == [tasks["a1"]]
    assert rig.t.status(new) in ("queued", "starting")
    assert json.loads(rig.sql("SELECT depends_on FROM tasks WHERE id = ?", tasks["a3"]).fetchone()[0]) == [new] and rig.t.status(tasks["a3"]) == "blocked"
    rig.start()
    spec = [s for s, *_ in rig.t.launcher.started if s.task_id == new][0]
    assert [u.run_id for u in spec.upstream] == [rig.t.row(tasks["a1"]).run_id] and "handoff.accepted.json" in spec.upstream[0].files

