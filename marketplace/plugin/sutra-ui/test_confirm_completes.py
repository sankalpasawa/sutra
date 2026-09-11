"""Confirming the last check finishes the Assignment -- with no extra turn.

THE DEAD END (live, goal g-e59b36c8ae53, 2026-09-11):

  04:29:37  the loop evaluates, one founder_confirm check is outstanding
            -> mission paused (pause_reason=founder_confirm)
            -> run_mission RETURNS, the runner's task ends, RUNNING drops it
            -> on_attempt_end -> goal verifying
  04:30:44  the founder clicks Confirm done
            -> confirm_check writes met/confirmed_by/confirmed_at
            -> record_founder_confirmation makes the goal read 2 of 2
            -> and nothing else. No transition, no re-evaluation.

`evaluate_done_when` is what turns "all checks met" into a done mission,
and it only ever ran inside a loop that had already exited 67 seconds
earlier. The Assignment was stuck permanently, not slowly.

Two properties are pinned here and they pull against each other, which is
why both are tested rather than assumed:

  ONE COMPLETION PATH   MissionEngine._complete is the only writer of a
                        `done` mission; settle() reaches THAT, it does not
                        carry a copy.
  NO EXTRA TURN         the loop says BEFORE it evaluates, so resuming it
                        would have put another Shadow turn in the founder's
                        chat to learn something already true.
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
import shadow_runner
from goal_store import GoalStore
from mission_engine import MissionEngine, MissionStore

SID = "afddb07f-4ad1-4172-8b86-481d2aa02437"
PHRASE = "docker compose up -d"
JUDGEMENT = ("That phrase sits in the final answer as the command to run, "
             "in a code block, not buried in prose as an aside")

_LOOP = None


def _ensure_loop():
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return _ensure_loop().run_until_complete(coro)


class Base(unittest.TestCase):
    def setUp(self):
        _ensure_loop()
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self.goals = GoalStore()
        self.transcript = "the answer is:\n```\n%s\n```\n" % PHRASE
        self.says = []

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def engine(self):
        """The production shape: a reader, no verifier."""
        async def sayer(m, text):
            self.says.append(text)
            return True

        async def waiter(m):
            return True

        return MissionEngine(
            self.store, sayer, waiter, lambda m: self.transcript,
            # exactly what shadow_runner._launch wires: without it the goal
            # never learns what the loop evaluated, and progress reads 0
            on_evaluated=lambda mission, results, done:
                goal_lifecycle.record_evaluation(mission, results, done))

    def goal_paused_on_confirm(self, done_when=None):
        """Drive the REAL loop until it parks on the founder_confirm."""
        g = self.goals.create(
            outcome="the chat gives the docker command",
            target_session=SID,
            done_when=done_when or [
                {"tier": "contains_artifact", "check": PHRASE},
                {"tier": "founder_confirm", "check": JUDGEMENT}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal_lifecycle.on_attempt_start(m)
        self.store.transition(m["id"], "running", "admitted")
        eng = self.engine()
        m = run(eng.run_mission(m["id"]))
        goal_lifecycle.on_attempt_end(m)
        return g["id"], m["id"]

    def settle(self, mid):
        """shadow_runner.settle_confirmation with the test's own reader --
        the same MissionEngine.settle the production helper calls."""
        eng = MissionEngine(
            self.store, None, None, lambda m: self.transcript,
            on_evaluated=lambda mission, results, done:
                goal_lifecycle.record_evaluation(mission, results, done))
        out = eng.settle(mid)
        goal_lifecycle.on_attempt_end(out)
        return out


class TestTheParkedAttempt(Base):
    """Reproduce the live state before touching it."""

    def test_01_the_loop_parks_on_the_outstanding_confirmation(self):
        gid, mid = self.goal_paused_on_confirm()
        m = self.store.load(mid)
        self.assertEqual(m["state"], "paused")
        self.assertEqual(m["pause_reason"], "founder_confirm")
        self.assertEqual(m["turns_used"], 1)
        self.assertEqual(self.goals.load(gid)["state"], "verifying")
        self.assertEqual(len(self.says), 1, "exactly one turn was spent")

    def test_02_the_machine_checked_tier_is_already_met(self):
        gid, _mid = self.goal_paused_on_confirm()
        p = self.goals.progress(gid)
        self.assertEqual(p["checks_label"], "1 of 2 checks")
        self.assertEqual(p["unmet"], [JUDGEMENT])


class TestFinalConfirmationCompletes(Base):
    """The fix."""

    def test_03_confirming_the_last_check_reaches_done(self):
        gid, mid = self.goal_paused_on_confirm()
        self.store.confirm_check(mid, 1)
        goal_lifecycle.record_founder_confirmation(self.store.load(mid))
        self.settle(mid)
        self.assertEqual(self.store.load(mid)["state"], "done")
        self.assertEqual(self.goals.load(gid)["state"], "done",
                         "verifying -> done, which is what was stuck")

    def test_04_no_extra_turn_is_sent_or_counted(self):
        gid, mid = self.goal_paused_on_confirm()
        before = self.store.load(mid)["turns_used"]
        self.store.confirm_check(mid, 1)
        self.settle(mid)
        self.assertEqual(self.says, [self.says[0]],
                         "NOTHING was said into the founder's chat")
        self.assertEqual(self.store.load(mid)["turns_used"], before,
                         "and no turn was consumed")
        self.assertEqual(self.goals.progress(gid)["turns_used"], before)

    def test_05_progress_reads_complete(self):
        gid, mid = self.goal_paused_on_confirm()
        self.store.confirm_check(mid, 1)
        goal_lifecycle.record_founder_confirmation(self.store.load(mid))
        self.settle(mid)
        p = self.goals.progress(gid)
        self.assertEqual(p["checks_label"], "2 of 2 checks")
        self.assertEqual(p["unmet"], [])

    def test_06_the_attempt_row_is_closed(self):
        gid, mid = self.goal_paused_on_confirm()
        self.store.confirm_check(mid, 1)
        self.settle(mid)
        row = self.goals.load(gid)["attempts"][-1]
        self.assertEqual(row["mission_id"], mid)
        self.assertEqual(row["ended_state"], "done")
        self.assertIsNotNone(row["ended_at"])
        self.assertIsNone(self.goals.load(gid)["current_mission_id"])

    def test_07_the_history_says_what_happened(self):
        _gid, mid = self.goal_paused_on_confirm()
        self.store.confirm_check(mid, 1)
        self.settle(mid)
        rows = [json.loads(l) for l in
                open(__import__("shadow_ledger")._path("missions"),
                     encoding="utf-8") if mid in l]
        notes = [r["note"] for r in rows]
        self.assertIn("founder confirmed check 1", notes)
        self.assertTrue(any("settles the attempt" in n for n in notes),
                        "the resume is recorded, not hidden: %s" % notes)
        self.assertTrue(any(n.startswith("done_when met") for n in notes))
        self.assertEqual([r["state"] for r in rows][-1], "done")


class TestNonFinalConfirmation(Base):
    """Confirming one of several leaves everything where it was."""

    def _two_judgements(self):
        return [{"tier": "contains_artifact", "check": PHRASE},
                {"tier": "founder_confirm", "check": JUDGEMENT},
                {"tier": "founder_confirm", "check": "reads well"}]

    def test_08_a_non_final_confirmation_keeps_the_pause(self):
        gid, mid = self.goal_paused_on_confirm(self._two_judgements())
        self.store.confirm_check(mid, 1)
        goal_lifecycle.record_founder_confirmation(self.store.load(mid))
        self.settle(mid)
        m = self.store.load(mid)
        self.assertEqual(m["state"], "paused", "still waiting on the other")
        self.assertEqual(m["pause_reason"], "founder_confirm")
        self.assertEqual(self.goals.load(gid)["state"], "verifying")

    def test_09_and_then_the_final_one_completes_it(self):
        gid, mid = self.goal_paused_on_confirm(self._two_judgements())
        for i in (1, 2):
            self.store.confirm_check(mid, i)
            goal_lifecycle.record_founder_confirmation(self.store.load(mid))
            self.settle(mid)
        self.assertEqual(self.store.load(mid)["state"], "done")
        self.assertEqual(self.goals.load(gid)["state"], "done")
        self.assertEqual(len(self.says), 1, "still one turn, total")

    def test_10_an_unmet_machine_check_blocks_completion(self):
        """A founder cannot confirm past a contains_artifact that is false."""
        gid, mid = self.goal_paused_on_confirm()
        self.transcript = "no command here at all"      # the phrase is gone
        self.store.confirm_check(mid, 1)
        self.settle(mid)
        self.assertEqual(self.store.load(mid)["state"], "paused",
                         "contains_artifact still decides its own tier")
        self.assertNotEqual(self.goals.load(gid)["state"], "done")


class TestIdempotenceAndGuards(Base):

    def test_11_confirming_twice_is_idempotent(self):
        gid, mid = self.goal_paused_on_confirm()
        self.store.confirm_check(mid, 1)
        self.settle(mid)
        first = self.store.load(mid)
        self.settle(mid)                       # again, on a done mission
        self.settle(mid)
        after = self.store.load(mid)
        self.assertEqual(after["state"], "done")
        self.assertEqual(after["seq"], first["seq"], "no further writes")
        self.assertEqual(self.goals.load(gid)["state"], "done")
        self.assertEqual(len(self.goals.load(gid)["attempts"]), 1)

    def test_12_settle_ignores_a_mission_that_is_not_confirmation_paused(self):
        for state, reason in (("running", None), ("paused", "floor_confirm"),
                              ("paused", "founder_intervened")):
            m = self.store.create(objective="o", template="fix",
                                  target_mode="existing", target_session=SID)
            self.store.transition(m["id"], "brief_confirm", "b")
            self.store.transition(m["id"], "running", "admitted")
            if state == "paused":
                mm = self.store.transition(m["id"], "paused", "x")
                mm["pause_reason"] = reason
                self.store.save(mm)
            eng = MissionEngine(self.store, None, None, lambda x: self.transcript)
            out = eng.settle(m["id"])
            self.assertEqual(out["state"], state, "%s/%s" % (state, reason))

    def test_13_a_floor_pause_is_never_settled_by_a_confirmation(self):
        """Safety: only the founder_confirm pause is this helper's business."""
        gid, mid = self.goal_paused_on_confirm()
        mm = self.store.load(mid)
        mm["pause_reason"] = "floor_confirm"
        self.store.save(mm)
        self.settle(mid)
        self.assertEqual(self.store.load(mid)["state"], "paused")


