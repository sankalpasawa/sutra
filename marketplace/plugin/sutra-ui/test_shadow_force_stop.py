#!/usr/bin/env python3
"""THE FOUNDER'S STOP MUST REACH THE WORKER PROCESS.

WHAT WAS MEASURED (founder, 2026-09-16, live app + a worker that hangs
mid-turn, Stop pressed on the task row):

    t+0s   POST stop -> state `stopped`, ended_by `founder`, slot freed
    t+10s  the worker process is STILL ALIVE and still mid-turn
           ps: 56613 S  .../Python.app/Contents/MacOS/Python

`MissionEngine.founder_stop` writes state and nothing else -- mission_engine
owns no processes. The only thing that reaps a delegate is the runner's own
terminal branch, reached when the LOOP returns; the loop was parked in a
boundary wait, which ends after STALL_SECS (240s) of silence or MAX_TURN_SECS
(3600s) for a worker that keeps emitting. A queued or paused mission has no
loop at all, so nothing would ever have reaped it. The worker died when the
app exited, and not before.

WHAT THIS PINS. `founder_force_stop` is the same founder_stop plus the
teardown, in the module that owns the processes, and every step is an
existing primitive: cancel the loop task, `release_delegate` (the one
reaper), or a group-kill by the recorded pid when this process has no handle
on the worker, then drop the loop lease.

NO NEW STATE. `stopped` + `ended_by="founder"` already IS an explicit
founder stop, and it stays distinguishable from a worker failure (`failed`)
and from a supervisor fault (`blocked` + failure_class).

REAL PROCESSES, NOT MOCKS. Sections 1, 2 and 6 spawn actual subprocesses
through the app's own ProcRuntime (process_group=0, so the child is a group
leader exactly as a delegate is) and assert the pid is gone afterwards.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_force_stop.py
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import mission_engine
import providers
import proc_group
import shadow_runner
from mission_engine import MissionStore


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


#: A stand-in worker that STAYS UP and whose argv really carries the session
#: id -- `/bin/sh -c "sleep 300" <sid>` does not, because the shell
#: exec-optimizes a single command and replaces its own argv with the
#: command's. A real delegate carries `--resume <sid>`, which is the whole
#: basis of delegate_alive()'s recycled-pid guard, so the fixture has to
#: carry one too or the guard is never actually exercised.
IDLE = [sys.executable, "-c", "import time; time.sleep(300)"]


def argv_of(pid):
    out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                         capture_output=True, text=True)
    return out.stdout or ""


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def wait_gone(pid, secs=5.0):
    """A SIGTERM is delivered, not applied: give the kernel a moment."""
    deadline = time.time() + secs
    while time.time() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return not pid_alive(pid)


class _Runtime(proc_group.ProcRuntime):
    """The app's OWN process lifecycle, with nothing else attached.

    ProcRuntime is a mixin -- it owns the methods, the subclass owns the
    fields -- so this declares the handful it relies on and nothing more.
    `_spawn_process` is the real one: process_group=0, so the child leads its
    own group and `kill_group` reaches its descendants, which is exactly how
    a delegate is spawned.
    """

    def __init__(self):
        self.proc = None
        self.key = ()
        self.stopped = False
        self.state = "idle"
        self.subscribers = []
        self.open_tools = set()
        self.turn_queue = None

    async def start(self, args, cwd):
        await self._spawn_process(args, cwd, tuple(args))
        return self.proc.pid


class Base(unittest.TestCase):
    def setUp(self):
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self._spawned = []
        shadow_runner.RUNNING.clear()
        shadow_runner.DELEGATES.clear()
        shadow_runner._STARTING.clear()

    def tearDown(self):
        for pid in self._spawned:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
        shadow_runner.RUNNING.clear()
        shadow_runner.DELEGATES.clear()
        shadow_runner._STARTING.clear()
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ---- fixtures ------------------------------------------------------
    def mission(self, state="running", sid="sess-1", **extra):
        m = self.store.create("Ship the thing.", "feature",
                              target_mode="new", target_session=sid, **extra)
        self.store.transition(m["id"], "brief_confirm", "t")
        if state == "brief_confirm":
            return m["id"]
        if state == "queued":
            self.store.transition(m["id"], "queued", "cap reached")
            return m["id"]
        self.store.transition(m["id"], "running", "admitted")
        if state == "paused":
            mm = self.store.transition(m["id"], "paused", "awaiting")
            mm["pause_reason"] = "founder_confirm"
            self.store.save(mm)
        elif state == "blocked":
            self.store.block(m["id"], "needs_founder", "Shadow asked")
        return m["id"]

    def worker(self, sid):
        """A REAL process, adopted as this session's delegate."""
        rt = _Runtime()
        pid = run(rt.start(["/bin/sh", "-c", "sleep 300", sid],
                           self.tmp.name))
        self._spawned.append(pid)
        shadow_runner.DELEGATES[sid] = rt
        self.assertTrue(pid_alive(pid), "precondition: the worker is running")
        return rt, pid

    def detached_worker(self, sid):
        """A worker THIS PROCESS HAS NO HANDLE ON -- the post-restart case.

        Its own process group, and the session id in its argv, because
        delegate_alive() refuses to trust a pid whose command line does not
        name the session (a recycled number must never be signalled).

        Returns the Popen, not the pid, for one reason that is a TEST
        artifact and not a product fact: this orphan is a CHILD of the test
        process, so once it is signalled it stays a zombie until someone
        waits on it -- and a zombie still answers `kill(pid, 0)`. In
        production the orphan belongs to a previous app run and is reaped by
        init. `died()` below waits, so the assertion is about death rather
        than about who reaps the corpse.
        """
        p = subprocess.Popen(IDLE + [sid], start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self._spawned.append(p.pid)
        self.assertTrue(pid_alive(p.pid))
        self.assertIn(sid, argv_of(p.pid),
                      "precondition: a delegate carries its session id in "
                      "argv, which is what delegate_alive() reads")
        return p

    def died(self, popen, secs=5):
        try:
            popen.wait(timeout=secs)
            return True
        except subprocess.TimeoutExpired:
            return False


# ============ 1. A RUNNING WORKER IS ACTUALLY TERMINATED ================
class TheWorkerProcessDies(Base):

    def test_force_stop_kills_the_running_worker(self):
        mid = self.mission()
        _rt, pid = self.worker("sess-1")
        out = shadow_runner.founder_force_stop(mid, "founder stop (home)")
        self.assertEqual(out["state"], "stopped")
        self.assertEqual(out["ended_by"], "founder")
        self.assertTrue(wait_gone(pid), "the worker process must be dead")
        self.assertNotIn("sess-1", shadow_runner.DELEGATES)

    def test_the_whole_process_group_goes(self):
        """A delegate spawns helpers that hold the stdout pipe; killing only
        the leader leaves them running. ProcRuntime spawns with
        process_group=0 for exactly this reason."""
        mid = self.mission(sid="sess-grp")
        rt = _Runtime()
        pid = run(rt.start(
            ["/bin/sh", "-c", "sleep 300 & sleep 300", "sess-grp"],
            self.tmp.name))
        self._spawned.append(pid)
        shadow_runner.DELEGATES["sess-grp"] = rt
        pgid = os.getpgid(pid)
        # Stop only once the helper exists. Stopping mid-fork lets a child born
        # a moment after the killpg escape it -- a race in this setup, not the
        # scenario under test (helpers already running when the founder stops).
        deadline = time.time() + 3.0
        while time.time() < deadline:
            members = subprocess.run(["pgrep", "-g", str(pgid)],
                                     capture_output=True, text=True).stdout.split()
            if len(members) >= 2:
                break
            time.sleep(0.02)
        shadow_runner.founder_force_stop(mid)
        self.assertTrue(wait_gone(pid))
        # Poll, not a fixed 0.2 s: under the release gate's parallel load the
        # signalled helper can take longer to exit, and a fixed sleep made this
        # red on a correct kill (2026-09-26, blocked the 2.304.2 release).
        deadline = time.time() + 3.0
        while True:
            left = subprocess.run(["pgrep", "-g", str(pgid)],
                                  capture_output=True, text=True)
            if not left.stdout.strip() or time.time() > deadline:
                break
            time.sleep(0.05)
        self.assertEqual(left.stdout.strip(), "",
                         "no member of the worker's group may survive")

    def test_the_loop_task_is_cancelled(self):
        mid = self.mission()
        self.worker("sess-1")

        async def forever():
            await asyncio.sleep(300)

        async def go():
            task = asyncio.ensure_future(forever())
            shadow_runner.RUNNING[mid] = task
            shadow_runner.founder_force_stop(mid)
            await asyncio.sleep(0.05)
            return task

        task = run(go())
        self.assertTrue(task.cancelled() or task.done(),
                        "the driving loop must not outlive the stop")
        self.assertNotIn(mid, shadow_runner.RUNNING)

    def test_the_loop_lease_is_released(self):
        mid = self.mission()
        self.worker("sess-1")
        shadow_runner._claim_loop(self.store, mid)
        self.assertEqual(self.store.load(mid)["loop_pid"], os.getpid())
        shadow_runner.founder_force_stop(mid)
        self.assertIsNone(self.store.load(mid)["loop_pid"])


# ====== 2. A WORKER WITH NO RUNTIME HANDLE (AFTER A RESTART) ============
class TheOrphanWorkerDiesToo(Base):

    def test_force_stop_kills_a_worker_by_its_recorded_pid(self):
        mid = self.mission(sid="sess-orphan")
        proc = self.detached_worker("sess-orphan")
        m = self.store.load(mid)
        m["delegate_pid"] = proc.pid
        self.store.save(m)
        self.assertNotIn("sess-orphan", shadow_runner.DELEGATES,
                         "precondition: no handle, exactly as after a boot")
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "stopped")
        self.assertTrue(self.died(proc),
                        "a delegate this process never held must still die")

    def test_a_recycled_pid_is_never_signalled(self):
        """delegate_alive checks ARGV as well as the pid. A live number whose
        command line does not name the session is not our worker."""
        p = subprocess.Popen(IDLE + ["someone-else"], start_new_session=True,
                             stdout=subprocess.DEVNULL)
        self._spawned.append(p.pid)
        self.assertIn("someone-else", argv_of(p.pid))
        mid = self.mission(sid="sess-recycled")
        m = self.store.load(mid)
        m["delegate_pid"] = p.pid
        self.store.save(m)
        shadow_runner.founder_force_stop(mid)
        time.sleep(0.3)
        self.assertTrue(pid_alive(p.pid),
                        "a pid that is not ours must not be killed")
        p.kill()

    def test_no_session_id_means_nothing_is_signalled(self):
        self.assertFalse(shadow_runner._kill_orphan_delegate(os.getpid(), ""))
        self.assertFalse(shadow_runner._kill_orphan_delegate(None, "s"))


