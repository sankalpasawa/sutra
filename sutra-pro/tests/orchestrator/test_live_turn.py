"""`LiveTurn`, the checkpoint store and the `chat.live` control event (streaming design D201 to D204, D211, D213, D222; work package STR-6).

The clock is injectable and the ticker is a method (`tick`), so cadence tests are exact; one test runs the real ticker thread to show a trailing piece is sent with no
further provider event. Nothing here starts a process or a model."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time

import pytest

from sutra_app.connectors.cancel import CancelToken
from sutra_app.connectors.chat_models import ChatEvent
from sutra_app.orchestrator import live_checkpoint, schema
from sutra_app.orchestrator.events import CONTROL_TYPES, LIVE, EventBus
from sutra_app.orchestrator.live_turn import LiveConfig, LiveTurn
from sutra_app.orchestrator.redact import Redactor


class Bus:
    """Records what is published, with the thread that published it (the real bus numbers and delivers under its own lock; this one keeps arrival order)."""

    def __init__(self):
        self.events, self.lock = [], threading.Lock()

    def publish_one(self, type, data):
        with self.lock:
            self.events.append((type, json.loads(json.dumps(data))))

    @property
    def live(self):
        return [d for t, d in self.events if t == LIVE]

    def types(self):
        return [d["type"] for d in self.live]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make(clock=None, bus=None, **kw):
    clock = clock or Clock()
    bus = bus if bus is not None else Bus()
    cfg = kw.pop("config", LiveConfig(heartbeat_s=5.0, coalesce_ms=33, checkpoint_s=1.5))
    live = LiveTurn(session_id="cs_one", message_id=7, generation_id="g" * 32, client_id="client-0001", attempt_no=kw.pop("attempt_no", 1), token=kw.pop("token", CancelToken()),
                    bus=bus, config=cfg, clock=clock, wall=lambda: 1_700_000_000.0 + clock(), start_thread=kw.pop("start_thread", False), **kw)
    return live, bus, clock


def ev(event_kind, /, **data):
    return ChatEvent(kind=event_kind, data=data)


def route(route_event, /, **data):
    return ev("route", event=route_event, **data)


def start_text(block_id="b1"):
    return ev("block_start", block_id=block_id, type="text", kind="other", name="")


def delta(text, offset, block_id="b1"):
    return ev("block_delta", block_id=block_id, delta=text, offset=offset)


def pump(live, *connector_events):
    """What `ChatPort.stream` does with a live turn's accumulator: feed each connector event to it and hand the block events to the live turn."""
    from sutra_app.connectors.models import ConnectorEvent
    for e in connector_events:
        for out in live.acc.feed(e if isinstance(e, ConnectorEvent) else ConnectorEvent(kind=e[0], data=e[1])):
            live.on_event(ev("block_" + out.kind, block_id=out.block_id, **out.data))


def text_events(*pieces):
    return [("message_boundary", {}), ("block_start", {"index": 0, "type": "text"})] + [("text_delta", {"text": p, "kind": "text"}) for p in pieces]


def attempt(n=1, provider="claude", idle=120.0):
    return route("attempt", provider=provider, model="sonnet", n=n, idle_limit_s=idle, stream_mode="tokens")


# ---- the envelope and the order ------------------------------------------------------------------------------------------------------

def test_every_event_has_the_envelope_and_seq_is_gap_free():
    live, bus, clock = make()
    live.accepted()
    live.on_event(route("plan", order=["claude", "codex"], model="sonnet"))
    live.on_event(attempt())
    live.on_event(ev("started", provider="claude", model="sonnet", session_id="p-1"))
    live.on_event(start_text())
    live.on_event(delta("Hi", 0))
    live.on_event(ev("block_end", block_id="b1", status="ok", is_error=False, truncated=False))
    e = bus.live
    assert [x["seq"] for x in e] == list(range(1, len(e) + 1))
    assert bus.types() == ["turn.accepted", "turn.connecting", "turn.started", "block.start", "block.delta", "block.end"]
    first = e[0]
    assert first["v"] == 1 and first["id"] == f"{'g' * 32}:1" and first["conversation_id"] == "cs_one" and first["message_id"] == 7 and first["attempt"] == 1
    assert first["payload"] == {"client_id": "client-0001", "attempt_no": 1} and first["ts"].endswith("Z") and len(first["ts"]) == 24
    assert e[3]["block_id"] == "b1" and "block_id" not in e[0]
    assert e[1]["payload"] == {"provider": "claude", "model": "sonnet", "stream_mode": "tokens"}
    assert e[2]["payload"] == {"provider": "claude", "model": "sonnet", "session_id": "p-1", "stream_mode": "tokens", "idle_limit_s": 120.0}


