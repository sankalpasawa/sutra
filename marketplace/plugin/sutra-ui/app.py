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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

import log_reader as lr
import session_reader as sr
import org_api
import providers
import connectors_store

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

    Contents: Sutra's own "sutra" server PLUS the operator's ENABLED connectors
    (connectors_store.mcp_servers_fragment). --strict-mcp-config still holds, so
    the merged set is the ONLY thing loaded — never the machine's global
    ~/.claude.json. Connector tools are deliberately NOT pre-allowed here: they
    run under the session's --permission-mode (only the sutra namespace is
    cleared by the PreToolUse hook in build_agent_args). FAIL-SOFT: if the
    connectors store errors, we fall back to just sutra and never break the
    turn.
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
    try:
        for name, spec in connectors_store.mcp_servers_fragment().items():
            if name == "sutra":
                continue  # reserved — a connector must never shadow sutra
            servers[name] = spec
    except Exception:
        pass  # a broken store must never take the turn down
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


def _tool_output(content, limit=4000):
    """A tool_result's content, flattened to text for display.

    The block is either a plain string or a list of typed parts. Only text is
    forwarded; an image is NAMED rather than inlined, because a base64 payload
    would be megabytes over a websocket that is rendering a progress view.

    Truncation is EXPLICIT. A silent cut would let someone read half a file and
    believe it was the whole one, which is worse than showing less.
    """
    if content is None:
        return None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict):
                if c.get("type") == "text" and c.get("text"):
                    parts.append(str(c["text"]))
                elif c.get("type"):
                    parts.append("[%s]" % c["type"])
        text = "\n".join(parts)
    else:
        text = str(content)
    text = text.strip()
    if not text:
        return None
    if len(text) > limit:
        return text[:limit] + ("\n… truncated, %d more characters"
                               % (len(text) - limit))
    return text


def _tool_summary(inp, limit=120):
    """One line describing what a tool was asked to do, or "".

    The UI needs to say WHICH file was read or WHICH command ran -- a column of
    identical "Bash" rows tells the operator nothing. The full input is not
    forwarded: a Write's `content` is the whole file, and shipping it to the
    browser on every call is both noise and an accidental data path.

    Key order is deliberate: the most identifying field for the common tools
    (command / file_path / pattern) first, then any short string field, then
    nothing. Never raises -- a tool with an unexpected input shape must not take
    the turn down.
    """
    if not isinstance(inp, dict):
        return ""
    # An Agent/Task input is {description, prompt, subagent_type}. The generic
    # scan below returns on the FIRST hit -- `prompt` -- and in a fan-out every
    # agent's prompt starts with the same preamble, so three parallel agents
    # rendered as three identical rows. subagent_type is the only field that says
    # WHICH agent this is, and it was dropped entirely.
    if inp.get("subagent_type") or inp.get("agent_type"):
        kind = str(inp.get("subagent_type") or inp.get("agent_type") or "agent").strip()
        desc = inp.get("description")
        if isinstance(desc, str) and desc.strip():
            v = "%s: %s" % (kind, " ".join(desc.split()))
            return v[:limit] + ("…" if len(v) > limit else "")
        return kind[:limit]
    for k in ("command", "file_path", "path", "pattern", "url", "query", "prompt",
              "description", "notebook_path"):
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return v[:limit] + ("…" if len(v) > limit else "")
    for v in inp.values():
        if isinstance(v, str) and v.strip() and len(v) <= limit:
            return " ".join(v.split())
    return ""


# A shell command is the one tool input the operator may legitimately want to run
# again by hand, so it is the one forwarded in FULL rather than as the 120-char
# display summary. Deliberately narrow: only tools that take a `command` and
# actually execute a shell. Everything else keeps the summary and nothing more --
# a Write's `content` is a whole file and has no business crossing this wire.
_SHELL_TOOLS = {"bash", "bashoutput", "killshell"}
# Long enough for any real one-liner or short heredoc; past this the paste would
# be unreviewable in a terminal prompt anyway, so it is refused rather than cut
# into something that looks complete but is not.
_COMMAND_MAX = 4000


def _tool_command(name, inp):
    """The verbatim shell command a tool was asked to run, or "".

    Never raises: an unexpected input shape must not take the turn down.
    """
    if not isinstance(inp, dict):
        return ""
    if (name or "").strip().lower() not in _SHELL_TOOLS:
        return ""
    cmd = inp.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    return cmd if len(cmd) <= _COMMAND_MAX else ""


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


