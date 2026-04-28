#!/usr/bin/env bash
# Log rotation — Tokens charter C2
# Rotates a JSONL log file when it exceeds MAX_LINES. Archive keeps oldest
# lines in .archive/<basename>-<YYYY-MM-DD>.jsonl. Idempotent.
#
# Usage:
#   bash holding/hooks/rotate-logs.sh <log-file> [max-lines]
#   # Default max-lines = 10000
#
# Exit 0 on success (rotation or no-op). Exit 1 on error.

set -euo pipefail

LOG_FILE="${1:?Usage: rotate-logs.sh <log-file> [max-lines]}"
MAX_LINES="${2:-10000}"

if [ ! -f "$LOG_FILE" ]; then
  echo "rotate-logs: $LOG_FILE does not exist (skipping)" >&2
  exit 0
fi

CURRENT=$(wc -l < "$LOG_FILE" | tr -d ' ')

if [ "$CURRENT" -le "$MAX_LINES" ]; then
  # No-op — under threshold
  exit 0
fi

LOG_DIR=$(dirname "$LOG_FILE")
LOG_BASE=$(basename "$LOG_FILE")
STEM="${LOG_BASE%.*}"
EXT="${LOG_BASE##*.}"
ARCHIVE_DIR="$LOG_DIR/.archive"
DATE=$(date +%Y-%m-%d)
ARCHIVE_FILE="$ARCHIVE_DIR/${STEM}-${DATE}.${EXT}"

mkdir -p "$ARCHIVE_DIR"

# Split: archive gets oldest, main keeps newest MAX_LINES
ARCHIVE_COUNT=$((CURRENT - MAX_LINES))
head -n "$ARCHIVE_COUNT" "$LOG_FILE" >> "$ARCHIVE_FILE"
# Atomic replace main file with tail
TAIL_TMP=$(mktemp)
tail -n "$MAX_LINES" "$LOG_FILE" > "$TAIL_TMP"
mv "$TAIL_TMP" "$LOG_FILE"

echo "rotate-logs: $LOG_BASE rotated ($CURRENT → $MAX_LINES lines; $ARCHIVE_COUNT archived to $(basename "$ARCHIVE_FILE"))"

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
