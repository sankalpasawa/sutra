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
    rig.sql("UPDATE tasks SET created_at = ?, started_at = ?, last_event_at = ?", BASE - 8100, BASE - 8000, BASE + 5)                    # the first node started 2 h 13 min ago; the cap is 7200 s
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
    rig.finish(tasks["a1"], status="crashed", outcome="stopped: this step used up its model calls", handoff=False)
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["state"] == "failed" and node["attempt"] == 1 and "model calls" in node["failure_reason"]            # the one retry would hit the same cap
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
    assert "are more than the project may spend" in rig.projects.gate(conn, BASE, rig.t.row(tasks["a1"]))
    assert rig.start() == []
    rig.sql("UPDATE agent_nodes SET state = 'cancelled' WHERE plan_ref = 'a2'")                              # a node that no longer counts frees its credits
    assert rig.projects.gate(conn, BASE, rig.t.row(tasks["a1"])) == ""


def test_a_project_that_waited_three_hours_for_an_answer_is_not_stopped_by_the_first_tick_after_it_starts(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)})
    rig.sql("UPDATE projects SET created_at = ? WHERE id = ?", BASE - 3 * 3600, reservation.project_id)         # made three hours ago, waiting for the owner
    rig.sql("UPDATE approvals SET expires_at = ?", BASE + 86_400)
    assert tick(rig, 10)["stopped"] == [] and rig.project(reservation.project_id)["status"] == "awaiting_approval"      # no node has started: no wall limit yet
    rig.t.run(rig.projects.answer(reservation.project_id, rig.store.approvals(reservation.project_id)[0].id, "allow_once"))
    rig.go(tasks["a1"])
    assert tick(rig, 60)["stopped"] == [] and rig.project(reservation.project_id)["status"] == "running"


def test_the_time_a_project_was_paused_is_not_counted(rig):
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET created_at = ?, started_at = ?, last_event_at = ?", BASE - 8100, BASE - 8000, BASE + 5)                       # 2 h 13 min since the start ...
    rig.sql("INSERT INTO node_audit(at, project_id, actor, action, decision) VALUES (?, ?, 'owner', 'project.paused', 'n/a')", BASE - 7000, reservation.project_id)
    rig.sql("INSERT INTO node_audit(at, project_id, actor, action, decision) VALUES (?, ?, 'owner', 'project.resumed', 'n/a')", BASE - 1000, reservation.project_id)      # ... of which 6000 s were paused
    assert tick(rig, 10)["stopped"] == []


def test_the_egress_file_is_read_before_the_write_transaction_and_the_row_is_written_once_even_when_the_stop_fails(rig, settings, monkeypatch):
    from sutra_app.orchestrator import conductor
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    path = settings.data_dir / "connectors" / "egress.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    node_id = rig.node_of(tasks["a1"])["id"]
    path.write_text("\n".join(json.dumps({"node": node_id, "shapes": {"api-key": 1}}) for _ in range(3)) + "\n", encoding="utf-8")
    depths, real = [], conductor.egress_scrubs
    monkeypatch.setattr(conductor, "egress_scrubs", lambda *a, **k: (depths.append(getattr(rig.t.db._local, "depth", 0)), real(*a, **k))[1])
    async def failing(task_id, outcome="x", **kw):
        raise RuntimeError("the ladder did not work")
    monkeypatch.setattr(rig.t.service, "stop_node", failing)
    for seconds in (10, 12, 14):
        tick(rig, seconds)
    assert depths == [0, 0, 0]                                                                        # never inside a transaction
    assert [r["action"] for r in rig.audit("trigger.egress_scrub")] == ["trigger.egress_scrub"] and len(notes(rig, reservation.project_id, "scrub")) == 1


def test_the_time_the_computer_slept_is_not_counted_in_the_wall_time(rig):                                      # PB-12
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET created_at = ?, started_at = ?, last_event_at = ?", BASE - 200, BASE - 100, BASE + 5)
    tick(rig, 10)
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 7490)
    woke = tick(rig, 7500)                                                                                    # the tick came two hours late: the computer slept, and nothing was open to refuse
    assert woke["stopped"] == [] and rig.project(reservation.project_id)["status"] == "running"
    [row] = rig.audit("project.slept")
    assert "asleep or closed" in row["reason"] and 7400 <= int(row["ref"]) <= 7490
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 7500 + 7300)
    assert tick(rig, 7510 + 7300)["stopped"] == [reservation.project_id]                                     # real working time still counts: two more hours of work stops it
