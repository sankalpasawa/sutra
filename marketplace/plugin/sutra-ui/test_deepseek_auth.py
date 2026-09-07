"""DeepSeek sign-in: the key, where it comes from, and what must never leak.

Three failures these tests exist to prevent, all of them shipped-bug shaped:

  1. A key saved while SUTRA_UI_DEEPSEEK_API_KEY or DEEPSEEK_API_KEY is set.
     It would never be used, the row would say "signed in", and nothing on
     screen would explain why the old key was still answering.

  2. A key that appears saved and is not. Either because the keychain was
     unavailable and something fell back to an in-process dict, or because the
     mask in settings.json outlived the keychain item. Both draw a
     "Ready to use" row over a provider that cannot answer a message -- the
     exact failure providers.py's readiness gate exists to stop.

  3. The key in a message. A rejected key is the likely failure here, and the
     natural way to report it is to echo what the transport said. Every refusal
     below is built from fixed strings and a status code.

NOTHING HERE TOUCHES THE REAL KEYCHAIN. `_store` is patched to a memory store
in every test that writes -- which is legitimate in a TEST (it proves the
interface) and is precisely what deepseek_auth refuses to do in a running app.

NO KEY IN THIS FILE IS REAL, and the stand-in is ASSEMBLED at import rather
than written out, so no source line in this repo is ever key-shaped (PROTO-004
blocks the Write otherwise, correctly).
"""
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import deepseek_auth
import providers

#: Long enough to mask, shaped enough to exercise the sk- branch, and visibly
#: not a credential.
FAKE_KEY = "sk-" + "-".join(["notreal"] * 3) + "4f2a"
FAKE_MASK = "sk-****4f2a"
#: A second one, for "the other variable is set to something else".
OTHER_KEY = "sk-" + "-".join(["alsofake"] * 3) + "9911"


class _Memory:
    """The connectors MemoryCredentialStore's three verbs, without the import."""

    def __init__(self, items=None):
        self.items = dict(items or {})

    def put_secret(self, key, secret):
        self.items[key] = secret

    def get_secret(self, key):
        from connectors.credentials import CredentialNotFound
        try:
            return self.items[key]
        except KeyError:
            raise CredentialNotFound(key)

    def delete_secret(self, key):
        self.items.pop(key, None)


