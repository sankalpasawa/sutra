#!/usr/bin/env python3
"""What a run costs in dollars (API price) per work credit, measured on recorded runs (D255).

    scripts/py scripts/usd_basis.py --data ~/.sutra-pro-beta

Reads `<data>/db.sqlite3` read-only (`mode=ro`) and the run folders `<data>/departments/*/runs/*/` (task.json's `task_id`, report.json's
`metrics.budget.spent`). Per run: its cost (the sum of the usd each AI call reported; stub rows never count), calls with and without a price,
tokens (in + out) and credits spent. Then the median, p25, p75, min and max of dollars per credit over runs that spent credits, the fallback
dollars per million tokens (all priced dollars over all their tokens; the estimate rate for a call with no price), and the proposed default: 1000 credits
in dollars, rounded to a clean amount, with presets half and double. Numbers only: no prompt, no reply, no path into a home folder.

Refuses the stable app's folder (~/.sutra-pro): it belongs to the owner. Exit codes: 0 measured, 2 refused or no database.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path

CREDITS = 1000      # the default is about this many credits in dollars

PER_TASK = """SELECT task_id, provider, json_extract(detail_json, '$.usd_basis') AS basis, usd, COALESCE(tokens_in, 0) + COALESCE(tokens_out, 0) AS tokens
FROM usage_ledger WHERE provider != 'stub' AND task_id IS NOT NULL"""


def open_ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)


def stable_folder(path: Path) -> bool:
    stable = (Path.home() / ".sutra-pro").resolve()
    found = path.resolve()
    return found == stable or stable in found.parents


def spread(values: list[float]) -> dict:
    if not values:
        return {"runs": 0, "median": None, "p25": None, "p75": None, "min": None, "max": None}
    p25, median, p75 = statistics.quantiles(values, n=4, method="inclusive") if len(values) > 1 else (values[0],) * 3
    return {"runs": len(values), "median": median, "p25": p25, "p75": p75, "min": min(values), "max": max(values)}


def clean_amount(dollars: float) -> int:
    """Nearest $5 below $50, else nearest $10 (halves round up); never below $5."""
    step = 5 if dollars < 50 else 10
    return max(5, int(math.floor(dollars / step + 0.5)) * step)


def presets(default: int) -> tuple:
    half = default / 2
    return (int(half) if half == int(half) else half, default, default * 2)


def spent_by_task(data: Path) -> dict[str, int]:
    out = {}
    for task_file in sorted(data.glob("departments/*/runs/*/task.json")):
        try:
            task_id = json.loads(task_file.read_text(encoding="utf-8"))["task_id"]
            report = json.loads((task_file.parent / "report.json").read_text(encoding="utf-8"))
            out[task_id] = int(report["metrics"]["budget"]["spent"])
        except (OSError, ValueError, KeyError, TypeError):
            continue      # a run still going or one that never wrote its report
    return out


def measure(data: Path) -> dict:
    conn = open_ro(data / "db.sqlite3")
    try:
        rows = conn.execute(PER_TASK).fetchall()
    finally:
        conn.close()
    spent = spent_by_task(data)
    runs = {t: {"task_id": t, "usd": 0.0, "priced": 0, "unpriced": 0, "tokens": 0, "spent": s} for t, s in spent.items()}
    calls: dict[tuple, dict] = {}
    priced_usd = priced_tokens = 0
    for task_id, provider, basis, usd, tokens in rows:
        key = (provider, basis or "unknown")
        calls.setdefault(key, {"priced": 0, "unpriced": 0})["priced" if usd is not None else "unpriced"] += 1
        if usd is not None and tokens > 0:
            priced_usd += usd
            priced_tokens += tokens
        run = runs.get(task_id)
        if run is None:
            continue      # a task with no run folder here: its calls count for the fallback rate only
        run["tokens"] += tokens
        if usd is None:
            run["unpriced"] += 1
        else:
            run["priced"] += 1
            run["usd"] += usd
    for run in runs.values():
        run["usd"] = round(run["usd"], 6)
        run["usd_per_credit"] = run["usd"] / run["spent"] if run["spent"] > 0 else None
    ordered = sorted(runs.values(), key=lambda r: r["task_id"])
    per_credit = spread([r["usd_per_credit"] for r in ordered if r["usd_per_credit"] is not None])
    return {"runs": ordered, "calls": calls, "per_credit": per_credit,
            "fallback_usd_per_mtok": priced_usd / priced_tokens * 1_000_000 if priced_tokens else None}


def report(m: dict) -> str:
    lines = [f"{'task':<18} {'cost $':>9} {'priced':>6} {'unpriced':>8} {'tokens':>10} {'credits':>7} {'$/credit':>9}"]
    for r in m["runs"]:
        per = f"{r['usd_per_credit']:.4f}" if r["usd_per_credit"] is not None else "-"
        lines.append(f"{r['task_id']:<18} {r['usd']:>9.2f} {r['priced']:>6} {r['unpriced']:>8} {r['tokens']:>10} {r['spent']:>7} {per:>9}")
    lines.append("")
    lines.append("calls by provider and basis (all tasks): " + ", ".join(
        f"{p}/{b}: {c['priced']} priced, {c['unpriced']} unpriced" for (p, b), c in sorted(m["calls"].items())))
    s = m["per_credit"]
    if s["runs"] == 0:
        lines.append("dollars per credit: no run spent credits")
        return "\n".join(lines)
    lines.append(f"dollars per credit over {s['runs']} runs: median {s['median']:.4f}, p25 {s['p25']:.4f}, p75 {s['p75']:.4f}, "
                 f"min {s['min']:.4f}, max {s['max']:.4f}")
    if m["fallback_usd_per_mtok"] is not None:
        lines.append(f"fallback dollars per million tokens (all priced dollars / all their tokens): {m['fallback_usd_per_mtok']:.2f}")
    raw = CREDITS * s["median"]
    default = clean_amount(raw)
    half, _, double = presets(default)
    early = sum(1 for r in m["runs"] if r["usd_per_credit"] is not None and r["usd_per_credit"] * CREDITS > default)
    over = sum(1 for r in m["runs"] if r["usd"] > default)
    lines.append(f"{CREDITS} x median = ${raw:.2f}; proposed default ${default} (presets ${half} / ${default} / ${double})")
    lines.append(f"runs that would reach ${default} before {CREDITS} credits: {early} of {s['runs']}; "
                 f"runs that cost more than ${default} as recorded: {over} of {len(m['runs'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, type=Path, help="an app data folder (the beta's: ~/.sutra-pro-beta)")
    args = parser.parse_args(argv)
    data = args.data.expanduser()
    if stable_folder(data):
        print("usd_basis: refused: ~/.sutra-pro is the stable app's data; measure the beta's (~/.sutra-pro-beta)", file=sys.stderr)
        return 2
    if not (data / "db.sqlite3").is_file():
        print("usd_basis: no db.sqlite3 in that folder", file=sys.stderr)
        return 2
    print(report(measure(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
