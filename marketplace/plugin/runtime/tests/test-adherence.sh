#!/usr/bin/env bash
# test-adherence.sh - adherence row 1: the step ledger (ups.steps_ledger),
# the gate (pre.adherence_gate) and the close (stop.steps_close). Every case
# runs the WHOLE `bin/sutra-turn run --event <E>` against a real plugin tree
# (a min copy with the three steps removed for the parity case), never a
# step script in isolation.
#
# ENVIRONMENT ISOLATION: every invocation strips CLAUDE_CODE_SESSION_ID and
# CLAUDE_SESSION_ID (see test-markers-step.sh for why) and runs under a
# private HOME, so the founder's own flags are never read.
#
# bash 3.2 compatible: no associative arrays, no ${var,,}, no mapfile.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-adherence.sh

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
[ -x "$PLUGIN_MAIN/bin/sutra-turn" ] || { fail "bin/sutra-turn missing at $PLUGIN_MAIN"; echo "failed=$failed"; exit 1; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-adherence.XXXXXX")"
if [ -z "${KEEP_WORK:-}" ]; then trap 'rm -rf "$WORK"' EXIT; else echo "work dir kept: $WORK"; fi

# ------------------------------------------------------------------ helpers --
mk_proj() {  # <proj> : a company-profile project so depth rubric = 5 (irrelevant here, but realistic)
  mkdir -p "$1/.claude/sessions" "$1/.sutra"
  printf '{"profile":"company"}\n' > "$1/.claude/sutra-project.json"
}
set_flags() {  # <home> <markers> <adherence>   ("" = absent)
  mkdir -p "$1"
  [ -n "$2" ] && printf '%s\n' "$2" > "$1/$F_MARK"
  [ -n "$3" ] && printf '%s\n' "$3" > "$1/$F_ADH"
  return 0
}
stdin_ups()   { jq -nc --arg sid "$1" --arg p "$2" '{session_id:$sid, hook_event_name:"UserPromptSubmit", prompt:$p}'; }
stdin_write() { jq -nc --arg sid "$1" --arg f "$2" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Write", tool_input:{file_path:$f, content:"x"}}'; }
stdin_bash()  { jq -nc --arg sid "$1" --arg c "$2" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Bash", tool_input:{command:$c}}'; }
stdin_task()  { jq -nc --arg sid "$1" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Task", tool_input:{description:"explore", prompt:"look"}}'; }
stdin_stop()  { jq -nc --arg sid "$1" --arg m "$2" '{session_id:$sid, hook_event_name:"Stop", last_assistant_message:$m}'; }

# do_run <name> <plugin_root> <proj> <home> <event> <stdin-json> [extra env ...] -> RC, $WORK/<name>.out/.err
do_run() {
  _n="$1"; _pr="$2"; _pj="$3"; _hm="$4"; _ev="$5"; _in="$6"; shift 6
  mkdir -p "$_pj" "$_hm"
  printf '%s' "$_in" > "$WORK/$_n.stdin.json"
  env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID "$@" \
    CLAUDE_PROJECT_DIR="$_pj" CLAUDE_PLUGIN_ROOT="$_pr" HOME="$_hm" RTK_SKIP=1 \
    "$_pr/bin/sutra-turn" run --event "$_ev" \
    < "$WORK/$_n.stdin.json" > "$WORK/$_n.out" 2> "$WORK/$_n.err"
  RC=$?
}
turn_of()   { cat "$1/.sutra/turn/$2/current" 2>/dev/null; }
ledger_of() { printf '%s/.sutra/turn/%s/%s.steps.json' "$1" "$2" "$3"; }
ctx_of()    { jq -r '.hookSpecificOutput.additionalContext // ""' "$WORK/$1.out" 2>/dev/null; }
deny_reason_of() { jq -r 'select(.hookSpecificOutput.permissionDecision == "deny") | .hookSpecificOutput.permissionDecisionReason // ""' "$WORK/$1.out" 2>/dev/null; }
sysmsg_of() { jq -r '.systemMessage // ""' "$WORK/$1.out" 2>/dev/null; }
adherence_denied() { deny_reason_of "$1" | grep -q 'ADHERENCE GATE'; }
adherence_warned() { sysmsg_of "$1" | grep -q 'ADHERENCE GATE'; }
rows() { jq -s "[.[] | select($2)] | length" "$1" 2>/dev/null; }
write_artifacts() {  # <proj> <sid> <turn> <ts> [lens-extra-jq] [cyn-extra-jq]
  _d="$1/.sutra/turn/$2"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$4" "{turn_id:\$t,session_id:\$sid,producer:\"model\",step:\"lens\",unit:\"add the adherence gate to the runtime\",axes:[\"decide-vs-verify\",\"runtime-vs-model\"],pick:[\"runtime-vs-model\"],direction:\"DOWN\",ts:\$ts} ${5:-}" > "$_d/$3.lens.json"
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$4" "{turn_id:\$t,session_id:\$sid,producer:\"model\",step:\"cynefin\",unit:\"add the adherence gate to the runtime\",domain:\"complicated\",shape:\"sequence with expert review before landing\",human_gate:false,ts:\$ts} ${6:-}" > "$_d/$3.cynefin.json"
  # row 6 (R4): these projects have no placement engine, so a new path needs the placement artifact
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$4" '{turn_id:$t,session_id:$sid,producer:"model",step:"placement",unit:"add the adherence gate to the runtime",domain_ref:"dref-0123456789abcdef",charter_id:"C-0123456789abcdef",reason:"test project placed under the test domain",confidence:0.9,ts:$ts}' > "$_d/$3.placement.json"
  # row 6 (R6): the blueprint artifact, with runnable verifies (depth 5 in these projects)
  jq -nc --arg t "$3" --arg sid "$2" --argjson ts "$4" "{turn_id:\$t,session_id:\$sid,producer:\"model\",step:\"blueprint\",unit:\"add the adherence gate to the runtime\",doing:\"add the gate step\",steps:[{do:\"write the step\",verify:{kind:\"cmd\",cmd:\"test -f runtime/steps/adherence_gate.sh\"}}],output:\"the step file exists and the suite is green\",verified_by:{kind:\"cmd\",cmd:\"bash runtime/tests/test-adherence.sh\"},stops_if:\"the suite fails\",ts:\$ts} ${7:-}" > "$_d/$3.blueprint.json"
}

# copy_plugin_min <dest>: the WHOLE plugin tree minus the golden corpus and the
# desktop app (both large, neither read by a hook). A partial copy is not a
# parity control: several Stop shims read os/, commands/ or skills/ and emit
# differently when those are missing (seen on the repo tree, 2026-09-17).
copy_plugin_min() {
  _d="$1"; mkdir -p "$_d"
  cp -R "$PLUGIN_MAIN/." "$_d/"
  rm -rf "$_d/hooks/tests" "$_d/sutra-ui" "$_d/.sutra" "$_d/.in_use" 2>/dev/null
  chmod -R u+w "$_d" 2>/dev/null || true
}

# A standard "turn": UPS with both flags on, returns TID/OPENED via globals.
open_turn() {  # <name> <proj> <home> <sid> [prompt]
  do_run "$1" "$PLUGIN_MAIN" "$2" "$3" UserPromptSubmit "$(stdin_ups "$4" "${5:-please add the adherence gate to the runtime}")"
  TID="$(turn_of "$2" "$4")"
  OPENED="$(jq -r '.opened_ts // 0' "$(ledger_of "$2" "$4" "$TID")" 2>/dev/null)"
}

# ===================================================================== 1 ====
echo "== case 1: parity - flag absent, three events, byte-identical stdout vs a plugin copy without the three steps =="
PB="$WORK/plugin-before"; copy_plugin_min "$PB"
jq 'del(.adherence) | .events.UserPromptSubmit |= map(select(.id != "ups.steps_ledger")) | .events.PreToolUse |= map(select(.id != "pre.adherence_gate")) | .events.Stop |= map(select(.id != "stop.steps_close"))' \
  "$PLUGIN_MAIN/runtime/pipeline.json" > "$PB/runtime/pipeline.json"
rm -f "$PB/runtime/steps/steps_ledger.sh" "$PB/runtime/steps/adherence_gate.sh" "$PB/runtime/steps/steps_close.sh"
for ev in UserPromptSubmit PreToolUse Stop; do
  for side in after before; do
    PJ="$WORK/c1-$side-$ev/proj"; HM="$WORK/c1-$side-$ev/home"; mk_proj "$PJ"; set_flags "$HM" "" ""
    [ "$side" = after ] && PR="$PLUGIN_MAIN" || PR="$PB"
    case "$ev" in
      UserPromptSubmit) IN="$(stdin_ups sid-c1 "please add the adherence gate")" ;;
      PreToolUse)       IN="$(stdin_write sid-c1 "$PJ/src/a.txt")" ;;
      Stop)             IN="$(stdin_stop sid-c1 "reply")" ;;
    esac
    # Timeouts x4: under tests/run-all.sh (charcap just ran) a class-B Stop shim can be
    # watchdog-killed on one side only, and a lost decision is not a parity signal.
    do_run "c1-$side-$ev" "$PR" "$PJ" "$HM" "$ev" "$IN" SUTRA_STEP_TIMEOUT_SCALE=400
  done
  # Normalise the two plugin roots (the golden normaliser does the same for <PLUGIN_ROOT>) and
  # drop watchdog-timeout systemMessages: 60+ sutra-turn runs in one suite make a 5000 ms step
  # time out at random on a loaded box, and that is not a parity signal (charcap runs isolated).
  norm_out() {
    sed -e "s|$2|<PLUGIN>|g" "$1" | { jq -c 'if ((.systemMessage // "") | test("^sutra runtime degraded")) then del(.systemMessage) else . end | if . == {} then empty else . end' 2>/dev/null || cat; }
  }
  norm_out "$WORK/c1-after-$ev.out" "$PLUGIN_MAIN" > "$WORK/c1-after-$ev.norm"
  norm_out "$WORK/c1-before-$ev.out" "$PB" > "$WORK/c1-before-$ev.norm"
  if cmp -s "$WORK/c1-after-$ev.norm" "$WORK/c1-before-$ev.norm"; then pass "case1: $ev stdout byte-identical with flag absent"
  else fail "case1: $ev stdout differs with flag absent: $(diff <(tr ',' '\n' < "$WORK/c1-before-$ev.norm") <(tr ',' '\n' < "$WORK/c1-after-$ev.norm") | head -6)"; fi
  [ -z "$(ls "$WORK/c1-after-$ev/proj/.sutra/turn/sid-c1/"*.steps.json 2>/dev/null)" ] && pass "case1: $ev no steps.json with flag absent" || fail "case1: $ev wrote a steps.json with flag absent"
  grep -qE 'steps_ledger|adherence_gate|steps_close|sutra_steps|sutra_artifact|sutra_prompt' "$WORK/c1-after-$ev.err" \
    && fail "case1: $ev stderr mentions an adherence step with flag absent: $(grep -E 'steps_|adherence|sutra_' "$WORK/c1-after-$ev.err" | head -2)" \
    || pass "case1: $ev stderr silent about the adherence steps"
  grep -qE '"kind":"(steps_|adherence_)' "$WORK/c1-after-$ev/proj/.sutra/turn/sid-c1/"*.jsonl 2>/dev/null \
    && fail "case1: $ev wrote adherence ledger rows with flag absent" || pass "case1: $ev no adherence ledger rows with flag absent"
done

# ===================================================================== 2 ====
echo "== case 2: flag on - ledger opened, runtime steps done, STEP TRACE names both artifact paths =="
PJ="$WORK/c2/proj"; HM="$WORK/c2/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c2 "$PJ" "$HM" sid-c2
TID2="$TID"; OPENED2="$OPENED"   # open_turn overwrites TID/OPENED; cases 10-12 need this project's
is "case2: exit 0" "$RC" 0
L="$(ledger_of "$PJ" sid-c2 "$TID")"
[ -f "$L" ] && pass "case2: steps.json exists" || fail "case2: steps.json missing at $L"
is "case2: 11 steps" "$(jq '.steps | length' "$L" 2>/dev/null)" 11
is "case2: classify done" "$(jq -r '.steps[0].status' "$L")" done
is "case2: resolve done"  "$(jq -r '.steps[1].status' "$L")" done
is "case2: depth done"    "$(jq -r '.steps[2].status' "$L")" done
is "case2: lens pending"  "$(jq -r '.steps[4].status' "$L")" pending
CTX="$(ctx_of c2)"
printf '%s' "$CTX" | grep -q "STEP TRACE turn $(printf '%s' "$TID" | head -c 8)" && pass "case2: trace in additionalContext" || fail "case2: no STEP TRACE in additionalContext"
printf '%s' "$CTX" | grep -q "$TID.lens.json" && pass "case2: trace names lens path" || fail "case2: trace lacks lens path"
printf '%s' "$CTX" | grep -q "$TID.cynefin.json" && pass "case2: trace names cynefin path" || fail "case2: trace lacks cynefin path"
TRACE_ONLY="$(printf '%s\n' "$CTX" | sed -n '/^STEP TRACE turn/,/^Paste the STEP TRACE/p')"
[ -n "$TRACE_ONLY" ] || fail "case2: could not isolate the trace section"
printf '%s' "$TRACE_ONLY" | LC_ALL=C grep -q $'[^ -~\t]' && fail "case2: trace has non-ASCII bytes: $(printf '%s' "$TRACE_ONLY" | LC_ALL=C grep $'[^ -~\t]' | head -2)" || pass "case2: trace is ASCII"
is "case2: steps_open row" "$(rows "$PJ/.sutra/turn/sid-c2/$TID.jsonl" '.kind=="steps_open"')" 1

# ===================================================================== 3 ====
echo "== case 3: on, Write to a repo path, no artifacts -> deny naming lens + cynefin =="
do_run c3 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")"
adherence_denied c3 && pass "case3: adherence deny emitted" || fail "case3: no adherence deny: $(head -c 300 "$WORK/c3.out")"
deny_reason_of c3 | grep -q "lens.json (missing)" && pass "case3: reason names lens path" || fail "case3: reason lacks lens path"
deny_reason_of c3 | grep -q "cynefin.json (missing)" && pass "case3: reason names cynefin path" || fail "case3: reason lacks cynefin path"
deny_reason_of c3 | grep -q "turn_id=$TID" && pass "case3: reason carries the turn id" || fail "case3: reason lacks turn id"
is "case3: mutation row deny" "$(jq -r '.mutations[-1].decision' "$L")" deny
is "case3: missing list (row 6: unmet rule ids)" "$(jq -c '.mutations[-1].missing' "$L")" '["R4","R5","R6"]'

# ===================================================================== 4 ====
echo "== case 4: valid artifacts -> allowed, steps 5-6 done =="
write_artifacts "$PJ" sid-c2 "$TID" "$OPENED"
do_run c4 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")"
adherence_denied c4 && fail "case4: denied with valid artifacts: $(deny_reason_of c4 | head -3)" || pass "case4: no adherence deny"
is "case4: lens done"    "$(jq -r '.steps[4].status' "$L")" done
is "case4: cynefin done" "$(jq -r '.steps[5].status' "$L")" done
is "case4: mutation row allow" "$(jq -r '.mutations[-1].decision' "$L")" allow
sysmsg_of c4 | grep -q '^\[sutra [0-9a-f]\{8\}\] .*lens done (' && pass "case4: live line printed for lens (2.285.1 form)" || fail "case4: no live line: $(head -c 200 "$WORK/c4.out")"
sysmsg_of c4 | grep -q 'cynefin done (complicated)' && pass "case4: live line printed for cynefin" || fail "case4: no cynefin live line"
sysmsg_of c4 | grep -q 'pending ->' && fail "case4: live line still carries the from-state noise" || pass "case4: live line is the compact form"
is "case4: transition row" "$(rows "$PJ/.sutra/turn/sid-c2/$TID.jsonl" '.kind=="adherence_transition"')" 1

# ===================================================================== 5 ====
echo "== case 5: stale turn_id / ts before open / hollow artifacts -> deny with the exact reason =="
write_artifacts "$PJ" sid-c2 "$TID" "$OPENED" '| .turn_id = "deadbeef"'
do_run c5a "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")"
deny_reason_of c5a | grep -q "stale-turn" && pass "case5a: stale turn refused" || fail "case5a: stale turn not refused"
write_artifacts "$PJ" sid-c2 "$TID" "$((OPENED - 10))"
do_run c5b "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")"
deny_reason_of c5b | grep -q "ts-before-turn-open" && pass "case5b: old ts refused" || fail "case5b: old ts not refused"
write_artifacts "$PJ" sid-c2 "$TID" "$OPENED" '| .pick = ["not-an-axis"]' '| .shape = "short"'
do_run c5c "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")"
deny_reason_of c5c | grep -q "pick-not-subset-of-axes" && pass "case5c: hollow lens refused" || fail "case5c: hollow lens accepted"
deny_reason_of c5c | grep -q "shape-under-20-chars" && pass "case5c: hollow cynefin refused" || fail "case5c: hollow cynefin accepted"
write_artifacts "$PJ" sid-c2 "$TID" "$OPENED"   # restore valid

