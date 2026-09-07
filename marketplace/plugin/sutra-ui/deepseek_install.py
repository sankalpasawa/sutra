"""Put the `deepseek` CLI on this Mac, so a saved key produces a usable provider.

WHY THIS EXISTS
---------------
DeepSeek needs TWO things and the panel could only supply one. `deepseek_auth`
saves a key; nothing supplied the binary. So the shipped flow was: paste a key,
watch it validate, read "saved on this Mac" -- printed directly under a row that
said "Not installed on this Mac" (founder screenshot, 2026-09-07). The operator
had done everything the screen asked and had a provider that could not answer a
message. Telling the truth about that gap was the first fix (org_api's
`_deepseek_saved_message`); closing it is this module.

WHY A THIRD MODULE
------------------
The split this package already uses. providers.py answers WHERE a thing would
come from and whether it is there; deepseek_auth.py performs the credential
ACTIONS; this performs the INSTALL action. Nothing here is called from
providers._describe() -- an npm subprocess on the render path would tax every
fs/tree and settings GET, the same reason codex_auth() and the keychain read
are kept off it.

--prefix, NOT -g. THIS IS THE WHOLE DESIGN.
-------------------------------------------
`npm install -g` writes to whatever prefix node was configured with. On a
Homebrew or system node that is a root-owned directory, so the install fails
with EACCES -- and the only fixes are sudo (which a GUI app must not ask for
and cannot supply) or reconfiguring the operator's npm prefix (a permanent,
global change to their machine, made to install one CLI). Both are worse than
the problem.

So the package goes into a directory Sutra already owns, beside settings.json,
and the resulting binary is registered through `providers.set_provider_bin` --
the settings-backed override `_bin_for()` already consults ahead of PATH. That
mechanism predates this module and had no control in front of it (05-chat.js
notes exactly that: "POST /settings/provider-bin exists as a route with no
control in front of it"). This is its first caller.

What that buys, and it is the point: no sudo, no PATH edit, no shell rc file
touched, nothing outside ~/.sutra-ui, and `installed` flips on the NEXT read
with no restart -- because _bin_for -> shutil.which(absolute path) resolves it
immediately.

WHAT IS NOT CLAIMED
-------------------
That this works without node. It does not, and it does not pretend to: a Mac
with no npm gets a refusal that names nodejs.org and says what was searched,
not a silent failure or a half-install. Sutra does not install node -- that is
a runtime the operator's other tools share, and putting a second copy of it
somewhere unexpected is not a decision this code gets to make.
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import providers

#: What to install. The package name comes from providers so there is ONE
#: string for it in the tree -- the reason sentence on the provider row and the
#: thing this module fetches must never be able to disagree.
PACKAGE = providers.DEEPSEEK_CLI_PACKAGE

#: PINNED, not floating. acp_runtime.py's transport was read out of an
#: unminified bundle of this exact version and its docstrings cite measurements
#: against it ("Probed on the wire against @sluisr/deepseek-cli@1.3.2,
#: 2026-09-07"). Installing `latest` would mean shipping an adapter verified
#: against one build and pointing it at another, which is the same class of
#: guess this package refuses everywhere else. Bumping it is a deliberate act
#: that comes with re-probing acp_runtime's assumptions.
VERSION = "1.3.2"

#: The executable the package publishes.
BIN_NAME = "deepseek"

#: The catalogue id in providers._CATALOG. Identical to BIN_NAME today, and
#: named separately because they answer different questions -- one addresses a
#: row, the other names a file -- and collapsing them is how a rename of either
#: silently reaches the other.
PROVIDER_ID = "deepseek"

#: npm fetching and unpacking a CLI over a home connection. Deliberately far
#: longer than any other subprocess here (codex's status probe is 10s): this
#: one is a download, and killing it at 30s would leave a half-populated
#: node_modules and report a failure that was only slowness.
INSTALL_TIMEOUT = 300

#: How much of npm's own complaint to quote back. Enough to carry an EACCES or
#: an ETARGET line; short enough that a wall of peer-dependency warnings cannot
#: become the message. No credential passes through this command -- unlike
#: deepseek_auth, whose exceptions are built from fixed strings for that exact
#: reason -- so quoting npm here is safe.
_ERR_TAIL = 400


class DeepSeekInstallError(RuntimeError):
    """A refusal with a machine-readable `code` and a sentence for the operator.

    Same shape as DeepSeekAuthError so the route can handle both identically.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------- location ---

def prefix():
    """The directory the package is installed into.

    Derived from providers.SETTINGS_PATH rather than hardcoded to ~/.sutra-ui,
    so SUTRA_UI_SETTINGS moves this too. That is not only a test convenience:
    the two are one unit -- the install and the provider_bins entry that points
    at it -- and a settings file redirected to a tempdir while the install went
    to the operator's real home would leave a registered path with nothing
    behind it.
    """
    return providers.SETTINGS_PATH.parent / "providers" / "deepseek"


def managed_bin():
    """The path this module would install to. Existence is NOT implied."""
    return prefix() / "node_modules" / ".bin" / BIN_NAME


