"""tests/test_source_check.py — the source check that runs after the body is written.

Everything is stubbed: the model is a local dispatcher, the write phase's fetch door answers from a
dict, DataForSEO is off. What this proves, in code:
  the FILTER   markers ([11]) are never a claim's number; years, labels and small numbers are skipped;
               the writer's own sums and comparisons are `derived`, and a note about the research is skipped
  the VERDICTS supported / not_supported / unreadable, one per claim, a short page counts as unreadable,
               a card with no url fails, and a bad page never spreads to another claim
  the HUNT     capped at HUNT_CAP claims, the most important first, one queued search batch
  the FIX      correct, soften, remove, each leaving the paragraph readable; code rejects a new digit and
               an out-of-scope edit, retries once with the fault named, then removes the sentence itself
  the LINE     exactly one say() per run, in the shape the chat shows
  the RESUME   a run paused with the OLD work-verify.json and work-freeze.json on disk carries on into
               shape, the body and the new check without error
"""
import copy
import json
import re
import shutil

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import llm, store
from seo_agent.checks import digit_guard
from seo_agent.tools import dfs
from seo_agent.write import _common as C, source_check as SC

FAILS, PASSES = [], []


def ok(label, cond, extra=""):
    (PASSES if cond else FAILS).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))
    return cond


# ---- every door to the outside, nailed shut ---------------------------------------------------------
dfs.available = lambda: False
C.ALIVE = lambda url: True
C.FETCH_GAP = 0.0
PAGES = {}
C.FETCH_ONCE = lambda url, timeout=15.0: PAGES.get(url, "__ERR__ConnectError")

REPLIES, SEEN = [], []


def json_stub(prompt, system=None, retries=1, **kw):
    SEEN.append(prompt)
    for pred, reply in REPLIES:
        if pred(prompt):
            return reply(prompt) if callable(reply) else copy.deepcopy(reply)
    got = _fixture.stub_json(prompt)
    return got if got is not None else {}


def text_stub(prompt, system=None, **kw):
    SEEN.append(prompt)
    return _fixture.stub_text(prompt)


llm.json_call, llm.text = json_stub, text_stub
_fixture.stub_voyage()
_fixture.plant_brand_files()

SAY = []


def say(label, note="", **extra):
    SAY.append((label, note, extra))


def is_judge(p):
    return '"supports": true|false' in p


def is_queries(p):
    return "published source for ONE factual claim" in p


def is_search(p):
    return '"urls": ["https://' in p


def is_fix(p):
    return '"action": "correct" | "soften" | "remove"' in p


def url_of(p):
    m = re.search(r"^URL: ?(\S+)", p, re.M)
    return m.group(1) if m else ""


# ======================================================================================
print("\nthe filter: what gets checked, what is analysis, what is skipped")
CARDS = [
    {"id": 1, "gloss": "Average cost per hire is 4,700 dollars",
     "verbatim": "The average cost per hire was $4,700 in 2023, per the SHRM benchmarking survey [11].",
     "source_urls": ["https://shrm.example.org/cost"], "tag": "evidence"},
    {"id": 2, "gloss": "Soft costs are 60 percent of the total", "verbatim": "Soft costs make up about 60% of the total [17].",
     "source_urls": ["https://shrm.example.org/cost"], "tag": "evidence"},
    {"id": 3, "gloss": "Time to fill averages 42 days", "verbatim": "The average time to fill a position is 42 days.",
     "source_urls": ["https://shrm.example.org/time"], "tag": "evidence"},
    {"id": 4, "gloss": "SHRM tracks race, ethnicity and gender",
     "verbatim": "The survey collects data on race, ethnicity and gender [11].",
     "source_urls": ["https://shrm.example.org/method"], "tag": "evidence"},
    {"id": 5, "gloss": "Published in 2022", "verbatim": "The report was published in 2022.",
     "source_urls": ["https://shrm.example.org/about"], "tag": "evidence"},
    {"id": 6, "gloss": "Type 2 assessments", "verbatim": "Type 2 assessments are the common kind.",
     "source_urls": ["https://x.example.org/types"], "tag": "evidence"},
    {"id": 7, "gloss": "Two of three studies agree", "verbatim": "Two of the three studies agreed.",
     "source_urls": ["https://x.example.org/studies"], "tag": "evidence"},
    {"id": 8, "gloss": "Onboarding costs 2,300 dollars", "verbatim": "Onboarding adds $2,300 per hire.",
     "source_urls": ["https://x.example.org/onboarding"], "tag": "evidence"},
    {"id": 8001, "gloss": "Our own stat", "verbatim": "We run 3,500 assessments a month.", "source_urls": [],
     "source_note": "our data", "tag": "brand-stat"},
]
IDX = C.card_index(CARDS)
BODY = {"sections": [
    {"headline": "What A Hire Costs", "job": "", "word_target": 300, "words": 80, "bad_tags_dropped": 0, "provenance": [],
     "prose": "\n\n".join([
         "The average cost per hire was $4,700 in 2023 [c1]. Soft costs make up about 60% of the total [c2]. "
         "The survey collects data on race, ethnicity and gender, according to SHRM [c4].",
         "The report was published in 2022 [c5]. Type 2 assessments are the common kind [c6]. "
         "Two of the three studies agreed [c7]. We run 3,500 assessments a month [c8001].",
         "Together, hiring and onboarding come to $7,000 per seat [c1, c8]. "
         "Cost per hire, at $4,700, compared with 42 days to fill, tells two stories [c1, c3]. "
         "Some teams report $9,999 per hire [c1].",
         "No collected source gives the 2022 sample size [c1].",
         "10. Time to fill sits at 42 days [c3].",
     ])}]}