# ===================================================================== 6 ====
echo "== case 6: the artifact write itself and other exempt paths are never refused =="
rm -f "$PJ/.sutra/turn/sid-c2/$TID.lens.json" "$PJ/.sutra/turn/sid-c2/$TID.cynefin.json"
do_run c6a "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/.sutra/turn/sid-c2/$TID.lens.json")"
adherence_denied c6a && fail "case6a: artifact write refused (deadlock)" || pass "case6a: artifact write exempt"
is "case6a: row exempt" "$(jq -r '.mutations[-1].decision' "$L")" exempt
do_run c6b "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/.claude/sessions/sid-c2/depth-registered")"
adherence_denied c6b && fail "case6b: session marker write refused" || pass "case6b: session marker exempt"
do_run c6c "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "/Users/x/.claude/projects/p/memory/note.md")"
adherence_denied c6c && fail "case6c: memory write refused" || pass "case6c: memory file exempt"
do_run c6d "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c2 "printf x > $PJ/.sutra/turn/sid-c2/$TID.lens.json")"
adherence_denied c6d && fail "case6d: bash artifact write refused (codex P1-1)" || pass "case6d: bash artifact write exempt"

# ===================================================================== 7 ====
echo "== case 7: bash classing matrix =="
for c in "git status" "ls -la" "grep -rn foo ." "cat README.md" "jq . x.json" "git diff HEAD~1" \
         "git status 2>/dev/null" "command -v jq >/dev/null 2>&1" "ls -la 2>&1" "git log --oneline -3 &>/dev/null"; do
  do_run c7r "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c2 "$c")"
  adherence_denied c7r && fail "case7: read-only misclassed: $c" || pass "case7: read-only allowed: $c"
