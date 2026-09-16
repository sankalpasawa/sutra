#!/bin/bash
# test-canary.sh - behaviour + budget test for bin/sutra-canary.
#
# WHAT IS ASSERTED.
#   1. 20 invocations, each with its own prompt_id, produce 20 distinct ledger
#      files holding EXACTLY ONE row each - a canary that double-writes or
#      collides on turn_id is not a heartbeat, it is noise.
#   2. Every row is valid JSON with kind=canary and a non-empty ts and event.
#   3. Each of the 20 calls finishes in under 200 ms of wall clock, measured as
#      the MINIMUM of three timings of that call. A single reading measures the
#      machine as much as the canary: under load - the parity suites running on
#      the same box - 3 of 20 single readings came in at 227 ms while all 11
#      functional asserts passed, i.e. the suite went red because something
#      else was busy. The minimum of three is the closest cheap estimate of the
#      canary's own cost; the median and worst of those minima are printed as a
#      metric line so a real regression is still visible in the numbers.
#   4. The canary emits nothing on stdout or stderr and exits 0.
#   5. The no-prompt_id path is DERIVED, not allocated. At UserPromptSubmit the
#      canary computes sha256(session_id + sha256(prompt key)) and publishes it
#      to .sutra/turn/<sid>/current; every later event of that turn reads the
#      file unmodified. Asserted three ways:
#        5a  UserPromptSubmit publishes `current`, and `current` is NOT a
#            *.jsonl file, so no reader that globs the ledger can see it;
#        5b  sutra-turn and the canary, given the same UserPromptSubmit stdin,
#            land in the SAME turn file - the correlation the heartbeat exists
#            for, which a shared counter destroys by handing the two programs
#            different numbers;
#        5c  8 PARALLEL PreToolUse calls after one UserPromptSubmit all land in
#            that one file (8 stage_digest rows in it, and exactly one *.jsonl
#            file in the session dir). Under the old counter this measured 5
#            files, 3 of them holding two merged turns.
#        5d  with no `current` published, the canary still writes exactly ONE
#            row and marks it "orphan":1 - a field, never a second row.
#   6. turn_id equals sha256(session_id + prompt_id) - byte-identical to the
#      value sutra-turn computes for the same turn.
#   7. With jq off the PATH the canary still routes the row correctly from
#      newline-free hook JSON, via the sed fallback.
#
# WHY THE CLOCK COMES FROM jq. macOS has no GNU date and bash 3.2 has no
# EPOCHREALTIME, so millisecond timing would otherwise need a dependency the
# runtime does not have. jq is already the runtime's one hard dependency, and
# `jq -n now` is sub-millisecond. The t1 reading is taken AFTER the canary
# returns, so its own start-up cost is charged to the measurement - the budget
# below is therefore conservative, never generous.
#
# bash 3.2 compatible: no associative arrays, no ${var^^}, no mapfile.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-canary.sh

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
CANARY="$PLUGIN_ROOT/bin/sutra-canary"
BUDGET_MS="${SUTRA_CANARY_BUDGET_MS:-200}"
CALLS=20

failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }

now_ms() { jq -n 'now*1000|floor'; }

sha_str() {
  # sha256 of a string with no trailing newline (matches the runtime's rule).
  printf '%s' "$1" | shasum -a 256 | sed -e 's/[[:space:]].*$//'
}

if [ ! -x "$CANARY" ]; then
  fail "sutra-canary missing or not executable at $CANARY"
  echo "failed=$failed"
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  fail "jq required to run this test"
  echo "failed=$failed"
  exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-canary-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
PROJ="$WORK/proj"
mkdir -p "$PROJ/.claude" "$PROJ/.sutra" "$PROJ/.enforcement"
SID="canary-test-session"
TURNDIR="$PROJ/.sutra/turn/$SID"

