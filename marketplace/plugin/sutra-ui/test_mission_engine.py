"""PLAN-100 S43-S50 (+S54): the mission engine against a mock session."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import providers
import mission_engine
from mission_engine import MissionStore, MissionEngine, evaluate_done_when


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def engine(self, transcripts=None, say_ok=True, waiter_result=True):
        self.says = []

        async def sayer(m, text):
            self.says.append(text)
            return say_ok

        async def waiter(m):
            return waiter_result

        def reader(m):
            if transcripts is None:
                return " ".join(self.says)
            i = min(len(self.says) - 1, len(transcripts) - 1)
            return transcripts[i] if transcripts else ""

        return MissionEngine(self.store, sayer, waiter, reader)


class TestStore(Base):
    def test_01_create_and_legal_transitions(self):
        m = self.store.create("fix the nav test", "fix")
        self.assertEqual(m["state"], "draft")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        with self.assertRaises(ValueError):
            self.store.transition(m["id"], "queued")  # running -> queued illegal

    def test_02_seq_ties_store_to_ledger(self):
        import shadow_ledger
        m = self.store.create("x" * 10, "fix")
        self.store.transition(m["id"], "brief_confirm")
        rows = [r for r in shadow_ledger.read("missions", 50)
                if r.get("mission_id") == m["id"] and r.get("seq")]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["seq"], self.store.load(m["id"])["seq"])

    def test_03_amend_bumps_version_keeps_budget(self):
        m = self.store.create("objective one", "feature")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        mm = self.store.load(m["id"])
        mm["turns_used"] = 7
        self.store.save(mm)
        # running missions stay running on amend detour; queued go back
        m2 = self.store.create("objective two", "feature")
        self.store.transition(m2["id"], "brief_confirm")
        self.store.transition(m2["id"], "queued")
        amended = self.store.amend(m2["id"], objective="tighter objective")
        self.assertEqual(amended["version"], 2)
        self.assertEqual(amended["state"], "brief_confirm")
        kept = self.store.amend(m["id"], objective="still mission one")
        self.assertEqual(kept["turns_used"], 7,
                         "amend never resets the budget")

    def test_04_confirm_check_is_the_only_founder_confirm_writer(self):
        m = self.store.create("ship it", "feature",
                              done_when=[{"tier": "founder_confirm",
                                          "check": "founder says yes"}])
        ok, results = evaluate_done_when(m, "founder says yes in transcript")
        self.assertFalse(ok, "transcript text must never satisfy the tier")
        self.store.confirm_check(m["id"], 0)
        m = self.store.load(m["id"])
        ok, _ = evaluate_done_when(m, "")
        self.assertTrue(ok)
        with self.assertRaises(ValueError):
            self.store.confirm_check(m["id"], 5)


class TestLoop(Base):
    def _running(self, template="fix", done_when=None, objective="do the thing"):
        m = self.store.create(objective, template, done_when=done_when)
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        return m

    def test_05_loop_reaches_done_via_contains(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "ALL GREEN"}])
        eng = self.engine(transcripts=["working on it", "tests ALL GREEN"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        self.assertEqual(self.store.load(m["id"])["turns_used"], 2)

    def test_06_max_turns_fails_deterministically(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER-THERE"}])
        mm = self.store.load(m["id"])
        mm["max_turns"] = 3
        self.store.save(mm)
        # vary the say each turn so ping-pong does not fire first
        eng = self.engine(transcripts=["a", "b", "c", "d"])
        n = {"i": 0}
        orig = eng._next_say
        def varied(mission):
            n["i"] += 1
            return "%s #%d" % (orig(mission), n["i"])
        eng._next_say = varied
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "failed")
        self.assertIn("max turns", self._last_note(m["id"]))

    def test_07_ping_pong_stops(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER"}])
        eng = self.engine(transcripts=["same", "same", "same"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "stopped")
        self.assertIn("ping-pong", self._last_note(m["id"]))

    def test_08_founder_stop_honored_mid_loop(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER"}])
        eng = self.engine()
        async def stopping_waiter(mission):
            eng2 = MissionEngine(self.store, None, None, None)
            eng2.founder_stop(mission["id"])
            return True
        eng.waiter = stopping_waiter
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "stopped")

    def test_09_intervention_pauses_and_resume_continues(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "FINISHED"}])
        eng = self.engine(transcripts=["nothing yet", "FINISHED"])
        calls = {"n": 0}
        async def intervening_waiter(mission):
            calls["n"] += 1
            if calls["n"] == 1:
                MissionEngine(self.store, None, None, None)\
                    .founder_intervened(mission["id"])
            return True
        eng.waiter = intervening_waiter
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_intervened")
        MissionEngine(self.store, None, None, None).resume(m["id"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "done")

    def test_10_founder_confirm_pending_pauses_not_completes(self):
        m = self._running(done_when=[
            {"tier": "contains_artifact", "check": "SHIPPED"},
            {"tier": "founder_confirm", "check": "founder approves"}])
        eng = self.engine(transcripts=["SHIPPED"])
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_confirm")

    def test_11_watch_template_never_says(self):
        m = self.store.create("watch session s-1", "watch")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        eng = self.engine()
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "running")
        self.assertEqual(self.says, [], "watch missions must not speak")

    def test_12_waiter_timeout_fails_not_hangs(self):
        m = self._running(done_when=[{"tier": "contains_artifact",
                                      "check": "NEVER"}])
        eng = self.engine(waiter_result=False)
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "failed")
        self.assertIn("timed out", self._last_note(m["id"]))

    def test_13_flag_dark_stops_the_loop(self):
        m = self._running()
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": False}))
        eng = self.engine()
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "stopped")

    def _last_note(self, mid):
        import shadow_ledger
        rows = [r for r in shadow_ledger.read("missions", 100)
                if r.get("mission_id") == mid]
        return rows[-1].get("note", "")


if __name__ == "__main__":
    unittest.main()
