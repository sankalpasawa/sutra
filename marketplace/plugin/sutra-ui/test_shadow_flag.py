"""PLAN-100 S8: the shadow.enabled flag ships dark.

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

    def test_01_default_is_off_when_no_settings_file(self):
        self.assertFalse(providers.shadow_enabled())

    def test_02_default_is_off_when_key_absent(self):
        self.settings.write_text(json.dumps({"provider": "claude"}))
        self.assertFalse(providers.shadow_enabled())

    def test_03_junk_values_are_off(self):
        for junk in ("true", 1, "on", {"enabled": True}, None, 0):
            self.settings.write_text(json.dumps({"shadow.enabled": junk}))
            self.assertFalse(providers.shadow_enabled(), repr(junk))

    def test_04_only_boolean_true_is_on(self):
        self.settings.write_text(json.dumps({"shadow.enabled": True}))
        self.assertTrue(providers.shadow_enabled())

    def test_05_explicit_settings_arg_wins(self):
        self.assertTrue(providers.shadow_enabled({"shadow.enabled": True}))
        self.assertFalse(providers.shadow_enabled({}))

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
