#!/usr/bin/env python3
"""A fault in the SUPERVISOR is not a verdict on the WORK.

WHAT THIS PINS (founder, 2026-09-16), measured on two live missions the day
before:

  m-07cbb61906cc  re-adopted 18:35:17Z, `failed` at 18:35:17Z -- one second,
                  no decider transcript written at all.
  m-5c2fca3f824b  re-adopted 19:17:12Z, `failed` at 19:17:13Z. The worker
                  then finished successfully at 19:18:49Z and 19:19:04Z --
                  96 seconds AFTER its mission had been marked failed -- and
                  the result was thrown away.

Neither failure consulted the work. `evaluate_done_when` sits far below the
undecided branch that returned, so the checks, the transcript and the test
results played no part. Five defects made that outcome possible, one section
each:

  1. an infra fault took the terminal exit        (INFRA_BLOCK_REASONS)
  2. nothing stopped two processes driving one mission  (the loop lease)
  3. re-adoption rebuilt argv from CURRENT settings (worker_permission_mode)
  4. no field named the turn that was in flight           (turn_open)
  5. `verifier` was None on every production path        (DONE-CHECK)

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_supervisor_recovery.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import session_reader
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
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig_settings
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def _running(self, **extra):
        m = self.store.create("Ship the thing.", "feature",
                              target_mode="new", target_session="sess-1",
                              **extra)
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        m["manifest_delivered"] = True
        m["turns_used"] = 2
        self.store.save(m)
        return m["id"]

    def _engine(self, decisions, **kw):
        """A loop whose decider answers from a list. `said` records every
        instruction that actually left the engine."""
        self.said = []

        async def sayer(m, text):
            self.said.append(text)
            return True

        async def waiter(m):
            return True

        seq = list(decisions)

        async def decider(ctx):
            return seq.pop(0) if seq else None

        return mission_engine.MissionEngine(
            self.store, sayer, waiter, lambda m: "", decider=decider, **kw)


# ============ 1. AN INFRA FAULT MUST NOT MARK A LIVE MISSION FAILED ======
class InfraFaultIsRecoverable(Base):
    """The exact shape of both live failures: a decider that answers with
    something validate_decision cannot read."""

    def test_an_unreadable_decision_blocks_rather_than_fails(self):
        mid = self._running()
        out = run(self._engine([{"action": "nonsense"}]).run_mission(mid))
        self.assertEqual(out["state"], "blocked",
                         "a broken decider must not kill a live mission")
        self.assertNotIn(out["state"], mission_engine.TERMINAL,
                         "and the state it lands in must be recoverable")

    def test_the_fault_is_labelled_as_shadows_own(self):
        """The whole ask: infrastructure failure is TOLD APART from work
        failure, on the record, without parsing prose."""
        mid = self._running()
        out = run(self._engine([{"action": "nonsense"}]).run_mission(mid))
        self.assertEqual(out.get("failure_class"), "shadow_infra")
        self.assertEqual(out.get("block_reason"), "shadow_undecided")

    def test_a_decider_that_raises_takes_the_same_exit(self):
        """`decider failed: ...` and `no usable decision` are one class."""
        mid = self._running()

        async def boom(ctx):
            raise RuntimeError("shadow is down")

        eng = self._engine([])
        eng.decider = boom
        out = run(eng.run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out.get("failure_class"), "shadow_infra")

    def test_nothing_is_said_into_the_worker_chat(self):
        mid = self._running()
        run(self._engine([{"action": "nonsense"}]).run_mission(mid))
        self.assertEqual(self.said, [],
                         "an undecided turn must send nothing")

    def test_the_reason_still_survives_on_the_record(self):
        mid = self._running()
        run(self._engine([{"action": "nonsense"}]).run_mission(mid))
        notes = [json.loads(l)["note"] for l
                 in open(shadow_runner.shadow_ledger._path("missions"),
                         encoding="utf-8") if mid in l]
        self.assertTrue(any("no usable decision" in n for n in notes),
                        "the diagnosis must not be lost: %s" % notes)

    def test_REAL_out_of_road_still_ends_the_mission(self):
        """The guard is narrow. Budget exhaustion is a fact about the WORK
        and keeps its historical terminal state."""
        mid = self._running()
        m = self.store.load(mid)
        m["turns_used"] = m["max_turns"]
        self.store.save(m)
        out = run(self._engine([]).run_mission(mid))
        self.assertEqual(out["state"], "failed",
                         "budget_exhausted is not Shadow's fault")
        self.assertIsNone(out.get("failure_class"))

    def test_a_goal_attempt_is_unchanged(self):
        """It already blocked; it must still block."""
        mid = self._running(goal_id="g-1")
        out = run(self._engine([{"action": "nonsense"}]).run_mission(mid))
        self.assertEqual(out["state"], "blocked")


# ================= 2. ONE LOOP PER MISSION, ACROSS PROCESSES =============
class OnlyOneLoopDrivesAMission(Base):
    """RUNNING is per-process, so five boots in eight seconds put four
    decider subprocesses on one mission (m-5c2fca3f824b, 19:15:06-19:15:20).
    The lease is the cross-process half of that guard."""

    def _foreign(self, mid, alive):
        m = self.store.load(mid)
        m["loop_pid"] = os.getpid() + 1
        self.store.save(m)
        orig = shadow_runner._app_process_alive
        self.addCleanup(setattr, shadow_runner, "_app_process_alive", orig)
        shadow_runner._app_process_alive = lambda pid: alive

    def test_an_unclaimed_mission_is_free(self):
        mid = self._running()
        self.assertFalse(shadow_runner.loop_held_elsewhere(self.store, mid))

    def test_our_own_lease_never_blocks_us(self):
        mid = self._running()
        m = self.store.load(mid)
        m["loop_pid"] = os.getpid()
        self.store.save(m)
        self.assertFalse(shadow_runner.loop_held_elsewhere(self.store, mid),
                         "a process must not refuse to relaunch its own loop")

    def test_a_LIVE_foreign_owner_holds_it(self):
        mid = self._running()
        self._foreign(mid, True)
        self.assertTrue(shadow_runner.loop_held_elsewhere(self.store, mid))

    def test_a_DEAD_owner_does_not_strand_the_mission(self):
        """The failure worth more than the duplicate it prevents: an app
        SIGKILLed by Electron leaves its pid on the record forever."""
        mid = self._running()
        self._foreign(mid, False)
        self.assertFalse(shadow_runner.loop_held_elsewhere(self.store, mid))

    def test_a_garbage_stamp_fails_open(self):
        mid = self._running()
        m = self.store.load(mid)
        m["loop_pid"] = "not-a-pid"
        self.store.save(m)
        self.assertFalse(shadow_runner.loop_held_elsewhere(self.store, mid))

    def test_launch_refuses_while_another_process_holds_it(self):
        mid = self._running()
        self._foreign(mid, True)
        shadow_runner._launch(mid, lambda *a, **k: True, None)
        self.assertNotIn(mid, shadow_runner.RUNNING,
                         "a second app instance must not start a second loop")

    def test_a_missing_mission_never_blocks(self):
        self.assertFalse(
            shadow_runner.loop_held_elsewhere(self.store, "m-gone"))

    def test_claiming_stamps_this_process_and_releasing_clears_it(self):
        mid = self._running()
        shadow_runner._claim_loop(self.store, mid)
        self.assertEqual(MissionStore().load(mid)["loop_pid"], os.getpid(),
                         "the lease must be durable, not in-memory")
        shadow_runner._release_loop(self.store, mid)
        self.assertIsNone(MissionStore().load(mid)["loop_pid"])

    def test_releasing_never_steals_a_lease_that_is_not_ours(self):
        """A process finishing late must not clear the lease a LIVE
        successor has already taken."""
        mid = self._running()
        m = self.store.load(mid)
        m["loop_pid"] = os.getpid() + 1
        self.store.save(m)
        shadow_runner._release_loop(self.store, mid)
        self.assertEqual(MissionStore().load(mid)["loop_pid"],
                         os.getpid() + 1)

    def test_neither_helper_raises_on_a_missing_mission(self):
        shadow_runner._claim_loop(self.store, "m-gone")
        shadow_runner._release_loop(self.store, "m-gone")


# ============ 3. THE WORKER KEEPS THE PERMISSIONS IT WAS SPAWNED WITH ====
class PermissionModeSurvivesReAdoption(Base):
    """A worker spawned under acceptEdits came back on whatever the founder
    had selected since -- `plan`, i.e. read only -- mid-task."""

    def _paused_delegate(self, mode):
        m = self.store.create("o", "fix", target_mode="new",
                              target_session="d-1")
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        m = self.store.transition(m["id"], "paused", "t")
        m["pause_reason"] = "app_restart"
        m["delegate_pid"] = 4242
        if mode:
            m["worker_permission_mode"] = mode
        self.store.save(m)
        return m["id"]

    def _resume(self):
        self.adopted = []

        async def adopt(sid, permission_mode=None):
            self.adopted.append((sid, permission_mode))
            return object()

        async def reattach(sid):
            return object()

        orig_launch = shadow_runner._launch
        orig_alive = shadow_runner.delegate_alive
        orig_read = shadow_runner.session_reader.read_session
        shadow_runner._launch = lambda mid, *a, **k: None
        shadow_runner.delegate_alive = lambda pid, sid=None: False
        shadow_runner.session_reader.read_session = lambda sid: {"id": sid}
        try:
            return run(shadow_runner.resume_after_restart(
                reattach, lambda *a, **k: True,
                ensure_delegate_async=adopt))
        finally:
            shadow_runner._launch = orig_launch
            shadow_runner.delegate_alive = orig_alive
            shadow_runner.session_reader.read_session = orig_read

    def test_the_stamped_mode_is_handed_back(self):
        self._paused_delegate("acceptEdits")
        self._resume()
        self.assertEqual([m for _, m in self.adopted], ["acceptEdits"],
                         "a re-adopted worker must not be re-permissioned")

    def test_an_unstamped_mission_resolves_to_the_historical_behaviour(self):
        """Every mission that existed before the stamp: None, which the
        callee turns back into 'read the live setting'."""
        self._paused_delegate(None)
        self._resume()
        self.assertEqual([m for _, m in self.adopted], [None])

    def test_the_session_is_still_the_one_that_was_adopted(self):
        self._paused_delegate("acceptEdits")
        self._resume()
        self.assertEqual([s for s, _ in self.adopted], ["d-1"])


# =================== 4. THE TURN THAT IS HAPPENING RIGHT NOW =============
class TheInFlightTurnIsOnTheRecord(Base):
    def test_turn_open_is_stamped_while_the_worker_is_speaking(self):
        mid = self._running()
        m = self.store.load(mid)
        m["max_turns"] = 3
        self.store.save(m)
        seen = {}

        async def sayer(mm, text):
            return True

        async def waiter(mm):
            cur = self.store.load(mid)
            seen["turn_open"] = cur.get("turn_open")
            seen["turns_used"] = cur.get("turns_used")
            return True

        async def decider(ctx):
            return {"action": "continue", "instruction": "go", "reason": "r"}

        eng = mission_engine.MissionEngine(
            self.store, sayer, waiter, lambda mm: "", decider=decider)
        run(eng.run_mission(mid))
        self.assertEqual(seen["turn_open"], seen["turns_used"] + 1,
                         "the in-flight turn is the NEXT one, not the last")

    def test_it_is_cleared_once_the_turn_lands(self):
        mid = self._running()
        m = self.store.load(mid)
        m["max_turns"] = 3
        self.store.save(m)
        run(self._engine([
            {"action": "continue", "instruction": "go", "reason": "r"},
            {"action": "ask_founder", "reason": "done"},
        ]).run_mission(mid))
        self.assertIsNone(self.store.load(mid).get("turn_open"),
                          "exactly one field describes a turn at a time")

    def test_it_is_DURABLE_so_a_restart_can_read_it(self):
        """Surviving the restart is the whole point -- a fresh store object
        must see it, not just the dict the loop mutated."""
        mid = self._running()
        m = self.store.load(mid)
        m["turn_open"] = 7
        self.store.save(m)
        self.assertEqual(MissionStore().load(mid).get("turn_open"), 7)

    # ---- THE FIRST TURN, WHICH HAPPENS INSIDE THE SPAWN ----------------
    # (founder, 2026-09-18: "when turn 1 is starting it still shows turn 0
    # of 25"). spawn_delegate_session sends the manifest and waits out the
    # WHOLE first agentic turn, and run_mission's `briefed` branch then
    # skips the say-and-wait block that carries `turn_open` -- so the one
    # turn nothing ever named was turn 1, the longest one of the mission.
    #
    # AND THE OTHER EDGE, ruled the same day: the stamp must NOT land before
    # the worker exists. provision_target once wrote it on the line above
    # `await spawner(m)`, which put "turn 1 of 25" on the card across the
    # criteria call and the process boot, while nothing was running. Zero is
    # the honest reading there. The spawner now names the turn at FIRST
    # CONTACT, through mission_engine.open_first_turn, and these two tests
    # are the two halves of that: still zero while the spawn is only
    # starting, one from the frame the worker actually paints.

    def _new_mission(self):
        m = self.store.create("Ship the thing.", "feature",
                              target_mode="new")
        self.store.transition(m["id"], "brief_confirm", "t")
        self.store.transition(m["id"], "running", "t")
        return m["id"]

    def test_the_card_stays_at_ZERO_until_the_worker_is_there(self):
        """The engine names NOTHING on the way into the spawn.

        Between admission and first contact there is no worker and nothing
        painting, and the founder's ruling is that the card reads 0 for that
        whole stretch. Read from the STORE, which is what a card renders.
        """
        mid = self._new_mission()
        seen = {}

        async def spawner(m):
            cur = self.store.load(mid)
            seen["turn_open"] = cur.get("turn_open")
            seen["turns_used"] = cur.get("turns_used")
            return "sess-live"

        eng = mission_engine.MissionEngine(self.store, None, None, None)
        run(eng.provision_target(mid, spawner))
        self.assertEqual(seen["turns_used"], 0, "no turn has FINISHED yet")
        self.assertIsNone(seen["turn_open"],
                          "no worker exists yet -- the card must read 0")

    def test_FIRST_CONTACT_names_turn_1_while_the_spawn_is_still_working(self):
        """...and the moment the worker paints, the turn has its number.

        The real hook is shadow_runner.spawn_delegate_session's `_adopt`,
        which fires on the first frame carrying a session id; here the fake
        spawner calls the same one-line writer that hook calls.
        """
        mid = self._new_mission()
        seen = {}

        async def spawner(m):
            mission_engine.open_first_turn(self.store, mid)   # first contact
            cur = self.store.load(mid)
            seen["turn_open"] = cur.get("turn_open")
            seen["turns_used"] = cur.get("turns_used")
            return "sess-live"

        eng = mission_engine.MissionEngine(self.store, None, None, None)
        run(eng.provision_target(mid, spawner))
        self.assertEqual(seen["turns_used"], 0, "still no FINISHED turn")
        self.assertEqual(seen["turn_open"], 1,
                         "turn 1 is the turn the worker has just begun")
        self.assertEqual(self.store.load(mid).get("turn_open"), 1,
                         "and it survives the rest of provision_target")

    def test_open_first_turn_never_lowers_and_never_raises(self):
        """A re-adopted or retried spawn must not walk the count backwards,
        and a terminal mission must not acquire a turn at all."""
        mid = self._new_mission()
        m = self.store.load(mid)
        m["turns_used"], m["turn_open"] = 4, 5
        self.store.save(m)
        mission_engine.open_first_turn(self.store, mid)
        self.assertEqual(self.store.load(mid).get("turn_open"), 5,
                         "a higher open turn stands")
        self.store.transition(mid, "stopped", "t")
        mission_engine.open_first_turn(self.store, mid)
        self.assertEqual(self.store.load(mid).get("turn_open"), 5,
                         "a terminal mission is left alone")
        self.assertIsNone(mission_engine.open_first_turn(self.store, "m-nope"),
                          "an unknown mission is a no-op, not a crash")

    def test_the_briefed_loop_clears_it_when_that_turn_lands(self):
        """The spawn stamp and the loop's own stamp are ONE field: the
        briefed iteration converges on the same increment, so turn 1 ends
        exactly as every later turn does."""
        mid = self._new_mission()

        async def spawner(m):
            mission_engine.open_first_turn(self.store, mid)
            return "sess-live"

        run(mission_engine.MissionEngine(
            self.store, None, None, None).provision_target(mid, spawner))
        self.assertEqual(self.store.load(mid).get("turn_open"), 1)
        run(self._engine([
            {"action": "ask_founder", "reason": "done"},
        ]).run_mission(mid))
        m = self.store.load(mid)
        self.assertIsNone(m.get("turn_open"),
                          "exactly one field describes a turn at a time")
        self.assertEqual(m.get("turns_used"), 1,
                         "the spawn turn is counted once, as it always was")

    def test_a_spawn_that_blows_up_leaves_no_turn_in_flight(self):
        mid = self._new_mission()

        async def spawner(m):
            # first contact happened -- the boot check is what fails
            mission_engine.open_first_turn(self.store, mid)
            raise RuntimeError("no runtime")

        eng = mission_engine.MissionEngine(self.store, None, None, None)
        with self.assertRaises(RuntimeError):
            run(eng.provision_target(mid, spawner))
        self.assertIsNone(self.store.load(mid).get("turn_open"),
                          "a turn nobody is working must not outlive the spawn")

    def test_the_spawn_stamp_is_not_a_second_budget(self):
        """max_turns is compared against turns_used and nothing else.

        A one-turn mission whose turn 1 is open must still GET that turn:
        if the stamp were counted, the loop would fail on budget before it
        ever evaluated the work the spawn already did.
        """
        mid = self._new_mission()
        m = self.store.load(mid)
        m["max_turns"] = 1
        self.store.save(m)

        async def spawner(m2):
            mission_engine.open_first_turn(self.store, mid)
            return "sess-live"

        run(mission_engine.MissionEngine(
            self.store, None, None, None).provision_target(mid, spawner))
        run(self._engine([
            {"action": "ask_founder", "reason": "q"}]).run_mission(mid))
        self.assertEqual(self.store.load(mid).get("turns_used"), 1,
                         "turn 1 ran and was counted -- the open stamp was "
                         "never a spent turn")

    # ---- THE TOP OF THE RANGE ------------------------------------------
    # The display names the turn IN FLIGHT, which makes the last turn of a
    # mission the one place that number and the ceiling meet. "25 of 25" is
    # right; "26 of 25" would be the fix trading one wrong number for a
    # worse one, so both ends are pinned here rather than reasoned about.

    def test_the_last_turn_reads_AS_THE_CEILING_not_past_it(self):
        mid = self._running()
        m = self.store.load(mid)
        m["turns_used"], m["max_turns"] = 24, 25
        self.store.save(m)
        seen = {}

        async def sayer(mm, text):
            return True

        async def waiter(mm):
            # the record as a card would render it mid-turn
            seen["turn_open"] = self.store.load(mid).get("turn_open")
            return True

        seq = [{"action": "continue", "instruction": "go", "reason": "r"}]

        async def decider(ctx):
            return seq.pop(0) if seq else None

        run(mission_engine.MissionEngine(
            self.store, sayer, waiter, lambda mm: "",
            decider=decider).run_mission(mid))
        self.assertEqual(seen["turn_open"], 25,
                         "the final turn is named 25, and 25 is the ceiling")

    def test_an_EXHAUSTED_budget_never_stamps_a_turn_past_the_ceiling(self):
        """`turns_used >= max_turns` is checked BEFORE the say, so the turn
        that would have been 26 is never opened -- the mission goes out of
        road with the record still reading 25."""
        mid = self._running()
        m = self.store.load(mid)
        m["turns_used"], m["max_turns"], m["turn_open"] = 25, 25, None
        self.store.save(m)
        out = run(self._engine([
            {"action": "continue", "instruction": "go", "reason": "r"}]
        ).run_mission(mid))
        self.assertIsNone(out.get("turn_open"),
                          "a spent mission has no turn in flight")
        self.assertEqual(out.get("turns_used"), 25,
                         "and the count it ends on is the ceiling itself")

    def test_the_budget_still_counts_FINISHED_turns_only(self):
        """turn_open must never become a second budget: max_turns is compared
        against turns_used and nothing else."""
        mid = self._running()
        m = self.store.load(mid)
        m["turns_used"], m["max_turns"], m["turn_open"] = 1, 30, 2
        self.store.save(m)
        out = run(self._engine([
            {"action": "ask_founder", "reason": "q"}]).run_mission(mid))
        self.assertNotEqual(out["state"], "failed",
                            "an open turn must not read as a spent budget")


# ================ 5. A VERIFY CHECK THAT CAN ACTUALLY PASS ===============
class TheVerifyTierWorks(Base):
    """`verifier` was None on every production path, so evaluate_done_when's
    verify arm returned False unconditionally. Three of m-5c2fca3f824b's four
    checks were verify-tier and were unsatisfiable by construction."""

    CHECK = ("The backend enforces the configured limit and excess tasks "
             "are queued instead of running.")

    def _mission_with(self, tier):
        """WRITTEN PAST THE DOOR, and deliberately.

        The subject of this class is evaluate_done_when's verify ARM and the
        _call_verifier shim -- evaluation-time behaviour, which
        resolve_verify_tier does not touch. The create() door now demotes a
        `verify` with no probe behind it (founder, 2026-09-17), so minting
        one there would test the door instead. save() is not a door, so this
        produces exactly the record a mission written before that rule has
        on disk -- which is the record these tests are about."""
        m = self.store.create("o", "fix", target_mode="new",
                              target_session="s")
        m["done_when"] = [{"tier": tier, "check": self.CHECK}]
        self.store.save(m)
        return self.store.load(m["id"])

    def _verifier(self):
        import app
        return app._shadow_verifier

    # ---- the shim ----
    def test_a_two_arg_verifier_is_given_the_evidence(self):
        seen = {}

        def v(check, evidence):
            seen["evidence"] = evidence
            return True

        done, _ = mission_engine.evaluate_done_when(
            self._mission_with("verify"), "THE EVIDENCE", v)
        self.assertTrue(done)
        self.assertEqual(seen["evidence"], "THE EVIDENCE")

    def test_a_ONE_arg_verifier_still_works(self):
        """Every verifier written before this one, and every test lambda."""
        done, _ = mission_engine.evaluate_done_when(
            self._mission_with("verify"), "x", lambda check: True)
        self.assertTrue(done)

    def test_a_TypeError_from_inside_is_not_retried_as_one_arg(self):
        calls = []

        def v(check, evidence):
            calls.append(1)
            raise TypeError("a real bug inside the verifier")

        with self.assertRaises(TypeError):
            mission_engine.evaluate_done_when(
                self._mission_with("verify"), "x", v)
        self.assertEqual(len(calls), 1, "it must not be called twice")

    def test_no_verifier_still_means_unmet(self):
        done, res = mission_engine.evaluate_done_when(
            self._mission_with("verify"), "x", None)
        self.assertFalse(done)
        self.assertFalse(res[0]["met"])

    # ---- the production verifier ----
    def test_a_quoted_DONE_CHECK_line_satisfies_the_check(self):
        ev = "I finished it.\nDONE-CHECK: %s\nNext up..." % self.CHECK
        self.assertTrue(self._verifier()(self.CHECK, ev))

    def test_prose_alone_never_satisfies_anything(self):
        ev = ("I implemented the backend limit and excess tasks are queued "
              "instead of running. All tests pass.")
        self.assertFalse(self._verifier()(self.CHECK, ev),
                         "a claim in prose is not an assertion")

    def test_a_DONE_CHECK_for_a_DIFFERENT_check_does_not_count(self):
        ev = "DONE-CHECK: The setting persists across an app restart."
        self.assertFalse(self._verifier()(self.CHECK, ev))

    def test_no_evidence_is_not_a_pass(self):
        self.assertFalse(self._verifier()(self.CHECK, ""))
        self.assertFalse(self._verifier()(self.CHECK, None))

    def test_a_trimmed_quote_still_counts_if_it_is_distinctive(self):
        """A worker retyping a sentence will trim it; requiring the whole
        string would fail honest assertions."""
        ev = "DONE-CHECK: The backend enforces the configured limit and exce"
        self.assertTrue(self._verifier()(self.CHECK, ev))

    def test_a_TINY_quote_is_refused(self):
        ev = "DONE-CHECK: done"
        self.assertFalse(self._verifier()(self.CHECK, ev),
                         "a few characters cannot identify a check")

    def test_it_drives_a_real_evaluation_end_to_end(self):
        m = self._mission_with("verify")
        ev = "DONE-CHECK: %s" % self.CHECK
        done, res = mission_engine.evaluate_done_when(m, ev, self._verifier())
        self.assertTrue(done, "a verify check must be able to pass: %s" % res)

    def test_founder_confirm_is_STILL_not_auto_passable(self):
        """The tier that must never be satisfiable by anything the worker
        says, however it says it."""
        m = self._mission_with("founder_confirm")
        done, _ = mission_engine.evaluate_done_when(
            m, "DONE-CHECK: %s" % self.CHECK, self._verifier())
        self.assertFalse(done, "only the founder may satisfy founder_confirm")


# ============ 6. THE CLI'S RESUME HANDSHAKE IS NOT A WORKER TURN =========
class ResumeHandshakeIsNotConversation(Base):
    """`claude --resume` injects a user turn and the model answers it.
    Shadow re-adopts on every restart, so a mission that survived five boots
    showed five of these as WORKER AGENT turns."""

    def _parse(self, rows):
        p = Path(self.tmp.name) / "t.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        return session_reader._parse_transcript(p)["messages"]

    def _user(self, text, meta=False, src=None):
        return {"type": "user", "isMeta": meta, "sourceToolUseID": src,
                "timestamp": "2026-09-16T00:00:00Z",
                "message": {"content": [{"type": "text", "text": text}]}}

    def _asst(self, text, calls=()):
        content = [{"type": "text", "text": text}]
        for c in calls:
            content.append({"type": "tool_use", "id": "t1", "name": c,
                            "input": {}})
        return {"type": "assistant", "timestamp": "2026-09-16T00:00:00Z",
                "message": {"content": content}}

    def test_the_injected_prompt_and_its_noop_reply_both_vanish(self):
        msgs = self._parse([
            self._user("Continue from where you left off.", meta=True),
            self._asst("No response requested."),
            self._asst("Here is the real work."),
        ])
        self.assertEqual([m["text"] for m in msgs], ["Here is the real work."])

    def test_a_REAL_founder_message_is_never_dropped(self):
        msgs = self._parse([self._user("Continue from where you left off.")])
        self.assertEqual(len(msgs), 1,
                         "only an isMeta record is the CLI's own")

    def test_a_noop_reply_with_a_TOOL_CALL_is_kept(self):
        """It did work; whatever it said about it is beside the point."""
        msgs = self._parse([
            self._user("Continue from where you left off.", meta=True),
            self._asst("No response requested.", calls=["Bash"]),
        ])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["tools"], ["Bash"])

    def test_an_unrelated_reply_after_an_injection_is_kept(self):
        msgs = self._parse([
            self._user("Continue from where you left off.", meta=True),
            self._asst("Resuming: the migration is half done."),
        ])
        self.assertEqual([m["text"] for m in msgs],
                         ["Resuming: the migration is half done."])

    def test_a_LATER_noop_reply_is_not_swallowed(self):
        """The guard is armed by an injection and disarmed by anything else,
        so it can never reach across the conversation."""
        msgs = self._parse([
            self._user("Continue from where you left off.", meta=True),
            self._asst("No response requested."),
            self._user("do the thing"),
            self._asst("No response requested."),
        ])
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])

    def test_the_tool_injected_rule_still_holds(self):
        """isMeta + sourceToolUseID was already dropped and still is."""
        msgs = self._parse([self._user("SKILL BODY", meta=True, src="tu-1")])
        self.assertEqual(msgs, [])

    def test_an_image_placeholder_is_still_kept(self):
        """The reason the isMeta flag alone was never enough."""
        msgs = self._parse([self._user("[Image: screenshot.png]", meta=True)])
        self.assertEqual(len(msgs), 1)


# ====== 6b. THE WORK IS ASKED BEFORE THE FAULT IS BELIEVED ===============
class AFaultNeverOutranksFinishedWork(Base):
    """THE "BUDGET PER TASK" POST-MORTEM (founder, m-6b177e1cbdf0).

        20:49:04Z  blocked   Shadow asks: "restart the app and sign off"
        20:50:50Z  blocked   founder answers YES -- check #2 is CONFIRMED
        20:50:50Z  running   the loop is relaunched to carry on
        20:51:01Z  failed    "say not delivered (no_live_runtime)"

    Eleven seconds after the founder signed off, with every edit already on
    disk, the task read FAILED. Nothing about the work was consulted: a
    missing runtime for the delegate says the say never LEFT -- it is the
    one outcome that is guaranteed to carry no information about the work.

    Section 1 above pins the decider half of the same disease. This pins the
    other three faults and, more importantly, the rule that covers all of
    them: when Shadow breaks, ASK THE WORK FIRST.
    """

    def _engine2(self, decisions, say_returns=True, evidence="",
                 verifier=None, reader=None):
        """Like Base._engine, but the say and the evidence are the knobs --
        those are what the live failures turned on."""
        self.said = []

        async def sayer(m, text):
            self.said.append(text)
            return say_returns

        async def waiter(m):
            return True

        seq = list(decisions)

        async def decider(ctx):
            return seq.pop(0) if seq else None

        return mission_engine.MissionEngine(
            self.store, sayer, waiter,
            reader if reader is not None else (lambda m: evidence),
            verifier, decider=decider)

    CONTINUE = {"action": "continue", "instruction": "keep going",
                "reason": "still work left"}

    def _checks(self, mid, *checks):
        m = self.store.load(mid)
        m["done_when"] = list(checks)
        self.store.save(m)

    @staticmethod
    def _artifact(text, met=False):
        return {"tier": "contains_artifact", "check": text, "met": met}

    @staticmethod
    def _confirm(text, met=False):
        c = {"tier": "founder_confirm", "check": text}
        if met:
            c.update(met=True, confirmed_by="founder", confirmed_at="t")
        return c

    # ---- the reproduction ------------------------------------------------
    def test_an_undelivered_say_does_not_fail_the_mission(self):
        """The exact Budget-per-task shape, standalone (no goal_id)."""
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._confirm("the founder signed off", met=True))
        out = run(self._engine2([self.CONTINUE],
                                say_returns="no_live_runtime"
                                ).run_mission(mid))
        self.assertNotEqual(out["state"], "failed",
                            "nothing was sent -- that is not a verdict on "
                            "the work")
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out.get("block_reason"), "no_live_runtime")
        self.assertEqual(out.get("failure_class"), "shadow_infra")

    def test_the_undelivered_say_spends_nothing(self):
        mid = self._running()
        before = self.store.load(mid)["turns_used"]
        out = run(self._engine2([self.CONTINUE],
                                say_returns="no_live_runtime"
                                ).run_mission(mid))
        self.assertEqual(out["turns_used"], before,
                         "a say that never left cannot cost a turn")

    def test_a_precondition_id_nobody_listed_still_parks(self):
        """The guard is on the SHAPE, not on a spelling. session_runtime may
        grow a second blocker id tomorrow; it must not arrive as a FAILED
        mission because nobody remembered to list it."""
        mid = self._running()
        out = run(self._engine2([self.CONTINUE],
                                say_returns="runtime_busy_elsewhere"
                                ).run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out.get("block_reason"), "runtime_busy_elsewhere")
        self.assertEqual(out.get("failure_class"), "shadow_infra")

    def test_a_REAL_refusal_still_fails(self):
        """The narrowness of the guard: False means the say was TURNED
        DOWN, which is a real refusal and keeps its terminal state."""
        mid = self._running()
        out = run(self._engine2([self.CONTINUE],
                                say_returns=False).run_mission(mid))
        self.assertEqual(out["state"], "failed")
        self.assertIsNone(out.get("failure_class"))

    # ---- rule 1: finished work beats the fault ---------------------------
    def test_work_already_done_COMPLETES_instead_of_failing(self):
        """m-5c2fca3f824b, the other way round: the checks were already
        satisfiable when the supervisor broke. DONE is the honest answer."""
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"))
        out = run(self._engine2([{"action": "nonsense"}],
                                evidence="worker: SHIPPED it"
                                ).run_mission(mid))
        self.assertEqual(out["state"], "done",
                         "the worker's result must survive Shadow's illness")
        self.assertTrue(out.get("completion"),
                        "and it completes through the ONE completion path")

    def test_an_undelivered_say_on_finished_work_also_completes(self):
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._confirm("signed off", met=True))
        out = run(self._engine2([self.CONTINUE],
                                say_returns="no_live_runtime",
                                evidence="worker: SHIPPED it").run_mission(mid))
        self.assertEqual(out["state"], "done")

    def test_completion_still_needs_the_checks_to_actually_pass(self):
        """NO WEAKENING. The same evidence, one unmet check, and the infra
        exit parks instead of completing -- it cannot wave work through."""
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._artifact("RELEASED"))
        out = run(self._engine2([{"action": "nonsense"}],
                                evidence="worker: SHIPPED it"
                                ).run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertNotEqual(out["state"], "done")

    def test_founder_confirm_is_STILL_not_auto_passable_here(self):
        mid = self._running()
        self._checks(mid, self._confirm("the founder is happy"))
        out = run(self._engine2([{"action": "nonsense"}],
                                evidence="worker: the founder is happy"
                                ).run_mission(mid))
        self.assertNotEqual(out["state"], "done",
                            "prose can never sign a founder_confirm check")

    # ---- rule 2: a signature outstanding is NEEDS YOU, then DONE ---------
    def test_only_a_signature_left_reads_NEEDS_YOU(self):
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._confirm("the founder signed off"))
        out = run(self._engine2([self.CONTINUE],
                                say_returns="no_live_runtime",
                                evidence="worker: SHIPPED it").run_mission(mid))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out.get("pause_reason"), "founder_confirm",
                         "the founder reads this as NEEDS YOU, not FAILED")

    def test_and_the_founders_YES_then_settles_it_DONE(self):
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._confirm("the founder signed off"))
        eng = self._engine2([self.CONTINUE], say_returns="no_live_runtime",
                            evidence="worker: SHIPPED it")
        run(eng.run_mission(mid))
        self.store.confirm_check(mid, 1)
        self.assertEqual(eng.settle(mid)["state"], "done")

    def test_a_BLOCKED_mission_settles_on_the_same_YES(self):
        """The half settle() could not reach. `ask_founder` parks a mission
        in `blocked`, and an intervention that declares confirms_check is
        answered THERE -- so a Yes that closes the last check must finish it
        without another turn. This is the turn m-6b177e1cbdf0 died taking."""
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._confirm("the founder signed off"))
        eng = self._engine2([{"action": "ask_founder", "reason": "sign off?"}],
                            evidence="worker: SHIPPED it")
        self.assertEqual(run(eng.run_mission(mid))["state"], "blocked")
        self.store.confirm_check(mid, 1)
        settled = eng.settle(mid)
        self.assertEqual(settled["state"], "done")
        self.assertEqual(self.said, [],
                         "and it costs no turn in the worker's chat")

    def test_a_blocked_mission_with_work_outstanding_stays_blocked(self):
        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"),
                     self._confirm("the founder signed off"))
        eng = self._engine2([{"action": "ask_founder", "reason": "sign off?"}],
                            evidence="nothing landed yet")
        run(eng.run_mission(mid))
        self.store.confirm_check(mid, 1)
        out = eng.settle(mid)
        self.assertEqual(out["state"], "blocked",
                         "a signature does not verify the machine checks")

    # ---- rule 3: an evaluation that cannot answer is not a failure -------
    def test_a_verifier_that_raises_parks_instead_of_failing(self):
        def boom(check, evidence=""):
            raise RuntimeError("the verifier is broken")

        mid = self._running()
        self._checks(mid, {"tier": "verify", "check": "tests pass"})
        out = run(self._engine2([self.CONTINUE], verifier=boom,
                                evidence="x").run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out.get("block_reason"), "shadow_eval_failed")
        self.assertEqual(out.get("failure_class"), "shadow_infra")

    def test_an_unreadable_transcript_parks_instead_of_failing(self):
        def unreadable(m):
            raise IOError("the transcript is gone")

        mid = self._running()
        self._checks(mid, self._artifact("SHIPPED"))
        out = run(self._engine2([self.CONTINUE],
                                reader=unreadable).run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out.get("block_reason"), "shadow_eval_failed")

    # ---- rule 4: a settled mission is never re-decided -------------------
    def test_a_DONE_mission_is_never_overwritten_by_a_later_fault(self):
        """The m-5c2fca3f824b race exactly: the worker finishes WHILE the
        supervisor's fault is being handled. Completion wins."""
        mid = self._running()
        stale = self.store.load(mid)          # the snapshot the fault holds
        self.store.transition(mid, "done", "the worker finished")
        eng = self._engine2([])
        out = eng._out_of_road(stale, "failed", "shadow_undecided", "late")
        self.assertEqual(out["state"], "done",
                         "a finished mission must not be re-decided")

    def test_a_founder_STOP_mid_fault_is_not_overwritten_either(self):
        mid = self._running()
        stale = self.store.load(mid)
        self.store.transition(mid, "stopped", "founder stopped it")
        out = self._engine2([])._out_of_road(stale, "failed",
                                             "no_live_runtime", "late")
        self.assertEqual(out["state"], "stopped")

    # ---- the boundary: work failures are untouched -----------------------
    def test_budget_exhaustion_is_still_a_FAILED_mission(self):
        mid = self._running()
        m = self.store.load(mid)
        m["turns_used"] = m["max_turns"]
        self.store.save(m)
        out = run(self._engine2([]).run_mission(mid))
        self.assertEqual(out["state"], "failed")
        self.assertIsNone(out.get("failure_class"))

    def test_ping_pong_is_still_a_STOPPED_mission(self):
        mid = self._running()
        same = {"action": "continue", "instruction": "same thing",
                "reason": "r"}
        out = run(self._engine2([same, same]).run_mission(mid))
        self.assertEqual(out["state"], "stopped")

    def test_a_stalled_worker_turn_is_still_the_workers_failure(self):
        """The worker went quiet. That IS a fact about the work, and it
        keeps its historical terminal state."""
        mid = self._running()
        eng = self._engine2([self.CONTINUE])

        async def never(m):
            return False

        eng.waiter = never
        out = run(eng.run_mission(mid))
        self.assertEqual(out["state"], "failed")
        self.assertIsNone(out.get("failure_class"))


