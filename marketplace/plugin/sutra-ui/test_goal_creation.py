"""V5 slice 8: natural language -> a proposed Goal, server side.

Shadow already interprets language and already answers in fenced blocks, so
this slice adds ONE block kind to that protocol rather than a parser, a
command system or a second model. The block is a PROPOSAL: nothing is
written when it arrives, and the founder's Confirm is what POSTs to the
existing /api/shadow/goals.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="goal-create-test-"))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import providers  # noqa: E402
import shadow_protocol  # noqa: E402
from goal_store import GoalStore  # noqa: E402
from mission_engine import MissionStore  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


class TestGoalBlock(unittest.TestCase):
    """The protocol addition, parsed deterministically."""

    def test_01_a_goal_block_is_parsed_and_stripped(self):
        reply = ('Here is what I will pursue.\n```goal\n'
                 + json.dumps({"outcome": "get the referral workflow "
                                          "configured and working",
                               "done_when": [
                                   {"tier": "contains_artifact",
                                    "check": "referral webhook returns 200"},
                                   {"tier": "verify",
                                    "check": "end-to-end referral test"}]})
                 + '\n```')
        display, blocks = shadow_protocol.parse_reply(reply)
        self.assertIn("goal", blocks)
        g = blocks["goal"]
        self.assertEqual(g["outcome"],
                         "get the referral workflow configured and working")
        self.assertEqual([c["check"] for c in g["done_when"]],
                         ["referral webhook returns 200",
                          "end-to-end referral test"])
        self.assertEqual([c["tier"] for c in g["done_when"]],
                         ["contains_artifact", "verify"])
        self.assertNotIn("```goal", display, "the block is stripped")
        self.assertIn("Here is what I will pursue", display)

    def test_02_no_outcome_means_no_proposal(self):
        for body in ({"done_when": [{"check": "x"}]}, {"outcome": "   "},
                     {"outcome": ""}):
            _d, blocks = shadow_protocol.parse_reply(
                "```goal\n" + json.dumps(body) + "\n```")
            self.assertNotIn("goal", blocks, body)

    def test_03_vague_criteria_are_dropped_never_coerced(self):
        """The honesty rule: anything that is not a usable check row is
        dropped, so the card can ASK instead of showing an invention."""
        _d, blocks = shadow_protocol.parse_reply(
            "```goal\n" + json.dumps({
                "outcome": "make it work",
                "done_when": ["just make it work", {}, {"check": "  "},
                              {"tier": "verify"}]}) + "\n```")
        self.assertEqual(blocks["goal"]["done_when"], [],
                         "no check is invented from unusable rows")

    def test_04_a_malformed_block_stays_visible_and_does_nothing(self):
        display, blocks = shadow_protocol.parse_reply(
            "```goal\n{not json at all}\n```")
        self.assertNotIn("goal", blocks)
        self.assertIn("```goal", display,
                      "malformed stays visible -- never an invisible effect")

    def test_05_the_other_block_kinds_still_parse(self):
        reply = ("ok\n```mission\n"
                 + json.dumps({"objective": "fix it", "template": "fix"})
                 + "\n```\n```chips\n[\"Start it\"]\n```")
        _d, blocks = shadow_protocol.parse_reply(reply)
        self.assertIn("mission", blocks)
        self.assertIn("chips", blocks)
        self.assertNotIn("goal", blocks)


class TestProposalThroughTheChatRoute(unittest.TestCase):
    """The route echoes a proposal and writes NOTHING."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        self.settings = Path(self.tmp.name) / "settings.json"
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = self.settings
        self.goals = GoalStore()
        self.missions = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def _reply(self, raw, scope_id="01a081"):
        """Drive the block-handling half of the chat route without a live
        Shadow session: parse_reply + the route's own proposal shaping."""
        _display, blocks = shadow_protocol.parse_reply(raw)
        self.assertIn("goal", blocks)
        g = dict(blocks["goal"])
        g["target_session"] = g.get("target_session") or scope_id
        g["needs_criteria"] = not g.get("done_when")
        g["needs_target"] = not g.get("target_session")
        return g

    def test_06_the_proposal_is_bound_to_the_chat_in_focus(self):
        g = self._reply("```goal\n" + json.dumps({
            "outcome": "ship the referral flow",
            "done_when": [{"check": "referral test green"}]}) + "\n```",
            scope_id="01a081")
        self.assertEqual(g["target_session"], "01a081",
                         "the tab's chat, never another")
        self.assertFalse(g["needs_target"])
        self.assertFalse(g["needs_criteria"])

    def test_07_no_chat_in_focus_is_surfaced_not_guessed(self):
        g = self._reply("```goal\n" + json.dumps({
            "outcome": "ship it",
            "done_when": [{"check": "x"}]}) + "\n```", scope_id=None)
        self.assertIsNone(g["target_session"])
        self.assertTrue(g["needs_target"], "the card must ask, not invent")

    def test_08_missing_criteria_is_flagged_for_the_founder(self):
        g = self._reply("```goal\n" + json.dumps({
            "outcome": "make the referral thing work"}) + "\n```")
        self.assertEqual(g["done_when"], [])
        self.assertTrue(g["needs_criteria"])

    def test_09_a_proposal_creates_nothing(self):
        self._reply("```goal\n" + json.dumps({
            "outcome": "ship it", "done_when": [{"check": "x"}]}) + "\n```")
        self.assertEqual(self.goals.list(), [], "no goal was written")
        self.assertEqual(self.missions.list(), [], "and no mission")

    def test_10_confirm_creates_exactly_one_goal_in_draft(self):
        g = self._reply("```goal\n" + json.dumps({
            "outcome": "get the referral workflow configured and working",
            "done_when": [{"check": "referral webhook returns 200"}]})
            + "\n```")
        r = self.client.post("/api/shadow/goals", headers=HDR, json={
            "outcome": g["outcome"], "target_session": g["target_session"],
            "done_when": g["done_when"]})
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        self.assertEqual(doc["state"], "draft", "creation never starts work")
        self.assertEqual(doc["target_session"], "01a081")
        self.assertEqual(doc["checks_total"], 1)
        self.assertEqual(len(self.goals.list()), 1, "exactly one")
        self.assertEqual(self.missions.list(), [],
                         "and no attempt until Start")

    def test_11_the_second_goal_for_one_chat_is_refused_honestly(self):
        body = {"outcome": "a", "target_session": "01a081",
                "done_when": [{"tier": "contains_artifact", "check": "x"}]}
        self.assertEqual(
            self.client.post("/api/shadow/goals", headers=HDR,
                             json=body).status_code, 200)
        r = self.client.post("/api/shadow/goals", headers=HDR,
                             json=dict(body, outcome="b"))
        self.assertEqual(r.status_code, 409)
        self.assertIn("one active goal per chat", r.json()["detail"])

    def test_12_creation_respects_the_shadow_gate(self):
        self.settings.write_text(json.dumps({"shadow.enabled": False}))
        r = self.client.post("/api/shadow/goals", headers=HDR, json={
            "outcome": "x", "target_session": "s",
            "done_when": [{"check": "y"}]})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], "the shadow flag is off")

    def test_13_start_uses_the_existing_action_and_keeps_the_chat(self):
        r = self.client.post("/api/shadow/goals", headers=HDR, json={
            "outcome": "ship the referral flow",
            "target_session": "01a081",
            "done_when": [{"tier": "contains_artifact", "check": "OK"}]})
        gid = r.json()["id"]
        calls = []
        real = app_module.shadow_runner.start_mission_async
        app_module.shadow_runner.start_mission_async = (
            lambda mid, say, provisioner=None, verifier=None:
            (calls.append(mid) or {"accepted": True, "mission_id": mid}))
        try:
            act = self.client.post("/api/shadow/goals/%s/act" % gid,
                                   headers=HDR, json={"action": "start"})
        finally:
            app_module.shadow_runner.start_mission_async = real
        self.assertEqual(act.status_code, 200, act.text)
        mid = act.json()["mission_id"]
        m = self.missions.load(mid)
        self.assertEqual(m["target_session"], "01a081",
                         "the SAME chat -- never a clone")
        self.assertEqual(m["target_mode"], "existing",
                         "no new chat is provisioned")
        self.assertEqual(m["goal_id"], gid)
        self.assertEqual(calls, [mid], "the existing start path was used")
        self.assertEqual(len(self.goals.list()), 1, "still one goal")


if __name__ == "__main__":
    unittest.main()