done
for c in "printf x > f.txt" "rm -f f.txt" "git commit -m x" "sed -i s/a/b/ f.txt" "mkdir d" "cp a b" "bash -c 'echo x > f'" "git push origin main" \
         "git merge feature" "git rebase main" "git cherry-pick abc123" \
         "git commit -m x
bash holding/bin/sutra-atom close a-1" \
         "sutra-marker read depth-registered && rm -rf src" \
         "rm -rf src; sutra-dispatch show" \
         "echo x > .sutra/turn/sid-c2/other.json && rm -rf src" \
         "echo 'x\\' ; rm -rf src" \
         "jq -n '{}' > .sutra/turn/sid-c2/x.review.json" \
         "jq -n '{}' > .sutra/turn/sid-c2/../escape.lens.json" \
         "/tmp/evil/sutra-atom-x close a-1 && rm -rf src"; do
  do_run c7m "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c2 "$c")"
  # row 6: a write to a lane/ledger file is refused earlier, as runtime-owned (R9); either refusal is the point
  { adherence_denied c7m || deny_reason_of c7m | grep -q 'RUNTIME-OWNED PATH'; } && pass "case7: mutation refused: $(printf '%s' "$c" | tr '\n' '|')" || fail "case7: mutation slipped: $(printf '%s' "$c" | tr '\n' '|')"
