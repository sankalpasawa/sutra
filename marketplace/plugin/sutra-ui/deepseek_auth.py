"""DeepSeek sign-in: validate a key, put it in the keychain, take it out again.

WHY A SEPARATE MODULE FROM providers.py
---------------------------------------
The split codex already has. providers.py answers WHERE a credential would come
from and whether one is there (`codex_auth`, `_codex_credential_present`);
codex_login.py performs the ACTIONS that change it. This module is DeepSeek's
half of the second half. The RESOLVER stays in providers.py --
`providers.deepseek_key_for_request()` is what the rest of the app reads
through -- and it imports this module lazily, inside the function body, so the
dependency runs one way at import time and both files can name each other.

WHY THE KEYCHAIN AND NOT settings.json
--------------------------------------
settings.json is plaintext (`providers._write_settings` -> `json.dumps`), and a
live API key in it is readable by anything that can read the operator's home.
connectors/credentials/keychain.py already exists, is already imported by this
app (connectors_api.py:30), talks to Security.framework through ctypes rather
than shelling out to `security add-generic-password -w` (so the secret never
enters argv, where any process on the machine could read it out of `ps`), and
sets kSecAttrAccessibleWhenUnlockedThisDeviceOnly -- which blocks iCloud
Keychain sync, so a key pasted on this Mac cannot silently appear on another.

Electron `safeStorage` was considered and REJECTED. Every consumer of this key
is Python: app.py's ws_chat connect gate, the `DEEPSEEK_API_KEY` it puts in the
spawn env for `deepseek --acp` (app.py:2165), and deepseek_usage.py's balance
fetch. Python cannot decrypt a safeStorage blob, so storing it there would make
the Electron main process a required proxy for every read -- including the
ws_chat read, which happens with no renderer in the loop at all.

NO MemoryCredentialStore FALLBACK
---------------------------------
connectors_api._foundation() degrades to it with a warning. That is right for a
connector the operator can re-authorise in one click; it is wrong here. An
in-process dict holds the key until the backend restarts, while the mask in
settings.json outlives it -- so the row would claim "signed in" with nothing
behind it. That is precisely the readiness lie providers.py's DeepSeek gate now
exists to stop. When there is no keychain, saving is REFUSED and says why.

WHAT NEVER LEAVES THIS MODULE
-----------------------------
The key. `read()` returns it to the two call sites that authenticate with it and
to nothing else. It is never logged, never interpolated into an exception
message, never written to settings.json, and never returned to a route: what a
caller may see is `mask()` -- "sk-****4f2a", built from the last four
characters and nothing more.
"""
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import providers

# The plugin tree ships whole (bundle-runtime.sh rsyncs marketplace/plugin/), so
# connectors/ is a sibling of sutra-ui/ in both dev and the app payload. Same
# insert connectors_api.py:26 performs, for the same reason.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1])
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

#: Keychain coordinates. A NEW namespace, deliberately not the connectors'
#: "com.sutra.connector": a provider credential is not a connector, and sharing
#: the service would put this item in reach of a connector-side sweep
#: (`CredentialStore.delete_all`) that knows nothing about it. Both strings are
#: part of the on-disk contract -- changing either orphans every saved key, so
#: they are named here once and read from nowhere else.
KEYCHAIN_SERVICE = "com.sutra.provider"
KEYCHAIN_ACCOUNT = "deepseek:api-key"

#: Where the NON-SECRET record of a saved key lives, inside settings.json:
#:     "deepseek_key": {"mask": "sk-****4f2a", "saved_at": 1757260000.0}
#: This is what the provider row renders from, so drawing the row costs zero
#: keychain reads -- see providers._deepseek_key_present().
SETTINGS_KEY = "deepseek_key"

#: The validation probe. Cheapest authenticated GET the API exposes: it lists
#: models, takes no body, and answers 401 on a bad key. Same host as
#: deepseek_usage.py's BALANCE_URL.
#:
#: UNVERIFIED AGAINST THE LIVE API (no key on the machine this was written on).
#: The path is DeepSeek's documented OpenAI-compatible /models endpoint; if it
#: ever answers 404 for a VALID key, `classify()` reports that as
#: "probe-unrecognised" rather than as a rejected key, so the failure names
#: itself instead of blaming the operator's paste.
MODELS_URL = "https://api.deepseek.com/models"

PROBE_TIMEOUT = 8.0

#: Longer than any key DeepSeek issues (~35 chars) and short enough that a
#: pasted file cannot become a keychain item. Mirrors the 400 cap main.js
#: applies to the codex key.
MAX_KEY_LEN = 400

