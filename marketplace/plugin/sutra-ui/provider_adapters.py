"""One adapter per provider. Every provider-specific rule lives in exactly one
of them, so the chat socket stops branching on the provider id.

WHAT THIS REPLACES. `ws_chat` in app.py branched on `active_id` in about a
dozen places: which runtime class to construct, which argv builder to call,
whether to re-build the argv with --resume, whether to pre-resolve the bundled
Node, which environment overlay to spawn with, whether to run the ACP
handshake, whether to take the first-run connect lock, which turn call to make,
and what to call the process in a failure line. Each of those was a fact about
ONE provider living in the file that serves ALL providers, which is why adding
Codex meant editing seven separate `if`s and why adding a fourth would mean
editing them again.

Now the socket does `adapter = provider_adapters.get(active_id)` once and asks
the adapter. Adding a provider is adding a class here plus a catalogue entry in
providers.py -- not an edit to the turn loop.

WHAT AN ADAPTER ANSWERS
  - which runtime class serves this provider (`new_runtime`)
  - how to build the spawn argv (`spawn_args`) and how to rebuild it to resume
    an existing thread (`resume_args`)
  - which NATIVE permission mode a shared access id maps to (`native_mode_for`)
  - how the per-provider settings switches reach the argv (`switch_args`)
  - how to classify one tool call into a `kind` for the timeline
    (`classify_tool`)
  - the small spawn-time facts: environment overlay, bundled-node need, ACP
    handshake, connect lock, failure label, service-tier support

WHAT IS DELIBERATELY STILL AT THE SOCKET LAYER. Anything that writes to the
websocket, mints a chat id, or decides replay/error policy stays in ws_chat --
an adapter answers questions, it does not own the turn. See the report for the
two branches that could not move.

THE ARGV BUILDERS MOVED HERE VERBATIM. `build_agent_args`, `build_acp_args`,
`build_codex_args`, `codex_turn_config`, `codex_mode_note` and
`_CODEX_SANDBOX_FOR_MODE` were app.py module functions. They are unchanged
except for two additive keyword arguments (`switches=`) that carry the
per-provider settings flags, and app.py keeps thin wrappers under the old names
so every existing caller and test still works.
"""
import json
import os
import shutil

import providers
from acp_runtime import AcpRuntime
from codex_runtime import CodexRuntime
from session_runtime import SessionRuntime, _tool_summary


# ---------------------------------------------------------------------------
# Value validation for anything that reaches a CLI argv.
#
# Moved from app.py so the builders that use them can live here. app.py still
# exposes them under the same names (it imports them back), so nothing that
# referenced `app._flag_list` changed.
#
# Everything is validated. A value that reaches the CLI unchecked fails several
# seconds later as a dead socket, which reads as "the panel is broken" rather
# than "that input was wrong".
# ---------------------------------------------------------------------------

def _flag_str(value, limit=4000):
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v[:limit] if v else None


def _flag_list(value, limit=64):
    """A repeated flag's values. Non-strings and blanks are dropped rather than
    stringified -- passing `None` to the CLI as the text "None" is worse than
    passing nothing."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        v = _flag_str(v, 1024)
        if v:
            out.append(v)
    return out[:limit]


def _flag_money(value):
    """A budget ceiling. Rejects anything non-positive or unparseable: a `0`
    silently means "spend nothing" and would look like a hung turn."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return ("%.4f" % f).rstrip("0").rstrip(".") if f > 0 else None


EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


# ---------------------------------------------------------------------------
# The two Claude-facing JSON blobs app.py owns.
#
# `_sutra_mcp_config` and `_sutra_allow_hook` build them from app-level state
# (the app directory, this interpreter, org_api.registry_root()). Rather than
# drag that state in here -- and take an import cycle with it -- app.py INJECTS
# the two callables at import time. The defaults return "", which is exactly
# what those functions return when the scripts are absent, so this module is
# importable and testable entirely on its own.
# ---------------------------------------------------------------------------

def _no_mcp_config():
    return ""


def _no_allow_hook():
    return ""


_CLAUDE_MCP_CONFIG = _no_mcp_config
_CLAUDE_ALLOW_HOOK = _no_allow_hook


def set_claude_hooks(mcp_config=None, allow_hook=None):
    """app.py hands over its own `_sutra_mcp_config` / `_sutra_allow_hook`.
    Pass None for either to restore the empty default (what tests want)."""
    global _CLAUDE_MCP_CONFIG, _CLAUDE_ALLOW_HOOK
    _CLAUDE_MCP_CONFIG = mcp_config or _no_mcp_config
    _CLAUDE_ALLOW_HOOK = allow_hook or _no_allow_hook


# ===========================================================================
# SECTION A -- access options: the shared buttons, and what each means natively
# ===========================================================================
#
# `id` lives only in the UI/API layer. What is STORED in settings.json stays the
# existing native mode id, so an install that already chose `dontAsk` keeps
# working and nothing has to be migrated.
#
# `manual` and `dontAsk` are NOT in this list and remain perfectly valid stored
# values (routines use `dontAsk`). They are the "Advanced" tail the UI discloses
# separately; nothing here removes them.

ACCESS_OPTIONS = (
    {"id": "read",  "label": "Read only",
     "desc": "Looks and plans. Changes nothing.", "warn": False},
    {"id": "edits", "label": "Accept edits",
     "desc": "Edits files in this folder. Asks for anything else.", "warn": False},
    {"id": "auto",  "label": "Approve for me",
     "desc": "Same limit, but the tool approves routine requests itself.",
     "warn": False},
    {"id": "full",  "label": "Full access",
     "desc": "Anything on this Mac, without asking.", "warn": True},
)

#: Access ids whose native mode needs the typed consent gate
#: (providers.unsafe_modes_allowed). Derived from the native modes rather than
#: listed twice -- one source of truth for "this one writes without asking".
UNSAFE_ACCESS_IDS = ("edits", "full")


def access_options():
    """The shared list, as plain dicts a caller may mutate."""
    return [dict(o) for o in ACCESS_OPTIONS]


