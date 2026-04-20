#!/bin/bash
# Sutra plugin — /sutra-status logic as standalone script.
# Prints project IDs, queue depth, opt-in flag, last flush marker.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

source "$PLUGIN_ROOT/lib/queue.sh"

cd "$PROJECT_ROOT"

echo "── Sutra plugin status ────────────────────────────────────"

if [ -f .claude/sutra-project.json ]; then
  python3 -c "
import json
d = json.load(open('.claude/sutra-project.json'))
for k,v in d.items():
    print(f'  {k:20s} {v}')
" 2>/dev/null
else
  echo "  (no .claude/sutra-project.json — run /sutra-onboard)"
fi

echo ""
echo "  queue_file           $(queue_file)"
echo "  queue_depth          $(queue_count)"

if [ -f "$SUTRA_HOME/last-flush.txt" ]; then
  echo ""
  sed 's/^/  /' "$SUTRA_HOME/last-flush.txt"
fi

echo "───────────────────────────────────────────────────────────"
