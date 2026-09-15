#!/usr/bin/env python3
"""The outcome is required; what counts as done is not.

WHAT THIS IS FOR (founder, 2026-09-15). The task form asks for two things and
only one of them is the founder's job. The OUTCOME is required -- Shadow does
not guess what you want. "Done when" is OPTIONAL, and when it is left empty
the founder was not declining to be served: they were declining to do
Shadow's job for it.

WHAT IT USED TO COST. evaluate_done_when returns False for an empty set, so a
mission with no checks could never reach `done`. It ran to max_turns and
failed with budget_exhausted -- the founder who left the box empty got a task
that could not finish.

THE SHAPE. Shadow writes them, on its own turn, through the decider that
already runs. `done_when` is an ADDITIVE key on a `continue` decision, exactly
like `intervention` on an ask_founder: absent or malformed and the decision is
byte-identical to what it always was. The prompt asks for them ONLY when the
mission has none, and the write happens ONLY onto an empty set -- so the
founder's own criteria can never be edited, replaced or appended to.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_criteria.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionStore        # noqa: E402

MIS = "/api/shadow/missions"


class CriteriaBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def create(self, **body):
        payload = {"template": "fix", "target_mode": "new"}
        payload.update(body)
        return self.client.post(MIS, json=payload)


# ------------------------------------------------ 1. OBJECTIVE IS REQUIRED --
class ObjectiveIsRequired(CriteriaBase):
    def test_an_empty_objective_is_refused(self):
        r = self.create(objective="")
        self.assertEqual(r.status_code, 400)
        self.assertIn("objective required", r.text)

    def test_a_whitespace_only_objective_is_refused(self):
        self.assertEqual(self.create(objective="   \n  ").status_code, 400)

    def test_an_absent_objective_is_refused(self):
        self.assertEqual(self.create().status_code, 400)

    def test_nothing_is_created_when_the_objective_is_refused(self):
        self.create(objective="")
        self.assertEqual(self.store.list(), [],
                         "a refused create must leave no mission behind")

    def test_a_real_objective_is_accepted(self):
        r = self.create(objective="Ship the EMI rounding fix.")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["objective"], "Ship the EMI rounding fix.")


# -------------------------------------- 2. THE FOUNDER'S CRITERIA ARE THEIRS --
class ExplicitCriteriaArePreserved(CriteriaBase):
    FOUNDER = [{"tier": "founder_confirm", "check": "The EMI check passes."},
               {"tier": "founder_confirm", "check": "A tested PR is open."}]

    def test_explicit_done_when_is_stored_verbatim(self):
        r = self.create(objective="Ship it.", done_when=self.FOUNDER)
        self.assertEqual(r.status_code, 200)
        got = r.json()["done_when"]
        self.assertEqual([c["check"] for c in got],
                         [c["check"] for c in self.FOUNDER])
        self.assertTrue(all(c["tier"] == "founder_confirm" for c in got))

    def test_the_prompt_does_not_ask_for_criteria_that_exist(self):
        """A mission that HAS checks is never invited to rewrite them."""
        m = self.store.create("Ship it.", "fix", done_when=self.FOUNDER)
        eng = mission_engine.MissionEngine(self.store, None, None, None)
        ctx = eng._decision_context(self.store.load(m["id"]), "")
        self.assertTrue(ctx["checks"], "the founder's checks must be shown")

    def test_shadow_may_not_overwrite_the_founders_criteria(self):
        """The write happens ONLY onto an empty set."""
        d = mission_engine.validate_decision(
            {"action": "continue", "instruction": "go", "reason": "r",
             "done_when": [{"tier": "founder_confirm", "check": "Shadow's."}]})
        self.assertEqual(d["done_when"][0]["check"], "Shadow's.")
        # the guard that protects the founder's set is the emptiness test
        m = self.store.create("Ship it.", "fix", done_when=self.FOUNDER)
        existing = self.store.load(m["id"]).get("done_when") or []
        self.assertTrue(existing, "precondition: the mission has criteria")
        self.assertFalse(not existing,
                         "a non-empty set must fail the write's guard")


# ------------------------------------ 3. EMPTY CRITERIA -> SHADOW WRITES THEM --
class ShadowWritesTheMissingCriteria(CriteriaBase):
    def test_empty_done_when_is_accepted(self):
        r = self.create(objective="Ship it.", done_when=[])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["done_when"], [])

    def test_an_absent_done_when_is_accepted(self):
        r = self.create(objective="Ship it.")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["done_when"], [])

    def test_the_prompt_ASKS_for_criteria_when_there_are_none(self):
        """THE KEY MUST REACH THE PROMPT. A context key that no placeholder
        renders is silently dropped -- this asserts the rendered text."""
        rendered = shadow_runner._DECIDE_PROMPT % {
            "outcome": "Ship it.", "checks": "- (none)", "turns_used": 1,
            "max_turns": 20, "last_instruction": "(none)",
            "last_response": "(nothing yet)", "founder_response": "(none)",
            "founder_says": "(none)",
            "criteria_ask": shadow_runner._CRITERIA_ASK}
        self.assertIn("THIS MISSION HAS NO COMPLETION CHECKS", rendered)
        self.assertIn('"done_when"', rendered)

    def test_the_prompt_is_SILENT_about_criteria_when_they_exist(self):
        rendered = shadow_runner._DECIDE_PROMPT % {
            "outcome": "Ship it.", "checks": "- #0 [ ] (founder_confirm) x",
            "turns_used": 1, "max_turns": 20, "last_instruction": "(none)",
            "last_response": "(nothing yet)", "founder_response": "(none)",
            "founder_says": "(none)", "criteria_ask": ""}
        self.assertNotIn("THIS MISSION HAS NO COMPLETION CHECKS", rendered)

    def test_a_decision_may_carry_the_checks_shadow_wrote(self):
        d = mission_engine.validate_decision({
            "action": "continue", "instruction": "Start on it.",
            "reason": "opening move",
            "done_when": [{"tier": "founder_confirm",
                           "check": "The EMI check passes."},
                          {"tier": "verify", "check": "The suite is green."}]})
        self.assertEqual([c["check"] for c in d["done_when"]],
                         ["The EMI check passes.", "The suite is green."])
        self.assertEqual([c["tier"] for c in d["done_when"]],
                         ["founder_confirm", "verify"])

    def test_a_decision_without_criteria_is_unchanged(self):
        d = mission_engine.validate_decision(
            {"action": "continue", "instruction": "go", "reason": "r"})
        self.assertNotIn("done_when", d,
                         "the key must be absent, not empty, when unused")

    def test_malformed_criteria_degrade_to_none_and_keep_the_instruction(self):
        for bad in ("not a list", 42, [{"check": ""}], [{"tier": "x",
                                                         "check": "y"}],
                    [{"tier": "contains_artifact", "check": "y"}], ["str"]):
            d = mission_engine.validate_decision(
                {"action": "continue", "instruction": "go", "reason": "r",
                 "done_when": bad})
            self.assertIsNotNone(d, "a bad list must not kill the decision")
            self.assertEqual(d["instruction"], "go")
            self.assertNotIn("done_when", d, "bad rows: %r" % (bad,))

    def test_contains_artifact_is_refused_to_a_decider(self):
        """It is a literal substring search over the worker's words, so a
        STATE can only be satisfied by uttering it. Founder-typed criteria
        already refuse it; a Shadow-written one must too."""
        self.assertNotIn("contains_artifact", mission_engine.DECIDER_TIERS)
        self.assertEqual(mission_engine.validate_done_when(
            [{"tier": "contains_artifact", "check": "HELLO"}]), [])

    def test_the_set_is_capped(self):
        many = [{"tier": "founder_confirm", "check": "c%d" % i}
                for i in range(30)]
        self.assertEqual(len(mission_engine.validate_done_when(many)),
                         mission_engine.MAX_DECIDER_CHECKS)

    def test_a_missing_tier_defaults_to_founder_confirm(self):
        got = mission_engine.validate_done_when([{"check": "It works."}])
        self.assertEqual(got, [{"tier": "founder_confirm",
                                "check": "It works."}])

    def test_written_criteria_make_the_mission_completable(self):
        """THE WHOLE POINT: an empty set can never be met."""
        m = self.store.create("Ship it.", "fix")
        done, results = mission_engine.evaluate_done_when(
            self.store.load(m["id"]), "")
        self.assertFalse(done)
        self.assertEqual(results, [], "no checks -> nothing to meet")
        written = mission_engine.validate_done_when(
            [{"tier": "founder_confirm", "check": "It works."}])
        rec = self.store.load(m["id"])
        rec["done_when"] = written
        self.store.save(rec)
        done, results = mission_engine.evaluate_done_when(
            self.store.load(m["id"]), "")
        self.assertFalse(done, "founder_confirm never auto-passes")
        self.assertEqual(len(results), 1, "now there IS something to meet")
        rec = self.store.load(m["id"])
        rec["done_when"][0]["met"] = True
        self.store.save(rec)
        done, _ = mission_engine.evaluate_done_when(
            self.store.load(m["id"]), "")
        self.assertTrue(done, "a signed-off check completes the mission")


# ------------------------------------------------------- THE LIVE PATH -----
class TheLivePathWritesCriteriaAndFinishes(CriteriaBase):
    """THE DOGFOOD CASE (founder, 2026-09-15): objective set, "Done when"
    left empty. The card said "no check was set, so Shadow will ask" and that
    was the whole defect -- an empty set is SHADOW'S to write, never a
    question to put back to the founder.

    This drives the real run_mission loop, not validate_decision: the engine
    reaches its first decision turn, Shadow's decision carries done_when, the
    engine writes it, and the SAME criteria then satisfy completion. A
    validator test cannot show any of that."""

    OBJECTIVE = "Improve the README installation section."

    def _engine(self, decision, transcript=""):
        """The real engine with the four injected collaborators stubbed."""
        self.says = []
        self.asked = []

        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        def reader(m):
            return transcript

        eng = mission_engine.MissionEngine(self.store, sayer, waiter, reader)

        async def decider(context):
            self.asked.append(context)
            return dict(decision)

        eng.decider = decider
        # NOTHING BOUNDS THIS BUT THE BUDGET. The stub decider always says
        # `continue` and the founder_confirm check is never signed off, so the
        # loop runs to max_turns and ends `failed`. That is the point: the
        # criteria are written on the FIRST decision turn and everything
        # asserted below is true long before the budget runs out.
        return eng

    def _mission(self):
        """Exactly what the composer posts: objective set, done_when empty,
        briefed at spawn like every target_mode=new task."""
        r = self.create(objective=self.OBJECTIVE, done_when=[])
        mid = r.json()["id"]
        m = self.store.load(mid)
        m["manifest_delivered"] = True          # the spawn delivered the brief
        m["target_session"] = "sess-live"
        self.store.save(m)
        self.store.transition(mid, "running", "admitted")
        return mid

    def test_shadow_writes_the_criteria_and_never_asks_the_founder(self):
        import asyncio
        mid = self._mission()
        self.assertEqual(self.store.load(mid)["done_when"], [],
                         "precondition: the founder left it open")

        eng = self._engine({
            "action": "continue",
            "instruction": "Rewrite the install steps and show me the diff.",
            "reason": "the outcome names the README install section",
            "done_when": [
                {"tier": "founder_confirm",
                 "check": "The README install section lists every step."},
                {"tier": "founder_confirm",
                 "check": "The steps work on a clean clone."}]})
        asyncio.get_event_loop().run_until_complete(eng.run_mission(mid))

        m = self.store.load(mid)
        checks = m.get("done_when") or []
        # 1. the criteria exist, and they are SHADOW's
        self.assertEqual(len(checks), 2,
                         "Shadow must write the criteria the founder left open")
        self.assertEqual(
            [c["check"] for c in checks],
            ["The README install section lists every step.",
             "The steps work on a clean clone."])
        # 2. they are CONCRETE -- a state, not a restatement of the objective
        for c in checks:
            self.assertNotEqual(c["check"].strip().lower(),
                                self.OBJECTIVE.strip().lower())
            self.assertTrue(len(c["check"]) > 10)
        # 3. the founder was NOT asked. This is the defect this test exists for
        self.assertNotIn(m["state"], ("blocked",),
                         "an empty Done when must never block on the founder")
        self.assertIsNone(m.get("block_reason"))
        self.assertIsNone(m.get("intervention"))
        self.assertEqual(self.store.load(mid).get("pause_reason"), None)
        # 4. the prompt Shadow actually saw carried the ask
        self.assertTrue(self.asked, "the decider must have been consulted")
        self.assertEqual(self.asked[0]["outcome"], self.OBJECTIVE)
        self.assertEqual(self.asked[0]["checks"], [],
                         "the first decision turn sees an empty set")

    def test_the_written_criteria_are_what_completion_then_uses(self):
        """Written once, then they behave exactly like founder-typed ones."""
        import asyncio
        mid = self._mission()
        eng = self._engine({
            "action": "continue", "instruction": "go", "reason": "r",
            "done_when": [{"tier": "founder_confirm",
                           "check": "The install steps are complete."}]})
        asyncio.get_event_loop().run_until_complete(eng.run_mission(mid))

        m = self.store.load(mid)
        self.assertEqual(len(m["done_when"]), 1)
        # unmet -> not done, exactly as a founder-typed founder_confirm
        done, results = mission_engine.evaluate_done_when(m, "")
        self.assertFalse(done)
        self.assertEqual(len(results), 1,
                         "the written check is what completion evaluates")
        # signed off -> done
        m["done_when"][0]["met"] = True
        self.store.save(m)
        done, _ = mission_engine.evaluate_done_when(self.store.load(mid), "")
        self.assertTrue(done, "Shadow's criteria complete the mission")

    def test_shadow_is_not_invited_to_rewrite_founder_criteria_live(self):
        """The same loop, but the founder DID say -- nothing is overwritten."""
        import asyncio
        mine = [{"tier": "founder_confirm", "check": "The founder's own."}]
        r = self.create(objective=self.OBJECTIVE, done_when=mine)
        mid = r.json()["id"]
        m = self.store.load(mid)
        m["manifest_delivered"] = True
        m["target_session"] = "sess-live"
        self.store.save(m)
        self.store.transition(mid, "running", "admitted")

        eng = self._engine({
            "action": "continue", "instruction": "go", "reason": "r",
            "done_when": [{"tier": "founder_confirm", "check": "Shadow's."}]})
        asyncio.get_event_loop().run_until_complete(eng.run_mission(mid))

        checks = self.store.load(mid)["done_when"]
        self.assertEqual([c["check"] for c in checks], ["The founder's own."],
                         "a founder's criteria may never be replaced")
        self.assertTrue(self.asked)
        self.assertTrue(self.asked[0]["checks"],
                        "and the prompt shows them, so no ask is rendered")


# ----------------------------- THE FIRST DECISION, ON THE BRIEFED PATH -----
class TheBarExistsBeforeTheWorkerIsSupervised(CriteriaBase):
    """THE DOGFOOD FAILURE (founder, 2026-09-15). Objective set, "Done when"
    blank, mission started -- and the card sat on "Shadow is writing these"
    at TURN 0 while the worker was already on turn 1 and exploring.

    ROOT CAUSE, pinned here. A target_mode="new" delegate is briefed by the
    SPAWN, so provision_target stamps manifest_delivered and run_mission takes
    its `briefed` branch, which sends nothing AND set `decision = None`. That
    None was the only thing that could have carried Shadow's criteria, so the
    whole first turn ran with an empty completion bar and nothing was written
    until turn 1 -- if the mission lived that long.

    These drive the REAL run_mission on the REAL briefed shape. A test that
    lets the loop run to the budget cannot see this: the criteria do arrive
    eventually. The bar has to exist on the FIRST turn, and that is what is
    asserted."""

    OBJECTIVE = ("Update the project README to explain what Shadow does "
                 "and how to run the Shadow tests.")
    WROTE = [{"tier": "founder_confirm",
              "check": "The README explains what Shadow does."},
             {"tier": "founder_confirm",
              "check": "The README shows how to run the Shadow tests."}]

    def _briefed_mission(self, done_when=None):
        """Exactly what the composer + spawn produce."""
        r = self.create(objective=self.OBJECTIVE, done_when=done_when or [])
        mid = r.json()["id"]
        m = self.store.load(mid)
        m["manifest_delivered"] = True     # the SPAWN delivered the brief
        m["target_session"] = "sess-live"
        m["max_turns"] = 1                 # one iteration, then stop
        self.store.save(m)
        self.store.transition(mid, "running", "admitted")
        return mid

    def _run(self, mid, decision):
        import asyncio
        self.says, self.seen = [], []

        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        def reader(m):
            return ""

        eng = mission_engine.MissionEngine(self.store, sayer, waiter, reader)

        async def decider(ctx):
            self.seen.append(ctx)
            return dict(decision)

        eng.decider = decider
        asyncio.new_event_loop().run_until_complete(eng.run_mission(mid))
        return self.store.load(mid)

    def test_the_criteria_exist_after_the_FIRST_turn(self):
        mid = self._briefed_mission()
        self.assertEqual(self.store.load(mid)["done_when"], [])
        m = self._run(mid, {"action": "continue", "instruction": "explore",
                            "reason": "r", "done_when": self.WROTE})
        self.assertEqual([c["check"] for c in m["done_when"]],
                         [c["check"] for c in self.WROTE],
                         "the bar must exist on the first turn, not turn 1")

    def test_shadow_is_actually_consulted_on_that_turn(self):
        mid = self._briefed_mission()
        self._run(mid, {"action": "continue", "instruction": "explore",
                        "reason": "r", "done_when": self.WROTE})
        self.assertTrue(self.seen, "the decider was never asked (the bug)")
        self.assertEqual(self.seen[0]["checks"], [],
                         "and it must be asked while the set is still empty, "
                         "so criteria_ask renders")
        self.assertEqual(self.seen[0]["outcome"], self.OBJECTIVE)

    def test_the_brief_is_NOT_sent_twice(self):
        """The spawn already briefed the delegate. The criteria pass must
        discard the instruction it came with."""
        mid = self._briefed_mission()
        self._run(mid, {"action": "continue",
                        "instruction": "THIS MUST NOT REACH THE WORKER",
                        "reason": "r", "done_when": self.WROTE})
        self.assertNotIn("THIS MUST NOT REACH THE WORKER", self.says)
        self.assertEqual(self.says, [],
                         "a briefed turn 0 says nothing, before and after")

    def test_the_criteria_are_PERSISTED_not_held_in_memory(self):
        """Re-read from the store, not from the dict the loop mutated."""
        mid = self._briefed_mission()
        self._run(mid, {"action": "continue", "instruction": "explore",
                        "reason": "r", "done_when": self.WROTE})
        fresh = mission_engine.MissionStore().load(mid)   # a NEW store object
        self.assertEqual(len(fresh["done_when"]), 2,
                         "the checks must survive on disk for the UI to read")
        for c in fresh["done_when"]:
            self.assertIn("tier", c)
            self.assertIn("check", c)

    def test_what_the_UI_reads_back_carries_the_criteria(self):
        """The card renders from GET /api/shadow/missions -- the same read
        the 4s refresh does. A criteria write the API does not serve is a
        write the founder never sees."""
        mid = self._briefed_mission()
        self._run(mid, {"action": "continue", "instruction": "explore",
                        "reason": "r", "done_when": self.WROTE})
        rows = self.client.get(MIS).json()["missions"]
        row = [r for r in rows if r["id"] == mid][0]
        self.assertEqual([c["check"] for c in row["done_when"]],
                         [c["check"] for c in self.WROTE],
                         "the refreshed mission state must carry the bar")

    def test_those_criteria_are_what_completion_then_measures(self):
        mid = self._briefed_mission()
        m = self._run(mid, {"action": "continue", "instruction": "explore",
                            "reason": "r", "done_when": self.WROTE})
        done, results = mission_engine.evaluate_done_when(m, "")
        self.assertFalse(done)
        self.assertEqual(len(results), 2, "both checks are evaluated")
        m["done_when"][0]["met"] = True
        m["done_when"][1]["met"] = True
        self.store.save(m)
        done, _ = mission_engine.evaluate_done_when(
            self.store.load(mid), "")
        self.assertTrue(done)

    def test_a_founder_who_DID_say_is_never_consulted_about_it(self):
        """The prompt does not even carry the request, and nothing is
        overwritten."""
        mine = [{"tier": "founder_confirm", "check": "The founder's own."}]
        mid = self._briefed_mission(done_when=mine)
        m = self._run(mid, {"action": "continue", "instruction": "x",
                            "reason": "r", "done_when": self.WROTE})
        self.assertEqual([c["check"] for c in m["done_when"]],
                         ["The founder's own."])
        self.assertEqual(self.seen, [],
                         "a briefed turn 0 WITH criteria must not spend a "
                         "decider turn at all")

    def test_a_failing_decider_costs_nothing(self):
        """Turn 1 asks again; the mission is not harmed."""
        import asyncio
        mid = self._briefed_mission()

        async def sayer(m, text):
            return True

        async def waiter(m):
            return True

        eng = mission_engine.MissionEngine(self.store, sayer, waiter,
                                           lambda m: "")

        async def boom(ctx):
            raise RuntimeError("shadow is down")

        eng.decider = boom
        asyncio.new_event_loop().run_until_complete(eng.run_mission(mid))
        m = self.store.load(mid)
        self.assertEqual(m["done_when"], [], "nothing written, nothing broken")


# ------------------------------------- 5. BEFORE THE FIRST WORKER CONTACT --
class TheBarExistsBeforeTheWorkerIsSpokenTo(CriteriaBase):
    """The order the founder asked for, asserted as an ORDER.

    Objective entered -> Shadow decides done_when -> persisted -> FIRST
    worker interaction. The turn-0 tests above prove the criteria arrive on
    the first loop iteration; they cannot see that the spawn already briefed
    the worker before that iteration began. This records the sequence
    itself: what the spawner sees when it is handed the mission.
    """

    OBJECTIVE = "Update the README to explain what Shadow does."
    WROTE = [{"tier": "founder_confirm",
              "check": "The README explains what Shadow does."}]

    def _provision(self, done_when=None):
        """Run the real provision_target with a spawner that RECORDS the
        mission as it stood when the brief went out."""
        import asyncio
        mid = self.create(objective=self.OBJECTIVE,
                          done_when=done_when or []).json()["id"]
        self.at_spawn, self.seen = [], []

        async def spawner(m):
            # the first Shadow -> Worker interaction: read from the STORE,
            # not from the dict handed in, so this is what the UI would see
            self.at_spawn.append(
                list(self.store.load(m["id"]).get("done_when") or []))
            return "sess-live"

        async def decider(ctx):
            self.seen.append(ctx)
            return {"action": "continue", "instruction": "explore",
                    "reason": "r", "done_when": self.WROTE}

        eng = mission_engine.MissionEngine(self.store, None, None, None,
                                           decider=decider)
        asyncio.new_event_loop().run_until_complete(
            eng.provision_target(mid, spawner))
        return mid

    def test_blank_done_when_is_filled_BEFORE_the_worker_is_briefed(self):
        mid = self._provision()
        self.assertEqual(len(self.at_spawn), 1, "the spawner ran once")
        self.assertEqual([c["check"] for c in self.at_spawn[0]],
                         [c["check"] for c in self.WROTE],
                         "the criteria must be on disk BEFORE the spawner "
                         "sends the brief -- not after the first turn")
        self.assertEqual([c["check"] for c in
                          self.store.load(mid)["done_when"]],
                         [c["check"] for c in self.WROTE])

    def test_the_UI_can_read_them_before_the_worker_ever_answers(self):
        mid = self._provision()
        row = [r for r in self.client.get(MIS).json()["missions"]
               if r["id"] == mid][0]
        self.assertEqual([c["check"] for c in row["done_when"]],
                         [c["check"] for c in self.WROTE])

    def test_a_founder_who_supplied_them_is_not_consulted_at_all(self):
        mine = [{"tier": "founder_confirm", "check": "The founder's own."}]
        mid = self._provision(done_when=mine)
        self.assertEqual(self.seen, [], "Shadow must generate nothing")
        self.assertEqual([c["check"] for c in self.at_spawn[0]],
                         ["The founder's own."],
                         "used exactly, and still before the brief")
        self.assertEqual([c["check"] for c in
                          self.store.load(mid)["done_when"]],
                         ["The founder's own."])

    def test_a_failing_decider_still_spawns_the_worker(self):
        """The bar is worth a decider turn, never the mission."""
        import asyncio
        mid = self.create(objective=self.OBJECTIVE,
                          done_when=[]).json()["id"]

        async def spawner(m):
            return "sess-live"

        async def boom(ctx):
            raise RuntimeError("shadow is down")

        eng = mission_engine.MissionEngine(self.store, None, None, None,
                                           decider=boom)
        sid = asyncio.new_event_loop().run_until_complete(
            eng.provision_target(mid, spawner))
        self.assertEqual(sid, "sess-live")
        self.assertEqual(self.store.load(mid)["done_when"], [],
                         "nothing written; turn 0 asks again")

    def test_an_existing_target_mission_decides_before_ITS_first_say(self):
        """No spawn on this path -- turn 0's say is the first contact."""
        import asyncio
        r = self.client.post(MIS, json={"template": "fix",
                                        "target_mode": "existing",
                                        "target_session": "sess-live",
                                        "objective": self.OBJECTIVE,
                                        "done_when": []})
        mid = r.json()["id"]
        m = self.store.load(mid)
        m["max_turns"] = 1
        self.store.save(m)
        self.store.transition(mid, "running", "admitted")
        at_say = []

        async def sayer(mission, text):
            at_say.append(
                list(self.store.load(mission["id"]).get("done_when") or []))
            return True

        async def waiter(mission):
            return True

        async def decider(ctx):
            return {"action": "continue", "instruction": "explore",
                    "reason": "r", "done_when": self.WROTE}

        eng = mission_engine.MissionEngine(self.store, sayer, waiter,
                                           lambda mission: "",
                                           decider=decider)
        asyncio.new_event_loop().run_until_complete(eng.run_mission(mid))
        self.assertTrue(at_say, "turn 0 said the brief")
        self.assertEqual([c["check"] for c in at_say[0]],
                         [c["check"] for c in self.WROTE],
                         "the bar must be on disk before the first say")


# --------------------------------------------------------------- untouched --
class NothingElseMoved(CriteriaBase):
    def test_delete_still_works(self):
        mid = self.create(objective="Ship it.").json()["id"]
        r = self.client.post("%s/%s/act" % (MIS, mid),
                             json={"action": "delete"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("deleted"))
        self.assertIsNone(self.store.load(mid))

    def test_say_anything_still_works(self):
        mid = self.create(objective="Ship it.").json()["id"]
        self.store.transition(mid, "running", "admitted")
        r = self.client.post("%s/%s/act" % (MIS, mid),
                             json={"action": "say", "text": "go carefully"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([s["text"] for s in
                          self.store.load(mid)["founder_says"]],
                         ["go carefully"])

    def test_ask_founder_and_its_intervention_are_unchanged(self):
        d = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "which region?"})
        self.assertEqual(d["action"], "ask_founder")
        self.assertNotIn("done_when", d,
                         "criteria ride on continue only")


if __name__ == "__main__":
    unittest.main(verbosity=2)
