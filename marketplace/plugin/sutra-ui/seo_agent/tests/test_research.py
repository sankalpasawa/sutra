"""tests/test_research.py — the research engine (run_research + build_blueprint), with everything stubbed.

DataForSEO is faked at the wire so the real parsing runs; the web is faked per URL; Voyage is the
deterministic fixture; the model answers by output key. What this proves is the plumbing and the
guards that are code: the filter maths, "no pick without a score", the read-list parse, the
verbatim check that throws out an invented quote, the three-question cap, the own-page cards
through the index, the cannibalisation flag, PROTECT, MECE, the permutation check, the FAQ and the
keyword set. Not whether the judgments are any good: only a real run shows that.
"""
import os
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.tools import _index, _shared as sh, dfs
from seo_agent.research import (_common as _c, curate, dossier, evidence, expand, faq_order,
                                gap_check, keywords, serp, source_match, topic_gate, web)

llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text
_fixture.stub_voyage()
_fixture.stub_web()
_fixture.stub_dfs(balance=12.5)

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond

# ---- the knowledge the engine reads: a company record with a scope, a persona library, the page index ----
rec = store.knowledge("brand/company.json") or {}
rec.setdefault("brand", "Example")
rec.setdefault("domain", "example.com")
rec.setdefault("brand_oneliner", "Example — practitioner-led business programmes for founders and senior operators")
rec.setdefault("niche_definition", "executive education — programmes for operators, cohort learning, leadership practice")
rec.setdefault("about", "Practitioner-led programmes for people who already run things.")
store.save_knowledge("brand/company.json", rec)
if not sh.brand_file("persona.md"):
    store.save_knowledge("brand/persona.md",
        "# Personas\n\n| Persona | Who | Reads |\n|---|---|---|\n"
        "| **Founder / CEO** | runs a 50-500 person company | strategy pieces |\n"
        "| **Senior Operator** | COO / VP running a function | how-to and cases |\n\n"
        "## How to pick one per article\nStrategy -> Founder; role how-to -> Operator.\n")
# Other suites rewrite the site index and the catalogue in the shared data folder, so the fixture's
# pages are pinned here for this run and put back at the end.
_saved_index = store.knowledge("site_index.json")
store.save_knowledge("site_index.json", _fixture.SITE_INDEX)
_fixture.plant_content_database()
_index.build(sh.pages_with_bodies(), say=lambda *a, **k: None, reindex=True)
ok("the page index is built for the test", _index.status()["built"])

print("\nthe cannibalisation flag")
from seo_agent.research import cannibalisation
from seo_agent.research import render
hit = cannibalisation.check("Operator Education", _fixture.SITE_INDEX)
ok("a keyword we hold in the top 10 is flagged with rank and url", hit == {"keyword": "Operator Education", "rank": 4, "url": "https://example.com/"}, hit)
ok("a page-2 ranking is not a flag", cannibalisation.check("leadership programme", _fixture.SITE_INDEX) is None)
ok("an unknown keyword is not a flag", cannibalisation.check("nothing we rank for", _fixture.SITE_INDEX) is None)

chat = store.new_chat("research test")
events = []
def ctx_for(run):
    return {"chat_id": chat, "run_id": run, "step_id": "step-1", "emit": lambda **kw: events.append(kw)}

# ---- the code-level guards, checked on their own -------------------------------------------------
print("\nthe filter (step 2)")
pool = [{"kw": "a", "vol": 1900, "kd": 30}, {"kw": "b", "vol": 400, "kd": None}, {"kw": "c", "vol": 99, "kd": 5},
        {"kw": "d", "vol": 500, "kd": 41}, {"kw": "e", "vol": 100, "kd": 40}]
short = expand.filter_pool(pool)
ok("keeps volume >= 100 and KD <= 40 (unknown KD kept)", [r["kw"] for r in short] == ["a", "b", "e"], [r["kw"] for r in short])
ok("sorted by volume, most searched first", short[0]["vol"] >= short[-1]["vol"])

print("\nno pick without a score (step 3)")
rows = [{"kw": "operator education", "vol": 1900, "kd": 30, "intent": "informational"},
        {"kw": "operator education programme", "vol": 400, "kd": 20, "intent": "informational"}]
