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
from seo_agent.research import _common as _c, evidence, expand, faq_order, gap_check, keywords, serp, topic_gate, web

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
_fixture.stub_dfs(balance=0.20)
r0 = store.new_run(chat, "broke")
out = run_research.run(ctx_for(r0), topic="Operator education (a buyer's guide)")
ok("below $0.50 returns an error naming the balance", "balance is $0.20" in (out.get("error") or ""), out)
ok("and spends nothing", not [c for c in _fixture.DFS_CALLS if "labs" in c[0] or "serp" in c[0]])

# ---- the whole run --------------------------------------------------------------------------------
print("\nrun_research, end to end")
_fixture.stub_dfs(balance=12.5)
run = store.new_run(chat, "operator education")
ctx = ctx_for(run)
out = run_research.run(ctx, topic="Operator education (a buyer's guide)", angle="what changes after")
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
ok("verdict bullets and a word band", len(rs["verdict"]) >= 3 and rs["build_spec"]["word_band"] == {"min": 1500, "max": 2200})
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
ok("our own domain is never outside evidence", not any("example.com" in c["source_urls"][0] for c in ev_cards))
ok("gap check judged the checklist items", len(rs["gap_check"]["items"]) >= 3 and all(i["verdict"] in ("covered", "partial", "no") for i in rs["gap_check"]["items"]))
ok("gap check caps at 3 questions (the stub asked for 4)", len(rs["gap_check"]["queries"]) == 3, len(rs["gap_check"]["queries"]))
ok("the gap rounds added cards", any(c["origin"].startswith("gap/") for c in ev_cards))
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
out2 = run_research.run(ctx, topic="Operator education (a buyer's guide)", angle="what changes after")
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
numeric_history = [c for c in cards2 if "history" in c["verbatim"].lower() and "1990" in c["verbatim"]]
plain_history = [c for c in cards2 if "history of the movement" in c["verbatim"].lower()]
kept_ids = set(scored.get("kept_ids") or [])
ok("PROTECT keeps a low-relevance card that carries a number",
   numeric_history and all(c["id"] in kept_ids and c["protected"] and c["relevance"] == 0 for c in numeric_history))
ok("a low-relevance card without a number is dropped", plain_history and all(c["id"] not in kept_ids for c in plain_history))
ok("drops are on record with a reason", all(d.get("reason") for d in scored["report"]["dropped"]) and scored["report"]["dropped_count"] > 0)
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
ok("format archetype and word band carried", bp["format_archetype"] == "how-to guide" and bp["word_band"] == {"min": 1500, "max": 2200})
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

shutil.rmtree(store.chat_dir(chat))
if _saved_index is not None:
    store.save_knowledge("site_index.json", _saved_index)
print("\nStubbed model, wire and web. Proves the guards and the shapes, not the judgment.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all research checks passed")
