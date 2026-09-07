"""tests/test_brand.py — the brand pack (learn_brand and its twelve builders), with the model stubbed.

Proves the plumbing: every builder reads the right inputs, writes its file with the original's
section headings, the rules the originals enforced in code still hold (a confirmed row is never
clobbered, the writer-brief verdict order, the CTA filters, card ids from 8001 and the n= check),
and the run is resumable. Reddit is stubbed too. What this does NOT prove is whether the model's
judgments are any good; only a real run does that.
"""
import os
import re
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store

# --- stub the model, counting calls so resume can be proven ------------------------------------
CALLS = {"json": 0, "text": 0}
UNFILLED = []          # any prompt that still carries a {{TOKEN}} when it reaches the model


def _json(prompt, system=None, retries=1, **kw):
    CALLS["json"] += 1
    if "{{" in prompt:
        UNFILLED.append(prompt[:80])
    return _fixture.stub_json(prompt, system, retries)


def _text(prompt, system=None, **kw):
    CALLS["text"] += 1
    if "{{" in prompt:
        UNFILLED.append(prompt[:80])
    return _fixture.stub_text(prompt, system)


llm.json_call = _json
llm.text = _text

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def calls():
    return CALLS["json"] + CALLS["text"]


# --- a richer site than the shared fixture: types, traffic, stories, a leaf product page ----------
BODY = _fixture._BODY
PAGES = [
    ("https://example.com/", "page", "Example: education for operators", 900, "operator education"),
    ("https://example.com/programmes", "page", "Programmes", 300, "leadership programme"),
    ("https://example.com/about", "page", "About", 50, ""),
    ("https://example.com/pricing/", "page", "Pricing", 120, "programme pricing"),
    ("https://example.com/why-us/", "page", "Why us", 0, ""),
    ("https://example.com/compare-planos/", "page", "Comparar planos", 10, ""),
    ("https://example.com/customers/acme", "successstory", "How Acme hires", 40, ""),
    ("https://example.com/customers/beta", "successstory", "How Beta hires", 30, ""),
    ("https://example.com/blog/what-changes-after", "post", "What changes after a programme", 260, "after executive education"),
    ("https://example.com/blog/what-is-operator-education", "post", "What is operator education?", 500, "operator education definition"),
    ("https://example.com/blog/how-to-run-a-cohort", "post", "How to run a cohort", 400, "run a cohort"),
    ("https://example.com/blog/top-10-operator-skills", "post", "Top 10 operator skills", 350, "operator skills"),
    ("https://example.com/blog/mba-vs-operator-programme", "post", "MBA vs operator programme", 200, "mba vs operator programme"),
    ("https://example.com/blog/thoughts-on-leadership", "post", "Thoughts on leadership", 150, "leadership"),
    ("https://example.com/blog/hiring-interview-questions", "post", "Hiring interview questions", 100, "interview questions"),
    ("https://example.com/integrations/slack", "integration", "Slack integration", 20, ""),
    ("https://example.com/test-library/bricklayer", "product", "Bricklayer test", 1198, "bricklayer test"),
    ("https://example.com/product/operator-interview-questions", "product", "Operator interview questions", 80, ""),
    ("https://example.com/rival-one-alternatives", "product", "Rival One alternatives", 15, "rival one alternatives"),
    ("https://example.com/product/cohort-builder", "product", "Cohort builder", 200, "cohort builder"),
]


def plant():
    kd = store.knowledge_dir()
    shutil.rmtree(os.path.join(kd, "brand"), ignore_errors=True)
    for f in ("brand_voice.json",):
        try:
            os.remove(os.path.join(kd, f))
        except OSError:
            pass
    rows, db, top = [], [], []
    for url, typ, title, traffic, kw in PAGES:
        body = BODY.format(h1=title)
        rows.append({"url": url, "type": typ, "title": title, "description": title, "h1": title,
                     "word_count": len(body.split()), "text": body[:400], "body_chars": len(body),
                     "body_status": "ok", "traffic": traffic, "traffic_clean": traffic,
                     "top_keyword": kw, "position": 5 if kw else 0, "lang": "en"})
        db.append({"url": url, "type": typ, "title": title, "body": body})
        if traffic:
            top.append({"url": url, "traffic": traffic, "traffic_clean": traffic, "top_keyword": kw, "intent": "informational"})
    top.sort(key=lambda r: -r["traffic"])
    import json
    store.save_knowledge("site_index.json", {"domain": "example.com", "page_count": len(rows), "pages": rows,
                                             "indexed_at": "2026-01-01T00:00:00Z"})
    store.save_knowledge("content-database.jsonl", "\n".join(json.dumps(r) for r in db) + "\n")
    store.save_knowledge("top-pages.json", top)
    store.save_knowledge("brand/company.json", {"brand": "Example", "domain": "example.com", "wordpress_url": "",
                                                "brand_oneliner": "", "niche_definition": "",
                                                "location_name": "United States", "language_code": "en", "about": ""})