done
for c in "bash holding/bin/sutra-atom close a-1" "bash holding/bin/sutra-atom close a-1 && bash holding/bin/sutra-dispatch show" "sutra-steps latest | head -20" \
         "jq -nc '{a:1}' > .sutra/turn/sid-c2/x.lens.json; ls .sutra/turn/sid-c2/ | wc -l" \
         "jq -nc '{shape:\"a; b | c\"}' > .sutra/turn/sid-c2/x.cynefin.json" \
         "cd /somewhere && jq -n '{}' > .sutra/turn/sid-c2/y.lens.json"; do
  do_run c7e "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c2 "$c")"
  adherence_denied c7e && fail "case7: exempt command refused: $c" || pass "case7: exempt command allowed: $c"
done
do_run c7t "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_task sid-c2)"
adherence_denied c7t && pass "case7: Task refused without artifacts (D-A7)" || fail "case7: Task allowed without artifacts"

# ===================================================================== 8 ====
echo "== case 8: warn mode - systemMessage, no permissionDecision =="
PJ8="$WORK/c8/proj"; HM8="$WORK/c8/home"; mk_proj "$PJ8"; set_flags "$HM8" on warn
open_turn c8 "$PJ8" "$HM8" sid-c8
do_run c8w "$PLUGIN_MAIN" "$PJ8" "$HM8" PreToolUse "$(stdin_write sid-c8 "$PJ8/src/a.txt")"
adherence_denied c8w && fail "case8: warn mode denied" || pass "case8: no deny in warn"
adherence_warned c8w && pass "case8: systemMessage carries the warning" || fail "case8: no warning systemMessage: $(head -c 200 "$WORK/c8w.out")"
is "case8: row warn" "$(jq -r '.mutations[-1].decision' "$(ledger_of "$PJ8" sid-c8 "$TID")")" warn

