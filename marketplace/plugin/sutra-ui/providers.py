"""providers.py -- which AI CLIs are ACTUALLY usable on this machine.

The panel was hardcoded to `claude`. Making it "multi-provider" by listing
three names in a dropdown would be worse than hardcoding: it would offer the
operator two choices that cannot run, and only reveal that after they pick
one. So availability is decided by two INDEPENDENT observations, both made
fresh on every call:

  installed   = shutil.which(<bin>) is not None      -- can we exec it?
  configured  = <config dir> is a directory          -- has it ever been set up?

  adapter     = <id> in ADAPTERS                     -- can WE drive it?

TWO PROVIDERS OVERRIDE `configured`, because for them the directory is not
evidence of anything: codex reads ~/.codex/auth.json (existence only) and
deepseek asks whether an API key resolves. Both directories exist after the CLI
has run once, whether or not anyone ever signed in, so treating them as setup
claimed the provider was ready on a machine that had never authenticated.

Neither is inferred from the others. A provider is `runnable` only when ALL
THREE hold, and `reason` states exactly which one failed, naming the path or
the missing capability, so the UI never says "unavailable" without saying why.

The third signal exists because the first two are properties of the MACHINE and
the third is a property of THIS CODEBASE. Installing the codex CLI makes codex
installed+configured within seconds, but the panel still cannot drive it: the
chat channel speaks Claude's `-p --output-format stream-json` protocol and
app.py refuses any other provider outright. Without `adapter`, installing a CLI
silently promoted it to selectable and the failure only surfaced after the
operator picked it and sent a message. That is precisely the "offer a choice
that cannot run" failure this module was written to prevent.

When an adapter is added, add its id to ADAPTERS -- that is the only change
required here.

SETTINGS live here too (rather than in org_api) because three callers need
the same file and the same validation: the settings endpoints, the provider
selector, and app.py's ws_chat. One reader, one writer, one set of defaults.

Reads: PATH, and the config dirs (existence only -- never their contents).
Writes: exactly one file, ~/.sutra-ui/settings.json, via save_settings().
        Never anything under SUTRA_NATIVE_HOME.
"""
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# ------------------------------------------------------------ login PATH ---
# A .app launched from Finder/Dock inherits launchd's PATH -- typically
# /usr/bin:/bin:/usr/sbin:/sbin -- NOT the PATH from the operator's shell rc.
# Every user-installed CLI lives outside that set: Homebrew puts `claude` in
# /opt/homebrew/bin, npm -g in ~/.npm-global/bin, and so on. The result was a
# desktop app reporting "binary 'claude' not on PATH (config found at ~/.claude)"
# on a machine where `claude` runs fine in any terminal -- chat dead, with the
# reason pointing at the wrong thing. This is a property of GUI LAUNCH, not of
# the machine, so it is repaired here rather than documented as a limitation.
_LOGIN_PATH_DONE = False
#: Why the login-shell harvest did not help, when it did not. "Both were
#: searched" told the operator nothing actionable: a harvest that TIMED OUT and
#: a harvest that ran fine but found nothing are different problems with
#: different fixes, and the panel could not tell them apart.
_HARVEST_NOTE = ""


def _harvest_note():
    return (" (%s)" % _HARVEST_NOTE) if _HARVEST_NOTE else ""


def _shell_path_once(sh, interactive):
    """One shell invocation's $PATH, or None. Never raises."""
    # `command -p echo` sidesteps an rc-defined echo alias mangling the output.
    global _HARVEST_NOTE
    args = [sh, "-l", "-i", "-c"] if interactive else [sh, "-l", "-c"]
    try:
        # 8s was too tight and failed SILENTLY. A first GUI launch pays for the
        # whole rc chain -- nvm, conda, oh-my-zsh plugins -- and a shell that
        # takes nine seconds is slow, not broken. Timing out there produced
        # "binary not on PATH" on a machine where the binary was on PATH.
        out = subprocess.run(args + ['command -p echo "$PATH"'],
                             capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        _HARVEST_NOTE = ("your login shell took over 25s to start, so its PATH "
                         "could not be read")
        return None
    except (OSError, subprocess.SubprocessError):
        _HARVEST_NOTE = "your login shell could not be run"
        return None
    lines = [l.strip() for l in (out.stdout or "").splitlines() if l.strip()]
    if not lines:
        return None
    # An rc file that prints a banner puts junk on earlier lines; PATH is the last
    # thing echoed. Require it to actually look like a PATH before trusting it.
    cand = lines[-1]
    if os.pathsep in cand and cand.startswith("/"):
        return cand
    # The shell ran but the last line was not a PATH -- an rc file printing
    # after the echo. Recorded rather than silently discarded, because the fix
    # (quieten the rc file) is nothing like the fix for a timeout.
    _HARVEST_NOTE = ("your shell startup printed output that hid its PATH")
    return None


def _login_shell_path():
    """The PATH the operator's own shell produces, or None.

    Asking the shell beats hardcoding directories: it picks up nvm, asdf, pyenv
    and hand-edited rc files, none of which are guessable.

    INTERACTIVE FIRST, and that is the whole point of this function.
    `zsh -l -c` is a LOGIN, NON-INTERACTIVE shell, and zsh reads ~/.zshrc only
    for INTERACTIVE ones -- it reads .zshenv/.zprofile/.zlogin otherwise. So a
    login-only harvest cannot see a PATH exported from .zshrc, which is where
    nvm, npm-global and Claude Code's own native installer put it. Field
    report: `claude` undetected on other people's Macs while working in every
    terminal on those same Macs. Reproduced with a HOME whose .zshrc adds the
    directory holding the binary -- `-l -c` misses it, `-l -i -c` finds it.

    (This machine did not show it: Homebrew writes its shellenv to .zprofile,
    which a login shell DOES read. The bug is invisible exactly where the
    binary happens to be installed by Homebrew.)

    Both are run and UNIONED rather than one being trusted: an interactive
    shell can be the odd one out too -- an rc file guarded on `[[ -o interactive ]]`
    that `return`s early, or a prompt framework that rewrites PATH. Taking both
    costs one extra process on a GUI launch and cannot lose a directory either
    one found.
    """
    sh = os.environ.get("SHELL") or "/bin/zsh"
    if not os.path.isfile(sh):
        sh = "/bin/zsh" if os.path.isfile("/bin/zsh") else "/bin/sh"

    merged, seen = [], set()
    for interactive in (True, False):
        got = _shell_path_once(sh, interactive)
        if not got:
            continue
        for entry in got.split(os.pathsep):
            if entry and entry not in seen:
                seen.add(entry)
                merged.append(entry)
    return os.pathsep.join(merged) if merged else None


# Where the CLIs actually install themselves, for the case where no shell can be
# asked at all: a login shell that hangs, an rc chain that exports PATH only
# under a condition we do not meet, fish/nushell whose syntax the POSIX probe
# above cannot drive, or a GUI-only account. Probed directly, never guessed at:
# a directory only joins PATH if it EXISTS and actually holds the binary.
#
# These are locations the vendors document, not a wishlist:
#   ~/.local/bin        Claude Code native installer
#   ~/.claude/local     Claude Code legacy local installer
#   /opt/homebrew/bin   Homebrew (Apple Silicon), /usr/local/bin (Intel + npm -g)
#   ~/.npm-global/bin   the documented npm prefix workaround
#   ~/.bun/bin ~/.volta/bin ~/.deno/bin   alternative runtimes people install with
#   ~/.nvm/versions/node/*/bin            nvm, whose init lives in .zshrc
_KNOWN_BIN_DIRS = (
    "~/.local/bin",
    "~/.claude/local",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "~/.npm-global/bin",
    "~/.yarn/bin",
    "~/.bun/bin",
    "~/.volta/bin",
    "~/.deno/bin",
    # Version-manager SHIM dirs. These were the gap that made the probe fail on
    # machines where the binary was installed perfectly normally: a shim dir is
    # exactly where a tool lands when the operator manages runtimes, and it is
    # never on a GUI launch's PATH. ~/Library/pnpm exists on the maintainer's
    # own machine and was not covered.
    "~/Library/pnpm",
    "~/.local/share/mise/shims",
    "~/.asdf/shims",
    "~/.nodenv/shims",
    "~/.n/bin",
    "~/.fnm/aliases/default/bin",
)


def _known_bin_dirs(binaries):
    """Existing directories from the list above that actually contain one of
    `binaries`. Returns [] when none do -- this must never widen PATH on a hunch."""
    found = []
    cands = [os.path.expanduser(d) for d in _KNOWN_BIN_DIRS]
    # nvm keeps one bin dir per installed node version; the active one is chosen
    # by .zshrc, so when that was missed every version is a candidate.
    nvm = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm):
        try:
            cands += [os.path.join(nvm, v, "bin") for v in sorted(os.listdir(nvm))]
        except OSError:
            pass
    for d in cands:
        if d in found or not os.path.isdir(d):
            continue
        for b in binaries:
            p = os.path.join(d, b)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                found.append(d)
                break
    return found


#: Where bundle-runtime.sh puts the vendored Node, relative to the payload root.
#: One string, because deepseek_install's npm search and the spawn PATH both
#: need it and a second copy is a second thing to keep in step.
BUNDLED_NODE_SUBDIR = os.path.join("node", "bin")
_BUNDLED_NODE_DONE = False


def bundled_node_bin_dir():
    """`payload/node/bin` inside a packaged Sutra.app, or None. Never raises.

    None IS THE NORMAL ANSWER outside the DMG. A checkout, a dev server and the
    test suite all have no payload, and every caller has to work the same way
    there as it did before Node was bundled -- so this returns None rather than
    guessing, and the callers fall back to the machine's own Node.

    Resolved from sys.executable FIRST. In the packaged app the interpreter is
    `payload/python/bin/python3`, which fixes the payload root exactly; __file__
    is the fallback because this module lives at `payload/plugin/sutra-ui/`,
    which is the same root two levels further down. Checking both means a build
    that rearranges one of the two does not silently lose Node.
    """
    roots = []
    try:
        exe = Path(sys.executable).resolve()
        if len(exe.parents) >= 3:
            roots.append(exe.parents[2])         # payload/python/bin/python3
    except Exception:                            # noqa: BLE001
        pass
    try:
        here = Path(__file__).resolve()
        if len(here.parents) >= 3:
            roots.append(here.parents[2])        # payload/plugin/sutra-ui/x.py
    except Exception:                            # noqa: BLE001
        pass
    for root in roots:
        d = root / BUNDLED_NODE_SUBDIR
        try:
            if (d / "node").is_file() and os.access(str(d / "node"), os.X_OK):
                return str(d)
        except OSError:
            continue
    return None


def ensure_bundled_node_path():
    """Put the bundled `node` on this process's PATH, once. Returns the dir or None.

    WHY THIS IS NOT ONLY deepseek_install's problem. npm_path() already appends
    whatever directory it found npm in, which is enough DURING an install. But
    the `deepseek` command npm publishes is a shim beginning
    `#!/usr/bin/env node`, so Node has to resolve on EVERY LATER LAUNCH too --
    and on those launches nothing installs anything, so npm_path() is never
    called and the PATH it would have fixed is never fixed. On a Mac with no
    Node of its own that is a CLI that installed perfectly and then dies at
    spawn with `env: node: No such file or directory`, which reads like a broken
    install rather than a missing runtime.

    APPENDED, never prepended, matching ensure_login_path(): a machine with its
    own Node keeps using it, and the bundled copy is the last resort it was
    bundled to be.
    """
    global _BUNDLED_NODE_DONE
    d = bundled_node_bin_dir()
    if not d:
        return None
    if not _BUNDLED_NODE_DONE:
        have = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        if d not in have:
            os.environ["PATH"] = os.pathsep.join(have + [d])
        _BUNDLED_NODE_DONE = True
    return d


def ensure_login_path():
    """Merge the login shell's PATH into this process, once, only if needed.

    A NO-OP when a catalogued binary already resolves: the CLI and dev-server
    launches inherit a correct PATH, and spawning a login shell every start would
    add latency and execute the operator's rc files for nothing. Only a GUI launch
    needs this.

    APPENDS rather than replaces, so a PATH deliberately set for this process still
    takes precedence over whatever the rc files say.

    Returns True only when it actually changed PATH.
    """
    global _LOGIN_PATH_DONE
    if _LOGIN_PATH_DONE:
        return False
    _LOGIN_PATH_DONE = True

    if any(shutil.which(spec["bin"]) for spec in _CATALOG):
        return False                     # PATH already resolves something; leave it

    have = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    added = []

    extra = _login_shell_path()
    if extra:
        added += [p for p in extra.split(os.pathsep) if p and p not in have]

    # Last resort, and only if the shell harvest did not already produce a PATH
    # that resolves a binary. Directly probing the documented install locations
    # is what makes this work for someone whose shell we could not ask at all.
    if not any(shutil.which(spec["bin"], path=os.pathsep.join(have + added))
               for spec in _CATALOG):
        binaries = [_bin_for(s["id"], s["bin"]) for s in _CATALOG]
        added += [d for d in _known_bin_dirs(binaries)
                  if d not in have and d not in added]

    if not added:
        return False
    os.environ["PATH"] = os.pathsep.join(have + added)
    return True

# ------------------------------------------------------------- settings ----
# Outside SUTRA_NATIVE_HOME by design -- panel preferences are not governance
# state. SUTRA_UI_SETTINGS exists so tests can point at a tempdir instead of
# the operator's real file.
SETTINGS_PATH = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_SETTINGS", "~/.sutra-ui/settings.json")))

# The permission modes the `claude` CLI's --permission-mode accepts that make
# sense for a panel-driven session.
#   plan               read/plan only; every edit needs an explicit approval.
#   acceptEdits        AUTO-APPROVES file writes/edits by the spawned agent.
#                      It will create, modify and delete files under `workdir`
#                      with no per-edit prompt. Opt in deliberately.
#   bypassPermissions  approves everything, including shell commands. Widest.
# All six the CLI accepts, verified against `claude --help` on the installed
# binary rather than assumed:
#   choices: "acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"
# The panel knew three, so `auto`, `manual` and `dontAsk` were unreachable from
# the UI even though the CLI has always taken them.
#
# manual / auto / dontAsk describe how APPROVALS are handled, and the approval
# round-trip needs a persistent stream-json session the panel does not have yet
# -- so they are selectable and honest about what they do, not silently broken:
# without that channel `manual` behaves as the CLI's own default handling.
PERMISSION_MODES = ("plan", "acceptEdits", "bypassPermissions",
                    "auto", "manual", "dontAsk")

# WHAT A MACHINE THAT HAS NEVER CHOSEN GETS. Founder direction 2026-09-18:
# Setup -> Access and permissions defaults to Full access, not Read only.
# This is the value the settings screen shows selected on a fresh install and
# the value a session spawns under when settings.json carries no mode.
#
# AND IT RUNS, rather than being stored and then clamped away. The unsafe-mode
# gate below is an OPT-OUT since the same direction (CLAMP_MODES_ENV): a
# default that the screen shows as selected while sessions actually start as
# `plan` is the Read only the founder asked to be rid of, only harder to see.
# An operator who wants the old posture sets SUTRA_UI_SAFE_PERM_MODES=1 and
# gets the consent gate back exactly as it was.
DEFAULT_PERMISSION_MODE = "bypassPermissions"

# THE SAFE FLOOR, AND DELIBERATELY NOT THE DEFAULT ABOVE. Everything that
# NARROWS a mode lands here: the unsafe-mode clamp, the Shadow autonomy
# ceiling (app.py _autonomy_ceiling), and an unparseable stored value. These
# were one constant until the default was widened -- at which point "clamp
# down to the default" would have clamped full access down to full access,
# i.e. every one of those guards would have become a no-op in a single line.
# `plan` is the floor of PERMISSION_MODES, so landing here can never widen.
PERMISSION_MODE_FLOOR = "plan"

# WHAT SEPARATES A CHOICE FROM AN INHERITANCE, and the reason a machine
# onboarded before 2026-09-18 does not stay on Read only forever.
#
# Widening DEFAULT_PERMISSION_MODE only changes what an ABSENT key resolves to.
# Every machine already onboarded HAS the key -- written as `plan` by the old
# default, not picked off the screen -- so on those machines the founder
# direction landed on nothing: the app still opens on Read only, which is the
# state this key exists to end.
#
# So save_settings stamps this whenever a mode is chosen EXPLICITLY, and
# load_settings treats a stored floor mode WITHOUT the stamp as "never chose"
# and resolves it to the default. Consequences, stated rather than discovered:
#
#   * an operator who deliberately picked Read only before the stamp existed
#     gets Full access once. Re-picking Read only stamps it and it sticks.
#   * it can only ever move the FLOOR mode. A stored `acceptEdits`, `dontAsk`
#     or anything else is untouched, stamped or not.
#   * it is a RESOLUTION rule, not a rewrite: nothing is written to
#     settings.json on read, so reverting this line reverts the behaviour with
#     no migrated file left behind.
#
# AND THE STAMP ITSELF NEEDS A CLAIMANT (2026-09-19, founder: "always Full
# access -- I shouldn't have to select it"). Until today save_settings stamped
# whenever a mode was NAMED, on the theory that naming one is choosing one. It
# is not: an echo of the value already on the screen names one too, and a write
# of exactly that shape pinned this key beside `plan` on the owner's own machine
# at 10:58:53 with no caller identifiable from any log or transcript. So the
# caller must now CLAIM the pick -- `save_settings(chosen=...)`, which the HTTP
# route defaults to False and the two controls a human clicks send as True. An
# unclaimed write still stores the mode; it just cannot pin Read only past a
# restart, which is what the founder asked to stop happening.
ACCESS_CHOSEN_KEY = "permission_mode_chosen"

DEFAULT_WORKDIR = "~/sutra-ui-workspace"

# Modes that let the spawned agent act without asking. The panel's settings
# endpoint is unauthenticated by construction (it is a localhost control
# plane), so anything that can reach the port could otherwise raise the
# ceiling to "auto-approve shell commands" and the operator would only learn
# about it from a status frame.
#
# That reasoning is why the list exists and is still why `warn` is set on the
# access row these map to. It is NO LONGER why they are gated, because since
# 2026-09-18 `bypassPermissions` is the shipped default and gating the door
# into a room with no walls protects nothing -- see unsafe_modes_allowed. The
# list is now consumed by: the `warn`/`requires_unlock` flags the screen draws,
# and the CLAMP_MODES_ENV opt-out for operators who want the old gate back.
UNSAFE_PERMISSION_MODES = ("acceptEdits", "bypassPermissions")
UNSAFE_MODES_ENV = "SUTRA_UI_ALLOW_UNSAFE_PERM_MODES"


UNSAFE_ACK_KEY = "unsafe_modes_acknowledged"

# THE OPT-OUT THAT REPLACED THE OPT-IN (founder direction 2026-09-18). Set to
# 1 to restore the pre-2026-09-18 posture in full: the write-capable modes are
# clamped to PERMISSION_MODE_FLOOR until the operator acknowledges them, by
# env var or by clicking through the UI confirmation. That is the kiosk / demo
# / shared-machine posture, and the exact analogue of SUTRA_UI_READ_ONLY for
# the editor. Nothing about the gate's machinery was deleted -- only which way
# it points when nobody has said anything.
CLAMP_MODES_ENV = "SUTRA_UI_SAFE_PERM_MODES"


def unsafe_modes_allowed(settings=None):
    """True when the write-capable modes may actually run. Default: True.

    WHY THIS INVERTED, and why it is not the loosening it looks like.

    The gate was written to answer ONE threat: UNATTENDED ENABLEMENT over the
    unauthenticated local socket -- something that can reach the port raising
    the ceiling to "auto-approve shell commands" without the operator ever
    agreeing. That was a real boundary while DEFAULT_PERMISSION_MODE was
    `plan`, because the only way to reach a write-capable mode was to ASK for
    one, and asking is what the gate intercepted.

    The moment the shipped default became `bypassPermissions` itself
    (2026-09-18, founder direction) the boundary stopped holding, for a reason
    that has nothing to do with how badly anyone wants the feature: a local
    process that can write settings.json to widen the mode can instead DELETE
    settings.json and inherit full access from the default on the next read.
    The gate guards one door in a wall that no longer has any others. What it
    still reliably produced was a settings screen that said Full access while
    sessions ran Read only -- a control the product shows and does not honour,
    which is the same failure the UI acknowledgement path was added to fix.

    So the gate is now an OPT-OUT (CLAMP_MODES_ENV), not an opt-in. When it is
    engaged, BOTH original ways in still work unchanged -- the env var for
    headless/CI, and the recorded acknowledgement that api_settings_post will
    only write when the caller sends the confirmation phrase.

    WHAT STILL NARROWS, and is untouched by this:

      * PERMISSION_MODE_FLOOR -- every narrowing path still lands on `plan`.
      * the Shadow autonomy ceiling (app.py _autonomy_ceiling) -- a worker the
        founder's autonomy level says MAY NOT WRITE is still capped at `plan`,
        via worker_may_write(), which never consulted this gate.
      * the origin guard on the unauthenticated port (app.py), which is what
        actually answers the cross-origin browser threat.
    """
    if os.environ.get(CLAMP_MODES_ENV, "") == "1":
        if os.environ.get(UNSAFE_MODES_ENV, "") == "1":
            return True
        s = settings if settings is not None else _raw_settings()
        return bool(s.get(UNSAFE_ACK_KEY))
    return True


