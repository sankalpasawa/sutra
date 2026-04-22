#!/bin/bash
# Sutra outcome test runner.
# Runs every 0N-*.sh script in this directory, aggregates pass/fail,
# exits non-zero if any test file fails.

set -u
cd "$(dirname "$0")"

TOTAL=0
FAILED=0
FAILED_TESTS=""
START=$(date +%s)

echo "═══════════════════════════════════════════════════════════════"
echo "  Sutra outcome tests — starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Source:  ${SUTRA_PACKAGE_DIR:-npx github:sankalpasawa/sutra-os}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Run each numbered test file.
for test_file in [0-9][0-9]-*.sh; do
  [ -f "$test_file" ] || continue
  TOTAL=$((TOTAL + 1))
  echo "── $test_file ─────────────────────────────────────────────────"
  bash "$test_file"
  if [ "$?" -ne 0 ]; then
    FAILED=$((FAILED + 1))
    FAILED_TESTS="$FAILED_TESTS $test_file"
  fi
  echo ""
done

END=$(date +%s)
DURATION=$((END - START))

PASSED=$((TOTAL - FAILED))

echo "═══════════════════════════════════════════════════════════════"
if [ "$FAILED" -eq 0 ]; then
  echo "  RESULT: $PASSED/$TOTAL files passed · ${DURATION}s"
else
  echo "  RESULT: $PASSED/$TOTAL files passed · ${DURATION}s · FAILED:$FAILED_TESTS"
fi
echo "═══════════════════════════════════════════════════════════════"

exit "$FAILED"
