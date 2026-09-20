"""Take Over must stay PAUSED, even when it lands mid-compose.

THE BUG (founder, 2026-09-14): "task was running, chat at turn 3, I clicked
TAKE OVER, the task went FAILED."

Take Over does two things and both are correct: it pauses the mission
(founder_intervened) and it reaps the delegate, because ownership has to end
or the founder cannot type into the chat. What was wrong is what the loop
did next. Composing an instruction is a model call -- 9 seconds on mission
m-8935e9a46557 -- and the loop had already passed its top-of-iteration state
check when the takeover landed inside that gap. Holding a pre-takeover
snapshot, it said into a session whose runtime had just been reaped, got the
"no_live_runtime" precondition back, and sent a DELIBERATE disownment down
_out_of_road as a failure:

    t+206s  say      turn 3
    t+214s  paused   "founder typed in the target session"
    t+215s  say NOT DELIVERED (no_live_runtime)
    t+215s  failed   "say not delivered (no_live_runtime) -- nothing was sent"

It cleared pause_reason on the way, so the record stopped saying the founder
had taken over at all.

THE FIX, asserted here: run_mission reloads the record immediately before
the say -- the same reload step 8 already does after the boundary wait --
and returns the fresh mission if the founder has taken the wheel. The say is
never attempted, so there is no no_live_runtime to mis-route. No new state,
no special case for that string, and _out_of_road is untouched.

Run: .venv/bin/python -m unittest test_shadow_takeover_race -v
"""
import asyncio
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-takeover-")

import mission_engine  # noqa: E402
from mission_engine import MissionEngine, MissionStore  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.store = MissionStore()
        self.says = []

    def _running(self, turns=1):
        """A mission mid-flight: past turn 0, so the decider is consulted and
        there is a real compose window to land a takeover in."""
        m = self.store.create("research the memo", "fix",
                              target_mode="new", target_session="sess-1",
                              done_when=[])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        self.store.transition(mid, "running", "admitted")
        m = self.store.load(mid)
        m["turns_used"] = turns
        self.store.save(m)
        return mid

    def _engine(self, decider, say_ok=True):
        async def sayer(m, text):
            self.says.append(text)
            return say_ok

        async def waiter(m):
            return True

        def reader(m):
            return " ".join(self.says)

        return MissionEngine(self.store, sayer, waiter, reader,
                             decider=decider)

    def _take_over(self, mid):
        """Exactly what POST /act {"action":"take_over"} writes."""
        m = self.store.transition(mid, "paused",
                                  "founder typed in the target session")
        m["pause_reason"] = "founder_intervened"
        self.store.save(m)


class TakeOverDuringComposition(Base):
    """The reported sequence, start to finish."""

    def test_the_say_is_never_attempted(self):
        mid = self._running()

        async def decider(ctx):
            # the takeover lands while Shadow is still composing
            self._take_over(mid)
            return {"action": "continue", "instruction": "keep going"}

        # say_ok is the STRING the reaped runtime really returns -- if the
        # loop ever reaches the sayer, this is what used to fail the mission
        eng = self._engine(decider, say_ok="no_live_runtime")
        m = asyncio.get_event_loop().run_until_complete(eng.run_mission(mid))

        self.assertEqual(self.says, [],
                         "the sayer must not be called once the founder has "
                         "taken the wheel: %r" % (self.says,))
        self.assertEqual(m["state"], "paused")
        self.assertNotEqual(m["state"], "failed")

    def test_the_pause_and_its_reason_survive(self):
        mid = self._running()

        async def decider(ctx):
            self._take_over(mid)
            return {"action": "continue", "instruction": "keep going"}

        asyncio.get_event_loop().run_until_complete(
            self._engine(decider, say_ok="no_live_runtime").run_mission(mid))
        rec = self.store.load(mid)
        self.assertEqual(rec["state"], "paused")
        self.assertEqual(
            rec["pause_reason"], "founder_intervened",
            "the record must still say the founder took over -- the old path "
            "cleared this on its way to failed")

    def test_the_turn_is_not_spent(self):
        mid = self._running(turns=3)

        async def decider(ctx):
            self._take_over(mid)
            return {"action": "continue", "instruction": "keep going"}

        asyncio.get_event_loop().run_until_complete(
            self._engine(decider, say_ok="no_live_runtime").run_mission(mid))
        self.assertEqual(self.store.load(mid)["turns_used"], 3,
                         "nothing was sent, so nothing was spent")

    def test_the_ledger_has_no_failure_row(self):
        mid = self._running()

        async def decider(ctx):
            self._take_over(mid)
            return {"action": "continue", "instruction": "keep going"}

        asyncio.get_event_loop().run_until_complete(
            self._engine(decider, say_ok="no_live_runtime").run_mission(mid))
        rows = [r for r in mission_engine.shadow_ledger.read("missions")
                if r.get("mission_id") == mid]
        self.assertFalse(
            [r for r in rows if r.get("state") == "failed"],
            "a takeover must leave no failure in the audit trail: %r" % (rows,))


