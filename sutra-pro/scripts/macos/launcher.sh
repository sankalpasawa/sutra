#!/bin/bash
# Sutra Pro.app launcher (Contents/MacOS/SutraPro). There is no desktop shell (D12): this script starts the bundled Python
# running `python -m sutra_app`, opens the default browser on it, and stops the server when the app quits.
#
#   1. find the bundled interpreter (Contents/Resources/python), data folder SUTRA_DATA_DIR (default ~/.sutra-pro)
#   2. one instance per data folder (the server is the only SQLite writer): a second launch opens the browser on the first
#   3. first free port in 8780-8799 (as `sutra-pro` picks), or SUTRA_PORT
#   4. start the server, wait for /api/health, open the browser
#   5. stay alive until the server ends; SIGTERM / SIGINT / SIGHUP stop it; a detached watchdog stops it even if this script is killed
# Everything is logged to <data folder>/logs/app.log (rotated at 5 MB). A start failure shows one dialog (osascript) and exits 1.
#
# Environment (all optional): SUTRA_DATA_DIR, SUTRA_PORT, SUTRA_PORT_MIN / SUTRA_PORT_MAX (default 8780 / 8799),
# SUTRA_START_TIMEOUT (seconds to wait for /api/health, default 60), SUTRA_EXTRA_PATH (appended to PATH), SUTRA_NO_DIALOG=1.
#
# bash 3.2 is what macOS ships: no associative arrays, no `wait -n`, no ${var,,}.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$HERE/../Resources"
PY="$RESOURCES/python/bin/python3"
DATA_DIR="${SUTRA_DATA_DIR:-$HOME/.sutra-pro}"
LOG_DIR="$DATA_DIR/logs"
LOG="$LOG_DIR/app.log"
PIDFILE="$DATA_DIR/app.pid"
PORT_MIN="${SUTRA_PORT_MIN:-8780}"
PORT_MAX="${SUTRA_PORT_MAX:-8799}"
START_TIMEOUT="${SUTRA_START_TIMEOUT:-60}"

SERVER_PID=""
WATCH_PID=""
STOPPING=0

# A GUI-launched app gets a bare PATH; the claude and codex CLIs the connectors run live elsewhere.
PATH="${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.claude/local:$HOME/.npm-global/bin:$HOME/.bun/bin${SUTRA_EXTRA_PATH:+:$SUTRA_EXTRA_PATH}"
export PATH
# The bundled interpreter must see nothing of the user's Python setup, and must never write into the (signed) bundle.
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONINSPECT PYTHONEXECUTABLE VIRTUAL_ENV
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export SUTRA_DATA_DIR="$DATA_DIR"

log() { printf '%s launcher: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"; }

fail() {
  log "ERROR: $1"
  if [ "${SUTRA_NO_DIALOG:-0}" != "1" ] && command -v osascript >/dev/null 2>&1; then
    osascript -e 'on run argv' \
      -e 'display dialog (item 1 of argv) with title "Sutra Pro" buttons {"OK"} default button "OK" with icon stop' \
      -e 'end run' "$1

Details: $LOG" >/dev/null 2>&1 || true
  fi
  exit 1
}

healthy() { curl -fsS --noproxy '*' --max-time 2 -o /dev/null "http://127.0.0.1:$1/api/health" 2>/dev/null; }
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
open_browser() { open "http://127.0.0.1:$1/" || log "could not open the browser; open http://127.0.0.1:$1/ yourself"; }

cleanup() {
  if [ "$STOPPING" = 1 ]; then return 0; fi
  STOPPING=1
  if [ -n "$WATCH_PID" ]; then kill "$WATCH_PID" 2>/dev/null; fi
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    log "stopping the server (pid $SERVER_PID)"
    kill -TERM "$SERVER_PID" 2>/dev/null
    waited=0
    while kill -0 "$SERVER_PID" 2>/dev/null && [ "$waited" -lt 100 ]; do sleep 0.1; waited=$((waited + 1)); done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      log "the server ignored SIGTERM for 10 s: killing it"
      kill -KILL "$SERVER_PID" 2>/dev/null
    fi
  fi
  if [ -f "$PIDFILE" ] && [ "$(cut -d' ' -f1 "$PIDFILE" 2>/dev/null)" = "$$" ]; then rm -f "$PIDFILE"; fi
}

# ---- 1. the bundle and the data folder
# the data folder holds the user's work: private (0700), as the server makes it, not the 0755 a plain mkdir -p gives under the usual umask
# (found by `sutra-pro doctor` right after the first real launch of the installed app)
if ! (umask 077 && mkdir -p "$LOG_DIR"); then fail "Cannot create the data folder $DATA_DIR."; fi
chmod 700 "$DATA_DIR" 2>/dev/null || true
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" | tr -d ' ')" -gt 5242880 ]; then mv -f "$LOG" "$LOG.1"; fi
exec < /dev/null >> "$LOG" 2>&1
log "starting (bundle $HERE, data $DATA_DIR)"
if [ ! -x "$PY" ]; then fail "The bundled Python is missing or not executable: $PY. Download the app again."; fi
cd "$DATA_DIR" || fail "Cannot enter the data folder $DATA_DIR."

