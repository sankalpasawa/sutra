#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Stop Dispatcher — Single-process execution of ALL Stop checks
# ═══════════════════════════════════════════════════════════════════════════════
# Replaces 11 individual Stop hook registrations with one shell process.
# All advisory (exit 0 always). Runs checks sequentially, emitting all output.
#
# Individual scripts kept in .claude/hooks/sutra/ for reference but are no longer
# registered as separate hooks.
# ═══════════════════════════════════════════════════════════════════════════════

set -o pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
HOOK_LOG="$REPO_ROOT/.claude/hooks/sutra/hook-log.jsonl"

# Health tracking
_HOOK_RAN=0
_HOOK_PASSED=0
_HOOK_FAILED=0
_HOOK_FAILURES=""

# Logging helper: log_hook HOOK_NAME STATUS [ERROR_MSG] START_SECONDS
log_hook() {
  local _name="$1" _status="$2" _error="$3" _start="$4"
  local _end=$(date +%s)
  local _ms=$(( (_end - _start) * 1000 ))
  _HOOK_RAN=$((_HOOK_RAN + 1))
  if [ "$_status" = "FAIL" ]; then
    _HOOK_FAILED=$((_HOOK_FAILED + 1))
    _HOOK_FAILURES="$_HOOK_FAILURES\n  $_name: $_error"
    echo "{\"ts\":$(date +%s),\"hook\":\"$_name\",\"event\":\"Stop\",\"status\":\"FAIL\",\"error\":\"$_error\",\"ms\":$_ms}" >> "$HOOK_LOG"
  else
    _HOOK_PASSED=$((_HOOK_PASSED + 1))
    echo "{\"ts\":$(date +%s),\"hook\":\"$_name\",\"event\":\"Stop\",\"status\":\"PASS\",\"ms\":$_ms}" >> "$HOOK_LOG"
  fi
}

# ─── 1. Session Checkpoint ────────────────────────────────────────────────────
# Source: .claude/hooks/sutra/session-checkpoint.sh
# Saves structured session state to holding/checkpoints/
_s1=$(date +%s)

CHECKPOINT_DIR="$REPO_ROOT/checkpoints"
TODAY=$(date -u +"%Y-%m-%d")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SHORT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "0000")
SESSION_ID="${TODAY}-${SHORT_HASH}"
CHECKPOINT_FILE="$CHECKPOINT_DIR/${TODAY}.json"

mkdir -p "$CHECKPOINT_DIR"

CREATED_JSON=$(git diff --name-only --diff-filter=A HEAD~10..HEAD 2>/dev/null | \
  awk 'BEGIN{first=1} {if(!first) printf ","; first=0; printf "\n    \"%s\"", $0} END{if(NR>0) printf "\n"}')

MODIFIED_JSON=$(git diff --name-only --diff-filter=M HEAD~10..HEAD 2>/dev/null | \
  awk 'BEGIN{first=1} {if(!first) printf ","; first=0; printf "\n    \"%s\"", $0} END{if(NR>0) printf "\n"}')

COMMIT_COUNT=$(git log --oneline HEAD~10..HEAD 2>/dev/null | wc -l | tr -d ' ')
COMMIT_HASHES_JSON=$(git log --format='%h' HEAD~10..HEAD 2>/dev/null | \
  awk 'BEGIN{first=1} {if(!first) printf ","; first=0; printf "\n    \"%s\"", $0} END{if(NR>0) printf "\n"}')

DIRECTION_COUNT=$(grep -c "^### D[0-9]" "$REPO_ROOT/FOUNDER-DIRECTIONS.md" 2>/dev/null || echo "0")
ENFORCEMENT_COUNT=$(grep -c "^## D[0-9]" "$REPO_ROOT/DIRECTION-ENFORCEMENT.md" 2>/dev/null || echo "0")

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
echo ""
echo "Per D18: Generate 'Your Day' dashboard before ending."
echo "Show: founder contributions, LLM contributions, what shipped, what's next."
log_hook "SessionCheckpoint" "PASS" "" "$_s1"

# ─── 2. Test in Production Check (D1) ────────────────────────────────────────
# Source: .claude/hooks/sutra/test-in-production-check.sh
_s2=$(date +%s)

NEW_FILES=$(cd "$REPO_ROOT" && git diff --name-only --diff-filter=A HEAD 2>/dev/null | grep -E '^(holding|sutra)/.*\.md$')

