"""tests/test_keyword_same_article.py — the keyword has to be the same article, or it is replaced.

THE INCIDENT (found 2026-09-22 while reading Devansh's own published runs). The article
"Skills Assessment: From Resume Claim to Cut Score" carries a primary keyword of
**"behavioral interview questions"** -- 12,100 searches a month, difficulty 21. The pages it then
studied were "30 behavioral interview questions to ask" listicles, and their common headings were
teamwork, adaptability and communication. The article is about cut scores.

`judge-keywords.md` says, in its own words:

    "PRIMARY (exactly 1): from the heads that match the article's intent AND clear KD, pick the
     HIGHEST-VOLUME one. Do NOT default to the exact article-title phrase if a higher-volume
     intent-match exists"

It optimises volume. Nothing asked whether a page ranking for that keyword would be THIS article.
And the keyword decides the SERP, which decides the winners, which decide the table stakes, the
gaps, the format and the rewritten angle. So one wrong pick made every demand signal for the run
wrong, at a cost of $0.44 of DataForSEO and hours of model time.

What this pins:

  1. A MISMATCH IS CAUGHT, and a match is left alone. Most keywords are fine and rejecting a good
     one costs a better one, so the prompt is told to be slow to say no.
  2. IT NEVER HALTS. Devansh asked this directly: "how will you choose the next keyword, I don't
     want you to fucking stop". A rejection drops to the next measured candidate; after three the
     judge's own pick stands and the doubt is SAID rather than buried.
  3. THE RUNNERS-UP EXIST AT ALL. The judge used to return one head term and discard the rest, so
     there was nowhere to go. Ranked by the scorer's own relevance, then volume, and anything it
     called off-topic (relevance <= 2) is not a fallback: swapping a wrong keyword for an
     irrelevant one is not a recovery.
  4. IT FAILS OPEN IN EVERY DIRECTION. No pages, no verdict, an exception: all answer yes. A check
     that cannot run must never be the reason a run stops.
  5. IT IS ALMOST FREE. The SERP is bought anyway; only a rejection costs a second fetch.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.research import _common as _c, keywords, serp
from seo_agent.tools import _shared as sh

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


LISTICLES = {"top_organic": [
    {"title": "30 Behavioral Interview Questions to Ask", "url": "https://a.example/30"},
    {"title": "Top behavioural questions for hiring", "url": "https://b.example/top"}]}
WORLD = {"about": "verifying claimed skills with tests", "not_about": "interview technique"}


# ---- 1. it catches the real failure, and leaves a good keyword alone ---------------------------
print("the check catches the mismatch that shipped, and only that")

_orig = llm.json_call
llm.json_call = lambda p, **k: {"same_article": False, "why": "these are interview question lists"}
try:
    bad_ok, bad_why = serp.same_article("behavioral interview questions", LISTICLES,
                                        "Skills Assessment: From Resume Claim to Cut Score", WORLD)
finally:
    llm.json_call = _orig
ok("the keyword that actually shipped is rejected", bad_ok is False, (bad_ok, bad_why))
ok("and the reason is in plain words a person can read", "interview question" in bad_why.lower())

llm.json_call = lambda p, **k: {"same_article": True, "why": "same need, worse pages"}
try:
    good_ok, _w = serp.same_article("skills assessment", LISTICLES, "Skills Assessment", WORLD)
finally:
    llm.json_call = _orig
ok("a keyword whose pages answer the same need is kept", good_ok is True)

seen = {}
llm.json_call = lambda p, **k: (seen.setdefault("p", p), {"same_article": True, "why": "x"})[1]
try:
    serp.same_article("a keyword", LISTICLES, "A topic", WORLD)
finally:
    llm.json_call = _orig
prompt = seen.get("p", "")
ok("the judge sees the real ranking pages, titles and all",
   "30 Behavioral Interview Questions to Ask" in prompt)
ok("it sees what the article is NOT about, which is how a near-miss is spotted",
   "interview technique" in prompt)
ok("and it is told to be SLOW to reject, because a false no costs a better keyword",
   "slow to say different" in prompt.lower())
ok("every token was filled", "{{" not in prompt, prompt[:160])


# ---- 2. it fails open in every direction --------------------------------------------------------
print("\nit fails open: a check that cannot run never stops a run")

ok("no ranking pages at all", serp.same_article("k", {"top_organic": []}, "t", WORLD)[0] is True)
ok("an extract that is not even a dict", serp.same_article("k", None, "t", WORLD)[0] is True)


def _boom(*_a, **_k):
    raise RuntimeError("the wire is down")


llm.json_call = _boom
try:
    ok("the model call raising", serp.same_article("k", LISTICLES, "t", WORLD)[0] is True)
finally:
    llm.json_call = _orig

llm.json_call = lambda p, **k: {"nonsense": 1}
try:
    ok("a reply with no verdict in it", serp.same_article("k", LISTICLES, "t", WORLD)[0] is True)
finally:
    llm.json_call = _orig

llm.json_call = lambda p, **k: None
try:
    ok("no reply at all", serp.same_article("k", LISTICLES, "t", WORLD)[0] is True)
finally:
    llm.json_call = _orig

ok("and the prompt itself says to answer SAME when there is nothing to read",
   "answer same" in prompt.lower())


# ---- 3. there is somewhere to go next -----------------------------------------------------------
print("\na rejection has somewhere to go, so the run never stops")

rows = [{"keyword": "cut scores", "relevance": 9},
        {"keyword": "skills testing", "relevance": 7},
        {"keyword": "office chairs", "relevance": 1},
        {"keyword": "cut scores", "relevance": 9}]
by_kw = {"cut scores": {"kw": "cut scores", "vol": 90},
         "skills testing": {"kw": "skills testing", "vol": 40},
         "office chairs": {"kw": "office chairs", "vol": 90000}}

alts = keywords._alternates(rows, by_kw, "cut scores")
names = [a["keyword"] for a in alts]
ok("the chosen keyword is not offered back as its own replacement", "cut scores" not in names, names)
ok("a real alternative is offered", "skills testing" in names, names)
ok("something the scorer called off-topic is NOT a fallback, whatever its volume",
   "office chairs" not in names, names)
ok("duplicates are not offered twice", len(names) == len(set(names)), names)
ok("the runners-up carry their measured numbers, not the judge's memory of them",
   all(a.get("volume") is not None for a in alts), alts)

high_vol_low_rel = keywords._alternates(
    [{"keyword": "skills testing", "relevance": 7}, {"keyword": "office chairs", "relevance": 3}],
    by_kw, "cut scores")
ok("relevance leads and volume only breaks ties: a huge irrelevant head does not jump the queue",
   [a["keyword"] for a in high_vol_low_rel][0] == "skills testing",
   [a["keyword"] for a in high_vol_low_rel])

ok("there is a hard limit on how many keywords get checked, so a bad run cannot loop",
   isinstance(_c.SAME_ARTICLE_TRIES, int) and 1 <= _c.SAME_ARTICLE_TRIES <= 5,
   _c.SAME_ARTICLE_TRIES)


# ---- 4. the judge is no longer chasing volume alone ---------------------------------------------
print("\nthe run records what it checked, so a swap is never silent")

src = open("seo_agent/tools/run_research.py").read()
ok("every verdict is written onto the research, not just acted on",
   "keyword_checks" in src)
# FOUND ON THE FIRST REAL RUN (2026-09-22). The check ran correctly and kept the right keyword,
# but research.json rebuilds its `keywords` block from named fields, so the verdicts never reached
# the file and nobody could read back WHY a keyword was kept or swapped. Acting on a judgment and
# recording it are two different things, and only one of them was done.
ok("and it survives into research.json, which rebuilds that block from named fields",
   '"keyword_checks": final.get("keyword_checks")' in src,
   "the verdicts are computed and then dropped when the research file is assembled")
ok("a swap is said out loud, naming the keyword that was dropped",
   "Changed the keyword" in src)
ok("and when nothing passes it carries on rather than halting, saying why",
   "anyway" in src and "may not" in src)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all keyword same-article checks passed")
