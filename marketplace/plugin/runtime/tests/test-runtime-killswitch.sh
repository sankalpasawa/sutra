#!/usr/bin/env bash
# test-runtime-killswitch.sh - step 0 of sutra-turn: the two ways the runtime
# stands down, and the proof that standing down still runs the fleet.
#
# THE CLAIM UNDER TEST. Before sutra-turn reads pipeline.json at all it must
# answer one question: am I allowed to be the runtime on this machine right now?
# Three answers, three observable behaviours:
#   ~/.sutra-runtime-disabled      -> legacy path, ledger row kind=killswitch
#   SUTRA_RUNTIME_DISABLED=1       -> legacy path, ledger row kind=killswitch
#   jq missing or failing its probe -> ONE fixed line on stdout, then the legacy
#                                      path, ledger row kind=jq_failed
# "Legacy path" means: every registration of the event in the PRE-COLLAPSE
# registry, in order, with the same stdin, streams straight through - what the
# host itself did before this program existed.
#
# WHICH REGISTRY. Not hooks.json. Once the runtime lands, hooks.json holds
# eight registrations and seven of them ARE sutra-turn, so a fallback reading it
# would re-exec itself (or, with the kill-switch set, loop) and the fleet would
# lose every hook at exactly the moment the runtime was told to stand down. The
# legacy registry of record is hooks/hooks.json.step3, the snapshot taken before
# the collapse; hooks.json is read only when no snapshot is installed. Either
# way a registration whose argv contains sutra-turn or sutra-canary is REFUSED,
# with a kind=legacy_skip ledger row naming it.
#
# HOW IT IS PROVED, NOT ASSERTED. The test builds a throw-away plugin root whose
# hooks.json is the real collapsed 8-entry file, whose hooks.json.step3 registers
# two hooks that print LEGACY-ONE / LEGACY-TWO (plus one self-registration that
# must be refused), and whose pipeline.json registers a DIFFERENT hook that
# prints RUNTIME-PROBE. The two code paths therefore have disjoint output, and a
# control run (no kill-switch, jq present) is asserted to take the runtime path -
# without it, a sutra-turn that always fell back would pass every kill-switch
# check.
#
# EMISSION. The last section asserts the other half of behaviour-identity: under
# the legacy host EVERY hook's stderr reached the terminal. Two advisory steps
# and one blocking step must therefore put all three messages on fd 2, in step
# order, with the blocking one last.
#
# The jq-missing case runs sutra-turn under a PATH that contains only symlinks
# to the commands the degraded path is allowed to need; jq is simply not one of
# them. HOME is redirected in every case so a real ~/.sutra-runtime-disabled on
# the developer's machine can neither cause nor mask a result.
#
# bash 3.2 + jq. Prints "failed=N"; exit 0 iff N is 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-runtime-killswitch.sh

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

command -v jq >/dev/null 2>&1 || { printf 'test-runtime-killswitch: jq required\nfailed=1\n'; exit 1; }
[ -x "$turn" ] || { printf 'test-runtime-killswitch: %s not executable\nfailed=1\n' "$turn"; exit 1; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-killswitch.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

# ------------------------------------------------------- throw-away plugin --
fake="$tmp/plugin"
mkdir -p "$fake/bin" "$fake/runtime" "$fake/hooks"
cp "$turn" "$fake/bin/sutra-turn"; chmod 0755 "$fake/bin/sutra-turn"
cp "$runtime/shim.sh" "$runtime/ledger.sh" "$fake/runtime/"

mkhook() { printf '#!/bin/sh\ncat >/dev/null\nprintf %%s\\\\n "%s"\n' "$2" > "$1"; chmod 0755 "$1"; }
mkhook "$fake/hooks/legacy-one.sh" "LEGACY-ONE"
mkhook "$fake/hooks/legacy-two.sh" "LEGACY-TWO"

# The pipeline step is a hook the legacy registry does NOT contain, so the two
# paths can never be confused for one another.
cat > "$fake/hooks/probe.sh" <<'PROBE'
#!/bin/sh
cat >/dev/null
printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"RUNTIME-PROBE"}}\n'
PROBE
chmod 0755 "$fake/hooks/probe.sh"

