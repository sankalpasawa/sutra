#!/usr/bin/env bash
# Regression test for holding/hooks/loop-budget-guard.sh
# PROTO-000: mechanism ships with test.  BUILD-LAYER: L1.
# Usage: bash holding/hooks/tests/test-loop-budget-guard.sh
# Isolation: per-run mktemp as LOOP_GUARD_STATE_DIR + CLAUDE_PROJECT_DIR; trap cleanup.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/loop-budget-guard.sh"
FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }
TMPROOT=$(mktemp -d -t loopguard-test.XXXXXX)
cleanup() { [ -n "${TMPROOT:-}" ] && [ -d "$TMPROOT" ] && rm -rf "$TMPROOT"; }
trap cleanup EXIT
STATE="$TMPROOT/state"; mkdir -p "$STATE"
run_hook() {
  local json="$1"
  printf '%s' "$json" | CLAUDE_PROJECT_DIR="$TMPROOT" LOOP_GUARD_STATE_DIR="$STATE" \
    SUTRA_TOOL_BUDGET="${SUTRA_TOOL_BUDGET:-250}" SUTRA_REPEAT_LIMIT="${SUTRA_REPEAT_LIMIT:-8}" \
    LOOP_BUDGET_GUARD_DISABLED="${LOOP_BUDGET_GUARD_DISABLED:-}" \
    SUTRA_BYPASS="${SUTRA_BYPASS:-}" LOOP_GUARD_ACK="${LOOP_GUARD_ACK:-}" bash "$HOOK"
  return $?
}
js() { printf '{"tool_name":"%s","tool_input":{"command":"%s"},"session_id":"%s"}' "$1" "$2" "$3"; }

echo "=== Case 1: single normal call passes ==="
run_hook "$(js Bash ls s1)"; rc=$?
[ "$rc" -eq 0 ] && pass "single call exits 0" || fail "single call expected 0 got $rc"
[ -f "$STATE/s1.loopguard" ] && [ "$(wc -l < "$STATE/s1.loopguard" | tr -d ' ')" = "1" ] \
  && pass "state file has 1 entry" || fail "state file not 1 entry"

echo "=== Case 2: repeat limit blocks the Nth identical call ==="
( export SUTRA_REPEAT_LIMIT=3
  run_hook "$(js Bash same s2)"; r1=$?; run_hook "$(js Bash same s2)"; r2=$?; run_hook "$(js Bash same s2)"; r3=$?
  [ "$r1" -eq 0 ] && [ "$r2" -eq 0 ] || { echo "  FAIL: first two should pass ($r1,$r2)"; exit 1; }
  [ "$r3" -eq 2 ] || { echo "  FAIL: 3rd identical should block (got $r3)"; exit 1; }
  echo "  PASS: 3rd identical call blocked (exit 2)" ) || FAIL=1

echo "=== Case 3: total tool budget exceeded blocks ==="
( export SUTRA_TOOL_BUDGET=3
  run_hook "$(js Bash a s3)" >/dev/null; run_hook "$(js Bash b s3)" >/dev/null; run_hook "$(js Bash c s3)" >/dev/null
  run_hook "$(js Bash d s3)"; r4=$?
  [ "$r4" -eq 2 ] || { echo "  FAIL: 4th call past budget should block (got $r4)"; exit 1; }
  echo "  PASS: call past budget blocked (exit 2)" ) || FAIL=1

echo "=== Case 4: LOOP_BUDGET_GUARD_DISABLED bypasses ==="
( export SUTRA_REPEAT_LIMIT=2 LOOP_BUDGET_GUARD_DISABLED=1
  run_hook "$(js Bash k s4)" >/dev/null; run_hook "$(js Bash k s4)"; r=$?
  [ "$r" -eq 0 ] || { echo "  FAIL: kill-switch should force 0 (got $r)"; exit 1; }
  echo "  PASS: kill-switch forces exit 0" ) || FAIL=1

echo "=== Case 5: SUTRA_BYPASS bypasses ==="
( export SUTRA_REPEAT_LIMIT=2 SUTRA_BYPASS=1
  run_hook "$(js Bash z s5)" >/dev/null; run_hook "$(js Bash z s5)"; r=$?
  [ "$r" -eq 0 ] || { echo "  FAIL: SUTRA_BYPASS should force 0 (got $r)"; exit 1; }
  echo "  PASS: SUTRA_BYPASS forces exit 0" ) || FAIL=1

echo "=== Case 6: LOOP_GUARD_ACK overrides the loop block ==="
( export SUTRA_REPEAT_LIMIT=2 LOOP_GUARD_ACK=1
  run_hook "$(js Bash q s6)" >/dev/null; run_hook "$(js Bash q s6)"; r=$?
  [ "$r" -eq 0 ] || { echo "  FAIL: ACK should force 0 (got $r)"; exit 1; }
  echo "  PASS: ACK overrides block" ) || FAIL=1

