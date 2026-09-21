#!/usr/bin/env python3
"""A FOUNDER CONFIRMATION MUST BE SELF-CONTAINED (founder, 2026-09-21).

THE FAILURE. A task was "make a 10 line list of the greatest MotoGP riders
ever and put it in some doc". Shadow settled what it could and then asked:

    "Does this ten-line ranking work as the greatest premier-class riders
     ever?"

The question is correctly the founder's -- a ranking of greatness is taste
and no probe will ever settle it. It was also unanswerable as presented: the
ten riders existed only in the worker's chat, so the founder was asked to
approve a list they could not see and had to open a second chat to answer a
question Shadow had put to them.

THE RULE. When Shadow puts a decision to a human, the surface carrying the
decision carries the evidence needed to make it. The worker chat stays
available as the full transcript; it stops being a REQUIRED stop.

WHAT THIS FILE PINS, as the founder's own acceptance list:

   1  ranking case     the items and their order are in the confirmation
   2  file case        the relevant content is in the confirmation
   3  visual case      the image is provided, not described
   4  research case    the claims/evidence needing judgement are visible
   5  machine-only     a mechanically settled criterion is NOT asked
   6  subjective       taste IS asked -- with the artifact attached
   7  large artifact   bounded preview, and the cut is announced
   8  no-context       says what is missing rather than asking the impossible
   9  regression       verification, completion and the tier ladder intact

AND THE PROPERTY THAT MAKES IT SAFE: the packet is built from FILES, so
there is no code path from the worker's prose to the founder's decision
surface. That is asserted directly rather than assumed.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_decision_packet.py
"""
import inspect
import os
import re
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
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-dp-test-")

import mission_engine
import shadow_decision
import shadow_evidence
import shadow_protocol

#: The founder's live question, verbatim.
RANKING_ASK = ("Does this ten-line ranking work as the greatest "
               "premier-class riders ever?")

TEN_RIDERS = "\n".join([
    "Giacomo Agostini", "Valentino Rossi", "Marc Marquez", "Mike Hailwood",
    "Eddie Lawson", "Mick Doohan", "Geoff Duke", "Casey Stoner",
    "Kenny Roberts", "Jorge Lorenzo"]) + "\n"


