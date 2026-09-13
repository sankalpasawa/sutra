"""test_shadow_smoke_cycle.py -- ONE real watch -> say -> verify cycle.

Opt-in, never part of the default gate: it runs the REAL claude binary and
writes to the operator's REAL shadow home, so the actions ledger ends up with
a say row and a done row for a mission that actually drove a chat. Costs two
Claude turns (one to open the pane, one for Shadow's say).

    SUTRA_SHADOW_SMOKE=1 ./run-tests.sh test_shadow_smoke_cycle.py

Everything else about the flow is the mounted-engine journey in
test_shadow_runner.py (chat -> mission -> start_now -> loop -> done).
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):
    VENV_PY = sys.executable

SMOKE = os.environ.get("SUTRA_SHADOW_SMOKE") == "1"
LIVE_HOME = os.path.expanduser("~/.sutra-ui/shadow")
FIXTURE_PREFIXES = ("fake-", "delegate-fake-", "runner-fake-", "say-fake-",
                    "shadow-fake-", "pubfake-", "floor-choke-")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close()
    return port


@unittest.skipUnless(SMOKE, "opt-in: SUTRA_SHADOW_SMOKE=1 spends two real Claude turns")
class TestRealCycle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._saved = {k: os.environ.get(k) for k in
                      ("SUTRA_SHADOW_HOME", "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS")}
        # a DELIBERATE integration test against the live home, said so
        os.environ["SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS"] = "1"
        os.environ["SUTRA_SHADOW_HOME"] = LIVE_HOME
        cls.tmp = tempfile.mkdtemp(prefix="shadow-smoke-")
        settings = os.path.join(cls.tmp, "settings.json")
        with open(settings, "w") as f:
            json.dump({}, f)              # shadow ON by default
        env = dict(os.environ, SUTRA_UI_SETTINGS=settings,
                   SUTRA_UI_WORKDIR_ROOT=cls.tmp)
        env.pop("SUTRA_UI_CLAUDE_BIN", None)     # the real binary
        cls.port = _free_port()
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 20
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

    def _post(self, path, body):
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    def _get(self, path):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (self.port, path), timeout=10) as r:
            return json.loads(r.read())

    def test_10_one_real_cycle_leaves_a_real_action_row(self):
        from websockets.sync.client import connect
        import shadow_ledger
        # WATCH: a real pane; the app auto-watches it
        ws = connect("ws://127.0.0.1:%d/ws/chat" % self.port, open_timeout=10)
        ws.recv(timeout=10)
        ws.send(json.dumps({"message": "Reply with the single word: ready"}))
        sid = None
        deadline = time.time() + 180
        while time.time() < deadline:
            fr = json.loads(ws.recv(timeout=180))
            if fr.get("type") == "session":
                sid = fr["id"]
            if fr.get("type") == "done":
                break
        self.assertTrue(sid, "the pane must report its session id")
        with open(os.path.join(LIVE_HOME, "watches.json")) as h:
            self.assertIn(sid, json.load(h), "the pane is watched")
        # SAY: a mission on that pane with a marker only a real turn can produce
        marker = "SMOKE-OK-%d" % int(time.time())
        m = self._post("/api/shadow/missions", {
            "objective": "Reply with exactly this text and nothing else: %s" % marker,
            "template": "fix", "target_session": sid,
            "done_when": [{"tier": "contains_artifact", "check": marker}]})
        mid = m["id"]
        started = self._post("/api/shadow/missions/%s/act" % mid,
                             {"action": "start_now"})
        self.assertTrue(started.get("accepted"))
        # VERIFY: the loop evaluates contains_artifact against the transcript
        final = None
        deadline = time.time() + 240
        while time.time() < deadline:
            final = next(x for x in self._get("/api/shadow/missions")["missions"]
                         if x["id"] == mid)
            if final["state"] in ("done", "failed", "stopped", "blocked"):
                break
            time.sleep(2)
        ws.close()
        self.assertEqual(final["state"], "done", final)
        rows = [r for r in shadow_ledger.read("actions", 500)
                if r.get("mission_id") == mid]
        kinds = {r["kind"] for r in rows}
        self.assertIn("say", kinds, rows)
        self.assertIn("done", kinds, rows)
        for r in rows:
            self.assertFalse(any(p in (r.get("summary") or "")
                                 for p in FIXTURE_PREFIXES), r)
        print("\nSMOKE: mission %s on session %s left %d real action rows"
              % (mid, sid, len(rows)))


if __name__ == "__main__":
    unittest.main()
