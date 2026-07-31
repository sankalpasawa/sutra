#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/codex-consult-marker.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-07-20
#
# codex-consult-marker.sh -- PostToolUse Bash writer that closes the loop for
# codex-consult-gate.sh (D63). When a REAL codex consult runs (the codex-sutra
# skill launches `codex exec` / `codex review` / `codex exec resume`), this
# hook writes .claude/codex-consulted with provenance, which satisfies the
# PreToolUse codex-consult-gate for the rest of the turn.
#
# This is the "cleanest writer" codex itself recommended (challenge finding c):
# the marker is written by the consult ACTION, not hand-forged. Per-turn: the
# marker is wiped by reset-turn-markers.sh on the next UserPromptSubmit, so each
# D3+ turn needs its own fresh consult.
#
# Match is specific (`codex <exec|review|resume>`), NOT bare "codex", so
# presence checks like `command -v codex` / `which codex` do NOT false-write.
#
# Non-blocking: exit 0 always (PostToolUse).

set -u
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -z "$REPO_ROOT" ] && exit 0

PAYLOAD=""
[ ! -t 0 ] && PAYLOAD="$(cat 2>/dev/null || true)"
CMD=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // empty' 2>/dev/null)
fi
[ -z "$CMD" ] && exit 0

# Real codex consult invocation? (specific subcommands, not bare "codex")
if printf '%s' "$CMD" | grep -qE 'codex[[:space:]]+(exec|review|resume)'; then
  SID="unknown"
  if command -v jq >/dev/null 2>&1 && [ -n "$PAYLOAD" ]; then
    SID=$(printf '%s' "$PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null)
  fi
  # Phase-2 marker-race fix (holding/research/2026-07-30-marker-race-root-cause.md
  # §6 phase 2): the marker previously landed ONLY at the legacy global
  # .claude/codex-consulted — SESSION= was stamped in the CONTENT but the PATH
  # was shared, so session A's consult satisfied session B's D3+ gate. Source
  # marker-lib defensively and write session-scoped (dual-write keeps the
  # legacy global twin for un-migrated readers). Fail-open on missing lib.
  MARKER_LIB="$(cd "$(dirname "$0")" && pwd)/marker-lib.sh"
  if [ -f "$MARKER_LIB" ]; then . "$MARKER_LIB" 2>/dev/null || true; fi
  command -v sutra_sid_from_stdin >/dev/null 2>&1 && sutra_sid_from_stdin "$PAYLOAD"
  BODY="$(printf 'CONSULT=codex-cli SESSION=%s TS=%s SOURCE=codex-consult-marker' \
    "$SID" "$(date +%s)")"
  if command -v sutra_marker_write >/dev/null 2>&1; then
    sutra_marker_write codex-consulted "$BODY" 2>/dev/null || true
  else
    mkdir -p "$REPO_ROOT/.claude" 2>/dev/null
    printf '%s\n' "$BODY" > "$REPO_ROOT/.claude/codex-consulted" 2>/dev/null
  fi
fi
exit 0
