"""tests/test_assets_competitors.py: method 1 of the asset engine, with the model, DataForSEO and
the page fetcher all stubbed.

What this proves: the gate fires before a penny is spent and writes nothing; the balance guard
refuses a run that cannot pay, and refuses it BEFORE the first paid call rather than after; the
filter keeps what the original's scars say to keep and drops what they say to drop; a page that
would not load is marked FETCH FAILED and never faked from its title; the two shared tests decide
the verdicts and the protect rule stops a measurement being overruled by a score; and the ideas come
out in this method's own id band with real linking-domain counts on their proof.

What it does not prove is whether the model's judgments are any good. Only a real run does that, and
a real run of step B needs a DataForSEO balance this account does not have.
"""
import os
import re
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store                                  # noqa: E402
from seo_agent.assets import _common as cm                        # noqa: E402
from seo_agent.assets import competitors as C                     # noqa: E402
from seo_agent.tools import dfs                                   # noqa: E402
from seo_agent.research import web                                # noqa: E402

FAILS = []
CALLS = {"json": 0, "text": 0}
UNFILLED = []               # any prompt that still carries a {{TOKEN}} when it reaches the model
DFS_CALLS = []              # every (endpoint, payload) the fake answered
FETCHED = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" | " + str(extra)) if extra and not cond else ""))
    return cond


def say(label, note=""):
    pass


# ---- the model, stubbed on the literal output keys each prompt asks for -------------------------

def _ids(prompt, marker):
    return re.findall(r"^### %s(\S+)" % marker, prompt, re.M)


def _json(prompt, system=None, retries=1, **kw):
    CALLS["json"] += 1
    if "{{" in prompt:
        UNFILLED.append(prompt[:90])
    p = prompt

    if '"excluded_notable"' in p:                       # competitors-shortlist
        return {"competitors": [
            {"domain": "rival-one.com", "group": "DIRECT", "why": "same product, same buyer"},
            {"domain": "rival-two.com", "group": "ADJACENT", "why": "owns the audience"},
            {"domain": "example.com", "group": "DIRECT", "why": "this is us and must be dropped"}],
            "excluded_notable": ["hbr.org: general business media"], "note": ""}

    if '"tags"' in p:                                   # competitors-tag-format
        out = []
        for rid in _ids(p, ""):
            url = re.search(r"^### %s\nurl: (\S+)" % re.escape(rid), p, re.M)
            u = url.group(1) if url else ""
            fmt = ("Glossary or dictionary" if "/glossary" in u else
                   "Quiz or free test" if "/tests" in u else "How-to guide")
            out.append({"id": rid, "format": fmt, "confidence": "high",
                        "why": "the headings say so", "new_format": False})
        return {"tags": out}

    if '"row_id"' in p:                                 # competitors-reason
        rows = []
        for rid in _ids(p, "row "):
            url = re.search(r"^### row %s\ncompetitor: \S+\nformat: (.+)\nurl: (\S+)" % rid, p, re.M)
            fmt = url.group(1) if url else "How-to guide"
            u = url.group(2) if url else "u%s" % rid
            slug = u.rstrip("/").split("/")[-1]
            rows.append({"row_id": int(rid), "brand_fit": "CORE",
                         "angle_gap": "420 words on %s, no worked example, cites a 2022 figure" % slug,
                         "format": fmt,
                         "asset": "What %s Really Costs, With Worked Examples" % slug.replace("-", " ").title(),
                         "distinct_angle": "adds the worked example and the current public figure "
                                           "this page lacks",
                         "tool_escalation": "", "notes": ""})
        return {"rows": rows}

    if '"beatability"' in p:                            # competitors-score
        return {"ideas": [{"id": i, "beatability": 3, "effort": "S", "why": "thin backing pages"}
                          for i in _ids(p, "")]}

    if "OWN an asset idea" in p:                        # _common ownability
        return [{"id": i, "verdict": True, "brand_fit": "CORE", "transplant_from": "",
                 "why": "it rests on what they already sell"} for i in _ids(p, "")]

    if "CITE an asset" in p:                            # _common linkability
        return [{"id": i, "score": 4, "why": "a citable number and a proven shape"}
                for i in _ids(p, "")]

    return _fixture.stub_json(prompt, system, retries)


def _text(prompt, system=None, **kw):
    CALLS["text"] += 1
    if "{{" in prompt:
        UNFILLED.append(prompt[:90])
    return _fixture.stub_text(prompt, system)


llm.json_call = _json
llm.text = _text


# ---- DataForSEO, stubbed at the wire ------------------------------------------------------------

