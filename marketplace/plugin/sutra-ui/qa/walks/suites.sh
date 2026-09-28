#!/bin/bash
# Every suite of the website department and the department screen, one process each; red anywhere is exit 1.
#   usage: qa/walks/suites.sh        (from anywhere; the app's own .venv when it exists)
set -u
UI="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$UI" || exit 1
RC=0
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
$PY -c "import engine_runtime as R; f=R.validate(R.defs()); assert not f, f; print('definitions: clean, version', R.defs()['def_version'])" || RC=1
$PY -m unittest test_engine_runtime 2>&1 | tail -3 | tr '\n' ' '; echo
$PY -m unittest test_engine_runtime >/dev/null 2>&1 || RC=1
$PY test_website_motor.py 2>&1 | tail -1
$PY test_website_motor.py >/dev/null 2>&1 || RC=1
$PY -m pytest -q test_website_dept.py test_channel_isolation.py 2>&1 | tail -1
$PY -m pytest -q test_website_dept.py test_channel_isolation.py >/dev/null 2>&1 || RC=1
for t in test_website.js test_dept.js test_org2.js; do
  node "$t" 2>&1 | tail -1 | sed "s/^/$t: /"
  node "$t" >/dev/null 2>&1 || RC=1
done
echo "suites exit $RC"
exit $RC
