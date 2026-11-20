"""The Conductor's task gate and the node state machine (MAN-5; D257, D302, D303): what holds a node, what lets it start, the lease and the teardown. Real `TaskService`, `Projector`,
`ProjectService`, `NodeControl`; `FakeLauncher` plays the engine."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_tasks import tenv  # noqa: F401

from sutra_app.orchestrator.testing.fake_engine import FakeLauncher

FIVE = [("a1", "web", []), ("a2", "sales", []), ("a3", "ops", []), ("a4", "hr", []), ("a5", "dev", [])]


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def test_independent_steps_start_together_up_to_the_projects_parallel_cap_of_three_and_the_rest_wait_with_a_sentence(rig):
    reservation, tasks = rig.request(FIVE)
    started = rig.start()
    assert started == [tasks["a1"], tasks["a2"], tasks["a3"]]                              # FIFO, three at a time
    assert [rig.t.status(tasks[r]) for r in ("a4", "a5")] == ["queued", "queued"]
    assert "Waiting for a free slot in this project (3 at a time)" in rig.detail(tasks["a4"])
    assert {r: s for r, s in rig.node_states(tasks).items()} == {"a1": "leased", "a2": "leased", "a3": "leased", "a4": "queued", "a5": "queued"}
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"])                                                                 # a slot is free: the next one starts by itself (the watcher's after_drain is start_ready)
    assert rig.t.run(rig.t.service.start_ready()) == [tasks["a4"]] or rig.t.status(tasks["a4"]) in ("starting", "running")


def test_a_dependant_waits_for_its_step_and_starts_when_it_is_done(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    assert rig.start() == [tasks["a1"]] and rig.t.status(tasks["a2"]) == "blocked"
    assert rig.node_states(tasks) == {"a1": "leased", "a2": "planned"}
    rig.go(tasks["a1"])
    assert rig.node_of(tasks["a1"])["state"] == "running"
    rig.finish(tasks["a1"])
    assert rig.node_of(tasks["a1"])["state"] == "done" and rig.t.status(tasks["a2"]) == "queued"
    assert rig.start() == [tasks["a2"]]


def test_the_machine_wide_caps_still_bound_the_nodes(db, settings, clock, events):
    rig = PRig(db, settings, clock, events, max_runs=2, max_live=2)
    reservation, tasks = rig.request(FIVE)
    assert len(rig.start()) == 2                                                            # SUTRA_MAX_RUNS (2) beats the project's cap of 3
    assert "waiting" in (rig.detail(tasks["a3"]) or "").lower()


def test_the_lease_is_taken_when_the_node_starts_beats_with_the_run_and_is_released_at_teardown(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    node = rig.node_of(tasks["a1"])
    assert node["state"] == "leased" and node["lease_expires_at"] == node["last_beat_at"] + 90
    rig.go(tasks["a1"])
    node = rig.node_of(tasks["a1"])
    assert node["state"] == "running" and node["lease_expires_at"] is not None
    rig.finish(tasks["a1"])
    node = rig.node_of(tasks["a1"])
    assert node["state"] == "done" and node["lease_expires_at"] is None and node["torn_down_at"] is not None and node["ended_at"] is not None
    actions = [r["action"] for r in rig.audit() if r["node_id"] == node["id"]]
    assert actions == ["grant.issued", "node.leased", "node.spawned", "handoff.accepted", "node.done"]


def test_a_failed_node_cancels_only_its_dependants_and_the_project_never_ends_done(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", ["a1"]), ("a4", "hr", ["a2"])])
    rig.start()
    for ref in ("a1", "a2"):
        rig.go(tasks[ref])
    rig.finish(tasks["a1"], "crashed", "it broke")
    assert rig.node_states(tasks) == {"a1": "failed", "a2": "running", "a3": "cancelled", "a4": "planned"}      # stop_branch: the sibling goes on, the dependant of the failed one is cancelled
    assert rig.node_of(tasks["a1"])["failure_reason"] == "it broke"
    rig.finish(tasks["a2"])
    rig.start()
    rig.go(tasks["a4"])
    rig.finish(tasks["a4"])
    assert rig.project(reservation.project_id)["status"] == "done_with_open_items" and rig.project(reservation.project_id)["ended_at"] is not None


def test_a_project_whose_every_node_is_done_is_done(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    rig.go(tasks["a1"]); rig.finish(tasks["a1"])
    rig.start()
    rig.go(tasks["a2"]); rig.finish(tasks["a2"])
    assert rig.project(reservation.project_id)["status"] == "done" and [r["action"] for r in rig.audit("project.ended")] == ["project.ended"]


# ---- what holds a node -------------------------------------------------------------------------------------------------------------

def test_pause_all_and_kill_hold_the_nodes_and_they_start_by_themselves_when_released(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.switch.set("pause")
    assert rig.start() == [] and "Paused" in rig.detail(tasks["a1"])
    rig.switch.clear()
    assert rig.start() == [tasks["a1"], tasks["a2"]]


def test_a_paused_project_holds_its_nodes_and_resume_lets_them_start(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.t.run(rig.projects.pause(reservation.project_id))
    assert rig.start() == [] and "this project is paused" in rig.detail(tasks["a1"])
    assert rig.t.run(rig.projects.pause(reservation.project_id, resume=True)).paused is False
    assert rig.t.status(tasks["a1"]) in ("starting", "running") and rig.t.status(tasks["a2"]) in ("starting", "running")      # resume kicks the scheduler


def test_a_project_that_waits_for_the_owner_starts_nothing(rig):
    steps = [(f"a{i}", team, []) for i, team in enumerate(("web", "sales", "ops", "hr", "dev", "legal"), 1)]       # 6 steps x the default slice of 100 = 600 > 500
    reservation, tasks = rig.request(steps)
    assert rig.project(reservation.project_id)["status"] == "awaiting_approval"
    assert rig.start() == [] and "Waiting for your answer" in rig.detail(tasks["a1"])
    assert [r["action"] for r in rig.audit("gate.asked")] == ["gate.asked"] and rig.store.approvals(reservation.project_id, status="open")[0].request["kind"] == "estimate"


def test_a_node_whose_grant_is_broken_is_held_and_the_rest_of_the_project_starts(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE agent_nodes SET grants_json = '{}' WHERE task_id = ?", tasks["a1"])
    assert rig.start() == [tasks["a2"]] and "no valid grant" in rig.detail(tasks["a1"])


def test_the_gate_asks_the_switch_before_the_project_and_never_holds_an_ordinary_task(rig):
    ordinary = rig.t.new("web", "plain")
    reservation, tasks = rig.request([("a1", "sales", []), ("a2", "ops", [])])
    rig.switch.set("kill")
    assert rig.start() == [ordinary.id] and "kill switch" in rig.detail(tasks["a1"])


def test_a_stopped_projects_nodes_are_never_started_by_the_scheduler(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.t.run(rig.projects.stop(reservation.project_id))
    assert rig.project(reservation.project_id)["status"] == "stopped" and rig.start() == []
    assert rig.node_states(tasks) == {"a1": "cancelled", "a2": "cancelled"}


def test_stop_a_running_project_stops_every_node_together_cancels_the_rest_and_ends_the_project(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", ["a1"])])
    rig.start()
    for ref in ("a1", "a2"):
        rig.go(tasks[ref])
    assert rig.t.run(rig.projects.stop(reservation.project_id)) == 3
    assert rig.node_states(tasks) == {"a1": "cancelled", "a2": "cancelled", "a3": "cancelled"} and rig.project(reservation.project_id)["status"] == "stopped"
    assert len(rig.t.launcher.stopped) == 2 and rig.project(reservation.project_id)["stop_reason"] == "stopped by you"
    assert [r["action"] for r in rig.audit("project.stopped")] == ["project.stopped"]
    assert rig.t.run(rig.projects.stop(reservation.project_id)) == 0                       # a repeat is a no-op


def test_kill_all_ends_every_project_with_an_open_node_and_nothing_starts_by_itself_after_resume(rig):
    first, t1 = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], request_id="req-1")
    second, t2 = rig.request([("b1", "ops", []), ("b2", "hr", [])], request_id="req-2")
    third, t3 = rig.request([("c1", "dev", []), ("c2", "legal", ["c1"])], request_id="req-3")
    rig.start()
    rig.go(t1["a1"])
    rig.go(t2["b1"])
    rig.t.run(rig.control.kill_all(reason="enough"))
    for reservation in (first, second, third):
        assert rig.project(reservation.project_id)["status"] == "stopped" and rig.project(reservation.project_id)["stop_reason"] == "stopped by the kill switch"
    assert set(rig.node_states(t1).values()) == {"cancelled"} and set(rig.node_states(t2).values()) == {"cancelled"} and set(rig.node_states(t3).values()) == {"cancelled"}
    rig.t.run(rig.control.resume())
    assert rig.start() == [] and rig.t.launcher.stopped and all(rig.t.status(t) in ("stopped", "cancelled") for t in (*t1.values(), *t2.values(), *t3.values()))


def test_pause_all_only_holds_nothing_is_cancelled(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    rig.go(tasks["a1"])
    rig.t.run(rig.control.pause_all())
    assert rig.project(reservation.project_id)["status"] == "running" and rig.node_states(tasks) == {"a1": "running", "a2": "planned"}
    rig.finish(tasks["a1"])
    assert rig.start() == [] and rig.t.status(tasks["a2"]) == "queued"                       # held by the pause
    rig.t.run(rig.control.resume())
    assert rig.t.status(tasks["a2"]) in ("starting", "running")


# ---- the planner's stop token and identity -----------------------------------------------------------------------------------------

def test_the_planner_gets_a_node_id_and_a_token_for_the_request_and_stop_planners_requests_it(rig):
    node, token = rig.projects.planner_for("req-9")
    assert node.startswith("nd_") and rig.projects.planner_for("req-9") == (node, token) and rig.projects.planner_id_of("req-9") == node
    assert not token.requested and rig.t.run(rig.projects.stop_planner_node(node)) is True and token.requested
    assert rig.t.run(rig.projects.stop_planner_node("nd_" + "f" * 12)) is False
    rig.projects.release_planner("req-9")
    assert rig.projects.planner_id_of("req-9") == "" and rig.projects.stop_planners() == 0


def test_stop_planners_without_a_request_stops_every_running_planner(rig):
    a, ta = rig.projects.planner_for("req-1")
    b, tb = rig.projects.planner_for("req-2")
    assert rig.projects.stop_planners("req-1") == 1 and ta.requested and not tb.requested
    assert rig.projects.stop_planners() == 2 and tb.requested


def test_a_kill_requests_the_running_planner_tokens(rig):
    node, token = rig.projects.planner_for("req-1")
    rig.t.run(rig.control.kill_all())
    assert token.requested


def test_pause_does_not_stop_a_planner(rig):
    node, token = rig.projects.planner_for("req-1")
    rig.t.run(rig.control.pause_all())
    assert not token.requested


def test_the_node_stop_of_a_planner_node_ends_its_call(rig):
    node, token = rig.projects.planner_for("req-1")
    assert rig.t.run(rig.control.stop_node(node)) is True and token.requested


# ---- the hand-off decides when a node is done (MAN-6) -------------------------------------------------------------------------------

def test_a_node_whose_run_ended_well_but_left_no_hand_off_is_failed_with_the_reason_and_its_dependant_is_cancelled(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], handoff=False)
    node = rig.node_of(tasks["a1"])
    assert node["state"] == "failed" and node["failure_reason"] == "hand-off refused: the node left no hand-off" and node["torn_down_at"] is not None
    assert rig.node_of(tasks["a2"])["state"] == "cancelled" and rig.project(reservation.project_id)["status"] == "failed"
    refused = rig.audit("handoff.refused")
    assert len(refused) == 1 and refused[0]["decision"] == "deny" and refused[0]["actor"] == "conductor" and rig.sql("SELECT count(*) FROM node_messages").fetchone()[0] == 0


def test_a_hand_off_that_does_not_match_its_files_fails_the_node_and_keeps_the_files(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], files={"out.md": "result"}, override={"files": [{"path": "out.md", "sha256": "0" * 64, "bytes": 6}]})
    assert "checksum" in rig.node_of(tasks["a1"])["failure_reason"] and (rig.t.run_dir(tasks["a1"]) / "out.md").is_file() and (rig.t.run_dir(tasks["a1"]) / "handoff.json").is_file()


def test_a_run_that_ended_with_open_items_hands_off_and_the_project_says_so(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    for ref in ("a1", "a2"):
        rig.go(tasks[ref])
    rig.finish(tasks["a1"], "done_with_open_items", "Partly done")
    rig.finish(tasks["a2"])
    assert rig.node_states(tasks) == {"a1": "done", "a2": "done"} and rig.project(reservation.project_id)["status"] == "done_with_open_items"
    assert [json.loads(m.body)["status"] for m in rig.store.messages(reservation.project_id)] == ["done_with_open_items", "done"]


def test_the_messages_route_reads_in_order_with_after_and_404s_for_an_unknown_project(db, settings, clock, events):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sutra_app.orchestrator.api import projects as api
    from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
    from sutra_app.orchestrator.redact import Redactor
    from sutra_app.orchestrator.services import Services
    rig = PRig(db, settings, clock, events, max_runs=5, max_live=10)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    for ref in ("a1", "a2"):
        rig.go(tasks[ref])
        rig.finish(tasks[ref])
    app = FastAPI()
    services = Services(settings=rig.t.settings, version="t", db=db, redact=Redactor(None, environ={}))
    services.projects, services.node_control = rig.projects, rig.control
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(api.build_router())
    client = TestClient(app, base_url="http://127.0.0.1:8780")
    base = f"/api/projects/{reservation.project_id}"
    got = client.get(base + "/messages").json()
    assert [m["seq"] for m in got] == [1, 2] and got[0]["kind"] == "handoff" and got[0]["body"]["status"] == "done" and got[0]["v"] == 1
    assert [m["seq"] for m in client.get(base + "/messages", params={"after": 1}).json()] == [2] and client.get(base + "/messages", params={"after": 2}).json() == []
    assert client.get("/api/projects/prj_" + "0" * 12 + "/messages").status_code == 404
    audit = client.get(base + "/audit").json()
    assert {"handoff.accepted", "grant.issued"} <= {row["action"] for row in audit}
