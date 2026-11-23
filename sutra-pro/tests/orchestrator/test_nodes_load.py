"""Many nodes at once (MAN-12, MAN-6): 24 stand-in nodes, each writing heartbeats and events while 8 threads drain them into the one SQLite writer. What is measured: the writes to `tasks` (a node's
heartbeat-only batch writes nothing with coalescing), that no write ever waits past the busy timeout (`StoreBusy` is zero), that a page that replays the event bus after every round never meets a gap
(the ring holds 1000 events), and that a hand-off is taken in at most a few milliseconds. The numbers are printed (run with -s) and written in dev-notes."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_tasks import ev

from sutra_app.orchestrator.db import StoreBusy
from sutra_app.orchestrator.events import EventBus

NODES, ROUNDS, THREADS = 24, 40, 8


@pytest.fixture
def world(db, settings, clock, events):
    rig = PRig(db, settings, clock, events, max_runs=40, max_live=60)
    tasks = [rig.t.new("web", f"stand-in node {i}") for i in range(NODES)]
    for i, task in enumerate(tasks):
        rig.sql("UPDATE tasks SET lane = ? WHERE id = ?", f"l{i}", task.id)                              # one live task per (team, lane): 24 live tasks of one team
    rig.t.run(rig.t.service.start_ready())
    for task in tasks:
        rig.go(task.id)
    rig.tasks = [t.id for t in tasks]
    return rig


def run(world, coalesce):
    rig = world
    rig.t.projector.coalesce = (lambda tx, row: True) if coalesce else None
    touches, lock, busy = [0], threading.Lock(), [0]
    real = rig.t.projector.store.touch

    def counting(*a, **k):
        with lock:
            touches[0] += 1
        return real(*a, **k)
    rig.t.projector.store.touch = counting
    bus, gaps, seen = EventBus(), [0], [0]
    after = bus.head
    started = time.monotonic()
    pool = ThreadPoolExecutor(THREADS)
    try:
        for round_ in range(ROUNDS):
            for task_id in rig.tasks:
                rig.t.write_events(task_id, {"t": "heartbeat", "at": f"2026-11-04T10:{round_ // 60:02d}:{round_ % 60:02d}Z"})

            def drain(task_id):
                try:
                    rig.t.projector.drain(task_id)
                except StoreBusy:
                    with lock:
                        busy[0] += 1
            list(pool.map(drain, rig.tasks))
            bus.publish(list(rig.t.env.events.events[seen[0]:]))
            seen[0] = len(rig.t.env.events.events)
            found = bus.replay(after)
            gaps[0] += 1 if found.resync == "gap" else 0
            after = bus.head
    finally:
        pool.shutdown()
        rig.t.projector.store.touch = real
    return {"touches": touches[0], "busy": busy[0], "gaps": gaps[0], "seconds": round(time.monotonic() - started, 2), "events": seen[0]}


def test_24_nodes_with_heartbeats_never_meet_the_busy_timeout_and_coalescing_cuts_the_writes(world, capsys):
    off = run(world, coalesce=False)
    on = run(world, coalesce=True)
    print("LOAD", json.dumps({"nodes": NODES, "rounds": ROUNDS, "threads": THREADS, "without_coalescing": off, "with_coalescing": on}))
    assert off["busy"] == 0 and on["busy"] == 0 and off["gaps"] == 0 and on["gaps"] == 0
    assert off["touches"] == NODES * ROUNDS and on["touches"] < off["touches"] // 3
    assert world.t.run(world.t.service.start_ready()) is not None


def test_a_hand_off_is_taken_in_quickly_while_many_nodes_beat(world):
    rig = world
    reservation, tasks = rig.request([("a1", "sales", []), ("a2", "ops", [])])
    rig.start()
    rig.go(tasks["a1"])
    stop = threading.Event()

    def beat():
        while not stop.is_set():
            for task_id in rig.tasks[:12]:
                rig.t.write_events(task_id, {"t": "heartbeat"})
                try:
                    rig.t.projector.drain(task_id)
                except StoreBusy:
                    pass
    worker = threading.Thread(target=beat)
    worker.start()
    try:
        began = time.monotonic()
        rig.finish(tasks["a1"], files={"out.md": "x" * 100_000})
        took = time.monotonic() - began
    finally:
        stop.set()
        worker.join(5)
    assert rig.node_of(tasks["a1"])["state"] == "done" and took < 3.0
    print("LOAD hand-off with 12 nodes beating:", round(took, 3), "s")


def test_coalescing_is_only_for_the_tasks_it_is_asked_about_a_late_beat_is_written_and_a_replay_is_harmless(world):
    rig = world
    task_id = rig.tasks[0]
    projector = rig.t.projector
    projector.coalesce = lambda tx, row: row.id == task_id
    first = projector.drain(task_id)                                                                    # nothing new yet
    rig.t.write_events(task_id, {"t": "heartbeat", "at": "2026-11-04T10:00:05Z"})
    before = rig.t.row(task_id)
    projector.drain(task_id)
    assert rig.t.row(task_id).events_offset == before.events_offset and rig.t.row(task_id).last_event_at == before.last_event_at        # within 15 s of the last event: nothing written
    projector.drain(task_id)                                                                           # the same line is read again: still harmless
    assert rig.t.row(task_id).last_event_at == before.last_event_at and first is not None
    rig.t.write_events(task_id, {"t": "heartbeat", "at": "2026-11-04T10:05:00Z"})                      # minutes later: written, the lease follows it
    projector.drain(task_id)
    assert rig.t.row(task_id).last_event_at > before.last_event_at
    other = rig.tasks[1]
    rig.t.write_events(other, {"t": "heartbeat", "at": "2026-11-04T10:00:05Z"})
    offset = rig.t.row(other).events_offset
    projector.drain(other)
    assert rig.t.row(other).events_offset > offset                                                      # a task it was not asked about is written as always
