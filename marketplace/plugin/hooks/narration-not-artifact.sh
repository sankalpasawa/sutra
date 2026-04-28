#!/bin/bash
# PROTO-009 — Narration Is Not Artifact
# PostToolUse on Write: lint .md files in spec/plan/review/design paths
# to catch prose-only bodies (no structured sections — no headers,
# no tables, no lists). Advisory (never blocks); logs warnings.
#
# Override: PROTO009_ACK=1 <tool call>
# Kill-switch: touch ~/.proto009-disabled  OR  PROTO009_DISABLED=1

set -u

[ -e "$HOME/.proto009-disabled" ] || [ "${PROTO009_DISABLED:-}" = "1" ] && exit 0
[ "${PROTO009_ACK:-0}" = "1" ] && exit 0

# Receive Claude Code event JSON from stdin
if [ -t 0 ]; then exit 0; fi
_JSON=$(cat 2>/dev/null || true)
[ -z "$_JSON" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
else
  FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[ -z "$FILE_PATH" ] && exit 0

# Only lint .md files
case "$FILE_PATH" in
  *.md) ;;
  *) exit 0 ;;
esac

# Only lint in paths where artifact-shape matters
case "$FILE_PATH" in
  *spec*|*SPEC*|*plan*|*PLAN*|*review*|*REVIEW*|*design*|*DESIGN*|*architecture*|*ARCHITECTURE*|*proposal*|*PROPOSAL*|*rfc*|*RFC*) ;;
  *) exit 0 ;;
esac

# Skip the file being linted doesn't exist yet (first-Write edge case)
[ -f "$FILE_PATH" ] || exit 0

BODY=$(cat "$FILE_PATH" 2>/dev/null)
[ -z "$BODY" ] && exit 0

# Word count (prose volume)
WORDS=$(printf '%s' "$BODY" | wc -w | tr -d ' ')
# Skip tiny files — they can be pointer-only prose
[ "$WORDS" -lt 150 ] && exit 0

# Count structure markers
HEADERS=$(printf '%s\n' "$BODY" | grep -cE '^#+[[:space:]]' || true)
TABLES=$(printf '%s\n' "$BODY" | grep -cE '^\|.*\|' || true)
LISTS=$(printf '%s\n' "$BODY" | grep -cE '^[[:space:]]*[-*][[:space:]]|^[[:space:]]*[0-9]+\.[[:space:]]' || true)
CODEFENCE=$(printf '%s\n' "$BODY" | grep -cE '^```' || true)

# "Structured" = at least one: >=2 headers OR any table OR >=3 list items
STRUCT_SCORE=$((HEADERS + TABLES * 3 + (LISTS >= 3 ? 1 : 0) + (CODEFENCE / 2)))

if [ "$HEADERS" -lt 2 ] && [ "$TABLES" -eq 0 ] && [ "$LISTS" -lt 3 ]; then
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  _SAFE=$(printf '%s' "$FILE_PATH" | tr -d '"\\' | tr '\n\r' '  ')
  echo "{\"ts\":$(date +%s),\"event\":\"proto009-warn\",\"file\":\"$_SAFE\",\"words\":$WORDS,\"headers\":$HEADERS,\"tables\":$TABLES,\"lists\":$LISTS}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
  echo "  PROTO-009 Warning: spec/plan/review-shaped file is prose-only (${WORDS}w, ${HEADERS} headers, ${TABLES} tables, ${LISTS} list lines): $FILE_PATH" >&2
  echo "  Add structure: sections (##), a table, or numbered steps. Override: PROTO009_ACK=1" >&2
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
# Founder reviews Application-Rate panel daily. Warn: override rate >30% over 7d.
# Breach: override rate >60% over 7d → rewrite rule or demote to advisory-only.
#
# ### 4. Iteration trigger
# False-positive count (overrides) or founder correction on a miss → revise patterns.
#
# ### 5. DRI
# Sutra-OS (Asawa-CEO). Operator: any session running in asawa-holding.
#
# ### 6. Decommission criteria
# Replaced by a higher-fidelity enforcer OR Sutra plugin absorbs this check.
