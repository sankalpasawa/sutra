#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Stop Dispatcher — Single-process execution of ALL Stop checks
# ═══════════════════════════════════════════════════════════════════════════════
# Replaces 11 individual Stop hook registrations with one shell process.
# All advisory (exit 0 always). Runs checks sequentially, emitting all output.
#
# Individual scripts kept in holding/hooks/ for reference but are no longer
# registered as separate hooks.
# ═══════════════════════════════════════════════════════════════════════════════

set -o pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
HOOK_LOG="$REPO_ROOT/holding/hooks/hook-log.jsonl"

# Stop hooks receive JSON on stdin (transcript_path, session_id, etc.).
# Capture once at dispatcher entry so downstream sections (triage-collector)
# can re-use it. Safe when stdin is empty/TTY — read returns immediately.
_STOP_STDIN=""
if [ ! -t 0 ]; then
  _STOP_STDIN=$(cat 2>/dev/null || true)
fi
export _STOP_STDIN

# Health tracking
_HOOK_RAN=0
_HOOK_PASSED=0
_HOOK_FAILED=0
_HOOK_FAILURES=""

# ms-resolution wall-clock helper (slowness #1, 2026-04-16) — matches
# dispatcher-pretool.sh. EPOCHREALTIME (bash 5) → gdate → python3 → date.
_now_ms() {
  if [ -n "${EPOCHREALTIME:-}" ]; then
    local _er="${EPOCHREALTIME/./}"
    printf '%s\n' "${_er:0:13}"
  elif command -v gdate >/dev/null 2>&1; then
    gdate +%s%3N
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import time; print(int(time.time()*1000))'
  else
    echo $(( $(date +%s) * 1000 ))
  fi
}

