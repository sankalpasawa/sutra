"""Sutra UI — read-only local governance dashboard (Step 1: Panel A turn feed).

One FastAPI process: serves the static page, exposes a state snapshot, a paged
log read, and an SSE live-tail. Reads only — never writes a governance file.
Run: python3 -m uvicorn app:app --host 127.0.0.1 --port 7000
"""
import asyncio
import threading
import time
import fcntl
import json
import os
import pty
import re
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
import project_import as pi
import routine_links
import providers
import chat_store
import secrets as _secrets
import shadow_egress
import switch
import switch_egress
# SessionRuntime / CodexRuntime / AcpRuntime are no longer CONSTRUCTED here --
# ws_chat asks `adapter.new_runtime()` instead -- but they stay imported: other
# modules read them off `app`, and dropping a public name from this module is a
# breakage nothing in this change needs.
from session_runtime import (SessionRuntime, _drain_to_newline,
                             _tool_command, _tool_output, _tool_summary,
                             register_runtime, unregister_runtime,
                             lookup_runtime, NoLiveRuntime)
from acp_runtime import AcpRuntime
from codex_runtime import CodexRuntime
import provider_adapters
# The flag validators and EFFORT_LEVELS moved to provider_adapters with the
# argv builders that use them. Re-exported under their old names so nothing
# that referenced app._flag_list or app.EFFORT_LEVELS changed.
from provider_adapters import (_flag_str, _flag_list, _flag_money,
                               EFFORT_LEVELS)

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
# Modules (Org > Modules, 2.247.0): the folder ~/.sutra-ui/modules IS the
# registry; same per-request opt-out flag posture as workspace (flags.modules).
import modules_api
app.include_router(modules_api.router)
# The new Org screen's read-only aggregates (org2_api.py; holding BUILD-PLAN.md).
import org2_api
app.include_router(org2_api.router)
# The department screen's read-only aggregates (dept_api.py; holding
# plans/department-screen/LLD.md). Reads only; its one future POST files a
# proposal and applies nothing.
import dept_api
app.include_router(dept_api.router)
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
# It MIRRORS providers.DEFAULT_PERMISSION_MODE rather than restating a literal,
# so the shipped default has one home; since 2026-09-18 that is
# `bypassPermissions` (Full access) per founder direction. SAFETY rule 4's
# protection now rests on the unsafe-mode consent gate plus
# providers.PERMISSION_MODE_FLOOR, not on this constant being narrow --
# see test_perm_mode_default.py.
PERM_MODE = os.environ.get("SUTRA_UI_PERMISSION_MODE",
                           providers.DEFAULT_PERMISSION_MODE)
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

# _flag_str / _flag_list / _flag_money / EFFORT_LEVELS now live in
# provider_adapters.py, imported above under the same names.


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
            # Passed to the server process explicitly; it uses this to find the
            # same registry the panel is reading.
            "env": _mcp_env_for_children(),
        }
    if not servers:
        return ""
    return json.dumps({"mcpServers": servers})


def _mcp_env_for_children():
    """Environment a Sutra MCP child receives. The registry root comes from
    org_api.registry_root() -- the engine's real binding -- not from
    os.environ, which org_api no longer writes (RCA 2026-09-11, fix row 4)."""
    return {"SUTRA_NATIVE_HOME": org_api.registry_root()}


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
        "env": [{"name": k, "value": v} for k, v in _mcp_env_for_children().items()],
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


def project_permissions_for(workdir):
    """The `permissions` subtree a NORMAL chat at `workdir` would receive.

    WHY THIS EXISTS (forensic, 2026-09-14). Claude resolves project settings
    from the process cwd and does NOT walk up to the git root. A normal chat
    runs at the repo root and picks up <repo>/.claude/settings.json, whose
    permissions.allow carries a bare `Bash`. A Shadow-created worker runs in
    the delegate workdir, which has no .claude/ at all, so it received NO
    permission rules and every non-trivial Bash fell into the approval path
    with nobody to answer it (`-p`). Measured: 0 Bash denials across 76
    repo-root sessions, 16 across 116 sessions in the delegate workdir.

    So the worker is handed the SAME permissions object, by the same
    mechanism -- --settings is documented as "load ADDITIONAL settings from",
    i.e. it merges -- WITHOUT moving its cwd. Isolation is unchanged.

    PERMISSIONS ONLY. The project file also carries `hooks`, and those are
    deliberately dropped: four use paths relative to the repo root (`bash
    .claude/hooks/...`), which do not resolve from the worker's cwd, and
    seven point at /Users/abhishekasawa/... -- a home that does not exist on
    this machine, so they already fail in normal chat. Copying them would
    fire a failing hook on every Edit/Write/Bash the worker makes.

    The walk STOPS BEFORE $HOME: ~/.claude/settings.json is the USER layer,
    which the CLI loads by itself. Treating it as a project file here would
    duplicate a layer Claude already has.

    Returns {"permissions": {...}} or {} -- never raises. A missing or
    malformed file means "no inheritance", which is exactly today's
    behaviour, so the worst case is the bug we started from, not a crash.
    """
    # AN EMPTY WORKDIR IS NOT "HERE" (caught by this change's own test 14).
    # os.path.realpath("") resolves to the SERVER PROCESS's cwd, so a blank
    # or absent workdir would have silently inherited whichever project the
    # backend happened to be started from -- the repo root, in every dev run.
    # Falsy means no inheritance, which is the pre-fix behaviour.
    if not workdir or not str(workdir).strip():
        return {}
    try:
        d = os.path.realpath(os.path.expanduser(str(workdir)))
        home = os.path.realpath(os.path.expanduser("~"))
    except Exception:  # noqa: BLE001 -- a bad path must not stop a spawn
        return {}
    for _ in range(32):                       # bounded: no symlink loop can spin
        if not d or d == home:
            break
        cand = os.path.join(d, ".claude", "settings.json")
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as handle:
                    raw = json.load(handle)
            except (OSError, ValueError):
                return {}
            perms = (raw or {}).get("permissions")
            return {"permissions": perms} if isinstance(perms, dict) else {}
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return {}


# --------------------------------------------------------- the argv builders --
# THESE MOVED TO provider_adapters.py. The bodies are unchanged there (plus one
# additive `switches=` keyword each, which carries the per-provider settings
# flags); what is left here is a thin wrapper per name.
#
# The wrappers are not ceremony. `build_agent_args`, `build_codex_args`,
# `build_acp_args` and `codex_turn_config` are referenced by name in switch.py's
# transport table, in providers.py's comments, and directly by ~60 assertions
# across test_app.py, test_codex_runtime.py, test_codex_chat.py, test_switch.py
# and test_switch_seed.py. Keeping the names callable from app is what makes the
# move a MOVE rather than a rename every one of those has to follow.
#
# The two JSON blobs Claude's builder needs are built from app-level state (this
# directory, this interpreter, org_api.registry_root()), so app INJECTS them
# rather than provider_adapters importing app back.
provider_adapters.set_claude_hooks(_sutra_mcp_config, _sutra_allow_hook)

#: Sutra permission modes codex can enforce -> its sandbox mode. Re-exported
#: from provider_adapters, which is where the table now lives.
_CODEX_SANDBOX_FOR_MODE = provider_adapters._CODEX_SANDBOX_FOR_MODE
_CODEX_TURN_CONFIG = provider_adapters._CODEX_TURN_CONFIG


def build_agent_args(agent_bin, msg, perm_mode, session_id=None, model=None,
                     opts=None, stream_input=False, extra_settings=None,
                     switches=None, autocompact=None):
    """Claude's full argv for one turn. See provider_adapters.build_agent_args."""
    return provider_adapters.build_agent_args(
        agent_bin, msg, perm_mode, session_id=session_id, model=model,
        opts=opts, stream_input=stream_input, extra_settings=extra_settings,
        switches=switches, autocompact=autocompact)


def build_acp_args(agent_bin, model=None):
    """DeepSeek's ACP argv. See provider_adapters.build_acp_args -- which takes
    two more keywords, for a SECOND ACP agent (Cursor); this wrapper keeps the
    two-argument shape every existing caller uses."""
    return provider_adapters.build_acp_args(agent_bin, model)


def codex_mode_note(perm_mode):
    """None when codex can honour `perm_mode`, else the divergence to STATE.
    See provider_adapters.codex_mode_note."""
    return provider_adapters.codex_mode_note(perm_mode)


def codex_turn_config(opts, model=None):
    """`-c key=value` pairs for one codex turn's options. See
    provider_adapters.codex_turn_config."""
    return provider_adapters.codex_turn_config(opts, model)


def build_codex_args(agent_bin, perm_mode, workdir, model=None, session_id=None,
                     opts=None, switches=None):
    """The full argv for one `codex exec` turn. See
    provider_adapters.build_codex_args."""
    return provider_adapters.build_codex_args(
        agent_bin, perm_mode, workdir, model=model, session_id=session_id,
        opts=opts, switches=switches)


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


def _list_every_chat():
    """True when the rail should list EVERY transcript, not just Sutra's own.

    Two inputs, env first so a diagnosis never depends on stored state:
      SUTRA_UI_ALL_CHATS=1   -- the escape hatch that already existed
      settings chat_scope    -- the operator's own choice, "sutra" | "all"

    IT IS A SETTING, NOT A NEW DEFAULT (founder, 2026-09-13). The scoped list
    is the owner's decision of 2026-09-09 and stays the default; an operator
    who uses Sutra as the one place to see all their work turns this on and it
    persists in ~/.sutra-ui/settings.json, outside the app bundle, so it
    survives a reinstall and an auto-update.

    Fails soft to the default: an unreadable settings file must not change what
    the rail shows."""
    if SESSION_LIST_UNSCOPED:
        return True
    try:
        return providers.load_settings().get("chat_scope") == "all"
    except Exception:                                     # noqa: BLE001
        return False


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
    # ROUTINE RUNS ARE SUTRA'S OWN CHATS (founder, 2026-09-13). Sutra's runner
    # launches them (launchd -> run-routine.py -> `claude -p`), so they are
    # conversations Sutra started -- they just never passed through chat_store,
    # which only indexes chats begun in the panel. Without them the default
    # scope showed an EMPTY Routines view on every fresh install: 0 of 1,207
    # routine runs on the founder's machine were in chat_store's index. Adding
    # them honours the 2026-09-09 decision (other tools' transcripts stay out)
    # rather than reversing it. Every routine run is a `claude -p` session, so
    # they join the claude id set. Fails soft: no runs tree, no additions.
    try:
        claude_ids |= set(routine_links.by_session())
    except Exception:   # noqa: BLE001 -- a broken runs tree must not empty the rail
        pass
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


def _with_departments(rows):
    """Attach the department that owns each session's working directory.

    WHY HERE AND NOT IN session_reader. That module is a read-only browser over
    transcript files and knows nothing about the registry; keeping the join out
    of it means a broken or empty registry can never stop sessions listing.

    WHY cwd AND NOT TURN PLACEMENTS. The Dept view partitioned on `turn.domain`,
    which is a real signal but an incomplete one: a transcript that ran in the
    terminal carries domain:null by design, an unread one has no turns at all,
    and `askSide` skips classification deliberately (02-helpers.js:98-113). So
    the axis only ever covered the subset that happened to route. Every session
    has a cwd, and since 2026-09-08 every Claude project IS a department
    (project_import.py), so cwd answers for the whole list rather than part of
    it. Turn placements still render -- this decides which GROUP a chat sits in.

    A session under no imported project gets department=None. That is the same
    rule teamsutra states for tasks (teamsutra.py:110): a wrong address is the
    failure the placement layer exists to remove, so an unknown one stays null
    rather than being rounded to the nearest plausible department.

    Fails soft: any registry error leaves the rows exactly as they arrived."""
    try:
        depts = pi.imported_departments()
    except Exception as exc:                              # noqa: BLE001
        print("[app] department join skipped: %s" % exc, file=sys.stderr)
        return rows
    if not depts:
        return rows
    for r in rows:
        d = pi.department_for_cwd(r.get("cwd"), depts)
        r["department"] = ({"ref": d["ref"], "name": d["name"], "cwd": d.get("cwd")}
                           if d else None)
    return rows


def _shadow_task_row(session_id):
    """What the driven chat's status strip renders, or None.

    ONE mission at most drives a session -- MissionScheduler.start refuses a
    second on the same target -- so the first non-terminal match is the
    answer. Deliberately small: the objective the founder is owed, the turn
    budget, and the outcome being pursued. No transcript, no evidence, no
    state the pane could act on by itself.

    `mission_id` rides along because Take over and Stop act on the MISSION,
    not on the session -- the pane must not have to guess which one.
    """
    store = _mission_engine.MissionStore()
    for m in store.list():
        if m.get("target_session") != session_id:
            continue
        if m.get("state") in _mission_engine.TERMINAL:
            continue
        return {
            "mission_id": m["id"],
            "objective": m.get("objective") or "",
            "state": m.get("state"),
            "turns_used": m.get("turns_used") or 0,
            # THE TURN THE WORKER IS ON RIGHT NOW (founder, 2026-09-16).
            #
            # `turns_used` counts turns that FINISHED -- the engine increments
            # it after the boundary arrives -- so the strip read "turn 0 / 25"
            # for the whole of turn 1, "turn 1 / 25" for the whole of turn 2,
            # and so on: one behind, for the entire time a turn was actually
            # being worked. The engine has stamped `turn_open` for exactly
            # that span since 2026-09-16 (mission_engine.run_mission, written
            # after the say is delivered and cleared with the increment), and
            # the workspace task card has read it through shadowTurnNow ever
            # since. This row simply never carried it, so the one surface the
            # founder watches while a chat is being driven could not.
            #
            # `turns_used` is UNTOUCHED and still first: it is the budget
            # counter, max_turns is compared against it in the engine, and
            # nothing here may become a second one. This adds a field; it
            # replaces none. None when no turn is in flight, which is what
            # lets the reader fall back.
            "turn_open": m.get("turn_open"),
            "max_turns": m.get("max_turns") or 0,
            "done_when": [c.get("check") for c in (m.get("done_when") or [])
                          if c.get("check")],
        }
    return None


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
    if _list_every_chat():
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
        # IS SHADOW DRIVING THIS CHAT RIGHT NOW? The same ownership read the
        # send guard uses, so the pane can never say one thing while the
        # server enforces another. A plain fact on an ordinary row -- this is
        # NOT a chat type, and nothing else branches on it.
        try:
            row["shadow_driving"] = bool(
                shadow_runner.driving(row.get("id"))) \
                if row.get("source") == "claude" else False
        except Exception:   # noqa: BLE001 -- same rule as above
            row["shadow_driving"] = False
        # ...and WHAT it is driving, for the chat's own status strip: turn
        # progress and the outcome being pursued. A SIBLING field, deliberately
        # -- shadow_driving stays a bool so the guard's contract and its tests
        # are untouched, and this carries only what the strip renders.
        # Absent unless Shadow is actually driving, so an ordinary chat costs
        # one dict lookup and nothing else.
        row["shadow_task"] = None
        if row.get("shadow_driving"):
            try:
                row["shadow_task"] = _shadow_task_row(row.get("id"))
            except Exception:   # noqa: BLE001 -- a strip is never worth a 500
                row["shadow_task"] = None
    # AND the department that owns each row's working directory, so the Chats
    # rail can group by department. Runs last and fails soft, so an unreadable
    # registry costs the grouping and never the list. See _with_departments.
    #
    # AND the routine run that produced it, where one did. A routine run IS a
    # chat -- `claude -p` writes a real transcript and reports its session id --
    # so these were already in the list, indistinguishable from hand-started
    # work. On the founder's machine 1,009 of 1,208 rows are routine runs, which
    # is the whole reason the rail needs to separate them. Cached on the runs
    # tree's mtimes; fails soft to routine:None.
    return routine_links.attach(_with_departments(rows))


# ---------------------------------------------------------------- live sync ---
# Sutra READS Claude's transcripts, and until now it read them once, at boot.
# Anything typed in Claude afterwards was invisible until the panel was reloaded,
# which makes the two look like separate programs that happen to share a folder.
# This is the half that makes them one thing: the server watches the transcript
# directory and tells the panel what changed, as it changes.
#
# STAT POLLING, NOT FILESYSTEM EVENTS. FSEvents/watchdog would be tidier and is a
# dependency this runtime does not have -- the bundled Python ships exactly
# fastapi, uvicorn and websockets, and adding one to a 95MB payload for a 1-second
# timer is a bad trade. sr.index() opens no files, so the poll costs one stat per
# transcript and is flat in history size.
#
# SSE, NOT A WEBSOCKET. The traffic is one-way and the browser reconnects on its
# own; a socket would be a second lifecycle to get wrong for no gain.
#
# RESTORED 2026-09-11: 2.254.0 (3e8e2e04) deleted this block while leaving both
# names in use inside gen() below, so the stream served its opening `sync` frame
# and then died on the first sleep with `NameError: SESSION_POLL_S`. The panel
# therefore listed sessions at boot and never updated again. Values are the
# originals, not new guesses. test_sessions_stream.py pins both.
SESSION_POLL_S = 1.5
SESSION_HEARTBEAT_S = 25        # keeps proxies and idle timeouts from closing it


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
            # Stat-first: only a live agent file is opened, and only as far as
            # its first user record (session_reader.live_agents). list_agents
            # parsed every agent under the session and dropped the idle ones
            # after the fact -- 113 parses to keep 2, every 2 s (2.278.8).
            for a in sr.live_agents(sid):
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

#: Serializes the DeepSeek ACP connect DURING FIRST RUN ONLY. The gemini-cli
#: fork writes shared ~/.gemini state (installation_id, projects.json) on its
#: first launch with a write-tmp-then-rename that is NOT concurrency-safe: two
#: panes/missions spawning `deepseek --acp` within the same second race on
#: projects.json, and the loser crashes mid-write and closes stdout -- the
#: operator sees "ACP process closed stdout" and ~/.gemini is left littered
#: with orphaned projects.json.*.tmp files (measured: four in one second on the
#: founder's machine, 2026-09-13). Holding this across spawn+authenticate+
#: session/new lets the first connect finish first-run init before the next
#: starts. It engages ONLY while first run is pending (installation_id absent),
#: so steady state has zero contention -- a stuck connect can never wedge other
#: panes once the fork has run once. deepseek is the only id that touches
#: ~/.gemini; codex and claude are unaffected.
_ACP_CONNECT_LOCK = asyncio.Lock()


def _with_stderr(base, tail):
    """Append a child's stderr tail to a failure line, when there is one. The
    ACP child's stderr is where the real death reason lives (a node ENOENT, an
    ESM stack, a first-run config error); the JSON-RPC side only ever goes
    quiet. Empty tail -> the base line unchanged."""
    return ("%s\n\nagent stderr:\n%s" % (base, tail)) if tail else base


def _gemini_home_uninitialised():
    """True when the gemini-cli fork has never completed a first run -- its
    installation_id marker is absent. Cheap stat, checked to decide whether the
    first-run connect lock is worth taking."""
    try:
        return not (Path.home() / ".gemini" / "installation_id").exists()
    except Exception:
        return False


#: Providers the Shadow path can actually drive. NOT providers.ADAPTERS: that
#: set answers "can a CHAT PANE run this", and a pane has two transports
#: (SessionRuntime for Claude, AcpRuntime for DeepSeek) selected by ws_chat.
#: Shadow has one -- build_agent_args + SessionRuntime + demux_turn -- so its
#: answer is narrower. Adding an id here without building the transport for it
#: is exactly the bug the guard below closes.
SHADOW_PROVIDERS = frozenset({"claude"})


def _shadow_args(session_id=None, extra_settings=None, permission_mode=None,
                 autocompact=None):
    """Claude's argv for Shadow and its runtimes.

    `session_id` is the ONE addition (2026-09-11): passed through to
    build_agent_args, which already turns it into `--resume <id>`. Omitted
    -- the default, and every pre-existing caller -- the argv is byte for
    byte what it has always been, which is what keeps new-delegate spawning
    unchanged.

    `autocompact` follows the same rule and only `_worker_args` sets it: the
    SUPERVISOR's own session must not compact, because its context IS the
    founder's conversation with Shadow. None keeps this builder's argv byte
    for byte for the supervisor and (via `_decide_args` no longer calling
    here at all) for the reasoning lane.
    """
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
    # ONE SOURCE OF TRUTH FOR PERMISSION MODE. This passed a literal "plan",
    # so a founder who had put the app in acceptEdits got chat panes that
    # could write and delegates that could not -- the delegate would design
    # the change and then stop, because the flag forbade doing it. Shadow is
    # not a separate trust domain; it is the same operator working through a
    # different surface.
    #
    # NO SHADOW-SPECIFIC SETTING and no second clamp: this is the SAME call
    # ws_chat makes (app.py, `perm_mode = providers.effective_permission_mode(
    # settings["permission_mode"])`), so every gate is inherited rather than
    # re-implemented -- unsafe modes stay clamped to plan unless
    # unsafe_modes_allowed(), an unknown value still resolves to plan, and a
    # hand-edited settings.json is still clamped at the point of USE.
    # load_settings() always returns permission_mode (it is one of the three
    # contract keys), so there is no missing-key path.
    # `permission_mode` is the mode a WORKER was spawned with, handed back on
    # re-adoption so a restart cannot silently re-permission it (founder,
    # 2026-09-16). It is still clamped HERE, at the point of use, exactly as
    # the stored setting is: a stamp taken while unsafe modes were allowed
    # must not survive them being turned off. None -- every other caller --
    # reads the live setting, byte-identical to before.
    perm_mode = providers.effective_permission_mode(
        permission_mode or providers.load_settings()["permission_mode"])
    return build_agent_args(prov["bin_path"], "", perm_mode,
                            session_id=session_id, stream_input=True,
                            extra_settings=extra_settings,
                            autocompact=autocompact)


#: The system prompt Shadow's REASONING lane runs under, in place of Claude
#: Code's own. It says what the process is and what it may do, and nothing
#: about HOW to decide -- every rule the decider follows is in
#: shadow_runner._DECIDE_PROMPT, which is sent as the user turn and is
#: untouched by this. Keeping the two apart is what makes the lane swap a
#: transport change rather than a change to Shadow's judgement.
SHADOW_DECIDER_SYSTEM_PROMPT = (
    "You are Shadow's reasoning step inside Sutra. You are given one decision "
    "prompt and you answer it with the JSON object that prompt specifies, in "
    "a ```json fence, and nothing else. You have no tools, you run no "
    "commands, you read no files and you send nothing anywhere. Your reply is "
    "read by a validator, never by a person."
)


def _decide_args():
    """argv for Shadow's one-shot DECIDER -- the reasoning lane.

    WAS `_shadow_args`, and the split is the whole optimisation. That builder
    makes a full Claude Code agent: every built-in tool schema, the skills
    catalog, the agent roster, the MCP servers, the founder's settings and
    hooks. The decider is allowed to use NONE of it -- make_decider spawns it
    deliberately without SUTRA_MCP_SHADOW so it "can only return text, which
    the engine then validates" -- and it was paying for all of it on every
    call. Measured across September: 758 decider processes, ~28,260 tokens
    each, of which ~1,622 was the actual steering prompt. 94% scaffolding.

    WHAT IS UNCHANGED, and this is the part that matters: the prompt text
    (shadow_runner.render_decide_prompt), the model, the validator
    (mission_engine.validate_decision), the JSON contract, the one-process-
    per-decision lifecycle, and the provider gate below. Shadow reads the
    same thing and answers the same way. Only the envelope shrinks.

    WHAT TIGHTENS: the lane can no longer call a tool even in principle
    (`--tools ""`), and it stops inheriting the founder's permission mode --
    it ran at `bypassPermissions` whenever they did, which was authority it
    had no path to use and no reason to hold.

    Same provider resolution and same SHADOW_PROVIDERS refusal as
    `_shadow_args`: Shadow and its lanes run on Claude only in this build,
    and a founder on another provider must get that sentence, not a parse
    error from a CLI being handed Claude's flags.
    """
    detail = providers.active_provider_detail()
    prov = providers.provider_by_id(detail["id"]) if detail["id"] else None
    if not prov or not prov.get("bin_path"):
        raise HTTPException(503, "no usable provider for Shadow")
    if prov["id"] not in SHADOW_PROVIDERS:
        raise HTTPException(503,
            "Shadow and its delegates run on Claude only in this build; the "
            "active provider is %r (%s). Switch to Claude to use Shadow -- "
            "chat panes still run %s." % (prov["id"], prov["name"],
                                          prov["name"]))
    return provider_adapters.build_reasoning_args(
        prov["bin_path"], SHADOW_DECIDER_SYSTEM_PROMPT)


