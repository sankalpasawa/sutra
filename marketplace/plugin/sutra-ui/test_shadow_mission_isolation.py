#!/usr/bin/env python3
"""NO CROSS-MISSION CONTEXT LEAKAGE (founder, 2026-09-21).

THE FAILURE. A mission whose objective was "Plan a personal trip for me to
Europe for 10 days" showed, on its own decision surface, `marc-marquez.txt`,
`motogp-top-10-news.md`, `weight-loss-plan.html` and several of Shadow's own
source files. Reproduced exactly before the fix: TWELVE candidate paths for a
mission whose only criterion was about an itinerary.

THE ROOT CAUSE, and it was mine. The artifact lane added on 2026-09-20 let the
judge read a newly created file by asking git for untracked paths. That solved
the blindness it was aimed at and, in the same move, made every uncommitted
file in the workdir eligible for every mission. In a shared workdir -- which
is the normal case, because every mission runs in the founder's repo -- that
is every file every previous mission ever produced.

    git status answers "what is not committed".
    It says NOTHING about which mission produced a file.
    The two coincide only when exactly one mission has ever run there.

I saw the symptom a turn earlier, when `completion_artifacts` returned
`['motogp-top-10-news.md', '.claude/build-layer', '.claude/depth',
'europe-10-day-trip.md', ...]`, fixed it for the COMPLETION surface only, and
reasoned that the same source was "harmless context" for the decision packet
and the judge. It was not harmless. It was this.

THE INVARIANT THIS FILE PINS: a mission may consume only what it OWNS --
paths its own probes name, or paths explicitly recorded on its record
(shadow_paths.owned_artifacts). Discovery is not ownership. A file that merely
exists near the work is not evidence about the work.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_mission_isolation.py
"""
import os
import subprocess
import tempfile
import unittest

# the live home is not a test fixture -- see tests-never-touch-live-stores
os.environ["SUTRA_SHADOW_HOME"] = tempfile.mkdtemp(prefix="shadow-iso-test-")

import mission_engine                                          # noqa: E402
import shadow_decision                                         # noqa: E402
import shadow_judge                                            # noqa: E402
import shadow_paths                                            # noqa: E402

MOTOGP = "Valentino Rossi, Giacomo Agostini, Marc Marquez\n"
EUROPE = "Day 1-3 Rome. Day 4-6 Florence. Day 7-10 Venice.\n"

EUROPE_ASK = "does this itinerary match the trip you want"


class Shared(unittest.TestCase):
    """ONE PHYSICAL WORKDIR, MANY MISSIONS -- the shape the bug lived in."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def write(self, name, text):
        path = os.path.join(self.root, name)
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
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

    def mission(self, mid, objective, checks):
        return {"id": mid, "objective": objective, "done_when": checks}

    def europe(self, owned=True):
        checks = [{"tier": "founder_confirm", "check": EUROPE_ASK}]
        if owned:
            checks.append({"tier": "verify", "check": "the plan exists",
                           "probe": {"kind": "file_exists",
                                     "path": "europe.md"}})
        return self.mission("m-europe", "Plan a trip to Europe for 10 days",
                            checks)

    def leaked(self, blob):
        """Anything from a mission that is not this one."""
        low = repr(blob).lower()
        return [w for w in ("motogp", "marquez", "rossi", "agostini",
                            "weight-loss", "dashboard")
                if w in low]


# 1 / 5 / 9 / 12 ── files from other missions ────────────────────────────
class FileIsolation(Shared):

    def test_1_europe_packet_contains_no_motogp(self):
        """THE REPORTED BUG, as a test."""
        self.repo()
        self.write("motogp-top-10-news.md", MOTOGP)
        self.write("marc-marquez.txt", MOTOGP)
        self.write("weight-loss-plan.html", "<html>diet</html>")
        self.write("europe.md", EUROPE)
        p = shadow_decision.packet_for(self.europe(), self.root)
        self.assertEqual(self.leaked(p), [],
                         "another mission's files reached this packet")
        self.assertIn("Rome", p["artifacts"][0]["text"],
                      "...and its own artifact is still there")

    def test_5_git_status_admits_nothing(self):
        """founder: "Do not use git status as a mission-scoped artifact
        source." Five untracked files from earlier missions, none owned."""
        self.repo()
        for n in ("motogp-top-10-news.md", "marc-marquez.txt",
                  "weight-loss-plan.html", "project-dashboard.html",
                  "riders.txt"):
            self.write(n, MOTOGP)
        m = self.mission("m-e", "Plan a trip to Europe",
                         [{"tier": "founder_confirm", "check": EUROPE_ASK}])
        self.assertEqual(shadow_decision.candidate_paths(m, self.root), [])
        self.assertEqual(shadow_decision.packet_for(m, self.root)["artifacts"],
                         [])

    def test_12_legacy_unowned_files_are_ignored(self):
        self.repo()
        self.write("old-notes.md", "something from months ago\n")
        m = self.mission("m-new", "a brand new task",
                         [{"tier": "founder_confirm", "check": "ok?"}])
        self.assertEqual(shadow_decision.candidate_paths(m, self.root), [])

    def test_9_filename_similarity_cannot_cross_the_boundary(self):
        """No fuzzy matching anywhere: ownership is an exact list."""
        self.repo()
        self.write("europe.md", EUROPE)
        self.write("europe-OLD.md", MOTOGP)
        self.write("europe-backup.md", MOTOGP)
        p = shadow_decision.packet_for(self.europe(), self.root)
        self.assertEqual([a["path"] for a in p["artifacts"]], ["europe.md"])


