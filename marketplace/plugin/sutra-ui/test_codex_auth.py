"""Codex API-key memory: the toggle, and the lies it must not tell.

Four failures these tests exist to prevent. Three are shipped-bug shaped and
one is a design pressure that will only grow.

  1. "Your saved key is gone" when the keychain is merely LOCKED. This is the
     headline. deepseek_auth.read() collapses CredentialNotFound and
     KeychainError into one None, which is right there and wrong here: a toggle
     that says "no key saved" to someone whose keychain is locked sends them to
     re-enter a key they still have, or to conclude they have lost it.
     read_or_reason() is the split, and TheSplitThatMattersMost pins it.

  2. A saved key that outlives its own record, or a record that outlives the
     key. The marker lives in its OWN file because backend and sidecar are two
     processes and settings.json has one temp path for all writers -- the
     interleave is real, and TheMarkerHoldsNoKey proves the separation rather
     than asserting it in a comment.

  3. A success message that overstates what happened. Measured 2026-09-08
     against codex-cli 0.153.2: `codex login --with-api-key` does not validate.
     It accepted a deliberately fake key, exited 0, printed "Successfully logged
     in", and wiped a live ChatGPT session. So "saved" means STORED AND NOW
     LIVE, never "OpenAI accepts it".

  4. An automatic switch onto per-token billing. Sutra now HOLDS the key, which
     is what makes the shortcut available and exactly why it is forbidden.
     NoAutomaticFallback guards the source.

NOTHING HERE TOUCHES THE REAL KEYCHAIN OR THE REAL codex. `_store` is patched
to a memory store, and `codex` is a shell script on a temp PATH -- legitimate in
a TEST (it proves the interface) and precisely what codex_auth refuses to do in
a running app.

NO KEY IN THIS FILE IS REAL, and the stand-in is ASSEMBLED at import rather than
written out, so no source line in this repo is ever key-shaped (PROTO-004 blocks
the Write otherwise, correctly).
"""
import json
import os
import re
import stat
import urllib.error
import urllib.request
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import codex_auth
import codex_install
import providers

#: Long enough to mask, shaped enough to exercise the sk- branch, and visibly
#: not a credential.
FAKE_KEY = "sk-proj-" + "-".join(["notreal"] * 3) + "4f2a"
FAKE_MASK = "sk-****4f2a"
#: What codex prints for it. Its OWN shape, not ours -- the row prefers this.
CODEX_STUB = "sk-proj-***" + "4f2a"

HERE = Path(__file__).resolve().parent


def _pristine_run():
    """subprocess.run out of a PRIVATE copy of the module.

    Under `unittest discover` every test module shares one process, and one of
    the siblings installs a mock over subprocess.run AT IMPORT TIME -- earlier
    in discovery order than this file, so simply capturing the attribute here
    captures the mock. Observed: a spawn in this file came back holding another
    suite's canned LLM fixture, which would have turned "the key goes on stdin
    and not into argv" into an assertion about nothing. It is also why
    test_codex_login.SpawnEnvironment already fails under discover and passes
    alone -- a pre-existing suite-isolation defect, not this module's to fix.

    A private copy rather than importlib.reload(subprocess): reload would
    replace the SHARED module's attributes and rip out the sibling's patch
    underneath it, breaking whichever suite is relying on it. This copy is
    visible only here.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_pristine_subprocess",
                                                  subprocess.__file__)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run


#: The tests below spawn REAL processes to prove real properties. _Base pins
#: this for the duration of each one; a test that deliberately mocks the spawn
#: stacks its own patch on top.
_REAL_RUN = _pristine_run()


def _text(blob):
    """Child output as str, whether the run came back in bytes or text mode.

    Not defensive noise: run under `unittest discover` these modules share one
    process, and a sibling suite that patches subprocess can leave `run`
    answering str where this call asked for bytes. The assertions here are
    about CONTENT, so they should not care which."""
    if blob is None:
        return ""
    return blob.decode("utf-8", "replace") if isinstance(blob, bytes) else str(blob)


class _Memory:
    """The connectors MemoryCredentialStore's three verbs, without the import."""

    def __init__(self, items=None, fail=None):
        self.items = dict(items or {})
        self.fail = fail            # "put" | "get" | "delete" | None

    def put_secret(self, key, secret):
        if self.fail == "put":
            raise RuntimeError("keychain said no")
        self.items[key] = secret

    def get_secret(self, key):
        from connectors.credentials import CredentialNotFound
        from connectors.credentials.keychain import KeychainError
        if self.fail == "get":
            raise KeychainError(-25308, "get")
        try:
            return self.items[key]
        except KeyError:
            raise CredentialNotFound(key)

    def delete_secret(self, key):
        if self.fail == "delete":
            raise RuntimeError("keychain said no")
        self.items.pop(key, None)