# ---------------------------------------------------- 1-4: 20 timed calls --
# One untimed warm-up first. The budget is a per-turn steady-state budget; the
# very first exec of a script on a cold page cache pays for loading sh, jq and
# openssl off disk (measured 564ms cold, ~35ms warm on the same machine), and
# charging that one-off to the canary would measure the filesystem, not the
# heartbeat. The warm-up writes into a throwaway session so it cannot be
# mistaken for one of the 20 rows.
printf '{"session_id":"warmup","prompt_id":"w0","hook_event_name":"SessionStart"}' > "$WORK/warm.json"
CLAUDE_PROJECT_DIR="$WORK/warm" "$CANARY" < "$WORK/warm.json" >/dev/null 2>&1

# MIN OF THREE, and only ONE of the three writes into $PROJ. The ledger asserts
# below want exactly one row per call, so reps 1 and 2 are timed against a
# throwaway project dir and rep 3 - the same program, the same stdin, the same
# work - is the one that lands in $PROJ. Every rep's exit, stdout and stderr is
# asserted; only the timing is reduced to a minimum.
TIMEPROJ="$WORK/timing"
mkdir -p "$TIMEPROJ/.claude" "$TIMEPROJ/.sutra" "$TIMEPROJ/.enforcement"

slow=0
worst=0
: > "$WORK/mins.txt"
i=1
while [ "$i" -le "$CALLS" ]; do
  printf '{"session_id":"%s","prompt_id":"p%s","hook_event_name":"PreToolUse","tool_name":"Edit"}' \
    "$SID" "$i" > "$WORK/in.json"
  best=""
  r=1
  while [ "$r" -le 3 ]; do
    if [ "$r" -eq 3 ]; then pd="$PROJ"; else pd="$TIMEPROJ"; fi
    t0="$(now_ms)"
    out="$(CLAUDE_PROJECT_DIR="$pd" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" \
           "$CANARY" < "$WORK/in.json" 2>"$WORK/err.$i")"
    rc=$?
    t1="$(now_ms)"
    el=$((t1 - t0))
    if [ -z "$best" ] || [ "$el" -lt "$best" ]; then best="$el"; fi
    [ "$rc" -eq 0 ] || fail "call #$i rep #$r exited $rc (want 0)"
    [ -z "$out" ] || fail "call #$i rep #$r wrote to stdout: $out"
    [ -s "$WORK/err.$i" ] && fail "call #$i rep #$r wrote to stderr: $(cat "$WORK/err.$i")"
    r=$((r + 1))
  done
  echo "$best" >> "$WORK/mins.txt"
  [ "$best" -gt "$worst" ] && worst="$best"
  [ "$best" -ge "$BUDGET_MS" ] && { slow=$((slow + 1)); echo "  slow call #$i: ${best}ms (min of 3)"; }
  i=$((i + 1))
done

median="$(sort -n "$WORK/mins.txt" | awk '{v[n++]=$1}
  END{ if (n == 0) print 0;
       else if (n % 2) print v[(n-1)/2];
       else print int((v[n/2-1] + v[n/2]) / 2) }')"
echo "metric: canary per-call min-of-3 — median ${median}ms worst ${worst}ms budget ${BUDGET_MS}ms (n=$CALLS)"

if [ "$slow" -eq 0 ]; then
  pass "$CALLS calls each under ${BUDGET_MS}ms (min of 3 per call; median ${median}ms, worst ${worst}ms)"
else
  fail "$slow/$CALLS calls at or over ${BUDGET_MS}ms even as a min of 3 (median ${median}ms, worst ${worst}ms)"
fi

files=$(ls -1 "$TURNDIR" 2>/dev/null | grep -c '\.jsonl$')
if [ "$files" -eq "$CALLS" ]; then
  pass "$CALLS calls produced $files distinct ledger files"
else
  fail "expected $CALLS ledger files, found $files in $TURNDIR"
fi

