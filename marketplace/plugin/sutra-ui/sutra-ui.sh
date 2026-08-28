#!/usr/bin/env bash
# Sutra UI — Claude Code in your browser, with friendly chrome.
#
# Serves a FastAPI app that runs the real `claude` TUI in a pseudo-terminal and
# renders it with xterm.js, wrapped in a sidebar of clickable actions. Full
# terminal parity (it IS the terminal) + buttons that type for you.
#
# BILLING INVARIANT: drives the `claude` CLI you are logged into (Claude Max),
# the SAME billing as the terminal. NOT the API, NOT the Agent SDK.
# REFUSES to start if any backend-redirect variable is set (see SUTRA_REDIRECT_VARS).
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
SUTRA_REDIRECT_VARS="ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY ANTHROPIC_BEDROCK_BASE_URL ANTHROPIC_VERTEX_BASE_URL CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX"
# Mirror of billing_guard.REDIRECT_VARS; test_billing_guard.py fails on drift.
# Presence is NOT the test: Claude Code itself exports
# ANTHROPIC_BASE_URL=https://api.anthropic.com, and refusing on that would brick
# the panel over a setting that redirects nothing. Values decide.
_sutra_official() {
  _h=${1#*://}; _h=${_h%%/*}; _h=${_h##*@}; _h=${_h%%:*}
  _h=$(printf '%s' "$_h" | tr '[:upper:]' '[:lower:]')
  case "$_h" in anthropic.com|*.anthropic.com) return 0 ;; *) return 1 ;; esac
}
_sutra_redirected=""
for _v in ANTHROPIC_BASE_URL ANTHROPIC_BEDROCK_BASE_URL ANTHROPIC_VERTEX_BASE_URL; do
  eval "_val=\${$_v:-}"
  if [ -n "$_val" ] && ! _sutra_official "$_val"; then
    _sutra_redirected="$_sutra_redirected $_v"
  fi
done
for _v in ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY; do
  eval "_val=\${$_v:-}"
  [ -n "$_val" ] && _sutra_redirected="$_sutra_redirected $_v"
done
for _v in CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX; do
  eval "_val=\${$_v:-}"
  case "$(printf '%s' "$_val" | tr '[:upper:]' '[:lower:]')" in
    ''|0|false|no|off) ;;
    *) _sutra_redirected="$_sutra_redirected $_v" ;;
  esac
done
if [ -n "$_sutra_redirected" ] && [ -z "${SUTRA_UI_ALLOW_BACKEND_REDIRECT:-}" ]; then
  echo "REFUSING TO START:$_sutra_redirected set -- that sends every turn to a backend other than your Max plan." >&2
  echo "  Your prompts -- and whatever the agent reads -- would go there, not to your Max plan." >&2
  echo "  Fix: unset$_sutra_redirected; ensure 'claude' is logged into Max (claude /login)." >&2
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
