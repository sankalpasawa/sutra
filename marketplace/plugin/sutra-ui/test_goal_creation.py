"""V5 slice 8: natural language -> a proposed Goal, server side.

Shadow already interprets language and already answers in fenced blocks, so
this slice adds ONE block kind to that protocol rather than a parser, a
command system or a second model. The block is a PROPOSAL: nothing is
written when it arrives, and the founder's Confirm is what POSTs to the
existing /api/shadow/goals.
"""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="goal-create-test-"))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import providers  # noqa: E402
import session_runtime  # noqa: E402
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
        # 2026-09-11: the proposal boundary no longer passes a tier
        # through unchecked. "referral webhook returns 200" is literal, so
        # it stays machine-checkable; `verify` is not offered to proposals
        # (no production caller injects a verifier, so such a check could
        # never be met by anyone) and becomes the founder's to confirm.
        self.assertEqual([c["tier"] for c in g["done_when"]],
                         ["contains_artifact", "founder_confirm"])
        self.assertEqual(g["done_when"][1]["proposed_tier"], "verify",
                         "and the re-tier is visible, not silent")
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


class TestProtocolAndPanelParity(unittest.TestCase):
    """Guards for the 2026-09-11 clobber. A stale working copy of three files
    was committed over the collaborator's work: shadow_protocol.py lost the
    `goal` fence and the tier contract while app.py kept routing goal blocks,
    panel.css lost the goal-workspace styles, and panel.html lost the
    18-goal-workspace.js script tag, so the workspace JS never loaded. The
    suites that caught it failed three layers down ("'goal' not found in {}").
    Each check here names the missing piece directly."""

    UI = Path(__file__).resolve().parent

    @staticmethod
    def _parsed_fences():
        pat = shadow_protocol._BLOCK.pattern
        return set(pat.split("(", 1)[1].split(")", 1)[0].split("|"))

    def test_every_fence_shadow_md_documents_is_one_the_parser_accepts(self):
        doc = (self.UI / "SHADOW.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"^```([a-z]+)\s*$", doc, re.M))
        self.assertTrue(documented, "SHADOW.md documents no fences at all")
        self.assertEqual(documented - self._parsed_fences(), set(),
                         "SHADOW.md tells the model to emit a fence that "
                         "parse_reply drops on the floor")

    def test_every_block_app_py_routes_is_one_the_parser_can_emit(self):
        src = (self.UI / "app.py").read_text(encoding="utf-8")
        routed = set(re.findall(r'if "([a-z]+)" in blocks', src))
        self.assertIn("goal", routed, "app.py stopped routing goal proposals")
        self.assertEqual(routed - self._parsed_fences(), set(),
                         "app.py routes a block kind parse_reply never emits "
                         "-- the exact shape of the 2026-09-11 regression")

    def test_every_panel_script_is_loaded_by_panel_html(self):
        html = (self.UI / "static" / "panel.html").read_text(encoding="utf-8")
        for js in sorted((self.UI / "static" / "js").glob("*.js")):
            self.assertIn("/static/js/%s" % js.name, html,
                          "%s exists but panel.html never loads it" % js.name)


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
        # Start now attaches first, so the target chat must be reachable
        # (2026-09-11). A live runtime is returned untouched by
        # ensure_runtime -- nothing spawns, nothing is read from disk.
        self._rt = type("LiveRt", (), {"alive": True})()
        session_runtime.register_runtime("01a081", self._rt)

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        session_runtime.unregister_runtime("01a081", self._rt)
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


class _ChatRouteHarness:
    """Drives api_shadow_chat itself with a canned Shadow turn.

    The shaping under test lives in the ROUTE, so a re-implementation of it
    (as _reply above does, deliberately, for the pure-proposal shape) would
    prove nothing about the branch that actually runs.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.missions = MissionStore()
        self.goals = GoalStore()
        self._saved = app_module._SHADOW.get("session")
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def tearDown(self):
        app_module._SHADOW["session"] = self._saved
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def _shadow_says(self, raw):
        """Park a fake Shadow session that answers with exactly `raw`."""
        class Rt:
            async def send_user_frame(self, _text):
                return None

            async def demux_turn(self, collect, sid):
                await collect({"type": "token", "text": raw})
                return (sid or "shadow-sess", 0.0, True, None, None)

        class Sess:
            alive = True
            session_id = "shadow-sess"
            rt = Rt()

        app_module._SHADOW["session"] = Sess()

    def _chat(self, message, scope_id):
        return self.client.post("/api/shadow/chat",
                                json={"message": message,
                                      "scope_id": scope_id},
                                headers=HDR).json()


class TestMissionBlockIsBoundToTheChatInScope(_ChatRouteHarness,
                                              unittest.TestCase):
    """The MISSION half of the same rule, through the real route.

    Founder, 2026-09-13: "Work in existing chat -> Enter -> nothing happens."
    The chat route already bound a GOAL proposal to the tab's chat
    (test_06 above), but the mission branch passed the model's
    `target_session` straight through -- and SHADOW.md tells the model it may
    omit it ("<sid or omit>"). An existing-target mission proposed inside a
    chat therefore landed with target_session None: the task card read "an
    existing chat" with no name and Start had nothing to attach to, so the
    chat was never taken over.

    Driven through api_shadow_chat itself -- see _ChatRouteHarness.
    """

    def test_20_an_omitted_target_means_the_chat_in_scope(self):
        self._shadow_says("On it.\n```mission\n" + json.dumps({
            "objective": "take this chat to done",
            "template": "fix",
            "done_when": [{"tier": "founder_confirm",
                           "check": "the founder signs it off"}]}) + "\n```")
        doc = self._chat("take this chat over", "01a081")
        self.assertIn("mission", doc, "the block must still create a brief")
        self.assertEqual(doc["mission"]["target_mode"], "existing")
        self.assertEqual(doc["mission"]["target_session"], "01a081",
                         "the mission must act in the chat the founder is in")
        self.assertEqual(doc["mission"]["state"], "brief_confirm",
                         "and it is still a brief -- Start stays explicit")

    def test_21_a_named_chat_is_never_overridden(self):
        self._shadow_says("```mission\n" + json.dumps({
            "objective": "fix the other one",
            "template": "fix",
            "target_session": "other-chat"}) + "\n```")
        doc = self._chat("fix the other chat", "01a081")
        self.assertEqual(doc["mission"]["target_session"], "other-chat",
                         "a chat the founder named beats the tab")

    def test_22_a_delegated_mission_never_targets_the_founders_chat(self):
        self._shadow_says("```mission\n" + json.dumps({
            "objective": "start something new",
            "template": "feature",
            "target_mode": "new"}) + "\n```")
        doc = self._chat("start a new one", "01a081")
        self.assertEqual(doc["mission"]["target_mode"], "new")
        self.assertIsNone(doc["mission"]["target_session"],
                          "+ Delegate provisions its OWN chat -- seeding the "
                          "founder's here would hand it to a delegate")

    def test_23_no_chat_in_scope_stays_untargeted(self):
        self._shadow_says("```mission\n" + json.dumps({
            "objective": "do the thing", "template": "fix"}) + "\n```")
        doc = self._chat("do the thing", None)
        self.assertIsNone(doc["mission"]["target_session"],
                          "nothing to bind to is not a licence to guess")


