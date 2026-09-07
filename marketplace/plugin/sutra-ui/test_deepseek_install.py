"""Installing the DeepSeek CLI: what must happen, and what must never.

THE BUG THIS CLOSES (founder screenshot, 2026-09-07). Entering a DeepSeek key
produced "DeepSeek accepted the key and it is saved on this Mac" printed
directly beneath a provider row reading "Not installed on this Mac". Both
sentences were true. DeepSeek needs a key AND the `deepseek` CLI -- Sutra
answers a message by spawning `<bin> --acp` -- and the panel only ever supplied
the key. test_deepseek_auth's SavedMessageTellsTheTruth stopped the message
lying about it; this module is about actually fetching the thing.

FOUR FAILURES THESE TESTS EXIST TO PREVENT:

  1. `npm install -g`. On a Homebrew or system node the global prefix is
     root-owned, so a global install fails with EACCES -- and the two ways out
     are sudo (a GUI app must not ask) or permanently repointing the operator's
     npm prefix. The whole design is --prefix into a directory Sutra owns, and
     test_the_install_is_never_global is the guard on it.

  2. A registered path with nothing behind it. `provider_bins` is what makes
     the row flip without a restart; writing it when the binary is not there,
     or not executable, trades "not installed" for "installed and will not
     run", which is a worse error further from the mistake.

  3. A refusal that blames the wrong thing. npm exiting non-zero, npm being
     absent, and npm succeeding while publishing no `deepseek` command are
     three different problems with three different fixes, and each has to name
     its own.

  4. A floating version. acp_runtime.py's transport was read out of
     @sluisr/deepseek-cli@1.3.2 and its docstrings cite wire measurements
     against that build. Installing `latest` ships an adapter verified against
     one version pointed at another.

NOTHING HERE RUNS THE REAL npm OR REACHES THE NETWORK. A stub script stands in,
records the argv it was called with, and populates the prefix the way npm
would. PATH is replaced for the duration, so a `deepseek` that happens to be
installed on the machine running these tests cannot make them pass.
"""
import json
import threading
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import deepseek_install
import providers

#: A stand-in for npm. Records its argv, then does what npm does to a prefix:
#: creates node_modules/.bin and drops the executable the package publishes.
#:
#: EVERY COMMAND IS ABSOLUTE, and that is not fussiness. The first draft called
#: bare `mkdir`/`chmod`, so the stub inherited whatever PATH the module under
#: test had just been handed -- and under `unittest discover`, sharing a process
#: with ~900 other tests, it ran with a PATH that had neither. The stub then
#: "succeeded" (its trailing `exit 0` masked the failures), produced no binary,
#: and eleven tests reported NO_BINARY: a fixture failure wearing a product
#: failure's clothes. A test stub must not depend on the environment its
#: subject is manipulating.
_FAKE_NPM = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
prefix=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--prefix" ]; then prefix="$2"; fi
  shift
done
[ -n "$prefix" ] || { echo "no --prefix" >&2; exit 1; }
/bin/mkdir -p "$prefix/node_modules/.bin"
printf '#!/bin/sh\necho fake-deepseek\n' > "$prefix/node_modules/.bin/deepseek"
/bin/chmod +x "$prefix/node_modules/.bin/deepseek"
echo "added 1 package"
exit 0
"""

#: npm that fails the way a real one does: a diagnosis on stderr and a non-zero
#: exit. The message is the only actionable thing in that failure.
_FAKE_NPM_FAILS = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
echo "npm error code ETARGET" >&2
echo "npm error notarget No matching version found for the package." >&2
exit 1
"""

#: npm that reports success and publishes nothing. Package renamed its command.
_FAKE_NPM_EMPTY = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
prefix=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--prefix" ]; then prefix="$2"; fi
  shift
