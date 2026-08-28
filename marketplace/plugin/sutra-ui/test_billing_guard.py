"""The guard is copied into four languages. These tests fail when they drift.

Why this file leans on mutation rather than assertion: the hole it closes existed
for months UNDER A PASSING SUITE, because every test asserted on ANTHROPIC_API_KEY
-- the one variable that was already handled. A test that cannot fail when the
feature is broken is not a check. So each site here is verified by breaking it.
"""

import ast
import io
import os
import re
import unittest

import billing_guard as bg

HERE = os.path.dirname(os.path.abspath(__file__))


def _read(rel):
    with io.open(os.path.join(HERE, rel), encoding="utf-8") as fh:
        return fh.read()


def _runner_list():
    """The REDIRECT_VARS tuple inlined inside routines._RUNNER."""
    src = _read("routines.py")
    m = re.search(r"^REDIRECT_VARS = \((.*?)\)", src, re.S | re.M)
    assert m, "REDIRECT_VARS missing from the runner"
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


class TestSemantics(unittest.TestCase):
    def test_redirect_vars_refuse(self):
        for v in bg.REDIRECT_VARS:
            self.assertIsNotNone(bg.refusal({v: "x"}), "%s not guarded" % v)

    def test_model_vars_do_not_refuse(self):
        """The prefix-match trap: these redirect nothing and must stay allowed."""
        for v in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
                  "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL"):
            self.assertIsNone(bg.refusal({v: "opus"}), "%s wrongly refused" % v)

    def test_empty_value_is_not_set(self):
        self.assertIsNone(bg.refusal({"ANTHROPIC_BASE_URL": "  "}))

    def test_opt_in_allows(self):
        env = {"ANTHROPIC_BASE_URL": "https://x", bg.ALLOW_ENV: "1"}
        self.assertIsNone(bg.refusal(env))
        self.assertTrue(bg.status(env)["redirected"])

    def test_refusal_never_leaks_values(self):
        """The message reaches logs and API responses; AUTH_TOKEN is a credential."""
        msg = bg.refusal({"ANTHROPIC_AUTH_TOKEN": "sk-secret-value-here"})
        self.assertNotIn("sk-secret-value-here", msg)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", msg)

    def test_scrub_removes_all_and_keeps_others(self):
        env = dict({v: "x" for v in bg.REDIRECT_VARS}, PATH="/bin", ANTHROPIC_MODEL="opus")
        bg.scrub(env)
        self.assertEqual(sorted(env), ["ANTHROPIC_MODEL", "PATH"])


class TestNoDrift(unittest.TestCase):
    """Same list, four languages. Parsed, not grepped -- a grep would match a
    variable's name inside a comment and pass while the code was wrong."""

    def _js_list(self):
        src = _read("electron/main.js")
        m = re.search(r"const REDIRECT_VARS = \[(.*?)\];", src, re.S)
        self.assertIsNotNone(m, "REDIRECT_VARS missing from main.js")
        return tuple(re.findall(r'"([^"]+)"', m.group(1)))

    def _sh_list(self, rel):
        src = _read(rel)
        m = re.search(r'^SUTRA_REDIRECT_VARS="([^"]+)"', src, re.M)
        self.assertIsNotNone(m, "SUTRA_REDIRECT_VARS missing from %s" % rel)
        return tuple(m.group(1).split())

    def test_js_matches_python(self):
        self.assertEqual(self._js_list(), bg.REDIRECT_VARS)

    def test_runner_matches_python(self):
        self.assertEqual(_runner_list(), bg.REDIRECT_VARS)

    def test_shell_matches_python(self):
        for rel in ("sutra-ui.sh", "install.sh"):
            self.assertEqual(self._sh_list(rel), bg.REDIRECT_VARS, rel)


