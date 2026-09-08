"""Installing the Codex CLI: what must happen, and what must never.

THE BUG THIS CLOSES (2026-09-08). On a Mac with no Codex CLI,
providers.codex_auth() answered `state: "no_binary"` and the sign-in block
rendered the reason with NO ACTIONS AT ALL -- `actions = ""`. A dead end, on
the one screen that exists to get Codex working: the user could neither sign in
(there is nothing to sign in to) nor install (nothing offered it). Meanwhile
the runtime chain a working Codex needs -- Node -> npm -> @openai/codex -> a
runnable `codex` -- had no code anywhere in the tree that could put any of it
there.

SIX FAILURES THESE TESTS EXIST TO PREVENT:

  1. `npm install -g`. On a system node, or Homebrew on Intel, the global
     prefix is root-owned, so a global install fails with EACCES -- and the two
     ways out are sudo (a GUI app must not ask) or permanently repointing the
     operator's npm prefix. Worse here than it was for DeepSeek: `codex` is a
     command plenty of people already have, and `-g` would REPLACE the one
     their terminal resolves. The design is --prefix into a directory Sutra
     owns; test_the_install_is_never_global is the guard on it.

  2. "npm exited 0" reported as a working runtime. This is the failure that is
     NOT in test_deepseek_install, and it is why this module cannot just be
     that one with the strings changed. @openai/codex publishes bin/codex.js,
     13KB of ESM beginning `#!/usr/bin/env node` (measured 2026-09-08 against
     0.153.4). Present, executable, and dead with `env: node: No such file or
     directory` on a Mac with no Node. Registered on npm's exit code alone,
     that becomes a row reading "Ready to use" over a provider that cannot
     answer a message -- the readiness lie this whole package is organised
     against. install() has to RUN the thing.

  3. Overwriting somebody's own Codex. Homebrew's cask ships a native binary,
     and plenty of people have their own npm install. Neither is Sutra's to
     delete, replace, or uninstall.

  4. A registered path with nothing behind it. `provider_bins` is what makes
     the row flip without a restart; writing it when the binary is absent, not
     executable, or non-functional trades "not installed" for "installed and
     will not run".

  5. A refusal that blames the wrong thing. No npm, npm failing, npm succeeding
     with no `codex` published, and a `codex` that will not run are four
     different problems with four different fixes.

  6. A floating version. codex_runtime.py's transport was measured against
     codex-cli 0.153.2 and providers._CODEX_API_KEY_RE parses the exact line
     that build prints. Installing `latest` ships an adapter verified against
     one version pointed at another -- silently changing both the chat wire
     format and the string the sign-in row reads.

NOTHING HERE RUNS THE REAL npm OR REACHES THE NETWORK. A stub script stands in,
records the argv it was called with, and populates the prefix the way npm
would. PATH is replaced for the duration, so the `codex` that happens to be
installed on the machine running these tests cannot make them pass.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import codex_install
import providers

#: A stand-in for npm. Records its argv, then does what npm does to a prefix:
#: creates node_modules/.bin and drops the executable the package publishes.
#:
#: The published `codex` ANSWERS `--version`, because that is what
#: codex_install.verify() asks it, and a stub that could not would make every
#: happy-path test below a verification failure.
#:
#: EVERY COMMAND IS ABSOLUTE, for the reason test_deepseek_install records: the
#: stub inherits whatever PATH the module under test has just been handed, and
#: a bare `mkdir` that silently fails produces a fixture failure wearing a
#: product failure's clothes.
_FAKE_NPM = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
prefix=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--prefix" ]; then prefix="$2"; fi
  shift
done
[ -n "$prefix" ] || { echo "no --prefix" >&2; exit 1; }
/bin/mkdir -p "$prefix/node_modules/.bin"
printf '#!/bin/sh\necho codex-cli 0.153.2\n' > "$prefix/node_modules/.bin/codex"
/bin/chmod +x "$prefix/node_modules/.bin/codex"
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

#: npm refusing on the engine field, which is the shape a too-old Node takes.
#: @openai/codex declares engines.node ">=16" (measured), and npm>=7 enforces
#: it -- so this is the failure a normal user's ancient Node produces.
_FAKE_NPM_EBADENGINE = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
echo "npm error code EBADENGINE" >&2
echo "npm error engine Unsupported engine {required:{node:'>=16'},current:{node:'v12.22.0'}}" >&2
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

#: npm that installs a `codex` which CANNOT RUN -- exactly what the real
#: package produces on a Mac with no Node: the shim is there, it is executable,
#: and `/usr/bin/env node` cannot resolve. Exit 127 with that message is what
#: the kernel and env actually produce, reproduced here rather than invented.
_FAKE_NPM_DEAD_SHIM = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
prefix=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--prefix" ]; then prefix="$2"; fi
  shift
done
/bin/mkdir -p "$prefix/node_modules/.bin"
printf '#!/bin/sh\necho "env: node: No such file or directory" >&2\nexit 127\n' \
  > "$prefix/node_modules/.bin/codex"
/bin/chmod +x "$prefix/node_modules/.bin/codex"
echo "added 1 package"
exit 0
"""

