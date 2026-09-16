#!/usr/bin/env bash
# test-turn-concurrency.sh - the four things sutra-turn must copy from the host
# and used to get wrong: it must run an event's hooks CONCURRENTLY, it must not
# stop dispatching after a deny, it must read a matcher the way the host reads
# it, and it must hand the host AT MOST ONE JSON object per event.
#
# WHY EACH SECTION EXISTS (every one of these is a measured regression, not a
# hypothetical):
#
#   1 WALL CLOCK. Serial execution made an event cost the SUM of its steps. The
#     Stop event registers 24 of them, the charcap harness watchdog killed the
#     run at its wall cap (exit 142) and the ledger stopped mid-walk - 107
#     "no ledger row" parity failures. The host's own rule is "all matching
#     hooks run in parallel to completion", so three 1-second hooks must finish
#     an event in about one second, never three.
#
#   2 DENY DOES NOT SKIP. sutra-turn used to skip every class B/C step after a
#     step exited 2. The host does no such thing: it dispatches every hook and
#     takes the most restrictive decision. 44 corpus cases carried "N step(s)
#     not executed by the runner after a deny" - 88 legacy executions, with
#     their side effects, silently dropped. Class is an EMISSION property here,
#     never an execution one.
#
#   3 MATCHER. One documented rule: omitted/"*" matches everything, anything
#     else must match the whole tool name as an anchored ERE. "Edit|Write" must
#     therefore NOT match MultiEdit (the registry spells MultiEdit out when it
#     means it), and "mcp__.*" must match every MCP tool - the registered
#     PermissionRequest matcher relies on exactly that.
#
#   4 ONE JSON OBJECT. Two steps that each print a JSON object used to be
#     concatenated into "{...}\n{...}", which is not JSON - and two PreToolUse
#     Bash steps do exactly that in the shipped registry. The merge is the
#     host's: deny > ask > allow, reasons joined, permission rules concatenated,
#     additionalContext joined and emitted on EVERY event.
#
# bash 3.2 + jq. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-turn-concurrency.sh

set -u

here="$(cd "$(dirname "$0")" && pwd -P)"
runtime="$(cd "$here/.." && pwd -P)"
plugin="$(cd "$runtime/.." && pwd -P)"
turn="$plugin/bin/sutra-turn"

checks=0
failed=0
ok()   { checks=$((checks+1)); }
fail() { checks=$((checks+1)); failed=$((failed+1)); printf 'FAIL %s\n' "$*" >&2; }
is()   { if [ "$2" = "$3" ]; then ok; else fail "$1: expected [$3] got [$2]"; fi; }
has()  { if printf '%s' "$2" | grep -q "$3"; then ok; else fail "$1: [$2] lacks [$3]"; fi; }

# The one wall-clock bound in this suite (section 3: a 600 ms budget on a 5 s
# hook must not hold the event open). The watchdog is deadline-based, so on an
# idle box the event finishes in well under a second and this default is
# generous already; a loaded CI runner or a laptop hosting eight sandboxes can
# still add seconds of scheduling latency that are not a regression, so the
# harness (tests/run-all.sh, and the release-gate workflow) exports a larger
# value. Everything else here is measured against the run's own numbers.
TIMEOUT_BUDGET_MS="${SUTRA_CONC_TIMEOUT_BUDGET_MS:-3000}"