_real_json = llm.json_call
def _no_scores(prompt, system=None, retries=1):
    if '"distinctness"' in prompt:
        raise ValueError("the scorer fell over")
    return _real_json(prompt, system, retries)
llm.json_call = _no_scores
try:
    keywords.score_and_judge(rows, "Operator education", "", {}, "", sh.company())
    ok("zero scored rows is an error, never a fabricated primary", False, "no raise")
except keywords.NoScores as e:
    ok("zero scored rows is an error, never a fabricated primary", "refusing" in str(e))
llm.json_call = _real_json
try:
    keywords.score_and_judge([{"kw": "x jobs", "vol": 900, "kd": 15, "intent": "navigational"}], "X", "", {}, "", sh.company())
    ok("no informational or commercial keyword -> no keyword demand", False, "no raise")
except keywords.NoKeywordDemand:
    ok("no informational or commercial keyword -> no keyword demand", True)
judged = keywords.score_and_judge(rows, "Operator education", "", {}, "", sh.company())
pr = judged["final"]["primary"]
ok("the judge's primary carries split_world", "split_world" in pr and isinstance(pr["split_world"], bool))
ok("the primary's numbers come from the metrics table, not the model", pr["volume"] == 1900 and pr["kd"] == 30)

print("\nthe read-list parse (step 4)")
extract = {"top_organic": [{"url": "https://a.com/1"}, {"url": "https://b.com/2"}, {"url": "https://c.com/3"}, {"url": "https://d.com/4"}]}
text = "**Who ranks:**\n- x\n```readlist\nhttps://b.com/2\nhttps://d.com/4\nhttps://not-in-extract.com/9\n```"
ok("takes the fenced block, only real URLs, topped up to exactly 3",
   serp._readlist(text, extract) == ["https://b.com/2", "https://d.com/4", "https://a.com/1"], serp._readlist(text, extract))
ok("falls back to the raw top 3 without a block", serp._readlist("no block here", extract) == ["https://a.com/1", "https://b.com/2", "https://c.com/3"])
parsed = serp.parse_snapshot("**Who ranks:**\n- vendors\n- Open gap: nobody covers X\n\n**PAA — on-angle (FAQ candidates):**\n- What is it?\n\n**PAA — off-angle (excluded):**\n- none\n")
ok("the gap line is kept out of who-ranks", "Open gap" not in parsed["who_ranks_text"] and parsed["open_gap"].startswith("nobody"))
ok("on/off-angle PAA parsed as lists", parsed["paa_on"] == ["What is it?"] and parsed["paa_off"] == [])

print("\nthe topic gate fails open")
def _blank(prompt, system=None, retries=1):
    return {} if '"relevant"' in prompt else _real_json(prompt, system, retries)
llm.json_call = _blank
g = topic_gate.run("T", "old angle", {"who_ranks_text": "x", "ai_overview_text": ""}, {"gaps_to_own": [], "common_h2s": []}, sh.company())
ok("a reply with no verdict passes the topic", g["relevant"] is True and "not judged" in g["why"])
llm.json_call = _real_json

print("\nthe order is accepted only as a valid permutation")
secs = [{"h2": "A"}, {"h2": "B"}, {"h2": "C"}]
def _bad_order(prompt, system=None, retries=1):
    return {"order": [0, 0, 1]} if '"order":' in prompt else _real_json(prompt, system, retries)
llm.json_call = _bad_order
ok("an invalid permutation is rejected, order kept", [s["h2"] for s in faq_order.order_sections(secs)] == ["A", "B", "C"])
llm.json_call = _real_json
ok("a valid permutation is applied", [s["h2"] for s in faq_order.order_sections(secs)] == ["C", "B", "A"])
ok("FAQ from PAA is deduped and question-marked", faq_order.faq_from_paa(["What is it?", "what is it", "How much"]) == ["What is it?", "How much?"])

# ---- the balance pre-flight -----------------------------------------------------------------------
print("\nthe pre-flight")
from seo_agent.tools import run_research, build_blueprint
# run_research now STOPS ONCE and asks how long the article should be, between the brief and the
# research conversation. Outside the loop there is nobody to answer, so this answers it the way
# loop._resume_words does and calls the tool straight back with the number.
def research(ctx, **kw):
    out = run_research.run(ctx, **kw)
    if isinstance(out, dict) and out.get("ask_words"):
        out = run_research.run(ctx, word_target=out["ask_words"]["suggested"])
    return out

