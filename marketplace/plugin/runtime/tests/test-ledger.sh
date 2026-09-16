#!/usr/bin/env bash
# test-ledger.sh - runtime/ledger.sh: three rows, both files, digest re-derived.
#
# The ledger is the only record of what sutra-turn did on a turn, so the test
# asserts the things a reviewer would later rely on: the rows are valid JSON,
# the canonical row carries the digest of the bytes the step produced, the flat
# row carries those bytes verbatim, and the stage digest is reproducible from
# the rows alone (not from the accumulator the run used, which is deleted).
#
# bash 3.2 + jq. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-ledger.sh

set -u

here="$(cd "$(dirname "$0")" && pwd -P)"
runtime="$(cd "$here/.." && pwd -P)"

checks=0
failed=0
ok()   { checks=$((checks+1)); }
fail() { checks=$((checks+1)); failed=$((failed+1)); printf 'FAIL %s\n' "$*" >&2; }
is()   { if [ "$2" = "$3" ]; then ok; else fail "$1: expected [$3] got [$2]"; fi; }

command -v jq >/dev/null 2>&1 || { printf 'test-ledger: jq required\nfailed=1\n'; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-ledger.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

proj="$tmp/proj"; mkdir -p "$proj"
sid="11111111-2222-3333-4444-555555555555"
turn="deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

# shellcheck source=../ledger.sh
. "$runtime/ledger.sh"

sutra_ledger_init "$proj" "$sid" "$turn" "UserPromptSubmit"

canon="$proj/.sutra/turn/$sid/$turn.jsonl"
flat="$proj/.sutra/turn/$sid.jsonl"

# three steps: a quiet one, one that emits additionalContext, one that denies.
printf '' > "$tmp/0.out";  printf '' > "$tmp/0.err"
printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"BLOCK ONE"}}\n' > "$tmp/1.out"
printf '' > "$tmp/1.err"
printf '' > "$tmp/2.out"
printf 'BLOCKED - marker missing\n' > "$tmp/2.err"

sutra_ledger_step 0 "ups.reset-turn-markers" ups "shim:hooks/reset-turn-markers.sh" \
  "hooks/reset-turn-markers.sh" 0 12 "$tmp/0.out" "$tmp/0.err"
sutra_ledger_step 1 "ups.per-turn-discipline-prompt" ups "shim:hooks/per-turn-discipline-prompt.sh" \
  "hooks/per-turn-discipline-prompt.sh" 0 34 "$tmp/1.out" "$tmp/1.err"
sutra_ledger_step 2 "ups.placement-resolve" ups "shim:hooks/placement-resolve.sh" \
  "hooks/placement-resolve.sh" 2 56 "$tmp/2.out" "$tmp/2.err"

digest="$(sutra_ledger_digest)"

# 1. both files exist
[ -f "$canon" ] && ok || fail "canonical ledger missing at $canon"
[ -f "$flat" ]  && ok || fail "flat ledger missing at $flat"

# 2. row counts: 3 steps + 1 stage_digest
is "canonical rows" "$(grep -c . "$canon")" 4
is "flat rows"      "$(grep -c . "$flat")"  4

# 3. every row is valid JSON
bad=0
while IFS= read -r line; do
  printf '%s' "$line" | jq -e . >/dev/null 2>&1 || bad=$((bad+1))
done < "$canon"
while IFS= read -r line; do
  printf '%s' "$line" | jq -e . >/dev/null 2>&1 || bad=$((bad+1))
done < "$flat"
is "invalid JSON rows" "$bad" 0

# 4. canonical step rows carry the contract's fields
is "canonical step count" \
  "$(jq -s '[.[] | select(.kind=="step")] | length' "$canon")" 3
is "canonical field set" \
  "$(jq -sr '[.[] | select(.kind=="step")][0] | [has("turn_id"),has("step_id"),has("family"),has("impl"),has("exit"),has("dur_ms"),has("stdout_sha"),has("stderr_sha"),has("ts"),has("event")] | all' "$canon")" \
  "true"

# 4b. ts AND event on EVERY row, in both files. bin/sutra-overhead derives
# work_ms from "first UserPromptSubmit row -> Stop stage_digest row"; with no
# stamp that subtraction is structurally 0 and the overhead KR measures nothing.
# ts is a STRING on purpose: bin/sutra-charcap seds the ledger before parsing it
# and rewrites any bare 10- or 13-digit number to <TS>, which would leave the
# row invalid JSON.
is "every canonical row has a string ts" \
  "$(jq -s '[.[] | select((.ts | type) != "string")] | length' "$canon")" 0
is "every flat row has a string ts" \
  "$(jq -s '[.[] | select((.ts | type) != "string")] | length' "$flat")" 0
