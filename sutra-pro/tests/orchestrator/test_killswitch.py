"""The kill switch and pause (MAN-4, guardrails 7; D279): the two files, what they mean, and the node controls that use the one stop ladder (`ProcessLauncher.stop`, here through
`FakeLauncher`, which records the pids it was asked to stop). Nothing new kills a process."""
import asyncio
import json
import os
import stat

import pytest
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.grants import StepRequest, intersect
from sutra_app.orchestrator.killswitch import KILL_FILE, KILL_OUTCOME, PAUSE_FILE, KillSwitch, NodeControl
from sutra_app.orchestrator.nodes_store import NodeStore
from sutra_app.orchestrator.testing.fake_engine import ev

PROJECT = "prj_" + "1" * 12


# ---- the two files --------------------------------------------------------------------------------------------------------------

@pytest.fixture
def switch(tmp_path):
    return KillSwitch(tmp_path / "data" / "nodes")


def test_with_no_file_agents_may_start_and_nothing_is_created(switch):
    assert (switch.level(), switch.allows_spawn(), switch.held(), switch.killed, switch.paused) == ("none", True, "", False, False)
    assert switch.status() == {"level": "none", "kill": None, "pause": None} and switch.stamp() is None
    assert not switch.directory.exists()                                        # looking creates nothing


def test_a_file_made_by_hand_is_enough_and_removing_it_resumes(switch):
    switch.directory.mkdir(parents=True)
    (switch.directory / KILL_FILE).touch()
    assert switch.level() == "kill" and not switch.allows_spawn() and "kill switch" in switch.held() and switch.status()["kill"] == {}
    (switch.directory / KILL_FILE).unlink()
    assert (switch.level(), switch.held()) == ("none", "")
    (switch.directory / PAUSE_FILE).touch()
    assert switch.level() == "pause" and "Paused" in switch.held() and not switch.allows_spawn()
    (switch.directory / PAUSE_FILE).unlink()
    assert switch.allows_spawn()


def test_kill_beats_pause_and_both_can_be_there(switch):
    switch.set("pause", reason="lunch")
    switch.set("kill", reason="stop now")
    assert switch.level() == "kill" and switch.status()["pause"]["reason"] == "lunch"
    assert switch.clear(pause=False) == [KILL_FILE] and switch.level() == "pause"
    assert switch.clear() == [PAUSE_FILE] and switch.level() == "none" and switch.clear() == []


def test_set_writes_a_private_small_json_note_with_who_why_and_when(switch):
    switch.set("kill", by="owner", reason="  line one\nline two  " + "x" * 300)
    path = switch.directory / KILL_FILE
    note = json.loads(path.read_text(encoding="utf-8"))
    assert note["v"] == 1 and note["by"] == "owner" and note["reason"].startswith("line one line two xxx") and len(note["reason"]) == 200 and note["at"].endswith("Z")
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(switch.directory.stat().st_mode) == 0o700
    assert switch.status()["kill"] == {key: note[key] for key in ("by", "reason", "at")}
    assert [p.name for p in switch.directory.iterdir()] == [KILL_FILE]            # no temp file is left behind


def test_set_refuses_a_level_that_is_not_pause_or_kill(switch):
    for level in ("none", "resume", "", "KILL"):
        with pytest.raises(ValueError):
            switch.set(level)
    assert not switch.directory.exists()


def test_a_folder_a_link_or_a_file_that_cannot_be_looked_at_counts_as_present(switch, monkeypatch, tmp_path):
    switch.directory.mkdir(parents=True)
    (switch.directory / KILL_FILE).mkdir()
    assert switch.killed and switch.clear() == [KILL_FILE] and not switch.killed
    if os.name == "posix":
        os.symlink(tmp_path / "nowhere", switch.directory / PAUSE_FILE)
        assert switch.paused                                                       # a broken link: somebody put it there
        assert switch.clear() == [PAUSE_FILE] and not os.path.lexists(switch.directory / PAUSE_FILE)
    real = os.lstat

    def refuse(path, *a, **k):
        if str(path).endswith(KILL_FILE):
            raise PermissionError("no")
        return real(path, *a, **k)

    monkeypatch.setattr(os, "lstat", refuse)
    assert switch.killed and switch.level() == "kill"                              # fails closed


