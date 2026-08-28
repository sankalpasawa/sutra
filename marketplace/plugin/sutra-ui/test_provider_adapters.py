"""A provider that is NOT Claude drives a real chat turn.

This is the only test that can show the adapter seam is an interface rather
than a description of one program. It runs a fake CLI speaking a line protocol
that has nothing to do with Claude Code's stream-json, through the real
/ws/chat socket, and checks that Sutra's own frame vocabulary comes out the
other end and the conversation lands in Sutra's session store.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request

from test_runtime_characterization import VENV_PY, HERE, _free_port

import provider_adapters as pa
import sessions_store as ss


FAKE_LINES = r"""#!/usr/bin/env python3
import os, sys
sid = "lines-%d" % os.getpid()
sys.stdout.write("SESSION %s\n" % sid)
sys.stdout.flush()
for line in sys.stdin:
    msg = line.rstrip("\n")
    for out in ("THINKING",
                "TOOL t1 Read",
                "TOOLEND t1 1",
                "TOKEN echo: " + msg,
                "WEIRD something new",
                "END"):
        sys.stdout.write(out + "\n")
    sys.stdout.flush()
"""


class AdapterUnit(unittest.TestCase):
    def test_registry(self):
        self.assertIn("claude", pa.available())
        self.assertIsNone(pa.for_provider("nope"))
        self.assertEqual(pa.for_provider("claude").protocol, pa.PROTO_CLAUDE)

    def test_lines_translation(self):
        a = pa.for_provider("lines")
        st = {}
        self.assertEqual(a.session_id(a.parse_line("SESSION abc")), "abc")
        frames, done, err = a.translate(a.parse_line("TOKEN hi"), st)
        self.assertEqual(frames, [{"type": "token", "text": "hi"}])
        self.assertTrue(st["got_text"])
        self.assertEqual(a.translate(a.parse_line("END"), st), ([], True, None))
        _f, done, err = a.translate(a.parse_line("ERROR boom"), st)
        self.assertTrue(done)
        self.assertEqual(err, "boom")

    def test_unknown_directive_is_surfaced_not_swallowed(self):
        """A provider that grows a directive this build predates should be
        visible to whoever is watching, not silently dropped."""
        a = pa.for_provider("lines")
        frames, done, err = a.translate(a.parse_line("NEWTHING x"), {})
        self.assertEqual(frames[0]["type"], "notice")
        self.assertFalse(done)

    def test_every_emitted_type_is_in_the_vocabulary(self):
        a = pa.for_provider("lines")
        st = {}
        for line in ("TOKEN a", "THINKING", "TOOL t1 Read", "TOOLEND t1 1",
                     "NOTICE n", "RETRY r", "END", "ERROR e", "ZZZ q"):
            frames, _d, _e = a.translate(a.parse_line(line), st)
            for f in frames:
                self.assertIn(f["type"], pa.FRAMES, f)


class NonClaudeChat(unittest.TestCase):
    """The end-to-end claim."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-lines-")
        cls.fake = os.path.join(cls.tmpdir, "fake-lines")
        with open(cls.fake, "w") as f:
            f.write(FAKE_LINES)
        os.chmod(cls.fake, 0o755)
        cfg = os.path.join(cls.tmpdir, "cfg")
        os.makedirs(cfg, exist_ok=True)
        cls._saved = {k: os.environ.get(k) for k in
                      ("SUTRA_UI_SETTINGS", "SUTRA_UI_WORKDIR_ROOT",
                       "SUTRA_UI_SESSIONS", "SUTRA_UI_PROVIDER",
                       "SUTRA_UI_EXTRA_PROVIDER")}
        os.environ["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        os.environ["SUTRA_UI_SESSIONS"] = os.path.join(cls.tmpdir, "sessions")
        os.environ["SUTRA_UI_PROVIDER"] = "lines"
        os.environ["SUTRA_UI_EXTRA_PROVIDER"] = (
            "id=lines,name=Lines,bin=%s,config=%s" % (cls.fake, cfg))
        cls.port = _free_port()
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=dict(os.environ),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("server did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
        for k, v in cls._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _turn(self, message):
        from websockets.sync.client import connect
        frames = []
        with connect("ws://127.0.0.1:%d/ws/chat" % self.port,
                     open_timeout=10, close_timeout=5) as ws:
            ws.send(json.dumps({"message": message}))
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    fr = json.loads(ws.recv(timeout=max(0.1, deadline - time.time())))
                except Exception:
                    break
                frames.append(fr)
                if fr.get("type") in ("done", "error"):
                    break
        return frames

    def test_a_non_claude_provider_completes_a_turn(self):
        frames = self._turn("hello")
        kinds = [f["type"] for f in frames]
        self.assertNotIn("error", kinds, frames)
        self.assertIn("done", kinds, "the turn never closed: %s" % kinds)
        self.assertIn("session", kinds)
        self.assertIn("token", kinds)
        self.assertIn("thinking", kinds)

        text = "".join(f.get("text", "") for f in frames if f["type"] == "token")
        self.assertEqual(text, "echo: hello")

        tools = [f for f in frames if f["type"] == "tool"]
        self.assertEqual([t["phase"] for t in tools], ["start", "end"])
        self.assertTrue(tools[1]["ok"])

        # the provider's id was recorded as a HANDLE on Sutra's own session
        sid = [f["id"] for f in frames if f["type"] == "sutra_session"][0]
        prov_id = [f["id"] for f in frames if f["type"] == "session"][0]
        self.assertTrue(prov_id.startswith("lines-"))
        self.assertEqual(ss.read(sid)["handles"]["lines"], prov_id)

        # and the transcript is Sutra's, in Sutra's shape
        turns = ss.transcript(sid)
        self.assertEqual([t["role"] for t in turns][:2], ["user", "assistant"])
        self.assertEqual(turns[1]["text"], "echo: hello")
        self.assertEqual(turns[1]["provider"], "lines")

    def test_unknown_directive_reaches_the_operator(self):
        frames = self._turn("hi")
        notices = [f for f in frames if f["type"] == "notice"]
        self.assertTrue(any("WEIRD" in (n.get("text") or "") for n in notices),
                        "an unrecognised directive was swallowed: %s" % notices)

    def test_resume_plan_says_replay_for_a_provider_that_cannot_resume(self):
        """`lines` declares native_resume=False. Holding a handle proves the
        thread existed, not that this CLI can continue it."""
        frames = self._turn("plan me")
        sid = [f["id"] for f in frames if f["type"] == "sutra_session"][0]
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/sutra/sessions/%s/resume-plan?provider=lines"
                % (self.port, sid), timeout=10) as r:
            body = json.loads(r.read())
        self.assertEqual(body["kind"], "replay", body)
        self.assertIn("lines", body["handles"])


class ShadowUsesTheSameGate(unittest.TestCase):
    """build_agent_args emits Claude Code's flags. Every path that calls it must
    check the adapter, not just the one in ws_chat -- otherwise selecting a
    provider without a Claude-protocol adapter and starting Shadow spawns that
    binary with arguments it cannot parse, which is the failure the chat gate
    exists to prevent, reached by a second door."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sutra-shadowgate-")
        self.fake = os.path.join(self.tmp, "fake-lines")
        with open(self.fake, "w") as f:
            f.write(FAKE_LINES)
        os.chmod(self.fake, 0o755)
        cfg = os.path.join(self.tmp, "cfg")
        os.makedirs(cfg, exist_ok=True)
        self._saved = {k: os.environ.get(k) for k in
                       ("SUTRA_UI_PROVIDER", "SUTRA_UI_EXTRA_PROVIDER")}
        os.environ["SUTRA_UI_PROVIDER"] = "lines"
        os.environ["SUTRA_UI_EXTRA_PROVIDER"] = (
            "id=lines,name=Lines,bin=%s,config=%s" % (self.fake, cfg))

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_shadow_refuses_a_provider_with_no_claude_adapter(self):
        import app
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            app._shadow_args()
        self.assertEqual(cm.exception.status_code, 503)
        self.assertIn("lines", str(cm.exception.detail))

    def test_shadow_still_works_for_claude(self):
        os.environ["SUTRA_UI_PROVIDER"] = "claude"
        import app
        args = app._shadow_args()
        self.assertTrue(args and "--output-format" in args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
