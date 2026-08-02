#!/bin/bash
# Claude Code Stop hook. Emits 'session_stop' event keyed by session_id.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_emit.sh"

SID=$(_billu_field "session_id")
[ -z "$SID" ] && exit 0

_billu_emit "{\"kind\":\"session_stop\",\"ts\":$(date +%s),\"tty\":\"$SID\",\"reason\":\"stop_hook\"}"
exit 0
