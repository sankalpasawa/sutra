#!/bin/bash
# sutra/marketplace/plugin/tests/integration/test-feedback-auto-override.sh
# Integration test for feedback-auto-override.sh hook.
# Verifies override events are counted as signals respecting privacy gates.

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$PLUGIN_ROOT/hooks/feedback-auto-override.sh"

TEST_HOME=$(mktemp -d -t sutra-int-XXXXXX)
export SUTRA_HOME="$TEST_HOME"
export SUTRA_FEEDBACK_AUTO="$TEST_HOME/feedback/auto"
export SUTRA_CONSENT_FILE="$TEST_HOME/consent"
export SUTRA_MEM_COUNTER="$TEST_HOME/mem-counter"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"

cleanup() { rm -rf "$TEST_HOME" 2>/dev/null; }
trap cleanup EXIT

PASS=0
FAIL=0
FAILURES=()
_pass() { PASS=$((PASS + 1)); }
_fail() { FAIL=$((FAIL + 1)); FAILURES+=("$1"); }

reset_state() {
  unset SUTRA_TELEMETRY SUTRA_FEEDBACK_CONSENT SUTRA_LEGACY_TELEMETRY
  unset PROTO004_ACK BUILD_LAYER_ACK CODEX_DIRECTIVE_ACK COMPLETION_PROTOCOL_ACK
  unset TOOL_INPUT_command
  rm -rf "$SUTRA_FEEDBACK_AUTO" 2>/dev/null
  rm -f "$SUTRA_MEM_COUNTER" "$SUTRA_CONSENT_FILE" 2>/dev/null
}

# Test 1 — PROTO004_ACK=1 in env, no consent → mem counter has override signal
reset_state
PROTO004_ACK=1 bash "$HOOK"
if [ -s "$SUTRA_MEM_COUNTER" ] && grep -q '"category":"override"' "$SUTRA_MEM_COUNTER" && grep -q '"sub":"PROTO004"' "$SUTRA_MEM_COUNTER"; then
  _pass
else
  _fail "Test 1: PROTO004_ACK in env → mem counter should have override/PROTO004"
fi

# Test 2 — Multiple ACKs → multiple signals deduped per hook-id
reset_state
PROTO004_ACK=1 BUILD_LAYER_ACK=1 bash "$HOOK"
if [ -s "$SUTRA_MEM_COUNTER" ]; then
  LINES=$(wc -l < "$SUTRA_MEM_COUNTER" | tr -d ' ')
  if [ "$LINES" = "2" ]; then _pass; else _fail "Test 2: expected 2 signals, got $LINES"; fi
  grep -q '"sub":"PROTO004"' "$SUTRA_MEM_COUNTER" && grep -q '"sub":"BUILD_LAYER"' "$SUTRA_MEM_COUNTER" && _pass || _fail "Test 2: should have PROTO004 and BUILD_LAYER subs"
else
  _fail "Test 2: no mem counter written"
  _fail "Test 2b: no mem counter written"
fi

# Test 3 — SUTRA_TELEMETRY=0 kill-switch → no capture
reset_state
SUTRA_TELEMETRY=0 PROTO004_ACK=1 bash "$HOOK"
if [ ! -s "$SUTRA_MEM_COUNTER" ] && ! find "$SUTRA_FEEDBACK_AUTO" -name '*.jsonl' 2>/dev/null | grep -q .; then
  _pass
else
  _fail "Test 3: opt-out should produce no capture"
fi

# Test 4 — Consent granted → disk write
reset_state
SUTRA_FEEDBACK_CONSENT=granted PROTO004_ACK=1 bash "$HOOK"
if find "$SUTRA_FEEDBACK_AUTO" -name '*.jsonl' 2>/dev/null | grep -q .; then
  FILE=$(find "$SUTRA_FEEDBACK_AUTO" -name '*.jsonl' | head -1)
  grep -q '"sub":"PROTO004"' "$FILE" && _pass || _fail "Test 4: disk file should contain PROTO004 sub"
else
  _fail "Test 4: consent → disk file should exist"
fi

# Test 5 — No ACKs → no capture
reset_state
bash "$HOOK"
if [ ! -s "$SUTRA_MEM_COUNTER" ]; then _pass; else _fail "Test 5: no ACKs should produce no capture"; fi

# Test 6 — Inline ACK in Bash command string → captured
reset_state
TOOL_INPUT_command='CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON="test" some-command' bash "$HOOK"
if [ -s "$SUTRA_MEM_COUNTER" ] && grep -q '"sub":"CODEX_DIRECTIVE"' "$SUTRA_MEM_COUNTER"; then
  _pass
else
  _fail "Test 6: inline CODEX_DIRECTIVE_ACK in command → should be captured"
fi

# Test 7 — Dedup: same ACK in both env and command → counted once
reset_state
TOOL_INPUT_command='PROTO004_ACK=1 cmd' PROTO004_ACK=1 bash "$HOOK"
if [ -s "$SUTRA_MEM_COUNTER" ]; then
  LINES=$(wc -l < "$SUTRA_MEM_COUNTER" | tr -d ' ')
  if [ "$LINES" = "1" ]; then _pass; else _fail "Test 7: dedup expected 1 signal, got $LINES"; fi
else
  _fail "Test 7: no mem counter written"
fi

# Test 8 — Hook exits 0 even on error (non-blocking contract)
reset_state
SUTRA_HOME="/nonexistent/readonly" PROTO004_ACK=1 bash "$HOOK"
EXIT=$?
assert_exit_zero() { [ "$1" = "0" ] && _pass || _fail "Test 8: hook must exit 0 even on error (got $1)"; }
assert_exit_zero "$EXIT"

# Test 9 — Hook exits 0 when no privacy lib (graceful missing-lib)
reset_state
CLAUDE_PLUGIN_ROOT=/nowhere bash "$HOOK"
EXIT=$?
[ "$EXIT" = "0" ] && _pass || _fail "Test 9: missing lib should exit 0 (got $EXIT)"

# Summary
TOTAL=$((PASS + FAIL))
echo ""
echo "-- Feedback Auto Override Hook --"
echo "PASS: $PASS / $TOTAL"
if [ $FAIL -gt 0 ]; then
  echo "FAIL: $FAIL"
  for f in "${FAILURES[@]}"; do echo "  x $f"; done
  exit 1
fi
echo "  OK all green"
exit 0
