#!/bin/bash
# PROTO-004 — Keys in Env Vars Only
# PreToolUse on Write/Edit: scan content about to be written for bare
# API-key-looking strings landing in a non-env file.
#
# TIER: HARD (exit 2, blocks the Write/Edit). Promoted from SOFT on 2026-04-23
# per Plan docs/superpowers/plans/2026-04-09-competitor-integration-plan.md
# Task 1 + founder directive. Matches dispatcher-pretool.sh Check 5 semantics
# (lines 236/266) — closes the SOFT/HARD divergence between the extracted
# hook and the in-dispatcher check.
#
# BUILD-LAYER: L0 (plugin-native, promoted from holding 2026-04-23 per
#              PROTO-021 — plugin v1.12.0).
#
# Default-OFF per D32 — each instance opts in via:
#   enabled_hooks:
#     keys-in-env-vars: true
#   (in instance's os/SUTRA-CONFIG.md)
#
# Override: PROTO004_ACK=1 PROTO004_ACK_REASON='<why>' <tool call>
# Kill-switch: touch ~/.proto004-disabled  OR  PROTO004_DISABLED=1

set -u

[ -e "$HOME/.proto004-disabled" ] || [ "${PROTO004_DISABLED:-}" = "1" ] && exit 0

# D32 enablement check (default-off)
_CFG="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}/os/SUTRA-CONFIG.md"
if [ ! -f "$_CFG" ]; then exit 0; fi
if ! grep -qE "^[[:space:]]+keys-in-env-vars:[[:space:]]+true" "$_CFG" 2>/dev/null; then exit 0; fi

# Claude Code passes event via stdin JSON
if [ -t 0 ]; then exit 0; fi
_JSON=$(cat 2>/dev/null || true)
[ -z "$_JSON" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
  CONTENT=$(printf '%s' "$_JSON" | jq -r '.tool_input.content // .tool_input.new_string // empty' 2>/dev/null)
else
  FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  CONTENT=""
fi

[ -z "$FILE_PATH" ] && exit 0

# Skip env-type files (legitimate home for secrets)
case "$FILE_PATH" in
  *.env|*.env.*|.env|.envrc|*/secrets/*|*/.ssh/*|*keys.json|*credentials*)
    exit 0 ;;
esac

# Skip binary / non-text paths
case "$FILE_PATH" in
  *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.zip|*.tar|*.gz|*.so|*.dylib) exit 0 ;;
esac

# Patterns matching common API-key shapes
# Sources: OWASP secret scanners, git-secrets default patterns
PATTERN='(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|xoxb-[0-9A-Za-z-]{20,}|ya29\.[A-Za-z0-9_-]+|AIza[0-9A-Za-z_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'

# Match in provided content
if [ -n "$CONTENT" ] && printf '%s' "$CONTENT" | grep -qE "$PATTERN"; then
  if [ "${PROTO004_ACK:-0}" = "1" ]; then
    REASON="${PROTO004_ACK_REASON:-no-reason-given}"
    REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
    mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
    echo "{\"ts\":$(date +%s),\"event\":\"proto004-override\",\"file\":\"$FILE_PATH\",\"reason\":\"$REASON\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
    echo "  PROTO-004 override accepted: $REASON" >&2
    exit 0
  fi
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  echo "{\"ts\":$(date +%s),\"event\":\"proto004-block\",\"file\":\"$FILE_PATH\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
  echo "BLOCKED: PROTO-004 — API-key-shaped string in non-env file: $FILE_PATH" >&2
  echo "  Put secrets in .env / env vars only. Override: PROTO004_ACK=1 PROTO004_ACK_REASON='<why>'" >&2
  exit 2
fi

exit 0

#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Logged to .enforcement/routing-misses.log on every fire + override.
# Roll-up visible in holding/ANALYTICS-PULSE.md Sutra-Application-Rate panel (review-loop.sh).
#
# ### 2. Adoption mechanism
# Registered in .claude/settings.json hooks array (PreToolUse/PostToolUse).
# Holding-only today; propagate to companies via upgrade-clients.sh next plugin version.
#
# ### 3. Monitoring / escalation
# Founder reviews Application-Rate panel daily.
# HARD tier thresholds (tighter than SOFT baseline):
#   Warn:   override rate  >10% over 7d  → pattern review needed
#   Breach: override rate  >25% over 7d  → rewrite patterns (false-positive heavy)
#   Never:  demote to advisory — PROTO-004 is structurally HARD (matches dispatcher Check 5)
#
# ### 4. Iteration trigger
# False-positive count (overrides) or founder correction on a miss → revise patterns.
#
# ### 5. DRI
# Sutra-OS (Asawa-CEO). Operator: any session running in asawa-holding.
#
# ### 6. Decommission criteria
# Replaced by a higher-fidelity enforcer OR Sutra plugin absorbs this check.