# Three advisory/blocking hooks for the PreToolUse emission section.
cat > "$fake/hooks/adv-one.sh" <<'A1'
#!/bin/sh
cat >/dev/null
printf 'ADV-ONE\n' >&2
exit 0
A1
cat > "$fake/hooks/adv-two.sh" <<'A2'
#!/bin/sh
cat >/dev/null
printf 'ADV-TWO\n' >&2
exit 0
A2
cat > "$fake/hooks/denier.sh" <<'A3'
#!/bin/sh
cat >/dev/null
printf 'DENY-THREE\n' >&2
exit 2
A3
chmod 0755 "$fake/hooks/adv-one.sh" "$fake/hooks/adv-two.sh" "$fake/hooks/denier.sh"

# hooks.json AS IT SHIPS AFTER THE COLLAPSE: eight registrations, seven of them
# this very program plus the canary. Nothing here may ever be executed by the
# fallback.
cat > "$fake/hooks/hooks.json" <<'REG'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event UserPromptSubmit"
          },
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/sutra-canary"
          }
        ]
      }
    ]
  }
}
REG

# hooks.json.step3: the PRE-COLLAPSE snapshot, in the host's own shape, with
# ${CLAUDE_PLUGIN_ROOT} left unexpanded exactly as the real registry writes it.
# The third entry is a self-registration that MUST be refused.
cat > "$fake/hooks/hooks.json.step3" <<'REG3'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/legacy-one.sh"
          },
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/legacy-two.sh"
          },
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/sutra-turn run --event UserPromptSubmit"
          }
        ]
      }
    ]
  }
}
REG3

cat > "$fake/runtime/pipeline.json" <<'PIPE'
{
  "contract_version": 1,
  "events": {
    "UserPromptSubmit": [
      {
        "id": "ups.probe",
        "matcher": "*",
        "class": "A",
        "impl": "shim:hooks/probe.sh",
        "timeout_ms": 3000,
        "replaces": ["hooks/probe.sh"]
      }
    ],
    "PreToolUse": [
      {
        "id": "pre.adv-one",
        "matcher": "*",
        "class": "A",
        "impl": "shim:hooks/adv-one.sh",
        "timeout_ms": 3000,
        "replaces": ["hooks/adv-one.sh"]
      },
      {
        "id": "pre.adv-two",
        "matcher": "*",
        "class": "A",
        "impl": "shim:hooks/adv-two.sh",
        "timeout_ms": 3000,
        "replaces": ["hooks/adv-two.sh"]
      },
      {
        "id": "pre.denier",
        "matcher": "*",
        "class": "A",
        "impl": "shim:hooks/denier.sh",
        "timeout_ms": 3000,
        "replaces": ["hooks/denier.sh"]
      }
    ]
  }
}
PIPE

sid="cafe0000-1111-2222-3333-444444444444"
printf '{"session_id":"%s","hook_event_name":"UserPromptSubmit","prompt":"hello"}\n' "$sid" > "$tmp/stdin.json"

printf 'LEGACY-ONE\nLEGACY-TWO\n'                                   > "$tmp/want.legacy"
printf 'sutra runtime degraded: jq unavailable\nLEGACY-ONE\nLEGACY-TWO\n' > "$tmp/want.degraded"

# run_case <name> <project_dir> <home_dir> [env assignments...]
# Leaves stdout in $tmp/<name>.out, stderr in $tmp/<name>.err, rc in $rc.
run_case() {
  _rc_name="$1"; _rc_proj="$2"; _rc_home="$3"; shift 3
  mkdir -p "$_rc_proj/.claude" "$_rc_proj/.sutra" "$_rc_proj/.enforcement" "$_rc_home"
  env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$_rc_proj" HOME="$_rc_home" "$@" \
    "$fake/bin/sutra-turn" run --event UserPromptSubmit \
    < "$tmp/stdin.json" > "$tmp/$_rc_name.out" 2> "$tmp/$_rc_name.err"
  rc=$?
}

# ledger_rows <project_dir> -> every jsonl row written for the session, flat view
ledger_flat() { printf '%s' "$1/.sutra/turn/$sid.jsonl"; }
kind_count() { jq -s --arg k "$2" '[.[] | select(.kind==$k)] | length' "$1" 2>/dev/null; }