plant()

# --- stub Reddit -------------------------------------------------------------------------------------
from seo_agent.brand import field_sources
field_sources.THROTTLE = 0
_HIT = ('<div class="search-result search-result-link"><span class="search-score">12 points</span>'
        '<a class="search-comments">%d comments</a></div>')
FETCHED = []


def fake_fetch(url):
    FETCHED.append(url)
    sub = url.split("/r/", 1)[1].split("/", 1)[0]
    if sub == "blockedsub":
        return "<html><body>log in to continue</body></html>"     # a 200 that is really a login page
    if sub == "flaky":
        return None
    if sub == "deadsub":
        return "<html>" + _HIT % 3 + "</html>"
    return "<html>" + "".join(_HIT % 20 for _ in range(6)) + "</html>"


field_sources.fetch = fake_fetch

# --- drive the tool -----------------------------------------------------------------------------------
c = store.new_chat("brand test")
r = store.new_run(c, "brand pack")
events = []
ctx = {"chat_id": c, "run_id": r, "emit": lambda **kw: events.append(kw)}

from seo_agent.tools import learn_brand
from seo_agent.brand import _common as cm, brand_facts, writer_brief, brand_cards, features, style_guide, pack


def brand(name):
    return cm.read(name)


print("\nlearn_brand: the whole pack, first run")
try:
    out = learn_brand.run(ctx)
    ok("returns a summary", bool(out.get("summary")), out.get("summary"))
    ok("returns files, needs_review and a null artifact",
       isinstance(out.get("files"), list) and isinstance(out.get("needs_review"), list) and out.get("artifact") is None)
    ok("every builder finished", not any("did not finish" in n for n in out["needs_review"]), out["needs_review"])
    ok("emitted progress substeps", len(events) > 30, len(events))
    ok("the model was called", calls() > 20, calls())
except Exception as e:
    import traceback; traceback.print_exc()
    ok("runs", False, e)

print("\n0 type-roles")
roles = brand("type-roles.json")
ok("type-roles.json has the four role lists + notes", isinstance(roles, dict) and all(k in roles for k in
   ("stat_types", "story_types", "commercial_types", "editorial_types", "notes")))

print("\n1 brand-facts")
stats = brand("stats.md")
ok("stats.md keeps the template's rule header", "# Stats — Example" in stats and "> **Rule:**" in stats)
ok("stats.md has the three tables", all(h in stats for h in ("## Product / scale", "## Results / proof", "## Credibility")))
ok("stats.md rows are marked ⚠️ with a source URL", "| Customers | 1,500+ | ⚠️ https://example.com/" in stats)
ok("stats rows were deduped across pages", stats.count("| Customers |") == 1, stats.count("| Customers |"))
ok("the drafted rows sit under the right bucket",
   stats.index("## Results / proof") < stats.index("| Time-to-hire cut |") < stats.index("## Credibility"))
stories = brand("stories.md")
ok("stories.md keeps its headings", "## Stories" in stories and "## The interview" in stories)
ok("stories are ⚠️ entries in the template's format", "### ⚠️ Acme cut its hiring time" in stories
   and "- Point it makes:" in stories and "- Source: https://example.com/customers/acme" in stories)
ok("the stories placeholder was replaced", "*(none yet)*" not in stories.split("## The interview")[0])
opinions = brand("opinions.md")
ok("opinions.md is the interview, untouched by the machine", "## The interview" in opinions and "*(none yet)*" in opinions)
ok("needs_review names the ⚠️ rows", any(n.startswith("stats.md:") and "⚠️" in n for n in out["needs_review"]), out["needs_review"])

