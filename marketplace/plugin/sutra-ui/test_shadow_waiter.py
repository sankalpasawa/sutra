"""The boundary waiter: a long turn is not a dead turn (2026-09-14).

WHY THIS FILE EXISTS. make_bindings' waiter had NO test of its own -- checked
across the suite before this file landed. test_mission_engine's
test_12_waiter_timeout_fails_not_hangs pins the ENGINE's handling of a mock
waiter returning False; nothing exercised the real binding, which is where
the flat 300s wall-clock deadline lived. Mission m-1e37cbe31708 was killed by
it at 6 of 20 turns with the delegate still alive.

Every bound is driven by an INJECTED clock, the same seam check_stalls uses,
so these tests never sleep for a threshold. poll_secs is tiny throughout: the
polls are real awaits, the DECISIONS are fake-clock, which is what keeps the
suite fast and deterministic.

EVERYTHING THAT TOUCHES asyncio IS BUILT INSIDE THE LOOP. The lane runs on
python 3.9 (run-tests.sh picks the app's own interpreter), where
asyncio.Queue() binds the running loop AT CONSTRUCTION -- building one at
setUp time raises "no current event loop". That is the same trap run-tests.sh
was written to stop being misread as a product defect, so the harness below
creates queues and runtimes inside the coroutine under test.
"""
import asyncio
import os
import tempfile
import unittest

import mission_engine
import session_runtime as srt
import shadow_runner


SID = "sess-waiter-1"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _waiter():
    """The production waiter, bound to a say that is never called here."""
    _sayer, waiter, _reader = shadow_runner.make_bindings(
        lambda *a, **k: None)
    return waiter


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        asyncio.set_event_loop(asyncio.new_event_loop())
        shadow_runner._BOUNDARIES.pop(SID, None)
        shadow_runner._LAST_FRAME_TS.pop(SID, None)
        self.mission = {"id": "m-waiter", "target_session": SID,
                        "turns_used": 0}

    def tearDown(self):
        shadow_runner._BOUNDARIES.pop(SID, None)
        shadow_runner._LAST_FRAME_TS.pop(SID, None)
        asyncio.get_event_loop().close()
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def queue(self):
        """Must be called from INSIDE the loop -- see the module docstring."""
        q = asyncio.Queue()
        shadow_runner._BOUNDARIES[SID] = q
        return q

    def clock(self, step, live=False, boundary_after=None, start=1000.0):
        """A fake clock. `live=True` stamps the frame clock on every tick,
        which is what a worker that is still producing output looks like.
        `boundary_after=N` pushes a boundary on the Nth tick."""
        st = {"t": start, "n": 0}

        def c():
            st["n"] += 1
            st["t"] += step
            if live:
                shadow_runner._LAST_FRAME_TS[SID] = st["t"]
            if boundary_after is not None and st["n"] == boundary_after:
                shadow_runner._BOUNDARIES[SID].put_nowait(
                    {"type": "_turn_boundary", "got_result": True})
            return st["t"]

        c.state = st
        return c


