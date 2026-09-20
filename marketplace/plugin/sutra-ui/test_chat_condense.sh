#!/usr/bin/env bash
# test_chat_condense.sh -- the chat activity-fold lanes (node vm scripts).
#
# The fold (one row per turn in place of a card per tool call, 2026-09-21)
# touches the turn renderer, the tool cards and the delegated click handler,
# so its verify is the new pin file PLUS the three suites that pin the older
# shape of those same functions. Exit 1 on any failing lane.
#
# Usage:
#   sutra/marketplace/plugin/sutra-ui/test_chat_condense.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2
command -v node >/dev/null 2>&1 || { echo "test_chat_condense: node is not on PATH" >&2; exit 2; }

rc=0
for lane in test_chat_condense.js test_composer_tools.js test_panel.js test_chat_chrome.js; do
  if [ ! -f "$lane" ]; then echo "test_chat_condense: missing lane $lane" >&2; rc=1; continue; fi
  echo "== $lane"
  node "$lane" || rc=1
done
exit $rc
