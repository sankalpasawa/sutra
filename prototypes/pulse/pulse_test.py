"""Pulse tests. Plain script, stdlib only, mock mode, temp dirs only.

Run: cd prototypes/pulse && python3 pulse_test.py
Google libraries are blocked and sockets raise, so any accidental network or Google import fails loudly.
"""
import sys

# Block Google libraries before anything can import them (FR-5, NFR-1).
for _name in ("google", "google.auth", "google.oauth2", "google.oauth2.service_account",
              "googleapiclient", "googleapiclient.discovery", "googleapiclient.errors"):
    sys.modules[_name] = None

import socket  # noqa: E402


class _NoSocket:
    def __init__(self, *a, **k):
        raise RuntimeError("network disabled in pulse_test.py")


socket.socket = _NoSocket
socket.create_connection = _NoSocket

import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config  # noqa: E402
import errors  # noqa: E402
from errors import PulseError, TransientError, HistoryExpired  # noqa: E402


class BaseCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"
        self.state = self.tmp / "state"
        self.home = self.tmp / "home"
        for d in (self.out, self.state, self.home):
            d.mkdir()
        self.env_file = self.tmp / ".env"
        self.env_file.write_text("", encoding="utf-8")

    def tearDown(self):
        # Restore write permission so cleanup works after read-only tests.
        for root, dirs, _files in os.walk(self.tmp):
            for d in dirs:
                p = os.path.join(root, d)
                if not os.path.islink(p):
                    os.chmod(p, 0o700)
        self._tmp.cleanup()

    def env(self, mock=True, **extra):
        e = {"HOME": str(self.home), "PULSE_OUT_DIR": str(self.out), "PULSE_STATE_DIR": str(self.state)}
        if mock:
            e["PULSE_MOCK"] = "1"
        e.update(extra)
        return e


# ---------------------------------------------------------------- T2: config and error mappers
class ConfigTests(BaseCase):
    def test_config_shell_wins(self):  # AC-3
        self.env_file.write_text("PULSE_DOMAIN=a.test\n", encoding="utf-8")
        cfg = config.load(self.env(mock=False, PULSE_DOMAIN="b.test"), self.env_file, need_live_keys=False)
        self.assertEqual(cfg.domain, "b.test")
        cfg = config.load(self.env(mock=False, PULSE_DOMAIN=""), self.env_file, need_live_keys=False)
        self.assertEqual(cfg.domain, "a.test")

    def test_env_file_quotes_comments(self):
        self.env_file.write_text('# c\n\nPULSE_DOMAIN="q.test"\nPULSE_RETENTION_DAYS=\'7\'\n', encoding="utf-8")
        cfg = config.load(self.env(mock=False), self.env_file, need_live_keys=False)
        self.assertEqual(cfg.domain, "q.test")
        self.assertEqual(cfg.retention_days, 7)

    def test_mock_value_invalid(self):
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(PULSE_MOCK="yes"), self.env_file, need_live_keys=True)
        self.assertEqual(cm.exception.code, "config_invalid")
        self.assertIn("PULSE_MOCK", cm.exception.message)

    def test_retention_bounds(self):
        for bad in ("0", "3651", "x"):
            with self.assertRaises(PulseError) as cm:
                config.load(self.env(PULSE_RETENTION_DAYS=bad), self.env_file, need_live_keys=True)
            self.assertEqual(cm.exception.code, "config_invalid")
        for good in ("1", "3650"):
            cfg = config.load(self.env(PULSE_RETENTION_DAYS=good), self.env_file, need_live_keys=True)
            self.assertEqual(cfg.retention_days, int(good))

    def test_live_missing_key_config_missing(self):  # AC-4 (config part)
        secret_like = "placeholder-domain-value.test"
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(mock=False, PULSE_DOMAIN=secret_like, PULSE_ALLOWLIST="/x"),
                        self.env_file, need_live_keys=True)
        self.assertEqual(cm.exception.code, "config_missing")
        self.assertEqual(cm.exception.exit_code, 2)
        self.assertIn("PULSE_SA_KEY_PATH", cm.exception.message)
        self.assertNotIn(secret_like, cm.exception.message)

    def test_mock_ignores_live_values(self):  # AC-4 (config part), R-2
        cfg = config.load(self.env(PULSE_DOMAIN="realcompany.example", PULSE_SA_KEY_PATH="",
                                   PULSE_ALLOWLIST="/nope"), self.env_file, need_live_keys=True)
        self.assertTrue(cfg.mock)
        self.assertEqual(cfg.domain, "example.test")
        self.assertEqual(cfg.allowlist, config.FIXTURES / "allowlist.txt")
        self.assertIsNone(cfg.sa_key_path)

    def test_defaults_under_home(self):
        cfg = config.load({"HOME": str(self.home), "PULSE_MOCK": "1"}, self.env_file, need_live_keys=True)
        self.assertEqual(cfg.out_dir, self.home / ".sutra-pulse" / "out")
        self.assertEqual(cfg.state_dir, self.home / ".sutra-pulse" / "state")
        self.assertEqual(cfg.retention_days, 30)
        self.assertEqual(cfg.scenario, "default")

    def test_bad_domain(self):
        with self.assertRaises(PulseError) as cm:
            config.load(self.env(mock=False, PULSE_DOMAIN="a@b.test"), self.env_file, need_live_keys=False)
        self.assertEqual(cm.exception.code, "config_invalid")


class ErrorMapperTests(unittest.TestCase):
    def test_error_mapper(self):  # AC-13(c)
        self.assertEqual(errors.map_refresh_error(
            "('unauthorized_client: Client is unauthorized to retrieve access tokens', {})").code,
            "unauthorized_client")
        self.assertEqual(errors.map_refresh_error("invalid_grant: Invalid email or User ID").code, "invalid_grant")
        self.assertEqual(errors.map_refresh_error("something else").code, "unauthorized_client")
        e = errors.map_http_error(403, "accessNotConfigured")
        self.assertEqual((e.code, e.exit_code), ("access_denied", 4))
        self.assertIn("Enable the Gmail API", e.message)
        self.assertIsInstance(errors.map_http_error(404, "notFound"), HistoryExpired)
        for s in (429, 500, 503, 599):
            t = errors.map_http_error(s, "")
            self.assertIsInstance(t, TransientError)
            self.assertEqual(t.status, s)
        e = errors.map_http_error(418, "teapot")
        self.assertEqual(e.code, "internal")
        self.assertIn("418", e.message)
        self.assertIn("Domain-wide delegation", errors.map_refresh_error("unauthorized_client").message)

    def test_exit_table(self):
        self.assertEqual({errors.EXIT[c] for c in ("rate_limited", "server_error")}, {5})
        with self.assertRaises(ValueError):
            PulseError("nope", "x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
