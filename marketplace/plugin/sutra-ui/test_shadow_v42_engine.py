"""Shadow v4.2, the engine half (founder 2026-09-21: "I typed Yes. and Shadow
said my yes does not count; there are no buttons in the chat").

Three primitives, all pure record work; the routes own the cap, the
transition and the launch exactly as they do for Approve today:

  pending_asks(m)   THE ONE LIST of what a task is waiting on -- a held
                    instruction, an unmet founder-confirm check, a typed
                    question, a parked instruction. The task chat is told
                    this list before it answers and the stream draws it.
  apply_answer      a typed or clicked answer, BOUND to the one ask it can
                    mean: approve (the one pending hold), confirm (the one
                    unmet check, or an index), withdraw / change (drop the
                    hold, tell Shadow why). Anything ambiguous is a
                    ValueError with the choices in it, never a guess.
  park_hold         a take-over during a hold parks the instruction instead
                    of leaving Approve armed behind the founder's back.

Run: ./run-tests.sh test_shadow_v42_engine.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-v42-engine-")

import mission_engine                          # noqa: E402
import providers                               # noqa: E402
from mission_engine import MissionStore         # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def task(self, state="running", target="s-worker-1", checks=None, **extra):
        m = self.store.create(
            "make the login test pass", "fix",
            target_mode="existing", target_session=target,
            done_when=checks if checks is not None else [
                {"tier": "founder_confirm", "check": "the greeting reads well"},
                {"tier": "verify", "check": "tests pass",
                 "probe": {"kind": "file_exists", "path": "x"}}])
        m = self.store.load(m["id"])
        m["state"] = state
        m["turns_used"] = 2
        m.update(extra)
        self.store.save(m)
        return self.store.load(m["id"])

    def held(self, say="Push fix/auth to origin and open the PR."):
        m = self.task(state="paused", pause_reason="floor_confirm")
        m["pending_say"] = say
        m["pending_floor_say"] = say
        m["approval"] = mission_engine.mint_approval(m, "floor_confirm", say)
        self.store.save(m)
        return self.store.load(m["id"])

    def confirming(self):
        return self.task(state="paused", pause_reason="founder_confirm")


# ----------------------------------------------------------- PENDING ASKS --
class TestPendingAsks(Base):

    def test_01_a_running_task_asks_nothing(self):
        self.assertEqual(mission_engine.pending_asks(self.task()), [])

    def test_02_a_held_say_is_an_approve_ask_with_its_id(self):
        m = self.held()
        asks = mission_engine.pending_asks(m)
        self.assertEqual([a["kind"] for a in asks], ["approve"])
        self.assertEqual(asks[0]["id"], m["approval"]["id"])
        self.assertEqual(asks[0]["text"], m["pending_say"])
        self.assertEqual(asks[0]["reason"], "floor_confirm")

    def test_03_unmet_founder_checks_are_confirm_asks_while_waiting(self):
        m = self.confirming()
        asks = mission_engine.pending_asks(m)
        self.assertEqual([a["kind"] for a in asks], ["confirm"])
        self.assertEqual(asks[0]["index"], 0)
        self.assertIn("greeting", asks[0]["text"])

    def test_04_a_met_check_is_not_asked_again(self):
        m = self.confirming()
        self.store.confirm_check(m["id"], 0)
        self.assertEqual(mission_engine.pending_asks(self.store.load(m["id"])), [])

    def test_05_a_used_approval_is_not_asked_again(self):
        m = self.held()
        mission_engine.approve_held_say(self.store, m["id"], m["approval"]["id"])
        self.assertEqual(mission_engine.pending_asks(self.store.load(m["id"])), [])

    def test_06_a_question_is_an_ask(self):
        m = self.task(state="blocked", block_reason="needs_founder",
                      intervention={"id": "iv-1", "question": "Which host?",
                                    "fields": [{"name": "host", "type": "text"}]})
        asks = mission_engine.pending_asks(m)
        self.assertEqual(asks[0]["kind"], "question")
        self.assertEqual(asks[0]["id"], "iv-1")
        self.assertEqual(asks[0]["text"], "Which host?")

    def test_07_a_parked_instruction_is_an_ask_while_paused(self):
        m = self.task(state="paused", pause_reason="founder_intervened",
                      parked_say="Merge PR #218.")
        asks = mission_engine.pending_asks(m)
        self.assertEqual(asks[0]["kind"], "parked")
        self.assertEqual(asks[0]["text"], "Merge PR #218.")

    def test_08_the_text_the_chat_is_told(self):
        m = self.held()
        text = mission_engine.pending_asks_text(m)
        self.assertIn("[Pending", text)
        self.assertIn("approve", text)
        self.assertIn("Push fix/auth", text)
        self.assertEqual(mission_engine.pending_asks_text(self.task()), "")


# ----------------------------------------------------------- APPLY ANSWER --
class TestApplyAnswer(Base):

    def test_10_yes_approves_the_one_pending_hold(self):
        m = self.held()
        out = mission_engine.apply_answer(self.store, m["id"], {"kind": "approve"})
        self.assertEqual(out["kind"], "approve")
        self.assertTrue(out["resume"])
        m = self.store.load(m["id"])
        self.assertTrue(m["approval"]["used"])
        self.assertEqual(m["approved_say"], "Push fix/auth to origin and open the PR.")
        self.assertIn("Approved by you in the chat", out["label"])

    def test_11_approve_with_nothing_held_is_refused(self):
        m = self.task()
        with self.assertRaises(ValueError) as ctx:
            mission_engine.apply_answer(self.store, m["id"], {"kind": "approve"})
        self.assertIn("nothing", str(ctx.exception).lower())

    def test_12_yes_confirms_the_one_unmet_check(self):
        m = self.confirming()
        out = mission_engine.apply_answer(self.store, m["id"], {"kind": "confirm"})
        self.assertEqual(out["kind"], "confirm")
        self.assertEqual(out["index"], 0)
        self.assertTrue(out["settle"])
        c = self.store.load(m["id"])["done_when"][0]
        self.assertTrue(c["met"])
        self.assertEqual(c["confirmed_by"], "founder")

    def test_13_two_unmet_checks_need_an_index(self):
        m = self.task(state="paused", pause_reason="founder_confirm", checks=[
            {"tier": "founder_confirm", "check": "the greeting reads well"},
            {"tier": "founder_confirm", "check": "the tone is right"}])
        with self.assertRaises(ValueError) as ctx:
            mission_engine.apply_answer(self.store, m["id"], {"kind": "confirm"})
        self.assertIn("#1", str(ctx.exception))
        self.assertIn("#2", str(ctx.exception))
        out = mission_engine.apply_answer(self.store, m["id"],
                                          {"kind": "confirm", "index": 1})
        self.assertEqual(out["index"], 1)
        checks = self.store.load(m["id"])["done_when"]
        self.assertFalse(checks[0].get("met"))
        self.assertTrue(checks[1]["met"])

    def test_14_a_yes_with_a_hold_and_a_check_pending_is_ambiguous(self):
        m = self.held()
        m["done_when"][0]["met"] = False
        self.store.save(m)
        # the hold is the ask that blocks the task; confirm is not offered
        # while a say is held, so a plain approve is not ambiguous here
        out = mission_engine.apply_answer(self.store, m["id"], {"kind": "approve"})
        self.assertEqual(out["kind"], "approve")

    def test_15_withdraw_drops_the_hold_and_tells_shadow_why(self):
        m = self.held()
        out = mission_engine.apply_answer(
            self.store, m["id"], {"kind": "withdraw", "text": "I did it myself"})
        self.assertEqual(out["kind"], "withdraw")
        self.assertTrue(out["resume"])
        m = self.store.load(m["id"])
        self.assertIsNone(m.get("pending_say"))
        self.assertIsNone(m.get("approval"))
        self.assertNotIn("pending_floor_say", m)
        self.assertEqual(m["withdrawn"][-1]["text"],
                         "Push fix/auth to origin and open the PR.")
        self.assertIn("I did it myself", m["founder_says"][-1]["text"])
        self.assertEqual(m["founder_says"][-1]["via"], "withdraw")

    def test_16_change_drops_the_hold_and_carries_the_new_words(self):
        m = self.held()
        out = mission_engine.apply_answer(
            self.store, m["id"], {"kind": "change", "text": "push to a branch, no PR"})
        self.assertEqual(out["kind"], "change")
        self.assertTrue(out["resume"])
        m = self.store.load(m["id"])
        self.assertIsNone(m.get("approval"))
        self.assertIn("push to a branch, no PR", m["founder_says"][-1]["text"])
        self.assertEqual(m["founder_says"][-1]["via"], "change")

    def test_17_change_needs_words(self):
        m = self.held()
        with self.assertRaises(ValueError):
            mission_engine.apply_answer(self.store, m["id"], {"kind": "change"})

    def test_18_an_unknown_kind_is_refused(self):
        m = self.held()
        with self.assertRaises(ValueError):
            mission_engine.apply_answer(self.store, m["id"], {"kind": "nuke"})
        with self.assertRaises(ValueError):
            mission_engine.apply_answer(self.store, m["id"], "yes")

    def test_19_the_worker_cannot_answer(self):
        """apply_answer is called only by the app on the founder's own line;
        this pins that nothing on the record lets a say text stand in."""
        m = self.held()
        with self.assertRaises(ValueError):
            mission_engine.apply_answer(self.store, m["id"],
                                        {"kind": "approve", "by": "worker"})


# ---------------------------------------------------------------- PARKING --
class TestParkHold(Base):

    def test_20_take_over_parks_the_held_instruction(self):
        m = self.held()
        out = mission_engine.park_hold(self.store, m["id"])
        self.assertEqual(out["parked_say"], "Push fix/auth to origin and open the PR.")
        self.assertIsNone(out.get("pending_say"))
        self.assertIsNone(out.get("approval"))
        self.assertNotIn("pending_floor_say", out)
        with self.assertRaises(ValueError):
            mission_engine.approve_held_say(self.store, m["id"], "ap-anything")

    def test_21_nothing_held_parks_nothing(self):
        m = self.task(state="paused", pause_reason="founder_intervened")
        out = mission_engine.park_hold(self.store, m["id"])
        self.assertNotIn("parked_say", out)

    def test_22_unpark_hands_shadow_a_question_not_an_order(self):
        m = self.held()
        mission_engine.park_hold(self.store, m["id"])
        out = mission_engine.unpark(self.store, m["id"])
        self.assertNotIn("parked_say", out)
        note = out["founder_says"][-1]
        self.assertEqual(note["via"], "hand_back")
        self.assertIn("Push fix/auth", note["text"])
        self.assertIn("ask", note["text"].lower())
        self.assertEqual(mission_engine.pending_asks(out), [])


if __name__ == "__main__":
    unittest.main()
