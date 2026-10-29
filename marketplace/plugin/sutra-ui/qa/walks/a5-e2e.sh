#!/bin/bash
# Amendment A5 end to end (PRD A5.8 P5, steps P5.1 to P5.5): the app from source on a record of its own, one department of each kind, three
# tasks (one using a department, one spawning one through a stubbed CHOOSER, one with none), a conversation and a goal; the walk in a real
# browser (a5-walk.js); the routes' own answers; a Setup conversation said to a Root in the J2 page; the Models editor's listing; the graph's
# read time on 300 seeded tasks.
#   usage: qa/walks/a5-e2e.sh [record-dir] [port] [out-dir]
#   record-dir  default: a new directory under $TMPDIR (kept, and named at the end)
#   port        default 8372 (not the walks' 8341 nor j2ui-e2e's 8362, so a founder's own server is left alone)
#   out-dir     where the screenshots go, default qa/shots/a5
# Nothing here calls a model (SUTRA_WEBSITE_OFFLINE=1, the motor off, the choice stubbed) and nothing leaves the record: the department records,
# the Shadow records (SUTRA_SHADOW_HOME) and the settings (SUTRA_UI_SETTINGS) are all under record-dir. The server is stopped on the way out.
# Exit 0 when every claim held, 1 otherwise; without Chrome the browser walk is skipped and said so (the routes' checks still run).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
UI="$(cd "$HERE/../.." && pwd)"
REC="${1:-$(mktemp -d "${TMPDIR:-/tmp}/a5-e2e-XXXXXX")}"
PORT="${2:-8372}"
OUT="${3:-$UI/qa/shots/a5}"
PY="$UI/.venv/bin/python"
[ -x "$PY" ] || PY=python3
export SUTRA_WEBSITE_OFFLINE=1 SUTRA_MOTOR_OFF=1 J2_FLOW_V1=1 J1_FLOW_V1=1
export SUTRA_SHADOW_HOME="$REC/shadow" SUTRA_UI_SETTINGS="$REC/settings.json"
mkdir -p "$REC" "$OUT"
cd "$UI" || exit 1
bash "$HERE/devserver-stop.sh" "$PORT" 2>&1 | tail -1
trap 'bash "$HERE/devserver-stop.sh" "$PORT" >/dev/null 2>&1' EXIT
SEEDED="$("$PY" "$HERE/a5_seed.py" "$REC" 2>/dev/null)" || { echo "a5-e2e: the seed failed"; exit 1; }
echo "$SEEDED"
"$PY" -c "import json,sys; print(json.dumps(dict(l.split(' ',1) for l in sys.stdin.read().splitlines())))" <<<"$SEEDED" > "$REC/refs.json"
# the server's HOME is a folder of the record, so the chats of the operator's own Claude sessions are not read onto the screens photographed
mkdir -p "$REC/home"
HOME="$REC/home" bash "$HERE/devserver-detach.sh" "$REC" "$PORT" | tail -2
RC=0

# ---- the routes' own answers: the graph, the detail, the listing, the models (no browser) ----------------------------------------
"$PY" - "http://127.0.0.1:$PORT" "$REC/refs.json" <<'PYEOF' || RC=1
import json, sys, urllib.request
base, refs = sys.argv[1], json.load(open(sys.argv[2]))
get = lambda p: json.load(urllib.request.urlopen(base + p, timeout=15))
fail = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else "  -- " + str(detail)))
    if not ok:
        fail.append(name)
