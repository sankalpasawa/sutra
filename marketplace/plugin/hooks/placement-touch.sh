#!/bin/bash
# placement-touch.sh — on-touch minting + post-close correction (ADR-028).
# PostToolUse Edit|Write: the touched file gets a DURABLE placement (backfill/
# mint on first touch; post-close supersede when evidence has moved). This is
# what populates the tree on fresh machines — no manual scan required.
# Fail-open always: population is a benefit, never a blocker.
set -u
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0
[ -f "$REPO_ROOT/.claude/placement-disabled" ] && exit 0
[ -f "$HOME/.placement-disabled" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
PAYLOAD=$(cat 2>/dev/null || true)
FILE=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0
case "$FILE" in
  */.claude/*|*/.enforcement/*|*/.analytics/*|*.lock|*/node_modules/*|*/.git/*) exit 0 ;;
esac
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
mkdir -p "$REPO_ROOT/.enforcement/placement" 2>/dev/null
( cd "$REPO_ROOT" && python3 "$PLUGIN_DIR/lib/placement_engine.py" touch "$FILE" \
    >> "$REPO_ROOT/.enforcement/placement/touch-log.jsonl" \
    2>> "$REPO_ROOT/.enforcement/placement/touch-errors.log" ) || true
exit 0
