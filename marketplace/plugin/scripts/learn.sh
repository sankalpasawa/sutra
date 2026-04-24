#!/bin/bash
# sutra/marketplace/plugin/scripts/learn.sh
# Sutra v2.1 — /sutra learn interactive tutor.
# Pedagogy charter v1.0 §Primitives #2.

set -u
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LESSONS_DIR="$PLUGIN_ROOT/skills/sutra-learn/lessons"

if [ ! -d "$LESSONS_DIR" ]; then
  echo "sutra learn: lessons directory not found at $LESSONS_DIR" >&2
  exit 1
fi

_list() {
  cat <<'LESSONS_EOF'
Sutra — Learn mode

Available lessons:

  1. depth        Understand DEPTH 1-5 and why every task gets assessed
  2. routing      Input Routing: how Sutra classifies what you say
  3. charters     The 5 charters and what each one governs
  4. hooks        How plugin hooks protect you (and when to override)
  5. build-layer  L0 / L1 / L2 — where code lives and why

Usage:
  sutra learn <topic>     e.g. sutra learn depth
  sutra learn --all       print all 5 in order

Each lesson is ~2 minutes. Start with depth — it anchors everything else.
LESSONS_EOF
}

_print() {
  local topic="$1"
  local file="$LESSONS_DIR/${topic}.md"
  if [ ! -f "$file" ]; then
    echo "sutra learn: no lesson named '$topic'" >&2
    echo "Available: depth, routing, charters, hooks, build-layer" >&2
    return 1
  fi
  cat "$file"
  echo ""
}

case "${1:-}" in
  ""|help|--help|-h)
    _list
    ;;
  --all)
    for t in depth routing charters hooks build-layer; do
      echo "═══════════════════════════════════════════════════════════════"
      _print "$t"
    done
    ;;
  *)
    _print "$1" || exit 1
    ;;
esac
exit 0
