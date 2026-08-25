"""PLAN-100 S32-S37: egress scrub, ledger, gate table, and the say chain.

The say chain end to end: capability token -> flag -> registry -> mission ->
dedupe -> scrub -> tag -> TurnQueue -> boundary delivery into the live pane.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):
    VENV_PY = "python3"

import shadow_egress
import shadow_ledger

FAKE = r"""#!/usr/bin/env python3
import json, os, sys
sid = "say-fake-%d" % os.getpid()
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
    if "SLOW" in msg:
        import time as _t
        _t.sleep(2)
    emit({"type": "stream_event", "session_id": sid,
          "event": {"delta": {"type": "text_delta",
                              "text": "echo: " + msg[:200]}}})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "session_id": sid, "duration_ms": 1, "num_turns": 1,
          "total_cost_usd": 0.0})
"""


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestScrubber(unittest.TestCase):
    def test_01_credential_shapes_redacted(self):
        text = ("key sk-abcdefghijklmnop and ghp_" + "a" * 24
                + " and xoxb-1234567890-abc and AKIAABCDEFGHIJKLMNOP"
                + " and Bearer abcdef1234567890abcdef")
        clean, n = shadow_egress.scrub(text)
        self.assertEqual(n, 5)
        self.assertNotIn("sk-abcdefghijklmnop", clean)
        self.assertNotIn("xoxb-", clean)

    def test_02_plain_text_untouched(self):
        clean, n = shadow_egress.scrub("fix the failing test in charter filter")
        self.assertEqual(n, 0)
        self.assertEqual(clean, "fix the failing test in charter filter")


class TestGateTable(unittest.TestCase):
    def test_03_every_shadow_tool_has_a_gate_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"shadow.enabled": True}))
            env = dict(os.environ, SUTRA_UI_SETTINGS=str(settings),
                       SUTRA_MCP_SHADOW="1")
            out = subprocess.run(
                [sys.executable, "-c",
                 "import sutra_mcp, json;"
                 "print(json.dumps([t['name'] for t in sutra_mcp.TOOLS"
                 " if t['name'].startswith('shadow_')]))"],
                capture_output=True, text=True, cwd=HERE, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            names = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertGreaterEqual(len(names), 6)
        for name in names:
            self.assertIn(name, shadow_egress.TOOL_GATES,
                          "%s registered without a gate row" % name)


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    def test_04_append_stamps_and_read_returns(self):
        row = shadow_ledger.append("actions", {"kind": "say", "summary": "x",
                                               "mission_id": "m-1"})
        self.assertTrue(row["id"].startswith("acti-"))
        self.assertIn("ts", row)
        rows = shadow_ledger.read("actions")
        self.assertEqual(rows[-1]["id"], row["id"])

    def test_05_kind_validation_and_row_shape(self):
        with self.assertRaises(ValueError):
            shadow_ledger.append("nope", {})
        with self.assertRaises(ValueError):
            shadow_ledger.append("actions", "not a dict")

    def test_06_oversized_row_refused(self):
        with self.assertRaises(ValueError):
            shadow_ledger.append("actions", {"blob": "x" * 9000})

    def test_07_symlink_escape_refused(self):
        outside = tempfile.mkdtemp(prefix="shadow-escape-")
        os.makedirs(os.path.join(self.tmp.name, "ledger"), exist_ok=True)
        link = os.path.join(self.tmp.name, "ledger", "actions.jsonl")
        os.symlink(os.path.join(outside, "stolen.jsonl"), link)
        with self.assertRaises(ValueError):
            shadow_ledger.append("actions", {"a": 1})

    def test_08_torn_line_skipped_not_fatal(self):
        shadow_ledger.append("missions", {"a": 1})
        with open(os.path.join(self.tmp.name, "ledger", "missions.jsonl"),
                  "a") as f:
            f.write("{torn")
        rows = shadow_ledger.read("missions")
        self.assertEqual(len(rows), 1)


class TestSayChain(unittest.TestCase):
    """One live server + fake claude; the full authorization chain."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-say-")
        cls.fake = os.path.join(cls.tmpdir, "fake-claude")
        with open(cls.fake, "w") as f:
            f.write(FAKE)
        os.chmod(cls.fake, 0o755)
        cls._env_saved = {k: os.environ.get(k)
                          for k in ("SUTRA_UI_SETTINGS", "SUTRA_UI_CLAUDE_BIN",
                                    "SUTRA_UI_WORKDIR_ROOT")}
        settings = os.path.join(cls.tmpdir, "settings.json")
        with open(settings, "w") as f:
            json.dump({"shadow.enabled": True}, f)
        os.environ["SUTRA_UI_SETTINGS"] = settings
        os.environ["SUTRA_UI_CLAUDE_BIN"] = cls.fake
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = cls.tmpdir
        cls.port = _free_port()
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
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
        # the say token lives in the SERVER's env; fish it out via a debug
        # read of its /proc is not portable -- instead the server exported it
        # to its own environ, so ask it politely: spawn a child of ourselves?
        # Simpler: the endpoint answers 401 for a wrong token, and the REAL
        # token is only needed for the accept path -- fetch it from the
        # server process env via lsof is fragile, so the accept-path test
        # spawns its OWN app in-process instead. See test_13.

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

    def _post(self, sid, body, token=None):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/sessions/%s/say" % (self.port, sid),
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json",
                     **({"x-shadow-say-token": token} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def test_10_no_token_is_401_and_learns_nothing(self):
        code, body = self._post("whatever", {"message": "x",
                                             "mission_id": "m-1"})
        self.assertEqual(code, 401)

    def test_11_wrong_token_is_401(self):
        code, _ = self._post("whatever", {"message": "x", "mission_id": "m-1"},
                             token="0" * 48)
        self.assertEqual(code, 401)


class TestSayAccepted(unittest.TestCase):
    """In-process app: the accept path with the real token, through the ws."""

    def test_13_full_chain_boundary_delivery_and_races(self):
        import asyncio
        import websockets.sync.client as wsc
        import importlib

        tmp = tempfile.mkdtemp(prefix="say-accept-")
        fake = os.path.join(tmp, "fake-claude")
        with open(fake, "w") as f:
            f.write(FAKE)
        os.chmod(fake, 0o755)
        settings = os.path.join(tmp, "settings.json")
        with open(settings, "w") as f:
            json.dump({"shadow.enabled": True}, f)
        port = _free_port()
        env = dict(os.environ, SUTRA_UI_SETTINGS=settings,
                   SUTRA_UI_CLAUDE_BIN=fake, SUTRA_UI_WORKDIR_ROOT=tmp,
                   SUTRA_SAY_TOKEN_ECHO=os.path.join(tmp, "token.txt"))
        env.pop("ANTHROPIC_API_KEY", None)
        code = "; ".join([
            "import os, uvicorn, app",
            "open(os.environ['SUTRA_SAY_TOKEN_ECHO'], 'w').write(app.SHADOW_SAY_TOKEN)",
            "uvicorn.run(app.app, host='127.0.0.1', port=%d, log_level='warning')" % port,
        ])
        proc = subprocess.Popen([VENV_PY, "-c", code], cwd=HERE, env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/org/stats" % port, timeout=1)
                    break
                except Exception:
                    time.sleep(0.25)
            token = open(os.path.join(tmp, "token.txt")).read().strip()

            ws = wsc.connect("ws://127.0.0.1:%d/ws/chat" % port,
                             open_timeout=10)
            ws.recv(timeout=10)  # provider
            ws.send(json.dumps({"message": "hello"}))
            sid = None
            deadline = time.time() + 20
            while time.time() < deadline:
                fr = json.loads(ws.recv(timeout=10))
                if fr["type"] == "session":
                    sid = fr["id"]
                if fr["type"] == "done":
                    break
            self.assertTrue(sid)

            def post(body, tok=token):
                req = urllib.request.Request(
                    "http://127.0.0.1:%d/api/sessions/%s/say" % (port, sid),
                    data=json.dumps(body).encode("utf-8"),
                    headers={"content-type": "application/json",
                             "x-shadow-say-token": tok})
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return resp.status, json.loads(resp.read())
                except urllib.error.HTTPError as exc:
                    return exc.code, exc.read().decode()

            # 400: mission required
            code_, _ = post({"message": "no mission"})
            self.assertEqual(code_, 400)
            # 404: unknown session
            req = urllib.request.Request(
                "http://127.0.0.1:%d/api/sessions/nope/say" % port,
                data=json.dumps({"message": "x",
                                 "mission_id": "m"}).encode(),
                headers={"content-type": "application/json",
                         "x-shadow-say-token": token})
            try:
                urllib.request.urlopen(req, timeout=10)
                self.fail("expected 404")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)
            # accept + scrub: the queued turn lands at the boundary, tagged
            code_, body = post({"message": "run check sk-abcdefghijklmnop now",
                                "mission_id": "m-42",
                                "dedupe_key": "%s:say-1:shadow" % sid})
            self.assertEqual(code_, 200)
            self.assertEqual(body["redactions"], 1)
            # 409 on the same key
            code_, _ = post({"message": "again",
                             "mission_id": "m-42",
                             "dedupe_key": "%s:say-1:shadow" % sid})
            self.assertEqual(code_, 409)
            # the shadow turn streams into the SAME pane, tagged + scrubbed
            texts = []
            deadline = time.time() + 20
            while time.time() < deadline:
                fr = json.loads(ws.recv(timeout=15))
                if fr["type"] == "token":
                    texts.append(fr["text"])
                if fr["type"] == "done":
                    break
            joined = " ".join(texts)
            self.assertIn("[Shadow \u00b7 mission m-42]", joined)
            self.assertNotIn("sk-abcdefghijklmnop", joined)
            # race, made DETERMINISTIC: while a turn is IN FLIGHT, queue a
            # shadow say AND an operator message. At the boundary both are
            # waiting -- the operator must go first. (Posting to an idle pane
            # and racing the socket is a coin flip, not the invariant.)
            ws.send(json.dumps({"message": "please be SLOW"}))
            time.sleep(0.5)  # the SLOW turn is now in flight
            post({"message": "shadow-second", "mission_id": "m-43"})
            ws.send(json.dumps({"message": "operator-first"}))
            # drain the SLOW turn first
            deadline = time.time() + 20
            while time.time() < deadline:
                fr = json.loads(ws.recv(timeout=15))
                if fr["type"] == "done":
                    break
            order = []
            deadline = time.time() + 30
            dones = 0
            while time.time() < deadline and dones < 2:
                fr = json.loads(ws.recv(timeout=15))
                if fr["type"] == "token":
                    order.append(fr["text"])
                if fr["type"] == "done":
                    dones += 1
            joined = " ".join(order)
            self.assertLess(joined.index("operator-first"),
                            joined.index("shadow-second"),
                            "the founder never queues behind automation")
            ws.close()
        finally:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
