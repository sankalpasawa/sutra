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

exit 0