rows_total=0
bad_rows=0
for f in "$TURNDIR"/*.jsonl; do
  [ -f "$f" ] || continue
  n=$(grep -c . "$f")
  rows_total=$((rows_total + n))
  [ "$n" -eq 1 ] || { bad_rows=$((bad_rows + 1)); echo "  $f has $n rows"; }
  kind=$(jq -r '.kind // "?"' "$f" 2>/dev/null)
  ts=$(jq -r '.ts // 0' "$f" 2>/dev/null)
  ev=$(jq -r '.event // ""' "$f" 2>/dev/null)
  [ "$kind" = "canary" ] || { bad_rows=$((bad_rows + 1)); echo "  $f kind=$kind"; }
  [ "$ts" -gt 0 ] 2>/dev/null || { bad_rows=$((bad_rows + 1)); echo "  $f ts=$ts"; }
  [ "$ev" = "PreToolUse" ] || { bad_rows=$((bad_rows + 1)); echo "  $f event=$ev"; }
done

if [ "$rows_total" -eq "$CALLS" ] && [ "$bad_rows" -eq 0 ]; then
  pass "$rows_total rows total, one valid kind=canary row per call (ts + event present)"
else
  fail "rows_total=$rows_total (want $CALLS), malformed=$bad_rows"
fi

# ------------------------------------------------- 6: turn_id is the rule --
want="$(sha_str "${SID}p1")"
if [ -f "$TURNDIR/$want.jsonl" ]; then
  pass "turn_id = sha256(session_id + prompt_id)"
else
  fail "no ledger file at $want.jsonl - turn_id rule does not match sutra-turn"
fi

# ------------------------------- 5: no prompt_id -> the derived `current` key --
# Claude Code sends NO prompt_id on UserPromptSubmit, so this is the common
# path, not an edge case. It has to hold under concurrency, which means the key
# can never be allocated - only derived from bytes both programs already have.
#
# A throw-away plugin root gives sutra-turn a one-step pipeline, so this section
# measures turn IDENTITY and nothing else: no real governance hook runs.
TURN="$PLUGIN_ROOT/bin/sutra-turn"
FAKE="$WORK/fake"
mkdir -p "$FAKE/bin" "$FAKE/runtime" "$FAKE/hooks"
cp "$TURN" "$FAKE/bin/sutra-turn" 2>/dev/null
cp "$CANARY" "$FAKE/bin/sutra-canary" 2>/dev/null
chmod 0755 "$FAKE/bin/sutra-turn" "$FAKE/bin/sutra-canary" 2>/dev/null
cp "$PLUGIN_ROOT/runtime/shim.sh" "$PLUGIN_ROOT/runtime/ledger.sh" "$FAKE/runtime/" 2>/dev/null
printf '#!/bin/sh\ncat >/dev/null\nexit 0\n' > "$FAKE/hooks/quiet.sh"
chmod 0755 "$FAKE/hooks/quiet.sh"
cat > "$FAKE/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "UserPromptSubmit": [
      { "id": "ups.quiet", "matcher": "*", "class": "A",
        "impl": "shim:hooks/quiet.sh", "timeout_ms": 3000,
        "replaces": ["hooks/quiet.sh"] }
    ],
    "PreToolUse": [
      { "id": "pre.quiet", "matcher": "*", "class": "A",
        "impl": "shim:hooks/quiet.sh", "timeout_ms": 3000,
        "replaces": ["hooks/quiet.sh"] }
    ]
  }
}
PIPE

SID2="canary-test-derived"
PROJ2="$WORK/proj2"
HOME2="$WORK/home2"
TD2="$PROJ2/.sutra/turn/$SID2"
mkdir -p "$PROJ2/.claude" "$PROJ2/.sutra" "$PROJ2/.enforcement" "$HOME2"
PROMPT2="resume the runtime program"
printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","prompt":"%s"}' \
  "$SID2" "$PROMPT2" > "$WORK/ups.json"
printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"Edit"}' \
  "$SID2" > "$WORK/pre.json"

run2() { env CLAUDE_PLUGIN_ROOT="$FAKE" CLAUDE_PROJECT_DIR="$PROJ2" HOME="$HOME2" "$@"; }

run2 "$FAKE/bin/sutra-turn" run --event UserPromptSubmit < "$WORK/ups.json" >/dev/null 2>&1
run2 "$FAKE/bin/sutra-canary" < "$WORK/ups.json" >/dev/null 2>&1

# 5a. the key is published, and it is invisible to every *.jsonl reader.
want2="$(sha_str "${SID2}$(sha_str "$(jq -rn --arg p "$PROMPT2" '$p|@base64')")")"
cur2="$(cat "$TD2/current" 2>/dev/null)"
if [ "$cur2" = "$want2" ]; then
  pass "UserPromptSubmit publishes current = sha256(session_id + sha256(prompt key))"
else
  fail "current is '$cur2', expected '$want2'"
fi
case "$(ls -1 "$TD2" | grep -c '^current$')/$(ls -1 "$TD2" | grep '\.jsonl$' | grep -c '^current')" in
  1/0) pass "current is not a *.jsonl file (invisible to charcap and to this test's own globs)" ;;
  *)   fail "current is missing, or it is being counted as a ledger file" ;;
esac

# 5b. one file holds both programs' rows for the same prompt.
n2=$(ls -1 "$TD2" 2>/dev/null | grep -c '\.jsonl$')
f2="$TD2/$want2.jsonl"
c2=$(jq -s '[.[] | select(.kind=="canary")] | length' "$f2" 2>/dev/null)
s2=$(jq -s '[.[] | select(.kind=="stage_digest")] | length' "$f2" 2>/dev/null)
if [ "$n2" -eq 1 ] && [ "$c2" = "1" ] && [ "$s2" = "1" ]; then
  pass "canary row and sutra-turn rows share one turn file"
else
  fail "shared turn file: files=$n2 (want 1), canary rows=$c2 (want 1), digests=$s2 (want 1)"
fi

# 5c. eight PARALLEL PreToolUse calls, one file, eight digests.
i=1
while [ "$i" -le 8 ]; do
  run2 "$FAKE/bin/sutra-turn" run --event PreToolUse < "$WORK/pre.json" >/dev/null 2>&1 &
  i=$((i + 1))
done
wait
n3=$(ls -1 "$TD2" 2>/dev/null | grep -c '\.jsonl$')
s3=$(jq -s '[.[] | select(.kind=="stage_digest")] | length' "$f2" 2>/dev/null)
if [ "$n3" -eq 1 ] && [ "$s3" = "9" ]; then
  pass "8 parallel PreToolUse calls stayed in the one turn file (9 stage_digest rows)"
else
  fail "parallel turn identity: files=$n3 (want 1), stage_digest rows=$s3 (want 9)"
fi

# 5d. no `current` published -> one row, marked orphan.
SID3="canary-test-orphan"
TD3="$PROJ2/.sutra/turn/$SID3"
printf '{"session_id":"%s","hook_event_name":"Stop"}' "$SID3" > "$WORK/orphan.json"
run2 "$FAKE/bin/sutra-canary" < "$WORK/orphan.json" >/dev/null 2>&1
o_files=$(ls -1 "$TD3" 2>/dev/null | grep -c '\.jsonl$')
o_rows=0
o_orphan=0
for f in $(find "$TD3" -name '*.jsonl' 2>/dev/null); do
  o_rows=$((o_rows + $(grep -c . "$f")))
  o_orphan=$((o_orphan + $(jq -s '[.[] | select(.kind=="canary" and .orphan==1)] | length' "$f" 2>/dev/null)))
done
if [ "$o_files" -eq 1 ] && [ "$o_rows" -eq 1 ] && [ "$o_orphan" -eq 1 ]; then
  pass "orphan event writes ONE canary row carrying orphan:1"
else
  fail "orphan path: files=$o_files rows=$o_rows orphan-marked=$o_orphan (want 1/1/1)"
fi

# 5e. and the counter is gone: nothing writes a .seq file any more.
if [ -z "$(find "$PROJ2/.sutra/turn" -name '*.seq' 2>/dev/null)" ] \
   && [ -z "$(find "$PROJ/.sutra/turn" -name '*.seq' 2>/dev/null)" ]; then
  pass "no .seq counter file is written by either program"
else
  fail ".seq counter still in use: $(find "$PROJ2/.sutra/turn" "$PROJ/.sutra/turn" -name '*.seq' 2>/dev/null | tr '\n' ' ')"
fi

# ------------------------------------ 7: degraded path, jq off the PATH ----
# The canary is a heartbeat: it has to keep beating on the exact install where
# jq is missing, because that is one of the installs the heartbeat exists to
# report. The fallback parses the hook JSON with sed, and the host's JSON
# arrives with NO trailing newline - the case that once collapsed all four
# fields onto one line and silently rerouted every row to the wrong session.
NOJQ_PATH="$(dirname "$(command -v sed)"):$(dirname "$(command -v cat)")"
if command -v jq >/dev/null 2>&1 && env PATH="$NOJQ_PATH" sh -c 'command -v jq' >/dev/null 2>&1; then
  echo "skip: cannot build a jq-less PATH on this machine"
else
  SID3="canary-test-nojq"
  # printf with no trailing newline on purpose: that is the host's shape.
  printf '{"session_id":"%s","prompt_id":"p-nojq","hook_event_name":"Stop","tool_name":"Bash"}' \
    "$SID3" > "$WORK/in3.json"
  out3="$(env PATH="$NOJQ_PATH" CLAUDE_PROJECT_DIR="$PROJ" "$CANARY" < "$WORK/in3.json" 2>&1)"
  rc3=$?
  want3="$(sha_str "${SID3}p-nojq")"
  if [ "$rc3" -eq 0 ] && [ -z "$out3" ] && [ -f "$PROJ/.sutra/turn/$SID3/$want3.jsonl" ] \
     && [ "$(jq -r '.event' "$PROJ/.sutra/turn/$SID3/$want3.jsonl")" = "Stop" ]; then
    pass "jq-less fallback parses newline-free hook JSON (session + prompt_id + event)"
  else
    fail "jq-less fallback: rc=$rc3 out='$out3' expected row $SID3/$want3.jsonl"
    ls -1 "$PROJ/.sutra/turn/$SID3" 2>/dev/null | sed 's/^/    have: /'
  fi
fi

# ------------ 8: a canary row survives charcap's timestamp normalisation ----
# The canary appends into the SAME canonical turn file sutra-turn writes, and
# bin/sutra-charcap normalises a recorded turn with
#   sed -E 's%[0-9]{13}%<TS>%g; s%[0-9]{10}%<TS>%g'
# before comparing it. runtime/ledger.sh quotes ts for exactly that reason; the
# canary printed it bare, so one canary row turned `"ts":1757800000` into
# `"ts":<TS>` and made the whole normalised file unparseable - taking every
# sutra-turn row in the file down with it.
SID4="canary-test-normalise"
printf '{"session_id":"%s","prompt_id":"p-norm","hook_event_name":"Stop","tool_name":"Bash"}' \
  "$SID4" > "$WORK/in4.json"
CLAUDE_PROJECT_DIR="$PROJ" "$CANARY" < "$WORK/in4.json" >/dev/null 2>&1
TURN4="$(sha_str "${SID4}p-norm")"
ROW4="$PROJ/.sutra/turn/$SID4/$TURN4.jsonl"
# a ledger-shaped sutra-turn row in the same file, so the assert covers both
printf '{"kind":"step","turn_id":"%s","step_id":"stop.probe","exit":0,"dur_ms":12,"ts":"%s","event":"Stop"}\n' \
  "$TURN4" "$(date +%s)" >> "$ROW4"
if [ -f "$ROW4" ]; then
  norm4="$WORK/norm4.jsonl"
  sed -E 's%[0-9]{13}%<TS>%g; s%[0-9]{10}%<TS>%g' "$ROW4" > "$norm4"
  bad4=0
  while IFS= read -r l4; do
    [ -n "$l4" ] || continue
    printf '%s' "$l4" | jq -e . >/dev/null 2>&1 || bad4=$((bad4 + 1))
  done < "$norm4"
  n4="$(wc -l < "$norm4" | tr -d ' ')"
  if [ "$bad4" -eq 0 ] && [ "$n4" -eq 2 ]; then
    pass "a canary row still parses after charcap's <TS> normalisation ($n4 rows)"
  else
    fail "normalised turn file has $bad4 unparseable row(s) of $n4"
    sed -n '1,4p' "$norm4" | sed 's/^/    /'
  fi
else
  fail "normalisation case: no canary row at $ROW4"
fi

echo "failed=$failed"
[ "$failed" -eq 0 ]
