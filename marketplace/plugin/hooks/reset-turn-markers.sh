#!/usr/bin/env bash
# UserPromptSubmit — clears per-turn markers so each prompt requires fresh blocks.
#
# P1 (2026-07-27): clears THIS session's marker dir (marker-lib) AND, transitionally,
# the legacy repo-global list (until every writer moves to the session dir). Once
# fully migrated, drop the global block. TODO[p1-dropglobal].
#
# Clearing BOTH is what makes the transition safe: a global marker written by an
# un-migrated writer is still cleared on every real turn, so there is no permanent
# "marker present forever" pass while the migration is in flight.
#
# GUARD RESTORATION (2026-07-27): the P1 rewrite collapsed this file 90 -> 17 lines
# and dropped four guards that existed for measured reasons. Without them this hook
# fires on every SYNTHETIC UserPromptSubmit — Claude Code injects reminders
# (system-reminder blocks, READ-BEFORE-EDIT, linter notices, task-list nudges,
# PreToolUse hook context) as synthetic prompt events — wiping markers between an
# assistant's own tool calls and hard-blocking the next Edit/Write for "missing"
# markers that were in fact written. That regression hits SINGLE-session users too,
# not just concurrent ones. Restored below; do not remove without replacing the
# behavior they encode.
#   1. empty-prompt skip        (2026-04-25 root-cause fix)
#   2. synthetic-turn detection (2026-05-09 stdin instrumentation)
#   3. burst guard, 3s          (2026-05-12, Gap #17 of testlify-deployment-gaps)
#   4. forensics logging        (so the case patterns can be refined from data)
#
# Also fixed: the rewrite sourced marker-lib but never called sutra_sid_from_stdin,
# so _sutra_sid fell through to pid-$PPID and the reset could clear a directory
# belonging to no live session (or, worse, the wrong one).

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

STDIN_RAW="$(cat 2>/dev/null)"
PROMPT=$(printf '%s' "$STDIN_RAW" | jq -r '.prompt // empty' 2>/dev/null)

# -- Guard 1: empty prompt = not a real turn --------------------------------
case "$PROMPT" in
  "")
    mkdir -p .enforcement 2>/dev/null
    STDIN_BYTES=${#STDIN_RAW}
    STDIN_HEAD=$(printf '%s' "$STDIN_RAW" | head -c 200 | tr -d '\n' | sed 's/"/\\"/g')
    printf '{"ts":%s,"event":"reset-skipped-empty-prompt","stdin_bytes":%s,"stdin_head":"%s"}\n' \
      "$(date +%s)" "$STDIN_BYTES" "$STDIN_HEAD" >> .enforcement/routing-misses.log
    exit 0
    ;;
  # -- Guard 2: synthetic turns MUST NOT wipe markers ----------------------
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

# -- Guard 3: burst guard — real prompts arrive >> 3s apart ------------------
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

# -- Guard 4: forensics on every actual clear -------------------------------
STDIN_HEAD_CLR=$(printf '%s' "$STDIN_RAW" | head -c 300 | tr -d '\n' | sed 's/"/\\"/g')
mkdir -p .enforcement 2>/dev/null
printf '{"ts":%s,"event":"clearing-with-context","prompt_head":"%s"}\n' \
  "$NOW" "$STDIN_HEAD_CLR" >> .enforcement/routing-misses.log

# -- Session-scoped clear (authoritative) -----------------------------------
# Sourced defensively — see flow-gate.sh (DeepSeek consult 2026-07-27, finding 4).
LIB="$(dirname "$0")/marker-lib.sh"
SELF_SID=""
if [ -f "$LIB" ]; then
  set +u
  . "$LIB" || true
  sutra_sid_from_stdin "$STDIN_RAW" || true
  command -v sutra_marker_reset >/dev/null 2>&1 && sutra_marker_reset
  SELF_SID="${CLAUDE_CODE_SESSION_ID:-}"
  set -u
fi

# -- Legacy repo-global clear (transitional, OWNERSHIP-AWARE) ---------------
# TODO[p1-dropglobal]: delete once every writer uses sutra_marker_set / sutra-marker.
#
# A blanket `rm -f .claude/<marker>` here is session-agnostic and re-creates the
# original bug in a smaller form: session A's reset deletes session B's legacy
# global marker, and any of B's readers still on the global path then hard-block
# on a turn where B did emit its blocks (DeepSeek consult 2026-07-27, finding 2).
#
# So: only clear a legacy global that is UNOWNED (no SESSION= stamp — e.g. written
# by a model following an older CLAUDE.md govblock, where nobody else can be relying
# on it) or OWNED BY THIS SESSION. A marker stamped with a peer's session id is left
# alone; that peer's own reset will clear it.
for m in input-routed depth-registered depth-assessed sutra-deploy-depth5 \
         build-layer-registered blueprint-registered structure-first-active \
         flow-classified flow-inner flow-type-resolved flow-closed codex-consulted \
         placement-registered; do
  f=".claude/$m"
  [ -f "$f" ] || continue
  owner=$(grep -o 'SESSION=[A-Za-z0-9_-]*' "$f" 2>/dev/null | head -1 | cut -d= -f2)
  if [ -z "$owner" ] || [ -z "$SELF_SID" ] || [ "$owner" = "$SELF_SID" ]; then
    rm -f "$f" 2>/dev/null
  else
    printf '{"ts":%s,"event":"reset-skipped-foreign-global","marker":"%s","owner":"%s","self":"%s"}\n' \
      "$NOW" "$m" "$owner" "$SELF_SID" >> .enforcement/routing-misses.log 2>/dev/null
  fi
done

mkdir -p .claude 2>/dev/null
echo "$NOW" > "$LAST_RESET_FILE" 2>/dev/null

printf '{"ts":%s,"event":"markers-cleared","scope":"session+legacy"}\n' "$NOW" >> .enforcement/routing-misses.log
exit 0
