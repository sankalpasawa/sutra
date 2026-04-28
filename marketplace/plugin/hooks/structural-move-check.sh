#!/bin/bash
# structural-move-check.sh — PROTO-025 STRUCTURAL-MOVE Authorization gate
#
# Direction:    PROTO-025 (extends PROTO-021 to Bash structural ops)
# Trigger:      2026-04-06 unauthorized git mv of holding/evolution/ surfaced
#               2026-04-27. Restored in commit 87fb3ca. PROTO-021's hook
#               fires only on Edit|Write — Bash mv/rm slipped past every gate.
# Event:        PreToolUse on Bash
# Enforcement:  HARD (exit 2 blocks tool call when the command moves/deletes
#               a HARD-list path without marker or ACK override).
#
# HARD paths (single source of truth shared with build-layer-check.sh):
#   holding/hooks/**
#   holding/departments/**
#   holding/evolution/**           (added 2026-04-27)
#   holding/FOUNDER-DIRECTIONS.md  (added 2026-04-27)
#   sutra/marketplace/plugin/**
#   sutra/os/charters/**
#
# Whitelist (no fire — same as PROTO-021):
#   .claude/**, .enforcement/**, .analytics/**
#   holding/checkpoints/**, holding/TODO.md, holding/hooks/hook-log.jsonl
#   holding/research/** (research docs)
#   sutra/archive/** (archived artifacts)
#   *.lock, ~/.claude/projects/**/memory/**
#
# Detected commands:
#   mv, rm, rmdir, git mv, git rm
#   find ... -delete, find ... -exec rm/mv
#   xargs ... rm/mv
#   bash -c '...', sh -c '...', eval '...'  (heuristic: log+block on HARD)
#
# Marker:  .claude/build-layer-registered (shared with PROTO-021)
# Override: BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' <tool call>
# Ledger:  .enforcement/build-layer-ledger.jsonl
#          event=structural-block | structural-override | structural-allow-marker
#
# Spec:    sutra/layer2-operating-system/PROTOCOLS.md §PROTO-025
# Design:  holding/research/2026-04-27-structural-move-protocol-design.md

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LEDGER="$REPO_ROOT/.enforcement/build-layer-ledger.jsonl"
MARKER="$REPO_ROOT/.claude/build-layer-registered"

mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null

# ── Extract command from TOOL_INPUT_command env or stdin JSON ─────────────────
CMD="${TOOL_INPUT_command:-}"
if [ -z "$CMD" ] && [ ! -t 0 ]; then
  _JSON=$(cat 2>/dev/null)
  if [ -n "$_JSON" ]; then
    if command -v jq >/dev/null 2>&1; then
      CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
    else
      CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p' | head -1)
    fi
  fi
fi

# No command → not relevant
[ -z "$CMD" ] && exit 0

# ── Detect structural verbs (heuristic, fail-safe toward block on HARD) ──────
# Strip leading whitespace
_CMD_TRIM=$(printf '%s' "$CMD" | sed -E 's/^[[:space:]]+//')

# Patterns that indicate a structural move/delete somewhere in the command.
# We match anywhere in the string, not just first token, to catch:
#   - chained commands (cmd1 && rm ...)
#   - subshells ($(rm ...))
#   - bash -c 'rm ...'
# False-positive risk is acceptable since the response is "ask for ack" not "delete".
STRUCTURAL_PATTERN='(^|[[:space:];|&`(])((sudo[[:space:]]+)?(git[[:space:]]+(mv|rm)|mv|rm|rmdir)([[:space:]]|$))|find[[:space:]].*-(delete|exec[[:space:]]+(rm|mv))|xargs.*[[:space:]](rm|mv)([[:space:]]|$)|bash[[:space:]]+-c[[:space:]]|sh[[:space:]]+-c[[:space:]]|^[[:space:]]*eval[[:space:]]'

if ! printf '%s' "$_CMD_TRIM" | grep -qE "$STRUCTURAL_PATTERN"; then
  # Not a structural-move command. Pass through.
  exit 0
fi

# ── Identify if any HARD path is referenced in the command ────────────────────
# Substring match — conservative. We treat the whole command as a string and
# check for any HARD-list path pattern. Simple, robust to quoting weirdness.
HARD_PATTERNS=(
  'holding/hooks/'
  'holding/departments/'
  'holding/evolution/'
  'holding/FOUNDER-DIRECTIONS.md'
  'sutra/marketplace/plugin/'
  'sutra/os/charters/'
)

HARD_HIT=""
for pat in "${HARD_PATTERNS[@]}"; do
  case "$_CMD_TRIM" in
    *"$pat"*) HARD_HIT="$pat"; break ;;
  esac
done

# ── Whitelist check (paths that should never block even if "structural") ─────
# These match before HARD evaluation only when the ENTIRE command is whitelisted-
# scope. We only carve out specific exact matches — broad whitelists like
# `.claude/` are NOT under HARD anyway, so they pass via the no-HARD-hit path.
case "$_CMD_TRIM" in
  *"holding/research/"*|*"sutra/archive/"*|*"holding/checkpoints/"*|*"holding/hooks/hook-log.jsonl"*|*"holding/TODO.md"*|*".enforcement/"*|*".analytics/"*|*".claude/"*)
    # If command also touches a HARD path, HARD_HIT wins. Otherwise allow.
    if [ -z "$HARD_HIT" ]; then
      exit 0
    fi
    ;;
