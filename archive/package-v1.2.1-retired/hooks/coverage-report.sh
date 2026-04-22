#!/bin/bash
# Sutra OS — Coverage Report Generator
# Reads os/coverage-log.jsonl, compares against expected methods per depth,
# outputs a gap report showing what was hit, missed, or skipped.
#
# Usage: bash .claude/hooks/coverage-report.sh [task_name]
#   If task_name is omitted, reports on ALL tasks in the log.
#   If task_name is provided, filters to that task only.

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
COVERAGE_LOG="$PROJECT_DIR/os/coverage-log.jsonl"
REGISTRY="$PROJECT_DIR/os/method-registry.jsonl"
TASK_FILTER="${1:-}"

if [ ! -f "$COVERAGE_LOG" ] || [ ! -s "$COVERAGE_LOG" ]; then
  echo "No coverage data yet. os/coverage-log.jsonl is empty."
  echo "Coverage logging happens during task execution."
  exit 0
fi

if [ ! -f "$REGISTRY" ]; then
  echo "ERROR: os/method-registry.jsonl not found."
  exit 1
fi

echo ""
echo "========================================================"
echo "  SUTRA COVERAGE REPORT"
echo "========================================================"
echo ""

# Get unique tasks
if [ -n "$TASK_FILTER" ]; then
  TASKS="$TASK_FILTER"
else
  TASKS=$(grep -o '"task":"[^"]*"' "$COVERAGE_LOG" | sort -u | sed 's/"task":"//;s/"//')
fi

TOTAL_TASKS=0
TOTAL_HIT=0
TOTAL_EXPECTED=0

while IFS= read -r TASK; do
  [ -z "$TASK" ] && continue
  TOTAL_TASKS=$((TOTAL_TASKS + 1))

  # Get depth for this task (from first log entry)
  DEPTH=$(grep "\"task\":\"$TASK\"" "$COVERAGE_LOG" | head -1 | grep -o '"depth":[0-9]' | grep -o '[0-9]')
  [ -z "$DEPTH" ] && DEPTH=1

  echo "  TASK: \"$TASK\""
  echo "  DEPTH: $DEPTH/5"
  echo "  --------------------------------------------------------"

  # Get expected methods for this depth
  EXPECTED_METHODS=""
  EXPECTED_COUNT=0
  TASK_HIT=0
  TASK_SKIPPED=0
  TASK_MISSED=0
  BONUS_COUNT=0
  while IFS= read -r line; do
    METHOD_ID=$(echo "$line" | grep -o '"id": *"[^"]*"' | sed 's/"id": *"//;s/"//')
    METHOD_NAME=$(echo "$line" | grep -o '"name": *"[^"]*"' | sed 's/"name": *"//;s/"//')
    REQUIRED_AT=$(echo "$line" | grep -o '"required_at": *\[[^]]*\]' | sed 's/"required_at": *//')
    IS_CONDITIONAL=$(echo "$line" | grep -o '"conditional": *true')

    # Check if this method is required at this depth
    if echo "$REQUIRED_AT" | grep -q "$DEPTH"; then
      EXPECTED_METHODS="$EXPECTED_METHODS $METHOD_ID"
      EXPECTED_COUNT=$((EXPECTED_COUNT + 1))

      # Check if it was logged
      if grep -q "\"task\":\"$TASK\".*\"method\":\"$METHOD_ID\"" "$COVERAGE_LOG"; then
        EVIDENCE=$(grep "\"task\":\"$TASK\".*\"method\":\"$METHOD_ID\"" "$COVERAGE_LOG" | tail -1 | grep -o '"evidence":"[^"]*"' | sed 's/"evidence":"//;s/"//')
        SKIPPED=$(grep "\"task\":\"$TASK\".*\"method\":\"$METHOD_ID\"" "$COVERAGE_LOG" | tail -1 | grep -o '"skipped_reason":"[^"]*"' | sed 's/"skipped_reason":"//;s/"//')
        TS=$(grep "\"task\":\"$TASK\".*\"method\":\"$METHOD_ID\"" "$COVERAGE_LOG" | tail -1 | grep -o '"ts":"[^"]*"' | sed 's/"ts":"//;s/"//' | sed 's/.*T//;s/Z//')

        if [ -n "$SKIPPED" ]; then
          printf "  [SKIP] %-25s %s  \"%s\"\n" "$METHOD_ID" "$TS" "$SKIPPED"
          TASK_SKIPPED=$((TASK_SKIPPED + 1))
        else
          printf "  [ OK ] %-25s %s  \"%s\"\n" "$METHOD_ID" "$TS" "$EVIDENCE"
          TASK_HIT=$((TASK_HIT + 1))
          TOTAL_HIT=$((TOTAL_HIT + 1))
        fi
      else
        if [ -n "$IS_CONDITIONAL" ]; then
          printf "  [COND] %-25s        (conditional -- may not apply)\n" "$METHOD_ID"
        else
          printf "  [MISS] %-25s        << NOT FIRED\n" "$METHOD_ID"
          TASK_MISSED=$((TASK_MISSED + 1))
        fi
      fi
    else
      # Check if this method was logged anyway (bonus — not required at this depth)
      if grep -q "\"task\":\"$TASK\".*\"method\":\"$METHOD_ID\"" "$COVERAGE_LOG"; then
        BONUS_COUNT=$((BONUS_COUNT + 1))
      fi
    fi
  done < "$REGISTRY"

  TOTAL_EXPECTED=$((TOTAL_EXPECTED + EXPECTED_COUNT))

  # Coverage is ONLY hits against expected checklist — bonus methods don't inflate
  if [ "$EXPECTED_COUNT" -gt 0 ]; then
    PCT=$((TASK_HIT * 100 / EXPECTED_COUNT))
  else
    PCT=0
  fi

  echo ""
  echo "  COVERAGE: $TASK_HIT/$EXPECTED_COUNT ($PCT%)"
  if [ "$BONUS_COUNT" -gt 0 ]; then
    echo "  BONUS: +$BONUS_COUNT extra methods logged (not required at depth $DEPTH)"
  fi

  # Severity assessment
  if [ "$PCT" -ge 90 ]; then
    echo "  STATUS: EXCELLENT"
  elif [ "$PCT" -ge 70 ]; then
    echo "  STATUS: GOOD (some gaps)"
  elif [ "$PCT" -ge 50 ]; then
    echo "  STATUS: CONCERN (significant gaps)"
  else
    echo "  STATUS: CRITICAL (process mostly skipped)"
  fi
  echo ""
  echo ""

