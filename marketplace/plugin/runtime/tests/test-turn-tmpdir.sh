#!/usr/bin/env bash
# test-turn-tmpdir.sh - three things sutra-turn must never do to the machine it
# runs on, each one a measured defect rather than a hypothetical.
#
#   1 IT MUST NEVER DELETE A DIRECTORY IT DID NOT CREATE. The old code did
#     `mkdir -p "$TMPDIR/sutra-turn-$$" || TMPROOT="$TMPDIR"` and then
#     `trap 'rm -rf "$TMPROOT"' EXIT`. Whenever the per-run subdir could not be
#     created - TMPDIR is a regular file, read-only, full, or the name is taken
#     - the fallback adopted the SHARED temp root and the exit trap deleted it,
#     taking every other process's temp state with it. Demonstrated: a file
#     under TMPDIR was gone after one PostToolUse call. The runtime now owns its
#     directory or it has none, says so, and runs the legacy hooks.
#
#   2 session_id IS A PATH COMPONENT. It arrives from the host's JSON and is
#     used for the ledger directory, the flat parity file and the `current`
#     pointer. "../../escape" wrote $CLAUDE_PROJECT_DIR/escape and escape.jsonl
#     - outside .sutra entirely. It is sanitised once, before any path is built,
#     and bin/sutra-canary applies the identical rule so the two programs agree
#     on where the pointer and the rows live.
#
#   3 AN UNKNOWN EVENT IS NOT A CLEAN TURN. `run --event Bogus` selected zero
#     steps, emitted nothing and exited 0, so a mis-registration was
#     indistinguishable from a quiet turn. It now prints a degraded line and
#     records a ledger row - still exit 0, because an unknown event must never
#     block the host.
#
# bash 3.2 + jq. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-turn-tmpdir.sh

set -u

here="$(cd "$(dirname "$0")" && pwd -P)"
runtime="$(cd "$here/.." && pwd -P)"
plugin="$(cd "$runtime/.." && pwd -P)"
turn="$plugin/bin/sutra-turn"
canary="$plugin/bin/sutra-canary"

checks=0
failed=0
ok()   { checks=$((checks+1)); }
fail() { checks=$((checks+1)); failed=$((failed+1)); printf 'FAIL %s\n' "$*" >&2; }
is()   { if [ "$2" = "$3" ]; then ok; else fail "$1: expected [$3] got [$2]"; fi; }

command -v jq >/dev/null 2>&1 || { printf 'test-turn-tmpdir: jq required\nfailed=1\n'; exit 1; }
[ -x "$turn" ] || { printf 'test-turn-tmpdir: %s not executable\nfailed=1\n' "$turn"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-tmpdir.XXXXXX")"
cleanup() {
  chmod 0755 "$tmp/rodir" "$tmp/rodir2" 2>/dev/null || true
  rm -rf "$tmp"
}
trap cleanup EXIT

# ------------------------------------------------------- throw-away plugin --
fake="$tmp/plugin"
mkdir -p "$fake/bin" "$fake/runtime" "$fake/hooks"
cp "$turn" "$fake/bin/sutra-turn"; chmod 0755 "$fake/bin/sutra-turn"
[ -x "$canary" ] && { cp "$canary" "$fake/bin/sutra-canary"; chmod 0755 "$fake/bin/sutra-canary"; }
cp "$runtime/shim.sh" "$runtime/ledger.sh" "$fake/runtime/"
[ -f "$runtime/selftest.sh" ] && cp "$runtime/selftest.sh" "$fake/runtime/"

cat > "$fake/hooks/legacy-one.sh" <<'L1'
#!/bin/sh
cat >/dev/null
printf 'LEGACY-ONE\n'
L1
cat > "$fake/hooks/probe.sh" <<'PB'
#!/bin/sh
cat >/dev/null
printf 'RUNTIME-PROBE\n'
PB
cat > "$fake/hooks/slow.sh" <<'SL'
#!/bin/sh
cat >/dev/null
sleep 3
printf 'SLOW-FINISHED\n'
SL
chmod 0755 "$fake/hooks/legacy-one.sh" "$fake/hooks/probe.sh" "$fake/hooks/slow.sh"

cat > "$fake/hooks/hooks.json.step3" <<'REG3'
{
  "hooks": {
    "PostToolUse": [
      {"matcher":"*","hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/legacy-one.sh"}]}
    ]
  }
}
REG3

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "matcher_semantics": "anchored-ere",
  "events": {
    "PostToolUse": [
      {"id":"post.probe","matcher":"*","class":"A","impl":"shim:hooks/probe.sh","timeout_ms":5000}
    ],
    "UserPromptSubmit": [
      {"id":"ups.probe","matcher":"*","class":"A","impl":"shim:hooks/probe.sh","timeout_ms":5000}
    ],
    "PreToolUse": [
      {"id":"pre.slow","matcher":"*","class":"B","impl":"shim:hooks/slow.sh","timeout_ms":300}
    ],
    "Stop": [
      {"id":"stop.slow","matcher":"*","class":"A","impl":"shim:hooks/slow.sh","timeout_ms":60000}
    ]
  }
}
PIPE

