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

# Lanes red on origin/main BEFORE this branch (step 19, 2026-09-16), each with
# the anchor that fails there. They are reported, never counted against v4;
# remove a row the day its owner fixes it upstream.
#   test_app.py            2 TestChatsAreSutrasOwn rows leak terminal fixtures
#                          (2.280.3 Setup screens; owner session b7)
#   test_attach_existing.py D5 early `DELEGATES[sid] = rt` at spawn
#                          (shadow_runner.py:2007 on main); D8 the decide
#                          prompt text sits inside the ensure_runtime slice
UPSTREAM_RED="test_app.py test_attach_existing.py"

echo "== python lanes"
if ! ./run-tests.sh > /tmp/verify-shadow-v4-py.log 2>&1; then
  while read -r lane _; do
    case " $UPSTREAM_RED " in
      *" $lane "*) printf '%-34s red on origin/main, not this branch\n' "$lane" ;;
      *) printf '%-34s FAIL\n' "$lane"; fail=1 ;;
    esac
  done < <(grep -E "^\S+\.py\s+(FAIL|ERROR)" /tmp/verify-shadow-v4-py.log)
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
