#!/usr/bin/env bash
# Regression test for D28 routing/depth gate and D27 Sutra→company gate.
# Simulates the 2026-04-15 failure mode and verifies the dispatcher now blocks it.
#
# Usage: bash holding/hooks/tests/test-d28-routing-gate.sh
# Exit 0 if all assertions pass, 1 otherwise.

set -u
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }

# Snapshot existing markers so we can restore after the test
SNAPSHOT_DIR=$(mktemp -d)
for f in input-routed depth-registered depth-assessed sutra-deploy-depth5; do
  [ -f ".claude/$f" ] && cp ".claude/$f" "$SNAPSHOT_DIR/$f"
done

cleanup() {
  rm -f .claude/input-routed .claude/depth-registered .claude/depth-assessed .claude/sutra-deploy-depth5
  for f in input-routed depth-registered depth-assessed sutra-deploy-depth5; do
    [ -f "$SNAPSHOT_DIR/$f" ] && cp "$SNAPSHOT_DIR/$f" ".claude/$f"
  done
  rm -rf "$SNAPSHOT_DIR"
}
trap cleanup EXIT

echo "=== D28 regression — routing gate blocks memory write without markers (2026-04-15 failure mode) ==="
bash holding/hooks/reset-turn-markers.sh >/dev/null
TOOL_NAME=Write TOOL_INPUT_file_path="/Users/$USER/.claude/projects/x/memory/feedback_x.md" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/d28-test.out 2>&1
rc=$?
if [ "$rc" != "0" ] && grep -q "INPUT ROUTING MISSING" /tmp/d28-test.out; then
  pass "memory write blocked with routing message"
else
  fail "expected BLOCK + 'INPUT ROUTING MISSING'; got rc=$rc"
fi

echo ""
echo "=== D28 regression — gate passes when markers present ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
TOOL_NAME=Write TOOL_INPUT_file_path="/tmp/fake-deliverable.md" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/d28-test.out 2>&1
rc=$?
if [ "$rc" = "0" ]; then
  pass "marker-present edit passes"
else
  fail "expected PASS; got rc=$rc"
  cat /tmp/d28-test.out
fi

echo ""
echo "=== D27 regression — Sutra→company edit blocked without depth-5 marker ==="
rm -f .claude/sutra-deploy-depth5
TOOL_NAME=Edit TOOL_INPUT_file_path="$REPO_ROOT/sutra/os/anything.md" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/d28-test.out 2>&1
rc=$?
if [ "$rc" != "0" ] && grep -q "SUTRA→COMPANY DEPLOY REQUIRES DEPTH 5" /tmp/d28-test.out; then
  pass "Sutra edit blocked with D27 message"
else
  fail "expected BLOCK + 'SUTRA→COMPANY DEPLOY REQUIRES DEPTH 5'; got rc=$rc"
fi

echo ""
echo "=== D27 regression — Sutra→company edit passes with depth-5 marker ==="
echo $(date +%s) > .claude/sutra-deploy-depth5
TOOL_NAME=Edit TOOL_INPUT_file_path="$REPO_ROOT/sutra/os/anything.md" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/d28-test.out 2>&1
rc=$?
if [ "$rc" = "0" ]; then
  pass "Sutra edit passes with depth-5 marker"
else
  fail "expected PASS; got rc=$rc"
  cat /tmp/d28-test.out
fi

echo ""
echo "=== UserPromptSubmit reset — markers cleared after reset hook ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
echo $(date +%s) > .claude/sutra-deploy-depth5
bash holding/hooks/reset-turn-markers.sh >/dev/null
if [ ! -f .claude/input-routed ] && [ ! -f .claude/depth-registered ] && [ ! -f .claude/sutra-deploy-depth5 ]; then
  pass "reset-turn-markers.sh clears all three markers"
else
  fail "markers still present after reset"
fi

echo ""
echo "=== Log audit — misses written to .enforcement/routing-misses.log ==="
if grep -q '"miss":"routing"' .enforcement/routing-misses.log 2>/dev/null; then
  pass "routing misses logged"
else
  fail "no routing miss entries in .enforcement/routing-misses.log"
fi

# ──────────────────────────────────────────────────────────────────────────
# PROTO-004 — Keys in Env Vars Only (HARD lift 2026-04-16, I-14 ladder)
# Check 5 in dispatcher-pretool.sh blocks on secret-pattern detection in
# existing file content. Override: SECRET_OVERRIDE=1 + reason. .env exempt.
# ──────────────────────────────────────────────────────────────────────────

