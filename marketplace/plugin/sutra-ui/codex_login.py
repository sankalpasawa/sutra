"""codex_login.py -- spawning `codex login` and `codex logout` server-side.

WHY THIS EXISTS SEPARATELY FROM THE DESKTOP SHELL

The Codex sign-in actions were built first as Electron IPC verbs, which made
them unreachable to anyone running the panel in a browser -- and Electron does
not install on every machine. These two verbs carry NO CREDENTIAL: `codex
login` opens a browser flow that completes inside codex itself, and `codex
logout` deletes what codex holds. So they can ride HTTP, and the worst a caller
gets is a visible browser window or a sign-out.

The API KEY verb does NOT live here and must not be added. `codex login
--with-api-key` reads the key from stdin, and routing it through HTTP would put
a live credential in a request body, through uvicorn's logging and validation
surface, and into this process's memory. None of that is about access control,
so no origin guard makes it acceptable. It stays on the IPC bridge.

WHY THAT IS SAFE HERE, MEASURED RATHER THAN ASSUMED

app.py's origin guard refuses every mutating request that carries a
non-loopback Origin, and demands the per-boot panel token from any request that
carries an Origin at all -- so a hostile web page cannot reach these routes
(verified against a live server: an evil Origin gets 403, a loopback Origin
without the token gets 403). The one caller the guard admits without a token is
a NON-BROWSER local process, and such a process can already run `codex logout`
in a shell. These routes hand it no authority it did not have.

The remaining worry was login-CSRF: an attacker triggering a login and
completing it into this machine's CLI with their own account, so the operator's
subsequent codex work flows into it. codex 0.153.2's flow carries PKCE and a
state parameter (`code_challenge`, `code_verifier`, `state=` are all present in
the binary), so completing it would need the verifier and state out of the
codex process. Not reachable by triggering a login.

NOTHING BLOCKS ON A HUMAN. `codex login` waits for a browser round-trip, which
can be three minutes or never. Held open as an HTTP request that would park a
threadpool worker, leave the panel with no cancel signal (apiGet has no
timeout), and orphan the child on a page reload. So start() returns the moment
the child is spawned and the panel polls `codex login status` instead -- the
credential CHANGING is a better completion signal than the child's exit code
anyway.

Reads: PATH (through providers), and the codex binary's location.
Writes: nothing. codex owns the credential; Sutra never holds any part of it.
"""
import os
import subprocess
import threading

import providers

#: How long a walked-away sign-in is allowed to hold a child. The browser flow
#: is a human round-trip, so this is generous -- but it is not unbounded: an
#: abandoned `codex login` keeps a /auth/callback listener bound, and the next
#: attempt would collide with it. Matches the desktop shell's own cap.
#: Module-level so tests can shrink it rather than sleep for three minutes.
CAP_SECONDS = 180

#: `codex logout` has no human in the loop -- it deletes a file and returns.
LOGOUT_TIMEOUT = 30

#: Grace between SIGTERM and SIGKILL, same as the desktop shell's.
KILL_GRACE = 5

#: Inherited variables that must not decide which credential gets stored. The
#: operator's CLICK decides. The status PROBE deliberately does NOT strip these
#: (see providers.codex_auth) -- it has to report what codex reports.
_STRIP_PREFIXES = ("OPENAI_", "CODEX_")


class Busy(RuntimeError):
    """Another codex credential operation is already running."""


class NoBinary(RuntimeError):
    """The codex CLI is not on this server's PATH."""


# One lock, one operation at a time, across BOTH verbs. They all end in the
# same single credential -- codex keeps exactly one -- so letting a logout race
# a login would leave the operator's real state decided by whichever process
# finished last. Same rule the desktop shell enforces with its single child.
#
# The lock is NEVER held across a subprocess: every critical section below is
# a few pointer writes. A lock held for the 30s of a logout would make a
# concurrent request queue for 30s instead of being told the truth immediately.
_lock = threading.Lock()
_child = None            # the live `codex login` Popen, or None
_busy = None             # None | "login" | "logout"


def _env():
    env = dict(os.environ)
    for k in list(env):
        if k.startswith(_STRIP_PREFIXES):
            del env[k]
    return env