is "every canonical row names its event" \
  "$(jq -s '[.[] | select((.event | type) != "string")] | length' "$canon")" 0
is "ts is epoch seconds" \
  "$(jq -sr '[.[] | select(.kind=="step")][0].ts | tonumber > 1700000000' "$canon")" "true"
is "the stage_digest row is stamped too" \
  "$(jq -sr '[.[] | select(.kind=="stage_digest")][0].ts | tonumber > 1700000000' "$canon")" "true"
# the whole point: a normalised ledger is still parseable JSON
sed -E -e 's%[0-9]{13}%<TS>%g' -e 's%[0-9]{10}%<TS>%g' "$canon" > "$tmp/canon.norm"
is "a charcap-normalised ledger is still JSON" \
  "$(jq -s 'length' "$tmp/canon.norm" 2>/dev/null)" "4"

# 5. the recorded digest is the digest of the bytes the step produced
want_sha="$(shasum -a 256 "$tmp/1.out" | awk '{print $1}')"
got_sha="$(jq -sr '[.[] | select(.kind=="step")][1].stdout_sha' "$canon")"
is "stdout_sha of step 1" "$got_sha" "$want_sha"

# 6. the flat row carries the raw bytes charcap diffs
is "flat stdout text" \
  "$(jq -sr '[.[] | select(.kind=="step")][1].stdout' "$flat")" \
  "$(cat "$tmp/1.out")"
is "flat stderr text" \
  "$(jq -sr '[.[] | select(.kind=="step")][2].stderr' "$flat")" \
  "$(cat "$tmp/2.err")"
is "flat exit code" \
  "$(jq -sr '[.[] | select(.kind=="step")][2].exit' "$flat")" "2"

# 7. stage digest re-derived FROM THE ROWS (the run's accumulator is gone)
jq -sr '[.[] | select(.kind=="step") | "\(.step_id):\(.exit)"] | join("\n")' "$canon" > "$tmp/acc.nl"
printf '%s' "$(cat "$tmp/acc.nl")" > "$tmp/acc"   # drop jq's trailing newline
rederived="$(shasum -a 256 "$tmp/acc" | awk '{print $1}')"
recorded="$(jq -sr '[.[] | select(.kind=="stage_digest")][0].stage_digest' "$canon")"
is "stage digest re-derived" "$rederived" "$recorded"
is "stage digest returned"   "$digest"    "$recorded"
is "stage digest step count" \
  "$(jq -sr '[.[] | select(.kind=="stage_digest")][0].steps' "$canon")" 3

# 8. a note row survives without jq-shaped input
sutra_ledger_note killswitch "runtime disabled"
is "note row kind" \
  "$(jq -sr '[.[] | select(.kind=="killswitch")] | length' "$flat")" 1
is "note row is stamped" \
  "$(jq -sr '[.[] | select(.kind=="killswitch")][0].ts | tonumber > 1700000000' "$flat")" "true"

# 8b. a note ABOUT one step carries that step's id (dropped_json always does)
sutra_ledger_note dropped_json "field decision.foo has no merge rule" "pre.rtk-auto-rewrite"
is "dropped_json names the step" \
  "$(jq -sr '[.[] | select(.kind=="dropped_json")][0].step_id' "$flat")" "pre.rtk-auto-rewrite"
is "a note with no step carries no step_id" \
  "$(jq -sr '[.[] | select(.kind=="killswitch")][0] | has("step_id")' "$flat")" "false"

# 9. a skip row is NOT counted as a step
sutra_ledger_skip 3 "ups.capture-prompt" "hooks/capture-prompt.sh" "blocked-by-earlier-deny"
is "skip is not a step" \
  "$(jq -s '[.[] | select(.kind=="step")] | length' "$flat")" 3
is "skip row present" \
  "$(jq -s '[.[] | select(.kind=="skip")] | length' "$flat")" 1

# 10. A TURN THAT SELECTS NO STEPS still gets a stage_digest row, and writes
# nothing to stderr. UserPromptExpansion has zero steps in the shipped
# pipeline, so this is not a hypothetical: `grep -c .` on an empty accumulator
# prints 0 AND exits 1, and the old `|| echo 0` guard turned the count into the
# two-line string "0\n0", which --argjson rejects - no digest row, and three
# lines of jq error on the terminal on every expansion.
proj0="$tmp/proj0"; mkdir -p "$proj0"
turn0="0000000000000000000000000000000000000000000000000000000000000000"
sutra_ledger_init "$proj0" "$sid" "$turn0" "UserPromptExpansion"
digest0="$(sutra_ledger_digest 2>"$tmp/zero.err")"
canon0="$proj0/.sutra/turn/$sid/$turn0.jsonl"