def _page(url, follow, nofollow=0, status=200, title="", h2=None, backlinks=None):
    return {"page": url, "status_code": status,
            "page_summary": {"referring_domains": follow + nofollow,
                             "referring_domains_nofollow": nofollow,
                             "backlinks": backlinks if backlinks is not None else follow * 3,
                             "first_seen": "2022-04-01 00:00:00 +00:00"},
            "meta": {"title": title or url.rstrip("/").split("/")[-1], "words_count": 900,
                     "images_count": 3, "external_links_count": 8,
                     "h1": ["The heading"], "h2": h2 or ["What it is", "How it works"]}}


PAGES = {
    "rival-one.com": [
        _page("https://rival-one.com/glossary/retention-bonus", 300),
        _page("https://rival-one.com/glossary/retention-bonus?utm_source=elsewhere", 12),
        _page("https://rival-one.com/blog/migrated-guide", 140, status=301),
        _page("https://rival-one.com/tests/python-skills", 90, status=0),
        _page("https://rival-one.com/", 4000),                       # homepage
        _page("https://rival-one.com/pricing", 500),                 # commercial
        _page("https://rival-one.com/fr/glossary/retention-bonus", 60),   # locale copy
        _page("https://rival-one.com/blog/gone", 200, status=404),   # dead
        _page("https://help.rival-one.com/article/setup", 150),      # not a content subdomain
        _page("https://rival-one.com/jobs/8812", 120),               # job posting
        _page("https://rival-one.com/blog/no-links", 0, nofollow=40),  # nothing passes authority
    ],
    "rival-two.com": [
        _page("https://rival-two.com/glossary/onboarding", 220),
        _page("https://rival-two.com/blog/will-not-load", 80),
    ],
}


def stub_dfs(balance=12.5):
    DFS_CALLS.clear()
    dfs._auth = lambda: ("fixture-login", "fixture-password")
    dfs.balance = lambda: balance

    def post(path, payload):
        task = (payload or [{}])[0]
        DFS_CALLS.append((path, task))
        if path.endswith("/competitors_domain/live"):
            items = [{"domain": d, "metrics": {"organic": {"count": 400 - i * 30, "etv": 900}}}
                     for i, d in enumerate(["rival-one.com", "rival-two.com", "scribd.com"])]
        elif path.endswith("/backlinks/domain_pages/live"):
            items = PAGES.get(task.get("target"), [])
        else:
            raise RuntimeError("the fixture has no answer for " + path)
        return {"status_code": 20000, "tasks": [{"status_code": 20000, "result": [{"items": items}]}]}
    dfs.post = post


def stub_web():
    def fetch(url, tries=3):
        FETCHED.append(url)
        if "will-not-load" in url:
            raise RuntimeError("HTTP 403")
        body = ("This page explains the subject at length. " * 40)
        return {"url": url, "title": url.rstrip("/").split("/")[-1], "headings": ["What it is", "How it works"],
                "text": body, "word_count": len(body.split())}
    web.fetch = fetch


stub_web()

CO = {"brand": "Example", "domain": "example.com", "brand_oneliner": "Example, for operators",
      "niche_definition": "executive education", "location_name": "United States",
      "language_code": "en"}

cm.save("scope.md", "# What Example is\nWe sell practitioner-led programmes to operators.\n"
                    "We are NOT a job board and NOT a payroll tool.\n")


def reset(keep_gate=False):
    """Clear this builder's files between scenarios. The gate answer is kept when asked, because
    several scenarios start from an approved list."""
    import shutil
    d = os.path.join(store.knowledge_dir(), "assets")
    gate = cm.read(cm.gate_path("competitors")) if keep_gate else None
    for name in ("competitors.json",):
        if cm.exists(name):
            os.remove(cm.path(name))
    work = os.path.join(d, "_work", "competitors")
    if os.path.isdir(work):
        shutil.rmtree(work)
    if keep_gate and gate is not None:
        cm.save_gate("competitors", gate)


# ================================================================================================
print("\nthe balance guard (the paid step's pre-flight)")

ok("MIN_DFS_BALANCE is a real constant in this module, not a name that does not exist",
   isinstance(C.MIN_DFS_BALANCE, float) and C.MIN_DFS_BALANCE > 0)

stub_dfs(balance=-0.07)
usable, why = C.paid_route()
ok("a balance below the floor refuses, and says the real number",
   usable is False and "-0.07" in why, (usable, why))

stub_dfs(balance=12.5)
usable, why = C.paid_route()
ok("a healthy balance goes ahead", usable is True and "12.50" in why, (usable, why))

dfs.balance = lambda: None
usable, why = C.paid_route()
ok("an unknown balance fails OPEN, because the paid call reports its own failure loudly",
   usable is True and "unknown" in why, (usable, why))

