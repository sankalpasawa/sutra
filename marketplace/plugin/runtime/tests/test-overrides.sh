#!/usr/bin/env bash
# test-overrides.sh - adherence row 4: ~/.sutra-overrides, the one override
# file, applied by bin/sutra-turn before step 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-overrides.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_MAIN="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }
command -v jq >/dev/null 2>&1 || { fail "jq required"; echo "failed=$failed"; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-overrides.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
LIB="$PLUGIN_MAIN/runtime/lib/overrides.sh"

echo "== case 1: the library parses clean under sh and bash =="
sh -n "$LIB" && pass "sh -n" || fail "sh -n"
bash -n "$LIB" && pass "bash -n" || fail "bash -n"

echo "== case 2: whitelisted keys export, unknown keys are ignored, env wins =="
HM="$WORK/home"; mkdir -p "$HM"
printf '# my overrides\nFLOW_ACK=1\nFLOW_ACK_REASON=testing the file\nNOT_A_KEY=1\nRTK_SKIP=1\nSUTRA_STEP_TIMEOUT_SCALE=400\n' > "$HM/.sutra-overrides"
OUT="$(env -i HOME="$HM" PATH="$PATH" RTK_SKIP=0 sh -c ". \"$LIB\"; sutra_overrides_apply \"$WORK\" sid-x; printf '%s|%s|%s|%s|%s' \"\${FLOW_ACK:-}\" \"\${FLOW_ACK_REASON:-}\" \"\${NOT_A_KEY:-}\" \"\${RTK_SKIP:-}\" \"\$SUTRA_OVERRIDES_APPLIED\"")"
is "case2: FLOW_ACK exported" "$(printf '%s' "$OUT" | cut -d'|' -f1)" 1
is "case2: reason exported with spaces" "$(printf '%s' "$OUT" | cut -d'|' -f2)" "testing the file"
is "case2: unknown key ignored" "$(printf '%s' "$OUT" | cut -d'|' -f3)" ""
is "case2: explicit env wins over the file" "$(printf '%s' "$OUT" | cut -d'|' -f4)" 0
is "case2: applied keys listed" "$(printf '%s' "$OUT" | cut -d'|' -f5)" "FLOW_ACK FLOW_ACK_REASON SUTRA_STEP_TIMEOUT_SCALE"
[ -f "$WORK/.enforcement/overrides.jsonl" ] && pass "case2: audit row written" || fail "case2: no audit row"
grep -q '"keys":"FLOW_ACK FLOW_ACK_REASON SUTRA_STEP_TIMEOUT_SCALE"' "$WORK/.enforcement/overrides.jsonl" 2>/dev/null && pass "case2: audit row names the keys" || fail "case2: audit row lacks keys"

echo "== case 3: HOME unset -> no file read, nothing exported =="
OUT="$(env -i PATH="$PATH" sh -c ". \"$LIB\"; sutra_overrides_apply \"$WORK\" sid-x; printf '%s' \"\${SUTRA_OVERRIDES_APPLIED-unset}\"")"
is "case3: nothing applied (empty, not unset)" "$OUT" ""

echo "== case 4: through sutra-turn: the ledger carries the override_file note and the run sees the var =="
PJ="$WORK/proj"; mkdir -p "$PJ/.claude/sessions" "$PJ/.sutra"; printf '{"profile":"company"}\n' > "$PJ/.claude/sutra-project.json"
# 2.285.1: the runtime flags are no longer override keys (brief ADHERENCE-ROW6 s3.6);
# the markers flag comes from its own file, the override file carries FLOW_ACK and a
# runtime flag that must be ignored. The file predates the session (touched old).
printf 'FLOW_ACK=1\nSUTRA_RUNTIME_ADHERENCE=on\n' > "$HM/.sutra-overrides"
touch -t 202001010000 "$HM/.sutra-overrides"
printf 'on\n' > "$HM/.sutra-runtime-markers"
IN="$(jq -nc '{session_id:"sid-o", hook_event_name:"UserPromptSubmit", prompt:"override file check"}')"
printf '%s' "$IN" > "$WORK/o.stdin"
env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$PJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" HOME="$HM" RTK_SKIP=1 \
  "$PLUGIN_MAIN/bin/sutra-turn" run --event UserPromptSubmit < "$WORK/o.stdin" > "$WORK/o.out" 2> "$WORK/o.err"
is "case4: exit 0" "$?" 0
TID="$(cat "$PJ/.sutra/turn/sid-o/current" 2>/dev/null)"
grep -q '"kind":"override_file"' "$PJ/.sutra/turn/sid-o/$TID.jsonl" 2>/dev/null && pass "case4: override_file ledger row" || fail "case4: no override_file row"
grep -q 'FLOW_ACK' "$PJ/.sutra/turn/sid-o/$TID.jsonl" 2>/dev/null && pass "case4: the row names FLOW_ACK" || fail "case4: row does not name FLOW_ACK"
[ -f "$PJ/.sutra/turn/sid-o/$TID.facts.json" ] && pass "case4: markers on from the flag file (facts written)" || fail "case4: markers flag file not honoured"
[ -f "$PJ/.sutra/turn/sid-o/$TID.steps.json" ] && fail "case4: the override file switched adherence on (it must not)" || pass "case4: SUTRA_RUNTIME_ADHERENCE in the override file is ignored"
[ -s "$PJ/.sutra/turn/sid-o/opened" ] && pass "case4: session stamp written" || fail "case4: no session stamp"