# ---- 2. one instance per data folder
if [ -f "$PIDFILE" ]; then
  read -r old_pid old_port < "$PIDFILE" || true
  if [ -n "${old_pid:-}" ] && [ -n "${old_port:-}" ] && kill -0 "$old_pid" 2>/dev/null && healthy "$old_port"; then
    log "already running (pid $old_pid, port $old_port): opening the browser on it"
    open_browser "$old_port"
    exit 0
  fi
  log "stale $PIDFILE (pid ${old_pid:-?}): ignored"
  rm -f "$PIDFILE"
fi

# ---- 3. the port
PORT=""
case "${SUTRA_PORT:-}" in
  "") ;;
  *[!0-9]*) fail "SUTRA_PORT must be a number, not '$SUTRA_PORT'." ;;
  *) PORT="$SUTRA_PORT"
     if port_busy "$PORT"; then fail "Port $PORT (SUTRA_PORT) is already in use."; fi ;;
esac
if [ -z "$PORT" ]; then
  candidate="$PORT_MIN"
  while [ "$candidate" -le "$PORT_MAX" ]; do
    if ! port_busy "$candidate"; then PORT="$candidate"; break; fi
    candidate=$((candidate + 1))
  done
  if [ -z "$PORT" ]; then fail "No free port between $PORT_MIN and $PORT_MAX. Quit the other Sutra Pro and try again."; fi
fi

# ---- 4. start the server and wait until it answers
trap 'cleanup; exit 143' TERM
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 129' HUP
trap cleanup EXIT
log "starting the server on 127.0.0.1:$PORT"
"$PY" -m sutra_app --no-browser --port "$PORT" --data-dir "$DATA_DIR" &
SERVER_PID=$!

# If this script is killed hard (SIGKILL cannot be trapped), the watchdog still stops the server within a second.
LAUNCHER_PID=$$
(
  while kill -0 "$LAUNCHER_PID" 2>/dev/null && kill -0 "$SERVER_PID" 2>/dev/null; do sleep 1; done
  if ! kill -0 "$LAUNCHER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null
    sleep 5
    kill -KILL "$SERVER_PID" 2>/dev/null
  fi
) > /dev/null 2>&1 &
WATCH_PID=$!

deadline=$((SECONDS + START_TIMEOUT))
until healthy "$PORT"; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    wait "$SERVER_PID"
    fail "The server stopped while starting (exit status $?)."
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then fail "The server did not answer /api/health within $START_TIMEOUT seconds."; fi
  sleep 0.2
done
printf '%s %s\n' "$$" "$PORT" > "$PIDFILE.$$" && mv -f "$PIDFILE.$$" "$PIDFILE"
log "ready: http://127.0.0.1:$PORT/ (server pid $SERVER_PID)"
open_browser "$PORT"

# ---- 5. live until the server ends
wait "$SERVER_PID"
code=$?
log "the server exited with status $code"
if [ "$code" -ne 0 ]; then fail "Sutra Pro stopped unexpectedly (exit status $code)."; fi
exit 0