# ------------------------------------------------- 1. control: runtime path --
# Without this, a sutra-turn that ALWAYS fell back would pass every case below.
run_case control "$tmp/proj-control" "$tmp/home-control"
is "control exit" "$rc" 0
if grep -q 'RUNTIME-PROBE' "$tmp/control.out"; then ok; else
  fail "control: pipeline step did not run"; sed -n '1,5p' "$tmp/control.out" >&2; fi
if grep -q 'LEGACY-ONE' "$tmp/control.out"; then
  fail "control: legacy path ran when the runtime was enabled"; else ok; fi
is "control has no killswitch row" \
  "$(kind_count "$(ledger_flat "$tmp/proj-control")" killswitch)" 0

# --------------------------------------- 2. ~/.sutra-runtime-disabled file --
mkdir -p "$tmp/home-file"
: > "$tmp/home-file/.sutra-runtime-disabled"
run_case ksfile "$tmp/proj-ksfile" "$tmp/home-file"
is "killswitch-file exit" "$rc" 0
if cmp -s "$tmp/ksfile.out" "$tmp/want.legacy"; then ok; else
  fail "killswitch-file: stdout is not the legacy output"
  diff -u "$tmp/want.legacy" "$tmp/ksfile.out" | sed -n '1,10p' >&2; fi
is "killswitch-file ledger row" \
  "$(kind_count "$(ledger_flat "$tmp/proj-ksfile")" killswitch)" 1
is "killswitch-file ran no pipeline step" \
  "$(kind_count "$(ledger_flat "$tmp/proj-ksfile")" step)" 0

# ----------------------------------------- 3. SUTRA_RUNTIME_DISABLED=1 env --
run_case ksenv "$tmp/proj-ksenv" "$tmp/home-env" SUTRA_RUNTIME_DISABLED=1
is "killswitch-env exit" "$rc" 0
if cmp -s "$tmp/ksenv.out" "$tmp/want.legacy"; then ok; else
  fail "killswitch-env: stdout is not the legacy output"
  diff -u "$tmp/want.legacy" "$tmp/ksenv.out" | sed -n '1,10p' >&2; fi
is "killswitch-env ledger row" \
  "$(kind_count "$(ledger_flat "$tmp/proj-ksenv")" killswitch)" 1

# ------------------------------------------------------- 4. jq unavailable --
# A PATH holding only what the degraded path may use. jq is not in the list, so
# `command -v jq` fails inside sutra-turn while the test's own jq still works.
nojq="$tmp/nojq-bin"; mkdir -p "$nojq"
for c in sh bash cat sed grep egrep awk tr head tail cut sort uniq wc shasum sha256sum \
         openssl date sleep mkdir rmdir rm mv cp ln chmod cmp diff dirname basename \
         mktemp ls env expr id kill printf test true false; do
  p="$(command -v "$c" 2>/dev/null)" || continue
  [ -n "$p" ] && [ -x "$p" ] || continue
  ln -sf "$p" "$nojq/$c" 2>/dev/null || true
done
if [ -x "$nojq/sh" ] && [ -x "$nojq/sed" ] && [ -x "$nojq/shasum" ] && [ ! -e "$nojq/jq" ]; then
  ok
else
  fail "no-jq PATH not buildable (sh/sed/shasum missing, or jq leaked in)"
fi

run_case nojq "$tmp/proj-nojq" "$tmp/home-nojq" PATH="$nojq"
is "no-jq exit" "$rc" 0
is "no-jq first line" "$(head -1 "$tmp/nojq.out")" "sutra runtime degraded: jq unavailable"
if cmp -s "$tmp/nojq.out" "$tmp/want.degraded"; then ok; else
  fail "no-jq: stdout is not the fixed line followed by the legacy output"
  diff -u "$tmp/want.degraded" "$tmp/nojq.out" | sed -n '1,10p' >&2; fi
is "no-jq ledger row" \
  "$(kind_count "$(ledger_flat "$tmp/proj-nojq")" jq_failed)" 1
# the hand-rolled row must still be valid JSON - it is written without jq
bad=0
while IFS= read -r line; do
  printf '%s' "$line" | jq -e . >/dev/null 2>&1 || bad=$((bad+1))
done < "$(ledger_flat "$tmp/proj-nojq")"
is "no-jq ledger rows are valid JSON" "$bad" 0