home="$tmp/home"; mkdir -p "$home"

# turnrun <name> <event> <project> [env assignments...] - stdin comes from
# $tmp/<name>.json; stdout/stderr land in $tmp/<name>.out / .err; rc in $rc.
turnrun() {
  _tr_n="$1"; _tr_e="$2"; _tr_p="$3"; shift 3
  mkdir -p "$_tr_p/.claude" "$_tr_p/.sutra" "$_tr_p/.enforcement"
  env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$_tr_p" HOME="$home" "$@" \
    "$fake/bin/sutra-turn" run --event "$_tr_e" \
    < "$tmp/$_tr_n.json" > "$tmp/$_tr_n.out" 2> "$tmp/$_tr_n.err"
  rc=$?
}

# ===================== 1. a temp root this process did not create is not ours --
printf '{"session_id":"t-file","hook_event_name":"PostToolUse","tool_name":"Bash"}' > "$tmp/tfile.json"
printf 'precious' > "$tmp/not-a-dir"
turnrun tfile PostToolUse "$tmp/proj-tfile" TMPDIR="$tmp/not-a-dir"
is "TMPDIR-is-a-file exit" "$rc" 0
is "TMPDIR-is-a-file did not delete it" "$(cat "$tmp/not-a-dir" 2>/dev/null)" "precious"
# The notice is the RUNTIME's own, so it goes to fd 2: stdout belongs to the
# host and a line of ours in front of a legacy hook's JSON would make the whole
# stream unparseable, which is how a directive gets silently lost.
is "TMPDIR-is-a-file says so on fd 2" "$(head -1 "$tmp/tfile.err")" \
  "sutra runtime degraded: no temp dir"
is "TMPDIR-is-a-file keeps stdout for the hooks" \
  "$(grep -c 'sutra runtime degraded' "$tmp/tfile.out" 2>/dev/null || true)" 0
is "TMPDIR-is-a-file still ran the legacy hook" \
  "$(grep -c 'LEGACY-ONE' "$tmp/tfile.out" 2>/dev/null || true)" 1
is "TMPDIR-is-a-file recorded a ledger row" \
  "$(jq -s '[.[]|select(.kind=="no_tmpdir")]|length' "$tmp/proj-tfile/.sutra/turn/t-file.jsonl" 2>/dev/null)" 1

# a READ-ONLY TMPDIR: the directory survives and stays empty
printf '{"session_id":"t-ro","hook_event_name":"PostToolUse","tool_name":"Bash"}' > "$tmp/tro.json"
mkdir -p "$tmp/rodir"; printf 'keep' > "$tmp/rodir/keepme"; chmod 0555 "$tmp/rodir"
turnrun tro PostToolUse "$tmp/proj-tro" TMPDIR="$tmp/rodir"
is "read-only TMPDIR exit" "$rc" 0
is "read-only TMPDIR survives" "$(cat "$tmp/rodir/keepme" 2>/dev/null)" "keep"
is "read-only TMPDIR says so on fd 2" "$(head -1 "$tmp/tro.err")" \
  "sutra runtime degraded: no temp dir"
