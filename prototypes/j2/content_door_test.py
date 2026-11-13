"""Offline flow checks of the content door (J2_ARTIFACT_LIBRARY=1, j2_artifact_lib + the served attempt in j2.py):
python content_door_test.py

Mock document runs into a copy of the library and a temp runs folder (j2_flow_test's session folders):
(a) the flag alone turns on the template library, run templates, auto-reuse and the artifact schema inside a run;
(b) a yoga documents run whose auto-picked run template points at a run that is not here: every door is "unknown",
    the run completes as today;
(c) the run is saved as a run template; the same brief again picks it and every document section is served
    (door reuse, rule same): 0 model calls for them, schema, rules and render receipts passing, the charge refunded,
    the run done;
(d) a pilates brief over the yoga template: each section is reuse (cross) or adapt; no name of the yoga studio
    reaches a prompt or a final section; no more model calls than the same brief with the flag off;
(e) the source data broken (ids out of order): the served section fails a rules receipt, the door drops to adapt,
    the run still completes;
(f) flag off: no reuse.json, no "by"-less meta line regression.
No AI calls. Nothing written outside the temp folders.
"""
import json
import os
import shutil
import sys
import tempfile

import j2_flow_test as t          # sets STUDIO_MOCK, J2_MEMORY=0, J2_REALIZATION=0, temp runs and library folders
import j2                          # noqa: E402
import j2_artifact_lib as A        # noqa: E402
import j2_template_lib as L        # noqa: E402

passed = 0
FLAGS = ("J2_ARTIFACT_LIBRARY", "J2_AUTO_REUSE", "J2_TEMPLATE_LIBRARY", "J2_RUN_TEMPLATES", "J2_ARTIFACT_SCHEMA", "J2_PUSH_RUNS")
YOGA_DOCS = (t.YOGA_BRIEF.replace("and then build the website for", "for")
             .replace(" The documents and the website must agree with each other.", ""))
PILATES_DOCS = t.PILATES_DOCS


def ok(cond, label):
    global passed
    if not cond:
        sys.exit(f"FAIL: {label}")
    passed += 1


def run_of(brief, budget=1400):
    run = j2.J2Run()
    run.budget = budget
    t.say(run, brief)
    t.finish(run)
    return run


def reuse_of(run):
    p = os.path.join(run.dir, "reuse.json")
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else None


