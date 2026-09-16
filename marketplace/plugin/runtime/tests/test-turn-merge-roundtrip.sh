#!/usr/bin/env bash
# test-turn-merge-roundtrip.sh - the merger must not eat anything the fleet
# actually prints.
#
# WHY THIS FILE EXISTS. sutra-turn merges every step's JSON object into at most
# one object for the host. The merger is a whitelist: a key with no rule lands in
# the "dropped" arm, is written to the ledger as kind=dropped_json, and never
# reaches fd 1. For a release, hookSpecificOutput.decision had no rule - the
# exact shape hooks/permission-gate.sh emits - so sutra-turn printed ZERO bytes
# on PermissionRequest, no auto-allow rule ever reached the host, and every MCP
# tool call prompted again. Nothing caught it:
#
#   - golden parity (bin/sutra-charcap) diffs PER-STEP ledger stdout against the
#     recorded corpus. The step's stdout was recorded correctly. The EVENT's
#     emitted aggregate - the thing the host reads - is not what parity compares.
#   - the unit case in test-turn-concurrency.sh fed a top-level {"decision":{}},
#     a shape no shipped hook emits, and passed.
#
# So this suite closes the loop from the other side: it takes the RECORDED FLEET
# OUTPUT itself (every expect/*.stdout under hooks/tests/golden that is a single
# JSON object), replays each one through the merger as the only step of its
# event, and demands the emitted object back, whole.
#
# ZERO DROPS ALLOWED. Equality is modulo key order and modulo exactly one field
# the runtime intentionally adds:
#
#   A1. hookSpecificOutput.hookEventName - re-stamped from the event sutra-turn
#       was invoked for, because the host's event name is authoritative and a
#       hook that names a different one must not misinform it. Neutralised here
#       by invoking each case with its OWN hookEventName, so the expected value
#       is the recorded one and the assertion stays exact.
#
# There is no second exception. If a future key needs one, add it to that list
# with its reason - do not loosen the comparison.
#
# bash 3.2 + jq, no GNU coreutils. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-turn-merge-roundtrip.sh

set -u

here="$(cd "$(dirname "$0")" && pwd -P)"
runtime="$(cd "$here/.." && pwd -P)"
plugin="$(cd "$runtime/.." && pwd -P)"
turn="$plugin/bin/sutra-turn"
golden="$plugin/hooks/tests/golden"

checks=0
failed=0
ok()   { checks=$((checks+1)); }
fail() { checks=$((checks+1)); failed=$((failed+1)); printf 'FAIL %s\n' "$*" >&2; }
is()   { if [ "$2" = "$3" ]; then ok; else fail "$1: expected [$3] got [$2]"; fi; }

command -v jq >/dev/null 2>&1 || {
  printf 'test-turn-merge-roundtrip: jq required\nfailed=1\n'; exit 1; }
[ -x "$turn" ] || {
  printf 'test-turn-merge-roundtrip: %s not executable\nfailed=1\n' "$turn"; exit 1; }
[ -d "$golden" ] || {
  printf 'test-turn-merge-roundtrip: no corpus at %s\nfailed=1\n' "$golden"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-rt.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# ------------------------------------------------------- throw-away plugin --
fake="$tmp/plugin"
mkdir -p "$fake/bin" "$fake/runtime" "$fake/hooks"
cp "$turn" "$fake/bin/sutra-turn"; chmod 0755 "$fake/bin/sutra-turn"
cp "$runtime/shim.sh" "$runtime/ledger.sh" "$fake/runtime/"

sid="11111111-2222-3333-4444-555555555555"
home="$tmp/home"; mkdir -p "$home"

# The step under test: it replays one recorded stdout byte for byte. Class B so
# that a drop would ALSO have to print the degraded line on fd 2 - both halves
# of the no-silent-loss contract are exercised by the same case.
cat > "$fake/hooks/replay.sh" <<'REPLAY'
#!/bin/sh
cat >/dev/null
cat "$SUTRA_RT_CASE"
exit 0
REPLAY
chmod 0755 "$fake/hooks/replay.sh"

# One registration per event - --event picks which one runs.
cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "SessionStart": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ],
    "UserPromptExpansion": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ],
    "UserPromptSubmit": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ],
    "PreToolUse": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ],
    "PostToolUse": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ],
    "PermissionRequest": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ],
    "Stop": [
      {"id":"rt.replay","matcher":"*","class":"B","impl":"shim:hooks/replay.sh","timeout_ms":9000}
    ]
  }
}
PIPE

# ------------------------------------------ 1. collect the recorded objects --
# Every non-empty expect/*.stdout in the corpus that is ONE JSON object,
# de-duplicated by content: the recorded files collapse to a handful of distinct
# SHAPES, and a shape is what the merger either understands or eats.
cases="$tmp/cases"; mkdir -p "$cases"
scanned=0
find "$golden" -path '*/expect/*.stdout' -size +0 > "$tmp/files.txt" 2>/dev/null
while IFS= read -r f; do
  [ -n "$f" ] || continue
  scanned=$((scanned+1))
  jq -e -cs 'length == 1 and (.[0]|type) == "object"' "$f" >/dev/null 2>&1 || continue
  jq -cs '.[0]' "$f" 2>/dev/null
done < "$tmp/files.txt" | sort -u > "$tmp/objs.txt"

