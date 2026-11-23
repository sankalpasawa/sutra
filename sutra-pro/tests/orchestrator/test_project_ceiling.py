"""The project's limits and the automatic triggers (MAN-9; D272, D303): wall time and dollars of the whole project, a node that reached a cap, a node whose prompts were scrubbed three times, and the
ceiling the slices must fit. Each trigger leaves an audit row and one plain note."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.conductor import MONTH_REASON, MONTH_START_REASON

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
        rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, 'claude', 'agent_turn', ?, ?)", LATER, task_id, usd)
    rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, 'stub', 'agent_turn', ?, 5.0)", LATER, tasks["a1"])        # a stub call costs nothing
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


def test_a_finished_project_leaves_one_note_with_the_way_back_into_it(rig):                                     # R6
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    for task_id in tasks.values():
        rig.finish(task_id)
    pid = reservation.project_id
    [done] = notes(rig, pid, "ended")
    assert rig.project(pid)["status"] == "done" and done["text"].endswith(f"It is finished. /p/{pid}")
    rig.t.run(rig.projects.tick(now=BASE + 20))
    assert len(notes(rig, pid, "ended")) == 1                                                                  # once


def audit_row(rig, pid, action, at, ref=""):
    rig.sql("INSERT INTO node_audit(at, project_id, actor, action, decision, ref, target) VALUES (?, ?, 'system', ?, 'n/a', ?, ?)", at, pid, action, ref, str(at) if action == "project.slept" else "")


def test_a_pause_and_a_sleep_that_overlap_are_left_out_once_not_twice(rig):                                     # N-1
    from sutra_app.orchestrator.conductor import Conductor
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    pid = reservation.project_id
    audit_row(rig, pid, "project.paused", BASE + 20)                                                            # paused at T0 + 20 ...
    audit_row(rig, pid, "project.slept", BASE + 7500, "7480")                                                   # ... the computer asleep until T0 + 7500 ...
    audit_row(rig, pid, "project.resumed", BASE + 7500)                                                         # ... resumed then
    with rig.t.db.tx() as tx:
        assert Conductor._paused_seconds(tx, pid, BASE + 7600, BASE) == 7480                                    # the time away, once (it was 14969 when the two were added)
        audit_row(rig, pid, "project.slept", BASE + 9000, "100")                                                # a separate sleep later: its own 100 seconds
        assert Conductor._paused_seconds(tx, pid, BASE + 9100, BASE) == 7480 + 100
        assert Conductor._paused_seconds(tx, pid, BASE + 9100, BASE + 7000) == 500 + 100                        # only what lies after `since`


def test_a_pause_that_is_still_on_counts_until_now_and_a_sleep_inside_it_adds_nothing(rig):
    from sutra_app.orchestrator.conductor import Conductor
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    pid = reservation.project_id
    audit_row(rig, pid, "project.paused", BASE + 100)
    audit_row(rig, pid, "project.slept", BASE + 4000, "3000")
    with rig.t.db.tx() as tx:
        assert Conductor._paused_seconds(tx, pid, BASE + 5000, BASE) == 4900


def test_a_project_is_not_stopped_at_once_by_the_wall_limit_because_the_app_was_closed_for_hours(rig):          # N-2
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    pid = reservation.project_id
    began = rig.sql("SELECT MIN(started_at) FROM tasks WHERE started_at IS NOT NULL").fetchone()[0]
    rig.sql("UPDATE tasks SET last_event_at = ?", began + 60)                                                   # the last sign of life, a minute in
    rig.t.clock.advance(3 * 3600)                                                                               # Sutra stays closed for three hours (the limit is two)
    rig.t.run(rig.projects.reconcile_projects())
    [row] = rig.audit("project.slept")
    assert "closed or the computer was off" in row["reason"] and 10_000 < int(row["ref"]) < 11_000
    now = rig.t.clock.peek
    done = rig.t.run(rig.projects.tick(now=now))
    assert done["stopped"] == [] and rig.project(pid)["status"] == "running"                                    # without the row the first tick would say "ran longer than 120 minutes"
    assert rig.audit("trigger.project_wall") == []


# ---- the owner's monthly dollar limit is the project's limit too (D381) -----------------------------------------------------------------

MONTH_SENTENCE = MONTH_REASON
MONTH_START_SENTENCE = MONTH_START_REASON
assert MONTH_SENTENCE == "Your monthly limit was reached, so the project stopped."


LATER = BASE + 5000                                                                          # after the project exists (a ledger row of its own steps); BASE + 3 is before it


def spend(rig, usd, task_id=None, provider="claude", at=None):
    rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, ?, 'agent_turn', ?, ?)", at if at is not None else (LATER if task_id or at is not None else BASE + 3), provider, task_id, usd)


def month_limit(rig, usd):
    rig.limits.update(monthly_usd=usd, now=BASE)
    rig.projects._limit_seen = (-1e9, None)                                                 # the 2 s memory of the file: forget it so this test's change is seen at once


def test_a_project_gets_what_is_left_of_the_monthly_limit_when_it_starts(rig):
    month_limit(rig, 3.0)
    spend(rig, 0.5)                                                                          # an ordinary task already spent 0.5 this month
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    project = rig.project(reservation.project_id)
    assert project["budget_usd"] == 2.5 and json.loads(project["caps_json"])["usd_from_month"] is True


def test_the_owners_budget_chip_is_the_projects_own_dollars(rig):
    """D424: the dollars the owner picked on Home's Budget chip are the project's own number (not the month's), so its stop says "the dollars you set"."""
    month_limit(rig, 3.0)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], usd=1.5)
    project = rig.project(reservation.project_id)
    assert project["budget_usd"] == 1.5 and "usd_from_month" not in json.loads(project["caps_json"])


