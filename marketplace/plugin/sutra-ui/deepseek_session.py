"""One-time pairing code: how a BROWSER earns the right to write a DeepSeek key.

THE PROBLEM
-----------
POST /api/providers/deepseek/key is token-gated, and until now the only token
that existed was SUTRA_DESKTOP_TOKEN -- minted by the Electron shell, handed
only to the backend it spawns, attached by the MAIN process so the renderer
never holds it. That is the right shape for the desktop app and it leaves a
browser at 127.0.0.1 with no way in at all: deepseekAuthHtml() renders "saving
one is a desktop-app action" and draws no field. So a CLI-run server cannot
sign in to DeepSeek from its own UI -- which is where development and testing
of this app happen.

THIS IS NOT AN UNAUTHENTICATED ROUTE WITH EXTRA STEPS
-----------------------------------------------------
The exchange route demands a secret that exists in exactly one place: the
STDOUT of the process the operator started. A web page cannot read a terminal.
So the capability is not granted by asking for it -- it is granted by the
operator copying it out of their own terminal, the same trust move as an ssh
host-key fingerprint or a device-pairing code. Two locks, not one:

  1. the code, which is only on the server's stdout; and
  2. app.py's origin guard, which refuses a cross-origin mutation that does not
     carry PANEL_TOKEN -- and PANEL_TOKEN is served only inside the panel HTML,
     which another origin can trigger a request to but can never READ.

A hostile page has neither. A local PROCESS could have both (it can read the
terminal, and it sends no Origin so the guard lets it by) -- and that is not a
new exposure: local processes are already outside this server's declared threat
model (app.py's origin-guard comment, providers.editing_allowed), and a process
that can read the operator's terminal can already read the keychain the moment
the operator unlocks it. This adds a door for the operator, not for anyone new.

WHY NO CODE WHEN SUTRA_DESKTOP_TOKEN IS SET
-------------------------------------------
Then the shell already owns the write path and a second door would exist for no
reason. `arm()` mints nothing in that case, `state()` says so, and the browser
row keeps telling you to use the app. The desktop posture is byte-for-byte what
it was.

WHY STDOUT AND NOT A FILE
-------------------------
A file is readable by every process on the machine and outlives the process
that wrote it. stdout is transient and belongs to whoever launched the server --
the one person this code is trying to authorise.

SINGLE USE, ONE TOKEN, NO PERSISTENCE
-------------------------------------
The code is burned on the first SUCCESSFUL exchange, so a second browser (or a
second person who read the terminal over a shoulder) cannot pair later in the
same run. Because the code is single-use, at most one session token can ever
exist per process -- so this module holds ONE token, not a set. Nothing here is
written to disk: restart the server and every code and token minted by the old
process is gone, which is the whole of the expiry policy.

THE CODE NEVER LEAVES THIS MODULE
---------------------------------
`state()` is folded into GET /api/settings, which is UNAUTHENTICATED. It reports
whether a code exists and never what it is. The only egress for the code itself
is `banner()`, whose caller prints it to stdout.
"""
import hmac
import os
import secrets
import sys

#: The request header the paired browser sends. Named here because org_api reads
#: it, the panel writes it, and the tests assert on it -- three places that must
#: agree on one string.
HEADER = "x-sutra-session-token"

#: Crockford base32: 32 symbols with I, L, O and U left out, because this string
#: gets read off a terminal and retyped. 4 groups of 4 is 80 bits, which is the
#: point of the grouping -- see _canonical() for the forgiving read-back.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_GROUPS, _GROUP_LEN = 4, 4

#: NO ATTEMPT CAP, deliberately. A cap on an 80-bit secret behind a loopback
#: socket protects nothing -- guessing it at ten thousand requests a second
#: takes longer than the universe has run -- while a cap turns a fat-fingered
#: paste into "restart the server", which is the failure this whole module
#: exists to remove. What IS bounded is success: one exchange, ever.

_code = None          # the canonical unclaimed code, or None
_claimed = False      # a code was minted AND exchanged -- distinct from never minted
_token = None         # the one session token this process will ever mint
_armed = False        # arm() ran; guards a double startup hook


