"""Release check: run the four release briefs to the end, each in its own process, with Decide for me on.

python3 tools/release_check.py [--cap USD] [--ledger PATH] [--mock]

A brief passes only when its run ends "Done:" (workable); "Done with open items" fails. The fourth brief asks for a
script run for real on a demo folder the check makes outside the repo: the check answers the run's question with
the exact RUN <code> it posted, as the Requester would (Decide for me never does), and, live, passes only when the
real run's receipt says approved, exit 0, and the demo folder was sorted. Spend is read from each run's calls.jsonl
(the "usd" the CLI reports). The ledger keeps the total across checks: --cap is the most all checks together may
spend; each brief gets an equal share of what is left and is stopped when it passes its share. Exit code 0 only
when every brief passed and the cap was not reached.
"""
import argparse, glob, json, os, re, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEFS = ["A landing page for Bean There, a coffee shop at 12 Park Road. Open 7am-6pm daily. "
          "Menu: espresso £2.50, flat white £3.20, croissant £2.80.",
          "a hiring policy for a small startup",
          "a script that copies files from one folder to another, with a test"]
REAL_BRIEF = ("Sort the files in {folder} into subfolders named for each file's extension (a.txt into txt/, b.csv into "
              "csv/), with a test, and run it on that folder.")
DEMO = {"a.txt": "alpha\n", "b.csv": "x,y\n1,2\n", "c.txt": "gamma\n"}


def passed(r):
    """Workable only: "Done: ..." passes; "Done with open items: ..." and everything else fails. A brief that needs a
    real run passes only when it ran (real_run_ok)."""
    return str(r.get("outcome") or "").startswith("Done:") and (not r.get("needs_real") or r.get("real_run_ok") is True)


def real_run_ok(run_dir, demo):
    """The run's real-run receipts approved and exit 0, and the demo folder sorted (each file in its extension's folder)."""
    try:
        recs = [json.loads(x) for x in open(os.path.join(run_dir, "receipts.jsonl"), encoding="utf-8") if '"real_run"' in x]
    except OSError:
        recs = []
    sorted_ = all(os.path.isfile(os.path.join(demo, n.rsplit(".", 1)[1], n)) for n in DEMO)
    return bool(recs) and all(r.get("approved") and r.get("exit") == 0 for r in recs) and sorted_


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
                if p and p["kind"] == "real_run":      # the Requester's exact reply, from the message code posted
                    ask = next((m["text"] for m in reversed(run.chat) if m.get("real_run")), "")
                    code = re.search(r"reply exactly: (RUN [0-9a-f]+)", ask)
                    if code and run.user_says(code.group(1)):
                        continue
                elif p and p["kind"] in j2.AUTO_ASK and run.user_says("Yes"):
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
    demo = tempfile.mkdtemp(prefix="j2-release-demo-")      # outside the repo: the folder the fourth brief sorts for real
    for n, t in DEMO.items():
        with open(os.path.join(demo, n), "w", encoding="utf-8") as f:
            f.write(t)
    briefs = BRIEFS + [REAL_BRIEF.format(folder=demo)]
    share = left / len(briefs)
    procs = []
    for i, b in enumerate(briefs):
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
    if not x.mock:      # the mock planner plans no real run: only a live check needs one
        res[-1].update(needs_real=True, real_run_ok=real_run_ok(res[-1].get("run") or "", demo), demo=demo)
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
