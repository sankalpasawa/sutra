#!/usr/bin/env python3
"""A resumed loop starts knowing what the worker already said.

THE MEASURED FAILURE (founder dogfood, 2026-09-15, mission m-80893d3f3d18).
run_mission opened with `last_response = None`, and it is re-entered on every
resume. The delegate's transcript held 188 assistant messages, but the
decider's FIRST turn after each re-adoption was composed with an empty "what
the target said back" -- so Shadow spent the turn saying "No output from you
yet, keep going". Sixteen restart/re-adopt cycles later the budget was gone
and the mission died `failed` on max turns with the work well advanced.

All four empty-response nudges in that mission landed within fifteen seconds
of a re-adoption. None landed anywhere else.

WHAT THIS FIX IS. One seed, from the reader the loop ALREADY consults at the
end of every iteration. worker_response behind it reads the durable
transcript (read_session), not the in-memory stream -- which is why it
survives the restart that cleared everything else.

WHAT IT IS NOT. Not a change to the per-turn assignment, not a change to
worker_response, DECISION_TAIL, DECIDE_PROSE_TAIL, evidence_text,
verification, interventions, confirms_check, adoption, or the
concurrent-runner behaviour. All of those are asserted untouched below.

Run: .venv/bin/python -m unittest test_shadow_resume_seed -v
"""
import asyncio
import os
import tempfile
import unittest

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-seed-")

import mission_engine  # noqa: E402
from mission_engine import MissionEngine, MissionStore  # noqa: E402

LATEST = "## CHANGE\n\nthe latest whole worker message"
OLDER = "## CHANGE\n\nan earlier, superseded draft"


class Base(unittest.TestCase):
    def setUp(self):
        self.store = MissionStore()
        self.seen = []          # every last_response the decider was handed
        self.says = []

    def _mission(self, turns=3):
        m = self.store.create("ship it", "fix", target_mode="new",
                              target_session="sess-1", done_when=[])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        self.store.transition(mid, "running", "admitted")
        m = self.store.load(mid)
        m["turns_used"] = turns          # past turn 0, so the decider is asked
        self.store.save(m)
        return mid

    def _engine(self, response_reader, replies=None):
        replies = list(replies or [{"action": "ask_founder", "reason": "done"}])

        async def decider(ctx):
            self.seen.append(ctx.get("last_response"))
            return replies.pop(0) if replies else {"action": "ask_founder",
                                                  "reason": "out of replies"}

        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        return MissionEngine(self.store, sayer, waiter,
                             lambda m: "EVIDENCE BLOB",
                             decider=decider,
                             response_reader=response_reader)

    def _run(self, eng, mid):
        return asyncio.get_event_loop().run_until_complete(eng.run_mission(mid))