class Fixture(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def write(self, name, text):
        with open(os.path.join(self.root, name), "w") as fh:
            fh.write(text)

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

    def mission(self, done_when, **kw):
        m = {"id": "m-x", "objective": "ten greatest riders",
             "done_when": done_when}
        m.update(kw)
        return m


# ------------------------------------------------- 1: the ranking case ---
class RankingIsVisibleInTheConfirmation(Fixture):
    """Case 1. The founder can see the ten riders and their order without
    opening the worker chat."""

    def packet(self):
        self.write("riders.txt", TEN_RIDERS)
        return shadow_decision.packet_for(self.mission([
            {"tier": "verify", "check": "the file holds 10 lines",
             "probe": {"kind": "line_count", "path": "riders.txt",
                       "count": 10}},
            {"tier": "founder_confirm", "check": RANKING_ASK},
        ]), self.root)

    def test_the_question_is_carried_verbatim(self):
        p = self.packet()
        self.assertEqual([a["check"] for a in p["asks"]], [RANKING_ASK])
        self.assertEqual(p["asks"][0]["index"], 1,
                         "the index is the RECORD's, because confirm_check "
                         "signs by index")

    def test_every_rider_is_in_the_packet(self):
        p = self.packet()
        blob = "\n".join(a.get("text", "") for a in p["artifacts"])
        for rider in TEN_RIDERS.strip().split("\n"):
            self.assertIn(rider, blob, "%s is not visible" % rider)

    def test_the_ORDER_is_preserved_not_just_the_names(self):
        """A ranking is an ORDER. A packet that carried the ten names as a
        set would satisfy "the items are there" and still be unanswerable,
        because the question is about which is first."""
        p = self.packet()
        text = p["artifacts"][0]["text"]
        seen = [text.find(r) for r in TEN_RIDERS.strip().split("\n")]
        self.assertEqual(seen, sorted(seen),
                         "the riders must appear in the file's own order")

    def test_the_machine_facts_ride_along(self):
        p = self.packet()
        self.assertTrue(any(e["met"] and "10 lines" in e["how"]
                            for e in p["established"]),
                        "what Shadow already settled is part of the packet")
        self.assertEqual(p["artifacts"][0]["facts"]["lines"], 10)

    def test_only_the_subjective_row_is_asked(self):
        """PART 4: the precise boundary that still needs a human. The line
        count is settled and must not be re-asked."""
        p = self.packet()
        self.assertEqual(len(p["asks"]), 1)
        self.assertNotIn("10 lines", p["asks"][0]["check"])


# ---------------------------------------------------- 2: the file case ---
class FileContentIsVisible(Fixture):

    def test_2_generated_content_is_in_the_confirmation(self):
        self.write("notes.md", "# Draft\n\nThe wording we settled on.\n")
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm",
             "check": "is this wording acceptable for our brand"},
            {"tier": "verify", "check": "the file exists",
             "probe": {"kind": "file_exists", "path": "notes.md"}},
        ]), self.root)
        self.assertIn("The wording we settled on.",
                      p["artifacts"][0]["text"])

    def test_an_untracked_file_NOBODY_OWNS_is_NOT_pulled_in(self):
        """THIS TEST ASSERTED THE BUG (founder, 2026-09-21), and it is kept
        inverted rather than deleted so the trade is visible.

        It used to require that a file nobody probed still reached the
        packet, on the reasoning that git reports it as new. That is a
        CROSS-MISSION LEAK: git status answers "what is uncommitted", which
        in a shared workdir is every file every previous mission left behind.
        Measured on the live repo -- a Europe trip mission's decision surface
        carried `marc-marquez.txt`, `motogp-top-10-news.md` and
        `weight-loss-plan.html`.

        Discovery is not ownership. A mission that owns nothing shows
        nothing, and says so."""
        self.repo()
        self.write("riders.txt", TEN_RIDERS)
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": RANKING_ASK}]), self.root)
        self.assertEqual(p["artifacts"], [],
                         "an unowned file must never become evidence")
        self.assertTrue(p["missing"], "...and the gap is stated in words")


# -------------------------------------------------- 3: the visual case ---
class VisualArtifactsAreProvided(Fixture):

    PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
           b"\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDAT"
           b"x\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00"
           b"IEND\xaeB`\x82")

    def png(self, name="shot.png", blob=None):
        with open(os.path.join(self.root, name), "wb") as fh:
            fh.write(blob if blob is not None else self.PNG)

    def test_3_the_image_is_inlined_not_described(self):
        """A path would be a preview the founder cannot open -- this app
        serves no workspace files -- so the bytes ride in the packet."""
        self.png()
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": "does this look good"},
            {"tier": "verify", "check": "the shot exists",
             "probe": {"kind": "file_exists", "path": "shot.png"}},
        ]), self.root)
        art = p["artifacts"][0]
        self.assertEqual(art["kind"], "image")
        self.assertTrue(art["data_uri"].startswith("data:image/png;base64,"))
        self.assertFalse(art["too_big"])

    def test_an_oversized_image_says_so_rather_than_drawing_nothing(self):
        self.png(blob=b"\x89PNG\r\n\x1a\n"
                 + b"\x00" * (shadow_decision.MAX_IMAGE_BYTES + 10))
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": "does this look good"},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "shot.png"}},
        ]), self.root)
        self.assertTrue(p["artifacts"][0]["too_big"])
        self.assertEqual(p["artifacts"][0]["data_uri"], "")

    def test_an_unlisted_binary_type_is_never_inlined(self):
        """IMAGE_TYPES is a short explicit list precisely so a new binary
        format cannot become a base64 blob by accident."""
        with open(os.path.join(self.root, "a.bin"), "wb") as fh:
            fh.write(b"\x00\x01\x02binary")
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": "ok?"},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "a.bin"}},
        ]), self.root)
        self.assertEqual(p["artifacts"], [])
        self.assertTrue(p["missing"], "and it says it has nothing to show")