_real_auth = dfs._auth
dfs._auth = lambda: None
usable, why = C.paid_route()
ok("no credentials refuses and names what is missing",
   usable is False and "not connected" in why, (usable, why))
dfs._auth = _real_auth


# ================================================================================================
print("\nthe filter (step C), and the scars that shaped it")

keep = lambda url, **kw: C.drop_reason(dict({"url": url, "status_code": 200,
                                             "domains_follow": 50}, **kw))
ok("the homepage goes", keep("https://a.com/") == "homepage or root variant")
ok("a 404 goes", keep("https://a.com/blog/x", status_code=404) == "dead page")
ok("a 301 on a real content path STAYS (the redirect trap: an early filter dropped every non-200 "
   "and destroyed two competitors' editorial)", keep("https://a.com/blog/x", status_code=301) is None)
ok("a blank status on a JavaScript-rendered test page STAYS",
   keep("https://a.com/tests/python", status_code=0) is None)
ok("a locale copy goes", keep("https://a.com/fr/blog/x") == "translated copy of an English page")
ok("a pricing page goes", "commercial" in (keep("https://a.com/pricing") or ""))
ok("a help subdomain goes", "subdomain" in (keep("https://help.a.com/x") or ""))
ok("a job posting goes", keep("https://a.com/jobs/8812") == "job posting")
ok("a page with nothing passing authority goes",
   keep("https://a.com/blog/x", domains_follow=0) == "no links that pass authority")
ok("a FREE TEST page stays, even though it is technically a product page",
   keep("https://a.com/tests/python-skills") is None)
ok("the brand-in-domain trap: /login on testgorilla.com is dropped on its PATH, and the domain "
   "carrying the word test does not save it",
   "commercial" in (keep("https://testgorilla.com/login") or ""))
ok("and a real test page on that same domain still stays",
   keep("https://testgorilla.com/tests/python") is None)

ok("tracking parameters are not part of a page's identity",
   C._canon("https://a.com/x?utm_source=y") == C._canon("https://www.a.com/x/"))
ok("a real query parameter still is",
   C._canon("https://a.com/x?p=12") != C._canon("https://a.com/x?p=13"))


# ================================================================================================
print("\nthe gate (step A4)")

reset()
stub_dfs(balance=12.5)
out = C.run(CO, say)
g = out.get("gate") or {}
ok("with nobody asked yet it returns a gate, not a result", bool(g), out.keys())
ok("the gate names its kind and its builder, so loop.py files the answer against the right one",
   g.get("kind") == "competitors" and g.get("builder") == "competitors", g)
ok("it proposes domains, each marked direct or adjacent, each with a reason",
   g.get("proposed") and all(p.get("domain") and p.get("kind") in ("direct", "adjacent")
                             for p in g["proposed"]), g.get("proposed"))
ok("it drops the company itself from its own shortlist",
   "example.com" not in [p["domain"] for p in g["proposed"]], g.get("proposed"))
ok("it asks a question a person can answer and says why it matters",
   len(g.get("question", "")) > 20 and len(g.get("why", "")) > 20)
ok("and it wrote NOTHING further: no pool file", not cm.exists("competitors.json"))
ok("and it spent nothing: no paid page pull went out",
   not any("domain_pages" in p for p, _t in DFS_CALLS), DFS_CALLS)
ok("None means nobody was asked, which is not the same as an empty answer",
   C.approved() is None)

cm.save_gate("competitors", [])
try:
    C.run(CO, say)
    ok("an empty approval is an answer and is not re-asked as a gate", False)
except C.Blocked as e:
    ok("an empty approval is an answer and is not re-asked as a gate", "kept nobody" in str(e))
ok("[] reads back as an empty list, never as None", C.approved() == [])


# ================================================================================================
print("\nblocked on money (step B), after the gate is approved")

reset(keep_gate=False)
cm.save_gate("competitors", [{"domain": "rival-one.com", "kind": "direct", "why": "same product"},
                             {"domain": "rival-two.com", "kind": "adjacent", "why": "owns the audience"}])
stub_dfs(balance=-0.07)
try:
    C.run(CO, say)
    ok("with no balance the run refuses instead of half-finishing", False)
except C.Blocked as e:
    msg = str(e)
    ok("with no balance the run refuses instead of half-finishing", True)
    ok("the refusal is plain English and names the real balance and what to do",
       "-0.07" in msg and "Top the account up" in msg and "Connections" in msg, msg)
    ok("it says the approved list is saved and the run picks up where it stopped",
       "picks up" in msg, msg)
    ok("it says the other methods still run, so the engine is not presented as dead",
       "other two methods" in msg, msg)
