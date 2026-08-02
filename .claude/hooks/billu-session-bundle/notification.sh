#!/bin/bash
# Claude Code Notification hook. Emits 'notification' event keyed by session_id.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_emit.sh"

SID=$(_billu_field "session_id")
MSG=$(_billu_field "message")
[ -z "$SID" ] && exit 0

MSG_E=$(_billu_esc "$MSG")

_billu_emit "{\"kind\":\"notification\",\"ts\":$(date +%s),\"tty\":\"$SID\",\"message\":\"$MSG_E\"}"
exit 0