# ------------------------------------------------ 4: the research case ---
class ResearchClaimsAreVisible(Fixture):

    def test_4_the_claims_and_their_sources_are_in_the_packet(self):
        self.write("findings.md",
                   "Claim: adoption doubled in Q3.\n"
                   "Source: https://example.test/report-q3\n"
                   "Claim: churn fell to 4%.\n"
                   "Source: https://example.test/churn\n")
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm",
             "check": "are these findings strong enough to act on"},
            {"tier": "verify", "check": "the findings file exists",
             "probe": {"kind": "file_exists", "path": "findings.md"}},
        ]), self.root)
        text = p["artifacts"][0]["text"]
        self.assertIn("adoption doubled in Q3", text)
        self.assertIn("https://example.test/report-q3", text,
                      "the evidence for the claim travels with the claim")


# --------------------------------------------- 5 + 6: who gets asked at all
class OnlyTheHumanPartIsAsked(Fixture):
    """Cases 5 and 6: the confirmation policy is the NATURE OF THE CRITERION
    (founder, 2026-09-21), never the task type."""

    def test_5_a_mechanically_settled_criterion_is_never_asked(self):
        """It is not asked merely because the information also happens to be
        in the worker transcript. The ladder decides by the criterion."""
        for check in ("the file holds 10 lines",
                      "the tests pass",
                      "each line is distinct",
                      "the build succeeds"):
            with self.subTest(check=check):
                self.assertNotEqual(
                    shadow_protocol.tier_for(check, None, None),
                    "founder_confirm")

    def test_5b_a_machine_only_mission_produces_no_packet_at_all(self):
        self.write("riders.txt", TEN_RIDERS)
        p = shadow_decision.packet_for(self.mission([
            {"tier": "verify", "check": "the file holds 10 lines",
             "probe": {"kind": "line_count", "path": "riders.txt",
                       "count": 10}}]), self.root)
        self.assertIsNone(p, "nothing is being asked, so nothing is packed")

    def test_6_taste_is_asked_AND_carries_its_artifact(self):
        for check in ("does this wording read well",
                      "is this the design you preferred",
                      "is this acceptable to you"):
            with self.subTest(check=check):
                self.assertEqual(
                    shadow_protocol.tier_for(check, None, None),
                    "founder_confirm")
        self.write("copy.txt", "Ship faster. Worry less.\n")
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": "does this wording read well"},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "copy.txt"}},
        ]), self.root)
        self.assertIn("Ship faster.", p["artifacts"][0]["text"])

    def test_6b_a_met_founder_row_is_not_re_asked(self):
        self.write("copy.txt", "x\n")
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": "already signed",
             "met": True, "confirmed_by": "founder"}]), self.root)
        self.assertIsNone(p)


# ------------------------------------------------ 7: bounded, announced ---
class LargeArtifactsAreBoundedAndSaySo(Fixture):

    def test_7_a_huge_file_is_cut_and_the_cut_is_announced(self):
        self.write("big.txt", "a line of text here\n" * 40000)
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": "is this acceptable to you"},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "big.txt"}},
        ]), self.root)
        art = p["artifacts"][0]
        self.assertTrue(art["truncated"],
                        "nobody may approve a file believing they saw it all")
        self.assertLessEqual(len(art["text"]), shadow_decision.MAX_TEXT)

    def test_the_packet_total_is_bounded_across_artifacts(self):
        names = []
        for i in range(6):
            names.append("f%d.txt" % i)
            self.write(names[-1], ("row %d\n" % i) * 4000)
        p = shadow_decision.packet_for(self.mission(
            [{"tier": "founder_confirm", "check": "is this acceptable to you"}]
            + [{"tier": "verify", "check": "c%d" % i,
                "probe": {"kind": "file_exists", "path": n}}
               for i, n in enumerate(names)]), self.root)
        total = sum(len(a.get("text", "")) for a in p["artifacts"])
        self.assertLessEqual(total, shadow_decision.MAX_TOTAL_TEXT)
        self.assertLessEqual(len(p["artifacts"]),
                             shadow_decision.MAX_ARTIFACTS)


