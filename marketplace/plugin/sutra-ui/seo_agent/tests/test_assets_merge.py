"""tests/test_assets_merge.py — the merge (builder 4) and the reuse check (builder 5), model stubbed.

Proves the plumbing and the rules the code is supposed to enforce, not whether the judgments are
any good. Only a real run shows that.

What it holds to account:
  merge   ids are re-minted so three pools that each number from a0001 cannot collide; the method
          comes from the pool file; a missing pool and an empty pool are recorded as different
          facts; only CROSS-method pairs are nominated for de-duplication; a SAME merge POOLS the
          methods and the proof instead of discarding a copy; a COMBINE rewrites the title and
          fills the survivor's blanks; the ranking puts an unownable idea last and orders the rest
          by brand fit then the shared Linkability score; a second run reuses the sheet.
  reuse   with no page index it says so and writes nothing; the match scores reach the working file
          and never reach the judge; the verdict is one of the four in `_common.REUSE_VERDICTS`;
          a chosen link is always one retrieval found; a second run reuses the verdicts.

The embeddings are stubbed with a small controlled table rather than the fixture's word-overlap
vectors, because this suite needs to know exactly which pairs get nominated.
"""
import os
import sys

import numpy as np

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.assets import _common as cm
from seo_agent.assets import merge, reuse
from seo_agent.tools import _index, _shared as sh, voyage

FAILS = []
CALLS = {"json": 0, "text": 0}
UNFILLED = []
JUDGE_PROMPTS = []
RELEVANCE_PROMPTS = []      # what the relevance recheck was actually shown


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def calls():
    return CALLS["json"] + CALLS["text"]


def say(label, note=""):
    print("      . %s — %s" % (label, note))


# --- the model ------------------------------------------------------------------------------------
# The dedup answer is read out of the cluster it was handed, the way a well-behaved model would:
# the two bad-hire ideas are the SAME asset, the two skills-gap ideas COMBINE, everything else is
# left alone. Every other prompt falls through to the shared fixture, which already answers the
# reuse judge (its prompt is the research flow's, ported from this very workflow).

def _ids(prompt):
    return [ln.split("id=", 1)[1].split(" ", 1)[0].strip(" ·")
            for ln in prompt.splitlines() if ln.strip().startswith("- id=")]


def _json(prompt, system=None, retries=1, **kw):
    CALLS["json"] += 1
    if "{{" in prompt:
        UNFILLED.append(prompt[:80])
    if "FINAL relevance pass" in prompt:
        # A well-behaved judge: the payroll idea is a different product world, everything else
        # belongs. The ids come back exactly as they were given.
        RELEVANCE_PROMPTS.append(prompt)
        out = []
        for ln in prompt.splitlines():
            if not ln.strip().startswith("- id="):
                continue
            rid = ln.split("id=", 1)[1].split(" ", 1)[0].strip(" ·")
            off = "payroll" in ln.lower()
            out.append({"id": rid, "decision": "DROP" if off else "KEEP",
                        "reason": "payroll is somebody else's product" if off else ""})
        return {"verdicts": out}
    if "de-duplicating a CLUSTER" in prompt:
        ids = _ids(prompt)
        low = prompt.lower()
        if "bad hire" in low or "bad-hire" in low:
            keep = next((i for i in ids if "Bad Hire" in prompt.split("id=" + i, 1)[1][:120]), ids[0])
            return {"groups": [{"action": "same", "ids": ids, "keep": keep}]}
        if "skills gap" in low or "skills-gap" in low:
            return {"groups": [{"action": "combine", "ids": ids,
                                "new_title": "The Skills-Gap Index, and the tension behind it",
                                "new_angle": "the gap measured, next to what people actually say about it"}]}
        return {"groups": []}
    return _fixture.stub_json(prompt, system, retries)


def _text(prompt, system=None, **kw):
    CALLS["text"] += 1
    if "{{" in prompt:
        UNFILLED.append(prompt[:80])
    if "OUR CLOSEST EXISTING PAGES" in prompt:
        JUDGE_PROMPTS.append(prompt)
    return _fixture.stub_text(prompt, system)


