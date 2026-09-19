"""Shadow inherits the global permission mode. ONE source of truth.

_shadow_args passed a literal "plan", so a founder running the app in
acceptEdits got chat panes that could write and delegates that could not:
the delegate designed the change and then stopped, because its own flag
forbade doing it. Shadow is not a separate trust domain -- it is the same
operator working through a different surface.

The fix reuses providers.effective_permission_mode() rather than adding a
Shadow-specific setting, so every existing gate is INHERITED, not
re-implemented. These tests pin that equivalence: for each stored mode, what
Shadow gets must equal what ws_chat computes from the same settings.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import app
import providers


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = providers.SETTINGS_PATH
        self.settings = Path(self.tmp.name) / "settings.json"
        providers.SETTINGS_PATH = self.settings
        self._unsafe = os.environ.get(providers.UNSAFE_MODES_ENV)
        self._pretend_claude()

    def tearDown(self):
        providers.SETTINGS_PATH = self._orig
        if self._unsafe is None:
            os.environ.pop(providers.UNSAFE_MODES_ENV, None)
        else:
            os.environ[providers.UNSAFE_MODES_ENV] = self._unsafe
        self.tmp.cleanup()

    def _pretend_claude(self):
        """Shadow refuses a non-Claude provider (SHADOW_PROVIDERS), so the
        argv builder needs a resolvable claude binary to reach at all."""
        self._orig_detail = providers.active_provider_detail
        self._orig_by_id = providers.provider_by_id
        # same shape test_shadow_delegate._pretend uses -- load_settings
        # reads detail["ignored"], so a partial stub breaks it
        providers.active_provider_detail = lambda: {
            "id": "claude", "source": "settings", "ignored": []}
        providers.provider_by_id = lambda pid: {
            "id": "claude", "name": "Claude Code",
            "bin_path": "/opt/homebrew/bin/claude",
            "runnable": True, "reason": None}
        self.addCleanup(setattr, providers, "active_provider_detail",
                        self._orig_detail)
        self.addCleanup(setattr, providers, "provider_by_id", self._orig_by_id)

    def write_mode(self, mode):
        self.settings.write_text(json.dumps({"permission_mode": mode}))

    def unsafe(self, allowed):
        """The REAL gate: SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1, or a recorded
        `unsafe_modes_acknowledged` in settings.json. Driven by the env var
        here because that is the out-of-band half and needs no consent
        phrase. (READ_ONLY_ENV gates editing_allowed(), a different thing.)

        SINCE 2026-09-18 the gate is an OPT-OUT, so `unsafe(False)` must
        ENGAGE it (SUTRA_UI_SAFE_PERM_MODES=1) rather than merely drop the
        opt-in -- otherwise "unsafe modes off" silently means "on", and the
        clamped half of every assertion below tests nothing. Both vars are set
        explicitly rather than popped, because this class asserts an
        EQUIVALENCE between Shadow and chat: an ambient value inherited from
        whatever ran before would move both sides together and pass while
        measuring the wrong posture.
        """
        if allowed:
            os.environ[providers.UNSAFE_MODES_ENV] = "1"
            os.environ.pop(providers.CLAMP_MODES_ENV, None)
        else:
            os.environ.pop(providers.UNSAFE_MODES_ENV, None)
            os.environ[providers.CLAMP_MODES_ENV] = "1"
        self.addCleanup(os.environ.pop, providers.UNSAFE_MODES_ENV, None)
        self.addCleanup(os.environ.pop, providers.CLAMP_MODES_ENV, None)

    def shadow_mode(self):
        args = app._shadow_args()
        self.assertIn("--permission-mode", args)
        return args[args.index("--permission-mode") + 1]

    def chat_mode(self):
        """What ws_chat computes from the same settings -- the contract."""
        return providers.effective_permission_mode(
            providers.load_settings()["permission_mode"])


class TestShadowInheritsTheGlobalMode(Base):

    def test_01_global_plan_gives_shadow_plan(self):
        self.write_mode("plan")
        self.unsafe(True)
        self.assertEqual(self.shadow_mode(), "plan")
        self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_02_authorized_acceptEdits_reaches_shadow(self):
        """THE BUG. This was "plan" no matter what the founder had set."""
        self.write_mode("acceptEdits")
        self.unsafe(True)
        self.assertEqual(self.shadow_mode(), "acceptEdits")
        self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_03_unauthorized_acceptEdits_is_clamped_like_chat(self):
        """The gate is INHERITED, not bypassed: with unsafe modes off,
        Shadow gets exactly the clamped value normal chat gets."""
        self.write_mode("acceptEdits")
        self.unsafe(False)
        self.assertEqual(self.chat_mode(), "plan", "chat is clamped")
        self.assertEqual(self.shadow_mode(), "plan", "so is Shadow")
        self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_04_authorized_bypassPermissions_reaches_shadow(self):
        self.write_mode("bypassPermissions")
        self.unsafe(True)
        self.assertEqual(self.shadow_mode(), "bypassPermissions")
        self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_05_unauthorized_bypassPermissions_is_clamped_like_chat(self):
        self.write_mode("bypassPermissions")
        self.unsafe(False)
        self.assertEqual(self.chat_mode(), "plan")
        self.assertEqual(self.shadow_mode(), "plan")
        self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_06_a_junk_stored_mode_still_resolves_to_plan(self):
        """A hand-edited or older-build settings.json must not raise the
        ceiling -- the same clamp-at-use rule ws_chat relies on."""
        self.settings.write_text(json.dumps({"permission_mode": "telepathy"}))
        self.unsafe(True)
        self.assertEqual(self.shadow_mode(), "plan")
        self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_07_shadow_and_chat_AGREE_for_every_supported_mode(self):
        """The contract itself, stated once: for every mode the app supports
        and both authorization states, Shadow == chat. A future edit that
        re-introduces a Shadow-specific mode fails here."""
        for mode in providers.PERMISSION_MODES:
            for allowed in (True, False):
                with self.subTest(mode=mode, unsafe_allowed=allowed):
                    self.write_mode(mode)
                    self.unsafe(allowed)
                    self.assertEqual(self.shadow_mode(), self.chat_mode())

    def test_08_no_shadow_specific_permission_setting_was_added(self):
        """Requirement 2, pinned in the source: the fix must reuse the one
        accessor, not introduce a parallel Shadow key."""
        src = Path(app.__file__).read_text()
        i = src.index("def _shadow_args(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn("providers.effective_permission_mode(", body,
                      "it must go through the shared accessor")
        self.assertNotIn('"", "plan"', body, "the hardcode is gone")
        for junk in ("shadow.permission_mode", "shadow_permission_mode",
                     "SHADOW_PERMISSION_MODE"):
            self.assertNotIn(junk, src,
                             "no Shadow-specific permission setting")

    def test_09_the_resume_argv_inherits_too(self):
        """ensure_runtime builds its argv through the same function, so an
        ATTACHED founder chat is not left on a different ceiling."""
        self.write_mode("acceptEdits")
        self.unsafe(True)
        args = app._shadow_args(session_id="sess-abc")
        self.assertEqual(args[args.index("--permission-mode") + 1],
                         "acceptEdits")
        self.assertIn("--resume", args)
        self.assertEqual(args[args.index("--resume") + 1], "sess-abc")

    def test_10_the_status_endpoint_reports_the_real_mode(self):
        """It returned a literal "plan" and would have kept saying so."""
        src = Path(app.__file__).read_text()
        i = src.index("async def api_shadow_status(")
        body = src[i:src.index("\n@app.", i + 10)]
        self.assertIn("effective_permission_mode", body)
        self.assertNotIn('"permission_mode": "plan"', body)


if __name__ == "__main__":
    unittest.main()
