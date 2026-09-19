#!/usr/bin/env bash
# test-gate-rules.sh - adherence row 6: the rules table (runtime/rules/gates.json)
# evaluated by pre.adherence_gate, the four new artifacts, sealed verdicts, the
# armed collapse of the legacy gates with its truth-diff, and the sutra-steps
# modes. Every case runs the WHOLE `bin/sutra-turn run --event <E>` against
# the real plugin tree under a private HOME (the founder's flags never leak).
#
# bash 3.2 compatible.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-gate-rules.sh

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_MAIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"

failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }

command -v jq >/dev/null 2>&1 || { fail "jq required"; echo "failed=$failed"; exit 1; }
[ -x "$PLUGIN_MAIN/bin/sutra-turn" ] || { fail "bin/sutra-turn missing"; echo "failed=$failed"; exit 1; }
RULES="$PLUGIN_MAIN/runtime/rules/gates.json"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-gate-rules.XXXXXX")"
if [ -z "${KEEP_WORK:-}" ]; then trap 'rm -rf "$WORK"' EXIT; else echo "work dir kept: $WORK"; fi

# ------------------------------------------------------------------ helpers --
# the flag / override / key file names under the private test HOME
FLAG_M=".sutra-runtime-markers"; FLAG_A=".sutra-runtime-adherence"; OVR=".sutra-overrides"; KEY=".sutra-runtime"; KEY="$KEY/seal.key"
stdin_write_c() { jq -nc --arg sid "$1" --arg f "$2" --arg c "$3" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Write", tool_input:{file_path:$f, content:$c}}'; }
stdin_bash()  { jq -nc --arg sid "$1" --arg c "$2" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Bash", tool_input:{command:$c}}'; }
mk_proj() {  # <proj>: company profile (rubric depth 5) with the D38 tree shapes
  mkdir -p "$1/.claude/sessions" "$1/.sutra" "$1/src" "$1/holding/bin" "$1/sutra/marketplace/plugin/hooks" "$1/sutra/os/charters" "$1/docs"
  printf '{"profile":"company"}\n' > "$1/.claude/sutra-project.json"
  ( cd "$1" && git init -q . 2>/dev/null && git add -A >/dev/null 2>&1 && git -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1 ) || true
}
set_flags() { mkdir -p "$1"; [ -n "$2" ] && printf '%s\n' "$2" > "$1/$FLAG_M"; [ -n "$3" ] && printf '%s\n' "$3" > "$1/$FLAG_A"; return 0; }
stdin_ups()   { jq -nc --arg sid "$1" --arg p "$2" '{session_id:$sid, hook_event_name:"UserPromptSubmit", prompt:$p}'; }
stdin_write() { jq -nc --arg sid "$1" --arg f "$2" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Write", tool_input:{file_path:$f, content:"x"}}'; }
do_run() {  # <name> <proj> <home> <event> <stdin> [env...]
  _n="$1"; _pj="$2"; _hm="$3"; _ev="$4"; _in="$5"; shift 5
  printf '%s' "$_in" > "$WORK/$_n.stdin.json"
  env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID "$@" CLAUDE_PROJECT_DIR="$_pj" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" HOME="$_hm" RTK_SKIP=1 SUTRA_STEP_TIMEOUT_SCALE=400 \
    "$PLUGIN_MAIN/bin/sutra-turn" run --event "$_ev" < "$WORK/$_n.stdin.json" > "$WORK/$_n.out" 2> "$WORK/$_n.err"
  RC=$?
}
turn_of() { cat "$1/.sutra/turn/$2/current" 2>/dev/null; }
decision_of() { _dv="$(jq -r '.hookSpecificOutput.permissionDecision // "none"' "$WORK/$1.out" 2>/dev/null)"; printf '%s' "${_dv:-none}"; }
reason_of() { jq -r '.hookSpecificOutput.permissionDecisionReason // ""' "$WORK/$1.out" 2>/dev/null; }
sysmsg_of() { jq -r '.systemMessage // ""' "$WORK/$1.out" 2>/dev/null; }
rows() { jq -s "[.[] | select($2)] | length" "$1" 2>/dev/null; }
art() {  # <proj> <sid> <turn> <ts> <kind> [extra-jq-merge]
  _d="$1/.sutra/turn/$2"; _base="{turn_id:\"$3\",session_id:\"$2\",producer:\"model\",step:\"$5\",unit:\"gate rules test unit of work\",ts:$4}"
  case "$5" in
    lens)      _x='{axes:["a-axis","b-axis"],pick:["a-axis"],direction:"DOWN"}' ;;
    cynefin)   _x='{domain:"clear",shape:"fixed sequence with one check at the end",human_gate:false}' ;;
    placement) _x='{domain_ref:"dref-0123456789abcdef",charter_id:"C-0123456789abcdef",reason:"placed under the test domain",confidence:0.9}' ;;
    blueprint) _x='{doing:"edit one file under test",steps:[{do:"write the file",verify:{kind:"cmd",cmd:"test -s src/a.txt"}}],output:"the file exists with content",verified_by:{kind:"cmd",cmd:"test -s src/a.txt"},stops_if:"the write is refused"}' ;;
    build_layer) _x='{layer:"L2",target_path:"holding/bin/x.sh",why_not_l0_kind:"instance-only",why_not_l0_reason:"box-local helper for one founder"}' ;;
    depth)     _x='{depth:5,reason:"governance code, exhaustive"}' ;;
  esac
  _m="${6:-}"; [ -n "$_m" ] || _m='{}'
  jq -nc "$_base + $_x + $_m" > "$_d/$3.$5.json" || fail "art: could not write $5 artifact"
}
open_turn() {  # <name> <proj> <home> <sid> [env...]
  _on="$1"; _op="$2"; _oh="$3"; _os="$4"; shift 4
  do_run "$_on" "$_op" "$_oh" UserPromptSubmit "$(stdin_ups "$_os" "please edit the governed file")" "$@"
  TID="$(turn_of "$_op" "$_os")"; OPENED="$(jq -r '.opened_ts // 0' "$_op/.sutra/turn/$_os/$TID.steps.json" 2>/dev/null)"; TS=$((OPENED + 1))
}
seal_review() {  # <proj> <home> <sid> <turn> [tamper]
  _d="$1/.sutra/turn/$3"; mkdir -p "$_d/lane-logs"
  jq -nc --arg t "$4" --argjson ts "$(date +%s)" '{lane:"review",status:"done",verdict:"PASS",exit:0,ts:$ts,file:"x",turn:$t}' > "$_d/$4.review.json"
  printf 'VERDICT: PASS\n' > "$_d/lane-logs/$4.review.md"; printf 'diff --git a/x b/x\n' > "$_d/lane-logs/$4.diff"
  ( HOME="$2"; . "$PLUGIN_MAIN/runtime/lib/seal.sh"; sutra_seal_file "$_d/$4.review.json" )
  [ "${5:-}" = "tamper" ] && { jq -c '.exit = 1' "$_d/$4.review.json" > "$_d/t.json" && mv "$_d/t.json" "$_d/$4.review.json"; }
  return 0
}