# Logging helper: log_hook HOOK_NAME STATUS [ERROR_MSG] START_MS
log_hook() {
  local _name="$1" _status="$2" _error="$3" _start="$4"
  local _end
  _end=$(_now_ms)
  local _ms=$(( _end - _start ))
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
# Source: holding/hooks/session-checkpoint.sh
# Saves structured session state to holding/checkpoints/
_s1=$(_now_ms)

CHECKPOINT_DIR="$REPO_ROOT/holding/checkpoints"
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

DIRECTION_COUNT=$(grep -c "^### D[0-9]" "$REPO_ROOT/holding/FOUNDER-DIRECTIONS.md" 2>/dev/null || echo "0")
ENFORCEMENT_COUNT=$(grep -c "^## D[0-9]" "$REPO_ROOT/holding/DIRECTION-ENFORCEMENT.md" 2>/dev/null || echo "0")

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
# D19 "Your Day" dashboard rendered by section 15 (session-end-satisfaction.sh)
# — removed mislabeled "Per D18" reminder 2026-04-22.
log_hook "SessionCheckpoint" "PASS" "" "$_s1"

# ─── 2. Test in Production Check (D1) ────────────────────────────────────────
# Source: holding/hooks/test-in-production-check.sh
_s2=$(_now_ms)

NEW_FILES=$(cd "$REPO_ROOT" && git diff --name-only --diff-filter=A HEAD 2>/dev/null | grep -E '^(holding|sutra)/.*\.md$')

if [ -n "$NEW_FILES" ]; then
  echo ""
  echo "Warning: Per D1: New system artifacts created but not tested in production."
  echo "Verify each against a real task:"
  echo "$NEW_FILES" | while read -r f; do echo "  - $f"; done
fi
log_hook "TestInProduction-D1" "PASS" "" "$_s2"

# ─── 3. Time Allocation Tracker (D12) ────────────────────────────────────────
# Source: holding/hooks/time-allocation-tracker.sh
_s3=$(_now_ms)

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
# Source: holding/hooks/principle-regression.sh
# 5 automated checks: P11 Readability, D7 Cascade, D23 Estimation, D28 Direction encoding, D22 Parallelization
_s4=$(_now_ms)

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

ESTIMATION_LOG="$REPO_ROOT/holding/ESTIMATION-LOG.jsonl"
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

DIRECTIONS_FILE="$REPO_ROOT/holding/FOUNDER-DIRECTIONS.md"
ENFORCEMENT_FILE="$REPO_ROOT/holding/DIRECTION-ENFORCEMENT.md"

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
# Source: holding/hooks/principle-regression-tests.sh
# 7 standalone checks: D1, D5, D6, D10, D12, D13, VER
_s5=$(_now_ms)

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
TIP_FILE="$REPO_ROOT/holding/TEST-IN-PRODUCTION.md"
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
SYSMAP="$REPO_ROOT/holding/SYSTEM-MAP.md"
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
# Source: holding/hooks/lifecycle-check.sh
_s6=$(_now_ms)

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
# Source: holding/hooks/auto-push.sh
_s7=$(_now_ms)

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
# Source: holding/hooks/kpi-tracker.sh
_s8=$(_now_ms)

BASELINE_FILES=136
BASELINE_ACCURACY=78

KPI_FILE_COUNT=$(find "$REPO_ROOT/holding" "$REPO_ROOT/sutra" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
C_DELTA_KPI=$((KPI_FILE_COUNT - BASELINE_FILES))
if [ "$C_DELTA_KPI" -gt 0 ]; then
  C_SIGN_KPI="+"
else
  C_SIGN_KPI=""
fi

KPI_LOG_FILE="$REPO_ROOT/holding/ESTIMATION-LOG.jsonl"
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
# Source: holding/hooks/cascade-check.sh
# Note: This is the PostToolUse version repurposed as Stop check.
# Checks if L0-L2 files changed and reminds about downstream.

# Already covered by principle-regression check 4b (D7) above — skip duplicate.
_s9=$(_now_ms)
log_hook "CascadeCheck-D7" "PASS" "" "$_s9"

# ─── 10. Process Fix Check (D2) ──────────────────────────────────────────────
# Source: holding/hooks/process-fix-check.sh
_s10=$(_now_ms)

LAST_MSG_PF=$(cd "$REPO_ROOT" && git log -1 --oneline 2>/dev/null)

if echo "$LAST_MSG_PF" | grep -iqE '\b(fix|bug|patch|hotfix)\b'; then
  echo ""
  echo "Warning: Per D2: Bug fix detected in recent commit: $LAST_MSG_PF"
  echo "Did you also fix the PROCESS that allowed this bug?"
  echo "Root cause -> process improvement required."
fi
log_hook "ProcessFixCheck-D2" "PASS" "" "$_s10"

# ─── 11. Context Budget Check ────────────────────────────────────────────────
# Source: holding/hooks/context-budget-check.sh
_s11=$(_now_ms)

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

# ─── 12. Triage Collector (CLAUDE.md:32) ─────────────────────────────────────
# Source: holding/hooks/triage-collector.sh
# Persists TRIAGE: depth_selected=X, depth_correct=X, class=... lines from the
# current transcript into holding/TRIAGE-LOG.jsonl. Advisory — always exits 0.
_s12=$(_now_ms)
_tc_status="PASS"
_tc_error=""
if [ -x "$REPO_ROOT/holding/hooks/triage-collector.sh" ]; then
  # Pass REPO_ROOT explicitly as CLAUDE_PROJECT_DIR so the collector doesn't
  # re-derive it via git rev-parse (which in a pipeline subshell inside a
  # superproject with submodules can resolve to the wrong submodule root).
  if [ -n "$_STOP_STDIN" ]; then
    printf '%s' "$_STOP_STDIN" | CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/triage-collector.sh" >/dev/null 2>&1 || {
      _tc_status="FAIL"; _tc_error="triage-collector.sh exited non-zero"
    }
  else
    CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/triage-collector.sh" </dev/null >/dev/null 2>&1 || {
      _tc_status="FAIL"; _tc_error="triage-collector.sh exited non-zero"
    }
  fi
else
  _tc_status="FAIL"; _tc_error="triage-collector.sh missing or not executable"
fi
log_hook "TriageCollector" "$_tc_status" "$_tc_error" "$_s12"