# ===========================================================================
# SECTION C -- per-provider settings (the bb "Claude Code tab")
# ===========================================================================
#
# EVERY SWITCH BELOW WAS VERIFIED AGAINST THE REAL CLI before it was written
# down. The commands and what they proved are in each entry's `verified` note.
# A planned switch that could not be verified was DROPPED rather than shipped on
# a guess -- see PROVIDER_SETTINGS_DROPPED at the bottom of this section.

PROVIDER_SETTINGS_SCHEMA = {
    "claude": (
        {"key": "chrome", "type": "boolean", "default": False,
         "label": "Claude in Chrome",
         "desc": "Let this chat drive your Chrome browser.",
         "verified": "claude 2.1.270: `claude -p ... --chrome` runs, and the "
                     "system/init frame's tool list gains 22 "
                     "mcp__claude-in-chrome__* tools that are absent without "
                     "the flag."},
        {"key": "subagents", "type": "boolean", "default": True,
         "label": "Subagents",
         "desc": "Let this chat start its own helper agents.",
         "verified": "claude 2.1.270: the live tool list names the subagent "
                     "tools `Task`, `TaskOutput`, `TaskStop` and `ListAgents`. "
                     "`--disallowedTools Task Workflow` removes Task from that "
                     "same init frame."},
        {"key": "workflows", "type": "boolean", "default": True,
         "label": "Workflows",
         "desc": "Let this chat run scripted multi-step workflows.",
         "verified": "claude 2.1.270: the tool is named `Workflow`, and "
                     "`--disallowedTools Task Workflow` removes it from the "
                     "init frame's tool list."},
    ),
    "codex": (
        {"key": "memory", "type": "boolean", "default": True,
         "label": "Memories",
         "desc": "Let Codex read and write its own memories.",
         "verified": "codex-cli 0.154.0: `-c memories.use_memories=\"notabool\"` "
                     "fails with `invalid type: string \"notabool\", expected a "
                     "boolean in memories.use_memories` (same for "
                     "generate_memories), so both keys are real and typed; with "
                     "=false the run parses and reaches the account's usage "
                     "limit, which is past config load."},
        {"key": "subagents", "type": "boolean", "default": True,
         "label": "Subagents",
         "desc": "Let Codex split work across several agents.",
         "verified": "codex-cli 0.154.0: `--disable <FEATURE>` is documented as "
                     "`equivalent to -c features.<name>=false`, and "
                     "`-c features.multi_agent=\"notabool\"` fails with "
                     "`expected a boolean in features`."},
    ),
}

#: Switches that were PLANNED and are NOT shipped, with the reason. Kept in the
#: code rather than only in a report so the next person does not re-plan them.
PROVIDER_SETTINGS_DROPPED = {
    ("claude", "memory"):
        "claude 2.1.270 exposes no memory flag. `claude --help | grep -i memor` "
        "finds only --bare (which also disables hooks, LSP, plugin sync, "
        "attribution, keychain reads and CLAUDE.md discovery) and "
        "--exclude-dynamic-system-prompt-sections (a cache-reuse knob). Neither "
        "is 'turn memory off', so nothing is emitted rather than something "
        "wider than the label promises.",
}


def provider_settings(pid):
    """This provider's settings values, defaults filled in.

    THREE READERS, IN ORDER, because W2 (the catalogue workstream) will publish
    the authoritative one and this must not wait for it:

      1. `providers.provider_settings(pid)` -- W2's function, once it exists.
      2. `providers._raw_settings()` -- the settings file as-is, which is where
         the new top-level `provider_settings` key lives.
      3. the settings file read directly off `providers.SETTINGS_PATH`.

    Never raises: a corrupt or absent file means "every default", which is
    today's behaviour on every one of these switches.
    """
    schema = PROVIDER_SETTINGS_SCHEMA.get(pid) or ()
    out = {s["key"]: s["default"] for s in schema}

    stored = None
    fn = getattr(providers, "provider_settings", None)
    if callable(fn):
        try:
            stored = fn(pid)
        except Exception:       # noqa: BLE001 -- a settings read must not fail a spawn
            stored = None
    if stored is None:
        raw = {}
        reader = getattr(providers, "_raw_settings", None)
        if callable(reader):
            try:
                raw = reader() or {}
            except Exception:   # noqa: BLE001
                raw = {}
        if not raw:
            try:
                raw = json.loads(providers.SETTINGS_PATH.read_text(encoding="utf-8"))
            except Exception:   # noqa: BLE001
                raw = {}
        if isinstance(raw, dict):
            block = raw.get("provider_settings")
            if isinstance(block, dict):
                stored = block.get(pid)

    if isinstance(stored, dict):
        for k, v in stored.items():
            if k in out and isinstance(v, bool):
                # ONLY booleans and ONLY known keys. A hand-edited file must not
                # be able to put an arbitrary value into an argv.
                out[k] = v
    return out


# ===========================================================================
# SECTION D -- tool kinds
# ===========================================================================
#
# THE TABLE LIVES IN tool_kinds.py, not here, for one reason: session_runtime,
# codex_runtime and acp_runtime all have to classify a tool the moment they emit
# its frame, and all three are imported BY this module. A table here would mean
# an import cycle. tool_kinds imports nothing local, so every runtime can use it
# and so can the UI workstream through the API.
#
# Re-exported under these names so a caller only ever needs `provider_adapters`.
from tool_kinds import (KINDS, classify as _classify_tool,        # noqa: E402
                        kind_table)


def classify_tool(provider_id, name, tool_input=None, extra=None):
    """One tool call -> {"kind", "title", "detail", "meta"}. See tool_kinds."""
    return _classify_tool(provider_id, name, tool_input, extra)


# ===========================================================================
# The argv builders. Moved from app.py; app.py keeps thin wrappers.
# ===========================================================================

