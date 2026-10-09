"""A worker gone quiet mid-turn is said on its task BEFORE the stall end
(founder, 2026-10-08: "keep the 4-minute end, add a warning").

  WINDOW    only while Shadow waits on the worker's turn (_WAITING_ON, set and
            cleared by the real waiter) -- never while Shadow itself decides.
  WARNING   quiet_report says nothing under QUIET_WARN_SECS (2 min), then
            {secs, ends_in} counted against STALL_SECS (4 min).
  UNCHANGED STALL_SECS is still 240 and a silent turn still ends at it.
  SURFACE   GET /api/shadow/missions carries `quiet` on that task only.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_quiet.py
"""
import asyncio
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-quiet-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402

SID = "sess-quiet-1"
RUNNING = {"id": "m-q1", "state": "running", "target_session": SID}


class Report(unittest.TestCase):
    def tearDown(self):
        shadow_runner._WAITING_ON.pop(SID, None)
        shadow_runner._LAST_FRAME_TS.pop(SID, None)

    def test_01_the_stall_end_is_unchanged(self):
        self.assertEqual(shadow_runner.STALL_SECS, 240)
        self.assertEqual(shadow_runner.QUIET_WARN_SECS, 120)

    def test_02_nothing_when_shadow_is_not_waiting_on_a_turn(self):
        shadow_runner._LAST_FRAME_TS[SID] = 1000
        self.assertIsNone(shadow_runner.quiet_report(RUNNING, now=5000),
                          "between turns Shadow is deciding: quiet is normal")

    def test_03_nothing_under_two_minutes(self):
        shadow_runner._WAITING_ON[SID] = 1000
        shadow_runner._LAST_FRAME_TS[SID] = 1000
        self.assertIsNone(shadow_runner.quiet_report(RUNNING, now=1119))

    def test_04_two_minutes_says_how_long_and_how_long_is_left(self):
        shadow_runner._WAITING_ON[SID] = 1000
        shadow_runner._LAST_FRAME_TS[SID] = 1000
        self.assertEqual(shadow_runner.quiet_report(RUNNING, now=1150),
                         {"secs": 150, "ends_in": 90})

    def test_05_the_clock_starts_at_the_turn_not_at_an_old_frame(self):
        shadow_runner._LAST_FRAME_TS[SID] = 100      # last turn's output
        shadow_runner._WAITING_ON[SID] = 1000        # this turn began here
        self.assertIsNone(shadow_runner.quiet_report(RUNNING, now=1060))

    def test_06_only_a_running_task(self):
        shadow_runner._WAITING_ON[SID] = 1000
        for state in ("paused", "blocked", "done", "brief_confirm"):
            self.assertIsNone(shadow_runner.quiet_report(
                dict(RUNNING, state=state), now=1200), state)


class TheRealWaiter(unittest.TestCase):
    """make_bindings' waiter opens the window on entry and closes it on every
    way out -- a boundary, a stall, or a cancel."""

    def setUp(self):
        _s, self.waiter, _r = shadow_runner.make_bindings(
            lambda *a, **k: None)

    def tearDown(self):
        shadow_runner._BOUNDARIES.pop(SID, None)
        shadow_runner._WAITING_ON.pop(SID, None)
        shadow_runner._LAST_FRAME_TS.pop(SID, None)

    def test_10_open_while_waiting_closed_on_a_boundary(self):
        async def main():
            q = asyncio.Queue()
            shadow_runner._BOUNDARIES[SID] = q
            task = asyncio.ensure_future(self.waiter(RUNNING, poll_secs=0.01))
            await asyncio.sleep(0.03)
            self.assertIn(SID, shadow_runner._WAITING_ON)
            q.put_nowait({"type": "_turn_boundary"})
            self.assertIs(await task, True)
            self.assertNotIn(SID, shadow_runner._WAITING_ON)
        asyncio.run(main())

    def test_11_closed_after_a_stall_which_still_ends_the_turn(self):
        t = {"now": 1000.0}

        def clock():
            t["now"] += 100
            return t["now"]

        async def main():
            shadow_runner._BOUNDARIES[SID] = asyncio.Queue()
            shadow_runner._LAST_FRAME_TS[SID] = 1000.0
            got = await self.waiter(RUNNING, clock=clock, poll_secs=0.001)
            self.assertIs(got, False, "silence still ends the turn")
            self.assertNotIn(SID, shadow_runner._WAITING_ON)
        asyncio.run(main())

    def test_12_closed_when_the_wait_is_cancelled(self):
        async def main():
            shadow_runner._BOUNDARIES[SID] = asyncio.Queue()
            task = asyncio.ensure_future(self.waiter(RUNNING, poll_secs=0.01))
            await asyncio.sleep(0.03)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.assertNotIn(SID, shadow_runner._WAITING_ON)
        asyncio.run(main())


class TheList(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        self.store = mission_engine.MissionStore()
        self.saved = providers.shadow_enabled
        providers.shadow_enabled = lambda: True

    def tearDown(self):
        providers.shadow_enabled = self.saved
        shadow_runner._WAITING_ON.pop(SID, None)
        shadow_runner._LAST_FRAME_TS.pop(SID, None)
        for m in self.store.list():
            self.store.delete(m["id"])

    def test_20_the_quiet_task_carries_it_and_no_other(self):
        a = self.store.create("quiet one", "feature", target_mode="new",
                              done_when=[])
        b = self.store.create("other one", "feature", target_mode="new",
                              done_when=[])
        for m in (a, b):
            self.store.transition(m["id"], "brief_confirm", "ready")
            self.store.transition(m["id"], "running", "go")
        m = self.store.load(a["id"])
        m["target_session"] = SID
        self.store.save(m)
        import time
        shadow_runner._WAITING_ON[SID] = time.time() - 150
        shadow_runner._LAST_FRAME_TS[SID] = time.time() - 150
        got = {x["id"]: x for x in self.client.get(
            "/api/shadow/missions").json()["missions"]}
        self.assertGreaterEqual(got[a["id"]]["quiet"]["secs"], 150)
        self.assertNotIn("quiet", got[b["id"]])
        self.assertNotIn("quiet", self.store.load(a["id"]),
                         "computed per read, never stored")


if __name__ == "__main__":
    unittest.main()