# The editor is the FIRST filesystem write path in this app. Everything else reads:
# the registry API is read-only by test, the git surface read-only by allow-list. A
# panel that can overwrite the operator's source files is a different risk class, so
# it is gated exactly the way unsafe permission modes are -- OUT OF BAND, set when
# starting the server, because this endpoint is unauthenticated by construction (a
# localhost control plane) and anything able to reach the port could otherwise
# rewrite files. Reading is NOT gated: it exposes nothing the chat agent, whose cwd
# is the same directory, cannot already read.
EDIT_ENV = "SUTRA_UI_ALLOW_EDIT"          # accepted for back-compat; now a no-op
READ_ONLY_ENV = "SUTRA_UI_READ_ONLY"


def editing_allowed():
    """Editing is ON by default (founder ruling 2026-08-25): a human editing
    their own workdir through their own app is normal-software behavior. The
    old SUTRA_UI_ALLOW_EDIT opt-in inverted to a SUTRA_UI_READ_ONLY opt-out
    (kiosk/demo posture). THREAT MODEL, declared per dual consult: the origin
    guard in app.py protects the unauthenticated loopback port against
    cross-origin BROWSER requests only; local processes are outside the model
    (they hold the user's file permissions already — with the TCC caveat that
    the app's grants may exceed another process's). Boot-token hardening is
    the named follow-up."""
    return os.environ.get(READ_ONLY_ENV, "") != "1"


def effective_permission_mode(mode):
    """Clamp a stored/env mode down to PERMISSION_MODE_FLOOR (`plan`) unless
    unsafe modes are enabled.

    NOTE the floor is NOT DEFAULT_PERMISSION_MODE, which since 2026-09-18 is
    itself an unsafe mode (`bypassPermissions`). Clamping to the default would
    clamp full access to full access.

    Gating only the WRITE path (save_settings) is not enough: a settings.json
    left behind by an older build, edited by hand, or written by another local
    process would still reach the subprocess spawn. Callers must pass the mode
    through here at the point of USE, not trust what was persisted.
    """
    if mode in UNSAFE_PERMISSION_MODES and not unsafe_modes_allowed():
        return PERMISSION_MODE_FLOOR
    return mode if mode in PERMISSION_MODES else PERMISSION_MODE_FLOOR


def workdir_allowed(path):
    """True if `path` is inside a directory the panel may use as an agent cwd.

    The workdir becomes the spawned agent's cwd, so an arbitrary path turns the
    chat endpoint into a read oracle over anywhere on disk. Confine it to $HOME
    (or an explicit operator-set root) unless unsafe modes are enabled.
    """
    root = os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_UI_WORKDIR_ROOT", "~")))
    target = os.path.realpath(os.path.expanduser(path))
    return target == root or target.startswith(root + os.sep)

# Models offerable for a session. An ALLOW-LIST, not free text: the value is passed
# straight to the CLI's model flag, where an unknown string fails several seconds
# later as a dead socket -- or worse, does not fail at all and something else
# answers (see _DEEPSEEK_MODELS). `""` means "let the CLI use its own default",
# which is the shipped behaviour and stays the default for every provider.
#
# Claude's are ALIASES on purpose. Pinned ids go stale the moment a new snapshot
# ships, and a panel that offers a retired id is offering something that cannot run
# -- the same failure providers.py exists to prevent. The CLI resolves an alias to
# whatever it currently points at. DeepSeek's fork takes concrete ids and has no
# alias layer, so its entries are pinned and that difference is per-provider too.
#
# PER PROVIDER, declared on the catalog row (see _CATALOG below), not switched
# on by id at the point of use. The panel offered Claude's four aliases on a
# DeepSeek session because there was ONE list and it was Claude's; the fix is
# not a branch in the picker, it is that each provider carries its own.
_CLAUDE_MODELS = (
    {"id": "",       "name": "CLI default",  "note": "whatever `claude` is configured to use"},
    # `fable` is the alias `claude --model` accepts (resolves to claude-fable-5 on CLI 2.1.247;
    # the dated claude-fable-5-1 id needs 2.1.251+). Owner, 2026-09-14: "why i cant see fable".
    {"id": "fable",  "name": "Fable",        "note": "newest and most capable, highest cost"},
    {"id": "opus",   "name": "Opus",         "note": "most capable, slowest, highest cost"},
    {"id": "sonnet", "name": "Sonnet",       "note": "balanced default for most work"},
    {"id": "haiku",  "name": "Haiku",        "note": "fastest and cheapest, least capable"},
)

# ------------------------------------------------------- model catalogue ----
# THE SECOND, RICHER VIEW OF THE SAME THING, and it is ADDITIVE ON PURPOSE.
#
# `_CLAUDE_MODELS` above is what `models_for()` returns and therefore what
# `models_by_provider` ships. It does not change: the SEO Writer and every
# client built before this catalogue existed read that list, and a rename or a
# reorder there is a break for all of them.
#
# What the new screens need on top is four things the flat list cannot carry:
#   - a MAIN/MORE split, so the picker shows five rows and hides the pinned
#     historical ids behind "More models"
#   - the EFFORT values each model accepts, so the effort control is per model
#     instead of a guess
#   - a FAST flag, so only a provider that has a service-tier switch renders one
#   - what `""` RESOLVES TO, so "CLI default" can say what it means
#
# so `model_catalog_for()` publishes those beside the flat list rather than
# instead of it.
#
# EVERY ID HERE IS VERIFIED AGAINST THE REAL CLI, not assumed. Probe, which
# spends no model turn because the run dies on the missing prompt AFTER the
# model name has already been resolved:
#
#     printf '' | claude --model <id> -p --output-format text
#       known id    -> "Error: Input must be provided ... when using --print"
#       unknown id  -> '"<id>" isn't described by this version's model catalog'
#
# Run over every id below on 2026-09-14 against Claude Code 2.1.270 (the build
# actually on this Mac; the shared spec was written against 2.1.247). All
# ACCEPTED: best, opus, sonnet, haiku, fable, claude-opus-5, claude-opus-4-8,
# claude-opus-4-7, claude-opus-4-6, claude-sonnet-5, claude-sonnet-4-6,
# opus[1m], sonnet[1m]. A control id, totally-bogus-model, was refused, which is
# what makes the probe evidence rather than a no-op.
#
# `best` RATHER THAN A DATED FABLE ID. `best` is the alias that resolves to the
# newest model the account can run (Fable 5.1 as measured for the spec on
# 2.1.247, where the dated `claude-fable-5-1` was still REFUSED and needed
# 2.1.251+). On this Mac's 2.1.270 the dated id is now accepted too -- but an
# alias cannot go stale the way a pinned snapshot id does, and the catalogue
# has to keep working on the older CLI as well, so `best` is what is offered.

#: The `--effort` values the CLI accepts, taken from its own rejection rather
#: than from documentation. Measured 2026-09-14 on 2.1.270:
#:
#:     claude --effort bogus -p
#:       -> "Warning: Unknown --effort value 'bogus' ... Valid values: low,
#:          medium, high, xhigh, max."
#:
#: The same five are accepted on every model, so this is one tuple rather than a
#: per-model set (Codex's genuinely differ per model and are discovered; see
#: codex_efforts_for). `ultracode` is also silently accepted by this build but is
#: NOT in the CLI's own list of valid values, so it is not offered.
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")

#: WHERE A MODEL'S DEFAULT EFFORT LIVES (founder 2026-09-22: "xhigh should be
#: drawn by the selection of the model ... in dispatch"): the `effort` field on
#: that model's `catalog` entry in the plugin's dispatch routing policy. The Mac
#: app bundles the whole plugin tree, so this file ships with it. The dispatch
#: resolver never reads that field; work units still take effort from the ladder.
ROUTING_POLICY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "os", "routing-policy.json")

#: Last resort only: the model box is blank ("Account default", so the model is
#: unknown), the id names no catalog family, or the policy cannot be read.
DEFAULT_EFFORT = "xhigh"

#: Picker id -> the policy's catalog model, by family word, so a pinned snapshot
#: (claude-opus-4-8) or a `[1m]` spelling takes its family's effort.
_EFFORT_FAMILY = (("best", "claude-fable-5"), ("fable", "claude-fable-5"),
                  ("opus", "claude-opus-5"), ("sonnet", "claude-sonnet-5"),
                  ("haiku", "claude-haiku-4-5"))


def _policy_efforts(path=None):
    """{catalog model id: effort} from the routing policy; {} if unreadable."""
    try:
        with open(path or ROUTING_POLICY_PATH) as f:
            catalog = json.load(f).get("catalog") or []
    except (OSError, ValueError, AttributeError):
        return {}
    return {e.get("model"): e.get("effort") for e in catalog
            if isinstance(e, dict) and e.get("effort") in CLAUDE_EFFORTS}


def default_effort_for(model, path=None):
    """The effort a Claude chat runs at when its options box names none: the
    chosen model's catalog entry, else DEFAULT_EFFORT. A chat's own pick is
    applied by the caller and always wins."""
    m = (model or "").strip().lower()
    for word, catalog_id in _EFFORT_FAMILY:
        if word in m:
            return _policy_efforts(path).get(catalog_id) or DEFAULT_EFFORT
    return DEFAULT_EFFORT

#: The rows the picker shows first. Same ids as _CLAUDE_MODELS except that
#: `fable` is published as `best` -- see the note above.
_CLAUDE_CATALOG_MODELS = (
    {"id": "",       "name": "Account default",
     "note": "whatever `claude` is configured to use"},
    {"id": "best",   "name": "Best available", "tag": "newest",
     "note": "the newest model this account can run (Fable 5.1 today)"},
    {"id": "opus",   "name": "Opus",
     "note": "most capable, slowest, highest cost"},
    {"id": "sonnet", "name": "Sonnet",
     "note": "balanced default for most work"},
    {"id": "haiku",  "name": "Haiku",
     "note": "fastest and cheapest, least capable"},
)

#: "More models": the pinned historical snapshots and the explicit 1M-context
#: spellings. Behind a disclosure because nobody picking a model for the first
#: time wants them, and present at all because someone pinning a build for
#: reproducibility does.
#:
#: The `[1m]` suffix is the CLI's own way of asking for the 1M context window on
#: a model whose default assumption is smaller; it is part of the id string that
#: reaches `--model`, not a separate flag.
_CLAUDE_MORE_MODELS = (
    {"id": "claude-opus-4-8",   "name": "Opus 4.8",   "note": "pinned snapshot"},
    {"id": "claude-opus-4-7",   "name": "Opus 4.7",   "note": "pinned snapshot"},
    {"id": "claude-opus-4-6",   "name": "Opus 4.6",   "note": "pinned snapshot"},
    {"id": "claude-sonnet-4-6", "name": "Sonnet 4.6", "note": "pinned snapshot"},
    {"id": "opus[1m]",          "name": "Opus · 1M context",
     "note": "Opus with the 1M-token window requested explicitly"},
    {"id": "sonnet[1m]",        "name": "Sonnet · 1M context",
     "note": "Sonnet with the 1M-token window requested explicitly"},
)

#: DeepSeek's "more" list is empty and that is an answer: the fork publishes
#: three concrete ids and no aliases, so there is nothing older to hide. Codex's
#: is empty for the opposite reason -- its roster is discovered per account, so
#: everything it knows is current by construction.
_DEEPSEEK_MORE_MODELS = ()

#: Which providers have a fast / service-tier switch. Codex's native binary
#: carries a `service_tier` config key (recorded in the shared spec); Claude and
#: DeepSeek have no equivalent, so their panes must not render the control.
#: Declared here rather than branched on an id at the point of use, same rule as
#: every other per-provider fact in this file.
_FAST_PROVIDERS = frozenset({"codex"})

#: What `""` resolves to, per provider, when this build can honestly say.
#:
#: Claude is ABSENT on purpose and the asymmetry is the same one budget.py
#: documents: `claude` with no model selected resolves to whatever the operator
#: configured the CLI with, which nothing here can read. DeepSeek's default IS
#: knowable -- its ACP session/new reports deepseek-v4-flash, measured
#: 2026-09-07. Codex's is discovered and is asked for at call time, so it is not
#: in this table either.
_STATIC_DEFAULT_MODEL = {
    "deepseek": "deepseek-v4-flash",
}

# DeepSeek's, passed as `-m <id>`. NOT aliases -- the fork takes concrete ids,
# and its ACP session/new advertises exactly deepseek-v4-pro and
# deepseek-v4-flash (measured 2026-09-07). `""` is the CLI's own default, which
# that same measurement showed to be deepseek-v4-flash.
#
# THE ALLOW-LIST IS LOAD-BEARING HERE IN A WAY IT IS NOT FOR CLAUDE. The fork
# does not validate -m. Its entire check is
#     resolveDeepSeekModel(m) { return m?.startsWith("deepseek-") ? m : "deepseek-chat" }
# so `deepseek-v9-nonsense` is forwarded verbatim to the API and `deepsek-v4-pro`
# (one typo) silently answers as deepseek-chat. Measured on the wire, both.
# Nothing downstream will refuse a bad id, so this tuple is the only refusal.
# POSSIBLE CROSS-CHECK, NOT WIRED (2026-09-07). `session/new` already returns
# the CLI's own list -- `models: {availableModels, currentModelId}` -- which
# AcpRuntime.new_session reads for `modes` and drops. Measured on the live
# build: auto / deepseek-v4-pro / deepseek-v4-flash / deepseek-v4-flash
# (the CLI's list really does carry that duplicate), currentModelId
# deepseek-v4-flash.
#
# That is a second source of truth for what follows, and this hardcoded tuple
# is the one that can go stale on a CLI upgrade with nothing to notice. Left
# unused on purpose for now -- consuming it would change which models the
# picker offers, which is a behaviour change, not a check. The cheap version
# is a test that compares the two and fails when they disagree.
_DEEPSEEK_MODELS = (
    {"id": "",                  "name": "CLI default",
     "note": "whatever `deepseek` is configured to use (currently V4 Flash)"},
    {"id": "deepseek-v4-pro",   "name": "V4 Pro",
     "note": "flagship, 1M context"},
    {"id": "deepseek-v4-flash", "name": "V4 Flash",
     "note": "fast and cheaper, 1M context"},
    # LISTED, DISABLED, WITH THE REASON ON SCREEN. Dropping it would hide that
    # the model exists; offering it enabled would be the offer-a-choice-that-
    # cannot-run failure ADAPTERS exists to prevent (see the ADAPTERS comment).
    # Also absent from the CLI's own ACP-advertised list, so even the fork does
    # not currently claim it is reachable this way.
    {"id": "deepseek-v4-flash-vision-exp", "name": "V4 Flash Vision",
     "note": "experimental multimodal",
     "selectable": False,
     "unavailable_reason":
         "this panel has no image channel -- an attachment is uploaded into "
         "the workdir and handed to the agent as a FILE PATH, and the ACP "
         "prompt it sends carries text blocks only. This model would receive "
         "a filename where it expects an image, so it is listed rather than "
         "offered."},
)

#: ONE ENTRY, AND THE EMPTINESS IS THE MEASUREMENT.
#:
#: codex-cli 0.153.2 publishes NO model list. There is no `codex models`
#: subcommand (checked against the full command list on 2026-09-08), nothing in
#: `codex exec --help`, and no model roster in the generated app-server schema
#: bundle. The only id this build has ever OBSERVED is the default the CLI
#: chose for itself -- `gpt-5.6-terra`, read out of a session rollout's
#: turn_context -- and that is a snapshot of a server-side default, not a menu.
#:
#: So the picker offers "let codex decide" and nothing else. The alternative
#: was inventing plausible OpenAI ids, and `-m` does NOT protect us from that:
#: measured, `-m gpt-5-codex` was ACCEPTED, warned "Model metadata for
#: `gpt-5-codex` not found. Defaulting to fallback metadata; this can degrade
#: performance and cause issues", and ran anyway. A wrong id therefore does not
#: fail loudly -- it silently degrades the session. Same laxity as DeepSeek's
#: `-m`, same mitigation: clean_model() gates every value against this tuple.
#:
#: "" is legal and means "no flag" (build_codex_args omits -m), which is why
#: this cannot rely on the truthiness of clean_model() alone.
#: RE-MEASURED 2026-09-08 against codex-cli 0.153.2, because "no model list"
#: is a claim that has to be re-checked before it is used to justify an empty
#: picker. It still holds, and here is everything that was asked:
#:
#:   codex models …                 no such subcommand (full command list read)
#:   codex exec --help              `-m, --model <MODEL>`, no enumeration
#:   codex app-server
#:     generate-json-schema         39 files, 1.79 MB, ZERO concrete model ids
#:   codex doctor                   reports `model  <default> · openai`
#:
#: The CLI itself does not know a roster. So this stays a one-entry list and
#: the picker keeps meaning what it says.
#:
#: WHAT IS AUTHORITATIVE, AND IS NOW USED: the operator's OWN config. codex
#: reads `model` out of $CODEX_HOME/config.toml, and `-p/--profile` layers
#: $CODEX_HOME/<name>.config.toml on top of it. A value the operator wrote
#: there is not a guess -- it is the model this machine is actually set up to
#: use -- so codex_config_models() surfaces it beside the default instead of
#: leaving the picker pretending there is nothing to choose. On a machine with
#: no config.toml (the common case) the picker is exactly what it was.
_CODEX_MODELS = (
    {"id": "", "name": "CLI default",
     "note": "whatever `codex` is configured to use"},
)

#: Where codex keeps its own configuration. CODEX_HOME wins, as it does for
#: codex itself.
def _codex_home():
    return Path(os.path.expanduser(
        os.environ.get("CODEX_HOME") or "~/.codex"))


#: `model = "..."` at the top level of a codex config file. A LINE SCAN, not a
#: TOML parse, and that is deliberate: tomllib is 3.11+ and this package still
#: runs its tests on 3.9, so a parser would have to be vendored to read one
#: key. The scan is anchored to column 0 so a `model` nested under any
#: `[table]` cannot be mistaken for the top-level default, and it accepts only
#: a quoted scalar -- anything it does not understand is simply not offered.
_CODEX_MODEL_LINE = re.compile(r'^model\s*=\s*["\']([^"\']+)["\']\s*(?:#.*)?$',
                               re.M)

#: mtime-keyed cache. models_for() is on the settings read path, which every
#: fs call goes through, and this must not become a stat-plus-read storm. The
#: key is (path, mtime, size) per file, so an edit is picked up on the next
#: call and nothing else costs more than one stat.
_CODEX_MODEL_CACHE = {}


