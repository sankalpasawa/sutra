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
TASK_DESC="unknown"
DEPTH_FILE="$PROJECT_DIR/.claude/depth-registered"
if [ -f "$DEPTH_FILE" ]; then
  TASK_DESC=$(head -1 "$DEPTH_FILE" | cut -d' ' -f3-)
fi
NOTE_ESC=$(echo "$NOTE" | sed 's/"/\\"/g')
TASK_ESC=$(echo "$TASK_DESC" | sed 's/"/\\"/g')
echo "{\"ts\":\"$TS\",\"task\":\"$TASK_ESC\",\"skill\":\"$SKILL\",\"outcome\":\"$OUTCOME\",\"note\":\"$NOTE_ESC\"}" >> "$LOG_FILE"
echo "Skill feedback logged: $SKILL=$OUTCOME"
