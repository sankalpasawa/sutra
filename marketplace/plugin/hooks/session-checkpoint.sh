#!/bin/bash
# Session Checkpoint — auto-save structured state at session end
# Event: Stop
# Enforcement: HARD (always runs, always exits 0)
# Implements: HUMAN-AI-INTERACTION.md Part 6 (Session Continuity)

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
CHECKPOINT_DIR="$REPO_ROOT/holding/checkpoints"
TODAY=$(date -u +"%Y-%m-%d")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SHORT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "0000")
SESSION_ID="${TODAY}-${SHORT_HASH}"
CHECKPOINT_FILE="$CHECKPOINT_DIR/${TODAY}.json"

# Ensure directory exists
mkdir -p "$CHECKPOINT_DIR"

# --- Gather git data (last 10 commits window) ---

# Files created
CREATED=$(git diff --name-only --diff-filter=A HEAD~10..HEAD 2>/dev/null | \
  sed 's/"/\\"/g' | awk '{printf "    \"%s\"", $0; if(NR>1 || getline > 0) printf ",\n"; else printf "\n"}' 2>/dev/null)
CREATED_JSON=$(git diff --name-only --diff-filter=A HEAD~10..HEAD 2>/dev/null | \
  awk 'BEGIN{first=1} {if(!first) printf ","; first=0; printf "\n    \"%s\"", $0} END{if(NR>0) printf "\n"}')

# Files modified
MODIFIED_JSON=$(git diff --name-only --diff-filter=M HEAD~10..HEAD 2>/dev/null | \
  awk 'BEGIN{first=1} {if(!first) printf ","; first=0; printf "\n    \"%s\"", $0} END{if(NR>0) printf "\n"}')

# Commit count and hashes
COMMIT_COUNT=$(git log --oneline HEAD~10..HEAD 2>/dev/null | wc -l | tr -d ' ')
COMMIT_HASHES_JSON=$(git log --format='%h' HEAD~10..HEAD 2>/dev/null | \
  awk 'BEGIN{first=1} {if(!first) printf ","; first=0; printf "\n    \"%s\"", $0} END{if(NR>0) printf "\n"}')

# Direction count from FOUNDER-DIRECTIONS.md
DIRECTION_COUNT=$(grep -c "^### D[0-9]" "$REPO_ROOT/holding/FOUNDER-DIRECTIONS.md" 2>/dev/null || echo "0")

# Enforcement count from DIRECTION-ENFORCEMENT.md
ENFORCEMENT_COUNT=$(grep -c "^## D[0-9]" "$REPO_ROOT/holding/DIRECTION-ENFORCEMENT.md" 2>/dev/null || echo "0")

# --- Write checkpoint JSON ---

cat > "$CHECKPOINT_FILE" << CHECKPOINT
{
  "session_id": "${SESSION_ID}",
  "timestamp": "${TIMESTAMP}",
  "directions_captured": {
    "count": ${DIRECTION_COUNT},
    "enforcement_count": ${ENFORCEMENT_COUNT},
    "ids": []
  },
  "decisions_made": [],
  "artifacts_created": [${CREATED_JSON}
  ],
  "artifacts_modified": [${MODIFIED_JSON}
  ],
  "commits": {
    "count": ${COMMIT_COUNT},
    "hashes": [${COMMIT_HASHES_JSON}
    ]
  },
  "agents_dispatched": {
    "count": 0,
    "types": [],
    "accuracy": null
  },
  "open_items": [],
  "estimation_calibration": {
    "tasks_estimated": 0,
    "accuracy_pct": null
  },
  "next_session_recommendations": []
}
CHECKPOINT

echo "Session checkpoint saved: ${CHECKPOINT_FILE}"
echo "  Session: ${SESSION_ID} | Commits: ${COMMIT_COUNT} | Directions: ${DIRECTION_COUNT} | Enforced: ${ENFORCEMENT_COUNT}"

# Merged from session-end-satisfaction.sh (D18)
echo ""
echo "Per D18: Generate 'Your Day' dashboard before ending."
echo "Show: founder contributions, LLM contributions, what shipped, what's next."

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