# ===================================================================== 1 ====
echo "== case 1: gates.json is well-formed and complete =="
jq -e '.rules | length >= 9' "$RULES" >/dev/null && pass "case1: 9+ rules" || fail "case1: rules missing"
is "case1: every rule has id, when, decision" "$(jq -r '(.rules | map(select((.id|type)=="string" and (.when|type)=="object" and (.decision|IN("allow","deny","warn")))) | length) == (.rules | length)' "$RULES")" true
is "case1: six artifact hints" "$(jq -r '.artifacts | keys | join(",")' "$RULES")" "blueprint,build_layer,cynefin,depth,lens,placement"
is "case1: collapsed steps name the legacy gates" "$(jq -r '.collapsed_steps.ids | length' "$RULES")" 11
for _id in $(jq -r '.collapsed_steps.ids[]' "$RULES"); do
  jq -e --arg id "$_id" '.events.PreToolUse[] | select(.id == $id)' "$PLUGIN_MAIN/runtime/pipeline.json" >/dev/null 2>&1 && pass "case1: $_id is a registered PreToolUse step" || fail "case1: $_id not registered"
done

# ===================================================================== 2 ====
echo "== case 2: one deny names every unmet rule; artifacts flip it to allow =="
PJ="$WORK/c2/proj"; HM="$WORK/c2/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c2u "$PJ" "$HM" sid-c2 SUTRA_LANE_CONFIGURED=0
do_run c2a "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case2: deny before artifacts" "$(decision_of c2a)" deny
for r in R4 R5 R6; do reason_of c2a | grep -q "^  $r " && pass "case2: deny names $r" || fail "case2: deny lacks $r"; done
reason_of c2a | grep -q 'blueprint.json (missing)' && pass "case2: names the blueprint file" || fail "case2: no blueprint path"
reason_of c2a | grep -q 'placement.json (missing)' && pass "case2: names the placement file (new path, no engine match)" || fail "case2: no placement path"
sysmsg_of c2a | grep -q 'REFUSED Write: unmet R4 R5 R6' && pass "case2: live line lists the unmet ids" || fail "case2: live line wrong: $(sysmsg_of c2a | head -1)"
is "case2: rules ledger row" "$(rows "$PJ/.sutra/turn/sid-c2/$TID.jsonl" '.kind == "adherence_rules" and .decision == "deny"')" 1
for k in lens cynefin placement blueprint; do art "$PJ" sid-c2 "$TID" "$TS" $k; done
do_run c2b "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case2: allow once the four artifacts exist" "$(decision_of c2b)" none
sysmsg_of c2b | grep -q 'blueprint done (1 steps, 1 runnable verifies)' && pass "case2: live line shows blueprint done with its verify count" || fail "case2: blueprint line: $(sysmsg_of c2b | head -1)"
is "case2: steps 5-7 done" "$(jq -r '[.steps[] | select(.id == "lens" or .id == "cynefin" or .id == "blueprint") | .status] | join(",")' "$PJ/.sutra/turn/sid-c2/$TID.steps.json")" "done,done,done"
is "case2: placement from the artifact" "$(jq -r '.steps[] | select(.id == "placement") | .detail' "$PJ/.sutra/turn/sid-c2/$TID.steps.json")" "dref-0123456789abcdef (placement.json)"
printf 'x\n' > "$PJ/docs/existing.md"; rm -f "$PJ/.sutra/turn/sid-c2/$TID.placement.json"
do_run c2c "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/docs/existing.md")" SUTRA_LANE_CONFIGURED=0
is "case2: an existing path passes without placement.json" "$(decision_of c2c)" none