ok("NOTHING was spent: not one page pull went out",
   not any("domain_pages" in p for p, _t in DFS_CALLS), DFS_CALLS)
ok("the approved list still reached knowledge/competitors.json, so the free work was not lost",
   {r["domain"] for r in (store.knowledge("competitors.json") or {}).get("competitors", [])}
   >= {"rival-one.com", "rival-two.com"})
ok("and no pool file was written, so a re-run after a top-up does the work",
   not cm.exists("competitors.json"))


# ================================================================================================
print("\nthe whole method, with a balance")

reset(keep_gate=True)
stub_dfs(balance=12.5)
FETCHED.clear()
out = C.run(CO, say)
rows = cm.read("competitors.json") or []

ok("it writes assets/competitors.json", cm.exists("competitors.json") and bool(rows))
ok("it returns the file and its review notes", out.get("files") == ["competitors.json"]
   and isinstance(out.get("needs_review"), list), out)
ok("every row is signed with this method, so the driver can tell it contributed",
   all(r["method"] == ["competitors"] for r in rows), [r["method"] for r in rows][:3])
ok("ids sit in this method's own band (a1001 up), so the merge never sees two methods'"
   " ideas wearing one id",
   rows[0]["id"] == "a1001" and all(r["id"] >= "a1001" for r in rows), [r["id"] for r in rows])
ok("every row carries every field of the shared schema",
   all(set(r) == set(cm.blank_idea("a1001", "competitors")) for r in rows))

by_url = {p["url"]: p for r in rows for p in r["proof"]}
ok("the proof carries the REAL follow-domain counts from the pull, not a guess",
   by_url.get("https://rival-one.com/glossary/retention-bonus", {}).get("domains") == 300,
   by_url.get("https://rival-one.com/glossary/retention-bonus"))
ok("follow domains, not the raw total: a page with 40 nofollow domains and none that follow is"
   " nowhere in the proof",
   "https://rival-one.com/blog/no-links" not in by_url)
ok("the raw total is kept beside it, so nothing is hidden",
   all("domains_total" in p for p in by_url.values()))
ok("every proof line names the competitor it came from",
   all(p.get("competitor") for p in by_url.values()))

ok("the format is the step D tag, copied, never upgraded to a tool",
   {r["format"] for r in rows} <= {"Glossary or dictionary", "Quiz or free test", "How-to guide"},
   {r["format"] for r in rows})
ok("no asset title carries a shape word, because the shape lives in the format field",
   not any(w in r["title"].lower() for r in rows
           for w in ("calculator", "quiz", "generator", "dashboard")), [r["title"] for r in rows])
ok("brand fit and the ownability verdict come from the shared test",
   all(r["brand_fit"] == "CORE" and r["ownability"]["verdict"] is True for r in rows))
ok("linkability is scored out of four and its verdict is derived in code at the shared floor",
   all(r["linkability"]["of"] == cm.LINKABILITY_OF and r["linkability"]["verdict"] is True
       for r in rows))
ok("beatability and effort are filled", all(r["beatability"] == 3 and r["effort"] == "S" for r in rows))
ok("tool_escalation is a real field and is False for an ordinary article",
   all(r["tool_escalation"] is False and r["what_it_would_be"] == "" for r in rows))

# the filter, end to end, through the real files
master = cm.read("_work/competitors/master.json") or []
report = cm.read("_work/competitors/filter-report.json") or []
one = next((r for r in report if r["competitor"] == "rival-one.com"), {})
ok("the filter kept the three replicable pages of eleven and recorded every drop with a reason",
   one.get("kept") == 3 and one.get("dropped") == 8 and one.get("reasons"), one)
kept_urls = {r["url"] for r in master if r["competitor"] == "rival-one.com"}
ok("and the three it kept are the glossary, the 301-migrated article and the free test",
   kept_urls == {"https://rival-one.com/glossary/retention-bonus",
                 "https://rival-one.com/blog/migrated-guide",
                 "https://rival-one.com/tests/python-skills"}, kept_urls)
ok("the same page under a tracking parameter was counted once, not twice",
   one["reasons"].get("the same page at several addresses") == 1, one.get("reasons"))
ok("a competitor collapsing below the alarm is flagged, not swallowed", one.get("alarm") is True)
ok("and the run says so in plain English",
   any("filter kept fewer" in n for n in out["needs_review"]), out["needs_review"])

# step E, the one that gets skipped
tally = cm.read("_work/competitors/read-tally.json") or {}
ok("every kept page was fetched, not a top slice", len(FETCHED) == len(master))
ok("the read tally adds up: rows = read + failed",
   tally["rows"] == tally["read"] + tally["failed"] and tally["rows"] == len(master), tally)
