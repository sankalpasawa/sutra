"""codex_auth.py -- remembering the Codex API key so a mode switch is reversible.

THE PROBLEM. Codex holds EXACTLY ONE credential. ~/.codex/auth.json carries
`auth_mode` set to "chatgpt" or "apikey", and signing in with one wipes the
other -- measured 2026-09-08 against codex-cli 0.153.2, in a CODEX_HOME copy so
no live credential was spent:

    before  auth_mode=chatgpt  keys: OPENAI_API_KEY, auth_mode, last_refresh, tokens
    after   auth_mode=apikey   keys: OPENAI_API_KEY, auth_mode

`tokens` and `last_refresh` are gone entirely. So a user who switches from key
to ChatGPT loses their key permanently, and Sutra never had a copy. This module
is the copy: the key goes in the keychain, and either mode can be restored on
demand. Codex still holds one credential at a time -- nothing here changes that.

WHY THIS IS A STANDALONE MODULE AND NOT AN ARM OF deepseek_auth.py
------------------------------------------------------------------
Founder direction 2026-09-08: do not touch working credential code tonight.
Four small functions below -- mask(), store_status(), _store(), clean() -- are
DUPLICATED from deepseek_auth.py rather than shared.

  >>> EXTRACTION POINT <<<
  Once this module is proven in the field, those four move to a new
  provider_keychain.py that both modules import, and this comment goes with
  them. Nothing else here belongs in that extraction: everything below the
  "codex-specific" banner is shaped by facts that are false for DeepSeek.

  What must NOT be extracted, and why the two modules are not one:
    - validate().  deepseek_auth probes api.deepseek.com and classifies 401 /
      402 / 429. Codex has no equivalent -- see NO VALIDATION below.
    - the ENV_OVERRIDE refusal. deepseek_auth.save() refuses when
      DEEPSEEK_API_KEY is set, because the variable wins over the keychain.
      The reverse is true here: providers.codex_auth() records that
      `OPENAI_API_KEY=sk-fake codex login status` STILL reports the ChatGPT
      sign-in, so auth.json beats the variable and refusing would be a false
      refusal.
    - the marker's home. See SINGLE WRITER below.
    - read(). See read_or_reason() -- deepseek_auth's collapses two different
      answers into one, which is right there and wrong here.

CODEX VALIDATES NOTHING, SO THIS MODULE DOES
--------------------------------------------
Measured 2026-09-08: `codex login --with-api-key` writes whatever it is given
and exits 0. A deliberately fake key ("sk-proj-FAKEKEY...0000") was accepted,
printed "Successfully logged in", and replaced a live ChatGPT session. codex
checks that stdin is NON-EMPTY and nothing more.

What the user then saw was not a sign-in error. It was every subsequent call
failing with a raw 401 retried five times, carrying websocket URLs and Rust
module paths -- output nobody would connect to the key they pasted ten minutes
earlier. So the check has to happen HERE.

validate() makes one cheap authenticated GET against api.openai.com/v1/models:
the same shape deepseek_auth uses, measured at ~0.4s to a 401 on a bad key, so
"too slow to check" is not a real trade.

THE PROBE RUNS BEFORE THE LOGIN, NOT AFTER. This is deliberate and it is not
where the founder's request pointed. Validating after the spawn would still let
a dead key REPLACE a working ChatGPT session -- the login is the destruction,
the store is only the record of it. Checking first means a rejected key never
reaches ~/.codex at all and the credential already there is untouched.

AN UNCONFIRMED KEY IS REFUSED, NOT SAVED WITH A CAVEAT. A network failure, a
429, or a status this build does not know all end the same way: nothing is
changed and the message says so. Saving an unchecked key would recreate exactly
the failure this section exists to stop, one step later and with a note nobody
reads. Same rule deepseek_auth.save() applies.

SINGLE WRITER: WHY THE MARKER IS NOT IN settings.json
-----------------------------------------------------
deepseek_auth keeps its non-secret marker in settings.json. That works there
because the BACKEND is the only writer. This module also runs as a SIDECAR
spawned by the desktop shell (see __main__), so backend and sidecar would be
two processes doing read-modify-write on one file -- and every caller does
exactly that (`providers._raw_settings()` -> mutate -> `_write_settings()`),
through a SHARED temp path (settings.json.tmp). Two writers there can lose an
update or interleave on the temp file itself. The marker gets its own file with
one writer instead. Resolved off providers.SETTINGS_PATH.parent so
SUTRA_UI_SETTINGS still redirects it under test.

WHAT NEVER LEAVES THIS MODULE
-----------------------------
The key. It enters on stdin, goes to the keychain, and comes back out only into
the stdin of a `codex login --with-api-key` child spawned HERE. It is never
returned by a function that a route can reach, never written to settings.json,
never logged, never interpolated into an exception message, and never printed
by the sidecar. What may cross a boundary is `display` -- the masked stub codex
itself prints, "sk-proj-***Kyt8A".

NO AUTOMATIC FALLBACK. Founder direction 2026-09-08: nothing in this module may
be called in reaction to a quota signal, a plan-exhausted error, or any other
machine-observed condition. restore() exists to serve a CLICK. Switching a user
onto per-token billing without them asking is a bill they did not agree to, and
if that is ever wanted it is an explicit prompt naming the cost, never a silent
switch. The place this would creep in is named in 07-loaders.js's codexReprobe.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import providers

# The plugin tree ships whole (bundle-runtime.sh rsyncs marketplace/plugin/), so
# connectors/ is a sibling of sutra-ui/ in both dev and the app payload. Same
# insert connectors_api.py:26 and deepseek_auth.py:63 perform.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1])
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

#: Keychain coordinates. The SERVICE is shared with deepseek_auth on purpose --
#: one namespace for provider credentials, deliberately not the connectors'
#: "com.sutra.connector" (a provider credential is not a connector, and sharing
#: that service would put this item in reach of CredentialStore.delete_all).
#: The ACCOUNT is what separates the two. Both strings are part of the on-disk
#: contract: changing either orphans every saved key.
KEYCHAIN_SERVICE = "com.sutra.provider"
KEYCHAIN_ACCOUNT = "codex:api-key"

#: The non-secret record of a saved key, in its own single-writer file:
#:     {"display": "sk-proj-***Kyt8A", "saved_at": 1757260000.0}
#: `display` is the stub CODEX printed, captured from `codex login status`
#: right after the key went live, so the row shows one string in every state
#: rather than switching between codex's mask and ours. mask() is the fallback
#: for when that capture failed.
MARKER_NAME = "codex-key.json"

#: Longer than any key OpenAI issues and short enough that a pasted file cannot
#: become a keychain item. Mirrors the 400 cap main.js already applies.
MAX_KEY_LEN = 400

#: Below this the last four characters ARE most of the key, so nothing is shown.
_MASKABLE_MIN = 12

#: `codex login --with-api-key` does no network round trip (see NO VALIDATION),
#: so this is generous only against a wedged process, not against a human.
RESTORE_TIMEOUT = 60

#: Matches providers.CODEX_STATUS_TIMEOUT.
STATUS_TIMEOUT = 10

#: The validation probe. The cheapest authenticated GET the OpenAI API exposes:
#: it lists models, takes no body, and answers 401 on a bad key. Measured
#: 2026-09-08: a fake key comes back 401 in ~0.4s.
VALIDATE_URL = "https://api.openai.com/v1/models"

PROBE_TIMEOUT = 8.0

#: Inherited variables that must not decide which credential gets stored. The
#: user's CLICK decides. Same strip main.js's codexEnv() and codex_login._env()
#: apply, and it deliberately takes CODEX_HOME with it.
_STRIP_PREFIXES = ("OPENAI_", "CODEX_")


class CodexAuthError(RuntimeError):
    """A refusal with a machine-readable `code` and a sentence for the user.

    The message is built from FIXED strings and never from the submitted key or
    from a child's output.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ================================================================= EXTRACTION
