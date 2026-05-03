#!/bin/bash
# Sutra: flush-telemetry.sh — Stop-hook handler (v1).
# Per codex review 2026-04-20: Stop hook does LOCAL work only.
# No network, no git, no auth. Session teardown must stay light.
#
# What this does:
#   1. Emit 1 summary metric (hook_fires_session) from session log if present
#   2. Ensure queue is flushed to disk (already is — queue.sh appends synchronously)
#   3. Log queue depth to ~/.sutra/last-flush.txt for status command
#
# Actual network push happens in /sutra-push (explicit, user-initiated)
# or an async background task the user can start separately.

set -u

# Read Stop event JSON from stdin (if available) to get session_id for counters
_STDIN=""
if [ ! -t 0 ]; then
  _STDIN=$(cat 2>/dev/null || true)
fi
SID=""
if [ -n "$_STDIN" ]; then
  SID=$(printf '%s' "$_STDIN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('session_id',''))" 2>/dev/null)
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
source "$PLUGIN_ROOT/lib/queue.sh"

queue_init

COUNT=$(queue_count)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Summary to last-flush marker (for /sutra-status)
cat > "$SUTRA_HOME/last-flush.txt" <<TXT
last_flush_ts: $TS
queue_depth:   $COUNT
note:          Stop-hook flush is local-only; run /sutra-push to transmit.
TXT

# Append existing estimation-log semantics (v0.1 kept working)
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$PROJECT_ROOT/.claude/sutra-estimation.log"
MARKER="$PROJECT_ROOT/.claude/depth-registered"
mkdir -p "$(dirname "$LOG")" 2>/dev/null
{
  echo "=== $TS ==="
  if [ -f "$MARKER" ]; then
    echo "depth_marker: $(cat "$MARKER")"
  else
    echo "depth_marker: (absent)"
  fi
  echo "queue_depth: $COUNT"
} >> "$LOG" 2>/dev/null || true

# ── v1.1 auto-emission ────────────────────────────────────────────────
# Emit 3 observability metrics per Stop. Best-effort (do not fail the hook).
EMIT="$PLUGIN_ROOT/hooks/emit-metric.sh"
if [ -x "$EMIT" ]; then
  MARKER_PRESENT=0
  [ -f "$MARKER" ] && MARKER_PRESENT=1
  bash "$EMIT" sessions  session_stops_total     1                  count instant 2>/dev/null || true
  bash "$EMIT" os_health queue_depth_at_stop     "$COUNT"           count instant 2>/dev/null || true
  bash "$EMIT" os_health depth_marker_present    "$MARKER_PRESENT"  count instant 2>/dev/null || true
fi

# ── v1.2 per-session tool counters + duration ─────────────────────────
# Read counters that PostToolUse hook accumulated for this session_id.
# Emit total tool_uses + per-tool counts + duration. Cleanup files.
SDIR="$SUTRA_HOME/sessions"
if [ -n "$SID" ] && [ -x "$EMIT" ] && [ -f "$SDIR/$SID.counters" ]; then
  TOTAL=$(wc -l < "$SDIR/$SID.counters" | tr -d ' ')
  bash "$EMIT" sessions tool_uses_session "$TOTAL" count instant 2>/dev/null || true

  # Per-tool counts (lowercased metric names)
  python3 -c "
import collections
c = collections.Counter(l.strip() for l in open('$SDIR/$SID.counters') if l.strip())
for tool, n in c.most_common():
    print(f'{tool.lower()}_uses_session {n}')
" 2>/dev/null | while read -r METRIC N; do
    [ -n "$METRIC" ] && bash "$EMIT" sessions "$METRIC" "$N" count instant 2>/dev/null || true
  done

  # Duration since first PostToolUse fire
  if [ -f "$SDIR/$SID.start" ]; then
    START_TS=$(cat "$SDIR/$SID.start" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    DUR=$((NOW - START_TS))
    [ "$DUR" -ge 0 ] && bash "$EMIT" sessions session_duration_sec "$DUR" count instant 2>/dev/null || true
  fi

  # Cleanup session files
  rm -f "$SDIR/$SID.counters" "$SDIR/$SID.start" 2>/dev/null
fi

# ── v1.1.3 auto-push (async, fire-and-forget) ──────────────────────────
# v2.18.0 (2026-05-03): SUTRA_TELEMETRY=0 short-circuits BEFORE the OPTIN
# read; jq replaces python3 for the OPTIN probe (matches start.sh v2.13.0
# EDR-killed-python3 fix). If jq is missing here, skip silently — this hook
# is on the Stop event and must remain non-blocking. push.sh itself fails
# loudly on missing jq with an actionable install hint.
if [ "${SUTRA_TELEMETRY:-1}" != "0" ] \
   && [ -f "$PROJECT_ROOT/.claude/sutra-project.json" ] \
   && command -v jq >/dev/null 2>&1; then
  OPTIN=$(jq -r '.telemetry_optin // false' "$PROJECT_ROOT/.claude/sutra-project.json" 2>/dev/null)
  if [ "$OPTIN" = "true" ] && [ -x "$PLUGIN_ROOT/scripts/push.sh" ]; then
    CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$PROJECT_ROOT" \
      nohup bash "$PLUGIN_ROOT/scripts/push.sh" >> "$SUTRA_HOME/auto-push.log" 2>&1 &
    disown 2>/dev/null || true
  fi
fi

exit 0