claims = SC.classify(BODY, IDX)
by_text = {c["clean"][:30]: c for c in claims}


def kind_of(prefix):
    return next((c for c in claims if c["clean"].startswith(prefix)), {})


ok("a statistic the card states is checked, against that card",
   kind_of("The average cost per hire")["kind"] == "check" and kind_of("The average cost per hire")["card_id"] == 1)
ok("a claim with no number but a named source is checked",
   kind_of("The survey collects")["kind"] == "check" and kind_of("The survey collects")["card_id"] == 4,
   kind_of("The survey collects"))
ok("the card's [11] marker is not a figure of the claim's",
   "11" not in kind_of("The survey collects")["clean"] and not kind_of("The survey collects")["figures"]
   and "11" not in SC._card_figs(IDX[4]))
ok("a year alone is skipped", kind_of("The report was published")["kind"] == "skip")
ok("a number in a label is skipped", kind_of("Type 2")["kind"] == "skip", kind_of("Type 2"))
ok("a small number in passing is skipped", kind_of("Two of the three")["kind"] == "skip")
ok("the company's own material is not checked against the web",
   kind_of("We run 3,500")["kind"] == "skip" and "own material" in kind_of("We run 3,500")["why"])
d1 = kind_of("Together, hiring")
ok("a sum of two cards is derived, and code confirms the arithmetic",
   d1["kind"] == "derived" and d1.get("derived_ok") is True, d1)
d2 = kind_of("Cost per hire, at")
ok("a comparison across two cards is derived", d2["kind"] == "derived", d2)
d3 = kind_of("Some teams report")
ok("a figure in no card that code cannot derive is left as written, and says so",
   d3["kind"] == "derived" and d3.get("derived_ok") is False and "left as written" in d3["why"], d3)
ok("a sentence about the research itself is skipped", kind_of("No collected source")["kind"] == "research_note")
d4 = kind_of("Time to fill sits")
ok("a list item's own number is structure, not a statistic", d4["kind"] == "check" and d4["figures"] == ["42"], d4)
ok("the derived arithmetic: sums, differences, ratios, percentages",
   SC.follows_from("7,000", {"4700", "2300"}) and SC.follows_from("2,400", {"4700", "2300"})
   and SC.follows_from("49%", {"2300", "4700"}) and not SC.follows_from("8,888", {"4700", "2300"}))
ok("strip_markers removes both kinds of bracket and tidies the spaces",
   SC.strip_markers("gender [11] , said so [c4, c5].") == "gender, said so.")

