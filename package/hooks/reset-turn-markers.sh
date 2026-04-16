#!/usr/bin/env bash
# UserPromptSubmit hook — clears per-turn routing/depth markers so each new
# founder prompt requires a fresh Input Routing block + Depth block.
# Root cause fix for 2026-04-15 miss: markers were session-scoped, not turn-scoped.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
cd "$REPO_ROOT" || exit 0

rm -f .claude/input-routed \
      .claude/depth-registered \
      .claude/depth-assessed \
      .claude/sutra-deploy-depth5 \
      2>/dev/null

mkdir -p .enforcement 2>/dev/null
echo "{\"ts\":$(date +%s),\"event\":\"markers-cleared\"}" >> .enforcement/routing-misses.log

exit 0