command -v jq >/dev/null 2>&1 || { printf 'test-turn-concurrency: jq required\nfailed=1\n'; exit 1; }
[ -x "$turn" ] || { printf 'test-turn-concurrency: %s not executable\nfailed=1\n' "$turn"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-conc.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# ------------------------------------------------------- throw-away plugin --
fake="$tmp/plugin"
mkdir -p "$fake/bin" "$fake/runtime" "$fake/hooks"
cp "$turn" "$fake/bin/sutra-turn"; chmod 0755 "$fake/bin/sutra-turn"
cp "$runtime/shim.sh" "$runtime/ledger.sh" "$fake/runtime/"

sid="99999999-8888-7777-6666-555555555555"
home="$tmp/home"; mkdir -p "$home"

# run <name> <event> <stdin-file> [tool_name] -> stdout/stderr/rc in $tmp/<name>.*
run() {
  _rn="$1"; _re="$2"; _ri="$3"
  _rp="$tmp/proj-$_rn"
  mkdir -p "$_rp/.claude" "$_rp/.sutra" "$_rp/.enforcement"
  env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$_rp" HOME="$home" \
    "$fake/bin/sutra-turn" run --event "$_re" \
    < "$_ri" > "$tmp/$_rn.out" 2> "$tmp/$_rn.err"
  rc=$?
  led="$_rp/.sutra/turn/$sid.jsonl"
}
now() { jq -n 'now'; }
elapsed() { jq -n --argjson a "$1" --argjson b "$2" '(($b-$a)*1000|floor)'; }

printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"Edit"}' "$sid" > "$tmp/pre.json"

# =================================================== 1. steps run in parallel --
# MEASURED, NOT TIMED OUT. A fixed "under 2 seconds" bound is a lie on a loaded
# machine (three 1s sleeps were observed taking 1.4-2.1s each while the runtime
# competed with seven other sandboxes). Two machine-independent facts prove
# concurrency instead:
#   a. the three hooks' [start,end] intervals OVERLAP - the last one to start
#      did so before the first one finished;
#   b. the event's wall clock is LESS than the sum of its steps' own measured
#      durations - which serial execution cannot be, by definition.
marks="$tmp/marks"; mkdir -p "$marks"
for n in 1 2 3; do
  cat > "$fake/hooks/slow-$n.sh" <<SLOW
#!/bin/sh
cat >/dev/null
jq -n 'now*1000|floor' > "$marks/start-$n"
sleep 1
jq -n 'now*1000|floor' > "$marks/end-$n"
printf 'SLOW-$n\n' >&2
exit 0
SLOW
  chmod 0755 "$fake/hooks/slow-$n.sh"
done

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PreToolUse": [
      {"id":"pre.slow-1","matcher":"*","class":"B","impl":"shim:hooks/slow-1.sh","timeout_ms":9000},
      {"id":"pre.slow-2","matcher":"*","class":"B","impl":"shim:hooks/slow-2.sh","timeout_ms":9000},
      {"id":"pre.slow-3","matcher":"*","class":"B","impl":"shim:hooks/slow-3.sh","timeout_ms":9000}
    ]
  }
}
PIPE

t0="$(now)"; run par PreToolUse "$tmp/pre.json"; t1="$(now)"
ms="$(elapsed "$t0" "$t1")"
is "parallel exit" "$rc" 0
is "parallel ran all three" "$(jq -s '[.[]|select(.kind=="step")]|length' "$led")" 3

laststart="$(cat "$marks"/start-* 2>/dev/null | sort -n | tail -1)"
firstend="$(cat "$marks"/end-*   2>/dev/null | sort -n | head -1)"
if [ -n "$laststart" ] && [ -n "$firstend" ] && [ "$laststart" -lt "$firstend" ]; then ok; else
  fail "the three hooks did not overlap: last start $laststart, first end $firstend"; fi
sumdur="$(jq -s '[.[]|select(.kind=="step")|.dur_ms]|add // 0' "$led")"
if [ "$ms" -lt "$sumdur" ]; then ok; else
  fail "event wall ${ms}ms >= the sum of its steps ${sumdur}ms (serial execution)"; fi
# and each one really did run - the ledger is not three rows about nothing
is "parallel stderr order" "$(tr -d ' ' < "$tmp/par.err" | tr '\n' ',')" "SLOW-1,SLOW-2,SLOW-3,"

