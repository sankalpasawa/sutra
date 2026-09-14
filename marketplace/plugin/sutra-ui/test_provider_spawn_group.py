"""Provider CLIs must be spawned in a new process GROUP, never a new SESSION.

THE BUG THIS GUARDS (measured 2026-09-13). DeepSeek turns in a workdir under
~/Desktop died at startup with `EPERM: uv_cwd` -- process.cwd() denied. Cause:
spawn() used start_new_session=True, which makes the child a SESSION leader, and
on macOS a session leader becomes its own TCC-responsible process. It then stops
inheriting the Sutra app's Files-and-Folders grants, so it cannot read a
TCC-protected folder (Desktop/Documents/Downloads) it was launched into -- even
though the Sutra app itself is granted Desktop access. kill_group only ever
needed a process GROUP leader (killpg reaches descendants), which process_group=0
provides WITHOUT the session detach, so the child stays attributed to Sutra.

This asserts the spawn kwargs directly: process_group=0 present, and
start_new_session absent. A revert to start_new_session -- the tidy-looking
"simplification" that silently reintroduces the Desktop crash -- fails here. TCC
attribution itself cannot be unit-tested (it needs a low-privilege responsible
process); this pins the one property that controls it.
"""
import asyncio
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

_ENV_TMP = tempfile.mkdtemp(prefix="spawn-group-env-")
os.environ["SUTRA_UI_WORKDIR"] = os.path.join(_ENV_TMP, "workspace")
os.environ["SUTRA_UI_WORKDIR_ROOT"] = _ENV_TMP
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_ENV_TMP, "settings.json")
os.environ["SUTRA_NATIVE_HOME"] = os.path.join(_ENV_TMP, "native")
os.environ["SUTRA_SHADOW_HOME"] = os.path.join(_ENV_TMP, "shadow")

sys.path.insert(0, HERE)

from acp_runtime import AcpRuntime          # noqa: E402
from session_runtime import SessionRuntime  # noqa: E402
from codex_runtime import CodexRuntime      # noqa: E402


class _Captured(Exception):
    """Carries the kwargs of the intercepted spawn out of the coroutine."""
    def __init__(self, kwargs):
        self.kwargs = kwargs


def _spawn_kwargs(runtime):
    """Return the kwargs a runtime passes to create_subprocess_exec, captured
    before the real spawn happens (we raise out of the stub)."""
    import acp_runtime, session_runtime, codex_runtime
    mods = [acp_runtime, session_runtime, codex_runtime]

    async def fake_exec(*args, **kwargs):
        raise _Captured(kwargs)

    saved = [(m, m.asyncio.create_subprocess_exec) for m in mods]
    for m, _ in saved:
        m.asyncio.create_subprocess_exec = fake_exec
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                runtime.spawn(["/bin/echo", "hi"], _ENV_TMP, ("k",)))
        except _Captured as c:
            return c.kwargs
        finally:
            loop.close()
        raise AssertionError("spawn did not call create_subprocess_exec")
    finally:
        for m, orig in saved:
            m.asyncio.create_subprocess_exec = orig


class TestProviderSpawnGroup(unittest.TestCase):
    def _check(self, runtime, label):
        kw = _spawn_kwargs(runtime)
        self.assertEqual(kw.get("process_group"), 0,
                         "%s must spawn with process_group=0" % label)
        self.assertNotIn("start_new_session", kw,
                         "%s must NOT use start_new_session (severs TCC "
                         "attribution; breaks providers under ~/Desktop)" % label)

    def test_deepseek_acp(self):
        self._check(AcpRuntime(), "AcpRuntime (DeepSeek)")

    def test_claude(self):
        self._check(SessionRuntime(), "SessionRuntime (Claude)")

    def test_codex(self):
        self._check(CodexRuntime(), "CodexRuntime (Codex)")


class TestGroupKillStillWorks(unittest.TestCase):
    def test_killpg_reaps_a_process_group(self):
        """process_group=0 must still let killpg reap the whole tree -- the one
        thing the session detach was there for."""
        async def go():
            p = await asyncio.create_subprocess_exec(
                "/bin/sh", "-c", "sleep 30",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, process_group=0)
            pgid = os.getpgid(p.pid)
            self.assertEqual(pgid, p.pid, "child is its own group leader")
            self.assertNotEqual(pgid, os.getpgid(0), "a NEW group, not ours")
            os.killpg(pgid, 15)
            await asyncio.wait_for(p.wait(), 5)
            self.assertIsNotNone(p.returncode)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(go())
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
