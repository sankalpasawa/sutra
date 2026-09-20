#!/usr/bin/env python3
"""SHADOW VERIFIES WHAT IS VERIFIABLE (founder, 2026-09-20, second D-SH-1 pass).

THE MEASUREMENT THAT PROMPTED IT. D-SH-1 inverted the tier ladder the day
before: `judge` became the default, and only taste and founder-held facts were
supposed to reach a human. It did not land. A task asked for "10 lines of
MotoGP's latest news" and the check

    "each line is a real, recent MotoGP news item drawn from current sources
     rather than invented or generic filler, and the file contains only the
     10 items with no headers, numbering or bullets"

arrived as a Confirm button. Every clause of it but one is objectively
decidable, and the founder was asked to sign all of them.

THE FAILURE WAS NOT THE TIERING. `shadow_protocol.tier_for` returns `judge`
for that string -- pinned below. It was `shadow_judge.evidence_for`, which
built its blob from `git status`, `git diff` and `git diff --cached` and so
could only ever see CHANGES TO TRACKED FILES. The artifact was a new,
untracked file; both diffs were empty; the judge was shown a filename and
correctly answered `cannot_tell`; `_run_judges` re-tiered the row to the
founder. Every authoring, generation and research task had the same shape.

WHAT THIS FILE PINS, in the layers of the verification ladder:

  L1 probe     a `lines_shape` probe settles "no headers, numbering or
               bullets" from a FIXED shape vocabulary -- never a
               model-authored regex
  L2 facts     the quantities in a file are COUNTED BY MACHINE and carried
               as evidence, so no model is asked to do arithmetic in prose
  L3 judge     the judge is shown the ARTIFACT -- the file the work wrote --
               and never the worker's account of it
  L4 founder   taste and founder-held facts, and nothing else

AND THE TWO RULES THAT KEEP IT HONEST:
  * a worker's claim is still not evidence, and there is still no parameter
    through which one could reach the judge
  * a compound row's probes are a PRECONDITION, never a substitute: a vague
    clause is never reported as verified because a countable one beside it
    was

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_artifact_evidence.py
"""
import asyncio
import os
import subprocess
import tempfile
import unittest

# ── THE LIVE HOME IS NOT A TEST FIXTURE (2026-09-21) ────────────────────
# This suite builds real MissionStore records. Without this line they land
# in the operator's own shadow home: fourteen fixture missions -- "ten
# greatest riders", "ten riders", "x" -- were written there across four
# `python3 -m unittest` runs and appeared in the founder's WAITING ON YOU
# list as tasks they had never started. shadow_ledger.shadow_home() now
# refuses the default home under any runner, so this is belt AND braces:
# the guard stops the damage, this line stops the failure.
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-ae-test-")

import mission_engine
import shadow_evidence
import shadow_judge
import shadow_probe
import shadow_protocol

#: The founder's live check, verbatim. Every assertion about "the composite
#: criterion" in this file is about THIS string, so the regression cannot be
#: quietly re-worded into something easier.
MOTOGP_CHECK = (
    "each line is a real, recent MotoGP news item drawn from current sources "
    "rather than invented or generic filler, and the file contains only the "
    "10 items with no headers, numbering or bullets")

#: Ten lines shaped like the artifact that started this: plain sentences, no
#: markers of any kind. The CONTENT is irrelevant to every test here -- what
#: is being pinned is that Shadow can read and measure it at all.
TEN_PLAIN_LINES = "\n".join(
    "Rider %d won at circuit %d on 20 Sep 2026, a first premier-class win."
    % (i, i) for i in range(1, 11)) + "\n"


