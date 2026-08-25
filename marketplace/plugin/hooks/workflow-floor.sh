#!/usr/bin/env bash
# workflow-floor.sh — Stop ADVISORY (G5, W4 parity 2026-08-25). DEFAULT OFF.
# Enable: touch ~/.sutra/workflow-floor-enabled
# Heuristic: this turn had >=6 Edit/Write tool calls across >=4 distinct files
# and no Agent/Task/Workflow dispatch -> one stderr advisory (never blocks).
# A hook cannot force a Skill/Workflow (D61); it CAN make the miss visible.
set -uo pipefail
[ -f "$HOME/.sutra/workflow-floor-enabled" ] || exit 0
INPUT=$(cat 2>/dev/null || true)
TR=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -f "$TR" ] || exit 0
STATS=$(tail -400 "$TR" 2>/dev/null | jq -rs '
  [ .[] | select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") ] as $t
  | {
      edits: ([ $t[] | select(.name=="Edit" or .name=="Write") ] | length),
      files: ([ $t[] | select(.name=="Edit" or .name=="Write") | .input.file_path ] | unique | length),
      fanout: ([ $t[] | select(.name=="Agent" or .name=="Task" or .name=="Workflow") ] | length)
    } | "\(.edits) \(.files) \(.fanout)"' 2>/dev/null) || exit 0
set -- $STATS
EDITS="${1:-0}"; FILES="${2:-0}"; FAN="${3:-0}"
if [ "$EDITS" -ge 6 ] && [ "$FILES" -ge 4 ] && [ "$FAN" -eq 0 ]; then
  echo "workflow-floor (advisory): $EDITS Edit/Write across $FILES files with no Agent/Workflow dispatch — consider fanning multi-file units out (core:flow deep mode / Workflow)." >&2
fi
exit 0
