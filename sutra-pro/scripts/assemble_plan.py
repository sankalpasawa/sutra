#!/usr/bin/env python3
"""Assemble docs/build-plan.json from the consolidation workflow's journal.

    scripts/py scripts/assemble_plan.py --journal <journal.jsonl> [--with-gaps] [--write]

Reads the final work-package list each section patcher returned (agents labelled 'patch:<section>'), optionally the
GAP-* packages the coverage critic proposed (label 'critic:coverage', severities high and medium), normalises them
(bare ids in depends_on, every package owns docs/notes/<id>.md), validates the result with plan_tools and, with
--write, writes docs/build-plan.json and docs/BUILD-PLAN.md. Without --write it only prints the problems and the waves.
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

SECTIONS = ("engine", "connectors", "library", "orchestrator", "ui")
# packages everything else stands on: they are reviewed and fixed BEFORE their dependants start
GATE_ON_REVIEW = ["L1", "E0", "CN-1", "ORCH-1"]


def journal_results(path: Path) -> dict[str, dict]:
    """label -> result of every finished agent in a workflow journal."""
    labels: dict[str, str] = {}
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("type") == "started":
            labels[row["agentId"]] = row.get("label", "")
        elif row.get("type") == "result" and row.get("result") is not None:
            out[labels.get(row["agentId"], row["agentId"])] = row["result"]
    return out


def bare_id(dep: str, known: set[str]) -> str | None:
    """'ENG E0 (sutra_app/engine/port.py)' -> 'E0'; None when no known id is named."""
    if dep in known:
        return dep
    for tok in re.findall(r"[A-Za-z]+-?\d+(?:-[A-Za-z0-9]+)?", dep):
        if tok in known:
            return tok
    return None


def normalise(wps: list[dict]) -> list[dict]:
    known = {w["id"] for w in wps}
    out = []
    for w in wps:
        w = dict(w)
        deps = []
        for d in w.get("depends_on", []):
            b = bare_id(d, known)
            if b and b != w["id"] and b not in deps:
                deps.append(b)
        w["depends_on"] = deps
        owns = list(dict.fromkeys(w.get("owns", [])))
        note = f"docs/notes/{w['id']}.md"
        if note not in owns:
            owns.append(note)
        w["owns"] = owns
        w["acceptance"] = list(w.get("acceptance", []))
        out.append(w)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True, type=Path)
    ap.add_argument("--with-gaps", action="store_true")
    ap.add_argument("--write", action="store_true")
    ns = ap.parse_args()

    results = journal_results(ns.journal)
    wps: list[dict] = []
    for sec in SECTIONS:
        r = results.get("patch:" + sec)
        if not r:
            print(f"MISSING patcher result for {sec}")
            return 1
        for w in r["work_packages"]:
            w = dict(w)
            w["section"] = sec
            wps.append(w)
    if ns.with_gaps:
        cov = results.get("critic:coverage")
        if not cov:
            print("MISSING coverage critic result")
            return 1
        for g in cov.get("gaps", []):
            pw = g.get("proposed_wp")
            if g.get("severity") in ("high", "medium") and pw:
                pw = dict(pw)
                pw["section"] = "gaps"
                pw["spec"] = g.get("spec", "") + "\n(source: " + g.get("source", "") + "; missing: " + g.get("missing", "") + ")"
                wps.append(pw)
    plan = {"version": 1, "gate_on_review": [i for i in GATE_ON_REVIEW if any(w["id"] == i for w in wps)],
            "work_packages": normalise(wps)}
    problems = plan_tools.validate(plan)
    for p in problems:
        print("PLAN PROBLEM:", p)
    for i, wave in enumerate(plan_tools.waves(plan) if not problems or True else []):
        print(f"wave {i}: {' '.join(wave)}")
    print("critical path:", " -> ".join(plan_tools.critical_path(plan)))
    print(f"{len(plan['work_packages'])} work packages, {len(problems)} problems")
    if ns.write:
        if problems:
            print("not written: fix the problems first")
            return 1
        plan_tools.PLAN.write_text(json.dumps(plan, indent=1) + "\n")
        plan_tools.BOARD.write_text(plan_tools.render(plan))
        print("wrote", plan_tools.PLAN, "and", plan_tools.BOARD)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
