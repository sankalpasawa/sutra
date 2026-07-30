#!/bin/bash
# placement-lint.sh — grounding rung 5. The gate checks a placement EXISTS;
# this separate pass checks it is TRUE (refs resolve, origin legal, engine-
# written). One advisory line on problems; silent when clean; never blocks.
set -u
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0
[ -f "$REPO_ROOT/.claude/placement-disabled" ] && exit 0
[ -f "$HOME/.placement-disabled" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT=$(cd "$REPO_ROOT" && CLAUDE_PROJECT_DIR="$REPO_ROOT" python3 "$PLUGIN_DIR/lib/placement_engine.py" lint 2>/dev/null)
OK=$(printf '%s' "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin).get('ok'))" 2>/dev/null)
if [ "$OK" = "False" ]; then
  N=$(printf '%s' "$OUT" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['issues']))" 2>/dev/null)
  FIRST=$(printf '%s' "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['issues'][0])" 2>/dev/null)
  printf 'PLACEMENT-LINT (advisory): %s grounding issue(s); first: %s\n' "${N:-?}" "${FIRST:-?}" >&2
fi
exit 0