def test_a_nodes_folder_that_is_a_file_fails_closed(tmp_path):
    """Minor 3: a part of the path that is a file (swapped, or wrong from the start) cannot be looked inside: not known, so nothing starts. (It once read as "nothing is there".)"""
    (tmp_path / "nodes").write_text("x")
    assert KillSwitch(tmp_path / "nodes").level() == "kill"


def test_the_stamp_changes_with_a_new_file_so_each_kill_is_dealt_with_once(switch):
    assert switch.stamp() is None
    switch.set("kill", reason="one")
    first = switch.stamp()
    assert first is not None and switch.stamp() == first
    switch.set("kill", reason="a longer reason than before")
    assert switch.stamp() != first


# ---- the node controls over the real task service ---------------------------------------------------------------------------------

def seed_node(t, task_id, n, role="worker"):
    node = f"nd_{n:012x}"
    grant = intersect("reviewer" if role == "reviewer" else "worker", StepRequest(), "edit", "edit", grant_id=f"gr_{n:012x}", node_id=node)
    t.sql("INSERT OR IGNORE INTO projects(id, created_at) VALUES (?, 1)", PROJECT)
    t.sql("INSERT INTO agent_nodes(id, project_id, task_id, role, runtime, state, grants_json, created_at) VALUES (?,?,?,?,?,?,?,1)", node, PROJECT, task_id, role, "engine", "running",
          json.dumps(grant.to_json()))
    return node


def seed_raw(t, task_id, n, grants_json, role="worker"):
    """A node row with whatever is in its `grants_json`."""
    t.sql("INSERT OR IGNORE INTO projects(id, created_at) VALUES (?, 1)", PROJECT)
    t.sql("INSERT INTO agent_nodes(id, project_id, task_id, role, runtime, state, grants_json, created_at) VALUES (?,?,?,?,?,?,?,1)", f"nd_{n:012x}", PROJECT, task_id, role, "engine", "queued",
          grants_json)
    return f"nd_{n:012x}"


class Rig:
    def __init__(self, tenv):
        self.t = tenv
        self.switch = KillSwitch(tenv.settings.data_dir / "nodes", clock=tenv.clock)
        self.store = NodeStore(tenv.db, ids=tenv.ids)
        self.kicks = 0

        async def kick():
            self.kicks += 1

        self.control = NodeControl(self.switch, tasks=tenv.service, db=tenv.db, store=self.store, clock=tenv.clock, kick=kick)
        tenv.service.task_gate = self.control.gate                                     # what the wiring does while SUTRA_NODES_V1 is on
        tenv.service.spawn_guard = self.control.spawn_guard

    def audit(self):
        return [(r["action"], r["actor"], r["node_id"]) for r in self.store.audit_rows(limit=500)]

    def node_state(self, node):
        return self.t.one("SELECT state FROM agent_nodes WHERE id = ?", node)


@pytest.fixture
def rig(tenv):
    return Rig(tenv)


def two_live_nodes(rig):
    """Two nodes of two teams, both running, and one ordinary task of a third that has nothing to do with nodes."""
    t = rig.t
    a, b = t.new("web", "node one"), t.new("sales", "node two")
    t.run(t.service.start_ready())
    for task in (a, b):
        t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
        t.drain(task.id)
    return a, b, seed_node(t, a.id, 1), seed_node(t, b.id, 2)


def test_kill_all_stops_every_live_node_through_the_ladder_writes_the_file_and_audits_it(rig):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    pids = {t.row(a.id).pid, t.row(b.id).pid}
    assert rig.t.run(rig.control.kill_all(by="owner", reason="enough")) == 2
    assert set(t.launcher.stopped) == pids and rig.switch.level() == "kill"
    assert (t.status(a.id), t.status(b.id)) == ("stopped", "stopped") and t.row(a.id).outcome == KILL_OUTCOME
    assert (rig.node_state(na), rig.node_state(nb)) == ("cancelled", "cancelled")
    audit = rig.audit()
    assert ("node.stopped", "system", na) in audit and ("node.stopped", "system", nb) in audit and ("kill", "owner", None) in audit
    assert "enough" in rig.store.audit_rows()[-1]["reason"] and "2 node(s)" in rig.store.audit_rows()[-1]["reason"]


