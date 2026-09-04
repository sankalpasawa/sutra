"""test_codex_login.py -- the server-side `codex login` / `codex logout` spawns.

THE LOAD-BEARING TEST IN THIS FILE IS THE FIRST ONE: that start() returns while
the child is STILL ALIVE. It is asserted against a real long-lived process, not
a mocked Popen, because a mock makes the property tautological -- of course a
fake returns immediately. The whole design exists because `codex login` waits
on a human, and holding that open as an HTTP request would park a threadpool
worker, leave the panel nothing to cancel (apiGet has no timeout), and orphan
the child on a page reload.

Every test here substitutes a SCRIPT for the codex binary. Nothing in this file
runs the real `codex login`: that would open a browser and replace whatever
credential the developer is signed in with.

Canaries below are deliberately NOT key-shaped. A realistic-looking key in a
source file is what PROTO-004 exists to stop, and a leak test does not need
one -- any unique string proves the same thing.
"""
import os
import stat
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import codex_login

#: Unique, and not shaped like a credential. See the module docstring.
CANARY = "LEAK-CANARY-4f2a91"


def _script(body, path):
    """Write an executable stand-in for the codex binary."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


class CodexLoginBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="codex-login-test-")
        self._orig = (codex_login.CAP_SECONDS, codex_login.KILL_GRACE,
                      codex_login.LOGOUT_TIMEOUT)
        self.addCleanup(self._teardown)

    def _teardown(self):
        (codex_login.CAP_SECONDS, codex_login.KILL_GRACE,
         codex_login.LOGOUT_TIMEOUT) = self._orig
        # Never leave a child of a test running.
        try:
            codex_login.cancel()
        except Exception:                          # noqa: BLE001
            pass
        codex_login._reset_for_tests()

    def _bin(self, body):
        path = _script(body, os.path.join(self.dir, "codex"))
        return mock.patch.object(codex_login.providers, "provider_bin",
                                 return_value=path)

    def _sleeper(self, seconds=30):
        return self._bin("sleep %s" % seconds)

    def _wait_until_idle(self, limit=10):
        deadline = time.monotonic() + limit
        while codex_login.state()["busy"] and time.monotonic() < deadline:
            time.sleep(0.05)


class StartDoesNotBlock(CodexLoginBase):
    def test_start_returns_while_the_child_is_still_running(self):
        """THE test. A real process that outlives the call, so "returns
        immediately" is a measurement rather than a property of a mock."""
        with self._sleeper():
            t0 = time.monotonic()
            out = codex_login.start()
            elapsed = time.monotonic() - t0
        self.assertTrue(out["started"])
        self.assertLess(elapsed, 1.0,
                        "start() blocked for %.2fs -- an HTTP request would be "
                        "held open for the whole browser round-trip" % elapsed)
        self.assertTrue(codex_login.in_flight(),
                        "the child must still be running when start() returns; "
                        "if it is not, this test proves nothing")
        self.assertEqual(out["cap_seconds"], codex_login.CAP_SECONDS)

    def test_the_pid_is_a_real_live_process(self):
        with self._sleeper():
            pid = codex_login.start()["pid"]
        os.kill(pid, 0)          # raises only if the process is gone

    def test_no_binary_is_refused_without_spawning(self):
        with mock.patch.object(codex_login.providers, "provider_bin",
                               return_value=None), \
             mock.patch.object(codex_login.subprocess, "Popen",
                               side_effect=AssertionError("spawned anyway")):
            with self.assertRaises(codex_login.NoBinary):
                codex_login.start()


class Cancel(CodexLoginBase):
    def test_cancel_kills_the_child_and_frees_the_slot(self):
        with self._sleeper():
            codex_login.start()
            self.assertTrue(codex_login.in_flight())
            self.assertTrue(codex_login.cancel())
        self._wait_until_idle()
        self.assertFalse(codex_login.in_flight(),
                         "a cancelled sign-in must not still read as in flight")
        self.assertIsNone(codex_login.state()["busy"])

    def test_cancel_with_nothing_running_is_false_not_an_error(self):
        """The panel's Cancel can lose a race with the flow completing.
        Reporting a failure for that would be a lie about state."""
        self.assertFalse(codex_login.cancel())

    def test_a_child_that_ignores_SIGTERM_is_killed(self):
        codex_login.KILL_GRACE = 1
        with self._bin("trap '' TERM; sleep 30"):
            codex_login.start()
            codex_login.cancel()
        self._wait_until_idle()
        self.assertFalse(codex_login.in_flight(),
                         "SIGTERM was ignored and no SIGKILL followed")


