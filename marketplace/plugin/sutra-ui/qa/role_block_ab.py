#!/usr/bin/env python3
"""qa/role_block_ab.py -- does the role block in a function's card help? The same scenarios, with and without it (PRD A3.4.3, A3 F8).

The role block (what a function is, is not, may do, never does, how it decides, what it avoids, whom it hands on to, and the
working agreement) costs 2,400 to 2,900 characters on every soft call of a function engine. Nothing offline can show whether it
helps or hurts a real model: the scripted-model suites prove structure, not behaviour. So this script runs the same J2 scenarios
twice in one process, with layer_schema.ROLE_IN_CARD True and then False (a constant set in code, never an environment
variable), on whatever model the app is configured with, and prints for each arm:

    steps run                 the rows the department's steps wrote
    checks / pass             how many covering checks ran, and the share that passed
    outside the contract      the rows whose check failed: an answer outside the shape its contract asks for
    soft calls, prompt chars  the model calls the functions and the work engines made, and the characters sent in all of them
    calls, usd                what the rows say the model reported (0 offline)

The scenarios are the happy path (the Library's line, said yes, built and read), a counter (Priority asks for less on the first
plan and says yes to the smaller one) and a refused plan (Priority says no; the owner says no too). Only Priority's answer is
scripted, to make the turn happen; every other step goes to the app's model, or to its draft offline.

OFFLINE BY DEFAULT: with the offline model every step runs its draft, so the two arms differ in prompt size only, which proves
the script and nothing else. `--live` leaves the app's own model in place; it spends the subscription (a department's run is
tens of calls), so it is never the default and nobody runs it by accident. The live numbers are pending (decision C2: live runs
need the owner's subscription) and go in the merge message when someone runs them.

A report, not a gate: the exit code is always 0. The records are a temporary home of the script's own, removed when it ends.

    python qa/role_block_ab.py                       # all three scenarios, offline
    python qa/role_block_ab.py happy counter         # some of them
    python qa/role_block_ab.py --json                # the numbers as JSON
    python qa/role_block_ab.py --live happy          # on the app's configured model (spends money)
"""
import argparse
import contextlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

UI = Path(__file__).resolve().parent.parent
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))

WEBSITE = "Build a website that teaches algebra to Class 8 students"
#: what the script sets for its own records and puts back when it ends
ENV = ("SUTRA_NATIVE_DEPT_HOME", "SUTRA_NATIVE_HOME", "SUTRA_UI_PROPOSALS", "SUTRA_WEBSITE_OFFLINE", "J1_FLOW_V1", "J2_FLOW_V1",
       "SUTRA_ENGINE_RUNTIME")


def _counter(prompt):
    """Priority asks for less on the first plan (the one that names Publish), and says yes to the plan that keeps three."""
    if "- Publish:" in prompt:
        return {"answer": "counter", "why": "room for three today", "keep": ["Plan", "Write", "Check"]}
    return {"answer": "accept", "why": "the envelope has room"}


