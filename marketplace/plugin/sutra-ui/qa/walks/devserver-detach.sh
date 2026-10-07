#!/bin/bash
# Start the source server detached from the shell (its own session id, no task the shell waits on), after stopping the
# one already on the port if it is this app's; then check it answers.
#   usage: qa/walks/devserver-detach.sh [record-dir] [port]     (defaults as devserver.sh)
# The server's log: <record-dir>/devserver.log. Stop it later with devserver-stop.sh <port>.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
T="${1:-${TMPDIR:-/tmp}/sutra-walk}"
PORT="${2:-8341}"
mkdir -p "$T"
bash "$HERE/devserver-stop.sh" "$PORT" 2>&1 | tail -2
python3 - "$HERE" "$T" "$PORT" <<'EOF'
import os, subprocess, sys
here, rec, port = sys.argv[1:4]
log = open(os.path.join(rec, "devserver.log"), "ab")
p = subprocess.Popen(["bash", os.path.join(here, "devserver.sh"), rec, port], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True, cwd=here)
print("detached server pid", p.pid)
EOF
for i in $(seq 1 60); do curl -s -m 2 "http://127.0.0.1:$PORT/api/native/depts" >/dev/null 2>&1 && break; /bin/sleep 1; done
curl -s -m 5 "http://127.0.0.1:$PORT/api/native/depts" | python3 -c 'import json,sys; d=json.load(sys.stdin)["depts"]; print(len(d), "departments answer:", ", ".join(x["name"] for x in d))'
echo "holder now: $(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $1, $2}')"
