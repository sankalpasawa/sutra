#!/bin/bash
# sutra/marketplace/plugin/hooks/feedback-auto-correction.sh
# Sutra Privacy v2.0 — correction-signal auto-capture (UserPromptSubmit).
#
# Reads user prompt IN-MEMORY ONLY during this hook run.
# Pattern-matches common correction phrases, emits count signals.
# Prompt text is never stored, written to disk, or transmitted.
#
# Disclosed in PRIVACY.md §"What we capture" exception clause.
#
# Non-blocking: exits 0 on every path.
# Matches: UserPromptSubmit (all)

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LIB="$PLUGIN_ROOT/lib/privacy-sanitize.sh"
[ -f "$LIB" ] || exit 0
source "$LIB" 2>/dev/null || exit 0

PROMPT=$(jq -r '.prompt // empty' 2>/dev/null)
[ -z "$PROMPT" ] && exit 0

# Lowercase once — all subsequent matches are case-insensitive
LOWER=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]' | tr '\n' ' ')

# Dedup set (bash 3.2-compatible — no associative arrays)
SEEN=""
_count_if_unseen() {
  local sub="$1"
  case " $SEEN " in *" $sub "*) return 0 ;; esac
  SEEN="$SEEN $sub"
  signal_write correction "$sub" 1 2>/dev/null || true
}

# Pattern bank (word-boundary regex; simple correction signals)
printf '%s' "$LOWER" | grep -qE "(^| )no(,|\.| |!)" && _count_if_unseen no
printf '%s' "$LOWER" | grep -qE "(^| )stop(,|\.| |!)" && _count_if_unseen stop
printf '%s' "$LOWER" | grep -qE "don'?t " && _count_if_unseen dont
printf '%s' "$LOWER" | grep -qE "(^| )do not " && _count_if_unseen dont
printf '%s' "$LOWER" | grep -qE "(^| )actually(,| )" && _count_if_unseen actually
printf '%s' "$LOWER" | grep -qE "(^| )wrong(,|\.| |!)" && _count_if_unseen wrong
printf '%s' "$LOWER" | grep -qE "(^| )that'?s not " && _count_if_unseen thats-not
printf '%s' "$LOWER" | grep -qE "(^| )nope(,|\.| |!)" && _count_if_unseen nope

exit 0