class TestEveryDocumentedFenceParses(unittest.TestCase):
    """THE GUARD FOR THE DELETION ITSELF (d6d6fc53, 2026-09-11).

    `goal` was dropped from shadow_protocol._BLOCK by a UI-mock commit that
    rewrote the module against a stale base and added `module` to the same
    line. Nothing failed loudly: a goal fence simply stopped matching, so it
    was never stripped, never parsed, and app.py's `if "goal" in blocks`
    branch became unreachable. The tests that DID cover it went red and read
    as "pre-existing" for two days.

    Per-kind tests could not stop a repeat, because the per-kind tests were
    exactly what got ignored. This pins the INVARIANT instead: the module
    docstring is the protocol's published surface, and every fence it
    advertises must reach the parser. Drop a kind from either side and this
    fails on the mismatch, not on a downstream feature.
    """

    #: one minimal VALID body per documented fence -- the shapes _eat
    #: accepts, nothing more. A new fence kind adds one row here.
    MINIMAL = {
        "mission": {"objective": "fix it", "template": "fix"},
        "goal": {"outcome": "get it working"},
        "chips": ["Do the thing"],
        "remember": {"text": "be terse", "precedence": "taste"},
        "module": {"name": "Friday review", "kind": "chat"},
        # v4: the brief is prose, not json; a json string is still prose
        "brief": "Objective: \"fix it\". Where: the repo. Done when: tests pass.",
    }

    def _documented(self):
        found = re.findall(r"^    ```(\w+)$", shadow_protocol.__doc__, re.M)
        self.assertTrue(found, "the docstring stopped advertising any fence")
        return set(found)

    def _compiled(self):
        alts = re.search(r"```\(([^)]+)\)", shadow_protocol._BLOCK.pattern)
        self.assertIsNotNone(alts, "_BLOCK stopped being an alternation")
        return set(alts.group(1).split("|"))

    def test_30_goal_is_a_fence_the_parser_knows(self):
        self.assertIn("goal", self._compiled(),
                      "THE BUG: a goal fence never matched, so the goal "
                      "branch of api_shadow_chat could not run")
        self.assertIn("goal", self._documented())

    def test_31_the_docstring_and_the_regex_do_not_drift(self):
        self.assertEqual(self._documented(), self._compiled(),
                         "a fence is advertised but unparsed, or parsed but "
                         "undocumented")

    def test_32_every_documented_fence_round_trips(self):
        for kind in sorted(self._documented()):
            self.assertIn(kind, self.MINIMAL, "no minimal body for %r" % kind)
            raw = ("here you go\n```" + kind + "\n"
                   + json.dumps(self.MINIMAL[kind]) + "\n```")
            display, blocks = shadow_protocol.parse_reply(raw)
            self.assertIn(kind, blocks, "%r did not parse" % kind)
            self.assertNotIn("```" + kind, display,
                             "%r was parsed but left in the reply" % kind)
            self.assertEqual(display, "here you go")


