#!/bin/bash
# PROTO-005 — Self-Assess Before Foundational Work
# PreToolUse: when depth-registered is 4 or 5 AND target file is in a
# foundational path (sutra/, holding/, os/charters/, FOUNDER-DIRECTIONS),
# require a self-assess marker at .claude/self-assessed-<task-slug>.
# Advisory (never blocks); logs warnings.
#
# Override: PROTO005_ACK=1 <tool call>
# Kill-switch: touch ~/.proto005-disabled  OR  PROTO005_DISABLED=1

set -u

[ -e "$HOME/.proto005-disabled" ] || [ "${PROTO005_DISABLED:-}" = "1" ] && exit 0
[ "${PROTO005_ACK:-0}" = "1" ] && exit 0

# Receive event JSON from stdin
if [ -t 0 ]; then exit 0; fi
_JSON=$(cat 2>/dev/null || true)
[ -z "$_JSON" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
else
  FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[ -z "$FILE_PATH" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"

# --- B2 marker-race P4: session-first marker reads --------------------
# Root cause: holding/research/2026-07-30-marker-race-root-cause.md (Phase 4,
# self-assess-before-foundational.sh:31). Session dir first via marker-lib;
# foreign-stamped globals ignored. Advisory only -- NEVER blocks; legacy
# global path is the fallback when marker-lib is unavailable. Sourced
# defensively (set -u).
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" 2>/dev/null || true
  if command -v sutra_sid_from_stdin >/dev/null 2>&1; then
    sutra_sid_from_stdin "$_JSON" 2>/dev/null || true
  fi
  set -u
fi
_b2_marker_path() {
  if command -v sutra_marker_has >/dev/null 2>&1; then
    if sutra_marker_has "$1" 2>/dev/null; then sutra_marker_path "$1"; fi
    return 0
  fi
  [ -f "$REPO_ROOT/.claude/$1" ] && printf '%s' "$REPO_ROOT/.claude/$1"
  return 0
}

# Read depth marker
DEPTH_FILE="$(_b2_marker_path depth-registered)"
[ -f "$DEPTH_FILE" ] || exit 0
DEPTH=$(grep -oE 'DEPTH=[0-9]+' "$DEPTH_FILE" 2>/dev/null | head -1 | cut -d= -f2)
TASK=$(grep -oE 'TASK=[^[:space:]]+' "$DEPTH_FILE" 2>/dev/null | head -1 | cut -d= -f2)

# Only fire for Depth 4 or 5
case "$DEPTH" in
  4|5) ;;
  *) exit 0 ;;
esac

# Only fire for foundational paths
FOUNDATIONAL=0
case "$FILE_PATH" in
  *"/sutra/"*|*"/holding/"*|*"/os/charters/"*|*"FOUNDER-DIRECTIONS.md"|*"SYSTEM-MAP.md"|*"CLAUDE.md"|*"PROTOCOLS.md"|*"state/system.yaml"|*"PROJECT.md")
    FOUNDATIONAL=1 ;;
esac
[ "$FOUNDATIONAL" = "1" ] || exit 0

# Whitelist: markers, TODO.md, logs — session plumbing, not foundational edits
case "$FILE_PATH" in
  */TODO.md|*/BACKLOG.md|*/.claude/*|*/hook-log.jsonl|*/routing-misses.log|*.log|*.jsonl)
    exit 0 ;;
esac

# Check for self-assess marker matching the current task slug
# (session-first; the suggested dismissal write path is the session dir when
# marker-lib is available, else the legacy global)
SLUG="${TASK:-unknown}"
ASSESS_MARKER="$REPO_ROOT/.claude/self-assessed-$SLUG"
if command -v sutra_marker_path >/dev/null 2>&1; then
  ASSESS_MARKER="$(sutra_marker_path "self-assessed-$SLUG" 2>/dev/null || printf '%s' "$ASSESS_MARKER")"
fi

if [ -z "$(_b2_marker_path "self-assessed-$SLUG")" ]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  _SAFE=$(printf '%s' "$FILE_PATH" | tr -d '"\\' | tr '\n\r' '  ')
  echo "{\"ts\":$(date +%s),\"event\":\"proto005-warn\",\"file\":\"$_SAFE\",\"depth\":$DEPTH,\"task\":\"$SLUG\"}" >> "$REPO_ROOT/.enforcement/proto005-warnings.log"
  echo "  PROTO-005 Reminder: Depth-$DEPTH foundational edit without self-assess marker." >&2
  echo "  Consider: have you ratified this approach? (write $ASSESS_MARKER to dismiss)" >&2
  echo "  Override: PROTO005_ACK=1 <tool call>" >&2
fi

exit 0

#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Logged to .enforcement/proto005-warnings.log on every fire + override.
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
