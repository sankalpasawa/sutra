"""Who is allowed to DELETE a saved credential, which is the part that broke.

THE SHIPPED BUG, measured 2026-09-08 on macOS 25.6. SecItemAdd's default ACL
trusts exactly the code identity that called it. Everything else that tries to
change the item gets -25244 errSecInvalidOwnerEdit -- no prompt, no way for the
user to grant access, permanent. Sutra's app is ad-hoc signed, so every build is
a new identity: a key saved by one build could not be removed by the next, and
the provider panel's Remove and Forget buttons failed with "(KeychainError)" and
nothing else to go on.

Four things these tests exist to keep true:

  1. Every saved item carries an EXPLICIT ACL. Lose that line and the bug comes
     back silently -- nothing fails until someone rebuilds and clicks Remove.

  2. Rotation REPLACES the item. SecItemUpdate cannot refresh an ACL (measured:
     it returns 0 and changes nothing, including when handed kSecAttrAccess), so
     an in-place rotation would keep every rotated key locked to the build that
     first saved it.

  3. -25244 falls back to `security delete-generic-password`, and that fallback
     passes NO SECRET -- a service name and an account name, both public. It is
     the one keychain verb where the CLI is the right tool, and the reason is
     the same argv argument the module docstring makes for avoiding it on writes.

  4. A failure names its OSStatus. "Locked keychain" and "owned by another
     build" are different problems with the same exception type, and reporting
     the type alone made them indistinguishable on screen.

THE UNIT TESTS FAKE THE ctypes LAYER and build the store with object.__new__ to
skip the macOS-only guard: what is under test is the access policy, not the
platform. The integration class at the bottom does hit the real login keychain,
under its own service name, and cleans up after itself.
"""
import ctypes
import subprocess
import unittest
from unittest import mock

from connectors.credentials import keychain as KC

#: Every Security.framework constant the store looks up, standing in for itself
#: so an assertion can name the key it expects.
_KEYS = (
    "kSecClass", "kSecClassGenericPassword", "kSecAttrService", "kSecAttrAccount",
    "kSecValueData", "kSecReturnData", "kSecMatchLimit", "kSecMatchLimitOne",
    "kSecAttrAccessible", "kSecAttrAccessibleWhenUnlockedThisDeviceOnly",
    "kSecAttrLabel", "kSecAttrAccess",
)

_ACCESS = 0xACCE55
_ACL_LIST = 0xAC1157
_ACL_COUNT = 3


class _FakeCF:
    def __init__(self):
        self.handle = 1000
        self.dicts = {}
        self.data_bytes = []
        self.released = []

    def _next(self):
        self.handle += 1
        return self.handle

    def CFStringCreateWithBytes(self, alloc, raw, length, encoding, external):
        return self._next()

    def CFDataCreate(self, alloc, raw, length):
        self.data_bytes.append(bytes(raw))
        return self._next()

    def CFDictionaryCreateMutable(self, alloc, size, key_cbs, value_cbs):
        handle = self._next()
        self.dicts[handle] = {}
        return handle

    def CFDictionarySetValue(self, handle, key, value):
        self.dicts[handle][key] = value

    def CFRelease(self, handle):
        self.released.append(handle)

    def CFArrayGetCount(self, array):
        return _ACL_COUNT

    def CFArrayGetValueAtIndex(self, array, index):
        return ("acl", index)


class _FakeSec:
    def __init__(self, add=(0,), delete=0, access_status=0):
        self.add_statuses = list(add)
        self.delete_status = delete
        self.access_status = access_status
        self.calls = []
        self.acl_app_lists = []

    # -- access ----------------------------------------------------------
    def SecAccessCreate(self, label, app_list, out):
        if self.access_status:
            return self.access_status
        out._obj.value = _ACCESS
        return 0

    def SecAccessCopyACLList(self, access, out):
        out._obj.value = _ACL_LIST
        return 0

    def SecACLSetContents(self, acl, app_list, description, prompt):
        self.acl_app_lists.append(app_list)
        return 0

    # -- items -----------------------------------------------------------
    def SecItemAdd(self, attrs, result):
        self.calls.append(("add", attrs))
        return self.add_statuses.pop(0) if self.add_statuses else 0

    def SecItemUpdate(self, query, changes):
        self.calls.append(("update", query))
        return 0

    def SecItemDelete(self, query):
        self.calls.append(("delete", query))
        return self.delete_status

    def SecItemCopyMatching(self, query, result):
        self.calls.append(("match", query))
        return KC._ERR_ITEM_NOT_FOUND


