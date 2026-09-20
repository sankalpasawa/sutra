#!/usr/bin/env python3
"""WORKER CLAIM != DONE.

Every tier Shadow had was attestation or judgement. `_shadow_verifier` makes
zero filesystem calls, so "a file exists containing exactly X" was settled by
the worker TYPING A SENTENCE -- and the previous fix (handing the worker the
exact check strings so its claim would match) made an accidental false claim
easier, not harder.

A probe is the engine looking for itself. These tests pin the boundary from
both sides:

  * a perfect DONE-CHECK claim over a WRONG file is UNMET
  * a probe that passes settles the check even when the worker never claimed
    it at all

...and they pin the confinement that makes reading the founder's real
filesystem safe: traversal, absolute escape and symlink escape are refused,
and a refusal is `unmet`, never a failed mission.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_probe.py
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

import app
import mission_engine
import providers
import shadow_egress
import shadow_probe
import shadow_runner
from mission_engine import (MissionEngine, MissionStore, evaluate_done_when,
                            validate_decision, validate_done_when)


def _probe(**kw):
    out = {"kind": "file_equals", "path": "a.txt", "text": "x"}
    out.update(kw)
    return out


class Root(unittest.TestCase):
    """A workdir, and an OUTSIDE it must never reach."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "workdir")
        self.outside = os.path.join(self.tmp.name, "outside")
        os.makedirs(self.root)
        os.makedirs(self.outside)
        Path(self.outside, "secret.txt").write_text("secret")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = Path(self.root, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p


# ---------------------------------------------------------------- the kinds

class TestFileExists(Root):
    def test_01_passes_for_an_existing_file(self):
        self.write("made.txt", "anything")
        r = shadow_probe.run({"kind": "file_exists", "path": "made.txt"},
                             self.root)
        self.assertTrue(r.met, r.reason)

    def test_02_fails_for_a_missing_file(self):
        r = shadow_probe.run({"kind": "file_exists", "path": "never.txt"},
                             self.root)
        self.assertFalse(r.met)
        self.assertEqual(r.reason, "does not exist")

    def test_03_a_subdirectory_path_is_ordinary(self):
        self.write("sub/deep.txt", "hi")
        self.assertTrue(shadow_probe.met(
            {"kind": "file_exists", "path": "sub/deep.txt"}, self.root))


class TestFileEquals(Root):
    def test_04_passes_for_exact_content(self):
        self.write("a.txt", "shadow-race-pass")
        self.assertTrue(shadow_probe.met(
            _probe(text="shadow-race-pass"), self.root))

    def test_05_trailing_newline_is_refused_unless_asked_for(self):
        self.write("a.txt", "shadow-race-pass\n")
        strict = _probe(text="shadow-race-pass")
        self.assertFalse(shadow_probe.met(strict, self.root),
                         "exactly X means exactly X by default")
        lenient = _probe(text="shadow-race-pass",
                         allow_trailing_newline=True)
        self.assertTrue(shadow_probe.met(lenient, self.root))

    def test_06_the_allowance_is_ONE_newline_not_any_whitespace(self):
        self.write("a.txt", "shadow-race-pass\n\n")
        self.assertFalse(shadow_probe.met(
            _probe(text="shadow-race-pass", allow_trailing_newline=True),
            self.root), "two newlines is not the editor's one")
        self.write("a.txt", "shadow-race-pass ")
        self.assertFalse(shadow_probe.met(
            _probe(text="shadow-race-pass", allow_trailing_newline=True),
            self.root), "a trailing space is not a newline")

    def test_07_crlf_counts_as_the_one_newline(self):
        self.write("a.txt", "shadow-race-pass\r\n")
        self.assertTrue(shadow_probe.met(
            _probe(text="shadow-race-pass", allow_trailing_newline=True),
            self.root))

    def test_08_fails_for_wrong_content(self):
        self.write("a.txt", "shadow-race-FAIL")
        r = shadow_probe.run(_probe(text="shadow-race-pass"), self.root)
        self.assertFalse(r.met)
        self.assertEqual(r.reason, "contents differ")

    def test_09_a_missing_file_is_unmet_not_an_error(self):
        r = shadow_probe.run(_probe(text="x", path="nope.txt"), self.root)
        self.assertFalse(r.met)
        self.assertEqual(r.reason, "no file there")

    def test_10_a_directory_is_not_a_file(self):
        os.makedirs(os.path.join(self.root, "d"))
        self.assertFalse(shadow_probe.met(_probe(path="d", text=""),
                                          self.root))

    def test_11_binary_is_unmet_never_a_crash(self):
        Path(self.root, "a.txt").write_bytes(b"\xff\xfe\x00bad")
        r = shadow_probe.run(_probe(text="x"), self.root)
        self.assertFalse(r.met)
        self.assertEqual(r.reason, "file is not utf-8 text")


# ---------------------------------------------------------------- the fence

class TestConfinement(Root):
    def test_12_traversal_out_of_the_workdir_is_rejected(self):
        """TWO FENCES, AND BOTH HOLD. A `..` segment never reaches disk
        (validate_probe screens it), and resolve refuses it anyway -- so a
        probe that got persisted before the screen existed, or one handed
        straight to the runner, is refused at the point of reading."""
        for path in ("../outside/secret.txt",
                     "sub/../../outside/secret.txt"):
            self.assertIsNone(shadow_probe.validate_probe(
                {"kind": "file_exists", "path": path}), path)
            self.assertFalse(shadow_probe.run(
                {"kind": "file_exists", "path": path}, self.root).met, path)
            with self.assertRaises(shadow_probe.ProbeUnsafe, msg=path):
                shadow_probe.resolve(self.root, path)

    def test_12b_a_backslash_traversal_is_screened_off_disk(self):
        """On posix `..\outside\secret.txt` is ONE filename, so resolve
        keeps it inside the root -- correctly, it names a file there. The
        screen refuses it anyway: a probe written that way is a model
        thinking in Windows paths, not a real file, and storing it would let
        the same string mean escape on a host where it is a separator."""
        path = "..\\outside\\secret.txt"
        self.assertIsNone(shadow_probe.validate_probe(
            {"kind": "file_exists", "path": path}))
        self.assertFalse(shadow_probe.run(
            {"kind": "file_exists", "path": path}, self.root).met)

    def test_13_an_absolute_path_outside_the_workdir_is_rejected(self):
        r = shadow_probe.run(
            {"kind": "file_exists",
             "path": os.path.join(self.outside, "secret.txt")}, self.root)
        self.assertFalse(r.met)
        self.assertIn("escapes the workdir", r.reason)

    def test_14_an_absolute_path_INSIDE_the_workdir_is_allowed(self):
        self.write("in.txt", "hi")
        self.assertTrue(shadow_probe.met(
            {"kind": "file_exists",
             "path": os.path.join(self.root, "in.txt")}, self.root))

    def test_15_a_symlink_pointing_out_of_the_workdir_is_rejected(self):
        os.symlink(os.path.join(self.outside, "secret.txt"),
                   os.path.join(self.root, "link.txt"))
        r = shadow_probe.run(
            {"kind": "file_equals", "path": "link.txt", "text": "secret"},
            self.root)
        self.assertFalse(r.met, "the link resolves outside; content is "
                                "irrelevant")
        self.assertIn("escapes the workdir", r.reason)

    def test_16_a_symlinked_PARENT_directory_is_rejected_too(self):
        os.symlink(self.outside, os.path.join(self.root, "away"))
        r = shadow_probe.run(
            {"kind": "file_exists", "path": "away/secret.txt"}, self.root)
        self.assertFalse(r.met)
        self.assertIn("escapes the workdir", r.reason)

    def test_17_a_symlink_INSIDE_the_workdir_still_works(self):
        self.write("real.txt", "here")
        os.symlink(os.path.join(self.root, "real.txt"),
                   os.path.join(self.root, "alias.txt"))
        self.assertTrue(shadow_probe.met(
            {"kind": "file_equals", "path": "alias.txt", "text": "here"},
            self.root))

    def test_18_no_workdir_is_unmet_with_a_reason_never_a_raise(self):
        for root in ("", "   ", os.path.join(self.tmp.name, "gone")):
            r = shadow_probe.run({"kind": "file_exists", "path": "a"}, root)
            self.assertFalse(r.met, repr(root))
            self.assertIn("probe refused", r.reason)


# ------------------------------------------------------------ what persists

class TestValidation(unittest.TestCase):
    def test_19_a_good_probe_normalises(self):
        self.assertEqual(
            shadow_probe.validate_probe(
                {"kind": "file_equals", "path": " a.txt ", "text": "x",
                 "junk": "dropped"}),
            {"kind": "file_equals", "path": "a.txt", "text": "x",
             "allow_trailing_newline": False})

    def test_20_unusable_probes_are_dropped_not_guessed(self):
        for raw in (None, "file_exists", {}, {"kind": "command_succeeds",
                                              "path": "a"},
                    {"kind": "file_exists"},
                    {"kind": "file_exists", "path": ""},
                    {"kind": "file_exists", "path": "~/repo/a.txt"},
                    {"kind": "file_exists", "path": "../a.txt"},
                    {"kind": "file_exists", "path": "a" * 600},
                    {"kind": "file_equals", "path": "a.txt"},
                    {"kind": "file_equals", "path": "a.txt", "text": 7},
                    {"kind": "file_equals", "path": "a.txt",
                     "text": "x" * 5000}):
            self.assertIsNone(shadow_probe.validate_probe(raw), repr(raw))

    def test_21_command_execution_is_argv_only_and_never_a_shell(self):
        """THE VOCABULARY GREW AGAIN, AND THIS TIME THE SAFETY STORY MOVED
        (founder D-SH-1, 2026-09-20). THIS TEST USED TO ASSERT THE OPPOSITE
        and the reversal is deliberate, so it is recorded rather than quietly
        rewritten.

        WHAT IT USED TO SAY: "command execution is not in the module at all",
        with `subprocess` on a banned-import list. That was right while the
        only thing it protected was a file read.

        WHY IT CHANGED: it was measured as the reason 9 of 9 live checks were
        founder_confirm. Every question a founder actually writes about
        working software -- "the tests pass", "nothing else broke" -- is a
        question about what happens when you RUN something, and none of them
        could be expressed. The founder was the test runner.

        WHY THE CHANGE ADDS NO CAPABILITY: the DELEGATE already runs in this
        same workdir at the founder's own permission mode and already runs
        anything it likes, every turn. A probe that runs pytest there adds no
        power to the system; it adds a reading of the result that the worker
        cannot author.

        WHAT STILL HOLDS, and this is what the assertions below pin:
          * ARGV, NEVER A SHELL STRING -- `shell=False`, a list, and a shell
            invoked with -c refused outright.
          * THE FLOORS APPLY -- screened through shadow_egress, the same
            table that screens a say.
          * NO NETWORK, NO os.system, NO os.popen, NO shlex. The module still
            never hands a string to anything that parses one.
        """
        self.assertEqual(shadow_probe.PROBE_KINDS,
                         ("file_exists", "file_equals", "line_count",
                          "lines_distinct", "file_contains",
                          "command_succeeds"))
        src = Path("shadow_probe.py").read_text()
        # THE ARGV PROPERTY, asserted against the source rather than argued.
        self.assertIn("shell=False", src)
        self.assertNotIn("shell=True", src)
        for banned in ("os.system", "os.popen", "shlex",
                       "urllib", "socket", "requests"):
            self.assertNotIn(banned, src, banned)
        # A SHELL HANDED -c IS REFUSED, so no model-authored string is ever
        # parsed by anything.
        for argv in (["bash", "-lc", "x"], ["sh", "-c", "x"],
                     ["python3", "-c", "x"]):
            self.assertIsNone(shadow_probe.validate_probe(
                {"kind": "command_succeeds", "argv": argv}), repr(argv))
        # THE FLOORS OUTRANK THE LANE.
        self.assertIn("floor_check", src)
        # NO KIND COMPILES A MODEL-AUTHORED PATTERN. `file_contains` is a
        # substring test precisely so a check's `text` never reaches a regex
        # engine; the module's own regexes are over paths and argv, never
        # over anything a check supplies as a pattern.
        self.assertIn("_SEGMENTS = re.compile", src)
        for never in ("file_matches", "regex", "pattern", "glob"):
            self.assertNotIn(never, [k for k in shadow_probe.PROBE_KINDS])

    def test_22_an_unusable_probe_is_unmet_never_a_pass(self):
        self.assertFalse(shadow_probe.met({"kind": "nope", "path": "a"}, "/"))
        self.assertFalse(shadow_probe.met(None, "/"))

    def test_23_a_verify_row_carries_its_probe_onto_the_record(self):
        rows = validate_done_when([
            {"tier": "verify", "check": "a.txt says hi",
             "probe": {"kind": "file_equals", "path": "a.txt", "text": "hi",
                       "allow_trailing_newline": True}}])
        self.assertEqual(rows[0]["probe"]["kind"], "file_equals")
        self.assertTrue(rows[0]["probe"]["allow_trailing_newline"])

    def test_24_founder_confirm_never_carries_one(self):
        """A filesystem fact cannot sign the founder's name."""
        rows = validate_done_when([
            {"tier": "founder_confirm", "check": "the copy reads well",
             "probe": {"kind": "file_exists", "path": "copy.txt"}}])
        self.assertEqual(rows[0]["tier"], "founder_confirm")
        self.assertNotIn("probe", rows[0], "probe = mechanically true; "
                                           "founder_confirm = signed off")

    def test_25_a_bad_probe_costs_the_probe_not_the_check(self):
        rows = validate_done_when([
            {"tier": "verify", "check": "a.txt exists",
             "probe": {"kind": "rm_rf", "path": "/"}}])
        self.assertEqual(len(rows), 1)
        self.assertNotIn("probe", rows[0],
                         "falls back to attestation -- harder, not easier")

    def test_26_a_decision_carries_probes_through_end_to_end(self):
        d = validate_decision({
            "action": "continue", "instruction": "make the file",
            "done_when": [{"tier": "verify", "check": "a.txt says hi",
                           "probe": {"kind": "file_equals", "path": "a.txt",
                                     "text": "hi"}}]})
        self.assertEqual(d["done_when"][0]["probe"]["text"], "hi")


class TestTheDoors(unittest.TestCase):
    """validate_done_when guards the DECIDER. Three other doors write rows
    raw -- the API create route, a `mission` fence from a task's own Shadow
    chat, and that fence's amend -- and they all land in MissionStore."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.missions = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_27a_create_normalises_a_good_probe(self):
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "verify", "check": "a.txt says hi",
             "probe": {"kind": "file_equals", "path": "a.txt", "text": "hi",
                       "junk": "dropped"}}])
        self.assertEqual(
            m["done_when"][0]["probe"],
            {"kind": "file_equals", "path": "a.txt", "text": "hi",
             "allow_trailing_newline": False})

    def test_27b_create_drops_an_unsafe_or_wrongly_tiered_probe(self):
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "verify", "check": "escape",
             "probe": {"kind": "file_exists", "path": "../../etc/passwd"}},
            {"tier": "founder_confirm", "check": "reads well",
             "probe": {"kind": "file_exists", "path": "a.txt"}},
            {"tier": "contains_artifact", "check": "BUILD OK"}])
        self.assertNotIn("probe", m["done_when"][0])
        self.assertNotIn("probe", m["done_when"][1])
        self.assertEqual(m["done_when"][0]["check"], "escape",
                         "the check survives; only the probe is dropped")
        self.assertEqual(m["done_when"][2],
                         {"tier": "contains_artifact", "check": "BUILD OK"},
                         "a row with no probe is byte-identical")

    def test_27c_amend_is_the_same_door(self):
        m = self.missions.create("x", "fix")
        m = self.missions.amend(m["id"], done_when=[
            {"tier": "verify", "check": "escape",
             "probe": {"kind": "file_exists", "path": "/etc/passwd",
                       "extra": 1}}])
        self.assertEqual(m["done_when"][0]["probe"],
                         {"kind": "file_exists", "path": "/etc/passwd"},
                         "an absolute path is shape-legal here and is "
                         "refused at READ time against the real workdir")

    def test_27d_confirmation_flags_survive_sanitising(self):
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "founder_confirm", "check": "signed"}])
        self.missions.transition(m["id"], "brief_confirm")
        m = self.missions.confirm_check(m["id"], 0)
        m = self.missions.amend(m["id"], done_when=m["done_when"])
        self.assertTrue(m["done_when"][0]["met"])
        self.assertIn("confirmed_by", m["done_when"][0])

    def test_27e_a_non_list_is_handed_back_untouched(self):
        self.assertIsNone(mission_engine.sanitise_probes(None))
        self.assertEqual(mission_engine.sanitise_probes("nope"), "nope")


class TestTheDemotionRule(unittest.TestCase):
    """A `verify` check without a valid probe is not a verify check.

    Deterministic, stated once in resolve_verify_tier, applied at both
    validation doors. It closes the loophole where Shadow could claim it
    verified something no engine ever looked at.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True}))
        providers.SETTINGS_PATH = p
        self.missions = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    GOOD = {"kind": "file_equals", "path": "a.txt", "text": "hi"}

    # ---- the rule itself, in one function --------------------------------

    def test_41_verify_with_a_valid_probe_stays_verify(self):
        tier, probe = mission_engine.resolve_verify_tier("verify", self.GOOD)
        self.assertEqual(tier, "verify")
        self.assertEqual(probe["kind"], "file_equals")

    def test_42_verify_without_a_probe_is_demoted(self):
        """DESTINATION CHANGED 2026-09-20 (D-SH-1), RULE UNCHANGED. A
        probe-less `verify` is still not a verify check and still never gets
        to claim "Shadow ran this check and it passed". It now lands on the
        JUDGE rather than on the founder's desk, because the judge can still
        settle it by reading the diff and says `cannot_tell` when it cannot --
        which is the founder's row arriving by the honest route instead of by
        default."""
        self.assertEqual(mission_engine.resolve_verify_tier("verify", None),
                         ("judge", None))

    def test_43_verify_with_an_invalid_probe_is_demoted(self):
        for bad in ({"kind": "command_succeeds", "path": "a"},
                    {"kind": "file_exists", "path": "../escape"},
                    {"kind": "file_equals", "path": "a.txt"},
                    {"kind": "file_exists"}, {}, "file_exists", 7):
            self.assertEqual(
                mission_engine.resolve_verify_tier("verify", bad),
                ("judge", None), repr(bad))

    def test_44_other_tiers_are_never_touched_by_the_rule(self):
        for tier in ("founder_confirm", "contains_artifact", "", None):
            self.assertEqual(
                mission_engine.resolve_verify_tier(tier, self.GOOD),
                (tier, None), repr(tier))

    # ---- door 1: the decider ---------------------------------------------

    def test_45_the_decider_path_demotes_and_keeps_the_wording(self):
        rows = validate_done_when([
            {"tier": "verify", "check": "The suite is green."},
            {"tier": "verify", "check": "a.txt says hi", "probe": self.GOOD}])
        self.assertEqual([r["tier"] for r in rows],
                         ["judge", "verify"])
        self.assertEqual([r["check"] for r in rows],
                         ["The suite is green.", "a.txt says hi"],
                         "demotion never re-words a check")
        self.assertNotIn("probe", rows[0])
        self.assertIn("probe", rows[1])

    def test_46_a_whole_decision_carries_the_demotion(self):
        d = validate_decision({
            "action": "continue", "instruction": "go", "reason": "r",
            "done_when": [{"tier": "verify", "check": "tests pass"}]})
        self.assertEqual(d["done_when"][0],
                         {"tier": "judge", "check": "tests pass"})

    def test_47_nothing_is_ever_dropped_by_the_rule(self):
        raw = [{"tier": "verify", "check": "one"},
               {"tier": "verify", "check": "two", "probe": self.GOOD},
               {"tier": "founder_confirm", "check": "three"}]
        self.assertEqual(len(validate_done_when(raw)), 3)

    # ---- door 2: create / amend ------------------------------------------

    def test_48_the_create_door_demotes(self):
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "verify", "check": "The suite is green."},
            {"tier": "verify", "check": "a.txt says hi", "probe": self.GOOD}])
        self.assertEqual([c["tier"] for c in m["done_when"]],
                         ["judge", "verify"])
        self.assertEqual(m["done_when"][0]["check"], "The suite is green.")

    def test_49_the_amend_door_demotes(self):
        m = self.missions.create("x", "fix")
        m = self.missions.amend(m["id"], done_when=[
            {"tier": "verify", "check": "tests pass"}])
        self.assertEqual(m["done_when"][0],
                         {"tier": "judge", "check": "tests pass"})

    def test_50_a_bad_probe_demotes_rather_than_falling_back(self):
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "verify", "check": "escape",
             "probe": {"kind": "file_exists", "path": "../../etc/passwd"}}])
        self.assertEqual(m["done_when"][0],
                         {"tier": "judge", "check": "escape"},
                         "an unsafe probe must not leave an attestation "
                         "check wearing the verify label")

    def test_51_rows_the_rule_does_not_own_pass_through_identically(self):
        rows = [{"tier": "contains_artifact", "check": "BUILD OK"},
                {"tier": "founder_confirm", "check": "reads well",
                 "met": True, "confirmed_by": "founder"},
                "not a dict", 7]
        self.assertEqual(mission_engine.sanitise_probes(rows), rows)

    def test_52_a_probe_on_a_non_verify_row_is_still_only_dropped(self):
        out = mission_engine.sanitise_probes([
            {"tier": "founder_confirm", "check": "reads well",
             "probe": self.GOOD}])
        self.assertEqual(out, [{"tier": "founder_confirm",
                                "check": "reads well"}],
                         "the tier is the founder's; only the probe goes")

    def test_53_save_is_not_a_door(self):
        """Requirement: no persisted mission is migrated or re-tiered."""
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "contains_artifact", "check": "x"}])
        m["done_when"] = [{"tier": "verify", "check": "legacy"}]
        self.missions.save(m)
        self.assertEqual(self.missions.load(m["id"])["done_when"][0]["tier"],
                         "verify")

    def test_54_retry_rebuilds_through_the_door_and_so_is_re_tiered(self):
        """Stated, not hidden: clone_for_retry goes through create(), so a
        retry of a legacy mission gets the CURRENT rule. That is a new
        record, not a migration of the old one -- the original is untouched
        on disk."""
        m = self.missions.create("x", "fix", done_when=[
            {"tier": "contains_artifact", "check": "x"}])
        m["done_when"] = [{"tier": "verify", "check": "legacy"}]
        self.missions.save(m)
        self.missions.transition(m["id"], "brief_confirm")
        self.missions.transition(m["id"], "running")
        self.missions.transition(m["id"], "stopped", "founder stop")
        clone = mission_engine.clone_for_retry(self.missions, m["id"])
        self.assertEqual(clone["done_when"][0]["tier"], "judge")
        self.assertEqual(clone["done_when"][0]["check"], "legacy")
        self.assertEqual(
            self.missions.load(m["id"])["done_when"][0]["tier"], "verify",
            "the original record is not rewritten")


