"""A task with nothing to do stops spending turns and asks to be closed
(founder, 2026-10-07).

THE CASE. "Fix a typo in README.md in the sutra repo" (m-62ab83be8a42): the
worker found no typo in any of six copies, its only check ("a typo is
corrected") could never be met, every ask was refused as "an answer on the
machine", and the mission went on searching the disk for .git folders.

THE RULE THAT STAYS. Shadow cannot end a task: DECISION_ACTIONS is still
("continue", "ask_founder") -- the verifier and the founder end work. So the
fix is an ASK, not an ending:

  SCREEN    `nothing_to_do` is admitted when it says what was found, and
            refused when it says nothing.
  ENGINE    the ask blocks the mission (worker kept alive, no more turns)
            with the app's own Close / Keep going form -- never the
            decider's -- the worker's last reply as evidence, and a stamp.
  ROUTE     "close" ends it through the founder's own stop and marks it
            nothing_to_do; "keep" resumes with what to look for.
  PROMPT    the decider is told when to use it and not to widen the hunt.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_nothing_to_do.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-ntd-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionEngine, MissionStore   # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
FOUND = ("no typo in README.md: checked all six sutra checkouts and "
         "origin/main, all identical and clean")

_LOOP = None


def run(coro):
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


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
        self.store = MissionStore()
        self.launched = []
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def running(self):
        m = self.store.create(
            "Fix a typo in README.md in the sutra repo.", "fix",
            target_mode="existing", target_session="sess-ntd",
            done_when=[{"tier": "judge",
                        "check": "a typo in README.md is corrected"}])
        self.store.transition(m["id"], "brief_confirm", "b")
        self.store.transition(m["id"], "running", "admitted")
        return m["id"]

    def drive(self, decisions, replies):
        """Run the real loop with a scripted decider and target."""
        said, transcript = [], {"t": ""}
        replies = list(replies)

        async def sayer(m, text):
            said.append(text)
            transcript["t"] += "\n" + (replies.pop(0) if replies else "(none)")
            return True

        async def waiter(m):
            return True

        calls = []

        async def decide(ctx):
            calls.append(ctx)
            return decisions[min(len(calls) - 1, len(decisions) - 1)]

        eng = MissionEngine(self.store, sayer, waiter,
                            lambda m: transcript["t"], decider=decide)
        mid = self.running()
        return run(eng.run_mission(mid)), said

    def act(self, mid, **body):
        return self.client.post("/api/shadow/missions/%s/act" % mid,
                                json=dict(body, action="intervene"),
                                headers=HDR)


class TheRuleThatStays(unittest.TestCase):

    def test_01_shadow_still_cannot_end_a_task(self):
        self.assertEqual(mission_engine.DECISION_ACTIONS,
                         ("continue", "ask_founder"))
        self.assertIsNone(mission_engine.validate_decision(
            {"action": "nothing_to_do", "reason": FOUND}))

    def test_02_the_screen_admits_it_only_with_what_was_found(self):
        ok, _ = mission_engine.screen_ask(
            {"action": "ask_founder", "ask_kind": "nothing_to_do",
             "reason": FOUND})
        self.assertTrue(ok)
        refused, why = mission_engine.screen_ask(
            {"action": "ask_founder", "ask_kind": "nothing_to_do",
             "reason": ""})
        self.assertFalse(refused, why)

    def test_03_the_kind_rides_the_decision(self):
        d = mission_engine.validate_decision(
            {"action": "ask_founder", "ask_kind": "nothing_to_do",
             "reason": FOUND})
        self.assertEqual(d["ask_kind"], "nothing_to_do")

    def test_04_the_form_is_fixed(self):
        iv = mission_engine.nothing_to_do_request(FOUND)
        self.assertTrue(iv["question"].startswith("Nothing to do here: no typo"))
        nxt = iv["fields"][0]
        self.assertEqual((nxt["key"], nxt["type"], nxt["required"]),
                         ("next", "choice", True))
        self.assertEqual([o["value"] for o in nxt["options"]],
                         ["close", "keep"])

    def test_05_the_decider_is_told_when_and_not_to_widen_the_hunt(self):
        p = " ".join(shadow_runner.render_decide_prompt({}).split())
        self.assertIn("nothing_to_do THE WORK HAS SHOWN THERE IS NOTHING TO DO", p)
        self.assertIn("do NOT widen the hunt", p)
        self.assertIn("you never close a task yourself", p)


class TheEngineAsksInsteadOfSearching(Base):

    def test_10_it_blocks_with_the_apps_form_and_stops_driving(self):
        out, said = self.drive(
            [{"action": "ask_founder", "ask_kind": "nothing_to_do",
              "reason": FOUND,
              # the decider's own form is replaced, never shown
              "intervention": {"question": "Search the whole disk?",
                               "fields": [{"key": "x", "type": "boolean",
                                           "label": "x"}]}}],
            ["Checked every README: no typo anywhere."])
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "needs_founder")
        iv = out["intervention"]
        self.assertTrue(iv["question"].startswith("Nothing to do here:"))
        self.assertEqual(iv["fields"][0]["key"], "next")
        self.assertEqual(out["nothing_to_do"]["intervention_id"], iv["id"])
        self.assertIn("six sutra checkouts", out["nothing_to_do"]["reason"])
        self.assertIn("no typo anywhere", json.dumps(iv.get("evidence")),
                      "the founder sees what the worker found")
        self.assertEqual(len(said), 1, "no turn was spent after the finding")

    def test_11_an_empty_finding_is_refused_and_the_work_goes_on(self):
        out, said = self.drive(
            [{"action": "ask_founder", "ask_kind": "nothing_to_do",
              "reason": ""},
             {"action": "continue", "instruction": "Open README.md again."}],
            ["looked", "looked again", "and again"])
        self.assertNotIn("nothing_to_do", out)


class TheFounderCloses(Base):

    def blocked(self):
        out, _ = self.drive(
            [{"action": "ask_founder", "ask_kind": "nothing_to_do",
              "reason": FOUND}], ["no typo anywhere"])
        return out["id"], out["intervention"]["id"]

    def test_20_close_ends_it_as_nothing_to_do(self):
        mid, ivid = self.blocked()
        r = self.act(mid, intervention_id=ivid, values={"next": "close"})
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "stopped")
        self.assertEqual(m["ended_by"], "founder", "the founder ended it")
        self.assertEqual(m["end_reason"], "nothing_to_do")
        self.assertIn("no typo", m["shadow_result"]["text"])
        self.assertEqual(self.launched, [], "nothing was relaunched")

    def test_21_keep_going_resumes_with_what_to_look_for(self):
        mid, ivid = self.blocked()
        r = self.act(mid, intervention_id=ivid,
                     values={"next": "keep", "look_for": "check docs/ too"})
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "running")
        self.assertNotIn("end_reason", m)
        self.assertEqual(m["founder_response"]["values"]["look_for"],
                         "check docs/ too")
        self.assertEqual(self.launched, [mid])

    def test_22_an_ordinary_question_is_never_closed_by_a_next_value(self):
        """Only the nothing_to_do form's own id can close a task."""
        mid = self.running()
        iv = mission_engine.nothing_to_do_request(FOUND)
        blocked = self.store.block(mid, "needs_founder", "q")
        blocked["intervention"] = iv               # no nothing_to_do stamp
        self.store.save(blocked)
        self.act(mid, intervention_id=iv["id"], values={"next": "close"})
        self.assertEqual(self.store.load(mid)["state"], "running")


if __name__ == "__main__":
    unittest.main(verbosity=2)
