#!/bin/bash
# test-mdiff.sh - runtime/steps/markers_diff.sh (stop.markers_diff, MVP-1b).
#
# The step is run DIRECTLY with the environment bin/sutra-turn gives a native
# step (D3: SUTRA_STEP_ID / SUTRA_TURN_ID / SUTRA_EVENT / SUTRA_LEDGER_*), so
# the asserts are about the step's own rows, not about the 24 legacy Stop
# hooks around it. The whole-event integration (stdout and stderr of the Stop
# event byte-identical with and without the step) is case 6 of
# test-markers-step.sh.
#
# Cases (BRIEF section 4, M1-M5, plus the facts-missing branch of D17):
#   M1  last_assistant_message carries a header equal to the facts
#       -> 9 marker_diff rows, every one equal:true, header_parsed:true,
#          one turns.jsonl line, no diffs.jsonl line, nothing on stdout/stderr
#   M2  header with a different RISK -> that row equal:false, one diffs.jsonl
#       line (a gate field), the RESOLUTION/SCOPE rows never reach diffs.jsonl
#   M3  no header anywhere -> one row header_parsed:false, no turns.jsonl line
#   M4  flag off -> one marker_flag row (mode off) and no marker_diff row
#   M5  no last_assistant_message, a transcript_path fixture whose last
#       assistant line carries a plain-dot header -> parsed from the transcript
#   M6  facts file absent -> one row facts_present:false, nothing else
#
# bash 3.2 compatible.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-mdiff.sh

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
STEP="$PLUGIN_ROOT/runtime/steps/markers_diff.sh"

failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }

if [ ! -x "$STEP" ]; then
  fail "markers_diff.sh missing or not executable at $STEP"
  echo "failed=$failed"; exit 1
fi
command -v jq >/dev/null 2>&1 || { fail "jq required"; echo "failed=$failed"; exit 1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-mdiff.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

HDR_DOT='[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]'
HDR_PLAIN='[INBOUND.DIRECT . TIMING:now . CHANNEL:in-band . REV:reversible . RISK:low]'
HDR_RISK='[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:high]'
FLOW_LINE='| [2] RESOLVE: FOLLOW test-strategy (scope platform) | CONSTRUCT   |'
DEPTH_LINE='DEPTH: 5/5 (exhaustive)'

# mk_case <name> <flag on|off|none> -> sets C_PROJ C_HOME C_CANON C_FLAT C_SID C_TURN
mk_case() {
  C_SID="sid-$1"; C_TURN="turn-$1"
  C_PROJ="$WORK/$1/proj"; C_HOME="$WORK/$1/home"
  mkdir -p "$C_PROJ/.claude/sessions/$C_SID" "$C_PROJ/.sutra/turn/$C_SID" "$C_HOME"
  case "$2" in
    on)  printf 'on\n'  > "$C_HOME/.sutra-runtime-markers" ;;
    off) printf 'off\n' > "$C_HOME/.sutra-runtime-markers" ;;
  esac
  C_CANON="$WORK/$1/canon.jsonl"; C_FLAT="$WORK/$1/flat.jsonl"
  : > "$C_CANON"; : > "$C_FLAT"
}

# write_facts: the frozen facts the UPS step would have written for this turn
write_facts() {
  jq -n --arg t "$C_TURN" --arg s "$C_SID" '{
    turn_id:$t, session_id:$s, mode:"on", prompt_sha256:"x",
    classify:{verb:"DIRECT", timing:"now", channel:"in-band", reversibility:"reversible", decision_risk:"low"},
    resolve:{resolution:"FOLLOW:test-strategy", scope:"platform", score:4, degraded:false},
    factors:null, depth:{n:5, rubric:"profile-company"}, type:"direction", slug:"fix-the-login-bug",
    markers:{"input-routed":"written","depth-registered":"written","flow-classified":"written","flow-type-resolved":"written"},
    degraded:[]}' > "$C_PROJ/.sutra/turn/$C_SID/$C_TURN.facts.json"
}

