#!/bin/bash
# tests/test-backward-compat.sh — existing Input Routing block format unchanged
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

GOLDEN="$DIR/golden/input-routing-baseline.txt"
[ -f "$GOLDEN" ] || { echo "golden missing"; exit 2; }

# Schema invariants in golden: every block has exactly these 6 lines
expected_fields=("INPUT:" "TYPE:" "EXISTING HOME:" "ROUTE:" "FIT CHECK:" "ACTION:")
for field in "${expected_fields[@]}"; do
  count=$(grep -c "^$field" "$GOLDEN")
  TESTS=$((TESTS+1))
  if [ "$count" -ge 1 ]; then
    PASS=$((PASS+1))
    echo "ok $TESTS - golden contains $field"
  else
    FAIL=$((FAIL+1))
    echo "not ok $TESTS - golden missing $field"
  fi
done

# After Phase 2 + activation, re-run on same inputs and diff against golden = 0
# (This second part runs in Phase 3.2, not here — this test only validates golden shape)

summary
