#!/usr/bin/env bash
# Sutra — MCP Governance Gate  (PreToolUse · matcher: mcp__claude_ai)
#
# Fires on every claude.ai MCP tool invocation. Delegates to
# connectors/mcp-governance/policy-check.mjs which:
#   1. Finds the matching connector manifest via mcp_tool_map
#   2. Checks tier access (T1–T4) against manifest tierAccess
#   3. Checks depth floor against manifest capability minDepth
#   4. Writes an audit row to .enforcement/connector-audit.jsonl
#   5. Exits 0 (allow) or 2 (block with reason)
#
# Fail-open: if the policy checker is missing or crashes, the tool call
# proceeds. Governance should never break the session — it should block
# specific violations and log everything else.
#
# Build-layer: L0 fleet (PLUGIN-RUNTIME path: sutra/marketplace/plugin/hooks/)

set -u

# ── Read tool name from stdin JSON ────────────────────────────────────────────

INPUT=$(cat)
TOOL_NAME=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_name', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

# Only govern claude.ai MCP tools — pass everything else through.
case "$TOOL_NAME" in
  mcp__claude_ai_*) ;;
  *) exit 0 ;;
esac

# ── Locate policy checker ─────────────────────────────────────────────────────

POLICY_CHECK="${CLAUDE_PLUGIN_ROOT}/connectors/mcp-governance/policy-check.mjs"

if [ ! -f "$POLICY_CHECK" ]; then
  # Missing policy checker: fail-open, warn loudly.
  printf '[sutra-mcp] WARNING: policy checker not found at %s (fail-open)\n' \
    "$POLICY_CHECK" >&2
  exit 0
fi

# ── Run policy check ──────────────────────────────────────────────────────────

exec node "$POLICY_CHECK" \
  --tool "$TOOL_NAME" \
  --manifests-dir "${CLAUDE_PLUGIN_ROOT}/connectors/manifests"