def test_kill_all_does_not_touch_an_ordinary_task_that_is_not_a_node(rig):
    t = rig.t
    ordinary, node_task = t.new("web", "plain task"), t.new("sales", "node task")
    t.run(t.service.start_ready())
    for task in (ordinary, node_task):
        t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
        t.drain(task.id)
    seed_node(t, node_task.id, 1)
    assert t.run(rig.control.kill_all(reason="x")) == 1
    assert t.status(ordinary.id) == "running" and t.launcher.stopped == [t.row(node_task.id).pid]


def waiting_detail(t, task_id):
    return t.one("SELECT detail FROM graph_nodes WHERE task_id = ? AND step_ref = 'task'", task_id)


def test_with_a_file_there_no_node_starts_and_it_says_why_and_removing_it_lets_it_start_by_itself(rig):
    t = rig.t
    live = t.new("web", "running node")
    t.run(t.service.start_ready())
    t.write_events(live.id, ev("run.started", pid=t.row(live.id).pid, schema="events/1", mock=True, seed="none"))
    t.drain(live.id)
    queued = t.new("web", "waiting node")                                           # same team: it waits behind the running one
    seed_node(t, live.id, 1)
    seed_node(t, queued.id, 2)
    assert t.run(rig.control.kill_all()) == 1
    assert t.status(live.id) == "stopped" and t.status(queued.id) == "queued"      # the stop frees the team, and still the second node does not start
    assert "kill switch" in waiting_detail(t, queued.id) and t.launcher.stopped == [t.row(live.id).pid]
    assert t.run(t.service.start_ready()) == [] and t.status(queued.id) == "queued"
    t.run(rig.control.resume())
    assert t.run(t.service.start_ready()) == [queued.id] and t.status(queued.id) == "starting"


def test_pause_holds_a_node_that_has_not_started_and_never_an_ordinary_task(rig):
    t = rig.t
    node_task, ordinary = t.new("web", "a node"), t.new("sales", "an ordinary task")
    seed_node(t, node_task.id, 1)
    rig.switch.set("pause", reason="lunch")
    assert t.run(t.service.start_ready()) == [ordinary.id]                          # the ordinary task starts as it always did
    assert t.status(node_task.id) == "queued" and "Paused" in waiting_detail(t, node_task.id)
    rig.switch.clear()
    assert t.run(t.service.start_ready()) == [node_task.id]


def test_the_gate_asks_the_files_first_and_the_table_only_when_something_holds(rig):
    t = rig.t
    task = t.new("web", "x")
    row = t.row(task.id)
    conn = t.db.conn()
    assert rig.control.gate(conn, 0, row) == ""                                     # no file: nothing asked of the database
    rig.switch.set("kill")
    assert rig.control.gate(conn, 0, row) == ""                                     # a file, but this task is not a node
    seed_node(t, task.id, 1)
    assert "kill switch" in rig.control.gate(conn, 0, row)


def test_resume_removes_both_files_audits_it_and_kicks_the_scheduler(rig):
    t = rig.t
    t.run(rig.control.pause_all(reason="lunch"))
    t.run(rig.control.kill_all(reason="stop"))
    assert rig.switch.level() == "kill"
    assert t.run(rig.control.resume()) is True
    assert rig.switch.level() == "none" and rig.kicks == 1 and rig.audit()[-1][0] == "resume"
    assert t.run(rig.control.resume()) is False and rig.kicks == 1                    # nothing to remove: no second audit row, no kick


