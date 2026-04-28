#!/usr/bin/env bash
# Stop hook: advisory context budget check for governance overhead
# Counts governance .md files loaded from holding/ and sutra/ during session

TRANSCRIPT="${CLAUDE_TRANSCRIPT:-}"
[ -z "$TRANSCRIPT" ] && exit 0

COUNT=$(echo "$TRANSCRIPT" | grep -oE '(holding|sutra)/[^ "]*\.md' | sort -u | wc -l | tr -d ' ')

if [ "$COUNT" -gt 10 ]; then
  cat <<EOF
{"decision":"BLOCK","reason":"CONTEXT BUDGET WARNING: ${COUNT} governance files loaded. Target: <10. Consider lazy loading."}
EOF
else
  echo '{"decision":"ALLOW","suppressOutput":true}'
fi

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
