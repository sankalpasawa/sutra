"""D-SH-1 (founder, 2026-09-20): SHADOW SETTLES ITS OWN CHECKS.

THE MEASUREMENT THAT PROMPTED IT. Across every mission on the founder's live
install, 9 done-when checks out of 9 were `founder_confirm`, every one with
`proposed_tier: None` -- Shadow named no tier and the fallback sent them all
to the founder's desk. Zero checks had ever been settled by Shadow. The
founder was hand-signing "the tests pass".

WHAT THIS FILE PINS, in the order the lanes were built:

  1. command probe    a check about whether something WORKS is answered by
                      running it, with argv and no shell
  2. evidence judge   a check about whether the CHANGE is right is answered
                      by reading the diff -- never the worker's prose
  3. the inversion    the default tier is the judge, not a signature; only
                      taste and founder-held facts reach a human
  4. the ask gate     the same rule mid-mission, so an intermediate question
                      cannot park a task on something Shadow could look up

AND THE THING THAT MAKES ALL OF IT SAFE: `cannot_tell`. Every route away from
the founder has a way back, so a wrong routing costs one model call instead of
a check nobody ever answers.
"""
import asyncio
import inspect
import os
import subprocess
import tempfile
import unittest

# ── THE LIVE HOME IS NOT A TEST FIXTURE (2026-09-21) ────────────────────
# RunJudges drives MissionEngine._run_judges, which appends to
# shadow_ledger -- so without this line this suite wrote ledger rows into
# the operator's own ~/.sutra-ui/shadow on every run. conftest.py sets this
# for pytest, but run-tests.sh drives `unittest`, where conftest is never
# loaded, so the isolation it provides never reached this lane.
#
# Found when shadow_ledger's live-home guard stopped keying on
# PYTEST_CURRENT_TEST and started asking "is this a test process at all".
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-lanes-test-")

import mission_engine
import shadow_judge
import shadow_probe
import shadow_protocol

#: A credential-SHAPED string, assembled at runtime rather than written as a
#: literal: PROTO-004 scans source files for these shapes and is right to,
#: so the one string in this suite that must LOOK like a key is built here.
FAKE_KEY = "sk-" + ("abcdefghij" * 2)


