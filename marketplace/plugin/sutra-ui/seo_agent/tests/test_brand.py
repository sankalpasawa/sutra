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
SEEN = []              # every prompt, so a test can prove what actually reached the model


def _json(prompt, system=None, retries=1, **kw):
    CALLS["json"] += 1
    SEEN.append(prompt)
    if "{{" in prompt:
        UNFILLED.append(prompt[:80])
    return _fixture.stub_json(prompt, system, retries)


def _text(prompt, system=None, **kw):
    CALLS["text"] += 1
    SEEN.append(prompt)
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

from seo_agent.tools import _shared as sh, learn_brand, onboard
from seo_agent.brand import (_common as cm, brand_cards, brand_facts, features, pack, style_guide,
                             type_roles, writer_brief)
from seo_agent.brand import cta as ctamod        # `cta` below is the FILE's text, read at step 4


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
ok("stats.md rows carry the invisible draft marker and a source URL",
   "| Customers | 1,500+ | https://example.com/" in stats and "\"Trusted by 1,500+ teams\" |<!--d-->" in stats)
ok("no warning symbol reaches the file", "⚠️" not in stats and "⚠️" not in cm.template("stats"))
ok("stats rows were deduped across pages", stats.count("| Customers |") == 1, stats.count("| Customers |"))
ok("the drafted rows sit under the right bucket",
   stats.index("## Results / proof") < stats.index("| Time-to-hire cut |") < stats.index("## Credibility"))
stories = brand("stories.md")
ok("stories.md keeps its headings", "## Stories" in stories and "## The interview" in stories)
ok("stories are marked entries in the template's format", "### Acme cut its hiring time<!--d-->" in stories
   and "- Point it makes:" in stories and "- Source: https://example.com/customers/acme" in stories)
ok("no warning symbol reaches stories.md either", "⚠️" not in stories and "⚠️" not in cm.template("stories"))
ok("the stories placeholder was replaced", "*(none yet)*" not in stories.split("## The interview")[0])
ok("opinions.md is gone: no builder writes it and no file lists it",
   not cm.exists("opinions.md") and "opinions.md" not in pack.FILES and "opinions.md" not in brand_facts.FILES)
ok("brand-facts asks for nothing: no row counts, no symbols, no opinions interview",
   not any(n.startswith(("stats.md", "stories.md", "opinions.md")) for n in out["needs_review"])
   and not any("⚠️" in n for n in out["needs_review"]), out["needs_review"])

# A DRAFTED ROW MUST BE ONE LINE. The stat, the number, the URL and the quote all come back from
# the model, and a quote with a line break in it used to be written straight into the row: the row
# became two, and the half without the marker read to human_confirmed() as a row a PERSON had
# confirmed. That one newline was enough to make the file look finished, so the next rebuild would
# divert its drafts to _drafts/ and the owner would never see them in stats.md again. Caught on a
# live run against real pages on 2026-09-09, where 4 of 43 drafted rows split this way.
# The newline is inside the QUOTE and nowhere else, which is exactly how it arrived in the wild:
# the row splits after three pipes, so the first half is a well-formed unmarked table row and the
# marker rides away on the second half.
_messy = {"stat": "tests in library", "value": "3,500+", "url": "https://example.com/x/",
          "quote": "3,500+ tests for\nevery role you hire"}
_row = brand_facts._stat_row(_messy)
_table = "| Stat | Value | Source-note |\n|---|---|---|\n" + _row + "\n"
ok("a drafted stat row is one line however the model wrote its cells", "\n" not in _row, repr(_row))
ok("and it still ends with the draft marker, so it is still a draft",
   _row.endswith(brand_facts.DRAFT), _row[-40:])
ok("so the machine's own draft is NOT read as a row a person confirmed",
   not brand_facts.human_confirmed(_table), _row)
ok("a pipe inside a value cannot open a new column: three cells, four pipes",
   brand_facts._stat_row(dict(_messy, quote="a | b")).count("|") == 4,
   brand_facts._stat_row(dict(_messy, quote="a | b")))
ok("a story title with a newline cannot leave a bare ### heading behind",
   "\n" not in brand_facts._story_block({"title": "Acme\nships", "url": "https://example.com/a"})[0])

