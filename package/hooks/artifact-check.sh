#!/bin/bash
# PROTO-009: Narration Is Not Artifact — Depth-Based Artifact Enforcement
# Event: PostToolUse on Edit|Write
# Enforcement: SOFT (warns but does not block, exit 0 always)
# At Depth 3+, every lifecycle phase must produce a file on disk.
# Fires when the target file is a completion-type file (RETROSPECTIVE.md, DELIVERABLES.md, project/).

FILE_PATH="$TOOL_INPUT_file_path"

# No file path → not relevant
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# ─── Only fire on completion-type files ─────────────────────────────────
IS_COMPLETION=false
case "$FILE_PATH" in
  *RETROSPECTIVE.md|*DELIVERABLES.md|*/project/*)
    IS_COMPLETION=true
    ;;
esac

if [ "$IS_COMPLETION" = false ]; then
  exit 0
fi

# ─── Find repo root ────────────────────────────────────────────────────
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# ─── Read depth registration ───────────────────────────────────────────
# Format: DEPTH_LEVEL TIMESTAMP TASK_DESCRIPTION
DEPTH_FILE="$REPO_ROOT/.claude/depth-registered"
if [ ! -f "$DEPTH_FILE" ]; then
  exit 0
fi

DEPTH_LINE=$(head -1 "$DEPTH_FILE")
DEPTH_LEVEL=$(echo "$DEPTH_LINE" | awk '{print $1}')

# Validate depth is a number
if ! echo "$DEPTH_LEVEL" | grep -qE '^[0-9]+$'; then
  exit 0
fi

# ─── Depth 1-2: no artifact check needed ───────────────────────────────
if [ "$DEPTH_LEVEL" -lt 3 ]; then
  exit 0
fi

# ─── Get registration timestamp for freshness checks ───────────────────
REG_TIMESTAMP=$(echo "$DEPTH_LINE" | awk '{print $2}')

MISSING=""

# ─── Depth 3+: Check context/DECISIONS.md updated ──────────────────────
DECISIONS_FILE="$REPO_ROOT/context/DECISIONS.md"
if [ ! -f "$DECISIONS_FILE" ]; then
  MISSING="$MISSING\n  - context/DECISIONS.md (does not exist — create it with key decisions)"
else
  # Check if modified after depth registration
  if [ -n "$REG_TIMESTAMP" ]; then
    FILE_MOD=$(stat -f '%m' "$DECISIONS_FILE" 2>/dev/null || stat -c '%Y' "$DECISIONS_FILE" 2>/dev/null)
    REG_EPOCH=$(date -j -f '%Y-%m-%dT%H:%M:%S' "$REG_TIMESTAMP" '+%s' 2>/dev/null || date -d "$REG_TIMESTAMP" '+%s' 2>/dev/null)
    if [ -n "$FILE_MOD" ] && [ -n "$REG_EPOCH" ] && [ "$FILE_MOD" -lt "$REG_EPOCH" ]; then
      MISSING="$MISSING\n  - context/DECISIONS.md (not updated since depth registration)"
    fi
  fi
fi

# ─── Depth 4+: Check estimation log marker ─────────────────────────────
if [ "$DEPTH_LEVEL" -ge 4 ]; then
  ESTIMATION_MARKER="$REPO_ROOT/.claude/estimation-logged"
  if [ ! -f "$ESTIMATION_MARKER" ]; then
    MISSING="$MISSING\n  - .claude/estimation-logged (no estimation log entry for this task)"
  fi
fi

# ─── Depth 5: Check project/RETROSPECTIVE.md updated ───────────────────
if [ "$DEPTH_LEVEL" -ge 5 ]; then
  RETRO_FILE="$REPO_ROOT/project/RETROSPECTIVE.md"
  if [ ! -f "$RETRO_FILE" ]; then
    MISSING="$MISSING\n  - project/RETROSPECTIVE.md (does not exist — create it with learnings)"
  else
    if [ -n "$REG_TIMESTAMP" ]; then
      FILE_MOD=$(stat -f '%m' "$RETRO_FILE" 2>/dev/null || stat -c '%Y' "$RETRO_FILE" 2>/dev/null)
      REG_EPOCH=$(date -j -f '%Y-%m-%dT%H:%M:%S' "$REG_TIMESTAMP" '+%s' 2>/dev/null || date -d "$REG_TIMESTAMP" '+%s' 2>/dev/null)
      if [ -n "$FILE_MOD" ] && [ -n "$REG_EPOCH" ] && [ "$FILE_MOD" -lt "$REG_EPOCH" ]; then
        MISSING="$MISSING\n  - project/RETROSPECTIVE.md (not updated since depth registration)"
      fi
    fi
  fi
fi

# ─── Log to JSONL ──────────────────────────────────────────────────────
LOG_DIR="$REPO_ROOT/.claude/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/artifact-check.jsonl"

TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
HAS_MISSING="false"
if [ -n "$MISSING" ]; then
  HAS_MISSING="true"
fi

# Escape strings for JSON
ESCAPED_FILE=$(echo "$FILE_PATH" | sed 's/"/\\"/g')
ESCAPED_MISSING=$(echo -e "$MISSING" | tr '\n' '|' | sed 's/"/\\"/g')

echo "{\"ts\":\"$TIMESTAMP\",\"depth\":$DEPTH_LEVEL,\"file\":\"$ESCAPED_FILE\",\"missing\":$HAS_MISSING,\"details\":\"$ESCAPED_MISSING\"}" >> "$LOG_FILE"

# ─── Output warning if artifacts missing ────────────────────────────────
TRACKER="$(dirname "$0")/compliance-tracker.sh"
RESIL="$(dirname "$0")/resilience.sh"

if [ -n "$MISSING" ]; then
  echo ""
  echo "=== PROTO-009: ARTIFACT CHECK (Depth $DEPTH_LEVEL) ==="
  echo "You are completing a task at Depth $DEPTH_LEVEL but required artifacts are missing:"
  echo -e "$MISSING"
  echo ""
  echo "Narration is not artifact. Create these files before closing this task."
  echo "================================================="
  echo ""
  [ -f "$TRACKER" ] && bash "$TRACKER" "artifact-check" "warn" "$REPO_ROOT"
  [ -f "$RESIL" ] && bash "$RESIL" "artifact-check" "warn" "$REPO_ROOT"
else
  [ -f "$TRACKER" ] && bash "$TRACKER" "artifact-check" "pass" "$REPO_ROOT"
  [ -f "$RESIL" ] && bash "$RESIL" "artifact-check" "pass" "$REPO_ROOT"
fi

# SOFT enforcement: always exit 0
exit 0
