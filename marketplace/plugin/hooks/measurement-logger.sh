#!/usr/bin/env bash
# measurement-logger.sh — Sutra Measurement Protocol (PostToolUse hook)
# Captures actuals after Edit/Write/Bash for the Estimation Engine calibration loop.
# Exit 0 always — measurement never blocks work.

# Read hook input from stdin (JSON with tool_name, tool_input, etc.)
INPUT="$(cat)"

# Extract tool name and file path from hook input
TOOL_NAME="$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
FILE_PATH=""

# Only fire for Edit, Write, Bash
case "$TOOL_NAME" in
  Edit|Write|Bash) ;;
  *) exit 0 ;;
esac

# Extract file_path from tool_input (Edit/Write have it)
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
  FILE_PATH="$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
fi

# Determine repo root (two levels up from this hook)
REPO_ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"

# Timestamp
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# ── Read depth-registered if it exists ──
DEPTH_FILE="$REPO_ROOT/.claude/depth-registered"
DEPTH_LEVEL=""
TASK_DESC=""
if [ -f "$DEPTH_FILE" ]; then
  LINE="$(head -1 "$DEPTH_FILE")"
  DEPTH_LEVEL="$(echo "$LINE" | cut -d'|' -f1 | tr -d ' ')"
  # Task description is third field onward
  TASK_DESC="$(echo "$LINE" | cut -d'|' -f3- | sed 's/^ *//')"
fi

# ── Append measurement entry to estimation-log.jsonl ──
LOG_DIR="$REPO_ROOT/os/engines"
LOG_FILE="$LOG_DIR/estimation-log.jsonl"

mkdir -p "$LOG_DIR" 2>/dev/null || true

# Build JSON line (no jq dependency — manual construction)
# Escape double quotes in strings
escape_json() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g'
}

TOOL_ESC="$(escape_json "$TOOL_NAME")"
FILE_ESC="$(escape_json "$FILE_PATH")"
DEPTH_ESC="$(escape_json "$DEPTH_LEVEL")"
TASK_ESC="$(escape_json "$TASK_DESC")"

ENTRY="{\"ts\":\"$TS\",\"event\":\"tool_use\",\"tool\":\"$TOOL_ESC\""
if [ -n "$FILE_PATH" ]; then
  ENTRY="$ENTRY,\"file\":\"$FILE_ESC\""
fi
if [ -n "$DEPTH_LEVEL" ]; then
  ENTRY="$ENTRY,\"depth_registered\":\"$DEPTH_ESC\""
fi
if [ -n "$TASK_DESC" ]; then
  ENTRY="$ENTRY,\"task\":\"$TASK_ESC\""
fi
ENTRY="$ENTRY}"

echo "$ENTRY" >> "$LOG_FILE" 2>/dev/null || true

# ── Update session stats ──
STATS_DIR="$REPO_ROOT/.claude"
STATS_FILE="$STATS_DIR/session-stats"

mkdir -p "$STATS_DIR" 2>/dev/null || true

# Initialize stats file if missing
if [ ! -f "$STATS_FILE" ]; then
  cat > "$STATS_FILE" <<STATS
edits_count=0
files_touched=
session_start=$TS
STATS
fi

# Read current values
EDITS_COUNT="$(sed -n 's/^edits_count=\(.*\)/\1/p' "$STATS_FILE")"
FILES_TOUCHED="$(sed -n 's/^files_touched=\(.*\)/\1/p' "$STATS_FILE")"
SESSION_START="$(sed -n 's/^session_start=\(.*\)/\1/p' "$STATS_FILE")"

# Default edits_count to 0 if empty
EDITS_COUNT="${EDITS_COUNT:-0}"

# Increment edit count for Edit/Write
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
  EDITS_COUNT=$((EDITS_COUNT + 1))

  # Add file to unique files list if not already present
  if [ -n "$FILE_PATH" ]; then
    if ! echo "$FILES_TOUCHED" | tr ',' '\n' | grep -qxF "$FILE_PATH"; then
      if [ -z "$FILES_TOUCHED" ]; then
        FILES_TOUCHED="$FILE_PATH"
      else
        FILES_TOUCHED="$FILES_TOUCHED,$FILE_PATH"
      fi
    fi
  fi
fi

# Write updated stats
cat > "$STATS_FILE" <<STATS
edits_count=$EDITS_COUNT
files_touched=$FILES_TOUCHED
session_start=${SESSION_START:-$TS}
STATS

exit 0