print("\n1 brand-facts: the seed rule")
confirmed = stats.replace("| Customers | 1,500+ | https://example.com/ — \"Trusted by 1,500+ teams\" |<!--d-->",
                          "| Customers | 1,500+ | https://example.com/ — confirmed by: Dev, 2026-01-02 |")
ok("the test set up a confirmed row", brand_facts.human_confirmed(confirmed) and not brand_facts.human_confirmed(stats))
cm.save("stats.md", confirmed)
say = lambda label, note="": None
n0 = calls()
brand_facts.run({"brand": "Example", "domain": "example.com", "niche_definition": "", "language_code": "en"}, say, redo=True)
ok("a confirmed stats.md is never clobbered", brand("stats.md") == confirmed)
ok("new candidates go beside it", cm.exists("_drafts/stats-new-candidates.md")
   and "## Product / scale" in brand("_drafts/stats-new-candidates.md")
   and "<!--d-->" in brand("_drafts/stats-new-candidates.md") and "⚠️" not in brand("_drafts/stats-new-candidates.md"))
ok("redo re-read the pages", calls() > n0)
def marked_stories(text=None):
    """Drafted story ENTRIES, not every mention of the marker: the template's rule line names the
    tag so a person can find it, and counting raw occurrences counts that line too."""
    return sum(1 for ln in (text if text is not None else brand("stories.md")).splitlines()
               if ln.startswith("### ") and brand_facts.is_draft(ln))


ok("a redo replaces the drafted stories instead of appending a second copy", marked_stories() == 2, marked_stories())
ok("strip_drafts(): the marked rows go, a confirmed row stays", brand_facts.strip_drafts(confirmed, "stats").count("| Customers |") == 1
   and not any(brand_facts.is_draft(ln) for ln in brand_facts.strip_drafts(confirmed, "stats").splitlines() if ln.startswith("|")))
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

# The style guide's own human gate, end to end. The original workflow flags its two [COMPANY]
# fields "confirm with marketing" and expects a person to say yes; that is a confirm-a-draft
# gate exactly like the personas, and it surfaces at the brand-pack checkpoint. A review on
# 2026-09-09 recorded it as never ported, having read only the workflow. It IS ported -- across
# the template, the prompt and the builder's note -- and nothing tied the three together, so any
# one of them could go missing and the gate would just quietly stop existing.
ok("the template still has [COMPANY] fields for a person to confirm",
   "[COMPANY" in cm.template("style-guide"))
ok("the prompt still tells the model to flag every one it fills",
   "confirm with marketing" in cm.prompt("fill-template"))
ok("the phrase counter counts lines, not files",
   cm.count_lines("a — confirm with marketing\nb\nc — confirm with marketing\n", "confirm with marketing") == 2)
ok("and the builder turns those lines into a note at the checkpoint",
   any("to confirm with marketing" in n for n in out["needs_review"]), out["needs_review"])

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

print("\n4 features: pricing.md, the facts a crawler cannot reach")
# Finding 8.21: features.py read a human-verified seed and called it authoritative, and nothing in
# Sutra could write it. The file now exists as a blank form the moment the builder runs, so the
# Knowledge tab has a door to open.
ok("the blank form is on disk, so there is something to open and type into", cm.exists("pricing.md"))
ok("a blank form is not content: the builder is handed nothing",
   features.pricing() == "" and features.untouched(brand("pricing.md")))
ok("pricing.md sits in the pack immediately before the file it feeds",
   pack.FILES.index("pricing.md") == pack.FILES.index("features.md") - 1, pack.FILES)
ok("it has a plain name and a line saying what it is for",
   pack.LABELS["pricing.md"][0] == "Prices and hidden facts" and "JavaScript" in pack.LABELS["pricing.md"][1])
ok("pack.inputs() lists it in the same row shape the rest of the screen uses",
   [f["name"] for f in pack.inputs()] == ["pricing.md"]
   and set(pack.inputs()[0]) == {"name", "label", "note", "exists", "words", "filled"}, pack.inputs())
# WORDS CANNOT ANSWER THIS. The blank form is real text on disk and counts about 200 words, so a
# screen deciding "has anybody written in this?" from the word count would call an untouched form
# filled and stop asking. That is precisely how the seed file this replaces stayed empty (8.21).
ok("a blank form reports itself as not filled in, even though it has 200 words of its own",
   pack.inputs()[0]["filled"] is False and pack.inputs()[0]["words"] > 100, pack.inputs())