_fixture.stub_dfs(balance=0.20)
r0 = store.new_run(chat, "broke")
out = run_research.run(ctx_for(r0), topic="Operator education (a buyer's guide)")
ok("below $0.50 returns an error naming the balance", "balance is $0.20" in (out.get("error") or ""), out)
ok("and spends nothing", not [c for c in _fixture.DFS_CALLS if "labs" in c[0] or "serp" in c[0]])

# ---- the offline source recovery, and the needs_source stamp ---------------------------------------
# A dossier sentence that loses its [n] marker used to be handed the WHOLE SECTION's source list.
# That reads as an attribution and is not one: the figure ends up credited to pages that never said
# it, and it ships as a citation. A numeric card now gets matched against the passages the
# researchers actually read, and gets NO source at all when it cannot be matched.
print("\nthe offline source recovery")
PAGES_FOR_MATCH = [
    {"url": "https://ranked.example.org/cost",
     "passages": ["Employers report a blended internal figure near $4,700 per hire for mid-size teams, "
                  "once the recruiter's time is counted."]},
    {"url": "https://other.example.org/unrelated",
     "passages": ["This page is about office furniture and mentions nothing about hiring at all."]},
]
MATCH_IDX = source_match.build_index(PAGES_FOR_MATCH)
ok("has_number ignores one-digit noise and finds a real figure",
   source_match.has_number("a blended figure near $4,700 per hire") and not source_match.has_number("step 3 of 4"))
url, phrase = source_match.recover("A blended internal figure near $4,700 per hire is reported for mid-size teams.", MATCH_IDX)
ok("a lifted numeric claim is matched back to the one page that carried it",
   url == "https://ranked.example.org/cost" and phrase, (url, phrase))
ok("a figure nothing retrieved ever stated is left unmatched",
   source_match.recover("Turnover costs reached $98,412 per department.", MATCH_IDX) == (None, None))
ok("no index means no source, never a guess", source_match.recover("$4,700 per hire", []) == (None, None))

DOC_NO_CITE = {"sources": [{"n": 1, "url": "https://ranked.example.org/cost", "title": "Cost"},
                           {"n": 2, "url": "https://other.example.org/unrelated", "title": "Other"}],
               "sections": [{"title": "What it costs", "md":
                             "A blended internal figure near $4,700 per hire is reported for mid-size teams. "
                             "Turnover costs reached $98,412 per department. "
                             "Teams consistently forget to count the internal share.",
                             "sources": ["https://ranked.example.org/cost",
                                         "https://other.example.org/unrelated"]}]}
har_test = dossier.harvest(DOC_NO_CITE, PAGES_FOR_MATCH)
by_gloss = {c["verbatim"][:20]: c for c in har_test["cards"]}
recovered = [c for c in har_test["cards"] if c.get("source_recovered")]
flagged = [c for c in har_test["cards"] if c.get("needs_source")]
ok("a figure whose sentence lost its [n] is traced back to the real page",
   len(recovered) == 1 and recovered[0]["source_urls"] == ["https://ranked.example.org/cost"], recovered)
ok("a figure nothing supports carries NO source at all, and is stamped needs_source",
   len(flagged) == 1 and flagged[0]["source_urls"] == [] and "98,412" in flagged[0]["verbatim"], flagged)
ok("a claim with no number keeps its section\'s sources, as a cross-source claim should",
   any(not c.get("needs_source") and not c.get("source_recovered") and len(c["source_urls"]) == 2
       for c in har_test["cards"]), [(c["verbatim"][:30], c["source_urls"]) for c in har_test["cards"]])
ok("the harvest counts both, so the run can report them",
   har_test["recovered_sources"] == 1 and har_test["needs_source"] == 1, har_test)

# ---- the dossier health gate ----------------------------------------------------------------------
# A dud research run used to pass in silence: the interviews ran, the section writes came back
# near-empty, and a 300-word dossier became the foundation of the blueprint, the plan and the
# article. His conductor refuses under STORM_MIN_WORDS and re-runs the research ONCE.
print("\nthe dossier health gate")
_fixture.stub_dfs(balance=12.5)
ok("the floor and the retry budget are his numbers", (_c.DOSSIER_MIN_WORDS, _c.DOSSIER_RETRIES) == (1500, 1),
   (_c.DOSSIER_MIN_WORDS, _c.DOSSIER_RETRIES))