llm.json_call = _json
llm.text = _text


# --- embeddings we control -------------------------------------------------------------------------
# One orthogonal axis per topic bucket, so two ideas in the same bucket sit at cosine 1.0 and two in
# different buckets at 0.0. The nomination threshold is then exercised exactly, with no luck in it.

BUCKETS = ("bad hire", "scorecard", "onboarding", "skills gap", "payroll")


def _bucket_vec(text):
    """One axis per bucket, and a shared "no bucket" axis for anything else. Hyphens are folded to
    spaces first, so "bad-hire" and "bad hire" land on the same axis rather than on two."""
    low = str(text).lower().replace("-", " ")
    v = np.zeros(len(BUCKETS) + 1, dtype=np.float32)
    for i, word in enumerate(BUCKETS):
        if word in low:
            v[i] = 1.0
    if not v.any():
        v[len(BUCKETS)] = 1.0
    return v / (np.linalg.norm(v) + 1e-9)


def stub_bucket_embeddings():
    voyage.embed = lambda texts, input_type="document": np.array(
        [_bucket_vec(t) for t in texts], dtype=np.float32)
    voyage.available = lambda: True


# --- the three pools ---------------------------------------------------------------------------------
# Ids come from `_common.new_id(n, band)`, which is what the three builders are meant to call: the
# bands (competitors 1001+, formats 2001+, trends 3001+) keep three pools that never see each other
# from minting the same id. The stack keeps these ids rather than re-numbering, so a row's id still
# says which method found it.

def idea(n, band, method, title, angle, **over):
    row = cm.blank_idea(cm.new_id(n, band), method)
    row["title"] = title
    row["angle"] = angle
    row["ownability"] = {"judged": True, "verdict": over.pop("own", True), "why": "judged"}
    link = over.pop("link", 3)
    row["linkability"] = ({"judged": False, "score": None, "of": 4, "verdict": None,
                           "why": "the linkability pass returned no row for this idea"}
                          if link is None else
                          {"judged": True, "score": link, "of": 4,
                           "verdict": link >= cm.LINKABILITY_FLOOR, "why": "scored"})
    row.update(over)
    return row


def plant_pools():
    store.save_knowledge("assets/competitors.json", [
        idea(1, "competitors", "competitors", "Cost of a Bad Hire, benchmarked",
             "what a wrong hire costs, by role and company size", brand_fit="CORE", link=4,
             format="benchmark report",
             proof=[{"url": "https://rival-one.com/bad-hire", "domains": 136, "what": "136 domains"}]),
        idea(2, "competitors", "competitors", "Interview Scorecard Template Library",
             "a scorecard per role, free", brand_fit="CORE", link=3, format="template pack"),
        # Nobody scored this one. That is not a score of zero and must not read as one.
        idea(3, "competitors", "competitors", "Interview scorecard pack, printable",
             "the same scorecards as a PDF", brand_fit="CORE", link=None, format="template pack"),
    ])
    store.save_knowledge("assets/trends.json", [
        # The side that gets merged away is the one carrying the build flag, so the flag can only
        # survive by being pooled onto the survivor.
        idea(1, "trends", "study-trends", "Annual bad-hire cost report",
             "[people keep arguing about it] we have the numbers", link=3, tool_escalation=True,
             proof=[{"url": "https://reddit.com/r/hr/x", "domains": 0, "what": "412 comments"}]),
        idea(2, "trends", "study-trends", "Remote onboarding tension index",
             "[nobody knows if it works] measured", brand_fit="ADJACENT", link=4),
        idea(3, "trends", "study-trends", "Skills gap tension report",
             "[the gap everyone complains about] with the complaints attached", brand_fit="CORE",
             link=4),
    ])
    store.save_knowledge("assets/formats.json", [
        idea(1, "formats", "model-other-niches", "Skills gap interactive index",
             "an index other niches proved works", brand_fit="TRANSPLANT", link=4,
             format="interactive index", beatability=2, effort="M",
             what_it_would_be="a live index page with a slider per industry",
             proof=[{"url": "https://otherniche.com/index", "domains": 58, "what": "58 domains"}]),
        idea(2, "formats", "model-other-niches", "Vendor-neutral payroll audit",
             "nothing to do with what this company sells", brand_fit="CORE", link=4, own=False),
    ])


# ==== merge ==========================================================================================

cm.save("scope.md", "# What Example can own\nPractitioner-led programmes for operators.\n"
                    "We are NOT a payroll tool and NOT a job board.\n")

print("merge: stacking the three pools")
plant_pools()
stub_bucket_embeddings()
co = sh.company()
out = merge.run(co, say)

rows = cm.ideas()
stacked = cm.read("_work/merge/stacked.json")
methods = cm.read("_work/merge/methods.json")

ok("stacked all three pools", len(stacked) == 8, len(stacked))
ok("kept every pool's own banded id rather than re-numbering",
   [r["id"] for r in stacked] == [r["_from"] for r in stacked]
   and len({r["id"] for r in stacked}) == 8, sorted(r["id"] for r in stacked))
ok("the bands survive, so an id still says which method found it",
   {r["id"][:2] for r in stacked[:3]} == {"a1"} and {r["id"][:2] for r in stacked[3:6]} == {"a3"}
   and {r["id"][:2] for r in stacked[6:]} == {"a2"}, [r["id"] for r in stacked])
ok("nothing was re-identified, because nothing collided", methods["reidentified"] is None,
   methods["reidentified"])
ok("kept each pool's own id in the working file, so a row is traceable",
   all(r.get("_from") for r in stacked), [r.get("_from") for r in stacked[:3]])
ok("the method comes from the pool file",
   [r["method"] for r in stacked[:3]] == [["competitors"]] * 3
   and stacked[3]["method"] == ["study-trends"] and stacked[6]["method"] == ["model-other-niches"])
ok("recorded all three methods as having run", methods["ran"] == 3 and methods["of"] == 3, methods["line"])
ok("no private key reached ideas.json",
   not any(k.startswith("_") for r in rows for k in r), [k for r in rows for k in r if k.startswith("_")])

print("\nmerge: de-duplication across methods")
dedup = cm.read("_work/merge/dedup.json")
cluster_ids = {tuple(sorted(c["cluster"])) for c in dedup["clusters"]}
ok("nominated only cross-method pairs: the two competitor scorecard ideas were never clustered",
   not any({"a0002", "a0003"} <= set(c) for c in cluster_ids), cluster_ids)
ok("nominated the two clusters that do cross methods", len(dedup["clusters"]) == 2, cluster_ids)

bad = next((r for r in rows if "Bad Hire" in r["title"]), None)
ok("the SAME pair became one row", bad is not None and
   not any("bad-hire cost report" in r["title"] for r in rows))
ok("the survivor kept the clearer title", bad and bad["title"] == "Cost of a Bad Hire, benchmarked")
ok("the survivor records BOTH methods that found it",
   bad and bad["method"] == ["competitors", "study-trends"], bad and bad["method"])
ok("the survivor carries BOTH proofs, not one",
   bad and sorted(p["url"] for p in bad["proof"]) ==
   ["https://reddit.com/r/hr/x", "https://rival-one.com/bad-hire"], bad and bad["proof"])
ok("the survivor keeps its own Linkability score, decided once by its own method",
   bad and bad["linkability"]["score"] == 4, bad and bad["linkability"])
ok("the build flag survives the merge even though it was on the side that merged away",
   bad and bad["tool_escalation"] is True, bad and bad.get("tool_escalation"))

combined = next((r for r in rows if r["title"].startswith("The Skills-Gap Index")), None)
ok("the COMBINE pair became one row with the new title", combined is not None)
ok("the combined row took the new angle",
   combined and combined["angle"].startswith("the gap measured"), combined and combined["angle"])
