#!/bin/bash
# Sutra: estimation-stop hook.
# On Stop event, appends a session summary line to .claude/sutra-estimation.log.

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$PROJECT_ROOT/.claude/sutra-estimation.log"
MARKER="$PROJECT_ROOT/.claude/depth-registered"

mkdir -p "$(dirname "$LOG")"

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  if [ -f "$MARKER" ]; then
    echo "depth_marker: $(cat "$MARKER")"
  else
    echo "depth_marker: (absent)"
  fi
} >> "$LOG"

exit 0
