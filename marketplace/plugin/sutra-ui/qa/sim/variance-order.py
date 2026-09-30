#!/usr/bin/env python3
"""Draw a goal's variances in a random order and log it, so no two runs walk the same path (TODO SIM-4; founder,
2026-09-28: "create scripts of various things which can create non-linear flows").
   usage: python3 qa/sim/variance-order.py <goal> [run-dir] [seed] [count]
     goal     a name under qa/sim/goals/
     run-dir  where order.json is written (default: stdout only)
     seed     an integer; the same seed draws the same order (default: from the clock)
     count    how many variances to draw (default: all)
   The agent (AGENT.md) takes the variances in this order, interleaving them with the goal's outcomes as a person
   would: a variance may fire while a line runs, or right after an ask. The order is the plan; the ledger is the truth."""
import json, os, random, sys, time
here = os.path.dirname(os.path.abspath(__file__))
goal = sys.argv[1]
run_dir = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
seed = int(sys.argv[3]) if len(sys.argv) > 3 else int(time.time())
g = json.load(open(os.path.join(here, "goals", goal + ".json"), encoding="utf-8"))
rng = random.Random(seed)
variances = list(g.get("variances") or [])
rng.shuffle(variances)
count = int(sys.argv[4]) if len(sys.argv) > 4 else len(variances)
drawn = variances[:count]
# where each fires: a moment a person might choose, drawn too, so the flow is non-linear in time as well as in order
moments = ["right after the goal is filed", "while Plan runs", "while Write runs", "right after the publish ask", "right after the site is live", "after Audit's question"]
plan = [{"n": i + 1, "id": v["id"], "at": rng.choice(moments), "say": v.get("say"), "do": v.get("do"), "expect": v.get("expect")} for i, v in enumerate(drawn)]
out = {"goal": goal, "person": g.get("person"), "seed": seed, "drawn": [p["id"] for p in plan], "plan": plan, "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
text = json.dumps(out, indent=1, ensure_ascii=False)
if run_dir:
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "order.json"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("order.json written to", run_dir, "(seed %d)" % seed)
for p in plan:
    print("%d. %s -- %s: %s" % (p["n"], p["id"], p["at"], p.get("say") or p.get("do")))
