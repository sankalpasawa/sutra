#!/usr/bin/env bash
# operationalization-check.sh — D30a Operationalization presence gate
#
# Plugin-native MVP, L0 promotion from holding/hooks/operationalization-check.sh
# via PROTO-021 BUILD-LAYER on 2026-04-23.
#
# Responsibility: block Edit/Write to an L0-L2 artifact path when the file
# does NOT contain a `## Operationalization` section with the 6 required
# subsections (Measurement / Adoption / Monitoring / Iteration / DRI /
# Decommission). Enforces D30a "Ship Is Not Done".
#
# This is the MVP plugin version. It covers generic enforced-path patterns
# any Sutra instance would plausibly have. Asawa's authoring instance
# retains holding/hooks/operationalization-check.sh for its fuller Tier A+B
# path classification + grandfathering via state.yaml.operationalization.
# cutover_commit; plugin version reaches feature parity in v2.
#
# Default-OFF per D32 (Hot-Reloadable Hooks, Default Off).
# Enablement: set `enabled_hooks.operationalization-check: true` in the
# instance's os/SUTRA-CONFIG.md. Absent flag = no-op exit.
#
# Enforced path patterns (defaults, universal shape):
#   hooks/**/*.sh              (any shell hook)
#   departments/**/*.sh        (department scripts)
#   charters/**/*.md           (initiative charters)
#   protocols/**/*.md          (protocol specs)
#   engines/**/*.md            (engine specs)
#   os/charters/**/*.md        (Sutra-layout charters)
#   os/protocols/**/*.md       (Sutra-layout protocols)
#   os/engines/**/*.md         (Sutra-layout engines)
#
# Override per-call: OPS_ACK=1 OPS_ACK_REASON='<why>' (logged to ledger).
# Override global: ~/.ops-check-disabled file OR OPS_CHECK_DISABLED=1 env.
#
# Ledger: .enforcement/ops-check.jsonl (per-instance append-only).
#
# Source: sutra/marketplace/plugin/hooks/operationalization-check.sh
# Spec: sutra/layer2-operating-system/PROTOCOLS.md §PROTO-000 (6-part rule)
#       + sutra/os/charters/OPERATIONALIZATION.md
# Template: holding/OPERATIONALIZATION-STANDARD.md
# Promoted-from: holding/hooks/operationalization-check.sh (L1→L0 2026-04-23)

set -uo pipefail

# ── Kill-switches ───────────────────────────────────────────────────────────
[ -f "$HOME/.ops-check-disabled" ] && exit 0
[ "${OPS_CHECK_DISABLED:-0}" = "1" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# ── D32 enablement check (default-off) ──────────────────────────────────────
CFG="$REPO_ROOT/os/SUTRA-CONFIG.md"
if [ ! -f "$CFG" ]; then
  # No SUTRA-CONFIG → instance hasn't opted in; exit clean.
  exit 0
fi
if ! grep -qE "^[[:space:]]+operationalization-check:[[:space:]]+true" "$CFG" 2>/dev/null; then
  # Config present but flag absent/false → not enabled.
  exit 0
fi

# ── File-path resolution (env or stdin JSON) ────────────────────────────────
FILE_PATH="${TOOL_INPUT_file_path:-}"
if [ -z "$FILE_PATH" ] && [ ! -t 0 ]; then
  _JSON=$(cat 2>/dev/null)
  if [ -n "$_JSON" ]; then
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    else
      FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi
  fi
fi
[ -z "$FILE_PATH" ] && exit 0

REL_PATH="${FILE_PATH#$REPO_ROOT/}"
LEDGER="$REPO_ROOT/.enforcement/ops-check.jsonl"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null

# ── Override ────────────────────────────────────────────────────────────────
if [ "${OPS_ACK:-0}" = "1" ]; then
  REASON=$(printf '%s' "${OPS_ACK_REASON:-no-reason-given}" | tr -d '"\\' | tr '\n\r' '  ')
  _SAFE=$(printf '%s' "$REL_PATH" | tr -d '"\\' | tr '\n\r' '  ')
  echo "{\"ts\":$(date +%s),\"event\":\"override\",\"file\":\"$_SAFE\",\"reason\":\"$REASON\"}" >> "$LEDGER"
  echo "  [ops-check] override accepted (OPS_ACK=1): $REASON" >&2
  exit 0
fi

# ── Enforced path detection (default patterns) ──────────────────────────────
is_enforced() {
  case "$1" in
    hooks/*.sh|hooks/**/*.sh) return 0 ;;
    departments/*/*.sh|departments/**/*.sh) return 0 ;;
    charters/*.md|charters/**/*.md) return 0 ;;
    protocols/*.md|protocols/**/*.md) return 0 ;;
    engines/*.md|engines/**/*.md) return 0 ;;
    os/charters/*.md|os/charters/**/*.md) return 0 ;;
    os/protocols/*.md|os/protocols/**/*.md) return 0 ;;
    os/engines/*.md|os/engines/**/*.md) return 0 ;;
    os/d-engines/*.md|os/d-engines/**/*.md) return 0 ;;
    *) return 1 ;;
  esac
}

