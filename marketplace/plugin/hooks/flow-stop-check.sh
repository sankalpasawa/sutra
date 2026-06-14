#!/bin/bash
# flow-stop-check.sh -- Stop-event FLOOR for D61 Flow firing.
#
# Canon:   holding/FOUNDER-DIRECTIONS.md §D61 (2026-06-14)
# Skill:   sutra/marketplace/plugin/skills/flow/SKILL.md (core:flow)
# Event:   Stop (end of every assistant turn)
# Enforcement: HARD, fleet-wide (founder direction 2026-06-14, "HARD fleet-wide now").
#
# Why a Stop hook: D61 requires core:flow to FIRE on EVERY input, including pure
# no-tool turns (a one-line answer, a yes/no, chitchat). PreToolUse gates
# (flow-gate.sh) cannot catch those -- no tool fires to gate. The Stop event is
# the only place to floor a no-tool turn. At turn-end, if the Flow classify
# marker is absent (the per-turn reset wipes .claude/flow-classified at
# UserPromptSubmit), Flow did not fire -> force a redo.
#
# LOOP SAFETY (non-negotiable): honors Claude Code's stop_hook_active flag. The
# FIRST Stop where flow didn't fire blocks (forces one redo); on the re-invoked
# turn stop_hook_active=true and this hook PASSES. So a client can never
# infinite-loop, even if a marker write fails (e.g. the sandbox-revert class of
# bug). Net behavior: every miss gets exactly one forced redo, then proceeds.
#
# Kill-switch (shared with the Flow family):
#   - FLOW_DISABLED=1            (per-shell env)
#   - $HOME/.flow-disabled       (per-machine fs)
# Override (per-turn, audit-logged):
#   - FLOW_ACK=1 FLOW_ACK_REASON='<why>'
#
# Composes with (does NOT duplicate) flow-gate.sh: flow-gate floors MUTATIONS
# (PreToolUse Edit/Write + Task/Agent); this hook floors NO-TOOL turns (Stop).
# Together they make Flow fire on every input.

set -u

# -- Kill-switches (either bypasses) ---------------------------------------
[ -n "${FLOW_DISABLED:-}" ] && exit 0
[ -f "$HOME/.flow-disabled" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -z "$REPO_ROOT" ] && exit 0
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
LEDGER="$REPO_ROOT/.enforcement/flow-gate.jsonl"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

STDIN_PAYLOAD=""
[ ! -t 0 ] && STDIN_PAYLOAD="$(cat 2>/dev/null || true)"

SESSION_ID="unknown"
ACTIVE="false"
if command -v jq >/dev/null 2>&1 && [ -n "$STDIN_PAYLOAD" ]; then
  SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null)
  ACTIVE=$(printf '%s'   "$STDIN_PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
fi

# -- Override (FLOW_ACK=1 -> audit-log + pass) -----------------------------
if [ "${FLOW_ACK:-0}" = "1" ]; then
  REASON=$(printf '%s' "${FLOW_ACK_REASON:-no-reason}" | tr -d '\n\r' | head -c 300)
  printf '{"ts":"%s","event":"flow-stop-override","session":"%s","reason":"%s"}\n' \
    "$NOW" "$SESSION_ID" "$REASON" >> "$LEDGER" 2>/dev/null
  exit 0
fi

# -- Loop-breaker: already forced one redo this turn -> PASS (never trap) ---
if [ "$ACTIVE" = "true" ]; then
  printf '{"ts":"%s","event":"flow-stop-skip","session":"%s","reason":"stop_hook_active"}\n' \
    "$NOW" "$SESSION_ID" >> "$LEDGER" 2>/dev/null
  exit 0
fi

# -- Flow fired this turn iff the classify marker exists --------------------
if [ -f "$REPO_ROOT/.claude/flow-classified" ]; then
  exit 0
fi

# -- Missing: Flow did not fire -> force exactly one redo (HARD, D61) -------
printf '{"ts":"%s","event":"flow-stop-block","session":"%s","reason":"flow-did-not-fire","mode":"hard"}\n' \
  "$NOW" "$SESSION_ID" >> "$LEDGER" 2>/dev/null

cat <<'JSON'
{
  "decision": "block",
  "reason": "FLOW layer FIRED (D61).\n\ncore:flow did not fire this turn -- no .claude/flow-classified marker. Per D61 the FULL core:flow spine runs on EVERY input (the way Input Routing fires every turn), including no-tool turns.\n\nWalk it now: invoke core:flow -> classify -> resolve a workflow type -> FOLLOW/CONSTRUCT -> inner engine -> Work-Atom -> close, writing the .claude/flow-* markers as you go. Then end the turn.\n\nIf the omission is intentional: FLOW_ACK=1 FLOW_ACK_REASON='<why>' (or FLOW_DISABLED=1 / touch ~/.flow-disabled)."
}
JSON
exit 0
