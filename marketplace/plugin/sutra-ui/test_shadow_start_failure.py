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
        """Let the background task the runner created actually run.

        It used to wait for a TERMINAL state. A pre-launch fault no longer
        reaches one (2026-09-17), so the signal is the handler having run at
        all: the start stamp cleared, or a terminal state for the arms that
        still have one."""
        for _ in range(limit):
            await asyncio.sleep(0.01)
            m = s.store.load(s.mid) or {}
            if m.get("state") in mission_engine.TERMINAL:
                return
            if not m.get("start_requested_at"):
                return
        return

    async def test_a_pre_launch_fault_does_NOT_fail_the_mission(self):
        """WHAT CHANGED, AND WHY (founder, 2026-09-17; m-b3eefc51a768).

        This file's original assertion was "a start that never got off the
        ground must reach the EXISTING failed state". The symptom it was
        written against is real and is still pinned below -- a dead row that
        can never be started -- but `failed` was the wrong cure. A pre-launch
        fault means NO WORKER WAS EVER SPAWNED: target_session is None and
        turns_used is 0, so there is nothing whose outcome `failed` could
        describe. The live case was a stale write while the task's Shadow
        chat was being published, and the founder was shown a FAILED task
        that had never run anything.

        So the mission stays where it is and becomes STARTABLE again. The
        dead row is cured by clearing start_requested_at, not by ending the
        mission."""
        s = _Store("a delegate that dies at argv")

        async def boom(mission):
            raise RuntimeError("spawn died at argv")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(s)
        m = s.store.load(s.mid)
        self.assertNotEqual(m["state"], "failed",
                            "a fault before the worker exists is not the "
                            "mission failing")
        self.assertEqual(m["state"], "brief_confirm",
                         "it stays where it was, ready to start again")
        self.assertIsNone(m.get("target_session"),
                          "and no worker was ever spawned")
        self.assertEqual(m.get("turns_used") or 0, 0)

    async def test_the_dead_row_is_still_cured(self):
        """THE ORIGINAL SYMPTOM, unchanged: brief_confirm WITH
        start_requested_at set is what the list draws as QUEUED with no Start
        button. Clearing the stamp is what makes the row READY again."""
        s = _Store("the dead row")

        async def boom(mission):
            raise RuntimeError("boom")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(s)
        m = s.store.load(s.mid)
        self.assertIsNone(m.get("start_requested_at"),
                          "the start stamp must be cleared or the row is "
                          "QUEUED forever with no way to start it")

    async def test_the_reason_is_recorded_not_swallowed(self):
        s = _Store("the note says why")

        async def boom(mission):
            raise RuntimeError("no such interpreter")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        await self._settle(s)
        rows = [r for r in mission_engine.shadow_ledger.read("missions")
                if r.get("mission_id") == s.mid]
        self.assertTrue(
            any("provision" in (r.get("note") or "") for r in rows),
            "the ledger must carry why the start failed: %r" % (rows,))
        self.assertTrue(
            any("startable again, not" in (r.get("note") or "")
                for r in rows),
            "and must say it was NOT a mission failure")

    async def test_the_exact_stale_write_race_cannot_fail_a_mission(self):
        """THE LIVE REPRODUCTION, as a test.

        Booting the task's Shadow chat stamps `task_chat_session` and
        `task_chat` onto the record -- two saves, two sequence bumps -- while
        provisioning holds a copy loaded before them. The held save then hits
        MissionStore's stale-write guard. This spawner reproduces exactly
        that: it advances the sequence twice, the way publication does, and
        then raises the ValueError the guard raises."""
        s = _Store("the stale write")
        held = s.store.load(s.mid)          # the copy provisioning would hold

        async def stamps_then_stale(mission):
            for field, val in (("task_chat_session", "tc-1"),
                               ("task_chat", "chat-1")):
                fresh = s.store.load(s.mid)
                fresh[field] = val
                s.store.save(fresh)          # the sequence advances
            s.store.save(held)               # ...and the held copy is refused
            raise AssertionError("the guard did not fire")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=stamps_then_stale)
        await self._settle(s)
        m = s.store.load(s.mid)
        self.assertNotEqual(
            m["state"], "failed",
            "a bookkeeping collision must never read as mission failure")
        self.assertEqual(m["state"], "brief_confirm")
        self.assertIsNone(m.get("start_requested_at"),
                          "and the task is startable again")
        self.assertEqual(m.get("task_chat_session"), "tc-1",
                         "the stamps that won the race are still on the "
                         "record -- the guard protected them, as designed")

    async def test_the_guard_itself_is_untouched(self):
        """The stale-write guard is not weakened by any of this: a writer
        holding an older sequence is still refused."""
        s = _Store("the guard stands")
        held = s.store.load(s.mid)
        fresh = s.store.load(s.mid)
        fresh["objective"] = "moved on"
        s.store.save(fresh)
        with self.assertRaises(ValueError) as caught:
            s.store.save(held)
        self.assertIn("stale write", str(caught.exception))

    async def test_a_worker_that_genuinely_dies_still_FAILS(self):
        """THE ARM THAT MUST NOT CHANGE. A mission whose worker existed and
        is gone -- running, a target_session, nothing in DELEGATES -- has no
        road left, and keeps the terminal state it has always had."""
        s = _Store("a worker that died")

        async def boom(mission):
            # adoption is what makes a mission running mid-spawn
            # (app._publish_delegate_chat step 1b), so the orphaned arm is
            # reached by a spawn that announces its session and THEN dies --
            # not by a mission that was already running when go() started,
            # which go() returns from as a double-start no-op.
            mm = s.store.load(s.mid)
            mm["target_session"] = "sess-gone"
            s.store.save(mm)
            s.store.transition(s.mid, "running", "adopted")
            raise RuntimeError("the delegate was reaped")

        shadow_runner.start_mission_async(
            s.mid, lambda *a, **k: None, provisioner=boom)
        for _ in range(200):
            await asyncio.sleep(0.01)
            if s.state() in mission_engine.TERMINAL:
                break
        self.assertEqual(s.state(), "failed",
                         "an orphaned running mission still fails")


if __name__ == "__main__":
    unittest.main()
