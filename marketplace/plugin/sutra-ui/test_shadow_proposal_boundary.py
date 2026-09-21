#!/usr/bin/env python3
"""A COMPLETE PLAN IS NOT AN ACCEPTED PLAN (founder, 2026-09-21, pass 11).

THE BUG. "I wanna visit Europe, make a 15 day plan I'd like." The worker
produces a complete, internally consistent 15-day itinerary; Shadow reads it,
sees nothing unmet, and marks the mission DONE. The founder never got to say
whether it was the trip they wanted.

WHERE THE DECISION ACTUALLY IS, and it is not where it looks. Completion is
`evaluate_done_when`: the mission is done when every `done_when` row is met,
and a `founder_confirm` row is the ONLY row that never auto-passes -- it is
met by an explicit founder action and nothing else. So a mission finishes
without asking precisely when nobody wrote a founder check for it.

The criteria are written by Shadow, at the first decide turn, under
`_CRITERIA_ASK`. That block pushed hard AWAY from the founder's tier -- for
good reason, because every check on the founder's install had been that tier
and they were signing off "the tests pass" by hand -- and it gave no rule at
all for a deliverable that IS a proposal. So the fix is one paragraph there,
and nothing in the state machine moves.

THE BOUNDARY IS INTENT, NOT VOCABULARY, and that is the constraint the
founder set:

  DIRECT     right or wrong on its own terms, and Shadow can establish
             which. "A file of 10 lines about X." Nobody has to agree with
             it for it to be done -- so no founder check, and an artifact
             existing is never a reason to ask.
  PROPOSAL   something the founder will ACT ON, LIVE WITH or CHOOSE
             BETWEEN, whose merit is theirs. An itinerary, a budget
             allocation, a shortlist. It can be complete and still not be
             the one they want, and no amount of reading settles that --
             which is the definition of the founder's tier.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_proposal_boundary.py
"""
import tempfile
import unittest
from pathlib import Path

import mission_engine
import shadow_decision
import shadow_protocol
import shadow_runner


class TheCriteriaGuidance(unittest.TestCase):
    """The one paragraph that moved. Asserted on the RENDERED prompt, because
    a block that does not render is a block Shadow never reads."""

    def setUp(self):
        self.text = shadow_runner.render_decide_prompt(
            {"outcome": "Make a 15 day Europe plan I'd like",
             "checks": [], "turns_used": 1, "max_turns": 20})

    def test_it_only_appears_when_there_are_no_checks(self):
        """Unchanged: the criteria ask is silent once a mission has checks."""
        withchecks = shadow_runner.render_decide_prompt(
            {"outcome": "x", "checks": [{"tier": "judge", "check": "y"}],
             "turns_used": 1, "max_turns": 20})
        self.assertNotIn("a PROPOSAL is something", withchecks)

    def test_both_kinds_of_deliverable_are_named(self):
        self.assertIn("a DIRECT DELIVERABLE is right or wrong", self.text)
        self.assertIn("a PROPOSAL is something the founder will ACT ON",
                      self.text)

    def test_a_direct_deliverable_is_told_not_to_ask(self):
        flat = " ".join(self.text.split())
        self.assertIn("do NOT write a founder check, settle it yourself, and "
                      "finish", flat)
        self.assertIn("An artifact existing is not a reason to ask", flat)

    def test_a_proposal_gets_exactly_one_founder_check(self):
        flat = " ".join(self.text.split())
        self.assertIn("write exactly ONE `founder_confirm` check", flat)
        self.assertIn("A proposal needs a single sign-off on the whole thing",
                      flat)

    def test_the_rule_is_intent_and_says_so(self):
        """NOT KEYWORD MATCHING -- the founder's explicit constraint."""
        flat = " ".join(self.text.split())
        self.assertIn("IT IS THE INTENT THAT DECIDES, NOT THE WORDS", flat)
        self.assertIn('"Make a file of 10 lines about X" is direct', flat)
        self.assertIn("is a proposal even though it produces a number", flat)