ok("a stub-length dossier is refused and a real one is not",
   dossier.healthy({"words": 300}) == (300, False) and dossier.healthy({"words": 1500})[1]
   and dossier.healthy({"words": 9000})[1])
# Drive the refusal by raising the floor out of reach for one run, rather than by making the stub
# write a bad dossier: the stub is shared with every other suite, and the thing under test here is
# what the run DOES when the dossier is short, not what makes it short.
_conversations = []
_real_curate_run = curate.run
def _counted_curate(*a, **k):
    _conversations.append(1)
    return _real_curate_run(*a, **k)
curate.run = _counted_curate
_c.DOSSIER_MIN_WORDS = 10 ** 6
r_thin = store.new_run(chat, "a thin dossier")
out_thin = research(ctx_for(r_thin), topic="Operator education (a buyer's guide)", angle="what changes after")
curate.run = _real_curate_run
ok("a dossier under the floor stops the run instead of poisoning everything after it",
   "{:,}".format(_c.DOSSIER_MIN_WORDS) in (out_thin.get("error") or "") and not out_thin.get("artifact"),
   out_thin)
ok("and the refusal is a person's English, naming the size and what to do",
   "words" in (out_thin.get("error") or "") and "run the research again" in (out_thin.get("error") or "").lower(),
   out_thin.get("error"))
ok("it tried the interviews a second time before giving up", len(_conversations) == 2, len(_conversations))
ok("nothing downstream was written from the thin run",
   store.load_artifact(chat, r_thin, "research.json") is None
   and store.load_artifact(chat, r_thin, "cards.json") is None)
_c.DOSSIER_MIN_WORDS = 1500

# ---- the whole run --------------------------------------------------------------------------------
print("\nrun_research, end to end")
_fixture.stub_dfs(balance=12.5)
run = store.new_run(chat, "operator education")
ctx = ctx_for(run)
out = research(ctx, topic="Operator education (a buyer's guide)", angle="what changes after")
rs = store.load_artifact(chat, run, "research.json") or {}
cards = store.load_artifact(chat, run, "cards.json") or []
ok("returns a summary and no error", bool(out.get("summary")) and not out.get("error"), out.get("error"))
ok("world has about and not_about", bool(rs.get("world", {}).get("about")) and bool(rs.get("world", {}).get("not_about")))
pr = (rs.get("keywords") or {}).get("primary") or {}
ok("primary is operator education (the measured head)", pr.get("keyword") == "operator education", pr)
ok("primary carries split_world", "split_world" in pr)
ok("the shortlist maths held: 4 of the 6 phrases per seed survive",
   len((store.load_artifact(chat, run, "_work/shortlist.json") or {}).get("rows", [])) == 8,
   len((store.load_artifact(chat, run, "_work/shortlist.json") or {}).get("rows", [])))
ok("navigational keywords never reached the scorer",
   "jobs" not in " ".join(s["keyword"] for s in (rs["keywords"].get("secondary") or []) + [pr]))
ok("serp: who ranks, PAA on/off, AI Overview", len(rs["serp"]["who_ranks"]) == 10 and rs["serp"]["paa_on"] and rs["serp"]["ai_overview"]["cites"])
ok("read-list has exactly 3 pages", len(rs["serp"]["read_list"]) == 3)
ok("winners: format, common H2s, gaps to own", rs["winners"]["format"] and rs["winners"]["common_h2s"] and rs["winners"]["gaps_to_own"])
# The word band in the build spec is now the ANSWER to the one length question (min == max), and
# what the ranking pages measured sits beside it under word_band_measured. The fixture's pages
# measure 1,500 to 2,200, so the suggestion offered and accepted here is 1,850.
ok("verdict bullets, and the answered length with the measurement kept beside it",
   len(rs["verdict"]) >= 3 and rs["build_spec"]["word_band"] == {"min": 1850, "max": 1850}
   and rs["build_spec"]["word_band_measured"] == {"min": 1500, "max": 2200}, rs["build_spec"])
