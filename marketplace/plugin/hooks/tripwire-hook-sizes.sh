#!/bin/bash
# Tripwire: watches for hook files being emptied. Logs + restores.
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || exit 0)}"
cd "$REPO_ROOT" || exit 0
TRIPLOG="$REPO_ROOT/.enforcement/hook-tripwire.log"
mkdir -p "$(dirname "$TRIPLOG")"
for f in holding/hooks/*.sh; do
  [ -f "$f" ] || continue
  lines=$(wc -l < "$f" 2>/dev/null)
  if [ "$lines" -lt 2 ]; then
    echo "{\"ts\":$(date +%s),\"event\":\"empty-hook\",\"file\":\"$f\",\"lines\":$lines}" >> "$TRIPLOG"
    # Restore from HEAD
    if git show HEAD:"$f" > "$f" 2>/dev/null; then
      chmod +x "$f"
      echo "{\"ts\":$(date +%s),\"event\":\"auto-restored\",\"file\":\"$f\"}" >> "$TRIPLOG"
    fi
  fi
done
exit 0

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
