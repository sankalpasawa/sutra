"""A stalled turn asks the founder; it does not quietly fail a goal (2026-09-14).

WHY THIS FILE EXISTS. Every other machine-run exit in run_mission -- budget
exhausted, ping-pong, ask_founder, undecided, an undelivered say -- goes
through `_out_of_road`, whose entire job is the V5 rule:

    an attempt OF A GOAL blocks and the founder is asked;
    a STANDALONE mission keeps its historical terminal state.

The waiter-timeout exit did not. It called `store.transition(mid, "failed")`
directly, so a goal whose worker went quiet died as FAILED with the founder
never asked -- the one thing the goal lifecycle exists to prevent. A stalled
turn means the worker stopped producing output; it says nothing about whether
the outcome is still reachable, which is exactly the judgement `_out_of_road`
hands to the founder.

The waiter itself is UNTOUCHED here: it still returns True/False, and False
still means the same thing. Only where False is routed changed.
"""
import asyncio
import os
import tempfile
import unittest

import mission_engine


SID = "sess-stall-routing"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.store = mission_engine.MissionStore()

    def tearDown(self):
        asyncio.get_event_loop().close()
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def _mission(self, goal_id=None):
        """A running mission whose check can never be met by the transcript,
        so the loop always reaches the say/wait it is here to exercise."""
        m = self.store.create("a real outcome", "fix", target_session=SID,
                              done_when=[{"tier": "contains_artifact",
                                          "check": "NEVER-APPEARS"}],
                              goal_id=goal_id)
        self.store.transition(m["id"], "brief_confirm", "b")
        self.store.transition(m["id"], "running", "admitted")
        return m["id"]

    def _engine(self, waiter, reader=lambda m: "nothing"):
        async def sayer(m, t):
            return True
        return mission_engine.MissionEngine(self.store, sayer, waiter, reader)

    @staticmethod
    def _stalls():
        async def waiter(m):
            return False
        return waiter

    @staticmethod
    def _arrives():
        async def waiter(m):
            return True
        return waiter


# =================== the fix: a goal reaches the founder =================
class TestGoalBackedStall(Base):

    def test_01_a_stalled_goal_attempt_BLOCKS(self):
        """NEEDS YOU, not FAILED. `blocked` is the engine's founder-facing
        state and is deliberately not in TERMINAL."""
        mid = self._mission(goal_id="g-1")
        out = run(self._engine(self._stalls()).run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertNotIn(out["state"], mission_engine.TERMINAL,
                         "a blocked attempt is still answerable")

    def test_02_it_never_passes_through_failed(self):
        """Not merely "ends blocked" -- it must never be written as failed on
        the way there, or the feed and the goal both see a dead attempt."""
        mid = self._mission(goal_id="g-1")
        seen = []
        real = self.store.transition

        def spy(m_id, new_state, note=""):
            seen.append(new_state)
            return real(m_id, new_state, note)

        self.store.transition = spy
        try:
            out = run(self._engine(self._stalls()).run_mission(mid))
        finally:
            self.store.transition = real
        self.assertEqual(out["state"], "blocked")
        self.assertNotIn("failed", seen,
                         "no silent FAILED transition on the goal path")

    def test_03_the_blocker_is_NAMED(self):
        """store.block refuses a reasonless block, and an unanswerable
        'Shadow needs you' is what the reason exists to prevent."""
        mid = self._mission(goal_id="g-1")
        out = run(self._engine(self._stalls()).run_mission(mid))
        self.assertEqual(out.get("block_reason"), "turn_stalled")

    def test_04_the_target_chat_is_KEPT(self):
        """The point of blocking instead of failing: the founder resumes the
        same chat. The mission must still name it."""
        mid = self._mission(goal_id="g-1")
        out = run(self._engine(self._stalls()).run_mission(mid))
        self.assertEqual(out["target_session"], SID)
        self.assertEqual(out["goal_id"], "g-1")


# ============ the half that must NOT move: standalone missions ==========
class TestStandaloneUnchanged(Base):

    def test_05_a_stalled_standalone_mission_still_FAILS(self):
        """The historical behaviour, byte for byte -- same state, same note.
        test_shadow_waiter.py::test_12 pins this too; it is restated here
        because this is the file that would break it."""
        mid = self._mission(goal_id=None)
        out = run(self._engine(self._stalls()).run_mission(mid))
        self.assertEqual(out["state"], "failed")
        self.assertIn(out["state"], mission_engine.TERMINAL)

    def test_06_out_of_road_semantics_are_untouched(self):
        """The helper this fix now routes through must still split the two
        cases the same way for the exits that ALREADY used it. Budget
        exhaustion is the cleanest: it needs no waiter at all."""
        solo = self._mission(goal_id=None)
        m = self.store.load(solo)
        m["turns_used"] = m["max_turns"]
        self.store.save(m)
        out = run(self._engine(self._arrives()).run_mission(solo))
        self.assertEqual(out["state"], "failed")
        self.assertIsNone(out.get("block_reason"),
                          "a standalone mission is not blocked, it ends")

        goal = self._mission(goal_id="g-2")
        m = self.store.load(goal)
        m["turns_used"] = m["max_turns"]
        self.store.save(m)
        out = run(self._engine(self._arrives()).run_mission(goal))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out.get("block_reason"), "budget_exhausted")


# ================== and completion still completes ======================
class TestCompletionUnchanged(Base):

    def test_07_a_met_check_still_finishes_goal_and_standalone_alike(self):
        """A waiter that ARRIVES plus evidence that satisfies the check is
        the happy path; the routing change must be invisible to it."""
        for goal_id, label in ((None, "standalone"), ("g-3", "goal-backed")):
            mid = self._mission(goal_id=goal_id)
            eng = self._engine(self._arrives(),
                               reader=lambda m: "here is NEVER-APPEARS now")
            out = run(eng.run_mission(mid))
            self.assertEqual(out["state"], "done",
                             "%s completion is unchanged" % label)


if __name__ == "__main__":
    unittest.main()
