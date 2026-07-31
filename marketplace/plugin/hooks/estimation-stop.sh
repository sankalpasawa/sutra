#!/bin/bash
# Sutra: estimation-stop hook.
# On Stop event, appends a session summary line to .claude/sutra-estimation.log.

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$PROJECT_ROOT/.claude/sutra-estimation.log"

# --- B2 marker-race P4: session-first marker reads --------------------
# Root cause: holding/research/2026-07-30-marker-race-root-cause.md (Phase 4,
# estimation-stop.sh:7). Session dir first via marker-lib; foreign-stamped
# globals ignored. Telemetry only -- NEVER blocks; legacy global path is the
# fallback when marker-lib is unavailable.
_B2_STDIN=""
if [ ! -t 0 ]; then _B2_STDIN=$(cat 2>/dev/null || true); fi
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  . "$_MARKER_LIB" 2>/dev/null || true
  if command -v sutra_sid_from_stdin >/dev/null 2>&1; then
    sutra_sid_from_stdin "$_B2_STDIN" 2>/dev/null || true
  fi
fi
_b2_marker_path() {
  if command -v sutra_marker_has >/dev/null 2>&1; then
    if sutra_marker_has "$1" 2>/dev/null; then sutra_marker_path "$1"; fi
    return 0
  fi
  [ -f "$PROJECT_ROOT/.claude/$1" ] && printf '%s' "$PROJECT_ROOT/.claude/$1"
  return 0
}
MARKER="$(_b2_marker_path depth-registered)"

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