class SessionCodeError(RuntimeError):
    """A refused exchange, with a machine-readable `code` and one sentence for
    the operator. Built from FIXED strings -- never from the submitted value."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _desktop_token_present():
    return bool(os.environ.get("SUTRA_DESKTOP_TOKEN"))


def _canonical(value):
    """The comparable form of a code: uppercased, Crockford-folded, and stripped
    of everything that is not an alphabet symbol.

    So "wxyz-2345-6789-abcd", "WXYZ2345 6789ABCD" and a paste that picked up a
    trailing newline are all the same code, and O/o read back as 0 and I/i/L/l
    as 1 -- the substitutions Crockford's alphabet exists to make safe. The
    result is ASCII, which is what hmac.compare_digest requires of a str.
    """
    if not isinstance(value, str):
        return ""
    folded = (value.upper()
              .replace("O", "0").replace("I", "1").replace("L", "1"))
    return "".join(c for c in folded if c in _ALPHABET)


def _mint_code():
    return "".join(secrets.choice(_ALPHABET)
                   for _ in range(_GROUPS * _GROUP_LEN))


def display(code):
    """The dashed form, for reading off a terminal. Grouping only -- the code is
    the canonical string, and _canonical() throws the dashes away again."""
    return "-".join(code[i:i + _GROUP_LEN]
                    for i in range(0, len(code), _GROUP_LEN))


# ------------------------------------------------------------------- arm ----

def arm():
    """Mint the process's one pairing code, or decline to. Idempotent.

    Returns the DISPLAY form when a code was just minted, and None when this
    process will not offer one -- either because the desktop shell already owns
    the write path, or because arm() already ran.
    """
    global _code, _armed
    if _armed:
        return None
    _armed = True
    if _desktop_token_present():
        return None
    _code = _mint_code()
    return display(_code)


#: ASCII ONLY, and not for the house style's sake (D-UX-1 governs the panel, not
#: this). stdout here can be a Windows console at cp1252 or a pipe whose encoding
#: Python guessed as ascii; a box-drawing character there is a
#: UnicodeEncodeError during startup, and losing the server to decoration would
#: be a genuinely stupid way to fail.
def banner():
    """The lines to print on stdout, or []. The ONLY egress for the code."""
    if not _code:
        return []
    return [
        "",
        "  +-- Sutra: DeepSeek sign-in code -------------------------------+",
        "  |                                                              |",
        "  |    %-58s|" % display(_code),
        "  |                                                              |",
        "  |  Paste it into the DeepSeek row under                        |",
        "  |  Settings -> AI Assistant to unlock the API-key field in a   |",
        "  |  browser. Single use. It dies with this server and is never  |",
        "  |  written to disk.                                            |",
        "  +--------------------------------------------------------------+",
        "",
    ]


def print_banner(stream=None):
    """Write banner() to stdout, flushed. Never raises: a redirected, closed or
    narrowly-encoded stdout must not take startup down with it -- the row still
    says a code exists, and the operator can restart with a terminal
    attached."""
    lines = banner()
    if not lines:
        return False
    out = stream if stream is not None else sys.stdout
    try:
        out.write("\n".join(lines) + "\n")
        out.flush()
    except Exception:
        return False
    return True


# ----------------------------------------------------------------- state ----

def state():
    """What the DeepSeek row needs to decide which field to draw.

    NEVER THE CODE. This rides in GET /api/settings, which is unauthenticated,
    so what leaves here is three booleans and a fixed sentence. `claimed` is
    separate from `available` on purpose: a browser that does not hold the token
    has to be told the difference between "paste the code" and "the code was
    already used and only a restart makes another one".
    """
    if _desktop_token_present():
        return {"available": False, "claimed": False, "reason": (
            "this server was started by the Sutra desktop app, which already "
            "owns the key-writing channel, so no browser sign-in code was "
            "issued. Sign in from the app window.")}
    if _code:
        return {"available": True, "claimed": False, "reason": None}
    if _claimed:
        return {"available": False, "claimed": True, "reason": (
            "this server's sign-in code has already been used once, and it is "
            "single-use. Restart the server to get a new one.")}
    return {"available": False, "claimed": False, "reason": (
        "this server issued no sign-in code, so there is no way to authorise a "
        "key write from a browser. Restart it from a terminal, where the code "
        "is printed.")}


# -------------------------------------------------------------- exchange ----

def exchange(submitted):
    """Trade the one-time code for the session token, or raise.

    compare_digest on the CANONICAL form -- same discipline as app.py:883 and
    org_api._desktop_control. The length of a code is public (it is printed), so
    comparing unequal lengths leaks nothing; what must not leak is which
    characters matched, and that is what compare_digest is for.

    The code is burned only on SUCCESS. A typo has to be retryable or the
    forgiving read-back in _canonical() would be pointless.
    """
    global _code, _claimed, _token
    if _desktop_token_present():
        raise SessionCodeError("NOT_OFFERED", state()["reason"])
    got = _canonical(submitted)
    if not got:
        raise SessionCodeError("NO_CODE", "no sign-in code was given.")
    if not _code:
        raise SessionCodeError("CLAIMED" if _claimed else "NOT_OFFERED",
                               state()["reason"])
    if not hmac.compare_digest(got, _code):
        raise SessionCodeError("BAD_CODE", (
            "that is not this server's sign-in code. It is printed on the "
            "server's own output when it starts -- look in the terminal you "
            "launched it from."))
    _code = None                    # single use, burned before the token exists
    _claimed = True
    _token = secrets.token_urlsafe(32)
    return _token


def verify(sent):
    """Does this header value authorise a DeepSeek key write?

    compare_digest again, and `_token` is checked for existence FIRST so an
    unpaired process cannot be talked into comparing against None.
    """
    if not _token or not isinstance(sent, str) or not sent:
        return False
    return hmac.compare_digest(sent, _token)


def _reset_for_tests():
    """Return the module to its pre-arm() state. Tests only -- there is no
    operational reason to re-arm a process, and offering one would turn a
    single-use code into an unlimited supply of them."""
    global _code, _claimed, _token, _armed
    _code, _claimed, _token, _armed = None, False, None, False
