#!/usr/bin/env python3
"""A CRITERION IS ABOUT THE WORLD, NOT ABOUT THIS CONVERSATION
(founder, 2026-09-21, pass 15).

THE REPORT. A task opened with "Hi" showed NEEDS YOU, narrated repo state at
the founder, and carried the criterion

    "the chat has answered the greeting with a short reply that states it is
     ready for a task"

-- a reply the founder never saw. The criteria layer was asserting a
user-visible response that had not been rendered.

THE ROOT CAUSE, and it is one line of the contract rather than a state bug.
`validate_done_when` already refuses a Shadow-written `contains_artifact`
check, for this exact reason: "a check describing a state could be satisfied
by the worker uttering the sentence." A check about what was SAID is that
failure in its purest form -- the utterance IS the evidence, so no tier can
settle it honestly. The judge would be asked to grade the model's own claim;
the founder would be asked to sign off a sentence they were never shown.

So such a check is DROPPED at validation, deterministically, and the decide
prompt is told why and told that a line asking for no work has no criteria to
write at all.

WHAT THIS DOES NOT TOUCH: the DIRECT vs PROPOSAL boundary (pass 11), the
confirm -> done completion line (pass 12), the deliverable preview (pass 14)
and the terminal follow-up classifier (pass 13) are all unchanged, and are
re-asserted at the end of this file.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_greeting.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

# THE HOME IS BOUND BEFORE THE FIRST IMPORT, not in setUp. conftest.py
# does this for pytest, and the DMG gate runs these lanes through
# run-tests.sh (plain unittest), where nothing does -- so anything that
# ledgers during import or outside a test method reached the LIVE shadow
# home. shadow_ledger refuses that outright, which is how this was
# caught; a per-test temp home still binds in setUp on top of it.
os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-greeting-"))

import app as app_module
from fastapi.testclient import TestClient

import mission_engine
import providers
import shadow_protocol
import shadow_runner
from mission_engine import MissionStore

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


class FakeChat:
    def __init__(self, reply="Hi! What can I help you with?"):
        self.reply = reply
        self.heard = []
        self.alive = True

    async def talk(self, message):
        self.heard.append(message)
        return shadow_protocol.parse_reply(self.reply)


class TheSelfReferentialRefusal(unittest.TestCase):
    """THE LOAD-BEARING TEST (#7): a criterion cannot be satisfied merely
    because the model claims it answered something."""

    REPORTED = ("the chat has answered the greeting with a short reply that "
                "states it is ready for a task")

    def test_the_reported_criterion_is_refused(self):
        self.assertTrue(shadow_protocol.is_self_referential(self.REPORTED))
        self.assertEqual(
            mission_engine.validate_done_when(
                [{"tier": "judge", "check": self.REPORTED}]),
            [], "a claim about Shadow's own reply is not a criterion")

    def test_every_shape_of_the_same_claim_is_refused(self):
        for check in ("Shadow replied to the greeting",
                      "the conversation acknowledges the request",
                      "a reply was sent to the founder",
                      "the greeting was answered",
                      "your response states it is ready for a task",
                      "the message was delivered"):
            with self.subTest(check=check):
                self.assertEqual(
                    mission_engine.validate_done_when(
                        [{"tier": "judge", "check": check}]), [], check)

    def test_checks_about_the_world_are_untouched(self):
        """The refusal is anchored on the SUBJECT, so a check about a file
        that happens to use a speech verb survives."""
        # MAX_DECIDER_CHECKS bounds the list, so this stays under it --
        # the claim is about the REFUSAL, not about the cap.
        keep = ["the itinerary is the trip you want",
                "the tests pass",
                "the README answers the setup question",
                "alien-species.txt has 10 lines",
                "the file states the current version",
                "the fix addresses the root cause"]
        rows = mission_engine.validate_done_when(
            [{"tier": "judge", "check": c} for c in keep])
        self.assertEqual([r["check"] for r in rows], keep)

    def test_a_refusal_does_not_cost_the_other_checks(self):
        rows = mission_engine.validate_done_when([
            {"tier": "judge", "check": self.REPORTED},
            {"tier": "judge", "check": "the fix addresses the root cause"}])
        self.assertEqual([r["check"] for r in rows],
                         ["the fix addresses the root cause"])

    def test_it_cannot_be_smuggled_in_on_another_tier(self):
        """Dropped, never re-tiered: no tier can settle it honestly."""
        for tier in ("judge", "verify", "founder_confirm"):
            with self.subTest(tier=tier):
                self.assertEqual(
                    mission_engine.validate_done_when(
                        [{"tier": tier, "check": self.REPORTED,
                          "probe": {"kind": "file_exists", "path": "x"}}]),
                    [], tier)

class TheConversationMissionBoundary(unittest.TestCase):
    """THE CONVERSATION -> MISSION MECHANISM.

    PASS 16'S PROMPT RULES WERE REVERTED (founder, 2026-09-21: "undo the last
    2 prompt changes -- they've made my product worse"), so the assertions
    that pinned their wording are gone with them. What remains is the
    MECHANISM they relied on, which is unchanged and worth holding: a mission
    exists only because Shadow emits a `mission` fence.

    THE CONTROL FLOW, traced before changing anything:

        composer -> POST /api/shadow/chat -> Shadow's turn
                 -> for mspec in blocks["missions"]: store.create(...)

    A mission exists ONLY because Shadow emitted a `mission` fence. Nothing
    creates one "despite no work requested" -- Shadow emitted a fence for a
    greeting. So the whole boundary is the instruction that decides whether
    the fence is emitted, and there is no state to add.

    BOTH INSTRUCTIONS HAD THE SAME FAULT: the intake prefix opened with an
    unconditional "treat it as work to delegate" and left "if it is genuinely
    not work, emit no block" as a trailing clause; SHADOW.md said how to
    propose a mission and never said when not to. Both now ask "is there work
    in it?" first.
    """

    def test_no_fence_means_no_mission(self):
        """THE MECHANISM, asserted rather than assumed: the create loop reads
        blocks["missions"], so a reply with no fence creates nothing."""
        _display, blocks = shadow_protocol.parse_reply(
            "Hi! What can I help you with?")
        self.assertEqual(blocks.get("missions") or [], [],
                         "a plain reply must carry no mission")

    def test_a_fence_still_opens_a_task(self):
        """#5: the next line, if it is work, opens a mission exactly as
        before -- the mechanism is untouched."""
        _display, blocks = shadow_protocol.parse_reply(
            "On it.\n```mission\n" + json.dumps({
                "objective": "Make me a 10-day Africa itinerary",
                "template": "research", "target_mode": "new"}) + "\n```")
        specs = blocks.get("missions") or []
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["objective"],
                         "Make me a 10-day Africa itinerary")


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

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        app_module._ensure_task_chat = self._real_ensure
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def open(self, message):
        return self.client.post("/api/shadow/tasks",
                                json={"message": message}, headers=HDR)


class AGreetingIsAnswered(Base):
    """#1-#6: the founder says "Hi" and gets an answer, and nothing else
    happens."""

    def test_1_shadow_answers_visibly(self):
        r = self.open("Hi")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["reply"], "Hi! What can I help you with?")

    def test_2_it_is_not_needs_you(self):
        r = self.open("Hi")
        state = r.json()["mission"]["state"]
        self.assertNotEqual(state, "blocked", "a greeting must not need you")
        self.assertNotEqual(state, "paused")

    def test_3_no_founder_confirmation_is_requested(self):
        r = self.open("Hi")
        m = r.json()["mission"]
        self.assertEqual(
            [c for c in (m.get("done_when") or [])
             if c.get("tier") == "founder_confirm"], [],
            "a greeting must not ask the founder to sign anything off")

    def test_4_no_worker_is_launched(self):
        self.open("Hi")
        self.assertEqual(self.launched, [],
                         "answering a greeting must spawn no worker")

    def test_5_diagnostics_do_not_replace_the_answer(self):
        """The conversational answer is what the founder receives, whatever
        the repository happens to look like."""
        self.chat.reply = "Hi! What can I help you with?"
        r = self.open("Hi")
        reply = r.json()["reply"]
        for noise in ("repo sits at", "uncommitted", "modified Shadow files",
                      "v2.291"):
            self.assertNotIn(noise, reply)

    def test_6_the_stored_and_returned_response_are_the_same(self):
        """Shadow's reply is returned to the founder AND is the turn in the
        task's own chat -- one response, not two."""
        r = self.open("Hi")
        self.assertEqual(self.chat.heard, ["Hi"],
                         "Shadow was asked exactly the founder's words")
        self.assertEqual(r.json()["reply"], self.chat.reply,
                         "and what came back is what it said")

    def test_a_greeting_never_gains_a_self_referential_criterion(self):
        """Even if the model writes one at draft time, it is refused before
        it can reach the record."""
        self.chat.reply = ("Hi!\n```mission\n" + json.dumps({
            "objective": "Hi",
            "done_when": [{"tier": "judge",
                           "check": "the chat has answered the greeting"}],
        }) + "\n```")
        r = self.open("Hi")
        rows = r.json()["mission"].get("done_when") or []
        self.assertEqual(
            [c for c in rows
             if shadow_protocol.is_self_referential(c.get("check", ""))], [],
            "a self-referential criterion reached the record")


class NothingElseMoved(unittest.TestCase):
    """#8: the boundaries from the previous passes, re-asserted."""

    def evaluate(self, checks, transcript="done"):
        return mission_engine.evaluate_done_when(
            {"done_when": checks}, transcript, verifier=lambda *a, **k: None)

    def test_the_proposal_boundary_is_unchanged(self):
        done, _ = self.evaluate([
            {"tier": "contains_artifact", "check": "europe-15-day.md"},
            {"tier": "founder_confirm", "check": "it is the trip you want"}])
        self.assertFalse(done, "a proposal still waits for the founder")

    def test_a_proposal_check_still_survives_validation(self):
        """The refusal must not eat the founder tier it sits beside."""
        rows = mission_engine.validate_done_when(
            [{"tier": "founder_confirm",
              "check": "the 15-day Europe itinerary is the trip you want"}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], shadow_protocol.FOUNDER_TIER)

    def test_a_direct_deliverable_still_needs_no_approval(self):
        done, _ = self.evaluate(
            [{"tier": "contains_artifact", "check": "alien-species.txt"}],
            transcript="alien-species.txt")
        self.assertTrue(done)

    def test_a_verify_probe_still_survives_validation(self):
        rows = mission_engine.validate_done_when(
            [{"tier": "verify", "check": "notes.txt has 10 lines",
              "probe": {"kind": "line_count", "path": "notes.txt",
                        "count": 10}}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], "verify")
        self.assertIn("probe", rows[0])


if __name__ == "__main__":
    unittest.main()
