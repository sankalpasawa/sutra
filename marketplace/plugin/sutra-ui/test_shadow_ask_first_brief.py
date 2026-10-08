""""Ask first" holds the opening brief, before any worker exists (founder,
2026-10-08, manual test 9).

THE GAP. The top-tier hold lived in the turn loop, but a task with a new
worker gets its opening brief AT SPAWN -- so "Create hello.txt" finished
without asking, and fizzbuzz asked only at its second instruction.

  RULE      held_before_spawn_needed: L3 + confirm_top_tier + not yet
            confirmed. Off by default ("Just do it").
  SPAWN     app._delegate_spawn raises HeldBeforeSpawn after writing the
            brief; start_mission_async parks the task (paused,
            autonomy_top_tier, approval bound to the brief, no worker).
  YES       Approve / Resume / a typed yes all go through
            _release_spawn_hold: hold spent, approved say dropped (the brief
            is delivered at spawn), the worker launched by the start path.

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_ask_first_brief.py
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-askfirst-")

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN,
       "Origin": "http://127.0.0.1:8330"}
BRIEF = 'Objective: "Create hello.txt containing the word hello." ...'


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
        self.starts = []
        self._real_start = shadow_runner.start_mission_async
        shadow_runner.start_mission_async = (
            lambda mid, *a, **k: self.starts.append((mid, k)))

    def tearDown(self):
        shadow_runner.start_mission_async = self._real_start
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def draft(self):
        m = self.store.create("Create hello.txt containing the word hello.",
                              "fix", target_mode="new", done_when=[])
        self.store.transition(m["id"], "brief_confirm", "proposed")
        return m["id"]

    def held(self):
        mid = self.draft()
        mission_engine.set_confirm_top_tier(True)
        mission_engine.hold_before_spawn(self.store, mid, BRIEF, BRIEF)
        return mid


class TheRule(Base):

    def test_01_off_by_default(self):
        self.assertFalse(mission_engine.held_before_spawn_needed({}))

    def test_02_ask_first_holds_until_confirmed(self):
        mission_engine.set_confirm_top_tier(True)
        self.assertTrue(mission_engine.held_before_spawn_needed({}))
        self.assertFalse(mission_engine.held_before_spawn_needed(
            {"top_tier_confirmed": True}))


class TheSpawnHolds(Base):

    def test_10_the_spawner_raises_with_the_brief_it_wrote(self):
        mid = self.draft()
        m = self.store.load(mid)
        m["manifest"] = BRIEF               # the brief is already written
        self.store.save(m)
        mission_engine.set_confirm_top_tier(True)
        with self.assertRaises(mission_engine.HeldBeforeSpawn) as cm:
            asyncio.run(app_module._delegate_spawn(self.store.load(mid)))
        self.assertEqual(cm.exception.brief, BRIEF)
        self.assertEqual(cm.exception.manifest, BRIEF)

    def test_11_the_start_path_parks_it_with_no_worker(self):
        shadow_runner.start_mission_async = self._real_start
        mid = self.draft()
        mission_engine.set_confirm_top_tier(True)
        spawned = []

        async def spawner(mission):
            if mission_engine.held_before_spawn_needed(
                    self.store.load(mission["id"])):
                raise mission_engine.HeldBeforeSpawn(BRIEF, BRIEF)
            spawned.append(mission["id"])
            return "w-1"

        async def go():
            shadow_runner.start_mission_async(
                mid, lambda *a, **k: None, provisioner=spawner)
            for _ in range(200):
                await asyncio.sleep(0.01)
                if (self.store.load(mid) or {}).get("held_before_spawn"):
                    return
        asyncio.run(go())
        m = self.store.load(mid)
        self.assertEqual((m["state"], m["pause_reason"]),
                         ("paused", "autonomy_top_tier"))
        self.assertEqual(m["pending_say"], BRIEF, "the founder sees the brief")
        self.assertTrue(m["approval"]["id"])
        self.assertIsNone(m.get("target_session"), "no worker exists")
        self.assertEqual(spawned, [])


class TheYesLaunches(Base):

    def test_20_approve_launches_and_spends_the_hold(self):
        mid = self.held()
        ap = self.store.load(mid)["approval"]["id"]
        r = self.client.post("/api/shadow/missions/%s/act" % mid, headers=HDR,
                             json={"action": "approve", "approval_id": ap})
        self.assertEqual(r.status_code, 200, r.text)
        m = self.store.load(mid)
        self.assertTrue(m["top_tier_confirmed"])
        self.assertNotIn("held_before_spawn", m)
        self.assertNotIn("approved_say", m, "the brief is not sent twice")
        self.assertEqual([s[0] for s in self.starts], [mid],
                         "the worker is launched through the start path")
        self.assertFalse(mission_engine.held_before_spawn_needed(m),
                         "and it is never held again")

    def test_21_resume_does_the_same(self):
        mid = self.held()
        r = self.client.post("/api/shadow/missions/%s/act" % mid, headers=HDR,
                             json={"action": "resume"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([s[0] for s in self.starts], [mid])

    def test_22_a_typed_yes_does_the_same(self):
        mid = self.held()
        outcome = mission_engine.apply_answer(self.store, mid,
                                              {"kind": "approve"})
        app_module._continue_after_answer(self.store, mid, outcome)
        self.assertEqual([s[0] for s in self.starts], [mid])

    def test_23_an_ordinary_hold_still_resumes_its_loop(self):
        """A hold on a task that already has a worker is unchanged."""
        launched = []
        real = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: launched.append(mid)
        try:
            mid = self.draft()
            self.store.transition(mid, "running", "admitted")
            eng = mission_engine.MissionEngine(self.store, None, None, None)
            mission_engine.set_confirm_top_tier(True)
            eng._hold_say(self.store.load(mid), "autonomy_top_tier", "n",
                          "next step")
            ap = self.store.load(mid)["approval"]["id"]
            self.client.post("/api/shadow/missions/%s/act" % mid, headers=HDR,
                             json={"action": "approve", "approval_id": ap})
        finally:
            shadow_runner._launch = real
        self.assertEqual(launched, [mid])
        self.assertEqual(self.starts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
