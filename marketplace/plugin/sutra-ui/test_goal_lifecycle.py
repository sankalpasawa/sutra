"""V5 slice 3: the Goal <-> Mission lifecycle.

The behavioural change this slice exists for, stated as tests: work that
runs out of road BLOCKS and waits for the founder in the SAME chat, instead
of failing terminally and offering a fresh one -- but only for work that
belongs to a goal. A standalone mission keeps every bit of its historical
terminal behaviour.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import goal_lifecycle
import goal_store
import mission_engine
import providers
from goal_store import GoalStore
from mission_engine import MissionEngine, MissionScheduler, MissionStore


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.goals = GoalStore()
        self.missions = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # -- fixtures ---------------------------------------------------------
    def goal(self, outcome="ship the connector retry fix", session="01a081",
             checks=(("contains_artifact", "ALL GREEN"),)):
        return self.goals.create(
            outcome, session,
            done_when=[{"tier": t, "check": c} for t, c in checks])

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

        return MissionEngine(self.missions, sayer, waiter, reader)

    def run_attempt(self, mission, **kw):
        """Admit the attempt and drive it to whatever it reaches."""
        MissionScheduler(self.missions).start(mission["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(mission["id"]))
        out = asyncio.run(self.engine(**kw).run_mission(mission["id"]))
        return goal_lifecycle.on_attempt_end(out), out


class TestAttemptStart(Base):
    def test_01_first_attempt_binds_and_moves_the_goal_to_working(self):
        g = self.goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.assertEqual(m["state"], "brief_confirm")
        self.assertEqual(m["goal_id"], g["id"])
        self.assertEqual(m["target_session"], "01a081")
        self.assertEqual(m["target_mode"], "existing",
                         "a goal attempt never provisions a fresh chat")
        held = self.goals.load(g["id"])
        self.assertEqual(held["current_mission_id"], m["id"])
        self.assertEqual(held["state"], "draft", "not working until admitted")
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))
        self.assertEqual(self.goals.load(g["id"])["state"], "working")

    def test_02_the_attempt_inherits_the_goals_outcome_and_checks(self):
        g = self.goal(outcome="make the retry idempotent",
                      checks=(("contains_artifact", "retry:"),
                              ("founder_confirm", "founder signs off")))
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.assertEqual(m["objective"], "make the retry idempotent")
        self.assertEqual([c["check"] for c in m["done_when"]],
                         ["retry:", "founder signs off"])

    def test_03_one_live_attempt_and_the_right_starting_state(self):
        g = self.goal()
        goal_lifecycle.start_first_attempt(g["id"])
        with self.assertRaises(ValueError):
            goal_lifecycle.start_first_attempt(g["id"])
        with self.assertRaises(ValueError):
            goal_lifecycle.resume_goal(g["id"])   # not blocked
        with self.assertRaises(ValueError):
            goal_lifecycle.start_first_attempt("g-nope")


class TestBudgetBecomesBlocked(Base):
    def test_04_max_turns_blocks_a_goal_attempt_instead_of_failing(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 2
        self.missions.save(mm)
        goal, out = self.run_attempt(m, transcripts=["nope", "still nope"])
        self.assertEqual(out["state"], "blocked",
                         "budget exhaustion must no longer fail the work")
        self.assertEqual(out["block_reason"], "budget_exhausted")
        self.assertNotIn(out["state"], mission_engine.TERMINAL)
        self.assertEqual(goal["state"], "blocked")
        # the historical ledger wording is preserved
        import shadow_ledger
        notes = [r["note"] for r in shadow_ledger.read("missions", 100)
                 if r.get("mission_id") == m["id"]]
        self.assertTrue(any("max turns" in n for n in notes), notes)

    def test_05_ping_pong_blocks_a_goal_attempt_instead_of_stopping(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        # NOTE the explicit transcript: the default reader replays Shadow's
        # own says, and _next_say interpolates unmet check names into the
        # prompt, so a check would satisfy itself (see report).
        goal, out = self.run_attempt(m, transcripts=["nope", "nope"])
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "ping_pong")
        self.assertEqual(goal["state"], "blocked")
        import shadow_ledger
        notes = [r["note"] for r in shadow_ledger.read("missions", 100)
                 if r.get("mission_id") == m["id"]]
        self.assertTrue(any("ping-pong" in n for n in notes), notes)

    def test_06_standalone_missions_keep_failed_and_stopped(self):
        """The boundary that keeps every shipped path unchanged."""
        solo = self.missions.create("do the thing", "fix",
                                    done_when=[{"tier": "contains_artifact",
                                                "check": "NEVER"}])
        self.assertIsNone(solo["goal_id"])
        self.missions.transition(solo["id"], "brief_confirm")
        self.missions.transition(solo["id"], "running")
        mm = self.missions.load(solo["id"])
        mm["max_turns"] = 2
        self.missions.save(mm)
        out = asyncio.run(self.engine(
            transcripts=["a", "b"]).run_mission(solo["id"]))
        self.assertEqual(out["state"], "failed", "unchanged for standalone")

        solo2 = self.missions.create("again", "fix")
        self.missions.transition(solo2["id"], "brief_confirm")
        self.missions.transition(solo2["id"], "running")
        out2 = asyncio.run(self.engine().run_mission(solo2["id"]))
        self.assertEqual(out2["state"], "stopped", "unchanged for standalone")


class TestBlockedGoal(Base):
    def _blocked(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, out = self.run_attempt(m, transcripts=["nope", "nope"])
        self.assertEqual(out["state"], "blocked")
        return goal, out

    def test_07_the_target_chat_survives_and_is_unchanged(self):
        goal, out = self._blocked()
        self.assertEqual(goal["target_session"], "01a081")
        self.assertEqual(out["target_session"], "01a081")
        self.assertEqual(len(self.goals.list(target_session="01a081")), 1,
                         "no second goal is minted for the same chat")

    def test_08_the_goal_persists_with_the_attempt_recorded(self):
        goal, out = self._blocked()
        fresh = GoalStore().load(goal["id"])
        self.assertEqual(fresh["state"], "blocked")
        self.assertEqual(len(fresh["attempts"]), 1)
        row = fresh["attempts"][0]
        self.assertEqual(row["mission_id"], out["id"])
        self.assertEqual(row["ended_state"], "blocked")
        self.assertEqual(row["ended_state"], "blocked")
        self.assertIsNone(fresh["current_mission_id"],
                          "the ended attempt is released per the store "
                          "contract, so a new one can bind")

    def test_09_blocked_frees_the_scheduler_slot_and_the_queue_moves(self):
        sched = MissionScheduler(self.missions, max_running=1)
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        self.assertEqual(sched.start(m["id"])["state"], "running")
        other = self.missions.create("unrelated work", "fix")
        self.missions.transition(other["id"], "brief_confirm")
        self.assertEqual(sched.start(other["id"])["state"], "queued")
        out = asyncio.run(self.engine(
            transcripts=["nope", "nope"]).run_mission(m["id"]))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(
            [x["id"] for x in self.missions.list(states=("running",))], [],
            "a blocked attempt holds no slot")
        promoted = sched.on_terminal(m["id"])
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["id"], other["id"])


class TestResume(Base):
    def _blocked_on_budget(self, budget=2):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        mm = self.missions.load(m["id"])
        mm["max_turns"] = budget
        self.missions.save(mm)
        goal, out = self.run_attempt(m, transcripts=["x", "y"])
        self.assertEqual(out["state"], "blocked")
        return goal, out

    def test_10_resume_runs_a_new_attempt_in_the_same_chat(self):
        goal, first = self._blocked_on_budget()
        second = goal_lifecycle.resume_goal(goal["id"], extra_turns=3)
        self.assertNotEqual(second["id"], first["id"],
                            "a new attempt, not a revived one")
        self.assertEqual(second["target_session"], first["target_session"])
        self.assertEqual(second["goal_id"], goal["id"])
        self.assertEqual(second["state"], "brief_confirm")
        held = self.goals.load(goal["id"])
        self.assertEqual(held["current_mission_id"], second["id"])
        self.assertEqual(held["state"], "blocked",
                         "still blocked until the attempt is admitted")

    def test_11_the_previous_attempt_stays_on_the_record(self):
        goal, first = self._blocked_on_budget()
        goal_lifecycle.resume_goal(goal["id"], extra_turns=3)
        held = self.goals.load(goal["id"])
        self.assertEqual([a["attempt"] for a in held["attempts"]], [1, 2])
        self.assertEqual(held["attempts"][0]["mission_id"], first["id"])
        self.assertEqual(held["attempts"][0]["ended_state"], "blocked")
        self.assertIsNone(held["attempts"][1]["ended_at"])
        self.assertEqual(self.goals.attempt_count(goal["id"]), 2)

    def test_12_resuming_moves_the_goal_back_to_working(self):
        goal, _first = self._blocked_on_budget()
        second = goal_lifecycle.resume_goal(goal["id"], extra_turns=3)
        MissionScheduler(self.missions).start(second["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(second["id"]))
        self.assertEqual(self.goals.load(goal["id"])["state"], "working")

    def test_13_budget_carries_forward_and_extending_adds_to_it(self):
        goal, first = self._blocked_on_budget(budget=2)
        self.assertEqual(self.missions.load(first["id"])["turns_used"], 2)
        second = goal_lifecycle.resume_goal(goal["id"], extra_turns=3)
        self.assertEqual(second["turns_used"], 2, "turns are preserved")
        self.assertEqual(second["max_turns"], 5, "extend adds, never resets")

    def test_14_resuming_without_extending_re_blocks_honestly(self):
        goal, _first = self._blocked_on_budget(budget=2)
        second = goal_lifecycle.resume_goal(goal["id"], extra_turns=0)
        goal2, out = self.run_attempt(second, transcripts=["x"])
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "budget_exhausted")
        self.assertEqual(goal2["state"], "blocked")
        self.assertEqual(self.goals.attempt_count(goal["id"]), 2)

    def test_15_founder_confirmations_survive_a_resume(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),
                              ("founder_confirm", "founder signs off")))
        m = goal_lifecycle.start_first_attempt(g["id"])
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 1
        self.missions.save(mm)
        self.missions.confirm_check(m["id"], 1)
        goal, _out = self.run_attempt(m, transcripts=["x"])
        self.assertEqual(goal["state"], "blocked")
        second = goal_lifecycle.resume_goal(goal["id"], extra_turns=2)
        self.assertTrue(second["done_when"][1]["met"],
                        "a founder confirmation is a fact about the world, "
                        "not about one attempt")


class TestVerifyingAndDone(Base):
    def test_16_verification_completes_the_goal(self):
        g = self.goal(checks=(("contains_artifact", "ALL GREEN"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, out = self.run_attempt(
            m, transcripts=["working on it", "tests ALL GREEN"])
        self.assertEqual(out["state"], "done")
        self.assertEqual(goal["state"], "done")
        self.assertEqual(goal["attempts"][0]["ended_state"], "done")
        self.assertIsNone(goal["current_mission_id"])
        self.assertIn("result_excerpt", out)

    def test_17_an_outstanding_founder_check_reads_as_verifying(self):
        g = self.goal(checks=(("contains_artifact", "ALL GREEN"),
                              ("founder_confirm", "founder signs off")))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, out = self.run_attempt(m, transcripts=["tests ALL GREEN"])
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_confirm")
        self.assertEqual(goal["state"], "verifying")
        self.assertEqual(goal["current_mission_id"], m["id"],
                         "the attempt is not over -- the same mission "
                         "resumes on confirmation")

    def test_18_confirming_the_check_carries_verifying_to_done(self):
        g = self.goal(checks=(("contains_artifact", "ALL GREEN"),
                              ("founder_confirm", "founder signs off")))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, _out = self.run_attempt(m, transcripts=["tests ALL GREEN"])
        self.assertEqual(goal["state"], "verifying")
        self.missions.confirm_check(m["id"], 1)
        self.missions.transition(m["id"], "running", "founder confirmed")
        out2 = asyncio.run(self.engine(
            transcripts=["tests ALL GREEN"]).run_mission(m["id"]))
        self.assertEqual(out2["state"], "done")
        goal2 = goal_lifecycle.on_attempt_end(out2)
        self.assertEqual(goal2["state"], "done")

    def test_19_a_goal_never_completes_because_an_attempt_merely_stopped(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, out = self.run_attempt(m, transcripts=["nope", "nope"])
        self.assertEqual(out["state"], "blocked")
        self.assertNotEqual(goal["state"], "done")
        # and a machine-side failure asks rather than completing or dying
        g2 = self.goal(session="01a082", checks=(("contains_artifact", "N"),))
        m2 = goal_lifecycle.start_first_attempt(g2["id"])
        goal2, out2 = self.run_attempt(m2, say_ok=False)
        self.assertEqual(out2["state"], "failed", "the ATTEMPT still fails")
        self.assertEqual(goal2["state"], "blocked",
                         "a goal cannot die without the founder being asked")


class TestFounderControl(Base):
    def test_20_founder_stop_of_the_attempt_stops_the_goal(self):
        g = self.goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))
        eng = MissionEngine(self.missions, None, None, None)
        stopped = eng.founder_stop(m["id"])
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(stopped["ended_by"], "founder")
        goal = goal_lifecycle.on_attempt_end(stopped)
        self.assertEqual(goal["state"], "stopped")
        self.assertEqual(goal["attempts"][0]["ended_state"], "stopped")

    def test_21_abandon_stops_the_live_attempt_and_the_goal(self):
        g = self.goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))
        goal = goal_lifecycle.abandon(g["id"], "not worth it")
        self.assertEqual(goal["state"], "stopped")
        self.assertEqual(self.missions.load(m["id"])["state"], "stopped")
        self.assertIsNone(goal["current_mission_id"])
        # idempotent
        self.assertEqual(goal_lifecycle.abandon(g["id"])["state"], "stopped")

    def test_22_abandoning_a_blocked_goal_needs_no_live_mission(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, _out = self.run_attempt(m, transcripts=["nope", "nope"])
        self.assertEqual(goal["state"], "blocked")
        self.assertEqual(goal_lifecycle.abandon(g["id"])["state"], "stopped")

    def test_23_intervention_and_floor_pauses_leave_the_goal_working(self):
        """Existing takeover and floor behaviour is reused, not changed:
        Shadow pauses in that chat and the founder is already present, so
        the goal is not moved."""
        g = self.goal()
        m = goal_lifecycle.start_first_attempt(g["id"])
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))
        eng = MissionEngine(self.missions, None, None, None)
        paused = eng.founder_intervened(m["id"])
        self.assertEqual(paused["pause_reason"], "founder_intervened")
        goal = goal_lifecycle.on_attempt_end(paused)
        self.assertEqual(goal["state"], "working")
        self.assertEqual(goal["current_mission_id"], m["id"],
                         "the attempt is only paused; it can resume")

    def test_24_a_floored_say_pauses_without_moving_the_goal(self):
        g = self.goal(outcome="clean the branch with git reset --hard")
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, out = self.run_attempt(m)
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "floor_confirm")
        self.assertEqual(self.says, [], "a floored say must never leave")
        self.assertEqual(goal["state"], "working")


class TestHookSafety(Base):
    def test_25_the_hooks_no_op_for_a_mission_with_no_goal(self):
        solo = self.missions.create("standalone", "fix")
        self.assertIsNone(goal_lifecycle.on_attempt_start(solo))
        self.assertIsNone(goal_lifecycle.on_attempt_end(solo))
        self.assertIsNone(goal_lifecycle.on_attempt_end(None))

    def test_26_on_attempt_end_is_idempotent(self):
        g = self.goal(checks=(("contains_artifact", "NEVER"),))
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal, out = self.run_attempt(m, transcripts=["nope", "nope"])
        self.assertEqual(goal["state"], "blocked")
        again = goal_lifecycle.on_attempt_end(out)
        self.assertEqual(again["state"], "blocked")
        self.assertEqual(len(again["attempts"]), 1, "no duplicate rows")

    def test_27_a_runner_goal_sync_failure_never_breaks_the_mission(self):
        import shadow_runner
        m = self.missions.create("orphaned attempt", "fix",
                                 goal_id="g-does-not-exist")
        self.assertIsNone(shadow_runner._goal_hook("on_attempt_end", m),
                          "a broken goal must not take down the runner")
        self.assertEqual(self.missions.load(m["id"])["state"], "draft")


if __name__ == "__main__":
    unittest.main()
