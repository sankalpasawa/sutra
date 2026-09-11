"""test_modules_api.py -- Org > Modules: the registry routes, the folder
contract, the page sandbox headers, and the Shadow fence.

Every test points SUTRA_MODULES_HOME at its own temp dir BEFORE importing
anything (the agents_api / shadow_home precedent), so nothing here can touch
the operator's real ~/.sutra-ui/modules.
"""
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

MOD_HOME = tempfile.mkdtemp(prefix="modules-test-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
os.environ.setdefault("SUTRA_NATIVE_HOME", tempfile.mkdtemp(prefix="modules-native-"))
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="modules-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="modules-shadow-"))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import modules_api  # noqa: E402
import providers  # noqa: E402
import shadow_protocol  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/modules"


class TestModulesApi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        # a clean folder per test: the folder IS the registry
        for name in os.listdir(MOD_HOME):
            shutil.rmtree(os.path.join(MOD_HOME, name), ignore_errors=True)
        self._settings = providers.SETTINGS_PATH

    def tearDown(self):
        providers.SETTINGS_PATH = self._settings

    # ---- list + seeds ------------------------------------------------------

    def test_01_list_is_seeds_only_on_a_fresh_install(self):
        r = self.client.get(BASE)
        self.assertEqual(r.status_code, 200)
        j = r.json()
        ids = [m["id"] for m in j["modules"]]
        self.assertEqual(ids, ["sys-balance", "sys-help", "sys-settings"])
        self.assertEqual(j["count_user"], 0)
        self.assertEqual(j["home"], os.path.realpath(MOD_HOME))
        # D-M9: the settings seed carries no section list of its own
        self.assertEqual(j["modules"][2]["surface"].get("sections"), "client")

    def test_02_shadow_is_not_a_fleet_seed(self):
        self.assertFalse(any(s["id"] == "sys-shadow" for s in modules_api.SYSTEM_SEEDS))

    # ---- create -------------------------------------------------------------

    def test_03_create_chat_module_writes_the_folder(self):
        r = self.client.post(BASE, json={"name": "Friday review", "kind": "chat",
                                         "tagline": "five questions", "instructions": "go"}, headers=HDR)
        self.assertEqual(r.status_code, 201, r.text)
        row = r.json()
        self.assertEqual(row["id"], "friday-review")
        self.assertEqual(row["status"], "draft")
        self.assertEqual(row["origin"]["created_by"], "app")
        f = Path(MOD_HOME) / "friday-review" / "module.json"
        self.assertTrue(f.is_file())
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        ids = [m["id"] for m in self.client.get(BASE).json()["modules"]]
        self.assertEqual(ids[:3], ["sys-balance", "sys-help", "sys-settings"])
        self.assertIn("friday-review", ids)

    def test_04_collision_is_409(self):
        self.client.post(BASE, json={"name": "Twice"}, headers=HDR)
        r = self.client.post(BASE, json={"name": "Twice"}, headers=HDR)
        self.assertEqual(r.status_code, 409)

    def test_05_reserved_and_bad_ids_are_400(self):
        r = self.client.post(BASE, json={"name": "x", "id": "sys-balance"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE, json={"name": "x", "id": "Bad_Id"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE, json={"name": "", "kind": "chat"}, headers=HDR)
        self.assertEqual(r.status_code, 400)

    def test_06_link_cannot_target_the_terminal_toggle(self):
        r = self.client.post(BASE, json={"name": "t", "kind": "link", "screen": "terminal"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE, json={"name": "Shadow", "kind": "link", "screen": "shadow"}, headers=HDR)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["status"], "ready")     # a link has nothing left to finish

    def test_07_traversal_ids_are_404_before_any_join(self):
        with self.assertRaises(modules_api.ModuleError) as cm:
            modules_api._dir("../x")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(self.client.get(BASE + "/A_B").status_code, 404)

    # ---- actions --------------------------------------------------------------

    def test_08_archive_hides_and_include_archived_shows(self):
        mid = self.client.post(BASE, json={"name": "Gone soon"}, headers=HDR).json()["id"]
        r = self.client.post(BASE + "/" + mid, json={"action": "archive"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "archived")
        ids = [m["id"] for m in self.client.get(BASE).json()["modules"]]
        self.assertNotIn(mid, ids)
        j = self.client.get(BASE + "?include=archived").json()
        self.assertIn(mid, [m["id"] for m in j["modules"]])
        self.assertEqual(j["archived"], 1)
        self.assertTrue((Path(MOD_HOME) / mid / "module.json").is_file())   # never deleted

    def test_09_system_rows_refuse_mutation_and_bad_actions_are_400(self):
        r = self.client.post(BASE + "/sys-balance", json={"action": "archive"}, headers=HDR)
        self.assertEqual(r.status_code, 404)
        mid = self.client.post(BASE, json={"name": "Plain"}, headers=HDR).json()["id"]
        r = self.client.post(BASE + "/" + mid, json={"action": "explode"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE + "/" + mid, json={"action": "set_instructions", "instructions": "new"}, headers=HDR)
        self.assertEqual(r.json()["surface"]["instructions"], "new")
        self.assertEqual(r.json()["version"], 2)

    # ---- page ----------------------------------------------------------------

    def test_10_page_module_without_html_is_a_draft_with_a_warning(self):
        r = self.client.post(BASE, json={"name": "Board", "kind": "page"}, headers=HDR)
        row = r.json()
        self.assertEqual(row["status"], "draft")
        self.assertFalse(row["has_page"])
        self.assertIn("index.html is missing", row["warning"])
        self.assertEqual(self.client.get(BASE + "/board/page").status_code, 404)
        self.assertEqual(self.client.post(BASE + "/board", json={"action": "mark_ready"}, headers=HDR).status_code, 409)

    def test_11_page_is_served_with_the_sandbox_headers_and_tokens(self):
        html = "<h1 style='color:var(--acc)'>Deals</h1><script>document.title='x'</script>"
        r = self.client.post(BASE, json={"name": "Pipeline", "kind": "page", "html": html}, headers=HDR)
        self.assertTrue(r.json()["has_page"])
        p = self.client.get(BASE + "/pipeline/page?theme=light")
        self.assertEqual(p.status_code, 200)
        csp = p.headers.get("content-security-policy", "")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertNotIn("connect-src", csp)
        self.assertEqual(p.headers.get("x-content-type-options"), "nosniff")
        self.assertIn('<style id="sutra-tokens">', p.text)
        self.assertIn('setAttribute("data-theme","light")', p.text)
        self.assertIn("Deals", p.text)
        self.assertEqual(self.client.post(BASE + "/pipeline", json={"action": "mark_ready"}, headers=HDR).json()["status"], "ready")

    # ---- the folder is the module -------------------------------------------

    def test_12_a_folder_written_by_anything_appears_as_from_disk(self):
        d = Path(MOD_HOME) / "shadow"
        d.mkdir()
        (d / "module.json").write_text(json.dumps({
            "schema": 1, "id": "shadow", "name": "Shadow", "kind": "link", "status": "ready",
            "surface": {"screen": "shadow"}, "guard": {}}), encoding="utf-8")
        rows = self.client.get(BASE).json()["modules"]
        hit = [m for m in rows if m["id"] == "shadow"][0]
        self.assertEqual(hit["origin"]["created_by"], "disk")
        self.assertEqual(hit["status"], "ready")
        self.assertIsNone(hit["warning"])
        self.assertIsNotNone(hit["created_at"])

    def test_13_reserved_folder_and_guard_are_reported_not_hidden(self):
        for mid, extra in (("sys-fake", {}), ("guarded", {"guard": {"rule": 1}})):
            d = Path(MOD_HOME) / mid
            d.mkdir()
            (d / "module.json").write_text(json.dumps(dict({"name": mid, "kind": "chat"}, **extra)), encoding="utf-8")
        rows = {m["id"]: m for m in self.client.get(BASE).json()["modules"]}
        self.assertTrue(rows["sys-fake"]["reserved"])
        self.assertEqual(rows["sys-fake"]["warning"], "reserved id, not loaded")
        self.assertEqual(rows["guarded"]["warning"], "guard rules not enforced yet")

    # ---- flag -----------------------------------------------------------------

    def test_14_explicit_false_flag_answers_404_with_the_hint(self):
        tmp = Path(tempfile.mkdtemp(prefix="modules-settings-")) / "settings.json"
        tmp.write_text(json.dumps({"flags": {"modules": False}}), encoding="utf-8")
        providers.SETTINGS_PATH = tmp
        r = self.client.get(BASE)
        self.assertEqual(r.status_code, 404)
        self.assertIn("flags.modules", r.json()["detail"])
        tmp.write_text(json.dumps({"flags": {"modules": True}}), encoding="utf-8")
        self.assertEqual(self.client.get(BASE).status_code, 200)

    # ---- Shadow fence ---------------------------------------------------------

    def test_15_shadow_module_fence_is_parsed_and_invalid_ones_stay_visible(self):
        good = 'Done.\n```module\n{"name": "Friday review", "kind": "chat", "instructions": "go"}\n```\n'
        display, blocks = shadow_protocol.parse_reply(good)
        self.assertEqual(display, "Done.")
        self.assertEqual(blocks["module"]["name"], "Friday review")
        bad = 'Nope.\n```module\n{"name": "x", "kind": "agent"}\n```\n'
        display, blocks = shadow_protocol.parse_reply(bad)
        self.assertNotIn("module", blocks)
        self.assertIn("```module", display)
        row = modules_api.create_module({"name": "From Shadow", "kind": "chat"}, "shadow", "s-1")
        self.assertEqual(row["origin"]["created_by"], "shadow")
        self.assertEqual(row["origin"]["session_id"], "s-1")
        self.assertEqual(row["status"], "draft")


if __name__ == "__main__":
    unittest.main()
