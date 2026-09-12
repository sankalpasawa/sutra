"""test_kit_upgrade.py -- a newer kit never rewrites an existing app (D75 ruling 2).

Copy on create: an app is held to the kit installed when its folder was made.
Installing kit 1.1.0 beside apps stamped 1.0.0 changes no byte and no mtime
under the modules home; the live check reports C20 as WARN (newer installed);
only the explicit `migrate_kit` action, the builder's yes, rewrites the two
stamp copies -- and nothing else (no version bump, no updated_ms, no event).

Isolation (I-T1): temp homes set and cached modules popped before any import.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MOD_HOME = tempfile.mkdtemp(prefix="kit-upgrade-modules-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="kit-upgrade-native-")
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="kit-upgrade-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="kit-upgrade-shadow-"))
os.environ["KIT_NO_RENDER"] = "1"
for _m in ("placement_engine", "org_api", "project_import", "modules_api", "modules_events", "modules_pkg", "workspace_api", "app", "check"):
    sys.modules.pop(_m, None)

from fastapi.testclient import TestClient  # noqa: E402
import app as app_module  # noqa: E402
import modules_api  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/modules"


def _snapshot(root, ids):
    out = {}
    for mid in ids:
        for p in Path(root, mid).rglob("*"):
            if p.is_file():
                out[str(p.relative_to(root))] = (p.read_bytes(), p.stat().st_mtime_ns)
    return out


class KitUpgrade(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
        for name in os.listdir(MOD_HOME):
            shutil.rmtree(os.path.join(MOD_HOME, name), ignore_errors=True)
        self._kit_dir = modules_api._KIT_DIR

    def tearDown(self):
        modules_api._KIT_DIR = self._kit_dir

    def _newer_kit(self, version, digest):
        tmp = Path(tempfile.mkdtemp(prefix="kit-1-1-")) / "apps-frameworks"
        shutil.copytree(self._kit_dir, tmp, ignore=shutil.ignore_patterns("__pycache__"))
        kj = json.loads((tmp / "kit.json").read_text())
        kj["version"], kj["digest_short"] = version, digest
        (tmp / "kit.json").write_text(json.dumps(kj, indent=1))
        return tmp

    def test_upgrade_rewrites_nothing_and_migration_is_the_builders_yes(self):
        ids = []
        for kind, extra in (("page", {}), ("chat", {"instructions": "Say hi."}), ("link", {"screen": "balance"})):
            r = self.client.post(BASE, json=dict({"name": "Old %s" % kind, "tagline": "one line", "kind": kind}, **extra), headers=HDR)
            self.assertEqual(r.status_code, 201, r.text)
            ids.append(r.json()["id"])
        before = _snapshot(MOD_HOME, ids)
        old_version = json.loads((self._kit_dir / "kit.json").read_text())["version"]
        events = Path(MOD_HOME) / ".events.jsonl"

        # install kit 1.1.0 beside the server
        modules_api._KIT_DIR = self._newer_kit("1.1.0", "ffffffffffff")
        self.assertEqual(self.client.get(BASE + "/frameworks", headers=HDR).json()["version"], "1.1.0")
        r = self.client.post(BASE, json={"name": "Fresh page", "tagline": "one line", "kind": "page"}, headers=HDR)
        self.assertEqual(r.json()["frameworkKit"]["version"], "1.1.0", "a NEW app gets the new kit")
        self.assertEqual(_snapshot(MOD_HOME, ids), before, "no byte and no mtime of an existing app changed")
        ev_before = events.read_text() if events.exists() else ""     # after the create: its app.created row is expected

        # the live check says so, as a WARN
        j = self.client.get(BASE + "/" + ids[0] + "/checks", headers=HDR).json()
        c20 = next(c for c in j["live"]["checks"] if c["id"] == "C20")
        self.assertEqual(c20["status"], "warn", c20)
        self.assertIn("installed is 1.1.0", c20["detail"])
        self.assertEqual(j["stamped"], old_version)

        # the builder says yes: two stamp copies move, nothing else
        raw_before = json.loads((Path(MOD_HOME) / ids[0] / "module.json").read_text())
        rec_before = (Path(MOD_HOME) / ids[0] / "APP.md").read_text().splitlines()
        r = self.client.post(BASE + "/" + ids[0], json={"action": "migrate_kit"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        raw_after = json.loads((Path(MOD_HOME) / ids[0] / "module.json").read_text())
        self.assertEqual(raw_after["frameworkKit"]["version"], "1.1.0")
        self.assertEqual(raw_after["frameworkKit"]["digest"], "ffffffffffff")
        self.assertTrue(raw_after["frameworkKit"]["migrated"])
        self.assertEqual(raw_after["frameworkKit"]["created_at"], raw_before["frameworkKit"]["created_at"])
        for k in ("version", "updated_ms", "updated_at", "status", "name"):
            self.assertEqual(raw_after[k], raw_before[k], k)
        rec_after = (Path(MOD_HOME) / ids[0] / "APP.md").read_text().splitlines()
        self.assertEqual(json.loads(rec_after[0][len("frameworkKit: "):]), raw_after["frameworkKit"], "APP.md line 1 follows")
        self.assertEqual(rec_after[1:], rec_before[1:], "nothing else in the record moved")
        self.assertEqual(events.read_text() if events.exists() else "", ev_before, "a migration appends no event")
        j = self.client.get(BASE + "/" + ids[0] + "/checks", headers=HDR).json()
        self.assertEqual(next(c for c in j["live"]["checks"] if c["id"] == "C20")["status"], "pass")

    def test_migrate_kit_on_an_app_without_a_stamp_adopts_the_kit(self):
        """Adoption (2026-09-12, founder: "does this also work in the existing
        apps?"): an app built before the kit takes the stamp and gets the record
        it never had, every unanswered row reading `not recorded`; nothing else
        moves; audited as its own event. A second call is the ordinary migration."""
        kit = json.loads((self._kit_dir / "kit.json").read_text())
        (Path(MOD_HOME) / "legacy").mkdir()
        legacy = {"id": "legacy", "name": "Legacy", "tagline": "an old chat", "kind": "chat", "status": "ready", "version": 3,
                  "updated_ms": 1700000000000, "updated_at": "2026-01-01T00:00:00Z", "surface": {"instructions": "Say hi."}}
        (Path(MOD_HOME) / "legacy" / "module.json").write_text(json.dumps(legacy))
        events = Path(MOD_HOME) / ".events.jsonl"
        r = self.client.post(BASE + "/legacy", json={"action": "migrate_kit"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        raw = json.loads((Path(MOD_HOME) / "legacy" / "module.json").read_text())
        stamp = raw["frameworkKit"]
        self.assertEqual((stamp["version"], stamp["digest"], stamp["kind"]), (kit["version"], kit["digest_short"], "chat"))
        self.assertTrue(stamp["adopted"])
        self.assertEqual(r.json()["frameworkKit"], stamp, "the normalized row mirrors the stamp")
        for k in ("version", "updated_ms", "updated_at", "status", "name"):
            self.assertEqual(raw[k], legacy[k], k)
        rec = (Path(MOD_HOME) / "legacy" / "APP.md").read_text()
        self.assertEqual(json.loads(rec.splitlines()[0][len("frameworkKit: "):]), stamp, "APP.md line 1 equals the manifest mirror")
        self.assertIn("# Legacy", rec)
        self.assertRegex(rec, r"(?m)^\| P1 \| .+ \| not recorded \|$")
        self.assertNotRegex(rec, r"(?m)^\| (P|S|DS|E|B|F)[0-9]+ \| .+ \|\s*\|$", "no answer cell is left empty")
        # the events file is shared by every test in this home: count this app's rows only
        adopted = lambda: [l for l in (events.read_text() if events.exists() else "").splitlines()
                           if "app.kit_adopted" in l and '"app_id":"legacy"' in l]
        self.assertEqual(len(adopted()), 1, adopted())
        j = self.client.get(BASE + "/legacy/checks", headers=HDR).json()
        self.assertEqual(j["stamped"], kit["version"], "the checks now run for this app")
        # second call: the ordinary migration -- stamp refreshed, record untouched, no event
        r = self.client.post(BASE + "/legacy", json={"action": "migrate_kit"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        raw2 = json.loads((Path(MOD_HOME) / "legacy" / "module.json").read_text())
        self.assertTrue(raw2["frameworkKit"]["migrated"])
        self.assertEqual(raw2["frameworkKit"]["adopted"], stamp["adopted"])
        rec2 = (Path(MOD_HOME) / "legacy" / "APP.md").read_text()
        self.assertEqual(rec2.splitlines()[1:], rec.splitlines()[1:], "nothing else in the record moved")
        self.assertEqual(len(adopted()), 1, "the second call is a migration and appends nothing")

    def test_adopting_a_legacy_page_keeps_it_ready_and_gates_only_a_later_mark_ready(self):
        """Codex pin (2026-09-12): adoption never changes status, but a page
        whose index.html predates the token rules is refused by a LATER
        mark_ready, with the failing ids named."""
        (Path(MOD_HOME) / "oldpage").mkdir()
        (Path(MOD_HOME) / "oldpage" / "module.json").write_text(json.dumps(
            {"id": "oldpage", "name": "Old page", "tagline": "a page from before", "kind": "page", "status": "ready", "version": 2}))
        (Path(MOD_HOME) / "oldpage" / "index.html").write_text('<div lang="en"><style>h1{color:#ff0000}</style><h1>Old</h1></div>')
        r = self.client.post(BASE + "/oldpage", json={"action": "migrate_kit"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "ready", "adoption never changes status")
        self.assertIn("not recorded", (Path(MOD_HOME) / "oldpage" / "APP.md").read_text())
        chk = self.client.get(BASE + "/oldpage/checks", headers=HDR).json()["live"]
        self.assertTrue(chk["blocked"], chk)
        self.assertIn("C10", chk["fails"], chk["fails"])
        r = self.client.post(BASE + "/oldpage", json={"action": "mark_ready"}, headers=HDR)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("C10", r.text)

    def test_migrate_kit_refuses_only_when_the_kit_is_absent(self):
        (Path(MOD_HOME) / "nokit").mkdir()
        (Path(MOD_HOME) / "nokit" / "module.json").write_text(json.dumps({"id": "nokit", "name": "No kit", "kind": "chat", "status": "draft", "version": 1}))
        modules_api._KIT_DIR = Path(tempfile.mkdtemp(prefix="no-kit-"))
        r = self.client.post(BASE + "/nokit", json={"action": "migrate_kit"}, headers=HDR)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertFalse((Path(MOD_HOME) / "nokit" / "APP.md").exists())


if __name__ == "__main__":
    unittest.main()