print("\n1 brand-facts: the seed rule")
confirmed = stats.replace("| Customers | 1,500+ | ⚠️ https://example.com/ — \"Trusted by 1,500+ teams\" |",
                          "| Customers | 1,500+ | https://example.com/ — confirmed by: Dev, 2026-01-02 |")
ok("the test set up a confirmed row", brand_facts.human_confirmed(confirmed) and not brand_facts.human_confirmed(stats))
cm.save("stats.md", confirmed)
say = lambda label, note="": None
n0 = calls()
brand_facts.run({"brand": "Example", "domain": "example.com", "niche_definition": "", "language_code": "en"}, say, redo=True)
ok("a confirmed stats.md is never clobbered", brand("stats.md") == confirmed)
ok("new candidates go beside it", cm.exists("_drafts/stats-new-candidates.md")
   and "## Product / scale" in brand("_drafts/stats-new-candidates.md") and "⚠️" in brand("_drafts/stats-new-candidates.md"))
ok("redo re-read the pages", calls() > n0)
ok("opinions.md was left alone by the redo", brand("opinions.md") == opinions)
ok("a redo replaces the drafted stories instead of appending a second copy", brand("stories.md").count("### ⚠️") == 2, brand("stories.md").count("### ⚠️"))
ok("strip_drafts(): the ⚠️ rows go, a confirmed row stays", brand_facts.strip_drafts(confirmed, "stats").count("| Customers |") == 1
   and not any("⚠️" in ln for ln in brand_facts.strip_drafts(confirmed, "stats").splitlines() if ln.startswith("|")))
ok("a bare template is not 'confirmed'", not brand_facts.human_confirmed(cm.template("stats")))

print("\n2 brand-voice")
sl = brand("page-shortlist.md")
ok("page-shortlist.md written", sl.startswith("# Page shortlist — Example") and "https://example.com/pricing/" in sl)
bv = brand("brand-voice.md")
for h in ("## Brand Voice Pillars", "## Tone Guidelines", "## Messaging Framework", "## Writing Style Guidelines",
          "## Content Formatting", "## Voice Examples", "## Audience Understanding", "## Quality Checklist"):
    ok("brand-voice.md has %s" % h, h in bv)
ok("no placeholder survives", not re.search(r"\[[A-Z][A-Z /·&-]{2,}\]", bv))
ev = brand("_work/brand-voice/evidence.json")
ok("one evidence row per shortlisted page", isinstance(ev, list) and len(ev) == len(re.findall(r"^- https://", sl, re.M)), (len(ev or []), sl.count("\n- ")))
ok("the gate verdict was saved", isinstance(brand("_work/brand-voice/gate-round-1.json"), dict))
rec = store.knowledge("brand/company.json")
ok("the one-liner and niche were filled into company.json where empty",
   rec.get("brand_oneliner", "").startswith("Example —") and "executive education" in rec.get("niche_definition", ""))

print("\n3 style-guide")
sg = brand("style-guide.md")
for h in ("## Grammar & Mechanics", "## Word Choice & Usage", "## Formatting Standards", "## SEO-Specific Style",
          "## Brand-Specific Guidelines", "## Editing Checklist"):
    ok("style-guide.md has %s" % h, h in sg)
ok("no [BLOGS]/[STANDARD]/[COMPANY] tag survives", not re.search(r"\[(?:BLOGS|STANDARD|COMPANY)", sg))
an = brand("_work/style-guide/analysis.json")
ok("the merge happened in code: majority for enums, union for lists",
   isinstance(an, dict) and an.get("oxford_comma") in ("Yes", "No") and isinstance(an.get("industry_terms"), list)
   and len(an["industry_terms"]) == len({t.lower() for t in an["industry_terms"]}))
m = style_guide.merge([{"oxford_comma": "Yes", "acronyms": ["ATS", "HR"], "brand_naming": "a"},
                       {"oxford_comma": "Yes", "acronyms": ["hr", "DEI"], "brand_naming": "b"},
                       {"oxford_comma": "No", "acronyms": [], "brand_naming": ""}])
ok("merge(): majority wins, union dedupes case-insensitively, text is carried per batch",
   m["oxford_comma"] == "Yes" and m["acronyms"] == ["ATS", "HR", "DEI"] and m["brand_naming"] == "batch1: a | batch2: b")