def test_without_a_monthly_limit_a_project_has_no_dollar_limit_of_its_own(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    assert rig.project(reservation.project_id)["budget_usd"] is None and "usd_from_month" not in json.loads(rig.project(reservation.project_id)["caps_json"])
    rig.start()
    node = json.loads((rig.t.run_dir(tasks["a1"]) / "task.json").read_text())["node"]
    assert node["caps"]["usd"] is None
    spend(rig, 50.0, tasks["a1"])
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    assert tick(rig, 10)["stopped"] == []


def test_a_step_starts_with_a_dollar_cap_of_what_the_project_and_the_month_have_left(rig):
    month_limit(rig, 3.0)
    spend(rig, 0.4)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.start()
    node = json.loads((rig.t.run_dir(tasks["a1"]) / "task.json").read_text())["node"]
    assert node["caps"]["usd"] == 2.6, "the step's own meter stops it between calls at what the month has left"
    rig.go(tasks["a1"])
    spend(rig, 1.0, tasks["a1"])                                                              # step one spent a dollar
    rig.finish(tasks["a1"])
    rig.start()
    second = json.loads((rig.t.run_dir(tasks["a2"]) / "task.json").read_text())["node"]
    assert second["caps"]["usd"] == 1.6, "and the next step gets what is left after that"


def test_when_the_monthly_limit_is_reached_a_running_step_is_stopped_with_one_plain_sentence(rig):
    month_limit(rig, 3.0)
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    assert tick(rig, 10)["stopped"] == []
    spend(rig, 2.9, tasks["a1"])                                                              # the running step spent 2.9 of the 3.0
    assert tick(rig, 12)["stopped"] == []
    spend(rig, 0.2, None, at=LATER)                                                           # an ordinary task takes the month past its limit
    done = tick(rig, 15)
    assert done["stopped"] == [reservation.project_id]
    project = rig.project(reservation.project_id)
    assert project["status"] == "stopped" and project["stop_reason"] == MONTH_SENTENCE
    assert rig.t.status(tasks["a1"]) == "stopped" and rig.node_states(tasks)["a2"] == "cancelled"
    assert [r["action"] for r in rig.audit("trigger.project_month")] == ["trigger.project_month"] and rig.audit("trigger.project_usd") == []
    texts = [r["text"] for r in notes(rig, reservation.project_id, "limit")]
    assert len(texts) == 1 and MONTH_SENTENCE in texts[0] and "I stopped it" not in texts[0]
    assert tick(rig, 20)["stopped"] == []                                                     # nothing is done twice


def test_a_project_that_spent_past_its_starting_allowance_is_stopped_and_says_so(rig):
    month_limit(rig, 3.0)
    spend(rig, 1.0)
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    month_limit(rig, 100.0)                                                                   # the owner raised the month meanwhile: the project still keeps to what it was given at its start
    spend(rig, 2.1, tasks["a1"])                                                              # more than the 2.0 it was given
    assert tick(rig, 10)["stopped"] == [reservation.project_id]
    assert rig.project(reservation.project_id)["stop_reason"] == MONTH_START_SENTENCE, "the month itself still has room, so the sentence is not 'monthly limit reached'"


def test_the_owners_own_lower_dollars_keep_their_own_words(rig):
    month_limit(rig, 3.0)
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE projects SET budget_usd = 0.5, caps_json = ? WHERE id = ?", json.dumps({**json.loads(rig.project(reservation.project_id)["caps_json"]), "usd_from_month": False}), reservation.project_id)
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    spend(rig, 0.6, tasks["a1"])
    assert tick(rig, 10)["stopped"] == [reservation.project_id]
    assert rig.project(reservation.project_id)["stop_reason"].startswith("stopped: the project spent more than the dollars you set") and rig.audit("trigger.project_month") == []


def test_an_ordinary_task_keeps_todays_rule_it_waits_and_nothing_stops_it(rig):
    """The start gate (`Limits.gate`) is unchanged: past the limit a NEW task waits; the project rules above never reach a task that is not a step."""
    month_limit(rig, 1.0)
    spend(rig, 1.5)
    waiting = rig.limits.gate(rig.t.db.conn(), BASE + 10, "web")
    assert waiting.startswith("This month's spending limit is used up") or "used up" in waiting
    assert tick(rig, 10)["stopped"] == []                                                       # no project exists: nothing is stopped


# ---- the frozen figure and the live month (D388) -----------------------------------------------------------------------------------------

def test_the_planners_calls_are_not_counted_twice_against_the_project(rig):
    """The planner's calls were made before the project existed, so they are already out of the month's allowance the project was given: they must not come off it a second time."""
    from sutra_app.orchestrator.budgets import project_cost
    month_limit(rig, 3.0)
    planner = "nd_" + "a" * 12
    rig.sql("INSERT INTO usage_ledger(at, provider, purpose, usd, detail_json) VALUES (?, 'claude', 'chat_plan', 0.5, ?)", BASE + 1, '{"agent_node": "%s"}' % planner)     # before the project
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    assert rig.project(reservation.project_id)["budget_usd"] == 2.5
    rig.sql("INSERT INTO agent_nodes(id, project_id, role, runtime, state, created_at) VALUES (?, ?, 'planner', 'inline', 'done', ?)", planner, reservation.project_id, BASE)
    spend(rig, 0.3, tasks["a1"])
    created = rig.project(reservation.project_id)["created_at"]
    assert project_cost(rig.t.db.conn(), reservation.project_id)[0] == pytest.approx(0.8), "the page shows everything"
    assert project_cost(rig.t.db.conn(), reservation.project_id, created)[0] == pytest.approx(0.3), "the limit counts what the project itself spent"
    assert rig.projects.usd_left(rig.t.db.conn(), reservation.project_id, BASE + 200) == pytest.approx(2.2), "2.5 given, 0.3 spent: not 1.7"


def test_removing_the_monthly_limit_mid_run_does_not_stop_the_project(rig):
    month_limit(rig, 3.0)
    spend(rig, 1.0)
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    rig.sql("UPDATE tasks SET last_event_at = ?", BASE + 5)
    month_limit(rig, None)                                                                    # the owner clears the limit
    spend(rig, 5.0, tasks["a1"])                                                              # far more than the 2.0 the project was given
    assert tick(rig, 10)["stopped"] == [] and rig.project(reservation.project_id)["status"] == "running"
    assert rig.audit("trigger.project_month") == []
    assert rig.projects.usd_left(rig.t.db.conn(), reservation.project_id, BASE + 10) is None, "no limit: nothing caps a new step"


def test_a_new_month_forgets_the_old_months_leftover(rig):
    month_limit(rig, 3.0)
    spend(rig, 1.0)
    reservation, tasks = running(rig, [("a1", "web", []), ("a2", "sales", [])])
    spend(rig, 2.1, tasks["a1"])                                                              # past the 2.0 it was given, in the old month
    later = 40 * 86400                                                                        # a month on: the full limit is there again
    rig.sql("UPDATE tasks SET started_at = ?, last_event_at = ?", BASE + later - 5, BASE + later - 1)
    assert tick(rig, later)["stopped"] == [] and rig.project(reservation.project_id)["status"] == "running"
    assert rig.projects.usd_left(rig.t.db.conn(), reservation.project_id, BASE + later) == pytest.approx(3.0), "the new month's allowance, not the old figure"


def test_a_step_does_not_start_when_the_project_has_no_dollars_left(rig):
    month_limit(rig, 3.0)
    spend(rig, 0.5)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    conn = rig.t.db.conn()
    assert rig.projects.gate(conn, BASE + 50, rig.t.row(tasks["a1"])) == ""
    spend(rig, 2.5, tasks["a1"])                                                              # the project's 2.5 are gone, the month is at 3.0
    assert rig.projects.gate(conn, BASE + 50, rig.t.row(tasks["a1"])) == "Waiting: the dollars for this project are used up"
    assert rig.start() == [], "no step is started with a token cap"


# ---- what one call may spend, read now and shared by the steps that run (D409, R-2) ------------------------------------------------------------------

def cap_of(rig, project_id, now=None):
    import sqlite3
    from sutra_app.orchestrator.livecap import call_cap
    conn = sqlite3.connect(f"file:{rig.t.settings.db_path}?mode=ro", uri=True)
    try:
        return call_cap(conn, project_id, rig.limits.monthly_limit(), BASE + 100 if now is None else now)
    finally:
        conn.close()


def set_state(rig, ref, state):
    rig.sql("UPDATE agent_nodes SET state = ? WHERE plan_ref = ?", state, ref)


def test_two_siblings_that_run_together_each_get_half_of_the_project(rig):
    month_limit(rig, 3.0)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    for ref in ("a1", "a2"):
        set_state(rig, ref, "running")
    assert cap_of(rig, reservation.project_id) == pytest.approx(1.5)


def test_the_cap_is_read_on_every_call_a_step_that_started_alone_is_lowered_when_a_sibling_starts_and_given_back_when_it_ends(rig):
    month_limit(rig, 3.0)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    set_state(rig, "a1", "running")
    assert cap_of(rig, reservation.project_id) == pytest.approx(3.0), "alone: all of it"
    set_state(rig, "a2", "running")
    assert cap_of(rig, reservation.project_id) == pytest.approx(1.5), "the sibling started: lowered, though a1 began with the whole"
    set_state(rig, "a2", "done")
    assert cap_of(rig, reservation.project_id) == pytest.approx(3.0), "the share is given back"


def test_a_step_held_for_an_answer_takes_no_share_until_it_runs(rig):
    month_limit(rig, 3.0)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])])
    set_state(rig, "a1", "running")
    set_state(rig, "a2", "running")
    set_state(rig, "a3", "awaiting_approval")
    assert cap_of(rig, reservation.project_id) == pytest.approx(1.5)
    set_state(rig, "a3", "running")
    assert cap_of(rig, reservation.project_id) == pytest.approx(1.0), "the owner answered: three run, a third each, for the very next call"


