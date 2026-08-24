"""PLAN-100 S19: SessionRuntime subscriber API.

The websocket stays the PRIMARY emit (its exception semantics are frozen by
the characterization suite); subscribers are additional observers of the same
frame stream. Pinned here: delivery parity, unsubscribe, mid-turn attach
(per-frame snapshot), and broken-observer isolation.
"""
import asyncio
import json
import unittest

from session_runtime import SessionRuntime


def _feed(events):
    reader = asyncio.StreamReader()
    for ev in events:
        reader.feed_data((json.dumps(ev) + "\n").encode("utf-8"))
    reader.feed_eof()
    return reader


EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "s-1", "model": "m",
     "tools": [], "mcp_servers": [], "slash_commands": [],
     "permissionMode": "plan", "cwd": "/"},
    {"type": "stream_event", "session_id": "s-1",
     "event": {"delta": {"type": "text_delta", "text": "hi"}}},
    {"type": "result", "subtype": "success", "is_error": False,
     "session_id": "s-1", "duration_ms": 1, "num_turns": 1,
     "total_cost_usd": 0.0},
]


class _FakeProc:
    def __init__(self, events):
        self.stdout = _feed(events)


def run_turn(rt, primary, events=EVENTS, session_id=None):
    # The fake proc (and its StreamReader) must be built INSIDE the running
    # loop: a StreamReader constructed outside one binds get_event_loop and
    # the second asyncio.run in the same thread then has no current loop.
    async def go():
        rt.proc = _FakeProc(events)
        return await rt.demux_turn(primary, session_id)
    return asyncio.run(go())


class TestSubscribers(unittest.TestCase):
    def test_01_subscriber_sees_every_frame_the_primary_sees(self):
        rt = SessionRuntime()
        primary, seen = [], []
        rt.subscribe(seen.append)
        run_turn(rt, lambda f: _async(primary.append, f))
        self.assertEqual(primary, seen)
        self.assertEqual([f["type"] for f in primary],
                         ["session", "sysinit", "token", "done"])

    def test_02_unsubscribe_stops_delivery(self):
        rt = SessionRuntime()
        seen = []
        cb = rt.subscribe(seen.append)
        rt.unsubscribe(cb)
        run_turn(rt, lambda f: _async(None, f))
        self.assertEqual(seen, [])

    def test_03_broken_subscriber_never_costs_the_turn(self):
        rt = SessionRuntime()
        primary = []

        def boom(frame):
            raise RuntimeError("observer bug")

        rt.subscribe(boom)
        sid, got_text, got_result, err, eof = run_turn(
            rt, lambda f: _async(primary.append, f))
        self.assertTrue(got_result)
        self.assertIsNone(err)
        self.assertEqual(primary[-1]["type"], "done")

    def test_04_async_subscriber_supported(self):
        rt = SessionRuntime()
        seen = []

        async def acb(frame):
            seen.append(frame["type"])

        rt.subscribe(acb)
        run_turn(rt, lambda f: _async(None, f))
        self.assertIn("done", seen)

    def test_05_primary_exceptions_still_propagate(self):
        rt = SessionRuntime()

        async def dead_socket(frame):
            raise ConnectionError("socket gone")

        with self.assertRaises(ConnectionError):
            run_turn(rt, dead_socket)

    def test_06_mid_turn_attach_delivery_starts_at_the_attach_frame(self):
        """Snapshot is per FRAME and taken after the primary emit: an observer
        attached while frame N is being delivered receives frame N itself and
        everything after -- nothing before. This is what lets Shadow attach to
        an already-running pane without replaying its history."""
        rt = SessionRuntime()
        seen = []

        def attach_on_token(frame):
            if frame["type"] == "token" and not rt.subscribers:
                rt.subscribe(lambda f: seen.append(f["type"]))
            return _async(None, frame)

        run_turn(rt, attach_on_token)
        self.assertEqual(seen, ["token", "done"])


def _async(fn, arg):
    async def go():
        if fn is not None:
            fn(arg)
    return go()


if __name__ == "__main__":
    unittest.main()
