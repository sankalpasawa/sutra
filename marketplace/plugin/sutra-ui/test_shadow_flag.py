"""PLAN-100 S8 (amended by founder direction 2026-08-25): the shadow
 flag ships ON.

Off-state contract: absent file, absent key, or junk values are all OFF.
Only a literal boolean true turns it on. shadow_enabled() is the single
sanctioned read path (the lazy-load guard for everything Shadow).

No importlib.reload here: reloading providers mid-suite replaces module
state other test files hold references to (broke test_ws_origin_guard).
We patch SETTINGS_PATH on the live module and restore it.
"""
import json
import tempfile
import unittest
from pathlib import Path

import providers


class TestShadowFlag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Path(self.tmp.name) / "settings.json"
        self._orig = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = self.settings

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def test_01_default_is_ON_when_no_settings_file(self):
        # founder direction 2026-08-25: Shadow is always on by default
        self.assertTrue(providers.shadow_enabled())

    def test_02_default_is_ON_when_key_absent(self):
        self.settings.write_text(json.dumps({"provider": "claude"}))
        self.assertTrue(providers.shadow_enabled())

    def test_03_only_boolean_false_disables(self):
        self.settings.write_text(json.dumps({"shadow.enabled": False}))
        self.assertFalse(providers.shadow_enabled())
        for not_off in ("false", 0, None, "off"):
            self.settings.write_text(json.dumps({"shadow.enabled": not_off}))
            self.assertTrue(providers.shadow_enabled(), repr(not_off))

    def test_04_boolean_true_is_on(self):
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        self.assertTrue(providers.shadow_enabled())

    def test_05_explicit_settings_arg_wins(self):
        self.assertFalse(providers.shadow_enabled({"shadow.enabled": False}))
        self.assertTrue(providers.shadow_enabled({}))

    def test_06_accessor_is_the_only_read_path(self):
        # the lint the off-state suite also runs: the key appears only in
        # providers.py (accessor home) and this test file
        import subprocess
        # escaped dot: the SETTINGS KEY is the contraband, not calls to
        # the shadow_enabled() accessor (which are the sanctioned path)
        out = subprocess.run(
            ["git", "grep", "-nE", r"shadow\.enabled", "--", "*.py"],
            capture_output=True, text=True).stdout
        # test fixtures legitimately WRITE the key into settings files;
        # the lint hunts production READS outside the accessor's home
        offenders = [l for l in out.splitlines()
                     if not l.startswith("providers.py")
                     and not l.startswith("test_")]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
