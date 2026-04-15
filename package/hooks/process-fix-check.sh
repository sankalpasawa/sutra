#!/bin/bash
# Direction: D2 — Fix the Process, Not Just the Instance
# Event: PostToolUse on Edit|Write
# Enforcement: SOFT (reminder, exit 0 always)
# If recent commit message contains fix/bug/patch/hotfix, remind to fix the process too.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# Check the most recent commit message for fix-related words
LAST_MSG=$(cd "$REPO_ROOT" && git log -1 --oneline 2>/dev/null)

if echo "$LAST_MSG" | grep -iqE '\b(fix|bug|patch|hotfix)\b'; then
  echo "Warning: Per D2: Bug fix detected in recent commit: $LAST_MSG"
  echo "Did you also fix the PROCESS that allowed this bug?"
  echo "Root cause -> process improvement required."
fi

exit 0
