#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/h-sutra-enforce.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-05-12
#
# h-sutra-enforce.sh — Stop-event hook. Fires when assistant finishes a turn.
# Audits the last assistant message for H-Sutra header (FIRST text per CLAUDE.md).
# If missing: returns decision:block JSON, forcing model to redo response with header.
#
# Charter: sutra/os/charters/HUMAN-SUTRA-LAYER.md
# Spec:    sutra/marketplace/plugin/skills/human-sutra/SKILL.md §Header emission
# Source:  founder direction 2026-05-12 "I don't see human Sota getting fired"
#          — H-Sutra layer is the responsible party for header emission; logged
#          violations are not enforcement. This hook fires the H-Sutra layer.
#
# Header format (CLAUDE.md per_turn_blocks):
#   [<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]
# Stage-1 fail variant:
#   [STAGE-1-FAIL · CLARIFY · attempt:<n>/<m>]
#
# Kill-switches: SUTRA_HSUTRA_ENFORCE_DISABLED=1  OR  ~/.h-sutra-enforce-disabled

set -u

# Kill-switches
[ "${SUTRA_HSUTRA_ENFORCE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.h-sutra-enforce-disabled" ] && exit 0

# Avoid infinite loops: if stop_hook_active is true (we already blocked once
# this turn), let it through. Single-block-per-turn ceiling per Claude Code
# hook contract.
STDIN_PAYLOAD=""
if [ ! -t 0 ]; then
  STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
fi

if command -v jq >/dev/null 2>&1; then
  ACTIVE=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
  [ "$ACTIVE" = "true" ] && exit 0
fi

# Locate transcript
TRANSCRIPT_PATH=""
if [ -n "$STDIN_PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  TRANSCRIPT_PATH=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
fi
[ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ] && exit 0

# Find LAST assistant turn text in transcript (JSONL). Each row has role+content.
LAST_ASSISTANT_TEXT=$(tac "$TRANSCRIPT_PATH" 2>/dev/null | head -50 | \
  jq -r 'select(.type=="assistant" or .role=="assistant") | .message.content // .content // empty' 2>/dev/null | \
  head -1)

# Fallback: if tac unavailable on macOS, use awk
if [ -z "$LAST_ASSISTANT_TEXT" ]; then
  LAST_ASSISTANT_TEXT=$(awk -F '\n' '/"role":"assistant"|"type":"assistant"/{last=$0} END{print last}' "$TRANSCRIPT_PATH" 2>/dev/null | \
    jq -r '.message.content // .content // empty' 2>/dev/null | head -200)
fi

# Extract content text — handle nested .content[].text arrays
if command -v jq >/dev/null 2>&1; then
  EXTRACTED=$(printf '%s' "$LAST_ASSISTANT_TEXT" | jq -r 'if type=="array" then .[0].text // .[0] else . end' 2>/dev/null)
  [ -n "$EXTRACTED" ] && LAST_ASSISTANT_TEXT="$EXTRACTED"
fi

# H-Sutra header regex: opening bracket, [A-Z0-9-]+·[A-Z-]+ verb, optional " · " segments, closing bracket
# Plus Stage-1-fail variant
HSUTRA_PATTERN='^\[([A-Z0-9-]+·[A-Z0-9-]+( · (TIMING|CHANNEL|REV|RISK|TENSE|attempt):[^]·]+)*|STAGE-1-FAIL · CLARIFY( · attempt:[0-9]+/[0-9]+)?)\]'

if printf '%s' "$LAST_ASSISTANT_TEXT" | head -1 | grep -qE "$HSUTRA_PATTERN" 2>/dev/null; then
  # Header present — pass through
  exit 0
fi

# Header MISSING — fire the H-Sutra layer
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null || echo "unknown")
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
FIRST_LINE=$(printf '%s' "$LAST_ASSISTANT_TEXT" | head -c 200 | tr -d '\n' | sed 's/"/\\"/g')

# Log to violations ledger
printf '{"ts":"%s","session_id":"%s","violation":"h_sutra_header_missing","layer":"h-sutra","layer_fired":true,"first_line_observed":"%s","action":"stop_blocked_force_redo"}\n' \
  "$NOW" "$SESSION_ID" "$FIRST_LINE" \
  >> "$REPO_ROOT/.enforcement/governance-violations.jsonl" 2>/dev/null

# Block + force redo
cat <<JSON
{
  "decision": "block",
  "reason": "H-Sutra layer FIRED: header missing from your last response.\n\nPer CLAUDE.md §Mandatory Blocks, EVERY response must start with the H-Sutra header as the literal FIRST text:\n  [<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]\n\nOr Stage-1-fail variant:\n  [STAGE-1-FAIL · CLARIFY · attempt:1/1]\n\nFirst 200 chars of your last response: '$FIRST_LINE'\n\nRedo your response: emit the H-Sutra header literally as the first line, then continue with Input Routing + Depth blocks per CLAUDE.md."
}
JSON
exit 0
