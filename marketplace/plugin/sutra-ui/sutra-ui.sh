#!/usr/bin/env bash
# Sutra UI — Claude Code in your browser, with friendly chrome.
#
# Serves a FastAPI app that runs the real `claude` TUI in a pseudo-terminal and
# renders it with xterm.js, wrapped in a sidebar of clickable actions. Full
# terminal parity (it IS the terminal) + buttons that type for you.
#
# BILLING INVARIANT: drives the `claude` CLI you are logged into (Claude Max),
# the SAME billing as the terminal. NOT the API, NOT the Agent SDK.
# REFUSES to start if ANTHROPIC_API_KEY is set.
#
# Usage:
#   cd <project you want Claude to work in>
#   /path/to/sutra-ui.sh
#   SUTRA_UI_PORT=9000 SUTRA_UI_WORKDIR=~/proj /path/to/sutra-ui.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${SUTRA_UI_HOST:-127.0.0.1}"
PORT="${SUTRA_UI_PORT:-7681}"
export SUTRA_UI_WORKDIR="${SUTRA_UI_WORKDIR:-$PWD}"

# --- Max-plan billing guard (#1 invariant) ---
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "REFUSING TO START: ANTHROPIC_API_KEY is set." >&2
  echo "  That routes through the API (per-token billing), NOT your Max plan." >&2
  echo "  Fix: unset ANTHROPIC_API_KEY; ensure 'claude' is logged into Max (claude /login)." >&2
  exit 2
fi

# --- dependencies ---
command -v claude >/dev/null 2>&1 || { echo "claude CLI not found on PATH." >&2; exit 2; }
if [ ! -x "$DIR/.venv/bin/python" ]; then
  echo "Python venv missing. One-time setup:" >&2
  echo "  cd '$DIR' && python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn websockets" >&2
  exit 2
fi

# --- localhost guard (a browser terminal = full machine access as you) ---
if [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ] && [ "${SUTRA_UI_ALLOW_EXTERNAL:-0}" != "1" ]; then
  echo "REFUSING to bind $HOST — anyone reaching it controls this machine as you." >&2
  echo "  Set SUTRA_UI_ALLOW_EXTERNAL=1 to override (add auth first)." >&2
  exit 2
fi

# open in the browser for you. SUTRA_UI_DEPT=marketing|sales|cs|hr|finance|devpm tunes the
# "Your tasks" panel; omit for the universal set. SUTRA_UI_NO_OPEN=1 disables auto-open.
URL="http://$HOST:$PORT/${SUTRA_UI_DEPT:+?dept=$SUTRA_UI_DEPT}"

echo "Sutra UI  ->  $URL"
echo "  claude workdir: $SUTRA_UI_WORKDIR"
echo "  auth:           Claude Max subscription (no API key)"
echo "  stop:           Ctrl-C"

# auto-open the browser once the server is up (backgrounded; exec below stays in foreground)
if [ "${SUTRA_UI_NO_OPEN:-0}" != "1" ] && command -v open >/dev/null 2>&1; then
  ( sleep 1.8; open "$URL" ) &
fi

cd "$DIR"
exec .venv/bin/python -m uvicorn app:app --host "$HOST" --port "$PORT" --log-level warning