def _shadow_new_runtime():
    """The runtime Shadow's REASONING turn speaks through.

    ONE RUNTIME FACTORY FOR THE WHOLE APP (founder, 2026-09-15: "Shadow is an
    AI -- shouldn't it be using Sutra Chat for that too?").

    It was `srt.SessionRuntime()`, constructed by hand inside make_decider.
    That worked, but it meant the one place in Sutra that decides WHICH
    runtime class speaks to a provider -- provider_adapters.get(id) ->
    adapter.new_runtime(), which is what ws_chat asks -- was bypassed for
    Shadow's own thinking. Two ways to obtain a model runtime is one too
    many: an adapter change (a new provider, a different runtime class for
    Claude) would reach every chat pane and silently miss Shadow.

    So Shadow now asks the SAME factory. `_shadow_args` above is unchanged
    and still resolves the provider, still enforces SHADOW_PROVIDERS and
    still inherits the founder's permission mode through the same
    effective_permission_mode() call ws_chat makes -- this only replaces the
    `new SessionRuntime()` line with the adapter's answer.

    WHAT THIS DELIBERATELY DOES NOT ADOPT, and it is the whole of the
    "behind the scenes" in the founder's question: chat_store. That reverse
    index IS the definition of a Sutra chat (_owned_transcripts), so a record
    here would put Shadow's private prompts, its decision JSON and its
    reasoning into Chats as an ordinary conversation. Shadow's thinking stays
    headless: no sutra_id, no index row, no registry entry, no resumable
    session, and -- because SUTRA_MCP_SHADOW is still not in the spawn env --
    no tools. It can only answer.

    Never fatal: an adapter this build has not registered falls back to the
    class Shadow always used, so a missing adapter costs the unification, not
    Shadow.
    """
    try:
        detail = providers.active_provider_detail()
        adapter = provider_adapters.get(detail["id"]) if detail else None
        if adapter is not None:
            return adapter.new_runtime()
    except Exception:           # noqa: BLE001 -- reasoning must not die here
        pass
    import session_runtime as _srt
    return _srt.SessionRuntime()


def _shadow_workdir_for_delegates():
    """Delegates work where the founder works (their objectives point at the
    real repo), under the SAME permission mode every chat pane runs at --
    see _shadow_args. It said "but in PLAN mode" while that was hardcoded."""
    settings = providers.load_settings()
    return settings.get("workdir") or WORKDIR


def _worker_args(session_id=None, permission_mode=None):
    """argv for a Shadow-created WORKER chat -- the actor, not the supervisor.

    THE ONLY BUILDER THAT INHERITS PROJECT PERMISSIONS, and the split is the
    whole point of this function existing. `_shadow_args` is shared by three
    very different processes:

        supervisor  ShadowSession       cwd ~/.sutra-ui/shadow/workdir
        decider     make_decider        cwd ~/.sutra-ui/shadow/workdir
        WORKER      spawn_delegate_*    cwd _shadow_workdir_for_delegates()

    Only the worker acts on the founder's problem, so only the worker is
    handed the founder's project permissions. Shadow's own two processes keep
    exactly the argv they had -- `_shadow_args` defaults extra_settings to
    None -- which is what stops "Shadow supervises" from quietly becoming
    "Shadow has a shell in the founder's repo".

    The ATTACH path (ensure_runtime) deliberately does NOT come through here.
    It resumes a chat the FOUNDER created, in that session's own cwd, so the
    CLI resolves that project's settings natively -- there is nothing to
    inherit and nothing to inject.
    """
    # THE AUTONOMY CEILING BINDS THE WORKER, AND ONLY THE WORKER. It is
    # applied here rather than inside _shadow_args because that builder also
    # makes the supervisor's and the decider's argv, and those two are not
    # acting on the founder's problem -- capping them would change what
    # Shadow can THINK based on how much it may DO, which is not the setting
    # the founder chose. test_shadow_permission_inherit pins that equivalence
    # for _shadow_args and stays true.
    #
    # IT ALSO RE-CLAMPS A REMEMBERED MODE, which is the re-adoption case. A
    # mission stamped `acceptEdits` at L3 and resumed after the founder drops
    # to L2 comes back read-only: the LOWER of what it was given and what is
    # allowed now wins. That does not contradict "the worker keeps the
    # permissions it was given" (the rule that stopped an unrelated global
    # change from downgrading a live delegate) -- a deliberate autonomy change
    # is exactly the thing that SHOULD bind it, and the clamp is one-way, so
    # this can never hand back more than it was stamped with either.
    mode = _autonomy_ceiling(providers.effective_permission_mode(
        permission_mode or providers.load_settings()["permission_mode"]))
    return _shadow_args(
        session_id=session_id,
        permission_mode=mode,
        autocompact=worker_autocompact(),
        extra_settings=project_permissions_for(
            _shadow_workdir_for_delegates()))


#: The worker's compaction window, in tokens. The CLI takes 100k-1M.
#:
#: WHY THE WORKER AND NOTHING ELSE. A chat pane is the founder's own
#: conversation, in front of them. A worker is driven headlessly for as many
#: agentic turns as the objective takes, and nobody is watching its window.
#: Measured over September's 48 worker sessions: ZERO compaction boundaries,
#: context running 27.8k -> 327k inside a single mission, and 9.4% of worker
#: calls served above 200k -- the long-context tier -- for 23% of the lane's
#: tokens. The 1M window did not bound it; it only postponed the wall.
#:
#: 150000 IS A WINDOW, NOT A LIMIT, and the difference is the whole reason
#: this is safe. `--autocompact` is Claude Code's own mechanism: the worker
#: keeps its thread, keeps working and keeps answering Shadow across the
#: boundary. Nothing about the mission loop, the budget, the checks or the
#: say path can observe it. What it removes is the long-context tier and the
#: unbounded tail.
#:
#: Overridable, and OFF is reachable: SUTRA_SHADOW_AUTOCOMPACT=0 (or any
#: junk) restores exactly today's argv, so a founder who wants the old
#: behaviour back needs one env var and no build.
WORKER_AUTOCOMPACT = "150000"


def worker_autocompact():
    """The `--autocompact` value a worker spawned RIGHT NOW would carry, or
    None to pass the flag at all. Resolved at CALL time, like every other
    Shadow setting, so a change binds the next spawn without a restart."""
    raw = os.environ.get("SUTRA_SHADOW_AUTOCOMPACT", WORKER_AUTOCOMPACT)
    try:
        tokens = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    # the CLI's own documented band; anything outside it would be rejected at
    # the argv parser, which is a dead worker rather than a wide window
    return str(tokens) if 100_000 <= tokens <= 1_000_000 else None


def _autonomy_ceiling(mode):
    """Lower `mode` to what the current autonomy level allows. NEVER RAISES IT.

    A CEILING, NOT A SOURCE, and that distinction is the whole reason this is
    a separate function instead of a branch inside the resolver below. There
    is still exactly ONE place a permission mode comes from --
    providers.effective_permission_mode over the founder's own setting -- and
    Shadow is still not a separate trust domain. This only ever narrows the
    answer that call already gave.

    The one-way property is what makes it safe, and it is asserted directly
    (test_shadow_autonomy: for every mode x every level, the result is never
    wider than the unclamped answer) rather than left to be read off this
    docstring. `plan` is the floor of PERMISSION_MODES, so clamping to it can
    never widen anything, whatever the founder's setting happens to be.

    NEVER RAISES: mission_engine.autonomy() degrades to L3 on an unreadable
    store, and L3 returns `mode` untouched -- i.e. a broken settings file
    leaves the historical behaviour in place rather than silently freezing
    every worker into read-only.

    THE FLOOR IS PERMISSION_MODE_FLOOR, NOT DEFAULT_PERMISSION_MODE. Those were
    the same constant until the shipped default became `bypassPermissions`
    (2026-09-18); returning the default here would have made a worker the
    founder's autonomy level says MAY NOT WRITE come back with full access.
    """
    if _mission_engine.worker_may_write():
        return mode
    return providers.PERMISSION_MODE_FLOOR         # "plan"


def worker_permission_mode():
    """The mode a worker spawned RIGHT NOW would run under.

    One resolver, so the value stamped on the mission and the value baked
    into argv can never disagree -- which is the whole point of stamping it.

    The autonomy ceiling is applied HERE rather than at the argv builder so
    the STAMP records what the worker actually got. A mission stamped
    `acceptEdits` while the founder was at L2 would be a lie the re-adoption
    path then replayed.
    """
    return _autonomy_ceiling(providers.effective_permission_mode(
        providers.load_settings()["permission_mode"]))


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


#: The worker's own assertion that a check is satisfied. The manifest has
#: asked for these lines since delegation shipped -- "state DONE-CHECK lines
#: when checks pass" -- and NOTHING HAS EVER PARSED THEM. That is the whole
#: of the verify-tier bug: `verifier` was None on every production path
#: (start_mission_async defaults it, both resume paths passed a literal
#: None), so evaluate_done_when's verify arm returned False unconditionally
#: and a `verify` check could not pass no matter what the worker did or said.
#: Measured on m-5c2fca3f824b: three of its four checks were verify-tier and
#: were therefore unsatisfiable by construction.
_DONE_CHECK_RE = re.compile(r"^\s*DONE-CHECK\s*[:\-]\s*(.+?)\s*$",
                            re.MULTILINE | re.IGNORECASE)

#: How much of a long check the worker must quote for the assertion to count.
#: Checks run to a sentence or more and a worker that retypes one will trim
#: it; requiring the whole string would fail honest assertions, and matching
#: on a handful of characters would let an unrelated line satisfy a check.
_DONE_CHECK_MIN_QUOTE = 40


def _norm_claim(text):
    """Whitespace-collapsed, case-folded. Punctuation is KEPT: it is part of
    what makes a quoted check distinctive."""
    return " ".join(str(text or "").split()).casefold()


def _shadow_verifier(check_text, evidence=""):
    """Did the WORKER assert this check, by name, in its own output?

    DETERMINISTIC, AND DELIBERATELY NOT A JUDGE. No model is asked whether
    the work is good -- that would make Shadow the grader of its own delegate
    and would let prose auto-complete a mission. The only question here is
    whether the worker emitted the DONE-CHECK line the manifest asks for,
    quoting the check it is claiming. That is a fact about the transcript.

    THE EVIDENCE ALREADY EXCLUDES SHADOW'S OWN TURNS (shadow_egress tags
    every say, and evidence assembly drops them), so an instruction that
    happens to contain the check's wording cannot satisfy that check. This is
    the same property `contains_artifact` relies on.

    Returns False for anything it cannot establish -- no evidence, no line,
    a line that quotes too little to be distinctive.
    """
    want = _norm_claim(check_text)
    if not want or not evidence:
        return False
    for claimed in _DONE_CHECK_RE.findall(str(evidence)):
        got = _norm_claim(claimed)
        if not got:
            continue
        # A SHORT CHECK MUST MATCH EXACTLY. Containment is only safe once the
        # string is long enough to be distinctive: "tests pass" appearing
        # inside some other DONE-CHECK line is not an assertion ABOUT this
        # check, and precedence here is worth being explicit about.
        if len(want) < _DONE_CHECK_MIN_QUOTE:
            if got == want:
                return True
            continue
        if want in got or (got in want
                           and len(got) >= _DONE_CHECK_MIN_QUOTE):
            return True
    return False


#: WHAT EVERY WORKER IS TOLD, on top of its own brief.
#:
#: Appended rather than folded into the default, because the default is only
#: reached when a mission carries no manifest of its own -- and almost none
#: do: the create route composes one at mission creation, so a rule written
#: only into the default would reach nobody who started a task from the UI.
#:
#: TWO RULES, AND THE SECOND IS THE ONE THAT WAS MISSING (founder,
#: 2026-09-16). Measured on m-5c2fca3f824b: the worker made 277 Bash calls,
#: 44 Edits, 16 Reads and 9 Writes across backend, frontend and tests in a
#: single session, and spawned no subagent at all. Nothing had ever told it
#: it could. The rule below is a DECISION RULE, not encouragement: a worker
#: that splits a three-file change pays more in re-established context than
#: it saves, so the trigger is stated in terms of files, layers and
#: dependency -- not size or ambition.
_WORKER_AGREEMENT = """

WORKING AGREEMENT

Claiming a check. When a completion check is genuinely satisfied, say so on a
line of its own:

    DONE-CHECK: <the check's text, quoted closely enough to identify it>

That line is the ONLY thing that marks a `verify` check met. Shadow does not
infer it from prose, so a check you do not claim this way stays outstanding --
and a check you claim without having done the work is a false report, which is
worse than an outstanding one.

Reporting a turn. End each turn with one line of its own:

    REPORT: <one sentence: the meaningful outcome of this turn>

That line is the ONE thing a founder who never opened this chat will see for
this turn. It must be the OUTCOME, not the route you took to reach it.

  LEAD WITH WHAT IS NOW TRUE that was not true before -- created, changed,
  fixed, tested, verified. If nothing changed, lead with what prevented it and
  what that leaves undone.

  A BLOCKER LEADS. "Could not create shadow-test.txt because plan mode blocks
  edits; the file remains unwritten" is the whole report. Never bury the
  blocker behind the work you did before hitting it.

  NOT THE SETUP. Paths you resolved, files you only inspected, commands and
  checks you ran, plans you wrote on the way: none of that is the outcome. Do
  not narrate the investigation -- all of it is already in this chat.

  NOT THE OBJECTIVE BACK. A line that only repeats the objective is not news
  unless finishing it IS the news. "Done." says nothing either.

  KEEP IT SHORT. Aim under 90 characters: the founder sees a single line, and
  a longer one is cut off mid-thought.

This does not replace the DONE-CHECK line above. Everything else you write
stays in the chat, unabridged -- with one exception, which is the next clause.

Your last message. THE LAST MESSAGE YOU SEND IS THE DELIVERABLE, and it is
read by the founder, not by Shadow. Answer the task in it. Do not report on
yourself doing the task.

  THE TEST: would this sentence still be worth writing if the founder had
  done the work themselves and only wanted the result? If not, it belongs in
  the chat above, not here. Everything you leave out is still in this chat --
  nothing is lost, and the founder can open it whenever they want the work.

  PUT IN whatever the founder needs to USE the result and to judge how far to
  trust it: the answer itself, findings and conclusions, the artifact you were
  asked for, the evidence a claim rests on, sources, dates, figures, and any
  caveat, limit or thing left undone. A caveat is part of the answer. So is
  saying plainly that you could not do something.

  LEAVE OUT anything whose subject is YOU rather than the work: the steps you
  took, the order you took them in, tools you called, searches you ran, files
  you opened, what you tried first, how long it took, what you corrected in
  your own earlier answers, and any account of how the answer was produced.
  A reader who never sees this chat must not be able to tell how many turns
  it took or what you did in them.

  NOT A COMPARISON WITH YOUR OWN PREVIOUS ANSWERS. If something you said
  earlier was wrong, the last message simply states what is true now. The
  correction is not the news; the current answer is. Reconciling your drafts
  against each other is bookkeeping about your process, and the founder was
  never shown the drafts.

  NOT A RESTATEMENT OF THE BRIEF, not a status line, and not an audit of
  yourself against the checks -- DONE-CHECK already claims those, and the
  founder sees the verdicts beside your answer.

  LEAD WITH THE ANSWER. The first line is the thing that was asked for. If
  the task produced an artifact rather than a finding, say what it is, where
  it is, and what is in it -- then stop.

  LENGTH FOLLOWS THE TASK. A task with one thing to report ends in one line;
  a task whose answer is genuinely large ends in as much as that answer
  honestly needs. Neither pad nor truncate.

  This is the same rule as REPORT above, applied to the whole message rather
  than one line: the outcome, not the route.

Using subagents. You have Claude Code subagents (the Task tool). Decide per
task whether they help; most tasks do not need them.

  SPLIT when two or more parts touch different files or layers AND neither
  needs the other's result to begin -- a feature's backend and frontend, an
  implementation and the tests that cover it, or an investigation that would
  otherwise block your main thread.

  DO NOT SPLIT a change of a few files, anything genuinely sequential,
  anything where the second part depends on decisions made in the first, or
  work whose context you are already holding. A subagent starts cold; briefing
  it can cost more than doing the work.

  YOU REMAIN THE INTEGRATOR. Give a subagent one bounded piece with a stated
  interface, never the whole objective. You review what comes back, resolve
  disagreements between them, and you alone run the full test suite and report
  the result. A subagent's claim is not evidence until you have checked it."""


#: The floors Shadow cannot be talked out of (SHADOW.md section 2). ONE
#: writer: the settings page reads it and the brief quotes it.
SHADOW_FLOORS = (
    "destructive git operations",
    "external client repositories",
    "irreversible external sends",
)


def _rules_in_scope(target_session=None):
    """The founder-confirmed rule lines a brief must carry: global rules,
    plus the rules of the chat the task runs in. Best-effort, never raises."""
    lines = []
    try:
        import shadow_ledger
        rows = shadow_ledger.read_latest("instructions")
        block = shadow_precedence.replay_context(rows, scope="global")
        lines += [ln for ln in block.split("\n") if ln.startswith("[")]
        if target_session:
            block = shadow_precedence.replay_context(
                rows, scope="chat", scope_id=target_session)
            lines += [ln for ln in block.split("\n") if ln.startswith("[")]
    except Exception:                   # noqa: BLE001
        pass
    return lines


def _founder_memory():
    """The founder's memory text for a worker brief, or "". Never raises."""
    try:
        return _mission_engine.memory()
    except Exception:                   # noqa: BLE001 -- see _brief_facts
        return ""


def _brief_facts(mission):
    """What the task's Shadow chat needs to write a brief and cannot know
    on its own: where the worker runs, the rules in scope, the floors."""
    return {
        "repo": _shadow_workdir_for_delegates(),
        "why_now": mission.get("why_now") or "",
        "rules": _rules_in_scope(mission.get("target_session")),
        # THE MEMORY BOX, for the worker. Best-effort like everything else
        # here: a brief must not fail because the limits file is unreadable,
        # so a bad read costs this line and nothing more. Only `memory`
        # travels -- see _facts_text on why `behaves` does not.
        "about": _founder_memory(),
        "floors": list(SHADOW_FLOORS),
    }


async def _compose_brief(mission):
    """Shadow v4 (C2, ADR-043): the task's OWN Shadow chat writes the
    worker's opening brief at Start, once, onto the record.

    Falls back to the template in _delegate_manifest on any failure -- a
    chat that will not boot, a reply without a fence -- and says so in the
    ledger. A task never fails for want of a composed brief. Returns the
    mission as it now reads.
    """
    store = _mission_engine.MissionStore()
    try:
        chat = await _ensure_task_chat(mission)
        text = await chat.brief(mission, _brief_facts(mission))
    except Exception as exc:            # noqa: BLE001 -- template, audibly
        _shadow_ledger_safe({
            "kind": "brief", "mission_id": mission["id"],
            "summary": "brief fallback to the template: %s" % str(exc)[:140]})
        return mission
    if not text:
        _shadow_ledger_safe({
            "kind": "brief", "mission_id": mission["id"],
            "summary": "brief fallback to the template: no brief fence"})
        return mission
    try:
        m = store.load(mission["id"])
        if m is None:
            return mission
        # ONTO THE RECORD, NOT THROUGH amend(): amend bumps the version and
        # re-asks for a yes; the founder already pressed Start.
        m["manifest"] = text
        m["brief_by"] = "task_chat"
        store.save(m)
        _shadow_ledger_safe({
            "kind": "brief", "mission_id": mission["id"],
            "summary": "brief written by the task chat (%d chars)" % len(text)})
        return m
    except Exception:                   # noqa: BLE001
        return mission


def _worker_checks_block(mission):
    """The verify-tier checks, verbatim, as the lines the worker must claim.

    THE FAILURE THIS CLOSES (founder, 2026-09-17; mission m-f9bb797db28b).
    The worker was told to claim a satisfied check "quoted closely enough to
    identify it" -- and was never shown the checks. It had only the objective,
    so it quoted that:

        checks:  "A file named shadow-race-test.txt exists in the working
                  directory"
        claimed: "DONE-CHECK: Create shadow-race-test.txt containing exactly
                  shadow-race-pass"

    _shadow_verifier compares TEXT. Neither string contains the other, so both
    checks read unmet on a task that was finished in turn 1 -- and Shadow, told
    the verifier owns completion and it must never claim a check satisfied,
    could only conclude the work was wrong. It spent three more turns inventing
    reasons why: the wrong directory, then a trailing newline. The file was
    correct the whole time.

    So the worker is handed the exact strings. Nothing about the verifier, the
    tiers or the evaluation changes -- the two sides simply stop guessing at
    each other's wording.

    VERIFY-TIER ONLY. `founder_confirm` is the founder's signature and a
    DONE-CHECK line cannot satisfy it (MissionStore.confirm_check is its only
    writer), so listing one here would invite a claim that does nothing.
    `contains_artifact` wants its literal in the work's own output, not in a
    claim line. `verify` is the one tier _shadow_verifier is called for, so it
    is the one tier quoted here.

    THE BLOCK CANNOT SATISFY ITSELF. The manifest is tagged with
    shadow_egress.say_tag and evidence assembly drops Shadow's own turns, which
    is the same reason the agreement's placeholder DONE-CHECK line has never
    been able to pass a real check.

    THE PROBE IS NEVER IN HERE (founder, 2026-09-17). A check may carry a
    `probe` -- the filesystem test shadow_probe runs, which settles that check
    on its own and does not consult this claim at all. Only `check`, the
    human-readable sentence, is quoted below: the worker is told WHAT is being
    judged and never HOW, so it cannot write to the thing being measured
    because it was shown the measurement. For a probed check this block is a
    reporting convention and nothing more -- copying the line perfectly over a
    wrong file leaves the check UNMET, which is the whole point of the probe.
    """
    all_rows = [c for c in (mission.get("done_when") or [])
                if isinstance(c, dict) and str(c.get("check") or "").strip()]
    if not all_rows:
        return ""
    # THE CONTRACT IS EVERY ROW (founder, 2026-09-21): "the worker must never
    # be expected to satisfy acceptance criteria that were hidden from it".
    #
    # THE BUG THIS FIXES, AND D-SH-1 INTRODUCED IT. This block used to list
    # `verify` rows ONLY, and the reasoning above was sound for the question
    # it was actually answering -- which lines the DONE-CHECK convention
    # applies to. Then D-SH-1 moved FALLBACK_TIER from `founder_confirm` to
    # `judge`, so the ORDINARY row stopped being `verify` and became `judge`.
    # The consequence nobody re-derived: most of a task's acceptance criteria
    # stopped reaching the worker at all. It was being graded on a contract
    # it had never been shown, by a judge reading the artifact for properties
    # nobody had asked it to produce.
    #
    # TWO SECTIONS, BECAUSE THERE ARE TWO DIFFERENT THINGS TO SAY. The
    # CONTRACT is what the work must satisfy, and it is complete. The CLAIM
    # CONVENTION is a reporting mechanism that only `verify` rows use, and it
    # stays exactly as narrow as it was.
    #
    # THE MECHANISM IS STILL NEVER EXPOSED. No tier is named, no probe is
    # quoted, and nothing says which rows a human signs -- the founder's own
    # boundary: Shadow "may derive internal probes, verification methods, or
    # founder-confirmation decisions from the contract, but those internal
    # mechanisms do not need to be exposed to the worker". The worker is told
    # WHAT must be true and never HOW it will be established.
    contract = "\n".join("    - %s" % str(c["check"]).strip()
                         for c in all_rows)
    claim_rows = [c for c in all_rows if c.get("tier") == "verify"]
    out = (
        "\n\nWHAT THIS TASK MUST SATISFY. Every line below is part of the "
        "contract and\nyour work is judged against all of them, whether or "
        "not you mention them:\n\n"
        + contract + "\n"
    )
    if claim_rows:
        # ...and the claim convention, for the rows whose verifier reads a
        # DONE-CHECK line. `contains_artifact` is deliberately absent: it is
        # `check in transcript`, so inviting a verbatim copy of one would
        # make it self-satisfying (m-245777cf1467). `founder_confirm` is
        # absent because confirm_check is its only writer and a claim does
        # nothing. `judge` is absent because a judge reads the artifact, not
        # a sentence about it -- listing it would invite a claim that cannot
        # help and reads as an attempt to be graded on prose.
        lines = "\n".join("    DONE-CHECK: %s" % str(c["check"]).strip()
                          for c in claim_rows)
        out += (
            "\nOF THOSE, THESE ARE CLAIMED BY LINE. They are the exact "
            "strings Shadow's\nverifier matches, character for character. "
            "When one is genuinely satisfied,\nclaim it by copying its line "
            "below EXACTLY -- do not paraphrase it, do not\nshorten it, and "
            "do not substitute the objective's wording:\n\n"
            + lines +
            "\n\nA claim in your own words reads as NOT DONE, and a finished "
            "task then keeps\nbeing driven. A claim for work you have not "
            "done is a false report, which is\nworse. Claim only what is "
            "true, in the words above. The rest of the contract is\n"
            "established by Shadow from the work itself -- you do not claim "
            "those, you\nsimply have to have done them.\n"
        )
    return out