# The four functions in this block are duplicated from deepseek_auth.py by
# founder direction and move to provider_keychain.py together. Kept
# byte-comparable to their originals so the extraction is a cut-and-paste
# rather than a merge -- do not "improve" one copy in place.
# ============================================================================

def mask(key):
    """"sk-****4f2a" -- the last four characters, and the sk- prefix if it is
    really there. FALLBACK ONLY here: the row prefers codex's own stub."""
    k = (key or "").strip()
    if len(k) < _MASKABLE_MIN:
        return "****"
    return ("sk-****" if k.startswith("sk-") else "****") + k[-4:]


def store_status():
    """(available, reason). `reason` is a sentence naming why remembering a key
    cannot be offered on this machine, or None when it can."""
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
        return False, ("remembering a key needs the macOS login keychain and "
                       "this is %s, where Sutra has no credential store yet "
                       "(the Windows DPAPI and Linux libsecret adapters are "
                       "not written)." % platform.system())
    return False, ("the macOS login keychain did not answer -- Security."
                   "framework would not load, so there is nowhere to keep a "
                   "key safely.")


def _store_failure(exc):
    """Why a keychain call failed, in a phrase a user can act on.

    NOT `type(exc).__name__`, which is what the keychain messages below used
    to carry.
    A locked keychain and an item owned by a build of Sutra that no longer
    exists both arrive here as KeychainError, and they arrived on screen as the
    same word -- one of them fixed by unlocking the keychain, the other never
    resolving on its own. describe_failure keeps the OSStatus, which is the
    only part that tells them apart.

    Falls back to the type name if the connectors package will not import, so a
    machine with no credential store still gets a sentence rather than a 500.
    """
    try:
        from connectors.credentials import describe_failure
    except Exception:                             # pragma: no cover - import guard
        return type(exc).__name__
    return describe_failure(exc)


