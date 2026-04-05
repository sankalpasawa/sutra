#!/bin/bash
# Sutra Submodule Boundary Enforcement
# Blocks Edit/Write/Bash to files outside this repo's root directory.
# This enforces physical isolation — a Maze session cannot touch DayFlow, Sutra, or holding.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

REPO_NAME="$(basename "$REPO_ROOT")"
FILE_PATH="$TOOL_INPUT_file_path"

# For Bash tool, check the command for paths outside repo
if [ -n "$TOOL_INPUT_command" ]; then
  CMD="$TOOL_INPUT_command"
  # Block commands that explicitly reference parent directories to escape
  if echo "$CMD" | grep -qE '\.\./|/Users/.*/Claude/asawa-holding/(holding|sutra|dayflow|maze|ppr)/' ; then
    # Allow if it's referencing THIS repo's own path
    if ! echo "$CMD" | grep -q "/Claude/asawa-holding/${REPO_NAME}/"; then
      echo "BLOCKED: Cannot access files outside ${REPO_NAME}/."
      echo "You are in an isolated ${REPO_NAME} session."
      echo "To access other repos, start a session in asawa-holding/ as CEO of Asawa."
      exit 2
    fi
  fi
  exit 0
fi

# For Edit/Write, check file_path
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Resolve to absolute path
ABS_PATH="$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd)/$(basename "$FILE_PATH")" 2>/dev/null

# Check if path is within repo root
if [ -n "$ABS_PATH" ]; then
  case "$ABS_PATH" in
    "$REPO_ROOT"*) exit 0 ;;  # Inside repo — allowed
    *)
      echo "BLOCKED: Cannot edit files outside ${REPO_NAME}/."
      echo "  Attempted: $FILE_PATH"
      echo "  Allowed: anything under $REPO_ROOT/"
      echo "To access other repos, start a session in asawa-holding/ as CEO of Asawa."
      exit 2
      ;;
  esac
fi

exit 0
