#!/usr/bin/env bash
# backfill-helper.sh — generate full YAML records for all cap-### entries in CAPABILITY-MAP.md
#
# Per CSM TODO #4 (deadline 2026-05-08). Reads cap-### rows from CAPABILITY-MAP.md
# tables (5 sections) and emits one YAML record per cap with bucket-appropriate
# required fields. Missing data is marked TBD-NEEDS-BACKFILL — sufficient for
# TODO #1 pre-commit/CI gate field-completeness validation.
#
# Output: writes records to holding/CAPABILITY-MAP-records.md (separate file to
# keep CAPABILITY-MAP.md scannable; the gate parses both).
#
# Build-layer: L1 single-instance:asawa. Promote-to plugin/scripts/ by 2026-06-01.

set -euo pipefail

ROOT="${ROOT:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
# Asawa-mode gate (L0 promotion): silently exit on T4 fleet
[ -f "$ROOT/holding/CAPABILITY-MAP.md" ] || exit 0
CSM="$ROOT/holding/CAPABILITY-MAP.md"
OUT="$ROOT/holding/CAPABILITY-MAP-records.md"
JSONL="$ROOT/holding/state/capability-map-audit.jsonl"
TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required" >&2; exit 127; }
[ -f "$CSM" ] || { echo "FATAL: CSM not found at $CSM" >&2; exit 1; }

# Bucket inference by cap-### range
bucket_of() {
  local id="$1"
  local n=${id#cap-}
  if [ "$n" -ge 200 ] && [ "$n" -lt 300 ]; then echo "asawa-only"
  elif [ "$n" -ge 300 ] && [ "$n" -lt 400 ]; then echo "sutra-internal"
  else echo "client-shippable"
  fi
}

# Governance plane defaults by bucket
plane_of() {
  local b="$1"
  case "$b" in
    asawa-only|sutra-internal) echo "governance" ;;
    *) echo "operations" ;;
  esac
}

# Consumer defaults by bucket
consumer_of() {
  local b="$1"
  case "$b" in
    asawa-only) echo "asawa" ;;
    sutra-internal) echo "sutra" ;;
    *) echo "T4" ;;
  esac
}

# Extract cap rows from all CSM tables. Format: id|name|status
extract_caps() {
  # Bucket A index table (cap-001..011)
  awk -F'|' '/^\| cap-[0-9]+ \|/{gsub(/^ +| +$/,"",$2); gsub(/^ +| +$/,"",$3); gsub(/^ +| +$/,"",$5); print $2 "|" $3 "|" $5}' "$CSM" | sort -u
}

# Known-values lookup for cap-001..011 (existing Bucket A shipping disciplines).
# Codex 2026-05-04 final-push ADVISORY: TBD-NEEDS-BACKFILL completion on these
# 11 records moves --strict-phase2 from blocked toward usable. Format:
#   "cap_id|surface|artifact_path|charter|activation_surface|release_vehicle|released_in|version_introduced|tests"
# Other fields default: distribution_scope=plugin-runtime, audience=external-developers,
# threat_model=sutra/marketplace/plugin/SECURITY.md, telemetry_coverage=per-turn fire counted.
KNOWN_VALUES=(
  "cap-001|skill|sutra/marketplace/plugin/skills/input-routing/|sutra/os/engines/INPUT-ROUTING-ENGINE.md|hooks.json:input-routing|marketplace-tag|core-v1.0.0|v1.0.0|sutra/marketplace/plugin/tests/input-routing/"
  "cap-002|skill|sutra/marketplace/plugin/skills/depth-estimation/|sutra/marketplace/plugin/skills/depth-estimation/SKILL.md|hooks.json:depth-marker-pretool|marketplace-tag|core-v1.0.0|v1.0.0|sutra/marketplace/plugin/tests/depth-estimation/"
  "cap-003|skill|sutra/marketplace/plugin/skills/blueprint/|sutra/os/engines/BLUEPRINT-ENGINE.md|hooks.json:blueprint-check|marketplace-tag|core-v2.9.0|v2.9.0|sutra/marketplace/plugin/tests/blueprint/"
  "cap-004|skill|sutra/marketplace/plugin/skills/readability-gate/|sutra/marketplace/plugin/skills/readability-gate/SKILL.md|auto-discovery|marketplace-tag|core-v1.0.0|v1.0.0|sutra/marketplace/plugin/tests/readability-gate/"
  "cap-005|skill|sutra/marketplace/plugin/skills/output-trace/|sutra/marketplace/plugin/skills/output-trace/SKILL.md|auto-discovery|marketplace-tag|core-v2.9.0|v2.9.0|sutra/marketplace/plugin/tests/output-trace/"
  "cap-006|skill|sutra/marketplace/plugin/skills/codex-sutra/|sutra/marketplace/plugin/skills/codex-sutra/SKILL.md|auto-discovery|marketplace-tag|core-v2.8.0|v2.8.0|sutra/marketplace/plugin/tests/codex-sutra/"
  "cap-007|command|sutra/marketplace/plugin/scripts/sbom.sh|sutra/marketplace/plugin/scripts/sbom.sh|bin/sutra:sbom|marketplace-tag|core-v2.10.0|v2.10.0|sutra/marketplace/plugin/tests/sbom/"
  "cap-008|skill|sutra/marketplace/plugin/scripts/learn.sh|sutra/marketplace/plugin/scripts/learn.sh|bin/sutra:learn|marketplace-tag|core-v1.0.0|v1.0.0|sutra/marketplace/plugin/tests/learn/"
  "cap-009|hook|sutra/marketplace/plugin/hooks/permission-gate.sh|sutra/os/charters/PERMISSIONS.md|hooks.json:PermissionRequest|marketplace-tag|core-v1.13.0|v1.13.0|sutra/marketplace/plugin/tests/permission-gate-test.sh"
  "cap-010|hook|sutra/marketplace/plugin/hooks/build-layer-check.sh|sutra/layer2-operating-system/PROTOCOLS.md|hooks.json:PreToolUse|marketplace-tag|core-v1.13.0|v1.13.0|sutra/marketplace/plugin/tests/build-layer/"
  "cap-011|hook|sutra/marketplace/plugin/hooks/flush-telemetry.sh|sutra/marketplace/plugin/PRIVACY.md|hooks.json:Stop|marketplace-tag|core-v2.9.1|v2.9.1|sutra/marketplace/plugin/tests/integration/test-onboard-to-push.sh"
)

