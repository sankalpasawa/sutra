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
import time
import unittest
from pathlib import Path

MOD_HOME = tempfile.mkdtemp(prefix="modules-test-")
os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
# v1.1 tests MINT departments, so the registry must be a throwaway even when
# the operator's shell exports SUTRA_NATIVE_HOME (setdefault would keep it).
NATIVE_HOME = tempfile.mkdtemp(prefix="modules-native-")
os.environ["SUTRA_NATIVE_HOME"] = NATIVE_HOME
os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="modules-seo-")
os.environ["SEO_AGENT_NO_CLI"] = "1"
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="modules-shadow-"))

# I-T1 (RCA 2026-09-11): in a whole-directory pytest run an earlier module has
# already imported the app with the operator's REAL registry bound (org_api
# exports the real path; placement_engine freezes HOME at import). Setting the
# env above is then a no-op for the cached modules, and the setUp below would
# empty the real ~/.sutra-native/user-kit/domains -- which it did. Drop every
# cached module that captured placement_engine so the imports below re-bind to
# this module's temp home.
import sys  # noqa: E402
for _m in ("placement_engine", "org_api", "project_import", "modules_api",
           "modules_events", "modules_pkg", "workspace_api", "app"):
    sys.modules.pop(_m, None)

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
import modules_api  # noqa: E402
import providers  # noqa: E402
import shadow_protocol  # noqa: E402

import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import placement_engine as E  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/modules"


