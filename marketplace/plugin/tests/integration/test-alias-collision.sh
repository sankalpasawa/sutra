#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Integration test — shell-alias collision regression (v1.7.1 / Option E).
#
# Reproduces dogfood Finding #12: a user-defined `alias sutra=...` (or function,
# or hash, or PATH shadow) that WINS bare-name resolution in the user's shell
# must NOT intercept plugin internal self-invocation.
#
# Under v1.7.0 and earlier, `commands/*.md` used `!sutra <sub>`, which routes
# through shell name resolution — so an alias wins and the plugin's binary
# never runs.  Under v1.7.1 (Option E), every internal call path resolves the
# plugin binary by absolute path (`${CLAUDE_PLUGIN_ROOT}/bin/sutra`), so the
# alias is completely bypassed.
#
# This test installs a hostile `alias sutra='echo HIJACKED && exit 42'` into
# a subshell and invokes the plugin's activation path (scripts/start.sh,
# which is what `bin/sutra start` ultimately dispatches to).  It asserts:
#
#   1. Exit code is 0                    (activation succeeded)
#   2. "HIJACKED" is not in captured output  (alias did not fire)
#   3. .claude/sutra-project.json exists    (onboard ran)
#
# If any of these fail, the alias-collision class has reopened.
# -----------------------------------------------------------------------------

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
START_SH="${PLUGIN_ROOT}/scripts/start.sh"

# Isolated sandbox so the test never pollutes the developer's real project.
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

export CLAUDE_PLUGIN_ROOT="${PLUGIN_ROOT}"
export CLAUDE_PROJECT_DIR="${WORK}/project"
export SUTRA_HOME="${WORK}/sutra-home"
mkdir -p "${CLAUDE_PROJECT_DIR}/.claude" "${SUTRA_HOME}"

PASS=0
FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# --- Run activation in a subshell that has the hostile alias defined ---------
# `bash -c` with `shopt -s expand_aliases` forces non-interactive alias expansion
# so the alias is actually a threat, exactly mirroring zsh/bash interactive
# shells where aliases expand. If the plugin's activation path ever falls back
# to bare `sutra <sub>`, the alias wins, `HIJACKED` prints, and exit code is 42.
CAPTURE_FILE="${WORK}/activation.out"
set +e
bash -c '
  shopt -s expand_aliases
  alias sutra="echo HIJACKED && exit 42"
  bash "$0" "$@"
' "${START_SH}" >"${CAPTURE_FILE}" 2>&1
RC=$?
set -e

# --- Assertion 1: exit code ---------------------------------------------------
if [ "${RC}" -eq 0 ]; then
  _ok "activation exit code 0 (alias did not hijack)"
else
  _no "activation exit code ${RC} (expected 0)"
fi

# --- Assertion 2: no HIJACKED in output --------------------------------------
if grep -q "HIJACKED" "${CAPTURE_FILE}"; then
  _no "captured output contains HIJACKED — alias fired"
  echo "      --- captured output ---"
  sed 's/^/      /' "${CAPTURE_FILE}"
  echo "      ------------------------"
else
  _ok "no HIJACKED in captured output"
fi

# --- Assertion 3: .claude/sutra-project.json exists --------------------------
if [ -f "${CLAUDE_PROJECT_DIR}/.claude/sutra-project.json" ]; then
  _ok ".claude/sutra-project.json written"
else
  _no ".claude/sutra-project.json missing — onboard did not run"
fi

echo ""
echo "test-alias-collision: ${PASS} passed, ${FAIL} failed"
exit "${FAIL}"
