#!/bin/bash
# Direction: D12 — 70/20/10 Products First
# Event: Stop
# Enforcement: AUDIT (informational, exit 0 always)
# Count files edited during session by category and report the split.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# Get all modified/added files in the working tree vs HEAD
CHANGED_FILES=$(cd "$REPO_ROOT" && git diff --name-only HEAD 2>/dev/null; cd "$REPO_ROOT" && git diff --name-only --cached 2>/dev/null)

if [ -z "$CHANGED_FILES" ]; then
  exit 0
fi

# Count by category
PRODUCT_COUNT=$(echo "$CHANGED_FILES" | grep -cE '^(dayflow|maze|ppr|jarvis)/' 2>/dev/null || echo 0)
OS_COUNT=$(echo "$CHANGED_FILES" | grep -cE '^(sutra|holding)/' 2>/dev/null || echo 0)
OTHER_COUNT=$(echo "$CHANGED_FILES" | grep -vcE '^(dayflow|maze|ppr|jarvis|sutra|holding)/' 2>/dev/null || echo 0)
TOTAL=$((PRODUCT_COUNT + OS_COUNT + OTHER_COUNT))

if [ "$TOTAL" -gt 0 ]; then
  echo "Session allocation: $PRODUCT_COUNT product files, $OS_COUNT OS files, $OTHER_COUNT other. Target: 70/20/10."
fi

exit 0
