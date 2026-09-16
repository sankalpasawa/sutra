#!/usr/bin/env bash
# test-markers-step.sh - the 14 numbered cases of BRIEF.md section 4 for
# native:markers_write (pipeline id ups.markers_write). Every case runs the
# WHOLE `bin/sutra-turn run --event UserPromptSubmit` against a real (or, for
# cases 4/5/6/14, a copied-and-edited) plugin tree - never the step script in
# isolation - because the contract under test is the pipeline's behaviour,
# not the step's.
#
# ENVIRONMENT ISOLATION. Every invocation strips CLAUDE_CODE_SESSION_ID and
# CLAUDE_SESSION_ID from the child's environment. shim.sh inherits the
# environment untouched, and hooks/marker-lib.sh's _sutra_sid() prefers
# CLAUDE_CODE_SESSION_ID over the stdin session_id - so without this, every
# marker in this suite would land under THIS harness's own real session id
# instead of the fake one each case constructs (confirmed empirically while
# writing this file: the session dir was this session's own SID until the
# env vars were stripped).
#
# bash 3.2 compatible: no associative arrays, no ${var,,}, no mapfile.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-markers-step.sh

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_MAIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"

failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }

if ! command -v jq >/dev/null 2>&1; then
  fail "jq required to run this test"; echo "failed=$failed"; exit 1
fi
if [ ! -x "$PLUGIN_MAIN/bin/sutra-turn" ]; then
  fail "bin/sutra-turn missing or not executable at $PLUGIN_MAIN/bin/sutra-turn"
  echo "failed=$failed"; exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-markers-step.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# ------------------------------------------------------------------ helpers --

set_flag() { mkdir -p "$1"; [ -n "$2" ] && printf '%s\n' "$2" > "$1/.sutra-runtime-markers"; }