# 3 / 4 / 10 / 11 ── many missions, one directory ────────────────────────
class SharedWorkdir(Shared):

    def test_3_each_mission_sees_only_its_own(self):
        self.repo()
        self.write("motogp.md", MOTOGP)
        self.write("europe.md", EUROPE)
        a = self.mission("m-a", "motogp list", [
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "motogp.md"}}])
        b = self.mission("m-b", "europe trip", [
            {"tier": "verify", "check": "y",
             "probe": {"kind": "file_exists", "path": "europe.md"}}])
        self.assertEqual(shadow_decision.candidate_paths(a, self.root),
                         ["motogp.md"])
        self.assertEqual(shadow_decision.candidate_paths(b, self.root),
                         ["europe.md"])

    def test_4_five_missions_one_directory(self):
        self.repo()
        for i in range(1, 6):
            self.write("m%d.md" % i, "mission %d output\n" % i)
        fifth = self.mission("m-5", "the fifth task", [
            {"tier": "founder_confirm", "check": "ok?"},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "m5.md"}}])
        p = shadow_decision.packet_for(fifth, self.root)
        self.assertEqual([a["path"] for a in p["artifacts"]], ["m5.md"])
        for other in ("mission 1", "mission 2", "mission 3", "mission 4"):
            self.assertNotIn(other, repr(p))

    def test_10_sequential_missions_stay_isolated(self):
        """MotoGP -> Europe -> MotoGP -> Europe, in one directory."""
        self.repo()
        self.write("motogp.md", MOTOGP)
        self.write("europe.md", EUROPE)
        for i in range(2):
            moto = self.mission("m-moto-%d" % i, "motogp", [
                {"tier": "verify", "check": "x",
                 "probe": {"kind": "file_exists", "path": "motogp.md"}}])
            euro = self.mission("m-euro-%d" % i, "europe", [
                {"tier": "verify", "check": "y",
                 "probe": {"kind": "file_exists", "path": "europe.md"}}])
            self.assertEqual(shadow_decision.candidate_paths(moto, self.root),
                             ["motogp.md"])
            self.assertEqual(shadow_decision.candidate_paths(euro, self.root),
                             ["europe.md"])

    def test_11_overlapping_missions_cannot_see_each_other(self):
        self.repo()
        self.write("a.md", "alpha output\n")
        self.write("b.md", "beta output\n")
        a = self.mission("m-a", "alpha", [
            {"tier": "founder_confirm", "check": "alpha ok?"},
            {"tier": "verify", "check": "x",
             "probe": {"kind": "file_exists", "path": "a.md"}}])
        b = self.mission("m-b", "beta", [
            {"tier": "founder_confirm", "check": "beta ok?"},
            {"tier": "verify", "check": "y",
             "probe": {"kind": "file_exists", "path": "b.md"}}])
        pa = shadow_decision.packet_for(a, self.root)
        pb = shadow_decision.packet_for(b, self.root)
        self.assertIn("alpha output", pa["artifacts"][0]["text"])
        self.assertNotIn("beta output", repr(pa))
        self.assertIn("beta output", pb["artifacts"][0]["text"])
        self.assertNotIn("alpha output", repr(pb))


