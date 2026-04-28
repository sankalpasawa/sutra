#!/bin/bash
# Asawa Enforcement Framework — Task Lifecycle Coverage (D3)
# Detects tasks that bypassed the Sutra Task Lifecycle (OBJECTIVE→OBSERVE→SHAPE→PLAN→EXECUTE→MEASURE→LEARN).
# Heuristic sensor — false positives are acceptable.
#
# Type: AUDIT (exit 0 always)
# Fires: Stop (session end)
# Principle: D3 ("Every task has a Sutra path")
# See: sutra/layer2-operating-system/TASK-LIFECYCLE.md

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

ESTIMATION_LOG="$REPO_ROOT/holding/ESTIMATION-LOG.jsonl"

# ─── Gather session commits ─────────────────────────────────────────────
# Heuristic: commits in the last 4 hours are "this session"
SINCE=$(date -v-4H +"%Y-%m-%dT%H:%M:%S" 2>/dev/null || date -d '4 hours ago' +"%Y-%m-%dT%H:%M:%S" 2>/dev/null)

if [ -z "$SINCE" ]; then
  # Fallback: last 10 commits
  COMMITS=$(git log -10 --format='%H' 2>/dev/null)
else
  COMMITS=$(git log --since="$SINCE" --format='%H' 2>/dev/null)
fi

if [ -z "$COMMITS" ]; then
  echo "═══ LIFECYCLE COVERAGE CHECK ═══"
  echo "No commits found this session. Nothing to audit."
  echo "═════════════════════════════════"
  exit 0
fi

# ─── Filter to source-code commits ──────────────────────────────────────
# Only check commits that touch src/, app/, lib/, features/, components/, pages/
SOURCE_PATTERNS="^(src/|app/|lib/|features/|components/|pages/|.*/(src|app|lib|features|components|pages)/)"

TOTAL_TASKS=0
LIFECYCLE_TASKS=0
BYPASS_TASKS=0
BYPASS_DETAILS=""

while IFS= read -r COMMIT; do
  [ -z "$COMMIT" ] && continue

  # Check if this commit touches source code
  FILES_CHANGED=$(git diff-tree --no-commit-id --name-only -r "$COMMIT" 2>/dev/null)
  SOURCE_FILES=$(echo "$FILES_CHANGED" | grep -E "$SOURCE_PATTERNS" || true)

  if [ -z "$SOURCE_FILES" ]; then
    continue  # Not a source-code commit, skip
  fi

  TOTAL_TASKS=$((TOTAL_TASKS + 1))
  COMMIT_MSG=$(git log -1 --format='%s' "$COMMIT" 2>/dev/null)
  COMMIT_SHORT=$(git log -1 --format='%h' "$COMMIT" 2>/dev/null)

  HAS_EVIDENCE=false

  # ─── Evidence 1: PLAN phase — estimation entry exists ───────────────
  # Check if ESTIMATION-LOG.jsonl was updated in this commit or nearby commits
  if [ -f "$ESTIMATION_LOG" ]; then
    ESTIMATION_IN_COMMIT=$(git diff-tree --no-commit-id --name-only -r "$COMMIT" 2>/dev/null | grep 'ESTIMATION-LOG.jsonl' || true)
    if [ -n "$ESTIMATION_IN_COMMIT" ]; then
      HAS_EVIDENCE=true
    fi
  fi

  # ─── Evidence 2: OBSERVE phase — meaningful commit message ───────────
  # A bare "fix typo" or single-word message suggests no OBSERVE phase
  MSG_LENGTH=${#COMMIT_MSG}
  # Check for contextual signals: colons (conventional commits), ticket refs, description
  HAS_CONTEXT=$(echo "$COMMIT_MSG" | grep -E '(:|#|—|→|phase|lifecycle|D[0-9]+|level [0-9]|estimate|plan)' || true)

  if [ "$MSG_LENGTH" -gt 30 ] || [ -n "$HAS_CONTEXT" ]; then
    HAS_EVIDENCE=true
  fi

  # ─── Evidence 3: PLAN phase — estimation log has a recent matching entry ──
  # Check if the estimation log mentions files from this commit (fuzzy match)
  if [ -f "$ESTIMATION_LOG" ] && [ "$HAS_EVIDENCE" = false ]; then
    # Get the first source file changed as a search key
    FIRST_FILE=$(echo "$SOURCE_FILES" | head -1)
    FILE_BASENAME=$(basename "$FIRST_FILE" 2>/dev/null)
    if [ -n "$FILE_BASENAME" ]; then
      LOG_MATCH=$(grep -l "$FILE_BASENAME" "$ESTIMATION_LOG" 2>/dev/null || true)
      if [ -n "$LOG_MATCH" ]; then
        HAS_EVIDENCE=true
      fi
    fi
  fi

  # ─── Evidence 4: Commit body has lifecycle markers ─────────────────
  COMMIT_BODY=$(git log -1 --format='%b' "$COMMIT" 2>/dev/null)
  if [ -n "$COMMIT_BODY" ]; then
    BODY_EVIDENCE=$(echo "$COMMIT_BODY" | grep -iE '(objective|observe|shape|plan|execute|measure|learn|estimation|level [0-9]|thoroughness|complexity|impact)' || true)
    if [ -n "$BODY_EVIDENCE" ]; then
      HAS_EVIDENCE=true
    fi
  fi

  # ─── Tally ─────────────────────────────────────────────────────────
  if [ "$HAS_EVIDENCE" = true ]; then
    LIFECYCLE_TASKS=$((LIFECYCLE_TASKS + 1))
  else
    BYPASS_TASKS=$((BYPASS_TASKS + 1))
    BYPASS_DETAILS="$BYPASS_DETAILS\n  -> $COMMIT_SHORT: \"$COMMIT_MSG\""
  fi

done <<< "$COMMITS"

# ─── Output ──────────────────────────────────────────────────────────────

echo "═══ LIFECYCLE COVERAGE CHECK (D3) ═══"

if [ "$TOTAL_TASKS" -eq 0 ]; then
  echo "No source-code commits this session. Nothing to audit."
  echo "══════════════════════════════════════"
  exit 0
fi

if [ "$BYPASS_TASKS" -eq 0 ]; then
  ICON="✅"
else
  ICON="⚠️"
fi

echo "$ICON Lifecycle coverage: $LIFECYCLE_TASKS/$TOTAL_TASKS tasks had lifecycle evidence."

if [ "$BYPASS_TASKS" -gt 0 ]; then
  echo ""
  echo "$BYPASS_TASKS task(s) may have bypassed the lifecycle:"
  echo -e "$BYPASS_DETAILS"
  echo ""
  echo "Reminder: OBJECTIVE→OBSERVE→SHAPE→PLAN→EXECUTE→MEASURE→LEARN (TASK-LIFECYCLE.md)"
fi

echo "══════════════════════════════════════"

# AUDIT mode: always exit 0
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
