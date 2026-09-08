"""The join between "Codex is signed in" and "Codex can be picked".

THE BUG THIS CLOSES (2026-09-08). The panel keeps those two facts in two
different places -- `S.codexAuth` and `PROVIDERS` -- and only the first was
ever refreshed after a sign-in. `PROVIDERS` is filled exactly once, by
loadRuntime() inside boot(); nothing else in the app re-reads it. So:

    click "Sign in with ChatGPT"
      -> codex completes the browser flow and writes ~/.codex/auth.json
      -> providers._describe() would now say configured/runnable
      -> the poll reads GET /providers/codex/auth
      -> the sign-in block says "Signed in with ChatGPT"
      -> the ROW DIRECTLY ABOVE IT still says "Installed, but not signed in
         yet", with its radio still disabled

...until the operator reloaded the page, which called loadRuntime() and got the
answer the backend had had the whole time. Sign-OUT had the same gap in the
more dangerous direction: "Ready to use" and an enabled radio over a Codex
holding no credential at all.

THE FIX, AND WHY IT IS SHAPED THIS WAY. `providers` and `settings` ride along
on the answer that OBSERVED the change -- the same move _deepseek_state() makes
for its own row, and POST /settings/provider-bin before it. No new poll, no
second request the client has to know to fire, no second copy of the state.
The poll endpoint is the anchor because every Codex transition funnels through
it: browser login (the watch's tick), bridge login, cancel, logout,
apikey:save, restore and forget all end in loadCodexAuth.

WHAT THESE TESTS ASSERT THAT THE EXISTING ONES DID NOT. test_panel.js's 45n
already pinned that a completed sign-in updates S.codexAuth.state -- and passed
for the whole life of the bug, because nothing looked at the row. Every test
below is about the ROW: what the wire carries, and what an older backend must
not be able to blank.

NOTHING HERE REACHES THE NETWORK OR A REAL KEYCHAIN. `codex` is a shell stub
whose output is the exact line codex-cli 0.153.2 prints, and HOME is redirected
so ~/.codex/auth.json is a file this test owns.
"""
import json
import os
import shutil
import stat
import threading
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_install
import codex_login
import org_api
import providers

#: The exact lines codex-cli 0.153.2 prints, verified 2026-09-04 and recorded
#: in providers._CODEX_API_KEY_RE's comment. Used rather than paraphrased: the
#: parser is what turns these into a billing mode, and a test that invents its
#: own wording would pass while the real line stopped being understood.
_SIGNED_IN = "Logged in using ChatGPT"
_SIGNED_OUT = "Not logged in"


