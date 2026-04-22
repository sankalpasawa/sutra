#!/bin/bash
# Outcome: /sutra command actually works when Claude Code launches.
# Uses `claude --print` (non-interactive, skips trust prompt) to exercise
# the command end-to-end.

set -u
TEST_NAME="02-activation"
source "$(dirname "$0")/lib/assert.sh"

# Bail gracefully if claude CLI isn't available (CI without Claude Code).
if ! command -v claude >/dev/null 2>&1; then
  echo "  [skip] claude CLI not installed — skipping activation test"
  echo "  — $TEST_NAME: 0 passed, 0 failed (skipped)"
  exit 0
fi

TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"
echo "  [setup] $TEST_DIR"

# Install.
if [ -n "${SUTRA_PACKAGE_DIR:-}" ] && [ -f "$SUTRA_PACKAGE_DIR/bin/install.mjs" ]; then
  node "$SUTRA_PACKAGE_DIR/bin/install.mjs" init >/dev/null 2>&1
else
  npx -y github:sankalpasawa/sutra-os init >/dev/null 2>&1
fi

# Run /sutra via claude --print (skips trust prompt, returns stdout).
# Timeout guards against unexpected hangs.
# macOS doesn't ship `timeout` by default. Detect + fall back gracefully.
TIMEOUT_CMD=""
command -v timeout  >/dev/null 2>&1 && TIMEOUT_CMD="timeout 60"
[ -z "$TIMEOUT_CMD" ] && command -v gtimeout >/dev/null 2>&1 && TIMEOUT_CMD="gtimeout 60"
OUT=$($TIMEOUT_CMD claude --print "/sutra" 2>&1 || echo "CLAUDE_RUN_FAILED")

# Assertions on the output.
echo "  [/sutra output — first 200 chars]"
printf '  %s\n' "${OUT:0:200}..."

if [ "$OUT" = "CLAUDE_RUN_FAILED" ] || [ -z "$OUT" ]; then
  _fail "claude --print /sutra returned output"
else
  _pass "claude --print /sutra returned output"
fi

# Activation banner should mention Sutra.
echo "$OUT" | grep -qi "sutra" && _pass "output mentions Sutra" || _fail "output mentions Sutra"

# Should reference install state or version.
echo "$OUT" | grep -qiE "installed|version|active" && _pass "output shows install/version state" \
  || _fail "output shows install/version state"

# Cleanup.
if [ "$FAILURES" -eq 0 ]; then
  rm -rf "$TEST_DIR"
else
  echo "  (keeping $TEST_DIR for inspection)"
fi

exit_with_summary