tb = brand("_work/style-guide/top-blogs.json")
ok("blogs came from the editorial type only", all("/blog/" in b["url"] for b in tb) and len(tb) == 7, [b["url"] for b in tb])

print("\n4 features + cta-pages")
ft = brand("features.md")
for h in ("## Core Value Propositions", "## Technical Features", "## Integrations & Ecosystem", "## Competitive Differentiators",
          "## Use Cases by Customer Segment", "## Pricing & Plan Benefits", "## Key Messaging for Conversions",
          "## Common Questions & Objections", "## Content Creation Guidelines"):
    ok("features.md has %s" % h, h in ft)
sp = brand("_work/features/source-pages.json")
kinds = {p["url"]: p["kind"] for p in sp}
ok("kinds come from the URL signals, then the classified types",
   kinds.get("https://example.com/pricing/") == "pricing / plans / compare"
   and kinds.get("https://example.com/rival-one-alternatives") == "competitor comparison"
   and kinds.get("https://example.com/integrations/slack") == "integrations"
   and kinds.get("https://example.com/") == "homepage"
   and kinds.get("https://example.com/product/cohort-builder") == "product or feature page", kinds)
ok("plain editorial posts are not product pages (only the URL-hinted -vs- post is a comparison candidate, as in the original)",
   [u for u in kinds if "/blog/" in u] == ["https://example.com/blog/mba-vs-operator-programme"]
   and kinds["https://example.com/blog/mba-vs-operator-programme"] == "competitor comparison", {u: k for u, k in kinds.items() if "/blog/" in u})
cta = brand("cta-pages.md")
ok("cta-pages.md has its heading and the dropped list", "pages a call to action may link to" in cta and "## Dropped, and why" in cta)
kept_urls = re.findall(r"^- Page: (\S+)", cta, re.M)
ok("the homepage comes first, then by traffic", kept_urls and kept_urls[0] == "https://example.com/", kept_urls)
ok("the leaf test page is dropped despite the highest traffic",
   "https://example.com/test-library/bricklayer" not in kept_urls and "bricklayer  — leaf page" in cta)
ok("the localised duplicate is dropped", "compare-planos/  — localised or superseded duplicate" in cta)
ok("the article-shaped product page is dropped", "operator-interview-questions  — reads as an article" in cta)
ok("competitor comparisons are dropped by kind", "rival-one-alternatives  — kind is competitor comparison" in cta)
ok("the real product and pricing pages are kept",
   "https://example.com/product/cohort-builder" in kept_urls and "https://example.com/pricing/" in kept_urls, kept_urls)
rows_, dropped_ = features.cta_rows(
    [{"url": "https://x.com/a", "kind": "homepage", "features": ["f1", "f2", "f3", "f4"]},
     {"url": "https://x.com/how-to-hire", "kind": "product or feature page", "features": []}],
    [{"url": "https://x.com/a", "title": "A", "traffic": 5}])
ok("cta_rows(): at most three features per page, article-shaped URLs dropped",
   len(rows_) == 1 and len(rows_[0]["features"]) == 3 and dropped_[0][1].startswith("reads as an article"))

print("\n5 writing-examples")
# a writing example is a published article: never the homepage, a commercial page, or nav furniture
from seo_agent.brand import writing_examples as _we
_co = {"domain": "example.com", "brand": "Example"}
ok("the homepage is never a writing example",
   not _we._is_article({"url": "https://example.com/", "title": "Home", "body": "x " * 500}, _co))
ok("a commercial landing page is never a writing example",
   not _we._is_article({"url": "https://example.com/pricing/", "title": "Pricing", "body": "x " * 500}, _co))
ok("a title full of nav dot leaders is never a writing example",
   not _we._is_article({"url": "https://example.com/x/", "title": "Hire for skills,not \u00b7\u00b7\u00b7\u00b7", "body": "x " * 500}, _co))
ok("a page too short to learn from is never a writing example",
   not _we._is_article({"url": "https://example.com/short/", "title": "Short", "body": "x " * 50}, _co))
ok("a real published article is",
   _we._is_article({"url": "https://example.com/a-guide-to-skills/", "title": "A guide to skills", "body": "x " * 500}, _co))

