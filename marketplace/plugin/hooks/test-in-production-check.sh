#!/bin/bash
# Direction: D1 — Test Everything in Production
# Event: Stop
# Enforcement: SOFT (reminder, exit 0 always)
# Check if new .md files were created in holding/ or sutra/ during this session.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# Check for new .md files added (staged or unstaged) in holding/ or sutra/
NEW_FILES=$(cd "$REPO_ROOT" && git diff --name-only --diff-filter=A HEAD 2>/dev/null | grep -E '^(holding|sutra)/.*\.md$')

if [ -n "$NEW_FILES" ]; then
  echo "Warning: Per D1: New system artifacts created but not tested in production."
  echo "Verify each against a real task:"
  echo "$NEW_FILES" | while read -r f; do echo "  - $f"; done
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