# ===================================================================== 3 ====
echo "== case 3: the blueprint artifact - trivial or manual-only verifies at depth 5 are refused; depth.json only raises =="
PJ="$WORK/c3/proj"; HM="$WORK/c3/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c3u "$PJ" "$HM" sid-c3 SUTRA_LANE_CONFIGURED=0
for k in lens cynefin placement; do art "$PJ" sid-c3 "$TID" "$TS" $k; done
art "$PJ" sid-c3 "$TID" "$TS" blueprint '{steps:[{do:"write the file",verify:{kind:"manual",cmd:""}}]}'
do_run c3a "$PJ" "$HM" PreToolUse "$(stdin_write sid-c3 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case3: manual-only verify at depth 5 -> deny" "$(decision_of c3a)" deny
reason_of c3a | grep -q 'verify-must-be-cmd-at-depth-3-plus' && pass "case3: reason names the depth rule" || fail "case3: reason: $(reason_of c3a | head -3)"
art "$PJ" sid-c3 "$TID" "$TS" blueprint '{steps:[{do:"write the file",verify:{kind:"cmd",cmd:"works"}}]}'
do_run c3b "$PJ" "$HM" PreToolUse "$(stdin_write sid-c3 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case3: a trivial verify word -> deny" "$(decision_of c3b)" deny
art "$PJ" sid-c3 "$TID" "$TS" blueprint '{verified_by:{kind:"cmd",cmd:"passes"}}'
do_run c3c "$PJ" "$HM" PreToolUse "$(stdin_write sid-c3 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case3: a trivial verified_by -> deny" "$(decision_of c3c)" deny
art "$PJ" sid-c3 "$TID" "$TS" blueprint
do_run c3d "$PJ" "$HM" PreToolUse "$(stdin_write sid-c3 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case3: a runnable blueprint -> allow" "$(decision_of c3d)" none
art "$PJ" sid-c3 "$TID" "$TS" depth '{depth:3}'
do_run c3e "$PJ" "$HM" PreToolUse "$(stdin_write sid-c3 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
jq -r '.steps[] | select(.id == "depth") | .detail' "$PJ/.sutra/turn/sid-c3/$TID.steps.json" | grep -q 'ignored: not a raise' && pass "case3: a lower depth.json is ignored and noted" || fail "case3: depth detail: $(jq -r '.steps[] | select(.id == "depth") | .detail' "$PJ/.sutra/turn/sid-c3/$TID.steps.json")"
art "$PJ" sid-c3 "$TID" "$TS" depth '{depth:7}'
do_run c3f "$PJ" "$HM" PreToolUse "$(stdin_write sid-c3 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
jq -r '.steps[] | select(.id == "depth") | .detail' "$PJ/.sutra/turn/sid-c3/$TID.steps.json" | grep -q 'depth.json' && fail "case3: an invalid depth.json was read" || pass "case3: an invalid depth.json (7) is not read"

