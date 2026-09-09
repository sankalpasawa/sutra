"""tests/test_picture.py — the search picture: the one file that shows what the search results said.

The owner asked for something he can read WHILE the article is being written, instead of being
stopped and asked to approve things (2026-09-09). It is built at the end of the gather step, once
the People-Also-Ask questions and the related searches have been vetted, and it is PURE ASSEMBLY.

What this proves is the discipline, not the prose:
  - every section is on the page, in the agreed order;
  - the numbers are the ones the research step wrote, character for character, not restated;
  - the question count is honest in BOTH directions: how many the search results raised and how
    many were kept, so nine questions where twenty-two were raised does not read as things going
    missing;
  - a run with no measured numbers says the figures are placeholders;
  - a run missing a whole section degrades to a plain line instead of crashing or printing "None";
  - NO model call is made to build it. A model writing this page could quietly drop a number or
    soften a gap, and then the page stops being evidence of anything.
"""
import copy
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.research import render
from seo_agent.tools import dfs, write_article
from seo_agent.write import gather, plan_select

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" | " + str(extra)) if extra and not cond else ""))
    return cond


# The nine sections, in the order the owner asked for them.
SECTIONS = [
    "## The keyword and its numbers",
    "## Who ranks now",
    "## What they all cover",
    "## What none of them cover",
    "## What the winners cover that this article should not",
    "## The questions worth answering",
    "## Related searches",
    "## Who this is written for",
    "## The verdict, and the angle it argued for",
]

# One research run, with numbers chosen so a restated version would look different: 2413 becomes
# "2,413" the moment anything reformats it, and 37 is not a round number either.
RESEARCH = {
    "topic": "What cost per hire really includes",
    "angle": "Lead with what the number leaves out, not the benchmark.",
    "demo_data": False,
    "keywords": {
        "primary": {"keyword": "cost per hire", "volume": 2413, "kd": 37, "intent": "informational",
                    "why": "best volume we can win"},
        "variations": [{"keyword": "hiring cost", "volume": 881, "kd": 29}],
        "secondary": [{"keyword": "time to fill", "volume": 1904, "kd": 33}],
    },
    "serp": {
        "who_ranks": [{"rank": 1, "domain": "shrm.org", "title": "Cost per hire", "url": "https://www.shrm.org/x"},
                      {"rank": 2, "domain": "rival-one.com", "title": "The real cost", "url": "https://rival-one.com/x"}],
        "who_ranks_text": "Two big HR bodies and one vendor blog hold the first page.",
        "paa_on": ["What is a good cost per hire?", "How do you calculate cost per hire?",
                   "What is included in cost per hire?", "Is cost per hire the same as cost of hire?"],
        "paa_off": ["What is the cost of a college application?", "How much does a hackathon cost?"],
        "related_on": ["cost per hire formula", "average cost per hire 2024", "cost per hire benchmark"],
        "related_off": ["hackathon prizes"],
    },
    "winners": {"format": "how-to guide",
                "common_h2s": ["Formula / how to calculate it", "Industry benchmarks", "Hard vs soft costs"],
                "drift": ["Candidate-side salary negotiation advice"],
                "gaps_to_own": ["The cost of the empty seat, priced"]},
    "verdict": ["Write it: nobody prices the empty seat."],
    "topic_gate": {"relevant": True, "why": "the ranking pages all stop at the invoice",
                   "angle_changed": True, "why_changed": "the results argue about what is left out"},
    "persona": {"name": "Head of Talent", "lens": "owns the hiring budget and the time to fill",
                "why": "they sign off the number"},
}

VETTED = {
    "paa_raw": RESEARCH["serp"]["paa_on"],
    "paa_kept": RESEARCH["serp"]["paa_on"][:2],
    "related_raw": RESEARCH["serp"]["related_on"],
    "related_kept": RESEARCH["serp"]["related_on"][:2],
    "table_stakes_raw": RESEARCH["winners"]["common_h2s"],
    "table_stakes_kept": RESEARCH["winners"]["common_h2s"][:2],
}

