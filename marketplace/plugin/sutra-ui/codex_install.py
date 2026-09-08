"""Put the `codex` CLI on this Mac, so an authenticated Codex is a usable one.

WHY THIS EXISTS
---------------
Codex needs TWO things and the panel could only supply one. `codex_login`/
`codex_auth` move the CREDENTIAL; nothing supplied the BINARY. So on a Mac with
no Codex CLI the sign-in block rendered `state: "no_binary"` with its detail
sentence and NO ACTIONS AT ALL (05-chat.js's codexAuthHtml: `actions = ""`) --
a dead end on the one screen that exists to get Codex working. Closing that gap
is this module.

It is the exact shape deepseek_install.py already proved in the field, applied
to the provider whose runtime chain is structurally identical:

    Node.js -> npm -> @openai/codex -> a runnable `codex`

MEASURED, NOT ASSUMED (2026-09-08, against the live npm registry and an
installed copy):

    @openai/codex@0.153.4  engines.node ">=16"
                           bin { codex: "bin/codex.js" }
                           dist.unpackedSize 13206 bytes
    bin/codex.js line 1    #!/usr/bin/env node        (ESM; imports node:*)
    the real CLI           an optionalDependencies platform package,
                           e.g. @openai/codex-darwin-arm64
    `file` on the result   "a /usr/bin/env node script text executable"

So the published `codex` is a NODE SHIM, not a native binary -- the same fact
bundle-runtime.sh records about the `deepseek` command. Node is therefore needed
TWICE: once to install, and again on EVERY LATER LAUNCH to run the shim. The
second half is app.py's `ensure_bundled_node_path()` call at the spawn, which is
why `codex` had to be added to that condition; without it the CLI installs
perfectly through the bundled npm and then dies at spawn with `env: node: No
such file or directory`, which reads like a broken install rather than a missing
runtime.

--prefix, NOT -g. THIS IS THE WHOLE DESIGN.
-------------------------------------------
`npm install -g` writes to whatever prefix node was configured with. On a
system node, or Homebrew on Intel, that is a root-owned directory, so the
install fails with EACCES -- and the only fixes are sudo (which a GUI app must
not ask for and cannot supply) or reconfiguring the operator's npm prefix (a
permanent, global change to their machine, made to install one CLI). Both are
worse than the problem.

There is a SECOND reason here that DeepSeek did not have. `codex` is a command
plenty of people already have on their PATH, from Homebrew's cask (a native
binary) or their own npm. A `-g` install would REPLACE whatever `codex` their
terminal resolves today. A --prefix install cannot: it goes into a directory
Sutra owns, beside settings.json, and the result is registered through
`providers.set_provider_bin` -- the settings-backed override `_bin_for()`
already consults ahead of PATH. The operator's own `codex` is never written to,
moved, or shadowed anywhere but inside Sutra.

What that buys: no sudo, no PATH edit, no shell rc file touched, nothing
outside ~/.sutra-ui, and `installed` flips on the NEXT read with no restart --
because _bin_for -> shutil.which(absolute path) resolves it immediately.

NPM EXITING 0 IS NOT A WORKING RUNTIME, AND THIS MODULE DOES NOT PRETEND IT IS
------------------------------------------------------------------------------
deepseek_install stops at "the file is there and executable". That is not
enough for a node shim: the file can be present, executable, and still die at
`env: node: No such file or directory`. Reported as a success it becomes the
readiness lie this whole package is organised against -- a row saying "Ready to
use" over a provider that cannot answer a message.

So `install()` ends by RUNNING the thing: `codex --version`, with the bundled
Node on PATH, and the provider_bins registration happens only if that
succeeded. A verification failure registers NOTHING; the row keeps saying "not
installed", which is the truth.

The same probe guards the ALREADY branch, which is the case deepseek_install
never had to think about: an EXTERNAL `codex` that resolves but cannot run.
That one is not overwritten -- it is not this module's to touch -- but it does
not get to be an answer either, so the fall-through installs a managed copy and
points Sutra at that instead. The operator's binary stays exactly where it was.

WHAT IS NOT CLAIMED
-------------------
That this works without node. It does not, and it does not pretend to: a Mac
with no npm gets a refusal that names nodejs.org and says what was searched.
Sutra does not install Node ONTO the machine -- that is a runtime the
operator's other tools share. It does ship one INSIDE Sutra.app
(bundle-runtime.sh's payload/node), which npm_path() falls back to last, so in
the packaged app NO_NPM is unreachable and a Mac with nothing installed still
gets from DMG to working Codex.

>>> DUPLICATION IS DELIBERATE <<<
`npm_path()`, `_no_npm_reason()`, `_usable()`, `_write_manifest()`, `_tail()`
and the error class are DUPLICATED from deepseek_install.py rather than
imported. Founder direction 2026-09-08: provider isolation. Importing them
would mean a change made for Codex could alter how DeepSeek installs, and the
two modules' failure text has to speak about different packages anyway. Once
BOTH are proven in the field these move to a provider_npm.py that each
imports -- the same EXTRACTION POINT note codex_auth.py carries for its four
helpers duplicated out of deepseek_auth.py.

Reads: PATH (through providers), npm's location, the codex binary's location.
Writes: ~/.sutra-ui/providers/codex/** and the `provider_bins` entry in
        ~/.sutra-ui/settings.json (via providers.set_provider_bin). Nothing
        else, anywhere. Never a credential -- this module never sees one.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import providers

#: What to install. The package name comes from providers so there is ONE
#: string for it in the tree -- the reason sentence on the provider row and the
#: thing this module fetches must never be able to disagree.
PACKAGE = providers.CODEX_CLI_PACKAGE

#: PINNED, not floating. codex_runtime.py's transport was measured against this
#: exact build and its docstrings cite it ("MEASURED against codex-cli 0.153.2
#: on 2026-09-08", "VERIFIED against codex-cli 0.153.2"), as does
#: providers._CODEX_API_KEY_RE's comment about the `codex login status` line.
#: Installing `latest` would mean shipping an adapter verified against one
#: build and pointing it at another -- the same class of guess this package
#: refuses everywhere else, and here it would silently change both the chat
#: wire format and the string the sign-in row parses. Bumping it is a
#: deliberate act that comes with re-probing those assumptions.
#:
#: Confirmed present on the registry 2026-09-08 (npm view @openai/codex
#: versions), alongside its six platform packages.
VERSION = "0.153.2"

#: The executable the package publishes -- a Node shim, see the header.
BIN_NAME = "codex"

#: The catalogue id in providers._CATALOG. Identical to BIN_NAME today, and
#: named separately because they answer different questions -- one addresses a
#: row, the other names a file -- and collapsing them is how a rename of either
#: silently reaches the other.
PROVIDER_ID = "codex"

#: npm fetching and unpacking a CLI over a home connection. Matches
#: deepseek_install's cap: this is a download, and killing it at 30s would
#: leave a half-populated node_modules and report a failure that was only
#: slowness. @openai/codex pulls a platform package holding a Rust binary, so
#: the bytes are not smaller than DeepSeek's.
INSTALL_TIMEOUT = 300

#: `codex --version` on an installed shim: node starts, resolves the platform
#: package, execs the Rust binary, prints one line. Generous against a cold
#: filesystem and a Gatekeeper first-run check, not against a human -- nothing
#: in this command waits for anybody.
VERIFY_TIMEOUT = 60

#: How much of npm's own complaint to quote back. Enough to carry an EACCES, an
#: ETARGET or an EBADENGINE line; short enough that a wall of peer-dependency
#: warnings cannot become the message. No credential passes through this
#: command -- unlike codex_auth, whose exceptions are built from fixed strings
#: for that exact reason -- so quoting npm here is safe.
_ERR_TAIL = 400


class CodexInstallError(RuntimeError):
    """A refusal with a machine-readable `code` and a sentence for the operator.

    Same shape as CodexAuthError and DeepSeekInstallError so the route can
    handle all three identically.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------- location ---

