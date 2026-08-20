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

Stdlib only: ctypes is in the standard library.
"""
import ctypes
import ctypes.util
import json
import platform
from typing import Optional

from ..models import Credential
from .store import CredentialNotFound, CredentialStore

SERVICE_NAME = "com.sutra.connector"

_ERR_SUCCESS = 0
_ERR_ITEM_NOT_FOUND = -25300
_ERR_DUPLICATE_ITEM = -25299

_CF_STRING_ENCODING_UTF8 = 0x08000100


class KeychainError(RuntimeError):
    def __init__(self, status, operation):
        super().__init__("Keychain %s failed with OSStatus %d" % (operation, status))
        self.status = status
        self.operation = operation


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

        sec.SecItemAdd.restype = ctypes.c_int32
        sec.SecItemAdd.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        sec.SecItemCopyMatching.restype = ctypes.c_int32
        sec.SecItemCopyMatching.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        sec.SecItemDelete.restype = ctypes.c_int32
        sec.SecItemDelete.argtypes = [ctypes.c_void_p]
        sec.SecItemUpdate.restype = ctypes.c_int32
        sec.SecItemUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        const = lambda name: ctypes.c_void_p.in_dll(sec, name)
        keys = {
            name: const(name) for name in (
                "kSecClass", "kSecClassGenericPassword", "kSecAttrService",
                "kSecAttrAccount", "kSecValueData", "kSecReturnData",
                "kSecMatchLimit", "kSecMatchLimitOne", "kSecAttrAccessible",
                "kSecAttrAccessibleWhenUnlockedThisDeviceOnly", "kSecAttrLabel",
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

    def _release(self, handles):
        for handle in handles:
            if handle:
                try:
                    self._cf.CFRelease(handle)
                except Exception:
                    pass

    # -- CredentialStore --------------------------------------------------
    def put_secret(self, key: str, secret_text: str) -> None:
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
            attrs = self._cfdict(pairs)
            owned.append(attrs)

            status = self._sec.SecItemAdd(attrs, None)
            if status == _ERR_DUPLICATE_ITEM:
                # Rotation: update in place so the previous material does not survive.
                query = self._cfdict(self._base_query(key, owned))
                changes = self._cfdict([(self._k["kSecValueData"], data)])
                owned.extend([query, changes])
                status = self._sec.SecItemUpdate(query, changes)
            if status != _ERR_SUCCESS:
                raise KeychainError(status, "save")
        finally:
            self._release(owned)
            del secret

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
            # Absent is success: disconnect must be idempotent.
            if status not in (_ERR_SUCCESS, _ERR_ITEM_NOT_FOUND):
                raise KeychainError(status, "delete")
        finally:
            self._release(owned)