class TestGoalBlockIsBoundToTheChatInScope(_ChatRouteHarness,
                                           unittest.TestCase):
    """The goal branch, now that it is reachable again.

    test_06 above pins the same rule against a re-implementation of the
    route's shaping; these run the route. Both are kept: the first is where
    the shape is specified, this is proof the specified shape is what the
    founder actually gets.
    """

    def test_33_a_goal_proposed_in_a_chat_targets_that_chat(self):
        self._shadow_says("On it.\n```goal\n" + json.dumps({
            "outcome": "get the referral workflow configured and working",
            "done_when": [{"tier": "founder_confirm",
                           "check": "the founder signs it off"}]}) + "\n```")
        doc = self._chat("keep at this until it works", "01a081")
        self.assertIn("goal_proposal", doc,
                      "THE BUG: the fence never parsed, so no card appeared")
        g = doc["goal_proposal"]
        self.assertEqual(g["target_session"], "01a081",
                         "the chat the founder is in, never another")
        self.assertFalse(g["needs_target"])
        self.assertFalse(g["needs_criteria"])
        self.assertNotIn("```goal", doc["reply"], "the block is stripped")
        self.assertEqual(doc["reply"], "On it.")

    def test_34_a_named_chat_still_beats_the_tab(self):
        self._shadow_says("```goal\n" + json.dumps({
            "outcome": "ship the other one",
            "target_session": "other-chat",
            "done_when": [{"tier": "founder_confirm", "check": "signed"}]})
            + "\n```")
        doc = self._chat("do the other chat", "01a081")
        self.assertEqual(doc["goal_proposal"]["target_session"], "other-chat")

    def test_35_no_chat_in_scope_is_asked_for_never_guessed(self):
        self._shadow_says("```goal\n" + json.dumps({
            "outcome": "ship it",
            "done_when": [{"tier": "founder_confirm", "check": "signed"}]})
            + "\n```")
        doc = self._chat("ship it", None)
        self.assertIsNone(doc["goal_proposal"]["target_session"])
        self.assertTrue(doc["goal_proposal"]["needs_target"],
                        "the card must ask, not invent")

    def test_36_a_proposal_still_writes_nothing(self):
        self._shadow_says("```goal\n" + json.dumps({
            "outcome": "ship it",
            "done_when": [{"tier": "founder_confirm", "check": "signed"}]})
            + "\n```")
        self._chat("ship it", "01a081")
        self.assertEqual(self.goals.list(), [],
                         "a goal block is a PROPOSAL -- Confirm writes it")
        self.assertEqual(self.missions.list(), [], "and no mission either")


if __name__ == "__main__":
    unittest.main()