# ------------------------------------------------- claim is not proof

class Engine(Root):
    """evaluate_done_when driven directly, with the REAL verifier injected --
    so a bypass is proved, not assumed."""

    def setUp(self):
        super().setUp()
        self.shadow_home = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.shadow_home.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.shadow_home.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True,
                                 "workdir": self.root}))
        providers.SETTINGS_PATH = p
        self.missions = MissionStore()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.shadow_home.cleanup()
        super().tearDown()

    def mission(self, done_when):
        m = self.missions.create("make the file", "fix",
                                 done_when=done_when)
        self.missions.transition(m["id"], "brief_confirm")
        return self.missions.transition(m["id"], "running")

    def evaluate(self, m, transcript):
        return evaluate_done_when(m, transcript, app._shadow_verifier,
                                  self.root)


CHECK = "shadow-race-test.txt contains exactly shadow-race-pass"
RACE_PROBE = {"kind": "file_equals", "path": "shadow-race-test.txt",
              "text": "shadow-race-pass", "allow_trailing_newline": True}
PERFECT_CLAIM = "I created the file.\nDONE-CHECK: " + CHECK + "\n"


class TestClaimIsNotProof(Engine):
    def test_27_a_perfect_claim_over_a_wrong_file_is_UNMET(self):
        """THE INVARIANT. The worker quotes the check character for
        character -- which is exactly what the manifest asks for and exactly
        what _shadow_verifier accepts -- and the file says something else."""
        self.write("shadow-race-test.txt", "shadow-race-FAIL")
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        self.assertTrue(app._shadow_verifier(CHECK, PERFECT_CLAIM),
                        "the attestation verifier IS satisfied by this claim")
        done, results = self.evaluate(m, PERFECT_CLAIM)
        self.assertFalse(done, "the filesystem is authoritative")
        self.assertFalse(results[0]["met"])

    def test_28_no_file_at_all_plus_a_perfect_claim_is_UNMET(self):
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        done, _ = self.evaluate(m, PERFECT_CLAIM)
        self.assertFalse(done)

    def test_29_a_passing_probe_needs_no_claim_at_all(self):
        """The worker paraphrases, refuses the format, or says nothing about
        the check. None of it matters."""
        self.write("shadow-race-test.txt", "shadow-race-pass\n")
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        for transcript in ("", "yeah that's handled",
                           "DONE-CHECK: I am not repeating your string",
                           "I refuse to emit DONE-CHECK lines."):
            done, results = self.evaluate(m, transcript)
            self.assertTrue(done, repr(transcript))
            self.assertTrue(results[0]["met"])

    def test_30_an_escaping_probe_is_unmet_even_with_a_perfect_claim(self):
        """THE SECOND FENCE, at read time. The door (sanitise_probes) keeps
        an escaping probe off disk, so this writes one PAST the door -- which
        is the real case it guards: a probe persisted against one workdir and
        evaluated after the founder pointed the app at another."""
        m = self.mission([{"tier": "verify", "check": CHECK}])
        m["done_when"][0]["probe"] = {"kind": "file_exists",
                                      "path": "../outside/secret.txt"}
        self.missions.save(m)
        m = self.missions.load(m["id"])
        self.assertIn("probe", m["done_when"][0], "it really is on disk")
        done, _ = self.evaluate(m, PERFECT_CLAIM)
        self.assertFalse(done, "a probe that cannot safely run is not a pass")

    def test_30b_the_door_keeps_that_probe_off_disk_in_the_first_place(self):
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": {"kind": "file_exists",
                                     "path": "../outside/secret.txt"}}])
        self.assertNotIn("probe", m["done_when"][0])

    def test_31_the_probe_root_defaults_to_the_delegate_workdir(self):
        """No caller threads it in production; the resolver reads the SAME
        setting the worker is spawned in."""
        self.write("shadow-race-test.txt", "shadow-race-pass")
        self.assertEqual(shadow_probe.default_root(),
                         os.path.expanduser(self.root))
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        done, _ = evaluate_done_when(m, "", app._shadow_verifier)
        self.assertTrue(done)


