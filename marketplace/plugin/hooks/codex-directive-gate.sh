#!/usr/bin/env bash
# PROTO-019 v3: Codex directive gate (PreToolUse hook)
#
# Reads the SESSION-SCOPED pending-directive marker written by
# codex-directive-detect.sh. Blocks Edit|Write|MultiEdit and destructive Bash
# (git commit/push/reset --hard, rm -rf) until a codex verdict file exists
# whose DIRECTIVE-ID matches the marker's.
#
# v3 change (2026-04-25): marker path is .claude/codex-directive-pending-<SID>
# instead of the legacy single-slot .claude/codex-directive-pending. This gate
# only checks the marker for the CURRENT session — orphans from other
# sessions can no longer block unrelated work.
#
# Exit semantics (PreToolUse):
#   0 = allow
#   2 = block with message on stderr
#
# Override: CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON='...' — logged, clears.
#
# Verdict file contract: any file in .enforcement/codex-reviews/*.md with
#   DIRECTIVE-ID: <id>
#   CODEX-VERDICT: PASS | FAIL | CHANGES-REQUIRED | ADVISORY

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

# Kill-switch
[ -n "${CODEX_DIRECTIVE_DISABLED:-}" ] && exit 0
[ -f "$HOME/.codex-directive-disabled" ] && exit 0

REVIEW_DIR=".enforcement/codex-reviews"

PAYLOAD=$(cat 2>/dev/null || true)
TOOL=$(printf '%s' "$PAYLOAD" | jq -r '.tool_name // empty' 2>/dev/null)
SID=$(printf '%s' "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)
SID=$(printf '%s' "$SID" | tr -cd 'a-zA-Z0-9_-' | head -c 64)
[ -z "$SID" ] && SID="no-sid"

# Refresh heartbeat on every fire — sweep uses this to detect dead sessions
mkdir -p .claude/heartbeats 2>/dev/null || true
touch ".claude/heartbeats/$SID" 2>/dev/null || true

MARKER=".claude/codex-directive-pending-$SID"

[ -f "$MARKER" ] || exit 0

# For Bash, only gate destructive commands
if [ "$TOOL" = "Bash" ]; then
  CMD=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // empty' 2>/dev/null)
  case "$CMD" in
    *"git commit"*|*"git push"*|*"git reset --hard"*|*"rm -rf"*) ;;
    *) exit 0 ;;
  esac
fi

log_event() {
  local json="$1"
  mkdir -p "$REVIEW_DIR"
  printf '%s\n' "$json" >> "$REVIEW_DIR/gate-log.jsonl" 2>/dev/null || true
}

# Override path
if [ "${CODEX_DIRECTIVE_ACK:-0}" = "1" ]; then
  REASON_RAW="${CODEX_DIRECTIVE_REASON:-no-reason}"
  REASON_SAFE=$(printf '%s' "$REASON_RAW" | tr -d '\n\r' | head -c 500)
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if command -v jq >/dev/null 2>&1; then
    EVENT=$(jq -nc --arg ts "$TS" --arg tool "$TOOL" --arg reason "$REASON_SAFE" \
      '{ts:$ts,event:"directive-override",tool:$tool,reason:$reason}')
    log_event "$EVENT"
  fi
  rm -f "$MARKER" 2>/dev/null || true
  exit 0
fi

DIRECTIVE_ID=$(grep -E "^DIRECTIVE-ID: " "$MARKER" 2>/dev/null | awk '{print $2}' | head -1)
MARKER_TS=$(grep -E "^TS: " "$MARKER" 2>/dev/null | awk '{print $2}' | head -1)
MATCH=$(grep -E "^MATCH: " "$MARKER" 2>/dev/null | cut -d' ' -f2- | head -1)

if [ -z "$DIRECTIVE_ID" ] || [ -z "$MARKER_TS" ]; then
  {
    printf 'PROTO-019: marker malformed at %s.\n' "$MARKER"
    printf '  Expected: DIRECTIVE-ID + TS + MATCH lines. Delete or fix, then retry.\n'
  } >&2
  exit 2
fi

MATCHING_VERDICT=""
if [ -d "$REVIEW_DIR" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    if grep -q "^DIRECTIVE-ID: ${DIRECTIVE_ID}$" "$f" 2>/dev/null; then
      MATCHING_VERDICT="$f"
      break
    fi
  done < <(ls -t "$REVIEW_DIR"/*.md 2>/dev/null)
fi

if [ -z "$MATCHING_VERDICT" ]; then
  {
    printf 'PROTO-019: codex review outstanding for directive at %s.\n' "$MARKER_TS"
    printf '  Directive ID: %s\n' "$DIRECTIVE_ID"
    printf '  Matched phrase: %s\n' "$MATCH"
    printf '  Run /codex review and ensure the verdict file echoes "DIRECTIVE-ID: %s".\n' "$DIRECTIVE_ID"
    printf '  Override: CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON="..." <tool-call>\n'
  } >&2
  exit 2
fi

VERDICT=$(grep -E "^CODEX-VERDICT: " "$MATCHING_VERDICT" 2>/dev/null | head -1 | awk '{print $2}')
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case "$VERDICT" in
  PASS|ADVISORY)
    rm -f "$MARKER" 2>/dev/null || true
    if command -v jq >/dev/null 2>&1; then
      EVENT=$(jq -nc --arg ts "$TS" --arg verdict "$VERDICT" \
        --argjson id "$DIRECTIVE_ID" --arg file "$MATCHING_VERDICT" \
        '{ts:$ts,event:"directive-cleared",id:$id,verdict:$verdict,file:$file}')
      log_event "$EVENT"
    fi
    exit 0
    ;;
  FAIL|CHANGES-REQUIRED)
    {
      printf 'PROTO-019: codex verdict is %s for directive at %s.\n' "$VERDICT" "$MARKER_TS"
      printf '  Verdict file: %s\n' "$MATCHING_VERDICT"
      printf '  Fix findings and re-run /codex review (must keep DIRECTIVE-ID: %s),\n' "$DIRECTIVE_ID"
      printf '  or override: CODEX_DIRECTIVE_ACK=1 CODEX_DIRECTIVE_REASON="..." <tool-call>\n'
    } >&2
    exit 2
    ;;
  *)
    {
      printf 'PROTO-019: verdict file %s has no recognized CODEX-VERDICT.\n' "$MATCHING_VERDICT"
      printf '  Expected "CODEX-VERDICT: PASS|FAIL|CHANGES-REQUIRED|ADVISORY", found: "%s"\n' "$VERDICT"
    } >&2
    exit 2
    ;;
esac
