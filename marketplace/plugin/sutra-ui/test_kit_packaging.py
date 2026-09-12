"""test_kit_packaging.py -- kit-built apps survive the ADR-039 round trip.

Export a materialized app of each kind (flag on), import it into a clean
home: the stamp travels inside module.json (unknown fields are preserved),
the installer reconstructs the APP.md skeleton with `not recorded` answers and
sets origin.imported, and the live check has no must-fix failure -- the
unanswered cells are WARNs, never FAILs.

Isolation (I-T1): temp homes set and cached modules popped before any import.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HOME_A = tempfile.mkdtemp(prefix="kit-pkg-a-")
HOME_B = tempfile.mkdtemp(prefix="kit-pkg-b-")
os.environ["SUTRA_MODULES_HOME"] = HOME_A
os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="kit-pkg-native-")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="kit-pkg-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="kit-pkg-shadow-"))
os.environ["KIT_NO_RENDER"] = "1"
for _m in ("placement_engine", "org_api", "project_import", "modules_api", "modules_events", "modules_pkg", "workspace_api", "app", "check"):
    sys.modules.pop(_m, None)

from fastapi.testclient import TestClient  # noqa: E402
import app as app_module  # noqa: E402
import providers  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/modules"


class KitPackaging(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        os.environ["SUTRA_MODULES_HOME"] = HOME_A
        for home in (HOME_A, HOME_B):
            for name in os.listdir(home):
                shutil.rmtree(os.path.join(home, name), ignore_errors=True)
        self._settings = providers.SETTINGS_PATH
        tmp = Path(tempfile.mkdtemp(prefix="kit-pkg-settings-")) / "settings.json"
        tmp.write_text(json.dumps({"flags": {"apps_publish": True}}), encoding="utf-8")
        providers.SETTINGS_PATH = tmp

    def tearDown(self):
        providers.SETTINGS_PATH = self._settings
        os.environ["SUTRA_MODULES_HOME"] = HOME_A

    def test_round_trip_keeps_the_stamp_and_reconstructs_the_record(self):
        for kind, extra in (("page", {}), ("chat", {"instructions": "You are the late-loans desk.\n- Never quote a phone number.\nWhich loans first?"}), ("link", {"screen": "balance"})):
            os.environ["SUTRA_MODULES_HOME"] = HOME_A
            r = self.client.post(BASE, json=dict({"name": "Trip %s" % kind, "tagline": "the late loans, oldest first", "kind": kind}, **extra), headers=HDR)
            self.assertEqual(r.status_code, 201, r.text)
            mid = r.json()["id"]
            stamp = r.json()["frameworkKit"]
            r = self.client.post(BASE + "/" + mid + "/export", headers=HDR)
            self.assertEqual(r.status_code, 200, r.text)
            blob = Path(r.json()["artifact_path"]).read_bytes()
            sha = hashlib.sha256(blob).hexdigest()

            os.environ["SUTRA_MODULES_HOME"] = HOME_B
            r = self.client.post(BASE + "/import?id=%s&sha256=%s" % (mid, sha), content=blob, headers=dict(HDR, **{"Content-Type": "application/gzip"}))
            self.assertEqual(r.status_code, 201, r.text)
            self.assertTrue(r.json()["record_reconstructed"], kind)
            folder = Path(HOME_B) / mid
            raw = json.loads((folder / "module.json").read_text())
            self.assertEqual(raw["frameworkKit"]["version"], stamp["version"], "the stamp travelled inside module.json")
            self.assertEqual(raw["frameworkKit"]["created_at"], stamp["created_at"])
            self.assertEqual(raw["origin"]["created_by"], "marketplace")
            self.assertTrue(raw["origin"]["imported"])
            self.assertEqual(raw["publish"]["state"], "imported")
            rec = (folder / "APP.md").read_text()
            self.assertEqual(json.loads(rec.splitlines()[0][len("frameworkKit: "):]), raw["frameworkKit"], "reconstructed line 1 equals the mirror")
            self.assertIn("| not recorded |", rec)
            self.assertIn("# Trip %s" % kind, rec)
            j = self.client.get(BASE + "/" + mid + "/checks", headers=HDR).json()
            live = j["live"]
            self.assertFalse(live["blocked"], "%s: must-fix failures after import: %s" % (kind, live["fails"]))
            by = {c["id"]: c for c in live["checks"]}
            self.assertEqual(by["C1"]["status"], "warn", by["C1"])
            self.assertEqual(by["C20"]["status"], "pass", by["C20"])
            self.assertEqual(by["C8"]["status"], "pass", "server-owned publish state passes")
            self.assertEqual(by["C17"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
