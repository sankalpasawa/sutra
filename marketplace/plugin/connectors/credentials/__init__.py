"""Credential storage, build-specific by platform.

The store is OS-native: the macOS build uses the login Keychain (keychain.py),
the Windows .exe uses Windows Credential Manager (wincred.py). Both implement
the same CredentialStore port, so everything above this package
(deepseek_auth, codex_auth, org_api, repo, providers) is unchanged -- it asks
for `KeychainCredentialStore(service=...)` and gets the right backend for the
build it is running on. The name stays `KeychainCredentialStore` on both so no
call site branches on platform.
"""
import platform

from .store import CredentialStore, CredentialNotFound, MemoryCredentialStore

if platform.system() == "Windows":
    from .wincred import (
        WindowsCredentialStore as KeychainCredentialStore,
        keychain_available,
        describe_failure,
    )
else:
    from .keychain import KeychainCredentialStore, keychain_available, describe_failure

__all__ = [
    "CredentialStore", "CredentialNotFound", "MemoryCredentialStore",
    "KeychainCredentialStore", "keychain_available", "describe_failure",
]
