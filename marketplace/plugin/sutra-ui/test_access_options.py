"""test_access_options.py -- the four plain-English access choices, and the
promise that nothing about what is STORED has changed.

The risk in this change is not the new vocabulary. It is that a machine already
running Sutra has a `permission_mode` in settings.json -- possibly `dontAsk`,
which every routine writes -- and a screen with four buttons must not lose,
rewrite or silently downgrade it. So most of this file is about the OLD values.

EVERY TEST USES A TEMP SETTINGS FILE. providers.SETTINGS_PATH is module-level,
so it is rebound per test and restored in tearDown; nothing here can reach
~/.sutra-ui.

Run: python -m pytest test_access_options.py -q
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import providers   # noqa: E402


class TempSettings(unittest.TestCase):
    """A throwaway settings.json, and the unsafe-mode env var forced OFF.

    The env var is popped rather than left alone because a machine that exports
    SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1 would make every gating test pass for the
    wrong reason -- the same class of false green test_deepseek_usage's
    no_key_anywhere() was written about.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sutra-access-test-")
        self._old_path = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.dir) / "settings.json"
        self._old_env = os.environ.pop(providers.UNSAFE_MODES_ENV, None)

    def tearDown(self):
        providers.SETTINGS_PATH = self._old_path
        if self._old_env is not None:
            os.environ[providers.UNSAFE_MODES_ENV] = self._old_env
        shutil.rmtree(self.dir, ignore_errors=True)

    def raw(self):
        return json.loads(providers.SETTINGS_PATH.read_text())

    def consent(self):
        providers.save_settings(unsafe_ack=providers.UNSAFE_ACK_PHRASE)


class TheTable(TempSettings):

    def test_the_four_ids_in_order(self):
        self.assertEqual([o["id"] for o in providers.access_options()],
                         ["read", "edits", "auto", "full"])

    def test_only_full_carries_the_warning(self):
        warned = [o["id"] for o in providers.access_options() if o["warn"]]
        self.assertEqual(warned, ["full"])

    def test_the_native_mapping_is_the_spec_table(self):
        self.assertEqual(providers.access_native_map(), {
            "read": {"claude": "plan", "codex": "plan", "deepseek": "plan"},
            "edits": {"claude": "acceptEdits", "codex": "acceptEdits",
                      "deepseek": "acceptEdits"},
            "auto": {"claude": "auto"},
            "full": {"claude": "bypassPermissions",
                     "codex": "bypassPermissions",
                     "deepseek": "bypassPermissions"},
        })

    def test_auto_is_offered_to_claude_alone(self):
        by_provider = providers.access_by_provider()
        self.assertEqual(by_provider["claude"], ["read", "edits", "auto", "full"])
        self.assertEqual(by_provider["codex"], ["read", "edits", "full"])
        self.assertEqual(by_provider["deepseek"], ["read", "edits", "full"])
        self.assertNotIn("gemini", by_provider,
                         "a provider with no adapter must have no access control")
        self.assertIsNone(providers.access_native("auto", "codex"))

    def test_every_native_mode_in_the_table_is_a_real_permission_mode(self):
        for natives in providers.access_native_map().values():
            for mode in natives.values():
                self.assertIn(mode, providers.PERMISSION_MODES)

    def test_the_advanced_list_is_what_the_four_do_not_cover(self):
        self.assertEqual(providers.advanced_permission_modes(),
                         ["manual", "dontAsk"])

    def test_the_reverse_lookup_agrees_with_the_forward_one(self):
        for opt in providers.ACCESS_OPTIONS:
            for pid, mode in opt["native"].items():
                self.assertEqual(providers.access_for_native(mode, pid), opt["id"])

    def test_an_advanced_mode_has_no_access_id(self):
        self.assertIsNone(providers.access_for_native("dontAsk", "claude"))
        self.assertIsNone(providers.access_for_native("manual", "claude"))

    def test_auto_does_not_reverse_map_on_codex(self):
        """`auto` can be STORED while Claude is selected and then read on a
        Codex pane -- permission_mode is global. The reverse lookup must answer
        "not one of yours" rather than lighting a button Codex cannot honour."""
        self.assertIsNone(providers.access_for_native("auto", "codex"))
        self.assertEqual(providers.access_for_native("auto", "claude"), "auto")


class TheGate(TempSettings):
    """Consent is unchanged: the two write-capable choices are still gated by
    exactly what gated the native modes they map to."""

    def test_edits_and_full_are_not_settable_before_consent(self):
        by_id = {o["id"]: o for o in providers.access_options("claude")}
        self.assertTrue(by_id["read"]["settable"])
        self.assertTrue(by_id["auto"]["settable"])
        self.assertFalse(by_id["edits"]["settable"])
        self.assertFalse(by_id["full"]["settable"])
        self.assertTrue(by_id["edits"]["requires_unlock"])

    def test_they_become_settable_after_consent(self):
        self.consent()
        by_id = {o["id"]: o for o in providers.access_options("claude")}
        self.assertTrue(by_id["edits"]["settable"])
        self.assertTrue(by_id["full"]["settable"])

    def test_saving_edits_without_consent_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            providers.save_settings(access="edits", access_provider="claude")
        self.assertIn("auto-approves", str(ctx.exception))
        self.assertFalse(providers.SETTINGS_PATH.exists(),
                         "a refused save must write nothing")

    def test_consent_and_the_choice_can_arrive_in_one_request(self):
        out = providers.save_settings(
            unsafe_ack=providers.UNSAFE_ACK_PHRASE, access="full",
            access_provider="claude")
        self.assertEqual(out["permission_mode"], "bypassPermissions")
        self.assertEqual(out["access"], "full")


