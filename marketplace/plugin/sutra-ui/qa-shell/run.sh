#!/usr/bin/env bash
# qa-shell/run.sh — run the production-shell publish check, then restore the app.
#
# Owns the choreography shell-check.mjs must not: putting the REAL Sutra.app
# into debug mode only for the duration of the check, and proving the backend
# it talks to belongs to THIS launch (a python child on the fixed port 8330 can
# outlive a dead shell, and the next launch silently attaches to the stale
# server — codex P1, 2026-08-18).
#
# Debug exposure is transient BY DESIGN: an unauthenticated CDP port lets any
# local process puppet the app, so the app never stays in debug mode.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${SHELL_DEBUG_PORT:-9223}"
APP="/Applications/Sutra.app"
REPO="$(cd "$HERE/.." && pwd)"
# QA_BACKEND=repo (pre-release): the installed app (2.117.0+) runs a FROZEN
# bundled payload, so the staged copy is never read. To verify REPO code in
# the real shell, start the repo's own backend on 8330 first -- main.js sees a
# Sutra already serving and ATTACHES to it instead of spawning its bundle.
# Default (app): verify the installed build as shipped.
MODE="${QA_BACKEND:-app}"
REPO_BPID=""
step(){ printf '\n== %s\n' "$*"; }

[ -d "$APP" ] || { echo "no $APP — install the app first"; exit 2; }
mkdir -p "$HERE/out"

cleanup(){
  # whatever happened, leave the founder a NORMAL app: kill any debug-mode
  # instance, clear stale backends (including the repo backend this script
  # started), reopen portless.
  pkill -x Sutra 2>/dev/null || true
  sleep 2
  [ -n "$REPO_BPID" ] && kill "$REPO_BPID" 2>/dev/null || true
  STALE=$(lsof -nP -tiTCP:8330 -sTCP:LISTEN 2>/dev/null || true)
  [ -n "$STALE" ] && kill $STALE 2>/dev/null || true
  sleep 1
  open -a Sutra
  echo "app restored to normal (portless) mode"
}
trap cleanup EXIT

step "quiesce: stop any running shell + verify the backend dies with it"
pkill -x Sutra 2>/dev/null || true
sleep 3
STALE=$(lsof -nP -tiTCP:8330 -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$STALE" ]; then
  echo "stale backend on 8330 (pid $STALE) survived its shell — killing it;"
  echo "attaching to it would have tested a server no app owns"
  kill $STALE 2>/dev/null || true
  sleep 1
fi

if [ "$MODE" = "repo" ]; then
  step "repo mode: start the REPO backend on 8330 so the shell attaches to it"
  ( cd "$REPO" && nohup .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8330 --log-level warning \
      >"$HERE/out/repo-backend.log" 2>&1 & echo $! > "$HERE/out/repo-backend.pid" )
  REPO_BPID=$(cat "$HERE/out/repo-backend.pid")
  for i in $(seq 1 30); do curl -s -o /dev/null --max-time 2 http://127.0.0.1:8330/ && break; sleep 1; done
  curl -s -o /dev/null --max-time 2 http://127.0.0.1:8330/ || { echo "repo backend never answered"; exit 1; }
  echo "repo backend pid $REPO_BPID serving $REPO"
fi

step "launch the shell in debug mode (transient)"
open -a Sutra --args --remote-debugging-port="$PORT"
for i in $(seq 1 30); do
  curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/json/version" && break
  sleep 1
done
curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/json/version" \
  || { echo "CDP port $PORT never opened"; exit 1; }

step "verify backend OWNERSHIP (not just port-open)"
for i in $(seq 1 30); do
  BPID=$(lsof -nP -tiTCP:8330 -sTCP:LISTEN 2>/dev/null || true)
  [ -n "$BPID" ] && break
  sleep 1
done
[ -n "${BPID:-}" ] || { echo "backend never bound 8330"; exit 1; }
SHELL_PID=$(pgrep -x Sutra | head -1)
if [ "$MODE" = "repo" ]; then
  # ownership in repo mode: the listener on 8330 must be the backend this script
  # started OR a descendant of it (the backgrounded launcher forks once, so the
  # bound pid is usually the recorded pid's child). Walk up to 4 levels.
  OWN=0; P="$BPID"
  for i in 1 2 3 4 5; do
    [ "$P" = "$REPO_BPID" ] && { OWN=1; break; }
    P=$(ps -o ppid= -p "$P" 2>/dev/null | tr -d ' '); [ -z "$P" ] || [ "$P" = "1" ] && break
  done
  [ "$OWN" = "1" ] \
    || { echo "backend $BPID on 8330 is not (a descendant of) the repo backend $REPO_BPID this script started — refusing"; exit 1; }
  echo "backend $BPID is the repo backend; the shell attached to it (repo code in the real shell)"
else
  BPPID=$(ps -o ppid= -p "$BPID" | tr -d ' ')
  [ "$BPPID" = "$SHELL_PID" ] \
    || { echo "backend $BPID is parented to $BPPID, not this shell $SHELL_PID — stale server, refusing"; exit 1; }
  echo "backend $BPID belongs to shell $SHELL_PID (installed build as shipped)"
fi

step "lane 1 (state) + lane 2 (pixels)"
# QA_SCRIPT: an alternative lane script (default: the chat-surface check).
# nav-check.mjs is the v3.3 shell lane — raw CDP, no playwright needed.
SHELL_DEBUG_PORT="$PORT" node "${QA_SCRIPT:-$HERE/shell-check.mjs}"
RC=$?

step "post-check liveness (the check must not have harmed the app)"
pgrep -x Sutra >/dev/null || { echo "the check killed the app — that is a lane-1 FAIL"; exit 1; }
curl -s -o /dev/null --max-time 3 http://127.0.0.1:8330/ || { echo "backend gone after check"; exit 1; }
echo "app + backend alive after detach"

exit $RC
