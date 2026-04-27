#!/usr/bin/env bash
# UserPromptSubmit hook — clears per-turn routing/depth markers so each new
# founder prompt requires a fresh Input Routing block + Depth block.
# Root cause fix for 2026-04-15 miss: markers were session-scoped, not turn-scoped.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

# Synthetic-turn detection (2026-04-25 root-cause fix).
# Claude Code injects reminders (READ-BEFORE-EDIT, MEMORY.md linter, task-list
# prompts, PreToolUse hook context) as synthetic UserPromptSubmit turns. These
# MUST NOT wipe per-turn markers — only REAL founder input resets markers.
# Preserves original design intent of PROTO-governance and prevents the
# hook-interaction cascade that blocks multi-tool edits in sutra/** / holding/**.
PROMPT=$(jq -r '.prompt // empty' 2>/dev/null)
case "$PROMPT" in
  "")
    # Empty PROMPT = stdin had no .prompt field or jq failed → synthetic.
    # Root-cause fix 2026-04-25: was falling through to rm -f, caused 2052:1
    # wipe:skip ratio blocking multi-tool Sutra edits.
    mkdir -p .enforcement 2>/dev/null
    echo "{\"ts\":$(date +%s),\"event\":\"reset-skipped-empty-prompt\"}" >> .enforcement/routing-misses.log
    exit 0
    ;;
  *"<system-reminder>"*|\
  *"PreToolUse:"*"hook additional context"*|\
  *"was modified, either by the user or by a linter"*|\
  *"READ-BEFORE-EDIT REMINDER"*|\
  *"task tools haven't been used recently"*|\
  *"<local-command-caveat>"*)
    mkdir -p .enforcement 2>/dev/null
    echo "{\"ts\":$(date +%s),\"event\":\"reset-skipped-synthetic-turn\"}" >> .enforcement/routing-misses.log
    exit 0
    ;;
esac

rm -f .claude/input-routed \
      .claude/depth-registered \
      .claude/depth-assessed \
      .claude/sutra-deploy-depth5 \
      .claude/build-layer-registered \
      2>/dev/null

mkdir -p .enforcement 2>/dev/null
echo "{\"ts\":$(date +%s),\"event\":\"markers-cleared\"}" >> .enforcement/routing-misses.log

exit 0