if [ -n "$NEW_FILES" ]; then
  echo ""
  echo "Warning: Per D1: New system artifacts created but not tested in production."
  echo "Verify each against a real task:"
  echo "$NEW_FILES" | while read -r f; do echo "  - $f"; done
fi
log_hook "TestInProduction-D1" "PASS" "" "$_s2"

# ─── 3. Time Allocation Tracker (D12) ────────────────────────────────────────
# Source: .claude/hooks/sutra/time-allocation-tracker.sh
_s3=$(date +%s)

CHANGED_FILES=$(cd "$REPO_ROOT" && git diff --name-only HEAD 2>/dev/null; cd "$REPO_ROOT" && git diff --name-only --cached 2>/dev/null)

if [ -n "$CHANGED_FILES" ]; then
  PRODUCT_COUNT=$(echo "$CHANGED_FILES" | grep -cE '^(dayflow|maze|ppr|jarvis)/' 2>/dev/null || echo 0)
  OS_COUNT=$(echo "$CHANGED_FILES" | grep -cE '^(sutra|holding)/' 2>/dev/null || echo 0)
  OTHER_COUNT=$(echo "$CHANGED_FILES" | grep -vcE '^(dayflow|maze|ppr|jarvis|sutra|holding)/' 2>/dev/null || echo 0)
  TOTAL=$((PRODUCT_COUNT + OS_COUNT + OTHER_COUNT))

  if [ "$TOTAL" -gt 0 ]; then
    echo ""
    echo "Session allocation: $PRODUCT_COUNT product files, $OS_COUNT OS files, $OTHER_COUNT other. Target: 70/20/10."
  fi
fi
log_hook "TimeAllocation-D12" "PASS" "" "$_s3"

# ─── 4. Principle Regression (D27) ───────────────────────────────────────────
# Source: .claude/hooks/sutra/principle-regression.sh
# 5 automated checks: P11 Readability, D7 Cascade, D23 Estimation, D28 Direction encoding, D22 Parallelization
_s4=$(date +%s)

PR_PASSED=0
PR_TOTAL=5
PR_FLAGS=""

# Check 4a: Readability regression (P11, D6, D13)
pr_check1_status="PASS"
pr_check1_detail=""

NEW_MD_FILES=$(git diff --name-only --diff-filter=A HEAD~5..HEAD 2>/dev/null | grep -E '^(holding|sutra)/.*\.md$' || true)

if [ -n "$NEW_MD_FILES" ]; then
  OPEN_EVIDENCE=$(git log --oneline -5 --all 2>/dev/null | grep -i 'open' || true)
  FILE_COUNT_MD=$(echo "$NEW_MD_FILES" | wc -l | tr -d ' ')

  if [ -z "$OPEN_EVIDENCE" ] && [ "$FILE_COUNT_MD" -gt 0 ]; then
    pr_check1_status="FLAG"
    pr_check1_detail="$FILE_COUNT_MD new system doc(s) created but no evidence of founder review (open command)"
  fi
fi

[ "$pr_check1_status" = "PASS" ] && PR_PASSED=$((PR_PASSED + 1)) || PR_FLAGS="$PR_FLAGS\n  -> P11: $pr_check1_detail"

# Check 4b: Cascade check (D7)
pr_check2_status="PASS"
pr_check2_detail=""

L0_L2_CHANGES=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | grep -E '^(holding/|sutra/layer2-operating-system/)' || true)

if [ -n "$L0_L2_CHANGES" ]; then
  DOWNSTREAM_MENTION=$(git log -5 --format='%s %b' 2>/dev/null | grep -iE '(TODO|downstream|cascade|deploy to|update .* companies|propagate)' || true)

  if [ -z "$DOWNSTREAM_MENTION" ]; then
    CHANGED_COUNT_L0=$(echo "$L0_L2_CHANGES" | wc -l | tr -d ' ')
    pr_check2_status="FLAG"
    pr_check2_detail="$CHANGED_COUNT_L0 L0-L2 file(s) changed with no downstream cascade mention"
  fi
fi

[ "$pr_check2_status" = "PASS" ] && PR_PASSED=$((PR_PASSED + 1)) || PR_FLAGS="$PR_FLAGS\n  -> D7: $pr_check2_detail"

# Check 4c: Estimation compliance (D23)
pr_check3_status="PASS"
pr_check3_detail=""

ESTIMATION_LOG="$REPO_ROOT/ESTIMATION-LOG.jsonl"
AGENT_EVIDENCE=$(git log -5 --format='%s %b' 2>/dev/null | grep -iE '(agent|parallel|dispatch|subagent|concurrent)' || true)