class TheSameGuardClosesTheStopRace(Base):
    """Founder stop mid-compose had the identical window."""

    def test_a_stop_during_composition_is_honoured(self):
        mid = self._running()

        async def decider(ctx):
            self.store.transition(mid, "stopped", "founder stop (home)")
            return {"action": "continue", "instruction": "keep going"}

        m = asyncio.get_event_loop().run_until_complete(
            self._engine(decider, say_ok="no_live_runtime").run_mission(mid))
        self.assertEqual(self.says, [], "a stopped mission must not speak")
        self.assertEqual(m["state"], "stopped")

    def test_a_block_during_composition_is_honoured(self):
        mid = self._running()

        async def decider(ctx):
            m = self.store.transition(mid, "blocked", "needs the founder")
            self.store.save(m)
            return {"action": "continue", "instruction": "keep going"}

        m = asyncio.get_event_loop().run_until_complete(
            self._engine(decider, say_ok="no_live_runtime").run_mission(mid))
        self.assertEqual(self.says, [])
        self.assertEqual(m["state"], "blocked")


class TheNormalPathIsUnchanged(Base):
    """The guard must cost a healthy mission nothing."""

    def test_a_running_mission_still_sends_its_instruction(self):
        mid = self._running()
        sent = {"n": 0}

        async def decider(ctx):
            sent["n"] += 1
            if sent["n"] > 1:
                return {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}
            return {"action": "continue", "instruction": "do the next bit"}

        asyncio.get_event_loop().run_until_complete(
            self._engine(decider).run_mission(mid))
        self.assertIn("do the next bit", self.says,
                      "nobody interfered, so the instruction must go out")

    def test_the_turn_counter_still_advances(self):
        mid = self._running(turns=2)
        sent = {"n": 0}

        async def decider(ctx):
            sent["n"] += 1
            if sent["n"] > 1:
                return {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}
            return {"action": "continue", "instruction": "carry on"}

        asyncio.get_event_loop().run_until_complete(
            self._engine(decider).run_mission(mid))
        self.assertEqual(self.store.load(mid)["turns_used"], 3,
                         "a delivered say still spends its turn")

    def test_a_genuine_no_live_runtime_still_ends_the_turn(self):
        """The guard must not swallow a REAL precondition failure -- one that
        happens with nobody having touched the mission.

        WHAT IS PINNED HERE, AND WHAT MOVED (2026-09-16). This test is about
        the TAKEOVER guard: a mission nobody touched must still go down the
        precondition path rather than sail on as if the say had landed. That
        is unchanged, and is what the assertions below check.

        Where that path LANDS is a different question, answered again after
        mission m-6b177e1cbdf0: a say that never left says nothing about the
        work, so it parks the mission as NEEDS YOU instead of killing it
        (mission_engine.INFRA_BLOCK_REASONS). `blocked` is non-terminal, so
        this still proves the loop stopped driving.
        """
        mid = self._running()

        async def decider(ctx):
            return {"action": "continue", "instruction": "speak"}

        m = asyncio.get_event_loop().run_until_complete(
            self._engine(decider, say_ok="no_live_runtime").run_mission(mid))
        self.assertEqual(self.says, ["speak"], "the say WAS attempted")
        self.assertEqual(
            m["state"], "blocked",
            "an untouched mission whose runtime is genuinely gone still "
            "leaves the loop -- now recoverably")
        self.assertEqual(m["block_reason"], "no_live_runtime")


if __name__ == "__main__":
    unittest.main()