class Watchdog(CodexLoginBase):
    def test_a_walked_away_login_is_killed_at_the_cap(self):
        """Nobody polls, nobody cancels, the human never finishes. An abandoned
        `codex login` keeps its /auth/callback listener bound, so the next
        attempt would collide with it."""
        codex_login.CAP_SECONDS = 1
        codex_login.KILL_GRACE = 1
        with self._sleeper():
            codex_login.start()
        self._wait_until_idle()
        self.assertFalse(codex_login.in_flight(),
                         "the cap did not reclaim the child")

    def test_the_slot_is_freed_so_the_next_login_can_start(self):
        """Watchdog and reaper are the same thread precisely so this holds --
        a cap that killed the child but left the slot occupied would read as
        permanently busy."""
        codex_login.CAP_SECONDS = 1
        with self._sleeper():
            codex_login.start()
            self._wait_until_idle()
            self.assertIsNone(codex_login.state()["busy"])
            codex_login.start()                    # would raise Busy if stuck
            self.assertTrue(codex_login.in_flight())

    def test_a_child_that_exits_on_its_own_frees_the_slot(self):
        with self._bin("exit 0"):
            codex_login.start()
        self._wait_until_idle()
        self.assertIsNone(codex_login.state()["busy"],
                          "a completed sign-in must not read as in flight")
        self.assertFalse(codex_login.in_flight())


class OneOperationAtATime(CodexLoginBase):
    """codex keeps exactly ONE credential, so letting a logout race a login
    would leave the operator's real state decided by whichever finished last."""

    def test_a_second_login_is_refused(self):
        with self._sleeper():
            codex_login.start()
            with self.assertRaises(codex_login.Busy):
                codex_login.start()

    def test_a_logout_during_a_login_is_refused(self):
        with self._sleeper():
            codex_login.start()
            with self.assertRaises(codex_login.Busy):
                codex_login.logout()

    def test_only_one_child_exists(self):
        with self._sleeper():
            first = codex_login.start()["pid"]
            try:
                codex_login.start()
            except codex_login.Busy:
                pass
            self.assertEqual(codex_login._child.pid, first)


class Logout(CodexLoginBase):
    def test_a_clean_logout_reports_ok(self):
        with self._bin("exit 0"):
            self.assertEqual(codex_login.logout(), {"ok": True})

    def test_a_failure_reports_the_exit_code_and_names_the_terminal(self):
        with self._bin("echo boom 1>&2; exit 3"):
            out = codex_login.logout()
        self.assertFalse(out["ok"])
        self.assertIn("3", out["reason"])
        self.assertIn("terminal", out["reason"])

    def test_the_childs_output_is_never_returned(self):
        """`codex logout` has no reason to print a credential, but the rule
        that child output does not cross into a response is cheaper to keep
        than to re-reason per verb."""
        with self._bin("echo %s; echo %s 1>&2; exit 1" % (CANARY, CANARY)):
            out = codex_login.logout()
        self.assertNotIn(CANARY, repr(out))

    def test_the_slot_is_freed_afterwards(self):
        with self._bin("exit 0"):
            codex_login.logout()
        self.assertIsNone(codex_login.state()["busy"])

    def test_a_hanging_logout_times_out_and_frees_the_slot(self):
        codex_login.LOGOUT_TIMEOUT = 1
        with self._bin("sleep 30"):
            out = codex_login.logout()
        self.assertFalse(out["ok"])
        self.assertIn("did not finish", out["reason"])
        self.assertIsNone(codex_login.state()["busy"])


class SpawnEnvironment(CodexLoginBase):
    def test_OPENAI_and_CODEX_variables_are_stripped(self):
        """The operator's CLICK decides which credential gets stored, not a
        variable exported in the shell that launched the server. The status
        PROBE deliberately does not strip -- it must report what codex
        reports."""
        dump = os.path.join(self.dir, "env.txt")
        os.environ["OPENAI_API_KEY"] = CANARY
        os.environ["CODEX_HOME"] = "/should/not/reach"
        os.environ["SUTRA_KEEP_ME"] = "yes"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in
                                 ("OPENAI_API_KEY", "CODEX_HOME", "SUTRA_KEEP_ME")])
        with self._bin("env > %s" % dump):
            codex_login.logout()
        with open(dump, encoding="utf-8") as fh:
            env = fh.read()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn(CANARY, env)
        self.assertNotIn("CODEX_HOME", env)
        self.assertIn("SUTRA_KEEP_ME", env,
                      "only the two prefixes are stripped, not the environment")

    def test_the_binary_comes_from_provider_bin(self):
        """So a hand-picked path set in Settings IS honoured here -- the one
        thing this transport does better than the IPC path, which cannot
        execute a renderer-chosen path."""
        marker = os.path.join(self.dir, "ran.txt")
        with self._bin("touch %s" % marker):
            codex_login.logout()
        self.assertTrue(os.path.exists(marker))


