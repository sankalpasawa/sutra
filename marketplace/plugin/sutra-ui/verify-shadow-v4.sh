#!/usr/bin/env bash
# verify-shadow-v4.sh -- the one check for the Shadow v4 program (BUILD-PLAN-V4
# step 18): every Python lane through run-tests.sh, every Shadow JS suite
# through node, and the v4 JS runner. The eval pack (evals/run_shadow_v4.py)
# is paid and slow, so it runs only with SHADOW_EVALS=1.
#
# Usage: sutra/marketplace/plugin/sutra-ui/verify-shadow-v4.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2
fail=0

echo "== python lanes"
if ! ./run-tests.sh > /tmp/verify-shadow-v4-py.log 2>&1; then
  grep -E "^\S+\.py\s+(FAIL|ERROR)" /tmp/verify-shadow-v4-py.log
  fail=1
fi
grep -c "PASS" /tmp/verify-shadow-v4-py.log | sed 's/^/python lanes green: /'

echo "== shadow, goal, governance and panel JS suites"
for t in test_shadow_*.js test_goal_*.js test_governance.js test_panel.js test_nav.js; do
  [ -f "$t" ] || continue
  case "$t" in test_shadow_v4_*) continue ;; esac
  if ! node "$t" > /tmp/verify-shadow-v4-js.log 2>&1; then
    printf '%-34s FAIL\n' "$t"; tail -n 6 /tmp/verify-shadow-v4-js.log | sed 's/^/    /'; fail=1
  fi
done

echo "== v4 JS lanes"
./test_shadow_v4_js.sh || fail=1

if [ "${SHADOW_EVALS:-0}" = "1" ]; then
  echo "== eval pack (real claude)"
  PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
  "$PY" evals/run_shadow_v4.py || fail=1
fi

if [ "$fail" = "0" ]; then echo "verify-shadow-v4: PASS"; else echo "verify-shadow-v4: FAIL"; fi
exit $fail
