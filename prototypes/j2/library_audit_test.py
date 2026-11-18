"""Offline checks of four Library fixes from the UI audit of 18 Nov 2026 (rows 5, 6, 7, 9): python library_audit_test.py

Each row is checked twice: on small records made here (runs anywhere), and on read-only copies of two saved live
runs when they are on this computer: j2-20261117-151050 (Zen Barre Studio, ended workable, started from a run
template) and j2-20261117-173751 (Crumb & Co Bakery, stopped in its PRD stage, no summary.json). They are looked for
in J2_AUDIT_RUNS, then in runs/ beside this file; a run that is not here is said so and its checks are left out.
(9) the Library tab's counts: every decision has a group, the groups add up to all the decisions, and the chips'
    numbers (reuse_totals) are the same count as the header's (reuse_counts);
(7) the score of an adapted template is its own coverage, the source's is kept apart; a decision that holds only
    the source's is labelled "source match";
(6) a business type that is nothing, a "says nothing" value or only an output type's name is shown as "not recorded";
(5) an artifact of a run that did not end workable is marked on the shelf with how the run ended, stays listed, and
    feeds no new run: not find_artifact, not auto-pick, not the content door.
No AI calls. Nothing written outside a temp folder; the saved runs are copied, never changed.
"""
import json
import os
import shutil
import sys
import tempfile

import j2_flow_test as t          # noqa: F401  sets STUDIO_MOCK and temp runs and library folders
import j2_artifact_lib as A        # noqa: E402
import j2_template_lib as L        # noqa: E402
import j2_types                    # noqa: E402

passed, left_out = 0, []
WORKABLE, STOPPED = "j2-20261117-151050", "j2-20261117-173751"


def ok(cond, label):
    global passed
    if not cond:
        sys.exit(f"FAIL: {label}")
    passed += 1