GROUP_B = {"gaps_to_own": RESEARCH["winners"]["gaps_to_own"],
           "winners_common_h2s": RESEARCH["winners"]["common_h2s"],
           "paa_pool": VETTED["paa_kept"], "related_searches": VETTED["related_kept"]}


# ======================================================================================
# 1. NO MODEL CALL. The whole point of the file: a straight lift, so what he reads is what
#    the steps produced. The model is a landmine for the length of this test.
print("\nthe search picture is pure assembly")
CALLS = []


def _landmine(*a, **k):
    CALLS.append(a[0][:60] if a else "")
    raise AssertionError("the search picture called the model")


llm.json_call, llm.text = _landmine, _landmine
DOC = render.search_picture(RESEARCH, VETTED, plan_select.tag_maps(GROUP_B))
ok("no model call was made to build the picture", CALLS == [], CALLS)

# ---- every section, in order ---------------------------------------------------------
for head in SECTIONS:
    ok("the picture has %s" % head.strip("# "), head in DOC, DOC[:120])
ok("the sections are in the order he asked for",
   [DOC.find(h) for h in SECTIONS] == sorted(DOC.find(h) for h in SECTIONS),
   [(h, DOC.find(h)) for h in SECTIONS])
ok("the page says nothing on it was written by a model", "no model wrote this page" in DOC)

# ---- the numbers are LIFTED, not restated --------------------------------------------
ok("the primary keyword's volume is the number the research step wrote", "2413" in DOC, DOC[:400])
ok("nothing reformatted that number on the way", "2,413" not in DOC)
ok("its difficulty and intent are on the page too", "37" in DOC and "informational" in DOC)
ok("a variation's volume is lifted as well", "881" in DOC and "hiring cost" in DOC)
ok("a secondary's volume is lifted as well", "1904" in DOC and "time to fill" in DOC)
ok("the reason the keyword was chosen is lifted verbatim", "best volume we can win" in DOC)

# ---- who ranks, what they cover, what they miss, what to avoid ------------------------
ok("who ranks now names the domain and the url",
   "shrm.org" in DOC and "https://www.shrm.org/x" in DOC and "rival-one.com" in DOC)
ok("the read of the results is lifted verbatim", "Two big HR bodies and one vendor blog" in DOC)
ok("what they all cover lists the shared topics", "Industry benchmarks" in DOC)
ok("what none of them cover is the gap the research found", "The cost of the empty seat, priced" in DOC)
ok("the avoid list is on the page under its own heading",
   "Candidate-side salary negotiation advice" in DOC.split("## The questions worth answering")[0])

# ---- the ids are the plan's ids -------------------------------------------------------
ids = plan_select.tag_maps(GROUP_B)
ok("the questions carry the same Q ids the plan tags against",
   "**Q1**" in DOC and ids["paa"]["Q1"] == VETTED["paa_kept"][0], ids["paa"])
ok("the gap carries its G id and a shared topic its T id", "**G1**" in DOC and "**T1**" in DOC)
ok("a shared topic that survived the filter is marked kept", "(kept)" in DOC)

# ---- the count, in both directions ----------------------------------------------------
print("\nthe filtered set says so, in numbers")
qs = DOC.split("## The questions worth answering")[1].split("## Related searches")[0]
ok("the questions section says how many the search results returned", "6 questions" in qs, qs[:300])
ok("it says how many survived the research step's world filter", "leaving 4" in qs, qs[:300])
ok("it says how many were kept for this article", "2 are kept here" in qs, qs[:300])
ok("it says in words that this is the filtered set",
   "not everything the search results raised" in qs, qs[:300])
DROPPED = "**Raised, but not kept for this article**"
ok("the questions kept are the vetted ones, not the raw list",
   "What is a good cost per hire?" in qs.split(DROPPED)[0] and "What is included in cost per hire?" in qs.split(DROPPED)[1],
   qs[:400])
