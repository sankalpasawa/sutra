#!/usr/bin/env python3
"""Record the prompt goldens into `tests/engine/golden/prompts_*.json` (work package E5, engine design 9, requirement ENG-01).

    scripts/py scripts/record_engine_golden.py --source /path/to/J2_Prototype [--commit 33aeeda...] [--out-dir DIR]
                                               [--scenario NAME ...] [--check] [--engine]

Runs six mock-mode scenarios against J2 itself (git archive of `--commit` into a temp folder when `--source` is a git repository, so
an edited working tree never matters) in a child process, with every J2 path under a temp folder and J2's Chrome checks faked as its
own `--fast` flow does. Per scenario it keeps the outcome, the spend, the hash of the last page, the hashes of the sections and of the
workflows and, for every model call in order, `[function, sha(system), sha(prompt)]` (12 hex characters of the sha256 of the text with
its ISO timestamps replaced by `T`: the same normalisation as J2's `plain_unchanged`). The engine is expected to ask the model for
exactly the same text in the same order: `tests/engine/test_engine_prompts.py` runs the same scenarios against the vendored engine
and compares.

    brewlab_fixes0    the Brew Lab brief, J2_FIXES=0, realization off (the classic path of J2's flow test)
    brewlab_fixes1    the same with J2_FIXES=1
    realization       the same with J2_REALIZATION=1 (J2's default: the planner of j2_realization.py runs)
    prd               J2_OUTPUT=prd with the QuickQueue brief (a document run, no website)
    design_docs       "write the design docs first": PRD, HLD and LLD in a chain, then the website, budget 900
    template_library  J2_TEMPLATE_LIBRARY=1 with the Thread & Loom boutique brief into an empty library

`--engine` records the vendored engine's run instead (to compare by eye or to bootstrap): it writes nothing unless `--out-dir` is
given. `--check` records again and exits 1 when a file differs. The module is imported by the test for `SCENARIOS`, `engine_result`
and `differences`, so the recorder and the test ask the same questions.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = "33aeeda639cd7bf828d5361273a8a153ebc63a36"
OUT_DIR = REPO / "tests" / "engine" / "golden"
SCHEMA = "prompts-golden/1"
FILE = "prompts_{}.json"

BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
BREW_FACTS = (" Users: coffee lovers and office staff. Problem: people can't see the menu or order ahead. Must-have "
              "features: see the menu with prices, pre-order a coffee, find the shop, read the opening hours. "
              "Constraints: one page only. Success: 30 pre-orders per week.")
PRD_BRIEF = ("Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: "
             "patients at small clinics and the front-desk staff who manage the line. Problem: patients wait 45 minutes on "
             "average in crowded waiting rooms. Must-have features: join the queue from a phone, live position updates, SMS "
             "alert when 2 patients are ahead, staff dashboard to call the next patient. Constraints: works on low-end "
             "Android phones; no patient health data stored. Success: average in-room wait under 10 minutes; 60% of "
             "patients join remotely within 3 months.")
BOUTIQUE_BRIEF = ("make a website for my cousin's clothing boutique called Thread & Loom in Pune. it sells handloom "
                  "kurtas (1499, 1699), sarees (3499), cotton shirts (1299) and dupattas (899). people should be able "
                  "to browse products by category, filter by size and price, see a size guide, check new arrivals, "
                  "and order on whatsapp (+91 00000 11111). it should feel earthy and elegant and work well on phones")

COMMON_ENV = {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0"}
# name -> flags, the brief and the budget the run is given (J2 starts with 100; a document or library run is given more, as the flow test does)
SCENARIOS = {
    "brewlab_fixes0": {"env": {"J2_FIXES": "0"}, "brief": BREW_LAB, "budget": None},
    "brewlab_fixes1": {"env": {"J2_FIXES": "1"}, "brief": BREW_LAB, "budget": None},
    "realization": {"env": {"J2_FIXES": "0", "J2_REALIZATION": "1"}, "brief": BREW_LAB, "budget": None},
    "prd": {"env": {"J2_FIXES": "0", "J2_OUTPUT": "prd"}, "brief": PRD_BRIEF, "budget": None},
    "design_docs": {"env": {"J2_FIXES": "0"}, "brief": BREW_LAB + " Write the design docs first." + BREW_FACTS, "budget": 900},
    "template_library": {"env": {"J2_FIXES": "0", "J2_TEMPLATE_LIBRARY": "1"}, "brief": BOUTIQUE_BRIEF, "budget": 1400},
}
TIME_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")


def dump(result: dict) -> str:
    """The golden file's text: sorted keys, one call per line (a call is three short values)."""
    head = {k: v for k, v in sorted(result.items()) if k != "calls"}
    body = json.dumps(head, indent=1, sort_keys=True)[:-2]       # drop the closing "\n}"
    calls = ",\n".join("  " + json.dumps(c) for c in result["calls"])
    return body + f',\n "calls": [\n{calls}\n ]\n}}\n'


