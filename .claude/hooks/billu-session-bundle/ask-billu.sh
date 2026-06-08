#!/bin/bash
# hooks/session-bundle/ask-billu.sh — emit decision_needed event.
# This script runs from a slash command (Claude's Bash tool), NOT as a hook,
# so there's no stdin JSON. Reads the session_id from the marker file written
# by SessionStart.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_emit.sh"

QUESTION="${*:-(no question)}"
DECISION_ID="$(date +%s)-$$"
CWD="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Read session_id from the marker that SessionStart wrote.
MARKER=$(_billu_session_marker_file)
SID=$(cat "$MARKER" 2>/dev/null)
[ -z "$SID" ] && SID="unknown-$(date +%s)-$$"

# class is the first whitespace-delimited token if it starts with `class:` else "general"
CLASS="general"
if printf '%s' "$QUESTION" | grep -qE '^class:[a-z_]+'; then
  CLASS=$(printf '%s' "$QUESTION" | sed -E 's/^class:([a-z_]+).*/\1/')
  QUESTION=$(printf '%s' "$QUESTION" | sed -E 's/^class:[a-z_]+[[:space:]]*//')
fi

QUESTION_E=$(_billu_esc "$QUESTION")
CWD_E=$(_billu_esc "$CWD")
CLASS_E=$(_billu_esc "$CLASS")

_billu_emit "{\"kind\":\"decision_needed\",\"ts\":$(date +%s),\"tty\":\"$SID\",\"decision_id\":\"$DECISION_ID\",\"class\":\"$CLASS_E\",\"question\":\"$QUESTION_E\",\"context\":{\"cwd\":\"$CWD_E\"}}"

# Tell the user we're waiting.
echo "[ask-billu] question dispatched (decision_id=$DECISION_ID, class=$CLASS). Waiting for inbox…"
exit 0
