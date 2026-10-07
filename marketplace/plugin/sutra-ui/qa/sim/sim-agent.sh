#!/bin/bash
# Start a Human Simulation run: the folder, the app up on its panel, and the goal, the person and the runbook printed
# for the agent that drives. The agent then walks the app by its own buttons (AGENT.md); this script only sets the table.
#   usage: qa/sim/sim-agent.sh <goal> [person] [base-url]
#     goal      a file under qa/sim/goals/ by its name, e.g. parasthi-hospital
#     person    a file under qa/sim/person/ by its name (default founder)
#     base-url  the panel (default http://127.0.0.1:8331, Sutra Beta)
#   makes: qa/sim/runs/<goal>-<YYYYMMDD-HHMM>/run.json  (goal, person, panel, app version, started)
#   env: SIM_OPEN=0 never opens the app (default: opens Sutra Beta when the panel does not answer)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
GOAL="${1:?which goal (a name under qa/sim/goals/)}"
PERSON="${2:-founder}"
BASE="${3:-http://127.0.0.1:8331}"
G="$HERE/goals/$GOAL.json"; P="$HERE/person/$PERSON.json"
[ -f "$G" ] || { echo "no goal at $G"; ls "$HERE/goals" | sed 's/\.json$//' | sed 's/^/  goals: /'; exit 2; }
[ -f "$P" ] || { echo "no person at $P"; exit 2; }
if ! curl -s -m 4 -o /dev/null "$BASE/"; then
  if [ "${SIM_OPEN:-1}" = "1" ] && [ "$BASE" = "http://127.0.0.1:8331" ]; then
    open -a "Sutra Beta" 2>/dev/null && echo "opened Sutra Beta; waiting for $BASE"
    for _ in $(seq 1 30); do curl -s -m 2 -o /dev/null "$BASE/" && break; sleep 2; done
  fi
  curl -s -m 4 -o /dev/null "$BASE/" || { echo "the panel at $BASE does not answer"; exit 3; }
fi
# the panel has no version route; the app's bundle says which build is installed (8331 is Sutra Beta, 8330 Sutra)
APP="/Applications/Sutra Beta.app"; [ "$BASE" = "http://127.0.0.1:8330" ] && APP="/Applications/Sutra.app"
VER="$(defaults read "$APP/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null || true)"
RUN="$HERE/runs/$GOAL-$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN"
python3 - "$RUN" "$GOAL" "$PERSON" "$BASE" "$VER" <<'EOF'
import json, sys, time
run, goal, person, base, ver = sys.argv[1:6]
json.dump({"goal": goal, "person": person, "panel": base, "app_version": ver, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "ledger": "ledger.jsonl", "findings": "findings.jsonl", "report": "report.md"}, open(run + "/run.json", "w"), indent=1)
EOF
echo "run folder: $RUN"
echo "panel: $BASE  app: ${VER:-unknown}"
echo; echo "== the person ($P)"; cat "$P"
echo; echo "== the goal ($G)"; cat "$G"
echo; echo "== the runbook: $HERE/AGENT.md"
echo "the agent now walks the panel by its own buttons; every click and its why is a row of $RUN/ledger.jsonl"