we = brand("writing-examples.md")
ok("writing-examples.md has its title and instructions", we.startswith("# Example Writing Examples") and "**What Makes It Great**" in we)
ok("five examples", we.count("## Example ") == 5, we.count("## Example "))
ok("each example carries URL, keyword, word count and the full body",
   we.count("**URL**:") == 5 and we.count("**Primary Keyword**:") == 5 and we.count("**Word Count**:") == 5 and we.count("**Full Content**") == 5)
ok("the off-voice article was dropped", "thoughts-on-leadership" not in we)
ok("the primary keyword comes from the traffic data, not the title", "**Primary Keyword**: run a cohort" in we)
ok("three or more formats and no human-decision flag", "⚑ HUMAN DECISION" not in we)
sc = brand("_work/writing-examples/scored.json")
ok("scores are saved without the bodies", isinstance(sc, list) and sc and all("body" not in s for s in sc))

print("\n6 persona")
pe = brand("persona.md")
ok("persona.md has the table and the READER-not-byline warning",
   "| Persona | Who | Reads | Cares about | Depth & angle | Not this |" in pe and "READER we write TO" in pe
   and "## How to pick the persona for an article" in pe)
ok("three personas", pe.count("| **") == 3, pe.count("| **"))

print("\n7 voices")
vo = brand("voices.md")
ok("voices.md is the questionnaire with the default byline", "## Default byline — Example Team" in vo
   and "## Auto-route rules" in vo and "*(ask" in vo)
ok("needs_review asks the team to fill it", any(n.startswith("voices.md") for n in out["needs_review"]))

print("\n8 writing-integrity + checklist")
wi = brand("writing-integrity.md")
ok("writing-integrity.md carries the brand and all ten rules", "Writing Integrity — Example" in wi
   and all(("## %d." % i) in wi for i in range(1, 11)))
ok("PRODUCT_IS is filled from the one-liner and features.md", "{{PRODUCT_IS}}" not in wi
   and "Example — practitioner-led" in wi and "Cohort builder" in wi)
ok("PRODUCT_IS_NOT stays a marked slot", "{{PRODUCT_IS_NOT}}" not in wi and "⚑ HUMAN DECISION: list what the product is NOT" in wi)
ok("the competitor list points at the agent's own file", "knowledge/competitors.json" in wi)
ck = brand("seo-aeo-geo-checklist.md")
ok("seo-aeo-geo-checklist.md is the verbatim gate", ck == cm.template("seo-aeo-geo-checklist") and "**Content**" in ck and "**Ship**" in ck)

print("\n9 writer-brief")
wb = brand("writer-brief.md")
for h in ("## Who is writing", "## What we believe", "## Naming Example", "## How our writing sounds", "## Words we use",
          "## House spelling", "## Phrases we never use", "## Competitors"):
    ok("writer-brief.md has %s" % h, h in wb)
ok("the rulings file was instantiated from the template", "# House decisions — Example" in brand("writer-brief-rulings.md"))
cl = brand("_work/writer-brief/classified.json")
secs = (cl or {}).get("sections") or []
ok("classified.json has every section with a verdict", secs and all("verdict" in s and "file" in s for s in secs))
by_head = {(s["file"], s["heading"]): s for s in secs}
one = {k: v for k, v in by_head.items() if k[0] == "brand-voice.md"}
vd = {k[1]: (v["verdict"], v["drop_reason"]) for k, v in one.items()}
ok("verdicts follow the recipe's order, in code",
   vd.get("Terminology") == ("keep", "") and vd.get("Quality Checklist") == ("drop", "not-the-writers-job")
   and vd.get("Social proof") == ("drop", "a-fact") and vd.get("Acronyms") == ("drop", "a-lookup-list")
   and vd.get("Sentence Structure") == ("drop", "general-craft"), vd)
ok("an unknown kind is treated as reference", vd.get("Odd one") == ("drop", "a-lookup-list"), vd.get("Odd one"))
ok("verdict(): not actionable wins over everything",
   writer_brief.verdict({"actionable": False, "kind": "fact", "scope": "universal"}) == ("drop", "not-the-writers-job"))
