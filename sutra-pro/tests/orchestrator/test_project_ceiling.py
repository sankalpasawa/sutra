"""The project's limits and the automatic triggers (MAN-9; D272, D303): wall time and dollars of the whole project, a node that reached a cap, a node whose prompts were scrubbed three times, and the
ceiling the slices must fit. Each trigger leaves an audit row and one plain note."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

BASE = 1793786400
NODE_A = "nd_"


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


def tick(rig, seconds):
    return rig.t.run(rig.projects.tick(now=BASE + seconds))


def notes(rig, project_id, tag):
    return rig.sql("SELECT text FROM chat_messages WHERE src_ref LIKE ?", f"project:{project_id}#{tag}%").fetchall()


def test_a_project_that_ran_past_its_wall_time_is_stopped_with_a_row_and_one_note(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET created_at = ? WHERE id = ?", BASE - 8000, reservation.project_id)          # 2 h 13 min ago; the cap is 7200 s
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    done = tick(rig, 10)
    assert done["stopped"] == [reservation.project_id] and rig.project(reservation.project_id)["status"] == "stopped"
    assert [r["action"] for r in rig.audit("trigger.project_wall")] == ["trigger.project_wall"] and len(notes(rig, reservation.project_id, "limit")) == 1
    assert rig.project(reservation.project_id)["stop_reason"].startswith("stopped: the project ran longer") and rig.node_states(tasks) == {"a1": "cancelled", "a2": "cancelled"}
    assert tick(rig, 20)["stopped"] == []                                                                 # nothing is done twice


def test_a_project_that_spent_more_dollars_than_the_owner_set_is_stopped(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET budget_usd = 0.5 WHERE id = ?", reservation.project_id)
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    assert tick(rig, 10)["stopped"] == []                                                                  # nothing spent yet
    for task_id, usd in ((tasks["a1"], 0.3), (tasks["a2"], 0.3)):                                          # the two nodes together spent 0.6: over the 0.5 the owner set
        rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, 'claude', 'agent_turn', ?, ?)", BASE + 11, task_id, usd)
    rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, 'stub', 'agent_turn', ?, 5.0)", BASE + 11, tasks["a1"])        # a stub call costs nothing
    done = tick(rig, 15)
    assert done["stopped"] == [reservation.project_id] and [r["action"] for r in rig.audit("trigger.project_usd")] == ["trigger.project_usd"]
    assert len(notes(rig, reservation.project_id, "limit")) == 1 and rig.project(reservation.project_id)["status"] == "stopped"


def test_a_node_that_reached_its_cap_is_failed_without_a_retry_with_a_row_and_a_note(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.finish(tasks["a1"], status="crashed", outcome="stopped: this step reached its calls cap", handoff=False)
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["state"] == "failed" and node["attempt"] == 1 and "calls cap" in node["failure_reason"]            # the one retry would hit the same cap
    assert [r["action"] for r in rig.audit("trigger.cap_reached")] == ["trigger.cap_reached"] and len(notes(rig, reservation.project_id, "cap")) == 1 and rig.audit("node.retry") == []


def test_a_node_whose_prompts_were_scrubbed_three_times_is_stopped_and_two_times_is_not(rig, settings):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    path = settings.data_dir / "connectors" / "egress.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    one, two = rig.node_of(tasks["a1"])["id"], rig.node_of(tasks["a2"])["id"]
    rows = [{"node": one, "shapes": {"api-key": 1}}] * 3 + [{"node": two, "shapes": {"email": 1}}] * 2 + [{"node": one, "shapes": {}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    tick(rig, 10)
    assert rig.t.status(tasks["a1"]) == "stopped" and rig.t.status(tasks["a2"]) == "running"
    assert [r["action"] for r in rig.audit("trigger.egress_scrub")] == ["trigger.egress_scrub"] and len(notes(rig, reservation.project_id, "scrub")) == 1
    assert tick(rig, 12)["stopped"] == [] and len(rig.audit("trigger.egress_scrub")) == 1                     # once


def test_the_gate_holds_a_node_when_the_slices_do_not_fit_the_ceiling(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    conn = rig.t.db.conn()
    assert rig.projects.gate(conn, BASE, rig.t.row(tasks["a1"])) == ""                                      # the slices are exactly the ceiling
    rig.sql("UPDATE agent_nodes SET slice_credits = slice_credits + 1 WHERE plan_ref = 'a2'")              # something moved credits past the ceiling: it must not start
    assert "do not fit its ceiling" in rig.projects.gate(conn, BASE, rig.t.row(tasks["a1"]))
    assert rig.start() == []
    rig.sql("UPDATE agent_nodes SET state = 'cancelled' WHERE plan_ref = 'a2'")                              # a node that no longer counts frees its credits
    assert rig.projects.gate(conn, BASE, rig.t.row(tasks["a1"])) == ""