def _store():
    """The keychain store, or raise. NEVER falls back to an in-memory store: a
    dict that empties on restart, with a marker on disk that does not, would
    make the row claim a saved key that is not there."""
    available, why = store_status()
    if not available:
        raise CodexAuthError("NO_KEYCHAIN", why)
    from connectors.credentials import KeychainCredentialStore
    return KeychainCredentialStore(service=KEYCHAIN_SERVICE)


def clean(submitted):
    """The key as it will be stored, or raise.

    Trimmed first: people paste with a trailing newline, and codex would take
    the newline as the end of the key. Internal whitespace is REFUSED rather
    than stripped -- it means a broken paste or two keys, and guessing which
    characters to keep is not a decision this code should make. The refusals
    name the paste; the value is never quoted back.
    """
    k = submitted.strip() if isinstance(submitted, str) else ""
    if not k:
        raise CodexAuthError("NO_KEY", "no API key was given.")
    if any(c.isspace() for c in k):
        raise CodexAuthError("BAD_PASTE", (
            "that does not look like one key -- it has a space or a line break "
            "inside it. Check the paste."))
    if len(k) > MAX_KEY_LEN:
        raise CodexAuthError("TOO_LONG", (
            "that is too long to be an API key (%d characters). Check the paste."
            % len(k)))
    return k

# ============================================================ end EXTRACTION


# ---------------------------------------------------------------- probe ----

def _classify(exc):
    """(code, sentence) for a probe failure.

    Built from the exception TYPE and HTTP STATUS only -- never from its text,
    and never from the request, which carries the key in an Authorization
    header. Every sentence below is a fixed string.
    """
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code == 401:
            return "KEY_REJECTED", (
                "OpenAI rejected that key, so nothing was changed. Codex is "
                "still using whatever it was using before.")
        if code == 403:
            return "KEY_REJECTED", (
                "OpenAI accepted the key but refused the request -- it may be "
                "disabled, or scoped away from this endpoint. Nothing was "
                "changed.")
        if code == 402:
            return "BILLING", (
                "OpenAI took the key and reported a billing problem on that "
                "account. Codex would authenticate but every call would fail, "
                "so nothing was changed.")
        if code == 429:
            return "RATE_LIMITED", (
                "OpenAI rate-limited the check, so the key could not be "
                "confirmed either way. Nothing was changed -- try again "
                "shortly.")
        if code == 404:
            return "PROBE_UNRECOGNISED", (
                "the endpoint Sutra checks keys against (%s) answered 404, so "
                "this key could not be confirmed either way. That is a Sutra "
                "problem, not a problem with your key. Nothing was changed."
                % VALIDATE_URL)
        return "HTTP", (
            "OpenAI answered HTTP %d, which this build does not know how to "
            "read. Nothing was changed." % code)
    if isinstance(exc, urllib.error.URLError):
        return "NETWORK", (
            "could not reach api.openai.com to check the key (%s). Nothing was "
            "changed -- an unchecked key is the failure this check exists to "
            "prevent, so it is not saved on a guess."
            % type(getattr(exc, "reason", exc)).__name__)
    return "NETWORK", (
        "could not reach api.openai.com to check the key (%s). Nothing was "
        "changed." % type(exc).__name__)