class _Base(unittest.TestCase):
    """A HOME, a settings file and a PATH this test owns outright.

    HOME because `configured` for codex is _codex_credential_present(), i.e.
    does ~/.codex/auth.json EXIST -- existence only, providers.py never opens
    it (a rule in its module docstring), so an empty placeholder is a faithful
    stand-in and carries no secret.
    """

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import app
        cls.client = TestClient(app.app)
        #: app.py's origin guard demands the panel token from anything carrying
        #: an Origin, and refuses a non-loopback one outright. A plain Host and
        #: no Origin is the non-browser lane, which is what a TestClient is.
        cls.H = {"host": "127.0.0.1:8787"}

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

        self._orig_settings = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = self.dir / "settings.json"
        self.addCleanup(setattr, providers, "SETTINGS_PATH", self._orig_settings)

        self.home = self.dir / "home"
        (self.home / ".codex").mkdir(parents=True)
        self._orig_env = dict(os.environ)
        self.addCleanup(self._restore_env)
        os.environ["HOME"] = str(self.home)

        self.bindir = self.dir / "bin"
        self.bindir.mkdir()
        #: Nothing real on PATH. The machine running this very likely HAS a
        #: codex (the maintainer's does), and it would answer the probe with
        #: the maintainer's own credential.
        os.environ["PATH"] = os.pathsep.join([str(self.bindir), "/usr/bin", "/bin"])
        os.environ.pop("SUTRA_UI_CODEX_BIN", None)
        os.environ.pop("SUTRA_UI_PROVIDER", None)

        self._orig_done = providers._LOGIN_PATH_DONE
        providers._LOGIN_PATH_DONE = True
        self.addCleanup(setattr, providers, "_LOGIN_PATH_DONE", self._orig_done)

        kb = mock.patch.object(providers, "_known_bin_dirs", return_value=[])
        kb.start()
        self.addCleanup(kb.stop)

        #: Never let a test start an npm. The kick is asserted by observing the
        #: CALL, not by letting it reach the registry. The PATCHER is kept as
        #: well as the mock, because the two tests that exercise the real kick
        #: have to lift this one -- and `self.kick.stop()` on the mock is a
        #: silent no-op that leaves it patched, which is how the first draft of
        #: those two tests "ran" against a stub that did nothing.
        self.kick_patch = mock.patch.object(org_api, "_codex_kick_install")
        self.kick = self.kick_patch.start()
        self.addCleanup(self.kick_patch.stop)

        codex_login._reset_for_tests()
        self.addCleanup(codex_login._reset_for_tests)

    def _restore_env(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    # ----------------------------------------------------------- fixtures --

    def codex(self, says=_SIGNED_OUT):
        """A `codex` on PATH whose `login status` prints `says`."""
        p = self.bindir / "codex"
        p.write_text('#!/bin/sh\nprintf "%s\\n" "' + says + '"\nexit 0\n')
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def sign_in(self):
        """What `codex login` does to this machine: leaves a credential file."""
        (self.home / ".codex" / "auth.json").write_text("")

    def sign_out(self):
        f = self.home / ".codex" / "auth.json"
        if f.exists():
            f.unlink()

    def auth(self):
        r = self.client.get("/api/providers/codex/auth", headers=self.H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def row(self, payload, pid="codex"):
        return next(p for p in payload["providers"] if p["id"] == pid)


# ------------------------------------------------- what the poll now carries --

class ThePollCarriesTheRowItMoves(_Base):

    def test_the_answer_holds_providers_and_settings(self):
        """Asserting the WIRE, not the fixture. test_deepseek_auth learned this
        one the hard way: the state landed as a sibling of `settings` and
        nothing read it."""
        self.codex()
        got = self.auth()
        self.assertIn("providers", got)
        self.assertIn("settings", got)
        self.assertTrue(any(p["id"] == "codex" for p in got["providers"]))

    def test_the_answer_holds_the_runtime_half_too(self):
        """`providers` says whether a codex resolves; `runtime` says whether
        Sutra could fetch one and why not. The Install control needs the
        second, and it is not derivable from the first."""
        got = self.auth()
        self.assertIn("runtime", got)
        self.assertIn("can_install", got["runtime"])
        self.assertEqual(got["runtime"]["package"], "@openai/codex")

    def test_the_live_credential_is_still_the_top_level_answer(self):
        """Additive. Everything the row read before must still be where it was
        -- an older panel served by a newer backend keeps working."""
        self.codex(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        self.assertEqual(got["state"], "chatgpt")
        self.assertIn("billing", got)
        self.assertIn("login_in_flight", got)
        self.assertIn("stored", got)

    def test_the_saved_key_state_is_not_the_runtime_state(self):
        """Three independent facts in one answer: which credential is live,
        whether Sutra holds a copy of a key, and whether a binary exists.
        Collapsing any two is how a row starts claiming something nobody read."""
        got = self.auth()
        self.assertNotIn("installed", got["stored"])
        self.assertNotIn("stored", got["runtime"])


class SigningInMovesTheRowOnTheSameAnswer(_Base):
    """The bug, stated as the behaviour that was missing."""

    def test_a_credential_written_after_boot_reaches_the_row(self):
        """This is the whole failure: the file appears while the window is
        open, and the answer the panel is already reading has to carry it."""
        self.codex(_SIGNED_OUT)
        before = self.row(self.auth())
        self.assertFalse(before["configured"])
        self.assertFalse(before["runnable"])

        self.codex(_SIGNED_IN)
        self.sign_in()

        after = self.row(self.auth())
        self.assertTrue(after["configured"])
        self.assertTrue(after["runnable"], "the row is still not selectable")

    def test_the_row_stays_unrunnable_when_there_is_no_binary(self):
        """AUTHENTICATION IS NOT READINESS. A credential file with no CLI is
        not a usable provider, and the row must not say it is."""
        self.sign_in()                       # credential, but no `codex`
        got = self.auth()
        self.assertEqual(got["state"], "no_binary")
        self.assertFalse(self.row(got)["runnable"])
        self.assertFalse(self.row(got)["installed"])

    def test_settings_re_resolves_the_active_provider(self):
        """`settings` is what makes the fallback correct. load_settings() re-runs
        active_provider_detail(), so the panel gets the new answer rather than
        boot()'s."""
        self.codex(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        self.assertIn("provider", got["settings"])
        self.assertIn("provider_ignored", got["settings"])


class SigningOutMovesItBack(_Base):
    """The same staleness, in the direction that matters more: a row saying
    "Ready to use" over a Codex with no credential is an offer that dies at the
    first message."""

    def logout(self):
        r = self.client.post("/api/providers/codex/logout",
                             json={"confirm": True}, headers=self.H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_the_logout_answer_carries_the_row(self):
        self.codex(_SIGNED_IN)
        self.sign_in()
        self.assertTrue(self.row(self.auth())["runnable"])

        # `codex logout` removes the credential; the stub stands in for it.
        p = self.bindir / "codex"
        p.write_text('#!/bin/sh\nprintf "%s\\n" "' + _SIGNED_OUT + '"\nexit 0\n')
        p.chmod(0o755)
        self.sign_out()

        out = self.logout()
        self.assertIn("providers", out)
        self.assertIn("settings", out)
        self.assertFalse(self.row(out)["runnable"],
                         "the row still offers a signed-out Codex")

    def test_the_fresh_probe_is_still_nested_under_auth(self):
        """Unchanged shape. The panel reads out.auth for the credential and the
        new keys for the row; neither may displace the other."""
        self.codex(_SIGNED_OUT)
        out = self.logout()
        self.assertIn("auth", out)
        self.assertIn("state", out["auth"])
        self.assertIn("login_in_flight", out["auth"])

    def test_a_failed_logout_still_reports_the_truth_about_the_machine(self):
        """A logout that FAILED must not leave the row showing a state nobody
        verified."""
        p = self.bindir / "codex"
        p.write_text('#!/bin/sh\nif [ "$1" = "logout" ]; then exit 3; fi\n'
                     'printf "%s\\n" "' + _SIGNED_IN + '"\nexit 0\n')
        p.chmod(0o755)
        self.sign_in()
        out = self.logout()
        self.assertFalse(out["ok"])
        self.assertIn("providers", out)
        self.assertTrue(self.row(out)["runnable"],
                        "the credential is still there and the row must say so")

    def test_confirm_is_still_required(self):
        """The client-side dialog is not the gate. Unchanged by this work, and
        pinned here because the response shape around it moved."""
        self.codex()
        r = self.client.post("/api/providers/codex/logout", json={},
                             headers=self.H)
        self.assertEqual(r.status_code, 400)


class CancellationAndFailureLeaveTheTruthInPlace(_Base):

    def test_a_cancel_answers_and_changes_nothing(self):
        self.codex(_SIGNED_OUT)
        r = self.client.post("/api/providers/codex/login/cancel", json={},
                             headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["cancelled"])
        self.assertFalse(self.row(self.auth())["runnable"])

    def test_a_login_with_no_binary_is_refused_and_kicks_the_install(self):
        """The operator asked for Codex (intent) and there is none (gap). The
        refusal is unchanged -- this route promises a browser window, not a
        300-second download -- but the runtime is provisioned regardless of
        what the browser does next."""
        r = self.client.post("/api/providers/codex/login", json={},
                             headers=self.H)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "CODEX_NOT_ON_PATH")
        self.assertTrue(self.kick.called, "nothing provisions the runtime")

    def test_a_login_that_starts_does_not_kick_anything(self):
        """There is a codex, so there is nothing to fetch. An install fired
        here would be the app downloading software nobody needs."""
        self.codex(_SIGNED_OUT)
        with mock.patch.object(codex_login, "start",
                               return_value={"started": True, "pid": 1,
                                             "cap_seconds": 180}):
            r = self.client.post("/api/providers/codex/login", json={},
                                 headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.kick.called)

    def test_an_unreadable_probe_never_reads_as_signed_out(self):
        """A codex that answers in a shape this build does not know is
        `unknown`, and the row must not be promoted off it."""
        p = self.bindir / "codex"
        p.write_text('#!/bin/sh\necho "something else entirely"\nexit 2\n')
        p.chmod(0o755)
        got = self.auth()
        self.assertEqual(got["state"], "unknown")
        self.assertIsNone(got["billing"])
        self.assertIn("providers", got, "the row must still be answered")


class TheAnswerCostsExactlyOneProbe(_Base):
    """The endpoint already spawns `codex login status`, and this change adds
    provider discovery and a settings read to it. Neither may become a second
    subprocess: this rides on a 2-second poll during a sign-in."""

    def test_no_extra_subprocess_is_introduced(self):
        self.codex(_SIGNED_IN)
        self.sign_in()
        seen = []
        real = subprocess.run

        def spy(args, *a, **kw):
            seen.append(args)
            return real(args, *a, **kw)

        with mock.patch.object(subprocess, "run", side_effect=spy):
            self.auth()
        self.assertEqual(len(seen), 1,
                         "the poll spawned %d processes: %r" % (len(seen), seen))
        self.assertEqual(list(seen[0])[1:], ["login", "status"])

    def test_the_runtime_half_spawns_nothing(self):
        """codex_install.state() is on this path and must stay subprocess-free
        -- the reason it has no `verified` field."""
        with mock.patch.object(subprocess, "run",
                               side_effect=AssertionError("state() spawned")):
            codex_install.state()


# ------------------------------------------------------------- the gate ------

class InstallingAnExecutableIsGated(_Base):
    """Note the asymmetry with the sign-in routes, which are deliberately open:
    `codex login` carries no credential and hands a local caller nothing it
    could not do in a shell. Fetching and registering a binary is not in that
    class."""

    def test_an_untokened_caller_is_refused(self):
        r = self.client.post("/api/providers/codex/cli", json={}, headers=self.H)
        self.assertEqual(r.status_code, 403)

    def test_the_refusal_never_starts_an_install(self):
        with mock.patch.object(codex_install, "install") as ran:
            self.client.post("/api/providers/codex/cli", json={}, headers=self.H)
        self.assertFalse(ran.called)

    def test_a_bad_panel_token_is_refused(self):
        r = self.client.post("/api/providers/codex/cli", json={},
                             headers={**self.H, "x-sutra-panel": "not-the-token"})
        self.assertEqual(r.status_code, 403)

    def test_the_panel_token_opens_it(self):
        """THE LANE THAT MAKES THE FEATURE WORK, and the one a straight copy of
        _deepseek_write_control would not have had. On a desktop-started server
        the renderer holds no desktop token (main.js keeps it in the main
        process) and deepseek_session mints no code, so without this the Sutra
        app's own window -- the primary user -- met a 403."""
        import app
        with mock.patch.object(codex_install, "install",
                               return_value={"ok": True, "code": "ALREADY",
                                             "bin_path": "/x/codex",
                                             "managed": False, "version": None,
                                             "took_ms": 0, "message": "already"}):
            r = self.client.post(
                "/api/providers/codex/cli", json={},
                headers={**self.H, "x-sutra-panel": app.PANEL_TOKEN})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["ok"])

    def test_the_panel_lane_works_on_a_desktop_started_server_too(self):
        """The exact configuration that was broken: DESKTOP_TOKEN set, so no
        session code is ever minted, and the panel has only its own token."""
        import app
        with mock.patch.object(org_api, "DESKTOP_TOKEN", "t0ken"), \
             mock.patch.object(codex_install, "install",
                               return_value={"ok": True, "code": "ALREADY",
                                             "bin_path": "/x/codex",
                                             "managed": False, "version": None,
                                             "took_ms": 0, "message": "already"}):
            r = self.client.post(
                "/api/providers/codex/cli", json={},
                headers={**self.H, "x-sutra-panel": app.PANEL_TOKEN})
        self.assertEqual(r.status_code, 200, r.text)

    def test_the_route_takes_no_arguments(self):
        """What makes the panel lane defensible: the package, the version and
        the destination are constants in codex_install, so a caller chooses
        nothing and the only obtainable effect is the one pinned CLI."""
        import inspect
        sig = inspect.signature(org_api.api_codex_cli_install)
        self.assertEqual(list(sig.parameters), ["request"])

    def test_the_desktop_token_opens_it(self):
        with mock.patch.object(org_api, "DESKTOP_TOKEN", "t0ken"), \
             mock.patch.object(codex_install, "install",
                               return_value={"ok": True, "code": "ALREADY",
                                             "bin_path": "/x/codex",
                                             "managed": False, "version": None,
                                             "took_ms": 0, "message": "already"}):
            r = self.client.post("/api/providers/codex/cli", json={},
                                 headers={**self.H,
                                          "x-sutra-desktop-token": "t0ken"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["ok"])

    def test_a_refused_install_still_answers_200_with_the_state(self):
        """The rows correct themselves even when the install did not happen.
        4xx stays for the things that really are protocol problems."""
        err = codex_install.CodexInstallError("NO_NPM", "there is no npm here")
        with mock.patch.object(org_api, "DESKTOP_TOKEN", "t0ken"), \
             mock.patch.object(codex_install, "install", side_effect=err):
            r = self.client.post("/api/providers/codex/cli", json={},
                                 headers={**self.H,
                                          "x-sutra-desktop-token": "t0ken"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["code"], "NO_NPM")
        self.assertIn("providers", body)
        self.assertIn("runtime", body)

    def test_a_successful_install_carries_the_row_too(self):
        with mock.patch.object(org_api, "DESKTOP_TOKEN", "t0ken"), \
             mock.patch.object(codex_install, "install",
                               return_value={"ok": True, "code": "INSTALLED",
                                             "bin_path": "/x/codex",
                                             "managed": True, "version": "0.153.2",
                                             "took_ms": 10, "message": "done"}):
            r = self.client.post("/api/providers/codex/cli", json={},
                                 headers={**self.H,
                                          "x-sutra-desktop-token": "t0ken"})
        body = r.json()
        self.assertIn("providers", body)
        self.assertIn("settings", body)


class NothingHereTouchesACredential(_Base):
    """The authentication model is unchanged by this work, and that is an
    invariant worth pinning rather than asserting in a commit message.

    Sutra supports BOTH a ChatGPT sign-in and a saved API key, and a user may
    keep the key saved while using ChatGPT so they can switch back.
    codex_install exists to fetch a binary and has no path to any of it.
    """

    #: What codex_install must not be able to REACH. Checked against the parsed
    #: module rather than its text: the docstring explains at length why this
    #: module is not codex_auth and what auth.json is, and a substring sweep
    #: cannot tell that prose from a call. A provable negative has to be about
    #: the code.
    _FORBIDDEN = frozenset({
        "codex_auth", "deepseek_auth", "keyring", "keychain",
        "get_secret", "put_secret", "delete_secret",
        "KEYCHAIN_SERVICE", "KEYCHAIN_ACCOUNT", "read_or_reason", "restore",
    })

    def _names_used_by(self, module_file):
        """Every identifier the module actually references: imports, bare
        names, and the attribute halves of dotted access."""
        import ast
        tree = ast.parse(Path(__file__).with_name(module_file).read_text())
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                used.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                used.add((node.module or "").split(".")[0])
                used.update(a.name for a in node.names)
            elif isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
        return used

    def test_the_install_module_cannot_reach_a_credential(self):
        """codex_install fetches a binary. It has no path to the ChatGPT
        session, to Sutra's saved API key, or to the keychain either lives in --
        so nothing it does can delete, overwrite or invalidate either one."""
        used = self._names_used_by("codex_install.py")
        self.assertEqual(used & self._FORBIDDEN, set())

    def test_the_install_module_never_spawns_a_codex_subcommand(self):
        """`--version` and nothing else. `login`, `logout` and `login status`
        all read or write the credential; a provisioning module that could
        reach them is one refactor away from signing somebody out."""
        import ast
        tree = ast.parse(Path(__file__).with_name("codex_install.py").read_text())
        literals = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for verb in ("login", "logout", "login status", "--with-api-key"):
            self.assertNotIn(verb, literals,
                             "codex_install must not name the %r verb" % verb)
        self.assertIn("--version", literals)

    def test_the_kick_calls_the_install_and_nothing_else(self):
        """Every other test in this file patches the kick out. This one runs
        the real thing with the INSTALL patched instead, so what the daemon
        thread actually does is pinned rather than assumed."""
        self.kick_patch.stop()                    # the real one, just here
        self.addCleanup(self.kick_patch.start)
        done = threading.Event()
        with mock.patch.object(codex_install, "install",
                               side_effect=lambda *a, **k: done.set()) as ran:
            org_api._codex_kick_install()
            self.assertTrue(done.wait(timeout=10), "the kick never ran")
        self.assertEqual(ran.call_args, mock.call())

    def test_a_failing_kick_is_swallowed_not_raised(self):
        """There is no channel to report into -- the login response has already
        been computed -- and a failure is not lost: the row still reads "not
        installed" with its own reason, and the Install button is still there."""
        self.kick_patch.stop()
        self.addCleanup(self.kick_patch.start)
        done = threading.Event()

        def boom(*a, **k):
            done.set()
            raise codex_install.CodexInstallError("NO_NPM", "nope")

        with mock.patch.object(codex_install, "install", side_effect=boom):
            org_api._codex_kick_install()
            self.assertTrue(done.wait(timeout=10))

    def test_signing_in_does_not_disturb_a_saved_key(self):
        """A saved key survives a ChatGPT sign-in -- the two are not mutually
        exclusive, and nothing in this change may make them so. `stored` is
        Sutra's own copy and is reported independently of the live mode."""
        self.codex(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        self.assertEqual(got["state"], "chatgpt")
        self.assertIn("stored", got)
        self.assertIn("store_available", got["stored"])


# ------------------------------------- the GLOBAL plan-usage route -----------
# WHY THIS CLASS EXISTS SEPARATELY FROM test_codex_models.py. That file pins the
# MAPPER and the auth gate inside codex_models -- given this JSON, these windows;
# given this state, no spawn. It reaches refresh_plan_if_stale() directly and so
# never proves that the ROUTE reads the auth state at all. Nothing tested that
# GET /api/providers/codex/plan gates on the live credential rather than
# trusting a caller, which is the one claim the whole feature rests on: the
# indicator has to disappear on a credential change, and the request has to not
# be sent in API-key mode.
#
# So every assertion below goes through the wire, and the auth state is set the
# way the machine sets it -- what `codex login status` prints plus whether
# ~/.codex/auth.json exists -- never by patching a state in.
#
# THE STUB IS ONE BINARY WITH TWO JOBS, because the real one is. `codex login
# status` answers the probe and `codex app-server` answers the rate-limit read,
# and the route calls both in that order. The script branches on $1 and APPENDS
# A LINE TO A TRACE FILE on every app-server start -- which is what makes "API
# key mode never asks" and "the cache prevents repeated spawning" observable as
# facts about the route rather than about a mock.

#: The exact line 0.153.2 prints for a saved key, from providers._CODEX_API_KEY_RE.
_API_KEY_LINE = "Logged in using an API key - sk-...abcd"

#: The shape measured live on 2026-09-09: planType "go", ONE 30-day window, no
#: `secondary`, credits all-null. Duplicated from test_codex_models rather than
#: imported so this file stays runnable on its own, and kept verbatim because it
#: is the answer that disproves the "5-hour and weekly" assumption.
_PLAN_MEASURED = {
    "rateLimits": {"primary": {"usedPercent": 5, "windowDurationMins": 43200,
                               "resetsAt": 1791134890},
                   "planType": "go", "limitId": "codex",
                   "rateLimitReachedType": None,
                   "credits": {"hasCredits": False, "unlimited": False,
                               "balance": None}},
    "rateLimitResetCredits": {"availableCount": 0},
}


class ThePlanRouteGatesOnTheLiveCredential(_Base):
    """GET /api/providers/codex/plan, end to end over the wire."""

    def setUp(self):
        super().setUp()
        import codex_models
        self.codex_models = codex_models
        codex_models._reset_plan_for_tests()
        self.addCleanup(codex_models._reset_plan_for_tests)
        #: Written by the stub, one line per `codex app-server` start.
        self.trace = self.dir / "app-server-starts"

    # ----------------------------------------------------------- fixtures --

    def codex_plan(self, says, result=_PLAN_MEASURED, answer=True):
        """A `codex` that answers BOTH `login status` and `app-server`.

        `answer=False` makes app-server exit non-zero -- an RPC failure, which
        the route has to survive rather than 500 on.
        """
        body = ("cat <<'JSON'\n" + json.dumps({"id": 2, "result": result})
                + "\nJSON\n") if answer else "exit 1\n"
        script = (
            '#!/bin/sh\n'
            'if [ "$1" = "app-server" ]; then\n'
            '  echo start >> "%s"\n'
            '  read _a\n'
            '  echo \'{"id":1,"result":{"codexHome":"/tmp"}}\'\n'
            '  read _b\n'
            '  %s'
            '  cat > /dev/null\n'
            '  exit 0\n'
            'fi\n'
            'printf "%%s\\n" "%s"\n'
            'exit 0\n'
        ) % (self.trace, body, says)
        p = self.bindir / "codex"
        p.write_text(script)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def plan(self):
        r = self.client.get("/api/providers/codex/plan", headers=self.H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def starts(self):
        """How many times `codex app-server` was actually started."""
        if not self.trace.exists():
            return 0
        return len([l for l in self.trace.read_text().splitlines() if l.strip()])

    # ------------------------------------------- chatgpt: it is reported ----

    def test_a_chatgpt_signin_gets_the_plan_over_the_wire(self):
        self.codex_plan(_SIGNED_IN)
        self.sign_in()
        got = self.plan()
        self.assertEqual(got["state"], "chatgpt")
        w = got["plan"]["windows"]
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0]["used_percent"], w[0]["duration_mins"],
                          w[0]["resets_at"]), (5.0, 43200, 1791134890))
        self.assertEqual(got["plan"]["plan_type"], "go")

    def test_the_route_names_no_window_duration_of_its_own(self):
        """WINDOW DURATIONS ARE DATA. Whatever OpenAI returns is what comes
        back -- a route that recognised 300 or 10080 specially would mislabel
        the measured account, which returns neither."""
        for mins in (5, 300, 1440, 10080, 43200, 99999):
            self.codex_models._reset_plan_for_tests()
            self.codex_plan(_SIGNED_IN, {"rateLimits": {
                "primary": {"usedPercent": 3, "windowDurationMins": mins}}})
            self.sign_in()
            got = self.plan()
            self.assertEqual(got["plan"]["windows"][0]["duration_mins"], mins,
                             "duration %r did not survive the route" % mins)

    def test_primary_and_secondary_both_cross_the_wire(self):
        self.codex_plan(_SIGNED_IN, {"rateLimits": {
            "primary": {"usedPercent": 12, "windowDurationMins": 300,
                        "resetsAt": 111},
            "secondary": {"usedPercent": 44, "windowDurationMins": 10080,
                          "resetsAt": 222}}})
        self.sign_in()
        got = self.plan()
        self.assertEqual([(w["duration_mins"], w["used_percent"])
                          for w in got["plan"]["windows"]],
                         [(300, 12.0), (10080, 44.0)])

    def test_several_metered_limits_all_cross_the_wire(self):
        self.codex_plan(_SIGNED_IN, {"rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 7, "windowDurationMins": 300},
                      "planType": "plus"},
            "other": {"primary": {"usedPercent": 9,
                                  "windowDurationMins": 10080}}}})
        self.sign_in()
        got = self.plan()
        self.assertEqual(sorted(w["duration_mins"]
                                for w in got["plan"]["windows"]),
                         [300, 10080])

    def test_absent_credits_are_absent_and_not_a_zero(self):
        """THE null RULE, asserted on the wire. The measured answer is
        {hasCredits:false, unlimited:false, balance:null} -- "no credits here",
        not "your balance is zero"."""
        self.codex_plan(_SIGNED_IN)
        self.sign_in()
        self.assertIsNone(self.plan()["plan"]["credits"])

    def test_reported_credits_cross_the_wire(self):
        self.codex_plan(_SIGNED_IN, {"rateLimits": {
            "primary": {"usedPercent": 1},
            "credits": {"hasCredits": True, "unlimited": False,
                        "balance": "12.50"}}})
        self.sign_in()
        self.assertEqual(self.plan()["plan"]["credits"]["balance"], "12.50")

    # -------------------------------------- everything else: it is hidden ---

    def test_api_key_mode_gets_no_plan_AND_STARTS_NO_APP_SERVER(self):
        """The strongest claim in the feature. An API key has no plan to have
        an allowance of, so this must not merely hide the answer -- the request
        must never be sent."""
        self.codex_plan(_API_KEY_LINE)
        self.sign_in()
        got = self.plan()
        self.assertEqual(got["state"], "api_key")
        self.assertIsNone(got["plan"])
        self.assertEqual(self.starts(), 0, "api_key mode started an app-server")

    def test_logged_out_gets_no_plan_and_starts_no_app_server(self):
        self.codex_plan(_SIGNED_OUT)
        self.sign_out()
        got = self.plan()
        self.assertEqual(got["state"], "logged_out")
        self.assertIsNone(got["plan"])
        self.assertEqual(self.starts(), 0, "a sign-out started an app-server")

    def test_no_binary_gets_no_plan(self):
        self.sign_out()
        got = self.plan()
        self.assertEqual(got["state"], "no_binary")
        self.assertIsNone(got["plan"])

    # ------------------------------------------------ auth TRANSITIONS ------

    def test_chatgpt_then_logout_makes_the_plan_GO_AWAY(self):
        """Not stale -- gone. A percentage left on screen after a sign-out
        describes an allowance nothing is metering any more."""
        self.codex_plan(_SIGNED_IN)
        self.sign_in()
        self.assertIsNotNone(self.plan()["plan"])
        self.codex_plan(_SIGNED_OUT)
        self.sign_out()
        self.assertIsNone(self.plan()["plan"])
        self.assertIsNone(self.codex_models.plan_cached())

    def test_chatgpt_then_api_key_makes_the_plan_GO_AWAY(self):
        self.codex_plan(_SIGNED_IN)
        self.sign_in()
        self.assertIsNotNone(self.plan()["plan"])
        self.codex_plan(_API_KEY_LINE)
        before = self.starts()
        self.assertIsNone(self.plan()["plan"])
        self.assertEqual(self.starts(), before,
                         "switching to an API key still asked for a plan")

    def test_api_key_then_chatgpt_FETCHES_the_plan(self):
        """The other direction has to work too, and from a cache that was
        emptied by the API-key read rather than left holding a stale None."""
        self.codex_plan(_API_KEY_LINE)
        self.sign_in()
        self.assertIsNone(self.plan()["plan"])
        self.codex_plan(_SIGNED_IN)
        self.assertIsNotNone(self.plan()["plan"])

    # ------------------------------------------------------- cost + failure -

    def test_repeated_gets_inside_the_ttl_start_ONE_app_server(self):
        """This route rides loadUsage(), which fires on boot, on screen open
        and after every completed turn. Without the TTL that is one app-server
        per paint."""
        self.codex_plan(_SIGNED_IN)
        self.sign_in()
        for _ in range(4):
            self.plan()
        self.assertEqual(self.starts(), 1,
                         "started %d app-servers for 4 reads" % self.starts())

    def test_an_rpc_failure_is_a_200_with_no_plan_not_a_500(self):
        """The indicator has to stay responsive when the read fails: drawing
        nothing is the state before this feature existed, and a 500 here would
        break the global usage load for every provider."""
        self.codex_plan(_SIGNED_IN, answer=False)
        self.sign_in()
        got = self.plan()
        self.assertEqual(got["state"], "chatgpt")
        self.assertIsNone(got["plan"])

    def test_a_plan_read_does_not_disturb_the_model_roster(self):
        """The two reads share a transport, not a cache. A plan refresh that
        invalidated the model list would empty the picker every minute."""
        self.codex_plan(_SIGNED_IN)
        self.sign_in()
        self.codex_models._CACHE.update(
            {"models": ({"id": "m-alpha"},), "state": "chatgpt",
             "at": __import__("time").time()})
        self.plan()
        self.assertEqual([m["id"] for m in self.codex_models.cached()],
                         ["m-alpha"])


# ======================= what the poll carries for the PICKER ==============
# THE SAME BUG, ONE LINK FURTHER ALONG (2026-09-09). The class above pins that
# the ROW moves on the answer that observed the sign-in. The MODEL PICKER did
# not, and for a reason no test above could catch: the published model list is a
# SIBLING of `settings` in the /settings payload, not a key inside it, so
# carrying `settings` on this route never carried the models.
#
# Measured before the fix, on a real account with a working model/list:
#
#   panel boot   GET /api/settings              -> codex: ['']
#   screen opens GET /providers/codex/auth      -> warms discovery, publishes
#                                                  providers/settings/runtime
#                                                  and NOT the models
#   (nothing re-reads /api/settings)            -> picker: "CLI default" alone
#   same backend GET /api/settings              -> codex: ['', <5 models>]
#
# The client half is pinned in test_panel.js §53; this half is the wire.
#
# ONE BINARY, TWO JOBS, exactly like codex_plan above: `login status` answers
# the probe and `app-server` answers model/list. The trace file makes "this
# route starts one app-server, not two" a fact about the ROUTE.

#: Ids that exist in NO catalogue -- static or real. A fixture that reused a
#: shipping id would pass just as well against a hardcoded list, which is the
#: one thing these tests exist to refuse.
_DISCOVERED = [
    {"id": "m-discovered-one", "model": "m-discovered-one",
     "displayName": "Discovered One", "description": "the default one",
     "hidden": False, "isDefault": True,
     "supportedReasoningEfforts": ["low", "medium", "high"]},
    {"id": "m-discovered-two", "model": "m-discovered-two",
     "displayName": "Discovered Two", "description": "the other one",
     "hidden": False, "isDefault": False,
     "supportedReasoningEfforts": ["low", "medium"]},
]
_DISCOVERED_HIDDEN = [
    {"id": "m-internal", "displayName": "Internal", "hidden": True},
]


class ThePollCarriesTheModelsThePickerNeeds(_Base):
    """GET /api/providers/codex/auth, end to end over the wire."""

    def setUp(self):
        super().setUp()
        import codex_models
        self.codex_models = codex_models
        #: The discovery cache is module state and the route reads it. Without
        #: this a list left behind by another test in this file would answer
        #: here, which is how a passing test proves nothing.
        codex_models._reset_for_tests()
        self.addCleanup(codex_models._reset_for_tests)
        self.trace = self.dir / "app-server-starts"

    # ----------------------------------------------------------- fixtures --

    def codex_models_stub(self, says, data=_DISCOVERED, answer=True):
        """A `codex` answering BOTH `login status` and `app-server`/model/list.

        `answer=False` makes app-server exit non-zero -- discovery failing,
        which the route must survive with the pre-discovery list rather than
        a 500 or an empty picker.
        """
        body = ("cat <<'JSON'\n" + json.dumps({"id": 2, "result": {"data": data}})
                + "\nJSON\n") if answer else "exit 1\n"
        script = (
            '#!/bin/sh\n'
            'if [ "$1" = "app-server" ]; then\n'
            '  echo start >> "%s"\n'
            '  read _a\n'
            '  echo \'{"id":1,"result":{"codexHome":"/tmp"}}\'\n'
            '  read _b\n'
            '  %s'
            '  cat > /dev/null\n'
            '  exit 0\n'
            'fi\n'
            'printf "%%s\\n" "%s"\n'
            'exit 0\n'
        ) % (self.trace, body, says)
        p = self.bindir / "codex"
        p.write_text(script)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def starts(self):
        if not self.trace.exists():
            return 0
        return len([l for l in self.trace.read_text().splitlines() if l.strip()])

    def picker(self, payload):
        """The ids the Model dropdown would render, in menu order."""
        return [m["id"] for m in payload["models_by_provider"]["codex"]]

    # ------------------------------------------------------- 1. the wire ----

    def test_the_answer_holds_models_by_provider(self):
        """Asserting the WIRE, not the fixture. This key's absence WAS the bug,
        and every other assertion in this file passed throughout it."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        self.assertIn("models_by_provider", got)
        self.assertIn("codex", got["models_by_provider"])

    # ------------------------------------------- 2. discovered, not static --

    def test_the_models_are_the_DISCOVERED_ones(self):
        """The ids come from model/list, so a payload built off the STATIC
        catalogue tuple cannot produce them -- which is what makes this the
        assertion the old code fails."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        self.assertEqual(self.picker(got),
                         ["", "m-discovered-one", "m-discovered-two"])
        entry = got["models_by_provider"]["codex"][1]
        self.assertEqual(entry["name"], "Discovered One")
        self.assertIn("the default one", entry["note"])
        self.assertTrue(entry["default"])

    def test_hidden_models_still_never_reach_the_picker(self):
        self.codex_models_stub(_SIGNED_IN, _DISCOVERED + _DISCOVERED_HIDDEN)
        self.sign_in()
        self.assertNotIn("m-internal", self.picker(self.auth()))

    # -------------------------------------------------- 7. CLI default ------

    def test_cli_default_is_still_first_and_keeps_the_empty_id(self):
        """The fallback the whole feature degrades to. It is FIRST so the menu
        opens on "leave it to codex", and its id is "" so choosing it emits no
        -m at all."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        first = self.auth()["models_by_provider"]["codex"][0]
        self.assertEqual((first["id"], first["name"]), ("", "CLI default"))

    def test_failed_discovery_leaves_cli_default_alone_rather_than_nothing(self):
        """Discovery is best-effort. A dead app-server must degrade to exactly
        the payload that shipped before the feature -- never an empty picker,
        and never a 500 on the provider screen."""
        self.codex_models_stub(_SIGNED_IN, answer=False)
        self.sign_in()
        got = self.auth()
        self.assertEqual(self.picker(got), [""])
        self.assertEqual(got["state"], "chatgpt")

    # ---------------------------------------- 5 + 6. BOTH credentials -------

    def test_a_chatgpt_signin_publishes_its_models(self):
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        self.assertEqual(got["state"], "chatgpt")
        self.assertEqual(self.picker(got),
                         ["", "m-discovered-one", "m-discovered-two"])

    def test_an_api_key_publishes_its_models_too(self):
        """NOT a copy of the test above. A ChatGPT plan and an API key are
        scoped by different things, so the picker has to be correct for each
        WITHOUT either being assumed to offer the other's list -- and the
        measured symptom was that both were stuck on "CLI default"."""
        self.codex_models_stub(_API_KEY_LINE)
        self.sign_in()
        got = self.auth()
        self.assertEqual(got["state"], "api_key")
        self.assertEqual(self.picker(got),
                         ["", "m-discovered-one", "m-discovered-two"])

    def test_a_credential_change_republishes_the_list(self):
        """The state is part of the discovery cache key, and the answer that
        observed the change is the one that must carry the new list."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        self.assertEqual(self.auth()["state"], "chatgpt")
        self.codex_models_stub(_API_KEY_LINE, [_DISCOVERED[1]])
        got = self.auth()
        self.assertEqual(got["state"], "api_key")
        self.assertEqual(self.picker(got), ["", "m-discovered-two"])

    # --------------------------------------- 8. the selection reaches -m ----

    def test_a_model_the_picker_now_offers_reaches_dash_m(self):
        """THE POINT OF THE PICKER. An id is only worth offering if it survives
        validation and lands in argv, so this walks the last two links of the
        chain with an id that came off the wire above -- not a literal."""
        import app
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        chosen = self.picker(self.auth())[1]
        self.assertEqual(providers.clean_model(chosen, "codex"), chosen,
                         "the picker offered an id the validator refuses")
        args = app.build_codex_args("/bin/codex", "plan", "/w", model=chosen)
        self.assertIn("-m", args)
        self.assertEqual(args[args.index("-m") + 1], chosen)

    def test_cli_default_still_emits_no_dash_m(self):
        """"" is not a model, it is the absence of one."""
        import app
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        self.assertEqual(self.picker(self.auth())[0], "")
        self.assertNotIn("-m", app.build_codex_args("/bin/codex", "plan", "/w",
                                                    model=""))

    # ------------------------------- 9. the efforts follow the selection ----

    def test_the_discovered_efforts_ride_along_per_model(self):
        """The Reasoning-effort control offers the SELECTED model's efforts, and
        the client resolves that off this same payload -- so the per-model sets
        have to cross the wire attached to their own model."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        rows = {m["id"]: m for m in self.auth()["models_by_provider"]["codex"]}
        self.assertEqual(rows["m-discovered-one"]["efforts"],
                         ["low", "medium", "high"])
        self.assertEqual(rows["m-discovered-two"]["efforts"], ["low", "medium"])
        self.assertEqual(providers.codex_efforts_for("m-discovered-two"),
                         ("low", "medium"))

    # ------------------------------------------- what must NOT have moved ---

    def test_the_route_starts_exactly_one_app_server(self):
        """NO NEW SUBPROCESS. all_models_by_provider() reads the cache
        refresh_if_stale() just filled; if it spawned, this would be two."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        self.auth()
        self.assertEqual(self.starts(), 1,
                         "the picker's list cost an extra app-server")

    def test_the_existing_answer_is_untouched(self):
        """ADDITIVE. Everything the row already read must still be where it
        was -- an older panel served by a newer backend keeps working."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        got = self.auth()
        for key in ("state", "billing", "login_in_flight", "stored",
                    "providers", "settings", "runtime"):
            self.assertIn(key, got, key)

    def test_claude_and_deepseek_lists_cross_the_wire_unchanged(self):
        """The map is every provider's, so this route now publishes Claude's and
        DeepSeek's too. They are the STATIC catalogue tuples verbatim -- a Codex
        discovery must not be able to touch either, and gemini must stay ABSENT
        rather than gaining an empty picker."""
        self.codex_models_stub(_SIGNED_IN)
        self.sign_in()
        pub = self.auth()["models_by_provider"]
        for pid in ("claude", "deepseek"):
            spec = next(s for s in providers._CATALOG if s["id"] == pid)
            self.assertEqual(pub[pid], list(spec["models"]), pid)
        self.assertNotIn("gemini", pub)


if __name__ == "__main__":
    unittest.main()
