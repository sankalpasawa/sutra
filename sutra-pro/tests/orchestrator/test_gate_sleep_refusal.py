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


def test_a_tick_whose_own_stops_took_long_is_not_read_as_a_sleep_but_a_real_gap_still_is(rig, clock, monkeypatch):
    """G2 (D311): the gap is measured from the END of a tick to the start of the next, so a tick that spent 50 s on its stop ladders does not make the next one look like a sleep."""
    reservation, tasks = with_open_gate(rig)
    conductor = rig.projects.conductor
    real = conductor._tick_sync

    def slow(now, gap):
        done = real(now, gap)
        clock.advance(50)                                                    # the stop ladders of this tick took 50 s
        return done
    tick(rig, 10)
    monkeypatch.setattr(conductor, "_tick_sync", slow)
    tick(rig, 20)                                                              # ends about 50 s later
    monkeypatch.setattr(conductor, "_tick_sync", real)
    normal = tick(rig, 75)                                                     # 55 s after the start of the slow tick, 5 s after its end: not a sleep (the old reading: 55 > 45)
    assert normal["refused"] == [] and normal["extended"] == [] and rig.project(reservation.project_id)["status"] == "running"
    assert len(rig.store.approvals(reservation.project_id)) == 1 and rig.store.approvals(reservation.project_id)[0].status == "open"
    woke = tick(rig, 75 + 60 + 6)                                              # a real gap of 60 s after the last tick ended: still a sleep
    assert woke["refused"] == [reservation.project_id]


# ---- a stop answers the open questions; no half-done refusal; a project that waits for nothing (MJ7) ---------------------------------------

def test_stopping_a_project_denies_its_open_questions_by_the_owner_and_a_kill_by_the_system(rig):
    reservation, tasks = with_open_gate(rig)
    rig.t.run(rig.projects.stop(reservation.project_id))
    [approval] = rig.store.approvals(reservation.project_id)
    assert approval.status == "denied" and approval.decided_by == "owner" and [r["action"] for r in rig.audit("approval.denied")] == ["approval.denied"]
    second, more = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2")
    with rig.t.db.tx() as tx:
        rig.store.open_approval(tx, project_id=second.project_id, node_id=rig.node_of(more["b1"])["id"], tier=4, request={"why": "read GitHub"}, expires_at=BASE + 86_400)
    ids = rig.projects.begin_kill("stopped by the kill switch")
    assert second.project_id in ids
    [asked] = rig.store.approvals(second.project_id)
    assert asked.status == "denied" and asked.decided_by == "system" and rig.project(second.project_id)["status"] == "stopped"


def test_a_project_that_waits_for_an_answer_with_no_question_open_is_ended_by_the_tick(rig):
    reservation, tasks = with_open_gate(rig)
    rig.sql("UPDATE projects SET status = 'awaiting_approval' WHERE id = ?", reservation.project_id)
    rig.sql("UPDATE approvals SET status = 'denied', decided_by = 'owner' WHERE project_id = ?", reservation.project_id)          # answered, but nothing moved the project on
    done = tick(rig, 10)
    project = rig.project(reservation.project_id)
    assert done["refused"] == [reservation.project_id] and project["status"] == "stopped" and project["stop_reason"].startswith("not approved")


def test_the_refusal_is_one_transaction_a_failure_half_way_leaves_the_gate_open_and_the_next_tick_finishes_it(rig, monkeypatch):
    reservation, tasks = with_open_gate(rig, expires=BASE + 500)
    conductor = rig.projects.conductor
    real = conductor._receipt
    monkeypatch.setattr(conductor, "_receipt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash while writing the receipt")))
    with pytest.raises(RuntimeError):
        tick(rig, 600)                                                                                 # the question ran out, then the stop failed
    assert [a.status for a in rig.store.approvals(reservation.project_id)] == ["open"] and rig.project(reservation.project_id)["status"] in ("running", "awaiting_approval")
    monkeypatch.setattr(conductor, "_receipt", real)
    assert tick(rig, 700)["refused"] == [reservation.project_id] and rig.project(reservation.project_id)["status"] == "stopped"
    assert [a.status for a in rig.store.approvals(reservation.project_id)] == ["expired"]