is "read-only TMPDIR still ran the legacy hook" \
  "$(grep -c 'LEGACY-ONE' "$tmp/tro.out" 2>/dev/null || true)" 1
chmod 0755 "$tmp/rodir"

# a NORMAL run: the runtime path, and not one sutra-turn-* directory left over
printf '{"session_id":"t-ok","hook_event_name":"PostToolUse","tool_name":"Bash"}' > "$tmp/tok.json"
mkdir -p "$tmp/tmpclean"
turnrun tok PostToolUse "$tmp/proj-tok" TMPDIR="$tmp/tmpclean"
is "normal-TMPDIR exit" "$rc" 0
is "normal-TMPDIR took the runtime path" \
  "$(grep -c 'RUNTIME-PROBE' "$tmp/tok.out" 2>/dev/null || true)" 1
is "normal-TMPDIR leaves no sutra-turn-* directory behind" \
  "$(find "$tmp/tmpclean" -maxdepth 1 -name 'sutra-turn-*' | wc -l | tr -d ' ')" 0
is "normal-TMPDIR wrote no no_tmpdir row" \
  "$(jq -s '[.[]|select(.kind=="no_tmpdir")]|length' "$tmp/proj-tok/.sutra/turn/t-ok.jsonl" 2>/dev/null)" 0

# ================================ 2. session_id can never escape .sutra/turn --
printf '{"session_id":"../../escape","hook_event_name":"PostToolUse","tool_name":"Bash"}' > "$tmp/esc.json"
proj="$tmp/proj-esc"
turnrun esc PostToolUse "$proj"
is "escaping session_id exit" "$rc" 0
is "nothing was written beside .sutra" \
  "$(find "$proj" -maxdepth 1 -name 'escape*' | wc -l | tr -d ' ')" 0
is "nothing was written above the project" \
  "$(find "$tmp" -maxdepth 1 -name 'escape*' | wc -l | tr -d ' ')" 0
is "the rows landed under .sutra/turn" \
  "$(find "$proj/.sutra/turn" -name '*.jsonl' | wc -l | tr -d ' ')" 2

# ... and both programs agree on the sanitised directory, including the pointer
if [ -x "$fake/bin/sutra-canary" ]; then
  printf '{"session_id":"a/b","hook_event_name":"UserPromptSubmit","prompt":"hi"}' > "$tmp/ab.json"
  proj2="$tmp/proj-ab"; mkdir -p "$proj2/.claude" "$proj2/.sutra"
  env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$proj2" HOME="$home" \
    "$fake/bin/sutra-canary" < "$tmp/ab.json" >/dev/null 2>&1
  turnrun ab UserPromptSubmit "$proj2"
  is "a slashed session_id creates exactly one ledger directory" \
    "$(find "$proj2/.sutra/turn" -type d -mindepth 1 | wc -l | tr -d ' ')" 1
  is "and it is the sanitised name both programs compute" \
    "$(basename "$(find "$proj2/.sutra/turn" -type d -mindepth 1 | head -1)")" "ab"
  is "the current pointer lives in that same directory" \
    "$(find "$proj2/.sutra/turn" -name current | wc -l | tr -d ' ')" 1
  is "the canary row and the turn rows share one file" \
    "$(find "$proj2/.sutra/turn/ab" -name '*.jsonl' | wc -l | tr -d ' ')" 1
  is "that file holds both a canary row and sutra-turn rows" \
    "$(jq -s '[([.[]|select(.kind=="canary")]|length > 0),([.[]|select(.kind=="step" or .kind=="emit")]|length > 0)]|all' \
       "$(find "$proj2/.sutra/turn/ab" -name '*.jsonl' | head -1)" 2>/dev/null)" "true"
else
  fail "bin/sutra-canary is not executable; the shared-path case could not run"
fi