# ===================================================================== 4 ====
echo "== case 4: path categories - plugin runtime is L0 by rule, holding-impl needs build_layer.json, governance paths need the sealed lane =="
PJ="$WORK/c4/proj"; HM="$WORK/c4/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c4u "$PJ" "$HM" sid-c4 SUTRA_LANE_CONFIGURED=0
for k in lens cynefin placement blueprint; do art "$PJ" sid-c4 "$TID" "$TS" $k; done
do_run c4a "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/sutra/marketplace/plugin/hooks/new.sh")" SUTRA_LANE_CONFIGURED=0
is "case4: plugin-runtime path passes (R7 L0 by rule; R8w warns without a lane)" "$(decision_of c4a)" none
sysmsg_of c4a | grep -q 'R8w' && pass "case4: warn names R8w (no lane configured)" || fail "case4: no R8w warning: $(sysmsg_of c4a | head -2)"
grep adherence_rules "$PJ/.sutra/turn/sid-c4/$TID.jsonl" | tail -1 | jq -r '.context.path_category' | grep -q plugin-runtime && pass "case4: category plugin-runtime recorded" || fail "case4: category not recorded"
do_run c4b "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/holding/bin/x.sh")" SUTRA_LANE_CONFIGURED=0
is "case4: holding-impl without build_layer.json -> deny" "$(decision_of c4b)" deny
reason_of c4b | grep -q '^  R7b ' && pass "case4: deny names R7b" || fail "case4: R7b missing from reason"
art "$PJ" sid-c4 "$TID" "$TS" build_layer '{layer:"L1",promote_to:"sutra/marketplace/plugin/bin/x",owner:"runtime",acceptance:"suite green on two boxes"}'
do_run c4c "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/holding/bin/x.sh")" SUTRA_LANE_CONFIGURED=0
is "case4: L1 without promote_by -> deny (invalid artifact)" "$(decision_of c4c)" deny
reason_of c4c | grep -q 'L1-needs-promote_to-promote_by-owner-acceptance' && pass "case4: reason names the L1 fields" || fail "case4: L1 reason: $(reason_of c4c | grep R7b -A1 | head -2)"
art "$PJ" sid-c4 "$TID" "$TS" build_layer
do_run c4d "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/holding/bin/x.sh")" SUTRA_LANE_CONFIGURED=0
is "case4: L2 with kind + reason -> allow" "$(decision_of c4d)" none
do_run c4e "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/sutra/os/charters/X.md")" SUTRA_LANE_CONFIGURED=1
is "case4: legacy-hard path at depth 5 with a lane but no verdict -> deny" "$(decision_of c4e)" deny
reason_of c4e | grep -q '^  R8 ' && pass "case4: deny names R8" || fail "case4: R8 missing"
seal_review "$PJ" "$HM" sid-c4 "$TID" tamper
do_run c4f "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/sutra/os/charters/X.md")" SUTRA_LANE_CONFIGURED=1
is "case4: a tampered sealed verdict -> still deny" "$(decision_of c4f)" deny
seal_review "$PJ" "$HM" sid-c4 "$TID"
do_run c4g "$PJ" "$HM" PreToolUse "$(stdin_write sid-c4 "$PJ/sutra/os/charters/X.md")" SUTRA_LANE_CONFIGURED=1
is "case4: a sealed corroborated verdict -> allow" "$(decision_of c4g)" none
sysmsg_of c4g | grep -q 'codex done (review lane PASS (sealed))' && pass "case4: live line shows the sealed lane" || fail "case4: codex line: $(sysmsg_of c4g | head -1)"
PJ5="$WORK/c4o/proj"; HM5="$WORK/c4o/home"; mk_proj "$PJ5"; set_flags "$HM5" on on
printf 'CODEX_CONSULT_ACK=1\nCODEX_CONSULT_ACK_REASON=lane exhausted\n' > "$HM5/$OVR"; touch -t 202001010000 "$HM5/$OVR"
open_turn c4ou "$PJ5" "$HM5" sid-c4o SUTRA_LANE_CONFIGURED=1
for k in lens cynefin placement blueprint; do art "$PJ5" sid-c4o "$TID" "$TS" $k; done
do_run c4h "$PJ5" "$HM5" PreToolUse "$(stdin_write sid-c4o "$PJ5/sutra/os/charters/X.md")" SUTRA_LANE_CONFIGURED=1
is "case4: the pre-session override key satisfies R8" "$(decision_of c4h)" none