ok("the combined row pooled both methods",
   combined and combined["method"] == ["study-trends", "model-other-niches"], combined and combined["method"])
ok("the combined row filled its blanks from the other side (effort, beatability, format)",
   combined and combined["effort"] == "M" and combined["beatability"] == 2
   and combined["format"] == "interactive index", combined)
ok("the combined row pooled what-it-would-be too",
   combined and combined["what_it_would_be"].startswith("a live index page"),
   combined and combined.get("what_it_would_be"))
ok("eight stacked ideas became six distinct ones", len(rows) == 6, len(rows))
ok("the dedup report names every cluster the model saw", len(dedup["clusters"]) == 2
   and dedup["same"] == 1 and dedup["combined"] == 1, dedup.get("same"))

print("\nmerge: ranking")
ok("every row carries its rank, 1..N", [r["rank"] for r in rows] == list(range(1, len(rows) + 1)),
   [r["rank"] for r in rows])
ok("the sheet is written best first", rows == sorted(rows, key=lambda r: r["rank"]))
ok("an idea the company cannot own is ranked last, not dropped",
   rows[-1]["title"].startswith("Vendor-neutral payroll")
   and rows[-1]["ownability"]["verdict"] is False, rows[-1]["title"])
ok("brand fit leads: the one ADJACENT idea sits below the CORE ones",
   [r["brand_fit"] for r in rows[:4]] == ["CORE"] * 4 and rows[4]["brand_fit"] == "ADJACENT",
   [r["brand_fit"] for r in rows])
ok("inside a fit tier the shared Linkability score decides",
   rows[0]["linkability"]["score"] == 4 and rows[1]["linkability"]["score"] == 4
   and rows[2]["linkability"]["score"] == 3, [r["linkability"]["score"] for r in rows])
ok("an idea nobody scored is ranked, not dropped, and not sent below the unownable one",
   rows[3]["linkability"]["score"] is None and rows[3]["rank"] < rows[-1]["rank"],
   [(r["id"], (r["linkability"] or {}).get("score"), r["rank"]) for r in rows])
ok("and it is raised for review rather than left to sit there quietly",
   any("never got a Linkability score" in n for n in out["needs_review"]), out["needs_review"])
ok("on a tie the heavier proof wins", rows[0]["title"] == "Cost of a Bad Hire, benchmarked",
   rows[0]["title"])
ok("run() reports what a person needs to see", out["count"] == 6 and out["multi_method"] == 2
   and out["methods"]["ran"] == 3, out)

print("\nmerge: the relevance recheck (the original's E7)")
verdicts = cm.read("_work/merge/relevance-verdicts.json") or []
drops = cm.read("_work/merge/relevance-drops.json") or {}
payroll = next((r for r in rows if r["title"].startswith("Vendor-neutral payroll")), None)

ok("the judge was shown the BRAND SCOPE, not just a list of titles",
   RELEVANCE_PROMPTS and "NOT a payroll tool" in RELEVANCE_PROMPTS[0],
   RELEVANCE_PROMPTS[:1])
ok("the off-brand idea was proposed for dropping, with the reason on the row",
   payroll and payroll["relevance"]["verdict"] == "drop proposed"
   and "payroll" in payroll["relevance"]["why"], payroll and payroll.get("relevance"))
ok("PROPOSED, never deleted: the row is still on the sheet where a person can argue with it",
   payroll is not None and payroll in rows)
ok("...and it is ranked last rather than offered as the next thing to write",
   payroll and payroll["rank"] == len(rows), payroll and payroll["rank"])
ok("an idea that belongs carries no relevance verdict at all",
   all(not (r.get("relevance") or {}).get("verdict") for r in rows if r is not payroll),
   [(r["id"], r.get("relevance")) for r in rows])
ok("every verdict is written down, keeps as well as drops, so the pass is auditable",
   len(verdicts) == len(rows) and {v["decision"] for v in verdicts} == {"KEEP", "DROP"},
   [(v["id"], v["decision"]) for v in verdicts])