# ============ 7. THE WIRING ITSELF, BECAUSE THE BUG WAS THE WIRING =======
class EveryProductionPathCarriesAVerifier(unittest.TestCase):
    """evaluate_done_when was never wrong. `verifier` simply arrived as None
    on every path that could reach it -- start_mission_async defaults it, and
    BOTH resume paths passed a literal None. A unit test of the evaluator
    would have passed throughout. This asserts the plumbing."""

    def _src(self, mod):
        import inspect
        return inspect.getsource(mod)

    def test_no_resume_path_launches_with_a_literal_None_verifier(self):
        src = self._src(shadow_runner)
        self.assertNotIn("_launch(mid, validated_say, None)", src,
                         "a resumed mission must evaluate like a fresh one")

    def test_the_app_hands_a_verifier_to_every_start(self):
        import app
        src = self._src(app)
        starts = src.count("shadow_runner.start_mission_async(")
        wired = src.count("verifier=_shadow_verifier")
        self.assertGreater(starts, 0)
        self.assertGreaterEqual(
            wired, starts,
            "every start_mission_async call must carry the verifier "
            "(%d starts, %d wired)" % (starts, wired))

    def test_the_app_hands_one_to_resume_after_restart_too(self):
        import app
        import re as _re
        src = self._src(app)
        call = _re.search(r"resume_after_restart\((?:[^()]|\([^()]*\))*\)",
                          src)
        self.assertIsNotNone(call, "the resume call must still exist")
        self.assertIn("verifier=_shadow_verifier", call.group(0))

    def test_resume_after_restart_accepts_one(self):
        import inspect
        sig = inspect.signature(shadow_runner.resume_after_restart)
        self.assertIn("verifier", sig.parameters)


if __name__ == "__main__":
    unittest.main(verbosity=2)
