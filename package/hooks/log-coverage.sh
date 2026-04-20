#!/bin/bash
# Sutra OS — Coverage Logger
# Logs a method fire to os/coverage-log.jsonl
#
# Usage: bash .claude/hooks/log-coverage.sh "<task>" <depth> "<method_id>" "<evidence>"
# To skip: bash .claude/hooks/log-coverage.sh "<task>" <depth> "<method_id>" "" "<reason>"

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$PROJECT_DIR/os/SUTRA-CONFIG.md"
COVERAGE_LOG="$PROJECT_DIR/os/coverage-log.jsonl"

# Check toggle — exit silently if coverage is off
if [ -f "$CONFIG" ]; then
  COVERAGE_SETTING=$(grep '^coverage:' "$CONFIG" | awk '{print $2}')
  if [ "$COVERAGE_SETTING" = "off" ]; then
    exit 0
  fi
fi

TASK="${1:-unspecified}"
DEPTH="${2:-0}"
METHOD="${3:-UNKNOWN}"
EVIDENCE="${4:-no evidence provided}"
SKIPPED_REASON="${5:-}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Ensure log exists
mkdir -p "$(dirname "$COVERAGE_LOG")"
touch "$COVERAGE_LOG"

# Build JSON line
if [ -n "$SKIPPED_REASON" ]; then
  echo "{\"task\":\"$TASK\",\"depth\":$DEPTH,\"method\":\"$METHOD\",\"ts\":\"$TIMESTAMP\",\"skipped_reason\":\"$SKIPPED_REASON\"}" >> "$COVERAGE_LOG"
  echo "COVERAGE: $METHOD skipped ($SKIPPED_REASON)"
else
  echo "{\"task\":\"$TASK\",\"depth\":$DEPTH,\"method\":\"$METHOD\",\"ts\":\"$TIMESTAMP\",\"evidence\":\"$EVIDENCE\"}" >> "$COVERAGE_LOG"
  echo "COVERAGE: $METHOD logged"
fi