#: npm that never returns. For the timeout classification.
_FAKE_NPM_HANGS = r"""#!/bin/sh
printf '%s\n' "$*" >> "$ARGV_LOG"
sleep 30
"""


class _Base(unittest.TestCase):
    """A settings DIRECTORY of our own, and a PATH with nothing real on it.

    A directory rather than a bare temp file: codex_install.prefix() is
    SETTINGS_PATH.parent/providers/codex, so a settings file in /tmp would put
    the install tree in /tmp/providers. The two are one unit and the test has
    to move them together.
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
        #: The machine running these tests very likely HAS a real `codex` (the
        #: maintainer's does, at /opt/homebrew/bin), which would send install()
        #: down the ALREADY branch and let every assertion below pass without
        #: the code being exercised. /bin and /usr/bin cannot reintroduce one --
        #: that is providers.py's opening premise, a GUI launch inherits exactly
        #: those. They are here because the npm STUB is a shell script.
        os.environ["PATH"] = os.pathsep.join([str(self.binroot), "/usr/bin", "/bin"])
        os.environ["ARGV_LOG"] = str(self.argv_log)
        os.environ.pop("SUTRA_UI_CODEX_BIN", None)
        #: The login-shell harvest is a subprocess AND it would re-widen PATH.
        self._orig_done = providers._LOGIN_PATH_DONE
        providers._LOGIN_PATH_DONE = True

        #: THE OTHER HALF OF THE PATH CONTROL. npm_path() falls back to
        #: providers._known_bin_dirs, which probes the REAL home directory and
        #: is entirely indifferent to what PATH says -- so on a developer's
        #: machine every "there is no npm" test would find one and run it
        #: against the live registry. Neutralised here and exercised
        #: deliberately in TheNpmSearchIsTheSameOneTheRowsGet below.
        kb = mock.patch.object(providers, "_known_bin_dirs", return_value=[])
        kb.start()
        self.addCleanup(kb.stop)

        providers._BUNDLED_NODE_DONE = False
        self.addCleanup(setattr, providers, "_BUNDLED_NODE_DONE", False)

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

    def external_codex(self, body='#!/bin/sh\necho codex-cli 9.9.9\n'):
        """A `codex` the operator installed themselves, on PATH and not ours."""
        p = self.binroot / "codex"
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

    def provider_bins(self):
        return self.settings().get("provider_bins") or {}


# --------------------------------------------------------------- the state --

class StateAnswersWithoutRunningAnything(_Base):
    """state() rides on GET /providers/codex/auth, which the sign-in poll hits
    every 2 seconds. A subprocess there would be a tax on a render path."""

    def test_a_bare_mac_reports_not_installed_and_says_why(self):
        st = codex_install.state()
        self.assertFalse(st["installed"])
        self.assertIsNone(st["bin_path"])
        self.assertFalse(st["managed"])
        self.assertFalse(st["can_install"])
        self.assertIn("nodejs.org", st["reason"])

    def test_an_npm_makes_the_install_offerable(self):
        self.npm()
        st = codex_install.state()
        self.assertTrue(st["can_install"])
        self.assertIsNone(st["reason"])

    def test_an_external_codex_is_reported_installed_but_not_managed(self):
        """The distinction uninstall() turns on. Sutra must know the difference
        between the copy it made and the one the operator did."""
        ext = self.external_codex()
        st = codex_install.state()
        self.assertTrue(st["installed"])
        self.assertEqual(st["bin_path"], str(ext))
        self.assertFalse(st["managed"])

    def test_it_never_spawns_a_subprocess(self):
        """The reason there is no `verified` field. Proving the runtime runs
        costs a `codex --version`, and this answer is on a 2-second poll."""
        self.npm()
        with mock.patch.object(subprocess, "run",
                               side_effect=AssertionError("state() spawned")) as ran:
            codex_install.state()
        self.assertFalse(ran.called)

    def test_the_package_and_version_are_published_not_guessed(self):
        st = codex_install.state()
        self.assertEqual(st["package"], "@openai/codex")
        self.assertEqual(st["version"], codex_install.VERSION)


# ---------------------------------------------------------- the happy path --

class AnAuthenticatedMacGetsAWorkingCli(_Base):

    def test_the_binary_lands_where_this_module_says_it_will(self):
        self.npm()
        out = codex_install.install()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["code"], "INSTALLED")
        self.assertEqual(out["bin_path"], str(codex_install.managed_bin()))
        self.assertTrue(os.access(out["bin_path"], os.X_OK))

    def test_everything_written_stays_under_the_settings_directory(self):
        """No sudo, no PATH edit, no shell rc file, nothing global. If this
        assertion ever needs relaxing, the design changed."""
        self.npm()
        codex_install.install()
        self.assertTrue(str(codex_install.prefix()).startswith(str(self.home)))

    def test_the_provider_row_flips_without_a_restart(self):
        """The whole reason the path is REGISTERED rather than installed onto
        PATH. providers._bin_for reads provider_bins ahead of PATH, so the very
        next describe() resolves it -- which is what "no restart" means."""
        self.npm()
        self.assertFalse(providers.provider_by_id("codex")["installed"])
        codex_install.install()
        self.assertTrue(providers.provider_by_id("codex")["installed"])

    def test_the_install_is_never_global(self):
        """THE WHOLE DESIGN. -g writes to a prefix that is root-owned on a
        system node, and would replace whatever `codex` the operator's terminal
        resolves today."""
        self.npm()
        codex_install.install()
        line = self.argv()[0]
        self.assertIn("--prefix", line)
        self.assertIn(str(codex_install.prefix()), line)
        self.assertNotIn(" -g", " " + line)
        self.assertNotIn("--global", line)

    def test_the_version_is_pinned_not_latest(self):
        """codex_runtime.py's wire format and providers._CODEX_API_KEY_RE's
        line were both measured against one build."""
        self.npm()
        codex_install.install()
        self.assertIn("@openai/codex@" + codex_install.VERSION, self.argv()[0])
        self.assertNotIn("@latest", self.argv()[0])

    def test_a_private_manifest_is_written_before_npm_is_asked(self):
        """Without one npm walks UP looking for a parent project, and a prefix
        under a directory that happens to have a package.json could install
        somewhere else entirely."""
        self.npm()
        codex_install.install()
        man = json.loads((codex_install.prefix() / "package.json").read_text())
        self.assertTrue(man["private"])
        self.assertEqual(man["name"], "sutra-provider-codex")

    def test_the_message_says_it_checked_that_it_runs(self):
        """Not decoration. It is the one claim that separates this install from
        the one that reported success off an exit code."""
        self.npm()
        out = codex_install.install()
        self.assertIn("runs", out["message"])


# ------------------------------------------------------- npm exiting 0 is not --

class NpmExitingZeroIsNotAWorkingRuntime(_Base):
    """THE FAILURE THIS MODULE EXISTS FOR, and the one test_deepseek_install
    never had to write.

    The published `codex` is a node shim. On a Mac with no Node it installs
    perfectly and dies at `env: node: No such file or directory`. Everything
    below is about that gap between "npm succeeded" and "Codex works".
    """

    def test_a_dead_shim_is_refused_not_registered(self):
        self.npm(_FAKE_NPM_DEAD_SHIM)
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertEqual(caught.exception.code, "VERIFY_FAILED")

    def test_a_dead_shim_leaves_the_row_saying_not_installed(self):
        """THE READINESS LIE, pinned. Registering this would put "Ready to use"
        over a provider that cannot answer a single message."""
        self.npm(_FAKE_NPM_DEAD_SHIM)
        with self.assertRaises(codex_install.CodexInstallError):
            codex_install.install()
        self.assertEqual(self.provider_bins().get("codex"), None)
        self.assertFalse(providers.provider_by_id("codex")["installed"])

    def test_the_refusal_quotes_what_the_binary_actually_said(self):
        """`env: node: No such file or directory` is the whole diagnosis. A
        bare exit code sends the operator to their network."""
        self.npm(_FAKE_NPM_DEAD_SHIM)
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertIn("node", str(caught.exception))

    def test_the_refusal_says_nothing_was_registered(self):
        self.npm(_FAKE_NPM_DEAD_SHIM)
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertIn("not installed", str(caught.exception))

    def test_verification_runs_the_binary_that_was_just_installed(self):
        """Not `codex` off PATH -- the managed absolute path. Verifying a
        DIFFERENT codex would be the cheeriest possible false pass."""
        self.npm()
        seen = []
        real = subprocess.run

        def spy(args, *a, **kw):
            seen.append(args)
            return real(args, *a, **kw)

        with mock.patch.object(subprocess, "run", side_effect=spy):
            codex_install.install()
        self.assertIn([str(codex_install.managed_bin()), "--version"], seen)

    def test_verify_asks_for_version_and_not_login_status(self):
        """`login status` reads a credential and exits non-zero on a signed-out
        machine. Using it here would refuse a perfectly good install for a
        reason that is not about the runtime at all."""
        self.npm()
        seen = []
        real = subprocess.run
        with mock.patch.object(subprocess, "run",
                               side_effect=lambda a, *r, **k: (seen.append(a),
                                                               real(a, *r, **k))[1]):
            codex_install.install()
        self.assertFalse(any("login" in x for a in seen for x in a),
                         "verification must not touch the credential: %r" % seen)


# ------------------------------------------------------------- ALREADY -------

class AnExistingCodexIsNeverOverwritten(_Base):

    def test_an_external_codex_short_circuits_and_npm_never_runs(self):
        self.npm()
        ext = self.external_codex()
        out = codex_install.install()
        self.assertTrue(out["ok"])
        self.assertEqual(out["code"], "ALREADY")
        self.assertEqual(out["bin_path"], str(ext))
        self.assertEqual(self.argv(), [], "npm ran over a working install")

    def test_already_reports_that_it_is_not_ours(self):
        self.npm()
        self.external_codex()
        self.assertFalse(codex_install.install()["managed"])

    def test_the_external_binary_is_left_byte_for_byte_alone(self):
        """Homebrew's cask, a global npm, a hand-built checkout -- none of them
        are this module's to touch."""
        self.npm()
        ext = self.external_codex()
        before = ext.read_bytes()
        codex_install.install()
        self.assertEqual(ext.read_bytes(), before)

    def test_already_still_proves_the_thing_runs(self):
        """The case deepseek_install never had: a codex that RESOLVES and
        CANNOT RUN must not be reported as a working install."""
        self.npm()
        self.external_codex('#!/bin/sh\nexit 127\n')
        out = codex_install.install()
        self.assertEqual(out["code"], "INSTALLED",
                         "a codex that cannot run was accepted as ALREADY")

    def test_a_broken_external_codex_gets_a_managed_copy_beside_it(self):
        """NOT a repair of theirs -- Sutra points ITSELF at a copy it owns, and
        the operator's binary and their terminal are untouched."""
        self.npm()
        ext = self.external_codex('#!/bin/sh\nexit 127\n')
        before = ext.read_bytes()
        out = codex_install.install()
        self.assertEqual(out["bin_path"], str(codex_install.managed_bin()))
        self.assertTrue(out["managed"])
        self.assertEqual(ext.read_bytes(), before)

    def test_force_reinstalls_over_our_own_copy(self):
        """The repair path: a registered install that stopped working."""
        self.npm()
        codex_install.install()
        self.assertEqual(len(self.argv()), 1)
        out = codex_install.install(force=True)
        self.assertEqual(out["code"], "INSTALLED")
        self.assertEqual(len(self.argv()), 2)


