"""Verification integrity: Shadow's own words are not proof.

`_next_say` names the outstanding checks verbatim ("Continue toward: X.
Outstanding checks: <names>") and the delegate manifest carries the
objective. Both land in the target session's transcript as USER turns. If
evidence assembly reads them back, a contains_artifact check is satisfied by
Shadow having ASKED for the thing rather than by the chat having done it.

These tests pin the boundary from both sides: Shadow's turns cannot satisfy
a check, and genuine chat/tool output still can.
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
from mission_engine import (MissionEngine, MissionScheduler, MissionStore,
                            evaluate_done_when)


class TestAuthorshipTag(unittest.TestCase):
    def test_01_one_writer_one_reader_of_the_tag(self):
        tag = shadow_egress.say_tag("m-abc123")
        self.assertEqual(tag, "[Shadow · mission m-abc123]")
        self.assertTrue(shadow_egress.is_shadow_authored(tag + " do the work"))
        self.assertTrue(shadow_egress.is_shadow_authored(
            "  " + tag + " leading space still counts"))

    def test_02_chat_output_is_never_mistaken_for_shadows(self):
        for text in ("integration test passes",
                     "I was told [Shadow · mission m-1] earlier",
                     "", None):
            self.assertFalse(shadow_egress.is_shadow_authored(text),
                             repr(text))


class TestEvidenceFilter(unittest.TestCase):
    """evidence_messages is pure -- drive it with transcript-shaped docs."""

    def setUp(self):
        self.tag = shadow_egress.say_tag("m-1")

    def test_03_shadow_user_turns_are_dropped(self):
        doc = {"id": "s-1", "messages": [
            {"role": "user", "text": self.tag + " Continue toward: ship it. "
                                                "Outstanding checks: ALL GREEN"},
            {"role": "assistant", "text": "running the suite now"},
        ]}
        kept = shadow_runner.evidence_messages(doc)
        self.assertEqual([m["role"] for m in kept], ["assistant"])

    def test_04_the_founders_own_turns_are_kept(self):
        doc = {"id": "s-1", "messages": [
            {"role": "user", "text": "the mock server needs to be up first"},
            {"role": "assistant", "text": "understood"},
        ]}
        self.assertEqual(len(shadow_runner.evidence_messages(doc)), 2,
                         "the founder talking in the chat IS evidence")

    def test_05_an_assistant_quoting_the_tag_is_still_kept(self):
        doc = {"messages": [
            {"role": "assistant", "text": self.tag + " was my instruction"},
        ]}
        self.assertEqual(len(shadow_runner.evidence_messages(doc)), 1,
                         "Shadow can only inject USER turns; an assistant "
                         "turn is the chat's own output")

    def test_06_tool_records_and_odd_shapes_survive(self):
        doc = {"messages": [
            {"role": "tool", "text": "2 passed, 1 failed"},
            {"role": "assistant"},
            {},
        ]}
        self.assertEqual(len(shadow_runner.evidence_messages(doc)), 3)
        self.assertEqual(shadow_runner.evidence_messages({}), [])
        self.assertEqual(shadow_runner.evidence_messages(None), [])

    def test_07_non_message_fields_pass_through_untouched(self):
        """Only `messages` is filtered; the rest of the doc is unchanged."""
        doc = {"id": "s-1", "cwd": "/repo", "branch": "main",
               "messages": [{"role": "user", "text": self.tag + " x"}]}
        orig = json.loads(json.dumps(doc))
        shadow_runner.evidence_messages(doc)
        self.assertEqual(doc, orig, "the filter must not mutate its input")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.missions = MissionStore()
        self.goals = GoalStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def _running(self, check="integration test passes", goal_id=None):
        m = self.missions.create(
            "make the integration test pass", "fix", goal_id=goal_id,
            done_when=[{"tier": "contains_artifact", "check": check}])
        self.missions.transition(m["id"], "brief_confirm")
        return self.missions.transition(m["id"], "running")

    def _engine(self, transcript_for):
        """Engine whose reader runs the REAL evidence filter over a fake
        transcript doc, so the loop is driven end to end through the code
        under test."""
        self.says = []

        async def sayer(mission, text):
            self.says.append(text)
            return True

        async def waiter(mission):
            return True

        def reader(mission):
            doc = transcript_for(self.says)
            doc = dict(doc)
            doc["messages"] = shadow_runner.evidence_messages(doc)
            return json.dumps(doc)

        return MissionEngine(self.missions, sayer, waiter, reader)


class TestShadowCannotVerifyItself(Base):
    def test_08_shadows_own_say_cannot_satisfy_the_check(self):
        """The exact attack: the follow-up prompt names the check, so the
        transcript contains the phrase -- as Shadow's turn."""
        m = self._running(check="integration test passes")
        mm = self.missions.load(m["id"])
        # 2, so the budget check fires before ping-pong could: this test is
        # about verification, and the halt reason must be unambiguous
        mm["max_turns"] = 2
        self.missions.save(mm)

        def transcript(says):
            # every say echoed back as a TAGGED user turn, exactly as
            # _validated_say writes it, plus an unhelpful chat reply
            msgs = []
            for s in says:
                msgs.append({"role": "user",
                             "text": shadow_egress.say_tag(m["id"]) + " " + s})
                msgs.append({"role": "assistant", "text": "still working"})
            return {"id": "s-1", "messages": msgs}

        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertEqual(out["state"], "failed",
                         "must run out of budget, never reach done")
        self.assertIn("max turns", self._last_note(m["id"]))
        # prove the phrase really was present in the raw transcript
        raw = json.dumps(transcript(self.says))
        self.assertIn("integration test passes", raw)
        self.assertNotIn("integration test passes",
                         json.dumps(shadow_runner.evidence_messages(
                             transcript(self.says))))

    def test_09_the_delegate_manifest_cannot_satisfy_the_check_either(self):
        m = self._running(check="make the integration test pass")

        def transcript(says):
            return {"id": "s-1", "messages": [
                {"role": "user",
                 "text": shadow_egress.say_tag(m["id"])
                         + " You are a delegate session working for the "
                           "founder via Shadow. Objective: make the "
                           "integration test pass."},
                {"role": "assistant", "text": "starting"},
            ]}

        mm = self.missions.load(m["id"])
        mm["max_turns"] = 1
        self.missions.save(mm)
        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertNotEqual(out["state"], "done",
                            "the briefing that asked for it is not proof")

    def test_10_genuine_chat_output_still_satisfies_the_check(self):
        m = self._running(check="integration test passes")

        def transcript(says):
            msgs = [{"role": "user",
                     "text": shadow_egress.say_tag(m["id"]) + " " + s}
                    for s in says]
            if says:
                msgs.append({"role": "assistant",
                             "text": "pytest: integration test passes"})
            return {"id": "s-1", "messages": msgs}

        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertEqual(out["state"], "done",
                         "the chat actually reporting it IS proof")
        self.assertEqual(out["turns_used"], 1)

    def test_11_genuine_tool_output_still_satisfies_the_check(self):
        m = self._running(check="2 passed")

        def transcript(says):
            msgs = [{"role": "user",
                     "text": shadow_egress.say_tag(m["id"]) + " " + s}
                    for s in says]
            if says:
                msgs.append({"role": "tool",
                             "text": "pytest -q -> 2 passed in 0.4s"})
            return {"id": "s-1", "messages": msgs}

        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertEqual(out["state"], "done", "tool output IS evidence")

    def test_12_the_founder_answering_in_the_chat_is_evidence(self):
        m = self._running(check="the mock server is up")

        def transcript(says):
            msgs = [{"role": "user",
                     "text": shadow_egress.say_tag(m["id"]) + " " + s}
                    for s in says]
            if says:
                msgs.append({"role": "user",
                             "text": "the mock server is up now, retry"})
            return {"id": "s-1", "messages": msgs}

        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertEqual(out["state"], "done",
                         "an untagged user turn is the founder, not Shadow")

    def _last_note(self, mid):
        import shadow_ledger
        rows = [r for r in shadow_ledger.read("missions", 100)
                if r.get("mission_id") == mid]
        return rows[-1].get("note", "")


