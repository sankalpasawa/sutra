#!/bin/bash
# PROTO-001 + I-14: Structure Before Creation + No-duplication gate
# Event: PreToolUse on Write (new file creation)
# Enforcement: HARD on basename-match (duplicate detection), SOFT on path-map
#
# When creating a new file:
#   (a) HARD-block if a file with the same basename already exists elsewhere
#       (I-14 strict — override via DUPLICATION_OVERRIDE=1 env or commit trailer)
#   (b) SOFT-warn if its directory isn't in SYSTEM-MAP.md (original PROTO-001)
#
# 2026-04-16: extended with basename-grep to close the duplicacy gap that
# caused today's evolution-cycle.sh + verify-company-deploy.sh dupes.

FILE_PATH="$TOOL_INPUT_file_path"

# Claude Code stdin-JSON fallback (Write hook format)
TOOL_NAME="${TOOL_NAME:-}"
if [ -z "$FILE_PATH" ] && [ ! -t 0 ]; then
  _J=$(cat)
  if [ -n "$_J" ]; then
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$_J" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
      [ -z "$TOOL_NAME" ] && TOOL_NAME=$(printf '%s' "$_J" | jq -r '.tool_name // empty' 2>/dev/null)
    else
      FILE_PATH=$(printf '%s' "$_J" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
      [ -z "$TOOL_NAME" ] && TOOL_NAME=$(printf '%s' "$_J" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi
  fi
fi

# No file path → not relevant
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Only fire on new file creation (file doesn't exist yet)
if [ -f "$FILE_PATH" ]; then
  exit 0
fi

REPO_ROOT=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}

# ── I-14 HARD basename-duplication gate ─────────────────────────────────────
# Block creation if a file with the same basename already exists elsewhere in
# the repo. Override: DUPLICATION_OVERRIDE=1 with DUPLICATION_OVERRIDE_REASON,
# or add `Duplication-Override: <reason>` trailer in the next commit message.
BASE=$(basename "$FILE_PATH")

# Skip basenames that are legitimately non-unique (one per dir by design)
case "$BASE" in
  README.md|CLAUDE.md|TODO.md|STATUS.md|METRICS.md|OKRs.md|DECISIONS.md|\
  SUTRA-CONFIG.md|SUTRA-VERSION.md|MANIFEST.md|PROTOCOLS.md|\
  package.json|.gitignore|index.md|index.ts|index.js|config.json|settings.json)
    ;;  # fall through to path-map warn only
  *)
    if [ -n "$REPO_ROOT" ] && [ "${DUPLICATION_OVERRIDE:-0}" != "1" ]; then
      MATCHES=$(cd "$REPO_ROOT" && find . \
        -path './.git' -prune -o \
        -path './node_modules' -prune -o \
        -path '*/archive/*' -prune -o \
        -path '*/archived*' -prune -o \
        -type f -name "$BASE" -print 2>/dev/null | head -10)
      if [ -n "$MATCHES" ]; then
        echo ""
        echo "BLOCKED — I-14 no-duplication gate (HARD)"
        echo "  Proposed new file: ${FILE_PATH#$REPO_ROOT/}"
        echo "  Existing files with the same basename:"
        echo "$MATCHES" | sed 's|^|    |'
        echo ""
        echo "  Options:"
        echo "    1. Extend one of the existing files instead of creating a new one."
        echo "    2. If this is genuinely novel, retry with override:"
        echo "       DUPLICATION_OVERRIDE=1 DUPLICATION_OVERRIDE_REASON='<why>' <tool call>"
        echo ""
        mkdir -p "$REPO_ROOT/.enforcement"
        echo "{\"ts\":$(date +%s),\"event\":\"block\",\"file\":\"$FILE_PATH\",\"matches\":$(echo "$MATCHES" | wc -l | tr -d ' ')}" >> "$REPO_ROOT/.enforcement/duplication-log.jsonl"
        exit 1
      fi
    elif [ "${DUPLICATION_OVERRIDE:-0}" = "1" ]; then
      REASON="${DUPLICATION_OVERRIDE_REASON:-no-reason-given}"
      # B5 shared-writer: typed audit row + legacy mirror until v1.10 cutover.
      _OA_LIB="$REPO_ROOT/holding/hooks/lib/override-audit.sh"
      [ -f "$_OA_LIB" ] || _OA_LIB="$(dirname "$0")/lib/override-audit.sh"
      if [ -f "$_OA_LIB" ]; then
        # shellcheck disable=SC1090
        source "$_OA_LIB"
        _OA_MODE="legacy"
        [ -n "${DUPLICATION_OVERRIDE_TOKEN:-}" ] && _OA_MODE="strict"
        if accept_override "DUPLICATION_OVERRIDE" "I-14" "new-path-detector.sh" "$REASON" 2 "$_OA_MODE" "$FILE_PATH"; then
          mkdir -p "$REPO_ROOT/.enforcement"
          # Legacy mirror: hand-built JSON kept for back-compat readers; reason is
          # already validated by accept_override (no CR/LF), but still escape quotes
          # defensively for the mirror sink.
          REASON_M=$(printf '%s' "$REASON" | tr -d '"' )
          echo "{\"ts\":$(date +%s),\"event\":\"override\",\"file\":\"$FILE_PATH\",\"reason\":\"$REASON_M\"}" >> "$REPO_ROOT/.enforcement/duplication-log.jsonl"
          echo "I-14 override accepted: $REASON"
        else
          # Helper rejected (bad reason or strict-mode token mismatch); re-block.
          echo "BLOCKED -- I-14 override REJECTED by audit helper (reason malformed or token invalid)."
          exit 1
        fi
      else
        mkdir -p "$REPO_ROOT/.enforcement"
        echo "{\"ts\":$(date +%s),\"event\":\"override\",\"file\":\"$FILE_PATH\",\"reason\":\"$REASON\"}" >> "$REPO_ROOT/.enforcement/duplication-log.jsonl"
        echo "I-14 override accepted: $REASON"
      fi
    fi
    ;;
