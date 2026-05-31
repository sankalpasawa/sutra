#!/usr/bin/env bash
# capture-prompt.sh — UserPromptSubmit hook (PROMPT-CAPTURE)
#
# Promoted to L0 plugin on 2026-05-31 (was L1 staging at holding/hooks/).
# Appends every founder prompt to a monthly append-only JSONL at the project's
# holding/state/prompts/YYYY-MM.jsonl so the prompt trail is preserved beyond
# the session transcript. Per founder direction 2026-05-31: every Native PRD
# artifact must be traceable to its originating prompts.
#
# Schema (one row per prompt):  {"ts","session_id","prompt"}
#
# LOSSLESS + NON-BLOCKING: any failure exits 0; never blocks the prompt.
# Kill switches:  PROMPT_CAPTURE_DISABLED=1  OR  ~/.prompt-capture-disabled
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/capture-prompt.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a

set -u
[ "${PROMPT_CAPTURE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.prompt-capture-disabled" ] && exit 0

REPO="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
DIR="$REPO/holding/state/prompts"
MONTH="$(date -u +%Y-%m)"
FILE="$DIR/$MONTH.jsonl"

mkdir -p "$DIR" 2>/dev/null || exit 0

STDIN_PAYLOAD=""
[ ! -t 0 ] && STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
[ -z "$STDIN_PAYLOAD" ] && exit 0

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SID="unknown"
PROMPT=""

if command -v jq >/dev/null 2>&1; then
  SID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null || echo unknown)
  PROMPT=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.prompt // ""' 2>/dev/null || echo "")
fi

[ -z "$PROMPT" ] && exit 0

if command -v jq >/dev/null 2>&1; then
  ROW=$(jq -nc \
    --arg ts "$TS" \
    --arg sid "$SID" \
    --arg p "$PROMPT" \
    '{ts:$ts, session_id:$sid, prompt:$p}' 2>/dev/null) || exit 0
  [ -n "$ROW" ] && printf '%s\n' "$ROW" >> "$FILE" 2>/dev/null
fi

exit 0
