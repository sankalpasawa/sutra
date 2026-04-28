#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# mark-tests-ran.sh — run a test command and write the .claude/ran-tests marker
# ═══════════════════════════════════════════════════════════════════════════════
# Usage:
#   bash holding/hooks/mark-tests-ran.sh <command...>
#
# Examples:
#   bash holding/hooks/mark-tests-ran.sh bash holding/hooks/tests/test-subagent-os-contract.sh
#   bash holding/hooks/mark-tests-ran.sh npm test
#   bash holding/hooks/mark-tests-ran.sh make check
#
# Runs the command inline, captures exit code, writes:
#   .claude/ran-tests  (ts=<unix>, exit=<code>, cmd=<command>)
#
# Exit code: propagates the wrapped command's exit (so CI/dev loops see failures).
# The marker is always written so pre-commit-test-gate can surface the failure.
# ═══════════════════════════════════════════════════════════════════════════════

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
MARKER_FILE="$REPO_ROOT/.claude/ran-tests"
mkdir -p "$REPO_ROOT/.claude"

if [ $# -eq 0 ]; then
  cat >&2 <<EOF
usage: bash holding/hooks/mark-tests-ran.sh <command...>

Examples:
  bash holding/hooks/mark-tests-ran.sh bash holding/hooks/tests/test-subagent-os-contract.sh
  bash holding/hooks/mark-tests-ran.sh npm test
EOF
  exit 2
fi

CMD_STR="$*"
TS=$(date +%s)

echo "→ running: $CMD_STR"
"$@"
EXIT=$?

# Sanitize cmd for marker file (strip newlines, quotes).
SAFE_CMD=$(printf '%s' "$CMD_STR" | tr -d '"\\' | tr '\n\r' '  ')

cat > "$MARKER_FILE" <<EOF
ts=$TS
exit=$EXIT
cmd=$SAFE_CMD
EOF

if [ "$EXIT" -eq 0 ]; then
  echo "✔ marker written: $MARKER_FILE (exit=0, ts=$TS)"
else
  echo "✘ marker written: $MARKER_FILE (exit=$EXIT, ts=$TS) — pre-commit-test-gate will block until fixed" >&2
fi

exit "$EXIT"

## Operationalization
#
### 1. Measurement mechanism
# Marker file .claude/ran-tests per repo. Freshness read by pre-commit-test-gate.
# Telemetry flows through the gate hook (not this helper).
#
### 2. Adoption mechanism
# Developer invocation: `bash holding/hooks/mark-tests-ran.sh <cmd>`.
# Documented in CLAUDE.md pre-commit section + pre-commit-test-gate block message.
#
### 3. Monitoring / escalation
# If marker is routinely stale at commit time, adoption is low — review dev loop.
#
### 4. Iteration trigger
# TTL tune in pre-commit-test-gate, not here. This is a pure helper.
#
### 5. DRI
# CEO of Asawa (governance-layer helper paired with pre-commit-test-gate).
#
### 6. Decommission criteria
# Retire when CI runs tests server-side and the local marker becomes redundant.
