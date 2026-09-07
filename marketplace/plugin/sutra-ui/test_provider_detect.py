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


class CodexStatusParse(unittest.TestCase):
    """The one line `codex login status` answers with.

    Verified against codex-cli 0.153.2 on 2026-09-04. The stakes are not
    cosmetic: subscription auth and an API key cost the operator completely
    different amounts for identical output, so a mode read wrongly here tells
    someone paying per token that their usage is included in a plan.
    """

    def test_chatgpt(self):
        self.assertEqual(providers._parse_codex_status("Logged in using ChatGPT"),
                         ("chatgpt", ""))

    def test_api_key_with_the_masked_stub(self):
        """The stub comes back in the CLI's own output. It is DISPLAYED and
        never stored -- there is no settings key for a Codex credential."""
        self.assertEqual(
            providers._parse_codex_status(
                "Logged in using an API key - sk-proj-***SMnIA"),
            ("api_key", "sk-proj-***SMnIA"))

    def test_an_em_dash_separator_is_still_an_api_key(self):
        """A cosmetic change upstream must not downgrade the MODE to unknown."""
        state, key = providers._parse_codex_status(
            "Logged in using an API key \u2014 sk-proj-***SMnIA")
        self.assertEqual((state, key), ("api_key", "sk-proj-***SMnIA"))

    def test_api_key_with_no_stub_is_still_an_api_key(self):
        """Losing the stub is cosmetic; losing the mode is a billing lie."""
        self.assertEqual(providers._parse_codex_status("Logged in using an API key"),
                         ("api_key", ""))

    def test_logged_out(self):
        self.assertEqual(providers._parse_codex_status("Not logged in"),
                         ("logged_out", ""))

    def test_empty_output_is_unknown_not_a_mode(self):
        self.assertEqual(providers._parse_codex_status(""), ("unknown", ""))
        self.assertEqual(providers._parse_codex_status("   \n "), ("unknown", ""))

    def test_unrelated_text_is_unknown_not_a_mode(self):
        for junk in ("error: could not read config",
                     "codex-cli 0.153.2",
                     "Usage: codex login [OPTIONS]"):
            self.assertEqual(providers._parse_codex_status(junk), ("unknown", ""),
                             "%r was read as a login state" % junk)


class CodexAuthProbe(unittest.TestCase):
    """codex_auth() around the subprocess. Never raises, never guesses."""

    def _run(self, out="", err="", code=0):
        return mock.Mock(stdout=out, stderr=err, returncode=code)

    def test_no_binary_when_codex_is_not_on_PATH(self):
        with mock.patch.object(providers, "provider_bin", return_value=None):
            a = providers.codex_auth()
        self.assertEqual(a["state"], "no_binary")
        self.assertIsNone(a["billing"])
        self.assertIn("PATH", a["detail"])

    def test_a_missing_binary_at_exec_time_is_also_no_binary(self):
        """which() found it, exec did not: it moved between the two calls."""
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run", side_effect=FileNotFoundError):
            a = providers.codex_auth()
        self.assertEqual(a["state"], "no_binary")

    def test_a_timeout_returns_cleanly_and_never_propagates(self):
        boom = providers.subprocess.TimeoutExpired(cmd="codex", timeout=10)
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run", side_effect=boom):
            a = providers.codex_auth()
        self.assertEqual(a["state"], "unknown")
        self.assertIn("did not finish", a["detail"])

    def test_an_os_error_returns_cleanly(self):
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run", side_effect=OSError("nope")):
            self.assertEqual(providers.codex_auth()["state"], "unknown")

    def test_the_billing_line_comes_from_this_module(self):
        """The panel must not re-derive the billing story and disagree."""
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run",
                               return_value=self._run("Logged in using ChatGPT")):
            self.assertEqual(providers.codex_auth()["billing"],
                             "usage included in your plan")
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run",
                               return_value=self._run(
                                   "Logged in using an API key - sk-proj-***SMnIA")):
            a = providers.codex_auth()
        self.assertEqual((a["state"], a["billing"], a["key_display"]),
                         ("api_key", "billed per token", "sk-proj-***SMnIA"))

    def test_a_recognised_line_wins_over_a_non_zero_exit(self):
        """Text decides the mode, not the exit code -- 0.153.2 exits 0 when
        logged in and learning what it exits when logged OUT would mean
        destroying the operator's live session to find out."""
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run",
                               return_value=self._run("Not logged in", code=1)):
            self.assertEqual(providers.codex_auth()["state"], "logged_out")

    def test_a_non_zero_exit_with_nothing_recognisable_is_unknown(self):
        """DELIBERATELY NOT no_binary (which the plan's test list asked for):
        the binary is right there and it ran, so claiming it is not installed
        would send the operator after a PATH problem that does not exist --
        the exact wrong diagnosis this file's header is about. The exit code
        goes in the detail instead."""
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run",
                               return_value=self._run("", "boom", code=2)):
            a = providers.codex_auth()
        self.assertEqual(a["state"], "unknown")
        self.assertIn("exit 2", a["detail"])

    def test_stderr_is_read_only_as_a_fallback(self):
        with mock.patch.object(providers, "provider_bin", return_value="/bin/codex"), \
             mock.patch.object(providers.subprocess, "run",
                               return_value=self._run("", "Not logged in")):
            self.assertEqual(providers.codex_auth()["state"], "logged_out")


class CodexIsConfiguredOnlyWhenSignedIn(unittest.TestCase):
    """~/.codex EXISTS after the first `codex` run whether or not anyone ever
    signed in -- it holds config.toml, session logs and sqlite state. Treating
    the directory as evidence of a login claimed codex was set up on a machine
    that had never authenticated."""

    SPEC = {"id": "codex", "name": "OpenAI Codex", "bin": "codex",
            "config_dir": "~/.codex", "default": False}

    def _describe(self, credential):
        with mock.patch.object(providers.shutil, "which", return_value="/bin/codex"), \
             mock.patch.object(Path, "is_dir", lambda self: True), \
             mock.patch.object(providers, "_codex_credential_present",
                               return_value=credential):
            return providers._describe(self.SPEC)

    def test_the_config_dir_alone_is_not_configured(self):
        self.assertFalse(self._describe(False)["configured"])

    def test_the_credential_file_is_configured(self):
        self.assertTrue(self._describe(True)["configured"])

    def test_the_signed_out_reason_does_not_claim_a_missing_directory(self):
        """The generic string would be wrong in a NEW way here: the directory
        is there, the login is not, and sending someone to look for a missing
        ~/.codex wastes the time the message was meant to save."""
        reason = self._describe(False)["reason"]
        self.assertNotIn("no config directory", reason)
        self.assertIn("nobody is signed in", reason)
        self.assertIn("auth.json", reason)

    def test_a_credential_check_reads_existence_only(self):
        """The file is a credential store. Nothing here opens it."""
        with mock.patch.object(providers, "open",
                               side_effect=AssertionError("opened auth.json"),
                               create=True):
            providers._codex_credential_present()


class CodexStaysUnselectable(unittest.TestCase):
    """Regression guard for the 2026-09-04 revert. codex was briefly added to
    ADAPTERS, which made the row render "Ready to use", accept the click, and
    then die at connect with code "no-adapter" -- the offer-a-choice-that-
    cannot-run failure providers.py exists to prevent. Refusing at SELECTION
    time is the better error until a CodexRuntime exists."""

    def test_codex_is_not_in_ADAPTERS(self):
        self.assertNotIn("codex", providers.ADAPTERS)

    def test_a_fully_installed_signed_in_codex_is_still_not_runnable(self):
        with mock.patch.object(providers.shutil, "which", return_value="/bin/codex"), \
             mock.patch.object(Path, "is_dir", lambda self: True), \
             mock.patch.object(providers, "_codex_credential_present", return_value=True):
            p = providers._describe(CodexIsConfiguredOnlyWhenSignedIn.SPEC)
        self.assertTrue(p["installed"])
        self.assertTrue(p["configured"])
        self.assertFalse(p["runnable"])
        self.assertFalse(p["adapter"])

    def test_the_no_adapter_reason_is_not_the_stale_claude_only_string(self):
        """It said "this panel drives Claude's stream-json protocol only",
        which stopped being true when the DeepSeek ACP adapter landed --
        DeepSeek renders as ready to use two rows away in the same list, so
        the row contradicted the screen it was printed on."""
        with mock.patch.object(providers.shutil, "which", return_value="/bin/codex"), \
             mock.patch.object(Path, "is_dir", lambda self: True), \
             mock.patch.object(providers, "_codex_credential_present", return_value=True):
            reason = providers._describe(
                CodexIsConfiguredOnlyWhenSignedIn.SPEC)["reason"]
        self.assertNotIn("stream-json protocol only", reason)
        self.assertIn("stream-json", reason)
        self.assertIn("ACP", reason)
        self.assertIn("0.153.2", reason)


class DeepSeekNeedsAKeyToBeRunnable(unittest.TestCase):
    """The same lie the codex class above is about, one row further down.

    `configured` for deepseek was `~/.deepseek` is_dir(), which is true after
    the CLI has run once and says nothing about a key. DeepSeek has no
    subscription to inherit -- every request is billed against a key -- so the
    row rendered "Ready to use", accepted the click, and then died at ws
    connect with "DEEPSEEK_API_KEY is not set in the server environment. Export
    it and restart the server." Refusing at SELECTION time is the better error,
    and it is the one thing that has to be true for the sign-in row to mean
    anything.
    """

    SPEC = {"id": "deepseek", "name": "DeepSeek", "bin": "deepseek",
            "config_dir": "~/.deepseek", "default": False}

    def _describe(self, keyed, installed=True):
        with mock.patch.object(providers.shutil, "which",
                               return_value="/bin/deepseek" if installed else None), \
             mock.patch.object(Path, "is_dir", lambda self: True), \
             mock.patch.object(providers, "_deepseek_key_present",
                               return_value=keyed):
            return providers._describe(self.SPEC)

    def test_the_config_dir_alone_is_not_configured(self):
        self.assertFalse(self._describe(False)["configured"])

    def test_a_resolvable_key_is_configured(self):
        self.assertTrue(self._describe(True)["configured"])

    def test_an_unkeyed_deepseek_is_not_runnable_even_with_the_cli(self):
        p = self._describe(False)
        self.assertTrue(p["installed"])
        self.assertTrue(p["adapter"])          # the ACP adapter exists
        self.assertFalse(p["runnable"])        # and it still cannot answer

    def test_a_keyed_installed_deepseek_is_runnable(self):
        self.assertTrue(self._describe(True)["runnable"])

    def test_the_unkeyed_reason_does_not_send_anyone_to_a_directory(self):
        """~/.deepseek stopped being evidence of anything the moment the key
        became the configured signal. Naming it would waste the time the
        message exists to save -- the mistake the codex signed-out string was
        rewritten to avoid."""
        reason = self._describe(False)["reason"]
        self.assertNotIn(".deepseek", reason)
        self.assertNotIn("config directory", reason)

    def test_the_unkeyed_reason_names_every_way_in(self):
        """All THREE sources, not just the two variables. "no key is saved on
        this Mac" was true and no help to someone asking where a key lives --
        the same failure as the ~/.deepseek string it replaced."""
        import deepseek_auth
        reason = self._describe(False)["reason"]
        self.assertIn("/bin/deepseek", reason)            # the CLI half is done
        for var in providers.DEEPSEEK_KEY_ENVS:
            self.assertIn(var, reason)
        self.assertIn(deepseek_auth.KEYCHAIN_SERVICE, reason)
        self.assertIn(deepseek_auth.KEYCHAIN_ACCOUNT, reason)

    def test_the_render_path_does_not_claim_to_have_opened_the_keychain(self):
        """_describe() decides from the settings marker. Asserting "the keychain
        holds no item" from a path that never opened it is the "configured means
        the directory exists" mistake in a new coat."""
        reason = self._describe(False)["reason"]
        self.assertNotIn("keychain holds no item", reason)
        self.assertIn("settings.json", reason)

    def test_a_key_with_no_cli_says_the_key_half_is_done(self):
        """Two independent requirements, so the row must not report the one that
        is satisfied as missing."""
        reason = self._describe(True, installed=False)["reason"]
        self.assertIn("not on PATH", reason)
        self.assertIn("--acp", reason)
        self.assertNotIn("no API key", reason)

    def test_neither_half_reports_both(self):
        reason = self._describe(False, installed=False)["reason"]
        self.assertIn("not on PATH", reason)
        self.assertIn("no API key", reason)
        self.assertNotIn("no config directory", reason)

    def test_readiness_never_reads_the_keychain(self):
        """_describe() runs four times per load_settings(), and every fs/tree,
        fs/read, ws_chat connect and settings GET goes through that. A
        Security.framework round trip on that path would tax requests that
        never asked about DeepSeek."""
        import deepseek_auth
        with mock.patch.object(deepseek_auth, "_store",
                               side_effect=AssertionError("read the keychain")), \
             mock.patch.object(providers.shutil, "which", return_value="/bin/deepseek"), \
             mock.patch.object(Path, "is_dir", lambda self: True):
            providers._describe(self.SPEC)

    def test_an_unkeyed_deepseek_cannot_be_selected(self):
        """save_settings refuses a provider that is not runnable, so the gate
        above is what makes the row unclickable rather than a UI detail."""
        with mock.patch.object(providers, "provider_by_id",
                               return_value=dict(self._describe(False))):
            with self.assertRaises(ValueError) as caught:
                providers.save_settings(provider="deepseek")
        self.assertIn("not runnable", str(caught.exception))

    def test_the_catalogue_entry_is_the_one_this_class_describes(self):
        """A drifted catalogue would make every assertion above vacuous."""
        live = [s for s in providers._CATALOG if s["id"] == "deepseek"]
        self.assertEqual(len(live), 1)
        entry = live[0]
        # The identity fields _describe() actually reads, compared exactly --
        # a change to any of them still trips this guard.
        self.assertEqual({k: entry[k] for k in self.SPEC}, self.SPEC)
        # The declarations added when models became per-provider. Pinned here
        # by their VALUES rather than folded into SPEC: SPEC referencing
        # providers._DEEPSEEK_MODELS would compare a constant with itself and
        # quietly stop guarding anything.
        self.assertEqual(entry["model_flag"], "-m")
        self.assertEqual(entry["usage_kind"], "balance")
        self.assertEqual([m["id"] for m in entry["models"]],
                         ["", "deepseek-v4-pro", "deepseek-v4-flash",
                          "deepseek-v4-flash-vision-exp"])
        # The declarations added when TURN OPTIONS and PERMISSION MODES became
        # per-provider. Pinned by value for the same reason as the three above,
        # and these two matter more than most: an empty turn_options is the
        # whole reason a DeepSeek pane stops rendering five controls the server
        # would discard, and the three modes are the ones ACP can actually
        # enforce. A well-meaning "fill these in" would put the no-op controls
        # straight back, so the emptiness is asserted, not assumed.
        self.assertEqual(entry["turn_options"], ())
        self.assertEqual(entry["permission_modes"],
                         ("plan", "acceptEdits", "bypassPermissions"))
        # Nothing may appear that neither half above accounts for, which is
        # what the old exact-equality assertion was really protecting.
        self.assertEqual(set(entry) - set(self.SPEC),
                         {"models", "model_flag", "usage_kind",
                          "turn_options", "permission_modes"})

    def test_deepseek_is_LAST_in_the_catalogue(self):
        """LOAD-BEARING FOR THE UI, which is why it is asserted here rather
        than left as an incidental fact.

        The sign-in block renders after the DEFAULT PROVIDER radiogroup, not
        inside provRow() -- a row is a <button role="radio">, and an <input>
        plus two buttons nested in one is invalid markup whose clicks would
        toggle the radio. "After the group" reads as "under the DeepSeek row"
        only while deepseek is the last row. Reorder the catalogue and the
        sign-in silently detaches from the row it belongs to, so this test is
        the tripwire for that.
        """
        self.assertEqual(providers._CATALOG[-1]["id"], "deepseek")


if __name__ == "__main__":
    unittest.main(verbosity=2)