def _delegate_manifest(mission):
    """ONE manifest composer (was three copies). Scoped rules are folded
    in AT SPAWN TIME, never baked into the mission record -- a revoked
    rule must not re-fire on retry."""
    base = mission.get("manifest") or (
        "You are a delegate session working for the founder via Shadow. "
        "Objective: %s. Work step by step." % mission["objective"])
    # TAGGED like a say: the manifest is Shadow's own instruction, and it
    # carries the objective, so an untagged manifest turn let a
    # transcript-based check satisfy itself from the briefing that asked
    # for it. The tag is what keeps it out of the evidence -- which is also
    # what stops the DONE-CHECK line in the agreement below, a placeholder,
    # from ever reading as a claim about a real check.
    # The checks sit with the DONE-CHECK rule they belong to, between the
    # agreement and the chat's own scoped rules.
    return "%s %s%s%s%s" % (shadow_egress.say_tag(mission["id"]), base,
                            _WORKER_AGREEMENT,
                            _worker_checks_block(mission),
                            _scoped_instructions(mission.get("target_session")))


#: How a Shadow-started chat names itself in the ordinary Chats rail. ONE
#: writer of this format, so the rail, the tests and any later reader cannot
#: drift. It is a NAME, not a type: nothing branches on it.
SHADOW_CHAT_TITLE_PREFIX = "Shadow Task — "


def _shadow_chat_title(mission):
    """"Shadow Task -- <task>", from the mission's own objective.

    The objective is the only task-specific text that exists at spawn time,
    and it is what the founder actually asked for. Trimmed to fit
    _claude_session_meta's 90-char title budget so the rail shows a name
    rather than a truncated sentence.
    """
    task = " ".join(str(mission.get("objective") or "").split())
    if not task:
        task = "untitled"
    if len(task) > 60:
        task = task[:59].rstrip() + "…"
    return SHADOW_CHAT_TITLE_PREFIX + task


def _publish_delegate_chat(mission):
    """(sid) -> sutra_id: turn a proven delegate session into a NORMAL chat.

    Injected into spawn_delegate_session so shadow_runner never imports
    chat_store -- the same rule that keeps build_args and register injected.

    THERE IS NO SECOND CHAT REGISTRY. chat_store's reverse index IS the
    definition of a Sutra chat (see _owned_transcripts), so binding a segment
    is the whole of "publish"; nothing else is needed and nothing else would
    be honoured.

    ORDER IS THE SAFETY PROPERTY, and it is not the obvious one:

      1. target_session onto the MISSION, first. provision_target writes this
         only AFTER the spawner returns, so between publication and that
         write there would be a visible chat that no durable record names --
         and recover_on_boot() rebuilds ownership from exactly that record.
         A crash in that window would leave the founder able to open the chat
         and type, and ws_chat would --resume a session whose orphaned
         process is still alive. Writing it here closes the window. It also
         guarantees the terminal reaper can find the session to release, even
         if provision_target's own save later fails its seq guard.
      2. the title, best-effort: the rail reads a transcript's custom-title
         record, never chat_store.title, so this is the only thing that makes
         the row say "Shadow Task --". A miss costs a name, not a chat.
      3. the chat record -- on disk, still INVISIBLE: a record with an empty
         provider_history writes no index row.
      4. begin_segment -- THE PUBLISH MOMENT. The index row is the last write
         and the only visible one, so no partial failure can ever show a chat
         whose record is missing.
      5. target_chat onto the mission: the durable link, written last because
         it is the only step whose loss costs nothing operational.

    Idempotent: a session already bound to a chat returns that chat untouched,
    so a retry or a re-spawn can never mint a twin.
    """
    def publish(sid):
        import shadow_ledger      # local, like every other ledger caller here
        store = _mission_engine.MissionStore()

        def _stamp(**fields):
            """One field write, never fatal. Mission bookkeeping must not take
            down a session that started -- the same house rule the chat_store
            append in ws_chat follows."""
            try:
                m = store.load(mission["id"])
                if m is None:
                    return
                m.update(fields)
                store.save(m)
            except Exception:       # noqa: BLE001
                pass

        # 1. the session is recoverable from disk from here on
        _stamp(target_session=sid)

        # 1b. ADMIT IT. Execution has begun -- there is a live process, it has
        #     been sent the brief, and it has announced its session id. The
        #     record must say so NOW.
        #
        #     WHAT WAS WRONG. `spawn_delegate_session` publishes the chat from
        #     its frame hook the instant the id appears (~1s), but it does not
        #     RETURN until demux_turn finishes, which is the end of the whole
        #     first agentic turn. provision_target therefore returns late, and
        #     `start_mission` -- the only caller of the scheduler on this path
        #     -- admitted the mission only then. Measured on eight real starts:
        #     7, 10, 12, 14, 15, 31, 44 and 95 seconds after the click, median
        #     15s. For that entire window the founder watched a chat with a
        #     worker visibly talking in it beside a card reading QUEUED, turn
        #     0 of 20, and the state flipped only as the SECOND exchange began.
        #     The 2026-09-13 fold already made this argument for the chat
        #     ("the founder had started a task and had nothing to open"); it
        #     was simply never applied to the mission state.
        #
        #     NOT A NEW STATE AND NOT A NEW AUTHORITY. MissionScheduler.start
        #     is the one admitter, it is what start_mission already calls, and
        #     it is idempotent for a mission already running -- so the later
        #     start_mission call keeps doing everything else it does
        #     (on_attempt_start, _launch) and simply finds the state settled.
        #     The launch itself is NOT moved: the pump and the observer must
        #     still attach after the spawn turn.
        #
        #     THE CAP IS NOT BYPASSED. Admission is refused here unless a slot
        #     is genuinely free, exactly as the scheduler would decide; there
        #     is no await between the count and the call, so nothing can take
        #     the slot in between. If the cap did fill during the spawn, this
        #     does nothing and the existing late path decides as it always
        #     did -- a queued row must never be a row with a live worker.
        #
        #     Best-effort, like every other write in this function: mission
        #     bookkeeping must not take down a session that started.
        try:
            _m = store.load(mission["id"])
            if _m and _m["state"] == "brief_confirm" \
                    and len(store.list(states=("running",))) \
                    < _mission_engine.max_running():
                _mission_engine.MissionScheduler(store).start(mission["id"])
        except Exception:           # noqa: BLE001
            pass

        existing = chat_store.resolve("claude", sid)
        if existing:
            _stamp(target_chat=existing)
            return existing

        title = _shadow_chat_title(mission)
        # 2. best-effort: the transcript may not have been flushed yet, and a
        #    nameless chat beats no chat
        try:
            sr.append_title(sid, title)
        except Exception:           # noqa: BLE001
            pass
        # 3. on disk, invisible
        rec = chat_store.create(cwd=_shadow_workdir_for_delegates(),
                                branch="", title=title)
        # 4. visible
        chat_store.begin_segment(rec, "claude", sid)
        # 5. the durable link
        _stamp(target_chat=rec["sutra_id"])
        shadow_ledger.append("actions", {
            "mission_id": mission["id"], "kind": "spawn",
            "summary": "published session %s as chat %s (%s)"
                       % (sid, rec["sutra_id"], title)})
        return rec["sutra_id"]

    return publish


#: How a task's own Shadow chat names itself in the Chats rail (V3-3:
#: agents show in Chats as "Shadow: <task>"). ONE writer of this format.
SHADOW_TASK_CHAT_TITLE_PREFIX = "Shadow: "


def _task_chat_title(mission):
    task = " ".join(str(mission.get("objective") or "").split()) or "untitled"
    if len(task) > 60:
        task = task[:59].rstrip() + "…"
    return SHADOW_TASK_CHAT_TITLE_PREFIX + task


def _publish_task_chat(mission):
    """(sid) -> sutra_id: a task's Shadow chat becomes a NORMAL Sutra chat.

    Shadow v4 (C1, ADR-043). The mirror of _publish_delegate_chat for the
    OTHER of the two AIs: same chat_store steps in the same order (session
    stamped on the mission first, title best-effort, record on disk, then the
    visible segment, then the durable link), no scheduler admission (starting
    a task's Shadow chat is not starting the task), and idempotent.
    """
    def publish(sid):
        import shadow_ledger
        store = _mission_engine.MissionStore()

        def _stamp(**fields):
            try:
                m = store.load(mission["id"])
                if m is None:
                    return
                m.update(fields)
                store.save(m)
            except Exception:       # noqa: BLE001 -- never fail a spawn
                pass

        _stamp(task_chat_session=sid)
        existing = chat_store.resolve("claude", sid)
        if existing:
            _stamp(task_chat=existing)
            return existing
        title = _task_chat_title(mission)
        try:
            sr.append_title(sid, title)
        except Exception:           # noqa: BLE001
            pass
        rec = chat_store.create(cwd=_shadow_workdir(), branch="", title=title)
        chat_store.begin_segment(rec, "claude", sid)
        _stamp(task_chat=rec["sutra_id"])
        shadow_ledger.append("actions", {
            "mission_id": mission["id"], "kind": "spawn",
            "summary": "published task chat %s as chat %s (%s)"
                       % (sid, rec["sutra_id"], title)})
        return rec["sutra_id"]

    return publish


async def _ensure_task_chat(mission):
    """This task's Shadow chat, alive: the one in memory, else a --resume of
    the session the record names, else a fresh start. Raises on failure so
    the caller can fall back (a task never dies for want of its Shadow)."""
    mid = mission["id"]
    chat = shadow_task_chat.get(mid)
    if chat is not None and chat.alive:
        return chat
    chat = chat or shadow_task_chat.TaskChat(mid, new_runtime=_shadow_new_runtime)
    if chat.session_id is None and mission.get("task_chat_session"):
        chat.session_id = mission["task_chat_session"]
    if chat.session_id:
        try:
            await chat.resume(lambda sid: _shadow_args(session_id=sid),
                              _shadow_workdir(), register=register_runtime)
            return chat
        except Exception:               # noqa: BLE001 -- start fresh below
            chat.session_id = None
    await chat.start(_shadow_args, _shadow_workdir(), mission,
                     register=register_runtime,
                     publish=_publish_task_chat(mission))
    return chat


async def _delegate_spawn(mission):
    """Spawn ONE worker for `mission`, and record what it was spawned with.

    THE ONE SPAWNER (was four identical copies: the default provisioner, the
    goal attempt, start_now and retry). They had already drifted to the same
    five arguments; folding them means the stamp below cannot be added to
    three of the four and forgotten in the last.

    THE STAMP is the mission's memory of its worker's permissions. Written
    BEFORE the spawn, because a spawn that dies still leaves a worker session
    on disk that a later boot may re-adopt, and best-effort because losing
    the stamp costs the re-adopted mode, never the spawn.

    `on_first_turn` IS WHERE TURN 1 GETS ITS NUMBER. The spawner waits out the
    whole first agentic turn and run_mission's `briefed` branch then skips the
    say-and-wait block that stamps `turn_open`, so turn 1 is the one turn the
    loop never names -- the card read "turn 0 of 25" for the whole of it while
    turns 2..n were right. mission_engine.open_first_turn is that missing
    stamp and this is its ONLY production caller: without the argument the
    field is never written outside the loop and the bug is exactly as it was.
    """
    try:
        store = _mission_engine.MissionStore()
        m = store.load(mission["id"])
        if m is not None and not m.get("worker_permission_mode"):
            m["worker_permission_mode"] = worker_permission_mode()
            store.save(m)
    except Exception:                   # noqa: BLE001 -- never fail a spawn
        pass
    # Shadow v4 (C2): the task's Shadow chat writes the brief when the
    # record has none; a record that already carries one (Retry, a founder
    # or Now-chat manifest) is sent as it is.
    if not mission.get("manifest"):
        mission = await _compose_brief(mission)
    mid = mission.get("id")

    def _name_the_first_turn():
        """Fired from the spawner's adoption hook -- the first frame that
        carries a session id, which is the instant the worker's turn 1 starts
        painting. open_first_turn swallows its own trouble and never lowers a
        count; a mission with no id (a bare fixture) simply has nothing to
        stamp."""
        if mid:
            _mission_engine.open_first_turn(
                _mission_engine.MissionStore(), mid)

    return await shadow_runner.spawn_delegate_session(
        _worker_args, _shadow_workdir_for_delegates(),
        _delegate_manifest(mission), register_runtime,
        publish=_publish_delegate_chat(mission),
        on_first_turn=_name_the_first_turn)


async def _default_delegate_spawner(mission):
    """Registered with the runner so PROMOTED queued missions (whose
    originating request is long gone) can still get a delegate."""
    return await _delegate_spawn(mission)


@app.on_event("startup")
async def _fix_deleted_cwd():
    """A backend launched from a versioned plugin folder (main.js sets cwd to
    RUNTIME.appDir) can start already sitting in a directory an update just removed.
    Registered first, before any other startup hook does relative-path work.
    """
    try:
        os.getcwd()
        return
    except OSError:
        pass
    safe = os.path.expanduser("~")
    try:
        os.chdir(safe)
    except OSError:
        pass
    print("[app] working directory was gone at startup; switched to %s" % safe, file=sys.stderr)


@app.on_event("startup")
async def _import_projects_as_departments():
    """Onboarding, done by code: every project on this machine becomes a
    department before the operator does anything (founder, 2026-09-08).

    HERE AND NOT AT IMPORT, for the same reason as the hook below: the test
    suites import app.py in-process and must not mint into whatever registry
    they happen to be pointed at. A startup hook fires only in a real server.

    ADD-ONLY. sync() never wipes -- a boot path that can delete a registry is
    one crash-loop away from doing it repeatedly. It mints what is missing and
    links what already exists, so this is safe on every launch and is also how
    a project you started yesterday shows up today.

    FAILS SOFT AND LOUD. A registry that cannot be written must not stop the
    panel serving; it must also not fail silently, or the operator is left
    looking at an empty Org screen with no reason given.
    """
    # OPT-OUT FOR SEEDED REGISTRIES. test_app.py stands up a real server against
    # a fixture org and asserts exact d-paths; minting the operator's own
    # projects into it gives that registry a second writer and the ordinals
    # move. Anything that seeds a registry and then asserts its shape sets this.
    if os.environ.get("SUTRA_SKIP_PROJECT_IMPORT"):
        return

    # OFF THE EVENT LOOP (speed unit, 2026-09-15). sync() reads transcripts to
    # find each project's folder and spawns one `git` per project; run inline
    # here it held the loop -- and with it every panel request -- until it was
    # done, and startup handlers run before uvicorn accepts a connection at all.
    # A daemon thread lets the panel answer immediately; the tree gains the new
    # departments on its next read, exactly the way a project started yesterday
    # already appears on the next launch. The engine's own locks cover the
    # concurrent mint against any read.
    def _run():
        try:
            result = pi.sync()
        except Exception as exc:                          # noqa: BLE001
            print("[app] project import skipped: %s" % exc, file=sys.stderr)
            return
        if result["created"]:
            print("[app] departments created from your projects: %s"
                  % ", ".join(result["created"]), file=sys.stderr)
        else:
            print("[app] departments already current (%d linked, %d skipped)"
                  % (result["linked"], result["skipped"]), file=sys.stderr)
    threading.Thread(target=_run, name="project-import", daemon=True).start()


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
async def _mend_runs_left_running():
    """A run still marked "running" belongs to a process that is no longer here.

    HERE AND NOT AT IMPORT, like the hooks above: the test suites import app.py in-process and
    must not rewrite anybody's run states as a side effect.

    Why it matters (owner, 2026-09-12: "I did type the question but I just didn't get the
    answer"): the send route refuses a message to a chat whose last run says "running", so one
    run left lying by a crash or a quit silences that conversation for good. Waiting runs are
    untouched -- they are waiting for a person and are meant to survive a restart.
    """
    try:
        from seo_agent import store as _seo_store
        n = _seo_store.reconcile_stale_runs()
        if n:
            print("[agents] %d run(s) left running by an earlier session marked stopped" % n,
                  file=sys.stderr)
    except Exception:  # noqa: BLE001 -- never let this stop the server coming up
        pass


@app.on_event("startup")
async def _shadow_apps():
    """Shadow v4 (C8): the two Shadow apps, only where the on-disk `shadow`
    link module already exists (instance-local, never a fleet seed). HERE AND
    NOT AT IMPORT, like every hook above: the suites import app in-process."""
    if not providers.shadow_enabled():
        return
    try:
        modules_api.ensure_shadow_apps()
    except Exception:                   # noqa: BLE001 -- never a boot failure
        pass


@app.on_event("startup")
async def _shadow_recover():
    if providers.shadow_enabled():
        # ONE RECOVERER PER HOME (founder, 2026-09-16). Everything below
        # rewrites a store another live backend may be driving right now, and
        # two of these steps are destructive in ways the per-mission loop
        # lease never sees: _clear_stale_start_requests erases a start the
        # other process has in flight, and the boot queue sweep at the bottom
        # of this block can spawn a SECOND real delegate for one mission
        # (provision_target returns early on target_session BEFORE it awaits
        # the spawner, and the spawner waits out a whole first turn). So the
        # claim gates the whole block, that sweep included. See
        # shadow_home_lock for why the founder-triggered drains and _launch
        # are deliberately NOT gated.
        #
        # (Naming the sweep in prose rather than by symbol is deliberate:
        # test_shadow_run_limit's test_67 reads this function's SOURCE and
        # asserts the restart sweep precedes the queue drain in it.)
        import shadow_home_lock          # local, like every ledger caller here
        import shadow_ledger
        _owned, _holder = shadow_home_lock.claim_recovery()
        try:
            # one row per process, whichever way this goes: it makes "five app
            # boots in eight seconds" visible AS five boots rather than as an
            # inference over pids. pid and build are stamped by append itself.
            shadow_ledger.append("actions", {
                "mission_id": None, "kind": "boot",
                "summary": "shadow boot: recovery %s"
                           % ("owned" if _owned
                              else "deferred to pid %s"
                                   % ((_holder or {}).get("pid") or "?"))})
        except Exception:
            pass
        if not _owned:
            # NOT permanent. This is the only caller of the block and it runs
            # once, so a bare return would strand every app_restart mission
            # paused for the life of this process -- and the instance that won
            # the lease is frequently the one that then dies (a crashloop, or
            # the self-updater launching its replacement over the top of it).
            try:
                shadow_home_lock.start_rearm(_shadow_recover)
            except Exception:
                pass
            return
        try:
            shadow_runner.recover_on_boot()
        except Exception:
            pass
        try:
            # a start the last process accepted but never finished is not a
            # pending start -- give those tasks their Start button back
            _clear_stale_start_requests()
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
        try:
            # SHADOW DRIVES from turn 1. Same argv builder and same empty
            # workdir Shadow's own session uses (SHADOW.md-only context,
            # fast turns) -- and deliberately WITHOUT SUTRA_MCP_SHADOW, so
            # the reasoning call has no shadow tools and can only answer.
            #
            # Shadow v4 (ADR-043): the task's OWN Shadow chat decides when it
            # is alive; the one-shot below is the fallback, byte-identical to
            # what ran before v4. Routed per decision by mission_id.
            # `_decide_args`, NOT `_shadow_args` (2026-09-19): the reasoning
            # lane buys no tools, no settings and no plugins, because it is
            # allowed to use none of them. See _decide_args for the numbers.
            _one_shot = shadow_runner.make_decider(_decide_args, _shadow_workdir(),
                                                   new_runtime=_shadow_new_runtime)

            async def _routed(context, _fallback=_one_shot):
                return await shadow_task_chat.route_decision(context, _fallback)

            shadow_runner.set_default_decider(_routed)
            # THE JUDGE IS BOUND BESIDE THE DECIDER (D-SH-1, 2026-09-20), on
            # the SAME argv builder and the same runtime factory -- so it
            # buys no tools, no settings and no plugins, for the same reason
            # the reasoning lane does not: it is allowed to use none of them.
            # It reads a diff handed to it as text and answers met / unmet /
            # cannot_tell.
            #
            # NOT ROUTED THROUGH THE TASK CHAT, deliberately. The decider is
            # routed there so a task's own Shadow conversation can steer it;
            # a judgement must NOT land in a conversation that has been
            # reading the worker's prose all mission, because the whole
            # property shadow_judge exists to hold is that the verdict was
            # formed from the artifact and not from anybody's account of it.
            shadow_runner.set_default_judge(
                shadow_runner.make_judge(_decide_args, _shadow_workdir(),
                                         new_runtime=_shadow_new_runtime))
        except Exception:
            pass
        try:
            # AFTER the decider is bound: a resumed loop is launched with
            # whatever DEFAULT_DECIDER holds at launch time
            await shadow_runner.resume_after_restart(
                _ensure_target_runtime, _validated_say,
                ensure_delegate_async=_ensure_delegate_runtime,
                # THE RESUMED LOOP GETS THE SAME EVALUATOR AS A FRESH ONE.
                # Both resume paths passed a literal None, so a mission that
                # had survived a restart could never satisfy a verify check
                # again even once one was wired.
                verifier=_shadow_verifier)
        except Exception:
            pass
        try:
            # AND THE QUEUE, LAST. A restart is the one free slot nobody
            # asked for: recover_on_boot pauses what the app was driving, and
            # resume_after_restart deliberately leaves a delegate paused
            # while its worker may still be writing -- so an install can come
            # up with room under the cap and tasks waiting for it, and
            # nothing on the way in would have noticed.
            #
            # A QUEUED ROW IS THE SAFE ONE TO START HERE, and it is the only
            # kind this touches. The fence resume_after_restart keeps exists
            # because a paused delegate may have a live process on its
            # transcript; a queued mission has never been provisioned at all
            # (it spawns nothing until promotion), so promoting it starts a
            # worker where there was none rather than a second one.
            #
            # Bounded and idempotent: drain_queue stops the moment the cap is
            # full or the queue is empty, and it is the same sweep the
            # settings route and every founder action use.
            await shadow_runner.drain_queue(_validated_say)
        except Exception:
            pass


@app.on_event("shutdown")
async def _shadow_shutdown():
    try:
        shadow_runner.shutdown()
    except Exception:
        pass


def _shadow_feed_items():
    """The rows Now may show: the feed filtered by the relevance rule
    (shadow_feed.live_items, 2026-09-16). One reader for the endpoint and
    the dot. The dot counts only the `new` rows among them: a card the
    founder has opened (`seen`) stays on Now but no longer counts."""
    import shadow_feed
    import mission_engine as _me
    try:
        return shadow_feed.live_items(_me.MissionStore())
    except OSError:
        return []


def _shadow_alert_count():
    """New needs-you feed items -- the dot pill number."""
    return sum(1 for it in _shadow_feed_items() if it.get("state") == "new")