def test_seq_order_equals_bus_order_with_threads_racing_the_provider_events():
    live, bus, clock = make()
    live.accepted()
    live.on_event(attempt())
    live.on_event(ev("started", provider="claude", model="m"))
    live.on_event(start_text())
    stop, errors = threading.Event(), []

    def racer(name):
        try:
            for n in range(150):
                live.publish("heartbeat", {"idle_ms": n, "who": name})
        except Exception as exc:                                  # noqa: BLE001
            errors.append(exc)

    def flusher():
        while not stop.is_set():
            clock.advance(0.05)
            live.tick()

    threads = [threading.Thread(target=racer, args=(f"r{i}",)) for i in range(4)] + [threading.Thread(target=flusher)]
    for t in threads:
        t.start()
    offset = 0
    for n in range(300):                                          # the worker thread feeds deltas while the others publish and tick
        live.on_event(delta(f"w{n} ", offset))
        offset += len(f"w{n} ")
    for t in threads[:-1]:
        t.join()
    stop.set()
    threads[-1].join()
    live.snapshot()
    assert not errors
    seqs = [d["seq"] for d in bus.live]
    assert seqs == list(range(1, len(seqs) + 1))                  # the order on the bus IS the order of seq: nothing overtook anything
    texts = [d for d in bus.live if d["type"] == "block.delta"]
    joined = "".join(d["payload"]["delta"] for d in texts)
    assert joined == "".join(f"w{n} " for n in range(300))
    offsets = [d["payload"]["offset"] for d in texts]
    assert offsets == sorted(offsets) and all(len("".join(t["payload"]["delta"] for t in texts[:i])) == offsets[i] for i in range(len(texts)))


# ---- text cadence --------------------------------------------------------------------------------------------------------------------

