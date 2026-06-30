#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/loopguard-turn-reset.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-06-30
#
# loopguard-turn-reset.sh — UserPromptSubmit hook.
#
# WHY: loop-budget-guard.sh counts tool calls in an append-only per-SESSION file
# (~/.sutra/sessions/<sid>.loopguard) that NEVER resets. A genuine runaway is a
# WITHIN-ONE-TURN event, but the cumulative count means a long, legitimate,
# call-heavy session (e.g. a multi-agent workflow, or a 2-hour working session)
# eventually crosses SUTRA_TOOL_BUDGET (250) and hard-stops itself — observed:
# a 253-call session where 246 calls were ordinary Bash/Read/Write.
#
# This hook truncates that counter at the start of each REAL user turn, making
# the budget PER-TURN: a runaway that fires 250 calls in ONE turn is still
# blocked; a productive multi-turn session never is. The repeat detector (8
# identical in 16) still catches loops within a turn regardless.
#
# Synthetic UserPromptSubmit turns (system-reminders, injected hook context,
# linter notices) are SKIPPED — resetting on those would wipe the counter
# mid-turn and weaken within-turn loop detection. Mirrors reset-turn-markers.sh.
#
# Fail-open: no stdin / no jq / no session_id -> exit 0 (never break a session).
# Kill (shares the guard's switches — if the guard is off, resetting is moot):
#   LOOP_BUDGET_GUARD_DISABLED=1 | SUTRA_BYPASS=1 | ~/.loop-budget-guard-disabled

set -u

[ "${SUTRA_BYPASS:-}" = "1" ] && exit 0
[ "${LOOP_BUDGET_GUARD_DISABLED:-}" = "1" ] && exit 0
[ -e "$HOME/.loop-budget-guard-disabled" ] && exit 0

[ -t 0 ] && exit 0
JSON=$(cat 2>/dev/null || true)
[ -z "$JSON" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

PROMPT=$(printf '%s' "$JSON" | jq -r '.prompt // empty' 2>/dev/null)
SID=$(printf '%s' "$JSON" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0

# Only REAL user prompts reset the per-turn counter (mirror reset-turn-markers.sh).
case "$PROMPT" in
  "") exit 0 ;;
  *"<system-reminder>"*|\
  *"PreToolUse:"*"hook additional context"*|\
  *"was modified, either by the user or by a linter"*|\
  *"READ-BEFORE-EDIT REMINDER"*|\
  *"task tools haven't been used recently"*|\
  *"<local-command-caveat>"*)
    exit 0 ;;
esac

STATE_DIR="${LOOP_GUARD_STATE_DIR:-${SUTRA_HOME:-$HOME/.sutra}/sessions}"
SID_SAFE=$(printf '%s' "$SID" | tr -c 'A-Za-z0-9._-' '_')
F="$STATE_DIR/${SID_SAFE}.loopguard"

# Truncate to zero (start the turn's count fresh). Keep the file so the guard's
# `>>` append continues to work. Best-effort — never fail the turn.
[ -f "$F" ] && : > "$F" 2>/dev/null || true
exit 0