ok("cannibalisation flags the top-10 keyword we already hold",
   (rs.get("cannibalisation") or {}).get("rank") == 4 and "example.com" in (rs.get("cannibalisation") or {}).get("url", ""), rs.get("cannibalisation"))
ok("the angle was replaced and the old one kept", rs["angle"] != rs["angle_before"] and rs["angle_before"] == "what changes after")
ok("the spine is set", bool(rs.get("spine")))
ok("the persona is picked once and carried", rs["persona"]["name"] == "Founder / CEO")
ok("cost was added up from the responses", rs["cost_usd"] > 0)
ev_cards = [c for c in cards if c["tag"] == "evidence"]
own_cards = [c for c in cards if c["tag"] == "ownpage"]
ok("evidence cards exist with verbatim, source and tag", ev_cards and all(c["verbatim"] and c["source_urls"] for c in ev_cards))
ok("the invented quote was dropped by the substring check",
   not any(c["verbatim"] == _fixture.FAKE_VERBATIM for c in cards) and rs["evidence"]["dropped_verbatims"] > 0)
# ---- the research conversation: a team, not a keyword lookup -------------------------------
evd = rs["evidence"]
roles = [r["role"] for r in (evd.get("team") or [])]
ok("a research team was picked, not a single searcher", len(roles) >= 3, roles)
ok("the team is mixed, never four people who agree", len(set(roles)) == len(roles), roles)
ok("every researcher asked more than one question", evd["questions"] >= len(roles) * 2, evd["questions"])
ok("each question became its own searches", evd["searches"] >= evd["questions"], (evd["searches"], evd["questions"]))
turns = evd.get("turns") or []
ok("every turn records the question, who asked it and what was searched",
   turns and all(t.get("question") and t.get("persona") and t.get("queries") for t in turns))
ok("the conversation carries forward: later questions are not the first one repeated",
   len({t["question"] for t in turns}) > 1, len({t["question"] for t in turns}))
ok("a dossier was written from what the team retrieved", evd.get("dossier_words", 0) > 0, evd.get("dossier_words"))
ok("and its sources are numbered once for the whole dossier",
   evd.get("dossier_sources") and [x["n"] for x in evd["dossier_sources"]] == list(range(1, len(evd["dossier_sources"]) + 1)))
doss = store.load_artifact(chat, run, "dossier.md") or ""
ok("the dossier is saved where a person can read it", "## Sources" in doss and len(doss.split()) > 40, len(doss.split()))
ok("the cards came out of the dossier, not off raw pages",
   ev_cards and any(c["origin"].startswith("dossier/") for c in ev_cards),
   [c["origin"] for c in ev_cards[:3]])
ok("a card cites the source its [n] marker names",
   all(c["source_urls"] for c in ev_cards if c["origin"].startswith("dossier/")))
ok("the run says which route the evidence took",
   any("researchers interviewing" in n for n in rs["notes"]), rs["notes"])

# ---- the two documents a person reads, and the trail behind them --------------------------
doc = store.load_artifact(chat, run, "research-doc.md") or ""
bun = store.load_artifact(chat, run, "bundle.md") or ""
for head in ("## Verdict", "## How the evidence was gathered", "## Keywords", "## SERP snapshot",
             "## What the winners cover", "## Build spec", "## Proof map", "## Completeness"):
    ok("the research doc has %s" % head.strip("# "), head in doc, doc[:200])
ok("the doc says how the evidence was gathered, naming the team",
   "research team of" in doc and "The Builder" in doc, doc[doc.find("## How the evidence"):][:200])
ok("the doc marks demo data at the top when the run was demo",
   ("DEMO DATA" in doc) == bool(rs.get("demo_data")))
ok("the bundle names the article, the keyword, the length and the reader",
   all(x in bun for x in ("**Title:**", "**Primary keyword:**", "**Target length:**", "**Reader")), bun[:200])
ok("the bundle's numbered pointers never skip a number",
   [int(l.split(".")[0]) for l in bun.splitlines() if l[:1].isdigit()] ==
   list(range(1, 1 + len([l for l in bun.splitlines() if l[:1].isdigit()]))),
   [l[:40] for l in bun.splitlines() if l[:1].isdigit()])
