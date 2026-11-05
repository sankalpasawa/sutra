#!/usr/bin/env python3
"""Build-plan tools: validate docs/build-plan.json, compute the waves, render docs/BUILD-PLAN.md.

    scripts/py scripts/plan_tools.py check     # exit 1 and list every problem
    scripts/py scripts/plan_tools.py waves     # print the waves
    scripts/py scripts/plan_tools.py render    # write docs/BUILD-PLAN.md

The plan is the contract between the design sections and the developer agents: one row per work package with the paths
it owns. The rules below are what lets many agents work in parallel without ever editing the same file.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "docs" / "build-plan.json"
BOARD = ROOT / "docs" / "BUILD-PLAN.md"

# Files that belong to the repo chassis: no work package may own them (changes go through the chassis, by hand).
PROTECTED = {
    "pyproject.toml", ".gitignore", "README.md", "scripts/gate.sh", "scripts/wt.sh", "scripts/py",
    "scripts/plan_tools.py", "tests/conftest.py", "docs/DECISIONS.md", "docs/DESIGN.md", "docs/BUILD-PLAN.md",
    "docs/build-plan.json", "docs/TRACEABILITY.md", "docs/traceability.json",
}
ALLOWED_ROOTS = ("sutra_app/", "tests/", "scripts/", "docs/", ".github/")
ALLOWED_FILES = {"MANIFEST.in"}   # repo-root files a package may own besides the chassis ones


def load(path: Path = PLAN) -> dict:
    return json.loads(path.read_text())


def _is_dir(p: str) -> bool:
    return p.endswith("/")


def validate(plan: dict) -> list[str]:
    problems: list[str] = []
    wps = plan.get("work_packages", [])
    ids = [w.get("id") for w in wps]
    if len(ids) != len(set(ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        problems.append(f"duplicate work package ids: {dup}")
    known = set(ids)
    owner: dict[str, str] = {}
    for w in wps:
        wid = w.get("id", "?")
        for key in ("title", "section", "owns", "depends_on", "acceptance"):
            if key not in w:
                problems.append(f"{wid}: missing '{key}'")
        if not w.get("owns"):
            problems.append(f"{wid}: owns nothing")
        if not w.get("acceptance"):
            problems.append(f"{wid}: no acceptance command")
        for dep in w.get("depends_on", []):
            if dep not in known:
                problems.append(f"{wid}: depends on unknown work package '{dep}'")
            if dep == wid:
                problems.append(f"{wid}: depends on itself")
        if f"docs/notes/{wid}.md" not in w.get("owns", []):
            problems.append(f"{wid}: must own docs/notes/{wid}.md")
        for p in w.get("owns", []):
            if p.startswith("/") or ".." in Path(p).parts or not (p.startswith(ALLOWED_ROOTS) or p in ALLOWED_FILES):
                problems.append(f"{wid}: owned path outside the repo roots: {p}")
            if p in PROTECTED:
                problems.append(f"{wid}: owns a protected chassis file: {p}")
            if p in owner and owner[p] != wid:
                problems.append(f"{p}: owned by both {owner[p]} and {wid}")
            owner.setdefault(p, wid)
    # a directory owner conflicts with any other owner beneath it
    for d, od in [(p, o) for p, o in owner.items() if _is_dir(p)]:
        for p, o in owner.items():
            if p != d and p.startswith(d) and o != od:
                problems.append(f"{d} (owned by {od}) contains {p} (owned by {o})")
    # cycles
    graph = {w["id"]: [d for d in w.get("depends_on", []) if d in known] for w in wps if "id" in w}
    state: dict[str, int] = {}

    def dfs(n: str, stack: list[str]) -> None:
        if state.get(n) == 1:
            problems.append("dependency cycle: " + " -> ".join(stack + [n]))
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for m in graph[n]:
            dfs(m, stack + [n])
        state[n] = 2

    for n in graph:
        dfs(n, [])
    return problems


def waves(plan: dict) -> list[list[str]]:
    wps = {w["id"]: w for w in plan["work_packages"]}
    level: dict[str, int] = {}

    def lvl(n: str) -> int:
        if n not in level:
            deps = [d for d in wps[n].get("depends_on", []) if d in wps]
            level[n] = 0 if not deps else 1 + max(lvl(d) for d in deps)
        return level[n]

    for n in wps:
        lvl(n)
    out: dict[int, list[str]] = defaultdict(list)
    for n, l in level.items():
        out[l].append(n)
    return [sorted(out[l]) for l in sorted(out)]


def critical_path(plan: dict) -> list[str]:
    wps = {w["id"]: w for w in plan["work_packages"]}
    best: dict[str, list[str]] = {}

    def path(n: str) -> list[str]:
        if n not in best:
            deps = [d for d in wps[n].get("depends_on", []) if d in wps]
            best[n] = (max((path(d) for d in deps), key=len) if deps else []) + [n]
        return best[n]

    return max((path(n) for n in wps), key=len)


def merged_ids() -> set[str]:
    """Work packages merged into main: scripts/wt.sh merges with the subject 'Merge wp/<id>'."""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%s", "--grep=^Merge wp/"],
                         capture_output=True, text=True).stdout
    return {line.split("wp/", 1)[1].strip() for line in out.splitlines() if line.startswith("Merge wp/")}


def render(plan: dict) -> str:
    wps = {w["id"]: w for w in plan["work_packages"]}
    done = merged_ids()
    ws = waves(plan)
    lines = [
        "# Build plan",
        "",
        "Generated by `scripts/plan_tools.py render` from `docs/build-plan.json`; do not edit by hand.",
        "",
        f"{len(wps)} work packages in {len(ws)} waves. A package starts when every package it depends on is merged.",
        "One developer agent builds one package in its own git worktree (`scripts/wt.sh new <id>`), and merges it with",
        "`scripts/wt.sh merge <id>`, which rebases on main, merges under a lock, runs the whole gate and undoes the merge",
        "if the gate fails. A package may touch only the paths it owns; `scripts/plan_tools.py check` (also a test)",
        "refuses overlapping ownership, unknown dependencies and cycles.",
        "",
        "Critical path: " + " -> ".join(critical_path(plan)),
        "",
    ]
    for i, wave in enumerate(ws):
        lines += [f"## Wave {i}", "", "| Package | Title | Section | After | Paths | Status |", "|---|---|---|---|---|---|"]
        for wid in wave:
            w = wps[wid]
            status = "merged" if wid in done else "pending"
            lines.append(f"| {wid} | {w['title']} | {w['section']} | {', '.join(w.get('depends_on', [])) or '-'} | "
                         f"{len(w['owns'])} | {status} |")
        lines.append("")
    lines += ["## Acceptance commands", ""]
    for wid in sorted(wps):
        lines.append(f"- **{wid}**: " + "; ".join(f"`{c}`" for c in wps[wid]["acceptance"]))
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    plan = load()
    if cmd == "check":
        problems = validate(plan)
        for p in problems:
            print("PLAN PROBLEM:", p)
        print(f"{len(plan['work_packages'])} work packages, {len(problems)} problems")
        return 1 if problems else 0
    if cmd == "waves":
        for i, w in enumerate(waves(plan)):
            print(f"wave {i}: {' '.join(w)}")
        print("critical path:", " -> ".join(critical_path(plan)))
        return 0
    if cmd == "render":
        BOARD.write_text(render(plan))
        print("wrote", BOARD)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
