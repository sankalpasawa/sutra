"""Check Adaptation's deliverable choice on real briefs (not part of the normal run).

Sends each brief straight to the planner's deliverable choice and workflow planning, as J2Run._deliverables does
(j2_realization.plan_goal with the type list, J2_GENERIC=1, J2_TEMPLATE_LIBRARY=1), with the real provider (claude-cli).
Identity's questions and the build are skipped. Prints each brief's deliverables (with why) and workflows (stage, name,
the deliverable it serves) and writes runs/deliverables-check.md.

    python3 tools/check_deliverables.py [--jobs 5]
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.update(J2_GENERIC="1", J2_TEMPLATE_LIBRARY="1", STUDIO_PROVIDER="claude-cli")
os.environ.pop("STUDIO_MOCK", None)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import j2_realization as R  # noqa: E402
import llm  # noqa: E402

BRIEFS = (
    "a website for a bakery",
    "a PRD for a booking app",
    "design docs for a booking app",
    "the HLD for a booking app",
    "a PRD and a website for a gym",
    "a hiring policy for a small startup",
    "a monthly sales report for a shop",
    "a landing page for a music event",
    "an LLD for a chat app",
    "help me sell more flowers",
)


def check(brief):
    t0 = time.time()
    goal = {"statement": brief, "brief": True}
    try:
        r = R.plan_goal(goal, web=False, log=lambda m: None, types=R.type_list())
    except Exception as e:      # one failed brief doesn't stop the others
        return {"brief": brief, "error": f"{type(e).__name__}: {e}", "seconds": round(time.time() - t0)}
    p = r["plan"]
    return {"brief": brief, "seconds": round(time.time() - t0), "calls": r["calls"],
            "confidence": r["plan_confidence"], "faults": r["plan_faults"],
            "deliverables": [d if isinstance(d, dict) else {"type": d, "why": ""} for d in R.lst(p.get("deliverables"))],
            "workflows": [{k: w.get(k) for k in ("stage", "name", "serves")} for w in R.lst(p.get("workflows"))
                          if isinstance(w, dict)]}


def md(res):
    out = ["# Deliverables check", "", f"Provider {llm.PROVIDER} ({llm.MODEL}), J2_GENERIC=1, J2_TEMPLATE_LIBRARY=1.", "",
           "| # | Brief | Deliverables |", "|---|---|---|"]
    out += [f"| {i} | {x['brief']} | " + (f"ERROR {x['error']}" if "error" in x else
                                          ", ".join(str(d.get("type")) + (" (new)" if isinstance(d.get("new"), dict) else "")
                                                    for d in x["deliverables"]) or "-") + " |"
            for i, x in enumerate(res, 1)]
    for i, x in enumerate(res, 1):
        out += ["", f"## {i}. {x['brief']}", ""]
        if "error" in x:
            out.append(f"Error: {x['error']}")
            continue
        out.append(f"{x['calls']} calls, {x['seconds']}s, plan confidence {x['confidence']:.2f}"
                   + (f", faults: {'; '.join(x['faults'])}" if x["faults"] else ", no faults"))
        out += ["", "Deliverables:"] + [f"- **{d.get('type')}**: {d.get('why') or '-'}"
                                        + (f" New type: {d['new'].get('label')}, sections {', '.join(d['new'].get('sections') or [])}, "
                                           f"file {d['new'].get('file')}." if isinstance(d.get("new"), dict) else "")
                                        for d in x["deliverables"]]
        out += ["", "| Stage | Workflow | Serves |", "|---|---|---|"]
        out += [f"| {w['stage']} | {str(w['name']).replace('|', '/')} | {w['serves']} |" for w in x["workflows"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    assert not llm.MOCK and llm.PROVIDER == "claude-cli", "needs the claude CLI (STUDIO_PROVIDER=claude-cli)"
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 5
    with ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(check, BRIEFS))
    text = md(res)
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    with open(os.path.join(HERE, "runs", "deliverables-check.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