class TheTierGate(unittest.TestCase):
    """A proposal check has to survive shadow_protocol.tier_for, which
    refuses a bare `founder_confirm` on anything Shadow could establish."""

    def tier(self, check):
        return shadow_protocol.tier_for(check, proposed="founder_confirm")

    def test_a_proposal_check_reaches_the_founder(self):
        for check in ("the 15-day Europe itinerary is the trip you want",
                      "the plan is the one you want",
                      "the shortlist is the direction you prefer",
                      "the draft reads the way you meant"):
            self.assertEqual(self.tier(check),
                             shadow_protocol.FOUNDER_TIER, check)

    def test_a_mechanical_check_is_still_refused_the_founder(self):
        """The half of the gate that must NOT loosen: writing the founder's
        tier over something a probe settles still routes to the judge."""
        for check in ("alien-species.txt has 10 lines",
                      "the tests pass",
                      "the fix addresses the root cause"):
            self.assertEqual(self.tier(check),
                             shadow_protocol.FALLBACK_TIER, check)


class TheCompletionBoundary(unittest.TestCase):
    """The state machine itself, unchanged -- these pin that the behaviour
    the new criteria produce is the behaviour that was already there."""

    def evaluate(self, checks, transcript="the worker says it is all done"):
        return mission_engine.evaluate_done_when(
            {"done_when": checks}, transcript,
            verifier=lambda *a, **k: None)

    def test_a_proposal_mission_does_not_complete_on_its_own(self):
        """CASE: plan/proposal -> worker completes -> NEEDS YOU.

        The mechanical rows are met and the worker claims completion; the
        founder row is unmet, so the mission is NOT done."""
        done, results = self.evaluate([
            {"tier": "contains_artifact", "check": "europe-15-day.md"},
            {"tier": "founder_confirm",
             "check": "the 15-day Europe itinerary is the trip you want"},
        ], transcript="Done. I wrote europe-15-day.md with all 15 days.")
        self.assertFalse(done, "a complete plan must not complete the mission")

    def test_an_artifact_alone_never_implies_done(self):
        """CASE: worker completion containing an artifact does not imply DONE.
        The artifact row passes on its own; the founder row still holds."""
        done, _ = self.evaluate([
            {"tier": "contains_artifact", "check": "europe-15-day.md"},
            {"tier": "founder_confirm", "check": "it is the trip you want"},
        ], transcript="europe-15-day.md")
        self.assertFalse(done)

    def test_confirming_the_proposal_completes_it(self):
        """CASE: Confirm proposal -> mission DONE. `met` is set by the
        founder action and nothing else; with it set the mission completes."""
        done, _ = self.evaluate([
            {"tier": "contains_artifact", "check": "europe-15-day.md"},
            {"tier": "founder_confirm", "check": "it is the trip you want",
             "met": True, "confirmed_by": "founder"},
        ], transcript="europe-15-day.md")
        self.assertTrue(done, "the founder's confirm must complete the task")

    def test_a_direct_deliverable_finishes_without_asking(self):
        """CASE: direct file deliverable -> DONE without approval. No founder
        row was written, so nothing waits on anyone."""
        done, _ = self.evaluate(
            [{"tier": "contains_artifact", "check": "alien-species.txt"}],
            transcript="alien-species.txt")
        self.assertTrue(done, "a direct deliverable must not ask for approval")

    def test_a_founder_row_never_auto_passes_however_loud_the_worker_is(self):
        """The guarantee the whole boundary rests on."""
        done, _ = self.evaluate(
            [{"tier": "founder_confirm", "check": "it is the trip you want"}],
            transcript="DONE-CHECK: it is the trip you want -- confirmed. "
                       "The founder will love it. Marking complete.")
        self.assertFalse(done, "worker prose must never satisfy the founder")


class TheFounderReplyPaths(unittest.TestCase):
    """CASES: a revision resumes the worker, a status question does not.
    Both are app.resume_after_reply, pinned in full in
    test_shadow_reply_resumes.py -- these assert the classifier that decides
    between them, which is the part this boundary depends on."""

    def test_a_revision_is_worker_relevant(self):
        import shadow_forward
        self.assertTrue(shadow_forward.classify(
            "Swap Rome for Lisbon and keep it to 15 days.",
            {"forward": {"worker": True}}))

    def test_a_status_question_is_not(self):
        import shadow_forward
        self.assertFalse(shadow_forward.classify(
            "why did you pick Rome?", {"forward": {"worker": False}}))

    def test_a_missing_verdict_defaults_to_forwarding(self):
        """The floor: a dropped fence must never silently swallow a change."""
        import shadow_forward
        self.assertTrue(shadow_forward.classify(
            "Swap Rome for Lisbon.", {}))