if [ -n "$AGENT_EVIDENCE" ]; then
  if [ -f "$ESTIMATION_LOG" ]; then
    ESTIMATION_UPDATED=$(git diff --name-only HEAD~5..HEAD 2>/dev/null | grep 'ESTIMATION-LOG.jsonl' || true)
    if [ -z "$ESTIMATION_UPDATED" ]; then
      pr_check3_status="FLAG"
      pr_check3_detail="Agents dispatched without estimation tracking (ESTIMATION-LOG.jsonl not updated)"
    fi
  else
    pr_check3_status="FLAG"
    pr_check3_detail="Agents dispatched but ESTIMATION-LOG.jsonl does not exist"
  fi
fi

[ "$pr_check3_status" = "PASS" ] && PR_PASSED=$((PR_PASSED + 1)) || PR_FLAGS="$PR_FLAGS\n  -> D23: $pr_check3_detail"

# Check 4d: Direction encoding (D28)
pr_check4_status="PASS"
pr_check4_detail=""

DIRECTIONS_FILE="$REPO_ROOT/FOUNDER-DIRECTIONS.md"
ENFORCEMENT_FILE="$REPO_ROOT/DIRECTION-ENFORCEMENT.md"

if [ -f "$DIRECTIONS_FILE" ] && [ -f "$ENFORCEMENT_FILE" ]; then
  DIR_COUNT_D=$(grep -cE '^### D[0-9]+' "$DIRECTIONS_FILE" 2>/dev/null || echo "0")
  ENF_COUNT_D=$(grep -cE '^## D[0-9]+' "$ENFORCEMENT_FILE" 2>/dev/null || echo "0")

  if [ "$DIR_COUNT_D" -gt "$ENF_COUNT_D" ]; then
    DELTA_D=$((DIR_COUNT_D - ENF_COUNT_D))
    pr_check4_status="FLAG"
    pr_check4_detail="$DELTA_D direction(s) not yet encoded in enforcement registry ($DIR_COUNT_D directions vs $ENF_COUNT_D enforcement entries)"
  fi
fi

[ "$pr_check4_status" = "PASS" ] && PR_PASSED=$((PR_PASSED + 1)) || PR_FLAGS="$PR_FLAGS\n  -> D28: $pr_check4_detail"

# Check 4e: Parallelization audit (D22)
pr_check5_status="PASS"
pr_check5_detail=""

COMMIT_DATA=$(git log -10 --format='%at %s' 2>/dev/null || true)

if [ -n "$COMMIT_DATA" ]; then
  PREV_TS=0
  CLUSTER_COUNT=0
  FOUND_PARALLEL_OPPORTUNITY=false

  while IFS= read -r line; do
    TS=$(echo "$line" | awk '{print $1}')

    if [ "$PREV_TS" -ne 0 ]; then
      DELTA_T=$((PREV_TS - TS))

      if [ "$DELTA_T" -ge 0 ] && [ "$DELTA_T" -le 300 ]; then
        CLUSTER_COUNT=$((CLUSTER_COUNT + 1))
      else
        if [ "$CLUSTER_COUNT" -ge 3 ]; then
          DIR_COUNT_UNIQUE=$(git log -"$CLUSTER_COUNT" --name-only --format='' 2>/dev/null | awk -F/ '{print $1}' | sort -u | wc -l | tr -d ' ')
          if [ "$DIR_COUNT_UNIQUE" -ge 2 ]; then
            FOUND_PARALLEL_OPPORTUNITY=true
          fi
        fi
        CLUSTER_COUNT=1
      fi
    else
      CLUSTER_COUNT=1
    fi

    PREV_TS=$TS
  done <<< "$COMMIT_DATA"

  if [ "$CLUSTER_COUNT" -ge 3 ]; then
    DIR_COUNT_UNIQUE=$(git log -"$CLUSTER_COUNT" --name-only --format='' 2>/dev/null | awk -F/ '{print $1}' | sort -u | wc -l | tr -d ' ')
    if [ "$DIR_COUNT_UNIQUE" -ge 2 ]; then
      FOUND_PARALLEL_OPPORTUNITY=true
    fi
  fi

  if [ "$FOUND_PARALLEL_OPPORTUNITY" = true ]; then
    pr_check5_status="FLAG"
    pr_check5_detail="3+ sequential commits within 5min touching different directories — could have been parallelized"
  fi
fi

[ "$pr_check5_status" = "PASS" ] && PR_PASSED=$((PR_PASSED + 1)) || PR_FLAGS="$PR_FLAGS\n  -> D22: $pr_check5_detail"

