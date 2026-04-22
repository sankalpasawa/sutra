#!/bin/bash
# Sutra OS — Session Logger Hook (Enhanced with Context Monitoring)
# Fires on every Edit/Write to track activity + governance overhead
# Logs to .claude/logs/activity.jsonl
# Context monitoring: tracks governance vs work file ratio

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
LOG_DIR="$PROJECT_DIR/.claude/logs"
LOG_FILE="$LOG_DIR/activity.jsonl"
STATS_FILE="$PROJECT_DIR/.claude/session-stats"

mkdir -p "$LOG_DIR"

TOOL_NAME="${TOOL_NAME:-unknown}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FILE_PATH="${TOOL_INPUT_file_path:-none}"

# Log the event
echo "{\"ts\":\"$TIMESTAMP\",\"tool\":\"$TOOL_NAME\",\"file\":\"$FILE_PATH\",\"event\":\"tool_use\"}" >> "$LOG_FILE"

# Context monitoring — categorize governance vs work files
if [ "$FILE_PATH" != "none" ]; then
  # Initialize stats if needed
  if [ ! -f "$STATS_FILE" ]; then
    cat > "$STATS_FILE" << STATS
governance_reads=0
work_reads=0
session_start=$TIMESTAMP
STATS
  fi

  GOV_COUNT=$(sed -n 's/^governance_reads=//p' "$STATS_FILE" 2>/dev/null)
  WORK_COUNT=$(sed -n 's/^work_reads=//p' "$STATS_FILE" 2>/dev/null)
  GOV_COUNT="${GOV_COUNT:-0}"
  WORK_COUNT="${WORK_COUNT:-0}"

  case "$FILE_PATH" in
    *CLAUDE.md|*/os/*|*SUTRA-CONFIG*|*OPERATING-SYSTEM*|*ADAPTIVE-PROTOCOL*|*ESTIMATION-ENGINE*)
      GOV_COUNT=$((GOV_COUNT + 1))
      ;;
    *)
      WORK_COUNT=$((WORK_COUNT + 1))
      ;;
  esac

  sed -i '' "s/^governance_reads=.*/governance_reads=$GOV_COUNT/" "$STATS_FILE" 2>/dev/null
  sed -i '' "s/^work_reads=.*/work_reads=$WORK_COUNT/" "$STATS_FILE" 2>/dev/null

  TOTAL=$((GOV_COUNT + WORK_COUNT))
  if [ "$TOTAL" -gt 0 ] && [ "$GOV_COUNT" -gt 20 ]; then
    GOV_PCT=$((GOV_COUNT * 100 / TOTAL))
    if [ "$GOV_PCT" -gt 40 ]; then
      echo "CONTEXT MONITOR: High governance overhead — $GOV_COUNT governance reads ($GOV_PCT%) vs $WORK_COUNT work reads"
    fi
  fi
fi

exit 0
