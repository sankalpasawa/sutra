"""Same-team lanes (MAN-10, D258, D323): with SUTRA_NODES_LANES two steps of ONE team may run together; without it they queue as they always did; an ordinary task still waits behind a live task of its
team (P11) and the team's chat and stop-live look at the team's own task only."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401


def build(db, settings, clock, events, tmp_path, lanes):
    rig = PRig(db, settings, clock, events, max_runs=6, max_live=12, nodes_lanes=lanes)
    rig.projects._folder_of = lambda: None
    return rig


def started(rig):
    return {s.task_id for s, *_ in rig.t.launcher.started}


@pytest.fixture
def lanes_on(db, settings, clock, events, tmp_path):
    return build(db, settings, clock, events, tmp_path, True)


@pytest.fixture
def lanes_off(db, settings, clock, events, tmp_path):
    return build(db, settings, clock, events, tmp_path, False)


def test_with_lanes_on_two_steps_of_one_team_start_together_each_in_its_own_lane(lanes_on):
    rig = lanes_on
    reservation, tasks = rig.request([("a1", "legal", []), ("a2", "legal", [])])
    rig.start()
    assert started(rig) == {tasks["a1"], tasks["a2"]}
    lanes = {r["id"]: r["lane"] for r in rig.sql("SELECT id, lane FROM tasks")}
    assert lanes[tasks["a1"]] != lanes[tasks["a2"]] and all(lane.startswith("n") for lane in lanes.values())


def test_with_lanes_off_the_same_two_steps_queue_one_behind_the_other_as_before(lanes_off):
    rig = lanes_off
    reservation, tasks = rig.request([("a1", "legal", []), ("a2", "legal", [])])
    rig.start()
    assert len(started(rig)) == 1 and {r["lane"] for r in rig.sql("SELECT lane FROM tasks")} == {""}
    assert "waiting for the team" in rig.detail(next(t for t in tasks.values() if t not in started(rig)))


def test_an_ordinary_task_still_waits_behind_a_live_step_of_its_team_and_behind_a_live_ordinary_task(lanes_on):
    rig = lanes_on
    reservation, tasks = rig.request([("a1", "legal", []), ("a2", "sales", [])])
    rig.start()
    plain = rig.t.new("legal", "an ordinary task")
    rig.start()
    assert plain.id not in started(rig) and "waiting for the team" in rig.detail(plain.id)
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"])
    assert plain.id in set(rig.start()) | started(rig)
    second = rig.t.new("legal", "a second ordinary task")
    rig.start()
    assert second.id not in started(rig)                                                              # P11 for ordinary tasks


def test_a_step_in_a_lane_waits_behind_a_live_ordinary_task_of_its_team(lanes_on):
    rig = lanes_on
    plain = rig.t.new("legal", "an ordinary task")
    rig.start()
    reservation, tasks = rig.request([("a1", "legal", []), ("a2", "sales", [])])
    rig.start()
    assert plain.id in started(rig) and tasks["a1"] not in started(rig) and tasks["a2"] in started(rig)


def test_the_teams_own_task_is_the_one_the_team_chat_and_stop_live_look_at(lanes_on):
    rig = lanes_on
    reservation, tasks = rig.request([("a1", "legal", []), ("a2", "legal", [])])
    rig.start()
    conn = rig.t.db.conn()
    assert rig.t.service.store.live_in(conn, "legal") is None                                         # only steps in lanes are live: the team has no task of its own
    assert rig.t.service.stop_live("legal") is True and rig.t.status(tasks["a1"]) in ("starting", "running")      # a reset does not touch a step in a lane


def test_the_unique_index_still_forbids_two_live_ordinary_tasks_of_one_team(lanes_off):
    import sqlite3
    rig = lanes_off
    a, b = rig.t.new("legal", "one"), rig.t.new("legal", "two")
    rig.sql("UPDATE tasks SET status = 'running' WHERE id = ?", a.id)
    with pytest.raises(sqlite3.IntegrityError):
        rig.sql("UPDATE tasks SET status = 'running' WHERE id = ?", b.id)
