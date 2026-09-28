#!/usr/bin/env bash
# test-tier.sh - the founder's acceptance conditions C6-C9
# (RUNTIME-ACCEPTANCE-CONDITIONS.md, 2026-09-28): a turn's own inputs replay
# through the code and reproduce its outputs; a code step below its threshold
# asks an agent and records source, confidence and a reason; an agent answer
# may only raise stringency; an unreachable agent leaves the code's answer
# standing, marked unresolved, with nothing guessed.
#
# The agent is stubbed by SUTRA_TIER_AGENT_CMD, so no suite run makes a network
# call. bash 3.2 compatible.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-tier.sh
set -u
RO_PRE=".sutra-"; F_MARK="${RO_PRE}runtime-markers"; F_ADH="${RO_PRE}runtime-adherence"
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_MAIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }
command -v jq >/dev/null 2>&1 || { fail "jq required"; echo "failed=$failed"; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-tier.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
. "$PLUGIN_MAIN/runtime/lib/steps.sh"
command -v sutra_tier_due >/dev/null 2>&1 || { fail "the tier library did not load with the step library"; echo "failed=$failed"; exit 1; }

PJ="$WORK/proj"; mkdir -p "$PJ/.sutra/turn/sid-t/lane-logs" "$PJ/.claude/sessions/sid-t"
TID=aaaabbbbccccdddd
# a register of this suite's own, so no case depends on the box's real one and
# the minting guard has something true to check against
REG="$WORK/reg/domains"; mkdir -p "$REG"
for _r in dref-abc123 dref-inreg01 dref-999aaa dref-777bbb dref-existing; do
  printf '{"ref":"%s","name":"suite domain"}\n' "$_r" > "$REG/$_r.json"
done
export SUTRA_NATIVE_HOME="$WORK/reg"

# ================================================================== C10/C7 ===
echo "== the direction is data, and the threshold decides whether to ask =="
is "threshold: placement carries its measured number" "$(sutra_tier_threshold "$PLUGIN_MAIN" placement)" 0.5
is "threshold: an unmeasured step has none" "$(sutra_tier_threshold "$PLUGIN_MAIN" classify)" ""
sutra_tier_due "$PLUGIN_MAIN" placement 0.28 && pass "ask is due below the threshold" || fail "no ask below the threshold"
sutra_tier_due "$PLUGIN_MAIN" placement 0.80 && fail "an ask was due above the threshold" || pass "no ask above the threshold"
sutra_tier_due "$PLUGIN_MAIN" classify 0.01 && fail "a null threshold still asked" || pass "a null threshold never asks"

# ====================================================================== C8 ===
echo "== C8: an agent answer may raise stringency and never lower it =="
is "depth: a higher number is taken" "$(sutra_tier_apply "$PLUGIN_MAIN" depth 3 5)" 5
sutra_tier_apply "$PLUGIN_MAIN" depth 3 5 >/dev/null && pass "depth: raising is applied" || fail "depth: raising was refused"
is "depth: a lower number is refused" "$(sutra_tier_apply "$PLUGIN_MAIN" depth 4 2)" 4
sutra_tier_apply "$PLUGIN_MAIN" depth 4 2 >/dev/null && fail "depth: lowering was applied" || pass "depth: lowering is refused"
is "depth: the same number changes nothing" "$(sutra_tier_apply "$PLUGIN_MAIN" depth 3 3)" 3
is "placement: an address where there was none is taken" "$(sutra_tier_apply "$PLUGIN_MAIN" placement unresolved dref-abc123)" dref-abc123
is "placement: an unresolved answer never unseats an address" "$(sutra_tier_apply "$PLUGIN_MAIN" placement dref-abc123 unresolved)" dref-abc123
is "placement: a made-up answer is refused" "$(sutra_tier_apply "$PLUGIN_MAIN" placement unresolved "the ops team")" unresolved
# the register, not the spelling, is what stops a minted department: an address
# that parses but is not in the register must be refused (peer review P1-1)
REG="$WORK/reg/domains"; mkdir -p "$REG"
printf '{"ref":"dref-inreg01","name":"A real one"}\n' > "$REG/dref-inreg01.json"
is "placement: an address the register holds is taken" \
  "$(SUTRA_NATIVE_HOME="$WORK/reg" sutra_tier_apply "$PLUGIN_MAIN" placement unresolved dref-inreg01)" dref-inreg01
is "placement: an address the register does not hold is refused" \
  "$(SUTRA_NATIVE_HOME="$WORK/reg" sutra_tier_apply "$PLUGIN_MAIN" placement unresolved dref-notthere)" unresolved
is "depth: a garbled answer cannot fail the comparison open" "$(sutra_tier_apply "$PLUGIN_MAIN" depth 3 "five-ish")" 3
is "classify: risk may go up" "$(sutra_tier_apply "$PLUGIN_MAIN" classify low high)" high
is "classify: risk may not go down" "$(sutra_tier_apply "$PLUGIN_MAIN" classify high low)" high

# ====================================================================== C7 ===
echo "== C7: below the threshold an agent is called and its answer is recorded =="
STUB="$WORK/agent-ok.sh"
{ echo '#!/usr/bin/env bash'
  echo 'printf "%s\n" "{\"value\":\"dref-999aaa\",\"confidence\":\"0.9\",\"reason\":\"the unit names the runtime department\"}" > "$2"'
} > "$STUB"; chmod +x "$STUB"
SUTRA_TIER_AGENT_CMD="$STUB" sutra_tier_ask_detach "$PLUGIN_MAIN" "$PJ" sid-t "$TID" placement "who owns this?"
_w=0; while [ ! -f "$PJ/.sutra/turn/sid-t/$TID.placement.ask.json" ] && [ "$_w" -lt 50 ]; do _w=$((_w + 1)); sleep 0.1; done
[ -f "$PJ/.sutra/turn/sid-t/$TID.placement.ask.json" ] && pass "C7: the detached ask produced an answer file" || fail "C7: no answer file"
printf '{"ref":"dref-999aaa","name":"The one the agent names"}\n' > "$REG/dref-999aaa.json"
SUTRA_NATIVE_HOME="$WORK/reg" sutra_tier_settle "$PLUGIN_MAIN" "$PJ" sid-t "$TID" placement unresolved 0.28
TF="$PJ/.sutra/turn/sid-t/$TID.tier.jsonl"
[ -f "$TF" ] && pass "C7: the decision is recorded" || fail "C7: no decision record"
is "C7: the row names the agent as the source" "$(jq -r 'select(.step=="placement") | .source' "$TF" | tail -1)" agent
is "C7: the row carries the agent's value" "$(jq -r 'select(.step=="placement") | .value' "$TF" | tail -1)" dref-999aaa
is "C7: the row carries a confidence" "$(jq -r 'select(.step=="placement") | .confidence' "$TF" | tail -1)" 0.9
jq -r 'select(.step=="placement") | .reason' "$TF" | tail -1 | grep -q '.' && pass "C7: the row carries one line of reason" || fail "C7: no reason recorded"
is "C7: one settle per step per turn" "$(jq -s 'length' "$TF")" 1

# ================================================================== C8 rec ===
echo "== C8: a lowering answer is refused, and the refusal is recorded =="
PJ2="$WORK/proj2"; mkdir -p "$PJ2/.sutra/turn/sid-t"
STUB2="$WORK/agent-lower.sh"
{ echo '#!/usr/bin/env bash'
  echo 'printf "%s\n" "{\"value\":\"unresolved\",\"confidence\":\"0.9\",\"reason\":\"nothing owns it\"}" > "$2"'
} > "$STUB2"; chmod +x "$STUB2"
SUTRA_TIER_AGENT_CMD="$STUB2" sutra_tier_ask_detach "$PLUGIN_MAIN" "$PJ2" sid-t "$TID" placement "who owns this?"
_w=0; while [ ! -f "$PJ2/.sutra/turn/sid-t/$TID.placement.ask.json" ] && [ "$_w" -lt 50 ]; do _w=$((_w + 1)); sleep 0.1; done
sutra_tier_settle "$PLUGIN_MAIN" "$PJ2" sid-t "$TID" placement dref-existing 0.28
TF2="$PJ2/.sutra/turn/sid-t/$TID.tier.jsonl"
is "C8: the code's value stands" "$(jq -r '.value' "$TF2" | tail -1)" dref-existing
is "C8: the source is the code, not the agent" "$(jq -r '.source' "$TF2" | tail -1)" code
jq -r '.reason' "$TF2" | tail -1 | grep -q 'raise-only' && pass "C8: the refusal names the rule" || fail "C8: the refusal is not recorded"

# ====================================================================== C9 ===
echo "== C9: an unreachable agent leaves the code's answer standing =="
PJ3="$WORK/proj3"; mkdir -p "$PJ3/.sutra/turn/sid-t"
STUB3="$WORK/agent-dead.sh"
{ echo '#!/usr/bin/env bash'; echo 'exit 3'; } > "$STUB3"; chmod +x "$STUB3"
SUTRA_TIER_AGENT_CMD="$STUB3" sutra_tier_ask_detach "$PLUGIN_MAIN" "$PJ3" sid-t "$TID" placement "who owns this?"
sleep 0.5
sutra_tier_settle "$PLUGIN_MAIN" "$PJ3" sid-t "$TID" placement unresolved 0.28
TF3="$PJ3/.sutra/turn/sid-t/$TID.tier.jsonl"
is "C9: the code's own value is kept" "$(jq -r '.value' "$TF3" | tail -1)" unresolved
is "C9: the source is the code" "$(jq -r '.source' "$TF3" | tail -1)" code
is "C9: the field is marked unresolved" "$(jq -r '.unresolved' "$TF3" | tail -1)" true
is "C9: the code's own confidence is unchanged" "$(jq -r '.confidence' "$TF3" | tail -1)" 0.28
is "C9: nothing was guessed" "$(jq -r 'select(.value | test("^dref-")) | .value' "$TF3" | wc -l | tr -d ' ')" 0

# ================================================================ C7 in row ==
echo "== C7: the tier that answered is in the step log row =="
PJ4="$WORK/proj4"; mkdir -p "$PJ4/.sutra/turn/sid-t" "$PJ4/.claude/sessions/sid-t"
printf 'DOMAIN_REF=unresolved\nCONFIDENCE=0.28\nSOURCE=engine\n' > "$PJ4/.claude/sessions/sid-t/placement-registered"
STUB4="$WORK/agent-row.sh"
{ echo '#!/usr/bin/env bash'
  echo 'printf "%s\n" "{\"value\":\"dref-777bbb\",\"confidence\":\"0.8\",\"reason\":\"runtime work\"}" > "$2"'
} > "$STUB4"; chmod +x "$STUB4"
SUTRA_TIER_AGENT_CMD="$STUB4" sutra_tier_ask_detach "$PLUGIN_MAIN" "$PJ4" sid-t "$TID" placement "who owns this?"
_w=0; while [ ! -f "$PJ4/.sutra/turn/sid-t/$TID.placement.ask.json" ] && [ "$_w" -lt 50 ]; do _w=$((_w + 1)); sleep 0.1; done
printf '{"ref":"dref-777bbb","name":"The one in the row"}\n' > "$REG/dref-777bbb.json"
STEPS='[{"n":4,"id":"placement","status":"done","detail":"unresolved"}]'
ROWOUT="$(SUTRA_NATIVE_HOME="$WORK/reg" sutra_step_log "$PLUGIN_MAIN" "$PJ4" sid-t "$TID" UserPromptSubmit "$STEPS" 1)"
L4="$PJ4/.sutra/turn/sid-t/$TID.steplog.jsonl"
is "C7: the row's source is the agent" "$(jq -r 'select(.step=="placement") | .source' "$L4" | tail -1)" agent
is "C7: the row keeps the step's own tier too" "$(jq -r 'select(.step=="placement") | .tier' "$L4" | tail -1)" code
printf '%s' "$ROWOUT" | grep -q 'code<agent' && pass "C7: the printed line shows who answered" || fail "C7: the printed line hides the source: $ROWOUT"

# ====================================================================== C6 ===
echo "== C6: a turn's own inputs replay through the code and reproduce it =="
PJ5="$WORK/proj5"; HM5="$WORK/home5"
mkdir -p "$PJ5/.claude/sessions" "$PJ5/src" "$HM5"
printf '{"profile":"company"}\n' > "$PJ5/.claude/sutra-project.json"
( cd "$PJ5" && git init -q . && git config user.email t@t && git config user.name t && printf 'a\n' > src/a.txt && git add -A && git commit -qm init ) >/dev/null 2>&1
printf 'on\n' > "$HM5/$F_MARK"; printf 'on\n' > "$HM5/$F_ADH"
jq -nc --arg sid sid-r --arg p "please change src/a.txt and run the tests for the replay case" \
  '{session_id:$sid, hook_event_name:"UserPromptSubmit", prompt:$p}' > "$WORK/r.stdin.json"
env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$PJ5" \
  CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" HOME="$HM5" RTK_SKIP=1 \
  "$PLUGIN_MAIN/bin/sutra-turn" run --event UserPromptSubmit < "$WORK/r.stdin.json" > "$WORK/r.out" 2>&1
TIDR="$(cat "$PJ5/.sutra/turn/sid-r/current" 2>/dev/null)"
RP="$PJ5/.sutra/turn/sid-r/$TIDR.replay.json"
[ -f "$RP" ] && pass "C6: the turn recorded its own inputs" || fail "C6: no replay record"
jq -e '.prompt != "" and .recorded.classify != "" and .recorded.depth != ""' "$RP" >/dev/null 2>&1 \
  && pass "C6: the record carries the prompt and each step's output" || fail "C6: the record is incomplete"
ROUT="$(env -u CLAUDE_CODE_SESSION_ID CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" CLAUDE_PROJECT_DIR="$PJ5" \
  "$PLUGIN_MAIN/bin/sutra-steps" --sid sid-r replay 2>&1)"
printf '%s' "$ROUT" | grep -q 'classify   SAME' && pass "C6: classify reproduced byte for byte" || fail "C6: classify did not reproduce: $ROUT"
printf '%s' "$ROUT" | grep -q 'depth      SAME' && pass "C6: depth reproduced byte for byte" || fail "C6: depth did not reproduce: $ROUT"
printf '%s' "$ROUT" | grep -qE 'resolve    (SAME|NOT REPLAYED)' && pass "C6: resolve reproduced or said why not" || fail "C6: resolve did not reproduce: $ROUT"
printf '%s' "$ROUT" | grep -q 'NOT REPLAYABLE' && pass "C6: the model steps say they cannot be replayed" || fail "C6: a model step was counted as reproduced"
printf '%s' "$ROUT" | grep -q 'every replayable step reproduced' && pass "C6: the verdict line is printed" || fail "C6: no verdict line"
# and the record is the runtime's own file, not a model-writable one
sutra_steps_runtime_owned_write "echo x > .sutra/turn/sid-r/$TIDR.replay.json" \
  && pass "C6: the replay record is runtime-owned" || fail "C6: a tool could write the replay record"

echo "failed=$failed"
[ "$failed" -eq 0 ]