def _store(sec, cf=None, service="com.sutra.test"):
    store = object.__new__(KC.KeychainCredentialStore)
    store.service = service
    store._cf = cf if cf is not None else _FakeCF()
    store._sec = sec
    store._k = {name: name for name in _KEYS}
    store._true = "kCFBooleanTrue"
    store._kcb = ctypes.c_void_p(0)
    store._vcb = ctypes.c_void_p(0)
    return store


def _ops(sec):
    return [name for name, _ in sec.calls]


# ------------------------------------------------------------------- save ----

class ASavedItemCarriesAnExplicitACL(unittest.TestCase):
    def test_the_add_dictionary_names_ksecattraccess(self):
        sec, cf = _FakeSec(), _FakeCF()
        store = _store(sec, cf)
        store.put_secret("acct", "value")
        (_, attrs), = [c for c in sec.calls if c[0] == "add"]
        self.assertEqual(cf.dicts[attrs]["kSecAttrAccess"], _ACCESS)

    def test_the_accessibility_class_is_still_set(self):
        """The explicit ACL is an addition, not a replacement -- Design 02 §2.4
        still wants the this-device-only class on the item."""
        sec, cf = _FakeSec(), _FakeCF()
        _store(sec, cf).put_secret("acct", "value")
        (_, attrs), = [c for c in sec.calls if c[0] == "add"]
        self.assertEqual(cf.dicts[attrs]["kSecAttrAccessible"],
                         "kSecAttrAccessibleWhenUnlockedThisDeviceOnly")

    def test_every_acl_in_the_access_trusts_any_application(self):
        """A NULL application list IS the "any application" ACL, and it has to
        be set on all of them -- SecAccessCreate hands back three."""
        sec = _FakeSec()
        _store(sec).put_secret("acct", "value")
        self.assertEqual(sec.acl_app_lists, [None] * _ACL_COUNT)

    def test_a_store_that_cannot_build_the_acl_still_saves(self):
        """A key that saves and needs the CLI to delete beats a save that
        refuses. The item is added with the default ACL and no exception."""
        sec, cf = _FakeSec(access_status=-1), _FakeCF()
        _store(sec, cf).put_secret("acct", "value")
        (_, attrs), = [c for c in sec.calls if c[0] == "add"]
        self.assertNotIn("kSecAttrAccess", cf.dicts[attrs])

    def test_a_failed_save_raises_with_its_osstatus(self):
        sec = _FakeSec(add=(KC._ERR_INTERACTION_NOT_ALLOWED,))
        with self.assertRaises(KC.KeychainError) as caught:
            _store(sec).put_secret("acct", "value")
        self.assertEqual(caught.exception.status, KC._ERR_INTERACTION_NOT_ALLOWED)


class RotationReplacesRatherThanUpdates(unittest.TestCase):
    def test_a_duplicate_is_deleted_and_re_added_not_updated(self):
        """SecItemUpdate leaves the old ACL in place, so an in-place rotation
        would hand the next build an item it cannot delete."""
        sec = _FakeSec(add=(KC._ERR_DUPLICATE_ITEM, 0))
        store = _store(sec)
        store._peek = lambda key: None
        store.put_secret("acct", "value")
        self.assertEqual(_ops(sec), ["add", "delete", "add"])
        self.assertNotIn("update", _ops(sec))

    def test_the_replacement_carries_the_explicit_acl(self):
        sec, cf = _FakeSec(add=(KC._ERR_DUPLICATE_ITEM, 0)), _FakeCF()
        store = _store(sec, cf)
        store._peek = lambda key: None
        store.put_secret("acct", "value")
        _, attrs = [c for c in sec.calls if c[0] == "add"][-1]
        self.assertEqual(cf.dicts[attrs]["kSecAttrAccess"], _ACCESS)

    def test_a_replacement_that_will_not_add_puts_the_previous_key_back(self):
        """The delete landed and the re-add did not. The caller is told nothing
        was saved, so the provider must not be left holding no credential."""
        sec = _FakeSec(add=(KC._ERR_DUPLICATE_ITEM,
                            KC._ERR_INTERACTION_NOT_ALLOWED, 0))
        cf = _FakeCF()
        store = _store(sec, cf)
        store._peek = lambda key: "previous"
        with self.assertRaises(KC.KeychainError) as caught:
            store.put_secret("acct", "replacement")
        self.assertEqual(caught.exception.status, KC._ERR_INTERACTION_NOT_ALLOWED)
        self.assertEqual(cf.data_bytes[-1], b"previous")

    def test_nothing_is_put_back_when_there_was_nothing_to_read(self):
        sec = _FakeSec(add=(KC._ERR_DUPLICATE_ITEM, KC._ERR_AUTH_FAILED))
        store = _store(sec)
        store._peek = lambda key: None
        with self.assertRaises(KC.KeychainError):
            store.put_secret("acct", "value")
        self.assertEqual(_ops(sec), ["add", "delete", "add"])


