#!/usr/bin/env bash
# The legacy J2 scripts as a parallel gate (work package E5, engine design 9; J2's own run_checks.sh is the model).
#
#   scripts/engine_gate.sh            j2_flow_test.py --fast, change_test.py and realization_test.py, each in its own throw-away copy of
#                                     tests/engine/legacy (the flow script writes runs, memory and a library while it runs, and the
#                                     scripts import each other), all at the same time; exit 0 only when every one passes
#   SUTRA_BROWSER=1 scripts/engine_gate.sh
#                                     also j2_flow_test.py --fast --browser (needs Chrome and node; skipped, with a line, otherwise)
#   SUTRA_J2_CHECKOUT=/path/to/J2_Prototype scripts/engine_gate.sh
#                                     the blocks that need J2's page, harness files and saved runs run too (they take much longer)
#
# What counts as green: exit 0; for the flow script also the last line "j2 flow checks passed", no Traceback, and at least as many
# lines ending " ok" as tests/engine/legacy/EXPECTED.json records; "N checks passed" with N at least the recorded number for the others.
# ENGINE_GATE_LEGACY_DIR and ENGINE_GATE_PY replace the script folder and the Python wrapper (the tests of this script use stand-ins).
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
LEGACY=${ENGINE_GATE_LEGACY_DIR:-$HERE/tests/engine/legacy}
PY=${ENGINE_GATE_PY:-$HERE/scripts/py}
TMP=${TMPDIR:-/tmp}

mirror() {   # a throw-away copy of the script folder (no caches)
  local d
  d=$(mktemp -d "${TMP%/}/engine-gate-XXXXXX") || exit 2
  (cd "$LEGACY" && tar -cf - --exclude __pycache__ .) | (cd "$d" && tar -xf -)
  echo "$d"
}

run_job() {  # run_job NAME COPY SCRIPT ARGS...  -> COPY/NAME.log and COPY/NAME.exit
  local name=$1 copy=$2
  shift 2
  ( cd "$copy" && "$PY" -u "$@" > "$name.log" 2>&1; echo $? > "$name.exit" )
}

if [ ! -f "$LEGACY/EXPECTED.json" ]; then echo "engine gate: $LEGACY/EXPECTED.json is missing" >&2; exit 2; fi
expected() { "$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$LEGACY/EXPECTED.json" "$1"; }
MIN_OK=$(expected flow_fast_ok_lines); MIN_CHANGE=$(expected change_checks); MIN_REAL=$(expected realization_checks)

fast=$(mirror); change=$(mirror); real=$(mirror); browser=""
echo "fast:         $fast/fast.log"
echo "change:       $change/change.log"
echo "realization:  $real/realization.log"
run_job fast "$fast" j2_flow_test.py --fast &
run_job change "$change" change_test.py &
run_job realization "$real" realization_test.py &
if [ "${SUTRA_BROWSER:-}" = "1" ]; then
  if command -v node >/dev/null 2>&1; then
    browser=$(mirror)
    echo "browser:      $browser/browser.log"
    run_job browser "$browser" j2_flow_test.py --fast --browser &
  else
    echo "browser:      skipped (node not found)"
  fi
else
  echo "browser:      skipped (set SUTRA_BROWSER=1 to run j2_flow_test.py --fast --browser)"
fi
wait

status=0
report() {   # report NAME COPY EXTRA-CHECK-RESULT
  local name=$1 copy=$2 code ok
  code=$(cat "$copy/$name.exit" 2>/dev/null || echo 99)
  ok=$(grep -c ' ok$' "$copy/$name.log" 2>/dev/null || true)
  echo "$name: exit $code, $ok lines ending ' ok'"
  if [ "$code" != 0 ]; then
    grep -A8 Traceback "$copy/$name.log" | tail -9
    tail -n 3 "$copy/$name.log"
    status=1
  fi
}
check_flow() {   # check_flow NAME COPY
  local name=$1 copy=$2
  report "$name" "$copy"
  if [ "$(cat "$copy/$name.exit")" = 0 ]; then
    if [ "$(tail -n 1 "$copy/$name.log")" != "j2 flow checks passed" ]; then echo "$name: the last line is not 'j2 flow checks passed'"; status=1; fi
    if grep -q Traceback "$copy/$name.log"; then echo "$name: a Traceback is in the log"; status=1; fi
    if [ "$(grep -c ' ok$' "$copy/$name.log")" -lt "$MIN_OK" ]; then echo "$name: fewer than $MIN_OK lines ending ' ok'"; status=1; fi
  fi
}
check_count() {  # check_count NAME COPY MIN
  local name=$1 copy=$2 min=$3 n
  report "$name" "$copy"
  if [ "$(cat "$copy/$name.exit")" = 0 ]; then
    n=$(grep -Eo '[0-9]+ checks passed' "$copy/$name.log" | tail -n 1 | grep -Eo '^[0-9]+')
    if [ -z "$n" ] || [ "$n" -lt "$min" ]; then echo "$name: '${n:-no} checks passed' is below the recorded $min"; status=1; fi
  fi
}
check_flow fast "$fast"
check_count change "$change" "$MIN_CHANGE"
check_count realization "$real" "$MIN_REAL"
[ -n "$browser" ] && check_flow browser "$browser"

if [ "$status" = 0 ]; then rm -rf "$fast" "$change" "$real" ${browser:+"$browser"}; echo "engine gate: ok"; else echo "engine gate: FAILED (logs are in the folders above)"; fi
exit $status
