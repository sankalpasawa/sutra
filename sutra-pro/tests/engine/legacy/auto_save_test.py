"""Offline checks of the run template a run saves by itself when it ends: python auto_save_test.py

Mock runs into empty temp libraries and a temp runs folder (j2_flow_test's session folders), J2_RUN_TEMPLATES=1:
(1) a run that ended workable saves one run template, named as run_template_from_run names it, and the chat says
    "Saved run template <name>.";
(2) saving twice does not duplicate: the hook again, the library function again, and the command line's own
    save_run_template(run_template_from_run()) all leave one template with its created time;
(3) a second workable run of the same business does not replace it and adds none;
(4) a run that ended not workable saves none; a stopped or crashed outcome saves none;
(5) a run saved by hand under another name is not saved again;
(6) with the flag off nothing is saved.
No AI calls. Nothing written outside the temp folders.
"""
import json
import os
import shutil
import sys
import tempfile

import j2_flow_test as t          # sets STUDIO_MOCK, J2_MEMORY=0, J2_REALIZATION=0, temp runs and library folders
from sutra_app.engine import j2      # noqa: E402  (engine port: the vendored engine, not J2's flat modules)
from sutra_app.engine import j2_template_lib as L      # noqa: E402  (engine port: the vendored engine, not J2's flat modules)

passed = 0
FLAGS = ("J2_ARTIFACT_LIBRARY", "J2_AUTO_REUSE", "J2_TEMPLATE_LIBRARY", "J2_RUN_TEMPLATES", "J2_ARTIFACT_SCHEMA", "J2_PUSH_RUNS")
YOGA_DOCS = (t.YOGA_BRIEF.replace("and then build the website for", "for")
             .replace(" The documents and the website must agree with each other.", ""))
SAID = "Saved run template "


def ok(cond, label):
    global passed
    if not cond:
        sys.exit(f"FAIL: {label}")
    passed += 1


def run_of(brief, budget=3000, prep=None):
    run = j2.J2Run()
    run.budget = budget
    if prep:
        prep(run)
    t.say(run, brief)
    t.finish(run)
    return run


def always_fails(run):
    """Audit's result for the first done-when item is NEEDS_REVISION in every cycle, so the run cannot end workable."""
    def forced(results):
        row = next((x for x in results if x["item"] == 1), None)
        if not row:
            return None
        row.update(verdict="NEEDS_REVISION", severity="medium", note="never right", **{"pass": False})
        return 1
    run._force_fail = forced


def end_as_it_is(run):
    """Answer until the run ends: a limit question with "3" (finish as it is), anything else as finish() does."""
    for _ in range(30):
        if not run.paused:
            return
        kind = run.paused["kind"]
        t.say(run, "3" if kind == "limit" else "Option 2" if kind == "conflict" else "1")


def fresh_library(name):
    os.environ["J2_LIBRARY_DIR"] = os.path.join(tmp, name)
    os.makedirs(os.environ["J2_LIBRARY_DIR"])


def said(run):
    return [m["text"] for m in run.chat if m["who"] == "system" and m["text"].startswith(SAID)]


def made_from(run):
    return [r for r in L.run_template_list() if r["made_from_run"] == os.path.basename(run.dir)]


tmp = tempfile.mkdtemp(prefix="j2-auto-save-")
keep = {k: os.environ.get(k) for k in FLAGS + ("J2_LIBRARY_DIR",)}
for k in FLAGS:
    os.environ.pop(k, None)
