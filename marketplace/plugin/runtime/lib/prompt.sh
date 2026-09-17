#!/bin/sh
# prompt.sh - shared synthetic-prompt detection for the native steps
# (Sutra Runtime, adherence row 1). POSIX sh, sourced by bash 3.2 and sh alike.
#
# WHY. markers_write.sh (MVP-1) carried the six reset-turn-markers.sh guard
# patterns inline. Two prompt shapes were missing and produced a facts file
# plus a rewritten depth marker on 2026-09-16 (session 94a0f78e): the
# background task notification ("<task-notification>") and the harness's
# "[SYSTEM NOTIFICATION" preamble. Every native step that keys on the prompt
# now shares this one list, so the two cannot drift apart again.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/prompt.sh

# sutra_prompt_synthetic <prompt> -> 0 when the prompt is synthetic (a step
# must skip), 1 when it is a real founder prompt.
sutra_prompt_synthetic() {
  case "${1:-}" in
    "") return 0 ;;
    *"<system-reminder>"*|\
    *"PreToolUse:"*"hook additional context"*|\
    *"was modified, either by the user or by a linter"*|\
    *"READ-BEFORE-EDIT REMINDER"*|\
    *"task tools haven't been used recently"*|\
    *"<local-command-caveat>"*|\
    *"<task-notification>"*|\
    *"[SYSTEM NOTIFICATION"*)
      return 0 ;;
  esac
  return 1
}