# ========================================== 2. a deny does not skip the rest --
cat > "$fake/hooks/deny-first.sh" <<'D1'
#!/bin/sh
cat >/dev/null
printf 'DENY-ONE\n' >&2
exit 2
D1
mkeffect() {  # <file> <marker>
  cat > "$1" <<EFF
#!/bin/sh
cat >/dev/null
: > "\$SUTRA_TEST_EFFECTS/$2"
printf '$2\n' >&2
exit 0
EFF
  chmod 0755 "$1"
}
mkeffect "$fake/hooks/side-two.sh" SIDE-TWO
mkeffect "$fake/hooks/side-three.sh" SIDE-THREE
chmod 0755 "$fake/hooks/deny-first.sh"

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PreToolUse": [
      {"id":"pre.deny-first","matcher":"*","class":"B","impl":"shim:hooks/deny-first.sh","timeout_ms":5000},
      {"id":"pre.side-two","matcher":"*","class":"B","impl":"shim:hooks/side-two.sh","timeout_ms":5000},
      {"id":"pre.side-three","matcher":"*","class":"C","impl":"shim:hooks/side-three.sh","timeout_ms":5000}
    ]
  }
}
PIPE

effects="$tmp/effects"; mkdir -p "$effects"
export SUTRA_TEST_EFFECTS="$effects"
run deny PreToolUse "$tmp/pre.json"
is "deny exit" "$rc" 2
[ -f "$effects/SIDE-TWO" ]   && ok || fail "class B step after a deny did not execute"
[ -f "$effects/SIDE-THREE" ] && ok || fail "class C step after a deny did not execute"
is "deny wrote three step rows" "$(jq -s '[.[]|select(.kind=="step")]|length' "$led")" 3
is "deny wrote no skip rows"    "$(jq -s '[.[]|select(.kind=="skip")]|length' "$led")" 0
is "blocking stderr is last" "$(tr -d ' ' < "$tmp/deny.err" | tr '\n' ',')" \
  "SIDE-TWO,SIDE-THREE,DENY-ONE,"

# ========================= 3. a timed-out step is 124 and delays nobody else --
cat > "$fake/hooks/hang.sh" <<'HANG'
#!/bin/sh
cat >/dev/null
sleep 5
exit 0
HANG
cat > "$fake/hooks/quick.sh" <<'QUICK'
#!/bin/sh
cat >/dev/null
exit 0
QUICK
chmod 0755 "$fake/hooks/hang.sh" "$fake/hooks/quick.sh"

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PreToolUse": [
      {"id":"pre.hang","matcher":"*","class":"B","impl":"shim:hooks/hang.sh","timeout_ms":600},
      {"id":"pre.quick","matcher":"*","class":"B","impl":"shim:hooks/quick.sh","timeout_ms":5000}
    ]
  }
}
PIPE

t0="$(now)"; run tmo PreToolUse "$tmp/pre.json"; t1="$(now)"
ms="$(elapsed "$t0" "$t1")"
is "timeout exit" "$rc" 0
is "timed-out step records 124" \
  "$(jq -s '[.[]|select(.kind=="step" and .step_id=="pre.hang")][0].exit' "$led")" 124
is "the other step still ran" \
  "$(jq -s '[.[]|select(.kind=="step" and .step_id=="pre.quick")][0].exit' "$led")" 0
# The hook sleeps 5s; anything comfortably under that proves the watchdog
# killed it on ITS budget and did not hold the event (or the other step) open.
echo "metric: 600ms budget on a 5s hook cost the event ${ms}ms (bound ${TIMEOUT_BUDGET_MS}ms)"
if [ "$ms" -lt "$TIMEOUT_BUDGET_MS" ]; then ok; else
  fail "a 600ms budget on a 5s hook cost the event ${ms}ms (bound ${TIMEOUT_BUDGET_MS}ms)"; fi

# -------- 3b. SUTRA_STEP_TIMEOUT_SCALE lengthens a budget, and only lengthens --
# The watchdog is deadline-based, so a machine that is deliberately
# oversubscribed (the parity replayer at --jobs N, a shared CI runner) can push
# a hook that normally takes 200 ms past a 3 s budget and the runtime will
# honestly kill it. The scale knob is how such a harness buys headroom; it is
# clamped at 100, so it can never be used to SHORTEN a cap and silence a hook.
cat > "$fake/hooks/second.sh" <<'SEC'
#!/bin/sh
cat >/dev/null
sleep 1
exit 0
SEC
chmod 0755 "$fake/hooks/second.sh"
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PreToolUse": [
      {"id":"pre.second","matcher":"*","class":"B","impl":"shim:hooks/second.sh","timeout_ms":300}
    ]
  }
}
PIPE
run scale0 PreToolUse "$tmp/pre.json"
is "a 1s hook on a 300ms budget is killed" \
  "$(jq -s '[.[]|select(.kind=="step" and .step_id=="pre.second")][0].exit' "$led")" 124

