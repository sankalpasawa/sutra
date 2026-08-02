#!/bin/bash
# Sutra OS — Skill Feedback Logger
# Called by agent when a skill/pattern was notably effective or ineffective.
# Usage: bash log-skill-feedback.sh <skill_name> <outcome: effective|ineffective> <note> [project_dir]
# Stop-hook safe: no-args → silent exit 0 (hook registration produces no-arg calls).
[ $# -eq 0 ] && exit 0
SKILL="${1:?Usage: log-skill-feedback.sh <skill> <effective|ineffective> <note> [project_dir]}"
OUTCOME="${2:?Usage: log-skill-feedback.sh <skill> <effective|ineffective> <note> [project_dir]}"
NOTE="${3:-}"
PROJECT_DIR="${4:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}}"
LOG_DIR="$PROJECT_DIR/os/engines"
LOG_FILE="$LOG_DIR/skill-feedback.jsonl"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# --- B2 marker-race P4: session-first marker reads --------------------
# Root cause: holding/research/2026-07-30-marker-race-root-cause.md (Phase 4,
# log-skill-feedback.sh:16). CLI-invoked from model Bash, so the sid comes
# from env CLAUDE_CODE_SESSION_ID (no hook stdin here). Session dir first via
# marker-lib; foreign-stamped globals ignored. Telemetry only -- NEVER
# blocks; legacy global path is the fallback when marker-lib is unavailable.
# marker-lib roots on CLAUDE_PROJECT_DIR; this CLI takes the project dir as
# arg 4, so align the lib's root with the arg when the env var is unset.
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PROJECT_DIR}"
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  . "$_MARKER_LIB" 2>/dev/null || true
fi
_b2_marker_path() {
  if command -v sutra_marker_has >/dev/null 2>&1; then
    if sutra_marker_has "$1" 2>/dev/null; then sutra_marker_path "$1"; fi
    return 0
  fi
  [ -f "$PROJECT_DIR/.claude/$1" ] && printf '%s' "$PROJECT_DIR/.claude/$1"
  return 0
}
TASK_DESC="unknown"
DEPTH_FILE="$(_b2_marker_path depth-registered)"
if [ -n "$DEPTH_FILE" ] && [ -f "$DEPTH_FILE" ]; then
  TASK_DESC=$(head -1 "$DEPTH_FILE" | cut -d' ' -f3-)
fi
NOTE_ESC=$(echo "$NOTE" | sed 's/"/\\"/g')
TASK_ESC=$(echo "$TASK_DESC" | sed 's/"/\\"/g')
echo "{\"ts\":\"$TS\",\"task\":\"$TASK_ESC\",\"skill\":\"$SKILL\",\"outcome\":\"$OUTCOME\",\"note\":\"$NOTE_ESC\"}" >> "$LOG_FILE"
echo "Skill feedback logged: $SKILL=$OUTCOME"
