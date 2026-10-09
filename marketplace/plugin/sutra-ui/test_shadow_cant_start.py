"""A task Shadow cannot start says WHY, with one action (founder, 2026-10-08,
from Paperclip: "one automatic recovery, then a clear blocked state with one
action for you").

  RETRIES   a start that fails before any worker exists is retried
            START_RETRY_DELAYS times; when every retry has failed the task
            carries `start_blocked` -- a plain reason -- instead of going back
            to a bare READY with no record of why.
  PRECHECK  a start that is CERTAIN to fail (Claude not the AI in use, Claude
            not found, the work folder gone) is blocked at once with that
            reason, and spends no retry and no worker.
  TRY AGAIN pressing it (start_now -> _mark_start_requested) clears the
            reason and gives the start fresh retries.

No new mission state: the task stays brief_confirm, and the transition table
pinned by test_shadow_start_failure is untouched.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_cant_start.py
"""
import asyncio
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-cant-")

from fastapi import HTTPException              # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import shadow_runner                           # noqa: E402


def drive(mid, provisioner):
    """Run one start_mission_async to the end of its first try, on a loop of
    its own. A retry it schedules sleeps 10s and is cancelled with the loop:
    these tests are about what ONE try leaves on the record."""
    async def main():
        shadow_runner.start_mission_async(mid, None, provisioner=provisioner)
        for _ in range(50):
            await asyncio.sleep(0)
    asyncio.run(main())


class Base(unittest.TestCase):
    def setUp(self):
        self.store = mission_engine.MissionStore()
        self.saved_pre = shadow_runner.DEFAULT_PRECHECK["fn"]
        shadow_runner.DEFAULT_PRECHECK["fn"] = None
        self.calls = []

    def tearDown(self):
        shadow_runner.DEFAULT_PRECHECK["fn"] = self.saved_pre
        for m in self.store.list():
            try:
                self.store.delete(m["id"])
            except Exception:
                pass

    def new_task(self, attempts=0):
        m = self.store.create("Write the launch note", "feature",
                              target_mode="new", done_when=[])
        m = self.store.transition(m["id"], "brief_confirm", "brief ready")
        self.assertEqual(m["state"], "brief_confirm")
        m["start_requested_at"] = mission_engine._now()
        m["start_attempts"] = attempts
        self.store.save(m)
        return m["id"]

    async def _lost(self, mission):
        self.calls.append(mission["id"])
        raise ConnectionError("Connection lost")

    def lost(self, mission):
        return self._lost(mission)


class Retries(Base):
    def test_01_a_retry_left_says_nothing_yet(self):
        mid = self.new_task(attempts=0)
        drive(mid, self.lost)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "brief_confirm")
        self.assertEqual(m["start_attempts"], 1)
        self.assertTrue(m.get("start_requested_at"), "still on its way")
        self.assertNotIn("start_blocked", m)

    def test_02_every_retry_spent_says_why_in_plain_words(self):
        mid = self.new_task(attempts=len(shadow_runner.START_RETRY_DELAYS))
        drive(mid, self.lost)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "brief_confirm", "no new state, not failed")
        self.assertIsNone(m.get("start_requested_at"))
        blocked = m["start_blocked"]
        self.assertEqual(blocked["attempts"], 4)
        self.assertIn("Shadow tried 4 times", blocked["reason"])
        self.assertIn("connection to Claude dropped", blocked["reason"])
        self.assertNotIn("Traceback", blocked["reason"])
        self.assertIn("Connection lost", blocked["detail"],
                      "the raw error is kept beside the sentence")

    def test_03_plain_start_error_never_shows_a_stack(self):
        f = shadow_runner.plain_start_error
        self.assertIn("dropped", f(ConnectionError("Connection lost")))
        self.assertIn("too long", f(TimeoutError("timed out")))
        self.assertEqual(f(RuntimeError("weird internal thing")),
                         "the worker could not be started")