def _usable(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


# ------------------------------------------------------------------- npm ----

def npm_path():
    """Where npm is, or None. Never raises.

    THE SAME SEARCH THE PROVIDER ROWS GET, and for the same reason. A GUI
    launch inherits a PATH of four system directories (providers.py's opening
    note), and npm lives in none of them -- so asking shutil.which() alone
    would report "no npm" on a machine where `npm -v` works in every terminal,
    which is the precise failure providers.ensure_login_path() was written
    about.

    THE DIRECTORY IS JOINED TO PATH, not just returned, and that matters after
    the install as much as during it: the shim npm publishes starts with
    `#!/usr/bin/env node`, so spawning `deepseek --acp` later needs `node`
    resolvable in this process's environment. node ships beside npm in every
    layout in _KNOWN_BIN_DIRS, so making npm reachable makes node reachable.
    Appended, never prepended -- a PATH set deliberately for this process keeps
    precedence, matching ensure_login_path().
    """
    providers.ensure_login_path()
    found = shutil.which("npm")
    if found:
        return found
    for d in providers._known_bin_dirs(["npm"]):
        cand = os.path.join(d, "npm")
        if _usable(cand):
            have = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
            if d not in have:
                os.environ["PATH"] = os.pathsep.join(have + [d])
            return cand
    return None


def _no_npm_reason():
    """Why the install cannot be offered, naming what was searched.

    Concrete in the style of providers._deepseek_reason, which names the PATH
    search and the harvest outcome rather than only the absence. "npm not
    found" is true and sends nobody anywhere.
    """
    return ("npm is not on this Mac, or not where Sutra can see it. The login "
            "shell's PATH and the usual install locations were both searched%s. "
            "The DeepSeek CLI is an npm package (%s), so installing it needs "
            "Node.js -- get it from nodejs.org or `brew install node`, then try "
            "again. Sutra does not install Node itself: it is a runtime your "
            "other tools share, and putting a second copy somewhere unexpected "
            "is not a decision this app should make for you."
            % (providers._harvest_note(), PACKAGE))


# ----------------------------------------------------------------- state ----

def state():
    """What the panel needs to decide whether to offer an install.

        {"installed":   a `deepseek` binary resolves right now
         "bin_path":    where, or None
         "managed":     True when that binary is the one Sutra installed
         "npm":         npm's path, or None
         "can_install": an install could be attempted
         "package", "version"
         "reason":      why it cannot be, or None}

    CHEAP ENOUGH TO CALL ON A RENDER, and no cheaper. It resolves two binaries
    and may spawn the login shell ONCE per process (ensure_login_path is a
    no-op after the first call). It runs no npm command -- `npm ls` to confirm
    the package would add a second-long subprocess to answer a question the
    binary's existence already answers.
    """
    bin_path = providers.provider_bin(PROVIDER_ID)
    npm = npm_path()
    return {
        "installed": bin_path is not None,
        "bin_path": bin_path,
        "managed": bool(bin_path) and bin_path == str(managed_bin()),
        "npm": npm,
        "can_install": npm is not None,
        "package": PACKAGE,
        "version": VERSION,
        "reason": None if npm else _no_npm_reason(),
    }


# --------------------------------------------------------------- install ----

def _write_manifest(root):
    """A minimal private package.json before npm is asked to install into here.

    Without one, npm treats the prefix as a project it has to guess at: it
    warns about missing fields, and its behaviour when it walks UP out of an
    empty directory looking for a parent project is not something to leave to
    chance -- a prefix inside a directory that happens to have a package.json
    above it could otherwise install somewhere else entirely. Declaring the
    root explicitly removes the guess.

    `private` keeps npm from ever treating this as publishable.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps({
        "name": "sutra-provider-deepseek",
        "version": "0.0.0",
        "private": True,
        "description": "Sutra-managed install of the DeepSeek CLI. "
                       "Safe to delete; Sutra will re-install on request.",
    }, indent=2) + "\n")


def _tail(text):
    blob = " ".join((text or "").split())
    return blob[-_ERR_TAIL:] if len(blob) > _ERR_TAIL else blob


def install(force=False):
    """Fetch the CLI and register it. Returns a result dict; raises
    DeepSeekInstallError with a classified reason on failure.

        {"ok": True, "code": "INSTALLED" | "ALREADY",
         "bin_path": ..., "message": one sentence, "took_ms": ...}

    ALREADY IS A SUCCESS, not a no-op to hide. Someone who installed the CLI
    themselves is done, and re-downloading over a working install to prove it
    would be slower and could only make things worse. `force` exists for a
    repair -- a registered path whose file has gone -- and is not what the
    save flow uses.

    ORDER. npm is resolved before anything is written, so a Mac that cannot do
    this at all does not get a directory created for an install that will not
    happen. The provider_bins entry is written LAST, after the binary has been
    confirmed executable on disk -- a registered path is a claim the panel
    renders, and set_provider_bin refuses a path that is not executable
    anyway, so this cannot leave a row pointing at nothing.
    """
    started = time.time()
    existing = providers.provider_bin(PROVIDER_ID)
    if existing and not force:
        return {"ok": True, "code": "ALREADY", "bin_path": existing,
                "took_ms": 0,
                "message": "the `%s` CLI is already on this Mac (%s), so "
                           "nothing was installed." % (BIN_NAME, existing)}

    # THE OVERRIDE CHECK, and it is deepseek_auth.save()'s env
    # guard applied to the other half of the provider. `_bin_for` puts
    # SUTRA_UI_DEEPSEEK_BIN ABOVE provider_bins, so with that variable set to a
    # path that does not resolve, an install would download the CLI, register
    # it, report "Sutra is pointed at it" -- and the row would still read "not
    # installed", because the variable keeps winning. That is the same
    # readiness lie in a new place: a success message over a machine the
    # operator cannot use. Refuse instead, and name the variable.
    #
    # A variable pointing at a binary that DOES resolve never reaches here:
    # provider_bin() answered it and the ALREADY branch above returned. That
    # ordering is not cosmetic -- the first draft checked the variable first
    # and refused a perfectly good override, which its own test caught.
    override = os.environ.get("SUTRA_UI_%s_BIN" % PROVIDER_ID.upper())
    if override and override.strip():
        raise DeepSeekInstallError("ENV_OVERRIDE", (
            "SUTRA_UI_%s_BIN is set in this server's environment (%s) and wins "
            "over anything installed here, so a CLI fetched now would never be "
            "used. That path does not resolve to a runnable binary -- point it "
            "at one, or unset it and restart the server, and Sutra can install "
            "the CLI itself." % (PROVIDER_ID.upper(), override.strip())))

    npm = npm_path()
    if not npm:
        raise DeepSeekInstallError("NO_NPM", _no_npm_reason())

    root = prefix()
    try:
        _write_manifest(root)
    except OSError as exc:
        raise DeepSeekInstallError("NO_DIRECTORY", (
            "could not prepare %s for the install (%s). Nothing was changed."
            % (root, type(exc).__name__)))

    spec = "%s@%s" % (PACKAGE, VERSION)
    try:
        p = subprocess.run(
            [npm, "install", spec, "--prefix", str(root),
             # No audit report, no funding banner, no lockfile chatter: none of
             # it can be acted on from here, and all of it would land in the
             # error tail and crowd out the line that matters.
             "--no-audit", "--no-fund", "--loglevel=error"],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
            # stdin closed. npm does not prompt for this command, and a build
            # that decides to would otherwise hang here for the full 300s with
            # a spinner on screen and no way for anyone to answer it.
            stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise DeepSeekInstallError("TIMEOUT", (
            "npm was still installing %s after %ds, so it was stopped. That is "
            "usually a slow or blocked connection to the npm registry. Nothing "
            "is registered; try again." % (spec, INSTALL_TIMEOUT)))
    except (OSError, subprocess.SubprocessError) as exc:
        raise DeepSeekInstallError("NPM_FAILED", (
            "npm could not be run (%s), so %s was not installed."
            % (type(exc).__name__, spec)))

    if p.returncode != 0:
        raise DeepSeekInstallError("NPM_FAILED", (
            "npm could not install %s (exit %d). It said: %s"
            % (spec, p.returncode,
               _tail(p.stderr) or _tail(p.stdout) or "nothing.")))

    got = managed_bin()
    if not _usable(str(got)):
        # npm reported success and the executable is not there. Says exactly
        # that rather than blaming the network: this is the package changing
        # the name it publishes, and a wrong diagnosis would send the operator
        # to their router.
        raise DeepSeekInstallError("NO_BINARY", (
            "npm installed %s but there is no runnable `%s` at %s afterwards. "
            "The package may have changed the command it publishes; this is a "
            "Sutra problem, not a problem with your machine." % (spec, BIN_NAME, got)))

    try:
        registered = providers.set_provider_bin(PROVIDER_ID, str(got))
    except (ValueError, OSError) as exc:
        raise DeepSeekInstallError("REGISTER_FAILED", (
            "%s was installed to %s, but Sutra could not record where (%s), so "
            "the provider row will not see it." % (spec, got, type(exc).__name__)))

    return {"ok": True, "code": "INSTALLED", "bin_path": registered,
            "took_ms": int((time.time() - started) * 1000),
            "message": "the DeepSeek CLI is installed (%s) and Sutra is pointed "
                       "at it -- no restart." % spec}


def uninstall():
    """Remove a Sutra-managed install and its registration. Idempotent.

    ONLY EVER TOUCHES OUR OWN PREFIX. A `deepseek` the operator installed
    themselves -- Homebrew, a global npm, a hand-built checkout -- is not this
    module's to delete, so the registration is cleared and the directory is
    removed only when it is the one we made.
    """
    root = prefix()
    had = root.is_dir()
    if providers.provider_bin(PROVIDER_ID) == str(managed_bin()) or had:
        try:
            providers.set_provider_bin(PROVIDER_ID, None)
        except (ValueError, OSError):
            pass
    if had:
        shutil.rmtree(root, ignore_errors=True)
    return {"removed": had}