# ======================================================================================
print("\nthe verdicts: one claim, one page, one verdict; nothing spreads")
PAGES.clear()
PAGES.update({
    "https://good.example.org/cost": "SHRM report. The average cost per hire was $4,700 in 2023. " * 30,
    "https://wrong.example.org/culture": "This page is about culture and says nothing about days at all. " * 30,
    "https://wall.example.org/short": "Please enable JavaScript to continue.",
    "https://dead.example.org/gone": "__ERR__HTTP404",
    "https://shared.example.org/both": "The average cost per hire was $4,700 in 2023. Nothing about days here. " * 30,
})
V_CARDS = [
    {"id": 1, "gloss": "cost per hire", "verbatim": "The average cost per hire was $4,700 in 2023.", "source_urls": ["https://good.example.org/cost"], "tag": "evidence"},
    {"id": 2, "gloss": "time to fill", "verbatim": "The average time to fill is 42 days.", "source_urls": ["https://wrong.example.org/culture"], "tag": "evidence"},
    {"id": 3, "gloss": "turnover", "verbatim": "Turnover fell 65% after assessments.", "source_urls": ["https://wall.example.org/short"], "tag": "evidence"},
    {"id": 4, "gloss": "validity", "verbatim": "Validity sits near 0.51.", "source_urls": ["https://dead.example.org/gone"], "tag": "evidence"},
    {"id": 5, "gloss": "no url", "verbatim": "Offers are declined 18% of the time.", "source_urls": [], "tag": "evidence"},
    {"id": 6, "gloss": "cost again", "verbatim": "The average cost per hire was $4,700.", "source_urls": ["https://shared.example.org/both"], "tag": "evidence"},
    {"id": 7, "gloss": "days on shared page", "verbatim": "Time to fill is 42 days.", "source_urls": ["https://shared.example.org/both"], "tag": "evidence"},
]
V_IDX = C.card_index(V_CARDS)
V_BODY = {"sections": [{"headline": "Costs", "job": "", "word_target": 300, "words": 60, "bad_tags_dropped": 0, "provenance": [],
                        "prose": "Cost per hire was $4,700 in 2023 [c1]. Time to fill is 42 days [c2]. Turnover fell 65% [c3]. "
                                 "Validity sits near 0.51 [c4]. Offers are declined 18% of the time [c5].\n\n"
                                 "The same report puts cost per hire at $4,700 [c6]. It puts time to fill at 42 days [c7]."}]}


def judge_by_page(p):
    """Supports when the claim's first figure is on the page shown."""
    claim = SC._norm(p.split("THE CLAIM, AS THE ARTICLE STATES IT:")[1].split("THE EVIDENCE CARD")[0])
    page = SC._norm(p.split("TEXT:\n")[-1].split("\n\nAnswer YES")[0])
    nums = [n for n in re.findall(r"\d[\d]*", claim) if len(n) >= 2]
    return {"supports": all(n in page for n in nums), "quote": "", "note": ""}


REPLIES[:] = [(is_judge, judge_by_page), (is_queries, {"queries": []})]
SEEN.clear()
v_claims = SC.classify(V_BODY, V_IDX)
pages = SC._Pages()
SC.check_all(v_claims, V_IDX, pages)
V = {c["card_id"]: c for c in v_claims if c["kind"] == "check"}
ok("a page that states the figure: supported", V[1]["verdict"] == "supported")
ok("a page that does not: not_supported, with the reason kept", V[2]["verdict"] == "not_supported" and V[2]["reason"])
ok("a page under 500 characters is unreadable, not wrong",
   V[3]["verdict"] == "unreadable" and "500" in V[3]["reason"], V[3])
ok("a page that will not load is unreadable, and names the error",
   V[4]["verdict"] == "unreadable" and "HTTP404" in V[4]["reason"], V[4])
ok("a card with no url cannot be checked and fails", V[5]["verdict"] == "not_supported" and "no source url" in V[5]["reason"])
ok("NO URL-WIDE SPREAD: two claims on one page get their own verdicts",
   V[6]["verdict"] == "supported" and V[7]["verdict"] == "not_supported", (V[6]["verdict"], V[7]["verdict"]))
ok("the judge was asked once per checked claim with a url, and no page was read unjudged",
   sum(1 for p in SEEN if is_judge(p)) == 4, sum(1 for p in SEEN if is_judge(p)))
ok("each url was fetched once", len(pages._got) == 5, sorted(pages._got))

# ======================================================================================
print("\nthe hunt: capped, most important first, one search batch")
H_CARDS = [{"id": i, "gloss": "figure %d" % i, "verbatim": "The measure is %d units." % (100 + i),
            "source_urls": ["https://wrong.example.org/culture"], "tag": "evidence"} for i in range(1, 14)]
