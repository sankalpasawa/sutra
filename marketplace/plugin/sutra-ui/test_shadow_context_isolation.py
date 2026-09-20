#!/usr/bin/env python3
"""ONE MISSION'S WORK NEVER BECOMES ANOTHER'S CONTEXT (founder, 2026-09-21).

THE FAILURE, observed verbatim on the founder's install. A mission whose
objective was "Plan a personal trip for me to Europe for 10 days" produced
context reading:

    "A prior plan (europe-trip-plan.md), same directory already exists..."
    "The one real signal about this founder in the workspace is MotoGP --
     two artifacts from this week..."

THE SOURCE, and it is NOT the artifact-discovery leak fixed the same day.
`shadow_session.standing_context()` ended with:

    acts = shadow_ledger.read("actions", 10)
    out += "RECENT SHADOW ACTIONS ..." + lines

`read()` returns the last ten rows written by ANY mission. That block was
appended to the boot context of EVERY task chat -- and a task chat is the
process that WRITES THE WORKER'S BRIEF. So the Europe mission booted holding
the MotoGP mission's judge verdicts, its criteria and the artifacts they
named, and then wrote about them.

Measured on the live ledger before the fix: ten rows spanning four different
missions, including `criteria` rows quoting artifact filenames and `judge`
rows quoting evidence.

WHY THE owned_artifacts FIX DID NOT COVER IT. That fix changed artifact
DISCOVERY -- git status to mission ownership -- on the filesystem. This is a
different data source entirely: the action LEDGER, which is global by design
and was being read unscoped. Same class of bug, different pipe.

THE BOUNDARY, and the two halves are scoped differently on purpose:

  PERSISTENT FOUNDER KNOWLEDGE crosses missions. Standing instructions and
  the founder's own memory/behaves boxes are deliberately stored, are about
  the FOUNDER rather than any one task, and are supposed to travel.

  MISSION CONTEXT does not. A judge verdict, a criterion, an artifact name,
  a worker report: each belongs to the mission that produced it and becomes
  global for nobody merely by being recent.

The founder's own line: "MotoGP is something the founder follows" may be
founder knowledge if it was deliberately stored; "motogp-top-10-news.md
exists" is mission artifact context and stays with its mission.

NO STRING FILTER ANYWHERE IN THIS FIX. Nothing greps for "MotoGP", nothing
keeps a topic or filename blacklist. The scoped reader simply cannot return
another mission's rows.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_context_isolation.py
"""
import os
import tempfile
import unittest

# the live home is not a test fixture -- see tests-never-touch-live-stores
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-ctx-test-")

import mission_engine                                          # noqa: E402
import shadow_ledger                                           # noqa: E402
import shadow_session                                          # noqa: E402

MOTO = "m-motogp"
EURO = "m-europe"
THIRD = "m-dashboard"

#: What a real MotoGP mission writes into the action ledger -- these are the
#: shapes seen on the live install, not invented ones.
MOTO_ROWS = [
    ("criteria", "Shadow wrote 5 check(s): motogp-top-10-news.md exists in "
                 "the working directory"),
    ("judge", "#1 met: the file lists ten riders including Marc Marquez"),
    ("result", "3 of 3 checks passed -- created motogp-top-10-news.md"),
    ("say", "worker turn 1: wrote marc-marquez.txt with the rider summary"),
]
EURO_ROWS = [
    ("criteria", "Shadow wrote 5 check(s): europe-10-day-trip.md exists in "
                 "the working directory"),
    ("judge", "#1 met: the itinerary covers Rome, Florence and Venice"),
]

MOTO_WORDS = ("motogp", "marquez", "marc-marquez.txt",
              "motogp-top-10-news.md")
EURO_WORDS = ("europe-10-day-trip.md", "florence", "venice")


def _seed(mission_id, rows):
    for kind, summary in rows:
        shadow_ledger.append("actions", {"mission_id": mission_id,
                                         "kind": kind, "summary": summary})


class Base(unittest.TestCase):

    def setUp(self):
        # a fresh ledger per test: these assertions are about WHAT a read
        # returns, so a shared log would make them order-dependent
        os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(
            prefix="shadow-ctx-test-")

    def ctx(self, mission_id):
        return shadow_session.standing_context(mission_id).lower()

    def hits(self, blob, words):
        return [w for w in words if w in blob]


