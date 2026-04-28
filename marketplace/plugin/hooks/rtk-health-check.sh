#!/usr/bin/env bash
# RTK Health Check — Tokens charter
# Snapshots `rtk gain` (cumulative savings + per-command breakdown) into a log.
# Run manually or via cron/scheduler; records a datestamped row for trend tracking.
#
# Usage:
#   bash holding/hooks/rtk-health-check.sh
#   bash holding/hooks/rtk-health-check.sh --json     # emit to jsonl instead of markdown
#
# Output:
#   holding/observability/rtk-gain-log.md     (human-readable, append-only)
#   holding/observability/rtk-gain-log.jsonl  (machine-readable, --json mode)

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
OBS_DIR="$REPO_ROOT/holding/observability"
MD_LOG="$OBS_DIR/rtk-gain-log.md"
JSONL_LOG="$OBS_DIR/rtk-gain-log.jsonl"
MODE="${1:-md}"

mkdir -p "$OBS_DIR"

# Check rtk installed
if ! command -v rtk >/dev/null 2>&1; then
  echo "rtk-health-check: rtk not installed — skipping"
  exit 0
fi

# Check kill-switch
if [ -f "$HOME/.rtk-disabled" ] || [ "${RTK_DISABLED:-0}" = "1" ]; then
  KILLED="yes"
else
  KILLED="no"
fi

TS=$(date +%Y-%m-%dT%H:%M:%S)
RTK_VER=$(rtk --version 2>/dev/null | awk '{print $2}')

# Capture machine-readable summary from rtk gain
GAIN_JSON=$(rtk gain --json 2>/dev/null || echo "{}")

if [ "$MODE" = "--json" ]; then
  echo "{\"ts\":\"$TS\",\"rtk_version\":\"$RTK_VER\",\"kill_switch_active\":\"$KILLED\",\"gain\":$GAIN_JSON}" >> "$JSONL_LOG"
  echo "rtk-health-check: appended JSONL row to $JSONL_LOG"
else
  {
    echo ""
    echo "## $TS — RTK v$RTK_VER — kill-switch: $KILLED"
    echo ""
    echo '```'
    rtk gain 2>/dev/null | head -40
    echo '```'
  } >> "$MD_LOG"
  echo "rtk-health-check: appended to $MD_LOG"
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