class Fixture(unittest.TestCase):
    """A workdir, and a repo when a test wants one."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def write(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def git(self, *args):
        subprocess.run(["git"] + list(args), cwd=self.root, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def repo(self):
        self.git("init")
        self.git("config", "user.email", "t@t.t")
        self.git("config", "user.name", "t")
        self.write("seed.txt", "seed\n")
        self.git("add", "-A")
        self.git("commit", "-m", "base")

    def probe(self, **kw):
        return shadow_probe.run(kw, self.root)


# ------------------------------------------------------- 1-4: L1 probes ---
class ObjectiveProbesSettleThemselves(Fixture):
    """Cases 1-4 of the founder's list: file exists, exactly N lines,
    distinct lines, no bullets or headers. All four are Shadow's."""

    def test_1_file_exists_is_shadows(self):
        self.write("news.txt", TEN_PLAIN_LINES)
        self.assertTrue(self.probe(kind="file_exists", path="news.txt").met)
        self.assertFalse(self.probe(kind="file_exists", path="nope.txt").met)

    def test_2_exact_line_count_is_shadows(self):
        self.write("news.txt", TEN_PLAIN_LINES)
        self.assertTrue(
            self.probe(kind="line_count", path="news.txt", count=10).met)
        res = self.probe(kind="line_count", path="news.txt", count=9)
        self.assertFalse(res.met)
        self.assertIn("10 lines, expected 9", res.reason)

    def test_3_distinct_lines_is_shadows(self):
        self.write("news.txt", TEN_PLAIN_LINES)
        self.assertTrue(self.probe(kind="lines_distinct", path="news.txt").met)
        self.write("dupe.txt", "same\nsame\n")
        res = self.probe(kind="lines_distinct", path="dupe.txt")
        self.assertFalse(res.met)
        self.assertIn("repeated line", res.reason)

    def test_4_no_bullets_headers_or_numbering_is_shadows(self):
        """The clause that had no vocabulary at all before this change."""
        self.write("clean.txt", TEN_PLAIN_LINES)
        self.assertTrue(self.probe(
            kind="lines_shape", path="clean.txt",
            forbid=["bullet", "numbered", "heading", "blank"]).met)

    def test_4b_each_forbidden_shape_is_actually_caught(self):
        cases = {
            "bullet": "- Rider one won the race.\n",
            "numbered": "1. Rider one won the race.\n",
            "heading": "# Latest news\n",
            "blank": "Rider one won.\n\nRider two won.\n",
        }
        for shape, body in cases.items():
            with self.subTest(shape=shape):
                self.write("x.txt", body)
                res = self.probe(kind="lines_shape", path="x.txt",
                                 forbid=[shape])
                self.assertFalse(res.met, "%s was not caught" % shape)
                self.assertIn(shape, res.reason)

    def test_4c_a_sentence_is_not_a_bullet_or_a_number(self):
        """THE FALSE-POSITIVE HALF, and it is the one that matters more. A
        shape test that is too eager makes "no bullets" unsatisfiable by an
        honest file -- a line opening with a minus sign or a year is prose."""
        self.write("x.txt", "-1.017s behind the leader at the flag.\n"
                            "2026 was the season the rule changed.\n")
        self.assertTrue(self.probe(kind="lines_shape", path="x.txt",
                                   forbid=["bullet", "numbered"]).met)

    def test_4d_no_model_authored_pattern_is_ever_accepted(self):
        """THE SECURITY HALF OF THE NEW KIND. `lines_shape` names shapes from
        a fixed table; anything that looks like a pattern is refused, so
        nothing in Shadow ever compiles a string a model wrote."""
        for bad in ({"kind": "lines_shape", "path": "x.txt",
                     "forbid": ["(a+)+$"]},
                    {"kind": "lines_shape", "path": "x.txt",
                     "regex": "^- "},
                    {"kind": "lines_shape", "path": "x.txt",
                     "forbid": ["heading", "nonsense"]},
                    {"kind": "lines_shape", "path": "x.txt"},
                    {"kind": "lines_shape", "path": "x.txt",
                     "forbid": ["bullet"], "require": ["bullet"]}):
            with self.subTest(probe=bad):
                self.assertIsNone(shadow_probe.validate_probe(bad))

    def test_4e_an_empty_file_does_not_pass_vacuously(self):
        self.write("empty.txt", "")
        self.assertFalse(self.probe(kind="lines_shape", path="empty.txt",
                                    forbid=["bullet"]).met)


