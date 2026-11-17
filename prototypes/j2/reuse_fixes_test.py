"""Offline checks of the four reuse fixes found in the live test of 16 Nov 2026 (runs j2-20261116-135730, -143416,
-150106): python reuse_fixes_test.py

Mock document runs into a copy of the library and a temp runs folder (j2_flow_test's session folders):
(1) never reuse when a fix is asked for: a run whose sections were served is given three rework rounds on one
    section; each revision's door is adapt (rule rework), each costs a model call, each prompt carries that round's
    finding, and the three rounds leave three different texts (before the fix: the old section, three times);
(2) adapt when numbering changed: an HLD section of the source run is served while the PRD is what the source run
    had, and adapted (rule inputs-changed) when this run's PRD has R-ids the source's did not, or other content;
    in the flow, the documents written after a changed PRD are drafted, not served;
(3) start fresh when the business is not similar enough: a law firm's PRD need creates its own template family and
    adapts no yoga, pilates or fitness template; a pilates need still adapts a studio's template; the generator is
    told the number, which is the settings file's;
(4) the same job after small changes: the yoga brief again, with one done-when item worded anew (another
    fingerprint), reuses the run template's own templates (rule j) and its PRD sections are served (rule same-job);
    a changed price is not the same job.
After the review of PR #205 (17 Nov 2026):
(5) a rework with no section of its own yet gets no draft: never the source run's section;
(6) the same job is held to the foreign-values rule: a section of the same business that holds a value of the
    source run's charter this charter does not is adapted (rule same-job-facts), not served;
(7) a source run that did not end workable is never served and never drafted from (door build, rule
    source-not-workable), in door() and in a whole run;
(8) flag scope: with J2_RUN_TEMPLATES=1 alone there is no same-job rule, no similarity floor and no sentence about
    it for the generator (the routing before #205); with J2_AUTO_REUSE=1, or J2_ARTIFACT_LIBRARY=1 which implies it,
    all three are there;
(9) the email, time and number shapes are the settings file's (fact_shapes) and give what the patterns that stood
    in code gave.
No AI calls. Nothing written outside the temp folders.
"""
import copy
import json
import os
import re
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
LAW_FACTS = ["Hale Finch Legal", "Property", "Employment", "Family", "Business contracts", "intake@halefinch.example",
             "name", "email", "matter type", "short description of the matter",
             "The Problem section states the problem the intake form solves for Hale Finch Legal."]
PILATES_FACTS = ["Calm Core Pilates", "Shop 7, 14 Example Road, Pune 411005", "Monday 7:30 am Mat Foundations 550",
                 "Tuesday 6:00 pm Reformer Basics 850", "Thursday 7:30 am Core and Balance 600",
                 "Friday 6:00 pm Evening Stretch 500", "Sunday 9:30 am Weekend Flow 650", "bookings@calmcore.example",
                 "name, email, class and preferred date", "Payment is made at the studio",
                 "The Problem section states the main problem the page solves."]
STUDIOS = ("Still Point", "Flow Pilates", "Iron Grove", "Rhythm Room", "Thread")


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


def reuse_of(run):
    p = os.path.join(run.dir, "reuse.json")
    return json.load(open(p, encoding="utf-8"))["decisions"] if os.path.isfile(p) else []


def routed(run):
    return json.load(open(os.path.join(run.dir, "templates.json"), encoding="utf-8"))


def summary_of(run):
    return json.load(open(os.path.join(run.dir, "summary.json"), encoding="utf-8"))


def versions(run, kind, heading):
    """The text of one section in every saved version of a document, in order."""
    site = os.path.join(run.dir, "site")
    names = sorted((n for n in os.listdir(site) if n.startswith(kind + "-v") and n.endswith(".md")),
                   key=lambda n: int(n[len(kind) + 2:-3]))
    out = []
    for n in names:
        text = open(os.path.join(site, n), encoding="utf-8").read()
        i = text.find(f"## {heading}")
        j = text.find("\n## ", i + 1)
        out.append(text[i:j if j > 0 else len(text)].strip() if i >= 0 else "")
    return out


def three_rounds(run, item=1):
    """Audit's result for one done-when item is NEEDS_REVISION in cycles 1 to 3, each time with another note (the
    test switch J2_FORCE_AUDIT_FAIL does one round)."""
    def forced(results):
        row = next((x for x in results if x["item"] == item), None)
        if run.cycle > 3 or not row or not run.doc or run.output != "prd":
            return None
        row.update(verdict="NEEDS_REVISION", severity="medium", note=f"ROUND-{run.cycle}-NOTE the section must say this", **{"pass": False})
        return item
    run._force_fail = forced