_rp="$tmp/proj-scale5"; mkdir -p "$_rp/.claude" "$_rp/.sutra" "$_rp/.enforcement"
env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$_rp" HOME="$home" \
  SUTRA_STEP_TIMEOUT_SCALE=1000 \
  "$fake/bin/sutra-turn" run --event PreToolUse \
  < "$tmp/pre.json" > "$tmp/scale5.out" 2> "$tmp/scale5.err"
is "scale x10 lets the same hook finish" \
  "$(jq -s '[.[]|select(.kind=="step" and .step_id=="pre.second")][0].exit' \
     "$_rp/.sutra/turn/$sid.jsonl")" 0

# and a scale BELOW 100 is clamped: with a 3 s budget the 1 s hook must still
# finish, where an unclamped x0.01 would have cut it to 30 ms and killed it.
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PreToolUse": [
      {"id":"pre.second","matcher":"*","class":"B","impl":"shim:hooks/second.sh","timeout_ms":3000}
    ]
  }
}
PIPE
_rp="$tmp/proj-scale-low"; mkdir -p "$_rp/.claude" "$_rp/.sutra" "$_rp/.enforcement"
env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$_rp" HOME="$home" \
  SUTRA_STEP_TIMEOUT_SCALE=1 \
  "$fake/bin/sutra-turn" run --event PreToolUse \
  < "$tmp/pre.json" > "$tmp/scalelow.out" 2> "$tmp/scalelow.err"
is "a scale below 100 is clamped and cannot shorten the budget" \
  "$(jq -s '[.[]|select(.kind=="step" and .step_id=="pre.second")][0].exit' \
     "$_rp/.sutra/turn/$sid.jsonl")" 0

# ============================================== 4. matcher: anchored ERE, one rule --
cat > "$fake/hooks/m.sh" <<'M'
#!/bin/sh
cat >/dev/null
exit 0
M
chmod 0755 "$fake/hooks/m.sh"
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "matcher_semantics": "anchored-ere",
  "events": {
    "PreToolUse": [
      {"id":"pre.alt","matcher":"Edit|Write","class":"B","impl":"shim:hooks/m.sh","timeout_ms":5000},
      {"id":"pre.mcp","matcher":"mcp__.*","class":"B","impl":"shim:hooks/m.sh","timeout_ms":5000},
      {"id":"pre.exact","matcher":"Edit","class":"B","impl":"shim:hooks/m.sh","timeout_ms":5000},
      {"id":"pre.star","matcher":"*","class":"B","impl":"shim:hooks/m.sh","timeout_ms":5000},
      {"id":"pre.none","class":"B","impl":"shim:hooks/m.sh","timeout_ms":5000}
    ]
  }
}
PIPE

ran() { jq -s '[.[]|select(.kind=="step")|.step_id]|sort|join(",")' -r "$1"; }

printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"MultiEdit"}' "$sid" > "$tmp/multi.json"
run m_multi PreToolUse "$tmp/multi.json"
is "Edit|Write does not match MultiEdit" "$(ran "$led")" "pre.none,pre.star"

printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"mcp__claude_ai_Gmail__send_message"}' "$sid" > "$tmp/mcp.json"
run m_mcp PreToolUse "$tmp/mcp.json"
is "mcp__.* matches an MCP tool" "$(ran "$led")" "pre.mcp,pre.none,pre.star"

run m_edit PreToolUse "$tmp/pre.json"
is "Edit matches Edit, and the alternation too" "$(ran "$led")" \
  "pre.alt,pre.exact,pre.none,pre.star"