# --------------------------------------------------------------- lane B ---
class CommandProbe(unittest.TestCase):
    """The probe that runs something. The shape of checks 1 and 3 of the
    founder's focus-fix task, both of which reached them by hand."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def run_probe(self, **probe):
        probe.setdefault("kind", "command_succeeds")
        return shadow_probe.run(probe, self.root)

    def test_a_passing_command_settles_the_check(self):
        self.assertTrue(self.run_probe(argv=["true"]).met)

    def test_a_failing_command_leaves_it_unmet(self):
        res = self.run_probe(argv=["false"])
        self.assertFalse(res.met)
        self.assertIn("exited 1", res.reason)

    def test_the_exit_code_can_be_something_other_than_zero(self):
        self.assertTrue(self.run_probe(argv=["false"], expect_exit=1).met)

    def test_contains_is_an_ADDITIONAL_condition_not_a_replacement(self):
        """A suite that exits 0 while printing "0 tests ran" is the case this
        exists for -- and the exit code still binds on its own."""
        with open(os.path.join(self.root, "out.txt"), "w") as fh:
            fh.write("42 passed\n")
        self.assertTrue(
            self.run_probe(argv=["cat", "out.txt"], contains="passed").met)
        self.assertFalse(
            self.run_probe(argv=["cat", "out.txt"], contains="failed").met)

    def test_a_shell_with_dash_c_is_REFUSED(self):
        """The argv list is the whole safety property. A shell handed -c
        would parse a model-authored string and give back every property the
        list exists to provide."""
        for argv in (["bash", "-lc", "echo hi"], ["sh", "-c", "echo hi"],
                     ["/bin/zsh", "-c", "ls"], ["python3", "-c", "print(1)"]):
            with self.subTest(argv=argv):
                self.assertIsNone(shadow_probe.validate_probe(
                    {"kind": "command_succeeds", "argv": argv}))

    def test_a_shell_WITHOUT_dash_c_is_fine(self):
        """Running a script is not the same as evaluating a string."""
        self.assertIsNotNone(shadow_probe.validate_probe(
            {"kind": "command_succeeds", "argv": ["bash", "run-tests.sh"]}))

    def test_a_floor_is_REFUSED_and_the_check_stays_outstanding(self):
        """THE FLOORS OUTRANK THIS LANE, exactly as they outrank a say and
        every autonomy level. One floor table for the whole of Shadow."""
        res = self.run_probe(argv=["git", "push", "--force", "origin", "main"])
        self.assertFalse(res.met)
        self.assertIn("floor", res.reason)

    def test_argv_must_be_a_list_of_strings(self):
        for argv in ("pytest -q", [], ["ok", 7], [""], None, {"a": 1}):
            with self.subTest(argv=argv):
                self.assertIsNone(shadow_probe.validate_probe(
                    {"kind": "command_succeeds", "argv": argv}))

    def test_a_missing_program_is_unmet_and_NOT_an_exception(self):
        """A probe fault is never a verdict on the work, and never a FAILED
        mission -- the rule the whole module is built on."""
        res = self.run_probe(argv=["definitely-not-a-real-program-xyz"])
        self.assertFalse(res.met)
        self.assertIn("no such program", res.reason)

    def test_a_timeout_is_unmet_and_bounded(self):
        res = self.run_probe(argv=["sleep", "5"], timeout_s=1)
        self.assertFalse(res.met)
        self.assertIn("timed out", res.reason)

    def test_the_reason_line_is_SCRUBBED_on_both_halves(self):
        """It reaches the ledger and the founder's card, and a command can
        carry a credential in its own arguments as well as in its output."""
        res = self.run_probe(argv=["echo", "tok " + FAKE_KEY])
        self.assertNotIn(FAKE_KEY, res.reason)
        self.assertIn("[redacted]", res.reason)

    def test_the_command_runs_INSIDE_the_workdir(self):
        with open(os.path.join(self.root, "here.txt"), "w") as fh:
            fh.write("x")
        self.assertTrue(self.run_probe(argv=["cat", "here.txt"]).met)

    def test_the_five_file_kinds_are_untouched(self):
        """Every pre-existing probe keeps working byte for byte."""
        with open(os.path.join(self.root, "a.txt"), "w") as fh:
            fh.write("ok\n")
        self.assertTrue(shadow_probe.run(
            {"kind": "file_exists", "path": "a.txt"}, self.root).met)
        self.assertTrue(shadow_probe.run(
            {"kind": "file_equals", "path": "a.txt", "text": "ok",
             "allow_trailing_newline": True}, self.root).met)


# --------------------------------------------------------------- lane C ---
class EvidenceJudge(unittest.TestCase):
    """The judge reads the ARTIFACT. Never anybody's account of it."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def git(self, *args):
        subprocess.run(["git"] + list(args), cwd=self.root, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def make_repo_with_a_change(self):
        self.git("init")
        self.git("config", "user.email", "t@t.t")
        self.git("config", "user.name", "t")
        with open(os.path.join(self.root, "f.py"), "w") as fh:
            fh.write("def a():\n    pass\n")
        self.git("add", "-A")
        self.git("commit", "-m", "base")
        with open(os.path.join(self.root, "f.py"), "w") as fh:
            fh.write("def a():\n    return 1\n")

    def test_evidence_carries_the_diff(self):
        self.make_repo_with_a_change()
        blob = shadow_judge.evidence_for(self.root)
        self.assertIn("return 1", blob)
        self.assertIn("git diff", blob)

    def test_evidence_never_carries_worker_prose(self):
        """THE LOAD-BEARING TEST OF THIS WHOLE CHANGE, and the one a future
        edit that threads the transcript into evidence_for must fail.

        If the worker's words can reach the judge, the judge stops being a
        reviewer and becomes an attestation -- the exact failure that let
        m-245777cf1467 close a check by writing "The task reaches DONE."
        """
        self.make_repo_with_a_change()
        claim = "I fixed it perfectly and all the tests pass, DONE-CHECK: x"
        blob = shadow_judge.evidence_for(self.root, ["ran suite -> MET"])
        self.assertNotIn(claim, blob)
        self.assertNotIn("DONE-CHECK", blob)
        # ...and the signature has no transcript parameter to pass one
        # through, which is the structural half of the same promise.
        #
        # `artifact_paths` ADDED 2026-09-20 and the list widened DELIBERATELY
        # rather than the assertion dropped. It takes PATHS, and the content
        # is read from disk by shadow_evidence -- so it is a way to name the
        # work, never a way to hand in somebody's account of it. The name
        # screen below is what actually holds the line as this list grows:
        # any future parameter carrying prose would have to be called
        # something, and every word a transcript could arrive under is
        # refused here.
        params = list(inspect.signature(
            shadow_judge.evidence_for).parameters)
        self.assertEqual(params, ["root", "probe_lines", "artifact_paths"])
        for name in params:
            for banned in ("transcript", "prose", "claim", "reply", "say",
                           "message", "said", "output_text", "summary"):
                self.assertNotIn(banned, name,
                                 "a parameter named %r could carry the "
                                 "worker's words into the judge" % name)

    def test_probe_results_ARE_carried(self):
        """A judge asked "did anything else break" must be able to see that
        the suite was run and what it printed."""
        self.make_repo_with_a_change()
        blob = shadow_judge.evidence_for(self.root, ["the suite passes -> MET"])
        self.assertIn("the suite passes -> MET", blob)

    def test_a_non_repo_yields_no_evidence_rather_than_raising(self):
        self.assertEqual(shadow_judge.evidence_for(self.root), "")
        self.assertEqual(shadow_judge.evidence_for("/nope/nope/nope"), "")
        self.assertEqual(shadow_judge.evidence_for(None), "")

    def test_the_three_verdicts_parse(self):
        for state in ("met", "unmet", "cannot_tell"):
            got = shadow_judge.parse_verdict(
                '```json\n{"verdict": "%s", "reason": "because"}\n```' % state)
            self.assertEqual(got.state, state)
            self.assertEqual(got.reason, "because")

    def test_an_unusable_reply_is_None_and_None_IS_NOT_A_VERDICT(self):
        """A judge that returned nothing usable has SAID NOTHING. That must
        never read as unmet (which would drive a worker at a check that may
        already hold) and certainly never as met."""
        for reply in ("", "I think so", '{"verdict": "probably"}',
                      '{"reason": "no verdict key"}', "```json\n{oops}\n```"):
            with self.subTest(reply=reply):
                self.assertIsNone(shadow_judge.parse_verdict(reply))

    def test_truncation_is_ANNOUNCED_so_the_judge_can_say_cannot_tell(self):
        blob = shadow_judge._clip("x" * 50000, 100)
        self.assertIn("truncated", blob)
        self.assertIn("cannot_tell", blob)

    def test_the_prompt_forbids_guessing(self):
        p = shadow_judge.render_prompt("does it work", "a diff", "an outcome")
        self.assertIn("GUESSING IS THE ONLY WRONG ANSWER", p)
        self.assertIn("cannot_tell", p)


# ----------------------------------------------------------- the ladder ---
class TheInversion(unittest.TestCase):
    """What a check gets when nothing claims it. This used to be a signature
    and it is now the judge."""

    def test_the_three_live_checks_no_longer_reach_the_founder(self):
        """The actual rows off mission m-e34460ddcafa, which the founder
        signed off by hand. Not one of them is taste."""
        for check in (
            "typing a long message into the talk-to-shadow box holds focus "
            "the whole time -- no keystrokes are dropped and the cursor "
            "never leaves the field",
            "the fix addresses the identified root cause of the focus loss "
            "in the live repo source, not a workaround such as a "
            "refocus-on-blur hack",
            "no other input, panel or behaviour in the UI changed as a side "
            "effect of the fix",
        ):
            with self.subTest(check=check[:40]):
                self.assertEqual(shadow_protocol.tier_for(check), "judge")

    def test_taste_still_reaches_the_founder(self):
        for check in ("the copy reads well", "this is the design you preferred",
                      "the landing page looks right to you",
                      "the wording is acceptable to you",
                      "you sign off on the migration"):
            with self.subTest(check=check):
                self.assertEqual(shadow_protocol.tier_for(check),
                                 "founder_confirm")

    def test_a_fact_only_the_founder_holds_reaches_them(self):
        for check in ("the budget cap is set", "the api key is configured",
                      "the credential is in place"):
            with self.subTest(check=check):
                self.assertEqual(shadow_protocol.tier_for(check),
                                 "founder_confirm")

    def test_a_bare_founder_confirm_PROPOSAL_is_not_enough(self):
        """THE SHARP EDGE. All 9 live checks arrived with no tier at all, so
        honouring a bare `founder_confirm` would leave that door open under a
        new name. A check routed to the founder has to LOOK like theirs."""
        self.assertEqual(
            shadow_protocol.tier_for("the tests pass", "founder_confirm"),
            "judge")
        self.assertEqual(
            shadow_protocol.tier_for("the copy reads well", "founder_confirm"),
            "founder_confirm")

    def test_verify_survives_WITH_a_probe_and_is_demoted_without_one(self):
        """`verify` was excluded from PROPOSAL_TIERS on the grounds that no
        production caller passed a verifier. That stopped being true when
        probes shipped, and the exclusion stayed."""
        probe = {"kind": "command_succeeds", "argv": ["true"]}
        self.assertEqual(shadow_protocol.tier_for("x", "verify", probe),
                         "verify")
        self.assertEqual(shadow_protocol.tier_for("x", "verify", None),
                         "judge")
        self.assertEqual(shadow_protocol.tier_for("x", "verify", {"kind": "no"}),
                         "judge")

    def test_a_literal_artifact_is_still_a_literal_artifact(self):
        self.assertEqual(
            shadow_protocol.tier_for("shadow-race-pass", "contains_artifact"),
            "contains_artifact")

    def test_a_check_is_NEVER_dropped_whatever_happens_to_its_tier(self):
        _, blocks = shadow_protocol.parse_reply(
            '```goal\n{"outcome": "o", "done_when": ['
            '{"check": "the tests pass"},'
            '{"check": "the copy reads well"},'
            '{"tier": "nonsense", "check": "something else"}]}\n```')
        self.assertEqual(len(blocks["goal"]["done_when"]), 3)
        self.assertEqual([c["tier"] for c in blocks["goal"]["done_when"]],
                         ["judge", "founder_confirm", "judge"])

    def test_the_engine_default_is_the_judge_too(self):
        """validate_done_when read `or "founder_confirm"`, which is how a
        decider that simply omitted the key put a check on the desk."""
        rows = mission_engine.validate_done_when([
            {"check": "the build is green"},
            {"tier": "founder_confirm", "check": "the tests pass"},
            {"tier": "founder_confirm", "check": "the spacing looks right"},
        ])
        self.assertEqual([r["tier"] for r in rows],
                         ["judge", "judge", "founder_confirm"])

    def test_judge_is_an_accepted_decider_tier(self):
        self.assertIn("judge", mission_engine.DECIDER_TIERS)
        self.assertIn("judge", mission_engine.HOW_MET)

    def test_how_met_does_not_overclaim(self):
        """The founder is entitled to know which of the three settled it."""
        self.assertNotEqual(mission_engine.HOW_MET["judge"],
                            mission_engine.HOW_MET["verify"])
        self.assertIn("read", mission_engine.HOW_MET["judge"])


class JudgeEvaluation(unittest.TestCase):
    """A judge row is settled off a STAMP, because evaluate_done_when is
    synchronous and the judging is a model call."""

    def mission(self, **check):
        check.setdefault("tier", "judge")
        check.setdefault("check", "it is right")
        return {"id": "m-1", "done_when": [check]}

    def test_an_unstamped_judge_row_is_unmet(self):
        done, results = mission_engine.evaluate_done_when(self.mission(), "")
        self.assertFalse(done)
        self.assertFalse(results[0]["met"])

    def test_a_met_stamp_settles_it(self):
        done, _ = mission_engine.evaluate_done_when(
            self.mission(judged={"state": "met", "reason": "hunk 3"}), "")
        self.assertTrue(done)

    def test_an_unmet_stamp_does_not(self):
        done, _ = mission_engine.evaluate_done_when(
            self.mission(judged={"state": "unmet", "reason": "no"}), "")
        self.assertFalse(done)

    def test_a_judge_row_can_NEVER_be_satisfied_by_the_transcript(self):
        """The worker saying the words is not the work being done -- the
        m-245777cf1467 failure, pinned against the new tier."""
        m = self.mission(check="the task reaches DONE")
        done, _ = mission_engine.evaluate_done_when(
            m, "Committed as f96c3ade. the task reaches DONE")
        self.assertFalse(done)

    def test_founder_confirm_STILL_never_auto_passes(self):
        done, _ = mission_engine.evaluate_done_when(
            self.mission(tier="founder_confirm", check="you like it"), "x")
        self.assertFalse(done)

    def test_a_judge_row_counts_as_machine_checkable(self):
        """confirmation_is_due asks whether the ONLY thing left is a
        signature; a judge row is not a signature."""
        _, results = mission_engine.evaluate_done_when(
            {"done_when": [
                {"tier": "judge", "check": "a",
                 "judged": {"state": "met", "reason": "r"}},
                {"tier": "founder_confirm", "check": "you like it"}]}, "")
        self.assertTrue(mission_engine.confirmation_is_due(results))


class RunJudges(unittest.TestCase):
    """_run_judges stamps the rows, and cannot_tell is the route home."""

    def run_judges(self, judge, checks):
        saved = {}

        class Store:
            def save(self, m):
                saved["m"] = m

        loop = mission_engine.MissionEngine.__new__(mission_engine.MissionEngine)
        loop.judge = judge
        loop.store = Store()
        loop.probe_root = tempfile.mkdtemp()
        loop._save_field = lambda m, k, v, skip_if=None: None
        m = {"id": "m-1", "objective": "o", "done_when": checks}
        loop_ = asyncio.new_event_loop()
        try:
            loop_.run_until_complete(loop._run_judges(m))
        finally:
            loop_.close()
        return m["done_when"]

    def test_met_stamps_and_settles(self):
        async def judge(check, evidence, outcome):
            return shadow_judge.Verdict("met", "hunk 3 does exactly this")
        rows = self.run_judges(judge, [{"tier": "judge", "check": "c"}])
        self.assertTrue(rows[0]["met"])
        self.assertEqual(rows[0]["judged"]["state"], "met")
        self.assertIn("hunk 3", rows[0]["judged"]["reason"])

    def test_cannot_tell_RETURNS_THE_ROW_TO_THE_FOUNDER(self):
        """THE PROPERTY THAT MAKES THE INVERSION SAFE. Demoting to the judge
        is not a one-way door: a check the judge cannot settle arrives on the
        founder's desk one call later, wording untouched."""
        async def judge(check, evidence, outcome):
            return shadow_judge.Verdict("cannot_tell", "needs your taste")
        rows = self.run_judges(
            judge, [{"tier": "judge", "check": "the spacing is right"}])
        self.assertEqual(rows[0]["tier"], "founder_confirm")
        self.assertFalse(rows[0]["met"])
        self.assertEqual(rows[0]["check"], "the spacing is right")
        self.assertIn("taste", rows[0]["judged"]["reason"])

    def test_a_judge_that_RAISES_leaves_the_row_exactly_as_it_was(self):
        async def judge(check, evidence, outcome):
            raise RuntimeError("boom")
        rows = self.run_judges(judge, [{"tier": "judge", "check": "c"}])
        self.assertEqual(rows[0], {"tier": "judge", "check": "c"})

    def test_a_judge_that_returns_None_says_NOTHING(self):
        async def judge(check, evidence, outcome):
            return None
        rows = self.run_judges(judge, [{"tier": "judge", "check": "c"}])
        self.assertNotIn("judged", rows[0])
        self.assertNotIn("met", rows[0])

    def test_no_judge_bound_means_no_judging(self):
        rows = self.run_judges(None, [{"tier": "judge", "check": "c"}])
        self.assertEqual(rows[0], {"tier": "judge", "check": "c"})

    def test_only_judge_rows_are_touched(self):
        async def judge(check, evidence, outcome):
            return shadow_judge.Verdict("met", "r")
        rows = self.run_judges(judge, [
            {"tier": "founder_confirm", "check": "you like it"},
            {"tier": "verify", "check": "v",
             "probe": {"kind": "command_succeeds", "argv": ["true"]}}])
        self.assertNotIn("judged", rows[0])
        self.assertNotIn("judged", rows[1])
        self.assertFalse(rows[0].get("met"))


# --------------------------------------------------------- the ask gate ---
class AskGate(unittest.TestCase):
    """The same sentence, applied MID-mission. The criteria work fixed what
    the founder signs at the end; this is the middle, which was wide open."""

    def ask(self, reason, **extra):
        d = {"action": "ask_founder", "reason": reason}
        d.update(extra)
        return mission_engine.screen_ask(d)

    def test_a_question_with_an_answer_on_the_machine_is_REFUSED(self):
        for reason in ("do the relevant tests pass?",
                       "did the fix land in the file?",
                       "does the build succeed?",
                       "is this the right file to edit?",
                       "can you check whether anything else broke?"):
            with self.subTest(reason=reason):
                self.assertFalse(self.ask(reason)[0])

    def test_taste_is_admitted(self):
        self.assertTrue(self.ask("which of these two layouts do you prefer",
                                 ask_kind="taste")[0])

    def test_a_founder_held_fact_is_admitted(self):
        self.assertTrue(self.ask("what is the budget cap",
                                 ask_kind="founder_fact")[0])

    def test_a_floor_is_admitted(self):
        admitted, why = self.ask("I need to push --force to origin",
                                 ask_kind="floor")
        self.assertTrue(admitted)
        self.assertIn("d52_destructive_git", why)

    def test_THE_LABEL_DOES_NOT_GET_IT_THROUGH(self):
        """A decider that writes ask_kind: taste over a mechanical question is
        not asking about taste. Honouring the label would make the gate a
        formality a model walks through by typing a word."""
        self.assertFalse(self.ask("do the tests pass", ask_kind="taste")[0])
        self.assertFalse(self.ask("does it build", ask_kind="founder_fact")[0])
        self.assertFalse(self.ask("is the file saved", ask_kind="floor")[0])

    def test_a_confirms_check_ask_is_admitted_without_re_screening(self):
        """It asks for a signature on a row the tier ladder has ALREADY ruled
        is the founder's. Re-screening would be a second opinion that drifts."""
        admitted, _ = self.ask("sign this off", intervention={
            "question": "q", "fields": [],
            "confirms_check": {"index": 0, "field": "f"}})
        self.assertTrue(admitted)

    def test_the_question_TEXT_is_screened_not_just_the_reason(self):
        admitted, _ = self.ask("I need something", intervention={
            "question": "which region should this deploy to?", "fields": []})
        self.assertTrue(admitted)

    def test_a_SCREENING_FAULT_fails_open(self):
        """The one place in this change that fails open, deliberately: a bug
        in the screen must not swallow a question about something
        irreversible. Forced by breaking the floor table the screen reads."""
        real = mission_engine.shadow_egress.floor_check
        mission_engine.shadow_egress.floor_check = lambda _t: 1 / 0
        try:
            admitted, why = self.ask("do the tests pass")
        finally:
            mission_engine.shadow_egress.floor_check = real
        self.assertTrue(admitted)
        self.assertIn("screen unavailable", why)

    def test_an_EMPTY_ask_is_refused_rather_than_admitted(self):
        """Distinct from a fault: there is nothing in it to put to anybody,
        and admitting it would park the mission on a blank card."""
        self.assertFalse(mission_engine.screen_ask(None)[0])
        self.assertFalse(mission_engine.screen_ask({})[0])
        # a decision of the WRONG TYPE is a fault, not an empty ask, so it
        # takes the fail-open path above rather than this one
        self.assertTrue(mission_engine.screen_ask("not a dict")[0])

    def test_the_refusal_tells_the_worker_to_go_and_look(self):
        text = mission_engine.ASK_REFUSED_INSTRUCTION % "whether tests pass"
        self.assertIn("Establish this yourself", text)
        self.assertIn("full access", text)
        self.assertIn("command_succeeds", text)

    def test_ask_kind_is_carried_through_validation(self):
        out = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "r", "ask_kind": "taste"})
        self.assertEqual(out["ask_kind"], "taste")

    def test_an_unknown_ask_kind_is_simply_not_carried(self):
        out = mission_engine.validate_decision(
            {"action": "ask_founder", "reason": "r", "ask_kind": "whatever"})
        self.assertNotIn("ask_kind", out)

    def test_there_IS_an_escape_hatch_after_repeated_refusals(self):
        """Without it the gate eats the mission: a fixed refusal string sent
        twice trips the ping-pong guard and the task dies quietly, which is
        worse for the founder than the question they did not want."""
        self.assertEqual(mission_engine.ASK_REFUSAL_LIMIT, 2)


class PromotionToAProbe(unittest.TestCase):
    """A judge row Shadow later works out how to RUN should stop being judged:
    a probe is deterministic, repeatable and costs no model call."""

    def test_judge_rows_are_eligible_for_verification(self):
        loop = mission_engine.MissionEngine.__new__(mission_engine.MissionEngine)
        m = {"done_when": [
            {"tier": "judge", "check": "the tests pass"},
            {"tier": "founder_confirm", "check": "you like it"},
            {"tier": "verify", "check": "v", "probe": {"kind": "file_exists",
                                                       "path": "a"}},
            {"tier": "judge", "check": "done", "met": True}]}
        self.assertEqual(loop._needs_verification(m), [0, 1])


if __name__ == "__main__":
    unittest.main()