def receipts_of(run):
    with open(os.path.join(run.dir, "receipts.jsonl"), encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def summary_of(run):
    return json.load(open(os.path.join(run.dir, "summary.json"), encoding="utf-8"))


def doc_decisions(run):
    """The content decisions of document workflows (the style guide and pages are out of scope)."""
    rec = reuse_of(run) or {"decisions": []}
    return [d for d in rec["decisions"] if d.get("artifact") in ("prd", "hld", "lld")]


here = os.path.dirname(os.path.abspath(__file__))
real_lib = os.path.join(here, "library")
tmp = tempfile.mkdtemp(prefix="j2-content-door-")
lib = os.path.join(tmp, "lib")
shutil.copytree(real_lib, lib)
keep = {k: os.environ.get(k) for k in FLAGS + ("J2_LIBRARY_DIR",)}
for k in FLAGS:
    os.environ.pop(k, None)
os.environ["J2_LIBRARY_DIR"] = lib
try:
    # (f) flag off: nothing of the door is on, no reuse.json after a run
    r0 = run_of(PILATES_DOCS)
    ok(summary_of(r0)["status"] == "done" and reuse_of(r0) is None, "flag off: the run is done and writes no reuse.json")
    ceiling = r0.calls
    with open(os.path.join(r0.dir, "chat.jsonl"), encoding="utf-8") as f:
        head = json.loads(f.readline())
    ok(head.get("meta") and isinstance(head.get("by"), str) and head["by"], f"the first chat line records who ran it: {head.get('by')!r}")

    # (a) the flag alone
    os.environ["J2_ARTIFACT_LIBRARY"] = "1"
    probe = j2.J2Run()
    ok(probe.art_lib and probe.tpl_lib and probe.schemas and j2.run_templates_on() and j2.auto_reuse_on(),
       "J2_ARTIFACT_LIBRARY=1 alone turns on the content door, the template library, the schema, run templates and auto-reuse")

    # (b) the yoga documents: the committed yoga run template is picked, its source run is not in this runs folder
    r1 = run_of(YOGA_DOCS)
    s1 = summary_of(r1)
    ok(s1["status"] == "done", f"run 1 done: {s1['status']} {s1.get('outcome')}")
    tpl1 = json.load(open(os.path.join(r1.dir, "templates.json"), encoding="utf-8"))
    ok((tpl1.get("run_template") or {}).get("id"), "run 1 auto-picked a run template")
    d1 = doc_decisions(r1)
    ok(d1 and all(d["door"] == "unknown" for d in d1), f"source run not here: every door is unknown, never build-for-nothing: {A.counts(d1)}")
    ok(all(not w.get("served_from") and w.get("charged") for w in r1._all_wfs() if w["status"] == "done"), "nothing served, nothing refunded")

    # (c) saved as a run template; the same brief again is served
    rt = L.run_template_from_run(r1.dir, name="A rerun of Still Point Yoga")
    L.save_run_template(rt)
    r2 = run_of(YOGA_DOCS)
    s2 = summary_of(r2)
    tpl2 = json.load(open(os.path.join(r2.dir, "templates.json"), encoding="utf-8"))
    ok((tpl2.get("run_template") or {}).get("id") == rt.id, f"run 2 picked the saved run template: {(tpl2.get('run_template') or {}).get('id')}")
    ok(s2["status"] == "done", f"run 2 done: {s2['status']} {s2.get('outcome')}")
    d2 = doc_decisions(r2)
    served = [d for d in d2 if d["door"] == "reuse" and d.get("held")]
    ok(d2 and served and all(d["door"] == "reuse" and d["rule"] == "same" and d["held"] for d in d2),
       f"same brief: every document section served and held (same inputs): {A.counts(d2)} / {[(d['workflow'], d['door'], d['rule'], d.get('held')) for d in d2]}")
    wf2 = {w["id"]: w for w in r2._all_wfs()}      # every stage's workflows (a stage's are archived when the next starts)
    ok(all(wf2[d["workflow"]]["calls_used"] == 0 for d in served), "a served section costs no model call")
    ok(all(wf2[d["workflow"]].get("charged") is False and d.get("refunded") == wf2[d["workflow"]]["cost"] for d in served),
       "a served section's charge is refunded")
    ok(r2.spent < sum(w["cost"] for w in r2._all_wfs()), f"the budget used is below the sum of the workflows' costs ({r2.spent})")
    rec2 = receipts_of(r2)
    for d in served:
        layers = {r["type"] for r in rec2 if str(r.get("atom") or "").startswith(d["workflow"] + ".") and r.get("pass") and r.get("type", "").startswith("artifact-")}
        ok({"artifact-schema", "artifact-rules", "artifact-render"} <= layers, f"{d['workflow']}: the three artifact receipts passed: {layers}")
    ok(any(m["who"] == "system" and "served" in m["text"] and "refunded" in m["text"] for m in r2.chat), "the chat says what was served and refunded")
    rows2 = j2.j2_artifacts.rows(r2.dir)
    ok(any(r.get("reused_from") for r in rows2), "the Artifacts rows name what was served")

    # (d) a pilates brief over the yoga template: cross-client
    r3 = run_of(PILATES_DOCS)
    s3 = summary_of(r3)
    ok(s3["status"] == "done", f"run 3 done: {s3['status']} {s3.get('outcome')}")
    d3 = doc_decisions(r3)
    ok(d3 and all(d["door"] in ("reuse", "adapt", "build") for d in d3), f"cross-client: every door decided: {A.counts(d3)}")
    ok(all(d["rule"] != "same" for d in d3 if d["door"] == "reuse"), "another business never matches the same inputs")
    names = ("Still Point", "stillpoint")      # the pilates brief keeps the yoga brief's address and classes as its own facts
    leaks = []
    for c in t.calls_file(r3):
        text = (c["system"] + c["prompt"])
        for n in names:
            i = text.lower().find(n.lower())
            if i >= 0:
                leaks.append((c.get("fn"), c.get("atom"), n, text[max(0, i - 90):i + 60].replace("\n", " ")))
    if leaks:
        print("LEAKS:", json.dumps(leaks, indent=1, ensure_ascii=False)[:4000])
        print("DECISIONS:", [(d["workflow"], d["section"], d["door"], d["rule"]) for d in d3])
    ok(not leaks, f"no name of the yoga studio reaches a pilates prompt: {sorted({l[2] for l in leaks})}")
    final = open(os.path.join(r3.dir, "site", sorted(n for n in os.listdir(os.path.join(r3.dir, "site")) if n.endswith(".md"))[-1]), encoding="utf-8").read()
    ok(not any(n.lower() in final.lower() for n in names), "no name of the yoga studio in the final document")
    ok(r3.calls <= ceiling, f"no more model calls with the flag on ({r3.calls}) than off ({ceiling})")
    ok(all(d.get("refunded") for d in d3 if d["door"] == "reuse" and d.get("held")) and
       not any(d.get("refunded") for d in d3 if d["door"] != "reuse"), "refunds only on sections that were served and held")

    # (e) the source data broken: the served section fails a receipt, drops to adapt, the run completes
    prd = json.load(open(os.path.join(r1.dir, "prd.json"), encoding="utf-8"))
    broke = None
    for sec, data in prd["sections"].items():
        for k, v in (data or {}).items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and isinstance(v[0].get("id"), str):
                v[0]["id"] = v[0]["id"][:1] + "9"      # G1 -> G9: ids no longer run in order, a rule the receipt checks
                broke = (sec, k)
                break
        if broke:
            break
    ok(broke, "a section with ids to break")
    json.dump(prd, open(os.path.join(r1.dir, "prd.json"), "w", encoding="utf-8"), indent=1)
    r4 = run_of(YOGA_DOCS)
    s4 = summary_of(r4)
    ok(s4["status"] == "done", f"run 4 done after a broken source: {s4['status']} {s4.get('outcome')}")
    d4 = {d["section"]: d for d in doc_decisions(r4) if d["artifact"] == "prd"}
    bad = d4.get(broke[0])
    ok(bad and bad["door"] == "adapt" and "served, then" in bad["reason"], f"the broken section was served, failed and became adapt: {bad}")
    ok(not bad.get("refunded") and not bad.get("held"), "a section that failed is neither held nor refunded")
    ok(any(d["door"] == "reuse" and d.get("held") for s, d in d4.items() if s != broke[0]), "the other sections were still served")
    print(f"content_door_test: {passed} checks passed (flag-off ceiling {ceiling} calls; run 2 served {len(served)} sections; "
          f"run 3 {A.counts(d3)})")
finally:
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)