esac

# No HARD path involved → not relevant for this hook
[ -z "$HARD_HIT" ] && exit 0

# ── Sanitize for ledger ───────────────────────────────────────────────────────
_safe() { printf '%s' "$1" | tr -d '"\\' | tr '\n\r' '  ' | head -c 500; }
SAFE_CMD=$(_safe "$_CMD_TRIM")
SAFE_HIT=$(_safe "$HARD_HIT")
TS=$(date +%s)

# ── Override check ────────────────────────────────────────────────────────────
if [ "${BUILD_LAYER_ACK:-0}" = "1" ]; then
  REASON=$(_safe "${BUILD_LAYER_ACK_REASON:-no-reason-given}")
  echo "{\"ts\":$TS,\"event\":\"structural-override\",\"command\":\"$SAFE_CMD\",\"hard_path\":\"$SAFE_HIT\",\"reason\":\"$REASON\"}" >> "$LEDGER"
  echo "  [structural-move] override accepted (BUILD_LAYER_ACK=1): $REASON" >&2
  exit 0
fi

# ── Marker check ──────────────────────────────────────────────────────────────
if [ -f "$MARKER" ]; then
  MARKER_AGE=$(( TS - $(stat -f %m "$MARKER" 2>/dev/null || stat -c %Y "$MARKER" 2>/dev/null || echo $TS) ))
  echo "{\"ts\":$TS,\"event\":\"structural-allow-marker\",\"command\":\"$SAFE_CMD\",\"hard_path\":\"$SAFE_HIT\",\"marker_age_sec\":$MARKER_AGE}" >> "$LEDGER"
  exit 0
fi

# ── No marker, no override → BLOCK ────────────────────────────────────────────
echo "{\"ts\":$TS,\"event\":\"structural-block\",\"command\":\"$SAFE_CMD\",\"hard_path\":\"$SAFE_HIT\"}" >> "$LEDGER"

{
  echo ""
  echo "BLOCKED — structural move on HARD path requires authorization (PROTO-025)"
  echo ""
  echo "  Command:        $_CMD_TRIM"
  echo "  HARD path hit:  $HARD_HIT"
  echo ""
  echo "  This hook closes the gap that allowed the 2026-04-06 unauthorized"
  echo "  archive of holding/evolution/. PROTO-021 fires on Edit|Write only;"
  echo "  PROTO-025 extends the same authorization model to Bash mv/rm/etc."
  echo ""
  echo "  HARD paths protected:"
  echo "    holding/hooks/**"
  echo "    holding/departments/**"
  echo "    holding/evolution/**"
  echo "    holding/FOUNDER-DIRECTIONS.md"
  echo "    sutra/marketplace/plugin/**"
  echo "    sutra/os/charters/**"
  echo ""
  echo "  Authorization (any one):"
  echo "    1) Emit BUILD-LAYER block + write .claude/build-layer-registered"
  echo "       marker (same as PROTO-021 Edit/Write pattern)."
  echo "    2) One-off override:"
  echo "         BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' <cmd>"
  echo ""
  echo "  Logged to .enforcement/build-layer-ledger.jsonl."
  echo "  Spec:   sutra/layer2-operating-system/PROTOCOLS.md §PROTO-025"
  echo "  Design: holding/research/2026-04-27-structural-move-protocol-design.md"
  echo ""
} >&2

exit 2

# ═════════════════════════════════════════════════════════════════════════════
# ## Operationalization
#
# ### 1. Measurement mechanism
# .enforcement/build-layer-ledger.jsonl row count by event for this hook:
# structural-block / structural-override / structural-allow-marker per session.
# Metric: structural_block_rate. Target: blocks should trend to zero (declarations
# become habit) within 14 days. A non-zero block rate indicates the LLM is
# attempting unauthorized moves and being caught — that IS the protocol working.
#
# ### 2. Adoption mechanism
# Registered in .claude/settings.json under PreToolUse Bash matcher (alongside
# rtk-auto-rewrite.sh). Marker write pattern documented in CLAUDE.md §Build-Layer
# (same pattern, expanded trigger). Plugin promotion to
# sutra/marketplace/plugin/hooks/structural-move-check.sh by 2026-05-27 after
# 30-day clean operation.
#
# ### 3. Monitoring / escalation
# Asawa CEO reviews session-end summary weekly. Warn: any structural-block
# event in 7d → review whether ACK should be promoted to a documented direction.
# Breach: any structural-override without a follow-up commit citing the reason
# → audit retroactively against FOUNDER-DIRECTIONS.
#
# ### 4. Iteration trigger
# Add a HARD path when a new governance dir surfaces. Remove a HARD path only
# via explicit founder direction. Expand command-detection patterns when an
# evasion path is observed in real session traffic (currently covers literal
# mv/rm/git mv/git rm, find -delete, find -exec, xargs, bash -c, sh -c, eval).
#
# ### 5. DRI
# Asawa CEO (durable role). Same as PROTO-021.
#
# ### 6. Decommission criteria
# Retire when (a) replaced by plugin equivalent at
# sutra/marketplace/plugin/hooks/structural-move-check.sh and Asawa-holding
# instance loads from plugin path, or (b) a native Claude Code structural-move
# tool replaces Bash mv/rm and routes through Edit/Write hook chain.
# ═════════════════════════════════════════════════════════════════════════════
