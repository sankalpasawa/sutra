#!/usr/bin/env bash
# governance-triage-headless.sh (plugin, fleet-generic) — the LLM half of the
# findings loop: fix-one-per-run. Ported 2026-08-26 (atom a-db25e6c4-08) from
# asawa-holding staging (original codex-consulted; billing = subscription only).
# Cost guard: zero open findings -> the LLM never starts. TRIAGE_DRY_RUN=1
# prints the decision and never spends.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 1
unset ANTHROPIC_API_KEY   # subscription auth, never API billing
GOVDIR="${SUTRA_GOV_DIR:-$ROOT/.sutra/governance}"
LEDGER="$GOVDIR/findings.jsonl"
HISTORY="$GOVDIR/triage-history.jsonl"
RUNLOG_DIR="$GOVDIR/triage-runs"
TODAY=$(date -u +%F)
command -v jq >/dev/null 2>&1 || { echo "triage: jq required"; exit 0; }
[ -f "$LEDGER" ] || { echo "triage: no ledger — nothing to do"; exit 0; }
OPEN=$(jq -s '[group_by(.id) | map(last) | .[] | select(.status=="open")] | length' "$LEDGER" 2>/dev/null || echo 0)
if [ "${OPEN:-0}" -eq 0 ]; then
  printf '{"date":"%s","decision":"skip-zero-open","ts":%s}\n' "$TODAY" "$(date +%s)" >> "$HISTORY"
  echo "triage: 0 open findings — skipping (free)"
  exit 0
fi
if [ "${TRIAGE_DRY_RUN:-0}" = "1" ]; then
  echo "triage DRY RUN: would fix one of $OPEN open finding(s)"
  exit 0
fi
command -v claude >/dev/null 2>&1 || { echo "triage: claude CLI not found"; exit 0; }
mkdir -p "$RUNLOG_DIR"
PROMPT="Read the governance findings ledger at ${LEDGER#$ROOT/} (append-only; the LAST row per id is current). Pick exactly ONE finding with status=open (prefer critical), fix its root cause in this repo, then append a status update row {id, status: fixed|accepted, note, date} to the ledger. Fix ONE only."
claude -p "$PROMPT" > "$RUNLOG_DIR/$TODAY.log" 2>&1
X=$?
printf '{"date":"%s","decision":"fix-one","exit":%s,"ts":%s}\n' "$TODAY" "$X" >> "$HISTORY"
echo "triage: fix-one run complete (exit=$X, log=$RUNLOG_DIR/$TODAY.log)"
exit 0