def test_pause_all_writes_the_file_counts_the_nodes_that_wait_and_stops_none(rig):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    waiting = t.new("web", "waits behind node one")
    seed_node(t, waiting.id, 3)
    assert t.run(rig.control.pause_all(by="owner", reason="lunch")) == 1
    assert rig.switch.level() == "pause" and t.launcher.stopped == [] and (t.status(a.id), t.status(b.id)) == ("running", "running")
    assert [row[0] for row in rig.audit()] == ["pause"]


def test_stop_node_stops_that_one_node_audits_it_and_a_finished_or_unknown_node_is_false(rig):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    assert t.run(rig.control.stop_node(na)) is True
    assert (t.status(a.id), t.status(b.id)) == ("stopped", "running") and t.row(a.id).outcome == "stopped by you" and t.launcher.stopped == [t.row(a.id).pid]
    assert rig.node_state(na) == "cancelled" and rig.audit() == [("node.stopped", "owner", na)]
    assert t.run(rig.control.stop_node(na)) is False                                  # its task is over
    assert t.run(rig.control.stop_node("nd_" + "f" * 12)) is False
    assert rig.node_state(nb) == "running"


def test_stop_node_cancels_a_queued_node_without_a_process(rig):
    t = rig.t
    first = t.new("web", "first")
    t.run(t.service.start_ready())
    queued = t.new("web", "second")
    node = seed_node(t, queued.id, 2)
    assert t.run(rig.control.stop_node(node)) is True and t.status(queued.id) == "cancelled" and t.status(first.id) in ("starting", "running")
    assert t.launcher.stopped == []


def test_a_dependant_of_a_stopped_node_follows_the_usual_rule_for_a_task_that_ended_badly(rig):
    t = rig.t
    a = t.new("web", "upstream node")
    t.run(t.service.start_ready())
    dependant = t.new("sales", "needs the first", depends_on=[a.id])
    node = seed_node(t, a.id, 1)
    assert t.status(dependant.id) == "blocked"
    t.run(rig.control.stop_node(node))
    assert t.status(dependant.id) == "cancelled"


def test_the_watcher_runs_the_ladder_once_for_a_file_made_by_hand_and_again_for_a_new_one(rig):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    assert t.run(rig.control.enforce()) == 0 and rig.audit() == []                  # no file: one look, nothing else
    rig.switch.directory.mkdir(parents=True, exist_ok=True)
    (rig.switch.directory / KILL_FILE).touch()
    assert t.run(rig.control.enforce()) == 2 and set(t.launcher.stopped) == {t.row(a.id).pid, t.row(b.id).pid}
    assert [row[0] for row in rig.audit()].count("kill") == 1 and rig.audit()[-1][1] == "system"
    assert t.run(rig.control.enforce()) == 0 and [row[0] for row in rig.audit()].count("kill") == 1      # the same file again: nothing more
    c = t.new("web", "started after the kill")
    t.run(t.service.start_ready())
    t.write_events(c.id, ev("run.started", pid=t.row(c.id).pid, schema="events/1", mock=True, seed="none"))
    t.drain(c.id)
    seed_node(t, c.id, 3)
    assert t.run(rig.control.enforce()) == 1 and t.status(c.id) == "stopped"          # the SAME file: a node that is live behind it is stopped at the next tick (M1)
    assert [row[0] for row in rig.audit()].count("kill") == 1                         # and the kill is audited once
    (rig.switch.directory / KILL_FILE).unlink()
    assert t.run(rig.control.enforce()) == 0
    (rig.switch.directory / KILL_FILE).touch()
    os.utime(rig.switch.directory / KILL_FILE, ns=(1, 1))                            # a different file, so a different stamp: audited again
    assert t.run(rig.control.enforce()) == 0 and [row[0] for row in rig.audit()].count("kill") == 2


def test_the_watcher_loop_notices_a_file_and_ends_cleanly(rig):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)

    async def go():
        rig.control.start_watching(0.01)
        rig.control.start_watching(0.01)                                              # idempotent
        rig.switch.directory.mkdir(parents=True, exist_ok=True)
        (rig.switch.directory / KILL_FILE).touch()
        for _ in range(300):
            if t.status(a.id) == "stopped" and t.status(b.id) == "stopped":
                break
            await asyncio.sleep(0.01)
        await rig.control.stop_watching()
        await rig.control.stop_watching()

    t.run(go())
    assert (t.status(a.id), t.status(b.id)) == ("stopped", "stopped") and rig.control._watcher is None


