#!/usr/bin/env bash
# findings-banner.sh (plugin, fleet-generic) — SessionStart one-liner over the
# governance findings ledger. Ported 2026-08-26 (atom a-db25e6c4-08). Silent
# when no ledger exists (zero noise for repos that never ran the audit).
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
GOVDIR="${SUTRA_GOV_DIR:-$ROOT/.sutra/governance}"
LEDGER="$GOVDIR/findings.jsonl"
HISTORY="$GOVDIR/triage-history.jsonl"
command -v jq >/dev/null 2>&1 || exit 0
[ -f "$LEDGER" ] || exit 0
OPEN=$(jq -s '[group_by(.id) | map(last) | .[] | select(.status=="open")] | length' "$LEDGER" 2>/dev/null || echo "?")
CRIT=$(jq -s '[group_by(.id) | map(last) | .[] | select(.status=="open" and .severity=="critical")] | length' "$LEDGER" 2>/dev/null || echo "?")
LAST_TRIAGE=$(tail -1 "$HISTORY" 2>/dev/null | jq -r '.date+" ("+.decision+")"' 2>/dev/null || echo "never")
echo "[Governance findings] open=$OPEN (critical=$CRIT) · last triage: $LAST_TRIAGE · ledger: ${LEDGER#$ROOT/}"
exit 0