#: Below this, the last four characters ARE most of the key, so nothing is
#: shown. A real key is ~35 characters and never reaches this branch.
_MASKABLE_MIN = 12


class DeepSeekAuthError(RuntimeError):
    """A refusal with a machine-readable `code` and a sentence for the operator.

    The message is built from FIXED strings and never from the submitted key or
    from a transport exception's text.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ mask ----

def mask(key):
    """"sk-****4f2a" -- the last four characters, and the sk- prefix if it is
    really there. The only projection of a key that may cross a process
    boundary."""
    k = (key or "").strip()
    if len(k) < _MASKABLE_MIN:
        return "****"
    return ("sk-****" if k.startswith("sk-") else "****") + k[-4:]


# ----------------------------------------------------------------- store ----

def store_status():
    """(available, reason). `reason` is a sentence naming why sign-in cannot be
    offered on this machine, or None when it can."""
    try:
        from connectors.credentials import keychain_available
    except Exception as exc:                      # pragma: no cover - import guard
        return False, ("the credential store could not be loaded (%s), so there "
                       "is nowhere to keep a key safely on this machine"
                       % type(exc).__name__)
    if keychain_available():
        return True, None
    import platform
    if platform.system() != "Darwin":
        return False, ("saving a key needs the macOS login keychain and this is "
                       "%s, where Sutra has no credential store yet (the "
                       "Windows DPAPI and Linux libsecret adapters are not "
                       "written). Set the key in the environment instead."
                       % platform.system())
    return False, ("the macOS login keychain did not answer -- Security.framework "
                   "would not load, so there is nowhere to keep a key safely. "
                   "Set the key in the environment instead.")


def _store():
    """The keychain store, or raise. NEVER falls back to an in-memory store --
    see the module docstring."""
    available, why = store_status()
    if not available:
        raise DeepSeekAuthError("NO_KEYCHAIN", why)
    from connectors.credentials import KeychainCredentialStore
    return KeychainCredentialStore(service=KEYCHAIN_SERVICE)


def read():
    """The stored key, or None. Never raises: a locked keychain, a deleted item
    and a machine with no store at all are all "no key" to a caller that just
    wants to authenticate, and the reason is reported by
    providers.deepseek_key_for_request() instead."""
    try:
        from connectors.credentials import CredentialNotFound
    except Exception:                             # pragma: no cover - import guard
        return None
    try:
        raw = _store().get_secret(KEYCHAIN_ACCOUNT)
    except (DeepSeekAuthError, CredentialNotFound):
        return None
    except Exception:
        # A KeychainError (OSStatus -25308 interaction-not-allowed on a locked
        # keychain, say). Swallowed for the same reason: this function's answer
        # is a key or nothing, and nothing must not become a 500.
        return None
    raw = (raw or "").strip()
    return raw or None


# ---------------------------------------------------------------- marker ----

def marker(settings=None):
    """The non-secret record of a saved key: {"mask", "saved_at"}, or {}."""
    raw = settings if settings is not None else providers._raw_settings()
    m = raw.get(SETTINGS_KEY)
    if not isinstance(m, dict) or not isinstance(m.get("mask"), str) or not m["mask"]:
        return {}
    saved = m.get("saved_at")
    return {"mask": m["mask"],
            "saved_at": saved if isinstance(saved, (int, float)) else None}


def _write_marker(key):
    raw = providers._raw_settings()
    raw[SETTINGS_KEY] = {"mask": mask(key), "saved_at": time.time()}
    providers._write_settings(raw)
    return marker()


def _clear_marker():
    raw = providers._raw_settings()
    if SETTINGS_KEY in raw:
        raw.pop(SETTINGS_KEY, None)
        providers._write_settings(raw)


def forget_stale_marker():
    """Drop a marker whose keychain item is gone.

    Called from the resolver when the two disagree. Without it the row keeps
    saying "signed in" after someone deletes the item in Keychain Access, and
    every chat fails at connect with no way to see why from the screen.
    Best-effort: a settings file that will not write is not a failed read.
    """
    try:
        _clear_marker()
    except Exception:
        pass


# ------------------------------------------------------------------ probe ---

def _classify(exc):
    """(code, sentence) for a probe failure. Built from the exception's TYPE and
    HTTP status only -- never from its text, and never from the request, which
    carries the key in an Authorization header."""
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code == 401:
            return "KEY_REJECTED", "DeepSeek rejected that key."
        if code == 403:
            return "KEY_REJECTED", ("DeepSeek accepted the key but refused the "
                                    "request -- the key may be disabled or "
                                    "scoped away from this endpoint.")
        if code == 402:
            return "BILLING", ("DeepSeek took the key and reported a billing "
                               "problem on that account. Top it up and try again.")
        if code == 429:
            return "RATE_LIMITED", ("DeepSeek rate-limited the check, so the key "
                                    "could not be confirmed. Try again shortly.")
        if code == 404:
            return "PROBE_UNRECOGNISED", (
                "the endpoint Sutra checks keys against (%s) answered 404, so "
                "this key could not be confirmed either way. That is a Sutra "
                "problem, not a problem with your key." % MODELS_URL)
        return "HTTP", ("DeepSeek answered HTTP %d, which this build does not "
                        "know how to read. The key was not saved." % code)
    if isinstance(exc, urllib.error.URLError):
        return "NETWORK", ("could not reach api.deepseek.com to check the key "
                           "(%s). Nothing was saved -- check the network and try "
                           "again." % type(getattr(exc, "reason", exc)).__name__)
    return "NETWORK", ("could not reach api.deepseek.com to check the key (%s). "
                       "Nothing was saved." % type(exc).__name__)


def validate(key):
    """One cheap authenticated GET. Returns None on success, raises
    DeepSeekAuthError with a classified reason otherwise.

    The key travels in the Authorization header of a request object that is not
    retained, and never appears in the raised message.
    """
    req = urllib.request.Request(
        MODELS_URL, headers={"Authorization": "Bearer " + key,
                             "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            if 200 <= resp.status < 300:
                return None
            raise DeepSeekAuthError(*_classify(
                urllib.error.HTTPError(MODELS_URL, resp.status, "", None, None)))
    except DeepSeekAuthError:
        raise
    except Exception as exc:
        raise DeepSeekAuthError(*_classify(exc))


# ----------------------------------------------------------------- verbs ----

def clean(submitted):
    """The key as it will be stored, or raise.

    Trimmed first: people paste with a trailing newline, and a stored key with
    one on the end is a 401 nobody can see the cause of. Internal whitespace is
    REFUSED rather than stripped -- it means a broken paste or two keys, and
    guessing which characters to keep is not a decision this code should make.
    The refusals name the paste; the value itself is never quoted back.
    """
    k = submitted.strip() if isinstance(submitted, str) else ""
    if not k:
        raise DeepSeekAuthError("NO_KEY", "no API key was given.")
    if any(c.isspace() for c in k):
        raise DeepSeekAuthError("BAD_PASTE", (
            "that does not look like one key -- it has a space or a line break "
            "inside it. Check the paste."))
    if len(k) > MAX_KEY_LEN:
        raise DeepSeekAuthError("TOO_LONG", (
            "that is too long to be an API key (%d characters). Check the paste."
            % len(k)))
    return k


def save(submitted):
    """Validate, then store. Returns the marker: {"mask", "saved_at"}.

    ORDER IS THE POINT. The env check comes first, because a key saved under a
    live override would never be used and the operator would have no way to
    tell. The keychain check comes before the network call, so a machine that
    cannot store a key does not send it anywhere to find that out. Only a key
    DeepSeek accepted is written, and the marker is written only after the
    keychain call returned -- so a "signed in" row is never drawn over a store
    that refused.
    """
    env_var = providers.deepseek_env_var()
    if env_var:
        raise DeepSeekAuthError("ENV_OVERRIDE", (
            "%s is set in this server's environment and wins over anything saved "
            "here, so a key saved now would have no effect. Unset it and restart "
            "the server first." % env_var))

    key = clean(submitted)
    store = _store()                  # raises NO_KEYCHAIN before the network call
    validate(key)                     # raises a classified reason; nothing stored

    try:
        store.put_secret(KEYCHAIN_ACCOUNT, key)
    except Exception as exc:
        raise DeepSeekAuthError("STORE_FAILED", (
            "DeepSeek accepted the key but the login keychain would not store it "
            "(%s). Nothing was saved." % type(exc).__name__))
    return _write_marker(key)


def remove():
    """Delete the stored key and its marker. Idempotent -- signing out of a
    machine that holds nothing is a success, not an error.

    The keychain item goes FIRST: if the marker were cleared first and the
    delete then failed, a live key would be left in the keychain with nothing
    on record pointing at it.
    """
    had = bool(marker())
    available, _ = store_status()
    if available:
        try:
            _store().delete_secret(KEYCHAIN_ACCOUNT)
        except Exception as exc:
            raise DeepSeekAuthError("STORE_FAILED", (
                "the login keychain would not delete the saved key (%s), so it is "
                "still there. Nothing was changed." % type(exc).__name__))
    _clear_marker()
    return {"removed": had}
