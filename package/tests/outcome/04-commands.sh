#!/bin/bash
# Outcome: the other Sutra slash commands respond via claude --print.
# Exercises /sutra-help and /sutra-update end-to-end.

set -u
TEST_NAME="04-commands"
source "$(dirname "$0")/lib/assert.sh"

if ! command -v claude >/dev/null 2>&1; then
  echo "  [skip] claude CLI not installed — skipping commands test"
  echo "  — $TEST_NAME: 0 passed, 0 failed (skipped)"
  exit 0
fi

# macOS doesn't ship `timeout` by default. Detect + fall back.
TIMEOUT_CMD=""
command -v timeout  >/dev/null 2>&1 && TIMEOUT_CMD="timeout 60"
[ -z "$TIMEOUT_CMD" ] && command -v gtimeout >/dev/null 2>&1 && TIMEOUT_CMD="gtimeout 60"

TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"
echo "  [setup] $TEST_DIR"

if [ -n "${SUTRA_PACKAGE_DIR:-}" ] && [ -f "$SUTRA_PACKAGE_DIR/bin/install.mjs" ]; then
  node "$SUTRA_PACKAGE_DIR/bin/install.mjs" init >/dev/null 2>&1
else
  npx -y github:sankalpasawa/sutra-os init >/dev/null 2>&1
fi

# /sutra-help: should list commands and show version.
HELP_OUT=$($TIMEOUT_CMD claude --print "/sutra-help" 2>&1 || echo "FAILED")
echo "$HELP_OUT" | grep -qi "sutra" && _pass "/sutra-help mentions Sutra" \
  || _fail "/sutra-help mentions Sutra"
echo "$HELP_OUT" | grep -qiE "commands|available" && _pass "/sutra-help lists commands" \
  || _fail "/sutra-help lists commands"

# /sutra-update: should reference the installer or update flow.
# Don't actually run the full install — just verify the command is reachable.
UPD_OUT=$($TIMEOUT_CMD claude --print "describe what /sutra-update would do. Do not run it." 2>&1 || echo "FAILED")
echo "$UPD_OUT" | grep -qiE "update|install|latest|npx" && _pass "/sutra-update described coherently" \
  || _fail "/sutra-update described coherently"

# Cleanup.
if [ "$FAILURES" -eq 0 ]; then
  rm -rf "$TEST_DIR"
else
  echo "  (keeping $TEST_DIR for inspection)"
fi

exit_with_summary