# ----------------------------------------------------- 5: decomposition ---
class CompositeCriteriaDecompose(Fixture):
    """Case 5: a composite objective criterion is decomposed, not signed."""

    def test_5a_the_live_check_is_not_routed_to_the_founder(self):
        """THE REGRESSION THIS FILE EXISTS FOR. The tiering was never the
        bug, and pinning it stops a future 'fix' from re-adding the demotion
        that D-SH-1 removed."""
        self.assertFalse(shadow_protocol.is_founder_only(MOTOGP_CHECK))
        for proposed in (None, "founder_confirm", "verify", "nonsense"):
            with self.subTest(proposed=proposed):
                self.assertEqual(
                    shadow_protocol.tier_for(MOTOGP_CHECK, proposed, None),
                    "judge")

    def test_5b_one_row_carries_several_probes(self):
        rows = mission_engine.validate_done_when([{
            "tier": "judge", "check": MOTOGP_CHECK,
            "probes": [
                {"kind": "line_count", "path": "news.txt", "count": 10},
                {"kind": "lines_distinct", "path": "news.txt"},
                {"kind": "lines_shape", "path": "news.txt",
                 "forbid": ["bullet", "numbered", "heading", "blank"]}],
        }])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], "judge")
        self.assertEqual(rows[0]["check"], MOTOGP_CHECK,
                         "the founder's wording must survive verbatim")
        self.assertEqual(len(rows[0]["probes"]), 3)

    def test_5c_a_failing_clause_makes_the_row_unmet_with_no_judge_call(self):
        """The decomposition's whole point: the countable clause is settled
        by machine, and a wrong count needs nobody's opinion."""
        self.write("news.txt", "one\ntwo\n")        # not 10 lines
        m = {"done_when": [{
            "tier": "judge", "check": MOTOGP_CHECK,
            "judged": {"state": "met", "reason": "looked fine"},
            "probes": [{"kind": "line_count", "path": "news.txt",
                        "count": 10}]}]}
        met, results = mission_engine.evaluate_done_when(
            m, "", probe_root=self.root)
        self.assertFalse(met)
        self.assertFalse(results[0]["met"],
                         "a stamped judge verdict must not override a probe "
                         "that refutes the same row")

    def test_5d_passing_probes_do_not_by_themselves_settle_the_row(self):
        """THE 'DO NOT PRETEND A VAGUE PROPERTY IS VERIFIED' RULE. Every
        countable clause passes; the row is still unmet until the residual
        judgement is made, because 'a real news item rather than filler' was
        not checked by any of them."""
        self.write("news.txt", TEN_PLAIN_LINES)
        m = {"done_when": [{
            "tier": "judge", "check": MOTOGP_CHECK,
            "probes": [{"kind": "line_count", "path": "news.txt",
                        "count": 10},
                       {"kind": "lines_distinct", "path": "news.txt"}]}]}
        met, results = mission_engine.evaluate_done_when(
            m, "", probe_root=self.root)
        self.assertFalse(met)
        self.assertFalse(results[0]["met"])

    def test_5e_probes_never_sit_underneath_a_signature(self):
        """A machine must not sign the founder's name -- the same rule
        resolve_verify_tier has always applied to the singular `probe`."""
        rows = mission_engine.validate_done_when([{
            "tier": "founder_confirm",
            "check": "the wording reads well and is your preferred phrasing",
            "probes": [{"kind": "file_exists", "path": "news.txt"}]}])
        self.assertEqual(rows[0]["tier"], "founder_confirm")
        self.assertNotIn("probes", rows[0])

    def test_5f_a_malformed_probe_in_the_list_is_dropped_not_trusted(self):
        rows = mission_engine.validate_done_when([{
            "tier": "judge", "check": MOTOGP_CHECK,
            "probes": [{"kind": "file_exists", "path": "../escape.txt"},
                       {"kind": "not_a_kind", "path": "news.txt"},
                       {"kind": "line_count", "path": "news.txt",
                        "count": True},
                       {"kind": "file_exists", "path": "news.txt"}]}])
        self.assertEqual(rows[0]["probes"],
                         [{"kind": "file_exists", "path": "news.txt"}])


