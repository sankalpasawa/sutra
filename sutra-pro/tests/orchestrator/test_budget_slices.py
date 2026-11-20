"""Slices and the project ceiling (MAN-9; D271, D272, D300): the sum of the slices is never over the ceiling, a retry starts with what is left, a node starts with its slice and cannot go past
it, and Decide for me never raises it."""
import json
import random

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.budgets import DEFAULT_SLICE, SCRUB_LIMIT, chain_spend, egress_scrubs, make_slices, project_spend


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def test_the_sum_of_the_slices_is_never_over_the_ceiling_for_any_wants():
    rng = random.Random(7)
    for _ in range(500):
        wants = [rng.choice([0, 1, 5, 40, 100, 333, 10_000]) for _ in range(rng.randint(1, 12))]
        ceiling = rng.randint(0, 3_000)
        slices = make_slices(wants, ceiling)
        assert len(slices) == len(wants) and sum(slices) <= ceiling and all(s >= 0 for s in slices)
        if ceiling >= len(wants):
            assert all(s >= 1 for s in slices)
    assert make_slices([120, 80], None) == [120, 80] and make_slices([120, 80], 500) == [120, 80] and make_slices([0, "x", None]) == [1, DEFAULT_SLICE, DEFAULT_SLICE]


def test_a_slice_left_is_the_slice_minus_what_earlier_attempts_spent_and_never_a_fresh_one():
    from sutra_app.orchestrator.budgets import slice_left
    assert slice_left(100, 0) == 100 and slice_left(100, 30) == 70 and slice_left(100, 100) == 0 and slice_left(100, 400) == 0 and slice_left(100, -5) == 100


def test_a_project_gets_one_slice_per_node_and_the_ceiling_is_their_sum(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", []), ("a3", "ops", [])], estimates={"a1": 150, "a3": 50})
    slices = {n["plan_ref"]: n["slice_credits"] for n in rig.sql("SELECT plan_ref, slice_credits FROM agent_nodes WHERE role = 'worker'")}
    assert slices == {"a1": 150, "a2": DEFAULT_SLICE, "a3": 50} and rig.project(reservation.project_id)["budget_credits"] == 300


def test_a_node_starts_with_its_slice_as_the_budget_and_the_cap_and_the_tasks_own_settings_are_not_rewritten(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 150, "a2": 40})
    before = rig.sql("SELECT settings_json FROM tasks WHERE id = ?", tasks["a1"]).fetchone()[0]
    rig.start()
    spec = {s.task_id: s for s, *_ in rig.t.launcher.started}
    assert spec[tasks["a1"]].settings.J2_BUDGET == "150" and spec[tasks["a1"]].settings.J2_BUDGET_CAP == "150" and spec[tasks["a2"]].settings.J2_BUDGET == "40"
    assert rig.sql("SELECT settings_json FROM tasks WHERE id = ?", tasks["a1"]).fetchone()[0] == before
    written = json.loads((rig.t.run_dir(tasks["a1"]) / "task.json").read_text(encoding="utf-8"))
    assert written["settings"]["J2_BUDGET"] == "150" and written["settings"]["J2_BUDGET_CAP"] == "150"


def test_the_owners_own_budget_is_each_slice_and_a_retry_starts_with_the_same_slice(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], budget=70)
    assert {n["slice_credits"] for n in rig.sql("SELECT slice_credits FROM agent_nodes WHERE role = 'worker'")} == {70} and rig.project(reservation.project_id)["budget_credits"] == 140
    rig.start()
    rig.go(tasks["a1"])
    rig.sql("UPDATE agent_nodes SET slice_credits = 55 WHERE plan_ref = 'a1'")                   # the slice on the row is the truth, however the task was made
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)
    new = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]
    rig.start()
    started = {s.task_id: s for s, *_ in rig.t.launcher.started}
    assert started[new].settings.J2_BUDGET == "55"


def test_a_run_that_is_not_a_node_is_given_no_slice(rig):
    ordinary = rig.t.new("web", "plain")
    rig.start()
    spec = [s for s, *_ in rig.t.launcher.started if s.task_id == ordinary.id][0]
    assert spec.node is None and spec.settings.J2_BUDGET is None and spec.settings.J2_BUDGET_CAP is None


