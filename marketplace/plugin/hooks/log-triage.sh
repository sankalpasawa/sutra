#!/bin/bash
# Sutra OS — Triage Logger
# Called by agent after task completion to log depth accuracy.
# Usage: bash log-triage.sh <depth_selected> <depth_correct> <class> [task_description] [project_dir]
# Stop-hook safe: no-args → silent exit 0 (hook registration produces no-arg calls).
[ $# -eq 0 ] && exit 0
DEPTH_SELECTED="${1:?Usage: log-triage.sh <depth_selected> <depth_correct> <class> [task] [project_dir]}"
DEPTH_CORRECT="${2:?Usage: log-triage.sh <depth_selected> <depth_correct> <class> [task] [project_dir]}"
CLASS="${3:?Usage: log-triage.sh <depth_selected> <depth_correct> <class> [task] [project_dir]}"
TASK_DESC="${4:-unspecified}"
PROJECT_DIR="${5:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}}"
LOG_DIR="$PROJECT_DIR/os/engines"
LOG_FILE="$LOG_DIR/triage-log.jsonl"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TASK_ESC=$(echo "$TASK_DESC" | sed 's/"/\\"/g')
echo "{\"ts\":\"$TS\",\"task\":\"$TASK_ESC\",\"depth_selected\":$DEPTH_SELECTED,\"depth_correct\":$DEPTH_CORRECT,\"class\":\"$CLASS\"}" >> "$LOG_FILE"
echo "Triage logged: depth=$DEPTH_SELECTED, correct=$DEPTH_CORRECT, class=$CLASS"
