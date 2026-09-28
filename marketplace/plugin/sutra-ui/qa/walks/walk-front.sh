#!/bin/bash
# A person at the front door, on the source server with the real model: say words on a Root, then watch Root hand them
# on and the department's answer come back onto Root's chat, printing each turn as it lands.
#   usage: qa/walks/walk-front.sh "<words>" [root-name] [base-url] [seconds]
#     words      what the person says, e.g. "On Sunrise Physio Website, add a Careers page."
#     root-name  which Root (default: the last Root the server lists)
#     base-url   default http://127.0.0.1:8341
#     seconds    how long to watch (default 240)
# Ends when the department files the words (filed in the Brief), refuses them, or Root says it could not act in time.
set -u
WORDS="${1:?say the words}"
ROOT_NAME="${2:-}"
BASE="${3:-http://127.0.0.1:8341}"
SECS="${4:-240}"
python3 - "$WORDS" "$ROOT_NAME" "$BASE" "$SECS" <<'EOF'
import json, sys, time, urllib.request
words, root_name, base, secs = sys.argv[1], sys.argv[2], sys.argv[3].rstrip("/") + "/api/native", float(sys.argv[4])
def get(p):
    with urllib.request.urlopen(base + p, timeout=10) as r: return json.load(r)
def post(p, body):
    req = urllib.request.Request(base + p, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r: return json.load(r)
d = get("/depts")["depts"]
roots = [x for x in d if x.get("kind") == "root"]
root = ([x for x in roots if x["name"] == root_name] or roots[-1:])
if not root:
    print("no Root on this server; found an organisation first"); sys.exit(1)
root = root[0]
kids = [x for x in d if x.get("parent") == root["ref"]]
print("Root:", root["name"], root["ref"], "| departments:", ", ".join(k["name"] for k in kids) or "none")
before = len(get("/%s/chat" % root["ref"])["turns"])
out = post("/%s/ask" % root["ref"], {"text": words})
print("said:", out["request"]["id"], "|", words)
seen, t0 = set(), time.time()
while time.time() - t0 < secs:
    c = get("/%s/chat" % root["ref"])
    for t in c["turns"][before:]:
        if t["n"] in seen: continue
        seen.add(t["n"])
        print("%6.0fs  %-8s %-6s %-22s %s  [%s]" % (time.time() - t0, t["src"], (t["msg_type"] or "")[:6], (t["name"] or "Root")[:22], (t["line"] or "")[:88], t["word"]))
    lines = [t["line"] or "" for t in c["turns"][before:]]
    if any("filed in the Brief" in l or l.startswith("refused") or "breaks a rule" in l or "could not act on this in time" in l for l in lines):
        break
    time.sleep(3)
c = get("/%s/chat" % root["ref"])
print("Root's chat: %d turns, %d asks waiting" % (len(c["turns"]), len(c["asks"])))
EOF