# ============== 3. EVERY STATE THE FOUNDER CAN PRESS IT IN ==============
class EveryStartingState(Base):

    def test_queued_is_removed_from_the_queue(self):
        mid = self.mission(state="queued")
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "stopped")
        self.assertEqual(out["ended_by"], "founder")
        queued = [m["id"] for m in self.store.list(states=("queued",))]
        self.assertNotIn(mid, queued)

    def test_paused_needs_you_stops(self):
        mid = self.mission(state="paused")
        _rt, pid = self.worker("sess-1")
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "stopped")
        self.assertTrue(wait_gone(pid),
                        "a paused mission has no loop -- nothing else would "
                        "ever have reaped this worker")

    def test_blocked_needs_you_stops(self):
        mid = self.mission(state="blocked")
        _rt, pid = self.worker("sess-1")
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "stopped")
        self.assertIsNone(out.get("block_reason"),
                          "leaving a state clears its reason")
        self.assertTrue(wait_gone(pid))

    def test_between_turns_with_no_worker_is_not_an_error(self):
        mid = self.mission()
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "stopped")

    def test_a_brief_the_founder_never_started(self):
        mid = self.mission(state="brief_confirm")
        self.assertEqual(
            shadow_runner.founder_force_stop(mid)["state"], "stopped")