#: name -> (what it is, the steps whose answer is scripted, whether the owner says yes to what waits for a stamp)
SCENARIOS = {
    "happy": ("the happy path: the Library's line, said yes, built and read", {}, True),
    "counter": ("Priority asks for less on the first plan and says yes to the smaller one", {"priority.bargain": _counter}, True),
    "refused": ("Priority says no to the plan, and the owner says no too", {"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}}, False),
}


@contextlib.contextmanager
def records(live):
    """A records home of the script's own: the environment pointed at it and the runtime reloaded on it, and everything put back
    when the block ends. Offline unless `live`."""
    saved = {k: os.environ.get(k) for k in ENV}
    home = tempfile.mkdtemp(prefix="role-block-ab-")
    os.environ.update(SUTRA_NATIVE_DEPT_HOME=home + "/departments", SUTRA_NATIVE_HOME=home + "/registry",
                      SUTRA_UI_PROPOSALS=home + "/proposals", J1_FLOW_V1="1", J2_FLOW_V1="1")
    os.environ.pop("SUTRA_ENGINE_RUNTIME", None)
    if live:
        os.environ.pop("SUTRA_WEBSITE_OFFLINE", None)
    else:
        os.environ["SUTRA_WEBSITE_OFFLINE"] = "1"
    try:
        importlib.import_module("founding")                             # puts the plugin's lib on the path, where placement_engine is
        modules = {}
        for name in ("placement_engine", "website_dept", "org2_apply", "founding", "engine_runtime", "j2_runtime"):
            modules[name] = importlib.reload(importlib.import_module(name))
        E = modules["placement_engine"]
        if not E.active_roots(E.load_domains()):
            E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
        yield modules
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(home, ignore_errors=True)


def run_arm(name, arm, live=False):
    """One scenario on one arm ('on': the role block is in the card; 'off': it is not): the numbers it leaves."""
    import layer_schema as S
    _, scripted, yes = SCENARIOS[name]
    before = S.ROLE_IN_CARD
    with records(live) as m:
        W, R, founding = m["website_dept"], m["engine_runtime"], m["founding"]
        calls = []                                                     # (engine, step id, characters) of every soft call
        real = R.call_model

        def call_model(prompt, step):
            calls.append((R.step_def(step["id"])[0], step["id"], len(prompt)))
            answer = scripted.get(step["id"])
            if answer is None:
                return real(prompt, step)
            return (answer(prompt) if callable(answer) else answer), 0.0, "model"
        S.ROLE_IN_CARD = arm == "on"
        R.call_model = call_model
        try:
            root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
            W.owner_ask(root, WEBSITE)
            W.run_until_idle(root, limit=300)
            child = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
            W.run_until_idle(child, limit=300)
            for _ in range(4):                                         # the owner answers what waits, so the work goes on
                waiting = [a for a in W.asks(child) if a["status"] == "pending" and (yes or a["kind"] == "conflict")]
                if not waiting:
                    break
                for a in waiting:
                    W.decide_ask(child, a["id"], yes)
                W.run_until_idle(child, limit=300)
            rows = R.step_rows(child)
        finally:
            R.call_model = real
            S.ROLE_IN_CARD = before
    checked = [r for r in rows if isinstance(r.get("check"), dict) and "ok" in r["check"]]
    outside = [r for r in checked if r["check"]["ok"] is False]
    function = [c for c in calls if c[0] in ("Identity", "Adaptation", "Priority", "Coordination", "Audit")]
    return {"scenario": name, "arm": arm, "steps": len(rows), "checks": len(checked), "passed": len(checked) - len(outside),
            "pass_rate": round((len(checked) - len(outside)) / len(checked), 3) if checked else None,
            "outside_the_contract": [{"step": r["step"], "notes": (r["check"].get("notes") or [])[:2]} for r in outside],
            "soft_calls": len(calls), "function_calls": len(function), "prompt_chars": sum(c[2] for c in calls),
            "function_prompt_chars": sum(c[2] for c in function),
            "calls": sum(int(r.get("calls") or 0) for r in rows), "usd": round(sum(float(r.get("usd") or 0) for r in rows), 4)}


def run_arms(names=None, live=False):
    """{scenario: {'on': numbers, 'off': numbers}} for the scenarios named (all of them by default), both arms in one process."""
    return {n: {arm: run_arm(n, arm, live) for arm in ("on", "off")} for n in (names or list(SCENARIOS))}


def report(results, live=False):
    """The numbers as the lines a person reads."""
    out = ["role block in the card: with (on) and without (off) it, on %s" % ("the app's configured model" if live else "the offline model (steps run their drafts; only Priority's answer is scripted)"),
           "%-8s %-4s %6s %7s %7s %8s %6s %9s %7s %6s" % ("scenario", "arm", "steps", "checks", "pass", "outside", "calls", "chars", "model", "usd")]
    for name, arms in results.items():
        for arm in ("on", "off"):
            a = arms[arm]
            out.append("%-8s %-4s %6d %7d %7s %8d %6d %9d %7d %6.2f" % (
                name, arm, a["steps"], a["checks"], "n/a" if a["pass_rate"] is None else "%d%%" % round(a["pass_rate"] * 100),
                len(a["outside_the_contract"]), a["soft_calls"], a["prompt_chars"], a["calls"], a["usd"]))
        on, off = arms["on"], arms["off"]
        same = all(on[k] == off[k] for k in ("steps", "checks", "passed", "soft_calls")) and on["outside_the_contract"] == off["outside_the_contract"]
        extra = on["prompt_chars"] - off["prompt_chars"]
        out.append("         the block adds %d characters over %d function calls (%.0f%% more)%s" % (
            extra, on["function_calls"], 100.0 * extra / off["prompt_chars"] if off["prompt_chars"] else 0.0,
            "; nothing else differs: the arms differ in prompt size only" if same else "; the arms differ in more than prompt size"))
        for arm in ("on", "off"):
            for row in arms[arm]["outside_the_contract"]:
                out.append("         %s: an answer outside the contract at %s: %s" % (arm, row["step"], "; ".join(row["notes"]) or "no note"))
    if not live:
        out.append("offline: this proves the script. The live numbers are pending (run with --live; it spends the subscription).")
    return out


def main(argv=None, out=None):
    """Prints the report; always 0, because it is a report and not a gate."""
    out = out or sys.stdout
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("scenarios", nargs="*", help="some of: " + ", ".join(SCENARIOS) + " (all of them by default)")
    p.add_argument("--live", action="store_true", help="use the app's configured model (spends the subscription)")
    p.add_argument("--json", action="store_true", help="print the numbers as JSON")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 0
    unknown = [n for n in args.scenarios if n not in SCENARIOS]
    if unknown:
        out.write("no scenario named %s; the scenarios are %s\n" % (", ".join(unknown), ", ".join(SCENARIOS)))
        return 0
    try:
        results = run_arms(args.scenarios or None, live=args.live)
        if args.json:
            out.write(json.dumps(results, indent=1) + "\n")
        else:
            out.write("\n".join(report(results, live=args.live)) + "\n")
    except Exception as exc:  # noqa: BLE001 -- a report that fails says so and still ends well
        out.write("the comparison could not be made: %s\n" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