P11_ICON=$( [ "$pr_check1_status" = "PASS" ] && echo "+" || echo "!" )
D7_ICON=$( [ "$pr_check2_status" = "PASS" ] && echo "+" || echo "!" )
D23_ICON=$( [ "$pr_check3_status" = "PASS" ] && echo "+" || echo "!" )
D28_ICON=$( [ "$pr_check4_status" = "PASS" ] && echo "+" || echo "!" )
D22_ICON=$( [ "$pr_check5_status" = "PASS" ] && echo "+" || echo "!" )

echo ""
echo "=== PRINCIPLE REGRESSION TEST ==="
echo "$P11_ICON P11 Readability: $pr_check1_status"
echo "$D7_ICON D7  Cascade: $pr_check2_status"
echo "$D23_ICON D23 Estimation: $pr_check3_status"
echo "$D28_ICON D28 Direction encoding: $pr_check4_status"
echo "$D22_ICON D22 Parallelization: $pr_check5_status"

if [ -n "$PR_FLAGS" ]; then
  echo ""
  echo "Flags:"
  echo -e "$PR_FLAGS"
fi

echo ""
echo "Score: $PR_PASSED/$PR_TOTAL passed"
echo "==============================="
if [ "$PR_PASSED" -eq "$PR_TOTAL" ]; then
  log_hook "PrincipleRegression-D27" "PASS" "" "$_s4"
else
  log_hook "PrincipleRegression-D27" "FAIL" "$((PR_TOTAL - PR_PASSED)) of $PR_TOTAL checks flagged" "$_s4"
fi

# ─── 5. Principle Regression Tests Suite ─────────────────────────────────────
# Source: .claude/hooks/sutra/principle-regression-tests.sh
# 7 standalone checks: D1, D5, D6, D10, D12, D13, VER
_s5=$(date +%s)

PRT_PASSED=0
PRT_FAILED=0
PRT_TOTAL=7
PRT_RESULTS=""

prt_pass() {
  PRT_PASSED=$((PRT_PASSED + 1))
  PRT_RESULTS="$PRT_RESULTS\n+ $1"
}

prt_fail() {
  PRT_FAILED=$((PRT_FAILED + 1))
  PRT_RESULTS="$PRT_RESULTS\n- $1"
}

# D1: Simplicity — governance file count
LIMIT=40
GOV_COUNT=$(find "$REPO_ROOT/holding" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "$GOV_COUNT" -le "$LIMIT" ]; then
  prt_pass "D1:  Governance files: $GOV_COUNT (limit: $LIMIT)"
else
  prt_fail "D1:  Governance files: $GOV_COUNT exceeds limit of $LIMIT"
fi

# D5: External Research — REFERENCES.md in each company submodule
SUBMODULES="dayflow maze ppr paisa"
D5_MISSING=""
D5_OK=true
for sub in $SUBMODULES; do
  if [ -d "$REPO_ROOT/$sub" ] && [ ! -f "$REPO_ROOT/$sub/REFERENCES.md" ]; then
    D5_MISSING="$D5_MISSING $sub/"
    D5_OK=false
  fi
done
if [ "$D5_OK" = true ]; then
  prt_pass "D5:  REFERENCES.md present in all company submodules"
else
  prt_fail "D5: ${D5_MISSING} missing REFERENCES.md"
fi

# D6: Directions Executable — all D# numbers encoded
if [ -f "$DIRECTIONS_FILE" ] && [ -f "$ENFORCEMENT_FILE" ]; then
  PRT_DIR_COUNT=$(grep -cE '^### D[0-9]+' "$DIRECTIONS_FILE" 2>/dev/null || echo "0")
  PRT_ENF_COUNT=$(grep -cE '^## D[0-9]+' "$ENFORCEMENT_FILE" 2>/dev/null || echo "0")
  if [ "$PRT_DIR_COUNT" -le "$PRT_ENF_COUNT" ]; then
    prt_pass "D6:  $PRT_ENF_COUNT/$PRT_DIR_COUNT directions encoded"
  else
    PRT_DELTA=$((PRT_DIR_COUNT - PRT_ENF_COUNT))
    prt_fail "D6:  $PRT_ENF_COUNT/$PRT_DIR_COUNT directions encoded ($PRT_DELTA missing)"
  fi
else
  prt_fail "D6:  Missing FOUNDER-DIRECTIONS.md or DIRECTION-ENFORCEMENT.md"
fi