is "zero-step stderr is empty" "$(wc -c < "$tmp/zero.err" | tr -d ' ')" 0
is "zero-step row count" "$(grep -c . "$canon0")" 1
is "zero-step row kind" \
  "$(jq -sr '.[0].kind' "$canon0")" "stage_digest"
is "zero-step steps=0" \
  "$(jq -sr '.[0].steps' "$canon0")" "0"
# sha256 of the empty string - the digest of an empty ordered list.
is "zero-step digest is the empty-string sha256" \
  "$digest0" "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
is "zero-step row is valid JSON" \
  "$(jq -sr 'length' "$canon0" 2>/dev/null)" "1"

# 11. RETENTION. pipeline.json has always declared budgets.context.ledger_max_bytes
# and ledger_retention_days and nothing read them, so .sutra/turn grew without
# bound - an append-only file per turn, per session, for ever. sutra_ledger_init
# now enforces both before the turn's first row:
#   size  the flat per-session file rolls to "<name>.jsonl.1" - the suffix goes
#         AFTER .jsonl so bin/sutra-charcap's *.jsonl glob ignores the roll-off
#   age   turn files older than the budget go, then the directories they emptied,
#         and never this turn's own file or this session's directory
projR="$tmp/projR"; mkdir -p "$projR"
sidR="retention-1111-2222-3333"
turnR="cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe"
turnsR="$projR/.sutra/turn"
mkdir -p "$turnsR/$sidR" "$turnsR/oldsession" "$turnsR/newsession"

# a flat file OVER the 5 MiB budget
dd if=/dev/zero of="$turnsR/$sidR.jsonl" bs=1048576 count=6 2>/dev/null
is "the oversized flat file really is over budget" \
  "$( [ "$(wc -c < "$turnsR/$sidR.jsonl" | tr -d ' ')" -gt 5242880 ] && echo yes || echo no )" "yes"

# a turn file from 2020 in another session's directory, and one from today
printf '{"kind":"step"}\n' > "$turnsR/oldsession/aaaa.jsonl"
printf '{"kind":"step"}\n' > "$turnsR/newsession/bbbb.jsonl"
# ... and THIS turn's own file, deliberately stamped old: it must survive anyway
printf '{"kind":"step"}\n' > "$turnsR/$sidR/$turnR.jsonl"
touch -t 202001010000 "$turnsR/oldsession/aaaa.jsonl" "$turnsR/oldsession" \
                      "$turnsR/$sidR/$turnR.jsonl" 2>/dev/null

sutra_ledger_init "$projR" "$sidR" "$turnR" "Stop"
sutra_ledger_note killswitch "a row, so the fresh flat file exists"

is "the oversized flat file rolled aside" \
  "$( [ -f "$turnsR/$sidR.jsonl.1" ] && echo yes || echo no )" "yes"
is "the roll-off is NOT visible to a *.jsonl glob under .sutra/turn" \
  "$(find "$turnsR" -maxdepth 1 -name '*.jsonl' | wc -l | tr -d ' ')" 1
is "the roll-off kept the bytes" \
  "$( [ "$(wc -c < "$turnsR/$sidR.jsonl.1" | tr -d ' ')" -gt 5242880 ] && echo yes || echo no )" "yes"
is "the flat file started fresh" \
  "$(grep -c . "$turnsR/$sidR.jsonl")" 1
is "the 31-day-old turn file is gone" \
  "$( [ -e "$turnsR/oldsession/aaaa.jsonl" ] && echo yes || echo no )" "no"
is "the directory it emptied is gone" \
  "$( [ -d "$turnsR/oldsession" ] && echo yes || echo no )" "no"
is "today's turn file survives" \
  "$( [ -f "$turnsR/newsession/bbbb.jsonl" ] && echo yes || echo no )" "yes"
is "THIS turn's own file is never pruned" \
  "$( [ -f "$turnsR/$sidR/$turnR.jsonl" ] && echo yes || echo no )" "yes"
is "the once-a-day marker was written" \
  "$( [ -f "$turnsR/.retention" ] && echo yes || echo no )" "yes"

# a second init in the same day must not walk the tree again: drop a fresh old
# file and show it survives because the marker is young.
printf '{"kind":"step"}\n' > "$turnsR/newsession/cccc.jsonl"
touch -t 202001010000 "$turnsR/newsession/cccc.jsonl" 2>/dev/null
sutra_ledger_init "$projR" "$sidR" "$turnR" "Stop"
is "the prune does not re-run within the day" \
  "$( [ -f "$turnsR/newsession/cccc.jsonl" ] && echo yes || echo no )" "yes"

printf 'test-ledger: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