# ----------------------------------------------- 8: nothing to show ------
class TheNoContextCaseIsHonest(Fixture):

    def test_8_it_says_what_is_missing(self):
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": RANKING_ASK}]), self.root)
        self.assertEqual(p["artifacts"], [])
        self.assertIn("could not gather", p["missing"])
        self.assertEqual([a["check"] for a in p["asks"]], [RANKING_ASK],
                         "the question is still asked -- honestly, with its "
                         "own gap stated")

    def test_a_probe_naming_a_missing_file_does_not_invent_one(self):
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": RANKING_ASK},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "nope.txt"}},
        ]), self.root)
        self.assertEqual(p["artifacts"], [])
        self.assertTrue(p["missing"])


# --------------------------------------- the leak boundary, asserted -----
class TheWorkerCannotTalkToTheDecisionSurface(Fixture):
    """The property that makes the whole packet safe, and it is STRUCTURAL
    rather than a filter: the packet is built from files, so there is no
    code path from the worker's prose to the founder's decision."""

    def test_no_producer_takes_a_transcript(self):
        for fn in (shadow_decision.packet_for, shadow_decision.artifacts_for,
                   shadow_decision.established_for,
                   shadow_decision.candidate_paths,
                   shadow_decision.open_asks):
            params = list(inspect.signature(fn).parameters)
            for name in params:
                for banned in ("transcript", "prose", "claim", "reply",
                               "say", "message", "said", "text"):
                    self.assertNotIn(banned, name,
                                     "%s(%s) could carry the worker's words "
                                     "to the founder" % (fn.__name__, name))

    def test_the_worker_account_never_reaches_the_packet(self):
        self.repo()
        self.write("riders.txt", TEN_RIDERS)
        claim = "I picked these perfectly. DONE-CHECK: the ranking is right."
        m = self.mission([{"tier": "founder_confirm", "check": RANKING_ASK}],
                         result_excerpt=claim, last_instruction=claim,
                         pending_say=claim)
        p = shadow_decision.packet_for(m, self.root)
        blob = repr(p)
        self.assertNotIn("picked these perfectly", blob)
        self.assertNotIn("DONE-CHECK", blob)

    def test_confinement_is_the_probe_resolver(self):
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": RANKING_ASK},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "../../etc/passwd"}},
        ]), self.root)
        self.assertEqual(p["artifacts"], [],
                         "a probe path that escapes is refused at validation "
                         "and can never reach the founder's surface")


