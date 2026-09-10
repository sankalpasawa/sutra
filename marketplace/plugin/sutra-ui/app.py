"""Sutra UI — read-only local governance dashboard (Step 1: Panel A turn feed).

One FastAPI process: serves the static page, exposes a state snapshot, a paged
log read, and an SSE live-tail. Reads only — never writes a governance file.
Run: python3 -m uvicorn app:app --host 127.0.0.1 --port 7000
"""
import asyncio
import time
import fcntl
import json
import os
import pty
import shutil
import signal
import struct
import subprocess
import sys
import termios
from html import escape as _html_escape
from pathlib import Path

from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

import log_reader as lr
import session_reader as sr
import connectors_api
import org_api
import providers
import chat_store
import secrets as _secrets
import shadow_egress
import switch
import switch_egress
import fanout
from session_runtime import (SessionRuntime, _drain_to_newline,
                             _tool_command, _tool_output, _tool_summary,
                             register_runtime, unregister_runtime,
                             lookup_runtime)
from acp_runtime import AcpRuntime
from codex_runtime import CodexRuntime

# BEFORE anything reads PATH. A Finder/Dock launch inherits launchd's minimal PATH,
# so `claude` at /opt/homebrew/bin was invisible and the desktop app reported "no AI
# provider is usable here" on a machine where claude runs fine in any terminal.
# No-op when PATH already resolves a catalogued binary, i.e. for CLI/dev launches.
if providers.ensure_login_path():
    print("[providers] PATH did not resolve any AI CLI; merged the login shell's PATH "
          "(GUI launch). claude=%s" % (shutil.which("claude") or "still not found"))

app = FastAPI(title="Sutra UI", docs_url=None, redoc_url=None)


# ── Origin/Host guard (dual consult 2026-08-25) ─────────────────────────────
# Editing now defaults ON, so the unauthenticated loopback port needs its
# declared protection: MUTATING requests carrying a cross-origin Origin header
# are refused, and the Host must be loopback. This closes cross-origin BROWSER
# writes (the one NEW surface default-on editing creates). It deliberately does
# NOT authenticate local processes — they are outside the declared threat
# model (documented in providers.editing_allowed). No-Origin requests pass:
# that is the agent/CLI lane (curl, hooks, the chat runner), and a browser
# cannot strip its own Origin on a cross-origin mutation.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")

#: Per-boot panel token (dual consult 2026-08-25: "keep the token — it is
#: cheap and reduces dependence on subtle browser rules"). Served ONLY inside
#: the panel HTML; a browser page on another origin can trigger a request to
#: this port but can never READ the panel to steal the header value. Local
#: processes can — they are outside the declared threat model (see
#: providers.editing_allowed). Required only when the request carries an
#: Origin header: the agent/CLI lane sends none and stays free.
import secrets as _secrets
PANEL_TOKEN = _secrets.token_urlsafe(32)