class TestUnprobedTiersAreUntouched(Engine):
    def test_32_a_probeless_verify_never_reaches_the_record(self):
        """WAS: "no probe -> the claim still settles it". That expectation
        encoded the loophole -- Shadow telling the founder "I ran this check
        and it passed" over a transcript it string-matched. The door now
        demotes, so the claim settles nothing.

        DESTINATION UPDATED 2026-09-20 (D-SH-1): the demotion now lands on
        `judge` rather than on the founder. The property this test exists for
        is UNCHANGED and is the assertion below -- a perfect DONE-CHECK line
        settles nothing, whichever tier the row ended up in. An unjudged
        `judge` row is unmet exactly as an unsigned `founder_confirm` row is,
        so the claim buys the worker nothing either way."""
        m = self.mission([{"tier": "verify", "check": CHECK}])
        self.assertEqual(m["done_when"][0]["tier"], "judge")
        done, results = self.evaluate(m, PERFECT_CLAIM)
        self.assertFalse(done, "a perfect DONE-CHECK line is not a signature")
        self.assertEqual(results[0]["tier"], "judge")
        self.assertFalse(results[0]["met"], "and it is not a judgement either")

    def test_32b_evaluation_time_attestation_is_UNCHANGED(self):
        """THE RULE IS VALIDATION-TIME ONLY. A probe-less `verify` already on
        disk -- written before this rule, by a door that did not have it --
        keeps scoring exactly as it always did. Nothing re-tiers a persisted
        mission, so no founder's task changes shape underneath them."""
        m = self.mission([{"tier": "contains_artifact", "check": "x"}])
        m["done_when"] = [{"tier": "verify", "check": CHECK}]
        self.missions.save(m)                     # save() is not a door
        m = self.missions.load(m["id"])
        self.assertEqual(m["done_when"][0]["tier"], "verify")
        self.assertTrue(self.evaluate(m, PERFECT_CLAIM)[0],
                        "the legacy attestation arm still scores")
        self.assertFalse(self.evaluate(m, "I did some stuff")[0])

    def test_33_founder_confirm_is_unchanged(self):
        m = self.mission([{"tier": "founder_confirm",
                           "check": "the copy reads well"}])
        done, results = self.evaluate(m, "DONE-CHECK: the copy reads well")
        self.assertFalse(done, "only confirm_check writes that flag")
        m = self.missions.confirm_check(m["id"], 0)
        done, _ = self.evaluate(m, "")
        self.assertTrue(done)

    def test_34_a_probe_smuggled_onto_a_stored_founder_confirm_row_is_inert(
            self):
        """Even if a row reaches disk with one, the tier gate in
        evaluate_done_when ignores it."""
        self.write("copy.txt", "anything")
        m = self.mission([{"tier": "founder_confirm", "check": "reads well",
                           "probe": {"kind": "file_exists",
                                     "path": "copy.txt"}}])
        done, _ = self.evaluate(m, "")
        self.assertFalse(done, "a machine must not sign the founder's name")

    def test_35_contains_artifact_is_unchanged(self):
        m = self.mission([{"tier": "contains_artifact", "check": "BUILD OK"}])
        self.assertFalse(self.evaluate(m, "it built")[0])
        self.assertTrue(self.evaluate(m, "log says BUILD OK here")[0])


