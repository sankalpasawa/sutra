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

    def setUp(self):
        self._old = os.environ.pop(providers.UNSAFE_MODES_ENV, None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(providers.UNSAFE_MODES_ENV, None)
        else:
            os.environ[providers.UNSAFE_MODES_ENV] = self._old

    def test_unsafe_modes_rejected_on_write_by_default(self):
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


class WorkdirContainment(unittest.TestCase):

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