# Markers stay set from prior cases so D28 routing-gate passes through.
SECRET_FILE="/tmp/proto004-secret.$$.txt"
SECRET_ENV="/tmp/proto004.$$.env"
CLEAN_FILE="/tmp/proto004-clean.$$.txt"
# Realistic-looking pattern that matches Check 5's regex: token[:=]"string >= 20 chars"
SECRET_LINE='api_key = "abcdef0123456789abcdefghijklm"'
echo "$SECRET_LINE" > "$SECRET_FILE"
echo "$SECRET_LINE" > "$SECRET_ENV"
echo "harmless content here" > "$CLEAN_FILE"

# Add a cleanup line so the trap removes our temp files too
# shellcheck disable=SC2329
_rm_proto004_temp() {
  rm -f "$SECRET_FILE" "$SECRET_ENV" "$CLEAN_FILE"
}
# Extend existing EXIT trap by calling cleanup + our remover
trap '_rm_proto004_temp; cleanup' EXIT

# Re-seed markers (prior test cases may have cleared/reset them)
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered

echo ""
echo "=== PROTO-004 (HARD) — Edit introducing secret in new_string → exit 2 ==="
TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_FILE" \
  TOOL_INPUT_new_string="$SECRET_LINE" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "2" ] && grep -q "BLOCKED — PROTO-004" /tmp/proto004-test.out; then
  pass "Edit with secret in new_string blocks exit 2"
else
  fail "expected exit 2 + 'BLOCKED — PROTO-004'; got rc=$rc"
  cat /tmp/proto004-test.out
fi

echo ""
echo "=== PROTO-004 (HARD) — Write with secret in content → exit 2 ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
TOOL_NAME=Write TOOL_INPUT_file_path="$CLEAN_FILE" \
  TOOL_INPUT_content="$SECRET_LINE" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "2" ] && grep -q "BLOCKED — PROTO-004" /tmp/proto004-test.out; then
  pass "Write with secret in content blocks exit 2"
else
  fail "expected exit 2 on Write with secret; got rc=$rc"
  cat /tmp/proto004-test.out
fi

echo ""
echo "=== PROTO-004 (HARD, codex P1 fix) — Edit REMOVING secret → exit 0 ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
# Existing file has secret on disk, but new_string removes it — remediation must pass
TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_FILE" \
  TOOL_INPUT_new_string="api_key = os.environ['API_KEY']  # moved to env" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q "BLOCKED — PROTO-004" /tmp/proto004-test.out; then
  pass "remediation edit (new_string without secret) passes exit 0"
else
  fail "expected exit 0 for remediation; got rc=$rc"
  cat /tmp/proto004-test.out
fi

echo ""
echo "=== PROTO-004 (HARD) — SECRET_OVERRIDE=1 → exit 0 ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
SECRET_OVERRIDE=1 SECRET_OVERRIDE_REASON='regression-test' \
  TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_FILE" \
  TOOL_INPUT_new_string="$SECRET_LINE" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && grep -q "PROTO-004 override accepted" /tmp/proto004-test.out; then
  pass "SECRET_OVERRIDE=1 passes with override-accepted message"
else
  fail "expected exit 0 + override message; got rc=$rc"
  cat /tmp/proto004-test.out
fi

echo ""
echo "=== PROTO-004 — .env file with secret content → exit 0 (exempt) ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
TOOL_NAME=Edit TOOL_INPUT_file_path="$SECRET_ENV" \
  TOOL_INPUT_new_string="$SECRET_LINE" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q "BLOCKED — PROTO-004" /tmp/proto004-test.out; then
  pass ".env file exempt (exit 0, no PROTO-004 block)"
else
  fail "expected exit 0 on .env; got rc=$rc"
  cat /tmp/proto004-test.out
fi

echo ""
echo "=== PROTO-004 — no secret in incoming content → exit 0 (silent) ==="
echo $(date +%s) > .claude/input-routed
echo "3 $(date +%s) test" > .claude/depth-registered
TOOL_NAME=Edit TOOL_INPUT_file_path="$CLEAN_FILE" \
  TOOL_INPUT_new_string="harmless replacement content here" \
  bash holding/hooks/dispatcher-pretool.sh >/tmp/proto004-test.out 2>&1
rc=$?
if [ "$rc" = "0" ] && ! grep -q "PROTO-004" /tmp/proto004-test.out; then
  pass "clean content passes with no PROTO-004 message"
else
  fail "expected exit 0 on clean; got rc=$rc"
  cat /tmp/proto004-test.out
fi

rm -f /tmp/proto004-test.out

echo ""
if [ "$FAIL" = "0" ]; then
  echo "ALL D27/D28/PROTO-004 REGRESSION TESTS PASSED"
  exit 0
else
  echo "D27/D28/PROTO-004 REGRESSION TESTS FAILED"
  exit 1
fi