# ----------------------------------------------------------------- delete ----

class DeleteFallsBackToTheCLIOnAnOwnerEdit(unittest.TestCase):
    def test_minus_25244_shells_out_and_succeeds_quietly(self):
        sec = _FakeSec(delete=KC._ERR_INVALID_OWNER_EDIT)
        store = _store(sec)
        store._cli_delete = mock.Mock(return_value=True)
        store.delete_secret("acct")
        store._cli_delete.assert_called_once_with("acct")

    def test_minus_25244_still_raises_when_the_cli_cannot_help(self):
        sec = _FakeSec(delete=KC._ERR_INVALID_OWNER_EDIT)
        store = _store(sec)
        store._cli_delete = mock.Mock(return_value=False)
        with self.assertRaises(KC.KeychainError) as caught:
            store.delete_secret("acct")
        self.assertEqual(caught.exception.status, KC._ERR_INVALID_OWNER_EDIT)
        self.assertIn("-25244", str(caught.exception))

    def test_a_locked_keychain_does_not_shell_out(self):
        """The CLI cannot unlock anything. Shelling out here would replace one
        honest failure with two."""
        sec = _FakeSec(delete=KC._ERR_INTERACTION_NOT_ALLOWED)
        store = _store(sec)
        store._cli_delete = mock.Mock(return_value=True)
        with self.assertRaises(KC.KeychainError):
            store.delete_secret("acct")
        store._cli_delete.assert_not_called()

    def test_an_absent_item_is_success_and_no_subprocess(self):
        sec = _FakeSec(delete=KC._ERR_ITEM_NOT_FOUND)
        store = _store(sec)
        store._cli_delete = mock.Mock(return_value=True)
        store.delete_secret("acct")
        store._cli_delete.assert_not_called()


