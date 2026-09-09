"""tests/test_stations.py — the three stations that used to declare themselves skipped.

  ENRICH          turns a needs_research marker into a real query, a real page read and a new card
                  numbered from 9001, and says so honestly when the search finds nothing.
  THE SOURCE HUNT a claim whose page does not support it goes and finds one that does; a claim whose
                  page DOES support it is left alone and never re-hunted.
  FIELD           real forum posts become prose; no posts means no file at all, never an invented one.

NOTHING HERE TOUCHES THE NETWORK. The model is a local dispatcher, DataForSEO's `post` raises if it is
ever reached, the write phase's fetch door (_common.FETCH_ONCE) answers from a dict, and the Reddit
module is a fake object. Two suites in this codebase once quietly hit real hosts for fake hostnames
and nobody noticed for weeks, so this suite also asserts, at the end, that no real request was made.
"""
import copy
import json
import re

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import llm, store
from seo_agent.research import evidence, web
from seo_agent.tools import dfs
from seo_agent.write import _common as C, enrich, field, verify_sources

FAILS, PASSES = [], []


def ok(label, cond, extra=""):
    (PASSES if cond else FAILS).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))
    return cond


# ---- every door to the outside, nailed shut ---------------------------------------------------------
NET = []            # anything that would have left this machine


def _no_network(*a, **kw):
    NET.append((a, kw))
    raise AssertionError("a station tried to reach the real network")


dfs.post = _no_network
dfs.available = lambda: False
web.fetch = _no_network
C.ALIVE = lambda url: True
C.FETCH_GAP = 0.0

PAGES = {}          # url -> page text the stations will "read"
C.FETCH_ONCE = lambda url, timeout=15.0: PAGES.get(url, "__ERR__ConnectError")

# ---- the model, one dispatcher ----------------------------------------------------------------------
REPLIES = []        # (predicate(prompt) -> bool, reply | callable(prompt))
SEEN = []           # every prompt the stations sent, for the assertions about what they asked


ALL_PROMPTS = []    # every prompt this suite ever sent; SEEN is cleared in places, this is not


def json_stub(prompt, system=None, retries=1, **kw):
    SEEN.append(prompt)
    ALL_PROMPTS.append(prompt)
    for pred, reply in REPLIES:
        if pred(prompt):
            return reply(prompt) if callable(reply) else copy.deepcopy(reply)
    return {}


def text_stub(prompt, system=None, **kw):
    SEEN.append(prompt)
    ALL_PROMPTS.append(prompt)
    for pred, reply in REPLIES:
        if pred(prompt):
            return reply(prompt) if callable(reply) else reply
    return ""


llm.json_call = json_stub
llm.text = text_stub

SAY = []


def say(label, note=""):
    SAY.append((label, note))


def said(fragment):
    return [s for s in SAY if fragment.lower() in (s[0] + " " + s[1]).lower()]


# ======================================================================================
print("\nenrich: a marker becomes a query, a page read, and a real card")

MARKER = "SHRM 2023 sample size and methodology"
ENRICH_PAGE = ("Cost per hire benchmarking. The SHRM 2023 benchmarking survey drew on 3,844 employers "
               "across 19 industries. Its median cost per hire was $4,700.\n\n"
               "The survey was fielded between January and March and weighted by headcount.\n\n"
               + "Methodology notes follow, in the plain wording the report itself uses. " * 20)
PAGES["https://source.example.org/shrm-methodology"] = ENRICH_PAGE

STRUCT = {"sections": [
    {"headline": "The Real Cost Of Filling A Seat", "job": "Price a hire honestly.",
     "lead": {"card_ids": [1], "is_lead": True},
     "h3s": [{"h3": "The invoiced half", "card_ids": [2]}],
     "needs_research": [{"topic": MARKER, "goes_to": "opening"}]},
    {"headline": "How Long The Seat Stays Empty", "job": "Show what the empty weeks cost.",
     "lead": {"card_ids": [3], "is_lead": True}, "h3s": [], "needs_research": []},
]}
CTX = {"title": "What cost per hire really includes", "angle": "Lead with what the number leaves out.",
       "about": "hiring cost for employers", "not_about": "student contests", "persona": "Head of Talent"}

