#!/bin/bash
# Unit test: hooks/per-turn-hard-gate.sh — the BLUEPRINT arm (added 2026-07-27).
#
# blueprint-check.sh v3 stopped HARD-blocking ordinary files at PreToolUse and
# kept enforcement for foundational paths only. This Stop floor is where the
# BLUEPRINT contract lands for everything else. It must:
#   - demand a BLUEPRINT only on turns that actually mutated a governed file
#   - stay silent on no-edit turns, whitelist-only turns and out-of-repo writes
#   - honor the BLUEPRINT kill-switches (one switch disarms both layers)
#   - never regress the existing Input Routing / Depth arms or loop safety

set -u
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/hooks/per-turn-hard-gate.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }

command -v jq >/dev/null 2>&1      || { echo "SKIP: jq not installed"; exit 0; }
command -v python3 >/dev/null 2>&1 || { echo "SKIP: python3 not installed"; exit 0; }

GOOD_BLOCKS='INPUT: do the thing
TYPE: task
ROUTE: direct
TASK: "do the thing"
DEPTH: 3/5
EFFORT: 5 min
COST: ~$0.10
IMPACT: one file'

BP='BLUEPRINT
- Doing: change one file
- Output looks like: the file changed
- Verified by: bash tests/unit/test-per-turn-hard-gate-blueprint.sh'

# run <assistant_text> <edited_path_or_empty> [env...] -> sets OUT
OUT=""
run(){
  local text="$1" edited="$2"; shift 2
  local D; D=$(mktemp -d)
  mkdir -p "$D/.claude"
  printf '{"project_id":"test"}\n' > "$D/.claude/sutra-project.json"
  {
    printf '{"type":"user","message":{"role":"user","content":"go"}}\n'
    TXT="$text" python3 -c 'import json,os; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":os.environ["TXT"]}]}}))'
    if [ -n "$edited" ]; then
      # relative -> inside the fake repo; absolute -> deliberately outside it
      case "$edited" in /*) FP_ABS="$edited" ;; *) FP_ABS="$D/$edited" ;; esac
      FP="$FP_ABS" python3 -c 'import json,os; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Write","input":{"file_path":os.environ["FP"]}}]}}))'
    fi
  } > "$D/transcript.jsonl"
  OUT=$(printf '{"session_id":"s","transcript_path":"%s","stop_hook_active":false}' "$D/transcript.jsonl" \
        | env "$@" CLAUDE_PROJECT_DIR="$D" HOME="$D" bash "$HOOK" 2>/dev/null)
  LAST_DIR="$D"
}
is_block(){ printf '%s' "$OUT" | grep -q '"decision": "block"'; }
names_bp(){ printf '%s' "$OUT" | grep -q 'BLUEPRINT'; }

echo "=== BLUEPRINT required only when the turn mutated a governed file ==="
run "$GOOD_BLOCKS" "src/thing.py"
if is_block && names_bp; then ok "edited a source file, no BLUEPRINT -> block naming BLUEPRINT"; else no "expected block: $OUT"; fi
rm -rf "$LAST_DIR"

run "$GOOD_BLOCKS
$BP" "src/thing.py"
if is_block; then no "BLUEPRINT present should pass: $OUT"; else ok "edited a source file WITH a BLUEPRINT -> pass"; fi
rm -rf "$LAST_DIR"

run "$GOOD_BLOCKS" ""
if is_block; then no "no-edit turn should pass: $OUT"; else ok "no edits in the turn -> no BLUEPRINT demanded"; fi
rm -rf "$LAST_DIR"

echo "=== whitelist + out-of-repo mirror blueprint-check.sh ==="
for p in ".claude/depth-registered" "holding/TODO.md" ".enforcement/x.jsonl" "holding/checkpoints/2026-07-27.json"; do
  run "$GOOD_BLOCKS" "$p"
  if is_block; then no "whitelisted path $p should not demand a BLUEPRINT: $OUT"; else ok "whitelisted path exempt: $p"; fi
  rm -rf "$LAST_DIR"
done

run "$GOOD_BLOCKS" "/somewhere/else/outside.md"
if is_block; then no "out-of-repo absolute path should be exempt: $OUT"; else ok "out-of-repo write exempt (#80 parity)"; fi
rm -rf "$LAST_DIR"

echo "=== kill-switches + loop safety ==="
run "$GOOD_BLOCKS" "src/thing.py" BLUEPRINT_DISABLED=1
if is_block; then no "BLUEPRINT_DISABLED should disarm this arm: $OUT"; else ok "BLUEPRINT_DISABLED disarms the Stop arm too"; fi
rm -rf "$LAST_DIR"

run "$GOOD_BLOCKS" "src/thing.py" BLUEPRINT_ACK=1
if is_block; then no "BLUEPRINT_ACK should pass: $OUT"; else ok "BLUEPRINT_ACK passes"; fi
rm -rf "$LAST_DIR"

D=$(mktemp -d); mkdir -p "$D/.claude"; printf '{"project_id":"t"}\n' > "$D/.claude/sutra-project.json"
printf '{"type":"user","message":{"role":"user","content":"go"}}\n' > "$D/transcript.jsonl"
TXT="$GOOD_BLOCKS" python3 -c 'import json,os; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":os.environ["TXT"]}]}}))' >> "$D/transcript.jsonl"
python3 -c 'import json; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Write","input":{"file_path":"src/a.py"}}]}}))' >> "$D/transcript.jsonl"
OUT=$(printf '{"session_id":"s","transcript_path":"%s","stop_hook_active":true}' "$D/transcript.jsonl" \
      | CLAUDE_PROJECT_DIR="$D" HOME="$D" bash "$HOOK" 2>/dev/null)
if is_block; then no "stop_hook_active must never block (loop safety): $OUT"; else ok "stop_hook_active -> pass (one redo max)"; fi
rm -rf "$D"

echo "=== existing arms unregressed ==="
run "TASK: x
DEPTH: 3/5" "src/thing.py"
printf '%s' "$OUT" | grep -q 'Input-Routing' && ok "Input Routing arm still fires" || no "Input Routing arm lost: $OUT"
rm -rf "$LAST_DIR"
run "INPUT: x
TYPE: task
$BP" "src/thing.py"
printf '%s' "$OUT" | grep -q 'Depth' && ok "Depth arm still fires" || no "Depth arm lost: $OUT"
rm -rf "$LAST_DIR"

echo ""
echo "per-turn-hard-gate-blueprint: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
