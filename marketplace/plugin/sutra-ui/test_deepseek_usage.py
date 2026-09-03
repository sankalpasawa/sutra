"""test_deepseek_usage.py -- DeepSeek's balance card: what it reads, what it
refuses, same discipline as test_account.py pins for usage.py.

The property worth pinning is not the happy path -- it is that
DEEPSEEK_API_KEY never survives into anything a route would serialise, and
that every failure mode (no key, dead network, a shape this build does not
recognise) fails OPEN to {"available": false, "reason": ...} rather than
raising into a route or inventing a number.

Run: python -m pytest test_deepseek_usage.py -q
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import deepseek_usage  # noqa: E402

LIVE_PAYLOAD = {
    "is_available": True,
    "balance_infos": [
        {"currency": "USD", "total_balance": "1.87",
         "granted_balance": "0.00", "topped_up_balance": "5.00"},
    ],
}


class Sanitize(unittest.TestCase):
    def test_allow_lists_the_row_fields(self):
        out = deepseek_usage.sanitize(LIVE_PAYLOAD, "live")
        self.assertTrue(out["available"])
        self.assertEqual(out["source"], "live")
        self.assertIs(out["is_available"], True)
        self.assertEqual(out["balances"], [
            {"currency": "USD", "total_balance": "1.87",
             "granted_balance": "0.00", "topped_up_balance": "5.00"},
        ])

    def test_unknown_row_fields_do_not_reach_the_payload(self):
        """A key this module has not been taught to read must not leak into a
        route response just because the API started sending it."""
        d = {"is_available": True, "balance_infos": [
            {"currency": "USD", "total_balance": "1.87", "secret_internal_id": "acct-999"}]}
        out = deepseek_usage.sanitize(d, "live")
        self.assertNotIn("secret_internal_id", json.dumps(out))

    def test_malformed_rows_are_skipped_not_fatal(self):
        d = {"is_available": True, "balance_infos": [None, "oops", {"currency": "USD", "total_balance": "1"}]}
        out = deepseek_usage.sanitize(d, "live")
        self.assertEqual(out["balances"], [{"currency": "USD", "total_balance": "1"}])


class Fetch(unittest.TestCase):
    def test_no_key_fails_open(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEEPSEEK_API_KEY", None)
            d, err = deepseek_usage._fetch()
        self.assertIsNone(d)
        self.assertIn("DEEPSEEK_API_KEY", err)

    def test_key_never_appears_in_a_request_exception_message(self):
        """Regression shape: a request built with the key in a header must not
        leak it back out through an error path (e.g. a repr of the request)."""
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-super-secret-123"}), \
             mock.patch("deepseek_usage.urllib.request.urlopen", side_effect=OSError("boom")):
            d, err = deepseek_usage._fetch()
        self.assertIsNone(d)
        self.assertNotIn("sk-super-secret-123", err)

    def test_unrecognised_shape_is_not_cached_and_not_fatal(self):
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-x"}), \
             mock.patch("deepseek_usage.urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = json.dumps({"nope": True}).encode()
            d, err = deepseek_usage._fetch()
        self.assertIsNone(d)
        self.assertIn("shape", err)


class Snapshot(unittest.TestCase):
    def test_fails_open_with_no_cache_and_no_key(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(deepseek_usage, "CACHE", os.path.join(td, "cache.json")), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEEPSEEK_API_KEY", None)
            out = deepseek_usage.snapshot()
        self.assertFalse(out["available"])
        self.assertIn("DEEPSEEK_API_KEY", out["reason"])
        self.assertEqual(out["balances"], [])

    def test_live_fetch_is_sanitised_and_cached(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(deepseek_usage, "GUARD_DIR", td), \
             mock.patch.object(deepseek_usage, "CACHE", os.path.join(td, "cache.json")), \
             mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-x"}), \
             mock.patch("deepseek_usage.urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = json.dumps(LIVE_PAYLOAD).encode()
            out = deepseek_usage.snapshot()
            self.assertTrue(os.path.exists(deepseek_usage.CACHE))
        self.assertTrue(out["available"])
        self.assertEqual(out["source"], "live")
        self.assertEqual(out["balances"][0]["total_balance"], "1.87")

    def test_second_call_within_ttl_serves_cache_not_network(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(deepseek_usage, "GUARD_DIR", td), \
             mock.patch.object(deepseek_usage, "CACHE", os.path.join(td, "cache.json")), \
             mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-x"}), \
             mock.patch("deepseek_usage.urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = json.dumps(LIVE_PAYLOAD).encode()
            deepseek_usage.snapshot()
            out = deepseek_usage.snapshot()
        self.assertEqual(out["source"], "cache")
        self.assertEqual(m.call_count, 1)

    def test_network_down_falls_back_to_stale_cache(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(deepseek_usage, "GUARD_DIR", td), \
             mock.patch.object(deepseek_usage, "CACHE", os.path.join(td, "cache.json")), \
             mock.patch.object(deepseek_usage, "CACHE_TTL", 0.0), \
             mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-x"}), \
             mock.patch("deepseek_usage.urllib.request.urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = json.dumps(LIVE_PAYLOAD).encode()
            deepseek_usage.snapshot()          # populates the cache
            m.side_effect = OSError("network down")
            out = deepseek_usage.snapshot()    # TTL already 0 -> forces a fetch, which fails
        self.assertTrue(out["available"])
        self.assertEqual(out["source"], "stale-cache")

    def test_never_raises_on_a_broken_environment(self):
        """snapshot() is called from a route with a 'never 5xx' contract --
        an unexpected exception anywhere inside must still come back as a
        normal unavailable payload, not propagate."""
        with mock.patch.object(deepseek_usage, "_cached", side_effect=RuntimeError("disk exploded")):
            out = deepseek_usage.snapshot()
        self.assertFalse(out["available"])
        self.assertIn("reason", out)


if __name__ == "__main__":
    unittest.main()