# 1-3 ── the reported case, and its mirror ───────────────────────────────
class MissionsDoNotSeeEachOther(Base):

    def test_1_europe_after_motogp_sees_no_motogp(self):
        """THE CRITICAL REPRODUCTION. Mission A writes a MotoGP file, then
        Mission B is the Europe trip, same directory, same ledger."""
        _seed(MOTO, MOTO_ROWS)
        _seed(EURO, EURO_ROWS)
        blob = self.ctx(EURO)
        self.assertEqual(self.hits(blob, MOTO_WORDS), [],
                         "MotoGP context reached the Europe mission")

    def test_2_motogp_after_europe_sees_no_europe(self):
        """The mirror, because a fix that only works in one order is an
        accident of ordering."""
        _seed(EURO, EURO_ROWS)
        _seed(MOTO, MOTO_ROWS)
        blob = self.ctx(MOTO)
        self.assertEqual(self.hits(blob, EURO_WORDS), [],
                         "Europe context reached the MotoGP mission")

    def test_3_three_missions_each_see_only_their_own(self):
        _seed(MOTO, MOTO_ROWS)
        _seed(EURO, EURO_ROWS)
        _seed(THIRD, [("judge", "#0 met: project-dashboard.html has 5 cards")])
        self.assertEqual(self.hits(self.ctx(EURO), MOTO_WORDS), [])
        self.assertNotIn("project-dashboard", self.ctx(EURO))
        self.assertEqual(self.hits(self.ctx(MOTO), EURO_WORDS), [])
        self.assertNotIn("project-dashboard", self.ctx(MOTO))
        self.assertEqual(self.hits(self.ctx(THIRD), MOTO_WORDS), [])
        self.assertEqual(self.hits(self.ctx(THIRD), EURO_WORDS), [])

    def test_a_mission_DOES_see_its_own_actions(self):
        """The scope must not be a mute: this block exists so Shadow can
        ground an undo request, and a mission's own history still reaches
        it."""
        _seed(MOTO, MOTO_ROWS)
        blob = self.ctx(MOTO)
        self.assertIn("marc-marquez.txt", blob)
        self.assertIn("recent shadow actions", blob)


# 4-7 ── the tempting cases ──────────────────────────────────────────────
class RelevanceIsNotOwnership(Base):

    def test_4_a_relevant_looking_FILENAME_is_still_not_injected(self):
        _seed(MOTO, [("result", "created europe-trip-plan.md as a side note")])
        self.assertNotIn("europe-trip-plan", self.ctx(EURO),
                         "a filename that looks like this mission's is "
                         "still another mission's row")

    def test_5_relevant_looking_CONTENT_is_still_not_injected(self):
        _seed(MOTO, [("judge", "#2 met: notes mention Rome, Florence and a "
                               "10 day itinerary")])
        blob = self.ctx(EURO)
        for word in ("rome", "florence", "itinerary"):
            self.assertNotIn(word, blob,
                             "content similarity crossed the boundary")

    def test_6_a_mission_finished_one_second_ago_is_still_not_injected(self):
        """Recency is not ownership. The previous row is the MOST likely to
        look relevant and is exactly as out of scope as an old one."""
        _seed(MOTO, MOTO_ROWS)
        _seed(EURO, [("spawn", "delegate session started")])
        self.assertEqual(self.hits(self.ctx(EURO), MOTO_WORDS), [])

    def test_7_a_mission_still_RUNNING_is_still_not_injected(self):
        _seed(MOTO, [("say", "worker turn 3: still writing "
                             "motogp-top-10-news.md")])
        self.assertEqual(self.hits(self.ctx(EURO), MOTO_WORDS), [])

    def test_rows_with_no_mission_id_belong_to_nobody(self):
        """A boot row or an unattached spawn is not "not another mission's",
        it is simply not this mission's -- admitting it is how a boundary
        erodes."""
        shadow_ledger.append("actions", {"kind": "boot",
                                         "summary": "shadow boot: recovery"})
        self.assertNotIn("recovery", self.ctx(EURO))
        self.assertEqual(
            shadow_ledger.read_for_mission("actions", None, 10), [])
        self.assertEqual(
            shadow_ledger.read_for_mission("actions", "", 10), [])