try:
    # ---- (6) the flag off: nothing is saved
    fresh_library("off")
    r0 = run_of(YOGA_DOCS)
    ok(j2.ended_workable(r0.dir), "flag off: the run ended workable")
    ok(not L.run_template_list() and not said(r0) and not os.path.isdir(os.path.join(L.lib_dir(), L.RUN_TEMPLATE_DIR)),
       f"flag off: no run template is saved and the chat says nothing of one: {L.run_template_list()}")

    # ---- (1) a workable run saves one run template
    os.environ["J2_RUN_TEMPLATES"] = "1"
    fresh_library("on")
    r1 = run_of(YOGA_DOCS)
    s1 = json.load(open(os.path.join(r1.dir, "summary.json"), encoding="utf-8"))
    ok(s1["status"] == "done" and j2.ended_workable(r1.dir), f"the run is done and workable: {s1['status']}")
    rows = L.run_template_list()
    ok(len(rows) == 1 and made_from(r1) == rows, f"one run template, made from this run: {[(r['name'], r['made_from_run']) for r in rows]}")
    want = L.run_template_from_run(r1.dir)
    rt = L.get_run_template(rows[0]["id"])
    ok(rt.name == want.name and rt.id == want.id == L.slug(want.name), f"named as run_template_from_run names it: {rt.name!r}")
    ok(rt.workflows == want.workflows and rt.stages == want.stages and rt.mock is True,
       f"the same workflows and stages as the command line would save: {len(rt.workflows)} workflows, {rt.stages}")
    ok(said(r1) == [f"{SAID}{rt.name}."], f"the chat says so, once: {said(r1)}")
    ok(os.path.isfile(os.path.join(L.run_template_dir(rt.id), "template.json")), "library/run-templates/<id>/template.json is written")

    # ---- (2) saving twice does not duplicate
    path = os.path.join(L.run_template_dir(rt.id), "template.json")
    before = open(path, encoding="utf-8").read()
    r1._save_run_template()
    ok(len(L.run_template_list()) == 1 and said(r1) == [f"{SAID}{rt.name}."] and open(path, encoding="utf-8").read() == before,
       "the hook again: still one template, the file as it was, no second chat line")
    ok(any(e["type"] == "run_template" and "already saved" in e["detail"] for e in r1.events), "the run records why nothing was saved")
    again, saved, why = L.auto_save_run_template(r1.dir)
    ok(not saved and again.id == rt.id and "already saved" in why and len(L.run_template_list()) == 1,
       f"auto_save_run_template again: not saved, the stored one returned: {why}")
    by_hand = L.save_run_template(L.run_template_from_run(r1.dir))
    ok(len(L.run_template_list()) == 1 and by_hand.created == rt.created, "saved again by the command line's way: one template, its created time kept")

    # ---- (3) a second workable run of the same business replaces nothing and adds nothing
    r2 = run_of(YOGA_DOCS)
    ok(j2.ended_workable(r2.dir) and os.path.basename(r2.dir) != os.path.basename(r1.dir), "a second run of the same brief ended workable")
    rows = L.run_template_list()
    ok(len(rows) == 1 and rows[0]["made_from_run"] == os.path.basename(r1.dir) and not made_from(r2) and not said(r2),
       f"the template is still the first run's, none is added: {[(r['name'], r['made_from_run']) for r in rows]}")
    ok(any(e["type"] == "run_template" and "exists, made from run" in e["detail"] for e in r2.events), "the second run records why")

    # ---- (4) not workable, stopped, crashed: never saved
    fresh_library("not-workable")
    r3 = run_of(YOGA_DOCS, prep=always_fails)
    end_as_it_is(r3)
    ok(not r3.paused and r3.done, f"the run with a failing item ended: {r3.outcome} (paused: {(r3.paused or {}).get('kind')})")
    s3 = json.load(open(os.path.join(r3.dir, "summary.json"), encoding="utf-8"))
    ok(not j2.ended_workable(r3.dir) and s3["workable"], f"the run ended not workable: {s3['status']}, {len(s3['workable'])} thing(s) in the way")
    ok(not L.run_template_list() and not said(r3), f"a not-workable run saves no run template: {L.run_template_list()}")
    ok(L.run_template_from_run(r3.dir).workflows, "although it has finished workflows a template could be made from")
    done_as = r1.outcome
    for label, outcome in (("stopped", "Stopped: out of budget."), ("crashed", "Crashed: ValueError: x"), ("no outcome", None)):
        r1.outcome = outcome
        r1._save_run_template()
        ok(not L.run_template_list(), f"a workable audit but a {label} run: nothing is saved")
    r1.outcome = done_as
    r1._save_run_template()
    ok(len(made_from(r1)) == 1, "the same run with its Done outcome is saved (the outcome was what held it back)")

    # ---- (5) a run saved by hand under another name is not saved again
    fresh_library("by-hand")
    L.save_run_template(L.run_template_from_run(r1.dir, name="My yoga documents"))
    r1._save_run_template()
    ok([r["name"] for r in L.run_template_list()] == ["My yoga documents"], f"the run keeps the one name it was saved under: {[r['name'] for r in L.run_template_list()]}")
    print(f"auto_save_test: {passed} checks passed (saved {rt.name!r}, {len(rt.workflows)} workflows; not-workable run {s3['status']})")
finally:
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)