class WhatIsStored(TempSettings):
    """THE contract: an access id goes in, a NATIVE mode comes out on disk."""

    def test_read_stores_plan_and_nothing_else(self):
        providers.save_settings(access="read", access_provider="claude")
        self.assertEqual(self.raw(), {"permission_mode": "plan"})

    def test_full_stores_bypasspermissions(self):
        self.consent()
        providers.save_settings(access="full", access_provider="deepseek")
        self.assertEqual(self.raw()["permission_mode"], "bypassPermissions")

    def test_no_access_key_is_ever_written(self):
        self.consent()
        providers.save_settings(access="edits", access_provider="claude")
        self.assertNotIn("access", self.raw())

    def test_an_unknown_access_id_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            providers.save_settings(access="wide-open")
        self.assertIn("unknown access", str(ctx.exception))

    def test_auto_on_a_provider_that_does_not_offer_it_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            providers.save_settings(access="auto", access_provider="codex")
        self.assertIn("does not offer", str(ctx.exception))

    def test_sending_both_vocabularies_is_refused(self):
        """Two answers to one question, and no rule for which wins."""
        with self.assertRaises(ValueError) as ctx:
            providers.save_settings(access="read", permission_mode="plan")
        self.assertIn("not both", str(ctx.exception))

    def test_the_provider_defaults_to_the_stored_one(self):
        providers.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        providers.SETTINGS_PATH.write_text(json.dumps({"provider": "deepseek"}))
        providers.save_settings(access="read")
        self.assertEqual(self.raw()["permission_mode"], "plan")


class LegacyValuesKeepWorking(TempSettings):
    """Nothing a user already chose may disappear because a newer screen has a
    shorter list. `dontAsk` is what every routine writes."""

    def test_a_stored_dontask_still_loads(self):
        providers.save_settings(permission_mode="dontAsk")
        out = providers.load_settings()
        self.assertEqual(out["permission_mode"], "dontAsk")
        self.assertIsNone(out["access"])
        self.assertTrue(out["access_advanced"])

    def test_a_stored_manual_still_loads(self):
        providers.save_settings(permission_mode="manual")
        out = providers.load_settings()
        self.assertEqual(out["permission_mode"], "manual")
        self.assertTrue(out["access_advanced"])

    def test_the_flat_permission_mode_list_is_unchanged(self):
        self.assertEqual(providers.PERMISSION_MODES,
                         ("plan", "acceptEdits", "bypassPermissions",
                          "auto", "manual", "dontAsk"))

    def test_permission_modes_by_provider_is_unchanged(self):
        got = providers.all_permission_modes_by_provider()
        self.assertEqual(got["claude"], list(providers.PERMISSION_MODES))
        self.assertEqual(got["codex"],
                         ["plan", "acceptEdits", "bypassPermissions"])
        self.assertEqual(got["deepseek"],
                         ["plan", "acceptEdits", "bypassPermissions"])

    def test_setting_a_mode_the_old_way_still_works(self):
        providers.save_settings(permission_mode="plan")
        self.assertEqual(self.raw()["permission_mode"], "plan")
        self.assertEqual(providers.load_settings()["access"], "read")

    def test_load_settings_still_carries_every_old_key(self):
        """Additive, not a reshuffle. These are the keys clients read today."""
        out = providers.load_settings()
        for key in ("provider", "permission_mode", "workdir", "onboarded",
                    "chat_scope", "model", "model_by_provider",
                    "permission_mode_note", "permission_mode_effective",
                    "permission_mode_clamped", "unsafe_modes_allowed",
                    "workdir_root", "flags", "deepseek_auth", "settings_path",
                    "invalid_stored_values"):
            self.assertIn(key, out)


class TheClampStillApplies(TempSettings):
    """effective_permission_mode() gates at the point of USE, not only at the
    point of save -- a settings.json written by hand must not reach a spawn."""

    def test_a_hand_written_unsafe_mode_is_still_clamped(self):
        providers.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        providers.SETTINGS_PATH.write_text(
            json.dumps({"permission_mode": "bypassPermissions"}))
        out = providers.load_settings()
        self.assertEqual(out["permission_mode"], "bypassPermissions")
        self.assertEqual(out["permission_mode_effective"], "plan")
        self.assertTrue(out["permission_mode_clamped"])
        self.assertEqual(out["access"], "full")
        self.assertEqual(out["access_effective"], "read",
                         "the effective access must follow the clamp, not the "
                         "stored value")


if __name__ == "__main__":
    unittest.main()