# ---------------------------------------------------------- classification ---

class EveryRefusalNamesItsOwnCause(_Base):

    def test_no_npm(self):
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertEqual(caught.exception.code, "NO_NPM")
        self.assertIn("nodejs.org", str(caught.exception))

    def test_no_npm_writes_nothing_at_all(self):
        """npm is resolved BEFORE anything is written, so a Mac that cannot do
        this does not get a directory made for an install that will not run."""
        with self.assertRaises(codex_install.CodexInstallError):
            codex_install.install()
        self.assertFalse(codex_install.prefix().exists())

    def test_npm_failing_quotes_npm(self):
        self.npm(_FAKE_NPM_FAILS)
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertEqual(caught.exception.code, "NPM_FAILED")
        self.assertIn("ETARGET", str(caught.exception))

    def test_a_too_old_node_is_named_as_such(self):
        """npm's EBADENGINE wall of prose is about a field name. The user's Mac
        having an ancient Node is the fact, and nodejs.org is the fix."""
        self.npm(_FAKE_NPM_EBADENGINE)
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertEqual(caught.exception.code, "NODE_TOO_OLD")
        self.assertIn("nodejs.org", str(caught.exception))

    def test_timeout(self):
        self.npm(_FAKE_NPM_HANGS)
        with mock.patch.object(codex_install, "INSTALL_TIMEOUT", 1):
            with self.assertRaises(codex_install.CodexInstallError) as caught:
                codex_install.install()
        self.assertEqual(caught.exception.code, "TIMEOUT")
        self.assertIn("registry", str(caught.exception))

    def test_npm_succeeding_with_no_command_published(self):
        """Blames the package, not the network -- a wrong diagnosis here sends
        the operator to their router."""
        self.npm(_FAKE_NPM_EMPTY)
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertEqual(caught.exception.code, "NO_BINARY")
        self.assertIn("Sutra problem", str(caught.exception))

    def test_an_env_override_that_does_not_resolve_is_refused_by_name(self):
        """SUTRA_UI_CODEX_BIN wins over provider_bins, so an install under it
        would download, register, report success -- and the row would still
        read "not installed"."""
        self.npm()
        os.environ["SUTRA_UI_CODEX_BIN"] = "/nowhere/codex"
        with self.assertRaises(codex_install.CodexInstallError) as caught:
            codex_install.install()
        self.assertEqual(caught.exception.code, "ENV_OVERRIDE")
        self.assertIn("SUTRA_UI_CODEX_BIN", str(caught.exception))

    def test_an_env_override_that_does_resolve_is_honoured_not_refused(self):
        """Ordering, and it is not cosmetic: the check has to come AFTER the
        ALREADY branch or a perfectly good override is refused."""
        self.npm()
        ext = self.external_codex()
        os.environ["SUTRA_UI_CODEX_BIN"] = str(ext)
        out = codex_install.install()
        self.assertEqual(out["code"], "ALREADY")

    def test_nothing_is_registered_by_any_refusal(self):
        for body in (_FAKE_NPM_FAILS, _FAKE_NPM_EMPTY, _FAKE_NPM_DEAD_SHIM):
            with self.subTest(npm=body[:40]):
                self.npm(body)
                with self.assertRaises(codex_install.CodexInstallError):
                    codex_install.install()
                self.assertIsNone(self.provider_bins().get("codex"))


