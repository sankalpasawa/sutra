"""Release check: run the three release briefs to the end, each in its own process, with Decide for me on.

python3 tools/release_check.py [--cap USD] [--ledger PATH] [--mock]

A brief passes only when its run ends "Done:" (workable); "Done with open items" fails. Spend is read from each run's calls.jsonl
(the "usd" the CLI reports). The ledger keeps the total across checks: --cap is the most all checks together may
spend; each brief gets an equal share of what is left and is stopped when it passes its share. Exit code 0 only
when every brief passed and the cap was not reached.
"""
import argparse, glob, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFS = ["A landing page for Bean There, a coffee shop at 12 Park Road. Open 7am-6pm daily. "
          "Menu: espresso £2.50, flat white £3.20, croissant £2.80.",
          "a hiring policy for a small startup",
          "a script that copies files from one folder to another, with a test"]


def passed(r):
    """Workable only: "Done: ..." passes; "Done with open items: ..." and everything else fails."""
    return str(r.get("outcome") or "").startswith("Done:")


def spent(run_dir):
    usd = 0.0
    for p in glob.glob(os.path.join(run_dir or "", "*calls.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    usd += float(json.loads(line).get("usd") or 0)
                except (ValueError, AttributeError):
                    pass
    return usd


def one(brief, cap, out):
    """Child: run one brief; write {brief, run, outcome, usd, secs, capped} to out."""
    sys.path.insert(0, HERE)
    os.chdir(HERE)
    import j2
    run, t0, capped = j2.J2Run(), time.time(), False
    run.set_auto(True)
    assert run.user_says(brief)
    while True:
        time.sleep(2)
        if spent(run.dir) > cap:
            capped = True
            break
        if run.status == "waiting":
            p = run.paused
            if not p or not run._auto_pick():      # nothing Decide for me can answer: the run has ended or needs a person
                if p and p["kind"] in j2.AUTO_ASK and run.user_says("Yes"):
                    continue
                break
    res = {"brief": brief, "run": run.dir, "outcome": run.outcome if not capped else f"Capped at ${cap:.2f}",
           "paused": (run.paused or {}).get("kind"), "usd": round(spent(run.dir), 3),
           "secs": round(time.time() - t0), "capped": capped}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f)
    os._exit(0)      # daemon threads (a run stopped at its cap) die with the process


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cap", type=float, default=60.0)
    a.add_argument("--ledger", default=os.path.join(HERE, "runs", "release", "ledger.json"))
    a.add_argument("--mock", action="store_true")
    a.add_argument("--one", nargs=3, help=argparse.SUPPRESS)
    x = a.parse_args()
    if x.one:
        return one(x.one[0], float(x.one[1]), x.one[2])
    ledger = json.load(open(x.ledger)) if os.path.exists(x.ledger) else {"checks": []}
    used = sum(c["usd"] for c in ledger["checks"])
    left = x.cap - used
    if left <= 0:
        print(f"CAP REACHED: ${used:.2f} of ${x.cap:.2f} already spent")
        return 2
    # release runs stay out of runs/ itself: the flow tests read every saved run there
    rdir = os.path.join(HERE, "runs", "release-mock" if x.mock else "release")
    os.makedirs(rdir, exist_ok=True)
    # no lessons or playbooks written to memory/
    env = {**os.environ, "J2_RUNS_DIR": rdir, "J2_MEMORY": "0", **({"STUDIO_MOCK": "1"} if x.mock else {})}
    share = left / len(BRIEFS)
    procs = []
    for i, b in enumerate(BRIEFS):
        out = os.path.join(rdir, f".result-{os.getpid()}-{i}.json")
        time.sleep(2 if i else 0)      # run folders are named to the second
        procs.append((subprocess.Popen([sys.executable, __file__, "--one", b, str(share), out], env=env, cwd=HERE), out))
    res = []
    for p, out in procs:
        p.wait()
        res.append(json.load(open(out)) if os.path.exists(out) else {"brief": "?", "outcome": f"exit {p.returncode}",
                                                                      "usd": 0, "capped": False})
        if os.path.exists(out):
            os.remove(out)
    usd = sum(r["usd"] for r in res)
    if not x.mock:
        ledger["checks"].append({"at": time.strftime("%Y-%m-%d %H:%M"), "usd": round(usd, 3), "results": res})
        os.makedirs(os.path.dirname(x.ledger), exist_ok=True)
        json.dump(ledger, open(x.ledger, "w"), indent=1)
    ok = all(passed(r) for r in res)
    for r in res:
        print(f"{'PASS' if passed(r) else 'FAIL'}  ${r['usd']:.2f}  "
              f"{r.get('secs', '?')}s  {r['brief']}\n      {r.get('outcome')}  ({os.path.basename(r.get('run') or '')})")
    print(f"this check ${usd:.2f}; all live checks ${used + (0 if x.mock else usd):.2f} of ${x.cap:.2f}")
    if any(r.get("capped") for r in res):
        print("CAP REACHED")
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