# ================== 4. THE SLOT AND THE ACCOUNTING =====================
class TheSlotIsReleased(Base):

    def test_a_stopped_mission_holds_no_slot(self):
        sched = mission_engine.MissionScheduler(self.store, max_running=1)
        first = self.mission()
        self.worker("sess-1")
        second = self.mission(state="brief_confirm", sid="sess-2")
        self.assertEqual(sched.start(second)["state"], "queued",
                         "precondition: the cap is full")
        shadow_runner.founder_force_stop(first)
        self.assertEqual(
            len(self.store.list(states=("running",))), 0,
            "the stopped mission is out of the running count")
        self.assertEqual(sched.start(second)["state"], "running",
                         "the freed slot admits the waiting task")

    def test_the_queue_promotes_on_the_existing_path(self):
        sched = mission_engine.MissionScheduler(self.store, max_running=1)
        first = self.mission()
        second = self.mission(state="brief_confirm", sid="sess-2")
        sched.start(second)
        shadow_runner.founder_force_stop(first)
        launched = []
        orig = shadow_runner._launch
        shadow_runner._launch = lambda mid, say, ver: launched.append(mid)
        try:
            promoted = run(shadow_runner._promote_after_slot_freed(
                self.store, first, object(), None))
        finally:
            shadow_runner._launch = orig
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["id"], second)
        self.assertEqual(launched, [second])


