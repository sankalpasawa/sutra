#!/usr/bin/env python3
"""Free-form founder input reaches Shadow, and only Shadow.

WHAT THIS IS FOR (founder, 2026-09-15). "Say anything" posted to
/api/shadow/chat -- the chief-of-staff conversation, which holds no mission
and cannot act on one. So an aside typed while a task was running ("actually,
prioritise release safety") reached something that could reply about the work
and nothing that could change it.

THE SHAPE. A new verb on the mission action endpoint every other Shadow
control already uses. It appends to `founder_says` on the record; run_mission
re-loads the record at the top of every turn, so the DECIDER reads it next
turn and decides for itself what it means. Nothing sends into the delegate
session -- the founder talks to Shadow, Shadow drives the worker.

WHAT IT IS NOT. Not an intervention: it answers no question, resolves no
block, confirms no check, and lives in its own field so the two can never be
confused. done_when evaluation, confirms_check and the state machine are
untouched.

Run: python3 test_shadow_say.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore        # noqa: E402

MIS = "/api/shadow/missions"


class SayBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def mission(self, state="running"):
        m = self.store.create("ship it", "fix", target_mode="new",
                              target_session="sess-keep",
                              done_when=[{"tier": "founder_confirm",
                                          "check": "It works."}])
        mid = m["id"]
        self.store.transition(mid, "brief_confirm", "proposed")
        if state != "brief_confirm":
            self.store.transition(mid, "running", "admitted")
        if state not in ("running", "brief_confirm"):
            if state == "blocked":
                self.store.block(mid, "needs_founder", "asked")
            else:
                self.store.transition(mid, state, "test")
        return mid

    def say(self, mid, text):
        return self.client.post("%s/%s/act" % (MIS, mid),
                                json={"action": "say", "text": text})


class SayLands(SayBase):
    def test_running_mission_records_the_aside(self):
        mid = self.mission("running")
        r = self.say(mid, "Prioritize release safety over code cleanliness.")
        self.assertEqual(r.status_code, 200)
        m = self.store.load(mid)
        says = m.get("founder_says") or []
        self.assertEqual(len(says), 1)
        self.assertEqual(says[0]["text"],
                         "Prioritize release safety over code cleanliness.")
        self.assertFalse(says[0]["seen"], "unread until a turn reads it")
        self.assertIn("at", says[0], "stamped, so the timeline can place it")
        # THE STATE DID NOT MOVE. An aside is not a lifecycle event.
        self.assertEqual(m["state"], "running")

    def test_several_asides_all_survive(self):
        mid = self.mission("running")
        for t in ("first", "second", "third"):
            self.assertEqual(self.say(mid, t).status_code, 200)
        says = self.store.load(mid)["founder_says"]
        self.assertEqual([s["text"] for s in says], ["first", "second", "third"],
                         "a list, not a field -- none overwrites another")

    def test_it_is_not_an_intervention(self):
        mid = self.mission("running")
        self.say(mid, "use the existing implementation")
        m = self.store.load(mid)
        self.assertNotIn("founder_response", m,
                         "an aside must not masquerade as an answer")
        self.assertNotIn("intervention", m, "and must not create a question")
        self.assertFalse(m["done_when"][0].get("met"),
                         "and must never satisfy a check")

    def test_empty_text_is_refused(self):
        mid = self.mission("running")
        self.assertEqual(self.say(mid, "   ").status_code, 400)
        self.assertIsNone(self.store.load(mid).get("founder_says"))


class SayRespectsState(SayBase):
    def test_terminal_missions_refuse_and_write_nothing(self):
        for state in ("done", "failed", "stopped"):
            mid = self.mission(state)
            r = self.say(mid, "actually, do it differently")
            self.assertEqual(r.status_code, 409, "%s must refuse" % state)
            m = self.store.load(mid)
            self.assertIsNone(m.get("founder_says"),
                              "%s must write nothing" % state)
            self.assertEqual(m["state"], state,
                             "%s must not be resurrected" % state)

    def test_live_and_waiting_states_accept(self):
        for state in ("running", "paused", "blocked", "brief_confirm"):
            mid = self.mission(state)
            r = self.say(mid, "noted")
            self.assertEqual(r.status_code, 200, "%s must accept" % state)
            self.assertEqual(self.store.load(mid)["state"], state,
                             "%s must not change state" % state)

    def test_blocked_mission_keeps_its_intervention(self):
        mid = self.mission("blocked")
        b = self.store.load(mid)
        b["intervention"] = {"id": "iv-1", "question": "ok?",
                             "fields": [{"key": "ok", "type": "boolean",
                                         "label": "ok"}]}
        self.store.save(b)
        self.assertEqual(self.say(mid, "some context for you").status_code, 200)
        m = self.store.load(mid)
        self.assertEqual(m["intervention"]["id"], "iv-1",
                         "an aside must not retire the pending question")
        self.assertEqual(m["state"], "blocked", "nor unblock the mission")

    def test_unknown_mission_is_404(self):
        self.assertEqual(self.say("m-nope", "hi").status_code, 404)


class SayReachesTheDecider(SayBase):
    def test_context_carries_unseen_asides_then_stops(self):
        mid = self.mission("running")
        self.say(mid, "prioritise release safety")
        m = self.store.load(mid)
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(m, "the worker said something")
        self.assertEqual([s["text"] for s in ctx["founder_says"]],
                         ["prioritise release safety"],
                         "the decider is told what the founder volunteered")
        # ...and it is its OWN block, never folded into what the chat said
        self.assertNotIn("prioritise release safety", ctx["last_response"])
        self.assertNotIn("founder_response", ctx,
                         "an aside is not an answer to a question")
        # once a turn has read it, it is standing context rather than news
        for s in m["founder_says"]:
            s["seen"] = True
        self.assertNotIn("founder_says", eng._decision_context(m, ""),
                         "a seen aside must not repeat every turn")

    def test_prompt_renders_the_asides_as_their_own_section(self):
        """TAGGED BY CHANNEL since step 2 (2026-09-16). An untagged row is a
        typed instruction by construction -- the say endpoint was the only
        writer before `via` existed -- so every historical aside still reads
        as the instruction it was."""
        text = shadow_runner._founder_says_text(
            [{"text": "prioritise release safety"}, {"text": "don't touch x"}])
        self.assertEqual(
            text,
            "- [instruction] prioritise release safety\n"
            "- [instruction] don't touch x")
        self.assertEqual(shadow_runner._founder_says_text(None), "(none)",
                         "a mission nobody has spoken to says (none)")
        self.assertEqual(shadow_runner._founder_says_text([]), "(none)")

    def test_the_two_channels_are_distinguishable_in_the_prompt(self):
        """Shadow cannot judge relevance without knowing which door a line
        came through: an instruction was composed to change the work, a
        conversational remark may be about nothing at all."""
        text = shadow_runner._founder_says_text([
            {"text": "Do not modify the API.", "via": "say"},
            {"text": "I think JSON is better than CSV.", "via": "talk"}])
        self.assertEqual(
            text,
            "- [instruction] Do not modify the API.\n"
            "- [conversation] I think JSON is better than CSV.")

    def test_the_prompt_tells_shadow_to_decide_rather_than_forward(self):
        """The whole point of step 2: casual conversation must not become a
        worker instruction by arriving."""
        prompt = shadow_runner.render_decide_prompt({
            "outcome": "x", "checks": [], "turns_used": 1, "max_turns": 9,
            "founder_says": [{"text": "maybe JSON", "via": "talk"}]})
        self.assertIn("[conversation]", prompt)
        self.assertIn("[instruction]", prompt)
        self.assertIn("NEITHER IS A MESSAGE FOR THE WORKER", prompt)
        self.assertIn("Do not forward the founder's wording", prompt)
        self.assertIn("do not instruct at all when nothing they said", prompt)


class DeleteIsUntouched(SayBase):
    def test_delete_still_works_after_an_aside(self):
        mid = self.mission("running")
        self.say(mid, "an aside")
        r = self.client.post("%s/%s/act" % (MIS, mid), json={"action": "delete"})
        self.assertIn(r.status_code, (200, 204),
                      "Delete must be unaffected by founder_says")
        # ARCHIVE THEN ERASE (2026-09-19). One press files the task; the
        # second is the eraser this test has always been about.
        self.assertIsNotNone(self.store.load(mid), "the first press archives")
        self.client.post("%s/%s/act" % (MIS, mid), json={"action": "delete"})
        self.assertIsNone(self.store.load(mid), "the record is gone")


if __name__ == "__main__":
    unittest.main(verbosity=2)