n_files="$(wc -l < "$tmp/files.txt" | tr -d ' ')"
n_objs="$(wc -l < "$tmp/objs.txt" | tr -d ' ')"

# A corpus that yields nothing would make every assertion below vacuous.
if [ "${n_objs:-0}" -lt 1 ]; then
  fail "corpus yielded no JSON-object stdout (scanned $n_files files) - this suite would be vacuous"
  printf 'test-turn-merge-roundtrip: checks=%s failed=%s\n' "$checks" "$failed"
  [ "$failed" -eq 0 ]
  exit
fi
ok   # the corpus produced at least one shape

# ------------------------------------------------ 2. replay each one, whole --
i=0
round_fail=0
drop_fail=0
event_seen=""
while IFS= read -r obj; do
  [ -n "$obj" ] || continue
  i=$((i+1))
  cfile="$cases/case-$i.json"
  printf '%s\n' "$obj" > "$cfile"

  # A1: invoke with the case's own hookEventName so the re-stamp is a no-op.
  # A recorded object with no hookSpecificOutput (the {"decision","reason"} Stop
  # gates) never carries one; Stop is where the fleet emits that shape.
  ev="$(printf '%s' "$obj" | jq -r '.hookSpecificOutput.hookEventName // "Stop"')"
  case "$ev" in
    SessionStart|UserPromptExpansion|UserPromptSubmit|PreToolUse|PostToolUse|PermissionRequest|Stop) ;;
    *) ev="Stop" ;;
  esac
  case " $event_seen " in *" $ev "*) ;; *) event_seen="$event_seen $ev" ;; esac

  proj="$tmp/proj-$i"; mkdir -p "$proj/.claude" "$proj/.sutra" "$proj/.enforcement"
  printf '{"session_id":"%s","hook_event_name":"%s","tool_name":"Bash"}' "$sid" "$ev" \
    > "$tmp/in-$i.json"

  env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$proj" HOME="$home" \
      SUTRA_RT_CASE="$cfile" \
    "$fake/bin/sutra-turn" run --event "$ev" \
    < "$tmp/in-$i.json" > "$tmp/out-$i" 2> "$tmp/err-$i"

  got="$(jq -S -c . "$tmp/out-$i" 2>/dev/null)"
  want="$(jq -S -c . "$cfile" 2>/dev/null)"
  if [ "$got" != "$want" ]; then
    round_fail=$((round_fail+1))
    printf 'FAIL roundtrip case %s (%s)\n  want %s\n  got  %s\n' "$i" "$ev" "$want" "$got" >&2
  fi

  led="$proj/.sutra/turn/$sid.jsonl"
  d="$(jq -s '[.[]|select(.kind=="dropped_json")]|length' "$led" 2>/dev/null)"
  [ -n "${d:-}" ] || d=0
  if [ "$d" != "0" ]; then
    drop_fail=$((drop_fail+1))
    printf 'FAIL drop case %s (%s): %s\n' "$i" "$ev" \
      "$(jq -sr '[.[]|select(.kind=="dropped_json")|.note]|join("; ")' "$led" 2>/dev/null)" >&2
  fi
done < "$tmp/objs.txt"

is "every recorded object round-trips through the merger unchanged" "$round_fail" 0
is "zero dropped_json rows across the whole corpus" "$drop_fail" 0
is "every collected shape was replayed" "$i" "$n_objs"

# The corpus must still be exercising the shape that broke: a PermissionRequest
# decision under hookSpecificOutput. If the fleet ever stops recording it, this
# suite quietly stops guarding it, so say so out loud.
permshapes="$(grep -c '"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision"' \
  "$tmp/objs.txt" 2>/dev/null || true)"
[ -n "${permshapes:-}" ] || permshapes=0
if [ "$permshapes" -ge 1 ]; then ok; else
  fail "corpus no longer records a PermissionRequest hookSpecificOutput.decision - the regression this suite exists for is unguarded"
fi

# ------------------------------- 3. a genuinely unknown key is NOT silent --
# The other half of the contract: what the merger cannot merge must be loud.
cat > "$fake/hooks/replay.sh" <<'REPLAY2'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","someFutureKey":{"a":1}}}\n'
exit 0
REPLAY2
chmod 0755 "$fake/hooks/replay.sh"
proj="$tmp/proj-unknown"; mkdir -p "$proj/.claude" "$proj/.sutra" "$proj/.enforcement"
printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"Bash"}' "$sid" \
  > "$tmp/in-unknown.json"
env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$proj" HOME="$home" \
  "$fake/bin/sutra-turn" run --event PreToolUse \
  < "$tmp/in-unknown.json" > "$tmp/out-unknown" 2> "$tmp/err-unknown"
led="$proj/.sutra/turn/$sid.jsonl"
is "an unknown key is recorded as dropped_json" \
  "$(jq -s '[.[]|select(.kind=="dropped_json")]|length' "$led" 2>/dev/null)" 1
is "a class B drop also says so on fd 2" \
  "$(grep -c 'sutra runtime degraded: step rt.replay emitted hookSpecificOutput.someFutureKey with no merge rule' \
      "$tmp/err-unknown" 2>/dev/null || echo 0)" 1

printf 'test-turn-merge-roundtrip: shapes=%s (from %s recorded files), events=%s\n' \
  "$n_objs" "$n_files" "$(printf '%s' "$event_seen" | sed 's/^ //')"
printf 'test-turn-merge-roundtrip: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