def build_agent_args(agent_bin, msg, perm_mode, session_id=None, model=None,
                     opts=None, stream_input=False, extra_settings=None,
                     switches=None):
    """The full argv for one turn.

    Separated from the socket loop so it is testable without a subprocess, and
    so adding a flag cannot accidentally change the ordering of the ones that
    already work.

    stream_input=True builds a PERSISTENT process: `-p` with no positional
    prompt plus `--input-format stream-json`, so messages arrive on stdin as
    JSON frames and one process serves many turns. Verified against the binary:
    two messages, one process, one session id, both answered.

    `switches` is the per-provider settings tail (ClaudeAdapter.switch_args).
    APPENDED LAST so every argv that already existed is byte-identical when it
    is empty -- the position of every flag that works today is untouched.
    """
    opts = opts if isinstance(opts, dict) else {}
    args = [agent_bin, "-p"]

    # ---- Sutra's own tools ------------------------------------------------
    # Without this the chat can DESCRIBE a routine but not make one: the CLI has
    # no path back into this panel. sutra_mcp.py is a stdio MCP server the CLI
    # spawns for THIS RUN via --mcp-config, so nothing is installed and the
    # operator's global ~/.claude.json is never touched.
    #
    # --strict-mcp-config: use ONLY what we pass. Without it the CLI also loads
    # whatever servers the user has configured globally, which would silently
    # change what the panel's chat can reach depending on the machine.
    #
    # --allowedTools scoped to mcp__sutra__*: these tools must not sit behind an
    # approval prompt, because a -p run has nobody to answer one -- the call
    # would stall the turn. They are safe to pre-allow precisely because the
    # mutating ones only write an inert proposal (see proposals.py).
    mcp_cfg = _CLAUDE_MCP_CONFIG()
    if mcp_cfg:
        args += ["--mcp-config", mcp_cfg, "--strict-mcp-config"]
        # AND the hook that makes them reachable. MEASURED, not assumed: with
        # --permission-mode plan (the panel's default) every mcp__sutra__ call
        # comes back in permission_denials and the server is never invoked --
        # --allowedTools does not help, because the MODE is evaluated first.
        # A PreToolUse hook is evaluated BEFORE the mode. See mcp_allow_hook.py
        # for why allowing exactly this namespace is safe.
        # `extra_settings` is MERGED into that same inline object rather than
        # emitted as a second --settings: the CLI takes one value for this
        # flag, so a second occurrence would silently drop whichever the
        # parser did not keep -- the same trap --allowedTools carries below.
        # Position is unchanged, so every argv that already existed is
        # byte-identical when extra_settings is None.
        hook = _CLAUDE_ALLOW_HOOK()
        settings_obj = json.loads(hook) if hook else {}
        if extra_settings:
            settings_obj.update(extra_settings)
        if settings_obj:
            args += ["--settings", json.dumps(settings_obj)]
    elif extra_settings:
        args += ["--settings", json.dumps(extra_settings)]
    if stream_input:
        args += ["--input-format", "stream-json"]
    else:
        args += [msg]
    args += [
        "--output-format", "stream-json",
        "--verbose", "--include-partial-messages",
        "--permission-mode", perm_mode,
    ]
    if session_id:
        args += ["--resume", session_id]
        # Only meaningful WITH --resume: it forks the resumed thread instead of
        # continuing it. Passing it alone is silently ignored by the CLI, which
        # would make a UI toggle look broken.
        if opts.get("fork_session"):
            args += ["--fork-session"]
    if model:
        args += ["--model", model]

    # "claude" is not a default here, it is a fact: build_agent_args builds
    # CLAUDE's argv, and --fallback-model is Claude's flag.
    fallback = providers.clean_model(opts.get("fallback_model"), "claude")
    if fallback and fallback != model:
        args += ["--fallback-model", fallback]

    effort = _flag_str(opts.get("effort"))
    if effort in EFFORT_LEVELS:
        args += ["--effort", effort]

    # Extra roots the tools may touch. Confined to $HOME for the same reason the
    # workdir is: this is a loopback web app, and a directory arriving over a
    # socket must not be able to hand the agent "/".
    home = os.path.realpath(os.path.expanduser("~"))
    for d in _flag_list(opts.get("add_dir"), 16):
        real = os.path.realpath(os.path.expanduser(d))
        if real == home or real.startswith(home + os.sep):
            args += ["--add-dir", real]

    allowed = _flag_list(opts.get("allowed_tools"), 64)
    # ONE --allowedTools, not two. Sutra's own tools are appended to whatever the
    # turn asked for rather than emitted as a second flag: the CLI takes this as
    # a variadic list, so a second occurrence is a conflict, and whichever the
    # parser kept would silently drop the other -- either losing the operator's
    # per-turn allow-list or losing Sutra's tools, with no error either way.
    #
    # They are pre-allowed because a -p run has NOBODY to answer a permission
    # prompt: a tool sitting behind one would stall the turn. That is safe here
    # precisely because the mutating tools only write an inert proposal.
    #
    # ONLY the sutra namespace is pre-allowed. User connectors merged into
    # mcp_cfg are NOT added here — they run under the session's --permission-mode.
    if mcp_cfg:
        allowed = list(allowed) + ["mcp__sutra__*"]
    if allowed:
        args += ["--allowedTools"] + allowed
    denied = _flag_list(opts.get("disallowed_tools"), 64)
    if denied:
        args += ["--disallowedTools"] + denied

    extra_prompt = _flag_str(opts.get("append_system_prompt"), 8000)
    if extra_prompt:
        args += ["--append-system-prompt", extra_prompt]

    budget = _flag_money(opts.get("max_budget_usd"))
    if budget:
        args += ["--max-budget-usd", budget]

    if switches:
        args += list(switches)

    return args