# --------------------------------------------- 9: the engine funnels -----
class TheEngineStampsItAtBothDoors(Fixture):
    """The packet is produced at the NARROWEST SHARED ABSTRACTION -- the two
    places a mission goes to a human -- so no surface has to build its own."""

    def engine(self):
        eng = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)
        eng.probe_root = self.root
        return eng

    def test_await_confirmation_stamps_the_packet(self):
        self.write("riders.txt", TEN_RIDERS)
        store = mission_engine.MissionStore()
        m = store.create("ten greatest riders", "research", done_when=[
            {"tier": "verify", "check": "the file holds 10 lines",
             "probe": {"kind": "line_count", "path": "riders.txt",
                       "count": 10}},
            {"tier": "founder_confirm", "check": RANKING_ASK}])
        store.transition(m["id"], "brief_confirm", "briefed")
        store.transition(m["id"], "running", "go")
        eng = self.engine()
        eng.store = store
        out = eng._await_confirmation(m["id"])
        self.assertEqual(out["pause_reason"], "founder_confirm")
        self.assertIn("Giacomo Agostini",
                      out["decision"]["artifacts"][0]["text"])
        self.assertIn("decision", store.load(m["id"]),
                      "and it is persisted, not only returned")

    def test_a_packet_failure_never_fails_the_pause(self):
        """NEVER RAISES is load-bearing here: this is the path to the
        founder, and an exception would turn "ask" into a failed mission."""
        store = mission_engine.MissionStore()
        m = store.create("x", "research", done_when=[
            {"tier": "founder_confirm", "check": RANKING_ASK}])
        store.transition(m["id"], "brief_confirm", "briefed")
        store.transition(m["id"], "running", "go")
        eng = self.engine()
        eng.store = store
        eng.probe_root = "/nonexistent/workdir/nowhere"
        out = eng._await_confirmation(m["id"])
        self.assertEqual(out["pause_reason"], "founder_confirm",
                         "the pause happened regardless")


# ------------------------------------------- 9: nothing else moved -------
class ExistingBehaviourIsIntact(Fixture):

    def test_the_tier_ladder_is_unchanged(self):
        self.assertEqual(shadow_protocol.FALLBACK_TIER, "judge")
        self.assertEqual(shadow_protocol.tier_for("the tests pass", None,
                                                  None), "judge")
        self.assertEqual(
            shadow_protocol.tier_for("does the wording read well", None,
                                     None), "founder_confirm")

    def test_the_packet_cannot_satisfy_a_check(self):
        """It is read-only evidence. confirm_check remains the only writer
        of a founder_confirm `met` flag."""
        m = self.mission([{"tier": "founder_confirm", "check": RANKING_ASK}])
        self.write("riders.txt", TEN_RIDERS)
        shadow_decision.packet_for(m, self.root)
        met, results = mission_engine.evaluate_done_when(
            m, "", probe_root=self.root)
        self.assertFalse(met)
        self.assertFalse(results[0]["met"])

    def test_evaluate_and_completion_are_untouched(self):
        self.write("riders.txt", TEN_RIDERS)
        m = self.mission([
            {"tier": "verify", "check": "ten lines",
             "probe": {"kind": "line_count", "path": "riders.txt",
                       "count": 10}}])
        met, results = mission_engine.evaluate_done_when(
            m, "", probe_root=self.root)
        self.assertTrue(met)
        self.assertTrue(mission_engine.completion_summary(m, results))

    def test_the_artifact_lane_bounds_still_hold(self):
        self.assertEqual(shadow_evidence.MAX_FILES, 8)
        self.assertEqual(shadow_evidence.MAX_FILE_BYTES, 32 * 1024)


