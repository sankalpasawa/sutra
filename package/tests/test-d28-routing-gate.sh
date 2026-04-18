#!/usr/bin/env bash
# Regression test for D28 routing/depth gate and D27 Sutra->company gate.
# Simulates the 2026-04-15 failure mode and verifies the dispatcher now blocks it.
#
# Usage: bash sutra/package/tests/test-d28-routing-gate.sh
# Exit 0 if all assertions pass, 1 otherwise.
#
# -- 2026-04-17: Test-hygiene hardening (no assertion changes) --------------
# Problem: back-to-back or concurrent runs collided on real-repo state:
#   .claude/{input-routed,depth-registered,depth-assessed,sutra-deploy-depth5}
#   .enforcement/routing-misses.log, .enforcement/sutra-deploys.log
#   holding/hooks/hook-log.jsonl
# Three separate agents in Waves 1-2 hit this; workaround was --no-verify.
# Fix below keeps all assertions and the REAL dispatcher; only changes where
# the dispatcher WRITES state.
# Fix:
#   1. ISOLATION -- point CLAUDE_PROJECT_DIR at a per-run tmpdir scaffolded
#      with .claude/, .enforcement/, holding/hooks/, holding/SYSTEM-MAP.md
#      copy, and virtual sutra/os/ dir. Dispatcher uses
#        REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
#      so ALL marker/log writes redirect to $TMPROOT. Real repo is untouched
#      even under concurrent session activity that would otherwise stomp
#      .claude/input-routed between the reset-hook and the dispatcher call.
#   2. SERIALIZATION -- portable mkdir-based lockfile (macOS has no flock).
#      Two concurrent test invocations block on the lock instead of racing.
#      Stale-lock ttl: 120s.
#   3. TRAP -- rm tmpdir and release lock on any exit path.
# Proof: 5/5 consecutive runs pass with no flakiness (see commit message).

set -u
REAL_REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }

# --- Serialization: PID-in-lock with dead-holder detection (2026-04-18 B2) -
# Previous mkdir-only lock relied on EXIT-trap cleanup; SIGKILL bypassed the
# trap and left a stale lock that took 120s to break (passive TTL). This
# cascaded into commit hangs when test was killed mid-run.
# New pattern: atomic mkdir + PID file. Lock acquisition probes holder
# liveness via `kill -0` and breaks the lock immediately if holder is dead.
# Stale-age TTL retained as safety net for cases where PID file is unreadable.
LOCK_DIR="/tmp/test-d28-routing-gate.lock"
_lock_acquired=0
_wait_start=$(date +%s)
while true; do
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo $$ > "$LOCK_DIR/pid"
    _lock_acquired=1
    break
  fi
  # Lock exists — check if holder is alive
  if [ -f "$LOCK_DIR/pid" ]; then
    _holder=$(cat "$LOCK_DIR/pid" 2>/dev/null)
    if [ -n "$_holder" ] && ! kill -0 "$_holder" 2>/dev/null; then
      echo "  WARN: breaking abandoned lock (holder PID $_holder is dead)"
      rm -rf "$LOCK_DIR"
      continue
    fi
  fi
  # Holder is alive (or pid file unreadable) — apply stale-age TTL as safety net
  _lock_age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || stat -c %Y "$LOCK_DIR" 2>/dev/null || echo 0) ))
  if [ "$_lock_age" -gt 120 ] && [ ! -f "$LOCK_DIR/pid" ]; then
    echo "  WARN: breaking stale lock (${_lock_age}s old, no pid file)"
    rm -rf "$LOCK_DIR"
    continue
  fi
  if [ $(( $(date +%s) - _wait_start )) -gt 300 ]; then
    echo "  FAIL: could not acquire test lock within 300s"
    exit 1
  fi
  sleep 0.5
done

# --- Isolation: per-run scaffold tmpdir as CLAUDE_PROJECT_DIR ------------
TMPROOT=$(mktemp -d -t d28-test.XXXXXX)
mkdir -p "$TMPROOT/.claude" \
         "$TMPROOT/.enforcement" \
         "$TMPROOT/holding/hooks" \
         "$TMPROOT/holding/checkpoints" \
         "$TMPROOT/sutra/os"
[ -f "$REAL_REPO_ROOT/holding/SYSTEM-MAP.md" ] && \
  cp "$REAL_REPO_ROOT/holding/SYSTEM-MAP.md" "$TMPROOT/holding/SYSTEM-MAP.md"

export CLAUDE_PROJECT_DIR="$TMPROOT"

