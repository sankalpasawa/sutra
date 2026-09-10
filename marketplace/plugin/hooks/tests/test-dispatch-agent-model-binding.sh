#!/usr/bin/env bash
# test-dispatch-agent-model-binding.sh — dispatch-gate.sh Agent model binding.
#
# Regression cover for the inversion found 2026-09-08: the gate compared the
# policy catalog id in the frozen record (claude-opus-5) against the Agent
# tool's alias enum (opus), so EVERY pinned Agent call BLOCKed and only an
# UNPINNED one passed. Evidence at the time — all three Agent rows ever
# journaled to .enforcement/dispatch-gate.jsonl: model=claude-haiku-4-5 BLOCK,
# model=opus BLOCK, probe="-" ALLOW.
#
# Drives dispatch_gate_check directly against a fabricated repo root so no real
# dispatch record or atom is touched.
set -uo pipefail

PASS=0; FAIL=0
GATE_SRC="$(cd "$(dirname "$0")/../.." && pwd)/hooks/dispatch-gate.sh"
[ -f "$GATE_SRC" ] || { echo "no gate at $GATE_SRC"; exit 2; }

TESTROOT=$(mktemp -d "${TMPDIR:-/tmp}/dg-model-test.XXXXXX")
trap 'rm -rf "$TESTROOT"' EXIT
SID="testsid-0001"

# One fabricated unit. CLASS=2 on purpose: the CLASS>=4 workflow floor is a
# different control with its own test, and would mask these assertions.
mk_unit() { # $1=MODEL  $2=PLACEMENT  $3=PROVIDER
  mkdir -p "$TESTROOT/.sutra/dispatch/$SID" "$TESTROOT/.sutra/atoms/$SID/a-test-01"
  cat > "$TESTROOT/.sutra/dispatch/$SID/dispatch-record" <<EOF
UNIT=test unit
CLASS=2
PROVIDER=$3
MODEL=$1
PLACEMENT=$2
TOUCHES=holding/
WORKROOT=$TESTROOT
ATOM_ID=a-test-01
SESSION=$SID
EOF
  echo '{"status":"open"}' > "$TESTROOT/.sutra/atoms/$SID/a-test-01/atom.json"
}

# Runs the gate in a subshell so each case re-sources with its own env.
run_gate() { # $@ = probes -> echoes "VERDICT reason"
  (
    export CLAUDE_PROJECT_DIR="$TESTROOT" CLAUDE_CODE_SESSION_ID="$SID"
    export DISPATCH_GATE_JOURNAL_OVERRIDE="$TESTROOT/journal.jsonl"
    # shellcheck disable=SC1090
    . "$GATE_SRC" 2>/dev/null
    dispatch_gate_check Agent "$@" >/dev/null 2>&1
    echo "$DISPATCH_GATE_VERDICT"
  )
}

check() { # $1=label $2=expected $3=actual
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); printf '  ok   %s (%s)\n' "$1" "$3"
  else FAIL=$((FAIL+1)); printf '  FAIL %s: expected %s got %s\n' "$1" "$2" "$3"; fi
}

echo "dispatch-gate Agent model binding"

# --- the regression itself: alias must be accepted -------------------------
mk_unit claude-opus-5 INLINE claude
check "alias 'opus' accepted for claude-opus-5"      ALLOW "$(run_gate 'model=opus')"
check "catalog id accepted as compatibility bridge"  ALLOW "$(run_gate 'model=claude-opus-5')"
check "wrong alias still blocks"                     BLOCK "$(run_gate 'model=haiku')"
check "wrong catalog id still blocks"                BLOCK "$(run_gate 'model=claude-haiku-4-5')"

# --- unknown routed id is malformed authority ------------------------------
mk_unit claude-nonesuch-9 INLINE claude
check "unknown routed id blocks"                     BLOCK "$(run_gate 'model=opus')"

# --- unpinned spawn ---------------------------------------------------------
mk_unit claude-sonnet-5 SPAWN claude
check "SPAWN + unpinned blocks"                      BLOCK "$(run_gate 'agent-model-absent=1')"
check "SPAWN + correct pin allows"                   ALLOW "$(run_gate 'model=sonnet')"

mk_unit claude-sonnet-5 INLINE claude
check "INLINE + unpinned allows"                     ALLOW "$(run_gate 'agent-model-absent=1')"

# Non-claude providers do not use this enum; a provider-agnostic rule would
# deadlock them (codex P2, 2026-09-08).
mk_unit gpt-5.4 SPAWN codex
check "non-claude SPAWN + unpinned does not block"   ALLOW "$(run_gate 'agent-model-absent=1')"

echo "  passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ]