# ------------------------------- the contract the worker actually gets ---
class TheWorkerGetsTheWholeContract(Fixture):
    """founder, 2026-09-21: "the worker must receive the canonical,
    actionable done_when contract before execution ... the worker must never
    be expected to satisfy acceptance criteria that were hidden from it."

    THE BUG D-SH-1 INTRODUCED. `_worker_checks_block` listed `verify` rows
    only. That was right while `verify` was the ordinary tier; D-SH-1 moved
    FALLBACK_TIER to `judge`, so the ordinary row stopped being listed and
    the worker started being graded on criteria it had never seen.
    """

    def block(self, rows):
        import app
        return app._worker_checks_block({"done_when": rows})

    ROWS = [
        {"tier": "verify", "check": "the file holds 10 lines",
         "probe": {"kind": "line_count", "path": "riders.txt", "count": 10}},
        {"tier": "judge", "check": "each entry is a real premier-class rider"},
        {"tier": "founder_confirm", "check": RANKING_ASK},
        {"tier": "contains_artifact", "check": "RIDERS-OK"},
    ]

    def test_every_criterion_reaches_the_worker(self):
        block = self.block(self.ROWS)
        for row in self.ROWS:
            self.assertIn(row["check"], block,
                          "%r was hidden from the worker" % row["check"])

    def test_the_judge_row_is_the_regression(self):
        """The specific row D-SH-1 made ordinary and this block dropped."""
        block = self.block([{"tier": "judge",
                             "check": "each entry is a real rider"}])
        self.assertIn("each entry is a real rider", block)

    def test_the_mechanism_is_never_exposed(self):
        """Shadow may DERIVE probes and confirmation decisions from the
        contract; it does not owe the worker those mechanisms -- and showing
        them is what would let a worker write to the measurement."""
        block = self.block(self.ROWS)
        # probe internals: plain substrings, none of which are English
        for leak in ("line_count", "riders.txt", "probe", "founder_confirm",
                     "contains_artifact"):
            self.assertNotIn(leak, block, "%r leaked the mechanism" % leak)
        # tier NAMES, as whole words. Word-boundaries because the preamble
        # says the work is "judged" against the contract, which is the
        # ordinary English verb and not the name of a lane -- a bare
        # substring test reads one as the other and fails an honest string.
        for leak in ("judge", "verify", "tier"):
            self.assertIsNone(re.search(r"\b%s\b" % leak, block),
                              "%r leaked the mechanism as a tier name" % leak)

    def test_only_verify_rows_get_the_claim_convention(self):
        """The claim convention stays exactly as narrow as it was. A
        `contains_artifact` row is `check in transcript`, so inviting a
        verbatim copy would make it self-satisfying (m-245777cf1467)."""
        block = self.block(self.ROWS)
        self.assertIn("DONE-CHECK: the file holds 10 lines", block)
        self.assertNotIn("DONE-CHECK: RIDERS-OK", block)
        self.assertNotIn("DONE-CHECK: %s" % RANKING_ASK, block)
        self.assertNotIn("DONE-CHECK: each entry is a real premier-class "
                         "rider", block)

    def test_a_contract_with_no_claimable_row_still_ships(self):
        block = self.block([{"tier": "judge", "check": "it reads well"}])
        self.assertIn("it reads well", block)
        self.assertNotIn("DONE-CHECK", block)

    def test_no_checks_means_no_block(self):
        self.assertEqual(self.block([]), "")

    def test_shadow_verifies_against_the_same_contract(self):
        """SYMMETRY: the strings the worker is given are the strings the
        engine evaluates. Not a copy, not a paraphrase -- the same rows."""
        import app
        rows = [dict(r) for r in self.ROWS]
        block = app._worker_checks_block({"done_when": rows})
        _, results = mission_engine.evaluate_done_when(
            {"done_when": rows}, "", probe_root=self.root)
        for r in results:
            self.assertIn(r["check"], block,
                          "the engine evaluates a criterion the worker was "
                          "not given")


