"""PLAN-100 S20-S25: boundary event, state machine, stop, registry, queue.

The state machine is on the MANDATORY path (codex fold): _observe runs inside
the emit closure before the primary send, so state stays correct with zero
subscribers attached.
"""
import asyncio
import json
import unittest

import session_runtime
from session_runtime import SessionRuntime, TurnQueue


def _feed(events):
    reader = asyncio.StreamReader()
    for ev in events:
        reader.feed_data((json.dumps(ev) + "\n").encode("utf-8"))
    reader.feed_eof()
    return reader


BASE = [
    {"type": "system", "subtype": "init", "session_id": "s-1", "model": "m",
     "tools": [], "mcp_servers": [], "slash_commands": [],
     "permissionMode": "plan", "cwd": "/"},
    {"type": "stream_event", "session_id": "s-1",
     "event": {"delta": {"type": "text_delta", "text": "hi"}}},
    {"type": "result", "subtype": "success", "is_error": False,
     "session_id": "s-1", "duration_ms": 1, "num_turns": 1,
     "total_cost_usd": 0.0},
]

TOOL_EVENTS = [
    BASE[0],
    {"type": "assistant", "session_id": "s-1", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Bash",
         "input": {"command": "ls"}}]}},
    {"type": "user", "session_id": "s-1", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
    BASE[2],
]


class _FakeProc:
    returncode = 0  # "already exited": kill_group stays a safe no-op

    def __init__(self, events):
        self.stdout = _feed(events)


def run_turn(rt, primary=None, events=BASE, session_id=None):
    async def go():
        rt.proc = _FakeProc(events)
        async def _null(frame):
            return None
        return await rt.demux_turn(primary or _null, session_id)
    return asyncio.run(go())


class TestBoundaryEvent(unittest.TestCase):
    def test_01_subscribers_get_boundary_primary_does_not(self):
        rt = SessionRuntime()
        primary, seen = [], []
        rt.subscribe(lambda f: seen.append(f["type"]))
        async def prim(f):
            primary.append(f["type"])
        run_turn(rt, prim)
        self.assertEqual(seen[-1], "_turn_boundary")
        self.assertNotIn("_turn_boundary", primary,
                         "internal frames must never reach the client")

    def test_02_boundary_carries_turn_outcome(self):
        rt = SessionRuntime()
        frames = []
        rt.subscribe(frames.append)
        run_turn(rt)
        b = frames[-1]
        self.assertTrue(b["got_result"])
        self.assertIsNone(b["error"])
        self.assertEqual(b["session"], "s-1")


class TestStateMachine(unittest.TestCase):
    def test_03_state_updates_with_zero_subscribers(self):
        # codex fold: the state path is mandatory, not an optional observer
        rt = SessionRuntime()
        states = []
        async def prim(f):
            states.append(rt.state)
        run_turn(rt, prim)
        self.assertIn("active", states)
        self.assertEqual(rt.state, "idle")

    def test_04_retrying_state_during_api_retry(self):
        rt = SessionRuntime()
        events = [BASE[0],
                  {"type": "system", "subtype": "api_retry",
                   "session_id": "s-1", "message": "rl", "attempt": 1},
                  BASE[1], BASE[2]]
        seen = []
        async def prim(f):
            seen.append((f["type"], rt.state))
        run_turn(rt, prim, events=events)
        self.assertIn(("retrying", "retrying"), seen)
        self.assertEqual(rt.state, "idle")

    def test_05_open_tools_tracks_start_and_end(self):
        rt = SessionRuntime()
        snaps = []
        async def prim(f):
            if f["type"] == "tool":
                snaps.append((f["phase"], set(rt.open_tools)))
        run_turn(rt, prim, events=TOOL_EVENTS)
        self.assertEqual(snaps[0], ("start", {"t1"}))
        self.assertEqual(snaps[1], ("end", set()))
        self.assertEqual(rt.open_tools, set())


class TestStop(unittest.TestCase):
    def test_06_stop_sets_state_drops_shadow_keeps_operator(self):
        rt = SessionRuntime()
        class _DeadProc:
            returncode = 0
        rt.proc = _DeadProc()
        rt.turn_queue.put({"m": "founder"}, source="operator")
        rt.turn_queue.put({"m": "shadow"}, source="shadow")
        rt.stop()
        self.assertTrue(rt.stopped)
        self.assertEqual(rt.state, "stopped")
        self.assertEqual(len(rt.turn_queue), 1)
        self.assertEqual(rt.turn_queue.get(), {"m": "founder"})

    def test_07_boundary_still_fires_after_stopped_turn(self):
        rt = SessionRuntime()
        seen = []
        rt.subscribe(lambda f: seen.append(f["type"]))
        rt.stopped = True
        rt.state = "stopped"
        run_turn(rt, events=[BASE[0]])  # no result: eof path, like a kill
        self.assertEqual(seen[-1], "_turn_boundary")
        self.assertEqual(rt.state, "stopped",
                         "a boundary must not resurrect a stopped runtime")


class TestRegistry(unittest.TestCase):
    def tearDown(self):
        session_runtime.RUNTIMES.clear()

    def test_08_register_lookup_unregister(self):
        rt = SessionRuntime()
        session_runtime.register_runtime("s-9", rt)
        self.assertIs(session_runtime.lookup_runtime("s-9"), rt)
        session_runtime.unregister_runtime("s-9", rt)
        self.assertIsNone(session_runtime.lookup_runtime("s-9"))

    def test_09_loser_of_a_session_race_cannot_evict_winner(self):
        old, new = SessionRuntime(), SessionRuntime()
        session_runtime.register_runtime("s-9", old)
        session_runtime.register_runtime("s-9", new)   # new socket wins
        session_runtime.unregister_runtime("s-9", old)  # old teardown
        self.assertIs(session_runtime.lookup_runtime("s-9"), new)

    def test_10_none_session_is_a_noop(self):
        rt = SessionRuntime()
        session_runtime.register_runtime(None, rt)
        session_runtime.unregister_runtime(None, rt)
        self.assertEqual(session_runtime.RUNTIMES, {})


class TestTurnQueue(unittest.TestCase):
    def test_11_operator_outranks_shadow_even_when_later(self):
        q = TurnQueue()
        q.put({"m": "shadow-1"}, source="shadow")
        q.put({"m": "founder"}, source="operator")
        self.assertEqual(q.get(), {"m": "founder"})
        self.assertEqual(q.get(), {"m": "shadow-1"})
        self.assertIsNone(q.get())

    def test_12_duplicate_key_rejected_no_key_never_deduped(self):
        q = TurnQueue()
        self.assertTrue(q.put({"m": "a"}, source="shadow",
                              dedupe_key="s-1:say-1:shadow"))
        self.assertFalse(q.put({"m": "a"}, source="shadow",
                               dedupe_key="s-1:say-1:shadow"))
        # same text, no key: two deliberate turns, both accepted
        self.assertTrue(q.put({"m": "yes"}, source="operator"))
        self.assertTrue(q.put({"m": "yes"}, source="operator"))
        self.assertEqual(len(q), 3)


if __name__ == "__main__":
    unittest.main()