# run_step <stdin-json-file> -> sets R_RC, R_OUT, R_ERR
run_step() {
  # env -u: a developer's shell (or a Claude Code session) exports its own
  # CLAUDE_CODE_SESSION_ID, and marker-lib prefers that over the stdin sid.
  R_OUT="$(env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID \
    HOME="$C_HOME" CLAUDE_PROJECT_DIR="$C_PROJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
    SUTRA_STEP_ID=stop.markers_diff SUTRA_TURN_ID="$C_TURN" SUTRA_EVENT=Stop \
    SUTRA_LEDGER_CANON="$C_CANON" SUTRA_LEDGER_FLAT="$C_FLAT" \
    "$STEP" < "$1" 2> "$WORK/err.txt")"
  R_RC=$?
  R_ERR="$(cat "$WORK/err.txt")"
}

stdin_with_message() {  # <file> <message-text>
  jq -n --arg s "$C_SID" --arg m "$2" --arg cwd "$C_PROJ" \
    '{session_id:$s, hook_event_name:"Stop", stop_hook_active:false, last_assistant_message:$m, cwd:$cwd}' > "$1"
}

count_rows() { jq -c "select($2)" "$1" 2>/dev/null | wc -l | tr -d ' '; }  # <file> <jq filter>

common_asserts() {  # <case>
  [ "$R_RC" -eq 0 ] || fail "$1: exit $R_RC (want 0)"
  [ -z "$R_OUT" ] || fail "$1: stdout not empty: $R_OUT"
  [ -z "$R_ERR" ] || fail "$1: stderr not empty: $R_ERR"
  [ "$(count_rows "$C_FLAT" '.kind=="marker_flag"')" = "1" ] || fail "$1: marker_flag rows in flat: want 1"
  [ "$(count_rows "$C_CANON" '.kind=="marker_flag"')" = "1" ] || fail "$1: marker_flag rows in canon: want 1"
}

# ------------------------------------------------------------------ M1 --
mk_case m1 on; write_facts
stdin_with_message "$WORK/m1.json" "$HDR_DOT
some prose
$FLOW_LINE
$DEPTH_LINE"
run_step "$WORK/m1.json"
common_asserts M1
n="$(count_rows "$C_FLAT" '.kind=="marker_diff"')"
[ "$n" = "9" ] && pass "M1: 9 marker_diff rows" || fail "M1: marker_diff rows: expected 9 got $n"
n="$(count_rows "$C_FLAT" '.kind=="marker_diff" and .equal==true')"
[ "$n" = "9" ] && pass "M1: every row equal:true" || { fail "M1: equal:true rows: expected 9 got $n"; jq -c 'select(.kind=="marker_diff" and .equal==false)' "$C_FLAT"; }
n="$(count_rows "$C_FLAT" '.kind=="marker_diff" and .header_parsed==true')"
[ "$n" = "9" ] && pass "M1: header_parsed:true on every row" || fail "M1: header_parsed:true rows: expected 9 got $n"
n="$(count_rows "$C_FLAT" '.kind=="marker_diff" and .gate_field==true')"
[ "$n" = "7" ] && pass "M1: 7 gate fields (6 header + DEPTH)" || fail "M1: gate_field rows: expected 7 got $n"
[ "$(count_rows "$C_PROJ/.sutra/shadow/markers/turns.jsonl" '.kind=="marker_diff_turn"')" = "1" ] \
  && pass "M1: one turns.jsonl line" || fail "M1: turns.jsonl line count != 1"
[ ! -s "$C_PROJ/.sutra/shadow/markers/diffs.jsonl" ] && pass "M1: diffs.jsonl empty or absent" || fail "M1: diffs.jsonl has lines on an all-equal turn"

# ------------------------------------------------------------------ M2 --
mk_case m2 on; write_facts
stdin_with_message "$WORK/m2.json" "$HDR_RISK
$FLOW_LINE
$DEPTH_LINE"
run_step "$WORK/m2.json"
common_asserts M2
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff" and .field=="RISK" and .equal==false and .runtime=="low" and .model=="high"')" = "1" ] \
  && pass "M2: RISK row equal:false with both values" || fail "M2: RISK row missing or wrong"
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff" and .equal==false')" = "1" ] \
  && pass "M2: exactly one unequal row" || fail "M2: unequal rows != 1"