def test_one_node_that_will_not_stop_does_not_keep_the_others_running(rig, monkeypatch):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    real = t.service.stop_node

    async def flaky(task_id, outcome="stopped by you", **kw):
        if task_id == a.id:
            raise RuntimeError("it will not stop")
        return await real(task_id, outcome, **kw)

    monkeypatch.setattr(t.service, "stop_node", flaky)
    assert t.run(rig.control.kill_all()) == 1 and t.status(b.id) == "stopped" and rig.switch.level() == "kill"


# ---- a node with no usable grant is held, never started (D302) ---------------------------------------------------------------------

def bad_grants(n):
    node = f"nd_{n:012x}"
    good = intersect("worker", StepRequest(), "edit", "edit", grant_id=f"gr_{n:012x}", node_id=node).to_json()
    reviewer = intersect("reviewer", StepRequest(), "edit", "edit", grant_id=f"gr_{n:012x}", node_id=node).to_json()
    return {
        "empty": "{}", "not json": "not json at all", "an array": "[1]", "a reviewer's grant on a worker": json.dumps(reviewer),
        "wider than the role table": json.dumps({**good, "tiers": [0, 1, 2, 3, 6]}), "tier 5": json.dumps({**good, "tiers": [0, 1, 2, 3, 5]}),
        "somebody else's grant": json.dumps({**good, "node_id": "nd_" + "e" * 12}), "no id": json.dumps({**good, "id": ""}), "an unknown field": json.dumps({**good, "surprise": 1}),
    }


@pytest.mark.parametrize("why", list(bad_grants(1)))
def test_a_node_whose_grant_is_missing_unreadable_too_wide_or_not_its_own_is_held_and_the_queue_goes_on(rig, why):
    t = rig.t
    broken, fine = t.new("web", "node with a bad grant"), t.new("sales", "an ordinary task behind it")
    seed_raw(t, broken.id, 1, bad_grants(1)[why])
    assert t.run(t.service.start_ready()) == [fine.id]                                # the held one does not stop the next from starting
    assert t.status(broken.id) == "queued" and "Held: this step has no permissions set, so it cannot start" in waiting_detail(t, broken.id)
    assert t.launcher.stopped == [] and not list((t.settings.data_dir / "departments" / "web" / "runs").glob("j2-*"))


def test_a_node_with_a_good_grant_starts_and_the_one_without_is_still_held_next_to_it(rig):
    t = rig.t
    good, broken = t.new("web", "good node"), t.new("sales", "broken node")
    seed_node(t, good.id, 1)
    seed_raw(t, broken.id, 2, "{}")
    assert t.run(t.service.start_ready()) == [good.id] and t.status(broken.id) == "queued"


def test_a_node_whose_grant_is_repaired_starts_by_itself_at_the_next_start_attempt(rig):
    t = rig.t
    task = t.new("web", "node")
    node = seed_raw(t, task.id, 1, "{}")
    assert t.run(t.service.start_ready()) == []
    grant = intersect("worker", StepRequest(), "edit", "edit", grant_id="gr_" + "1" * 12, node_id=node)
    t.sql("UPDATE agent_nodes SET grants_json = ? WHERE id = ?", json.dumps(grant.to_json()), node)
    assert t.run(t.service.start_ready()) == [task.id]


def test_the_gate_names_the_switch_before_the_grant_and_never_holds_an_ordinary_task(rig):
    t = rig.t
    task, ordinary = t.new("web", "node"), t.new("sales", "plain")
    seed_raw(t, task.id, 1, "{}")
    conn = t.db.conn()
    assert rig.control.gate(conn, 0, t.row(task.id)) == "Held: this step has no permissions set, so it cannot start" and rig.control.gate(conn, 0, t.row(ordinary.id)) == ""
    rig.switch.set("pause")
    assert "Paused" in rig.control.gate(conn, 0, t.row(task.id)) and rig.control.gate(conn, 0, t.row(ordinary.id)) == ""


