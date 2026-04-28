#!/usr/bin/env bash
# Sutra OS — Research Cadence Check (D5)
# Scans holding/research/ for staleness against D5 cadence:
#   AI / tech / market:           weekly  (>7d stale → flag)
#   Frameworks / governance:      bi-weekly (>14d stale → flag)
#
# Classification by filename keyword:
#   ai/tech:     {token, context, claude, mcp, anthropic, llm, openai, codex, model}
#   framework:   {framework, doctrine, governance, protocol, charter, standard}
#
# Writes status snapshot to holding/research/CADENCE-STATUS.md (founder
# reads at session start or on-demand). Advisory only, exits 0.
#
# Invocation:
#   Manual:       bash holding/hooks/research-cadence-check.sh
#   LaunchAgent:  holding/hooks/launchd/os.sutra.research-cadence.plist
#                 (daily 06:00 local time)
# ───────────────────────────────────────────────────────────────────────────────

set -o pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
RESEARCH_DIR="$REPO_ROOT/holding/research"
STATUS_FILE="$RESEARCH_DIR/CADENCE-STATUS.md"

if [ ! -d "$RESEARCH_DIR" ]; then
  exit 0
fi

AI_KEYWORDS='token|context|claude|mcp|anthropic|llm|openai|codex|model|sdk|embedding|agent'
FW_KEYWORDS='framework|doctrine|governance|protocol|charter|standard|cynefin|operationaliz|policy'

NOW=$(date +%s)

# stat flavor — macOS vs GNU
if [[ "$(uname)" == "Darwin" ]]; then
  STAT_MTIME() { stat -f %m "$1" 2>/dev/null; }
else
  STAT_MTIME() { stat -c %Y "$1" 2>/dev/null; }
fi

latest_mtime_for() {
  local pattern="$1"
  local latest=0 latest_file=""
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    local mt; mt=$(STAT_MTIME "$f")
    [ -z "$mt" ] && continue
    if [ "$mt" -gt "$latest" ]; then
      latest="$mt"; latest_file="$f"
    fi
  done < <(find "$RESEARCH_DIR" -maxdepth 2 -type f -name '*.md' 2>/dev/null | \
           awk -F/ -v pat="$pattern" 'BEGIN{IGNORECASE=1} tolower($NF) ~ pat {print}')
  echo "$latest $latest_file"
}

AI_ROW=$(latest_mtime_for "$AI_KEYWORDS")
FW_ROW=$(latest_mtime_for "$FW_KEYWORDS")

AI_MTIME=$(printf '%s' "$AI_ROW" | awk '{print $1}')
AI_FILE=$(printf '%s' "$AI_ROW" | cut -d' ' -f2-)
FW_MTIME=$(printf '%s' "$FW_ROW" | awk '{print $1}')
FW_FILE=$(printf '%s' "$FW_ROW" | cut -d' ' -f2-)

AI_AGE_DAYS=$(( ( NOW - ${AI_MTIME:-0} ) / 86400 ))
FW_AGE_DAYS=$(( ( NOW - ${FW_MTIME:-0} ) / 86400 ))

ai_status="FRESH"
[ "$AI_AGE_DAYS" -gt 7 ] && ai_status="STALE"
[ "${AI_MTIME:-0}" = "0" ] && ai_status="MISSING"

fw_status="FRESH"
[ "$FW_AGE_DAYS" -gt 14 ] && fw_status="STALE"
[ "${FW_MTIME:-0}" = "0" ] && fw_status="MISSING"

mkdir -p "$RESEARCH_DIR"
cat > "$STATUS_FILE" << STATUS
# Research Cadence Status (D5)

*Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) · Source: \`holding/hooks/research-cadence-check.sh\`*

| Track | Latest | Age (days) | Cadence | Status |
|---|---|---|---|---|
| AI / tech / market  | \`$(basename "${AI_FILE:-—}")\` | ${AI_AGE_DAYS} | weekly (≤7d) | **$ai_status** |
| Frameworks / governance | \`$(basename "${FW_FILE:-—}")\` | ${FW_AGE_DAYS} | bi-weekly (≤14d) | **$fw_status** |

**D5 principle**: External research at every level. AI/tech weekly, traditional frameworks bi-weekly.

Run again: \`bash holding/hooks/research-cadence-check.sh\`
LaunchAgent: \`launchctl load ~/Library/LaunchAgents/os.sutra.research-cadence.plist\`
STATUS

# Signal to stderr only if anything is stale (non-zero exit would block the
# LaunchAgent in some configs; keep advisory).
if [ "$ai_status" = "STALE" ] || [ "$fw_status" = "STALE" ]; then
  echo "research-cadence: STALE — AI:${ai_status}(${AI_AGE_DAYS}d), FW:${fw_status}(${FW_AGE_DAYS}d). See holding/research/CADENCE-STATUS.md." >&2
fi

exit 0

## Operationalization
#
### 1. Measurement mechanism
# Age in days since newest file matching AI/tech or framework/governance
# keyword patterns in holding/research/. Target: AI ≤7d, FW ≤14d.
#
### 2. Adoption mechanism
# Two entry points: (a) manual bash invocation; (b) LaunchAgent
# os.sutra.research-cadence daily 06:00. Status file CADENCE-STATUS.md is
# the single surface founder reads.
#
### 3. Monitoring / escalation
# CADENCE-STATUS.md regenerated on every run. STALE status → stderr warn;
# repeat for 2 consecutive days → LaunchAgent should escalate (future).
#
### 4. Iteration trigger
# Revise keywords when new research topics emerge that don't match either
# bucket (e.g., "security" research slot). Revise windows when founder
# changes cadence per D5.
#
### 5. DRI
# CEO of Asawa (D5 owner).
#
### 6. Decommission criteria
# Retire when: research-cadence sensing moves into DIRECTIONS-ENGINE
# enforcement phase (parked 2026-04-22).
