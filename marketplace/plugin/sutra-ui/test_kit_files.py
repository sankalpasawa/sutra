"""test_kit_files.py -- the Apps frameworks kit files are one contract.

angles/*.json is the only authored source of ids (codex Phase A consult P1).
This suite is the validator the kit has instead of a JSON Schema (P2): shape,
enums, id regexes, uniqueness across angles, the v1 must-fix set, the generated
twins and screens.json being current, and (from Phase B) profile coverage and
the leak scan over builder-facing files.

Isolation (I-T1, registry RCA 2026-09-11): SUTRA_NATIVE_HOME is set to a temp
dir and cached modules popped BEFORE anything imports modules_api.
"""
import glob
import json
import os
import re
import sys
import tempfile
import unittest

os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="kit-native-")
os.environ["SUTRA_MODULES_HOME"] = tempfile.mkdtemp(prefix="kit-modules-")
for _m in ("placement_engine", "org_api", "project_import", "modules_api", "modules_events", "modules_pkg", "workspace_api", "app"):
    sys.modules.pop(_m, None)

UI = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(UI, "apps-frameworks")
sys.path.insert(0, KIT)
sys.path.insert(0, UI)
import build_kit  # noqa: E402

# Design questions are DS1..DS6, not D1..D6: the leak scanner (C4) refuses
# decision ids shaped D<n> / D-M<n>, and a record must never trip its own scan.
Q_RE = re.compile(r"^(P|S|DS|E|B|F)[0-9]{1,2}$")
C_RE = re.compile(r"^C[0-9]{1,2}$")
R_RE = re.compile(r"^(PR|ST|DE|EN|BA|FR)-[0-9]{1,2}$")


