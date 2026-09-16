#!/usr/bin/env python3
"""Two Shadow backends, one home: only one of them gets to recover it.

THE GAP (founder, 2026-09-16). Nothing stopped two uvicorn backends from
booting against one shadow home, and the boot block rewrites the shared
mission store before any mission loop exists. The per-mission `loop_pid` lease
cannot see that far back: it is consulted in _launch, and the two worst steps
happen earlier --

  * _clear_stale_start_requests() erases a `start_requested_at` the OTHER
    process has in flight;
  * boot drain_queue -> provision_target, which returns early on
    `target_session` BEFORE it awaits the spawner, and the spawner waits out a
    whole first agentic turn -- so two boots both pass the check and both
    spawn a real delegate for one mission.

So recovery takes a lease on the home (shadow_home_lock), and a backend that
does not hold it stands down instead of seizing missions it cannot see.

WHY A REAL SECOND PROCESS IN HERE. The guard is self-arming: it claims the
lease itself rather than requiring a pre-claim, which is what lets all 44
existing Shadow lanes keep passing untouched on their own temp homes. The
cost of that choice is that every one of them acquires trivially, so the
REFUSAL branch -- the entire point of this work -- would otherwise be
exercised by nothing. Tests 08-10 and 13 hold a real subprocess against the
lock file. There is deliberately no _force_ownership() test hook; a fake
holder would only prove the fake works.

Run: python3 test_shadow_home_lock.py
"""