class _Base(unittest.TestCase):
    """A settings DIRECTORY of our own, so marker_path() lands in it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self._orig = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = Path(self.dir) / "settings.json"
        self.addCleanup(lambda: setattr(providers, "SETTINGS_PATH", self._orig))
        # Order-independence, not defensiveness -- see _REAL_RUN. A test that
        # deliberately mocks the spawn stacks its own patch on top of this.
        self._patch(subprocess, "run", _REAL_RUN)

    def _patch(self, *args, **kwargs):
        p = mock.patch.object(*args, **kwargs)
        started = p.start()
        self.addCleanup(p.stop)
        return started

    def store(self, items=None, fail=None):
        """Patch in a memory store that reports itself available."""
        mem = _Memory(items, fail)
        self._patch(codex_auth, "_store", return_value=mem)
        self._patch(codex_auth, "store_status", return_value=(True, None))
        return mem

    def no_store(self, why="no credential store on this machine."):
        self._patch(codex_auth, "store_status", return_value=(False, why))

    def quiet_display(self, value=""):
        return self._patch(codex_auth, "current_display", return_value=value)

    def ok_probe(self):
        """Stub the OpenAI validation probe. Tests about the SPAWN must not
        depend on a network, and must not send anything anywhere."""
        return self._patch(codex_auth, "validate", return_value=None)

    def fake_codex(self, script):
        """Put a `codex` on PATH that runs `script`. Returns the log path it
        may write to. Restored on cleanup."""
        bindir = Path(self.dir) / "bin"
        bindir.mkdir(exist_ok=True)
        log = Path(self.dir) / "codex.log"
        path = bindir / "codex"
        path.write_text("#!/bin/sh\n" + script + "\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        was = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bindir) + os.pathsep + was
        self.addCleanup(lambda: os.environ.__setitem__("PATH", was))
        return log


# ------------------------------------------------------------------- mask ----

class Mask(unittest.TestCase):
    def test_the_last_four_and_the_prefix(self):
        self.assertEqual(codex_auth.mask(FAKE_KEY), FAKE_MASK)

    def test_a_short_string_reveals_nothing(self):
        self.assertEqual(codex_auth.mask("sk-abc"), "****")

    def test_the_mask_is_not_the_key(self):
        self.assertNotIn(FAKE_KEY, codex_auth.mask(FAKE_KEY))

    def test_none_and_empty_do_not_raise(self):
        self.assertEqual(codex_auth.mask(None), "****")
        self.assertEqual(codex_auth.mask(""), "****")


# ----------------------------------------------------------------- pastes ----

class PastesAreCleanedOrRefused(unittest.TestCase):
    def test_a_trailing_newline_is_trimmed(self):
        """codex reads until the newline, so a stored one is a broken key."""
        self.assertEqual(codex_auth.clean(FAKE_KEY + "\n"), FAKE_KEY)

    def test_internal_whitespace_is_refused_not_stripped(self):
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.clean(FAKE_KEY[:8] + " " + FAKE_KEY[8:])
        self.assertEqual(c.exception.code, "BAD_PASTE")

    def test_empty_is_refused(self):
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.clean("   ")
        self.assertEqual(c.exception.code, "NO_KEY")

    def test_a_pasted_file_is_refused(self):
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.clean("x" * (codex_auth.MAX_KEY_LEN + 1))
        self.assertEqual(c.exception.code, "TOO_LONG")

    def test_no_refusal_quotes_the_key_back(self):
        for bad in (FAKE_KEY[:8] + " " + FAKE_KEY[8:], FAKE_KEY * 40):
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.clean(bad)
            self.assertNotIn(FAKE_KEY, str(c.exception))


# ------------------------------------------------------- the important one ----

class TheSplitThatMattersMost(_Base):
    """A locked keychain is not an absent key, and saying so is the whole
    reason this module does not reuse deepseek_auth.read()."""

    def test_a_saved_key_comes_back(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        key, code, reason = codex_auth.read_or_reason()
        self.assertEqual(key, FAKE_KEY)
        self.assertIsNone(code)
        self.assertIsNone(reason)

    def test_nothing_saved_is_NO_STORED_KEY(self):
        self.store()
        key, code, reason = codex_auth.read_or_reason()
        self.assertIsNone(key)
        self.assertEqual(code, "NO_STORED_KEY")

    def test_a_LOCKED_keychain_is_not_a_missing_key(self):
        """THE FAILURE THIS FILE EXISTS FOR. Two different answers, and the
        locked one must not send anyone looking for a key they still have."""
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY}, fail="get")
        key, code, reason = codex_auth.read_or_reason()
        self.assertIsNone(key)
        self.assertEqual(code, "STORE_UNREADABLE")
        self.assertNotEqual(code, "NO_STORED_KEY")

    def test_the_locked_reason_says_the_key_is_still_there(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY}, fail="get")
        _, _, reason = codex_auth.read_or_reason()
        self.assertIn("still", reason)
        self.assertIn("25308", reason)          # searchable, and the only detail
        self.assertNotIn("no API key", reason)

    def test_no_credential_store_at_all_is_its_own_answer(self):
        self.no_store("this is Linux, where Sutra has no credential store yet.")
        key, code, reason = codex_auth.read_or_reason()
        self.assertIsNone(key)
        self.assertEqual(code, "NO_KEYCHAIN")
        self.assertIn("Linux", reason)

    def test_an_empty_stored_value_is_not_a_key(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: "   "})
        _, code, _ = codex_auth.read_or_reason()
        self.assertEqual(code, "NO_STORED_KEY")

    def test_no_reason_anywhere_carries_the_key(self):
        for setup in (lambda: self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY}, fail="get"),
                      lambda: self.store()):
            setup()
            _, _, reason = codex_auth.read_or_reason()
            self.assertNotIn(FAKE_KEY, str(reason))


# ----------------------------------------------------------------- marker ----

class TheMarkerHoldsNoKey(_Base):
    def setUp(self):
        super().setUp()
        self.store()
        self.quiet_display()

    def test_only_a_display_and_a_timestamp_are_written(self):
        codex_auth.store(FAKE_KEY)
        on_disk = json.loads(codex_auth.marker_path().read_text(encoding="utf-8"))
        self.assertEqual(sorted(on_disk), ["display", "saved_at"])
        self.assertNotIn(FAKE_KEY, json.dumps(on_disk))

    def test_it_is_NOT_the_settings_file(self):
        """The separation is the design. Same file would be two writers."""
        codex_auth.store(FAKE_KEY)
        self.assertNotEqual(codex_auth.marker_path(), providers.SETTINGS_PATH)
        self.assertEqual(codex_auth.marker_path().name, codex_auth.MARKER_NAME)

    def test_the_temp_path_is_not_the_settings_temp_path(self):
        """The interleave this file exists to avoid: two processes writing
        through one shared settings.json.tmp, where A's replace can move B's
        content into place."""
        ours = codex_auth.marker_path().with_suffix(".json.tmp")
        theirs = providers.SETTINGS_PATH.with_suffix(".json.tmp")
        self.assertNotEqual(ours, theirs)

    def test_a_settings_write_does_not_clobber_the_marker(self):
        """The actual race, driven rather than asserted in a comment."""
        codex_auth.store(FAKE_KEY)
        providers._write_settings({"workdir": "/tmp", "provider": "codex"})
        self.assertTrue(codex_auth.marker())
        self.assertEqual(codex_auth.marker()["display"], FAKE_MASK)

    def test_a_marker_write_does_not_clobber_settings(self):
        providers._write_settings({"workdir": "/tmp"})
        codex_auth.store(FAKE_KEY)
        self.assertEqual(providers._raw_settings().get("workdir"), "/tmp")

    def test_the_file_is_not_readable_by_anyone_else(self):
        codex_auth.store(FAKE_KEY)
        mode = stat.S_IMODE(codex_auth.marker_path().stat().st_mode)
        self.assertEqual(mode & 0o077, 0)

    def test_a_corrupt_marker_is_no_key_rather_than_a_crash(self):
        codex_auth.marker_path().parent.mkdir(parents=True, exist_ok=True)
        codex_auth.marker_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(codex_auth.marker(), {})

    def test_a_marker_without_a_display_is_not_a_saved_key(self):
        codex_auth.marker_path().parent.mkdir(parents=True, exist_ok=True)
        codex_auth.marker_path().write_text('{"saved_at": 1}', encoding="utf-8")
        self.assertEqual(codex_auth.marker(), {})

    def test_codex_own_stub_is_preferred_over_our_mask(self):
        """So the button that offers the key and the row that shows it live
        print the same string, rather than two masks of one key."""
        self.quiet_display(CODEX_STUB)
        m = codex_auth.store(FAKE_KEY)
        self.assertEqual(m["display"], CODEX_STUB)

    def test_our_mask_is_the_fallback_when_codex_printed_nothing(self):
        self.quiet_display("")
        self.assertEqual(codex_auth.store(FAKE_KEY)["display"], FAKE_MASK)


# ------------------------------------------------------------------ store ----

class StoreRecordsAKeyThatIsAlreadyLive(_Base):
    def test_a_good_key_is_stored_trimmed_and_marked(self):
        mem = self.store()
        self.quiet_display()
        codex_auth.store("  " + FAKE_KEY + "\n")
        self.assertEqual(mem.items[codex_auth.KEYCHAIN_ACCOUNT], FAKE_KEY)
        self.assertTrue(codex_auth.marker())

    def test_no_keychain_means_refused_and_nothing_written(self):
        self.no_store()
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.store(FAKE_KEY)
        self.assertEqual(c.exception.code, "NO_KEYCHAIN")
        self.assertFalse(codex_auth.marker_path().exists())

    def test_a_store_that_fails_leaves_no_marker(self):
        self.store(fail="put")
        self.quiet_display()
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.store(FAKE_KEY)
        self.assertEqual(c.exception.code, "STORE_FAILED")
        self.assertFalse(codex_auth.marker_path().exists())

    def test_a_store_failure_still_says_the_LOGIN_worked(self):
        """The two fail independently. A keychain that refused must not read as
        a sign-in that refused -- codex is using the key either way."""
        self.store(fail="put")
        self.quiet_display()
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.store(FAKE_KEY)
        self.assertIn("using the key now", str(c.exception))

    def test_no_message_claims_the_key_was_verified(self):
        """codex validates nothing (measured). No string here may imply it."""
        self.store(fail="put")
        self.quiet_display()
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.store(FAKE_KEY)
        blob = str(c.exception).lower()
        for word in ("valid", "verified", "accepted by openai", "confirmed"):
            self.assertNotIn(word, blob)


# ----------------------------------------------------------------- forget ----

class ForgetIsIdempotentAndIsNotASignOut(_Base):
    def test_the_key_and_the_marker_both_go(self):
        mem = self.store()
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        self.assertEqual(codex_auth.forget(), {"removed": True})
        self.assertEqual(mem.items, {})
        self.assertFalse(codex_auth.marker_path().exists())

    def test_forgetting_nothing_succeeds(self):
        self.store()
        self.assertEqual(codex_auth.forget(), {"removed": False})

    def test_a_failed_delete_keeps_the_marker(self):
        """Otherwise a live key sits in the keychain with nothing pointing at it."""
        self.store(fail="delete")
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.forget()
        self.assertEqual(c.exception.code, "STORE_FAILED")
        self.assertTrue(codex_auth.marker())

    def _failed_delete_message(self, status):
        from connectors.credentials.keychain import KeychainError
        mem = self.store()
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        mem.delete_secret = mock.Mock(
            side_effect=KeychainError(status, "delete"))
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.forget()
        return str(c.exception)

    def test_a_failed_forget_names_the_osstatus(self):
        """Forget is the same keychain path Remove is, and it read the same way
        -- "(KeychainError)", which named the class and not the problem."""
        message = self._failed_delete_message(-25308)
        self.assertIn("-25308", message)
        self.assertNotIn("KeychainError", message)

    def test_a_locked_keychain_and_a_foreign_owner_do_not_read_alike(self):
        locked = self._failed_delete_message(-25308)
        foreign = self._failed_delete_message(-25244)
        self.assertNotEqual(locked, foreign)
        self.assertIn("locked", locked)
        self.assertIn("different build", foreign)

    def test_forget_spawns_NOTHING(self):
        """Forgetting Sutra's copy must never sign codex out. A tidy-up that
        destroyed a working session would be the worst kind of surprise."""
        self.store()
        with mock.patch("subprocess.run",
                        side_effect=AssertionError("spawned anyway")):
            codex_auth.forget()


# ---------------------------------------------------------------- restore ----

class RestorePutsTheKeyBack(_Base):
    def test_the_key_goes_on_STDIN_and_never_into_argv(self):
        """argv is world-readable through ps. This is the whole reason the
        helper spawns codex itself rather than handing the key back out."""
        self.ok_probe()
        log = self.fake_codex('echo "ARGV:$@" > "%s"; cat >> "%s"' % (
            Path(self.dir) / "codex.log", Path(self.dir) / "codex.log"))
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.quiet_display(CODEX_STUB)
        codex_auth.restore()
        body = log.read_text(encoding="utf-8")
        self.assertIn("ARGV:login --with-api-key", body)
        self.assertNotIn(FAKE_KEY, body.split("\n")[0])   # not in argv
        self.assertIn(FAKE_KEY, body)                     # but it did arrive

    def test_nothing_saved_spawns_NOTHING(self):
        self.store()
        with mock.patch("subprocess.run",
                        side_effect=AssertionError("spawned anyway")):
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.restore()
        self.assertEqual(c.exception.code, "NO_STORED_KEY")

    def test_a_locked_keychain_spawns_NOTHING_and_says_which(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY}, fail="get")
        with mock.patch("subprocess.run",
                        side_effect=AssertionError("spawned anyway")):
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.restore()
        self.assertEqual(c.exception.code, "STORE_UNREADABLE")

    def test_a_refusal_is_classified_and_the_child_is_not_echoed(self):
        """codex echoes 'Reading API key from stdin...' on this path, and a
        future build could echo more of it."""
        self.ok_probe()
        self.fake_codex('echo "SECRET-CHILD-OUTPUT" >&2; exit 3')
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.restore()
        self.assertEqual(c.exception.code, "CODEX_REFUSED")
        self.assertNotIn("SECRET-CHILD-OUTPUT", str(c.exception))
        self.assertNotIn(FAKE_KEY, str(c.exception))

    def test_no_binary_is_its_own_code(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.ok_probe()
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.restore()
        self.assertEqual(c.exception.code, "NO_BINARY")

    def test_the_return_value_carries_a_stub_and_not_the_key(self):
        self.ok_probe()
        self.fake_codex("cat > /dev/null; exit 0")
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.quiet_display(CODEX_STUB)
        out = codex_auth.restore()
        self.assertEqual(out, {"display": CODEX_STUB})
        self.assertNotIn(FAKE_KEY, repr(out))

    def test_ONE_spawn_and_no_logout_first(self):
        """Measured 2026-09-08 on 0.153.2: --with-api-key overwrites a live
        ChatGPT session directly. A logout first would open a window where the
        user holds no credential at all, for nothing."""
        seen = []
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.quiet_display()
        self.ok_probe()

        def spy(argv, *a, **k):
            seen.append(list(argv))
            return mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("subprocess.run", side_effect=spy):
            codex_auth.restore()
        self.assertEqual(len(seen), 1)
        self.assertNotIn("logout", seen[0])


# ------------------------------------------------------------------ state ----

class StateDescribesTheCopyAndNeverTheLiveMode(_Base):
    def test_a_saved_key_reports_its_stub_and_when(self):
        self.store()
        self.quiet_display(CODEX_STUB)
        codex_auth.store(FAKE_KEY)
        st = codex_auth.state()
        self.assertTrue(st["stored"])
        self.assertEqual(st["display"], CODEX_STUB)
        self.assertIsInstance(st["saved_at"], float)

    def test_no_store_says_so_and_why(self):
        """The row must not draw a control that cannot work on this machine."""
        self.no_store("this is Linux, where Sutra has no credential store yet.")
        st = codex_auth.state()
        self.assertFalse(st["store_available"])
        self.assertIn("Linux", st["store_reason"])
        self.assertFalse(st["stored"])

    def test_state_makes_no_claim_about_which_credential_is_live(self):
        """`codex login status` is the only authority. A field here that looked
        like a mode would let the row say 'API key' over a ChatGPT session."""
        self.store()
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        self.assertEqual(sorted(codex_auth.state()),
                         ["display", "saved_at", "store_available",
                          "store_reason", "stored"])

    def test_no_state_field_can_hold_a_key(self):
        self.store()
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        self.assertNotIn(FAKE_KEY, repr(codex_auth.state()))


# ---------------------------------------------------------------- sidecar ----

class TheSidecarAlwaysAnswersOneJsonLine(_Base):
    """The desktop shell parses stdout. A traceback there is an unparseable
    answer AND, on the store path, a print of locals that include the key."""

    def run_verb(self, verb, stdin=b""):
        env = dict(os.environ)
        env["SUTRA_UI_SETTINGS"] = str(providers.SETTINGS_PATH)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p = subprocess.run([sys.executable, "-m", "codex_auth", verb],
                           cwd=str(HERE), env=env, input=stdin,
                           capture_output=True, timeout=60)
        return p, _text(p.stdout)

    def test_every_verb_answers_parseable_json(self):
        for verb in ("state", "restore", "forget", "store", "nonsense"):
            p, out = self.run_verb(verb)
            self.assertEqual(p.returncode, 0, verb)
            parsed = json.loads(out.strip())
            self.assertIsInstance(parsed.get("ok"), bool, verb)

    def test_a_failure_still_exits_zero_with_a_code(self):
        """So the shell reads a reason rather than guessing from a dead child."""
        p, out = self.run_verb("restore")
        self.assertEqual(p.returncode, 0)
        parsed = json.loads(out.strip())
        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["code"], "NO_STORED_KEY")

    def test_an_unknown_verb_is_named_not_crashed(self):
        p, out = self.run_verb("wat")
        self.assertEqual(json.loads(out.strip()).get("code"), "BAD_VERB",
                         "stdout=%r stderr=%r" % (out, _text(p.stderr)))

    def test_a_key_on_stdin_never_reaches_stdout(self):
        p, out = self.run_verb("store", (FAKE_KEY + "\n").encode())
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn(FAKE_KEY, _text(p.stderr))

    def test_an_unexpected_failure_reports_a_TYPE_and_no_traceback(self):
        with mock.patch.object(codex_auth, "state",
                               side_effect=ValueError(FAKE_KEY)):
            answer = codex_auth._main(["codex_auth", "state"])
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["code"], "UNEXPECTED")
        self.assertIn("ValueError", answer["message"])
        self.assertNotIn(FAKE_KEY, json.dumps(answer))


# ------------------------------------------------------------- no leakage ----

class NothingEchoesTheKey(_Base):
    """The route-level sweep. The existing no-echo tests are module-scoped
    (test_codex_login's source grep) or contract-scoped (test_deepseek_auth's
    repr checks); none of them walks an actual HTTP answer with a key in the
    store. This one does."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import app
        cls.client = TestClient(app.app)
        cls.H = {"host": "127.0.0.1:8787"}

    def test_no_read_route_carries_the_key(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        for path in ("/api/providers/codex/auth", "/api/settings", "/api/providers"):
            r = self.client.get(path, headers=self.H)
            self.assertNotIn(FAKE_KEY, r.text, path)

    def test_the_codex_auth_route_carries_the_saved_state(self):
        """The row reads it from HERE. Asserting the wire, not the fixture --
        test_deepseek_auth learned this one the hard way (the state landed as a
        sibling of `settings` and nothing read it)."""
        self.store()
        self.quiet_display(CODEX_STUB)
        codex_auth.store(FAKE_KEY)
        got = self.client.get("/api/providers/codex/auth", headers=self.H).json()
        self.assertIn("stored", got)
        self.assertTrue(got["stored"]["stored"])
        self.assertEqual(got["stored"]["display"], CODEX_STUB)

    def test_the_saved_state_never_replaces_the_live_state(self):
        """Two separate facts in one answer. Collapsing them would let the row
        claim a billing mode nobody read from codex."""
        self.store()
        self.quiet_display()
        codex_auth.store(FAKE_KEY)
        got = self.client.get("/api/providers/codex/auth", headers=self.H).json()
        self.assertIn("state", got)               # from `codex login status`
        self.assertIn("stored", got)              # from our keychain
        self.assertNotIn("state", got["stored"])


# ------------------------------------------------------------- validation ----

class BadKeysAreRefusedBeforeAnythingChanges(_Base):
    """THE FAILURE THIS CLASS EXISTS FOR (founder report, 2026-09-08).

    A deliberately fake key was saved successfully: codex printed "Successfully
    logged in" and the row read "billed per token". Every call afterwards failed
    with a raw 401 retried five times, carrying websocket URLs and Rust module
    paths -- output nobody would connect to a key they pasted earlier. codex
    validates NOTHING; it checks that stdin is non-empty.

    So Sutra probes the key itself, and it does so BEFORE the login spawn: a
    rejected key must never reach ~/.codex, because the login is what destroys
    the credential already there. Every assertion below is either "the right
    refusal" or "and nothing was touched".
    """

    def probe(self, exc):
        """Make the OpenAI probe fail in a specific way."""
        return self._patch(urllib.request, "urlopen", side_effect=exc)

    def http(self, code):
        return urllib.error.HTTPError(codex_auth.VALIDATE_URL, code, "", None, None)

    def test_401_is_a_rejected_key_and_says_nothing_changed(self):
        self.probe(self.http(401))
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.check(FAKE_KEY)
        self.assertEqual(c.exception.code, "KEY_REJECTED")
        self.assertIn("nothing was changed", str(c.exception).lower())

    def test_402_is_billing_not_a_bad_key(self):
        """Different sentence because it is a different fix. The key is real."""
        self.probe(self.http(402))
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.check(FAKE_KEY)
        self.assertEqual(c.exception.code, "BILLING")

    def test_429_says_UNCONFIRMED_rather_than_wrong(self):
        self.probe(self.http(429))
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.check(FAKE_KEY)
        self.assertEqual(c.exception.code, "RATE_LIMITED")
        self.assertIn("could not be confirmed", str(c.exception))

    def test_404_blames_this_build_not_the_operator(self):
        self.probe(self.http(404))
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.check(FAKE_KEY)
        self.assertEqual(c.exception.code, "PROBE_UNRECOGNISED")
        self.assertIn("not a problem with your key", str(c.exception))

    def test_a_network_failure_is_not_a_rejected_key(self):
        """And it is REFUSED rather than saved unchecked -- saving on a guess
        recreates the exact failure this probe exists to stop."""
        self.probe(urllib.error.URLError("boom"))
        with self.assertRaises(codex_auth.CodexAuthError) as c:
            codex_auth.check(FAKE_KEY)
        self.assertEqual(c.exception.code, "NETWORK")
        self.assertIn("not saved on a guess", str(c.exception))

    def test_no_refusal_anywhere_carries_the_key(self):
        for exc in (self.http(401), self.http(402), self.http(429),
                    self.http(404), self.http(500), urllib.error.URLError("x")):
            self.probe(exc)
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.check(FAKE_KEY)
            self.assertNotIn(FAKE_KEY, str(c.exception))

    def test_a_2xx_passes_and_returns_only_a_mask(self):
        self._patch(urllib.request, "urlopen",
                    return_value=mock.MagicMock(
                        __enter__=lambda s: mock.Mock(status=200),
                        __exit__=lambda *a: False))
        out = codex_auth.check(FAKE_KEY)
        self.assertEqual(out, {"mask": FAKE_MASK})
        self.assertNotIn(FAKE_KEY, repr(out))

    def test_the_key_goes_in_a_HEADER_and_not_the_url(self):
        """A URL reaches proxy logs and browser history. A header does not."""
        seen = {}

        def spy(req, *a, **k):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            raise self.http(401)
        self._patch(urllib.request, "urlopen", side_effect=spy)
        with self.assertRaises(codex_auth.CodexAuthError):
            codex_auth.check(FAKE_KEY)
        self.assertNotIn(FAKE_KEY, seen["url"])
        self.assertIn(FAKE_KEY, seen["auth"])

    def test_a_refused_key_SPAWNS_NOTHING_and_STORES_NOTHING(self):
        """The whole point of checking first. codex keeps what it had."""
        self.store()
        self.probe(self.http(401))
        with mock.patch("subprocess.run",
                        side_effect=AssertionError("spawned anyway")):
            with self.assertRaises(codex_auth.CodexAuthError):
                codex_auth.check(FAKE_KEY)
        self.assertFalse(codex_auth.marker_path().exists())

    def test_a_bad_paste_is_refused_before_the_network_is_touched(self):
        """No point sending a broken paste anywhere to learn it is broken."""
        with mock.patch.object(urllib.request, "urlopen",
                               side_effect=AssertionError("probed anyway")):
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.check(FAKE_KEY[:8] + " " + FAKE_KEY[8:])
        self.assertEqual(c.exception.code, "BAD_PASTE")


class RestoreChecksTheSavedKeyToo(_Base):
    """A key that was good when saved can be revoked, rotated or defunded.
    Putting a dead one live is the same 401 storm, aimed at someone who did
    nothing wrong."""

    def test_a_revoked_saved_key_does_not_reach_codex(self):
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self._patch(urllib.request, "urlopen",
                    side_effect=urllib.error.HTTPError(
                        codex_auth.VALIDATE_URL, 401, "", None, None))
        with mock.patch("subprocess.run",
                        side_effect=AssertionError("spawned anyway")):
            with self.assertRaises(codex_auth.CodexAuthError) as c:
                codex_auth.restore()
        self.assertEqual(c.exception.code, "KEY_REJECTED")

    def test_a_rejected_restore_KEEPS_the_saved_copy(self):
        """The key may be fine and the network may not. Forgetting it here would
        destroy the only copy over a transient."""
        mem = self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.quiet_display()
        codex_auth._write_marker(FAKE_KEY, CODEX_STUB)
        self._patch(urllib.request, "urlopen",
                    side_effect=urllib.error.URLError("offline"))
        with self.assertRaises(codex_auth.CodexAuthError):
            codex_auth.restore()
        self.assertEqual(mem.items[codex_auth.KEYCHAIN_ACCOUNT], FAKE_KEY)
        self.assertTrue(codex_auth.marker())


class TheCheckRunsBEFORETheLogin(unittest.TestCase):
    """THE ORDERING IS THE FIX, and it is the part most easily undone.

    Checking after the spawn -- which is where the request first pointed --
    would still let a dead key REPLACE a working ChatGPT sign-in, because the
    login is the destruction and the store is only the record of it. This reads
    the shell as text, since main.js cannot be require()d (it pulls in electron).

    THE LOGIN MARKER CHANGED WITH BUG #4 (2026-09-09), the invariant did not.
    The login used to be `codexRun(e, ["login","--with-api-key"], ...)` in this
    handler; it is now `codexAuthCli("login", ...)`, because spawning the bare
    name `codex` here found nothing on the default install. What these tests
    pin -- probe first, store last, and a rejected key returning before the
    login -- is untouched by that move.
    """

    def setUp(self):
        self.js = (HERE / "electron" / "main.js").read_text(encoding="utf-8")
        start = self.js.index('ipcMain.handle("sutra:codex-api-key"')
        self.handler = self.js[start:self.js.index("});", self.js.index(
            'codexAuthCli("store"', start))]

    def test_the_handler_checks_then_logs_in_then_stores(self):
        i_check = self.handler.index('codexAuthCli("check"')
        i_login = self.handler.index('codexAuthCli("login"')
        i_store = self.handler.index('codexAuthCli("store"')
        self.assertLess(i_check, i_login, "the probe must precede the spawn")
        self.assertLess(i_login, i_store, "only a live key is remembered")

    def test_a_failed_check_returns_before_the_spawn(self):
        between = self.handler[self.handler.index('codexAuthCli("check"'):
                               self.handler.index('codexAuthCli("login"')]
        self.assertIn("return", between,
                      "a rejected key must return, not fall through to the spawn")

    def test_the_shell_forwards_the_helpers_sentence_not_its_own(self):
        """The helper classifies; main.js must not invent a reason, and must not
        forward anything derived from a child's output."""
        self.assertIn("checked && checked.message", self.handler)


# ------------------------------------------------------ the standing rules ----

def _code_only(text, lang):
    """The file with COMMENTS AND DOCSTRINGS REMOVED.

    Needed because the ban below is DOCUMENTED in the very files it applies to
    -- codex_auth.py's docstring names 429 in order to say it is not reacted
    to, and 07-loaders.js's codexReprobe warning names codexKeyRestore in order
    to forbid calling it there. A raw substring scan would read the prohibition
    as the violation, which is the test failing on its own explanation.
    """
    if lang == "py":
        text = re.sub(r'"""[\s\S]*?"""', "", text)
        text = re.sub(r"(?m)#.*$", "", text)
    else:
        text = re.sub(r"/\*[\s\S]*?\*/", "", text)
        text = re.sub(r"(?m)//.*$", "", text)
    return text


class NoAutomaticFallback(unittest.TestCase):
    """Founder direction 2026-09-08. Sutra now holds the key, which is what
    makes a silent switch onto per-token billing possible -- so the ban is
    pinned in the place it would be broken rather than only written down."""

    def _read(self, rel):
        return (HERE / rel).read_text(encoding="utf-8")

    def _code(self, rel):
        return _code_only(self._read(rel), "py" if rel.endswith(".py") else "js")

    def test_the_panel_only_restores_from_a_click_handler(self):
        """ONE call site in executable code, and it is inside the [data-codex]
        onclick. A second would mean something else can start a switch."""
        code = self._code("static/js/07-loaders.js")
        self.assertEqual(code.count("codexKeyRestore"), 1)
        self.assertIn("bridge.codexKeyRestore()", code)

    def test_the_panel_never_branches_on_a_quota_signal(self):
        """Scoped to the PANEL, which is where an auto-switch would live.

        It used to scan codex_auth.py for the same tokens, and that became wrong
        the moment save-time validation landed: _classify() legitimately reads a
        429 from the OpenAI probe in order to REFUSE a save. Branching on a
        quota to decline an action is the opposite of branching on one to start
        a billed session, and a test that cannot tell them apart would have
        forced the validation to be written worse.
        """
        code = self._code("static/js/07-loaders.js").lower()
        for trigger in ("429", "quota", "plan_exhausted", "insufficient",
                        "rate_limit"):
            self.assertNotIn(trigger, code, "the panel branches on %s" % trigger)

    def test_restore_is_only_reachable_from_the_verb_dispatch(self):
        """The module-side half of the same ban: nothing inside codex_auth calls
        restore() except the sidecar's verb table, so there is no in-process
        path that could put a billed credential live without a click."""
        code = _code_only((HERE / "codex_auth.py").read_text(encoding="utf-8"), "py")
        calls = [l.strip() for l in code.split("\n")
                 if "restore()" in l and "def restore" not in l]
        self.assertEqual(calls, ['return {"ok": True, **restore()}'],
                         "unexpected restore() call sites: %s" % calls)

    def test_the_reprobe_carries_the_warning_where_it_would_creep_in(self):
        src = self._read("static/js/07-loaders.js")
        i = src.index("async function codexReprobe")
        self.assertIn("NO AUTOMATIC FALLBACK", src[max(0, i - 1200):i])


class TheDuplicationIsDeclared(unittest.TestCase):
    """deepseek_auth.py is NOT touched (founder direction 2026-09-08), so four
    small functions are duplicated. The extraction point is marked so the
    follow-up is obvious rather than archaeological -- and this fails if the
    marker is quietly dropped."""

    def test_the_extraction_point_is_named(self):
        src = (HERE / "codex_auth.py").read_text(encoding="utf-8")
        self.assertIn("EXTRACTION POINT", src)
        self.assertIn("provider_keychain.py", src)

    def test_this_module_does_not_reach_into_deepseek_auth(self):
        """Founder direction: standalone, tonight. The docstrings cite
        deepseek_auth constantly -- to explain what was NOT reused -- so the
        assertion is against executable code only."""
        code = _code_only((HERE / "codex_auth.py").read_text(encoding="utf-8"), "py")
        self.assertNotIn("deepseek_auth", code)


# ================== BUG #4: THE API KEY NEVER BECAME THE ACTIVE MODE ========
# THE BUG, exactly. On a machine where `codex` is NOT on PATH -- which is the
# machine this app is BUILT for, because Sutra installs its own codex at
# ~/.sutra-ui/providers/codex/node_modules/.bin/codex and puts it on no PATH --
# adding an OpenAI API key did nothing:
#
#   1. main.js's codexRun() spawned the BARE NAME `codex`      -> ENOENT
#   2. `codex login --with-api-key` therefore never ran
#   3. ~/.codex/auth.json kept the CHATGPT credential
#   4. the row went on saying "Signed in with ChatGPT · covered by your
#      ChatGPT plan" -- TRUTHFULLY, because that is what codex still held
#   5. and the keychain copy was never written either: main.js returns before
#      its `store` step when the login fails
#
# The status PROBE resolved fine the whole time, through
# providers.provider_bin("codex") -- so the two halves of the feature were
# asking two different binaries and only one of them existed. codex_auth.py
# recorded that as a "KNOWN DIVERGENCE" and main.js as a "KNOWN LIMIT"; it was
# a live bug on the default install.
#
# THE FIX. _codex_bin() resolves PATH first and Sutra's own install second, and
# is now the SINGLE place that decides which binary receives a credential --
# login() and restore() both go through _put_key_live().
#
# WHAT THESE TESTS PIN, that nothing above did: the RESOLUTION. Every existing
# test in this file puts a `codex` on PATH via fake_codex(), so all of them
# passed for the entire life of the bug. The regression is the case where PATH
# has none.


class _NoCodexOnPath(_Base):
    """_Base, plus a PATH with no `codex` on it at all.

    This is the shape the bug lived in, and no other test in this file creates
    it -- fake_codex() always makes the bare name resolve.
    """

    def setUp(self):
        super().setUp()
        # The SYSTEM dirs stay, deliberately: a real machine has /bin and
        # /usr/bin and simply no codex, and the stub scripts below need `cat`.
        # An empty PATH would make them exit 127 and test the fixture instead.
        was = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(["/usr/bin", "/bin"])
        self.addCleanup(lambda: os.environ.__setitem__("PATH", was))
        self.assertIsNone(__import__("shutil").which("codex"),
                          "the fixture failed: a codex is still reachable")

    def managed(self, script="exit 0"):
        """A Sutra-managed codex at a path that is on NO PATH. Returns (path,
        log) -- the script may append to `log` to prove it was the one run."""
        root = Path(self.dir) / "managed" / "node_modules" / ".bin"
        root.mkdir(parents=True, exist_ok=True)
        log = Path(self.dir) / "managed.log"
        binp = root / "codex"
        binp.write_text("#!/bin/sh\necho managed >> '%s'\n%s\n" % (log, script),
                        encoding="utf-8")
        binp.chmod(binp.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self._patch(codex_install, "managed_bin", return_value=binp)
        return binp, log


class TheCredentialSpawnFindsSutrasOwnCodex(_NoCodexOnPath):
    """_codex_bin(): PATH first, Sutra's own install second, provider_bin never."""

    def test_THE_BUG_managed_install_is_used_when_PATH_has_no_codex(self):
        """THE REGRESSION. Before the fix this returned the bare name "codex",
        which does not exist here, and every credential spawn died ENOENT."""
        binp, _ = self.managed()
        self.assertEqual(codex_auth._codex_bin(), str(binp))
        self.assertNotEqual(codex_auth._codex_bin(), "codex")

    def test_a_codex_on_PATH_still_wins_so_nothing_else_changes(self):
        """The bare name is still preferred when it resolves: a machine with a
        real codex on PATH must behave exactly as it did before."""
        self.managed()
        self.fake_codex("exit 0")               # puts one back on PATH
        got = codex_auth._codex_bin()
        self.assertTrue(got.endswith("/bin/codex"), got)
        self.assertNotIn("node_modules", got)

    def test_the_bare_name_is_the_last_resort_so_the_error_is_unchanged(self):
        """Neither exists -> "codex", so FileNotFoundError still fires and the
        NO_BINARY sentence is the one it always was."""
        self._patch(codex_install, "managed_bin",
                    return_value=Path(self.dir) / "nope" / "codex")
        self.assertEqual(codex_auth._codex_bin(), "codex")

    def test_provider_bins_is_STILL_never_honoured(self):
        """The renderer can set provider_bins; it must never choose which
        binary receives a key. The fallback is a FIXED Sutra-owned path, which
        is the whole difference between it and provider_bin."""
        binp, _ = self.managed()
        evil = Path(self.dir) / "evil-codex"
        evil.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        evil.chmod(evil.stat().st_mode | stat.S_IEXEC)
        self._patch(providers, "provider_bin", return_value=str(evil))
        self.assertEqual(codex_auth._codex_bin(), str(binp))

    def test_a_broken_managed_lookup_degrades_to_the_bare_name(self):
        """managed_bin() reads a settings path; if that ever raises, a
        credential verb must still produce its normal refusal rather than a
        traceback out of the sidecar."""
        self._patch(codex_install, "managed_bin",
                    side_effect=RuntimeError("settings unreadable"))
        self.assertEqual(codex_auth._codex_bin(), "codex")


class LoginMakesTheKeyTheActiveCredential(_NoCodexOnPath):
    """codex_auth.login() -- the verb main.js now calls instead of spawning
    `codex` itself."""

    def test_THE_BUG_END_TO_END_the_key_reaches_codex_with_no_PATH_entry(self):
        """What the operator actually reported: adding a key changed nothing.
        The login now runs, through Sutra's own binary, and reports the mask."""
        _, log = self.managed("cat > /dev/null")
        self.ok_probe()
        self.quiet_display(CODEX_STUB)
        out = codex_auth.login(FAKE_KEY)
        self.assertEqual(out, {"display": CODEX_STUB})
        self.assertIn("managed", log.read_text(encoding="utf-8"),
                      "Sutra's own codex was never the one that ran")

    def test_the_key_goes_on_STDIN_and_never_into_argv(self):
        """A key in argv is readable from the process list by anything on this
        machine. The spawn is inspected directly rather than trusted."""
        self.managed("cat > /dev/null")
        self.ok_probe()
        self.quiet_display()
        seen = {}
        real = subprocess.run

        def spy(args, **kw):
            seen["argv"] = list(args)
            seen["input"] = kw.get("input")
            return real(args, **kw)

        self._patch(subprocess, "run", side_effect=spy)
        codex_auth.login(FAKE_KEY)
        self.assertEqual(seen["argv"][1:], ["login", "--with-api-key"])
        self.assertNotIn(FAKE_KEY, " ".join(seen["argv"]))
        self.assertEqual(seen["input"], FAKE_KEY + "\n")

    def test_the_probe_runs_BEFORE_the_spawn_so_a_bad_key_changes_nothing(self):
        """The login is the destruction: a key OpenAI rejects must never reach
        ~/.codex, or a dead paste replaces a working ChatGPT session."""
        _, log = self.managed("cat > /dev/null")
        self._patch(codex_auth, "validate",
                    side_effect=codex_auth.CodexAuthError("BAD_KEY", "no."))
        with self.assertRaises(codex_auth.CodexAuthError):
            codex_auth.login(FAKE_KEY)
        self.assertFalse(log.exists(), "a rejected key still reached codex")

    def test_a_refusing_codex_is_reported_without_echoing_its_output(self):
        self.managed("cat > /dev/null\necho 'the key is %s' >&2\nexit 3" % FAKE_KEY)
        self.ok_probe()
        self.quiet_display()
        with self.assertRaises(codex_auth.CodexAuthError) as caught:
            codex_auth.login(FAKE_KEY)
        msg = str(caught.exception)
        self.assertEqual(caught.exception.code, "CODEX_REFUSED")
        self.assertNotIn(FAKE_KEY, msg)
        self.assertNotIn("the key is", msg)

    def test_a_missing_binary_refuses_without_a_traceback(self):
        self._patch(codex_install, "managed_bin",
                    return_value=Path(self.dir) / "nope" / "codex")
        self.ok_probe()
        with self.assertRaises(codex_auth.CodexAuthError) as caught:
            codex_auth.login(FAKE_KEY)
        self.assertEqual(caught.exception.code, "NO_BINARY")

    def test_restore_uses_THE_SAME_resolution_so_it_is_fixed_too(self):
        """restore() had the identical ENOENT. It now shares _put_key_live, so
        one definition decides which binary receives a credential."""
        _, log = self.managed("cat > /dev/null")
        self.store({codex_auth.KEYCHAIN_ACCOUNT: FAKE_KEY})
        self.ok_probe()
        self.quiet_display(CODEX_STUB)
        self.assertEqual(codex_auth.restore(), {"display": CODEX_STUB})
        self.assertIn("managed", log.read_text(encoding="utf-8"))


class TheSidecarLoginVerbAnswersOneJsonLine(_NoCodexOnPath):
    """The wire main.js now uses: `python -m codex_auth login`, key on stdin."""

    def _run(self, key, script="cat > /dev/null"):
        binp, _ = self.managed(script)
        env = dict(os.environ)
        env["SUTRA_UI_SETTINGS"] = str(providers.SETTINGS_PATH)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["SUTRA_TEST_MANAGED_CODEX"] = str(binp)
        return subprocess.run(
            [sys.executable, "-m", "codex_auth", "login"],
            input=key, capture_output=True, text=True, cwd=str(HERE),
            env=env, timeout=60)

    def test_an_unroutable_probe_is_a_refusal_not_a_crash(self):
        """No network is touched: the probe host is unroutable, so this asserts
        the SHAPE of the answer -- one JSON line, ok:false, no key in it."""
        self._patch(codex_auth, "VALIDATE_URL", "https://127.0.0.1:1/v1/models")
        p = self._run(FAKE_KEY)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1, p.stdout)
        answer = json.loads(lines[0])
        self.assertIs(answer["ok"], False)
        self.assertNotIn(FAKE_KEY, p.stdout)
        self.assertNotIn(FAKE_KEY, p.stderr)

    def test_the_verb_is_recognised_at_all(self):
        """A verb the sidecar does not know answers BAD_VERB, which is what
        `login` did before this fix -- main.js would have had no way to run it."""
        p = subprocess.run([sys.executable, "-m", "codex_auth", "login"],
                           input="", capture_output=True, text=True,
                           cwd=str(HERE), timeout=60)
        answer = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertNotEqual(answer.get("code"), "BAD_VERB",
                            "the login verb is not wired into _main")


class MainJsDelegatesTheLoginToTheSidecar(unittest.TestCase):
    """main.js is read as TEXT -- it needs Electron to execute. These pin the
    two-line rewiring that is the other half of the fix."""

    def setUp(self):
        self.js = (HERE / "electron" / "main.js").read_text(encoding="utf-8")

    def test_the_api_key_handler_no_longer_spawns_codex_itself(self):
        handler = self.js.split('ipcMain.handle("sutra:codex-api-key"')[1]
        handler = handler.split("ipcMain.handle(")[0]
        self.assertNotIn('codexRun(e, ["login", "--with-api-key"]', handler,
                         "the bare-name spawn is back in the API-key handler")
        self.assertIn('codexAuthCli("login"', handler)

    def test_the_login_timeout_exceeds_the_helpers_own_budget(self):
        """An outer kill inside the helper's 78s worst case would SIGKILL it
        mid-spawn and report a timeout for a login that already landed."""
        m = re.search(r"CODEX_KEY_LOGIN_TIMEOUT\s*=\s*(\d+)", self.js)
        self.assertIsNotNone(m, "CODEX_KEY_LOGIN_TIMEOUT is gone")
        budget = (codex_auth.PROBE_TIMEOUT + codex_auth.RESTORE_TIMEOUT
                  + codex_auth.STATUS_TIMEOUT)
        self.assertGreater(int(m.group(1)) / 1000.0, budget)

    def test_no_http_route_accepts_a_key(self):
        """The fix must not have moved the key onto the backend port. The
        sidecar is stdin; org_api has no key-accepting route and gains none."""
        org = (HERE / "org_api.py").read_text(encoding="utf-8")
        self.assertNotIn("codex/apikey", org)
        self.assertNotIn("with-api-key", org)


if __name__ == "__main__":
    unittest.main()
