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

echo ""
if [ "$FAIL" = "0" ]; then
  echo "ALL D27/D28 REGRESSION TESTS PASSED"
  exit 0
else
  echo "D27/D28 REGRESSION TESTS FAILED"
  exit 1
fi
