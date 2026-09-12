"""test_kit_runner.py -- apps-frameworks/check.py against real folders.

Pass fixtures per kind (tests/fixtures/kit/pass/<kind>, regenerated here into a
temp dir from the kit templates), one failing folder per v1 must-fix id (the
matrix), the degrade cases (no render runtime -> exit 3, --allow-skip-render ->
0, a blocking failure plus no runtime -> 1) and the waiver.

Isolation (I-T1): SUTRA_NATIVE_HOME is a temp dir and cached modules are popped
before check.py imports modules_api / modules_pkg / placement_engine.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="kit-runner-native-")
os.environ["SUTRA_MODULES_HOME"] = tempfile.mkdtemp(prefix="kit-runner-modules-")
os.environ["KIT_NO_RENDER"] = "1"          # the render lane needs Chrome; the degrade tests pin the skip path
for _m in ("placement_engine", "org_api", "project_import", "modules_api", "modules_events", "modules_pkg", "workspace_api", "app", "check"):
    sys.modules.pop(_m, None)

UI = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(UI, "apps-frameworks")
FIX = os.path.join(UI, "tests", "fixtures", "kit")
sys.path.insert(0, KIT)
sys.path.insert(0, FIX)
sys.path.insert(0, UI)
import check  # noqa: E402
import make_fixtures  # noqa: E402
import build_kit  # noqa: E402


def _cli(*args):
    env = dict(os.environ)
    p = subprocess.run([sys.executable, os.path.join(KIT, "check.py")] + list(args), capture_output=True, text=True, env=env, cwd=UI)
    return p.returncode, p.stdout, p.stderr


class Runner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="kit-fixtures-")
        make_fixtures.main([cls.root])
        cls.pass_dirs = {k: os.path.join(cls.root, "pass", k) for k in ("page", "chat", "link")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    # ---- pass fixtures ----------------------------------------------------------

    def test_pass_fixtures_have_no_blocking_failure(self):
        for kind, d in self.pass_dirs.items():
            results, summary, code = check.run(d, kind, allow_skip_render=True)
            fails = [(r["id"], r["detail"]) for r in results if r["status"] == "fail" and r["level"] == "must-fix"]
            self.assertEqual(fails, [], "%s pass fixture blocks: %s" % (kind, fails))
            self.assertEqual(code, 0, "%s: exit %d, summary %s" % (kind, code, summary))
            self.assertFalse(summary["blocked"])

    def test_pass_fixtures_run_exactly_the_profile_checks(self):
        for kind, d in self.pass_dirs.items():
            results, _s, _c = check.run(d, kind, allow_skip_render=True)
            ids = {r["id"] for r in results} - {"C36"}
            profile = json.load(open(os.path.join(KIT, "profiles", kind + ".json")))
            self.assertEqual(ids, set(profile["checks"]) - {"C36"}, kind)

    def test_levels_come_from_kit_json(self):
        results, _s, _c = check.run(self.pass_dirs["page"], "page", allow_skip_render=True)
        for r in results:
            self.assertEqual(r["level"], "must-fix" if r["id"] in build_kit.V1_MUST_FIX else "suggest", r["id"])

    # ---- the matrix: one failing folder per must-fix id -------------------------

    def test_matrix_every_must_fix_id_has_a_fixture(self):
        self.assertEqual(set(make_fixtures.MUTATIONS), set(build_kit.V1_MUST_FIX))

    def test_matrix_each_mutation_fails_its_own_check(self):
        # C36 needs a render runtime and KIT_NO_RENDER is pinned for this module; it has its own test below
        root = tempfile.mkdtemp(prefix="kit-matrix-")
        try:
            for cid in sorted(build_kit.V1_MUST_FIX - {"C36"}, key=lambda s: int(s[1:])):
                kind, folder = make_fixtures.mutate(cid, root)
                results, summary, code = check.run(folder, kind, allow_skip_render=True)
                by = {r["id"]: r for r in results}
                self.assertIn(cid, by, cid)
                self.assertEqual(by[cid]["status"], "fail", "%s did not fail: %s" % (cid, by[cid]))
                self.assertEqual(by[cid]["level"], "must-fix", cid)
                self.assertTrue(summary["blocked"], cid)
                self.assertEqual(code, 1, cid)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    # ---- C36 (must-fix since kit 1.1.0): the render lane -------------------------
    # The desktop's own run_checks pins KIT_NO_RENDER=1 and allows the skip, so C36
    # bites in the CLI and MCP lanes the chat runs before "done". These two tests run
    # the CLI with the pin removed: with node + Chrome they prove the lane; without
    # them they prove the honest degrade (skip, exit 3, never a pass) and skip.

    def _render_cli(self, folder, kind):
        env = dict(os.environ)
        env.pop("KIT_NO_RENDER", None)
        p = subprocess.run([sys.executable, os.path.join(KIT, "check.py"), folder, "--kind", kind, "--no-write", "--json"],
                           capture_output=True, text=True, env=env, cwd=UI, timeout=240)
        doc = json.loads(p.stdout)
        return p.returncode, doc, next(r for r in doc["results"] if r["id"] == "C36")

    def test_render_c36_blocks_a_page_that_throws_where_a_runtime_exists(self):
        root = tempfile.mkdtemp(prefix="kit-c36-")
        try:
            kind, folder = make_fixtures.mutate("C36", root)
            code, doc, c36 = self._render_cli(folder, kind)
            self.assertEqual(c36["level"], "must-fix")
            if check._which("node") and check._find_chrome():
                self.assertEqual(c36["status"], "fail", c36)
                self.assertIn("render check: boom", c36["detail"])
                self.assertTrue(doc["summary"]["blocked"])
                self.assertEqual(code, 1)
            else:
                self.assertEqual(c36["status"], "skip", c36)
                self.assertFalse(doc["summary"]["blocked"])
                self.assertEqual(code, 3, "no runtime: the run is incomplete, never a pass")
                self.skipTest("no headless runtime on this machine; the degrade path was asserted")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_render_c36_passes_the_page_starter_where_a_runtime_exists(self):
        if not (check._which("node") and check._find_chrome()):
            self.skipTest("no headless runtime on this machine")
        code, doc, c36 = self._render_cli(self.pass_dirs["page"], "page")
        self.assertEqual(c36["status"], "pass", c36)
        self.assertEqual(doc["summary"]["render"], "render: dark+light")
        self.assertEqual(code, 0)

    # ---- degrade + waiver -------------------------------------------------------

    def test_degrade_page_without_render_exits_3_unless_allowed(self):
        code, out, _err = _cli(self.pass_dirs["page"], "--kind", "page", "--no-write")
        self.assertEqual(code, 3, out)
        self.assertIn("render: not run", out)
        code, out, _err = _cli(self.pass_dirs["page"], "--kind", "page", "--no-write", "--allow-skip-render")
        self.assertEqual(code, 0, out)

    def test_degrade_blocking_failure_beats_no_render(self):
        root = tempfile.mkdtemp(prefix="kit-degrade-")
        try:
            kind, folder = make_fixtures.mutate("C25", root)
            code, out, _err = _cli(folder, "--kind", kind, "--no-write")
            self.assertEqual(code, 1, out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_degrade_unreadable_folder_exits_2(self):
        code, _out, err = _cli(os.path.join(self.root, "nope"), "--no-write")
        self.assertEqual(code, 2)
        self.assertIn("module.json", err)

    def test_degrade_chat_and_link_report_render_not_applicable(self):
        for kind in ("chat", "link"):
            results, summary, code = check.run(self.pass_dirs[kind], kind)
            c36 = next(r for r in results if r["id"] == "C36")
            self.assertEqual(c36["status"], "n/a", kind)
            self.assertEqual(code, 0, kind)

    def test_waive_turns_one_blocking_failure_into_a_recorded_waiver(self):
        root = tempfile.mkdtemp(prefix="kit-waive-")
        try:
            kind, folder = make_fixtures.mutate("C10", root)
            code, out, _err = _cli(folder, "--kind", kind, "--allow-skip-render", "--waive", "C10", "--why", "the grey is the brand grey, agreed with design")
            self.assertEqual(code, 0, out)
            self.assertIn("waived", out)
            rec = open(os.path.join(folder, "APP.md"), encoding="utf-8").read()
            self.assertIn("waived: C10 - the grey is the brand grey", rec)
            self.assertIn("## Checks", rec)
            self.assertTrue(rec.splitlines()[0].startswith("frameworkKit:"), "the stamp line is untouched")
            code, _out, err = _cli(folder, "--kind", kind, "--waive", "C10")
            self.assertEqual(code, 2, "a waiver without a reason is refused")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_checks_block_is_the_only_write(self):
        d = self.pass_dirs["chat"]
        before = json.load(open(os.path.join(d, "module.json")))
        code, _out, _err = _cli(d, "--kind", "chat")
        self.assertEqual(code, 0)
        after = json.load(open(os.path.join(d, "module.json")))
        self.assertEqual(before, after, "module.json must not change")
        rec = open(os.path.join(d, "APP.md"), encoding="utf-8").read()
        self.assertIn("## Checks\n\nkit ", rec)
        self.assertEqual(rec.count("## Checks"), 1)

    def test_json_output(self):
        code, out, _err = _cli(self.pass_dirs["link"], "--kind", "link", "--json", "--no-write")
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertIn("results", doc)
        self.assertEqual(doc["summary"]["kind"], "link")

    def test_leak_scanner_catches_founder_text_and_allows_the_literals(self):
        self.assertEqual(check.leak_hits("Filed under module.json and /api/modules; the modules home is here.", strict=True), [])
        hits = check.leak_hits("INPUT: founder said\nThis module is filed under dref-0123456789abcdef per ADR-039 and D-M17.", strict=True)
        reasons = {h[0] for h in hits}
        self.assertTrue({"a governance block line", "a department ref", "a decision record number", "a design decision id", "the internal word module"} <= reasons, reasons)
        self.assertEqual(check.leak_hits("Design question DS1 and rule DE-4 are fine; so is C10."), [])
        # codex R2 P1: a builder's own prose is theirs -- loan buckets, chips and the plural word pass
        self.assertEqual(check.leak_hits("Loan id D12 is overdue; bucket D2.D1 shows 63 days; lending modules by owner."), [])
        self.assertEqual([h[0] for h in check.leak_hits("Open the module to see the modules list.", strict=True)], ["the internal word module", "the internal word module"])


if __name__ == "__main__":
    unittest.main()