class FollowsFindings:
    """A stand-in for a model that does what a rework prompt asks: when a builder's prompt carries "A FIX WAS ASKED
    FOR", the mock's section gets the finding's note written into its first text field. Every other call is the mock's
    own reply. Without the fix no such prompt is ever sent (the old section is served), so the text never changes."""
    def __init__(self):
        self.orig, self.prompts = j2.llm.ask, []

    def __enter__(self):
        def ask(system, user, mock, *a, **kw):
            raw = self.orig(system, user, mock, *a, **kw)
            text = f"{system}\n{user}"
            if "A FIX WAS ASKED FOR" not in text:
                return raw
            self.prompts.append(text)
            asked = text[text.find("FINDINGS TO FIX:"):text.find("THE SECTION AS IT IS NOW")]
            note = (re.findall(r"ROUND-\d+-NOTE", asked) or [""])[0]      # the finding as Audit last wrote it
            try:
                reply = json.loads(raw)
            except (TypeError, ValueError):
                return raw
            sec = reply.get("section")
            key = next((k for k, v in (sec or {}).items() if isinstance(v, str) and k != "facts_used"), None)
            if key and note:
                sec[key] = f"{sec[key].split(' Fixed as asked in ')[0].rstrip('.')}. Fixed as asked in {note}."
            return json.dumps(reply, ensure_ascii=False)
        j2.llm.ask = ask
        return self

    def __exit__(self, *exc):
        j2.llm.ask = self.orig


def reworded(run, kinds=("prd",)):
    """The run's needs with one fact worded anew (the done-when item or the last fact), so the fingerprint is not the
    source run's: what a second live run of the same brief gives, since Identity writes the items again each time."""
    orig = run._template_need

    def need_of(w, kind, section):
        need = orig(w, kind, section)
        if kind in kinds and need["facts"]:
            facts = list(need["facts"])
            i = next((n for n, f in enumerate(facts) if "section" in f.lower()), len(facts) - 1)
            facts[i] = facts[i].rstrip(".") + " clearly"
            fresh = L.make_need(kind, section, need["business_type"], facts, need["site"],
                                [x for x in need["_derived"] if x[0].name not in {f.name for f, _ in L.fact_fields(facts)}],
                                workflow=need["workflow"], atom=need["atom"])
            need = {**need, "facts": fresh["facts"], "fingerprint": fresh["fingerprint"]}
        return need
    run._template_need = need_of


here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(prefix="j2-reuse-fixes-")
lib = os.path.join(tmp, "lib")
shutil.copytree(os.path.join(here, "library"), lib)
keep = {k: os.environ.get(k) for k in FLAGS + ("J2_LIBRARY_DIR",)}
for k in FLAGS:
    os.environ.pop(k, None)
