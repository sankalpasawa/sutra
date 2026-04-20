#!/bin/bash
# Sutra plugin v1 test runner.
# Runs unit + integration + smoke in order. Exits non-zero on any failure.
set -u
cd "$(dirname "$0")"

TOTAL=0; FAIL=0

_run() {
  local f="$1"
  TOTAL=$((TOTAL+1))
  echo "── $f ──────────────────────────────"
  bash "$f"
  if [ $? -ne 0 ]; then
    FAIL=$((FAIL+1))
    echo "  FAIL: $f"
  fi
  echo ""
}

echo "═══ Sutra plugin tests ═══"
for f in unit/test-*.sh; do [ -f "$f" ] && _run "$f"; done
for f in integration/test-*.sh; do [ -f "$f" ] && _run "$f"; done
[ -f smoke.sh ] && _run smoke.sh

PASS=$((TOTAL-FAIL))
echo "═══════════════════════════"
echo "  $PASS/$TOTAL test files passed"
[ "$FAIL" -gt 0 ] && echo "  FAILURES: $FAIL"
exit "$FAIL"