# a semantics this runtime does not implement is refused, not guessed at
cat > "$fake/hooks/legacy-sem.sh" <<'LS'
#!/bin/sh
cat >/dev/null
printf 'LEGACY-SEM\n'
exit 0
LS
chmod 0755 "$fake/hooks/legacy-sem.sh"
cat > "$fake/hooks/hooks.json.step3" <<'REG3'
{
  "hooks": {
    "PreToolUse": [
      {"matcher":"*","hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/legacy-sem.sh"}]}
    ]
  }
}
REG3
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "matcher_semantics": "prefix-glob",
  "events": {
    "PreToolUse": [
      {"id":"pre.star","matcher":"*","class":"B","impl":"shim:hooks/m.sh","timeout_ms":5000}
    ]
  }
}
PIPE
run sem PreToolUse "$tmp/pre.json"
is "unknown matcher_semantics exit" "$rc" 0
# The notice is the RUNTIME's, not the host's input: it goes to fd 2, so the
# legacy hook's own stdout is all the host sees and stays parseable.
is "unknown matcher_semantics says so on fd 2" "$(head -1 "$tmp/sem.err")" \
  "sutra runtime degraded: unsupported matcher_semantics prefix-glob"
is "unknown matcher_semantics fell back to legacy" "$(head -1 "$tmp/sem.out")" "LEGACY-SEM"
is "the notice did not land on stdout" \
  "$(grep -c 'sutra runtime degraded' "$tmp/sem.out" 2>/dev/null || true)" 0
is "unknown matcher_semantics ran no pipeline step" \
  "$(jq -s '[.[]|select(.kind=="step")]|length' "$led")" 0
rm -f "$fake/hooks/hooks.json.step3"

# ================================================= 5. ONE merged JSON object --
cat > "$fake/hooks/allow.sh" <<'AL'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"rtk rewrite ok"}}\n'
exit 0
AL
cat > "$fake/hooks/denyjson.sh" <<'DJ'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"blueprint marker missing"}}\n'
exit 0
DJ
cat > "$fake/hooks/ctx.sh" <<'CX'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"CONTEXT-FROM-PRETOOL"}}\n'
exit 0
CX
cat > "$fake/hooks/plain.sh" <<'PL'
#!/bin/sh
cat >/dev/null
printf 'PLAIN-NUDGE\n'
exit 0
PL
chmod 0755 "$fake/hooks/allow.sh" "$fake/hooks/denyjson.sh" "$fake/hooks/ctx.sh" "$fake/hooks/plain.sh"

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PreToolUse": [
      {"id":"pre.plain","matcher":"*","class":"A","impl":"shim:hooks/plain.sh","timeout_ms":5000},
      {"id":"pre.allow","matcher":"*","class":"A","impl":"shim:hooks/allow.sh","timeout_ms":5000},
      {"id":"pre.denyjson","matcher":"*","class":"A","impl":"shim:hooks/denyjson.sh","timeout_ms":5000},
      {"id":"pre.ctx","matcher":"*","class":"A","impl":"shim:hooks/ctx.sh","timeout_ms":5000}
    ],
    "PermissionRequest": [
      {"id":"perm.one","matcher":"*","class":"A","impl":"shim:hooks/perm-one.sh","timeout_ms":5000},
      {"id":"perm.two","matcher":"*","class":"A","impl":"shim:hooks/perm-two.sh","timeout_ms":5000}
    ]
  }
}
PIPE

run merge PreToolUse "$tmp/pre.json"
is "merge exit" "$rc" 0
# THE WHOLE STDOUT IS ONE JSON OBJECT. The host parses a hook's stdout as JSON
# only when the entire stream is one object; "PLAIN-NUDGE\n{...deny...}" reached
# it as a plain string and the deny was lost. The plain step's text is therefore
# folded INTO the object - systemMessage on PreToolUse, which is where the host
# shows plain stdout on this event.
is "stdout parses as exactly one JSON object" "$(jq -s 'length' "$tmp/merge.out")" 1
if jq -e . "$tmp/merge.out" >/dev/null 2>&1; then ok; else
  fail "stdout is not valid JSON: [$(cat "$tmp/merge.out")]"; fi
is "the plain step's text survives, inside systemMessage" \
  "$(jq -r '.systemMessage' "$tmp/merge.out")" "PLAIN-NUDGE"