failed_row = next((r for r in master if "will-not-load" in r["url"]), {})
ok("a page that would not load is marked FETCH FAILED", failed_row.get("read_status") == "FETCH FAILED")
ok("and its body is EMPTY: the title is never used as the page (title-as-content is banned)",
   failed_row.get("body") == "" and failed_row.get("title") not in ("", None))
ok("the run says how many would not load", any("FETCH FAILED" in n for n in out["needs_review"]),
   out["needs_review"])

# step F, the answer this method exists for
summary = cm.read("_work/competitors/format-summary.json") or []
ok("the format summary is written and ranked on average follow domains per page",
   summary and summary == sorted(summary, key=lambda r: -r["avg_follow_domains"]), summary)
ok("it counts pages, competitors and the median length of the pages behind each shape",
   all({"pages", "competitors", "median_words", "proven"} <= set(r) for r in summary))
gl = next((r for r in summary if r["format"] == "Glossary or dictionary"), {})
ok("a shape two competitors share is counted across both", gl.get("competitors") == 2, gl)

ok("knowledge/competitors.json holds the approved list, which is where the rest of the app reads it",
   {r["domain"] for r in (store.knowledge("competitors.json") or {}).get("competitors", [])}
   >= {"rival-one.com", "rival-two.com"})

n = CALLS["json"] + CALLS["text"]
out2 = C.run(CO, say)
ok("a second run reuses the finished file and calls no model",
   CALLS["json"] + CALLS["text"] == n and out2["files"] == ["competitors.json"])


# ================================================================================================
print("\nthe traps step G is designed against")

notes = []
same = "generic explainer, no original data, no inline test"
trap_rows = [{"title": "How-to guide on hiring", "format": "How-to guide",
              "gaps": [{"url": "https://a.com/%d" % i, "gap": same}]} for i in range(14)]
rep = C._traps(trap_rows, notes)
ok("one reason repeated across fourteen ideas is caught in code, not left to the prompt",
   rep["repeated_gaps"] and rep["repeated_gaps"][0]["count"] == 14, rep)
ok("too few distinct reasons for the number of pages is caught too", rep["thin"] is True, rep)
ok("a title that is just <format> on <topic> is caught", rep["glued_titles"], rep)
ok("and all three are said in plain English, so a person can act on them",
   len(notes) == 3 and all("competitors.json:" in n for n in notes), notes)

notes = []
varied = [{"title": "What Onboarding Really Costs", "format": "How-to guide",
           "gaps": [{"url": "https://a.com/%d" % i, "gap": "gap number %d, specific to it" % i}]}
          for i in range(14)]
ok("real, varied reading raises nothing", not C._traps(varied, notes)["repeated_gaps"] and not notes)


# ================================================================================================
print("\nthe cut, and the protect rule")

low = {"title": "weak", "linkability": {"judged": True, "verdict": False, "score": 1},
       "pooled_follow_domains": 4}
proven = {"title": "proven", "linkability": {"judged": True, "verdict": False, "score": 2},
          "pooled_follow_domains": C.PROTECT_DOMAINS + 1}
unjudged = {"title": "forgotten", "linkability": {"judged": False, "verdict": None, "score": None},
            "pooled_follow_domains": 3}
kept = C._cut([low, proven, unjudged], say)
titles = [r["title"] for r in kept]
ok("an idea nobody would cite is dropped", "weak" not in titles, titles)
ok("an idea whose backing pages really pulled %d linking domains is NEVER dropped by a score"
   % C.PROTECT_DOMAINS, "proven" in titles, titles)
ok("an idea the judge forgot is unjudged, which is not a zero and not a drop",
   "forgotten" in titles, titles)
dropped = cm.read("_work/competitors/dropped.json") or []
ok("every cut is written to an audit file, so no drop is silent",
   len(dropped) == 1 and dropped[0]["title"] == "weak", dropped)


# ================================================================================================
print("\nprompts")
ok("every {{TOKEN}} in every prompt this builder sends was filled before the model saw it",
   not UNFILLED, UNFILLED[:3])
for name in ("competitors-shortlist", "competitors-tag-format", "competitors-reason",
             "competitors-score"):
    ok("prompts/assets/%s.md exists" % name,
       os.path.exists(os.path.join(cm.PROMPTS, name + ".md")))

print("\nStubbed the model, DataForSEO and the page fetcher. Proves the plumbing, the balance "
      "guard, the filter rules and the gate, not the quality of any judgment.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all competitor-study checks passed")
