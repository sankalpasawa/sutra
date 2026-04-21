#!/bin/bash
# Sutra plugin smoke test.
# Verifies the plugin was installed correctly and every surface is wired.
#
# Run AFTER `claude plugin install core@sutra` (+ Claude Code restart if needed).
# Exits 0 if all surfaces present, non-zero if anything is missing.
#
# Surfaces checked:
#   - installed_plugins registry entry
#   - plugin cache dir exists + plugin.json valid
#   - 4 skills: input-routing, depth-estimation, readability-gate, output-trace
#   - 2 hooks: depth-marker-pretool.sh, estimation-stop.sh (runnable)
#   - 2 commands: sutra.md, depth-check.md
#   - hooks.json references real files

set -u

PASS=0
FAIL=0
FAIL_MSGS=()

_pass() { PASS=$((PASS+1)); echo "  OK  $1"; }
_fail() { FAIL=$((FAIL+1)); FAIL_MSGS+=("$1"); echo "  X   $1"; }

_req_file() { [ -f "$1" ] && _pass "$2 ($1)" || _fail "$2 — missing: $1"; }
_req_dir()  { [ -d "$1" ] && _pass "$2 ($1)" || _fail "$2 — missing: $1"; }
_req_run()  { [ -x "$1" ] && _pass "$2 ($1)" || _fail "$2 — not runnable: $1"; }

echo "==============================================================="
echo "  Sutra plugin smoke test — $(date '+%Y-%m-%d %H:%M:%S')"
echo "==============================================================="

# 1. Registry entry
echo ""
echo "[1/6] Plugin registry"
REG=~/.claude/plugins/installed_plugins.json
if [ -f "$REG" ]; then
  if python3 -c "import json,sys; d=json.load(open('$REG')); sys.exit(0 if 'core@sutra' in d.get('plugins',{}) else 1)" 2>/dev/null; then
    _pass "installed_plugins.json contains core@sutra"
  else
    _fail "core@sutra not in installed_plugins.json — did /plugin install run?"
  fi
else
  _fail "installed_plugins.json missing ($REG)"
fi

# 2. Plugin cache dir
echo ""
echo "[2/6] Plugin cache"
PCACHE=$(ls -d ~/.claude/plugins/cache/sutra/sutra/*/ 2>/dev/null | head -1)
if [ -n "$PCACHE" ] && [ -d "$PCACHE" ]; then
  _pass "plugin cache dir present: $PCACHE"
  _req_file "${PCACHE}.claude-plugin/plugin.json" "plugin.json present"
  if [ -f "${PCACHE}.claude-plugin/plugin.json" ]; then
    python3 -c "
import json,sys
d=json.load(open('${PCACHE}.claude-plugin/plugin.json'))
assert d.get('name')=='core', f\"name is {d.get('name')}\"
assert d.get('version'), 'version missing'
print(f\"  plugin v{d['version']}\")
" 2>&1 | grep -q "plugin v" && _pass "plugin.json valid (name=core, version set)" || _fail "plugin.json contents invalid"
  fi
else
  _fail "plugin cache dir missing under ~/.claude/plugins/cache/sutra/sutra/"
  echo ""
  echo "  HINT: Run: claude plugin install core@sutra  — then retry."
  echo ""
  exit 1
fi

# 3. Skills (4)
echo ""
echo "[3/6] Skills"
for skill in input-routing depth-estimation readability-gate output-trace; do
  _req_file "${PCACHE}skills/${skill}/SKILL.md" "skill: $skill"
done

# 4. Hooks (2 + hooks.json)
echo ""
echo "[4/6] Hooks"
_req_file "${PCACHE}hooks/hooks.json" "hooks.json"
_req_run  "${PCACHE}hooks/depth-marker-pretool.sh" "hook: depth-marker-pretool.sh"
_req_run  "${PCACHE}hooks/estimation-stop.sh" "hook: estimation-stop.sh"
if [ -f "${PCACHE}hooks/hooks.json" ]; then
  python3 -c "
import json
d=json.load(open('${PCACHE}hooks/hooks.json'))
evs = list(d.get('hooks',{}).keys())
assert 'PreToolUse' in evs, 'PreToolUse missing'
assert 'Stop' in evs, 'Stop missing'
print('  events:', evs)
" 2>&1 | grep -q "events:" && _pass "hooks.json registers PreToolUse + Stop" || _fail "hooks.json structure wrong"
fi

# 5. Commands (v1.5.x surface)
echo ""
echo "[5/8] Commands"
_req_file "${PCACHE}commands/start.md" "command: /core:start"
_req_file "${PCACHE}commands/status.md" "command: /core:status"
_req_file "${PCACHE}commands/update.md" "command: /core:update"
_req_file "${PCACHE}commands/uninstall.md" "command: /core:uninstall"
_req_file "${PCACHE}commands/permissions.md" "command: /core:permissions"
_req_file "${PCACHE}commands/depth-check.md" "command: /core:depth-check"

# 6. Lib (v1 additions)
echo ""
echo "[6/8] Lib (v1)"
_req_file "${PCACHE}lib/project-id.sh" "lib: project-id.sh"
_req_file "${PCACHE}lib/queue.sh" "lib: queue.sh"

# 7. V1 hooks (emit-metric + flush-telemetry)
echo ""
echo "[7/8] V1 hooks"
_req_run  "${PCACHE}hooks/emit-metric.sh" "hook: emit-metric.sh"
_req_run  "${PCACHE}hooks/flush-telemetry.sh" "hook: flush-telemetry.sh"
if [ -f "${PCACHE}hooks/hooks.json" ]; then
  python3 -c "
import json
d=json.load(open('${PCACHE}hooks/hooks.json'))
stops=[h['command'] for h in d['hooks']['Stop'][0]['hooks']]
assert any('flush-telemetry' in c for c in stops), 'flush-telemetry not in Stop hook chain'
print('  Stop chain includes flush-telemetry')
" 2>&1 | grep -q "includes flush-telemetry" && _pass "hooks.json registers flush-telemetry on Stop" || _fail "flush-telemetry missing from Stop chain"
fi

# 8. Summary
echo ""
echo "[8/8] Summary"
TOTAL=$((PASS+FAIL))
echo ""
echo "==============================================================="
if [ "$FAIL" -eq 0 ]; then
  echo "  SMOKE TEST PASSED — $PASS/$TOTAL checks · plugin fully wired"
  echo "==============================================================="
  echo ""
  echo "Next: behavioural test (run inside Claude Code):"
  echo "  /core:start          — create sutra-project.json with install_id + project_id"
  echo "  /core:status         — inspect queue depth, opt-in flag, last flush"
  echo "  (work a little — Stop hook auto-emits metrics per session)"
  echo "  sutra push           — deliver queue to sankalpasawa/sutra-data (private)"
  echo ""
  exit 0
else
  echo "  SMOKE TEST FAILED — $PASS/$TOTAL passed · $FAIL missing"
  echo "==============================================================="
  echo ""
  echo "Failures:"
  for m in "${FAIL_MSGS[@]}"; do echo "  - $m"; done
  echo ""
  exit 1
fi
