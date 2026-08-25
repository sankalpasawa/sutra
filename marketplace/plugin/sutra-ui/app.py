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
import sb_sidecar
import secrets as _secrets
import shadow_egress
from session_runtime import (SessionRuntime, _drain_to_newline,
                             _tool_command, _tool_output, _tool_summary,
                             register_runtime, unregister_runtime,
                             lookup_runtime)

# BEFORE anything reads PATH. A Finder/Dock launch inherits launchd's minimal PATH,
# so `claude` at /opt/homebrew/bin was invisible and the desktop app reported "no AI
# provider is usable here" on a machine where claude runs fine in any terminal.
# No-op when PATH already resolves a catalogued binary, i.e. for CLI/dev launches.
if providers.ensure_login_path():
    print("[providers] PATH did not resolve any AI CLI; merged the login shell's PATH "
          "(GUI launch). claude=%s" % (shutil.which("claude") or "still not found"))

app = FastAPI(title="Sutra UI", docs_url=None, redoc_url=None)

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
                     opts=None, stream_input=False):
    """The full argv for one turn.

    Separated from the socket loop so it is testable without a subprocess, and
    so adding a flag cannot accidentally change the ordering of the ones that
    already work.

    stream_input=True builds a PERSISTENT process: `-p` with no positional
    prompt plus `--input-format stream-json`, so messages arrive on stdin as
    JSON frames and one process serves many turns. Verified against the binary:
    two messages, one process, one session id, both answered.
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
    mcp_cfg = _sutra_mcp_config()
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

    fallback = providers.clean_model(opts.get("fallback_model"))
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
    for p in [root / "panel.css", root / "panel.html", *sorted((root / "js").glob("*.js"))]:
        try:
            m = p.stat().st_mtime
            if m > newest:
                newest = m
        except OSError:
            pass
    return str(int(newest))


def _panel_html() -> str:
    """The Tier-3 org/reorg studio: the reviewed design shell, wired to the real
    /api/org/* endpoints (org_api.py -> placement_engine.py). Markup and CSS
    are byte-identical to the reviewed design; only the data layer differs
    (seed constants replaced with fetch()).

    The __ASSETVER__ token in the asset URLs is substituted here, per request, so
    the page always references the version of the JS/CSS currently on disk."""
    html = (HERE / "static" / "panel.html").read_text(encoding="utf-8")
    return html.replace("__ASSETVER__", _asset_version())


# The page itself must never be cached, or the browser serves an old page whose
# asset URLs point at old ?v= tokens -- which would defeat the busting below.
# The versioned JS/CSS, by contrast, are safe to cache HARD: their URL changes
# when they do.
_NOCACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/api/files/status")
def api_files_status(start: int = 0):
    """Files screen (SilverBullet sidecar) state. `?start=1` lazily launches
    the sidecar against the configured workdir — same root, same $HOME guard,
    and the same out-of-band edit gate as /api/fs/write (sidecar goes
    read-only when editing is off). Loopback-only like everything else here."""
    if start:
        root = providers.load_settings().get("workdir") or _ensure_workdir()
        if not root:
            return JSONResponse({"running": False, "error": "no usable workdir"},
                                status_code=400)
        try:
            return sb_sidecar.start(os.path.realpath(os.path.expanduser(root)))
        except Exception as exc:  # noqa: BLE001 — panel shows the reason verbatim
            return JSONResponse({"running": False, "error": str(exc)}, status_code=500)
    return sb_sidecar.status()


@app.on_event("shutdown")
def _sb_shutdown():
    # The sidecar dies with the backend: no orphan SilverBullet process may
    # outlive the app that gated its read-only mode.
    sb_sidecar.stop()


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


@app.get("/api/sessions")
def api_sessions(limit: int = 100, offset: int = 0):
    """One page of sessions, newest first. `offset` walks back into history so
    the panel can fetch more as it scrolls; a page shorter than `limit` means
    the end. See session_reader.list_sessions for the offset-stability note."""
    return sr.list_sessions(limit, offset)


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


def _shadow_args():
    detail = providers.active_provider_detail()
    prov = providers.provider_by_id(detail["id"]) if detail["id"] else None
    if not prov or not prov.get("bin_path"):
        raise HTTPException(503, "no usable provider for Shadow")
    return build_agent_args(prov["bin_path"], "", "plan", stream_input=True)


@app.get("/api/shadow/status")
async def api_shadow_status():
    """The dot reads this: watching (green) / not (grey). Never 500s -- a
    down Shadow is a STATE the UI renders, not an error."""
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    sess = _SHADOW["session"]
    return {"watching": bool(sess and sess.alive),
            "session": sess.session_id if sess else None,
            "permission_mode": "plan"}


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
    async with _SHADOW_LOCK:
        sess = _SHADOW["session"]
        if sess is None or not sess.alive:
            sess = _shadow_session.ShadowSession()
            booted = await sess.start(
                _shadow_args, WORKDIR,
                extra_env={"SUTRA_SHADOW_SAY_TOKEN": SHADOW_SAY_TOKEN})
            if booted is None:
                raise HTTPException(503, "shadow could not boot")
            _SHADOW["session"] = sess
        tokens = []

        async def collect(frame):
            if frame.get("type") == "token":
                tokens.append(frame.get("text") or "")

        await sess.rt.send_user_frame(msg)
        (sess.session_id, _t, got_result,
         err, _e) = await sess.rt.demux_turn(collect, sess.session_id)
    if err:
        raise HTTPException(502, "shadow turn failed: %s" % err[:200])
    return {"reply": "".join(tokens), "session": sess.session_id,
            "watching": sess.alive}


# ------------------------------------------------- shadow home endpoints --
# PLAN-100 P6. All flag-gated. Instructions and watches are ledgered, never
# deleted: a revoked instruction stays on the record as inert history
# (archive-never-delete), and a watch toggle is an auditable act.
import mission_engine as _mission_engine
import shadow_precedence


@app.get("/api/shadow/instructions")
async def api_shadow_instructions():
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    import shadow_ledger
    rows = shadow_ledger.read("instructions", 200)
    latest = {}
    for r in rows:                       # last writer per id wins
        if r.get("id"):
            latest[r["id"]] = r
    return {"instructions": sorted(
        latest.values(), key=shadow_precedence.rank_key)}


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
        row = shadow_ledger.append("instructions", {
            "text": text[:1000],
            "precedence": body.get("precedence") or "history",
            "confirmed": False,
            "source_thread": body.get("source_thread")})
        return row
    if action in ("confirm", "revoke"):
        iid = body.get("id") or ""
        rows = [r for r in shadow_ledger.read("instructions", 500)
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
    return {"watching": sorted(watches)}


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
            return sched.start(mid)
        if action == "confirm_check":
            return store.confirm_check(mid, int(body.get("index") or 0))
        if action == "resume":
            return store.transition(mid, "running", "explicit resume (home)")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    raise HTTPException(400, "unknown action %r" % action)


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


@app.post("/api/sessions/{sid}/say")
async def api_session_say(sid: str, request: Request):
    if request.headers.get("x-shadow-say-token") != SHADOW_SAY_TOKEN:
        raise HTTPException(401, "missing or wrong say token")
    if not providers.shadow_enabled():
        raise HTTPException(403, "the shadow flag is off")
    rt = lookup_runtime(sid)
    if rt is None:
        raise HTTPException(404, "no live runtime for session %s" % sid)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "body must be json")
    msg = (body.get("message") or "").strip()
    mission = (body.get("mission_id") or "").strip()
    if not msg or not mission:
        raise HTTPException(400, "message and mission_id are required")
    # The endpoint is where the mission state machine BINDS (codex P1 fold):
    # a token holder must not bypass states, targets, or template invariants.
    import mission_engine as _me
    m = _me.MissionStore().load(mission)
    if m is None:
        raise HTTPException(404, "no such mission %s" % mission)
    if m["state"] != "running":
        raise HTTPException(409, "mission %s is %s, not running"
                            % (mission, m["state"]))
    if m.get("target_session") and m["target_session"] != sid:
        raise HTTPException(409, "mission %s targets %s, not %s"
                            % (mission, m["target_session"], sid))
    if "never_say" in m.get("invariants", ()):
        raise HTTPException(403, "watch missions never speak")
    clean, redactions = shadow_egress.scrub(msg)
    tagged = "[Shadow \u00b7 mission %s] %s" % (mission, clean)
    ok = rt.turn_queue.put({"message": tagged, "_source": "shadow"},
                           source="shadow",
                           dedupe_key=body.get("dedupe_key"))
    if not ok:
        raise HTTPException(409, "duplicate say (dedupe key already accepted)")
    rt.queue_event.set()
    return {"queued": True, "redactions": redactions,
            "position": len(rt.turn_queue)}


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
    detail = providers.active_provider_detail()
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

    if active_id != "claude":
        # Honest refusal instead of a confusing crash: the frames below parse
        # Claude Code's `--output-format stream-json` protocol. Spawning
        # another vendor's CLI with these flags would fail on argument
        # parsing and report as though the provider were broken. No adapter
        # has been written, so say that.
        await ws.send_json({"type": "error", "code": "no-adapter", "detail":
            "Active provider is %r (%s at %s). This chat channel speaks Claude "
            "Code's --output-format stream-json protocol and no adapter has "
            "been written for %s, so it is not being run rather than run "
            "wrongly. Use the provider selector to switch to claude, or the "
            "terminal tab." % (active_id, prov["name"], prov["bin_path"], active_id)})
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
    })

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
    rt = SessionRuntime()
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
            msg = payload.get("message", "")
            seed = payload.get("resume")
            model = payload.get("model")
            if not msg.strip():
                continue
            if (session_id is None and seed and isinstance(seed, str)
                    and seed not in dead_seeds
                    and "/" not in seed and ".." not in seed):
                session_id, resume_unverified = seed, True

            # Model: per-message override wins over the stored setting, and BOTH are
            # validated against the allow-list -- an arbitrary string here would be
            # passed straight to the CLI, where a typo fails as a dead socket several
            # seconds later instead of as a refusal now.
            chosen_model = providers.clean_model(model) or providers.stored_model()
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
            args = build_agent_args(agent_bin, msg, perm_mode,
                                    session_id=None, model=chosen_model,
                                    opts=payload.get("opts"), stream_input=True)
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

            # EXACTLY ONE `start` PER OPERATOR MESSAGE. The client treats `start`
            # as the demarcation that binds the next token stream to the next
            # QUEUED turn (`ch.pending.shift()`), so a second one for an internal
            # replay would bind the reply to whatever message the operator typed
            # while this turn was failing. A replay continues the turn that is
            # already on screen; it does not announce a new one.
            if not payload.get("_replay"):
                await ws.send_json({"type": "start", "model": chosen_model})
            if not alive:
                try:
                    proc = await rt.spawn(args, workdir, spawn_key)
                except OSError as e:
                    # Real cause, verbatim -- a dead socket taught the operator nothing.
                    await ws.send_json({"type": "error", "detail":
                        "could not start %r in %s: %s" % (agent_bin, workdir, e)})
                    continue
            proc = rt.proc

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
            # S23: now that the session id is known, make this runtime
            # discoverable (idempotent; same id + same rt every turn).
            register_runtime(session_id, rt)

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
                detail = err.strip()[:600] or result_error or ("claude exited " + str(rc))
                frame = {"type": "error", "detail": detail}
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
