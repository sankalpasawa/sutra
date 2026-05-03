#!/usr/bin/env bash
# Sutra Native v1.1.0-wave1 — Stop teardown
#
# Best-effort graceful teardown on Claude Code session Stop.
# Releases the PID lock so the next SessionStart can re-acquire cleanly.
#
# Per founder direction 2026-05-03 + codex consult: Stop hook is required
# for teardown / flush; missing it leaves stale lock files.
#
# Failures are SILENT (telemetry-only via $LOG) per [Never bypass governance].

set -uo pipefail  # NOT -e — failures non-fatal

if [ "${SUTRA_NATIVE_DISABLED:-0}" = "1" ]; then
  exit 0
fi

NATIVE_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$NATIVE_ROOT" ]; then
  NATIVE_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
fi

NATIVE_HOME="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native}"
LOG="$NATIVE_HOME/native.log"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

BIN="$NATIVE_ROOT/bin/sutra-native"
if [ -x "$BIN" ]; then
  "$BIN" stop >> "$LOG" 2>&1 || {
    EXIT=$?
    echo "[$TS] sutra-native stop exit=$EXIT (likely no-lock-to-release; not fatal)" >> "$LOG" 2>&1
  }
fi

exit 0
