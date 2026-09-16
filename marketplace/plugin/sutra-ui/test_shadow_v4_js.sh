#!/usr/bin/env bash
# test_shadow_v4_js.sh -- run every Shadow v4 screen lane (node vm scripts).
#
# The JS suites are plain `node test_x.js` scripts (no jsdom, no framework);
# run-tests.sh only knows the Python lanes, so the v4 build gets this one
# runner for its JS lanes. Exit 1 on any failing lane, or when no lane exists
# yet (a verify that passes on nothing proves nothing).
#
# Usage:
#   sutra/marketplace/plugin/sutra-ui/test_shadow_v4_js.sh            # all v4 lanes
#   sutra/marketplace/plugin/sutra-ui/test_shadow_v4_js.sh prose      # lanes matching a word
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2
command -v node >/dev/null 2>&1 || { echo "test_shadow_v4_js: node is not on PATH" >&2; exit 2; }

shopt -s nullglob
lanes=(test_shadow_v4_*${1:-}*.js)
if [ ${#lanes[@]} -eq 0 ]; then
  echo "test_shadow_v4_js: no test_shadow_v4_*.js lane found" >&2
  exit 1
fi

fail=0
for t in "${lanes[@]}"; do
  log="$(mktemp -t shadow-v4-js.XXXXXX)"
  if node "$t" > "$log" 2>&1; then
    printf '%-34s PASS  %s\n' "$t" "$(grep -c '^ok ' "$log") checks"
  else
    printf '%-34s FAIL\n' "$t"
    sed 's/^/    /' "$log" | tail -n 30
    fail=1
  fi
  rm -f "$log"
done
exit $fail