# ======================= 5. IDEMPOTENCE ================================
class PressingItAgainIsSafe(Base):

    def test_repeated_force_stop_is_a_no_op(self):
        mid = self.mission()
        _rt, pid = self.worker("sess-1")
        first = shadow_runner.founder_force_stop(mid)
        self.assertTrue(wait_gone(pid))
        for _ in range(3):
            again = shadow_runner.founder_force_stop(mid)
            self.assertEqual(again["state"], "stopped")
            self.assertEqual(again["ended_by"], "founder")
        self.assertEqual(again["seq"], first["seq"],
                         "no further transition was written")
        self.assertEqual(len(self.store.list(states=("running",))), 0)

    def test_it_never_overwrites_a_completion(self):
        """Force Stop landing just after the worker finished, before Shadow
        settled the result: the completion is the worker's and stands."""
        mid = self.mission()
        done = self.store.transition(mid, "done", "done_when met")
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "done")
        self.assertIsNone(out.get("ended_by"),
                          "a completion is not a founder stop")
        self.assertEqual(out["seq"], done["seq"])

    def test_a_failed_mission_is_handed_back_unchanged(self):
        mid = self.mission()
        self.store.transition(mid, "failed", "budget")
        out = shadow_runner.founder_force_stop(mid)
        self.assertEqual(out["state"], "failed")
        self.assertIsNone(out.get("ended_by"))

    def test_an_unknown_mission_raises_rather_than_inventing_one(self):
        with self.assertRaises(ValueError):
            shadow_runner.founder_force_stop("m-nope")


# ============ 6. NOTHING RESPAWNS, ADOPTS OR RESURRECTS IT =============
class NoRespawnAfterTheStop(Base):

    def test_a_stop_during_the_spawn_reaps_what_the_spawn_created(self):
        """The window that matters: provisioning a delegate takes minutes,
        and the founder pressed Stop inside it. The spawn still finishes and
        still hands back a live worker."""
        mid = self.mission(state="brief_confirm", sid=None)
        m = self.store.load(mid)
        m["target_session"] = None
        self.store.save(m)
        holder = {}

        async def spawner(mission):
            # the founder presses Stop while this is running
            shadow_runner.founder_force_stop(mid)
            rt = _Runtime()
            pid = await rt.start(IDLE + ["sess-late"], self.tmp.name)
            self._spawned.append(pid)
            shadow_runner.DELEGATES["sess-late"] = rt
            holder["pid"] = pid
            return "sess-late"

        launched = []
        orig = shadow_runner._launch
        shadow_runner._launch = lambda *a: launched.append(a[0])
        try:
            # SYNC: it schedules its own background task and answers at once
            shadow_runner.start_mission_async(
                mid, lambda *a, **k: True, provisioner=spawner)
            run(asyncio.sleep(0.3))
        finally:
            shadow_runner._launch = orig
        self.assertEqual(launched, [], "a stopped mission must not launch")
        self.assertEqual(self.store.load(mid)["state"], "stopped")
        self.assertTrue(wait_gone(holder["pid"]),
                        "the worker the spawn created must not be left alive")

    def test_boot_recovery_does_not_resurrect_it(self):
        mid = self.mission()
        self.worker("sess-1")
        shadow_runner.founder_force_stop(mid)
        shadow_runner.RUNNING.clear()
        shadow_runner.recover_on_boot()
        self.assertEqual(self.store.load(mid)["state"], "stopped")
        self.assertNotIn(mid, [m["id"] for m in
                               self.store.list(states=("paused",))])

    def test_the_restart_sweep_does_not_adopt_it(self):
        mid = self.mission()
        self.worker("sess-1")
        shadow_runner.founder_force_stop(mid)
        adopted, launched = [], []

        async def ensure_rt(sid):
            adopted.append(sid)

        async def ensure_delegate(sid, mode=None):
            adopted.append(sid)

        orig = shadow_runner._launch
        shadow_runner._launch = lambda *a: launched.append(a[0])
        try:
            res = run(shadow_runner.resume_after_restart(
                ensure_rt, lambda *a, **k: True,
                ensure_delegate_async=ensure_delegate))
        finally:
            shadow_runner._launch = orig
        self.assertEqual(res["resumed"], [])
        self.assertEqual(adopted, [], "nothing may be re-entered")
        self.assertEqual(launched, [])
        self.assertEqual(self.store.load(mid)["state"], "stopped")

    def test_the_stop_survives_a_reload(self):
        mid = self.mission()
        self.worker("sess-1")
        shadow_runner.founder_force_stop(mid)
        fresh = MissionStore()          # a new reader, as a reload is
        self.assertEqual(fresh.load(mid)["state"], "stopped")
        self.assertEqual(fresh.load(mid)["ended_by"], "founder")


