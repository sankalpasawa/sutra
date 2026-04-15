#!/usr/bin/env bash
# Sutra OS — UserPromptSubmit hook (portable bundle, v1.9)
# Clears per-turn routing/depth markers so each new founder prompt requires
# a fresh Input Routing block + Depth block.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$REPO_ROOT" || exit 0

rm -f .claude/input-routed \
      .claude/depth-registered \
      .claude/depth-assessed \
      .claude/sutra-deploy-depth5 \
      2>/dev/null

mkdir -p .enforcement 2>/dev/null
echo "{\"ts\":$(date +%s),\"event\":\"markers-cleared\"}" >> .enforcement/routing-misses.log

exit 0
