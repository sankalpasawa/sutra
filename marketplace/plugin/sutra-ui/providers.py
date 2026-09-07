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
import json
import os
import re
import shutil
import subprocess
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
DEFAULT_PERMISSION_MODE = "plan"
DEFAULT_WORKDIR = "~/sutra-ui-workspace"

# Modes that let the spawned agent act without asking. The panel's settings
# endpoint is unauthenticated by construction (it is a localhost control
# plane), so anything that can reach the port could otherwise raise the
# ceiling to "auto-approve shell commands" and the operator would only learn
# about it from a status frame. Selecting these requires an explicit
# server-side opt-in the operator sets when STARTING the server -- i.e. out of
# band from anything reachable over the socket.
UNSAFE_PERMISSION_MODES = ("acceptEdits", "bypassPermissions")
UNSAFE_MODES_ENV = "SUTRA_UI_ALLOW_UNSAFE_PERM_MODES"


UNSAFE_ACK_KEY = "unsafe_modes_acknowledged"


def unsafe_modes_allowed(settings=None):
    """True when the operator has authorised the write-capable modes.

    TWO ways in, and both are a DELIBERATE HUMAN ACT:

      1. the env var, set when starting the server -- for headless/CI, and the
         original out-of-band gate
      2. an acknowledgement recorded in settings.json by someone clicking
         through the confirmation in the UI

    (2) was added because (1) alone was unusable as a product: the panel told
    the operator to "restart the server with SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1",
    which for a Finder-launched .app means editing a plist or launching from a
    terminal -- i.e. the setting was effectively unreachable for the people the
    app is for. A control the UI shows, refuses, and cannot teach you to enable
    is worse than no control.

    The threat this still answers is UNATTENDED ENABLEMENT over the
    unauthenticated local socket. That is why the acknowledgement is not a
    plain boolean flip: api_settings_post requires the caller to send the
    confirmation phrase, so a stray POST from anything else that can reach the
    port cannot turn it on by accident. It is consent, recorded, not a default.
    """
    if os.environ.get(UNSAFE_MODES_ENV, "") == "1":
        return True
    s = settings if settings is not None else _raw_settings()
    return bool(s.get(UNSAFE_ACK_KEY))


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
    """Clamp a stored/env mode down to `plan` unless unsafe modes are enabled.

    Gating only the WRITE path (save_settings) is not enough: a settings.json
    left behind by an older build, edited by hand, or written by another local
    process would still reach the subprocess spawn. Callers must pass the mode
    through here at the point of USE, not trust what was persisted.
    """
    if mode in UNSAFE_PERMISSION_MODES and not unsafe_modes_allowed():
        return DEFAULT_PERMISSION_MODE
    return mode if mode in PERMISSION_MODES else DEFAULT_PERMISSION_MODE


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
    {"id": "opus",   "name": "Opus",         "note": "most capable, slowest, highest cost"},
    {"id": "sonnet", "name": "Sonnet",       "note": "balanced default for most work"},
    {"id": "haiku",  "name": "Haiku",        "note": "fastest and cheapest, least capable"},
)

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


def _model_selectable(entry):
    """Absent `selectable` means True.

    Deliberate: only the one unavailable entry carries the key, so every
    provider's ordinary rows stay byte-identical to what they were before this
    field existed -- nothing about Claude's payload moved.
    """
    return entry.get("selectable", True) is not False


def models_for(pid):
    """Every model this provider declares, in menu order. () for a provider
    that has none (codex, gemini) -- which is a real answer, not a gap: their
    rows render without a picker rather than with someone else's."""
    for spec in _CATALOG:
        if spec["id"] == pid:
            return spec.get("models", ())
    return ()


def model_ids_for(pid):
    """Every declared id, selectable or not. Use for "is this catalogued"."""
    return frozenset(m["id"] for m in models_for(pid))


def selectable_model_ids_for(pid):
    """The ids a session may actually RUN on. The narrower set, and the one
    clean_model() gates against -- a listed-but-disabled model must be
    unreachable through the API too, not merely greyed out in the menu."""
    return frozenset(m["id"] for m in models_for(pid) if _model_selectable(m))


def all_models_by_provider():
    """{provider_id: [model, ...]} for every provider that declares any.

    The shape the settings endpoint publishes. A provider with no models is
    ABSENT rather than present-and-empty, so the client's test for "does this
    provider have a picker" is the same test as "is it in this dict".
    """
    return {spec["id"]: list(spec["models"])
            for spec in _CATALOG if spec.get("models")}


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

# Providers this codebase can actually DRIVE. Keep in lockstep with app.py's
# ws_chat provider dispatch (SessionRuntime for claude, AcpRuntime for
# deepseek; anything else falls through to the "no-adapter" refusal). Adding
# an id here without writing its adapter re-creates the bug this set exists
# to prevent.
#
# codex: DELIBERATELY ABSENT (2026-09-04). It was added here as a staging step
# and taken back out the same day. With codex in this set the row rendered
# "Ready to use", accepted the click, and then died at connect with code
# "no-adapter" (app.py's `elif active_id != "claude"` arm) -- exactly the
# offer-a-choice-that-cannot-run failure this set exists to prevent. Refusing
# at SELECTION time is the better error until a CodexRuntime, a
# build_codex_args() and a third arm in the ws_chat dispatch exist.
#
# The Codex row now offers SIGN-IN (see the codex auth section below), which is
# a different capability from selectability and says so on screen. Signing in
# does not belong to this set and must not be read as progress toward it.
ADAPTERS = frozenset({"claude", "deepseek"})