ok("verdict(): fact before reference before universal",
   writer_brief.verdict({"actionable": True, "kind": "fact", "scope": "universal"}) == ("drop", "a-fact")
   and writer_brief.verdict({"actionable": True, "kind": "reference", "scope": "universal"}) == ("drop", "a-lookup-list")
   and writer_brief.verdict({"actionable": True, "kind": "rule", "scope": "universal"}) == ("drop", "general-craft")
   and writer_brief.verdict({"actionable": True, "kind": "rule", "scope": "company"}) == ("keep", ""))
dr = brand("_work/writer-brief/dropped.md")
ok("dropped.md records every drop, general-craft in full", "## general-craft" in dr and "Vary length" in dr and "## a-fact" in dr)
carried = [e for e in events if e.get("label") == "Concrete items carried through"]
ok("the atom loss check is printed as a substep", carried and re.match(r"\d+ of \d+", carried[-1]["note"]), carried)
ok("the kept atoms all survived (the stub carries the table through)", carried and carried[-1]["note"].split(" of ")[0] == carried[-1]["note"].split(" of ")[1].split(";")[0], carried[-1]["note"] if carried else "")
ok("atoms(): arrow pairs keep the side that must survive", writer_brief.atoms("| clients -> customers | x |") == {"clients"})

print("\n10 brand-cards")
bc = brand("brand-cards.json")
ok("brand-cards.json has research and results lists", isinstance(bc, dict) and isinstance(bc.get("research"), list) and isinstance(bc.get("results"), list))
ok("ids start at 8001 and run without gaps", [c["id"] for c in bc["research"] + bc["results"]] == list(range(8001, 8001 + len(bc["research"]) + len(bc["results"]))))
ok("customer results were parsed from stories.md by code", len(bc["results"]) == 2 and all(c["tag"] == "brand-result" and c["source_urls"] for c in bc["results"]), bc["counts"])
ok("results from ⚠️ stories are marked unconfirmed", all(c.get("confirmed") is False for c in bc["results"])
   and any("unconfirmed" in n for n in out["needs_review"]))
ok("no research study in a bare stats.md means no research cards", bc["counts"]["research"] == 0)
# now a study in stats.md, in the shape the original expected: a ## block with ### questions under it
study = (brand("stats.md") + "\n\n## The study\n**The Example Hiring Survey 2026** — 128 HR and TA practitioners, fielded in May.\n\n"
         "## Validation\n### Q9. Who validates your assessments?\n| Answer | Share |\n|---|---|\n| Nobody | 44.5% |\n\n"
         "## Speed\n### Q3. How long to shortlist?\n| Answer | Share |\n|---|---|\n| 4+ days | 78.7% |\n")
cm.save("stats.md", study)
h, secs_ = brand_cards.split_study(study)
ok("split_study(): the header keeps the study description, sections are the ## blocks with ### under them",
   "The Example Hiring Survey 2026" in h and len(secs_) == 2 and brand_cards.citation(h) == "The Example Hiring Survey 2026")
n0 = calls()
brand_cards.run({"brand": "Example", "domain": "example.com", "niche_definition": ""}, say, redo=True)
bc = brand("brand-cards.json")
ok("research cards were extracted (one model call per batch of 3 sections)", bc["counts"]["research"] == 2 and calls() - n0 == 1, (bc["counts"], calls() - n0))
ok("research first, then results, ids continuous from 8001",
   [c["id"] for c in bc["research"]] == [8001, 8002] and [c["id"] for c in bc["results"]] == [8003, 8004])
ok("every research card carries the study citation", all(c["source_note"] == "The Example Hiring Survey 2026" for c in bc["research"]))
ok("the n= check flags the card without a base", bc["warnings"]["no_base"] == [8002] and bc["warnings"]["no_number"] == [])
ok("no research URL is invented", all(c["source_urls"] == [] for c in bc["research"]) and bc["research_url"] == "")

