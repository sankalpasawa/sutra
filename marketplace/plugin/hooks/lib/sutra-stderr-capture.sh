#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/lib/sutra-stderr-capture.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-05-12
#
# sutra-stderr-capture.sh — SessionStart hook wrapper for stderr capture.
#
# WHY: Closes Gap #1 from holding/research/2026-05-12-testlify-sutra-deployment-gaps.md
# Claude Code reports "SessionStart:startup hook error · No stderr output" when
# any SessionStart hook exits non-zero. The downstream symptom was governance
# blocks not firing in Testlify T3 client. Per-hook stderr was lost.
#
# WHAT: Wraps a SessionStart hook to capture its stderr to a debug log without
# blocking session start. The hook's stdout flows to terminal unchanged (banners,
# privacy notices, inbox display still work). Stderr is appended to a single
# rolling log at $HOME/.sutra/hook-errors.log with start/end timestamps and exit
# code per hook. Wrapper always exits 0, so a failing inner hook does not bubble
# up to Claude Code as a SessionStart error.
#
# USAGE in hooks.json (SessionStart entries):
#   {
#     "type": "command",
#     "command": "${CLAUDE_PLUGIN_ROOT}/hooks/lib/sutra-stderr-capture.sh ${CLAUDE_PLUGIN_ROOT}/hooks/<NAME>.sh",
#     "timeout": <existing>
#   }
#
# DEBUG: tail -f ~/.sutra/hook-errors.log
#
# KILL-SWITCH: SUTRA_STDERR_CAPTURE_DISABLED=1 → bypass wrapper, run inner hook directly

set -u

# Pass-through mode (kill-switch)
if [ "${SUTRA_STDERR_CAPTURE_DISABLED:-0}" = "1" ]; then
  HOOK_PATH="${1:?usage: sutra-stderr-capture.sh <hook-path> [args...]}"
  shift
  exec "$HOOK_PATH" "$@"
fi

HOOK_PATH="${1:?usage: sutra-stderr-capture.sh <hook-path> [args...]}"
shift

LOG_DIR="$HOME/.sutra"
LOG="$LOG_DIR/hook-errors.log"
mkdir -p "$LOG_DIR" 2>/dev/null

HOOK_NAME="$(basename "$HOOK_PATH")"
TS_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Boundary marker (start) to log only
{
  printf '=== %s START %s pid=%s cwd=%s ===\n' "$TS_START" "$HOOK_NAME" "$$" "$(pwd)"
} >> "$LOG" 2>/dev/null

# Run inner hook; stderr -> log, stdout -> terminal
"$HOOK_PATH" "$@" 2>>"$LOG"
RC=$?

TS_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '=== %s END %s rc=%s ===\n' "$TS_END" "$HOOK_NAME" "$RC" >> "$LOG" 2>/dev/null

# Log size guard: trim to last 5000 lines if file > 1MB
if [ -f "$LOG" ]; then
  SIZE=$(wc -c < "$LOG" 2>/dev/null | tr -d ' ')
  if [ "${SIZE:-0}" -gt 1048576 ] 2>/dev/null; then
    tail -5000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
  fi
fi

# Always exit 0 so an inner hook failure does NOT block SessionStart
exit 0