def build_acp_args(agent_bin, model=None, flags=("--acp", "--skip-trust"),
                   model_flag=None):
    """The full argv for the ACP subprocess. Unlike build_agent_args, this is
    spawn-time only -- ACP's permission-mode and session are protocol-level
    (session/new, session/set_session_mode), so there is no per-message argv to
    build. The MODEL is the exception, and the reason this takes an argument.

    `flags` and `model_flag` exist so a SECOND ACP agent can reuse this builder
    without either forking it or inheriting DeepSeek's flags. The defaults are
    DeepSeek's exact old argv, so every existing caller is byte-identical.

    -m: THE MODEL WAS BEING DROPPED ON THE FLOOR. This function used to take
    only the binary, so `chosen_model` -- resolved a few lines above the spawn,
    validated, and announced to the client in the `start` frame -- reached
    Claude's argv and nothing at all on DeepSeek's. The pane displayed a model
    the CLI had never been told about, for every DeepSeek session this panel
    has ever run. Measured on the wire (2026-09-07): with no -m the fork sends
    `deepseek-v4-flash` whatever the panel claimed; with -m it sends what it
    was given.

    The caller passes a value that has already been through
    providers.clean_model(value, "deepseek"), because the fork does NOT
    validate this flag -- an unknown `deepseek-`-prefixed id is forwarded
    verbatim to the API and anything else silently becomes `deepseek-chat`.
    Passing "" or None means "no flag", which lets the CLI use its own default
    rather than asserting one here.

    Model is spawn-time here, and the reason recorded above this line was
    WRONG. It said this build answers session/set_model with -32601. It does
    not. Re-probed on the wire, 2026-09-07:

        session/set_model                 -> {}        (implemented)
        session/unstable_setSessionModel  -> -32601    (never was a method --
                                                        it is the AGENT-SIDE
                                                        HANDLER name for
                                                        session/set_model, so
                                                        calling it was always
                                                        going to 404)

    The original probe evidently tried the handler name, got -32601, and
    generalised to both. A wrong recorded finding is worse than none: anyone
    revisiting this would have believed the door was locked without checking.

    THE RESPAWN DESIGN STANDS, on a better reason. `Session.setModel` is a bare
    `config.setModel(modelId)` with NO validation -- it accepted
    "totally-bogus-model-xyz" and "" with {} on the same probe -- so a success
    here says nothing about whether the id is real, and the allow-list plus a
    respawn remains the only thing that can refuse one. Whether set_model
    changes the model MID-SESSION is untested: proving it needs a billed prompt
    turn, which that probe deliberately did not run. So it is not "impossible",
    it is "unverified and not needed" -- respawn already works, because
    spawn_key is tuple(args) and this argv carries the model.

    --skip-trust: this CLI is spawned into whatever workdir the operator's
    Sutra workdir setting points at -- the same directory Claude is spawned
    into -- which by definition was never trusted from an interactive
    `deepseek` prompt first. Without this flag the underlying Gemini-CLI-
    fork trust dialog stalls the process waiting for a TTY answer that
    never comes.
    """
    args = [agent_bin] + list(flags)
    if model:
        args += [model_flag or providers.model_flag_for("deepseek") or "-m", model]
    return args


#: Sutra permission modes codex can enforce -> its sandbox mode. Anything not
#: in here has NO codex equivalent and is answered by the safest option rather
#: than the nearest-looking one (see build_codex_args).
_CODEX_SANDBOX_FOR_MODE = {
    "plan": "read-only",
    "acceptEdits": "workspace-write",
    # bypassPermissions is deliberately ABSENT: it is not a --sandbox value, it
    # is a different flag that replaces the sandbox entirely.
}


def codex_mode_note(perm_mode):
    """None when codex can honour `perm_mode`, else the divergence to STATE.

    Reachable because permission_mode is stored GLOBALLY, not per provider: an
    operator who picks `dontAsk` while Claude is selected and then switches to
    Codex arrives here with a mode codex has no equivalent for. The client's
    picker already hides those on a Codex pane (permission_modes_for), but it
    cannot un-store a value chosen on another provider.

    Same contract and same frame as DeepSeek's `rt.acp_mode_note`: the pane's
    permission chip is showing what the operator chose, and if nothing is
    enforcing it they have to be told rather than left to infer it.
    """
    if perm_mode in providers.permission_modes_for("codex"):
        return None
    return {
        "asked": perm_mode,
        "running": "plan",
        "reason": "codex has no equivalent for %r. Its approval policies are "
                  "untrusted/on-failure/on-request/granular/never, and every "
                  "one except `never` waits for an answer on a channel a chat "
                  "pane does not have -- a `codex exec` run has nobody to "
                  "approve anything, so it would stall rather than prompt. "
                  "This turn runs read-only instead of running something "
                  "wider than you asked for." % perm_mode,
    }


#: The two per-turn config keys codex enumerates, and the enum each is checked
#: against. Sutra emits NOTHING it has not validated: codex accepts `-c` values
#: fairly loosely (a bad `model_reasoning_effort` sailed through), so the
#: allow-list is the only thing standing between a typo in a client payload and
#: a silently different run.
_CODEX_TURN_CONFIG = (
    ("reasoning_summary", "model_reasoning_summary", providers.CODEX_REASONING_SUMMARY),
    ("verbosity", "model_verbosity", providers.CODEX_VERBOSITY),
)

#: Accepted `service_tier` values (SPEC section E). MEASURED on codex-cli
#: 0.154.0: `-c service_tier=fast` is reported back by the CLI as `priority`, so
#: `fast` is an alias the binary resolves -- and an unrecognised value is NOT
#: refused, it is carried as far as the request and then dropped with a warning
#: ("Configured service tier `nonsense` is not advertised as supported for model
#: `gpt-5.5`"). That is exactly why this allow-list exists: the CLI will not say
#: no for us.
CODEX_SERVICE_TIERS = ("fast",)