class TestEvaluatorUnchanged(Base):
    """The evaluator itself is untouched -- same tiers, same semantics."""

    def test_13_the_three_tiers_behave_exactly_as_before(self):
        mission = {"done_when": [
            {"tier": "contains_artifact", "check": "ALL GREEN"},
            {"tier": "verify", "check": "build"},
            {"tier": "founder_confirm", "check": "sign off"},
        ]}
        done, results = evaluate_done_when(mission, "tests ALL GREEN",
                                           verifier=lambda c: True)
        self.assertFalse(done, "founder_confirm never auto-passes")
        self.assertEqual([r["met"] for r in results], [True, True, False])
        mission["done_when"][2]["met"] = True
        done, _ = evaluate_done_when(mission, "tests ALL GREEN",
                                     verifier=lambda c: True)
        self.assertTrue(done)

    def test_14_an_empty_check_set_still_never_completes(self):
        done, results = evaluate_done_when({"done_when": []}, "anything")
        self.assertFalse(done)
        self.assertEqual(results, [])

    def test_15_evidence_text_keeps_its_shape_and_tail(self):
        """Same two sources, same order, same 40k tail as before."""
        shadow_runner._RECENT_TEXT["s-ev"] = "streamed assistant text"
        try:
            out = shadow_runner.evidence_text("s-ev")
        finally:
            shadow_runner._RECENT_TEXT.pop("s-ev", None)
        self.assertTrue(out.startswith("streamed assistant text "))
        self.assertLessEqual(len(out), 40000)
        self.assertIn("{}", out, "no transcript on disk -> empty doc")


