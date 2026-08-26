"""Finding the CLI is the difference between a working panel and a dead one.

A user reported Claude installed and the panel saying "binary 'claude' not on
PATH (config found at ~/.claude)". Three distinct causes hide behind that one
sentence, and the panel could not tell them apart:

  - a GUI launch inherits launchd's PATH, and the login-shell harvest that
    repairs it failed silently (timeout, or an rc file printing over its output)
  - the binary is in a version-manager shim dir the probe did not know
  - Claude DESKTOP is installed and Claude CODE is not -- different products;
    Desktop ships no `claude` binary at all (verified against an installed
    bundle: no executable of that name inside it)

The third is the cruel one: nothing is broken, nothing is misconfigured, and
the message sends the operator hunting for a PATH problem that does not exist.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import providers


class KnownInstallLocations(unittest.TestCase):
    def test_version_manager_shims_are_probed(self):
        """The gap that produced the report. A shim dir is exactly where a CLI
        lands when the operator manages runtimes, and it is never on a GUI
        launch's PATH."""
        dirs = " ".join(providers._KNOWN_BIN_DIRS)
        for needed in ("pnpm", "mise", "asdf", "nodenv"):
            self.assertIn(needed, dirs, "%s shim dir is not probed" % needed)

    def test_the_documented_vendor_locations_are_still_probed(self):
        """Regression guard: widening the list must not drop what worked."""
        for needed in ("~/.local/bin", "~/.claude/local", "/opt/homebrew/bin",
                       "/usr/local/bin", "~/.npm-global/bin"):
            self.assertIn(needed, providers._KNOWN_BIN_DIRS)


class ClaudeDesktopIsADifferentProduct(unittest.TestCase):
    def test_detected_by_bundle(self):
        with mock.patch("os.path.isdir", lambda p: p.endswith("Claude.app")):
            self.assertTrue(providers.claude_desktop_installed())

    def test_absent_when_no_bundle(self):
        with mock.patch("os.path.isdir", lambda p: False):
            self.assertFalse(providers.claude_desktop_installed())

    def test_the_reason_names_the_RIGHT_product_to_install(self):
        """With Desktop present and the CLI missing, "not on PATH" is a wrong
        diagnosis. The operator has to install a different product."""
        spec = {"id": "claude", "name": "Claude Code", "bin": "claude",
                "config_dir": "~/.claude", "default": True}
        with mock.patch.object(providers.shutil, "which", return_value=None), \
             mock.patch.object(Path, "is_dir", lambda self: True), \
             mock.patch.object(providers, "claude_desktop_installed", return_value=True):
            reason = providers._describe(spec)["reason"]
        self.assertIn("Claude Desktop is installed", reason)
        self.assertIn("Claude Code CLI", reason)
        self.assertIn("claude-code", reason, "must name the thing to install")
        self.assertNotIn("not on PATH", reason,
                         "a PATH diagnosis here sends them after the wrong bug")

    def test_without_desktop_the_PATH_diagnosis_is_still_given(self):
        spec = {"id": "claude", "name": "Claude Code", "bin": "claude",
                "config_dir": "~/.claude", "default": True}
        with mock.patch.object(providers.shutil, "which", return_value=None), \
             mock.patch.object(Path, "is_dir", lambda self: True), \
             mock.patch.object(providers, "claude_desktop_installed", return_value=False):
            reason = providers._describe(spec)["reason"]
        self.assertIn("not on PATH", reason)