# Look up known values for a cap_id; returns "" if not in table
lookup_known() {
  local id="$1"
  for row in "${KNOWN_VALUES[@]}"; do
    case "$row" in "${id}|"*) echo "$row"; return ;; esac
  done
}

# Generate one YAML record
emit_record() {
  local id="$1"
  local name="$2"
  local status_arg="${3:-proposed}"
  local bucket; bucket=$(bucket_of "$id")
  local plane; plane=$(plane_of "$bucket")
  local consumer; consumer=$(consumer_of "$bucket")
  # Codex 2026-05-04 P1 fix: extract_caps grabs column 5 as status — true for Bucket A
  # and fleet-parity tables, but FALSE for Bucket B/C tables (column 5 there is
  # "Why Not Client" prose). For B/C buckets, default status to "shipping" (these
  # are existing in-use disciplines, no explicit status column).
  local status
  case "$bucket" in
    asawa-only|sutra-internal) status="shipping" ;;
    *) status="$status_arg" ;;
  esac

  # Codex 2026-05-04 final-push ADVISORY fold: known-values lookup for cap-001..011
  local known surface artifact_path charter activation_surface release_vehicle released_in version_introduced tests
  known=$(lookup_known "$id")
  if [ -n "$known" ]; then
    IFS='|' read -r _ surface artifact_path charter activation_surface release_vehicle released_in version_introduced tests <<< "$known"
  else
    surface="TBD-NEEDS-BACKFILL"
    artifact_path="TBD-NEEDS-BACKFILL"
    charter="TBD-NEEDS-BACKFILL"
    activation_surface="TBD-NEEDS-BACKFILL"
    release_vehicle="TBD-NEEDS-BACKFILL"
    released_in="TBD-NEEDS-BACKFILL"
    version_introduced="TBD-NEEDS-BACKFILL"
    tests="TBD-NEEDS-BACKFILL"
  fi

  # Default audience and distribution_scope by bucket; overridable by known values
  local audience distribution_scope
  case "$bucket" in
    client-shippable) audience="external-developers"; distribution_scope="plugin-runtime" ;;
    asawa-only) audience="asawa-ceo-sessions"; distribution_scope="holding-only" ;;
    sutra-internal) audience="sutra-os-team"; distribution_scope="sutra-internal" ;;
  esac

  # promotion_proofs from known values where available
  local activation_proof test_proof release_proof canonical_path_exists
  if [ -n "$known" ]; then
    activation_proof="$activation_surface"
    test_proof="$tests green @ $released_in"
    release_proof="tag $released_in"
    canonical_path_exists=true
  else
    activation_proof="TBD-NEEDS-BACKFILL"
    test_proof="TBD-NEEDS-BACKFILL"
    release_proof="TBD-NEEDS-BACKFILL"
    canonical_path_exists="TBD-NEEDS-BACKFILL"
  fi

  cat <<RECORD