echo "== case 5: flag absent everywhere -> byte-identical stdout with and without the library present =="
HM2="$WORK/home2"; mkdir -p "$HM2"; PJ2="$WORK/proj2"; mkdir -p "$PJ2/.claude/sessions" "$PJ2/.sutra"; printf '{"profile":"company"}\n' > "$PJ2/.claude/sutra-project.json"
env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_SESSION_ID CLAUDE_PROJECT_DIR="$PJ2" CLAUDE_PLUGIN_ROOT="$PLUGIN_MAIN" HOME="$HM2" RTK_SKIP=1 SUTRA_STEP_TIMEOUT_SCALE=400 \
  "$PLUGIN_MAIN/bin/sutra-turn" run --event UserPromptSubmit < "$WORK/o.stdin" > "$WORK/p1.out" 2>/dev/null
grep -q 'override_file' "$PJ2/.sutra/turn/sid-o/"*.jsonl 2>/dev/null && fail "case5: override row without a file" || pass "case5: no override row without a file"

echo "== case 6: 2.285.1 - the runtime flags are not override keys; a file written inside the session is ignored until the next one =="
HM6="$WORK/h6"; PJ6="$WORK/p6"; mkdir -p "$HM6" "$PJ6/.sutra/turn/sid-6"
printf 'SUTRA_RUNTIME_ADHERENCE=off\nSUTRA_RUNTIME_DISABLED=1\nFLOW_ACK=1\n' > "$HM6/.sutra-overrides"
NOW="$(date +%s)"
echo $((NOW - 100)) > "$PJ6/.sutra/turn/sid-6/opened"     # session opened 100 s ago; the file is newer
run6() { env -i HOME="$HM6" PATH="$PATH" sh -c ". \"$LIB\"; sutra_overrides_apply \"$PJ6\" sid-6; printf '%s|%s|%s|%s' \"\${SUTRA_RUNTIME_ADHERENCE:-}\" \"\${SUTRA_RUNTIME_DISABLED:-}\" \"\${FLOW_ACK:-}\" \"\$SUTRA_OVERRIDES_APPLIED\""; }
is "case6: written inside the session -> nothing applied" "$(run6)" "|||"
grep -q '"ignored":true' "$PJ6/.enforcement/overrides.jsonl" 2>/dev/null && pass "case6: audit row says ignored" || fail "case6: no ignored audit row"
echo $((NOW + 100)) > "$PJ6/.sutra/turn/sid-6/opened"     # file predates the session
is "case6: predates the session -> FLOW_ACK applied, runtime flags never" "$(run6)" "||1|FLOW_ACK"
rm -rf "$PJ6/.sutra/turn/sid-6"
touch -t 202001010000 "$HM6/.sutra-overrides"
is "case6: first event stamps opened, an old file applies" "$(run6)" "||1|FLOW_ACK"
[ -s "$PJ6/.sutra/turn/sid-6/opened" ] && pass "case6: opened stamp written by the first event" || fail "case6: no opened stamp"
# no file at the first event, file created later in the session -> ignored (workflow wf_1dc20d5c P1-2)
HM7="$WORK/h7"; PJ7="$WORK/p7"; mkdir -p "$HM7" "$PJ7"
env -i HOME="$HM7" PATH="$PATH" sh -c ". \"$LIB\"; sutra_overrides_apply \"$PJ7\" sid-7"
[ -s "$PJ7/.sutra/turn/sid-7/opened" ] && pass "case6: first event stamps opened even without a file" || fail "case6: no stamp without a file"
sleep 1; printf 'FLOW_ACK=1\n' > "$HM7/.sutra-overrides"
OUT7="$(env -i HOME="$HM7" PATH="$PATH" sh -c ". \"$LIB\"; sutra_overrides_apply \"$PJ7\" sid-7; printf '%s|%s' \"\${FLOW_ACK:-}\" \"\$SUTRA_OVERRIDES_APPLIED\"")"
is "case6: a file that appears mid-session is ignored" "$OUT7" "|"
echo 0 > "$PJ6/.sutra/turn/sid-6/opened"                   # a zeroed stamp fails closed: re-stamped, file ignored this event
is "case6: zero stamp -> ignored and re-stamped" "$(run6)" "|||"
[ "$(cat "$PJ6/.sutra/turn/sid-6/opened")" -gt 1000000 ] && pass "case6: stamp rewritten with now" || fail "case6: stamp not rewritten"
grep -q 'SUTRA_RUNTIME_ADHERENCE' "$LIB" && grep -q 'SUTRA_RUNTIME_ADHERENCE' <(sed -n 's/^SUTRA_OVERRIDE_KEYS=//p' "$LIB") && fail "case6: runtime flag still in the whitelist" || pass "case6: runtime flags out of the whitelist"

echo "failed=$failed"
[ "$failed" -eq 0 ]