write_stdin() {  # <path> <sid> <event> [prompt]
  if [ $# -ge 4 ]; then
    jq -n --arg sid "$2" --arg ev "$3" --arg p "$4" \
      '{session_id:$sid, hook_event_name:$ev, prompt:$p}' > "$1"
  else
    jq -n --arg sid "$2" --arg ev "$3" \
      '{session_id:$sid, hook_event_name:$ev}' > "$1"
  fi
}

# do_run <name> <plugin_root> <proj> <home> <stdin_file> <event> [extra env ...]
# Sets RC. stdout/stderr land at $WORK/<name>.out and $WORK/<name>.err.
do_run() {
  _n="$1"; _pr="$2"; _pj="$3"; _hm="$4"; _stdin="$5"; _ev="$6"; shift 6
  mkdir -p "$_pj" "$_hm"
  env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID "$@" \
    CLAUDE_PROJECT_DIR="$_pj" CLAUDE_PLUGIN_ROOT="$_pr" HOME="$_hm" \
    "$_pr/bin/sutra-turn" run --event "$_ev" \
    < "$_stdin" > "$WORK/$_n.out" 2> "$WORK/$_n.err"
  RC=$?
}

session_dir()  { printf '%s/.claude/sessions/%s' "$1" "$2"; }             # <proj> <sid>
turn_current() { cat "$1/.sutra/turn/$2/current" 2>/dev/null; }           # <proj> <sid>
canon_ledger() { printf '%s/.sutra/turn/%s/%s.jsonl' "$1" "$2" "$3"; }    # <proj> <sid> <turnid>
facts_file()   { printf '%s/.sutra/turn/%s/%s.facts.json' "$1" "$2" "$3"; }
marker_body()  { cat "$(session_dir "$1" "$2")/$3" 2>/dev/null; }         # <proj> <sid> <name>
has_line()     { grep -qxF "$2" "$1" 2>/dev/null; }                       # <file> <exact line>
row_count() {  # <ledger_file> <jq_bool_filter>
  jq -s "[.[] | select($2)] | length" "$1" 2>/dev/null
}
MARKER_NAMES="input-routed depth-registered flow-classified flow-type-resolved"

# copy_plugin_min <dest> - bin, runtime, hooks (top-level files + hooks/lib,
# NEVER hooks/tests: that golden corpus is ~27MB), lib, skills, scripts.
copy_plugin_min() {
  _d="$1"
  mkdir -p "$_d"
  cp -R "$PLUGIN_MAIN/bin" "$_d/bin"
  cp -R "$PLUGIN_MAIN/runtime" "$_d/runtime"
  mkdir -p "$_d/hooks"
  find "$PLUGIN_MAIN/hooks" -maxdepth 1 -type f -exec cp {} "$_d/hooks/" \;
  cp -R "$PLUGIN_MAIN/hooks/lib" "$_d/hooks/lib"
  cp -R "$PLUGIN_MAIN/lib" "$_d/lib"
  cp -R "$PLUGIN_MAIN/skills" "$_d/skills"
  cp -R "$PLUGIN_MAIN/scripts" "$_d/scripts"
  chmod -R u+w "$_d" 2>/dev/null || true
}

# ===================================================================== 1 ====
echo "== case 1: flag on =="
PJ="$WORK/c1/proj"; HM="$WORK/c1/home"; SID="sid-c1"
set_flag "$HM" on
write_stdin "$WORK/c1.stdin.json" "$SID" UserPromptSubmit "please build the runtime markers step"
do_run c1 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c1.stdin.json" UserPromptSubmit
is "case1: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
if [ -z "$TID" ]; then
  fail "case1: no turn id published at .sutra/turn/$SID/current"
else
  SD="$(session_dir "$PJ" "$SID")"
  for m in $MARKER_NAMES; do
    if [ -f "$SD/$m" ]; then
      has_line "$SD/$m" "SOURCE=runtime" && pass "case1: $m carries SOURCE=runtime" \
        || fail "case1: $m missing exact line SOURCE=runtime: $(cat "$SD/$m")"
      has_line "$SD/$m" "SESSION=$SID" && pass "case1: $m carries SESSION=$SID" \
        || fail "case1: $m missing exact line SESSION=$SID: $(cat "$SD/$m")"
    else
      fail "case1: $m missing under $SD"
    fi
  done
  if [ -f "$SD/depth-registered" ]; then
    L1="$(sed -n '1p' "$SD/depth-registered")"
    printf '%s\n' "$L1" | grep -Eq '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$' \
      && pass "case1: depth-registered line 1 is Form A" \
      || fail "case1: depth-registered line 1 [$L1] is not Form A"
  fi
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case1: marker_write row count" "$(row_count "$CL" '.kind=="marker_write"')" 4
    is "case1: marker_flag row count" "$(row_count "$CL" '.kind=="marker_flag"')" 1
  else
    fail "case1: no canonical ledger at $CL"
  fi
  FF="$(facts_file "$PJ" "$SID" "$TID")"
  if [ -f "$FF" ]; then
    pass "case1: facts file exists"
    is "case1: facts .markers[depth-registered] == written" \
      "$(jq -r '.markers["depth-registered"]' "$FF" 2>/dev/null)" "written"
  else
    fail "case1: no facts file at $FF"
  fi
fi

# ===================================================================== 2 ====
echo "== case 2: flag absent =="
PJ="$WORK/c2/proj"; HM="$WORK/c2/home"; SID="sid-c2"
# No .sutra-runtime-markers file at all: mode resolves to off/default.
mkdir -p "$HM"
write_stdin "$WORK/c2.stdin.json" "$SID" UserPromptSubmit "please build the runtime markers step"
do_run c2 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c2.stdin.json" UserPromptSubmit
is "case2: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
SD="$(session_dir "$PJ" "$SID")"
none=1
for m in $MARKER_NAMES; do [ -f "$SD/$m" ] && none=0; done
[ "$none" -eq 1 ] && pass "case2: no marker under the session dir" \
  || fail "case2: a marker was written under $SD despite flag absent"
if [ -n "$TID" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case2: marker_skip reason=flag-off row count" \
      "$(row_count "$CL" '.kind=="marker_skip" and .reason=="flag-off"')" 1
  else
    fail "case2: no canonical ledger at $CL"
  fi
  FF="$(facts_file "$PJ" "$SID" "$TID")"
  [ -f "$FF" ] && fail "case2: facts file written despite flag absent: $FF" \
    || pass "case2: no facts file"
else
  fail "case2: no turn id published"
fi

# ===================================================================== 3 ====
echo "== case 3: SUTRA_RUNTIME_DISABLED=1 with flag on =="
PJ="$WORK/c3/proj"; HM="$WORK/c3/home"; SID="sid-c3"
set_flag "$HM" on
write_stdin "$WORK/c3.stdin.json" "$SID" UserPromptSubmit "please build the runtime markers step"
do_run c3 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c3.stdin.json" UserPromptSubmit SUTRA_RUNTIME_DISABLED=1
is "case3: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
SD="$(session_dir "$PJ" "$SID")"
none=1
for m in $MARKER_NAMES; do [ -f "$SD/$m" ] && none=0; done
[ "$none" -eq 1 ] && pass "case3: no marker written with the runtime disabled" \
  || fail "case3: a marker was written under $SD despite SUTRA_RUNTIME_DISABLED=1"
if [ -n "$TID" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case3: killswitch row count" "$(row_count "$CL" '.kind=="killswitch"')" 1
    is "case3: no marker_* rows at all" \
      "$(row_count "$CL" '(.kind|tostring|startswith("marker_"))')" 0
  else
    fail "case3: no canonical ledger at $CL"
  fi
fi

# ===================================================================== 4 ====
echo "== case 4: reset hook sleeps 150ms then wipes; the post-phase step must survive =="
C4="$WORK/c4-plugin"
copy_plugin_min "$C4"
cat > "$C4/hooks/reset-turn-markers.sh" <<'STUB4'
#!/bin/sh
IN="$(cat)"
SID=$(printf '%s' "$IN" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
sleep 0.15
[ -n "$SID" ] && rm -rf "${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/$SID"
exit 0
STUB4
chmod 0755 "$C4/hooks/reset-turn-markers.sh"
PJ="$WORK/c4/proj"; HM="$WORK/c4/home"; SID="sid-c4"
set_flag "$HM" on
write_stdin "$WORK/c4.stdin.json" "$SID" UserPromptSubmit "please ship the post-phase ordering test"
do_run c4 "$C4" "$PJ" "$HM" "$WORK/c4.stdin.json" UserPromptSubmit
is "case4: exit 0" "$RC" 0
SD="$(session_dir "$PJ" "$SID")"
for m in $MARKER_NAMES; do
  if [ -f "$SD/$m" ] && has_line "$SD/$m" "SOURCE=runtime"; then
    pass "case4: $m survived the mid-turn wipe (D4 ordering)"
  else
    fail "case4: $m missing or lacks SOURCE=runtime after the reset stub's wipe"
  fi
done

# ===================================================================== 5 ====
echo "== case 5: classify.sh stub exits 1 =="
C5="$WORK/c5-plugin"
copy_plugin_min "$C5"
cat > "$C5/skills/human-sutra/scripts/classify.sh" <<'STUB5'
#!/bin/bash
exit 1
STUB5
chmod 0755 "$C5/skills/human-sutra/scripts/classify.sh"
PJ="$WORK/c5/proj"; HM="$WORK/c5/home"; SID="sid-c5"
set_flag "$HM" on
write_stdin "$WORK/c5.stdin.json" "$SID" UserPromptSubmit "please degrade the classify path"
do_run c5 "$C5" "$PJ" "$HM" "$WORK/c5.stdin.json" UserPromptSubmit
is "case5: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
SD="$(session_dir "$PJ" "$SID")"
for m in $MARKER_NAMES; do
  [ -f "$SD/$m" ] && pass "case5: $m still written despite classify.sh failing" \
    || fail "case5: $m missing"
done
if [ -f "$SD/flow-classified" ]; then
  has_line "$SD/flow-classified" "VERB=UNKNOWN" && pass "case5: flow-classified has VERB=UNKNOWN" \
    || fail "case5: flow-classified missing VERB=UNKNOWN: $(cat "$SD/flow-classified")"
fi
if [ -n "$TID" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case5: marker_source_failed tool=classify.sh row count" \
      "$(row_count "$CL" '.kind=="marker_source_failed" and .tool=="classify.sh"')" 1
  else
    fail "case5: no canonical ledger at $CL"
  fi
fi

# ===================================================================== 6 ====
echo "== case 6: event stdout/stderr byte-identical with and without the native steps =="
C6W="$WORK/c6-with"; C6X="$WORK/c6-without"
copy_plugin_min "$C6W"
copy_plugin_min "$C6X"
jq '.events.UserPromptSubmit |= map(select(.impl != "native:markers_write"))
  | .events.Stop |= map(select(.impl != "native:markers_diff"))' \
  "$C6X/runtime/pipeline.json" > "$C6X/runtime/pipeline.json.new" \
  && mv "$C6X/runtime/pipeline.json.new" "$C6X/runtime/pipeline.json"
w_native="$(jq '[.events.UserPromptSubmit[], .events.Stop[] | select(.impl=="native:markers_write" or .impl=="native:markers_diff")] | length' "$C6W/runtime/pipeline.json")"
x_native="$(jq '[.events.UserPromptSubmit[], .events.Stop[] | select(.impl=="native:markers_write" or .impl=="native:markers_diff")] | length' "$C6X/runtime/pipeline.json")"
is "case6: 'with' pipeline still declares both native steps" "$w_native" 2
is "case6: 'without' pipeline declares neither native step" "$x_native" 0

# Legacy Stop hooks run here against an empty temp project on a possibly
# loaded box and hit their budgets at random ("sutra runtime degraded: step X
# exceeded Nms" on the event's stderr, the RT-4 (x) class); WHICH ones time out
# differs between the 'with' and 'without' runs. Those lines are load, not the
# native step. A degraded line naming a NATIVE step is a parity break and fails
# outright (D12); every other byte of stderr must match.
err_pair_check() {  # <label> <event> <with.err> <without.err>
  if grep -qE '^sutra runtime degraded: step (ups\.markers_write|stop\.markers_diff) exceeded' "$3" 2>/dev/null; then
    fail "case6 [$1] $2: a native step hit its watchdog (degraded line on stderr)"
    return 0
  fi
  grep -vE '^sutra runtime degraded: step [^ ]+ exceeded [0-9]+ms$' "$3" > "$3.norm" 2>/dev/null
  grep -vE '^sutra runtime degraded: step [^ ]+ exceeded [0-9]+ms$' "$4" > "$4.norm" 2>/dev/null
  if cmp -s "$3.norm" "$4.norm"; then
    pass "case6 [$1] $2: stderr byte-identical with/without the native step (legacy timeout lines aside)"
    return 0
  fi
  # Flag ON is the one state where the two sides legitimately differ: the
  # markers the step wrote at UserPromptSubmit are exactly what the Stop gates
  # read (flow-stop-check stops warning "core:flow did not fire" once
  # flow-classified exists). That is the increment, not a leak. The rule that
  # still holds: the native step may make a downstream gate DROP a line, it may
  # never ADD one. Lines present on the 'with' side and absent on the 'without'
  # side are therefore the only failure.
  if [ "$1" = "on" ]; then
    added="$(grep -vxF -f "$4.norm" "$3.norm" 2>/dev/null)"
    if [ -z "$added" ]; then
      removed_n="$(grep -vxF -f "$3.norm" "$4.norm" 2>/dev/null | grep -c . 2>/dev/null)"
      pass "case6 [$1] $2: stderr adds nothing with the native step ($removed_n gate line(s) dropped because the markers now exist)"
      return 0
    fi
    fail "case6 [$1] $2: stderr gained line(s) with the native step:"
    printf '%s\n' "$added" | sed -n '1,10p'
    return 0
  fi
  fail "case6 [$1] $2: stderr differs with/without the native step"
  diff -u "$4.norm" "$3.norm" 2>&1 | sed -n '1,10p'
}

c6_pair() {  # <label> <flagval or empty>
  _lbl="$1"; _fv="$2"
  PJW="$WORK/c6-${_lbl}-with-proj"; HMW="$WORK/c6-${_lbl}-with-home"
  PJX="$WORK/c6-${_lbl}-without-proj"; HMX="$WORK/c6-${_lbl}-without-home"
  set_flag "$HMW" "$_fv"; set_flag "$HMX" "$_fv"
  SID="sid-c6-$_lbl"
  write_stdin "$WORK/c6-${_lbl}.stdin.json" "$SID" UserPromptSubmit "please compare with and without the native step"
  do_run "c6-${_lbl}-with" "$C6W" "$PJW" "$HMW" "$WORK/c6-${_lbl}.stdin.json" UserPromptSubmit
  RCW=$RC
  do_run "c6-${_lbl}-without" "$C6X" "$PJX" "$HMX" "$WORK/c6-${_lbl}.stdin.json" UserPromptSubmit
  RCX=$RC
  is "case6 [$_lbl] UPS: exit codes match" "$RCW" "$RCX"
  if cmp -s "$WORK/c6-${_lbl}-with.out" "$WORK/c6-${_lbl}-without.out"; then
    pass "case6 [$_lbl] UPS: stdout byte-identical with/without the native step"
  else
    fail "case6 [$_lbl] UPS: stdout differs with/without the native step"
    diff -u "$WORK/c6-${_lbl}-without.out" "$WORK/c6-${_lbl}-with.out" 2>&1 | sed -n '1,10p'
  fi
  err_pair_check "$_lbl" UPS "$WORK/c6-${_lbl}-with.err" "$WORK/c6-${_lbl}-without.err"

  # Stop pair, same two sessions, so a facts file exists on the 'with' side
  # (and is simply absent on the 'without' side - the step there does not
  # exist to write one, which is exactly what parity requires).
  write_stdin "$WORK/c6-${_lbl}-stop.stdin.json" "$SID" Stop
  # SUTRA_STEP_TIMEOUT_SCALE=400 is the documented harness knob (golden/README.md):
  # it lengthens every legacy step's budget so a loaded box times out fewer of
  # the 24 Stop hooks; it never shortens a budget, so it cannot hide a slow native step.
  do_run "c6-${_lbl}-with-stop" "$C6W" "$PJW" "$HMW" "$WORK/c6-${_lbl}-stop.stdin.json" Stop SUTRA_STEP_TIMEOUT_SCALE=400
  RCW2=$RC
  do_run "c6-${_lbl}-without-stop" "$C6X" "$PJX" "$HMX" "$WORK/c6-${_lbl}-stop.stdin.json" Stop SUTRA_STEP_TIMEOUT_SCALE=400
  RCX2=$RC
  is "case6 [$_lbl] Stop: exit codes match" "$RCW2" "$RCX2"
  if cmp -s "$WORK/c6-${_lbl}-with-stop.out" "$WORK/c6-${_lbl}-without-stop.out"; then
    pass "case6 [$_lbl] Stop: stdout byte-identical with/without the native step"
  else
    fail "case6 [$_lbl] Stop: stdout differs with/without the native step"
  fi
  err_pair_check "$_lbl" Stop "$WORK/c6-${_lbl}-with-stop.err" "$WORK/c6-${_lbl}-without-stop.err"
}
c6_pair "on" "on"
c6_pair "off" ""

# ===================================================================== 7 ====
echo "== case 7: two sessions, A on, B off, no cross-contamination =="
PJ="$WORK/c7/proj"
HMA="$WORK/c7/homeA"; HMB="$WORK/c7/homeB"
set_flag "$HMA" on
set_flag "$HMB" off
SIDA="sid-c7-A"; SIDB="sid-c7-B"
write_stdin "$WORK/c7a.stdin.json" "$SIDA" UserPromptSubmit "please run session A"
do_run c7a "$PLUGIN_MAIN" "$PJ" "$HMA" "$WORK/c7a.stdin.json" UserPromptSubmit
write_stdin "$WORK/c7b.stdin.json" "$SIDB" UserPromptSubmit "please run session B"
do_run c7b "$PLUGIN_MAIN" "$PJ" "$HMB" "$WORK/c7b.stdin.json" UserPromptSubmit
SDA="$(session_dir "$PJ" "$SIDA")"; SDB="$(session_dir "$PJ" "$SIDB")"
a_ok=1
for m in $MARKER_NAMES; do
  [ -f "$SDA/$m" ] && has_line "$SDA/$m" "SESSION=$SIDA" || a_ok=0
done
[ "$a_ok" -eq 1 ] && pass "case7: session A's 4 markers all carry SESSION=$SIDA" \
  || fail "case7: session A's markers incomplete or mis-stamped under $SDA"
b_ok=1
for m in input-routed depth-registered; do
  [ -f "$SDB/$m" ] && b_ok=0
done
for m in flow-classified flow-type-resolved; do
  [ -f "$SDB/$m" ] && has_line "$SDB/$m" "SOURCE=runtime" && b_ok=0
done
[ "$b_ok" -eq 1 ] && pass "case7: session B (flag off) carries no runtime-written marker" \
  || fail "case7: session B has a runtime-attributable marker under $SDB despite flag off"
CONTAM="$PJ/.enforcement/marker-contamination.jsonl"
if [ ! -s "$CONTAM" ]; then
  pass "case7: marker-contamination.jsonl absent or empty"
else
  fail "case7: marker-contamination.jsonl non-empty: $(cat "$CONTAM")"
fi

# ===================================================================== 8 ====
echo "== case 8: PATH with no python3 -> degraded fallback =="
NOJQ8="$WORK/c8-bin"; mkdir -p "$NOJQ8"
# DEVIATION (documented, see final report): the brief's own allowlist omits
# bash. runtime/steps/*.sh and most hooks are #!/usr/bin/env bash (Rule,
# BRIEF.md section 1) - without bash on PATH the whole event fails, testing
# "no bash" instead of the intended "no python3" degraded-fallback path. bash
# is included so this case exercises what D11/D19 actually describe.
for c in sh jq grep sed awk cut tr head cat date mkdir mv rm shasum wc sort uniq \
         basename dirname printf ls find sleep kill env bash; do
  p="$(command -v "$c" 2>/dev/null)" || continue
  [ -n "$p" ] && [ -x "$p" ] || continue
  ln -sf "$p" "$NOJQ8/$c" 2>/dev/null || true
done
if [ -x "$NOJQ8/jq" ] && [ -x "$NOJQ8/bash" ] && [ ! -e "$NOJQ8/python3" ] && [ ! -e "$NOJQ8/python" ]; then
  pass "case8: no-python3 PATH is buildable (jq/bash present, python3/python absent)"
else
  fail "case8: no-python3 PATH not buildable as intended under $NOJQ8"
fi
PJ="$WORK/c8/proj"; HM="$WORK/c8/home"; SID="sid-c8"
set_flag "$HM" on
write_stdin "$WORK/c8.stdin.json" "$SID" UserPromptSubmit "please build without python3"
do_run c8 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c8.stdin.json" UserPromptSubmit PATH="$NOJQ8"
is "case8: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
SD="$(session_dir "$PJ" "$SID")"
for m in $MARKER_NAMES; do
  [ -f "$SD/$m" ] && pass "case8: $m exists" || fail "case8: $m missing"
done
if [ -f "$SD/flow-type-resolved" ]; then
  L1="$(sed -n '1p' "$SD/flow-type-resolved")"
  is "case8: flow-type-resolved line 1" "$L1" "RESOLUTION=CONSTRUCT SCOPE=none SCORE=0"
  has_line "$SD/flow-type-resolved" "DEGRADED=python3" && pass "case8: DEGRADED=python3 present" \
    || fail "case8: DEGRADED=python3 missing: $(cat "$SD/flow-type-resolved")"
fi
if [ -f "$SD/depth-registered" ]; then
  grep -Eq '^RUBRIC=.*-degraded$' "$SD/depth-registered" && pass "case8: RUBRIC=*-degraded" \
    || fail "case8: no RUBRIC=*-degraded line: $(cat "$SD/depth-registered")"
fi
if [ -n "$TID" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case8: marker_source_failed row count" "$(row_count "$CL" '.kind=="marker_source_failed"')" 2
    is "case8: no marker_source_failed for classify.sh (needs no python3)" \
      "$(row_count "$CL" '.kind=="marker_source_failed" and .tool=="classify.sh"')" 0
  else
    fail "case8: no canonical ledger at $CL"
  fi
fi

# ===================================================================== 9 ====
echo "== case 9: identity - facts parse back through the gates' own greps =="
PJ="$WORK/c9/proj"; HM="$WORK/c9/home"; SID="sid-c9"
set_flag "$HM" on
write_stdin "$WORK/c9.stdin.json" "$SID" UserPromptSubmit "what is the status of the runtime build?"
do_run c9 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c9.stdin.json" UserPromptSubmit
is "case9: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
FF="$(facts_file "$PJ" "$SID" "$TID")"
SD="$(session_dir "$PJ" "$SID")"
if [ -f "$FF" ]; then
  F_VERB="$(jq -r '.classify.verb' "$FF")"
  F_TYPE="$(jq -r '.type' "$FF")"
  F_DEPTH="$(jq -r '.depth.n' "$FF")"
  F_RES="$(jq -r '.resolve.resolution' "$FF")"
  F_SCOPE="$(jq -r '.resolve.scope' "$FF")"

  if [ -f "$SD/flow-classified" ]; then
    is "case9: VERB (flow-classified, gate regex 'VERB=') matches facts" \
      "$(grep -oE 'VERB=[A-Za-z_-]+' "$SD/flow-classified" | head -1 | cut -d= -f2)" "$F_VERB"
  else
    fail "case9: flow-classified missing, cannot cross-check VERB"
  fi
  if [ -f "$SD/input-routed" ]; then
    is "case9: TYPE (input-routed, gate regex 'TYPE=') matches facts" \
      "$(grep -oE 'TYPE=[A-Za-z_-]+' "$SD/input-routed" | head -1 | cut -d= -f2)" "$F_TYPE"
  else
    fail "case9: input-routed missing, cannot cross-check TYPE"
  fi
  if [ -f "$SD/depth-registered" ]; then
    is "case9: DEPTH (depth-registered, gate regex 'DEPTH=[0-9]+') matches facts" \
      "$(grep -oE 'DEPTH=[0-9]+' "$SD/depth-registered" | head -1 | cut -d= -f2)" "$F_DEPTH"
  else
    fail "case9: depth-registered missing, cannot cross-check DEPTH"
  fi
  if [ -f "$SD/flow-type-resolved" ]; then
    is "case9: RESOLUTION (flow-type-resolved, gate regex 'RESOLUTION=') matches facts" \
      "$(grep -oE 'RESOLUTION=[^ ]*' "$SD/flow-type-resolved" | head -1 | cut -d= -f2-)" "$F_RES"
    is "case9: SCOPE (flow-type-resolved, gate regex 'SCOPE=') matches facts" \
      "$(grep -oE 'SCOPE=[^ ]*' "$SD/flow-type-resolved" | head -1 | cut -d= -f2-)" "$F_SCOPE"
  else
    fail "case9: flow-type-resolved missing, cannot cross-check RESOLUTION/SCOPE"
  fi
else
  fail "case9: no facts file at $FF"
fi

# ==================================================================== 10 ====
echo "== case 10: same stdin twice, same turn_id =="
PJ="$WORK/c10/proj"; HM="$WORK/c10/home"; SID="sid-c10"
set_flag "$HM" on
write_stdin "$WORK/c10.stdin.json" "$SID" UserPromptSubmit "please repeat the same turn twice"
do_run c10a "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c10.stdin.json" UserPromptSubmit
is "case10: first run exit 0" "$RC" 0
TID1="$(turn_current "$PJ" "$SID")"
snap1=""
for m in $MARKER_NAMES; do
  snap1="$snap1|||$m:$(marker_body "$PJ" "$SID" "$m" | sed -E 's/ TS=[0-9]+$//' | grep -v '^TS=')"
done
do_run c10b "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c10.stdin.json" UserPromptSubmit
is "case10: second run exit 0" "$RC" 0
TID2="$(turn_current "$PJ" "$SID")"
is "case10: same turn_id both runs" "$TID2" "$TID1"
snap2=""
for m in $MARKER_NAMES; do
  snap2="$snap2|||$m:$(marker_body "$PJ" "$SID" "$m" | sed -E 's/ TS=[0-9]+$//' | grep -v '^TS=')"
done
is "case10: marker bodies identical except TS=" "$snap2" "$snap1"
n_facts="$(find "$PJ/.sutra/turn/$SID" -maxdepth 1 -name '*.facts.json' 2>/dev/null | wc -l | tr -d ' ')"
is "case10: exactly one facts file" "$n_facts" 1
if [ -n "$TID1" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID1")"
  [ -f "$CL" ] && is "case10: marker_write rows across both runs" \
    "$(row_count "$CL" '.kind=="marker_write"')" 8
fi

# ==================================================================== 11 ====
echo "== case 11: narrated depth-registered body is left alone (D6) =="
# A body written BEFORE the UserPromptSubmit cannot survive it: the reset step
# wipes the session dir on every real prompt, by design. The narrated body D6
# protects is one the model writes AFTER the reset. So: run 1 (the runtime
# writes all four), the "model" overwrites depth-registered with a narrated
# body, then run 2 inside the reset's 3 s burst window (stamp touched, so no
# wipe): depth-registered stays, the three computed bodies are replaced, and
# the ledger carries one marker_skip reason=narrated row.
PJ="$WORK/c11/proj"; HM="$WORK/c11/home"; SID="sid-c11"
set_flag "$HM" on
write_stdin "$WORK/c11.stdin.json" "$SID" UserPromptSubmit "please respect the narrated marker"
do_run c11a "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c11.stdin.json" UserPromptSubmit
is "case11: first run exit 0" "$RC" 0
SD="$(session_dir "$PJ" "$SID")"
[ -f "$SD/depth-registered" ] && has_line "$SD/depth-registered" "SOURCE=runtime" \
  && pass "case11: run 1 wrote a computed depth body" \
  || fail "case11: run 1 did not write a computed depth-registered under $SD"
NARRATED_BODY="DEPTH=2 TASK=manual-note TS=1700000000
NOTE=written by the model after the runtime step ran
SESSION=$SID"
printf '%s\n' "$NARRATED_BODY" > "$SD/depth-registered"
date +%s > "$SD/.last-reset-ts"
do_run c11 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c11.stdin.json" UserPromptSubmit
is "case11: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
is "case11: depth-registered body untouched" "$(cat "$SD/depth-registered")" "$(printf '%s\n' "$NARRATED_BODY")"
for m in input-routed flow-classified flow-type-resolved; do
  [ -f "$SD/$m" ] && has_line "$SD/$m" "SOURCE=runtime" && pass "case11: $m written normally" \
    || fail "case11: $m missing or lacks SOURCE=runtime"
done
if [ -n "$TID" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case11: marker_skip reason=narrated name=depth-registered row count" \
      "$(row_count "$CL" '.kind=="marker_skip" and .reason=="narrated" and .name=="depth-registered"')" 1
    # same prompt -> same turn_id -> one canonical ledger for both runs:
    # 4 writes from run 1 + 3 from run 2 (depth-registered skipped as narrated).
    is "case11: marker_write rows across both runs (4 + 3)" \
      "$(row_count "$CL" '.kind=="marker_write"')" 7
  else
    fail "case11: no canonical ledger at $CL"
  fi
fi

# ==================================================================== 12 ====
echo "== case 12: synthetic prompt is not a real turn =="
PJ="$WORK/c12/proj"; HM="$WORK/c12/home"; SID="sid-c12"
set_flag "$HM" on
write_stdin "$WORK/c12.stdin.json" "$SID" UserPromptSubmit "<system-reminder>this is a synthetic injected prompt</system-reminder>"
do_run c12 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c12.stdin.json" UserPromptSubmit
is "case12: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
SD="$(session_dir "$PJ" "$SID")"
none=1
for m in $MARKER_NAMES; do [ -f "$SD/$m" ] && none=0; done
[ "$none" -eq 1 ] && pass "case12: no marker written on a synthetic prompt" \
  || fail "case12: a marker was written on a synthetic prompt under $SD"
if [ -n "$TID" ]; then
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  if [ -f "$CL" ]; then
    is "case12: marker_skip reason=synthetic row count" \
      "$(row_count "$CL" '.kind=="marker_skip" and .reason=="synthetic"')" 1
    FF="$(facts_file "$PJ" "$SID" "$TID")"
    [ -f "$FF" ] && fail "case12: facts file written despite the synthetic skip" \
      || pass "case12: no facts file written"
  fi
fi

# ==================================================================== 13 ====
echo "== case 13: mode shadow =="
PJ="$WORK/c13/proj"; HM="$WORK/c13/home"; SID="sid-c13"
set_flag "$HM" shadow
write_stdin "$WORK/c13.stdin.json" "$SID" UserPromptSubmit "please run in shadow mode"
do_run c13 "$PLUGIN_MAIN" "$PJ" "$HM" "$WORK/c13.stdin.json" UserPromptSubmit
is "case13: exit 0" "$RC" 0
TID="$(turn_current "$PJ" "$SID")"
SD="$(session_dir "$PJ" "$SID")"
none=1
for m in $MARKER_NAMES; do [ -f "$SD/$m" ] && none=0; done
[ "$none" -eq 1 ] && pass "case13: real session dir holds no runtime marker" \
  || fail "case13: shadow mode wrote into the real session dir $SD"
if [ -n "$TID" ]; then
  SHDIR="$PJ/.sutra/shadow/markers/$SID/$TID"
  allfour=1
  for m in $MARKER_NAMES; do [ -f "$SHDIR/$m" ] || allfour=0; done
  [ "$allfour" -eq 1 ] && pass "case13: shadow dir holds all four bodies" \
    || fail "case13: shadow dir $SHDIR is missing one or more of the four bodies"
  CL="$(canon_ledger "$PJ" "$SID" "$TID")"
  [ -f "$CL" ] && is "case13: marker_shadow row count" \
    "$(row_count "$CL" '.kind=="marker_shadow"')" 4
  FF="$(facts_file "$PJ" "$SID" "$TID")"
  [ -f "$FF" ] && pass "case13: facts file exists in shadow mode" \
    || fail "case13: no facts file at $FF"
fi

# ==================================================================== 14 ====
echo "== case 14: timing - native step adds under 1500ms, no watchdog kill =="
now_ms() { jq -n 'now*1000|floor'; }
timed_run() {  # <plugin_root> <name_prefix> -> prints min-of-3 ms
  _pr="$1"; _pp="$2"
  best=""
  i=1
  while [ "$i" -le 3 ]; do
    PJt="$WORK/${_pp}-$i"; HMt="$WORK/${_pp}-$i-home"
    set_flag "$HMt" on
    write_stdin "$WORK/${_pp}-$i.stdin.json" "sid-${_pp}-$i" UserPromptSubmit "please time the event"
    t0="$(now_ms)"
    do_run "${_pp}-$i" "$_pr" "$PJt" "$HMt" "$WORK/${_pp}-$i.stdin.json" UserPromptSubmit
    t1="$(now_ms)"
    el=$((t1 - t0))
    if [ -z "$best" ] || [ "$el" -lt "$best" ]; then best="$el"; fi
    i=$((i + 1))
  done
  printf '%s' "$best"
}
MIN_WITH="$(timed_run "$C6W" "c14w")"
MIN_WITHOUT="$(timed_run "$C6X" "c14x")"
DELTA=$((MIN_WITH - MIN_WITHOUT))
[ "$DELTA" -lt 0 ] && DELTA=$((0 - DELTA))
echo "metric: case14 min-of-3 with=${MIN_WITH}ms without=${MIN_WITHOUT}ms delta=${DELTA}ms"
if [ "$DELTA" -lt 1500 ]; then
  pass "case14: wall delta ${DELTA}ms under 1500ms"
else
  fail "case14: wall delta ${DELTA}ms is 1500ms or more"
fi
LASTPJ="$WORK/c14w-3"; LASTSID="sid-c14w-3"
TID14="$(turn_current "$LASTPJ" "$LASTSID")"
if [ -n "$TID14" ]; then
  CL14="$(canon_ledger "$LASTPJ" "$LASTSID" "$TID14")"
  [ -f "$CL14" ] && is "case14: no exit:124 row for ups.markers_write" \
    "$(row_count "$CL14" '.kind=="step" and .step_id=="ups.markers_write" and .exit==124')" 0
fi
if grep -q 'degraded' "$WORK/c14w-3.err" 2>/dev/null; then
  fail "case14: event stderr contains a degraded line: $(cat "$WORK/c14w-3.err")"
else
  pass "case14: event stderr has no degraded line"
fi

echo "failed=$failed"
[ "$failed" -eq 0 ]
