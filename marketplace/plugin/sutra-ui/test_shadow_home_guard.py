"""test_shadow_home_guard.py -- tests can never write the live Shadow home.

Two layers, both pinned:
  1. conftest.py redirects SUTRA_SHADOW_HOME to a temp dir before collection
     and re-asserts it before every test (nineteen modules pop it at teardown).
  2. shadow_ledger.shadow_home() refuses the default home while pytest runs a
     test, unless SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1.

Test order matters for the re-assert case: test_1 pops the variable exactly
the way the offending teardowns do, and test_2 (alphabetically next) must
still see a temp home.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import shadow_ledger  # noqa: E402
import mission_engine  # noqa: E402

LIVE = os.path.realpath(os.path.expanduser(shadow_ledger.DEFAULT_HOME))


def _is_live(path):
    r = os.path.realpath(os.path.expanduser(path))
    return r == LIVE or r.startswith(LIVE + os.sep)


class ShadowHomeGuard(unittest.TestCase):
    """pytest-only: both layers under test exist only inside a pytest run
    (conftest.py + PYTEST_CURRENT_TEST). run-tests.sh executes files
    standalone, where each module binds its own home at import instead."""

    def setUp(self):
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self.skipTest("pytest-only (conftest redirect + PYTEST_CURRENT_TEST)")

    def test_0_conftest_redirected_the_home(self):
        home = os.environ.get("SUTRA_SHADOW_HOME", "")
        self.assertTrue(home, "conftest must set SUTRA_SHADOW_HOME before collection")
        self.assertFalse(_is_live(home), "the redirected home must not be the live one")
        self.assertFalse(_is_live(shadow_ledger.shadow_home()))
        self.assertFalse(_is_live(mission_engine._home()))

    def test_1_default_home_is_refused_under_pytest(self):
        self.assertTrue(os.environ.get("PYTEST_CURRENT_TEST"),
                        "pytest sets this while a test runs")
        with mock.patch.dict(os.environ):
            os.environ.pop("SUTRA_SHADOW_HOME", None)
            os.environ.pop("SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS", None)
            with self.assertRaises(RuntimeError):
                shadow_ledger.shadow_home()
            with self.assertRaises(RuntimeError):
                mission_engine._home()
            with self.assertRaises(RuntimeError):
                shadow_ledger._path("actions")
        # the offending pattern itself, left in place for test_2 to observe
        os.environ.pop("SUTRA_SHADOW_HOME", None)

    def test_2_a_popped_home_is_reasserted_before_the_next_test(self):
        home = os.environ.get("SUTRA_SHADOW_HOME", "")
        self.assertTrue(home, "conftest.pytest_runtest_setup must restore the temp home")
        self.assertFalse(_is_live(home))

    def test_3_override_names_a_deliberate_integration_test(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("SUTRA_SHADOW_HOME", None)
            os.environ["SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS"] = "1"
            self.assertTrue(_is_live(shadow_ledger.shadow_home()))


if __name__ == "__main__":
    unittest.main()
