#!/usr/bin/env bash
# phase-exit-audit.sh — L2 PHASE-EXIT-VERIFY audit-only Stop hook (V1)
#
# Founder direction 2026-05-12: "verify at each phase".
# Codex + DeepSeek convergent verdict (DIRECTIVE-ID 1778573655):
# audit-only, no mid-turn block. Gather 1-2 weeks data before deciding on
# narrowed HARD enforcement.
# Verdict: .enforcement/codex-reviews/2026-05-12-l2-enforcement-design.md
#
# Fires: Stop event. NEVER blocks. D3+ only.
# Logs:  .enforcement/phase-exit-audit.jsonl
# Kill:  PHASE_EXIT_AUDIT_DISABLED=1 OR ~/.phase-exit-audit-disabled

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$REPO_ROOT" || exit 0

[ -n "${PHASE_EXIT_AUDIT_DISABLED:-}" ] && exit 0
[ -f "$HOME/.phase-exit-audit-disabled" ] && exit 0

STDIN_RAW="$(cat 2>/dev/null)"
SESSION_ID=""
TRANSCRIPT_PATH=""
if command -v jq >/dev/null 2>&1 && [ -n "$STDIN_RAW" ]; then
  SESSION_ID=$(printf '%s' "$STDIN_RAW" | jq -r '.session_id // empty' 2>/dev/null)
  TRANSCRIPT_PATH=$(printf '%s' "$STDIN_RAW" | jq -r '.transcript_path // empty' 2>/dev/null)
fi

DEPTH=""
if [ -f ".claude/depth-registered" ]; then
  _LA=$(grep -E '^DEPTH=[0-9]+[[:space:]]+TASK=[^[:space:]]+[[:space:]]+TS=[0-9]+$' .claude/depth-registered 2>/dev/null | head -1)
  if [ -n "$_LA" ]; then
    DEPTH=$(printf '%s' "$_LA" | sed -E 's/^DEPTH=([0-9]+).*$/\1/')
  else
    _LB=$(grep -E '^DEPTH=[0-9]+$' .claude/depth-registered 2>/dev/null | head -1)
    [ -n "$_LB" ] && DEPTH=$(printf '%s' "$_LB" | sed -E 's/^DEPTH=([0-9]+)$/\1/')
  fi
fi
case "$DEPTH" in ''|*[!0-9]*) DEPTH=5 ;; esac

if [ "$DEPTH" -lt 3 ] 2>/dev/null; then
  exit 0
fi

TS=$(date +%s)
mkdir -p .enforcement 2>/dev/null

PHASES_EMITTED=""
PHASES_MISSING=""
TRANSCRIPT_STATUS="ok"
RESPONSE_TEXT=""

if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ] && command -v jq >/dev/null 2>&1; then
  RESPONSE_TEXT=$(jq -r 'select(.role=="assistant") | (.content // "")' "$TRANSCRIPT_PATH" 2>/dev/null | tail -c 200000 | tr '\n' ' ')
  [ -z "$RESPONSE_TEXT" ] && TRANSCRIPT_STATUS="empty"
else
  TRANSCRIPT_STATUS="unavailable"
fi

for PHASE in OBJECTIVE OBSERVE SHAPE PLAN EXECUTE MEASURE LEARN; do
  if [ -n "$RESPONSE_TEXT" ] && printf '%s' "$RESPONSE_TEXT" | grep -qE "PHASE[- ]${PHASE}\b|\b${PHASE}:|## ${PHASE}\b|\*\*${PHASE}\*\*"; then
    PHASES_EMITTED="${PHASES_EMITTED}${PHASE},"
  else
    PHASES_MISSING="${PHASES_MISSING}${PHASE},"
  fi
done

COMPRESSION_INFERRED="unknown"
if [ -f ".claude/blueprint-registered" ] && grep -q '^HAS_PER_STEP_VERIFY=1$' .claude/blueprint-registered 2>/dev/null; then
  MC=$(printf '%s' "$PHASES_MISSING" | tr ',' '\n' | grep -c .)
  if [ "${MC:-0}" -ge 4 ] 2>/dev/null; then COMPRESSION_INFERRED="yes"; else COMPRESSION_INFERRED="no"; fi
fi

SS=$(printf '%s' "$SESSION_ID" | tr -d '"\\' | tr '\n\r' '  ' | head -c 64)
SE=$(printf '%s' "$PHASES_EMITTED" | tr -d '"\\')
SM=$(printf '%s' "$PHASES_MISSING" | tr -d '"\\')
printf '{"ts":%s,"session_id":"%s","depth":%s,"phases_emitted":"%s","phases_missing":"%s","compression_inferred":"%s","transcript_status":"%s"}\n' \
  "$TS" "$SS" "$DEPTH" "$SE" "$SM" "$COMPRESSION_INFERRED" "$TRANSCRIPT_STATUS" \
  >> .enforcement/phase-exit-audit.jsonl 2>/dev/null

exit 0

## Operationalization
#
### 1. Measurement mechanism
# .enforcement/phase-exit-audit.jsonl per-turn rows.
#
### 2. Adoption mechanism
# Plugin Stop hook (hooks.json). Default ON.
#
### 3. Monitoring / escalation
# Warn: phase-skip >30% on D4+. Breach: transcript_status="unavailable" >50%.
#
### 4. Iteration trigger
# 1-2 weeks data: if PLAN->EXECUTE or EXECUTE->MEASURE skip correlates
# with bad outcomes, promote to narrowed HARD. NEVER promote
# OBSERVE/SHAPE/LEARN.
#
### 5. DRI
# CEO of Asawa (Sutra Forge).
#
### 6. Decommission criteria
# (a) data validates narrowed HARD (replace), (b) 30d benign (close),
# (c) runtime adopts different verification arch.
