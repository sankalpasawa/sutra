#!/usr/bin/env bash
# The merge gate: every test in this checkout, Python and JavaScript. Exit 0 only when all pass.
# Usage: scripts/gate.sh [pytest args]     (run it inside any worktree; it tests that worktree's code)
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
cd "$HERE"
"$HERE/scripts/py" -m pytest "$@"   # pyproject addopts already has -q: a second one would hide the summary line
if ls tests/js/*.mjs >/dev/null 2>&1; then
  for f in tests/js/*.mjs; do
    echo "node $f"
    node "$f"
  done
fi
# the desktop app's own tests, when its dependencies are installed (CI installs them in its `desktop` job: npm ci --ignore-scripts in desktop/)
if [ -d desktop/node_modules ]; then
  echo "npm test (desktop)"
  (cd desktop && npm test)
fi
echo "gate: ok"
