"""test_shadow_restart_resume.py -- what a restart does to missions, both halves.

recover_on_boot() pauses what the app cannot vouch for; resume_after_restart()
undoes that pause where it is safe, under the SAME admission rules as Start
(cap, one running mission per target). Unit-level: _launch and the runtime
re-attach are stubbed, so nothing spawns.
"""
import asyncio
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mission_engine  # noqa: E402
import shadow_ledger  # noqa: E402
import shadow_runner  # noqa: E402


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self.store = mission_engine.MissionStore()
        self._launch = shadow_runner._launch
        self._read = shadow_runner.session_reader.read_session
        self.launched = []
        shadow_runner._launch = lambda mid, vs, verifier: self.launched.append(mid)
        self.transcripts = set()
        shadow_runner.session_reader.read_session = (
            lambda sid: {"messages": []} if sid in self.transcripts else None)
        shadow_runner.RUNNING.clear()
        shadow_runner._ORPHANED.clear()
        self.ensured = []

    def tearDown(self):
        shadow_runner._launch = self._launch
        shadow_runner.session_reader.read_session = self._read
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    async def _ensure_ok(self, sid):
        self.ensured.append(sid)
        return object()

    async def _ensure_fail(self, sid):
        self.ensured.append(sid)
        raise RuntimeError("no such runtime")

    def _running(self, template="fix", target_mode="existing", sid=None):
        m = self.store.create("objective", template, target_mode=target_mode,
                              target_session=sid)
        self.store.transition(m["id"], "brief_confirm", "t")
        return self.store.transition(m["id"], "running", "t")

    def _paused(self, template="fix", target_mode="existing", sid=None,
                reason="app_restart"):
        m = self._running(template, target_mode, sid)
        m = self.store.transition(m["id"], "paused", "t")
        m["pause_reason"] = reason
        self.store.save(m)
        return m

    def _resume(self, ensure=None):
        return asyncio.run(shadow_runner.resume_after_restart(
            ensure or self._ensure_ok, lambda *a, **k: True))

    def _state(self, mid):
        return self.store.load(mid)["state"]

    def _notes(self, mid):
        return [r["note"] for r in shadow_ledger.read("missions", 200)
                if r.get("mission_id") == mid]


class RecoverOnBoot(Base):

    def test_10_watch_mission_survives_the_restart(self):
        w = self._running("watch", "existing", "chat-w")
        f = self._running("fix", "existing", "chat-f")
        shadow_runner.recover_on_boot()
        self.assertEqual(self._state(w["id"]), "running")
        self.assertEqual(self._state(f["id"]), "paused")
        self.assertEqual(self.store.load(f["id"])["pause_reason"], "app_restart")
        self.assertIn("survived app restart (watch: no loop to lose)",
                      self._notes(w["id"]))


class ResumeAfterRestart(Base):

    def test_20_watch_paused_by_a_restart_resumes_without_a_launch(self):
        w = self._paused("watch", "existing", "chat-w")
        out = self._resume()
        self.assertEqual(self._state(w["id"]), "running")
        self.assertEqual(out["resumed"], [w["id"]])
        self.assertEqual(self.launched, [])
        self.assertEqual(self.ensured, [])

    def test_21_existing_target_with_a_transcript_reattaches_and_launches(self):
        self.transcripts.add("chat-1")
        m = self._paused("fix", "existing", "chat-1")
        out = self._resume()
        self.assertEqual(self.ensured, ["chat-1"])
        self.assertEqual(self._state(m["id"]), "running")
        self.assertEqual(self.launched, [m["id"]])
        self.assertEqual(out["resumed"], [m["id"]])
        self.assertIn("resumed after restart", self._notes(m["id"]))

    def test_22_missing_transcript_stays_paused_and_never_reattaches(self):
        m = self._paused("fix", "existing", "floor-choke-session")
        out = self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.ensured, [])
        self.assertEqual(self.launched, [])
        self.assertEqual(out["left"], [m["id"]])
        self.assertTrue(any("transcript" in n for n in self._notes(m["id"])))

    def test_23_delegate_stays_fenced(self):
        self.transcripts.add("delegate-1")
        m = self._paused("fix", "new", "delegate-1")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.ensured, [])
        self.assertTrue(any("fenced" in n for n in self._notes(m["id"])))

    def test_24_cap_is_honored(self):
        for i in range(mission_engine.MAX_RUNNING):
            self._running("fix", "existing", "busy-%d" % i)
        self.transcripts.add("chat-1")
        m = self._paused("fix", "existing", "chat-1")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.ensured, [])
        self.assertTrue(any("cap" in n for n in self._notes(m["id"])))

    def test_25_one_running_mission_per_target(self):
        self.transcripts.add("chat-1")
        self._running("fix", "existing", "chat-1")
        m = self._paused("fix", "existing", "chat-1")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.launched, [])
        self.assertTrue(any("already has a running mission" in n
                            for n in self._notes(m["id"])))

    def test_26_two_paused_for_one_target_resume_only_the_oldest(self):
        self.transcripts.add("chat-1")
        a = self._paused("fix", "existing", "chat-1")
        b = self._paused("fix", "existing", "chat-1")
        out = self._resume()
        self.assertEqual(out["resumed"], [a["id"]])
        self.assertEqual(self._state(b["id"]), "paused")

    def test_27_founder_pauses_are_never_touched(self):
        self.transcripts.add("chat-1")
        m = self._paused("fix", "existing", "chat-1", reason="founder_intervened")
        c = self._paused("fix", "existing", "chat-2", reason="founder_confirm")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self._state(c["id"]), "paused")
        self.assertEqual(self.ensured, [])

    def test_28_a_failed_reattach_leaves_it_paused_with_the_reason(self):
        self.transcripts.add("chat-1")
        m = self._paused("fix", "existing", "chat-1")
        self._resume(self._ensure_fail)
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.launched, [])
        self.assertTrue(any("could not re-attach" in n for n in self._notes(m["id"])))


if __name__ == "__main__":
    unittest.main()
