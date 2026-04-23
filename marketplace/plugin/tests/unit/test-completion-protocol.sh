#!/bin/bash
# Unit test: completion-protocol-check.sh
# Covers: each of 4 terminal states, missing STATUS, incomplete escalation,
# non-Task tool skip, kill-switch, override, config-disabled path.

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
HOOK="$PLUGIN_ROOT/hooks/completion-protocol-check.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

run_hook() {
  local response="$1" tool="${2:-Task}" ack="${3:-0}" ack_reason="${4:-}" disabled="${5:-}" config_enabled="${6:-true}" TDIR="$7"

  if [ "$config_enabled" = "false" ]; then
    mkdir -p "$TDIR/.sutra"
    echo "SUTRA_COMPLETION_PROTOCOL_ENABLED=false" > "$TDIR/.sutra/config.env"
  fi

  local payload
  payload=$(jq -nc --arg t "$tool" --arg r "$response" \
    '{tool_name:$t,tool_input:{subagent_type:"test"},tool_response:$r}')

  printf '%s' "$payload" | \
    CLAUDE_PROJECT_DIR="$TDIR" \
    HOME="$TDIR" \
    COMPLETION_PROTOCOL_ACK="$ack" \
    COMPLETION_PROTOCOL_ACK_REASON="$ack_reason" \
    COMPLETION_PROTOCOL_DISABLED="$disabled" \
    bash "$HOOK" 2>"$TDIR/stderr.txt"
  echo $?
}

{ T=$(mktemp -d); rc=$(run_hook "work done

STATUS: DONE" "Task" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q '"state":"DONE"' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null; then
    _ok "STATUS: DONE → exit 0 + log ok"
  else
    _no "DONE: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "done but concerns

STATUS: DONE_WITH_CONCERNS" "Task" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q '"state":"DONE_WITH_CONCERNS"' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null; then
    _ok "STATUS: DONE_WITH_CONCERNS"
  else
    _no "DWC: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "cannot proceed

STATUS: BLOCKED
REASON: missing codex binary
ATTEMPTED: brew install
RECOMMENDATION: install manually" "Task" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q '"state":"BLOCKED"' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null \
     && grep -q 'completion-protocol-ok' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null; then
    _ok "BLOCKED + full escalation → ok"
  else
    _no "BLOCKED full: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "stopped

STATUS: BLOCKED
ATTEMPTED: x
RECOMMENDATION: y" "Task" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q 'completion-protocol-incomplete-escalation' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null \
     && grep -q 'REASON' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null; then
    _ok "BLOCKED missing REASON → warn + log incomplete"
  else
    _no "BLOCKED missing REASON: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "need info

STATUS: NEEDS_CONTEXT
REASON: ambiguous
ATTEMPTED: read memory
RECOMMENDATION: clarify" "Task" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q '"state":"NEEDS_CONTEXT"' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null \
     && grep -q 'completion-protocol-ok' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null; then
    _ok "NEEDS_CONTEXT + full escalation → ok"
  else
    _no "NEEDS_CONTEXT full: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "just a summary" "Task" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q 'completion-protocol-missing' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null \
     && grep -q "missing STATUS" "$T/stderr.txt" 2>/dev/null; then
    _ok "no STATUS → warn + log missing"
  else
    _no "missing STATUS: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "doesn't matter" "Edit" "0" "" "" "true" "$T")
  if [ "$rc" = "0" ] && [ ! -f "$T/.enforcement/completion-protocol.jsonl" ]; then
    _ok "non-Task tool → silent pass, no log"
  else
    _no "non-Task: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "no status" "Task" "0" "" "1" "true" "$T")
  if [ "$rc" = "0" ] && [ ! -f "$T/.enforcement/completion-protocol.jsonl" ]; then
    _ok "kill-switch env → silent pass"
  else
    _no "kill-switch env: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "no status" "Task" "0" "" "" "false" "$T")
  if [ "$rc" = "0" ] && [ ! -f "$T/.enforcement/completion-protocol.jsonl" ]; then
    _ok "config SUTRA_COMPLETION_PROTOCOL_ENABLED=false → silent"
  else
    _no "config disabled: rc=$rc"
  fi
  rm -rf "$T"; }

{ T=$(mktemp -d); rc=$(run_hook "no status" "Task" "1" "legitimate-data-return" "" "true" "$T")
  if [ "$rc" = "0" ] && grep -q 'completion-protocol-override' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null \
     && grep -q 'legitimate-data-return' "$T/.enforcement/completion-protocol.jsonl" 2>/dev/null; then
    _ok "override → exit 0 + log override"
  else
    _no "override: rc=$rc"
  fi
  rm -rf "$T"; }

echo ""
echo "completion-protocol: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