echo "=== Case 7: malformed and empty stdin fail open ==="
printf '%s' 'not json at all' | CLAUDE_PROJECT_DIR="$TMPROOT" LOOP_GUARD_STATE_DIR="$STATE" bash "$HOOK"; r=$?
[ "$r" -eq 0 ] && pass "malformed stdin exits 0" || fail "malformed expected 0 got $r"
printf '' | CLAUDE_PROJECT_DIR="$TMPROOT" LOOP_GUARD_STATE_DIR="$STATE" bash "$HOOK"; r=$?
[ "$r" -eq 0 ] && pass "empty stdin exits 0" || fail "empty expected 0 got $r"

echo "=== Case 8: path-traversal session_id is sanitized (no escape) ==="
run_hook "$(js Bash x '../../etc/evil')"; r=$?
[ "$r" -eq 0 ] && pass "traversal session_id still exits 0" || fail "traversal expected 0 got $r"
# Sanitized name begins with '.' (../../ -> .._.._); use ls -a or it stays hidden.
if ls -a "$STATE" | grep -q '_etc_evil[.]loopguard$'; then
  pass "traversal session_id sanitized to flat filename (no escape)"
else
  fail "expected sanitized flat filename not found"
fi

echo "=== Case 9: agent-orchestration tools are EXEMPT (multi-agent fix) ==="
# With a tiny budget + repeat limit, many identical Agent/Task/Workflow
# dispatches must STILL pass and must NOT be recorded — a fan-out is not a loop.
( export SUTRA_TOOL_BUDGET=3 SUTRA_REPEAT_LIMIT=2
  ok=1
  for i in 1 2 3 4 5 6 7 8 9 10; do run_hook "$(js Agent dispatch sAgent)" >/dev/null || { ok=0; break; }; done
  for t in Task Workflow; do for i in 1 2 3 4 5; do run_hook "$(js "$t" same sAgent)" >/dev/null || { ok=0; break; }; done; done
  [ "$ok" -eq 1 ] || { echo "  FAIL: agent-dispatch tool was blocked (should be exempt)"; exit 1; }
  [ ! -f "$STATE/sAgent.loopguard" ] || { echo "  FAIL: agent dispatch was recorded (should be exempt)"; exit 1; }
  echo "  PASS: Agent/Task/Workflow dispatches exempt — not blocked, not recorded" ) || FAIL=1

echo "=== Case 10: LOOP_GUARD_COUNT_AGENTS=1 restores counting ==="
( export SUTRA_REPEAT_LIMIT=3 LOOP_GUARD_COUNT_AGENTS=1
  run_hook "$(js Agent z sCount)" >/dev/null; run_hook "$(js Agent z sCount)" >/dev/null
  run_hook "$(js Agent z sCount)"; r=$?
  [ "$r" -eq 2 ] || { echo "  FAIL: with COUNT_AGENTS=1, 3rd identical Agent should block (got $r)"; exit 1; }
  echo "  PASS: opt-in counting blocks looping Agent dispatch" ) || FAIL=1

echo "=== Case 11: per-turn reset (loopguard-turn-reset.sh) clears the budget ==="
# Budget-bound session: exhaust the budget so the guard blocks; a REAL user
# prompt (UserPromptSubmit) should reset the counter so the next call passes.
RESET="$(cd "$(dirname "$HOOK")" && pwd)/loopguard-turn-reset.sh"
( export SUTRA_TOOL_BUDGET=3
  run_hook "$(js Bash a sTurn)" >/dev/null; run_hook "$(js Bash b sTurn)" >/dev/null
  run_hook "$(js Bash c sTurn)" >/dev/null
  run_hook "$(js Bash d sTurn)"; rb=$?
  [ "$rb" -eq 2 ] || { echo "  FAIL: 4th call should block before reset (got $rb)"; exit 1; }
  # Real user prompt -> reset hook truncates the counter
  printf '{"prompt":"next real task","session_id":"sTurn"}' \
    | LOOP_GUARD_STATE_DIR="$STATE" bash "$RESET"
  [ ! -s "$STATE/sTurn.loopguard" ] || { echo "  FAIL: reset did not truncate counter"; exit 1; }
  run_hook "$(js Bash e sTurn)"; ra=$?
  [ "$ra" -eq 0 ] || { echo "  FAIL: call after reset should pass (got $ra)"; exit 1; }
  echo "  PASS: real-turn reset clears the budget; next turn passes" ) || FAIL=1

echo "=== Case 12: reset SKIPS synthetic turns (no mid-turn wipe) ==="
( export SUTRA_TOOL_BUDGET=3
  run_hook "$(js Bash a sSyn)" >/dev/null; run_hook "$(js Bash b sSyn)" >/dev/null
  # Synthetic UserPromptSubmit (system-reminder) must NOT reset
  printf '{"prompt":"<system-reminder>blah</system-reminder>","session_id":"sSyn"}' \
    | LOOP_GUARD_STATE_DIR="$STATE" bash "$RESET"
  n=$(wc -l < "$STATE/sSyn.loopguard" | tr -d ' ')
  [ "$n" = "2" ] || { echo "  FAIL: synthetic turn wrongly reset counter (lines=$n)"; exit 1; }
  echo "  PASS: synthetic turn does NOT reset (counter intact)" ) || FAIL=1

echo
[ "$FAIL" -eq 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL
