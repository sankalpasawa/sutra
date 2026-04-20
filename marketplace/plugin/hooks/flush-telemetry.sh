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

# ── v1.1.3 auto-push (async, fire-and-forget) ──────────────────────────
# If telemetry_optin is true in the project, push the queue in the BACKGROUND.
# Stop hook stays light (no blocking wait). Queue preserved if push fails.
if [ -f "$PROJECT_ROOT/.claude/sutra-project.json" ]; then
  OPTIN=$(python3 -c "import json; print('true' if json.load(open('$PROJECT_ROOT/.claude/sutra-project.json')).get('telemetry_optin') else 'false')" 2>/dev/null)
  if [ "$OPTIN" = "true" ] && [ -x "$PLUGIN_ROOT/scripts/push.sh" ]; then
    CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$PROJECT_ROOT" \
      nohup bash "$PLUGIN_ROOT/scripts/push.sh" >> "$SUTRA_HOME/auto-push.log" 2>&1 &
    disown 2>/dev/null || true
  fi
fi

exit 0