# ─── 13. Estimation Collector (ESTIMATION-ENGINE.md MEASURE phase) ───────────
# Source: holding/hooks/estimation-collector.sh
# Persists ESTIMATE: tokens_est=N, files_est=M, time_min_est=T, category=...
# lines from the current transcript into holding/ESTIMATION-LOG.jsonl.
# Wires the auto-capture behavior specified in ESTIMATION-ENGINE.md lines
# 443-486 (MEASURE phase). Seed data was frozen 2026-04-05; this hook
# resumes live capture as of 2026-04-17. Advisory — always exits 0.
_s13=$(_now_ms)
_ec_status="PASS"
_ec_error=""
if [ -x "$REPO_ROOT/holding/hooks/estimation-collector.sh" ]; then
  if [ -n "$_STOP_STDIN" ]; then
    printf '%s' "$_STOP_STDIN" | CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/estimation-collector.sh" >/dev/null 2>&1 || {
      _ec_status="FAIL"; _ec_error="estimation-collector.sh exited non-zero"
    }
  else
    CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/estimation-collector.sh" </dev/null >/dev/null 2>&1 || {
      _ec_status="FAIL"; _ec_error="estimation-collector.sh exited non-zero"
    }
  fi
else
  _ec_status="FAIL"; _ec_error="estimation-collector.sh missing or not executable"
fi
log_hook "EstimationCollector" "$_ec_status" "$_ec_error" "$_s13"

# ─── 14. Latency Collector (SPEED charter W1) ────────────────────────────────
# Source: holding/hooks/latency-collector.sh
# Parses session transcript into per-task latency rows → holding/LATENCY-LOG.jsonl
# Spec: sutra/os/charters/SPEED.md + SPEED-phase-taxonomy.md
# Advisory — always exits 0. No behavior change; pure observation.
_s14=$(_now_ms)
_lc_status="PASS"
_lc_error=""
if [ -x "$REPO_ROOT/holding/hooks/latency-collector.sh" ]; then
  if [ -n "$_STOP_STDIN" ]; then
    printf '%s' "$_STOP_STDIN" | CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/latency-collector.sh" >/dev/null 2>&1 || {
      _lc_status="FAIL"; _lc_error="latency-collector.sh exited non-zero"
    }
  else
    CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/latency-collector.sh" </dev/null >/dev/null 2>&1 || {
      _lc_status="FAIL"; _lc_error="latency-collector.sh exited non-zero"
    }
  fi
else
  _lc_status="FAIL"; _lc_error="latency-collector.sh missing or not executable"
fi
log_hook "LatencyCollector" "$_lc_status" "$_lc_error" "$_s14"

# ─── 15. D19 Daily Satisfaction — "Your Day" Dashboard ───────────────────────
# Source: holding/hooks/session-end-satisfaction.sh
# Renders session dashboard: commits, files touched, direction count, top-3
# TODO queue, recent commits. Replaces inline reminder at section 1 (which
# was mislabeled D18). Advisory — always exits 0.
_s15=$(_now_ms)
_ds_status="PASS"
_ds_error=""
if [ -x "$REPO_ROOT/holding/hooks/session-end-satisfaction.sh" ]; then
  CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/session-end-satisfaction.sh" </dev/null 2>&1 || {
    _ds_status="FAIL"; _ds_error="session-end-satisfaction.sh exited non-zero"
  }
else
  _ds_status="FAIL"; _ds_error="session-end-satisfaction.sh missing or not executable"
fi
log_hook "DailySatisfaction-D19" "$_ds_status" "$_ds_error" "$_s15"

# ─── 16. Output Behavior Lint (memory feedback rules) ────────────────────────
# Source: holding/hooks/output-behavior-lint.sh
# Scans last N assistant turns for:
#   - never-ask-to-run violations (feedback_never_ask_to_run)
#   - no-HTML-unless-asked violations (feedback_no_html_unless_asked)
# Findings append to .enforcement/routing-misses.log. Advisory — exit 0.
_s16=$(_now_ms)
_ol_status="PASS"
_ol_error=""
if [ -x "$REPO_ROOT/holding/hooks/output-behavior-lint.sh" ]; then
  if [ -n "$_STOP_STDIN" ]; then
    printf '%s' "$_STOP_STDIN" | CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/output-behavior-lint.sh" >/dev/null 2>&1 || {
      _ol_status="FAIL"; _ol_error="output-behavior-lint.sh exited non-zero"
    }
  else
    CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$REPO_ROOT/holding/hooks/output-behavior-lint.sh" </dev/null >/dev/null 2>&1 || {
      _ol_status="FAIL"; _ol_error="output-behavior-lint.sh exited non-zero"
    }
  fi
else
  _ol_status="FAIL"; _ol_error="output-behavior-lint.sh missing or not executable"
fi
log_hook "OutputBehaviorLint" "$_ol_status" "$_ol_error" "$_s16"