is "no bare plain line was printed beside the object" \
  "$(grep -c '^PLAIN-NUDGE$' "$tmp/merge.out" 2>/dev/null || true)" 0
obj="$(cat "$tmp/merge.out")"
is "most restrictive decision wins" \
  "$(printf '%s' "$obj" | jq -r '.hookSpecificOutput.permissionDecision')" "deny"
has "both reasons survive" \
  "$(printf '%s' "$obj" | jq -r '.hookSpecificOutput.permissionDecisionReason')" \
  "rtk rewrite ok | blueprint marker missing"
is "additionalContext reaches a PreToolUse emission" \
  "$(printf '%s' "$obj" | jq -r '.hookSpecificOutput.additionalContext')" "CONTEXT-FROM-PRETOOL"

# PermissionRequest: two allows, both rule sets kept.
#
# THE SHAPE IS THE TEST. This case used to feed a TOP-LEVEL {"decision":{...}},
# which no shipped hook emits - so it passed green for a release while the one
# registered PermissionRequest hook (hooks/permission-gate.sh, which puts its
# decision UNDER hookSpecificOutput) had its decision dropped on the floor and
# sutra-turn printed ZERO bytes. Every auto-allow rule stopped reaching the host
# and every MCP tool call prompted again. Golden parity could not see it: it
# projects per-step ledger stdout, never the event's emitted aggregate. So the
# synthetic hooks below emit the SHIPPED shape, and the section after this one
# pins the runtime's emission to the real hook's own output, byte for byte.
cat > "$fake/hooks/perm-one.sh" <<'P1'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow","updatedPermissions":[{"type":"addRules","rules":["Bash(rtk:*)"]}]}}}\n'
exit 0
P1
cat > "$fake/hooks/perm-two.sh" <<'P2'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow","updatedPermissions":[{"type":"addRules","rules":["Read(//tmp/**)"]},{"type":"addRules","rules":["Bash(rtk:*)"]}]}}}\n'
exit 0
P2
chmod 0755 "$fake/hooks/perm-one.sh" "$fake/hooks/perm-two.sh"
printf '{"session_id":"%s","hook_event_name":"PermissionRequest","tool_name":"Bash"}' "$sid" > "$tmp/perm.json"
run perm PermissionRequest "$tmp/perm.json"
is "permission exit" "$rc" 0
is "one JSON object for PermissionRequest" "$(jq -s 'length' "$tmp/perm.out")" 1
is "decision emitted UNDER hookSpecificOutput, not at top level" \
  "$(jq -r '[(.hookSpecificOutput.decision|type),(.decision|type)]|join(",")' "$tmp/perm.out")" \
  "object,null"
is "behavior merged" \
  "$(jq -r '.hookSpecificOutput.decision.behavior' "$tmp/perm.out")" "allow"
is "both rule sets concatenated" \
  "$(jq -r '[.hookSpecificOutput.decision.updatedPermissions[].rules[]]|join(",")' "$tmp/perm.out")" \
  "Bash(rtk:*),Read(//tmp/**)"
is "no permission rule is dropped on the floor" \
  "$(jq -s '[.[]|select(.kind=="dropped_json")]|length' "$led")" 0

# The runtime is a drop-in for the host: with permission-gate.sh as the ONLY
# registered step, what sutra-turn prints must BE what that hook prints.
#
# CLAUDE_PLUGIN_ROOT is the REAL plugin here on purpose: permission-gate.sh
# resolves its rule table relative to that root, so a hooks-only copy makes it
# emit nothing and the comparison would pass on two empty strings. The real
# root also means the REAL runtime/pipeline.json is what selects the step -
# the registration under test, not a hand-written one.
realproj="$tmp/proj-realperm"; mkdir -p "$realproj/.claude" "$realproj/.sutra" "$realproj/.enforcement"
printf '{"session_id":"%s","hook_event_name":"PermissionRequest","tool_name":"mcp__claude_ai_Gmail__send_message"}' \
  "$sid" > "$tmp/realperm.json"
realsteps="$(jq -r '[.events.PermissionRequest[]?
                     | select((.impl // "") | endswith("permission-gate.sh"))] | length' \
             "$runtime/pipeline.json" 2>/dev/null)"
realtotal="$(jq -r '(.events.PermissionRequest // []) | length' "$runtime/pipeline.json" 2>/dev/null)"
if [ -r "$plugin/hooks/permission-gate.sh" ] && [ "${realsteps:-0}" = "1" ] && [ "${realtotal:-0}" = "1" ]; then
  env CLAUDE_PLUGIN_ROOT="$plugin" CLAUDE_PROJECT_DIR="$realproj" HOME="$home" \
    sh "$plugin/hooks/permission-gate.sh" < "$tmp/realperm.json" \
    > "$tmp/realperm.direct" 2>/dev/null
  env CLAUDE_PLUGIN_ROOT="$plugin" CLAUDE_PROJECT_DIR="$realproj" HOME="$home" \
    "$fake/bin/sutra-turn" run --event PermissionRequest \
    < "$tmp/realperm.json" > "$tmp/realperm.turn" 2>/dev/null
  is "the real hook still auto-allows this MCP tool (test premise)" \
    "$(jq -r '.hookSpecificOutput.decision.behavior // "none"' "$tmp/realperm.direct" 2>/dev/null)" \
    "allow"
  is "runtime emission == permission-gate.sh's own output, byte for byte" \
    "$(jq -S -c . "$tmp/realperm.turn" 2>/dev/null)" \
    "$(jq -S -c . "$tmp/realperm.direct" 2>/dev/null)"
else
  # Not a silent skip: if the registration ever stops being "permission-gate.sh
  # alone", this assertion no longer means what it says and must be rewritten.
  fail "PermissionRequest registration is no longer permission-gate.sh alone (steps=${realtotal:-?}) - rewrite this case"
  fail "PermissionRequest registration is no longer permission-gate.sh alone (steps=${realtotal:-?}) - rewrite this case"
fi

# an unmergeable field is recorded, not silently dropped
cat > "$fake/hooks/weird.sh" <<'WD'
#!/bin/sh
cat >/dev/null
printf '{"someUnknownField":{"a":1}}\n'
exit 0
WD
chmod 0755 "$fake/hooks/weird.sh"
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "PostToolUse": [
      {"id":"post.weird","matcher":"*","class":"A","impl":"shim:hooks/weird.sh","timeout_ms":5000}
    ]
  }
}
PIPE
printf '{"session_id":"%s","hook_event_name":"PostToolUse","tool_name":"Edit"}' "$sid" > "$tmp/post.json"
run drop PostToolUse "$tmp/post.json"
is "dropped_json row written" \
  "$(jq -s '[.[]|select(.kind=="dropped_json")]|length' "$led")" 1
