#!/usr/bin/env python3
"""The speed of a reply, from a department's record (founder, 2026-09-28: "the speed of a reply and what blocks it").
For every request the person made, the wall time until the department said something back, and where that time went:
steps by the model, steps by code, and the rest (waiting for the clock, a gate, or a person). Read-only.
   usage: python3 qa/sim/reply-speed.py <record-dir>
     record-dir  a department's record, e.g. ~/.sutra-ui-beta/native/<ref> (Sutra Beta) or <walk>/native/<ref>"""
import json, os, sys
from datetime import datetime

rec = os.path.expanduser(sys.argv[1]).rstrip("/")
def lines(name):
    p = os.path.join(rec, name)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None

board, steps = lines("board.jsonl"), lines("steps.jsonl")
runs = json.load(open(os.path.join(rec, "runs.json"))) if os.path.exists(os.path.join(rec, "runs.json")) else []
runs = runs if isinstance(runs, list) else list(runs.values())
by_run = {}
for s in steps:
    by_run.setdefault(s.get("run"), []).append(s)
asked = [p for p in board if p["src"] == "Owner" and p["msg_type"] in ("request", "accept-proposal", "reject-proposal")]
# model and code are sums over the steps that ran in the window; steps run side by side, so a sum can pass the wall
# time and "rest" go negative: read rest as waiting only when it is positive
print("%-6s %-9s %-46s %8s %8s %8s %8s  %s" % ("n", "act", "the words", "reply s", "model+s", "code+s", "rest s", "who answered"))
for p in asked:
    t0 = ts(p["at"])
    after = [q for q in board if q["n"] > p["n"] and q["src"] != "Owner" and "Owner" in q["dst"]]
    ans = after[0] if after else None
    t1 = ts(ans["at"]) if ans else None
    wall = (t1 - t0) if (t0 and t1) else None
    inside = [r for r in runs if ts(r.get("started")) and t0 <= ts(r["started"]) <= (t1 or 1e18)]
    model = sum(s.get("ms", 0) for r in inside for s in by_run.get(r["id"], []) if s.get("calls")) / 1000
    code = sum(s.get("ms", 0) for r in inside for s in by_run.get(r["id"], []) if not s.get("calls")) / 1000
    rest = (wall - model - code) if wall is not None else None
    words = str((p.get("payload") or {}).get("words") or (p.get("payload") or {}).get("word") or "")[:46]
    print("%-6s %-9s %-46s %8s %8.1f %8.1f %8s  %s" % (p["n"], p["msg_type"][:9], words, "%.0f" % wall if wall is not None else "-",
                                                     model, code, "%.0f" % rest if rest is not None else "-",
                                                     "%s: %s" % (ans["src"], str((ans.get("payload") or {}).get("word"))) if ans else "nobody yet"))
slow = sorted((s for s in steps if s.get("ms")), key=lambda s: -s["ms"])[:8]
print("\nslowest steps:")
for s in slow:
    print("  %6.1fs  %-12s %-22s %s%s" % (s["ms"] / 1000, s.get("engine"), s.get("step"), "model" if s.get("calls") else "code",
                                          (" item=" + str(s["item"])) if s.get("item") else ""))
