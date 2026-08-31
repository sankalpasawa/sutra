"""providers.py -- which AI CLIs are ACTUALLY usable on this machine.

The panel was hardcoded to `claude`. Making it "multi-provider" by listing
three names in a dropdown would be worse than hardcoding: it would offer the
operator two choices that cannot run, and only reveal that after they pick
one. So availability is decided by two INDEPENDENT observations, both made
fresh on every call:

  installed   = shutil.which(<bin>) is not None      -- can we exec it?
  configured  = <config dir> is a directory          -- has it ever been set up?

  adapter     = <id> in ADAPTERS                     -- can WE drive it?

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
import shutil
import subprocess
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
# straight to `claude --model`, where an unknown string fails several seconds later
# as a dead socket rather than as a refusal the operator can read. `""` means "let
# the CLI use its own default", which is the shipped behaviour and stays the default.
#
# These are ALIASES on purpose. Pinned ids go stale the moment a new snapshot ships,
# and a panel that offers a retired id is offering something that cannot run -- the
# same failure providers.py exists to prevent. The CLI resolves an alias to whatever
# it currently points at.
MODELS = (
    {"id": "",       "name": "CLI default",  "note": "whatever `claude` is configured to use"},
    {"id": "opus",   "name": "Opus",         "note": "most capable, slowest, highest cost"},
    {"id": "sonnet", "name": "Sonnet",       "note": "balanced default for most work"},
    {"id": "haiku",  "name": "Haiku",        "note": "fastest and cheapest, least capable"},
)
MODEL_IDS = frozenset(m["id"] for m in MODELS)


def clean_model(value):
    """A catalogued model id, or None. Never raises, never passes junk to the CLI."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if (v and v in MODEL_IDS) else None


def stored_model():
    """The model chosen in Settings, or None for the CLI's own default."""
    return clean_model(_raw_settings().get("model"))


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
# ws_chat guard (`if active_id != "claude": ... no adapter`). Adding an id here
# without writing its adapter re-creates the bug this set exists to prevent.
ADAPTERS = frozenset({"claude"})

# ------------------------------------------------------------- catalog -----
# Order is precedence order for the "first runnable provider" fallback.
# `default` marks the one the panel ships pointed at.
_CATALOG = (
    {"id": "claude", "name": "Claude Code", "bin": "claude",
     "config_dir": "~/.claude", "default": True},
    {"id": "codex", "name": "OpenAI Codex", "bin": "codex",
     "config_dir": "~/.codex", "default": False},
    {"id": "gemini", "name": "Gemini CLI", "bin": "gemini",
     "config_dir": "~/.gemini", "default": False},
    {"id": "deepseek", "name": "DeepSeek", "bin": "deepseek",
     "config_dir": "~/.deepseek", "default": False},
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

    adapter = spec["id"] in ADAPTERS

    if installed and configured and adapter:
        reason = None
    elif installed and configured and not adapter:
        reason = ("no chat adapter yet -- this panel drives Claude's "
                  "stream-json protocol only, so %s cannot be used here even "
                  "though it is installed at %s" % (spec["name"], bin_path))
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
        "bin_path": bin_path,
        "config_path": str(cfg_path),
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
    that the next launch silently degrades to defaults."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
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
        "model": stored_model() or "",
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
                  model=None, unsafe_ack=None):
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

    if model is not None:
        # "" is legal: it means "let the CLI choose", which is why this cannot use
        # the truthiness of clean_model() alone.
        if not isinstance(model, str) or (model.strip() and model.strip() not in MODEL_IDS):
            raise ValueError(
                "unknown model %r -- must be one of: %s (or \"\" for the CLI default)"
                % (model, ", ".join(sorted(i for i in MODEL_IDS if i))))
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
