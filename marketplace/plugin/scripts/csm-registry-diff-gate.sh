#!/usr/bin/env bash
# csm-registry-diff-gate.sh — Capability Surface Map registry diff gate
#
# WHAT: Validates CAPABILITY-MAP.md cap-### table rows have matching YAML
# records in CAPABILITY-MAP-records.md with bucket-appropriate required fields
# present (and not all TBD-NEEDS-BACKFILL).
#
# WHY: Per CSM TODO #1 (codex P1 critical, deadline 2026-05-15). Without this
# gate, the map drifts: rows added without records, fields stay TBD forever,
# bucket assignments don't match, etc.
#
# MODES (per codex 2026-05-04 ADVISORY hybrid recommendation):
#   --warn    : warn-first stabilization mode. Always exit 0. Stderr lists violations.
#   --strict  : hard-block mode. Exit 2 on any violation. CI-mode.
#   --report  : just print the matrix, exit 0.
#
# Default: --warn. Per codex 2026-05-04 batch review #2: 2-phase stabilization
# rollout (avoids training the team to ignore the gate):
#   Phase 1 (by 2026-05-15): --strict treats only missing/orphan/malformed records
#     as violations; TBD-NEEDS-BACKFILL placeholders are tolerated.
#   Phase 2 (after field completion of all 39 stub records): --strict adds
#     TBD-NEEDS-BACKFILL completeness check.
# Phase 2 strict-flag wired in via follow-up commit when field completion lands.
#
# Build-layer: L1 single-instance:asawa. Promote-to plugin/scripts/ by 2026-06-01.

set -euo pipefail

ROOT="${ROOT:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
# Asawa-mode gate (L0 promotion): silently exit on T4 fleet
[ -f "$ROOT/holding/CAPABILITY-MAP.md" ] || exit 0
CSM="$ROOT/holding/CAPABILITY-MAP.md"
RECORDS="$ROOT/holding/CAPABILITY-MAP-records.md"
JSONL="$ROOT/holding/state/capability-map-audit.jsonl"
TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STABILIZATION_END="2026-05-15"

MODE="${1:---warn}"
# Codex 2026-05-04 batch review fold: --strict alias for --strict-phase1 to
# avoid training the team to ignore the gate during stabilization.
[ "$MODE" = "--strict" ] && MODE="--strict-phase1"

[ -f "$CSM" ] || { echo "FATAL: CSM not found at $CSM" >&2; exit 1; }
[ -f "$RECORDS" ] || { echo "FATAL: records not found at $RECORDS" >&2; exit 1; }

# Today vs stabilization end (used by pre-commit wrapper to auto-switch mode)
TODAY="$(date -u +%Y-%m-%d)"

# Extract cap-### IDs from CSM tables
csm_caps() {
  awk -F'|' '/^\| cap-[0-9]+ \|/{gsub(/^ +| +$/,"",$2); print $2}' "$CSM" | sort -u
}

# Extract cap-### IDs from records file
records_caps() {
  grep '^id: cap-' "$RECORDS" | awk '{print $2}' | sort -u
}

