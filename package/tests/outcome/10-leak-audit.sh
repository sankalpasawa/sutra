#!/bin/bash
# Outcome: installed Sutra surface has zero leaks of holding-company brand strings
# that an external user would see.
# Exempt: deep os-core/ governance docs (Posture 1 per founder direction 2026-04-19
# — authentic origin attribution is allowed inside read-only governance docs).
# Targeted: user-facing command files, templates, CLAUDE.md, installer banner.

set -u
TEST_NAME="10-leak-audit"
source "$(dirname "$0")/lib/assert.sh"

TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"

echo "  [setup] $TEST_DIR"

# Install.
if [ -n "${SUTRA_PACKAGE_DIR:-}" ] && [ -f "$SUTRA_PACKAGE_DIR/bin/install.mjs" ]; then
  node "$SUTRA_PACKAGE_DIR/bin/install.mjs" init >/tmp/install-log-$$.txt 2>&1
else
  npx -y github:sankalpasawa/sutra-os init >/tmp/install-log-$$.txt 2>&1
fi

# User-visible surfaces to audit.
# NOT auditing .claude/os/ (Posture 1 — governance docs can reference Asawa as origin).
assert_nostring "asawa" "CLAUDE.md" \
  "no 'asawa' in CLAUDE.md (user opens this)"
assert_nostring "asawa" "TODO.md" \
  "no 'asawa' in TODO.md"
assert_nostring "asawa" "os/SUTRA-CONFIG.md" \
  "no 'asawa' in os/SUTRA-CONFIG.md"
assert_nostring "asawa" ".claude/commands" \
  "no 'asawa' in .claude/commands/ (slash-command files)"
assert_nostring "dayflow" ".claude/commands" \
  "no 'dayflow' in .claude/commands/"

# Installer banner output — what the user sees during install.
assert_nostring "asawa" "/tmp/install-log-$$.txt" \
  "no 'asawa' in installer banner"

# Os docs at user level (top-level os/, NOT .claude/os/).
# These templates get rendered into user project — must be generic.
assert_nostring "asawa" "os/STATUS.md" \
  "no 'asawa' in os/STATUS.md template"
assert_nostring "asawa" "os/METRICS.md" \
  "no 'asawa' in os/METRICS.md template"
assert_nostring "asawa" "os/OKRs.md" \
  "no 'asawa' in os/OKRs.md template"

# Cleanup.
if [ "$FAILURES" -eq 0 ]; then
  rm -rf "$TEST_DIR" /tmp/install-log-$$.txt
else
  echo "  (keeping $TEST_DIR + /tmp/install-log-$$.txt for inspection)"
fi

exit_with_summary
