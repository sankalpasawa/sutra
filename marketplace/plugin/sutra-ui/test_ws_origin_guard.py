"""test_ws_origin_guard.py -- the websocket/settings hardening added on top of PR #85.

Two confirmed high-severity holes are covered here, plus the clamps codex
flagged as insufficient-if-only-enforced-on-write:

  1. /ws/chat and /ws/term accepted ANY Origin. Browser same-origin policy does
     not cover WebSocket handshakes and no preflight is sent, so any page the
     operator visited could drive the local agent, read its output, and inject
     bytes into the PTY. Fixed by _origin_ok/_reject_cross_origin.
  2. An unauthenticated POST /api/settings could persist
     permission_mode=bypassPermissions, which ws_chat passed to the spawned
     agent as --permission-mode. Fixed by an env opt-in enforced at BOTH the
     write path (save_settings) and the use path (effective_permission_mode).

These are security glue: grep-style assertions are not enough, so each test
exercises the real function against the real values.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("SUTRA_NATIVE_HOME", tempfile.mkdtemp(prefix="sutra-ui-origin-test-"))
os.environ.setdefault("SUTRA_UI_SETTINGS",
                      os.path.join(tempfile.mkdtemp(prefix="sutra-ui-settings-"), "settings.json"))

import app          # noqa: E402
import providers    # noqa: E402


class _FakeWS(object):
    """Minimal stand-in: _origin_ok only reads .headers."""

    def __init__(self, origin=None):
        self.headers = {} if origin is None else {"origin": origin}


class OriginGuard(unittest.TestCase):

    def test_loopback_origins_allowed(self):
        for origin in ("http://127.0.0.1:8330", "http://localhost:8330",
                       "http://localhost", "https://127.0.0.1:9999"):
            self.assertTrue(app._origin_ok(_FakeWS(origin)), origin)

    def test_hostile_origins_rejected(self):
        for origin in ("https://evil.example", "http://evil.example",
                       "http://127.0.0.1.evil.example", "http://localhost.evil.example",
                       "https://evil.example:8330", "null", "file://"):
            self.assertFalse(app._origin_ok(_FakeWS(origin)), origin)

    def test_absent_origin_allowed_for_non_browser_clients(self):
        # RFC 6455: a browser MUST send Origin on a cross-origin handshake and
        # a page cannot suppress it, so this is not a browser-reachable bypass.
        self.assertTrue(app._origin_ok(_FakeWS(None)))

    def test_extra_origins_env_is_honoured(self):
        old = os.environ.get("SUTRA_UI_ALLOWED_ORIGINS")
        os.environ["SUTRA_UI_ALLOWED_ORIGINS"] = "https://trusted.example"
        try:
            self.assertTrue(app._origin_ok(_FakeWS("https://trusted.example")))
            self.assertFalse(app._origin_ok(_FakeWS("https://other.example")))
        finally:
            if old is None:
                del os.environ["SUTRA_UI_ALLOWED_ORIGINS"]
            else:
                os.environ["SUTRA_UI_ALLOWED_ORIGINS"] = old

    def test_both_socket_handlers_gate_before_accept(self):
        import inspect
        for fn in (app.ws_chat, app.ws_term):
            src = inspect.getsource(fn)
            gate = src.index("_reject_cross_origin")
            accept = src.index("ws.accept()")
            self.assertLess(gate, accept,
                            "%s must reject cross-origin BEFORE accept()" % fn.__name__)

    def test_trusted_host_middleware_installed(self):
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        self.assertTrue(any(m.cls is TrustedHostMiddleware for m in app.app.user_middleware),
                        "TrustedHostMiddleware missing -- DNS rebinding is open")
        self.assertNotIn("*", app.ALLOWED_HOSTS)


class PermissionModeGate(unittest.TestCase):
    """Hole 2's fix, exercised WITH THE GATE ENGAGED.

    Founder direction 2026-09-18 made Full access the shipped default and made
    it run, so the gate is now an opt-out (SUTRA_UI_SAFE_PERM_MODES=1) rather
    than the default posture -- see providers.unsafe_modes_allowed for why the
    clamp stopped answering its own threat once the DEFAULT became
    `bypassPermissions`. The gate's machinery is unchanged and still ships, so
    every assertion below still holds; it just has to be switched on first.
    DefaultPostureIsFullAccess covers the posture that now ships.
    """

    def setUp(self):
        self._old = os.environ.pop(providers.UNSAFE_MODES_ENV, None)
        self._old_clamp = os.environ.get(providers.CLAMP_MODES_ENV)
        os.environ[providers.CLAMP_MODES_ENV] = "1"
        # A FRESH SETTINGS FILE PER TEST, not the module-level one. The gate's
        # second way in is a RECORDED acknowledgement, so any earlier test in
        # the process that consented leaves this class asserting "the gate
        # refuses" against a settings.json that has already agreed -- green
        # for the wrong reason in a whole-directory run, red only here.
        self._old_path = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(
            tempfile.mkdtemp(prefix="sutra-ui-gate-")) / "settings.json"

    def tearDown(self):
        providers.SETTINGS_PATH = self._old_path
        if self._old is None:
            os.environ.pop(providers.UNSAFE_MODES_ENV, None)
        else:
            os.environ[providers.UNSAFE_MODES_ENV] = self._old
        if self._old_clamp is None:
            os.environ.pop(providers.CLAMP_MODES_ENV, None)
        else:
            os.environ[providers.CLAMP_MODES_ENV] = self._old_clamp

    def test_unsafe_modes_rejected_on_write_when_the_gate_is_engaged(self):
        for mode in providers.UNSAFE_PERMISSION_MODES:
            with self.assertRaises(ValueError):
                providers.save_settings(permission_mode=mode)

    def test_plan_still_writable(self):
        self.assertEqual(providers.save_settings(permission_mode="plan")["permission_mode"],
                         "plan")

    def test_stale_unsafe_value_is_clamped_at_use(self):
        # The hole codex caught: gating only the write path leaves a stale or
        # hand-edited settings.json able to reach the subprocess spawn.
        for mode in providers.UNSAFE_PERMISSION_MODES:
            self.assertEqual(providers.effective_permission_mode(mode), "plan")

    def test_opt_in_env_enables_unsafe_modes(self):
        os.environ[providers.UNSAFE_MODES_ENV] = "1"
        self.assertEqual(providers.effective_permission_mode("bypassPermissions"),
                         "bypassPermissions")
        self.assertEqual(providers.save_settings(permission_mode="acceptEdits")["permission_mode"],
                         "acceptEdits")
        providers.save_settings(permission_mode="plan")

    def test_unknown_mode_falls_back_to_plan(self):
        self.assertEqual(providers.effective_permission_mode("nonsense"), "plan")


class DefaultPostureIsFullAccess(unittest.TestCase):
    """The other half of the 2026-09-18 direction, pinned here next to the
    gate it replaced so the two can be read together.

    Hole 2 was "an unauthenticated POST could persist bypassPermissions". That
    is no longer a widening at all -- bypassPermissions is the shipped default,
    so a POST that sets it changes nothing a fresh install did not already do,
    and a process that can reach the port can delete the settings file to get
    the same result. What is still load-bearing is (a) that the narrow choice
    is honoured when an operator makes it and (b) that the origin guard above
    is what actually answers the cross-origin browser threat.
    """

    def setUp(self):
        self._old = os.environ.pop(providers.UNSAFE_MODES_ENV, None)
        self._old_clamp = os.environ.pop(providers.CLAMP_MODES_ENV, None)
        self._old_path = providers.SETTINGS_PATH     # same isolation, same why
        providers.SETTINGS_PATH = Path(
            tempfile.mkdtemp(prefix="sutra-ui-open-")) / "settings.json"

    def tearDown(self):
        providers.SETTINGS_PATH = self._old_path
        for key, val in ((providers.UNSAFE_MODES_ENV, self._old),
                         (providers.CLAMP_MODES_ENV, self._old_clamp)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_the_shipped_default_is_not_clamped_at_use(self):
        self.assertEqual(
            providers.effective_permission_mode(providers.DEFAULT_PERMISSION_MODE),
            providers.DEFAULT_PERMISSION_MODE,
            "the default must reach the spawn, or the screen lies about it")

    def test_a_deliberate_narrowing_is_still_honoured(self):
        self.assertEqual(
            providers.save_settings(permission_mode="plan")["permission_mode"],
            "plan")
        self.assertEqual(providers.effective_permission_mode("plan"), "plan")

    def test_junk_still_lands_on_the_floor_not_on_the_default(self):
        """The widened default must not be reachable by being WRONG."""
        self.assertEqual(providers.effective_permission_mode("nonsense"),
                         providers.PERMISSION_MODE_FLOOR)


class WorkdirContainment(unittest.TestCase):
    """Same import-time leak as test_claude_local's RecentWorkspace, same fix.

    providers.workdir_allowed() reads SUTRA_UI_WORKDIR_ROOT on every call and
    defaults to "~". test_shadow_delegate.py and test_codex_runtime.py set it
    to a temp dir at import time -- correctly, so importing `app` cannot touch
    the operator's real home -- and pytest performs those imports during
    COLLECTION, before any test runs. `test_home_paths_allowed` then asked
    whether ~ was inside a temp root and was told no. It passed alone and
    failed in the suite. A test that asserts about the default root sets it.
    """

    def setUp(self):
        self._orig_root = os.environ.pop("SUTRA_UI_WORKDIR_ROOT", None)
        self.addCleanup(self._restore_root)

    def _restore_root(self):
        if self._orig_root is None:
            os.environ.pop("SUTRA_UI_WORKDIR_ROOT", None)
        else:
            os.environ["SUTRA_UI_WORKDIR_ROOT"] = self._orig_root

    def test_paths_outside_root_rejected(self):
        for bad in ("/etc", "/", "/var/root", "/usr/bin"):
            self.assertFalse(providers.workdir_allowed(bad), bad)
            with self.assertRaises(ValueError):
                providers.save_settings(workdir=bad)

    def test_home_paths_allowed(self):
        self.assertTrue(providers.workdir_allowed(os.path.expanduser("~/sutra-ui-workspace")))

    def test_traversal_out_of_root_rejected(self):
        self.assertFalse(providers.workdir_allowed(os.path.expanduser("~/../../etc")))


if __name__ == "__main__":
    unittest.main()
