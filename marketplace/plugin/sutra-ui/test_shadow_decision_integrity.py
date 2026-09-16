#!/usr/bin/env python3
"""Two ways a check or a decision can be satisfied by SAYING something.

Both were found in one dogfood run (founder, 2026-09-15, mission
m-245777cf1467), and both let words stand in for work.

P0  THE DECIDER ECHOED ITS OWN PROMPT. After resume_after_restart re-adopted
    a delegate, the decider answered with the example from its own prompt:

        {"action": "continue",
         "instruction": "<what to send into the chat next>",
         "reason": "<one short line: why this, now>"}

    `instruction` was a non-empty string, so validate_decision accepted it
    and the runner said `<what to send into the chat next>` into the delegate
    chat -- twice. The ping-pong guard saw two identical says and stopped the
    mission one second after it had been rescued.

P1  A CRITERION WAS SATISFIABLE BY QUOTING IT. The founder wrote "The task
    reaches DONE." as a done_when. It is short, five words and carries no
    criterion marker, so is_literal_artifact called it literal and tier_for
    kept `contains_artifact` -- a tier evaluated as

        met = check["check"] in transcript_text

    The delegate wrote "Committed as f96c3ade. The task reaches DONE." and
    the check about whether the work finished became a check about whether
    the chat contained a sentence.

Run: python3 test_shadow_decision_integrity.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import mission_engine
import providers
import shadow_ledger
import shadow_protocol as sp
from mission_engine import MissionEngine, MissionStore, validate_decision

SID = "sess-integrity"
TEMPLATE = "<what to send into the chat next>"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================ P0: the template echo ======
class TestTemplateEchoIsNotADecision(unittest.TestCase):

    def test_01_the_exact_placeholder_is_rejected(self):
        for ph in ("<what to send into the chat next>",
                   "<one short line: why this, now>",
                   "<what you need from the founder>",
                   "<one short line>"):
            self.assertIsNone(
                validate_decision({"action": "continue", "instruction": ph,
                                   "reason": "r"}),
                "the prompt's own example must not validate: " + ph)

    def test_01b_whitespace_and_case_do_not_smuggle_it_through(self):
        self.assertIsNone(validate_decision(
            {"action": "continue", "instruction": "  " + TEMPLATE + "  ",
             "reason": "r"}))
        self.assertIsNone(validate_decision(
            {"action": "continue", "instruction": TEMPLATE.upper(),
             "reason": "r"}))

    def test_02_legitimate_angle_brackets_are_ACCEPTED(self):
        """Engineering English is full of brackets. Refusing them would
        refuse most of what Shadow actually says."""
        for good in ("replace <sid> in the config and re-run",
                     "the <div> is unclosed in panel.html",
                     "run `git diff <base>..<head>` and paste the output",
                     "a <what to send into the chat next> placeholder is "
                     "still in the template -- fix it",
                     "explain what <T> binds to here"):
            d = validate_decision({"action": "continue", "instruction": good,
                                   "reason": "r"})
            self.assertIsNotNone(d, "legitimate instruction refused: " + good)
            self.assertEqual(d["instruction"], good)

    def test_03_a_normal_continue_is_UNAFFECTED(self):
        d = validate_decision({"action": "continue",
                               "instruction": "Finish the memo and paste it.",
                               "reason": "it stalled"})
        self.assertEqual(d["action"], "continue")
        self.assertEqual(d["instruction"], "Finish the memo and paste it.")
        self.assertEqual(d["reason"], "it stalled")

    def test_03b_ask_founder_and_empty_are_unchanged(self):
        self.assertEqual(
            validate_decision({"action": "ask_founder", "reason": "help"}),
            {"action": "ask_founder", "reason": "help", "instruction": ""})
        self.assertIsNone(validate_decision({"action": "continue",
                                             "instruction": "  "}))
        self.assertIsNone(validate_decision({"action": "nope"}))


class TestTemplateEchoCannotPingPong(unittest.TestCase):
    """The end-to-end shape of the live failure: a resumed loop whose first
    decision is the template must not talk to the chat at all."""

    def setUp(self):
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        settings = Path(self.tmp.name) / "settings.json"
        settings.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = settings
        self.store = MissionStore()
        self.said = []

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def _engine(self, script):
        async def sayer(m, text):
            self.said.append(text)
            return True

        async def waiter(m):
            return True

        async def decide(ctx):
            return script[min(len(self.said), len(script) - 1)]
        return MissionEngine(self.store, sayer, waiter,
                             lambda m: "transcript", decider=decide)

    def _resumed_mission(self):
        """turns_used > 0 is what makes this the RESUMED shape: the loop
        consults the decider instead of sending the manifest."""
        m = self.store.create("objective", "fix", target_mode="new",
                              target_session=SID,
                              done_when=[{"tier": "contains_artifact",
                                          "check": "FINAL:"}])
        self.store.transition(m["id"], "brief_confirm", "t")
        m = self.store.transition(m["id"], "running", "t")
        m["turns_used"] = 2
        m["manifest_delivered"] = True
        self.store.save(m)
        return m["id"]

    def test_04_a_template_echo_never_reaches_the_chat(self):
        mid = self._resumed_mission()
        out = run(self._engine([
            {"action": "continue", "instruction": TEMPLATE,
             "reason": "<one short line: why this, now>"},
        ]).run_mission(mid))
        self.assertEqual(self.said, [],
                         "the placeholder was said into the delegate chat")
        self.assertNotEqual(out["state"], "stopped",
                            "it must not ping-pong itself to death")
        # ENDS HONESTLY, AND RECOVERABLY (founder, 2026-09-16). The reason is
        # unchanged and still recorded; what changed is where it lands. An
        # undecidable turn is a fault in SHADOW, so it can no longer write the
        # same terminal state as work that genuinely failed -- `blocked` keeps
        # the delegate alive and the founder can Resume. See
        # mission_engine.INFRA_BLOCK_REASONS.
        self.assertEqual(out["state"], "blocked",
                         "an undecidable turn must not kill a live mission")
        self.assertEqual(out.get("failure_class"), "shadow_infra",
                         "and it must be labelled as Shadow's fault, not the "
                         "worker's")
        self.assertEqual(out.get("block_reason"), "shadow_undecided")
        notes = [json.loads(l)["note"] for l
                 in open(shadow_ledger._path("missions"), encoding="utf-8")
                 if mid in l]
        self.assertTrue(any("no usable decision" in n for n in notes),
                        "the reason must survive: %s" % notes)

    def test_05_a_real_instruction_on_the_same_path_still_drives(self):
        """The guard must not have closed the ordinary resumed turn."""
        mid = self._resumed_mission()
        run(self._engine([
            {"action": "continue", "instruction": "Carry on and paste it.",
             "reason": "r"},
            {"action": "ask_founder", "reason": "done here"},
        ]).run_mission(mid))
        self.assertEqual(self.said, ["Carry on and paste it."],
                         "a resumed mission must still say real things")


# ============================================ P1: outcome-shaped checks ==
class TestOutcomeShapedCriteriaAreNotArtifacts(unittest.TestCase):

    #: verbatim from the dogfood mission's done_when
    LIVE = ["The task reaches DONE.",
            "Tests cover the new behavior.",
            "Existing Shadow behavior still works.",
            "Relevant tests pass."]

    def test_10_the_live_criteria_demote_to_founder_confirm(self):
        for s in self.LIVE:
            self.assertFalse(sp.is_literal_artifact(s),
                             "still literal: " + s)
            self.assertEqual(sp.tier_for(s, "contains_artifact"),
                             "founder_confirm", s)

    def test_11_more_outcome_phrasings_demote_too(self):
        for s in ("The feature is complete.", "The mission is done",
                  "It is finished.", "The build is green.",
                  "The suite is passing.", "Everything still works."):
            self.assertEqual(sp.tier_for(s, "contains_artifact"),
                             "founder_confirm", s)

    def test_12_GENUINE_artifacts_are_preserved(self):
        """A filename, a marker, an exact output line -- strings the work
        PRODUCES. Demoting these would cost a sign-off for nothing."""
        for s in ("FINAL:", "shadow-auto-start.txt", "Final choice:",
                  "## Winner", "OK", "referral webhook 200", "BUILD GREEN",
                  "exit code 0", "Deployment complete", "Copy result",
                  "a tested PR is open", "the EMI check passes"):
            self.assertTrue(sp.is_literal_artifact(s), "demoted: " + s)
            self.assertEqual(sp.tier_for(s, "contains_artifact"),
                             "contains_artifact", s)

    def test_13_the_demoted_check_cannot_be_SAID_into_being(self):
        """The whole point: with the tier corrected, a transcript that
        quotes the criterion no longer satisfies it."""
        m = {"done_when": [{"tier": sp.tier_for("The task reaches DONE.",
                                                "contains_artifact"),
                            "check": "The task reaches DONE."}]}
        done, results = mission_engine.evaluate_done_when(
            m, "Committed as f96c3ade. The task reaches DONE.")
        self.assertFalse(done, "the worker talked its way to done")
        self.assertEqual(results[0]["tier"], "founder_confirm")
        self.assertFalse(results[0]["met"])

    def test_14_a_real_artifact_still_matches_its_transcript(self):
        m = {"done_when": [{"tier": sp.tier_for("FINAL:", "contains_artifact"),
                            "check": "FINAL:"}]}
        done, results = mission_engine.evaluate_done_when(
            m, "...working...\nFINAL: postgres")
        self.assertTrue(done)
        self.assertEqual(results[0]["tier"], "contains_artifact")

    def test_15_the_existing_tier_for_contract_is_unchanged(self):
        """Everything tier_for did before it learned about outcomes."""
        self.assertEqual(sp.tier_for("FINAL:", None), "founder_confirm")
        self.assertEqual(sp.tier_for("FINAL:", "verify"), "founder_confirm")
        self.assertEqual(sp.tier_for("FINAL:", "nonsense"), "founder_confirm")
        self.assertEqual(sp.tier_for("FINAL:", "founder_confirm"),
                         "founder_confirm")
        self.assertEqual(sp.tier_for("a" * 61, "contains_artifact"),
                         "founder_confirm", "the 60-char ceiling still binds")
        self.assertEqual(sp.tier_for("w " * 8 + "w", "contains_artifact"),
                         "founder_confirm", "the 8-word ceiling still binds")


if __name__ == "__main__":
    unittest.main(verbosity=2)
