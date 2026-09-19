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
        # ...and the OPT-OUT popped for the same reason the opt-in is: a
        # machine that exports SUTRA_UI_SAFE_PERM_MODES=1 would otherwise run
        # every test below in the clamped posture, which since 2026-09-18 is
        # no longer the shipped one. Tests that WANT the gate engage it
        # explicitly by subclassing ClampedPosture.
        self._old_clamp = os.environ.pop(providers.CLAMP_MODES_ENV, None)

    def tearDown(self):
        providers.SETTINGS_PATH = self._old_path
        # SYMMETRIC WITH THE CLAMP BELOW, and it has to be: a test in here
        # sets the opt-in to prove it still works inside the opt-out, and a
        # tearDown that only RESTORES leaves that "1" in os.environ for the
        # whole rest of the run. Every later suite then reads unsafe modes as
        # authorised -- test_provider_routes' gate tests were failing in the
        # full run and passing alone for exactly that reason.
        if self._old_env is not None:
            os.environ[providers.UNSAFE_MODES_ENV] = self._old_env
        else:
            os.environ.pop(providers.UNSAFE_MODES_ENV, None)
        if self._old_clamp is not None:
            os.environ[providers.CLAMP_MODES_ENV] = self._old_clamp
        else:
            os.environ.pop(providers.CLAMP_MODES_ENV, None)
        shutil.rmtree(self.dir, ignore_errors=True)


    def raw(self):
        return json.loads(providers.SETTINGS_PATH.read_text())

    def consent(self):
        providers.save_settings(unsafe_ack=providers.UNSAFE_ACK_PHRASE)


class ClampedPosture(TempSettings):
    """The opt-out posture, which is where the consent gate still lives.

    Founder direction 2026-09-18 made Full access the shipped default AND made
    it run, so the gate no longer fires unless an operator asks for it with
    SUTRA_UI_SAFE_PERM_MODES=1 (kiosk / demo / shared machine). None of the
    gate's machinery was deleted, so all of it is still worth testing -- it
    just has to be switched on first, which is what this class does.
    """

    def setUp(self):
        super().setUp()
        os.environ[providers.CLAMP_MODES_ENV] = "1"


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


class TheGate(ClampedPosture):
    """Consent WHERE CONSENT STILL APPLIES: with SUTRA_UI_SAFE_PERM_MODES=1,
    the two write-capable choices are gated by exactly what gated the native
    modes they map to, exactly as before 2026-09-18. What changed is which
    posture ships by default, not what the gate does once engaged --
    TheDefaultPosture below pins the other half."""

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

    def test_read_stores_plan_and_the_stamp_that_makes_it_a_choice(self):
        """The mode, plus providers.ACCESS_CHOSEN_KEY -- and nothing else.

        The stamp is the ONE key this file's original "nothing else" assertion
        gave up, and it is load-bearing: without it load_settings cannot tell
        this deliberate `plan` from the one the pre-2026-09-18 default wrote,
        and would widen it back to Full access on the next read.
        """
        providers.save_settings(access="read", access_provider="claude")
        self.assertEqual(self.raw(),
                         {"permission_mode": "plan",
                          providers.ACCESS_CHOSEN_KEY: True})

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


class TheClampStillApplies(ClampedPosture):
    """IN THE CLAMPED POSTURE, effective_permission_mode() gates at the point
    of USE, not only at the point of save -- a settings.json written by hand
    must not reach a spawn. This is the property the opt-out exists to give
    back, so it is tested with the opt-out on."""

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


