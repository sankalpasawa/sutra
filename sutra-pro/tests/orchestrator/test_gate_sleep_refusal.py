"""A closed laptop is a refusal (D296; MAN-7 detection, tested here at the project layer): a sleep or a close while a gate is open refuses every open gate of the project, cancels the nodes that waited,
stops the ones that run, stops the project and leaves one receipt line. A project with no open gate keeps the one-time lease extension. An open gate also ends after 24 hours."""
import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.nodes_store import GATE_REFUSED_CLOSED, GATE_REFUSED_SLEEP, PROJECT_STOPPED_ACTION

BASE = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=5, max_live=10)


def with_open_gate(rig, expires=BASE + 86_400):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"]), ("a3", "ops", [])])
    rig.start()
    for ref in ("a1", "a3"):
        rig.go(tasks[ref])
    with rig.t.db.tx() as tx:
        rig.store.open_approval(tx, project_id=reservation.project_id, node_id=rig.node_of(tasks["a2"])["id"], tier=4, request={"why": "read GitHub"}, expires_at=expires)
    return reservation, tasks


def tick(rig, seconds):
    return rig.t.run(rig.projects.tick(now=BASE + seconds))


def test_a_sleep_with_an_open_gate_refuses_it_stops_the_running_nodes_and_the_project_and_says_why_once(rig):
    reservation, tasks = with_open_gate(rig)
    tick(rig, 10)
    done = tick(rig, 3000)                                                                              # the tick came 2990 s late: the computer slept
    assert done["refused"] == [reservation.project_id] and done["extended"] == []
    project = rig.project(reservation.project_id)
    assert project["status"] == "stopped" and project["stop_reason"] == GATE_REFUSED_SLEEP == "the computer went to sleep before you answered"
    assert rig.node_states(tasks) == {"a1": "cancelled", "a2": "cancelled", "a3": "cancelled"} and len(rig.t.launcher.stopped) == 2        # two ran: both stopped by the ladder together
    approvals = rig.store.approvals(reservation.project_id)
    assert [a.status for a in approvals] == ["denied"] and approvals[0].decided_by == "system"
    assert [r["reason"] for r in rig.audit("gate.refused")] == [GATE_REFUSED_SLEEP] and [r["action"] for r in rig.audit(PROJECT_STOPPED_ACTION)] == [PROJECT_STOPPED_ACTION]
    notes = rig.sql("SELECT text FROM chat_messages WHERE src_ref = ?", f"project:{reservation.project_id}#stopped").fetchall()
    assert len(notes) == 1 and GATE_REFUSED_SLEEP in notes[0]["text"]
    assert tick(rig, 3010) == {"expired": [], "refused": [], "stopped": [], "extended": []}               # nothing is left to do, and nothing is done twice
    assert rig.start() == []


def test_a_project_with_no_open_gate_is_not_stopped_by_a_sleep_only_its_leases_are_extended_once(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])])
    rig.start()
    for task_id in tasks.values():
        rig.go(task_id)
    tick(rig, 10)
    woke = tick(rig, 3000)
    assert woke["refused"] == [] and len(woke["extended"]) == 2 and rig.project(reservation.project_id)["status"] == "running" and rig.t.launcher.stopped == []


def test_a_gate_that_ran_out_after_24_hours_is_refused_with_not_approved(rig):
    reservation, tasks = with_open_gate(rig, expires=BASE + 500)
    done = tick(rig, 600)
    assert done["refused"] == [reservation.project_id]
    assert rig.project(reservation.project_id)["status"] == "stopped" and rig.project(reservation.project_id)["stop_reason"].startswith("not approved")
    assert [a.status for a in rig.store.approvals(reservation.project_id)] == ["expired"] and rig.node_states(tasks) == {"a1": "cancelled", "a2": "cancelled", "a3": "cancelled"}


def test_the_gate_of_one_project_does_not_stop_another(rig):
    first, t1 = with_open_gate(rig)
    second, t2 = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2")
    rig.start()
    tick(rig, 10)
    tick(rig, 3000)
    assert rig.project(first.project_id)["status"] == "stopped" and rig.project(second.project_id)["status"] == "running"


def test_a_project_stopped_by_a_closed_laptop_is_not_started_again_by_itself(rig):
    reservation, tasks = with_open_gate(rig)
    tick(rig, 10)
    tick(rig, 3000)
    assert rig.start() == [] and rig.t.run(rig.control.resume()) is False
    assert rig.project(reservation.project_id)["status"] == "stopped"


def test_the_words_are_the_decided_ones():
    assert GATE_REFUSED_CLOSED == "Sutra was closed before you answered" and GATE_REFUSED_SLEEP == "the computer went to sleep before you answered"