def prefix():
    """The directory the package is installed into.

    Derived from providers.SETTINGS_PATH rather than hardcoded to ~/.sutra-ui,
    so SUTRA_UI_SETTINGS moves this too. That is not only a test convenience:
    the install and the provider_bins entry that points at it are one unit, and
    a settings file redirected to a tempdir while the install went to the
    operator's real home would leave a registered path with nothing behind it.
    """
    return providers.SETTINGS_PATH.parent / "providers" / "codex"


def managed_bin():
    """The path this module would install to. Existence is NOT implied."""
    return prefix() / "node_modules" / ".bin" / BIN_NAME


def _usable(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def is_managed(bin_path):
    """Is `bin_path` the copy THIS module installed?

    The question `uninstall()` turns on, and the reason it can be safe: a
    `codex` the operator installed themselves -- Homebrew's cask, a global npm,
    a hand-built checkout -- is not this module's to delete or replace.
    """
    return bool(bin_path) and str(bin_path) == str(managed_bin())


# ------------------------------------------------------------------- npm ----

def npm_path():
    """Where npm is, or None. Never raises.

    DUPLICATED from deepseek_install.npm_path -- see the header's DUPLICATION
    note. Behaviour is deliberately identical, because the search is a property
    of the MACHINE and not of the provider.

    THE SAME SEARCH THE PROVIDER ROWS GET, and for the same reason. A GUI
    launch inherits a PATH of four system directories (providers.py's opening
    note), and npm lives in none of them -- so asking shutil.which() alone
    would report "no npm" on a machine where `npm -v` works in every terminal,
    which is the precise failure providers.ensure_login_path() was written
    about.

    THE DIRECTORY IS JOINED TO PATH, not just returned, and that matters after
    the install as much as during it: `codex` is a shim beginning
    `#!/usr/bin/env node`, so `codex --version` below -- and every later chat
    turn -- needs `node` resolvable in this process's environment. node ships
    beside npm in every layout in _KNOWN_BIN_DIRS, so making npm reachable
    makes node reachable. Appended, never prepended -- a PATH set deliberately
    for this process keeps precedence, matching ensure_login_path().
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
    # LAST, and only in the packaged app. bundle-runtime.sh vendors Node into
    # payload/node so a Mac with nothing installed can still get from DMG to a
    # working provider, and this is where it is found. Deliberately BELOW the
    # searches above: the operator's Node is the one their other tools use, so
    # nothing about a machine that has one changes.
    d = providers.ensure_bundled_node_path()
    if d:
        cand = os.path.join(d, "npm")
        if _usable(cand) or os.path.islink(cand):
            return cand
    return None


def _no_npm_reason():
    """Why the install cannot be offered, naming what was searched.

    Concrete in the style of providers._deepseek_reason, which names the PATH
    search and the harvest outcome rather than only the absence. "npm not
    found" is true and sends nobody anywhere.
    """
    return ("npm is not on this Mac, or not where Sutra can see it. The login "
            "shell's PATH, the usual install locations and Sutra's own bundled "
            "copy of Node were all searched%s. "
            "The Codex CLI is an npm package (%s), so installing it needs "
            "Node.js -- get it from nodejs.org, then try again. Sutra does not "
            "install Node onto your Mac: it is a runtime your other tools "
            "share, and putting a second copy somewhere unexpected is not a "
            "decision this app should make for you."
            % (providers._harvest_note(), PACKAGE))


# ----------------------------------------------------------------- state ----

def state():
    """What the panel needs to decide whether to offer an install.

        {"installed":   a `codex` binary resolves right now
         "bin_path":    where, or None
         "managed":     True when that binary is the one Sutra installed
         "npm":         npm's path, or None
         "can_install": an install could be attempted
         "package", "version"
         "reason":      why it cannot be, or None}

    CHEAP ENOUGH TO CALL ON A RENDER, and no cheaper. It resolves two binaries
    and may spawn the login shell ONCE per process (ensure_login_path is a
    no-op after the first call). IT RUNS NO SUBPROCESS -- deliberately, and it
    is why `verified` is NOT a field here. Proving the runtime executes costs a
    `codex --version`, and this answer rides on GET /providers/codex/auth,
    which the sign-in poll hits every 2 seconds. Verification happens at the
    one moment the answer can change: inside install(). Provider discovery
    (providers._describe) stays subprocess-free for the same reason, only more
    so -- it runs four times per load_settings().
    """
    bin_path = providers.provider_bin(PROVIDER_ID)
    npm = npm_path()
    return {
        "installed": bin_path is not None,
        "bin_path": bin_path,
        "managed": is_managed(bin_path),
        "npm": npm,
        "can_install": npm is not None,
        "package": PACKAGE,
        "version": VERSION,
        "reason": None if npm else _no_npm_reason(),
    }


# ------------------------------------------------------------ verification ---

def _verify_env():
    """The environment `codex --version` runs in.

    OPENAI_/CODEX_ ARE NOT STRIPPED, unlike codex_login._env() and
    codex_auth._env(). Those two spawn commands that DECIDE which credential
    gets stored, so the operator's click has to win over a variable in their
    shell profile. `--version` decides nothing and stores nothing; it prints a
    string. Stripping here would make the probe run in an environment no real
    turn ever sees, which is the opposite of what a verification is for.
    """
    return dict(os.environ)


def verify(bin_path):
    """Does this `codex` actually RUN? -> (ok, reason).

    THE POINT OF THIS MODULE'S EXISTENCE, AND WHY IT IS NOT deepseek_install.
    The published `codex` is a node shim (see the header), so the file being
    present and executable proves nothing: with no `node` resolvable it exits
    127 with `env: node: No such file or directory`. Registered on the strength
    of npm's exit code, that becomes a row reading "Ready to use" over a
    provider that dies on the first message.

    `--version` and not `login status`: this must answer "can the runtime
    execute", a question with nothing to do with credentials. `login status`
    reads ~/.codex, has its own 10s budget in providers.codex_auth(), and
    on a signed-out machine exits non-zero for a reason that is not a runtime
    problem at all -- so using it here would refuse a perfectly good install.

    The bundled Node is put on PATH first. No-op outside the packaged app, and
    npm_path() has usually done it already; called again because verify() is
    reachable without an install having just run.
    """
    if not _usable(bin_path):
        return False, ("there is no runnable file at %s" % bin_path)
    providers.ensure_bundled_node_path()
    try:
        p = subprocess.run([str(bin_path), "--version"],
                           capture_output=True, text=True,
                           timeout=VERIFY_TIMEOUT, env=_verify_env(),
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, ("`%s --version` did not answer within %ds"
                       % (BIN_NAME, VERIFY_TIMEOUT))
    except (OSError, subprocess.SubprocessError) as exc:
        return False, ("%s could not be run (%s)"
                       % (bin_path, type(exc).__name__))
    if p.returncode != 0:
        # THE `env: node: No such file or directory` CASE LANDS HERE, and the
        # tail is what makes it diagnosable rather than a bare exit code.
        return False, ("`%s --version` exited %s. It said: %s"
                       % (BIN_NAME, p.returncode,
                          _tail(p.stderr) or _tail(p.stdout) or "nothing."))
    return True, None


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
        "name": "sutra-provider-codex",
        "version": "0.0.0",
        "private": True,
        "description": "Sutra-managed install of the Codex CLI. "
                       "Safe to delete; Sutra will re-install on request.",
    }, indent=2) + "\n")


def _tail(text):
    blob = " ".join((text or "").split())
    return blob[-_ERR_TAIL:] if len(blob) > _ERR_TAIL else blob


def _npm_failure(spec, returncode, stderr, stdout):
    """Classify one non-zero npm exit into a (code, sentence).

    ONE ARM ABOVE THE GENERIC ONE, and it earns its place because
    @openai/codex declares `engines.node ">=16"` while the target user's Mac
    may carry whatever Node some other installer left behind years ago. npm>=7
    refuses that with EBADENGINE, and left in the generic tail it arrives as a
    wall of npm prose about a field name. "Your Node is too old" is the same
    fact in words that name the fix.

    Nothing else is guessed at. EACCES is NOT special-cased: --prefix into
    ~/.sutra-ui should never produce one, and inventing a sudo story for a
    permission error we do not expect would send people somewhere wrong.
    """
    tail = _tail(stderr) or _tail(stdout) or "nothing."
    if "EBADENGINE" in (stderr or "") + (stdout or ""):
        return "NODE_TOO_OLD", (
            "the Node.js on this Mac is too old for %s, which needs Node 16 or "
            "newer. npm refused the install rather than leaving a broken one. "
            "Updating Node from nodejs.org fixes it. It said: %s" % (spec, tail))
    return "NPM_FAILED", (
        "npm could not install %s (exit %d). It said: %s"
        % (spec, returncode, tail))


#: SINGLE-FLIGHT. npm has no opinion about two of itself unpacking into one
#: prefix at the same time, and this can be entered twice for reasons the UI
#: cannot prevent: the panel's own sign-in->install chain racing the server-side
#: kick, an operator with the panel open in two tabs, or a retry fired while a
#: slow registry was still answering. The second caller BLOCKS on this and then
#: re-enters install(), where the ALREADY branch answers it from the first
#: one's result -- so it reports the truth rather than a second download over a
#: half-written tree.
_INSTALL_LOCK = threading.Lock()


def install(force=False):
    """Fetch the CLI, prove it runs, and register it. Returns a result dict;
    raises CodexInstallError with a classified reason on failure.

        {"ok": True, "code": "INSTALLED" | "ALREADY",
         "bin_path": ..., "managed": bool, "version": ...,
         "message": one sentence, "took_ms": ...}

    ALREADY IS A SUCCESS, not a no-op to hide. Someone who installed the CLI
    themselves is done, and re-downloading over a working install to prove it
    would be slower and could only make things worse. `force` exists for a
    repair -- a registered path whose file has gone, or a managed copy that
    stopped running -- and is not what the sign-in flow uses.

    ORDER, and every step of it is load-bearing:

      1. an existing `codex` that VERIFIES  -> ALREADY, npm never runs
      2. npm resolved                       -> before anything is written, so a
                                               Mac that cannot do this at all
                                               does not get a directory made
                                               for an install that will not
                                               happen
      3. npm install --prefix <ours>
      4. the file is there and executable
      5. `codex --version` actually runs    -> npm exiting 0 is not a runtime
      6. provider_bins written LAST         -> a registered path is a claim the
                                               panel renders as "Ready to use",
                                               so nothing is registered until
                                               the claim is true
    """
    with _INSTALL_LOCK:
        return _install_locked(force)


def _install_locked(force):
    """install()'s body, entered one at a time. See _INSTALL_LOCK."""
    started = time.time()
    existing = providers.provider_bin(PROVIDER_ID)
    if existing and not force:
        ok, why = verify(existing)
        if ok:
            return {"ok": True, "code": "ALREADY", "bin_path": existing,
                    "managed": is_managed(existing), "version": None,
                    "took_ms": int((time.time() - started) * 1000),
                    "message": "the `%s` CLI is already on this Mac (%s) and "
                               "runs, so nothing was installed."
                               % (BIN_NAME, existing)}
        # IT RESOLVES AND IT CANNOT RUN. Falling through to install a managed
        # copy, and NOT touching the one that is there: a `codex` the operator
        # installed is not this module's to overwrite, delete or repair. What
        # Sutra can do is point ITSELF at a copy it owns -- set_provider_bin
        # wins over PATH inside this app and changes nothing about what the
        # operator's terminal resolves.
        #
        # Mostly unreachable in the packaged app, where ensure_bundled_node_path
        # makes any node shim run; a machine with genuinely no Node falls out
        # at the npm check below instead, with the reason that actually applies.
        pass

    # THE OVERRIDE CHECK, and it is deepseek_install's env guard applied to the
    # same hole in the same place. `_bin_for` puts SUTRA_UI_CODEX_BIN ABOVE
    # provider_bins, so with that variable set to a path that does not resolve,
    # an install would download the CLI, register it, report success -- and the
    # row would still read "not installed", because the variable keeps winning.
    # That is a readiness lie in a new place. Refuse instead, and name it.
    #
    # A variable pointing at a binary that DOES resolve and run never reaches
    # here: provider_bin() answered it and the ALREADY branch returned.
    override = os.environ.get("SUTRA_UI_%s_BIN" % PROVIDER_ID.upper())
    if override and override.strip():
        raise CodexInstallError("ENV_OVERRIDE", (
            "SUTRA_UI_%s_BIN is set in this server's environment (%s) and wins "
            "over anything installed here, so a CLI fetched now would never be "
            "used. That path does not resolve to a runnable binary -- point it "
            "at one, or unset it and restart the server, and Sutra can install "
            "the CLI itself." % (PROVIDER_ID.upper(), override.strip())))

    npm = npm_path()
    if not npm:
        raise CodexInstallError("NO_NPM", _no_npm_reason())

    root = prefix()
    try:
        _write_manifest(root)
    except OSError as exc:
        raise CodexInstallError("NO_DIRECTORY", (
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
        raise CodexInstallError("TIMEOUT", (
            "npm was still installing %s after %ds, so it was stopped. That is "
            "usually a slow or blocked connection to the npm registry. Nothing "
            "is registered; try again." % (spec, INSTALL_TIMEOUT)))
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexInstallError("NPM_FAILED", (
            "npm could not be run (%s), so %s was not installed."
            % (type(exc).__name__, spec)))

    if p.returncode != 0:
        raise CodexInstallError(*_npm_failure(spec, p.returncode,
                                              p.stderr, p.stdout))

    got = managed_bin()
    if not _usable(str(got)):
        # npm reported success and the executable is not there. Says exactly
        # that rather than blaming the network: this is the package changing
        # the name it publishes, and a wrong diagnosis would send the operator
        # to their router.
        raise CodexInstallError("NO_BINARY", (
            "npm installed %s but there is no runnable `%s` at %s afterwards. "
            "The package may have changed the command it publishes; this is a "
            "Sutra problem, not a problem with your machine."
            % (spec, BIN_NAME, got)))

    ok, why = verify(str(got))
    if not ok:
        # NOTHING IS REGISTERED. The tree is left where it is -- it is inert
        # until something points at it, and a `force` retry can repair it
        # without downloading again -- but the provider row keeps saying "not
        # installed", because that is what is true.
        raise CodexInstallError("VERIFY_FAILED", (
            "%s was installed to %s, but it does not run here: %s. Nothing has "
            "been registered, so Codex is still reported as not installed "
            "rather than as ready." % (spec, got, why)))

    try:
        registered = providers.set_provider_bin(PROVIDER_ID, str(got))
    except (ValueError, OSError) as exc:
        raise CodexInstallError("REGISTER_FAILED", (
            "%s was installed to %s and runs, but Sutra could not record where "
            "(%s), so the provider row will not see it."
            % (spec, got, type(exc).__name__)))

    return {"ok": True, "code": "INSTALLED", "bin_path": registered,
            "managed": True, "version": VERSION,
            "took_ms": int((time.time() - started) * 1000),
            "message": "the Codex CLI is installed (%s), Sutra checked that it "
                       "runs, and it is pointed at it -- no restart." % spec}


def uninstall():
    """Remove a Sutra-managed install and its registration. Idempotent.

    ONLY EVER TOUCHES OUR OWN PREFIX. A `codex` the operator installed
    themselves -- Homebrew's cask, a global npm, a hand-built checkout -- is
    not this module's to delete, so the registration is cleared and the
    directory is removed only when it is the one we made.

    That distinction matters more for Codex than it did for DeepSeek: `codex`
    is a command many people already have, and `providers.provider_bin` can
    perfectly well be resolving theirs.

    THE REGISTRATION IS CLEARED FROM THE STORED VALUE, not from what
    provider_bin() currently resolves. Those differ in exactly the case that
    needs handling: a managed install deleted by hand leaves the entry behind
    and `_bin_for` starts ignoring it (it skips a stored path that no longer
    exists), so provider_bin() would report the operator's own `codex` and a
    check against THAT would leave the dead entry in settings.json forever.
    Reading the raw entry also means an override the operator set themselves --
    pointing somewhere outside our prefix -- is left exactly alone.
    """
    root = prefix()
    had = root.is_dir()
    stored = (providers._raw_settings().get("provider_bins") or {}).get(PROVIDER_ID)
    ours = bool(stored) and (str(stored) == str(managed_bin())
                             or str(stored).startswith(str(root) + os.sep))
    if ours:
        try:
            providers.set_provider_bin(PROVIDER_ID, None)
        except (ValueError, OSError):
            pass
    if had:
        shutil.rmtree(root, ignore_errors=True)
    return {"removed": had}
