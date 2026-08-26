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

    def test_u3_boot_replay_confirmed_only(self):
        """U3 applied-thereafter: boot context carries confirmed rows only."""
        import shadow_session
        shadow_ledger.append("instructions", {
            "text": "never say maybe", "precedence": "taste",
            "confirmed": True})
        shadow_ledger.append("instructions", {
            "text": "unconfirmed wish", "precedence": "taste",
            "confirmed": False})
        shadow_ledger.append("actions", {
            "mission_id": "m-x", "kind": "say", "summary": "did a thing"})
        ctx = shadow_session.standing_context()
        self.assertIn("never say maybe", ctx)
        self.assertNotIn("unconfirmed wish", ctx)
        self.assertIn("RECENT SHADOW ACTIONS", ctx)
        self.assertIn("did a thing", ctx)

    def test_u1_stall_detection(self):
        """U1: a silent running mission raises ONE deduped stall item."""
        store = MissionStore()
        m = store.create("quiet work", "fix", target_session="sess-stall")
        store.transition(m["id"], "brief_confirm")
        store.transition(m["id"], "running")
        shadow_runner._LAST_FRAME_TS["sess-stall"] = 100.0
        raised = shadow_runner.check_stalls(now=1000.0, stall_secs=240)
        self.assertEqual(raised, [m["id"]])
        self.assertEqual(
            shadow_runner.check_stalls(now=2000.0, stall_secs=240), [],
            "dedupe: one stall alert per mission")
        import importlib, shadow_feed as sf
        importlib.reload(sf)
        with open(sf._feed_path()) as fh:
            self.assertTrue(any("stall-%s" % m["id"] in l for l in fh))

    def test_failed_retry_clones_fresh_mission(self):
        """Mission-failed journey: Retry = same brief, NEW target."""
        from mission_engine import clone_for_retry
        store = MissionStore()
        m = store.create("doomed again", "fix", target_session="s-dead",
                         done_when=[{"tier": "auto", "check": "x", "met": True}])
        store.transition(m["id"], "brief_confirm")
        store.transition(m["id"], "running")
        store.transition(m["id"], "failed", "say refused")
        clone = clone_for_retry(store, m["id"])
        self.assertEqual(clone["state"], "brief_confirm")
        self.assertEqual(clone["objective"], "doomed again")
        self.assertIsNone(clone.get("target_session"))
        self.assertEqual(clone["target_mode"], "new")
        self.assertNotIn("met", clone["done_when"][0])
        live = store.create("still running", "fix", target_session="s-live")
        store.transition(live["id"], "brief_confirm")
        store.transition(live["id"], "running")
        with self.assertRaises(ValueError):
            clone_for_retry(store, live["id"])

    def test_retry_is_idempotent_while_clone_lives(self):
        from mission_engine import clone_for_retry
        store = MissionStore()
        m = store.create("flaky", "fix", target_session="s-a")
        store.transition(m["id"], "brief_confirm")
        store.transition(m["id"], "running")
        store.transition(m["id"], "failed", "boom")
        first = clone_for_retry(store, m["id"])
        with self.assertRaises(ValueError):
            clone_for_retry(store, m["id"])
        store.transition(first["id"], "queued")
        store.transition(first["id"], "running")
        store.transition(first["id"], "failed", "boom again")
        second = clone_for_retry(store, m["id"])
        self.assertNotEqual(second["id"], first["id"])

    def test_stall_grace_for_silent_from_birth_session(self):
        store = MissionStore()
        m = store.create("mute", "fix", target_session="sess-mute")
        store.transition(m["id"], "brief_confirm")
        store.transition(m["id"], "running")
        shadow_runner._LAST_FRAME_TS.pop("sess-mute", None)
        self.assertEqual(shadow_runner.check_stalls(now=5000.0), [],
                         "first sweep stamps, never alerts")
        raised = shadow_runner.check_stalls(now=5000.0 + 241)
        self.assertEqual(raised, [m["id"]])

    def test_boot_context_degrades_loudly(self):
        import shadow_session
        from unittest import mock
        with mock.patch.object(shadow_session, "standing_context",
                               wraps=shadow_session.standing_context):
            with mock.patch("shadow_ledger.read",
                            side_effect=OSError("ledger torn")):
                ctx = shadow_session.standing_context()
        self.assertIn("standing instructions unavailable", ctx)
        self.assertIn("ledger torn", ctx)

    def test_feed_retirement_on_open(self):
        """Observations pass: opening retires; idempotent; emit survives."""
        ok, _ = shadow_feed.emit({
            "item_id": "ret-1", "producer": "shadow",
            "kind": "needs_decision", "title": "retire me",
            "deep_link": "sutra://shadow/home", "dedupe_key": "r1",
            "state": "new"})
        self.assertTrue(ok)
        self.assertTrue(shadow_feed.mark_handled("ret-1"))
        self.assertFalse(shadow_feed.mark_handled("ret-1"),
                         "second handle is a no-op")
        ok2, _ = shadow_feed.emit({
            "item_id": "ret-2", "producer": "shadow",
            "kind": "info", "title": "after the rewrite",
            "deep_link": "sutra://shadow/home", "dedupe_key": "r2",
            "state": "new"})
        self.assertTrue(ok2, "emit still works after a rewrite")
        import importlib, shadow_feed as sf
        importlib.reload(sf)
        states = {}
        with open(sf._feed_path()) as fh:
            for line in fh:
                import json as _j
                row = _j.loads(line)
                states[row["item_id"]] = row["state"]
        self.assertEqual(states["ret-1"], "handled")
        self.assertEqual(states["ret-2"], "new")

    def test_scoped_instruction_never_enters_the_global_boot(self):
        """THE leak test (recon risk #1): a confirmed CHAT-scoped rule must
        not appear in Shadow's boot context, and a global one must."""
        import shadow_session
        shadow_ledger.append("instructions", {
            "text": "global rule visible everywhere", "precedence": "taste",
            "confirmed": True, "scope": "global", "scope_id": None})
        shadow_ledger.append("instructions", {
            "text": "paisa only rule", "precedence": "taste",
            "confirmed": True, "scope": "chat", "scope_id": "sess-paisa"})
        ctx = shadow_session.standing_context()
        self.assertIn("global rule visible everywhere", ctx)
        self.assertNotIn("paisa only rule", ctx)

    def test_legacy_rows_are_grandfathered_global(self):
        """A row written before v10 carries no scope: it stays global."""
        import shadow_session
        shadow_ledger.append("instructions", {
            "text": "legacy standing rule", "precedence": "taste",
            "confirmed": True})
        self.assertIn("legacy standing rule",
                      shadow_session.standing_context())

    def test_scoped_replay_returns_only_that_chat(self):
        rows = [
            {"text": "A", "precedence": "taste", "confirmed": True,
             "scope": "chat", "scope_id": "s-1"},
            {"text": "B", "precedence": "taste", "confirmed": True,
             "scope": "chat", "scope_id": "s-2"},
            {"text": "C", "precedence": "taste", "confirmed": True,
             "scope": "global"},
        ]
        one = shadow_precedence.replay_context(rows, scope="chat",
                                               scope_id="s-1")
        self.assertIn("A", one)
        self.assertNotIn("B", one)
        self.assertNotIn("C", one)
        glob = shadow_precedence.replay_context(rows, scope="global")
        self.assertIn("C", glob)
        self.assertNotIn("A", glob)

    def test_window_starvation_cannot_evict_a_global_rule(self):
        """codex P1: 250 per-chat rows after one global rule -- the global
        rule must still reach the boot context, and the FIRST row must
        still be findable by id (revokeable)."""
        import shadow_session
        first = shadow_ledger.append("instructions", {
            "text": "the one global rule", "precedence": "taste",
            "confirmed": True, "scope": "global", "scope_id": None})
        for i in range(250):
            shadow_ledger.append("instructions", {
                "text": "chat rule %d" % i, "precedence": "taste",
                "confirmed": True, "scope": "chat",
                "scope_id": "sess-%d" % (i % 7)})
        ctx = shadow_session.standing_context()
        self.assertIn("the one global rule", ctx)
        self.assertNotIn("chat rule 249", ctx)
        rows = [r for r in shadow_ledger.read_latest("instructions")
                if r.get("id") == first["id"]]
        self.assertEqual(len(rows), 1, "old row still findable by id")

    # Delegate (U2), floors (permission mid-mission), down-state, takeover and
    # the say chain are pinned END TO END in: test_shadow_runner.py,
    # test_mission_engine.py, test_shadow_say.py, test_shadow_overlay.js.
    # This file exists so every JOURNEY has a named simulation entry point.


if __name__ == "__main__":
    unittest.main()