ok("the bundle lists the evidence trail with a plain name per file",
   "## The evidence trail" in bun and "`world.json`" in bun and "The world statement" in bun)
ok("every trail entry names a file that really exists",
   all(store.load_artifact(chat, run, "_work/" + r["file"]) is not None
       for r in render.trail(chat, run, store)))

ok("our own domain is never outside evidence", not any("example.com" in c["source_urls"][0] for c in ev_cards))
ok("gap check judged the checklist items", len(rs["gap_check"]["items"]) >= 3 and all(i["verdict"] in ("covered", "partial", "no") for i in rs["gap_check"]["items"]))
ok("gap check caps at 3 questions (the stub asked for 4)", len(rs["gap_check"]["queries"]) == 3, len(rs["gap_check"]["queries"]))
# ---- the gap fill is the real research conversation, not a keyword lookup ------------------
# His 12-gap-check re-runs STORM ITSELF per gap query, four perspectives and four turns, carrying
# the article's spine. Sutra answered the same gap with one keyword search, so the holes that
# matter most — the gaps we can own — got the thinnest evidence in the run.
rounds = rs["gap_check"]["fill_rounds"]
ok("every gap question got its own round, one per query",
   len(rounds) == len(rs["gap_check"]["queries"]), rounds)
ok("each round was the research conversation, not a keyword read",
   rounds and all(r["route"] == "the research conversation" for r in rounds), [r["route"] for r in rounds])
ok("each round asked real questions rather than running one search",
   rounds and all(r["questions"] >= 2 for r in rounds), [r["questions"] for r in rounds])
ok("each round wrote its own dossier and lifted facts out of it",
   rounds and all(r["harvested"] >= 1 for r in rounds), [r["harvested"] for r in rounds])
_main_vb = {c["verbatim"] for c in ev_cards if not c["origin"].startswith("gap/")}
_gap_vb = [c["verbatim"] for c in ev_cards if c["origin"].startswith("gap/")]
ok("a fact the main round already carries is never filed again by a gap round",
   not (set(_gap_vb) & _main_vb), sorted(set(_gap_vb) & _main_vb)[:2])
ok("whatever a gap round does keep came out of its own dossier",
   all(c["origin"].startswith("gap/dossier/") for c in ev_cards if c["origin"].startswith("gap/")),
   [c["origin"] for c in ev_cards if c["origin"].startswith("gap/")][:3])
ok("ownpage cards come from the index and carry internal_link",
   own_cards and all(c["internal_link"] and c["internal_link"].startswith("https://example.com") for c in own_cards), len(own_cards))
ok("ownpage verbatim is the code-sliced section text", all(c["heading"] for c in own_cards))
ok("reuse verdict recorded with real chosen links",
   rs["reuse"]["verdict"] == "Build from parts" and all(u.startswith("https://example.com") for u in rs["reuse"]["chosen_links"]))
ok("card ids are continuous, evidence first then ownpage",
   [c["id"] for c in cards] == list(range(1, len(cards) + 1)) and cards[0]["tag"] == "evidence" and cards[-1]["tag"] == "ownpage")
ok("older readers still find primary_keyword and people_also_ask", rs.get("primary_keyword", {}).get("keyword") and isinstance(rs.get("people_also_ask"), list))
ok("substeps were emitted with a parent", len(events) > 15 and all(e.get("parent") for e in events))

print("\nresume")
n_calls = len(_fixture.DFS_CALLS)
out2 = research(ctx, topic="Operator education (a buyer's guide)", angle="what changes after")
ok("a second run reuses every step and spends nothing", len(_fixture.DFS_CALLS) == n_calls and not out2.get("error"))
ok("and rewrites the same brief", (store.load_artifact(chat, run, "research.json") or {}).get("keywords", {}).get("primary", {}).get("keyword") == "operator education")