ok("and the drops are written separately, each with its reason",
   drops.get("proposed") == 1 and drops["drops"][0]["why"], drops.get("drops"))
ok("a person is told, in plain English, and told nothing was deleted",
   any("ranked last rather than removed" in n for n in out["needs_review"]), out["needs_review"])

# PROTECT. The bad-hire idea carries 136 linking domains across its pooled proof, well over the
# floor, so the judge is never even asked about it: a measurement is harder evidence than a verdict.
ok("an idea with real backlink proof is never even shown to the judge",
   drops.get("protected") == 2 and not any("Bad Hire" in p for p in RELEVANCE_PROMPTS),
   (drops.get("protected"), [p[-400:] for p in RELEVANCE_PROMPTS]))
ok("the protect floor is the original's number", merge.RELEVANCE_PROTECT_DOMAINS == 50)

protected_row = dict(cm.blank_idea("a9001", "competitors"), title="A payroll thing anyway",
                     proof=[{"url": "https://x.com/1", "domains": 60}])
kept_p, rep_p = merge.relevance([protected_row], "scope", "Example", say)
ok("...so even a payroll idea survives if the measurement vouches for it",
   not (kept_p[0].get("relevance") or {}).get("verdict") and rep_p["protected"] == 1, rep_p)

# THE CAP. A judge that wants to gut the sheet is wrong about the sheet, not right about the ideas.
greedy = [dict(cm.blank_idea("a900%d" % i, "competitors"), title="A payroll thing %d" % i,
               proof=[{"url": "https://x.com/%d" % i, "domains": 1}]) for i in range(10)]
kept_c, rep_c = merge.relevance(greedy, "scope", "Example", say)
ok("a pass that wants to drop more than %.0f%% of the sheet is refused, not applied"
   % (100 * merge.RELEVANCE_DROP_CAP),
   rep_c["proposed"] == 10 and rep_c["applied"] is False, rep_c)
ok("the cap is the looser of the percentage and a small absolute number, so a six-idea sheet is "
   "not forbidden from dropping its one piece of junk",
   rep_c["allowed"] == merge.RELEVANCE_MIN_DROPS and merge.RELEVANCE_MIN_DROPS == 3, rep_c)
ok("...and NOTHING is marked when it is refused, so one bad answer cannot gut the sheet",
   all(not (r.get("relevance") or {}).get("verdict") for r in kept_c),
   [r.get("relevance") for r in kept_c])
ok("the refusal is still written to the audit file, with every drop it wanted",
   (cm.read("_work/merge/relevance-drops.json") or {}).get("applied") is False)

print("\nmerge: resume")
n = calls()
merge.run(co, say)
ok("a second run reuses the sheet and calls no model", calls() == n)

# ==== reuse ==========================================================================================

print("\nreuse: with no page index")
r = reuse.run(co, say)
ok("says there is no index and writes nothing", r["files"] == [] and r["needs_review"]
   and "build_page_index" in r["needs_review"][0], r)
ok("left every reuse verdict empty rather than defaulting one",
   all(not (x.get("reuse") or {}).get("verdict") for x in cm.ideas()))

print("\nreuse: against the real page index")
_fixture.stub_voyage()          # word-overlap vectors, so retrieval behaves like retrieval
_index.build(sh.pages_with_bodies(), say=say)
r = reuse.run(co, say)
rows = cm.ideas()
cand = cm.read("_work/reuse/candidates.json")

ok("every idea got a verdict", all((x.get("reuse") or {}).get("verdict") for x in rows),
   [(x["id"], (x.get("reuse") or {}).get("verdict")) for x in rows])
ok("every verdict is one of the four, in the sheet's own words",
   all((x["reuse"]["verdict"]) in cm.REUSE_VERDICTS for x in rows),
   {x["reuse"]["verdict"] for x in rows})
ok("the four verdicts are still in the original's order, so the decision tree is intact",
   cm.REUSE_VERDICTS == ("already have it", "improve existing", "build from parts", "brand new"),
   cm.REUSE_VERDICTS)
