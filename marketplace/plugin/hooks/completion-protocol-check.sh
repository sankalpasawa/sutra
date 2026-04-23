#!/usr/bin/env bash
# PROTO-022: Completion Status Protocol check (PostToolUse on Task)
#
# Scans subagent output for a normalized terminal state line. SOFT enforcement:
# missing STATUS line → warning to stderr + audit row in
# .enforcement/completion-protocol.jsonl. Does NOT block.
#
# Expected (case-sensitive):
#   STATUS: DONE
#   STATUS: DONE_WITH_CONCERNS
#   STATUS: BLOCKED           (+ REASON + ATTEMPTED + RECOMMENDATION)
#   STATUS: NEEDS_CONTEXT     (+ REASON + ATTEMPTED + RECOMMENDATION)
#
# Kill-switch: COMPLETION_PROTOCOL_DISABLED=1 env OR ~/.completion-protocol-disabled
# OR SUTRA_COMPLETION_PROTOCOL_ENABLED=false in ~/.sutra/config.env
#
# Override: COMPLETION_PROTOCOL_ACK=1 COMPLETION_PROTOCOL_ACK_REASON="..." (logged)

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
cd "$REPO_ROOT" || exit 0

[ -n "${COMPLETION_PROTOCOL_DISABLED:-}" ] && exit 0
[ -f "$HOME/.completion-protocol-disabled" ] && exit 0

if [ -f "$HOME/.sutra/config.env" ]; then
  # shellcheck disable=SC1090
  . "$HOME/.sutra/config.env" 2>/dev/null || true
fi
[ "${SUTRA_COMPLETION_PROTOCOL_ENABLED:-true}" = "false" ] && exit 0

LOG_DIR="$REPO_ROOT/.enforcement"
LOG_FILE="$LOG_DIR/completion-protocol.jsonl"
mkdir -p "$LOG_DIR" 2>/dev/null || true

log_event() { printf '%s\n' "$1" >> "$LOG_FILE" 2>/dev/null || true; }

JSON=""
[ ! -t 0 ] && JSON=$(cat 2>/dev/null)

TOOL_NAME="${TOOL_NAME:-}"
if [ -z "$TOOL_NAME" ] && [ -n "$JSON" ] && command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$JSON" | jq -r '.tool_name // empty' 2>/dev/null)
fi

case "$TOOL_NAME" in
  Task|Agent) ;;
  *) exit 0 ;;
esac

# Override path
if [ "${COMPLETION_PROTOCOL_ACK:-0}" = "1" ]; then
  REASON_RAW="${COMPLETION_PROTOCOL_ACK_REASON:-no-reason}"
  REASON_SAFE=$(printf '%s' "$REASON_RAW" | tr -d '\n\r' | head -c 500)
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if command -v jq >/dev/null 2>&1; then
    EVT=$(jq -nc --arg ts "$TS" --arg tool "$TOOL_NAME" --arg reason "$REASON_SAFE" \
      '{ts:$ts,event:"completion-protocol-override",tool:$tool,reason:$reason}')
    log_event "$EVT"
  fi
  exit 0
fi

RESPONSE=""
if [ -n "$JSON" ] && command -v jq >/dev/null 2>&1; then
  for path in '.tool_response' '.tool_response.content' '.tool_response.text' \
              '.tool_response.content[0].text' '.response' '.output'; do
    CANDIDATE=$(printf '%s' "$JSON" | jq -r "$path // empty" 2>/dev/null)
    if [ -n "$CANDIDATE" ] && [ "$CANDIDATE" != "null" ]; then
      RESPONSE="$CANDIDATE"
      break
    fi
  done
fi

[ -z "$RESPONSE" ] && exit 0

SUBAGENT_TYPE=""
if [ -n "$JSON" ] && command -v jq >/dev/null 2>&1; then
  SUBAGENT_TYPE=$(printf '%s' "$JSON" | jq -r '.tool_input.subagent_type // "unknown"' 2>/dev/null)
fi

STATUS_LINE=$(printf '%s\n' "$RESPONSE" | grep -E '^[[:space:]]*STATUS:[[:space:]]+(DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT)[[:space:]]*$' | tail -1)

if [ -z "$STATUS_LINE" ]; then
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  {
    echo "PROTO-022: subagent response missing STATUS: line."
    echo "  Expected one of: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT"
    echo "  Subagent type: $SUBAGENT_TYPE"
    echo "  (SOFT warning — exit 0; HARD once adoption passes 80%)"
  } >&2
  if command -v jq >/dev/null 2>&1; then
    EVT=$(jq -nc --arg ts "$TS" --arg tool "$TOOL_NAME" --arg subagent "$SUBAGENT_TYPE" \
      '{ts:$ts,event:"completion-protocol-missing",tool:$tool,subagent:$subagent}')
    log_event "$EVT"
  fi
  exit 0
fi

STATE=$(printf '%s' "$STATUS_LINE" | sed -E 's/^[[:space:]]*STATUS:[[:space:]]+([A-Z_]+).*$/\1/')

case "$STATE" in
  BLOCKED|NEEDS_CONTEXT)
    HAS_REASON=$(printf '%s\n' "$RESPONSE" | grep -cE '^[[:space:]]*REASON:' || true)
    HAS_ATTEMPTED=$(printf '%s\n' "$RESPONSE" | grep -cE '^[[:space:]]*ATTEMPTED:' || true)
    HAS_RECO=$(printf '%s\n' "$RESPONSE" | grep -cE '^[[:space:]]*RECOMMENDATION:' || true)
    MISSING=""
    [ "$HAS_REASON" = "0" ] && MISSING="$MISSING REASON"
    [ "$HAS_ATTEMPTED" = "0" ] && MISSING="$MISSING ATTEMPTED"
    [ "$HAS_RECO" = "0" ] && MISSING="$MISSING RECOMMENDATION"

    if [ -n "$MISSING" ]; then
      TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      {
        echo "PROTO-022: STATUS: $STATE requires escalation block but missing:$MISSING"
        echo "  (SOFT warning — exit 0)"
      } >&2
      if command -v jq >/dev/null 2>&1; then
        EVT=$(jq -nc --arg ts "$TS" --arg state "$STATE" --arg missing "${MISSING# }" \
          --arg tool "$TOOL_NAME" --arg subagent "$SUBAGENT_TYPE" \
          '{ts:$ts,event:"completion-protocol-incomplete-escalation",state:$state,missing:$missing,tool:$tool,subagent:$subagent}')
        log_event "$EVT"
      fi
      exit 0
    fi
    ;;
esac

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if command -v jq >/dev/null 2>&1; then
  EVT=$(jq -nc --arg ts "$TS" --arg state "$STATE" --arg tool "$TOOL_NAME" --arg subagent "$SUBAGENT_TYPE" \
    '{ts:$ts,event:"completion-protocol-ok",state:$state,tool:$tool,subagent:$subagent}')
  log_event "$EVT"
fi

exit 0
