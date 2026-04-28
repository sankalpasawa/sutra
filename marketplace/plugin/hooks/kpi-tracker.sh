#!/usr/bin/env bash
# kpi-tracker.sh — Sutra KPI delta sensor (Stop hook, AUDIT mode)
# Measures C (Cognitive Load) and A (Accuracy) per session against v1.3.1 baselines.
# Exit 0 always — audit only, never blocks.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ── Baselines (from SUTRA-KPI.md v1.3.1) ──
BASELINE_FILES=136
BASELINE_ACCURACY=78  # mean accuracy %

# ── C: Cognitive Load (file count proxy) ──
FILE_COUNT=$(find "$REPO_ROOT/holding" "$REPO_ROOT/sutra" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
C_DELTA=$((FILE_COUNT - BASELINE_FILES))
if [ "$C_DELTA" -gt 0 ]; then
  C_SIGN="+"
elif [ "$C_DELTA" -eq 0 ]; then
  C_SIGN=""
else
  C_SIGN=""  # negative sign is already in the number
fi

# ── A: Accuracy (mean of last 5 ESTIMATION-LOG entries) ──
LOG_FILE="$REPO_ROOT/holding/ESTIMATION-LOG.jsonl"
A_DISPLAY="N/A"
A_DELTA_DISPLAY="no data"

if [ -f "$LOG_FILE" ]; then
  # Extract accuracy.tokens_pct from last 5 non-empty lines, compute mean as integer %
  ACCURACIES=$(tail -20 "$LOG_FILE" | grep -v '^$' | tail -5 | \
    sed -n 's/.*"tokens_pct":\([0-9.]*\).*/\1/p')

  if [ -n "$ACCURACIES" ]; then
    # Compute mean accuracy as integer percentage using awk
    A_MEAN=$(echo "$ACCURACIES" | awk '{sum += $1; n++} END {if(n>0) printf "%d", (sum/n)*100; else print "0"}')
    A_DELTA=$((A_MEAN - BASELINE_ACCURACY))
    if [ "$A_DELTA" -gt 0 ]; then
      A_DELTA_DISPLAY="+${A_DELTA}%"
    else
      A_DELTA_DISPLAY="${A_DELTA}%"
    fi
    A_DISPLAY="${A_MEAN}%"
  fi
fi

# ── Regression flags ──
REGRESSION=""
# C regression: >5% increase over baseline
C_THRESHOLD=$(( BASELINE_FILES * 5 / 100 ))
if [ "$C_DELTA" -gt "$C_THRESHOLD" ]; then
  REGRESSION="${REGRESSION}\n  !! C REGRESSION: file count grew >${C_THRESHOLD} beyond baseline"
fi
# A regression: >5% decrease below baseline
if [ "$A_DISPLAY" != "N/A" ]; then
  if [ "$A_MEAN" -lt $((BASELINE_ACCURACY * 95 / 100)) ]; then
    REGRESSION="${REGRESSION}\n  !! A REGRESSION: accuracy dropped below ${BASELINE_ACCURACY}% - 5% threshold"
  fi
fi

# ── Report ──
cat <<EOF

═══ SUTRA KPI DELTA ═══
C (Cognitive Load): ${FILE_COUNT} files (baseline: ${BASELINE_FILES}, delta: ${C_SIGN}${C_DELTA})
A (Accuracy):       ${A_DISPLAY} (baseline: ${BASELINE_ACCURACY}%, delta: ${A_DELTA_DISPLAY})
═══════════════════════
EOF

if [ -n "$REGRESSION" ]; then
  echo -e "$REGRESSION"
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