class NoApiKeyPathHere(unittest.TestCase):
    """The key reaches codex on stdin over the IPC bridge and must never travel
    through an HTTP request body. These two guard that boundary in the one place
    it could quietly move."""

    def _source(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "codex_login.py"), encoding="utf-8") as fh:
            return fh.read()

    def test_no_api_key_spawn_reaches_this_module(self):
        # Strip the docstring, which names the flag in order to forbid it.
        body = self._source().split('"""', 2)[-1]
        self.assertNotIn("--with-api-key", body)

    def test_stdin_is_never_a_pipe(self):
        """Corollary: nothing here has anything to write to a child."""
        src = self._source()
        self.assertIn("stdin=subprocess.DEVNULL", src)
        self.assertNotIn("stdin=subprocess.PIPE", src)


class Routes(unittest.TestCase):
    """org_api's three routes are transport only. These pin the contracts the
    panel depends on -- and the confirm flag that stands between a bare POST
    and a credential nobody can restore.

    The module is mocked here on purpose: what is under test is the mapping
    from module outcome to HTTP answer, and the spawns themselves are covered
    above against real processes.
    """

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import app
        cls.client = TestClient(app.app)
        # The origin guard demands a loopback Host on every mutation.
        cls.H = {"host": "127.0.0.1:8787"}

    def test_logout_without_confirm_is_refused_and_spawns_NOTHING(self):
        """The dialog is client-side, so anything reaching this route directly
        has bypassed the warning. If the credential is an API key it is the
        only copy anywhere."""
        with mock.patch.object(codex_login, "logout",
                               side_effect=AssertionError("spawned anyway")):
            r = self.client.post("/api/providers/codex/logout", json={},
                                 headers=self.H)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "CONFIRM_REQUIRED")

    def test_confirm_false_is_refused_too(self):
        with mock.patch.object(codex_login, "logout",
                               side_effect=AssertionError("spawned anyway")):
            r = self.client.post("/api/providers/codex/logout",
                                 json={"confirm": False}, headers=self.H)
        self.assertEqual(r.status_code, 400)

    def test_logout_answers_with_the_fresh_probe(self):
        """So there is no window where the panel shows a state nobody read."""
        with mock.patch.object(codex_login, "logout", return_value={"ok": True}):
            r = self.client.post("/api/providers/codex/logout",
                                 json={"confirm": True}, headers=self.H)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn("state", body["auth"])
        self.assertIn("login_in_flight", body["auth"])

    def test_a_FAILED_logout_still_reports_what_codex_holds(self):
        with mock.patch.object(codex_login, "logout",
                               return_value={"ok": False, "reason": "codex exited 3"}):
            r = self.client.post("/api/providers/codex/logout",
                                 json={"confirm": True}, headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertIn("state", r.json()["auth"])

    def test_busy_is_409_not_500(self):
        """The panel distinguishes "already running" from "broken" by code."""
        with mock.patch.object(codex_login, "start",
                               side_effect=codex_login.Busy("login")):
            r = self.client.post("/api/providers/codex/login", headers=self.H)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "CODEX_BUSY")

    def test_a_logout_during_a_login_is_409(self):
        with mock.patch.object(codex_login, "logout",
                               side_effect=codex_login.Busy("login")):
            r = self.client.post("/api/providers/codex/logout",
                                 json={"confirm": True}, headers=self.H)
        self.assertEqual(r.status_code, 409)

    def test_no_binary_is_400_with_the_path_action(self):
        with mock.patch.object(codex_login, "start",
                               side_effect=codex_login.NoBinary("not on PATH")):
            r = self.client.post("/api/providers/codex/login", headers=self.H)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["user_action"], "INSTALL_OR_SET_PATH")

    def test_login_answers_started_immediately(self):
        with mock.patch.object(codex_login, "start",
                               return_value={"started": True, "pid": 1,
                                             "cap_seconds": 180}):
            r = self.client.post("/api/providers/codex/login", headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["started"])

    def test_cancel_with_nothing_running_is_200_false(self):
        with mock.patch.object(codex_login, "cancel", return_value=False):
            r = self.client.post("/api/providers/codex/login/cancel",
                                 headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["cancelled"])

    def test_the_auth_route_carries_login_in_flight(self):
        """Without it a panel RELOAD renders "Not signed in" while a child is
        running and about to change the credential."""
        with mock.patch.object(codex_login, "in_flight", return_value=True):
            r = self.client.get("/api/providers/codex/auth", headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["login_in_flight"])
        self.assertIn("state", r.json(), "the probe's own fields survive the merge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