# ===================================================================== 5 ====
echo "== case 5: armed collapse - legacy gates run, their decisions go to the truth-diff, only the rules decide; unarmed they decide as before =="
PJ="$WORK/c5/proj"; HM="$WORK/c5/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c5u "$PJ" "$HM" sid-c5 SUTRA_LANE_CONFIGURED=0
for k in lens cynefin placement blueprint; do art "$PJ" sid-c5 "$TID" "$TS" $k; done
do_run c5a "$PJ" "$HM" PreToolUse "$(stdin_write sid-c5 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case5: armed -> the rules allow, the legacy refusal is dropped" "$(decision_of c5a)" none
grep -q 'requires a depth marker' "$WORK/c5a.err" && fail "case5: legacy stderr leaked into the emission" || pass "case5: legacy stderr dropped"
TD="$PJ/.sutra/turn/sid-c5/$TID.truthdiff.jsonl"
[ -f "$TD" ] && pass "case5: truth-diff file written" || fail "case5: no truth-diff file"
is "case5: legacy depth-marker decision recorded as deny" "$(jq -r 'select(.source == "legacy" and .step == "pre.depth-marker-pretool") | .decision' "$TD" 2>/dev/null | tail -1)" deny
is "case5: rules decision recorded as allow" "$(jq -r 'select(.source == "rules") | .decision' "$TD" 2>/dev/null | tail -1)" allow
grep -q 'rules gate armed' "$PJ/.sutra/turn/sid-c5/$TID.jsonl" && pass "case5: armed note in the ledger" || fail "case5: no armed note"
OUT="$(CLAUDE_PROJECT_DIR="$PJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-c5 truthdiff 2>&1)"
printf '%s' "$OUT" | grep '^  legacy denied:' | grep -q 'pre.depth-marker-pretool' && pass "case5: sutra-steps truthdiff reports the disagreement" || fail "case5: truthdiff output: $(printf '%s' "$OUT" | tail -2)"
printf '%s' "$OUT" | grep -q 'rules denied: none' && pass "case5: truthdiff shows the rules allowed" || fail "case5: rules line missing"
PJW="$WORK/c5w/proj"; HMW="$WORK/c5w/home"; mk_proj "$PJW"; set_flags "$HMW" on warn
open_turn c5wu "$PJW" "$HMW" sid-c5w SUTRA_LANE_CONFIGURED=0
for k in lens cynefin placement blueprint; do art "$PJW" sid-c5w "$TID" "$TS" $k; done
do_run c5b "$PJW" "$HMW" PreToolUse "$(stdin_write sid-c5w "$PJW/src/a.txt")" SUTRA_LANE_CONFIGURED=0
{ grep -q 'requires a depth marker' "$WORK/c5b.err" || [ "$RC" = "2" ]; } && pass "case5: warn mode is unarmed: the legacy depth gate refused" || fail "case5: unarmed legacy gate did not decide (rc=$RC)"
{ [ -f "$PJW/.sutra/turn/sid-c5w/$TID.truthdiff.jsonl" ] && jq -e 'select(.source == "legacy")' "$PJW/.sutra/turn/sid-c5w/$TID.truthdiff.jsonl" >/dev/null 2>&1; } && fail "case5: legacy rows recorded while unarmed" || pass "case5: no legacy truth-diff rows while unarmed"
do_run c5c "$PJ" "$HM" PreToolUse "$(stdin_write sid-c5 "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0 SUTRA_RUNTIME_DISABLED=1
grep -q 'requires a depth marker' "$WORK/c5c.err" && pass "case5: kill-switch -> legacy path, legacy gate decides" || fail "case5: kill-switch did not fall back (rc=$RC): $(head -c 200 "$WORK/c5c.err")"

# ===================================================================== 6 ====
echo "== case 6: the seal library and the sutra-steps modes =="
HM6="$WORK/c6/home"; mkdir -p "$HM6"; F="$WORK/c6/v.json"; printf '{"lane":"review","status":"done","verdict":"PASS","ts":1}\n' > "$F"
( HOME="$HM6"; . "$PLUGIN_MAIN/runtime/lib/seal.sh"; sutra_seal_file "$F" && sutra_seal_verify "$F" ) && pass "case6: sign + verify round-trip" || fail "case6: round-trip failed"
[ -s "$HM6/$KEY" ] && pass "case6: the box key was created on first use" || fail "case6: no key created"
[ "$(stat -f %Lp "$HM6/$KEY" 2>/dev/null || stat -c %a "$HM6/$KEY")" = "600" ] && pass "case6: key mode 600" || fail "case6: key mode not 600"
( HOME="$HM6"; . "$PLUGIN_MAIN/runtime/lib/seal.sh"; jq -c '.verdict = "CHANGES-REQUIRED"' "$F" > "$F.t" && mv "$F.t" "$F"; sutra_seal_verify "$F" ) && fail "case6: tampered file verified" || pass "case6: tampered file fails to verify"
( unset HOME; . "$PLUGIN_MAIN/runtime/lib/seal.sh"; sutra_seal_sign '{"a":1}' ) >/dev/null 2>&1 && fail "case6: signed with HOME unset" || pass "case6: HOME unset -> nothing signs (fail closed)"
PJ="$WORK/c2/proj"
OUT="$(printf '{"session_id":"sid-c2","cwd":"%s/src","workspace":{"current_dir":"%s/src"}}' "$PJ" "$PJ" | env -u CLAUDE_CODE_SESSION_ID CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" statusline 2>&1)"
printf '%s' "$OUT" | grep -qE '^sutra [0-9a-f]{8} \[[#~!.]{11}\] [0-9]+/11' && pass "case6: statusline line from the host JSON (walks up from a subdir)" || fail "case6: statusline: [$OUT]"
OUT="$(printf '{"session_id":"nope","cwd":"%s"}' "$PJ" | env -u CLAUDE_CODE_SESSION_ID CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" statusline 2>&1)"
OUT2="$(printf '{"session_id":"sid-c2","cwd":"%s"}' "$PJ" | CLAUDE_CODE_SESSION_ID=some-other-session CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" statusline 2>&1)"
printf '%s' "$OUT2" | grep -q '^sutra ' && pass "case6: the host JSON session wins over the env session" || fail "case6: env session shadowed the host JSON: [$OUT2]"
is "case6: statusline silent without a ledger" "$OUT" ""
OUT="$(CLAUDE_PROJECT_DIR="$PJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-c2 pretty 2>&1)"
is "case6: pretty prints one checkbox row per step" "$(printf '%s\n' "$OUT" | grep -c '^  \[[x o~!]\] ')" 11
CLAUDE_PROJECT_DIR="$PJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-c2 --json 2>/dev/null | jq -e '.steps | length == 11' >/dev/null && pass "case6: --json is the ledger" || fail "case6: --json broken"