class KitFiles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.angles = build_kit.load_angles()

    # ---- shape --------------------------------------------------------------

    def test_ids_shape_and_enums(self):
        for a in self.angles:
            self.assertIn(a["angle"], build_kit.ANGLE_ORDER)
            self.assertTrue(a["purpose"].strip())
            for q in a["questions"]:
                self.assertRegex(q["id"], Q_RE, a["angle"])
                self.assertTrue(q["question"].strip())
                self.assertTrue(set(q["required_for"]) <= set(build_kit.KINDS), q["id"])
                self.assertIsInstance(q["optional"], bool)
                self.assertIn(q["v1_asked"], build_kit.V1_ASKED, q["id"])
                if q["optional"]:
                    self.assertEqual(q["required_for"], [], "%s: an optional question is required for no kind" % q["id"])
                else:
                    self.assertTrue(q["required_for"], "%s: a required question names at least one kind" % q["id"])
            for r in a["rules"]:
                self.assertRegex(r["id"], R_RE, a["angle"])
                self.assertTrue(r["rule"].strip() and r["sutra_source"].strip() and r["enforced_by"].strip(), r["id"])
                self.assertTrue(set(r["kinds"]) <= set(build_kit.KINDS) and r["kinds"], r["id"])
            for c in a["checks"]:
                self.assertRegex(c["id"], C_RE, a["angle"])
                self.assertIn(c["level"], build_kit.LEVELS, c["id"])
                self.assertTrue(set(c["kinds"]) <= set(build_kit.KINDS) and c["kinds"], c["id"])
                self.assertTrue(c["what"].strip() and c["evaluator"].strip(), c["id"])
                self.assertIsInstance(c["v1_must_fix"], bool, c["id"])
                if c["level"] == "required":
                    self.assertEqual(sorted(c["kinds"]), sorted(build_kit.KINDS) if c["id"] != "C36" else ["page"],
                                     "%s: required means every kind (C36 is the page-only exception)" % c["id"])

    def test_ids_are_unique_across_angles(self):
        qs = [q["id"] for a in self.angles for q in a["questions"]]
        cs = [c["id"] for a in self.angles for c in a["checks"]]
        rs = [r["id"] for a in self.angles for r in a["rules"]]
        for name, ids in (("question", qs), ("check", cs), ("rule", rs)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            self.assertEqual(dupes, [], "%s ids in more than one angle: %s" % (name, dupes))
        self.assertEqual(len(cs), 38, "the kit has 38 check ids (C1..C38)")
        self.assertEqual(sorted(cs, key=lambda s: int(s[1:])), ["C%d" % i for i in range(1, 39)])
        self.assertGreaterEqual(len(qs), 30)

    def test_ids_v1_must_fix_is_exactly_the_ruling(self):
        flagged = {c["id"] for a in self.angles for c in a["checks"] if c["v1_must_fix"]}
        self.assertEqual(flagged, set(build_kit.V1_MUST_FIX))
        self.assertEqual(len(flagged), 18)

    def test_ids_rule_enforcement_names_existing_checks(self):
        cs = {c["id"] for a in self.angles for c in a["checks"]}
        for a in self.angles:
            for r in a["rules"]:
                for cid in re.findall(r"\bC[0-9]{1,2}\b", r["enforced_by"]):
                    self.assertIn(cid, cs, "%s names %s which is not a check" % (r["id"], cid))

    # ---- generated twins ------------------------------------------------------

    def test_twins_are_current(self):
        for path, content in build_kit.derived_files().items():
            self.assertTrue(os.path.exists(path), "missing generated file %s (run build_kit.py)" % os.path.relpath(path, KIT))
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), content, "%s is stale: run build_kit.py" % os.path.relpath(path, KIT))

    def test_twins_screens_json_matches_screen_ids(self):
        import modules_api
        with open(os.path.join(KIT, "screens.json"), encoding="utf-8") as fh:
            screens = json.load(fh)
        self.assertEqual(screens["screens"], list(modules_api.SCREEN_IDS))
        self.assertEqual(sorted(screens["forbidden"]), sorted(modules_api.LINK_FORBIDDEN))
        for bad in modules_api.LINK_FORBIDDEN:
            self.assertNotIn(bad, screens["screens"])

    # ---- Phase B (skipped until the profiles exist) ---------------------------

    def _profiles(self):
        return sorted(glob.glob(os.path.join(KIT, "profiles", "*.json")))

    def test_coverage_profiles_select_exactly_the_required_ids(self):
        paths = self._profiles()
        if not paths:
            self.skipTest("profiles land in Phase B")
        by_kind_required = {k: set() for k in build_kit.KINDS}
        for a in self.angles:
            for q in a["questions"]:
                for k in q["required_for"]:
                    by_kind_required[k].add(q["id"])
        all_checks = {c["id"]: c for a in self.angles for c in a["checks"]}
        all_q = {q["id"] for a in self.angles for q in a["questions"]}
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                p = json.load(fh)
            kind = p["kind"]
            asked = p["questions_v1"] + p["prefilled_v1"] + p["asked_at_end_v1"]
            self.assertEqual(len(asked), len(set(asked)), "%s asks a question twice" % kind)
            self.assertTrue(set(asked) <= all_q, "%s names an unknown question id" % kind)
            self.assertTrue(by_kind_required[kind] <= set(asked),
                            "%s misses required ids %s" % (kind, sorted(by_kind_required[kind] - set(asked))))
            for cid in p["checks"]:
                self.assertIn(cid, all_checks, "%s names unknown check %s" % (kind, cid))
                self.assertIn(kind, all_checks[cid]["kinds"], "%s lists %s which does not apply to it" % (kind, cid))
            for cid, c in all_checks.items():
                if kind in c["kinds"] and cid not in p["checks"]:
                    self.fail("%s omits %s which applies to it" % (kind, cid))

    def test_leak_builder_facing_files_carry_no_founder_text(self):
        facing = sorted(glob.glob(os.path.join(KIT, "angles", "*.md")) + glob.glob(os.path.join(KIT, "profiles", "*.md"))
                        + glob.glob(os.path.join(KIT, "templates", "**", "*"), recursive=True))
        facing = [p for p in facing if os.path.isfile(p) and not p.endswith(".rules.md")]
        if not facing:
            self.skipTest("builder-facing files land in Phase B")
        try:
            import check as kit_check
        except ImportError:
            self.skipTest("check.py lands in Phase C")
        for p in facing:
            with open(p, encoding="utf-8", errors="replace") as fh:
                hits = kit_check.leak_hits(fh.read())
            self.assertEqual(hits, [], "%s leaks founder-only text: %s" % (os.path.relpath(p, KIT), hits[:3]))


if __name__ == "__main__":
    unittest.main()
