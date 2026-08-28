"""A keychain prompt must not be able to wedge the panel.

SecItemCopyMatching blocks while macOS shows "python3.12 wants to use your
confidential information stored in com.sutra.connector", and it takes no timeout
argument. Connector endpoints are synchronous `def`, so FastAPI runs each in a
threadpool worker and a blocked call holds that worker until somebody answers a
dialog that may be behind another window. An audit observed exactly that dialog
open on the operator's machine.

The call cannot be cancelled, so what is bounded is the WAIT.
"""

import platform
import sys
import time
import unittest

if platform.system() != "Darwin":                       # pragma: no cover
    raise unittest.SkipTest("macOS keychain adapter")

from connectors.credentials import keychain as kc


class _FakeSec(object):
    """Stands in for Security.framework. `delay` models an unanswered prompt."""

    def __init__(self, delay=0.0, status=0):
        self.delay = delay
        self.status = status
        self.calls = 0

    def SecItemCopyMatching(self, query, out):
        self.calls += 1
        time.sleep(self.delay)
        return self.status


class KeychainWaitIsBounded(unittest.TestCase):

    def _store(self, sec):
        store = kc.KeychainCredentialStore.__new__(kc.KeychainCredentialStore)
        store._sec = sec
        store._cf = None
        # the query builders are not exercised: _base_query/_cfdict are stubbed
        store._base_query = lambda key, owned: []
        store._cfdict = lambda pairs: object()
        store._release = lambda owned: None
        store._true = object()
        store._k = {"kSecReturnData": 1, "kSecMatchLimit": 2, "kSecMatchLimitOne": 3}
        return store

    def test_a_hung_read_gives_the_worker_back(self):
        slow = _FakeSec(delay=30.0)
        store = self._store(slow)
        t0 = time.time()
        with self.assertRaises(kc.KeychainTimeout) as cm:
            store.get_secret("anything")
        waited = time.time() - t0
        self.assertLess(waited, kc.GET_TIMEOUT_S + 2.0,
                        "the caller waited %.1fs -- the bound did not hold" % waited)
        self.assertGreaterEqual(waited, kc.GET_TIMEOUT_S - 0.5)

    def test_the_timeout_names_the_dialog(self):
        """An OSStatus number tells the operator nothing. The one thing they can
        act on is that a prompt is waiting for them."""
        store = self._store(_FakeSec(delay=30.0))
        with self.assertRaises(kc.KeychainTimeout) as cm:
            store.get_secret("anything")
        msg = str(cm.exception)
        self.assertIn("dialog", msg.lower())
        self.assertIn(kc.SERVICE_NAME, msg)

    def test_a_timeout_is_still_a_KeychainError(self):
        """Callers already handle KeychainError; a new sibling type must not
        escape their except clause."""
        self.assertTrue(issubclass(kc.KeychainTimeout, kc.KeychainError))

    def test_the_fast_path_is_not_slowed_down(self):
        """Reads that answer immediately must not pay for the guard."""
        quick = _FakeSec(delay=0.0, status=kc._ERR_ITEM_NOT_FOUND)
        store = self._store(quick)
        t0 = time.time()
        with self.assertRaises(kc.CredentialNotFound):
            store.get_secret("missing")
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual(quick.calls, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