# 8-9 + 12 ── founder knowledge is not mission context ───────────────────
class PersistentFounderKnowledgeStillCrosses(Base):
    """founder: "Do not delete legitimate persistent founder knowledge."

    The two halves of standing_context are scoped differently and that is
    the whole design -- a deliberately stored fact about the FOUNDER travels;
    a generated artifact from a mission does not."""

    def test_8_a_stored_founder_preference_reaches_a_new_mission(self):
        mission_engine.set_memory("I follow MotoGP and support Ducati")
        try:
            blob = self.ctx(EURO)
            self.assertIn("ducati", blob,
                          "deliberately stored founder knowledge must still "
                          "cross missions")
        finally:
            mission_engine.set_memory("")

    def test_9_an_artifact_MENTIONING_a_preference_does_not_leak(self):
        """The distinction the founder drew, as a test. The same sentence is
        founder knowledge when STORED and mission context when it is merely
        something a mission's artifact happened to contain."""
        _seed(MOTO, [("result", "wrote a file noting the founder follows "
                                "MotoGP and supports Ducati")])
        blob = self.ctx(EURO)
        self.assertNotIn("ducati", blob,
                         "an artifact's contents became founder knowledge "
                         "without anyone storing it")
        self.assertNotIn("motogp", blob)

    def test_12_a_mission_row_can_never_promote_itself_to_global(self):
        """There is no path from the action ledger into the founder's boxes.
        `set_memory` is the only writer, and nothing in the mission loop
        calls it."""
        _seed(MOTO, MOTO_ROWS)
        self.assertNotIn("motogp", (mission_engine.memory() or "").lower())
        self.assertNotIn("motogp",
                         (mission_engine.carry_block() or "").lower())


# 10-11 ── the same boundary everywhere ──────────────────────────────────
class OneBoundaryForEveryConsumer(Base):

    def test_10_the_task_chat_boot_passes_its_own_mission_id(self):
        """The worker's brief is written BY the task chat, so the task
        chat's boot scope IS the worker's scope. Asserted against the
        source, because this is the one line that binds them."""
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "shadow_task_chat.py")) as fh:
            src = fh.read()
        self.assertIn('standing_context(mission.get("id"))', src,
                      "a task chat must boot scoped to its own mission")
        self.assertNotIn("standing_context()", src,
                         "an unscoped boot is the leak")

    def test_11_one_missions_rows_never_reach_another_reader(self):
        """The ledger is global BY DESIGN -- it is one audit log. What
        changed is that a mission-scoped READER exists and the context path
        uses it."""
        _seed(MOTO, MOTO_ROWS)
        _seed(EURO, EURO_ROWS)
        moto = shadow_ledger.read_for_mission("actions", MOTO, 50)
        euro = shadow_ledger.read_for_mission("actions", EURO, 50)
        self.assertTrue(moto and euro)
        self.assertTrue(all(r["mission_id"] == MOTO for r in moto))
        self.assertTrue(all(r["mission_id"] == EURO for r in euro))
        # ...and the unscoped read still sees everything, for the audit
        every = shadow_ledger.read("actions", 50)
        self.assertGreaterEqual(len(every), len(moto) + len(euro))

    def test_the_now_chat_keeps_its_unscoped_overview(self):
        """DELIBERATE ASYMMETRY. The Now chat is the founder's own overview,
        does no work, and its context reaches no worker -- so its history is
        the founder's own. Pinned so the asymmetry is a decision rather than
        a gap somebody closes by accident."""
        _seed(MOTO, MOTO_ROWS)
        self.assertIn("motogp", shadow_session.standing_context().lower())


# ── no blacklist anywhere ───────────────────────────────────────────────
class TheFixIsAScopeNotAFilter(Base):

    def test_no_topic_or_filename_filter_exists(self):
        """founder: "DO NOT fix this with a string filter." Asserted against
        the source of both changed functions."""
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("shadow_session.py", "shadow_ledger.py"):
            with open(os.path.join(here, name)) as fh:
                src = fh.read().lower()
            for banned in ('"motogp"', "'motogp'", "blacklist", "denylist"):
                self.assertNotIn(banned, src,
                                 "%s carries a %s filter" % (name, banned))


if __name__ == "__main__":
    unittest.main()
