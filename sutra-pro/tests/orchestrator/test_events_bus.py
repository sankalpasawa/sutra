"""EventBus (ORCH-2): numbering, the ring, replay and resync reasons, control events, topics, thread safety, slow streams, close."""
import asyncio
import logging
import threading

import pytest

from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.events import (
    CONTROL_TYPES, MAX_PENDING, RING_SIZE, EventBus, event_type_ok, topic_matches, topic_of,
)
from sutra_app.orchestrator.models import Event
from sutra_app.orchestrator.testing import FakeClock


def ev(type="chat.message", **data) -> Event:
    return Event(seq=0, at="2026-11-04T10:00:00Z", type=type, data=data)


def fill(bus: EventBus, n: int, type="chat.message") -> None:
    for i in range(n):
        bus.publish_one(type, {"i": i})


def run(coro):
    return asyncio.run(coro)


# ---- numbering and the ring -------------------------------------------------------------------------------------------------------------

def test_publish_numbers_a_batch_from_one_in_order():
    bus = EventBus()
    out = bus.publish([ev("chat.message", a=1), ev("graph.updated", a=2), ev("task.updated", a=3)])
    assert [(e.seq, e.type) for e in out] == [(1, "chat.message"), (2, "graph.updated"), (3, "task.updated")]
    assert bus.head == 3
    assert bus.publish([ev(a=4)])[0].seq == 4
    assert [e.seq for e in bus.replay(0).events] == [1, 2, 3, 4]


def test_publish_one_stamps_at_from_the_clock_and_copies_the_data():
    bus = EventBus(clock=FakeClock())
    data = {"provider": "claude", "nested": {"k": [1]}}
    event = bus.publish_one("connector.health", data)
    data["nested"]["k"].append(2)
    assert event.seq == 1 and event.at == "2026-11-04T10:00:00Z" and event.type == "connector.health"
    assert bus.replay(0).events[0].data == {"provider": "claude", "nested": {"k": [1]}}
    assert bus.publish_one("connector.mode").data == {}
    assert bus.publish_one("connector.mode").at == "2026-11-04T10:00:02Z"


def test_the_ring_keeps_only_the_newest_events():
    bus = EventBus(ring_size=5)
    fill(bus, 8)
    assert bus.head == 8
    assert [e.seq for e in bus.replay(3).events] == [4, 5, 6, 7, 8]
    assert RING_SIZE == 1000 and MAX_PENDING >= RING_SIZE


def test_bad_constructor_arguments_are_refused():
    with pytest.raises(ValueError):
        EventBus(ring_size=0)
    with pytest.raises(ValueError):
        EventBus(max_pending=0)


# ---- replay and resync reasons ----------------------------------------------------------------------------------------------------------

def test_replay_first_connection_head_future_and_forgotten_ids():
    bus = EventBus(ring_size=5)
    assert bus.replay(None) == ((), None)
    assert bus.replay(0) == ((), None)                       # nothing published yet: nothing missed
    assert bus.replay(7).resync == "restart"                 # past the (empty) head: an id from a previous launch
    fill(bus, 8)                                             # ring holds 4..8
    assert bus.replay(None) == ((), None)
    assert bus.replay(8) == ((), None)                       # up to date
    assert bus.replay(9).resync == "restart" and bus.replay(9).events == ()
    assert [e.seq for e in bus.replay(3).events] == [4, 5, 6, 7, 8]      # the oldest id that can still be replayed
    gap = bus.replay(2)
    assert gap.resync == "gap" and gap.events == ()
    assert bus.replay(0).resync == "gap"


def test_replay_filters_by_topic_and_server_always_passes():
    bus = EventBus()
    bus.publish_one("chat.message", {})
    bus.publish_one("graph.updated", {})
    bus.publish_one("connector.mode", {})
    bus.publish_one("needs_you.changed", {})
    assert [e.type for e in bus.replay(0, {"chat"}).events] == ["chat.message"]
    assert [e.type for e in bus.replay(0, {"connector", "needs_you"}).events] == ["connector.mode", "needs_you.changed"]
    assert bus.replay(0, set()).events == ()
    assert len(bus.replay(0, None).events) == 4
    assert topic_matches({"chat"}, "server.resync") and topic_matches(None, "x.y") and not topic_matches({"chat"}, "graph.updated")
    assert topic_of("chat.message") == "chat" and topic_of("ping") == "ping" and topic_matches({"ping"}, "ping")
    assert not topic_matches({"chat"}, "chatter.x")          # whole word before the dot, not a string prefix


