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
             "target_session": None, "done_when": []}
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


class TheLastMessageIsTheDeliverable(Base):
    """THE UNIVERSAL RULE (founder, 2026-09-17).

    THE FAILURE, seen across every task type in the live store -- not one
    of them a research quirk:

        m-5089c1448d05  research  "## Reconciliation first -- my previous
                                   list was wrong", over a table comparing
                                   the worker's own earlier claims
        m-ecdedc5ab394  research  "Both open items closed. Here is the
                                   artifact." -- meta about the Worker<->
                                   Shadow exchange, not about Verstappen
                                   or Hamilton
        m-e0f2e48460c4  file      a "| Check | Evidence |" table in which
                                   the worker audits itself
        m-e51bd967a76a  file      a governance preamble before the finding

    One defect with one shape: THE WORKER REPORTED ON ITSELF DOING THE TASK
    INSTEAD OF ANSWERING THE TASK. The subject of the text was the worker,
    not the work.

    WHY THE RULE BELONGS HERE. `completion.outcome` is the worker's last
    message (shadow_runner.last_worker_message), and the DONE Summary draws
    it. The agreement already stated exactly this principle for the one-line
    REPORT -- "the OUTCOME, not the route you took to reach it" -- and then
    explicitly exempted everything else: "your ordinary output ... stays in
    the chat, unabridged". That exemption was correct while the last message
    was chat-only. Since the Summary shipped it is a founder-facing surface,
    so the SAME principle now covers the whole final message. No new rule was
    invented; the existing one stopped being scoped to one line.

    AND IT IS STATED UNIVERSALLY. The clause never names a task type, a
    domain or an example, which is what test_the_rule_is_not_task_type_
    specific below enforces -- a rule that said "remove reconciliation
    sections from research" would have fixed one screenshot and nothing else.
    """

    #: the shapes a mission can take, as objectives. The point is that the
    #: manifest treats them identically -- see the byte-identity test.
    SHAPES = {
        "research": "Pull the very latest information about a public figure.",
        "coding": "Fix the failing test in the parser and refactor the guard.",
        "file": "Create a file called notes.txt with today's date in it.",
        "web": "Find the three cheapest flights to Lisbon next month.",
        "general": "Decide whether we should move the release to Friday.",
        "mixed": "Research the options, then write the summary to a file.",
    }

    def test_the_clause_reaches_every_worker(self):
        for name, obj in self.SHAPES.items():
            out = self.manifest(objective=obj)
            flat = " ".join(out.split())
            self.assertIn("THE LAST MESSAGE YOU SEND IS THE DELIVERABLE", flat,
                          "missing for %s" % name)
            self.assertIn("Do not report on yourself doing the task", flat,
                          "missing for %s" % name)

    def test_the_rule_is_IDENTICAL_for_every_task_shape(self):
        """THE ANTI-SPECIAL-CASE TEST. Two manifests for two completely
        different kinds of work must differ ONLY by the objective. If a
        future edit branches the agreement on task type, this fails."""
        outs = {}
        for name, obj in self.SHAPES.items():
            outs[name] = self.manifest(objective=obj).replace(obj, "<OBJ>")
        first = outs["research"]
        for name, text in outs.items():
            self.assertEqual(text, first,
                             "the agreement differs for %s -- it must not "
                             "branch on the kind of work" % name)

    def test_the_rule_is_not_task_type_specific(self):
        """The clause may not name a task type, a domain, or the example it
        was found on. A rule that names its example is a special case wearing
        a general rule's clothes."""
        clause = self._clause()
        for word in ["research", "coding", "reconciliation", "Verstappen",
                     "Hamilton", "Rossi", "F1", "Formula", "file task",
                     "web search", "audit bookkeeping"]:
            self.assertNotIn(word.lower(), clause.lower(),
                             "the clause names %r -- state the principle, "
                             "not the case" % word)

    def _clause(self):
        out = self.manifest()
        i = out.index("Your last message.")
        j = out.index("Using subagents.")
        return out[i:j]

    def test_it_states_the_principle_not_a_list_of_banned_sections(self):
        c = self._clause()
        # the general test the worker can apply to anything
        self.assertIn("would this sentence still be worth writing if the "
                      "founder had done the work themselves", " ".join(c.split()))
        # and the axis: subject is the work, not the worker
        self.assertIn("anything whose subject is YOU rather than the work", c)

    def test_it_says_what_MAY_be_included(self):
        """The rule must not read as "be terse". A caveat, a limit and an
        admission of failure are part of an answer."""
        c = " ".join(self._clause().split())
        for keep in ["findings and conclusions", "the artifact you were asked",
                     "the evidence a claim rests on", "sources, dates, figures",
                     "caveat", "left undone"]:
            self.assertIn(keep, c, "the rule must permit: %s" % keep)
        self.assertIn("A caveat is part of the answer", c)

    def test_it_names_process_narration_generally(self):
        c = " ".join(self._clause().split())
        for out in ["the steps you took", "tools you called",
                    "how the answer was produced"]:
            self.assertIn(out, c)

    def test_self_comparison_is_excluded_as_a_PRINCIPLE(self):
        """The Verstappen case, generalised: correcting your own earlier
        drafts is bookkeeping about your process. Stated without naming the
        task it was found on."""
        c = " ".join(self._clause().split())
        self.assertIn("NOT A COMPARISON WITH YOUR OWN PREVIOUS ANSWERS", c)
        self.assertIn("The correction is not the news; the current answer is",
                      c)

    def test_it_does_not_ask_for_truncation(self):
        """A universal rule that shortened every answer would break research
        as surely as narration did."""
        c = " ".join(self._clause().split())
        self.assertIn("LENGTH FOLLOWS THE TASK", c)
        self.assertIn("Neither pad nor truncate", c)

    def test_nothing_is_LOST_only_relocated(self):
        """The founder can still read the working; it stays in the chat."""
        c = " ".join(self._clause().split())
        self.assertIn("Everything you leave out is still in this chat", c)

    def test_it_does_not_disturb_DONE_CHECK_or_REPORT(self):
        """Both protocols are preserved verbatim: the clause is additive."""
        out = self.manifest()
        self.assertIn("DONE-CHECK: <the check's text", out)
        self.assertIn("REPORT: <one sentence", out)
        self.assertIn("That line is the ONLY thing that marks a `verify` "
                      "check met", out)
        # ...and it points AT them rather than replacing them
        self.assertIn("DONE-CHECK already claims those", self._clause())

    def test_the_old_exemption_no_longer_licenses_narration(self):
        """THE MUTATION THIS FIXES. The agreement used to say the final
        message was exempt -- "it does not replace your ordinary output".
        That sentence is what told the worker its last message could be
        anything. It must not come back."""
        out = self.manifest()
        self.assertNotIn("it does not replace your\nordinary output", out)
        self.assertIn("with one exception, which is the next clause", out)

    def test_it_says_the_answer_LEADS(self):
        c = " ".join(self._clause().split())
        self.assertIn("LEAD WITH THE ANSWER", c)
        self.assertIn("The first line is the thing that was asked for", c)

    def test_a_mission_with_its_own_manifest_still_gets_the_clause(self):
        """Almost every real mission carries a composed manifest, so a rule
        that only reached the default would reach nobody."""
        out = self.manifest(manifest="Do it your way.")
        self.assertIn("THE LAST MESSAGE YOU SEND IS THE DELIVERABLE", out)