class TheSeed(Base):

    def test_1_existing_worker_output_is_seeded_on_the_first_turn(self):
        mid = self._mission()
        self._run(self._engine(lambda m: LATEST), mid)
        self.assertEqual(self.seen[0], LATEST,
                         "the first decider turn must see what the worker "
                         "already said, not None")

    def test_2_a_RESUMED_loop_does_not_start_empty(self):
        """The reported bug: re-entering run_mission after a restart."""
        mid = self._mission()
        eng = self._engine(lambda m: LATEST)
        self._run(eng, mid)                      # first process, ends blocked
        # the real re-entry: a blocked mission put back to running is exactly
        # what a restart's re-adoption (and a founder answer) does. Either way
        # run_mission is ENTERED AGAIN, which is the condition under test.
        self.store.transition(mid, "running", "re-adopted after restart")
        self.seen = []
        self._run(eng, mid)                      # a second, resumed process
        self.assertEqual(self.seen[0], LATEST,
                         "a resume must not hand the decider an empty "
                         "response while the transcript has output")
        self.assertTrue(self.seen[0])

    def test_3_an_empty_transcript_falls_back_to_None(self):
        mid = self._mission()
        self._run(self._engine(lambda m: ""), mid)
        # the decider is handed _decision_context's rendering, which turns an
        # unseeded None into "" -- so an empty seed must leave it EMPTY
        self.assertEqual(self.seen[0], "",
                         "no worker output yet stays empty, as before")

    def test_4_a_reader_that_raises_is_swallowed(self):
        mid = self._mission()

        def boom(m):
            raise RuntimeError("transcript unreadable")

        self._run(self._engine(boom), mid)
        self.assertEqual(self.seen[0], "", "a failed seed leaves the old value")

    def test_4b_a_reader_returning_None_is_safe(self):
        mid = self._mission()
        self._run(self._engine(lambda m: None), mid)
        self.assertEqual(self.seen[0], "")

    def test_5_later_turns_are_unchanged(self):
        """Turn 2+ still reads its own iteration's value, not the seed."""
        calls = {"n": 0}

        def reader(m):
            calls["n"] += 1
            return LATEST if calls["n"] == 1 else "TURN %d TEXT" % calls["n"]

        mid = self._mission()
        eng = self._engine(reader, replies=[
            {"action": "continue", "instruction": "go on"},
            {"action": "ask_founder", "reason": "enough"}])
        self._run(eng, mid)
        self.assertEqual(self.seen[0], LATEST, "turn 1 got the seed")
        self.assertEqual(self.seen[1], "TURN 2 TEXT",
                         "turn 2 got its OWN reading, not the seed")

    def test_6_the_LATEST_whole_message_is_what_is_seeded(self):
        """Whatever response_reader returns is passed through verbatim --
        no slicing, no join, no earlier drafts."""
        mid = self._mission()
        self._run(self._engine(lambda m: LATEST), mid)
        self.assertEqual(self.seen[0], LATEST)
        self.assertNotIn(OLDER, self.seen[0] or "")
        self.assertTrue((self.seen[0] or "").startswith("## CHANGE"),
                        "the head survives -- that is the whole point")

    def test_7_no_response_reader_is_byte_identical(self):
        """Every existing caller and every existing test."""
        mid = self._mission()
        self._run(self._engine(None), mid)
        self.assertEqual(self.seen[0], "",
                         "without a reader the historical empty value is kept")

    def test_8_the_seed_reads_the_mission_from_the_store(self):
        got = {}

        def reader(m):
            got["id"] = m.get("id")
            got["state"] = m.get("state")
            return LATEST

        mid = self._mission()
        self._run(self._engine(reader), mid)
        self.assertEqual(got["id"], mid, "the seed passes the real mission")
        self.assertEqual(got["state"], "running")


class NothingElseMoved(unittest.TestCase):
    """The blast radius, asserted."""

    def test_the_windows_are_unchanged(self):
        self.assertEqual(mission_engine.DECISION_TAIL, 2000)
        self.assertEqual(mission_engine.DECISION_INSTRUCTION_MAX, 2000)

    def test_the_per_turn_assignment_still_exists(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "mission_engine.py"), encoding="utf-8").read()
        self.assertIn("last_response = transcript", src,
                      "the historical per-turn value is untouched")
        self.assertIn("shaped = self.response_reader(m)", src,
                      "the per-turn reading is untouched")

    def test_evaluate_still_receives_the_full_evidence(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "mission_engine.py"), encoding="utf-8").read()
        # PREFIX, NOT THE WHOLE CALL. What this guards is the FIRST argument
        # -- `transcript`, the full evidence blob -- never `last_response`,
        # the decider's shaped view. Pinning the closing paren made it a
        # guard on the argument COUNT as well, and it broke the moment
        # `probe_root` was threaded in beside `verifier` without touching the
        # evidence at all.
        self.assertIn("evaluate_done_when(m, transcript, self.verifier", src,
                      "verification still reads the evidence blob, not the "
                      "decider's shaped view")
        self.assertNotIn("evaluate_done_when(m, last_response", src,
                         "the shaped view is the DECIDER's input only")

    def test_the_state_machine_did_not_move(self):
        self.assertEqual(len(mission_engine.STATES), 9)
        self.assertEqual(mission_engine.TERMINAL, ("done", "failed", "stopped"))
        self.assertEqual(mission_engine.DECISION_ACTIONS,
                         ("continue", "ask_founder"))


if __name__ == "__main__":
    unittest.main()
