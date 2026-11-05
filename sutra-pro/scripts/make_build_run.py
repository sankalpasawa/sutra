#!/usr/bin/env python3
"""Write a ready-to-run workflow script for the build: scripts/build_workflow.js with the plan from docs/build-plan.json
injected as EMBEDDED_ARGS, and the packages that are already merged (read from git) marked as done.

    scripts/py scripts/make_build_run.py [--out PATH] [--only ID,ID] [--no-review] [--slots N]

Then run it with  Workflow({scriptPath: PATH})  (add resumeFromRunId to continue an interrupted run).
Re-running the build after an interruption is safe: merged packages are detected from git and skipped.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("plan_tools", ROOT / "scripts" / "plan_tools.py")
plan_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_tools)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/private/tmp/claude-501/arch/work/build-run.js")
    ap.add_argument("--only", default="", help="comma separated package ids: build only these (and what they need)")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--slots", type=int, default=3, help="review-phase agents running at once")
    ap.add_argument("--parallel", type=int, default=5, help="developer agents running at once (paces token use)")
    ap.add_argument("--findings", action="append", default=[], metavar="ID=PATH",
                    help="json list of review findings already confirmed for package ID: run only its fix round, no review")
    ns = ap.parse_args()

    plan = plan_tools.load()
    problems = plan_tools.validate(plan)
    if problems:
        print("\n".join("PLAN PROBLEM: " + p for p in problems))
        return 1
    wps = plan["work_packages"]
    if ns.only:
        want = set(ns.only.split(","))
        by_id = {w["id"]: w for w in wps}
        keep: set[str] = set()

        def add(i: str) -> None:
            if i in keep:
                return
            keep.add(i)
            for d in by_id[i].get("depends_on", []):
                add(d)

        for i in want:
            add(i)
        wps = [w for w in wps if w["id"] in keep]
    fix_id = re.compile(r"-r\d+$")   # follow-up fixes after a review are merged as <id>-r1, <id>-r2 ...
    merged = {m for m in plan_tools.merged_ids() if not fix_id.search(m)}
    reviewed = {fix_id.sub("", m) for m in plan_tools.merged_ids() if fix_id.search(m)}
    embedded = {
        "app": str(ROOT),
        "wps": [{k: w[k] for k in ("id", "title", "section", "owns", "depends_on", "acceptance", "spec") if k in w} for w in wps],
        "alreadyMerged": sorted(merged),
        "alreadyReviewed": sorted(reviewed),
        "gateOnReview": plan.get("gate_on_review", []),
        "reviewOnly": plan.get("review_only"),
        "preConfirmed": {i: json.loads(Path(f).read_text()) for i, f in (x.split("=", 1) for x in ns.findings)},
        "reviewLenses": plan.get("review_lenses"),
        "maxParallel": ns.parallel,
        "skipReview": ns.no_review,
        "reviewSlots": ns.slots,
    }
    template = (ROOT / "scripts" / "build_workflow.js").read_text()
    marker = "// the plan is injected by the launcher"
    assert marker in template, "template changed: marker not found"
    out = template.replace(marker, "const EMBEDDED_ARGS = " + json.dumps(embedded) + "\n" + marker, 1)
    Path(ns.out).write_text(out)
    todo = [w["id"] for w in wps if w["id"] not in merged]
    print(f"wrote {ns.out}: {len(wps)} packages, {len(merged & {w['id'] for w in wps})} already merged, {len(todo)} to build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
