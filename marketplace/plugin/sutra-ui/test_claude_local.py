"""Identity and workspace come from Claude, not from a hardcoded guess.

The panel shipped a literal "TC" avatar (a developer's initials, wrong for
every other operator) and defaulted the agent's cwd to ~/sutra-ui-workspace, a
directory nobody works in. Both facts were already known to Claude Code.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import claude_local
import providers


class Initials(unittest.TestCase):
    def test_one_word_name_gives_one_letter(self):
        """Not padded to two. "Tishant" -> "T"; "TI" looks like a typo, and
        inventing a second letter is inventing identity."""
        self.assertEqual(claude_local.initials_for("Tishant"), "T")

    def test_two_words_give_two_letters(self):
        self.assertEqual(claude_local.initials_for("Ada Lovelace"), "AL")

    def test_hyphenated_and_extra_words_cap_at_two(self):
        self.assertEqual(claude_local.initials_for("Jean-Luc Picard"), "JP")
        self.assertEqual(claude_local.initials_for("A B C D"), "AB")

    def test_falls_back_to_the_email_local_part(self):
        self.assertEqual(claude_local.initials_for("", "jo@example.com"), "J")

    def test_nothing_known_yields_nothing_invented(self):
        self.assertEqual(claude_local.initials_for("", ""), "")
        self.assertEqual(claude_local.initials_for(None, None), "")


class Account(unittest.TestCase):
    def _with_claude_json(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh)
        self.addCleanup(os.unlink, path)
        return mock.patch.object(claude_local, "CLAUDE_JSON", path)

    def test_reads_the_signed_in_account(self):
        with self._with_claude_json({"oauthAccount": {
                "displayName": "Ada Lovelace", "emailAddress": "ada@example.com",
                "organizationName": "Analytical Engines"}}):
            a = claude_local.account()
        self.assertEqual(a["display_name"], "Ada Lovelace")
        self.assertEqual(a["initials"], "AL")
        self.assertEqual(a["email"], "ada@example.com")

    def test_missing_file_is_unknown_not_an_error(self):
        """A machine with no Claude config must render an unknown identity, not
        take the page down and not show a placeholder."""
        with mock.patch.object(claude_local, "CLAUDE_JSON", "/nonexistent/x.json"):
            self.assertIsNone(claude_local.account())

    def test_corrupt_file_is_unknown_not_an_error(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            fh.write("{not json")
        self.addCleanup(os.unlink, path)
        with mock.patch.object(claude_local, "CLAUDE_JSON", path):
            self.assertIsNone(claude_local.account())

    def test_signed_out_shape_is_unknown(self):
        with self._with_claude_json({"oauthAccount": {}}):
            self.assertIsNone(claude_local.account())
        with self._with_claude_json({}):
            self.assertIsNone(claude_local.account())


class RecentWorkspace(unittest.TestCase):
    def test_skips_a_directory_that_no_longer_exists(self):
        with mock.patch("session_reader.list_sessions",
                        return_value=[{"cwd": "/gone/forever"},
                                      {"cwd": os.path.expanduser("~")}]):
            self.assertEqual(claude_local.recent_workspace(),
                             os.path.expanduser("~"))

    def test_refuses_a_path_outside_the_permitted_root(self):
        """This value becomes the agent's cwd. Widening that boundary because
        another program's config pointed outside $HOME would be an escalation."""
        with mock.patch("session_reader.list_sessions",
                        return_value=[{"cwd": "/etc"},
                                      {"cwd": os.path.expanduser("~")}]):
            got = claude_local.recent_workspace(providers.workdir_allowed)
        self.assertEqual(got, os.path.expanduser("~"))

    def test_no_sessions_is_none_not_a_guess(self):
        with mock.patch("session_reader.list_sessions", return_value=[]):
            self.assertIsNone(claude_local.recent_workspace())

    def test_a_broken_reader_does_not_propagate(self):
        with mock.patch("session_reader.list_sessions", side_effect=OSError("boom")):
            self.assertIsNone(claude_local.recent_workspace())


class WorkdirDefault(unittest.TestCase):
    """load_settings() precedence: stored > SUTRA_UI_WORKDIR > Claude's most
    recent workspace > ~/sutra-ui-workspace."""

    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("SUTRA_UI_WORKDIR", None)
        fd, self.settings_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.settings_path)
        # providers.SETTINGS_PATH is computed at IMPORT time, so setting
        # SUTRA_UI_SETTINGS here would do nothing and every test in this class
        # would silently read the developer's real settings file -- passing or
        # failing on whatever that machine happens to contain. Patch the
        # resolved constant instead.
        from pathlib import Path as _P
        patcher = mock.patch.object(providers, "SETTINGS_PATH", _P(self.settings_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.clear(); os.environ.update(self._env)
        if os.path.exists(self.settings_path):
            os.unlink(self.settings_path)

    def test_claude_recent_beats_the_synthetic_default(self):
        home = os.path.expanduser("~")
        with mock.patch("claude_local.recent_workspace", return_value=home):
            s = providers.load_settings()
        self.assertEqual(s["workdir"], home)
        self.assertEqual(s["workdir_source"], "claude_recent")

    def test_falls_back_when_claude_knows_nothing(self):
        with mock.patch("claude_local.recent_workspace", return_value=None):
            s = providers.load_settings()
        self.assertEqual(s["workdir"],
                         os.path.expanduser(providers.DEFAULT_WORKDIR))
        self.assertEqual(s["workdir_source"], "default")

    def test_env_still_wins_over_claude(self):
        os.environ["SUTRA_UI_WORKDIR"] = os.path.expanduser("~")
        with mock.patch("claude_local.recent_workspace",
                        return_value="/should/not/be/used") as m:
            s = providers.load_settings()
        self.assertEqual(s["workdir_source"], "env")
        m.assert_not_called()

    def test_a_stored_workdir_is_never_overridden(self):
        want = os.path.expanduser("~")
        with open(self.settings_path, "w") as fh:
            json.dump({"workdir": want}, fh)
        with mock.patch("claude_local.recent_workspace",
                        return_value="/should/not/be/used") as m:
            s = providers.load_settings()
        self.assertEqual(s["workdir"], want)
        self.assertEqual(s["workdir_source"], "stored")
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