done
/bin/mkdir -p "$prefix/node_modules/.bin"
echo "added 1 package"
exit 0
"""


class _Base(unittest.TestCase):
    """A settings DIRECTORY of our own, and a PATH with nothing real on it.

    A directory rather than a bare temp file, unlike test_deepseek_auth's base:
    deepseek_install.prefix() is SETTINGS_PATH.parent/providers/deepseek, so a
    settings file in /tmp would put the install tree in /tmp/providers. The two
    are one unit and the test has to move them together.
    """

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self._orig_settings = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = self.home / "settings.json"

        self.binroot = self.home / "bin"
        self.binroot.mkdir()
        self.argv_log = self.home / "argv.log"

        self._orig_env = dict(os.environ)
        #: PATH holds what a test puts there, plus the two SYSTEM directories.
        #: A machine with a real `deepseek` would otherwise send install() down
        #: the ALREADY branch and every assertion below would pass without the
        #: code being exercised -- and /bin and /usr/bin cannot reintroduce one,
        #: which is the whole premise of providers.py's opening note (a GUI
        #: launch inherits exactly those, and no user-installed CLI is in them).
        #: They are here because the npm STUB is a shell script and needs mkdir
        #: and chmod to do npm's job.
        os.environ["PATH"] = os.pathsep.join([str(self.binroot), "/usr/bin", "/bin"])
        os.environ["ARGV_LOG"] = str(self.argv_log)
        os.environ.pop("SUTRA_UI_DEEPSEEK_BIN", None)
        #: The login-shell harvest is a subprocess AND it would re-widen PATH.
        #: Marked done rather than patched out, which is what a second call in a
        #: live process sees anyway.
        self._orig_done = providers._LOGIN_PATH_DONE
        providers._LOGIN_PATH_DONE = True

        #: THE OTHER HALF OF THE PATH CONTROL, and it caught a real hole in the
        #: first draft of these tests. npm_path() falls back to
        #: providers._known_bin_dirs, which probes the REAL home directory --
        #: ~/.npm-global/bin, /opt/homebrew/bin, the nvm version dirs -- and is
        #: entirely indifferent to what PATH says. So on the maintainer's own
        #: machine every "there is no npm" test found one and ran it, against
        #: the live registry. Neutralised here and exercised deliberately in
        #: TheNpmSearchIsTheSameOneTheRowsGet below.
        kb = mock.patch.object(providers, "_known_bin_dirs", return_value=[])
        kb.start()
        self.addCleanup(kb.stop)

        self.addCleanup(self._restore)

    def _restore(self):
        providers.SETTINGS_PATH = self._orig_settings
        providers._LOGIN_PATH_DONE = self._orig_done
        os.environ.clear()
        os.environ.update(self._orig_env)

    def npm(self, body=_FAKE_NPM):
        p = self.binroot / "npm"
        p.write_text(body)
        p.chmod(0o755)
        return p

    def argv(self):
        return self.argv_log.read_text().splitlines() if self.argv_log.exists() else []

    def settings(self):
        """settings.json, or {} -- a refused install writes nothing at all, and
        the assertions about that must not trip over the absence."""
        if not providers.SETTINGS_PATH.exists():
            return {}
        return json.loads(providers.SETTINGS_PATH.read_text())


# ------------------------------------------------------------ the happy path --

class AKeyedMacGetsAWorkingCli(_Base):

    def test_the_binary_lands_where_this_module_says_it_will(self):
        self.npm()
        out = deepseek_install.install()
        self.assertTrue(out["ok"])
        self.assertEqual(out["code"], "INSTALLED")
        self.assertEqual(out["bin_path"], str(deepseek_install.managed_bin()))
        self.assertTrue(os.access(out["bin_path"], os.X_OK))

    def test_everything_written_stays_under_the_settings_directory(self):
        """No sudo, no PATH edit, no shell rc file, nothing global. If this
        assertion ever needs relaxing, the design changed."""
        self.npm()
        deepseek_install.install()
        self.assertTrue(str(deepseek_install.prefix()).startswith(str(self.home)))

    def test_the_provider_row_flips_without_a_restart(self):
        """The whole reason the path is registered instead of installed onto
        PATH. providers._bin_for reads provider_bins ahead of PATH, so the very
        next describe() resolves it -- which is what "no restart" in the panel's
        success message means."""
        self.npm()
        self.assertFalse(providers.provider_by_id("deepseek")["installed"])
        deepseek_install.install()
        row = providers.provider_by_id("deepseek")
        self.assertTrue(row["installed"])
        self.assertEqual(row["bin_path"], str(deepseek_install.managed_bin()))

    def test_the_install_is_never_global(self):
        """FAILURE 1. `-g` is the sudo-or-repoint-your-npm-prefix trap."""
        self.npm()
        deepseek_install.install()
        line = self.argv()[0]
        self.assertNotIn(" -g", " " + line)
        self.assertNotIn("--global", line)
        self.assertIn("--prefix %s" % deepseek_install.prefix(), line)

    def test_the_version_is_the_one_the_adapter_was_measured_against(self):
        """FAILURE 4. acp_runtime.py cites @sluisr/deepseek-cli@1.3.2 on the
        wire; this must ask for that build and not for `latest`."""
        self.npm()
        deepseek_install.install()
        line = self.argv()[0]
        self.assertIn("%s@%s" % (deepseek_install.PACKAGE,
                                 deepseek_install.VERSION), line)
        self.assertNotIn("@latest", line)

    def test_the_package_name_is_the_one_the_provider_row_names(self):
        """One string in the tree. The sentence telling someone what is missing
        and the thing that gets fetched cannot be allowed to disagree."""
        self.assertEqual(deepseek_install.PACKAGE, providers.DEEPSEEK_CLI_PACKAGE)

    def test_a_private_manifest_is_written_before_npm_is_asked(self):
        """Without one npm walks UP looking for a project, and a prefix nested
        under some other package.json could install somewhere else entirely."""
        self.npm()
        deepseek_install.install()
        manifest = json.loads((deepseek_install.prefix() / "package.json").read_text())
        self.assertTrue(manifest["private"])


# ------------------------------------------------------------- the refusals --

class EachFailureNamesItsOwnFix(_Base):

    def test_no_npm_is_answered_with_node_not_with_a_shrug(self):
        """FAILURE 3. There is no npm on the PATH this test built."""
        with self.assertRaises(deepseek_install.DeepSeekInstallError) as caught:
            deepseek_install.install()
        self.assertEqual(caught.exception.code, "NO_NPM")
        msg = str(caught.exception)
        self.assertIn("nodejs.org", msg)
        self.assertIn(deepseek_install.PACKAGE, msg)

    def test_a_mac_without_npm_gets_no_directory_created_for_it(self):
        """Nothing is written for an install that cannot happen."""
        with self.assertRaises(deepseek_install.DeepSeekInstallError):
            deepseek_install.install()
        self.assertFalse(deepseek_install.prefix().exists())

    def test_npm_s_own_complaint_is_what_gets_reported(self):
        """FAILURE 3. ETARGET and EACCES have completely different fixes and
        only npm knows which happened. No credential passes through this
        command, so quoting it is safe here in a way it never is in
        deepseek_auth."""
        self.npm(_FAKE_NPM_FAILS)
        with self.assertRaises(deepseek_install.DeepSeekInstallError) as caught:
            deepseek_install.install()
        self.assertEqual(caught.exception.code, "NPM_FAILED")
        self.assertIn("ETARGET", str(caught.exception))

    def test_a_failed_install_registers_nothing(self):
        """FAILURE 2. A provider_bins entry is a claim the panel renders."""
        self.npm(_FAKE_NPM_FAILS)
        with self.assertRaises(deepseek_install.DeepSeekInstallError):
            deepseek_install.install()
        self.assertIsNone(providers.provider_by_id("deepseek")["bin_path"])
        self.assertFalse(self.settings().get("provider_bins", {}).get("deepseek"))

    def test_a_success_with_no_binary_says_so_rather_than_blaming_the_network(self):
        """FAILURE 3 again, and the subtlest arm: npm was happy, the command is
        not there. That is the package renaming what it publishes, and sending
        the operator to their router would waste their afternoon."""
        self.npm(_FAKE_NPM_EMPTY)
        with self.assertRaises(deepseek_install.DeepSeekInstallError) as caught:
            deepseek_install.install()
        self.assertEqual(caught.exception.code, "NO_BINARY")
        self.assertIn("Sutra problem", str(caught.exception))
        self.assertFalse(self.settings().get("provider_bins", {}).get("deepseek"))

    def test_a_slow_registry_is_a_timeout_and_not_a_broken_key(self):
        self.npm()
        with mock.patch.object(
                deepseek_install.subprocess, "run",
                side_effect=subprocess.TimeoutExpired("npm", 300)):
            with self.assertRaises(deepseek_install.DeepSeekInstallError) as caught:
                deepseek_install.install()
        self.assertEqual(caught.exception.code, "TIMEOUT")
        self.assertIn("registry", str(caught.exception))

    def test_an_env_override_that_cannot_resolve_refuses_the_install(self):
        """deepseek_auth.save()'s env guard, applied to the other half of the
        provider. _bin_for puts SUTRA_UI_DEEPSEEK_BIN ABOVE provider_bins, so
        installing under a live override would download the CLI, register it,
        report success -- and leave the row reading "not installed", because the
        variable keeps winning. Found while building the CLI-less backend for
        the in-app run, which is what that variable is for."""
        os.environ["SUTRA_UI_DEEPSEEK_BIN"] = str(self.home / "nowhere" / "deepseek")
        self.npm()
        with self.assertRaises(deepseek_install.DeepSeekInstallError) as caught:
            deepseek_install.install()
        self.assertEqual(caught.exception.code, "ENV_OVERRIDE")
        self.assertIn("SUTRA_UI_DEEPSEEK_BIN", str(caught.exception))
        self.assertEqual(self.argv(), [])          # npm was never run

    def test_an_override_pointing_at_a_real_binary_is_simply_already_installed(self):
        """It never reaches the guard: provider_bin() resolves it and the
        ALREADY branch answers. The refusal is only for an override that
        resolves to nothing."""
        theirs = self.binroot / "their-deepseek"
        theirs.write_text("#!/bin/sh\nexit 0\n"); theirs.chmod(0o755)
        os.environ["SUTRA_UI_DEEPSEEK_BIN"] = str(theirs)
        self.npm()
        out = deepseek_install.install()
        self.assertEqual(out["code"], "ALREADY")
        self.assertEqual(out["bin_path"], str(theirs))

    def test_the_timeout_clears_a_real_download(self):
        """310s in the desktop bridge sits outside this; a value that drifted
        under a minute would abandon healthy installs and call them failures."""
        self.assertGreaterEqual(deepseek_install.INSTALL_TIMEOUT, 120)


# ----------------------------------------------------- someone else's install --

class AnExistingCliIsLeftAlone(_Base):

    def _hand_installed(self):
        """A `deepseek` the operator put on PATH themselves."""
        p = self.binroot / "deepseek"
        p.write_text("#!/bin/sh\necho theirs\n")
        p.chmod(0o755)
        return p

    def test_nothing_is_downloaded_over_a_working_cli(self):
        theirs = self._hand_installed()
        self.npm()
        out = deepseek_install.install()
        self.assertTrue(out["ok"])
        self.assertEqual(out["code"], "ALREADY")
        self.assertEqual(out["bin_path"], str(theirs))
        self.assertEqual(self.argv(), [])          # npm was never run

    def test_already_is_reported_as_a_success(self):
        """The caller asked for a usable CLI and there is one. Treating that as
        an error would put a red box on a machine that is fine."""
        self._hand_installed()
        self.npm()
        self.assertTrue(deepseek_install.install()["ok"])

    def test_uninstall_never_touches_a_cli_sutra_did_not_install(self):
        self._hand_installed()
        out = deepseek_install.uninstall()
        self.assertFalse(out["removed"])
        self.assertTrue((self.binroot / "deepseek").exists())

    def test_a_deleted_install_stops_shadowing_a_global_one(self):
        """The stale-registration trap this feature made reachable. The tree
        lives under ~/.sutra-ui; clearing that directory, or deleting the
        install by hand, leaves the provider_bins record pointing at nothing.
        Honouring it would report "not installed" on a Mac where the operator
        has since put `deepseek` on PATH themselves -- a Sutra record making a
        working CLI invisible."""
        self.npm()
        deepseek_install.install()
        shutil.rmtree(deepseek_install.prefix())
        self.assertIsNone(providers.provider_by_id("deepseek")["bin_path"])

        theirs = self._hand_installed()
        self.assertEqual(providers.provider_by_id("deepseek")["bin_path"],
                         str(theirs))

    def test_a_live_registration_still_wins_over_path(self):
        """The other half: falling through must not become a habit. A stored
        path that IS there is the whole mechanism."""
        self.npm()
        out = deepseek_install.install()
        self._hand_installed()
        self.assertEqual(providers.provider_by_id("deepseek")["bin_path"],
                         out["bin_path"])

    def test_uninstall_removes_our_own_tree_and_its_registration(self):
        self.npm()
        deepseek_install.install()
        self.assertTrue(deepseek_install.uninstall()["removed"])
        self.assertFalse(deepseek_install.prefix().exists())
        self.assertIsNone(providers.provider_by_id("deepseek")["bin_path"])


# ----------------------------------------------------------------- the state --

class StateAnswersWhatThePanelAsks(_Base):

    def test_a_mac_with_no_npm_cannot_install_and_says_why(self):
        st = deepseek_install.state()
        self.assertFalse(st["installed"])
        self.assertFalse(st["can_install"])
        self.assertIn("nodejs.org", st["reason"])

    def test_a_mac_with_npm_can(self):
        self.npm()
        st = deepseek_install.state()
        self.assertTrue(st["can_install"])
        self.assertIsNone(st["reason"])

    def test_state_runs_no_npm_command(self):
        """It is cheap enough to call on a render only because it asks nothing.
        `npm ls` would add a second-long subprocess to answer a question the
        binary's existence already answers."""
        self.npm()
        deepseek_install.state()
        self.assertEqual(self.argv(), [])

    def test_managed_says_which_install_is_ours(self):
        self.npm()
        self.assertFalse(deepseek_install.state()["managed"])
        deepseek_install.install()
        self.assertTrue(deepseek_install.state()["managed"])

    def test_the_prefix_follows_the_settings_file(self):
        """They are one unit: the tree and the provider_bins entry pointing at
        it. A settings file redirected while the install went to the real home
        would leave a registered path with nothing behind it."""
        self.assertEqual(deepseek_install.prefix().parent.parent, self.home)