# ---- control events ---------------------------------------------------------------------------------------------------------------------

def test_control_events_get_no_seq_and_stay_out_of_the_ring():
    async def go():
        bus = EventBus()
        sub, _ = bus.subscribe(topics={"chat"})
        bus.publish_one("chat.message", {})
        resync = bus.publish_one("server.resync", {"reason": "restart"})
        hello = bus.publish([ev("server.hello", version="x")])[0]
        bus.publish_one("graph.updated", {})
        got = [await asyncio.wait_for(sub.next(), 5) for _ in range(3)]
        return bus, resync, hello, got
    bus, resync, hello, got = run(go())
    assert CONTROL_TYPES == ("server.hello", "server.resync", "chat.partial")
    assert resync.seq == 0 and hello.seq == 0
    assert bus.head == 2 and [e.type for e in bus.replay(0).events] == ["chat.message", "graph.updated"]
    assert [(e.type, e.seq) for e in got] == [("chat.message", 1), ("server.resync", 0), ("server.hello", 0)]   # server passes a topic filter


# ---- invalid input ----------------------------------------------------------------------------------------------------------------------

def test_bad_type_or_data_is_logged_and_dropped_never_raised(caplog):
    bus = EventBus()
    with caplog.at_level(logging.ERROR):
        assert bus.publish_one("Bad Type", {}) is None
        assert bus.publish_one("chat.message\nevil", {}) is None
        assert bus.publish_one("x" * 61, {}) is None
        assert bus.publish_one("chat.message", {"when": object()}) is None
        assert bus.publish_one("chat.message", ["not", "an", "object"]) is None
        out = bus.publish([ev("chat.message", a=1), ev("bad type"), ev("task.updated", a=2)])
    assert [e.seq for e in out] == [1, 2] and [e.type for e in out] == ["chat.message", "task.updated"]
    assert bus.head == 2 and len(caplog.records) >= 6
    assert event_type_ok("a.b_c.d9") and not event_type_ok("A.b") and not event_type_ok("") and not event_type_ok(None) and not event_type_ok("a..b")


# ---- threads ----------------------------------------------------------------------------------------------------------------------------

def test_publishing_from_many_threads_numbers_every_event_once_in_ring_order():
    async def go():
        bus = EventBus()
        sub, _ = bus.subscribe()

        def worker(k):
            for i in range(100):
                if i % 2:
                    bus.publish_one("chat.message", {"w": k, "i": i})
                else:
                    bus.publish([ev("graph.updated", w=k, i=i)])
        threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        got = [await asyncio.wait_for(sub.next(), 10) for _ in range(800)]
        for t in threads:
            t.join()
        return bus, got
    bus, got = run(go())
    assert bus.head == 800
    assert [e.seq for e in got] == list(range(1, 801))                       # the stream saw every event, in order
    per_thread = {}
    for e in got:
        per_thread.setdefault(e.data["w"], []).append(e.data["i"])
    assert all(v == list(range(100)) for v in per_thread.values())           # each publisher's own order is kept
    # the ring (1000) holds all 800 of them, in seq order
    assert [e.seq for e in bus.replay(0).events] == list(range(1, 801))


def test_subscribe_takes_the_replay_and_registers_in_one_step():
    async def go():
        bus = EventBus()
        fill(bus, 10)
        started = threading.Event()

        def writer():
            for i in range(500):
                bus.publish_one("chat.message", {})
                if i == 20:
                    started.set()
        t = threading.Thread(target=writer)
        t.start()
        started.wait(5)
        sub, replay = bus.subscribe(after=4)
        live = []
        while (live[-1].seq if live else replay.events[-1].seq) < 510:
            live.append(await asyncio.wait_for(sub.next(), 5))
        t.join()
        return replay, live
    replay, live = run(go())
    seqs = [e.seq for e in replay.events] + [e.seq for e in live]
    assert seqs == list(range(5, 511))                                        # no gap, no duplicate between replay and tail


