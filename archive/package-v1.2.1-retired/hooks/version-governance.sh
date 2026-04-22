#!/bin/bash
# Direction: D24 — OS Deploys Downstream by Judgment
# Event: PreToolUse on Edit|Write
# Enforcement: SOFT (reminder, exit 0 always)
# If editing a company's os/ directory, remind about version governance.

FILE_PATH="$TOOL_INPUT_file_path"

# No file path → not relevant
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Check if editing a company's os/ directory
case "$FILE_PATH" in
  */dayflow/os/*|*/maze/os/*|*/ppr/os/*|*/jarvis/os/*)
    COMPANY=$(echo "$FILE_PATH" | grep -oE '(dayflow|maze|ppr|jarvis)' | head -1)
    echo "Warning: Per D24: Editing $COMPANY OS files: $FILE_PATH"
    echo "Is this a sanctioned update? PULL (company CEO decides) or PUSH (Asawa override)?"
    ;;
esac

exit 0
