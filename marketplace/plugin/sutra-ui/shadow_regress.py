#!/usr/bin/env python3
"""Shadow regression gate: did this change break anything Shadow had working?

WHY (founder, 2026-10-08: "I'm making loads of changes on this shadow
feature, we gotta make sure stuff isn't regressing"). Two facts made "run the
tests" not enough:

  * CI never runs the Shadow PYTHON tests -- release-dmg.yml runs the Shadow
    JS list and marketplace/plugin/lib/tests only. ~110 Python files guard
    Shadow and nothing runs them unless someone does it by hand.
  * Some of them fail on a given machine for reasons that are not the change
    (Windows event loops, CRLF checkouts, a missing CLI). "93 failed" says
    nothing; "these 2 failed and did not before" says everything.

WHAT IT DOES. Runs every Shadow test file -- Python and JS -- ONE FILE AT A
TIME (a whole-suite run on a small machine was killed for memory, and one
hanging test took a whole pytest session with it), records which tests fail,
and compares that with a BASELINE recorded on this machine before the change.

    python shadow_regress.py --record     # before you change anything
    python shadow_regress.py              # after: exit 1 on anything new
    python shadow_regress.py --only js    # or py; --files a.py,b.js to narrow
    python shadow_regress.py --record --root <clean checkout>/.../sutra-ui

A test that fails now and passed in the baseline is a REGRESSION. A file
that is new since the baseline is held to "everything passes". A failure
that was already there is reported as known, never as a regression.

THE BASELINE IS PER MACHINE (~/.sutra-ui/shadow-regress-baseline.json by
default, --baseline to move it), because the known failures are.

WHICH FILES. test_shadow*.py / test_shadow*.js, plus any other Python test
that imports Shadow's modules (mission_engine, session_runtime, shadow_*) and
any other JS test that loads the two Shadow screens.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASELINE = os.path.join(os.path.expanduser("~"), ".sutra-ui",
                                "shadow-regress-baseline.json")
PY_TIMEOUT_S = 600
JS_TIMEOUT_S = 180
_PY_IMPORTS = re.compile(
    r"^(import|from) (mission_engine|session_runtime|shadow_[a-z_]+)\b", re.M)
_JS_LOADS = re.compile(r"15-shadow-overlay|16-shadow-home")
#: a test file that runs itself on import and calls sys.exit -- pytest cannot
#: collect it, so it is run as a script and judged by its exit code
_SCRIPT = re.compile(r"^(sys\.exit|raise SystemExit)|^    sys\.exit\(1 if",
                     re.M)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def discover(root=HERE):
    """(python files, js files), sorted."""
    py, js = [], []
    for name in sorted(os.listdir(root)):
        if not name.startswith("test_"):
            continue
        path = os.path.join(root, name)
        if name.endswith(".py") and name != "test_shadow_regress.py":
            if name.startswith("test_shadow") or _PY_IMPORTS.search(_read(path)):
                py.append(name)
        elif name.endswith(".js"):
            if name.startswith("test_shadow") or _JS_LOADS.search(_read(path)):
                js.append(name)
    return py, js


def _env():
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_py(name, python, root=HERE):
    """{"status": ok|fail|timeout|error, "failed": [test ids]}."""
    path = os.path.join(root, name)
    if _SCRIPT.search(_read(path)):
        argv = [python, name]
    else:
        argv = [python, "-m", "pytest", "-q", "-rfE", "-p", "no:warnings",
                "-p", "no:cacheprovider", "--color=no", name]
    try:
        p = subprocess.run(argv, cwd=root, env=_env(), capture_output=True,
                           timeout=PY_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "failed": [name + "::<timeout>"]}
    out = p.stdout.decode("utf-8", "replace").replace("\r", "")
    if argv[1] == name:
        return {"status": "ok" if p.returncode == 0 else "fail",
                "failed": [] if p.returncode == 0 else [name + "::<script>"]}
    failed = sorted({m.group(2) for m in
                     re.finditer(r"^(FAILED|ERROR) (\S+)", out, re.M)})
    if p.returncode in (0, 5):          # 5: nothing collected
        return {"status": "ok", "failed": failed}
    if not failed:
        # pytest ended badly with no test to blame: collection or internal
        return {"status": "error", "failed": [name + "::<collection>"]}
    return {"status": "fail", "failed": failed}


def run_js(name, node="node", root=HERE):
    try:
        p = subprocess.run([node, name], cwd=root, capture_output=True,
                           timeout=JS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "failed": [name]}
    return {"status": "ok" if p.returncode == 0 else "fail",
            "failed": [] if p.returncode == 0 else [name]}


def compare(baseline, current):
    """What changed between two result maps ({file: {"failed": [...]}}).

    -> {"regressed": [ids], "new_files_failing": [ids], "fixed": [ids],
        "known": [ids]}. Pure, so test_shadow_regress.py pins it directly.
    """
    base_files = (baseline or {}).get("files") or {}
    out = {"regressed": [], "new_files_failing": [], "fixed": [], "known": []}
    for name, res in sorted((current or {}).get("files", {}).items()):
        now = set(res.get("failed") or [])
        if name not in base_files:
            out["new_files_failing"].extend(sorted(now))
            continue
        was = set(base_files[name].get("failed") or [])
        out["regressed"].extend(sorted(now - was))
        out["known"].extend(sorted(now & was))
        out["fixed"].extend(sorted(was - now))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--record", action="store_true",
                    help="save this run as the baseline")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE)
    ap.add_argument("--only", choices=("py", "js"))
    ap.add_argument("--files", default="",
                    help="comma-separated test files to run instead of all")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--node", default="node")
    ap.add_argument("--root", default=HERE,
                    help="the sutra-ui folder to test (default: this one) -- "
                         "e.g. a clean checkout, to record its baseline")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)

    py, js = discover(root)
    if args.files:
        want = [f.strip() for f in args.files.split(",") if f.strip()]
        py = [f for f in want if f.endswith(".py")]
        js = [f for f in want if f.endswith(".js")]
    if args.only == "py":
        js = []
    elif args.only == "js":
        py = []

    files, t0 = {}, time.time()
    total = len(py) + len(js)
    for i, name in enumerate(py + js, 1):
        res = (run_py(name, args.python, root) if name.endswith(".py")
               else run_js(name, args.node, root))
        files[name] = res
        mark = "ok  " if not res["failed"] else "FAIL"
        print("[%3d/%d] %s %s%s" % (i, total, mark, name,
              "" if not res["failed"] else "  (%d)" % len(res["failed"])),
              flush=True)
    current = {"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
               "files": files}
    print("\n%d files in %ds" % (total, time.time() - t0))

    if args.record:
        base = {}
        if (args.files or args.only) and os.path.exists(args.baseline):
            with open(args.baseline, encoding="utf-8") as fh:
                base = json.load(fh)
        merged = dict(base.get("files") or {})
        merged.update(files)
        os.makedirs(os.path.dirname(args.baseline), exist_ok=True)
        with open(args.baseline, "w", encoding="utf-8") as fh:
            json.dump({"recorded_at": current["recorded_at"],
                       "files": merged}, fh, indent=1, sort_keys=True)
        known = sum(len(r["failed"]) for r in merged.values())
        print("baseline saved: %s (%d files, %d known failures)"
              % (args.baseline, len(merged), known))
        return 0

    if not os.path.exists(args.baseline):
        print("no baseline at %s -- run with --record on a clean checkout "
              "first" % args.baseline)
        return 2
    with open(args.baseline, encoding="utf-8") as fh:
        baseline = json.load(fh)
    diff = compare(baseline, current)
    print("baseline: %s" % baseline.get("recorded_at"))
    print("  known failures, unchanged: %d" % len(diff["known"]))
    print("  fixed since the baseline:  %d" % len(diff["fixed"]))
    for t in diff["fixed"]:
        print("    + %s" % t)
    bad = diff["regressed"] + diff["new_files_failing"]
    if diff["new_files_failing"]:
        print("  NEW test files failing:    %d" % len(diff["new_files_failing"]))
        for t in diff["new_files_failing"]:
            print("    ! %s" % t)
    print("  REGRESSIONS:               %d" % len(diff["regressed"]))
    for t in diff["regressed"]:
        print("    ! %s" % t)
    print("\n%s" % ("NO REGRESSIONS" if not bad else "REGRESSED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