# --------------------------------------------------- 6: the artifact lane -
class TheJudgeCanSeeTheArtifact(Fixture):
    """Case 6: a source/content-backed criterion is verifiable when the
    evidence is there. This is the fix for the measured failure."""

    def test_6a_an_OWNED_file_is_readable_an_unowned_one_is_not(self):
        """AMENDED 2026-09-21. The original asserted that ANY untracked file
        reached the judge, which was a cross-mission leak: git status reports
        every uncommitted file in a shared workdir, so a judge settling one
        mission's criterion could read another mission's artifacts.

        The artifact lane survives; only its SOURCE changed. A path the
        caller owns is read in full; a path merely lying around is not."""
        self.repo()
        self.write("news.txt", TEN_PLAIN_LINES)
        self.write("someone-elses.txt", "another mission wrote this\n")
        blob = shadow_judge.evidence_for(self.root, None, ["news.txt"])
        self.assertIn("?? news.txt", blob, "git still LISTS what changed")
        self.assertIn("Rider 1 won", blob,
                      "the owned artifact is readable, which is the whole "
                      "point of the artifact lane")
        self.assertNotIn("another mission wrote this", blob,
                         "a file nobody owns never becomes evidence")

    def test_6b_the_measured_facts_travel_with_it(self):
        self.repo()
        self.write("news.txt", TEN_PLAIN_LINES)
        blob = shadow_judge.evidence_for(self.root, None, ["news.txt"])
        self.assertIn("lines=10", blob)
        self.assertIn("distinct_non_empty_lines=10", blob)
        self.assertIn("bullet_lines=0", blob)
        self.assertIn("heading_lines=0", blob)
        self.assertIn("numbered_lines=0", blob)

    def test_6c_a_probe_named_path_is_read_even_without_git(self):
        """A workdir that is not a repo still yields evidence when Shadow's
        own probes name the file -- the artifact lane does not depend on git
        knowing about the work."""
        self.write("report.md", "# Findings\n\nsource: https://example.test\n")
        blob = shadow_judge.evidence_for(self.root, None, ["report.md"])
        self.assertIn("example.test", blob)

    def test_6d_the_engine_hands_the_judge_its_own_probe_paths(self):
        self.write("news.txt", TEN_PLAIN_LINES)
        loop = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)
        loop.probe_root = self.root
        blob = loop._judge_evidence({"done_when": [{
            "tier": "judge", "check": MOTOGP_CHECK,
            "probes": [{"kind": "line_count", "path": "news.txt",
                        "count": 10}]}]})
        self.assertIn("Rider 1 won", blob)
        self.assertIn("MET", blob, "the probe result is evidence too")

    def test_6e_modified_tracked_files_are_not_read_twice(self):
        """THE BUDGET RULE. A modified file is already in the diff; reading
        it again would spend the artifact budget on a duplicate."""
        self.repo()
        self.write("seed.txt", "seed\nchanged\n")
        blob = shadow_judge.evidence_for(self.root)
        self.assertIn("git diff", blob)
        self.assertNotIn("THE ARTIFACT", blob)