class TestOneCompletionPath(Base):
    """The structural promise: no second way to become `done`."""

    def test_14_complete_is_the_only_writer_of_a_done_mission(self):
        src = Path(__file__).with_name("mission_engine.py").read_text()
        self.assertEqual(src.count('transition(\n                    mid, "done"'), 0)
        self.assertEqual(src.count('"done", "done_when met'), 1,
                         "exactly one place performs the done transition")
        i = src.index("def _complete")
        self.assertIn('"done", "done_when met', src[i:i + 700])
        # and both callers reach THAT
        self.assertIn("return self._complete(mid, results, transcript)", src)
        j = src.index("def settle")
        self.assertIn("self._complete(mid, results, transcript)",
                      src[j:j + 2500])

    def test_15_settle_uses_the_existing_evaluator(self):
        src = Path(__file__).with_name("mission_engine.py").read_text()
        body = src[src.index("def settle"):src.index("def _out_of_road")]
        self.assertIn("evaluate_done_when(m, transcript, self.verifier)", body)
        self.assertNotIn("in (transcript", body, "no second matcher")
        self.assertNotIn("self.sayer", body, "and it never says anything")

    def test_16_contains_artifact_only_completion_is_unchanged(self):
        """The pre-existing route must still finish inside the loop."""
        g = self.goals.create(outcome="the docker command", target_session=SID,
                              done_when=[{"tier": "contains_artifact",
                                          "check": PHRASE}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        goal_lifecycle.on_attempt_start(m)
        self.store.transition(m["id"], "running", "admitted")
        out = run(self.engine().run_mission(m["id"]))
        goal_lifecycle.on_attempt_end(out)
        self.assertEqual(out["state"], "done", "no confirmation involved")
        self.assertIn("result_excerpt", out, "the excerpt is still written")
        self.assertEqual(self.goals.load(g["id"])["state"], "done")
        self.assertEqual(len(self.says), 1)


class TestBothEntryPoints(Base):
    """Whichever button the founder pressed, the same thing happens."""

    def test_17_both_arms_call_the_same_settle(self):
        src = Path(__file__).with_name("app.py").read_text()
        goal_arm = src[src.index('if action == "confirm":'):]
        goal_arm = goal_arm[:goal_arm.index("except HTTPException")]
        self.assertIn("shadow_runner.settle_confirmation(mid)", goal_arm)
        mission_arm = src[src.index('if action == "confirm_check":'):]
        mission_arm = mission_arm[:mission_arm.index('if action == "resume"')]
        self.assertIn("shadow_runner.settle_confirmation(mid)", mission_arm)

    def test_18_the_helper_reaches_the_engines_settle(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        body = src[src.index("def settle_confirmation"):
                   src.index("def reap_attached")]
        self.assertIn("engine.settle(mid)", body)
        self.assertIn("evidence_text(m.get(\"target_session\"))", body,
                      "the SAME evidence rule -- Shadow's own turns excluded")
        self.assertIn('_goal_hook("on_attempt_end", m)', body)
        self.assertNotIn("_launch", body, "it must not restart the loop")

    def test_19_teardown_reaps_a_delegate_and_never_an_attachment(self):
        src = Path(__file__).with_name("shadow_runner.py").read_text()
        body = src[src.index("def settle_confirmation"):
                   src.index("def reap_attached")]
        self.assertIn("DELEGATES.pop(", body)
        # the docstring NAMES the attached registry while explaining why it
        # is not touched, so assert against the code, not the prose
        code = body[body.index('"""', body.index('"""') + 3) + 3:]
        self.assertNotIn("ATTACHED", code,
                         "a founder's chat outlives the mission that drove it")


if __name__ == "__main__":
    unittest.main()
