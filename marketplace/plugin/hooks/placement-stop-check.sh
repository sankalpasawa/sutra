#!/bin/bash
# placement-stop-check.sh -- Stop-event floor for the PLACEMENT block (ADR-028)
#
# Canon:   sutra/os/decisions/ADR-028-mandatory-work-placement.md
# Event:   Stop
# Sibling: flow-stop-check.sh (same shape, same reason)
#
# WHY THIS EXISTS: placement-gate.sh is PreToolUse. A turn that answers a
# question and calls no tool never reaches it, so the per-turn requirement
# would have a hole exactly where governance is cheapest to skip. This closes
# it at Stop.
#
# (For the record: a peer review of this design asserted that no-tool-turn
# enforcement was impossible and that Claude Code has no hook able to block
# such a turn. That is wrong -- Stop hooks do precisely this, and
# flow-stop-check.sh + h-sutra-enforce.sh have been doing it in production.
# This file is the counter-example.)
#
# LADDER: shares .claude/placement-mode with placement-gate.sh.
#   warn (default) -> stderr notice, exit 0
#   hard           -> exit 2, forcing the response to be redone with the block
#
# Kill-switches: .claude/placement-disabled (repo) · ~/.placement-disabled
#                (machine) · PLACEMENT_DISABLED=1 (shell)
# Override:      PLACEMENT_ACK=1 PLACEMENT_ACK_REASON='<why>'

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

LEDGER="$REPO_ROOT/.enforcement/placement/gate-log.jsonl"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
_log() { mkdir -p "$(dirname "$LEDGER")" 2>/dev/null; printf '%s\n' "$1" >> "$LEDGER" 2>/dev/null; }

# -- Kill-switches -----------------------------------------------------------
[ -n "${PLACEMENT_DISABLED:-}" ] && exit 0
[ -f "$REPO_ROOT/.claude/placement-disabled" ] && exit 0
[ -f "$HOME/.placement-disabled" ] && exit 0
# File-based one-shot override (env ACKs never reach hook processes; the
# WORKING escape hatch is a file, consumed on use).
if [ -f "$REPO_ROOT/.claude/placement-ack" ]; then
  REASON=$(head -c 200 "$REPO_ROOT/.claude/placement-ack" 2>/dev/null | tr -d '\n\r' | tr '"' "'")
  command rm -f "$REPO_ROOT/.claude/placement-ack"
  _log "{\"ts\":\"$TS\",\"event\":\"placement-ack-file\",\"reason\":\"$REASON\"}"
  exit 0
fi
if [ "${PLACEMENT_ACK:-0}" = "1" ]; then
  REASON=$(printf '%s' "${PLACEMENT_ACK_REASON:-no-reason}" | tr -d '\n\r' | tr '"\\' "''" | head -c 500)
  _log "{\"ts\":\"$TS\",\"event\":\"placement-stop-override\",\"reason\":\"$REASON\"}"
  exit 0
fi

PAYLOAD=$(cat 2>/dev/null || true)
command -v jq >/dev/null 2>&1 || exit 0   # fail-open on infrastructure, never on discipline

# -- Loop guard: a Stop hook that blocks its own retry deadlocks the turn -----
# stop_hook_active is set by the harness when we are already inside a
# stop-hook-triggered continuation. Never block twice.
ACTIVE=$(printf '%s' "$PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
[ "$ACTIVE" = "true" ] && exit 0

# -- Marker check (Scheme A session-scoped via marker-lib) -------------------
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" || true
  sutra_sid_from_stdin "$PAYLOAD" || true
  set -u
fi
if command -v sutra_marker_has >/dev/null 2>&1; then
  sutra_marker_has placement-registered && exit 0
else
  [ -f "$REPO_ROOT/.claude/placement-registered" ] && exit 0
fi

# -- Mode --------------------------------------------------------------------
MODE_FILE="$REPO_ROOT/.claude/placement-mode"
MODE="warn"
[ -f "$MODE_FILE" ] && MODE=$(tr -d '[:space:]' < "$MODE_FILE" 2>/dev/null)
case "$MODE" in hard|warn) ;; *) MODE="warn" ;; esac

_log "{\"ts\":\"$TS\",\"event\":\"placement-stop-miss\",\"mode\":\"$MODE\",\"session\":\"${CLAUDE_SESSION_ID:-unknown}\"}"

if [ "$MODE" = "hard" ]; then
  {
    printf '\nPLACEMENT layer FIRED (ADR-028).\n\n'
    printf 'This turn carries no placement — the work has no address.\n'
    printf 'Emit the PLACEMENT block as literal text, then write\n'
    printf '.claude/placement-registered via the Write tool:\n\n'
    printf '  PLACEMENT: D0 > D3 <name> > D3.D2 <name> | "<charter title>"\n\n'
    printf 'Expand to the full ancestor tree ONLY if a Domain or Charter was minted.\n'
    printf 'Never block on a missing domain — mint under the deepest matching\n'
    printf 'ancestor and continue. The system decides the taxonomy, not the operator.\n\n'
    printf "If intentional (one-shot): echo reason > .claude/placement-ack\n"
    printf '(or PLACEMENT_DISABLED=1 / touch .claude/placement-disabled)\n\n'
  } >&2
  exit 2
fi

{
  printf '\nPLACEMENT (warn): this turn has no address. Emit the PLACEMENT block +\n'
  printf '  write .claude/placement-registered. Enforcement promotes to HARD once\n'
  printf '  this repo clears its compliance threshold.\n\n'
} >&2
exit 0