REPLIES[:] = [
    (lambda p: '"queries": ["<query>"' in p and "H3 that needs research" in p,
     {"queries": ["shrm 2023 cost per hire survey methodology", "shrm benchmarking sample size 2023"]}),
    (lambda p: '"urls": ["https://' in p, {"urls": ["https://source.example.org/shrm-methodology",
                                                    "https://dead.example.org/nothing"]}),
    (lambda p: "breaking ONE web page into small" in p,
     [{"gloss": "The SHRM 2023 survey drew on 3,844 employers",
       "verbatim": "The SHRM 2023 benchmarking survey drew on 3,844 employers across 19 industries."},
      {"gloss": "A fact that is not on the page", "verbatim": "This sentence was never on the page."}]),
]
SAY.clear()
out = enrich.run(copy.deepcopy(STRUCT), say, CTX)
st, new = out["structure"], out["enriched_cards"]

planned = [p for p in SEEN if "H3 that needs research" in p]
ok("the marker was turned into a real search query, with the section's JOB in the prompt",
   len(planned) == 1 and MARKER in planned[0] and "Price a hire honestly" in planned[0])
ok("the queries it planned were searched", any("shrm 2023 cost per hire survey methodology" in p for p in SEEN))
ok("a new card exists and is numbered from 9001", list(new) == [9001], list(new))
ok("the new card carries the page's own words and that page as its source",
   new[9001]["verbatim"].startswith("The SHRM 2023 benchmarking survey drew on 3,844")
   and new[9001]["source_urls"] == ["https://source.example.org/shrm-methodology"], new.get(9001))
ok("a quote that is not on the page is thrown away, never kept",
   not any("never on the page" in c.get("verbatim", "") for c in new.values()))
ok("the card was placed where the architect said (the opening)", 9001 in st["sections"][0]["lead"]["card_ids"])
ok("the enrichment report counts what really happened",
   st["enrichment"]["markers"] == 1 and st["enrichment"]["resolved"] == 1
   and st["enrichment"]["new_cards"] == 1 and st["enrichment"]["failed"] == 0, st["enrichment"])
ok("no research failure is recorded for a marker that worked", not st.get("research_failures"))
ok("it logged live, one line per thing", bool(said("Searching for")) and bool(said("Read 1 page"))
   and bool(said("Found 1 new fact")), [s[0] for s in SAY])

print("\nenrich: a marker that finds nothing SAYS SO and invents nothing")
REPLIES[:] = [
    (lambda p: '"queries": ["<query>"' in p and "H3 that needs research" in p,
     {"queries": ["a query that finds nothing"]}),
    (lambda p: '"urls": ["https://' in p, {"urls": ["https://dead.example.org/nothing"]}),
]
SAY.clear()
out2 = enrich.run(copy.deepcopy(STRUCT), say, CTX)
st2 = out2["structure"]
ok("no card is invented when no page would open", out2["enriched_cards"] == {}, out2["enriched_cards"])
ok("the failure is recorded against the section, with the queries it tried",
   st2["research_failures"] and st2["research_failures"][0]["status"] == "no pages loaded"
   and st2["research_failures"][0]["queries"] == ["a query that finds nothing"], st2.get("research_failures"))
ok("the report says one marker came back empty",
   st2["enrichment"]["failed"] == 1 and st2["enrichment"]["resolved"] == 0, st2["enrichment"])
ok("it said so out loud", bool(said("No page would open")), [s[0] for s in SAY])

print("\nenrich: with nothing asked for, nothing is searched")
NOASK = {"sections": [{"headline": "A", "job": "j", "lead": {"card_ids": [1]}, "h3s": [], "needs_research": []}]}
SEEN_BEFORE = len(SEEN)
out3 = enrich.run(copy.deepcopy(NOASK), say, CTX)
ok("no model call and no search when there is no marker", len(SEEN) == SEEN_BEFORE)
ok("and the note says exactly that", "no extra research" in out3["structure"]["enrichment"]["note"])

print("\nenrich: the route is named, and a demo SERP is never researched from")
dfs.available = lambda: True
dfs.balance = lambda: 0.10
r_name, r_note = enrich.route()
ok("a balance under the floor falls back to the model route and says why",
   r_name == "model" and "DataForSEO" in r_note and "skipped" in r_note, r_note)
dfs.balance = lambda: 25.0
ok("a funded account uses the live search", enrich.route()[0] == "dataforseo")
evidence.plan_pages = lambda *a, **kw: ([("https://demo.example/x", "q")], 0.0, True)
ok("a DEMO search result is thrown away, because researching from made-up urls is fabrication",
   enrich.search(["anything"], "dataforseo") == ([], 0.0))
dfs.available = lambda: False

# ======================================================================================
print("\nverify_sources: a dead source is replaced, a good one is left alone")

