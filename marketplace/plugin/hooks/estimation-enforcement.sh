#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Estimation Enforcement Hook — PreToolUse (Edit/Write)
# ═══════════════════════════════════════════════════════════════════════════════
# SOFT enforcement: warns when editing deliverable files without a fresh
# estimation marker. Becomes HARD after adoption data shows <80% compliance.
#
# Marker: .claude/estimation-logged (timestamp, must be <2 hours old)
# ═══════════════════════════════════════════════════════════════════════════════

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
HOOK_LOG="$REPO_ROOT/holding/hooks/hook-log.jsonl"
FILE_PATH="${TOOL_INPUT_file_path:-}"
_start=$(date +%s)

# Logging helper
log_result() {
  local _status="$1"
  local _end=$(date +%s)
  local _ms=$(( (_end - _start) * 1000 ))
  echo "{\"ts\":$(date +%s),\"hook\":\"EstimationEnforcement\",\"event\":\"PreToolUse\",\"status\":\"$_status\",\"ms\":$_ms}" >> "$HOOK_LOG"
}

# No file path — nothing to check
if [ -z "$FILE_PATH" ]; then
  log_result "PASS"
  exit 0
fi

# ─── Skip config/meta files ──────────────────────────────────────────────────
case "$FILE_PATH" in
  */.claude/*|*/os/*|*/context/*)
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

# ─── Check for fresh estimation marker ───────────────────────────────────────
MARKER="$REPO_ROOT/.claude/estimation-logged"

if [ -f "$MARKER" ]; then
  # Check freshness — marker must be less than 2 hours old
  MARKER_TS=$(cat "$MARKER" 2>/dev/null | head -1 | tr -dc '0-9')
  if [ -n "$MARKER_TS" ]; then
    NOW=$(date +%s)
    AGE=$(( NOW - MARKER_TS ))
    if [ "$AGE" -lt 7200 ]; then
      log_result "PASS"
      # Track compliance
      TRACKER="$(dirname "$0")/compliance-tracker.sh"
      [ -f "$TRACKER" ] && bash "$TRACKER" "estimation-enforcement" "pass" "$REPO_ROOT"
      RESIL="$(dirname "$0")/resilience.sh"
      [ -f "$RESIL" ] && bash "$RESIL" "estimation-enforcement" "pass" "$REPO_ROOT"
      exit 0
    fi
  fi
fi

# ─── No fresh marker — warn ──────────────────────────────────────────────────
echo ""
echo "WARNING: No estimation logged before editing deliverable file."
echo "  File: $FILE_PATH"
echo ""
echo "  The estimation engine requires pre-task estimates for calibration."
echo "  Before proceeding, please:"
echo ""
echo "  1. Output an estimation table:"
echo "     EFFORT: [time estimate]"
echo "     COST: ~\$X"
echo "     CONFIDENCE: [low/medium/high]"
echo "     TIME: [expected duration]"
echo ""
echo "  2. Create the marker:"
echo "     echo \$(date +%s) > .claude/estimation-logged"
echo ""
echo "  3. Then proceed with your edits."
echo ""

log_result "WARN"

# Track compliance + resilience
TRACKER="$(dirname "$0")/compliance-tracker.sh"
RESIL="$(dirname "$0")/resilience.sh"
[ -f "$TRACKER" ] && bash "$TRACKER" "estimation-enforcement" "warn" "$REPO_ROOT"
[ -f "$RESIL" ] && bash "$RESIL" "estimation-enforcement" "warn" "$REPO_ROOT"

# SOFT enforcement — warn only, never block
exit 0
