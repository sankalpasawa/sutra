"""Shadow v4 step 16 (C8, ADR-043): the two Shadow apps, instance-local.

modules_api.ensure_shadow_apps runs at boot and does nothing unless the
operator's instance already holds the on-disk `shadow` link module (never a
fleet seed, D-M4). Where it exists: the app is assigned to the live
department named Shadow (else the registry root), and a sibling link app
`shadow-behaves` opens the sheet "What Shadow knows". Idempotent; never
raises.

Same isolation as test_modules_api (temp modules home, temp registry).

Run: sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_v4_apps.py
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

MOD_HOME = tempfile.mkdtemp(prefix="shadow-apps-test-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
NATIVE_HOME = tempfile.mkdtemp(prefix="shadow-apps-native-")
os.environ["SUTRA_NATIVE_HOME"] = NATIVE_HOME
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="shadow-apps-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="shadow-apps-shadow-"))
for _m in ("placement_engine", "org_api", "project_import", "modules_api",
           "modules_events", "modules_pkg", "workspace_api", "app"):
    sys.modules.pop(_m, None)

import modules_api  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import placement_engine as E  # noqa: E402

SHADOW_JSON = {"schema": 1, "id": "shadow", "name": "Shadow",
               "tagline": "your chief of staff · one conversation, everywhere",
               "kind": "link", "status": "ready", "version": 1,
               "origin": {"created_by": "disk", "session_id": None, "at": "2026-09-08T10:30:00Z"},
               "surface": {"screen": "shadow"}, "guard": {},
               "created_at": "2026-09-08T10:30:00Z", "updated_at": "2026-09-08T10:30:00Z"}


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
        for name in os.listdir(MOD_HOME):
            shutil.rmtree(os.path.join(MOD_HOME, name), ignore_errors=True)
        assert os.path.realpath(E.HOME) == os.path.realpath(NATIVE_HOME), (
            "refusing to empty %s" % E.HOME)
        E._ensure_dirs()
        for name in os.listdir(E.DOMAINS):
            os.remove(os.path.join(E.DOMAINS, name))

    def mint(self, parent, name):
        ref, _ = E.mint_domain(parent, name, [name.lower()], "T-local")
        time.sleep(0.002)
        return ref

    def on_disk_shadow(self):
        d = os.path.join(MOD_HOME, "shadow")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "module.json"), "w", encoding="utf-8") as handle:
            json.dump(SHADOW_JSON, handle)

    def record(self, mid):
        with open(os.path.join(MOD_HOME, mid, "module.json"), encoding="utf-8") as handle:
            return json.load(handle)


class TestEnsureShadowApps(Base):

    def test_01_without_the_on_disk_shadow_nothing_happens(self):
        self.mint(None, "Asawa")
        out = modules_api.ensure_shadow_apps()
        self.assertEqual(out, {"present": False, "assigned": None, "created": None})
        self.assertEqual(sorted(os.listdir(MOD_HOME)), [], "no fleet seed, ever")

    def test_02_assigned_to_the_shadow_department_and_the_sibling_created(self):
        root = self.mint(None, "Asawa")
        shadow_ref = self.mint(root, "Shadow")
        self.on_disk_shadow()
        out = modules_api.ensure_shadow_apps()
        self.assertTrue(out["present"])
        self.assertEqual(out["assigned"], shadow_ref)
        self.assertEqual(out["created"], "shadow-behaves")
        self.assertEqual(self.record("shadow")["department"], {"ref": shadow_ref})
        sib = self.record("shadow-behaves")
        self.assertEqual(sib["kind"], "link")
        self.assertEqual(sib["surface"], {"screen": "shadowsettings"})
        self.assertEqual(sib["department"], {"ref": shadow_ref})
        self.assertEqual(sib["status"], "ready", "a link has nothing left to finish")
        self.assertEqual(sib["origin"]["created_by"], "system")
        self.assertTrue(os.path.isfile(os.path.join(MOD_HOME, "shadow-behaves", "APP.md")),
                        "the record the kit writes")

    def test_03_idempotent(self):
        root = self.mint(None, "Asawa")
        self.mint(root, "Shadow")
        self.on_disk_shadow()
        modules_api.ensure_shadow_apps()
        v1 = (self.record("shadow")["version"], self.record("shadow-behaves")["version"])
        out = modules_api.ensure_shadow_apps()
        self.assertEqual(out["assigned"], None)
        self.assertEqual(out["created"], None)
        v2 = (self.record("shadow")["version"], self.record("shadow-behaves")["version"])
        self.assertEqual(v1, v2, "a second boot changes nothing")

    def test_04_no_department_named_shadow_means_the_root(self):
        root = self.mint(None, "Asawa")
        self.mint(root, "Finance")
        self.on_disk_shadow()
        out = modules_api.ensure_shadow_apps()
        self.assertEqual(out["assigned"], root)
        self.assertEqual(self.record("shadow-behaves")["department"], {"ref": root})

    def test_05_empty_registry_creates_the_sibling_unassigned_and_never_raises(self):
        self.on_disk_shadow()
        out = modules_api.ensure_shadow_apps()
        self.assertTrue(out["present"])
        self.assertIsNone(out["assigned"])
        self.assertEqual(out["created"], "shadow-behaves")
        self.assertIsNone(self.record("shadow-behaves")["department"])
        self.assertIsNone(self.record("shadow").get("department"))

    def test_06_an_already_assigned_shadow_is_left_alone(self):
        root = self.mint(None, "Asawa")
        shadow_ref = self.mint(root, "Shadow")
        finance = self.mint(root, "Finance")
        self.on_disk_shadow()
        modules_api.apply_action("shadow", "assign", {"department_ref": finance})
        out = modules_api.ensure_shadow_apps()
        self.assertIsNone(out["assigned"], "the founder's own placement wins")
        self.assertEqual(self.record("shadow")["department"], {"ref": finance})
        self.assertEqual(self.record("shadow-behaves")["department"], {"ref": shadow_ref})


if __name__ == "__main__":
    unittest.main(verbosity=2)
