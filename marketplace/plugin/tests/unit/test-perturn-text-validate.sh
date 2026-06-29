#!/bin/bash
# Unit test: hooks/perturn-text-validate.sh — A4 Input-Routing + Depth + Output-Trace
# TEXT validation (Stop event).
#
# Stop hooks signal a block via {"decision":"block"} JSON on STDOUT and exit 0
# (NOT exit 2). So assertions check stdout for the decision, not the exit code.

set -u
PLUGIN_ROOT="$(cd "$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")" && pwd)"
HOOK="$PLUGIN_ROOT/hooks/perturn-text-validate.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

VALID='[INBOUND·ASSERT · TIMING:now · CHANNEL:in-band · REV:none · RISK:low]
INPUT: do the thing
TYPE: task
EXISTING HOME: none
ROUTE: some skill
FIT CHECK: no change
ACTION: act
TASK: "do the thing"
DEPTH: 3/5 (thorough)
EFFORT: 5 min, 1 file
COST: ~$0.10
IMPACT: small
OS: input-routing (task) > depth 3 > 1 call > gate > done'

# run_case <turn_text> [stop_active=false] [env KEY=VAL ...]
# echoes the hook stdout; sets $RC to exit code.
RC=0
run_case() {
  local atext="$1" active="${2:-false}"; shift 2 || shift $#
  local D; D=$(mktemp -d -t ptv-XXXXXX)
  local TR="$D/t.jsonl"
  jq -nc '{type:"user",message:{role:"user",content:"go"}}' > "$TR"
  jq -nc --arg t "$atext" '{type:"assistant",message:{role:"assistant",content:[{type:"text",text:$t}]}}' >> "$TR"
  local PAYLOAD
  PAYLOAD=$(jq -nc --arg tr "$TR" --argjson a "$active" \
    '{session_id:"t",transcript_path:$tr,stop_hook_active:$a}')
  local OUT
  OUT=$(printf '%s' "$PAYLOAD" | env CLAUDE_PROJECT_DIR="$D" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$@" bash "$HOOK" 2>/dev/null)
  RC=$?
  rm -rf "$D"
  printf '%s' "$OUT"
}

is_block() { printf '%s' "$1" | grep -q '"decision": "block"'; }

# 1) fully valid turn -> pass (no block)
OUT=$(run_case "$VALID"); if is_block "$OUT"; then _no "valid turn passes"; else _ok "valid turn passes"; fi

# 2) missing Output Trace -> block, message names it
NO_TRACE="${VALID/OS: input-routing (task) > depth 3 > 1 call > gate > done/}"
OUT=$(run_case "$NO_TRACE"); if is_block "$OUT" && printf '%s' "$OUT" | grep -qi "Output Trace"; then _ok "missing trace blocks"; else _no "missing trace should block w/ trace msg: $OUT"; fi

# 3) missing DEPTH line -> block
NO_DEPTH="${VALID/DEPTH: 3\/5 (thorough)/}"
OUT=$(run_case "$NO_DEPTH"); if is_block "$OUT" && printf '%s' "$OUT" | grep -qi "Depth"; then _ok "missing DEPTH blocks"; else _no "missing DEPTH should block: $OUT"; fi

# 4) DEPTH out of range -> block
BAD_DEPTH="${VALID/DEPTH: 3\/5 (thorough)/DEPTH: 7\/5 (impossible)}"
OUT=$(run_case "$BAD_DEPTH"); if is_block "$OUT" && printf '%s' "$OUT" | grep -qi "range"; then _ok "DEPTH out of range blocks"; else _no "DEPTH=7 should block: $OUT"; fi

# 5) TYPE not in enum -> block
BAD_TYPE="${VALID/TYPE: task/TYPE: banana}"
OUT=$(run_case "$BAD_TYPE"); if is_block "$OUT" && printf '%s' "$OUT" | grep -qi "TYPE"; then _ok "bad TYPE blocks"; else _no "TYPE=banana should block: $OUT"; fi

# 6) missing ROUTE -> block
NO_ROUTE="${VALID/ROUTE: some skill/}"
OUT=$(run_case "$NO_ROUTE"); if is_block "$OUT" && printf '%s' "$OUT" | grep -qi "ROUTE"; then _ok "missing ROUTE blocks"; else _no "missing ROUTE should block: $OUT"; fi

# 7) compact form 'INPUT ... (task)' (no explicit TYPE line) -> pass
COMPACT='[INBOUND·QUERY · TIMING:now · CHANNEL:in-band · REV:none · RISK:low]
INPUT: quick question (task)
ROUTE: answer inline
TASK: "answer"
DEPTH: 1/5
EFFORT: trivial
COST: ~$0
IMPACT: none
OS: input-routing (task) > depth 1 > 0 calls > gate > done'
OUT=$(run_case "$COMPACT"); if is_block "$OUT"; then _no "compact form should pass: $OUT"; else _ok "compact form passes"; fi

# 8) stop_hook_active=true with broken blocks -> pass (loop safety)
OUT=$(run_case "no blocks here at all" true); if is_block "$OUT"; then _no "stop_hook_active should pass"; else _ok "stop_hook_active loop-safety passes"; fi

# 9) kill-switch -> pass
OUT=$(run_case "no blocks here" false PERTURN_TEXT_VALIDATE_DISABLED=1); if is_block "$OUT"; then _no "kill-switch should pass"; else _ok "kill-switch disables"; fi

# 10) override -> pass
OUT=$(run_case "no blocks here" false PERTURN_TEXT_ACK=1); if is_block "$OUT"; then _no "ACK override should pass"; else _ok "ACK override passes"; fi

# 11) ASCII-boxed depth block -> pass (declutter strips pipes)
BOXED='[INBOUND·ASSERT · TIMING:now · CHANNEL:in-band · REV:none · RISK:low]
INPUT: boxed
TYPE: task
ROUTE: x
| TASK: "boxed task"                                    |
| DEPTH: 2/5 (considered)                               |
| EFFORT: 10 min                                        |
| COST: ~$0.05                                          |
| IMPACT: minor                                         |
OS: a > b > c'
OUT=$(run_case "$BOXED"); if is_block "$OUT"; then _no "boxed depth should pass: $OUT"; else _ok "boxed depth passes"; fi

# 12) empty turn text -> pass (fail-open / skip)
OUT=$(run_case ""); if is_block "$OUT"; then _no "empty turn should pass"; else _ok "empty turn fail-open passes"; fi

echo ""
echo "perturn-text-validate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