# ============================ 3. an unknown event is reported, never silent --
printf '{"session_id":"t-bogus","hook_event_name":"Bogus","tool_name":"Bash"}' > "$tmp/bogus.json"
turnrun bogus Bogus "$tmp/proj-bogus"
is "unknown-event exit" "$rc" 0
is "unknown-event says which event, on fd 2" "$(head -1 "$tmp/bogus.err")" \
  "sutra runtime degraded: no pipeline entry for event Bogus"
is "unknown-event recorded a ledger row" \
  "$(jq -s '[.[]|select(.kind=="unknown_event")]|length' "$tmp/proj-bogus/.sutra/turn/t-bogus.jsonl" 2>/dev/null)" 1
is "unknown-event ran no pipeline step" \
  "$(jq -s '[.[]|select(.kind=="step")]|length' "$tmp/proj-bogus/.sutra/turn/t-bogus.jsonl" 2>/dev/null)" 0

# ... AND IT STILL RUNS THE REGISTRY. This was the one degraded path with no
# legacy fallback: if the host really is firing an event the pipeline has not
# specified, the registry may still carry hooks for it and dropping them is the
# silent loss of governance every other degraded path exists to avoid.
cp "$fake/hooks/hooks.json.step3" "$tmp/step3.saved-bogus"
cat > "$fake/hooks/hooks.json.step3" <<'REGB'
{
  "hooks": {
    "Bogus": [
      {"matcher":"*","hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/legacy-one.sh"}]}
    ]
  }
}
REGB
printf '{"session_id":"t-bogus2","hook_event_name":"Bogus","tool_name":"Bash"}' > "$tmp/bogus2.json"
turnrun bogus2 Bogus "$tmp/proj-bogus2"
cp "$tmp/step3.saved-bogus" "$fake/hooks/hooks.json.step3"
is "unknown-event with a registration exits 0" "$rc" 0
is "unknown-event ran the legacy registration" \
  "$(cat "$tmp/bogus2.out")" "LEGACY-ONE"
is "unknown-event still recorded its row" \
  "$(jq -s '[.[]|select(.kind=="unknown_event")]|length' "$tmp/proj-bogus2/.sutra/turn/t-bogus2.jsonl" 2>/dev/null)" 1

# ================= 4. `run --event` WITH NO VALUE must not hang the host call --
# `--event) EV="${2:-}"; shift 2` looks safe and is not: with one argument left,
# POSIX `shift 2` shifts NOTHING, so the loop re-reads "--event" for ever and
# the hook call never returns. The whole case is therefore run under an alarm:
# a hang is a FAILED check, not a test that never finishes.
noval_rc=""
( env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-noval" HOME="$home" \
    "$fake/bin/sutra-turn" run --event </dev/null \
    > "$tmp/noval.out" 2> "$tmp/noval.err" ) &
noval_pid=$!
spin=0
while kill -0 "$noval_pid" 2>/dev/null && [ "$spin" -lt 50 ]; do
  sleep 0.1; spin=$((spin+1))
done
if kill -0 "$noval_pid" 2>/dev/null; then
  kill -9 "$noval_pid" 2>/dev/null
  fail "run --event with no value hung (still running after 5s)"
else
  wait "$noval_pid"; noval_rc=$?
  is "run --event with no value exits 1" "$noval_rc" 1
  is "run --event with no value says which option" "$(head -1 "$tmp/noval.err")" \
    "sutra-turn: --event needs a value"
fi

# ============ 5. a legacy registry that matches no tool is NOT a broken registry --
# The fallback used to count only the registrations it EXECUTED, so a kill-switched
# PostToolUse call on Bash - against a registry whose only registration matches
# Edit - printed "legacy registry missing" and wrote the row that says the
# package is broken. Read and runnable are what make a registry sound; matching
# is about this one tool.
cp "$fake/hooks/hooks.json.step3" "$tmp/step3.saved"
cat > "$fake/hooks/hooks.json.step3" <<'REGE'
{
  "hooks": {
    "PostToolUse": [
      {"matcher":"Edit","hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/legacy-one.sh"}]}
    ]
  }
}
REGE
kshome="$tmp/home-ks"; mkdir -p "$kshome"; : > "$kshome/.sutra-runtime-disabled"

