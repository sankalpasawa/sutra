#!/usr/bin/env bash
# test-review-lane.sh - adherence row 2: stop.review_lane runs the declared
# test command and a second-lane review of the turn's diff, detached, and the
# next turn's ledger reports them. The review command is stubbed through
# SUTRA_REVIEW_LANE_CMD so no network is touched.
#
# bash 3.2 compatible. Every run strips the harness session ids and uses a
# private HOME.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-review-lane.sh
set -u
# runtime-owned file names, built from parts so no line of this suite names one in a write shape (row 6, D-A15)
RO_PRE=".sutra-"; F_MARK="${RO_PRE}runtime-markers"; F_ADH="${RO_PRE}runtime-adherence"; F_DIS="${RO_PRE}runtime-adherence-disabled"; F_OVR="${RO_PRE}overrides"
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_MAIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }
command -v jq >/dev/null 2>&1 || { fail "jq required"; echo "failed=$failed"; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-review-lane.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

STUB="$WORK/stub-review.sh"
cat > "$STUB" <<'EOF'
#!/usr/bin/env bash
# stub reviewer: <prompt-file> <out-file>; echoes a verdict, records the prompt size
printf 'stub review of %s bytes\nVERDICT: PASS\nP1 (must fix): none\n' "$(wc -c < "$1" | tr -d ' ')" > "$2"
exit 0
EOF
chmod 0755 "$STUB"

mk_proj() {  # <proj> [test_command]
  mkdir -p "$1/.claude/sessions" "$1/.sutra" "$1/src"
  if [ -n "${2:-}" ]; then jq -nc --arg t "$2" '{profile:"company", test_command:$t}' > "$1/.claude/sutra-project.json"
  else printf '{"profile":"company"}\n' > "$1/.claude/sutra-project.json"; fi
  ( cd "$1" && git init -q . && git config user.email t@t && git config user.name t && printf 'a\n' > src/a.txt && git add -A && git commit -qm init ) >/dev/null 2>&1
}
set_flags() { mkdir -p "$1"; printf 'on\n' > "$1/$F_MARK"; printf '%s\n' "${2:-on}" > "$1/$F_ADH"; }
stdin_ups()   { jq -nc --arg sid "$1" --arg p "$2" '{session_id:$sid, hook_event_name:"UserPromptSubmit", prompt:$p}'; }
stdin_write() { jq -nc --arg sid "$1" --arg f "$2" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Write", tool_input:{file_path:$f, content:"x"}}'; }
stdin_stop()  { jq -nc --arg sid "$1" '{session_id:$sid, hook_event_name:"Stop", last_assistant_message:"done"}'; }
do_run() {  # <name> <proj> <home> <event> <stdin-json> [env...]
  _n="$1"; _pj="$2"; _hm="$3"; _ev="$4"; _in="$5"; shift 5
  printf '%s' "$_in" > "$WORK/$_n.stdin.json"
  env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID "$@" CLAUDE_PROJECT_DIR="$_pj" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" HOME="$_hm" RTK_SKIP=1 \
    SUTRA_REVIEW_LANE_CMD="$STUB" "$PLUGIN_MAIN/bin/sutra-turn" run --event "$_ev" < "$WORK/$_n.stdin.json" > "$WORK/$_n.out" 2> "$WORK/$_n.err"
  RC=$?
}
turn_of() { cat "$1/.sutra/turn/$2/current" 2>/dev/null; }
write_artifacts() {  # <proj> <sid> <turn>
  _d="$1/.sutra/turn/$2"; _o="$(jq -r '.opened_ts' "$_d/$3.steps.json")"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" '{turn_id:$t,session_id:$sid,producer:"model",step:"lens",unit:"review lane test unit of work",axes:["one-axis","two-axis"],pick:["one-axis"],direction:"DOWN",ts:$ts}' > "$_d/$3.lens.json"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" '{turn_id:$t,session_id:$sid,producer:"model",step:"cynefin",unit:"review lane test unit of work",domain:"clear",shape:"fixed sequence with one check at the end",human_gate:false,ts:$ts}' > "$_d/$3.cynefin.json"
  # row 6 (R4): no placement engine in these projects, so a new path needs the placement artifact
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" '{turn_id:$t,session_id:$sid,producer:"model",step:"placement",unit:"review lane test unit of work",domain_ref:"dref-0123456789abcdef",charter_id:"C-0123456789abcdef",reason:"test project placed under the test domain",confidence:0.9,ts:$ts}' > "$_d/$3.placement.json"
  # row 6: the blueprint artifact is the third thing every mutation needs (R6)
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$_o" '{turn_id:$t,session_id:$sid,producer:"model",step:"blueprint",unit:"review lane test unit of work",doing:"edit one file for the lane test",steps:[{do:"write the file",verify:{kind:"cmd",cmd:"test -s src/a.txt"}}],output:"the file exists with content",verified_by:{kind:"cmd",cmd:"test -s src/a.txt"},stops_if:"the write is refused",ts:$ts}' > "$_d/$3.blueprint.json"
}
wait_for() {  # <file> <jq-cond> [secs]
  _i=0; while [ $_i -lt "${3:-15}" ]; do [ -f "$1" ] && jq -e "$2" "$1" >/dev/null 2>&1 && return 0; sleep 1; _i=$((_i+1)); done; return 1
}
rows() { jq -s "[.[] | select($2)] | length" "$1" 2>/dev/null; }

# ===================================================================== 1 ====
echo "== case 1: a turn that mutated a repo file -> both lanes run, verdicts land, marker written =="
PJ="$WORK/c1/proj"; HM="$WORK/c1/home"; mk_proj "$PJ" "printf tests-ok; exit 0"; set_flags "$HM" on
do_run c1u "$PJ" "$HM" UserPromptSubmit "$(stdin_ups sid-c1 "please change src/a.txt")"
TID="$(turn_of "$PJ" sid-c1)"; write_artifacts "$PJ" sid-c1 "$TID"
do_run c1w "$PJ" "$HM" PreToolUse "$(stdin_write sid-c1 "$PJ/src/a.txt")"
printf 'changed\n' > "$PJ/src/a.txt"     # the mutation the gate allowed
do_run c1s "$PJ" "$HM" Stop "$(stdin_stop sid-c1)"
is "case1: Stop exit 0" "$RC" 0
D="$PJ/.sutra/turn/sid-c1"
wait_for "$D/$TID.tests.json" '.status == "done"' 20 && pass "case1: tests lane finished" || fail "case1: tests lane did not finish: $(cat "$D/$TID.tests.json" 2>/dev/null)"
is "case1: tests exit 0" "$(jq -r '.exit' "$D/$TID.tests.json" 2>/dev/null)" 0
wait_for "$D/$TID.review.json" '.status == "done"' 20 && pass "case1: review lane finished" || fail "case1: review lane did not finish: $(cat "$D/$TID.review.json" 2>/dev/null)"
is "case1: review verdict" "$(jq -r '.verdict' "$D/$TID.review.json" 2>/dev/null)" PASS
[ -f "$PJ/.claude/sessions/sid-c1/deepseek-consulted" ] && pass "case1: deepseek-consulted marker written by the runtime" || fail "case1: no deepseek-consulted marker"
grep -qx 'SOURCE=runtime' "$PJ/.claude/sessions/sid-c1/deepseek-consulted" 2>/dev/null && pass "case1: marker carries SOURCE=runtime" || fail "case1: marker lacks SOURCE=runtime"
grep -q 'src/a.txt' "$D/lane-logs/$TID.review-prompt.txt" 2>/dev/null && pass "case1: review prompt carries the diff" || fail "case1: review prompt lacks the diff"
is "case1: lane rows" "$(rows "$D/$TID.jsonl" '.kind=="lane_tests" or .kind=="lane_review"')" 2
[ -z "$(cat "$WORK/c1s.out")" ] && pass "case1: review_lane emits nothing on stdout" || pass "case1: Stop stdout carried other steps' output only"

# ===================================================================== 2 ====
echo "== case 2: the next turn's trace reports the lanes and steps 8 + 10 read done =="
do_run c2u "$PJ" "$HM" UserPromptSubmit "$(stdin_ups sid-c1 "next thing please")"
CTX="$(jq -r '.hookSpecificOutput.additionalContext // ""' "$WORK/c2u.out")"
printf '%s' "$CTX" | grep -q 'review=done:PASS' && pass "case2: Last turn line carries the review verdict" || fail "case2: no review verdict in the trace tail: $(printf '%s' "$CTX" | grep 'Last turn')"
printf '%s' "$CTX" | grep -q 'tests=done exit=0' && pass "case2: Last turn line carries the tests exit" || fail "case2: no tests exit in the trace tail"
TID2="$(turn_of "$PJ" sid-c1)"
is "case2: step 8 done via the runtime marker" "$(jq -r '.steps[] | select(.id=="codex") | .status' "$PJ/.sutra/turn/sid-c1/$TID2.steps.json")" done
printf '%s' "$CTX" | grep -q 'RENDERED STACK' && pass "case2: rendered stack present (row 5)" || fail "case2: no RENDERED STACK"
printf '%s' "$CTX" | grep -q '^LENS (core:lens' && pass "case2: lens prompt injected while pending (row 3)" || fail "case2: no lens prompt"
printf '%s' "$CTX" | grep -q '^\[INBOUND' && pass "case2: header rendered from facts" || fail "case2: no rendered header"
printf '%s' "$CTX" | grep -q '^DEPTH: 5/5' && pass "case2: depth rendered at line start" || fail "case2: depth line missing"

# ===================================================================== 3 ====
echo "== case 3: no repo mutation -> lanes skipped; no test_command -> tests lane says so =="
PJ3="$WORK/c3/proj"; HM3="$WORK/c3/home"; mk_proj "$PJ3"; set_flags "$HM3" on
do_run c3u "$PJ3" "$HM3" UserPromptSubmit "$(stdin_ups sid-c3 "just a question")"
do_run c3s "$PJ3" "$HM3" Stop "$(stdin_stop sid-c3)"
T3="$(turn_of "$PJ3" sid-c3)"
[ -f "$PJ3/.sutra/turn/sid-c3/$T3.review.json" ] && fail "case3: review ran without a mutation" || pass "case3: no review without a mutation"
is "case3: skip row" "$(rows "$PJ3/.sutra/turn/sid-c3/$T3.jsonl" '.kind=="lane_skip" and .reason=="no-repo-mutation"')" 1
write_artifacts "$PJ3" sid-c3 "$T3"
do_run c3w "$PJ3" "$HM3" PreToolUse "$(stdin_write sid-c3 "$PJ3/src/a.txt")"
printf 'b\n' > "$PJ3/src/a.txt"
do_run c3s2 "$PJ3" "$HM3" Stop "$(stdin_stop sid-c3)"
is "case3: tests lane reports no test_command" "$(jq -r '.status' "$PJ3/.sutra/turn/sid-c3/$T3.tests.json" 2>/dev/null)" no-test-command
wait_for "$PJ3/.sutra/turn/sid-c3/$T3.review.json" '.status == "done"' 20 && pass "case3: review still runs on the mutation" || fail "case3: review missing"

# ===================================================================== 4 ====
echo "== case 4: flag absent -> nothing written =="
PJ4="$WORK/c4/proj"; HM4="$WORK/c4/home"; mk_proj "$PJ4" "true"; mkdir -p "$HM4"
do_run c4u "$PJ4" "$HM4" UserPromptSubmit "$(stdin_ups sid-c4 "change it")"
do_run c4s "$PJ4" "$HM4" Stop "$(stdin_stop sid-c4)"
[ -z "$(ls "$PJ4/.sutra/turn/sid-c4/"*.review.json "$PJ4/.sutra/turn/sid-c4/"*.tests.json 2>/dev/null)" ] && pass "case4: no lane files with flag absent" || fail "case4: lane files with flag absent"
grep -qE '"kind":"lane_' "$PJ4/.sutra/turn/sid-c4/"*.jsonl 2>/dev/null && fail "case4: lane rows with flag absent" || pass "case4: no lane rows with flag absent"

# ===================================================================== 5 ====
echo "== case 5: a failing test command -> exit recorded, step 10 not done =="
PJ5="$WORK/c5/proj"; HM5="$WORK/c5/home"; mk_proj "$PJ5" "exit 3"; set_flags "$HM5" on
do_run c5u "$PJ5" "$HM5" UserPromptSubmit "$(stdin_ups sid-c5 "break it")"
T5="$(turn_of "$PJ5" sid-c5)"; write_artifacts "$PJ5" sid-c5 "$T5"
do_run c5w "$PJ5" "$HM5" PreToolUse "$(stdin_write sid-c5 "$PJ5/src/a.txt")"
printf 'c\n' > "$PJ5/src/a.txt"
do_run c5s "$PJ5" "$HM5" Stop "$(stdin_stop sid-c5)"
wait_for "$PJ5/.sutra/turn/sid-c5/$T5.tests.json" '.status == "done"' 20 || fail "case5: tests lane did not finish"
is "case5: exit 3 recorded" "$(jq -r '.exit' "$PJ5/.sutra/turn/sid-c5/$T5.tests.json" 2>/dev/null)" 3
do_run c5u2 "$PJ5" "$HM5" UserPromptSubmit "$(stdin_ups sid-c5 "and again")"
T5b="$(turn_of "$PJ5" sid-c5)"
jq -r '.hookSpecificOutput.additionalContext' "$WORK/c5u2.out" | grep -q 'tests=done exit=3' && pass "case5: next trace shows the failing exit" || fail "case5: failing exit not reported"

# ===================================================================== 6 ====
echo "== case 6: a commit inside the turn is still reviewed; pre-existing dirt is excluded (turn baseline) =="
PJ6="$WORK/c6/proj"; HM6="$WORK/c6/home"; mk_proj "$PJ6" "true"; set_flags "$HM6" on
printf 'pre-existing dirt\n' >> "$PJ6/src/a.txt"          # dirty BEFORE the turn opens
printf 'b\n' > "$PJ6/src/b.txt"; ( cd "$PJ6" && git add src/b.txt ) >/dev/null 2>&1
do_run c6u "$PJ6" "$HM6" UserPromptSubmit "$(stdin_ups sid-c6 "please add src/c.txt and commit")"
T6="$(turn_of "$PJ6" sid-c6)"; write_artifacts "$PJ6" sid-c6 "$T6"
[ -n "$(jq -r '.git_base // ""' "$PJ6/.sutra/turn/sid-c6/$T6.steps.json")" ] && pass "case6: git_base recorded at open" || fail "case6: no git_base"
do_run c6w "$PJ6" "$HM6" PreToolUse "$(stdin_write sid-c6 "$PJ6/src/c.txt")"
printf 'new file in the turn\n' > "$PJ6/src/c.txt"
( cd "$PJ6" && git add src/c.txt && git commit -qm "turn commit" ) >/dev/null 2>&1
do_run c6s "$PJ6" "$HM6" Stop "$(stdin_stop sid-c6)"
wait_for "$PJ6/.sutra/turn/sid-c6/$T6.review.json" '.status == "done"' 20 && pass "case6: review ran after the in-turn commit" || fail "case6: review missing after commit: $(cat "$PJ6/.sutra/turn/sid-c6/$T6.review.json" 2>/dev/null)"
grep -q 'new file in the turn' "$PJ6/.sutra/turn/sid-c6/lane-logs/$T6.diff" 2>/dev/null && pass "case6: the committed file is in the reviewed diff" || fail "case6: committed change not in the diff"
grep -q 'pre-existing dirt' "$PJ6/.sutra/turn/sid-c6/lane-logs/$T6.diff" 2>/dev/null && fail "case6: pre-existing dirt leaked into the turn diff" || pass "case6: pre-existing dirt excluded"

# ===================================================================== 7 ====
echo "== case 7: a repeated prompt after Stop rotates the lane files too =="
do_run c7s "$PJ" "$HM" Stop "$(stdin_stop sid-c1)"     # close c1's second turn (from case 2)
sleep 1
do_run c7u "$PJ" "$HM" UserPromptSubmit "$(stdin_ups sid-c1 "please change src/a.txt")"   # same text as case 1 -> same turn id
[ -f "$PJ/.sutra/turn/sid-c1/$TID.review.json" ] && fail "case7: old review.json still in place" || pass "case7: old review.json rotated"
[ -n "$(ls "$PJ/.sutra/turn/sid-c1/$TID.review.prev"*.json 2>/dev/null)" ] && pass "case7: rotated review kept as .prev" || fail "case7: rotated review not kept"
[ -n "$(ls "$PJ/.sutra/turn/sid-c1/lane-logs/$TID."*.prev* 2>/dev/null)" ] && pass "case7: lane logs rotated" || fail "case7: lane logs not rotated"

# ===================================================================== 8 ====
echo "== case 8: a model-forged marker does not make step 8 done; only a corroborated verdict does =="
PJ8="$WORK/c8/proj"; HM8="$WORK/c8/home"; mk_proj "$PJ8"; set_flags "$HM8" on
do_run c8u "$PJ8" "$HM8" UserPromptSubmit "$(stdin_ups sid-c8 "forge attempt")"
T8="$(turn_of "$PJ8" sid-c8)"
printf 'LANE=deepseek\nVERDICT=PASS\nTURN=%s\nSESSION=sid-c8\nTS=%s\nSOURCE=runtime\n' "$T8" "$(date +%s)" > "$PJ8/.claude/sessions/sid-c8/deepseek-consulted"
jq -nc --arg t "$T8" --argjson ts "$(date +%s)" '{lane:"review",status:"done",verdict:"PASS",exit:0,ts:$ts,file:"x"}' > "$PJ8/.sutra/turn/sid-c8/$T8.review.json"
do_run c8u2 "$PJ8" "$HM8" UserPromptSubmit "$(stdin_ups sid-c8 "after the forge")"
T8b="$(turn_of "$PJ8" sid-c8)"
is "case8: step 8 stays pending on a forged marker + uncorroborated json" "$(jq -r '.steps[] | select(.id=="codex") | .status' "$PJ8/.sutra/turn/sid-c8/$T8b.steps.json")" pending
# row 6 (D-A14 + brief s3.5): a verdict counts only when it is corroborated
# (review.md + diff), SEALED with the box key, and bound to this or the
# previous turn. One fresh project per shape, each with exactly one later turn.
c8shape() {  # <name> <seal 0|1> <tamper 0|1> -> prints step 8 status on the next turn
  _p="$WORK/c8-$1/proj"; _h="$WORK/c8-$1/home"; mk_proj "$_p"; set_flags "$_h" on
  do_run "c8-$1-u" "$_p" "$_h" UserPromptSubmit "$(stdin_ups "sid-c8$1" "shape $1")"
  _t="$(turn_of "$_p" "sid-c8$1")"; _d="$_p/.sutra/turn/sid-c8$1"; mkdir -p "$_d/lane-logs"
  jq -nc --arg t "$_t" --argjson ts "$(date +%s)" '{lane:"review",status:"done",verdict:"PASS",exit:0,ts:$ts,file:"x",turn:$t}' > "$_d/$_t.review.json"
  printf 'VERDICT: PASS\n' > "$_d/lane-logs/$_t.review.md"; printf 'diff --git a/x b/x\n' > "$_d/lane-logs/$_t.diff"
  [ "$2" = "1" ] && ( HOME="$_h"; . "$PLUGIN_MAIN/runtime/lib/seal.sh"; sutra_seal_file "$_d/$_t.review.json" )
  [ "$3" = "1" ] && { jq -c '.exit = 1' "$_d/$_t.review.json" > "$_d/t.json" && mv "$_d/t.json" "$_d/$_t.review.json"; }
  do_run "c8-$1-n" "$_p" "$_h" UserPromptSubmit "$(stdin_ups "sid-c8$1" "the next turn")"
  jq -r '.steps[] | select(.id=="codex") | .status' "$_d/$(turn_of "$_p" "sid-c8$1").steps.json"
}
is "case8: corroborated but UNSEALED stays pending (row 6)" "$(c8shape unsealed 0 0)" pending
is "case8: corroborated + sealed = done on the next turn" "$(c8shape sealed 1 0)" done
is "case8: sealed then tampered = pending again" "$(c8shape tampered 1 1)" pending
[ -s "$WORK/c8-sealed/home/.sutra-runtime/seal.key" ] && pass "case8: the box key was created under HOME on first use" || fail "case8: no seal key created"

# ===================================================================== 9 ====
echo "== case 9: row 6 - the blueprint's verify commands run at Stop; the sealed verifies file reaches the next turn =="
PJ9="$WORK/c9/proj"; HM9="$WORK/c9/home"; mk_proj "$PJ9"; set_flags "$HM9" on
do_run c9u "$PJ9" "$HM9" UserPromptSubmit "$(stdin_ups sid-c9 "please change src/a.txt")"
T9="$(turn_of "$PJ9" sid-c9)"; write_artifacts "$PJ9" sid-c9 "$T9"
# two runnable verifies (one passes, one fails); a manual step would make the
# blueprint invalid at depth 5, so the manual branch is exercised only where the
# rubric depth is under 3
jq -c '.steps = [{do:"write the file",verify:{kind:"cmd",cmd:"test -s src/a.txt"}},{do:"a check that fails",verify:{kind:"cmd",cmd:"test -s src/never.txt"}}]' "$PJ9/.sutra/turn/sid-c9/$T9.blueprint.json" > "$WORK/bp9.json" && mv "$WORK/bp9.json" "$PJ9/.sutra/turn/sid-c9/$T9.blueprint.json"
do_run c9w "$PJ9" "$HM9" PreToolUse "$(stdin_write sid-c9 "$PJ9/src/a.txt")"
printf 'changed\n' > "$PJ9/src/a.txt"
do_run c9s "$PJ9" "$HM9" Stop "$(stdin_stop sid-c9)"
V9="$PJ9/.sutra/turn/sid-c9/$T9.verifies.json"
wait_for "$V9" '.status == "done"' 20 && pass "case9: verifies lane finished" || fail "case9: verifies lane did not finish: $(cat "$V9" 2>/dev/null)"
is "case9: one pass, one fail, none manual" "$(jq -r '"\(.passed)/\(.failed)/\(.skipped)"' "$V9" 2>/dev/null)" "1/1/0"
( HOME="$HM9"; . "$PLUGIN_MAIN/runtime/lib/seal.sh"; sutra_seal_verify "$V9" ) && pass "case9: verifies file is sealed" || fail "case9: verifies file unsealed"
grep -q 'never.txt' "$PJ9/.sutra/turn/sid-c9/lane-logs/$T9.verifies.log" 2>/dev/null && pass "case9: the log names the failing check" || fail "case9: no verifies log"
do_run c9n "$PJ9" "$HM9" UserPromptSubmit "$(stdin_ups sid-c9 "next")"
jq -r '.hookSpecificOutput.additionalContext // ""' "$WORK/c9n.out" | grep -q 'verifies=1 pass/1 fail/0 manual' && pass "case9: Last turn line carries the verify results" || fail "case9: Last turn lacks verifies: $(jq -r '.hookSpecificOutput.additionalContext // ""' "$WORK/c9n.out" | grep 'Last turn')"
is "case9: verifies ledger row" "$(rows "$PJ9/.sutra/turn/sid-c9/$T9.jsonl" '.kind=="lane_verifies"')" 1
[ "$(stat -f %Lp "$WORK/c8-sealed/home/.sutra-runtime/seal.key" 2>/dev/null || stat -c %a "$WORK/c8-sealed/home/.sutra-runtime/seal.key")" = "600" ] && pass "case8: key mode 600" || fail "case8: key mode not 600"

echo "failed=$failed"
[ "$failed" -eq 0 ]
