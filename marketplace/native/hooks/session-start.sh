#!/usr/bin/env bash
# Sutra Native v1.1.0-wave1 — SessionStart auto-activation
#
# Best-effort start of the Native engine on Claude Code session start.
# Wave 1 contract: this hook attempts to acquire the PID lock + print
# the activation banner. Engine workflow execution comes in wave 2.
#
# Failures are SILENT (telemetry-only via $LOG) so a broken Native
# never blocks Claude Code session start. Per [Customer Focus First] +
# [Never bypass governance] (governance hooks must not break sessions).
#
# Intake contract per SPEC.md:
#   Native depends on core@sutra writing H-Sutra events to a JSONL log.
#   Native subscribes to that log via HSutraConnector. If core@sutra is
#   not installed, Native still starts but has no input source.
#
# Override: SUTRA_NATIVE_DISABLED=1 skips activation entirely.

set -uo pipefail  # NOT -e — failures are non-fatal

if [ "${SUTRA_NATIVE_DISABLED:-0}" = "1" ]; then
  exit 0
fi

NATIVE_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$NATIVE_ROOT" ]; then
  # Fallback: resolve relative to script location
  NATIVE_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
fi

NATIVE_HOME="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native}"
LOG="$NATIVE_HOME/native.log"
mkdir -p "$NATIVE_HOME" 2>/dev/null

BIN="$NATIVE_ROOT/bin/sutra-native"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if [ ! -x "$BIN" ]; then
  echo "[$TS] sutra-native: bin not executable at $BIN — skipping activation" >> "$LOG" 2>&1
  exit 0
fi

# Best-effort start; output to log (no stdout pollution of session start).
"$BIN" start >> "$LOG" 2>&1 || {
  EXIT=$?
  echo "[$TS] sutra-native start exit=$EXIT (likely lock-already-held; not fatal)" >> "$LOG" 2>&1
}

exit 0
