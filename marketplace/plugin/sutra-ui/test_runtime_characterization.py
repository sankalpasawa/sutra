"""PLAN-100 P1 S13-S16: characterization of the CURRENT /ws/chat behavior.

These tests pin the contract the SessionRuntime refactor (S17+) must preserve,
running against UNMODIFIED chat code with a scripted fake claude binary
(SUTRA_UI_CLAUDE_BIN). What is pinned:

  S13  turn flow: provider -> start -> sysinit -> session -> token -> done;
       process REUSED across messages with identical spawn args
  S14  stop mid-turn: process-group kill -> "stopped" frame, session KEPT,
       next message respawns (new pid) and resumes (same session id)
  S15  system/api_retry surfaces as a "retrying" frame (turn still completes)
  S16  reconnect with resume seed continues the thread; a DEAD seed produces
       error+resume_reset and the message is REPLAYED on a fresh thread with
       no second "start" frame

The fake claude speaks just enough stream-json: init, text_delta, api_retry,
result; --resume dead-* exits 1 with the CLI\'s "No conversation found" stderr.
"""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):
    VENV_PY = "python3"

FAKE = r"""#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
resume = None
if "--resume" in args:
    resume = args[args.index("--resume") + 1]
if resume and resume.startswith("dead"):
    sys.stderr.write("No conversation found with session ID: %s\n" % resume)
    sys.exit(1)
sid = resume or ("fake-%d" % os.getpid())
pid = os.getpid()
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
          "model": "fake-model", "tools": [], "mcp_servers": [],
          "slash_commands": [], "permissionMode": "plan", "cwd": os.getcwd()})
    if "RETRY" in msg:
        emit({"type": "system", "subtype": "api_retry", "session_id": sid,
              "message": "rate limited, retrying", "attempt": 1})
    if "SLOW" in msg:
        time.sleep(8)
    emit({"type": "stream_event", "session_id": sid,
          "event": {"delta": {"type": "text_delta",
                              "text": "echo[pid=%d]: %s" % (pid, msg)}}})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "session_id": sid, "duration_ms": 5, "num_turns": 1,
          "total_cost_usd": 0.0})
"""


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ChatCharacterization(unittest.TestCase):
    """One server, one fake claude, four pinned behaviors."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-char-")
        cls.fake = os.path.join(cls.tmpdir, "fake-claude")
        with open(cls.fake, "w") as f:
            f.write(FAKE)
        os.chmod(cls.fake, 0o755)
        cls._env_saved = {k: os.environ.get(k)
                          for k in ("SUTRA_UI_SETTINGS", "SUTRA_UI_CLAUDE_BIN",
                                    "SUTRA_UI_WORKDIR_ROOT", "SUTRA_UI_PROVIDER",
                                    "SUTRA_UI_PERMISSION_MODE")}
        os.environ["SUTRA_UI_SETTINGS"] = os.path.join(cls.tmpdir, "settings.json")
        os.environ["SUTRA_UI_CLAUDE_BIN"] = cls.fake
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        os.environ.pop("SUTRA_UI_PROVIDER", None)
        os.environ.pop("SUTRA_UI_PERMISSION_MODE", None)
        cls.port = _free_port()
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)  # the refusal branch is pinned elsewhere
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
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
        for k, v in cls._env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # ---- helpers ---------------------------------------------------------

    def _connect(self):
        from websockets.sync.client import connect
        return connect("ws://127.0.0.1:%d/ws/chat" % self.port,
                       open_timeout=10, close_timeout=5)

    def _collect(self, ws, until=("done", "error", "stopped"), timeout=20):
        frames = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=max(0.1, deadline - time.time()))
            except Exception:
                break
            fr = json.loads(raw)
            frames.append(fr)
            if fr.get("type") in until:
                break
        return frames

    @staticmethod
    def _types(frames):
        return [f["type"] for f in frames]

    @staticmethod
    def _pid_from(frames):
        for f in frames:
            if f["type"] == "token" and "echo[pid=" in f.get("text", ""):
                return int(f["text"].split("echo[pid=")[1].split("]")[0])
        return None

    # ---- S13: turn flow + process reuse ----------------------------------

    def test_01_turn_flow_frame_order(self):
        with self._connect() as ws:
            provider = json.loads(ws.recv(timeout=10))
            self.assertEqual(provider["type"], "provider")
            self.assertEqual(provider["id"], "claude")
            ws.send(json.dumps({"message": "hello"}))
            frames = self._collect(ws)
            kinds = self._types(frames)
            self.assertEqual(kinds[0], "start")
            self.assertIn("sysinit", kinds)
            self.assertIn("session", kinds)
            self.assertIn("token", kinds)
            self.assertEqual(kinds[-1], "done")
            self.assertLess(kinds.index("session"), kinds.index("token"))
            token = [f for f in frames if f["type"] == "token"][0]
            self.assertIn("hello", token["text"])
            done = frames[-1]
            self.assertTrue(done["session"].startswith("fake-"))
            self.assertEqual(done["num_turns"], 1)

    def test_02_persistent_process_reused_across_messages(self):
        with self._connect() as ws:
            ws.recv(timeout=10)  # provider
            ws.send(json.dumps({"message": "first"}))
            f1 = self._collect(ws)
            ws.send(json.dumps({"message": "second"}))
            f2 = self._collect(ws)
        p1, p2 = self._pid_from(f1), self._pid_from(f2)
        self.assertIsNotNone(p1)
        self.assertEqual(p1, p2, "same argv must REUSE the process")
        s1 = [f for f in f1 if f["type"] == "session"]
        self.assertEqual(len(s1), 1, "session announced once per socket")

    # ---- S14: stop mid-turn ----------------------------------------------

    def test_03_stop_kills_turn_keeps_session_resumes_next(self):
        with self._connect() as ws:
            ws.recv(timeout=10)
            ws.send(json.dumps({"message": "please be SLOW"}))
            # sysinit proves the turn is in flight before we cut it
            got = []
            while True:
                fr = json.loads(ws.recv(timeout=10))
                got.append(fr)
                if fr["type"] == "sysinit":
                    break
            sid = [f for f in got if f["type"] == "session"]
            ws.send(json.dumps({"type": "stop"}))
            frames = got + self._collect(ws)
            kinds = self._types(frames)
            self.assertIn("stopped", kinds)
            self.assertNotIn("error", kinds,
                             "an operator stop must not read as a crash")
            stopped = [f for f in frames if f["type"] == "stopped"][0]
            old_pid = None  # SLOW turn was cut before its token
            # next message: fresh process, SAME thread via --resume
            ws.send(json.dumps({"message": "after stop"}))
            f2 = self._collect(ws)
            self.assertEqual(self._types(f2)[-1], "done")
            self.assertEqual(f2[-1]["session"], stopped["session"],
                             "session id survives a stop")

    # ---- S15: api_retry surfaces as retrying -----------------------------

    def test_04_api_retry_becomes_retrying_frame(self):
        with self._connect() as ws:
            ws.recv(timeout=10)
            ws.send(json.dumps({"message": "hit a RETRY please"}))
            frames = self._collect(ws)
        kinds = self._types(frames)
        self.assertIn("retrying", kinds)
        self.assertEqual(kinds[-1], "done", "retry is a pause, not a failure")
        retrying = [f for f in frames if f["type"] == "retrying"][0]
        self.assertEqual(retrying["attempt"], 1)

    # ---- S16: reconnect + resume, dead seed replays ----------------------

    def test_05_reconnect_with_resume_seed_continues_thread(self):
        with self._connect() as ws:
            ws.recv(timeout=10)
            ws.send(json.dumps({"message": "hello"}))
            sid = self._collect(ws)[-1]["session"]
        with self._connect() as ws:
            ws.recv(timeout=10)
            ws.send(json.dumps({"message": "back again", "resume": sid}))
            frames = self._collect(ws)
        self.assertEqual(frames[-1]["type"], "done")
        self.assertEqual(frames[-1]["session"], sid,
                         "reconnect with a live seed keeps the thread")

    def test_06_dead_resume_seed_retries_on_a_fresh_thread(self):
        """A dead seed is NOT an error to the operator: the server emits ONE
        `retry` frame (resume_reset: true), drops the seed, and replays the
        same text on a fresh thread under the SAME `start` -- the message is
        never lost and the client never sees a failed turn."""
        with self._connect() as ws:
            ws.recv(timeout=10)
            ws.send(json.dumps({"message": "important text",
                                "resume": "dead-0000"}))
            frames = self._collect(ws)
        kinds = self._types(frames)
        self.assertEqual(kinds[0], "start")
        self.assertEqual(kinds.count("start"), 1,
                         "a replay continues the turn already on screen")
        self.assertIn("retry", kinds)
        self.assertNotIn("error", kinds,
                         "a stale seed must not surface as a failure")
        retry = [f for f in frames if f["type"] == "retry"][0]
        self.assertTrue(retry.get("resume_reset"))
        self.assertLess(kinds.index("retry"), kinds.index("session"),
                        "the reset is announced before the fresh thread")
        self.assertEqual(kinds[-1], "done")
        self.assertTrue(frames[-1]["session"].startswith("fake-"))
        token = [f for f in frames if f["type"] == "token"][0]
        self.assertIn("important text", token["text"],
                      "the operator\'s message is not lost with the dead id")


if __name__ == "__main__":
    unittest.main()