# ---- subscribers ------------------------------------------------------------------------------------------------------------------------

def test_a_subscriber_only_gets_its_topics_live():
    async def go():
        bus = EventBus()
        sub, replay = bus.subscribe(topics=["connector"])
        bus.publish_one("chat.message", {})
        bus.publish_one("connector.switch", {"from": "claude", "to": "codex"})
        bus.publish_one("graph.updated", {})
        bus.publish_one("connector.mode", {"mode": "stub"})
        return replay, await asyncio.wait_for(sub.next(), 5), await asyncio.wait_for(sub.next(), 5), bus.subscriber_count
    replay, a, b, count = run(go())
    assert replay.events == () and (a.type, a.seq) == ("connector.switch", 2) and (b.type, b.seq) == ("connector.mode", 4) and count == 1


def test_a_slow_stream_is_told_to_resync_with_gap_and_then_continues():
    async def go():
        bus = EventBus(max_pending=5)
        sub, _ = bus.subscribe()
        fill(bus, 9)
        await asyncio.sleep(0.05)                                            # let the loop run the queued pushes
        first = await asyncio.wait_for(sub.next(), 5)
        bus.publish_one("task.updated", {})
        second = await asyncio.wait_for(sub.next(), 5)
        return first, second
    first, second = run(go())
    assert (first.type, first.seq, first.data) == ("server.resync", 0, {"reason": "gap"})
    assert (second.type, second.seq) == ("task.updated", 10)


def test_unsubscribe_and_a_dead_loop_remove_a_stream():
    async def go():
        bus = EventBus()
        a, _ = bus.subscribe()
        b, _ = bus.subscribe()
        a.close()
        a.close()
        return bus, b
    bus, b = run(go())
    assert bus.subscriber_count == 1
    other = asyncio.new_event_loop()
    holder = {}

    async def make():
        holder["sub"], _ = bus.subscribe()
    other.run_until_complete(make())
    other.close()
    assert bus.subscriber_count == 2
    assert bus.publish_one("chat.message", {}).seq == 1                       # closed loops do not break publishing
    assert bus.subscriber_count == 0                                         # b's loop ended with run(), the other with close()


def test_close_ends_every_stream_now_and_later_ones_too():
    async def go():
        bus = EventBus()
        sub, _ = bus.subscribe()
        bus.publish_one("chat.message", {})
        bus.close()
        bus.close()
        first = await asyncio.wait_for(sub.next(), 5)
        ended = [await asyncio.wait_for(sub.next(), 5), await asyncio.wait_for(sub.next(), 5)]
        late, _ = bus.subscribe()
        late_first = await asyncio.wait_for(late.next(), 5)
        bus.publish_one("chat.message", {})                                    # still allowed, nobody listens
        return bus, first, ended, late_first
    bus, first, ended, late_first = run(go())
    assert first.type == "chat.message" and ended == [None, None] and late_first is None
    assert bus.closed and bus.subscriber_count == 0 and bus.head == 2


# ---- the database feeds the bus ---------------------------------------------------------------------------------------------------------

def test_database_commits_publish_numbered_events_and_rollbacks_publish_none(settings, clock):
    bus = EventBus(clock=clock)
    db = Database(settings.db_path, bus.publish, clock=clock)
    db.migrate()
    with db.tx() as tx:
        tx.emit("chat.message", {"n": 1})
        tx.emit("graph.updated", {"n": 2})
    with pytest.raises(RuntimeError):
        with db.tx() as tx:
            tx.emit("task.updated", {"n": 3})
            raise RuntimeError("boom")
    with db.tx() as tx:
        tx.emit("usage.recorded", {"n": 4})
    db.close()
    assert [(e.seq, e.type, e.data["n"]) for e in bus.replay(0).events] == [(1, "chat.message", 1), (2, "graph.updated", 2), (3, "usage.recorded", 4)]
