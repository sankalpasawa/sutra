#!/bin/bash
# Sutra OS — Coverage Logger
# Logs a method fire to os/coverage-log.jsonl
#
# Usage: bash .claude/hooks/log-coverage.sh "<task>" <depth> "<method_id>" "<evidence>"
#
# D31 (2026-04-20): Runtime skip path REMOVED. Clients cannot decide to skip.
# If a method feels wrong for a task, file feedback at os/feedback-to-sutra/
# and Sutra will update enabled_methods in SUTRA-CONFIG.md via PROTO-018.

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$PROJECT_DIR/os/SUTRA-CONFIG.md"
COVERAGE_LOG="$PROJECT_DIR/os/coverage-log.jsonl"

# Check toggle — exit silently if coverage is off
if [ -f "$CONFIG" ]; then
  COVERAGE_SETTING=$(grep '^coverage:' "$CONFIG" | head -1 | awk '{print $2}')
  if [ "$COVERAGE_SETTING" = "off" ]; then
    exit 0
  fi
fi

TASK="${1:-unspecified}"
DEPTH="${2:-0}"
METHOD="${3:-UNKNOWN}"
EVIDENCE="${4:-no evidence provided}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# D31 guard: if a 5th argument is passed, reject with a pointer to the feedback path.
if [ -n "${5:-}" ]; then
  echo "[log-coverage] D31: client-side skip_reason path removed." >&2
  echo "  Method '$METHOD' cannot be skipped at runtime. Options:" >&2
  echo "  1. Fire the method (do the step, then log it with evidence)." >&2
  echo "  2. If the method genuinely shouldn't apply here, file feedback:" >&2
  echo "       echo '# Skip request: $METHOD on $TASK' > os/feedback-to-sutra/\$(date -u +%Y-%m-%d)-skip-$METHOD.md" >&2
  echo "     Sutra triages and may update enabled_methods in SUTRA-CONFIG.md." >&2
  exit 2
fi

# Ensure log exists
mkdir -p "$(dirname "$COVERAGE_LOG")"
touch "$COVERAGE_LOG"

# Build JSON line
echo "{\"task\":\"$TASK\",\"depth\":$DEPTH,\"method\":\"$METHOD\",\"ts\":\"$TIMESTAMP\",\"evidence\":\"$EVIDENCE\"}" >> "$COVERAGE_LOG"
echo "COVERAGE: $METHOD logged"
