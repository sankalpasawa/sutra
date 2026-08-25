"""PLAN-100 S51-S58: floors, delegation, scheduler cap/queue, feed emit."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import providers
import shadow_egress
import shadow_feed
from mission_engine import (MissionStore, MissionEngine, MissionScheduler,
                            emit_mission_feed)


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


class TestFloors(Base):
    def test_01_floor_patterns(self):
        self.assertEqual(shadow_egress.floor_check("run git push --force"),
                         ["d52_destructive_git"])
        self.assertEqual(shadow_egress.floor_check("edit ~/Claude/Paisa/app.py"),
                         ["d33_client_repo"])
        self.assertEqual(shadow_egress.floor_check("send the email to Benzy"),
                         ["irreversible_external_send"])
        self.assertEqual(shadow_egress.floor_check(
            "work in ~/Claude/asawa-holding/holding"), [])

    def test_02_floored_say_pauses_before_leaving_the_engine(self):
        m = self.store.create("clean the branch with git reset --hard", "fix")
        self.store.transition(m["id"], "brief_confirm")
        self.store.transition(m["id"], "running")
        said = []

        async def sayer(mission, text):
            said.append(text)
            return True

        async def waiter(mission):
            return True

        eng = MissionEngine(self.store, sayer, waiter, lambda m: "")
        out = asyncio.run(eng.run_mission(m["id"]))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "floor_confirm")
        self.assertEqual(said, [], "a floored say must never leave")
        self.assertIn("reset --hard", out["pending_floor_say"])


class TestDelegation(Base):
    def test_03_provision_once_idempotent(self):
        m = self.store.create("research X in a fresh session", "research",
                              target_mode="new")
        spawns = []

        async def spawner(mission):
            spawns.append(mission["id"])
            return "new-sess-1"

        eng = MissionEngine(self.store, None, None, None)
        sid = asyncio.run(eng.provision_target(m["id"], spawner))
        self.assertEqual(sid, "new-sess-1")
        sid2 = asyncio.run(eng.provision_target(m["id"], spawner))
        self.assertEqual(sid2, "new-sess-1")
        self.assertEqual(spawns, [m["id"]], "spawner runs exactly once")


class TestScheduler(Base):
    def _mission(self, i, session=None):
        m = self.store.create("objective %d" % i, "fix",
                              target_session=session)
        self.store.transition(m["id"], "brief_confirm")
        return m

    def test_04_cap_queue_promote_cancel(self):
        sched = MissionScheduler(self.store, max_running=2)
        m1, m2, m3, m4 = (self._mission(i) for i in range(4))
        self.assertEqual(sched.start(m1["id"])["state"], "running")
        self.assertEqual(sched.start(m2["id"])["state"], "running")
        self.assertEqual(sched.start(m3["id"])["state"], "queued")
        self.assertEqual(sched.start(m4["id"])["state"], "queued")
        self.store.transition(m1["id"], "done", "test")
        promoted = sched.on_terminal(m1["id"])
        self.assertEqual(promoted["id"], m3["id"], "FIFO promotion")
        self.assertEqual(sched.cancel_queued(m4["id"])["state"], "stopped")

    def test_05_one_mission_per_target_session(self):
        sched = MissionScheduler(self.store)
        m1 = self._mission(1, session="s-42")
        m2 = self._mission(2, session="s-42")
        sched.start(m1["id"])
        with self.assertRaises(ValueError):
            sched.start(m2["id"])

    def test_06_disambiguation_lists_every_pending_yes(self):
        sched = MissionScheduler(self.store)
        for i in range(2):
            m = self._mission(i)
            self.store.transition(m["id"], "running")
            mm = self.store.transition(m["id"], "paused", "test")
            mm["pause_reason"] = "founder_confirm"
            self.store.save(mm)
        pend = sched.pending_confirmations()
        self.assertEqual(len(pend), 2, "two pending -> ask Yes to which")


class TestFeedEmit(Base):
    def test_07_mission_event_becomes_feed_item_once(self):
        m = self.store.create("ship the fix", "fix")
        m["state"] = "paused"
        ok, problems = emit_mission_feed(m, "needs_decision",
                                         "floor requires confirmation")
        self.assertTrue(ok, problems)
        ok, problems = emit_mission_feed(m, "needs_decision", "again")
        self.assertFalse(ok, "same mission+state+version dedupes")
        m["version"] += 1
        ok, _ = emit_mission_feed(m, "needs_decision", "amended brief")
        self.assertTrue(ok, "an amend re-surfaces exactly once")


if __name__ == "__main__":
    unittest.main()
