"""Offline checks of the run template a run saves by itself when it ends: python auto_save_test.py

Mock runs into empty temp libraries and a temp runs folder (j2_flow_test's session folders). A mock run is never
saved, so to check what a live run does, a finished mock run is shown to the hook as a live one (as_live: its
chat's meta line says mock false and STUDIO_MOCK is unset while the hook runs); no model is called.
(1) a mock run is never saved: the event says "not saved: mock run" and the chat says nothing, whether the mock is
    known from STUDIO_MOCK or from the chat's meta line;
(2) a live run that ended workable saves version 1, named as run_template_from_run names it, and the chat says
    "Saved run template <name> v1.";
(3) saving twice does not duplicate;
(4) a second and a third workable run of the same business are saved as versions 2 and 3 ("... v2.", "... v3."),
    the earlier versions left as they were;
(5) auto-pick uses the newest workable version: only it can be picked; when its run is not workable the one before
    it is; a run with J2_AUTO_REUSE=1 picks it;
(6) a run that ended not workable saves none; a stopped or crashed outcome saves none;
(7) a run saved by hand under another name is not saved again;
(8) with the flag off nothing is saved.
No AI calls. Nothing written outside the temp folders.
"""
import json
import os
import shutil
import sys
import tempfile

import j2_flow_test as t          # sets STUDIO_MOCK, J2_MEMORY=0, J2_REALIZATION=0, temp runs and library folders
import j2                          # noqa: E402
import j2_template_lib as L        # noqa: E402

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


class as_live:
    """A finished mock run shown as a live run: its chat's meta line says mock false, and STUDIO_MOCK is unset and
    llm.MOCK false while the block runs (nothing in the block calls a model)."""
    def __init__(self, run, meta=False, env=None):
        self.run, self.meta, self.env = run, meta, env

    def __enter__(self):
        path = os.path.join(self.run.dir, "chat.jsonl")
        lines = open(path, encoding="utf-8").read().split("\n")
        first = json.loads(lines[0])
        assert first.get("meta"), "the chat's first line is its meta line"
        self.path, self.lines = path, list(lines)
        lines[0] = json.dumps({**first, "mock": self.meta})
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        self.keep_env, self.keep_mock = os.environ.pop("STUDIO_MOCK", None), j2.llm.MOCK
        if self.env:
            os.environ["STUDIO_MOCK"] = self.env
        j2.llm.MOCK = bool(self.meta or self.env)
        return self.run

    def __exit__(self, *exc):
        j2.llm.MOCK = self.keep_mock
        os.environ.pop("STUDIO_MOCK", None)
        if self.keep_env is not None:
            os.environ["STUDIO_MOCK"] = self.keep_env


def save_live(run):
    with as_live(run):
        run._save_run_template()


def events(run, text):
    return [e for e in run.events if e["type"] == "run_template" and text in e["detail"]]


tmp = tempfile.mkdtemp(prefix="j2-auto-save-")
keep = {k: os.environ.get(k) for k in FLAGS + ("J2_LIBRARY_DIR",)}
for k in FLAGS:
    os.environ.pop(k, None)