ok("the ones the filter dropped are still visible, so nothing looks lost",
   DROPPED in qs and "Is cost per hire the same as cost of hire?" in qs.split(DROPPED)[1], qs[:400])
rel = DOC.split("## Related searches")[1].split("## Who this is written for")[0]
ok("the related searches carry the same two counts", "4 related searches" in rel and "2 are kept here" in rel, rel[:300])

# ---- the reader, the verdict, the angle -----------------------------------------------
ok("the reader is named with the lens the research picked",
   "Head of Talent" in DOC and "Their lens: owns the hiring budget" in DOC)
ok("the verdict is lifted verbatim", "Write it: nobody prices the empty seat." in DOC)
ok("the angle is on the page", "Lead with what the number leaves out" in DOC)
ok("a rewritten angle says it was rewritten from the real results",
   "rewritten from the real search results" in DOC)

# ======================================================================================
# 2. NO MEASURED NUMBERS. The owner's DataForSEO balance is minus seven cents, so this is
#    the common case: the page must say the figures are placeholders, never present them
#    as measurements.
print("\na run with no measured numbers says so")
demo = copy.deepcopy(RESEARCH)
demo["demo_data"] = True
demo["keywords"]["primary"] = {"keyword": "cost per hire", "volume": None, "kd": None, "intent": ""}
demo["keywords"]["variations"] = ["hiring cost"]
demo["keywords"]["secondary"] = []
DEMO_DOC = render.search_picture(demo, VETTED, ids)
ok("the demo banner is at the top, not in a footnote",
   "DEMO DATA" in DEMO_DOC.split("## The keyword")[0], DEMO_DOC[:200])
ok("it says the figures are placeholders, not measurements", "not a measurement" in DEMO_DOC)
ok("a figure that was never measured says so instead of showing a number",
   "not measured" in DEMO_DOC, DEMO_DOC[:600])
ok("the word None never reaches the page", "None" not in DEMO_DOC,
   [l for l in DEMO_DOC.splitlines() if "None" in l])
ok("a real run carries no demo banner", "DEMO DATA" not in DOC)

# ======================================================================================
# 3. A MISSING SECTION degrades to a plain line. A half-finished run still has to render.
print("\nnothing crashes and nothing prints None when a step wrote nothing")
EMPTY = render.search_picture({}, {}, None)
for head in SECTIONS:
    ok("an empty run still has %s" % head.strip("# "), head in EMPTY)
ok("an empty run prints a plain line, never None or a traceback",
   "None" not in EMPTY and "(none)" in EMPTY and "(nothing was recorded for this run)" in EMPTY,
   EMPTY[:400])
ok("an empty run says plainly that nothing was filtered, rather than implying a filter ran",
   "there was nothing to filter" in EMPTY, EMPTY.split("## The questions")[1][:200])
HALF = render.search_picture({"topic": "half a run", "keywords": {"primary": {"keyword": "x"}}},
                             {"paa_raw": ["a?"], "paa_kept": ["a?"]}, None)
ok("a half-finished run renders every section too", all(h in HALF for h in SECTIONS))
ok("and one question kept out of one raised reads as English, not as a count",
   "1 question. 1 is kept here" in HALF, HALF.split("## The questions")[1][:200])
ok("and prints no None", "None" not in HALF, [l for l in HALF.splitlines() if "None" in l])

# ======================================================================================
# 4. THROUGH THE REAL STEP. gather is the only place the picture is built, and the only
#    model call in that step is the vetting one.
print("\ngather builds it at the end, after the filter, with one model call and no more")
GCALLS = []


def _stub(prompt, system=None, retries=1):
    GCALLS.append(prompt[:80])
    if '"keep_table_stakes"' in prompt:
        # keep two of the four questions, one of the three related searches
        return {"keep_questions": RESEARCH["serp"]["paa_on"][:2],
                "keep_related": RESEARCH["serp"]["related_on"][:1],
                "keep_table_stakes": RESEARCH["winners"]["common_h2s"][:2]}
    return _fixture.stub_json(prompt)