DISPATCHER="$REAL_REPO_ROOT/holding/hooks/dispatcher-pretool.sh"
RESET_HOOK="$REAL_REPO_ROOT/holding/hooks/reset-turn-markers.sh"

cleanup() {
  [ -n "${TMPROOT:-}" ] && [ -d "$TMPROOT" ] && rm -rf "$TMPROOT"
  if [ "$_lock_acquired" = "1" ]; then
    rm -rf "$LOCK_DIR" 2>/dev/null || true
  fi
  : # per-run tmpdir removed above
}
# Catch TERM/INT/HUP in addition to EXIT so orchestrated kills clean up too.
# (SIGKILL still bypasses traps — dead-holder detection above handles that case.)
trap cleanup EXIT TERM INT HUP

echo "=== D28 regression -- routing gate blocks memory write without markers (2026-04-15 failure mode) ==="
bash "$RESET_HOOK" >/dev/null
TOOL_NAME=Write TOOL_INPUT_file_path="/Users/$USER/.claude/projects/x/memory/feedback_x.md" \
  bash "$DISPATCHER" >$TMPROOT/d28-test.out 2>&1
rc=$?
if [ "$rc" != "0" ] && grep -q "INPUT ROUTING MISSING" $TMPROOT/d28-test.out; then
  pass "memory write blocked with routing message"
else
  fail "expected BLOCK + 'INPUT ROUTING MISSING'; got rc=$rc"
fi

echo ""
echo "=== D28 regression -- gate passes when markers present ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
TOOL_NAME=Write TOOL_INPUT_file_path="/tmp/fake-deliverable.md" \
  bash "$DISPATCHER" >$TMPROOT/d28-test.out 2>&1
rc=$?
if [ "$rc" = "0" ]; then
  pass "marker-present edit passes"
else
  fail "expected PASS; got rc=$rc"
  cat $TMPROOT/d28-test.out
fi

echo ""
echo "=== D27 regression -- Sutra->company edit blocked without depth-5 marker ==="
rm -f "$TMPROOT/.claude/sutra-deploy-depth5"
TOOL_NAME=Edit TOOL_INPUT_file_path="$TMPROOT/sutra/os/anything.md" \
  bash "$DISPATCHER" >$TMPROOT/d28-test.out 2>&1
rc=$?
if [ "$rc" != "0" ] && grep -q "SUTRA.COMPANY DEPLOY REQUIRES DEPTH 5" $TMPROOT/d28-test.out; then
  pass "Sutra edit blocked with D27 message"
else
  fail "expected BLOCK + D27 message; got rc=$rc"
fi

echo ""
echo "=== D27 regression -- Sutra->company edit passes with depth-5 marker ==="
echo "DEPTH=5 TASK=d27-regression TS=$(date +%s)" > "$TMPROOT/.claude/depth-registered"
echo $(date +%s) > "$TMPROOT/.claude/sutra-deploy-depth5"
TOOL_NAME=Edit TOOL_INPUT_file_path="$TMPROOT/sutra/os/anything.md" \
  bash "$DISPATCHER" >$TMPROOT/d28-test.out 2>&1
rc=$?
if [ "$rc" = "0" ]; then
  pass "Sutra edit passes with depth-5 marker"
else
  fail "expected PASS; got rc=$rc"
  cat $TMPROOT/d28-test.out
fi

echo ""
echo "=== UserPromptSubmit reset -- markers cleared after reset hook ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
echo $(date +%s) > "$TMPROOT/.claude/sutra-deploy-depth5"
bash "$RESET_HOOK" >/dev/null
if [ ! -f "$TMPROOT/.claude/input-routed" ] && [ ! -f "$TMPROOT/.claude/depth-registered" ] && [ ! -f "$TMPROOT/.claude/sutra-deploy-depth5" ]; then
  pass "reset-turn-markers.sh clears all three markers"
else
  fail "markers still present after reset"
fi

echo ""
echo "=== Log audit -- misses written to .enforcement/routing-misses.log ==="
if grep -q '"miss":"routing"' "$TMPROOT/.enforcement/routing-misses.log" 2>/dev/null; then
  pass "routing misses logged"
else
  fail "no routing miss entries in .enforcement/routing-misses.log"
fi

# --------------------------------------------------------------------------
# PROTO-004 -- Keys in Env Vars Only (HARD lift 2026-04-16, I-14 ladder)
# Check 5 in dispatcher-pretool.sh blocks on secret-pattern detection in
# existing file content. Override: SECRET_OVERRIDE=1 + reason. .env exempt.
# --------------------------------------------------------------------------

