#!/bin/bash
# Outcome: a fresh install via npx produces the expected Sutra layout.
# Tests the external-user first-run experience end-to-end.

set -u
TEST_NAME="01-install"
source "$(dirname "$0")/lib/assert.sh"

TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"

echo "  [setup] $TEST_DIR"

# Action: run the installer the same way an external user would.
# Prefer local package if SUTRA_PACKAGE_DIR is set (for in-repo dev); else pull from github.
if [ -n "${SUTRA_PACKAGE_DIR:-}" ] && [ -f "$SUTRA_PACKAGE_DIR/bin/install.mjs" ]; then
  node "$SUTRA_PACKAGE_DIR/bin/install.mjs" init >/tmp/sutra-install-$$.log 2>&1
else
  npx -y github:sankalpasawa/sutra-os init >/tmp/sutra-install-$$.log 2>&1
fi
INSTALL_EXIT=$?

# Install must succeed.
assert_eq "$INSTALL_EXIT" "0" "installer exits 0"

# Core project files present (at repo root).
assert_file "CLAUDE.md"                  "CLAUDE.md rendered"
assert_file "TODO.md"                    "TODO.md rendered"

# OS directory: governance docs + state templates live together in os/.
assert_dir  "os"                         "os/ directory created"
assert_file "os/STATUS.md"               "os/STATUS.md present"
assert_file "os/METRICS.md"              "os/METRICS.md present"
assert_file "os/OKRs.md"                 "os/OKRs.md present"
assert_file "os/SUTRA-CONFIG.md"         "os/SUTRA-CONFIG.md present"

# Claude Code wiring.
assert_dir  ".claude"                    ".claude/ directory created"
assert_file ".claude/settings.json"      ".claude/settings.json present"
assert_file ".claude/sutra-version"      ".claude/sutra-version pin present"
assert_dir  ".claude/hooks/sutra"        ".claude/hooks/sutra/ dir created"
assert_dir  ".claude/commands"           ".claude/commands/ dir created"

# Hook count in expected range (tier 2 = product, ~29-30 hooks).
assert_count "ls .claude/hooks/sutra/*.sh 2>/dev/null | wc -l | tr -d ' '" 20 35 \
  "hook count 20..35"

# OS docs count in expected range — governance + templates together in os/.
assert_count "ls os/*.md 2>/dev/null | wc -l | tr -d ' '" 15 30 \
  "os/ docs count 15..30"

# Version pin is valid semver.
VERSION=$(head -1 .claude/sutra-version 2>/dev/null | tr -d '[:space:]')
assert_semver "$VERSION" "version pin is semver"

# Settings JSON is valid.
if command -v jq >/dev/null 2>&1; then
  assert_exit 'jq empty .claude/settings.json' 0 "settings.json is valid JSON"
fi

# Cleanup on success.
if [ "$FAILURES" -eq 0 ]; then
  rm -rf "$TEST_DIR" /tmp/sutra-install-$$.log
else
  echo "  (keeping $TEST_DIR + /tmp/sutra-install-$$.log for inspection)"
fi

exit_with_summary