# ===================================================================== 9 ====
echo "== case 9: kill-switch precedence =="
PJ9="$WORK/c9/proj"; HM9="$WORK/c9/home"; mk_proj "$PJ9"; set_flags "$HM9" on on
do_run c9a "$PLUGIN_MAIN" "$PJ9" "$HM9" UserPromptSubmit "$(stdin_ups sid-c9 "please add the gate")" SUTRA_RUNTIME_DISABLED=1
[ -z "$(ls "$PJ9/.sutra/turn/sid-c9/"*.steps.json 2>/dev/null)" ] && pass "case9a: SUTRA_RUNTIME_DISABLED wins" || fail "case9a: ledger written under kill-switch"
ctx_of c9a | grep -q "STEP TRACE" && fail "case9a: trace under kill-switch" || pass "case9a: no trace under kill-switch"
touch "$HM9/$F_DIS"
do_run c9b "$PLUGIN_MAIN" "$PJ9" "$HM9" UserPromptSubmit "$(stdin_ups sid-c9 "please add the gate")"
[ -z "$(ls "$PJ9/.sutra/turn/sid-c9/"*.steps.json 2>/dev/null)" ] && pass "case9b: adherence-disabled file wins" || fail "case9b: ledger written under adherence-disabled"
rm -f "$HM9/$F_DIS"
do_run c9c "$PLUGIN_MAIN" "$PJ9" "$HM9" UserPromptSubmit "$(stdin_ups sid-c9 "please add the gate")" SUTRA_RUNTIME_ADHERENCE=off
[ -z "$(ls "$PJ9/.sutra/turn/sid-c9/"*.steps.json 2>/dev/null)" ] && pass "case9c: env off beats file on" || fail "case9c: env off ignored"

# ==================================================================== 10 ====
echo "== case 10: Stop closes the ledger; trace_pasted recorded; sutra-steps prints =="
TID="$TID2"; OPENED="$OPENED2"
write_artifacts "$PJ" sid-c2 "$TID" "$OPENED"
do_run c10 "$PLUGIN_MAIN" "$PJ" "$HM" Stop "$(stdin_stop sid-c2 "[INBOUND·DIRECT]
STEP TRACE turn $(printf '%s' "$TID" | head -c 8) (adherence=on)
done")"
is "case10: close done" "$(jq -r '.steps[10].status' "$L")" done
is "case10: trace_pasted" "$(jq -r '.closed.trace_pasted' "$L")" true
sysmsg_of c10 | grep -q '^sutra turn [0-9a-f]\{8\} .*done [0-9]*/11' && pass "case10: the final step prints the whole table at Stop (2.285.1 form)" || fail "case10: no final table at Stop: $(head -c 200 "$WORK/c10.out")"
is "case10: final table has one checkbox row per step" "$(sysmsg_of c10 | grep -c '^  \[[x o~!]\] ')" 11
sysmsg_of c10 | grep -q '^  \[x\] close      closed at Stop' && pass "case10: close row is done" || fail "case10: close row wrong: $(sysmsg_of c10 | grep 'close' | head -1)"
CLAUDE_PROJECT_DIR="$PJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-c2 latest 2>/dev/null | grep -qE '^ *11 close +runtime +done' && pass "case10: row 11 reads done in the STEP TRACE form" || fail "case10: row 11 not done in the STEP TRACE form"
[ "$(jq -r '.closed.refused' "$L")" -ge 1 ] && pass "case10: refused count kept" || fail "case10: refused count lost"
is "case10: steps_close row" "$(rows "$PJ/.sutra/turn/sid-c2/$TID.jsonl" '.kind=="steps_close"')" 1
OUT="$(CLAUDE_PROJECT_DIR="$PJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-c2 latest 2>&1)"
printf '%s' "$OUT" | grep -q "STEP TRACE turn" && pass "case10: sutra-steps prints the table" || fail "case10: sutra-steps output: $OUT"
printf '%s' "$OUT" | grep -q "DENY  Write" && pass "case10: sutra-steps lists the refusal" || fail "case10: sutra-steps lacks the refusal line"
do_run c10b "$PLUGIN_MAIN" "$PJ8" "$HM8" Stop "$(stdin_stop sid-c8 "no trace here")"
is "case10b: trace_pasted false" "$(jq -r '.closed.trace_pasted' "$(ledger_of "$PJ8" sid-c8 "$(turn_of "$PJ8" sid-c8)")")" false