def validate(key):
    """One cheap authenticated GET. None on success, CodexAuthError otherwise.

    THE CHECK CODEX DOES NOT DO. `codex login --with-api-key` takes any
    non-empty string and exits 0, so without this a typo becomes a live
    credential and the user meets it later as a raw 401 retried five times.

    The key travels in the Authorization header of a request object that is not
    retained, and never appears in the raised message.
    """
    req = urllib.request.Request(
        VALIDATE_URL, headers={"Authorization": "Bearer " + key,
                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            if 200 <= resp.status < 300:
                return None
            raise CodexAuthError(*_classify(
                urllib.error.HTTPError(VALIDATE_URL, resp.status, "", None, None)))
    except CodexAuthError:
        raise
    except Exception as exc:
        raise CodexAuthError(*_classify(exc))


def check(submitted):
    """Clean and validate a pasted key WITHOUT storing or spawning anything.

    The desktop shell calls this FIRST, before `codex login --with-api-key`, so
    a key OpenAI rejects never reaches ~/.codex and the credential already
    there survives the attempt. Returns the cleaned key's mask for the caller
    to show; the key itself does not cross back.
    """
    key = clean(submitted)
    validate(key)
    return {"mask": mask(key)}


# ---------------------------------------------------------------- marker ----

def marker_path():
    """The marker file. Derived from providers.SETTINGS_PATH so that pointing
    SUTRA_UI_SETTINGS at a tempdir moves this too -- otherwise a test run would
    read and write the operator's real marker."""
    return providers.SETTINGS_PATH.parent / MARKER_NAME


def marker():
    """{"display", "saved_at"} for a saved key, or {}. Never raises -- a corrupt
    marker is "no key on record", not a broken panel."""
    try:
        data = json.loads(marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    display = data.get("display")
    if not isinstance(display, str) or not display:
        return {}
    saved = data.get("saved_at")
    return {"display": display,
            "saved_at": saved if isinstance(saved, (int, float)) else None}


def _write_marker(key, display):
    """Atomic and 0600, for the same reasons providers._write_settings is both.

    The TEMP NAME IS OUR OWN (codex-key.json.tmp), never settings.json.tmp --
    sharing that path with the backend is the interleave this file exists to
    avoid.
    """
    path = marker_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = {"display": display or mask(key), "saved_at": time.time()}
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return marker()


def _clear_marker():
    try:
        marker_path().unlink()
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------ read ----

def read_or_reason():
    """(key, code, sentence). Exactly one of key / code is set.

    THE SPLIT deepseek_auth.read() DELIBERATELY DOES NOT MAKE, and the reason
    this module does not reuse it. That one collapses CredentialNotFound and
    KeychainError into a single None, which is correct there: its caller only
    wants to authenticate, and the resolver reports the difference separately.

    Here the caller is a TOGGLE. Telling someone their saved key is gone when
    the login keychain is merely LOCKED sends them to re-enter a key they still
    have -- and if they no longer have it, to conclude they have lost it. The
    two answers get two codes:

        NO_STORED_KEY     nothing was ever saved, or it was deleted
        STORE_UNREADABLE  something is there but the keychain would not open
        NO_KEYCHAIN       this machine has no credential store at all
    """
    available, why = store_status()
    if not available:
        return None, "NO_KEYCHAIN", why
    try:
        from connectors.credentials import CredentialNotFound
        from connectors.credentials.keychain import KeychainError
    except Exception as exc:                      # pragma: no cover - import guard
        return None, "STORE_UNREADABLE", (
            "the credential store could not be loaded (%s), so the saved key "
            "could not be read." % type(exc).__name__)
    try:
        raw = _store().get_secret(KEYCHAIN_ACCOUNT)
    except CredentialNotFound:
        return None, "NO_STORED_KEY", "there is no API key saved in Sutra."
    except KeychainError as exc:
        # OSStatus -25308 is interaction-not-allowed: a locked keychain, or one
        # that refused the prompt. The STATUS is named because it is the one
        # thing that makes this searchable; nothing else about the item is.
        return None, "STORE_UNREADABLE", (
            "the login keychain would not open the saved key (OSStatus %d). "
            "Unlock your login keychain and try again -- the key is still "
            "there." % exc.status)
    except CodexAuthError:
        raise
    except Exception as exc:
        return None, "STORE_UNREADABLE", (
            "the saved key could not be read (%s)." % _store_failure(exc))
    raw = (raw or "").strip()
    if not raw:
        return None, "NO_STORED_KEY", "there is no API key saved in Sutra."
    return raw, None, None


# --------------------------------------------------------------- display ----

def _codex_bin():
    """The BARE NAME off PATH, never providers.provider_bin("codex").

    provider_bin honours `provider_bins` in settings.json, which the RENDERER
    can set -- so using it here would let the panel choose which binary receives
    the API key on stdin. That is the hole main.js's codex verbs already refuse
    to open ("executing a path the RENDERER chose is a bigger hole than the
    inconvenience it fixes"). codex_login.py may use provider_bin because those
    verbs carry no credential; these do.

    KNOWN DIVERGENCE, pre-existing: the STATUS probe in providers.codex_auth()
    does honour the override, so on a machine with one set, the row and this
    spawn can be talking about two different binaries.
    """
    return "codex"


def _env():
    env = dict(os.environ)
    for k in list(env):
        if k.startswith(_STRIP_PREFIXES):
            del env[k]
    return env


def current_display():
    """The masked stub codex is printing right now, or "". Never raises.

    Captured after a key goes live so the marker can show CODEX's string rather
    than ours. Parsing is providers._parse_codex_status -- the single place that
    knowledge lives, so a codex build that changes the line changes both callers
    at once rather than drifting.
    """
    try:
        p = subprocess.run([_codex_bin(), "login", "status"], env=_env(),
                           capture_output=True, text=True, timeout=STATUS_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    blob = (p.stdout or "").strip() or (p.stderr or "").strip()
    state, display = providers._parse_codex_status(blob)
    return display if state == "api_key" else ""


# ----------------------------------------------------------------- verbs ----

def store(submitted):
    """Remember a key that is ALREADY LIVE. Returns the marker.

    CALLED SECOND, never first. The desktop shell has just run `codex login
    --with-api-key` with this key and seen it exit 0; this only records it so
    the switch is reversible. That order is the point: a keychain that refuses
    leaves the user correctly signed in and merely not remembered, which is a
    sentence the panel can say. The reverse order would risk the opposite.

    Does NOT mean the key is valid -- codex validated nothing. See NO VALIDATION.
    """
    key = clean(submitted)
    store_ = _store()                 # raises NO_KEYCHAIN with the reason
    try:
        store_.put_secret(KEYCHAIN_ACCOUNT, key)
    except Exception as exc:
        raise CodexAuthError("STORE_FAILED", (
            "Codex is using the key now, but the login keychain would not keep "
            "a copy (%s) -- so switching to ChatGPT and back would lose it."
            % _store_failure(exc)))
    return _write_marker(key, current_display())


def forget():
    """Delete the saved key and its marker. Idempotent.

    The keychain item goes FIRST: if the marker were cleared first and the
    delete then failed, a live key would be left in the keychain with nothing
    on record pointing at it.

    THIS DOES NOT SIGN CODEX OUT. Codex keeps whatever credential it holds --
    forgetting is about Sutra's copy, and conflating the two would make a
    tidy-up destroy a working session.
    """
    had = bool(marker())
    available, _ = store_status()
    if available:
        try:
            _store().delete_secret(KEYCHAIN_ACCOUNT)
        except Exception as exc:
            raise CodexAuthError("STORE_FAILED", (
                "the login keychain would not delete the saved key (%s), so it "
                "is still there. Nothing was changed." % _store_failure(exc)))
    _clear_marker()
    return {"removed": had}


def restore():
    """Put the saved key back in front of codex. Returns {"display": ...}.

    ONE SPAWN, NO LOGOUT FIRST -- measured 2026-09-08 against 0.153.2:
    `--with-api-key` over a live ChatGPT session overwrites it and exits 0.
    A logout first would open a window where the user holds no credential at
    all, for no gain.

    THE KEY GOES ON STDIN and never into argv, so it is not in the process list
    for anything else on this machine to read. It never enters a return value.

    SERVES A CLICK ONLY. See NO AUTOMATIC FALLBACK in the module docstring.
    """
    key, code, reason = read_or_reason()
    if key is None:
        raise CodexAuthError(code, reason)
    # CHECKED ON THE WAY BACK OUT, not just on the way in. A key that was good
    # when it was saved can be revoked, rotated or defunded later, and putting a
    # dead one live is the same raw-401 storm as saving a bad one -- just aimed
    # at someone who did nothing wrong. Costs one ~0.4s GET on a deliberate
    # click. The saved copy is LEFT ALONE when this fails: the key may be fine
    # and the network may not, and forgetting it here would destroy the only
    # copy over a transient.
    validate(key)
    try:
        p = subprocess.run(
            [_codex_bin(), "login", "--with-api-key"], env=_env(),
            input=key + "\n", capture_output=True, text=True,
            timeout=RESTORE_TIMEOUT)
    except FileNotFoundError:
        raise CodexAuthError("NO_BINARY", (
            "the `codex` CLI is not on PATH, so the saved key could not be "
            "put back."))
    except subprocess.TimeoutExpired:
        raise CodexAuthError("TIMEOUT", (
            "`codex login --with-api-key` did not finish within %ss. Nothing "
            "was changed here; run it in a terminal to see what it says."
            % RESTORE_TIMEOUT))
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexAuthError("SPAWN_FAILED", (
            "`codex login --with-api-key` could not be run (%s)."
            % type(exc).__name__))
    finally:
        key = None
    if p.returncode != 0:
        # The child's output is NOT forwarded. On this path stderr echoes the
        # read ("Reading API key from stdin...") and a future build could echo
        # more, so a fixed string crosses instead -- the same discipline
        # main.js's codexError() applies at the other layer.
        raise CodexAuthError("CODEX_REFUSED", (
            "codex exited %s without taking the saved key. Running `codex "
            "login --with-api-key` in a terminal will show what it said."
            % p.returncode))
    return {"display": current_display()}


def state():
    """What the row needs to know about Sutra's copy. Carries NO key.

        {"stored": bool, "display": str, "saved_at": float|None,
         "store_available": bool, "store_reason": str|None}

    NOT A CLAIM ABOUT THE LIVE MODE. `codex login status` is the only authority
    for what codex is using right now (providers.codex_auth); this says only
    whether there is something to restore. Merged into the route's answer, never
    substituted for it.
    """
    available, why = store_status()
    m = marker()
    return {"stored": bool(m), "display": m.get("display", ""),
            "saved_at": m.get("saved_at"),
            "store_available": available, "store_reason": why}


# --------------------------------------------------------------- sidecar ----
# HOW THE KEY REACHES THE KEYCHAIN WITHOUT TOUCHING HTTP.
#
# The desktop shell spawns this module as a child of the bundle's own python
# and writes the key to its STDIN. Precedent and rationale are main.js's
# updateCli/updates_cli.py, whose comment states it exactly: "no HTTP and no
# token: the token exists because any browser page can POST to localhost, and a
# child process is not reachable from a page."
#
# So the key crosses one pipe between two local processes. It is never in a
# request body, never through uvicorn's logging or validation surface, never in
# the backend's memory, and never in argv.
#
# THE ANSWER IS ONE JSON LINE ON STDOUT and never carries the key. Every failure
# is {"ok": false, "code", "message"} with exit 0, so the shell reads a reason
# rather than guessing from a killed process. A traceback must never reach
# stdout: it would be an unparseable answer, and on the store path the local
# variables it printed would include the key.

def _main(argv):
    verb = argv[1] if len(argv) > 1 else ""
    try:
        if verb == "store":
            # Read from the BUFFER and decode ourselves: a locale that is not
            # UTF-8 must not mangle the key on the way in.
            submitted = sys.stdin.buffer.read().decode("utf-8", "replace")
            m = store(submitted)
            return {"ok": True, "display": m.get("display", ""),
                    "saved_at": m.get("saved_at")}
        if verb == "check":
            submitted = sys.stdin.buffer.read().decode("utf-8", "replace")
            return {"ok": True, **check(submitted)}
        if verb == "restore":
            return {"ok": True, **restore()}
        if verb == "forget":
            return {"ok": True, **forget()}
        if verb == "state":
            return {"ok": True, **state()}
        return {"ok": False, "code": "BAD_VERB",
                "message": "unknown verb %r" % verb}
    except CodexAuthError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}
    except Exception as exc:
        # LAST RESORT. The type name only -- str(exc) on this path could quote
        # a local that holds the key.
        return {"ok": False, "code": "UNEXPECTED",
                "message": "the credential helper failed (%s)."
                           % type(exc).__name__}


if __name__ == "__main__":
    sys.stdout.write(json.dumps(_main(sys.argv)) + "\n")