# ------------------------------- 5. the fallback never re-enters the runtime --
# The .step3 snapshot carries one self-registration. It must be refused, by
# name, with a ledger row - not silently skipped and not executed.
is "killswitch-file refused the sutra-turn registration" \
  "$(kind_count "$(ledger_flat "$tmp/proj-ksfile")" legacy_skip)" 1
skipped="$(jq -sr '[.[] | select(.kind=="legacy_skip")][0].note // ""' \
  "$(ledger_flat "$tmp/proj-ksfile")" 2>/dev/null)"
case "$skipped" in
  *bin/sutra-turn*) ok ;;
  *) fail "legacy_skip row does not name the refused command: [$skipped]" ;;
esac

# ------------------- 6. no .step3 snapshot: hooks.json, and it is ALL runtime --
# An install that never took a snapshot falls back to the collapsed hooks.json.
# Every one of its registrations is sutra-turn or sutra-canary, so the correct
# behaviour is to refuse them all and run nothing - never to recurse.
#
# AND TO SAY SO. Silence here is the worst failure this program can have: the
# kill-switch is set, ZERO governance hooks run, and the turn exits 0 as if all
# were well. The packaging fault must therefore announce itself on stdout with
# one fixed line and leave a kind=legacy_registry_missing row - while still
# never blocking the host, because the fault is ours, not the caller's.
mv "$fake/hooks/hooks.json.step3" "$tmp/step3.saved"
run_case nostep3 "$tmp/proj-nostep3" "$tmp/home-nostep3" SUTRA_RUNTIME_DISABLED=1
is "no-snapshot exit" "$rc" 0
is "no-snapshot says the registry is missing, on fd 2" "$(cat "$tmp/nostep3.err")" \
  "sutra runtime degraded: legacy registry missing"
is "no-snapshot stdout stays clean" "$(wc -c < "$tmp/nostep3.out" | tr -d ' ')" 0
is "no-snapshot ledger row" \
  "$(kind_count "$(ledger_flat "$tmp/proj-nostep3")" legacy_registry_missing)" 1
is "no-snapshot refused both runtime registrations" \
  "$(kind_count "$(ledger_flat "$tmp/proj-nostep3")" legacy_skip)" 2
is "no-snapshot ran no legacy hook" \
  "$(grep -c 'LEGACY' "$tmp/nostep3.out" 2>/dev/null || true)" 0
mv "$tmp/step3.saved" "$fake/hooks/hooks.json.step3"

# 6b. a snapshot that registers NOTHING for this event is the same fault: the
# line is printed once, the row is written once, and the exit is still 0.
cat > "$tmp/empty-step3.json" <<'EMPTY'
{ "hooks": { "Stop": [] } }
EMPTY
cp "$fake/hooks/hooks.json.step3" "$tmp/step3.saved2"
cp "$tmp/empty-step3.json" "$fake/hooks/hooks.json.step3"
run_case emptyreg "$tmp/proj-emptyreg" "$tmp/home-emptyreg" SUTRA_RUNTIME_DISABLED=1
is "empty-registry exit" "$rc" 0
is "empty-registry says the registry is missing, on fd 2" "$(cat "$tmp/emptyreg.err")" \
  "sutra runtime degraded: legacy registry missing"
is "empty-registry ledger row" \
  "$(kind_count "$(ledger_flat "$tmp/proj-emptyreg")" legacy_registry_missing)" 1
cp "$tmp/step3.saved2" "$fake/hooks/hooks.json.step3"

# --------------------- 6b. a COMPACT snapshot still yields its registrations --
# The jq-less registry reader used to be a LINE-SHAPE guess: it matched the line
# that opens an event array and took the first quoted token on it. A snapshot
# written by `jq -c` puts the whole registry on ONE line, so that token was
# "hooks", no event ever matched, and a kill-switched fleet without jq ran
# nothing at all - silently. The reader is now a structural scan, so the same
# registry in compact form must produce exactly the same legacy output.
compact="$tmp/step3.compact.json"
jq -c . "$fake/hooks/hooks.json.step3" > "$compact"
is "the compact snapshot really is one line" "$(wc -l < "$compact" | tr -d ' ')" 1
cp "$fake/hooks/hooks.json.step3" "$tmp/step3.saved3"
cp "$compact" "$fake/hooks/hooks.json.step3"
run_case compact "$tmp/proj-compact" "$tmp/home-compact" PATH="$nojq"
is "compact-snapshot exit" "$rc" 0
if cmp -s "$tmp/compact.out" "$tmp/want.degraded"; then ok; else
  fail "compact-snapshot: the jq-less reader lost the registrations"
  diff -u "$tmp/want.degraded" "$tmp/compact.out" | sed -n '1,10p' >&2; fi