def codex_turn_config(opts, model=None):
    """`-c key=value` pairs for one turn's options. [] when there are none.

    PURE, so the mapping from a client payload to argv can be tested without a
    subprocess -- the same reason build_codex_args is separate from the socket
    loop.

    A value not in its enum is DROPPED, not passed on and not an error. Codex
    would take an unknown one and run with a fallback, which is a turn that
    quietly did something other than what the control said; leaving the key off
    means codex uses its own default, which is what the empty option means
    anyway. "" is the empty option and is skipped by the same test.

    TOML, not bare text: `-c` parses the value as TOML and falls back to a
    literal string, so a quoted scalar is what these enums actually are.
    """
    if not isinstance(opts, dict):
        return []
    out = []
    for key, cfg, allowed in _CODEX_TURN_CONFIG:
        val = opts.get(key)
        if not isinstance(val, str):
            continue
        v = val.strip()
        if not v or v not in allowed:
            continue
        out += ["-c", '%s="%s"' % (cfg, v)]

    # REASONING EFFORT, validated against a list that depends on the MODEL --
    # which is why it cannot live in the table above. Measured on one account:
    # terra offers `ultra`, luna does not, 5.5 stops at `xhigh`. A fixed list
    # would offer every model the union, and codex takes an unsupported value
    # silently, so the turn would just quietly run at something else.
    #
    # `model` is the id already chosen for this turn, or None for "CLI
    # default" -- codex_efforts_for() resolves None to whatever model/list
    # marked isDefault, the same resolution the client's picker uses, so the
    # control and this check cannot disagree about what is offerable.
    #
    # Unknown model, no discovery, or an effort this model does not support all
    # end the same way: nothing is emitted and codex uses its own default.
    effort = opts.get("reasoning_effort")
    if isinstance(effort, str) and effort.strip():
        v = effort.strip()
        if v in providers.codex_efforts_for(model):
            out += ["-c", 'model_reasoning_effort="%s"' % v]

    # SERVICE TIER (SPEC section E). Same allow-list policy as everything above
    # it, for the measured reason in CODEX_SERVICE_TIERS: the CLI accepts any
    # string here and only warns.
    tier = opts.get("service_tier")
    if isinstance(tier, str) and tier.strip() in CODEX_SERVICE_TIERS:
        out += ["-c", 'service_tier="%s"' % tier.strip()]
    return out


def build_codex_args(agent_bin, perm_mode, workdir, model=None, session_id=None,
                     opts=None, switches=None):
    """The full argv for one `codex exec` turn.

    ONE PROCESS PER TURN, unlike the other two builders. codex exec reads the
    prompt, streams JSONL and exits; continuity is `resume <thread_id>`. So
    everything -- model, sandbox, approval policy, resume -- is spawn-time
    argv, which is also why the provider declares no turn_options.

    Every element below was verified against codex-cli 0.153.2 on 2026-09-08
    and re-checked against 0.154.0 on 2026-09-14.

    FLAG ORDER IS LOAD-BEARING. `codex exec resume` accepts only
    -c/--last/--all/--enable/--disable/-i/--strict-config -- NOT --json,
    --sandbox, -C, --skip-git-repo-check or -m. Measured both ways:

        exec --json --sandbox read-only -C wd --skip-git-repo-check resume ID -
            -> parsed, ran, emitted JSONL
        exec resume --last --json
            -> plain-text error, NO JSON on stdout at all

    So `resume` goes LAST, after every flag, and the prompt marker after it.
    `switches` (the per-provider settings `-c` pairs) is therefore emitted with
    the other `-c` flags, BEFORE resume -- appending it at the end, as Claude's
    builder does, would put flags after `resume` and break the parse.

    --skip-git-repo-check is MANDATORY, not defensive. Without it codex refuses
    with "Not inside a trusted directory and --skip-git-repo-check was not
    specified." and emits nothing -- and the Sutra workdir is frequently not a
    git repo. This is the direct analogue of DeepSeek's --skip-trust.

    THE PROMPT IS NOT HERE. The argv ends with `-`, codex's documented "read
    instructions from stdin" form, and CodexRuntime.send_prompt writes it
    there. Putting the message in argv would work for short turns and die at
    exec with E2BIG on a long one -- which is the failure switch.py's
    ARGV_SAFETY_FRACTION exists to predict, and which stdin has no ceiling for.

    approval_policy=never is what makes a headless run possible: all three
    probe turns ran with stdin closed after the prompt and never stalled
    waiting for a TTY answer.
    """
    args = [agent_bin, "exec", "--json", "--skip-git-repo-check", "-C", workdir]

    if perm_mode == "bypassPermissions":
        # NOT a --sandbox value. This flag replaces the sandbox rather than
        # selecting one, so it is passed alone -- adding --sandbox beside it
        # would be asking for two different things at once.
        args += ["--dangerously-bypass-approvals-and-sandbox"]
    else:
        # Unknown modes land on read-only, the NARROWEST option. Widening on an
        # unrecognised value is the one direction this must never be wrong in;
        # codex_mode_note() says so on screen rather than letting it be silent.
        sandbox = _CODEX_SANDBOX_FOR_MODE.get(perm_mode, "read-only")
        args += ["--sandbox", sandbox, "-c", "approval_policy=never"]
        if sandbox == "workspace-write":
            # NAMED EXPLICITLY rather than inherited. Whether workspace-write
            # defaults its writable root to the -C directory on the exec path
            # was NOT measured, and a wrong guess here either blocks the edits
            # the operator opted into or widens them past the workdir. Stating
            # it removes the guess. json.dumps for the escaping: this is a TOML
            # array of basic strings, and a path is operator-supplied.
            args += ["-c", "sandbox_workspace_write.writable_roots=%s"
                     % json.dumps([workdir])]

    # PER-TURN OPTIONS, and they belong here rather than on a running session
    # because `codex exec` has none: one process per turn means a spawn-time
    # `-c` IS a per-turn control. Emitted BEFORE `resume` for the same reason
    # every other flag is -- `codex exec resume` accepts no flags after it.
    args += codex_turn_config(opts, model)

    if switches:
        args += list(switches)

    if model:
        # Pre-validated by the caller through providers.clean_model(value,
        # "codex"). codex does NOT validate this: measured, an unknown id is
        # accepted with a "Model metadata ... not found" warning and then runs
        # on fallback metadata, so the allow-list is the only thing that can
        # refuse one.
        args += [providers.model_flag_for("codex") or "-m", model]

    if session_id:
        args += ["resume", session_id]

    # Prompt on stdin. Must be the final element.
    args += ["-"]
    return args


# ===========================================================================
# The adapters
# ===========================================================================

