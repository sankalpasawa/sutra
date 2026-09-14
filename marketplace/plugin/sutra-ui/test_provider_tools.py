"""test_provider_tools.py -- CLI versions, and who is allowed to replace them.

The dangerous half of this feature is the update, so most of this file is about
what it REFUSES:

  - a Homebrew binary, always. A formula's files belong to brew, and a
    `brew upgrade` later would undo whatever we did.
  - anything at all while a chat is open on that provider. Replacing the binary
    under a running turn kills it.
  - `claude update` on a `claude` that Claude Code's own installer did not put
    there.

The other half is that an offline Mac degrades to "we do not know" -- a null
version and a sentence -- rather than to a spinner, an error or a guess.

NOTHING HERE RUNS npm, `claude update` OR ANY REAL INSTALL. Every subprocess is
mocked, and SETTINGS_PATH is rebound to a temp dir so even a stray write lands
nowhere near ~/.sutra-ui.

Run: python -m pytest test_provider_tools.py -q
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import providers   # noqa: E402


def _completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


class ToolsBase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sutra-tools-test-")
        self._old = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.dir) / "settings.json"
        # THE ENV VAR TOO (2026-09-14). codex_install.prefix() derives Sutra's own
        # install prefix from SUTRA_UI_SETTINGS, not from this module attribute, so
        # patching the attribute alone left the prefix pointing at whatever another
        # test module had exported at import time -- passing alone, failing in a full
        # run, and asserting nothing about the isolation it exists to prove.
        self._old_env = os.environ.get("SUTRA_UI_SETTINGS")
        os.environ["SUTRA_UI_SETTINGS"] = str(providers.SETTINGS_PATH)
        providers.invalidate_tool_caches()
        # Any chat count left behind by another test would silently turn every
        # update below into CHAT_RUNNING.
        for pid in list(providers.chats_running()):
            while providers.chats_running(pid):
                providers.chat_finished(pid)

    def tearDown(self):
        providers.SETTINGS_PATH = self._old
        if self._old_env is None:
            os.environ.pop("SUTRA_UI_SETTINGS", None)
        else:
            os.environ["SUTRA_UI_SETTINGS"] = self._old_env
        providers.invalidate_tool_caches()
        shutil.rmtree(self.dir, ignore_errors=True)

    def fake_binary(self, name="claude"):
        """A real executable file, so os.stat and os.access answer truthfully."""
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)
        return path


class ParsingVersions(unittest.TestCase):

    def test_the_real_version_lines_parse(self):
        """Measured 2026-09-14: these are exactly what the CLIs print."""
        self.assertEqual(providers.parse_version("2.1.270 (Claude Code)"),
                         "2.1.270")
        self.assertEqual(providers.parse_version("codex-cli 0.154.0"), "0.154.0")
        self.assertEqual(providers.parse_version("1.3.2"), "1.3.2")

    def test_junk_parses_to_none_rather_than_to_a_wrong_number(self):
        for junk in ("", None, "no version here", "vNEXT"):
            self.assertIsNone(providers.parse_version(junk))

    def test_comparison_orders_the_way_a_human_expects(self):
        self.assertTrue(providers.version_at_least("2.1.270", "2.1.247"))
        self.assertTrue(providers.version_at_least("2.1.247", "2.1.247"))
        self.assertFalse(providers.version_at_least("2.1.9", "2.1.247"),
                         "a string compare would call 2.1.9 newer than 2.1.247")
        self.assertTrue(providers.version_at_least("3.0.0", "2.9.9"))

    def test_a_prerelease_sorts_below_its_release(self):
        self.assertFalse(providers.version_at_least("2.0.0-rc1", "2.0.0"))
        self.assertTrue(providers.version_at_least("2.0.0", "2.0.0-rc1"))

    def test_an_unparseable_version_is_never_reported_as_fine(self):
        """"cannot confirm" must not collapse into "up to date"."""
        self.assertFalse(providers.version_at_least(None, "2.1.247"))
        self.assertFalse(providers.version_at_least("nonsense", "2.1.247"))
        self.assertFalse(providers.version_at_least("2.1.247", "nonsense"))


class WhoOwnsTheBinary(ToolsBase):

    def test_homebrew_is_recognised_through_its_symlink(self):
        """`brew --prefix/bin/x` is a symlink into Cellar, which realpath
        follows -- so the Cellar marker is the reliable one."""
        for path in ("/opt/homebrew/Cellar/codex/0.1/bin/codex",
                     "/usr/local/Cellar/codex/0.1/bin/codex",
                     "/opt/homebrew/bin/codex"):
            self.assertEqual(providers._install_kind("codex", path), "homebrew",
                             path)

    def test_claudes_native_install_is_recognised(self):
        self.assertEqual(
            providers._install_kind(
                "claude", os.path.expanduser(
                    "~/.local/share/claude/versions/2.1.270")),
            "claude-self")

    def test_a_global_npm_install_is_recognised(self):
        self.assertEqual(
            providers._install_kind("codex",
                                    "/usr/local/lib/node_modules/@openai/codex/bin/codex.js"),
            "npm-global")

    def test_nothing_installed_has_no_owner(self):
        self.assertIsNone(providers._install_kind("codex", None))


class WhatTheButtonWouldDo(ToolsBase):

    def test_homebrew_is_always_manual(self):
        for pid in ("claude", "codex", "deepseek"):
            self.assertEqual(providers._update_action(pid, "homebrew"), "manual")

    def test_claude_is_updatable_only_from_its_own_installer(self):
        self.assertEqual(providers._update_action("claude", "claude-self"),
                         "claude-update")
        for kind in ("npm-global", "other", None):
            self.assertEqual(providers._update_action("claude", kind), "manual")

    def test_a_global_npm_codex_is_still_updatable(self):
        """The --prefix design's whole point: Sutra fetches its OWN copy, so
        the operator's install is never written to and their terminal keeps
        resolving exactly what it resolves today."""
        self.assertEqual(providers._update_action("codex", "npm-global"),
                         "sutra-npm")
        self.assertEqual(providers._update_action("deepseek", "sutra"),
                         "sutra-npm")


class TheReport(ToolsBase):

    def rows(self, version="2.1.270", latest="2.1.270", path=None):
        binp = path or self.fake_binary()
        with mock.patch("providers.provider_bin", return_value=binp), \
             mock.patch("providers.installed_version", return_value=version), \
             mock.patch("providers.npm_latest", return_value=latest):
            return {r["id"]: r for r in providers.tools_report()}

    def test_one_row_per_provider_with_a_cli(self):
        rows = self.rows()
        self.assertEqual(sorted(rows), ["claude", "codex", "deepseek"])
        self.assertNotIn("gemini", rows,
                         "a provider with no adapter has no version to report")

    def test_every_row_has_the_contract_fields(self):
        for row in self.rows().values():
            for key in ("id", "name", "bin", "installed_version",
                        "latest_version", "minimum", "update_available",
                        "too_old", "managed_by_sutra", "update_command",
                        "note"):
                self.assertIn(key, row)

    def test_the_declared_minimums_are_the_spec_numbers(self):
        self.assertEqual(providers.PROVIDER_MIN_VERSIONS,
                         {"claude": "2.1.247", "codex": "0.144.4",
                          "deepseek": "1.3.2"})

    def test_too_old_is_reported_and_nothing_is_blocked(self):
        """A warning, never a refusal: Sutra has no evidence the older build is
        broken, and refusing on a number it did not measure would be inventing
        a failure."""
        with mock.patch("providers._install_kind", return_value="claude-self"):
            row = self.rows(version="2.1.100")["claude"]
        self.assertTrue(row["too_old"])
        self.assertTrue(row["can_update"], "too old must not disable the button")
        self.assertIn("2.1.247", row["note"])
        self.assertIn("Nothing is blocked", row["note"])

    def test_a_newer_release_sets_update_available(self):
        row = self.rows(version="2.1.247", latest="2.1.270")["claude"]
        self.assertTrue(row["update_available"])

    def test_an_older_release_on_the_registry_does_not(self):
        row = self.rows(version="2.1.270", latest="2.1.247")["claude"]
        self.assertFalse(row["update_available"])

    def test_offline_degrades_to_unknown_not_to_an_error(self):
        row = self.rows(latest=None)["claude"]
        self.assertIsNone(row["latest_version"])
        self.assertFalse(row["update_available"],
                         "unknown must never read as an update being available")
        self.assertIn("could not be reached", row["note"])

    def test_a_missing_binary_says_so_and_offers_no_command(self):
        with mock.patch("providers.provider_bin", return_value=None), \
             mock.patch("providers.npm_latest", return_value="1.3.2"):
            row = {r["id"]: r for r in providers.tools_report()}["deepseek"]
        self.assertIsNone(row["installed_version"])
        self.assertFalse(row["can_update"])
        self.assertIsNone(row["update_command"])
        self.assertIn("not on this Mac", row["note"])

    def test_a_live_chat_marks_the_row_busy(self):
        providers.chat_started("claude")
        try:
            row = self.rows()["claude"]
            self.assertTrue(row["busy"])
            self.assertFalse(row["can_update"])
        finally:
            providers.chat_finished("claude")


class TheChatRegister(ToolsBase):

    def test_it_counts_rather_than_flags(self):
        """Several panes can be open on one provider; a boolean would be
        cleared by the first of them to finish."""
        providers.chat_started("claude")
        providers.chat_started("claude")
        self.assertEqual(providers.chats_running("claude"), 2)
        providers.chat_finished("claude")
        self.assertEqual(providers.chats_running("claude"), 1)
        providers.chat_finished("claude")
        self.assertEqual(providers.chats_running("claude"), 0)

    def test_a_double_release_cannot_go_negative(self):
        providers.chat_finished("codex")
        providers.chat_finished("codex")
        self.assertEqual(providers.chats_running("codex"), 0)

    def test_the_lease_releases_even_on_a_crash(self):
        """A disconnected pane must not leave a provider marked busy forever."""
        with self.assertRaises(RuntimeError):
            with providers.chat_lease("deepseek"):
                self.assertEqual(providers.chats_running("deepseek"), 1)
                raise RuntimeError("pane died")
        self.assertEqual(providers.chats_running("deepseek"), 0)

    def test_providers_do_not_share_a_count(self):
        providers.chat_started("claude")
        try:
            self.assertEqual(providers.chats_running("codex"), 0)
        finally:
            providers.chat_finished("claude")


class TheUpdateRefusals(ToolsBase):

    def test_an_unknown_provider_is_refused(self):
        with self.assertRaises(providers.ToolUpdateError) as ctx:
            providers.update_tool("gemini")
        self.assertEqual(ctx.exception.code, "UNKNOWN_PROVIDER")

    def test_a_running_chat_is_refused_before_anything_else_is_checked(self):
        providers.chat_started("claude")
        try:
            with mock.patch("subprocess.run",
                            side_effect=AssertionError("spawned anyway")):
                with self.assertRaises(providers.ToolUpdateError) as ctx:
                    providers.update_tool("claude")
        finally:
            providers.chat_finished("claude")
        self.assertEqual(ctx.exception.code, "CHAT_RUNNING")

    def test_a_missing_binary_is_refused(self):
        with mock.patch("providers.provider_bin", return_value=None):
            with self.assertRaises(providers.ToolUpdateError) as ctx:
                providers.update_tool("codex")
        self.assertEqual(ctx.exception.code, "NOT_INSTALLED")

    def test_homebrew_is_never_touched(self):
        """THE rule. No subprocess may run at all."""
        brew = "/opt/homebrew/Cellar/codex/0.1/bin/codex"
        with mock.patch("providers.provider_bin", return_value=brew), \
             mock.patch("providers.installed_version", return_value="0.1.0"), \
             mock.patch("subprocess.run",
                        side_effect=AssertionError("touched Homebrew")):
            with self.assertRaises(providers.ToolUpdateError) as ctx:
                providers.update_tool("codex")
        self.assertEqual(ctx.exception.code, "NOT_OURS")
        self.assertIn("brew upgrade", str(ctx.exception))

    def test_claude_from_somewhere_else_is_refused(self):
        other = "/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js"
        with mock.patch("providers.provider_bin", return_value=other), \
             mock.patch("providers.installed_version", return_value="2.1.270"), \
             mock.patch("subprocess.run",
                        side_effect=AssertionError("ran claude update")):
            with self.assertRaises(providers.ToolUpdateError) as ctx:
                providers.update_tool("claude")
        self.assertEqual(ctx.exception.code, "NOT_OURS")

    def test_no_npm_is_refused_with_the_package_named(self):
        managed = os.path.join(self.dir, "providers", "codex", "node_modules",
                               ".bin", "codex")
        with mock.patch("providers.provider_bin", return_value=managed), \
             mock.patch("providers.installed_version", return_value="0.153.2"), \
             mock.patch("providers._npm_bin", return_value=None), \
             mock.patch("providers._install_kind", return_value="sutra"):
            with self.assertRaises(providers.ToolUpdateError) as ctx:
                providers.update_tool("codex")
        self.assertEqual(ctx.exception.code, "NO_NPM")
        self.assertIn("@openai/codex", str(ctx.exception))


class TheUpdateHappyPaths(ToolsBase):

    def test_claude_runs_its_own_updater_and_reports_both_versions(self):
        binp = self.fake_binary("claude")
        versions = iter(["2.1.247", "2.1.270"])
        with mock.patch("providers.provider_bin", return_value=binp), \
             mock.patch("providers._install_kind", return_value="claude-self"), \
             mock.patch("providers.installed_version",
                        side_effect=lambda *a, **k: next(versions)), \
             mock.patch("subprocess.run",
                        return_value=_completed("Updated to 2.1.270")) as run:
            out = providers.update_tool("claude")
        self.assertEqual(run.call_args[0][0], [binp, "update"])
        self.assertEqual(out["version_before"], "2.1.247")
        self.assertEqual(out["version_after"], "2.1.270")
        self.assertTrue(out["changed"])
        self.assertIn("Updated to 2.1.270", out["log"])

    def test_an_already_current_claude_reports_no_change(self):
        binp = self.fake_binary("claude")
        with mock.patch("providers.provider_bin", return_value=binp), \
             mock.patch("providers._install_kind", return_value="claude-self"), \
             mock.patch("providers.installed_version", return_value="2.1.270"), \
             mock.patch("subprocess.run", return_value=_completed("up to date")):
            out = providers.update_tool("claude")
        self.assertFalse(out["changed"])
        self.assertEqual(out["version_before"], out["version_after"])

    def test_a_failing_updater_is_reported_with_its_own_words(self):
        binp = self.fake_binary("claude")
        with mock.patch("providers.provider_bin", return_value=binp), \
             mock.patch("providers._install_kind", return_value="claude-self"), \
             mock.patch("providers.installed_version", return_value="2.1.247"), \
             mock.patch("subprocess.run",
                        return_value=_completed("", 1, "permission denied")):
            with self.assertRaises(providers.ToolUpdateError) as ctx:
                providers.update_tool("claude")
        self.assertEqual(ctx.exception.code, "UPDATE_FAILED")
        self.assertIn("permission denied", str(ctx.exception))

    def test_codex_installs_into_sutras_own_prefix_and_never_globally(self):
        import codex_install
        managed = str(codex_install.managed_bin())
        os.makedirs(os.path.dirname(managed), exist_ok=True)
        with open(managed, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(managed, 0o755)
        with mock.patch("providers.provider_bin", return_value=managed), \
             mock.patch("providers._install_kind", return_value="sutra"), \
             mock.patch("providers._npm_bin", return_value="/bin/npm"), \
             mock.patch("providers.npm_latest", return_value="0.154.0"), \
             mock.patch("providers.installed_version",
                        side_effect=["0.153.2", "0.154.0"]), \
             mock.patch("providers.set_provider_bin", return_value=managed), \
             mock.patch("subprocess.run", return_value=_completed("added 1")) as run:
            out = providers.update_tool("codex")
        argv = run.call_args[0][0]
        self.assertEqual(argv[:3], ["/bin/npm", "install",
                                    "@openai/codex@0.154.0"])
        self.assertIn("--prefix", argv)
        self.assertNotIn("-g", argv, "a global install would replace the "
                                     "operator's own copy")
        self.assertNotIn("--global", argv)
        self.assertEqual(out["version_after"], "0.154.0")

    def test_the_prefix_is_derived_from_the_settings_path(self):
        """So a test (or SUTRA_UI_SETTINGS) can never install into the real
        ~/.sutra-ui."""
        import codex_install
        # ASKED OF THE MODULE codex_install ACTUALLY USES (2026-09-14). A full-suite
        # run can leave two `providers` module objects in sys.modules (a staged or
        # payload copy imported under the same name), and then patching the one this
        # file imported says nothing about the one codex_install reads. The invariant
        # is "the install prefix follows the settings file", so ask it that way, and
        # separately prove it is nowhere near the operator's real home.
        seen = codex_install.providers.SETTINGS_PATH.parent
        self.assertEqual(codex_install.prefix(), seen / "providers" / "codex")
        self.assertFalse(
            str(codex_install.prefix()).startswith(str(Path.home() / ".sutra-ui")),
            "a test must never resolve the real ~/.sutra-ui install prefix")

    def test_nothing_is_registered_when_the_new_binary_does_not_answer(self):
        import codex_install
        managed = str(codex_install.managed_bin())
        os.makedirs(os.path.dirname(managed), exist_ok=True)
        with mock.patch("providers.provider_bin", return_value="/bin/codex"), \
             mock.patch("providers._install_kind", return_value="sutra"), \
             mock.patch("providers._npm_bin", return_value="/bin/npm"), \
             mock.patch("providers.npm_latest", return_value="0.154.0"), \
             mock.patch("providers.installed_version",
                        side_effect=["0.153.2", None]), \
             mock.patch("providers.set_provider_bin",
                        side_effect=AssertionError("registered a dud")), \
             mock.patch("subprocess.run", return_value=_completed("added 1")):
            with self.assertRaises(providers.ToolUpdateError) as ctx:
                providers.update_tool("codex")
        self.assertEqual(ctx.exception.code, "VERIFY_FAILED")


if __name__ == "__main__":
    unittest.main()