is "compact-snapshot still refused the sutra-turn registration" \
  "$(kind_count "$(ledger_flat "$tmp/proj-compact")" legacy_skip)" 1
cp "$tmp/step3.saved3" "$fake/hooks/hooks.json.step3"

# ------------------------------------- 7. every step's stderr reaches fd 2 --
# Behaviour-identity is not only about stdout. Under the legacy host each hook
# owned the terminal's fd 2, so advisory nudges printed there were seen even on
# a turn that was ultimately blocked. Parity measured 456 lost stderr diffs when
# only the blocking step's stderr survived.
printf '{"session_id":"%s","hook_event_name":"PreToolUse","tool_name":"Edit"}' "$sid" \
  > "$tmp/pre.json"
mkdir -p "$tmp/proj-stderr/.claude" "$tmp/proj-stderr/.sutra" "$tmp/proj-stderr/.enforcement" \
  "$tmp/home-stderr"
env CLAUDE_PLUGIN_ROOT="$fake" CLAUDE_PROJECT_DIR="$tmp/proj-stderr" HOME="$tmp/home-stderr" \
  "$fake/bin/sutra-turn" run --event PreToolUse \
  < "$tmp/pre.json" > "$tmp/stderr.out" 2> "$tmp/stderr.err"
rc=$?
printf 'ADV-ONE\nADV-TWO\nDENY-THREE\n' > "$tmp/want.stderr"
is "stderr case exit" "$rc" 2
if cmp -s "$tmp/stderr.err" "$tmp/want.stderr"; then ok; else
  fail "fd 2 does not carry all three messages in step order"
  diff -u "$tmp/want.stderr" "$tmp/stderr.err" | sed -n '1,10p' >&2; fi

# ============== 8. a plugin root with a SPACE in it, and one with '&' in it --
# The fallback expanded ${CLAUDE_PLUGIN_ROOT} through `sed "s|...|$PLUGIN_ROOT|"`
# and then split the result on spaces. A root under "/tmp/with space" became two
# words, argv[0] was not an executable file, `[ -x "$1" ] || continue` dropped
# the registration - and the ENTIRE kill-switch path then ran zero hooks,
# printed nothing and exited 0. A root containing '&' was corrupted by sed
# itself (the matched text pasted back in); one containing '|' or '\' ended or
# ate the s/// command. Both roots must behave exactly like an ordinary one, on
# a TMPDIR that has a space in it too.
mkroot() {  # <root dir> - a second throw-away plugin, registry and all
  _mr="$1"
  mkdir -p "$_mr/bin" "$_mr/runtime" "$_mr/hooks"
  cp "$turn" "$_mr/bin/sutra-turn"; chmod 0755 "$_mr/bin/sutra-turn"
  cp "$runtime/shim.sh" "$runtime/ledger.sh" "$_mr/runtime/"
  cp "$fake/runtime/pipeline.json" "$_mr/runtime/pipeline.json"
  cp "$fake/hooks/hooks.json.step3" "$_mr/hooks/hooks.json.step3"
  cp "$fake/hooks/probe.sh" "$_mr/hooks/probe.sh"; chmod 0755 "$_mr/hooks/probe.sh"
  mkhook "$_mr/hooks/legacy-one.sh" "LEGACY-ONE"
  mkhook "$_mr/hooks/legacy-two.sh" "LEGACY-TWO"
}