here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="j2-library-audit-")
keep = {k: os.environ.get(k) for k in ("J2_LIBRARY_DIR", "J2_RUNS_DIR")}
try:
    lib = os.path.join(tmp, "lib")
    shutil.copytree(os.path.join(here, "library"), lib)
    runs = os.path.join(tmp, "runs")
    os.makedirs(runs)
    os.environ["J2_LIBRARY_DIR"], os.environ["J2_RUNS_DIR"] = lib, runs
    saved = {}
    for rid in (WORKABLE, STOPPED):      # read-only copies of the two saved runs, when they are here
        src = next((p for p in (os.path.join(d, rid) for d in (os.environ.get("J2_AUDIT_RUNS"), os.path.join(here, "runs")) if d) if os.path.isdir(p)), None)
        if src:
            shutil.copytree(src, os.path.join(runs, rid), symlinks=True)
            saved[rid] = os.path.join(runs, rid)
        else:
            left_out.append(rid)
    ui = open(os.path.join(here, "j2_ui.html"), encoding="utf-8").read()
    types = j2_types._read_types()
    page_form = next(f for f, e in types["forms"].items() if isinstance(e, dict) and e.get("style_guide"))
    guide = types["forms"][page_form]["style_guide"]
    doc_type = next(x["name"] for x in types["types"] if x.get("form") != page_form and x.get("output", True))
    page_type = next(x["name"] for x in types["types"] if x.get("form") == page_form)

    # ---- (9) one count, every decision in a group
    D = lambda artifact, action, **kw: {"workflow": "W-1", "artifact": artifact, "section": "S", "action": action, **kw}
    decs = [D(doc_type, "extended", from_template=True), D(doc_type, "created", from_template=False), D(page_type, "reused", from_template=True),
            D(guide, "generic"), D("no-such-type", "generic")]
    groups = [L.decision_group(d) for d in decs]
    ok(all(groups), f"every decision has a group: {groups}")
    ok(groups[3] == groups[2] == page_form, f"the style guide is in the group of the form that names it ({page_form}): {groups[3]}")
    ok(groups[4] == L.OTHER_GROUP, f"an artifact no type and no form names is in the group {L.OTHER_GROUP!r}, not dropped: {groups[4]}")
    counts, totals = L.reuse_counts(decs), L.reuse_totals(L.reuse_counts(decs))
    ok(sum(g["total"] for g in counts.values()) == len(decs) == totals["total"], f"the groups add up to all {len(decs)} decisions: {totals}")
    ok(all(totals[k] == sum(1 for d in decs if L.decision_kind(d) == k) for k in L.REUSE_KINDS), f"each chip's number is the groups' own sum: {totals}")
    ok(sum(totals[k] for k in L.REUSE_KINDS) == totals["total"], "created + adapted + reused + generic = all")
    ok({s["key"] for s in L.decision_scopes(decs)} == set(counts), "there is a scope button for every group that is counted")
    ok([r["group"] for r in L.reuse_rows(decs)] == groups, "each row carries the same group the counts used")
    ok("u.totals" in ui and "(u.counts || {})[rtScope()]" in ui, "the page's chips read the server's counts (totals for All, the group's counts in a scope)")
    if WORKABLE in saved:
        use = L.run_template_use(saved[WORKABLE])
        n = len(json.load(open(os.path.join(saved[WORKABLE], "templates.json"), encoding="utf-8"))["decisions"])
        ok(use["totals"]["total"] == n == sum(g["total"] for g in use["counts"].values()) == 25, f"{WORKABLE}: 25 decisions, the groups add to 25 (the audit saw 25 beside 24): {use['totals']}")
        ok(use["counts"][page_form]["generic"] == 1 == use["totals"]["generic"], f"its style guide row is counted in {page_form}: generic 1 in both places")
    if STOPPED in saved:
        use = L.run_template_use(saved[STOPPED])
        ok(use["totals"]["total"] == 5 == sum(g["total"] for g in use["counts"].values()), f"{STOPPED}: 5 decisions in both counts: {use['totals']}")

    # ---- (7) an adapted template's score is its own
    row = next(e for e in L.index()["templates"] if e["kind"] == "specialised" and e["artifact"] == doc_type)
    t0 = L.get(f"{row['name']}@{row['versions'][-1]['version']}", row["artifact"], row["section"])
    facts = [f"The business is Audit Row Seven Ltd, fact {i}" for i in range(1, 5)]
    need = L.make_need(t0.artifact, t0.section, "accounting firm", facts, "Audit Row Seven Ltd")
    tpl, rec = L.route(need, {"run": "test-row7", "workflow": "W-1", "atom": "W-1.a1"}, first={"template": f"{t0.name}@{t0.version}"}, closest=True)
    ok(rec["action"] == "extended" and rec.get("adapted_from") == f"{t0.name}@{t0.version}", f"a template is adapted from another business's: {rec['action']} from {rec.get('adapted_from')}")
    own = L.coverage(need, {"facts": tpl.context.facts_used, "fields": [f.name for f in tpl.fields], "enums": L._enums(tpl)})[0]
    src = L.coverage(need, {"facts": t0.context.facts_used, "fields": [f.name for f in t0.fields], "enums": L._enums(t0)})[0]
    ok(rec["score"] == own == 1.0 and rec["covers"].startswith(f"covers {len(facts)} of {len(facts)} facts"), f"its score is its own coverage, as covers says: {rec['score']} / {rec['covers']}")
    ok(rec["source_score"] == src < own, f"the source's coverage is kept apart as source_score: {rec['source_score']}")
    ok(L.score_label(rec) == "", "a decision that holds both is not labelled")
    old = {k: v for k, v in rec.items() if k != "source_score"}
    old["score"] = src      # as recorded before: only the source's number
    ok(L.score_label(old) == L.SOURCE_MATCH == "source match", f"a decision that holds only the source's number is labelled: {L.score_label(old)!r}")
    ok(L.score_label({**old, "adapted_from": f"{old['template']}@{old['version']}"}) == "", "a template reused as it is has its own score: no label")
    ok(L.score_label({"template": "T", "version": 1, "score": 0.5}) == "" and L.score_label({**old, "score": None}) == "", "no source, or no score: no label")
    ok(L.reuse_rows([old])[0]["score_label"] == "source match" and L.reuse_rows([rec])[0]["score_label"] == "", "the rows the page reads carry the label")
    ok("source match" in ui and "rtScoreLabel" in ui and 'data-tplscore=' in ui, "the page's Score cell shows the label")
    if WORKABLE in saved:
        rows = L.reuse_rows(json.load(open(os.path.join(saved[WORKABLE], "templates.json"), encoding="utf-8"))["decisions"])
        adapted = [r for r in rows if r["kind_shown"] == "adapted"]
        ok(len(adapted) == 24 and all(r["score_label"] == "source match" for r in adapted), f"{WORKABLE}: its 24 adapted rows hold the source's number and say so")
        ok(all(r["score"] < 0.5 and r["covers"].startswith("covers ") for r in adapted), "the numbers themselves are as recorded (0.08 beside covers 12 of 12 facts)")
        ok(all(r["score_label"] == "" for r in rows if r["kind_shown"] != "adapted"), "its other rows are not labelled")

    # ---- (6) a business type that records no business
    for name in j2_types.names():
        ok(L.business_type_shown(name) == L.NOT_RECORDED and L.business_type_shown(name.upper()) == L.NOT_RECORDED, f"an output type's name is no business type: {name}")
    for v in list(L.settings()["no_business_type"]) + ["", None, "  "]:
        ok(L.business_type_shown(v) == L.NOT_RECORDED, f"{v!r} is shown as not recorded")
    ok(L.business_type_shown("barre studio") == "barre studio" and L.business_type_shown(" Law firm ") == "Law firm", "a real business type is shown as recorded")
    ok(L._same_business("yoga studio", "Yoga Studio") == 2 and L._same_business(doc_type, doc_type) == 0, "the same-business test gives what it gave")
    ok('data-shelfbiz="none"' in ui, "the shelf's Summary has a Business type row that says not recorded")
    if STOPPED in saved:
        raw = json.load(open(os.path.join(saved[STOPPED], "goal.json"), encoding="utf-8")).get("business_type")
        arts = L.run_artifacts(saved[STOPPED])
        ok(arts and L._no_business_type(raw) and all(a["business_type"] == L.NOT_RECORDED for a in arts), f"{STOPPED}: its charter says {raw!r}; the shelf shows not recorded")
        ok(json.load(open(os.path.join(saved[STOPPED], "goal.json"), encoding="utf-8")).get("business_type") == raw, "the record is not changed")
    if WORKABLE in saved:
        raw = json.load(open(os.path.join(saved[WORKABLE], "goal.json"), encoding="utf-8")).get("business_type")
        ok(all(a["business_type"] == raw for a in L.run_artifacts(saved[WORKABLE])) and not L._no_business_type(raw), f"{WORKABLE}: its real business type is shown ({raw!r})")

    # ---- (5) work from a run that did not end workable
    def run_folder(name, summary):
        d = os.path.join(runs, name)
        os.makedirs(d)
        if summary is not None:
            json.dump(summary, open(os.path.join(d, "summary.json"), "w", encoding="utf-8"))
        return d
    ends = {"done and workable": ({"status": "done", "workable": [], "outcome": "Done: workable."}, True),
            "open items left": ({"status": "done_with_open_items", "workable": ["item 1"], "outcome": "Done with open items: x"}, False),
            "open items accepted": ({"status": "done_with_open_items", "workable": [], "outcome": "Done with open items: accepted"}, True),
            "crashed, last audit clean": ({"status": "crashed", "workable": [], "outcome": "Crashed: x"}, False),
            "stopped (no summary)": (None, False), "an old summary, done": ({"status": "done"}, True)}
    for i, (label, (summary, want)) in enumerate(ends.items()):
        e = L.run_end(run_folder(f"j2-20000101-00000{i}", summary))
        ok(e["finished"] is want and e["outcome"], f"run_end, {label}: finished {e['finished']} ({e['outcome'][:50]})")
    ok(L.run_ended_workable(os.path.join(runs, "j2-20000101-000003")) is False, "a run that crashed is not workable although its last audit was clean")
    ok('data-shelfend="unfinished"' in ui and "unfinished run" in ui and 'data-shelfoutcome=' in ui, "the shelf has the badge and the outcome line")
    ok("Finished work from the projects" not in ui, "the shelf no longer calls everything on it finished work")
    if STOPPED in saved and WORKABLE in saved:
        arts = L._all_artifacts(runs)
        mine = [a for a in arts if a["run"] == STOPPED]
        ok(mine and all(a["run_end"]["finished"] is False and "no summary.json" in a["run_end"]["outcome"] for a in mine), f"{STOPPED}: its {len(mine)} artifact(s) are listed, marked unfinished, with why")
        good = [a for a in arts if a["run"] == WORKABLE]
        ok(good and all(a["run_end"]["finished"] is True and a["run_end"]["outcome"].startswith("Done") for a in good), f"{WORKABLE}: its {len(good)} artifacts are not marked")
        kind = mine[0]["type"]
        found = {c["run"] for c in L.find_artifact({"artifact": kind}, runs)}
        ok(STOPPED not in found and WORKABLE in found, f"find_artifact offers the workable run's {kind} and not the stopped run's: {sorted(found)}")
        # auto-pick: a run template saved by hand from the stopped run can never be picked
        bad = L.save_run_template(L.run_template_from_run(saved[STOPPED], name="Saved by hand from a stopped run"))
        fine = L.save_run_template(L.run_template_from_run(saved[WORKABLE], name="Saved from a workable run"))
        sc = {x["id"]: x for x in L.match_run_templates(list(bad.stages), "bakery cakes", [], live=True)}
        ok(sc[bad.id]["eligible"] is False and "did not end workable" in sc[bad.id]["why_not"], f"auto-pick never takes it: {sc[bad.id].get('why_not')}")
        sc2 = {x["id"]: x for x in L.match_run_templates(list(fine.stages), "barre studio", [], live=True)}
        ok(sc2[fine.id]["eligible"] is True, "a run template of the workable run can be picked")
        ok(L.auto_save_run_template(saved[STOPPED])[1] is False, "the library saves nothing by itself for it (it is already saved by hand here)")
    # the content door and the auto-save: their own checks in j2.py, pinned here so they are not lost
    j2src = open(os.path.join(here, "j2.py"), encoding="utf-8").read()
    ok('workable=ended_workable(saved_dir(src["run"])) if src else None' in j2src, "j2.py gives the content door the source run's workable state")
    ok('or not ended_workable(self.dir)' in j2src, "j2.py saves a run template by itself only for a run that ended workable")
    door = A.door({"fingerprint": "x"}, {"action": "reused", "template": "T", "version": 1},
                  {"run": "r", "workflow": "W-1", "key": "W-1", "sha": "s", "template": "T@1", "fingerprint": "x", "audit": "pass", "receipts_passed": [], "data": {}, "dir": tmp},
                  workable=False)
    ok(door["door"] == "build" and door["rule"] == "source-not-workable", f"the content door serves and drafts nothing from a run that did not end workable: {door['door']} {door['rule']}")
    print(f"library_audit_test: {passed} checks passed" + (f" (saved runs not on this computer, their checks left out: {', '.join(left_out)})" if left_out else f" (with saved runs {WORKABLE} and {STOPPED})"))
finally:
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)