def digest(text) -> str:
    """12 hex characters of the sha256 of `text` with every ISO timestamp (to the second) replaced by `T`."""
    return hashlib.sha256(TIME_RE.sub("T", str(text)).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------------------------------------------- the child
def child(kind: str, folder: str, name: str, work: str) -> int:
    """Run scenario `name` in this process with `j2` taken from `folder` (kind "j2") or from `sutra_app.engine` (kind "engine")
    and print its result as JSON. Everything J2 writes goes under `work`."""
    spec = SCENARIOS[name]
    env = {**COMMON_ENV, **spec["env"], "J2_RUNS_DIR": os.path.join(work, "runs"), "J2_LIBRARY_DIR": os.path.join(work, "library"),
           "J2_MEMORY_FILE": os.path.join(work, "lessons.jsonl"), "J2_PLAYBOOK_FILE": os.path.join(work, "playbooks.jsonl")}
    os.environ.update(env)
    if kind == "j2":
        sys.path.insert(0, folder)
        import j2
        import j2_check
    else:
        sys.path.insert(0, str(REPO))
        from sutra_app.engine import j2, j2_check

    def fake_check(html):          # J2's --fast stub: the render check without a browser
        st = j2_check.static_checks(html)
        return {"available": True, **st, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0},
                "js_errors": [], "design": {}, "form_results": [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [],
                                                               "errors_during": [], "ok": True} for i in range(st["forms"])]}
    j2_check.find_chrome = lambda: None
    j2_check.tap_targets = lambda html, selector, min_px=44: {"available": True, "roots": 1, "checked": 0, "small_count": 0, "small": []}
    j2_check.check = fake_check

    def say(run, text):
        assert run.user_says(text)
        end = time.time() + 280
        while run.status != "waiting":
            assert time.time() < end, "the run did not stop"
            time.sleep(0.01)

    run = j2.J2Run()
    if spec["budget"]:
        run.budget = spec["budget"]
    say(run, spec["brief"])
    for _ in range(6):                      # answer what a person would (flow test `finish`): a conflict with the simpler option, a limit with "keep working"
        if not run.paused:
            break
        say(run, "Option 2" if run.paused["kind"] == "conflict" else "1")
    rows = [json.loads(line) for line in open(os.path.join(run.dir, "calls.jsonl"), encoding="utf-8") if line.strip()]
    out = {"schema": SCHEMA, "scenario": name, "env": {**COMMON_ENV, **spec["env"]}, "brief_sha": digest(spec["brief"]),
           "budget": spec["budget"], "outcome": run.outcome, "spent": run.spent,
           "site": digest(run.sites[-1]) if run.sites else None,
           "sections": digest(json.dumps(run.sections, sort_keys=True, default=str)),
           "workflows": digest(json.dumps([{k: v for k, v in w.items() if k != "t"} for w in run.workflows], sort_keys=True,
                                          default=str)),
           "calls": [[c["fn"], digest(c["system"]), digest(c["prompt"])] for c in rows]}
    print(json.dumps(out, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------------------------------------------- the parent
def run_child(kind: str, folder, name: str, extra_env: dict = None) -> dict:
    """Run scenario `name` in a child process; `extra_env` is added to the child's (cleaned) environment, e.g. J2_AGENTS_DIR."""
    work = tempfile.mkdtemp(prefix="engine-golden-")
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_"))}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(extra_env or {})
        env["PYTHONPATH"] = str(REPO) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
        res = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", kind, str(folder), name, work],
                             capture_output=True, text=True, env=env, cwd=work, timeout=600)
        if res.returncode:
            raise RuntimeError(f"the {kind} child for {name} failed:\n{res.stderr[-3000:]}")
        return json.loads(res.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(work, ignore_errors=True)


def engine_result(name: str) -> dict:
    """The vendored engine's run of scenario `name`."""
    return run_child("engine", REPO, name)


def checkout_of(source, commit):
    """(folder to run J2 from, temp folder to remove or None, full commit)."""
    source = Path(source).resolve()
    if (source / ".git").exists():
        tmp = Path(tempfile.mkdtemp(prefix="j2-golden-src-"))
        arch = subprocess.run(["git", "-C", str(source), "archive", commit], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=arch, check=True)
        full = subprocess.run(["git", "-C", str(source), "rev-parse", commit], capture_output=True, text=True, check=True).stdout.strip()
        return tmp, tmp, full
    return source, None, commit


def differences(golden: dict, got: dict) -> list:
    """What differs between a golden and a result, as short sentences (empty: equal). Calls are compared one by one."""
    out = [f"{k}: golden {golden.get(k)!r}, got {got.get(k)!r}" for k in ("scenario", "outcome", "spent", "site", "sections", "workflows")
           if golden.get(k) != got.get(k)]
    gc, rc = golden.get("calls") or [], got.get("calls") or []
    if len(gc) != len(rc):
        out.append(f"calls: golden {len(gc)}, got {len(rc)}")
    for i, (a, b) in enumerate(zip(gc, rc)):
        if a != b:
            what = [n for n, x, y in zip(("function", "system", "prompt"), a, b) if x != y]
            out.append(f"call {i + 1} ({a[0]}): {', '.join(what)} differ")
            break
    return out


def record(source, commit, names) -> dict:
    folder, tmp, full = checkout_of(source, commit)
    try:
        results = {}
        for name in names:
            results[name] = {**run_child("j2", folder, name), "j2_commit": full}
        return results
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default=os.environ.get("SUTRA_J2_CHECKOUT"), help="a J2_Prototype checkout")
    ap.add_argument("--commit", default=BASELINE)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--scenario", action="append", choices=sorted(SCENARIOS))
    ap.add_argument("--check", action="store_true", help="record again and exit 1 when a file differs")
    ap.add_argument("--engine", action="store_true", help="record the vendored engine instead of J2")
    ap.add_argument("--child", nargs=4, metavar=("KIND", "FOLDER", "NAME", "WORK"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.child:
        return child(*a.child)
    names = a.scenario or list(SCENARIOS)
    if a.engine:
        data = {n: engine_result(n) for n in names}
    else:
        if not a.source:
            ap.error("--source (or SUTRA_J2_CHECKOUT) is required")
        data = record(a.source, a.commit, names)
    out_dir = Path(a.out_dir) if a.out_dir else (None if a.engine else OUT_DIR)
    bad = 0
    for name, result in data.items():
        text = dump(result)
        print(f"{name}: {len(result['calls'])} calls, spent {result['spent']}, {str(result['outcome'])[:60]}")
        if out_dir is None:
            continue
        target = out_dir / FILE.format(name)
        if a.check:
            same = target.is_file() and target.read_text(encoding="utf-8") == text
            print(f"  {target.name}: " + ("up to date" if same else "DIFFERENT"))
            bad += not same
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
