#!/usr/bin/env python3
"""STEP 2.5: STANDING FOUNDER INSTRUCTIONS (founder, 2026-09-16).

THE GAP AFTER STEP 2. Everything the founder said reached the decider once,
through `founder_says`, and was then marked `seen` -- correct for an aside
("how close are we?"), wrong for a constraint ("don't modify the API").
A constraint the founder stated on turn 1 was invisible from turn 2 onward,
so the worker respected it exactly once.

WHAT STEP 2.5 ADDS, and it is one field. `standing_instructions` on the
mission record is the set that CURRENTLY GOVERNS the task, written by Shadow
in Shadow's own words and sent on EVERY later decision -- never consumed,
because standing is the point. `founder_says` is untouched and still answers
"what has the founder actually said", so no history is rewritten when an
instruction is superseded.

THE THREE LAYERS THIS PINS:

  conversation  transient by default; Shadow answers it in the chat.
  instruction   durable; it belongs in the active set.
  decision      Shadow reads the set plus what was just said, and composes
                ONE instruction for the worker in its own words.

WHAT IS NOT ASSERTED HERE. Whether Shadow correctly recognises durable intent
inside a sentence is the model's judgement, so every decider below is
scripted. What is asserted is the machinery around that judgement: that the
set reaches every decision, survives a restart, replaces cleanly, is never
wiped by a decider that said nothing about it, and cannot send a turn.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_standing.py
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

    def running(self, says=None, standing=None, state="running"):
        m = self.store.create("Ship the exporter.", "feature",
                              target_mode="new", target_session="sess-1")
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        m["manifest_delivered"] = True
        m["turns_used"], m["max_turns"] = 2, 9
        if says:
            m["founder_says"] = list(says)
        if standing:
            m["standing_instructions"] = [{"text": t, "at": "2026-09-16T10:00:00Z"}
                                          for t in standing]
        if state != "running":
            m["state"] = state
        self.store.save(m)
        return m["id"]

    def engine(self, decisions):
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

    def active(self, mid):
        return [r["text"] for r in
                (self.store.load(mid).get("standing_instructions") or [])]

    @staticmethod
    def talked(text):
        return {"text": text, "at": "2026-09-16T10:00:00Z", "at_turn": 2,
                "via": "talk", "seen": False}

    @staticmethod
    def typed(text):
        return {"text": text, "at": "2026-09-16T10:00:00Z", "at_turn": 2,
                "seen": False}

    STOP = {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste"}

    @staticmethod
    def go(instruction, standing=None):
        d = {"action": "continue", "instruction": instruction, "reason": "r"}
        if standing is not None:
            d["standing"] = standing
        return d


# ======== 1. AN EXPLICIT INSTRUCTION BECOMES STANDING ====================
class ExplicitBecomesStanding(Base):

    def test_it_is_written_once_and_governs_every_later_turn(self):
        mid = self.running([self.typed("Do not modify the API.")])
        eng = self.engine([
            self.go("Finish the exporter; keep the existing API unchanged.",
                    ["Keep the existing API unchanged."]),
            self.go("Carry on."),          # says nothing about standing
            self.STOP])
        run(eng.run_mission(mid))
        self.assertEqual(self.active(mid), ["Keep the existing API unchanged."])
        # turn 1 saw it as a fresh founder line, turns 2 AND 3 saw it as a
        # standing constraint -- which is the whole point of step 2.5
        self.assertNotIn("standing", self.seen_ctx[0], "nothing governed yet")
        self.assertEqual(self.seen_ctx[1]["standing"],
                         ["Keep the existing API unchanged."])
        self.assertEqual(self.seen_ctx[2]["standing"],
                         ["Keep the existing API unchanged."],
                         "and it is NOT consumed the way an aside is")

    def test_the_founders_raw_words_are_not_what_is_stored(self):
        mid = self.running([self.typed("Do not modify the API.")])
        run(self.engine([self.go("Keep the API as it is.",
                                 ["Keep the existing API unchanged."]),
                         self.STOP]).run_mission(mid))
        self.assertEqual(self.active(mid), ["Keep the existing API unchanged."])
        self.assertNotIn("Do not modify the API.", self.active(mid),
                         "Shadow restates; it does not store the raw line")
        # ...and the raw line is still on the record, unrewritten
        self.assertEqual(
            [s["text"] for s in self.store.load(mid)["founder_says"]],
            ["Do not modify the API."], "history is preserved, not edited")


# ======== 2/3/4. CONVERSATION: TRANSIENT UNLESS SHADOW SAYS OTHERWISE ====
class ConversationIsTransientByDefault(Base):

    def test_a_question_creates_nothing(self):
        mid = self.running([self.talked("Why are you using CSV?")])
        run(self.engine([self.go("Carry on with the exporter."),
                         self.STOP]).run_mission(mid))
        self.assertEqual(self.active(mid), [],
                         "a question is never an instruction")
        self.assertIsNone(
            self.store.load(mid).get("standing_instructions"),
            "and no set is created just because the founder spoke")

    def test_a_durable_preference_in_chat_can_become_standing(self):
        mid = self.running([self.talked(
            "Actually, use JSON instead of CSV from now on.")])
        eng = self.engine([
            self.go("Switch the exporter to JSON.",
                    ["Emit JSON, not CSV."]),
            self.go("Carry on."), self.STOP])
        run(eng.run_mission(mid))
        self.assertEqual(self.active(mid), ["Emit JSON, not CSV."])
        self.assertEqual(self.seen_ctx[1]["standing"], ["Emit JSON, not CSV."])

    def test_a_mixed_message_leaves_only_the_constraint_standing(self):
        mid = self.running([self.talked(
            "How close are we? Also don't modify the API.")])
        eng = self.engine([
            self.go("Two checks left. Keep the existing API unchanged.",
                    ["Keep the existing API unchanged."]),
            self.STOP])
        run(eng.run_mission(mid))
        self.assertEqual(self.active(mid), ["Keep the existing API unchanged."])
        self.assertNotIn("How close are we", self.active(mid)[0],
                         "the question is answered in the chat, not stored")


# ======== 5. SUPERSESSION ================================================
class NewerIntentWins(Base):

    def test_the_set_is_replaced_whole(self):
        mid = self.running(standing=["Use CSV for the export."])
        eng = self.engine([self.go("Switch to JSON.", ["Emit JSON, not CSV."]),
                           self.STOP])
        run(eng.run_mission(mid))
        self.assertEqual(self.active(mid), ["Emit JSON, not CSV."],
                         "only the newer intent governs")

    def test_a_relaxed_constraint_can_be_cleared(self):
        mid = self.running(standing=["Keep the existing API unchanged."])
        run(self.engine([self.go("You may change the API if needed.", []),
                         self.STOP]).run_mission(mid))
        self.assertEqual(self.active(mid), [],
                         "an empty list is a deliberate clear")

    def test_history_is_never_deleted_by_a_supersession(self):
        mid = self.running([self.typed("Use CSV."),
                            self.typed("Actually, use JSON instead.")],
                           standing=["Use CSV for the export."])
        run(self.engine([self.go("Switch to JSON.", ["Emit JSON, not CSV."]),
                         self.STOP]).run_mission(mid))
        self.assertEqual(
            [s["text"] for s in self.store.load(mid)["founder_says"]],
            ["Use CSV.", "Actually, use JSON instead."],
            "both founder messages remain on the record")


# ======== ABSENT MEANS KEEP =============================================
class ASilentDecisionCannotDropTheSet(Base):

    def test_a_decision_without_the_key_keeps_what_governs(self):
        mid = self.running(standing=["Keep the existing API unchanged."])
        run(self.engine([self.go("Carry on."), self.STOP]).run_mission(mid))
        self.assertEqual(self.active(mid), ["Keep the existing API unchanged."],
                         "a decider that said nothing about the set must not "
                         "be able to drop the founder's constraints")

    def test_a_malformed_set_is_ignored_not_obeyed(self):
        self.assertIsNone(mission_engine.validate_standing("not a list"))
        self.assertIsNone(mission_engine.validate_standing(None))
        self.assertEqual(mission_engine.validate_standing([]), [])
        self.assertEqual(
            mission_engine.validate_standing(
                ["  keep the API  ", "", None, "keep the API", 7]),
            ["keep the API"], "blank, duplicate and non-text rows are dropped")
        self.assertEqual(
            len(mission_engine.validate_standing(
                ["r%d" % i for i in range(40)])),
            mission_engine.MAX_STANDING, "and the set is capped")

    def test_the_decision_shape_is_unchanged_when_nothing_is_sent(self):
        """ADDITIVE: every decision that existed before step 2.5 validates to
        exactly what it validated to before."""
        out = mission_engine.validate_decision(
            {"action": "continue", "instruction": "go", "reason": "r"})
        self.assertEqual(out, {"action": "continue", "instruction": "go",
                               "reason": "r"})
        self.assertNotIn("standing", out)

    def test_an_ask_founder_may_still_change_the_set(self):
        """The founder can change what governs the task on a turn Shadow ends
        by asking them something."""
        out = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste", "standing": ["keep x"]})
        self.assertEqual(out["standing"], ["keep x"])


# ======== 6. RESTART / RECOVERY =========================================
class ItSurvivesARestart(Base):

    def test_a_fresh_store_still_sees_the_active_set(self):
        mid = self.running()
        run(self.engine([self.go("Keep the API as it is.",
                                 ["Keep the existing API unchanged."]),
                         self.STOP]).run_mission(mid))
        fresh = MissionStore()          # the restart case
        eng = mission_engine.MissionEngine(fresh, None, None, None)
        ctx = eng._decision_context(fresh.load(mid), "")
        self.assertEqual(ctx["standing"], ["Keep the existing API unchanged."])
        self.assertIn("- Keep the existing API unchanged.",
                      shadow_runner.render_decide_prompt(ctx),
                      "and a restarted process puts it back in the prompt")

    def test_it_still_influences_the_next_worker_instruction(self):
        mid = self.running(standing=["Keep the existing API unchanged."])
        fresh = MissionStore()
        self.store = fresh
        eng = self.engine([self.go("Finish the exporter without touching the "
                                   "API."), self.STOP])
        run(eng.run_mission(mid))
        self.assertEqual(self.seen_ctx[0]["standing"],
                         ["Keep the existing API unchanged."],
                         "the decision after a restart is made with it")
        self.assertEqual(self.said,
                         ["Finish the exporter without touching the API."])


# ======== 7/8. NO DUPLICATION, NO EXTRA TURNS ===========================
class ItCannotDriveTheWorker(Base):

    def test_the_set_is_not_re_sent_to_the_worker_every_turn(self):
        mid = self.running(standing=["Keep the existing API unchanged."])
        eng = self.engine([self.go("Step one."), self.go("Step two."),
                           self.STOP])
        run(eng.run_mission(mid))
        self.assertEqual(self.said, ["Step one.", "Step two."],
                         "only what Shadow composed reaches the worker")
        for sent in self.said:
            self.assertNotIn("Keep the existing API unchanged.", sent,
                             "the set is a constraint on the instruction, "
                             "not a preamble bolted onto it")

    def test_writing_the_set_spends_no_turn_and_sends_nothing(self):
        mid = self.running()
        eng = self.engine([{"action": "ask_founder", "reason": "does the copy read well to you", "ask_kind": "taste",
                            "standing": ["Keep the existing API unchanged."]}])
        before = self.store.load(mid)["turns_used"]
        run(eng.run_mission(mid))
        self.assertEqual(self.active(mid), ["Keep the existing API unchanged."],
                         "the set was written")
        self.assertEqual(self.said, [], "and nothing was sent")
        self.assertEqual(self.store.load(mid)["turns_used"], before,
                         "and no turn was spent")

    def test_an_unchanged_set_is_not_rewritten(self):
        """Re-sending the same set is a no-op: no write, no ledger row, and
        the stamps on the existing rows do not churn. Asserted on the writer
        itself, because a turn saves the record for several other reasons."""
        mid = self.running(standing=["Keep the existing API unchanged."])
        m = self.store.load(mid)
        was = list(m["standing_instructions"])
        eng = self.engine([])
        self.assertFalse(
            eng._adopt_standing(m, {"standing": ["Keep the existing API "
                                                 "unchanged."]}),
            "an identical set must not be written again")
        self.assertEqual(m["standing_instructions"], was,
                         "and the stamps do not churn")
        self.assertTrue(
            eng._adopt_standing(m, {"standing": ["Emit JSON, not CSV."]}),
            "a changed set IS written")


# ======== 9. WHOSE WORDS ================================================
class ShadowsOwnReplyIsNeverAnInstruction(Base):

    def test_only_a_decision_can_write_the_set(self):
        """The conversational route (TaskChat.talk) has no path here: the set
        is written by _adopt_standing, from a validated decision, and by
        nothing else."""
        import app as app_module
        src = Path(app_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("standing_instructions", src,
                         "no route may write the set directly")
        eng_src = Path(mission_engine.__file__).read_text(encoding="utf-8")
        self.assertEqual(eng_src.count('m["standing_instructions"] ='), 1,
                         "exactly one writer")

    def test_a_shadow_reply_does_not_reach_the_set(self):
        mid = self.running([self.talked("why CSV?")])
        run(self.engine([self.go("Carry on."), self.STOP]).run_mission(mid))
        self.assertEqual(self.active(mid), [])


# ======== 11. TERMINAL STATES ===========================================
class TerminalIsUnchanged(Base):

    def test_a_terminal_task_is_never_driven_or_written(self):
        for state in ("done", "failed", "stopped"):
            mid = self.running(state=state)
            eng = self.engine([self.go("Go.", ["Keep the API unchanged."])])
            out = run(eng.run_mission(mid))
            self.assertEqual(out["state"], state, "%s left alone" % state)
            self.assertEqual(self.said, [], "%s sends nothing" % state)
            self.assertEqual(self.active(mid), [],
                             "%s writes no standing set" % state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
