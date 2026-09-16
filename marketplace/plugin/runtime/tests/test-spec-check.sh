#!/usr/bin/env bash
# test-spec-check.sh - runtime/spec-check.sh must judge the registry by DERIVED
# counts, never by a literal.
#
# WHY. spec-check used to assert that the collapsed hooks.json holds "exactly 8
# registrations". EXECUTION step 37 adds one more by design (SubagentStop), and
# dropping the dead UserPromptExpansion entry took one away, so a literal would
# have gone red twice on changes the plan calls for - and the fix people reach
# for in that moment is to bump the literal, which is how a validator stops
# validating. The expected number is derived: one `sutra-turn run --event <E>`
# per event THIS pipeline declares, plus exactly one bare sutra-canary (7
# today). The asserts that do the real work - one runtime registration per
# event, exactly one canary, no legacy hook left in the collapsed file, no
# event registered with zero steps (check 13) - are re-proved here, and every
# count in this file is read out of the two files rather than written down.
#
# bash 3.2 + jq. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-spec-check.sh

set -u

here="$(cd "$(dirname "$0")" && pwd -P)"
runtime="$(cd "$here/.." && pwd -P)"
plugin="$(cd "$runtime/.." && pwd -P)"

checks=0
failed=0
ok()   { checks=$((checks+1)); }
fail() { checks=$((checks+1)); failed=$((failed+1)); printf 'FAIL %s\n' "$*" >&2; }
is()   { if [ "$2" = "$3" ]; then ok; else fail "$1: expected [$3] got [$2]"; fi; }
has()  { if grep -q "$2" "$3" 2>/dev/null; then ok; else
           fail "$1: no line matching [$2] in $3"; sed -n '1,6p' "$3" >&2; fi; }

command -v jq >/dev/null 2>&1 || { printf 'test-spec-check: jq required\nfailed=1\n'; exit 1; }
for f in "$runtime/spec-check.sh" "$runtime/pipeline.json" \
         "$plugin/hooks/hooks.json" "$plugin/hooks/hooks.json.step3"; do
  [ -r "$f" ] || { printf 'test-spec-check: missing %s\nfailed=1\n' "$f"; exit 1; }
done

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-speccheck.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# ---------------------------------------------------- the shipped registry --
# The control: today's 6-event pipeline against today's 7-entry collapsed file.
# Both numbers are DERIVED here too, so this line does not go stale either.
out="$tmp/live.log"
bash "$runtime/spec-check.sh" "$runtime/pipeline.json" > "$out" 2>&1
is "the shipped pipeline passes" "$?" 0
is "one runtime registration per declared event, plus the canary" \
  "$(jq '[.hooks[][].hooks[]]|length' "$plugin/hooks/hooks.json")" \
  "$(jq '(.events|keys|length)+1' "$runtime/pipeline.json")"

# ------------------------------------------- the 8-registration future case --
# A throw-away plugin whose hooks.json, hooks.json.step3 and pipeline.json all
# carry SubagentStop. spec-check resolves the registry from ITS OWN directory,
# so the copy has to be a whole little plugin.
mk9() {  # mk9 <dir>
  mkdir -p "$1/runtime" "$1/hooks"
  cp "$runtime/spec-check.sh" "$1/runtime/spec-check.sh"
  jq '.hooks.SubagentStop = [{"matcher":"*","hooks":[
        {"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/subagent-probe.sh"}]}]' \
    "$plugin/hooks/hooks.json.step3" > "$1/hooks/hooks.json.step3"
  # The runtime registration carries an explicit timeout: check 12 rejects a
  # collapsed registration that leans on the host default, and 10 s covers the
  # 5000 ms step below with the standard 5 s runtime margin.
  jq '.hooks.SubagentStop = [{"hooks":[
        {"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event SubagentStop","timeout":10}]}]' \
    "$plugin/hooks/hooks.json" > "$1/hooks/hooks.json"
  jq '.events.SubagentStop = [{
        "id":"sub.subagent-probe","matcher":"*","class":"B",
        "impl":"shim:hooks/subagent-probe.sh","timeout_ms":5000,
        "on_error":"warn","replaces":["hooks/subagent-probe.sh"],
        "killswitch_aliases":[]}]
      | .budgets.event_wall_ms.SubagentStop = 20000' \
    "$runtime/pipeline.json" > "$1/runtime/pipeline.json"
}

p9="$tmp/p9"; mk9 "$p9"
is "the fixture holds one more registration than the shipped file" \
  "$(jq '[.hooks[][].hooks[]]|length' "$p9/hooks/hooks.json")" \
  "$(( $(jq '[.hooks[][].hooks[]]|length' "$plugin/hooks/hooks.json") + 1 ))"
bash "$p9/runtime/spec-check.sh" "$p9/runtime/pipeline.json" > "$tmp/nine.log" 2>&1
is "one more registration the pipeline declares is accepted" "$?" 0
has "and it says so" "live registry $(jq '[.hooks[][].hooks[]]|length' "$p9/hooks/hooks.json") entries" "$tmp/nine.log"

