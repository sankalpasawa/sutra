#!/bin/bash
# Every suite of the website department and the department screen, one process each; red anywhere is exit 1.
#   usage: qa/walks/suites.sh        (from anywhere; the app's own .venv when it exists)
set -u
UI="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$UI" || exit 1
RC=0
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
# every Python lane on a registry of its own: a lane that mints a root finds one root, never the last lane's
# (2026-09-28: the founding test spawned no child on a shared registry, and this runner said exit 1 under green lanes)
lane(){ SUTRA_NATIVE_HOME="$(mktemp -d "${TMPDIR:-/tmp}/sutra-suite-XXXXXX")" "$@"; }
lane $PY -c "import engine_runtime as R; f=R.validate(R.defs()); assert not f, f; print('definitions: clean, version', R.defs()['def_version'])" || RC=1
lane $PY -m unittest test_engine_runtime > /tmp/sutra-suite-runtime.txt 2>&1 || RC=1
tail -3 /tmp/sutra-suite-runtime.txt | tr '\n' ' '; echo
lane $PY test_website_motor.py > /tmp/sutra-suite-motor.txt 2>&1 || RC=1
tail -1 /tmp/sutra-suite-motor.txt
lane $PY -m pytest -q test_website_dept.py test_channel_isolation.py > /tmp/sutra-suite-pytest.txt 2>&1 || RC=1
tail -1 /tmp/sutra-suite-pytest.txt
# each function's instruction files (PRD M2): byte for byte as the inline prompts were, a stamp-only change, a refused
# change leaving nothing, a change surviving an update; a lane of its own, since its fixture reloads the runtime
lane $PY -m pytest -q -p no:cacheprovider test_function_prompts.py > /tmp/sutra-suite-prompts.txt 2>&1 || RC=1
tail -1 /tmp/sutra-suite-prompts.txt | sed "s/^/function prompts: /"
# the department's life (J1 made it, J2 runs it): these files have no __main__ block, so only pytest runs them
lane $PY -m pytest -q test_j2.py test_j2_api.py test_j1.py > /tmp/sutra-suite-j2.txt 2>&1 || RC=1
tail -1 /tmp/sutra-suite-j2.txt
# the ledger's contract (PRD M0.2: append without reading, read only through J.events) and the lanes' honesty (M0.1);
# about 70 s together, the 10,000-append ledger test most of it; its p95 is recorded, never a gate
lane $PY -m pytest -q -p no:cacheprovider test_j2_ledger.py test_run_lanes.py > /tmp/sutra-suite-ledger.txt 2>&1 || RC=1
tail -1 /tmp/sutra-suite-ledger.txt | sed "s/^/ledger and lanes: /"
for t in test_website.js test_dept.js test_org2.js; do
  node "$t" 2>&1 | tail -1 | sed "s/^/$t: /"
  node "$t" >/dev/null 2>&1 || RC=1
done
echo "suites exit $RC"
exit $RC
