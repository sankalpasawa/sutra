"""V5 slice 4: goal-level progress and verification state.

Two independent numbers, no third invented one:

    checks_met / checks_total   the outcome
    turns_used / max_turns      the cost

Progress is DERIVED on read from stored per-check results, so it can never
drift from the results it describes, and a blocked or stopped goal keeps
everything it had already proven.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import goal_lifecycle
import mission_engine
import providers
import shadow_egress
import shadow_runner
from goal_store import GoalStore
from mission_engine import MissionEngine, MissionScheduler, MissionStore

C_ART = "contains_artifact"


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

    def three_check_goal(self, session="01a081"):
        return self.goals.create(
            "ship the connector retry fix", session,
            done_when=[{"tier": C_ART, "check": "BUILD OK"},
                        {"tier": C_ART, "check": "RETRY OK"},
                        {"tier": C_ART, "check": "INTEGRATION OK"}])

    def engine(self, transcripts, on_evaluated=None):
        """Real evaluator, real evidence filter, scripted chat output."""
        self.says = []

        async def sayer(mission, text):
            self.says.append(text)
            return True

        async def waiter(mission):
            return True

        def reader(mission):
            i = min(len(self.says) - 1, len(transcripts) - 1)
            said = transcripts[i] if transcripts else ""
            doc = {"id": mission["target_session"], "messages": [
                {"role": "user",
                 "text": shadow_egress.say_tag(mission["id"]) + " "
                         + " ".join(self.says)},
                {"role": "assistant", "text": said},
            ]}
            doc["messages"] = shadow_runner.evidence_messages(doc)
            return json.dumps(doc)

        return MissionEngine(
            self.missions, sayer, waiter, reader,
            on_evaluated=on_evaluated or (
                lambda m, r, d: goal_lifecycle.record_evaluation(m, r, d)))

    def drive(self, goal, transcripts, budget=None):
        m = goal_lifecycle.start_first_attempt(goal["id"])
        if budget is not None:
            mm = self.missions.load(m["id"])
            mm["max_turns"] = budget
            self.missions.save(mm)
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))
        out = asyncio.run(self.engine(transcripts).run_mission(m["id"]))
        return goal_lifecycle.on_attempt_end(out), out, m


class TestCheckCounting(Base):
    def test_01_three_checks_none_satisfied_reads_zero_of_three(self):
        g = self.three_check_goal()
        p = self.goals.progress(g["id"])
        self.assertEqual((p["checks_met"], p["checks_total"]), (0, 3))
        self.assertEqual(p["checks_label"], "0 of 3 checks")
        self.assertEqual(len(p["checks"]), 3)
        self.assertEqual([c["met"] for c in p["checks"]],
                         [False, False, False])
        self.assertEqual(p["unmet"], ["BUILD OK", "RETRY OK",
                                      "INTEGRATION OK"])
        self.assertIsNone(p["turn_label"],
                          "no attempt has run -- do not invent a ceiling")
        self.assertIsNone(p["last_evaluated_at"])

    def test_02_two_of_three_satisfied_reads_two_of_three(self):
        g = self.three_check_goal()
        goal, out, _m = self.drive(
            g, ["BUILD OK", "BUILD OK RETRY OK"], budget=2)
        self.assertEqual(out["state"], "blocked", "the third never lands")
        p = self.goals.progress(g["id"])
        self.assertEqual((p["checks_met"], p["checks_total"]), (2, 3))
        self.assertEqual(p["checks_label"], "2 of 3 checks")
        self.assertEqual([c["met"] for c in p["checks"]],
                         [True, True, False])
        self.assertEqual(p["unmet"], ["INTEGRATION OK"])

    def test_03_all_satisfied_reads_three_of_three_and_completes(self):
        g = self.three_check_goal()
        goal, out, _m = self.drive(
            g, ["BUILD OK RETRY OK INTEGRATION OK"])
        self.assertEqual(out["state"], "done")
        self.assertEqual(goal["state"], "done")
        p = self.goals.progress(g["id"])
        self.assertEqual(p["checks_label"], "3 of 3 checks")
        self.assertEqual(p["checks_met"], 3)
        self.assertEqual(p["unmet"], [])
        self.assertEqual(p["state"], "done")

    def test_04_no_percentage_is_ever_exposed(self):
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK"], budget=1)
        p = self.goals.progress(g["id"])
        for key in p:
            self.assertNotIn("percent", key.lower())
            self.assertNotIn("pct", key.lower())
        self.assertNotIn("%", p["checks_label"])


class TestPersistence(Base):
    def test_05_check_results_survive_a_reload(self):
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK", "BUILD OK RETRY OK"], budget=2)
        fresh = GoalStore()
        held = fresh.load(g["id"])
        self.assertEqual(len(held["check_results"]), 3)
        row = held["check_results"][0]
        self.assertEqual(row["check"], "BUILD OK")
        self.assertEqual(row["tier"], C_ART)
        self.assertTrue(row["met"])
        self.assertTrue(row["evaluated_at"], "when it was last evaluated")
        self.assertTrue(row["mission_id"], "and which attempt evaluated it")
        self.assertEqual(row["attempt"], 1)
        self.assertEqual(fresh.progress(g["id"])["checks_label"],
                         "2 of 3 checks")

    def test_06_results_are_rows_not_a_prose_summary(self):
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK"], budget=1)
        held = self.goals.load(g["id"])
        self.assertIsInstance(held["check_results"], list)
        for row in held["check_results"]:
            self.assertIsInstance(row, dict)
            for field in ("index", "tier", "check", "met", "evaluated_at"):
                self.assertIn(field, row)

    def test_07_the_definition_stays_pristine(self):
        """done_when is the definition; results live beside it."""
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK"], budget=1)
        held = self.goals.load(g["id"])
        self.assertEqual(held["done_when"],
                         [{"tier": C_ART, "check": "BUILD OK"},
                          {"tier": C_ART, "check": "RETRY OK"},
                          {"tier": C_ART, "check": "INTEGRATION OK"}])


class TestStatePreservation(Base):
    def test_08_a_blocked_goal_keeps_its_results_and_its_blocker(self):
        g = self.three_check_goal()
        goal, out, _m = self.drive(g, ["BUILD OK", "BUILD OK"], budget=2)
        self.assertEqual(goal["state"], "blocked")
        p = self.goals.progress(g["id"])
        self.assertEqual(p["state"], "blocked")
        self.assertEqual(p["checks_label"], "1 of 3 checks",
                         "progress is not lost when work stops")
        self.assertEqual(p["block_reason"], "budget_exhausted")
        self.assertEqual(p["turn_label"], "turn 2/2")

    def test_09_a_stopped_goal_keeps_its_last_known_results(self):
        g = self.three_check_goal()
        goal, _out, _m = self.drive(g, ["BUILD OK", "BUILD OK"], budget=2)
        self.assertEqual(goal["state"], "blocked")
        stopped = goal_lifecycle.abandon(g["id"], "not worth it")
        self.assertEqual(stopped["state"], "stopped")
        p = self.goals.progress(g["id"])
        self.assertEqual(p["state"], "stopped")
        self.assertEqual(p["checks_label"], "1 of 3 checks")
        self.assertEqual([c["met"] for c in p["checks"]],
                         [True, False, False])

    def test_10_verifying_shows_the_latest_results(self):
        g = self.goals.create(
            "ship it", "01a083",
            done_when=[{"tier": C_ART, "check": "BUILD OK"},
                        {"tier": "founder_confirm", "check": "sign off"}])
        goal, out, m = self.drive(g, ["BUILD OK"])
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_confirm")
        self.assertEqual(goal["state"], "verifying")
        p = self.goals.progress(g["id"])
        self.assertEqual(p["state"], "verifying")
        self.assertEqual(p["checks_label"], "1 of 2 checks")
        self.assertEqual(p["unmet"], ["sign off"])

    def test_11_resuming_keeps_what_was_already_proven(self):
        g = self.three_check_goal()
        goal, _out, _m = self.drive(g, ["BUILD OK", "BUILD OK"], budget=2)
        self.assertEqual(self.goals.progress(g["id"])["checks_met"], 1)
        second = goal_lifecycle.resume_goal(g["id"], extra_turns=3)
        mid_resume = self.goals.progress(g["id"])
        self.assertEqual(mid_resume["checks_met"], 1,
                         "a resumed goal does not forget its progress")
        # the attempt exists but is not admitted yet, so the goal is still
        # blocked and still says why (slice 3 contract)
        self.assertEqual(mid_resume["state"], "blocked")
        self.assertEqual(mid_resume["block_reason"], "budget_exhausted")
        MissionScheduler(self.missions).start(second["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(second["id"]))
        running = self.goals.progress(g["id"])
        self.assertEqual(running["state"], "working")
        self.assertIsNone(running["block_reason"],
                          "the blocker clears once the goal is working")
        self.assertEqual(running["checks_met"], 1,
                         "and the proven checks still stand")


class TestBudgetSemantics(Base):
    def test_12_turns_are_exposed_separately_from_check_progress(self):
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK", "BUILD OK"], budget=2)
        p = self.goals.progress(g["id"])
        self.assertEqual((p["turns_used"], p["max_turns"]), (2, 2))
        self.assertEqual(p["turn_label"], "turn 2/2")
        # the two numbers are independent: 2 turns spent, 1 check met
        self.assertEqual(p["checks_met"], 1)
        self.assertNotEqual(p["turns_used"], p["checks_met"])

    def test_13_extending_adds_to_the_ceiling_and_keeps_turns_used(self):
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK", "BUILD OK"], budget=2)
        before = self.goals.progress(g["id"])
        self.assertEqual(before["turn_label"], "turn 2/2")
        second = goal_lifecycle.resume_goal(g["id"], extra_turns=3)
        self.assertEqual(second["turns_used"], 2)
        self.assertEqual(second["max_turns"], 5)
        after = self.goals.progress(g["id"])
        self.assertEqual(after["turns_used"], 2, "never reset")
        self.assertEqual(after["max_turns"], 5, "ceiling raised")
        self.assertEqual(after["turn_label"], "turn 2/5")
        self.assertEqual(after["attempt"], 2)

    def test_14_turn_count_is_never_presented_as_task_progress(self):
        """Turns can be spent with nothing proven -- and it must show."""
        g = self.three_check_goal()
        self.drive(g, ["nothing useful", "nothing useful"], budget=2)
        p = self.goals.progress(g["id"])
        self.assertEqual(p["turn_label"], "turn 2/2")
        self.assertEqual(p["checks_label"], "0 of 3 checks")


class TestVerificationIntegrityPreserved(Base):
    def test_15_shadow_authored_text_still_cannot_satisfy_a_check(self):
        """The engine's reader here runs the real evidence filter, and the
        say echoes every check name -- none of it may count."""
        g = self.three_check_goal()
        goal, out, _m = self.drive(g, ["still working on it"], budget=2)
        p = self.goals.progress(g["id"])
        self.assertEqual(p["checks_label"], "0 of 3 checks")
        self.assertEqual(out["state"], "blocked")
        # prove the phrases really were in the raw say
        joined = " ".join(self.says)
        self.assertIn("BUILD OK", joined,
                      "the follow-up prompt names the unmet checks")

    def test_16_genuine_chat_output_still_counts(self):
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK RETRY OK INTEGRATION OK"])
        self.assertEqual(self.goals.progress(g["id"])["checks_label"],
                         "3 of 3 checks")


class TestNonGoalUnchanged(Base):
    def test_17_a_standalone_mission_records_no_goal_progress(self):
        solo = self.missions.create(
            "do the thing", "fix",
            done_when=[{"tier": C_ART, "check": "OK"}])
        self.missions.transition(solo["id"], "brief_confirm")
        self.missions.transition(solo["id"], "running")
        self.assertIsNone(solo["goal_id"])
        seen = []
        eng = self.engine(["OK"], on_evaluated=lambda m, r, d: seen.append(
            goal_lifecycle.record_evaluation(m, r, d)))
        out = asyncio.run(eng.run_mission(solo["id"]))
        self.assertEqual(out["state"], "done", "unchanged verification")
        self.assertEqual(seen, [None], "the hook no-ops without a goal")
        self.assertEqual(self.goals.list(), [])

    def test_18_the_observer_is_optional_and_never_load_bearing(self):
        """A raising observer cannot change a mission's outcome."""
        solo = self.missions.create(
            "do the thing", "fix",
            done_when=[{"tier": C_ART, "check": "OK"}])
        self.missions.transition(solo["id"], "brief_confirm")
        self.missions.transition(solo["id"], "running")

        def boom(mission, results, done):
            raise RuntimeError("progress bookkeeping exploded")

        out = asyncio.run(self.engine(["OK"], on_evaluated=boom)
                          .run_mission(solo["id"]))
        self.assertEqual(out["state"], "done")

    def test_19_the_evaluator_itself_is_untouched(self):
        mission = {"done_when": [
            {"tier": C_ART, "check": "ALL GREEN"},
            {"tier": "verify", "check": "build"},
            {"tier": "founder_confirm", "check": "sign off"}]}
        done, results = mission_engine.evaluate_done_when(
            mission, "tests ALL GREEN", verifier=lambda c: True)
        self.assertFalse(done, "founder_confirm never auto-passes")
        self.assertEqual([r["met"] for r in results], [True, True, False])


class TestProgressApiShape(Base):
    def test_20_progress_is_domain_level_only(self):
        """No routes, no UI -- the projection is a store method."""
        g = self.three_check_goal()
        self.assertTrue(hasattr(self.goals, "progress"))
        p = self.goals.progress(g["id"])
        self.assertEqual(p["goal_id"], g["id"])
        self.assertEqual(p["outcome"], "ship the connector retry fix")
        self.assertEqual(p["target_session"], "01a081")
        with self.assertRaises(ValueError):
            self.goals.progress("g-nope")

    def test_21_progress_is_derived_not_a_stored_summary(self):
        """Editing done_when changes the denominator immediately."""
        g = self.three_check_goal()
        self.drive(g, ["BUILD OK"], budget=1)
        self.assertEqual(self.goals.progress(g["id"])["checks_total"], 3)
        held = self.goals.load(g["id"])
        held["done_when"] = held["done_when"][:2]
        self.goals.save(held)
        p = self.goals.progress(g["id"])
        self.assertEqual(p["checks_total"], 2, "counted from the definition")
        self.assertEqual(p["checks_label"], "1 of 2 checks")


if __name__ == "__main__":
    unittest.main()