def _codex_model_from(path):
    """The top-level `model` in one codex config file, or None. Never raises."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime, st.st_size)
    if key in _CODEX_MODEL_CACHE:
        return _CODEX_MODEL_CACHE[key]
    found = None
    try:
        # Capped: a config file is a few KB, and a caller must not be able to
        # make this read an arbitrarily large file off the settings path.
        m = _CODEX_MODEL_LINE.search(path.read_text(encoding="utf-8",
                                                    errors="replace")[:65536])
        if m:
            found = m.group(1).strip() or None
    except OSError:
        found = None
    _CODEX_MODEL_CACHE.clear() if len(_CODEX_MODEL_CACHE) > 64 else None
    _CODEX_MODEL_CACHE[key] = found
    return found


def codex_config_models():
    """Models the operator's own codex config declares, in menu order.

    () on a machine with no codex config, which is the ordinary case and the
    reason this can never make the picker worse.

    TWO SOURCES, both codex's own:
      $CODEX_HOME/config.toml          -> the base default
      $CODEX_HOME/<name>.config.toml   -> one per `-p/--profile`

    NOTHING IS INVENTED HERE. Every id returned was typed by the operator into
    a file codex reads. If they wrote something codex will not accept, codex
    answers for it the same way it would have without Sutra -- and Sutra is not
    in a position to know better, because the CLI publishes no roster to check
    against (see _CODEX_MODELS).
    """
    home = _codex_home()
    out, seen = [], set()
    base = _codex_model_from(home / "config.toml")
    if base:
        seen.add(base)
        out.append({"id": base, "name": base,
                    "note": "from your codex config"})
    try:
        profiles = sorted(home.glob("*.config.toml"))
    except OSError:
        profiles = []
    for p in profiles:
        mid = _codex_model_from(p)
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append({"id": mid, "name": mid,
                    "note": "from your %s codex profile" % p.name.split(".")[0]})
    return tuple(out)


#: Codex's own enumerations, read out of the CLI's REJECTION of a bad value --
#: the only authoritative source there is, and cheap to re-check:
#:
#:   codex exec --strict-config -c model_reasoning_summary='"__bogus__"' …
#:     -> unknown variant `__bogus__`, expected one of `auto`, `concise`,
#:        `detailed`, `none`
#:   codex exec --strict-config -c model_verbosity='"__bogus__"' …
#:     -> unknown variant `__bogus__`, expected one of `low`, `medium`, `high`
#:
#: Measured 2026-09-08 on 0.153.2 WITHOUT spending a model turn: `--strict-config`
#: validates the config before anything is sent, and the probe resumed a
#: nonexistent thread so the run died at "No prompt provided via stdin".
#:
#: `model_reasoning_effort` IS a real key -- the same probe proves it, because a
#: made-up key is refused with "unknown configuration field" and that one was
#: not -- but it ACCEPTED "__bogus__" as a value, so this build has no
#: authoritative list of its levels. It is therefore NOT offered: a picker of
#: guessed levels is the invented-capability this module refuses everywhere
#: else. If a later codex declares them, the probe above is how to find out.
#:
#: "" is legal in both and means "leave it to codex" (no -c emitted).
CODEX_REASONING_SUMMARY = ("", "auto", "concise", "detailed", "none")
CODEX_VERBOSITY = ("", "low", "medium", "high")

#: What the model CATALOGUE offers as efforts for a Codex model the discovered
#: roster says nothing about. NOT an allow-list for the wire -- build_codex_args
#: still validates against codex_efforts_for(model), which is the roster and only
#: the roster. This is a label set for a picker that would otherwise be empty on
#: a machine where discovery has not run, and it is the intersection every
#: measured Codex model has agreed on (terra adds `ultra`, luna does not, 5.5
#: stops at `xhigh`). Declared in the shared spec; kept narrow on purpose.
CODEX_FALLBACK_EFFORTS = ("low", "medium", "high", "xhigh")

#: Which of PERMISSION_MODES codex can actually enforce, and why the other
#: three are absent rather than pending.
#:
#: VERIFIED against codex-cli 0.153.2 on 2026-09-08. The sandbox enumeration
#: comes from the CLI's own rejection ("[possible values: read-only,
#: workspace-write, danger-full-access]") and the enforcement was measured
#: through `codex sandbox`, which runs a command under the same seatbelt
#: without spending a model turn:
#:
#:   read-only          reads succeed; a write answers "Operation not permitted"
#:   workspace-write    a write inside the workspace root succeeds; the same
#:                      write to $HOME answers "Operation not permitted"
#:   danger-full-access writes succeed
#:
#: plan               -> --sandbox read-only        + approval_policy=never
#: acceptEdits        -> --sandbox workspace-write  + approval_policy=never
#: bypassPermissions  -> --dangerously-bypass-approvals-and-sandbox
#:
#: auto / manual / dontAsk: NO codex equivalent and no near-miss. codex's
#: approval_policy values are untrusted/on-failure/on-request/granular/never
#: (from its config-load error), and every one except `never` waits for an
#: answer on a channel a chat pane does not have -- a `codex exec` run has
#: nobody to approve anything, so it would stall rather than prompt. Offering
#: one of these would repeat the DeepSeek bug this per-provider list was
#: written to end: the control displayed the operator's choice while something
#: else ran.
#:
#: DECLARED, NOT LEFT EMPTY, and that distinction is load-bearing.
#: permission_modes_for() falls back to ALL SIX for a provider that declares
#: (), and its docstring says that default is "safe only because it is
#: unreachable". The moment codex entered ADAPTERS it became reachable, so an
#: empty declaration here would have put auto/manual/dontAsk on a Codex pane.
_CODEX_PERMISSION_MODES = ("plan", "acceptEdits", "bypassPermissions")


def _model_selectable(entry):
    """Absent `selectable` means True.

    Deliberate: only the one unavailable entry carries the key, so every
    provider's ordinary rows stay byte-identical to what they were before this
    field existed -- nothing about Claude's payload moved.
    """
    return entry.get("selectable", True) is not False


def models_for(pid):
    """Every model this provider declares, in menu order. () for a provider
    that has none -- which is a real answer, not a gap: its rows render
    without a picker rather than with someone else's.

    CODEX IS COMPOSED, not static, and it is the only one: its catalogue entry
    carries "CLI default" and codex_config_models() appends whatever the
    operator's own codex config declares. Nothing about any other provider's
    list changes -- the branch is keyed on the id and every other spec returns
    its tuple exactly as before.

    Cheap enough for this path (a stat per config file, cached on mtime; see
    _codex_model_from) and it must stay that way: load_settings() reaches here
    and every fs call reaches load_settings().
    """
    for spec in _CATALOG:
        if spec["id"] == pid:
            declared = spec.get("models", ())
            if pid == "codex":
                return tuple(declared) + _codex_discovered()
            return declared
    return ()


def _codex_discovered():
    """Codex's own model list, then the operator's config, then nothing.

    ORDER IS THE POINT. codex_models.cached() holds what `model/list` last
    answered -- account-scoped, server-fresh, and Codex's own opinion of what
    it will run -- so it wins. codex_config_models() stays BEHIND it rather
    than being deleted: a `model` the operator wrote into their own codex
    config is a legitimate custom choice (a self-hosted provider, an
    entitlement Sutra cannot see), and it is only reachable through this path.
    It is consulted only when discovery has produced nothing, so on an ordinary
    machine it costs one stat and changes nothing.

    NO SUBPROCESS, EVER. cached() is pure by construction -- the spawning half
    lives in codex_models.refresh_if_stale() and is called from the auth route,
    never from here. This function is reached by load_settings(), and every
    fs/tree, fs/read and settings GET goes through that; the same rule that
    keeps codex_auth() out of _describe() applies with more force here.

    Underscore keys are stripped: `_default` is bookkeeping between
    codex_models and the picker's first option, `_window` is what
    budget.window_for reads, and a key that reaches a client frame because
    nothing removed it is how a private field becomes an accidental contract.

    THE IMPORT IS DEFERRED because codex_models imports THIS module -- a
    top-level import here would be a cycle. Same shape org_api uses for its
    `import app`, and cheap after the first call (sys.modules).
    """
    import codex_models
    # Before discovery has run in this process (it runs only from the Codex auth route), Codex's
    # own models_cache.json is the same roster model/list would answer. Without this the SEO
    # Writer and any chat opened before the Codex settings row offered one model (2026-09-14).
    found = codex_models.cached() or codex_models.cache_file_models()
    if not found:
        return codex_config_models()
    # `_default` becomes the public `default`, and `efforts` rides along. Both
    # are needed by the CLIENT and by nothing else: the Reasoning-effort picker
    # offers the SELECTED model's efforts, and on "CLI default" it has to know
    # which model that resolves to. Server-side validation resolves the same
    # two facts through codex_efforts_for(), so the control and the validator
    # cannot disagree about what is offerable.
    #
    # Codex-only keys. Claude's and DeepSeek's entries are untouched, and no
    # existing reader looks past {id, name, note, selectable}.
    return tuple(dict({k: v for k, v in m.items() if not k.startswith("_")},
                      default=bool(m.get("_default")))
                 for m in found)


def codex_efforts_for(model_id=None):
    """The reasoning efforts a Codex model supports, or ().

    The allow-list build_codex_args validates a per-turn `reasoning_effort`
    against. It is PER MODEL and discovered, never declared: measured on one
    account, terra offers `ultra`, luna does not, and 5.5 stops at `xhigh`.

    () is the honest answer when discovery has not run or the model is unknown,
    and it makes the control degrade correctly -- only "default" is offered and
    no override is emitted, which is exactly the behaviour before this existed.

    NO SUBPROCESS. Reads codex_models' cache, like _codex_discovered().
    """
    import codex_models
    return codex_models.efforts_for(model_id)


def codex_default_model():
    """The id `codex` would pick on its own, or None.

    Metadata about the CLI default, so the picker's first row can say what it
    resolves to. NOT a selection: choosing "CLI default" still stores "" and
    still emits no -m.
    """
    import codex_models
    return codex_models.default_id()


def catalog_models_for(pid):
    """(main, more) for the RICH picker, as two tuples of entry dicts.

    The catalogue view. models_for() is the flat legacy list and is unchanged;
    this is what model_catalog_for() publishes, and the two deliberately differ
    for Claude (`best` here, `fable` there -- see the catalogue note above).

    Every provider that is not specially catalogued falls back to its flat list
    as the main tuple with an empty `more`, so adding a provider needs no change
    here before its picker works.
    """
    if pid == "claude":
        return _CLAUDE_CATALOG_MODELS, _CLAUDE_MORE_MODELS
    if pid == "deepseek":
        return tuple(models_for(pid)), _DEEPSEEK_MORE_MODELS
    return tuple(models_for(pid)), ()


def _catalog_efforts(pid, model_id):
    """The effort values ONE model accepts, as a list. [] when none apply.

    Claude's five are a constant because the CLI accepts the same set on every
    model (measured); Codex's are per model and discovered from its own roster,
    with a documented fallback for a model the roster does not describe;
    DeepSeek carries no effort lever at all on the ACP wire, which is measured
    and not a gap (see _CLAUDE_TURN_OPTIONS).
    """
    if pid == "claude":
        return list(CLAUDE_EFFORTS)
    if pid == "codex":
        found = codex_efforts_for(model_id or None)
        return list(found) if found else list(CODEX_FALLBACK_EFFORTS)
    return []


def default_model_for(pid):
    """The id `""` resolves to for this provider, or "" when it cannot be known.

    "" is the honest answer for Claude and the caller must render it as "the
    CLI's own default" rather than as a model name -- see _STATIC_DEFAULT_MODEL.
    """
    if pid == "codex":
        try:
            return codex_default_model() or ""
        except Exception:
            return ""
    return _STATIC_DEFAULT_MODEL.get(pid, "")


def fast_supported(pid):
    """True when this provider has a fast / service-tier switch to offer.

    The one place that question is answered. ws_chat's per-turn `service_tier`
    option is validated against this, so the control and the validator cannot
    disagree about which panes may send one.
    """
    return pid in _FAST_PROVIDERS


def _catalog_entry(pid, entry):
    """One catalogue row, with its efforts attached. Never mutates the source.

    THE ENTRY'S OWN `efforts` WINS. Codex's discovered rows already carry the
    set that model published, and that is a stronger source than anything this
    function can look up -- codex_efforts_for() reads the RPC cache alone, which
    is empty until the Codex auth route has run, so a fresh process would have
    downgraded a known per-model set to the generic fallback.
    """
    out = dict(entry)
    own = entry.get("efforts")
    out["efforts"] = (list(own) if own
                      else _catalog_efforts(pid, entry.get("id") or ""))
    out.setdefault("selectable", _model_selectable(entry))
    return out


def model_catalog_for(pid):
    """The rich catalogue for one provider, or None when it declares no models.

        {"models": [...], "more": [...], "fast": bool, "default": "<id>"}

    None rather than an empty dict for a provider with no picker, so the
    client's "does this pane have a model control" test is the same test it
    already uses for models_by_provider: is this provider in the dict.
    """
    if not models_for(pid):
        return None
    main, more = catalog_models_for(pid)
    if not main:
        return None
    return {
        "models": [_catalog_entry(pid, m) for m in main],
        "more": [_catalog_entry(pid, m) for m in more],
        "fast": fast_supported(pid),
        "default": default_model_for(pid),
    }


def all_model_catalog_by_provider():
    """{provider_id: catalogue} for every provider that has a picker.

    Same absent-when-empty contract as all_models_by_provider(), and it rides
    BESIDE that map in GET /api/settings rather than replacing it.
    """
    out = {}
    for spec in _CATALOG:
        cat = model_catalog_for(spec["id"]) if spec.get("models") else None
        if cat:
            out[spec["id"]] = cat
    return out


def _catalog_extra_entries(pid):
    """Catalogue rows that are NOT in the flat models_for() list.

    Exists so model_ids_for / selectable_model_ids_for can widen to the
    catalogue without models_for() -- and therefore models_by_provider -- moving
    an inch. `best` and the six pinned Claude ids live only here.
    """
    have = {m["id"] for m in models_for(pid)}
    main, more = catalog_models_for(pid)
    return tuple(m for m in tuple(main) + tuple(more) if m["id"] not in have)


def model_ids_for(pid):
    """Every declared id, selectable or not. Use for "is this catalogued".

    WIDENED to the catalogue, deliberately. A user who picks `best` in the new
    screen has that id written to settings.json; if this set still answered
    only the flat list, the very next read would call it unknown and the choice
    would evaporate. Adding an id to the picker and refusing it at the API is
    the offer-a-choice-that-cannot-run failure this module exists to prevent,
    pointed the other way round.
    """
    return frozenset(m["id"] for m in
                     tuple(models_for(pid)) + _catalog_extra_entries(pid))


def selectable_model_ids_for(pid):
    """The ids a session may actually RUN on. The narrower set, and the one
    clean_model() gates against -- a listed-but-disabled model must be
    unreachable through the API too, not merely greyed out in the menu."""
    return frozenset(m["id"] for m in
                     tuple(models_for(pid)) + _catalog_extra_entries(pid)
                     if _model_selectable(m))


def all_models_by_provider():
    """{provider_id: [model, ...]} for every provider that declares any.

    The shape the settings endpoint publishes. A provider with no models is
    ABSENT rather than present-and-empty, so the client's test for "does this
    provider have a picker" is the same test as "is it in this dict".

    GOES THROUGH models_for(), and that is the fix for a real bug: this read
    `spec["models"]` straight off _CATALOG, which is the STATIC tuple. Every
    other consumer -- clean_model, selectable_model_ids_for, model_ids_for --
    already went through models_for(), so when codex's list became composed
    (catalogue + what `model/list` discovered) a selected model VALIDATED and
    reached `-m` correctly while the picker had no rows to select from. The
    published payload was the one path that bypassed the composition, so the
    Codex picker showed "CLI default" alone on a machine where discovery had
    just returned three models.

    UNCHANGED FOR EVERY OTHER PROVIDER: models_for() returns spec["models"]
    verbatim for every id except codex. The `if spec.get("models")` guard still
    keys off the STATIC tuple on purpose -- it answers "is this provider
    supposed to have a picker at all", which must not become true for a
    provider with no declared models just because some future discovery
    returned something.
    """
    return {spec["id"]: list(models_for(spec["id"]))
            for spec in _CATALOG if spec.get("models")}


def turn_options_for(pid):
    """The per-turn controls this provider can HONOUR, in no particular order.
    () for a provider whose transport carries none -- which is a real answer,
    not a gap: its pane renders without those controls rather than with
    controls that are discarded server-side.

    An unknown provider gets () rather than Claude's list. A provider this
    build has never heard of cannot be assumed to accept Claude's flags, and
    guessing yes is what puts a dead control on screen."""
    for spec in _CATALOG:
        if spec["id"] == pid:
            return spec.get("turn_options", ())
    return ()


def all_turn_options_by_provider():
    """{provider_id: [option, ...]} for every provider that honours any.

    Same contract as all_models_by_provider: a provider that honours none is
    ABSENT rather than present-and-empty, so the client's "does this pane have
    turn options" test is the same test as "is it in this dict". Claude always
    declares five, so a LOADED map is never empty -- which is what lets the
    client tell "not fetched yet" from "declares none"."""
    return {spec["id"]: list(spec["turn_options"])
            for spec in _CATALOG if spec.get("turn_options")}


def permission_modes_for(pid):
    """The subset of PERMISSION_MODES this provider can actually enforce.

    Falls back to ALL of them when a provider declares none, and for a provider
    that is not catalogued at all -- the opposite default from
    turn_options_for() above, and deliberately so. A missing turn option means
    a control vanishes, which is safe; a missing permission mode would mean the
    pane offers no way to say "plan", and hiding a safety control is the wrong
    direction to be wrong in.

    EMPTY AND MISSING ARE TREATED THE SAME HERE, which they are not in
    all_permission_modes_by_provider() below -- that omits an empty declaration
    so the CLIENT applies its own fallback. Both halves therefore answer "all
    of them" for a provider that declares (). Returning () here instead
    would leave this helper disagreeing with the panel about the same provider,
    and two copies of an answer that can differ is how one of them goes stale.

    A provider declares () when the question is unanswerable rather than
    answered: no adapter, so no pane can run it, and nothing has ever measured
    which modes it would honour. Guessing Claude's six is safe only because it
    is unreachable."""
    for spec in _CATALOG:
        if spec["id"] == pid:
            return spec.get("permission_modes") or PERMISSION_MODES
    return PERMISSION_MODES


def all_permission_modes_by_provider():
    """{provider_id: [mode_id, ...]} for every provider that enforces any."""
    return {spec["id"]: list(spec["permission_modes"])
            for spec in _CATALOG if spec.get("permission_modes")}


def model_flag_for(pid):
    """The CLI flag that carries the model, or None when the provider has no
    model lever. `--model` for claude, `-m` for deepseek."""
    for spec in _CATALOG:
        if spec["id"] == pid:
            return spec.get("model_flag")
    return None


def usage_kind_for(pid):
    """What KIND of usage fact this provider reports:

      window-percent  a share of a rate-limit window (claude)
      balance         money left in a pay-as-you-go account (deepseek)
      none            neither -- do not show a figure, and do not borrow
                      another provider's

    `none` is why this is a declared kind rather than an if/else. The client's
    usage branch was `if deepseek -> balance else -> Anthropic percentage`, so
    Codex would have rendered Claude's percentage on a Codex session the day it
    became selectable.
    """
    for spec in _CATALOG:
        if spec["id"] == pid:
            return spec.get("usage_kind", "none")
    return "none"


def clean_model(value, provider_id):
    """A model id this PROVIDER can run, or None. Never raises, never passes
    junk to the CLI.

    `provider_id` is mandatory on purpose. An optional one -- or one defaulting
    to "claude" -- reintroduces the exact bug this change exists to remove: a
    forgotten argument would silently validate a DeepSeek session's model
    against Claude's list.

    Gated on the SELECTABLE set, so a catalogued-but-disabled id (the vision
    model) is refused here and not only hidden in the menu.
    """
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if (v and v in selectable_model_ids_for(provider_id)) else None


def stored_model(provider_id):
    """The model chosen for THIS provider, or None for the CLI's own default.

    Each provider keeps its own slot, so switching provider and back does not
    discard the choice -- and a Claude id can never leak onto a DeepSeek spawn,
    which a single shared scalar made possible.
    """
    return clean_model(_stored_models().get(provider_id), provider_id)


def _stored_models():
    """{provider_id: model_id} as stored, with the legacy scalar migrated.

    Storage moved from a single `model` key to `model_by_provider` when the
    picker became per-provider. The old scalar only ever described Claude, so
    it migrates into that slot. Read-side only: nothing rewrites the file until
    the next save, so an older build reading this file still finds what it
    expects.
    """
    raw = _raw_settings()
    by_provider = raw.get("model_by_provider")
    out = ({k: v for k, v in by_provider.items() if isinstance(v, str)}
           if isinstance(by_provider, dict) else {})
    legacy = raw.get("model")
    if "claude" not in out and isinstance(legacy, str):
        out["claude"] = legacy
    return out


PERMISSION_MODE_NOTES = {
    "plan": "read-only planning: the agent proposes edits, you approve each one.",
    "auto": "the CLI decides per action, using its own rules and your "
            "~/.claude settings.",
    "manual": "every action is asked about. Approvals need a persistent session "
              "channel the panel does not have yet, so today this defers to the "
              "CLI's own handling rather than prompting in this pane.",
    "dontAsk": "never prompts. Actions the rules do not already allow are "
               "declined rather than escalated.",
    "acceptEdits": "the agent WRITES FILES without asking -- it can create, "
                   "modify and delete files under the workdir. Opt in knowingly.",
    "bypassPermissions": "everything is auto-approved, including shell commands "
                         "-- the widest setting there is.",
}


# --------------------------------------------------------------- access ----
# WHAT THE SCREEN OFFERS, mapped onto what has always been STORED.
#
# The six native ids above are CLI vocabulary: plan / acceptEdits /
# bypassPermissions / auto / manual / dontAsk. They are precise and nobody
# outside this codebase knows what they mean. The new screens offer four plain
# choices instead -- read / edits / auto / full -- and this table is the only
# place the two vocabularies meet.
#
# NOTHING NEW IS STORED. An `access` id lives in the UI and API layer and is
# translated here; settings.json keeps holding a NATIVE mode under the existing
# `permission_mode` key, so an older build reading the same file finds exactly
# what it expects and a routine that wrote `dontAsk` two months ago still runs
# as `dontAsk`.
#
# ONE TABLE, not a switch in the picker and another in the validator. The bug
# this shape prevents is the one models_by_provider was written about: two
# copies of a per-provider answer that can drift, so the control displays one
# choice while something else runs.
#
# `manual` and `dontAsk` are DELIBERATELY ABSENT from the four. They are not
# retired -- they remain valid stored values, they still load, and
# advanced_permission_modes() below hands them to the UI for its "Advanced"
# disclosure. A choice someone already made must never vanish because a newer
# screen has a shorter list.
#
# CONSENT GOES THROUGH THE ONE GATE. `edits` and `full` map to acceptEdits and
# bypassPermissions, which are UNSAFE_PERMISSION_MODES, so they go through
# unsafe_modes_allowed() and the same UNSAFE_ACK_PHRASE. This table renames
# nothing about that and adds no second gate of its own.
#
# WHAT THAT GATE ANSWERS CHANGED ON 2026-09-18, and this table did not: it is
# an opt-out now (CLAMP_MODES_ENV), so in the shipped posture all four are
# settable and `full` is the default. `warn` is therefore doing more work than
# it used to -- it is the only thing on the row telling the operator that the
# option selected for them auto-approves shell commands. Keep it truthful.
ACCESS_OPTIONS = (
    {"id": "read", "label": "Read only",
     "desc": "Looks and plans. Changes nothing.", "warn": False,
     "native": {"claude": "plan", "codex": "plan", "deepseek": "plan"}},
    {"id": "edits", "label": "Accept edits",
     "desc": "Edits files in this folder. Asks for anything else.", "warn": False,
     "native": {"claude": "acceptEdits", "codex": "acceptEdits",
                "deepseek": "acceptEdits"}},
    # Claude ONLY, and the emptiness elsewhere is measured rather than pending.
    # codex's approval_policy values all wait for an answer on a channel a chat
    # pane does not have, and DeepSeek's ACP layer has no equivalent of `auto`
    # at all -- see _CODEX_PERMISSION_MODES and _DEEPSEEK_PERMISSION_MODES.
    {"id": "auto", "label": "Approve for me",
     "desc": "Same limit, but the tool approves routine requests itself.",
     "warn": False,
     "native": {"claude": "auto"}},
    {"id": "full", "label": "Full access",
     "desc": "Anything on this Mac, without asking.", "warn": True,
     "native": {"claude": "bypassPermissions", "codex": "bypassPermissions",
                "deepseek": "bypassPermissions"}},
)

#: Native modes that are real, still stored, still honoured -- and not one of
#: the four. Derived from the table rather than typed out twice, so a native id
#: promoted into ACCESS_OPTIONS leaves this list automatically.
def advanced_permission_modes():
    """The native modes the new list does not cover, in PERMISSION_MODES order.

    `manual` and `dontAsk` today. Routines write `dontAsk`, so this is not a
    legacy shelf -- it is a live part of the product that simply has no plain-
    English button.
    """
    mapped = set()
    for opt in ACCESS_OPTIONS:
        mapped.update(opt["native"].values())
    return [m for m in PERMISSION_MODES if m not in mapped]


def access_native(access_id, provider_id):
    """The native permission mode `access_id` means for `provider_id`, or None.

    None is a real answer, not a failure: `auto` on a Codex pane has no native
    equivalent, and the caller must refuse rather than substitute one.
    """
    for opt in ACCESS_OPTIONS:
        if opt["id"] == access_id:
            return opt["native"].get(provider_id)
    return None


def access_for_native(mode, provider_id=None):
    """The access id a stored native mode shows as, or None for an advanced one.

    The reverse direction, and the UI needs it on every load: settings.json
    holds `acceptEdits` and the radio group has to come up on "Accept edits".
    `provider_id` narrows the lookup to that provider's own mapping; without it
    any provider's mapping counts, which is what a settings screen rendered
    before a provider is chosen needs.
    """
    if mode not in PERMISSION_MODES:
        return None
    for opt in ACCESS_OPTIONS:
        natives = opt["native"]
        if provider_id is not None:
            if natives.get(provider_id) == mode:
                return opt["id"]
        elif mode in natives.values():
            return opt["id"]
    return None


def access_options(provider_id=None, settings=None):
    """The four choices, each with everything a screen needs to draw it.

        {id, label, desc, warn, native, providers, settable, requires_unlock}

    `native` is the native mode for `provider_id` (None when that provider does
    not offer this option), and `providers` lists every provider that does.

    `settable` answers BEFORE the click, the same way the existing
    permission_modes list does: an option the server will refuse must say so up
    front, or the screen reads as broken rather than as gated.
    """
    unlocked = unsafe_modes_allowed(settings)
    out = []
    for opt in ACCESS_OPTIONS:
        native_here = opt["native"].get(provider_id) if provider_id else None
        gated = any(m in UNSAFE_PERMISSION_MODES for m in opt["native"].values())
        out.append({
            "id": opt["id"],
            "label": opt["label"],
            "desc": opt["desc"],
            "warn": opt["warn"],
            "native": native_here,
            "providers": sorted(opt["native"]),
            "requires_unlock": gated,
            "settable": (not gated) or unlocked,
        })
    return out


def access_by_provider():
    """{provider_id: [access id, ...]} -- which of the four each pane may offer.

    Absent-when-empty, same contract as models_by_provider and
    turn_options_by_provider: a provider with no entry has no access control to
    draw, and the client's test for "does this pane have one" is "is it in this
    dict".
    """
    out = {}
    for opt in ACCESS_OPTIONS:
        for pid in opt["native"]:
            out.setdefault(pid, []).append(opt["id"])
    order = [o["id"] for o in ACCESS_OPTIONS]
    return {pid: sorted(ids, key=order.index) for pid, ids in out.items()}


def access_native_map():
    """{access id: {provider id: native mode}} -- the raw table, published.

    Shipped so the client can show which native mode a choice really sets
    (Settings > Advanced does) without keeping a second copy of this mapping in
    JavaScript. A JS copy would drift the day a provider is added, silently.
    """
    return {opt["id"]: dict(opt["native"]) for opt in ACCESS_OPTIONS}


# ----------------------------------------------- per-provider settings -----
# The switches that belong to ONE assistant rather than to Sutra.
#
# Every row is a boolean with a DEFAULT, and the default is the CLI's own
# behaviour -- so a machine that has never touched this screen behaves exactly
# as it does today, and `provider_settings` in settings.json is absent
# entirely. Only a value that DIFFERS from its default is stored, which is why
# turning something off and back on leaves no trace.
#
# NOTHING HERE IS APPLIED BY THIS MODULE. providers.py owns the table and the
# storage; the spawn path (build_agent_args / build_codex_args) reads
# provider_settings(pid) and decides what argv it turns into. Keeping the
# application out of here is what stops this file from growing a second opinion
# about the CLI's flags.
#
# EVERY KEY WAS CHECKED AGAINST THE REAL CLI BEFORE IT WAS LISTED:
#
#   claude `chrome`      `--chrome` AND `--no-chrome` are both in
#                        `claude --help` on 2.1.270, read 2026-09-14.
#   claude `subagents`   expressible through `--disallowedTools`, which is in
#                        the same help output. Which tool name goes in it is
#                        the spawn path's call, not this table's.
#   claude `workflows`   same lever, same reasoning.
#   codex  `memory`      `memories.use_memories` / `memories.generate_memories`
#                        are config keys the Codex native binary carries
#                        (recorded in the shared spec).
#   codex  `subagents`   `features.multi_agent`, same source.
#
# ONE PLANNED KEY WAS DROPPED RATHER THAN SHIPPED: claude `memory`. There is no
# memory switch in `claude --help` on 2.1.270 -- the only thing that turns
# auto-memory off is `--bare`, which ALSO drops hooks, LSP, plugin sync,
# attribution, background prefetches, keychain reads and CLAUDE.md discovery. A
# toggle labelled "Memory" that quietly disables seven other things is worse
# than no toggle, so it is absent until the CLI has a lever that means what the
# label says.
PROVIDER_SETTINGS_SCHEMA = {
    "claude": (
        {"key": "chrome", "label": "Claude in Chrome",
         "desc": "Let this assistant drive a Chrome tab you already have open.",
         "type": "boolean", "default": False},
        {"key": "subagents", "label": "Subagents",
         "desc": "Let it start helper agents to work on parts of a task in "
                 "parallel.",
         "type": "boolean", "default": True},
        {"key": "workflows", "label": "Workflows",
         "desc": "Let it run saved multi-step workflows.",
         "type": "boolean", "default": True},
    ),
    "codex": (
        {"key": "memory", "label": "Memories",
         "desc": "Let it read and write its own notes between sessions.",
         "type": "boolean", "default": True},
        {"key": "subagents", "label": "Subagents",
         "desc": "Let it start helper agents to work on parts of a task in "
                 "parallel.",
         "type": "boolean", "default": True},
    ),
}

#: The settings.json key. NEW and top-level, beside `model_by_provider` and
#: `permission_mode` -- never inside any of them. Nothing that exists today is
#: read, rewritten or reordered by this feature.
PROVIDER_SETTINGS_KEY = "provider_settings"


def provider_settings_schema():
    """{provider_id: [row, ...]} -- every switch, with its default.

    The client renders from this rather than from a hardcoded list, so a key
    added here appears on the screen without a JS change, and a key removed
    here disappears from the screen instead of lingering as a control that
    writes a value nothing reads.
    """
    return {pid: [dict(row) for row in rows]
            for pid, rows in PROVIDER_SETTINGS_SCHEMA.items()}


def _schema_rows(pid):
    return PROVIDER_SETTINGS_SCHEMA.get(pid, ())


def _stored_provider_settings(raw=None):
    """The raw stored map, sanitised to {pid: {known key: bool}}.

    Junk dies here: an unknown provider, an unknown key, a non-boolean value
    and a non-dict at any level are all dropped rather than carried. The file
    is hand-editable and is also written by older and newer builds, so this has
    to survive anything.
    """
    data = (raw if raw is not None else _raw_settings()).get(PROVIDER_SETTINGS_KEY)
    if not isinstance(data, dict):
        return {}
    out = {}
    for pid, rows in PROVIDER_SETTINGS_SCHEMA.items():
        got = data.get(pid)
        if not isinstance(got, dict):
            continue
        keep = {}
        for row in rows:
            v = got.get(row["key"])
            if isinstance(v, bool):
                keep[row["key"]] = v
        if keep:
            out[pid] = keep
    return out


def provider_settings(pid, raw=None):
    """The EFFECTIVE switches for one provider: every key, defaults filled in.

    This is what the spawn path reads. It always answers every key in the
    schema, so a caller never has to remember a default or handle a missing
    one -- `provider_settings("claude")["chrome"]` is always a bool.

    {} for a provider with no schema, which is a real answer: deepseek has no
    per-provider switches, and its spawn path asks for nothing.

    NOT the same thing as what is published. GET /api/settings sends
    stored_provider_settings() -- only the values that differ from a default --
    because the schema already carries the defaults and sending them twice is
    two copies of one fact.
    """
    rows = _schema_rows(pid)
    if not rows:
        return {}
    stored = _stored_provider_settings(raw).get(pid, {})
    return {row["key"]: stored.get(row["key"], row["default"]) for row in rows}


def stored_provider_settings(raw=None):
    """{provider_id: {key: value}} for NON-DEFAULT values only.

    The published shape. A provider whose every switch is at its default is
    absent, so an untouched machine sends `{}` and the client knows nothing was
    overridden without diffing anything.
    """
    out = {}
    for pid, rows in PROVIDER_SETTINGS_SCHEMA.items():
        stored = _stored_provider_settings(raw).get(pid, {})
        diff = {row["key"]: stored[row["key"]] for row in rows
                if row["key"] in stored and stored[row["key"]] != row["default"]}
        if diff:
            out[pid] = diff
    return out


def save_provider_settings(patch):
    """Merge `{pid: {key: bool}}` into settings.json and return load_settings().

    A PATCH, not a replacement: a provider absent from `patch` is untouched,
    and a key absent from a provider's dict is untouched. Sending a key back at
    its default REMOVES it from storage rather than writing it, which is what
    keeps the file free of rows that only restate the schema.

    Validates BEFORE writing, the same way save_settings() does. An unknown
    provider, an unknown key or a non-boolean value raises ValueError with the
    specific reason, so nothing is half-applied and the operator is never told
    a switch took effect when it did not.

    ONLY the `provider_settings` key is written. Every other key in the file is
    read and put back exactly as it was.
    """
    if not isinstance(patch, dict):
        raise ValueError("provider_settings must be an object of "
                         "{provider: {key: true|false}}")
    for pid, values in patch.items():
        rows = _schema_rows(pid)
        if not rows:
            raise ValueError(
                "provider %r has no per-provider settings -- known: %s"
                % (pid, ", ".join(sorted(PROVIDER_SETTINGS_SCHEMA))))
        if not isinstance(values, dict):
            raise ValueError("provider_settings[%r] must be an object" % pid)
        known = {row["key"] for row in rows}
        for key, value in values.items():
            if key not in known:
                raise ValueError(
                    "unknown setting %r for provider %r -- must be one of: %s"
                    % (key, pid, ", ".join(sorted(known))))
            if not isinstance(value, bool):
                raise ValueError(
                    "provider_settings[%r][%r] must be true or false, not %r"
                    % (pid, key, value))

    raw = _raw_settings()
    current = _stored_provider_settings(raw)
    for pid, values in patch.items():
        rows = {row["key"]: row for row in _schema_rows(pid)}
        slot = dict(current.get(pid, {}))
        for key, value in values.items():
            if value == rows[key]["default"]:
                slot.pop(key, None)      # a default is absence, not a row
            else:
                slot[key] = value
        if slot:
            current[pid] = slot
        else:
            current.pop(pid, None)
    if current:
        raw[PROVIDER_SETTINGS_KEY] = current
    else:
        raw.pop(PROVIDER_SETTINGS_KEY, None)
    _write_settings(raw)
    return load_settings()

# Providers this codebase can actually DRIVE. Keep in lockstep with app.py's
# ws_chat provider dispatch (SessionRuntime for claude, CodexRuntime for codex,
# AcpRuntime for deepseek; anything else falls through to the "no-adapter"
# refusal). Adding an id here without writing its adapter re-creates the bug
# this set exists to prevent.
#
# codex: ADDED 2026-09-08, and this note records what had to exist first.
# It was briefly in this set on 2026-09-04 as a staging step and taken back out
# the same day: with codex here the row rendered "Ready to use", accepted the
# click, and then died at connect with code "no-adapter" (app.py's
# `elif active_id != "claude"` arm) -- exactly the offer-a-choice-that-cannot-
# run failure this set exists to prevent. The note left behind said refusing at
# SELECTION time was the better error "until a CodexRuntime, a
# build_codex_args() and a third arm in the ws_chat dispatch exist".
#
# All three now exist: codex_runtime.CodexRuntime (`codex exec --json`,
# measured against codex-cli 0.153.2 on 2026-09-08), build_codex_args() in
# app.py beside the other two builders, and the codex arms in ws_chat's
# dispatch. So this membership is now backed by a transport rather than
# staging a hope.
#
# SIGN-IN IS STILL A DIFFERENT CAPABILITY. The Codex row's sign-in block (see
# the codex auth section below) answers "which credential is codex holding",
# which is `configured`, not `adapter`. Being in this set does not mean anyone
# is signed in, and being signed in never implied membership here.
ADAPTERS = frozenset({"claude", "codex", "deepseek"})

# ------------------------------------------------------------- catalog -----
# Order is precedence order for the "first runnable provider" fallback.
# `default` marks the one the panel ships pointed at.
#
# `models` / `model_flag` / `usage_kind` are DECLARATIONS, read through
# models_for() / model_flag_for() / usage_kind_for(). They live here so a new
# provider answers all three questions by being added to this tuple, instead of
# by someone remembering to extend a switch in the picker, another in the usage
# row, and a third in the spawn path.
#: Per-turn controls a provider can actually HONOUR. Claude's five map 1:1 onto
#: documented `claude` flags, validated in build_agent_args.
#:
#: DeepSeek declares NONE, and that is a measured answer rather than a gap.
#: Its transport is ACP, whose entire per-turn request is
#: `{sessionId, prompt[], messageId?, _meta?}` -- there is no options field to
#: carry any of this, `Session.prompt` reads only `params.prompt`, and the
#: agent implements no `extMethod`, so there is not even an extension route.
#: Probed on the wire against @sluisr/deepseek-cli@1.3.2, 2026-09-07:
#: session/set_config_option (ACP's generic per-session config surface, and the
#: one place a reasoning-effort knob could have lived) answers -32601.
#:
#: The individual controls, and why each is absent rather than pending:
#:
#:   effort              nothing to wire. `reasoningEffort` exists in the fork
#:                       as config, is only ever SET from the interactive TUI's
#:                       keyboard toggle, and never reaches the request body --
#:                       `body.reasoning_effort` is assigned nowhere in the
#:                       bundle and deleted in one place.
#:   budget              no flag, no method. ACP reports per-turn token counts
#:                       AFTER the fact and no dollar figure at all.
#:   append_system_prompt  no equivalent on either surface.
#:   disallowed_tools    no argv flag. Expressible only as a Policy Engine
#:                       .toml (decision = "deny") passed with --policy, which
#:                       REPLACES the operator's own policies directory when
#:                       non-empty -- so wiring it would silently drop their
#:                       rules. Deliberately not attempted.
#:   allowed_tools       DO NOT WIRE THIS TO --allowed-tools. It looks like
#:                       Claude's --allowedTools and does the OPPOSITE KIND of
#:                       thing: Gemini's flag feeds
#:                       mapToolsToRules(..., autoApprove=true)
#:                       (chunk-UNFT3LTQ.js:384568) and the CLI's own copy for
#:                       it reads "This project auto-approves certain tools".
#:                       It is a permission-prompt BYPASS, not a capability
#:                       whitelist. An operator typing "Read Bash" into a box
#:                       labelled "Allow only" is narrowing what the agent may
#:                       do; this flag would WIDEN it. A control that does the
#:                       reverse of what its label promises is worse than an
#:                       absent one, which is why this stays empty.
_CLAUDE_TURN_OPTIONS = ("effort", "max_budget_usd", "allowed_tools",
                        "disallowed_tools", "append_system_prompt")

#: Which of PERMISSION_MODES a provider can actually enforce.
#:
#: Claude's six are all of them -- this is the existing global list, declared
#: per provider rather than changed.
#:
#: DeepSeek's ACP layer offers four modes (default/autoEdit/yolo/plan) and
#: three of Sutra's six map onto them. `auto`, `manual` and `dontAsk` have no
#: equivalent and no near-miss, so they are not offered on a DeepSeek pane --
#: selecting one there ran `default` while the control kept displaying the
#: choice. AcpRuntime._apply_mode still states the divergence for a mode that
#: arrives anyway (a value stored while Claude was selected), because
#: permission_mode is stored GLOBALLY and this list cannot prevent that.
_CLAUDE_PERMISSION_MODES = PERMISSION_MODES
_DEEPSEEK_PERMISSION_MODES = ("plan", "acceptEdits", "bypassPermissions")

#: Codex's per-turn controls. ONE PROCESS PER TURN is what makes these
#: deliverable: the old declaration was () with the note "there is no running
#: session to change anything on", which is true of a persistent process and
#: backwards for `codex exec` -- every turn is a fresh spawn, so a spawn-time
#: `-c` IS a per-turn control.
#:
#: BOTH ARE ENFORCED BY CODEX ITSELF, not interpreted by Sutra, and both are
#: named by the CLI's own rejection of a bad value (see CODEX_REASONING_SUMMARY).
#: Nothing else is offered: `model_reasoning_effort` is real but publishes no
#: value list, and Claude's five have no codex equivalent.
#: `reasoning_effort` ADDED 2026-09-09, and it is a DIFFERENT AXIS from
#: `reasoning_summary` rather than a rename of it: summary is how much of its
#: reasoning codex SHOWS (auto/concise/detailed/none), effort is how much it
#: DOES (low/medium/high/xhigh/max/ultra). They share no values.
#:
#: It was deliberately left out when the other two shipped, because
#: `-c model_reasoning_effort` ACCEPTS an unknown value without complaint
#: (measured: "__bogus__" sailed through) and no enumeration was available, so
#: any list would have been guesses. model/list supplies one -- per model, and
#: the sets differ -- which is what made this implementable without inventing
#: anything. Its allow-list is therefore codex_efforts_for(model), not a
#: constant like the other two.
_CODEX_TURN_OPTIONS = ("reasoning_summary", "verbosity", "reasoning_effort")

_CATALOG = (
    {"id": "claude", "name": "Claude Code", "bin": "claude",
     "config_dir": "~/.claude", "default": True,
     "models": _CLAUDE_MODELS, "model_flag": "--model",
     "usage_kind": "window-percent",
     "turn_options": _CLAUDE_TURN_OPTIONS,
     "permission_modes": _CLAUDE_PERMISSION_MODES},
    # usage_kind "none" is still a DECLARATION, not a gap, now that codex has
    # an adapter. `turn.completed` carries {input_tokens, cached_input_tokens,
    # cache_write_input_tokens, output_tokens, reasoning_output_tokens} --
    # per-turn counts with NO dollar figure and no rate-limit window anywhere
    # in the payload (measured 0.153.2, 2026-09-08). Neither "window-percent"
    # nor "balance" is true of that, and declaring one would put Anthropic's
    # percentage on a Codex session. The counts still reach the client on the
    # `done` frame's `quota` field; they are just not a usage HEADLINE.
    #
    # turn_options () -- measured, like DeepSeek's. Every per-turn lever codex
    # has is spawn-time argv (model, sandbox, approval policy), and `codex
    # exec` is one process per turn, so there is no running session to change
    # anything on. Nothing to wire, rather than something not yet wired.
    {"id": "codex", "name": "OpenAI Codex", "bin": "codex",
     "config_dir": "~/.codex", "default": False,
     "models": _CODEX_MODELS, "model_flag": "-m",
     # "tokens", not "none" and emphatically not "window-percent" or
     # "balance". codex reports PER-TURN TOKEN COUNTS on turn.completed and
     # nothing else: no dollar figure, no rate-limit window, no plan
     # allowance. Those counts were already reaching the client on the `done`
     # frame's `quota` field and nothing rendered them. This declares what kind
     # of fact they are so the client can show them AS TOKENS -- the one thing
     # that is true -- rather than borrowing Anthropic's percentage or
     # DeepSeek's balance, which is what any of the other three values would
     # have done.
     "usage_kind": "tokens",
     "turn_options": _CODEX_TURN_OPTIONS,
     "permission_modes": _CODEX_PERMISSION_MODES},
    # Gemini CLI LEFT THE CATALOGUE 2026-09-16 (owner: "Sutra has no adapter
    # for it, so remove it everywhere it appears"). It had no adapter, no
    # models, no usage figure and no minimum version, so every screen that
    # listed it could only say "not installed" or "no adapter". `~/.gemini`
    # still appears elsewhere in this tree: that is the DeepSeek CLI, which is
    # a Gemini-CLI fork and keeps its state there. Unrelated to this entry.
    {"id": "deepseek", "name": "DeepSeek", "bin": "deepseek",
     "config_dir": "~/.deepseek", "default": False,
     "models": _DEEPSEEK_MODELS, "model_flag": "-m",
     "usage_kind": "balance",
     # None, measured. See _CLAUDE_TURN_OPTIONS above for each control and why.
     "turn_options": (),
     "permission_modes": _DEEPSEEK_PERMISSION_MODES},
)


#: EXTRA SPELLINGS an operator may reasonably type for a provider, beyond its
#: catalogue id and its display name (both of which provider_aliases() derives
#: automatically -- they are NOT repeated here).
#:
#: WHY THIS LIVES BESIDE _CATALOG. The panel detects an in-chat provider request
#: ("using Codex, ...") in the browser, because the provider is fixed when the
#: socket opens and the decision has to be made before that. The NAMES it
#: matches on must still come from here: a second copy in JS would drift the
#: day a provider is added or renamed, and the drift would be silent -- an
#: alias that no longer matches simply stops switching, with nothing to say so.
#: So the table ships to the client through _declarations_attr (app.py), the
#: same channel turn_options_by_provider already rides.
#:
#: DELIBERATELY SHORT, and model names are deliberately absent. "opus",
#: "sonnet" and "gpt" are not provider names: the first two are entries in
#: Claude's own model picker, so "use opus" is a MODEL request that this table
#: would silently answer with a PROVIDER switch. Adding them is a product
#: decision, not an oversight.
_PROVIDER_ALIAS_EXTRAS = {
    "claude": ("claude code",),
    "codex": ("openai codex",),
    "deepseek": ("deep seek",),
}


def provider_aliases():
    """{spelling: provider_id} for every catalogued provider, lowercased.

    Every id and every display name is included automatically, so a provider
    added to _CATALOG is matchable the moment it exists rather than when
    someone remembers this function.

    EVERY catalogued provider is listed, whether or not it is runnable right
    now: "use Codex" on a Mac with no Codex sign-in should be RECOGNISED and
    then refused with the reason, which is what the readiness gate already
    says. Whether a matched provider may actually be selected is decided by
    `runnable`, never here. A name that is not in the catalogue at all (Gemini,
    since 2026-09-16) is simply not matched.
    """
    out = {}
    for spec in _CATALOG:
        pid = spec["id"]
        out[pid.lower()] = pid
        name = (spec.get("name") or "").strip().lower()
        if name:
            out[name] = pid
        for extra in _PROVIDER_ALIAS_EXTRAS.get(pid, ()):
            out[extra] = pid
    return out


#: Claude Desktop's bundle. It is NOT the Claude Code CLI and ships no `claude`
#: binary -- verified by searching the installed bundle for any executable of
#: that name and finding none. Someone who installed Desktop has nothing Sutra
#: can drive, and telling them "binary not on PATH" sends them hunting for a
#: PATH problem that does not exist. Detected only so the panel can say which
#: product is missing.
_DESKTOP_APP_PATHS = (
    "/Applications/Claude.app",
    "~/Applications/Claude.app",
)


def claude_desktop_installed():
    return any(os.path.isdir(os.path.expanduser(p)) for p in _DESKTOP_APP_PATHS)


def _bin_for(pid, fallback):
    """Which binary to look for, in precedence order.

      1. SUTRA_UI_<ID>_BIN      env override; predates this module, and tests
                                rely on it, so it stays first and wins.
      2. settings provider_bins a path the operator set IN THE PANEL.
      3. the bare name           resolved through PATH.

    Step 2 is the one that matters for a stuck operator. The env var is a fine
    escape hatch for a terminal launch and a useless one for a .app opened from
    Finder: setting it means `launchctl setenv` plus a relaunch, it does not
    survive a reboot, and nothing in the UI hints at any of that. The panel was
    naming an escape hatch most of the people who needed it could not use.

    Reads the settings file DIRECTLY rather than through load_settings(),
    which calls active_provider_detail() -> discover_providers() -> here.
    Going through it would recurse forever on the first call.
    """
    env = os.environ.get("SUTRA_UI_%s_BIN" % pid.upper())
    if env:
        return env
    bins = _raw_settings().get("provider_bins")
    if isinstance(bins, dict):
        chosen = bins.get(pid)
        if isinstance(chosen, str) and chosen.strip():
            full = os.path.expanduser(chosen.strip())
            # A STORED PATH THAT NO LONGER EXISTS IS IGNORED, not honoured.
            # set_provider_bin validates at write time, so this only happens
            # afterwards -- and deepseek_install made it reachable: its tree
            # lives under ~/.sutra-ui and someone who clears that directory, or
            # deletes the install by hand, leaves the record behind. Returning
            # it anyway means which() answers None and the row says "not
            # installed" on a machine where the operator has since installed
            # the CLI globally and it is sitting on PATH. Falling through costs
            # one stat and cannot lose a working binary: if the stored path is
            # there, it still wins.
            if os.path.exists(full):
                return full
    return fallback


def set_provider_bin(pid, path):
    """Persist a hand-picked binary path, or clear it with a falsy path.

    Validated HERE rather than at render time: a path that is not an executable
    file cannot help, and storing it would replace "cannot find it" with
    "found it and it will not run", which is a worse error later and further
    from the mistake.
    """
    raw = _raw_settings()
    bins = dict(raw.get("provider_bins") or {})
    if path:
        full = os.path.expanduser(str(path).strip())
        if not os.path.isfile(full):
            raise ValueError("no file at %s" % full)
        if not os.access(full, os.X_OK):
            raise ValueError("%s is not executable" % full)
        bins[pid] = full
    else:
        bins.pop(pid, None)
    raw["provider_bins"] = bins
    _write_settings(raw)
    return bins.get(pid)


# ----------------------------------------------------------- codex auth ----
# Codex is the one provider whose BILLING MODE is invisible from the outside,
# and the two modes cost the operator completely different amounts for
# identical output: a ChatGPT sign-in draws on a plan they already pay for, an
# API key bills per token. Nothing in the panel showed which was in play.
#
# Codex stores EXACTLY ONE credential. Signing in with either method REPLACES
# the other -- there is no both-at-once state and no precedence to resolve --
# so this is one active mode plus a switch, never two independent toggles.
#
# THE CLI IS THE AUTHORITY. `codex login status` is ASKED rather than
# ~/.codex/auth.json being parsed: that file is a credential store, and this
# module reads config paths for EXISTENCE only, never contents (module
# docstring). The masked stub codex prints ("sk-proj-***SMnIA") is DISPLAYED
# and never stored -- Sutra holds no part of the key at any point, and there is
# deliberately no settings key for one.
#
# NOT CALLED FROM _describe(). _describe() runs four times per
# load_settings(), and every fs/tree, fs/read, ws_chat connect and settings GET
# goes through that; a subprocess there would tax requests that never asked
# about codex, and _bin_for() already had to dodge one recursion loop through
# the same chain. This mirrors how the Claude account is handled instead:
# claude_local.account() is a separate function the route calls and merges.
# Provider IDENTITY is not a field of provider AVAILABILITY.

#: Where codex keeps the one credential. Checked for existence, never opened.
CODEX_AUTH_PATH = "~/.codex/auth.json"

CODEX_STATUS_TIMEOUT = 10

#: The npm package the `codex exec --json` transport was measured against
#: (codex_runtime.py's docstring: "MEASURED against codex-cli 0.153.2 on
#: 2026-09-08"). Lives here for the same reason DEEPSEEK_CLI_PACKAGE does:
#: codex_install.py fetches it and the provider row may name it, and those two
#: must never be able to disagree about which package is meant.
#:
#: NAMING IT IS NOT AN INSTALL COMMAND. `npm install -g` is exactly what
#: codex_install.py refuses to do -- see its "--prefix, NOT -g" section.
CODEX_CLI_PACKAGE = "@openai/codex"

#: The one line `codex login status` answers with, verified against codex-cli
#: 0.153.2 on 2026-09-04:
#:
#:     Logged in using ChatGPT
#:     Logged in using an API key - sk-proj-***SMnIA
#:     Not logged in
#:
#: The API-key form is matched with the separator OPTIONAL and the stub
#: OPTIONAL: a build that stops printing the stub must still be recognised as
#: an API-key login, because losing the stub is cosmetic and losing the MODE
#: means telling the operator their tokens are free while they are being
#: billed. Hyphen, en-dash, em-dash and colon are all accepted as the
#: separator so a cosmetic change upstream cannot silently downgrade the state
#: to "unknown".
_CODEX_API_KEY_RE = re.compile(
    r"logged\s+in\s+using\s+an\s+api\s+key\s*(?:[-:\u2013\u2014]\s*(\S+))?", re.I)
_CODEX_CHATGPT_RE = re.compile(r"logged\s+in\s+using\s+chatgpt", re.I)
_CODEX_LOGGED_OUT_RE = re.compile(r"not\s+logged\s+in", re.I)

#: Plain English for each state, so the panel does not re-derive the billing
#: story and disagree with this module. The whole point of the row is that
#: these two cost different amounts.
#: REWORDED 2026-09-08. "usage included in your plan" was read as unlimited,
#: and "billed per token" implied Sutra knows a rate. Neither is knowable here:
#: codex publishes no plan allowance and no price (see usage_kind "tokens"), so
#: these say WHERE the usage lands and stop -- one short clause, no number.
#: The longer explanation lives in CODEX_BILLING_DETAIL below, which the
#: sign-in block renders under the row rather than inside this label.
CODEX_BILLING = {
    "chatgpt": "covered by your ChatGPT plan",
    "api_key": "billed to your OpenAI API account",
}

#: The sentence a normal user needs, for each credential. NO PRICES, NO LIMITS,
#: NO REMAINING QUOTA -- none of the three is obtainable from the CLI, and a
#: made-up figure here is worse than an absent one because it would be believed.
#: What each one DOES say is which account pays and that limits exist somewhere
#: the user can go and look.
CODEX_BILLING_DETAIL = {
    "chatgpt": ("Codex runs against your ChatGPT plan and draws on that plan's "
                "own Codex usage limits. Nothing here is billed per token. "
                "Sutra cannot see how much of the allowance is left -- codex "
                "does not report it -- so check your ChatGPT account for that."),
    "api_key": ("Codex runs against your OpenAI API account, so these turns are "
                "billed at OpenAI's API pricing and are NOT covered by a "
                "ChatGPT subscription. Sutra shows the tokens a turn used but "
                "not what they cost: codex reports no prices, and Sutra will "
                "not guess at them. Your OpenAI usage dashboard is the "
                "authority on spend."),
}


def _codex_credential_present():
    """True when codex is holding a credential -- ~/.codex/auth.json exists.

    EXISTENCE ONLY. The file is a credential store and nothing here opens it.
    """
    return Path(os.path.expanduser(CODEX_AUTH_PATH)).is_file()


def _parse_codex_status(text):
    """(state, key_display) for one `codex login status` answer.

    Matched on the TEXT, not the exit code. 0.153.2 exits 0 when logged in, and
    learning what it exits when logged OUT would mean destroying the operator's
    live session to find out -- so the exit code is used only for the coarse
    "did it run at all" signal in codex_auth(), never to decide a mode.

    Anything unrecognised is "unknown": asked, and could not tell. Guessing a
    mode here is the convincing-wrong answer this codebase refuses to produce,
    and the specific wrong answer would be "your usage is included" to someone
    paying per token.
    """
    blob = (text or "").strip()
    if not blob:
        return "unknown", ""
    m = _CODEX_API_KEY_RE.search(blob)
    if m:
        # rstrip: the stub is matched as one non-space run, so a build that ends
        # the line with punctuation would otherwise fold it into the key.
        return "api_key", (m.group(1) or "").rstrip(".,;:")
    if _CODEX_CHATGPT_RE.search(blob):
        return "chatgpt", ""
    if _CODEX_LOGGED_OUT_RE.search(blob):
        return "logged_out", ""
    return "unknown", ""


def codex_auth():
    """Which credential Codex is holding, and therefore how it bills.

        {"state":       chatgpt | api_key | logged_out | no_binary | unknown,
         "key_display": the masked stub codex printed, or "" -- DISPLAY ONLY,
         "billing":     one line of plain English, or None,
         "detail":      what happened, when the answer is not a login state,
         "bin_path":    the binary that was asked, or None,
         "checked_at_ms": when}

    NEVER RAISES. A probe that times out, cannot start, or answers in a shape
    this build does not know comes back as "unknown" WITH the reason. It must
    never fall back to a mode: the two modes bill differently, so a confident
    wrong answer here is worse than no answer.

    THE ENVIRONMENT DOES NOT CHANGE THE ANSWER while a credential file exists.
    Measured on 0.153.2 (2026-09-04): `OPENAI_API_KEY=sk-fake codex login
    status` still reports the ChatGPT sign-in, so ~/.codex/auth.json takes
    precedence over the variable. That is what makes _describe()'s cheap
    auth.json check agree with this probe rather than race it. Deliberately
    still unmeasured, and therefore not claimed either way: whether the
    variable authenticates ON ITS OWN when auth.json is absent entirely.

    The env is passed through UNCHANGED, unlike the desktop shell's login
    spawns which strip OPENAI_*/CODEX_*. This function reports what codex
    reports; sanitising the environment here would make the panel disagree with
    the same command run in a terminal, which is a worse failure than
    inheriting a variable on a read.
    """
    ensure_login_path()
    bin_path = provider_bin("codex")
    now = int(time.time() * 1000)
    if not bin_path:
        return {"state": "no_binary", "key_display": "", "billing": None,
                "billing_detail": None,
                "detail": "the `codex` CLI is not on PATH, so its sign-in "
                          "state cannot be read",
                "bin_path": None, "checked_at_ms": now}
    try:
        p = subprocess.run([bin_path, "login", "status"], capture_output=True,
                           text=True, timeout=CODEX_STATUS_TIMEOUT)
    except FileNotFoundError:
        # which() found it and exec did not: it moved between the two calls.
        return {"state": "no_binary", "key_display": "", "billing": None,
                "billing_detail": None,
                "detail": "%s could not be run -- it is no longer there"
                          % bin_path,
                "bin_path": bin_path, "checked_at_ms": now}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"state": "unknown", "key_display": "", "billing": None,
                "billing_detail": None,
                "detail": "`codex login status` did not finish (%s)"
                          % type(exc).__name__,
                "bin_path": bin_path, "checked_at_ms": now}

    # stderr is read only as a FALLBACK. 0.153.2 answers on stdout; a build
    # that moves the line should still be understood rather than reported as
    # an unknown mode.
    blob = (p.stdout or "").strip() or (p.stderr or "").strip()
    state, key_display = _parse_codex_status(blob)
    detail = None
    if state == "unknown":
        # DELIBERATELY NOT no_binary. The binary is right there and it ran --
        # saying it is not installed would send the operator after a PATH
        # problem that does not exist, which is the exact wrong diagnosis
        # test_provider_detect.py was written about. Unknown, with the exit
        # code, is the honest report.
        detail = ("`codex login status` answered in a shape this build does "
                  "not recognise (exit %s). Run it in a terminal to see what "
                  "it says." % p.returncode)
    return {"state": state, "key_display": key_display,
            "billing": CODEX_BILLING.get(state), "detail": detail,
            # The paragraph the short label cannot carry: which account pays,
            # and -- explicitly -- what Sutra does NOT know (price, allowance,
            # remaining quota). Sent as a sibling of `billing` so the row can
            # render one line and the block underneath the fuller sentence,
            # without either re-deriving the other.
            "billing_detail": CODEX_BILLING_DETAIL.get(state),
            "bin_path": bin_path, "checked_at_ms": now}


# -------------------------------------------------------- deepseek sign-in --
# DeepSeek is the inverse of Claude on billing: Claude inherits a logged-in Max
# subscription and app.py REFUSES a stray ANTHROPIC_API_KEY, while DeepSeek has
# no subscription path at all and every request is billed against a key. So a
# key is not a preference here -- it is half of whether the provider works, and
# it belongs in the same readiness answer as the binary.
#
# THE BUG THIS SECTION FIXES. `configured` for deepseek was `~/.deepseek`
# is_dir(), which is true after the CLI has run once and says nothing about a
# key. The row rendered "Ready to use", accepted the click, and then died at
# connect with "DEEPSEEK_API_KEY is not set in the server environment. Export it
# and restart the server." -- the offer-a-choice-that-cannot-run failure this
# module's docstring is about, and the one codex was pulled out of ADAPTERS for
# on 2026-09-04. Refusing at SELECTION time is the better error.
#
# ONE RESOLVER. app.py's ws_chat gate and deepseek_usage.py's balance fetch each
# called os.environ.get("DEEPSEEK_API_KEY") independently and neither knew about
# a saved key, so with a key in the keychain the balance card and the chat would
# have disagreed about whether DeepSeek was usable. Both now read
# deepseek_key_for_request().
#
# READ AT CALL TIME, never cached: signing in has to take effect on the next
# message, not the next restart.

#: Precedence, highest first. The Sutra-prefixed name matches the SUTRA_UI_<THING>
#: convention this file already uses (SUTRA_UI_PROVIDER, SUTRA_UI_SETTINGS,
#: SUTRA_UI_ALLOW_UNSAFE_PERM_MODES, and the SUTRA_UI_<ID>_BIN family in
#: _bin_for). The bare vendor name is SECOND and is not going away: it is what
#: app.py and deepseek_usage.py have always read and what operators already
#: export, and dropping it would sign out every machine that works today.
DEEPSEEK_KEY_ENVS = ("SUTRA_UI_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY")


def deepseek_env_var():
    """Which env var is supplying a DeepSeek key, or None.

    Returns the NAME only, never the value -- callers that want the value go
    through deepseek_api_key(), and the UI needs this to say which variable is
    winning so nobody saves a key that silently has no effect.
    """
    for var in DEEPSEEK_KEY_ENVS:
        raw = os.environ.get(var)
        if raw and raw.strip():
            return var
    return None


def _deepseek_key_present():
    """True when a key would resolve, WITHOUT reading one.

    Existence only, the same discipline _codex_credential_present() applies to
    auth.json. A stored key is attested by the NON-SECRET marker in
    settings.json rather than by a keychain read, because _describe() runs four
    times per load_settings() and every fs/tree, fs/read, ws_chat connect and
    settings GET goes through that -- a Security.framework round trip on that
    path would tax requests that never asked about DeepSeek, and _bin_for()
    already had to dodge one recursion loop through the same chain.

    The cost of trusting the marker is that a key deleted straight out of
    Keychain Access still reads as present here. That divergence is caught in
    deepseek_key_for_request(), which does read, and which drops the stale
    marker so the row corrects itself.
    """
    if deepseek_env_var():
        return True
    try:
        import deepseek_auth
        return bool(deepseek_auth.marker().get("mask"))
    except Exception:
        return False


def deepseek_api_key():
    """The key to authenticate DeepSeek with, or None. Never raises.

    Precedence: SUTRA_UI_DEEPSEEK_API_KEY, then DEEPSEEK_API_KEY, then the
    keychain. Prefer deepseek_key_for_request() on a request path -- it gives
    you the same key plus the sentence to show when there is not one.
    """
    for var in DEEPSEEK_KEY_ENVS:
        raw = os.environ.get(var)
        if raw and raw.strip():
            return raw.strip()
    try:
        import deepseek_auth
        return deepseek_auth.read()
    except Exception:
        return None


def deepseek_key_for_request():
    """(key, reason). THE call a request path makes.

    Exactly one of the two is set. `reason` is a sentence, not a code -- it is
    shown verbatim by the ws_chat refusal and the balance card, so both say the
    same thing about the same machine.

    This is where a marker/keychain divergence is caught: the marker says a key
    was saved, the keychain no longer holds it, and rather than reporting an
    unexplained failure the marker is DROPPED so the provider row flips back to
    not-signed-in on the next read.
    """
    key = deepseek_api_key()
    if key:
        return key, None
    try:
        import deepseek_auth
        stale = deepseek_auth.marker()
        if stale.get("mask"):
            deepseek_auth.forget_stale_marker()
            return None, (
                "a saved key was on record (%s) but the login keychain no longer "
                "holds it -- the item at service %r, account %r is gone or could "
                "not be read. That record has been cleared; sign in again to "
                "replace it."
                % (stale["mask"], deepseek_auth.KEYCHAIN_SERVICE,
                   deepseek_auth.KEYCHAIN_ACCOUNT))
    except Exception:
        pass
    # keychain_read=True: deepseek_api_key() above went through
    # deepseek_auth.read(), so this path has actually opened the keychain and
    # may say so. _describe()'s path has not -- see _deepseek_no_key_reason.
    return None, _deepseek_no_key_reason(keychain_read=True)


def _deepseek_no_key_reason(keychain_read=False):
    """The sentence for a machine with no DeepSeek key, naming all three places
    a key can come from and what was found at each.

    Concrete in the style of the missing-CLI row, which names what it searched
    ("the login shell's PATH and the usual install locations were both
    searched") rather than only what is missing. "no key is saved on this Mac" was the
    first draft and it was the same failure as the string it replaced: true,
    and no help to someone who wants to know WHERE a key would live.

    `keychain_read` is not cosmetic. Only deepseek_key_for_request() actually
    reads the keychain; _describe() decides from the settings marker, because a
    Security.framework round trip on the render path would tax every fs/tree
    and settings GET (see _deepseek_key_present). So the two call sites have
    observed different things and must not make the same claim -- asserting
    "the keychain holds no item" from a path that never opened it is exactly
    the "configured means the directory exists" mistake in a new coat.
    """
    try:
        import deepseek_auth
        available, why = deepseek_auth.store_status()
        service, account = (deepseek_auth.KEYCHAIN_SERVICE,
                            deepseek_auth.KEYCHAIN_ACCOUNT)
        settings_key = deepseek_auth.SETTINGS_KEY
    except Exception:                             # pragma: no cover - import guard
        available, why = False, "the credential store could not be loaded"
        service = account = settings_key = "?"

    if not available:
        # No point naming a keychain item on a machine that has no keychain --
        # and no second tail either: store_status()'s sentence already ends by
        # sending the operator to the environment, so appending the sign-in tail
        # produced "...in the environment instead.. So: set one of those
        # variables...". Its trailing stop is dropped rather than the sentence
        # rewritten, so the two callers of store_status() can keep one string.
        stored_clause = why.rstrip(".")
        tail = ""
    elif keychain_read:
        stored_clause = ("the login keychain holds no item at service %r, "
                         "account %r" % (service, account))
        tail = ("Sign in on the DeepSeek row, or set one of those variables "
                "before starting the server.")
    else:
        stored_clause = ("nothing is saved here -- settings.json carries no %r "
                         "record, which is what a saved key leaves behind (its "
                         "mask; the key itself goes to the login keychain at "
                         "service %r, account %r)"
                         % (settings_key, service, account))
        tail = ("Sign in on the DeepSeek row, or set one of those variables "
                "before starting the server.")

    return ("no API key. DeepSeek has no subscription to inherit -- every "
            "request is billed against a key -- and all three places it can "
            "come from were checked: %s is not set, %s is not set, and %s.%s"
            % (DEEPSEEK_KEY_ENVS[0], DEEPSEEK_KEY_ENVS[1], stored_clause,
               (" " + tail) if tail else ""))


def deepseek_auth_state():
    """Where a DeepSeek key comes from on this machine, and what the row should
    say. Reads no secret: the mask for a stored key comes from the settings
    marker, and the mask for an env key is computed from the value without
    keeping it.

    Cheap by construction -- settings read plus two env lookups -- which is why
    this can be merged into the settings response instead of needing its own
    probe route the way codex_auth() does (that one spawns `codex login
    status`, so _describe() must not call it).
    """
    var = deepseek_env_var()
    store_available, store_reason = True, None
    m = {}
    try:
        import deepseek_auth
        store_available, store_reason = deepseek_auth.store_status()
        m = deepseek_auth.marker()
        env_mask = deepseek_auth.mask(os.environ.get(var, "")) if var else None
    except Exception:
        env_mask = None

    # Whether a BROWSER can authorise a key write on this server, and why not
    # when it cannot. Three booleans and a fixed sentence -- deepseek_session
    # never puts the pairing code in here, which matters because this dict
    # rides in GET /api/settings, and that route is unauthenticated.
    try:
        import deepseek_session
        session = deepseek_session.state()
    except Exception:
        session = {"available": False, "claimed": False, "reason": None}

    if var:
        return {"state": "env", "signed_in": True, "env_var": var,
                "env_vars": list(DEEPSEEK_KEY_ENVS), "mask": env_mask,
                "saved_at": None, "stored_mask": m.get("mask"),
                "store_available": store_available, "store_reason": store_reason,
                "browser_session": session, "reason": None}
    if m.get("mask"):
        return {"state": "stored", "signed_in": True, "env_var": None,
                "env_vars": list(DEEPSEEK_KEY_ENVS), "mask": m["mask"],
                "saved_at": m.get("saved_at"), "stored_mask": m["mask"],
                "store_available": store_available, "store_reason": store_reason,
                "browser_session": session, "reason": None}
    return {"state": "none", "signed_in": False, "env_var": None,
            "env_vars": list(DEEPSEEK_KEY_ENVS), "mask": None,
            "saved_at": None, "stored_mask": None,
            "store_available": store_available, "store_reason": store_reason,
            "browser_session": session,
            "reason": _deepseek_no_key_reason()}


#: The npm package the ACP transport was read out of and verified against
#: (acp_runtime.py's docstring: "@sluisr/deepseek-cli@1.3.2, an unminified
#: esbuild bundle"). Named, not turned into an install command -- how it got
#: onto the machine is the operator's business and guessing wrong sends them
#: after the wrong fix.
DEEPSEEK_CLI_PACKAGE = "@sluisr/deepseek-cli"


def _deepseek_reason(binary, bin_path, installed, keyed):
    """Why DeepSeek is not runnable, or None. Two independent requirements --
    the CLI and the key -- so all three failing combinations are answered here
    rather than as three arms bolted into the generic ladder in _describe().

    `~/.deepseek` is deliberately absent from every string: it stopped being
    evidence of anything the moment the key became the configured signal, and
    sending someone to look for a directory that has no bearing on the failure
    is the mistake the codex signed-out message was rewritten to avoid.
    """
    if installed and keyed:
        return None
    if installed and not keyed:
        return "installed at %s, but %s" % (bin_path, _deepseek_no_key_reason())
    missing_cli = ("the %r CLI is not on PATH (%s, the package this build's ACP "
                   "transport was verified against). The login shell's PATH and "
                   "the usual install locations were both searched%s. Sutra "
                   "spawns `%s --acp` to talk to DeepSeek, so a key alone is not "
                   "enough. Set the full path in Settings below, or "
                   "SUTRA_UI_DEEPSEEK_BIN -- `which %s` in your terminal will say "
                   "where."
                   % (binary, DEEPSEEK_CLI_PACKAGE, _harvest_note(), binary,
                      binary))
    if keyed:
        return missing_cli
    return "%s And %s" % (missing_cli, _deepseek_no_key_reason())


def _describe(spec):
    """One provider's live state. `installed` is shutil.which() and NOTHING
    else -- a config directory is not evidence of a binary, and this function
    must never claim otherwise."""
    binary = _bin_for(spec["id"], spec["bin"])
    bin_path = shutil.which(binary)
    installed = bin_path is not None

    cfg_display = spec["config_dir"]
    cfg_path = Path(os.path.expanduser(cfg_display))
    configured = cfg_path.is_dir()
    if spec["id"] == "codex":
        # ~/.codex EXISTS after the first `codex` run whether or not anyone
        # ever signed in -- it holds config.toml, session logs and sqlite
        # state. Treating the directory as evidence of a login claimed codex
        # was set up on a machine that had never authenticated. The credential
        # is ONE FILE inside it, so that is what is checked.
        #
        # Still existence only, never contents. WHICH of the two billing modes
        # is active comes from codex_auth(), which asks the CLI -- and the two
        # agree rather than race, because auth.json takes precedence over
        # OPENAI_API_KEY (measured on 0.153.2; see codex_auth()).
        configured = _codex_credential_present()
    elif spec["id"] == "deepseek":
        # Same correction, same reasoning: ~/.deepseek exists after the CLI has
        # run once and says nothing about a key, and DeepSeek cannot answer a
        # single message without one. Existence only here too -- the key itself
        # is never read on this path (see _deepseek_key_present).
        configured = _deepseek_key_present()

    adapter = spec["id"] in ADAPTERS

    if installed and configured and adapter:
        reason = None
    elif spec["id"] == "deepseek":
        # ONE arm rather than three: for DeepSeek every not-runnable case is
        # about the CLI or the key, and neither is a config directory, so the
        # generic strings below would all name ~/.deepseek wrongly.
        reason = _deepseek_reason(binary, bin_path, installed, configured)
    elif installed and configured and not adapter:
        # This said "this panel drives Claude's stream-json protocol only",
        # which stopped being true when the DeepSeek ACP adapter landed:
        # DeepSeek renders as ready to use two rows away in the same list, so
        # the row contradicted the screen it was printed on. Corrected a second
        # time on 2026-09-08 for the same reason -- the count became three when
        # the Codex adapter landed, and the codex-specific version pin that
        # used to hang off this string went with it, because codex is now in
        # ADAPTERS and can no longer reach this arm at all. No catalogued
        # provider reaches it today (Gemini CLI, the last one that did, left
        # the catalogue 2026-09-16); it stays as the honest answer for any
        # future entry that ships before its adapter does.
        reason = ("no chat adapter yet -- this panel speaks three protocols, "
                  "Claude's stream-json, Codex's `exec --json` and DeepSeek's "
                  "ACP, and %s exposes none of them, so it cannot answer "
                  "messages here even though it is installed at %s"
                  % (spec["name"], bin_path))
    elif configured and not installed:
        # This is the message a user sees when the app cannot find a CLI they
        # know is installed. "not on PATH" alone sent people looking in the
        # wrong place -- name the escape hatch, because at this point PATH
        # repair and the known-location probe have BOTH already failed.
        if spec["id"] == "claude" and claude_desktop_installed():
            # The failure that reads as a Sutra bug and is not one. Claude
            # Desktop and Claude Code are different products; Desktop ships no
            # `claude` binary. Naming the right thing to install is the whole
            # fix for this case.
            reason = ("Claude Desktop is installed, but this panel needs the "
                      "Claude Code CLI -- a separate product that Desktop does "
                      "not include. Install it with `brew install --cask "
                      "claude-code`, or from claude.com/claude-code, then press "
                      "Check again. (Config was found at %s, which is why the "
                      "provider is listed at all.)" % cfg_display)
        else:
            reason = ("binary %r not on PATH (config found at %s). The login "
                      "shell's PATH and the usual install locations were both "
                      "searched%s. Set the full path in Settings below, or "
                      "SUTRA_UI_%s_BIN -- `which %s` in your terminal will say "
                      "where."
                      % (binary, cfg_display, _harvest_note(),
                         spec["id"].upper(), binary))
    elif installed and not configured:
        if spec["id"] == "codex":
            # The generic string below would be WRONG here in a new way: for a
            # signed-out codex the config directory is present, it is the
            # LOGIN that is missing, and sending someone to look for a missing
            # ~/.codex would waste the time the message was meant to save.
            reason = ("installed at %s, but nobody is signed in -- there is no "
                      "credential at %s. Sign in from the Codex row below. "
                      "(%s exists either way, so its presence is not evidence "
                      "of a login.)"
                      % (bin_path, CODEX_AUTH_PATH, cfg_display))
        else:
            reason = "binary %r found at %s but no config directory at %s" % (
                binary, bin_path, cfg_display)
    else:
        reason = "no binary and no config directory"

    return {
        "id": spec["id"],
        "name": spec["name"],
        "bin": binary,
        "installed": installed,
        "configured": configured,
        "config_dir": cfg_display,
        "reason": reason,
        "default": spec["default"],
        # extras -- not part of the required shape, but the UI would otherwise
        # have to re-derive them and could disagree with this module
        "adapter": adapter,
        "runnable": installed and configured and adapter,
        # A FLAG, not a sentence. The provider list stopped rendering `reason`
        # (05-chat.js provRow, founder 2026-09-07), and "Not installed on this
        # Mac" is the one status that is actively WRONG for the person who has
        # Claude Desktop and believes they installed Claude -- the field
        # incident named in the claude arm above. The UI needs to know that
        # this is that case; it does not need this module's prose to say it.
        "desktop_only": (spec["id"] == "claude" and not installed
                         and claude_desktop_installed()),
        "bin_path": bin_path,
        "config_path": str(cfg_path),
        # WHAT KIND of usage figure this provider has, so the client can look
        # it up per provider instead of branching on the id. The client held
        # `if (SETTINGS.provider === "deepseek") balance; else Anthropic
        # percentage` in four places; this is the fact those four branches were
        # each re-deriving, published once.
        "usage_kind": spec.get("usage_kind", "none"),
        # Declared so a reader can see WHY a provider has no picker (no flag to
        # carry a model) without opening this file.
        "model_flag": spec.get("model_flag"),
    }


def discover_providers():
    """Every catalogued provider, in precedence order, with live state."""
    return [_describe(spec) for spec in _CATALOG]


def provider_by_id(pid):
    """One provider's live state, or None if `pid` is not catalogued."""
    if not pid:
        return None
    for spec in _CATALOG:
        if spec["id"] == pid:
            return _describe(spec)
    return None


def runnable_providers():
    return [p for p in discover_providers() if p["runnable"]]


def provider_bin(pid):
    """Absolute path to the provider's binary, or None. Callers spawn this;
    None means do not spawn -- report the provider's `reason` instead."""
    p = provider_by_id(pid)
    return p["bin_path"] if p else None


# --------------------------------------------------------------- shadow ----
# Shadow (the chief-of-staff companion) ships dark: the flag defaults to OFF
# and this accessor is the ONLY sanctioned read path for it. Nothing Shadow-
# related may import, spawn, write, or render unless shadow_enabled() is True
# at the call site (lazy-load guard). Direct reads of the "shadow.enabled"
# settings key outside this function are a review failure (PLAN-100 S8).

def shadow_enabled(settings=None):
    """True unless settings.json carries "shadow.enabled": false (bool).

    Founder direction 2026-08-25: Shadow is ALWAYS ON by default. Only an
    explicit boolean false turns it off -- absent file, absent key, or junk
    values all mean ON. The off state still exists (this accessor is still
    the single read path, and everything downstream still honors it); it is
    simply opt-out now instead of opt-in.
    """
    s = settings if settings is not None else _raw_settings()
    return s.get("shadow.enabled") is not False


# ------------------------------------------------------------ settings io --

def _write_settings(raw):
    """Atomic, so a crash mid-write cannot leave a half-parsed preferences file
    that the next launch silently degrades to defaults.

    0600, set on the TEMP file before the replace so the contents are never
    briefly world-readable. No secret is kept here -- the DeepSeek marker is a
    mask, not a key (deepseek_auth's docstring) -- but this file also records
    the workdir the agent is pointed at and the permission mode it runs under,
    and neither is anyone else's business. mode=0o700 applies only when the
    directory is CREATED; an existing ~/.sutra-ui is left as the operator has
    it rather than silently re-permissioned underneath them.
    """
    SETTINGS_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(SETTINGS_PATH)


def _raw_settings():
    """The settings file as-is, or {} when absent/unreadable. Never raises --
    a corrupt preferences file must not take the panel down."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _clean_permission_mode(value):
    return value if value in PERMISSION_MODES else None


#: Which chats the rail lists.
#:
#:   "sutra" -- only chats this app started (bound to a sutra_id in
#:              chat_store's index). The default the owner chose on 2026-09-09:
#:              on a disk with 20,255 transcripts, one of them a Sutra chat,
#:              listing everything filled Sutra's own Chats folder with
#:              conversations from VS Code, terminals and every other tool
#:              writing to the same directory.
#:   "all"   -- every transcript on the machine, whichever provider wrote it.
#:              What an operator who uses Sutra as the one place to see their
#:              work wants, and the founder's own direction on 2026-09-13.
#:
#: It is a SETTING and not a hardcoded default because those two operators both
#: exist and neither is wrong. Measured cost of "all" on a 1,181-transcript
#: disk: 42 ms for the first page against 16 ms scoped -- the 3.5-5s figure in
#: api_sessions is a 20,255-transcript disk paying a title parse per row it
#: walked past, which is not what either path does now.
CHAT_SCOPES = ("sutra", "all")
DEFAULT_CHAT_SCOPE = "sutra"


def _clean_chat_scope(value):
    return value if value in CHAT_SCOPES else None


# -------------------------------------------------------------- active -----

def active_provider_detail():
    """Resolve the ACTIVE provider and say where the choice came from.

    Precedence, highest first:
      1. SUTRA_UI_PROVIDER   -- explicit operator intent for this process
      2. settings.json       -- the last thing chosen in the UI
      3. first runnable      -- catalog order (claude leads, and is `default`)
      4. None                -- nothing on this machine can run

    An override at (1) or (2) is honoured ONLY if it names a runnable
    provider. Handing back an id whose binary is absent would push the failure
    down into create_subprocess_exec, where it surfaces as a dead socket. When
    an override is dropped, `ignored` records what was asked for and why, so
    the UI can say so out loud rather than silently substituting.
    """
    ignored = []

    env_choice = os.environ.get("SUTRA_UI_PROVIDER")
    file_choice = _raw_settings().get("provider")

    for source, choice in (("env", env_choice), ("settings", file_choice)):
        if not choice:
            continue
        p = provider_by_id(choice)
        if p is None:
            ignored.append({"source": source, "id": choice,
                            "reason": "unknown provider id"})
            continue
        if not p["runnable"]:
            ignored.append({"source": source, "id": choice, "reason": p["reason"]})
            continue
        return {"id": p["id"], "source": source, "ignored": ignored}

    for p in discover_providers():
        if p["runnable"]:
            return {"id": p["id"], "source": "fallback", "ignored": ignored}

    return {"id": None, "source": "none", "ignored": ignored}


def active_provider():
    """The active provider id, or None when nothing on this machine is runnable."""
    return active_provider_detail()["id"]


def load_settings():
    """Effective settings: file values where valid, documented defaults
    otherwise. Always returns all three contract keys (provider,
    permission_mode, workdir) plus metadata explaining how each was reached.

    permission_mode defaults to DEFAULT_PERMISSION_MODE -- `bypassPermissions`
    (Full access) since founder direction 2026-09-18, `plan` before it.
    SUTRA_UI_PERMISSION_MODE still supplies the default when no valid value is
    stored, so existing deployments keep their behaviour.

    THREE OUTCOMES, not two, because "never chose" and "chose something
    unreadable" must not resolve the same way once the default is the widest
    mode rather than the narrowest:

        key absent          -> DEFAULT_PERMISSION_MODE   (Full access)
        key present, valid  -> that value
        key present, junk   -> PERMISSION_MODE_FLOOR     (`plan`)
    """
    raw = _raw_settings()
    invalid = {}

    stored_mode = raw.get("permission_mode")
    mode = _clean_permission_mode(stored_mode)
    # PRESENT-BUT-UNREADABLE IS NOT "NEVER CHOSE", and since the default became
    # Full access (2026-09-18) the difference decides which way the resolution
    # falls. A hand-edited or older-build settings.json that says `telepathy`
    # must not RAISE the ceiling by being wrong, so junk lands on
    # PERMISSION_MODE_FLOOR; only a genuinely absent key takes the default.
    # These were one branch while the default WAS the floor.
    mode_invalid = stored_mode is not None and mode is None
    if mode_invalid:
        invalid["permission_mode"] = stored_mode
    # AN INHERITED FLOOR IS NOT A CHOICE EITHER -- see ACCESS_CHOSEN_KEY. A
    # `plan` with no stamp beside it was written by the pre-2026-09-18 default
    # rather than picked, so it resolves the way an absent key does. Everything
    # else on file stands, and SUTRA_UI_PERMISSION_MODE still wins below.
    mode_inherited = (mode == PERMISSION_MODE_FLOOR
                      and not raw.get(ACCESS_CHOSEN_KEY))
    if mode_inherited:
        mode = None
    if mode is None:
        # The env var stays ahead of both: setting it is a deliberate operator
        # act, and it is the documented escape hatch.
        mode = _clean_permission_mode(
            os.environ.get("SUTRA_UI_PERMISSION_MODE")) or (
                PERMISSION_MODE_FLOOR if mode_invalid else DEFAULT_PERMISSION_MODE)

    scope = _clean_chat_scope(raw.get("chat_scope"))
    if raw.get("chat_scope") is not None and scope is None:
        invalid["chat_scope"] = raw.get("chat_scope")
    if scope is None:
        scope = DEFAULT_CHAT_SCOPE

    workdir = raw.get("workdir")
    workdir_source = "stored"
    if not isinstance(workdir, str) or not workdir.strip():
        if workdir is not None:
            invalid["workdir"] = workdir
        env_wd = os.environ.get("SUTRA_UI_WORKDIR")
        if env_wd:
            workdir, workdir_source = env_wd, "env"
        else:
            # Before falling back to ~/sutra-ui-workspace -- a directory nobody
            # works in and nothing else creates -- ask Claude where this
            # operator actually last worked. Sutra runs on top of Claude Code,
            # so on a fresh install that answer already exists and is far more
            # useful than a synthetic empty folder.
            #
            # Only ever a DEFAULT: a stored value and SUTRA_UI_WORKDIR both win,
            # and the path is filtered through workdir_allowed() inside
            # recent_workspace() because it becomes the agent's cwd.
            recent = None
            try:
                import claude_local
                recent = claude_local.recent_workspace(workdir_allowed)
            except Exception:
                recent = None
            workdir = recent or DEFAULT_WORKDIR
            workdir_source = "claude_recent" if recent else "default"
    workdir = os.path.expanduser(workdir)

    detail = active_provider_detail()
    stored = raw.get("provider")
    if stored and provider_by_id(stored) is None:
        invalid["provider"] = stored

    # The mode that will ACTUALLY reach the subprocess spawn. `permission_mode`
    # above is what is stored/requested; the two diverge whenever an unsafe mode
    # is on file without the out-of-band opt-in. Reporting only the stored value
    # let the panel state "nothing will prompt you per edit" while ws_chat was
    # in fact spawning `plan` -- the UI asserted authority the agent did not
    # have. Both values ship, and the UI renders the effective one.
    effective = effective_permission_mode(mode)
    clamped = effective != mode

    # First run is a PROPERTY OF THE SETTINGS FILE, not a browser flag: the
    # onboarding explains what this panel will do with the operator's machine
    # (which CLI it drives, where it writes, what authority the agent gets), so
    # clearing localStorage or opening it in another browser must not skip it.
    onboarded = raw.get("onboarded") is True

    return {
        "provider": detail["id"],
        "permission_mode": mode,
        "workdir": workdir,
        "onboarded": onboarded,
        # Which chats the rail lists -- see CHAT_SCOPES.
        "chat_scope": scope,
        # "" is a real, meaningful value here ("use the CLI's default"), so it is
        # reported as "" rather than folded into null.
        #
        # LEGACY ACCESSOR onto the claude slot, not a second store. Storage is
        # `model_by_provider` below; this key is what existed when there was one
        # shared model, it only ever described Claude, and it keeps working for
        # anything still reading it. One storage, one compat reader -- not two
        # sources that can disagree.
        "model": stored_model("claude") or "",
        # The real thing: every provider's own choice, so switching provider and
        # back does not discard it and no provider can be handed another's id.
        # Only providers that declare models appear.
        "model_by_provider": {spec["id"]: (stored_model(spec["id"]) or "")
                              for spec in _CATALOG if spec.get("models")},
        # metadata -- the three keys above are the contract; these explain them
        "workdir_source": workdir_source,
        "provider_source": detail["source"],
        "provider_stored": stored,
        "provider_ignored": detail["ignored"],
        "permission_mode_note": PERMISSION_MODE_NOTES.get(mode),
        # THE SAME MODE, IN THE NEW VOCABULARY. Not a second setting: `access`
        # is derived from `permission_mode` above every time it is read, so the
        # two can never disagree and nothing new is stored. None means the
        # stored mode is one of the advanced ones (`manual`, `dontAsk`), which
        # the four-button list does not cover -- the screen then shows the
        # Advanced disclosure instead of guessing a button.
        #
        # Resolved against the ACTIVE provider, because the mapping is
        # per-provider: `auto` is a Claude-only option.
        "access": access_for_native(mode, detail["id"]),
        "access_effective": access_for_native(effective, detail["id"]),
        "access_advanced": mode in advanced_permission_modes(),
        # The per-provider switches, NON-DEFAULT VALUES ONLY. {} on a machine
        # that has never touched the screen. The defaults live in
        # provider_settings_schema(), which the same response carries, so this
        # never restates them.
        "provider_settings": stored_provider_settings(raw),
        # effective-vs-stored: what runs, whether it was clamped, and how to unlock
        "permission_mode_effective": effective,
        "permission_mode_effective_note": PERMISSION_MODE_NOTES.get(effective),
        "permission_mode_clamped": clamped,
        "permission_mode_clamp_reason": (
            "%r auto-approves agent actions, so it is not honoured unless the "
            "server was started with %s=1. The session runs as %r instead."
            % (mode, UNSAFE_MODES_ENV, effective)) if clamped else None,
        "unsafe_modes_allowed": unsafe_modes_allowed(),
        "unsafe_modes_env": UNSAFE_MODES_ENV,
        # The root a workdir must sit under. Surfaced so the picker can state the
        # constraint UP FRONT rather than letting the operator type a path and
        # discover the rule from a 400.
        "workdir_root": os.path.realpath(os.path.expanduser(
            os.environ.get("SUTRA_UI_WORKDIR_ROOT", "~"))),
        # Feature flags, verbatim booleans from the file. The panel's rail
        # gates screens on these (wsFlagOn reads SETTINGS.flags); the backend
        # reads the raw file directly (workspace_api._flag_on). Omitting them
        # here made the two disagree: the API answered while the rail row
        # never rendered. Sanitized to {name: bool} -- anything non-dict or
        # non-boolean-true is OFF, matching FLAG.md's "absent means OFF".
        # Booleans pass through BOTH ways since S92: absent means ON for
        # cutover flags, so an explicit false must survive sanitization to
        # remain expressible. Junk still dies here.
        "flags": {k: v for k, v in (raw.get("flags") or {}).items()
                  if isinstance(v, bool)} if isinstance(raw.get("flags"), dict) else {},
        # The DeepSeek row's sign-in state. INSIDE the settings contract, not
        # a sibling of it in the route's response: the panel does
        # `SETTINGS = r.settings` (07-loaders.js), so a top-level sibling would
        # be read by nothing -- which is exactly the bug this line replaces.
        # Living here also means the three responses that already carry
        # load_settings() (GET /settings, POST /providers/active, and the
        # deepseek key verbs) get it without any of them being told to.
        #
        # Cheap enough for a per-request call: a settings read plus two env
        # lookups, no subprocess and no keychain. Carries a MASK, never a key.
        "deepseek_auth": deepseek_auth_state(),
        "settings_path": str(SETTINGS_PATH),
        "settings_file_exists": SETTINGS_PATH.exists(),
        "invalid_stored_values": invalid,
    }


#: What a caller must send to record the acknowledgement. Not a boolean: the
#: local socket is unauthenticated, so anything that can reach the port could
#: flip a plain `true`. Requiring the phrase makes enabling it an act of
#: intent that a stray or hostile POST does not perform by accident.
UNSAFE_ACK_PHRASE = "I understand the agent will write files without asking"


def save_settings(provider=None, permission_mode=None, workdir=None, onboarded=None,
                  model=None, unsafe_ack=None, model_provider=None,
                  chat_scope=None, access=None, access_provider=None, chosen=True):
    """Merge a partial update into the settings file and return load_settings().

    Validates BEFORE writing: an unknown or unrunnable provider, or an unknown
    permission_mode, raises ValueError carrying the specific reason. Written
    tmp+replace so a crash mid-write cannot leave a truncated file.

    `chosen` says whether naming a mode was an OPERATOR'S PICK. It is the
    difference between "the founder chose Read only" and "something re-sent the
    value that was already on screen", which the file alone cannot tell apart --
    and telling them apart is the whole job of ACCESS_CHOSEN_KEY. It defaults to
    True for direct library callers (naming a mode in Python IS the deliberate
    act) and the HTTP route defaults it to False, because an unattributed POST
    is exactly the write that pinned Read only on the owner's machine on
    2026-09-19 with nobody able to say who sent it.

    `access` is the NEW vocabulary and the OLD storage: it is translated to a
    native mode here and written to `permission_mode`, so nothing downstream --
    the spawn path, an older build, a routine -- learns a new word. It is
    mutually exclusive with `permission_mode`: sending both would be two
    answers to one question, and silently preferring one of them is how a
    screen ends up displaying a mode that is not what ran.
    """
    raw = _raw_settings()

    # RESOLVED FIRST, so everything below sees one value. The translation
    # happens here rather than in the route because the consent gate, the
    # per-provider support check and the write all live here, and splitting
    # them would leave the route re-implementing two of the three.
    if access is not None:
        if permission_mode is not None:
            raise ValueError(
                "send either access or permission_mode, not both -- they set "
                "the same thing and there is no rule for which wins")
        target = access_provider or provider or raw.get("provider") \
            or active_provider() or "claude"
        if not any(o["id"] == access for o in ACCESS_OPTIONS):
            raise ValueError(
                "unknown access %r -- must be one of: %s"
                % (access, ", ".join(o["id"] for o in ACCESS_OPTIONS)))
        native = access_native(access, target)
        if native is None:
            offered = access_by_provider().get(target) or []
            raise ValueError(
                "%s does not offer %r -- it offers: %s"
                % (target, access, ", ".join(offered) or "none"))
        permission_mode = native

    # Handled FIRST, so a single request can grant consent and select the mode
    # it unlocks -- otherwise the UI would have to make two round trips and
    # could leave consent recorded with nothing set.
    if unsafe_ack is not None:
        if unsafe_ack is False:
            raw[UNSAFE_ACK_KEY] = False        # withdrawing needs no phrase
        elif unsafe_ack != UNSAFE_ACK_PHRASE:
            raise ValueError(
                "to enable the write-capable modes, send unsafe_ack set to the "
                "exact phrase %r. A boolean is not accepted: this port is "
                "unauthenticated, so enabling must be a deliberate act."
                % UNSAFE_ACK_PHRASE)
        else:
            raw[UNSAFE_ACK_KEY] = True

    if provider is not None:
        p = provider_by_id(provider)
        if p is None:
            raise ValueError(
                "unknown provider %r -- known ids: %s"
                % (provider, ", ".join(s["id"] for s in _CATALOG)))
        if not p["runnable"]:
            raise ValueError("provider %r is not runnable: %s" % (provider, p["reason"]))
        raw["provider"] = p["id"]

    if permission_mode is not None:
        if permission_mode not in PERMISSION_MODES:
            raise ValueError(
                "unknown permission_mode %r -- must be one of: %s"
                % (permission_mode, ", ".join(PERMISSION_MODES)))
        # `raw` is passed so consent granted in THIS request counts -- reading
        # the file again here would miss it and refuse the mode it just unlocked.
        if permission_mode in UNSAFE_PERMISSION_MODES and not unsafe_modes_allowed(raw):
            raise ValueError(
                "permission_mode %r auto-approves agent actions. Confirm it in "
                "Settings first (or start the server with %s=1)."
                % (permission_mode, UNSAFE_MODES_ENV))
        previous = raw.get("permission_mode")
        raw["permission_mode"] = permission_mode
        # STAMPED HERE AND ONLY HERE, AND ONLY WHEN THE CALLER CLAIMS THE PICK.
        # Naming a mode is not by itself a choice -- an echo of the value already
        # on screen names one too, and a write of that shape pinned Read only on
        # the owner's machine (2026-09-19 10:58:53) with no caller identifiable
        # afterwards. Only `chosen` separates the two, and only the controls that
        # a human actually clicks send it.
        if chosen:
            raw[ACCESS_CHOSEN_KEY] = True
        elif permission_mode != previous:
            # AN UNCLAIMED WRITE THAT MOVES THE MODE INVALIDATES THE OLD CLAIM.
            # The stamp describes the value beneath it, not the key: leaving it
            # behind would let an unattributed write inherit a pick made for a
            # mode that is no longer stored. An unclaimed write that names the
            # SAME mode changes nothing and leaves the stamp alone.
            raw.pop(ACCESS_CHOSEN_KEY, None)

    if workdir is not None:
        if not isinstance(workdir, str) or not workdir.strip():
            raise ValueError("workdir must be a non-empty path string")
        expanded = os.path.expanduser(workdir.strip())
        if not workdir_allowed(expanded):
            raise ValueError(
                "workdir %r is outside the allowed root. Set SUTRA_UI_WORKDIR_ROOT "
                "when starting the server to widen it." % expanded)
        raw["workdir"] = expanded

    if onboarded is not None:
        if not isinstance(onboarded, bool):
            raise ValueError("onboarded must be a boolean")
        raw["onboarded"] = onboarded

    if chat_scope is not None:
        if _clean_chat_scope(chat_scope) is None:
            raise ValueError("chat_scope must be one of %s, not %r"
                             % (", ".join(CHAT_SCOPES), chat_scope))
        raw["chat_scope"] = chat_scope

    # `model` without a provider still means CLAUDE -- that is what the key
    # meant for its whole life, and callers that predate per-provider models
    # are not silently retargeted at whichever provider happens to be active.
    # `model_provider` names the slot explicitly.
    if model is not None:
        target = model_provider or "claude"
        if not models_for(target):
            raise ValueError(
                "provider %r declares no models, so none can be stored for it"
                % (target,))
        # "" is legal: it means "let the CLI choose", which is why this cannot use
        # the truthiness of clean_model() alone.
        allowed = selectable_model_ids_for(target)
        if not isinstance(model, str) or (model.strip() and model.strip() not in allowed):
            listed = model_ids_for(target)
            # Name the disabled case specifically. "unknown model" is wrong and
            # unhelpful for an id that IS catalogued and cannot be run -- the
            # operator would go looking for a typo that is not there.
            if isinstance(model, str) and model.strip() in listed:
                # The union, not models_for() alone: `listed` is model_ids_for(),
                # which now spans the catalogue, so searching only the flat list
                # here would raise StopIteration on a catalogue-only entry and
                # turn a clear refusal into a 500.
                entry = next(m for m in (tuple(models_for(target))
                                         + _catalog_extra_entries(target))
                             if m["id"] == model.strip())
                raise ValueError(
                    "model %r is listed for %s but cannot be selected: %s"
                    % (model, target, entry.get("unavailable_reason",
                                                "not available in this build")))
            raise ValueError(
                "unknown model %r for provider %r -- must be one of: %s "
                "(or \"\" for the CLI default)"
                % (model, target, ", ".join(sorted(i for i in allowed if i))))
        by_provider = dict(raw.get("model_by_provider") or {})
        by_provider[target] = model.strip()
        raw["model_by_provider"] = by_provider
        # The legacy scalar is kept in step for the claude slot ONLY, so an
        # older build (or anything still reading settings.json by hand) does
        # not see Claude's model silently revert. Never written for another
        # provider -- that would put a DeepSeek id where a Claude id is
        # expected, which is the failure this whole change removes.
        if target == "claude":
            raw["model"] = model.strip()

    _write_settings(raw)
    return load_settings()


# ================================================= tool versions & updates ==
# WHICH BUILD OF EACH CLI IS ON THIS MAC, whether a newer one exists, and -- for
# the installs Sutra is allowed to touch -- a button that fetches it.
#
# FOUR RULES SHAPE ALL OF IT:
#
# 1. TOO OLD IS A WARNING, NEVER A REFUSAL. The minimum version is the build the
#    adapter was measured against. Running an older one is a reason to say
#    "some of this may not work and here is how to fix it", not a reason to take
#    the provider away. Sutra has no way to know that an older build is actually
#    broken, and refusing on a number it did not measure would be inventing a
#    failure.
#
# 2. HOMEBREW IS NEVER TOUCHED. A `brew install` is a package manager's
#    property: replacing its binary, or shadowing it with a copy of our own,
#    leaves the operator with two installs and a `brew upgrade` that undoes
#    whatever we did. Those rows report "update it yourself" with the command to
#    run, and the update route refuses them outright.
#
# 3. EVERY NETWORK CALL IS TIME-BOXED AND FAILS SOFT. An offline Mac gets a row
#    with `latest_version: null` and a note, not a spinner and not an error.
#
# 4. NOTHING IS UPDATED WHILE A CHAT IS RUNNING ON IT. See the chat register
#    below.

#: The build each adapter was MEASURED against, from the shared spec. Not a
#: floor the code enforces -- see rule 1 -- but the number the warning quotes.
PROVIDER_MIN_VERSIONS = {
    "claude": "2.1.247",
    "codex": "0.144.4",
    "deepseek": "1.3.2",
}

#: The npm package each CLI is published as. Claude's is listed so `npm view`
#: can report the latest release even though Claude's own installer, not npm, is
#: what updates it on this Mac.
PROVIDER_NPM_PACKAGE = {
    "claude": "@anthropic-ai/claude-code",
    "codex": CODEX_CLI_PACKAGE,
    "deepseek": DEEPSEEK_CLI_PACKAGE,
}

#: `<cli> --version` prints one line and exits. Generous against a cold
#: filesystem and a Gatekeeper first-run check (codex_install.VERIFY_TIMEOUT is
#: 60 for the same reason), not against a human.
TOOL_VERSION_TIMEOUT = 20

#: `npm view <pkg> version` is one registry round trip. Short: this rides on a
#: screen load, and a slow registry must degrade to "unknown", never to a hang.
TOOL_LATEST_TIMEOUT = 12

#: An update is a download and an unpack, so it gets the install timeout the
#: install modules already use.
TOOL_UPDATE_TIMEOUT = 300

#: How long an answer is reused. The installed version changes only when
#: something installs, so it is keyed on the binary's (path, mtime, size) as
#: well -- an update is visible immediately, and an untouched binary is never
#: re-spawned for. The registry answer has no such key, so it is time-only.
TOOL_VERSION_TTL = 300.0
TOOL_LATEST_TTL = 900.0

_TOOL_CACHE_LOCK = threading.Lock()
_INSTALLED_VERSION_CACHE = {}      # bin key -> (at, version)
_LATEST_VERSION_CACHE = {}         # package -> (at, version)

#: The first version-looking token in a `--version` line. Deliberately loose:
#: `2.1.270 (Claude Code)`, `codex-cli 0.154.0` and a bare `1.3.2` all parse,
#: and anything else yields None rather than a wrong number.
_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]([0-9A-Za-z.\-]+))?")


def invalidate_tool_caches():
    """Forget every cached version answer.

    Called after an update -- the whole point of the (path, mtime, size) key is
    that a NEW file is a new key, but the registry answer has no such key and
    would otherwise keep reporting the version that was latest before. Tests use
    it for the same reason.
    """
    with _TOOL_CACHE_LOCK:
        _INSTALLED_VERSION_CACHE.clear()
        _LATEST_VERSION_CACHE.clear()


#: Kept as the name the rest of this package uses for a test reset hook
#: (codex_models._reset_for_tests, _reset_plan_for_tests).
_reset_tool_caches_for_tests = invalidate_tool_caches


def parse_version(text):
    """The version string inside `text`, or None. Never raises."""
    m = _VERSION_RE.search(text or "")
    if not m:
        return None
    core = ".".join(p for p in m.group(1, 2, 3) if p)
    return "%s-%s" % (core, m.group(4)) if m.group(4) else core


def version_tuple(value):
    """A comparable tuple for `value`, or () when it is not a version.

    A pre-release suffix sorts BELOW the same release (2.0.0-rc1 < 2.0.0), which
    is the only property the comparison here needs and the one a naive split
    gets backwards.
    """
    if not isinstance(value, str):
        return ()
    m = _VERSION_RE.search(value)
    if not m:
        return ()
    nums = tuple(int(p) for p in m.group(1, 2, 3) if p)
    nums = nums + (0,) * (3 - len(nums))
    return nums + ((0, m.group(4)) if m.group(4) else (1, ""))


def version_at_least(have, want):
    """True when `have` >= `want`. False when either cannot be parsed, so an
    unreadable version is reported as "cannot confirm", never as "fine"."""
    a, b = version_tuple(have), version_tuple(want)
    return bool(a) and bool(b) and a >= b


def installed_version(pid, bin_path=None):
    """What `<cli> --version` prints, or None. Never raises, never spawns twice.

    Cached on the binary's identity (path, mtime, size) as well as on time, so
    an update is reflected on the very next read while an untouched binary costs
    nothing.
    """
    path = bin_path or provider_bin(pid)
    if not path:
        return None
    try:
        st = os.stat(path)
        key = (str(path), st.st_mtime, st.st_size)
    except OSError:
        return None
    now = time.time()
    with _TOOL_CACHE_LOCK:
        hit = _INSTALLED_VERSION_CACHE.get(key)
        if hit and (now - hit[0]) < TOOL_VERSION_TTL:
            return hit[1]
    ensure_login_path()
    ensure_bundled_node_path()
    try:
        p = subprocess.run([str(path), "--version"], capture_output=True,
                           text=True, timeout=TOOL_VERSION_TIMEOUT,
                           stdin=subprocess.DEVNULL)
        blob = (p.stdout or "").strip() or (p.stderr or "").strip()
        found = parse_version(blob)
    except (OSError, subprocess.SubprocessError):
        found = None
    with _TOOL_CACHE_LOCK:
        if len(_INSTALLED_VERSION_CACHE) > 32:
            _INSTALLED_VERSION_CACHE.clear()
        _INSTALLED_VERSION_CACHE[key] = (now, found)
    return found


def _npm_bin():
    """npm, through the same resolver the install modules use.

    Deferred import: codex_install imports THIS module, so a top-level import
    would be a cycle. Its npm_path() also puts the bundled Node on PATH, which
    is what makes `npm` runnable inside the packaged .app at all.
    """
    try:
        import codex_install
        return codex_install.npm_path()
    except Exception:
        return shutil.which("npm")


def npm_latest(package):
    """`npm view <package> version`, or None. Never raises, time-boxed.

    None is the OFFLINE answer as well as the no-npm answer, and the caller
    renders both as "could not check" -- which is the truth in each case and is
    why they do not need telling apart here.
    """
    if not package:
        return None
    now = time.time()
    with _TOOL_CACHE_LOCK:
        hit = _LATEST_VERSION_CACHE.get(package)
        if hit and (now - hit[0]) < TOOL_LATEST_TTL:
            return hit[1]
    npm = _npm_bin()
    found = None
    if npm:
        try:
            p = subprocess.run([str(npm), "view", package, "version",
                                "--no-audit", "--no-fund", "--loglevel=error"],
                               capture_output=True, text=True,
                               timeout=TOOL_LATEST_TIMEOUT,
                               stdin=subprocess.DEVNULL)
            if p.returncode == 0:
                found = parse_version(p.stdout)
        except (OSError, subprocess.SubprocessError):
            found = None
    with _TOOL_CACHE_LOCK:
        _LATEST_VERSION_CACHE[package] = (now, found)
    return found


#: Path fragments that mean Homebrew owns this file. `/Cellar/` is the reliable
#: one -- every brew formula lands there and `brew --prefix/bin/<x>` is a
#: symlink into it, which realpath() follows -- and the two prefixes cover a
#: cask or a keg that is not symlinked.
_BREW_MARKERS = ("/cellar/", "/opt/homebrew/", "/usr/local/homebrew/",
                 "/home/linuxbrew/")


def _install_kind(pid, bin_path):
    """WHO owns this binary, which decides whether Sutra may replace it.

        sutra        installed into Sutra's own provider prefix by codex_install
                     or deepseek_install. Ours to update.
        claude-self  Claude Code's own native install (~/.local/share/claude/
                     versions/...). `claude update` is its supported updater, so
                     it is ours to trigger, not ours to overwrite.
        homebrew     brew's. NEVER touched -- see rule 2.
        npm-global   somebody's own `npm install -g`. Not ours either: replacing
                     it would fight their npm, and shadowing it would leave two.
        other        anything else, including a SUTRA_UI_<ID>_BIN override.
    """
    if not bin_path:
        return None
    real = os.path.realpath(str(bin_path)).lower()
    if any(marker in real for marker in _BREW_MARKERS):
        return "homebrew"
    for mod_name, want in (("codex_install", "codex"),
                           ("deepseek_install", "deepseek")):
        if pid != want:
            continue
        try:
            mod = __import__(mod_name)
            if os.path.realpath(str(mod.managed_bin())).lower() == real:
                return "sutra"
        except Exception:
            pass
    if pid == "claude" and "/share/claude/versions/" in real:
        return "claude-self"
    if pid == "claude" and "/.claude/local/" in real:
        return "claude-self"
    if "/node_modules/" in real or "/lib/node_modules/" in real:
        return "npm-global"
    return "other"


# ------------------------------------------------------------ chat register --
# WHICH PROVIDERS HAVE A LIVE CHAT RIGHT NOW, so an update cannot pull a binary
# out from under a running turn.
#
# A COUNTER, not a boolean: several panes can be open on one provider, and a
# boolean would be cleared by the first of them to finish while the others were
# still streaming.
#
# THE SPAWN PATH HAS TO CALL THIS. ws_chat lives in app.py, which this
# workstream does not own, so the register ships here with `chat_lease()` ready
# to wrap the connection and the wiring is handed to the integrator. Until that
# one line exists the count is always zero and the update route's refusal is
# inert -- stated plainly rather than left to be discovered.
_CHAT_LOCK = threading.Lock()
_CHATS_RUNNING = {}


def chat_started(pid):
    """Record that a chat has opened on `pid`. Returns the new count."""
    with _CHAT_LOCK:
        _CHATS_RUNNING[pid] = _CHATS_RUNNING.get(pid, 0) + 1
        return _CHATS_RUNNING[pid]


def chat_finished(pid):
    """Record that a chat on `pid` has ended. Never goes below zero: a double
    release must not make a live chat look idle."""
    with _CHAT_LOCK:
        n = max(_CHATS_RUNNING.get(pid, 0) - 1, 0)
        if n:
            _CHATS_RUNNING[pid] = n
        else:
            _CHATS_RUNNING.pop(pid, None)
        return n


def chats_running(pid=None):
    """How many chats are open on `pid`, or the whole {pid: n} map."""
    with _CHAT_LOCK:
        if pid is None:
            return dict(_CHATS_RUNNING)
        return _CHATS_RUNNING.get(pid, 0)


@contextlib.contextmanager
def chat_lease(pid):
    """`with providers.chat_lease(active_id):` around a chat connection.

    The release is in a finally, so a crashed or disconnected pane cannot leave
    a provider permanently marked busy -- which would turn the update button off
    forever with nothing on screen to explain it.
    """
    chat_started(pid)
    try:
        yield
    finally:
        chat_finished(pid)


def _update_action(pid, kind):
    """WHAT the update button would do for this row.

        claude-update  run `claude update` -- Claude Code's own updater, and
                       the only thing that maintains a native install
        sutra-npm      npm install into SUTRA'S OWN prefix, then point Sutra at
                       it. The operator's own copy, if they have one, is never
                       written to; their terminal keeps resolving exactly what
                       it resolves today
        manual         nothing Sutra may do. The row says what to run instead

    npm-global IS `sutra-npm`, NOT `manual`, and that is the point of the
    --prefix design: someone with their own `npm -g codex` still gets a working
    Update button, because Sutra fetches its own copy rather than fighting
    their npm. Homebrew is the one hard no -- a formula's files belong to brew,
    and a `brew upgrade` later would undo whatever we did.

    Claude has no `sutra-npm` arm on purpose: there is no Sutra-managed Claude
    install to update into, and quietly shadowing the operator's Claude Code
    with a second copy is a far bigger act than doing the same for a provider
    CLI Sutra installed itself.
    """
    if kind == "homebrew":
        return "manual"
    if pid == "claude":
        return "claude-update" if kind == "claude-self" else "manual"
    if kind is None:
        return "manual"           # nothing installed; Install, not Update
    return "sutra-npm"


def _tool_note(pid, bin_path, kind, installed, latest, minimum, action):
    """The one sentence the row shows, or None when there is nothing to say."""
    package = PROVIDER_NPM_PACKAGE.get(pid, pid)
    if not bin_path:
        return ("the `%s` CLI is not on this Mac, so there is no version to "
                "report." % _bin_for(pid, pid))
    parts = []
    if installed and minimum and not version_at_least(installed, minimum):
        parts.append(
            "this is version %s, and Sutra's %s support was built and measured "
            "against %s, so some of it may not work here. Nothing is blocked -- "
            "updating is the fix." % (installed, pid, minimum))
    if kind == "homebrew":
        parts.append("Homebrew installed this, so Sutra will not touch it. "
                     "Update it yourself with `brew upgrade %s`."
                     % package.split("/")[-1])
    elif action == "manual" and pid == "claude":
        parts.append("this `claude` did not come from Claude Code's own "
                     "installer, so `claude update` is not what maintains it. "
                     "Update it the way you installed it.")
    elif kind == "npm-global" and action == "sutra-npm":
        parts.append("this copy came from your own global npm. Updating here "
                     "installs a separate copy into Sutra's folder and points "
                     "Sutra at that -- yours is left exactly as it is.")
    if installed and not latest:
        parts.append("the npm registry could not be reached, so whether a "
                     "newer version exists is unknown.")
    return " ".join(parts) or None


def _tool_row(pid, name):
    """One provider's version row. Never raises: every probe inside fails soft."""
    binary = _bin_for(pid, pid)
    bin_path = provider_bin(pid)
    kind = _install_kind(pid, bin_path)
    installed = installed_version(pid, bin_path) if bin_path else None
    package = PROVIDER_NPM_PACKAGE.get(pid)
    latest = npm_latest(package) if package else None
    minimum = PROVIDER_MIN_VERSIONS.get(pid)
    action = _update_action(pid, kind)
    if action == "claude-update":
        command = "%s update" % (bin_path or binary)
    elif action == "sutra-npm":
        command = "npm install %s@%s --prefix %s" % (
            package, latest or "latest",
            SETTINGS_PATH.parent / "providers" / pid)
    elif kind == "homebrew":
        command = "brew upgrade %s" % (package or pid).split("/")[-1]
    elif kind == "npm-global":
        command = "npm install -g %s" % package
    else:
        command = None
    return {
        "id": pid,
        "name": name,
        "bin": bin_path or binary,
        "installed_version": installed,
        "latest_version": latest,
        "minimum": minimum,
        "update_available": bool(installed and latest
                                 and version_tuple(latest) > version_tuple(installed)),
        "too_old": bool(installed and minimum
                        and not version_at_least(installed, minimum)),
        # Did SUTRA put the binary that is in use there? A fact about the
        # CURRENT install, and NOT the same question as "may the button be
        # pressed" -- an operator's own global npm copy is not Sutra-managed and
        # is still updatable, because Sutra fetches its own rather than touching
        # theirs. `can_update` is the button's answer.
        "managed_by_sutra": kind == "sutra",
        "install_kind": kind,
        "update_action": action,
        "can_update": action != "manual" and chats_running(pid) == 0,
        "update_command": command,
        # Whether the button may be pressed right now, and why not. Separate
        # from can_update so the client renders a disabled button with a reason
        # rather than hiding the control and leaving nothing to explain.
        "busy": chats_running(pid) > 0,
        "package": package,
        "note": _tool_note(pid, bin_path, kind, installed, latest, minimum,
                           action),
    }


