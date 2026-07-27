#!/usr/bin/env bash
# UserPromptSubmit — clears per-turn markers so each prompt requires fresh blocks.
# P1 (2026-07-27): clears THIS session's marker dir (marker-lib) AND, transitionally,
# the legacy repo-global list (until every writer moves to the session dir). Once
# fully migrated, drop the global block. TODO[p1-dropglobal].
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0
LIB="$(dirname "$0")/marker-lib.sh"; [ -f "$LIB" ] && . "$LIB"
command -v sutra_marker_reset >/dev/null 2>&1 && sutra_marker_reset
rm -f .claude/input-routed .claude/depth-registered .claude/depth-assessed \
      .claude/sutra-deploy-depth5 .claude/build-layer-registered \
      .claude/blueprint-registered .claude/structure-first-active \
      .claude/flow-classified .claude/flow-inner .claude/flow-type-resolved \
      .claude/flow-closed .claude/codex-consulted 2>/dev/null
mkdir -p .enforcement 2>/dev/null
echo "{\"ts\":$(date +%s),\"event\":\"markers-cleared\",\"scope\":\"session+legacy\"}" >> .enforcement/routing-misses.log
exit 0
