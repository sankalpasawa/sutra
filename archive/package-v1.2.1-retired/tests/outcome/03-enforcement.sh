#!/bin/bash
# Outcome: hooks block Edit/Write without markers; allow with markers; log fires.
# Tests the enforcement end-to-end from the external-user perspective.

set -u
TEST_NAME="03-enforcement"
source "$(dirname "$0")/lib/assert.sh"

TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"

echo "  [setup] $TEST_DIR"

# Install Sutra.
if [ -n "${SUTRA_PACKAGE_DIR:-}" ] && [ -f "$SUTRA_PACKAGE_DIR/bin/install.mjs" ]; then
  node "$SUTRA_PACKAGE_DIR/bin/install.mjs" init >/dev/null 2>&1
else
  npx -y github:sankalpasawa/sutra-os init >/dev/null 2>&1
fi

# Case 1: no markers → Write should be BLOCKED (exit 1).
CLAUDE_PROJECT_DIR="$TEST_DIR" \
  TOOL_NAME=Write \
  TOOL_INPUT_file_path="$TEST_DIR/foo.md" \
  bash .claude/hooks/sutra/dispatcher-pretool.sh >/dev/null 2>&1
NO_MARKERS_EXIT=$?
assert_eq "$NO_MARKERS_EXIT" "1" "Write without markers exits 1 (blocked)"

# Case 2: write markers → Write should PASS (exit 0).
mkdir -p .claude
echo "$(date +%s)" > .claude/input-routed
echo "DEPTH=3 TASK=outcome-test TS=$(date +%s)" > .claude/depth-registered
echo "$(date +%s)" > .claude/sutra-deploy-depth5

CLAUDE_PROJECT_DIR="$TEST_DIR" \
  TOOL_NAME=Write \
  TOOL_INPUT_file_path="$TEST_DIR/foo.md" \
  bash .claude/hooks/sutra/dispatcher-pretool.sh >/dev/null 2>&1
WITH_MARKERS_EXIT=$?
assert_eq "$WITH_MARKERS_EXIT" "0" "Write with markers exits 0 (allowed)"

# Case 3: hook log populated.
assert_file ".claude/logs/hook-fires.jsonl" "hook-fires.jsonl written"
assert_count "wc -l < .claude/logs/hook-fires.jsonl | tr -d ' '" 1 200 \
  "hook log has 1..200 entries"

# Case 4: enforcement log of misses populated (from Case 1 block).
assert_file ".enforcement/routing-misses.log" ".enforcement/routing-misses.log written"

# Cleanup.
if [ "$FAILURES" -eq 0 ]; then
  rm -rf "$TEST_DIR"
else
  echo "  (keeping $TEST_DIR for inspection)"
fi

exit_with_summary
