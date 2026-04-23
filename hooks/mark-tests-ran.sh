#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# mark-tests-ran.sh — run a test command and write .claude/ran-tests marker
# ═══════════════════════════════════════════════════════════════════════════════
# Ported from holding/hooks/mark-tests-ran.sh (commit 31dcaa3 in asawa-holding).
# Usage:
#   bash hooks/mark-tests-ran.sh <command...>
# ═══════════════════════════════════════════════════════════════════════════════

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
MARKER_FILE="$REPO_ROOT/.claude/ran-tests"
mkdir -p "$REPO_ROOT/.claude"

if [ $# -eq 0 ]; then
  cat >&2 <<EOF
usage: bash hooks/mark-tests-ran.sh <command...>
EOF
  exit 2
fi

CMD_STR="$*"
TS=$(date +%s)

echo "→ running: $CMD_STR"
"$@"
EXIT=$?

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
# Marker file .claude/ran-tests. Freshness read by pre-commit-test-gate.
#
### 2. Adoption mechanism
# Developer invocation: `bash hooks/mark-tests-ran.sh <cmd>`.
#
### 3. Monitoring / escalation
# Stale-marker blocks flagged in test-gate.jsonl.
#
### 4. Iteration trigger
# Kept in sync with holding/hooks/mark-tests-ran.sh.
#
### 5. DRI
# CEO of Sutra.
#
### 6. Decommission criteria
# Retire when CI runs tests server-side and local marker is redundant.