def _home_lock():
    """The recovery-lease module, imported at call time like every ledger
    caller in this file."""
    import shadow_home_lock
    return shadow_home_lock


@app.get("/api/shadow/status")
async def api_shadow_status():
    """The dot reads this: watching (green) / not (grey). Never 500s -- a
    down Shadow is a STATE the UI renders, not an error."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    sess = _SHADOW["session"]
    return {"watching": bool(sess and sess.alive),
            "session": sess.session_id if sess else None,
            # the mode Shadow ACTUALLY runs at, from the one source of
            # truth -- reporting a literal "plan" here would keep lying the
            # moment the founder raised the global mode
            "permission_mode": providers.effective_permission_mode(
                providers.load_settings()["permission_mode"]),
            "active_missions": shadow_runner.active_mission_count(),
            # WHO IS RECOVERING THIS HOME. Without it, a backend that stood
            # down at boot looks identical to a healthy one: the founder's
            # symptom is "my tasks are frozen and the app looks fine", and the
            # only evidence is a ledger row nobody reads.
            "recovery_owned": _home_lock().holds_recovery(),
            "recovery_holder_pid": (_home_lock().recovery_holder()
                                    or {}).get("pid"),
            # THE APPS PRESENCE IS HIDDEN FOR. hidden_apps() never raises, so
            # this cannot be the thing that makes a status read fail -- and
            # the docstring's promise above ("never 500s") still holds.
            #
            # THE OVERLAY DOES NOT READ THIS ONE. bootShadowOverlay already
            # awaits /api/shadow/settings beside this route and takes the
            # whole presence block from there, so a second copy would be two
            # sources for one answer. It is reported here because status is
            # the Shadow read that answers with nothing else attached, and a
            # caller holding only this route would otherwise have to guess.
            "presence_hidden_apps": shadow_presence.hidden_apps(),
            "alerts": _shadow_alert_count()}


#: What the Now box says before the founder's line (v4, V4-3). ONE writer:
#: the route reads it, the eval runner sends the same words.
SHADOW_INTAKE_PREFIX = (
    "[Intake] The founder typed this in the box that opens tasks (Now: "
    "\"What do you have in mind?\"). Treat it as work to delegate, not as a "
    "question to answer: one mission block per distinct ask, target_mode "
    "\"new\", the founder's words as each objective, one short line of reply. "
    "If it is genuinely not work, say so in one line and emit no block.\n\n")


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
    # Shadow v4 (V4-3): the Now box is Shadow's intake. A line typed there
    # is one or more tasks to open, never a question to answer -- the same
    # words in the corner card are a conversation. The box says so.
    intake = bool(body.get("intake"))
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
        if intake:
            pre += SHADOW_INTAKE_PREFIX
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
    if "goal" in blocks:
        # A PROPOSAL, not a creation (slice 8). Nothing is written here: the
        # founder reads and edits it in a confirmation card and their
        # Confirm is what POSTs /api/shadow/goals. The target is the CHAT
        # THE FOUNDER IS IN -- the tab's scope_id -- so a goal can never be
        # silently bound to a chat other than the one under discussion, and
        # no chat is ever created for it.
        gspec = dict(blocks["goal"])
        gspec["target_session"] = gspec.get("target_session") or scope_id
        # honest about the two ways a proposal can be incomplete, so the
        # card asks instead of inventing
        gspec["needs_criteria"] = not gspec.get("done_when")
        gspec["needs_target"] = not gspec.get("target_session")
        out["goal_proposal"] = gspec
    # Shadow v4 (C3, ADR-043): the Now chat may answer one founder message
    # with SEVERAL mission fences, one per task. Each becomes its own
    # brief_confirm draft; `missions` carries them all in reply order and
    # `mission` stays the first so every existing reader is unchanged.
    created = []
    for mspec in blocks.get("missions") or []:
        store = _mission_engine.MissionStore()
        mode = mspec.get("target_mode") or "existing"
        # THE CHAT IN SCOPE IS THE TARGET -- the same rule the goal branch
        # above already follows, and SHADOW.md lets the model omit the id
        # ("<sid or omit>"). Without this an existing-target mission proposed
        # inside a chat landed with target_session None: the card said "an
        # existing chat" with no name and Start had nothing to attach to.
        # Only for target_mode "existing" -- a delegated mission provisions
        # its OWN session and must never be pointed at the founder's chat.
        target = mspec.get("target_session")
        if mode == "existing" and not target:
            target = scope_id
        try:
            m = store.create(mspec["objective"], mspec["template"],
                             target_mode=mode,
                             target_session=target,
                             done_when=mspec.get("done_when"),
                             manifest=mspec.get("manifest"))
            store.transition(m["id"], "brief_confirm", "proposed in chat")
            created.append(store.load(m["id"]))
        except ValueError:
            pass                      # invalid proposal: reply text stands
    if "limits" in blocks:
        # v4.1 (V4-7). "Start X, no turn limit" in ONE line: the limit binds
        # the task(s) that same reply drafted. With no task drafted, a limit
        # said here is about every task -- the default on the sheet
        # (SHADOW-V3 section 13.1, scope row).
        spec = blocks["limits"]
        if spec.get("scope") == "task" and created and "turns" in spec:
            merged = {"applied": [], "refused": []}
            for c in created:
                got = _apply_limits_fence(
                    {"limits": {"scope": "task", "turns": spec["turns"]}},
                    c["id"]) or {}
                merged["applied"] += got.get("applied") or []
                merged["refused"] += got.get("refused") or []
            if "running_at_once" in spec:
                got = _apply_limits_fence({"limits": {
                    "scope": "default",
                    "running_at_once": spec["running_at_once"]}}) or {}
                merged["applied"] += got.get("applied") or []
                merged["refused"] += got.get("refused") or []
            created = [_mission_engine.MissionStore().load(c["id"]) or c
                       for c in created]
            out["limits"] = merged
        else:
            out["limits"] = _apply_limits_fence(
                {"limits": {**spec, "scope": "default"}})
    if created:
        out["missions"] = created
        out["mission"] = created[0]
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
    if "module" in blocks:
        # D-M10: created immediately as a draft (new precedent, documented in
        # 2026-09-08-modules-design.md). A refused spec leaves the reply text
        # standing and says why, so Shadow never claims a module it did not get.
        try:
            out["module"] = modules_api.create_module(
                blocks["module"], created_by="shadow", session_id=sess.session_id)
        except modules_api.ModuleError as e:
            out["module_error"] = str(e)
    return out


# ------------------------------------------------- shadow home endpoints --
# PLAN-100 P6. All flag-gated. Instructions and watches are ledgered, never
# deleted: a revoked instruction stays on the record as inert history
# (archive-never-delete), and a watch toggle is an auditable act.
import mission_engine as _mission_engine
import shadow_intervention as _shadow_intervention
import goal_lifecycle as _goal_lifecycle
import goal_store as _goal_store
import shadow_precedence
import shadow_presence
import shadow_runner
import shadow_protocol
import shadow_task_chat
import shadow_forward

#: The restart half of the forwarding lane (2026-09-21). shadow_runner calls
#: this from _launch to re-offer founder lines that were accepted by a
#: TurnQueue which then died with its process. Injected rather than imported
#: because shadow_runner must not import app.
#: `revive=True`: the flush runs at launch, when any row left `dispatched`
#: was accepted by a TurnQueue that died with its process. Ordinary calls
#: leave it off -- see shadow_forward.pending for why that matters.
shadow_runner.FORWARD_FLUSH["fn"] = lambda mid: forward_to_worker(
    mid, revive=True)


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
    # best-effort, like the instruction read above: a settings page must not
    # 500 because the mission store is unreadable. The counts degrade to 0
    # and the cap still comes back.
    try:
        _tasks_store = _mission_engine.MissionStore()
        _run_n = len(_tasks_store.list(states=("running",)))
        _queued_n = len(_tasks_store.list(states=("queued",)))
    except Exception:                     # noqa: BLE001
        _run_n = _queued_n = 0
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
        "floors": list(SHADOW_FLOORS),
        # HOW FAR SHADOW MAY GO, and what that actually resolves to right
        # now. `worker_mode` is the point of the block: it is the mode a
        # worker spawned this second would really get, ceiling and all, so
        # the page can state the consequence rather than leave the founder to
        # infer it from a level name. It comes from the SAME resolver the
        # spawn uses, so the sentence on screen and the argv cannot drift.
        "autonomy": {
            "level": _mission_engine.autonomy(),
            "levels": list(_mission_engine.AUTONOMY_LEVELS),
            "confirm_top_tier": _mission_engine.confirm_top_tier(),
            "worker_may_write": _mission_engine.worker_may_write(),
            "worker_mode": worker_permission_mode(),
        },
        # The task limits this build actually runs at. BOTH are writable now
        # and both reads go through the same resolver the engine itself uses
        # -- max_running() is what admission enforces, turn_budgets() is what
        # MissionStore.create stamps onto a new mission -- so this page states
        # the limits actually kept rather than ones that are merely plausible.
        #
        # THE BUDGET WAS READ-ONLY UNTIL NOW, and the reasoning that kept it
        # so is worth keeping straight rather than deleting: it is chosen by
        # the KIND of work, and that is still true. What changed is only that
        # the founder may now override the default the kind supplies. It stays
        # PER-KIND for that reason -- `turn_budget_set` names the kinds that
        # carry an override, which is the only honest way to draw `auto`,
        # because setting a budget to exactly its default is a real choice and
        # comparing values would misread it as untouched. `watch` is absent
        # from `turn_budget_kinds`: its budget is never consumed.
        #
        # `running_now` rides along because the founder needs it to read the
        # cap honestly -- lowering the cap below what is in flight queues the
        # NEXT task, it does not kill the ones already working, and a bare
        # number cannot say that.
        # Shadow v4 (C7): the founder's own words, same store as the numbers
        "behaves": _mission_engine.behaves(),
        "behaves_max": _mission_engine.BEHAVES_MAX_CHARS,
        # the founder's own memory text. The learned-rule list ships beside
        # it under `global`/`per_chat` and is untouched -- two stores, two
        # questions (see mission_engine.MEMORY_MAX_CHARS).
        "memory": _mission_engine.memory(),
        "memory_max": _mission_engine.MEMORY_MAX_CHARS,
        "tasks": {
            "running_at_once": _mission_engine.max_running(),
            "running_at_once_min": _mission_engine.MIN_RUNNING,
            "running_at_once_max": _mission_engine.RUNNING_CEILING,
            "running_now": _run_n,
            "queued_now": _queued_n,
            "turn_budget": _mission_engine.turn_budgets(),
            "turn_budget_min": _mission_engine.MIN_TURNS,
            "turn_budget_max": _mission_engine.TURNS_CEILING,
            "turn_budget_set": _mission_engine.turn_budget_overrides(),
            "turn_budget_kinds": list(
                _mission_engine.settable_budget_kinds()),
            # WHAT SHADOW ACTUALLY OFFERS, which is now the founder's list
            # rather than four names compiled into the page. The client draws
            # the Delegate form AND the Settings chips off this one field, so
            # the two can no longer drift; `turn_budget` above covers the
            # whole catalogue so every chip can state its own budget.
            "offers": _mission_engine.offered_kinds(),
            "offers_min": _mission_engine.MIN_OFFERS,
            "offers_max": _mission_engine.MAX_OFFERS,
        },
        # HOW SHADOW SHOWS UP. It rides THIS payload rather than getting an
        # endpoint of its own because the overlay's boot already has to await
        # an answer before it may mount, and a dedicated presence GET would
        # make that two round-trips to learn one boolean.
        #
        # This is the STANDING choice only. The card's own "hide" control is
        # a dismissal that lives in the browser for one page load, and the
        # two are deliberately not the same state -- the card is visible when
        # both agree. There is nothing to report here about the session flag
        # because the server has never known it and does not start now.
        # HIDDEN_APPS is the narrower choice beside it: `corner_card` answers
        # "does the dot exist at all", this answers "not while I am in THIS
        # app". Both live in presence.json and both survive a restart; they
        # are separate keys because they are separate questions, and a
        # founder who hid the dot inside one app has not asked for it to go
        # everywhere. The client reads the hide list from HERE -- the copy on
        # /api/shadow/status exists for a reader that has only the status
        # route, and the overlay is not one of them.
        # NUDGES_PER_HOUR is the third presence key and the only one that is a
        # number: the rate the unsolicited pill is held to. It ships with its
        # own bounds for the reason `running_at_once` does -- the stepper draws
        # its ends from the server that clamps it, so the two cannot disagree
        # about where the edges are. The browser keeps NO default of its own:
        # if this field is missing the pill stays silent rather than falling
        # back to a number nobody set.
        # QUIET_HOURS is the fourth presence key and the only one with a clock
        # behind it: the other three answer "would Shadow show up at all", this
        # answers "not at this hour". `null` means not set, and it is null
        # rather than an empty object because "cleared" and "never set" are one
        # state on disk (shadow_presence.QUIET_HOURS_DEFAULT) and must stay one
        # state on the wire.
        #
        # QUIET_NOW RIDES ALONG BUT IS NOT THE GATE. It is what the settings
        # row STATES ("quiet now"), computed server-side so the page does not
        # have to re-derive it to draw itself. What actually gates a nudge is
        # the client's own live evaluation of the WINDOW -- this GET is not
        # polled and the overlay is pinned no-poll, so a boolean fetched at
        # boot is wrong an hour later, precisely at the boundary the setting
        # exists to honour. Reporting it anyway is what makes the server's
        # reading visible and therefore checkable against the client's.
        "presence": {
            "corner_card": shadow_presence.corner_card(),
            "hidden_apps": shadow_presence.hidden_apps(),
            "nudges_per_hour": shadow_presence.nudges_per_hour(),
            "nudges_per_hour_min": shadow_presence.MIN_NUDGES_PER_HOUR,
            "nudges_per_hour_max": shadow_presence.MAX_NUDGES_PER_HOUR,
            "quiet_hours": shadow_presence.quiet_hours(),
            "quiet_now": shadow_presence.quiet_now(),
        },
    }


@app.post("/api/shadow/settings/tasks")
async def api_shadow_settings_tasks(request: Request):
    """Write "Running at once" -- the only task limit the founder owns.

    WHY THIS IS A SEPARATE ROUTE and not a PUT over /api/shadow/settings:
    almost everything that GET returns is DERIVED (the floors are constants,
    memory is the instructions ledger, attention is the watch lists, the turn
    budget belongs to the kind of work). A whole-object write would invite a
    client to send those back and make the shape look settable when it is
    not. One route, one field, no ambiguity about what a write can move.

    RAISING THE CAP DRAINS THE QUEUE, IN THE BACKGROUND. Otherwise the
    setting is a promise the founder cannot see kept: tasks queued behind the
    old limit would sit there until unrelated work happened to finish.
    Promotion goes through the SAME path a finishing mission uses
    (MissionScheduler.on_terminal via shadow_runner.drain_queue), so a
    promoted row provisions its delegate and launches exactly as it always
    did -- this route adds no second way for a mission to start.

    WHY IT CANNOT BE AWAITED HERE. A promoted mission with target_mode "new"
    still has to SPAWN, and spawning a delegate takes minutes: awaiting the
    drain would hold this request open across it and let a client timeout
    cancel a promotion mid-spawn. That is the exact failure
    start_mission_async was written for ("second-flight fix"), and the same
    answer applies -- the drain is an app task, the answer is instant, and
    the mission files are the progress surface the UI re-reads.

    SO THE RESPONSE SAYS `starting`, NOT `promoted`. The number of slots the
    drain will try to fill is known here and is true here; which missions
    actually reached `running` is not knowable until the spawns land, and
    reporting ids this route has not seen admitted would be a guess wearing
    a result's clothes.

    LOWERING NEVER KILLS. See mission_engine.set_max_running: the overflow
    drains as work ends. The response says how many are over so the UI can
    tell the founder rather than leaving them to wonder why 7 are running
    under a cap of 3.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    if "running_at_once" not in body:
        raise HTTPException(400, "running_at_once required")
    try:
        value = _mission_engine.set_max_running(body["running_at_once"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store = _mission_engine.MissionStore()
    running_now = len(store.list(states=("running",)))
    queued_now = len(store.list(states=("queued",)))
    # how many the drain can actually take: free slots, bounded by the queue
    starting = _free_slots(store, value)
    if starting:
        _drain_queue_in_background("cap raised to %d" % value)
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "running_at_once set to %d (%d running, %d queued, "
                   "starting %d)" % (value, running_now, queued_now, starting)})
    return {"running_at_once": value,
            "min": _mission_engine.MIN_RUNNING,
            "max": _mission_engine.RUNNING_CEILING,
            "running_now": running_now,
            "queued_now": queued_now,
            "starting": starting,
            # honest about the one thing a lower cap cannot do
            "over_cap": max(0, running_now - value)}


@app.post("/api/shadow/settings/behaves")
async def api_shadow_settings_behaves(request: Request):
    """Write "How Shadow behaves" -- the founder's own words (Shadow v4 C7).

    One route, one field, like the cap above. The text lands in the task
    limits store (mission_engine.set_behaves) and binds the NEXT Shadow boot:
    the Now chat and every task chat read it in standing_context. A running
    Shadow chat keeps the words it booted with; that is the same rule the
    standing instructions follow, and the founder restarts Shadow to apply.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    if "behaves" not in body:
        raise HTTPException(400, "behaves required")
    try:
        value = _mission_engine.set_behaves(body["behaves"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "behaves set (%d chars)" % len(value)})
    return {"behaves": value, "max": _mission_engine.BEHAVES_MAX_CHARS}


@app.post("/api/shadow/settings/memory")
async def api_shadow_settings_memory(request: Request):
    """Write "What Shadow should remember" -- the founder's own words.

    THE TWIN OF behaves ABOVE, deliberately: one route, one field, the same
    limits store, the same boot binding. It does NOT touch the learned-rule
    list (`global` / `per_chat`) -- that record is append-only with its own
    confirmation provenance, and a text cursor over it would quietly rewrite
    what Shadow was told it had learned.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    if "memory" not in body:
        raise HTTPException(400, "memory required")
    try:
        value = _mission_engine.set_memory(body["memory"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "memory set (%d chars)" % len(value)})
    return {"memory": value, "max": _mission_engine.MEMORY_MAX_CHARS}


@app.post("/api/shadow/settings/budget")
async def api_shadow_settings_budget(request: Request):
    """Write "Budget per task" -- one kind's turn budget.

    WHY A SIBLING ROUTE AND NOT A SECOND FIELD ON /settings/tasks. That route
    earns its shape by being one route, one field, and two tests hold it to
    that (test_shadow_run_limit test_34 and test_35). Adding `turn_budget` to
    it would make both of them false and would reopen exactly the ambiguity
    its docstring closes -- what may a write move? Two single-field routes
    keep the answer a constant per route, and cost one decorator.

    WHAT MOVED, EXACTLY. The budget is still chosen by the KIND of work; that
    reasoning was right and survives. What is new is that the founder may
    override the number a kind supplies. So the body names a kind, and one
    write moves one kind -- a map body would need partial-failure semantics
    for a gesture that is always a single click.

    RESET IS `turns: null`, NOT A SENTINEL NUMBER. The store deletes the key,
    so "auto" is the ABSENCE of a setting rather than a magic value every
    reader would have to special-case, and a future change to a template
    default still reaches every kind the founder never touched.

    NO DRAIN, DELIBERATELY. The cap route schedules one because raising a cap
    promotes queued missions. A budget change promotes nothing and stops
    nothing: max_turns is stamped at create(), so this binds the NEXT task and
    leaves everything in flight on the number it started with. _free_slots and
    _drain_queue_in_background are not called here, and that is not an
    omission.

    IT REPORTS THE WHOLE MAP BACK. The settings page draws five things off
    these numbers (the row and four Delegate-offer chips), so returning the
    full effective map lets the client repaint from the server's answer rather
    than patching one key and trusting the rest -- the same rule the cap
    route's response follows.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    kind = body.get("kind")
    if not kind:
        raise HTTPException(400, "kind required")
    if "turns" not in body:
        raise HTTPException(400, "turns required (null resets to auto)")
    turns = body["turns"]
    try:
        value = _mission_engine.set_turn_budget(kind, turns)
    except ValueError as exc:
        # unknown kind, a kind with no budget to set (watch), or junk turns --
        # the store raises for all three and its message names which
        raise HTTPException(400, str(exc))
    overrides = _mission_engine.turn_budget_overrides()
    auto = kind not in overrides
    # templates(), not TEMPLATES: a founder-minted kind has a default too, and
    # indexing the built-ins would KeyError into a 500 the moment a budget was
    # set on a kind this install added rather than shipped with
    default = (_mission_engine.templates().get(kind) or {}).get("max_turns", 0)
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": ("turn budget for %s reset to auto (%d)" % (kind, value))
                   if auto else
                   ("turn budget for %s set to %d (auto is %d)"
                    % (kind, value, default))})
    return {"kind": kind,
            "turns": value,
            # `auto` is read off the store, never inferred by comparing the
            # value to the default: setting a budget to exactly its default is
            # a real choice, and comparing would redraw it as untouched and
            # take the reset control away
            "auto": auto,
            "default": default,
            "min": _mission_engine.MIN_TURNS,
            "max": _mission_engine.TURNS_CEILING,
            "turn_budget": _mission_engine.turn_budgets(),
            "turn_budget_set": overrides}


@app.post("/api/shadow/settings/autonomy")
async def api_shadow_settings_autonomy(request: Request):
    """Write "Autonomy" -- the level, the top-tier switch, or both.

    WHY BOTH FIELDS SHARE ONE ROUTE, when tasks and budget each got their
    own. The rule those two follow is "one route, one thing a write can
    move", and the thing this route moves is autonomy. The switch is not a
    second setting, it is a qualifier on the top LEVEL -- it has no meaning
    except in terms of L3, and the response has to restate both whichever one
    was sent, because changing either one changes what the other means on
    screen. Splitting them would mean two routes that must be read together
    to know the state, which is the ambiguity the one-field rule exists to
    prevent, not an instance of it.

    EITHER KEY MAY BE ABSENT; sending neither is the error. That keeps a
    toggle click from having to restate the level and risk stamping a stale
    one back over a change made in another tab.

    NOTHING RUNNING IS TOUCHED, and this route deliberately schedules no
    drain. Lowering autonomy does not kill a worker mid-turn (see
    mission_engine.set_autonomy); it binds the next turn, because autonomy()
    is read live at the top of every say. Raising it promotes nothing either
    -- a task held at L0 or L1 is PAUSED, and a paused task is resumed by the
    founder, not by a settings write. So the response says what is held
    rather than pretending to release it.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    if "level" not in body and "confirm_top_tier" not in body:
        raise HTTPException(400, "level or confirm_top_tier required")
    try:
        if "level" in body:
            _mission_engine.set_autonomy(body["level"])
        if "confirm_top_tier" in body:
            _mission_engine.set_confirm_top_tier(body["confirm_top_tier"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    level = _mission_engine.autonomy()
    top = _mission_engine.confirm_top_tier()
    # what is sitting in the waiting room BECAUSE of autonomy. The founder
    # has to resume these by hand, so the number is the honest counterpart to
    # "nothing running is touched" above.
    try:
        store = _mission_engine.MissionStore()
        held = len([m for m in store.list(states=("paused",))
                    if m.get("pause_reason") in ("autonomy_hold",
                                                 "autonomy_suggest",
                                                 "autonomy_top_tier")])
    except Exception:                     # noqa: BLE001 -- a count, never a reason to fail
        held = 0
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "autonomy set to %s (confirm_top_tier=%s, worker mode %s, "
                   "%d held)" % (level, top, worker_permission_mode(), held)})
    return {"level": level,
            "levels": list(_mission_engine.AUTONOMY_LEVELS),
            "confirm_top_tier": top,
            "worker_may_write": _mission_engine.worker_may_write(),
            "worker_mode": worker_permission_mode(),
            "held": held}


