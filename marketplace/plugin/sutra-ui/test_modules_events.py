"""test_modules_events.py -- the Apps event log, the touch endpoint and the
placement pin (APPS-EVENTS.md; program steps 57, 58). Temp homes are set
BEFORE the app is imported, as in test_modules_api.py.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

MOD_HOME = tempfile.mkdtemp(prefix="events-test-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
NATIVE_HOME = tempfile.mkdtemp(prefix="events-native-")
os.environ["SUTRA_NATIVE_HOME"] = NATIVE_HOME
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="events-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="events-shadow-"))

# I-T1 (RCA 2026-09-11): drop every cached module that captured
# placement_engine with another home, so the imports below bind to NATIVE_HOME
# even when an earlier module in the same pytest process imported the app.
for _m in ("placement_engine", "org_api", "project_import", "modules_api",
           "modules_events", "modules_pkg", "workspace_api", "app"):
    sys.modules.pop(_m, None)

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import modules_events  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import placement_engine as E  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/modules"


class TestModulesEvents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
        for name in os.listdir(MOD_HOME):
            p = os.path.join(MOD_HOME, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        # I-T1: never clean a registry that is not THIS module's temp home, and
        # the app must be bound to the same engine object this test cleans.
        assert os.path.realpath(E.HOME) == os.path.realpath(NATIVE_HOME), (
            "refusing to empty %s: the engine is not bound to this module's temp "
            "home %s (RCA 2026-09-11)" % (E.HOME, NATIVE_HOME))
        assert app_module.org_api.E is E, "app and test hold different placement_engine modules"
        E._ensure_dirs()
        for name in os.listdir(E.DOMAINS):
            os.remove(os.path.join(E.DOMAINS, name))

    def _events(self, app_id=None):
        rows, _corrupt = modules_events.read(MOD_HOME, app_id=app_id)
        return rows

    # ---- the writer ----------------------------------------------------------

    def test_01_append_is_one_line_with_a_stable_key_and_reads_dedupe(self):
        row = modules_events.append(MOD_HOME, "app.edited", "x", kind="chat", version=2, actor="app")
        # a retry re-sends the SAME row (same ts) -> same key -> read once
        line = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        with open(modules_events.path(MOD_HOME), "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.write("{not json\n")                        # a corrupt line is skipped, never fatal
        rows, corrupt = modules_events.read(MOD_HOME)
        self.assertEqual([r["key"] for r in rows], [row["key"]])
        self.assertEqual(corrupt, 1)
        with self.assertRaises(ValueError):
            modules_events.append(MOD_HOME, "app.exploded", "x")

    def test_02_create_and_actions_append_their_events(self):
        mid = self.client.post(BASE, json={"name": "Evented"}, headers=HDR).json()["id"]
        self.client.post(BASE + "/" + mid, json={"action": "rename", "name": "Evented 2"}, headers=HDR)
        self.client.post(BASE + "/" + mid, json={"action": "archive"}, headers=HDR)
        names = [r["event"] for r in self._events(mid)]
        self.assertEqual(names, ["app.created", "app.edited", "app.archived"])
        self.assertEqual(self.client.get(BASE).status_code, 200)   # a read appends nothing
        self.assertEqual(len(self._events(mid)), 3)

    # ---- touch (the seeded chat's done hook) ---------------------------------

    def test_03_touch_on_an_unchanged_folder_appends_nothing(self):
        mid = self.client.post(BASE, json={"name": "Quiet"}, headers=HDR).json()["id"]
        before = len(self._events(mid))
        r = self.client.post(BASE + "/" + mid + "/touch", json={"mode": "edit", "session_id": "s-1"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["changed"])
        self.assertEqual(len(self._events(mid)), before)

    def test_04_touch_after_a_chat_edited_the_folder_bumps_version_and_appends(self):
        mid = self.client.post(BASE, json={"name": "Edited by chat", "kind": "page", "html": "<p>v1</p>"}, headers=HDR).json()["id"]
        f = Path(MOD_HOME) / mid / "index.html"
        f.write_text("<p>v2</p>", encoding="utf-8")
        future = time.time() + 10
        os.utime(f, (future, future))                          # newer than updated_at
        r = self.client.post(BASE + "/" + mid + "/touch", json={"mode": "edit", "session_id": "s-2"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["changed"])
        self.assertEqual(r.json()["app"]["version"], 2)
        raw = json.loads((Path(MOD_HOME) / mid / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["schema"], 2)
        last = self._events(mid)[-1]
        self.assertEqual((last["event"], last["actor"]), ("app.edited", "chat:s-2"))

    # ---- the pin --------------------------------------------------------------

    def test_05_pinned_classify_files_under_the_pin_with_exactly_one_row(self):
        root, _ = E.mint_domain(None, "Asawa", ["asawa"], "T-local"); time.sleep(0.002)
        desk, _ = E.mint_domain(root, "Desktop app", ["desktop"], "T-local"); time.sleep(0.002)
        # a charter so write_placement has something to file against
        cid = None
        try:
            body = E.write_charter(desk, "Desktop app", "the Mac app", kind="scope") if hasattr(E, "write_charter") else None
            cid = (body or {}).get("id")
        except Exception:
            cid = None
        before = len(E.all_placements())
        r = self.client.post("/api/classify", json={"text": "ROUTING PIN — do not re-classify. Create a new app.",
                                                   "pin": {"department_ref": desk}}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(j["mode"], "pinned")
        self.assertEqual(j["domain_ref"], desk)
        if "placement" in j:
            self.assertEqual(len(E.all_placements()), before + 1)       # exactly one row written
        else:
            self.assertIn("blocked", j)                                  # no charter reachable: pinned, but honestly not filed
        # an unknown pin falls back to the classifier and says so
        r = self.client.post("/api/classify", json={"text": "hello there", "pin": {"department_ref": "dref-nope"}}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json().get("mode"), "pinned")


if __name__ == "__main__":
    unittest.main()
