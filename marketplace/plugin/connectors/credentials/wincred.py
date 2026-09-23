"""Windows Credential Manager adapter for the CredentialStore port.

The build-specific sibling of keychain.py: on the macOS build credentials live
in the login Keychain (Security.framework via ctypes); on the Windows .exe they
live in Windows Credential Manager (advapi32 CredReadW/CredWriteW/CredDeleteW
via ctypes -- no third-party dependency, same as the mac adapter's approach).

connectors/credentials/__init__.py picks the adapter by platform and exports it
under the name KeychainCredentialStore, so every caller
(deepseek_auth, codex_auth, org_api, repo, providers) is unchanged: it asks for
a store keyed by a `service` string and gets the right OS-native one.

Secrets are stored as GENERIC credentials, one per (service, key), persisted for
the local machine. The blob is UTF-8; Sutra reads only its own credentials, so
no interop encoding (UTF-16-LE) with the Credential Manager UI is required.

LIMIT: a single Credential Manager blob caps around 2560 bytes. Provider API
keys and device codes are far under that; a very large OAuth token could exceed
it, in which case CredWriteW fails loudly rather than truncating -- chunking is
a later refinement if a real token ever hits the cap.
"""
import ctypes
from ctypes import wintypes

from .store import CredentialStore, CredentialNotFound

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168

# advapi32 only exists on Windows; this module is only imported there.
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)


class _CREDENTIAL_ATTRIBUTE(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", ctypes.POINTER(ctypes.c_byte)),
    ]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTE)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_PCREDENTIAL = ctypes.POINTER(_CREDENTIAL)

_CredReadW = _advapi32.CredReadW
_CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_PCREDENTIAL)]
_CredReadW.restype = wintypes.BOOL

_CredWriteW = _advapi32.CredWriteW
_CredWriteW.argtypes = [_PCREDENTIAL, wintypes.DWORD]
_CredWriteW.restype = wintypes.BOOL

_CredDeleteW = _advapi32.CredDeleteW
_CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_CredDeleteW.restype = wintypes.BOOL

_CredFree = _advapi32.CredFree
_CredFree.argtypes = [wintypes.LPVOID]
_CredFree.restype = None

SERVICE_NAME = "com.sutra.provider"


class WindowsCredentialError(RuntimeError):
    def __init__(self, code, operation):
        self.code = code
        self.operation = operation
        super().__init__("Credential Manager %s failed (WinError %d)" % (operation, code))


def keychain_available() -> bool:
    """Credential Manager is always present on Windows; a probe write/delete
    confirms this process can actually use it."""
    probe = "com.sutra.__probe__"
    try:
        _store_raw(probe, b"1")
        _delete_raw(probe)
        return True
    except Exception:
        return False


def describe_failure(exc) -> str:
    if isinstance(exc, WindowsCredentialError):
        return "Windows Credential Manager %s failed (WinError %d)" % (exc.operation, exc.code)
    return type(exc).__name__


def _store_raw(target: str, blob: bytes) -> None:
    buf = ctypes.create_string_buffer(blob, len(blob))
    cred = _CREDENTIAL()
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = target
    if not _CredWriteW(ctypes.byref(cred), 0):
        raise WindowsCredentialError(ctypes.get_last_error(), "save")


def _read_raw(target: str) -> str:
    pcred = _PCREDENTIAL()
    if not _CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        err = ctypes.get_last_error()
        if err == ERROR_NOT_FOUND:
            raise CredentialNotFound(target)
        raise WindowsCredentialError(err, "get")
    try:
        cred = pcred.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return blob.decode("utf-8")
    finally:
        _CredFree(pcred)


def _delete_raw(target: str) -> None:
    if not _CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        err = ctypes.get_last_error()
        if err != ERROR_NOT_FOUND:            # delete must succeed when absent
            raise WindowsCredentialError(err, "delete")


class WindowsCredentialStore(CredentialStore):
    """CredentialStore backed by Windows Credential Manager. Same interface as
    KeychainCredentialStore; __init__.py exports it under that name on Windows so
    callers keyed by `service` need no change."""

    def __init__(self, service: str = SERVICE_NAME):
        self.service = service

    def _target(self, key: str) -> str:
        # One Credential Manager target per (service, key), matching the mac
        # keychain's (service, account) addressing.
        return "%s:%s" % (self.service, key)

    def put_secret(self, key: str, secret_text: str) -> None:
        _store_raw(self._target(key), secret_text.encode("utf-8"))

    def get_secret(self, key: str) -> str:
        try:
            return _read_raw(self._target(key))
        except CredentialNotFound:
            raise CredentialNotFound(key)

    def delete_secret(self, key: str) -> None:
        _delete_raw(self._target(key))