# ===================== the two bounds, and what separates them ===========
class TestWaiterBounds(Base):

    def test_01_boundary_before_timeout_returns_true(self):
        """Baseline: the ordinary turn is unchanged."""
        async def go():
            q = self.queue()
            q.put_nowait({"type": "_turn_boundary", "got_result": True})
            return await _waiter()(self.mission, poll_secs=0.01)
        self.assertTrue(run(go()))

    def test_02_active_worker_past_the_old_300s_returns_true(self):
        """THE REGRESSION THAT CAUSED THE INCIDENT. Frames keep arriving and
        the boundary lands at ~600 elapsed seconds -- twice the old deadline.
        The old waiter returned False here; this one must not."""
        c = self.clock(step=100.0, live=True, boundary_after=6)

        async def go():
            self.queue()
            return await _waiter()(self.mission, clock=c, poll_secs=0.01,
                                   stall_secs=240, max_turn_secs=3600)
        self.assertTrue(run(go()), "an active worker must survive a long turn")
        self.assertGreater(c.state["t"] - 1000.0, 300,
                           "the test must actually cross the old ceiling")

    def test_03_silent_worker_fails_at_stall_secs(self):
        """Silence still stops it -- and not one poll before the threshold."""
        c = self.clock(step=50.0, live=False)

        async def go():
            self.queue()
            shadow_runner._LAST_FRAME_TS[SID] = 1000.0   # last frame, then quiet
            return await _waiter()(self.mission, clock=c, poll_secs=0.01,
                                   stall_secs=240, max_turn_secs=3600)
        self.assertFalse(run(go()))
        silent_for = c.state["t"] - 1000.0
        self.assertGreaterEqual(silent_for, 240, "never fails before STALL_SECS")
        self.assertLess(silent_for, 240 + 50, "and fails within one poll of it")

    def test_04_runaway_frame_producer_stops_at_the_ceiling(self):
        """The one case silence CANNOT catch: frames forever, no boundary."""
        c = self.clock(step=100.0, live=True)            # always fresh, no boundary

        async def go():
            self.queue()
            return await _waiter()(self.mission, clock=c, poll_secs=0.01,
                                   stall_secs=240, max_turn_secs=1000)
        self.assertFalse(run(go()), "the absolute ceiling must still fire")
        self.assertGreaterEqual(c.state["t"] - 1000.0, 1000)

    def test_05_active_and_silent_are_genuinely_DIFFERENT(self):
        """The whole point, asserted as one comparison: comparable elapsed
        time, opposite verdicts, decided only by whether frames arrived."""
        active = self.clock(step=100.0, live=True, boundary_after=6)
        silent = self.clock(step=100.0, live=False)

        async def go_active():
            self.queue()
            return await _waiter()(self.mission, clock=active,
                                   poll_secs=0.01, stall_secs=240)

        async def go_silent():
            shadow_runner._BOUNDARIES.pop(SID, None)
            shadow_runner._LAST_FRAME_TS.pop(SID, None)
            self.queue()
            shadow_runner._LAST_FRAME_TS[SID] = 1000.0
            return await _waiter()(self.mission, clock=silent,
                                   poll_secs=0.01, stall_secs=240)

        self.assertTrue(run(go_active()))
        self.assertFalse(run(go_silent()))
        self.assertGreater(active.state["t"] - 1000.0, 300,
                           "the ACTIVE run really did exceed the old 300s")