ok("retrieval wrote candidates for every idea", set(cand) == {x["id"] for x in rows}, sorted(cand))
ok("the match scores are kept in the working file",
   all("score" in c for v in cand.values() for c in v))
ok("no match score reached ideas.json: the row carries the verdict, its links and why",
   all(set(x["reuse"]) == {"verdict", "links", "why"} for x in rows),
   [set(x["reuse"]) for x in rows[:1]])

scores_in_prompt = []
for p in JUDGE_PROMPTS:
    for v in cand.values():
        for c in v:
            for shown in ("%.3f" % c["score"], "(%s)" % c["score"], " %s)" % c["score"]):
                if c["score"] and shown in p:
                    scores_in_prompt.append(shown)
ok("the judge was never shown a match score, so its verdict came from reading",
   not scores_in_prompt, scores_in_prompt[:3])
ok("the judge was shown the candidate pages themselves",
   JUDGE_PROMPTS and "OUR CLOSEST EXISTING PAGES" in JUDGE_PROMPTS[0]
   and "https://example.com" in JUDGE_PROMPTS[0])
ok("the judge read at most the top-7 window of the top-15 candidates",
   all(p.count("\n[") <= 7 for p in JUDGE_PROMPTS),
   [p.count("\n[") for p in JUDGE_PROMPTS])

bad_links = [(x["id"], u) for x in rows for u in x["reuse"]["links"]
             if u not in {c["url"] for c in cand[x["id"]]}]
ok("every chosen link is one retrieval found; the judge invented none", not bad_links, bad_links)
ok("run() reports the verdict counts", sum(r["counts"].values()) == len(rows), r["counts"])

# THE ASSET ENGINE READS FOUR TIMES WHAT THE ARTICLE FLOW DOES, and both numbers are his. The
# original gives 5-reuse-check's judge JUDGE_DOC_CHARS = 12000, and the mid-article spoke check
# (14-research-conductor/scripts/reuse_one.py) DOC_CHARS = 3000. Only the 3,000 was ported, so this
# builder — the one deciding whether to go and build a thing — was reading a quarter of the page.
print("\nreuse: the read window is the asset engine's, not the article flow's")
from seo_agent.research import _common as _rc, ownpage as _ownpage
from seo_agent.tools import _shared as _sh
ok("the two windows are named apart, with the asset engine's four times the other",
   _rc.JUDGE_DOC_CHARS == 3000 and _rc.ASSET_JUDGE_DOC_CHARS == 12000,
   (_rc.JUDGE_DOC_CHARS, _rc.ASSET_JUDGE_DOC_CHARS))
_long = "cost per hire benchmark data. " * 900        # ~27,000 chars, past both windows
_saved_bodies = _sh.page_bodies
_sh.page_bodies = lambda: {"https://example.com/long": _long}
_pages = [{"url": "https://example.com/long", "title": "Long", "score": 0.9}]
try:
    JUDGE_PROMPTS.clear()
    _ownpage.reuse_judge("a topic", "an angle", _pages, co)
    _article_window = len(JUDGE_PROMPTS[-1])
    JUDGE_PROMPTS.clear()
    # same fmt as the call above, so the ONLY difference between the two prompts is the window
    reuse.judge({"title": "a topic", "angle": "an angle", "format": "article"}, _pages, co)
    _asset_window = len(JUDGE_PROMPTS[-1])
    ok("the article flow's judge still reads its own 3,000 characters of a page",
       _rc.JUDGE_DOC_CHARS <= _article_window < _rc.JUDGE_DOC_CHARS + 3000, _article_window)
    ok("the asset engine's judge reads the full 12,000, so it decides on the evidence and not a "
       "quarter of it", _asset_window - _article_window
       == _rc.ASSET_JUDGE_DOC_CHARS - _rc.JUDGE_DOC_CHARS, (_article_window, _asset_window))
finally:
    _sh.page_bodies = _saved_bodies

print("\nreuse: resume")
n = calls()
reuse.run(co, say)
ok("a second run reuses the verdicts and calls no model", calls() == n)