# ==================================================================== 11 ====
echo "== case 11: synthetic prompts (task notification) open no ledger and write no facts =="
PJ11="$WORK/c11/proj"; HM11="$WORK/c11/home"; mk_proj "$PJ11"; set_flags "$HM11" on on
do_run c11 "$PLUGIN_MAIN" "$PJ11" "$HM11" UserPromptSubmit "$(stdin_ups sid-c11 "<task-notification><task-id>x</task-id></task-notification>")"
[ -z "$(ls "$PJ11/.sutra/turn/sid-c11/"*.steps.json 2>/dev/null)" ] && pass "case11: no ledger on notification" || fail "case11: ledger on notification"
[ -z "$(ls "$PJ11/.sutra/turn/sid-c11/"*.facts.json 2>/dev/null)" ] && pass "case11: no facts on notification (markers_write shares the guard)" || fail "case11: facts on notification"
do_run c11b "$PLUGIN_MAIN" "$PJ11" "$HM11" UserPromptSubmit "$(stdin_ups sid-c11 "[SYSTEM NOTIFICATION - NOT USER INPUT] something")"
[ -z "$(ls "$PJ11/.sutra/turn/sid-c11/"*.steps.json 2>/dev/null)" ] && pass "case11b: no ledger on system notification" || fail "case11b: ledger on system notification"

# ==================================================================== 12 ====
echo "== case 12: missing ledger (UPS step lost) -> allow + bootstrap row, never refuse =="
rm -f "$L"
do_run c12 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c2 "$PJ/src/a.txt")"
adherence_denied c12 && fail "case12: refused without a ledger" || pass "case12: allowed without a ledger"
is "case12: bootstrap row" "$(rows "$PJ/.sutra/turn/sid-c2/$TID.jsonl" '.kind=="adherence_decision" and .reason=="bootstrap-no-ledger"')" 1

# ==================================================================== 13 ====
echo "== case 13: re-running UPS for the same turn keeps opened_ts, mutations and closed (merge, not replace) =="
open_turn c13 "$PJ8" "$HM8" sid-c8
O1="$OPENED"; L13="$(ledger_of "$PJ8" sid-c8 "$TID")"
do_run c13m "$PLUGIN_MAIN" "$PJ8" "$HM8" PreToolUse "$(stdin_write sid-c8 "$PJ8/src/b.txt")"
M1="$(jq '.mutations | length' "$L13")"
sleep 1
open_turn c13b "$PJ8" "$HM8" sid-c8
is "case13: opened_ts preserved" "$OPENED" "$O1"
is "case13: mutations preserved across re-run" "$(jq '.mutations | length' "$L13")" "$M1"
[ "$M1" -ge 1 ] && pass "case13: a mutation row existed to preserve" || fail "case13: no mutation row was recorded before the re-run"
echo "== case 13b: the SAME prompt after Stop closed the ledger is a new occurrence: fresh opened_ts, artifacts rotated =="
write_artifacts "$PJ8" sid-c8 "$TID" "$OPENED"
do_run c13s "$PLUGIN_MAIN" "$PJ8" "$HM8" Stop "$(stdin_stop sid-c8 "done")"
is "case13b: ledger closed" "$(jq -r 'if .closed == null then "open" else "closed" end' "$L13")" closed
sleep 1
open_turn c13c "$PJ8" "$HM8" sid-c8
[ "$OPENED" -gt "$O1" ] && pass "case13b: opened_ts advanced ($O1 -> $OPENED)" || fail "case13b: opened_ts not advanced ($O1 -> $OPENED)"
is "case13b: mutations reset" "$(jq '.mutations | length' "$L13")" 0
is "case13b: closed reset" "$(jq -r '.closed' "$L13")" null
[ -f "$PJ8/.sutra/turn/sid-c8/$TID.lens.json" ] && fail "case13b: old lens artifact still in place" || pass "case13b: old lens artifact rotated away"
[ -n "$(ls "$PJ8/.sutra/turn/sid-c8/$TID.lens.prev"*.json 2>/dev/null)" ] && pass "case13b: rotated lens kept as .prev" || fail "case13b: rotated lens not kept"
[ "$(rows "$PJ8/.sutra/turn/sid-c8/$TID.jsonl" '.kind=="steps_rotate"')" -ge 1 ] && pass "case13b: rotate row present" || fail "case13b: no steps_rotate row"
# PJ8 runs in WARN mode (case 8), so the re-authoring demand arrives as a systemMessage, not a deny.
do_run c13d "$PLUGIN_MAIN" "$PJ8" "$HM8" PreToolUse "$(stdin_write sid-c8 "$PJ8/src/c.txt")"
adherence_warned c13d && pass "case13b: mutation warned again after rotation (stale artifacts do not authorize)" || fail "case13b: stale artifacts still authorize: $(head -c 200 "$WORK/c13d.out")"
sysmsg_of c13d | grep -q "lens.json (missing)" && pass "case13b: warning names the missing lens" || fail "case13b: warning lacks the missing lens"