# D10: Test in Production — no protocol UNTESTED >7 days
TIP_FILE="$REPO_ROOT/TEST-IN-PRODUCTION.md"
D10_OK=true
if [ -f "$TIP_FILE" ]; then
  SEVEN_DAYS_AGO=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '7 days ago' +%Y-%m-%d 2>/dev/null)
  if [ -n "$SEVEN_DAYS_AGO" ]; then
    while IFS= read -r line; do
      FOUND_DATE=$(echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
      if [ -n "$FOUND_DATE" ] && [[ "$FOUND_DATE" < "$SEVEN_DAYS_AGO" ]]; then
        D10_OK=false
        break
      fi
    done < <(grep -i 'UNTESTED' "$TIP_FILE" 2>/dev/null || true)
  fi
fi
if [ "$D10_OK" = true ]; then
  prt_pass "D10: No protocols UNTESTED >7 days"
else
  prt_fail "D10: Protocol(s) marked UNTESTED for >7 days in TEST-IN-PRODUCTION.md"
fi

# D12: Architecture Awareness — SYSTEM-MAP.md freshness
SYSMAP="$REPO_ROOT/SYSTEM-MAP.md"
if [ -f "$SYSMAP" ]; then
  if [[ "$(uname)" == "Darwin" ]]; then
    LAST_MOD=$(stat -f %m "$SYSMAP" 2>/dev/null)
  else
    LAST_MOD=$(stat -c %Y "$SYSMAP" 2>/dev/null)
  fi
  NOW=$(date +%s)
  SEVEN_DAYS=$((7 * 86400))
  AGE=$((NOW - LAST_MOD))
  if [ "$AGE" -le "$SEVEN_DAYS" ]; then
    DAYS_AGO=$((AGE / 86400))
    prt_pass "D12: SYSTEM-MAP.md updated ${DAYS_AGO}d ago (limit: 7d)"
  else
    DAYS_AGO=$((AGE / 86400))
    prt_fail "D12: SYSTEM-MAP.md is ${DAYS_AGO}d old — stale (limit: 7d)"
  fi
else
  prt_fail "D12: SYSTEM-MAP.md not found"
fi

# D13: Cascade — holding/ changes have downstream TODOs
D13_OK=true
HOLDING_CHANGES=$(git -C "$REPO_ROOT" diff --name-only HEAD~5..HEAD 2>/dev/null | grep -E '^holding/' || true)
if [ -n "$HOLDING_CHANGES" ]; then
  CASCADE_MENTION=$(git -C "$REPO_ROOT" log -5 --format='%s %b' 2>/dev/null | grep -iE '(TODO|downstream|cascade|propagate|deploy to)' || true)
  if [ -z "$CASCADE_MENTION" ]; then
    D13_CHANGE_COUNT=$(echo "$HOLDING_CHANGES" | wc -l | tr -d ' ')
    D13_OK=false
  fi
fi
if [ "$D13_OK" = true ]; then
  prt_pass "D13: No holding/ changes without downstream TODOs"
else
  prt_fail "D13: $D13_CHANGE_COUNT holding/ file(s) changed with no cascade mention"
fi

# VER: CURRENT-VERSION.md matches latest in RELEASES.md
CV_FILE="$REPO_ROOT/sutra/CURRENT-VERSION.md"
REL_FILE="$REPO_ROOT/sutra/RELEASES.md"
if [ ! -f "$CV_FILE" ]; then
  prt_fail "VER: CURRENT-VERSION.md not found"
elif [ ! -f "$REL_FILE" ]; then
  prt_fail "VER: RELEASES.md not found"
else
  CV_VER=$(grep -oE 'v[0-9]+\.[0-9]+' "$CV_FILE" | head -1)
  REL_VER=$(grep -oE 'v[0-9]+\.[0-9]+' "$REL_FILE" | head -1)
  if [ -n "$CV_VER" ] && [ -n "$REL_VER" ]; then
    if [ "$CV_VER" = "$REL_VER" ] || [[ "$CV_VER" > "$REL_VER" ]]; then
      prt_pass "VER: CURRENT-VERSION.md ($CV_VER) matches/ahead of RELEASES.md ($REL_VER)"
    else
      prt_fail "VER: CURRENT-VERSION.md ($CV_VER) behind RELEASES.md ($REL_VER)"
    fi
  else
    prt_fail "VER: Could not parse versions (CV=$CV_VER, REL=$REL_VER)"
  fi
fi

echo ""
echo "=== PRINCIPLE REGRESSION TESTS ==="
echo -e "$PRT_RESULTS"
echo ""
echo "PASSED: $PRT_PASSED/$PRT_TOTAL  FAILED: $PRT_FAILED/$PRT_TOTAL"
echo "=================================="
if [ "$PRT_FAILED" -eq 0 ]; then
  log_hook "PrincipleRegressionTests" "PASS" "" "$_s5"
else
  log_hook "PrincipleRegressionTests" "FAIL" "$PRT_FAILED of $PRT_TOTAL tests failed" "$_s5"
fi

# ─── 6. Lifecycle Coverage Check (D3) ────────────────────────────────────────
# Source: .claude/hooks/sutra/lifecycle-check.sh
_s6=$(date +%s)

SINCE_LC=$(date -v-4H +"%Y-%m-%dT%H:%M:%S" 2>/dev/null || date -d '4 hours ago' +"%Y-%m-%dT%H:%M:%S" 2>/dev/null)

if [ -z "$SINCE_LC" ]; then
  LC_COMMITS=$(git log -10 --format='%H' 2>/dev/null)
else
  LC_COMMITS=$(git log --since="$SINCE_LC" --format='%H' 2>/dev/null)
fi

SOURCE_PATTERNS="^(src/|app/|lib/|features/|components/|pages/|.*/(src|app|lib|features|components|pages)/)"

LC_TOTAL=0
LC_LIFECYCLE=0
LC_BYPASS=0
LC_BYPASS_DETAILS=""

while IFS= read -r COMMIT; do
  [ -z "$COMMIT" ] && continue

  FILES_CHANGED_LC=$(git diff-tree --no-commit-id --name-only -r "$COMMIT" 2>/dev/null)
  SOURCE_FILES_LC=$(echo "$FILES_CHANGED_LC" | grep -E "$SOURCE_PATTERNS" || true)

  if [ -z "$SOURCE_FILES_LC" ]; then
    continue
  fi

  LC_TOTAL=$((LC_TOTAL + 1))
  COMMIT_MSG_LC=$(git log -1 --format='%s' "$COMMIT" 2>/dev/null)
  COMMIT_SHORT_LC=$(git log -1 --format='%h' "$COMMIT" 2>/dev/null)

  HAS_EVIDENCE_LC=false

  if [ -f "$ESTIMATION_LOG" ]; then
    ESTIMATION_IN_COMMIT_LC=$(git diff-tree --no-commit-id --name-only -r "$COMMIT" 2>/dev/null | grep 'ESTIMATION-LOG.jsonl' || true)
    if [ -n "$ESTIMATION_IN_COMMIT_LC" ]; then
      HAS_EVIDENCE_LC=true
    fi
  fi

  MSG_LENGTH_LC=${#COMMIT_MSG_LC}
  HAS_CONTEXT_LC=$(echo "$COMMIT_MSG_LC" | grep -E '(:|#|—|→|phase|lifecycle|D[0-9]+|level [0-9]|estimate|plan)' || true)

  if [ "$MSG_LENGTH_LC" -gt 30 ] || [ -n "$HAS_CONTEXT_LC" ]; then
    HAS_EVIDENCE_LC=true
  fi

  if [ -f "$ESTIMATION_LOG" ] && [ "$HAS_EVIDENCE_LC" = false ]; then
    FIRST_FILE_LC=$(echo "$SOURCE_FILES_LC" | head -1)
    FILE_BASENAME_LC=$(basename "$FIRST_FILE_LC" 2>/dev/null)
    if [ -n "$FILE_BASENAME_LC" ]; then
      LOG_MATCH_LC=$(grep -l "$FILE_BASENAME_LC" "$ESTIMATION_LOG" 2>/dev/null || true)
      if [ -n "$LOG_MATCH_LC" ]; then
        HAS_EVIDENCE_LC=true
      fi
    fi
  fi

  COMMIT_BODY_LC=$(git log -1 --format='%b' "$COMMIT" 2>/dev/null)
  if [ -n "$COMMIT_BODY_LC" ]; then
    BODY_EVIDENCE_LC=$(echo "$COMMIT_BODY_LC" | grep -iE '(think|pre|execute|post|compress|estimation|level [0-9]|thoroughness|complexity|impact)' || true)
    if [ -n "$BODY_EVIDENCE_LC" ]; then
      HAS_EVIDENCE_LC=true
    fi
  fi

  if [ "$HAS_EVIDENCE_LC" = true ]; then
    LC_LIFECYCLE=$((LC_LIFECYCLE + 1))
  else
    LC_BYPASS=$((LC_BYPASS + 1))
    LC_BYPASS_DETAILS="$LC_BYPASS_DETAILS\n  -> $COMMIT_SHORT_LC: \"$COMMIT_MSG_LC\""
  fi
done <<< "$LC_COMMITS"

echo ""
echo "=== LIFECYCLE COVERAGE CHECK (D3) ==="
if [ "$LC_TOTAL" -eq 0 ]; then
  echo "No source-code commits this session. Nothing to audit."
else
  if [ "$LC_BYPASS" -eq 0 ]; then
    LC_ICON="+"
  else
    LC_ICON="!"
  fi
  echo "$LC_ICON Lifecycle coverage: $LC_LIFECYCLE/$LC_TOTAL tasks had lifecycle evidence."

  if [ "$LC_BYPASS" -gt 0 ]; then
    echo ""
    echo "$LC_BYPASS task(s) may have bypassed the lifecycle:"
    echo -e "$LC_BYPASS_DETAILS"
    echo ""
    echo "Reminder: THINK->PRE->EXECUTE->POST->COMPRESS (TASK-LIFECYCLE.md)"
  fi
fi
echo "======================================"
if [ "$LC_BYPASS" -eq 0 ]; then
  log_hook "LifecycleCoverage-D3" "PASS" "" "$_s6"
else
  log_hook "LifecycleCoverage-D3" "FAIL" "$LC_BYPASS task(s) bypassed lifecycle" "$_s6"
fi

# ─── 7. Auto-push Warning ────────────────────────────────────────────────────
# Source: .claude/hooks/sutra/auto-push.sh
_s7=$(date +%s)

warnings=""

check_repo() {
  local dir="$1"
  local name="$2"

  cd "$dir" 2>/dev/null || return

  local uncommitted=0
  local unpushed=0

  uncommitted=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  if git rev-parse --verify origin/main &>/dev/null; then
    unpushed=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
  elif git rev-parse --verify origin/master &>/dev/null; then
    unpushed=$(git log origin/master..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
  fi

  if [ "$uncommitted" -gt 0 ] || [ "$unpushed" -gt 0 ]; then
    warnings="${warnings}\n  ${name}: ${uncommitted} files uncommitted, ${unpushed} commits unpushed"
  fi
}

check_repo "$REPO_ROOT" "asawa-holding"

for sub in dayflow sutra maze ppr jarvis; do
  sub_path="$REPO_ROOT/$sub"
  if [ -d "$sub_path/.git" ] || [ -f "$sub_path/.git" ]; then
    check_repo "$sub_path" "$sub"
  fi
done

if [ -n "$warnings" ]; then
  echo ""
  echo "BACKUP RISK — unpushed work detected:"
  echo -e "$warnings"
  echo ""
  echo "Run: git add + commit + push before ending session."
  echo ""
fi
if [ -n "$warnings" ]; then
  log_hook "AutoPushWarning" "FAIL" "Unpushed work detected" "$_s7"
else
  log_hook "AutoPushWarning" "PASS" "" "$_s7"
fi

# ─── 8. KPI Tracker ──────────────────────────────────────────────────────────
# Source: .claude/hooks/sutra/kpi-tracker.sh
_s8=$(date +%s)

BASELINE_FILES=136
BASELINE_ACCURACY=78

KPI_FILE_COUNT=$(find "$REPO_ROOT/holding" "$REPO_ROOT/sutra" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
C_DELTA_KPI=$((KPI_FILE_COUNT - BASELINE_FILES))
if [ "$C_DELTA_KPI" -gt 0 ]; then
  C_SIGN_KPI="+"
else
  C_SIGN_KPI=""
fi

KPI_LOG_FILE="$REPO_ROOT/ESTIMATION-LOG.jsonl"
A_DISPLAY_KPI="N/A"
A_DELTA_DISPLAY_KPI="no data"

if [ -f "$KPI_LOG_FILE" ]; then
  ACCURACIES_KPI=$(tail -20 "$KPI_LOG_FILE" | grep -v '^$' | tail -5 | \
    sed -n 's/.*"tokens_pct":\([0-9.]*\).*/\1/p')

  if [ -n "$ACCURACIES_KPI" ]; then
    A_MEAN_KPI=$(echo "$ACCURACIES_KPI" | awk '{sum += $1; n++} END {if(n>0) printf "%d", (sum/n)*100; else print "0"}')
    A_DELTA_KPI=$((A_MEAN_KPI - BASELINE_ACCURACY))
    if [ "$A_DELTA_KPI" -gt 0 ]; then
      A_DELTA_DISPLAY_KPI="+${A_DELTA_KPI}%"
    else
      A_DELTA_DISPLAY_KPI="${A_DELTA_KPI}%"
    fi
    A_DISPLAY_KPI="${A_MEAN_KPI}%"
  fi
fi

KPI_REGRESSION=""
C_THRESHOLD_KPI=$(( BASELINE_FILES * 5 / 100 ))
if [ "$C_DELTA_KPI" -gt "$C_THRESHOLD_KPI" ]; then
  KPI_REGRESSION="${KPI_REGRESSION}\n  !! C REGRESSION: file count grew >${C_THRESHOLD_KPI} beyond baseline"
fi
if [ "$A_DISPLAY_KPI" != "N/A" ]; then
  if [ "$A_MEAN_KPI" -lt $((BASELINE_ACCURACY * 95 / 100)) ]; then
    KPI_REGRESSION="${KPI_REGRESSION}\n  !! A REGRESSION: accuracy dropped below ${BASELINE_ACCURACY}% - 5% threshold"
  fi
fi

echo ""
echo "=== SUTRA KPI DELTA ==="
echo "C (Cognitive Load): ${KPI_FILE_COUNT} files (baseline: ${BASELINE_FILES}, delta: ${C_SIGN_KPI}${C_DELTA_KPI})"
echo "A (Accuracy):       ${A_DISPLAY_KPI} (baseline: ${BASELINE_ACCURACY}%, delta: ${A_DELTA_DISPLAY_KPI})"
echo "======================="

if [ -n "$KPI_REGRESSION" ]; then
  echo -e "$KPI_REGRESSION"
  echo ""
  log_hook "KPITracker" "FAIL" "KPI regression detected" "$_s8"
else
  log_hook "KPITracker" "PASS" "" "$_s8"
fi

# ─── 9. Cascade Check (D7) ───────────────────────────────────────────────────
# Source: .claude/hooks/sutra/cascade-check.sh
# Note: This is the PostToolUse version repurposed as Stop check.
# Checks if L0-L2 files changed and reminds about downstream.

# Already covered by principle-regression check 4b (D7) above — skip duplicate.
_s9=$(date +%s)
log_hook "CascadeCheck-D7" "PASS" "" "$_s9"

# ─── 10. Process Fix Check (D2) ──────────────────────────────────────────────
# Source: .claude/hooks/sutra/process-fix-check.sh
_s10=$(date +%s)

LAST_MSG_PF=$(cd "$REPO_ROOT" && git log -1 --oneline 2>/dev/null)

if echo "$LAST_MSG_PF" | grep -iqE '\b(fix|bug|patch|hotfix)\b'; then
  echo ""
  echo "Warning: Per D2: Bug fix detected in recent commit: $LAST_MSG_PF"
  echo "Did you also fix the PROCESS that allowed this bug?"
  echo "Root cause -> process improvement required."
fi
log_hook "ProcessFixCheck-D2" "PASS" "" "$_s10"

# ─── 11. Context Budget Check ────────────────────────────────────────────────
# Source: .claude/hooks/sutra/context-budget-check.sh
_s11=$(date +%s)

TRANSCRIPT="${CLAUDE_TRANSCRIPT:-}"
_cb_status="PASS"
_cb_error=""
if [ -n "$TRANSCRIPT" ]; then
  CB_COUNT=$(echo "$TRANSCRIPT" | grep -oE '(holding|sutra)/[^ "]*\.md' | sort -u | wc -l | tr -d ' ')

  if [ "$CB_COUNT" -gt 10 ]; then
    echo ""
    echo "CONTEXT BUDGET WARNING: ${CB_COUNT} governance files loaded. Target: <10. Consider lazy loading."
    _cb_status="FAIL"
    _cb_error="${CB_COUNT} governance files loaded (limit: 10)"
  fi
fi
log_hook "ContextBudget" "$_cb_status" "$_cb_error" "$_s11"

# ─── Health Summary ──────────────────────────────────────────────────────────
echo ""
echo "═══ HOOK HEALTH ═══"
echo "Ran: $_HOOK_RAN  Passed: $_HOOK_PASSED  Failed: $_HOOK_FAILED"
if [ "$_HOOK_FAILED" -gt 0 ]; then
  echo -e "$_HOOK_FAILURES"
fi
echo "═══════════════════"

# ─── Done ─────────────────────────────────────────────────────────────────────
exit 0