# -------------------------------------------------------------- ordering -----

class RegistrationIsTheLastThingThatHappens(_Base):

    def test_the_row_is_never_pointed_at_an_unverified_binary(self):
        """A registered path is a claim the panel renders as "Ready to use".
        Nothing may be registered until that claim is true."""
        order = []
        real_set = providers.set_provider_bin
        real_run = subprocess.run

        def note_run(args, *a, **kw):
            if isinstance(args, (list, tuple)) and len(args) > 1 and args[1] == "--version":
                order.append("verify")
            return real_run(args, *a, **kw)

        def note_set(pid, path):
            order.append("register")
            return real_set(pid, path)

        self.npm()
        with mock.patch.object(subprocess, "run", side_effect=note_run), \
             mock.patch.object(providers, "set_provider_bin", side_effect=note_set):
            codex_install.install()
        self.assertEqual(order, ["verify", "register"])

    def test_a_keychain_style_register_failure_is_its_own_code(self):
        self.npm()
        with mock.patch.object(providers, "set_provider_bin",
                               side_effect=OSError("read-only")):
            with self.assertRaises(codex_install.CodexInstallError) as caught:
                codex_install.install()
        self.assertEqual(caught.exception.code, "REGISTER_FAILED")


# ---------------------------------------------------------- single-flight ----