@app.middleware("http")
async def _origin_guard(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        raw_host = request.headers.get("host") or ""
        # IPv6-safe: [::1]:8330 must parse to ::1, not "[". urlsplit handles
        # the bracket form; a bare value falls back to the pre-colon split.
        from urllib.parse import urlsplit as _us
        try:
            host = _us("//" + raw_host).hostname or ""
        except ValueError:
            host = raw_host.split(":")[0]
        if host not in ("127.0.0.1", "localhost", "::1", ""):
            return JSONResponse({"detail": "host not loopback"}, status_code=403)
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit
            ohost = (urlsplit(origin).hostname or "")
            if ohost not in ("127.0.0.1", "localhost", "::1"):
                return JSONResponse({"detail": "cross-origin mutation refused"},
                                    status_code=403)
            if request.headers.get("x-sutra-panel") != PANEL_TOKEN:
                return JSONResponse({"detail": "panel token missing or stale "
                                     "-- reload the panel"}, status_code=403)
    return await call_next(request)

# --- DNS-rebinding defence -------------------------------------------------
# Binding to 127.0.0.1 keeps other machines out; it does NOT keep out a page
# the operator visits. A hostile site can point its own DNS name at 127.0.0.1
# and reach this server through the browser -- and then the Host header is the
# attacker's name, not ours. Reject any Host that is not literal loopback.
# TrustedHostMiddleware covers websocket scopes as well as http.
ALLOWED_HOSTS = [h.strip() for h in
                 os.environ.get("SUTRA_UI_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",")
                 if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

app.include_router(org_api.router)
# Connector platform (ADR-034). The panel never sees a credential --
# it deals in connector ids and connector state only.
app.include_router(connectors_api.router)
# Workspace (flag-gated, FLAG.md): the router mounts always, and every route
# answers 404 flag_off until flags.workspace is set — mounting conditionally
# would make the flag require a restart, which FLAG.md's rollback forbids.
import workspace_api
app.include_router(workspace_api.router)
# Optimus (Focus > Optimus): a window over sutra-daemon's stores. Reads are
# fixed-path + bounded; mutations shell the daemon CLI (desktop-token gated).
import optimus_api
app.include_router(optimus_api.router)
# The Agents destination (2.239.0). Its routes live under /api/agents/<agent>/ so a
# second agent is another prefix, not another top-level shape. The engine itself is
# the `seo_agent` package: standalone, no import of anything in this app.
import agents_api  # noqa: E402
app.include_router(agents_api.router)
HERE = Path(__file__).resolve().parent


def _origin_ok(ws):
    """Same-origin gate for the websockets.

    The browser same-origin policy does NOT cover WebSocket handshakes and no
    preflight is sent, so without this any page the operator visits can open
    ws://127.0.0.1:<port>/ws/chat, drive the agent with its own prompt and read
    every token frame back. /ws/term is worse -- it writes attacker bytes
    straight into the PTY. Loopback binding stops other machines, not the
    operator's own browser. Allow only loopback origins.

    A missing Origin means a non-browser client (curl, the test suite, the
    Electron shell). Per RFC 6455 a browser MUST send Origin on a cross-origin
    handshake and a page cannot suppress it, so absent-Origin is not a
    browser-reachable bypass.
    """
    origin = ws.headers.get("origin")
    if not origin:
        return True
    extra = [o.strip() for o in
             os.environ.get("SUTRA_UI_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origin in extra:
        return True
    try:
        u = urlparse(origin)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and u.hostname in ("127.0.0.1", "localhost", "::1")


async def _reject_cross_origin(ws):
    """Deny a disallowed handshake BEFORE accept(). Returns True if rejected.

    close() before accept() denies the handshake outright (the client sees a
    403) -- never accept a socket we intend to refuse.
    """
    if _origin_ok(ws):
        return False
    await ws.close(code=1008)
    return True

# persistent (non-transient) marker files for the state panel — see README §4
STATE_MARKERS = ("active-role", "structure-first-active", ".last-reset-ts")

# --- chat wrapper config: drives an AI CLI as a subprocess (Max-plan auth, no API key) ---
# CLAUDE_BIN is the ws_term (PTY) default and the back-compatible env name.
# ws_chat no longer uses it: it resolves the ACTIVE provider through
# providers.py on every connect, so switching providers in the UI takes effect
# on the next message instead of on the next server restart.
CLAUDE_BIN = os.environ.get("SUTRA_UI_CLAUDE_BIN", "claude")
WORKDIR = os.path.expanduser(os.environ.get("SUTRA_UI_WORKDIR", "~/sutra-ui-workspace"))
# Module-level default, kept for the env-var contract (SAFETY rule 4 /
# test_perm_mode_default). The live value ws_chat sends is read per-connect
# from ~/.sutra-ui/settings.json, which falls back to exactly this env var.
PERM_MODE = os.environ.get("SUTRA_UI_PERMISSION_MODE", "plan")
INIT_CMD = os.environ.get("SUTRA_UI_INIT", "/core:start")          # run every fresh session so Sutra fires
AUTO_CAVEMAN = os.environ.get("SUTRA_UI_AUTO_CAVEMAN", "1") == "1"  # token-saving default (non-Max friendly)
INIT_DELAY = float(os.environ.get("SUTRA_UI_INIT_DELAY", "3.5"))    # secs to let the TUI boot before typing


# --------------------------------------------------------------- arg vector --
# The spawn used to be a hardcoded list with no extension point, so every CLI
# capability the panel wanted meant editing the middle of the websocket loop.
# `claude --help` on the installed binary exposes ~40 flags that are each one
# append; this makes them a FIELD rather than a code change.
#
# Everything is validated here. A value that reaches the CLI unchecked fails
# several seconds later as a dead socket, which reads as "the panel is broken"
# rather than "that input was wrong".

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


def _sutra_mcp_config():
    """Inline JSON for --mcp-config, or "" when there is nothing to pass.

    Passed as a STRING rather than a file so there is no temp file to leak, no
    path for another process to tamper with between write and read, and nothing
    to clean up when the turn ends.

    The interpreter is THIS one (sys.executable): in the packaged app that is
    the bundled CPython inside the .app, which is the only python guaranteed to
    exist on the machine and to have the modules sutra_mcp imports.

    Contents: Sutra's own "sutra" server, and nothing else.

    The connector layer that used to merge additional servers here (a hosted
    Composio tool router and a 1MCP local aggregator) is REMOVED, pending a
    rewrite on feature/connector-integration. `sutra` is not a connector -- it is
    Sutra's own tool surface over its own registry -- so it stays, and this
    function keeps its shape for the rewrite to merge back into.

    --strict-mcp-config still holds, and now means exactly one server: the
    machine's global ~/.claude.json is still never loaded. Sutra's own namespace
    is cleared by the PreToolUse hook in build_agent_args; anything added later
    must run under the session's --permission-mode rather than being pre-allowed
    here.
    """
    servers = {}
    script = HERE / "sutra_mcp.py"
    if script.is_file():
        servers["sutra"] = {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(script)],
            # Inherited by the server process; it uses these to find the same
            # registry and stores the panel is reading.
            "env": {"SUTRA_NATIVE_HOME": os.environ.get("SUTRA_NATIVE_HOME", "")},
        }
    if not servers:
        return ""
    return json.dumps({"mcpServers": servers})


def _sutra_acp_mcp_servers():
    """Sutra's own MCP server, ACP-shaped for AcpRuntime.new_session's
    mcp_servers param -- the array session/new and session/load actually take,
    per the DeepSeek CLI's bundled schema (zNewSessionRequest.mcpServers ->
    zMcpServer -> zMcpServerStdio in @sluisr/deepseek-cli's gemini-*.js).
    Different shape from _sutra_mcp_config()'s Claude-facing dict-of-dicts:
    a list, each entry carrying its own `name`, and `env` as a list of
    {name, value} pairs rather than a plain dict. No `type` key -- that
    literal only disambiguates the union's http/sse branches; stdio is the
    bare fallback (matched at runtime by `"command" in server`).

    session/new's advertised agentCapabilities.mcpCapabilities ({http, sse})
    covers only those two REMOTE transports -- confirmed against the same
    bundle (newSessionConfig branches straight to a stdio MCPServerConfig
    whenever "command" in server, no capability check involved), so the
    absence of a "stdio" capability flag does not mean stdio is unsupported.
    """
    script = HERE / "sutra_mcp.py"
    if not script.is_file():
        return []
    return [{
        "name": "sutra",
        "command": sys.executable,
        "args": [str(script)],
        "env": [{"name": "SUTRA_NATIVE_HOME",
                 "value": os.environ.get("SUTRA_NATIVE_HOME", "")}],
    }]


def _sutra_allow_hook():
    """Inline --settings JSON carrying the PreToolUse allow hook, or "".

    Inline rather than a file for the same reason as the mcp config: nothing to
    leak, nothing to tamper with between write and read, nothing to clean up.
    """
    script = HERE / "mcp_allow_hook.py"
    if not script.is_file():
        return ""
    return json.dumps({"hooks": {"PreToolUse": [{
        # The matcher narrows which tools even reach the hook; the hook itself
        # re-checks with an anchored pattern rather than trusting this.
        "matcher": "mcp__sutra__.*",
        "hooks": [{"type": "command",
                   "command": "%s %s" % (sys.executable, script)}],
    }]}})


def build_agent_args(agent_bin, msg, perm_mode, session_id=None, model=None,
                     opts=None, stream_input=False, mcp=True):
    """The full argv for one turn.

    Separated from the socket loop so it is testable without a subprocess, and
    so adding a flag cannot accidentally change the ordering of the ones that
    already work.

    stream_input=True builds a PERSISTENT process: `-p` with no positional
    prompt plus `--input-format stream-json`, so messages arrive on stdin as
    JSON frames and one process serves many turns. Verified against the binary:
    two messages, one process, one session id, both answered.

    mcp=False omits Sutra's own MCP server and its allow-hook. DEFAULT TRUE, so
    every existing caller builds a byte-identical argv -- pinned by
    test_fanout.test_build_agent_args_default_is_unchanged. It exists for the
    fan-out worker (worker.py): a throwaway sub-task has no business writing
    proposals through mcp__sutra__*, and each --mcp-config spawns another
    python server, which at three concurrent workers is three of them for
    tools none of those turns should be calling.
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
    mcp_cfg = _sutra_mcp_config() if mcp else ""
    if mcp_cfg:
        args += ["--mcp-config", mcp_cfg, "--strict-mcp-config"]
        # AND the hook that makes them reachable. MEASURED, not assumed: with
        # --permission-mode plan (the panel's default) every mcp__sutra__ call
        # comes back in permission_denials and the server is never invoked --
        # --allowedTools does not help, because the MODE is evaluated first.
        # A PreToolUse hook is evaluated BEFORE the mode. See mcp_allow_hook.py
        # for why allowing exactly this namespace is safe.
        hook = _sutra_allow_hook()
        if hook:
            args += ["--settings", hook]
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

    return args


def build_acp_args(agent_bin, model=None):
    """The full argv for the ACP subprocess. Unlike build_agent_args, this is
    spawn-time only -- ACP's permission-mode and session are protocol-level
    (session/new, session/set_session_mode), so there is no per-message argv to
    build. The MODEL is the exception, and the reason this takes an argument.

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
    args = [agent_bin, "--acp", "--skip-trust"]
    if model:
        args += [providers.model_flag_for("deepseek") or "-m", model]
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
    return out


def build_codex_args(agent_bin, perm_mode, workdir, model=None, session_id=None,
                     opts=None):
    """The full argv for one `codex exec` turn.

    ONE PROCESS PER TURN, unlike the other two builders. codex exec reads the
    prompt, streams JSONL and exits; continuity is `resume <thread_id>`. So
    everything -- model, sandbox, approval policy, resume -- is spawn-time
    argv, which is also why the provider declares no turn_options.

    Every element below was verified against codex-cli 0.153.2 on 2026-09-08.

    FLAG ORDER IS LOAD-BEARING. `codex exec resume` accepts only
    -c/--last/--all/--enable/--disable/-i/--strict-config -- NOT --json,
    --sandbox, -C, --skip-git-repo-check or -m. Measured both ways:

        exec --json --sandbox read-only -C wd --skip-git-repo-check resume ID -
            -> parsed, ran, emitted JSONL
        exec resume --last --json
            -> plain-text error, NO JSON on stdout at all

    So `resume` goes LAST, after every flag, and the prompt marker after it.

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


def _ensure_workdir(path=None):
    """Both socket handlers spawn a subprocess with cwd=<workdir>. If that
    directory does not exist, create_subprocess_exec raises FileNotFoundError
    BEFORE a single frame is written, the socket dies, and the operator sees a
    UI that simply does nothing -- no error text, no output, no clue. WORKDIR
    defaults to ~/sutra-ui-workspace, which nothing else on the system creates,
    so on a fresh machine that was the guaranteed state. ws_chat did the
    makedirs; ws_term did not. Both paths go through here now.

    Returns the usable directory, or None if it cannot be created -- the caller
    reports that to the client rather than dying mid-handshake."""
    target = path or WORKDIR
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        return None
    return target if os.path.isdir(target) else None


# Create it ONCE, at import, rather than only on the first socket connect.
# The per-handler calls below stay (a directory can be removed while the server
# runs), but doing it here means the failure is visible in the server's own
# startup rather than as a socket that dies mid-handshake on the first message
# the operator ever sends. None => could not be created; the handlers still
# report that to the client instead of raising FileNotFoundError from
# create_subprocess_exec.
WORKDIR_READY = _ensure_workdir()


def _asset_version() -> str:
    """A token that CHANGES whenever any panel asset changes, appended to every
    /static/js/*.js and panel.css URL as ?v=<token>.

    Why this exists: a desktop update replaces the bundle, but the module URLs
    were identical across versions and StaticFiles serves them with an ETag and
    NO Cache-Control. Chromium is free to reuse the cached copy without
    revalidating, so an updated app kept rendering the OLD UI -- the "Test pane
    is still there after I removed it" report was exactly this: 2.103.0 shipped
    without it, the window ran a cached 02-helpers.js that still had it. A
    per-build token in the URL makes the new bundle request new URLs, so the
    cache can never serve last version's Javascript.

    Derived from the newest mtime across the served assets rather than a wired
    version string: it needs no bump to stay correct, works from a source
    checkout where no STAMP exists, and changes for ANY edit, not just a version
    bump. Cheap -- a dozen stats on one page load."""
    root = HERE / "static"
    newest = 0.0
    for p in [root / "panel.css", root / "workspace.css", root / "agents.css", root / "panel.html",
              *sorted((root / "js").glob("*.js"))]:
        try:
            m = p.stat().st_mtime
            if m > newest:
                newest = m
        except OSError:
            pass
    return str(int(newest))


def _panel_html() -> str:
    # CAPTURE-GATE ESCAPE, accepted (dual-lane consult 2026-08-25): the
    # rendered-capture gate stamps static/** + electron/** edits only. This
    # function's token substitution is the one Python path that can change
    # render output without a stamp -- rare, and such changes co-ship with
    # static/ edits in practice. If you change the substitution itself,
    # capture the rendered panel anyway.
    """The Tier-3 org/reorg studio: the reviewed design shell, wired to the real
    /api/org/* endpoints (org_api.py -> placement_engine.py). Markup and CSS
    are byte-identical to the reviewed design; only the data layer differs
    (seed constants replaced with fetch()).

    The __ASSETVER__ token in the asset URLs is substituted here, per request, so
    the page always references the version of the JS/CSS currently on disk."""
    html = (HERE / "static" / "panel.html").read_text(encoding="utf-8")
    return (html.replace("__ASSETVER__", _asset_version())
                .replace("__DECLARATIONS__", _declarations_attr())
                .replace("__PANELTOKEN__", PANEL_TOKEN))


def _declarations_attr() -> str:
    """WHICH CONTROLS A PANE MAY SHOW, carried BY THE PAGE instead of arriving
    behind a fetch. HTML-escaped JSON for a meta `content` attribute.

    Why this is in the page. turn_options_by_provider / permission_modes_by_
    provider tell the panel which controls a pane's provider can honour, and
    they reached the client only via GET /api/settings. Until that resolved,
    the maps were empty -- and an empty map means NOT FETCHED, which the client
    answers by rendering Claude's full set. So a DeepSeek pane showed Claude's
    five turn options for the whole boot window, which is exactly when an
    operator opens that menu: before asking anything.

    The two ways out were "hide the controls until the maps arrive" (that
    changes CLAUDE's render, and a control that blinks out is its own defect)
    and this one -- make the declaration available before the first paint, so
    there is no window in which the answer is unknown. The client keeps its
    empty-map fallback for a page served without this token.

    Never raises. A panel that will not load is worse than one whose first
    paint is momentarily ungated, so a failure here degrades to exactly the
    old behaviour rather than a 500 on the page itself.
    """
    try:
        decl = {
            # active_provider(), not load_settings()["provider"] -- same
            # resolution (env, then settings.json, then first runnable) without
            # the keychain probe load_settings does for deepseek_auth. This runs
            # on every page load.
            "provider": providers.active_provider() or "",
            "turn_options_by_provider": providers.all_turn_options_by_provider(),
            "permission_modes_by_provider": providers.all_permission_modes_by_provider(),
            # {spelling: provider_id} for in-chat provider requests. Shipped
            # here for the same reason as the two maps above -- the composer
            # must be able to recognise "using Codex, ..." on the first paint,
            # before any fetch resolves -- and shipped AT ALL so provider names
            # exist in exactly one place (providers._CATALOG). A copy in JS
            # would drift silently the day a provider is renamed.
            "provider_aliases": providers.provider_aliases(),
        }
        return _html_escape(json.dumps(decl, separators=(",", ":")), quote=True)
    except Exception:
        return ""


# The page itself must never be cached, or the browser serves an old page whose
# asset URLs point at old ?v= tokens -- which would defeat the busting below.
# The versioned JS/CSS, by contrast, are safe to cache HARD: their URL changes
# when they do.
_NOCACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/api/panel-token")
async def api_panel_token():
    """Heal a stale panel after a backend restart (found live, 2026-08-25):
    in Electron the window OUTLIVES backend restarts, so the token baked into
    the page dies silently and every mutation 403s until a manual reload.
    Same-origin JS can read this and retry; a cross-site page cannot read the
    response (no CORS headers), so CSRF protection is intact."""
    return JSONResponse({"token": PANEL_TOKEN}, headers=_NOCACHE)


# (r5) /api/files/status and the shutdown hook are GONE with sb_sidecar:
# the native editor replaced the SilverBullet sidecar (PLAN-25), and its
# one-release retirement clock expired. Module archived at
# sutra/archive/sutra-ui-sidecar/.


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """THE app. This previously served term.html (the xterm console), so the
    front door showed a completely different UI from the studio, and the studio
    was reachable only if you already knew to type /panel. Anyone who opened
    the server saw the wrong product. The studio IS the app; the older
    surfaces remain reachable under /legacy/* below.
    """
    return HTMLResponse(_panel_html(), headers=_NOCACHE)


@app.get("/panel", response_class=HTMLResponse)
def panel_page() -> HTMLResponse:
    """Alias for /, so existing links and bookmarks keep working."""
    return HTMLResponse(_panel_html(), headers=_NOCACHE)


# --- legacy surfaces -------------------------------------------------------
# Pre-existing dashboards, moved off the front door rather than deleted --
# they are working tools that predate this work, not mine to remove. The old
# paths still resolve so nothing that linked to them breaks.

@app.get("/legacy/term", response_class=HTMLResponse)
def legacy_term() -> str:
    return (HERE / "static" / "term.html").read_text(encoding="utf-8")


@app.get("/legacy/panels", response_class=HTMLResponse)
@app.get("/panels", response_class=HTMLResponse)
def panels() -> str:
    return (HERE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/legacy/sessions", response_class=HTMLResponse)
@app.get("/sessions", response_class=HTMLResponse)
def sessions_page() -> str:
    return (HERE / "static" / "sessions.html").read_text(encoding="utf-8")


#: Escape hatch: list EVERY transcript on the machine, the way this endpoint did
#: before the scoping below. For diagnosing "where did my chat go", never for normal
#: use -- an unscoped list is the bug this constant exists to be able to reproduce.
SESSION_LIST_UNSCOPED = os.environ.get("SUTRA_UI_ALL_CHATS", "") == "1"


def _owned_transcripts():
    """(mtime, source, id, path) for every transcript a SUTRA chat claims, newest first.

    chat_store's reverse index is the whole definition of "a Sutra chat" and there is no
    second one: every chat sent through this panel is bound to a sutra_id on its first
    turn (ws_chat calls chat_store.create/resolve, then switch.confirm, which reindexes),
    so a transcript with no row in that index was written by something else.

    RESOLVED, NOT SCANNED. The obvious shape -- page through list_sessions and drop the
    rows that do not match -- costs a title parse for every transcript it walks past, and
    on the founder's disk (20,255 transcripts, one of them his) that measured 3.5-5s per
    rail refresh for a single row. This asks the opposite question: it takes the handful of
    ids the index names and goes straight to their files. session_reader.index() is the one
    glob, it is STAT-ONLY (0.11s for those 20,255), and it is already what the transcript
    watcher polls every second -- so nothing here is a new kind of read. Cost is flat in
    the number of chats the person actually has.

    Nothing is opened here. The caller parses titles for the ONE page it is about to
    return, which is what makes this cheap.
    """
    try:
        owned = chat_store.index() or {}
    except Exception:   # noqa: BLE001 -- an unreadable index must not empty the rail
        return []
    cands = []
    claude_ids = {k.split(":", 1)[1] for k in owned if k.startswith("claude:")}
    if claude_ids:
        disk = sr.index()          # stat-only, one glob of ~/.claude/projects
        for sid in claude_ids:
            rec = disk.get(sid)
            if not rec:
                continue           # claimed by a chat, no longer on disk
            f = sr.PROJECTS / rec["project"] / (sid + ".jsonl")
            try:
                cands.append((int(f.stat().st_mtime), "claude", sid, f))
            except OSError:
                continue           # removed between the glob and here
    # The other two trees have their own layouts and no cheap whole-tree index, but they
    # are also a handful of rows: resolve each claimed id on its own. read_resolve_path is
    # the read-only resolver that spans all three trees (never resolve_path, which the
    # write paths share).
    for key in owned:
        provider, _, sid = key.partition(":")
        if provider == "claude" or not sid:
            continue
        f = sr.read_resolve_path(sid)
        if f is None:
            continue
        try:
            cands.append((int(f.stat().st_mtime), provider, sid, f))
        except OSError:
            continue
    cands.sort(key=lambda c: c[0], reverse=True)
    return cands


def _session_row(source, path, project_cwd):
    """One transcript in the shape list_sessions returns, whichever tree it is in.

    These are session_reader's own per-tree readers, the same three list_sessions calls
    in its own window loop -- reached directly because this endpoint picks its window by
    id rather than by position. Private, and deliberately so: they are the read half of a
    module whose write half must never be pointed at another vendor's tree.
    """
    if source == "claude":
        return sr._claude_session_meta(path)
    if source == "codex":
        return sr._codex_session_meta(path)
    return sr._gemini_session_meta(path, project_cwd)


@app.get("/api/sessions")
def api_sessions(limit: int = 100, offset: int = 0):
    """One page of SUTRA'S OWN chats, newest first. `offset` walks back into history
    so the panel can fetch more as it scrolls; a page shorter than `limit` means the
    end.

    SUTRA'S OWN, AND THAT IS THE POINT (owner, 2026-09-09). session_reader.list_sessions
    enumerates every transcript on the machine -- ~/.claude/projects/*/*.jsonl plus the
    codex and deepseek trees -- because it is also the reader behind "open this id" and
    has to be able to see everything. This endpoint is not that: it fills the app's own
    Chats folder, and it was handing that folder every conversation the founder had ever
    had in VS Code, in a terminal, or in any other tool that writes to the same directory.
    Measured on his disk: 20,255 transcripts listed, one of which was a Sutra chat. They
    are not Sutra's chats and he does not want them in Sutra's list.

    Scoped HERE rather than in session_reader because list_sessions is shared with the id
    resolvers, which must keep seeing every file -- a chat opened by id, or reached by a
    provider switch, still resolves exactly as it did. SUTRA_UI_ALL_CHATS=1 puts the old
    unscoped list back for diagnosis.

    EACH ROW ALSO CARRIES THE SUTRA CHAT IT BELONGS TO, and that is what makes a
    provider switch survive a refresh. The browser holds `sutra_id` in memory
    only, so a reload loses it; the pane then reconnects with no ?sutra=, and
    ws_chat's chat-local step (_chat_local_provider) is keyed entirely on that
    parameter -- it returns immediately on an empty one and never reads the
    record that holds the answer. Resolution fell through to the GLOBAL default,
    so a chat switched to Codex came back on Claude, and the in-loop seed
    recovery then found the chat too late to change the provider and performed a
    real Codex -> Claude carry-over instead. Measured live: "OpenAI Codex ->
    Claude Code, turns 1-2 carried over" on a chat nobody had asked to move.

    chat_store.resolve() is the existing reverse-index lookup and is used as-is:
    it answers exactly "which chat owns this provider-native session id", which
    is the question a rail row raises. No second mapping is introduced, and a
    row whose id belongs to no chat simply carries None.
    """
    limit = max(0, int(limit or 0))
    offset = max(0, int(offset or 0))
    if SESSION_LIST_UNSCOPED:
        rows = sr.list_sessions(limit, offset)
    else:
        window = _owned_transcripts()[offset:offset + limit]
        # Built only for the page being returned, and only when a row needs it.
        project_cwd = (sr._gemini_project_cwd_map()
                       if any(src == "deepseek" for _, src, _, _ in window) else {})
        rows = []
        for _mtime, source, _sid, path in window:
            try:
                row = _session_row(source, path, project_cwd)
            except OSError:
                row = None         # deleted while this page was being built
            if row is not None:
                rows.append(row)
    for row in rows:
        try:
            row["sutra_id"] = chat_store.resolve(row.get("source"), row.get("id"))
        except Exception:   # noqa: BLE001 -- a bad index must not empty the rail
            row["sutra_id"] = None
    return rows


@app.get("/api/sessions/stream")
async def api_sessions_stream():
    async def gen():
        prev = {}
        first = True
        last_beat = time.time()
        while True:
            try:
                cur = sr.index()
            except Exception:
                # A read error must not kill the stream: the panel would fall back
                # to boot-only behaviour silently, which is the bug this fixes.
                await asyncio.sleep(SESSION_POLL_S)
                continue

            if first:
                # The opening frame is the whole index, so a panel that connects
                # late is immediately correct rather than correct-from-now-on.
                yield _sse_event("sync", {"sessions": [
                    dict(id=k, **v, live=sr.liveness(v["mtime"])) for k, v in cur.items()]})
                first = False
            else:
                changed = [dict(id=k, **v, live=sr.liveness(v["mtime"]))
                           for k, v in cur.items()
                           # SIZE as well as mtime: a transcript can be appended to
                           # twice inside one second, and mtime alone would report
                           # the first write and swallow the second.
                           if k not in prev or prev[k]["mtime"] != v["mtime"]
                           or prev[k]["size"] != v["size"]
                           # A subagent write leaves the PARENT's own size
                           # untouched, and mtime is int seconds -- two writes in
                           # one second are swallowed. agents_bytes moves on every
                           # subagent append, so it is what makes the fold in
                           # session_reader.index() actually reach the client.
                           or prev[k].get("agents_bytes") != v.get("agents_bytes")]
                gone = [k for k in prev if k not in cur]
                if changed:
                    yield _sse_event("changed", {"sessions": changed})
                if gone:
                    yield _sse_event("vanished", {"ids": gone})
                # Liveness decays with the clock, not with writes -- a session that
                # stops being written goes active -> idle on its own, and nothing
                # would ever say so without a tick.
                if time.time() - last_beat >= SESSION_HEARTBEAT_S:
                    last_beat = time.time()
                    yield _sse_event("tick", {"now": int(time.time())})
            prev = cur
            await asyncio.sleep(SESSION_POLL_S)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",      # nothing may buffer an event stream
    })


def _sse_event(event: str, data: dict) -> str:
    """A NAMED SSE frame.

    Deliberately not called `_sse`: this module already had one, defined further
    down for the log tail, whose signature is a single row and which emits an
    unnamed `data:` frame. Two functions with one name is a silent overwrite --
    the later definition won, every call here passed two arguments to a
    one-argument function, and the stream died on its opening frame with the
    panel simply never receiving anything.
    """
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data))


@app.get("/api/sessions/{sid}")
def api_session(sid: str):
    data = sr.read_session(sid)
    if data is None:
        raise HTTPException(status_code=404, detail="session not found")
    return data


@app.post("/api/sessions/{sid}/rename")
def api_session_rename(sid: str, body: dict):
    title = (body or {}).get("title", "")
    if not sr.append_title(sid, title):
        raise HTTPException(status_code=404, detail="session not found, or the title was empty")
    return {"ok": True, "title": str(title).replace("\n", " ").strip()[:200], "title_source": "custom"}


@app.post("/api/sessions/{sid}/archive")
def api_session_archive(sid: str):
    r = sr.relocate(sid, "archive")
    if r is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, **r}


@app.post("/api/sessions/{sid}/delete")
def api_session_delete(sid: str):
    r = sr.relocate(sid, "trash")
    if r is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, **r}


@app.post("/api/sessions/{sid}/reveal")
def api_session_reveal(sid: str):
    if sys.platform != "darwin":
        raise HTTPException(status_code=400, detail="reveal in Finder is macOS-only")
    p = sr.resolve_path(sid)
    if p is None:
        raise HTTPException(status_code=404, detail="session not found")
    subprocess.run(["open", "-R", str(p)], check=False)
    return {"ok": True}


@app.get("/api/sessions/{sid}/agents")
def api_session_agents(sid: str):
    """Subagent transcripts spawned under one session.

    Read-only. Fails OPEN to [] -- a session with no fan-out is the common case and
    must render an empty fold, not an error. sid is validated inside session_reader
    (guarded, glob-only, never joined onto a path).
    """
    return sr.list_agents(sid)


@app.get("/api/sessions/{sid}/agents/{aid}")
def api_session_agent(sid: str, aid: str):
    """One subagent transcript, same {id,cwd,branch,messages} shape as GET
    /api/sessions/{sid}. 404 when the id resolves to nothing under the parent's
    subagents dir -- mirrors api_session, and is what makes traversal a miss
    rather than a leak."""
    data = sr.read_agent(sid, aid)
    if data is None:
        raise HTTPException(status_code=404, detail="agent transcript not found")
    return data


@app.get("/api/activity")
def api_activity() -> dict:
    """Everything running right now, for the global Activity panel. Read-only.

    Two kinds of live work: a chat TURN in flight (Sutra spawns a `claude`
    process per turn, so a session whose transcript is being written this
    instant IS a running background process), and a subagent AGENT. "Running"
    is transcript liveness == "active" -- the SAME rule the SSE stream and the
    log tail already use, not a new definition. elapsed_s is best-effort: now
    minus the last write (mtime). Stat-cheap and safe to poll every ~2s: the
    per-agent parse is paid only for sessions index() already flagged as having
    a live agent (agents_live), so idle history costs nothing.
    """
    now = time.time()
    idx = sr.index()
    turns = []
    agents = []
    for sid, rec in idx.items():
        if sr.liveness(rec["mtime"], now) == "active":
            meta = sr.head_meta(sid)
            turns.append({
                "sid": sid,
                "title": meta.get("title", ""),
                "cwd": meta.get("cwd", ""),
                "elapsed_s": max(0, int(now - rec["mtime"])),
            })
        if rec.get("agents_live"):
            for a in sr.list_agents(sid):
                if not a.get("running"):
                    continue
                agents.append({
                    "parent_sid": sid,
                    "id": a["id"],
                    "label": a.get("label", ""),
                    "elapsed_s": max(0, int(now - a["mtime"])),
                })
    return {"turns": turns, "agents": agents, "count": len(turns) + len(agents)}


@app.get("/api/balance")
def api_balance() -> dict:
    """Balance state contract, read-only (2026-08-07).

    Fixed directory — no path parameters, so no traversal surface. Resolution:
    SUTRA_UI_BALANCE_DIR env, else the asawa-holding checkout four levels up
    (sutra is a submodule there). A provisioned .app copy has neither, and the
    honest answer is {present: false} — the panel renders its design preview
    then, never a fabricated measurement. Errors never leak filesystem paths.
    """
    import time as _time

    bdir = os.environ.get("SUTRA_UI_BALANCE_DIR") or str(
        HERE.parent.parent.parent.parent / "holding" / "state" / "balance")
    state_p = Path(bdir) / "balance-state.json"
    log_p = Path(bdir) / "balance-log.jsonl"

    def _read(name):
        """Fail-soft read of one balance artifact — None when absent/corrupt."""
        try:
            return json.loads((Path(bdir) / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    # The nightly UI read model + the roles review are read INDEPENDENTLY of the
    # observer snapshot (consult P1 2026-08-18): a missing/half-written
    # balance-state.json must not silently hide the approved dashboard design.
    view = _read("dashboard-data.json")
    review = _read("roles-review.json")
    snap = _read("balance-state.json") if state_p.exists() else None
    if snap is None and view is None:
        return {"present": False}
    if snap is None:
        # Design present, observer snapshot not yet — the panel renders the
        # nightly tabs and says so, rather than falling back to a sample.
        return {"present": True, "state": {}, "today": [], "view": view, "review": review}
    today = []
    lt = _time.localtime()
    day_start = int(_time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))
    try:
        with open(log_p, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2_000_000))
            for line in f.read().decode("utf-8", "replace").splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a bad line is skipped, never a 500
                if isinstance(row.get("epoch"), (int, float)) and row["epoch"] >= day_start:
                    today.append(row)
    except OSError:
        pass
    # Actionables read model (PLAN-25 step 9): the coach's derived view, if
    # the nightly pass has produced one. Absent/corrupt = key omitted, not 500.
    out = {"present": True, "state": snap, "today": today[-96:],
           "view": view, "review": review}
    derived = _read("actionables.json")
    if derived:
        out["actionables"] = derived.get("actionables", [])
        out["max_active"] = derived.get("max_active")
        out["profile_warnings"] = derived.get("profile_warnings", [])
    return out


# Fixed drop reasons — one click each in the panel, no typing. "Doesn't matter"
# is the founder's own phrase for this control and stays first.
DROP_REASONS = ("doesnt-matter", "not-now", "handled-elsewhere", "coach-wrong")


@app.post("/api/balance/actionable")
def api_balance_actionable(body: dict, request: Request) -> dict:
    """Append ONE coach-ledger event for an actionable (PLAN-25 step 10).

    Desktop-only write: requires x-sutra-desktop-token matching the env token
    the Electron shell minted — ALWAYS (403 when the env token is absent; a
    CLI-run server is read-only here). The renderer never sees the token: the
    panel calls window.sutra.markActionable, and the shell's main process
    attaches the header (same doctrine as preload.js — "the token never
    reaches here"). Consult folds 2026-08-18: no unauth fallback; flock'd
    ledger-read + single O_APPEND write for idempotency; schema whitelists.
    """
    import fcntl
    import hmac as _hmac
    import re as _re
    import time as _time

    env_token = os.environ.get("SUTRA_DESKTOP_TOKEN", "")
    got = request.headers.get("x-sutra-desktop-token", "")
    if not env_token or not got or not _hmac.compare_digest(env_token, got):
        raise HTTPException(status_code=403, detail="desktop-only write")

    aid = str((body or {}).get("id", ""))
    op = (body or {}).get("op", "")
    note = str((body or {}).get("note", "") or "")
    reason = str((body or {}).get("reason", "") or "")
    if op not in ("done", "drop", "movement"):
        raise HTTPException(status_code=422, detail="op must be done|drop|movement")
    if not _re.fullmatch(r"[a-z0-9-]{1,64}", aid):
        raise HTTPException(status_code=422, detail="bad id")
    if len(note) > 200:
        raise HTTPException(status_code=422, detail="note too long (200 max)")
    # A drop must say WHY (consult fold 2026-08-18, both lanes converged): the
    # founder's word closes an item, but a why-less drop leaves the ledger
    # proving only that something uncomfortable was dismissed — not whether the
    # coach was wrong, the item expired, or it was handled elsewhere. FIXED
    # reasons, never free text: a required essay would defeat the one-click ask.
    if op == "drop" and reason not in DROP_REASONS:
        raise HTTPException(status_code=422,
                            detail="drop needs reason: " + "|".join(DROP_REASONS))

    bdir = os.environ.get("SUTRA_UI_BALANCE_DIR") or str(
        HERE.parent.parent.parent.parent / "holding" / "state" / "balance")
    ledger = Path(bdir) / "coach-ledger.jsonl"
    if not ledger.exists():
        raise HTTPException(status_code=404, detail="no coach ledger")

    lock_p = Path(bdir) / "coach-ledger.lock"
    with open(lock_p, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            born, closed_as = False, None
            with open(ledger, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("id") != aid:
                        continue
                    if e.get("event") == "born":
                        born = True
                    elif e.get("event") in ("done", "dropped"):
                        closed_as = e["event"]
            if not born:
                raise HTTPException(status_code=404, detail="unknown actionable")
            # Terminal is terminal, for EVERY verb (consult fold: the earlier
            # code short-circuited only `done`, so a second drop would have
            # appended a duplicate closing row). A stale-UI race stays boring —
            # 200 with the prior state, never a 409, and `closed_as` so the
            # client can say what actually happened instead of guessing.
            if closed_as:
                return {"ok": True, "already": True, "closed_as": closed_as}
            row = {"ts": int(_time.time()),
                   "event": "dropped" if op == "drop" else op,
                   "id": aid, "by": "founder-ui"}
            if op == "drop":
                row["reason"] = reason
            if note:
                row["note"] = note
            data = (json.dumps(row) + "\n").encode("utf-8")
            fd = os.open(ledger, os.O_WRONLY | os.O_APPEND)
            try:
                os.write(fd, data)  # single write, one line, <4KB
            finally:
                os.close(fd)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    return {"ok": True, "already": False}


@app.get("/api/evals")
def api_evals() -> dict:
    """Verifier/Evals read model (2026-08-08, VERIFIER-LEDGER V-35/V-36).

    Same posture as /api/balance: fixed directories, no path parameters, no
    traversal surface; a provisioned copy without the asawa-holding checkout
    answers {present: false} and the panel says so — never a fabricated
    scorecard. Sources: check registry (holding/state/verifier/registry.jsonl),
    nightly run summaries (holding/plans/eval-program/runs/*.json, latest two
    for the regression strip), findings tail. Errors never leak paths.
    """
    root = Path(os.environ.get("SUTRA_UI_EVALS_ROOT")
                or HERE.parent.parent.parent.parent)
    reg_p = root / "holding" / "state" / "verifier" / "registry.jsonl"
    runs_d = root / "holding" / "plans" / "eval-program" / "runs"
    findings_p = root / "holding" / "observability" / "eval-nightly" / "findings.jsonl"
    if not reg_p.exists():
        return {"present": False}

    by_status: dict = {}
    active_by_scope: dict = {}
    checks = []
    try:
        # bounded read (codex V3): a runaway registry must not become a
        # memory/latency hole in the panel server — 16MB / 10k lines cap
        if reg_p.stat().st_size > 16_000_000:
            return {"present": False}
        for n, line in enumerate(reg_p.read_text(encoding="utf-8").splitlines()):
            if n >= 10_000:
                break
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
            if r.get("status") == "active":
                active_by_scope[r.get("scope", "?")] = active_by_scope.get(r.get("scope", "?"), 0) + 1
            checks.append({
                "check_id": r.get("check_id"),
                "scope": r.get("scope"),
                "status": r.get("status"),
                "tag": r.get("tag"),
                "goal": (r.get("goal") or "")[:120],
                "reason": (r.get("reason") or "")[:120],
                "superseded_by": r.get("superseded_by"),
            })
    except OSError:
        return {"present": False}

    def _cases(run) -> list:
        """Well-formed case dicts only — a malformed artifact degrades to
        'not counted', never to a 500 (codex V3)."""
        if not isinstance(run, dict) or not isinstance(run.get("cases"), list):
            return []
        return [c for c in run["cases"] if isinstance(c, dict) and c.get("id")]

    runs = []
    try:
        # decay runner writes <unix-ts>.json; other artifacts (spike reports,
        # diffs) share the dir — numeric-stem filter keeps them out of the
        # scorecard (a grader spike is not a decay run)
        paths = sorted((p for p in runs_d.glob("*.json") if p.stem.isdigit()),
                       key=lambda p: int(p.stem), reverse=True)[:2]
        for p in paths:
            try:
                if p.stat().st_size <= 8_000_000:
                    runs.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    latest = runs[0] if runs else None
    prev = runs[1] if len(runs) > 1 else None
    regressions, fixed = [], []
    if latest is not None and prev is not None:
        prev_pass = {c["id"] for c in _cases(prev) if c.get("score") == "C"}
        prev_fail = {c["id"] for c in _cases(prev) if c.get("score") != "C"}
        for c in _cases(latest):
            if c.get("score") != "C" and c["id"] in prev_pass:
                regressions.append(c["id"])
            if c.get("score") == "C" and c["id"] in prev_fail:
                fixed.append(c["id"])
    scorecard = None
    if latest is not None:
        cases = _cases(latest)
        scorecard = {
            "ts": latest.get("ts") if isinstance(latest, dict) else None,
            "scored": len(cases),
            "pass": sum(1 for c in cases if c.get("score") == "C"),
            "fail": sum(1 for c in cases if c.get("score") != "C"),
            "failing_ids": [c["id"] for c in cases if c.get("score") != "C"][:40],
        }

    findings = []
    try:
        if findings_p.exists():
            # seek-tail like /api/balance — never read a large log whole
            with open(findings_p, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 262_144))
                tail = f.read().decode("utf-8", "replace").splitlines()[-20:]
            for line in tail:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        findings.append(row)
                except ValueError:
                    pass
    except OSError:
        pass

    # Deep transcripts live in Inspect's own viewer; the panel hands the
    # operator the exact command instead of spawning servers from this app
    # (spawn would widen the hardened surface for no gain).
    view_cmd = ("cd " + "holding/plans/eval-program/impl && "
                ".venv/bin/inspect view --log-dir ../logs")

    return {
        "present": True,
        "registry": {"by_status": by_status, "active_by_scope": active_by_scope},
        "scorecard": scorecard,
        "regressions": regressions,
        "fixed": fixed,
        "checks": checks[:400],
        "findings": findings,
        "view_cmd": view_cmd,
    }


@app.get("/api/state")
def state() -> dict:
    base = lr.BASE / ".claude"
    out = {}
    for name in STATE_MARKERS:
        p = base / name
        out[name] = p.read_text(encoding="utf-8").strip() if p.exists() else None
    return out


@app.get("/api/logs/{source}")
def logs(source: str, n: int = 50):
    try:
        path = lr.resolve(source)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown source")
    return lr.read_tail(path, n)


def _sse(row: dict) -> str:
    return "data: " + json.dumps(row) + "\n\n"


@app.get("/sse/{source}")
async def sse(source: str):
    try:
        path = lr.resolve(source)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown source")

    async def gen():
        # 1) backlog
        for row in lr.read_tail(path, 50):
            yield _sse(row)
        yield ": backlog-end\n\n"
        # 2) live tail — poll, survive truncation, buffer partial lines
        offset = path.stat().st_size if path.exists() else 0
        buf = b""
        while True:
            await asyncio.sleep(0.5)
            if not path.exists():
                continue
            size = path.stat().st_size
            if size < offset:          # truncated / rotated -> reset
                offset, buf = 0, b""
            if size > offset:
                with path.open("rb") as f:
                    f.seek(offset)
                    chunk = f.read()
                    offset = f.tell()
                buf += chunk
                parts = buf.split(b"\n")
                buf = parts.pop()       # last element = partial remainder, keep buffering
                for raw in parts:
                    row = lr.parse(raw.decode("utf-8", "replace"))
                    if row is not None:
                        yield _sse(row)

    return StreamingResponse(gen(), media_type="text/event-stream")


# --------------------------------------------------------------- shadow say --
# PLAN-100 S37. Capability token first (dual-lane fold, 2026-08-25): a local
# HTTP port is reachable by every same-user process, and mission_id is
# attribution, not authorization. The token is minted per app boot and travels
# to Shadow's MCP child via the spawn env; nothing else knows it. It is
# checked BEFORE flag/session/mission so an unauthorized caller learns
# nothing (no oracle).
# In APP MEMORY ONLY (codex P1 fold): a global env write leaked the token
# into every chat pane's spawned agent. Shadow's own session receives it via
# its spawn env overlay -- nothing else can present it.
SHADOW_SAY_TOKEN = _secrets.token_hex(24)


# ------------------------------------------------------------ shadow chat --
# PLAN-100 P5: ONE Shadow conversation. The overlay card and the Focus home
# are two views of this channel. Lazy: the first message boots the session;
# the flag off means 403 and no process ever exists.
import shadow_session as _shadow_session

_SHADOW = {"session": None}
_SHADOW_LOCK = asyncio.Lock()   # boot + turn serialization (codex P2 fold)


#: Providers the Shadow path can actually drive. NOT providers.ADAPTERS: that
#: set answers "can a CHAT PANE run this", and a pane has two transports
#: (SessionRuntime for Claude, AcpRuntime for DeepSeek) selected by ws_chat.
#: Shadow has one -- build_agent_args + SessionRuntime + demux_turn -- so its
#: answer is narrower. Adding an id here without building the transport for it
#: is exactly the bug the guard below closes.
SHADOW_PROVIDERS = frozenset({"claude"})


def _shadow_args():
    detail = providers.active_provider_detail()
    prov = providers.provider_by_id(detail["id"]) if detail["id"] else None
    if not prov or not prov.get("bin_path"):
        raise HTTPException(503, "no usable provider for Shadow")
    # REFUSE, rather than hand another vendor's CLI Claude's flags (2026-09-03).
    # This resolved the ACTIVE provider's binary and then unconditionally built
    # Claude's argv below (-p, --input-format stream-json, --permission-mode
    # plan). With `provider: deepseek` selected, Shadow's own boot AND every
    # delegate spawn ran `deepseek -p --input-format stream-json ...`, which
    # that CLI rejects at its argv parser -- surfacing as "shadow could not
    # boot" / "delegate session failed to boot" with a parse error attached.
    # The operator reads that as a broken Shadow; nothing in it points at the
    # provider selector, which is the one thing that would fix it.
    #
    # ws_chat has branched on active_id since the ACP wiring; this path never
    # did. SHORT-TERM ON PURPOSE: the honest refusal is not the ACP delegate
    # path. That is separate work -- AcpRuntime + session/new (plan mode is a
    # session mode there, not a flag) + DEEPSEEK_API_KEY in the spawn env + a
    # prompt_turn pump in shadow_runner.spawn_delegate_session, whose Claude
    # path test_shadow_delegate.py now pins. When it lands, it replaces this.
    if prov["id"] not in SHADOW_PROVIDERS:
        raise HTTPException(503,
            "Shadow and its delegates run on Claude only in this build; the "
            "active provider is %r (%s). Switch to Claude to use Shadow -- "
            "chat panes still run %s." % (prov["id"], prov["name"],
                                          prov["name"]))
    return build_agent_args(prov["bin_path"], "", "plan", stream_input=True)


def _shadow_workdir_for_delegates():
    """Delegates work where the founder works (their objectives point at the
    real repo), but in PLAN mode -- reads and plans, no writes until granted."""
    settings = providers.load_settings()
    return settings.get("workdir") or WORKDIR


def _shadow_workdir():
    """Shadow's OWN workdir (live fix 2026-08-25): booting in the founder's
    repo made the session load that repo's entire governance stack -- 40s+
    turns and replies drowned in per-turn blocks. An empty home keeps the
    persona pure (SHADOW.md is the only context) and turns fast."""
    import shadow_ledger
    d = os.path.join(os.path.dirname(shadow_ledger._path("actions")),
                     "..", "workdir")
    d = os.path.realpath(d)
    os.makedirs(d, exist_ok=True)
    return d


def _scoped_instructions(scope_id):
    """The confirmed rules that belong to ONE chat, as a labeled block.
    Empty string when that chat has taught Shadow nothing."""
    if not scope_id:
        return ""
    try:
        import shadow_ledger
        block = shadow_precedence.replay_context(
            shadow_ledger.read_latest("instructions"),
            scope="chat", scope_id=scope_id)
        # replay_context always emits the floors line; a scope with no
        # rules of its own must not ship a bare floors block
        body = [ln for ln in block.split("\n") if ln.startswith("[")]
        if not body:
            return ""
        return ("\n\nRULES FOR THIS CHAT ONLY (founder-confirmed; they "
                "apply while you work on it):\n" + "\n".join(body))
    except Exception:
        return ""


def _delegate_manifest(mission):
    """ONE manifest composer (was three copies). Scoped rules are folded
    in AT SPAWN TIME, never baked into the mission record -- a revoked
    rule must not re-fire on retry."""
    base = mission.get("manifest") or (
        "You are a delegate session working for the founder via Shadow. "
        "Objective: %s. Work step by step; state DONE-CHECK lines when "
        "checks pass." % mission["objective"])
    return base + _scoped_instructions(mission.get("target_session"))


async def _default_delegate_spawner(mission):
    """Registered with the runner so PROMOTED queued missions (whose
    originating request is long gone) can still get a delegate."""
    return await shadow_runner.spawn_delegate_session(
        _shadow_args, _shadow_workdir_for_delegates(),
        _delegate_manifest(mission), register_runtime)


@app.on_event("startup")
async def _deepseek_pairing_code():
    """Print the one-time DeepSeek sign-in code, when this process offers one.

    HERE AND NOT AT IMPORT. The test suites import app.py in-process, and a
    module-level mint would put a code in every one of them and print it into
    their output. A startup hook fires once, only when a server is actually
    serving.

    deepseek_session.arm() decides whether to mint at all -- it declines when
    SUTRA_DESKTOP_TOKEN is set, because the Electron shell already owns the
    key-writing channel and a second door would exist for no reason.
    """
    import deepseek_session
    deepseek_session.arm()
    deepseek_session.print_banner()


@app.on_event("startup")
async def _shadow_recover():
    if providers.shadow_enabled():
        try:
            shadow_runner.recover_on_boot()
        except Exception:
            pass
        try:
            shadow_runner.start_stall_watch()
        except Exception:
            pass
        try:
            shadow_runner.set_default_provisioner(_default_delegate_spawner)
        except Exception:
            pass


@app.on_event("shutdown")
async def _shadow_shutdown():
    try:
        shadow_runner.shutdown()
    except Exception:
        pass


def _shadow_alert_count():
    """New rescue/stall/needs-decision feed items -- the dot pill number."""
    import shadow_feed
    count = 0
    try:
        with open(shadow_feed._feed_path(), encoding="utf-8") as handle:
            for line in handle:
                try:
                    it = json.loads(line)
                except ValueError:
                    continue
                iid = it.get("item_id") or ""
                if it.get("state") == "new" and (
                        it.get("kind") == "needs_decision"
                        or iid.startswith("rescue-")
                        or iid.startswith("stall-")):
                    count += 1
    except OSError:
        pass
    return count


@app.get("/api/shadow/status")
async def api_shadow_status():
    """The dot reads this: watching (green) / not (grey). Never 500s -- a
    down Shadow is a STATE the UI renders, not an error."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    sess = _SHADOW["session"]
    return {"watching": bool(sess and sess.alive),
            "session": sess.session_id if sess else None,
            "permission_mode": "plan",
            "active_missions": shadow_runner.active_mission_count(),
            "alerts": _shadow_alert_count()}


@app.post("/api/shadow/chat")
async def api_shadow_chat(request: Request):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be json")
    msg = (body.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "message required")
    # v10: the tab the founder is typing in. Scope rides the TURN, not the
    # process -- one Shadow session serves every tab.
    scope_id = (body.get("scope_id") or "").strip() or None
    async with _SHADOW_LOCK:
        sess = _SHADOW["session"]
        if sess is None or not sess.alive:
            sess = _shadow_session.ShadowSession()
            booted = await sess.start(
                _shadow_args, _shadow_workdir(),
                extra_env={"SUTRA_SHADOW_SAY_TOKEN": SHADOW_SAY_TOKEN})
            if booted is None:
                raise HTTPException(503, "shadow could not boot")
            _SHADOW["session"] = sess
        tokens = []

        async def collect(frame):
            if frame.get("type") == "token":
                tokens.append(frame.get("text") or "")

        # the scoped preamble is sent ONCE per (scope, rules) pair: a
        # tab switch or a new rule re-arms it, an ordinary next message
        # does not repeat it
        pre = ""
        if scope_id:
            scoped = _scoped_instructions(scope_id)
            stamp = "%s:%s" % (scope_id, hash(scoped))
            if getattr(sess, "scope_stamp", None) != stamp:
                sess.scope_stamp = stamp
                pre = ("[Context] You are now talking about the chat %s."
                       % scope_id) + scoped + "\n\n"
        elif getattr(sess, "scope_stamp", None) is not None:
            sess.scope_stamp = None
            pre = ("[Context] Back to general talk -- no single chat is "
                   "in focus.\n\n")
        await sess.rt.send_user_frame(pre + msg)
        (sess.session_id, _t, got_result,
         err, _e) = await sess.rt.demux_turn(collect, sess.session_id)
    if err:
        raise HTTPException(502, "shadow turn failed: %s" % err[:200])
    raw = "".join(tokens)
    display, blocks = shadow_protocol.parse_reply(raw)
    out = {"reply": display, "session": sess.session_id,
           "watching": sess.alive, "scope_id": scope_id}
    if "chips" in blocks:
        out["chips"] = blocks["chips"]
    if "mission" in blocks:
        mspec = blocks["mission"]
        store = _mission_engine.MissionStore()
        try:
            m = store.create(mspec["objective"], mspec["template"],
                             target_mode=mspec.get("target_mode") or "existing",
                             target_session=mspec.get("target_session"),
                             done_when=mspec.get("done_when"),
                             manifest=mspec.get("manifest"))
            store.transition(m["id"], "brief_confirm", "proposed in chat")
            out["mission"] = store.load(m["id"])
        except ValueError:
            pass                      # invalid proposal: reply text stands
    if "remember" in blocks:
        import shadow_ledger
        # the SECOND ledger writer: without this stamp, an instruction
        # Shadow captures inside a chat tab would land GLOBAL
        row = shadow_ledger.append("instructions", {
            "text": blocks["remember"]["text"][:1000],
            "precedence": blocks["remember"]["precedence"],
            "confirmed": False,
            "scope": "chat" if scope_id else "global",
            "scope_id": scope_id or None,
            "source_thread": sess.session_id})
        out["remembered"] = row
    return out


# ------------------------------------------------- shadow home endpoints --
# PLAN-100 P6. All flag-gated. Instructions and watches are ledgered, never
# deleted: a revoked instruction stays on the record as inert history
# (archive-never-delete), and a watch toggle is an auditable act.
import mission_engine as _mission_engine
import shadow_precedence
import shadow_runner
import shadow_protocol


@app.get("/api/shadow/instructions")
async def api_shadow_instructions(request: Request):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_ledger
    out = sorted(shadow_ledger.read_latest("instructions"),
                 key=shadow_precedence.rank_key)
    for r in out:                        # explicit scope for every row
        r.setdefault("scope", shadow_precedence.row_scope(r))
    want = request.query_params.get("scope") if request else None
    want_id = request.query_params.get("scope_id") if request else None
    if want:
        out = [r for r in out if r.get("scope") == want
               and (want != "chat" or not want_id
                    or r.get("scope_id") == want_id)]
    return {"instructions": out}


@app.post("/api/shadow/instructions")
async def api_shadow_instruction_write(request: Request):
    """capture (unconfirmed=inert) / confirm / revoke -- one endpoint,
    action field decides; every action is one more ledger row."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_ledger
    body = await request.json()
    action = body.get("action")
    if action == "capture":
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, "text required")
        # v10: scope is explicit on every NEW row. An unknown scope is a
        # 400, never a silent global (a mis-typed scope must not leak a
        # per-chat rule into every reply).
        scope = (body.get("scope") or "global").strip()
        scope_id = (body.get("scope_id") or "").strip() or None
        if scope not in ("global", "chat"):
            raise HTTPException(400, "scope must be global|chat")
        if scope == "chat" and not scope_id:
            raise HTTPException(400, "scope_id required for scope=chat")
        row = shadow_ledger.append("instructions", {
            "text": text[:1000],
            "precedence": body.get("precedence") or "history",
            "confirmed": False,
            "scope": scope,
            "scope_id": scope_id,
            "source_thread": body.get("source_thread")})
        return row
    if action in ("confirm", "revoke"):
        iid = body.get("id") or ""
        rows = [r for r in shadow_ledger.read_latest("instructions")
                if r.get("id") == iid]
        if not rows:
            raise HTTPException(404, "no instruction %s" % iid)
        row = dict(rows[-1])
        if action == "confirm":
            row["confirmed"] = True
            row["confirmed_at"] = row.pop("ts", None)
        else:
            row["confirmed"] = False
            row["revoked_at"] = row.pop("ts", None)
        return shadow_ledger.append("instructions", row)
    raise HTTPException(400, "action must be capture|confirm|revoke")


@app.get("/api/shadow/settings")
async def api_shadow_settings():
    """The codified rules, one read: how Shadow engages, what it
    remembers (global and per chat), its attention, and the floors it
    cannot be talked out of. The ledger wearing a settings face."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_ledger
    try:
        rows = shadow_ledger.read_latest("instructions")
    except Exception:
        rows = []
    live = [r for r in rows
            if r.get("confirmed") and not r.get("revoked_at")]
    per_chat = {}
    for r in live:
        if shadow_precedence.row_scope(r) == "chat":
            per_chat.setdefault(r.get("scope_id") or "?", []).append(r)
    return {
        "engage": [
            "Answer with the outcome in the first line.",
            "One slow entrance, never a pulse.",
            "Opening a card retires it.",
        ],
        "global": [r for r in live
                   if shadow_precedence.row_scope(r) == "global"],
        "per_chat": per_chat,
        "attention": {
            "watching": sorted(_shadow_watches()),
            "off": sorted(_shadow_unwatched()),
            "alerts": _shadow_alert_count(),
        },
        "floors": [
            "destructive git operations",
            "external client repositories",
            "irreversible external sends",
        ],
    }


@app.get("/api/shadow/watches")
async def api_shadow_watches():
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    return {"watches": sorted(_shadow_watches())}


@app.post("/api/shadow/watches")
async def api_shadow_watch_toggle(request: Request):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_ledger
    body = await request.json()
    sid = (body.get("session_id") or "").strip()
    if not sid:
        raise HTTPException(400, "session_id required")
    watch = bool(body.get("watch"))
    shadow_ledger.append("actions", {
        "kind": "say" if False else ("resume" if watch else "stop"),
        "mission_id": None,
        "summary": ("watch " if watch else "unwatch ") + sid})
    watches = _shadow_watches()
    (watches.add if watch else watches.discard)(sid)
    _save_watches(watches)
    # explicit opt-out semantics (deepseek fold): unwatch remembers the
    # founder's choice against auto-watch; watch=true clears it
    unwatched = _shadow_unwatched()
    (unwatched.discard if watch else unwatched.add)(sid)
    _save_unwatched(unwatched)
    return {"watching": sorted(watches)}


def _unwatched_path():
    import shadow_ledger
    return os.path.join(os.path.dirname(shadow_ledger._path("actions")),
                        "..", "unwatched.json")


def _shadow_unwatched():
    try:
        with open(_unwatched_path(), encoding="utf-8") as handle:
            return set(json.load(handle))
    except (OSError, ValueError):
        return set()


def _save_unwatched(ids):
    with open(_unwatched_path(), "w", encoding="utf-8") as handle:
        json.dump(sorted(ids), handle)


def _shadow_auto_watch(sid):
    """Panes are watched by default (D68 spirit). Skips delegates (they are
    Shadow's own hands, not founder work) and explicit opt-outs; skips the
    write entirely when already listed (deepseek fold: no restart storms)."""
    if sid in shadow_runner.DELEGATES:
        return
    if sid in _shadow_unwatched():
        return
    watches = _shadow_watches()
    if sid in watches:
        return
    watches.add(sid)
    _save_watches(watches)


def _watches_path():
    import shadow_ledger
    return os.path.join(os.path.dirname(shadow_ledger._path("actions")),
                        "..", "watches.json")


def _shadow_watches():
    try:
        with open(_watches_path(), encoding="utf-8") as handle:
            return set(json.load(handle))
    except (OSError, ValueError):
        return set()


def _save_watches(watches):
    with open(_watches_path(), "w", encoding="utf-8") as handle:
        json.dump(sorted(watches), handle)


@app.post("/api/shadow/missions")
async def api_shadow_mission_create(request: Request):
    """GAP-AUDIT row 1: the delegate path. Shadow\'s proposal (or the
    founder\'s direct ask) creates a brief_confirm mission; Start is the
    founder\'s confirm + admit."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    objective = (body.get("objective") or "").strip()
    template = body.get("template") or "fix"
    if not objective:
        raise HTTPException(400, "objective required")
    store = _mission_engine.MissionStore()
    try:
        m = store.create(objective, template,
                         target_mode=body.get("target_mode") or "existing",
                         target_session=body.get("target_session"),
                         done_when=body.get("done_when"),
                         manifest=body.get("manifest"))
        store.transition(m["id"], "brief_confirm", "proposed")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return store.load(m["id"])


@app.get("/api/shadow/missions")
async def api_shadow_missions():
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    store = _mission_engine.MissionStore()
    return {"missions": store.list()}


@app.post("/api/shadow/missions/{mid}/act")
async def api_shadow_mission_act(mid: str, request: Request):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    action = body.get("action")
    store = _mission_engine.MissionStore()
    sched = _mission_engine.MissionScheduler(store)
    try:
        if action == "stop":
            return store.transition(mid, "stopped", "founder stop (home)")
        if action == "drop":
            return sched.cancel_queued(mid)
        if action == "start_now":
            async def _spawner(mission):
                return await shadow_runner.spawn_delegate_session(
                    _shadow_args, _shadow_workdir_for_delegates(),
                    _delegate_manifest(mission), register_runtime)
            # second-flight fix: never hold the request open across a
            # minutes-long provision -- background task, instant answer
            return shadow_runner.start_mission_async(
                mid, _validated_say, provisioner=_spawner)
        if action == "retry":
            clone = _mission_engine.clone_for_retry(store, mid)

            async def _respawner(mission):
                return await shadow_runner.spawn_delegate_session(
                    _shadow_args, _shadow_workdir_for_delegates(),
                    _delegate_manifest(mission), register_runtime)
            return shadow_runner.start_mission_async(
                clone["id"], _validated_say, provisioner=_respawner)
        if action == "confirm_check":
            return store.confirm_check(mid, int(body.get("index") or 0))
        if action == "resume":
            m = store.transition(mid, "running", "explicit resume (home)")
            shadow_runner._launch(mid, _validated_say, None)
            return m
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    raise HTTPException(400, "unknown action %r" % action)


@app.post("/api/shadow/feed/handle")
async def api_shadow_feed_handle(request: Request):
    """Opening a card retires it (observations pass 2026-08-26): the pill
    must stop counting things the founder has already looked at."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_feed
    body = await request.json()
    iid = (body.get("item_id") or "").strip()
    if not iid:
        raise HTTPException(400, "item_id required")
    return {"handled": shadow_feed.mark_handled(iid), "item_id": iid}


@app.get("/api/shadow/feed")
async def api_shadow_feed():
    """PLAN-100 S59: the needs-you feed, render-only. 403 when the flag is
    off -- the panel treats any non-200 as "render the placeholder", so the
    off state costs zero client logic."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_feed
    items = []
    try:
        with open(shadow_feed._feed_path(), encoding="utf-8") as handle:
            for line in handle:
                try:
                    it = json.loads(line)
                except ValueError:
                    continue
                if it.get("state") not in ("expired", "handled"):
                    items.append(it)
    except OSError:
        pass
    return {"items": items[-50:], "ts": time.time()}


def _validated_say(sid, mission_id, msg, dedupe_key=None):
    """The ONE say path (endpoint AND runner): every check or none."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    rt = lookup_runtime(sid)
    if rt is None:
        raise HTTPException(404, "no live runtime for session %s" % sid)
    import mission_engine as _me
    m = _me.MissionStore().load(mission_id)
    if m is None:
        raise HTTPException(404, "no such mission %s" % mission_id)
    if m["state"] != "running":
        raise HTTPException(409, "mission %s is %s, not running"
                            % (mission_id, m["state"]))
    if m.get("target_session") != sid:
        # STRICT binding (codex re-review P1): an unbound running mission
        # must not become a skeleton key over every pane.
        raise HTTPException(409, "mission %s is not bound to session %s"
                            % (mission_id, sid))
    if "never_say" in m.get("invariants", ()):
        raise HTTPException(403, "watch missions never speak")
    clean, redactions = shadow_egress.scrub(msg)
    tagged = "[Shadow \u00b7 mission %s] %s" % (mission_id, clean)
    ok = rt.turn_queue.put({"message": tagged, "_source": "shadow"},
                           source="shadow", dedupe_key=dedupe_key)
    if not ok:
        raise HTTPException(409, "duplicate say (dedupe key already accepted)")
    rt.queue_event.set()
    return {"queued": True, "redactions": redactions,
            "position": len(rt.turn_queue)}


@app.post("/api/sessions/{sid}/say")
async def api_session_say(sid: str, request: Request):
    if request.headers.get("x-shadow-say-token") != SHADOW_SAY_TOKEN:
        raise HTTPException(401, "missing or wrong say token")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be json")
    msg = (body.get("message") or "").strip()
    mission = (body.get("mission_id") or "").strip()
    if not msg or not mission:
        raise HTTPException(400, "message and mission_id are required")
    return _validated_say(sid, mission, msg, body.get("dedupe_key"))


def _seed_is_another_providers(seed, active_id, sutra_id):
    """True when THIS chat already records `seed` as a DIFFERENT provider's
    native session.

    The browser keeps ONE session id per pane -- 01-state.js:1455 writes
    s.claude_session from the `session` frame of whichever provider spoke last
    -- and hands it back as `resume`. Nothing in the id says who minted it, and
    the two spawn paths that consume it are credulous in opposite ways:

      claude    resolves ids in its own tree, so a foreign one fails the turn
                loudly and the dead-seed retry recovers it.
      codex     reports the id it was resumed WITH as its own thread.started id
                (measured, codex_runtime.py:522). A foreign id is therefore
                ACCEPTED IN SILENCE, and switch.confirm then writes it onto a
                codex segment -- a segment naming a session that does not exist
                in codex's tree at all. Measured on a live server: the bogus
                segment made active_segment() report codex, so every later
                plan() returned NOT_NEEDED and the chat could never carry over
                again. No error frame anywhere.

    So the id is checked against what the chat ALREADY KNOWS, using the reverse
    index chat_store maintains for exactly this kind of lookup rather than a
    second one invented here.

    DELIBERATELY NARROW. Only an id this chat records under another provider is
    refused. An UNRECORDED id -- a pane restored from the transcript rail, say
    (07-loaders.js:2244) -- behaves exactly as before, which is what keeps
    Claude's dead_seeds/retry machinery and DeepSeek's session/load fallback
    untouched. This closes the case where the chat itself contradicts the
    client, not every case where the client could be wrong.
    """
    if not (seed and sutra_id and active_id):
        return False
    for pid in chat_store.SEGMENT_PROVIDERS:
        if pid == active_id:
            continue
        try:
            if chat_store.resolve(pid, seed) == sutra_id:
                return True
        except Exception:   # noqa: BLE001 -- a bad index must not kill a turn
            continue
    return False


def _chat_local_provider(sutra_id):
    """The provider THIS CHAT is already running on, when it can still be run.

    THE CHAT-LOCAL PROVIDER IS NOT A NEW PIECE OF STATE. It is the provider of
    the chat's last segment -- `provider_history[-1]["provider"]`, written by
    switch.confirm() on every successful switch since piece 7. This function
    only READS it. Nothing here writes settings.json, and that is the whole
    point: a chat may run on Codex while the global default stays Claude.

    WHY THIS HAS TO EXIST AT ALL, and what was broken without it. The browser
    holds `sutra_id` in memory only (02-helpers.js:341), and claudeWsUrl sent
    no ?provider=, so EVERY reconnect resolved through active_provider_detail()
    -- the global default. A chat switched to Codex therefore reverted to
    Claude on the next connect, and because ?sutra= was still sent, switch.plan
    saw active_segment=codex against target=claude and REPLAYED THE ENTIRE
    CONVERSATION BACK TO CLAUDE. A silent un-switch that cost a full carry-over.
    Reading the chat's own record here is what makes the switch stick across a
    reload, a server restart, and a dropped socket.

    RUNNABLE IS RE-CHECKED, NOT ASSUMED. A provider that was ready when the
    segment was written can be uninstalled or signed out afterwards. Returning
    it anyway would push the failure down into the spawn, which is the exact
    failure mode providers.py was written to prevent. The one readiness
    mechanism is providers.provider_by_id(...)["runnable"] -- the same gate the
    ?provider= arm below applies, and the same one save_settings applies. No
    second notion of readiness is introduced here.

    Returns (provider_id, ignored) -- `ignored` is None unless a recorded
    provider had to be dropped, in which case it is one entry in
    active_provider_detail()'s own `ignored` shape, so the UI renders it through
    the path that already exists for a dropped Settings choice rather than a
    new one invented for this case.
    """
    if not sutra_id:
        return None, None
    try:
        rec = chat_store.load(sutra_id)
    except Exception:   # noqa: BLE001 -- a bad record must not kill the connect
        return None, None
    if rec is None:
        return None, None
    pid = (chat_store.active_segment(rec) or {}).get("provider")
    if not pid:
        # A chat that exists but has never been sent anywhere. It has no
        # provider of its own yet, so the global default is the right answer --
        # which is what returning None asks the caller to do.
        return None, None
    prov = providers.provider_by_id(pid)
    if prov is None:
        return None, {"source": "chat-history", "id": pid,
                      "reason": "unknown provider id"}
    if not prov["runnable"]:
        return None, {"source": "chat-history", "id": pid,
                      "reason": prov["reason"]}
    return prov["id"], None


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """Chat <-> background `claude -p`. One subprocess per message; --resume keeps
    the conversation. Inherits the logged-in Max subscription (no API key in env).

    Frames out: {"type":"start"} {"type":"session","id":...} {"type":"token","text":...}
                {"type":"tool","name":...} {"type":"done","session":...}
                {"type":"error","detail":...}
    Frames in:  {"message": "<text>", "resume": "<claude session id>"|null}
                `resume` seeds the thread when the browser reconnects a pane that
                already has a Claude session (a new socket otherwise starts cold).
    """
    if await _reject_cross_origin(ws):
        return
    await ws.accept()
    # Same refusal ws_term already makes: a key in the server env bills the API
    # instead of the Max plan. Silently spending the operator's API credit
    # because a stray key was exported is not an acceptable default.
    if os.environ.get("ANTHROPIC_API_KEY"):
        await ws.send_json({"type": "error", "detail":
            "Refused: ANTHROPIC_API_KEY is set in the server environment -- that bills "
            "the API, not your Max plan. Unset it and restart the server."})
        await ws.close()
        return
    # --- resolve the ACTIVE provider, per connect ------------------------
    # Hardcoding CLAUDE_BIN meant the provider selector in the UI was
    # decoration: whatever you picked, the server still spawned `claude`.
    # Resolve it here instead, and REFUSE clearly rather than handing an
    # unrunnable name to create_subprocess_exec -- which fails as a socket
    # that dies mid-handshake with no text on screen.
    # PER-CHAT provider override (provider-switch piece 7). The global setting
    # is the DEFAULT; one chat may run on a different provider, which is what
    # the composer's provider control sets.
    #
    # WHY A QUERY PARAM AND NOT A MESSAGE FIELD: the provider decides which
    # BINARY is spawned and which protocol the runtime speaks (Claude's
    # stream-json vs ACP), both fixed at spawn. It is the same class of thing as
    # cwd, and cwd is carried on the socket URL for exactly this reason -- see
    # claudeWsUrl/setSessCwd in static/js/01-state.js. Changing it therefore
    # drops the socket and the next message opens a new one; a per-message field
    # would promise something this handler cannot deliver.
    #
    # An unrunnable or unknown request is REFUSED rather than silently falling
    # back to the global provider: a pane that answers as Claude after the
    # operator picked DeepSeek is worse than one that says why it cannot.
    req_provider = (ws.query_params.get("provider") or "").strip()
    # The durable chat this pane belongs to. Absent for every existing caller,
    # which is what keeps this whole feature additive -- without it the handler
    # behaves exactly as it did before piece 7.
    sutra_id = (ws.query_params.get("sutra") or "").strip()

    if req_provider:
        want = providers.provider_by_id(req_provider)
        if want is None:
            await ws.send_json({"type": "error", "code": "unknown-provider",
                "detail": "unknown provider %r -- known ids: %s"
                          % (req_provider,
                             ", ".join(p["id"] for p in providers.discover_providers()))})
            await ws.close()
            return
        if not want["runnable"]:
            await ws.send_json({"type": "error", "code": "provider-missing",
                "detail": "provider %r cannot be started here: %s"
                          % (req_provider, want["reason"])})
            await ws.close()
            return
        detail = {"id": want["id"], "source": "chat", "ignored": []}
    else:
        # CHAT-LOCAL BEFORE GLOBAL. The precedence is now:
        #
        #   1. ?provider=          explicit switch request        (arm above)
        #   2. this chat's own last segment                       (here)
        #   3. active_provider_detail()  env -> settings -> first runnable
        #
        # Step 2 is what makes an in-chat switch STICKY without touching
        # settings.json: the chat carries its own answer in provider_history,
        # so Chat A can sit on Codex while the global default -- and therefore
        # every new chat and every chat that never switched -- stays Claude.
        #
        # A DROPPED RECORDED PROVIDER IS SAID OUT LOUD, through the `ignored`
        # list active_provider_detail already publishes for a dropped Settings
        # choice. Falling back silently would answer as Claude on a chat the
        # operator moved to Codex, with nothing on screen to explain it.
        chat_pid, chat_ignored = _chat_local_provider(sutra_id)
        if chat_pid:
            detail = {"id": chat_pid, "source": "chat-history", "ignored": []}
        else:
            detail = providers.active_provider_detail()
            if chat_ignored:
                detail = dict(detail, ignored=[chat_ignored]
                              + list(detail.get("ignored") or []))
    active_id = detail["id"]
    if active_id is None:
        lines = ["  - %s: %s" % (p["id"], p["reason"] or "?")
                 for p in providers.discover_providers()]
        await ws.send_json({"type": "error", "code": "no-provider", "detail":
            "No AI provider is usable here -- a provider must be installed, "
            "configured, AND have a chat adapter in this build:\n"
            + "\n".join(lines)})
        await ws.close()
        return

    prov = providers.provider_by_id(active_id)
    if not prov["bin_path"]:
        # Reachable if the binary disappears between the settings write and
        # this connect (uninstall, PATH change, a stale settings.json).
        await ws.send_json({"type": "error", "code": "provider-missing", "detail":
            "Active provider %r cannot be started: %s" % (active_id, prov["reason"])})
        await ws.close()
        return

    deepseek_key = None
    if active_id == "deepseek":
        # Mirrors the ANTHROPIC_API_KEY refusal above, for the opposite
        # reason: Claude inherits the logged-in Max subscription and
        # REFUSES a stray key; DeepSeek has no subscription path at all and
        # REQUIRES one. Refused here, at connect time, rather than left to
        # fail inside spawn() as a dead socket with no text.
        #
        # THROUGH THE RESOLVER, not os.environ. This read was its own
        # os.environ.get("DEEPSEEK_API_KEY") and deepseek_usage.py's balance
        # fetch was another, so neither could see a key saved in the keychain
        # and the two would have disagreed about whether DeepSeek was usable.
        # providers.deepseek_key_for_request() is the one resolution path, and
        # it is read HERE, per connect, so signing in takes effect on the next
        # message instead of the next restart.
        #
        # STILL REACHABLE with the readiness gate in place. An unkeyed DeepSeek
        # is no longer runnable, so the `prov["runnable"]` refusal above now
        # catches the ordinary case; what is left for this arm is the narrow
        # one -- a key that vanished between that check and this line, or a
        # settings marker whose keychain item is gone. The resolver's reason
        # names which.
        deepseek_key, why = providers.deepseek_key_for_request()
        if not deepseek_key:
            await ws.send_json({"type": "error", "code": "provider-missing", "detail":
                "Active provider is 'deepseek', but %s" % why})
            await ws.close()
            return
    elif active_id not in ("claude", "codex"):
        # Honest refusal instead of a confusing crash: the frames below parse
        # Claude Code's `--output-format stream-json`, Codex's `exec --json`
        # or DeepSeek's ACP protocol. Spawning another vendor's CLI with these
        # flags would fail on argument parsing and report as though the
        # provider were broken. No adapter has been written, so say that.
        #
        # `not in (...)` rather than `!= "claude"` (2026-09-08, Codex adapter).
        # The truth table is unchanged for every id that could already reach
        # this line: claude was False and stays False; deepseek returns or
        # falls through from the arm above and never arrives here; gemini and
        # any unknown id are still refused. Only `codex` changed answer.
        await ws.send_json({"type": "error", "code": "no-adapter", "detail":
            "Active provider is %r (%s at %s). No chat adapter has been "
            "written for it here, so it is not being run rather than run "
            "wrongly. Use the provider selector to switch to claude, codex or "
            "deepseek, or the terminal tab." % (active_id, prov["name"], prov["bin_path"])})
        await ws.close()
        return

    settings = providers.load_settings()
    # Clamp at the point of USE, not just where it was written: a settings.json
    # from an older build, hand-edited, or written by another local process
    # would otherwise reach the spawn below with the ceiling raised.
    perm_mode = providers.effective_permission_mode(settings["permission_mode"])
    workdir = settings["workdir"] or WORKDIR
    # Per-session working directory. The settings value is the DEFAULT; a session
    # may run somewhere else, which is what the composer's folder control sets.
    # Same confinement as every other path into a spawn -- workdir_allowed() keeps
    # this inside $HOME (or SUTRA_UI_WORKDIR_ROOT), because the workdir becomes the
    # agent's cwd and an arbitrary one turns this endpoint into a read oracle over
    # the whole disk. A refused path FALLS BACK to the setting and says so in the
    # provider frame rather than failing the connection: the operator gets a
    # working session and an honest label, not a dead socket.
    req_cwd = ws.query_params.get("cwd")
    cwd_refused = None
    if req_cwd:
        if providers.workdir_allowed(req_cwd):
            workdir = os.path.expanduser(req_cwd)
        else:
            cwd_refused = req_cwd
    if not providers.workdir_allowed(workdir):
        workdir = WORKDIR
    agent_bin = prov["bin_path"]

    if _ensure_workdir(workdir) is None:
        await ws.send_json({"type": "error", "detail":
            "workdir %s does not exist and could not be created" % workdir})
        await ws.close()
        return

    # One frame the client can render as a status line: which binary, which
    # permission mode, and (when acceptEdits/bypassPermissions is on) the fact
    # that this session may write files without asking.
    await ws.send_json({
        "type": "provider",
        "id": active_id,
        "name": prov["name"],
        "bin": agent_bin,
        "source": detail["source"],
        "permission_mode": perm_mode,
        "permission_note": providers.PERMISSION_MODE_NOTES.get(perm_mode),
        "writes_files": perm_mode in ("acceptEdits", "bypassPermissions"),
        "workdir": workdir,
        # Stated, not swallowed: the session is running somewhere other than what
        # was asked for, and a UI that showed the requested path would be lying.
        "cwd_refused": cwd_refused,
        # Which chat this pane is bound to, echoed so the UI can confirm the
        # server agrees with it rather than assuming.
        "sutra_id": sutra_id or None,
    })

    # Provider-switch seeding (piece 7). Armed only when the pane named a chat;
    # consumed by the FIRST message of this connection and then cleared, because
    # a switch happens once -- at the moment the provider changes -- and turns
    # after it are ordinary turns on the new provider's own session.
    seed_switch = bool(sutra_id)
    #: A carry-over payload was BUILT this turn and the target has not yet
    #: handed back a native session. Exists because "once per connection,
    #: whatever happens" was written when a switch had only two outcomes --
    #: planned, or refused -- and a target that dies AFTER a successful plan is
    #: a third one it did not anticipate. In that case the switch did not
    #: happen: no segment was written, and the payload was never processed, so
    #: the carry-over is still owed to the operator. See the `failed` branch.
    switch_planned = False

    session_id = None
    resume_unverified = False   # session id came from the client, not from a live run
    dead_seeds = set()          # client-supplied ids claude has already rejected
    # A message to re-run immediately, bypassing the inbox. Set when a turn dies
    # because the resumed thread did not exist: the message itself was fine, so
    # it is replayed once WITHOUT --resume instead of being thrown away. See the
    # failure branch below for why losing it was the actual bug.
    pending = None

    # ---- interrupt --------------------------------------------------------
    # The loop used to `await ws.receive_text()` and only THEN spawn, so nothing
    # read the socket while a turn streamed: a stop sent mid-turn sat unread until
    # the very turn it was meant to cancel had already finished. A button alone
    # could not fix that -- the read must happen CONCURRENTLY with the subprocess.
    #
    # One reader task owns the socket, handles `stop` inline (the only frame that
    # must act during a turn) and queues everything else for the main loop.
    # Claude's arm is FIRST and unchanged; the final else still yields
    # AcpRuntime for deepseek, which is the only other id that reaches here
    # (everything else was refused above). Only codex takes the new branch.
    rt = (SessionRuntime() if active_id == "claude"
          else CodexRuntime() if active_id == "codex"
          else AcpRuntime())
    inbox = asyncio.Queue()
    reader_dead = asyncio.Event()

    #: The live /fanout orchestration for this socket, or None. A MUTABLE CELL
    #: rather than a plain name because `_reader` below closes over it and has
    #: to see a value assigned later, in the turn loop.
    #:
    #: WHY IT HAS TO EXIST AT ALL: the stop handler signals `rt`, the PANE's
    #: runtime -- and during a fan-out that runtime has not been spawned yet.
    #: The live children are locals inside worker.run_one, so without this a
    #: Stop would signal a process that does not exist while up to three real
    #: CLI processes kept running, and a disconnect would orphan them.
    #: None for every ordinary turn, which is why nothing below changes shape
    #: for a message that is not a fan-out.
    fanout_live = {"orch": None}

    async def _reader():
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    payload = json.loads(raw)
                except (ValueError, TypeError):
                    payload = {"message": raw}
                if not isinstance(payload, dict):
                    payload = {"message": str(payload)}
                if payload.get("type") == "stop":
                    # FAN-OUT WORKERS FIRST, then the pane. Their order matters
                    # only in that both must happen: cancel() is a synchronous,
                    # idempotent no-op when nothing is fanning out, so the
                    # existing single-provider stop path is unchanged.
                    orch = fanout_live["orch"]
                    if orch is not None:
                        orch.cancel()
                    # Set the flag BEFORE killing: the stdout loop can end between
                    # the signal and the assignment, and would then report the
                    # operator's own interrupt as a crash.
                    rt.stop()
                    continue
                await inbox.put(payload)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            reader_dead.set()

    reader_task = asyncio.create_task(_reader())

    try:
        while True:
            if pending is not None:
                # A replay never touches the socket: the operator already sent
                # this text, and re-reading the inbox here would reorder it
                # behind anything they typed while the failed turn was running.
                payload, pending = pending, None
            elif inbox.empty() and len(rt.turn_queue) > 0:
                # S37: a queued shadow turn runs ONLY at a boundary and ONLY
                # when no operator frame is waiting -- the founder never queues
                # behind automation. The loop-top length check (not the event)
                # is authoritative, so coalesced wake-ups cannot stall a
                # non-empty queue (dual-lane fold).
                rt.queue_event.clear()
                payload = rt.turn_queue.get()
                if payload is None:
                    continue
            else:
                get_next = asyncio.ensure_future(inbox.get())
                gone = asyncio.ensure_future(reader_dead.wait())
                nudge = asyncio.ensure_future(rt.queue_event.wait())
                done, _ = await asyncio.wait({get_next, gone, nudge},
                                             return_when=asyncio.FIRST_COMPLETED)
                if get_next in done:
                    gone.cancel()
                    nudge.cancel()
                    payload = get_next.result()
                elif nudge in done:
                    # just a nudge: loop back up; the queue check above decides
                    get_next.cancel()
                    gone.cancel()
                    rt.queue_event.clear()
                    continue
                else:
                    get_next.cancel()  # socket closed -- stop serving this channel
                    nudge.cancel()
                    break
            rt.stopped = False
            if (payload.get("_source") != "shadow" and session_id
                    and providers.shadow_enabled()):
                # R22 takeover (dual-lane fold): an operator turn on a session
                # with a running mission PAUSES it here -- after payload
                # ownership, before any turn dispatches; queued shadow turns
                # for this session are dropped by the pause path.
                try:
                    hit = shadow_runner.founder_takeover(session_id)
                    if hit is not None:
                        rt.turn_queue.clear_shadow()
                except Exception:
                    pass
            msg = payload.get("message", "")
            seed = payload.get("resume")
            model = payload.get("model")
            if not msg.strip():
                continue

            # ---- the chat id can arrive with the MESSAGE, not the URL --------
            # A pane opened from the transcript rail knows a native session id
            # (07-loaders.js adoptRealSessions attaches one to every listed
            # transcript) but NOT the sutra chat id: the browser learns that
            # only from a `provider` or `chat` frame, and both need a socket
            # that does not exist yet. So the first message after opening such a
            # chat arrives with `resume` set and `?sutra=` absent.
            #
            # WHAT THAT COST, measured on disk 2026-09-09. seed_switch is
            # bool(sutra_id), so it was false; switch.plan never ran, and the
            # conversation was not carried anywhere. The seed guard below is
            # `_seed_is_another_providers(seed, active_id, sutra_id)`, which
            # short-circuits to False on an empty sutra_id -- so a CLAUDE id was
            # adopted on a CODEX pane, passed as `codex exec resume <claude id>`,
            # echoed back by codex as its own thread id (codex_runtime.py:522),
            # missed by the resolve() below, and written to a BRAND NEW chat
            # record. One switch produced: a forked chat, no carried context,
            # and a codex segment naming a session that exists only in claude's
            # tree. Two such records are on the founder's disk.
            #
            # THE LOOKUP ALREADY EXISTED AND IS DOCUMENTED FOR EXACTLY THIS.
            # chat_store.resolve's own docstring: "the lookup ws_chat needs on
            # reconnect: the browser hands back a native session id, and the
            # panel has to find the Sutra chat it belongs to -- which may have
            # started on the OTHER provider." It was only ever called AFTER the
            # turn, and only with `active_id` -- the provider being switched TO
            # -- which can never match a seed minted by the one being left. So
            # this asks every segment provider, before the switch decision
            # instead of after it. No new index, no new state.
            if not sutra_id and seed and isinstance(seed, str):
                for _pid in chat_store.SEGMENT_PROVIDERS:
                    try:
                        _found = chat_store.resolve(_pid, seed)
                    except Exception:   # noqa: BLE001 -- a bad index must not kill a turn
                        _found = None
                    if _found:
                        sutra_id = _found
                        # RE-ARM. seed_switch was computed from an empty
                        # sutra_id at connect; the chat is now known, so the
                        # carry-over this connection is owed can still happen.
                        # Set here rather than at connect because that is the
                        # first moment the id exists.
                        seed_switch = True
                        # TELL THE CLIENT, or it re-learns this on every single
                        # connect and only for as long as it still holds a
                        # resumable seed. The frame is the one the minting path
                        # below already sends; the client stores it
                        # (01-state.js) and the next socket carries ?sutra=.
                        await ws.send_json({"type": "chat", "sutra_id": sutra_id})
                        break

            # ---- carry the conversation across a provider switch ------------
            # The operator picked a different provider, the socket reopened on
            # it, and this is the first message. The new provider knows nothing
            # about the previous N turns, so the prior transcript is replayed to
            # it as the first prompt and the operator's message rides along at
            # the end (switch.plan -> switch_egress.prepare).
            #
            # A REFUSAL IS SURFACED, NOT SWALLOWED. Every reason switch.plan can
            # decline -- unreadable source transcript, a payload that will not
            # fit even without tool output, a boundary that cannot be trusted --
            # is a thing the operator has to know, because the alternative is a
            # new provider answering turn 51 as though it were turn 1. The turn
            # still runs; it just runs WITHOUT the history, and says so.
            # The operator's OWN message, kept before the replay can replace
            # `msg` below. The chat record stores what the operator typed, not
            # the 200KB recording that got wrapped around it -- otherwise every
            # switch would append a copy of the entire prior conversation to the
            # very record the next switch reads.
            operator_msg = msg

            # ---- /fanout: RECOGNISE here, RUN after `start` -----------------
            # Two string operations on the operator's own text, before anything
            # else looks at it. The normal-chat fast path is this `if` and
            # nothing more: no provider call, no planner, no allocation, and
            # `fanout_req` stays None all the way down, so every branch below
            # behaves exactly as it did.
            #
            # READ FROM operator_msg, NOT msg, and the distinction is not
            # cosmetic: switch.plan may replace `msg` with a transcript replay
            # a few lines below, and the operator's command would then be
            # buried inside 200KB of recording where startswith cannot see it.
            #
            # RECOGNITION AND EXECUTION ARE SPLIT because the client binds a
            # token stream to a queued turn on the `start` frame
            # (01-state.js: ch.pending.shift()). Emitting progress -- or an
            # error -- before that frame would land it on no turn at all.
            fanout_req = (fanout.parse_request(operator_msg)
                          if fanout.should_orchestrate(operator_msg) else None)

            switch_note = None
            if seed_switch:
                seed_switch = False   # once per connection, whatever happens
                try:
                    # Same resolution build_agent_args gets below; computed here
                    # because the budget depends on WHICH model will answer
                    # (Haiku 4.5 is 200K where its siblings are 1M) and the
                    # payload has to be sized before it is built.
                    # THE REPLAY'S CLOSING LINE CARRIES THE OPERATOR'S REQUEST,
                    # AND `/fanout ...` IS NOT ONE. replay._closing appends
                    # next_message verbatim under "The operator's next message
                    # follows", so a raw command would arrive at the incoming
                    # provider as a literal it has never heard of, attached to
                    # a transcript it is being asked to continue. The JOB is
                    # what the operator actually asked for, so that is what the
                    # carry-over states.
                    #
                    # NOTHING ABOUT SWITCHING CHANGES. plan() still receives a
                    # next_message string and treats it identically; only WHICH
                    # string differs, and only on a turn that is already a
                    # fan-out. `fanout_req` is None for every other message, so
                    # this expression is `msg` verbatim.
                    plan = switch.plan(
                        sutra_id, active_id,
                        next_message=(fanout_req["job"]
                                      if fanout_req and fanout_req["ok"]
                                      else msg),
                        model=(providers.clean_model(model, active_id)
                               or providers.stored_model(active_id)))
                    if plan.get("switch"):
                        plan = switch_egress.prepare(plan)
                    if plan.get("switch"):
                        msg = plan["payload"]
                        # Owed until the target proves it exists. Only a BUILT
                        # payload arms this -- every refusal below is
                        # deterministic (NOT_NEEDED, UNKNOWN_TARGET,
                        # OVER_BUDGET, FENCE_BROKEN) and returns the identical
                        # answer next message, so re-attempting one would
                        # re-announce a refusal on every turn and change
                        # nothing.
                        switch_planned = True
                        switch_note = {
                            "type": "switch", "ok": True,
                            "source": plan["source"], "target": plan["target"],
                            "from_turn": plan["from_turn"], "tier": plan["tier"],
                            "chars": plan["chars"],
                            "redactions": plan.get("redaction_count", 0),
                            "dropped": {k: v for k, v in
                                        (plan.get("dropped") or {}).items() if v},
                            "detail": switch.describe(plan),
                        }
                    elif plan.get("reason") != switch.NOT_NEEDED:
                        switch_note = {
                            "type": "switch", "ok": False,
                            "reason": plan.get("reason"),
                            "detail": plan.get("detail"),
                            "source": plan.get("source"),
                            "target": active_id,
                        }
                    # THE CLIENT'S RESUME SEED BELONGS TO THE PROVIDER WE ARE
                    # LEAVING, so on a provider change it must not be adopted
                    # by the block below.
                    #
                    # The browser keeps ONE session id per pane
                    # (01-state.js:1455 writes s.claude_session from the
                    # `session` frame of WHICHEVER provider sent it) and hands
                    # it back as `resume` on the next connect. Nothing in that
                    # id says which provider minted it. Adopted here it becomes
                    # `session_id`, and two spawn paths then act on it:
                    #
                    #   claude    build_agent_args(session_id=...) -> --resume,
                    #             rebuilt at the `not alive` arm below. Claude
                    #             resolves ids in its OWN tree, so a Codex
                    #             thread id fails the turn outright:
                    #             "No conversation found with session ID: ..."
                    #   deepseek  new_session(session_id=...) -> session/load
                    #             instead of session/new, which is the opposite
                    #             of what switch._transport_for("deepseek")
                    #             declares seeding to mean.
                    #
                    # And because _demux_turn_inner adopts a native id only
                    # when the incoming one is None (session_runtime.py:439),
                    # the foreign id then SURVIVES the turn and reaches
                    # switch.confirm -- writing the source provider's
                    # native_id onto the target's segment. Measured live
                    # 2026-09-09 on two chats: every segment shared one id, so
                    # a later switch would have deduped them and never read
                    # the target's own transcript at all.
                    #
                    # NOT_NEEDED IS THE EXEMPTION, and it is what keeps
                    # ordinary reconnect-resume working: switch.plan returns it
                    # for "chat is already running on <target>" -- the
                    # same-provider reconnect -- and for a chat with no segment
                    # yet. Both keep their seed and behave exactly as before.
                    # Every other outcome means the provider changed, so the
                    # seed is stale by definition. A REFUSED switch is included
                    # deliberately: the live 10:17 failure leaked its seed on
                    # the refusal path, where the provider had still changed.
                    if plan.get("reason") != switch.NOT_NEEDED:
                        seed = None
                except Exception as exc:   # never let this kill a live turn
                    switch_note = {"type": "switch", "ok": False,
                                   "reason": "internal-error",
                                   "detail": "the conversation could not be "
                                             "carried over (%s); this turn runs "
                                             "without it" % exc}
            if switch_note:
                await ws.send_json(switch_note)
            if (session_id is None and seed and isinstance(seed, str)
                    and seed not in dead_seeds
                    and "/" not in seed and ".." not in seed
                    # NOT this pane's provider's id, by this chat's own record.
                    #
                    # THE CASE THIS GUARDS IS THE `NOT_NEEDED` ONE, which the
                    # switch-time clearing above cannot reach: plan() returns
                    # NOT_NEEDED for "already running on <target>", and that
                    # arm deliberately KEEPS the seed so an ordinary
                    # same-provider reconnect still resumes. It keeps whatever
                    # the client sent -- and the client holds ONE id per pane,
                    # written by whichever provider spoke last, so on a chat
                    # that has already switched, the id offered may belong to
                    # the provider being reconnected AWAY from. Codex accepts
                    # such an id in silence (see _seed_is_another_providers),
                    # so nothing downstream would have caught it.
                    #
                    # A target that DIES is a different problem with a
                    # different fix: the `failed` branch re-arms seed_switch,
                    # so the next message re-plans the switch and clears the
                    # seed through the normal path. This guard is not what
                    # covers that.
                    and not _seed_is_another_providers(seed, active_id, sutra_id)):
                session_id, resume_unverified = seed, True

            # Model: per-message override wins over the stored setting, and BOTH are
            # validated against the allow-list -- an arbitrary string here would be
            # passed straight to the CLI, where a typo fails as a dead socket several
            # seconds later instead of as a refusal now.
            chosen_model = (providers.clean_model(model, active_id)
                            or providers.stored_model(active_id))
            # Everything else the client may ask for this turn, validated in
            # build_agent_args rather than trusted here.
            #
            # ONE PROCESS, MANY TURNS. Every message used to spawn its own
            # `claude -p <msg>` with stdin closed: ~3s of cold start per turn, a
            # cross-process prompt-cache miss every time, and session continuity
            # faked with --resume (whose failure is the bug that lost messages).
            # A persistent process fed stream-json on stdin keeps one session id
            # for the life of the pane.
            #
            # BUT the model, permission mode, effort and budget are SPAWN-TIME
            # flags -- they cannot change on a running process. So the rule is:
            # reuse while the argv would be identical, otherwise respawn and
            # carry the thread across with --resume. That keeps per-message
            # overrides working instead of silently ignoring them, which is what
            # a naive "always reuse" would do.
            if active_id == "claude":
                args = build_agent_args(agent_bin, msg, perm_mode,
                                        session_id=None, model=chosen_model,
                                        opts=payload.get("opts"), stream_input=True)
            elif active_id == "codex":
                # RESUME IS BAKED IN HERE, unlike Claude's path, and that is
                # correct rather than a copy of the bug below. Claude keeps ONE
                # PROCESS across turns, so a resume-bearing spawn_key made the
                # reuse test permanently unequal and cold-started the CLI every
                # message. `codex exec` is one process per TURN -- it exits
                # after answering -- so `alive` is always False at the top of
                # the next turn and the comparison can never mis-fire. The
                # thread id therefore belongs in the argv the key is built
                # from.
                #
                # THE PROMPT IS NOT PASSED. build_codex_args ends the argv with
                # `-` and CodexRuntime.send_prompt delivers `msg` on stdin, so
                # no message text ever reaches argv (and E2BIG cannot happen on
                # a long provider-switch payload).
                args = build_codex_args(agent_bin, perm_mode, workdir,
                                        model=chosen_model,
                                        session_id=session_id,
                                        # The pane's own per-turn controls,
                                        # validated in codex_turn_config rather
                                        # than trusted here -- same policy the
                                        # Claude arm applies to its own opts.
                                        opts=payload.get("opts"))
            else:
                # Permission-mode is set once in new_session below, not per
                # message. The MODEL is spawn-time argv (ACP exposes no
                # set_model on this build), so it goes here -- and because
                # spawn_key is tuple(args), changing it respawns through the
                # same path a permission-mode change already uses.
                args = build_acp_args(agent_bin, chosen_model)
            spawn_key = tuple(args)
            proc = rt.proc
            alive = rt.alive
            if alive and rt.key != spawn_key:
                # a spawn-time option changed: end this process and carry the
                # conversation over rather than dropping it
                rt.kill_group()
                try:
                    await proc.wait()
                except Exception:
                    pass
                alive = False
            if not alive and session_id and active_id == "claude":
                args = build_agent_args(agent_bin, msg, perm_mode,
                                        session_id=session_id, model=chosen_model,
                                        opts=payload.get("opts"), stream_input=True)
                # DELIBERATELY NOT re-keying spawn_key here. The reuse test at the
                # top compares the RESUME-FREE key (session_id=None) built each
                # message; storing the resume-BEARING key made that comparison
                # permanently unequal, so any pane opened from an existing
                # transcript killed and cold-started claude on every message --
                # ~3s of startup, the sutra MCP server respawned, the prompt cache
                # missed, the conversation re-read from disk. `args` still carries
                # --resume for THIS spawn; only the stored comparison key stops
                # depending on it, so the next message reuses the live process.
                #
                # Not applicable to deepseek: ACP has no --resume flag, so a
                # dead ACP process starts a genuinely new session below rather
                # than resuming the old one -- a known gap (session/load could
                # close it later), not a silent one.

            # EXACTLY ONE `start` PER OPERATOR MESSAGE. The client treats `start`
            # as the demarcation that binds the next token stream to the next
            # QUEUED turn (`ch.pending.shift()`), so a second one for an internal
            # replay would bind the reply to whatever message the operator typed
            # while this turn was failing. A replay continues the turn that is
            # already on screen; it does not announce a new one.
            if not payload.get("_replay"):
                # `model` here is now true on BOTH paths. It always was on
                # Claude's (build_agent_args carries it into --model) and never
                # was on DeepSeek's, where build_acp_args discarded it -- so
                # this frame asserted a model the CLI had not been given. Both
                # arms above now build argv from this same `chosen_model`, and
                # TestDeepSeekSpawnedModel.test_announced_model_is_the_spawned_model
                # asserts it against the ACTUAL argv the CLI was launched with
                # (recorded from inside the spawned process by
                # qa/fake_acp_agent.py), not against what this code intended.
                await ws.send_json({"type": "start", "model": chosen_model})

            # ---- /fanout: the orchestration itself --------------------------
            # AFTER `start`, so every frame below lands on a turn the client
            # has already bound; BEFORE the spawn, so the parent provider is
            # started once, with the finished synthesis prompt, and answers it
            # as an ordinary turn. Everything past this block is untouched.
            #
            # THE ARGV IS ALREADY BUILT ABOVE AND THAT IS SAFE ON ALL THREE
            # PATHS -- none of them carries the message in argv. Claude's
            # stream_input=True branch omits the positional prompt,
            # build_codex_args ends the argv with `-` and delivers on stdin,
            # and build_acp_args never took a message. So rewriting `msg` here
            # reaches the provider and changes no command line.
            if fanout_req is not None:
                if not fanout_req["ok"]:
                    # Malformed command. Close the turn honestly rather than
                    # spending a provider call to explain a typo.
                    await ws.send_json({"type": "error",
                                        "detail": fanout_req["error"]})
                    await ws.send_json({"type": "done", "session": session_id})
                    continue
                orch = fanout.Orchestration()
                fanout_live["orch"] = orch
                try:
                    fo = await fanout.run(
                        fanout_req["job"], active_id, workdir, perm_mode,
                        emit=ws.send_json, orch=orch)
                except Exception as exc:      # noqa: BLE001
                    fo = {"ok": False, "reason": "internal-error", "tasks": [],
                          "detail": "the fan-out could not run (%s)" % exc}
                finally:
                    # Guarantees no child survives on ANY path -- including the
                    # exception one, where run()'s own cleanup did not finish.
                    # Then drop the handle, so a stop arriving later on this
                    # socket cannot sweep a job that is already done.
                    orch.cancel()
                    fanout_live["orch"] = None
                # `fo["reason"]`, NOT orch.cancelled: the finally above sets
                # that flag on every path, so testing it here would read as a
                # condition and behave as a constant. run() reports whether the
                # operator actually stopped it.
                if fo.get("reason") == "cancelled":
                    # The operator pressed stop DURING the fan-out. No parent
                    # turn runs: they asked for it to end, and spending a
                    # synthesis call would be the opposite of stopping.
                    rt.stopped = False
                    await ws.send_json({"type": "stopped", "session": session_id})
                    continue
                # THE COMMAND WORD IS NOT PART OF THE QUESTION, and the
                # PLACEMENT grounding is. Rebuilding `prefix + job` keeps the
                # ADR-028 block the client attached to this turn -- so a
                # fan-out turn reaches the provider with exactly the grounding
                # an ordinary turn would have had -- while dropping the
                # `/fanout` token, which is a Sutra trigger and means nothing
                # to a model. When a switch already rewrote `msg` into a
                # replay, that payload is kept as-is: its closing line was
                # built from the job (see the switch.plan call above).
                base = (fanout_req["prefix"] + fanout_req["job"]
                        if msg == operator_msg else msg)
                if fo.get("ok"):
                    msg = fanout.compose(base, fanout_req["job"], fo["tasks"])
                else:
                    # FALL BACK, never fabricate. Planning failed, the job did
                    # not decompose, or every worker died -- the operator still
                    # gets a real answer from the parent provider, to their
                    # ORIGINAL words, and is told the fan-out did not happen.
                    await ws.send_json({
                        "type": "tool", "phase": "start", "id": "fanout-plan",
                        "name": "fan-out", "summary": fo.get("detail")
                        or "not run", "command": "", "caller": None})
                    await ws.send_json({
                        "type": "tool", "phase": "end", "id": "fanout-plan",
                        "ok": False, "output": fo.get("detail") or ""})
                    # Same rebuild as the success path: the operator still
                    # gets a real answer to their real question, grounded.
                    msg = base

            if not alive:
                if active_id in ("deepseek", "codex"):
                    # The `deepseek` command npm publishes is a shim beginning
                    # `#!/usr/bin/env node`, so Node has to resolve HERE, on
                    # every launch -- not only during the install that fetched
                    # it. On a Mac with no Node of its own, without this the CLI
                    # installs perfectly (through the bundled npm) and then dies
                    # at spawn with `env: node: No such file or directory`,
                    # which reads like a broken install rather than a missing
                    # runtime. No-op outside the packaged app.
                    #
                    # `codex` ADDED 2026-09-08 and it is the same fact, measured
                    # rather than assumed: @openai/codex publishes bin/codex.js,
                    # 13KB of ESM beginning `#!/usr/bin/env node`, which resolves
                    # a platform package and execs the Rust binary inside it
                    # (`file` on an installed copy: "a /usr/bin/env node script
                    # text executable"). codex_install.py fetches that package,
                    # so a Codex installed by Sutra on a Node-less Mac had
                    # exactly the DeepSeek failure waiting for it. Nothing about
                    # Claude changes -- its CLI is not a node shim and it is
                    # still excluded.
                    providers.ensure_bundled_node_path()
                spawn_env = ({"DEEPSEEK_API_KEY": deepseek_key}
                             if active_id == "deepseek" else None)
                try:
                    proc = await rt.spawn(args, workdir, spawn_key, env=spawn_env)
                except OSError as e:
                    # Real cause, verbatim -- a dead socket taught the operator nothing.
                    await ws.send_json({"type": "error", "detail":
                        "could not start %r in %s: %s" % (agent_bin, workdir, e)})
                    continue
                if active_id == "deepseek":
                    # NARROWED from `!= "claude"` (2026-09-08, Codex adapter).
                    # This block is the ACP handshake -- authenticate +
                    # session/new + the mode note -- and `codex exec` has none
                    # of those: no auth step (the CLI owns ~/.codex/auth.json),
                    # no session/new (the thread arrives on stdout's first
                    # line), and its permission mode is spawn-time argv. Left
                    # as `!= "claude"` a Codex pane would have called
                    # AcpRuntime methods CodexRuntime does not implement and
                    # died at the first message with an AttributeError.
                    #
                    # A STATEMENT OF TRUTH, NOT A BEHAVIOUR CHANGE: deepseek is
                    # the only id that has ever reached this line. claude was
                    # excluded by the old condition and is excluded by this
                    # one; gemini and unknown ids are refused at connect.
                    if deepseek_key:
                        # BEFORE session/new, not instead of the env key.
                        # AcpRuntime.authenticate's docstring has the wire
                        # evidence: without this the fork defaults the session
                        # to Gemini auth and refuses it with "Gemini API key is
                        # missing or not configured" -- a Gemini error on a
                        # DeepSeek pane, with a valid DeepSeek key in hand.
                        try:
                            await rt.authenticate(deepseek_key)
                        except Exception as e:
                            await ws.send_json({"type": "error", "detail":
                                "%s did not accept the saved key: %s" % (active_id, e)})
                            rt.kill_group()
                            rt.clear()
                            continue
                    try:
                        # session_id is already in scope here: the client's
                        # `resume` seed on a reconnect (set above, before
                        # this block -- the same variable Claude's own
                        # --resume path reads), or None on a cold pane.
                        # AcpRuntime resolves the fallback-on-dead-id case
                        # internally -- nothing else to do here.
                        await rt.new_session(workdir, perm_mode, session_id=session_id,
                                             mcp_servers=_sutra_acp_mcp_servers())
                    except Exception as e:
                        await ws.send_json({"type": "error", "detail":
                            "could not start a %s session: %s" % (active_id, e)})
                        rt.kill_group()
                        rt.clear()
                        continue
                    # The permission mode the operator picked did not survive
                    # the trip to this provider. SAID, once per spawn, because
                    # the `provider` frame above already told the pane it would
                    # run `perm_mode` -- and that frame is sent before the
                    # session exists, so it cannot know. Without this the pane
                    # keeps displaying a mode nothing is enforcing, which is
                    # the bug the runtime fix half-solves: the runtime now
                    # knows the truth, and this is the only channel that can
                    # carry it to the operator.
                    #
                    # A NEW FRAME TYPE, not the existing `notice`. `notice` is
                    # emitted server-side in three places and the client has NO
                    # handler for any of them -- it is dropped on the floor
                    # today (checked, not assumed). Reusing it would look like
                    # reporting and report nothing. Claude never sends this
                    # frame, so nothing about Claude's rendering changes.
                    if rt.acp_mode_note:
                        await ws.send_json(dict(rt.acp_mode_note,
                                                type="mode_note",
                                                provider=active_id))
                elif active_id == "codex":
                    # Same divergence, same frame, computed WITHOUT a round
                    # trip: codex's permission posture is spawn-time argv, so
                    # the mismatch is known from `perm_mode` alone and needs no
                    # equivalent of ACP's session/new response. Reachable
                    # because permission_mode is stored globally -- a `dontAsk`
                    # chosen while Claude was selected arrives here. Emitted
                    # once per spawn, exactly like DeepSeek's.
                    note = codex_mode_note(perm_mode)
                    if note:
                        await ws.send_json(dict(note, type="mode_note",
                                                provider=active_id))
            proc = rt.proc

            if active_id == "claude":
                # The turn itself: one stream-json frame on stdin.
                try:
                    await rt.send_user_frame(msg)
                except (BrokenPipeError, ConnectionResetError, AttributeError) as e:
                    # the process died between the liveness check and the write
                    rt.proc = None
                    await ws.send_json({"type": "error", "detail":
                        "the agent process closed before the message was sent (%s)" % e})
                    continue
                (session_id, got_text, got_result,
                 result_error, eof) = await rt.demux_turn(ws.send_json, session_id)
            else:
                # ACP's session/prompt is one request/response -- send and
                # read-until-terminal collapse into one call. Same 5-tuple
                # contract as demux_turn, so everything below this point
                # (stderr/rc reap, stop/failed/done handling) is unchanged.
                #
                # CODEX SHARES THIS CALL UNCHANGED (2026-09-08). Its turn is
                # also one send-then-read-to-terminal, so CodexRuntime
                # implements the same prompt_turn(msg, emit, session_id)
                # signature and returns the same 5-tuple -- which is why the
                # third provider needed no third arm here.
                (session_id, got_text, got_result,
                 result_error, eof) = await rt.prompt_turn(msg, ws.send_json, session_id)
            # S23: now that the session id is known, make this runtime
            # discoverable (idempotent; same id + same rt every turn).
            register_runtime(session_id, rt)

            # The segment records a session that EXISTS, which is why this is
            # here and not next to switch.plan above: writing it before the
            # transport returned an id would leave a from_turn pointing at a
            # session that may never have been created, and the next reconnect
            # would try to resume a thread that was never born. Idempotent for
            # the same (provider, id), so calling it every turn is correct and
            # a reconnect on the live session does not split one run in two.
            #
            # AND THIS IS WHERE THE CHAT ID IS MINTED. It has to be: the id is
            # keyed to a provider-native session, and that session does not
            # exist until the transport hands one back. The first version of
            # this feature only sent `?sutra=` when the client ALREADY knew the
            # id and nothing ever produced the first one -- so seed_switch was
            # always false, switch.plan was never called, and a provider change
            # switched the provider while silently carrying nothing. The
            # provider swapped, the conversation did not, and no error said so.
            # Minted server-side rather than in the browser because the id is
            # durable state keyed on a session id only the server sees.
            if session_id:
                # The target EXISTS, so the carry-over is no longer owed: the
                # segment below records it, and the next plan() therefore
                # returns NOT_NEEDED. Cleared here rather than in the failure
                # branch so a turn that fails LATER -- after a session was
                # established -- cannot re-arm and replay a payload the target
                # has already received.
                switch_planned = False
                try:
                    if not sutra_id:
                        # Resolve first: a pane reopened on an existing session
                        # already belongs to a chat, and creating a second
                        # record for it would split one conversation in two.
                        found = chat_store.resolve(active_id, session_id)
                        if found:
                            sutra_id = found
                        else:
                            rec = chat_store.create(cwd=workdir, branch="")
                            sutra_id = rec["sutra_id"]
                        await ws.send_json({"type": "chat", "sutra_id": sutra_id})
                    switch.confirm(sutra_id, active_id, session_id)
                    # The operator's turn, so turn_count -- and therefore the
                    # `from_turn` of the NEXT segment -- is a real number rather
                    # than permanently 0.
                    rec = chat_store.load(sutra_id)
                    if rec is not None:
                        chat_store.append_turn(
                            rec, "user", [chat_store.block_text(operator_msg)])
                except Exception:
                    # Bookkeeping must never take down a turn that worked. The
                    # cost of losing it is a switch that is not recorded, which
                    # the next connect reports as a provider mismatch rather
                    # than corrupting anything.
                    pass
            if session_id and providers.shadow_enabled():
                # the watcher rides every live pane (GAP-AUDIT row 3)
                shadow_runner.attach_observer(session_id, rt)
                # auto-watch (finish-list 2026-08-26): panes appear in the
                # Watching list by default. No-op when already listed (no
                # disk write storm), never for delegates or opted-out ids.
                try:
                    _shadow_auto_watch(session_id)
                except Exception:
                    pass

            # Do NOT read stderr to EOF or wait() here: both block forever on a
            # process that is meant to outlive the turn. Only a dead process is
            # drained and reaped.
            err = ""
            rc = 0
            if eof:
                try:
                    err = (await asyncio.wait_for(proc.stderr.read(), 2)).decode(
                        "utf-8", "replace")
                except (asyncio.TimeoutError, Exception):
                    err = ""
                try:
                    rc = await asyncio.wait_for(proc.wait(), 5)
                except (asyncio.TimeoutError, Exception):
                    rc = -1
                rt.clear()

            if rt.stopped:
                # SIGTERM makes rc non-zero, which the branch below would report as
                # "claude exited -15" -- i.e. blaming the tool for the operator's own
                # interrupt. A stop is a normal outcome and gets its own frame.
                # The session id is KEPT: the thread is still resumable, the operator
                # simply cut this turn short.
                #
                # A stop now ends the whole PERSISTENT process, because that is
                # the only way to interrupt a turn in flight. Clear it so the
                # next message spawns a fresh one -- and because session_id is
                # kept, that respawn carries --resume and the conversation
                # continues where it was cut.
                rt.stopped = False
                rt.clear()
                await ws.send_json({"type": "stopped", "session": session_id})
                continue

            # rc is only meaningful when the process actually exited. A live
            # process has no return code, so a turn fails when it SAID it failed
            # or when the process died before producing a result.
            failed = (result_error is not None) or (eof and not got_result) or (eof and rc != 0)
            if failed:
                # stderr carries the specific cause ("No conversation found with
                # session ID: ..."); the result payload is the fallback.
                #
                # The last-resort string names CODEX on a codex pane and is
                # otherwise untouched. Added as its own branch rather than by
                # interpolating active_id into the existing one, because that
                # would also change the sentence DeepSeek shows -- a working
                # provider's error text is not this change's business. Narrow
                # but real: eof with an empty stderr on a codex pane would
                # otherwise report "claude exited -1" about a process named
                # codex.
                fallback = ("codex exited " + str(rc) if active_id == "codex"
                            else "claude exited " + str(rc))
                detail = err.strip()[:600] or result_error or fallback
                frame = {"type": "error", "detail": detail}
                if switch_planned and session_id is None:
                    # A CARRY-OVER WAS BUILT AND THE TARGET NEVER CAME UP, so
                    # the switch did not happen: `if session_id:` above wrote no
                    # segment, and the payload was never processed. Re-arm so
                    # the next message on this connection tries again, rather
                    # than running on the new provider with no history and
                    # saying nothing about it -- which is the failure the switch
                    # marker exists to make visible.
                    #
                    # This cannot duplicate a replay. The two outcomes are
                    # exhaustive: no session means the target read nothing, and
                    # a session means the branch above already cleared this flag
                    # and the next plan() answers NOT_NEEDED.
                    #
                    # Only THIS outcome re-arms. Deterministic refusals never
                    # set switch_planned, so one-switch-per-connection still
                    # holds for every non-failure path.
                    seed_switch = True
                    switch_planned = False
                if resume_unverified:
                    # The id the browser handed us may be stale, from another
                    # machine, or -- the common case -- from a session recorded
                    # under a DIFFERENT working directory: `claude --resume`
                    # resolves ids per project, so an id adopted from the
                    # transcript list is rejected whenever the panel's workdir is
                    # not the one that session ran in.
                    #
                    # Drop it so it is never retried, and remember it, or the
                    # client re-sends the same dead id on every message and the
                    # channel never recovers.
                    dead_seeds.add(session_id)
                    session_id = None
                    resume_unverified = False
                    frame["resume_reset"] = True

                    # REPLAY THE MESSAGE. Telling the operator "the next message
                    # will start a new thread" was the bug: their message had
                    # nothing wrong with it, and it was discarded -- the turn
                    # showed `failed` and they had to retype it. The only thing
                    # wrong was the id WE attached. Drop the id, run the same
                    # text again, and the turn simply works.
                    #
                    # Guarded by `not got_text`: once any answer has streamed to
                    # the client, replaying would duplicate it. Bounded to one
                    # attempt, because the retry carries no --resume and so
                    # cannot fail this way twice.
                    if not got_text:
                        await ws.send_json({
                            "type": "retry",
                            "resume_reset": True,
                            "detail": "the saved thread was gone, so this message "
                                      "is being sent as a new one",
                        })
                        payload["_replay"] = True   # suppress a second `start`
                        pending = payload
                        continue
                    frame["detail"] = detail + (
                        "  (resumed session was rejected; the next message will "
                        "start a new thread)")
                await ws.send_json(frame)
            elif not got_result:
                # process ended without a result event: still close the turn out
                await ws.send_json({"type": "done", "session": session_id})
            else:
                resume_unverified = False
    except WebSocketDisconnect:
        pass
    finally:
        # Without this the reader task outlives the channel: one leaked task per
        # closed socket, each still awaiting receive_text() on a dead connection.
        # Killing any still-running child too -- a disconnected browser must not
        # leave a `claude` process running against the operator's plan.
        reader_task.cancel()
        # A disconnected browser must not leave WORKERS running either. Same
        # rule the line below has always applied to the pane's own child, now
        # covering the fan-out's children -- which are the ones nothing else
        # holds a handle to. No-op when no fan-out ran.
        orch = fanout_live["orch"]
        if orch is not None:
            orch.cancel()
        rt.kill_group()
        unregister_runtime(session_id, rt)


@app.websocket("/ws/term")
async def ws_term(ws: WebSocket):
    """Run the real `claude` TUI in a PTY and relay raw bytes <-> xterm.js.

    This renders the ACTUAL terminal (full parity) — it does NOT parse Claude's
    output. Drives the logged-in `claude` binary => Max-plan billing, no API key.
    """
    if await _reject_cross_origin(ws):
        return
    await ws.accept()
    if os.environ.get("ANTHROPIC_API_KEY"):
        await ws.send_text("\r\n\x1b[31mRefused: ANTHROPIC_API_KEY is set — that bills the API, not your Max plan.\x1b[0m\r\n")
        await ws.close()
        return

    # optional: resume an existing session, in its original cwd
    resume = ws.query_params.get("resume")
    req_cwd = ws.query_params.get("cwd")
    # CREATE the requested workdir rather than silently falling back to WORKDIR when it
    # does not exist yet. The chat path already does this (_ensure_workdir before spawn),
    # so the old isdir() test made the two disagree: the pane header said
    # ~/sutra-work-verified while the shell prompt sat in ~/sutra-ui-workspace, with
    # nothing on screen explaining the difference. Confined to the same root the settings
    # writer validates against, so this cannot be pointed at an arbitrary path.
    workdir = WORKDIR
    if req_cwd and providers.workdir_allowed(req_cwd):
        workdir = _ensure_workdir(req_cwd) or WORKDIR
    # ws_term never created WORKDIR: on a fresh machine the PTY spawn below
    # raised FileNotFoundError and the terminal socket died on connect.
    workdir = _ensure_workdir(workdir) or os.path.expanduser("~")

    # ?shell=1 -> the operator's OWN login shell, not the claude TUI. This endpoint
    # only ever ran `claude`, so the studio's terminal pane could not be used as a
    # terminal: no git, no ls, no build. $SHELL is what Terminal.app itself uses
    # (zsh on macOS since Catalina); falling back to /bin/zsh then /bin/sh keeps it
    # working when $SHELL is unset, as it is under a launchd/Finder launch.
    # `-l` makes it a LOGIN shell so the operator's PATH, aliases and rc files apply
    # -- without it, `claude`, `node` and `brew` are typically not even on PATH here.
    plain_shell = ws.query_params.get("shell") == "1"
    if plain_shell:
        sh = os.environ.get("SHELL") or "/bin/zsh"
        if not os.path.isfile(sh):
            sh = "/bin/zsh" if os.path.isfile("/bin/zsh") else "/bin/sh"
        args = [sh, "-l"]
    else:
        args = [CLAUDE_BIN]
        if resume and "/" not in resume and ".." not in resume:
            args += ["--resume", resume]

    # Fix #2/#4: classic (non-alt-screen) renderer + correct TERM/locale reduce TUI corruption
    env = dict(os.environ)
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("LC_ALL", "en_US.UTF-8")
    env["CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN"] = "1"

    master, slave = pty.openpty()
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=workdir, env=env,
        stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
    )
    os.close(slave)
    loop = asyncio.get_event_loop()

    async def pump_out():
        """PTY master -> browser. Send RAW bytes (#3): never decode server-side —
        a 64KB read can split a multibyte UTF-8 char; xterm.js decodes the stream safely."""
        try:
            while True:
                data = await loop.run_in_executor(None, os.read, master, 65536)
                if not data:
                    break
                await ws.send_bytes(data)
        except (OSError, RuntimeError, WebSocketDisconnect):
            pass

    reader = asyncio.create_task(pump_out())

    # Auto-fire Sutra (/core:start) + token-saving caveman on each FRESH session.
    # Skipped on resume (already activated in the original session).
    async def autostart():
        # INIT_CMD and /caveman are claude SLASH COMMANDS. In shell mode they would be
        # typed straight into the operator's zsh, which would run "/core:start" as a
        # path and print "no such file or directory" into a brand-new terminal.
        if resume or plain_shell:
            return
        caveman = ws.query_params.get("caveman", "1" if AUTO_CAVEMAN else "0") == "1"
        await asyncio.sleep(INIT_DELAY)
        if INIT_CMD:
            os.write(master, (INIT_CMD + "\r").encode("utf-8"))
        if caveman:
            await asyncio.sleep(1.5)
            os.write(master, "/caveman\r".encode("utf-8"))

    starter = asyncio.create_task(autostart())
    try:
        while True:
            msg = await ws.receive_text()
            try:
                m = json.loads(msg)
            except ValueError:
                continue
            kind = m.get("t")
            if kind == "i":                       # keystroke / injected text
                os.write(master, m.get("d", "").encode("utf-8"))
            elif kind == "r":                     # resize
                # FLOOR, not trust. A browser that measures a hidden or
                # not-yet-laid-out container reports a 2x1 terminal, and the TUI
                # reflows into a garbled sliver the moment that reaches the PTY --
                # permanently, because nothing re-sends a size afterwards. The
                # client refuses to send such a measurement (static/term.html);
                # this refuses to APPLY one, so a single buggy or hostile client
                # cannot wedge a session. 20x4 is below any usable terminal and
                # above every degenerate one.
                rows, cols = int(m.get("r", 24)), int(m.get("c", 80))
                if rows < 4 or cols < 20:
                    continue
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        starter.cancel()
        try:
            proc.send_signal(signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            os.close(master)
        except OSError:
            pass


# static assets (css/js if added later); index is served by "/" above
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.middleware("http")
async def _no_heuristic_caching(request, call_next):
    """Force revalidation on the panel document and its assets.

    Without a Cache-Control header, Chromium HEURISTICALLY caches a response
    for 10% of its Last-Modified age -- a JS file untouched for days stays
    "fresh" for hours, and an edited panel keeps rendering from the renderer's
    disk cache through any number of ordinary reloads. `no-cache` does not
    forbid caching; it forbids REUSE WITHOUT ASKING, and StaticFiles' etags
    make each ask a cheap 304. The panel is served off loopback, so the extra
    round-trip costs nothing.
    """
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.startswith("/static/"):
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp
