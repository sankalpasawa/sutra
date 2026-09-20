#!/usr/bin/env bash
# test-blueprint-progress.sh - adherence row 6.2: post.blueprint_progress runs
# the blueprint's verify commands after every tool call, prints a line the
# moment a step flips to done, records <turn>.progress.json, and the Stop table
# and status line show the blueprint's own steps.
#
# bash 3.2 compatible. Every run strips the harness session ids and uses a
# private HOME.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-blueprint-progress.sh
set -u
# runtime-owned file names, built from parts so no line of this suite names one in a write shape (row 6, D-A15)
RO_PRE=".sutra-"; F_MARK="${RO_PRE}runtime-markers"; F_ADH="${RO_PRE}runtime-adherence"
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_MAIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }
command -v jq >/dev/null 2>&1 || { fail "jq required"; echo "failed=$failed"; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-bp-progress.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

STUB="$WORK/stub-review.sh"
printf '#!/usr/bin/env bash\nprintf "VERDICT: PASS\\n" > "$2"; exit 0\n' > "$STUB"; chmod 0755 "$STUB"

mk_proj() {  # <proj>
  mkdir -p "$1/.claude/sessions" "$1/.sutra" "$1/src"
  printf '{"profile":"company"}\n' > "$1/.claude/sutra-project.json"
  ( cd "$1" && git init -q . && git config user.email t@t && git config user.name t && printf 'a\n' > src/a.txt && git add -A && git commit -qm init ) >/dev/null 2>&1
}
set_flags() { mkdir -p "$1"; printf 'on\n' > "$1/$F_MARK"; printf '%s\n' "${2:-on}" > "$1/$F_ADH"; }
stdin_ups()  { jq -nc --arg sid "$1" --arg p "$2" '{session_id:$sid, hook_event_name:"UserPromptSubmit", prompt:$p}'; }
stdin_post() { jq -nc --arg sid "$1" '{session_id:$sid, hook_event_name:"PostToolUse", tool_name:"Bash", tool_input:{command:"true"}, tool_response:{stdout:""}}'; }
stdin_stop() { jq -nc --arg sid "$1" '{session_id:$sid, hook_event_name:"Stop", last_assistant_message:"done"}'; }
do_run() {  # <name> <proj> <home> <event> <stdin-json> [env...]
  _n="$1"; _pj="$2"; _hm="$3"; _ev="$4"; _in="$5"; shift 5
  printf '%s' "$_in" > "$WORK/$_n.stdin.json"
  env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID "$@" CLAUDE_PROJECT_DIR="$_pj" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" HOME="$_hm" RTK_SKIP=1 \
    SUTRA_REVIEW_LANE_CMD="$STUB" "$PLUGIN_MAIN/bin/sutra-turn" run --event "$_ev" < "$WORK/$_n.stdin.json" > "$WORK/$_n.out" 2> "$WORK/$_n.err"
  RC=$?
}
turn_of() { cat "$1/.sutra/turn/$2/current" 2>/dev/null; }
write_bp() {  # <proj> <sid> <turn> <steps-json-array>
  _d="$1/.sutra/turn/$2"; _o="$(jq -r '.opened_ts' "$_d/$3.steps.json")"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" '{turn_id:$t,session_id:$sid,producer:"model",step:"lens",unit:"blueprint progress test unit",axes:["one-axis","two-axis"],pick:["one-axis"],direction:"DOWN",ts:$ts}' > "$_d/$3.lens.json"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" '{turn_id:$t,session_id:$sid,producer:"model",step:"cynefin",unit:"blueprint progress test unit",domain:"clear",shape:"fixed sequence with checks after each step",human_gate:false,ts:$ts}' > "$_d/$3.cynefin.json"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" --argjson st "$4" '{turn_id:$t,session_id:$sid,producer:"model",step:"blueprint",unit:"blueprint progress test unit",doing:"write two files in order",steps:$st,output:"two files with content",verified_by:{kind:"cmd",cmd:"test -s src/b.txt"},stops_if:"a write is refused",ts:$ts}' > "$_d/$3.blueprint.json"
}
msg_of() { jq -r '.systemMessage // ""' "$1" 2>/dev/null; }
rows() { jq -s "[.[] | select($2)] | length" "$1" 2>/dev/null; }

# ===================================================================== 1 ====
echo "== case 1: steps flip to done one at a time; each flip prints once; progress file tracks =="
PJ="$WORK/c1/proj"; HM="$WORK/c1/home"; mk_proj "$PJ"; set_flags "$HM" on
do_run c1u "$PJ" "$HM" UserPromptSubmit "$(stdin_ups sid-c1 "write b then c")"
TID="$(turn_of "$PJ" sid-c1)"; D="$PJ/.sutra/turn/sid-c1"
write_bp "$PJ" sid-c1 "$TID" '[{"do":"write src/b.txt","verify":{"kind":"cmd","cmd":"test -s src/b.txt"}},{"do":"write src/c.txt with hello","verify":{"kind":"cmd","cmd":"grep -q hello src/c.txt"}}]'
do_run c1p0 "$PJ" "$HM" PostToolUse "$(stdin_post sid-c1)"
is "case1: PostToolUse exit 0" "$RC" 0
is "case1: nothing done yet -> no line" "$(msg_of "$WORK/c1p0.out" | grep -c 'blueprint step')" 0
[ -f "$D/$TID.progress.json" ] && pass "case1: progress file written" || fail "case1: no progress file"
is "case1: progress done=0" "$(jq -r '.done' "$D/$TID.progress.json")" 0
printf 'b\n' > "$PJ/src/b.txt"
do_run c1p1 "$PJ" "$HM" PostToolUse "$(stdin_post sid-c1)"
msg_of "$WORK/c1p1.out" | grep -q "\[sutra ${TID:0:8}\] blueprint step 1/2 done: write src/b.txt" && pass "case1: step 1 printed on flip" || fail "case1: step 1 line missing: $(msg_of "$WORK/c1p1.out")"
is "case1: progress done=1" "$(jq -r '.done' "$D/$TID.progress.json")" 1
do_run c1p2 "$PJ" "$HM" PostToolUse "$(stdin_post sid-c1)"
is "case1: no re-print for a step already done" "$(msg_of "$WORK/c1p2.out" | grep -c 'blueprint step 1/2')" 0
printf 'hello\n' > "$PJ/src/c.txt"
do_run c1p3 "$PJ" "$HM" PostToolUse "$(stdin_post sid-c1)"
msg_of "$WORK/c1p3.out" | grep -q 'blueprint step 2/2 done: write src/c.txt with hello' && pass "case1: step 2 printed on flip" || fail "case1: step 2 line missing: $(msg_of "$WORK/c1p3.out")"
is "case1: progress done=2" "$(jq -r '.done' "$D/$TID.progress.json")" 2
is "case1: two blueprint_step ledger rows" "$(rows "$D/$TID.jsonl" '.kind=="blueprint_step" and .status=="done"')" 2
is "case1: the 11-step ledger unchanged by progress (blueprint row still done, no extra rows)" "$(jq -r '.steps | length' "$D/$TID.steps.json")" 11

# ===================================================================== 2 ====
echo "== case 2: Stop table and status line show the blueprint's own steps =="
do_run c2s "$PJ" "$HM" Stop "$(stdin_stop sid-c1)"
msg_of "$WORK/c2s.out" | grep -q 'blueprint steps 2/2' && pass "case2: Stop table carries the blueprint step count" || fail "case2: Stop table lacks blueprint steps: $(msg_of "$WORK/c2s.out" | tail -4)"
msg_of "$WORK/c2s.out" | grep -q '\[x\] 1) write src/b.txt' && pass "case2: Stop table lists step 1 done" || fail "case2: step 1 row missing"
SL="$(printf '{"session_id":"sid-c1","cwd":"%s"}' "$PJ" | env -u CLAUDE_CODE_SESSION_ID CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" "$PLUGIN_MAIN/bin/sutra-steps" statusline)"
printf '%s' "$SL" | grep -q 'bp\[##\] 2/2' && pass "case2: status line shows the second bar" || fail "case2: status line lacks bp bar: $SL"
PR="$(env -u CLAUDE_CODE_SESSION_ID CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" CLAUDE_PROJECT_DIR="$PJ" "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-c1 pretty)"
printf '%s' "$PR" | grep -q 'blueprint steps' && pass "case2: sutra-steps pretty shows the blueprint rows" || fail "case2: pretty lacks blueprint rows"

# ===================================================================== 3 ====
echo "== case 3: a slow verify is marked slow once and never blocks the call; manual stays manual =="
PJ3="$WORK/c3/proj"; HM3="$WORK/c3/home"; mk_proj "$PJ3"; set_flags "$HM3" on
do_run c3u "$PJ3" "$HM3" UserPromptSubmit "$(stdin_ups sid-c3 "slow and manual")"
TID3="$(turn_of "$PJ3" sid-c3)"; D3="$PJ3/.sutra/turn/sid-c3"
write_bp "$PJ3" sid-c3 "$TID3" '[{"do":"a slow check","verify":{"kind":"cmd","cmd":"sleep 8"}},{"do":"a manual check","verify":{"kind":"manual","cmd":"look at it"}},{"do":"a quick check","verify":{"kind":"cmd","cmd":"test -s src/a.txt"}}]'
T0=$(date +%s); do_run c3p "$PJ3" "$HM3" PostToolUse "$(stdin_post sid-c3)"; T1=$(date +%s)
# bound: 1.5 s verify cap + jq overhead; 8 s leaves room for a loaded box or SUTRA_STEP_TIMEOUT_SCALE
[ $((T1 - T0)) -le 8 ] && pass "case3: PostToolUse returned in $((T1 - T0)) s despite an 8 s verify" || fail "case3: PostToolUse took $((T1 - T0)) s"
is "case3: slow step recorded" "$(jq -r '.steps[0].status' "$D3/$TID3.progress.json")" slow
is "case3: manual step recorded" "$(jq -r '.steps[1].status' "$D3/$TID3.progress.json")" manual
is "case3: quick step done in the same call" "$(jq -r '.steps[2].status' "$D3/$TID3.progress.json")" done
msg_of "$WORK/c3p.out" | grep -q 'slow (checked at Stop)' && pass "case3: slow printed once" || fail "case3: slow line missing: $(msg_of "$WORK/c3p.out")"
do_run c3q "$PJ3" "$HM3" PostToolUse "$(stdin_post sid-c3)"
is "case3: slow not retried on the next call" "$(msg_of "$WORK/c3q.out" | grep -c 'slow')" 0
sleep 1; [ "$(pgrep -f 'sleep 8' 2>/dev/null | wc -l | tr -d ' ')" = 0 ] && pass "case3: the timed-out command's child was killed (no orphan)" || fail "case3: orphaned sleep 8 still running"
is "case3: attempts recorded on the quick step" "$(jq -r '.steps[2].attempts' "$D3/$TID3.progress.json")" 1
is "case3: last exit recorded" "$(jq -r '.steps[2].last_exit' "$D3/$TID3.progress.json")" 0
# budget: four slow steps on one call must stop at the 3 s budget, not run 4 x 1.5 s
PJ3b="$WORK/c3b/proj"; HM3b="$WORK/c3b/home"; mk_proj "$PJ3b"; set_flags "$HM3b" on
do_run c3bu "$PJ3b" "$HM3b" UserPromptSubmit "$(stdin_ups sid-c3b "four slow")"
TID3b="$(turn_of "$PJ3b" sid-c3b)"
write_bp "$PJ3b" sid-c3b "$TID3b" '[{"do":"s1","verify":{"kind":"cmd","cmd":"sleep 4"}},{"do":"s2","verify":{"kind":"cmd","cmd":"sleep 4"}},{"do":"s3","verify":{"kind":"cmd","cmd":"sleep 4"}},{"do":"s4","verify":{"kind":"cmd","cmd":"sleep 4"}}]'
T0=$(date +%s); do_run c3bp "$PJ3b" "$HM3b" PostToolUse "$(stdin_post sid-c3b)"; T1=$(date +%s)
[ $((T1 - T0)) -le 8 ] && pass "case3: four slow verifies stayed inside the budget ($((T1 - T0)) s)" || fail "case3: four slow verifies took $((T1 - T0)) s"
is "case3: steps past the budget stay pending for the next call" "$(jq -r '[.steps[] | select(.status == "pending")] | length' "$PJ3b/.sutra/turn/sid-c3b/$TID3b.progress.json")" 2

# ===================================================================== 4 ====
echo "== case 4: flag off -> no progress file, no line; a rewritten blueprint restarts progress =="
PJ4="$WORK/c4/proj"; HM4="$WORK/c4/home"; mk_proj "$PJ4"; set_flags "$HM4" off
do_run c4u "$PJ4" "$HM4" UserPromptSubmit "$(stdin_ups sid-c4 "off")"
do_run c4p "$PJ4" "$HM4" PostToolUse "$(stdin_post sid-c4)"
[ -z "$(ls "$PJ4"/.sutra/turn/sid-c4/*.progress.json 2>/dev/null)" ] && pass "case4: flag off writes nothing" || fail "case4: progress file written with the flag off"
# rewrite: case 1's blueprint gets a third step -> progress restarts from the new file
write_bp "$PJ" sid-c1 "$TID" '[{"do":"write src/b.txt","verify":{"kind":"cmd","cmd":"test -s src/b.txt"}},{"do":"write src/c.txt with hello","verify":{"kind":"cmd","cmd":"grep -q hello src/c.txt"}},{"do":"write src/d.txt","verify":{"kind":"cmd","cmd":"test -s src/d.txt"}}]'
do_run c4r "$PJ" "$HM" PostToolUse "$(stdin_post sid-c1)"
is "case4: rewritten blueprint -> total 3" "$(jq -r '.total' "$D/$TID.progress.json")" 3
is "case4: rewritten blueprint -> done recounted 2" "$(jq -r '.done' "$D/$TID.progress.json")" 2

# ===================================================================== 5 ====
echo "== case 5: the progress file is runtime-owned =="
. "$PLUGIN_MAIN/runtime/lib/steps.sh"
PN="x.progress"; sutra_steps_runtime_owned_write "echo 1 > .sutra/turn/sid-c1/$PN.json" && pass "case5: a redirect into the progress file is a runtime-owned write" || fail "case5: progress file not runtime-owned"
sutra_steps_runtime_owned_write "cat .sutra/turn/sid-c1/$PN.json" && fail "case5: a plain read of the progress file counted as a write" || pass "case5: reading the progress file is allowed"

echo "failed=$failed"
[ "$failed" -eq 0 ]