is "dropped_json names the step" \
  "$(jq -sr '[.[]|select(.kind=="dropped_json")][0].step_id' "$led")" "post.weird"

# ========================================== 6. every ledger row carries ts/event --
badts="$(jq -s '[.[]|select((.ts|type)!="string" or (.event|type)!="string")]|length' "$led")"
is "every row has a string ts and event" "$badts" 0

# ===== 7. ONE object per event, on every shape - and exit 2 where it counts --
# The host reads a hook's stdout as JSON only when the WHOLE stream is one
# object. Printing a step's plain nudge and then the merged object therefore
# destroyed BOTH: the deny, the Stop decision and the additionalContext were
# silently discarded on every event where one step printed text and another
# emitted a directive - and the shipped registry has exactly that pair on
# PreToolUse. Golden parity cannot see it (it projects PER-STEP stdout).
cat > "$fake/hooks/ups-plain.sh" <<'UP'
#!/bin/sh
cat >/dev/null
printf 'UPS-NUDGE\n'
exit 0
UP
cat > "$fake/hooks/ups-ctx.sh" <<'UC'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"CTX-FROM-HOOK"}}\n'
exit 0
UC
cat > "$fake/hooks/ups-deny.sh" <<'UD'
#!/bin/sh
cat >/dev/null
printf 'UPS-BLOCKED\n' >&2
exit 2
UD
cat > "$fake/hooks/hang2.sh" <<'H2'
#!/bin/sh
cat >/dev/null
sleep 5
exit 0
H2
chmod 0755 "$fake/hooks/ups-plain.sh" "$fake/hooks/ups-ctx.sh" \
           "$fake/hooks/ups-deny.sh" "$fake/hooks/hang2.sh"

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "UserPromptSubmit": [
      {"id":"ups.plain","matcher":"*","class":"A","impl":"shim:hooks/ups-plain.sh","timeout_ms":5000},
      {"id":"ups.ctx","matcher":"*","class":"A","impl":"shim:hooks/ups-ctx.sh","timeout_ms":5000}
    ],
    "PreToolUse": [
      {"id":"pre.hang2","matcher":"*","class":"B","impl":"shim:hooks/hang2.sh","timeout_ms":300},
      {"id":"pre.plain","matcher":"*","class":"A","impl":"shim:hooks/plain.sh","timeout_ms":5000}
    ]
  }
}
PIPE

