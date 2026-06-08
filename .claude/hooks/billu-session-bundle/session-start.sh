#!/bin/bash
# Claude Code SessionStart hook. Emits 'session_start' event.
# Reads session_id from the JSON payload Claude Code delivers on stdin.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_emit.sh"

SID=$(_billu_field "session_id")
CWD=$(_billu_field "cwd")
[ -z "$CWD" ] && CWD="${CLAUDE_PROJECT_DIR:-$(pwd)}"
COMPANY="${BILLU_COMPANY:-$(basename "$CWD")}"

# Skip if no session_id (something is wrong)
[ -z "$SID" ] && exit 0

# Persist marker for ask-billu and similar in-session scripts that don't get stdin JSON.
MARKER=$(_billu_session_marker_file)
mkdir -p "$(dirname "$MARKER")" 2>/dev/null
printf '%s' "$SID" > "$MARKER"

CWD_E=$(_billu_esc "$CWD")
COMP_E=$(_billu_esc "$COMPANY")
SID_E=$(_billu_esc "$SID")

_billu_emit "{\"kind\":\"session_start\",\"ts\":$(date +%s),\"tty\":\"$SID_E\",\"cwd\":\"$CWD_E\",\"company\":\"$COMP_E\",\"session_id\":\"$SID_E\"}"
exit 0
