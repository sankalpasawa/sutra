#!/bin/bash
# Test: blueprint-check.sh D48 extension (Output looks like + Verified by fields).
# PROTO-000 test for the BLUEPRINT engine V2 mechanism.
#
# Verifies:
#   [1] foundational + marker with both flags -> exit 0 (pass)
#   [2] foundational + no marker -> exit 2 (existing behavior preserved)
#   [3] foundational + missing HAS_OUTPUT -> exit 2 (D48 new)
#   [4] foundational + missing HAS_VERIFY -> exit 2 (D48 new)
#   [5] non-foundational + no marker -> exit 0 (SOFT advisory only)
#   [6] BLUEPRINT_ACK=1 override -> exit 0 (bypass)

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$PLUGIN_ROOT/hooks/blueprint-check.sh"

PASS=0
FAIL=0
FAILURES=()

_result() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS+1))
    echo "  PASS: $name"
  else
    FAIL=$((FAIL+1))
    FAILURES+=("$name :: expected=$expected actual=$actual")
    echo "  FAIL: $name"
    echo "    expected: $expected"
    echo "    actual:   $actual"
  fi
}

_TMP=$(mktemp -d)
trap "rm -rf $_TMP" EXIT
mkdir -p "$_TMP/.claude" "$_TMP/sutra/os/charters" "$_TMP/holding"
MARKER="$_TMP/.claude/blueprint-registered"

_run_capture_exit() {
  local file_path="$1"
  printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$file_path" \
    | CLAUDE_PROJECT_DIR="$_TMP" "$HOOK" >/dev/null 2>&1
  echo $?
}

echo "== blueprint-check.sh D48 extension tests =="

# --- [1] foundational + both flags -> exit 0
echo "[1] foundational + both flags -> pass"
printf 'HAS_OUTPUT=1\nHAS_VERIFY=1\nTS=1730000000\nTASK=test\n' > "$MARKER"
exit_code=$(_run_capture_exit "$_TMP/holding/FOUNDER-DIRECTIONS.md")
_result "both flags pass" "0" "$exit_code"

# --- [2] foundational + no marker -> exit 2
echo "[2] foundational + no marker -> blocked"
rm -f "$MARKER"
exit_code=$(_run_capture_exit "$_TMP/holding/FOUNDER-DIRECTIONS.md")
_result "no marker blocked" "2" "$exit_code"

# --- [3] foundational + missing HAS_OUTPUT -> exit 2 (D48)
echo "[3] foundational + missing HAS_OUTPUT -> blocked"
printf 'HAS_VERIFY=1\nTS=1730000000\nTASK=test\n' > "$MARKER"
exit_code=$(_run_capture_exit "$_TMP/holding/FOUNDER-DIRECTIONS.md")
_result "no HAS_OUTPUT blocked" "2" "$exit_code"

# --- [4] foundational + missing HAS_VERIFY -> exit 2 (D48)
echo "[4] foundational + missing HAS_VERIFY -> blocked"
printf 'HAS_OUTPUT=1\nTS=1730000000\nTASK=test\n' > "$MARKER"
exit_code=$(_run_capture_exit "$_TMP/holding/FOUNDER-DIRECTIONS.md")
_result "no HAS_VERIFY blocked" "2" "$exit_code"

# --- [5] non-foundational path -> SOFT advisory regardless
echo "[5] non-foundational + no marker -> soft advisory (exit 0)"
rm -f "$MARKER"
exit_code=$(_run_capture_exit "$_TMP/some/random/file.txt")
_result "non-foundational soft" "0" "$exit_code"

# --- [6] override -> bypass
echo "[6] BLUEPRINT_ACK=1 -> bypass"
rm -f "$MARKER"
ack_exit=$(printf '{"tool_name":"Edit","tool_input":{"file_path":"'"$_TMP"'/holding/FOUNDER-DIRECTIONS.md"}}' \
  | CLAUDE_PROJECT_DIR="$_TMP" BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='test override' "$HOOK" >/dev/null 2>&1; echo $?)
_result "override bypass" "0" "$ack_exit"

# --- Report
echo ""
echo "== Results: $PASS passed, $FAIL failed =="
if [ $FAIL -gt 0 ]; then
  echo "Failures:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
  exit 1
fi
exit 0
