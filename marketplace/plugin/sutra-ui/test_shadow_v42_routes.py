"""Shadow v4.2 over HTTP (founder 2026-09-21: "I typed Yes. and Shadow said
my yes does not count; there are no buttons in the chat; remove Retry").

  J10  A TYPED YES CLOSES THE CHECK. The task waits on one founder-confirm
       check; the founder types "Yes."; the task chat (told the pending
       asks) answers with an `answer` fence; the app confirms the check and
       settles the task. The same for a held instruction: yes approves it,
       "change it to X" and "I did it" withdraw it and Shadow is told why.
  J11  THE CHAT IS TOLD. Every talk on a task with a pending ask carries the
       [Pending asks] block; a task with nothing pending carries nothing.
  J12  TAKE OVER PARKS. A take-over during a hold parks the instruction;
       Approve is gone; Resume hands Shadow a question, not an order.
  Plus the `answer` action for the buttons on the ask rows.

Run: ./run-tests.sh test_shadow_v42_routes.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-v42-routes-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_protocol                         # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore         # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
MIS = "/api/shadow/missions"


def fence(obj):
    return "```answer\n%s\n```" % json.dumps(obj)


class FakeChat:
    def __init__(self):
        self.replies = []
        self.heard = []
        self.alive = True

    async def talk(self, message):
        self.heard.append(message)
        raw = self.replies.pop(0) if self.replies else "Noted."
        return shadow_protocol.parse_reply(raw)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "providers-settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self.chat = FakeChat()
        self._real_ensure = app_module._ensure_task_chat

        async def _ensure(mission):
            return self.chat
        app_module._ensure_task_chat = _ensure
        self.launched = []
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)
        self.settled = []
        self._real_settle = shadow_runner.settle_confirmation
        shadow_runner.settle_confirmation = \
            lambda mid, verifier=None: self.settled.append(mid) or None

    def tearDown(self):
        shadow_runner.settle_confirmation = self._real_settle
        shadow_runner._launch = self._real_launch
        app_module._ensure_task_chat = self._real_ensure
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def task(self, state="running", target="s-worker", checks=None, **extra):
        m = self.store.create(
            "make the greeting right", "fix",
            target_mode="existing", target_session=target,
            done_when=checks if checks is not None else [
                {"tier": "founder_confirm",
                 "check": "the greeting states what it can help with"}])
        m = self.store.load(m["id"])
        m["state"], m["turns_used"] = state, 2
        m.update(extra)
        self.store.save(m)
        return m["id"]

    def held(self, say="Push fix/auth to origin and open the PR."):
        mid = self.task(state="paused", pause_reason="floor_confirm")
        m = self.store.load(mid)
        m["pending_say"] = say
        m["pending_floor_say"] = say
        m["approval"] = mission_engine.mint_approval(m, "floor_confirm", say)
        self.store.save(m)
        return mid

    def confirming(self):
        return self.task(state="paused", pause_reason="founder_confirm")

    def talk(self, mid, message, reply="Noted."):
        self.chat.replies = [reply]
        return self.client.post("/api/shadow/tasks/%s/chat" % mid,
                                json={"message": message}, headers=HDR)

    def act(self, mid, action, **body):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json={"action": action, **body}, headers=HDR)


# -------------------------------------------------------------------- J11 --
class TestJ11TheChatIsTold(Base):

    def test_01_a_pending_check_is_told_before_the_founders_line(self):
        mid = self.confirming()
        self.talk(mid, "Yes.")
        heard = self.chat.heard[-1]
        self.assertTrue(heard.startswith("[Pending asks on this task"))
        self.assertIn("confirm #1: the greeting states", heard)
        self.assertTrue(heard.endswith("[The founder says:] Yes."))

    def test_02_a_held_instruction_is_told(self):
        mid = self.held()
        self.talk(mid, "go ahead")
        self.assertIn("approve: I am holding this instruction", self.chat.heard[-1])
        self.assertIn("Push fix/auth", self.chat.heard[-1])

    def test_03_nothing_pending_means_the_line_alone(self):
        mid = self.task()
        self.talk(mid, "how is it going?")
        self.assertEqual(self.chat.heard[-1], "how is it going?")


# -------------------------------------------------------------------- J10 --
class TestJ10ATypedAnswerCounts(Base):

    def test_10_yes_confirms_the_check_and_settles(self):
        mid = self.confirming()
        r = self.talk(mid, "Yes.", "Confirmed.\n" + fence({"kind": "confirm"}))
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        self.assertEqual(doc["reply"], "Confirmed.")
        self.assertEqual(doc["answer"]["applied"][0]["kind"], "confirm")
        self.assertEqual(doc["answer"]["applied"][0]["index"], 0)
        self.assertIn("confirmed by you in the chat",
                      doc["answer"]["applied"][0]["label"])
        self.assertTrue(self.store.load(mid)["done_when"][0]["met"])
        self.assertEqual(self.settled, [mid], "and the task is settled")

    def test_11_yes_approves_the_held_instruction_and_relaunches(self):
        mid = self.held()
        r = self.talk(mid, "yes", "Sending it.\n" + fence({"kind": "approve"}))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["answer"]["applied"][0]["kind"], "approve")
        m = self.store.load(mid)
        self.assertTrue(m["approval"]["used"])
        self.assertEqual(m["approved_say"], "Push fix/auth to origin and open the PR.")
        self.assertEqual(m["state"], "running")
        self.assertIn(mid, self.launched)
        self.assertEqual(r.json()["mission"]["state"], "running",
                         "the reply carries the record as it now reads")

    def test_12_change_withdraws_and_shadow_is_told(self):
        mid = self.held()
        r = self.talk(mid, "change it to push to a branch, no PR",
                      "Changing.\n" + fence({"kind": "change",
                                             "text": "push to a branch, no PR"}))
        self.assertEqual(r.json()["answer"]["applied"][0]["kind"], "change")
        m = self.store.load(mid)
        self.assertIsNone(m["approval"])
        self.assertEqual(m["state"], "running")
        self.assertIn("push to a branch, no PR", m["founder_says"][-1]["text"])
        self.assertIn(mid, self.launched)

    def test_13_i_did_it_withdraws(self):
        mid = self.held()
        r = self.talk(mid, "I did it myself",
                      "Ok.\n" + fence({"kind": "withdraw", "text": "I did it myself"}))
        self.assertEqual(r.json()["answer"]["applied"][0]["kind"], "withdraw")
        self.assertEqual(self.store.load(mid)["state"], "running")

    def test_14_a_refusal_is_said_not_swallowed(self):
        mid = self.task()
        r = self.talk(mid, "yes", "Ok.\n" + fence({"kind": "approve"}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answer"]["applied"], [])
        self.assertIn("nothing is held", r.json()["answer"]["refused"][0])
        self.assertEqual(self.store.load(mid)["state"], "running")

    def test_15_two_checks_and_no_index_asks_which(self):
        mid = self.task(state="paused", pause_reason="founder_confirm", checks=[
            {"tier": "founder_confirm", "check": "the greeting reads well"},
            {"tier": "founder_confirm", "check": "the tone is right"}])
        r = self.talk(mid, "yes", "Which?\n" + fence({"kind": "confirm"}))
        self.assertIn("which check", r.json()["answer"]["refused"][0])
        self.assertEqual(self.settled, [])

    def test_16_no_fence_no_answer_key(self):
        mid = self.confirming()
        r = self.talk(mid, "what is check 1 again?", "It is the greeting.")
        self.assertNotIn("answer", r.json())
        self.assertFalse(self.store.load(mid)["done_when"][0].get("met"))

    def test_17_the_worker_cannot_answer_through_the_fence(self):
        """The fence only rides a reply to the founder's own line; the
        runner's decide() path parses decisions, not replies. Pinned as a
        property: the loop never calls _apply_answer_fence."""
        src = Path(app_module.__file__).read_text()
        self.assertEqual(src.count("= _apply_answer_fence(blocks, mid)"), 1)
        self.assertEqual(src.count("_apply_answer_fence("), 2,
                         "one definition, one call, in the task chat route")


# --------------------------------------------------------------- buttons --
class TestTheAnswerButtons(Base):

    def test_20_confirm_button_on_the_ask_row(self):
        mid = self.confirming()
        r = self.act(mid, "answer", kind="confirm", index=0)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["answered"]["kind"], "confirm")
        self.assertTrue(self.store.load(mid)["done_when"][0]["met"])
        self.assertEqual(self.settled, [mid])

    def test_21_withdraw_button_on_the_hold_row(self):
        mid = self.held()
        r = self.act(mid, "answer", kind="withdraw")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.store.load(mid)["state"], "running")
        self.assertIn(mid, self.launched)

    def test_22_a_refused_button_is_a_409_in_the_stores_words(self):
        mid = self.task()
        r = self.act(mid, "answer", kind="approve")
        self.assertEqual(r.status_code, 409)
        self.assertIn("nothing is held", r.json()["detail"])
        self.assertEqual(self.act(mid, "answer", kind="nuke").status_code, 409)

    def test_23_at_capacity_the_answer_lands_but_says_so(self):
        mission_engine.set_max_running(1)
        self.task(state="running", target="s-busy")
        mid = self.held()
        r = self.talk(mid, "yes", "Sending.\n" + fence({"kind": "approve"}))
        self.assertEqual(r.status_code, 200)
        self.assertIn("running 1 of 1", r.json()["answer"]["refused"][0])
        m = self.store.load(mid)
        self.assertTrue(m["approval"]["used"], "the approval itself is spent")
        self.assertEqual(m["state"], "paused", "and the task waits for room")


# -------------------------------------------------------------------- J12 --
class TestJ12TakeOverParks(Base):

    def test_30_take_over_during_a_hold_parks_it(self):
        mid = self.held()
        r = self.act(mid, "take_over")
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["pause_reason"], "founder_intervened")
        self.assertEqual(m["parked_say"], "Push fix/auth to origin and open the PR.")
        self.assertIsNone(m["approval"], "Approve is gone")
        self.assertEqual(mission_engine.pending_asks(m)[0]["kind"], "parked")

    def test_31_resume_hands_shadow_a_question_not_the_order(self):
        mid = self.held()
        self.act(mid, "take_over")
        r = self.act(mid, "resume")
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "running")
        self.assertNotIn("parked_say", m)
        self.assertIsNone(m.get("approved_say"), "nothing is resent")
        self.assertEqual(m["founder_says"][-1]["via"], "hand_back")
        self.assertIn("ask me", m["founder_says"][-1]["text"])

    def test_32_a_stale_approve_after_take_over_is_refused(self):
        mid = self.held()
        ap = self.store.load(mid)["approval"]["id"]
        self.act(mid, "take_over")
        r = self.act(mid, "approve", approval_id=ap)
        self.assertEqual(r.status_code, 409)
        self.assertIsNone(self.store.load(mid).get("approved_say"))


if __name__ == "__main__":
    unittest.main()