# ==================================================================== 14 ====
echo "== case 14: spec-check + selftest =="
bash "$PLUGIN_MAIN/runtime/spec-check.sh" "$PLUGIN_MAIN/runtime/pipeline.json" >/dev/null 2>&1 && pass "case14: spec-check" || fail "case14: spec-check"
CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" bash "$PLUGIN_MAIN/bin/sutra-turn" --selftest 2>&1 | grep -q 'fail=0' && pass "case14: selftest" || fail "case14: selftest"
for s in steps_ledger adherence_gate steps_close; do
  [ -x "$PLUGIN_MAIN/runtime/steps/$s.sh" ] && pass "case14: $s.sh executable" || fail "case14: $s.sh not executable"
done

# ==================================================================== 15 ====
echo "== case 15: 2.285.1 - runtime-owned paths refused to every tool; Bash classed by shape; scripts under exempt dirs not exempt =="
stdin_write_c() { jq -nc --arg sid "$1" --arg f "$2" --arg c "$3" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Write", tool_input:{file_path:$f, content:$c}}'; }
stdin_read()    { jq -nc --arg sid "$1" --arg f "$2" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"Read", tool_input:{file_path:$f}}'; }
ro_denied() { deny_reason_of "$1" | grep -q 'RUNTIME-OWNED PATH'; }
decision_of() { _dv="$(jq -r '.hookSpecificOutput.permissionDecision // "none"' "$WORK/$1.out" 2>/dev/null)"; printf '%s' "${_dv:-none}"; }   # empty stdout = allowed
PJ="$WORK/c15/proj"; HM="$WORK/c15/home"; mk_proj "$PJ"; set_flags "$HM" on on
open_turn c15u "$PJ" "$HM" sid-c15
write_artifacts "$PJ" sid-c15 "$TID" $((OPENED + 1))
# R9 holds even with both artifacts valid
do_run c15a "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c15 "$HM/$F_OVR")"
ro_denied c15a && pass "case15: Write to the override file refused" || fail "case15: Write to the override file not refused: $(deny_reason_of c15a | head -1)"
do_run c15b "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c15 "printf off > $HM/$F_ADH")"
ro_denied c15b && pass "case15: Bash writing the flag file refused" || fail "case15: Bash writing the flag file not refused"
do_run c15c "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c15 "cat ~/$F_MARK")"
[ "$(decision_of c15c)" = none ] && pass "case15: a READ of a flag file passes (a mention is not a mutation)" || fail "case15: read of a flag file refused: $(deny_reason_of c15c | head -1)"
do_run c15c2 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c15 "cat ~/.sutra-runtime/seal.key | base64")"
ro_denied c15c2 && pass "case15: a READ of the seal dir is refused" || fail "case15: seal read not refused"
do_run c15c3 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c15 "grep -rn sutra-overrides docs/ | head")"
[ "$(decision_of c15c3)" = none ] && pass "case15: grep for the name passes" || fail "case15: grep for the name refused"
do_run c15c4 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write_c sid-c15 "$PJ/docs/flags.md" "The founder sets ~/$F_ADH in a terminal; see ~/$F_OVR for the ACK keys.")"
[ "$(decision_of c15c4)" = none ] && pass "case15: a doc that mentions the names passes" || fail "case15: doc mention refused: $(deny_reason_of c15c4 | head -1)"
do_run c15c5 "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(jq -nc --arg sid sid-c15 --arg f "$PJ/tools/x.py" --arg ns "open(os.path.expanduser(\"~/$F_OVR\"), \"w\").write(\"FLOW_ACK=1\")" '{session_id:$sid, hook_event_name:"PreToolUse", tool_name:"MultiEdit", tool_input:{file_path:$f, edits:[{old_string:"a", new_string:$ns}]}}')"
ro_denied c15c5 && pass "case15: MultiEdit payload writing the file is refused" || fail "case15: MultiEdit payload slipped: $(deny_reason_of c15c5 | head -1)"
do_run c15d "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write_c sid-c15 "$PJ/tools/x.sh" "printf off > ~/$F_OVR")"
ro_denied c15d && pass "case15: Write whose CONTENT names the override file refused" || fail "case15: content naming the override file not refused"
do_run c15e "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c15 "rm $PJ/.sutra/turn/sid-c15/opened")"
ro_denied c15e && pass "case15: the session stamp is runtime-owned" || fail "case15: session stamp not protected"
do_run c15f "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_read sid-c15 "$HM/.sutra-runtime/seal.key")"
ro_denied c15f && pass "case15: Read of the seal dir refused" || fail "case15: Read of the seal dir not refused"
do_run c15h "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_bash sid-c15 "printf off > ~/.sutra-over\"\"rides")"
ro_denied c15h && pass "case15: quote-split name still refused" || fail "case15: quote-split name slipped through"
sysmsg_of c15a | grep -q 'REFUSED Write: runtime-owned' && pass "case15: live line names the refusal" || fail "case15: no live line"
is "case15: eight runtime-owned decision rows" "$(rows "$PJ/.sutra/turn/sid-c15/$TID.jsonl" '.kind == "adherence_decision" and .reason == "runtime-owned"')" 8
do_run c15g "$PLUGIN_MAIN" "$PJ" "$HM" PreToolUse "$(stdin_write sid-c15 "$PJ/src/ok.txt")"
[ "$(decision_of c15g)" = none ] && pass "case15: an ordinary Write still passes with artifacts" || fail "case15: ordinary Write refused"
# warn mode: systemMessage, no deny
PJW="$WORK/c15w/proj"; HMW="$WORK/c15w/home"; mk_proj "$PJW"; set_flags "$HMW" on warn
open_turn c15wu "$PJW" "$HMW" sid-c15w
do_run c15w "$PLUGIN_MAIN" "$PJW" "$HMW" PreToolUse "$(stdin_write sid-c15w "$HMW/$F_OVR")"
[ "$(decision_of c15w)" = none ] && sysmsg_of c15w | grep -q 'RUNTIME-OWNED PATH' && pass "case15: warn mode warns, never denies" || fail "case15: warn mode wrong"
# shape: a fresh turn WITHOUT artifacts - mutations are refused, reads pass
PJ2="$WORK/c15s/proj"; HM2="$WORK/c15s/home"; mk_proj "$PJ2"; set_flags "$HM2" on on
open_turn c15su "$PJ2" "$HM2" sid-c15s
i=0
for cmd in "bash .enforcement/x.sh" "./run.sh" "sh scripts/build.sh --all" "source ./env.sh" "make build" "frobnicate --all" "python3 - <<'EOF'
print(1)
EOF" "cd $PJ2 && bash tools/run.sh" "node scripts/gen.js" "ENV=1 bash x.sh" "env VAR=1 bash x.sh" "git clone https://example.invalid/r.git" "bash /tmp/x" "x.bash --all" "ls & bash deploy.sh" "find . -name '*.sh' -exec bash {} \\;" "VAR=\$(bash x.sh)" "echo evil.sh | xargs -I{} bash {}" "awk 'BEGIN{system(\"./deploy\")}'" "if true; then bash x.sh; fi"; do
  i=$((i + 1)); do_run "c15m$i" "$PLUGIN_MAIN" "$PJ2" "$HM2" PreToolUse "$(stdin_bash sid-c15s "$cmd")"
  adherence_denied "c15m$i" && pass "case15: mutation by shape: $(printf '%s' "$cmd" | head -1)" || fail "case15: not classed as mutation: $(printf '%s' "$cmd" | head -1)"
