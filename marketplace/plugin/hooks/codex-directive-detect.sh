#!/usr/bin/env bash
# PROTO-019 v3: Codex directive detector (UserPromptSubmit hook)
#
# When the founder says "use codex to review X" (or similar), we want that
# directive enforced — not just acknowledged and forgotten. This hook detects
# the directive in the raw prompt and writes a pending marker that the
# PreToolUse gate reads to block Edit/Write until a matching verdict exists.
#
# Design (v3 — session-scoped, 2026-04-25):
#   - Strip fenced code blocks + inline backticks before matching
#   - Match known directive phrasings (verb + codex proximity)
#   - Reject on explicit negation within a short window before "codex"
#   - Marker is session-scoped: .claude/codex-directive-pending-<session_id>
#   - Heartbeat touched on every fire: .claude/heartbeats/<session_id>
#   - Embed DIRECTIVE-ID (epoch) for verdict pairing
#
# Why session-scoped: previous single-slot marker survived across sessions.
# Abandoned sessions left orphaned markers that blocked unrelated future
# sessions on the same repo. v3 isolates markers per session; the
# sessionstart sweep archives any whose heartbeat is stale.
#
# Payload: JSON on stdin with .prompt and .session_id
# Output: writes .claude/codex-directive-pending-<SID> on match; always
#         touches .claude/heartbeats/<SID>
# Exit: always 0 (detection is advisory; gate does the blocking)

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

# Kill-switch
[ -n "${CODEX_DIRECTIVE_DISABLED:-}" ] && exit 0
[ -f "$HOME/.codex-directive-disabled" ] && exit 0

mkdir -p .claude .claude/heartbeats

PAYLOAD=$(cat 2>/dev/null || true)
PROMPT=$(printf '%s' "$PAYLOAD" | jq -r '.prompt // empty' 2>/dev/null)
SID=$(printf '%s' "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)

# Sanitize SID (alphanumeric + dash/underscore only; fallback to "no-sid")
SID=$(printf '%s' "$SID" | tr -cd 'a-zA-Z0-9_-' | head -c 64)
[ -z "$SID" ] && SID="no-sid"

# Always refresh heartbeat — proves this session is alive
touch ".claude/heartbeats/$SID" 2>/dev/null || true

[ -z "$PROMPT" ] && exit 0

# Strip fenced code blocks and inline backticks
CLEAN=$(printf '%s\n' "$PROMPT" | awk '
  /^```/ { inblock = !inblock; next }
  !inblock { print }
' | sed 's/`[^`]*`//g')

CLEAN_LOWER=$(printf '%s' "$CLEAN" | tr '\n' ' ' | tr '[:upper:]' '[:lower:]')

DIRECTIVE_PATTERNS=(
  '(use|using|run|running|have|having|let|ask|consult)( +[a-z/]+){0,4} +codex'
  'codex +(review|check|audit|should|must|needs +to|to +review|to +check)'
  '/codex +(review|consult|challenge)'
)

MATCHED=0
MATCH_TEXT=""
for pat in "${DIRECTIVE_PATTERNS[@]}"; do
  hit=$(printf '%s' "$CLEAN_LOWER" | grep -E -o ".{0,40}$pat.{0,40}" | head -1)
  if [ -n "$hit" ]; then
    MATCHED=1
    MATCH_TEXT="$hit"
    break
  fi
done

[ "$MATCHED" -eq 0 ] && exit 0

# Negation suppression
NEG_RE="(don'?t|do +not|without|shouldn'?t|can'?t|won'?t|no +need +to)[a-z' ]{0,24}codex"
if printf '%s' "$CLEAN_LOWER" | grep -E -q "$NEG_RE"; then
  exit 0
fi

DIRECTIVE_ID=$(date +%s)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
MATCH_SAFE=$(printf '%s' "$MATCH_TEXT" | tr -d '\n\r' | head -c 160)

cat > ".claude/codex-directive-pending-$SID" <<EOF
DIRECTIVE-ID: $DIRECTIVE_ID
TS: $TS
SESSION-ID: $SID
MATCH: $MATCH_SAFE
EOF

mkdir -p .enforcement/codex-reviews
if command -v jq >/dev/null 2>&1; then
  jq -nc \
    --arg ts "$TS" \
    --arg match "$MATCH_SAFE" \
    --arg sid "$SID" \
    --argjson id "$DIRECTIVE_ID" \
    '{ts:$ts,event:"directive-detected",id:$id,session_id:$sid,match:$match}' \
    >> .enforcement/codex-reviews/gate-log.jsonl 2>/dev/null || true
fi

exit 0