class TheDefaultPosture(TempSettings):
    """THE SHIPPED DEFAULT, founder direction 2026-09-18: Setup -> Access and
    permissions defaults to Full access -- and Full access is what RUNS.

    The half that is easy to get wrong is the second one. Storing
    `bypassPermissions` and then clamping it away at the point of use gives a
    screen that shows Full access selected while every session starts as
    `plan`, which is the Read only the direction was about, only harder to
    see. So every test here asserts the EFFECTIVE value, not the stored one.
    """

    def test_a_machine_that_has_never_chosen_runs_full_access(self):
        out = providers.load_settings()
        self.assertFalse(providers.SETTINGS_PATH.exists(),
                         "this test is meaningless if something wrote a choice")
        self.assertEqual(out["permission_mode"], "bypassPermissions")
        self.assertEqual(out["permission_mode_effective"], "bypassPermissions",
                         "the default must RUN, not be stored and clamped away")
        self.assertFalse(out["permission_mode_clamped"])
        self.assertEqual(out["access"], "full")
        self.assertEqual(out["access_effective"], "full")

    def test_every_one_of_the_four_is_settable_without_a_ceremony(self):
        """`settable` is the posture-dependent field -- the one the screen
        draws the `locked` pill from. `requires_unlock` is NOT: it is a static
        property of the option ("this maps to a write-capable native mode")
        and stays true for edits/full in every posture, which is why it is
        asserted unchanged rather than flipped."""
        by_id = {o["id"]: o for o in providers.access_options("claude")}
        for oid in ("read", "edits", "auto", "full"):
            self.assertTrue(by_id[oid]["settable"],
                            "%r is not settable in the shipped posture" % oid)
        self.assertTrue(by_id["full"]["requires_unlock"])
        self.assertFalse(by_id["read"]["requires_unlock"])

    def test_full_saves_without_an_acknowledgement(self):
        out = providers.save_settings(access="full", access_provider="claude")
        self.assertEqual(out["permission_mode"], "bypassPermissions")
        self.assertEqual(out["permission_mode_effective"], "bypassPermissions")

    def test_read_only_is_still_reachable_and_is_honoured(self):
        """A wider default must not make the NARROW choice unreachable, and
        must not silently widen it back on the next read -- otherwise the
        screen has four buttons and one outcome."""
        providers.save_settings(access="read", access_provider="claude")
        out = providers.load_settings()
        self.assertEqual(self.raw(),
                         {"permission_mode": "plan",
                          providers.ACCESS_CHOSEN_KEY: True})
        self.assertEqual(out["permission_mode_effective"], "plan")
        self.assertEqual(out["access_effective"], "read")
        self.assertFalse(out["permission_mode_clamped"])

    def test_the_opt_out_restores_the_whole_gate(self):
        """SUTRA_UI_SAFE_PERM_MODES=1 is the documented way back to the old
        posture. If it ever stops working, the loosening is irreversible."""
        os.environ[providers.CLAMP_MODES_ENV] = "1"
        by_id = {o["id"]: o for o in providers.access_options("claude")}
        self.assertFalse(by_id["full"]["settable"])
        self.assertTrue(by_id["full"]["requires_unlock"])
        self.assertEqual(
            providers.effective_permission_mode("bypassPermissions"), "plan")
        with self.assertRaises(ValueError):
            providers.save_settings(access="full", access_provider="claude")

    def test_the_old_opt_in_still_works_inside_the_opt_out(self):
        """Both original ways through the gate survive, so an install that set
        the env var years ago behaves identically."""
        os.environ[providers.CLAMP_MODES_ENV] = "1"
        os.environ[providers.UNSAFE_MODES_ENV] = "1"
        self.assertTrue(providers.unsafe_modes_allowed())
        self.assertEqual(
            providers.effective_permission_mode("bypassPermissions"),
            "bypassPermissions")

    def test_an_unparseable_stored_value_still_lands_on_the_floor(self):
        """The widened default must not be reachable by being WRONG -- junk on
        disk goes to `plan`, never to Full access."""
        providers.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        providers.SETTINGS_PATH.write_text(json.dumps({"permission_mode": "telepathy"}))
        out = providers.load_settings()
        self.assertEqual(out["permission_mode"], "plan")
        self.assertEqual(out["permission_mode_effective"], "plan")
        self.assertIn("permission_mode", out["invalid_stored_values"])


class AnInheritedReadOnlyIsNotAChoice(TempSettings):
    """THE HALF THE 2026-09-18 DIRECTION MISSED, and why it is being fixed now.

    Widening DEFAULT_PERMISSION_MODE only changes what an ABSENT key resolves
    to. Every machine already onboarded has the key -- `plan`, written by the
    OLD default, never picked off a screen -- so on every existing install the
    direction changed nothing: the app kept opening on Read only. That is the
    founder's own machine, and it is the whole population of installs that
    predate the change.

    So a stored floor mode with no providers.ACCESS_CHOSEN_KEY beside it is
    read as "never chose". The risk this class exists to hold down is the
    obvious one: that the rule reaches further than the floor, or that it
    overrides someone who actually picked Read only.
    """

    def _write(self, raw):
        providers.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        providers.SETTINGS_PATH.write_text(json.dumps(raw))

    def test_a_pre_change_plan_now_resolves_to_full_access(self):
        """The founder's settings.json, verbatim in shape."""
        self._write({"onboarded": True, "permission_mode": "plan",
                     "provider": "claude", "unsafe_modes_acknowledged": True})
        out = providers.load_settings()
        self.assertEqual(out["permission_mode"], "bypassPermissions")
        self.assertEqual(out["permission_mode_effective"], "bypassPermissions")
        self.assertEqual(out["access_effective"], "full")

    def test_a_stamped_plan_stays_read_only(self):
        """The stamp is what makes Read only a decision rather than a leftover.
        If this fails, the four buttons have one outcome again."""
        self._write({"permission_mode": "plan",
                     providers.ACCESS_CHOSEN_KEY: True})
        self.assertEqual(providers.load_settings()["access_effective"], "read")

    def test_choosing_read_only_now_survives_the_next_read(self):
        """End to end through the real writer, which is the path the screen
        uses -- not a hand-built file."""
        providers.save_settings(access="read", access_provider="claude")
        self.assertIs(self.raw()[providers.ACCESS_CHOSEN_KEY], True)
        self.assertEqual(providers.load_settings()["access_effective"], "read")

    def test_it_only_ever_touches_the_floor_mode(self):
        """An unstamped `acceptEdits` or `dontAsk` is someone's setting too.
        The rule must not treat every unstamped value as up for grabs."""
        for stored in ("acceptEdits", "dontAsk", "manual", "auto"):
            self._write({"permission_mode": stored})
            self.assertEqual(providers.load_settings()["permission_mode"],
                             stored, "unstamped %r was rewritten" % stored)

    def test_nothing_is_written_to_disk_by_reading(self):
        """A RESOLUTION rule, not a migration: reverting it must revert the
        behaviour with no rewritten settings.json left behind."""
        before = {"permission_mode": "plan"}
        self._write(before)
        providers.load_settings()
        self.assertEqual(self.raw(), before)

    def test_the_env_var_still_wins(self):
        """SUTRA_UI_PERMISSION_MODE is the documented headless escape hatch and
        is a deliberate operator act, so it outranks the default this rule
        falls through to."""
        self._write({"permission_mode": "plan"})
        os.environ["SUTRA_UI_PERMISSION_MODE"] = "plan"
        try:
            self.assertEqual(
                providers.load_settings()["permission_mode_effective"], "plan")
        finally:
            os.environ.pop("SUTRA_UI_PERMISSION_MODE", None)