def _warm_latest_versions(pids):
    """Fetch the three registry answers CONCURRENTLY, into the cache.

    Serially, an offline Mac pays TOOL_LATEST_TIMEOUT three times before the
    screen draws -- about half a minute of nothing, for three answers that are
    all going to be "unknown". Each lookup has its own cache key, so a single
    negative result cannot stand in for the others; running them at once is
    what turns that into one timeout.

    Failures are swallowed on purpose: npm_latest() already fails soft, and
    this is only a cache warm -- _tool_row() calls it again and gets the cached
    answer, or does the lookup itself if this could not.
    """
    packages = [p for p in (PROVIDER_NPM_PACKAGE.get(pid) for pid in pids) if p]
    if len(packages) < 2:
        return
    try:
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=len(packages)) as pool:
            list(pool.map(npm_latest, packages))
    except Exception:
        pass


def tools_report():
    """Every provider that has a CLI to version, in catalogue order.

    Only providers with a declared minimum version are listed: a provider with
    no minimum has nothing true to say about its version, and a row of nulls
    would read as a broken probe rather than as "not supported".
    """
    pids = [spec["id"] for spec in _CATALOG if spec["id"] in PROVIDER_MIN_VERSIONS]
    _warm_latest_versions(pids)
    names = {spec["id"]: spec["name"] for spec in _CATALOG}
    return [_tool_row(pid, names[pid]) for pid in pids]