class ProviderAdapter:
    """The questions ws_chat asks about a provider, in one place.

    Every hook has a default that is right for "a provider with nothing
    special", so a new adapter overrides only what is genuinely different.
    """

    id = ""
    name = ""
    runtime_class = None

    #: "stream_input" -> one persistent process fed stream-json frames (Claude);
    #: "prompt"       -> one send-and-read-to-terminal call (Codex, ACP).
    turn_style = "prompt"

    #: The CLI is a `#!/usr/bin/env node` shim, so Node must resolve at spawn.
    needs_bundled_node = False
    #: The spawn is followed by an ACP handshake (authenticate + session/new).
    needs_acp_handshake = False
    #: The catalogue says this provider has a fast/service-tier switch.
    supports_service_tier = False
    #: What ws_chat calls the process in the LAST-RESORT failure line ("%s
    #: exited %s"), reached only when a turn failed with an empty stderr and no
    #: result payload.
    #:
    #: FROZEN AT TODAY'S TEXT, not corrected. The line used to be a literal
    #: `"codex exited " if active_id == "codex" else "claude exited "`, so a
    #: DeepSeek failure has always said "claude exited N" -- wrong, and known
    #: wrong: the comment on that branch said the codex arm was added separately
    #: "because interpolating active_id would also change the sentence DeepSeek
    #: shows -- a working provider's error text is not this change's business."
    #: That is still true of THIS change. DeepSeekAdapter therefore keeps
    #: "claude" here on purpose; correcting it belongs to a change that owns
    #: DeepSeek's error text and can re-record the goldens for it.
    exit_label = "claude"

    #: Shared access id -> the NATIVE mode stored in settings.json.
    access_map = {}

    # ---------------------------------------------------------------- setup --

    def available(self):
        """Is this adapter offerable on THIS machine? Overridden only by
        adapters that are not in providers.py's catalogue yet."""
        return True

    def new_runtime(self):
        return self.runtime_class()

    # ----------------------------------------------------------------- argv --

    def settings(self):
        """This provider's settings switches, defaults filled in."""
        return provider_settings(self.id)

    def switch_args(self, settings=None):
        """Extra argv this provider's settings switches contribute. []
        by default: a provider with no switches adds nothing."""
        return []

    def extra_opts(self, opts, settings=None):
        """A COPY of the turn's opts with any settings-driven additions folded
        in. Claude's disallowed-tool switches use this, because they are a list
        the turn may already have entries in and a second --disallowedTools
        would silently lose one of the two."""
        return opts

    def spawn_args(self, agent_bin, msg, perm_mode, workdir, model=None,
                   session_id=None, opts=None, settings=None,
                   extra_settings=None):
        raise NotImplementedError

    def resume_args(self, agent_bin, msg, perm_mode, workdir, model=None,
                    session_id=None, opts=None, settings=None,
                    extra_settings=None):
        """The argv to use when the process is DEAD and a thread is to be
        resumed, or None for "the spawn argv already carries it".

        None is the right answer for Codex (resume is baked into the spawn argv,
        which is correct because the process is one-shot) and for ACP (no
        --resume flag exists; a dead ACP process starts a genuinely new session
        -- a known gap that session/load could close later, not a silent one).
        """
        return None

    def spawn_env(self, key=None):
        """Environment OVERLAY for the spawn, or None."""
        return None

    # ---------------------------------------------------------- permissions --

    def native_modes(self):
        """The native modes this provider can actually enforce."""
        return tuple(providers.permission_modes_for(self.id))

    def native_mode_for(self, access_id):
        """SECTION A: shared access id -> this provider's native mode, or None
        when this provider does not offer that option at all (Codex and DeepSeek
        have no equivalent of Claude's `auto`)."""
        return self.access_map.get(access_id)

    def access_id_for(self, native_mode):
        """The reverse lookup, or None for a native mode outside the shared list
        (`manual` and `dontAsk` are valid stored values and deliberately have no
        access id -- they live under the UI's Advanced disclosure)."""
        for aid, native in self.access_map.items():
            if native == native_mode:
                return aid
        return None

    def access_options(self):
        """The shared rows THIS provider can honour, in the shared order."""
        return [dict(o) for o in ACCESS_OPTIONS if o["id"] in self.access_map]

    def supports_mode(self, native_mode):
        return native_mode in self.native_modes()

    def mode_note(self, perm_mode):
        """The divergence to state when this provider cannot honour the mode the
        operator chose, or None. Computed without a round trip where possible;
        ACP's comes back from the CLI itself (rt.acp_mode_note)."""
        return None

    # ----------------------------------------------------------------- turn --

    async def run_turn(self, rt, msg, emit, session_id):
        """Run one whole turn. Returns the 5-tuple
        (session_id, got_text, got_result, result_error, eof).

        May raise BrokenPipeError / ConnectionResetError / AttributeError when
        the process died between the socket layer's liveness check and the
        write; the recovery policy stays at the socket layer.
        """
        return await rt.prompt_turn(msg, emit, session_id)

    # ----------------------------------------------------------------- tool --

    def classify_tool(self, name, tool_input=None, extra=None):
        return classify_tool(self.id, name, tool_input, extra)