# ------------------------------------------------------- the boundaries ---
class ArtifactBoundaries(Fixture):
    """The lane must not become unlimited workspace ingestion (founder,
    2026-09-20). Every limit is a refusal and every refusal is REPORTED."""

    def test_confinement_is_the_probe_resolver(self):
        for path in ("../escape.txt", "/etc/passwd", "~/secrets"):
            with self.subTest(path=path):
                text, note = shadow_evidence.read_artifact(self.root, path)
                self.assertIsNone(text)
                self.assertTrue(note)

    def test_a_symlink_out_of_the_workdir_is_refused(self):
        outside = tempfile.mkdtemp()
        with open(os.path.join(outside, "secret.txt"), "w") as fh:
            fh.write("not yours")
        os.symlink(os.path.join(outside, "secret.txt"),
                   os.path.join(self.root, "link.txt"))
        text, note = shadow_evidence.read_artifact(self.root, "link.txt")
        self.assertIsNone(text)
        self.assertIn("escapes the workdir", note)

    def test_a_binary_file_is_refused_and_says_so(self):
        with open(os.path.join(self.root, "b.bin"), "wb") as fh:
            fh.write(b"\x89PNG\x00\x01\x02binary")
        text, note = shadow_evidence.read_artifact(self.root, "b.bin")
        self.assertIsNone(text)
        self.assertIn("binary", note)

    def test_a_file_over_the_stat_ceiling_is_not_opened(self):
        self.write("big.txt", "x" * (shadow_evidence.MAX_STAT_BYTES + 10))
        text, note = shadow_evidence.read_artifact(self.root, "big.txt")
        self.assertIsNone(text)
        self.assertIn("ceiling", note)

    def test_truncation_is_announced_rather_than_silent(self):
        self.write("long.txt", "line\n" * 20000)
        text, note = shadow_evidence.read_artifact(self.root, "long.txt")
        self.assertIsNone(note)
        self.assertLessEqual(len(text),
                             shadow_evidence.MAX_FILE_BYTES + 400)
        self.assertIn("truncated", text)
        self.assertIn("cannot_tell", text,
                      "a judge shown a fragment must be told it is one")

    def test_the_file_count_is_capped_and_the_overflow_is_announced(self):
        names = []
        for i in range(shadow_evidence.MAX_FILES + 3):
            names.append("f%d.txt" % i)
            self.write(names[-1], "content %d\n" % i)
        out = shadow_evidence.render(self.root, names)
        self.assertIn("f0.txt", out)
        self.assertNotIn("content %d" % (shadow_evidence.MAX_FILES + 2), out)
        self.assertIn("NOT shown here", out)

    def test_the_section_budget_is_respected(self):
        names = []
        for i in range(6):
            names.append("f%d.txt" % i)
            self.write(names[-1], ("row %d\n" % i) * 2000)
        out = shadow_evidence.render(self.root, names)
        self.assertLessEqual(len(out),
                             shadow_evidence.MAX_SECTION_BYTES + 2000)

    def test_a_missing_file_is_reported_but_not_echoed(self):
        """THE HONESTY RULE AND THE LEAK RULE, meeting.

        A file that could not be read must be REPORTED -- a silent skip is
        evidence loss the judge cannot know about, so it would grade a
        partial picture believing it was whole. But the path must NOT be
        echoed, because a candidate with no file behind it is nothing but the
        caller's string (test_9b). So the judge is told the COUNT and told to
        answer cannot_tell, which is everything it needs and nothing it
        cannot trust.
        """
        out = shadow_evidence.render(self.root, ["nope.txt"])
        self.assertIn("could NOT be read", out)
        self.assertIn("cannot_tell", out)
        self.assertNotIn("nope.txt", out)

    def test_an_over_long_line_is_measured_rather_than_quoted(self):
        self.write("min.js", "a" * 5000 + "\n")
        out = shadow_evidence.render(self.root, ["min.js"])
        self.assertIn("not quoted", out)
        self.assertNotIn("a" * 3000, out)

    def test_nothing_is_read_that_nobody_named(self):
        """NO WALK, NO GLOB. A file that is neither named nor reported by git
        does not exist to this lane."""
        self.write("private.txt", "TOPSECRET")
        self.assertEqual(shadow_evidence.render(self.root, []), "")
        self.assertNotIn("TOPSECRET",
                         shadow_judge.evidence_for(self.root))