H_IDX = C.card_index(H_CARDS)
H_BODY = {"sections": [{"headline": "Twelve Numbers, And One Is 113 Units", "job": "", "word_target": 300, "words": 60,
                        "bad_tags_dropped": 0, "provenance": [],
                        "prose": " ".join("The measure is %d units [c%d]." % (100 + i, i) for i in range(1, 14))}]}
BATCHES = []


def fake_batch(queries, location_name=None, language_code=None, depth=10, say=None):
    BATCHES.append(list(queries))
    return {"urls": {q: [] for q in queries}, "cost": 0.0, "missing": [], "demo": False}


REPLIES[:] = [(is_judge, judge_by_page),
              (is_queries, lambda p: {"queries": ["shared query", "the measure " + re.search(r"is (\d+) units", p).group(1)]})]
dfs.available, dfs.balance, dfs.serp_batch = (lambda: True), (lambda: 50.0), fake_batch
SEEN.clear()
h_claims = SC.classify(H_BODY, H_IDX)
SC.check_all(h_claims, H_IDX, SC._Pages())
log = SC.hunt(h_claims, H_IDX, SC._Pages())
ok("13 claims failed, 10 were hunted", sum(1 for c in h_claims if c["verdict"] == "not_supported") == 13 and len(log) == 10, len(log))
ok("...which is HUNT_CAP", SC.HUNT_CAP == 10 and sum(1 for p in SEEN if is_queries(p)) == 10)
ok("the claim whose figure is in a heading was hunted first", log[0]["card_id"] == 13, [e["card_id"] for e in log])
ok("every query was bought in ONE queued batch, deduped", len(BATCHES) == 1 and BATCHES[0].count("shared query") == 1, BATCHES)
ok("a search that came back empty is recorded as searched with nothing found",
   all(e["searched"] and "none" in e["outcome"] or "no candidate" in e["outcome"] for e in log), [e["outcome"] for e in log][:3])
ok("the chat was not told about any of it here (the step says one line, later)", not SAY)
dfs.available = lambda: False
BATCHES.clear()

# ======================================================================================
print("\nthe fix: correct, soften, remove; each paragraph still reads")
PAGES.update({
    "https://p.example.org/cost": "Cost report. The average cost per hire was $4,700 in 2023. " * 30,
    "https://p.example.org/soft": "Soft costs make up about 58% of the total cost of a hire. " * 30,
    "https://p.example.org/days": "Filling a position takes several weeks in most sectors, the report says. " * 30,
    "https://p.example.org/turnover": "This page is about pets. " * 60,
})
F_CARDS = [
    {"id": 1, "gloss": "cost per hire", "verbatim": "The average cost per hire was $4,700 in 2023.", "source_urls": ["https://p.example.org/cost"], "tag": "evidence"},
    {"id": 2, "gloss": "soft costs", "verbatim": "Soft costs make up about 60% of the total.", "source_urls": ["https://p.example.org/soft"], "tag": "evidence"},
    {"id": 3, "gloss": "time to fill", "verbatim": "The average time to fill a position is 42 days.", "source_urls": ["https://p.example.org/days"], "tag": "evidence"},
    {"id": 4, "gloss": "turnover", "verbatim": "Turnover fell 65% after assessments.", "source_urls": ["https://p.example.org/turnover"], "tag": "evidence"},
]
F_IDX = C.card_index(F_CARDS)
P0 = ("Hiring is expensive. The average cost per hire was $4,700 in 2023 [c1]. Soft costs make up about 60% "
      "of the total [c2]. Budgets rarely reflect that.")
P1 = "The average time to fill a position is 42 days [c3]. That is six weeks of an empty seat."
P2 = "Assessments help. Turnover fell 65% after teams adopted them [c4]. The effect shows up within a year."
F_BODY = {"sections": [{"headline": "Costs", "job": "", "word_target": 300, "words": 70, "bad_tags_dropped": 0, "provenance": [],
                        "prose": P0 + "\n\n" + P1 + "\n\n" + P2}]}


def judge_fix(p):
    u = url_of(p)
    if u.endswith("/cost"):
        return {"supports": True, "quote": "The average cost per hire was $4,700 in 2023.", "note": ""}
    if u.endswith("/soft"):
        return {"supports": False, "quote": "Soft costs make up about 58% of the total cost of a hire.",
                "note": "the page gives 58%, not 60%"}
    return {"supports": False, "quote": "", "note": "the page does not state this"}


