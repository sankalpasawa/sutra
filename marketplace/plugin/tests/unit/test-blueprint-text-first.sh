#!/bin/bash
# Unit test: hooks/blueprint-check.sh v3 — TEXT-FIRST enforcement.
#
# Covers the #68 + 2026-07-08 field-incident fix:
#   - a valid BLUEPRINT in the turn TEXT passes with no marker present
#   - ordinary (non-foundational) files are no longer gated here at all
#   - foundational field rules (Output / Verified by / per-step Verify) survive,
#     just read from the text instead of marker flags
#   - the marker is written BY the hook as a per-turn cache
#   - degraded mode (no transcript) falls back to the legacy marker check
#   - #80's out-of-repo guard, the whitelist, override and kill-switch still hold
#
# Builds a synthetic transcript (human row + assistant text [+ tool_use rows])
# and feeds a PreToolUse payload, asserting exit code + side effects.

set -u
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/hooks/blueprint-check.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }

command -v jq >/dev/null 2>&1      || { echo "SKIP: jq not installed"; exit 0; }
command -v python3 >/dev/null 2>&1 || { echo "SKIP: python3 not installed"; exit 0; }

GOOD_BP='BLUEPRINT
- Doing: rewrite the enforcement path of the blueprint gate
- Steps: 1) port the text validator  Verify: bash tests/unit/test-blueprint-text-first.sh
- Output looks like: hooks/blueprint-check.sh reads the turn text, tests green
- Verified by: bash tests/unit/test-blueprint-text-first.sh exits 0
- Scale: 4 files
- Stops if: the suite cannot reach green'

BP_TRIVIAL_VERIFY='BLUEPRINT
- Doing: rewrite the gate
- Output looks like: hooks/blueprint-check.sh reads the turn text
- Verified by: works'

BP_NO_OUTPUT='BLUEPRINT
- Doing: rewrite the gate
- Verified by: bash tests/unit/test-blueprint-text-first.sh exits 0'

BP_BOX='+-- BLUEPRINT ------------------------------------------------+
| Doing: rewrite the enforcement path of the blueprint gate    |
| Output looks like: the hook reads the turn text, tests green |
| Verified by: bash tests/unit/test-blueprint-text-first.sh    |
+--------------------------------------------------------------+'

BP_HEADING='## BLUEPRINT
Doing: rewrite the enforcement path of the blueprint gate
Output looks like: the hook reads the turn text, tests green
Verified by: bash tests/unit/test-blueprint-text-first.sh exits 0'

BP_D3_BAD_STEPS='BLUEPRINT
- Doing: rewrite the gate
- Steps: 1) port the validator 2) wire the Stop floor
- Output looks like: the hook reads the turn text, tests green
- Verified by: bash tests/unit/test-blueprint-text-first.sh exits 0'

# make_env <depth|none> <assistant_text> -> echoes a temp dir
make_env(){
  local depth="$1" text="$2"
  local D; D=$(mktemp -d)
  mkdir -p "$D/.claude" "$D/sutra/os/charters" "$D/src" "$D/holding"
  printf '{"project_id":"test"}\n' > "$D/.claude/sutra-project.json"
  [ "$depth" != none ] && printf 'DEPTH=%s TASK=t TS=1730000000\n' "$depth" > "$D/.claude/depth-registered"
  {
    printf '{"type":"user","message":{"role":"user","content":"do the thing"}}\n'
    if [ -n "$text" ]; then
      python3 -c 'import json,sys; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":sys.stdin.read()}]}}))' <<< "$text"
    fi
  } > "$D/transcript.jsonl"
  echo "$D"
}

# run <dir> <rel_path> [extra_env...] -> sets RC + ERR
RC=0; ERR=""
run(){
  local D="$1" rel="$2"; shift 2
  local err="$D/err"
  printf '{"tool_name":"Write","tool_input":{"file_path":"%s"},"transcript_path":"%s"}' \
    "$D/$rel" "$D/transcript.jsonl" \
  | env "$@" CLAUDE_PROJECT_DIR="$D" bash "$HOOK" 2>"$err" >/dev/null
  RC=$?; ERR=$(cat "$err")
}

# run_no_transcript <dir> <rel_path> -> degraded mode
run_no_transcript(){
  local D="$1" rel="$2"
  local err="$D/err"
  printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$D/$rel" \
  | CLAUDE_PROJECT_DIR="$D" bash "$HOOK" 2>"$err" >/dev/null
  RC=$?; ERR=$(cat "$err")
}

