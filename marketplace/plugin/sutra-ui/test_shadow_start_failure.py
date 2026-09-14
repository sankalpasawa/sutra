"""A start that never gets off the ground must END, not hang as QUEUED.

THE BUG THIS PINS (founder, 2026-09-14). `+ Delegate -> Create Task` already
calls the existing start -- shadowCreateTask awaits shadowMissionAct(id,
"start_now"), the same action the Start button posts -- so the wiring was
never the problem. What was missing sat one layer down, in the failure path:

  shadow_runner.start_mission_async.go() catches everything a start can
  throw and, when the mission is still pre-launch, calls

      store.transition(mid, "failed", "provision/admit failed: ...")

  The guard already named the two pre-launch states ("brief_confirm",
  "queued") -- but TRANSITIONS listed `failed` under NEITHER, so that call
  raised ValueError, and the handler's own `except Exception: pass` ate it.
  The mission stayed brief_confirm with start_requested_at set, which the
  task list draws as QUEUED with no Start button. A dead row, forever, and
  no record anywhere of why.

  It was reachable in the ordinary way: a delegate spawn that dies at argv.
  (The founder hit it with a server hand-launched on Python 3.9, where
  session_runtime's `process_group=0` is a TypeError -- but the interpreter
  is incidental. ANY provisioning failure produced the same dead row.)

WHAT IS ASSERTED HERE, and deliberately nothing more: `failed` is reachable
from exactly the two states the existing handler guards on, every other row
of the table is untouched, and a real start_mission_async whose provisioner
raises leaves a FAILED mission rather than a frozen one. No new state, no
new mechanism, and the success path is asserted unchanged.

Run: .venv/bin/python -m unittest test_shadow_start_failure -v
"""
import asyncio
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-startfail-")

import mission_engine  # noqa: E402
import shadow_runner  # noqa: E402


class TheTransitionTable(unittest.TestCase):
    """The table IS the state machine, so the widening is asserted exactly."""

    def test_failed_is_reachable_from_both_pre_launch_states(self):
        for state in ("brief_confirm", "queued"):
            self.assertIn(
                "failed", mission_engine.TRANSITIONS[state],
                "%s is a state start_mission_async's handler guards on; it "
                "must be able to reach failed" % state)

    def test_the_success_path_is_untouched(self):
        self.assertIn("running", mission_engine.TRANSITIONS["brief_confirm"])
        self.assertIn("queued", mission_engine.TRANSITIONS["brief_confirm"])
        self.assertIn("running", mission_engine.TRANSITIONS["queued"])

    def test_no_other_row_was_widened(self):
        """A regression fence: only two rows may have changed, and `failed`
        stays terminal. If someone widens the machine further, this fails."""
        self.assertEqual(mission_engine.TRANSITIONS, {
            "draft": ("brief_confirm", "stopped"),
            "brief_confirm": ("running", "queued", "draft", "failed",
                              "stopped"),
            "running": ("paused", "blocked", "done", "failed", "stopped"),
            "queued": ("running", "failed", "stopped"),
            "paused": ("running", "stopped", "failed"),
            "blocked": ("running", "stopped"),
            "done": (), "failed": (), "stopped": (),
        })

    def test_failed_is_still_terminal(self):
        self.assertIn("failed", mission_engine.TERMINAL)
        self.assertEqual(mission_engine.TRANSITIONS["failed"], ())


class _Store:
    """One brief_confirm mission, the state an accepted start sits in."""

    def __init__(self, objective="boom"):
        self.store = mission_engine.MissionStore()
        m = self.store.create(objective, "fix", target_mode="new",
                              target_session=None, done_when=[],
                              manifest="say READY and stop")
        self.mid = m["id"]
        self.store.transition(self.mid, "brief_confirm", "proposed")

    def state(self):
        return (self.store.load(self.mid) or {}).get("state")


class AStartThatDies(unittest.IsolatedAsyncioTestCase):
    """The real start_mission_async, with a provisioner that raises."""

    async def _settle(self, s, limit=200):
        """Let the background task the runner created actually run."""
        for _ in range(limit):
            await asyncio.sleep(0.01)
            if s.state() in mission_engine.TERMINAL:
                return
        return

    async def test_a_provisioner_that_raises_ends_as_failed(self):
        s = _Store("a delegate that dies at argv")

        async def boom(mission):
            raise RuntimeError("spawn died at argv")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(s)
        self.assertEqual(
            s.state(), "failed",
            "a start that never got off the ground must reach the EXISTING "
            "failed state, not sit in brief_confirm as a permanent QUEUED row")

    async def test_the_reason_is_recorded_not_swallowed(self):
        s = _Store("the note says why")

        async def boom(mission):
            raise RuntimeError("no such interpreter")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(s)
        m = s.store.load(s.mid)
        self.assertEqual(m["state"], "failed")
        rows = [r for r in mission_engine.shadow_ledger.read("missions")
                if r.get("mission_id") == s.mid]
        self.assertTrue(
            any("provision" in (r.get("note") or "") for r in rows),
            "the ledger must carry why the start failed: %r" % (rows,))

    async def test_it_is_no_longer_stuck_in_brief_confirm(self):
        """The exact symptom, stated as its own assertion."""
        s = _Store("the dead row")

        async def boom(mission):
            raise RuntimeError("boom")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(s)
        self.assertNotEqual(s.state(), "brief_confirm")
        self.assertNotEqual(s.state(), "queued")


if __name__ == "__main__":
    unittest.main()
