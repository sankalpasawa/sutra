#!/bin/bash
# Unit test: hooks/blueprint-text-validate.sh — A4 BLUEPRINT block TEXT validation.
#
# Builds synthetic transcripts (human row + assistant text with/without a valid
# BLUEPRINT block), feeds a PreToolUse payload, asserts exit code + reason.

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
HOOK="$PLUGIN_ROOT/hooks/blueprint-text-validate.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

VALID_BLOCK='+-- BLUEPRINT --------------------------------------------------+
| Doing: add a new charter section for X                        |
| Steps:                                                         |
|   1) edit the charter       Verify: grep finds new section    |
|   2) run the parity check   Verify: bash verify.sh exits 0    |
| Output looks like: charter has a new ## X section, parity green|
| Verified by (overall): bash tests/run-all.sh exits 0          |
| Scale: 1 file, 20 min                                         |
| Stops if: parity check fails twice                            |
| Switch: ON                                                    |
+---------------------------------------------------------------+'

# Run the hook with a synthetic turn. Args: <rel_path> <assistant_text> <depth> [env...]
# Echoes "exit=<code>" and stderr is captured to $RUN_ERR.
RUN_ERR=""
run_case() {
  local rel="$1" atext="$2" depth="$3"; shift 3
  local D; D=$(mktemp -d -t bptv-XXXXXX)
  mkdir -p "$D/.claude" "$D/sutra/os/charters" "$D/holding"
  printf 'DEPTH=%s TASK=test TS=1782489000\n' "$depth" > "$D/.claude/depth-registered"
  local TR="$D/transcript.jsonl"
  # human user row + assistant text row
  jq -nc --arg t "do the task" '{type:"user",message:{role:"user",content:$t}}' > "$TR"
  jq -nc --arg t "$atext" '{type:"assistant",message:{role:"assistant",content:[{type:"text",text:$t}]}}' >> "$TR"
  local PAYLOAD
  PAYLOAD=$(jq -nc --arg fp "$D/$rel" --arg tr "$TR" '{tool_input:{file_path:$fp},transcript_path:$tr}')
  RUN_ERR="$D/err.txt"
  printf '%s' "$PAYLOAD" | env CLAUDE_PROJECT_DIR="$D" "$@" bash "$HOOK" 2>"$RUN_ERR"
  echo "exit=$?"
  # caller may inspect $RUN_ERR; cleanup deferred to trap
  echo "$D"
}

# helper: assert exit code; arg1=label arg2=expected_exit arg3=run_output(2 lines)
assert_exit() {
  local label="$1" want="$2" out="$3"
  local got; got=$(printf '%s\n' "$out" | sed -n 's/^exit=//p' | head -1)
  if [ "$got" = "$want" ]; then _ok "$label (exit $got)"; else _no "$label: expected exit $want, got $got"; fi
}

FOUND="sutra/os/charters/foo.md"

# 1) valid block on foundational path, D5 -> pass (0)
OUT=$(run_case "$FOUND" "$VALID_BLOCK" 5); assert_exit "valid block passes" 0 "$OUT"

# 2) no blueprint block at all -> block (2)
OUT=$(run_case "$FOUND" "Sure, editing the charter now." 5); assert_exit "missing block blocks" 2 "$OUT"

# 3) empty Doing -> block
BAD_DOING="${VALID_BLOCK/Doing: add a new charter section for X/Doing:}"
OUT=$(run_case "$FOUND" "$BAD_DOING" 5); assert_exit "empty Doing blocks" 2 "$OUT"

# 4) missing Output looks like -> block
NO_OUT="${VALID_BLOCK/| Output looks like: charter has a new ## X section, parity green|/}"
OUT=$(run_case "$FOUND" "$NO_OUT" 5); assert_exit "missing Output field blocks" 2 "$OUT"

# 5) trivial Verified by ("works") -> block
TRIV="${VALID_BLOCK/Verified by (overall): bash tests\/run-all.sh exits 0/Verified by (overall): works}"
OUT=$(run_case "$FOUND" "$TRIV" 5); assert_exit "trivial Verified-by blocks" 2 "$OUT"

# 6) missing per-step Verify at D5 -> block
NOVERIFY="${VALID_BLOCK/   1) edit the charter       Verify: grep finds new section/   1) edit the charter}"
OUT=$(run_case "$FOUND" "$NOVERIFY" 5); assert_exit "missing per-step Verify (D5) blocks" 2 "$OUT"

# 7) non-foundational path with a BAD block -> skip/pass (0) in slice-1 foundational scope
OUT=$(run_case "holding/notes.md" "no blueprint here at all" 5); assert_exit "non-foundational path skipped" 0 "$OUT"

# 8) kill-switch -> pass (0) even with missing block
OUT=$(run_case "$FOUND" "no blueprint here" 5 BLUEPRINT_TEXT_VALIDATE_DISABLED=1); assert_exit "kill-switch disables" 0 "$OUT"

# 9) BLUEPRINT_ACK override -> pass (0)
OUT=$(run_case "$FOUND" "no blueprint here" 5 BLUEPRINT_ACK=1); assert_exit "BLUEPRINT_ACK override passes" 0 "$OUT"

# 10) missing per-step Verify but D2 (below D3) -> pass (0)
OUT=$(run_case "$FOUND" "$NOVERIFY" 2); assert_exit "missing per-step Verify at D2 passes" 0 "$OUT"

# 11) reason code surfaced on stderr for trivial-verify case
D11=$(mktemp -d -t bptv-r-XXXXXX); mkdir -p "$D11/.claude" "$D11/sutra/os/charters"
printf 'DEPTH=5 TASK=test TS=1782489000\n' > "$D11/.claude/depth-registered"
jq -nc '{type:"user",message:{role:"user",content:"go"}}' > "$D11/t.jsonl"
jq -nc --arg t "$TRIV" '{type:"assistant",message:{role:"assistant",content:[{type:"text",text:$t}]}}' >> "$D11/t.jsonl"
ERR=$(printf '%s' "$(jq -nc --arg fp "$D11/$FOUND" --arg tr "$D11/t.jsonl" '{tool_input:{file_path:$fp},transcript_path:$tr}')" | CLAUDE_PROJECT_DIR="$D11" bash "$HOOK" 2>&1 1>/dev/null)
if printf '%s' "$ERR" | grep -qi "trivial"; then _ok "trivial-verify repair message mentions the problem"; else _no "repair message missing trivial detail: $ERR"; fi

echo ""
echo "blueprint-text-validate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