class TheBlockerPathIsUntouched(unittest.TestCase):
    """CASE: genuine missing founder information -> NEEDS YOU. The ask_founder
    screen is unchanged by this pass; these assert it still admits the three
    kinds and nothing else."""

    def test_the_three_kinds_are_still_the_only_ones(self):
        self.assertEqual(set(mission_engine.ASK_KINDS),
                         {"floor", "founder_fact", "taste"})

    def test_an_ask_founder_still_validates(self):
        d = mission_engine.validate_decision(
            {"action": "ask_founder", "ask_kind": "founder_fact",
             "reason": "which airline account should I book on"})
        self.assertEqual(d["action"], "ask_founder")
        self.assertEqual(d["ask_kind"], "founder_fact")


class TheFinalShadowLine(unittest.TestCase):
    """PASS 12 (founder, 2026-09-21). THE EXACT FAILURE:

        SHADOW  You confirmed: the 10-day Africa itinerary is the trip you want
        SHADOW  Done.
                Replaced an earlier plan: ...
                africa-10-day-plan.md

    THE DATA FLOW THAT CAUSED IT. `MissionEngine.settle` decides a
    founder_confirm pause WITHOUT SPENDING A TURN -- correct, a signature is
    not a reason to spend the worker's budget -- so on confirm -> done NO
    decide turn runs, `_adopt_update` is never called, and nothing
    Shadow-authored exists for the completion to carry. The pane fell back to
    `completion.outcome` (the worker's last message); when that cleaned to
    nothing the founder read a bare "Done."

    THE FIX IS ONE FIELD, WRITTEN ON A TURN THAT ALREADY HAPPENS. `result` is
    Shadow's description of WHAT NOW EXISTS, sent on the turn that raises the
    proposal or finishes the work, kept on the record as `shadow_result`, and
    stamped onto the completion by `_complete` -- the ONE writer of a done
    mission, so the loop route and the confirm route cannot disagree.
    """

    def engine(self):
        eng = mission_engine.MissionEngine.__new__(mission_engine.MissionEngine)
        eng.outcome_reader = None
        return eng

    def adopt(self, m, decision):
        mission_engine.MissionEngine._adopt_update(self.engine(), m, decision)
        return m

    def test_the_result_is_kept_on_the_record(self):
        m = {"turns_used": 3}
        self.adopt(m, {"result": "I built a 10-day Africa plan in "
                                 "africa-10-day-plan.md."})
        self.assertEqual(m["shadow_result"]["text"],
                         "I built a 10-day Africa plan in "
                         "africa-10-day-plan.md.")
        self.assertEqual(m["shadow_result"]["at_turn"], 3)

    def test_it_is_replaced_not_appended(self):
        """ONE CURRENT FACT: the newest description of what exists now."""
        m = {"turns_used": 1}
        self.adopt(m, {"result": "A draft plan exists."})
        m["turns_used"] = 4
        self.adopt(m, {"result": "The 10-day plan is in africa-10-day-plan.md."})
        self.assertEqual(m["shadow_result"]["text"],
                         "The 10-day plan is in africa-10-day-plan.md.")

    def test_it_is_a_different_sentence_from_the_update(self):
        """The update asks; the result describes. Read back at DONE, an
        update that asks for a decision already given is the wrong line."""
        m = {"turns_used": 2}
        self.adopt(m, {"update": "I need your call on the pace.",
                       "result": "The 10-day plan is in the file."})
        self.assertEqual(m["shadow_updates"][-1]["text"],
                         "I need your call on the pace.")
        self.assertEqual(m["shadow_result"]["text"],
                         "The 10-day plan is in the file.")

    def test_a_turn_with_no_result_leaves_the_previous_one_standing(self):
        m = {"turns_used": 1}
        self.adopt(m, {"result": "The plan is in the file."})
        m["turns_used"] = 2
        self.adopt(m, {"update": "Checking the legs."})
        self.assertEqual(m["shadow_result"]["text"],
                         "The plan is in the file.")

    def test_machinery_is_refused_from_the_result_too(self):
        for bad in ('{"path": "a.md"}', "```json\n{}\n```",
                    "see https://x.y", "10 tool calls - web search 6"):
            self.assertIsNone(mission_engine.validate_result(bad), bad)

    def test_it_rides_both_decision_shapes(self):
        """The proposal turn is an ask_founder, so it MUST carry one."""
        for shape in ({"action": "continue", "instruction": "go",
                       "reason": "r"},
                      {"action": "ask_founder", "reason": "r",
                       "ask_kind": "taste"}):
            d = mission_engine.validate_decision(
                dict(shape, result="The plan is in the file."))
            self.assertEqual(d["result"], "The plan is in the file.", shape)

    def test_the_prompt_asks_for_it_on_both_shapes(self):
        t = shadow_runner.render_decide_prompt(
            {"outcome": "x", "checks": [], "turns_used": 1, "max_turns": 5})
        self.assertEqual(t.count('"result":'), 2)
        flat = " ".join(t.split())
        self.assertIn("it carries NO question", flat)
        self.assertIn("settled without spending a turn", flat)
        self.assertIn("If the work has produced nothing you can honestly "
                      "describe, OMIT IT", flat)


