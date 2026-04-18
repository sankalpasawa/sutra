#!/bin/bash
# Sutra: depth-marker pretool hook (warn-only in v0.1).
# Reminds the model to emit a depth block before Edit/Write if no marker exists.
# Does NOT block. Hard enforcement deferred to v0.2.

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
MARKER="$PROJECT_ROOT/.claude/depth-registered"

if [ ! -f "$MARKER" ]; then
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
EOF
fi

exit 0