done
i=0
for cmd in "ls -la" "git status --short" "grep -rn x ." "python3 --version" "cat a.txt | head -3" "jq -r .version p.json" "RTK_SKIP=1 git log --oneline -3" "find . -name '*.sh' | wc -l" "docker --version" "/usr/bin/git status" "env" "if [ -f x ]; then ls; fi" "export FOO=1" "for f in a b; do echo \$f; done" "(cd $PJ2 && ls)" "bash -n x.sh" "ls 2>&1 | head -2" "npm ls" "\"$PLUGIN_MAIN/bin/sutra-steps\" --sid sid-c15s latest" "python3 -m json.tool p.json"; do
  i=$((i + 1)); do_run "c15r$i" "$PLUGIN_MAIN" "$PJ2" "$HM2" PreToolUse "$(stdin_bash sid-c15s "$cmd")"
  [ "$(decision_of "c15r$i")" = none ] && pass "case15: read by shape: $cmd" || fail "case15: read refused: $cmd"
done
# scripts under exempt dirs are not exempt; plain logs there still are
do_run c15x1 "$PLUGIN_MAIN" "$PJ2" "$HM2" PreToolUse "$(stdin_write sid-c15s "$PJ2/.enforcement/x.sh")"
adherence_denied c15x1 && pass "case15: .enforcement/x.sh is not exempt" || fail "case15: .enforcement/x.sh exempt"
do_run c15x2 "$PLUGIN_MAIN" "$PJ2" "$HM2" PreToolUse "$(stdin_write sid-c15s "$PJ2/.claude/sessions/sid-c15s/note.py")"
adherence_denied c15x2 && pass "case15: session-dir .py is not exempt" || fail "case15: session-dir .py exempt"
do_run c15x3 "$PLUGIN_MAIN" "$PJ2" "$HM2" PreToolUse "$(stdin_write_c sid-c15s "$PJ2/.enforcement/tool" "#!/bin/sh
rm -rf x")"
adherence_denied c15x3 && pass "case15: shebang content is never exempt" || fail "case15: shebang content exempt"
do_run c15x4 "$PLUGIN_MAIN" "$PJ2" "$HM2" PreToolUse "$(stdin_write sid-c15s "$PJ2/.enforcement/log.jsonl")"
[ "$(decision_of c15x4)" = none ] && pass "case15: .enforcement/log.jsonl still exempt" || fail "case15: log.jsonl refused"
# the library, called directly, agrees with the gate
. "$PLUGIN_MAIN/runtime/lib/steps.sh"
sutra_steps_bash_mutation "ls -la && bash x.sh" && pass "case15: lib: one mutating segment makes the command a mutation" || fail "case15: lib: bash x.sh missed"
sutra_steps_bash_mutation "ls -la | grep x" && fail "case15: lib: read pipeline classed as mutation" || pass "case15: lib: read pipeline is a read"
sutra_steps_bash_shape "python3 -V" && fail "case15: lib: python3 -V classed as mutation" || pass "case15: lib: interpreter version flag is a read"
sutra_steps_exempt_bash "bash holding/bin/sutra-atom close a-1" sid-x && pass "case15: lib: governance CLI still exempt under the shape pass" || fail "case15: lib: governance CLI lost its exemption"
sutra_steps_runtime_owned "echo .sutra/turn/sid-1/opened-notes" && fail "case15: lib: runtime-owned regex over-matches" || pass "case15: lib: opened-notes is not the stamp"

echo "failed=$failed"
[ "$failed" -eq 0 ]
