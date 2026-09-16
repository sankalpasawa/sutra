#!/usr/bin/env python3
"""What every Worker Agent is told, beyond its own brief.

TWO RULES, ONE MANIFEST (founder, 2026-09-16).

DONE-CHECK. The manifest has asked for these lines since delegation shipped
and nothing had ever parsed them, so `verify`-tier checks could not pass. Now
that app._shadow_verifier reads them, the instruction has to be exact about
the format -- a protocol only one side implements is worse than none.

SUBAGENTS. The intended shape is USER -> SHADOW -> ONE WORKER -> the worker's
own Claude Code subagents. Shadow fan-out is deliberately NOT built: one
worker per mission stays the invariant. What was missing is that the worker
was never told it may decompose. Measured on m-5c2fca3f824b: 277 Bash calls,
44 Edits, 16 Reads and 9 Writes across backend, frontend and tests in a single
session, and no subagent at all.

The rule is a DECISION rule, not encouragement. A worker that splits a
three-file change pays more in re-established context than it saves, so the
trigger is stated in files, layers and dependency -- never in ambition.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_worker_agreement.py
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import app
import providers


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def manifest(self, **over):
        m = {"id": "m-1", "objective": "Ship the thing.",
             "target_session": None}
        m.update(over)
        return app._delegate_manifest(m)


class TheAgreementReachesEveryWorker(Base):

    def test_a_mission_with_its_OWN_manifest_still_gets_it(self):
        """The case that matters: the create route composes a manifest at
        mission creation, so almost no real mission reaches the default. A
        rule written only into the default would reach nobody."""
        out = self.manifest(manifest="Do the thing, your way.")
        self.assertIn("Do the thing, your way.", out)
        self.assertIn("WORKING AGREEMENT", out)

    def test_a_mission_without_one_gets_both_halves(self):
        out = self.manifest()
        self.assertIn("Ship the thing.", out)
        self.assertIn("WORKING AGREEMENT", out)

    def test_it_is_still_TAGGED_as_shadows_own_turn(self):
        """The tag is what keeps the manifest out of the evidence -- and so
        keeps the DONE-CHECK placeholder inside it from ever reading as a
        claim about a real check."""
        import shadow_egress
        out = self.manifest()
        self.assertTrue(out.startswith(shadow_egress.say_tag("m-1")))


class TheDoneCheckProtocolIsStated(Base):

    def test_the_exact_line_format_is_given(self):
        out = self.manifest()
        self.assertIn("DONE-CHECK:", out)

    def test_it_says_the_check_must_be_QUOTED(self):
        """The verifier matches on the check's own words; a worker that
        writes 'DONE-CHECK: done' satisfies nothing."""
        out = self.manifest()
        self.assertIn("quoted", out.lower())

    def test_it_says_this_is_the_ONLY_thing_that_marks_a_check(self):
        out = self.manifest().lower()
        self.assertIn("only", out)
        self.assertIn("verify", out)

    def test_it_warns_against_claiming_work_not_done(self):
        """A protocol that only rewards claiming invites false claims."""
        self.assertIn("false report", self.manifest().lower())

    def test_the_placeholder_cannot_satisfy_a_real_check(self):
        """Belt and braces on the tag: the agreement's own example line must
        not match anything, even if it ever reached the evidence."""
        out = self.manifest()
        self.assertFalse(
            app._shadow_verifier("The backend enforces the configured limit "
                                 "and excess tasks are queued.", out))


class TheTurnReportProtocolIsStated(Base):
    """REPORT. The founder-facing timeline used to show an EXCERPT of the
    turn -- the first sentence that survived cleaning -- which only
    accidentally answered the question its heading asks. The worker is now
    asked for the line itself, in the same "line of its own" shape DONE-CHECK
    has always used, and 16-shadow-home.shadowSayReport SELECTS it. Nothing
    summarises: a turn with no REPORT falls back to the old excerpt exactly.

    OUTCOME-FIRST, AND THAT TOOK A SECOND PASS (founder, 2026-09-16). The
    first wording asked for "what you changed, what you found, or what
    blocked you" and added "name what changed and what you ran". Measured on
    mission m-69aee2e5cebc, a worker obeyed it exactly and produced 387
    characters that opened with a resolved path and an existence check; the
    display cap cut the line before the clause saying the file had never been
    written, so the timeline read like progress on a turn where nothing was
    created. The worker's own PROSE led with the outcome -- only the REPORT
    did not, which is how we know the fault was in what we asked for.

    So the rules below are ORDERING rules, not topic rules: what leads the
    sentence is the whole point, and the manifest now says which material is
    disqualified from leading it. Nothing about selection, cleaning, the cap
    or the fallback moved for this -- only these words.
    """

    def test_the_line_and_its_format_are_asked_for(self):
        out = self.manifest()
        self.assertIn("REPORT:", out)
        self.assertIn("line of its own", out)

    def test_it_asks_for_ONE_sentence(self):
        """The timeline draws one line; a paragraph would be cut by the cap
        and the founder would read half a thought."""
        self.assertIn("one sentence", self.manifest().lower())

    def test_the_OUTCOME_leads_the_sentence(self):
        """The defect this wording exists to fix: a report is what the turn
        achieved, not the order in which the worker got there."""
        out = self.manifest()
        self.assertIn("meaningful outcome", out)
        self.assertIn("LEAD WITH WHAT IS NOW TRUE", out)
        self.assertIn("not the route you took", out)
        # the verbs that make an outcome an outcome
        for done in ["created", "changed", "fixed", "tested", "verified"]:
            self.assertIn(done, out, done)

    def test_a_BLOCKER_leads_when_there_is_one(self):
        """A blocked turn's news is the blocker and what it leaves undone --
        the exact thing m-69aee2e5cebc buried in clause four."""
        out = self.manifest()
        self.assertIn("A BLOCKER LEADS", out)
        self.assertIn("Never bury the", out)
        self.assertIn("plan mode blocks", out,
                      "the worked example is what makes the rule concrete")

    def test_SETUP_AND_TOOLING_are_named_as_disqualified(self):
        """Naming the material explicitly is the fix: the old wording invited
        it with "what you found" and "what you ran"."""
        out = self.manifest()
        self.assertIn("NOT THE SETUP", out)
        for banned in ["Paths you resolved", "files you only inspected",
                       "commands and", "checks you ran", "plans you wrote"]:
            self.assertIn(banned, out, banned)
        self.assertIn("not narrate the investigation", out)

    def test_the_old_invitations_are_GONE(self):
        """Regression on the wording itself. These two phrases are what the
        worker was obeying when it led with a path and an existence check."""
        out = self.manifest()
        self.assertNotIn("what you found", out)
        self.assertNotIn("what you ran;", out)

    def test_it_is_honest_when_blocked_or_when_nothing_changed(self):
        out = self.manifest().lower()
        self.assertIn("nothing changed", out)
        self.assertIn("blocker", out)
        self.assertIn("leaves undone", out)

    def test_it_refuses_the_two_ways_of_saying_nothing(self):
        out = self.manifest()
        self.assertIn('"Done." says nothing', out)
        self.assertIn("repeats the objective", out)

    def test_it_asks_for_a_line_that_FITS_the_display(self):
        """90, NOT 150 (founder, 2026-09-16). The first budget was written
        against SH_SAY_MAX, the JS cap -- but the founder-visible cut is the
        one-line clamp on .shagentsay, and a rendered line of that pane holds
        roughly 90 characters. Measured live: a 147-character report passed
        the JS untouched and was still cut on screen, at "unavailable in...".
        So the number the worker is given is now the number the pane can
        actually show. SH_SAY_MAX and the CSS are unchanged; only this
        guidance moved."""
        out = self.manifest()
        self.assertIn("KEEP IT SHORT", out)
        self.assertIn("under 90 characters", out)
        self.assertIn("cut off mid-thought", out)

    def test_it_does_not_disturb_the_DONE_CHECK_PROTOCOL(self):
        """The two rules travel together and neither replaces the other --
        stated in the manifest, because a worker reading one may assume it
        supersedes the other."""
        out = self.manifest()
        self.assertIn("DONE-CHECK:", out)
        self.assertIn("ONLY thing that marks a `verify` check met", out)
        self.assertIn("does not replace the DONE-CHECK line above", out)

    def test_the_example_line_is_a_placeholder_not_a_report(self):
        """Belt and braces on the tag, exactly as the DONE-CHECK lane does:
        the agreement's own specimen must not read as a claim about work."""
        out = self.manifest()
        self.assertIn("<one sentence", out)

    def test_it_does_not_ask_the_worker_to_stop_writing_prose(self):
        """REPORT is an ADDITIONAL line, not a replacement for the turn's
        ordinary output -- the whole transcript is still the worker chat."""
        out = self.manifest()
        self.assertIn("stays in the chat", out)


