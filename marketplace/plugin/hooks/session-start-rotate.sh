#!/usr/bin/env bash
# SessionStart hook — rotate tracked logs past threshold (Tokens charter C2).
# Fires once at session start. Silent no-op when all logs under threshold.
# Never fails the session — rotation errors go to stderr only.

set -uo pipefail

# Customer-box guard: this hook rotates Asawa-internal logs that don't exist
# on plugin-only customer machines. Silent return.
if [ -r "${CLAUDE_PLUGIN_ROOT:-}/lib/is_customer_box.sh" ]; then
  . "${CLAUDE_PLUGIN_ROOT}/lib/is_customer_box.sh"
  is_customer_box && exit 0
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
ROTATE="$REPO_ROOT/holding/hooks/rotate-logs.sh"

# Exit cleanly if utility missing (safety during partial deploys)
if [ ! -x "$ROTATE" ]; then
  exit 0
fi

# Logs to rotate (path, max-lines)
LOGS=(
  "$REPO_ROOT/holding/hooks/hook-log.jsonl:10000"
  "$REPO_ROOT/holding/ESTIMATION-LOG.jsonl:10000"
  "$REPO_ROOT/holding/TRIAGE-LOG.jsonl:10000"
  "$REPO_ROOT/.enforcement/routing-misses.log:10000"
  "$REPO_ROOT/.enforcement/codex-reviews/gate-log.jsonl:10000"
  "$REPO_ROOT/.enforcement/proto-018-reminders.log:5000"
  "$REPO_ROOT/.enforcement/d30-policy-only.log:5000"
  "$REPO_ROOT/.enforcement/god-mode.log:5000"
  "$REPO_ROOT/.enforcement/sutra-deploys.log:5000"
)

for entry in "${LOGS[@]}"; do
  path="${entry%:*}"
  max="${entry##*:}"
  bash "$ROTATE" "$path" "$max" 2>/dev/null || true
done

exit 0

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
