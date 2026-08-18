#!/usr/bin/env bash
# Balance V1 daily pass — 21:30 via launchd (os.asawa.balance-daily.plist).
# Single-instance via mkdir lock (macOS has no flock binary — consult fold).
# Derives repo root from its own path; launchd-safe (no cwd/env assumptions).
set -u
SELF="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SELF/../.." && pwd)"
BALDIR="${SUTRA_BALANCE_STATE_DIR:-${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.sutra/balance}}"
BALDIR="${BALDIR:-$REPO/holding/state/balance}"
mkdir -p "$BALDIR" 2>/dev/null || true
LOCK="$BALDIR/.daily-pass.lock"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

if ! mkdir "$LOCK" 2>/dev/null; then
  # Stale-lock recovery: a lock older than 30 min belongs to a dead run.
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || true
    mkdir "$LOCK" 2>/dev/null || { echo "balance-daily-pass: locked, exiting"; exit 0; }
  else
    echo "balance-daily-pass: another run in progress, exiting"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

/usr/bin/python3 "$SELF/balance_coach_pass.py" || exit 1
/usr/bin/python3 "$SELF/balance-render-dashboard.py" || exit 1
echo "balance-daily-pass: OK $(date -u +%Y-%m-%dT%H:%M:%SZ)"
