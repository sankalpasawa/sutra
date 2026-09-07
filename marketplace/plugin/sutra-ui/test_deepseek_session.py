"""test_deepseek_session.py -- the one-time pairing code, and what it authorises.

WHAT IS ACTUALLY AT RISK HERE
-----------------------------
This module widened a credential-WRITE surface. Before it, POST
/api/providers/deepseek/key was reachable only with a token the Electron main
process held; now a browser can earn one. Every property that makes that safe
is a property of this module, so each one is pinned below:

  - no code at all when SUTRA_DESKTOP_TOKEN is set (no second door on a
    desktop-started backend)
  - the code never appears in state(), which rides in the UNAUTHENTICATED
    GET /api/settings
  - single use: the second exchange of a correct code fails
  - a wrong code does NOT burn the right one (a typo must be retryable)
  - verify() refuses everything on an unpaired process, `None` and "" included
  - the token is not derivable from the code, and neither is persisted

Run: python3 -m pytest test_deepseek_session.py   (or python3 test_deepseek_session.py)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deepseek_session as ds  # noqa: E402


class _Base(unittest.TestCase):
    """Every test starts from a process that has never armed.

    The module holds its code and token in globals ON PURPOSE -- nothing is
    persisted, so "expires with the process" needs no expiry code -- which
    means the reset has to be explicit here.
    """

    def setUp(self):
        self._prev_env = os.environ.get("SUTRA_DESKTOP_TOKEN")
        os.environ.pop("SUTRA_DESKTOP_TOKEN", None)
        ds._reset_for_tests()

    def tearDown(self):
        ds._reset_for_tests()
        if self._prev_env is None:
            os.environ.pop("SUTRA_DESKTOP_TOKEN", None)
        else:
            os.environ["SUTRA_DESKTOP_TOKEN"] = self._prev_env


class TestArming(_Base):

    def test_a_cli_run_server_mints_and_prints_a_code(self):
        shown = ds.arm()
        self.assertTrue(shown)
        self.assertRegex(shown, r"^[0-9A-Z]{4}(-[0-9A-Z]{4}){3}$")
        self.assertTrue(ds.state()["available"])

    def test_the_desktop_shell_gets_no_second_door(self):
        """The whole safety argument for lane 2 is that it exists only where
        lane 1 does not. A desktop-started backend must mint nothing."""
        os.environ["SUTRA_DESKTOP_TOKEN"] = "shell-token"
        self.assertIsNone(ds.arm())
        self.assertEqual(ds.banner(), [])
        st = ds.state()
        self.assertFalse(st["available"])
        self.assertIn("desktop app", st["reason"])

    def test_arming_twice_does_not_mint_a_second_code(self):
        """A double startup hook, or an app.py that grows a second caller, must
        not turn a single-use code into two."""
        first = ds.arm()
        self.assertIsNone(ds.arm())
        self.assertEqual(ds.display(ds._code), first)

    def test_the_banner_carries_the_code_and_says_what_it_is_for(self):
        shown = ds.arm()
        text = "\n".join(ds.banner())
        self.assertIn(shown, text)
        self.assertIn("DeepSeek", text)
        self.assertIn("Single use", text)

    def test_the_banner_is_ascii_only(self):
        """stdout here can be a cp1252 console or a pipe Python typed as ascii.
        A box-drawing character would be a UnicodeEncodeError during startup --
        losing the server to decoration."""
        ds.arm()
        "\n".join(ds.banner()).encode("ascii")

    def test_printing_survives_a_stdout_that_refuses(self):
        class Broken(object):
            def write(self, _):
                raise IOError("closed")

            def flush(self):
                pass

        ds.arm()
        self.assertFalse(ds.print_banner(Broken()))

    def test_printing_reports_false_when_there_is_nothing_to_print(self):
        os.environ["SUTRA_DESKTOP_TOKEN"] = "shell-token"
        ds.arm()

        class Sink(object):
            def __init__(self):
                self.text = ""

            def write(self, s):
                self.text += s

            def flush(self):
                pass

        sink = Sink()
        self.assertFalse(ds.print_banner(sink))
        self.assertEqual(sink.text, "")


class TestStateLeaks(_Base):
    """state() is folded into GET /api/settings, which is unauthenticated."""

    def test_the_code_is_never_in_the_state_the_panel_reads(self):
        shown = ds.arm()
        st = ds.state()
        self.assertNotIn(shown, repr(st))
        self.assertNotIn(shown.replace("-", ""), repr(st))

    def test_the_token_is_never_in_the_state_either(self):
        ds.arm()
        token = ds.exchange(ds.display(ds._code))
        self.assertNotIn(token, repr(ds.state()))

    def test_state_says_which_of_three_situations_this_is(self):
        """"paste the code", "restart for a new one" and "use the app" are three
        different instructions, and giving the wrong one is what made the
        browser field read as a missing feature."""
        never = ds.state()
        self.assertFalse(never["available"])
        self.assertFalse(never["claimed"])
        self.assertIn("no sign-in code", never["reason"])

        ds.arm()
        self.assertEqual(ds.state(),
                         {"available": True, "claimed": False, "reason": None})

        ds.exchange(ds.display(ds._code))
        spent = ds.state()
        self.assertFalse(spent["available"])
        self.assertTrue(spent["claimed"])
        self.assertIn("Restart the server", spent["reason"])


class TestExchange(_Base):

    def _code(self):
        ds.arm()
        return ds.display(ds._code)

    def test_the_right_code_yields_a_token_that_verifies(self):
        token = ds.exchange(self._code())
        self.assertTrue(token)
        self.assertTrue(ds.verify(token))

    def test_the_code_is_single_use(self):
        code = self._code()
        ds.exchange(code)
        with self.assertRaises(ds.SessionCodeError) as caught:
            ds.exchange(code)
        self.assertEqual(caught.exception.code, "CLAIMED")

    def test_a_second_exchange_does_not_invalidate_the_first_token(self):
        """A stale tab retrying its paste must not sign the paired one out."""
        code = self._code()
        token = ds.exchange(code)
        try:
            ds.exchange(code)
        except ds.SessionCodeError:
            pass
        self.assertTrue(ds.verify(token))

    def test_a_wrong_code_does_not_burn_the_right_one(self):
        """A typo has to be retryable, or the forgiving read-back in
        _canonical() would be pointless and every fat-fingered paste would
        cost a server restart."""
        code = self._code()
        for guess in ("ZZZZ-ZZZZ-ZZZZ-ZZZZ", "nope", "", None, 7, code[:-1]):
            with self.assertRaises(ds.SessionCodeError):
                ds.exchange(guess)
        self.assertTrue(ds.verify(ds.exchange(code)))

    def test_the_refusal_never_quotes_the_submitted_value_back(self):
        self._code()
        secret_ish = "MYSECRETPASTE"
        with self.assertRaises(ds.SessionCodeError) as caught:
            ds.exchange(secret_ish)
        self.assertNotIn(secret_ish, str(caught.exception))

    def test_the_code_reads_back_forgivingly(self):
        """It gets read off a terminal, so dashes, case, surrounding
        whitespace and the Crockford I/L->1, O->0 confusions all have to land
        on the same code."""
        code = self._code()
        flat = code.replace("-", "")
        for variant in (code, flat, code.lower(), " " + code + "\n",
                        flat.replace("0", "O").replace("1", "l"),
                        "-".join([flat[:8], flat[8:]])):
            ds._code = flat          # re-arm without minting: same code, unclaimed
            ds._claimed = False
            self.assertTrue(ds.exchange(variant), variant)

    def test_a_desktop_started_server_refuses_to_exchange_anything(self):
        os.environ["SUTRA_DESKTOP_TOKEN"] = "shell-token"
        with self.assertRaises(ds.SessionCodeError) as caught:
            ds.exchange("ZZZZ-ZZZZ-ZZZZ-ZZZZ")
        self.assertEqual(caught.exception.code, "NOT_OFFERED")

    def test_the_code_carries_real_entropy(self):
        """80 bits is what lets this route go without an attempt cap. If the
        alphabet or the length ever shrinks, the no-cap decision in the module
        docstring stops being true and this fails."""
        self.assertEqual(len(ds._ALPHABET), 32)
        self.assertEqual(ds._GROUPS * ds._GROUP_LEN, 16)
        self.assertEqual(len(set(ds._ALPHABET)), 32, "a repeated symbol is lost entropy")
        for ambiguous in "ILOU":
            self.assertNotIn(ambiguous, ds._ALPHABET, "unreadable off a terminal")
        # 200 draws, no repeats: a mint that ever returned a constant would
        # otherwise pass every other test in this file.
        self.assertEqual(len({ds._mint_code() for _ in range(200)}), 200)

    def test_the_token_is_not_derivable_from_the_code(self):
        code = self._code()
        token = ds.exchange(code)
        self.assertNotIn(code.replace("-", ""), token)
        self.assertGreaterEqual(len(token), 32)


class TestVerify(_Base):

    def test_an_unpaired_process_verifies_nothing(self):
        """Including the falsy values, because `compare_digest(None, None)`
        raises rather than answering, and an empty header must be a plain no."""
        ds.arm()
        for value in (None, "", "anything", 0, b"bytes"):
            self.assertFalse(ds.verify(value))

    def test_a_wrong_token_is_refused_after_pairing(self):
        ds.arm()
        token = ds.exchange(ds.display(ds._code))
        self.assertFalse(ds.verify(token[:-1]))
        self.assertFalse(ds.verify(token + "x"))
        self.assertFalse(ds.verify("x" * len(token)))
        self.assertTrue(ds.verify(token))

    def test_nothing_is_written_to_disk(self):
        """"Expires with the server process" is implemented as "there is
        nowhere for it to survive". A file here would need an expiry policy
        this module does not have."""
        import inspect
        source = inspect.getsource(ds)
        for forbidden in ("open(", "Path(", "json.dump", "os.environ["):
            self.assertNotIn(forbidden, source,
                             "the pairing code must not reach a file or the env")


if __name__ == "__main__":
    unittest.main()