# ------------------------------------------------------------- the loop

class TestLoop(Engine):
    def _engine(self, transcript, on_say=None):
        self.says = []

        async def sayer(mission, text):
            self.says.append(text)
            if on_say is not None:
                on_say(len(self.says))
            return True

        async def waiter(mission):
            return True

        return MissionEngine(self.missions, sayer, waiter,
                             lambda m: transcript(len(self.says)),
                             app._shadow_verifier, probe_root=self.root)

    def test_36_a_probed_task_is_DONE_after_the_first_worker_turn(self):
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        out = asyncio.run(self._engine(
            lambda n: PERFECT_CLAIM,
            on_say=lambda n: self.write("shadow-race-test.txt",
                                        "shadow-race-pass\n")
        ).run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["turns_used"], 1,
                         "the engine read the file; it took one turn")
        self.assertEqual(len(self.says), 1)

    def test_37_a_failing_probe_costs_another_worker_turn(self):
        """The adversarial case: the worker claims it, the file is wrong."""
        self.write("shadow-race-test.txt", "shadow-race-FAIL")
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 2
        self.missions.save(mm)
        out = asyncio.run(
            self._engine(lambda n: PERFECT_CLAIM).run_mission(m["id"]))
        self.assertNotEqual(out["state"], "done",
                            "the worker does not get to decide")
        self.assertEqual(len(self.says), 2, "Shadow instructed it again")

    def test_38_the_worker_is_driven_again_and_THEN_it_passes(self):
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])

        def on_say(n):
            self.write("shadow-race-test.txt",
                       "shadow-race-FAIL" if n < 2 else "shadow-race-pass")

        out = asyncio.run(
            self._engine(lambda n: PERFECT_CLAIM,
                         on_say=on_say).run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["turns_used"], 2)


