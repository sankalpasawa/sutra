#!/bin/bash
# Sutra Default: warn on unpushed work at session end.
# Company override: set `git_push_cadence: silent` in SUTRA-CONFIG.md to suppress.
#
# Event: Stop (session end)
# Enforcement: SOFT (warning only, exit 0 always)
# Tier: 3 — Tunable Default (DEFAULTS-ARCHITECTURE.md)

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

warnings=""

# --- Check main repo ---
check_repo() {
  local dir="$1"
  local name="$2"

  cd "$dir" 2>/dev/null || return

  local uncommitted=0
  local unpushed=0

  # Count uncommitted changes (staged + unstaged + untracked)
  uncommitted=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  # Count unpushed commits (only if remote tracking exists)
  if git rev-parse --verify origin/main &>/dev/null; then
    unpushed=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
  elif git rev-parse --verify origin/master &>/dev/null; then
    unpushed=$(git log origin/master..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
  fi

  if [ "$uncommitted" -gt 0 ] || [ "$unpushed" -gt 0 ]; then
    warnings="${warnings}\n  ${name}: ${uncommitted} files uncommitted, ${unpushed} commits unpushed"
  fi
}

# Check the main holding repo
check_repo "$REPO_ROOT" "asawa-holding"

# Check submodules if they exist
for sub in dayflow sutra maze ppr jarvis; do
  sub_path="$REPO_ROOT/$sub"
  if [ -d "$sub_path/.git" ] || [ -f "$sub_path/.git" ]; then
    check_repo "$sub_path" "$sub"
  fi
done

# Output warning if anything found
if [ -n "$warnings" ]; then
  echo ""
  echo "⚠️  BACKUP RISK — unpushed work detected:"
  echo -e "$warnings"
  echo ""
  echo "Run: git add + commit + push before ending session."
  echo ""
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