# ====== 7. LATE WORKER OUTPUT CANNOT MOVE A STOPPED MISSION ============
class StoppedIsFinal(Base):

    def _stopped(self):
        mid = self.mission()
        shadow_runner.founder_force_stop(mid)
        return mid

    def test_the_state_machine_refuses_every_exit(self):
        mid = self._stopped()
        self.assertEqual(mission_engine.TRANSITIONS["stopped"], ())
        for target in ("done", "failed", "running", "paused", "blocked"):
            with self.assertRaises(ValueError, msg=target):
                self.store.transition(mid, target, "late")
        with self.assertRaises(ValueError):
            self.store.block(mid, "shadow_crashed", "late crash")

    def test_the_ending_funnels_hand_it_back(self):
        """A turn that was in flight when the stop landed, arriving late."""
        mid = self._stopped()
        rec = self.store.load(mid)
        eng = mission_engine.MissionEngine(
            self.store, None, None,
            lambda m: "DONE-MARKER, everything finished")
        for reason, term in (("budget_exhausted", "failed"),
                             ("ping_pong", "stopped"),
                             ("turn_stalled", "failed")):
            self.assertEqual(
                eng._out_of_road(dict(rec), term, reason, "late")["state"],
                "stopped", reason)
        for reason in sorted(mission_engine.INFRA_BLOCK_REASONS):
            self.assertEqual(
                eng._infra_exit(dict(rec), reason, "late")["state"],
                "stopped", reason)
        self.assertEqual(self.store.load(mid)["state"], "stopped")

    def test_the_loop_returns_without_driving(self):
        mid = self._stopped()
        said = []

        async def sayer(m, t):
            said.append(t)
            return True

        async def waiter(m):
            return True

        eng = mission_engine.MissionEngine(
            self.store, sayer, waiter, lambda m: "")
        out = run(eng.run_mission(mid))
        self.assertEqual(out["state"], "stopped")
        self.assertEqual(said, [], "a stopped mission is never spoken to")


# ============== 8. PROVENANCE STAYS TRUTHFUL ===========================
class WhoEndedIt(Base):

    def test_a_founder_stop_is_distinguishable_from_machine_endings(self):
        founder = self.mission()
        shadow_runner.founder_force_stop(founder)
        f = self.store.load(founder)

        machine = self.mission(sid="sess-2")
        rec = self.store.load(machine)
        eng = mission_engine.MissionEngine(self.store, None, None,
                                           lambda m: "nothing yet")
        eng._out_of_road(rec, "stopped", "ping_pong", "ping-pong detected")
        p = self.store.load(machine)

        self.assertEqual((f["state"], f.get("ended_by")),
                         ("stopped", "founder"))
        self.assertEqual(p["state"], "stopped")
        self.assertIsNone(p.get("ended_by"),
                          "ping-pong is not a founder decision and must "
                          "never be recorded as one")

    def test_the_teardown_is_recorded(self):
        mid = self.mission()
        self.worker("sess-1")
        shadow_runner.founder_force_stop(mid)
        rows = [json.loads(l) for l in
                (Path(self.tmp.name) / "ledger" / "actions.jsonl")
                .read_text().splitlines()]
        stops = [r for r in rows
                 if r.get("mission_id") == mid and r["kind"] == "stop"]
        self.assertTrue(stops, "the founder action leaves an audit row")
        self.assertIn("founder force stop", stops[-1]["summary"])
        self.assertIn("reaped", stops[-1]["summary"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
