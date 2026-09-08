"""macOS Keychain adapter, via Security.framework through ctypes.

WHY NOT THE `security` CLI, which would be five lines:

    security add-generic-password -s com.sutra.connector -a <id> -w <secret>

puts the secret in argv, where any process on the machine can read it out of
`ps` for the duration of the call. The threat model already admits that local
mode does not defend against malware running as the same user (T-08), but
handing a token to `ps` is a leak we can simply decline to create.

The CLI also cannot set the accessibility class. Design 02 §2.4 claims
kSecAttrAccessibleWhenUnlockedThisDeviceOnly -- which blocks iCloud Keychain
sync, so a GitHub credential cannot silently propagate to another machine with
no connector row and no audit trail to match. Shipping the CLI version would
have made that claim false.

THE ONE PLACE THE CLI IS RIGHT IS DELETE, and it is the same argv argument
read the other way round: `security delete-generic-password -s <service> -a
<account>` passes no secret, so there is nothing in `ps` for anyone to read.
It is also the only way to remove an item whose per-process ACL belongs to a
build that no longer exists -- see delete_secret and _access_for_any_app.

Stdlib only: ctypes and subprocess are both in the standard library.
"""
import ctypes
import ctypes.util
import json
import platform
import subprocess
from typing import Optional

from ..models import Credential
from .store import CredentialNotFound, CredentialStore

SERVICE_NAME = "com.sutra.connector"

_ERR_SUCCESS = 0
_ERR_ITEM_NOT_FOUND = -25300
_ERR_DUPLICATE_ITEM = -25299
#: errSecInvalidOwnerEdit. What SecItemDelete returns for an item whose ACL
#: trusts a different code identity -- no prompt, no way for the user to grant
#: access, and permanent until the item is removed some other way. SecItemUpdate
#: does NOT report it: it answers 0 and changes the data, leaving the ACL as it
#: was, which is why put_secret replaces rather than updates.
_ERR_INVALID_OWNER_EDIT = -25244
_ERR_AUTH_FAILED = -25293
_ERR_INTERACTION_NOT_ALLOWED = -25308
_ERR_MISSING_ENTITLEMENT = -34018

#: `security`'s exit code for "no such item". Deleting what is already gone is
#: the outcome delete_secret wants, not a failure.
_CLI_ITEM_NOT_FOUND = 44

_CF_STRING_ENCODING_UTF8 = 0x08000100


class KeychainError(RuntimeError):
    def __init__(self, status, operation):
        super().__init__("Keychain %s failed with OSStatus %d" % (operation, status))
        self.status = status
        self.operation = operation


#: What each OSStatus means, in the one sentence a panel can show. The NUMBER is
#: always kept alongside it: the sentence is a reading of the status, not a
#: replacement for it, and the number is the part that survives being searched.
_STATUS_SENTENCES = {
    _ERR_INVALID_OWNER_EDIT: (
        "the saved item belongs to a different build of Sutra, and macOS lets "
        "only that build change it"),
    _ERR_INTERACTION_NOT_ALLOWED: "the login keychain is locked",
    _ERR_AUTH_FAILED: "macOS refused the keychain without asking",
    _ERR_ITEM_NOT_FOUND: "there is no such item in the login keychain",
    _ERR_MISSING_ENTITLEMENT: (
        "this build is not entitled to the keychain group it asked for"),
}


def describe_failure(exc) -> str:
    """A short reason for a keychain failure, for a sentence a user will read.

    WHY THIS EXISTS: every caller reported `type(exc).__name__`, so a locked
    keychain and an item owned by another build both reached the screen as
    "(KeychainError)". One of those is fixed by unlocking the keychain and the
    other never resolves on its own, and the OSStatus -- the only part that
    tells them apart -- was exactly the part being dropped.

    Carries nothing from the secret. A KeychainError is built from a status code
    and an operation name, both of this module's own making; anything else falls
    back to the exception's TYPE, never its text.
    """
    if isinstance(exc, KeychainError):
        sentence = _STATUS_SENTENCES.get(exc.status)
        if sentence:
            return "%s -- OSStatus %d" % (sentence, exc.status)
        return "OSStatus %d" % exc.status
    return type(exc).__name__


