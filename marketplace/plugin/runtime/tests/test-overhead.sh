#!/bin/bash
# test-overhead.sh — W0a step 11. Covers bin/sutra-overhead.
#
# Scripted turn: a canary row + sutra-turn UserPromptSubmit rows + sutra-turn
# Stop rows + the stage_digest row are written into a throwaway project ledger
# at $CLAUDE_PROJECT_DIR/.sutra/turn/<session>/<turn_id>.jsonl, then
# `sutra-overhead emit` must append exactly ONE task_end row carrying
# governance_ms, and `report` must print a p50 with its denominator.
#
# The ledger rows are written here rather than produced by running the real
# sutra-turn so this suite stays hermetic (no legacy hook executes, nothing
# outside the temp dir is touched). Set SUTRA_OVERHEAD_TEST_LIVE=1 to ALSO run
# the real bin/sutra-canary + bin/sutra-turn once, as an integration case.
#
# bash 3.2 compatible. Prints "failed=<n>"; exit code = failures.
set -u

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$TESTS_DIR/../.." && pwd)"
OVERHEAD="$PLUGIN_DIR/bin/sutra-overhead"

failed=0
pass() { echo "  ok   — $1"; }
fail() { echo "  FAIL — $1"; failed=$((failed+1)); }
check() { # check <label> <actual> <expected>
  if [ "$2" = "$3" ]; then pass "$1 ($2)"; else fail "$1: got '$2' want '$3'"; fi
}

command -v jq >/dev/null 2>&1 || { echo "jq missing — cannot run"; echo "failed=1"; exit 1; }
[ -f "$OVERHEAD" ] || { echo "missing $OVERHEAD"; echo "failed=1"; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/sutra-overhead-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
PROJ="$TMP/proj"
SESS="sess-test-0001"
TURN="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
LEDGER_DIR="$PROJ/.sutra/turn/$SESS"
mkdir -p "$LEDGER_DIR"
LEDGER="$LEDGER_DIR/$TURN.jsonl"

echo "=== sutra-overhead ==="

# ── the scripted turn ───────────────────────────────────────────────────────
T0=1757600000000     # epoch ms, first UserPromptSubmit row
{
  # canary (UserPromptSubmit lane, its own registration)
  printf '{"turn_id":"%s","step_id":"canary","family":"canary","impl":"bin:sutra-canary","exit":0,"dur_ms":3,"stdout_sha":"e3b0c442","stderr_sha":"e3b0c442","event":"UserPromptSubmit","ts":%s}\n' "$TURN" "$T0"
  # sutra-turn UserPromptSubmit steps
  printf '{"turn_id":"%s","step_id":"turn_reset","family":"ups","impl":"shim:hooks/reset-turn-markers.sh","exit":0,"dur_ms":12,"stdout_sha":"aa01","stderr_sha":"e3b0c442","event":"UserPromptSubmit","ts":%s}\n' "$TURN" "$((T0+10))"
  printf '{"turn_id":"%s","step_id":"hsutra_classify","family":"ups","impl":"shim:hooks/per-turn-discipline-prompt.sh","exit":0,"dur_ms":24,"stdout_sha":"aa02","stderr_sha":"e3b0c442","event":"UserPromptSubmit","ts":%s}\n' "$TURN" "$((T0+40))"
  # a degrade row that is NOT a step (kill-switch fallback to legacy)
  printf '{"turn_id":"%s","kind":"killswitch","event":"PreToolUse","ts":%s}\n' "$TURN" "$((T0+120))"
  # sutra-turn Stop steps, one of them timed out (exit 124)
  printf '{"turn_id":"%s","step_id":"stop_collect","family":"stop-collect","impl":"shim:hooks/session-logger.sh","exit":0,"dur_ms":30,"stdout_sha":"bb01","stderr_sha":"e3b0c442","event":"Stop","ts":%s}\n' "$TURN" "$((T0+5000))"
  printf '{"turn_id":"%s","step_id":"stop_verdict","family":"writing","impl":"shim:hooks/writing-style-gate.sh","exit":124,"dur_ms":18,"stdout_sha":"e3b0c442","stderr_sha":"bb02","event":"Stop","ts":%s}\n' "$TURN" "$((T0+5100))"
  # stage digest closes the turn (not a step)
  printf '{"turn_id":"%s","stage_digest":"9f2c1a6b0d4e8f37","event":"Stop","ts":%s}\n' "$TURN" "$((T0+5101))"
} > "$LEDGER"

EXP_GOV=$((3+12+24+30+18))        # 87
EXP_STEPS=5
EXP_DEGRADES=2                     # killswitch row + the exit-124 step
# the stage_digest row is the turn's last Stop-event row, so it bounds the wall
EXP_WORK=$(( (T0+5101) - T0 - EXP_GOV ))   # 5014

# ── 1. emit appends exactly one row ─────────────────────────────────────────
OUT="$(CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" emit 2>&1)"; rc=$?
check "emit exit code" "$rc" "0"
LOG="$PROJ/.sutra/estimation.jsonl"
if [ -s "$LOG" ]; then pass "estimation.jsonl created"; else fail "estimation.jsonl not created (emit said: $OUT)"; fi
check "rows appended" "$(wc -l < "$LOG" | tr -d ' ')" "1"