class _Base(unittest.TestCase):
    """A settings file of our own and a clean environment, restored after."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)
        self._orig = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.path)
        self._saved_env = {v: os.environ.pop(v, None)
                           for v in providers.DEEPSEEK_KEY_ENVS}
        self.addCleanup(self._restore)

    def _restore(self):
        providers.SETTINGS_PATH = self._orig
        for var, was in self._saved_env.items():
            if was is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = was
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _patch(self, *args, **kwargs):
        p = mock.patch.object(*args, **kwargs)
        started = p.start()
        self.addCleanup(p.stop)
        return started

    def store(self, items=None):
        """Patch in a memory store that reports itself available."""
        mem = _Memory(items)
        self._patch(deepseek_auth, "_store", return_value=mem)
        self._patch(deepseek_auth, "store_status", return_value=(True, None))
        return mem

    def ok_probe(self):
        return self._patch(deepseek_auth, "validate", return_value=None)


# ------------------------------------------------------------------- mask ----

class MaskShowsFourCharacters(unittest.TestCase):
    def test_the_last_four_and_the_prefix(self):
        self.assertEqual(deepseek_auth.mask(FAKE_KEY), FAKE_MASK)

    def test_a_key_without_the_sk_prefix_does_not_get_one_invented(self):
        self.assertEqual(deepseek_auth.mask("abcdefghijklmnop"), "****mnop")

    def test_a_short_string_reveals_nothing(self):
        """Below the floor the "last four" IS most of the value."""
        self.assertEqual(deepseek_auth.mask("sk-abc12"), "****")

    def test_trailing_whitespace_does_not_shift_the_visible_characters(self):
        self.assertEqual(deepseek_auth.mask(FAKE_KEY + "\n"), FAKE_MASK)

    def test_the_mask_is_not_the_key(self):
        self.assertNotIn(FAKE_KEY, deepseek_auth.mask(FAKE_KEY))
        self.assertLess(len(deepseek_auth.mask(FAKE_KEY)), len(FAKE_KEY))

    def test_none_and_empty_do_not_raise(self):
        self.assertEqual(deepseek_auth.mask(None), "****")
        self.assertEqual(deepseek_auth.mask(""), "****")


# ------------------------------------------------------------ resolution ----

class PrecedenceIsEnvThenEnvThenKeychain(_Base):
    def test_the_sutra_variable_wins(self):
        self.store({deepseek_auth.KEYCHAIN_ACCOUNT: "stored"})
        os.environ["DEEPSEEK_API_KEY"] = OTHER_KEY
        os.environ["SUTRA_UI_DEEPSEEK_API_KEY"] = FAKE_KEY
        self.assertEqual(providers.deepseek_api_key(), FAKE_KEY)
        self.assertEqual(providers.deepseek_env_var(), "SUTRA_UI_DEEPSEEK_API_KEY")

    def test_the_vendor_variable_wins_over_the_keychain(self):
        """It is what app.py and deepseek_usage.py have always read. Dropping it
        would sign out every machine that works today."""
        self.store({deepseek_auth.KEYCHAIN_ACCOUNT: "stored"})
        os.environ["DEEPSEEK_API_KEY"] = OTHER_KEY
        self.assertEqual(providers.deepseek_api_key(), OTHER_KEY)

    def test_the_keychain_is_used_when_no_variable_is_set(self):
        self.store({deepseek_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.assertEqual(providers.deepseek_api_key(), FAKE_KEY)
        self.assertIsNone(providers.deepseek_env_var())

    def test_nothing_anywhere_is_none_with_a_reason(self):
        self.store()
        key, why = providers.deepseek_key_for_request()
        self.assertIsNone(key)
        for var in providers.DEEPSEEK_KEY_ENVS:
            self.assertIn(var, why)
        self.assertIn(deepseek_auth.KEYCHAIN_SERVICE, why)
        self.assertIn(deepseek_auth.KEYCHAIN_ACCOUNT, why)

    def test_the_reading_path_may_say_the_keychain_was_empty(self):
        """This resolver DID open the keychain (via deepseek_auth.read), so
        unlike the render path it is entitled to report what was in it."""
        self.store()
        _, why = providers.deepseek_key_for_request()
        self.assertIn("keychain holds no item", why)

    def test_an_empty_variable_is_not_a_key(self):
        """An exported-but-blank variable is how a shell profile looks after
        someone deletes the value. It must not win, and must not read as set."""
        self.store({deepseek_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        os.environ["DEEPSEEK_API_KEY"] = "   "
        self.assertIsNone(providers.deepseek_env_var())
        self.assertEqual(providers.deepseek_api_key(), FAKE_KEY)

    def test_a_variable_with_a_trailing_newline_is_trimmed(self):
        os.environ["DEEPSEEK_API_KEY"] = FAKE_KEY + "\n"
        self.assertEqual(providers.deepseek_api_key(), FAKE_KEY)

    def test_the_resolver_never_raises_when_the_store_explodes(self):
        self._patch(deepseek_auth, "_store", side_effect=RuntimeError("on fire"))
        self.assertIsNone(providers.deepseek_api_key())

    def test_a_key_is_resolved_per_call_not_cached(self):
        """Signing in has to take effect on the next message, not the next
        restart -- that is the whole product change."""
        mem = self.store()
        self.assertIsNone(providers.deepseek_api_key())
        mem.items[deepseek_auth.KEYCHAIN_ACCOUNT] = FAKE_KEY
        self.assertEqual(providers.deepseek_api_key(), FAKE_KEY)


class AStaleMarkerCorrectsItself(_Base):
    """Someone deletes the item in Keychain Access. The marker in settings.json
    knows nothing about it, so the row would keep saying "signed in" and every
    chat would fail at connect with no explanation on screen."""

    def setUp(self):
        super().setUp()
        mem = self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        mem.items.clear()                      # the item is gone; the marker is not

    def test_the_reason_names_the_item_that_is_missing(self):
        key, why = providers.deepseek_key_for_request()
        self.assertIsNone(key)
        self.assertIn(deepseek_auth.KEYCHAIN_SERVICE, why)
        self.assertIn(deepseek_auth.KEYCHAIN_ACCOUNT, why)
        self.assertIn(FAKE_MASK, why)

    def test_the_marker_is_dropped_so_the_row_flips_back(self):
        self.assertTrue(deepseek_auth.marker())
        providers.deepseek_key_for_request()
        self.assertFalse(deepseek_auth.marker())
        self.assertFalse(providers._deepseek_key_present())


# ----------------------------------------------------------------- input ----

class PastesAreCleanedOrRefused(unittest.TestCase):
    def test_a_trailing_newline_is_trimmed(self):
        """People paste with one. Stored with it, the key is a 401 nobody can
        see the cause of."""
        self.assertEqual(deepseek_auth.clean(FAKE_KEY + "\n"), FAKE_KEY)

    def test_surrounding_spaces_are_trimmed(self):
        self.assertEqual(deepseek_auth.clean("  " + FAKE_KEY + "  "), FAKE_KEY)

    def test_internal_whitespace_is_refused_not_stripped(self):
        """It means a broken paste or two keys. Which characters to keep is not
        a decision this code should make on the operator's behalf."""
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.clean(FAKE_KEY[:10] + " " + FAKE_KEY[10:])
        self.assertEqual(caught.exception.code, "BAD_PASTE")

    def test_two_keys_on_two_lines_are_refused(self):
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.clean(FAKE_KEY + "\n" + OTHER_KEY)
        self.assertEqual(caught.exception.code, "BAD_PASTE")

    def test_empty_is_refused(self):
        for value in ("", "   ", None, 7):
            with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
                deepseek_auth.clean(value)
            self.assertEqual(caught.exception.code, "NO_KEY")

    def test_a_pasted_file_is_refused(self):
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.clean("x" * (deepseek_auth.MAX_KEY_LEN + 1))
        self.assertEqual(caught.exception.code, "TOO_LONG")

    def test_no_refusal_quotes_the_key_back(self):
        for value in (FAKE_KEY[:10] + " " + FAKE_KEY[10:],
                      FAKE_KEY + "x" * deepseek_auth.MAX_KEY_LEN):
            with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
                deepseek_auth.clean(value)
            self.assertNotIn(value.strip(), str(caught.exception))
            self.assertNotIn("4f2a", str(caught.exception))


