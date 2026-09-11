"""test_registry_isolation.py -- the operator's registry survives the test suite.

Regression for the 2026-09-11 wipe (holding/research/2026-09-11-registry-reset-
rca.md): a whole-directory pytest run imported the app before the Apps modules
set their temp SUTRA_NATIVE_HOME, so placement_engine stayed bound to the real
~/.sutra-native/user-kit and two setUp loops emptied it. 68 departments gone.

This test replays that exact collection order (an app-importing module first,
then the two Apps modules) in a child pytest process under a throwaway HOME
that holds a canary domain, and asserts the canary is still there afterwards
and nothing foreign was minted next to it. It is the acceptance check for I-T1
(placement_engine refuses the default home under pytest) and for the Apps
modules' re-bind. Runtime about one second; it is the only test allowed to
spawn pytest.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["test_activity.py", "test_modules_api.py", "test_modules_events.py"]


class TestRegistryIsolation(unittest.TestCase):

    def test_whole_directory_order_never_touches_the_default_home(self):
        fake_home = tempfile.mkdtemp(prefix="registry-isolation-home-")
        domains = Path(fake_home) / ".sutra-native" / "user-kit" / "domains"
        domains.mkdir(parents=True)
        canary = domains / "dref-canary000000000.json"
        canary.write_text(json.dumps({"ref": "dref-canary000000000", "name": "CANARY",
                                      "parent_ref": None, "status": "active",
                                      "tenant_id": "T-local"}), encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k not in ("SUTRA_NATIVE_HOME", "PYTEST_CURRENT_TEST", "PYTEST_ADDOPTS")}
        env["HOME"] = fake_home
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
             "--rootdir", str(HERE)] + [str(HERE / f) for f in ORDER],
            cwd=str(HERE), env=env, capture_output=True, text=True, timeout=600)
        tail = "\n".join(proc.stdout.splitlines()[-15:])
        self.assertTrue(canary.exists(),
                        "the canary in the default home was deleted by the suite:\n" + tail)
        drefs = sorted(p.name for p in domains.glob("dref-*.json"))
        self.assertEqual(drefs, ["dref-canary000000000.json"],
                         "foreign domains were minted in the default home: %s\n%s" % (drefs, tail))
        self.assertEqual(proc.returncode, 0, "child pytest failed:\n" + tail)


if __name__ == "__main__":
    unittest.main()
