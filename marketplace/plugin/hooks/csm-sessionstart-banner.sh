#!/bin/bash
# csm-sessionstart-banner.sh — SessionStart hook (CSM TODO #2, D43).
#
# WHAT: Emits a 5-line summary of the Capability Surface Map at session start.
# Bucket counts, pending fleet-parity count, latest audit timestamp, recurring-
# instrument pointer, and how to run the audit on demand.
#
# WHY: Per D43 + codex P2 surfacing path. Without a hook-emitted banner, the
# CSM's drift-detection findings are invisible until the founder manually runs
# the audit — defeating the "visibility before influence" stance (D42).
#
# WHERE: Asawa-mode emits (file holding/CAPABILITY-MAP.md present); T4-mode
# silent skip (file absent per D33 firewall — CSM is Asawa-internal). Future:
# T4 summary via /sutra-capability skill (CSM TODO #3, deadline 2026-06-01).
#
# Kill-switches:
#   CSM_BANNER_DISABLED=1
#   ~/.csm-banner-disabled  (file presence)
#
# Build-layer: L0 fleet (sutra/marketplace/plugin/hooks/).

set -u   # not -e: soft-fail (never block session start)

[ "${CSM_BANNER_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.csm-banner-disabled" ] && exit 0

PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
MAP="$PROJ/holding/CAPABILITY-MAP.md"
AUDIT_JSONL="$PROJ/holding/state/capability-map-audit.jsonl"

# Asawa-mode gate: only emit if CAPABILITY-MAP.md exists in this project tree
[ -f "$MAP" ] || exit 0

# Bucket counts (parse status column from cap-### table rows)
SHIPPING=$(grep -cE '^\| cap-[0-9]+ \|.* \| shipping ' "$MAP" 2>/dev/null || echo 0)
PROPOSED=$(grep -cE '^\| cap-[0-9]+ \|.* \| proposed ' "$MAP" 2>/dev/null || echo 0)
ASAWA_ONLY=$(grep -cE '^\| cap-2[0-9]+ ' "$MAP" 2>/dev/null || echo 0)
INTERNAL=$(grep -cE '^\| cap-3[0-9]+ ' "$MAP" 2>/dev/null || echo 0)
PENDING_PARITY=$(grep -cE '^\| cap-1[0-9]+ \|.* \| proposed ' "$MAP" 2>/dev/null || echo 0)

# Latest audit timestamp from jsonl
LATEST_AUDIT="(no audit run yet)"
TOTAL_ROWS=0
if [ -f "$AUDIT_JSONL" ]; then
  TOTAL_ROWS=$(wc -l < "$AUDIT_JSONL" 2>/dev/null | tr -d ' ' || echo 0)
  if command -v jq >/dev/null 2>&1; then
    LATEST=$(jq -r 'select(.action=="AUDIT_RUN") | .ts' "$AUDIT_JSONL" 2>/dev/null | tail -1)
    [ -n "$LATEST" ] && LATEST_AUDIT="$LATEST"
  fi
fi

# Emit 5-line banner (stdout, ASCII-safe, middle-dot separator allowed per H-Sutra header convention)
printf '[CSM·D43] Buckets: %s shipping · %s proposed · %s asawa-only · %s sutra-internal\n' "$SHIPPING" "$PROPOSED" "$ASAWA_ONLY" "$INTERNAL"
printf '[CSM·D43] Pending fleet-parity (cap-1xx proposed): %s; deadlines 2026-05-08 → 2026-06-01\n' "$PENDING_PARITY"
printf '[CSM·D43] Latest audit: %s (audit jsonl: %s rows)\n' "$LATEST_AUDIT" "$TOTAL_ROWS"
printf '[CSM·D43] Recurring instrument: holding/scripts/capability-audit.sh (L1, promote-to plugin/scripts/ by 2026-06-01)\n'
printf '[CSM·D43] Run audit on demand: bash holding/scripts/capability-audit.sh\n'

exit 0