echo "=== foundational: the emitted TEXT is the contract (the #68 / #80 fix) ==="
D=$(make_env 5 "$GOOD_BP"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "valid BLUEPRINT text + NO marker -> pass (was: hard block)" || no "expected 0 got $RC: $ERR"
grep -q '^VALIDATED_FROM=text$' "$D/.claude/blueprint-registered" 2>/dev/null \
  && ok "hook wrote its own cache marker (VALIDATED_FROM=text)" || no "cache marker not written"
grep -q '^HAS_PER_STEP_VERIFY=1$' "$D/.claude/blueprint-registered" 2>/dev/null \
  && ok "cache records per-step verify at D5" || no "cache missing HAS_PER_STEP_VERIFY at D5"
rm -rf "$D"

D=$(make_env 5 "$BP_BOX");     run "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "ASCII-box BLUEPRINT shape accepted" || no "box shape expected 0 got $RC: $ERR"; rm -rf "$D"
D=$(make_env 5 "$BP_HEADING"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "markdown-heading BLUEPRINT shape accepted" || no "heading shape expected 0 got $RC: $ERR"; rm -rf "$D"

D=$(make_env 5 "no plan here, just prose"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 2 ] && ok "foundational + no BLUEPRINT in text -> blocked" || no "expected 2 got $RC"; rm -rf "$D"

D=$(make_env 5 "$BP_TRIVIAL_VERIFY"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 2 ] && ok "trivial 'Verified by: works' -> blocked" || no "expected 2 got $RC"
printf '%s' "$ERR" | grep -q 'Verified by' && ok "error names the offending field" || no "error not field-specific: $ERR"; rm -rf "$D"

D=$(make_env 5 "$BP_NO_OUTPUT"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 2 ] && ok "missing 'Output looks like' -> blocked (D48 preserved)" || no "expected 2 got $RC"; rm -rf "$D"

D=$(make_env 3 "$BP_D3_BAD_STEPS"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 2 ] && ok "D3 numbered Step without inline Verify -> blocked (V2.2 preserved)" || no "expected 2 got $RC"; rm -rf "$D"
D=$(make_env 2 "$BP_D3_BAD_STEPS"); run "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "same block at D2 -> pass (per-step Verify is D3+ only)" || no "expected 0 got $RC: $ERR"; rm -rf "$D"

echo "=== ordinary files: PreToolUse no longer gates them (Stop floor owns) ==="
D=$(make_env 5 "no plan here"); run "$D" "src/thing.py"
[ "$RC" = 0 ] && ok "ordinary file + no BLUEPRINT + D5 -> pass here" || no "expected 0 got $RC: $ERR"; rm -rf "$D"
D=$(make_env none "no plan here"); run "$D" "src/thing.py"
[ "$RC" = 0 ] && ok "ordinary file + NO depth marker -> pass (no fail-closed tax)" || no "expected 0 got $RC"; rm -rf "$D"

echo "=== per-turn cache short-circuits repeat validation ==="
D=$(make_env 5 "no plan here at all")
printf 'VALIDATED_FROM=text\nHAS_OUTPUT=1\nHAS_VERIFY=1\nHAS_PER_STEP_VERIFY=1\nTS=1\n' > "$D/.claude/blueprint-registered"
run "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "cache hit -> pass without re-reading the transcript" || no "expected 0 got $RC"; rm -rf "$D"

echo "=== project-level foundational override ==="
D=$(make_env 5 "no plan here")
printf '{"project_id":"t","blueprint_foundational_paths":["docs/governance/*.md"]}\n' > "$D/.claude/sutra-project.json"
mkdir -p "$D/docs/governance"
run "$D" "docs/governance/policy.md"
[ "$RC" = 2 ] && ok "custom foundational glob from sutra-project.json is enforced" || no "expected 2 got $RC"
run "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "default globs yield to the project override" || no "expected 0 got $RC: $ERR"; rm -rf "$D"

echo "=== degraded mode (no transcript) falls back to the legacy marker ==="
D=$(make_env 5 "$GOOD_BP"); run_no_transcript "$D" "sutra/os/charters/x.md"
[ "$RC" = 2 ] && ok "no transcript + no marker -> blocked (does not fail open)" || no "expected 2 got $RC"
printf '%s' "$ERR" | grep -qi 'degraded' && ok "degraded mode is named in the error" || no "error does not say degraded: $ERR"
printf 'HAS_OUTPUT=1\nHAS_VERIFY=1\nHAS_PER_STEP_VERIFY=1\nTS=1\n' > "$D/.claude/blueprint-registered"
run_no_transcript "$D" "sutra/os/charters/x.md"
[ "$RC" = 0 ] && ok "no transcript + complete legacy marker -> pass" || no "expected 0 got $RC: $ERR"; rm -rf "$D"

echo "=== preserved guards ==="
D=$(make_env 5 "no plan"); run "$D" ".claude/notes.md"
[ "$RC" = 0 ] && ok "whitelist (.claude/**) exempt" || no "expected 0 got $RC"
run "$D" "holding/checkpoints/2026-07-27.json"
[ "$RC" = 0 ] && ok "whitelist (checkpoints) exempt" || no "expected 0 got $RC"
ERRF="$D/err"
printf '{"tool_name":"Write","tool_input":{"file_path":"%s/outside.md"},"transcript_path":"%s"}' "$HOME" "$D/transcript.jsonl" \
  | CLAUDE_PROJECT_DIR="$D" bash "$HOOK" 2>"$ERRF" >/dev/null
[ "$?" = 0 ] && ok "out-of-repo absolute path exempt (#80 guard intact)" || no "out-of-repo should exit 0"
run "$D" "sutra/os/charters/x.md" BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON=test
[ "$RC" = 0 ] && ok "BLUEPRINT_ACK override passes" || no "ACK failed"
grep -q 'blueprint-override' "$D/.enforcement/blueprint-ledger.jsonl" 2>/dev/null \
  && ok "override is audit-logged" || no "override not logged"
run "$D" "sutra/os/charters/x.md" BLUEPRINT_DISABLED=1
[ "$RC" = 0 ] && ok "BLUEPRINT_DISABLED kill-switch passes" || no "kill-switch failed"
rm -rf "$D"

echo ""
echo "blueprint-text-first: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
