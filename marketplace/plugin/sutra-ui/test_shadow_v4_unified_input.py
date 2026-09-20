#!/usr/bin/env python3
"""STEP 2: ONE DECISION LAYER OVER BOTH FOUNDER DOORS (founder, 2026-09-16).

THE SPLIT THIS CLOSES. The founder had two ways to reach Shadow and Shadow
had two memories of them:

  Give instruction to Shadow -> founder_says on the mission record, handed to
                                the decider by _decision_context, consumed
                                once via the `seen` flag.
  Talk to Shadow             -> the task chat's own transcript. The LIVE chat
                                could see it (decide() and talk() are two
                                prompts on one session) but the one-shot
                                fallback decider could not, and nothing
                                marked it consumed -- so a remark could steer
                                every later turn for the rest of the mission.

THE FIX IS THE SAME LIST. A post-Start talked line is appended to
`founder_says` with `via: "talk"`. No new store, no queue, no cursor: the
record is already durable and atomic, `seen` is already the consumption
cursor, and append order is already the chronology.

WHAT THIS FILE PINS, and it is the architectural rule rather than the model's
judgement: EVERYTHING THE FOUNDER SAID REACHES THE DECIDER, AND ONLY WHAT THE
DECIDER COMPOSES REACHES THE WORKER. A conversational line is never forwarded
to the worker by arriving; it is input to a decision, and mission_engine's
_instruction -> validate_decision -> sayer path is still the only way a turn
is sent. Whether a particular remark is operationally relevant is Shadow's
call, so the deciders here are scripted: what is asserted is the plumbing
around that call, never the call itself.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_unified_input.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import shadow_runner
from mission_engine import MissionStore


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    def setUp(self):
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def running(self, says=None):
        m = self.store.create("Ship the exporter.", "feature",
                              target_mode="new", target_session="sess-1")
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        m["manifest_delivered"] = True
        m["turns_used"], m["max_turns"] = 2, 9
        if says:
            m["founder_says"] = list(says)
        self.store.save(m)
        return m["id"]

    def engine(self, decisions):
        """A loop whose decider answers from a list. `said` records every
        instruction that actually LEFT the engine; `seen_ctx` records what
        the decider was given."""
        self.said, self.seen_ctx = [], []

        async def sayer(m, text):
            self.said.append(text)
            return True

        async def waiter(m):
            return True

        seq = list(decisions)

        async def decider(ctx):
            self.seen_ctx.append(ctx)
            return seq.pop(0) if seq else None

        return mission_engine.MissionEngine(
            self.store, sayer, waiter, lambda m: "", decider=decider)

    @staticmethod
    def talked(text, seen=False):
        return {"text": text, "at": "2026-09-16T10:00:00Z", "at_turn": 2,
                "via": "talk", "seen": seen}

    @staticmethod
    def typed(text, seen=False):
        return {"text": text, "at": "2026-09-16T10:00:00Z", "at_turn": 2,
                "seen": seen}


# ===================== 1. CONVERSATIONAL ONLY ===========================
class ConversationIsNotWork(Base):
    """"What are you doing?" -- Shadow answered it in the chat. The next
    decision must be free to send the worker nothing new because of it."""

    def test_the_line_reaches_the_decider_tagged_as_conversation(self):
        mid = self.running([self.talked("What are you doing?")])
        eng = self.engine([{"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        ctx = self.seen_ctx[0]
        self.assertEqual([s["text"] for s in ctx["founder_says"]],
                         ["What are you doing?"])
        self.assertIn("- [conversation] What are you doing?",
                      shadow_runner.render_decide_prompt(ctx))

    def test_an_idle_remark_can_end_the_turn_without_a_say(self):
        """The decider is free to decide that nothing changed. Nothing in the
        plumbing forces a worker turn merely because the founder spoke."""
        mid = self.running([self.talked("What are you doing?")])
        # D-SH-1: an escalation must BE one of the three admissible kinds,
        # so the fixture asks a real taste question. What this test pins is
        # unchanged and is the assertion below -- an ask_founder turn sends
        # the WORKER nothing, whatever the founder is being asked.
        eng = self.engine([{"action": "ask_founder", "ask_kind": "taste",
                            "reason": "does the copy read well to you"}])
        run(eng.run_mission(mid))
        self.assertEqual(self.said, [],
                         "a conversation must not send a worker turn on its "
                         "own")
        self.assertEqual(self.store.load(mid)["turns_used"], 2,
                         "and must not spend one")


# ===================== 2/3. OPERATIONAL CONTENT =========================
class OnlyWhatShadowComposesReachesTheWorker(Base):

    def test_the_worker_receives_shadows_words_not_the_founders(self):
        mid = self.running([self.talked(
            "Why are you using CSV? I think JSON would be better.")])
        eng = self.engine([
            {"action": "continue",
             "instruction": "Founder prefers JSON over CSV. Reassess the "
                            "export format before proceeding.",
             "reason": "founder supplied a format preference"},
            {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        self.assertEqual(self.said,
                         ["Founder prefers JSON over CSV. Reassess the export "
                          "format before proceeding."])
        for sent in self.said:
            self.assertNotIn("Why are you using CSV", sent,
                             "the founder's raw wording must not be forwarded")

    def test_a_mixed_message_is_one_row_and_shadow_splits_it(self):
        """"How close are we? Also don't change the API." The founder is
        never asked to classify; the whole sentence reaches the decider and
        Shadow carries across only the part that changes the work."""
        mid = self.running([self.talked(
            "How close are we? Also don't change the API.")])
        eng = self.engine([
            {"action": "continue",
             "instruction": "Constraint from the founder: do not modify the "
                            "API while finishing this.",
             "reason": "operational constraint inside a question"},
            {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        prompt = shadow_runner.render_decide_prompt(self.seen_ctx[0])
        self.assertIn("How close are we? Also don't change the API.", prompt)
        self.assertEqual(
            self.said,
            ["Constraint from the founder: do not modify the API while "
             "finishing this."])
        self.assertNotIn("How close are we", self.said[0])


# ===================== 4/5. BOTH CHANNELS ===============================
class BothDoorsOneDecision(Base):

    def test_the_explicit_path_is_unchanged_and_still_reaches_the_decider(self):
        mid = self.running([self.typed("Do not modify the API.")])
        eng = self.engine([{"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        ctx = self.seen_ctx[0]
        self.assertEqual([s["text"] for s in ctx["founder_says"]],
                         ["Do not modify the API."])
        self.assertIn("- [instruction] Do not modify the API.",
                      shadow_runner.render_decide_prompt(ctx),
                      "an untagged row is a typed instruction by "
                      "construction -- every row written before step 2")

    def test_both_channels_arrive_in_order_and_neither_is_duplicated(self):
        mid = self.running([self.talked("JSON would be better"),
                            self.typed("Do not modify the API.")])
        eng = self.engine([{"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        prompt = shadow_runner.render_decide_prompt(self.seen_ctx[0])
        self.assertIn("- [conversation] JSON would be better\n"
                      "- [instruction] Do not modify the API.", prompt,
                      "one list, in the order the founder said them")
        rows = prompt.count("JSON would be better")
        self.assertEqual(rows, 1, "and each appears exactly once")


# ===================== 6. NO REPEATED STEERING ==========================
class ConsumedOnce(Base):

    def test_a_read_line_does_not_steer_the_next_turn(self):
        mid = self.running([self.talked("JSON would be better")])
        eng = self.engine([
            {"action": "continue", "instruction": "Switch to JSON.",
             "reason": "founder preference"},
            {"action": "continue", "instruction": "Carry on.",
             "reason": "nothing new"},
            {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        self.assertIn("founder_says", self.seen_ctx[0],
                      "the first decision sees it")
        self.assertNotIn("founder_says", self.seen_ctx[1],
                         "the second must not -- a consumed line is standing "
                         "context, not news")
        self.assertEqual(self.said, ["Switch to JSON.", "Carry on."])

    def test_the_cursor_is_on_the_record_so_a_restart_keeps_it(self):
        mid = self.running([self.talked("JSON would be better")])
        eng = self.engine([{"action": "continue", "instruction": "Switch.",
                            "reason": "r"},
                           {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        self.assertTrue(self.store.load(mid)["founder_says"][0]["seen"],
                        "consumption is persisted, not held in memory")
        # a FRESH store object is the restart case
        fresh = MissionStore()
        eng2 = mission_engine.MissionEngine(fresh, None, None, None)
        self.assertNotIn("founder_says",
                         eng2._decision_context(fresh.load(mid), ""),
                         "and a restarted process must not re-steer on it")

    def test_an_unread_line_survives_a_decider_that_died(self):
        """Marking happens AFTER the decider returns, so a turn that dies
        leaves the line unseen and it goes again -- the safe direction."""
        mid = self.running([self.talked("JSON would be better")])

        async def sayer(m, text):
            return True

        async def waiter(m):
            return True

        async def boom(ctx):
            raise RuntimeError("the chat died")

        eng = mission_engine.MissionEngine(
            self.store, sayer, waiter, lambda m: "", decider=boom)
        run(eng.run_mission(mid))
        says = self.store.load(mid)["founder_says"]
        self.assertFalse(says[0]["seen"],
                         "an input the decider never read is still news")


# ============ 9. WHOSE WORDS ARE THESE ==================================
class OnlyTheFounderIsInThisList(Base):

    def test_shadows_own_instruction_is_not_founder_input(self):
        mid = self.running()
        eng = self.engine([{"action": "continue",
                            "instruction": "Switch to JSON.", "reason": "r"},
                           {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])
        run(eng.run_mission(mid))
        m = self.store.load(mid)
        self.assertIsNone(m.get("founder_says"),
                          "nothing Shadow said becomes something it was told")
        self.assertEqual(m["last_instruction"], "Switch to JSON.",
                         "Shadow's own word to the worker has its own field")

    def test_the_worker_output_is_not_founder_input(self):
        """last_response is its own labelled block, and stays one."""
        mid = self.running([self.talked("JSON would be better")])
        eng = self.engine([{"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}])

        def reader(m):
            return "the worker said: use CSV"

        eng.reader = reader
        run(eng.run_mission(mid))
        ctx = self.seen_ctx[0]
        self.assertEqual([s["text"] for s in ctx["founder_says"]],
                         ["JSON would be better"])
        self.assertNotIn("JSON would be better", ctx["last_response"],
                         "and the two blocks never merge")


# ============ 10. TERMINAL STATES ARE UNCHANGED =========================
class TerminalIsUnchanged(Base):

    def test_a_terminal_mission_is_never_driven_by_an_aside(self):
        for state in ("done", "failed", "stopped"):
            mid = self.running([self.talked("JSON would be better")])
            m = self.store.load(mid)
            m["state"] = state
            self.store.save(m)
            eng = self.engine([{"action": "continue",
                                "instruction": "Switch.", "reason": "r"}])
            out = run(eng.run_mission(mid))
            self.assertEqual(out["state"], state,
                             "%s must be left alone" % state)
            self.assertEqual(self.said, [],
                             "%s must send nothing" % state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
