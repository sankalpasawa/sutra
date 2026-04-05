#!/bin/bash
# Sutra Cascade Warning — fires when editing engine files
# Warns the agent that downstream companies need updating
# PreToolUse hook on Edit|Write for sutra/ files

FILE_PATH="$TOOL_INPUT_file_path"

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Check if this file is copied to companies
BASENAME=$(basename "$FILE_PATH")
DIRNAME=$(dirname "$FILE_PATH")

# Engine files are cascaded
if echo "$FILE_PATH" | grep -q "d-engines/"; then
  COMPANIES=""
  for co in maze dayflow jarvis ppr; do
    if [ -f "../$co/os/engines/$BASENAME" ]; then
      COMPANIES="$COMPANIES $co"
    fi
  done
  
  if [ -n "$COMPANIES" ]; then
    echo ""
    echo "CASCADE WARNING: $BASENAME is deployed to:$COMPANIES"
    echo "After editing, run: cp sutra/layer2-operating-system/d-engines/$BASENAME {company}/os/engines/"
    echo "Then commit to each company repo."
    echo ""
  fi
fi

# Always allow the edit — this is advisory, not blocking
exit 0