printf '{"session_id":"t-nomatch","hook_event_name":"PostToolUse","tool_name":"Bash"}' > "$tmp/nomatch.json"
mkdir -p "$tmp/proj-nomatch/.claude" "$tmp/proj-nomatch/.sutra" "$tmp/proj-nomatch/.enforcement"
env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-nomatch" HOME="$kshome" \
  "$fake/bin/sutra-turn" run --event PostToolUse \
  < "$tmp/nomatch.json" > "$tmp/nomatch.out" 2> "$tmp/nomatch.err"
rc=$?
nomatch_led="$tmp/proj-nomatch/.sutra/turn/t-nomatch.jsonl"
is "kill-switched no-match exit" "$rc" 0
is "kill-switched no-match says nothing on stdout" \
  "$(wc -c < "$tmp/nomatch.out" | tr -d ' ')" 0
is "kill-switched no-match wrote no legacy_registry_missing row" \
  "$(jq -s '[.[]|select(.kind=="legacy_registry_missing")]|length' "$nomatch_led" 2>/dev/null)" 0
is "kill-switched no-match wrote one no_match row" \
  "$(jq -s '[.[]|select(.kind=="no_match")]|length' "$nomatch_led" 2>/dev/null)" 1
is "the no_match row names the tool" \
  "$(jq -sr '[.[]|select(.kind=="no_match")][0].note | test("none matched tool Bash")' "$nomatch_led" 2>/dev/null)" "true"

# the same on the NO-TEMP-DIR path, which reaches legacy_run by its own route
printf '{"session_id":"t-nomatch2","hook_event_name":"PostToolUse","tool_name":"Bash"}' > "$tmp/nomatch2.json"
mkdir -p "$tmp/proj-nomatch2/.claude" "$tmp/proj-nomatch2/.sutra" "$tmp/proj-nomatch2/.enforcement"
env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-nomatch2" HOME="$home" \
  TMPDIR="$tmp/not-a-dir" \
  "$fake/bin/sutra-turn" run --event PostToolUse \
  < "$tmp/nomatch2.json" > "$tmp/nomatch2.out" 2> "$tmp/nomatch2.err"
rc=$?
nomatch2_led="$tmp/proj-nomatch2/.sutra/turn/t-nomatch2.jsonl"
is "no-tmpdir no-match exit" "$rc" 0
is "no-tmpdir no-match says nothing on stdout" \
  "$(wc -c < "$tmp/nomatch2.out" | tr -d ' ')" 0
is "no-tmpdir no-match says only the temp-dir line, on fd 2" \
  "$(cat "$tmp/nomatch2.err")" "sutra runtime degraded: no temp dir"
is "no-tmpdir no-match wrote no legacy_registry_missing row" \
  "$(jq -s '[.[]|select(.kind=="legacy_registry_missing")]|length' "$nomatch2_led" 2>/dev/null)" 0
is "no-tmpdir no-match wrote one no_match row" \
  "$(jq -s '[.[]|select(.kind=="no_match")]|length' "$nomatch2_led" 2>/dev/null)" 1
cp "$tmp/step3.saved" "$fake/hooks/hooks.json.step3"

# ================================ 6. a KILLED step is named, never swallowed --
# `[ "$S_RC" = "124" ] && continue` dropped the step in silence: the governance
# gate did not run and the turn looked clean. It now names the step and the
# budget on fd 2, and - class B, output the host acts on - carries the same
# sentence into the emission as a systemMessage.
printf '{"session_id":"t-slow","hook_event_name":"PreToolUse","tool_name":"Edit"}' > "$tmp/slow.json"
mkdir -p "$tmp/tmpdebris"
turnrun slow PreToolUse "$tmp/proj-slow" TMPDIR="$tmp/tmpdebris"
is "timed-out step exit" "$rc" 0
is "timed-out step never finished" \
  "$(grep -c 'SLOW-FINISHED' "$tmp/slow.out" 2>/dev/null || true)" 0