class TheCLIDeleteCarriesNoSecret(unittest.TestCase):
    """The module docstring declines the `security` CLI for writes because
    `-w <secret>` puts the key in argv, where `ps` can read it. This asserts the
    delete really is the exception it claims to be."""

    def _run(self, returncode=0):
        done = mock.Mock(returncode=returncode)
        with mock.patch.object(KC.subprocess, "run", return_value=done) as run:
            ok = _store(_FakeSec(), service="com.sutra.svc")._cli_delete("acct")
        return ok, run

    def test_the_argv_is_a_service_and_an_account_and_nothing_else(self):
        ok, run = self._run()
        self.assertTrue(ok)
        argv = run.call_args[0][0]
        self.assertEqual(argv, ["/usr/bin/security", "delete-generic-password",
                                "-s", "com.sutra.svc", "-a", "acct"])
        self.assertNotIn("-w", argv)

    def test_the_output_is_dropped(self):
        """`security` prints the deleted item's attributes. None of it is read,
        logged, or put in an exception."""
        _, run = self._run()
        self.assertEqual(run.call_args[1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args[1]["stderr"], subprocess.DEVNULL)

    def test_an_item_already_gone_counts_as_deleted(self):
        ok, _ = self._run(returncode=KC._CLI_ITEM_NOT_FOUND)
        self.assertTrue(ok)

    def test_any_other_exit_code_is_a_failure(self):
        ok, _ = self._run(returncode=1)
        self.assertFalse(ok)

    def test_a_security_binary_that_will_not_run_is_a_failure_not_a_crash(self):
        with mock.patch.object(KC.subprocess, "run", side_effect=OSError("nope")):
            self.assertFalse(_store(_FakeSec())._cli_delete("acct"))


# --------------------------------------------------------------- messages ----

class AFailureNamesItsOSStatus(unittest.TestCase):
    def test_a_locked_keychain_and_a_foreign_owner_do_not_read_alike(self):
        locked = KC.describe_failure(
            KC.KeychainError(KC._ERR_INTERACTION_NOT_ALLOWED, "delete"))
        foreign = KC.describe_failure(
            KC.KeychainError(KC._ERR_INVALID_OWNER_EDIT, "delete"))
        self.assertNotEqual(locked, foreign)
        self.assertIn("locked", locked)
        self.assertIn("different build", foreign)

    def test_the_number_is_always_there(self):
        for status in (KC._ERR_INVALID_OWNER_EDIT, KC._ERR_INTERACTION_NOT_ALLOWED,
                       KC._ERR_MISSING_ENTITLEMENT, -99999):
            self.assertIn(str(status),
                          KC.describe_failure(KC.KeychainError(status, "delete")))

    def test_something_that_is_not_a_keychain_error_gives_its_type(self):
        self.assertEqual(KC.describe_failure(OSError("locked")), "OSError")

    def test_nothing_from_the_exception_text_is_quoted(self):
        """An exception's text could hold a local that holds the key. Only the
        TYPE and this module's own status table are ever read."""
        self.assertNotIn("hunter2", KC.describe_failure(OSError("hunter2")))


# ------------------------------------------------------------ integration ----

@unittest.skipUnless(KC.keychain_available(), "needs a macOS login keychain")
class AgainstTheRealLoginKeychain(unittest.TestCase):
    """Its own service name, so nothing here can touch a real provider key."""

    SERVICE = "com.sutra.provider.test-keychain-access"
    ACCOUNT = "test:keychain-access"

    def setUp(self):
        self.store = KC.KeychainCredentialStore(service=self.SERVICE)
        self.addCleanup(self._wipe)
        self._wipe()

    def _wipe(self):
        subprocess.run(["/usr/bin/security", "delete-generic-password",
                        "-s", self.SERVICE, "-a", self.ACCOUNT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_save_read_rotate_delete(self):
        from connectors.credentials import CredentialNotFound
        self.store.put_secret(self.ACCOUNT, "first")
        self.assertEqual(self.store.get_secret(self.ACCOUNT), "first")
        self.store.put_secret(self.ACCOUNT, "second")
        self.assertEqual(self.store.get_secret(self.ACCOUNT), "second")
        self.store.delete_secret(self.ACCOUNT)
        with self.assertRaises(CredentialNotFound):
            self.store.get_secret(self.ACCOUNT)

    def test_an_item_owned_by_another_binary_is_still_removable(self):
        """`security` is a DIFFERENT code identity from this interpreter, so an
        item it creates reproduces the shipped bug exactly: SecItemDelete
        answers -25244 (asserted below, so this test fails loudly if a future
        macOS stops behaving that way) and delete_secret must still remove it.

        The `-w` here is the one place a secret would reach argv, which is why
        the value is a fixed non-secret string.
        """
        subprocess.run(["/usr/bin/security", "add-generic-password",
                        "-s", self.SERVICE, "-a", self.ACCOUNT, "-w", "not-a-secret"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        owned = []
        try:
            raw = self.store._sec.SecItemDelete(
                self.store._cfdict(self.store._base_query(self.ACCOUNT, owned)))
        finally:
            self.store._release(owned)
        self.assertEqual(raw, KC._ERR_INVALID_OWNER_EDIT)

        self.store.delete_secret(self.ACCOUNT)          # the fallback
        found = subprocess.run(["/usr/bin/security", "find-generic-password",
                                "-s", self.SERVICE, "-a", self.ACCOUNT],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertNotEqual(found.returncode, 0, "the item survived delete_secret")

    def test_a_rotated_item_is_editable_by_another_identity(self):
        """The regression that shipped: rotation used to update in place and
        keep the old ACL. `security` stands in for the next build of Sutra."""
        subprocess.run(["/usr/bin/security", "add-generic-password",
                        "-s", self.SERVICE, "-a", self.ACCOUNT, "-w", "not-a-secret"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        self.store.put_secret(self.ACCOUNT, "rotated")
        self.assertEqual(self.store.get_secret(self.ACCOUNT), "rotated")
        owned = []
        try:
            raw = self.store._sec.SecItemDelete(
                self.store._cfdict(self.store._base_query(self.ACCOUNT, owned)))
        finally:
            self.store._release(owned)
        self.assertEqual(raw, 0, "the replacement kept an ACL this build cannot edit")


if __name__ == "__main__":
    unittest.main()