class TestCallSitesWired(unittest.TestCase):
    """AST, not substring: four earlier bugs in this repo were substring checks
    matching an explanatory COMMENT instead of the code."""

    def _calls_in(self, rel):
        tree = ast.parse(_read(rel))
        out = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                v = n.func.value
                if isinstance(v, ast.Name) and v.id == "billing_guard":
                    out.add(n.func.attr)
        return out

    def test_app_refuses_on_both_sockets(self):
        tree = ast.parse(_read("app.py"))
        found = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for sub in ast.walk(n):
                    if (isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "refusal"
                            and isinstance(sub.func.value, ast.Name)
                            and sub.func.value.id == "billing_guard"):
                        found.add(n.name)
        self.assertIn("ws_chat", found)
        self.assertIn("ws_term", found)

    def test_session_runtime_scrubs(self):
        self.assertIn("scrub", self._calls_in("session_runtime.py"))

    def test_routines_runner_scrubs_inline(self):
        """routines.py deliberately does NOT import billing_guard: the scrub it
        needs lives inside _RUNNER, a generated stdlib-only script that must keep
        working while the .app is mid-update. So the list is inlined there, and
        this test is the thing that keeps it honest."""
        import routines
        self.assertEqual(_runner_list(), bg.REDIRECT_VARS)
        # and the scrub is actually performed, not merely declared
        self.assertIn("env.pop(_v, None)", routines._RUNNER)

    def test_runner_defines_everything_it_uses(self):
        """The generated runner cannot import app helpers. This is the check that
        catches someone wiring one in anyway -- it compiles fine and dies at
        launchd fire time."""
        import routines
        self.assertEqual(routines.runner_undefined_names(), [])

    def test_runner_undefined_check_actually_fails(self):
        """Mutation: without this, the test above is indistinguishable from a
        check that always returns []."""
        import routines
        broken = routines._RUNNER.replace(
            "for _v in REDIRECT_VARS:\n            env.pop(_v, None)",
            "billing_guard.scrub(env)")
        self.assertNotEqual(broken, routines._RUNNER, "mutation did not apply")
        self.assertEqual(routines.runner_undefined_names(broken), ["billing_guard"])
        self.assertIsNone(routines.runner_syntax_error(broken),
                          "syntax check now catches this; retire the name check?")

    def test_session_runtime_env_is_scrubbed_not_raw(self):
        """Specifically: the env= kwarg must be wrapped, not a bare dict()."""
        tree = ast.parse(_read("session_runtime.py"))
        raw = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                for kw in n.keywords:
                    if kw.arg == "env" and isinstance(kw.value, ast.Call):
                        f = kw.value.func
                        if isinstance(f, ast.Name) and f.id == "dict":
                            raw.append(n)
        self.assertFalse(raw, "env=dict(os.environ, ...) passed unscrubbed")


# The case table all three implementations must agree on. Presence-vs-value is
# the whole point: rows 1-2 are the reason this guard cannot be a presence check.
CASES = (
    ({"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}, False),
    ({"ANTHROPIC_BASE_URL": "https://api.anthropic.com/v1"}, False),
    ({"ANTHROPIC_BASE_URL": "https://evil.example/v1"}, True),
    ({"ANTHROPIC_BASE_URL": "https://anthropic.com.evil.net"}, True),
    ({"ANTHROPIC_BASE_URL": "http://localhost:8080"}, True),
    ({"ANTHROPIC_AUTH_TOKEN": "sk-x"}, True),
    ({"ANTHROPIC_API_KEY": "sk-x"}, True),
    ({"CLAUDE_CODE_USE_BEDROCK": "0"}, False),
    ({"CLAUDE_CODE_USE_BEDROCK": "1"}, True),
    ({"ANTHROPIC_MODEL": "opus"}, False),
    ({}, False),
)


class TestCrossLanguageBehaviour(unittest.TestCase):
    """Matching NAME LISTS is not enough -- three copies can share a list and
    still disagree about what a value means. These run the other two
    implementations for real and compare verdicts."""

    def test_python(self):
        for env, want in CASES:
            self.assertEqual(bool(bg.refusal(env)), want, env)

    def test_shell_agrees(self):
        import subprocess, tempfile, re as _re
        src = _read("sutra-ui.sh")
        m = _re.search(r'^SUTRA_REDIRECT_VARS=.*?^fi$', src, _re.S | _re.M)
        self.assertIsNotNone(m, "guard block not found in sutra-ui.sh")
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(m.group(0))
            path = fh.name
        for env, want in CASES:
            base = {"PATH": "/usr/bin:/bin"}
            base.update(env)
            rc = subprocess.call(["sh", path], env=base,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(rc == 2, want, "shell disagrees on %s" % env)

    def test_electron_agrees(self):
        import subprocess, shutil, tempfile, os as _os, re as _re, json
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        src = _read("electron/main.js")
        parts = []
        for pat, what in ((r"const OFFICIAL = [\s\S]*?\n};", "OFFICIAL"),
                          (r"const FALSEY = [^\n]*\n", "FALSEY"),
                          (r"function activeRedirects\(env\) \{[\s\S]*?\n\}", "activeRedirects")):
            m = _re.search(pat, src)
            self.assertIsNotNone(m, "%s missing from main.js" % what)
            parts.append(m.group(0))
        # argv[2]: for a FILE script node puts the script path at argv[1]
        parts.append("const cases = JSON.parse(process.argv[2]);")
        parts.append("console.log(JSON.stringify("
                     "cases.map((c) => activeRedirects(c).length > 0)));")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write("\n".join(parts))
            path = fh.name
        envs = [c[0] for c in CASES]
        out = subprocess.check_output([node, path, json.dumps(envs)])
        got = json.loads(out)
        for (env, want), g in zip(CASES, got):
            self.assertEqual(g, want, "electron disagrees on %s" % env)


if __name__ == "__main__":
    unittest.main(verbosity=2)
