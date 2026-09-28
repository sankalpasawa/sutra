#!/usr/bin/env python3
"""How long the panel takes to answer, every 2 s, while a run is on: the numbers behind "the app went quiet" (Human
Simulation run 1, finding 11: /map timed out for 15 s after the publish stamp). Read-only; it only reads the map.
   usage: python3 qa/sim/probe-map.py <dept-ref> [base-url] [seconds] [out.jsonl]
     dept-ref  the department whose map is read (from /api/native/depts)
     base-url  default http://127.0.0.1:8331
     seconds   how long (default 600)
     out.jsonl where each reading goes (default: stdout only)
   prints every reading slower than 3 s as it happens, and a summary at the end: count, slowest, what ran then."""
import json, sys, time, urllib.request
ref = sys.argv[1]
base = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8331").rstrip("/") + "/api/native"
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 600
out = open(sys.argv[4], "a") if len(sys.argv) > 4 else None
t0, rows = time.time(), []
while time.time() - t0 < secs:
    t = time.time()
    try:
        with urllib.request.urlopen("%s/%s/map" % (base, ref), timeout=30) as r:
            m = json.load(r)
        took, running, err = time.time() - t, [x["engine"] for x in m["status"]["running"]], None
    except Exception as e:  # noqa: BLE001 -- a timeout is the reading
        took, running, err = time.time() - t, None, repr(e)[:80]
    row = {"at": round(t - t0, 1), "took_s": round(took, 2), "running": running, "err": err}
    rows.append(row)
    if out:
        out.write(json.dumps(row) + "\n"); out.flush()
    if took > 3 or err:
        print("%6.1fs  took %5.2fs  running=%s  %s" % (row["at"], took, running, err or ""), flush=True)
    time.sleep(max(0.0, 2 - took))
slow = [r for r in rows if r["took_s"] > 3 or r["err"]]
worst = max(rows, key=lambda r: r["took_s"]) if rows else None
print("readings %d, slow (>3 s or failed) %d, slowest %.2fs at %ss (running=%s)" % (
    len(rows), len(slow), worst["took_s"] if worst else 0, worst["at"] if worst else "-", worst["running"] if worst else "-"))
