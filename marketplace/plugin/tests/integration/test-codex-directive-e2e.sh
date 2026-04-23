#!/bin/bash
# Integration test: PROTO-019 v2 end-to-end
#
# Simulates the full directive → block → verdict → unblock loop:
#   1. UserPromptSubmit with "use codex to review X"  -> detect writes marker
#   2. PreToolUse Edit                                -> gate blocks (exit 2)
#   3. Verdict file with matching DIRECTIVE-ID + PASS  written externally
#   4. PreToolUse Edit again                          -> gate clears marker, allows
#
# Also exercises the FAIL path and override.

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
DETECT="$PLUGIN_ROOT/hooks/codex-directive-detect.sh"
GATE="$PLUGIN_ROOT/hooks/codex-directive-gate.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# ── Scenario A: happy path — directive → block → PASS verdict → unblock ──
{
  D=$(mktemp -d -t codex-e2e-happy-XXXXXX)
  mkdir -p "$D/.claude"

  # Step 1: founder says "use codex to review the migration plan"
  P=$(jq -nc '{prompt:"use codex to review the migration plan",hook_event_name:"UserPromptSubmit"}')
  printf '%s' "$P" | CLAUDE_PROJECT_DIR="$D" bash "$DETECT"

  if [ ! -f "$D/.claude/codex-directive-pending" ]; then
    _no "[A] detect did not write marker on positive prompt"
    rm -rf "$D"
  else
    _ok "[A] step 1: directive detected, marker written"

    DIRECTIVE_ID=$(grep DIRECTIVE-ID "$D/.claude/codex-directive-pending" | awk '{print $2}')

    # Step 2: Claude tries to Edit — gate must block
    PAYLOAD=$(jq -nc '{tool_name:"Edit",tool_input:{file_path:"/tmp/foo.md"}}')
    printf '%s' "$PAYLOAD" | CLAUDE_PROJECT_DIR="$D" bash "$GATE" 2>/dev/null
    rc=$?
    if [ "$rc" -eq 2 ] && [ -f "$D/.claude/codex-directive-pending" ]; then
      _ok "[A] step 2: gate blocked Edit with no verdict (exit 2)"
    else
      _no "[A] step 2: gate allowed Edit unexpectedly (exit $rc)"
    fi

    # Step 3: /codex review writes verdict with matching DIRECTIVE-ID + PASS
    mkdir -p "$D/.enforcement/codex-reviews"
    cat > "$D/.enforcement/codex-reviews/plan-review.md" <<EOF
# Codex review

DIRECTIVE-ID: $DIRECTIVE_ID
CODEX-VERDICT: PASS

Design looks fine. Ship it.
EOF
    _ok "[A] step 3: verdict file written externally with matching DIRECTIVE-ID"

    # Step 4: Claude retries Edit — gate clears marker and allows
    printf '%s' "$PAYLOAD" | CLAUDE_PROJECT_DIR="$D" bash "$GATE" 2>/dev/null
    rc=$?
    if [ "$rc" -eq 0 ] && [ ! -f "$D/.claude/codex-directive-pending" ]; then
      _ok "[A] step 4: PASS verdict cleared marker, Edit allowed"
    else
      _no "[A] step 4: exit=$rc marker_still=$([ -f $D/.claude/codex-directive-pending ] && echo yes || echo no)"
    fi

    # Verify audit trail has both detection + clearance
    if grep -q directive-detected "$D/.enforcement/codex-reviews/gate-log.jsonl" 2>/dev/null \
       && grep -q directive-cleared "$D/.enforcement/codex-reviews/gate-log.jsonl" 2>/dev/null; then
      _ok "[A] audit trail: detection + clearance both logged"
    else
      _no "[A] audit trail incomplete"
    fi
    rm -rf "$D"
  fi
}

# ── Scenario B: FAIL verdict keeps blocking ──
{
  D=$(mktemp -d -t codex-e2e-fail-XXXXXX)
  mkdir -p "$D/.claude"

  P=$(jq -nc '{prompt:"codex should check the security model"}')
  printf '%s' "$P" | CLAUDE_PROJECT_DIR="$D" bash "$DETECT"
  DIRECTIVE_ID=$(grep DIRECTIVE-ID "$D/.claude/codex-directive-pending" 2>/dev/null | awk '{print $2}')

  if [ -z "$DIRECTIVE_ID" ]; then
    _no "[B] detect failed for 'codex should check'"
  else
    mkdir -p "$D/.enforcement/codex-reviews"
    cat > "$D/.enforcement/codex-reviews/sec-review.md" <<EOF
DIRECTIVE-ID: $DIRECTIVE_ID
CODEX-VERDICT: FAIL

Critical: injection vulnerability at line 42.
EOF

    PAYLOAD=$(jq -nc '{tool_name:"Write",tool_input:{}}')
    printf '%s' "$PAYLOAD" | CLAUDE_PROJECT_DIR="$D" bash "$GATE" 2>/dev/null
    rc=$?
    if [ "$rc" -eq 2 ] && [ -f "$D/.claude/codex-directive-pending" ]; then
      _ok "[B] FAIL verdict keeps blocking (marker survives)"
    else
      _no "[B] FAIL scenario: exit=$rc"
    fi
  fi
  rm -rf "$D"
}

# ── Scenario C: override unblocks ──
{
  D=$(mktemp -d -t codex-e2e-override-XXXXXX)
  mkdir -p "$D/.claude"

  P=$(jq -nc '{prompt:"use codex to audit the rollout"}')
  printf '%s' "$P" | CLAUDE_PROJECT_DIR="$D" bash "$DETECT"

  if [ -f "$D/.claude/codex-directive-pending" ]; then
    PAYLOAD=$(jq -nc '{tool_name:"Edit",tool_input:{}}')
    printf '%s' "$PAYLOAD" | \
      CLAUDE_PROJECT_DIR="$D" CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON="founder-verified-manually" \
      bash "$GATE" 2>/dev/null
    rc=$?
    if [ "$rc" -eq 0 ] && [ ! -f "$D/.claude/codex-directive-pending" ] \
       && grep -q founder-verified-manually "$D/.enforcement/codex-reviews/gate-log.jsonl" 2>/dev/null; then
      _ok "[C] override clears marker + logs reason"
    else
      _no "[C] override path: exit=$rc"
    fi
  else
    _no "[C] detect failed for 'use codex to audit'"
  fi
  rm -rf "$D"
}

echo ""
echo "e2e: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
