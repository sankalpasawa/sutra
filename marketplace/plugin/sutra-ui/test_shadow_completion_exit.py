#!/usr/bin/env python3
"""RUNNING OUT OF ROAD IS NOT A VERDICT ON THE WORK.

The companion to test_shadow_supervisor_recovery. That file pins the rule
for a fault in the SUPERVISOR; this one pins it for the four endings the
MACHINE decides -- the budget is spent, the chat repeated itself, the turn
stalled, the say was turned down. Each of those wrote a terminal state with
`evaluate_done_when` sitting one screen away, unasked.

WHAT WAS MEASURED (founder, 2026-09-16), reproduced against the real engine
with a stub sayer/waiter and a worker transcript that says the work is
finished:

    all checks founder_confirm  -> failed  (3 turns, 3 says)
    identical instruction twice -> stopped (2 turns, 2 says)

All-`founder_confirm` is the DEFAULT shape, not an edge case:
shadow_protocol.tier_for demotes every check that is not a short literal
marker. Such a mission has NO exit to `done` inside the loop -- so it drove
until the budget was spent and died `failed`, with the founder never asked
for the one thing that could have finished it. m-cd009367d41a died that way
with four of its five checks passing.

THE FIX IS TWO RULES AND NO NEW STATE:

  A. _out_of_road consults the work (_work_first) before every ordinary
     ending, exactly as _infra_exit already did for supervisor faults.
  B. confirmation_reachable: once the attempt has been DRIVEN and every
     outstanding check is one only the founder can sign, the ending is
     NEEDS YOU, never FAILED. confirmation_is_due is untouched, so the
     in-loop first-evaluation safety is byte-identical.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_completion_exit.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import shadow_runner
from mission_engine import MissionStore


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


CONTINUE = {"action": "continue", "instruction": "carry on", "reason": "r"}
FINISHED = "I have finished the work. Everything asked for is in place."


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
        self.transcript = FINISHED

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig_settings
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ---- fixtures ------------------------------------------------------
    def mission(self, checks=None, max_turns=3, **extra):
        m = self.store.create("Ship the thing.", "feature",
                              target_mode="new", target_session="sess-1",
                              done_when=checks, **extra)
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        m["max_turns"] = max_turns
        self.store.save(m)
        return m["id"]

    def engine(self, decisions=None, sayer=None, waiter=None,
               verifier=None, vary=True):
        """A loop whose decider answers from a list. `said` records every
        instruction that actually left the engine."""
        self.said = []
        n = {"i": 0}

        async def _sayer(m, text):
            self.said.append(text)
            return True

        async def _waiter(m):
            return True

        async def decider(ctx):
            n["i"] += 1
            if decisions:
                return dict(decisions[min(n["i"] - 1, len(decisions) - 1)])
            out = dict(CONTINUE)
            if vary:                      # so ping-pong does not fire first
                out["instruction"] = "carry on #%d" % n["i"]
            return out

        return mission_engine.MissionEngine(
            self.store, sayer or _sayer, waiter or _waiter,
            lambda m: self.transcript, verifier, decider=decider)

    def confirm_all(self, mid):
        m = self.store.load(mid)
        for i, _c in enumerate(m["done_when"]):
            self.store.confirm_check(mid, i)


CONFIRM = [{"tier": "founder_confirm", "check": "The feature works."},
           {"tier": "founder_confirm", "check": "Nothing else broke."}]
ARTIFACT_MET = [{"tier": "contains_artifact", "check": "finished the work"}]
ARTIFACT_UNMET = [{"tier": "contains_artifact", "check": "NEVER-THERE"}]


# =============== 1. THE DEFAULT SHAPE REACHES THE FOUNDER ===============
class AllFounderConfirmReachesNeedsYou(Base):

    def test_out_of_turns_is_needs_you_not_failed(self):
        mid = self.mission(CONFIRM)
        out = run(self.engine().run_mission(mid))
        self.assertEqual(out["state"], "paused",
                         "a signature nobody was asked for is not a failure")
        self.assertEqual(out["pause_reason"], "founder_confirm")
        self.assertEqual(out["turns_used"], 3, "the budget was still spent")

    def test_ping_pong_is_needs_you_not_stopped(self):
        mid = self.mission(CONFIRM)
        out = run(self.engine([CONTINUE, CONTINUE]).run_mission(mid))
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_confirm")

    def test_the_founders_yes_then_completes_it(self):
        """The waiting room is the SHIPPED one: settle_confirmation turns
        the signature into `done` with no extra turn."""
        mid = self.mission(CONFIRM)
        out = run(self.engine().run_mission(mid))
        self.assertEqual(out["state"], "paused")
        self.confirm_all(mid)
        eng = mission_engine.MissionEngine(
            self.store, None, None, lambda m: self.transcript)
        done = eng.settle(mid)
        self.assertEqual(done["state"], "done")
        self.assertEqual(len(self.said), 3,
                         "settling costs no further say")

    def test_nothing_here_satisfies_a_check(self):
        mid = self.mission(CONFIRM)
        run(self.engine().run_mission(mid))
        for c in self.store.load(mid)["done_when"]:
            self.assertFalse(c.get("met"),
                             "only the founder may satisfy this tier")


# ============ 2. A DONE MISSION COMPLETES INSTEAD OF ENDING =============
class TheWorkWinsOverTheEnding(Base):

    def test_ping_pong_completes_a_mission_whose_checks_are_met(self):
        mid = self.mission(ARTIFACT_MET)
        out = run(self.engine([CONTINUE, CONTINUE]).run_mission(mid))
        self.assertEqual(out["state"], "done")
        self.assertTrue(out.get("completion"))

    def test_a_stalled_turn_evaluates_before_it_fails(self):
        mid = self.mission(ARTIFACT_MET)

        async def never(m):
            return False

        out = run(self.engine(waiter=never).run_mission(mid))
        self.assertEqual(out["state"], "done",
                         "a boundary nobody saw is not a lost result")

    def test_a_refused_say_evaluates_before_it_fails(self):
        mid = self.mission(ARTIFACT_MET)
        m = self.store.load(mid)
        m["turns_used"] = 1            # a turn already landed the evidence
        self.store.save(m)

        async def refuse(m_, text):
            return False

        out = run(self.engine(sayer=refuse).run_mission(mid))
        self.assertEqual(out["state"], "done")


# ================ 3. THE OLD GUARDS ARE STILL GUARDS ====================
class UnfinishedWorkStillEndsExactlyAsBefore(Base):

    def test_budget_with_an_unmet_machine_check_still_fails(self):
        mid = self.mission(ARTIFACT_UNMET)
        out = run(self.engine().run_mission(mid))
        self.assertEqual(out["state"], "failed")
        self.assertNotIn("block_reason", out)
        self.assertIsNone(out.get("failure_class"))

    def test_ping_pong_with_an_unmet_machine_check_still_stops(self):
        mid = self.mission(ARTIFACT_UNMET)
        out = run(self.engine([CONTINUE, CONTINUE]).run_mission(mid))
        self.assertEqual(out["state"], "stopped")
        self.assertNotIn("block_reason", out)

    def test_a_stalled_turn_with_unmet_checks_is_still_a_failure(self):
        mid = self.mission(ARTIFACT_UNMET)

        async def never(m):
            return False

        out = run(self.engine(waiter=never).run_mission(mid))
        self.assertEqual(out["state"], "failed")
        self.assertIsNone(out.get("failure_class"))

    def test_a_mission_with_no_criteria_keeps_its_historical_ending(self):
        """No bar means nothing to sign and nothing to meet, so this is
        NOT the founder-confirm waiting room -- the ending is unchanged."""
        mid = self.mission(None)
        out = run(self.engine().run_mission(mid))
        self.assertEqual(out["state"], "failed")

    def test_a_goal_attempt_still_blocks_rather_than_failing(self):
        mid = self.mission(ARTIFACT_UNMET, goal_id="g-abc123")
        out = run(self.engine().run_mission(mid))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "budget_exhausted")


# ========== 4. A REFUSED SAY GOES THROUGH THE FUNNEL LIKE THE REST ======
class ARefusedSayTakesTheSameExit(Base):

    def _refusing(self, mid, **kw):
        async def refuse(m_, text):
            return False
        return run(self.engine(sayer=refuse, **kw).run_mission(mid))

    def test_unfinished_work_still_fails_with_the_same_note(self):
        mid = self.mission(ARTIFACT_UNMET)
        out = self._refusing(mid)
        self.assertEqual(out["state"], "failed")
        rows = [json.loads(ln) for ln
                in (Path(self.tmp.name) / "ledger" / "missions.jsonl")
                .read_text().splitlines()]
        self.assertIn("say refused", rows[-1]["note"])

    def test_a_goal_attempt_is_escalated_instead_of_killed(self):
        mid = self.mission(ARTIFACT_UNMET, goal_id="g-abc123")
        out = self._refusing(mid)
        self.assertEqual(out["state"], "blocked",
                         "a goal must never die without the founder asked")
        self.assertEqual(out["block_reason"], "say_refused")


# ====== 5. AN UNOBSERVABLE BOUNDARY IS SHADOW'S FAULT, NOT THE WORKER'S ==
class AMissingBoundaryQueueIsInfra(Base):

    def test_the_waiter_names_the_precondition(self):
        """The real binding, not a stub: no observer attached to this
        session means no queue, and the wait never happens."""
        sayer, waiter, _reader = shadow_runner.make_bindings(
            lambda *a, **k: None)
        got = run(waiter({"target_session": "no-such-session",
                          "id": "m-x", "turns_used": 0}))
        self.assertEqual(got, "no_boundary_queue")
        self.assertIsNot(got, False, "a string is not a stall")

    def test_the_engine_parks_it_instead_of_failing_the_mission(self):
        mid = self.mission(ARTIFACT_UNMET)

        async def unobservable(m):
            return "no_boundary_queue"

        out = run(self.engine(waiter=unobservable).run_mission(mid))
        self.assertEqual(out["state"], "blocked", "NEEDS YOU, not FAILED")
        self.assertEqual(out["block_reason"], "no_boundary_queue")
        self.assertEqual(out["failure_class"],
                         mission_engine.INFRA_FAILURE_CLASS)

    def test_and_completes_the_mission_when_the_work_was_done(self):
        mid = self.mission(ARTIFACT_MET)

        async def unobservable(m):
            return "no_boundary_queue"

        out = run(self.engine(waiter=unobservable).run_mission(mid))
        self.assertEqual(out["state"], "done")


# =========== 6. THE FIRST-EVALUATION SAFETY IS BYTE-IDENTICAL ===========
class ConfirmationRulesUnchanged(unittest.TestCase):

    def test_confirmation_is_due_is_exactly_what_it_was(self):
        due = mission_engine.confirmation_is_due
        confirm = {"tier": "founder_confirm", "met": False}
        machine_ok = {"tier": "verify", "met": True}
        machine_no = {"tier": "verify", "met": False}
        self.assertFalse(due([]), "no results is not due")
        self.assertFalse(due(None))
        self.assertFalse(due([confirm]),
                         "ALL founder_confirm is NOT due -- all([]) is True "
                         "and that was the m-b7d534be84d7 bug")
        self.assertFalse(due([dict(confirm), dict(confirm)]))
        self.assertFalse(due([confirm, machine_no]))
        self.assertTrue(due([confirm, machine_ok]))
        self.assertFalse(due([machine_ok]), "nothing left to confirm")

    def test_reachable_is_turn_gated(self):
        reach = mission_engine.confirmation_reachable
        confirm = {"tier": "founder_confirm", "met": False}
        self.assertFalse(reach([confirm], 0),
                         "nothing was driven: the historical ending stands")
        self.assertFalse(reach([confirm], None))
        self.assertTrue(reach([confirm], 1))

    def test_reachable_refuses_an_unmet_machine_check(self):
        reach = mission_engine.confirmation_reachable
        confirm = {"tier": "founder_confirm", "met": False}
        self.assertFalse(
            reach([confirm, {"tier": "verify", "met": False}], 3),
            "a machine check nobody satisfied is not a signature")
        self.assertFalse(
            reach([confirm, {"tier": "contains_artifact", "met": False}], 3))
        self.assertTrue(reach([confirm, {"tier": "verify", "met": True}], 3))

    def test_reachable_refuses_an_empty_or_satisfied_set(self):
        reach = mission_engine.confirmation_reachable
        self.assertFalse(reach([], 3), "no bar is not a signature")
        self.assertFalse(reach(None, 3))
        self.assertFalse(reach([{"tier": "founder_confirm", "met": True}], 3),
                         "every check met is evaluate_done_when's word")

    def test_reachable_is_wider_than_due_at_turn_one(self):
        """The ending path asks the wider question; the loop keeps the
        narrow one. Anything due is reachable -- never the reverse."""
        cases = [
            [{"tier": "founder_confirm", "met": False}],
            [{"tier": "founder_confirm", "met": False},
             {"tier": "verify", "met": True}],
            [{"tier": "founder_confirm", "met": False},
             {"tier": "verify", "met": False}],
            [{"tier": "verify", "met": True}],
            [],
        ]
        for r in cases:
            if mission_engine.confirmation_is_due(r):
                self.assertTrue(mission_engine.confirmation_reachable(r, 1),
                                r)


class TheLoopStillDrivesBeforeItAsks(Base):

    def test_the_first_evaluation_does_not_pause(self):
        """m-b7d534be84d7: an all-founder_confirm mission paused on its
        FIRST evaluation having verified nothing and driven nothing. The
        loop must keep driving; only the END of the road asks."""
        mid = self.mission(CONFIRM, max_turns=9)
        eng = self.engine()
        seen = []
        real = eng._await_confirmation

        def spy(m_id):
            seen.append(self.store.load(m_id)["turns_used"])
            return real(m_id)

        eng._await_confirmation = spy
        out = run(eng.run_mission(mid))
        self.assertEqual(out["turns_used"], 9,
                         "every turn of the budget was driven first")
        self.assertEqual(seen, [9], "asked once, at the end, not at turn 1")
        self.assertEqual(len(self.said), 9)


# ====== 7. A COMPLETED MISSION CAN NEVER BE REGRESSED AFTERWARDS ========
class DoneIsFinal(Base):
    """The completion is the WORKER'S. No later fault in Shadow -- an
    ending path, a supervisor fault, a crashed loop, a bookkeeping hook --
    may take it back."""

    def _done(self):
        mid = self.mission(ARTIFACT_MET)
        out = run(self.engine().run_mission(mid))
        self.assertEqual(out["state"], "done")
        return mid, out

    def test_an_ordinary_ending_hands_back_the_completion(self):
        mid, done = self._done()
        eng = self.engine()
        m = dict(done)
        for reason, terminal in (("budget_exhausted", "failed"),
                                 ("ping_pong", "stopped"),
                                 ("turn_stalled", "failed"),
                                 ("say_refused", "failed")):
            out = eng._out_of_road(m, terminal, reason, "late %s" % reason)
            self.assertEqual(out["state"], "done", reason)
        self.assertEqual(self.store.load(mid)["state"], "done")

    def test_a_supervisor_fault_hands_back_the_completion(self):
        mid, done = self._done()
        eng = self.engine()
        for reason in sorted(mission_engine.INFRA_BLOCK_REASONS):
            out = eng._infra_exit(dict(done), reason, "late %s" % reason)
            self.assertEqual(out["state"], "done", reason)
            self.assertIsNone(out.get("failure_class"), reason)
        self.assertEqual(self.store.load(mid)["state"], "done")

    def test_the_state_machine_itself_refuses_every_exit_from_done(self):
        """Belt and braces: even a caller that skips both funnels cannot
        write a terminal state over a completion."""
        mid, _done = self._done()
        self.assertEqual(mission_engine.TRANSITIONS["done"], ())
        for target in ("failed", "stopped", "blocked", "paused", "running"):
            with self.assertRaises(ValueError, msg=target):
                self.store.transition(mid, target, "late")
        with self.assertRaises(ValueError):
            self.store.block(mid, "shadow_crashed", "late crash")
        self.assertEqual(self.store.load(mid)["state"], "done")

    def test_the_runner_crash_handler_leaves_it_done(self):
        """shadow_runner._launch's last-resort handler: block() raises on a
        done mission, the fallback transition raises too, and the record it
        hands back is the completion."""
        mid, _done = self._done()
        store = self.store
        try:
            m = store.block(mid, "shadow_crashed", "runner crashed: boom")
            m["failure_class"] = mission_engine.INFRA_FAILURE_CLASS
            store.save(m)
        except Exception:
            try:
                m = store.transition(mid, "failed", "runner crashed: boom")
            except Exception:
                m = store.load(mid)
        self.assertEqual(m["state"], "done")
        self.assertIsNone(m.get("failure_class"))

    def test_settle_cannot_reopen_a_done_mission(self):
        mid, _done = self._done()
        eng = mission_engine.MissionEngine(
            self.store, None, None, lambda m: "")
        out = eng.settle(mid)
        self.assertEqual(out["state"], "done")

    def test_the_completion_summary_survives(self):
        mid, done = self._done()
        head = done["completion"]["headline"]
        self.engine()._out_of_road(dict(done), "failed", "budget_exhausted",
                                   "late")
        self.assertEqual(
            self.store.load(mid)["completion"]["headline"], head)


if __name__ == "__main__":
    unittest.main(verbosity=2)
