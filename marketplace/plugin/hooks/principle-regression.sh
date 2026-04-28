#!/bin/bash
# Asawa Enforcement Framework — Principle Regression Tests (D27)
# Automated immune system: detects principle violations post-session.
# Reports only — never blocks.
#
# Type: AUDIT (exit 0 always)
# Fires: Stop (session end)
# Principles: P11, D6, D7, D13, D22, D23, D28
# See: HUMAN-AI-INTERACTION.md §7 (Sensors — Principle Regression Tests)

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

PASSED=0
TOTAL=5
FLAGS=""

# ─── Check 1: Readability regression (P11, D6, D13) ───────────────────────
# New .md files in holding/ or sutra/ created but not opened for founder review
check1_status="PASS"
check1_detail=""

# Find .md files added in recent commits
NEW_MD_FILES=$(git diff --name-only --diff-filter=A HEAD~5..HEAD 2>/dev/null | grep -E '^(holding|sutra)/.*\.md$' || true)

if [ -n "$NEW_MD_FILES" ]; then
  # Check git log for 'open' commands in recent commits (heuristic: if open was run,
  # it likely appeared in bash history or commit messages)
  OPEN_EVIDENCE=$(git log --oneline -5 --all 2>/dev/null | grep -i 'open' || true)

  # Also check if any recent bash commands include 'open' (from git diff of shell history)
  # Heuristic: if new system docs were created, they should have been opened
  FILE_COUNT=$(echo "$NEW_MD_FILES" | wc -l | tr -d ' ')

  if [ -z "$OPEN_EVIDENCE" ] && [ "$FILE_COUNT" -gt 0 ]; then
    check1_status="FLAG"
    check1_detail="$FILE_COUNT new system doc(s) created but no evidence of founder review (open command)"
  fi
fi

if [ "$check1_status" = "PASS" ]; then
  PASSED=$((PASSED + 1))
else
  FLAGS="$FLAGS\n  -> P11: $check1_detail"
fi

# ─── Check 2: Cascade check (D7) ──────────────────────────────────────────
# L0-L2 files changed without downstream TODO
check2_status="PASS"
check2_detail=""

L0_L2_CHANGES=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | grep -E '^(holding/|sutra/layer2-operating-system/)' || true)

if [ -n "$L0_L2_CHANGES" ]; then
  # Check if any recent commits mention downstream impact
  DOWNSTREAM_MENTION=$(git log -5 --format='%s %b' 2>/dev/null | grep -iE '(TODO|downstream|cascade|deploy to|update .* companies|propagate)' || true)

  if [ -z "$DOWNSTREAM_MENTION" ]; then
    CHANGED_COUNT=$(echo "$L0_L2_CHANGES" | wc -l | tr -d ' ')
    check2_status="FLAG"
    check2_detail="$CHANGED_COUNT L0-L2 file(s) changed with no downstream cascade mention"
  fi
fi

if [ "$check2_status" = "PASS" ]; then
  PASSED=$((PASSED + 1))
else
  FLAGS="$FLAGS\n  -> D7: $check2_detail"
fi

# ─── Check 3: Estimation compliance (D23) ─────────────────────────────────
# Agents dispatched without estimation tracking
check3_status="PASS"
check3_detail=""

ESTIMATION_LOG="$REPO_ROOT/holding/ESTIMATION-LOG.jsonl"

# Check if agents were dispatched (heuristic: git log mentions agent/parallel/dispatch)
AGENT_EVIDENCE=$(git log -5 --format='%s %b' 2>/dev/null | grep -iE '(agent|parallel|dispatch|subagent|concurrent)' || true)

if [ -n "$AGENT_EVIDENCE" ]; then
  # Check if estimation log was updated this session
  if [ -f "$ESTIMATION_LOG" ]; then
    ESTIMATION_UPDATED=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | grep 'ESTIMATION-LOG.jsonl' || true)
    if [ -z "$ESTIMATION_UPDATED" ]; then
      check3_status="FLAG"
      check3_detail="Agents dispatched without estimation tracking (ESTIMATION-LOG.jsonl not updated)"
    fi
  else
    check3_status="FLAG"
    check3_detail="Agents dispatched but ESTIMATION-LOG.jsonl does not exist"
  fi
fi

if [ "$check3_status" = "PASS" ]; then
  PASSED=$((PASSED + 1))
else
  FLAGS="$FLAGS\n  -> D23: $check3_detail"
fi

# ─── Check 4: Direction encoding (D28) ────────────────────────────────────
# Directions in FOUNDER-DIRECTIONS.md vs entries in DIRECTION-ENFORCEMENT.md
check4_status="PASS"
check4_detail=""

DIRECTIONS_FILE="$REPO_ROOT/holding/FOUNDER-DIRECTIONS.md"
ENFORCEMENT_FILE="$REPO_ROOT/holding/DIRECTION-ENFORCEMENT.md"

