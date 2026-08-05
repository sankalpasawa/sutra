#!/usr/bin/env bash
# dispatch-report.sh — WDP W5-T46 per FROZEN LLD-LEDGER-REPORT + TELEMETRY-DESIGN.
# Emits REVIEW CANDIDATES, never verdicts. Golden-determinism (G5-consult fold):
# LC_ALL=C, jq -S, sorted inputs, secondary sort keys, timestamps normalized out.
# Orphan mutations are the ONE invariant — printed as RED marker lines.
set -euo pipefail
export LC_ALL=C TZ=UTC   # codex determinism fold: TZ pinned with locale
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
DL="${DISPATCH_LEDGER_OVERRIDE:-$ROOT/.sutra/dispatch-ledger.jsonl}"
AL="${ATOM_LEDGER_OVERRIDE:-$ROOT/.sutra/atom-ledger.jsonl}"
AR="${ATOM_ARCHIVE_OVERRIDE:-$ROOT/.sutra/atom-ledger-test-archive.jsonl}"
FJ="${FLOW_JOURNAL_OVERRIDE:-$ROOT/.enforcement/flow-journal}"
AG="${ATOM_GATE_OVERRIDE:-$ROOT/.enforcement/atom-gate.jsonl}"
NOW="${REPORT_NOW_OVERRIDE:-$(date +%s)}"   # override pins 'now' for golden runs
command -v jq >/dev/null || { echo "dispatch-report: jq required" >&2; exit 1; }

atoms_all() {  # atom ledger + archive sidecar, sorted (id, ts) for determinism
  cat "$AL" 2>/dev/null || true
  cat "$AR" 2>/dev/null || true
}

section() { printf '\n== %s ==\n' "$1"; }

echo "review candidates — human judges, policy version bumps, never auto-retunes"
echo "inputs: dispatch-ledger atom-ledger(+archive) floor-journal atom-gate"

# 1. under-modeled? cheap-tier atom with attempts > 1
section "under-modeled? (cheap tier, attempts > 1 — may equally be bad spec / flaky verify / missing context)"
atoms_all | jq -rS 'select((.model=="claude-haiku-4-5" or .model=="claude-sonnet-5") and ((.attempt // 0) > 1))
  | [.id, .model, (.attempt|tostring), .status] | @tsv' 2>/dev/null | sort | tee /tmp/.dr.$$ | head -5
printf 'count: %s\n' "$(wc -l < /tmp/.dr.$$ | tr -d ' ')"

# 2. over-modeled? top-two-tier atom closing attempt 1 (class join lands when
# outcome rows populate; v1 flags on tier alone — candidates, not verdicts)
section "over-modeled? (top-two tier closed attempt 1 — down-tier trial candidate)"
atoms_all | jq -rS '
  select((.model=="claude-fable-5" or .model=="claude-opus-5") and .status=="closed" and ((.attempt // 0) <= 1))
  | [.id, .model, .status] | @tsv' 2>/dev/null | sort | tee /tmp/.dr.$$ | head -5
printf 'count: %s\n' "$(wc -l < /tmp/.dr.$$ | tr -d ' ')"

# 3. over-broad touches: breadth > 20 on dir declarations (decision rows)
section "over-broad touches (touches_breadth > 20 sustained — v2 named-pattern trigger)"
jq -rS 'select(.kind=="decision" and ((.touches_breadth // 0) > 20)) | [.unit, (.touches_breadth|tostring)] | @tsv' \
  "$DL" 2>/dev/null | sort | tee /tmp/.dr.$$ | head -5
printf 'count: %s\n' "$(wc -l < /tmp/.dr.$$ | tr -d ' ')"

# 4. escalation hotspot: same unit escalating repeatedly
section "escalation hotspot (same unit escalating — ladder misclassifies this shape)"
jq -rS 'select(.kind=="escalation") | .from + " -> " + .to + " (" + .trigger + ")"' "$DL" 2>/dev/null \
  | sort | uniq -c | sort -rn -k1,1 | tee /tmp/.dr.$$ | head -5
printf 'count: %s\n' "$(wc -l < /tmp/.dr.$$ | tr -d ' ')"

# 5. touches_miss: floor SOFT rows (W1-T17)
section "touches_miss (floor SOFT rows — calibration data for the W6 HARD flip)"
# G6-synthesis P1: this read .kind; the ONLY writer (atom-floor.sh) emits
# "event":"touches_miss". 152 real rows were invisible and the section
# reported 0 — the SECOND instance of this exact schema-drift class, after
# the orphan invariant. Accept either key so a future writer change is loud
# rather than silent.
jq -rS 'select(.event=="touches_miss" or .kind=="touches_miss") | [.atom_id // "-", .path // "-"] | @tsv' "$AG" 2>/dev/null \
  | sort | uniq -c | sort -rn -k1,1 | tee /tmp/.dr.$$ | head -5
printf 'count: %s\n' "$(wc -l < /tmp/.dr.$$ | tr -d ' ')"

# 6. ORPHAN MUTATION — the one invariant; always RED
section "orphan mutations (INVARIANT — journal mutation with no attributable open atom)"
ORPHANS=0
if [ -d "$FJ" ]; then
  # G6 codex: the old predicate matched a schema the writer never emits (no
  # `mutation` field; unattributed rows carry the literal "none"), so the ONE
  # invariant could never fire. Matching the real schema alone over-reports in
  # the other direction: the floor journals an attempt BEFORE deciding, so an
  # atom-less row is usually an attempt it then BLOCKED. A real orphan is a
  # mutation that was journaled with no atom AND never blocked — the join.
  _ORPH=$(mktemp); _WB=$(mktemp)
  cat "$FJ"/*.jsonl 2>/dev/null | jq -c 'select((.atom_id // "none") == "none") | {ts, tool, path}' 2>/dev/null | sort -u > "$_ORPH"
  jq -c 'select(.event == "would_block") | {ts, tool, path}' "$AG" 2>/dev/null | sort -u > "$_WB"
  ORPHANS=$(comm -23 "$_ORPH" "$_WB" | wc -l | tr -d ' ')
  printf 'attempts journaled without an atom: %s (blocked by the floor: %s)\n' \
    "$(wc -l < "$_ORPH" | tr -d ' ')" "$(wc -l < "$_WB" | tr -d ' ')"
  rm -f "$_ORPH" "$_WB"
fi
if [ "${ORPHANS:-0}" -gt 0 ]; then
  echo "RED: $ORPHANS orphan mutation row(s) — INVARIANT VIOLATION, investigate immediately"
else
  echo "none (invariant holds)"
fi

# 7. stale atoms: open > 24h
section "stale atoms (open > 24h — hygiene candidate)"
atoms_all | jq -rS --argjson now "$NOW" \
  'select(.status=="open" and (($now - (.ts // $now)) > 86400)) | [.id, .goal] | @tsv' 2>/dev/null \
  | sort | tee /tmp/.dr.$$ | head -5
printf 'count: %s\n' "$(wc -l < /tmp/.dr.$$ | tr -d ' ')"
rm -f /tmp/.dr.$$
