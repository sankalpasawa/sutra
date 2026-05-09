#!/usr/bin/env bash
# structure-first-reminder.sh — D55 governance hook
#
# Direction: holding/FOUNDER-DIRECTIONS.md §D55 (Structure-First Default +
#            Restructure-on-Add). Founder utterance 2026-05-09: "Make sure
#            by default there is structuring applied everywhere whenever you
#            go about doing something. And then make sure that when we add
#            new things, you structure the existing things with the new
#            things and see if there are simplifications required. Make
#            this as a hard. This code which has to run on every command."
#
# Event: PreToolUse (no matcher) — fires on EVERY tool call
# Behavior: emit structure-first + restructure-on-add reminder to stderr ONCE
#           per founder turn. Subsequent tool calls in the same turn no-op
#           (dedupe via per-turn marker). The hook ITSELF runs on every call;
#           the REMINDER is once-per-turn to avoid context bloat.
# Logging: appends one JSONL row to holding/hooks/hook-log.jsonl when emitted.
# Fail-open: exit 0 always (never block a tool call). Soft guidance per
#            D40 codex caveat (hook-injects-prompt is advisory only).
#
# Kill-switches (any one disables):
#   ~/.sutra-defaults-disabled        — all D40 + D55 defaults
#   ~/.structure-first-disabled       — D55 only
#   STRUCTURE_FIRST_DISABLED=1        — env-var, single command
#   STRUCTURE_FIRST_ACK=1 STRUCTURE_FIRST_ACK_REASON='<why>' <cmd>
#                                     — per-call audit-logged override

set -u

# --- Kill-switches ---------------------------------------------------------
[ -f "$HOME/.sutra-defaults-disabled" ] && exit 0
[ -f "$HOME/.structure-first-disabled" ] && exit 0
[ -n "${STRUCTURE_FIRST_DISABLED:-}" ] && exit 0

# Per-call ACK override (audit-logged but reminder skipped)
if [ -n "${STRUCTURE_FIRST_ACK:-}" ]; then
  REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
  LOG="${REPO_ROOT}/holding/hooks/hook-log.jsonl"
  if [ -d "$(dirname "$LOG")" ]; then
    printf '{"ts":"%s","hook":"structure-first-reminder","action":"ack-override","reason":"%s","session":"%s"}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "${STRUCTURE_FIRST_ACK_REASON:-no-reason}" \
      "${CLAUDE_SESSION_ID:-unknown}" >> "$LOG" 2>/dev/null
  fi
  exit 0
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"

# --- Fresh-install gate ---------------------------------------------------
# Stay silent until /core:start has written .claude/sutra-project.json.
# Before that, reminder is non-actionable noise. Override: SUTRA_DISCIPLINE_PRE_ACTIVATION=1.
if [ -z "${SUTRA_DISCIPLINE_PRE_ACTIVATION:-}" ] && [ ! -f "$REPO_ROOT/.claude/sutra-project.json" ]; then
  exit 0
fi

# --- Per-turn dedupe -------------------------------------------------------
# reset-turn-markers.sh (Stop event) wipes .claude/structure-first-active.
# First tool call of a new turn finds no marker → emit + write marker.
# Subsequent tool calls find marker → silent no-op.
ACTIVE_MARKER="$REPO_ROOT/.claude/structure-first-active"
if [ -f "$ACTIVE_MARKER" ]; then
  grep -q '^EMITTED=true$' "$ACTIVE_MARKER" 2>/dev/null && exit 0
fi

# --- Emit reminder ---------------------------------------------------------
cat >&2 <<'REMINDER'
[D55 STRUCTURE-FIRST DEFAULT] structure is the default shape of every action.
  - Tables > prose for >=3 comparable rows.
  - Numbers > adjectives; progress bars for scores; ranges for estimates.
  - Decisions in ASCII-boxed callouts (no unicode box-drawing).
  - Impact + Effort columns on every task list.

[D55 RESTRUCTURE-ON-ADD] when adding ANYTHING new (file, section, direction,
protocol, hook, skill, dependency), four mandatory steps:
  1. Survey  — list existing structure the new thing touches.
  2. Reorg   — fit new + existing into one coherent shape.
  3. Simplify — dedupe, merge, delete redundancy. Apply ruthlessly.
  4. Surface — state in turn output: added / restructured / simplified / deleted.

Kill: touch ~/.structure-first-disabled
Full direction: holding/FOUNDER-DIRECTIONS.md §D55
REMINDER

# --- Write per-turn marker ------------------------------------------------
mkdir -p "$(dirname "$ACTIVE_MARKER")" 2>/dev/null
{
  echo "STRUCTURE_FIRST=ON"
  echo "TURN_TS=$(date +%s)"
  echo "EMITTED=true"
  echo "RESTRUCTURE_APPLIED=false"
} > "$ACTIVE_MARKER" 2>/dev/null

# --- Audit log -------------------------------------------------------------
LOG="${REPO_ROOT}/holding/hooks/hook-log.jsonl"
if [ -d "$(dirname "$LOG")" ]; then
  TOOL_NAME="${CLAUDE_TOOL_NAME:-unknown}"
  printf '{"ts":"%s","hook":"structure-first-reminder","action":"emitted","tool":"%s","session":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$TOOL_NAME" \
    "${CLAUDE_SESSION_ID:-unknown}" >> "$LOG" 2>/dev/null
fi

exit 0
