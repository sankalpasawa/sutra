"""Shadow v4 step 6 (C3): the Now chat splits one message into several tasks.

One reply may carry SEVERAL ```mission fences, one per task. parse_reply
returns them all under `missions` (in reply order) and keeps `mission` as the
FIRST one so every existing reader of blocks["mission"] is unchanged. The chat
route creates one brief_confirm draft per fence and answers with `missions`
(list) plus `mission` (the first), same compatibility rule.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_protocol.py
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SUTRA_SHADOW_HOME",
                      tempfile.mkdtemp(prefix="shadow-v4-protocol-"))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import providers  # noqa: E402
import shadow_protocol  # noqa: E402
from mission_engine import MissionStore  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}


def _fence(objective, template="research", **extra):
    spec = {"objective": objective, "template": template,
            "target_mode": "new",
            "done_when": [{"tier": "founder_confirm",
                           "check": "the founder signs it off"}]}
    spec.update(extra)
    return "```mission\n" + json.dumps(spec) + "\n```"


class TestParseReplyMissions(unittest.TestCase):
    """The parser: a list, in order, first one mirrored to `mission`."""

    def test_01_three_fences_yield_three_missions_in_order(self):
        reply = ("Three tasks.\n" + _fence("Fix the login bug", "fix")
                 + "\n" + _fence("Research SSO vendors")
                 + "\n" + _fence("Draft the pricing page", "feature"))
        display, blocks = shadow_protocol.parse_reply(reply)
        self.assertEqual(display, "Three tasks.")
        self.assertEqual([m["objective"] for m in blocks["missions"]],
                         ["Fix the login bug", "Research SSO vendors",
                          "Draft the pricing page"])
        self.assertEqual(blocks["mission"]["objective"], "Fix the login bug",
                         "`mission` stays the FIRST fence for old readers")

    def test_02_one_fence_is_a_list_of_one(self):
        display, blocks = shadow_protocol.parse_reply(
            "One task.\n" + _fence("Top 10 fruits in the market"))
        self.assertEqual(len(blocks["missions"]), 1)
        self.assertIs(blocks["missions"][0], blocks["mission"])

    def test_03_no_fence_means_no_missions_key(self):
        display, blocks = shadow_protocol.parse_reply("Just talk.")
        self.assertNotIn("missions", blocks)
        self.assertNotIn("mission", blocks)

    def test_04_a_malformed_fence_stays_visible_and_the_rest_parse(self):
        bad = "```mission\n{not json\n```"
        reply = (_fence("A") + "\n" + bad + "\n" + _fence("C"))
        display, blocks = shadow_protocol.parse_reply(reply)
        self.assertEqual([m["objective"] for m in blocks["missions"]],
                         ["A", "C"])
        self.assertIn("{not json", display,
                      "an invalid block is left visible, never a side effect")

    def test_05_an_invalid_template_fence_is_skipped_not_fatal(self):
        reply = _fence("A") + "\n" + _fence("B", template="bogus")
        display, blocks = shadow_protocol.parse_reply(reply)
        self.assertEqual([m["objective"] for m in blocks["missions"]], ["A"])
        self.assertIn("bogus", display)


class TestChatRouteCreatesOneDraftPerFence(unittest.TestCase):
    """Through the real route, with the Shadow session faked (the harness
    pattern of test_goal_creation.py)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self._saved = app_module._SHADOW.get("session")
        self.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def tearDown(self):
        app_module._SHADOW["session"] = self._saved
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def _shadow_says(self, raw):
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

    def _chat(self, message):
        return self.client.post("/api/shadow/chat",
                                json={"message": message}, headers=HDR).json()

    def test_10_three_fences_become_three_drafts(self):
        self._shadow_says("Three tasks.\n" + _fence("Fix the login bug", "fix")
                          + "\n" + _fence("Research SSO vendors")
                          + "\n" + _fence("Draft the pricing page", "feature"))
        doc = self._chat("fix login, research SSO, draft pricing")
        self.assertEqual(doc["reply"], "Three tasks.")
        self.assertEqual([m["objective"] for m in doc["missions"]],
                         ["Fix the login bug", "Research SSO vendors",
                          "Draft the pricing page"])
        self.assertEqual(doc["mission"]["id"], doc["missions"][0]["id"],
                         "`mission` mirrors the first draft for old readers")
        for m in doc["missions"]:
            self.assertEqual(m["state"], "brief_confirm")
            self.assertEqual(m["target_mode"], "new")
        ids = [m["id"] for m in doc["missions"]]
        self.assertEqual(len(set(ids)), 3)
        on_disk = {m["id"] for m in self.store.list()}
        self.assertTrue(set(ids) <= on_disk)

    def test_11_one_fence_is_one_draft_and_shape_unchanged(self):
        self._shadow_says("One task.\n" + _fence("Top 10 fruits"))
        doc = self._chat("top 10 fruits")
        self.assertEqual(len(doc["missions"]), 1)
        self.assertEqual(doc["mission"]["objective"], "Top 10 fruits")

    def test_12_no_fence_no_missions_key(self):
        self._shadow_says("Nothing to start.")
        doc = self._chat("hello")
        self.assertNotIn("missions", doc)
        self.assertNotIn("mission", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