# ── 2. the row's fields ─────────────────────────────────────────────────────
ROW="$(tail -1 "$LOG")"
check "row has governance_ms" "$(printf '%s' "$ROW" | jq -r 'has("governance_ms")')" "true"
check "governance_ms"         "$(printf '%s' "$ROW" | jq -r '.governance_ms')" "$EXP_GOV"
check "steps_run"             "$(printf '%s' "$ROW" | jq -r '.steps_run')"     "$EXP_STEPS"
check "degrades"              "$(printf '%s' "$ROW" | jq -r '.degrades')"      "$EXP_DEGRADES"
check "work_ms"               "$(printf '%s' "$ROW" | jq -r '.work_ms')"       "$EXP_WORK"
check "turn_id"               "$(printf '%s' "$ROW" | jq -r '.turn_id')"       "$TURN"
TS="$(printf '%s' "$ROW" | jq -r '.ts')"
if [ "$TS" -gt 1700000000 ] 2>/dev/null; then pass "ts is epoch seconds ($TS)"; else fail "ts not epoch seconds: $TS"; fi
# timeouts is degrades' killed-step half on its own: governance that was cut off
# rather than governance that fell back. One of the Stop steps above exited 124.
check "timeouts"              "$(printf '%s' "$ROW" | jq -r '.timeouts')"      "1"
check "row key set" "$(printf '%s' "$ROW" | jq -r 'keys_unsorted | sort | join(",")')" \
  "degrades,governance_ms,steps_run,timeouts,ts,turn_id,work_ms"

# ── 3. report prints p50 + denominator ──────────────────────────────────────
REP="$(CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" report 2>&1)"; rc=$?
check "report exit code" "$rc" "0"
case "$REP" in *"p50 governance_ms: $EXP_GOV"*) pass "report p50" ;; *) fail "report p50 missing: $REP" ;; esac
case "$REP" in *"denominator: 1 turns"*)        pass "report denominator" ;; *) fail "report denominator missing: $REP" ;; esac
case "$REP" in *"timeouts: 1 steps"*)            pass "report timeouts" ;; *) fail "report timeouts missing: $REP" ;; esac
check "report --json timeouts" \
  "$(CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" report --json | jq -r '.timeouts')" "1"
check "report --json denominator" \
  "$(CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" report --json | jq -r '.denominator')" "1"

# ── 4. a second turn moves the denominator and the p50 ──────────────────────
TURN2="00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
printf '{"turn_id":"%s","step_id":"only","family":"ups","impl":"shim:hooks/x.sh","exit":0,"dur_ms":7,"event":"UserPromptSubmit","ts":%s}\n' \
  "$TURN2" "$T0" > "$LEDGER_DIR/$TURN2.jsonl"
CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" emit --turn-id "$TURN2" --quiet
check "rows after second emit" "$(wc -l < "$LOG" | tr -d ' ')" "2"
check "second row governance_ms" "$(tail -1 "$LOG" | jq -r '.governance_ms')" "7"
check "second row work_ms (no Stop row)" "$(tail -1 "$LOG" | jq -r '.work_ms')" "0"
check "p50 over two turns" \
  "$(CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" report --json | jq -r '.p50_governance_ms')" \
  "$(( (EXP_GOV + 7) / 2 ))"
check "denominator over two turns" \
  "$(CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" report --json | jq -r '.denominator')" "2"