class TheCompletionCarriesIt(unittest.TestCase):
    """_complete is the ONE writer of a done mission, so both routes to DONE
    -- the loop's own completion and the founder's Confirm -- get the line."""

    def complete(self, mission):
        eng = mission_engine.MissionEngine.__new__(mission_engine.MissionEngine)
        eng.outcome_reader = None
        saved = {}

        class _Store:
            def transition(self, mid, state, note):
                return dict(mission, state=state)

            def save(self, m):
                saved["m"] = m

        eng.store = _Store()
        eng._complete("m-1", [{"check": "x", "met": True}], "")
        return saved["m"]

    BASE = {"id": "m-1", "objective": "make a 10 day Africa plan I'd like",
            "turns_used": 4, "max_turns": 25,
            "done_when": [{"tier": "founder_confirm",
                           "check": "the 10-day Africa itinerary is the trip "
                                    "you want", "met": True}]}

    def test_the_confirm_route_carries_shadows_line(self):
        """THE REGRESSION. No turn runs on confirm -> done, so the line has
        to come off the record -- and it does."""
        said = "I built a 10-day Africa plan in africa-10-day-plan.md."
        m = self.complete(dict(self.BASE,
                               shadow_result={"text": said, "at_turn": 3}))
        self.assertEqual(m["completion"]["said"], said)

    def test_no_result_means_no_claim(self):
        """CASE D: nothing describable -> nothing invented. The completion
        carries no line and the pane falls back exactly as it did."""
        m = self.complete(dict(self.BASE))
        self.assertNotIn("said", m["completion"])

    def test_the_rest_of_the_completion_is_untouched(self):
        m = self.complete(dict(self.BASE,
                               shadow_result={"text": "It is built.",
                                              "at_turn": 3}))
        for key in ("headline", "checks", "turns_used"):
            self.assertIn(key, m["completion"],
                          "the existing completion lost " + key)
        self.assertEqual(m["state"], "done")