spacetmp="$tmp/tmp with space"; mkdir -p "$spacetmp"
ri=0
for rootname in "with space/plug root" "amp&root" 'pipe|back\slash'; do
  ri=$((ri+1))
  root="$tmp/$rootname"
  mkroot "$root"
  rproj="$tmp/proj-root$ri"; rhome="$tmp/home-root$ri"
  mkdir -p "$rproj/.claude" "$rproj/.sutra" "$rproj/.enforcement" "$rhome"
  : > "$rhome/.sutra-runtime-disabled"
  env CLAUDE_PLUGIN_ROOT="$root" CLAUDE_PROJECT_DIR="$rproj" HOME="$rhome" \
      TMPDIR="$spacetmp" \
    "$root/bin/sutra-turn" run --event UserPromptSubmit \
    < "$tmp/stdin.json" > "$tmp/root$ri.out" 2> "$tmp/root$ri.err"
  rc=$?
  is "root [$rootname] exit" "$rc" 0
  if cmp -s "$tmp/root$ri.out" "$tmp/want.legacy"; then ok; else
    fail "root [$rootname]: the kill-switch path did not run the legacy hooks"
    diff -u "$tmp/want.legacy" "$tmp/root$ri.out" | sed -n '1,6p' >&2; fi
  is "root [$rootname] still refused the self-registration" \
    "$(kind_count "$(ledger_flat "$rproj")" legacy_skip)" 1
  is "root [$rootname] wrote no legacy_not_executable row" \
    "$(kind_count "$(ledger_flat "$rproj")" legacy_not_executable)" 0
done

# ... and the RUNTIME path is fine on such a root too (the control for the three
# cases above: without it, a runtime that failed everywhere would pass them).
rproj="$tmp/proj-rootctl"; mkdir -p "$rproj/.claude" "$rproj/.sutra" "$rproj/.enforcement"
env CLAUDE_PLUGIN_ROOT="$tmp/with space/plug root" CLAUDE_PROJECT_DIR="$rproj" \
    HOME="$tmp/home-rootctl" TMPDIR="$spacetmp" \
  "$tmp/with space/plug root/bin/sutra-turn" run --event UserPromptSubmit \
  < "$tmp/stdin.json" > "$tmp/rootctl.out" 2> "$tmp/rootctl.err"
is "a spaced root on the runtime path still runs its step" \
  "$(grep -c 'RUNTIME-PROBE' "$tmp/rootctl.out" 2>/dev/null || true)" 1

# ======== 9. a legacy hook that cannot be executed is a FAULT, never a no-op --
# `[ -x "$1" ] || continue` dropped it with no ledger row and no stderr, and the
# turn was then recorded kind=no_match with a note claiming the matcher had not
# matched. A plugin that lost an x-bit ran no governance under the kill-switch
# and the ledger asserted a clean turn.
nx="$tmp/plugin-notexec"
mkroot "$nx"
chmod 0644 "$nx/hooks/legacy-two.sh"
nxproj="$tmp/proj-notexec"; nxhome="$tmp/home-notexec"
mkdir -p "$nxproj/.claude" "$nxproj/.sutra" "$nxproj/.enforcement" "$nxhome"
: > "$nxhome/.sutra-runtime-disabled"
env CLAUDE_PLUGIN_ROOT="$nx" CLAUDE_PROJECT_DIR="$nxproj" HOME="$nxhome" \
  "$nx/bin/sutra-turn" run --event UserPromptSubmit \
  < "$tmp/stdin.json" > "$tmp/notexec.out" 2> "$tmp/notexec.err"
rc=$?
is "0644 legacy hook exit" "$rc" 0
is "the executable registration still ran" "$(cat "$tmp/notexec.out")" "LEGACY-ONE"
is "the refusal is a ledger row" \
  "$(kind_count "$(ledger_flat "$nxproj")" legacy_not_executable)" 1
is "the row names the hook" \
  "$(jq -sr '[.[]|select(.kind=="legacy_not_executable")][0].note | test("legacy-two.sh")' \
     "$(ledger_flat "$nxproj")" 2>/dev/null)" "true"
is "one fixed line on fd 2" \
  "$(grep -c '^sutra runtime degraded: legacy hook not executable .*legacy-two.sh$' \
     "$tmp/notexec.err" 2>/dev/null || true)" 1
is "and NO no_match row, because the matcher did match" \
  "$(kind_count "$(ledger_flat "$nxproj")" no_match)" 0

printf 'test-runtime-killswitch: checks=%s failed=%s\n' "$checks" "$failed"
[ "$failed" -eq 0 ]
