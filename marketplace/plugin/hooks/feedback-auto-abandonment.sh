#!/bin/bash
# sutra/marketplace/plugin/hooks/feedback-auto-abandonment.sh
# Sutra Privacy v2.0 — abandonment-signal auto-capture (Stop).

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || exit 0
source "$LIB" 2>/dev/null || exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
[ -z "$REPO_ROOT" ] && exit 0

# --- B2 marker-race P4: session-first marker reads --------------------
# Root cause: holding/research/2026-07-30-marker-race-root-cause.md (Phase 4,
# feedback-auto-abandonment.sh:13). Session dir first via marker-lib;
# foreign-stamped globals ignored. Telemetry only -- NEVER blocks; legacy
# global path is the fallback when marker-lib is unavailable.
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
  [ -f "$REPO_ROOT/.claude/$1" ] && printf '%s' "$REPO_ROOT/.claude/$1"
  return 0
}

DEPTH_MARKER="$(_b2_marker_path depth-registered)"
[ -f "$DEPTH_MARKER" ] || exit 0

NOW=$(date +%s)
MTIME=$(stat -f %m "$DEPTH_MARKER" 2>/dev/null || stat -c %Y "$DEPTH_MARKER" 2>/dev/null)
[ -z "$MTIME" ] && exit 0
AGE=$((NOW - MTIME))
[ "$AGE" -gt 3600 ] && exit 0

SLUG=$(grep -oE 'TASK=[a-zA-Z0-9_-]+' "$DEPTH_MARKER" 2>/dev/null | head -1 | cut -d= -f2)
[ -z "$SLUG" ] && SLUG="unknown"

signal_write abandonment "$SLUG" 1 2>/dev/null || true
exit 0
