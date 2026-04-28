#!/bin/bash
# Sutra OS — Hook Graduation Checker
# Reads compliance.jsonl and reports which SOFT hooks should graduate to HARD.
# Usage: bash check-graduation.sh [project_dir]
# Graduation threshold: <80% compliance over 20+ events
PROJECT_DIR="${1:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}}"
LOG_FILE="$PROJECT_DIR/.claude/logs/compliance.jsonl"
if [ ! -f "$LOG_FILE" ]; then
  echo "No compliance data yet. Run 5+ sessions first."
  exit 0
fi
echo "═══════════════════════════════════════════"
echo "  HOOK GRADUATION REPORT"
echo "═══════════════════════════════════════════"
echo ""
HOOKS=$(cat "$LOG_FILE" | sed -n 's/.*"hook":"\([^"]*\)".*/\1/p' | sort -u)
for hook in $HOOKS; do
  TOTAL=$(grep "\"hook\":\"$hook\"" "$LOG_FILE" | wc -l | tr -d ' ')
  PASSES=$(grep "\"hook\":\"$hook\"" "$LOG_FILE" | grep '"status":"pass"' | wc -l | tr -d ' ')
  if [ "$TOTAL" -eq 0 ]; then continue; fi
  PCT=$((PASSES * 100 / TOTAL))
  if [ "$TOTAL" -ge 20 ] && [ "$PCT" -lt 80 ]; then
    echo "  GRADUATE  $hook — $PCT% compliance ($PASSES/$TOTAL) — promote to HARD"
  elif [ "$TOTAL" -ge 20 ]; then
    echo "  KEEP SOFT $hook — $PCT% compliance ($PASSES/$TOTAL)"
  else
    echo "  WAITING   $hook — $PCT% compliance ($PASSES/$TOTAL) — need 20+ events"
  fi
done
echo ""
echo "═══════════════════════════════════════════"

# ============================================================================
# ## Operationalization
# (Auto-appended on D38 wave-6 plugin promotion — lightweight default; replace
# with concrete metrics when this hook gets attention.)
#
# ### 1. Measurement mechanism
# Hook events emit to .enforcement/build-layer-ledger.jsonl or hook-specific
# log when relevant; no dedicated metric until usage observed.
# ### 2. Adoption mechanism
# Activated via plugin distribution from sutra/marketplace/plugin/hooks/.
# ### 3. Monitoring / escalation
# Surface error/anomaly rate to Asawa CEO weekly until baseline established.
# ### 4. Iteration trigger
# Tighten or loosen after 14 days of fleet observation.
# ### 5. DRI
# Asawa CEO (Sutra Forge per D31).
# ### 6. Decommission criteria
# Retire when capability supersedes via newer hook or absorbed into a
# composite gate. Currently no decommission planned.
# ============================================================================