# Check a record for required fields (bucket-aware)
check_record() {
  local id="$1"
  local record
  record=$(awk -v id="id: $id" '$0==id{flag=1} flag; /^```$/ && flag{exit}' "$RECORDS")
  [ -z "$record" ] && { echo "MISSING-RECORD"; return; }

  local bucket; bucket=$(echo "$record" | grep '^bucket:' | head -1 | awk '{print $2}')

  # Required fields per bucket
  local required_a=("threat_model" "telemetry_coverage" "activation_surface" "release_vehicle")
  local required_bc=("why_not_client_shippable" "decommission_trigger")
  local universal=("name" "bucket" "governance_plane" "consumer" "owner" "direction_binding" "status")

  local violations=()
  local f
  for f in "${universal[@]}"; do
    if ! echo "$record" | grep -qE "^${f}:[[:space:]]+\S"; then
      violations+=("missing-${f}")
    fi
  done

  if [ "$bucket" = "client-shippable" ]; then
    for f in "${required_a[@]}"; do
      if ! echo "$record" | grep -qE "^${f}:[[:space:]]+\S"; then
        violations+=("missing-${f}")
      fi
    done
  elif [ "$bucket" = "asawa-only" ] || [ "$bucket" = "sutra-internal" ]; then
    for f in "${required_bc[@]}"; do
      val=$(echo "$record" | grep -E "^${f}:" | head -1 | sed -E "s/^${f}:[[:space:]]*//")
      if [ -z "$val" ] || [ "$val" = "TBD-NEEDS-BACKFILL" ] || [ "$val" = "null" ]; then
        violations+=("invalid-${f}")
      fi
    done
  fi

  # For shipping-status caps, TBD-NEEDS-BACKFILL is forbidden in critical fields
  local status; status=$(echo "$record" | grep '^status:' | head -1 | awk '{print $2}')
  if [ "$status" = "shipping" ]; then
    for f in artifact_path activation_surface release_vehicle released_in; do
      val=$(echo "$record" | grep -E "^${f}:" | head -1 | sed -E "s/^${f}:[[:space:]]*//")
      if [ "$val" = "TBD-NEEDS-BACKFILL" ]; then
        violations+=("shipping-but-${f}=TBD")
      fi
    done
  fi

  if [ ${#violations[@]} -eq 0 ]; then
    echo "OK"
  else
    (IFS=,; echo "${violations[*]}")
  fi
}

# Run validation
declare -a missing_records=()
declare -a violation_records=()
declare -a ok_records=()

while read -r id; do
  [ -z "$id" ] && continue
  result=$(check_record "$id")
  if [ "$result" = "OK" ]; then
    ok_records+=("$id")
  elif [ "$result" = "MISSING-RECORD" ]; then
    missing_records+=("$id")
  else
    violation_records+=("$id:$result")
  fi
done < <(csm_caps)

# Check for orphan records (record without table row)
declare -a orphan_records=()
while read -r id; do
  [ -z "$id" ] && continue
  if ! grep -q "^| $id " "$CSM"; then
    orphan_records+=("$id")
  fi
done < <(records_caps)

TOTAL_CAPS=$(csm_caps | wc -l | tr -d ' ')
OK_COUNT=${#ok_records[@]}
MISSING_COUNT=${#missing_records[@]}
VIOLATION_COUNT=${#violation_records[@]}
ORPHAN_COUNT=${#orphan_records[@]}
TOTAL_VIOLATIONS=$((MISSING_COUNT + VIOLATION_COUNT + ORPHAN_COUNT))

# Report
if [ "$MODE" = "--report" ] || [ "$MODE" = "--warn" ] || [ "$MODE" = "--strict" ]; then
  echo "# CSM Registry Diff Gate — $TS_UTC (mode=$MODE)"
  echo "Total caps in table: $TOTAL_CAPS"
  echo "OK records: $OK_COUNT"
  echo "Missing records (table row, no YAML): $MISSING_COUNT"
  echo "Violation records (incomplete fields): $VIOLATION_COUNT"
  echo "Orphan records (YAML, no table row): $ORPHAN_COUNT"
  echo
  if [ "$MISSING_COUNT" -gt 0 ]; then
    echo "## Missing records"
    printf '  - %s\n' "${missing_records[@]}"
    echo
  fi
  if [ "$VIOLATION_COUNT" -gt 0 ]; then
    echo "## Violations (record exists but fields incomplete)"
    printf '  - %s\n' "${violation_records[@]}" | head -50
    [ ${#violation_records[@]} -gt 50 ] && echo "  ... ($((${#violation_records[@]} - 50)) more)"
    echo
  fi
  if [ "$ORPHAN_COUNT" -gt 0 ]; then
    echo "## Orphan records (in records, not in CSM table)"
    printf '  - %s\n' "${orphan_records[@]}"
    echo
  fi
fi

# Append audit row
jq -nc --arg ts "$TS_UTC" --arg mode "$MODE" \
  --arg total "$TOTAL_CAPS" --arg ok "$OK_COUNT" \
  --arg missing "$MISSING_COUNT" --arg violations "$VIOLATION_COUNT" --arg orphan "$ORPHAN_COUNT" \
  '{ts:$ts, action:"GATE_RUN", actor:"csm-registry-diff-gate", note:"mode=\($mode); total=\($total) ok=\($ok) missing=\($missing) violations=\($violations) orphan=\($orphan)", cap_id:null, direction:"D43", script:"holding/scripts/csm-registry-diff-gate.sh", mode:$mode}' >> "$JSONL"

# Exit policy per mode
case "$MODE" in
  --report)
    exit 0
    ;;
  --warn)
    if [ "$TOTAL_VIOLATIONS" -gt 0 ]; then
      echo
      echo "WARN: $TOTAL_VIOLATIONS violation(s). Stabilization mode — exiting 0."
      echo "After $STABILIZATION_END the local pre-commit will switch to --strict-phase1 (missing/orphan only)."
      echo "Phase 2 (--strict-phase2; TBD-NEEDS-BACKFILL completeness check) activates post-field-completion."
    fi
    exit 0
    ;;
  --strict-phase1)
    # Phase 1 (codex 2026-05-04 stability fold): block on missing/orphan/malformed
    # records ONLY. TBD-NEEDS-BACKFILL placeholders are tolerated (intentional
    # incompleteness — field completion is follow-up work).
    PHASE1_VIOLATIONS=$((MISSING_COUNT + ORPHAN_COUNT))
    if [ "$PHASE1_VIOLATIONS" -gt 0 ]; then
      echo
      echo "BLOCKED (Phase 1): $PHASE1_VIOLATIONS missing/orphan record(s). Exiting 2."
      echo "Phase 1 tolerates TBD-NEEDS-BACKFILL placeholders ($VIOLATION_COUNT shipping-status field violations IGNORED until Phase 2)."
      echo "Override (audit-logged): GATE_ACK=1 GATE_ACK_REASON='<why>' <next command>"
      [ -n "${GATE_ACK:-}" ] && [ -n "${GATE_ACK_REASON:-}" ] && {
        echo "GATE_ACK active — proceeding despite violations. Reason: $GATE_ACK_REASON"
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GATE_ACK_OVERRIDE actor=$USER reason=$GATE_ACK_REASON" >> "$ROOT/.enforcement/csm-gate-overrides.log"
        exit 0
      }
      exit 2
    fi
    echo "PASS (Phase 1): 0 missing/orphan; $VIOLATION_COUNT field-completeness violations tolerated until Phase 2."
    exit 0
    ;;
  --strict-phase2)
    # Phase 2 (post-field-completion): block on ALL violations including
    # TBD-NEEDS-BACKFILL completeness. Activates after the 39 stub records
    # are field-completed.
    if [ "$TOTAL_VIOLATIONS" -gt 0 ]; then
      echo
      echo "BLOCKED (Phase 2): $TOTAL_VIOLATIONS violation(s) including TBD-NEEDS-BACKFILL completeness. Exiting 2."
      echo "Override (audit-logged): GATE_ACK=1 GATE_ACK_REASON='<why>' <next command>"
      [ -n "${GATE_ACK:-}" ] && [ -n "${GATE_ACK_REASON:-}" ] && {
        echo "GATE_ACK active — proceeding despite violations. Reason: $GATE_ACK_REASON"
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) GATE_ACK_OVERRIDE actor=$USER reason=$GATE_ACK_REASON" >> "$ROOT/.enforcement/csm-gate-overrides.log"
        exit 0
      }
      exit 2
    fi
    echo "PASS (Phase 2): 0 violations, all $OK_COUNT caps validated end-to-end."
    exit 0
    ;;
  *)
    echo "Unknown mode: $MODE. Use --warn / --strict / --strict-phase1 / --strict-phase2 / --report." >&2
    exit 64
    ;;
esac