# ==== a partial sheet, which is the state the engine is actually in ====================================

print("\nmerge: when only one method could run")
os.remove(os.path.join(store.knowledge_dir(), "assets", "competitors.json"))
store.save_knowledge("assets/formats.json", [])
stub_bucket_embeddings()
out = merge.run(co, say, redo=True)
methods = cm.read("_work/merge/methods.json")

ok("merged the one pool that exists", out["count"] == 3, out["count"])
ok("counts only the method that ran", methods["ran"] == 1 and methods["of"] == 3, methods)
ok("tells apart a method that ran and found nothing from one that never ran",
   [m["state"] for m in methods["methods"]] == ["missing", "ran", "empty"],
   [(m["method"], m["state"]) for m in methods["methods"]])
ok("says so in one plain line", "1 of 3 methods ran" in methods["line"]
   and "model-other-niches ran and found nothing" in methods["line"]
   and "competitors did not run" in methods["line"], methods["line"])
ok("flags the partial sheet for review", out["needs_review"]
   and "1 of 3 methods ran" in out["needs_review"][0], out["needs_review"])

print("\nmerge: when the pools collide on their ids")
# What the three builders actually do today (2026-09-09): every one calls `new_id(n)` without its
# method, so the bands in `_common.ID_BASE` never apply and all three pools mint a0001, a0002...
# The merge looks every row up by id, so it has to notice rather than fold two ideas into one.
plant_pools()
for name in ("competitors.json", "trends.json", "formats.json"):
    pool = store.knowledge("assets/" + name)
    for i, row in enumerate(pool, 1):
        row["id"] = cm.new_id(i)                       # no method, so no band: the live defect
    store.save_knowledge("assets/" + name, pool)
stub_bucket_embeddings()
out = merge.run(co, say, redo=True)
stacked = cm.read("_work/merge/stacked.json")
methods = cm.read("_work/merge/methods.json")

ok("noticed the clash instead of folding two ideas onto one id",
   methods["reidentified"] and methods["reidentified"]["n"] == 3, methods.get("reidentified"))
ok("every id in the stack is unique again",
   len({r["id"] for r in stacked}) == len(stacked), len(stacked))
ok("re-numbered from each method's own band, so an id still says where it came from",
   [r["id"] for r in stacked] == ["a1001", "a1002", "a1003", "a3001", "a3002", "a3003",
                                  "a2001", "a2002"], [r["id"] for r in stacked])
ok("still merged the same pairs afterwards", out["count"] == 6 and out["multi_method"] == 2, out)
ok("told a person, and named the real fix",
   any("_common.new_id" in n for n in out["needs_review"]), out["needs_review"])

# THE SCREEN READS THIS RECORD, AND IT READS IT AS THE OTHER SHAPE. `_work/merge/methods.json` has
# two writers: merge.py (here) writes `methods` as a LIST of {method, file, state, ideas}, and
# import_sheet.py writes it as a DICT of {method: state}. `agents_api._assets_payload` called
# .items() on it, so the first real merge would have 500'd the whole Asset ideas tab. Reading the
# file back with cm.read cannot see that: both shapes read back fine and only the consumer
# disagrees. So this feeds the record the merge REALLY wrote to the code that really consumes it.
print("\nthe Asset ideas screen can read the record this merge just wrote")
import agents_api                                        # noqa: E402
payload = agents_api._assets_payload()
ok("the screen survives the merge's own shape, and names the methods that ran",
   isinstance(payload.get("methods_run"), list) and payload["methods_run"], payload.get("methods_run"))
ok("and reports the sheet it just built", payload["built"] and payload["total"] > 0, payload["total"])

print("\nprompts")
ok("every {{TOKEN}} in every merge prompt was filled before the model saw it", not UNFILLED,
   UNFILLED[:3])

print("\nStubbed the model and Voyage. Proves the plumbing, the code-enforced rules and resume, "
      "not judgment quality.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all merge and reuse checks passed")
