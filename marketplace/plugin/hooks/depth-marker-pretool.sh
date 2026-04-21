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

# All profiles emit the same reminder text
cat <<'EOF' >&2
⚠ Sutra: no depth marker found. Emit a Depth + Estimation block before Edit/Write.

Required format:
  TASK: "..."
  DEPTH: X/5 (surface|considered|thorough|rigorous|exhaustive)
  EFFORT: ..., ...
  COST: ~$X
  IMPACT: ...

Then write the marker:
  mkdir -p .claude && echo "DEPTH=N TASK=<slug> TS=$(date +%s)" > .claude/depth-registered

Escape hatch (one-shot): run the command with SUTRA_BYPASS=1 prefix.
EOF

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