# ── the judge is scoped too ─────────────────────────────────────────────
class JudgeEvidenceIsScoped(Shared):

    def test_the_judge_reads_only_what_it_is_given(self):
        """`evidence_for` used to add untracked paths ITSELF, so a judge
        settling one mission's criterion could read another's artifacts."""
        self.repo()
        self.write("motogp.md", MOTOGP)
        self.write("europe.md", EUROPE)
        blob = shadow_judge.evidence_for(self.root, None, ["europe.md"])
        self.assertIn("Rome", blob)
        self.assertNotIn("Valentino Rossi", blob)

    def test_the_status_listing_survives_but_admits_no_content(self):
        """"these files changed" is a genuine fact about the tree; it is the
        CONTENT that had to stop leaking."""
        self.repo()
        self.write("motogp.md", MOTOGP)
        blob = shadow_judge.evidence_for(self.root)
        self.assertIn("?? motogp.md", blob, "the listing is still shown")
        self.assertNotIn("Valentino Rossi", blob,
                         "but nothing unowned is read")

    def test_the_engine_hands_the_judge_only_owned_paths(self):
        self.repo()
        self.write("motogp.md", MOTOGP)
        self.write("europe.md", EUROPE)
        eng = mission_engine.MissionEngine.__new__(
            mission_engine.MissionEngine)
        eng.probe_root = self.root
        blob = eng._judge_evidence(self.mission("m-e", "europe", [
            {"tier": "judge", "check": "the plan is coherent",
             "probes": [{"kind": "file_exists", "path": "europe.md"}]}]))
        self.assertIn("Rome", blob)
        self.assertNotIn("Valentino Rossi", blob)


# ── ownership is the one source ─────────────────────────────────────────
class OwnershipIsExplicit(Shared):

    def test_a_probe_path_owns_the_file(self):
        m = self.mission("m", "x", [
            {"tier": "verify", "check": "c",
             "probe": {"kind": "file_exists", "path": "europe.md"}}])
        self.assertEqual(shadow_paths.owned_artifacts(m), ["europe.md"])

    def test_an_explicit_record_list_owns_the_file(self):
        m = self.mission("m", "x", [])
        m["artifacts"] = ["europe.md", "itinerary.md"]
        self.assertEqual(shadow_paths.owned_artifacts(m),
                         ["europe.md", "itinerary.md"])

    def test_nothing_else_owns_anything(self):
        self.assertEqual(shadow_paths.owned_artifacts({}), [])
        self.assertEqual(shadow_paths.owned_artifacts(None), [])
        self.assertEqual(shadow_paths.owned_artifacts(
            self.mission("m", "europe trip please", [])), [])

    def test_ownership_never_walks_the_tree(self):
        """No glob, no walk, no mtime, no similarity -- asserted against the
        SOURCE, because the next leak will arrive as a convenience."""
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "shadow_paths.py")) as fh:
            src = fh.read()
        tail = src[src.index("def owned_artifacts"):]
        # the CODE, not the docstring -- which names each banned mechanism
        # in order to say it is absent, and would match every pattern below
        tail = tail[tail.index('"""', tail.index('"""') + 3) + 3:]
        for banned in ("glob", "walk", "listdir", "git", "getmtime",
                       "scandir"):
            self.assertNotIn(banned, tail,
                             "%r would make discovery into ownership"
                             % banned)


# 7 ── the surfaces agree ────────────────────────────────────────────────
class TheSurfacesAgree(Shared):

    def test_7_the_confirmation_packet_is_europe_only(self):
        self.repo()
        self.write("motogp-top-10-news.md", MOTOGP)
        self.write("europe.md", EUROPE)
        p = shadow_decision.packet_for(self.europe(), self.root)
        self.assertEqual([a["check"] for a in p["asks"]], [EUROPE_ASK])
        self.assertEqual(self.leaked(p), [])
        self.assertIn("Florence", p["artifacts"][0]["text"],
                      "enough to answer without opening another chat")

    def test_completion_names_only_owned_artifacts(self):
        self.repo()
        self.write("motogp-top-10-news.md", MOTOGP)
        self.write("europe.md", EUROPE)
        got = mission_engine.completion_artifacts(self.europe(), self.root)
        self.assertEqual(got, ["europe.md"])

    def test_a_mission_owning_nothing_says_so_rather_than_borrowing(self):
        self.repo()
        self.write("motogp-top-10-news.md", MOTOGP)
        p = shadow_decision.packet_for(self.europe(owned=False), self.root)
        self.assertEqual(p["artifacts"], [])
        self.assertIn("could not gather", p["missing"])
        self.assertEqual(self.leaked(p), [])


if __name__ == "__main__":
    unittest.main()
