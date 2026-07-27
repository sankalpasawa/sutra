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

# ── Session-scoped clear (2026-07-27) ──────────────────────────────────────
# These markers are per-repo single-slot files. When two Claude Code sessions
# work in the same repo, each session's reset wiped the OTHER session's live
# markers, and every downstream gate (depth, blueprint, build-layer, flow) then
# hard-blocked a session that had in fact emitted its blocks.
#
# Observed live 2026-07-27: session c2360700 logged markers-cleared while
# session e52b2379 was mid-edit; e52b2379's next Edit was blocked for "INPUT
# ROUTING MISSING" on a turn whose routing block had been emitted and written.
# An unknown share of the historical flow-gate-block / flow-stop-block volume
# is this race, not genuine misses — which is why the pass-logging added in the
# same release matters before anyone tunes on that data.
#
# Session-scoped markers (<name>-<SID>, written by per-turn-discipline-prompt.sh)
# are cleared ONLY for this session. Legacy single-slot markers are cleared
# only when unowned or owned by this session — a marker stamped SESSION=<other>
# belongs to a live peer and is left alone.
SID=$(printf '%s' "$STDIN_RAW" | jq -r '.session_id // empty' 2>/dev/null)
SID=$(printf '%s' "$SID" | tr -cd 'a-zA-Z0-9_-' | head -c 64)

LEGACY_MARKERS="input-routed depth-registered depth-assessed sutra-deploy-depth5
                build-layer-registered blueprint-registered structure-first-active
                flow-classified flow-inner flow-type-resolved flow-closed
                codex-consulted"

for m in $LEGACY_MARKERS; do
  f=".claude/$m"
  [ -f "$f" ] || continue
  OWNER=$(grep -o 'SESSION=[A-Za-z0-9_-]*' "$f" 2>/dev/null | head -1 | cut -d= -f2)
  if [ -z "$OWNER" ] || [ -z "$SID" ] || [ "$OWNER" = "$SID" ]; then
    rm -f "$f" 2>/dev/null
  else
    printf '{"ts":%s,"event":"reset-skipped-foreign-marker","marker":"%s","owner":"%s","self":"%s"}\n' \
      "$NOW" "$m" "$OWNER" "$SID" >> .enforcement/routing-misses.log 2>/dev/null
  fi
done

# Session-scoped copies: only ever this session's.
if [ -n "$SID" ]; then
  rm -f .claude/flow-classified-"$SID" \
        .claude/flow-type-resolved-"$SID" \
        .claude/flow-inner-"$SID" \
        .claude/flow-closed-"$SID" \
        2>/dev/null
fi

# Record this reset's timestamp so future bursts can be detected
mkdir -p .claude 2>/dev/null
echo "$NOW" > "$LAST_RESET_FILE" 2>/dev/null

printf '{"ts":%s,"event":"markers-cleared"}\n' "$NOW" >> .enforcement/routing-misses.log

exit 0
