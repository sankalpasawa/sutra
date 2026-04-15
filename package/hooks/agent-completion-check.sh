#!/bin/bash
# PROTO-002: Wait for Parallel Completion
# Event: PostToolUse on Bash|Edit|Write
# Enforcement: SOFT (reminder, exit 0 always)
#
# Heuristic: check if any agent output files in /tmp were modified
# in the last 60 seconds, suggesting parallel agents are still running.
# Also checks for common Claude agent task patterns.

# Fast-path: skip expensive /tmp scan if no agent markers exist
# This is the single biggest latency win — avoids find/stat on every tool call
if ! ls /tmp/claude-agent-* /tmp/claude-tasks 2>/dev/null | head -1 | grep -q .; then
  exit 0
fi

# Look for recently-modified agent output files in /tmp
# Claude Code agent tasks often write to /tmp with .output or task-related names
RECENT_AGENT_FILES=()

# Check /tmp for agent output files modified in last 60 seconds
if [ -d "/tmp" ]; then
  while IFS= read -r -d '' file; do
    RECENT_AGENT_FILES+=("$file")
  done < <(find /tmp -maxdepth 2 -name "*.output" -o -name "*agent*" -o -name "*task-output*" 2>/dev/null | while read f; do
    if [ -f "$f" ]; then
      # Check if modified in last 60 seconds
      MOD_TIME=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null)
      NOW=$(date +%s)
      if [ -n "$MOD_TIME" ] && [ $((NOW - MOD_TIME)) -lt 60 ]; then
        printf '%s\0' "$f"
      fi
    fi
  done)
fi

# Also check for background jobs from this shell session
BG_JOBS=$(jobs -r 2>/dev/null | wc -l | tr -d ' ')

# Check for Claude-specific task directories
CLAUDE_TASK_DIR="/tmp/claude-tasks"
ACTIVE_TASKS=0
if [ -d "$CLAUDE_TASK_DIR" ]; then
  for task_dir in "$CLAUDE_TASK_DIR"/*/; do
    if [ -d "$task_dir" ]; then
      # Check if task has a .running marker or was recently modified
      if [ -f "${task_dir}.running" ]; then
        ACTIVE_TASKS=$((ACTIVE_TASKS + 1))
      fi
    fi
  done
fi

# Report if anything looks like pending parallel work
TOTAL_SIGNALS=$(( ${#RECENT_AGENT_FILES[@]} + BG_JOBS + ACTIVE_TASKS ))

if [ "$TOTAL_SIGNALS" -gt 0 ]; then
  echo ""
  echo "⚠ PROTO-002: Parallel agents may still be running"

  if [ ${#RECENT_AGENT_FILES[@]} -gt 0 ]; then
    echo "  Recently modified agent output files (< 60s):"
    for f in "${RECENT_AGENT_FILES[@]}"; do
      echo "    - $f"
    done
  fi

  if [ "$BG_JOBS" -gt 0 ]; then
    echo "  Background jobs running: $BG_JOBS"
  fi

  if [ "$ACTIVE_TASKS" -gt 0 ]; then
    echo "  Active Claude tasks: $ACTIVE_TASKS"
  fi

  echo ""
  echo "  Per PROTO-002 (Wait for Parallel Completion):"
  echo "    - Do NOT write synthesis/output until ALL agents complete."
  echo "    - Read ALL agent outputs before proceeding."
  echo "    - Do NOT substitute your own work for pending agent work."
  echo ""
fi

exit 0