class HarvestFailureIsExplained(unittest.TestCase):
    def setUp(self):
        providers._HARVEST_NOTE = ""
        self.addCleanup(setattr, providers, "_HARVEST_NOTE", "")

    def test_a_timeout_says_so(self):
        """A slow rc chain and a missing binary produced the same message. They
        have nothing in common as problems."""
        import subprocess as sp
        with mock.patch.object(providers.subprocess, "run",
                               side_effect=sp.TimeoutExpired("zsh", 25)):
            self.assertIsNone(providers._shell_path_once("/bin/zsh", True))
        self.assertIn("25s", providers._HARVEST_NOTE)

    def test_a_noisy_rc_file_says_so(self):
        class R: stdout = "welcome to my shell\nnot-a-path\n"; returncode = 0
        with mock.patch.object(providers.subprocess, "run", return_value=R()):
            self.assertIsNone(providers._shell_path_once("/bin/zsh", True))
        self.assertIn("printed output", providers._HARVEST_NOTE)

    def test_a_good_harvest_records_nothing(self):
        class R: stdout = "/opt/homebrew/bin:/usr/bin\n"; returncode = 0
        with mock.patch.object(providers.subprocess, "run", return_value=R()):
            got = providers._shell_path_once("/bin/zsh", True)
        self.assertEqual(got, "/opt/homebrew/bin:/usr/bin")
        self.assertEqual(providers._harvest_note(), "")

    def test_the_timeout_is_generous_enough_for_a_real_rc_chain(self):
        """8s was too tight: a first GUI launch pays for nvm + conda +
        oh-my-zsh, and timing out there reported a PATH problem on a machine
        that had none."""
        src = open("providers.py").read()
        self.assertIn("timeout=25", src)
        self.assertNotIn("timeout=8", src)


class BinaryPathOverride(unittest.TestCase):
    """The escape hatch a GUI user can actually reach. SUTRA_UI_CLAUDE_BIN
    means launchctl setenv plus a relaunch, and does not survive a reboot."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd); os.unlink(self.path)
        self._orig = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.path)
        os.environ.pop("SUTRA_UI_CLAUDE_BIN", None)
        self.addCleanup(self._restore)

    def _restore(self):
        providers.SETTINGS_PATH = self._orig
        if os.path.exists(self.path): os.unlink(self.path)
        os.environ.pop("SUTRA_UI_CLAUDE_BIN", None)

    def _an_executable(self):
        return providers.shutil.which("sh") or "/bin/sh"

    def test_a_stored_path_is_used(self):
        exe = self._an_executable()
        providers.set_provider_bin("claude", exe)
        self.assertEqual(providers._bin_for("claude", "claude"), exe)

    def test_a_missing_file_is_refused_at_SET_time(self):
        """Storing it would trade "cannot find it" for "found it and it will
        not run" -- a worse error, further from the mistake."""
        with self.assertRaises(ValueError):
            providers.set_provider_bin("claude", "/nope/claude")

    def test_a_non_executable_file_is_refused(self):
        with self.assertRaises(ValueError):
            providers.set_provider_bin("claude", self._orig_or_tmp())

    def _orig_or_tmp(self):
        fd, p = tempfile.mkstemp(); os.close(fd)
        self.addCleanup(lambda: os.path.exists(p) and os.unlink(p))
        return p

    def test_the_env_var_still_wins(self):
        """Tests and terminal launches rely on it; it stays first."""
        exe = self._an_executable()
        providers.set_provider_bin("claude", exe)
        os.environ["SUTRA_UI_CLAUDE_BIN"] = "/env/wins"
        self.assertEqual(providers._bin_for("claude", "claude"), "/env/wins")

    def test_clearing_falls_back_to_PATH_lookup(self):
        providers.set_provider_bin("claude", self._an_executable())
        providers.set_provider_bin("claude", None)
        self.assertEqual(providers._bin_for("claude", "claude"), "claude")

    def test_reading_the_override_does_not_recurse(self):
        """_bin_for reads the settings file directly. Going through
        load_settings() would be load_settings -> active_provider_detail ->
        discover_providers -> _describe -> _bin_for -> load_settings."""
        providers.set_provider_bin("claude", self._an_executable())
        providers.load_settings()          # would blow the stack if it recursed


if __name__ == "__main__":
    unittest.main(verbosity=2)