try:
    # ---- (8) the flag off: nothing is saved
    fresh_library("off")
    r0 = run_of(YOGA_DOCS)
    ok(j2.ended_workable(r0.dir), "flag off: the run ended workable")
    save_live(r0)
    ok(not L.run_template_list() and not said(r0) and not os.path.isdir(os.path.join(L.lib_dir(), L.RUN_TEMPLATE_DIR)),
       f"flag off: no run template is saved, as a live run either, and the chat says nothing of one: {L.run_template_list()}")

    # ---- (1) a mock run is never saved
    os.environ["J2_RUN_TEMPLATES"] = "1"
    fresh_library("on")
    r1 = run_of(YOGA_DOCS)
    s1 = json.load(open(os.path.join(r1.dir, "summary.json"), encoding="utf-8"))
    ok(s1["status"] == "done" and j2.ended_workable(r1.dir) and L.run_ended_workable(r1.dir) is True, f"the run is done and workable: {s1['status']}")
    ok(not L.run_template_list() and not said(r1), f"a mock run that ended workable saves no run template and the chat says nothing: {L.run_template_list()}")
    ok(len(events(r1, "not saved: mock run")) == 1, f"the run's event says why: {[e['detail'] for e in r1.events if e['type'] == 'run_template']}")
    for label, kw in (("its chat's meta line says mock", {"meta": True}), ("STUDIO_MOCK=1", {"env": "1"})):
        with as_live(r1, **kw):
            r1._save_run_template()
            got = L.auto_save_run_template(r1.dir)
        ok(not L.run_template_list() and not said(r1) and got == (None, False, "mock run"), f"mock known only because {label}: not saved: {got}")

    # ---- (2) a live run that ended workable saves version 1
    save_live(r1)
    rows = L.run_template_list()
    ok(len(rows) == 1 and made_from(r1) == rows, f"one run template, made from this run: {[(r['name'], r['made_from_run']) for r in rows]}")
    with as_live(r1):
        want = L.run_template_from_run(r1.dir)
    rt = L.get_run_template(rows[0]["id"])
    ok(rt.name == want.name and rt.id == want.id == L.slug(want.name) and rt.version == 1 and rows[0]["version"] == 1,
       f"named as run_template_from_run names it, version 1: {rt.name!r} v{rt.version}")
    ok(rt.workflows == want.workflows and rt.stages == want.stages and rt.mock is False,
       f"the same workflows and stages as the command line would save, made by a live run: {len(rt.workflows)} workflows, {rt.stages}")
    ok(said(r1) == [f"{SAID}{rt.name} v1."], f"the chat says so, once, with the version: {said(r1)}")
    path = os.path.join(L.run_template_dir(rt.id), "template.json")
    ok(os.path.isfile(path), "library/run-templates/<id>/template.json is written")

    # ---- (3) saving twice does not duplicate
    before = open(path, encoding="utf-8").read()
    save_live(r1)
    ok(len(L.run_template_list()) == 1 and said(r1) == [f"{SAID}{rt.name} v1."] and open(path, encoding="utf-8").read() == before,
       "the hook again: still one template, the file as it was, no second chat line")
    ok(events(r1, "already saved"), "the run records why nothing was saved")
    with as_live(r1):
        again, saved, why = L.auto_save_run_template(r1.dir)
        by_hand = L.save_run_template(L.run_template_from_run(r1.dir))
    ok(not saved and again.id == rt.id and "already saved" in why, f"auto_save_run_template again: not saved, the stored one returned: {why}")
    ok(len(L.run_template_list()) == 1 and by_hand.created == rt.created and by_hand.version == 1, "saved again by the command line's way: one template, its created time kept")

    # ---- (4) the same business again: versions 2 and 3
    r2 = run_of(YOGA_DOCS)
    ok(j2.ended_workable(r2.dir) and os.path.basename(r2.dir) != os.path.basename(r1.dir) and len(L.run_template_list()) == 1,
       "a second run of the same brief ended workable (a mock run: nothing saved yet)")
    save_live(r2)
    vs = L.run_template_versions(rt.name)
    ok([(v["version"], v["made_from_run"]) for v in vs] == [(1, os.path.basename(r1.dir)), (2, os.path.basename(r2.dir))] and len(L.run_template_list()) == 2,
       f"it is saved as version 2 of the same run template, not skipped: {[(v['id'], v['version']) for v in vs]}")
    v2 = L.get_run_template(vs[1]["id"])
    ok(v2.name == rt.name and v2.id == f"{rt.id}-v2" and v2.version == 2 and v2.made_from_run == os.path.basename(r2.dir), f"the same name, id {v2.id}")
    ok(said(r2) == [f"{SAID}{rt.name} v2."], f"the chat says version 2: {said(r2)}")
    ok(open(path, encoding="utf-8").read() == before, "version 1 is left as it was")
    save_live(r2)
    ok(len(L.run_template_list()) == 2 and len(said(r2)) == 1, "the second run again: no version 3 from the same run")
    r3 = run_of(YOGA_DOCS)
    save_live(r3)
    vs = L.run_template_versions(rt.name)
    ok([v["version"] for v in vs] == [1, 2, 3] and vs[2]["id"] == f"{rt.id}-v3" and said(r3) == [f"{SAID}{rt.name} v3."],
       f"a third workable run is version 3: {[(v['id'], v['version']) for v in vs]} {said(r3)}")

    # ---- (5) auto-pick uses the newest workable version
    goal = json.load(open(os.path.join(r1.dir, "goal.json"), encoding="utf-8"))
    scored = lambda: {x["id"]: x for x in L.match_run_templates(list(rt.stages), YOGA_DOCS, goal.get("done_when"), live=True)}
    sc = scored()
    ok([i for i, x in sc.items() if x["eligible"]] == [vs[2]["id"]], f"only version 3 can be picked: {[(x['version'], x['eligible']) for x in sc.values()]}")
    ok(all("version 3 of this run template is newer" in sc[v["id"]]["why_not"] for v in vs[:2]), f"versions 1 and 2 say why not: {sc[vs[0]['id']].get('why_not')}")
    ok(len({x["score"] for x in sc.values()}) == 1, "the three versions score the same: the version decides, not the score")
    spath = os.path.join(r3.dir, "summary.json")
    s3_then = open(spath, encoding="utf-8").read()
    json.dump({**json.loads(s3_then), "workable": ["done-when item 1 failed"]}, open(spath, "w", encoding="utf-8"))
    try:
        ok(L.run_ended_workable(r3.dir) is False, "version 3's run is now recorded as not workable")
        sc = scored()
        ok([i for i, x in sc.items() if x["eligible"]] == [vs[1]["id"]], f"then version 2 is the one that can be picked: {[(x['version'], x['eligible']) for x in sc.values()]}")
        ok("did not end workable, so version 2 is used" in sc[vs[2]["id"]]["why_not"], f"version 3 says why not: {sc[vs[2]['id']].get('why_not')}")
    finally:
        open(spath, "w", encoding="utf-8").write(s3_then)
    ok(L.run_ended_workable(os.path.join(tmp, "no-such-run")) is None, "a run that is not here is not known to be workable")
    os.environ["J2_AUTO_REUSE"] = "1"
    try:
        r4 = run_of(YOGA_DOCS)
    finally:
        os.environ.pop("J2_AUTO_REUSE", None)
    a4 = json.load(open(os.path.join(r4.dir, "templates.json"), encoding="utf-8"))
    ok(a4["auto_reuse"]["picked"] == vs[2]["id"] and a4["run_template"]["id"] == vs[2]["id"],
       f"a run with auto reuse picks version 3: {a4['auto_reuse']['picked']} (match {a4['auto_reuse']['match']})")
    ok(L.get_run_template(vs[2]["id"]).used_by[-1]["run"] == os.path.basename(r4.dir) and not L.get_run_template(vs[0]["id"]).used_by,
       "version 3 records the run that used it; version 1 records none")

    # ---- (6) not workable, stopped, crashed: never saved
    fresh_library("not-workable")
    r5 = run_of(YOGA_DOCS, prep=always_fails)
    end_as_it_is(r5)
    ok(not r5.paused and r5.done, f"the run with a failing item ended: {r5.outcome} (paused: {(r5.paused or {}).get('kind')})")
    s5 = json.load(open(os.path.join(r5.dir, "summary.json"), encoding="utf-8"))
    ok(not j2.ended_workable(r5.dir) and s5["workable"] and L.run_ended_workable(r5.dir) is False,
       f"the run ended not workable: {s5['status']}, {len(s5['workable'])} thing(s) in the way")
    save_live(r5)
    ok(not L.run_template_list() and not said(r5), f"a not-workable live run saves no run template: {L.run_template_list()}")
    with as_live(r5):
        ok(L.run_template_from_run(r5.dir).workflows, "although it has finished workflows a template could be made from")
    done_as = r1.outcome
    for label, outcome in (("stopped", "Stopped: out of budget."), ("crashed", "Crashed: ValueError: x"), ("no outcome", None)):
        r1.outcome = outcome
        save_live(r1)
        ok(not L.run_template_list(), f"a workable audit but a {label} run: nothing is saved")
    r1.outcome = done_as
    save_live(r1)
    ok(len(made_from(r1)) == 1, "the same run with its Done outcome is saved (the outcome was what held it back)")

    # ---- (7) a run saved by hand under another name is not saved again
    fresh_library("by-hand")
    with as_live(r1):
        L.save_run_template(L.run_template_from_run(r1.dir, name="My yoga documents"))
    save_live(r1)
    ok([r["name"] for r in L.run_template_list()] == ["My yoga documents"], f"the run keeps the one name it was saved under: {[r['name'] for r in L.run_template_list()]}")
    print(f"auto_save_test: {passed} checks passed (saved {rt.name!r} v1 to v3, {len(rt.workflows)} workflows; auto reuse picked "
          f"{a4['auto_reuse']['picked']}; not-workable run {s5['status']})")
finally:
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)
