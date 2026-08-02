#!/bin/bash
# Claude Code PostToolUse hook. Emits 'tool_use' event keyed by session_id.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_emit.sh"

SID=$(_billu_field "session_id")
TOOL=$(_billu_field "tool_name")
[ -z "$SID" ] || [ -z "$TOOL" ] && exit 0

# tool_input is a JSON object — extract a brief from common fields.
BRIEF=$(_billu_read_stdin_json | python3 -c "import json,sys
d=json.load(sys.stdin)
ti=d.get('tool_input', {}) or {}
b=ti.get('file_path') or ti.get('command') or ti.get('path') or ti.get('pattern') or ''
print(str(b)[:80])" 2>/dev/null)

TOOL_E=$(_billu_esc "$TOOL")
BRIEF_E=$(_billu_esc "$BRIEF")

_billu_emit "{\"kind\":\"tool_use\",\"ts\":$(date +%s),\"tty\":\"$SID\",\"tool\":\"$TOOL_E\",\"brief\":\"$BRIEF_E\"}"
exit 0