if [ -f "$DIRECTIONS_FILE" ] && [ -f "$ENFORCEMENT_FILE" ]; then
  # Count D## headers in directions file
  DIR_COUNT=$(grep -cE '^### D[0-9]+' "$DIRECTIONS_FILE" 2>/dev/null || echo "0")
  # Count D## headers in enforcement file
  ENF_COUNT=$(grep -cE '^## D[0-9]+' "$ENFORCEMENT_FILE" 2>/dev/null || echo "0")

  if [ "$DIR_COUNT" -gt "$ENF_COUNT" ]; then
    DELTA=$((DIR_COUNT - ENF_COUNT))
    check4_status="FLAG"
    check4_detail="$DELTA direction(s) not yet encoded in enforcement registry ($DIR_COUNT directions vs $ENF_COUNT enforcement entries)"
  fi
fi

if [ "$check4_status" = "PASS" ]; then
  PASSED=$((PASSED + 1))
else
  FLAGS="$FLAGS\n  -> D28: $check4_detail"
fi

# ─── Check 5: Parallelization audit (D22) ─────────────────────────────────
# Sequential commits that could have been parallel
check5_status="PASS"
check5_detail=""

# Get timestamps and directories of recent commits
COMMIT_DATA=$(git log -10 --format='%at %s' 2>/dev/null || true)

if [ -n "$COMMIT_DATA" ]; then
  # Find clusters: 3+ commits within 300 seconds (5 minutes)
  PREV_TS=0
  CLUSTER_COUNT=0
  CLUSTER_DIRS=""
  FOUND_PARALLEL_OPPORTUNITY=false

  while IFS= read -r line; do
    TS=$(echo "$line" | awk '{print $1}')

    if [ "$PREV_TS" -ne 0 ]; then
      DELTA_T=$((PREV_TS - TS))  # git log is newest-first, so prev > current

      if [ "$DELTA_T" -ge 0 ] && [ "$DELTA_T" -le 300 ]; then
        CLUSTER_COUNT=$((CLUSTER_COUNT + 1))
      else
        # Check if cluster was large enough
        if [ "$CLUSTER_COUNT" -ge 3 ]; then
          # Check if commits touch different directories
          CLUSTER_COMMITS=$(git log -"$CLUSTER_COUNT" --format='%H' 2>/dev/null | head -"$CLUSTER_COUNT")
          if [ -n "$CLUSTER_COMMITS" ]; then
            DIR_COUNT_UNIQUE=$(git log -"$CLUSTER_COUNT" --name-only --format='' 2>/dev/null | awk -F/ '{print $1}' | sort -u | wc -l | tr -d ' ')
            if [ "$DIR_COUNT_UNIQUE" -ge 2 ]; then
              FOUND_PARALLEL_OPPORTUNITY=true
            fi
          fi
        fi
        CLUSTER_COUNT=1
      fi
    else
      CLUSTER_COUNT=1
    fi

    PREV_TS=$TS
  done <<< "$COMMIT_DATA"

  # Check final cluster
  if [ "$CLUSTER_COUNT" -ge 3 ]; then
    DIR_COUNT_UNIQUE=$(git log -"$CLUSTER_COUNT" --name-only --format='' 2>/dev/null | awk -F/ '{print $1}' | sort -u | wc -l | tr -d ' ')
    if [ "$DIR_COUNT_UNIQUE" -ge 2 ]; then
      FOUND_PARALLEL_OPPORTUNITY=true
    fi
  fi

  if [ "$FOUND_PARALLEL_OPPORTUNITY" = true ]; then
    check5_status="FLAG"
    check5_detail="3+ sequential commits within 5min touching different directories — could have been parallelized"
  fi
fi

if [ "$check5_status" = "PASS" ]; then
  PASSED=$((PASSED + 1))
else
  FLAGS="$FLAGS\n  -> D22: $check5_detail"
fi

# ─── Output ───────────────────────────────────────────────────────────────

P11_ICON=$( [ "$check1_status" = "PASS" ] && echo "✅" || echo "⚠️" )
D7_ICON=$( [ "$check2_status" = "PASS" ] && echo "✅" || echo "⚠️" )
D23_ICON=$( [ "$check3_status" = "PASS" ] && echo "✅" || echo "⚠️" )
D28_ICON=$( [ "$check4_status" = "PASS" ] && echo "✅" || echo "⚠️" )
D22_ICON=$( [ "$check5_status" = "PASS" ] && echo "✅" || echo "⚠️" )

echo "═══ PRINCIPLE REGRESSION TEST ═══"
echo "$P11_ICON P11 Readability: $check1_status"
echo "$D7_ICON D7  Cascade: $check2_status"
echo "$D23_ICON D23 Estimation: $check3_status"
echo "$D28_ICON D28 Direction encoding: $check4_status"
echo "$D22_ICON D22 Parallelization: $check5_status"

if [ -n "$FLAGS" ]; then
  echo ""
  echo "Flags:"
  echo -e "$FLAGS"
fi

echo ""
echo "Score: $PASSED/$TOTAL passed"
echo "═══════════════════════════════"

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
