#!/bin/bash
# Phase 6 onboarding self-check — PostToolUse on Write
# Advisory only (exit 0 always). Catches placeholders in company os/ dirs.

FILE_PATH="$TOOL_INPUT_file_path"
[ -z "$FILE_PATH" ] && exit 0

# Only check files inside a company's os/ directory
COMPANY=$(echo "$FILE_PATH" | grep -oE '(dayflow|maze|ppr|jarvis|paisa)/os/' | head -1)
[ -z "$COMPANY" ] && exit 0
COMPANY_NAME=$(echo "$COMPANY" | cut -d/ -f1)

# Patterns to flag
PATTERNS='\{placeholder\}|\{company|\{COMPANY|ExampleCo|TODO:|FIXME:|__REPLACE__|<<.*>>'
# Cross-company name leak: flag "DayFlow" in non-dayflow repos
if [ "$COMPANY_NAME" != "dayflow" ]; then
  PATTERNS="$PATTERNS|DayFlow"
fi

MATCHES=$(grep -noE "$PATTERNS" "$FILE_PATH" 2>/dev/null)
if [ -n "$MATCHES" ]; then
  echo ""
  echo "ONBOARDING QA: Found placeholder in $FILE_PATH:"
  echo "$MATCHES" | head -5
  echo "Fix before proceeding."
  echo ""
fi
exit 0
