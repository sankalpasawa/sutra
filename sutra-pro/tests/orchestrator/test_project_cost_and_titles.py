"""What the project page is told (D383): a step has its own title, and the project's dollars are the ledger's: the steps, the reviewer and the planner's own calls, with the calls that have no price
counted apart so the page can say "about"."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

BASE = 1793786400
PLANNER = "nd_" + "a" * 12


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def ledger(rig, usd, *, task_id=None, session="cs_org", node=None, provider="claude", purpose="agent_turn"):
    detail = json.dumps({"agent_node": node, "agent_role": "planner"}) if node else None
    rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd, detail_json) VALUES (?, ?, ?, ?, ?, ?)", BASE + 3, provider, purpose, task_id, usd, detail)


def test_a_step_is_named_by_its_title_in_the_snapshot_and_a_node_without_a_task_has_none(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("UPDATE tasks SET title = 'Describe each file' WHERE id = ?", tasks["a1"])
    snapshot = rig.projects.snapshot(reservation.project_id)
    titles = {n["plan_ref"]: n["title"] for n in snapshot["nodes"]}
    assert titles == {"a1": "Describe each file", "a2": "a2"}
    rig.sql("INSERT INTO agent_nodes(id, project_id, role, runtime, state, created_at) VALUES (?, ?, 'planner', 'inline', 'done', ?)", PLANNER, reservation.project_id, BASE)
    assert [n["title"] for n in rig.projects.snapshot(reservation.project_id)["nodes"] if n["role"] == "planner"] == [""]


def test_the_projects_dollars_are_the_ledgers_steps_reviewer_planner_and_the_unpriced_are_counted_apart(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("INSERT INTO agent_nodes(id, project_id, role, runtime, state, created_at) VALUES (?, ?, 'planner', 'inline', 'done', ?)", PLANNER, reservation.project_id, BASE)
    ledger(rig, 0.30, task_id=tasks["a1"])
    ledger(rig, 0.20, task_id=tasks["a2"])
    ledger(rig, 0.07, node=PLANNER, purpose="chat_plan")                                   # the planner's three calls are rows of the org chat, no task
    ledger(rig, 0.03, node=PLANNER, purpose="chat_plan")
    ledger(rig, None, task_id=tasks["a1"])                                                  # a call that reported no dollars
    ledger(rig, 9.0, node="nd_" + "b" * 12, purpose="chat_plan")                           # another project's planner: not ours
    ledger(rig, 9.0, task_id=None, node=None, purpose="chat_plan")                          # an ordinary org-chat call: not ours
    ledger(rig, 5.0, task_id=tasks["a1"], provider="stub")                                  # a stub call costs nothing
    spend = rig.projects.snapshot(reservation.project_id)["spend"]
    assert spend["usd"] == 0.6 and spend["unpriced"] == 1
    assert spend["calls"] == 3, "credits count the steps' own calls, as before"


def test_a_project_with_no_calls_says_no_dollars_and_the_planner_alone_is_shown(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    assert rig.projects.snapshot(reservation.project_id)["spend"] == {"calls": 0, "usd": None, "unpriced": 0}
    rig.sql("INSERT INTO agent_nodes(id, project_id, role, runtime, state, created_at) VALUES (?, ?, 'planner', 'inline', 'done', ?)", PLANNER, reservation.project_id, BASE)
    ledger(rig, 0.05, node=PLANNER, purpose="chat_plan")
    assert rig.projects.snapshot(reservation.project_id)["spend"]["usd"] == 0.05


def test_each_step_carries_its_calls_dollars_and_minutes_every_attempt_counted(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("UPDATE tasks SET started_at = ?, ended_at = ? WHERE id = ?", BASE + 60, BASE + 60 + 150, tasks["a1"])        # 2.5 minutes
    ledger(rig, 0.30, task_id=tasks["a1"])
    ledger(rig, 0.20, task_id=tasks["a1"])
    ledger(rig, None, task_id=tasks["a1"])
    ledger(rig, 5.00, task_id=tasks["a2"], provider="stub")
    by_ref = {n["plan_ref"]: n for n in rig.projects.snapshot(reservation.project_id)["nodes"]}
    assert (by_ref["a1"]["calls"], by_ref["a1"]["usd"], by_ref["a1"]["minutes"]) == (3, 0.5, 2.5)
    assert by_ref["a2"]["calls"] == 0 and by_ref["a2"]["usd"] is None, "a step that has made no call has nothing used"


def test_minutes_run_from_the_first_attempt_to_the_last_end(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    rig.sql("UPDATE tasks SET started_at = ?, ended_at = ?, status = 'crashed' WHERE id = ?", BASE + 0, BASE + 120, tasks["a1"])
    rig.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, parent_task_id, created_at, started_at, ended_at) "
            "SELECT 'tsk_aaaaaaaaaaaa', dept_id, title, user_text, 'done', ?, created_at, ?, ? FROM tasks WHERE id = ?", tasks["a1"], BASE + 600, BASE + 720, tasks["a1"])
    rig.sql("UPDATE agent_nodes SET task_id = 'tsk_aaaaaaaaaaaa' WHERE plan_ref = 'a1' AND project_id = ?", reservation.project_id)
    ledger(rig, 0.1, task_id=tasks["a1"])
    ledger(rig, 0.1, task_id="tsk_aaaaaaaaaaaa")
    node = next(n for n in rig.projects.snapshot(reservation.project_id)["nodes"] if n["plan_ref"] == "a1")
    assert node["minutes"] == 12.0 and node["calls"] == 2 and node["usd"] == 0.2


def test_a_step_whose_calls_carry_no_price_says_no_dollars_not_zero(rig):
    """m-6: an all-Codex step showed 'about $0.00'."""
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])])
    ledger(rig, None, task_id=tasks["a1"], provider="codex")
    ledger(rig, None, task_id=tasks["a1"], provider="codex")
    ledger(rig, 0.40, task_id=tasks["a2"])
    ledger(rig, None, task_id=tasks["a2"])
    by_ref = {n["plan_ref"]: n for n in rig.projects.snapshot(reservation.project_id)["nodes"]}
    assert (by_ref["a1"]["calls"], by_ref["a1"]["usd"]) == (2, None)
    assert (by_ref["a2"]["calls"], by_ref["a2"]["usd"]) == (2, 0.4), "one priced call: the dollars known so far, with 'about'"