class TwoInstallsAreOneDownload(_Base):
    """npm has no opinion about two of itself unpacking into one prefix, and
    this route can be entered twice for reasons the UI cannot prevent: the
    panel's sign-in chain racing the server-side kick, two open tabs, or a
    retry fired while a slow registry was still answering."""

    def test_concurrent_installs_run_npm_once(self):
        self.npm()
        results, errors = [], []

        def go():
            try:
                results.append(codex_install.install())
            except Exception as exc:          # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=go) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 4)
        self.assertEqual(len(self.argv()), 1,
                         "npm ran %d times for one install" % len(self.argv()))

    def test_the_losers_are_told_the_truth_not_given_a_second_download(self):
        self.npm()
        results = []
        threads = [threading.Thread(target=lambda: results.append(
            codex_install.install())) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        codes = sorted(r["code"] for r in results)
        self.assertEqual(codes, ["ALREADY", "ALREADY", "INSTALLED"])
        for r in results:
            self.assertEqual(r["bin_path"], str(codex_install.managed_bin()))


# ------------------------------------------------------------- uninstall -----

class UninstallOnlyEverTouchesOurOwn(_Base):

    def test_a_managed_install_goes_and_takes_its_registration_with_it(self):
        self.npm()
        codex_install.install()
        out = codex_install.uninstall()
        self.assertTrue(out["removed"])
        self.assertFalse(codex_install.prefix().exists())
        self.assertIsNone(self.provider_bins().get("codex"))

    def test_an_external_codex_survives_untouched(self):
        ext = self.external_codex()
        codex_install.uninstall()
        self.assertTrue(ext.exists())
        self.assertTrue(providers.provider_by_id("codex")["installed"])

    def test_an_operator_set_override_is_left_alone(self):
        """provider_bins can hold a path the operator chose. Uninstalling OUR
        copy must not clear THEIR pointer."""
        self.npm()
        ext = self.external_codex()
        providers.set_provider_bin("codex", str(ext))
        codex_install.prefix().mkdir(parents=True, exist_ok=True)
        codex_install.uninstall()
        self.assertEqual(self.provider_bins().get("codex"), str(ext))

    def test_it_is_idempotent(self):
        self.assertFalse(codex_install.uninstall()["removed"])
        self.assertFalse(codex_install.uninstall()["removed"])

    def test_a_hand_deleted_managed_tree_still_clears_its_registration(self):
        """_bin_for ignores a stored path that no longer exists, so
        provider_bin() would report the operator's own codex and a check
        against THAT would leave the dead entry in settings.json forever."""
        self.npm()
        codex_install.install()
        shutil.rmtree(codex_install.prefix())
        codex_install.uninstall()
        self.assertIsNone(self.provider_bins().get("codex"))


# ----------------------------------------------------------- the npm search --

class TheNpmSearchIsTheSameOneTheRowsGet(_Base):
    """A GUI launch inherits a PATH of four system directories and npm is in
    none of them. shutil.which() alone would report "no npm" on a machine where
    `npm -v` works in every terminal."""

    def test_a_known_install_location_is_found_and_joined_to_path(self):
        d = self.home / "npm-global" / "bin"
        d.mkdir(parents=True)
        (d / "npm").write_text(_FAKE_NPM)
        (d / "npm").chmod(0o755)
        os.environ["PATH"] = os.pathsep.join(["/usr/bin", "/bin"])
        with mock.patch.object(providers, "_known_bin_dirs", return_value=[str(d)]):
            found = codex_install.npm_path()
        self.assertEqual(found, str(d / "npm"))
        self.assertIn(str(d), os.environ["PATH"].split(os.pathsep))


class TheBundledNodeIsTheLastResort(_Base):
    """bundle-runtime.sh vendors Node 24.20.0 into payload/node so a Mac with
    nothing installed can still go from DMG to a working provider. @openai/codex
    declares engines.node >=16, so that copy satisfies it."""

    def _payload(self):
        root = self.home / "payload"
        d = root / "node" / "bin"
        d.mkdir(parents=True)
        (d / "node").write_text("#!/bin/sh\nexit 0\n")
        (d / "node").chmod(0o755)
        (d / "npm").write_text(_FAKE_NPM)
        (d / "npm").chmod(0o755)
        return root, d

    def _point_providers_at(self, root):
        return mock.patch.object(providers, "bundled_node_bin_dir",
                                 return_value=str(root / "node" / "bin"))

    def test_a_mac_with_no_node_installs_through_the_bundled_one(self):
        root, _ = self._payload()
        with self._point_providers_at(root):
            self.assertIsNone(shutil.which("npm"),
                              "this test is meaningless with an npm on PATH")
            out = codex_install.install()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["code"], "INSTALLED")

    def test_a_machine_with_its_own_npm_ignores_the_bundle(self):
        own = self.npm()
        root, bundled = self._payload()
        with self._point_providers_at(root):
            found = codex_install.npm_path()
        self.assertEqual(found, str(own), "the bundle won over the machine's own npm")
        self.assertNotIn(str(bundled), os.environ.get("PATH", "").split(os.pathsep))

    def test_verification_can_reach_the_bundled_node(self):
        """THE SHIM'S RUNTIME, not just the install's. `codex` starts
        `#!/usr/bin/env node`, so `codex --version` needs node resolvable --
        and so does every later chat turn."""
        root, d = self._payload()
        with self._point_providers_at(root):
            providers._BUNDLED_NODE_DONE = False
            codex_install.verify(str(self.external_codex()))
        self.assertIn(str(d), os.environ["PATH"].split(os.pathsep))
        self.assertIsNotNone(shutil.which("node"), "node still does not resolve")

    def test_no_payload_means_no_change(self):
        """A checkout, a dev server and this suite have no payload. Every
        caller must behave exactly as it did before Node was bundled."""
        before = os.environ["PATH"]
        with mock.patch.object(providers, "bundled_node_bin_dir", return_value=None):
            self.assertIsNone(providers.ensure_bundled_node_path())
            self.assertIsNone(codex_install.npm_path())
        self.assertEqual(os.environ["PATH"], before)

    def test_the_refusal_names_the_bundled_copy_too(self):
        with mock.patch.object(providers, "bundled_node_bin_dir", return_value=None):
            with self.assertRaises(codex_install.CodexInstallError) as caught:
                codex_install.install()
        self.assertEqual(caught.exception.code, "NO_NPM")
        self.assertIn("bundled", str(caught.exception))