# ------------------------------------------------- 7-9: what must not move -
class WhatMustNotMove(Fixture):
    """Cases 7, 8, 9: taste still reaches the founder, the founder-confirm
    path still works, and a worker's claim is still not verification."""

    def test_7_a_subjective_criterion_stays_the_founders(self):
        for check in ("the wording reads well",
                      "this is the design you preferred",
                      "the copy is acceptable to you",
                      "it looks right on a narrow window",
                      "the spend limit is the one you wanted"):
            with self.subTest(check=check):
                self.assertEqual(
                    shadow_protocol.tier_for(check, None, None),
                    "founder_confirm")

    def test_8_the_founder_confirm_path_still_settles_a_row(self):
        m = {"done_when": [{"tier": "founder_confirm", "check": "you like it",
                            "met": True}]}
        met, results = mission_engine.evaluate_done_when(m, "")
        self.assertTrue(met)
        self.assertTrue(results[0]["met"])
        m["done_when"][0]["met"] = False
        met, _ = mission_engine.evaluate_done_when(m, "")
        self.assertFalse(met, "founder_confirm never auto-passes")

    def test_9a_a_worker_claim_is_not_verification(self):
        """The m-245777cf1467 failure, re-pinned against the new lanes: a
        perfect sentence over a missing file is still unmet."""
        claim = ("I created news.txt with 10 distinct lines. "
                 "DONE-CHECK: the file holds 10 lines. The task reaches DONE.")
        m = {"done_when": [{"tier": "verify",
                            "check": "the file holds 10 lines",
                            "probe": {"kind": "line_count",
                                      "path": "news.txt", "count": 10}}]}
        met, _ = mission_engine.evaluate_done_when(
            m, claim, verifier=lambda *a: True, probe_root=self.root)
        self.assertFalse(met, "the filesystem answers, not the transcript")

    def test_9b_the_artifact_lane_did_not_open_a_door_for_prose(self):
        """THE LOAD-BEARING EXCLUSION, re-asserted against the NEW source.

        `artifact_paths` is the one new way into evidence_for, so the
        question it has to answer is the one the whole module rests on: can a
        sentence somebody wrote reach the judge through it? It cannot, and it
        takes TWO rules to make that true rather than one -- this test caught
        the gap between them when only the first existed.

          1. an entry that is not a path SHAPE is dropped (_path_candidates
             asks shadow_probe's own validator, so `..`, `~` and NUL are
             refused exactly as they are on a probe)
          2. a path that names no file is COUNTED, never echoed
             (shadow_evidence.render) -- because a candidate with no file
             behind it is nothing but the caller's string, so quoting it back
             to explain the refusal is the whole leak

        Rule 1 alone is not enough and that is the point of pinning both: a
        short claim is a syntactically valid relative path, so it survives
        the shape screen and is stopped only by rule 2.
        """
        self.repo()
        claim = "I fixed it perfectly, all tests pass, DONE-CHECK: x"
        blob = shadow_judge.evidence_for(self.root, None, [claim])
        self.assertNotIn("fixed it perfectly", blob)
        self.assertNotIn("DONE-CHECK", blob)
        # ...and the judge is still TOLD that something could not be read,
        # so it can answer cannot_tell rather than judge a gap it cannot see
        self.assertIn("could NOT be read", blob)

    def test_9b2_a_path_shaped_escape_is_refused_before_the_filesystem(self):
        """Rule 1 of the two above, on its own."""
        self.repo()
        blob = shadow_judge.evidence_for(
            self.root, None, ["../../etc/passwd", "~/.ssh/id_rsa", "x\x00y"])
        self.assertNotIn("passwd", blob)
        self.assertNotIn("id_rsa", blob)
        self.assertNotIn("THE ARTIFACT", blob,
                         "every candidate was refused on shape, so the lane "
                         "should not have run at all")

    def test_9c_the_worker_is_never_shown_a_probe(self):
        """Unchanged rule, re-pinned because `probes` is a new field that
        could have leaked into the worker's brief."""
        import app
        block = app._worker_checks_block({"done_when": [{
            "tier": "verify", "check": MOTOGP_CHECK,
            "probe": {"kind": "line_count", "path": "news.txt", "count": 10},
            "probes": [{"kind": "lines_shape", "path": "news.txt",
                        "forbid": ["bullet"]}]}]})
        self.assertIn(MOTOGP_CHECK, block)
        self.assertNotIn("line_count", block)
        self.assertNotIn("news.txt", block)


# ------------------------------------------------ 10: security unchanged --
class SecurityAndConfinementUnchanged(Fixture):
    """Case 10. The new kind and the new lane add no capability: every
    operation is a read, and the floors still screen commands."""

    def test_the_new_kind_is_read_only(self):
        self.write("x.txt", "line\n")
        before = sorted(os.listdir(self.root))
        self.probe(kind="lines_shape", path="x.txt", forbid=["bullet"])
        self.assertEqual(sorted(os.listdir(self.root)), before)

    def test_path_escapes_are_still_refused_by_the_validator(self):
        for path in ("../x.txt", "..\\x.txt", "~/x.txt", "a/../../x.txt"):
            with self.subTest(path=path):
                self.assertIsNone(shadow_probe.validate_probe(
                    {"kind": "lines_shape", "path": path,
                     "forbid": ["bullet"]}))

    def test_a_shell_in_argv_costume_is_still_refused(self):
        self.assertIsNone(shadow_probe.validate_probe(
            {"kind": "command_succeeds", "argv": ["bash", "-lc", "rm -rf /"]}))

    def test_a_floored_command_probe_is_still_refused(self):
        res = self.probe(kind="command_succeeds",
                         argv=["git", "push", "--force", "origin", "main"])
        self.assertFalse(res.met)
        self.assertIn("floor", res.reason)