llm.json_call, llm.text = _stub, _fixture.stub_text
BP, RS, CARDS = _fixture.write_inputs()
RS = copy.deepcopy(RS)
RS["serp"].update({"paa_on": RESEARCH["serp"]["paa_on"], "paa_off": RESEARCH["serp"]["paa_off"],
                   "related_on": RESEARCH["serp"]["related_on"], "related_off": RESEARCH["serp"]["related_off"],
                   "who_ranks": RESEARCH["serp"]["who_ranks"]})
RS["keywords"]["primary"] = dict(RESEARCH["keywords"]["primary"])
out = gather.run(BP, RS, CARDS, lambda *a: None)
pic = out.get("search_picture") or ""
ok("gather returns the picture with its other outputs", bool(pic.strip()), list(out))
ok("gather made exactly one model call, the vetting one", len(GCALLS) == 1, GCALLS)
ok("the picture holds every section", all(h in pic for h in SECTIONS),
   [h for h in SECTIONS if h not in pic])
ok("the picture shows the KEPT questions, the ones the plan will use",
   all(q in pic for q in out["group_b"]["paa_pool"]))
ok("and it counts both sides of the filter",
   "6 questions" in pic and "2 are kept here" in pic, pic.split("## The questions")[1][:300])
ok("the picture's ids are the ids the plan mints from the same lists",
   plan_select.tag_maps(out["group_b"])["paa"]["Q1"] == out["group_b"]["paa_pool"][0])
ok("the raw research numbers survive into the picture", "2413" in pic)

# ======================================================================================
# 5. THE WHOLE WRITE PHASE. The file has to land in the run's artifacts under exactly the
#    name the Library looks for, or the screen showing it finds nothing.
print("\nthe write phase saves it as search-picture.md, and a resumed run still has it")
llm.json_call, llm.text = _fixture.stub_json, _fixture.stub_text
_fixture.stub_voyage()
_fixture.plant_brand_files()
_fixture.stub_write_network()
dfs.available = lambda: False
chat = store.new_chat("picture test")
run = store.new_run(chat, "cost per hire")
_fixture.plant_write_inputs(chat, run)
notes = []
res = write_article.run({"chat_id": chat, "run_id": run, "step_id": "s1",
                         "emit": lambda **kw: notes.append(kw.get("label") or "")})
saved = store.load_artifact(chat, run, "search-picture.md") or ""
ok("the write phase finished", not res.get("error"), res)
ok("search-picture.md is in the run's artifacts, spelled the way the Library reads it",
   bool(saved.strip()), sorted(store.load_artifact(chat, run, "write-report.json") or {}))
ok("the saved file holds every section", all(h in saved for h in SECTIONS),
   [h for h in SECTIONS if h not in saved])
ok("the saved file says the questions are the filtered set",
   "kept here" in saved and "not everything the search results raised" in saved)
ok("the run says the picture is ready to read, in plain English",
   any("search picture" in n.lower() for n in notes), notes[:6])
ok("the picture is written BEFORE the plan is judged",
   [n.lower() for n in notes].index(next(n.lower() for n in notes if "search picture" in n.lower()))
   < [n.lower() for n in notes].index(next(n.lower() for n in notes if "earn their place" in n.lower())),
   notes[:10])
again = write_article.run({"chat_id": chat, "run_id": run, "step_id": "s2", "emit": lambda **kw: None})
ok("a resumed run still leaves the file there", (store.load_artifact(chat, run, "search-picture.md") or "") == saved,
   again.get("error"))
shutil.rmtree(store.chat_dir(chat), ignore_errors=True)

print("\nPure assembly, no model call. Proves the shape and the counts, not the prose.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all picture checks passed")
