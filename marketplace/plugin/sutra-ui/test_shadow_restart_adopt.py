#!/usr/bin/env python3
"""A restart must not turn a healthy Shadow mission into a founder chore.

THE BUG (founder, 2026-09-15, mission m-55c220d58b1a). A mission driving
itself -- four consecutive `continue` decisions, no question asked of anyone
-- stopped dead because the uvicorn app restarted under it. recover_on_boot
paused it (`app_restart`), and resume_after_restart fenced EVERY delegate
regardless of whether anything was still writing its transcript. The founder
had to press Resume on work that had nothing wrong with it. Empirically the
worker is usually already gone: the delegate behind that mission left no
process at all.

WHY IT WAS FENCED, AND WHY THAT WAS RIGHT. A delegate spawns with
process_group=0, so its Claude process outlives the app, and Electron
SIGKILLs the uvicorn child on quit so shutdown() often never reaps it. The
runtime's pipes die with the parent and cannot be re-acquired by ANY later
process, so the only way back into that conversation is `claude --resume
<sid>` -- a SECOND process on one transcript. Safe only if the first is
dead, and nothing on disk could say whether it was.

WHAT CHANGED: the answer is knowable now. The spawn records its pid on the
mission (`delegate_pid`), and delegate_alive() asks about that pid, checking
argv too so a recycled pid cannot read as alive. Dead -> adopt through the
same path an existing-target mission already takes. Alive, unknown, or any
probe that failed -> the historical fence, unchanged.

Run: python3 test_shadow_restart_adopt.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import shadow_ledger
import shadow_runner
from mission_engine import MissionStore


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Base(unittest.TestCase):

    def setUp(self):
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig_settings = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()

        self.launched = []
        self.adopted = []
        self.reattached = []
        self.transcripts = set()

        self._orig_launch = shadow_runner._launch
        self._orig_read = shadow_runner.session_reader.read_session
        self._orig_alive = shadow_runner.delegate_alive
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)
        shadow_runner.session_reader.read_session = (
            lambda sid: {"id": sid} if sid in self.transcripts else None)

    def tearDown(self):
        shadow_runner._launch = self._orig_launch
        shadow_runner.session_reader.read_session = self._orig_read
        shadow_runner.delegate_alive = self._orig_alive
        providers.SETTINGS_PATH = self._orig_settings
        shadow_runner.DELEGATE_PIDS.clear()
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ---- fixtures -------------------------------------------------------
    def _paused_delegate(self, sid="d-1", pid=4242, reason="app_restart"):
        m = self.store.create("objective", "fix", target_mode="new",
                              target_session=sid)
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        m = self.store.transition(m["id"], "paused", "t")
        m["pause_reason"] = reason
        if pid is not None:
            m["delegate_pid"] = pid
        self.store.save(m)
        self.transcripts.add(sid)
        return m

    async def _adopt_ok(self, sid):
        self.adopted.append(sid)
        return object()

    async def _reattach_ok(self, sid):
        self.reattached.append(sid)
        return object()

    def _resume(self, adopt=True):
        return run(shadow_runner.resume_after_restart(
            self._reattach_ok, lambda *a, **k: True,
            ensure_delegate_async=(self._adopt_ok if adopt else None)))

    def _state(self, mid):
        return self.store.load(mid)["state"]

    def _notes(self, mid):
        return [r["note"] for r in shadow_ledger.read("missions", 300)
                if r.get("mission_id") == mid]

    def _dead(self):
        shadow_runner.delegate_alive = lambda pid, sid=None: False

    def _alive(self):
        shadow_runner.delegate_alive = lambda pid, sid=None: True


# =============================== 1, 2, 3: the healthy restart ============
class TestHealthyMissionResumes(Base):

    def test_01_a_healthy_delegate_resumes_automatically(self):
        self._dead()
        m = self._paused_delegate()
        out = self._resume()
        self.assertEqual(self._state(m["id"]), "running",
                         "a restart must not leave healthy work paused")
        self.assertIn(m["id"], out["resumed"])
        self.assertIn(m["id"], self.launched, "the loop must be relaunched")
        self.assertTrue(any("re-adopted" in n for n in self._notes(m["id"])))

    def test_02_no_second_worker_is_spawned(self):
        """Adoption goes through ensure_runtime (`claude --resume <sid>`),
        which is ONE process for the session, never a fresh delegate."""
        self._dead()
        m = self._paused_delegate(sid="d-nospawn")
        self._resume()
        self.assertEqual(self.adopted, ["d-nospawn"],
                         "exactly one re-entry, through the resume primitive")
        self.assertEqual(self.reattached, [],
                         "a delegate must not go through the existing-target "
                         "builder: wrong argv, wrong tool scope")

    def test_03_the_SAME_session_is_retained(self):
        self._dead()
        m = self._paused_delegate(sid="d-same")
        self._resume()
        after = self.store.load(m["id"])
        self.assertEqual(after["target_session"], "d-same",
                         "the worker session must be retained, not replaced")
        self.assertEqual(after["target_mode"], "new")
        self.assertEqual(self.adopted, ["d-same"])


# =============================== 4, 5, 6: everything else is untouched ===
class TestOtherStatesUnmoved(Base):

    def _mission_in(self, state, **fields):
        m = self.store.create("objective", "fix", target_mode="new",
                              target_session="s-x")
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        if state != "running":
            m = self.store.transition(m["id"], state, "t")
        for k, v in fields.items():
            m[k] = v
        self.store.save(m)
        return m

    def test_04_a_blocked_mission_stays_blocked(self):
        """needs-founder is a DECISION. A restart must never answer it."""
        self._dead()
        m = self._mission_in("blocked", block_reason="needs_founder")
        self._resume()
        after = self.store.load(m["id"])
        self.assertEqual(after["state"], "blocked")
        self.assertEqual(after["block_reason"], "needs_founder")
        self.assertNotIn(m["id"], self.launched)

    def test_05_a_founder_stopped_mission_stays_stopped(self):
        self._dead()
        m = self._mission_in("stopped", ended_by="founder")
        self._resume()
        after = self.store.load(m["id"])
        self.assertEqual(after["state"], "stopped")
        self.assertEqual(after["ended_by"], "founder")
        self.assertNotIn(m["id"], self.launched)

    def test_06_a_failed_mission_stays_failed(self):
        self._dead()
        m = self._mission_in("failed")
        self._resume()
        self.assertEqual(self._state(m["id"]), "failed")
        self.assertNotIn(m["id"], self.launched)

    def test_06b_a_FOUNDER_pause_is_never_adopted(self):
        """founder_confirm / floor_confirm / founder_intervened are decisions
        waiting on a human. Only `app_restart` is machine trouble."""
        self._dead()
        for reason in ("founder_confirm", "floor_confirm",
                       "founder_intervened"):
            m = self._paused_delegate(sid="d-" + reason, reason=reason)
            self._resume()
            self.assertEqual(self._state(m["id"]), "paused", reason)
            self.assertNotIn(m["id"], self.launched, reason)


# =============================== 7: the fence still holds ===============
class TestFenceStillHolds(Base):

    def test_07_a_LIVE_worker_is_never_adopted(self):
        """The single-writer invariant: a second `claude --resume` on a
        transcript something is still writing is the one thing this fence
        exists to prevent."""
        self._alive()
        m = self._paused_delegate(sid="d-live")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.adopted, [], "a live worker was adopted")
        self.assertNotIn(m["id"], self.launched)
        self.assertTrue(any("still alive" in n for n in self._notes(m["id"])))

    def test_07b_no_recorded_pid_keeps_the_HISTORICAL_fence(self):
        """A mission created before the pid was stamped cannot be vouched
        for, so it behaves exactly as it did before this shipped."""
        shadow_runner.delegate_alive = self._orig_alive   # the real probe
        m = self._paused_delegate(pid=None)
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.adopted, [])

    def test_07c_delegate_alive_fails_CLOSED(self):
        """Every uncertainty must read as 'alive'. A wrong 'alive' costs one
        Resume click; a wrong 'dead' puts two writers on one transcript."""
        self.assertTrue(shadow_runner.delegate_alive(None),
                        "no pid must read as alive")
        self.assertTrue(shadow_runner.delegate_alive(0))
        self.assertTrue(shadow_runner.delegate_alive("not-a-pid"))
        # our own pid IS alive, and argv will not mention this fake session
        self.assertTrue(shadow_runner.delegate_alive(os.getpid()),
                        "a live pid with no session id to check reads alive")

    def test_07d_a_RECYCLED_pid_is_not_mistaken_for_the_delegate(self):
        """A live pid whose argv does not carry the session id is a recycled
        number -- the delegate it once named is gone."""
        self.assertFalse(
            shadow_runner.delegate_alive(os.getpid(),
                                         "sid-that-is-not-in-our-argv"),
            "a recycled pid must not fence a mission forever")

    def test_07e_a_dead_pid_is_provably_dead(self):
        """A pid nothing owns reads as dead, which is what unfences."""
        self.assertFalse(shadow_runner.delegate_alive(999999, "any-sid"))

    def test_07f_a_missing_transcript_is_never_adopted(self):
        self._dead()
        m = self._paused_delegate(sid="d-gone")
        self.transcripts.discard("d-gone")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.adopted, [])

    def test_07g_a_failed_re_entry_leaves_it_paused_with_the_reason(self):
        self._dead()
        m = self._paused_delegate(sid="d-boom")

        async def _boom(sid):
            raise RuntimeError("resume refused")
        out = run(shadow_runner.resume_after_restart(
            self._reattach_ok, lambda *a, **k: True,
            ensure_delegate_async=_boom))
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertIn(m["id"], out["left"])
        self.assertTrue(any("could not re-adopt" in n
                            for n in self._notes(m["id"])))

    def test_07h_admission_rules_still_bind(self):
        """Adoption is not a way around the cap."""
        self._dead()
        for i in range(mission_engine.MAX_RUNNING):
            mm = self.store.create("o%d" % i, "fix", target_mode="existing",
                                   target_session="busy-%d" % i)
            self.store.transition(mm["id"], "brief_confirm", "t")
            self.store.transition(mm["id"], "running", "t")
        m = self._paused_delegate(sid="d-capped")
        self._resume()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertTrue(any("cap" in n for n in self._notes(m["id"])))


# =============================== the pid stamp ==========================
class TestPidIsRecorded(Base):

    def test_08_remember_delegate_pid_stamps_the_mission(self):
        m = self.store.create("o", "fix", target_mode="new",
                              target_session="d-pid")
        shadow_runner.DELEGATE_PIDS["d-pid"] = 31337
        shadow_runner.remember_delegate_pid(self.store, m["id"])
        self.assertEqual(self.store.load(m["id"])["delegate_pid"], 31337)

    def test_08b_it_is_idempotent_and_never_overwrites(self):
        m = self.store.create("o", "fix", target_mode="new",
                              target_session="d-pid2")
        m["delegate_pid"] = 111
        self.store.save(m)
        shadow_runner.DELEGATE_PIDS["d-pid2"] = 222
        shadow_runner.remember_delegate_pid(self.store, m["id"])
        self.assertEqual(self.store.load(m["id"])["delegate_pid"], 111,
                         "the first pid is the one that spawned it")

    def test_08c_no_pid_known_stamps_nothing_and_never_raises(self):
        m = self.store.create("o", "fix", target_mode="new",
                              target_session="d-nopid")
        shadow_runner.remember_delegate_pid(self.store, m["id"])
        self.assertNotIn("delegate_pid", self.store.load(m["id"]))
        shadow_runner.remember_delegate_pid(self.store, "m-does-not-exist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