_before = brand("pricing.md")
cm.save("pricing.md", _before + "\n\nStarter $69/mo, 100 candidate credits a year, 3 users.\n")
ok("and one line typed into it flips that, without the word count saying anything useful",
   pack.inputs()[0]["filled"] is True, pack.inputs())
cm.save("pricing.md", _before)
ok("the old seed path is not read while pricing.md is there", not cm.exists("_seed/features-seed.md"))
ok("nothing is stale straight after a build", not features.pricing_stale())
ok("the SEED-WINS rule is still exactly what the original says",
   "the SEED WINS" in cm.prompt("fill-schema") and "AUTHORITATIVE" in cm.prompt("fill-schema"))

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
ok("persona.md has the table and the reader-not-author warning",
   "| Persona | Who | Reads | Cares about | Depth & angle | Not this |" in pe and "READER we write TO" in pe
   and "## How to pick the persona for an article" in pe)
ok("three personas", pe.count("| **") == 3, pe.count("| **"))

print("\n7 the byline feature is gone")
# Deleted whole on 2026-09-09, the owner's words: "remove completely everything about the byline
# questions, everything from Sutra for now." Not disabled — removed, so nothing can quietly wire
# a half-built questionnaire back in.
ok("no voices.md is written, and nothing lists one",
   not cm.exists("voices.md") and "voices.md" not in pack.FILES and "voices.md" not in pack.LABELS
   and "voices.md" not in writer_brief.SOURCE_FILES)
ok("there is no builder to run", not any(k == "voices" for k, _m, _f in learn_brand.BUILDERS)
   and "voices" not in learn_brand.KEYS)
ok("and no setup question to ask",
   [q for q, _f in onboard.QUESTIONS] == ["numbers", "origin-story", "lesson-learned", "competitors"]
   and onboard.BRAND_FILES == ["stats.md", "stories.md"], onboard.QUESTIONS)
ok("their prompt files are gone too",
   not os.path.exists(os.path.join(sh.PROMPTS, "onboard", "byline.md"))
   and not os.path.exists(os.path.join(sh.PROMPTS, "onboard", "founder-voice.md")))
