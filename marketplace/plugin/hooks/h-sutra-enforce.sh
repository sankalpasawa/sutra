#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/h-sutra-enforce.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-05-12
# VERSION=v4 (filters tool_result user rows; first-text-of-current-turn semantic)
#
# h-sutra-enforce.sh — Stop hook. Identifies the LAST HUMAN user message
# (filtering out tool_result user rows), then checks the FIRST text content
# of the FIRST assistant row after it. That text must start with H-Sutra
# header. If not → decision:block JSON forces redo.
#
# v4 fix (2026-05-12 same-day from v3): Claude Code records tool_results
# as role:user with tool_result-typed content. v3 was finding the latest
# tool_result and walking forward → got the LAST text of turn, not the
# FIRST. v4 filters tool_result user rows to find the true human turn.
#
# Kill: SUTRA_HSUTRA_ENFORCE_DISABLED=1  OR  ~/.h-sutra-enforce-disabled

set -u
export LC_ALL=C.UTF-8 LANG=C.UTF-8 2>/dev/null || true

[ "${SUTRA_HSUTRA_ENFORCE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.h-sutra-enforce-disabled" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
AUDIT_LOG="$REPO_ROOT/.enforcement/h-sutra-audit.jsonl"
VIOLATIONS_LOG="$REPO_ROOT/.enforcement/governance-violations.jsonl"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null

STDIN_PAYLOAD=""
[ ! -t 0 ] && STDIN_PAYLOAD="$(cat 2>/dev/null || true)"

SESSION_ID="unknown"
TRANSCRIPT_PATH=""
ACTIVE="false"

if command -v jq >/dev/null 2>&1 && [ -n "$STDIN_PAYLOAD" ]; then
  SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null)
  TRANSCRIPT_PATH=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
  ACTIVE=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

audit_log() {
  local decision="$1" first200="$2" reason="${3:-}"
  first200=$(printf '%s' "$first200" | head -c 200 | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
  reason=$(printf '%s' "$reason" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"ts":"%s","session_id":"%s","decision":"%s","first200":"%s","reason":"%s"}\n' \
    "$NOW" "$SESSION_ID" "$decision" "$first200" "$reason" \
    >> "$AUDIT_LOG" 2>/dev/null
}

if [ "$ACTIVE" = "true" ]; then
  audit_log "skipped" "" "stop_hook_active=true"
  exit 0
fi

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  audit_log "skipped" "" "no_transcript"
  exit 0
fi

# Identify FIRST TEXT of CURRENT TURN via Python (clean JSONL walk).
# Current turn = everything after the last HUMAN user row (not tool_result).
FIRST_TEXT_OF_TURN=$(TRANSCRIPT_FOR_PY="$TRANSCRIPT_PATH" python3 -c '
import os, sys, json
p = os.environ["TRANSCRIPT_FOR_PY"]
rows = []
try:
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
except: sys.exit(0)

def is_human_user(r):
    if r.get("role") != "user" and r.get("type") != "user":
        return False
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, str): return True
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                return False
        return True
    return False

last_user = -1
for i, r in enumerate(rows):
    if is_human_user(r):
        last_user = i

for r in rows[last_user+1:]:
    if r.get("role") != "assistant" and r.get("type") != "assistant":
        continue
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                t = b.get("text", "")
                if t:
                    print(t)
                    sys.exit(0)
    elif isinstance(content, str) and content:
        print(content)
        sys.exit(0)
')

if [ -z "$FIRST_TEXT_OF_TURN" ]; then
  audit_log "skipped" "" "no_text_in_current_turn"
  exit 0
fi

FIRST_LINE=$(printf '%s' "$FIRST_TEXT_OF_TURN" | head -1)
FIRST200=$(printf '%s' "$FIRST_TEXT_OF_TURN" | head -c 200)

HEADER_RE='^\[(D[0-9]+|[A-Z0-9-]+)·([A-Z0-9-]+)( · (TIMING|TENSE|CHANNEL|REV|RISK|attempt):[^]·]+)*\]|^\[STAGE-1-FAIL · CLARIFY( · attempt:[0-9]+/[0-9]+)?\]'

if printf '%s' "$FIRST_LINE" | grep -qE "$HEADER_RE"; then
  audit_log "pass" "$FIRST200" "header_matched"
  exit 0
fi

audit_log "block" "$FIRST200" "header_missing_layer_fired"

FIRST_ESC=$(printf '%s' "$FIRST200" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"ts":"%s","session_id":"%s","violation":"h_sutra_header_missing","layer":"h-sutra","layer_fired":true,"first_line_observed":"%s","action":"stop_blocked_force_redo"}\n' \
  "$NOW" "$SESSION_ID" "$FIRST_ESC" \
  >> "$VIOLATIONS_LOG" 2>/dev/null

cat <<JSON
{
  "decision": "block",
  "reason": "H-Sutra layer FIRED: first text of this turn did not start with the H-Sutra header.\n\nPer CLAUDE.md §Mandatory Blocks, EVERY response must start with the H-Sutra header as the literal FIRST text:\n  [<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]\n\nOr Stage-1-fail variant:\n  [STAGE-1-FAIL · CLARIFY · attempt:1/1]\n\nFirst 200 chars of your turn's first text: '${FIRST_ESC}'\n\nRedo: emit the H-Sutra header as the LITERAL FIRST line, then continue with Input Routing + Depth blocks per CLAUDE.md."
}
JSON
exit 0
