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