# ------------------------------------------------------------- catalog -----
# Order is precedence order for the "first runnable provider" fallback.
# `default` marks the one the panel ships pointed at.
#
# `models` / `model_flag` / `usage_kind` are DECLARATIONS, read through
# models_for() / model_flag_for() / usage_kind_for(). They live here so a new
# provider answers all three questions by being added to this tuple, instead of
# by someone remembering to extend a switch in the picker, another in the usage
# row, and a third in the spawn path.
_CATALOG = (
    {"id": "claude", "name": "Claude Code", "bin": "claude",
     "config_dir": "~/.claude", "default": True,
     "models": _CLAUDE_MODELS, "model_flag": "--model",
     "usage_kind": "window-percent"},
    # No models and no usage: Codex is sign-in-only in this build (no adapter,
    # see ADAPTERS above). Declaring the absence is the point -- it is what
    # stops the usage row falling through to Anthropic's percentage.
    {"id": "codex", "name": "OpenAI Codex", "bin": "codex",
     "config_dir": "~/.codex", "default": False,
     "models": (), "model_flag": None, "usage_kind": "none"},
    {"id": "gemini", "name": "Gemini CLI", "bin": "gemini",
     "config_dir": "~/.gemini", "default": False,
     "models": (), "model_flag": None, "usage_kind": "none"},
    {"id": "deepseek", "name": "DeepSeek", "bin": "deepseek",
     "config_dir": "~/.deepseek", "default": False,
     "models": _DEEPSEEK_MODELS, "model_flag": "-m",
     "usage_kind": "balance"},
)


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
            return os.path.expanduser(chosen.strip())
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
CODEX_BILLING = {
    "chatgpt": "usage included in your plan",
    "api_key": "billed per token",
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
                "detail": "the `codex` CLI is not on PATH, so its sign-in "
                          "state cannot be read",
                "bin_path": None, "checked_at_ms": now}
    try:
        p = subprocess.run([bin_path, "login", "status"], capture_output=True,
                           text=True, timeout=CODEX_STATUS_TIMEOUT)
    except FileNotFoundError:
        # which() found it and exec did not: it moved between the two calls.
        return {"state": "no_binary", "key_display": "", "billing": None,
                "detail": "%s could not be run -- it is no longer there"
                          % bin_path,
                "bin_path": bin_path, "checked_at_ms": now}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"state": "unknown", "key_display": "", "billing": None,
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

    Concrete in the style of the gemini row, which names what it searched ("the
    login shell's PATH and the usual install locations were both searched")
    rather than only what is missing. "no key is saved on this Mac" was the
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
        # the row contradicted the screen it was printed on.
        pin = (" (checked against codex-cli 0.153.2)"
               if spec["id"] == "codex" else "")
        reason = ("no chat adapter yet -- this panel speaks two protocols, "
                  "Claude's stream-json and DeepSeek's ACP, and %s exposes "
                  "neither%s, so it cannot answer messages here even though "
                  "it is installed at %s" % (spec["name"], pin, bin_path))
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

    permission_mode defaults to "plan" (SAFETY rule 4 / test_perm_mode_default);
    SUTRA_UI_PERMISSION_MODE still supplies the default when no valid value is
    stored, so existing deployments keep their behaviour.
    """
    raw = _raw_settings()
    invalid = {}

    mode = _clean_permission_mode(raw.get("permission_mode"))
    if raw.get("permission_mode") is not None and mode is None:
        invalid["permission_mode"] = raw.get("permission_mode")
    if mode is None:
        mode = _clean_permission_mode(
            os.environ.get("SUTRA_UI_PERMISSION_MODE")) or DEFAULT_PERMISSION_MODE

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
                  model=None, unsafe_ack=None, model_provider=None):
    """Merge a partial update into the settings file and return load_settings().

    Validates BEFORE writing: an unknown or unrunnable provider, or an unknown
    permission_mode, raises ValueError carrying the specific reason. Written
    tmp+replace so a crash mid-write cannot leave a truncated file.
    """
    raw = _raw_settings()

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
        raw["permission_mode"] = permission_mode

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
                entry = next(m for m in models_for(target)
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


if __name__ == "__main__":
    for prov in discover_providers():
        print("%-8s installed=%-5s configured=%-5s  %s"
              % (prov["id"], prov["installed"], prov["configured"],
                 prov["reason"] or "runnable (%s)" % prov["bin_path"]))
    print()
    print("active:   %s" % json.dumps(active_provider_detail(), sort_keys=True))
    print("settings: %s" % json.dumps(load_settings(), indent=2, sort_keys=True))