# ---- the ladders run together (D303) --------------------------------------------------------------------------------------------------

def test_kill_all_with_three_stubborn_nodes_ends_in_about_one_ladders_time(db, settings, clock, events):
    """Each fake run ignores the stop line and holds for 0.5 s (its stop grace): one after the other that would be 1.5 s."""
    import time
    from orchestrator.test_tasks import tenv_with
    from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
    t = tenv_with(db, settings, clock, events, max_runs=3, max_live=6, launcher=FakeLauncher({"*": [{"ignore_stop": True}, {"hold": True}]}, stop_grace=0.5))
    from orchestrator.test_chart_store import dept_op
    t.env.apply(dept_op("$ops", "Ops"))                                               # a third team: the chart has web and sales
    rig = Rig(t)
    tasks = [t.new(dept, f"node in {dept}") for dept in ("web", "sales", "ops")]
    t.run(t.service.start_ready())
    for task in tasks:
        t.write_events(task.id, ev("run.started", pid=t.row(task.id).pid, schema="events/1", mock=True, seed="none"))
        t.drain(task.id)
    for n, task in enumerate(tasks, 1):
        seed_node(t, task.id, n)
    started = time.monotonic()
    assert t.run(rig.control.kill_all(reason="all of them")) == 3
    took = time.monotonic() - started
    assert took < 1.2, f"the ladders ran one after the other: {took:.2f} s"
    assert [t.status(task.id) for task in tasks] == ["stopped"] * 3 and len(t.launcher.stopped) == 3


def test_a_node_that_will_not_stop_is_logged_and_the_rest_still_end_together(rig, monkeypatch, caplog):
    import logging
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    real = t.service.stop_node

    async def flaky(task_id, outcome="stopped by you", **kw):
        if task_id == a.id:
            raise RuntimeError("it will not stop")
        return await real(task_id, outcome, **kw)

    monkeypatch.setattr(t.service, "stop_node", flaky)
    with caplog.at_level(logging.ERROR, logger="sutra_app.orchestrator.killswitch"):
        assert t.run(rig.control.kill_all()) == 1
    assert "could not stop node" in caplog.text and t.status(b.id) == "stopped"


# ---- a kill must not leave a node running: the start that was under way (M1) ------------------------------------------------------------

def fresh_rig(tenv_obj):
    return Rig(tenv_obj)


def test_a_kill_that_comes_after_the_task_is_marked_starting_and_before_its_process_is_not_lost(rig, monkeypatch):
    """The window: `_prepare_next` has committed `starting` and made the run folder; the owner kills; only then would the process start. It must not start."""
    t = rig.t
    task = t.new("web", "node")
    node = seed_node(t, task.id, 1)
    real = t.service._prepare_next

    def kill_in_the_window(*a, **k):
        prepared = real(*a, **k)
        if prepared is not None:
            rig.switch.set("kill", reason="in the window")
        return prepared

    monkeypatch.setattr(t.service, "_prepare_next", kill_in_the_window)
    t.run(t.service.start_ready())
    assert t.launcher.started == [] and t.status(task.id) == "stopped" and t.row(task.id).outcome == KILL_OUTCOME


def test_a_kill_that_comes_while_the_process_is_starting_stops_that_process(rig):
    t = rig.t
    task = t.new("web", "node")
    seed_node(t, task.id, 1)
    real_start = t.launcher.start

    async def start_then_kill(spec, run_dir):
        pid = await real_start(spec, run_dir)
        rig.switch.set("kill", reason="while it starts")                              # the file appears right after the process began, before the server stored its pid
        return pid

    t.launcher.start = start_then_kill
    t.run(t.service.start_ready())
    assert t.status(task.id) == "stopped" and t.launcher.stopped == [t.row(task.id).pid]      # the outcome is the run's own words: the engine ends a stopped run the same way for every stop