import asyncio
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import providers
import shadow_home_lock
import shadow_ledger
import shadow_runner
from mission_engine import MissionStore


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    """The temp-home + settings fixture every Shadow lane rebuilds, plus a
    release in teardown: this is the one suite that holds a real lease."""

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
        self.transcripts = set()
        self._holder = None

        self._orig_launch = shadow_runner._launch
        self._orig_read = shadow_runner.session_reader.read_session
        self._orig_alive = shadow_runner.delegate_alive
        shadow_runner._launch = lambda mid, *a, **k: self.launched.append(mid)
        shadow_runner.session_reader.read_session = (
            lambda sid: {"id": sid} if sid in self.transcripts else None)
        shadow_runner.delegate_alive = lambda pid, sid=None: False

    def tearDown(self):
        self._stop_holder()
        shadow_home_lock.release_recovery()
        shadow_home_lock._REARM["task"] = None
        shadow_home_lock._REARM["done"] = False
        shadow_runner._launch = self._orig_launch
        shadow_runner.session_reader.read_session = self._orig_read
        shadow_runner.delegate_alive = self._orig_alive
        providers.SETTINGS_PATH = self._orig_settings
        shadow_runner.RUNNING.clear()
        shadow_runner._ORPHANED.clear()
        shadow_runner.DELEGATE_PIDS.clear()
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ---- a real rival ---------------------------------------------------
    def _start_holder(self):
        """A SEPARATE PROCESS holding the lease, the way a second backend
        would. Returns its pid once the lock is provably taken."""
        ready = os.path.join(self.tmp.name, "holder-ready")
        code = textwrap.dedent("""
            import fcntl, os, sys, time
            path, ready = sys.argv[1], sys.argv[2]
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, (
                '{"pid": %d, "build": "test-holder"}' % os.getpid()
            ).encode())
            os.fsync(fd)
            open(ready, "w").write(str(os.getpid()))
            time.sleep(120)
        """)
        path = os.path.join(os.path.realpath(self.tmp.name),
                            shadow_home_lock.LOCK_NAME)
        self._holder = subprocess.Popen(
            [sys.executable, "-c", code, path, ready],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(200):                       # up to 10s
            if os.path.exists(ready):
                return self._holder.pid
            time.sleep(0.05)
        self.fail("the holder process never took the lock")

    def _stop_holder(self):
        if self._holder is None:
            return
        try:
            self._holder.kill()
            self._holder.wait(timeout=10)
        except Exception:                          # noqa: BLE001
            pass
        self._holder = None

    # ---- mission fixtures ------------------------------------------------
    def _running_delegate(self, sid="d-1"):
        m = self.store.create("objective", "fix", target_mode="new",
                              target_session=sid)
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        self.transcripts.add(sid)
        return m

    def _paused_delegate(self, sid="d-1", pid=4242):
        m = self._running_delegate(sid)
        m = self.store.transition(m["id"], "paused", "t")
        m["pause_reason"] = "app_restart"
        m["delegate_pid"] = pid
        self.store.save(m)
        return m

    async def _adopt_ok(self, sid, permission_mode=None):
        self.adopted.append(sid)
        return object()

    async def _reattach_ok(self, sid):
        return object()

    def _resume(self):
        return run(shadow_runner.resume_after_restart(
            self._reattach_ok, lambda *a, **k: True,
            ensure_delegate_async=self._adopt_ok))

    def _state(self, mid):
        return self.store.load(mid)["state"]

    def _mission_notes(self):
        return [r.get("note") or "" for r in shadow_ledger.read("missions", 300)]


# ======================================== 1-7: the lease itself ==========
class TestRecoveryLease(Base):

    def test_01_the_first_claim_wins_and_records_who_took_it(self):
        owned, holder = shadow_home_lock.claim_recovery()
        self.assertTrue(owned)
        self.assertIsNone(holder, "nobody refused us")
        self.assertTrue(shadow_home_lock.holds_recovery())
        rec = shadow_home_lock.recovery_holder()
        self.assertEqual(rec["pid"], os.getpid())
        self.assertEqual(rec["build"], shadow_ledger.build_id())
        self.assertTrue(os.path.exists(
            os.path.join(os.path.realpath(self.tmp.name),
                         shadow_home_lock.LOCK_NAME)))

    def test_02_claiming_twice_is_idempotent_and_leaks_no_fd(self):
        self.assertTrue(shadow_home_lock.claim_recovery()[0])
        fd = shadow_home_lock._LOCK["fd"]
        for _ in range(5):
            self.assertTrue(shadow_home_lock.claim_recovery()[0])
        self.assertEqual(shadow_home_lock._LOCK["fd"], fd,
                         "a repeat claim must reuse the fd, not open another")

    def test_03_a_foreign_fd_holding_the_lock_refuses_us(self):
        """macOS flock conflicts across two fds in ONE process, so this is the
        real kernel mechanism, not a stub of it."""
        path = os.path.join(os.path.realpath(self.tmp.name),
                            shadow_home_lock.LOCK_NAME)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            owned, _holder = shadow_home_lock.claim_recovery()
            self.assertFalse(owned)
            self.assertFalse(shadow_home_lock.holds_recovery())
        finally:
            os.close(fd)

    def test_04_the_holder_record_is_advisory_and_readable(self):
        pid = self._start_holder()
        owned, holder = shadow_home_lock.claim_recovery()
        self.assertFalse(owned)
        self.assertIsNotNone(holder, "a refusal must name who refused")
        self.assertEqual(holder["pid"], pid)

    def test_05_release_frees_it_for_the_next_claim(self):
        self.assertTrue(shadow_home_lock.claim_recovery()[0])
        shadow_home_lock.release_recovery()
        self.assertFalse(shadow_home_lock.holds_recovery())
        self.assertIsNone(shadow_home_lock._LOCK["fd"])
        self.assertTrue(shadow_home_lock.claim_recovery()[0])

    def test_06_switching_home_releases_the_old_one(self):
        self.assertTrue(shadow_home_lock.claim_recovery()[0])
        first = shadow_home_lock._LOCK["home"]
        other = tempfile.TemporaryDirectory()
        try:
            os.environ["SUTRA_SHADOW_HOME"] = other.name
            self.assertTrue(shadow_home_lock.claim_recovery()[0])
            self.assertTrue(shadow_home_lock.holds_recovery())
            self.assertNotEqual(shadow_home_lock._LOCK["home"], first)
            # and the first home is genuinely free again
            fd = os.open(os.path.join(first, shadow_home_lock.LOCK_NAME),
                         os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        finally:
            os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
            shadow_home_lock.release_recovery()
            other.cleanup()

    def test_07_a_garbage_lock_record_does_not_raise(self):
        """The record is advisory; a torn write must not blind the decision."""
        os.makedirs(os.path.realpath(self.tmp.name), exist_ok=True)
        with open(os.path.join(os.path.realpath(self.tmp.name),
                               shadow_home_lock.LOCK_NAME), "w") as fh:
            fh.write("{not json at all")
        self.assertIsNone(shadow_home_lock.recovery_holder())
        self.assertTrue(shadow_home_lock.claim_recovery()[0],
                        "garbage in the file is not a rival")

    def test_07b_realpath_not_the_raw_env_string(self):
        """macOS mkdtemp hands back /var/... whose realpath is /private/var/...
        Comparing raw strings would make one home look like two, and every
        needless re-acquire is a window where nobody holds it."""
        self.assertTrue(shadow_home_lock.claim_recovery()[0])
        fd = shadow_home_lock._LOCK["fd"]
        os.environ["SUTRA_SHADOW_HOME"] = os.path.realpath(self.tmp.name)
        self.assertTrue(shadow_home_lock.claim_recovery()[0])
        self.assertEqual(shadow_home_lock._LOCK["fd"], fd,
                         "same home by realpath -- must not re-acquire")


# ============================ 8-13: a second instance cannot seize ========
class TestSecondInstanceCannotSeize(Base):

    def test_08_recover_on_boot_leaves_missions_alone(self):
        m = self._running_delegate()
        pid = self._start_holder()

        shadow_runner.recover_on_boot()

        self.assertEqual(self._state(m["id"]), "running",
                         "a second instance must not pause work the owner "
                         "is driving")
        self.assertNotIn("d-1", shadow_runner._ORPHANED,
                         "and must not fence a session it does not own")
        self.assertTrue(any(str(pid) in n for n in self._mission_notes()),
                        "the stand-down must name the holder")

    def test_09_resume_after_restart_adopts_nothing(self):
        m = self._paused_delegate()
        self._start_holder()

        out = self._resume()

        self.assertEqual(out, {"resumed": [], "left": []})
        self.assertEqual(self.adopted, [],
                         "re-entry is `claude --resume` -- a second process "
                         "must never start one on the owner's transcript")
        self.assertEqual(self.launched, [])
        self.assertEqual(self._state(m["id"]), "paused")

    def test_10_the_refusal_is_on_the_record(self):
        self._paused_delegate()
        pid = self._start_holder()
        self._resume()
        notes = self._mission_notes()
        self.assertTrue(any("re-adoption skipped" in n for n in notes), notes)
        self.assertTrue(any(str(pid) in n for n in notes), notes)

    def test_11_regression_the_owner_still_pauses_running_missions(self):
        """The guard must not have changed the path it guards."""
        m = self._running_delegate()
        shadow_runner.recover_on_boot()
        self.assertEqual(self._state(m["id"]), "paused")
        self.assertEqual(self.store.load(m["id"])["pause_reason"],
                         "app_restart")
        self.assertIn("d-1", shadow_runner._ORPHANED)

    def test_12_regression_the_owner_still_re_adopts(self):
        m = self._paused_delegate()
        out = self._resume()
        self.assertEqual(out["resumed"], [m["id"]])
        self.assertEqual(self.adopted, ["d-1"])
        self.assertEqual(self._state(m["id"]), "running")

    def test_13_the_lease_is_reclaimable_once_the_holder_dies(self):
        """A SIGKILLed backend leaves no stale lock -- the kernel drops the
        flock with the process. This is the whole reason it is not a pidfile,
        and the precondition the re-arm depends on."""
        m = self._paused_delegate()
        self._start_holder()
        self.assertFalse(shadow_home_lock.claim_recovery()[0])

        self._stop_holder()                        # SIGKILL, no clean release

        owned, _ = shadow_home_lock.claim_recovery()
        self.assertTrue(owned, "a dead holder must not fence the home")
        out = self._resume()
        self.assertEqual(out["resumed"], [m["id"]],
                         "and recovery must actually run once we win it")

    def test_13b_the_rearm_runs_recovery_exactly_once_on_a_win(self):
        """A refusal is not permanent: _shadow_recover is the only caller and
        runs once, so without this a stood-down backend never recovers."""
        calls = []

        async def _recovery():
            calls.append(1)

        self._start_holder()
        self.assertFalse(shadow_home_lock.claim_recovery()[0])

        async def _drive():
            shadow_home_lock.start_rearm(_recovery, interval=0.05)
            shadow_home_lock.start_rearm(_recovery, interval=0.05)   # singleton
            await asyncio.sleep(0.2)
            self.assertEqual(calls, [], "must not fire while a rival holds it")
            self._stop_holder()
            for _ in range(100):
                if calls:
                    break
                await asyncio.sleep(0.05)

        run(_drive())
        self.assertEqual(calls, [1], "exactly once, however many arms")


# ================================ 14-18: provenance on every row =========
class TestLedgerProvenance(Base):

    def test_14_every_kind_carries_the_writing_pid_and_build(self):
        for kind in ("missions", "actions", "instructions"):
            row = shadow_ledger.append(kind, {"note": "x"})
            self.assertEqual(row["pid"], os.getpid(), kind)
            self.assertEqual(row["build"], shadow_ledger.build_id(), kind)
            self.assertTrue(row["build"], "a build stamp is never empty")

    def test_15_a_caller_supplied_stamp_is_overwritten_not_honored(self):
        """sutra_mcp hands a worker's own dict straight to append, and the
        instruction confirm path re-appends dict(rows[-1]). A stamp that can
        be supplied or inherited is not provenance."""
        row = shadow_ledger.append("actions", {
            "kind": "say", "pid": 1, "build": "9.9.9-forged"})
        self.assertEqual(row["pid"], os.getpid())
        self.assertNotEqual(row["build"], "9.9.9-forged")

    def test_16_a_real_transition_carries_it_with_no_call_site_change(self):
        m = self.store.create("objective", "fix")
        self.store.transition(m["id"], "brief_confirm", "t")
        rows = [r for r in shadow_ledger.read("missions", 300)
                if r.get("mission_id") == m["id"]]
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["pid"], os.getpid())
            self.assertEqual(r["build"], shadow_ledger.build_id())

    def test_17_readers_still_fold_and_tail_with_the_new_fields(self):
        first = shadow_ledger.append("instructions", {
            "text": "a", "confirmed": False})
        again = dict(first)
        again["confirmed"] = True
        shadow_ledger.append("instructions", again)
        folded = [r for r in shadow_ledger.read_latest("instructions")
                  if r["id"] == first["id"]]
        self.assertEqual(len(folded), 1, "supersede-by-id still folds")
        self.assertTrue(folded[0]["confirmed"])
        self.assertEqual(folded[0]["pid"], os.getpid())

    def test_18_the_stamp_did_not_move_the_caller_s_size_limit(self):
        """MAX_ROW_BYTES is about what a CALLER may hand us. Charging the
        caller for our own bookkeeping could fail a lifecycle write -- most
        call sites do not wrap append in try/except."""
        with self.assertRaises(ValueError):
            shadow_ledger.append("actions", {"blob": "x" * 9000})
        near = shadow_ledger.append(
            "actions", {"blob": "x" * (shadow_ledger.MAX_ROW_BYTES - 120)})
        self.assertEqual(near["pid"], os.getpid(),
                         "a row just under the bar is still accepted, and "
                         "still stamped")


if __name__ == "__main__":
    unittest.main(verbosity=2)
