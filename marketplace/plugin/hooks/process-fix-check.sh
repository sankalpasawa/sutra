#!/bin/bash
# Direction: D2 — Fix the Process, Not Just the Instance
# Event: PostToolUse on Edit|Write
# Enforcement: SOFT (reminder, exit 0 always)
# If recent commit message contains fix/bug/patch/hotfix, remind to fix the process too.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# Claude Code stdin-JSON drain (prevents indefinite wait on piped input).
[ ! -t 0 ] && cat > /dev/null 2>&1 || true

# Check the most recent commit message for fix-related words
LAST_MSG=$(cd "$REPO_ROOT" && git log -1 --oneline 2>/dev/null)

if echo "$LAST_MSG" | grep -iqE '\b(fix|bug|patch|hotfix)\b'; then
  echo "Warning: Per D2: Bug fix detected in recent commit: $LAST_MSG"
  echo "Did you also fix the PROCESS that allowed this bug?"
  echo "Root cause -> process improvement required."
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
