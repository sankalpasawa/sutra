#!/bin/bash
# Unit test: skills/writing-style/SKILL.md obeys its own section 7 (verify-your-own-instruments).
# Asserts: <= 250 lines, exactly one H1 outside fences, zero untagged fences, metadata block,
# provenance footer, banned block present, and md-standard-gate.sh passes the file.

set -u
PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$PLUGIN/skills/writing-style/SKILL.md"
GATE="$PLUGIN/hooks/md-standard-gate.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }

[ -f "$SKILL" ] || { echo "  XX  skill file missing: $SKILL"; exit 1; }

LINES=$(wc -l < "$SKILL" | tr -d ' ')
[ "$LINES" -le 250 ] && ok "$LINES lines <= 250 (M8)" || no "$LINES lines > 250"

SCAN=$(awk 'BEGIN{f=0;h=0;u=0} /^[[:space:]]*(```|~~~)/{ if(f==0){f=1; s=$0; sub(/^[[:space:]]*(```|~~~)/,"",s); if(s ~ /^[[:space:]]*$/) u++} else {f=0}; next } f==0 && /^# /{h++} END{printf "%d %d",h,u}' "$SKILL")
H1=${SCAN%% *}; UNTAGGED=${SCAN#* }
[ "$H1" -eq 1 ] && ok "exactly one H1 outside fences (R5)" || no "H1 count $H1"
[ "$UNTAGGED" -eq 0 ] && ok "every fence carries a language tag (R12)" || no "$UNTAGGED untagged fences"

head -15 "$SKILL" | grep -qE '^---$' && ok "frontmatter present" || no "no frontmatter"
grep -q '^\- \*\*status\*\*' "$SKILL" && ok "metadata block present (R1)" || no "metadata block missing"
tail -12 "$SKILL" | grep -q '^provenance:' && ok "provenance footer present (R10)" || no "provenance footer missing"
grep -q '<!-- banned:start -->' "$SKILL" && grep -q '<!-- banned:end -->' "$SKILL" && ok "banned block markers present" || no "banned block markers missing"
grep -q '^| P0 | MINIMIZE |' "$SKILL" && ok "MINIMIZE is principle 0" || no "P0 MINIMIZE row missing"
for a in principles scope minimize banned budgets shapes files revoke enforcement checklist not-adopted; do
  grep -q "<a id=\"$a\"></a>" "$SKILL" || { no "anchor #$a missing"; continue; }
done
ok "section anchors present (R6)"
grep -qE '[─-▟]' "$SKILL" && no "unicode box/block glyph in the skill file" || ok "no unicode structural glyphs (R4, ASCII only)"

if command -v jq >/dev/null 2>&1; then
  OUT=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$SKILL" | CLAUDE_PROJECT_DIR="$PLUGIN" bash "$GATE" 2>&1); RC=$?
  [ "$RC" -eq 0 ] && ok "md-standard-gate.sh passes the skill file (rc=0)" || no "md-standard-gate rc=$RC: $OUT"
fi

echo ""
echo "writing-style-skill-selfcheck: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