FIX_PROMPTS = []


def fix_reply(p):
    FIX_PROMPTS.append(p)
    return {"paragraphs": [
        {"n": 0, "text": "Hiring is expensive. The average cost per hire was $4,700 in 2023 [c1]. Soft costs make up about 58% "
                         "of the total [c2]. Budgets rarely reflect that."},
        {"n": 1, "text": "Filling a position takes several weeks [c3]. That is six weeks of an empty seat."},
        {"n": 2, "text": "Assessments help, and the effect shows up within a year."}],
        "sentences": [{"sentence": "Soft costs make up about 60% of the total [c2].", "action": "correct", "why": "page says 58%"},
                      {"sentence": "The average time to fill a position is 42 days [c3].", "action": "soften", "why": "no figure on the page"},
                      {"sentence": "Turnover fell 65% after teams adopted them [c4].", "action": "remove", "why": "page is about pets"}]}


REPLIES[:] = [(is_judge, judge_fix), (is_queries, {"queries": ["q"]}), (is_search, {"urls": []}), (is_fix, fix_reply)]
SAY.clear()
SEEN.clear()
out = SC.run(copy.deepcopy(F_BODY), F_IDX, say)
prose = out["body"]["sections"][0]["prose"]
ch = {x["card_id"]: x for x in out["report"]["changes"]}
ok("CORRECT: the figure became what the page states, tag kept",
   "58% of the total [c2]" in prose and "60%" not in prose and ch[2]["action"] == "corrected", (prose, ch.get(2)))
ok("SOFTEN: the exact figure is gone, what the page supports stays, tag kept",
   "42 days" not in prose and "several weeks [c3]" in prose and ch[3]["action"] == "softened", ch.get(3))
ok("REMOVE: the sentence is gone and the paragraph was bridged from its own words",
   "65%" not in prose and "[c4]" not in prose and "Assessments help, and the effect shows up within a year." in prose
   and ch[4]["action"] == "removed", ch.get(4))
ok("the supported sentence is untouched", "$4,700 in 2023 [c1]" in prose)
ok("ONE model call fixed the whole section", len(FIX_PROMPTS) == 1, len(FIX_PROMPTS))
ok("the fix prompt showed the page's own figure for the correction", "58%" in FIX_PROMPTS[0])
ok("the provenance follows the prose: card 4 is gone, cards 1 to 3 remain",
   [p["card_id"] for p in out["body"]["sections"][0]["provenance"]] == [1, 2, 3], out["body"]["sections"][0]["provenance"])
ok("every change carries a before and an after", all(x["before"] and ("after" in x) for x in out["report"]["changes"]))
ok("the correction is saved with its evidence, for the digit guard",
   out["report"]["corrections"] and "58%" in out["report"]["corrections"][0]["evidence"], out["report"]["corrections"])
ok("the digit guard accepts the corrected figure once the report is on file",
   digit_guard.check("# T\n\nSoft costs make up about 58% of the total.",
                     {"cards.json": F_CARDS, "brand_text": "", "source-check.json": out["report"]})["status"] == "pass"
   and digit_guard.check("# T\n\nSoft costs make up about 58% of the total.",
                         {"cards.json": F_CARDS, "brand_text": ""})["status"] == "fail")
ok("the ONE line: what was checked and what changed",
   len(SAY) == 1 and SAY[0][0] == "Checked 4 facts: 1 fine, 1 corrected, 1 softened, 1 removed", SAY)
ok("the line points at the report artifact", SAY[0][2].get("artifact") == "source-check.md", SAY[0][2])
ok("the readable report carries the counts and every before/after",
   "| Corrected to the page's figure | 1 |" in out["markdown"] and "Before: Turnover fell 65%" in out["markdown"]
   and "(sentence removed)" in out["markdown"], out["markdown"][:600])
md = out["markdown"]
ok("no em dashes in what a person reads", "—" not in md and "—" not in SAY[0][0])