# ================================================================== 6b ====
echo "== case 6b: review-lane folds - the most governed path wins, shell no-ops are not verifies, the ledger files and the seal dir are runtime-owned =="
PJ="$WORK/c6b/proj"; HM="$WORK/c6b/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c6bu "$PJ" "$HM" sid-c6b SUTRA_LANE_CONFIGURED=0
for k in lens cynefin placement blueprint; do art "$PJ" sid-c6b "$TID" "$TS" $k; done
printf 'x\n' > "$PJ/holding/bin/a.sh"
do_run c6b1 "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c6b "mv $PJ/sutra/marketplace/plugin/hooks/z.sh $PJ/holding/bin/a.sh")" SUTRA_LANE_CONFIGURED=0
is "case6b: a structural command naming plugin + holding paths is judged as holding-impl (deny without build_layer.json)" "$(decision_of c6b1)" deny
reason_of c6b1 | grep -q 'path_category=holding-impl' && pass "case6b: the most governed category won" || fail "case6b: category: $(reason_of c6b1 | grep -o 'path_category=[a-z-]*')"
art "$PJ" sid-c6b "$TID" "$TS" blueprint '{steps:[{do:"write the file",verify:{kind:"cmd",cmd:"true"}}]}'
do_run c6b2 "$PJ" "$HM" PreToolUse "$(stdin_write sid-c6b "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case6b: verify cmd 'true' is not a verify" "$(decision_of c6b2)" deny
art "$PJ" sid-c6b "$TID" "$TS" blueprint '{steps:[{do:"write the file",verify:{kind:"cmd",cmd:"exit 0"}}]}'
do_run c6b3 "$PJ" "$HM" PreToolUse "$(stdin_write sid-c6b "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case6b: verify cmd 'exit 0' is not a verify" "$(decision_of c6b3)" deny
art "$PJ" sid-c6b "$TID" "$TS" blueprint
do_run c6b4 "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c6b "rm $PJ/.sutra/turn/sid-c6b/$TID.facts.json")" SUTRA_LANE_CONFIGURED=0
reason_of c6b4 | grep -q 'RUNTIME-OWNED PATH' && pass "case6b: the facts file is runtime-owned (deleting it cannot blank the depth)" || fail "case6b: facts deletion allowed: $(decision_of c6b4)"
do_run c6b5 "$PJ" "$HM" PreToolUse "$(stdin_write sid-c6b "$PJ/.sutra/turn/sid-c6b/$TID.review.json")" SUTRA_LANE_CONFIGURED=0
reason_of c6b5 | grep -q 'RUNTIME-OWNED PATH' && pass "case6b: a lane verdict file cannot be written by a tool" || fail "case6b: verdict Write allowed"
do_run c6b6 "$PJ" "$HM" PreToolUse "$(stdin_write_c sid-c6b "$PJ/src/tests/test-off.sh" "#!/bin/sh
rm -f \"\$HOME/$FLAG_A\" \"\$HOME/$FLAG_M\"")" SUTRA_LANE_CONFIGURED=0
reason_of c6b6 | grep -q 'RUNTIME-OWNED PATH' && pass "case6b: a 'test' script that deletes the flag files is refused anywhere (no carve-out)" || fail "case6b: flag-deleting script allowed: $(decision_of c6b6)"
do_run c6b7 "$PJ" "$HM" PreToolUse "$(stdin_write_c sid-c6b "$PJ/docs/notes.md" "cleanup: rm .sutra/turn/sid-x/abc.steps.json when a session is retired")" SUTRA_LANE_CONFIGURED=0
is "case6b: a doc that names a ledger file next to a verb still passes (content mode)" "$(decision_of c6b7)" none
do_run c6b8 "$PJ" "$HM" PreToolUse "$(stdin_write sid-c6b "$PJ/src/a.txt")" SUTRA_LANE_CONFIGURED=0
is "case6b: the ordinary Write still passes after all that" "$(decision_of c6b8)" none