class _Frameworks:
    """Lazily loaded so importing this module on Linux/Windows does not explode."""
    _loaded = None

    @classmethod
    def load(cls):
        if cls._loaded is not None:
            return cls._loaded
        cf = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        sec = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/Security.framework/Security")

        cf.CFStringCreateWithBytes.restype = ctypes.c_void_p
        cf.CFStringCreateWithBytes.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32, ctypes.c_bool]
        cf.CFDataCreate.restype = ctypes.c_void_p
        cf.CFDataCreate.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long]
        cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_char)
        cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        cf.CFDataGetLength.restype = ctypes.c_long
        cf.CFDataGetLength.argtypes = [ctypes.c_void_p]
        cf.CFDictionaryCreateMutable.restype = ctypes.c_void_p
        cf.CFDictionaryCreateMutable.argtypes = [
            ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
        cf.CFDictionarySetValue.restype = None
        cf.CFDictionarySetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        cf.CFRelease.restype = None
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFArrayGetCount.restype = ctypes.c_long
        cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]

        sec.SecItemAdd.restype = ctypes.c_int32
        sec.SecItemAdd.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        sec.SecItemCopyMatching.restype = ctypes.c_int32
        sec.SecItemCopyMatching.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        sec.SecItemDelete.restype = ctypes.c_int32
        sec.SecItemDelete.argtypes = [ctypes.c_void_p]
        sec.SecItemUpdate.restype = ctypes.c_int32
        sec.SecItemUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        # The ACL trio. Deprecated in favour of access groups, which need an
        # entitlement this process cannot have -- see _access_for_any_app.
        sec.SecAccessCreate.restype = ctypes.c_int32
        sec.SecAccessCreate.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        sec.SecAccessCopyACLList.restype = ctypes.c_int32
        sec.SecAccessCopyACLList.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        sec.SecACLSetContents.restype = ctypes.c_int32
        sec.SecACLSetContents.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint16]

        const = lambda name: ctypes.c_void_p.in_dll(sec, name)
        keys = {
            name: const(name) for name in (
                "kSecClass", "kSecClassGenericPassword", "kSecAttrService",
                "kSecAttrAccount", "kSecValueData", "kSecReturnData",
                "kSecMatchLimit", "kSecMatchLimitOne", "kSecAttrAccessible",
                "kSecAttrAccessibleWhenUnlockedThisDeviceOnly", "kSecAttrLabel",
                "kSecAttrAccess",
            )
        }
        cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        type_cbs = ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        value_cbs = ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryValueCallBacks")

        cls._loaded = (cf, sec, keys, cf_true, type_cbs, value_cbs)
        return cls._loaded


def keychain_available() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        _Frameworks.load()
        return True
    except Exception:
        return False


