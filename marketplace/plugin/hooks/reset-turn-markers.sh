#!/usr/bin/env bash
# UserPromptSubmit hook — clears per-turn routing/depth markers so each new
# founder prompt requires a fresh Input Routing block + Depth block.
# Root cause fix for 2026-04-15 miss: markers were session-scoped, not turn-scoped.
#
# v3 (2026-05-12): Burst guard added (Gap #17 of testlify-deployment-gaps).
# Synthetic-turn detection in the case block below misses some Claude Code
# stdin payloads (real user prompt concatenated with system-reminder content).
# When that happens, reset fires multiple times per real turn — wiping markers
# between same-turn assistant tool calls and forcing every Edit/Write to hit
# a missing-marker hook failure. The burst guard caps marker-clear frequency:
# if last reset was < 3s ago, treat as synthetic same-turn and skip.

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

# Synthetic-turn detection (2026-04-25 root-cause fix; 2026-05-09 stdin instr).
# Claude Code injects reminders (READ-BEFORE-EDIT, MEMORY.md linter, task-list
# prompts, PreToolUse hook context) as synthetic UserPromptSubmit turns. These
# MUST NOT wipe per-turn markers — only REAL founder input resets markers.
STDIN_RAW="$(cat 2>/dev/null)"
PROMPT=$(printf '%s' "$STDIN_RAW" | jq -r '.prompt // empty' 2>/dev/null)
case "$PROMPT" in
  "")
    mkdir -p .enforcement 2>/dev/null
    STDIN_BYTES=${#STDIN_RAW}
    STDIN_HEAD=$(printf '%s' "$STDIN_RAW" | head -c 200 | tr -d '\n' | sed 's/"/\\"/g')
    printf '{"ts":%s,"event":"reset-skipped-empty-prompt","stdin_bytes":%s,"stdin_head":"%s"}\n' \
      "$(date +%s)" "$STDIN_BYTES" "$STDIN_HEAD" >> .enforcement/routing-misses.log
    exit 0
    ;;
  *"<system-reminder>"*|\
  *"PreToolUse:"*"hook additional context"*|\
  *"was modified, either by the user or by a linter"*|\
  *"READ-BEFORE-EDIT REMINDER"*|\
  *"task tools haven't been used recently"*|\
  *"<local-command-caveat>"*)
    mkdir -p .enforcement 2>/dev/null
    printf '{"ts":%s,"event":"reset-skipped-synthetic-turn"}\n' "$(date +%s)" >> .enforcement/routing-misses.log
    exit 0
    ;;
esac

# Burst guard (Gap #17 fix 2026-05-12) — if last reset < 3s ago, skip wipe.
# Real user prompts arrive >> 3s apart (typing + send time). Same-turn
# synthetic events arrive sub-second to a few seconds apart.
NOW=$(date +%s)
LAST_RESET_FILE=".claude/.last-reset-ts"
if [ -f "$LAST_RESET_FILE" ]; then
  LAST=$(cat "$LAST_RESET_FILE" 2>/dev/null)
  if [ -n "$LAST" ] && [ "$LAST" -gt 0 ] 2>/dev/null; then
    DELTA=$(( NOW - LAST ))
    if [ "$DELTA" -ge 0 ] && [ "$DELTA" -lt 3 ] 2>/dev/null; then
      mkdir -p .enforcement 2>/dev/null
      STDIN_HEAD_BG=$(printf '%s' "$STDIN_RAW" | head -c 200 | tr -d '\n' | sed 's/"/\\"/g')
      printf '{"ts":%s,"event":"reset-skipped-burst-guard","last_reset_ago_s":%s,"prompt_head":"%s"}\n' \
        "$NOW" "$DELTA" "$STDIN_HEAD_BG" >> .enforcement/routing-misses.log
      exit 0
    fi
  fi
fi

# Forensics: log stdin context on every actual clear so the case patterns
# above can be refined from data when the burst guard catches false-positives.
STDIN_HEAD_CLR=$(printf '%s' "$STDIN_RAW" | head -c 300 | tr -d '\n' | sed 's/"/\\"/g')
mkdir -p .enforcement 2>/dev/null
printf '{"ts":%s,"event":"clearing-with-context","prompt_head":"%s"}\n' \
  "$NOW" "$STDIN_HEAD_CLR" >> .enforcement/routing-misses.log

rm -f .claude/input-routed \
      .claude/depth-registered \
      .claude/depth-assessed \
      .claude/sutra-deploy-depth5 \
      .claude/build-layer-registered \
      .claude/blueprint-registered \
      .claude/structure-first-active \
      .claude/flow-classified \
      .claude/flow-inner \
      .claude/flow-type-resolved \
      .claude/flow-closed \
      2>/dev/null

# Record this reset's timestamp so future bursts can be detected
mkdir -p .claude 2>/dev/null
echo "$NOW" > "$LAST_RESET_FILE" 2>/dev/null

printf '{"ts":%s,"event":"markers-cleared"}\n' "$NOW" >> .enforcement/routing-misses.log

exit 0