class TestLifecycleStillWorks(Base):
    def test_16_a_goal_still_completes_on_genuine_evidence(self):
        g = self.goals.create("make the integration test pass", "01a081",
                              done_when=[{"tier": "contains_artifact",
                                          "check": "integration test passes"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))

        def transcript(says):
            msgs = [{"role": "user",
                     "text": shadow_egress.say_tag(m["id"]) + " " + s}
                    for s in says]
            if says:
                msgs.append({"role": "assistant",
                             "text": "integration test passes"})
            return {"id": "01a081", "messages": msgs}

        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        goal = goal_lifecycle.on_attempt_end(out)
        self.assertEqual(goal["state"], "done")

    def test_17_a_goal_blocks_rather_than_self_verifying(self):
        g = self.goals.create("make the integration test pass", "01a082",
                              done_when=[{"tier": "contains_artifact",
                                          "check": "integration test passes"}])
        m = goal_lifecycle.start_first_attempt(g["id"])
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 2
        self.missions.save(mm)
        MissionScheduler(self.missions).start(m["id"])
        goal_lifecycle.on_attempt_start(self.missions.load(m["id"]))

        def transcript(says):
            msgs = []
            for s in says:
                msgs.append({"role": "user",
                             "text": shadow_egress.say_tag(m["id"]) + " " + s})
                msgs.append({"role": "assistant", "text": "still trying"})
            return {"id": "01a082", "messages": msgs}

        out = asyncio.run(self._engine(transcript).run_mission(m["id"]))
        self.assertEqual(out["state"], "blocked")
        self.assertEqual(out["block_reason"], "budget_exhausted")
        goal = goal_lifecycle.on_attempt_end(out)
        self.assertEqual(goal["state"], "blocked",
                         "asked, not silently completed")


if __name__ == "__main__":
    unittest.main()