# ── 5. soft failure: no ledger at all never blocks a turn ───────────────────
EMPTY="$TMP/empty"; mkdir -p "$EMPTY"
OUT="$(CLAUDE_PROJECT_DIR="$EMPTY" sh "$OVERHEAD" emit 2>&1)"; rc=$?
check "emit with no ledger exits 0" "$rc" "0"
case "$OUT" in *"no ledger rows"*) pass "emit says why it did nothing" ;; *) fail "unexpected: $OUT" ;; esac
if [ -f "$EMPTY/.sutra/estimation.jsonl" ]; then fail "emit wrote a row with no ledger"; else pass "no row written with no ledger"; fi
OUT="$(CLAUDE_PROJECT_DIR="$EMPTY" sh "$OVERHEAD" report 2>&1)"; rc=$?
check "report with no log exits 0" "$rc" "0"
case "$OUT" in *"denominator: 0 turns"*) pass "empty report shows denominator 0" ;; *) fail "unexpected: $OUT" ;; esac

# ── 6. jq-missing degrade ───────────────────────────────────────────────────
FAKEBIN="$TMP/nojq"; mkdir -p "$FAKEBIN"
for c in sh date mkdir ls head dirname printf cat; do
  p="$(command -v "$c" 2>/dev/null)"; [ -n "$p" ] && ln -sf "$p" "$FAKEBIN/$c"
done
OUT="$(PATH="$FAKEBIN" CLAUDE_PROJECT_DIR="$PROJ" sh "$OVERHEAD" emit 2>&1)"; rc=$?
check "emit without jq exits 0" "$rc" "0"
case "$OUT" in *"degraded: jq unavailable"*) pass "jq-missing degrade line" ;; *) fail "unexpected: $OUT" ;; esac
check "no extra row written without jq" "$(wc -l < "$LOG" | tr -d ' ')" "2"

# ── 7. --version ────────────────────────────────────────────────────────────
case "$(sh "$OVERHEAD" --version 2>&1)" in
  "sutra-overhead "*) pass "--version" ;;
  *) fail "--version output" ;;
esac

# ── 8. optional live integration with the real runtime binaries ─────────────
if [ "${SUTRA_OVERHEAD_TEST_LIVE:-0}" = "1" ] \
   && [ -x "$PLUGIN_DIR/bin/sutra-turn" ] && [ -x "$PLUGIN_DIR/bin/sutra-canary" ]; then
  LIVE="$TMP/live"; mkdir -p "$LIVE/.claude" "$LIVE/.sutra"
  HOOKJSON='{"session_id":"live-sess","prompt_id":"live-prompt","hook_event_name":"UserPromptSubmit","prompt":"hello"}'
  printf '%s' "$HOOKJSON" | CLAUDE_PROJECT_DIR="$LIVE" CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR" "$PLUGIN_DIR/bin/sutra-canary" >/dev/null 2>&1
  printf '%s' "$HOOKJSON" | CLAUDE_PROJECT_DIR="$LIVE" CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR" "$PLUGIN_DIR/bin/sutra-turn" run --event UserPromptSubmit >/dev/null 2>&1
  # The gap between the two events IS the work the meter is supposed to see: the
  # model thinking and calling tools while no hook is running. Without it a
  # scripted turn is all governance and work_ms is legitimately 0, which proves
  # nothing about whether the stamps are readable.
  sleep 3
  printf '%s' '{"session_id":"live-sess","prompt_id":"live-prompt","hook_event_name":"Stop"}' \
    | CLAUDE_PROJECT_DIR="$LIVE" CLAUDE_PLUGIN_ROOT="$PLUGIN_DIR" "$PLUGIN_DIR/bin/sutra-turn" run --event Stop >/dev/null 2>&1
  CLAUDE_PROJECT_DIR="$LIVE" sh "$OVERHEAD" emit --quiet
  if [ -s "$LIVE/.sutra/estimation.jsonl" ] \
     && [ "$(tail -1 "$LIVE/.sutra/estimation.jsonl" | jq -r 'has("governance_ms")')" = "true" ]; then
    pass "live scripted turn produced a task_end row"
  else
    fail "live scripted turn produced no task_end row"
  fi
  LIVE_ROW="$(tail -1 "$LIVE/.sutra/estimation.jsonl" 2>/dev/null)"
  LIVE_WORK="$(printf '%s' "$LIVE_ROW" | jq -r '.work_ms // 0' 2>/dev/null)"
  if [ "${LIVE_WORK:-0}" -gt 0 ] 2>/dev/null; then
    pass "live work_ms > 0 (ledger rows carry a readable ts): $LIVE_WORK"
  else
    fail "live work_ms is $LIVE_WORK — the ledger's ts is missing or unreadable: $LIVE_ROW"
  fi
else
  echo "  skip — live integration (set SUTRA_OVERHEAD_TEST_LIVE=1 with sutra-turn/sutra-canary present)"
fi

echo "failed=$failed"
exit "$failed"