class TheNpmSearchIsTheSameOneTheRowsGet(_Base):
    """A GUI launch inherits four system directories and npm is in none of them
    (providers.py's opening note). Asking shutil.which alone would report "no
    npm" on a machine where `npm -v` works in every terminal -- the exact
    failure providers.ensure_login_path() exists for, reproduced one layer up.
    """

    def test_npm_is_found_in_a_known_install_location_off_path(self):
        elsewhere = self.home / "npm-global" / "bin"
        elsewhere.mkdir(parents=True)
        (elsewhere / "npm").write_text("#!/bin/sh\nexit 0\n")
        (elsewhere / "npm").chmod(0o755)
        with mock.patch.object(providers, "_known_bin_dirs",
                               return_value=[str(elsewhere)]):
            self.assertEqual(deepseek_install.npm_path(),
                             str(elsewhere / "npm"))

    def test_that_directory_joins_path_so_node_resolves_for_the_spawn(self):
        """Not cosmetic. The shim npm publishes begins `#!/usr/bin/env node`,
        so the later `deepseek --acp` spawn needs node reachable from THIS
        process -- and node ships beside npm in every layout in
        _KNOWN_BIN_DIRS."""
        elsewhere = self.home / "volta" / "bin"
        elsewhere.mkdir(parents=True)
        (elsewhere / "npm").write_text("#!/bin/sh\nexit 0\n")
        (elsewhere / "npm").chmod(0o755)
        with mock.patch.object(providers, "_known_bin_dirs",
                               return_value=[str(elsewhere)]):
            deepseek_install.npm_path()
        self.assertIn(str(elsewhere), os.environ["PATH"].split(os.pathsep))

    def test_path_is_appended_to_and_never_replaced(self):
        """A PATH set deliberately for this process keeps precedence, matching
        ensure_login_path()."""
        before = os.environ["PATH"].split(os.pathsep)
        elsewhere = self.home / "bun" / "bin"
        elsewhere.mkdir(parents=True)
        (elsewhere / "npm").write_text("#!/bin/sh\nexit 0\n")
        (elsewhere / "npm").chmod(0o755)
        with mock.patch.object(providers, "_known_bin_dirs",
                               return_value=[str(elsewhere)]):
            deepseek_install.npm_path()
        after = os.environ["PATH"].split(os.pathsep)
        self.assertEqual(after[:len(before)], before)