class TheCompletionDeliversTheResult(unittest.TestCase):
    """PASS 14 (founder, 2026-09-21). "Founder confirmation controls WHETHER a
    proposal may become done. It does NOT control whether Shadow shows the
    resulting deliverable."

    A confirmed itinerary was finishing as a filename and a one-line
    description -- filed, not delivered. `completion.preview` is the produced
    artifact itself, read off disk at completion by the same reader and the
    same ownership rule the evidence lane uses, bounded for a chat message.

    NO STATE MACHINE MOVED. This is a rendering/response policy: the preview
    is stamped AFTER `done` is decided and can change no check, no state and
    no completion verdict.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, body):
        Path(self.root, name).write_text(body, encoding="utf-8")
        return {"id": "m-1",
                "done_when": [{"tier": "verify", "check": name,
                               "probe": {"kind": "file_exists",
                                         "path": name}}]}

    PLAN = "\n".join(
        ["Day %d  leg %d of the northern circuit" % (i, i)
         for i in range(1, 31)])

    def test_a_confirmed_proposal_shows_its_contents(self):
        """THE REPORTED CASE: the founder approved an itinerary and got a
        filename. Now they get the itinerary."""
        m = self.write("africa-5-day-plan.md", self.PLAN)
        p = shadow_decision.preview_for(m, self.root)
        self.assertIsNotNone(p, "the deliverable must be previewed")
        self.assertIn("Day 1  leg 1 of the northern circuit", p["text"])
        self.assertEqual(p["path"], "africa-5-day-plan.md")

    def test_a_direct_file_task_shows_the_actual_file(self):
        lines = "\n".join("Line %d about Pedro Acosta." % i
                           for i in range(1, 11))
        m = self.write("pedro-acosta.txt", lines)
        p = shadow_decision.preview_for(m, self.root)
        self.assertIn("Line 1 about Pedro Acosta.", p["text"])
        self.assertIn("Line 10 about Pedro Acosta.", p["text"])
        self.assertFalse(p["truncated"], "ten lines fit whole")

    def test_an_explicit_print_request_gets_the_lines(self):
        """CASE: "give me the 10 lines" -- the content is IN the completion,
        not a sentence saying where it was written."""
        lines = "\n".join("%d. a sourced line." % i for i in range(1, 11))
        m = self.write("ten.txt", lines)
        p = shadow_decision.preview_for(m, self.root)
        for i in range(1, 11):
            self.assertIn("%d. a sourced line." % i, p["text"])

    def test_a_long_artifact_is_cut_and_says_so(self):
        """CONCISE BY DEFAULT: nobody reads a partial plan believing it
        whole, and the whole file stays one click away."""
        m = self.write("africa-5-day-plan.md", self.PLAN)
        p = shadow_decision.preview_for(m, self.root)
        self.assertTrue(p["truncated"], "a 30-line plan must be cut")
        self.assertEqual(p["lines"], 30, "and report the real length")
        self.assertLessEqual(len(p["text"].splitlines()),
                             shadow_decision.PREVIEW_LINES)
        self.assertNotIn("Day 30", p["text"])

    def test_it_cannot_show_contents_that_are_not_there(self):
        """GROUNDED: no file, no preview -- whatever the worker claimed."""
        m = {"id": "m-1",
             "done_when": [{"tier": "verify", "check": "gone.txt",
                            "probe": {"kind": "file_exists",
                                      "path": "gone.txt"}}]}
        self.assertIsNone(shadow_decision.preview_for(m, self.root))

    def test_an_empty_artifact_is_not_a_deliverable(self):
        m = self.write("blank.txt", "   \n\n")
        self.assertIsNone(shadow_decision.preview_for(m, self.root))

    def test_a_mission_owning_nothing_previews_nothing(self):
        self.assertIsNone(shadow_decision.preview_for({"id": "m-1"},
                                                      self.root))

    def test_it_never_raises(self):
        for bad in (None, {}, {"done_when": "not a list"}):
            self.assertIsNone(shadow_decision.preview_for(bad, self.root))

    def test_the_prompt_says_to_give_content_when_asked_for_it(self):
        flat = " ".join(shadow_runner.render_decide_prompt(
            {"outcome": "print the 10 lines", "checks": [],
             "turns_used": 1, "max_turns": 5}).split())
        self.assertIn("WHEN THE FOUNDER ASKED TO BE GIVEN THE CONTENT, GIVE "
                      "IT", flat)
        self.assertIn("The content IS the result".lower(), flat.lower())


class TheBoundaryIsUnchangedByTheRendering(unittest.TestCase):
    """PASS 14 must not have moved the DIRECT vs PROPOSAL rule, and a
    preview must not become a reason to ask or to stop asking."""

    def evaluate(self, checks, transcript="the worker says it is all done"):
        return mission_engine.evaluate_done_when(
            {"done_when": checks}, transcript,
            verifier=lambda *a, **k: None)

    def test_a_proposal_still_waits_for_the_founder(self):
        done, _ = self.evaluate([
            {"tier": "contains_artifact", "check": "europe-15-day.md"},
            {"tier": "founder_confirm", "check": "it is the trip you want"}])
        self.assertFalse(done)

    def test_a_direct_deliverable_still_needs_no_approval(self):
        done, _ = self.evaluate(
            [{"tier": "contains_artifact", "check": "alien-species.txt"}],
            transcript="alien-species.txt")
        self.assertTrue(done)

    def test_the_preview_is_not_a_check(self):
        """It is stamped after `done` is decided and settles nothing."""
        self.assertNotIn("preview", mission_engine.DECISION_ACTIONS)
        d = mission_engine.validate_decision(
            {"action": "continue", "instruction": "go", "reason": "r",
             "preview": "anything at all"})
        self.assertNotIn("preview", d)


if __name__ == "__main__":
    unittest.main()