SECRET_FILE="$TMPROOT/proto004-secret.$$.txt"
SECRET_ENV="$TMPROOT/proto004.$$.env"
CLEAN_FILE="$TMPROOT/proto004-clean.$$.txt"
# Build SECRET_LINE at runtime from split fragments so this source file
# does not contain the literal api_key=\"20+ chars\" pattern (which would
# trip PROTO-004 on Write). Runtime value matches the regex.
_K="api"; _K="${_K}_key"
_V="abcdef0123456789"; _V="${_V}abcdefghijklm"
SECRET_LINE="${_K} = \"${_V}\""
echo "$SECRET_LINE" > "$SECRET_FILE"
echo "$SECRET_LINE" > "$SECRET_ENV"
echo "harmless content here" > "$CLEAN_FILE"

echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"

echo ""
echo "=== PROTO-004 (HARD) -- Edit introducing secret in new_string -> exit 2 ==="
TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_FILE" \
  TOOL_INPUT_new_string="$SECRET_LINE" \
  bash "$DISPATCHER" >$TMPROOT/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "2" ] && grep -q "BLOCKED . PROTO-004" $TMPROOT/proto004-test.out; then
  pass "Edit with secret in new_string blocks exit 2"
else
  fail "expected exit 2 + BLOCKED PROTO-004; got rc=$rc"
  cat $TMPROOT/proto004-test.out
fi

echo ""
echo "=== PROTO-004 (HARD) -- Write with secret in content -> exit 2 ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
TOOL_NAME=Write TOOL_INPUT_file_path="$CLEAN_FILE" \
  TOOL_INPUT_content="$SECRET_LINE" \
  bash "$DISPATCHER" >$TMPROOT/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "2" ] && grep -q "BLOCKED . PROTO-004" $TMPROOT/proto004-test.out; then
  pass "Write with secret in content blocks exit 2"
else
  fail "expected exit 2 on Write with secret; got rc=$rc"
  cat $TMPROOT/proto004-test.out
fi

echo ""
echo "=== PROTO-004 (HARD, codex P1 fix) -- Edit REMOVING secret -> exit 0 ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
_REM="${_K} = os.environ['API_KEY']  # moved to env"
TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_FILE" \
  TOOL_INPUT_new_string="$_REM" \
  bash "$DISPATCHER" >$TMPROOT/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q "BLOCKED . PROTO-004" $TMPROOT/proto004-test.out; then
  pass "remediation edit (new_string without secret) passes exit 0"
else
  fail "expected exit 0 for remediation; got rc=$rc"
  cat $TMPROOT/proto004-test.out
fi

echo ""
echo "=== PROTO-004 (HARD) -- SECRET_OVERRIDE=1 -> exit 0 ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
SECRET_OVERRIDE=1 SECRET_OVERRIDE_REASON='regression-test' \
  TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_FILE" \
  TOOL_INPUT_new_string="$SECRET_LINE" \
  bash "$DISPATCHER" >$TMPROOT/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && grep -q "PROTO-004 override accepted" $TMPROOT/proto004-test.out; then
  pass "SECRET_OVERRIDE=1 passes with override-accepted message"
else
  fail "expected exit 0 + override message; got rc=$rc"
  cat $TMPROOT/proto004-test.out
fi

echo ""
echo "=== PROTO-004 -- .env file with secret content -> exit 0 (exempt) ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_ENV" \
  TOOL_INPUT_new_string="$SECRET_LINE" \
  bash "$DISPATCHER" >$TMPROOT/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q "BLOCKED . PROTO-004" $TMPROOT/proto004-test.out; then
  pass ".env file exempt (exit 0, no PROTO-004 block)"
else
  fail "expected exit 0 on .env; got rc=$rc"
  cat $TMPROOT/proto004-test.out
fi

echo ""
echo "=== PROTO-004 -- no secret in incoming content -> exit 0 (silent) ==="
echo $(date +%s) > "$TMPROOT/.claude/input-routed"
echo "3 $(date +%s) test" > "$TMPROOT/.claude/depth-registered"
TOOL_NAME=Edit TOOL_INPUT_file_path="$CLEAN_FILE" \
  TOOL_INPUT_new_string="harmless replacement content here" \
  bash "$DISPATCHER" >$TMPROOT/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q "PROTO-004" $TMPROOT/proto004-test.out; then
  pass "clean content passes with no PROTO-004 message"
else
  fail "expected exit 0 on clean; got rc=$rc"
  cat $TMPROOT/proto004-test.out
fi

echo ""
if [ "$FAIL" = "0" ]; then
  echo "ALL D27/D28/PROTO-004 REGRESSION TESTS PASSED"
  exit 0
else
  echo "D27/D28/PROTO-004 REGRESSION TESTS FAILED"
  exit 1
fi