# ---- the blueprint --------------------------------------------------------------------------------
print("\nbuild_blueprint")
out = build_blueprint.run(ctx)
bp = store.load_artifact(chat, run, "blueprint.json") or {}
cards2 = store.load_artifact(chat, run, "cards.json") or []
scored = store.load_artifact(chat, run, "_work/scored-cards.json") or {}
ok("returns a summary and no error", bool(out.get("summary")) and not out.get("error"), out.get("error"))
ok("h1 is the topic", bp.get("h1") == "Operator education (a buyer's guide)")
kept_ids = set(scored.get("kept_ids") or [])
# PROTECT, driven straight at the filter rather than through whichever step happened to read a raw
# page. The rule is what matters: a card the judge scores off-spine survives anyway when it carries
# a figure, and the same card without one does not.
from seo_agent.research import score_cards
_protect_pair = [
    {"id": 9001, "tag": "evidence", "gloss": "how far the field goes back",
     "verbatim": "The history of the field goes back to 1990 and 42 early programmes.",
     "source_urls": ["https://ranked.example.org/a"]},
    {"id": 9002, "tag": "evidence", "gloss": "the field's history in general",
     "verbatim": "The history of the movement is long and contested.",
     "source_urls": ["https://ranked.example.org/a"]},
]
_kept_pair, _prep = score_cards.run(_protect_pair, rs["topic"], rs["angle"], rs["persona"],
                                    {"spine": rs["spine"], "about": rs["world"]["about"],
                                     "not_about": rs["world"]["not_about"]},
                                    "Example — practitioner-led business programmes")
ok("PROTECT keeps a low-relevance card that carries a number",
   [c["id"] for c in _kept_pair] == [9001] and _protect_pair[0]["protected"]
   and _protect_pair[0]["relevance"] == 0, (_kept_pair, _protect_pair[0]))
ok("a low-relevance card without a number is dropped",
   [d["id"] for d in _prep["dropped"]] == [9002], _prep["dropped"])
ok("drops are on record with a reason",
   all(d.get("reason") for d in _prep["dropped"]) and _prep["dropped_count"] > 0, _prep["dropped"])
placed = []
for s in bp["sections"]:
    placed += s["evidence"]
    for h in s["h3"]:
        placed += h["evidence"]
ok("MECE holds: every kept card in exactly one section", sorted(placed) == sorted(kept_ids), (len(placed), len(kept_ids)))
ok("internal_links attach per section from the ownpage cards",
   any(s["internal_links"] for s in bp["sections"]) and all(u.startswith("https://example.com") for s in bp["sections"] for u in s["internal_links"]))
ok("external_links never include our own pages", not any("example.com" in u for s in bp["sections"] for u in s["external_links"]))
ok("every section has an h2 and a job", all(s["h2"] and s["job"] for s in bp["sections"]))
ok("faq is the PAA, deduped, with question marks",
   bp["faq"] == ["What is operator education?", "How much does operator education cost?", "Is operator education worth it?"], bp["faq"])
ks = bp["keyword_set"]
ok("keyword_set shape", set(ks) == {"primary", "variations", "secondaries", "in_body"} and ks["primary"] == "operator education"
   and ks["primary"] not in ks["secondaries"] and ks["in_body"] == ["decision speed"], ks)
ok("orphan keywords come from the measured pool", all("keyword" in o and "volume" in o for o in bp["orphan_keywords"]))
ok("persona reused, never re-picked", bp["persona"] == rs["persona"])
ok("format archetype and the answered length carried", bp["format_archetype"] == "how-to guide" and bp["word_band"] == {"min": 1850, "max": 1850}, bp.get("word_band"))
ok("angle_filter counts", bp["angle_filter"]["kept"] + bp["angle_filter"]["dropped"] == len(cards2))
ok("write guidance is present", "note" in bp.get("write_guidance", {}))
ok("older readers find title and heading/covers", bp.get("title") and all(s.get("heading") and s.get("covers") for s in bp["sections"]))

print("\nthe scorer fails closed")
def _scorer_dies(prompt, system=None, retries=1):
    if '{"scores":[' in prompt:
        raise ValueError("scorer down")
    return _real_json(prompt, system, retries)
llm.json_call = _scorer_dies
out = build_blueprint.run(ctx, redo=True)
ok("a failed scorer aborts the blueprint instead of keeping everything", bool(out.get("error")) and "scorer" in out["error"].lower(), out)
llm.json_call = _real_json

import os as _os
if not _os.environ.get('KEEP_RUN'):
    shutil.rmtree(store.chat_dir(chat))
if _saved_index is not None:
    store.save_knowledge("site_index.json", _saved_index)
print("\nStubbed model, wire and web. Proves the guards and the shapes, not the judgment.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all research checks passed")
