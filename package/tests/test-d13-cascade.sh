#!/usr/bin/env bash
# Regression test for D13 — Cascade Downstream Immediately.
# Verifies cascade-check.sh warns when L0-L2 files are edited.

set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }

echo "=== D13 — holding/ edit triggers cascade warning ==="
OUT=$(TOOL_INPUT_file_path="$REPO_ROOT/holding/PRINCIPLES.md" bash holding/hooks/cascade-check.sh 2>&1)
if echo "$OUT" | grep -qi "downstream"; then
  pass "cascade warning printed for holding/ edit"
else
  fail "expected cascade warning; got: $OUT"
fi

echo ""
echo "=== D13 — sutra/layer2-operating-system/ edit triggers cascade warning ==="
OUT=$(TOOL_INPUT_file_path="$REPO_ROOT/sutra/layer2-operating-system/protocols/PROTO-001.md" bash holding/hooks/cascade-check.sh 2>&1)
if echo "$OUT" | grep -qi "downstream"; then
  pass "cascade warning printed for Sutra L2 edit"
else
  fail "expected cascade warning; got: $OUT"
fi

echo ""
echo "=== D13 — non-governance file does NOT trigger warning ==="
OUT=$(TOOL_INPUT_file_path="$REPO_ROOT/dayflow/mobile/src/app.tsx" bash holding/hooks/cascade-check.sh 2>&1)
if [ -z "$OUT" ]; then
  pass "no warning for product file"
else
  fail "expected silence; got: $OUT"
fi

echo ""
if [ "$FAIL" = "0" ]; then
  echo "ALL D13 REGRESSION TESTS PASSED"
  exit 0
else
  echo "D13 REGRESSION TESTS FAILED"
  exit 1
fi
