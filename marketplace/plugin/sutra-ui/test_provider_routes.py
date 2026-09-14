"""test_provider_routes.py -- the HTTP surface of the provider cleanup.

Four things reach a client, and this file is about the wire rather than the
readers underneath (those have their own files: test_model_catalog,
test_access_options, test_provider_settings, test_usage_all,
test_provider_tools):

  GET  /api/settings                        gains five fields and loses none
  POST /api/settings                        accepts `access` and
                                            `provider_settings`
  GET  /api/usage/all                       one row per provider
  GET  /api/providers/tools                 one row per CLI
  POST /api/providers/tools/{id}/update     gated, and refuses loudly

THE SETTINGS FILE IS REDIRECTED BEFORE app IS IMPORTED. providers.SETTINGS_PATH
is bound at import time, so setting the variable afterwards would be too late
and the first write would land in ~/.sutra-ui.

Run: python -m pytest test_provider_routes.py -q
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_TMP = tempfile.mkdtemp(prefix="sutra-routes-test-")
os.environ["SUTRA_UI_SETTINGS"] = os.path.join(_TMP, "settings.json")
os.environ.setdefault("SUTRA_NATIVE_HOME", os.path.join(_TMP, "native"))
os.environ.pop("SUTRA_UI_ALLOW_UNSAFE_PERM_MODES", None)

from fastapi.testclient import TestClient   # noqa: E402

import app         # noqa: E402
import providers   # noqa: E402
import usage       # noqa: E402

#: TestClient defaults to http://testserver, which app.py's host guard refuses
#: (400 "Invalid host header"). Loopback is what a real panel sends.
BASE = "http://127.0.0.1:8765"


class Routes(unittest.TestCase):
    """`app` IS RESOLVED PER TEST, not captured at import.

    test_perm_mode_default.py deletes `app` and `org_api` from sys.modules and
    re-imports them to re-evaluate a module-level constant. In a whole-directory
    run that can happen between this module being imported and its tests being
    run, after which a captured `app` is a DIFFERENT object from the one
    org_api's own `import app` now resolves -- with a different PANEL_TOKEN, so
    every gated POST here answered 403, and a different router, so a route this
    file added answered 404. Both failures pointed at this change and neither
    was about it. Reading sys.modules at test time makes the order irrelevant.
    """

    @property
    def live_app(self):
        return sys.modules.get("app", app)

    @property
    def client(self):
        return TestClient(self.live_app.app, base_url=BASE)

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sutra-routes-case-")
        self._old = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.dir) / "settings.json"
        usage._reset_all_for_tests()
        self.headers = {"x-sutra-panel": self.live_app.PANEL_TOKEN}

    def tearDown(self):
        providers.SETTINGS_PATH = self._old
        shutil.rmtree(self.dir, ignore_errors=True)

    def get(self, path, **kw):
        return self.client.get(path, **kw)

    def post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers=self.headers)

    def raw(self):
        try:
            return json.loads(providers.SETTINGS_PATH.read_text())
        except OSError:
            return {}


class SettingsGet(Routes):

    def payload(self):
        r = self.get("/api/settings")
        self.assertEqual(r.status_code, 200, r.text[:400])
        return r.json()

    def test_the_five_new_fields_are_published(self):
        d = self.payload()
        for key in ("model_catalog_by_provider", "access_options",
                    "access_by_provider", "access_native",
                    "provider_settings_schema", "provider_settings",
                    "permission_modes_advanced"):
            self.assertIn(key, d)

    def test_every_old_field_is_still_published(self):
        """The whole backwards-compatibility promise, on the wire."""
        d = self.payload()
        for key in ("settings", "permission_modes", "unsafe_modes_allowed",
                    "unsafe_modes_env", "models_by_provider",
                    "turn_options_by_provider", "permission_modes_by_provider",
                    "providers", "claude_account"):
            self.assertIn(key, d)

    def test_models_by_provider_is_still_the_flat_list(self):
        d = self.payload()
        self.assertEqual([m["id"] for m in d["models_by_provider"]["claude"]],
                         ["", "fable", "opus", "sonnet", "haiku"])

    def test_the_catalogue_rides_beside_it_not_instead_of_it(self):
        d = self.payload()
        self.assertEqual(
            [m["id"] for m in d["model_catalog_by_provider"]["claude"]["models"]],
            ["", "best", "opus", "sonnet", "haiku"])

    def test_the_six_native_modes_are_still_offered_with_their_notes(self):
        d = self.payload()
        self.assertEqual([m["id"] for m in d["permission_modes"]],
                         ["plan", "acceptEdits", "bypassPermissions",
                          "auto", "manual", "dontAsk"])
        for m in d["permission_modes"]:
            self.assertIn("note", m)

    def test_the_advanced_list_names_the_two_the_buttons_do_not_cover(self):
        self.assertEqual(self.payload()["permission_modes_advanced"],
                         ["manual", "dontAsk"])

    def test_access_options_carries_settable_before_the_click(self):
        """A control the server will refuse must say so BEFORE it is clicked,
        or the screen reads as broken rather than as gated."""
        by_id = {o["id"]: o for o in self.payload()["access_options"]}
        self.assertFalse(by_id["full"]["settable"])
        self.assertTrue(by_id["full"]["requires_unlock"])
        self.assertTrue(by_id["read"]["settable"])

    def test_the_settings_block_carries_the_derived_access_id(self):
        self.post("/api/settings", {"permission_mode": "plan"})
        d = self.payload()
        self.assertEqual(d["settings"]["access"], "read")
        self.assertFalse(d["settings"]["access_advanced"])


class SettingsPost(Routes):

    def test_an_access_id_stores_the_native_mode(self):
        r = self.post("/api/settings", {"access": "read"})
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["settings"]["permission_mode"], "plan")
        self.assertEqual(self.raw(), {"permission_mode": "plan"},
                         "no new key may be written")

    def test_a_gated_access_id_is_a_400_with_the_reason(self):
        r = self.post("/api/settings", {"access": "full"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("auto-approves", r.json()["detail"])

    def test_auto_on_codex_is_a_400_naming_what_codex_does_offer(self):
        r = self.post("/api/settings",
                      {"access": "auto", "access_provider": "codex"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not offer", r.json()["detail"])

    def test_both_vocabularies_at_once_is_a_400(self):
        r = self.post("/api/settings",
                      {"access": "read", "permission_mode": "plan"})
        self.assertEqual(r.status_code, 400)

    def test_the_old_permission_mode_field_still_works(self):
        r = self.post("/api/settings", {"permission_mode": "dontAsk"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["settings"]["permission_mode"], "dontAsk")

    def test_a_provider_settings_patch_writes_only_its_own_key(self):
        self.post("/api/settings", {"permission_mode": "plan"})
        r = self.post("/api/settings",
                      {"provider_settings": {"claude": {"chrome": True}}})
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(self.raw(),
                         {"permission_mode": "plan",
                          "provider_settings": {"claude": {"chrome": True}}})

    def test_a_bad_provider_settings_patch_is_a_400(self):
        r = self.post("/api/settings",
                      {"provider_settings": {"claude": {"nope": True}}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("unknown setting", r.json()["detail"])

    def test_a_switch_and_a_mode_can_arrive_together(self):
        r = self.post("/api/settings",
                      {"access": "read",
                       "provider_settings": {"codex": {"memory": False}}})
        self.assertEqual(r.status_code, 200)
        body = r.json()["settings"]
        self.assertEqual(body["permission_mode"], "plan")
        self.assertEqual(body["provider_settings"], {"codex": {"memory": False}})

    def test_an_empty_body_is_still_a_400(self):
        r = self.post("/api/settings", {})
        self.assertEqual(r.status_code, 400)
        self.assertIn("nothing to update", r.json()["detail"])

    def test_a_catalogue_only_model_id_can_be_saved(self):
        """The failure the widened id set exists to prevent: the picker offers
        `best`, the user clicks it, and the API calls it unknown."""
        r = self.post("/api/settings", {"model": "best"})
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.json()["settings"]["model"], "best")

    def test_an_unknown_model_id_is_still_refused(self):
        r = self.post("/api/settings", {"model": "claude-opus-9-9"})
        self.assertEqual(r.status_code, 400)


class UsageAll(Routes):

    def test_it_answers_one_row_per_provider(self):
        with mock.patch("usage.all_providers",
                        return_value={"providers": [{"id": "claude"}],
                                      "fetched_at": 1.0, "source": "live"}):
            r = self.get("/api/usage/all")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["providers"], [{"id": "claude"}])

    def test_refresh_zero_is_passed_through(self):
        with mock.patch("usage.all_providers",
                        return_value={"providers": []}) as spy:
            self.get("/api/usage/all?refresh=0")
        self.assertEqual(spy.call_args.kwargs, {"refresh": False})

    def test_it_never_5xxs_when_a_provider_blows_up(self):
        with mock.patch("providers.deepseek_auth_state",
                        side_effect=RuntimeError("boom")), \
             mock.patch("providers.provider_bin", return_value=None):
            r = self.get("/api/usage/all")
        self.assertEqual(r.status_code, 200)
        states = {p["id"]: p["state"] for p in r.json()["providers"]}
        self.assertEqual(states["deepseek"], "error")

    def test_the_existing_usage_routes_still_answer(self):
        """Unchanged, and proved so without a network call: the two snapshots
        are stubbed at their own failure shape, which is what a machine with no
        credential answers anyway."""
        unavailable = {"available": False, "reason": "stubbed",
                       "limits": [], "extra_usage": None}
        with mock.patch("usage.snapshot", return_value=unavailable), \
             mock.patch("deepseek_usage.snapshot", return_value=unavailable):
            for path in ("/api/usage", "/api/account", "/api/deepseek/usage"):
                r = self.get(path)
                self.assertEqual(r.status_code, 200, path)
                self.assertIn("available", r.json(), path)


class ToolRoutes(Routes):

    def test_the_report_is_a_list_of_rows(self):
        with mock.patch("providers.tools_report",
                        return_value=[{"id": "claude"}]):
            r = self.get("/api/providers/tools")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [{"id": "claude"}])

    def test_an_unknown_id_is_a_404(self):
        r = self.post("/api/providers/tools/gemini/update")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "UNKNOWN_PROVIDER")

    def test_the_update_needs_the_panel_token(self):
        r = self.client.post("/api/providers/tools/claude/update", json={})
        self.assertEqual(r.status_code, 403)

    def test_a_refusal_is_200_with_ok_false_and_a_code(self):
        """Matching its neighbours: the rows ride along either way, so the
        screen corrects itself even when nothing was updated."""
        err = providers.ToolUpdateError("CHAT_RUNNING", "a chat is open.")
        with mock.patch("providers.update_tool", side_effect=err), \
             mock.patch("providers.tools_report", return_value=[]):
            r = self.post("/api/providers/tools/claude/update")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["code"], "CHAT_RUNNING")
        self.assertIn("tools", body)

    def test_a_successful_update_reports_both_versions(self):
        done = {"ok": True, "provider": "claude", "version_before": "2.1.247",
                "version_after": "2.1.270", "log": "done", "changed": True}
        with mock.patch("providers.update_tool", return_value=done), \
             mock.patch("providers.tools_report", return_value=[]):
            r = self.post("/api/providers/tools/claude/update")
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["code"], "UPDATED")
        self.assertEqual(body["version_before"], "2.1.247")
        self.assertEqual(body["version_after"], "2.1.270")

    def test_an_unchanged_update_says_already(self):
        done = {"ok": True, "provider": "codex", "version_before": "0.154.0",
                "version_after": "0.154.0", "log": "", "changed": False}
        with mock.patch("providers.update_tool", return_value=done), \
             mock.patch("providers.tools_report", return_value=[]):
            r = self.post("/api/providers/tools/codex/update")
        self.assertEqual(r.json()["code"], "ALREADY")

    def test_a_live_chat_refuses_the_real_update(self):
        """End to end through the route, with no mock on update_tool."""
        providers.chat_started("claude")
        try:
            with mock.patch("providers.tools_report", return_value=[]):
                r = self.post("/api/providers/tools/claude/update")
        finally:
            providers.chat_finished("claude")
        self.assertEqual(r.json()["code"], "CHAT_RUNNING")


if __name__ == "__main__":
    unittest.main()