def test_the_egress_audit_is_counted_per_node_from_the_rows_where_something_was_scrubbed(tmp_path):
    path = tmp_path / "egress.jsonl"
    rows = [{"node": "nd_" + "a" * 12, "shapes": {"api-key": 1}}, {"node": "nd_" + "a" * 12, "shapes": {}}, {"node": "nd_" + "b" * 12, "shapes": {"secret-value": 2}},
            {"node": "nd_" + "a" * 12, "shapes": {"email": 1}}, {"shapes": {"api-key": 1}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    assert egress_scrubs(path) == {"nd_" + "a" * 12: 2, "nd_" + "b" * 12: 1} and egress_scrubs(path, ["nd_" + "b" * 12]) == {"nd_" + "b" * 12: 1}
    assert egress_scrubs(tmp_path / "missing.jsonl") == {} and SCRUB_LIMIT == 3


def ledger(rig, task_id, calls, usd_each=0.1, provider="claude"):
    for _ in range(calls):
        rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, ?, 'agent_turn', ?, ?)", 1793786400, provider, task_id, usd_each)


def test_a_retry_starts_with_its_slice_minus_what_the_first_attempt_spent(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 100, "a2": 100})
    rig.start()
    rig.go(tasks["a1"])
    ledger(rig, tasks["a1"], 30)
    ledger(rig, tasks["a1"], 5, provider="stub")                                                    # a stub call is free
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)
    new = rig.sql("SELECT task_id, slice_credits FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    rig.start()
    started = {s.task_id: s for s, *_ in rig.t.launcher.started}
    assert new["slice_credits"] == 100 and started[new["task_id"]].settings.J2_BUDGET == "70" == started[new["task_id"]].settings.J2_BUDGET_CAP
    assert chain_spend(rig.t.db.conn(), new["task_id"]) == (30, pytest.approx(3.0))


def test_a_node_that_used_up_its_slice_is_not_tried_again(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], estimates={"a1": 20, "a2": 20})
    rig.start()
    rig.go(tasks["a1"])
    ledger(rig, tasks["a1"], 25)
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)
    node = rig.sql("SELECT * FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()
    assert node["state"] == "failed" and node["attempt"] == 1 and "used up all its credits" in node["failure_reason"]


def test_the_dollar_total_and_the_snapshot_count_every_attempt_of_every_node(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    rig.go(tasks["a1"])
    ledger(rig, tasks["a1"], 2, usd_each=0.4)
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)
    new = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]
    ledger(rig, new, 1, usd_each=0.1)
    assert project_spend(rig.t.db.conn(), reservation.project_id) == (3, pytest.approx(0.9))
    assert rig.projects.snapshot(reservation.project_id)["spend"] == {"calls": 3, "usd": pytest.approx(0.9)}


def test_the_ceiling_is_what_the_owner_agreed_to_the_estimate_they_are_asked_about_or_the_sum_of_the_default_slices(rig):          # PA-2
    from sutra_app.orchestrator.projects import ProjectStep
    wants = [ProjectStep(f"a{i}", "web", estimate_credits=900) for i in range(1, 3)]
    reservation = rig.projects.reserve("req-big", "t", wants, decide_for_me=True)                  # 1800 is over the cap of 1000: the owner must say yes; Decide for me may not
    project = rig.project(reservation.project_id)
    [asked] = rig.store.approvals(reservation.project_id, status="open")
    assert project["status"] == "awaiting_approval" and asked.request["kind"] == "plan_estimate"
    assert project["budget_credits"] == asked.request["credits"] == 1800                              # the number the owner is asked about IS the ceiling: no step can be given more, and none is cut below what was approved
    plain = rig.projects.reserve("req-4", "t", [ProjectStep(f"a{i}", "web") for i in range(1, 5)])
    slices = [n["slice_credits"] for n in rig.sql("SELECT slice_credits FROM agent_nodes WHERE project_id = ?", plain.project_id)]
    assert slices == [100] * 4 and rig.project(plain.project_id)["budget_credits"] == sum(slices) == 400 and rig.store.approvals(plain.project_id, status="open") == []
    owner = rig.projects.reserve("req-own", "t", [ProjectStep(f"a{i}", "web", estimate_credits=900) for i in range(1, 4)], budget=250)
    assert [n["slice_credits"] for n in rig.sql("SELECT slice_credits FROM agent_nodes WHERE project_id = ?", owner.project_id)] == [250] * 3          # the owner's number wins over the planner's guess
