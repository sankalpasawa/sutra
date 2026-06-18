"""Sutra UI — read-only local governance dashboard (Step 1: Panel A turn feed).

One FastAPI process: serves the static page, exposes a state snapshot, a paged
log read, and an SSE live-tail. Reads only — never writes a governance file.
Run: python3 -m uvicorn app:app --host 127.0.0.1 --port 7000
"""
import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import log_reader as lr
import session_reader as sr

app = FastAPI(title="Sutra UI", docs_url=None, redoc_url=None)
HERE = Path(__file__).resolve().parent

# persistent (non-transient) marker files for the state panel — see README §4
STATE_MARKERS = ("active-role", "structure-first-active", ".last-reset-ts")

# --- chat wrapper config: drives the `claude` CLI as a subprocess (Max-plan auth, no API key) ---
CLAUDE_BIN = os.environ.get("SUTRA_UI_CLAUDE_BIN", "claude")
WORKDIR = os.path.expanduser(os.environ.get("SUTRA_UI_WORKDIR", "~/sutra-ui-workspace"))
PERM_MODE = os.environ.get("SUTRA_UI_PERMISSION_MODE", "acceptEdits")
INIT_CMD = os.environ.get("SUTRA_UI_INIT", "/core:start")          # run every fresh session so Sutra fires
AUTO_CAVEMAN = os.environ.get("SUTRA_UI_AUTO_CAVEMAN", "1") == "1"  # token-saving default (non-Max friendly)
INIT_DELAY = float(os.environ.get("SUTRA_UI_INIT_DELAY", "3.5"))    # secs to let the TUI boot before typing


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (HERE / "static" / "term.html").read_text(encoding="utf-8")


@app.get("/panels", response_class=HTMLResponse)
def panels() -> str:
    return (HERE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/sessions", response_class=HTMLResponse)
def sessions_page() -> str:
    return (HERE / "static" / "sessions.html").read_text(encoding="utf-8")


@app.get("/api/sessions")
def api_sessions(limit: int = 100):
    return sr.list_sessions(limit)


@app.get("/api/sessions/{sid}")
def api_session(sid: str):
    data = sr.read_session(sid)
    if data is None:
        raise HTTPException(status_code=404, detail="session not found")
    return data


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
    the conversation. Inherits the logged-in Max subscription (no API key in env)."""
    await ws.accept()
    os.makedirs(WORKDIR, exist_ok=True)
    session_id = None
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw).get("message", "")
            except (ValueError, AttributeError):
                msg = raw
            if not msg.strip():
                continue

            args = [
                CLAUDE_BIN, "-p", msg,
                "--output-format", "stream-json",
                "--verbose", "--include-partial-messages",
                "--permission-mode", PERM_MODE,
            ]
            if session_id:
                args += ["--resume", session_id]

            await ws.send_json({"type": "start"})
            proc = await asyncio.create_subprocess_exec(
                *args, cwd=WORKDIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=dict(os.environ),          # no ANTHROPIC_API_KEY -> subscription auth
            )
            got_text = False
            async for line in proc.stdout:
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
                elif t == "assistant" and not got_text:
                    # fallback when partial deltas are absent: emit full text blocks
                    for blk in (ev.get("message") or {}).get("content", []):
                        if blk.get("type") == "text" and blk.get("text"):
                            await ws.send_json({"type": "token", "text": blk["text"]})
                        elif blk.get("type") == "tool_use":
                            await ws.send_json({"type": "tool", "name": blk.get("name", "")})
                elif t == "result":
                    await ws.send_json({"type": "done", "session": session_id})

            err = (await proc.stderr.read()).decode("utf-8", "replace")
            rc = await proc.wait()
            if rc != 0:
                await ws.send_json({"type": "error", "detail": (err[:600] or ("claude exited " + str(rc)))})
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/term")
async def ws_term(ws: WebSocket):
    """Run the real `claude` TUI in a PTY and relay raw bytes <-> xterm.js.

    This renders the ACTUAL terminal (full parity) — it does NOT parse Claude's
    output. Drives the logged-in `claude` binary => Max-plan billing, no API key.
    """
    await ws.accept()
    if os.environ.get("ANTHROPIC_API_KEY"):
        await ws.send_text("\r\n\x1b[31mRefused: ANTHROPIC_API_KEY is set — that bills the API, not your Max plan.\x1b[0m\r\n")
        await ws.close()
        return

    # optional: resume an existing session, in its original cwd
    resume = ws.query_params.get("resume")
    req_cwd = ws.query_params.get("cwd")
    workdir = req_cwd if (req_cwd and os.path.isdir(req_cwd)) else WORKDIR
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
        if resume:
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
                rows, cols = int(m.get("r", 24)), int(m.get("c", 80))
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