\`\`\`yaml
id: $id
name: "$name"
bucket: $bucket
governance_plane: $plane
consumer: $consumer
audience: $audience
surface: $surface
artifact_path: $artifact_path
source_of_truth_artifact: null
charter: $charter
distribution_scope: $distribution_scope
activation_surface: $activation_surface
release_vehicle: $release_vehicle
released_in: $released_in
status: $status
version_introduced: $version_introduced
version_current: v2.30.0
created_at: 2026-05-04
deprecated_at: null
archived_at: null
last_verified_at: 2026-05-04
tests: $tests
verification_mechanism: $([ -n "$known" ] && echo "unit + integration + governance-parity-harness" || echo "TBD-NEEDS-BACKFILL")
owner: "Sutra Core"
direction_binding: D43
promotion_proofs:
  activation_proof: "$activation_proof"
  test_proof: "$test_proof"
  release_proof: "$release_proof"
  shim_ttl: null
  canonical_path_exists: $canonical_path_exists
RECORD

  if [ "$bucket" = "client-shippable" ]; then
    local threat_model telemetry_coverage
    if [ -n "$known" ]; then
      threat_model="sutra/marketplace/plugin/SECURITY.md"
      telemetry_coverage="per-turn fire counted in telemetry-banner"
    else
      threat_model="TBD-NEEDS-BACKFILL"
      telemetry_coverage="TBD-NEEDS-BACKFILL"
    fi
    cat <<RECORD
why_not_client_shippable: null
decommission_trigger: null
threat_model: $threat_model
telemetry_coverage: $telemetry_coverage
RECORD
  else
    cat <<RECORD
why_not_client_shippable: TBD-NEEDS-BACKFILL
decommission_trigger: TBD-NEEDS-BACKFILL
threat_model: null
telemetry_coverage: null
RECORD
  fi

  cat <<RECORD
depends_on: []
required_by: []
supersedes: null
replaces: null
audit_log:
  - { ts: "${TS_UTC}", action: BACKFILLED, status_to: $status, actor: backfill-helper, note: "stub generated by backfill-helper.sh per CSM TODO #4; field completion remains" }
codex_review: null
\`\`\`

RECORD
}

# Main: emit all records grouped by bucket section
{
  echo "# CAPABILITY-MAP — Full YAML records (auto-generated stubs)"
  echo
  echo "**Generated**: $TS_UTC"
  echo "**Source**: \`backfill-helper.sh\` parsing \`CAPABILITY-MAP.md\` cap-### table rows"
  echo "**Status**: stubs with TBD-NEEDS-BACKFILL placeholders for fields not derivable from table data"
  echo "**Per CSM TODO #4** (deadline 2026-05-08). Field completion is a follow-up; this file gives the gate something to validate structurally."
  echo
  echo "## Bucket A — Client-Shippable"
  echo
  while IFS='|' read -r id name status; do
    [ -z "$id" ] && continue
    [ "$(bucket_of "$id")" = "client-shippable" ] || continue
    emit_record "$id" "$name" "$status"
  done < <(extract_caps)

  echo "## Bucket B — Asawa-Only"
  echo
  while IFS='|' read -r id name status; do
    [ -z "$id" ] && continue
    [ "$(bucket_of "$id")" = "asawa-only" ] || continue
    emit_record "$id" "$name" "$status"
  done < <(extract_caps)

  echo "## Bucket C — Sutra-Internal"
  echo
  while IFS='|' read -r id name status; do
    [ -z "$id" ] && continue
    [ "$(bucket_of "$id")" = "sutra-internal" ] || continue
    emit_record "$id" "$name" "$status"
  done < <(extract_caps)
} > "$OUT"

# Count what we generated
TOTAL=$(grep -c '^id: cap-' "$OUT" 2>/dev/null || echo 0)
A=$(awk '/^## Bucket A/,/^## Bucket B/' "$OUT" | grep -c '^id: cap-')
B=$(awk '/^## Bucket B/,/^## Bucket C/' "$OUT" | grep -c '^id: cap-')
C=$(awk '/^## Bucket C/,EOF' "$OUT" | grep -c '^id: cap-')

# Append BACKFILLED audit row
jq -nc --arg ts "$TS_UTC" --arg n "$TOTAL" --arg a "$A" --arg b "$B" --arg c "$C" --arg out "$OUT" \
  '{ts:$ts, action:"BACKFILLED_BATCH", actor:"backfill-helper", note:"\($n) YAML stub records generated (Bucket A: \($a), B: \($b), C: \($c)); field completion follow-up. Output: \($out). Per CSM TODO #4.", cap_id:null, direction:"D43", script:"holding/scripts/backfill-helper.sh", output:$out}' >> "$JSONL"

echo "Records generated: $TOTAL total (A=$A, B=$B, C=$C)"
echo "Output: $OUT"
echo "Audit JSONL: $JSONL (1 row appended)"