class TheSpawnRepairsPathForCodexToo(unittest.TestCase):
    """app.py's one-line change, pinned.

    A SOURCE ASSERTION, deliberately, and this codebase already has the
    precedent (test_forbidden_calls.py greps org_api.py for a provable
    negative). The behaviour it guards -- the bundled Node reaching a `codex
    exec` spawn -- is only observable on a machine that HAS a payload and has
    NO Node, which is a packaged DMG on a bare Mac and not something this suite
    can be. What can be pinned here is that codex is inside the condition, and
    that is exactly the line a future edit would drop.

    WHY IT MATTERS: @openai/codex publishes a `#!/usr/bin/env node` shim, so a
    Codex installed by codex_install on a Node-less Mac dies at spawn with
    `env: node: No such file or directory` -- an install that worked perfectly,
    reading as a broken install rather than a missing runtime. That is the
    DeepSeek bug this comment's neighbour in app.py was written about.
    """

    def test_codex_is_in_the_bundled_node_condition(self):
        import inspect

        import app
        src = inspect.getsource(app.ws_chat)
        guarded = re.search(
            r'if active_id in \(([^)]*)\):\s*\n(?:\s*#[^\n]*\n)*'
            r'\s*providers\.ensure_bundled_node_path\(\)', src)
        self.assertIsNotNone(
            guarded,
            "no `if active_id in (...)` guarding ensure_bundled_node_path()")
        self.assertIn('"codex"', guarded.group(1))
        self.assertIn('"deepseek"', guarded.group(1),
                      "DeepSeek must keep the repair it already had")

    def test_claude_is_still_excluded(self):
        """Claude's CLI is not a node shim, and nothing about it changes."""
        import inspect

        import app
        src = inspect.getsource(app.ws_chat)
        guarded = re.search(r'if active_id in \(([^)]*)\):\s*\n(?:\s*#[^\n]*\n)*'
                            r'\s*providers\.ensure_bundled_node_path\(\)', src)
        self.assertNotIn('"claude"', guarded.group(1))


