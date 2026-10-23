#!/usr/bin/env bash
# Run sutra-ui tests on an interpreter that actually has the app's deps.
#
# Why this exists: the app targets Python 3.11 and needs fastapi + websockets.
# System `python3` on macOS is 3.9 with neither, so three test lanes fail with
# ModuleNotFoundError / "asyncio.Event() needs a running loop" and get
# misread as product defects (JOURNEY-TESTS.md section 5 records exactly that
# mistake). Naming an absolute interpreter path in a command is also refused by
# the dispatch envelope, which by design rejects absolute declared entries
# (holding/hooks/lib/touches-match.sh). So the resolution lives HERE, in a
# repo-relative script, and callers invoke a path inside the work envelope.
#
# Usage:
#   sutra/marketplace/plugin/sutra-ui/run-tests.sh                 # all lanes
#   sutra/marketplace/plugin/sutra-ui/run-tests.sh test_shadow_floor_choke.py
#   sutra/marketplace/plugin/sutra-ui/run-tests.sh --which          # print interp
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Candidates, most-preferred first. A local .venv wins so a developer can pin
# their own; the shipped app payload is the reliable fallback.
CANDIDATES=(
  "$HERE/.venv/bin/python"
  "$HERE/.venv/bin/python3"
  "/Applications/Sutra.app/Contents/Resources/payload/python/bin/python3"
  "$HOME/Applications/Sutra.app/Contents/Resources/payload/python/bin/python3"
  "$HOME/.local/bin/python3.11"
)

PY=""
for c in "${CANDIDATES[@]}"; do
  [ -x "$c" ] || continue
  # Require the deps, not just the version -- a 3.11 without fastapi is no use.
  if "$c" -c 'import fastapi' >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "run-tests.sh: no interpreter with fastapi found. Tried:" >&2
  printf '  %s\n' "${CANDIDATES[@]}" >&2
  echo "Install deps into $HERE/.venv, or install Sutra.app." >&2
  exit 3
fi

if [ "${1:-}" = "--which" ]; then
  echo "$PY"
  "$PY" -c 'import sys, fastapi; print("python", sys.version.split()[0], "| fastapi", fastapi.__version__)'
  exit 0
fi

if [ "$#" -gt 0 ]; then
  LANES=("$@")
else
  LANES=()
  for f in "$HERE"/test_*.py; do LANES+=("$(basename "$f")"); done
fi

# How a lane runs. A file with a __main__ block runs itself and says "Ran N tests". A file with none would run as a
# script that defines its tests and calls nothing, and the lane said PASS over 0 tests (found 2026-10-23: eleven such
# files, test_j2.py among them, PASS with nothing run); so pytest runs it, and says "N passed". A plain script of
# checks (top-level check() calls, no test function, no __main__) still runs itself and says "N checks". A lane
# that runs nothing is a FAIL: pytest's exit 5 (no tests collected), or a count of 0.
mode_of() {
  if grep -q "__main__" "$1"; then echo script
  elif grep -qE '^[[:space:]]*(async[[:space:]]+)?def test_' "$1"; then echo pytest
  else echo script; fi
}

rc=0
for lane in "${LANES[@]}"; do
  printf '%-34s ' "$lane"
  if [ "$(mode_of "$HERE/$lane")" = pytest ]; then
    out=$("$PY" -m pytest -q -p no:cacheprovider "$HERE/$lane" 2>&1); code=$?
    count=$(printf '%s' "$out" | tail -1 | grep -oE '[0-9]+ (passed|xfailed|skipped)' | paste -sd, - | sed 's/,/, /g')
  else
    out=$("$PY" "$HERE/$lane" 2>&1); code=$?
    count=$(printf '%s' "$out" | grep -oE 'Ran [0-9]+ tests?|[0-9]+ checks' | tail -1)
  fi
  if [ "$code" -eq 0 ] && ! printf '%s' "$count" | grep -qE '^(Ran )?0 '; then
    echo "PASS  $count"
  else
    [ "$code" -eq 5 ] && echo "FAIL  no tests collected" || echo "FAIL"
    printf '%s\n' "$out" | tail -18 | sed 's/^/    /'
    rc=1
  fi
done
exit $rc
