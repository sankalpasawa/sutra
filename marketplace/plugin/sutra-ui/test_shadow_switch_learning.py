"""Rule 2: Shadow suggests a switch change from a pattern (founder,
2026-10-08). See shadow_switch_learning for the signals and guardrails.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_switch_learning.py
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-swl-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_conversations                    # noqa: E402
import shadow_knows                            # noqa: E402
import shadow_ledger                           # noqa: E402
import shadow_switch_learning as swl           # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
DAY = 86400


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


class Base(unittest.TestCase):
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
        self.store = mission_engine.MissionStore()
        self.now = time.time()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def mission(self, **fields):
        m = self.store.create("some task", "fix", target_mode="new",
                              done_when=[])
        m = self.store.load(m["id"])
        m.update(fields)
        self.store.save(m)
        return m["id"]

    def approval(self, mid, ago=0):
        shadow_ledger.append("actions", {"mission_id": mid, "kind": "approval",
                                         "summary": "approved",
                                         "ts": iso(self.now - ago)})

    def open_(self):
        return {s["name"]: s for s in swl.suggestions(self.now)}


class ThePattern(Base):

    def test_01_three_different_tasks_make_a_suggestion(self):
        shadow_knows.set_switch("acting", "balanced")
        for _ in range(3):
            self.approval(self.mission())
        got = self.open_()["acting"]
        self.assertEqual((got["from"], got["to"]), ("balanced", "just_do_it"))
        self.assertIn("approved 3 held instructions", got["why"])

    def test_02_two_tasks_or_one_busy_task_do_not(self):
        shadow_knows.set_switch("acting", "balanced")
        a, b = self.mission(), self.mission()
        for _ in range(4):
            self.approval(a)
        self.approval(b)
        self.assertNotIn("acting", self.open_())

    def test_03_signals_older_than_the_window_do_not_count(self):
        shadow_knows.set_switch("acting", "balanced")
        for _ in range(3):
            self.approval(self.mission(), ago=31 * DAY)
        self.assertNotIn("acting", self.open_())

    def test_04_no_suggestion_for_the_value_it_already_has(self):
        for _ in range(3):
            self.approval(self.mission())       # default is already just_do_it
        self.assertNotIn("acting", self.open_())

    def test_05_withdrawals_and_stops_point_toward_ask_first(self):
        t = iso(self.now)
        self.mission(withdrawn=[{"text": "x", "at": t, "why": "withdraw"}])
        self.mission(withdrawn=[{"text": "y", "at": t, "why": "change"}])
        stopped = self.mission()
        shadow_ledger.append("missions", {"mission_id": stopped,
                                          "state": "stopped",
                                          "note": "founder stop (home)",
                                          "ts": t})
        got = self.open_()["acting"]
        self.assertEqual(got["to"], "ask_first")

    def test_06_a_delete_or_a_nothing_to_do_close_is_not_a_stop(self):
        t = iso(self.now)
        for note in ("founder delete (home)", "founder closed: nothing to do",
                     "cancelled from queue"):
            shadow_ledger.append("missions", {"mission_id": self.mission(),
                                              "state": "stopped",
                                              "note": note, "ts": t})
        self.assertNotIn("acting", self.open_())

    def test_07_reopened_done_tasks_point_toward_prove(self):
        shadow_knows.set_switch("done", "key")
        for _ in range(3):
            self.mission(reopened=[{"at": iso(self.now), "from": "done",
                                    "via": "talk"}])
        self.assertEqual(self.open_()["done"]["to"], "prove")

    def test_08_what_the_founder_says_moves_replies_and_checkins(self):
        shadow_knows.set_switch("replies", "normal")
        # the built-in 3 nudges an hour already reads as "milestones"
        shadow_knows.set_switch("checkins", "only_stuck")
        t = iso(self.now)
        for text in ("this is too long", "shorter please", "tl;dr?"):
            self.mission(founder_says=[{"text": text, "at": t}])
        for i, text in enumerate(("what's happening?", "any update",
                                  "how's it going")):
            cid = "shc-zz%06d" % i
            shadow_conversations.create(cid, "hi")
            shadow_conversations.append(cid, "founder", text)
        got = self.open_()
        self.assertEqual(got["replies"]["to"], "short")
        self.assertEqual(got["checkins"]["to"], "milestones",
                         "chats count as units too")


class TheAnswer(Base):

    def setUp(self):
        super().setUp()
        shadow_knows.set_switch("acting", "balanced")
        for _ in range(3):
            self.approval(self.mission())

    def test_10_yes_sets_the_switch_and_the_card_goes(self):
        swl.answer("acting", "yes", self.now)
        self.assertEqual(shadow_knows.effective()["acting"], "just_do_it")
        self.assertNotIn("acting", self.open_())

    def test_11_no_rests_it_and_old_signals_never_return(self):
        swl.answer("acting", "no", self.now)
        self.assertEqual(shadow_knows.effective()["acting"], "balanced")
        self.assertNotIn("acting", self.open_())
        later = self.now + 31 * DAY
        self.assertNotIn("acting", {s["name"]: s
                                    for s in swl.suggestions(later)},
                         "the signals before the answer do not count again")

    def test_12_no_means_quiet_even_if_the_pattern_goes_on(self):
        swl.answer("acting", "no", self.now)
        for _ in range(3):
            self.approval(self.mission())
        self.assertNotIn("acting", self.open_(), "resting for 30 days")

    def test_13_an_answer_needs_an_open_suggestion(self):
        with self.assertRaises(shadow_knows.Refused):
            swl.answer("replies", "yes", self.now)
        with self.assertRaises(shadow_knows.Refused):
            swl.answer("acting", "maybe", self.now)

    def test_14_through_the_route(self):
        listing = self.client.get("/api/shadow/knows").json()
        self.assertEqual([s["name"] for s in listing["switch_suggestions"]],
                         ["acting"])
        r = self.client.post("/api/shadow/knows", headers=HDR, json={
            "action": "switch_suggestion", "name": "acting", "answer": "yes"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["knows"]["switch_suggestions"], [])
        self.assertEqual(self.client.post("/api/shadow/knows", headers=HDR,
                                          json={"action": "switch_suggestion",
                                                "name": "acting",
                                                "answer": "yes"}).status_code,
                         409)


if __name__ == "__main__":
    unittest.main(verbosity=2)