class TheWorkerIsShownTheChecksItIsJudgedBy(Base):
    """THE FOUR-TURN TASK THAT WAS DONE IN ONE (founder, 2026-09-17).

    Mission m-f9bb797db28b: "Create shadow-race-test.txt containing exactly
    shadow-race-pass." Shadow wrote two verify-tier checks. The worker created
    the file correctly in turn 1 -- 16 bytes, exact content, verified with
    `od -c` -- and claimed it the only way it could, by quoting the OBJECTIVE,
    because the checks were never shown to it. _shadow_verifier compares text;
    neither string contains the other; both checks read unmet. Shadow, whose
    prompt forbids it from ever claiming a check satisfied, spent three more
    turns inventing explanations: the wrong directory, then a trailing newline.

    The fix is to stop the two sides guessing at each other's wording.
    """

    RACE_CHECKS = [
        {"tier": "verify",
         "check": "A file named shadow-race-test.txt exists in the working "
                  "directory"},
        {"tier": "verify",
         "check": "The file's contents are exactly shadow-race-pass, with no "
                  "extra characters other than an optional single trailing "
                  "newline"},
    ]

    def test_the_exact_check_text_is_in_the_manifest(self):
        out = self.manifest(done_when=list(self.RACE_CHECKS))
        for c in self.RACE_CHECKS:
            self.assertIn("DONE-CHECK: %s" % c["check"], out,
                          "the worker must be given the check VERBATIM")

    def test_it_says_to_copy_them_exactly(self):
        out = self.manifest(done_when=list(self.RACE_CHECKS))
        self.assertIn("character for character", out)
        self.assertIn("copying its line below EXACTLY", out)
        self.assertIn("do not paraphrase", out)
        # ...and WHY, which is the lesson of the four-turn task
        self.assertIn("reads as NOT DONE", out)

    def test_only_verify_tier_checks_are_quoted(self):
        """founder_confirm is the founder's signature and no DONE-CHECK line
        can satisfy it; contains_artifact wants its literal in the work's own
        output. Listing either would invite a claim that does nothing."""
        out = self.manifest(done_when=[
            {"tier": "verify", "check": "the suite is green"},
            {"tier": "founder_confirm", "check": "the founder signs it off"},
            {"tier": "contains_artifact", "check": "shadow-pass"},
        ])
        self.assertIn("DONE-CHECK: the suite is green", out)
        self.assertNotIn("the founder signs it off", out)
        self.assertNotIn("DONE-CHECK: shadow-pass", out)

    def test_a_mission_with_no_verify_checks_is_byte_identical(self):
        """ADDITIVE: every manifest that existed before this is unchanged."""
        plain = self.manifest()
        self.assertNotIn("THE CHECKS THIS TASK IS JUDGED BY", plain)
        confirm_only = self.manifest(done_when=[
            {"tier": "founder_confirm", "check": "the founder signs it off"}])
        self.assertNotIn("THE CHECKS THIS TASK IS JUDGED BY", confirm_only)
        self.assertEqual(plain, confirm_only,
                         "a founder_confirm-only mission gets the manifest it "
                         "always got")

    def test_the_block_cannot_satisfy_its_own_checks(self):
        """THE TAG IS NOW LOAD-BEARING, not belt and braces. The manifest
        carries real DONE-CHECK lines, so if it ever reached the evidence it
        WOULD pass them. It cannot: it is a Shadow-authored user turn and
        evidence assembly drops those."""
        import shadow_runner
        out = self.manifest(done_when=list(self.RACE_CHECKS))
        check = self.RACE_CHECKS[0]["check"]
        # on the raw text the claim matches -- that is the danger
        self.assertTrue(app._shadow_verifier(check, out),
                        "the block does contain a matching claim")
        # ...and the evidence never contains it
        doc = {"messages": [{"role": "user", "text": out}]}
        kept = shadow_runner.evidence_messages(doc)
        self.assertEqual(kept, [], "the manifest must not be evidence")
        evidence = "\n".join(m["text"] for m in kept)
        self.assertFalse(app._shadow_verifier(check, evidence),
                         "a check must never be satisfied by the briefing "
                         "that asked for it")

    def test_a_worker_that_copies_them_completes_in_ONE_turn(self):
        """The whole point, end to end through the real evaluator."""
        import mission_engine
        m = {"done_when": list(self.RACE_CHECKS)}
        worker_said = (
            "**Done.** shadow-race-test.txt -- 16 bytes, exactly "
            "shadow-race-pass, no trailing newline. Verified with od -c.\n\n"
            "DONE-CHECK: %s\n"
            "DONE-CHECK: %s\n" % (self.RACE_CHECKS[0]["check"],
                                  self.RACE_CHECKS[1]["check"]))
        done, results = mission_engine.evaluate_done_when(
            m, worker_said, app._shadow_verifier)
        self.assertTrue(done, "one turn must be enough: %r" % (results,))
        self.assertTrue(all(r["met"] for r in results))

    def test_the_OLD_wording_still_does_not_pass(self):
        """The verifier is unchanged: quoting the objective instead of the
        check still reads as unmet. That is what made the four turns, and it
        is still true -- the fix is that the worker now has the right text,
        not that the matcher got looser."""
        import mission_engine
        m = {"done_when": list(self.RACE_CHECKS)}
        old = ("**Done.** 16 bytes, exactly shadow-race-pass.\n\n"
               "DONE-CHECK: Create shadow-race-test.txt containing exactly "
               "shadow-race-pass\n")
        done, results = mission_engine.evaluate_done_when(
            m, old, app._shadow_verifier)
        self.assertFalse(done, "the objective's wording must not pass a check")
        self.assertFalse(any(r["met"] for r in results))

    def test_a_check_the_worker_did_NOT_claim_stays_unmet(self):
        """No false completion: claiming one of two leaves the mission driving."""
        import mission_engine
        m = {"done_when": list(self.RACE_CHECKS)}
        partial = "DONE-CHECK: %s\n" % self.RACE_CHECKS[0]["check"]
        done, results = mission_engine.evaluate_done_when(
            m, partial, app._shadow_verifier)
        self.assertFalse(done)
        self.assertEqual([r["met"] for r in results], [True, False])

    def test_founder_confirm_is_untouched_by_any_claim(self):
        """A DONE-CHECK line cannot satisfy the founder's signature, however
        exactly it is quoted -- confirm_check remains the only writer."""
        import mission_engine
        check = "the founder signs this off"
        m = {"done_when": [{"tier": "founder_confirm", "check": check}]}
        done, results = mission_engine.evaluate_done_when(
            m, "DONE-CHECK: %s\n" % check, app._shadow_verifier)
        self.assertFalse(done, "only the founder may satisfy this tier")
        self.assertFalse(results[0]["met"])


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