# ---------------------------------------------------- what the worker sees

class TestWorkerNeverSeesTheProbe(Engine):
    def test_39_the_manifest_quotes_the_check_and_nothing_else(self):
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        block = app._worker_checks_block(m)
        self.assertIn("DONE-CHECK: " + CHECK, block)
        for leak in ("file_equals", "probe", "allow_trailing_newline",
                     '"path"', "kind"):
            self.assertNotIn(leak, block, leak)

    def test_40_and_neither_does_the_full_delegate_manifest(self):
        m = self.mission([{"tier": "verify", "check": CHECK,
                           "probe": RACE_PROBE}])
        manifest = app._delegate_manifest(m)
        self.assertIn(CHECK, manifest)
        for leak in ("file_equals", "allow_trailing_newline", "shadow_probe"):
            self.assertNotIn(leak, manifest, leak)


# --------------------------------------------------------- the worker lie

LIE_OBJECTIVE = ("Create shadow-lie-test.txt containing exactly "
                 "shadow-lie-pass")
LIE_CHECK = ("The file shadow-lie-test.txt exists and contains exactly "
             "shadow-lie-pass")
LIE_PROBE = {"kind": "file_equals", "path": "shadow-lie-test.txt",
             "text": "shadow-lie-pass", "allow_trailing_newline": True}