# ================================================================== 6c ====
echo "== case 6c: workflow folds - Bash writes are judged by path, placement only from the engine, a broken rules file fails closed, the collapse needs a decided gate =="
PJ="$WORK/c6c/proj"; HM="$WORK/c6c/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c6cu "$PJ" "$HM" sid-c6c SUTRA_LANE_CONFIGURED=0
for k in lens cynefin placement blueprint; do art "$PJ" sid-c6c "$TID" "$TS" $k; done
do_run c6c1 "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c6c "printf x > holding/bin/new.sh")" SUTRA_LANE_CONFIGURED=0
is "case6c: a redirect into holding/bin is judged holding-impl (deny R7b)" "$(decision_of c6c1)" deny
reason_of c6c1 | grep -q '^  R7b ' && pass "case6c: names R7b" || fail "case6c: R7b missing: $(reason_of c6c1 | head -3)"
do_run c6c2 "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c6c "cat > sutra/os/charters/NEW.md <<'EOF'
x
EOF")" SUTRA_LANE_CONFIGURED=1
is "case6c: a heredoc into a charter at depth 5 with a lane needs the sealed verdict (deny R8)" "$(decision_of c6c2)" deny
reason_of c6c2 | grep -q '^  R8 ' && pass "case6c: names R8" || fail "case6c: R8 missing"
do_run c6c3 "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c6c "tee src/brand-new.txt < /dev/null")" SUTRA_LANE_CONFIGURED=0
[ "$(decision_of c6c3)" = none ] && pass "case6c: tee to a soft path passes (placement.json present)" || fail "case6c: tee refused: $(reason_of c6c3 | head -2)"
# placement: a model-written marker is no evidence
PJ2="$WORK/c6c2/proj"; HM2="$WORK/c6c2/home"; mk_proj "$PJ2"; set_flags "$HM2" on on
open_turn c6c2u "$PJ2" "$HM2" sid-c6c2 SUTRA_LANE_CONFIGURED=0
for k in lens cynefin blueprint; do art "$PJ2" sid-c6c2 "$TID" "$TS" $k; done
printf 'DOMAIN_REF=dref-deadbeefdeadbeef\nCHARTER_ID=C-deadbeefdeadbeef\nSOURCE=model\n' > "$PJ2/.claude/sessions/sid-c6c2/placement-registered"
do_run c6c4 "$PJ2" "$HM2" PreToolUse "$(stdin_write sid-c6c2 "$PJ2/src/new.txt")" SUTRA_LANE_CONFIGURED=0
is "case6c: a model-written placement marker does not clear R4" "$(decision_of c6c4)" deny
reason_of c6c4 | grep -q '^  R4 ' && pass "case6c: names R4" || fail "case6c: R4 missing"
printf 'DOMAIN_REF=dref-0123456789abcdef\nCHARTER_ID=C-0123456789abcdef\nSOURCE=engine\n' > "$PJ2/.claude/sessions/sid-c6c2/placement-registered"
do_run c6c5 "$PJ2" "$HM2" PreToolUse "$(stdin_write sid-c6c2 "$PJ2/src/new.txt")" SUTRA_LANE_CONFIGURED=0
is "case6c: the engine's marker clears R4" "$(decision_of c6c5)" none
# a broken rules file: deny, and the legacy gates are not collapsed
PB="$WORK/c6c3/plugin"; mkdir -p "$PB"; cp -R "$PLUGIN_MAIN/." "$PB/"; rm -rf "$PB/hooks/tests" "$PB/sutra-ui" 2>/dev/null; chmod -R u+w "$PB" 2>/dev/null
printf '{"rules": [' > "$PB/runtime/rules/gates.json"
PJ3="$WORK/c6c3/proj"; HM3="$WORK/c6c3/home"; mk_proj "$PJ3"; set_flags "$HM3" on on
printf '%s' "$(stdin_ups sid-c6c3 "broken rules")" > "$WORK/c6c3u.stdin.json"
env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$PJ3" CLAUDE_PLUGIN_ROOT="$PB" HOME="$HM3" RTK_SKIP=1 SUTRA_STEP_TIMEOUT_SCALE=400 SUTRA_LANE_CONFIGURED=0 "$PB/bin/sutra-turn" run --event UserPromptSubmit < "$WORK/c6c3u.stdin.json" > "$WORK/c6c3u.out" 2>/dev/null
T3="$(turn_of "$PJ3" sid-c6c3)"; O3="$(jq -r '.opened_ts' "$PJ3/.sutra/turn/sid-c6c3/$T3.steps.json")"
for k in lens cynefin placement blueprint; do art "$PJ3" sid-c6c3 "$T3" $((O3 + 1)) $k; done
printf '%s' "$(stdin_write sid-c6c3 "$PJ3/src/a.txt")" > "$WORK/c6c6.stdin.json"
env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$PJ3" CLAUDE_PLUGIN_ROOT="$PB" HOME="$HM3" RTK_SKIP=1 SUTRA_STEP_TIMEOUT_SCALE=400 SUTRA_LANE_CONFIGURED=0 "$PB/bin/sutra-turn" run --event PreToolUse < "$WORK/c6c6.stdin.json" > "$WORK/c6c6.out" 2> "$WORK/c6c6.err"
is "case6c: a broken gates.json -> deny even with every artifact" "$(decision_of c6c6)" deny
reason_of c6c6 | grep -q 'unparseable' && pass "case6c: the reason names the broken file" || fail "case6c: reason: $(reason_of c6c6 | head -2)"
grep -q 'rules gate armed' "$PJ3/.sutra/turn/sid-c6c3/$T3.jsonl" && fail "case6c: the collapse was armed on a broken rules file" || pass "case6c: no collapse on a broken rules file"
# lane_configured: a codex binary is not a lane; an executable lane command is
PATH_SAVE="$PATH"; FAKE="$WORK/fakebin"; mkdir -p "$FAKE"; printf '#!/bin/sh\nexit 0\n' > "$FAKE/codex"; chmod +x "$FAKE/codex"
( export PATH="$FAKE:$PATH"; unset SUTRA_LANE_CONFIGURED SUTRA_REVIEW_LANE_CMD DEEPSEEK_TOKEN_FILE; HOME="$WORK/c6c-nohome"; mkdir -p "$HOME"; . "$PLUGIN_MAIN/runtime/lib/steps.sh"; sutra_steps_lane_configured ) && fail "case6c: a codex binary counted as a lane" || pass "case6c: a codex binary alone is not a lane"
( unset SUTRA_LANE_CONFIGURED; SUTRA_REVIEW_LANE_CMD="$FAKE/codex"; export SUTRA_REVIEW_LANE_CMD; HOME="$WORK/c6c-nohome"; . "$PLUGIN_MAIN/runtime/lib/steps.sh"; sutra_steps_lane_configured ) && pass "case6c: an executable lane command is a lane" || fail "case6c: executable lane command not counted"
( unset SUTRA_LANE_CONFIGURED; SUTRA_REVIEW_LANE_CMD="$WORK/does-not-exist"; export SUTRA_REVIEW_LANE_CMD; HOME="$WORK/c6c-nohome"; . "$PLUGIN_MAIN/runtime/lib/steps.sh"; sutra_steps_lane_configured ) && fail "case6c: a missing lane command counted" || pass "case6c: a missing lane command is not a lane"

# ===================================================================== 7 ====
echo "== case 7: flags absent - no rules, no truth-diff, no armed note (D-A9) =="
PJ="$WORK/c7/proj"; HM="$WORK/c7/home"; mk_proj "$PJ"; set_flags "$HM" "" ""
do_run c7u "$PJ" "$HM" UserPromptSubmit "$(stdin_ups sid-c7 "flag absent")"
do_run c7a "$PJ" "$HM" PreToolUse "$(stdin_write sid-c7 "$PJ/src/a.txt")"
ls "$PJ/.sutra/turn/sid-c7/"*.truthdiff.jsonl >/dev/null 2>&1 && fail "case7: truth-diff written with flags absent" || pass "case7: no truth-diff with flags absent"
grep -rq 'adherence_armed\|adherence_rules\|rules gate armed' "$PJ/.sutra/turn/sid-c7/" 2>/dev/null && fail "case7: rules rows with flags absent" || pass "case7: no rules rows with flags absent"
grep -q 'requires a depth marker' "$WORK/c7a.err" && pass "case7: the legacy depth gate still decides" || fail "case7: legacy gate silent with flags absent"

echo "failed=$failed"
[ "$failed" -eq 0 ]
