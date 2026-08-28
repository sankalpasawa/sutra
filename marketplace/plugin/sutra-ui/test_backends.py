"""Redirecting one turn to another backend, without the OS ever seeing it.

The security properties are the point, so most of these tests are about what
must NOT happen: the token must not reach argv, must not reach os.environ, must
not be readable by another account, and must not appear in anything shown or
logged.
"""

import json
import os
import shutil
import stat
import tempfile
import unittest

import backends


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-backends-")
        self._old = {k: os.environ.get(k) for k in
                     ("SUTRA_UI_BACKENDS", "SUTRA_UI_BACKEND_TOKENS",
                      "SUTRA_UI_BACKEND_SETTINGS")}
        os.environ["SUTRA_UI_BACKENDS"] = os.path.join(self.tmp, "backends.json")
        os.environ["SUTRA_UI_BACKEND_TOKENS"] = os.path.join(self.tmp, "tokens")
        os.environ["SUTRA_UI_BACKEND_SETTINGS"] = os.path.join(self.tmp, "settings")
        for mod_attr, env in (("PROFILES_PATH", "SUTRA_UI_BACKENDS"),
                              ("TOKEN_DIR", "SUTRA_UI_BACKEND_TOKENS"),
                              ("SETTINGS_DIR", "SUTRA_UI_BACKEND_SETTINGS")):
            setattr(backends, mod_attr, os.environ[env])
        os.makedirs(backends.TOKEN_DIR, mode=0o700, exist_ok=True)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _profile(self, **kw):
        p = {"id": "acme", "name": "Acme", "base_url": "https://acme.example",
             "model_map": {"sonnet": "acme-large", "haiku": "acme-small"}}
        p.update(kw)
        with open(backends.PROFILES_PATH, "w") as fh:
            json.dump({"backends": [p]}, fh)
        return p

    def _token(self, pid="acme", value="sk-secret-do-not-leak", mode=0o600):
        path = os.path.join(backends.TOKEN_DIR, pid + ".json")
        with open(path, "w") as fh:
            json.dump({"token": value}, fh)
        os.chmod(path, mode)
        return path


class TestProfiles(Base):
    def test_load(self):
        self._profile()
        self.assertEqual([p["id"] for p in backends.load_profiles()], ["acme"])
        self.assertIsNotNone(backends.load_profile("acme"))
        self.assertIsNone(backends.load_profile("nope"))

    def test_malformed_file_is_no_profiles_not_a_crash(self):
        with open(backends.PROFILES_PATH, "w") as fh:
            fh.write("{not json")
        self.assertEqual(backends.load_profiles(), [])

    def test_missing_file_is_no_profiles(self):
        self.assertEqual(backends.load_profiles(), [])


class TestToken(Base):
    def test_reads_a_0600_token(self):
        p = self._profile()
        self._token()
        self.assertEqual(backends.read_token(p), "sk-secret-do-not-leak")

    def test_refuses_a_group_readable_token(self):
        p = self._profile()
        self._token(mode=0o640)
        with self.assertRaises(backends.BackendError) as cm:
            backends.read_token(p)
        self.assertIn("readable by other accounts", str(cm.exception))

    def test_refuses_world_readable(self):
        p = self._profile()
        self._token(mode=0o604)
        with self.assertRaises(backends.BackendError):
            backends.read_token(p)

    def test_missing_token_says_where_to_put_it(self):
        p = self._profile()
        with self.assertRaises(backends.BackendError) as cm:
            backends.read_token(p)
        self.assertIn("mode 600", str(cm.exception))
        self.assertIn(backends.TOKEN_DIR, str(cm.exception))

    def test_token_file_cannot_escape_the_directory(self):
        p = self._profile(token_file="../../etc/passwd")
        with self.assertRaises(backends.BackendError):
            backends.token_path(p)


class TestSettingsFile(Base):
    def test_carries_hook_and_redirect_together(self):
        p = self._profile()
        self._token()
        hook = {"hooks": {"PreToolUse": [{"matcher": "mcp__sutra__.*"}]}}
        path = backends.settings_file(p, hook, accept="bare")
        with open(path) as fh:
            got = json.load(fh)
        # --settings takes ONE object; both must survive the merge
        self.assertIn("PreToolUse", got["hooks"])
        self.assertEqual(got["env"]["ANTHROPIC_BASE_URL"], "https://acme.example")
        self.assertEqual(got["env"]["ANTHROPIC_AUTH_TOKEN"], "sk-secret-do-not-leak")
        self.assertEqual(got["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], "acme-large")

    def test_settings_file_is_private(self):
        p = self._profile()
        self._token()
        path = backends.settings_file(p, {}, accept="bare")
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode & 0o077, 0, "settings file is readable by others: %o" % mode)

    def test_no_temp_file_left_behind(self):
        p = self._profile()
        self._token()
        for _ in range(5):
            backends.settings_file(p, {}, accept="bare")
        leftovers = [f for f in os.listdir(backends.SETTINGS_DIR) if ".tmp" in f]
        self.assertEqual(leftovers, [])

    def test_the_token_never_reaches_the_environment(self):
        """The whole reason this is a file: a redirect in os.environ would be
        visible to the terminal pane, routines, and any login shell."""
        p = self._profile()
        self._token()
        backends.settings_file(p, {}, accept="bare")
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", os.environ)
        self.assertNotIn("ANTHROPIC_BASE_URL", [k for k in os.environ
                                                if os.environ.get(k) == "https://acme.example"])


class TestNoLeak(Base):
    def test_public_dict_has_no_token_and_no_length(self):
        p = self._profile()
        self._token()
        pub = backends.public_dict(p)
        blob = json.dumps(pub)
        self.assertNotIn("sk-secret-do-not-leak", blob)
        self.assertTrue(pub["has_token"])
        # a length is a fact about a secret
        self.assertNotIn("len", blob.lower())

    def test_module_never_builds_argv_containing_a_token(self):
        """--settings accepts inline JSON, and argv is world-readable via ps.
        Nothing here may return the credential as a command-line fragment."""
        import ast
        src = open(os.path.join(os.path.dirname(os.path.abspath(backends.__file__)),
                                "backends.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr in ("run", "Popen", "check_output", "call"):
                    self.fail("backends.py spawns a process; a token could reach argv")


class TestRefusesToLeak(Base):
    """The measurement this module exists to record.

    With a keychain OAuth session present, claude 2.1.212 sends
    sk-ant-oat...(108) to a redirected backend whatever the settings file says;
    only --bare selects the supplied credential, and --bare turns off Sutra's
    governance. Rendering a redirect without stating which trade-off you are
    taking is therefore refused.
    """

    def test_no_accept_is_refused(self):
        p = self._profile()
        self._token()
        with self.assertRaises(backends.BackendError) as cm:
            backends.settings_file(p, {})
        msg = str(cm.exception)
        self.assertIn("sk-ant-oat", msg)
        self.assertIn("--bare", msg)
        self.assertIn("provider_adapters", msg)

    def test_a_wrong_accept_is_refused(self):
        p = self._profile()
        self._token()
        for bad in ("yes", True, "", "BARE"):
            with self.assertRaises(backends.BackendError):
                backends.settings_file(p, {}, accept=bad)

    def test_both_stated_trade_offs_render(self):
        p = self._profile()
        self._token()
        for ok in ("bare", "oauth"):
            self.assertTrue(os.path.exists(backends.settings_file(p, {}, accept=ok)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
