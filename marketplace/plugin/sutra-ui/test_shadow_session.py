"""PLAN-100 S29-S31: Shadow session manager + gated MCP registration.

Off-state first: with the flag off, start() refuses, the loader returns None,
and the MCP server does not list shadow tools at all.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import providers
import shadow_session
from shadow_session import ShadowSession

HERE = os.path.dirname(os.path.abspath(__file__))


def _flag(tmp, on):
    settings = Path(tmp) / "settings.json"
    settings.write_text(json.dumps({"shadow.enabled": bool(on)}))
    return settings


FAKE = r"""#!/usr/bin/env python3
import json, os, sys
sid = "shadow-fake-%d" % os.getpid()
def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
for line in sys.stdin:
    try:
        frame = json.loads(line)
    except ValueError:
        continue
    try:
        msg = frame["message"]["content"][0]["text"]
    except Exception:
        msg = ""
    emit({"type": "system", "subtype": "init", "session_id": sid,
          "model": "fake", "tools": [], "mcp_servers": [],
          "slash_commands": [], "permissionMode": "plan", "cwd": os.getcwd()})
    emit({"type": "stream_event", "session_id": sid,
          "event": {"delta": {"type": "text_delta",
                              "text": "SEEN:" + msg[:120]}}})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "session_id": sid, "duration_ms": 1, "num_turns": 1,
          "total_cost_usd": 0.0})
"""


class TestShadowSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = providers.SETTINGS_PATH

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        self.tmp.cleanup()

    def _fake_bin(self):
        fake = Path(self.tmp.name) / "fake-claude"
        fake.write_text(FAKE)
        os.chmod(fake, 0o755)
        return str(fake)

    def test_01_flag_off_start_refuses_and_loader_is_none(self):
        providers.SETTINGS_PATH = _flag(self.tmp.name, False)
        self.assertIsNone(shadow_session.load_context())
        s = ShadowSession()
        out = asyncio.run(s.start(lambda: [self._fake_bin()], self.tmp.name))
        self.assertIsNone(out)
        self.assertFalse(s.started)
        self.assertIsNone(s.rt.proc, "no process may exist with the flag off")

    def test_02_flag_on_boots_and_injects_context(self):
        providers.SETTINGS_PATH = _flag(self.tmp.name, True)
        frames = []

        async def emit(frame):
            frames.append(frame)

        s = ShadowSession()
        sid = asyncio.run(s.start(lambda: [self._fake_bin()],
                                  self.tmp.name, emit))
        self.assertTrue(sid and sid.startswith("shadow-fake-"))
        self.assertTrue(s.started)
        echoed = " ".join(f.get("text", "") for f in frames
                          if f["type"] == "token")
        self.assertIn("Shadow boot", echoed,
                      "the transcript must show the context injection (S30)")
        s.stop()
        self.assertFalse(s.started)

    def test_03_context_carries_the_persona_doc(self):
        providers.SETTINGS_PATH = _flag(self.tmp.name, True)
        ctx = shadow_session.load_context()
        self.assertIn("Persona", ctx)
        self.assertIn("Precedence", ctx)


class TestMcpGating(unittest.TestCase):
    def _tools(self, flag_on):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"shadow.enabled": flag_on}))
            env = dict(os.environ, SUTRA_UI_SETTINGS=str(settings),
                       SUTRA_MCP_SHADOW="1")
            out = subprocess.run(
                [sys.executable, "-c",
                 "import sutra_mcp, json;"
                 "print(json.dumps([t['name'] for t in sutra_mcp.TOOLS]))"],
                capture_output=True, text=True, cwd=HERE, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            return json.loads(out.stdout.strip().splitlines()[-1])

    def test_04_flag_off_shadow_tools_absent(self):
        self.assertNotIn("shadow_sessions_list", self._tools(False))

    def test_05_flag_on_shadow_tools_present(self):
        self.assertIn("shadow_sessions_list", self._tools(True))

    def test_06_flag_on_but_no_shadow_env_marker_stays_absent(self):
        # chat panes share this server; they never see Shadow tools
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"shadow.enabled": True}))
            env = dict(os.environ, SUTRA_UI_SETTINGS=str(settings))
            env.pop("SUTRA_MCP_SHADOW", None)
            out = subprocess.run(
                [sys.executable, "-c",
                 "import sutra_mcp, json;"
                 "print(json.dumps([t['name'] for t in sutra_mcp.TOOLS]))"],
                capture_output=True, text=True, cwd=HERE, env=env)
            self.assertNotIn("shadow_sessions_list",
                             json.loads(out.stdout.strip().splitlines()[-1]))

    def test_07_handler_recheck_refuses_when_flag_drops_mid_process(self):
        # spawn-time table latches until respawn (pinned semantics), but the
        # HANDLER re-checks at call time: authorization, not just hiding
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"shadow.enabled": True}))
            env = dict(os.environ, SUTRA_UI_SETTINGS=str(settings),
                       SUTRA_MCP_SHADOW="1")
            code = "; ".join([
                "import json, sutra_mcp",
                "names = [t['name'] for t in sutra_mcp.TOOLS]",
                "assert 'shadow_sessions_list' in names",
                "open(%r, 'w').write(json.dumps({'shadow.enabled': False}))" % str(settings),
                "t = sutra_mcp.BY_NAME['shadow_sessions_list']",
                "print(json.dumps(t['fn']({})))",
            ])
            out = subprocess.run([sys.executable, "-c", code],
                                 capture_output=True, text=True,
                                 cwd=HERE, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("refused", out.stdout)


if __name__ == "__main__":
    unittest.main()