class ToolUpdateError(RuntimeError):
    """A refused or failed update, with a machine-readable `code`. Same shape as
    CodexInstallError and DeepSeekInstallError so one route handles all three."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _tail(text, limit=4000):
    s = (text or "").strip()
    return s[-limit:] if len(s) > limit else s


def update_tool(pid):
    """Update one provider's CLI. Returns {ok, version_before, version_after, log}.

    Raises ToolUpdateError with a code on every refusal, so a caller never has
    to read the log to find out whether anything happened.

    THE REFUSALS, in the order they are checked:
      UNKNOWN_PROVIDER   not a provider with a CLI
      CHAT_RUNNING       a chat is live on it -- rule 4
      NOT_INSTALLED      nothing to update
      NOT_OURS           Homebrew's or a global npm's -- rules 2 and the note
      NO_NPM             npm is not reachable and the update needs it
      UPDATE_FAILED      the command ran and did not work; the log says how

    NOTHING IS REGISTERED UNTIL THE NEW BINARY RUNS. The npm path installs into
    Sutra's own prefix, proves `--version` answers there, and only then points
    Sutra at it -- the same order codex_install.install() uses, and for the same
    reason: a registered path is a claim the panel renders as "ready".
    """
    if pid not in PROVIDER_MIN_VERSIONS:
        raise ToolUpdateError("UNKNOWN_PROVIDER",
                              "there is no updatable CLI called %r" % pid)
    if chats_running(pid) > 0:
        raise ToolUpdateError("CHAT_RUNNING", (
            "a %s chat is open, and updating the CLI underneath a running turn "
            "would kill it. Close the chat and try again." % pid))

    bin_path = provider_bin(pid)
    if not bin_path:
        raise ToolUpdateError("NOT_INSTALLED", (
            "the `%s` CLI is not on this Mac, so there is nothing to update. "
            "Install it first." % _bin_for(pid, pid)))

    kind = _install_kind(pid, bin_path)
    action = _update_action(pid, kind)
    before = installed_version(pid, bin_path)

    if kind == "homebrew":
        raise ToolUpdateError("NOT_OURS", (
            "Homebrew installed this copy (%s), and Sutra will not touch a "
            "package manager's files. Update it yourself: `brew upgrade %s`."
            % (bin_path, (PROVIDER_NPM_PACKAGE.get(pid) or pid).split("/")[-1])))

    if pid == "claude":
        if action != "claude-update":
            raise ToolUpdateError("NOT_OURS", (
                "this `claude` was not installed by Claude Code's own installer "
                "(%s), so `claude update` is not what maintains it. Update it "
                "the way you installed it." % bin_path))
        ensure_login_path()
        try:
            p = subprocess.run([str(bin_path), "update"], capture_output=True,
                               text=True, timeout=TOOL_UPDATE_TIMEOUT,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise ToolUpdateError("TIMEOUT", (
                "`claude update` was still running after %ds and was stopped. "
                "Nothing here changed it; run it in a terminal to see what it "
                "is waiting on." % TOOL_UPDATE_TIMEOUT))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ToolUpdateError("UPDATE_FAILED",
                                  "`claude update` could not be run (%s)."
                                  % type(exc).__name__)
        log = _tail((p.stdout or "") + ("\n" + p.stderr if p.stderr else ""))
        invalidate_tool_caches()
        after = installed_version(pid, provider_bin(pid))
        if p.returncode != 0:
            raise ToolUpdateError("UPDATE_FAILED", (
                "`claude update` exited %s. It said: %s"
                % (p.returncode, _tail(log, 400) or "nothing.")))
        return {"ok": True, "provider": pid, "version_before": before,
                "version_after": after, "log": log,
                "changed": bool(after and after != before)}

    # codex / deepseek: npm, into SUTRA'S OWN PREFIX and nowhere else.
    #
    # A global-npm copy is NOT refused here. Installing into our own prefix
    # writes nothing the operator owns -- their `codex` stays exactly where and
    # what it is, and their terminal keeps resolving it -- so there is no file
    # of theirs to protect. What changes is only which copy SUTRA uses, which
    # is what set_provider_bin has always meant. Homebrew is refused above
    # because there the files really would be a package manager's.
    mod_name = "codex_install" if pid == "codex" else "deepseek_install"
    try:
        mod = __import__(mod_name)
    except Exception as exc:
        raise ToolUpdateError("UPDATE_FAILED",
                              "the %s installer could not be loaded (%s)."
                              % (pid, type(exc).__name__))

    npm = _npm_bin()
    if not npm:
        raise ToolUpdateError("NO_NPM", (
            "npm is not reachable from here, and the %s CLI is an npm package "
            "(%s), so it cannot be updated without it."
            % (pid, PROVIDER_NPM_PACKAGE.get(pid))))

    package = PROVIDER_NPM_PACKAGE[pid]
    want = npm_latest(package)
    spec = "%s@%s" % (package, want) if want else "%s@latest" % package
    root = mod.prefix()
    try:
        mod._write_manifest(root)
    except OSError as exc:
        raise ToolUpdateError("UPDATE_FAILED", (
            "could not prepare %s for the update (%s). Nothing was changed."
            % (root, type(exc).__name__)))
    try:
        p = subprocess.run([str(npm), "install", spec, "--prefix", str(root),
                            "--no-audit", "--no-fund", "--loglevel=error"],
                           capture_output=True, text=True,
                           timeout=TOOL_UPDATE_TIMEOUT,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ToolUpdateError("TIMEOUT", (
            "npm was still installing %s after %ds, so it was stopped. That is "
            "usually a slow or blocked connection. Nothing was registered."
            % (spec, TOOL_UPDATE_TIMEOUT)))
    except (OSError, subprocess.SubprocessError) as exc:
        raise ToolUpdateError("UPDATE_FAILED",
                              "npm could not be run (%s), so %s was not updated."
                              % (type(exc).__name__, spec))
    log = _tail((p.stdout or "") + ("\n" + p.stderr if p.stderr else ""))
    if p.returncode != 0:
        raise ToolUpdateError("UPDATE_FAILED", (
            "npm could not install %s (exit %d). It said: %s"
            % (spec, p.returncode, _tail(log, 400) or "nothing.")))

    got = mod.managed_bin()
    invalidate_tool_caches()
    after = installed_version(pid, str(got))
    if not after:
        raise ToolUpdateError("VERIFY_FAILED", (
            "%s was installed to %s but `--version` did not answer there, so "
            "nothing has been repointed and the CLI you had is still the one "
            "in use." % (spec, got)))
    try:
        set_provider_bin(pid, str(got))
    except (ValueError, OSError) as exc:
        raise ToolUpdateError("REGISTER_FAILED", (
            "%s was updated at %s and runs, but Sutra could not record where "
            "(%s)." % (spec, got, type(exc).__name__)))
    return {"ok": True, "provider": pid, "version_before": before,
            "version_after": after, "log": log,
            "changed": bool(after != before)}


if __name__ == "__main__":
    for prov in discover_providers():
        print("%-8s installed=%-5s configured=%-5s  %s"
              % (prov["id"], prov["installed"], prov["configured"],
                 prov["reason"] or "runnable (%s)" % prov["bin_path"]))
    print()
    print("active:   %s" % json.dumps(active_provider_detail(), sort_keys=True))
    print("settings: %s" % json.dumps(load_settings(), indent=2, sort_keys=True))