CARDS = [
    {"id": 1, "gloss": "Average cost per hire is 4,700 dollars",
     "verbatim": "The average cost per hire was $4,700 in 2023, per the SHRM benchmarking survey.",
     "source_urls": ["https://good.example.org/cost-per-hire"], "tag": "evidence"},
    {"id": 2, "gloss": "Time to fill averages 42 days",
     "verbatim": "The average time to fill a position is 42 days.",
     "source_urls": ["https://wrong.example.org/culture"], "tag": "evidence"},
]
PLAN = {"h1": "x", "sections": [{"h2": "Costs", "h3s": [
    {"h3": "The benchmark", "card_ids": [1, 2]}]}]}
PAGES.update({
    "https://good.example.org/cost-per-hire":
        "The average cost per hire was $4,700 in 2023, per the SHRM benchmarking survey. " * 20,
    "https://wrong.example.org/culture": "This page is about culture and says nothing about days. " * 40,
    "https://replacement.example.net/time-to-fill":
        "The average time to fill a position is 42 days across the sample. " * 20,
})

JUDGED = []


def _judge_reply(p):
    """The source judge: a page supports the claim only when the claim's number is really on it."""
    url = (re.search(r"^URL: ?(\S+)", p, re.M) or re.search(r"(https?://\S+)", p))
    JUDGED.append(url.group(1) if url else "?")
    supports = "42 days" in p.split("THE PAGE")[-1] if "42 days" in p.split("THE PAGE")[0] else True
    return {"supports": bool(supports), "quote": "", "note": ""}


REPLIES[:] = [
    (lambda p: '{"verify": [' in p, {"verify": [1, 2]}),
    (lambda p: '"supports"' in p, _judge_reply),
    (lambda p: '"queries": ["<query>"' in p and "published source for ONE factual claim" in p,
     {"queries": ["average time to fill 42 days"]}),
    (lambda p: '"urls": ["https://' in p, {"urls": ["https://replacement.example.net/time-to-fill"]}),
]
SAY.clear()
idx = C.card_index(CARDS)
ver = verify_sources.run(copy.deepcopy(PLAN), idx, say)
pol = ver["police"]
ok("the good source is confirmed and left exactly as it was",
   1 in pol["kept_ok"] and idx[1]["source_urls"] == ["https://good.example.org/cost-per-hire"], pol["kept_ok"])
ok("the claim whose page did not support it got a NEW source",
   [r["card_id"] for r in pol["replaced"]] == [2]
   and idx[2]["source_urls"] == ["https://replacement.example.net/time-to-fill"], pol["replaced"])
ok("the replaced card is not marked as needing a source, and is not cut",
   not idx[2].get("needs_source") and not pol["cut"] and not pol["needs_source"], (pol["cut"], pol["needs_source"]))
ok("the search was planned from the claim itself, gloss and verbatim both",
   any("published source for ONE factual claim" in p and "42 days" in p and "Time to fill" in p for p in SEEN))
ok("the hunt report says how many were replaced, and names its route",
   "1 of 1" in pol["hunt"] and "DataForSEO" in pol["hunt"], pol["hunt"])
ok("the good source was never re-hunted", JUDGED.count("https://good.example.org/cost-per-hire") == 1)
ok("it logged live", bool(said("Hunting a replacement")) and bool(said("New source found")), [s[0] for s in SAY])

print("\nverify_sources: when the hunt finds nothing, the old honest behaviour holds")
REPLIES[:] = [
    (lambda p: '{"verify": [' in p, {"verify": [1, 2]}),
    (lambda p: '"supports"' in p, _judge_reply),
    (lambda p: '"queries": ["<query>"' in p and "published source for ONE factual claim" in p,
     {"queries": ["nothing will be found"]}),
    (lambda p: '"urls": ["https://' in p, {"urls": []}),
]
idx_b = C.card_index(CARDS)
ver_b = verify_sources.run(copy.deepcopy(PLAN), idx_b, say)
ok("a numeric claim with no page behind it and no replacement is cut",
   [x["card_id"] for x in ver_b["police"]["cut"]] == [2], ver_b["police"]["cut"])
ok("the cut says the hunt ran and found nothing", "hunt" in ver_b["police"]["cut"][0]["why"])
ok("the good card still survives", 1 in ver_b["police"]["kept_ok"])

# ======================================================================================
print("\nfield: real posts become prose")