# ------------------------------------------- the install does not need a UI --

class TheInstallHappensWhateverTheClientDoes(_Base):
    """A CORRECT KEY MUST MEAN THE INSTALL IS ATTEMPTED. Not "the panel usually
    chains one onto it".

    THE GAP THIS CLOSES. 07-loaders.js runs the install after a SAVED_NO_CLI
    save, and that is the right place for it -- it is what puts progress and a
    real failure sentence on screen. But it is the BROWSER, and everything it
    needs can be gone a moment after the key is written: window closed, page
    reloaded, desktop bridge dead, or an app binary too old to carry the verb
    (the panel is served fresh by the backend while preload.js ships frozen
    inside Sutra.app). Each of those ends at a validated key on a Mac with no
    CLI and nothing running that will fix it -- the exact 2026-09-07 state this
    whole module exists to abolish, reachable again by a different door.

    And the fix has a cost that has to be paid for: the panel's install and the
    server's now BOTH run for one key. Two npm processes unpacking into one
    prefix is how a slow success becomes a broken tree, so the single-flight
    lock is not an optimisation here, it is what makes the guarantee safe.
    """

    def test_a_saved_key_with_no_cli_starts_an_install_server_side(self):
        """No client involved: the route is called directly."""
        import org_api
        kicked = []
        with mock.patch.object(org_api, "_deepseek_kick_install",
                               side_effect=lambda: kicked.append(True)):
            code, _ = org_api._deepseek_saved_message("sk-****beef", [
                {"id": "deepseek", "installed": False,
                 "reason": "the CLI is not on this Mac"}])
            self.assertEqual(code, "SAVED_NO_CLI")
            if code == "SAVED_NO_CLI":
                org_api._deepseek_kick_install()
        self.assertEqual(kicked, [True],
                         "a keyed Mac with no CLI must not depend on the browser")

    def test_an_already_installed_cli_starts_nothing(self):
        """SAVED means the CLI is there. Re-fetching over a working install is
        slower and can only make things worse."""
        import org_api
        code, _ = org_api._deepseek_saved_message("sk-****beef", [
            {"id": "deepseek", "installed": True}])
        self.assertEqual(code, "SAVED")

    def test_the_kick_never_raises_into_the_key_response(self):
        """The key is already written by the time this runs and the response is
        already computed -- an npm failure must not turn a successful save into
        a 500."""
        import org_api
        with mock.patch.object(deepseek_install, "install",
                               side_effect=RuntimeError("npm exploded")):
            org_api._deepseek_kick_install()
            for t in threading.enumerate():
                if t.name == "deepseek-cli-install":
                    t.join(timeout=5)

    def test_two_installs_at_once_run_one_npm(self):
        """THE COST OF THE GUARANTEE, pinned. The panel's chain and the server's
        kick fire for the same key; npm has no opinion about two of itself
        unpacking into one prefix. The second caller must wait and then be
        answered ALREADY from the first one's result."""
        self.npm()
        results = []
        errors = []

        def go():
            try:
                results.append(deepseek_install.install())
            except Exception as e:      # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, [], "a concurrent install failed: %r" % (errors,))
        self.assertEqual(len(results), 4)
        installs = [line for line in self.argv() if "install" in line]
        self.assertEqual(len(installs), 1,
                         "npm ran %d times for one install: %r"
                         % (len(installs), installs))
        self.assertEqual(sum(1 for r in results if r["code"] == "INSTALLED"), 1)
        self.assertEqual(sum(1 for r in results if r["code"] == "ALREADY"), 3)


if __name__ == "__main__":
    unittest.main()