class TheSubagentRuleIsADecisionRule(Base):

    def test_the_worker_is_told_subagents_exist(self):
        out = self.manifest()
        self.assertIn("subagent", out.lower())
        self.assertIn("Task tool", out)

    def test_it_names_when_to_SPLIT(self):
        out = self.manifest()
        self.assertIn("SPLIT when", out)
        for trigger in ("different files or layers", "backend and frontend",
                        "tests"):
            self.assertIn(trigger, out)

    def test_it_names_when_NOT_to(self):
        """Without this half it is a mandate, and the founder asked for a
        judgement call."""
        out = self.manifest()
        self.assertIn("DO NOT SPLIT", out)
        self.assertIn("sequential", out)
        self.assertIn("starts cold", out)

    def test_it_does_not_MANDATE_decomposition(self):
        out = self.manifest().lower()
        for forced in ("always use a subagent", "must use subagents",
                       "every task should be split"):
            self.assertNotIn(forced, out)
        self.assertIn("most tasks do not need them", out)

    def test_the_worker_stays_the_integrator(self):
        """Shadow supervises the worker; the worker supervises its subagents.
        Nothing may hand a subagent the objective itself."""
        out = self.manifest()
        self.assertIn("never the whole objective", out)
        self.assertIn("you alone run the full test suite", out.lower())

    def test_a_subagents_claim_is_not_evidence(self):
        self.assertIn("not evidence until you have checked it",
                      self.manifest().lower())


class ShadowFanOutIsStillNotBuilt(Base):
    """The explicit non-goal. One worker per mission remains the invariant,
    so the decision vocabulary must stay exactly two verbs."""

    def test_shadow_has_no_delegate_or_split_action(self):
        import mission_engine
        self.assertEqual(mission_engine.DECISION_ACTIONS,
                         ("continue", "ask_founder"))

    def test_a_decision_asking_to_fan_out_is_refused(self):
        import mission_engine
        for action in ("delegate", "split", "spawn", "fan_out"):
            self.assertIsNone(
                mission_engine.validate_decision(
                    {"action": action, "reason": "r"}),
                "%r must not become a Shadow verb" % action)

    def test_a_mission_still_has_exactly_one_target_session(self):
        import mission_engine
        m = mission_engine.MissionStore().create(
            "o", "fix", target_mode="new", target_session="s-1")
        self.assertIsInstance(m["target_session"], str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