# The post and comment shapes are research/reddit.py's own, and so is the three-state answer:
# "ok" (it answered and there is something), "empty" (it answered and there is nothing), "unknown"
# (we could not look). Nothing here invents a field that module does not return.
POSTS = [
    {"id": "a1", "title": "Approval delays cost us the candidate again", "permalink": "/r/recruiting/a1",
     "url": "https://www.reddit.com/r/recruiting/a1", "subreddit": "recruiting", "author": "x",
     "score": 210, "num_comments": 84, "created_utc": 0.0, "text": "Third time this quarter."},
    {"id": "b2", "title": "Why does everyone quote cost per hire", "permalink": "/r/recruiting/b2",
     "url": "https://www.reddit.com/r/recruiting/b2", "subreddit": "recruiting", "author": "y",
     "score": 90, "num_comments": 41, "created_utc": 0.0, "text": ""},
]
COMMENTS = [
    {"id": "c1", "author": "p", "score": 120, "permalink": "",
     "text": "The number nobody counts is the four weeks the seat sits empty while finance signs off."},
    {"id": "c2", "author": "q", "score": 88, "permalink": "",
     "text": "Agreed, our real cost is double the invoiced one once you count the manager's time."},
    {"id": "c3", "author": "r", "score": 3, "permalink": "", "text": "ok"},
]


class FakeReddit:
    """Stands in for research/reddit.py. Same signatures, same three-state answers."""
    calls = []

    @staticmethod
    def search(subreddit, query, limit=25, **kw):
        FakeReddit.calls.append(("search", query, subreddit))
        return {"state": "ok", "posts": list(POSTS), "reason": "", "url": "x"}

    @staticmethod
    def top(subreddit, limit=25, **kw):
        return {"state": "ok", "posts": list(POSTS), "reason": "", "url": "x"}

    @staticmethod
    def comments(post_id, limit=None, **kw):
        FakeReddit.calls.append(("comments", post_id, None))
        return {"state": "ok", "comments": list(COMMENTS), "reason": "", "url": "x"}


store.save_knowledge("brand/field-sources.md",
                     "# Field sources\n\n## Reddit\n\n| Subreddit | Who is in there | Activity |\n"
                     "|---|---|---|\n| r/recruiting | in-house recruiters | very active |\n"
                     "| talentacquisition | TA leads | active |\n\nRejected: r/jobs, thin\n")

WRITTEN = ("# Voices from the field, cost per hire\n\n> What people say, never a fact.\n\n"
           "**Coverage.** {cov}\n\n"
           "## Approval delay is the cost nobody counts\n**What they say.** Several recruiters describe the "
           "same wait — the seat sits empty while finance signs off.\n**Strength.** Strong, two discussions.\n"
           "**Serves.** Section 1.\n**What this changes.** Price the wait.\n\n"
           "## Practitioners split on whether the number is useful at all\n**What they say.** Some track it, "
           "some call it theatre.\n**Strength.** Moderate.\n**Serves.** The angle.\n"
           "**What this changes.** Give both sides.\n\n"
           "## What did not show up\n- Nobody discussed agency fees.\n")

field.REDDIT = FakeReddit
REPLIES[:] = [
    (lambda p: '"reddit": {"queries"' in p and "search box" in p,
     {"reddit": {"queries": [{"q": "waiting on approval lost candidate",
                              "subreddits": ["r/recruiting", "r/notchecked"], "serves": "1"}]}}),
    (lambda p: '"action": "read"|"requery"|"stop"' in p,
     {"reddit": {"action": "read", "read": [0, 1], "why": "people are arguing about the wait"}}),
    (lambda p: "writing one short briefing" in p, lambda p: WRITTEN.replace(
        "{cov}", re.search(r"\*\*Coverage\.\*\* (.+)", p).group(1) if re.search(r"\*\*Coverage\.\*\* (.+)", p) else "")),
]
SAY.clear()
FakeReddit.calls.clear()
ST = {"sections": [{"headline": "The Real Cost", "job": "Price a hire honestly."},
                   {"headline": "Empty Seats", "job": "Price the wait."}], "spine": "The invoiced half is not the cost."}
fl = field.run(ST, CTX, say)

ok("only the checked subreddits are searched; an unchecked one is dropped",
   [c[2] for c in FakeReddit.calls if c[0] == "search"] == ["recruiting"], FakeReddit.calls)
ok("the shortlisted discussions were opened by POST ID, which is how Reddit serves a comment tree",
   sorted(c[1] for c in FakeReddit.calls if c[0] == "comments") == ["a1", "b2"], FakeReddit.calls)