@app.post("/api/shadow/settings/offers")
async def api_shadow_settings_offers(request: Request):
    """Write "Delegate offers" -- the kinds of work Shadow offers to start.

    A THIRD SINGLE-PURPOSE ROUTE, for the reason the budget route gives: the
    cap route earns its shape by being one route, one field, and folding a
    third setting into it would reopen the ambiguity its docstring closes.

    THE BODY IS A VERB, NOT A LIST. `{"add": "review"}` or
    `{"remove": "watch"}` -- never `{"offers": [...]}`. Two reasons, both
    real. A whole-list write makes two quick clicks a lost update: the second
    POST carries a list built before the first one landed and silently undoes
    it. And the ledger row can say what the founder MEANT ("added review")
    rather than printing a before-and-after the reader has to diff.

    EXACTLY ONE VERB PER WRITE. Both together is refused rather than ordered,
    because there is no ordering a caller could rely on and no gesture in the
    UI that produces one.

    REMOVING UN-OFFERS; IT NEVER UN-DEFINES. mission_engine.remove_offer
    keeps the kind's definition so a finished mission of that kind can still
    be retried -- see the section header there. This route is a door for
    "start something NEW", which is why it refuses a retired kind while
    clone_for_retry happily rebuilds one.

    NO DRAIN, DELIBERATELY, and for a simpler reason than the budget route's:
    changing what is on offer starts nothing, stops nothing, and touches no
    mission record. Every task already created keeps the template it was
    created with.

    IT REPORTS THE WHOLE LIST BACK, plus the budget map, because the client
    repaints both the chips and the Delegate form from this answer rather
    than patching one key and trusting the rest.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    has_add, has_remove = "add" in body, "remove" in body
    if has_add and has_remove:
        raise HTTPException(400, "one of add or remove, not both")
    if not (has_add or has_remove):
        raise HTTPException(400, "add or remove required")
    try:
        if has_add:
            offers = _mission_engine.add_offer(body["add"])
            what = "added %s" % _mission_engine.clean_offer_name(body["add"])
        else:
            offers = _mission_engine.remove_offer(body["remove"])
            what = "removed %s" % _mission_engine.clean_offer_name(
                body["remove"])
    except ValueError as exc:
        # a junk name, the ceiling, or the last-offer floor -- the store
        # raises for all three and its message names which
        raise HTTPException(400, str(exc))
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "delegate offers: %s (now %s)" % (what, ", ".join(offers))})
    return {"offers": offers,
            "min": _mission_engine.MIN_OFFERS,
            "max": _mission_engine.MAX_OFFERS,
            "turn_budget": _mission_engine.turn_budgets(),
            "turn_budget_kinds": list(
                _mission_engine.settable_budget_kinds())}


@app.post("/api/shadow/settings/presence")
async def api_shadow_settings_presence(request: Request):
    """Write one standing Presence choice: "Corner card on every screen", or
    "Nudges per hour".

    A FOURTH SINGLE-PURPOSE ROUTE, for the reason the budget and offers
    routes give: the cap route earns its shape by being one route, one field,
    and folding a fourth setting into it would reopen the ambiguity its
    docstring closes.

    ONE WRITE STILL MOVES ONE FIELD. Two settings reach the founder through
    this route, and the body must name EXACTLY ONE of them -- both is a 400,
    neither is a 400. That is the offers route's shape (`{"add"}` or
    `{"remove"}`, never both), and it keeps the guarantee the single-field
    rule was protecting: what a write can move is a constant per request, so
    the answer the client repaints from is never a partial one. They share a
    route rather than splitting because they are the same question asked at
    two grains -- how Shadow shows up when nothing has happened -- and both
    land in the same presence.json.

    THE CARD SWITCH IS THE STANDING CHOICE, NOT A DISMISSAL. The card's own
    hide control is a browser-lifetime flag meaning "not right now"; this is
    the founder saying whether the card exists at all. Keeping them separate
    is what lets a dismissal expire at reload while this survives a restart --
    one state per meaning, rather than one flag asked to carry two.

    THE RATE IS THE MAXIMUM THE PILL IS HELD TO, and the server is the clamp:
    a number past an end stops at the end, junk is refused rather than guessed,
    and 0 is a real answer meaning "never unasked". The stored value comes back
    with its bounds so the stepper draws the ends the server will actually
    enforce.

    NOTHING IS STARTED OR STOPPED BY EITHER, so there is no drain here and no
    counts to report back: presence is a view preference, and no mission
    record reads it. The answer is the stored value, which is what the control
    repaints from -- never the optimistic one the client sent.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    named = [k for k in ("corner_card", "nudges_per_hour") if k in body]
    if len(named) != 1:
        raise HTTPException(400, "name exactly one of corner_card, "
                                 "nudges_per_hour")
    try:
        if named[0] == "nudges_per_hour":
            rate = shadow_presence.set_nudges_per_hour(body["nudges_per_hour"])
        else:
            value = shadow_presence.set_corner_card(body["corner_card"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if named[0] == "nudges_per_hour":
        _shadow_ledger_safe({
            "kind": "setting", "mission_id": None,
            "summary": "nudges per hour set to %d%s"
                       % (rate, " (never unasked)" if rate == 0 else "")})
        return {"nudges_per_hour": rate,
                "min": shadow_presence.MIN_NUDGES_PER_HOUR,
                "max": shadow_presence.MAX_NUDGES_PER_HOUR}
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "corner card on every screen set to %s"
                   % ("on" if value else "off")})
    return {"corner_card": value}


