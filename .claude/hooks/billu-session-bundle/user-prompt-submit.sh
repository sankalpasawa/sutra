#!/bin/bash
# hooks/session-bundle/user-prompt-submit.sh
# (a) emit user_prompt event keyed by session_id
# (b) if inbox entry exists for this session_id, inject Billu's response and emit decision_made
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_emit.sh"

SID=$(_billu_field "session_id")
PROMPT=$(_billu_field "prompt")
[ -z "$SID" ] && exit 0

PREVIEW=$(printf '%s' "$PROMPT" | head -c 80 | tr -d '\n')
PREVIEW_E=$(_billu_esc "$PREVIEW")

_billu_emit "{\"kind\":\"user_prompt\",\"ts\":$(date +%s),\"tty\":\"$SID\",\"text_len\":${#PROMPT},\"preview\":\"$PREVIEW_E\"}"

# Inbox path uses the same key encoding as paths.ts inboxFile() — slash-replaced + leading-underscores-stripped
HOME_BILLU="${BILLU_HOME:-$HOME/.billu}"
SAFE_KEY=$(printf '%s' "$SID" | sed 's|/|_|g; s|^_*||')
INBOX_FILE="$HOME_BILLU/inbox/$SAFE_KEY.json"

if [ -f "$INBOX_FILE" ]; then
  RESPONSE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["response"])' "$INBOX_FILE" 2>/dev/null)
  DECISION_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decision_id"])' "$INBOX_FILE" 2>/dev/null)
  DECIDED_BY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decided_by"])' "$INBOX_FILE" 2>/dev/null)

  RESP_E=$(_billu_esc "$RESPONSE")
  _billu_emit "{\"kind\":\"decision_made\",\"ts\":$(date +%s),\"tty\":\"$SID\",\"decision_id\":\"$DECISION_ID\",\"decided_by\":\"$DECIDED_BY\",\"response\":\"$RESP_E\"}"

  # Use python json for stdout to safely escape DECISION_ID + RESPONSE.
  python3 -c "import json,sys
print(json.dumps({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':f'Billu answered your earlier question (decision_id={sys.argv[1]}, decided_by={sys.argv[2]}): {sys.argv[3]}'}}))" "$DECISION_ID" "$DECIDED_BY" "$RESPONSE"

  rm -f "$INBOX_FILE"
fi

exit 0