class ClaudeAdapter(ProviderAdapter):
    id = "claude"
    name = "Claude Code"
    runtime_class = SessionRuntime
    turn_style = "stream_input"
    exit_label = "claude"
    supports_service_tier = False

    #: Claude is the only provider offering all four (it has a native `auto`).
    access_map = {"read": "plan", "edits": "acceptEdits",
                  "auto": "auto", "full": "bypassPermissions"}

    #: SETTINGS SWITCH -> the tool name to deny. VERIFIED on claude 2.1.270 by
    #: reading the live system/init frame's `tools` array, not by guessing:
    #: without --disallowedTools it lists Task/TaskOutput/TaskStop/ListAgents
    #: and Workflow; with `--disallowedTools Task Workflow` both Task and
    #: Workflow are gone from that same array.
    #:
    #: TaskOutput/TaskStop/ListAgents are denied alongside Task because they
    #: only ever operate on a subagent Task started -- leaving them reachable
    #: with the launcher gone offers the model tools that can do nothing.
    #:
    #: `Agent` is included although 2.1.270 does not offer it: an unknown name
    #: in --disallowedTools is accepted without error (verified: the run with
    #: `--disallowedTools Task Agent Workflow` started normally), and older
    #: builds named the tool that way.
    _SWITCH_DENIES = {
        "subagents": ("Task", "Agent", "TaskOutput", "TaskStop", "ListAgents"),
        "workflows": ("Workflow",),
    }

    def switch_args(self, settings=None):
        s = settings if isinstance(settings, dict) else self.settings()
        args = []
        if s.get("chrome"):
            # VERIFIED on claude 2.1.270: with --chrome the init frame's tool
            # list gains 22 mcp__claude-in-chrome__* entries that are absent
            # without it. Default OFF, so an operator who never asked for it
            # gets the argv that exists today, byte for byte.
            args.append("--chrome")
        return args

    def extra_opts(self, opts, settings=None):
        """Fold the OFF switches into the turn's own disallowed-tools list.

        Through `opts` rather than as a second --disallowedTools: the CLI takes
        that flag as a variadic list, so two occurrences are a conflict and
        whichever the parser kept would silently drop the other -- losing either
        the operator's per-turn deny-list or this switch, with no error.
        """
        s = settings if isinstance(settings, dict) else self.settings()
        deny = []
        for key, names in self._SWITCH_DENIES.items():
            if s.get(key) is False:
                deny += list(names)
        if not deny:
            return opts
        base = opts if isinstance(opts, dict) else {}
        merged = dict(base)
        existing = _flag_list(base.get("disallowed_tools"), 64)
        merged["disallowed_tools"] = existing + [d for d in deny
                                                 if d not in existing]
        return merged

    def spawn_args(self, agent_bin, msg, perm_mode, workdir, model=None,
                   session_id=None, opts=None, settings=None,
                   extra_settings=None):
        s = settings if isinstance(settings, dict) else self.settings()
        return build_agent_args(
            agent_bin, msg, perm_mode,
            # SESSION ID IS DELIBERATELY NOT PASSED HERE. ws_chat compares a
            # RESUME-FREE key each message; a resume-bearing one made that
            # comparison permanently unequal and cold-started claude on every
            # message. resume_args() below builds the resume-bearing argv for
            # the spawn itself.
            session_id=None, model=model, opts=self.extra_opts(opts, s),
            stream_input=True, extra_settings=extra_settings,
            switches=self.switch_args(s))

    def resume_args(self, agent_bin, msg, perm_mode, workdir, model=None,
                    session_id=None, opts=None, settings=None,
                    extra_settings=None):
        """Claude is the ONLY provider with a --resume flag on the spawn argv,
        and the only one whose process is meant to outlive a turn. A dead
        process plus a known thread means: rebuild the argv WITH --resume, spawn
        that, and leave the stored comparison key resume-free."""
        if not session_id:
            return None
        s = settings if isinstance(settings, dict) else self.settings()
        return build_agent_args(
            agent_bin, msg, perm_mode, session_id=session_id, model=model,
            opts=self.extra_opts(opts, s), stream_input=True,
            extra_settings=extra_settings, switches=self.switch_args(s))

    async def run_turn(self, rt, msg, emit, session_id):
        """One stream-json frame on stdin, then demux the answer. The write may
        raise if the process died between the liveness check and here; the
        socket layer owns that policy."""
        await rt.send_user_frame(msg)
        return await rt.demux_turn(emit, session_id)


class CodexAdapter(ProviderAdapter):
    id = "codex"
    name = "Codex"
    runtime_class = CodexRuntime
    exit_label = "codex"
    supports_service_tier = True
    #: @openai/codex publishes bin/codex.js, 13KB of ESM beginning
    #: `#!/usr/bin/env node`, which resolves a platform package and execs the
    #: Rust binary inside it. On a Node-less Mac a Codex installed by Sutra has
    #: exactly DeepSeek's `env: node: No such file or directory` waiting for it.
    needs_bundled_node = True

    #: No native `auto`: codex's approval policies all wait for an answer on a
    #: channel a headless `codex exec` run does not have.
    access_map = {"read": "plan", "edits": "acceptEdits",
                  "full": "bypassPermissions"}

    def switch_args(self, settings=None):
        """VERIFIED against codex-cli 0.154.0. Both keys are real and TYPED --
        passing a string where a boolean belongs fails at config load naming the
        exact key -- which is the proof that matters here, because codex ignores
        an unrecognised `-c` key in silence."""
        s = settings if isinstance(settings, dict) else self.settings()
        args = []
        if s.get("memory") is False:
            args += ["-c", "memories.use_memories=false",
                     "-c", "memories.generate_memories=false"]
        if s.get("subagents") is False:
            args += ["-c", "features.multi_agent=false"]
        return args

    def spawn_args(self, agent_bin, msg, perm_mode, workdir, model=None,
                   session_id=None, opts=None, settings=None,
                   extra_settings=None):
        """RESUME IS BAKED IN HERE, unlike Claude's path, and that is correct
        rather than a copy of a bug. Claude keeps ONE PROCESS across turns, so a
        resume-bearing key made the reuse test permanently unequal. `codex exec`
        is one process per TURN -- it exits after answering -- so `alive` is
        always False at the top of the next turn and the comparison can never
        mis-fire. The thread id therefore belongs in the argv the key is built
        from.

        THE PROMPT IS NOT PASSED. build_codex_args ends the argv with `-` and
        CodexRuntime.send_prompt delivers it on stdin, so no message text ever
        reaches argv (and E2BIG cannot happen on a long switch payload).
        """
        s = settings if isinstance(settings, dict) else self.settings()
        return build_codex_args(agent_bin, perm_mode, workdir, model=model,
                                session_id=session_id, opts=opts,
                                switches=self.switch_args(s))

    def mode_note(self, perm_mode):
        """Computed WITHOUT a round trip: codex's permission posture is
        spawn-time argv, so the mismatch is known from `perm_mode` alone."""
        return codex_mode_note(perm_mode)


