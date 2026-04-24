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

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
MARKER="$PROJECT_ROOT/.claude/depth-registered"
CONFIG="$PROJECT_ROOT/.claude/sutra-project.json"

# Respect explicit bypass
if [ "${SUTRA_BYPASS:-}" = "1" ]; then
  exit 0
fi

# Marker present — nothing to enforce
if [ -f "$MARKER" ]; then
  exit 0
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
SUTRA_LEVEL="${SUTRA_LEVEL:-}"
if [ -z "$SUTRA_LEVEL" ] && [ -f "$HOME/.sutra/level" ]; then
  SUTRA_LEVEL=$(head -1 "$HOME/.sutra/level" 2>/dev/null | tr -d '[:space:]')
fi
SUTRA_LEVEL="${SUTRA_LEVEL:-apprentice}"

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
