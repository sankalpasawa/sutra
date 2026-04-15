#!/bin/bash
# Sutra OS — Estimation Enforcement (portable, v1.9)
# SOFT: warns when editing deliverable files without a fresh estimation marker.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOOK_LOG="$REPO_ROOT/.claude/hooks/sutra/hook-log.jsonl"
FILE_PATH="${TOOL_INPUT_file_path:-}"
_start=$(date +%s)
mkdir -p "$(dirname "$HOOK_LOG")" 2>/dev/null

log_result() {
  local _status="$1"
  local _end=$(date +%s)
  local _ms=$(( (_end - _start) * 1000 ))
  echo "{\"ts\":$(date +%s),\"hook\":\"EstimationEnforcement\",\"event\":\"PreToolUse\",\"status\":\"$_status\",\"ms\":$_ms}" >> "$HOOK_LOG"
}

if [ -z "$FILE_PATH" ]; then
  log_result "PASS"
  exit 0
fi

case "$FILE_PATH" in
  "$REPO_ROOT/.claude/"*|*/os/*|*/context/*)
    log_result "PASS"
    exit 0
    ;;
esac
case "$(basename "$FILE_PATH")" in
  CLAUDE.md|TODO.md|REQUIREMENTS.md|DECISIONS.md|RETROSPECTIVE.md|DELIVERABLES.md|COMPANY.md)
    log_result "PASS"
    exit 0
    ;;
esac

MARKER="$REPO_ROOT/.claude/estimation-logged"
if [ -f "$MARKER" ]; then
  MARKER_TS=$(cat "$MARKER" 2>/dev/null | head -1 | tr -dc '0-9')
  if [ -n "$MARKER_TS" ]; then
    NOW=$(date +%s)
    AGE=$(( NOW - MARKER_TS ))
    if [ "$AGE" -lt 7200 ]; then
      log_result "PASS"
      exit 0
    fi
  fi
fi

echo ""
echo "WARNING: No estimation logged before editing deliverable file."
echo "  Output EFFORT/COST/CONFIDENCE/TIME, then: echo \$(date +%s) > .claude/estimation-logged"
echo ""
log_result "WARN"
exit 0