done <<< "$TASKS"

# Session summary
echo "========================================================"
echo "  SESSION SUMMARY"
echo "========================================================"
echo "  Tasks tracked:  $TOTAL_TASKS"
if [ "$TOTAL_EXPECTED" -gt 0 ]; then
  OVERALL_PCT=$((TOTAL_HIT * 100 / TOTAL_EXPECTED))
  echo "  Overall coverage: $TOTAL_HIT/$TOTAL_EXPECTED ($OVERALL_PCT%)"
else
  echo "  Overall coverage: no data"
fi
echo ""

# Find most-missed methods across all tasks
echo "  MOST MISSED METHODS (across all tasks):"
FOUND_MISSED=0
while IFS= read -r line; do
  METHOD_ID=$(echo "$line" | grep -o '"id": *"[^"]*"' | sed 's/"id": *"//;s/"//')
  [ -z "$METHOD_ID" ] && continue
  FIRE_COUNT=$(grep -c "\"method\":\"$METHOD_ID\"" "$COVERAGE_LOG" 2>/dev/null)
  FIRE_COUNT="${FIRE_COUNT:-0}"
  FIRE_COUNT=$(echo "$FIRE_COUNT" | tr -d '[:space:]')

  if [ "$FIRE_COUNT" = "0" ] && [ "$TOTAL_TASKS" -gt 0 ]; then
    MIN_DEPTH=$(echo "$line" | grep -o '"min_depth": *[0-9]' | grep -o '[0-9]')
    MIN_DEPTH="${MIN_DEPTH:-99}"
    HAS_QUALIFYING_TASK=$(grep -c "\"depth\":[$MIN_DEPTH-5]" "$COVERAGE_LOG" 2>/dev/null)
    HAS_QUALIFYING_TASK=$(echo "$HAS_QUALIFYING_TASK" | tr -d '[:space:]')
    if [ "${HAS_QUALIFYING_TASK:-0}" -gt 0 ] 2>/dev/null; then
      printf "    %-25s never fired (required at depth %s+)\n" "$METHOD_ID" "$MIN_DEPTH"
      FOUND_MISSED=1
    fi
  fi
done < "$REGISTRY"
if [ "$FOUND_MISSED" = "0" ]; then
  echo "    (none -- all expected methods fired at least once)"
fi

echo ""
echo "========================================================"