# ------------------------------------------------ the asserts that still bite --
# a DUPLICATE runtime registration
pdup="$tmp/pdup"; mk9 "$pdup"
jq '.hooks.Stop += [{"hooks":[
      {"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event Stop"}]}]' \
  "$p9/hooks/hooks.json" > "$pdup/hooks/hooks.json"
bash "$pdup/runtime/spec-check.sh" "$pdup/runtime/pipeline.json" > "$tmp/dup.log" 2>&1
is "a duplicate sutra-turn registration is rejected" "$?" 3
has "and it names the event" "2 .sutra-turn run --event Stop. registrations" "$tmp/dup.log"

# a ROGUE legacy hook left in the collapsed file
prog="$tmp/prog"; mk9 "$prog"
jq '.hooks.PreToolUse += [{"matcher":"Edit","hooks":[
      {"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/rogue-gate.sh"}]}]' \
  "$p9/hooks/hooks.json" > "$prog/hooks/hooks.json"
bash "$prog/runtime/spec-check.sh" "$prog/runtime/pipeline.json" > "$tmp/rogue.log" 2>&1
is "a legacy hook left in the collapsed file is rejected" "$?" 3
has "and it names the hook" "still registers a legacy hook" "$tmp/rogue.log"

# a MISSING canary
pnc="$tmp/pnc"; mk9 "$pnc"
jq '.hooks.UserPromptSubmit |= [ .[] | .hooks |= [ .[] |
      select((.command // "") | test("sutra-canary") | not) ] ]' \
  "$p9/hooks/hooks.json" > "$pnc/hooks/hooks.json"
bash "$pnc/runtime/spec-check.sh" "$pnc/runtime/pipeline.json" > "$tmp/nocanary.log" 2>&1
is "a missing canary is rejected" "$?" 3
has "and it says how many it found" "sutra-canary registrations, expected exactly 1" "$tmp/nocanary.log"

# an event key that is not canonical at all
pbad="$tmp/pbad"; mk9 "$pbad"
jq '.events.Bogus = []' "$p9/runtime/pipeline.json" > "$pbad/runtime/pipeline.json"
bash "$pbad/runtime/spec-check.sh" "$pbad/runtime/pipeline.json" > "$tmp/bogus.log" 2>&1
is "a non-canonical event key is rejected" "$?" 3
has "and it names the key" "non-canonical key" "$tmp/bogus.log"

# ------------------------------------------- check 12: host cap vs budgets --
# THE REGRESSION. Collapsing the registry gave each event ONE host timeout for
# every step folded under it. A step budget larger than that timeout is not a
# slow hook being killed any more - the host SIGKILLs sutra-turn itself and the
# whole event disappears (no step rows, no emit, no stage_digest). Stop is the
# worst case: stop.domains-site-refresh alone is 150000 ms, and the collapsed
# file shipped a 25 s cap.
pcap="$tmp/pcap"; mk9 "$pcap"
jq '.hooks.Stop = [{"hooks":[{"type":"command",
      "command":"${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event Stop","timeout":25}]}]' \
  "$p9/hooks/hooks.json" > "$pcap/hooks/hooks.json"
bash "$pcap/runtime/spec-check.sh" "$pcap/runtime/pipeline.json" > "$tmp/cap.log" 2>&1
is "a host timeout below the largest step budget is rejected" "$?" 3
has "and it names the event and the cap" "event Stop: hooks.json timeout 25s" "$tmp/cap.log"
has "and it names the step budget it cannot cover" "BELOW the largest step budget 150000ms" "$tmp/cap.log"
has "and it says what to register instead" "register at least 155s" "$tmp/cap.log"

# a collapsed registration with NO timeout at all leans on the host default,
# which is invisible in the file and wrong for Stop either way.
pnt="$tmp/pnt"; mk9 "$pnt"
jq 'del(.hooks.Stop[0].hooks[0].timeout)' "$p9/hooks/hooks.json" > "$pnt/hooks/hooks.json"
bash "$pnt/runtime/spec-check.sh" "$pnt/runtime/pipeline.json" > "$tmp/notimeout.log" 2>&1
is "a runtime registration with no timeout is rejected" "$?" 3
has "and it says the cap must be explicit" "carries no numeric timeout" "$tmp/notimeout.log"

