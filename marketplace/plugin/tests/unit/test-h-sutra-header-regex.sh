#!/bin/bash
# Test: h-sutra-enforce.sh HEADER_RE accepts compound verb chars (+, /, _).
# Fix for vinit-audit-2026-05-20 C2 — verb char-class was [A-Z0-9-]; rejected
# valid headers like [INPUT·FETCH+BUILD · ...] forcing 4x re-emit token cost.
# Broadened to [A-Z0-9+/_-]. Hyphen kept at end of class for literal interpretation.

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$PLUGIN_ROOT/hooks/h-sutra-enforce.sh"

PASS=0
FAIL=0
FAILURES=()

# Extract HEADER_RE directly from the hook (avoids drift between test and source).
HEADER_RE=$(awk '/^HEADER_RE=/ { sub(/^HEADER_RE=./,""); sub(/.$/,""); print; exit }' "$HOOK")

if [ -z "$HEADER_RE" ]; then
  echo "FATAL: could not extract HEADER_RE from $HOOK"
  exit 2
fi

_assert() {
  local name="$1" expected="$2" header="$3"
  local actual
  if printf '%s' "$header" | grep -qE "$HEADER_RE"; then
    actual="match"
  else
    actual="no-match"
  fi
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS+1))
    echo "  PASS: $name"
  else
    FAIL=$((FAIL+1))
    FAILURES+=("$name :: expected=$expected actual=$actual header='$header'")
    echo "  FAIL: $name (expected=$expected actual=$actual)"
  fi
}

echo "== HEADER_RE acceptance — compound verbs (C2 fix) =="
_assert "compound + verb"        "match" '[INPUT·FETCH+BUILD · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'
_assert "compound + verb alt"    "match" '[INPUT·PUSH+FILE · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'
_assert "slash verb"             "match" '[REVIEW·PUSH/FILE · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'
_assert "underscore verb"        "match" '[ASAWA·FOO_BAR · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'

echo "== HEADER_RE acceptance — legacy shapes (regression) =="
_assert "simple verb"            "match" '[INPUT·BUILD · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'
_assert "review gate"            "match" '[REVIEW·GATE · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'
_assert "stage-1-fail"           "match" '[STAGE-1-FAIL · CLARIFY · attempt:1/1]'
_assert "D-prefix direction"     "match" '[D38·VERIFY · TIMING:NOW · CHANNEL:CLI · REV:LOW · RISK:LOW]'

echo "== HEADER_RE rejection — malformed (negative) =="
_assert "no middot"              "no-match" '[INPUT BUILD]'
_assert "no bracket"             "no-match" 'No bracket at all'
_assert "lowercase verb"         "no-match" '[INPUT·build · TIMING:NOW]'
_assert "lowercase direction"    "no-match" '[lowercase·BUILD]'

echo ""
echo "== Summary =="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  for f in "${FAILURES[@]}"; do
    echo "  - $f"
  done
  exit 1
fi
exit 0
