#!/usr/bin/env bash
# depth-enforcement-hook.sh
# Sutra OS — Depth Block Enforcement Hook
#
# Purpose: Ensures a depth assessment block has been registered before any
#          Edit or Write operation. Prevents tasks from executing without
#          the mandatory depth assessment.
#
# Installation: Add to .claude/settings.json as a PreToolUse hook for Edit/Write:
#   {
#     "hooks": {
#       "PreToolUse": [
#         {
#           "matcher": "Edit|Write",
#           "hook": "bash .claude/hooks/depth-enforcement-hook.sh"
#         }
#       ]
#     }
#   }
#
# Marker file: .claude/depth-registered
#   Format: <unix_timestamp> <task_description>
#   Created by: register-depth.sh

MARKER_FILE=".claude/depth-registered"
MAX_AGE_MINUTES=60

# Check if marker file exists
if [ ! -f "$MARKER_FILE" ]; then
    echo >&2 "BLOCKED: No depth assessment registered for current task."
    echo >&2 ""
    echo >&2 "Before editing files, you must register a depth assessment:"
    echo >&2 "  bash .claude/hooks/register-depth.sh \"<task description>\" <depth 1-5>"
    echo >&2 ""
    echo >&2 "Example:"
    echo >&2 "  bash .claude/hooks/register-depth.sh \"Add user settings screen\" 3"
    echo >&2 ""
    echo >&2 "This is required by Sutra OS. Every task needs a depth assessment"
    echo >&2 "before any file modifications begin."
    exit 1
fi

# Read marker file
REGISTERED_TIMESTAMP=$(head -1 "$MARKER_FILE" | cut -d' ' -f1)
REGISTERED_TASK=$(head -1 "$MARKER_FILE" | cut -d' ' -f2-)

# Check if marker is stale (older than MAX_AGE_MINUTES)
CURRENT_TIMESTAMP=$(date +%s)
AGE_SECONDS=$((CURRENT_TIMESTAMP - REGISTERED_TIMESTAMP))
MAX_AGE_SECONDS=$((MAX_AGE_MINUTES * 60))

if [ "$AGE_SECONDS" -gt "$MAX_AGE_SECONDS" ]; then
    echo "BLOCKED: Depth assessment is stale (registered ${AGE_SECONDS}s ago, max ${MAX_AGE_SECONDS}s)."
    echo ""
    echo "Registered task: $REGISTERED_TASK"
    echo ""
    echo "Re-register the depth assessment for the current task:"
    echo "  bash .claude/hooks/register-depth.sh \"<task description>\" <depth 1-5>"
    exit 1
fi

# Marker exists and is fresh — allow the operation
exit 0
