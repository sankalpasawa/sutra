#!/bin/bash
# Sutra OS — Coverage Gate (D31 enforcer)
# Checks: for each enabled method required at the task's depth, was it fired?
# Mode: SOFT (Phase 1) — prints warning on gaps, does NOT block. Exit 0 always.
#
# Usage: bash .claude/hooks/coverage-gate.sh [task_name]
#   If task_name omitted, checks the LATEST task in coverage-log.jsonl.
#
# Doctrine (D31):
#   - Sutra owns all authority. Clients execute mechanically.
#   - Skips are declarative (enabled_methods in SUTRA-CONFIG.md), never runtime.
#   - If a method feels wrong, clients file feedback — they do not skip.

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$PROJECT_DIR/os/SUTRA-CONFIG.md"
COVERAGE_LOG="$PROJECT_DIR/os/coverage-log.jsonl"
REGISTRY="$PROJECT_DIR/os/method-registry.jsonl"

[ -f "$CONFIG" ]        || exit 0
[ -f "$COVERAGE_LOG" ]  || exit 0
[ -f "$REGISTRY" ]      || exit 0

COVERAGE_SETTING=$(grep '^coverage:' "$CONFIG" | head -1 | awk '{print $2}')
[ "$COVERAGE_SETTING" = "off" ] && exit 0

TASK="${1:-}"
if [ -z "$TASK" ]; then
  TASK=$(tail -1 "$COVERAGE_LOG" 2>/dev/null | grep -oE '"task":"[^"]+"' | head -1 | sed 's/"task":"//;s/"$//')
fi
[ -z "$TASK" ] && exit 0

DEPTH=$(grep "\"task\":\"$TASK\"" "$COVERAGE_LOG" | tail -1 | grep -oE '"depth":[0-9]+' | head -1 | grep -oE '[0-9]+')
DEPTH="${DEPTH:-1}"

FIRED_TMP=$(mktemp)
grep "\"task\":\"$TASK\"" "$COVERAGE_LOG" | grep -oE '"method":"[^"]+"' | sed 's/"method":"//;s/"$//' | sort -u > "$FIRED_TMP"

# Parse enabled_methods block from SUTRA-CONFIG.md
ENABLED_TMP=$(mktemp)
awk '
  /^enabled_methods:/ { in_block = 1; next }
  in_block && /^[^[:space:]]/ { in_block = 0 }
  in_block && /:[[:space:]]*true[[:space:]]*$/ {
    gsub(/^[[:space:]]+/, "")
    sub(/:[[:space:]]*true.*$/, "")
    print
  }
' "$CONFIG" | sort -u > "$ENABLED_TMP"

REQUIRED_TMP=$(mktemp)
awk -v d="$DEPTH" '
  {
    id = ""; req = ""
    if (match($0, /"id":[[:space:]]*"[^"]+"/)) {
      id = substr($0, RSTART, RLENGTH)
      sub(/"id":[[:space:]]*"/, "", id); sub(/"$/, "", id)
    }
    if (match($0, /"required_at":[[:space:]]*\[[^]]*\]/)) {
      req = substr($0, RSTART, RLENGTH)
      if (req ~ ("[[,][[:space:]]*" d "[[:space:]]*[],]") && id != "") print id
    }
  }
' "$REGISTRY" | sort -u > "$REQUIRED_TMP"

EXPECTED_TMP=$(mktemp)
comm -12 "$ENABLED_TMP" "$REQUIRED_TMP" > "$EXPECTED_TMP"
EXPECTED_COUNT=$(wc -l < "$EXPECTED_TMP" | tr -d ' ')

MISSING_TMP=$(mktemp)
comm -23 "$EXPECTED_TMP" "$FIRED_TMP" > "$MISSING_TMP"
MISSING_COUNT=$(wc -l < "$MISSING_TMP" | tr -d ' ')
FIRED_OF_EXPECTED=$(comm -12 "$EXPECTED_TMP" "$FIRED_TMP" | wc -l | tr -d ' ')

if [ "$EXPECTED_COUNT" = "0" ]; then
  rm -f "$FIRED_TMP" "$ENABLED_TMP" "$REQUIRED_TMP" "$EXPECTED_TMP" "$MISSING_TMP"
  exit 0
fi

PCT=$(awk -v f="$FIRED_OF_EXPECTED" -v e="$EXPECTED_COUNT" 'BEGIN{printf "%.0f", f*100/e}')
if [ "$MISSING_COUNT" -gt 0 ]; then
  echo "[coverage-gate SOFT] task '$TASK' depth $DEPTH: $FIRED_OF_EXPECTED/$EXPECTED_COUNT enabled+required methods fired (${PCT}%)"
  echo "  Missing (enabled for you at depth $DEPTH per SUTRA-CONFIG.md):"
  sed 's/^/    - /' "$MISSING_TMP"
  echo "  D31: fire them, or file feedback at os/feedback-to-sutra/ for Sutra to reconsider enablement."
  echo "  Phase 1 SOFT — not blocking. HARD enforcement rolls out after 2 clean weeks."
else
  echo "[coverage-gate] task '$TASK' depth $DEPTH: all $EXPECTED_COUNT enabled+required methods fired (100%)"
fi

rm -f "$FIRED_TMP" "$ENABLED_TMP" "$REQUIRED_TMP" "$EXPECTED_TMP" "$MISSING_TMP"
exit 0