g = get("/api/shadow/graph")
kinds = {n["kind"] for n in g["nodes"]}
check("api graph: a node of every kind", kinds >= {"shadow", "task", "goal", "conversation", "task_chat", "worker", "department"}, kinds)
edge = {e["kind"]: e for e in g["edges"] if e["kind"] in ("uses", "spawned")}
check("api graph: uses and spawned each carry the reason", all(edge.get(k) and edge[k].get("reason") for k in ("uses", "spawned")), edge)
check("api graph: the task with no department draws no department edge", not any(e["target"].endswith(refs["task_none"]) for e in g["edges"] if e["kind"] in ("uses", "spawned")))
d = get("/api/shadow/graph/task/" + refs["task_use"])
check("api detail: decision, departments, chats, costs, timeline", all(k in d for k in ("decision", "departments", "chats", "costs", "timeline")), list(d))
check("api detail: the decision is a use of Billing", d["decision"]["final_action"] == "use" and d["decision"]["final_ref"] == refs["default"], d["decision"])
dn = get("/api/shadow/graph/task/" + refs["task_none"])
check("api detail: a task with no department says so", (dn.get("decision") or {}).get("final_action") == "none" or dn.get("decision") is None)
lst = get("/api/native/_departments?root=" + refs["root"])
check("api listing: the Root's departments are listed", len(lst.get("departments", lst if isinstance(lst, list) else [])) >= 2, str(lst)[:200])
for kind in ("default", "organic", "root", "website"):
    st = get("/j2ui/%s/api/state" % refs[kind])
    check("api page: %s answers its state with words" % kind, "words" in st and st["words"].get("pick") is False if kind != "website" else "words" in st, list(st)[:5])
m = get("/api/native/_models?all=1")
m = m.get("data", m) if isinstance(m, dict) else m
sealed = [r["key"] for layer in (m.get("built_in") or []) for r in layer["models"] if r.get("sealed")]
check("api models: the editor lists all 17 A5 models as read-only built-ins", len(sealed) == 17, sealed)
check("api models: none of them is offered to build on", not any(k in json.dumps(m.get("buildable")) for k in ("shadow.graph", "dept.decision")))
print("fail:", len(fail))
sys.exit(1 if fail else 0)
PYEOF

# ---- the browser walk (Chrome) ----------------------------------------------------------------------------------------------------
if [ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] && [ -z "${CHROME:-}" ]; then
  echo "a5-e2e: Google Chrome is not here (set CHROME); the browser walk and the screenshots were skipped"
else
  node "$HERE/a5-walk.js" "$OUT" "http://127.0.0.1:$PORT" "$REC/refs.json" || RC=1
fi
# ---- P5.3: a real Setup conversation with a Root inside the J2 page ------------------------------------------------------------------
# It needs a model, so it is never part of the gate: A5_REAL_SETUP=1 runs it (the app on the record with the motor on and no offline
# functions, the operator's own HOME so the model CLI is signed in; it spends what a Setup conversation spends). The record of 2026-10-29: not
# walked, because no model was reachable from the build session (offline, with the motor on, Root files nothing and makes no department),
# so J2_ROOT_DEFAULT stays false (A5-5) and Root's chat stays the classic one until this passes and its owner flips the one line.
if [ "${A5_REAL_SETUP:-0}" = "1" ]; then
  bash "$HERE/devserver-stop.sh" "$PORT" 2>&1 | tail -1
  ( unset SUTRA_WEBSITE_OFFLINE SUTRA_MOTOR_OFF; bash "$HERE/devserver-detach.sh" "$REC" "$PORT" | tail -1 )
  ROOT_REF="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['root'])" "$REC/refs.json")"
  curl -s -m 20 -X POST "http://127.0.0.1:$PORT/j2ui/$ROOT_REF/api/say" -H 'Content-Type: application/json' \
    -d '{"text":"I want a department that answers customer invoice questions and files every invoice"}' >/dev/null
  SETUP=FAIL
  for i in $(seq 1 36); do
    sleep 5
    N="$(curl -s -m 10 "http://127.0.0.1:$PORT/api/native/depts" | "$PY" -c "import json,sys; print(sum(1 for d in json.load(sys.stdin)['depts'] if d.get('parent') == sys.argv[1]))" "$ROOT_REF")"
    [ "${N:-0}" -gt 4 ] && { SETUP=PASS; break; }
  done
  echo "root setup in the J2 page: $SETUP (a new department under the Root within 180 s)" | tee "$OUT/root-setup.txt"
else
  echo "root setup in the J2 page: not walked (A5_REAL_SETUP=1 needs a model); J2_ROOT_DEFAULT stays false"
fi
echo "record: $REC   screenshots: $OUT   exit $RC"
exit $RC
