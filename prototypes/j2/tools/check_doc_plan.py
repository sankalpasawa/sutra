"""Check Adaptation's document planning on a real model (not part of the normal run).

J2_GENERIC=1, the real provider (claude-cli). For one brief: the planner chooses the deliverables (as J2Run._deliverables
does), the first document's charter is written by code (the type's mock charter; Identity's questions are skipped),
then Adaptation's real propose call plans the document's workflows through J2's own checks (sections, coverage, atoms).
Nothing is built. Prints the deliverables, then each proposed workflow: name, sections, covers, parts, and the
validator's flags.

    python3 tools/check_doc_plan.py ["a PRD for a booking app"]
"""
import json
import os
import sys

os.environ.update(J2_GENERIC="1", STUDIO_PROVIDER="claude-cli")
os.environ.pop("STUDIO_MOCK", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import j2  # noqa: E402
import llm  # noqa: E402


def main(brief):
    assert not llm.MOCK and llm.PROVIDER == "claude-cli", "needs the claude CLI (STUDIO_PROVIDER=claude-cli)"
    run = j2.J2Run()
    run.request = brief
    if run._plan_stages() is False:
        return print("the planner chose nothing J2 can build")
    d = json.load(open(os.path.join(run.dir, "deliverables.json"), encoding="utf-8"))
    print(f"run folder: {run.dir}\n\nDELIVERABLES: " + ", ".join(d["deliverables"]))
    if not run.doc:
        return print(f"the first deliverable is {run.output}, not a document: nothing to plan here")
    run.goal = run.out["mock_charter"](brief)      # code's charter: Identity is skipped
    print(f"\nCHARTER ({run.out['noun']}, written by code): " + "; ".join(f"{i}. {c}" for i, c in enumerate(run.goal["done_when"], 1)))
    run._handoff("adaptation", kind="propose", new_cycle=True)
    run._turn_adaptation(run.handoff)
    wfs = run.a_pos or []
    print(f"\nWORKFLOWS ({len(wfs)}):")
    for w in wfs:
        print(f"- {w.get('name')}: sections {w.get('sections')}, covers {w.get('covers')}, parts {w.get('parts')}, cost {w.get('cost')}")
    flags = [x["reason"] for x in run.rejections]
    print("\nVALIDATOR FLAGS: " + (" | ".join(flags) if flags else "none"))
    print(f"\nTEMPLATE SECTIONS: {', '.join(run.out['sections'])}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "a PRD for a booking app")