# ------------------------------------------------------------- validation ----

def _http(status):
    return urllib.error.HTTPError(deepseek_auth.MODELS_URL, status, "", None, None)


class ProbeFailuresAreToldApart(unittest.TestCase):
    """"It did not work" is not actionable. A rejected key, an unreachable
    network and a billing problem need three different next steps."""

    def _fail(self, exc):
        with mock.patch.object(deepseek_auth.urllib.request, "urlopen",
                               side_effect=exc):
            with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
                deepseek_auth.validate(FAKE_KEY)
        return caught.exception.code, str(caught.exception)

    def test_401_is_a_rejected_key(self):
        code, message = self._fail(_http(401))
        self.assertEqual(code, "KEY_REJECTED")
        self.assertIn("rejected", message)

    def test_402_is_billing_not_a_bad_key(self):
        self.assertEqual(self._fail(_http(402))[0], "BILLING")

    def test_429_says_the_key_is_unconfirmed_rather_than_wrong(self):
        code, message = self._fail(_http(429))
        self.assertEqual(code, "RATE_LIMITED")
        self.assertIn("could not be confirmed", message)

    def test_a_network_failure_is_not_a_rejected_key(self):
        code, message = self._fail(urllib.error.URLError(OSError("no route")))
        self.assertEqual(code, "NETWORK")
        self.assertIn("api.deepseek.com", message)

    def test_a_timeout_is_a_network_failure(self):
        self.assertEqual(self._fail(TimeoutError())[0], "NETWORK")

    def test_a_404_blames_this_build_not_the_operator(self):
        """The endpoint is documented but was never confirmed live from here. If
        it moves, the failure must name itself rather than telling someone their
        working key is bad."""
        code, message = self._fail(_http(404))
        self.assertEqual(code, "PROBE_UNRECOGNISED")
        self.assertIn("not a problem with your key", message)

    def test_an_unknown_status_says_nothing_was_saved(self):
        code, message = self._fail(_http(500))
        self.assertEqual(code, "HTTP")
        self.assertIn("not saved", message)

    def test_no_classified_message_can_carry_the_key(self):
        """The natural implementation interpolates the exception, and on this
        path the request carries the key in an Authorization header."""
        for exc in (_http(401), _http(500),
                    urllib.error.URLError(OSError("Bearer " + FAKE_KEY)),
                    RuntimeError(FAKE_KEY)):
            _, message = self._fail(exc)
            self.assertNotIn(FAKE_KEY, message)
            self.assertNotIn("4f2a", message)

    def test_a_2xx_is_success(self):
        resp = mock.MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: False
        with mock.patch.object(deepseek_auth.urllib.request, "urlopen",
                               return_value=resp):
            self.assertIsNone(deepseek_auth.validate(FAKE_KEY))

    def test_the_key_goes_in_a_header_and_not_the_url(self):
        """A key in a query string lands in every proxy and server log between
        here and DeepSeek."""
        seen = {}

        def capture(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            raise _http(401)

        with mock.patch.object(deepseek_auth.urllib.request, "urlopen",
                               side_effect=capture):
            with self.assertRaises(deepseek_auth.DeepSeekAuthError):
                deepseek_auth.validate(FAKE_KEY)
        self.assertNotIn(FAKE_KEY, seen["url"])
        self.assertEqual(seen["auth"], "Bearer " + FAKE_KEY)


# ------------------------------------------------------------------ save ----

class SaveRefusesBeforeItStores(_Base):
    def test_an_env_override_is_refused_and_nothing_is_written(self):
        """The whole point of naming the variable: a key saved under a live
        override would never be used and nothing would say so."""
        mem = self.store()
        self.ok_probe()
        os.environ["DEEPSEEK_API_KEY"] = OTHER_KEY
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.save(FAKE_KEY)
        self.assertEqual(caught.exception.code, "ENV_OVERRIDE")
        self.assertIn("DEEPSEEK_API_KEY", str(caught.exception))
        self.assertEqual(mem.items, {})
        self.assertFalse(deepseek_auth.marker())

    def test_no_keychain_means_refused_and_never_a_memory_store(self):
        """connectors_api degrades to MemoryCredentialStore with a warning. Here
        that would hold the key until the backend restarts while the mask
        outlived it -- a row claiming "signed in" with nothing behind it."""
        self._patch(deepseek_auth, "store_status",
                    return_value=(False, "no keychain on this box"))
        sent = self._patch(deepseek_auth, "validate")
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.save(FAKE_KEY)
        self.assertEqual(caught.exception.code, "NO_KEYCHAIN")
        self.assertFalse(deepseek_auth.marker())
        sent.assert_not_called()      # a box that cannot store must not transmit

    def test_a_rejected_key_is_not_stored(self):
        mem = self.store()
        self._patch(deepseek_auth, "validate",
                    side_effect=deepseek_auth.DeepSeekAuthError(
                        "KEY_REJECTED", "DeepSeek rejected that key."))
        with self.assertRaises(deepseek_auth.DeepSeekAuthError):
            deepseek_auth.save(FAKE_KEY)
        self.assertEqual(mem.items, {})
        self.assertFalse(deepseek_auth.marker())

    def test_a_store_that_fails_leaves_no_marker(self):
        mem = self.store()
        mem.put_secret = mock.Mock(side_effect=OSError("locked"))
        self.ok_probe()
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.save(FAKE_KEY)
        self.assertEqual(caught.exception.code, "STORE_FAILED")
        self.assertFalse(deepseek_auth.marker())

    def test_the_probe_sees_the_trimmed_key_not_the_paste(self):
        self.store()
        sent = self.ok_probe()
        deepseek_auth.save("  " + FAKE_KEY + "\n")
        sent.assert_called_once_with(FAKE_KEY)

    def test_a_good_key_is_stored_trimmed_and_marked(self):
        mem = self.store()
        self.ok_probe()
        out = deepseek_auth.save("  " + FAKE_KEY + "\n")
        self.assertEqual(mem.items[deepseek_auth.KEYCHAIN_ACCOUNT], FAKE_KEY)
        self.assertEqual(out["mask"], FAKE_MASK)
        self.assertEqual(deepseek_auth.marker()["mask"], FAKE_MASK)
        self.assertIsInstance(deepseek_auth.marker()["saved_at"], float)


class TheSettingsFileHoldsNoKey(_Base):
    def test_only_a_mask_and_a_timestamp_are_written(self):
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        text = Path(self.path).read_text()
        self.assertNotIn(FAKE_KEY, text)
        self.assertIn(FAKE_MASK, text)
        self.assertEqual(set(providers._raw_settings()[deepseek_auth.SETTINGS_KEY]),
                         {"mask", "saved_at"})

    def test_the_file_is_not_readable_by_anyone_else(self):
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_a_junk_marker_is_not_a_signed_in_state(self):
        """A hand-edited or half-written file must not read as a saved key."""
        for junk in ("yes", {}, {"mask": ""}, {"mask": None}, {"saved_at": 1}, 5):
            providers._write_settings({deepseek_auth.SETTINGS_KEY: junk})
            self.assertEqual(deepseek_auth.marker(), {})
            self.assertFalse(providers._deepseek_key_present())

    def test_saving_leaves_the_rest_of_the_file_alone(self):
        providers._write_settings({"workdir": "/tmp/somewhere",
                                   "permission_mode": "plan"})
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        raw = providers._raw_settings()
        self.assertEqual(raw["workdir"], "/tmp/somewhere")
        self.assertEqual(raw["permission_mode"], "plan")


# ---------------------------------------------------------------- remove ----

class RemoveIsIdempotent(_Base):
    def test_the_key_and_the_marker_both_go(self):
        mem = self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        self.assertEqual(deepseek_auth.remove(), {"removed": True})
        self.assertEqual(mem.items, {})
        self.assertFalse(deepseek_auth.marker())

    def test_removing_nothing_succeeds(self):
        """Signing out of a machine that holds nothing is not an error."""
        self.store()
        self.assertEqual(deepseek_auth.remove(), {"removed": False})

    def test_a_failed_delete_keeps_the_marker(self):
        """If the marker went first and the delete then failed, a live key would
        be left in the keychain with nothing on record pointing at it."""
        mem = self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        mem.delete_secret = mock.Mock(side_effect=OSError("locked"))
        with self.assertRaises(deepseek_auth.DeepSeekAuthError) as caught:
            deepseek_auth.remove()
        self.assertEqual(caught.exception.code, "STORE_FAILED")
        self.assertTrue(deepseek_auth.marker())


# ------------------------------------------------------------------ state ----

class TheRowStateSaysWhichSourceWon(_Base):
    def test_an_env_key_names_the_variable_and_masks_it(self):
        self.store()
        os.environ["SUTRA_UI_DEEPSEEK_API_KEY"] = FAKE_KEY
        state = providers.deepseek_auth_state()
        self.assertEqual(state["state"], "env")
        self.assertTrue(state["signed_in"])
        self.assertEqual(state["env_var"], "SUTRA_UI_DEEPSEEK_API_KEY")
        self.assertEqual(state["mask"], FAKE_MASK)
        self.assertIsNone(state["reason"])

    def test_an_env_key_still_reports_the_stored_one_it_is_shadowing(self):
        """Otherwise unsetting the variable looks like it will sign you out,
        when there is a saved key waiting underneath."""
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        os.environ["DEEPSEEK_API_KEY"] = OTHER_KEY
        state = providers.deepseek_auth_state()
        self.assertEqual(state["state"], "env")
        self.assertEqual(state["stored_mask"], FAKE_MASK)

    def test_a_stored_key_reports_when_it_was_saved(self):
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        state = providers.deepseek_auth_state()
        self.assertEqual(state["state"], "stored")
        self.assertEqual(state["mask"], FAKE_MASK)
        self.assertIsInstance(state["saved_at"], float)

    def test_no_key_carries_the_reason_the_row_renders(self):
        self.store()
        state = providers.deepseek_auth_state()
        self.assertEqual(state["state"], "none")
        self.assertFalse(state["signed_in"])
        self.assertIn("no API key", state["reason"])
        self.assertIn(deepseek_auth.KEYCHAIN_SERVICE, state["reason"])

    def test_no_reason_anywhere_mentions_the_config_directory(self):
        """~/.deepseek is not what signed-in means. Nothing in the keychain
        sign-in path creates it or reads it, so no string may cite it."""
        self.store()
        _, request_reason = providers.deepseek_key_for_request()
        for text in (request_reason,
                     providers.deepseek_auth_state()["reason"],
                     providers._deepseek_reason("deepseek", None, False, False),
                     providers._deepseek_reason("deepseek", "/bin/deepseek",
                                                True, False)):
            self.assertNotIn(".deepseek", text)
            self.assertNotIn("config directory", text)

    def test_no_store_says_so_and_offers_the_variables_instead(self):
        """The row must not offer a control that cannot work on this machine."""
        self._patch(deepseek_auth, "store_status",
                    return_value=(False, "no keychain; set it in the environment."))
        state = providers.deepseek_auth_state()
        self.assertFalse(state["store_available"])
        self.assertIn("no keychain; set it in the environment.",
                      state["store_reason"])
        self.assertIn("no keychain; set it in the environment",
                      state["reason"])
        self.assertNotIn("Sign in on the DeepSeek row", state["reason"])
        # No point naming an item on a machine with nowhere to put it.
        self.assertNotIn(deepseek_auth.KEYCHAIN_SERVICE, state["reason"])
        # And no doubled stop: store_status()'s sentence already ends by
        # sending them to the environment, so no second tail is appended.
        self.assertNotIn("..", state["reason"])
        self.assertNotIn("instead. So:", state["reason"])

    def test_the_state_rides_INSIDE_the_settings_contract(self):
        """WHERE it lands is load-bearing, and the first version got it wrong.

        The row reads SETTINGS.deepseek_auth, and the panel sets
        `SETTINGS = r.settings` (07-loaders.js), so returning the state as a
        SIBLING of `settings` in the route response -- next to claude_account,
        which is where it first went -- meant nothing read it and the row
        rendered empty on a machine that had a key. The panel tests could not
        catch that: they inject the fixture directly. This one asserts the wire.
        """
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        got = providers.load_settings()
        self.assertIn("deepseek_auth", got)
        self.assertEqual(got["deepseek_auth"]["mask"], FAKE_MASK)
        self.assertEqual(got["deepseek_auth"]["state"], "stored")

    def test_the_settings_contract_never_carries_the_key(self):
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        os.environ["DEEPSEEK_API_KEY"] = FAKE_KEY
        self.assertNotIn(FAKE_KEY, repr(providers.load_settings()))

    def test_no_state_field_can_hold_a_key(self):
        self.store()
        self.ok_probe()
        deepseek_auth.save(FAKE_KEY)
        os.environ["DEEPSEEK_API_KEY"] = FAKE_KEY
        self.assertNotIn(FAKE_KEY, repr(providers.deepseek_auth_state()))


class SavedMessageTellsTheTruth(unittest.TestCase):
    """A key write that succeeded must not claim a provider that cannot run.

    THE SHIPPED BUG (founder report, screenshot 2026-09-07). The save handler
    ended its success message with "DeepSeek is selectable above now" for every
    successful write. A key is one of DeepSeek's TWO requirements -- the other
    is the CLI on PATH, because Sutra spawns `<bin> --acp` -- so on a Mac
    without it the panel printed that sentence directly beneath a row that
    correctly read "Not installed on this Mac". Sibling of failure 2 in this
    module's header: there the row lied about a key, here the message lied
    about the machine.

    org_api._deepseek_saved_message is the whole decision and it is pure, so
    these drive it with provider rows directly -- no keychain, no HTTP, no
    dependence on whether the DEV machine happens to have the CLI (it does,
    which is exactly why an end-to-end assertion here would pass while the
    reported bug stayed shipped).
    """

    ROW_MISSING_CLI = {
        "id": "deepseek", "installed": False, "configured": True,
        "runnable": False,
        "reason": "the 'deepseek' CLI is not on PATH (@sluisr/deepseek-cli).",
    }
    ROW_READY = {"id": "deepseek", "installed": True, "configured": True,
                 "runnable": True, "reason": None}

    def msg(self, rows):
        import org_api
        return org_api._deepseek_saved_message(FAKE_MASK, rows)

    def test_a_missing_cli_is_never_called_selectable(self):
        code, message = self.msg([self.ROW_READY | {"id": "claude"},
                                  self.ROW_MISSING_CLI])
        self.assertEqual(code, "SAVED_NO_CLI")
        self.assertNotIn("selectable above now", message)
        self.assertIn("still not selectable", message)

    def test_the_key_is_still_reported_as_saved(self):
        #: The write DID happen. Burying that would send the operator back to
        #: re-paste a key that is already in the keychain.
        _, message = self.msg([self.ROW_MISSING_CLI])
        self.assertIn("saved on this Mac", message)
        self.assertIn(FAKE_MASK, message)

    def test_the_row_s_own_reason_is_what_gets_quoted(self):
        #: One source for the requirement sentence. If providers.py rewords it,
        #: this message follows instead of drifting.
        _, message = self.msg([self.ROW_MISSING_CLI])
        self.assertIn(self.ROW_MISSING_CLI["reason"], message)

    def test_an_installed_cli_still_gets_the_no_restart_promise(self):
        code, message = self.msg([self.ROW_READY])
        self.assertEqual(code, "SAVED")
        self.assertIn("selectable above now -- no restart.", message)

    def test_a_reasonless_missing_row_still_refuses_to_promise(self):
        code, message = self.msg([self.ROW_MISSING_CLI | {"reason": None}])
        self.assertEqual(code, "SAVED_NO_CLI")
        self.assertNotIn("selectable above now", message)

    def test_no_deepseek_row_claims_nothing_either_way(self):
        #: Should be unreachable -- deepseek is catalogued. A row that went
        #: missing is still not evidence the CLI is present.
        code, message = self.msg([{"id": "claude", "installed": True}])
        self.assertEqual(code, "SAVED")
        self.assertNotIn("selectable", message)
        self.assertIn("saved on this Mac", message)

    def test_an_empty_provider_list_does_not_raise(self):
        for rows in ([], None):
            code, message = self.msg(rows)
            self.assertEqual(code, "SAVED")
            self.assertIn(FAKE_MASK, message)

    def test_the_message_never_carries_the_key(self):
        for rows in ([self.ROW_READY], [self.ROW_MISSING_CLI]):
            self.assertNotIn(FAKE_KEY, self.msg(rows)[1])


if __name__ == "__main__":
    unittest.main()
