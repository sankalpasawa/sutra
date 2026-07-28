#!/bin/bash
# flow-stop-check.sh -- Stop-event FLOOR for D61 Flow firing.
#
# Canon:   holding/FOUNDER-DIRECTIONS.md §D61 (2026-06-14)
# Skill:   sutra/marketplace/plugin/skills/flow/SKILL.md (core:flow)
# Event:   Stop (end of every assistant turn)
# Enforcement: profile-gated (2026-06-19, was unconditional HARD 2026-06-14).
#   profile=company        -> HARD redo (force one redo on miss)
#   individual/project/etc -> warn+log, NO redo
# FAIL-OPEN BY DESIGN: when sutra-project.json is absent OR jq is unavailable,
# profile defaults to "individual" => WARN. HARD is opt-in via profile=company;
# there is intentionally no fail-closed default (founder: minimize forced redos).
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
# Session-scoped first, legacy single-slot as fallback (2026-07-27). Before
# this, a peer session's reset could delete the single-slot marker mid-turn and
# this hook would force a redo on a turn that HAD fired — observed live
# 2026-07-27 (session c2360700 cleared markers while e52b2379 was mid-work).
# Scheme A (marker-lib) is the single marker authority as of 2026-07-27; the flat
# `.claude/flow-classified-<sid>` suffix scheme this hook briefly read is DELETED.
# Sourced defensively — see flow-gate.sh (DeepSeek consult 2026-07-27, finding 4).
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" || true
  sutra_sid_from_stdin "$STDIN_PAYLOAD" || true
  set -u
  if command -v sutra_marker_has >/dev/null 2>&1; then
    sutra_marker_has flow-classified && exit 0
  elif [ -f "$REPO_ROOT/.claude/flow-classified" ]; then
    exit 0
  fi
elif [ -f "$REPO_ROOT/.claude/flow-classified" ]; then
  # lib missing: legacy global only (fail-open on infrastructure, not on discipline)
  exit 0
fi

# -- Honor the project enforce profile (2026-06-19, founder-directed) -------
# Mirrors h-sutra-enforce.sh v9 + the depth-marker profile convention: the Stop
# layers were the only ones ignoring .profile. profile=company keeps the HARD
# redo; individual/project/unknown get warn+log, NO forced redo. Banner's
# "Enforce: warn-only" becomes true for the loud layers too.
FL_PROFILE="individual"
FL_CONFIG="$REPO_ROOT/.claude/sutra-project.json"
if [ -f "$FL_CONFIG" ] && command -v jq >/dev/null 2>&1; then
  _fp=$(jq -r '.profile // empty' "$FL_CONFIG" 2>/dev/null)
  _fp=$(printf '%s' "$_fp" | tr -cd 'a-zA-Z0-9_-')   # profile is a bare token; strip anything else so it can't break the ledger JSON
  [ -n "$_fp" ] && FL_PROFILE="$_fp"
fi
if [ "$FL_PROFILE" != "company" ]; then
  printf '{"ts":"%s","event":"flow-stop-warn","session":"%s","reason":"flow-did-not-fire","mode":"warn","profile":"%s"}\n' \
    "$NOW" "$SESSION_ID" "$FL_PROFILE" >> "$LEDGER" 2>/dev/null
  printf 'FLOW (warn, profile=%s): core:flow did not fire this turn. Walk the spine next turn (no redo forced).\n' "$FL_PROFILE" >&2
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