@app.post("/api/shadow/settings/quiet-hours")
async def api_shadow_settings_quiet_hours(request: Request):
    """Write "Quiet hours" -- the window Shadow will not speak unasked inside.

    ITS OWN ROUTE, not a third field on /settings/presence. That route's
    docstring earns its shape by holding fields that are the same question at
    two grains -- "how does Shadow show up when nothing has happened" -- and
    answers a request by naming exactly one of them. This is a different
    question: not whether Shadow shows up, but WHEN. It also carries a
    different body shape (an object or null, rather than a scalar) and a
    different clear semantic, and folding a third spelling into that route's
    exactly-one-of rule is how a route stops being readable.

    NULL CLEARS, ABSENT IS A MISTAKE, and the two must not be one request.
    `{"quiet_hours": null}` is the founder pressing clear and is a 200; a body
    with no quiet_hours key at all is a client bug and is a 400. Treating
    absence as a clear would let a malformed request silently delete a
    setting, which is the one failure a settings route must not have.

    THE CLAMP IS HERE, not in the control. <input type="time"> can only emit
    HH:MM, but a hand-written POST is not an input element -- so the store
    refuses junk, refuses a half window, and refuses start == end, and this
    route hands the store's own words back as the 400.

    NOTHING IS STARTED OR STOPPED BY IT, so there is no drain and no counts to
    report: quiet hours is a view preference and no mission record reads it.
    The answer is the STORED window plus the server's reading of whether it is
    quiet at this moment -- never the optimistic value the client sent.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    if not isinstance(body, dict) or "quiet_hours" not in body:
        raise HTTPException(400, "quiet_hours required (null to clear it)")
    try:
        window = shadow_presence.set_quiet_hours(body["quiet_hours"])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "quiet hours cleared" if window is None
                   else "quiet hours set to %s-%s"
                        % (window["start"], window["end"])})
    return {"quiet_hours": window,
            "quiet_now": shadow_presence.quiet_now()}


@app.post("/api/shadow/settings/presence/app")
async def api_shadow_settings_presence_app(request: Request):
    """Write "Hide for this app" -- Presence, per app.

    A FIFTH SINGLE-PURPOSE ROUTE, and specifically NOT a second field on
    /settings/presence beside corner_card. That route earns its shape the way
    /settings/tasks does, by being one route one field, and the two settings
    are not even the same shape: corner_card is a standing boolean, this is
    membership in a set. Folding them would mean a body whose legal keys
    depend on each other, which is the ambiguity the whole family of routes
    exists to avoid.

    THE BODY IS A VERB, NOT A LIST -- `{"hide": "photo-gallery"}` or
    `{"show": "photo-gallery"}`, never `{"hidden_apps": [...]}`. Exactly the
    reasoning /settings/offers gives for the same shape of store: a
    whole-list write makes two quick clicks a lost update, because the second
    POST carries a list built before the first landed and silently undoes it.
    And the ledger row can say what the founder MEANT ("hid photo-gallery")
    rather than printing a before-and-after the reader has to diff.

    EXACTLY ONE VERB PER WRITE, refused rather than ordered when both are
    sent: there is no ordering a caller could rely on and no gesture in the
    UI that produces one.

    THE ID IS NOT CHECKED AGAINST THE APPS REGISTRY, deliberately. Three
    reasons, and the third is the one that decides it. The Apps surface is
    flag-gated (modules_api.FLAG) and this setting is not, so an existence
    check would make the founder's Presence choice fail for a reason that has
    nothing to do with Presence. An app can be deleted after the hide is
    stored, so the list has to tolerate an id with no app behind it whatever
    this route does. And a stored id that matches nothing is INERT -- it is
    only ever asked "are you the open app", and the answer is no forever. The
    shape IS checked, in the store, against the same pattern modules_api
    validates with, so a junk id is still refused here rather than written.

    NOTHING IS STARTED OR STOPPED BY IT. Like corner_card, this is a view
    preference: no mission record reads it, so there is no drain and no
    counts to report. It reports the WHOLE list back because the client
    repaints the row from this answer rather than patching one id and
    trusting the rest.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    has_hide, has_show = "hide" in body, "show" in body
    if has_hide and has_show:
        raise HTTPException(400, "one of hide or show, not both")
    if not (has_hide or has_show):
        raise HTTPException(400, "hide or show required")
    app_id = body["hide"] if has_hide else body["show"]
    try:
        hidden_apps = shadow_presence.set_app_hidden(app_id, has_hide)
        # cleaned AFTER the store accepted it, so the ledger row and the
        # answer both name the id that was actually written
        named = shadow_presence.clean_app_id(app_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _shadow_ledger_safe({
        "kind": "setting", "mission_id": None,
        "summary": "presence: %s %s (now hidden for %s)"
                   % ("hid" if has_hide else "showed", named,
                      ", ".join(hidden_apps) if hidden_apps else "no apps")})
    return {"app_id": named,
            "hidden": has_hide,
            "hidden_apps": hidden_apps}


def _free_slots(store=None, cap=None):
    """How many queued missions could start RIGHT NOW: free slots, bounded by
    the queue. Never negative.

    ONE DEFINITION of "there is room and someone is waiting", because two
    callers need the same arithmetic for different answers -- the settings
    route needs the COUNT (it reports `starting`), the founder-action routes
    need the BOOLEAN (schedule a drain, or do not bother). A second copy of
    `min(queued, cap - running)` is how the two drift apart.
    """
    store = store or _mission_engine.MissionStore()
    cap = _mission_engine.max_running() if cap is None else cap
    return max(0, min(len(store.list(states=("queued",))),
                      cap - len(store.list(states=("running",)))))


def _drain_queue_in_background(why):
    """Schedule the promotion sweep off the request. Extracted so the route
    reads as one decision and so a test can watch the schedule without
    spawning a delegate.

    `why` is the phrase the ledger uses if the sweep fails -- "cap raised to
    5", "task m-abc stopped". The action that CAUSED the free slot has
    already happened and stands on its own; this is the queue catching up
    with it, and a failure here must be recorded against the right cause.
    """
    async def go():
        try:
            await shadow_runner.drain_queue(_validated_say)
        except Exception as exc:          # noqa: BLE001
            # the ACTION is done either way -- a promotion that failed must
            # not make the founder think their stop, or their limit, did not
            # stick
            _shadow_ledger_safe({"kind": "setting", "mission_id": None,
                                 "summary": "the queue did not drain after "
                                            "%s: %s"
                                            % (why, str(exc)[:160])})
    # create_task, not get_event_loop().create_task: the only caller is an
    # async route, so a loop is always running here, and the bare form is
    # what the rest of this file uses (_reader, pump_out, autostart).
    # get_event_loop() is deprecated off-loop and would warn on 3.12+.
    asyncio.create_task(go())


def _drain_queue_after(why):
    """THE ONE THING EVERY FOUNDER ACTION THAT FREES A SLOT DOES NEXT.

    WHY THIS EXISTS. Promotion had exactly two triggers: the runner loop's
    own wrapper (a mission that ran to a terminal state or blocked) and the
    settings route (the cap went up). Every OTHER way a slot frees went
    unnoticed, and each one left a task sitting queued behind capacity that
    was no longer in use:

      stop        the act route ends the mission itself. The wrapper only
                  promotes if a loop was alive AND reached its next boundary
                  check -- so a stop landed between turns waited out a whole
                  turn, and a stop on a mission with no live loop (adopted
                  after a restart, a loop that died) never promoted at all.
      take over   running -> paused. The slot is free, the wrapper's paused
                  branch emits a feed row and promotes nothing.
      delete      the record is REMOVED, so the wrapper reloads None and
                  cannot promote against a mission that no longer exists.
      abandon     the goal route stops its live attempt through the same
                  founder_stop, one layer up.

    IT IS A SWEEP, NOT A SECOND WAY TO START. drain_queue is the settings
    route's own path and promotes through MissionScheduler.on_terminal, so a
    promoted row provisions and launches exactly as it always did.

    DOUBLE-SAFE BY CONSTRUCTION. The wrapper may also promote for the same
    freed slot; on_terminal returns None the moment the cap is full again,
    and _launch no-ops for a mission already running. Nothing here can start
    a task twice.

    NEVER RAISES, and never blocks: a queue that cannot be read must not
    fail the stop that was asked for.
    """
    try:
        if not _free_slots():
            return False                  # nothing waiting, or no room yet
        _drain_queue_in_background(why)
        return True
    except Exception:                     # noqa: BLE001 -- see docstring
        return False


def _shadow_ledger_safe(row):
    """Audit rows are a record, never a reason to fail the write that caused
    them -- the house rule every other Shadow write in this file follows."""
    try:
        import shadow_ledger
        shadow_ledger.append("actions", row)
    except Exception:                     # noqa: BLE001
        pass


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
    # THE FOUNDER'S LIST, AT DECISION TIME. The default is the first kind on
    # offer rather than the constant "fix", because the founder may have
    # retired it and a default pointing at a kind they removed is exactly the
    # failure the offered/catalogue split exists to prevent.
    template = body.get("template") or _mission_engine.default_offer()
    if not objective:
        raise HTTPException(400, "objective required")
    # THIS DOOR MEANS "START SOMETHING NEW", so it refuses a kind that is no
    # longer offered. Retry is the other door and deliberately does not: it
    # rebuilds work already done, and gating it here would make every past
    # task of a retired kind un-retryable (mission_engine, delegate offers).
    if template not in _mission_engine.offered_kinds():
        raise HTTPException(400, "%r is not a kind Shadow offers" % (template,))
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


def _apply_task_fence(mid, blocks, scope_id=None):
    """A `mission` fence from a task's OWN Shadow chat amends THAT draft:
    objective, done_when, kind, and where it runs. Never a second task.
    Returns the record as it now reads. Best-effort on a terminal task."""
    store = _mission_engine.MissionStore()
    spec = (blocks or {}).get("mission")
    if isinstance(spec, dict):
        fields = {}
        if str(spec.get("objective") or "").strip():
            fields["objective"] = str(spec["objective"]).strip()
        if isinstance(spec.get("done_when"), list):
            fields["done_when"] = spec["done_when"]
        try:
            if fields:
                store.amend(mid, **fields)
            m = store.load(mid)
            if m is not None:
                kind = spec.get("template")
                if kind in _mission_engine.offered_kinds():
                    m["template"] = kind
                if spec.get("target_mode") == "existing":
                    m["target_mode"] = "existing"
                    m["target_session"] = (spec.get("target_session")
                                           or scope_id or m.get("target_session"))
                store.save(m)
        except ValueError:
            pass                        # terminal or unknown: reply stands
    return store.load(mid)


def _apply_limits_fence(blocks, mid=None):
    """Shadow v4.1 (V4-7): THE FOUNDER'S WORDS SET THE TASK.

    A `limits` fence in a reply to the founder's OWN line is applied by the
    app, at once: scope `task` binds the task whose chat this is (even while
    it runs); scope `default` writes the same task-limits store the sheet
    writes. Returns what the chip shows, or None when the reply carried no
    fence.

    ONLY EVER CALLED ON A REPLY TO THE FOUNDER. Its two callers are the task
    chat route and the Now chat route, both founder-typed; nothing the worker
    says, and nothing Shadow says unprompted, reaches this.

    A REFUSAL IS AN ANSWER, NOT AN ERROR. The founder said something and
    Shadow heard it; if the store says no (a number already spent, a kind that
    never speaks) the chip says why in the store's own words and nothing is
    written. Never raises: a limits fault must not cost the founder the reply.
    """
    spec = (blocks or {}).get("limits")
    if not isinstance(spec, dict):
        return None
    store = _mission_engine.MissionStore()
    done, refused = [], []
    try:
        if "turns" in spec:
            turns = spec["turns"]
            if spec["scope"] == "task" and mid:
                m = _mission_engine.set_task_turns(store, mid, turns)
                done.append({"label": _mission_engine.limits_label(m),
                             "undo": {"mid": mid, "action": "undo_limits"}})
            elif turns == "none":
                refused.append("No limit is set per task -- say it in that "
                               "task's chat.")
            else:
                m = store.load(mid) if mid else None
                kind = (m or {}).get("template") \
                    or _mission_engine.default_offer()
                n = _mission_engine.set_turn_budget(kind, turns)
                done.append({"label": "turns: %d, every new %s task"
                                      % (n, kind)})
        if "running_at_once" in spec:
            n = _mission_engine.set_max_running(spec["running_at_once"])
            done.append({"label": "running at once: %d" % n})
            _drain_queue_after("running at once set from a chat")
    except ValueError as exc:
        refused.append(str(exc))
    except Exception as exc:            # noqa: BLE001 -- see docstring
        refused.append("could not save that: %s" % str(exc)[:140])
    return {"applied": done, "refused": refused}


def _continue_after_answer(store, mid, outcome):
    """Shadow v4.2: what the routes do after mission_engine.apply_answer.

    THE SAME THREE MOVES THE BUTTONS MAKE, so a typed yes and a clicked one
    end in the same place: approve -> cap check, running, launch (the Approve
    button's path); confirm -> the goal hook and settle_confirmation (the
    Confirm button's path); withdraw / change -> running, launch (Resume's
    path: Shadow recomposes at the next boundary with the founder's words in
    front of it). Returns the record as it now reads."""
    m = store.load(mid)
    if outcome.get("settle"):
        _goal_hook_safe("record_founder_confirmation", m)
        settled = shadow_runner.settle_confirmation(mid, _shadow_verifier)
        return settled or store.load(mid)
    if outcome.get("resume") and m is not None and m["state"] == "paused":
        running_n = len(store.list(states=("running",)))
        cap = _mission_engine.max_running()
        if running_n >= cap:
            raise ValueError("answered, but Shadow is already running %d of "
                             "%d tasks -- stop one, or raise Running at once"
                             % (running_n, cap))
        if m.get("pause_reason") == "autonomy_top_tier" \
                and outcome.get("kind") == "approve":
            m["top_tier_confirmed"] = True
            store.save(m)
        m = store.transition(mid, "running", "%s from the chat"
                             % outcome.get("kind"))
        shadow_runner._launch(mid, _validated_say, _shadow_verifier)
    return store.load(mid)


def _apply_answer_fence(blocks, mid):
    """Shadow v4.2 (founder 2026-09-21): THE FOUNDER'S TYPED LINE ANSWERS THE
    ASK. The task chat was told the pending asks (pending_asks_text) and,
    reading the founder's line, emitted one `answer` fence; the app binds it
    to the one ask it can mean and does exactly what the button would do.

    ONLY EVER ON A REPLY TO THE FOUNDER'S OWN LINE (the task chat route).
    A refusal is an answer, not an error: the founder said something and
    Shadow heard it; if it cannot be bound (nothing held, two checks
    waiting, at capacity) the sentence comes back in `refused` and nothing
    is written. Never raises."""
    spec = (blocks or {}).get("answer")
    if not isinstance(spec, dict) or not mid:
        return None
    store = _mission_engine.MissionStore()
    try:
        outcome = _mission_engine.apply_answer(store, mid, spec)
        _continue_after_answer(store, mid, outcome)
        return {"applied": [{"kind": outcome["kind"],
                             "label": outcome["label"],
                             "index": outcome.get("index")}],
                "refused": []}
    except ValueError as exc:
        return {"applied": [], "refused": [str(exc)]}
    except Exception as exc:            # noqa: BLE001 -- see docstring
        return {"applied": [], "refused": ["could not apply that: %s"
                                           % str(exc)[:140]]}


def _reopen_and_launch(store, mid, words, via):
    """Shadow v4.1 (V4-9): DONE IS NOT A DEAD END. The one place the app
    reopens a finished task, so the three doors (the task chat, "give
    instruction", Hand back) cannot drift.

    mission_engine.reopen does the record; this does what `resume` does after
    it: a task that came back `running` gets its loop, a task that came back
    `queued` is promoted by the ordinary path when a slot frees
    (_promote_after_slot_freed launches an existing chat without provisioning
    a second one). A refusal is the store's own sentence, as a 409.
    """
    try:
        _mission_engine.unpark(store, mid)      # v4.2: a parked say asks first
        m = _mission_engine.reopen(store, mid, words, via=via)
    except ValueError as exc:
        raise HTTPException(409, {"detail": str(exc),
                                  "state": (store.load(mid) or {}).get("state")})
    if m["state"] == "running":
        shadow_runner._launch(mid, _validated_say, _shadow_verifier)
    return m


@app.post("/api/shadow/tasks")
async def api_shadow_task_open(request: Request):
    """Shadow v4 (J1): one line from the founder opens a task.

    The line becomes a DRAFT (brief_confirm, the objective verbatim), the
    task's own Shadow chat boots and answers it, and a `mission` fence in
    that answer sharpens the draft. Nothing starts: Start is the founder's.
    A Shadow chat that will not boot leaves the verbatim draft standing and
    an empty reply, never a lost line.
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    scope_id = (body.get("scope_id") or "").strip() or None
    store = _mission_engine.MissionStore()
    try:
        m = store.create(message, _mission_engine.default_offer(),
                         target_mode="new")
        store.transition(m["id"], "brief_confirm", "drafted in the task chat")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    mission = store.load(m["id"])
    reply, blocks = "", {}
    try:
        chat = await _ensure_task_chat(mission)
        reply, blocks = await chat.talk(message)
    except Exception as exc:            # noqa: BLE001 -- the draft stands
        _shadow_ledger_safe({
            "kind": "spawn", "mission_id": mission["id"],
            "summary": "task chat unavailable at open: %s" % str(exc)[:140]})
    out = {"mission": _apply_task_fence(mission["id"], blocks, scope_id),
           "reply": reply}
    if "chips" in blocks:
        out["chips"] = blocks["chips"]
    return out


def _forward_enqueue(sid, text, key, mid=None, indices=None):
    """Put ONE composed forward on the worker's own queue. Returns accepted.

    THE SHADOW LANE, NEVER THE OPERATOR LANE, and it is not a style choice.
    TurnQueue.get() drains `_operator` before `_shadow`, so a founder line
    placed there would overtake a say already queued for this turn -- and
    shadow_runner.waiter, which consumes the next boundary on the session
    without being able to tell whose turn produced it, would read the founder
    turn's boundary as its say's, take the wrong `last_response` and spend a
    turn of budget on it. The founder's own constraint ("do not create an
    operator lane where the user's message bypasses Shadow's authority") and
    the ordering requirement have the same answer, which is this one.
    """
    rt = lookup_runtime(sid)
    if rt is None:
        return False
    # THE ROWS RIDE WITH THE PAYLOAD so the pump can close their lifecycle
    # without knowing anything about missions: shadow_runner._forward_consumed
    # reads these two keys off the frame it just sent and marks them
    # `consumed`. Underscore-prefixed like `_source`, which the queue already
    # carries the same way and which the wire never sees.
    ok = rt.turn_queue.put({"message": text, "_source": "shadow",
                            "_forward": True,
                            "_mission": mid,
                            "_fwd_indices": list(indices or ())},
                           source="shadow", dedupe_key=key)
    if ok:
        rt.queue_event.set()
    return ok


def forward_to_worker(mid, store=None, enqueue=None, revive=False):
    """Hand the worker everything the founder has said that it needs to hear.

    SYNCHRONOUS ON PURPOSE, AND THAT IS THE WHOLE CONCURRENCY STORY. load ->
    compose -> put -> mark -> save runs with no await in it, so on a
    single-threaded event loop no second caller can observe a half-applied
    dispatch: it is a critical section by construction rather than by a lock
    that someone has to remember to take. MissionStore.save's own seq guard
    covers the only case this cannot -- a SECOND PROCESS on the same shadow
    home -- by refusing the stale write outright.

    IDEMPOTENT THREE TIMES OVER, because losing a correction and delivering
    it twice are both failures this lane is required not to have: `pending`
    only returns rows still awaiting the worker, TurnQueue refuses a repeated
    dedupe_key for the life of the runtime, and the rows are marked
    `dispatched` before the function returns. A retry of the identical
    forward computes the identical key and is refused.

    COALESCED, ONE TURN. Every pending row goes in one frame, newline-joined
    in list order (shadow_forward.coalesce). Three rapid corrections cost the
    worker one model call, not three, and their order is preserved inside the
    frame rather than across three racing ones.

    BEST-EFFORT, LOUD, NEVER FATAL. This is called from the founder's own
    chat request. A forwarding fault must cost the forward and nothing else:
    the founder already has Shadow's answer, the line is already on
    `founder_says` for the decider, and rows left `queued` are picked up by
    the next call or by boot recovery. So every failure ledgers and returns.
    """
    store = store or _mission_engine.MissionStore()
    enqueue = enqueue or _forward_enqueue
    try:
        m = store.load(mid)
        # A MISSION THAT IS NOT RUNNING HAS NO WORKER LISTENING. A draft has
        # not spawned one, a paused/terminal one is not being driven, and a
        # watch mission never speaks at all (`never_say`). The rows stay
        # `queued` and durable either way -- a paused task that resumes
        # delivers them, which is the behaviour the founder asked for.
        if m is None or m.get("state") != "running":
            return None
        if "never_say" in (m.get("invariants") or ()):
            return None
        sid = m.get("target_session")
        if not sid:
            return None
        indices, payload = shadow_forward.deliverable(m, revive=revive)
        if not indices:
            return None
        # THE SAME EGRESS FLOOR EVERY OTHER WORKER-BOUND BYTE CROSSES. This
        # lane does not get its own weaker one: the floor is about what may
        # leave for a worker session, not about who composed it.
        #
        # A FLOORED FORWARD IS MARKED skip, NOT LEFT QUEUED. Left queued it
        # would be recomposed and re-floored on every later message, forever.
        # Nothing is lost by skipping it: `seen` is untouched, so the line
        # still reaches the decider on the next steering turn and Shadow can
        # raise it with the founder in words.
        tripped = shadow_egress.floor_check(payload)
        if tripped:
            shadow_forward.mark(m, indices, shadow_forward.FWD_SKIP)
            store.save(m)
            _shadow_ledger_safe({
                "kind": "say", "mission_id": mid,
                "summary": "forward NOT sent, floor: %s" % ", ".join(tripped)})
            return None
        clean, _redactions = shadow_egress.scrub(payload)
        if not enqueue(sid, clean, shadow_forward.dedupe_key(mid, indices),
                       mid, indices):
            # Refused: no live runtime, or this exact payload is already on
            # the queue. Either way the rows stay as they are and the next
            # attempt re-offers them.
            return None
        shadow_forward.mark(m, indices, shadow_forward.FWD_DISPATCHED)
        store.save(m)
        _shadow_ledger_safe({
            "kind": "say", "mission_id": mid,
            "summary": "forwarded %d founder line(s) to the worker"
                       % len(indices)})
        return indices
    except Exception as exc:            # noqa: BLE001 -- audible, never fatal
        _shadow_ledger_safe({
            "kind": "say", "mission_id": mid,
            "summary": "forward FAILED: %s" % str(exc)[:140]})
        return None


def resume_after_revision(mid, was_state, store=None, launch=None):
    """A REVISED TASK MUST ACTUALLY GO BACK TO WORK (founder, 2026-09-21).

    THE BUG, reproduced before it was fixed. A mission at NEEDS YOU is
    PAUSED, and run_mission has already left its loop -- the top of the loop
    returns as soon as it reads a paused state (mission_engine, "founder stop
    / intervention / done"). When the founder then replies with a change,
    `_apply_task_fence` amends the mission and `_invalidate_for_revision`
    releases the pause by setting the state back to `running`. The record
    then reads: running, v2, new objective, old decision superseded -- and
    NOTHING IS DRIVING IT. Shadow had said "I'll build that into its next
    instruction", and there was no next instruction, because there was no
    loop left to compose one.

    THE FIX IS THE DOOR THAT ALREADY EXISTS. The `resume` action ends with
    `shadow_runner._launch(mid, _validated_say, _shadow_verifier)`, which is
    exactly what restarts a loop that has exited. A revision that releases a
    pause needs the same call, so it makes it. No new state, no second
    runner, no parallel path.

    ONLY WHEN THE REVISION ACTUALLY RELEASED A PAUSE. `was_state` is what
    the mission was before the fence touched it, so a task that was already
    running is left alone (its loop is live and will read the new revision
    at the top of its next iteration) and a DRAFT is left alone (amend puts
    it in brief_confirm and Start is the founder's). The only case that
    launches is paused-or-blocked -> running, which is the one that was dead.

    IT IS NOT THE ANSWER TO THE QUESTION. Confirm is a different door
    entirely -- confirm_check / settle_confirmation, which satisfy the check
    and let the mission complete -- and is untouched by this. A reply CHANGES
    the work; it does not satisfy it. The worker still has to execute the
    revised task and Shadow still has to verify the result.

    BEST-EFFORT AND LOUD. This runs inside the founder's own chat request; a
    launch failure must cost the resume and not the reply, so it ledgers and
    returns False rather than raising into their conversation.
    """
    if was_state not in ("paused", "blocked"):
        return False
    store = store or _mission_engine.MissionStore()
    try:
        m = store.load(mid)
        if m is None or m.get("state") != "running":
            return False
        # already driven: _launch guards this too, but saying so here keeps
        # the ledger row honest about what actually happened
        if mid in shadow_runner.RUNNING and not shadow_runner.RUNNING[mid].done():
            return False
        (launch or shadow_runner._launch)(
            mid, _validated_say, _shadow_verifier)
        _shadow_ledger_safe({
            "kind": "spawn", "mission_id": mid,
            "summary": "resumed after revision to v%s (founder changed the task)"
                       % m.get("version")})
        return True
    except Exception as exc:            # noqa: BLE001 -- audible, never fatal
        _shadow_ledger_safe({
            "kind": "spawn", "mission_id": mid,
            "summary": "could not resume after revision: %s" % str(exc)[:140]})
        return False


def _record_founder_talk(mid, text, blocks=None):
    """ONE MEMORY OF THE FOUNDER (founder, 2026-09-16, step 2).

    THE SPLIT THIS CLOSES. The founder had two doors and Shadow had two
    memories of them. "Give instruction to Shadow" appends to the mission's
    `founder_says`, which `_decision_context` hands the decider and the
    `seen` flag stops repeating. "Talk to Shadow" lived only in the task
    chat's own transcript -- which the LIVE chat can see, because decide()
    and talk() are two prompts on one session, but the one-shot fallback
    decider cannot see at all, and which nothing marks as consumed. So a
    constraint the founder mentioned conversationally reached the worker
    only by luck, and could steer every later turn forever.

    THE WHOLE FIX IS THE SAME LIST. A talked line is appended to
    `founder_says` exactly as a typed one is, tagged `via` so Shadow can
    tell a deliberate instruction from a passing remark. Everything else
    already exists and is already tested: the record is durable and atomic,
    `seen` is the consumption cursor, append order is the chronology, and
    both the task chat and the one-shot fallback read the same context. No
    new field, no new store, no queue, no cursor of its own.

    IT IS NOT AN INSTRUCTION, AND THIS DOES NOT MAKE IT ONE. `founder_says`
    has never been a message to the worker: it is INPUT TO A DECISION, and
    the decider composes the instruction itself (mission_engine._instruction
    -> validate_decision -> the one validated say path). What changed is
    that Shadow can now see everything the founder said; what did not change
    is who decides, and that nothing here can reach the worker on its own.

    ONLY THE FOUNDER'S OWN WORDS. Shadow's reply is never recorded -- it is
    returned to the founder and stays in the chat -- so Shadow can never read
    its own answer back as something it was told. Nothing from the worker
    reaches this list either; it has exactly two writers, both founder-typed.

    NOT WHILE DRAFTING: before Start the conversation IS the drafting of the
    task and lands on the objective through the `mission` fence. Recording it
    as well would replay the whole drafting exchange into the first decision.

    BEST-EFFORT BY CONSTRUCTION. A store failure here must cost the record of
    one line and nothing else: the founder already has Shadow's answer, and a
    Shadow-side fault must never become a worker fault.

    AND IT NOW CARRIES THE FORWARDING VERDICT (founder, 2026-09-21). `blocks`
    is Shadow's own parsed reply to this very line, so the `forward` fence in
    it is the supervisor's judgement about whether the worker needs to hear
    it -- taken on a turn that was happening anyway, which is what keeps this
    from becoming a second authority that can disagree with Shadow. The
    verdict is stamped on the row as `fwd` and the actual delivery is
    forward_to_worker's job, not this function's. What did NOT change is the
    sentence above it: `founder_says` is still input to a decision, `seen` is
    still the only cursor the decider reads, and nothing here composes an
    instruction.
    """
    try:
        store = _mission_engine.MissionStore()
        m = store.load(mid)
        if m is None or m["state"] in _mission_engine.TERMINAL:
            return
        says = list(m.get("founder_says") or [])
        says.append({"text": str(text)[:_SAY_MAX],
                     "at": _mission_engine._now(),
                     "at_turn": m.get("turns_used") or 0,
                     "via": "talk",
                     "seen": False,
                     # THE FORWARDING VERDICT, STAMPED AT ARRIVAL (2026-09-21)
                     # and never revisited. `seen` is the decider's cursor
                     # over this same list and is deliberately untouched:
                     # every line still reaches the decider exactly as it
                     # did, whatever `fwd` says. See shadow_forward.
                     "fwd": shadow_forward.verdict(text, blocks)})
        m["founder_says"] = says
        store.save(m)
    except Exception as exc:            # noqa: BLE001 -- audible, never fatal
        _shadow_ledger_safe({
            "kind": "say", "mission_id": mid,
            "summary": "founder talk NOT recorded: %s" % str(exc)[:140]})


@app.post("/api/shadow/tasks/{mid}/chat")
async def api_shadow_task_chat(mid: str, request: Request):
    """Talk to ONE task's Shadow chat. Before Start the draft card follows
    the conversation; after Start the words reach the chat that steers the
    worker (it may amend its next instruction). Never the working chat.

    TWO GUARDS, BOTH ABOUT WHEN THE CONVERSATION IS ALLOWED TO CHANGE THINGS
    (founder, 2026-09-16, step 1 of the Shadow conversation UX). The route is
    otherwise untouched: same chat, same `talk`, same reply.

    A FINISHED TASK REOPENS (v4.1, V4-9). Until 2026-09-21 a terminal task
    refused the founder's words with a 409. It now goes back to work on those
    words first (_reopen_and_launch) and the chat answers afterwards, so
    Shadow never answers as though finished work were live.

    THE `mission` FENCE NOW AMENDS A LIVE TASK TOO (founder, 2026-09-21).
    It used to apply only while DRAFTING, and the reasoning was that after
    Start "it would make a casual question re-scope live work". That guard
    was too blunt, and it is the bug the founder hit: watching an Africa
    trip sit at NEEDS YOU they said "I changed my mind, I want India", Shadow
    answered "India it is, amending the task now" -- and nothing amended.
    The objective, the done_when and the version never moved, so the Africa
    criteria stayed authoritative and NEEDS YOU kept asking about a trip
    that had been abandoned. Shadow said one thing and the record said
    another.

    A CASUAL QUESTION STILL RE-SCOPES NOTHING, and the discriminator was
    already here: the task chat emits a `mission` fence only when it means
    to amend (SHADOW.md: "a `mission` fence from you AMENDS it"). "What are
    you doing?" and "thanks" produce prose and no fence, so they reach
    `founder_says` exactly as before and change no state. No classifier was
    added; the existing protocol IS the signal.

    WHAT THE AMEND DOES is MissionStore.amend's business, and it bumps
    `version` -- the revision the loop, the approval and the sign-off all
    validate against. A turn composed under the old objective can no longer
    complete the new one."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    store = _mission_engine.MissionStore()
    mission = store.load(mid)
    if mission is None:
        raise HTTPException(404, "no task %s" % mid)
    # v4.1 (V4-9, founder 2026-09-21): DONE IS NOT A DEAD END. This used to
    # answer 409 "this task has finished" -- the founder gave a finished task
    # more to do and was told no. The words now REOPEN the task (same record,
    # same chats) before the chat answers, so the answer comes from a Shadow
    # that is working again rather than one talking about live work that is
    # not live. The guard the old refusal stood for still holds: a terminal
    # task is never talked to AS terminal.
    reopened = mission["state"] in _mission_engine.TERMINAL
    if reopened:
        mission = _reopen_and_launch(store, mid, message, "talk")
    drafting = mission["state"] in ("draft", "brief_confirm")
    # v4.2: THE CHAT IS TOLD WHAT THE TASK IS WAITING ON before it answers,
    # the same way the Now box prefixes [Intake]. Without this Shadow said
    # "on it" to a line that could move nothing (founder 2026-09-21).
    pending = _mission_engine.pending_asks_text(mission)
    try:
        chat = await _ensure_task_chat(mission)
        reply, blocks = await chat.talk(
            (pending + "[The founder says:] " + message) if pending
            else message)
    except Exception as exc:            # noqa: BLE001
        if not reopened:
            raise HTTPException(
                503, "this task's Shadow chat is not available: %s"
                % str(exc)[:140])
        # THE REOPEN STANDS. The words are already on the record
        # (founder_says, via "reopen") and the loop is already running on
        # them; a Shadow chat that will not boot costs the reply, never the
        # work -- the same rule api_shadow_task_open applies to a draft.
        reply, blocks = "", {}
    if not drafting and not reopened:
        # RECORD, THEN FORWARD, AND BOTH BEFORE THE REPLY GOES OUT. Shadow
        # has already answered the founder above -- that never waited on
        # anything and still does not. `blocks` carries Shadow's own
        # `forward` verdict on this line; the record stamps it and the
        # dispatch acts on it immediately, so a worker-relevant line is on
        # the worker's queue before this request returns rather than at the
        # top of some later steering turn. That gap WAS the bug.
        #
        # STILL SKIPPED ON A REOPEN, which is the other half of this block:
        # those words are already on founder_says via "reopen" and the loop
        # is already running on them, so recording and forwarding again
        # would double a line the worker is about to act on.
        _record_founder_talk(mid, message, blocks)
        forward_to_worker(mid)
    # DRAFTING OR LIVE, the fence is the founder changing what the task is
    # for. A terminal task is still refused -- amend raises on one, and the
    # reopen path above is how a finished task comes back.
    # WHAT THE TASK WAS BEFORE THE FENCE TOUCHED IT. Read here, from the
    # record loaded at the top of this route, because the fence is about to
    # overwrite it -- and whether the founder's reply RELEASED A PAUSE is the
    # whole question resume_after_revision asks.
    was_state = mission["state"]
    out = {"mission": (_apply_task_fence(mid, blocks)
                       if (drafting or not reopened) else store.load(mid)),
           "reply": reply}
    # ── AND THE WORKER ACTUALLY GOES BACK TO WORK (founder, 2026-09-21) ────
    # A reply from NEEDS YOU that changes the task amends it and releases the
    # pause, and until this line nothing restarted the loop that had already
    # exited on that pause -- so the record read `running` with nobody driving
    # it and Shadow's "I'll build that into its next instruction" was a
    # promise about a turn that never came. Confirm is a different door and is
    # untouched: it satisfies the check, it does not change the work.
    if resume_after_revision(mid, was_state, store=store):
        out["mission"] = store.load(mid) or out["mission"]
        out["resumed"] = True
    if "chips" in blocks:
        out["chips"] = blocks["chips"]
    limits = _apply_limits_fence(blocks, mid)
    if limits is not None:
        out["limits"] = limits
        out["mission"] = store.load(mid)
    # v4.2: the founder's line answered an ask -- the app applies it,
    # bound to that ask, and the reply carries what happened
    answered = _apply_answer_fence(blocks, mid)
    if answered is not None:
        out["answer"] = answered
        out["mission"] = store.load(mid)
    if reopened:
        out["reopened"] = True
    return out


@app.get("/api/shadow/missions")
async def api_shadow_missions():
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    store = _mission_engine.MissionStore()
    return {"missions": store.list()}


# ------------------------------------------------------------- goals ----
# The Goal is the durable outcome; a Mission is one attempt at it. These
# routes are a thin shell over GoalStore + goal_lifecycle -- no domain
# logic lives here, and in particular no mission is ever created in this
# file (goal_lifecycle owns that).


def _goal_hook_safe(fn_name, *args):
    """Goal bookkeeping must never take down a request that worked -- the
    same house rule shadow_runner._goal_hook follows."""
    try:
        return getattr(_goal_lifecycle, fn_name)(*args)
    except Exception:
        return None


def _sync_goal_after_founder_end(mission):
    """Reconcile a goal whose attempt the FOUNDER just ended.

    Needed for the two paths that never reach the runner's on_attempt_end
    funnel: a dropped queued attempt (never launched) and a stop the loop
    will only notice when it next wakes. on_attempt_end is idempotent, so
    the later funnel call is harmless.
    """
    if not (mission or {}).get("goal_id"):
        return None
    return _goal_hook_safe("on_attempt_end", mission)


def _mark_start_requested(store, mid):
    """Stamp the durable fact that a start was ACCEPTED for this mission.

    THE PROBLEM THIS EXISTS FOR. `start_mission_async` is the deliberate
    second-flight fix: it answers {"accepted": true} immediately and does
    admission + provisioning in an app task, because provisioning a delegate
    can take minutes and holding the request open let client timeouts cancel
    it mid-spawn. The consequence is a window in which the mission is still
    `brief_confirm` on disk while Shadow is already starting it -- and
    brief_confirm is exactly the state the task UI draws a Start button for.
    So the founder pressed Start and the Start button stayed, and a page
    refresh inside that window had nothing at all to read it from: the
    in-memory _STARTING guard is the runner's, not the record's.

    NOT A NEW STATE. `state` is untouched, the transition table is untouched,
    and nothing reads this to decide what a mission may do -- the scheduler
    still owns admission and still moves brief_confirm -> running|queued on
    its own. It is one timestamp the UI reads to draw the EXISTING `queued`
    face ("QUEUED", admitted and not yet running) instead of an actionable
    Start, which is the honest reading of a start that has been accepted.
    Same shape as `pause_reason`: a fact carried beside the state because the
    state alone is not the whole face.

    Cleared at boot by _clear_stale_start_requests(): a start the previous
    process accepted and never finished is not a pending start.
    """
    m = store.load(mid)
    if m is None or m.get("state") != "brief_confirm":
        # running/queued already SAY they started; a terminal mission has
        # nothing to claim. Only the gap needs covering.
        return m
    m["start_requested_at"] = _mission_engine._now()
    try:
        store.save(m)
    except ValueError:
        # a concurrent writer moved the mission on; its state is now the
        # truthful face and the stamp is not needed
        return store.load(mid)
    return m


def _clear_stale_start_requests():
    """Boot: forget starts the PREVIOUS process accepted but never completed.

    Admission and provisioning run as an app task, so nothing survives a
    restart to finish them -- a mission still sitting in `brief_confirm` with
    a stamp on it will never move on its own. Clearing the stamp is what puts
    Start back in front of the founder instead of leaving a task reading
    QUEUED forever with no way to act on it.

    Deliberately here and not in shadow_runner.recover_on_boot: this is the
    request-surface stamp this file writes, and recover_on_boot owns the
    running-mission/ownership rebuild, which is untouched.
    """
    store = _mission_engine.MissionStore()
    cleared = 0
    for m in store.list(states=("draft", "brief_confirm")):
        if not m.get("start_requested_at"):
            continue
        m.pop("start_requested_at", None)
        try:
            store.save(m)
            cleared += 1
        except ValueError:
            pass
    return cleared


def _delete_delegate_chat(mission):
    """Remove the chat Shadow MADE for this task, with the task.

    THE OWNERSHIP RULE, and it is the whole of the safety here:

        target_mode == "new"       Shadow spawned this chat for this mission
                                   and nothing else will ever claim it, so
                                   deleting the task deletes it too.
        target_mode == "existing"  the founder's own chat, which Shadow was
                                   only ever a visitor in. NEVER deleted --
                                   removing the task must not remove a
                                   conversation the founder started.

    Both halves reuse machinery that already exists and neither is a second
    deletion architecture:

      * session_reader.relocate(sid, "trash") is exactly what
        POST /api/sessions/{sid}/delete does -- the transcript moves to
        ~/.sutra-ui/trash with a .orig.json beside it, so this is
        RECOVERABLE, not destruction.
      * chat_store.delete(sutra_id) drops the record and its index rows.
        chat_store's reverse index IS the definition of a Sutra chat
        (_owned_transcripts), so that is what makes the row leave Chats.

    Order matters: transcript first. A failure between the two leaves a
    record naming a trashed file -- invisible and harmless -- rather than a
    live transcript that no record claims, which is the orphan the Chats
    list would go on showing.

    Best-effort by design: a chat that cannot be removed must never block
    the founder from removing the task. Returns what it actually did, so
    the caller can say so.
    """
    out = {"chat_deleted": False, "transcript_trashed": False}
    if (mission or {}).get("target_mode") != "new":
        return out                      # the founder's chat is not ours
    sid = mission.get("target_session")
    if not sid:
        return out
    try:
        if sr.relocate(sid, "trash"):
            out["transcript_trashed"] = True
    except Exception:                   # noqa: BLE001 -- never block the delete
        pass
    sutra_id = mission.get("target_chat")
    if not sutra_id:
        try:
            sutra_id = chat_store.resolve("claude", sid)
        except Exception:               # noqa: BLE001
            sutra_id = None
    if sutra_id:
        try:
            out["chat_deleted"] = bool(chat_store.delete(sutra_id))
        except Exception:               # noqa: BLE001
            pass
    return out


def _goal_or_404(gid):
    store = _goal_store.GoalStore()
    g = store.load(gid)
    if g is None:
        raise HTTPException(404, "no goal %s" % gid)
    return store, g


def _goal_row(store, g):
    """The list shape: what a Shadow Home row needs and nothing more."""
    p = store.progress(g["id"])
    return {
        "id": g["id"],
        "outcome": g.get("outcome"),
        "state": g.get("state"),
        "target_session": g.get("target_session"),
        "checks_met": p["checks_met"],
        "checks_total": p["checks_total"],
        "checks_label": p["checks_label"],
        # ADDITIVE (slice 10): the outstanding checks, so a Shadow Home row
        # can honestly say what a working goal is waiting on instead of
        # narrating. Already computed by GoalStore.progress() and already
        # public on the detail payload -- this exposes existing derived data
        # to the list, and introduces no new semantics.
        "unmet": p["unmet"],
        "turns_used": p["turns_used"],
        "max_turns": p["max_turns"],
        "turn_label": p["turn_label"],
        "block_reason": p["block_reason"],
        "attempt": p["attempt"],
        "current_mission_id": g.get("current_mission_id"),
        "created_at": g.get("created_at"),
        "updated_at": g.get("updated_at"),
        "last_evaluated_at": g.get("last_evaluated_at"),
    }


def _goal_detail(store, g):
    """The detail shape: the row, plus checks, attempts and memory.

    Deliberately composed rather than dumping the record: `seq`,
    `created_ns`, raw `check_results` and each learned row's `dedupe_key`
    are storage mechanics, not product facts.
    """
    row = _goal_row(store, g)
    p = store.progress(g["id"])
    mem = store.memory(g["id"])
    row.update({
        "done_when": g.get("done_when") or [],
        "checks": p["checks"],
        "unmet": p["unmet"],
        "attempts": mem["attempts"],
        "history": mem["history"],
        "learned": [{k: v for k, v in item.items() if k != "dedupe_key"}
                    for item in mem["learned"]],
        "founder_guidance": [
            {k: v for k, v in item.items() if k != "dedupe_key"}
            for item in mem["founder_guidance"]],
        "blockers": [{k: v for k, v in item.items() if k != "dedupe_key"}
                     for item in mem["blockers"]],
    })
    return row


async def _ensure_target_runtime(session_id):
    """Give Shadow something to speak through in an EXISTING chat.

    Deliberately called from the Start/Resume HANDLER rather than from
    _validated_say: the say path is the one place every check is enforced,
    and making it a process manager as well would mean a spawn could happen
    inside any check-and-say. It is also not folded into
    start_mission_async: that runs in the background precisely because
    PROVISIONING takes minutes, whereas attaching is one
    create_subprocess_exec and no turn -- so doing it in the request means a
    chat Shadow cannot reach is refused BEFORE an attempt exists, instead of
    creating a doomed one.

    Raises NoLiveRuntime, which the handler turns into a 409.
    """
    return await shadow_runner.ensure_runtime(
        session_id, lambda sid: _shadow_args(session_id=sid),
        register_runtime)


async def _ensure_delegate_runtime(session_id, permission_mode=None):
    """Re-enter a DELEGATE's session after a restart, when its worker is gone.

    Same primitive as _ensure_target_runtime and the same measured
    `--resume <sid>` contract: the id is checked against disk first, the
    session id comes back byte-identical, and the transcript is appended to
    rather than forked. The ONLY difference is the argv builder -- a delegate
    runs on _worker_args (its own MCP config, permission mode and tool
    scope), not on the args Shadow uses to speak inside a founder's chat.
    Re-attaching on the wrong builder would give the adopted worker a
    different toolset than the one it was spawned with.

    Called from exactly one place: resume_after_restart, and only after
    delegate_alive() has said the previous process is gone. It is never a
    second spawn path -- an id with a live worker never reaches here.

    Raises NoLiveRuntime, which the caller records as a left-paused reason.
    """
    return await shadow_runner.ensure_runtime(
        session_id,
        lambda sid: _worker_args(session_id=sid,
                                 permission_mode=permission_mode),
        register_runtime)


def _start_goal_attempt(mission):
    """Admit + launch one goal attempt through the EXISTING mission start
    path, so admission, the cap, FIFO and the runner behave identically to
    every other mission."""
    async def _spawner(m):
        return await _delegate_spawn(m)
    # a goal attempt lands in the SAME task list as a delegated task, so it
    # gets the same honest face while it provisions
    _mark_start_requested(_mission_engine.MissionStore(), mission["id"])
    return shadow_runner.start_mission_async(
        mission["id"], _validated_say, provisioner=_spawner,
        verifier=_shadow_verifier)


@app.get("/api/shadow/goals")
async def api_shadow_goals(request: Request):
    """Every goal, oldest-created first. `?state=` and `?target_session=`
    narrow it, matching the instructions endpoint's query-filter style."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    store = _goal_store.GoalStore()
    want_state = request.query_params.get("state") if request else None
    want_session = (request.query_params.get("target_session")
                    if request else None)
    states = (want_state,) if want_state else None
    return {"goals": [_goal_row(store, g)
                      for g in store.list(states=states,
                                          target_session=want_session)]}


@app.post("/api/shadow/goals")
async def api_shadow_goal_create(request: Request):
    """An outcome for one chat, in `draft`. Creation never starts work --
    Start is a separate, explicit founder action, exactly as it is for a
    mission's brief_confirm."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be json")
    outcome = (body.get("outcome") or "").strip()
    target_session = (body.get("target_session") or "").strip()
    if not outcome:
        raise HTTPException(400, "outcome required")
    if not target_session:
        raise HTTPException(400, "target_session required")
    store = _goal_store.GoalStore()
    try:
        g = store.create(outcome, target_session,
                         done_when=body.get("done_when"))
    except ValueError as exc:
        # one active goal per chat is a CONFLICT, not a malformed request
        raise HTTPException(409, str(exc))
    return _goal_detail(store, g)


@app.get("/api/shadow/goals/{gid}")
async def api_shadow_goal(gid: str):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    store, g = _goal_or_404(gid)
    return _goal_detail(store, g)


@app.post("/api/shadow/goals/{gid}/act")
async def api_shadow_goal_act(gid: str, request: Request):
    """One endpoint, action field decides -- the same shape as
    /api/shadow/missions/{mid}/act.

    start     first attempt at a draft goal, then admit + launch
    resume    a NEW attempt at a blocked goal, same chat, +extra_turns
    stop      the founder abandons the outcome
    guidance  keep something the founder said about this goal
    confirm   satisfy a founder_confirm check on the live attempt
    """
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be json")
    action = body.get("action")
    store, _g = _goal_or_404(gid)
    try:
        if action == "start":
            # BEFORE the attempt exists: a chat Shadow cannot reach is
            # refused with the goal untouched in `draft`, rather than
            # spending an attempt on a mission that can never say anything.
            await _ensure_target_runtime(_g.get("target_session"))
            m = _goal_lifecycle.start_first_attempt(
                gid, template=body.get("template") or None)
            started = _start_goal_attempt(m)
            return {"goal": _goal_detail(store, store.load(gid)),
                    "mission_id": m["id"], "started": started}
        if action == "resume":
            await _ensure_target_runtime(_g.get("target_session"))
            m = _goal_lifecycle.resume_goal(
                gid, extra_turns=int(body.get("extra_turns") or 0),
                template=body.get("template") or None)
            started = _start_goal_attempt(m)
            return {"goal": _goal_detail(store, store.load(gid)),
                    "mission_id": m["id"], "started": started}
        if action == "stop":
            _goal_lifecycle.abandon(
                gid, body.get("note") or "founder abandoned the goal")
            # abandon() stops the live ATTEMPT through the same founder_stop
            # the task route uses, so it frees a slot for the same reason and
            # advances the queue through the same sweep
            _drain_queue_after("goal %s abandoned" % gid)
            return _goal_detail(store, store.load(gid))
        if action == "guidance":
            text = (body.get("text") or "").strip()
            if not text:
                raise HTTPException(400, "text required")
            _goal_lifecycle.record_founder_guidance(
                gid, text, attempt=body.get("attempt"))
            return _goal_detail(store, store.load(gid))
        if action == "confirm":
            g = store.load(gid)
            mid = g.get("current_mission_id")
            if not mid:
                raise HTTPException(409, "goal %s has no live attempt" % gid)
            mstore = _mission_engine.MissionStore()
            # the EXISTING confirmation writer; no new verification here
            m = mstore.confirm_check(mid, int(body.get("index") or 0))
            _goal_lifecycle.record_founder_confirmation(m)
            # ...and DECIDE. Recording the confirmation was never enough:
            # evaluate_done_when only ever ran inside the loop, and that
            # loop returned when it paused. settle_confirmation is the
            # loop's own evaluate-and-decide step, with no turn spent.
            shadow_runner.settle_confirmation(mid, _shadow_verifier)
            return _goal_detail(store, store.load(gid))
    except HTTPException:
        raise
    except NoLiveRuntime as exc:
        # the goal is untouched -- still draft or still blocked, nothing
        # spent -- so the founder can simply act again. `block_reason` is
        # the same deterministic id the panel already maps to copy.
        raise HTTPException(409, {"detail": str(exc),
                                  "block_reason": exc.reason,
                                  "goal_id": gid})
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    raise HTTPException(400, "unknown action %r" % action)


# A founder aside is a sentence or two, not a brief. Long enough for any real
# instruction, short enough that it cannot crowd the decider's prompt.
_SAY_MAX = 2000


@app.post("/api/shadow/missions/{mid}/act")
async def api_shadow_mission_act(mid: str, request: Request):
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    body = await request.json()
    action = body.get("action")
    store = _mission_engine.MissionStore()
    sched = _mission_engine.MissionScheduler(store)
    try:
        if action == "take_over":
            # THE FOUNDER TAKES THE WHEEL of a chat Shadow started, without
            # abandoning the outcome. Stop ends the mission; this only ends
            # SHADOW'S TURN AT IT, which is the difference the two buttons
            # carry in the design.
            #
            # Both halves already exist and neither is re-implemented here:
            # founder_intervened is the same pause an operator turn in a
            # founder-owned chat produces, and release_delegate is the one
            # reaper. Ownership ends, so the single-writer guard stops
            # refusing the send and the founder simply types -- there is
            # never a moment with two writers, because the process is reaped
            # before the pane can spawn its own.
            m = store.load(mid)
            if m is None:
                raise HTTPException(404, "no mission %s" % mid)
            # v4.2: a take-over during a hold PARKS the held instruction.
            # Leaving it armed meant the founder did the thing by hand,
            # handed back, and Approve was still offered -- pressing it did
            # it twice. unpark (on Resume / Hand back) turns the parked text
            # into a question for Shadow, never an order.
            m = _mission_engine.park_hold(store, mid)
            if m["state"] == "running":
                m = _mission_engine.MissionEngine(
                    store, None, None, None).founder_intervened(mid)
            elif m["state"] == "paused":
                # ALREADY paused, for some other reason -- recover_on_boot
                # pauses anything the app was driving when it stopped. The
                # founder taking the wheel is the CURRENT truth, and leaving
                # "app_restart" there would tell them to Resume a task they
                # just took over. paused -> paused is not a legal transition
                # (and should not become one for this), so the reason is
                # re-stamped through the store's own writer instead.
                m["pause_reason"] = "founder_intervened"
                store.save(m)
            shadow_runner.release_delegate(m.get("target_session"))
            _goal_hook_safe("on_attempt_end", m)
            # the founder now owns the chat, so Shadow is no longer running
            # this task -- the slot it held belongs to whatever is waiting
            _drain_queue_after("task %s taken over" % mid)
            return m
        if action == "stop":
            # founder_stop, not a bare transition (slice 3 finding): it is
            # what stamps `ended_by`, without which a goal reads a founder
            # decision as machine trouble and blocks instead of stopping
            #
            # ...AND THE WORKER STOPS WITH IT (founder, 2026-09-16). This
            # called MissionEngine.founder_stop directly, which writes state
            # and nothing else -- mission_engine owns no processes. Measured
            # live: Stop on a running task returned `stopped` in the same
            # second and the delegate was still alive ten seconds later,
            # still mid-turn, because the only thing that reaps a delegate is
            # the runner's terminal branch and the loop was parked in a
            # boundary wait (up to MAX_TURN_SECS). A queued or paused mission
            # has no loop at all, so nothing would ever have reaped it.
            #
            # founder_force_stop IS that same founder_stop plus the teardown,
            # in the module that owns the processes: cancel the loop, reap
            # the delegate (or kill the orphan by pid), drop the lease. Same
            # action, same button, same state, same `ended_by`.
            m = shadow_runner.founder_force_stop(mid, "founder stop (home)")
            _sync_goal_after_founder_end(m)
            # THE SLOT IS FREE THE MOMENT THE STOP IS WRITTEN, and the queue
            # must not wait for the loop to notice. The runner's wrapper
            # still promotes on its own exit and that stays the path for a
            # mission that ENDS ITSELF; this covers the stop that lands
            # between turns, and the one on a mission with no live loop at
            # all -- adopted after a restart, or a loop that died under it.
            _drain_queue_after("task %s stopped" % mid)
            return m
        if action == "drop":
            # a dropped QUEUED attempt never reaches the runner's funnel,
            # so the goal is synced here or its current_mission_id goes
            # stale forever (slice 3 finding)
            m = sched.cancel_queued(mid)
            _sync_goal_after_founder_end(m)
            return m
        if action == "start_now":
            async def _spawner(mission):
                return await _delegate_spawn(mission)
            # BEFORE the launch, not after: the answer is instant and the
            # founder's next read of the list must already see that the start
            # was taken. Stamping after would re-open the very window the
            # stamp exists to close.
            _mark_start_requested(store, mid)
            # second-flight fix: never hold the request open across a
            # minutes-long provision -- background task, instant answer
            return shadow_runner.start_mission_async(
                mid, _validated_say, provisioner=_spawner,
                verifier=_shadow_verifier)
        if action == "retry":
            clone = _mission_engine.clone_for_retry(store, mid)

            async def _respawner(mission):
                return await _delegate_spawn(mission)
            # the CLONE is the mission that starts, so it carries the stamp
            _mark_start_requested(store, clone["id"])
            return shadow_runner.start_mission_async(
                clone["id"], _validated_say, provisioner=_respawner,
                verifier=_shadow_verifier)
        if action == "confirm_check":
            m = store.confirm_check(mid, int(body.get("index") or 0))
            # the goal's progress must not keep showing a check the founder
            # has already signed off, so reflect it now instead of waiting
            # for the attempt to resume and re-evaluate
            _goal_hook_safe("record_founder_confirmation", m)
            # the SAME settle the goal arm runs -- both entry points end a
            # confirmation the same way or one of them is a dead end again
            settled = shadow_runner.settle_confirmation(mid, _shadow_verifier)
            return settled or store.load(mid)
        if action == "approve":
            # Shadow v4 (C9, ADR-043): the founder approves ONE held say by
            # its one-use approval id. The engine validates the object and
            # stamps the exact string; the loop sends it once and composes
            # nothing for it. Same cap rule as resume: approving is running.
            # THE CAP FIRST, THEN THE YES (DeepSeek P1, 2026-09-16): spending
            # the one-use approval and then refusing on capacity would leave
            # approved_say on a paused record, sendable later without a fresh
            # yes. A refusal must consume nothing.
            running_n = len(store.list(states=("running",)))
            cap = _mission_engine.max_running()
            if running_n >= cap:
                raise HTTPException(409, {
                    "detail": "Shadow is already running %d of %d tasks. "
                              "Stop one, or raise Running at once."
                              % (running_n, cap),
                    "at_capacity": True,
                    "running_now": running_n,
                    "running_at_once": cap})
            try:
                m = _mission_engine.approve_held_say(
                    store, mid, body.get("approval_id"))
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            if m.get("pause_reason") == "autonomy_top_tier":
                m["top_tier_confirmed"] = True
                store.save(m)
            m = store.transition(mid, "running",
                                 "approved say %s" % body.get("approval_id"))
            shadow_runner._launch(mid, _validated_say, _shadow_verifier)
            return m
        if action == "resume":
            # THE CAP IS A CAP ON RUNNING WORK, however the work got there.
            # Resume was the one door into `running` with no admission check
            # on it: at a cap of 2 with 2 running, resuming a paused task
            # made three, and the setting the founder had just chosen was
            # simply wrong on screen.
            #
            # REFUSED, NOT QUEUED, and that is the existing ruling rather
            # than a new one: `paused -> queued` is not a legal edge, and
            # shadow_runner.resume_after_restart already leaves a mission
            # that does not fit paused with a ledger note. This says the
            # same thing to the founder's face, with the two numbers and
            # both ways out, instead of silently doing nothing.
            #
            # ANSWERING SHADOW IS NOT RESUMING. `intervene`, `confirm_check`
            # and settle_confirmation continue a task that is already in
            # flight and whose question the founder just answered; refusing
            # those would strand a mission with its answer recorded and no
            # road left. They are deliberately NOT gated here.
            # NOT _free_slots: that asks "how many QUEUED tasks could start",
            # and a resume must not be refused merely because nothing happens
            # to be queued. The question here is only "is there room for one
            # more running task".
            running_n = len(store.list(states=("running",)))
            cap = _mission_engine.max_running()
            if running_n >= cap:
                raise HTTPException(409, {
                    "detail": "Shadow is already running %d of %d tasks. "
                              "Stop one, or raise Running at once."
                              % (running_n, cap),
                    "at_capacity": True,
                    "running_now": running_n,
                    "running_at_once": cap})
            # THE TOP-TIER YES IS SPENT HERE, AND ONLY HERE. Resuming a
            # mission held at `autonomy_top_tier` IS the founder authorising
            # the tier, so record it on the mission before it goes back to
            # running -- otherwise the loop composes its next say, asks
            # again, and the founder is in a confirm loop they cannot leave.
            #
            # ONLY that reason is spent. An L1 hold is deliberately NOT
            # stamped: L1 means "ask every turn", so its yes covers one turn
            # and the next say asks again, which is the setting working.
            prior = store.load(mid)
            if prior is not None \
                    and prior.get("pause_reason") == "autonomy_top_tier":
                prior["top_tier_confirmed"] = True
                store.save(prior)
            # v4.2: hand back -- a parked instruction becomes a question
            _mission_engine.unpark(store, mid)
            m = store.transition(mid, "running", "explicit resume (home)")
            shadow_runner._launch(mid, _validated_say, _shadow_verifier)
            return m
        if action == "reopen":
            # v4.1 (V4-9): HAND BACK TO SHADOW, AFTER THE END. The founder
            # went into the working chat of a finished task, did what they
            # wanted, and gives the chat back. Optional `text` is what they
            # want next; with none, Shadow picks up from the chat and the
            # founder confirms at the end (mission_engine._HAND_BACK_CHECK).
            # Launches exactly as `resume` does after a take-over: the say
            # path is the single writer into the chat either way.
            text = str(body.get("text") or "").strip()
            if store.load(mid) is None:
                raise HTTPException(404, "no mission %s" % mid)
            return _reopen_and_launch(
                store, mid, text[:_SAY_MAX], "talk" if text else "hand_back")
        if action == "answer":
            # v4.2: THE BUTTON ON THE ASK ROW, and the click path for a
            # typed answer. body: kind (approve|confirm|withdraw|change),
            # index?, text?. The same binding and the same three moves the
            # chat's fence takes (_apply_answer_fence); a refusal is a 409
            # in the store's own words.
            spec = {k: body.get(k) for k in ("kind", "index", "text")
                    if k in body}
            outcome = _mission_engine.apply_answer(store, mid, spec)
            m = _continue_after_answer(store, mid, outcome)
            return {**m, "answered": {"kind": outcome["kind"],
                                      "label": outcome["label"],
                                      "index": outcome.get("index")}}
        if action == "set_limits":
            # v4.1 (V4-7), THE SAME WRITER THE FENCE USES, for the sheet row
            # and for a founder who would rather click than say it. `turns`
            # is a whole number, or null / "none" for no limit.
            if "turns" not in body:
                raise HTTPException(400, "turns required (a number, or none)")
            m = _mission_engine.set_task_turns(store, mid, body.get("turns"))
            return {**m, "limits_label": _mission_engine.limits_label(m)}
        if action == "undo_limits":
            m = _mission_engine.undo_task_turns(store, mid)
            return {**m, "limits_label": _mission_engine.limits_label(m)}
        if action == "say":
            # FREE-FORM FOUNDER INPUT, UNPROMPTED. "Actually, prioritise
            # release safety." -- something the founder decides to tell
            # Shadow mid-flight, with no question outstanding.
            #
            # IT IS NOT AN INTERVENTION AND MUST NOT LOOK LIKE ONE. An
            # intervention is a question Shadow asked with a schema attached,
            # answered through `intervene`, and it closes a decision. This is
            # the founder volunteering something; it answers nothing, resolves
            # nothing, and confirms no check. Separate verb, separate field.
            #
            # IT REACHES SHADOW ALWAYS, AND THE WORKER WHEN IT MATTERS TO
            # THE WORK (founder, 2026-09-21; this said "NEVER THE WORKER"
            # until then, and that stopped being true here).
            #
            # SHADOW'S PATH IS UNCHANGED. The record is where Shadow reads,
            # run_mission re-loads it at the top of every turn, and the
            # decider still sees this line and still decides for itself what
            # the next INSTRUCTION is. `seen` is untouched. Nothing about the
            # loop, the budget or the decision moved.
            #
            # WHAT IS NEW is forward_to_worker below: a line judged capable
            # of changing the work is also put on the worker's own queue,
            # verbatim and tagged as the founder's, right now -- because
            # waiting for the decider to re-author "actually make it 20
            # lines" on a later turn is how a correction arrived after the
            # work it was correcting. It is not an instruction and cannot
            # become one; only the decider composes those.
            text = str(body.get("text") or "").strip()
            if not text:
                raise HTTPException(400, "text required")
            m = store.load(mid)
            if m is None:
                raise HTTPException(404, "no mission %s" % mid)
            # A FINISHED TASK REOPENS ON THE FOUNDER'S WORDS (v4.1, V4-9).
            # run_mission has left its loop, so appending to founder_says
            # alone would be read by nothing -- which is why this used to
            # refuse. reopen puts the words on the record AND puts the loop
            # back, so the instruction is heard rather than refused.
            if m["state"] in _mission_engine.TERMINAL:
                return _reopen_and_launch(store, mid, text[:_SAY_MAX], "say")
            says = list(m.get("founder_says") or [])
            says.append({"text": text[:_SAY_MAX],
                         "at": _mission_engine._now(),
                         "at_turn": m.get("turns_used") or 0,
                         "seen": False,
                         # NO `blocks` ON THIS DOOR, AND THAT IS CORRECT.
                         # This is the founder typing an instruction at
                         # Shadow, not a chat turn, so there is no Shadow
                         # reply to carry a verdict. shadow_forward.verdict
                         # falls through to its conservative default, which
                         # forwards anything that is not plainly a question
                         # about Shadow -- the right answer for a door whose
                         # entire purpose is to steer the work.
                         "fwd": shadow_forward.verdict(text)})
            m["founder_says"] = says
            store.save(m)
            forward_to_worker(mid, store=store)
            return store.load(mid) or m
        if action == "intervene":
            # THE FOUNDER ANSWERS THE TYPED QUESTION SHADOW ASKED.
            #
            # ONE ACTION FOR EVERY FIELD TYPE. The shape of the answer lives
            # in the request Shadow stored on the record, so adding a type
            # never adds a verb here -- which is the whole reason the form is
            # data rather than an endpoint.
            #
            # IT REUSES THE RESUME PATH VERBATIM. Nothing about the delegate
            # changes: ask_founder deliberately keeps the worker ALIVE, and
            # _launch drives the mission's existing target_session, so the
            # SAME worker continues. No respawn, no second chat.
            m = store.load(mid)
            if m is None:
                raise HTTPException(404, "no mission %s" % mid)
            iv = m.get("intervention")
            given = str(body.get("intervention_id") or "").strip()
            # STALE-SAFE, AND IDEMPOTENT. A resubmitted answer to the question
            # that was just answered is a no-op success (the founder pressed
            # twice, or a retry landed late). An answer to any OTHER id is
            # refused, so a late reply can never be read as the answer to a
            # newer question.
            answered = m.get("founder_response") or {}
            if not iv:
                if given and answered.get("intervention_id") == given:
                    return m
                raise HTTPException(409, "no intervention is waiting")
            if given and given != iv.get("id"):
                raise HTTPException(409, {
                    "detail": "that question has been superseded",
                    "active_intervention_id": iv.get("id")})
            clean, errors = _shadow_intervention.validate_values(
                iv, body.get("values") or {})
            if errors:
                # THE MISSION STAYS BLOCKED. Nothing is written, so the
                # founder simply corrects the form and sends again.
                raise HTTPException(422, {"detail": "some answers need a fix",
                                          "intervention_id": iv.get("id"),
                                          "errors": errors})
            m["founder_response"] = {
                "intervention_id": iv.get("id"),
                "question": iv.get("question") or "",
                "answered_at": _mission_engine._now(),
                "values": clean,
                "summary": _shadow_intervention.summarise(iv, clean),
            }
            m.pop("intervention", None)     # retired: it has been answered
            store.save(m)
            # AN ANSWER TO A TARGETED QUESTION CLOSES ITS CHECK (founder,
            # 2026-09-15, mission m-cd009367d41a). Shadow asked "do you
            # accept the test evidence as passing?", the founder said yes,
            # and done_when[2] ("Relevant tests pass.", founder_confirm)
            # stayed unmet -- so a mission with four of five checks passing
            # ran out of turns and died `failed`. The founder had answered
            # the exact question the check asks, in the only place Shadow
            # asked it.
            #
            # confirm_check IS STILL THE ONE WRITER. This does not set `met`;
            # it calls the same method the pane's Confirm button calls, with
            # by="founder", so confirmed_by and confirmed_at are stamped
            # identically and the dual-lane rule is intact. Shadow still
            # cannot satisfy this tier -- a founder action does, and this IS
            # a founder action.
            #
            # OPT-IN AND AFFIRMATIVE-ONLY. Only an intervention whose request
            # declared `confirms_check` reaches here at all, and only when
            # its named boolean field came back True (see
            # shadow_intervention.confirmed_index). Every other intervention
            # is byte-identical to before.
            #
            # FAILS SAFE. A stale or out-of-range index, or a check that is
            # not founder_confirm, makes confirm_check raise ValueError --
            # caught here, ledgered, and the answer still stands. An
            # intervention must never be rejected because its target moved.
            _ix = _shadow_intervention.confirmed_index(iv, clean)
            if _ix is not None:
                try:
                    m = store.confirm_check(mid, _ix, by="founder")
                except ValueError as exc:
                    import shadow_ledger as _sl
                    _sl.append("actions", {
                        "mission_id": mid, "kind": "intervention",
                        "summary": "answer targeted check %s but it could "
                                   "not be confirmed: %s" % (_ix, exc)})
            import shadow_ledger      # local, like every other ledger caller
            shadow_ledger.append("actions", {
                "mission_id": mid, "kind": "intervention",
                "summary": "founder answered %s (%d field%s)"
                           % (iv.get("id"), len(clean),
                              "" if len(clean) == 1 else "s")})
            # AN ANSWER THAT FINISHES THE TASK MUST NOT COST A TURN
            # (founder, 2026-09-16). The answer above can close the LAST
            # outstanding check -- that is what `confirms_check` is for --
            # and the mission would still be relaunched, spend a decider
            # call and a say to learn something already true, and only then
            # evaluate. On m-6b177e1cbdf0 that relaunch is precisely the say
            # that found no live runtime, eleven seconds after the founder
            # had signed off.
            #
            # settle_confirmation IS the loop's own evaluate-and-decide step
            # with no turn spent, and it is what both confirm_check arms
            # already call. It completes ONLY when evaluate_done_when says
            # every check is met, on the same evidence with the same
            # verifier; anything short of that returns the record untouched
            # and the two lines below run exactly as they always have.
            settled = shadow_runner.settle_confirmation(mid, _shadow_verifier)
            if settled is not None \
                    and settled["state"] in _mission_engine.TERMINAL:
                return settled
            # the EXISTING continuation, byte-for-byte the resume path above
            m = store.transition(mid, "running", "founder answered Shadow")
            shadow_runner._launch(mid, _validated_say, _shadow_verifier)
            return m
        if action == "delete":
            # THE FOUNDER REMOVES A TASK FROM THE LIST. Not a state and not a
            # second lifecycle: this ENDS the mission through the EXISTING
            # founder paths first, and only then removes the record.
            #
            #   queued  -> cancel_queued  (the one path for an attempt that
            #              was admitted but never launched; stamps ended_by)
            #   live    -> founder_stop   (the same writer Stop uses, so a
            #              goal reads a founder decision as a founder
            #              decision and not as machine trouble)
            #   terminal-> nothing to end
            #
            # then release_delegate -- THE one reaper, idempotent and a no-op
            # for a session Shadow never owned -- so a running task can never
            # be deleted into an orphaned worker process. The published chat,
            # its transcript and its index row are untouched: what ends is
            # Shadow's ownership, exactly as Stop and Take over end it.
            #
            # The goal layer is synced BEFORE the record goes, or a goal
            # would keep pointing current_mission_id at a file that no
            # longer exists.
            m = store.load(mid)
            if m is None:
                raise HTTPException(404, "no mission %s" % mid)
            already_archived = bool(m.get("archived_at"))
            sid, pid = m.get("target_session"), m.get("delegate_pid")
            # THE STOP IS THE RUNNER'S, NOT A STATE WRITE (founder,
            # 2026-09-19: "if we delete a shadow task, the task should stop
            # -- the underlying task too should do a hard stop").
            #
            # This branch used to call MissionEngine.founder_stop and then
            # release_delegate, which is steps 2 and 4 of the six
            # founder_force_stop performs. The three it skipped are the ones
            # that matter when the worker is not where this process can see
            # it: the LOOP TASK was never cancelled, the LEASE was never
            # released, and -- the founder's actual complaint -- there was no
            # _kill_orphan_delegate fallback, so DELEGATES being empty (which
            # it is for every mission that outlived an app restart) meant the
            # record vanished from the list while the `claude` process it
            # named kept running with nothing left pointing at it.
            #
            # founder_force_stop IS the founder's Stop, carried all the way to
            # the worker, and it is idempotent on a terminal mission.
            if m["state"] == "queued":
                m = sched.cancel_queued(mid)
                shadow_runner.release_delegate(sid)
            elif m["state"] not in _mission_engine.TERMINAL:
                m = shadow_runner.founder_force_stop(
                    mid, "founder delete (home)")
            else:
                # TERMINAL, AND STILL WORTH REAPING. founder_force_stop hands
                # a concluded mission straight back -- correctly, a stop must
                # never overwrite a completion -- so the two reapers are
                # called here directly. Both are idempotent and both no-op on
                # a session Shadow never owned.
                if shadow_runner.release_delegate(sid) is None:
                    shadow_runner._kill_orphan_delegate(pid, sid)
            _sync_goal_after_founder_end(m)
            import shadow_feed
            if not already_archived:
                # FIRST PRESS ARCHIVES (founder, 2026-09-19). The task is
                # stopped, filed under Archived in the workspace, and still
                # readable: its record, its transcript and the chat Shadow
                # made for it all stand. Erasing was the old behaviour of
                # this same press and is now what the SECOND one does.
                m = store.archive(mid, "founder archived (home)")
                # the cards still go, for the 2026-09-16 reason: an archived
                # task must not keep asking for the founder on Now.
                shadow_feed.retire(mission_id=mid)
                _drain_queue_after("task %s archived" % mid)
                return {"deleted": False, "archived": True,
                        "mission_id": mid, "target_session": sid,
                        "archived_at": m.get("archived_at")}
            # SECOND PRESS ERASES -- the path this branch has always taken.
            # the chat Shadow MADE for this task goes with it; a founder-owned
            # chat Shadow only visited never does (see _delete_delegate_chat)
            chat = _delete_delegate_chat(m)
            # LAST. The mission record is the only thing that still names the
            # session and the chat, so removing it first would strand both
            # with nothing left to find them by.
            removed = store.delete(mid)
            shadow_feed.retire(mission_id=mid)
            # ...and the slot goes with it. The runner's wrapper cannot do
            # this one: it reloads the mission to decide, and the record it
            # would read is exactly what was just removed.
            _drain_queue_after("task %s deleted" % mid)
            return {"deleted": bool(removed), "archived": False,
                    "mission_id": mid,
                    "target_session": sid, **chat}
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    raise HTTPException(400, "unknown action %r" % action)


@app.post("/api/shadow/feed/handle")
async def api_shadow_feed_handle(request: Request):
    """Opening a card marks it SEEN (founder 2026-09-16): the dot stops
    counting what the founder has already looked at (observations pass
    2026-08-26), but the card stays on Now until the task moves on -- an
    opened question is still unanswered. The relevance rule
    (shadow_feed.live_items) is what retires it; nothing here does."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_feed
    body = await request.json()
    iid = (body.get("item_id") or "").strip()
    if not iid:
        raise HTTPException(400, "item_id required")
    return {"seen": shadow_feed.mark_seen(iid), "handled": False,
            "item_id": iid}


@app.get("/api/shadow/feed")
async def api_shadow_feed():
    """PLAN-100 S59: the needs-you feed, render-only. 403 when the flag is
    off -- the panel treats any non-200 as "render the placeholder", so the
    off state costs zero client logic."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    # Only what still waits on the founder (the relevance rule in
    # shadow_feed.live_items): a card for a deleted, finished or resumed
    # task is expired on the way out, never served.
    return {"items": _shadow_feed_items()[-50:], "ts": time.time()}


def _validated_say(sid, mission_id, msg, dedupe_key=None):
    """The ONE say path (endpoint AND runner): every check or none."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    rt = lookup_runtime(sid)
    if rt is None:
        # A PRECONDITION, not a rejection -- typed so the runner can retry it
        # instead of burying the attempt. The HTTP arm below still answers
        # 404, so the wire contract is unchanged.
        raise NoLiveRuntime(sid)
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
    # FLOOR (P0, JOURNEY-TESTS.md 3a). The last app-side gate before the
    # payload is queued, so the floor is enforced HERE and not only in the
    # mission loop. floor_check had exactly one caller (mission_engine.py:331),
    # which left this path -- reachable by Shadow itself through the MCP
    # session_say tool -> POST /api/sessions/{sid}/say -- entirely unfloored.
    # Raw message, deliberately BEFORE scrub: scrub is a confidentiality
    # transform, not a safety canonicalizer, and the floor matches intent.
    # The 403 returns floor NAMES only, never the message.
    # No bypass parameter yet by design -- the three floors are never
    # ledger-overridable (SHADOW.md section 2). The one-use approved-floor
    # exception arrives with the pending_floor object in step 2 of the fix
    # order, and must consume a nonce/hash-bound approval, not re-send raw.
    # Ordinary missions never reach here floored: the loop floors the same
    # text with the same patterns and pauses first.
    tripped = shadow_egress.floor_check(msg)
    # THE ONE-USE APPROVED-FLOOR EXCEPTION (v4 C9, the step 2 this comment
    # promised): only the exact string the founder approved, only while the
    # record still carries it -- the loop clears `approved_say` as it leaves.
    approved = m.get("approved_say")
    if tripped and not (approved and approved == msg):
        raise HTTPException(403, "floor: %s" % ", ".join(tripped))
    clean, redactions = shadow_egress.scrub(msg)
    # same wire format as before, from the one writer of it -- evidence
    # assembly reads the same constant to exclude Shadow's own turns
    tagged = "%s %s" % (shadow_egress.say_tag(mission_id), clean)
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
    try:
        return _validated_say(sid, mission, msg, body.get("dedupe_key"))
    except NoLiveRuntime as exc:
        # the endpoint keeps the 404 it has always answered; only the runner
        # cares that this one is retryable
        raise HTTPException(404, str(exc))


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

    # ---- the adapter for this provider ----------------------------------
    # ONE LOOKUP, and every provider-specific question below goes through it
    # instead of another `if active_id == ...`. See provider_adapters.py for
    # what an adapter answers and what deliberately stayed here.
    #
    # None is an HONEST REFUSAL rather than a confusing crash: the frames below
    # parse Claude Code's `--output-format stream-json`, Codex's `exec --json`
    # or an ACP agent's JSON-RPC. Spawning another vendor's CLI with those flags
    # would fail on argument parsing and report as though the provider were
    # broken. No adapter has been written, so say that.
    adapter = provider_adapters.get(active_id)
    if adapter is None:
        await ws.send_json({"type": "error", "code": "no-adapter", "detail":
            "Active provider is %r (%s at %s). No chat adapter has been "
            "written for it here, so it is not being run rather than run "
            "wrongly. Use the provider selector to switch to %s, or the "
            "terminal tab." % (active_id, prov["name"], prov["bin_path"],
                               ", ".join(provider_adapters.ids()))})
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
        # STILL AN `if active_id ==` AND DELIBERATELY SO. This is not a spawn
        # rule, it is a CONNECT-TIME REFUSAL with its own error code and its own
        # close -- socket policy, which is this handler's job. What the adapter
        # owns is what the key is FOR: DeepSeekAdapter.spawn_env() turns it into
        # the environment overlay, which is the part that used to be a second
        # branch further down.
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

    settings = providers.load_settings()
    # Clamp at the point of USE, not just where it was written: a settings.json
    # from an older build, hand-edited, or written by another local process
    # would otherwise reach the spawn below with the ceiling raised.
    perm_mode = providers.effective_permission_mode(settings["permission_mode"])
    # ---- PER-CONNECTION permission mode (SPEC section E) ------------------
    # `?perm=<native mode id>` overrides the stored setting for THIS CONNECTION
    # ONLY. Nothing is written to settings.json, so the global default and every
    # other pane are untouched. ABSENT means "use the stored setting", which is
    # exactly today's behaviour -- every existing caller sends no `perm` and
    # takes the unchanged path.
    #
    # A QUERY PARAM AND NOT A MESSAGE FIELD, for the reason `?provider=` is one:
    # the permission mode is SPAWN-TIME on Claude (--permission-mode) and on
    # Codex (--sandbox / --dangerously-bypass...), and protocol-level at
    # session/new on ACP. It is fixed when the process starts, so a per-message
    # field would promise something this handler cannot deliver. Changing it
    # drops the socket and the next message opens a new one.
    #
    # THE SAME THREE CHECKS THE STORED VALUE GETS, in the same order:
    #   1. is it a real mode id            -> providers.PERMISSION_MODES
    #   2. does THIS provider enforce it   -> adapter.supports_mode()
    #   3. is it consent-gated             -> effective_permission_mode()
    #
    # (1) and (2) REFUSE rather than fall back. There is no sensible clamp for
    # "that mode does not exist" or "this provider cannot do that", and the
    # precedent is a few lines up: `?provider=` refuses an unrunnable request
    # rather than silently answering as something else, because a pane that runs
    # wider than the operator asked is the failure this whole surface exists to
    # prevent.
    #
    # (3) CLAMPS, exactly as the stored value does, and says so -- the consent
    # gate is a settings-level fact (providers.unsafe_modes_allowed), and
    # clamping an unconsented mode down to `plan` is what already happens to a
    # stored one. `permission_clamped` in the provider frame below carries it to
    # the screen so nothing is silent.
    req_perm = (ws.query_params.get("perm") or "").strip()
    perm_requested = None
    if req_perm:
        if req_perm not in providers.PERMISSION_MODES:
            await ws.send_json({"type": "error", "code": "unknown-perm-mode",
                "detail": "unknown permission mode %r -- known ids: %s"
                          % (req_perm, ", ".join(providers.PERMISSION_MODES))})
            await ws.close()
            return
        if not adapter.supports_mode(req_perm):
            await ws.send_json({"type": "error", "code": "perm-mode-unsupported",
                "detail": "provider %r cannot enforce %r. It offers: %s"
                          % (active_id, req_perm,
                             ", ".join(adapter.native_modes()))})
            await ws.close()
            return
        perm_requested = req_perm
        perm_mode = providers.effective_permission_mode(req_perm)
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
    # SECTION C: this provider's own switches (Claude's chrome/subagents/
    # workflows, Codex's memory/subagents), read ONCE per connect rather than
    # per turn -- they are spawn-time flags, so re-reading the file on every
    # message would cost a stat per turn and still could not take effect until
    # the next respawn. Defaults filled in, so a settings.json with no
    # `provider_settings` key at all yields exactly today's argv.
    provider_switches = adapter.settings()

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
        # What ?perm= asked for, and whether the consent gate clamped it. Both
        # null on every connection that did not send one, so an old client sees
        # the frame it has always seen.
        "permission_requested": perm_requested,
        "permission_clamped": bool(perm_requested and perm_requested != perm_mode),
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
    rt = adapter.new_runtime()
    inbox = asyncio.Queue()
    reader_dead = asyncio.Event()

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

    # BUSY, FOR THE UPDATE BUTTON. Updating a provider's CLI out from under a
    # running chat is how a turn dies mid-sentence, so POST /providers/tools/{id}
    # /update refuses while this count is above zero. Counted, not a boolean --
    # several panes can hold the same provider -- and released in the finally
    # below, so a disconnected browser cannot leave a provider busy forever.
    providers.chat_started(active_id)
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
            # ---- single-writer guard ---------------------------------------
            # AT MOST ONE SUTRA RUNTIME MAY WRITE TO ONE CLAUDE SESSION.
            # Shadow can own a session (a delegate it started and is driving);
            # this handler would otherwise spawn `claude --resume <sid>` for it
            # a few hundred lines below and put a SECOND process on the same
            # transcript -- the very file done_when is evaluated against.
            #
            # BEFORE the takeover block on purpose: typing into a chat Shadow
            # STARTED is not a takeover, it is a collision, and pausing the
            # mission would be the wrong answer to it. Founder-owned chats
            # Shadow merely attached to are untouched by this and still take
            # the takeover path exactly as before.
            #
            # `payload.get("resume")` as well as session_id: a pane opened
            # from the rail arrives with `resume` set and the socket's
            # session_id still None on its first message (see the chat-id
            # recovery below), which is precisely when the old code spawned.
            if payload.get("_source") != "shadow" and providers.shadow_enabled():
                try:
                    _owned = shadow_runner.driving(
                        session_id or payload.get("resume"))
                except Exception:   # noqa: BLE001 -- never fail a turn on this
                    _owned = None
                if _owned:
                    await ws.send_json({"type": "error", "detail":
                        "Shadow is working in this chat. You can read along; "
                        "you can send once it finishes or you stop it in "
                        "Focus › Shadow."})
                    continue
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

            switch_note = None
            if seed_switch:
                seed_switch = False   # once per connection, whatever happens
                try:
                    # Same resolution build_agent_args gets below; computed here
                    # because the budget depends on WHICH model will answer
                    # (Haiku 4.5 is 200K where its siblings are 1M) and the
                    # payload has to be sized before it is built.
                    plan = switch.plan(
                        sutra_id, active_id, next_message=msg,
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
            # ONE CALL, NO PROVIDER BRANCH. Each adapter knows its own builder,
            # its own resume policy and its own settings switches; what the
            # socket knows is the inputs. The three arms this replaces differed
            # in exactly those three things and in nothing else.
            #
            # Claude's argv deliberately carries NO --resume here: the reuse
            # test below compares a RESUME-FREE key built each message, and a
            # resume-bearing one made that comparison permanently unequal, so
            # any pane opened from an existing transcript cold-started claude
            # every message. The resume-bearing argv is built by
            # adapter.resume_args() a few lines down, for the spawn only.
            # Codex's argv DOES carry `resume <id>`, correctly: its process is
            # one-shot, so `alive` is always False at the top of the next turn
            # and the comparison can never mis-fire.
            args = adapter.spawn_args(
                agent_bin, msg, perm_mode, workdir, model=chosen_model,
                session_id=session_id,
                # The pane's own per-turn controls, validated inside the
                # builder rather than trusted here.
                opts=payload.get("opts"), settings=provider_switches)
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
            if not alive and session_id:
                # RESUME, if this provider has one. Claude is the only one that
                # does: it keeps one process across turns, so a dead process
                # plus a known thread means "spawn with --resume". Codex bakes
                # `resume <id>` into the spawn argv already (one process per
                # turn) and ACP has no --resume flag at all, so both adapters
                # answer None here and `args` is left exactly as built.
                _resumed = adapter.resume_args(
                    agent_bin, msg, perm_mode, workdir, model=chosen_model,
                    session_id=session_id, opts=payload.get("opts"),
                    settings=provider_switches)
                if _resumed is not None:
                    args = _resumed
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
            if not alive:
                # first-run connect serialization -- see _ACP_CONNECT_LOCK.
                # The lock is for the gemini-cli fork's FIRST RUN, which is a
                # DeepSeek fact, so the adapter owns "am I that provider" and
                # this line owns "is the marker still missing".
                _acp_locked = (getattr(adapter, "id", "") == "deepseek"
                               and _gemini_home_uninitialised())
                if _acp_locked:
                    await _ACP_CONNECT_LOCK.acquire()
                try:
                    if adapter.needs_bundled_node:
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
                    # None for every provider that needs no overlay; DeepSeek
                    # turns the key resolved at connect into its env var.
                    spawn_env = adapter.spawn_env(deepseek_key)
                    try:
                        proc = await rt.spawn(args, workdir, spawn_key, env=spawn_env)
                    except OSError as e:
                        # Real cause, verbatim -- a dead socket taught the operator nothing.
                        # And when the death IS the child closing stdout ("ACP
                        # process closed stdout"), its stderr is the only place the
                        # reason lives -- appended here rather than dropped.
                        await ws.send_json({"type": "error", "detail": _with_stderr(
                            "could not start %r in %s: %s" % (agent_bin, workdir, e),
                            await rt.stderr_tail() if not rt.alive else "")})
                        continue
                    if adapter.needs_acp_handshake:
                        # KEYED ON A CAPABILITY, NOT AN ID (was `active_id ==
                        # "deepseek"`, and `!= "claude"` before that). This block
                        # is the ACP handshake -- authenticate + session/new +
                        # the mode note -- so the question it is really asking is
                        # "does this provider speak ACP", which is exactly what
                        # the flag says. A second ACP agent (Cursor) therefore
                        # gets it with no edit here, and Codex still does not:
                        # `codex exec` has no auth step (the CLI owns
                        # ~/.codex/auth.json), no session/new (the thread arrives
                        # on stdout's first line), and its permission mode is
                        # spawn-time argv.
                        #
                        # STILL A STATEMENT OF TRUTH, NOT A BEHAVIOUR CHANGE:
                        # deepseek is the only id that has ever reached this
                        # line, and it is the only registered adapter that sets
                        # the flag today.
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
                                await ws.send_json({"type": "error", "detail": _with_stderr(
                                    "%s did not accept the saved key: %s" % (active_id, e),
                                    await rt.stderr_tail() if not rt.alive else "")})
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
                            await ws.send_json({"type": "error", "detail": _with_stderr(
                                "could not start a %s session: %s" % (active_id, e),
                                await rt.stderr_tail() if not rt.alive else "")})
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
                    else:
                        # Same divergence, same frame, computed WITHOUT a round
                        # trip for a provider whose permission posture is
                        # spawn-time argv -- the mismatch is known from
                        # `perm_mode` alone and needs no equivalent of ACP's
                        # session/new response. Reachable because permission_mode
                        # is stored globally: a `dontAsk` chosen while Claude was
                        # selected arrives here on a Codex pane. Emitted once per
                        # spawn, exactly like DeepSeek's.
                        #
                        # ASKED OF THE ADAPTER, so it is Codex's answer that
                        # arrives rather than Codex's name being tested. Claude
                        # returns None (it enforces every mode), so the `elif
                        # active_id == "codex"` this replaces has the same truth
                        # table it always had.
                        note = adapter.mode_note(perm_mode)
                        if note:
                            await ws.send_json(dict(note, type="mode_note",
                                                    provider=active_id))
                finally:
                    if _acp_locked:
                        _ACP_CONNECT_LOCK.release()
            proc = rt.proc

            # ONE CALL FOR EVERY PROVIDER. Claude's turn is a stream-json
            # user frame on stdin plus a demux loop; Codex's and ACP's are one
            # send-then-read-to-terminal. Both shapes return the SAME 5-tuple,
            # which is why everything below this point -- stderr/rc reap,
            # stop/failed/done handling, the chat bookkeeping -- was already
            # provider-neutral and needs no arm of its own.
            try:
                (session_id, got_text, got_result,
                 result_error, eof) = await adapter.run_turn(
                     rt, msg, ws.send_json, session_id)
            except (BrokenPipeError, ConnectionResetError, AttributeError) as e:
                # The process died between the liveness check and the write.
                # Claude's arm always handled this; Codex's prompt_turn handles
                # it internally and never reaches here. ACP's did NOT -- its
                # session/prompt write could raise straight out of the handler.
                # Catching it here makes that a clean error frame instead, which
                # is the same policy the other two already had.
                rt.proc = None
                await ws.send_json({"type": "error", "detail":
                    "the agent process closed before the message was sent (%s)" % e})
                continue
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
                # NAMES THE PROCESS THAT ACTUALLY DIED. Interpolating the
                # adapter's own label rather than testing for codex: an eof with
                # an empty stderr on a codex pane used to report "claude exited
                # -1" about a process named codex, and the same would have been
                # true of the next provider added.
                fallback = "%s exited %s" % (adapter.exit_label, rc)
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
        rt.kill_group()
        unregister_runtime(session_id, rt)
        providers.chat_finished(active_id)


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
