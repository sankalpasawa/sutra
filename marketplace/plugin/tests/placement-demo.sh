#!/usr/bin/env bash
# placement-demo.sh — visual end-to-end demonstration of ADR-028 placement.
#
#   bash "$(ls -d ~/.claude/plugins/cache/sutra/core/*/ | sort -V | tail -1)tests/placement-demo.sh"
#
# Builds a THROWAWAY registry in a temp dir from a real directory tree, then
# shows every surface: the derived tree, classification across many inputs, all
# three print shapes, what the per-turn hook hands the model, the MECE report,
# and a restructure with its blast radius. Your real registry is never touched.
set -u

PLUGIN="$(cd "$(dirname "$0")/.." && pwd)"
ENG="$PLUGIN/lib/placement_engine.py"
REND="$PLUGIN/lib/placement-render.sh"
HOOK="$PLUGIN/hooks/placement-resolve.sh"
TARGET="${1:-$PLUGIN}"

SB=$(mktemp -d); trap 'rm -rf "$SB"' EXIT
export SUTRA_NATIVE_HOME="$SB/user-kit"
export PLACEMENT_ROOT_NAME="${PLACEMENT_ROOT_NAME:-Asawa Inc.}"

hr()  { printf '\n%s\n' "-------------------------------------------------------------------------"; }
ttl() { hr; printf ' %s\n' "$1"; hr; }

ttl "0. BUILD A REGISTRY FROM A REAL TREE  ($TARGET)"
python3 "$ENG" scan "$TARGET" > "$SB/scan.json" 2>&1
python3 - "$SB/scan.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
print("  files enumerated : %s" % d['units_enumerated'])
print("  files addressed  : %s" % d['units_addressed'])
print("  root-level files : %s  (placed at root, not given their own domain)" % d['root_level_files'])
print("  domains derived  : %s" % d['mece']['domains'])
print("  MECE violations  : %s" % d['mece']['me_violations'])
PY

ttl "1. THE DERIVED TREE  (nesting comes from real structure)"
python3 "$ENG" tree | python3 -c "
import json,sys
ds=json.load(sys.stdin)['domains']
def key(d):
    return [-1] if d['path']=='D0' else [int(x[1:]) for x in d['path'].split('.')]
for d in sorted(ds,key=key):
    depth = 0 if d['path']=='D0' else len(d['path'].split('.'))
    print('  %s%-9s %s' % ('   '*depth, d['path'], d['name']))
print()
print('  %d domains total' % len(ds))"

ttl "2. CLASSIFICATION — MANY INPUTS, ONE TABLE"
printf '  %-40s %-8s %-7s %s\n' "INPUT" "CONF" "MODE" "RESOLVED TO"
printf '  %-40s %-8s %-7s %s\n' "$(printf '%.40s' '----------------------------------------')" "-------" "------" "------------------------"
run() { # run <label> <utterance> [path]
  local label="$1" utt="$2" p="${3:-}"
  local R
  if [ -n "$p" ]; then R=$(python3 "$ENG" classify "$utt" "$p" 2>/dev/null)
  else R=$(python3 "$ENG" classify "$utt" 2>/dev/null); fi
  printf '  %-40s %-8s %-7s %s\n' "$label" \
    "$(printf '%s' "$R" | jq -r '.confidence')" \
    "$(printf '%s' "$R" | jq -r '.mode // "-"')" \
    "$(printf '%s' "$R" | jq -r 'if .resolved then (.chain|map(.name)|join(" > ")) else "[" + .reason + "]" end')"
}
echo "  -- path evidence (strong) --"
run "hooks/placement-gate.sh"        "edit"  "hooks/placement-gate.sh"
run "lib/placement_engine.py"        "edit"  "lib/placement_engine.py"
run "tests/unit/placement.test.sh"   "edit"  "tests/unit/placement.test.sh"
run "skills/flow/SKILL.md"           "edit"  "skills/flow/SKILL.md"
run "commands/ (any)"                "edit"  "commands/start.md"
echo "  -- utterance only (weak by nature) --"
run "\"update the unit tests\""            "update the unit tests"
run "\"fix the placement gate hook\""      "fix the placement gate hook"
run "\"add a connector manifest\""         "add a connector manifest"
run "\"buy milk\""                         "buy milk"

