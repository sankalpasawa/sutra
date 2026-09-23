#!/usr/bin/env bash
# test_chat_pill.sh -- the combined governance + runtime pill (2026-09-23).
#
# The pill replaced the governance chip, the activity fold, the verdict and
# meta pills and the live loader in the turn renderer, and it changes the click
# path and the founder turn's side. Its verify is the new pin file PLUS every
# suite that pins those same functions or that surface. Exit 1 on any failing lane.
#
# Usage:
#   sutra/marketplace/plugin/sutra-ui/test_chat_pill.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2
command -v node >/dev/null 2>&1 || { echo "test_chat_pill: node is not on PATH" >&2; exit 2; }

rc=0
for lane in test_chat_pill.js test_panel.js test_chat_condense.js test_composer_tools.js \
            test_governance.js test_gov_capture.js test_agents.js test_chat_chrome.js; do
  if [ ! -f "$lane" ]; then echo "test_chat_pill: missing lane $lane" >&2; rc=1; continue; fi
  printf '== %-26s ' "$lane"
  out=$(node "$lane" 2>&1 </dev/null); lrc=$?
  echo "$out" | tail -1
  [ $lrc -eq 0 ] || { rc=1; echo "$out" | grep -E '^FAIL' | head -5; }
done
exit $rc
