#!/bin/bash
# Direction: D13 — Cascade Downstream Immediately
# Invariant:  I-15 — Cascade evidence on governance changes
# Event: PostToolUse on Edit|Write
# Enforcement: HARD (PostToolUse exit 2 — edit lands on disk but blocks
#              the assistant response until downstream TODO evidence exists
#              in the staged/unstaged diff, OR CASCADE_ACK=1 override is set).
# When L0-L2 files change, the agent MUST add a TODO line referencing the
# changed file's basename or stem to the affected companies' TODO.md files
# (or the holding TODO.md). Pattern: '+... TODO ... <stem>'.
# Override: CASCADE_ACK=1 CASCADE_ACK_REASON='<why>' <tool call>.
# Lifted SOFT→HARD on 2026-04-16 via the I-14 ladder.

FILE_PATH="$TOOL_INPUT_file_path"

# Claude Code stdin-JSON fallback (same P0 class — 2026-04-16).
if [ -z "$FILE_PATH" ] && [ ! -t 0 ]; then
  _JSON=$(cat)
  if [ -n "$_JSON" ]; then
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    else
      FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi
  fi
fi

# No file path → not relevant
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Resolve repo-relative bits for grep + logging
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
REL_PATH="${FILE_PATH#$REPO_ROOT/}"
BASE="$(basename "$FILE_PATH")"
STEM="${BASE%.*}"

# Escape regex metachars for safe injection into grep -E
# (addresses codex P2 — stems like 'a+b' or 'foo.bar' would break match)
_re_escape() {
  printf '%s' "$1" | sed 's/[][\\.*^$+?(){}|/-]/\\&/g'
}
ESC_STEM="$(_re_escape "$STEM")"
ESC_BASE="$(_re_escape "$BASE")"
ESC_REL_PATH="$(_re_escape "$REL_PATH")"

# Exempt routine backlog maintenance: editing TODO.md IS the cascade action.
# Without this carve-out, every `- [ ] foo` → `- [x] foo` flip triggers the
# hard gate and demands CASCADE_ACK (codex P1 2026-04-16).
case "$FILE_PATH" in
  */TODO.md|*/BACKLOG.md)
    exit 0
    ;;
esac

# Check if file is in holding/ or sutra/layer2-operating-system/
case "$FILE_PATH" in
  */holding/*|*/sutra/layer2-operating-system/*)
    echo "Warning: L0-L2 file changed: $FILE_PATH"
    echo "Per D13: List all downstream impacts and create TODOs for each company affected."
    echo "Check: dayflow, billu, maze, ppr, paisa — which are affected by this change?"

    # ── Explicit deferral override (mirror of I-14 DUPLICATION_OVERRIDE) ─────
    if [ "${CASCADE_ACK:-0}" = "1" ]; then
      _REASON_RAW="${CASCADE_ACK_REASON:-no-reason-given}"
      # B5 shared-writer: typed audit row + legacy mirror until v1.10 cutover.
      _OA_LIB="$REPO_ROOT/holding/hooks/lib/override-audit.sh"
      [ -f "$_OA_LIB" ] || _OA_LIB="$(dirname "$0")/lib/override-audit.sh"
      if [ -f "$_OA_LIB" ]; then
        # shellcheck disable=SC1090
        source "$_OA_LIB"
        _OA_MODE="legacy"
        [ -n "${CASCADE_ACK_TOKEN:-}" ] && _OA_MODE="strict"
        if accept_override "CASCADE_ACK" "D13" "cascade-check.sh" "$_REASON_RAW" 2 "$_OA_MODE" "$REL_PATH"; then
          REASON=$(printf '%s' "$_REASON_RAW" | tr -d '"\\' | tr '\n\r' '  ')
          if [ -n "$REPO_ROOT" ]; then
            mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
            echo "{\"ts\":$(date +%s),\"event\":\"cascade-override\",\"file\":\"$REL_PATH\",\"reason\":\"$REASON\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
          fi
          echo "  D13 override accepted (CASCADE_ACK): $REASON"
          exit 0
        fi
        # Helper rejected (bad reason or strict-mode token mismatch); fall through to block.
      else
        REASON=$(printf '%s' "$_REASON_RAW" | tr -d '"\\' | tr '\n\r' '  ')
        if [ -n "$REPO_ROOT" ]; then
          mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
          echo "{\"ts\":$(date +%s),\"event\":\"cascade-override\",\"file\":\"$REL_PATH\",\"reason\":\"$REASON\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
        fi
        echo "  D13 override accepted (CASCADE_ACK): $REASON"
        exit 0
      fi
    fi

    # ── Diff-evidence check: did the agent add a TODO referencing this file? ─
    # Restricted to actual TODO.md files via git pathspec so comments in other
    # files can't trivially satisfy the gate (codex P1). Looks for
    # +... TODO ... <stem|basename|relpath> across staged + unstaged diffs of
    # every TODO.md in the repo.
    if [ -n "$REPO_ROOT" ]; then
      DIFF_TEXT="$(
        cd "$REPO_ROOT" 2>/dev/null || exit 0
        git diff -- ':(glob)**/TODO.md' 'TODO.md' 2>/dev/null
        git diff --cached -- ':(glob)**/TODO.md' 'TODO.md' 2>/dev/null
      )"
      if printf '%s\n' "$DIFF_TEXT" | grep -v '^+++' | grep -Ei "^\+.*TODO.*(${ESC_STEM}|${ESC_BASE}|${ESC_REL_PATH})" >/dev/null 2>&1; then
        echo "  D13 evidence found: downstream TODO added referencing '${STEM}' in a TODO.md file."
        exit 0
      fi
    fi

    # ── No evidence, no override → hard block (exit 2) ──────────────────────
    echo ""
    echo "BLOCKED — D13 cascade gate (HARD)"
    echo "  File:   $REL_PATH"
    echo "  No downstream TODO evidence found in any TODO.md diff (staged or unstaged)."
    echo ""
    echo "  Required: add a line to holding/TODO.md and/or the affected"
    echo "  company TODO.md files matching: '+ ... TODO ... ${STEM}'"
    echo ""
    echo "  Override (intentional deferral):"
    echo "    CASCADE_ACK=1 CASCADE_ACK_REASON='<why>' <tool call>"
    echo ""
    if [ -n "$REPO_ROOT" ]; then
      mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
      _SAFE_REL_PATH=$(printf '%s' "$REL_PATH" | tr -d '"\\' | tr '\n\r' '  ')
      echo "{\"ts\":$(date +%s),\"event\":\"cascade-block\",\"file\":\"$_SAFE_REL_PATH\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
    fi
    exit 2
    ;;
esac

exit 0