ok("the file is real prose with the findings in it",
   "Approval delay is the cost nobody counts" in fl["markdown"] and fl["report"]["findings"] == 2, fl["report"])
ok("the coverage line is counted in CODE, never written by the model",
   "2 discussion(s) read and 4 comments" in fl["markdown"], fl["report"]["coverage"])
ok("comments under 25 characters are not read as opinion", "(3) ok" not in json.dumps(SEEN[-1]))
ok("the writer gets a FILE 2 block built from the file",
   "FILE 2: VOICES FROM THE FIELD" in fl["block"] and "Approval delay" in fl["block"])
ok("it logged live, one line per thing", bool(said("Searched")) and bool(said("Read:"))
   and bool(said("Coverage")), [s[0] for s in SAY])

print("\nfield: no posts means NO file, never an invented one")


class EmptyReddit(FakeReddit):
    @staticmethod
    def search(subreddit, query, limit=25, **kw):
        return {"state": "empty", "posts": [], "reason": "Reddit answered with no results", "url": "x"}

    @staticmethod
    def comments(post_id, limit=None, **kw):
        return {"state": "empty", "comments": [], "reason": "no readable comments", "url": "x"}


field.REDDIT = EmptyReddit
SEEN.clear()
SAY.clear()
fl2 = field.run(ST, CTX, say)
ok("nothing is written when nothing was read", fl2["markdown"] == "" and fl2["block"] == "")
ok("the writing prompt was never even sent, so there is nothing to invent",
   not any("writing one short briefing" in p for p in SEEN))
ok("the report says plainly that nothing came back", "nothing worth reading" in fl2["report"]["note"], fl2["report"])
ok("it said so out loud", bool(said("No voices from the field")))

print("\nfield: shut out is not the same finding as nothing there")


class BlockedReddit(FakeReddit):
    @staticmethod
    def search(subreddit, query, limit=25, **kw):
        return {"state": "unknown", "posts": [],
                "reason": "Reddit served a login page (HTTP 200), so this could not be checked", "url": "x"}


field.REDDIT = BlockedReddit
SAY.clear()
fl_b = field.run(ST, CTX, say)
ok("a login-walled Reddit is reported as unknown, never as an empty community",
   "unknown, not empty" in fl_b["report"]["note"] and fl_b["report"]["blocked"] > 0, fl_b["report"])
ok("and it says so as it happens", bool(said("Could not search")))

print("\nfield: one weak finding is dropped rather than handed to the writer")
ONE = ("# Voices from the field, x\n\n## Only one thing came up\n**What they say.** A bit.\n\n"
       "## What did not show up\n- everything else\n")
ok("a file with one finding produces no block", field.block(ONE) == "")
ok("a file with two findings produces one", "FILE 2" in field.block(WRITTEN.replace("{cov}", "x")))

print("\nfield: with no Reddit reader and with no checked list, it degrades honestly")
field.REDDIT = False
fl3 = field.run(ST, CTX, say)
ok("no Reddit module -> no file and a plain reason",
   fl3["markdown"] == "" and "not installed" in fl3["report"]["note"], fl3["report"]["note"])
field.REDDIT = FakeReddit
store.save_knowledge("brand/field-sources.md", "# Field sources\n\nNo table here yet.\n")
fl4 = field.run(ST, CTX, say)
ok("no checked subreddit list -> no file and a plain reason",
   fl4["markdown"] == "" and "checked subreddit list" in fl4["report"]["note"], fl4["report"]["note"])

# ======================================================================================
print("\nthe field station sits where the original puts it")
from seo_agent.tools import write_article
S = write_article.STEPS
ok("field runs after the architect's last step and before the writer's first",
   S.index("headings") < S.index("field") < S.index("write_body"), S)
ok("the writer is still the last thing to run", S[-1] == "assemble")

# ======================================================================================
print("\nevery prompt these stations send is fully filled")
UNFILLED = sorted({t for p_ in ALL_PROMPTS for t in re.findall(r"\{\{[A-Z_]+\}\}", p_)})
ok("no {{TOKEN}} reached the model unfilled", not UNFILLED, UNFILLED)

# ======================================================================================
print("\nthe suite never reached the network")
ok("no real HTTP request was attempted", NET == [], NET)

print("\n%d passed, %d failed" % (len(PASSES), len(FAILS)))
for f in FAILS:
    print("  FAILED: " + f)
raise SystemExit(1 if FAILS else 0)