def test_the_month_bounds_every_project_and_two_projects_divide_their_own_dollars_only(rig):
    month_limit(rig, 3.0)
    first, _ = rig.request([("a1", "web", []), ("a2", "sales", [])], request_id="req-1")
    second, _ = rig.request([("b1", "ops", []), ("b2", "hr", ["b1"])], request_id="req-2")
    for ref in ("a1", "a2", "b1"):
        set_state(rig, ref, "running")
    assert cap_of(rig, first.project_id) == pytest.approx(1.5) and cap_of(rig, second.project_id) == pytest.approx(3.0), "each divides its own"
    spend(rig, 2.5, at=LATER)                                                                 # the month is nearly gone: 0.5 left, for every project
    assert cap_of(rig, first.project_id, LATER + 5) == pytest.approx(0.5) and cap_of(rig, second.project_id, LATER + 5) == pytest.approx(0.5)


def test_without_a_limit_nothing_caps_a_call_and_a_removed_limit_lifts_a_month_figure(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    set_state(rig, "a1", "running")
    assert cap_of(rig, reservation.project_id) is None
    month_limit(rig, 3.0)
    reservation2, _ = rig.request([("b1", "ops", []), ("b2", "hr", ["b1"])], request_id="req-9")
    set_state(rig, "b1", "running")
    assert cap_of(rig, reservation2.project_id) == pytest.approx(3.0)
    month_limit(rig, None)
    assert cap_of(rig, reservation2.project_id) is None


def test_the_start_cap_of_a_step_is_what_the_project_and_month_have_left_the_per_call_cap_does_the_sharing(rig):
    month_limit(rig, 3.0)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    caps = [json.loads((rig.t.run_dir(task_id) / "task.json").read_text())["node"]["caps"]["usd"] for task_id in tasks.values() if (rig.t.run_dir(task_id) / "task.json").exists()]
    assert caps and all(c == 3.0 for c in caps)