is "timed-out step is named on fd 2 with its budget" \
  "$(grep -c '^sutra runtime degraded: step pre.slow exceeded 300ms$' "$tmp/slow.err" 2>/dev/null || true)" 1
is "a class B timeout reaches the transcript as a systemMessage" \
  "$(jq -r '.systemMessage // ""' "$tmp/slow.out" 2>/dev/null)" \
  "sutra runtime degraded: step pre.slow exceeded 300ms"
is "the ledger recorded the kill as exit 124" \
  "$(jq -s '[.[]|select(.kind=="step" and .exit==124)]|length' "$tmp/proj-slow/.sutra/turn/t-slow.jsonl" 2>/dev/null)" 1

# =========================== 7. no scratch file survives outside the temp root --
# The watchdog flag, the digest accumulator and the sha256 scratch were built in
# $TMPDIR itself - outside TMPROOT and outside the cleanup trap - so a killed run
# left them behind for ever.
debris() {
  find "$1" \( -name 'sutra-shim-to-*' -o -name 'sutra-digest-*' -o -name 'sutra-sha-*' \) \
    2>/dev/null | wc -l | tr -d ' '
}
is "a timed-out run leaves no scratch file in TMPDIR" "$(debris "$tmp/tmpdebris")" 0

mkdir -p "$tmp/tmpkill"
printf '{"session_id":"t-kill","hook_event_name":"PreToolUse","tool_name":"Edit"}' > "$tmp/kill.json"
mkdir -p "$tmp/proj-kill/.claude" "$tmp/proj-kill/.sutra" "$tmp/proj-kill/.enforcement"
( env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-kill" HOME="$home" \
    TMPDIR="$tmp/tmpkill" \
    "$fake/bin/sutra-turn" run --event PreToolUse \
    < "$tmp/kill.json" > "$tmp/kill.out" 2> "$tmp/kill.err" ) &
kill_pid=$!
sleep 0.6
kill -TERM "$kill_pid" 2>/dev/null
wait "$kill_pid" 2>/dev/null
is "a TERM-killed run leaves no scratch file in TMPDIR" "$(debris "$tmp/tmpkill")" 0

# A SIGNAL MUST END THE PROCESS, NOT RESUME IT. `trap cleanup EXIT HUP INT TERM
# ALRM QUIT` with a handler ending in `return 0` is a POSIX trap that RESUMES
# the script at the interrupted line: TMPROOT was deleted and the run walked on,
# reading files that no longer existed, and still closed the turn with a stage
# digest - a falsely clean turn made out of an interrupted one.
#
# The TERM must land while a step is genuinely in flight, so this uses the Stop
# registration (sleep 3 on a 60 s budget) rather than the 300 ms PreToolUse one,
# which is already over by the time a 0.6 s sleep returns.
mkdir -p "$tmp/tmpterm"
printf '{"session_id":"t-term","hook_event_name":"Stop"}' > "$tmp/term.json"
mkdir -p "$tmp/proj-term/.claude" "$tmp/proj-term/.sutra" "$tmp/proj-term/.enforcement"
( env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-term" HOME="$home" \
    TMPDIR="$tmp/tmpterm" \
    "$fake/bin/sutra-turn" run --event Stop \
    < "$tmp/term.json" > "$tmp/term.out" 2> "$tmp/term.err" ) &
term_pid=$!
sleep 0.8
kill -TERM "$term_pid" 2>/dev/null
wait "$term_pid" 2>/dev/null
term_rc=$?
if [ "${term_rc:-0}" -ne 0 ]; then ok; else
  fail "a run TERMed mid-step exited 0 (the signal trap resumed the script)"; fi
term_led="$tmp/proj-term/.sutra/turn/t-term.jsonl"
if [ -f "$term_led" ]; then
  is "a run TERMed mid-step writes no stage digest" \
    "$(jq -s '[.[]|select(.kind=="stage_digest")]|length' "$term_led" 2>/dev/null)" 0
else
  ok   # killed before the ledger was opened at all: also no digest
fi
is "a run TERMed mid-step leaves no temp directory behind" \
  "$(find "$tmp/tmpterm" -maxdepth 1 -name 'sutra-turn-*' 2>/dev/null | wc -l | tr -d ' ')" 0
is "the step it was running did not finish" \
  "$(grep -c 'SLOW-FINISHED' "$tmp/term.out" 2>/dev/null || true)" 0
is "a TERM-killed run leaves no temp directory in TMPDIR" \
  "$(find "$tmp/tmpkill" -maxdepth 1 -name 'sutra-turn-*' 2>/dev/null | wc -l | tr -d ' ')" 0

# SIGKILL runs no trap at all, which is the case that made the placement matter:
# whatever the run had already created is what stays on the disk for ever. A
# scratch file built in $TMPDIR is then orphaned in the SHARED root; built inside
# the run's own directory it is at least gathered in one removable place. So the
# assertion is two-sided - the digest accumulator must EXIST (the probe caught
# the run mid-flight) and must NOT be sitting directly in TMPDIR.
mkdir -p "$tmp/tmpkill9"
printf '{"session_id":"t-kill9","hook_event_name":"Stop"}' > "$tmp/kill9.json"
mkdir -p "$tmp/proj-kill9/.claude" "$tmp/proj-kill9/.sutra" "$tmp/proj-kill9/.enforcement"
( env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-kill9" HOME="$home" \
    TMPDIR="$tmp/tmpkill9" \
    "$fake/bin/sutra-turn" run --event Stop \
    < "$tmp/kill9.json" > "$tmp/kill9.out" 2> "$tmp/kill9.err" ) &
kill9_pid=$!
sleep 0.8
deep9="$(find "$tmp/tmpkill9" -name 'sutra-digest-*' 2>/dev/null | wc -l | tr -d ' ')"
flat9="$(find "$tmp/tmpkill9" -maxdepth 1 \
          \( -name 'sutra-shim-to-*' -o -name 'sutra-digest-*' -o -name 'sutra-sha-*' \) \
          2>/dev/null | wc -l | tr -d ' ')"
kill -9 "$kill9_pid" 2>/dev/null
wait "$kill9_pid" 2>/dev/null
if [ "$deep9" -ge 1 ]; then ok; else
  fail "the mid-flight probe found no digest accumulator at all (test is blind)"; fi
is "a SIGKILLed run orphans nothing directly in TMPDIR" "$flat9" 0

# ===== 8. an unusable TMPDIR adds NOTHING BUT ITS OWN LINE to the streams --
# The degraded path says ONE fixed line on stdout and runs the legacy hooks.
# runtime/ledger.sh then built the digest accumulator under the SAME unusable
# TMPDIR with `: > "$ACC" 2>/dev/null`, and a redirection that fails is reported
# by the shell BEFORE the `2>` on that simple command is in force - so every
# degraded turn leaked "ledger.sh: line 193: <TMPDIR>/sutra-digest-<pid>-...:
# Not a directory" to fd 2. Exit code and stdout were correct, which is exactly
# why nothing caught it: on Stop and PreToolUse the host shows stderr to the
# user. The assertions are therefore byte comparisons on fd 2, not greps.
noise_line="sutra runtime degraded: no temp dir"

# A PreToolUse registration that says nothing at all, so the ONLY output either
# stream can carry is the runtime's own. (Without one the fallback correctly
# reports a registry with no PreToolUse entry, which is a different case -
# section 5 covers it.)
cat > "$fake/hooks/legacy-quiet.sh" <<'LQ'
#!/bin/sh
cat >/dev/null
exit 0
LQ
chmod 0755 "$fake/hooks/legacy-quiet.sh"
cp "$fake/hooks/hooks.json.step3" "$tmp/step3.saved8q"
cat > "$fake/hooks/hooks.json.step3" <<'REGQ'
{
  "hooks": {
    "PreToolUse": [
      {"matcher":"*","hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/legacy-quiet.sh"}]}
    ]
  }
}
REGQ

printf '{"session_id":"t-q1","hook_event_name":"PreToolUse","tool_name":"Read"}' > "$tmp/q1.json"
turnrun q1 PreToolUse "$tmp/proj-q1" TMPDIR="$tmp/not-a-dir"
is "file-shaped TMPDIR exit" "$rc" 0
is "file-shaped TMPDIR leaves stdout empty for the hooks" \
  "$(wc -c < "$tmp/q1.out" | tr -d ' ')" 0
is "file-shaped TMPDIR stderr is exactly the degraded line" "$(cat "$tmp/q1.err")" "$noise_line"
is "file-shaped TMPDIR adds no shell noise of its own" \
  "$(wc -c < "$tmp/q1.err" | tr -d ' ')" "$(( ${#noise_line} + 1 ))"
is "file-shaped TMPDIR still recorded the no_tmpdir row" \
  "$(jq -s '[.[]|select(.kind=="no_tmpdir")]|length' "$tmp/proj-q1/.sutra/turn/t-q1.jsonl" 2>/dev/null)" 1

mkdir -p "$tmp/rodir2"; chmod 0500 "$tmp/rodir2"
printf '{"session_id":"t-q2","hook_event_name":"PreToolUse","tool_name":"Read"}' > "$tmp/q2.json"
turnrun q2 PreToolUse "$tmp/proj-q2" TMPDIR="$tmp/rodir2"
chmod 0755 "$tmp/rodir2"
is "read-only TMPDIR exit" "$rc" 0
is "read-only TMPDIR leaves stdout empty for the hooks" \
  "$(wc -c < "$tmp/q2.out" | tr -d ' ')" 0
is "read-only TMPDIR stderr is exactly the degraded line" "$(cat "$tmp/q2.err")" "$noise_line"
is "read-only TMPDIR adds no shell noise of its own" \
  "$(wc -c < "$tmp/q2.err" | tr -d ' ')" "$(( ${#noise_line} + 1 ))"
is "read-only TMPDIR still recorded the no_tmpdir row" \
  "$(jq -s '[.[]|select(.kind=="no_tmpdir")]|length' "$tmp/proj-q2/.sutra/turn/t-q2.jsonl" 2>/dev/null)" 1

# ... and a legacy hook that DOES write to fd 2 must come through untouched:
# the runtime neither adds a line of its own nor swallows the hook's.
cat > "$fake/hooks/legacy-noisy.sh" <<'LN'
#!/bin/sh
cat >/dev/null
printf 'LEGACY-ERR\n' >&2
printf 'LEGACY-OUT\n'
LN
chmod 0755 "$fake/hooks/legacy-noisy.sh"
cat > "$fake/hooks/hooks.json.step3" <<'REG8'
{
  "hooks": {
    "PreToolUse": [
      {"matcher":"*","hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/hooks/legacy-noisy.sh"}]}
    ]
  }
}
REG8
printf '{"session_id":"t-q3","hook_event_name":"PreToolUse","tool_name":"Read"}' > "$tmp/q3.json"
turnrun q3 PreToolUse "$tmp/proj-q3" TMPDIR="$tmp/not-a-dir"
cp "$tmp/step3.saved8q" "$fake/hooks/hooks.json.step3"
is "noisy legacy hook exit" "$rc" 0
is "stderr is the runtime's own line and then the hook's, nothing else" \
  "$(cat "$tmp/q3.err")" "$(printf '%s\nLEGACY-ERR' "$noise_line")"
is "stderr is exactly those two lines, byte for byte" \
  "$(wc -c < "$tmp/q3.err" | tr -d ' ')" "$(( ${#noise_line} + 1 + 11 ))"
is "stdout is the legacy hook's stdout ALONE - parseable as the host left it" \
  "$(cat "$tmp/q3.out")" "LEGACY-OUT"
is "the file TMPDIR was still not deleted" "$(cat "$tmp/not-a-dir" 2>/dev/null)" "precious"

printf 'test-turn-tmpdir: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