# ===================== the edges the fix must not break =================
class TestWaiterEdges(Base):

    def test_06_missing_frame_clock_is_seeded_then_bounded(self):
        """No frame has EVER been seen for this session. It must not read as
        infinitely fresh (hang) -- check_stalls seeds, so this seeds."""
        c = self.clock(step=50.0, live=False)

        async def go():
            self.queue()
            self.assertNotIn(SID, shadow_runner._LAST_FRAME_TS)
            return await _waiter()(self.mission, clock=c, poll_secs=0.01,
                                   stall_secs=240, max_turn_secs=3600)
        self.assertFalse(run(go()))
        self.assertIn(SID, shadow_runner._LAST_FRAME_TS,
                      "the clock was seeded rather than treated as fresh")

    def test_07_no_queue_names_a_precondition_without_waiting(self):
        """NO QUEUE IS NOT A STALL (founder, 2026-09-16). It must still not
        touch the clock -- nothing is waited on -- but what it RETURNS is a
        named precondition rather than False.

        A missing queue means no observer is attached to this session, which
        is a fault in Shadow's own plumbing: _forget_session drops all three
        per-session maps when a runtime is reaped, so a reap-and-reattach
        race leaves the loop waiting on a boundary nobody is pushing. False
        said "the worker went quiet" and the engine spent a mission on it,
        without waiting a single second and without once reading the work.
        A string takes the infra exit instead -- evaluate first, then park as
        NEEDS YOU -- exactly as the sayer's NoLiveRuntime already does at the
        other end of the turn.
        """
        c = self.clock(step=1.0)

        async def go():
            return await _waiter()(self.mission, clock=c, poll_secs=0.01)
        got = run(go())
        self.assertEqual(got, "no_boundary_queue")
        self.assertIsNot(got, False, "a precondition is not a stall")
        self.assertEqual(c.state["n"], 0, "no queue means no wait")

    def test_08_process_death_unblocks_through_the_eof_boundary(self):
        """demux_turn emits a _turn_boundary after EOF, so a worker that
        EXITS ends the wait through the queue -- it never reaches a bound."""
        c = self.clock(step=1.0)

        async def go():
            rt = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, rt)
            for cb in rt.subscribers:                 # the frame demux_turn emits
                cb({"type": "_turn_boundary", "session": SID,
                    "got_result": False, "error": None, "eof": True})
            return await _waiter()(self.mission, clock=c, poll_secs=0.01)
        self.assertTrue(run(go()))

    def test_09_pump_death_without_a_boundary_falls_to_silence(self):
        """start_pump kills and returns on exception, emitting NO boundary.
        Silence is what has to catch that, and within stall_secs."""
        c = self.clock(step=60.0, live=False)

        async def go():
            self.queue()
            shadow_runner._LAST_FRAME_TS[SID] = 1000.0   # frames stopped here
            return await _waiter()(self.mission, clock=c, poll_secs=0.01,
                                   stall_secs=240, max_turn_secs=3600)
        self.assertFalse(run(go()))
        self.assertLess(c.state["t"] - 1000.0, 3600,
                        "caught by silence, not by the ceiling")

    def test_10_observer_stamps_the_clock_the_waiter_relies_on(self):
        """The signal the whole fix depends on, pinned for every frame type
        the waiter's liveness test can see."""
        async def go():
            rt = srt.SessionRuntime()
            shadow_runner.attach_observer(SID, rt)
            for frame in ({"type": "token", "text": "working"},
                          {"type": "error", "detail": "x"},
                          {"type": "_turn_boundary", "got_result": True}):
                shadow_runner._LAST_FRAME_TS.pop(SID, None)
                for cb in rt.subscribers:
                    cb(frame)
                self.assertIn(SID, shadow_runner._LAST_FRAME_TS,
                              "%s must stamp the liveness clock"
                              % frame["type"])
        run(go())

    def test_11_stale_boundary_is_still_drained_before_the_next_say(self):
        """The pre-drain in sayer is what keeps a LONGER wait from consuming
        a previous turn's boundary. Unchanged by this fix, pinned here."""
        async def go():
            q = self.queue()
            q.put_nowait({"type": "_turn_boundary", "stale": True})
            q.put_nowait({"type": "_turn_boundary", "stale": True})
            sayer, _w, _r = shadow_runner.make_bindings(lambda *a, **k: None)
            ok = await sayer(self.mission, "next instruction")
            return ok, q.empty()
        ok, drained = run(go())
        self.assertTrue(ok)
        self.assertTrue(drained, "stale boundaries were drained")


# ===================== the engine contract is untouched =================
class TestEngineContractUnchanged(Base):

    def _mission(self, store):
        m = store.create("a real outcome", "fix", target_session=SID,
                         done_when=[{"tier": "contains_artifact",
                                     "check": "NEVER-APPEARS"}])
        store.transition(m["id"], "brief_confirm", "b")
        store.transition(m["id"], "running", "admitted")
        return m["id"]

    def test_12_waiter_false_still_fails_the_mission(self):
        """mission_engine.py is untouched: False is still a failed turn."""
        store = mission_engine.MissionStore()
        mid = self._mission(store)

        async def sayer(m, t):
            return True

        async def waiter(m):
            return False

        eng = mission_engine.MissionEngine(store, sayer, waiter,
                                           lambda m: "nothing")
        out = run(eng.run_mission(mid))
        self.assertEqual(out["state"], "failed")

    def test_13_takeover_during_a_long_wait_is_still_honored(self):
        """The engine reloads after the wait, so a founder who takes the
        wheel mid-turn wins however long the wait was."""
        store = mission_engine.MissionStore()
        mid = self._mission(store)

        async def sayer(m, t):
            return True

        async def waiter(m):
            mission_engine.MissionEngine(
                store, None, None, None).founder_intervened(mid)
            return True

        eng = mission_engine.MissionEngine(store, sayer, waiter,
                                           lambda m: "nothing")
        out = run(eng.run_mission(mid))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_intervened")


if __name__ == "__main__":
    unittest.main()