def _watch(child):
    """Wait out one login child: enforce the cap, then clear the slot.

    The watchdog and the reaper are the SAME thread on purpose. A separate
    reaper would mean in_flight() could report a zombie as live, and a
    watchdog without a reaper would leave the slot occupied after a kill --
    both of which end with the panel showing a sign-in that is not happening.
    """
    global _child, _busy
    try:
        child.wait(timeout=CAP_SECONDS)
    except subprocess.TimeoutExpired:
        # Walked away, or the browser flow was never completed. Reclaim the
        # callback port rather than leaving a child holding it forever.
        try:
            child.terminate()
        except OSError:
            pass
        try:
            child.wait(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired:
            try:
                child.kill()
            except OSError:
                pass
            try:
                child.wait(timeout=KILL_GRACE)
            except subprocess.TimeoutExpired:
                pass
    finally:
        with _lock:
            if _child is child:
                _child = None
                _busy = None


def start():
    """Spawn `codex login` and return IMMEDIATELY.

    {"started": True, "pid": ..., "cap_seconds": CAP_SECONDS}

    Raises Busy when an operation is already running, NoBinary when codex is
    not on PATH -- answered by provider_bin alone, without spawning anything.

    The child is deliberately NOT put in its own session (no
    start_new_session): this process is the only thing tracking it, so it
    should not outlive the server. An orphan would keep the /auth/callback
    listener bound with nothing able to cancel it.

    Output goes to DEVNULL. codex prints the sign-in URL as a fallback for when
    the browser does not open, and forwarding that would mean reading the
    child's stdout -- a different contract, and the browser-opening path is the
    verified one. The panel names `codex login` in a terminal as the way
    through instead, so an invisible URL never leaves anyone stranded.
    """
    global _child, _busy
    providers.ensure_login_path()
    binary = providers.provider_bin("codex")
    if not binary:
        raise NoBinary("the `codex` CLI is not on this server's PATH")
    with _lock:
        if _busy:
            raise Busy(_busy)
        child = subprocess.Popen(
            [binary, "login"], env=_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _child = child
        _busy = "login"
    threading.Thread(target=_watch, args=(child,), daemon=True,
                     name="codex-login-watch").start()
    return {"started": True, "pid": child.pid, "cap_seconds": CAP_SECONDS}


def cancel():
    """SIGTERM a running login, SIGKILL after the grace period.

    Returns True if something was signalled, False if nothing was running --
    which is NOT an error: the panel's Cancel can lose a race with the flow
    completing, and reporting a failure for that would be a lie about state.

    The signal is sent OUTSIDE the lock. Holding it while waiting on a child
    would block the very reads that tell the panel what is going on.
    """
    with _lock:
        child = _child if _busy == "login" else None
    if child is None:
        return False
    try:
        child.terminate()
    except OSError:
        return False
    try:
        child.wait(timeout=KILL_GRACE)
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except OSError:
            pass
    return True


def logout():
    """Run `codex logout`, blocking. No human is in the loop.

    Raises Busy if a sign-in is in flight -- cancel that first, rather than
    letting two operations decide one credential by finish order.

    The child's output is captured and DELIBERATELY NOT RETURNED. `codex
    logout` has no reason to print a credential, but the rule that child output
    does not cross into a response is cheaper to keep than to reason about per
    verb, and the terminal is right there for anyone who needs the detail.
    """
    global _busy
    providers.ensure_login_path()
    binary = providers.provider_bin("codex")
    if not binary:
        raise NoBinary("the `codex` CLI is not on this server's PATH")
    with _lock:
        if _busy:
            raise Busy(_busy)
        _busy = "logout"
    try:
        p = subprocess.run([binary, "logout"], env=_env(), capture_output=True,
                           text=True, timeout=LOGOUT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False,
                "reason": "`codex logout` did not finish within %ss"
                          % LOGOUT_TIMEOUT}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False,
                "reason": "`codex logout` could not be run (%s)"
                          % type(exc).__name__}
    finally:
        with _lock:
            _busy = None
    if p.returncode != 0:
        return {"ok": False,
                "reason": "codex exited %s. Running `codex logout` in a "
                          "terminal will show what it said." % p.returncode}
    return {"ok": True}


def in_flight():
    """Is a `codex login` running right now?

    The panel needs this because a RELOAD loses its in-memory busy state: with
    a child running and about to change the credential, the row would otherwise
    render "Not signed in", which is the row lying about state.
    """
    with _lock:
        child, busy = _child, _busy
    return bool(busy == "login" and child is not None and child.poll() is None)


def state():
    """{"busy": None|"login"|"logout", "login_in_flight": bool}."""
    with _lock:
        busy = _busy
    return {"busy": busy, "login_in_flight": in_flight()}


def _reset_for_tests():
    """Drop any tracked child WITHOUT signalling it. Tests only."""
    global _child, _busy
    with _lock:
        _child, _busy = None, None