os.environ["J2_LIBRARY_DIR"] = lib
os.environ["J2_ARTIFACT_LIBRARY"] = "1"
try:
    # the source: a yoga documents run, saved as a run template (as content_door_test does)
    r1 = run_of(YOGA_DOCS)
    ok(summary_of(r1)["status"] == "done", "the source run is done")
    rt = L.run_template_from_run(r1.dir, name="A rerun of Still Point Yoga")
    L.save_run_template(rt)
    lib0 = os.path.join(tmp, "lib0")      # the library as the source run left it, for the flag checks of (8)
    shutil.copytree(lib, lib0)

    # ---- (1) never reuse when a fix is asked for: three rework rounds, three texts
    with FollowsFindings() as model:
        r2 = run_of(YOGA_DOCS, prep=three_rounds)
    s2 = summary_of(r2)
    ok(s2["status"] in ("done", "done_with_open_items"), f"the rework run ended: {s2['status']}")
    d2 = reuse_of(r2)
    first = [d for d in d2 if d["artifact"] == "prd" and d["workflow"] in {f"W-{i}" for i in range(1, 7)}]
    ok(first and all(d["door"] == "reuse" and d["held"] for d in first), f"the first PRD sections were served: {A.counts(first)}")
    fixes = [w for w in r2._all_wfs() if w.get("revises") or w.get("fixes")]
    ok(len(fixes) >= 3, f"three revision workflows were registered: {[w['id'] for w in fixes]}")
    by = {d["workflow"]: d for d in d2}
    for w in fixes:
        d = by.get(w["id"])
        ok(d and d["door"] == "adapt" and d["rule"] == "rework" and not d.get("held") and not d.get("refunded"),
           f"{w['id']} (revises {w.get('revises')}, fixes {w.get('fixes')}): the door is adapt, rule rework, nothing served: {d}")
        ok(w["calls_used"] >= 1 and not w.get("served_from"), f"{w['id']}: the builder was called ({w['calls_used']}) and nothing was served")
    ok(len(model.prompts) >= 3, f"a rework prompt was sent in each round: {len(model.prompts)}")
    for n in (1, 2, 3):
        ok(any(f"ROUND-{n}-NOTE" in p and "FINDINGS TO FIX" in p and "THE SECTION AS IT IS NOW" in p for p in model.prompts),
           f"round {n}: the builder's prompt carries that round's finding and the section as it is now")
    texts = versions(r2, "prd", "Problem")
    kept = [x for i, x in enumerate(texts) if x and (i == 0 or x != texts[i - 1])]
    ok(len(kept) >= 4 and len(set(kept)) == len(kept),
       f"the Problem section has four different texts (served, then three rework rounds): {len(kept)} of {len(texts)} versions differ")
    ok(all(f"ROUND-{n}-NOTE" in kept[n] for n in (1, 2, 3)), "each round's text is the one written for that round's finding")
    ok(any(m["who"] == "system" and "a fix was asked for" in m["text"] and "is not served" in m["text"] for m in r2.chat),
       "the chat says a fix was asked for and nothing was served")
    unit = A.door({"fingerprint": "x"}, {"action": "reused", "template": "T", "version": 1},
                  {"run": "r", "workflow": "W-1", "key": "W-1", "sha": "s", "template": "T@1", "fingerprint": "x", "audit": "pass",
                   "receipts_passed": [], "data": {}, "dir": tmp}, rework="it revises W-1 and fixes F-1")
    ok(unit["door"] == "adapt" and unit["rule"] == "rework", f"door(): the same inputs and a fix asked for is adapt, rule rework: {unit}")

    # ---- (2) adapt when numbering changed
    later = [d for d in d2 if d["artifact"] in ("hld", "lld")]
    ok(later and all(d["door"] == "adapt" and d["rule"] == "inputs-changed" and not d.get("held") for d in later),
       f"after the PRD changed, no HLD or LLD section is served: {[(d['workflow'], d['door'], d['rule']) for d in later]}")
    ok(all(w["calls_used"] >= 1 for w in r2._all_wfs() if w["id"] in {d["workflow"] for d in later}), "each was written by a builder call")
    hrow = next(w for w in rt.workflows if w.artifact == "hld")
    src = A.source_section(rt.id, hrow.key, "hld", hrow.section)
    ok(src and src["audit"] == "pass", f"the source run's HLD section {hrow.section} is read")
    prd_then = json.load(open(os.path.join(r1.dir, "prd.json"), encoding="utf-8"))["sections"]
    rec = {"action": "reused", "template": src["template"].rpartition("@")[0], "version": int(src["template"].rpartition("@")[2])}
    need = {"fingerprint": src["fingerprint"]}
    same = A.door(need, rec, src, inputs={"prd": A.doc_state(prd_then)})
    ok(same["door"] == "reuse" and same["rule"] == "same", f"the PRD the source run had: the HLD section is served: {same['door']} {same['rule']}")
    then_ids = [i for i in A.ids_of(prd_then) if i.startswith("R")]
    ok(then_ids, f"the source PRD has requirement ids: {then_ids}")
    prd_now = copy.deepcopy(prd_then)
    reqs = next(v for sec in prd_now.values() for v in sec.values() if isinstance(v, list) and v and isinstance(v[0], dict)
                and str(v[0].get("id") or "").startswith("R"))
    last = int(then_ids[-1][1:])
    reqs.extend({**copy.deepcopy(reqs[-1]), "id": f"R{last + n}"} for n in (1, 2))
    more = A.door(need, rec, src, inputs={"prd": A.doc_state(prd_now)})
    ok(more["door"] == "adapt" and more["rule"] == "inputs-changed",
       f"this run's PRD has R{last + 1} and R{last + 2}, the source's ended at R{last}: adapted, not served: {more['door']} {more['rule']}")
    ok(f"R1 to R{last} then" in more["reason"] and f"R1 to R{last + 2} now" in more["reason"], f"the reason names both id ranges: {more['reason']}")
    prd_text = copy.deepcopy(prd_then)
    sec = next(iter(prd_text.values()))
    key = next(k for k, v in sec.items() if isinstance(v, str))
    sec[key] += " More."
    other = A.door(need, rec, src, inputs={"prd": A.doc_state(prd_text)})
    ok(other["door"] == "adapt" and other["rule"] == "inputs-changed" and "same ids but other content" in other["reason"],
       f"the same ids and other content is adapted too: {other['door']} {other['rule']}")
    ok(A.door(need, rec, src, inputs={})["door"] == "reuse", "a first document (nothing written before it) is served as before")

    # ---- (3) start fresh when the business is not similar enough
    least = float(L.routing("adapt_min_similarity"))
    ok(least == 0.6 and any(str(least) in r and "another business" in r for r in L.routing_rules()),
       f"the least similarity is the settings file's ({least}) and the generator is told it")
    # the flow: a law firm's PRD run adapts no studio template
    r3 = run_of("Write a PRD for Clear Counsel, a law firm."
                + t.CAMPUS.replace("students and teachers", "prospective clients").replace("students lose track of their notes", "intakes arrive by phone and get lost")
                .replace("upload notes, search notes", "name, email, matter type, short description of the matter"))
    t3 = routed(r3)
    spec3 = [d for d in t3["decisions"] if d.get("kind") == "specialised"]
    ok(not (t3.get("run_template") or {}).get("id"), f"the law firm's run picked no run template: {(t3.get('run_template') or {}).get('id')}")
    ok(spec3 and not any(s in str(d.get("adapted_from") or "") + d["template"] for d in spec3 for s in STUDIOS),
       f"no section template of the law firm's run is a studio's or adapted from one: {[(d['section'], d['action'], d['template'], d.get('adapted_from')) for d in spec3]}")
    ok(all(d["action"] == "created" and d["template"].startswith("Clear Counsel") and d.get("fresh_start") for d in spec3
           if d["artifact"] == "prd" and not d.get("revises")),
       f"it created its own template family for every PRD section: {[(d['section'], d['action'], d.get('fresh_start')) for d in spec3]}")
    ok(any(m["who"] == "system" and "template: created Clear Counsel" in m["text"] for m in r3.chat), "the chat says each template was created")

    law = L.make_need("prd", "Problem", "prd", LAW_FACTS, "Hale Finch Legal")
    before = {(e["name"], v["version"]) for e in L.index()["templates"] for v in e["versions"]}
    _, lrec = L.route(law, {"run": "test-law", "workflow": "W-1", "atom": "W-1.a1"}, closest=True)
    ok(lrec["action"] == "created" and not lrec.get("adapted_from"), f"a law firm's PRD need creates a template: {lrec['action']} {lrec.get('adapted_from')}")
    ok(lrec.get("fresh_start") and lrec["not_similar"]["templates"] and
       all(x["business_similarity"] < least for x in lrec["not_similar"]["templates"]),
       f"the decision records the studios' templates that were not similar enough: {lrec.get('not_similar')}")
    ok(lrec["template"].startswith("Hale Finch Legal") and not any(s in lrec["template"] for s in STUDIOS),
       f"the new family is this business's own: {lrec['template']}")
    made = L.get(f"{lrec['template']}@{lrec['version']}", "prd", "Problem")
    ok(made and not any(s.lower() in json.dumps(made.model_dump(), ensure_ascii=False).lower() for s in STUDIOS),
       "nothing of a studio is in the law firm's template")
    ok("similar enough" in lrec["reason"] and "own template family" in lrec["reason"], f"the reason says why: {lrec['reason'][:160]}")
    pil = L.make_need("prd", "Problem", "prd", PILATES_FACTS, "Calm Core Pilates")
    _, prec = L.route(pil, {"run": "test-pilates", "workflow": "W-1", "atom": "W-1.a1"}, closest=True)
    ok(prec["action"] == "extended" and prec.get("adapted_from") and any(s in prec["adapted_from"] for s in STUDIOS),
       f"a pilates PRD need still adapts a studio's template: {prec['action']} from {prec.get('adapted_from')}")
    ok(prec["nearest"]["business_similarity"] >= least, f"its business similarity is at or above the least: {prec['nearest']['business_similarity']}")
    ok(prec["template"].startswith("Calm Core Pilates"), f"stored as the pilates studio's own family: {prec['template']}")
    few = L.make_need("hld", "Risks", "hld", ["The Risks section is written for Hale Finch Legal"], "Hale Finch Legal")
    known = {}
    L.route(L.make_need("prd", "Users", "prd", LAW_FACTS, "Hale Finch Legal"), {"run": "test-law", "workflow": "W-2", "atom": "W-2.a1", "similar": known}, closest=True)
    ok(known and all(v < least for v in known.values()), f"the run keeps what it found for each other business: {known}")
    _, frec = L.route(few, {"run": "test-law", "workflow": "W-9", "atom": "W-9.a1", "similar": known}, closest=True)
    ok(not frec.get("adapted_from") or not any(s in frec["adapted_from"] for s in STUDIOS if s in " ".join(known)),
       f"a section with too few facts to compare takes the run's finding for that business: {frec['action']} {frec.get('adapted_from')}")
    sim_law, n_law = L.business_similarity(law, L.get("Still Point Yoga Problem@2", "prd", "Problem").context.facts_used)
    sim_pil, n_pil = L.business_similarity(pil, L.get("Still Point Yoga Problem@2", "prd", "Problem").context.facts_used)
    ok(sim_law < least <= sim_pil, f"law firm to yoga studio {sim_law} ({n_law} facts), pilates to yoga studio {sim_pil} ({n_pil} facts)")
    # a page section with facts of its own never takes a template of another business that has too few facts to compare
    # (live run j2-20261116-172922 W-22: a yoga page section adapted from a boutique's one-fact template)
    page = L.make_need("website", "Section", "website", ["The page shows the studio name Harbour Yoga", "The page shows the address 4 Sample Quay as text",
                                                         "The weekly class list has five classes with day, time and price"], "Harbour Yoga")
    thread = L.get("Thread Filter@1", "website", "Section")
    ok(L.business_similarity(page, thread.context.facts_used, "Thread")[1][1] < int(L.routing("similarity_min_facts")),
       f"the boutique's template has too few facts to compare: {thread.context.facts_used}")
    _, wrec = L.route(page, {"run": "test-yoga-page", "workflow": "W-1", "atom": "W-1.a1"}, closest=True)
    ok("Thread" not in str(wrec.get("adapted_from") or ""), f"it is not adapted for the yoga page: {wrec['action']} {wrec.get('adapted_from')}")
    # ---- (4) the same job after small changes
    t0 = L.get("Still Point Yoga Problem@2", "prd", "Problem")
    facts = list(t0.context.facts_used)
    i = next(n for n, f in enumerate(facts) if "section" in f.lower() or n == len(facts) - 1)
    anew = L.make_need("prd", "Problem", "prd", facts[:i] + [facts[i].rstrip(".") + " clearly"] + facts[i + 1:], "Still Point Yoga")
    ok(anew["fingerprint"] not in {fp for e in L.index()["templates"] if e["name"] == t0.name for v in e["versions"] for fp in v.get("fingerprints") or []},
       "a fact worded anew gives another fingerprint")
    ok(L.same_job(anew, t0) is not None, f"the same business, the same values, one fact worded anew: the same job ({L.same_job(anew, t0)})")
    _, jrec = L.route(anew, {"run": "test-yoga", "workflow": "W-1", "atom": "W-1.a1"}, first={"template": "Still Point Yoga Problem@2"})
    ok(jrec["action"] == "reused" and jrec["rule"] == "j" and jrec["version"] == 2 and jrec.get("same_job"),
       f"the run template's own template is reused as it is, not adapted to a new version: {jrec['action']} v{jrec['version']} rule {jrec['rule']}")
    price = [f.replace("500", "550") if "Monday" in f else f for f in facts]
    ok(price != facts and L.same_job(L.make_need("prd", "Problem", "prd", price, "Still Point Yoga"), t0) is None, "a changed price is not the same job")
    ok(L.same_job(L.make_need("prd", "Problem", "prd", facts, "Calm Core Pilates"), t0) is None, "another business is never the same job")
    jd = A.door({"fingerprint": "another"}, {"action": "reused", "template": "T", "version": 1, "same_job": {"match": 0.9}},
                {"run": "r", "workflow": "W-1", "key": "W-1", "sha": "s", "template": "T@1", "fingerprint": "x", "audit": "pass",
                 "receipts_passed": [], "data": {"facts_used": ["an old fact"]}, "dir": tmp}, goal={"facts": []})
    ok(jd["door"] == "reuse" and jd["rule"] == "same-job", f"door(): the same job and the same template is served: {jd['door']} {jd['rule']}")
    # the flow: the yoga brief again, its PRD needs worded anew
    r4 = run_of(YOGA_DOCS, prep=reworded)
    s4 = summary_of(r4)
    ok(s4["status"] == "done", f"the same-job run is done: {s4['status']} {s4.get('outcome')}")
    d4 = [d for d in reuse_of(r4) if d["artifact"] == "prd"]
    t4 = [d for d in routed(r4)["decisions"] if d["artifact"] == "prd"]
    ok(t4 and all(d["action"] == "reused" for d in t4) and any(d.get("rule") == "j" for d in t4),
       f"every PRD template is reused although the fingerprints differ: {[(d['section'], d['action'], d.get('rule')) for d in t4]}")
    ok(d4 and all(d["door"] == "reuse" and d["held"] for d in d4) and any(d["rule"] == "same-job" for d in d4),
       f"the PRD sections are served: {[(d['section'], d['door'], d['rule'], d.get('held')) for d in d4]}")
    wf4 = {w["id"]: w for w in r4._all_wfs()}
    ok(all(wf4[d["workflow"]]["calls_used"] == 0 for d in d4), "a served PRD section costs no model call")
    rest = [d for d in reuse_of(r4) if d["artifact"] in ("hld", "lld")]
    ok(rest and all(d["door"] == "reuse" and d["held"] for d in rest),
       f"the PRD is what the source run had, so the HLD and LLD are served too: {A.counts(rest)}")

    # ---- (5) a rework with no section yet: the draft stays empty, never the source run's section
    d0 = d4[0]
    w0, sec0 = wf4[d0["workflow"]], d0["section"]
    src0 = r4.content_sources[w0["id"]]
    ok(src0 and src0["data"], f"{w0['id']} {sec0} has a source section")
    fix = {**w0, "id": "W-901", "revises": w0["id"], "fixes": ["F-1"]}
    r4.tpl_routes["W-901"] = r4.tpl_routes[w0["id"]]
    mine_now = r4.art_data["prd"].pop(sec0)      # this run has not written the section (yet)
    dn = r4._route_content(fix, "prd", sec0)
    ok(dn["door"] == "adapt" and dn["rule"] == "rework" and dn["source"], f"a rework with a source and no section yet: adapt, rule rework: {dn['door']} {dn['rule']}")
    ok("W-901" not in r4.content_draft, f"no draft is made, the source run's section is not used: {str(r4.content_draft.get('W-901'))[:80]}")
    block = r4._content_draft_text(fix)
    ok("A FIX WAS ASKED FOR" in block and "THE SECTION AS IT IS NOW" not in block and "DRAFT (" not in block,
       "the prompt asks for the fix and carries no section text")
    ok(not any(str(v) in block for v in src0["data"].values() if isinstance(v, str) and len(v) > 20), "nothing of the source section is in the prompt")
    r4.art_data["prd"][sec0] = mine_now
    fix2 = {**fix, "id": "W-902"}
    r4.tpl_routes["W-902"] = r4.tpl_routes[w0["id"]]
    r4._route_content(fix2, "prd", sec0)
    ok(json.loads(r4.content_draft["W-902"]) == mine_now and "THE SECTION AS IT IS NOW" in r4._content_draft_text(fix2),
       "with a section of its own the rework draft is this run's section, as before")

    # ---- (6) the same job is held to the foreign-values rule
    jrow = next(w for w in rt.workflows if w.artifact == "prd")
    jsrc = A.source_section(rt.id, jrow.key, "prd", jrow.section)
    name, _, ver = jsrc["template"].rpartition("@")
    jrec6 = {"action": "reused", "template": name, "version": int(ver), "same_job": {"match": 0.9}}
    goal1 = json.load(open(os.path.join(r1.dir, "goal.json"), encoding="utf-8"))
    clean = A.door({"fingerprint": "another"}, jrec6, jsrc, goal=goal1)
    ok(clean["door"] == "reuse" and clean["rule"] == "same-job", f"the same job, nothing foreign in the section: served: {clean['door']} {clean['rule']}")
    # the same business's source run, whose charter and section carry a value of another business
    other_dir = os.path.join(tmp, "source-with-foreign-value")
    shutil.copytree(r1.dir, other_dir)
    g = json.load(open(os.path.join(other_dir, "goal.json"), encoding="utf-8"))
    g["facts"] = list(g.get("facts") or []) + ["bookings@calmcore.example"]
    json.dump(g, open(os.path.join(other_dir, "goal.json"), "w", encoding="utf-8"))
    carried = copy.deepcopy(jsrc["data"])
    tkey = next(k for k, v in carried.items() if isinstance(v, str))
    carried[tkey] += " Write to bookings@calmcore.example."
    fsrc = {**jsrc, "dir": other_dir, "data": carried}
    ok(A.foreign_values(fsrc, goal1) == ["bookings@calmcore.example"], f"the section holds a value this charter does not: {A.foreign_values(fsrc, goal1)}")
    held = A.door({"fingerprint": "another"}, jrec6, fsrc, goal=goal1)
    ok(held["door"] == "adapt" and held["rule"] == "same-job-facts" and "1 value" in held["reason"],
       f"the same job with another business's value in the section: adapted, not served: {held['door']} {held['rule']}")
    ok("calmcore" not in A.draft_text(fsrc), "and the draft has that value slotted")
    ok(A.door({"fingerprint": "another"}, jrec6, fsrc, goal={**goal1, "facts": g["facts"]})["door"] == "reuse",
       "a value this charter holds too is not foreign")

    # ---- (7) a source run that did not end workable is never served or drafted from
    ok(j2.ended_workable(j2.saved_dir(jsrc["run"])), "the source run ended workable (so far it was served from)")
    for label, kw, want in (("not workable", {"workable": False}, ("build", "source-not-workable")),
                            ("workable", {"workable": True}, ("reuse", "same-job")),
                            ("not asked", {}, ("reuse", "same-job"))):
        got = A.door({"fingerprint": "another"}, jrec6, jsrc, goal=goal1, **kw)
        ok((got["door"], got["rule"]) == want, f"door(), source {label}: {got['door']} {got['rule']}")
    nw = A.door({"fingerprint": jsrc["fingerprint"]}, jrec6, jsrc, goal=goal1, workable=False, inputs={})
    ok(nw["door"] == "build" and nw["reason"].startswith("source-not-workable"), f"the same inputs too, and the reason says so: {nw['reason']}")
    ok(A.door({"fingerprint": "x"}, {**jrec6, "action": "extended", "same_job": None}, jsrc, goal=goal1, workable=False)["door"] == "build",
       "a section that would be a draft (adapt) is not one either")
    apath = os.path.join(r1.dir, "audits.json")
    audits_then = open(apath, encoding="utf-8").read()
    audits = json.loads(audits_then)
    last_audit = [a for a in audits if isinstance(a, dict) and a.get("kind") != "recheck"][-1]
    last_audit["results"][0].update(verdict="NEEDS_REVISION", **{"pass": False})
    last_audit["accepted"] = []
    json.dump(audits, open(apath, "w", encoding="utf-8"))
    try:
        ok(not j2.ended_workable(r1.dir), "the source run's last audit is now not workable")
        asked, orig_ask = [], j2.llm.ask

        def listen(system, user, mock, *a, **kw):
            asked.append(f"{system}\n{user}")
            return orig_ask(system, user, mock, *a, **kw)
        j2.llm.ask = listen
        try:
            r5 = run_of(YOGA_DOCS)
        finally:
            j2.llm.ask = orig_ask
    finally:
        open(apath, "w", encoding="utf-8").write(audits_then)
    d5 = reuse_of(r5)
    from5 = [d for d in d5 if d.get("source")]
    ok(len(from5) >= 6 and all(d["source"]["run"] == os.path.basename(r1.dir) for d in from5),
       f"the run followed the source run's run template: {len(from5)} sections have a source")
    ok(all(d["door"] == "build" and d["rule"] == "source-not-workable" and not d.get("held") and not d.get("refunded") for d in from5),
       f"none is served or adapted: {sorted({(d['door'], d['rule']) for d in from5})}")
    ok(not any(d["door"] in ("reuse", "adapt") for d in d5), f"no section of the run is served or drafted: {A.counts(d5)}")
    wf5 = {w["id"]: w for w in r5._all_wfs()}
    ok(all(wf5[d["workflow"]]["calls_used"] >= 1 and not wf5[d["workflow"]].get("served_from") for d in from5),
       "each section was written by a builder call")
    ok(not r5.content_draft and not any("DRAFT (the same section" in x for x in asked), "no draft was made and no prompt carries one")
    ok(any(m["who"] == "system" and "source-not-workable" in m["text"] for m in r5.chat), "the chat says why")

    # ---- (8) flag scope: the same-job rule and the similarity floor only with J2_AUTO_REUSE (J2_ARTIFACT_LIBRARY implies it)
    def routed_with(flag, n):
        """A PRD need of the same job and a law firm's need, routed in a fresh copy of the library with one flag on."""
        for k in FLAGS:
            os.environ.pop(k, None)
        os.environ[flag] = "1"
        os.environ["J2_LIBRARY_DIR"] = os.path.join(tmp, f"lib-flag-{n}")
        shutil.copytree(lib0, os.environ["J2_LIBRARY_DIR"])
        _, j = L.route(anew, {"run": "test-flag", "workflow": "W-1", "atom": "W-1.a1"}, first={"template": "Still Point Yoga Problem@2"})
        _, f = L.route(law, {"run": "test-flag", "workflow": "W-2", "atom": "W-2.a1"})
        return j, f, L.routing_rules()
    told = len(L.settings()["routing"]["rules"])
    try:
        joff, foff, rules_off = routed_with("J2_RUN_TEMPLATES", 0)
        ok(not L.auto_reuse(), "J2_RUN_TEMPLATES=1 alone is not auto reuse")
        ok(joff["action"] == "extended" and joff["rule"] == "t" and not joff.get("same_job") and joff["version"] > 2
           and joff["template"] == "Still Point Yoga Problem",
           f"run templates alone: other facts make a new version of the run template's template, no same-job rule: {joff['action']} v{joff['version']} rule {joff['rule']}")
        ok(foff["action"] == "created" and not any(k in foff for k in ("fresh_start", "not_similar", "nearest")),
           f"run templates alone: no similarity floor is applied: {foff['action']} {[k for k in ('fresh_start', 'not_similar', 'nearest') if k in foff]}")
        ok(len(rules_off) == told and not any("another business" in r for r in rules_off),
           f"run templates alone: the generator is told the {told} rules it was told before, nothing of the floor")
        for n, flag in ((1, "J2_AUTO_REUSE"), (2, "J2_ARTIFACT_LIBRARY")):
            jon, fon, rules_on = routed_with(flag, n)
            ok(L.auto_reuse(), f"{flag}=1 is auto reuse")
            ok(jon["action"] == "reused" and jon["rule"] == "j" and jon["version"] == 2 and jon.get("same_job"),
               f"{flag}=1: the same job reuses the template as it is: {jon['action']} v{jon['version']} rule {jon['rule']}")
            ok(fon["action"] == "created" and fon.get("fresh_start") and fon.get("not_similar"),
               f"{flag}=1: the similarity floor is applied: {fon['action']} fresh_start {fon.get('fresh_start')}")
            ok(len(rules_on) == told + 1 and any(str(least) in r and "another business" in r for r in rules_on),
               f"{flag}=1: the generator is told the floor too")
    finally:
        for k in FLAGS:
            os.environ.pop(k, None)
        os.environ["J2_LIBRARY_DIR"] = lib
        os.environ["J2_ARTIFACT_LIBRARY"] = "1"

    # ---- (9) the shapes are the settings file's and give what the patterns in code gave
    was_email = re.compile(r"\S+@\S+")
    was_hard = re.compile(r"[\w.+-]+@[\w.-]+|\d{1,2}:\d{2}|\d{3,}")
    shapes = json.load(open(L.SETTINGS_PATH, encoding="utf-8"))["fact_shapes"]
    ok(L.fact_shape("not_compared").pattern == shapes["not_compared"] == was_email.pattern, "not_compared is the settings file's, the pattern as it was")
    ok(L.fact_shape("hard").pattern == "|".join(shapes["hard"].values()) == was_hard.pattern, "hard is the settings file's shapes in order, the pattern as it was")
    code = open(os.path.join(here, "j2_template_lib.py"), encoding="utf-8").read()
    ok(not any(x in code for x in ("_EMAIL_RE", "_HARD_RE", was_email.pattern, was_hard.pattern, r"\d{1,2}:\d{2}")),
       "neither pattern is left in j2_template_lib.py")
    samples = LAW_FACTS + PILATES_FACTS + [f for e in L.index()["templates"] for v in e["versions"]
                                           for f in (L.get(f"{e['name']}@{v['version']}", e["artifact"], e["section"]).context.facts_used)]
    ok(len(samples) > 50 and all(L.fact_shape("hard").findall(f.lower()) == was_hard.findall(f.lower())
                                 and L.fact_shape("not_compared").sub(" ", f) == was_email.sub(" ", f) for f in samples),
       f"every fact of the library ({len(samples)}) gives the same emails, times and numbers as before")
    ok((sim_law, sim_pil) == (0.1818, 0.8182), f"the similarities are what they were (0.1818, 0.8182): {sim_law} {sim_pil}")
    print(f"reuse_fixes_test: {passed} checks passed (rework run: {len(fixes)} revisions, {len(kept)} Problem texts; "
          f"law firm {sim_law} / pilates {sim_pil} to a yoga studio, least {least}; same-job run served {len(d4)} PRD sections)")
finally:
    for k, v in keep.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(tmp, ignore_errors=True)
