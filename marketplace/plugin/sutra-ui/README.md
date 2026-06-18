# Sutra UI — Claude Code in your browser

A local web app that puts **Claude Code (with Sutra) in a browser tab** — no terminal
app needed. Full parity (it runs the real `claude` TUI in a pseudo-terminal), plus a
**session browser** to read your history as chat and resume any session.

> **Bills as your Claude Max subscription** — same as the terminal. Never the API / Agent
> SDK. The launcher refuses to start if `ANTHROPIC_API_KEY` is set.

## Run

```bash
brew install ttyd        # optional, only for the ttyd path; the app itself needs only python
cd holding/sutra-ui
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn websockets   # one-time
cd <the project you want Claude to work in>
/path/to/holding/sutra-ui/sutra-ui.sh
# open http://127.0.0.1:7681
```

## Three views

| URL | What |
|---|---|
| `/` | **Terminal** — the real `claude` TUI (xterm.js), themed, with a sidebar of clickable actions (slash commands, starters, keys). Full function. |
| `/sessions` | **Session browser** — every local session (`~/.claude/projects/*.jsonl`), searchable. Click → read it as chat bubbles (read-only, $0). "Resume in terminal" → `claude --resume`. |
| `/panels` | **Governance panels** — live turn feed / violations / state from Sutra's logs (read-only dashboard). |

## Behaviour

- **Auto-fires `/core:start`** (~3.5s) on each fresh session so Sutra always activates.
- **Auto-`/caveman`** (token-saving) each session — toggle in the sidebar, "Restart session" to apply.
- Localhost-only by default; refuses non-loopback bind without `SUTRA_UI_ALLOW_EXTERNAL=1`.

### Config (env)

| Var | Default | Meaning |
|---|---|---|
| `SUTRA_UI_PORT` | `7681` | port (avoid 7000 — macOS AirPlay) |
| `SUTRA_UI_WORKDIR` | `$PWD` | folder `claude` runs in |
| `SUTRA_UI_AUTO_CAVEMAN` | `1` | inject `/caveman` per session |
| `SUTRA_UI_INIT` | `/core:start` | command auto-run each fresh session |

## Honest scope

This is a **themed terminal + session browser**, not a chat-bubble app. A true chat-look UI
would require rendering Claude Code's **undocumented `stream-json` control protocol**, whose
billing lane (subscription vs the June-15-2026 Agent-SDK credit pool) can't be verified from
our side. That path is **deferred** — see `HANDOFF-BRIEF.md` and the red-team log
(`~/.sutra/prompt-validation.log`). The terminal renders Claude's TUI as-is; we don't control
its internal layout/wrapping.

## Files

| File | Role |
|---|---|
| `sutra-ui.sh` | launcher (Max-billing guard + localhost guard) |
| `app.py` | FastAPI: serves the views, PTY WebSocket (`/ws/term`), session + log APIs |
| `session_reader.py` | read-only parser for saved session transcripts |
| `log_reader.py` | read-only tail of Sutra's governance JSONL |
| `static/term.html` | terminal view (xterm.js + sidebar) |
| `static/sessions.html` | session browser |
| `static/index.html` | governance panels |

See `HANDOFF-BRIEF.md` for the full decision trail.