def test_stopping_a_node_that_is_still_starting_with_no_pid_leaves_no_process_running(rig):
    """The owner's stop arrives while the task is `starting` and has no pid: nothing to signal then, so the process that begins right after must be stopped by the launch itself."""
    import asyncio
    t = rig.t
    task = t.new("web", "node")
    node = seed_node(t, task.id, 1)
    real_start = t.launcher.start
    stops = []

    async def stop_first(spec, run_dir):
        assert t.row(task.id).status == "starting" and t.row(task.id).pid is None
        stops.append(asyncio.get_running_loop().create_task(rig.control.stop_node(node)))      # another request: it waits for the start loop's lock after it has ended the task
        for _ in range(60):
            await asyncio.sleep(0.01)
            if t.status(task.id) == "stopped":
                break
        return await real_start(spec, run_dir)

    async def go():
        await t.service.start_ready()
        return [await s for s in stops]

    t.launcher.start = stop_first
    assert t.run(go()) == [True]
    assert t.status(task.id) == "stopped" and len(t.launcher.started) == 1
    pid = next(iter(t.launcher._dirs))
    assert not t.launcher.alive(pid) and pid in t.launcher.stopped                    # the process that began after the stop was ended at once


def test_an_ordinary_task_is_never_ended_by_the_launch_guard(rig):
    t = rig.t
    plain = t.new("web", "plain")
    rig.switch.set("kill")
    assert t.run(t.service.start_ready()) == [plain.id] and t.status(plain.id) in ("starting", "running")


def test_the_launch_guard_asks_only_when_a_kill_file_is_there(rig):
    t = rig.t
    task = t.new("web", "node")
    seed_node(t, task.id, 1)
    conn = t.db.conn()
    assert rig.control.spawn_guard(conn, t.row(task.id)) == ""
    rig.switch.set("pause")
    assert rig.control.spawn_guard(conn, t.row(task.id)) == ""                         # a pause only holds what has not started
    rig.switch.set("kill")
    assert rig.control.spawn_guard(conn, t.row(task.id)) == KILL_OUTCOME


# ---- the kill file must not fail open (M2) ------------------------------------------------------------------------------------------

def test_kill_all_with_a_file_that_cannot_be_written_still_stops_everything_and_says_so(rig, monkeypatch, caplog):
    import logging
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    monkeypatch.setattr(rig.switch, "set", lambda *x, **k: (_ for _ in ()).throw(OSError("no space left on device")))
    with caplog.at_level(logging.ERROR, logger="sutra_app.orchestrator.killswitch"):
        result = t.run(rig.control.kill_all(reason="disk is full"))
    assert result == 2 and result.file_written is False
    assert (t.status(a.id), t.status(b.id)) == ("stopped", "stopped") and "could not be written" in caplog.text
    row = rig.store.audit_rows()[-1]
    assert row["action"] == "kill" and "could not be written" in row["reason"] and "disk is full" in row["reason"]


def test_the_kill_file_is_written_with_a_unique_temp_name_synced_and_cleaned_up_on_failure(switch, monkeypatch):
    seen = []
    real_open = os.open

    def spy(path, flags, *a, **k):
        seen.append((str(path), flags))
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", spy)
    synced = []
    monkeypatch.setattr(os, "fsync", lambda fd: synced.append(fd))
    switch.set("kill", reason="x")
    switch.set("kill", reason="y")
    temps = [p for p, f in seen if p.endswith(".tmp")]
    assert len(temps) == 2 and len(set(temps)) == 2 and all(f & os.O_EXCL for p, f in seen if p.endswith(".tmp")) and len(synced) == 2
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        switch.set("pause")
    assert sorted(p.name for p in switch.directory.iterdir()) == [KILL_FILE]                  # no temp file left, no half file
    assert switch.paused                                                                                                  # and the pause that could not be written is held in memory (Minor 3)


def test_a_stale_temp_file_of_the_same_kind_does_not_block_the_next_write(switch):
    switch.directory.mkdir(parents=True)
    (switch.directory / f".{KILL_FILE}.1.tmp").write_text("left by a crash")
    switch.set("kill", reason="again")
    assert switch.killed and switch.status()["kill"]["reason"] == "again"


