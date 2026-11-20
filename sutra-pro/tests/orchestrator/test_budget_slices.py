"""Slices and the project ceiling (MAN-9; D271, D272, D300): the sum of the slices is never over the ceiling, unspent credits move only inside it, a node starts with its slice and cannot go past
it, and Decide for me never raises it."""
import json
import random

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.budgets import DEFAULT_SLICE, SCRUB_LIMIT, egress_scrubs, make_slices, move_unspent, unspent


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


def test_unspent_credits_move_only_between_steps_only_what_is_unspent_and_never_past_the_ceiling():
    slices, spent = [100, 100, 100], [30, 100, 0]
    assert move_unspent(slices, spent, 300, 0, 1, 50) == [50, 150, 100] and sum(move_unspent(slices, spent, 300, 0, 1, 50)) == 300
    assert move_unspent(slices, spent, 300, 0, 1, 71) == slices                          # more than the donor has left
    assert move_unspent(slices, spent, 300, 1, 2, 1) == slices                           # the donor spent it all
    assert move_unspent(slices, spent, 300, 0, 0, 10) == slices and move_unspent(slices, spent, 300, 0, 9, 10) == slices and move_unspent(slices, spent, 300, 0, 1, 0) == slices
    assert move_unspent(slices, spent, 250, 0, 1, 10) == slices                          # the slices are over the ceiling already: nothing moves
    assert unspent(100, 30) == 70 and unspent(100, 400) == 0


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
