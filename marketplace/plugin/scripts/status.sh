#!/bin/bash
# Sutra plugin — /sutra-status logic as standalone script.
# Prints project IDs, queue depth, opt-in flag, last flush marker.

set -u

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(realpath "$0")")")}"
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

source "$PLUGIN_ROOT/lib/queue.sh"

cd "$PROJECT_ROOT"

echo "── Sutra plugin status ────────────────────────────────────"

# v2.18.0 (2026-05-03): jq replaces python3 for sutra-project.json read.
# Status is display-only — graceful "(jq missing)" line if jq unavailable
# rather than hard-fail. Matches start.sh v2.13.0 EDR-killed-python3 fix.
if [ -f .claude/sutra-project.json ]; then
  if command -v jq >/dev/null 2>&1; then
    jq -r 'to_entries[] | "  \(.key | . + (" " * (20 - length))) \(.value)"' .claude/sutra-project.json 2>/dev/null \
      || echo "  (jq parse failed — sutra-project.json may be corrupt)"
  else
    echo "  (jq missing — install: brew install jq / apt-get install jq)"
  fi
else
  echo "  (no .claude/sutra-project.json — run /sutra-onboard)"
fi

# Telemetry kill-switch state — surface explicitly so user understands transport behavior
if [ "${SUTRA_TELEMETRY:-1}" = "0" ]; then
  echo ""
  echo "  ⚠ SUTRA_TELEMETRY=0 — capture and push are both DISABLED"
fi

echo ""
echo "  queue_file           $(queue_file)"
echo "  queue_depth          $(queue_count)"

if [ -f "$SUTRA_HOME/last-flush.txt" ]; then
  echo ""
  sed 's/^/  /' "$SUTRA_HOME/last-flush.txt"
fi

echo "───────────────────────────────────────────────────────────"