class AcpAdapter(ProviderAdapter):
    """Shared base for every agent that speaks ACP over stdio. DeepSeek is the
    one that ships; Cursor reuses the whole transport and changes only the
    argv."""

    runtime_class = AcpRuntime
    needs_acp_handshake = True
    #: Permission mode is protocol-level (session/new + session/set_session_mode)
    #: and the model is spawn-time argv, so there is no per-message argv at all.
    access_map = {"read": "plan", "edits": "acceptEdits",
                  "full": "bypassPermissions"}

    #: The spawn flags after the binary, and the model flag. Subclasses override.
    acp_flags = ("--acp",)
    acp_model_flag = None
    #: Does this agent take a model on the argv AT ALL? DeepSeek's `-m` was
    #: measured on the wire; a second ACP agent's was not. False means the CLI
    #: uses its own default and the pane does not claim otherwise -- which is
    #: better than a guessed flag that is either silently ignored or fails the
    #: spawn. Default True, so DeepSeek is unchanged.
    emits_model = True

    def new_runtime(self):
        """Tell the runtime WHICH ACP agent it is driving. The only thing that
        reads it is the tool-kind table, and both ACP agents share one table --
        so this is a label, not a branch. AcpRuntime defaults it to "deepseek",
        which is what every existing construction site gets."""
        rt = self.runtime_class()
        rt.provider_id = self.id
        return rt

    def spawn_args(self, agent_bin, msg, perm_mode, workdir, model=None,
                   session_id=None, opts=None, settings=None,
                   extra_settings=None):
        return build_acp_args(agent_bin, model if self.emits_model else None,
                              flags=self.acp_flags,
                              model_flag=self.acp_model_flag)


class DeepSeekAdapter(AcpAdapter):
    id = "deepseek"
    name = "DeepSeek"
    #: "claude", deliberately -- see ProviderAdapter.exit_label. This is the
    #: string this path has always produced for DeepSeek.
    exit_label = "claude"
    needs_bundled_node = True
    #: The `deepseek` command npm publishes is a `#!/usr/bin/env node` shim.
    acp_flags = ("--acp", "--skip-trust")

    def spawn_env(self, key=None):
        """DeepSeek has no subscription path and REQUIRES a key. Resolved by the
        socket layer through providers.deepseek_key_for_request() -- the one
        resolution path, so the keychain and the env cannot disagree -- and
        handed here rather than read from os.environ a second time."""
        return {"DEEPSEEK_API_KEY": key} if key else None


class CursorAdapter(AcpAdapter):
    """`cursor-agent acp` through the existing ACP runtime.

    NOT VERIFIED LIVE. `cursor-agent` is not installed on the machine this was
    written on, so the argv below is what Cursor documents (`cursor-agent acp`,
    an ACP stdio agent) and nothing more. Everything downstream of the spawn is
    AcpRuntime, which IS exercised -- by the DeepSeek tests and by a fake ACP
    agent in this adapter's own test -- so what is untested here is exactly one
    thing: whether `cursor-agent acp` is the right command on a real install.

    NO MODEL FLAG IS EMITTED. DeepSeek's `-m` was measured on the wire; Cursor's
    equivalent was not, and inventing one would either be silently ignored or
    fail the spawn. Until someone with the binary measures it, the CLI uses its
    own default and the pane does not claim otherwise.

    VISIBLE ONLY WHERE THE BINARY EXISTS -- `available()` below. It is not in
    providers.py's catalogue yet (that file belongs to the catalogue
    workstream), so nothing can select it from the UI until W2 adds the entry;
    registering it here means the adapter is ready and testable when it does.
    """

    id = "cursor"
    name = "Cursor"
    exit_label = "cursor-agent"
    acp_flags = ("acp",)
    #: `cursor-agent acp` is a subcommand, not a flag, hence no leading dashes.
    #: NO MODEL ON THE ARGV. Without this, build_acp_args' fallback would hand
    #: Cursor DEEPSEEK's `-m` -- a flag measured against a different binary.
    emits_model = False

    BIN = "cursor-agent"

    def available(self):
        """Only where the binary is actually installed. Checked through
        providers' own resolver when it knows this id, so a SUTRA_UI_CURSOR_BIN
        override or a bundled copy is honoured; PATH otherwise."""
        try:
            prov = providers.provider_by_id(self.id)
        except Exception:       # noqa: BLE001
            prov = None
        if prov is not None:
            return bool(prov.get("bin_path"))
        return bool(shutil.which(self.BIN))


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

_ADAPTERS = {}


def register(adapter):
    """Add or replace an adapter. Returns it, so a subclass can be registered
    at definition site."""
    _ADAPTERS[adapter.id] = adapter
    return adapter


for _cls in (ClaudeAdapter, CodexAdapter, DeepSeekAdapter, CursorAdapter):
    register(_cls())


def get(pid):
    """The adapter for a provider id, or None when this build has no chat
    adapter for it.

    None is the honest answer and the socket layer refuses on it: the frame
    parsers below speak Claude's stream-json, Codex's exec --json or ACP, and
    spawning another vendor's CLI with those flags would fail on argument
    parsing and report as though the provider were broken.

    An adapter whose binary is absent (Cursor on a machine without it) is NOT
    returned -- it would be offered and then fail at spawn.
    """
    a = _ADAPTERS.get(pid)
    if a is None:
        return None
    return a if a.available() else None


def ids():
    """Every provider id this build can run a chat on, on THIS machine."""
    return [pid for pid, a in _ADAPTERS.items() if a.available()]


def all_ids():
    """Every registered id, whether or not its binary is present here."""
    return list(_ADAPTERS)


# ---------------------------------------------------------------------------
# SECTION A, across all providers
# ---------------------------------------------------------------------------

def access_map_by_provider():
    """{provider_id: {access_id: native_mode}} for every registered adapter --
    what the UI needs to draw the shared buttons and know which are offered."""
    return {pid: dict(a.access_map) for pid, a in _ADAPTERS.items()}


def native_mode_for(pid, access_id):
    """Shared access id -> native mode for one provider, or None."""
    a = _ADAPTERS.get(pid)
    return a.native_mode_for(access_id) if a else None
