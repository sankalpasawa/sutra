#!/bin/bash
# subagent-os-contract.sh — PostToolUse on Task tool
#
# Plugin-native, L0 promotion from holding/hooks/subagent-os-contract.sh
# via PROTO-021 BUILD-LAYER on 2026-04-23. Drop-in replacement for the
# "[TEMP — remove when Sutra plugin ships]" holding copy.
#
# Validates that subagent responses contain the Sutra OS contract:
#   Boot block: INPUT / TYPE / DEPT / DEPTH / EFFORT / IMPACT   (6 fields)
#   Footer:     TRIAGE / ESTIMATE / ACTUAL / OS TRACE           (4 fields)
#
# Enforcement shape (PostToolUse reality):
#   The subagent has already run by the time this hook fires. `exit 2`
#   is feedback-to-model, not a true block. PreToolUse briefing gate
#   (the parent-prompt contract check) is where real HARD enforcement
#   lives; this hook measures child compliance.
#
#     Boot missing   → soft WARN, exit 0 (telemetry row logged)
#     Footer missing → BLOCK (exit 2) — feedback to model; re-dispatch
#                      with contract OR override
#
# Override (per-call): SUBAGENT_CONTRACT_ACK=1 SUBAGENT_CONTRACT_ACK_REASON='<why>'
# Kill-switch: ~/.subagent-contract-disabled OR SUBAGENT_CONTRACT_DISABLED=1
#
# Default-OFF per D32 — each instance opts in via:
#   enabled_hooks:
#     subagent-os-contract: true
#   (in instance's os/SUTRA-CONFIG.md)
#
# Telemetry: one JSONL row per dispatch to
#   <instance>/.enforcement/subagent-contract.jsonl
# Feeds Sutra Analytics Dept (child_agent_os_adoption_pct dimension)
# when Analytics Dept ships in a future plugin release.
#
# Fail-safe: if stdin JSON is malformed or response cannot be extracted,
# exit 0 + log `status:response_empty` row.
#
# Source: sutra/marketplace/plugin/hooks/subagent-os-contract.sh
# Promoted-from: holding/hooks/subagent-os-contract.sh (L1→L0 2026-04-23)
# Replaces: holding/hooks/subagent-os-contract.sh "[TEMP — remove when
#   Sutra plugin ships]" block (per Asawa CLAUDE.md §Agent Dispatch).

set -uo pipefail

# ── Kill-switches ───────────────────────────────────────────────────────────
[ -f "$HOME/.subagent-contract-disabled" ] && exit 0
[ "${SUBAGENT_CONTRACT_DISABLED:-0}" = "1" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"

# ── D32 enablement check (default-off) ──────────────────────────────────────
CFG="$REPO_ROOT/os/SUTRA-CONFIG.md"
if [ ! -f "$CFG" ]; then exit 0; fi
if ! grep -qE "^[[:space:]]+subagent-os-contract:[[:space:]]+true" "$CFG" 2>/dev/null; then
  exit 0
fi

LOG_FILE="$REPO_ROOT/.enforcement/subagent-contract.jsonl"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null

# ── Read stdin JSON (Claude Code passes hook payload) ──────────────────────
JSON=""
if [ ! -t 0 ]; then
  JSON=$(cat)
fi

TOOL_NAME="${TOOL_NAME:-}"
if [ -z "$TOOL_NAME" ] && [ -n "$JSON" ] && command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$JSON" | jq -r '.tool_name // empty' 2>/dev/null)
fi
case "$TOOL_NAME" in
  Task|Agent) ;;
  *) exit 0 ;;
esac

# ── Extract subagent response (path can vary across CC versions) ───────────
RESPONSE=""
if [ -n "$JSON" ] && command -v jq >/dev/null 2>&1; then
  for path in '.tool_response' '.tool_response.content' '.tool_response.text' \
              '.tool_response.content[0].text' '.response' '.output'; do
    CANDIDATE=$(printf '%s' "$JSON" | jq -r "$path // empty" 2>/dev/null)
    if [ -n "$CANDIDATE" ] && [ "$CANDIDATE" != "null" ]; then
      RESPONSE="$CANDIDATE"
      break
    fi
  done
fi

SUBAGENT_TYPE="unknown"
if [ -n "$JSON" ] && command -v jq >/dev/null 2>&1; then
  SUBAGENT_TYPE=$(printf '%s' "$JSON" | jq -r '.tool_input.subagent_type // "unknown"' 2>/dev/null)
fi

if [ -z "$RESPONSE" ]; then
  TS=$(date +%s)
  printf '{"ts":%s,"subagent_type":"%s","status":"response_empty","boot":0,"footer":0,"score":0}\n' \
    "$TS" "$SUBAGENT_TYPE" >> "$LOG_FILE"
  exit 0
fi

# ── Validate boot block (6 fields) ──────────────────────────────────────────
BOOT_PASS=0
for field in '^INPUT:' '^TYPE:' '^DEPT:' '^DEPTH:' '^EFFORT:' '^IMPACT:'; do
  if printf '%s' "$RESPONSE" | grep -qE "$field"; then
    BOOT_PASS=$((BOOT_PASS + 1))
  fi
done

# ── Validate footer (4 fields, line-anchored in tail) ───────────────────────
FOOTER_PASS=0
TAIL_TEXT=$(printf '%s' "$RESPONSE" | tail -30)
printf '%s' "$TAIL_TEXT" | grep -qE '^TRIAGE: depth_selected=[0-9]' && FOOTER_PASS=$((FOOTER_PASS + 1))
printf '%s' "$TAIL_TEXT" | grep -qE '^ESTIMATE: tokens_est=[0-9]'   && FOOTER_PASS=$((FOOTER_PASS + 1))
printf '%s' "$TAIL_TEXT" | grep -qE '^ACTUAL:'                       && FOOTER_PASS=$((FOOTER_PASS + 1))
printf '%s' "$TAIL_TEXT" | grep -qE '^OS TRACE:'                     && FOOTER_PASS=$((FOOTER_PASS + 1))

SCORE=$((BOOT_PASS + FOOTER_PASS))
TS=$(date +%s)

# ── Telemetry ───────────────────────────────────────────────────────────────
printf '{"ts":%s,"subagent_type":"%s","boot":%s,"footer":%s,"score":%s,"max":10}\n' \
  "$TS" "$SUBAGENT_TYPE" "$BOOT_PASS" "$FOOTER_PASS" "$SCORE" >> "$LOG_FILE"

# ── Override ────────────────────────────────────────────────────────────────
if [ "${SUBAGENT_CONTRACT_ACK:-0}" = "1" ]; then
  REASON="${SUBAGENT_CONTRACT_ACK_REASON:-no-reason-given}"
  echo "subagent-os-contract: override active (reason: $REASON; score=$SCORE/10)" >&2
  exit 0
fi

# ── Soft WARN on boot ──────────────────────────────────────────────────────
if [ "$BOOT_PASS" -lt 6 ]; then
  echo "subagent-os-contract: WARN — subagent_type='$SUBAGENT_TYPE' boot block $BOOT_PASS/6 (soft; logged)" >&2
fi

# ── HARD feedback on footer ─────────────────────────────────────────────────
if [ "$FOOTER_PASS" -lt 4 ]; then
  cat >&2 <<EOF
subagent-os-contract: BLOCK — subagent_type='$SUBAGENT_TYPE' footer $FOOTER_PASS/4
  Required footer (every subagent response):
    TRIAGE: depth_selected=<N>, depth_correct=<N>, class=<correct|overtriage|undertriage>
    ESTIMATE: tokens_est=<N>, files_est=<M>, time_min_est=<T>, category=<slug>
    ACTUAL:   tokens≈<N>, files=<M>, time_min≈<T>, category=<slug>
    OS TRACE: <route> > <domain> > <node-count> > <terminal> > <output>
  Re-dispatch with the contract OR override:
    SUBAGENT_CONTRACT_ACK=1 SUBAGENT_CONTRACT_ACK_REASON='<why>'
EOF
  exit 2
fi

exit 0

# ================================================================================
# ## Operationalization
#
# ### 1. Measurement mechanism
# .enforcement/subagent-contract.jsonl row per dispatch. Metric:
# `child_agent_os_adoption_pct` = mean(score/10) across 24h dispatches per
# instance. Target ≥80% after 14 days of enablement. Null handling: no rows
# when instance hasn't enabled OR no subagents dispatched.
#
# ### 2. Adoption mechanism
# Ships via plugin. Default-OFF per D32 — each instance sets
# `enabled_hooks.subagent-os-contract: true` in its own os/SUTRA-CONFIG.md.
# Delivery: `claude plugin marketplace update sutra`. Activation: per-instance
# explicit. Intended first-cohort: Asawa + Sutra dogfood + DayFlow.
#
# ### 3. Monitoring / escalation
# Per-instance DRI reviews adoption % weekly. Sutra Forge reviews fleet aggregate
# (future Analytics Dept plugin). Warn: adoption % <50% at 7d post-enable
# (parent prompts not briefing contract). Breach: adoption % <30% at 14d
# (escalate — parent-prompt briefing discipline not sticking).
#
# ### 4. Iteration trigger
# Extend boot/footer schema when new OS blocks become mandatory (e.g. if
# BUILD-LAYER block gets added to subagent boot). Tighten footer HARD→real-
# HARD when PreToolUse Task prompt-contract check lands in plugin (replaces
# the "can't truly block at PostToolUse" caveat).
#
# ### 5. DRI
# Sutra Forge owns the plugin version. Per-instance DRI owns enablement.
#
# ### 6. Decommission criteria
# Retire when (a) PreToolUse:Task prompt-contract check lands in plugin and
# fully supersedes post-dispatch telemetry, OR (b) subagent infra changes such
# that the OS-contract shape no longer applies.
# ================================================================================