# the event_wall_ms arm. For every event that HAS steps, check 5 (sum <= wall)
# already implies wall >= max, so the only reachable case is an event that
# declares no step yet: its floor is budgets.step_default_ms, because that is
# what the first step added there will inherit. Check 13 rejects such an event
# outright, but check 12 runs FIRST and its message is the one that names the
# budget, so the fixture below has to satisfy check 12 to reach check 13 - and
# this one deliberately does not.
#
# mkempty <dir> <wall_ms>: a plugin whose pipeline declares UserPromptExpansion
# with zero steps and whose collapsed registry registers it - exactly the shape
# that shipped before this fix. The registration keeps the registry count equal
# to "one per declared event + canary" so check 10 stays green.
mkempty() {  # mkempty <dir> <wall_ms>
  mk9 "$1"
  jq --argjson w "$2" '.events.UserPromptExpansion = []
        | .budgets.event_wall_ms.UserPromptExpansion = $w' \
    "$p9/runtime/pipeline.json" > "$1/runtime/pipeline.json"
  jq '.hooks.UserPromptExpansion = [{"hooks":[
        {"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event UserPromptExpansion","timeout":10}]}]' \
    "$p9/hooks/hooks.json" > "$1/hooks/hooks.json"
}

pwall="$tmp/pwall"; mkempty "$pwall" 1000
bash "$pwall/runtime/spec-check.sh" "$pwall/runtime/pipeline.json" > "$tmp/wall.log" 2>&1
is "an event_wall_ms below the step-default floor is rejected" "$?" 3
has "and it names the event and the budget" \
  "event UserPromptExpansion: budgets.event_wall_ms 1000ms is BELOW" "$tmp/wall.log"

# ------------------------------------------------ check 13: no dead event --
# THE ROUND-6 REGRESSION. The collapsed registry registered
# `sutra-turn run --event UserPromptExpansion` while the pipeline declared that
# event as an empty array and hooks.json.step3 registered nothing there at all:
# every prompt expansion would fork the runtime, select no step, write an
# orphan_turn + stage_digest row and exit. Checks 1-12 are all green on it -
# the spec and the registry are each internally consistent - so this fixture is
# check 13's and nothing else's. Budgets are correct here on purpose so the
# failure cannot be blamed on check 12.
pdead="$tmp/pdead"; mkempty "$pdead" 10000
bash "$pdead/runtime/spec-check.sh" "$pdead/runtime/pipeline.json" > "$tmp/dead.log" 2>&1
is "a registered event with zero steps is rejected" "$?" 3
has "and it names the event" \
  "event UserPromptExpansion: declared in the pipeline with ZERO steps" "$tmp/dead.log"
has "and it says the fork buys nothing" "orphan_turn" "$tmp/dead.log"
has "and check 12 is NOT what fired" "no steps" "$tmp/dead.log"

# an empty event declaration that is NOT registered is still a placeholder, not
# a spec - but it also unbalances check 10's derived count, so this fixture
# proves the pair is rejected, whichever of the two speaks first.
pempty="$tmp/pempty"; mkempty "$pempty" 10000
cp "$p9/hooks/hooks.json" "$pempty/hooks/hooks.json"
bash "$pempty/runtime/spec-check.sh" "$pempty/runtime/pipeline.json" > "$tmp/empty.log" 2>&1
is "an unregistered empty event declaration is rejected" "$?" 3

# and the reverse direction: a runtime registration for an event the pipeline
# does not declare. Check 10's derived count speaks first (the registry now
# holds one more entry than "one per declared event + canary"); check 13's
# second arm is the backstop for the day a future check-10 shape lets the count
# match anyway. Either way the release gate is red.
punreg="$tmp/punreg"; mk9 "$punreg"
jq '.hooks.UserPromptExpansion = [{"hooks":[
      {"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event UserPromptExpansion","timeout":10}]}]' \
  "$p9/hooks/hooks.json" > "$punreg/hooks/hooks.json"
bash "$punreg/runtime/spec-check.sh" "$punreg/runtime/pipeline.json" > "$tmp/unreg.log" 2>&1
is "a runtime registration for an undeclared event is rejected" "$?" 3

# the shipped pair is green on check 13: every event the pipeline declares has
# at least one step, and every registered runtime event is one of them. Derived
# from the two files, not asserted as a list of names.
is "no shipped event declares zero steps" \
  "$(jq '[.events[] | select(length == 0)] | length' "$runtime/pipeline.json")" 0
is "every registered runtime event is declared with steps" \
  "$(jq -r --slurpfile s "$runtime/pipeline.json" '
       [ .hooks | to_entries[] | .key as $e | .value[] | (.hooks // [])[]
         | select((.command // "") | test("sutra-turn run --event"))
         | select((($s[0].events[$e] // []) | length) == 0) ] | length' \
     "$plugin/hooks/hooks.json")" 0

# and the shipped pair is green on check 12 - proved by the control at the top,
# restated here against the real files so a reader sees the positive case.
bash "$runtime/spec-check.sh" "$runtime/pipeline.json" "$plugin/hooks/hooks.json.step3" \
  > "$tmp/cap-ok.log" 2>&1
is "the shipped hooks.json covers every step budget" "$?" 0

# the red fixture that ships with the runtime still fails
bash "$runtime/spec-check.sh" "$here/spec-missing.json" > "$tmp/red.log" 2>&1
is "the red fixture is still rejected" "$?" 3

printf 'test-spec-check: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