# ------------------------------------- the packet changes NO authority ---
class TheConfirmationChangesNoAuthority(Fixture):
    """founder, 2026-09-21: "do not change worker access/permissions merely
    because a founder-facing confirmation is being displayed"."""

    #: every field that governs what the worker may do. Displaying evidence
    #: must not touch one of them.
    AUTHORITY = ("autonomy", "permission_mode", "read_only", "never_say",
                 "approval", "pending_say", "approved_say", "floors",
                 "template", "target_session", "target_mode")

    def test_stamping_a_packet_touches_no_authority_field(self):
        self.write("riders.txt", TEN_RIDERS)
        store = mission_engine.MissionStore()
        m = store.create("ten riders", "research", done_when=[
            {"tier": "verify", "check": "ten lines",
             "probe": {"kind": "line_count", "path": "riders.txt",
                       "count": 10}},
            {"tier": "founder_confirm", "check": RANKING_ASK}])
        store.transition(m["id"], "brief_confirm", "briefed")
        store.transition(m["id"], "running", "go")
        before = {k: store.load(m["id"]).get(k) for k in self.AUTHORITY}
        eng = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)
        eng.probe_root, eng.store = self.root, store
        eng._await_confirmation(m["id"])
        after = {k: store.load(m["id"]).get(k) for k in self.AUTHORITY}
        self.assertEqual(before, after,
                         "showing the founder evidence must not widen or "
                         "narrow what the worker may do")

    def test_the_packet_carries_no_authority_of_its_own(self):
        """It is evidence. It has no field a reader could mistake for a
        permission, an approval or an instruction."""
        self.write("riders.txt", TEN_RIDERS)
        p = shadow_decision.packet_for(self.mission([
            {"tier": "founder_confirm", "check": RANKING_ASK},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "riders.txt"}},
        ]), self.root)
        # `version` ADDED 2026-09-21: the packet names the revision it
        # speaks for, so confirm_check can refuse a sign-off given for a
        # question the founder has since replaced. An integer, not a
        # capability -- the screen below still holds.
        self.assertEqual(sorted(p), ["artifacts", "asks", "at",
                                     "established", "missing", "version"])
        for banned in ("instruction", "approve", "permission", "autonomy",
                       "say", "command", "argv"):
            self.assertNotIn(banned, repr(sorted(p)))


# ------------------------------- what a finished task says it produced ---
class CompletionNamesTheResult(Fixture):
    """founder, 2026-09-21: a DONE surface should say "what was completed"
    and "the resulting artifact/file if applicable" -- not a check count."""

    def test_a_named_path_wins_over_discovery(self):
        """THE NOISE THIS REMOVES, measured on this repo: discovery returned
        the mission's own file PLUS `.claude/depth`, `.claude/build-layer`
        and two unrelated documents. A founder reading "what did this
        produce" is being told the truth and none of it is the answer."""
        self.repo()
        self.write("riders.txt", TEN_RIDERS)
        self.write("unrelated.md", "something else entirely\n")
        m = self.mission([
            {"tier": "verify", "check": "the file exists",
             "probe": {"kind": "file_exists", "path": "riders.txt"}},
            {"tier": "founder_confirm", "check": RANKING_ASK}])
        got = mission_engine.completion_artifacts(m, self.root)
        self.assertEqual(got, ["riders.txt"])
        self.assertNotIn("unrelated.md", got)

    def test_there_is_NO_discovery_fallback(self):
        """ALSO INVERTED (founder, 2026-09-21). A completion surface that
        fell through to git-status discovery listed another mission's files
        as this one's result. A mission that named no artifact reports
        none -- which is true, and the alternative is a confident lie."""
        self.repo()
        self.write("riders.txt", TEN_RIDERS)
        m = self.mission([{"tier": "founder_confirm", "check": RANKING_ASK}])
        self.assertEqual(mission_engine.completion_artifacts(m, self.root), [])

    def test_the_count_is_still_on_the_record(self):
        """INTERNAL VERIFICATION IS NOT DISCARDED -- it stops being what the
        founder reads first. The server still stamps every verdict."""
        self.write("riders.txt", TEN_RIDERS)
        m = self.mission([
            {"tier": "verify", "check": "ten lines",
             "probe": {"kind": "line_count", "path": "riders.txt",
                       "count": 10}}])
        met, results = mission_engine.evaluate_done_when(
            m, "", probe_root=self.root)
        c = mission_engine.completion_summary(m, results)
        self.assertTrue(met)
        self.assertEqual(c["headline"], "1 of 1 checks passed")
        self.assertEqual(c["checks_met"], 1)
        self.assertEqual(len(c["checks"]), 1)
        self.assertIn("1 of 1 checks passed",
                      mission_engine.completion_text(c))

    def test_completion_artifacts_never_raises(self):
        self.assertEqual(
            mission_engine.completion_artifacts({}, "/nope/nowhere"), [])


if __name__ == "__main__":
    unittest.main()
