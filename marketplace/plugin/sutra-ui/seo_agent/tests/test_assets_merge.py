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
# Each pool numbers itself from a0001, exactly as `_common.new_id` makes a method do, so the stack
# has to re-mint or three rows collide on one id.

def idea(n, method, title, angle, **over):
    row = cm.blank_idea(cm.new_id(n), method)
    row["title"] = title
    row["angle"] = angle
    row["ownability"] = {"verdict": over.pop("own", True), "why": "judged by the method"}
    row["linkability"] = {"score": over.pop("link", 3), "of": 4,
                          "verdict": over.pop("link", 3) >= cm.LINKABILITY_FLOOR, "why": "scored"}
    row.update(over)
    return row


def plant_pools():
    store.save_knowledge("assets/competitors.json", [
        idea(1, "competitor-study", "Cost of a Bad Hire, benchmarked",
             "what a wrong hire costs, by role and company size", brand_fit="CORE", link=4,
             format="benchmark report",
             proof=[{"url": "https://rival-one.com/bad-hire", "domains": 136, "what": "136 domains"}]),
        idea(2, "competitor-study", "Interview Scorecard Template Library",
             "a scorecard per role, free", brand_fit="CORE", link=3, format="template pack"),
        idea(3, "competitor-study", "Interview scorecard pack, printable",
             "the same scorecards as a PDF", brand_fit="CORE", link=3, format="template pack"),
    ])
    store.save_knowledge("assets/trends.json", [
        idea(1, "study-trends", "Annual bad-hire cost report",
             "[people keep arguing about it] we have the numbers", link=3,
             proof=[{"url": "https://reddit.com/r/hr/x", "domains": 0, "what": "412 comments"}]),
        idea(2, "study-trends", "Remote onboarding tension index",
             "[nobody knows if it works] measured", brand_fit="ADJACENT", link=4),
        idea(3, "study-trends", "Skills gap tension report",
             "[the gap everyone complains about] with the complaints attached", brand_fit="CORE",
             link=4),
    ])
    store.save_knowledge("assets/formats.json", [
        idea(1, "model-other-niches", "Skills gap interactive index",
             "an index other niches proved works", brand_fit="TRANSPLANT", link=4,
             format="interactive index", beatability=2, effort="M",
             proof=[{"url": "https://otherniche.com/index", "domains": 58, "what": "58 domains"}]),
        idea(2, "model-other-niches", "Vendor-neutral payroll audit",
             "nothing to do with what this company sells", brand_fit="CORE", link=4, own=False),
    ])


# ==== merge ==========================================================================================

print("merge: stacking the three pools")
plant_pools()
stub_bucket_embeddings()
co = sh.company()
out = merge.run(co, say)

rows = cm.ideas()
stacked = cm.read("_work/merge/stacked.json")
methods = cm.read("_work/merge/methods.json")

ok("stacked all three pools", len(stacked) == 8, len(stacked))
ok("re-minted the ids, so three pools numbered from a0001 do not collide",
   len({r["id"] for r in stacked}) == 8, sorted(r["id"] for r in stacked))
ok("kept each pool's own id in the working file, so a row is traceable",
   all(r.get("_from") for r in stacked), [r.get("_from") for r in stacked[:3]])
ok("the method comes from the pool file",
   [r["method"] for r in stacked[:3]] == [["competitor-study"]] * 3
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
   bad and bad["method"] == ["competitor-study", "study-trends"], bad and bad["method"])
ok("the survivor carries BOTH proofs, not one",
   bad and sorted(p["url"] for p in bad["proof"]) ==
   ["https://reddit.com/r/hr/x", "https://rival-one.com/bad-hire"], bad and bad["proof"])
ok("the survivor keeps its own Linkability score, decided once by its own method",
   bad and bad["linkability"]["score"] == 4, bad and bad["linkability"])

combined = next((r for r in rows if r["title"].startswith("The Skills-Gap Index")), None)
ok("the COMBINE pair became one row with the new title", combined is not None)
ok("the combined row took the new angle",
   combined and combined["angle"].startswith("the gap measured"), combined and combined["angle"])
ok("the combined row pooled both methods",
   combined and combined["method"] == ["study-trends", "model-other-niches"], combined and combined["method"])
ok("the combined row filled its blanks from the other side (effort, beatability, format)",
   combined and combined["effort"] == "M" and combined["beatability"] == 2
   and combined["format"] == "interactive index", combined)
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
ok("on a tie the heavier proof wins", rows[0]["title"] == "Cost of a Bad Hire, benchmarked",
   rows[0]["title"])
ok("run() reports what a person needs to see", out["count"] == 6 and out["multi_method"] == 2
   and out["methods"]["ran"] == 3, out)

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
   and "competitor-study did not run" in methods["line"], methods["line"])
ok("flags the partial sheet for review", out["needs_review"]
   and "1 of 3 methods ran" in out["needs_review"][0], out["needs_review"])

print("\nprompts")
ok("every {{TOKEN}} in every merge prompt was filled before the model saw it", not UNFILLED,
   UNFILLED[:3])

print("\nStubbed the model and Voyage. Proves the plumbing, the code-enforced rules and resume, "
      "not judgment quality.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all merge and reuse checks passed")