class TestModulesApi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        # re-assert the home per test: another suite collected in the same
        # pytest process (test_modules_pkg.py) binds its own temp home at import
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
        # a clean folder per test: the folder IS the registry
        for name in os.listdir(MOD_HOME):
            shutil.rmtree(os.path.join(MOD_HOME, name), ignore_errors=True)
        # and a clean department registry (v1.1): the v1 tests run on an EMPTY
        # registry, which is the fleet's first-open state (D-M14)
        # I-T1: never clean a registry that is not THIS module's temp home.
        assert os.path.realpath(E.HOME) == os.path.realpath(NATIVE_HOME), (
            "refusing to empty %s: the engine is not bound to this module's temp "
            "home %s (RCA 2026-09-11)" % (E.HOME, NATIVE_HOME))
        assert app_module.org_api.E is E, "app and test hold different placement_engine modules"
        E._ensure_dirs()
        for name in os.listdir(E.DOMAINS):
            os.remove(os.path.join(E.DOMAINS, name))
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
        # Apps frameworks: the server materializes the page starter, so a fresh
        # page has a page; the missing-html state is a DISK state (someone
        # deleted it) and still reads as a draft with the warning.
        self.assertTrue(row["has_page"])
        os.remove(os.path.join(MOD_HOME, "board", "index.html"))
        row = self.client.get(BASE + "/board", headers=HDR).json()
        self.assertFalse(row["has_page"])
        self.assertIn("index.html is missing", row["warning"])
        self.assertEqual(self.client.get(BASE + "/board/page").status_code, 404)
        self.assertEqual(self.client.post(BASE + "/board", json={"action": "mark_ready"}, headers=HDR).status_code, 409)

    def test_11_page_is_served_with_the_sandbox_headers_and_tokens(self):
        # one root element with lang, inline only (the frameworks' page shape)
        html = "<section lang='en'><h1 style='color:var(--acc)'>Deals</h1><script>document.title='x'</script></section>"
        r = self.client.post(BASE, json={"name": "Pipeline", "kind": "page", "html": html,
                                         "tagline": "the late loans, oldest first, with the owner beside each"}, headers=HDR)
        self.assertTrue(r.json()["has_page"])
        self._answer_record(Path(MOD_HOME) / "pipeline")     # mark_ready is gated on the record (Apps frameworks)
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

    # ---- v1.1: one department per module -----------------------------------
    # Design: 2026-09-08-modules-design.md §v11 (D-M13 assignment, D-M14 empty
    # registry, D-M15 query). Codex folds 2026-09-11: only the ref is persisted
    # (P6); an unknown ref never falls to root (P2); counts are user modules
    # only (P7); `unassigned` is a terminal pseudo-ref (P9); the flat `modules`
    # list is unchanged by the filter (P10).

    def _mint(self, parent, name):
        ref, _ = E.mint_domain(parent, name, [name.lower()], "T-local")
        # Sibling ordinals (D1, D2 …) are ordered by ts_minted_ms; two mints in
        # the same millisecond tie-break by hash and flip between runs (seen
        # 2026-09-11: 1 of 3 runs). A 2 ms gap makes the tree deterministic.
        time.sleep(0.002)
        return ref

    def _tree(self):
        root = self._mint(None, "Asawa")
        exp = self._mint(root, "Experience")
        desk = self._mint(exp, "Desktop app")
        ana = self._mint(root, "Analytics")
        return root, exp, desk, ana

    def _disk(self, mid, **extra):
        d = Path(MOD_HOME) / mid
        d.mkdir()
        (d / "module.json").write_text(json.dumps(dict({"name": mid, "kind": "chat"}, **extra)), encoding="utf-8")

    def test_v11_seeds_sit_at_the_root_and_the_list_names_it(self):
        root, exp, desk, ana = self._tree()
        j = self.client.get(BASE).json()
        self.assertEqual(j["root"]["ref"], root)
        self.assertEqual(j["root"]["path"], "D0")
        self.assertEqual(j["department"]["ref"], root)          # no param = root selected
        for s in j["modules"][:3]:
            self.assertEqual(s["department"]["ref"], root)
        self.assertEqual([m["id"] for m in j["groups"]["system"]], ["sys-balance", "sys-help", "sys-settings"])
        self.assertEqual(j["counts_by_ref"], {})                 # seeds never count (codex P7)

    def test_v11_create_defaults_to_root_and_persists_only_the_ref(self):
        root, exp, desk, ana = self._tree()
        row = self.client.post(BASE, json={"name": "Friday review"}, headers=HDR).json()
        self.assertEqual(row["department"], {"ref": root, "path": "D0", "name": "Asawa", "moved": False})
        raw = json.loads((Path(MOD_HOME) / "friday-review" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["department"], {"ref": root})       # path/name are read-time caches (codex P6)
        row = self.client.post(BASE, json={"name": "Site check", "department": exp}, headers=HDR).json()
        self.assertEqual(row["department"]["name"], "Experience")
        self.assertEqual(row["department"]["path"], "D1")
        r = self.client.post(BASE, json={"name": "Lost", "department": "dref-nope"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE, json={"name": "Lost", "department": "unassigned"}, headers=HDR)
        self.assertEqual(r.status_code, 400)                     # assignment is a department, always

    def test_v11_disk_modules_without_a_live_department_are_unassigned(self):
        root, exp, desk, ana = self._tree()
        self._disk("scratch")                                    # no department at all
        self._disk("stale", department={"ref": "dref-gone", "path": "D9", "name": "Gone"})
        rows = {m["id"]: m for m in self.client.get(BASE).json()["modules"]}
        self.assertIsNone(rows["scratch"]["department"])
        self.assertIsNone(rows["stale"]["department"])           # unknown ref is NOT root (codex P2)
        self.assertIsNone(rows["scratch"]["warning"])            # unassigned is a state, not a fault
        j = self.client.get(BASE).json()
        self.assertEqual(sorted(m["id"] for m in j["groups"]["unassigned"]), ["scratch", "stale"])
        self.assertEqual(j["unassigned_count"], 2)

    def test_v11_a_retired_department_resolves_to_its_successor_at_read(self):
        root, exp, desk, ana = self._tree()
        mid = self.client.post(BASE, json={"name": "Weekly", "department": desk}, headers=HDR).json()["id"]
        res = E.restructure("merge", desk, target=ana)
        self.assertTrue(res.get("ok"), res)
        row = self.client.get(BASE + "/" + mid).json()
        self.assertEqual(row["department"]["ref"], ana)
        self.assertEqual(row["department"]["name"], "Analytics")
        self.assertTrue(row["department"]["moved"])
        raw = json.loads((Path(MOD_HOME) / mid / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["department"]["ref"], desk)         # disk keeps the original; read resolves
        j = self.client.get(BASE + "?department=" + ana).json()
        self.assertEqual([m["id"] for m in j["groups"]["here"]], [mid])

    def test_v11_query_groups_here_below_system_unassigned_and_counts(self):
        root, exp, desk, ana = self._tree()
        m_desk = self.client.post(BASE, json={"name": "Desk one", "department": desk}, headers=HDR).json()["id"]
        m_exp = self.client.post(BASE, json={"name": "Exp one", "department": exp}, headers=HDR).json()["id"]
        m_ana = self.client.post(BASE, json={"name": "Ana one", "department": ana}, headers=HDR).json()["id"]
        self._disk("scratch")
        j = self.client.get(BASE + "?department=" + exp).json()
        self.assertEqual([m["id"] for m in j["groups"]["here"]], [m_exp])
        self.assertEqual([(g["department"]["ref"], [m["id"] for m in g["modules"]]) for g in j["groups"]["below"]],
                         [(desk, [m_desk])])
        self.assertEqual(j["groups"]["system"], [])              # root only
        self.assertEqual(j["groups"]["unassigned"], [])          # root only
        self.assertEqual(j["department"]["path"], "D1")
        self.assertEqual(j["counts_by_ref"], {root: 3, exp: 2, desk: 1, ana: 1})
        self.assertEqual(j["unassigned_count"], 1)
        ids = [m["id"] for m in j["modules"]]
        self.assertEqual(ids[:3], ["sys-balance", "sys-help", "sys-settings"])
        self.assertEqual(sorted(ids[3:]), sorted([m_desk, m_exp, m_ana, "scratch"]))   # flat list unfiltered (P10)
        j = self.client.get(BASE + "?department=" + exp + "&subtree=0").json()
        self.assertEqual(j["groups"]["below"], [])
        j = self.client.get(BASE + "?department=unassigned").json()
        self.assertEqual([m["id"] for m in j["groups"]["unassigned"]], ["scratch"])
        self.assertEqual(j["groups"]["here"], [])
        self.assertEqual(j["groups"]["below"], [])
        self.assertEqual(j["department"], {"ref": "unassigned", "path": "", "name": "Unassigned", "description": ""})
        self.assertEqual(self.client.get(BASE + "?department=dref-nope").status_code, 404)
        j = self.client.get(BASE).json()                         # root: everything below, grouped
        self.assertEqual(j["groups"]["here"], [])
        self.assertEqual([g["department"]["ref"] for g in j["groups"]["below"]], [exp, desk, ana])
        self.assertEqual(len(j["groups"]["system"]), 3)
        self.assertEqual([m["id"] for m in j["groups"]["unassigned"]], ["scratch"])

    def test_v11_assign_moves_a_module_and_validates_the_target(self):
        root, exp, desk, ana = self._tree()
        self.assertIn("assign", modules_api.ACTIONS)
        mid = self.client.post(BASE, json={"name": "Mover"}, headers=HDR).json()["id"]
        r = self.client.post(BASE + "/" + mid, json={"action": "assign", "department_ref": ana}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["department"]["ref"], ana)
        self.assertEqual(r.json()["version"], 2)
        r = self.client.post(BASE + "/" + mid, json={"action": "assign", "department_ref": "dref-nope"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE + "/" + mid, json={"action": "assign"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(BASE + "/sys-balance", json={"action": "assign", "department_ref": ana}, headers=HDR)
        self.assertEqual(r.status_code, 404)

    def test_v11_an_empty_registry_is_unassigned_only_and_mints_nothing(self):
        j = self.client.get(BASE).json()
        self.assertIsNone(j["root"])
        self.assertIsNone(j["department"])
        row = self.client.post(BASE, json={"name": "First"}, headers=HDR).json()
        self.assertIsNone(row["department"])
        j = self.client.get(BASE).json()
        self.assertEqual([m["id"] for m in j["groups"]["unassigned"]], ["first"])
        self.assertEqual(len(j["groups"]["system"]), 3)
        self.assertEqual(j["counts_by_ref"], {})
        self.assertEqual(E.load_domains(), {})                   # D-M14: Modules never mints a domain
        r = self.client.post(BASE, json={"name": "Second", "department": "dref-nope"}, headers=HDR)
        self.assertEqual(r.status_code, 400)

    def test_v11_live_destination_is_public_and_unknown_refs_stay_unknown(self):
        root, exp, desk, ana = self._tree()
        domains = E.load_domains()
        self.assertEqual(E.live_destination("dref-nope", domains, root), (None, "unknown"))
        self.assertEqual(E.live_destination(desk, domains, root), (desk, "home"))
        E.restructure("merge", desk, target=ana)
        self.assertEqual(E.live_destination(desk, E.load_domains(), root), (ana, "successor"))

    def test_v11_shadow_fence_department_is_a_ref_only(self):
        root, exp, desk, ana = self._tree()
        row = modules_api.create_module({"name": "Placed", "kind": "chat", "department": desk}, "shadow", "s-2")
        self.assertEqual(row["department"]["ref"], desk)
        with self.assertRaises(modules_api.ModuleError):
            modules_api.create_module({"name": "Named", "kind": "chat", "department": "Desktop app"}, "shadow", "s-2")

    # ---- v1.2: manifest schema, migration, building row, goldens ------------
    # Program steps 46 (migration) and 48 (golden). schemas/MIGRATIONS.md M-1..M-7.
    # The three test_v12_* migration cases FAIL until program step 55 lands.

    FIXTURES = Path(__file__).resolve().parent / "schemas" / "fixtures"

    def _fixture(self, name, mid):
        d = Path(MOD_HOME) / mid
        d.mkdir()
        shutil.copy(self.FIXTURES / name, d / "module.json")
        return d / "module.json"

    def test_v12_schema1_fixtures_read_as_schema2_rows(self):
        # M-1: read-time normalization only; passes already (documents the floor)
        self._fixture("schema1-minimal.json", "old-one")
        self._fixture("schema1-unknown-stale.json", "stale-dept")
        rows = {m["id"]: m for m in self.client.get(BASE).json()["modules"]}
        self.assertIsNone(rows["old-one"]["department"])
        self.assertIsNone(rows["old-one"]["publish"])
        self.assertIsNone(rows["old-one"]["warning"])
        self.assertIsNone(rows["stale-dept"]["department"])       # stale ref -> Unassigned, never root

    def test_v12_write_back_bumps_schema_and_preserves_unknown_fields(self):
        # M-2 + M-4 (fails until step 55): the next mutation patches the RAW file
        f = self._fixture("schema1-unknown-stale.json", "stale-dept")
        r = self.client.post(BASE + "/stale-dept", json={"action": "rename", "name": "Renamed"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        raw = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(raw["schema"], 2)
        self.assertEqual(raw["colour"], "sepia")                  # unknown field survives the write-back
        self.assertEqual(raw["department"]["ref"], "dref-0000000000000000")   # M-5: never rewritten by a read or a rename

    def test_v12_create_writes_schema2(self):
        # M-7 (fails until step 55): new apps are schema 2 so export never needs a migration
        root, exp, desk, ana = self._tree()
        mid = self.client.post(BASE, json={"name": "Fresh"}, headers=HDR).json()["id"]
        raw = json.loads((Path(MOD_HOME) / mid / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["schema"], 2)

    def test_v12_unparsable_manifest_is_a_building_row_not_a_missing_app(self):
        # M-6 / D-M21 (fails until step 54): folder exists, manifest invalid -> row with a warning
        d = Path(MOD_HOME) / "half-written"
        d.mkdir()
        (d / "module.json").write_text('{"schema": 1, "id": "half-written", "name": "Half', encoding="utf-8")
        rows = {m["id"]: m for m in self.client.get(BASE).json()["modules"]}
        self.assertIn("half-written", rows)
        self.assertIn("building", (rows["half-written"]["warning"] or "").lower())

    def test_v13_touch_ignores_the_record_dotfiles_and_holding_inert(self):
        # Apps frameworks (design v1 R1-P2): APP.md, dot-prefixed names and a
        # top-level holding/ are never an edit of the app -- no version bump,
        # no app.edited row. A real file change still counts.
        r = self.client.post(BASE, json={"name": "Inert probe", "kind": "chat", "instructions": "hi"}, headers=HDR)
        self.assertEqual(r.status_code, 201, r.text)
        mid = r.json()["id"]
        folder = Path(MOD_HOME) / mid
        events = Path(MOD_HOME) / ".events.jsonl"
        before = events.read_text().count('"%s"' % mid) if events.exists() else 0
        time.sleep(0.02)
        (folder / "APP.md").write_text("frameworkKit: {}\n# record\n", encoding="utf-8")
        (folder / ".scratch").write_text("x", encoding="utf-8")
        (folder / "holding").mkdir()
        (folder / "holding" / "notes.txt").write_text("y", encoding="utf-8")
        r = self.client.post(BASE + "/" + mid + "/touch", json={"mode": "edit", "session_id": "s-1"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["changed"])
        self.assertEqual(r.json()["app"]["version"], 1)
        after = events.read_text().count('"%s"' % mid) if events.exists() else 0
        self.assertEqual(after, before, "an inert file appended an event")
        time.sleep(0.02)
        (folder / "data-policy.json").write_text('{"panel_apis": []}', encoding="utf-8")
        r = self.client.post(BASE + "/" + mid + "/touch", json={"mode": "edit"}, headers=HDR)
        self.assertTrue(r.json()["changed"])
        self.assertEqual(r.json()["app"]["version"], 2)

    # ---- Apps frameworks (design v1, program Phase D) -------------------------

    def _kit(self):
        return json.loads((Path(modules_api._KIT_DIR) / "kit.json").read_text())

    def _answer_record(self, folder):
        """Fill every empty answer cell of the folder's own APP.md (stamp line untouched)."""
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tests" / "fixtures" / "kit"))
        import make_fixtures
        rp = Path(folder) / "APP.md"
        out = []
        for line in rp.read_text().splitlines():
            if line.startswith("|") and not line.startswith("|---"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) == 3 and cells[0] in make_fixtures.ANSWERS and not cells[2]:
                    line = "| %s | %s | %s |" % (cells[0], cells[1], make_fixtures.ANSWERS[cells[0]])
            out.append(line)
        rp.write_text("\n".join(out) + "\n")

    def test_v13_frameworks_endpoint_serves_the_installed_kit(self):
        r = self.client.get(BASE + "/frameworks", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        fw = r.json()
        kit = self._kit()
        self.assertEqual(fw["version"], kit["version"])
        self.assertEqual(fw["digest"], kit["digest_short"])
        self.assertEqual(sorted(fw["kinds"]), ["chat", "link", "page"])
        self.assertTrue(fw["check"].endswith("apps-frameworks/check.py"))
        self.assertEqual(fw["screens"], list(modules_api.SCREEN_IDS))
        self.assertIn("ink", fw["tokens"])
        self.assertIn("acc", fw["tokens"])
        self.assertEqual(sorted(fw["must_fix"], key=lambda s: int(s[1:]))[:3], ["C1", "C2", "C3"])

    def test_v13_create_materializes_starters_and_the_stamp_last(self):
        kit = self._kit()
        for kind, extra in (("page", {}), ("chat", {"instructions": "hi."}), ("link", {"screen": "balance"})):
            r = self.client.post(BASE, json=dict({"name": "Starter %s" % kind, "tagline": "one line", "kind": kind}, **extra), headers=HDR)
            self.assertEqual(r.status_code, 201, r.text)
            row = r.json()
            folder = Path(MOD_HOME) / row["id"]
            raw = json.loads((folder / "module.json").read_text())
            stamp = raw["frameworkKit"]
            self.assertEqual(stamp["version"], kit["version"])
            self.assertEqual(stamp["digest"], kit["digest_short"])
            self.assertEqual(stamp["kind"], kind)
            self.assertEqual(row["frameworkKit"], stamp, "the normalized row mirrors the stamp")
            rec = (folder / "APP.md").read_text()
            first = rec.splitlines()[0]
            self.assertTrue(first.startswith("frameworkKit: "), first)
            self.assertEqual(json.loads(first[len("frameworkKit: "):]), stamp, "APP.md line 1 equals the manifest mirror")
            self.assertIn("# Starter %s" % kind, rec)
            self.assertIn("| S3 |", rec)
            if kind == "page":
                starter = (Path(modules_api._KIT_DIR) / "templates" / "page" / "index.html").read_text()
                self.assertEqual((folder / "index.html").read_text(), starter, "the page starter is the template byte for byte")
            else:
                self.assertFalse((folder / "index.html").exists())
            if kind == "link":
                self.assertIn("| B5 | Which screen should this open? | balance |", rec)
        # a legacy folder (no stamp) still reads, with frameworkKit null
        (Path(MOD_HOME) / "legacy").mkdir()
        (Path(MOD_HOME) / "legacy" / "module.json").write_text(json.dumps({"id": "legacy", "name": "Legacy", "kind": "chat", "status": "draft", "version": 1}))
        self.assertIsNone(self.client.get(BASE + "/legacy", headers=HDR).json()["frameworkKit"])

    def test_v13_mark_ready_refuses_with_the_failing_check_ids_then_passes(self):
        r = self.client.post(BASE, json={"name": "Loan book by bucket", "tagline": "placeholder", "kind": "page"}, headers=HDR)
        mid = r.json()["id"]
        folder = Path(MOD_HOME) / mid
        r = self.client.post(BASE + "/" + mid, json={"action": "mark_ready"}, headers=HDR)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("C1", r.json()["detail"], "the unanswered record is named")
        # answer the record and set the one-line tagline the record carries
        self._answer_record(folder)
        raw = json.loads((folder / "module.json").read_text())
        raw["tagline"] = "the late loans, oldest first, with the owner beside each"
        (folder / "module.json").write_text(json.dumps(raw))
        r = self.client.post(BASE + "/" + mid, json={"action": "mark_ready"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "ready")
        # a legacy app (no stamp) is never gated
        (Path(MOD_HOME) / "old-one").mkdir()
        (Path(MOD_HOME) / "old-one" / "module.json").write_text(json.dumps({"id": "old-one", "name": "Old", "kind": "chat", "status": "draft", "version": 1, "surface": {"instructions": "x"}}))
        r = self.client.post(BASE + "/old-one", json={"action": "mark_ready"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)

    def test_v13_checks_readonly_endpoint_returns_live_and_recorded(self):
        r = self.client.post(BASE, json={"name": "Checks probe", "tagline": "one line", "kind": "chat", "instructions": "Say hi."}, headers=HDR)
        mid = r.json()["id"]
        folder = Path(MOD_HOME) / mid
        events = Path(MOD_HOME) / ".events.jsonl"
        before_ev = events.read_text() if events.exists() else ""
        before_rec = (folder / "APP.md").read_text()
        mtime = (folder / "APP.md").stat().st_mtime_ns
        r = self.client.get(BASE + "/" + mid + "/checks", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(j["kind"], "chat")
        self.assertIn("C1", j["live"]["fails"], "an unanswered record fails C1 live")
        self.assertTrue(j["live"]["blocked"])
        self.assertEqual(j["recorded"], {"ran": False}, "no check has written the block yet")
        self.assertEqual((folder / "APP.md").read_text(), before_rec, "GET writes nothing")
        self.assertEqual((folder / "APP.md").stat().st_mtime_ns, mtime)
        self.assertEqual(events.read_text() if events.exists() else "", before_ev, "GET appends no event")
        self.assertEqual(self.client.get(BASE + "/sys-balance/checks", headers=HDR).status_code, 404)

    def test_v12_two_hundred_apps_list_under_300ms(self):
        # Program step 85: the list is one directory read + one registry read per request
        root, exp, desk, ana = self._tree()
        for i in range(200):
            self._disk("app-%03d" % i, department={"ref": desk if i % 2 else exp})
        t0 = time.perf_counter()
        j = self.client.get(BASE).json()
        dt = time.perf_counter() - t0
        self.assertEqual(j["count_user"], 200)
        self.assertLess(dt, 0.3, "root listing of 200 apps took %.3fs" % dt)

    def test_v12_golden_grouped_response_for_a_department(self):
        # Step 48: the grouped answer for one department, refs normalised to names.
        root, exp, desk, ana = self._tree()
        names = {root: "Asawa", exp: "Experience", desk: "Desktop app", ana: "Analytics"}
        for name, dep in (("Desk one", desk), ("Exp one", exp), ("Ana one", ana)):
            self.client.post(BASE, json={"name": name, "department": dep}, headers=HDR)
        j = self.client.get(BASE + "?department=" + exp).json()

        def norm(o):
            # refs -> names, timestamps stripped, and every list of rows sorted
            # so mtime / construction order can never flake the golden (codex R2 P3)
            if isinstance(o, dict):
                # the frameworks stamp carries the kit digest, which moves with
                # every kit edit: its PRESENCE is golden, its value is not
                return {k: ("<stamp>" if k == "frameworkKit" and isinstance(v, dict) else norm(v))
                        for k, v in o.items() if k not in ("created_at", "updated_at", "home", "at", "session_id")}
            if isinstance(o, list):
                items = [norm(x) for x in o]
                if items and all(isinstance(x, dict) for x in items):
                    key = (lambda x: x.get("id") or (x.get("department") or {}).get("name") or "")
                    items = sorted(items, key=key)
                return items
            if isinstance(o, str) and o in names:
                return "<" + names[o] + ">"
            return o
        got = norm(j)
        got["counts_by_ref"] = {"<" + names[k] + ">": v for k, v in j["counts_by_ref"].items()}
        # Publish program: the payload says whether publishing is on (a settings read) and which registry
        # is the default (a shipped file); its PRESENCE is golden, its values are the machine's
        self.assertEqual(set(j["publish"]), {"on", "registry"})
        got["publish"] = "<publish>"
        want = json.loads((self.FIXTURES / "golden-grouped-experience.json").read_text(encoding="utf-8"))
        self.assertEqual(got, want)



# ---- Publish program P3 + P4 (2026-09-12): publish as an approved proposal; registry verdicts, refresh, update ----

import base64  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import tarfile  # noqa: E402

import proposals  # noqa: E402
import modules_registry  # noqa: E402
import modules_sign  # noqa: E402
import providers  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures", "kit"))
import make_fixtures  # noqa: E402


@unittest.skipUnless(modules_sign.available(), "cryptography is not importable here (the DMG carries it)")
class TestPublishProgram(unittest.TestCase):
    """P3: Publish... in the header only while the flag is on; the approval of an
    app.publish proposal exports, versions, signs and stages; refusals leave the
    manifest untouched. P4: GET registry is a read, POST refresh is the write,
    the Update path installs the newer version verified."""

    REG = "https://registry.invalid/apps/registry.json"

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        cls.kid, cls.priv, cls.pub = modules_sign.generate()
        cls.publisher = {"publisher_id": "acme", "key_id": cls.kid, "pubkey": modules_sign.pub_b64(cls.pub), "added_at": "2026-09-12T15:00:00Z"}

    def setUp(self):
        os.environ["SUTRA_MODULES_HOME"] = MOD_HOME
        for name in os.listdir(MOD_HOME):
            shutil.rmtree(os.path.join(MOD_HOME, name), ignore_errors=True)
        for var, prefix in (("SUTRA_UI_PROPOSALS", "pub-props-"), ("SUTRA_UI_KEYS", "pub-keys-"), ("SUTRA_UI_PUBLISH", "pub-stage-"),
                            ("SUTRA_UI_REGISTRY_CACHE", "pub-cache-")):
            os.environ[var] = tempfile.mkdtemp(prefix=prefix)
        os.environ["SUTRA_UI_PINNED"] = os.path.join(tempfile.mkdtemp(prefix="pub-pins-"), "pinned.json")
        self._settings = providers.SETTINGS_PATH
        self._flag(True)
        self._fetch = modules_registry.fetch_bytes
        self.served = {}
        modules_registry.fetch_bytes = lambda url, cap, timeout=10.0: self._serve(url)

    def tearDown(self):
        providers.SETTINGS_PATH = self._settings
        modules_registry.fetch_bytes = self._fetch

    def _flag(self, on):
        tmp = Path(tempfile.mkdtemp(prefix="pub-settings-")) / "settings.json"
        tmp.write_text(json.dumps({"flags": {"apps_publish": bool(on)}}), encoding="utf-8")
        providers.SETTINGS_PATH = tmp

    def _serve(self, url):
        if url not in self.served:
            raise OSError("no such url %s" % url)
        return self.served[url]

    def _ready_app(self, mid="loan-book"):
        folder = make_fixtures.make_pass("page", os.path.join(MOD_HOME, mid))
        raw = json.loads(Path(folder, "module.json").read_text(encoding="utf-8"))
        raw["status"] = "ready"
        Path(folder, "module.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
        return folder

    def _events(self, event):
        p = Path(MOD_HOME) / ".events.jsonl"
        return [json.loads(l) for l in (p.read_text(encoding="utf-8") if p.exists() else "").splitlines() if l.strip() and '"%s"' % event in l]

    # ---- P3 ---------------------------------------------------------------------

    def test_p3_list_payload_says_whether_publishing_is_on(self):
        j = self.client.get(BASE, headers=HDR).json()
        self.assertTrue(j["publish"]["on"])
        self.assertEqual(j["publish"]["registry"], modules_registry.default_registry()["url"])
        self._flag(False)
        self.assertFalse(self.client.get(BASE, headers=HDR).json()["publish"]["on"])

    def test_p3_approving_the_proposal_exports_versions_signs_and_stages(self):
        folder = self._ready_app()
        p = proposals.create("app.publish", {"id": "loan-book", "bump": "patch"}, "publish app loan-book", session_id="s-pub")
        r = self.client.post("/api/proposals/%s/decide" % p["id"], json={"approve": True}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        rec = r.json()
        self.assertEqual(rec["status"], "approved", rec)
        res = rec["result"]
        self.assertEqual(res["version"], "1.0.0")
        self.assertTrue(os.path.isfile(res["entry_path"]) and os.path.isfile(res["artifact_path"]))
        entry = json.load(open(res["entry_path"], encoding="utf-8"))
        ident = modules_sign.publisher()
        pins = {ident["key_id"]: {"pubkey": modules_sign.pub_from_b64(ident["pubkey"]), "publisher_id": ident["publisher_id"]}}
        ok, why = modules_sign.verify_entry(entry, pins)
        self.assertTrue(ok, why)
        self.assertEqual(entry["sha256"], hashlib.sha256(Path(res["artifact_path"]).read_bytes()).hexdigest())
        self.assertEqual(entry["kinds"], ["page"])
        self.assertIn("modules_registry.py add", res["registry_step"])
        raw = json.loads(Path(folder, "module.json").read_text(encoding="utf-8"))
        self.assertEqual((raw["publish"]["state"], raw["publish"]["version"]), ("published", "1.0.0"))
        self.assertEqual(raw["publish"]["registry"], modules_registry.default_registry()["url"])
        with tarfile.open(fileobj=io.BytesIO(Path(res["artifact_path"]).read_bytes())) as t:
            inner = json.load(t.extractfile("loan-book/module.json"))
        self.assertEqual(inner["publish"]["version"], "1.0.0", "the tarball carries the signed version (R-5)")
        ev = self._events("app.published")[-1]
        self.assertEqual((ev["app_id"], ev["publish_version"], ev["actor"]), ("loan-book", "1.0.0", "proposal:" + p["id"]))
        # C8 reads the published block as the desktop's, not the chat's (kit 1.1.1)
        chk = self.client.get(BASE + "/loan-book/checks", headers=HDR).json()["live"]
        self.assertNotIn("C8", chk["fails"], chk)
        # a second approval bumps
        p2 = proposals.create("app.publish", {"id": "loan-book", "bump": "minor"}, "publish again")
        rec = self.client.post("/api/proposals/%s/decide" % p2["id"], json={"approve": True}, headers=HDR).json()
        self.assertEqual(rec["result"]["version"], "1.1.0", rec)

    def test_p3_refusals_leave_the_manifest_untouched(self):
        folder = self._ready_app()
        raw = json.loads(Path(folder, "module.json").read_text(encoding="utf-8"))
        raw["status"] = "draft"
        Path(folder, "module.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
        with self.assertRaises(modules_api.ModuleError) as cm:
            modules_api.publish_app("loan-book", "patch")
        self.assertEqual(cm.exception.status, 409)
        raw["status"] = "ready"
        rec = Path(folder, "APP.md").read_text(encoding="utf-8").replace(make_fixtures.ANSWERS["P1"], "")
        Path(folder, "APP.md").write_text(rec, encoding="utf-8")                # C1 fails: an unanswered required row
        Path(folder, "module.json").write_text(json.dumps(raw, indent=1), encoding="utf-8")
        with self.assertRaises(modules_api.ModuleError) as cm:
            modules_api.publish_app("loan-book", "patch")
        self.assertIn("C1", str(cm.exception))
        after = json.loads(Path(folder, "module.json").read_text(encoding="utf-8"))
        self.assertIsNone(after.get("publish"), "a refused publish writes no version")
        self._flag(False)
        with self.assertRaises(modules_api.ModuleError) as cm:
            modules_api.publish_app("loan-book", "patch")
        self.assertEqual(cm.exception.status, 404)
        p = proposals.create("app.publish", {"id": "loan-book", "bump": "patch"}, "publish while off")
        rec = self.client.post("/api/proposals/%s/decide" % p["id"], json={"approve": True}, headers=HDR).json()
        self.assertEqual(rec["status"], "failed", "an approval that cannot apply is recorded, never retried")

    # ---- P4 ---------------------------------------------------------------------

    def _tar(self, version, mid="imported-one"):
        m = {"schema": 2, "id": mid, "name": "Imported one", "kind": "page", "status": "ready", "version": 1,
             "surface": {"entry": "index.html"}, "guard": {}, "publish": {"version": version}}
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for arc, data in ((mid + "/module.json", json.dumps(m).encode()), (mid + "/index.html", ("<h1>v%s</h1>" % version).encode())):
                ti = tarfile.TarInfo(arc)
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
        return buf.getvalue()

    def _entry(self, blob, version, mid="imported-one", published_at="2026-09-12T15:00:00Z", rng=None):
        e = {"id": mid, "name": "Imported one", "version": version, "manifest_schema": 2,
             "artifact_url": "https://registry.invalid/apps/artifacts/%s-%s.tgz" % (mid, version),
             "sha256": hashlib.sha256(blob).hexdigest(), "published_at": published_at,
             "sutra_version_range": rng or {"min": "2.263.0", "max": None}, "kinds": ["page"], "publisher_id": "acme"}
        self.served[e["artifact_url"]] = blob
        return modules_sign.sign_entry(e, self.priv)

    def _publish(self, entries):
        idx = {"registry_schema": 1, "name": "Acme", "updated_at": "2026-09-12T15:00:00Z", "apps": entries, "publishers": [self.publisher]}
        self.served[self.REG] = json.dumps(idx).encode()

    def test_p4_registry_read_never_writes_and_refresh_writes_once(self):
        self._publish([self._entry(self._tar("1.0.0"), "1.0.0")])
        r = self.client.post(BASE + "/install", json={"registry": self.REG, "id": "imported-one"}, headers=HDR)
        self.assertEqual(r.status_code, 201, r.text)
        view = self.client.get(BASE + "/registry", headers=HDR).json()
        mine = [a for a in view["apps"] if a["id"] == "imported-one"]
        self.assertEqual((mine[0]["verdict"], mine[0]["installed_version"]), ("current", "1.0.0"), view)
        acme = next(row for row in view["registries"] if row["url"] == self.REG)
        self.assertEqual((acme["ok"], acme["pin_source"], acme["publishers"]), (True, "pinned", 1))
        # a newer entry appears; the read says so but writes nothing
        self._publish([self._entry(self._tar("1.1.0"), "1.1.0", published_at="2026-09-13T09:00:00Z")])
        view = self.client.get(BASE + "/registry?refresh=1", headers=HDR).json()
        self.assertEqual([a["verdict"] for a in view["apps"] if a["id"] == "imported-one"], ["update_available"])
        raw = json.loads((Path(MOD_HOME) / "imported-one" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["publish"]["state"], "imported", "a read enters no state")
        self.assertEqual(self._events("app.registry_refreshed"), [], "a read emits nothing")
        # the write
        r = self.client.post(BASE + "/registry/refresh", headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["refreshed"]["updates"], 1)
        raw = json.loads((Path(MOD_HOME) / "imported-one" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["publish"]["state"], "update_available")
        self.assertEqual(raw["version"], 1, "write-back only: no version bump")
        evs = self._events("app.registry_refreshed")
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["app_id"], evs[0]["updates"], evs[0]["checked"]), ("*", 1, 1))
        row = next(m for m in self.client.get(BASE, headers=HDR).json()["modules"] if m["id"] == "imported-one")
        self.assertEqual(row["publish"]["state"], "update_available", "the panel row carries the state")
        # the Update path: a verified install of the newer version, then the refresh reads current again
        r = self.client.post(BASE + "/install", json={"registry": self.REG, "id": "imported-one", "replace": True}, headers=HDR)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["version"], "1.1.0")
        r = self.client.post(BASE + "/registry/refresh", headers=HDR)
        self.assertEqual(r.json()["refreshed"]["updates"], 0)
        raw = json.loads((Path(MOD_HOME) / "imported-one" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual((raw["publish"]["state"], raw["publish"]["version"]), ("imported", "1.1.0"))
        # an incompatible entry
        self._publish([self._entry(self._tar("2.0.0"), "2.0.0", rng={"min": "9.0.0", "max": None})])
        r = self.client.post(BASE + "/registry/refresh", headers=HDR)
        self.assertEqual(r.json()["refreshed"]["incompatible"], 1)
        raw = json.loads((Path(MOD_HOME) / "imported-one" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["publish"]["state"], "incompatible")

    def test_p4_registry_routes_are_unreachable_while_off(self):
        self._flag(False)
        for r in (self.client.get(BASE + "/registry", headers=HDR), self.client.post(BASE + "/registry/refresh", headers=HDR)):
            self.assertEqual(r.status_code, 404)
            self.assertIn("apps_publish", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