ok("the writer brief no longer has a section about who signs it",
   "## Who is writing" not in cm.template("writer-brief") and "byline" not in cm.template("writer-brief-rulings"))

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
for h in ("## What we believe", "## Naming Example", "## How our writing sounds", "## Words we use",
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
ok("results from unapproved stories are marked unconfirmed", all(c.get("confirmed") is False for c in bc["results"])
   and any("nobody has approved" in n for n in out["needs_review"]), out["needs_review"])
ok("and the card's text carries no marker", all("<!--d-->" not in c["verbatim"] and "⚠️" not in c["verbatim"]
                                                for c in bc["results"]), [c["verbatim"][:40] for c in bc["results"]])
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

print("\npricing.md -> features.md, the one hop")
# The whole point of the file: a person types in a price the crawler cannot see, and the product
# facts the writer reads are filled again from it. Reusing the cached facts, so NO page is read
# again, and rebuilding features.md and nothing else (the owner's call: "we can skip writing
# integrity, we can skip the writer brief as well").
_PRICES = ("# Prices and hidden facts\n\n## Pricing and plans\n\n"
           "Starter is $69 a month billed annually, 100 credits a year. The trial runs 7 days "
           "with no card, and there is a 30-day money-back guarantee.\n")
_facts_before = brand("_work/features/facts.json")
_stamps = {f: os.path.getmtime(cm.path(f)) for f in
           ("_work/features/source-pages.json", "writing-integrity.md", "writer-brief.md")}
cm.save("pricing.md", _PRICES)                     # a person types their prices in the Knowledge tab
ok("what a person typed is content, and it is what the builder reads", features.pricing() == _PRICES)
ok("features.md is stale, because it was filled from a different pricing.md", features.pricing_stale())
n_calls, n_seen = calls(), len(SEEN)
out4 = learn_brand.run(ctx)
ok("the pack rebuilt features.md rather than reporting it already built",
   any(e["label"] == "Your prices changed" for e in events), [e["label"] for e in events][-6:])
ok("the typed-in prices reached the fill prompt as the authoritative seed",
   any("$69 a month" in t and "the SEED WINS" in t for t in SEEN[n_seen:]),
   [t[:60] for t in SEEN[n_seen:]])
ok("no page was read again: the crawled facts were reused as they were",
   brand("_work/features/facts.json") == _facts_before)
ok("and the page list was not rebuilt either",
   os.path.getmtime(cm.path("_work/features/source-pages.json")) == _stamps["_work/features/source-pages.json"])
ok("a rebuild is one fill and one gate, not a crawl", calls() - n_calls == 2, calls() - n_calls)
ok("features.md is in the files it reports", "features.md" in (out4.get("files") or []), out4.get("files"))
ok("THE CHAIN IS ONE HOP: writing-integrity.md and writer-brief.md are left alone",
   all(os.path.getmtime(cm.path(f)) == _stamps[f] for f in ("writing-integrity.md", "writer-brief.md")))
ok("and it is not stale any more", not features.pricing_stale())
n_calls = calls()
learn_brand.run(ctx)
ok("so the next run goes back to keeping what is built", calls() == n_calls, calls() - n_calls)

# The save hook: a person editing the file marks features.md for a rebuild without doing the slow
# work inside the save itself.
ok("saving pricing.md by hand marks features.md for a rebuild",
   features.pricing_saved() is True and features.pricing_stale())
features._stamp()
ok("and stamping it settles it again", not features.pricing_stale())

# The owner has real prices in the original's path. They are migrated across, never lost.
_now = brand("pricing.md")
os.remove(cm.path("pricing.md"))
cm.save("_seed/features-seed.md", "# Features seed\n\nStarter $99/mo. Annual billing saves 30%.\n")
ok("with no pricing.md, the original's own seed file is read", "Starter $99/mo" in features.pricing())
ok("and it is migrated to pricing.md, so it is editable from then on",
   cm.exists("pricing.md") and "Starter $99/mo" in brand("pricing.md"))
ok("the old file is left where it is: deleting somebody's text is not this builder's call",
   cm.exists("_seed/features-seed.md"))
os.remove(cm.path("_seed/features-seed.md"))
cm.save("pricing.md", _now)
features._stamp()

print("\npack.summary()")
ps = pack.summary()
names = [f["name"] for f in ps["files"]]
ok("lists every brand file in build order", names[0] == "type-roles.json" and "writer-brief.md" in names and names[-1] == "seo-aeo-geo-checklist.md")
ok("every file exists after a full run", all(f["exists"] for f in ps["files"]), [f["name"] for f in ps["files"] if not f["exists"]])
ok("no flags and no needs_review reach the screen any more",
   set(ps) == {"files"} and all(set(f) == {"name", "exists", "words"} for f in ps["files"]),
   (sorted(ps), sorted(ps["files"][0])))

print("\nthe invisible draft marker, end to end")
# The round trip that matters: draft -> a person confirms one row -> redraft. The confirmed row must
# still be there afterwards, and the machine's own rows must be replaced rather than doubled.
_ROUND = ("# Stats — Example\n\n"
          "## Product / scale\n| Stat | Value | Source-note |\n|---|---|---|\n"
          "| Customers | 1,500+ | https://example.com/ — \"quote\" |<!--d-->\n"
          "| Cohorts | 40 | https://example.com/ — confirmed by: Dev, 2026-01-02 |\n")
ok("a marked row is a draft and an unmarked one is confirmed",
   brand_facts.already_drafted(_ROUND) and brand_facts.human_confirmed(_ROUND))
ok("stripping the drafts keeps the confirmed row and loses the marked one",
   "| Cohorts |" in brand_facts.strip_drafts(_ROUND, "stats")
   and "| Customers |" not in brand_facts.strip_drafts(_ROUND, "stats"))
ok("a file of nothing but drafts is not 'confirmed'",
   not brand_facts.human_confirmed(_ROUND.replace("| Cohorts | 40 | https://example.com/ — confirmed by: Dev, 2026-01-02 |", "")))
ok("a bare template is not 'confirmed' and is not 'drafted'",
   not brand_facts.human_confirmed(cm.template("stats")) and not brand_facts.already_drafted(cm.template("stats")))

# tools/onboard.py is a SECOND writer into these two files: it puts the setup interview's answers
# into a delimited block. Those answers are the owner's prose, not rows anybody confirmed, and if
# the gate read them as confirmed then answering one question would cost him the whole machine
# draft. onboard.py keeps tables and ### headings out of its block for exactly that reason; the
# gate masks the block as well, so an answer's own words can never trip it either.
_IVIEW = ("<!-- setup-interview:start -->\n\n## Asked at setup\n\n"
          "**What numbers do you publish?**\n\n"
          "### Our figures | 1,500 | teams |\nWe say 1,500 teams everywhere.\n\n"
          "*(the team, 2026-09-09)*\n\n<!-- setup-interview:end -->\n")
_PLAIN = cm.template("stats")
ok("an interview answer, even one shaped like a row or a heading, is not a confirmation",
   not brand_facts.human_confirmed(_PLAIN + "\n" + _IVIEW),
   [l for l in _IVIEW.splitlines() if l.startswith(("|", "###"))])
ok("and it does not read as a machine draft either", not brand_facts.already_drafted(_PLAIN + "\n" + _IVIEW))
ok("a confirmed row OUTSIDE the block still counts",
   brand_facts.human_confirmed(_IVIEW + "\n| Customers | 1,500 | https://example.com/ — confirmed by: Dev |"))
ok("stripping the drafts never touches the interview block",
   brand_facts.strip_drafts(_IVIEW + "\n| x | y | z |<!--d-->\n", "stats").count("### Our figures") == 1
   and "<!-- setup-interview:end -->" in brand_facts.strip_drafts(_IVIEW, "stats"))
ok("and neither does the migration off the old symbol",
   brand_facts.migrate("# S\n\n" + _IVIEW.replace("1,500 teams", "1,500 ⚠️ teams") + "\n| a | b | ⚠️ c |\n", "stats")
   .count("⚠️") == 1)

# the whole point: answer a question, then draft, and the machine's own rows still appear
_kd = cm.path("stats.md")
cm.save("stats.md", cm.template("stats").replace("{{BRAND}}", "Example") + "\n" + _IVIEW)
brand_facts.run({"brand": "Example", "domain": "example.com", "niche_definition": "", "language_code": "en"}, say)
ok("after an interview answer, the machine still drafts the numbers the site publishes",
   "| Customers | 1,500+ |" in brand("stats.md") and brand_facts.already_drafted(brand("stats.md")),
   brand("stats.md")[:200])
ok("and the interview answer is still in the file, untouched",
   "<!-- setup-interview:start -->" in brand("stats.md") and "We say 1,500 teams everywhere." in brand("stats.md"))

# a legacy file, exactly as the owner's installed app holds it
_LEGACY = ("# Stats — Testlify (canonical real numbers)\n\n"
           "> Machine-drafted 2026-09-09 from 62 pages: 35 unique candidates. EVERY row marked ⚠️ is unconfirmed.\n\n"
           "> **Rule:** when writing, pull numbers from this file. Anything marked ⚠️ is\n"
           "> unconfirmed (machine-drafted) — confirm before\n"
           "> using in published copy. A confirmed row loses its ⚠️.\n\n"
           "## Product / scale\n| Stat | Value | Source-note |\n|---|---|---|\n"
           "| talent teams | 1,500+ | ⚠️ https://testlify.com/ — \"1,500+talent teams\" |\n"
           "| cohorts run | 40 | https://testlify.com/ — confirmed by: Dev |\n")
ok("a legacy ⚠️ row still reads as a draft, not as confirmed",
   brand_facts.already_drafted(_LEGACY) and brand_facts.is_draft("| x | y | ⚠️ z |"))
ok("and the confirmed row beside it still reads as confirmed", brand_facts.human_confirmed(_LEGACY))
_MIG = brand_facts.migrate(_LEGACY, "stats")
ok("migrating clears every warning symbol", "⚠️" not in _MIG, [l for l in _MIG.splitlines() if "⚠️" in l])
ok("the drafted row keeps its meaning, its number and its source",
   "| talent teams | 1,500+ | https://testlify.com/ — \"1,500+talent teams\" |<!--d-->" in _MIG
   and brand_facts.already_drafted(_MIG))
ok("the confirmed row is untouched by the migration",
   "| cohorts run | 40 | https://testlify.com/ — confirmed by: Dev |" in _MIG and brand_facts.human_confirmed(_MIG))
ok("the paragraph that explained the symbol is replaced whole, not left in half",
   "unconfirmed (machine-drafted) — confirm before" not in _MIG and "> **Rule:** when writing" in _MIG
   and "Machine-drafted 2026-09-09" not in _MIG)
ok("migrating a file that is already clean changes nothing", brand_facts.migrate(_MIG, "stats") == _MIG)

# and through the builder: a legacy file the builder decides to KEEP is still cleaned
cm.save("stats.md", _LEGACY)
_n = calls()
brand_facts.run({"brand": "Example", "domain": "example.com", "niche_definition": "", "language_code": "en"}, say)
ok("a legacy file the builder keeps is still migrated on the next run",
   "⚠️" not in brand("stats.md") and "<!--d-->" in brand("stats.md"))
ok("and it was migrated without re-reading a single page", calls() == _n, calls() - _n)
cm.save("stats.md", study)          # put the study back for anything downstream

print("\nthe CTA page list: brand/cta.py")
_before = brand("cta-pages.md")
_rows = ctamod.rows()
ok("every generated row parses back out of the file it was written to",
   _rows and all(r["url"].startswith("http") for r in _rows) and not any(r["mine"] for r in _rows), _rows[:2])
ok("the row order is the file's order, homepage first",
   _rows[0]["url"] == "https://example.com/", [r["url"] for r in _rows])
ok("a generated row's note falls back to its kind", _rows[0]["note"] == "homepage", _rows[0])
ok("the title is looked up from the catalogue",
   _rows[0]["title"] == "Example: education for operators", _rows[0]["title"])

# the save round trip: the person's whole list, in their order, one page not in the catalogue
_saved = ctamod.save("Example", [
    {"url": "https://example.com/pricing/", "note": "send everyone here"},
    {"url": "https://example.com/brand-new-page/", "note": "shipped after the last crawl"},
    {"url": "https://example.com/", "note": ""},
])
ok("save/load round trip: the same rows come back in the same order",
   [r["url"] for r in _saved] == [r["url"] for r in ctamod.rows()]
   == ["https://example.com/pricing/", "https://example.com/brand-new-page/", "https://example.com/"], [r["url"] for r in _saved])
ok("every saved row is the person's", all(r["mine"] for r in _saved), _saved)
ok("the note the person typed comes back verbatim", _saved[0]["note"] == "send everyone here", _saved[0])
ok("a page the catalogue has never seen is allowed, and comes back with an empty title",
   _saved[1]["url"] == "https://example.com/brand-new-page/" and _saved[1]["title"] == "", _saved[1])
ok("a page the catalogue knows still gets its title", _saved[2]["title"] == "Example: education for operators", _saved[2])
_txt = brand("cta-pages.md")
ok("the writer's parser still finds every url: `- Page:` lines, one per row",
   re.findall(r"^- Page: (\S+)", _txt, re.M)[:3]
   == ["https://example.com/pricing/", "https://example.com/brand-new-page/", "https://example.com/"],
   re.findall(r"^- Page: (\S+)", _txt, re.M)[:3])
ok("the mine marker never lands inside the url the parser captures", "<!--mine-->" not in "".join(re.findall(r"^- Page: (\S+)", _txt, re.M)))
ok("the crawl's own detail survived the person's save (the writer reads this text)",
   "- Kind: homepage" in _txt and "## Dropped, and why" in _txt)

# validation
_co = {"domain": "example.com"}
ok("a url on somebody else's domain is refused",
   "not on example.com" in ctamod.check("https://rival.com/pricing", "example.com"), ctamod.check("https://rival.com/pricing", "example.com"))
ok("something that is not a web address is refused", ctamod.check("pricing", "example.com").endswith("http:// or https://."))
ok("a url the catalogue has never seen is NOT refused", ctamod.check("https://example.com/brand-new-page/", "example.com") == "")
ok("www and the apex are the same site", ctamod.check("https://www.example.com/x", "example.com") == "")

# the rebuild: the person's rows must survive the features builder running again
_n = calls()
features.run({"brand": "Example", "domain": "example.com", "niche_definition": "", "language_code": "en"}, say, redo=True)
_after = ctamod.rows()
_mine = [r for r in _after if r["mine"]]
ok("a person-authored row survives a features rebuild",
   [r["url"] for r in _mine] == ["https://example.com/pricing/", "https://example.com/brand-new-page/", "https://example.com/"],
   [r["url"] for r in _mine])
ok("and it is re-emitted ABOVE the generated rows",
   [r["mine"] for r in _after] == sorted([r["mine"] for r in _after], reverse=True), [(r["url"], r["mine"]) for r in _after])
ok("the person's note survived the rebuild too", _mine[0]["note"] == "send everyone here", _mine[0])
ok("a page the person already listed is not written a second time by the crawl",
   len([r for r in _after if r["url"].rstrip("/") == "https://example.com"]) == 1, [r["url"] for r in _after])
ok("the crawl's other pages are still there", any(not r["mine"] for r in _after), [(r["url"], r["mine"]) for r in _after])
ok("the file the writer reads still parses to the same urls",
   set(re.findall(r"^- Page: (\S+)", brand("cta-pages.md"), re.M)) == {r["url"] for r in _after})

print("\n0 type-roles: the plain-English names")
_roles = brand("type-roles.json")
ok("type-roles.json carries a display name for every type it was shown",
   isinstance(_roles.get("display_names"), dict) and set(_roles["display_names"]) >= {"page", "post", "product"},
   _roles.get("display_names"))
ok("a name was decided for every type, with no second model call",
   all(isinstance(v, str) and v for v in _roles["display_names"].values()), _roles["display_names"])
ok("pretty() is the floor under a name the model left out",
   type_roles.pretty("test-library") == "Test library" and type_roles.pretty("hr_glossary") == "Hr glossary"
   and type_roles.pretty("") == "", type_roles.pretty("test-library"))
ok("display_names() answers for the types asked about, never for others",
   set(type_roles.display_names(["post", "made-up-type"])) == {"post", "made-up-type"}
   and type_roles.display_names(["made-up-type"])["made-up-type"] == "Made up type",
   type_roles.display_names(["post", "made-up-type"]))

print("\n8 writing-integrity: Rule 1's product boundary")
from seo_agent.brand import writing_integrity as wi
_keep = {n: brand(n) for n in ("features.md", "writer-brief.md", "writing-integrity.md")}
_co8 = {"brand": "Example", "domain": "example.com", "niche_definition": "", "language_code": "en"}


def _boundary(features_text, brief_text, co=None):
    cm.save("features.md", features_text)
    cm.save("writer-brief.md", brief_text)
    return wi.product_is_not(co or _co8)


def _rule1():
    """Rebuild writing-integrity.md and hand back Rule 1's is-NOT slot as it ships."""
    wi.run(_co8, say, redo=True)
    return brand("writing-integrity.md")


# FILLS: the only true boundary in the owner's whole pack is one item with no comma in it
ok("a one-item boundary fills the slot",
   _boundary("# F\n\nNothing about boundaries here.\n", "# B\n\nExample is not another ATS. We test skills.\n")
   == "another ATS", _boundary("# F\n", "# B\n\nExample is not another ATS.\n"))
ok("and Rule 1 ships filled, not as a decision for a person",
   "another ATS" in _rule1() and wi.SLOT_IS_NOT not in _rule1())
ok("a sentence-initial It works too",
   _boundary("# F\n\nWe test skills. It is not an ATS.\n", "# B\n") == "ATS")
ok("a comma list still works, and the longest match in a file wins",
   _boundary("# F\n\nIt is not an ATS. It is not an ATS, an HRIS, or a job board.\n", "# B\n")
   == "ATS, an HRIS, or a job board")
ok("features.md outranks the writer brief",
   _boundary("# F\n\nIt is not a payroll tool.\n", "# B\n\nExample is not another ATS.\n") == "payroll tool")
ok("a lowercase brand in the record still matches how the pages spell it",
   _boundary("# F\n", "# B\n\nExample is not another ATS.\n", {"brand": "example"}) == "another ATS")

# DOES NOT FILL: the false positive that used to be the only thing the pattern found
_INCL = "# F\n\nWe build a community where inclusion is not only valued but prioritized every day.\n"
ok("a sentence about inclusion is not a product boundary", _boundary(_INCL, "# B\n") == "",
   repr(_boundary(_INCL, "# B\n")))
ok("and Rule 1 stays a marked decision rather than shipping that",
   wi.SLOT_IS_NOT in _rule1() and "inclusion" not in _rule1())
ok("`is not only / just / merely` is rhetoric, never a boundary",
   all(_boundary("# F\n\nIt is not %s a test library.\n" % w, "# B\n") == "" for w in ("only", "just", "merely")))
ok("`it is not` inside a word never matches",
   _boundary("# F\n\nthe quality is not measured by seat count here\n", "# B\n") == "")
ok("neither file saying anything leaves the slot empty, never invented",
   _boundary("# F\n\nNothing.\n", "# B\n\nNothing.\n") == "" and wi.SLOT_IS_NOT in _rule1())
_rec = store.knowledge("brand/company.json")
store.save_knowledge("brand/company.json", dict(_rec, product_is_not="a payroll system or an HRIS"))
_boundary("# F\n", "# B\n\nExample is not another ATS.\n")
ok("the record's own product_is_not outranks anything read out of the pack",
   "a payroll system or an HRIS" in _rule1() and "another ATS" not in _rule1())
store.save_knowledge("brand/company.json", _rec)
for _n, _v in _keep.items():
    cm.save(_n, _v)
ok("the files this section borrowed were put back", brand("writer-brief.md") == _keep["writer-brief.md"])

print("\nthe /knowledge brand shape")
_b = {"brand": "Example", "brief": pack.brief(), "built_from": pack.built_from(),
      "extras": pack.extras(), "cta": {"count": ctamod.count()}}
ok("brief carries exists, words and the text verbatim",
   _b["brief"]["exists"] and _b["brief"]["words"] > 50 and _b["brief"]["text"] == brand("writer-brief.md"))
# The owner asked that this door show "only the actual files which were used". So the assertion is
# against what writer_brief.py actually reads, not against what anyone assumed. features.md is
# EXCLUDED there by name. voices.md was a fourth source until the byline feature was deleted.
ok("built_from is exactly what the brief is really assembled from, in build order",
   [f["name"] for f in _b["built_from"]]
   == ["brand-voice.md", "style-guide.md", "persona.md", "writing-integrity.md",
       "writer-brief-rulings.md"],
   [f["name"] for f in _b["built_from"]])
ok("features.md is NOT one of them: the builder excludes it by name",
   "features.md" not in pack.built_from_names() and "features.md" not in writer_brief.SOURCE_FILES)
ok("the deleted voices.md is not offered as a source either",
   "voices.md" not in pack.built_from_names())
ok("built_from is derived from the builder, not typed out",
   set(pack.built_from_names())
   <= (set(writer_brief.SOURCE_FILES) | {writer_brief.RULINGS, "persona.md"}))
ok("every built_from row carries a plain name, a note, exists and a word count",
   all(set(f) == {"name", "label", "note", "exists", "words"} and f["label"] and f["note"] for f in _b["built_from"]),
   _b["built_from"][0])
ok("a file that is not there is included, marked not built, so the screen can grey it",
   [f["exists"] for f in pack.built_from()] == [True] * 5
   and (lambda: (os.remove(cm.path("persona.md")),
                 [f["exists"] for f in pack.built_from()])[1])() == [True, True, False, True, True])
shutil.copyfile(cm.path("writer-brief.md"), cm.path("persona.md"))   # put a file back where one was
ok("extras is features.md, and it is honestly marked as in use",
   [(f["name"], f["in_use"]) for f in _b["extras"]] == [("features.md", True)], _b["extras"])
ok("cta is a count and nothing else", set(_b["cta"]) == {"count"} and _b["cta"]["count"] == len(ctamod.rows()), _b["cta"])
ok("no needs_review and no flags anywhere in the shape",
   "needs_review" not in _b and "flags" not in repr(_b)[:200] and not any("flags" in f for f in _b["built_from"]))

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