# ======================================================================================
print("\nthe code gate: a new digit, an out-of-scope edit, then the fallback")
BAD = [
    # attempt 1: a figure that is neither in the paragraph nor on the page
    {"paragraphs": [{"n": 1, "text": "The average time to fill a position is 45 days [c3]. That is six weeks of an empty seat."}],
     "sentences": [{"sentence": "The average time to fill a position is 42 days [c3].", "action": "correct"}]},
    # attempt 2: the listed sentence removed, but the neighbour rewritten too
    {"paragraphs": [{"n": 1, "text": "An empty seat costs more than most budgets admit, and it stays empty for longer."}],
     "sentences": [{"sentence": "The average time to fill a position is 42 days [c3].", "action": "remove"}]},
]
ATTEMPTS = []


def bad_fix(p):
    ATTEMPTS.append(p)
    return BAD[min(len(ATTEMPTS) - 1, len(BAD) - 1)]


def judge_days_only(p):
    return {"supports": not url_of(p).endswith("/days"), "quote": "", "note": ""}


REPLIES[:] = [(is_judge, judge_days_only), (is_queries, {"queries": ["q"]}), (is_search, {"urls": []}), (is_fix, bad_fix)]
SAY.clear()
out2 = SC.run(copy.deepcopy(F_BODY), F_IDX, say)
prose2 = out2["body"]["sections"][0]["prose"]
ok("the first answer was rejected for the new digit, and the retry was told why",
   len(ATTEMPTS) == 2 and "YOUR LAST ANSWER WAS REJECTED" in ATTEMPTS[1] and "45" in ATTEMPTS[1], len(ATTEMPTS))
ok("the second answer was rejected for touching an unlisted sentence",
   out2["report"]["changes"][0]["by"] == "code" and "not on the list" in out2["report"]["changes"][0]["why"],
   out2["report"]["changes"])
ok("FALLBACK: code removed the sentence and left the neighbour exactly as written",
   "42 days" not in prose2 and "That is six weeks of an empty seat." in prose2 and P0 in prose2 and P2 in prose2, prose2)
ok("the record says removed, by code", out2["report"]["changes"][0]["action"] == "removed")
ok("still one line", len(SAY) == 1 and "1 removed" in SAY[0][0], SAY)

# the gate on its own
ok("validate_block: a new tag is refused",
   "source tag" in SC.validate_block(P1, "The average time to fill is weeks [c3, c9]. That is six weeks of an empty seat.",
                                     ["The average time to fill a position is 42 days [c3]."], set()))
ok("validate_block: an added sentence is refused",
   "added a sentence" in SC.validate_block(P1, "It takes weeks [c3]. That is six weeks of an empty seat. Plan for it.",
                                           ["The average time to fill a position is 42 days [c3]."], set()))
ok("validate_block: a figure the page states is allowed for a correction",
   SC.validate_block(P1, "The average time to fill a position is 44 days [c3]. That is six weeks of an empty seat.",
                     ["The average time to fill a position is 42 days [c3]."], {"44"}) == "")
ok("validate_block: a connective word on the neighbour passes, a rewrite does not",
   SC.validate_block(P1, "Filling a seat takes weeks [c3]. And that is six weeks of an empty seat.",
                     ["The average time to fill a position is 42 days [c3]."], set()) == ""
   and "not on the list" in SC.validate_block(P1, "Filling a seat takes weeks [c3]. Empty seats are costly.",
                                              ["The average time to fill a position is 42 days [c3]."], set()))

# a model that fails outright also falls back to code
REPLIES[:] = [(is_judge, judge_days_only), (is_queries, {"queries": ["q"]}), (is_search, {"urls": []}),
              (is_fix, lambda p: (_ for _ in ()).throw(ValueError("Model did not return valid JSON")))]
out3 = SC.run(copy.deepcopy(F_BODY), F_IDX, say)
ok("a model that returns nothing usable: the sentence is removed by code",
   "42 days" not in out3["body"]["sections"][0]["prose"] and out3["report"]["changes"][0]["by"] == "code")

# ======================================================================================
print("\nthe summary line, in every shape")
ok("the shape the chat shows",
   SC.summary_line({"checked": 59, "supported": 50, "unreadable": 0, "replaced": 3, "corrected": 1, "softened": 3, "removed": 2})
   == "Checked 59 facts: 50 fine, 3 new sources, 1 corrected, 3 softened, 2 removed")