# ─── Section 17: BUILD-LAYER REVIEW (PROTO-021) ─────────────────────────────
# Surfaces per-session L0/L1/L2 counts + stale-L1 items past promote-by date.
# Ledger: .enforcement/build-layer-ledger.jsonl
_s17=$(date +%s%N 2>/dev/null || date +%s)
_bl_status="PASS"
_bl_error=""
_bl_ledger="$REPO_ROOT/.enforcement/build-layer-ledger.jsonl"
if [ -f "$_bl_ledger" ]; then
  # Count today's events by type
  _today_start=$(date -v -24H +%s 2>/dev/null || date -d "-24 hours" +%s 2>/dev/null || echo 0)
  if command -v jq >/dev/null 2>&1 && [ "$_today_start" -gt 0 ]; then
    _n_block=$(jq -r "select(.ts >= $_today_start) | select(.event == \"block\") | .file" "$_bl_ledger" 2>/dev/null | wc -l | tr -d ' ')
    _n_advisory=$(jq -r "select(.ts >= $_today_start) | select(.event == \"advisory\") | .file" "$_bl_ledger" 2>/dev/null | wc -l | tr -d ' ')
    _n_override=$(jq -r "select(.ts >= $_today_start) | select(.event == \"override\") | .file" "$_bl_ledger" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$_n_block" != "0" ] || [ "$_n_advisory" != "0" ] || [ "$_n_override" != "0" ]; then
      echo ""
      echo "═══ BUILD-LAYER REVIEW (PROTO-021, last 24h) ═══"
      echo "  Block events:    $_n_block (HARD path, declaration missing)"
      echo "  Advisory events: $_n_advisory (SOFT path, declaration missing)"
      echo "  Overrides:       $_n_override"
      # Sample most recent 3 blocks for context
      if [ "$_n_block" != "0" ]; then
        echo ""
        echo "  Recent blocks:"
        jq -r "select(.ts >= $_today_start) | select(.event == \"block\") | \"    \\(.file)\"" "$_bl_ledger" 2>/dev/null | tail -3
      fi
      echo "═══════════════════════════════════════════════"
    fi
  fi
fi
log_hook "BuildLayerReview" "$_bl_status" "$_bl_error" "$_s17"

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

## Operationalization
#
### 1. Measurement mechanism
# Each section logs to holding/hooks/hook-log.jsonl via HOOK_EVENT row.
# Per-section failures captured in dispatcher-stop-dashboard status hook (_ds_status).
# Missing Stop-event fires → hook-log gap >1 session = diagnostic signal.
#
### 2. Adoption mechanism
# Registered in .claude/settings.json Stop hook (highest-priority aggregator).
# Sections 1-17 are internal — no per-section registration needed.
#
### 3. Monitoring / escalation
# DRI reviews hook-log nightly for Stop-fire continuity. Missing → investigate
# which section failed by scanning _ds_status rows. Kill-switch: remove from
# .claude/settings.json (heavy — breaks governance stack).
#
### 4. Iteration trigger
# New Stop-event responsibility → add as new numbered section; re-number downstream.
# Section failures >3% of sessions → section-specific debugging.
#
### 5. DRI
# Sutra-OS (Stop-event coordination owner).
#
### 6. Decommission criteria
# Retire when: Claude Code provides native multi-hook Stop sequencing; or
# Stop-event governance model supersedes this aggregator.

## Operationalization
#
### 1. Measurement mechanism
# Per-section log_hook rows in holding/hooks/hook-log.jsonl (PASS/FAIL, ms).
# Aggregate health printed at Health Summary section (ran/passed/failed counts).
#
### 2. Adoption mechanism
# Registered in .claude/settings.json under Stop event. Single entry point
# for all Stop-time hooks.
#
### 3. Monitoring / escalation
# If _HOOK_FAILED > 0 on Stop, failures echoed to stderr at tail. Per-section
# timing watched via hook-log.jsonl ms field.
#
### 4. Iteration trigger
# Revise when a new Stop-event sensor is added, a section regresses >500ms,
# or the Sutra plugin ships an equivalent Stop dispatcher.
#
### 5. DRI
# CEO of Asawa (OS hook infrastructure owner).
#
### 6. Decommission criteria
# Retire when the Sutra marketplace plugin ships a Stop dispatcher with
# equivalent sections + registry-backed enablement and Asawa migrates off.
