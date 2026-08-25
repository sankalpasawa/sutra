"""PLAN-100 S63: feed emit -> GET p95 under the 1s budget, measured live."""
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
if not os.path.exists(VENV_PY):
    VENV_PY = "python3"


class TestFeedLatency(unittest.TestCase):
    def test_p95_under_budget(self):
        tmp = tempfile.mkdtemp(prefix="feedlat-")
        settings = os.path.join(tmp, "settings.json")
        with open(settings, "w") as f:
            json.dump({"shadow.enabled": True}, f)
        s = socket.socket(); s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]; s.close()
        env = dict(os.environ, SUTRA_UI_SETTINGS=settings,
                   SUTRA_SHADOW_HOME=tmp, SUTRA_UI_WORKDIR_ROOT=tmp)
        env.pop("ANTHROPIC_API_KEY", None)
        proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(port), "--log-level", "warning"],
            cwd=HERE, env=env, stdout=subprocess.PIPE,
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
            os.environ["SUTRA_SHADOW_HOME"] = tmp
            import importlib
            import shadow_feed
            importlib.reload(shadow_feed)
            samples = []
            for i in range(20):
                t0 = time.monotonic()
                ok, problems = shadow_feed.emit({
                    "item_id": "lat-%d" % i, "producer": "shadow",
                    "kind": "info", "title": "latency probe %d" % i,
                    "deep_link": "sutra://x", "dedupe_key": "lat-%d" % i,
                    "state": "new"})
                self.assertTrue(ok, problems)
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/shadow/feed" % port,
                        timeout=5) as resp:
                    doc = json.loads(resp.read())
                self.assertTrue(any(it["item_id"] == "lat-%d" % i
                                    for it in doc["items"]))
                samples.append((time.monotonic() - t0) * 1000)
            samples.sort()
            p95 = samples[int(round(0.95 * len(samples))) - 1]
            print("feed emit->GET p95: %.1fms (budget 1000ms)" % p95)
            self.assertLess(p95, 1000)
        finally:
            os.environ.pop("SUTRA_SHADOW_HOME", None)
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