# (a) context event: the plain text lands in additionalContext, which is where
#     the host would have put a plain-stdout hook's output anyway.
printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","prompt":"hi"}' "$sid" \
  > "$tmp/ups.json"
run upsfold UserPromptSubmit "$tmp/ups.json"
is "UPS fold exit" "$rc" 0
is "UPS stdout is exactly one JSON object" "$(jq -s 'length' "$tmp/upsfold.out")" 1
is "UPS plain text folded into additionalContext" \
  "$(jq -r '.hookSpecificOutput.additionalContext' "$tmp/upsfold.out")" \
  "$(printf 'CTX-FROM-HOOK\nUPS-NUDGE')"

# (a cont.) a timed-out class B step + a plain step: the loss is named on fd 2
#     AND the stdout the host reads is still one valid object.
run tmofold PreToolUse "$tmp/pre.json"
is "timeout-fold exit" "$rc" 0
is "a timed-out step is still named on fd 2" \
  "$(grep -c '^sutra runtime degraded: step pre.hang2 exceeded 300ms$' "$tmp/tmofold.err" 2>/dev/null || true)" 1
is "timeout-fold stdout is exactly one JSON object" "$(jq -s 'length' "$tmp/tmofold.out")" 1
is "the timeout sentence and the plain nudge both survive in systemMessage" \
  "$(jq -r '.systemMessage' "$tmp/tmofold.out")" \
  "$(printf 'sutra runtime degraded: step pre.hang2 exceeded 300ms\nPLAIN-NUDGE')"

# (e) exit 2 on UserPromptSubmit is a BLOCK the host honours (the prompt is not
#     processed). Propagating it only on PreToolUse and Stop downgraded a UPS
#     gate's refusal to a clean turn.
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "UserPromptSubmit": [
      {"id":"ups.deny","matcher":"*","class":"B","impl":"shim:hooks/ups-deny.sh","timeout_ms":5000},
      {"id":"ups.plain","matcher":"*","class":"A","impl":"shim:hooks/ups-plain.sh","timeout_ms":5000}
    ],
    "PostToolUse": [
      {"id":"post.deny","matcher":"*","class":"B","impl":"shim:hooks/ups-deny.sh","timeout_ms":5000}
    ]
  }
}
PIPE
run upsdeny UserPromptSubmit "$tmp/ups.json"
is "exit 2 on UserPromptSubmit propagates" "$rc" 2
is "the blocking step's stderr is on fd 2" \
  "$(grep -c '^UPS-BLOCKED$' "$tmp/upsdeny.err" 2>/dev/null || true)" 1
is "the other step still ran" \
  "$(jq -s '[.[]|select(.kind=="step")]|length' "$led")" 2
# ... and only where the host honours it: PostToolUse is left alone, so the
# runtime never invents a block of its own.
printf '{"session_id":"%s","hook_event_name":"PostToolUse","tool_name":"Edit"}' "$sid" \
  > "$tmp/post2.json"
run postdeny PostToolUse "$tmp/post2.json"
is "exit 2 on PostToolUse is not propagated" "$rc" 0

printf 'test-turn-concurrency: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