if ! is_enforced "$REL_PATH"; then
  exit 0
fi

# ── Ops section presence check ──────────────────────────────────────────────
has_ops_section() {
  local f="$1"
  [ -f "$f" ] || return 1
  grep -qE '^(#[[:space:]]*)?##[[:space:]]+([0-9]+\.[[:space:]]+)?Operationalization' "$f" || return 1
  local count=0
  for pat in 'Measurement' 'Adoption' 'Monitoring' 'Iteration' 'DRI' 'Decommission'; do
    if grep -qE "^(#[[:space:]]*)?###[[:space:]]+[1-6]\.[[:space:]]*${pat}" "$f"; then
      count=$((count + 1))
    fi
  done
  [ "$count" -ge 6 ]
}

if has_ops_section "$FILE_PATH"; then
  _SAFE=$(printf '%s' "$REL_PATH" | tr -d '"\\' | tr '\n\r' '  ')
  echo "{\"ts\":$(date +%s),\"event\":\"allow\",\"file\":\"$_SAFE\"}" >> "$LEDGER"
  exit 0
fi

# ── Missing ops section → block ────────────────────────────────────────────
_SAFE=$(printf '%s' "$REL_PATH" | tr -d '"\\' | tr '\n\r' '  ')
echo "{\"ts\":$(date +%s),\"event\":\"block\",\"file\":\"$_SAFE\"}" >> "$LEDGER"
{
  echo ""
  echo "BLOCKED — Operationalization section missing (D30a, Sutra plugin)"
  echo "  File:   $REL_PATH"
  echo ""
  echo "  Required: inline '## Operationalization' section with 6 subsections:"
  echo "    1. Measurement mechanism"
  echo "    2. Adoption mechanism"
  echo "    3. Monitoring / escalation"
  echo "    4. Iteration trigger"
  echo "    5. DRI"
  echo "    6. Decommission criteria"
  echo ""
  echo "  Template: sutra/os/charters/OPERATIONALIZATION.md"
  echo "  Override (one call): OPS_ACK=1 OPS_ACK_REASON='<why>' <tool>"
  echo "  Disable (per-instance): remove 'operationalization-check: true'"
  echo "    from os/SUTRA-CONFIG.md enabled_hooks block."
  echo ""
} >&2
exit 2

# ================================================================================
# ## Operationalization
#
# ### 1. Measurement mechanism
# .enforcement/ops-check.jsonl rows by event type (allow/block/override) in each
# instance. Aggregated fleet-wide via Sutra Analytics Dept (future). Metric:
# `ops_section_block_rate` per instance; spike = instance just enabled without
# remediation. Null: silent exit 0 when instance hasn't flagged enabled_hooks.
#
# ### 2. Adoption mechanism
# Ships via plugin. Default-OFF per D32 (Hot-Reloadable Hooks, Default Off);
# each instance flips `enabled_hooks.operationalization-check: true` in their
# own os/SUTRA-CONFIG.md. Delivery: automatic on next `claude plugin marketplace
# update sutra` after plugin version bump. Activation: per-instance explicit.
#
# ### 3. Monitoring / escalation
# Per-instance DRI reviews .enforcement/ops-check.jsonl. Cohort-wide DRI (Sutra
# Forge) reviews the fleet aggregate. Warn: >5 blocks/day per instance. Breach:
# >20 blocks/day (instance just enabled and is triaging; escalate with migration).
#
# ### 4. Iteration trigger
# v2 adds: Tier A+B path granularity from Asawa's holding/hooks version,
# grandfathering via state.yaml.operationalization.cutover_commit, plugin-
# native state.yaml read. Trigger for v2: when Asawa's holding copy reaches
# 30 days of stability with parity gaps documented, promote the richer
# version and retire holding/hooks copy.
#
# ### 5. DRI
# Sutra Forge (authoring team) owns the plugin version. Per-instance DRI
# owns enablement in that instance's SUTRA-CONFIG.md.
#
# ### 6. Decommission criteria
# Retire when D30a itself is retired OR when every Sutra instance ships a
# machine-readable ops-manifest (yaml/json) adjacent to each enforced
# artifact, making string-grep obsolete. Signal: >=90% of enforced-path
# edits show allow outcome for 60 days (habit internalized).
# ================================================================================