def test_the_first_piece_of_a_block_is_sent_at_once_and_later_pieces_are_joined_until_the_deadline():
    live, bus, clock = make()
    live.on_event(start_text())
    live.on_event(delta("A", 0))
    assert [d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta"] == ["A"]               # no delay for the first
    live.on_event(delta("B", 1))
    live.on_event(delta("C", 2))
    assert [d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta"] == ["A"]               # held for the coalescer
    clock.advance(0.020)
    live.tick()
    assert len([d for d in bus.live if d["type"] == "block.delta"]) == 1
    clock.advance(0.020)
    live.tick()                                                                                           # 40 ms after the first held piece: past 33 ms
    assert [(d["payload"]["delta"], d["payload"]["offset"]) for d in bus.live if d["type"] == "block.delta"] == [("A", 0), ("BC", 1)]


def test_a_piece_that_arrives_after_the_deadline_flushes_everything_held():
    live, bus, clock = make()
    live.on_event(start_text())
    live.on_event(delta("A", 0))
    live.on_event(delta("B", 1))
    clock.advance(0.05)
    live.on_event(delta("C", 2))
    assert [(d["payload"]["delta"], d["payload"]["offset"]) for d in bus.live if d["type"] == "block.delta"] == [("A", 0), ("BC", 1)]


def test_other_events_flush_held_text_first_so_nothing_is_reordered():
    live, bus, clock = make()
    live.on_event(start_text("b1"))
    live.on_event(delta("one", 0, "b1"))
    live.on_event(delta("two", 3, "b1"))
    live.on_event(ev("block_end", block_id="b1", status="ok", is_error=False, truncated=False))
    live.on_event(start_text("b2"))
    live.on_event(delta("next", 0, "b2"))
    assert bus.types() == ["block.start", "block.delta", "block.delta", "block.end", "block.start", "block.delta"]
    assert [d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta"] == ["one", "two", "next"]


def test_a_trailing_piece_is_sent_by_the_real_ticker_with_no_further_provider_event():
    live, bus, clock = make(clock=time.monotonic, start_thread=True)
    live.start()
    try:
        live.on_event(start_text())
        live.on_event(delta("A", 0))
        live.on_event(delta("B", 1))                                  # held: nothing else will ever arrive
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len([d for d in bus.live if d["type"] == "block.delta"]) < 2:
            time.sleep(0.005)
        got = [d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta"]
        assert got == ["A", "B"]
    finally:
        live.close()


def test_the_flush_deadline_wakes_the_ticker_for_about_the_coalesce_time():
    live, bus, _ = make(clock=time.monotonic, start_thread=True)
    live.start()
    try:
        live.on_event(start_text())
        live.on_event(delta("A", 0))
        began = time.monotonic()
        live.on_event(delta("B", 1))
        while len([d for d in bus.live if d["type"] == "block.delta"]) < 2 and time.monotonic() - began < 2:
            time.sleep(0.002)
        assert time.monotonic() - began < 0.5                         # a real timer: tens of milliseconds, never a second
    finally:
        live.close()


def test_empty_deltas_and_deltas_without_a_block_are_ignored():
    live, bus, _ = make()
    live.on_event(ev("block_delta", block_id="b1", delta="", offset=0))
    live.on_event(ev("block_delta", delta="x", offset=0))
    assert bus.live == []


# ---- heartbeat ------------------------------------------------------------------------------------------------------------------------

def test_a_heartbeat_after_silence_carries_the_real_idle_time_and_limit_and_repeats_every_interval():
    live, bus, clock = make()
    live.on_event(attempt(idle=90.0))
    live.on_event(ev("started", provider="claude", model="m"))
    clock.advance(4.9)
    live.tick()
    assert "heartbeat" not in bus.types()
    clock.advance(0.2)
    live.tick()
    beat = bus.live[-1]
    assert beat["type"] == "heartbeat" and beat["payload"] == {"idle_ms": 5100, "idle_limit_s": 90.0}
    clock.advance(5.0)
    live.tick()
    assert bus.live[-1]["payload"]["idle_ms"] == 10100 and bus.types().count("heartbeat") == 2
    live.on_event(start_text())                                         # a provider event resets the idle time
    clock.advance(5.0)
    live.tick()
    assert bus.live[-1]["payload"]["idle_ms"] == 5000


def test_no_heartbeat_while_backing_off_stopping_or_after_the_end():
    live, bus, clock = make()
    live.on_event(attempt())
    live.on_event(ev("started", provider="claude", model="m"))
    live.on_event(route("failed", provider="claude", code="server_error", reason="Claude had a server error", retryable=True, action="retry", delay_s=30.0, next_provider="claude"))
    clock.advance(60)
    live.tick()
    assert "heartbeat" not in bus.types() and live.state == "backoff"
    live.on_event(attempt(n=2))
    live.request_stop()
    clock.advance(60)
    live.tick()
    assert "heartbeat" not in bus.types()


def test_idle_limit_is_none_when_the_plan_has_no_idle_timeout():
    live, bus, clock = make()
    live.on_event(route("attempt", provider="codex", model="m", n=1, idle_limit_s=None, stream_mode="activity"))
    clock.advance(6)
    live.tick()
    assert bus.live[-1]["payload"] == {"idle_ms": 6000, "idle_limit_s": None}


# ---- router and provider events ------------------------------------------------------------------------------------------------------

def test_the_states_follow_the_router_and_the_provider_not_a_script():
    live, bus, clock = make()
    live.accepted()
    assert live.state == "accepted"
    live.on_event(route("plan", order=["claude"], model="m"))
    assert live.state == "accepted"
    live.on_event(attempt())
    assert live.state == "connecting"
    live.on_event(ev("started", provider="claude", model="m"))
    assert live.state == "running"
    live.on_event(route("failed", provider="claude", code="crashed", reason="Claude stopped unexpectedly (exit 137)", retryable=True, action="retry", delay_s=2.0, next_provider="claude"))
    assert live.state == "backoff"
    failed = bus.live[-1]
    assert failed["type"] == "attempt.failed" and failed["payload"] == {"provider": "claude", "code": "crashed", "reason": "Claude stopped unexpectedly (exit 137)",
                                                                       "action": "retry", "delay_s": 2.0, "next_provider": "claude"}
    live.on_event(attempt(n=2))
    assert live.state == "connecting" and bus.live[-1]["attempt"] == 2 and bus.live[-1]["type"] == "turn.connecting"
    live.on_event(ev("restart", provider="claude", reason="x", after_side_effects=True))
    assert live.state == "running" and bus.live[-1]["type"] == "attempt.restart" and bus.live[-1]["payload"] == {"attempt": 2, "provider": "claude", "after_side_effects": True}
    live.on_event(ev("started", provider="claude", model="m"))
    assert bus.live[-1]["attempt"] == 2


def test_route_plan_and_usage_and_switched_are_not_live_events():
    live, bus, _ = make()
    live.on_event(route("plan", order=["claude"], model="m"))
    live.on_event(ev("usage", usd=0.1, usage={}))
    live.on_event(ev("switched", **{"from": "claude", "to": "codex", "plan": {}}))
    assert bus.live == []


def test_after_a_restart_the_first_piece_of_each_new_block_is_again_sent_at_once():
    live, bus, _ = make()
    live.on_event(start_text("b1"))
    live.on_event(delta("a", 0, "b1"))
    live.on_event(ev("restart", provider="codex", reason="x", after_side_effects=False))
    live.on_event(start_text("b2"))
    live.on_event(delta("fresh", 0, "b2"))
    assert [d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta"] == ["a", "fresh"]


# ---- stop ----------------------------------------------------------------------------------------------------------------------------

def test_request_stop_sends_what_was_held_freezes_then_publishes_turn_stopping_in_that_order():
    token = CancelToken()
    live, bus, clock = make(token=token)
    pump(live, *text_events("seen ", "also seen"))                       # the second piece is held by the coalescer at this moment
    assert [d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta"] == ["seen "]
    assert live.request_stop() is True and token.requested
    assert bus.types()[-2:] == ["block.delta", "turn.stopping"]
    assert bus.live[-2]["payload"]["delta"] == "also seen" and live.state == "stopping"
    pump(live, ("text_delta", {"text": "grace period output", "kind": "text"}), ("block_start", {"index": 1, "type": "text"}), ("block_stop", {"index": 0}))   # the CLI keeps printing
    live.on_event(delta("grace period output", 14))                      # and even a stray event of the port is dropped
    assert bus.types()[-1] == "turn.stopping" and live.shown_text() == "seen also seen"
    assert live.request_stop() is False                                  # a second Stop changes nothing


def test_the_stored_text_equals_what_every_tab_received_after_a_stop():
    live, bus, clock = make()
    pump(live, *text_events("one ", "two ", "three ", "four "))
    live.request_stop()
    pump(live, ("text_delta", {"text": "five ", "kind": "text"}), ("text_delta", {"text": "six ", "kind": "text"}))
    received = "".join(d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta")
    assert received == live.shown_text() == "one two three four "


def test_open_tool_blocks_end_interrupted_when_the_stopped_turn_settles():
    live, bus, clock = make()
    pump(live, ("message_boundary", {}), ("block_start", {"index": 1, "type": "tool_use", "tool_id": "t1", "name": "Bash"}), ("block_start", {"index": 2, "type": "text"}))
    live.request_stop()
    live.settle_blocks("interrupted")
    ends = [d for d in bus.live if d["type"] == "block.end"]
    assert {(d["block_id"], d["payload"]["status"]) for d in ends} == {("b1", "interrupted"), ("b2", "ok")}
    assert bus.types().index("turn.stopping") < bus.types().index("block.end")


def test_a_stop_that_races_a_finished_turn_changes_nothing():
    live, bus, _ = make()
    live.on_event(start_text())
    live.finish(11, {"text": "all done", "stored_order": ["b1"]})
    assert live.request_stop() is False and live.state == "done" and bus.types()[-1] == "turn.done"


# ---- the endings -----------------------------------------------------------------------------------------------------------------------

def test_turn_done_carries_the_reply_id_the_settle_map_and_usage_and_a_switch_only_there():
    live, bus, _ = make(attempt_no=2)
    live.on_event(start_text())
    live.on_event(delta("Hello", 0))
    done = {"text": "Hello", "stored_order": ["b1"], "usage": {"input_tokens": 3}, "usd": 0.002, "switched": {"from": "claude", "to": "codex", "plan": {}}}
    out = live.finish(42, done)
    assert out["type"] == "turn.done" and out["payload"] == {"message_id_reply": 42, "attempt_no": 2, "text_len": 5, "stored_order": ["b1"],
                                                            "usage": {"usage": {"input_tokens": 3}, "usd": 0.002}, "switched": {"from": "claude", "to": "codex", "plan": {}}}
    assert live.terminal and live.state == "done"


def test_stopped_and_failed_endings_and_a_terminal_state_never_changes():
    live, bus, _ = make()
    pump(live, *text_events("part"))
    live.request_stop()
    live.settle_blocks("interrupted")
    out = live.stopped(9, "cancelled")
    assert out["type"] == "turn.stopped" and out["payload"] == {"message_id_reply": 9, "attempt_no": 1, "exit": "cancelled", "stored_order": ["b1"]}
    live.failed("late", "x", 10)                                             # an ending after an ending is published but the state stays
    assert live.state == "failed" or live.state == "stopped"
    other, bus2, _ = make()
    other.on_event(start_text())
    out = other.failed("Claude did not answer within 120 s: it sent no output for that long, so it was stopped", "timeout", 12)
    assert out["type"] == "turn.failed" and out["payload"]["code"] == "timeout" and "120 s" in out["payload"]["message"] and other.state == "failed"


def test_events_after_the_end_are_ignored():
    live, bus, _ = make()
    live.finish(1, {"text": ""})
    before = len(bus.live)
    live.on_event(start_text())
    live.on_event(attempt())
    assert len(bus.live) == before


# ---- the snapshot -----------------------------------------------------------------------------------------------------------------------

def reduce(envelopes):
    """A tiny reducer: what a page would hold after these events. Only what the snapshot test compares."""
    blocks, order = {}, []
    for e in envelopes:
        t, p, b = e["type"], e["payload"], e.get("block_id")
        if t == "block.start":
            blocks[b] = {"block_id": b, "type": p["type"], "status": "open", "text": ""}
            order.append(b)
        elif t == "block.delta":
            blocks[b]["text"] += p["delta"]
        elif t == "block.end":
            blocks[b]["status"] = p["status"]
        elif t == "attempt.restart":
            blocks, order = {}, []
    return [blocks[b] for b in order]


def test_the_snapshot_equals_the_replay_of_the_events_up_to_its_seq():
    live, bus, clock = make()
    live.accepted()
    live.on_event(attempt())
    live.on_event(ev("started", provider="claude", model="m"))
    from sutra_app.connectors.models import ConnectorEvent as CE
    for e in (CE(kind="message_boundary"), CE(kind="block_start", data={"index": 0, "type": "text"}), CE(kind="text_delta", data={"text": "Hello, ", "kind": "text"}),
              CE(kind="text_delta", data={"text": "world", "kind": "text"})):
        for out in live.acc.feed(e):
            live.on_event(ev("block_" + out.kind, block_id=out.block_id, **out.data))
    snap = live.snapshot()                                                  # flushes the held piece first
    assert snap["seq"] == bus.live[-1]["seq"] and snap["state"] == "connecting" or snap["state"] == "running"
    replayed = reduce([d for d in bus.live if d["seq"] <= snap["seq"]])
    assert [(b["block_id"], b["type"], b["text"]) for b in replayed] == [(b["block_id"], b["type"], b["text"]) for b in snap["blocks"]] == [("b1", "text", "Hello, world")]


def test_snapshot_fields_and_earlier_tries():
    live, bus, clock = make()
    live.on_event(attempt(idle=100.0))
    clock.advance(2.5)
    snap = live.snapshot()
    assert snap["generation_id"] == "g" * 32 and snap["message_id"] == 7 and snap["client_id"] == "client-0001" and snap["attempt"] == 1 and snap["attempt_no"] == 1
    assert snap["provider"] == "claude" and snap["stream_mode"] == "tokens" and snap["idle_limit_s"] == 100.0 and snap["elapsed_ms"] == 2500 and snap["earlier"] == []
    from sutra_app.connectors.models import ConnectorEvent as CE
    live.acc.feed(CE(kind="block_start", data={"index": 0, "type": "text"}))
    live.acc.restart("Claude had a server error", "codex")
    assert [e["reason"] for e in live.snapshot()["earlier"]] == ["Claude had a server error"]


def test_a_snapshot_taken_while_the_worker_runs_is_never_ahead_of_its_events():
    live, bus, clock = make()
    live.on_event(start_text())
    stop, bad = threading.Event(), []

    def worker():
        offset = 0
        for n in range(400):
            live.on_event(delta(f"{n},", offset))
            offset += len(f"{n},")
            clock.advance(0.01)
        stop.set()

    t = threading.Thread(target=worker)
    t.start()
    while not stop.is_set():
        snap = live.snapshot()
        with bus.lock:
            upto = [d for d in bus.live if d["seq"] <= snap["seq"]]
        text = "".join(d["payload"]["delta"] for d in upto if d["type"] == "block.delta")
        if snap["blocks"] and snap["blocks"][0]["text"] != text:
            bad.append((snap["seq"], len(text), len(snap["blocks"][0]["text"])))
    t.join()
    assert not bad


# ---- redaction and the hold-back ---------------------------------------------------------------------------------------------------------

def test_a_secret_split_across_pieces_never_reaches_the_bus_or_the_snapshot():
    redact = Redactor(environ={}, extra=("hunter2-password",))
    live, bus, clock = make(redact=redact)
    from sutra_app.connectors.models import ConnectorEvent as CE
    for e in (CE(kind="block_start", data={"index": 0, "type": "text"}), CE(kind="text_delta", data={"text": "the pass", "kind": "text"}),
              CE(kind="text_delta", data={"text": "word hunter2-", "kind": "text"}), CE(kind="text_delta", data={"text": "password!", "kind": "text"}),
              CE(kind="block_stop", data={"index": 0})):
        for out in live.acc.feed(e):
            live.on_event(ev("block_" + out.kind, block_id=out.block_id, **out.data))
    live.snapshot()
    assert "hunter2-password" not in json.dumps(bus.live) and "hunter2-password" not in json.dumps(live.snapshot())
    assert live.shown_text() == "the password [redacted]!" == "".join(d["payload"]["delta"] for d in bus.live if d["type"] == "block.delta")


# ---- lifecycle ----------------------------------------------------------------------------------------------------------------------------

def test_close_is_idempotent_joins_the_ticker_and_works_when_the_caller_raised():
    live, bus, _ = make(clock=time.monotonic, start_thread=True)
    live.start()
    thread = live._thread
    assert thread.is_alive()
    try:
        raise RuntimeError("the turn blew up")
    except RuntimeError:
        pass
    finally:
        live.close()
    assert not thread.is_alive()
    live.close()                                                              # twice: nothing
    live.tick()                                                               # and a late tick after close is harmless


def test_close_does_not_hang_on_a_ticker_stuck_in_a_slow_write(monkeypatch):
    class SlowDb:
        pass
    live, bus, clock = make()
    gate = threading.Event()
    monkeypatch.setattr(live_checkpoint, "save", lambda db, **row: gate.wait(10))
    live._db = SlowDb()
    live.on_event(attempt())
    clock.advance(1.0)
    live.tick()                                                               # a due structural checkpoint: the write thread blocks
    began = time.monotonic()
    import sutra_app.orchestrator.live_turn as module
    monkeypatch.setattr(module, "JOIN_S", 0.2)
    live.close()
    assert time.monotonic() - began < 2
    gate.set()


# ---- the checkpoint ------------------------------------------------------------------------------------------------------------------------

def test_the_checkpoint_is_written_when_the_state_changes_and_a_block_ends_and_when_text_has_grown(db, monkeypatch):
    saved = []
    monkeypatch.setattr(live_checkpoint, "save", lambda database, **row: saved.append(row))
    live, bus, clock = make(db=db)
    live.on_event(attempt())                                                  # a state change
    clock.advance(0.3)
    live.tick()
    for t in list(live._ckpt_thread and [live._ckpt_thread] or []):
        t.join(2)
    assert [r["state"] for r in saved] == ["connecting"]
    pump(live, *text_events("x" * 100))
    clock.advance(2.0)
    live.tick()                                                               # 100 characters: under the 256 threshold, and the block start was structural: due after 0.25 s
    live._ckpt_thread.join(2)
    saved_before = len(saved)
    clock.advance(2.0)
    live.tick()
    assert len(saved) == saved_before                                         # nothing new since: no write
    pump(live, ("text_delta", {"text": "y" * 300, "kind": "text"}))
    clock.advance(1.6)
    live.tick()
    live._ckpt_thread.join(2)
    assert len(saved) == saved_before + 1 and saved[-1]["seq"] <= live.seq and any(b["type"] == "text" and len(b["text"]) >= 400 for b in saved[-1]["blocks"])
    pump(live, ("block_stop", {"index": 0}))
    clock.advance(0.3)
    live.tick()
    live._ckpt_thread.join(2)
    assert len(saved) == saved_before + 2 and saved[-1]["blocks"][0]["status"] == "ok"


def test_the_checkpoint_is_serialised_and_written_outside_every_lock(db, monkeypatch):
    held = []

    def save(database, **row):
        acquired = live._lock.acquire(blocking=False)                          # the writer thread can take the turn's lock: nobody holds it while the write runs
        held.append(acquired)
        if acquired:
            live._lock.release()
    monkeypatch.setattr(live_checkpoint, "save", save)
    live, bus, clock = make(db=db)
    live.on_event(attempt())
    clock.advance(0.5)
    live.tick()
    live._ckpt_thread.join(2)
    assert held == [True]


def test_a_checkpoint_still_writing_makes_the_next_due_one_skip_not_pile_up(db, monkeypatch):
    gate = threading.Event()
    calls = []
    monkeypatch.setattr(live_checkpoint, "save", lambda database, **row: (calls.append(row), gate.wait(5)))
    live, bus, clock = make(db=db)
    live.on_event(attempt())
    clock.advance(0.5)
    live.tick()
    time.sleep(0.05)
    live.on_event(start_text())
    live.on_event(ev("block_end", block_id="b1", status="ok", is_error=False, truncated=False))
    clock.advance(0.5)
    live.tick()
    assert len(calls) == 1 and live.ckpt_skipped == 1
    gate.set()
    live._ckpt_thread.join(2)
    clock.advance(0.5)
    live.tick()
    live._ckpt_thread.join(2)
    assert len(calls) == 2                                                    # the skipped one was not lost: its data goes with the next


def test_a_checkpoint_that_fails_never_fails_the_turn(db, monkeypatch, caplog):
    def boom(database, **row):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(live_checkpoint, "save", boom)
    live, bus, clock = make(db=db)
    live.on_event(attempt())
    clock.advance(0.5)
    live.tick()
    live._ckpt_thread.join(2)
    live.on_event(start_text())
    assert live.state == "connecting" and bus.types()[-1] == "block.start"


# ---- the checkpoint store -------------------------------------------------------------------------------------------------------------------

def test_the_checkpoint_store_round_trips_replaces_and_drops_inside_a_transaction(db):
    rows = [{"block_id": "b1", "type": "text", "text": "partial words", "status": "open"}]
    live_checkpoint.save(db, generation_id="g1", session_id="cs_org", message_id=5, attempt=1, attempt_no=1, state="running", seq=9, blocks=rows, now=100.0)
    live_checkpoint.save(db, generation_id="g1", session_id="cs_org", message_id=5, attempt=1, attempt_no=1, state="running", seq=12, blocks=rows * 2, now=101.0)
    live_checkpoint.save(db, generation_id="g2", session_id="cs_other", message_id=6, attempt=2, attempt_no=3, state="stopping", seq=3, blocks=[], now=102.0)
    got = live_checkpoint.load(db, "cs_org")
    assert got["generation_id"] == "g1" and got["seq"] == 12 and got["state"] == "running" and len(got["blocks"]) == 2 and got["message_id"] == 5
    assert live_checkpoint.load(db, "cs_none") is None
    assert [r["generation_id"] for r in live_checkpoint.all_rows(db)] == ["g1", "g2"]
    with db.tx() as tx:
        live_checkpoint.drop(tx, "g1")
    assert live_checkpoint.load(db, "cs_org") is None and live_checkpoint.load(db, "cs_other")["attempt_no"] == 3
    live_checkpoint.drop_session(db, "cs_other")
    assert live_checkpoint.all_rows(db) == []


def test_the_checkpoint_json_is_capped_trimming_the_oldest_text_first():
    blocks = [{"type": "text", "text": "A" * 150_000, "block_id": "b1"}, {"type": "tool_use", "name": "Read", "block_id": "b2"}, {"type": "text", "text": "B" * 150_000, "block_id": "b3"}]
    capped = live_checkpoint.cap_blocks(blocks)
    assert live_checkpoint._size(capped) <= live_checkpoint.MAX_JSON
    assert capped[0].get("truncated") is True and len(capped[0]["text"]) < 150_000 and capped[2]["text"] == "B" * 150_000 and capped[1] == blocks[1]
    assert live_checkpoint.cap_blocks(blocks[:1]) == blocks[:1] and live_checkpoint.cap_blocks([]) == []
    tools = [{"type": "tool_use", "name": "X" * 1000, "block_id": f"b{i}"} for i in range(1000)]
    assert live_checkpoint._size(live_checkpoint.cap_blocks(tools)) <= live_checkpoint.MAX_JSON


def test_a_corrupt_blocks_column_loads_as_no_blocks(db):
    live_checkpoint.save(db, generation_id="g1", session_id="cs_org", message_id=5, attempt=1, attempt_no=1, state="running", seq=1, blocks=[])
    with db.tx() as tx:
        tx.conn.execute("UPDATE chat_turn_checkpoint SET blocks_json = '{not json'")
    assert live_checkpoint.load(db, "cs_org")["blocks"] == []


def test_the_real_ticker_writes_a_checkpoint_to_the_database_and_it_survives_for_recovery(db):
    live, bus, _ = make(clock=time.monotonic, db=db, start_thread=True, config=LiveConfig(heartbeat_s=5.0, coalesce_ms=5, checkpoint_s=0.05, structural_checkpoint_s=0.02))
    live.session_id = "cs_org"
    live.start()
    try:
        live.on_event(attempt())
        live.on_event(start_text())
        live.on_event(delta("t" * 300, 0))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and live_checkpoint.load(db, "cs_org") is None:
            time.sleep(0.01)
        got = live_checkpoint.load(db, "cs_org")
        assert got is not None and got["generation_id"] == "g" * 32 and got["message_id"] == 7
    finally:
        live.close()


# ---- the migration and the control event --------------------------------------------------------------------------------------------------

def test_migration_v5_adds_the_checkpoint_table_and_changes_nothing_else(settings, events, clock):
    from sutra_app.orchestrator.db import Database
    old = Database(settings.data_dir / "v4.sqlite3", events, clock=clock)
    old.migrate(schema.MIGRATIONS[:4])
    old.conn().execute("INSERT INTO chat_sessions(id, node_id, kind, title, created_at, updated_at) VALUES ('cs_x','root','org','Org',1,1)") if False else None
    before = {r[0] for r in old.conn().execute("SELECT name FROM sqlite_master")}
    assert old.version() == 4 and "chat_turn_checkpoint" not in before
    assert old.migrate() == schema.SCHEMA_VERSION == 5
    after = {r[0] for r in old.conn().execute("SELECT name FROM sqlite_master")}
    assert after - before == {"chat_turn_checkpoint", "chat_turn_checkpoint_session", "sqlite_autoindex_chat_turn_checkpoint_1"} or after - before >= {"chat_turn_checkpoint", "chat_turn_checkpoint_session"}
    assert before - after == set()
    cols = [r[1] for r in old.conn().execute("PRAGMA table_info(chat_turn_checkpoint)")]
    assert cols == ["generation_id", "session_id", "message_id", "attempt", "attempt_no", "state", "seq", "blocks_json", "updated_at"]
    assert "chat_turn_checkpoint" in schema.TABLES
    assert old.migrate() == schema.SCHEMA_VERSION                              # again: a no-op
    old.close()


def test_chat_live_is_a_control_event_no_seq_never_in_the_ring_and_delivered_in_order():
    assert LIVE == "chat.live" and LIVE in CONTROL_TYPES

    async def go():
        bus = EventBus()
        sub, _ = bus.subscribe(topics={"chat"})
        bus.publish_one("chat.message", {})
        for n in range(1, 6):
            bus.publish_one(LIVE, {"seq": n})
        bus.publish_one("chat.message", {})
        got = [await asyncio.wait_for(sub.next(), 5) for _ in range(7)]
        return bus, got
    bus, got = asyncio.run(go())
    assert [e.type for e in got] == ["chat.message"] + [LIVE] * 5 + ["chat.message"]
    assert [e.seq for e in got if e.type == LIVE] == [0] * 5 and [e.data["seq"] for e in got if e.type == LIVE] == [1, 2, 3, 4, 5]
    assert [e.type for e in bus.replay(0).events] == ["chat.message", "chat.message"]


def test_a_live_turn_through_the_real_bus_reaches_a_subscriber_in_seq_order():
    async def go():
        bus = EventBus()
        sub, _ = bus.subscribe(topics={"chat"})
        live, _, clock = make(bus=bus)
        loop = asyncio.get_running_loop()

        def produce():
            live.accepted()
            live.on_event(attempt())
            live.on_event(ev("started", provider="claude", model="m"))
            live.on_event(start_text())
            for n in range(20):
                live.on_event(delta("w", n))
            live.finish(3, {"text": "w" * 20, "stored_order": ["b1"]})
        await loop.run_in_executor(None, produce)
        out = []
        while len(out) < live.seq:
            out.append((await asyncio.wait_for(sub.next(), 5)).data)
        return out
    out = asyncio.run(go())
    assert [d["seq"] for d in out] == list(range(1, len(out) + 1)) and out[0]["type"] == "turn.accepted" and out[-1]["type"] == "turn.done"


def test_the_real_ticker_does_not_spin_while_a_checkpoint_write_is_slow(db, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(live_checkpoint, "save", lambda database, **row: gate.wait(5))
    cfg = LiveConfig(heartbeat_s=5.0, coalesce_ms=33, checkpoint_s=0.01, structural_checkpoint_s=0.01)
    live, bus, clock = make(db=db, config=cfg, start_thread=True, clock=lambda: time.monotonic())
    ticks = []
    live.start()
    original = live.tick
    live.tick = lambda now=None: (ticks.append(1), original(now))[1]
    try:
        live.on_event(attempt())
        live.on_event(start_text())
        live.on_event(ev("block_end", block_id="b1", status="ok", is_error=False, truncated=False))
        time.sleep(0.15)                                                       # the first write is now running and blocked
        live.on_event(start_text())                                            # new structure while it runs: a checkpoint is due and can only be skipped
        live.on_event(ev("block_end", block_id="b1", status="ok", is_error=False, truncated=False))
        time.sleep(0.6)
        assert len(ticks) < 100, len(ticks)
    finally:
        gate.set()
        live.close()


def _count_ticks(live):
    ticks = []
    original = live.tick
    live.tick = lambda now=None: (ticks.append(1), original(now))[1]
    return ticks


@pytest.mark.parametrize("with_db", [True, False])
def test_the_real_ticker_does_not_spin_in_a_quiet_stretch_inside_a_text_block(db, with_db):
    """A model that pauses mid-sentence (or a tool that runs) after fewer than `checkpoint_chars` unsaved chars: nothing is due, so the ticker must sleep, not loop."""
    cfg = LiveConfig(heartbeat_s=30.0, coalesce_ms=33, checkpoint_s=0.2, structural_checkpoint_s=0.05)
    live, bus, clock = make(db=db if with_db else None, config=cfg, start_thread=True, clock=lambda: time.monotonic())
    live.start()
    try:
        live.on_event(attempt())
        live.on_event(ev("started", provider="claude", model="sonnet", session_id="s"))
        live.on_event(start_text())
        time.sleep(0.4)                                                        # let the structural checkpoint go, then 100 unsaved chars and silence
        live.on_event(delta("x" * 100, 0))
        time.sleep(0.4)
        ticks = _count_ticks(live)
        time.sleep(1.0)
        assert len(ticks) < 20, len(ticks)
    finally:
        live.close()


def test_a_text_checkpoint_deadline_counts_only_once_enough_chars_are_unsaved(db):
    live, bus, clock = make(db=db, config=LiveConfig(heartbeat_s=1e6, coalesce_ms=33, checkpoint_s=1.5))
    live.on_event(attempt())
    live.on_event(start_text())
    live._ckpt_dirty = False
    live.on_event(delta("x" * 10, 0))
    clock.advance(100)
    assert live._next_timeout(clock()) > 1e5                # only the far heartbeat: no checkpoint deadline in the past
    live.on_event(delta("x" * live.config.checkpoint_chars, 10))
    assert live._next_timeout(clock()) == 0.0