ok("zero counts are left out", SC.summary_line({"checked": 4, "supported": 4, "unreadable": 0, "replaced": 0, "corrected": 0,
                                                 "softened": 0, "removed": 0}) == "Checked 4 facts: 4 fine")
ok("unreadable pages are named as kept",
   "2 could not be read (kept)" in SC.summary_line({"checked": 5, "supported": 3, "unreadable": 2, "replaced": 0,
                                                    "corrected": 0, "softened": 0, "removed": 0}))
ok("a body with nothing to check says so", SC.summary_line({"checked": 0}).startswith("Checked 0 facts"))

# ======================================================================================
print("\nresuming a run that was paused with the OLD work-verify.json and work-freeze.json on disk")
REPLIES[:] = []
_fixture.stub_write_network()
c = store.new_chat("resume old cache"); r = store.new_run(c, "cost per hire")
_fixture.plant_write_inputs(c, r)
events = []
ctx = {"chat_id": c, "run_id": r, "step_id": "s1", "emit": lambda **kw: events.append(kw)}
from seo_agent.tools import write_article
first = write_article.run(ctx)
ok("a fresh run finishes with the new check in it",
   not first.get("error") and store.load_artifact(c, r, "work-source_check.json") is not None
   and store.load_artifact(c, r, "source-check.md"), first)
ok("the write report names the new step and not the old one",
   "source_check" in (store.load_artifact(c, r, "write-report.json") or {}).get("steps", {})
   and "verify" not in (store.load_artifact(c, r, "write-report.json") or {}).get("steps", {}))
# Now make it look like one of the three paused runs: planner done under the OLD code, nothing after.
import os
art = os.path.dirname(store.artifact_path(c, r, "x"))
for name in os.listdir(art):
    if name.startswith("work-") and name not in ("work-gather.json", "work-route.json", "work-select.json", "work-freeze.json"):
        os.remove(os.path.join(art, name))
for name in ("draft.md", "article.json", "write-report.json", "source-check.json", "source-check.md", "links-report.json"):
    if os.path.exists(os.path.join(art, name)):
        os.remove(os.path.join(art, name))
old_plan = store.load_artifact(c, r, "work-freeze.json")["plan"]
store.save_artifact(c, r, "work-verify.json", {
    "plan": old_plan,
    "card_fixes": {"3": {"source_urls": [], "needs_source": True, "note": "source proven wrong, no replacement found, kept and flagged"}},
    "police": {"kept_ok": [1, 2], "unverifiable_kept": [5], "needs_source": [{"card_id": 3, "claim": "42 days", "why": "old"}],
               "cut": [], "kept_unsourced": [], "bad_urls": ["https://www.shrm.org/research/time-to-fill"], "propagated": [],
               "dropped_h3s": [], "dropped_sections": [], "replaced": [], "hunt": "old", "hunt_route": "model",
               "hunt_searched": 0, "failed_worthy_batches": 0,
               "coverage": {"claims_to_check": 5, "actually_judged": 3, "unloadable": 1}}})
store.save_artifact(c, r, "work-freeze.json", {"hard": [], "soft": ["1 card(s) kept without a checked source; still in the plan"], "plan": old_plan})
events.clear()
second = write_article.run(ctx)
labels = [e.get("label") or "" for e in events]
ok("the paused run carries on to a finished draft without error",
   not second.get("error") and store.load_artifact(c, r, "draft.md"), second)
ok("the planner's cache was reused, the old verify file was never a step",
   any(l == "Reusing: Freezing the plan" for l in labels) and not any("Checking the sources behind every number" in l for l in labels)
   and store.load_artifact(c, r, "work-verify.json") is not None, labels[:8])
ok("shape, the body and the new check all ran",
   store.load_artifact(c, r, "work-shape.json") and store.load_artifact(c, r, "work-write_body.json")
   and store.load_artifact(c, r, "work-source_check.json") and any(l.startswith("Checked ") for l in labels), labels)
ok("the check said its one line, with the report reachable",
   sum(1 for l in labels if l.startswith("Checked ")) == 1
   and any(e.get("artifact") == "source-check.md" for e in events if (e.get("label") or "").startswith("Checked ")))
shutil.rmtree(store.chat_dir(c), ignore_errors=True)

print("\n%d checks, %d failed" % (len(PASSES) + len(FAILS), len(FAILS)))
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
    raise SystemExit(1)
print("all source-check checks passed")