[ "$(count_rows "$C_PROJ/.sutra/shadow/markers/diffs.jsonl" '.field=="RISK"')" = "1" ] \
  && pass "M2: one diffs.jsonl line, the RISK field" || fail "M2: diffs.jsonl line for RISK missing"
[ "$(count_rows "$C_PROJ/.sutra/shadow/markers/turns.jsonl" '.any_gate_diff==true')" = "1" ] \
  && pass "M2: turns.jsonl says any_gate_diff:true" || fail "M2: turns.jsonl any_gate_diff not true"

# RESOLUTION mismatch is never a diffs.jsonl line (gate_field:false)
mk_case m2b on; write_facts
stdin_with_message "$WORK/m2b.json" "$HDR_DOT
| [2] RESOLVE: CONSTRUCT |
$DEPTH_LINE"
run_step "$WORK/m2b.json"
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff" and .field=="RESOLUTION" and .equal==false and .gate_field==false')" = "1" ] \
  && pass "M2b: RESOLUTION row unequal and gate_field:false" || fail "M2b: RESOLUTION row wrong"
[ ! -s "$C_PROJ/.sutra/shadow/markers/diffs.jsonl" ] && pass "M2b: judgment fields never reach diffs.jsonl" || fail "M2b: diffs.jsonl got a non-gate row"

# ------------------------------------------------------------------ M3 --
mk_case m3 on; write_facts
stdin_with_message "$WORK/m3.json" "no header here, just prose"
run_step "$WORK/m3.json"
common_asserts M3
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff" and .header_parsed==false')" = "1" ] \
  && pass "M3: one header_parsed:false row" || fail "M3: header_parsed:false row count != 1"
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff"')" = "1" ] && pass "M3: no field rows" || fail "M3: unexpected field rows"
[ ! -s "$C_PROJ/.sutra/shadow/markers/turns.jsonl" ] && pass "M3: no turns.jsonl line" || fail "M3: turns.jsonl written without a header"

# ------------------------------------------------------------------ M4 --
mk_case m4 off; write_facts
stdin_with_message "$WORK/m4.json" "$HDR_DOT
$FLOW_LINE
$DEPTH_LINE"
run_step "$WORK/m4.json"
common_asserts M4
[ "$(count_rows "$C_FLAT" '.kind=="marker_flag" and .mode=="off"')" = "1" ] && pass "M4: marker_flag mode off" || fail "M4: marker_flag mode not off"
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff"')" = "0" ] && pass "M4: no marker_diff row with the flag off" || fail "M4: marker_diff rows with the flag off"

# ------------------------------------------------------------------ M5 --
mk_case m5 on; write_facts
TP="$WORK/m5/transcript.jsonl"
{
  printf '{"type":"user","message":{"role":"user","content":"hi"}}\n'
  jq -nc --arg t "$HDR_PLAIN
$FLOW_LINE
$DEPTH_LINE" '{type:"assistant",message:{role:"assistant",content:[{type:"text",text:$t}]}}'
  printf '{"type":"system","subtype":"noise"}\n'
} > "$TP"
jq -n --arg s "$C_SID" --arg tp "$TP" --arg cwd "$C_PROJ" \
  '{session_id:$s, hook_event_name:"Stop", stop_hook_active:false, transcript_path:$tp, cwd:$cwd}' > "$WORK/m5.json"
run_step "$WORK/m5.json"
common_asserts M5
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff" and .equal==true')" = "9" ] \
  && pass "M5: header parsed from the transcript tail (plain-dot separators)" || { fail "M5: rows from transcript: expected 9 equal"; jq -c 'select(.kind=="marker_diff")' "$C_FLAT" | head -3; }

# ------------------------------------------------------------------ M6 --
mk_case m6 on   # no facts file
stdin_with_message "$WORK/m6.json" "$HDR_DOT
$FLOW_LINE
$DEPTH_LINE"
run_step "$WORK/m6.json"
common_asserts M6
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff" and .facts_present==false')" = "1" ] \
  && pass "M6: one facts_present:false row" || fail "M6: facts_present:false row count != 1"
[ "$(count_rows "$C_FLAT" '.kind=="marker_diff"')" = "1" ] && pass "M6: nothing else" || fail "M6: extra rows without a facts file"

echo "failed=$failed"
[ "$failed" -eq 0 ]