print("\n11 field-sources")
fs = brand("field-sources.md")
ok("field-sources.md has the Reddit table and the other two sources", "## Reddit" in fs and "## Teamblind" in fs and "## LinkedIn" in fs)
cands = (brand("_work/field-sources/candidates.json") or {}).get("candidates") or []
verd = {c["name"]: c["verdict"] for c in cands}
ok("the r/ prefix is stripped without eating letters", "recruiting" in verd and "jobs" in verd and "r/recruiting" not in verd, verd)
ok("live subreddits are kept", verd.get("recruiting") == "keep" and verd.get("AskHR") == "keep", verd)
ok("a quiet subreddit is dropped by the activity thresholds", verd.get("deadsub") == "drop")
ok("a login page with a 200 is unknown, never empty", verd.get("blockedsub") == "unknown")
ok("unverified is said, not raised", any("unverified" in n for n in out["needs_review"]), out["needs_review"])
ok("kept names are in the file, dropped ones are not in the table", "recruiting" in fs and not re.search(r"\|\s*deadsub\s*\|", fs))
ok("Reddit was probed once per candidate", len(FETCHED) == len(cands), (len(FETCHED), len(cands)))
ok("a network failure degrades to unknown", field_sources.probe("flaky") is None)

print("\nresume, redo and only")
n_ev, n_calls = len(events), calls()
out2 = learn_brand.run(ctx)
ok("a second run makes no model calls", calls() == n_calls, calls() - n_calls)
ok("and says every builder was already built",
   all(e["label"].startswith(("Already built", "Kept", "Building")) for e in events[n_ev:]), [e["label"] for e in events[n_ev:]][:6])
ok("the summary says what was kept", "kept" in out2["summary"], out2["summary"])
before = {f: os.path.getmtime(cm.path(f)) for f in ("brand-voice.md", "features.md", "style-guide.md")}
n_calls = calls()
out3 = learn_brand.run(ctx, only="persona")
ok("only=persona rebuilds just the persona", calls() - n_calls == 1 and "persona" in out3["summary"], (calls() - n_calls, out3["summary"]))
ok("the other files were not touched", all(os.path.getmtime(cm.path(f)) == t for f, t in before.items()))
try:
    learn_brand.run(ctx, only="nonsense")
    ok("an unknown builder name is refused", False, "no raise")
except ValueError as e:
    ok("an unknown builder name is refused", "Unknown builder" in str(e))

print("\npack.summary()")
ps = pack.summary()
names = [f["name"] for f in ps["files"]]
ok("lists every brand file in build order", names[0] == "type-roles.json" and "writer-brief.md" in names and names[-1] == "seo-aeo-geo-checklist.md")
ok("every file exists after a full run", all(f["exists"] for f in ps["files"]), [f["name"] for f in ps["files"] if not f["exists"]])
ok("flags are counted from the files", any("⚠️" in x for f in ps["files"] if f["name"] == "stats.md" for x in f["flags"]))
ok("needs_review points at the human gates", any(n.startswith("voices.md") for n in ps["needs_review"])
   and any(n.startswith("opinions.md") for n in ps["needs_review"]))

print("\nlearn_voice: the alias")
from seo_agent.tools import learn_voice
try:
    n_calls = calls()
    o = learn_voice.run(ctx, sample_pages=4)
    v = store.knowledge("brand_voice.json")
    ok("returns a summary", bool(o.get("summary")))
    ok("reuses the built brand-voice.md without calling the model", calls() == n_calls)
    ok("writes brand_voice.json in the old shape", v and all(k in v for k in ("company", "summary", "traits", "avoid", "examples", "what_they_sell", "who_buys")))
    ok("derived from brand-voice.md: the pillars are the traits", v["traits"] == ["Direct, Backed by Proof", "Operator's Eye", "Practitioners, Not Lecturers"], v["traits"])
    ok("the general tone is the summary", "experienced operator" in v["summary"], v["summary"])
    ok("avoid comes from the Avoid lines and the Not-That pairs", "managers" in v["avoid"] and any("vague scale words" in a for a in v["avoid"]), v["avoid"])
    ok("examples are the ✅ excerpts, verbatim", v["examples"] and v["examples"][0].startswith("We build programmes"), v["examples"])
    ok("what_they_sell is the one-liner, who_buys the primary audience", v["what_they_sell"].startswith("Example —") and "Founders" in v["who_buys"])
    ok("the company is the brand", v["company"] == "Example")
except Exception as e:
    import traceback; traceback.print_exc()
    ok("runs", False, e)

print("\nprompts")
ok("every {{TOKEN}} in every brand prompt was filled before the model saw it", not UNFILLED, UNFILLED[:3])

shutil.rmtree(store.chat_dir(c))
print("\nStubbed model and Reddit. Proves plumbing, the code-enforced rules and resume, not judgment quality.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all brand checks passed")