if __name__ == "__main__":
    unittest.main()


# ================================================== the UX enhancement pass ==

class TestCodexModelDiscovery(_Base):
    """THE PICKER'S ONLY AUTHORITATIVE SOURCE.

    Re-measured 2026-09-08 against codex-cli 0.153.2 before any of this was
    written, because "codex publishes no model list" is a claim that has to be
    re-checked before it justifies an empty picker:

        codex models …            no such subcommand
        codex exec --help         `-m, --model <MODEL>`, no enumeration
        codex app-server
          generate-json-schema    39 files, 1.79 MB, ZERO concrete model ids
        codex doctor              reports `model  <default> · openai`

    It still holds. So nothing is invented -- and the one place a real id can
    be read from is the operator's OWN codex config, which is what these pin.
    """

    def _home(self, **files):
        home = self.home / "codexhome"
        home.mkdir(exist_ok=True)
        for name, body in files.items():
            (home / name).write_text(body)
        os.environ["CODEX_HOME"] = str(home)
        providers._CODEX_MODEL_CACHE.clear()
        self.addCleanup(providers._CODEX_MODEL_CACHE.clear)
        return home

    def test_no_config_leaves_the_picker_exactly_as_it_was(self):
        """The ordinary case. This feature may not make an unconfigured machine
        worse, so the floor is the single CLI-default entry and nothing else."""
        self._home()
        self.assertEqual(providers.codex_config_models(), ())
        self.assertEqual([m["id"] for m in providers.models_for("codex")], [""])

    def test_a_configured_model_is_offered_beside_the_default(self):
        self._home(**{"config.toml": 'model = "gpt-5.6-terra"\n'})
        ids = [m["id"] for m in providers.models_for("codex")]
        self.assertEqual(ids, ["", "gpt-5.6-terra"])
        self.assertIn("your codex config",
                      providers.models_for("codex")[1]["note"])

    def test_a_profile_model_is_offered_and_names_its_profile(self):
        self._home(**{"work.config.toml": 'model = "some-model-id"\n'})
        entry = providers.models_for("codex")[1]
        self.assertEqual(entry["id"], "some-model-id")
        self.assertIn("work", entry["note"])

    def test_duplicates_across_files_appear_once(self):
        self._home(**{"config.toml": 'model = "same"\n',
                      "a.config.toml": 'model = "same"\n'})
        self.assertEqual([m["id"] for m in providers.models_for("codex")],
                         ["", "same"])

    def test_a_model_nested_under_a_table_is_NOT_read_as_the_default(self):
        """The scan is anchored to column 0 on purpose: `model` inside any
        [table] describes that table, not the top-level default, and offering
        it would be Sutra inventing a choice the operator did not make."""
        self._home(**{"config.toml":
                      '[model_providers.openai]\n  model = "not-the-default"\n'})
        self.assertEqual(providers.codex_config_models(), ())

    def test_junk_is_ignored_rather_than_offered(self):
        for body in ("", "model =\n", "model = \n", "# model = \"x\"\n",
                     "modelx = \"y\"\n", 'model = ""\n'):
            with self.subTest(body=body):
                self._home(**{"config.toml": body})
                self.assertEqual(providers.codex_config_models(), (),
                                 "offered something from %r" % body)

    def test_a_discovered_model_actually_survives_validation(self):
        """THE WHOLE POINT: a picked model has to REACH codex. clean_model
        gates every value against the selectable set, so a discovered id that
        did not pass would be a control that silently did nothing."""
        self._home(**{"config.toml": 'model = "gpt-5.6-terra"\n'})
        self.assertEqual(providers.clean_model("gpt-5.6-terra", "codex"),
                         "gpt-5.6-terra")
        self.assertIsNone(providers.clean_model("never-configured", "codex"))

    def test_the_cli_default_still_means_no_flag(self):
        """"" is a real choice and must stay one -- it is what leaves model
        selection to codex, which is the behaviour this preserves."""
        self._home(**{"config.toml": 'model = "gpt-5.6-terra"\n'})
        self.assertIsNone(providers.clean_model("", "codex"))

    def test_other_providers_lists_are_untouched(self):
        """models_for() grew one id-keyed branch. Claude and DeepSeek must come
        back byte-identical to their catalogue tuples."""
        self._home(**{"config.toml": 'model = "gpt-5.6-terra"\n'})
        for pid in ("claude", "deepseek", "gemini"):
            spec = next(s for s in providers._CATALOG if s["id"] == pid)
            self.assertEqual(providers.models_for(pid), spec["models"], pid)

    def test_the_read_is_cached_on_mtime(self):
        """models_for() is on the settings path and every fs call reaches it."""
        home = self._home(**{"config.toml": 'model = "one"\n'})
        real = Path.read_text
        calls = []

        def counted(self, *a, **k):
            calls.append(str(self))
            return real(self, *a, **k)

        with mock.patch.object(Path, "read_text", counted):
            providers.codex_config_models()
            providers.codex_config_models()
            providers.codex_config_models()
        reads = [c for c in calls if c.endswith("config.toml")]
        self.assertEqual(len(reads), 1, "read %d times" % len(reads))
