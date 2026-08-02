#!/bin/bash
# Sutra: depth-marker pretool hook.
# Behavior depends on the active profile (set by /core:start):
#
#   individual  — warn-only, never block. Default.
#   project     — warn-only.
#   company     — HARD: exit 2 on missing marker (blocks the tool call).
#
# Profile is read from .claude/sutra-project.json; defaults to individual.
#
# Escape hatch (even on company): set SUTRA_BYPASS=1 to skip the check
# for a single tool call.
#
# 2026-07-30 (marker-race fix, root-cause doc §2 depth-registered row):
# depth-registered is read via marker-lib — session dir
# .claude/sessions/<sid>/ first, with self-only adoption of an unstamped or
# self-stamped legacy global. A foreign-stamped global (a concurrent session's
# depth) can no longer satisfy this gate. The legacy path is the fallback only
# when the lib itself is unavailable.

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
MARKER="$PROJECT_ROOT/.claude/depth-registered"
CONFIG="$PROJECT_ROOT/.claude/sutra-project.json"

# Respect explicit bypass
if [ "${SUTRA_BYPASS:-}" = "1" ]; then
  exit 0
fi

# Read the PreToolUse stdin JSON up front (2026-07-30): both the session-id
# resolution (marker-lib) and the bootstrap whitelist below need it.
_STDIN_PAYLOAD="$(cat 2>/dev/null)"

# Session-scoped marker read via marker-lib (defensive sourcing, flow-gate.sh
# pattern): on lib failure degrade to the legacy path — the gate must never
# block because its own infrastructure errored.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  . "$_MARKER_LIB" 2>/dev/null || true
  command -v sutra_sid_from_stdin >/dev/null 2>&1 && { sutra_sid_from_stdin "$_STDIN_PAYLOAD" || true; }
fi

_depth_marker_present() {
  if command -v sutra_marker_read >/dev/null 2>&1; then
    sutra_marker_read depth-registered >/dev/null 2>&1; return $?
  fi
  # lib missing: legacy global (fail-open on infrastructure, not on discipline)
  [ -f "$MARKER" ]
}

# Marker present — nothing to enforce
if _depth_marker_present; then
  exit 0
fi

# ── Governance-state whitelist (2026-07-27 bootstrap-deadlock fix) ──────────
# The per-turn markers themselves live under .claude/ and .enforcement/.
# Gating those writes on a depth marker is circular: the model cannot write
# .claude/depth-registered because .claude/depth-registered is missing.
# Observed live 2026-07-27: a Write of .claude/flow-classified was blocked
# here, which is also why flow-gate / flow-stop-check then fired on turns that
# had in fact walked the spine. Governance state is never substantive work.
if [ -n "$_STDIN_PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  _FILE_PATH=$(printf '%s' "$_STDIN_PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
  if [ -n "$_FILE_PATH" ]; then
    _REL="${_FILE_PATH#"$PROJECT_ROOT"/}"
    # Scoped to the exact per-turn marker set — NOT a blanket .claude/* pass.
    # A blanket pass would also unblock .claude/CLAUDE.md and
    # .claude/settings.json, i.e. the files that define the agent's own
    # governance, letting turn 0 rewrite the contract and escape every later
    # depth check. (DeepSeek consult 2026-07-27, finding 3a.)
    # .claude/sessions/* is the Scheme A session-scoped marker home
    # (marker-lib) — same governance-state class, same bootstrap-deadlock
    # rationale (2026-07-30 marker-race fix, migration plan Phase 3).
    case "$_REL" in
      .claude/depth-registered|.claude/depth-assessed|\
      .claude/input-routed|.claude/blueprint-registered|\
      .claude/build-layer-registered|.claude/codex-consulted|\
      .claude/estimation-logged|.claude/structure-first-active|\
      .claude/sutra-deploy-depth5|.claude/.last-reset-ts|\
      .claude/flow-classified|.claude/flow-classified-*|\
      .claude/flow-type-resolved|.claude/flow-type-resolved-*|\
      .claude/flow-inner|.claude/flow-closed|\
      .claude/sessions/*|\
      .claude/codex-directive-pending-*|.claude/heartbeats/*|\
      .enforcement/*|.analytics/*) exit 0 ;;
    esac
  fi
fi

# Read profile from project config; default to individual
PROFILE="individual"
if [ -f "$CONFIG" ]; then
  if command -v jq >/dev/null 2>&1; then
    _PROFILE_READ=$(jq -r '.profile // empty' "$CONFIG" 2>/dev/null)
  else
    _PROFILE_READ=$(sed -n 's/.*"profile"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -1)
  fi
  [ -n "$_PROFILE_READ" ] && PROFILE="$_PROFILE_READ"
fi

# v2.1 PEDAGOGY charter — level-aware explanation.
# SUTRA_LEVEL: novice | apprentice | journeyman | master (env or ~/.sutra/level).
# Default = master (terse one-line warn). Apprentice/novice are opt-in via
# `sutra learn` flow or explicit ~/.sutra/level write — they emit verbose
# stderr that's overwhelming to customers who haven't asked to be taught.
SUTRA_LEVEL="${SUTRA_LEVEL:-}"
if [ -z "$SUTRA_LEVEL" ] && [ -f "$HOME/.sutra/level" ]; then
  SUTRA_LEVEL=$(head -1 "$HOME/.sutra/level" 2>/dev/null | tr -d '[:space:]')
fi
SUTRA_LEVEL="${SUTRA_LEVEL:-master}"

case "$SUTRA_LEVEL" in
  novice)
    cat <<'EOF' >&2
⚠ Sutra: no depth marker found.

WHY THIS MATTERS
  Sutra asks you to rate every task's depth (1-5) BEFORE you act on it.
  This is the single biggest discipline the OS enforces — because visible
  choices get examined, and examined choices get better.

  Over-triage (D5 for a one-line fix) = wastes attention.
  Under-triage (D1 for a cross-cutting migration) = breaks production.

  Writing the depth down before acting forces the choice.

THE FORMAT
  TASK: "..."
  DEPTH: X/5 (surface | considered | thorough | rigorous | exhaustive)
  EFFORT: time est., files est.
  COST: ~$X
  IMPACT: who/what changes

THEN WRITE THE MARKER
  mkdir -p .claude && echo "DEPTH=N TASK=<slug> TS=$(date +%s)" > .claude/depth-registered

ESCAPE HATCH (one-shot)
  SUTRA_BYPASS=1 <your-command>

LEARN MORE
  sutra learn depth

YOUR LEVEL
  SUTRA_LEVEL=novice — this verbose explanation will fire until you
  set SUTRA_LEVEL=apprentice (env) or echo apprentice > ~/.sutra/level.
EOF
    ;;
  master)
    echo "⚠ missing depth marker (SUTRA_BYPASS=1 overrides)" >&2
    ;;
  *)
    cat <<'EOF' >&2
⚠ Sutra: no depth marker found. Emit Depth + Estimation block before Edit/Write.

Required:
  TASK: "..."
  DEPTH: X/5
  EFFORT: ..., ...
  COST: ~$X
  IMPACT: ...

Write marker: mkdir -p .claude && echo "DEPTH=N TASK=<slug> TS=$(date +%s)" > .claude/depth-registered
Escape: SUTRA_BYPASS=1 prefix.
EOF
    ;;
esac

# Company profile: HARD block. Others: soft warn.
case "$PROFILE" in
  company)
    echo "" >&2
    echo "❌ BLOCKED — profile=company requires a depth marker before every Edit/Write." >&2
    exit 2
    ;;
  *)
    # individual, project, or unknown → warn-only
    exit 0
    ;;
esac