class Precheck(Base):
    def test_10_a_start_certain_to_fail_is_blocked_at_once(self):
        shadow_runner.DEFAULT_PRECHECK["fn"] = \
            lambda m: "Switch to Claude, then try again."
        mid = self.new_task()
        drive(mid, self.lost)
        m = self.store.load(mid)
        self.assertEqual(self.calls, [], "no worker was even attempted")
        self.assertEqual(m["start_blocked"]["reason"],
                         "Switch to Claude, then try again.")
        self.assertIsNone(m.get("start_requested_at"))
        self.assertEqual(m.get("start_attempts"), 0, "no retry was spent")

    def test_11_no_problem_means_the_start_goes_ahead(self):
        shadow_runner.DEFAULT_PRECHECK["fn"] = lambda m: None
        mid = self.new_task()
        drive(mid, self.lost)
        self.assertEqual(self.calls, [mid])
        self.assertNotIn("start_blocked", self.store.load(mid))

    def test_12_a_check_that_breaks_never_blocks_a_start(self):
        def boom(m):
            raise RuntimeError("the check itself broke")
        shadow_runner.DEFAULT_PRECHECK["fn"] = boom
        mid = self.new_task()
        drive(mid, self.lost)
        self.assertEqual(self.calls, [mid])
        self.assertNotIn("start_blocked", self.store.load(mid))


class AppPrecheck(unittest.TestCase):
    """app._shadow_start_precheck: only what is certain, in plain words."""

    def setUp(self):
        self.saved = (app_module._shadow_args,
                      app_module._shadow_workdir_for_delegates)

    def tearDown(self):
        (app_module._shadow_args,
         app_module._shadow_workdir_for_delegates) = self.saved

    def test_20_another_ai_selected(self):
        def refuse(*a, **k):
            raise HTTPException(503, "Shadow and its delegates run on Claude "
                                     "only in this build; ...")
        app_module._shadow_args = refuse
        got = app_module._shadow_start_precheck({})
        self.assertIn("Switch to Claude", got)

    def test_21_the_work_folder_is_gone(self):
        app_module._shadow_args = lambda *a, **k: []
        gone = os.path.join(tempfile.gettempdir(), "no-such-folder-cant-start")
        app_module._shadow_workdir_for_delegates = lambda: gone
        got = app_module._shadow_start_precheck({})
        self.assertIn("doesn't exist any more", got)
        self.assertIn(gone, got)

    def test_22_all_well_is_none(self):
        app_module._shadow_args = lambda *a, **k: []
        app_module._shadow_workdir_for_delegates = tempfile.gettempdir
        self.assertIsNone(app_module._shadow_start_precheck({}))

    def test_23_an_unexpected_error_is_not_a_reason(self):
        def odd(*a, **k):
            raise RuntimeError("something else")
        app_module._shadow_args = odd
        self.assertIsNone(app_module._shadow_start_precheck({}))

    def test_24_it_is_wired_at_startup(self):
        src = open(app_module.__file__, encoding="utf-8").read()
        self.assertIn("shadow_runner.set_default_precheck("
                      "_shadow_start_precheck)", src)


class TryAgain(Base):
    def test_30_try_again_clears_the_reason_and_the_count(self):
        mid = self.new_task(attempts=4)
        shadow_runner.block_start(self.store, mid, "it broke")
        self.assertIn("start_blocked", self.store.load(mid))
        app_module._mark_start_requested(self.store, mid)
        m = self.store.load(mid)
        self.assertNotIn("start_blocked", m)
        self.assertEqual(m["start_attempts"], 0)
        self.assertTrue(m["start_requested_at"])

    def test_31_block_start_never_touches_a_task_that_moved_on(self):
        mid = self.new_task()
        self.store.transition(mid, "stopped", "founder stopped it")
        shadow_runner.block_start(self.store, mid, "late reason")
        self.assertNotIn("start_blocked", self.store.load(mid))


if __name__ == "__main__":
    unittest.main()
