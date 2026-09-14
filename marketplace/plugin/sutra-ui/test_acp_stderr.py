"""The ACP child's death must name itself.

THE BUG THESE EXIST FOR (measured 2026-09-13). A DeepSeek turn failed with a
single opaque line -- "could not start '.../deepseek' in <cwd>: ACP process
closed stdout" -- and nothing else. The child's stderr, where the real reason
lives (a node ENOENT, an ESM stack, a first-run config crash), was captured to
a PIPE that nothing ever read, so it was thrown away at exactly the moment it
was needed. The root cause on that machine was a concurrent FIRST-RUN race: two
`deepseek --acp` spawns within one second both initialising the shared
~/.gemini state, the loser crashing mid-write and closing stdout (four orphaned
projects.json.*.tmp files were the fingerprint).

Two fixes, one test file:
  1. AcpRuntime drains the child's stderr and stderr_tail() returns it, so a
     death is self-explaining -- asserted here against a real subprocess that
     writes to stderr and closes stdout, the exact shape of the failure.
  2. app._gemini_home_uninitialised() gates the first-run connect lock, so it
     engages only while the race is possible and never in steady state.
"""
import asyncio
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

# IMPORT-TIME ISOLATION before `import app` -- app.py runs _ensure_workdir() at
# module level and providers reads env-resolved paths; an unguarded import would
# touch the operator's real workspace and settings. Mirrors test_codex_runtime.
_ENV_TMP = tempfile.mkdtemp(prefix="acp-stderr-env-")
os.environ["SUTRA_UI_WORKDIR"] = os.path.join(_ENV_TMP, "workspace")
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_NATIVE_HOME"] = os.path.join(_ENV_TMP, "native")
os.environ["SUTRA_SHADOW_HOME"] = os.path.join(_ENV_TMP, "shadow")

sys.path.insert(0, HERE)

import app                          # noqa: E402  (env above must be set first)
from acp_runtime import AcpRuntime  # noqa: E402


def _in_loop(coro_factory):
    """Run one coroutine in a fresh loop -- AcpRuntime.__init__ builds an
    asyncio.Event, so the runtime must be constructed inside the loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


class TestWithStderr(unittest.TestCase):
    def test_appended_only_when_present(self):
        base = "could not start 'deepseek' in /x: ACP process closed stdout"
        self.assertEqual(app._with_stderr(base, ""), base)
        joined = app._with_stderr(base, "env: node: No such file or directory")
        self.assertIn(base, joined)
        self.assertIn("agent stderr:", joined)
        self.assertIn("env: node: No such file or directory", joined)


class TestStderrCaptured(unittest.TestCase):
    def test_death_carries_its_stderr(self):
        """A child that writes to stderr and closes stdout without ever
        answering initialize: spawn() must raise ConnectionResetError AND its
        stderr must be recoverable -- the whole point of the fix."""
        wd = tempfile.mkdtemp(prefix="acp-death-")
        reason = "boom: env: node: No such file or directory"
        # never writes stdout -> initialize's readline hits EOF -> _on_eof
        child = ("import sys; sys.stderr.write(%r + chr(10)); "
                 "sys.stderr.flush(); sys.exit(1)" % reason)
        args = [sys.executable, "-c", child]

        box = {}

        async def go():
            rt = AcpRuntime()
            box["rt"] = rt
            with self.assertRaises(ConnectionResetError):
                await rt.spawn(args, wd, tuple(args))
            return await rt.stderr_tail()

        tail = _in_loop(go)
        self.assertIn(reason, tail)

    def test_quiet_death_returns_empty_not_none(self):
        """A child that writes nothing to stderr must give "" (callers append
        only a truthy tail), never None or a crash."""
        wd = tempfile.mkdtemp(prefix="acp-quiet-")
        args = [sys.executable, "-c", "import sys; sys.exit(1)"]

        async def go():
            rt = AcpRuntime()
            with self.assertRaises(ConnectionResetError):
                await rt.spawn(args, wd, tuple(args))
            return await rt.stderr_tail()

        self.assertEqual(_in_loop(go), "")


class TestFirstRunGate(unittest.TestCase):
    def test_gate_tracks_installation_id(self):
        """The connect lock is worth taking only before the fork's first run.
        _gemini_home_uninitialised() keys off the installation_id marker."""
        home = tempfile.mkdtemp(prefix="acp-home-")
        old = os.environ.get("HOME")
        try:
            os.environ["HOME"] = home
            # no ~/.gemini at all -> first run pending
            self.assertTrue(app._gemini_home_uninitialised())
            gem = os.path.join(home, ".gemini")
            os.makedirs(gem, exist_ok=True)
            # dir exists but no marker -> still pending
            self.assertTrue(app._gemini_home_uninitialised())
            with open(os.path.join(gem, "installation_id"), "w") as f:
                f.write("abc123")
            # marker present -> first run done, no lock, zero steady-state contention
            self.assertFalse(app._gemini_home_uninitialised())
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old


if __name__ == "__main__":
    unittest.main()
