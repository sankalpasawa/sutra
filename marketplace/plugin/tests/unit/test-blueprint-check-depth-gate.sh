#!/bin/bash
# Regression test for blueprint-check.sh #68 fixes:
#   D2 — non-foundational error drops the (foundational-only) Output/Verified-by ask
#   D3 — error text points to a real doc, not the phantom "CLAUDE.md Mandatory Blocks"
#   D4 — non-foundational BLUEPRINT required only at DEPTH>=3 (D<=2 exempt; fail-closed)
set -u
HOOK="$(cd "$(dirname "$0")/../.." && pwd)/hooks/blueprint-check.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }

# run <rel_path> <depth|none> [marker_lines] -> sets RC + ERR
RC=0; ERR=""
run(){
  local rel="$1" depth="$2" marker="${3:-}"
  local D; D=$(mktemp -d)
  mkdir -p "$D/.claude" "$D/sutra/os/charters" "$D/some/dir"
  [ "$depth" != none ] && printf 'DEPTH=%s TASK=t TS=1730000000\n' "$depth" > "$D/.claude/depth-registered"
  [ -n "$marker" ] && printf '%b' "$marker" > "$D/.claude/blueprint-registered"
  local err; err="$D/err"
  printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$D/$rel" \
    | CLAUDE_PROJECT_DIR="$D" bash "$HOOK" 2>"$err" >/dev/null
  RC=$?; ERR=$(cat "$err"); rm -rf "$D"
}

echo "=== D4: non-foundational depth gate ==="
run "some/dir/file.txt" 1        ; [ "$RC" = 0 ] && ok "D1 non-foundational + no marker + DEPTH=1 -> exempt (0)" || no "D=1 expected 0 got $RC"
run "some/dir/file.txt" 2        ; [ "$RC" = 0 ] && ok "non-foundational + no marker + DEPTH=2 -> exempt (0)" || no "D=2 expected 0 got $RC"
run "some/dir/file.txt" 3        ; [ "$RC" = 2 ] && ok "non-foundational + no marker + DEPTH=3 -> blocked (2)" || no "D=3 expected 2 got $RC"
run "some/dir/file.txt" none     ; [ "$RC" = 2 ] && ok "non-foundational + no marker + NO depth -> fail-closed block (2)" || no "no-depth expected 2 got $RC"
run "some/dir/file.txt" 2 "TS=1\nTASK=t\n" ; [ "$RC" = 0 ] && ok "non-foundational + marker + DEPTH=2 -> pass (0)" || no "D2+marker expected 0 got $RC"
run "some/dir/file.txt" 3 "HAS_PER_STEP_VERIFY=1\nTS=1\nTASK=t\n" ; [ "$RC" = 0 ] && ok "non-foundational + marker(+per-step) + DEPTH=3 -> pass (0)" || no "D3+marker expected 0 got $RC"
run "some/dir/file.txt" 3 "TS=1\nTASK=t\n" ; [ "$RC" = 2 ] && ok "non-foundational + marker WITHOUT per-step + DEPTH=3 -> blocked (2, existing D3+ rule)" || no "D3 per-step expected 2 got $RC"

echo "=== foundational unchanged (always HARD, any depth) ==="
run "sutra/os/charters/x.md" 1   ; [ "$RC" = 2 ] && ok "foundational + no marker + DEPTH=1 -> blocked (2)" || no "foundational D1 expected 2 got $RC"
run "sutra/os/charters/x.md" 2 "TS=1\nTASK=t\n" ; [ "$RC" = 2 ] && ok "foundational + marker missing HAS_OUTPUT/VERIFY -> blocked (2)" || no "foundational D48 expected 2 got $RC"
run "sutra/os/charters/x.md" 2 "HAS_OUTPUT=1\nHAS_VERIFY=1\nTS=1\nTASK=t\n" ; [ "$RC" = 0 ] && ok "foundational + full marker (D<3) -> pass (0)" || no "foundational full expected 0 got $RC"

echo "=== D2: non-foundational message does NOT demand Output/Verified-by as a requirement ==="
run "some/dir/file.txt" 3
printf '%s' "$ERR" | grep -qi "only on FOUNDATIONAL" && ok "D2 non-foundational msg clarifies Output/Verified-by is foundational-only" || no "D2 message not split: $ERR"

echo "=== D3: no message points to the phantom 'CLAUDE.md Mandatory Blocks' ==="
run "some/dir/file.txt" 3;  M1="$ERR"
run "sutra/os/charters/x.md" 1; M2="$ERR"
if printf '%s\n%s' "$M1" "$M2" | grep -qi "Mandatory Blocks"; then no "D3 still references phantom Mandatory Blocks"; else ok "D3 no phantom reference"; fi
printf '%s' "$M1" | grep -qi "core:blueprint skill\|SUTRA-DEFAULTS" && ok "D3 points to a real doc (skill / SUTRA-DEFAULTS.md)" || no "D3 no real doc pointer: $M1"

echo "=== overrides still work ==="
D=$(mktemp -d); mkdir -p "$D/some" "$D/.claude"; printf 'DEPTH=5 TASK=t TS=1\n' > "$D/.claude/depth-registered"
printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$D/some/f.txt" | CLAUDE_PROJECT_DIR="$D" BLUEPRINT_ACK=1 bash "$HOOK" >/dev/null 2>&1; [ "$?" = 0 ] && ok "BLUEPRINT_ACK override passes" || no "ACK override failed"
printf '{"tool_name":"Edit","tool_input":{"file_path":"%s"}}' "$D/some/f.txt" | CLAUDE_PROJECT_DIR="$D" BLUEPRINT_DISABLED=1 bash "$HOOK" >/dev/null 2>&1; [ "$?" = 0 ] && ok "BLUEPRINT_DISABLED kill-switch passes" || no "kill-switch failed"
rm -rf "$D"

echo ""
echo "blueprint-check-depth-gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