# ----------------------------------------- 11-12: no regression elsewhere -
class NoRegressionInWhatWasFixedBefore(Fixture):
    """Cases 11 and 12: the pure-evidence rule and the Summary/done
    behaviour are untouched by this change."""

    def test_11_evidence_is_still_empty_when_there_is_nothing_to_show(self):
        self.assertEqual(shadow_judge.evidence_for(self.root), "")
        self.assertEqual(shadow_judge.evidence_for("/nope/nope/nope"), "")
        self.assertEqual(shadow_judge.evidence_for(None), "")
        self.assertEqual(shadow_judge.evidence_for(self.root, None, []), "")

    def test_12a_an_all_machine_mission_reaches_done_with_no_confirm(self):
        """THE UX REQUIREMENT, at its source rather than in the UI. When
        every check is objectively verifiable and passes, there is no
        founder_confirm row left for a Confirm button to render from."""
        self.write("news.txt", TEN_PLAIN_LINES)
        m = {"done_when": [
            {"tier": "verify", "check": "the file exists",
             "probe": {"kind": "file_exists", "path": "news.txt"}},
            {"tier": "verify", "check": "it holds 10 lines",
             "probe": {"kind": "line_count", "path": "news.txt",
                       "count": 10}},
            {"tier": "verify", "check": "no bullets, headings or numbering",
             "probe": {"kind": "lines_shape", "path": "news.txt",
                       "forbid": ["bullet", "numbered", "heading"]}}]}
        met, results = mission_engine.evaluate_done_when(
            m, "", probe_root=self.root)
        self.assertTrue(met)
        self.assertEqual([r["met"] for r in results], [True, True, True])
        self.assertEqual(
            [r for r in results if r["tier"] == "founder_confirm"], [],
            "nothing here is the founder's, so nothing should ask them")

    def test_12b_the_completion_summary_still_describes_each_tier(self):
        summary = mission_engine.completion_summary(
            {"done_when": [
                {"tier": "verify", "check": "the file exists"},
                {"tier": "judge", "check": "the items are real"}]},
            [{"tier": "verify", "check": "the file exists",
              "met": True},
             {"tier": "judge", "check": "the items are real",
              "met": True}])
        self.assertTrue(summary)

    def test_12c_a_row_with_no_probes_scores_exactly_as_before(self):
        """The additive promise: `probes` absent means byte-identical
        behaviour on every tier."""
        cases = [
            ({"tier": "verify", "check": "x"}, False),
            ({"tier": "judge", "check": "x",
              "judged": {"state": "met", "reason": "r"}}, True),
            ({"tier": "judge", "check": "x"}, False),
            ({"tier": "contains_artifact", "check": "MARKER-7"}, True),
            ({"tier": "founder_confirm", "check": "x", "met": True}, True),
        ]
        for row, want in cases:
            with self.subTest(row=row):
                met, _ = mission_engine.evaluate_done_when(
                    {"done_when": [row]}, "output MARKER-7 here",
                    probe_root=self.root)
                self.assertEqual(met, want)


# ------------------------------------------------------- the judge gate ---
class TheJudgeIsNotCalledWhenAProbeAlreadyAnswered(Fixture):
    """A compound row whose countable clause is false needs no model call --
    and the evaluator and the judge loop must agree about that."""

    def test_a_refuted_row_is_skipped_by_run_judges(self):
        self.write("news.txt", "one\ntwo\n")
        calls = []

        async def judge(check, evidence, outcome):
            calls.append(check)
            return shadow_judge.Verdict("met", "looked fine")

        loop = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)
        loop.probe_root = self.root
        loop.judge = judge
        m = {"id": "m-test", "done_when": [{
            "tier": "judge", "check": MOTOGP_CHECK,
            "probes": [{"kind": "line_count", "path": "news.txt",
                        "count": 10}]}]}
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            loop._run_judges(m))
        self.assertEqual(calls, [],
                         "no model call is worth paying for on a row a probe "
                         "has already refuted")


if __name__ == "__main__":
    unittest.main()