#: WHAT A LYING WORKER LOOKS LIKE. Not a paraphrase and not a near miss: the
#: check quoted character for character, in the exact format the manifest
#: asks for, which is precisely what _shadow_verifier is built to accept.
#: Anything weaker would prove only that a BAD claim fails.
LIE_CLAIM = ("I created shadow-lie-test.txt and wrote the required "
             "contents.\nDONE-CHECK: " + LIE_CHECK
             + "\nThe task is complete.")


class TestTheWorkerLie(Engine):
    """WORKER CLAIM != DONE, driven end to end through the real loop.

    The worker says the check is satisfied, in the exact words Shadow's
    attestation verifier accepts, and the file on disk says WRONG. Nothing is
    stubbed out of the verification path: the engine is the production
    MissionEngine, the verifier is app._shadow_verifier, the transcript goes
    through shadow_runner.evidence_messages exactly as a live one does, and
    the probe reads a real file with real syscalls.

    The only injected things are the four the engine ALREADY takes from
    production -- sayer, waiter, reader, verifier -- plus probe_root, so the
    probe looks at a tmpdir instead of the founder's repo. There is no
    test-only branch in production code and no escape hatch.
    """

    def setUp(self):
        super().setUp()
        self.says = []

    def _mission(self):
        m = self.missions.create(LIE_OBJECTIVE, "fix", target_mode="new",
                                 target_session="sess-lie",
                                 done_when=[{"tier": "verify",
                                             "check": LIE_CHECK,
                                             "probe": LIE_PROBE}])
        self.missions.transition(m["id"], "brief_confirm")
        return self.missions.transition(m["id"], "running")

    def _engine(self, mid, claim=LIE_CLAIM):
        """The real loop. `reader` builds the transcript a live worker turn
        would produce and runs it through the REAL evidence filter, so the
        claim arrives as an assistant turn with Shadow's own says removed --
        the same string production would evaluate."""
        self.read_back = []

        async def sayer(mission, text):
            self.says.append(text)
            return True                 # the worker NEVER touches the file

        async def waiter(mission):
            return True

        def reader(mission):
            doc = {"id": "sess-lie", "messages": (
                [{"role": "user",
                  "text": shadow_egress.say_tag(mid) + " " + s}
                 for s in self.says]
                + [{"role": "assistant", "text": claim}])}
            doc = dict(doc)
            doc["messages"] = shadow_runner.evidence_messages(doc)
            # THE SHAPE PRODUCTION PRODUCES (shadow_runner.evidence_text):
            # the streamed assistant text, with its real newlines, followed
            # by the json dump of the filtered doc. Handing the engine the
            # json alone would escape every "\n" and silently defeat
            # _DONE_CHECK_RE's MULTILINE anchor -- the claim would fail the
            # attestation verifier for a reason that has nothing to do with
            # the probe, and this class would pass while proving nothing.
            text = claim + " " + json.dumps(doc)
            self.read_back.append(text)
            return text

        return MissionEngine(self.missions, sayer, waiter, reader,
                             app._shadow_verifier, probe_root=self.root)

    # ---- the scenario ----------------------------------------------------

    def test_55_the_claim_is_a_PERFECT_one_and_the_file_says_WRONG(self):
        """The premise, pinned. If either half of this drifts the rest of the
        class stops proving anything: a claim the verifier would reject, or a
        file that happens to be right, would pass for the wrong reason."""
        self.write("shadow-lie-test.txt", "WRONG")
        self.assertTrue(
            app._shadow_verifier(LIE_CHECK, LIE_CLAIM),
            "the attestation verifier ACCEPTS this claim -- that is the "
            "whole danger, and it must remain true for this test to bite")
        self.assertEqual(
            Path(self.root, "shadow-lie-test.txt").read_text(), "WRONG")

    def test_56_shadow_runs_the_probe_itself_and_the_check_stays_unmet(self):
        self.write("shadow-lie-test.txt", "WRONG")
        m = self._mission()
        done, results = self.evaluate(m, LIE_CLAIM)
        self.assertFalse(done)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["met"], "the filesystem is authoritative")
        self.assertEqual(results[0]["check"], LIE_CHECK)
        self.assertEqual(shadow_probe.run(LIE_PROBE, self.root).reason,
                         "contents differ",
                         "and it is the CONTENTS that settled it")

    def test_57_the_mission_cannot_become_done_from_the_claim(self):
        self.write("shadow-lie-test.txt", "WRONG")
        m = self._mission()
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 3
        self.missions.save(mm)
        out = asyncio.run(self._engine(m["id"]).run_mission(m["id"]))
        self.assertNotEqual(out["state"], "done",
                            "a worker does not get to declare itself done")
        self.assertFalse((out.get("completion") or {}).get("done"),
                         "and no completion record is stamped")
        self.assertEqual(Path(self.root, "shadow-lie-test.txt").read_text(),
                         "WRONG", "nothing in the loop wrote the file")

    def test_58_the_claim_IS_retained_as_evidence_not_as_proof(self):
        """Two things at once, and the pairing is the point. The claim is not
        censored -- it reaches the engine, in full, as the worker's report --
        and it settles nothing."""
        self.write("shadow-lie-test.txt", "WRONG")
        m = self._mission()
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 2
        self.missions.save(mm)
        out = asyncio.run(self._engine(m["id"]).run_mission(m["id"]))
        self.assertTrue(self.read_back, "the engine read the transcript")
        evidence = self.read_back[-1]
        self.assertIn("DONE-CHECK", evidence,
                      "the report survives in the evidence")
        self.assertIn("shadow-lie-pass", evidence)
        self.assertTrue(
            app._shadow_verifier(LIE_CHECK, evidence),
            "and the evidence the engine actually held would have satisfied "
            "the attestation verifier -- it was simply never asked")
        self.assertNotEqual(out["state"], "done")

    def test_59_repeating_the_lie_buys_nothing(self):
        """Not a one-turn accident: the worker keeps claiming it, every turn,
        and the answer does not drift."""
        self.write("shadow-lie-test.txt", "WRONG")
        m = self._mission()
        mm = self.missions.load(m["id"])
        mm["max_turns"] = 3
        self.missions.save(mm)
        out = asyncio.run(self._engine(m["id"]).run_mission(m["id"]))
        self.assertNotEqual(out["state"], "done")
        self.assertGreaterEqual(len(self.says), 1,
                                "Shadow kept driving instead of completing")
        self.assertFalse(self.evaluate(self.missions.load(m["id"]),
                                       LIE_CLAIM)[0])

    def test_60_a_near_miss_file_is_still_WRONG(self):
        """The lie does not have to be bold. One character is enough."""
        for wrong in ("shadow-lie-Pass", "shadow-lie-pass ",
                      " shadow-lie-pass", "shadow-lie-passs", ""):
            self.write("shadow-lie-test.txt", wrong)
            m = self._mission()
            self.assertFalse(self.evaluate(m, LIE_CLAIM)[0], repr(wrong))

    # ---- the positive control -------------------------------------------

    def test_61_the_SAME_setup_reaches_done_when_the_file_is_right(self):
        """WITHOUT THIS THE CLASS PROVES NOTHING. Every assertion above is
        satisfied by a mission that can never complete, so the identical
        harness -- same objective, same check, same probe, same claim, same
        engine -- must reach `done` on the one thing that changed: the bytes
        on disk."""
        self.write("shadow-lie-test.txt", "shadow-lie-pass\n")
        m = self._mission()
        out = asyncio.run(self._engine(m["id"]).run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["turns_used"], 1)

    def test_62_and_the_claim_is_not_what_completed_it(self):
        """The file is right and the worker says NOTHING about the check."""
        self.write("shadow-lie-test.txt", "shadow-lie-pass")
        m = self._mission()
        out = asyncio.run(self._engine(
            m["id"], claim="done I guess").run_mission(m["id"]))
        self.assertEqual(out["state"], "done")
        self.assertFalse(app._shadow_verifier(LIE_CHECK, "done I guess"),
                         "nothing here could have satisfied attestation")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTheAddedKinds(Root):
    """line_count / lines_distinct / file_contains (founder, 2026-09-17).

    WHY THEY EXIST. A two-kind vocabulary (file_exists, file_equals) could
    not express the checks a founder actually writes, so resolve_verify_tier
    demoted them to founder_confirm and Shadow parked instead of driving.
    Measured on m-56e8a6ee4f1f: "A file named `Joy Stefan` exists" got a
    probe and read "Shadow checks this"; "contains 10 lines, each a distinct
    line of random text" got none and read "Confirm".

    WHAT THEY ARE NOT. Every one is a plain read of one file. No globbing, no
    shell, no regex engine -- file_contains is a SUBSTRING test exactly so a
    check's text never reaches a pattern matcher. "random text" is still not
    machine-decidable and still belongs to the founder; splitting a composite
    check is what makes that honest rather than all-or-nothing.
    """

    def test_23_line_count_counts_content_lines(self):
        """"10 lines" means ten lines of content. The newline an editor
        leaves at the end is the editor's, not an eleventh line."""
        self.write("ten.txt", "\n".join("l%d" % i for i in range(10)) + "\n")
        p = {"kind": "line_count", "path": "ten.txt", "count": 10}
        self.assertTrue(shadow_probe.met(p, self.root))
        self.assertFalse(shadow_probe.met(
            dict(p, count=11), self.root))
        # ...and the strict reading is available when a check asks for it
        self.assertFalse(shadow_probe.met(
            dict(p, count=10, ignore_trailing_blank=False), self.root))

    def test_24_line_count_refuses_a_bool_and_a_negative(self):
        """bool is an int in Python, so True would otherwise validate as 1 --
        a model answering the wrong question must not produce a valid probe."""
        for bad in (True, False, -1, 1.5, "3", None,
                    shadow_probe.PROBE_LINES_MAX + 1):
            self.assertIsNone(shadow_probe.validate_probe(
                {"kind": "line_count", "path": "a.txt", "count": bad}),
                repr(bad))

    def test_25_lines_distinct_finds_the_repeat(self):
        self.write("uniq.txt", "alpha\nbeta\ngamma\n")
        self.write("dupe.txt", "alpha\nbeta\nalpha\n")
        self.assertTrue(shadow_probe.met(
            {"kind": "lines_distinct", "path": "uniq.txt"}, self.root))
        r = shadow_probe.run(
            {"kind": "lines_distinct", "path": "dupe.txt"}, self.root)
        self.assertFalse(r.met)
        self.assertIn("alpha", r.reason)

    def test_26_an_empty_file_is_not_all_distinct(self):
        """Vacuous truth is the wrong answer: it would pass a check on a file
        nobody wrote."""
        self.write("empty.txt", "")
        self.assertFalse(shadow_probe.met(
            {"kind": "lines_distinct", "path": "empty.txt"}, self.root))
        self.write("blanks.txt", "\n\n\n")
        self.assertFalse(shadow_probe.met(
            {"kind": "lines_distinct", "path": "blanks.txt"}, self.root))

    def test_27_file_contains_is_a_substring_never_a_pattern(self):
        self.write("doc.txt", "Ships on 2026-10-01. Owner: Joy.")
        self.assertTrue(shadow_probe.met(
            {"kind": "file_contains", "path": "doc.txt", "text": "2026-10-01"},
            self.root))
        self.assertFalse(shadow_probe.met(
            {"kind": "file_contains", "path": "doc.txt", "text": "2026-11-01"},
            self.root))
        # a REGEX is matched literally -- nothing here compiles it
        self.assertFalse(shadow_probe.met(
            {"kind": "file_contains", "path": "doc.txt", "text": "20..-10-01"},
            self.root))
        # case folding only when asked
        self.assertFalse(shadow_probe.met(
            {"kind": "file_contains", "path": "doc.txt", "text": "owner"},
            self.root))
        self.assertTrue(shadow_probe.met(
            {"kind": "file_contains", "path": "doc.txt", "text": "owner",
             "ignore_case": True}, self.root))

    def test_28_file_contains_refuses_empty_text(self):
        """An empty substring is in every file, so it is not a check."""
        self.assertIsNone(shadow_probe.validate_probe(
            {"kind": "file_contains", "path": "a.txt", "text": ""}))

    def test_29_the_new_kinds_are_confined_like_the_old_ones(self):
        """Confinement is one comparison after realpath and it is not per
        kind -- but a new kind that skipped `resolve` would bypass it, so
        every one is asserted here rather than assumed."""
        for kind in ("line_count", "lines_distinct", "file_contains"):
            raw = {"kind": kind, "path": "../escape.txt"}
            if kind == "line_count":
                raw["count"] = 1
            if kind == "file_contains":
                raw["text"] = "x"
            self.assertIsNone(shadow_probe.validate_probe(raw), kind)
            # and an ABSOLUTE path outside the root is refused at run time
            raw["path"] = "/etc/passwd"
            self.assertFalse(shadow_probe.met(raw, self.root), kind)

    def test_30_a_missing_file_is_unmet_for_every_new_kind(self):
        for raw in ({"kind": "line_count", "path": "no.txt", "count": 1},
                    {"kind": "lines_distinct", "path": "no.txt"},
                    {"kind": "file_contains", "path": "no.txt", "text": "x"}):
            r = shadow_probe.run(raw, self.root)
            self.assertFalse(r.met)
            self.assertIn("no file there", r.reason)
