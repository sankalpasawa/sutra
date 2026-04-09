#!/usr/bin/env bash
# register-depth.sh
# Sutra OS — Depth Registration Script
#
# Purpose: Registers a depth assessment for the current task, creating the
#          marker file that depth-enforcement-hook.sh checks.
#
# Usage:
#   bash .claude/hooks/register-depth.sh "<task description>" <depth 1-5>
#
# Example:
#   bash .claude/hooks/register-depth.sh "Add user settings screen" 3
#   bash .claude/hooks/register-depth.sh "Fix login redirect bug" 2
#   bash .claude/hooks/register-depth.sh "Full security audit of RLS policies" 5

MARKER_FILE=".claude/depth-registered"
LOG_FILE=".claude/depth-log.jsonl"

# Validate arguments
if [ $# -lt 2 ]; then
    echo "Usage: bash .claude/hooks/register-depth.sh \"<task description>\" <depth 1-5>"
    echo ""
    echo "Example:"
    echo "  bash .claude/hooks/register-depth.sh \"Add user settings screen\" 3"
    exit 1
fi

TASK_DESCRIPTION="$1"
DEPTH="$2"

# Validate depth is 1-5
if ! [[ "$DEPTH" =~ ^[1-5]$ ]]; then
    echo "ERROR: Depth must be 1-5. Got: $DEPTH"
    echo ""
    echo "Depth levels:"
    echo "  1 = surface    (quick fix, trivial change)"
    echo "  2 = considered (standard task, some thought needed)"
    echo "  3 = thorough   (significant feature, edge cases matter)"
    echo "  4 = rigorous   (complex system, multi-file, needs verification)"
    echo "  5 = exhaustive (architecture, security, cross-cutting concerns)"
    exit 1
fi

# Ensure .claude directory exists
mkdir -p "$(dirname "$MARKER_FILE")"

# Write marker file
TIMESTAMP=$(date +%s)
echo "$TIMESTAMP $TASK_DESCRIPTION" > "$MARKER_FILE"

# Append to log (for audit trail)
DATE_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "{\"timestamp\":\"$DATE_ISO\",\"task\":\"$TASK_DESCRIPTION\",\"depth\":$DEPTH}" >> "$LOG_FILE"

# Depth label lookup
case $DEPTH in
    1) LABEL="surface" ;;
    2) LABEL="considered" ;;
    3) LABEL="thorough" ;;
    4) LABEL="rigorous" ;;
    5) LABEL="exhaustive" ;;
esac

echo "Depth registered: $DEPTH/5 ($LABEL)"
echo "Task: $TASK_DESCRIPTION"
echo "Valid for: 60 minutes"
echo ""
echo "You may now proceed with file edits."
