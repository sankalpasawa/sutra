"""The 10 designed journeys as simulations (PRODUCT.md §4; designer intent:
functional journeys, simulable backends). This file is the MAP — each test
names its journey; deeper mechanics live in the suites it references.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import shadow_feed
import shadow_ledger
import shadow_precedence
from mission_engine import MissionStore, MissionScheduler
import session_runtime as srt
import shadow_runner


class TestJourneySims(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_u1_rescue_error_frame_becomes_feed_item(self):
        """U1 core: an error on a watched session surfaces to Now."""
        rt = srt.SessionRuntime()
        shadow_runner.attach_observer("sess-err-1", rt)
        # the observer path is exercised by pushing the frame it subscribes to
        for cb in rt.subscribers:
            cb({"type": "error", "detail": "socket died mid-answer"})
        import importlib, shadow_feed as sf
        importlib.reload(sf)
        items = []
        try:
            with open(sf._feed_path()) as fh:
                items = [json.loads(l) for l in fh if l.strip()]
        except OSError:
            pass
        self.assertTrue(any("rescue" in (i.get("item_id") or "")
                            for i in items), items)

    def test_u3_remember_inert_until_confirmed(self):
        """U3: captured -> inert; confirm -> in the replay context."""
        row = shadow_ledger.append("instructions", {
            "text": "outcome first", "precedence": "taste",
            "confirmed": False})
        ctx = shadow_precedence.replay_context(
            shadow_ledger.read("instructions", 50))
        self.assertNotIn("outcome first", ctx)
        confirmed = dict(row, confirmed=True); confirmed.pop("ts", None)
        shadow_ledger.append("instructions", confirmed)
        latest = {}
        for r in shadow_ledger.read("instructions", 50):
            latest[r["id"]] = r
        ctx = shadow_precedence.replay_context(list(latest.values()))
        self.assertIn("outcome first", ctx)

    def test_u4_supervise_stop_and_resume(self):
        """U4: one-tap stop; paused missions resume."""
        store = MissionStore()
        m = store.create("watchable work", "fix", target_session="s-1")
        store.transition(m["id"], "brief_confirm")
        store.transition(m["id"], "running")
        mm = store.transition(m["id"], "paused", "app restart sim")
        self.assertEqual(mm["state"], "paused")
        self.assertEqual(store.transition(m["id"], "running",
                                          "resume")["state"], "running")
        self.assertEqual(store.transition(m["id"], "stopped",
                                          "founder stop")["state"], "stopped")

    def test_failed_journey_reason_is_recorded(self):
        """Mission-failed: the stop reason survives to the ledger."""
        store = MissionStore()
        m = store.create("doomed", "fix", target_session="s-2")
        store.transition(m["id"], "brief_confirm")
        store.transition(m["id"], "running")
        store.transition(m["id"], "failed", "max turns (20) reached")
        rows = [r for r in shadow_ledger.read("missions", 50)
                if r.get("mission_id") == m["id"]]
        self.assertIn("max turns", rows[-1]["note"])

    def test_return_journey_feed_persists(self):
        """Return/catch-up: waiting cards survive (file-backed)."""
        ok, _ = shadow_feed.emit({
            "item_id": "wait-1", "producer": "shadow",
            "kind": "needs_decision", "title": "waiting for you",
            "deep_link": "sutra://shadow/m", "dedupe_key": "w1",
            "state": "new"})
        self.assertTrue(ok)
        import importlib, shadow_feed as sf2
        importlib.reload(sf2)     # a fresh process would re-read the file
        with open(sf2._feed_path()) as fh:
            self.assertTrue(any("wait-1" in l for l in fh))

    # Delegate (U2), floors (permission mid-mission), down-state, takeover and
    # the say chain are pinned END TO END in: test_shadow_runner.py,
    # test_mission_engine.py, test_shadow_say.py, test_shadow_overlay.js.
    # This file exists so every JOURNEY has a named simulation entry point.


if __name__ == "__main__":
    unittest.main()
