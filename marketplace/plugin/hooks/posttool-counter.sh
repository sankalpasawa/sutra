#!/bin/bash
# Sutra: posttool-counter.sh — fires on PostToolUse, records which tool ran.
# Per-session counter file at $SUTRA_HOME/sessions/<session_id>.counters.
# Stop hook reads + tallies + emits + cleans up.
#
# Concurrent-safe: each session has its own file keyed by session_id.

set -u

# v2.18.0 (2026-05-03): SUTRA_TELEMETRY=0 kill-switch — capture must be off
# end-to-end. Early exit BEFORE any JSON parsing or .counters file write so
# the documented "stops both capture and push uniformly" claim in PRIVACY.md
# is factually accurate. Per codex R4 finding.
[ "${SUTRA_TELEMETRY:-1}" = "0" ] && exit 0

_JSON=""
if [ ! -t 0 ]; then
  _JSON=$(cat 2>/dev/null || true)
fi

[ -z "$_JSON" ] && exit 0

TOOL=$(printf '%s' "$_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null)
SID=$(printf '%s' "$_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('session_id','unknown'))" 2>/dev/null)

[ -z "$TOOL" ] && exit 0

SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
SDIR="$SUTRA_HOME/sessions"
mkdir -p "$SDIR" 2>/dev/null

# Append tool name (one per line)
echo "$TOOL" >> "$SDIR/$SID.counters"

# Record first-fire timestamp for duration calc (only if not already there)
START="$SDIR/$SID.start"
if [ ! -f "$START" ]; then
  date +%s > "$START"
fi

exit 0