esac

# Get the directory of the new file
DIR_PATH=$(dirname "$FILE_PATH")

# Get the directory name (last component) for matching
DIR_NAME=$(basename "$DIR_PATH")

# Resolve path relative to repo root for readability
REPO_ROOT=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}
if [ -n "$REPO_ROOT" ]; then
  REL_PATH="${FILE_PATH#$REPO_ROOT/}"
  REL_DIR="${DIR_PATH#$REPO_ROOT/}"
else
  REL_PATH="$FILE_PATH"
  REL_DIR="$DIR_PATH"
fi

SYSTEM_MAP="$REPO_ROOT/holding/SYSTEM-MAP.md"

# Check if SYSTEM-MAP.md exists
if [ ! -f "$SYSTEM_MAP" ]; then
  exit 0
fi

# Check if the directory path appears in SYSTEM-MAP.md
# We check for the relative dir path or the directory name in the tree
if ! grep -q "$REL_DIR\|$DIR_NAME/" "$SYSTEM_MAP" 2>/dev/null; then
  echo ""
  echo "⚠ PROTO-001: New path detected outside SYSTEM-MAP.md"
  echo "  File: $REL_PATH"
  echo "  Dir:  $REL_DIR"
  echo ""
  echo "  This directory is not in holding/SYSTEM-MAP.md."
  echo "  Per PROTO-001 (Structure Before Creation):"
  echo "    1. Does this content already have a home in an existing directory?"
  echo "    2. If not, document WHY existing structures don't fit."
  echo "    3. Update SYSTEM-MAP.md after creating."
  echo ""
else
  # Directory exists in map but still remind about SYSTEM-MAP consultation
  echo ""
  echo "PROTO-001: Creating new file in mapped directory: $REL_PATH"
  echo "  Confirm: does this fit the purpose of $REL_DIR per SYSTEM-MAP.md?"
  echo ""
fi

exit 0