ttl "3. THE PRINTED BLOCK — ALL THREE SHAPES"
echo "  (a) COMPACT — the every-turn case, one line:"
printf '{"chain":[{"path":"D0","name":"Asawa Inc."},{"path":"D4","name":"Hooks"}],"charter":{"id":"C-x","title":"Hooks Charter"},"created":{"domains":[],"charters":[]},"units":1}' \
  | bash "$REND" | sed 's/^/      /'
echo
echo "  (b) EXPANDED — only when something was minted:"
printf '{"chain":[{"path":"D0","name":"Asawa Inc."},{"path":"D4","name":"Hooks"},{"path":"D4.D3","name":"Placement","is_new":true}],"charter":{"id":"C-new","title":"Placement Charter","promise":"every unit of work carries an address","scope_in":"hooks, lib, tests","scope_out":"canon docs","is_new":true},"created":{"domains":["d1"],"charters":["C-new"]},"units":1}' \
  | bash "$REND" | sed 's/^/      /'
echo
echo "  (c) SUMMARY — bulk turns (>20 units):"
printf '{"chain":[{"path":"D0","name":"Asawa Inc."},{"path":"D4","name":"Hooks"}],"charter":{"id":"C-x","title":"Hooks Charter"},"created":{"domains":["a","b"],"charters":["C-1"]},"units":323}' \
  | bash "$REND" | sed 's/^/      /'

ttl "4. WHAT THE PER-TURN HOOK HANDS THE MODEL"
for utt in "fix the placement gate hook" "update the unit tests"; do
  echo "  utterance: \"$utt\""
  printf '{"prompt":"%s","session_id":"demo"}' "$utt" \
    | CLAUDE_PROJECT_DIR="$SB" CLAUDE_PLUGIN_ROOT="$PLUGIN" bash "$HOOK" 2>/dev/null \
    | jq -r '.hookSpecificOutput.additionalContext // "  (no context emitted)"' | sed 's/^/    /'
  echo
done

ttl "5. MECE REPORT — P5 made runnable"
python3 "$ENG" mece | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('  domains              : %s' % d['domains'])
print('  mutual-exclusion viol: %s   (auto-mergeable: %s)' % (d['me_violations'], d['auto_mergeable']))
print('  addressed work units : %s' % d['ce_addressed_units'])
for o in d['overlaps'][:5]:
    print('    overlap: %-20s <-> %-20s sim=%.2f auto=%s' % (o['a_name'],o['b_name'],o['similarity'],o['auto_mergeable']))
if not d['overlaps']: print('    (no sibling overlaps detected)')"

ttl "6. RESTRUCTURE — MOVE MUST RE-MINT ZERO ROWS (I-P8)"
BEFORE=$(python3 "$ENG" stats | jq -r '.placements')
REF=$(python3 "$ENG" tree | python3 -c "
import json,sys
ds=json.load(sys.stdin)['domains']
c=[d for d in ds if d['path']!='D0' and '.' not in d['path']]
print(c[-1]['ref'] if c else '')")
TGT=$(python3 "$ENG" tree | python3 -c "
import json,sys
ds=json.load(sys.stdin)['domains']
c=[d for d in ds if d['path']!='D0' and '.' not in d['path']]
print(c[0]['ref'] if c else '')")
if [ -n "$REF" ] && [ -n "$TGT" ] && [ "$REF" != "$TGT" ]; then
  python3 "$ENG" restructure move "$REF" "$TGT" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('  move ok=%s  placements_repointed=%s' % (d.get('ok'), d.get('placements_repointed')))"
  AFTER=$(python3 "$ENG" stats | jq -r '.placements')
  printf '  placement rows: before=%s after=%s  ->  %s\n' "$BEFORE" "$AFTER" \
    "$([ "$BEFORE" = "$AFTER" ] && echo 'ZERO re-mints (correct)' || echo 'MISMATCH (defect)')"
else
  echo "  (not enough top-level domains to demo a move)"
fi

ttl "7. FINAL STATE"
python3 "$ENG" stats | sed 's/^/  /'
hr
printf ' Demo complete. Temp registry at %s is now deleted.\n' "$SUTRA_NATIVE_HOME"
hr