class KeychainCredentialStore(CredentialStore):
    def __init__(self, service: str = SERVICE_NAME):
        if platform.system() != "Darwin":
            raise RuntimeError(
                "KeychainCredentialStore is macOS-only. Windows uses the DPAPI adapter "
                "and Linux the libsecret adapter; both implement the same port."
            )
        self.service = service
        self._cf, self._sec, self._k, self._true, self._kcb, self._vcb = _Frameworks.load()

    # -- CF helpers -------------------------------------------------------
    def _cfstr(self, text: str):
        raw = text.encode("utf-8")
        return self._cf.CFStringCreateWithBytes(
            None, raw, len(raw), _CF_STRING_ENCODING_UTF8, False)

    def _cfdata(self, raw: bytes):
        return self._cf.CFDataCreate(None, raw, len(raw))

    def _cfdict(self, pairs):
        d = self._cf.CFDictionaryCreateMutable(
            None, 0, ctypes.byref(self._kcb), ctypes.byref(self._vcb))
        for key, value in pairs:
            self._cf.CFDictionarySetValue(d, key, value)
        return d

    def _base_query(self, connector_id: str, owned):
        service = self._cfstr(self.service)
        account = self._cfstr(connector_id)
        owned.extend([service, account])
        return [
            (self._k["kSecClass"], self._k["kSecClassGenericPassword"]),
            (self._k["kSecAttrService"], service),
            (self._k["kSecAttrAccount"], account),
        ]

    def _access_for_any_app(self, owned):
        """A SecAccess whose ACLs trust ANY application on this Mac, or None.

        WHAT IT FIXES. SecItemAdd's default ACL trusts exactly the code identity
        that called it. Anything else that tries to CHANGE the item -- rotate
        it, delete it -- gets -25244 errSecInvalidOwnerEdit: no prompt, no way
        for the user to grant access, permanent. Sutra hits that on every
        rebuild, because the app is ad-hoc signed and each build is therefore a
        new identity, so the provider panel's Remove and Forget buttons failed
        for anyone who had saved a key from an earlier build. Measured
        2026-09-08 on macOS 25.6: add as one identity, delete as another, -25244
        both directions; with the ACL below, 0.

        WHY NOT kSecAttrAccessGroup, which is the modern answer. It needs a
        keychain-access-groups entitlement, and the backend does not run inside
        the signed app -- it runs under whichever interpreter resolveRuntime
        found, which in the install.sh layout is Apple's /usr/bin/python3, a
        binary we cannot entitle. Measured the same day: SecItemAdd with an
        access group and kSecUseDataProtectionKeychain returns -34018
        errSecMissingEntitlement. It would also move the item into the
        data-protection keychain, which the bundled-python layout could not
        find and where every key already saved would go invisible.

        THIS DOES NOT WIDEN READ ACCESS. An unrelated python3 already reads
        these items today with no prompt -- the default ACL only ever guarded
        modification -- and T-08 already places a process running as this user
        outside the threat model. What changes is that removing a key stops
        being impossible.

        None on any failure, and put_secret then adds with the default ACL: a
        key that saves and needs the CLI to delete beats a save that refuses.
        """
        label = self._cfstr("Sutra: %s" % self.service)
        owned.append(label)
        access = ctypes.c_void_p()
        if self._sec.SecAccessCreate(label, None, ctypes.byref(access)):
            return None
        owned.append(access.value)
        acls = ctypes.c_void_p()
        if self._sec.SecAccessCopyACLList(access.value, ctypes.byref(acls)):
            return None
        owned.append(acls.value)
        for index in range(self._cf.CFArrayGetCount(acls.value)):
            acl = self._cf.CFArrayGetValueAtIndex(acls.value, index)
            # A NULL application list IS the "any application" ACL. The label
            # goes back unchanged so the item still names itself in Keychain
            # Access, and the prompt selector is 0 -- never ask.
            if self._sec.SecACLSetContents(acl, None, label, 0):
                return None
        return access.value

    def _cli_delete(self, key: str) -> bool:
        """`security delete-generic-password` for an item this process is not
        allowed to change. True when the item is gone.

        THE ARGV OBJECTION IN THE MODULE DOCSTRING DOES NOT APPLY HERE. The two
        arguments are a service name and an account name, both already public
        strings in this file; no secret reaches `ps`. The item's password is not
        in the output either, and the output is dropped regardless, because
        `security` prints the deleted item's attributes.

        WHY IT WORKS WHERE SecItemDelete DOES NOT: the legacy
        SecKeychainItemDelete path the CLI takes does not make the owner check
        that returns -25244. Measured 2026-09-08 -- an item added by one code
        identity is refused through SecItemDelete and removed through this.
        """
        try:
            done = subprocess.run(
                ["/usr/bin/security", "delete-generic-password",
                 "-s", self.service, "-a", key],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=20)
        except Exception:
            return False
        return done.returncode in (0, _CLI_ITEM_NOT_FOUND)

    def _release(self, handles):
        for handle in handles:
            if handle:
                try:
                    self._cf.CFRelease(handle)
                except Exception:
                    pass

    # -- CredentialStore --------------------------------------------------
    def _add(self, key: str, secret_text: str) -> int:
        """SecItemAdd with this module's access policy. Returns the OSStatus.

        Split out of put_secret so rotation can re-run it: a replacement item
        has to be created exactly the way a first-time save is, ACL included,
        or rotation would quietly hand the next build an item it cannot delete.
        """
        secret = secret_text.encode("utf-8")
        owned = []
        try:
            data = self._cfdata(secret)
            owned.append(data)
            pairs = self._base_query(key, owned)
            pairs.append((self._k["kSecValueData"], data))
            # Blocks iCloud Keychain sync: a credential must not reach another
            # machine without a connector row and an audit trail there.
            pairs.append((self._k["kSecAttrAccessible"],
                          self._k["kSecAttrAccessibleWhenUnlockedThisDeviceOnly"]))
            # An explicit ACL, so a later build of Sutra can still delete this.
            access = self._access_for_any_app(owned)
            if access:
                pairs.append((self._k["kSecAttrAccess"], access))
            attrs = self._cfdict(pairs)
            owned.append(attrs)
            return self._sec.SecItemAdd(attrs, None)
        finally:
            self._release(owned)
            del secret

    def _peek(self, key: str):
        """The stored secret, or None. Never raises -- it exists only so that
        put_secret can put back what it was about to replace."""
        try:
            return self.get_secret(key)
        except Exception:
            return None

    def put_secret(self, key: str, secret_text: str) -> None:
        status = self._add(key, secret_text)
        if status == _ERR_DUPLICATE_ITEM:
            # ROTATION REPLACES, IT DOES NOT UPDATE. SecItemUpdate leaves the
            # stored item's ACL alone -- measured 2026-09-08 on macOS 25.6: it
            # returns 0 both for an item this process is not allowed to delete
            # and when handed kSecAttrAccess in its change dictionary, and the
            # item stays un-deletable either way. Updating in place would keep
            # every rotated key locked to whichever build first saved it, which
            # is the bug this module is being changed to fix. Deleting first
            # also keeps the old guarantee that the previous material does not
            # survive a rotation.
            previous = self._peek(key)
            self.delete_secret(key)
            status = self._add(key, secret_text)
            if status != _ERR_SUCCESS and previous is not None:
                # The delete landed and the re-add did not, so the caller is
                # about to be told nothing was saved. Put back what was there
                # first, rather than leave a working provider with no
                # credential and a message that says nothing changed.
                self._add(key, previous)
        if status != _ERR_SUCCESS:
            raise KeychainError(status, "save")

    def get_secret(self, key: str) -> str:
        owned = []
        try:
            pairs = self._base_query(key, owned)
            pairs.append((self._k["kSecReturnData"], self._true))
            pairs.append((self._k["kSecMatchLimit"], self._k["kSecMatchLimitOne"]))
            query = self._cfdict(pairs)
            owned.append(query)

            result = ctypes.c_void_p()
            status = self._sec.SecItemCopyMatching(query, ctypes.byref(result))
            if status == _ERR_ITEM_NOT_FOUND:
                raise CredentialNotFound(key)
            if status != _ERR_SUCCESS:
                raise KeychainError(status, "get")

            owned.append(result.value)
            length = self._cf.CFDataGetLength(result.value)
            pointer = self._cf.CFDataGetBytePtr(result.value)
            raw = ctypes.string_at(pointer, length)
            return raw.decode("utf-8")
        finally:
            self._release(owned)

    def delete_secret(self, key: str) -> None:
        owned = []
        try:
            query = self._cfdict(self._base_query(key, owned))
            owned.append(query)
            status = self._sec.SecItemDelete(query)
            if status == _ERR_INVALID_OWNER_EDIT and self._cli_delete(key):
                return
            # Absent is success: disconnect must be idempotent.
            if status not in (_ERR_SUCCESS, _ERR_ITEM_NOT_FOUND):
                raise KeychainError(status, "delete")
        finally:
            self._release(owned)