def _panel_html() -> str:
    """The Tier-3 org/reorg studio: the reviewed design shell, wired to the real
    /api/org/* endpoints (org_api.py -> placement_engine.py). Markup and CSS
    are byte-identical to the reviewed design; only the data layer differs
    (seed constants replaced with fetch()).
    """
    return (HERE / "static" / "panel.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """THE app. This previously served term.html (the xterm console), so the
    front door showed a completely different UI from the studio, and the studio
    was reachable only if you already knew to type /panel. Anyone who opened
    the server saw the wrong product. The studio IS the app; the older
    surfaces remain reachable under /legacy/* below.
    """
    return _panel_html()


@app.get("/panel", response_class=HTMLResponse)
def panel_page() -> str:
    """Alias for /, so existing links and bookmarks keep working."""
    return _panel_html()


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
def api_sessions(limit: int = 100):
    return sr.list_sessions(limit)


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
    if not state_p.exists():
        return {"present": False}
    try:
        snap = json.loads(state_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Fail closed, not 500: a half-written snapshot is "not present yet".
        return {"present": False}
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
    return {"present": True, "state": snap, "today": today[-96:]}


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


# ============================================================ connectors =====
# MCP connectors the operator defines once and Sutra merges into every spawned
# turn's --mcp-config (see _sutra_mcp_config). The reads are fail-soft: a broken
# or absent store returns [] rather than a 500, because the panel polls these
# and a hard error would read as "connectors are broken" on a machine that
# simply has none. Only add_or_update raises (ValueError -> 400) on bad input.

@app.get("/api/connectors")
def api_connectors() -> dict:
    """Every stored connector, enabled or not. Read-only."""
    return {"connectors": connectors_store.load()}


@app.post("/api/connectors")
def api_connectors_upsert(body: dict):
    """Create or update one connector (matched by id; id assigned when absent).
    Returns {"connector": ...} or 400 {"error": ...} on a validation miss — bad
    name, reserved "sutra", unknown transport, stdio without command, http/sse
    without url, or a duplicate name."""
    try:
        conn = connectors_store.add_or_update(body or {})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return {"connector": conn}


@app.post("/api/connectors/{cid}/toggle")
def api_connectors_toggle(cid: str) -> dict:
    """Flip enabled for one connector. {"connector": ...} or 404."""
    conn = connectors_store.toggle(cid)
    if conn is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return {"connector": conn}


@app.delete("/api/connectors/{cid}")
def api_connectors_delete(cid: str) -> dict:
    """Delete one connector. {"ok": true} or 404."""
    if not connectors_store.remove(cid):
        raise HTTPException(status_code=404, detail="connector not found")
    return {"ok": True}


@app.get("/api/connectors/catalog")
def api_connectors_catalog() -> dict:
    """The one-click presets (blank secrets, env_keys names the vars to fill).
    Read-only, static."""
    return {"catalog": connectors_store.CATALOG}


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
    live = {"proc": None, "stopped": False}
    inbox = asyncio.Queue()
    reader_dead = asyncio.Event()

    def _kill_live():
        """Kill the process GROUP, not just the direct child.

        `claude` spawns helpers; signalling only the parent leaves them holding
        the stdout pipe, so the read loop never ends and the turn never actually
        stops. The spawn below uses start_new_session=True, which makes the child
        a group leader so this reaches its descendants too.
        """
        p = live["proc"]
        if p is None or p.returncode is not None:
            return False
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                p.kill()
            except (ProcessLookupError, OSError):
                return False
        return True

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
                    live["stopped"] = True
                    _kill_live()
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
            else:
                get_next = asyncio.ensure_future(inbox.get())
                gone = asyncio.ensure_future(reader_dead.wait())
                done, _ = await asyncio.wait({get_next, gone},
                                             return_when=asyncio.FIRST_COMPLETED)
                if get_next not in done:
                    get_next.cancel()  # socket closed -- stop serving this channel
                    break
                gone.cancel()
                payload = get_next.result()
            live["stopped"] = False
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
            proc = live.get("proc")
            alive = proc is not None and proc.returncode is None
            if alive and live.get("key") != spawn_key:
                # a spawn-time option changed: end this process and carry the
                # conversation over rather than dropping it
                _kill_live()
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
                    proc = await asyncio.create_subprocess_exec(
                        *args, cwd=workdir,
                        # stdin is a PIPE now, not DEVNULL: it is the channel the
                        # turns arrive on. (DEVNULL was there because a plain
                        # inherited stdin made claude wait 3s for piped input on
                        # every message -- with stream-json that wait IS the
                        # feature.)
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=dict(os.environ),  # no ANTHROPIC_API_KEY -> subscription auth
                        # own process group, so an interrupt can signal the whole tree
                        start_new_session=True,
                    )
                except OSError as e:
                    # Real cause, verbatim -- a dead socket taught the operator nothing.
                    await ws.send_json({"type": "error", "detail":
                        "could not start %r in %s: %s" % (agent_bin, workdir, e)})
                    continue
                live["proc"] = proc
                live["key"] = spawn_key
            proc = live["proc"]

            # The turn itself: one stream-json frame on stdin.
            try:
                proc.stdin.write((json.dumps({
                    "type": "user",
                    "message": {"role": "user",
                                "content": [{"type": "text", "text": msg}]},
                }) + "\n").encode("utf-8"))
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, AttributeError) as e:
                # the process died between the liveness check and the write
                live["proc"] = None
                await ws.send_json({"type": "error", "detail":
                    "the agent process closed before the message was sent (%s)" % e})
                continue

            got_text = got_result = False
            result_error = None
            # READ UNTIL THIS TURN'S `result`, not until EOF. The process is
            # persistent now, so EOF only happens when it DIES -- an `async for`
            # over stdout would simply never return.
            eof = False
            while True:
                line = await proc.stdout.readline()
                if not line:
                    eof = True
                    break
                try:
                    ev = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                # capture session id from the first event that carries one
                if session_id is None and ev.get("session_id"):
                    session_id = ev["session_id"]
                    await ws.send_json({"type": "session", "id": session_id})
                t = ev.get("type")
                if t == "stream_event":
                    delta = (ev.get("event") or {}).get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        got_text = True
                        await ws.send_json({"type": "token", "text": delta["text"]})
                elif t == "assistant":
                    for blk in (ev.get("message") or {}).get("content", []):
                        # fallback when partial deltas are absent: emit full text blocks
                        if blk.get("type") == "text" and blk.get("text") and not got_text:
                            await ws.send_json({"type": "token", "text": blk["text"]})
                        elif blk.get("type") == "thinking":
                            # Presence only. The thinking TEXT is deliberately not
                            # forwarded: it is the model's scratchpad, it is long, and
                            # rendering it as if it were the answer misrepresents both.
                            await ws.send_json({"type": "thinking"})
                        elif blk.get("type") == "tool_use":
                            # tool_use blocks never arrive as text deltas, so this must
                            # run regardless of got_text -- gating it behind the text
                            # fallback meant a streaming turn reported zero tool calls.
                            #
                            # phase=start + id: the id is what `tool_result` correlates
                            # against (verified against a real `claude -p` run: tool_use.id
                            # == tool_result.tool_use_id). Without it the UI could show
                            # that a tool was CALLED but never that it finished, so every
                            # tool appeared to run forever.
                            await ws.send_json({
                                "type": "tool",
                                "phase": "start",
                                "id": blk.get("id"),
                                "name": blk.get("name", ""),
                                "summary": _tool_summary(blk.get("input")),
                                # Shell commands only, in full -- what "open this in
                                # the terminal" needs. "" for every other tool.
                                "command": _tool_command(blk.get("name", ""),
                                                         blk.get("input")),
                                # Forwarded VERBATIM. Observed {"type":"direct"} for a
                                # main-agent call; other shapes are not guessed at here,
                                # and the client labels whatever actually arrives.
                                "caller": (blk.get("caller") or {}).get("type"),
                            })
                elif t == "user":
                    # tool_result lives on USER messages, not assistant ones. This branch
                    # did not exist, so every tool result was dropped and completion was
                    # unknowable by construction.
                    for blk in (ev.get("message") or {}).get("content", []):
                        if isinstance(blk, dict) and blk.get("type") == "tool_result":
                            _out = _tool_output(blk.get("content"))
                            # A BACKGROUND agent's tool_result is a LAUNCH RECEIPT,
                            # not a completion: it arrives immediately, carries the
                            # Agent's tool_use_id, and its content begins "Async
                            # agent launched successfully". Emitting phase:end here
                            # marked the subagent finished the instant it started.
                            # Its REAL completion comes later as a system/
                            # task_notification with the same tool_use_id (handled
                            # in the system branch). Skip the receipt; the tool
                            # stays running until that notification lands. Measured
                            # against claude v2.1.212, stream-json, run_in_background.
                            if _out.strip().startswith("Async agent launched"):
                                continue
                            await ws.send_json({
                                "type": "tool",
                                "phase": "end",
                                "id": blk.get("tool_use_id"),
                                "ok": not blk.get("is_error"),
                                # WHAT THE TOOL ACTUALLY RETURNED. This was dropped:
                                # the frame carried {id, ok} and the whole content
                                # array was discarded server-side, so an operator
                                # could see that Read ran and never what it read,
                                # and a failing tool showed a red dot with no reason
                                # attached -- the one thing you need when a turn
                                # goes wrong.
                                "output": _out,
                            })
                elif t == "system":
                    # THE FOURTH TYPE THE PARSER NEVER HANDLED. The dispatch knew
                    # stream_event / assistant / user / result and silently
                    # `continue`d past everything else, so two useful things were
                    # invisible:
                    #
                    #   init      what the session actually resolved -- model,
                    #             tool count, mcp servers, plugins. The panel
                    #             showed the model it REQUESTED, never the one in
                    #             force, and those differ whenever a fallback or
                    #             a settings default applies.
                    #   api_retry a rate-limit backoff. Claude waits and retries;
                    #             with no frame for it the pane sat silent and
                    #             the turn read as HUNG. "Waiting, retrying" and
                    #             "wedged" look identical when nothing is sent.
                    sub = ev.get("subtype")
                    if sub == "init":
                        await ws.send_json({
                            "type": "sysinit",
                            "model": ev.get("model"),
                            "tools": len(ev.get("tools") or []),
                            "mcp_servers": [
                                {"name": m.get("name"), "status": m.get("status")}
                                for m in (ev.get("mcp_servers") or [])
                                if isinstance(m, dict)],
                            "slash_commands": len(ev.get("slash_commands") or []),
                            "permission_mode": ev.get("permissionMode"),
                            "cwd": ev.get("cwd"),
                        })
                    elif sub == "api_retry":
                        await ws.send_json({
                            "type": "retrying",
                            "detail": str(ev.get("message") or ev.get("error")
                                          or "the API asked us to retry")[:300],
                            "attempt": ev.get("attempt"),
                        })
                    elif sub == "task_notification":
                        # THE REAL completion of a background agent. Its receipt
                        # tool_result was skipped above, so the UI shows the agent
                        # running until THIS frame -- which carries the same
                        # tool_use_id the UI opened the tool with, plus the summary
                        # and usage the receipt never had. task_started/task_progress
                        # fire while it runs and are intentionally not forwarded (the
                        # tool row already reads "running"); only the terminal
                        # notification closes it. Measured shape: {tool_use_id,
                        # status, summary, usage{...}}.
                        status = ev.get("status") or "completed"
                        tuid = ev.get("tool_use_id")
                        if tuid and status in ("completed", "failed", "cancelled"):
                            await ws.send_json({
                                "type": "tool",
                                "phase": "end",
                                "id": tuid,
                                "ok": status == "completed",
                                "output": str(ev.get("summary") or "")[:4000],
                            })
                elif t == "result":
                    got_result = True
                    # A `result` event is NOT proof of success: a failed run (stale
                    # --resume, permission abort, API error) emits one with
                    # is_error/subtype set and THEN exits non-zero. Sending "done"
                    # here painted a failed turn as answered-with-empty-text, and the
                    # real error arrived a frame later -- where the client attributed
                    # it to whatever turn came next. Hold it and report once, below.
                    if ev.get("is_error") or (ev.get("subtype") or "success") != "success":
                        result_error = str(ev.get("result") or ev.get("subtype")
                                           or "claude reported an error")[:600]
                    else:
                        # Carry the REAL measurements the result frame already has, so
                        # the UI states duration and cost instead of estimating them.
                        await ws.send_json({
                            "type": "done",
                            "session": session_id,
                            "duration_ms": ev.get("duration_ms"),
                            "num_turns": ev.get("num_turns"),
                            "cost_usd": ev.get("total_cost_usd"),
                        })
                    # `result` closes THIS TURN. The process stays up for the
                    # next one -- that is the whole point of the change.
                    break

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
                live["proc"] = None
                live["key"] = None

            if live["stopped"]:
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
                live["stopped"] = False
                live["proc"] = None
                live["key"] = None
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
        _kill_live()


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
