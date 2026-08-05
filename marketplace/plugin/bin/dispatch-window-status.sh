#!/usr/bin/env bash
# dispatch-window-status.sh — WDP W6-T58. Reports whether the observation
# WINDOW is ready to close, on evidence rather than a stopwatch.
#
# Closing conditions (all four):
#   1. >= WINDOW_HOURS (default 24) elapsed since the recorded window start
#   2. zero orphan mutations (the one invariant)
#   3. every BLOCK row since the baseline is triaged (an evidence row of kind
#      observation-triage covers it)
#   4. zero unparseable journal rows outside the quarantine manifest
#
# Exit 0 = GO (safe to close T58), 1 = WAIT, 2 = infra error.
set -euo pipefail
export LC_ALL=C TZ=UTC
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
EV="$ROOT/.enforcement/wdp/evidence.jsonl"
GJ="$ROOT/.enforcement/dispatch-gate.jsonl"
FJ="$ROOT/.enforcement/flow-journal"
AG="$ROOT/.enforcement/atom-gate.jsonl"
QUAR="$ROOT/.enforcement/wdp/journal-quarantine.jsonl"
WINDOW_HOURS="${WINDOW_HOURS:-24}"
NOW="${WINDOW_NOW_OVERRIDE:-$(date +%s)}"
command -v jq >/dev/null || { echo "window-status: jq required" >&2; exit 2; }

# Readers must tolerate corrupt lines (append-only store; bad rows stay put).
parse_ok() { jq -R 'fromjson? // empty' "$1" 2>/dev/null; }

START=$(parse_ok "$EV" | jq -rs '[.[] | select(.kind=="observation-window" and .event=="start")] | last | .ts // empty')
[ -n "${START:-}" ] || { echo "window-status: no window start recorded" >&2; exit 2; }
ELAPSED=$(( NOW - START ))
HOURS=$(( ELAPSED / 3600 ))

BLOCKS=$(parse_ok "$GJ" | jq -rs '[.[] | select(.verdict=="BLOCK")] | length')
SKIPS=$(parse_ok "$GJ" | jq -rs  '[.[] | select(.verdict=="SKIP" or .verdict=="OPAQUE")] | length')
# G6-synthesis P1: this SUMMED cumulative snapshots (8 then 28 -> 36) and
# compared 36 >= 33 live blocks, manufacturing a pass — and since every new
# triage row inflated the sum, the condition could never fail again.
# Triage rows are SNAPSHOT state, not events: reduce to the latest, never add.
# Latest by ts (not file position) per codex — append order is not guaranteed.
TRIAGED=$(parse_ok "$EV" | jq -rs '[.[] | select(.kind=="observation-triage")] | if length == 0 then 0 else (max_by(.ts) | .blocks_since_baseline // 0) end')

# Orphans: journaled without an atom, minus attempts the floor blocked.
_O=$(mktemp); _W=$(mktemp)
cat "$FJ"/*.jsonl 2>/dev/null | jq -R 'fromjson? // empty' 2>/dev/null \
  | jq -c 'select((.atom_id // "none") == "none") | {ts, tool, path}' | sort -u > "$_O"
parse_ok "$AG" | jq -c 'select(.event == "would_block") | {ts, tool, path}' | sort -u > "$_W"
ORPHANS=$(comm -23 "$_O" "$_W" | wc -l | tr -d ' ')
rm -f "$_O" "$_W"

# Corrupt rows not covered by the quarantine manifest.
TOTAL_ROWS=$(wc -l < "$GJ" 2>/dev/null | tr -d ' ' || echo 0)
GOOD_ROWS=$(parse_ok "$GJ" | jq -rs 'length')
CORRUPT=$(( TOTAL_ROWS - GOOD_ROWS ))
QUARANTINED=$(parse_ok "$QUAR" 2>/dev/null | jq -rs 'length' 2>/dev/null || echo 0)
UNQUARANTINED=$(( CORRUPT - QUARANTINED ))
[ "$UNQUARANTINED" -lt 0 ] && UNQUARANTINED=0

printf '== WDP observation WINDOW status ==\n'
printf 'elapsed         : %sh of %sh required\n' "$HOURS" "$WINDOW_HOURS"
printf 'gate BLOCK rows : %s (triaged: %s)\n' "$BLOCKS" "$TRIAGED"
printf 'SKIP/OPAQUE     : %s (scanner-gap classes, journaled by design)\n' "$SKIPS"
printf 'orphan mutations: %s (the one invariant)\n' "$ORPHANS"
printf 'corrupt rows    : %s (quarantined: %s, unaccounted: %s)\n' "$CORRUPT" "$QUARANTINED" "$UNQUARANTINED"

FAIL=0
[ "$HOURS" -ge "$WINDOW_HOURS" ] || { echo "WAIT: window needs $(( WINDOW_HOURS - HOURS ))h more"; FAIL=1; }
[ "$ORPHANS" -eq 0 ] || { echo "WAIT: $ORPHANS orphan mutation(s) — investigate before closing"; FAIL=1; }
[ "$TRIAGED" -ge "$BLOCKS" ] || { echo "WAIT: $(( BLOCKS - TRIAGED )) BLOCK row(s) untriaged"; FAIL=1; }
[ "$UNQUARANTINED" -eq 0 ] || { echo "WAIT: $UNQUARANTINED corrupt row(s) not in the quarantine manifest"; FAIL=1; }

[ "$FAIL" -eq 0 ] && { echo "GO: all closing conditions met — T58 may close"; exit 0; }
exit 1