# ---- reading and removing a file made by hand (m6) ----------------------------------------------------------------------------------

def test_a_huge_hand_made_kill_file_is_read_only_up_to_4_kb_and_its_words_are_clipped(switch):
    switch.directory.mkdir(parents=True)
    body = json.dumps({"by": "me", "reason": "r" * 5000, "at": "2026-11-20T10:00:00Z"})
    (switch.directory / KILL_FILE).write_text(body + " " * 10_000)
    note = switch.status()["kill"]
    assert note == {} or all(len(v) <= 200 for v in note.values())                                                  # the first 4 KB cut the JSON: it says nothing, and cost nothing
    (switch.directory / KILL_FILE).write_text(json.dumps({"by": "me" * 300, "reason": "line\none  two", "at": "x" * 500, "extra": "ignored"}))
    assert switch.status()["kill"] == {"by": ("me" * 300)[:200], "reason": "line one two", "at": "x" * 200}


@pytest.mark.skipif(os.name != "posix", reason="a pipe")
def test_a_pipe_named_kill_is_never_opened(switch):
    switch.directory.mkdir(parents=True)
    os.mkfifo(switch.directory / KILL_FILE)
    assert switch.killed and switch.status()["kill"] == {}                                                          # no hang
    assert switch.clear() == [KILL_FILE]


def test_clear_is_safe_when_kill_is_a_folder_with_something_in_it(switch, caplog):
    import logging
    switch.directory.mkdir(parents=True)
    (switch.directory / KILL_FILE).mkdir()
    (switch.directory / KILL_FILE / "keep.txt").write_text("the owner's own file")
    with caplog.at_level(logging.WARNING, logger="sutra_app.orchestrator.killswitch"):
        assert switch.clear() == []
    assert (switch.directory / KILL_FILE / "keep.txt").read_text() == "the owner's own file" and switch.killed and "could not be removed" in caplog.text
    (switch.directory / PAUSE_FILE).touch()
    assert switch.clear() == [PAUSE_FILE] and switch.killed                                                           # the pause went, the kill stays and still holds


# ---- a KILL file that cannot be written is held in memory (Minor 3) ---------------------------------------------------------------------

def test_a_switch_that_cannot_be_written_is_held_in_memory_until_it_is_cleared(tmp_path, monkeypatch):
    switch = KillSwitch(tmp_path / "nodes")
    monkeypatch.setattr(switch, "_write", lambda *a, **k: (_ for _ in ()).throw(PermissionError("read-only disk")))
    with pytest.raises(OSError):
        switch.set("kill", reason="disk is read-only")
    assert not (tmp_path / "nodes" / KILL_FILE).exists()
    assert switch.killed and switch.level() == "kill" and not switch.allows_spawn() and "Stopped" in switch.held()
    assert switch.status()["kill"]["by"] == "system"
    monkeypatch.undo()
    assert switch.clear(pause=False) == [KILL_FILE] and switch.level() == "none" and switch.clear() == []


def test_the_gate_still_holds_a_node_when_the_kill_file_could_not_be_written(rig, monkeypatch):
    t = rig.t
    a, b, na, nb = two_live_nodes(rig)
    monkeypatch.setattr(rig.switch, "_write", lambda *x, **k: (_ for _ in ()).throw(OSError("no space left on device")))
    result = t.run(rig.control.kill_all(reason="disk is full"))
    assert result.file_written is False and not (rig.switch.directory / KILL_FILE).exists() and rig.switch.level() == "kill"
    waiting = t.new("web", "a node that waits for the team")
    seed_node(t, waiting.id, 3)
    assert "kill switch" in rig.control.gate(t.db.conn(), 0, t.row(waiting.id)) and rig.control.spawn_guard(t.db.conn(), t.row(waiting.id)) == KILL_OUTCOME
    assert t.run(rig.control.resume()) is True and rig.switch.level() == "none"                      # resume lets the memory go too