class OnlyAClaimedPickPinsReadOnly(TempSettings):
    """THE SECOND HALF, added 2026-09-19 after the first half did not hold.

    The inherited-floor rule above cannot help a machine whose `plan` carries
    the stamp -- and the owner's machine acquired one at 10:58:53 that morning
    from a POST no log, transcript or UI path could be traced back to. Naming a
    mode was enough to stamp it, and naming one is not the same as choosing one:
    an echo of the value already on the screen names one too.

    So the claim is now explicit (`chosen`), the HTTP boundary defaults it to
    False, and the two controls a human presses send it True. What this class
    holds down: that an unclaimed write can still SET the mode (it is not a
    refusal), that it cannot PIN Read only past a restart, and that a real pick
    still sticks exactly as it did.
    """

    def _write(self, raw):
        providers.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        providers.SETTINGS_PATH.write_text(json.dumps(raw))

    def test_an_unclaimed_write_stores_the_mode_but_does_not_stamp_it(self):
        providers.save_settings(permission_mode="plan", chosen=False)
        self.assertEqual(self.raw()["permission_mode"], "plan")
        self.assertNotIn(providers.ACCESS_CHOSEN_KEY, self.raw())

    def test_an_unclaimed_read_only_resolves_back_to_full_access(self):
        """THE FOUNDER'S ASK, in one assertion: an unattributed write cannot
        leave the app opening on Read only."""
        providers.save_settings(permission_mode="plan", chosen=False)
        self.assertEqual(providers.load_settings()["access_effective"], "full")

    def test_a_claimed_read_only_still_sticks(self):
        """The other side: the four buttons must keep meaning something."""
        providers.save_settings(permission_mode="plan", chosen=True)
        self.assertIs(self.raw()[providers.ACCESS_CHOSEN_KEY], True)
        self.assertEqual(providers.load_settings()["access_effective"], "read")

    def test_direct_library_calls_still_default_to_claiming(self):
        """`chosen` defaults True in Python: naming a mode in code IS the
        deliberate act. Only the unauthenticated HTTP boundary defaults it
        off, which is where the unowned write came from."""
        providers.save_settings(access="read", access_provider="claude")
        self.assertIs(self.raw()[providers.ACCESS_CHOSEN_KEY], True)

    def test_an_unclaimed_write_that_moves_the_mode_drops_the_old_claim(self):
        """A stamp describes the value beneath it, not the key. Left behind, it
        would let an unowned write inherit a pick made for a mode that is no
        longer stored."""
        self._write({"permission_mode": "plan",
                     providers.ACCESS_CHOSEN_KEY: True})
        providers.save_settings(permission_mode="acceptEdits", chosen=False)
        self.assertNotIn(providers.ACCESS_CHOSEN_KEY, self.raw())

    def test_an_unclaimed_write_of_the_SAME_mode_leaves_the_claim_alone(self):
        """An echo changes nothing, so it un-decides nothing either: a founder
        who genuinely picked Read only keeps it."""
        self._write({"permission_mode": "plan",
                     providers.ACCESS_CHOSEN_KEY: True})
        providers.save_settings(permission_mode="plan", chosen=False)
        self.assertIs(self.raw()[providers.ACCESS_CHOSEN_KEY], True)
        self.assertEqual(providers.load_settings()["access_effective"], "read")


if __name__ == "__main__":
    unittest.main()
